"""StockQuoteSource:個股 TC4 資料源(design v4 §2.3)。

繼承 TC4QuoteSource 複用連線/REQ 全域互斥/_dispose/stale 重連機制(不動 tc4.py,
案 A:TXO 實盤路徑零風險)。覆寫:

- `_rt_request`:REALTIME 窗 = 個股當日 UTC 日盤窗(非 TXO 時段窗)。
- listener 原始分派:REALTIME → `on_message(Quote dict)`(book/meta 都要,不能只回 Tick)。
- 逐檔 subscribe/unsubscribe(refcount 池在 engine 層)+ 無推播健檢(訂閱後 N 秒
  無該檔任何推播 → `on_no_data(code)`;僅交易時段生效 — 個股休市 snapshot 行為
  未實測,design R5)。
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import threading
import time
from typing import Any, Callable, TypedDict

from copycat.live.stock_models import StockTick, parse_hist_tick
from copycat.live.tc4 import TC4QuoteSource, build_rt_request
from copycat.tc4common import iter_qry_pages

logger = logging.getLogger(__name__)

_TRADING_START = _dt.time(8, 30)
_TRADING_END = _dt.time(13, 35)

_DAILY_WINDOW_DAYS = 40  # 日 K 抓取視窗(日曆日;25 交易日 + 假日餘裕)


class DailyBar(TypedDict):
    """overlay 用日 bar(毫元;date = YYYY-MM-DD)。定義在 source 層避免 live→server 逆依賴。"""

    date: str
    high: int
    low: int
    close: int


def _milli(raw: str) -> int:
    return round(float(raw) * 1000)


def _iso_date(ymd: str) -> str:
    return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}"


def _parse_dk_rows(rows: list[dict]) -> list[DailyBar]:
    bars: list[DailyBar] = []
    skipped = 0
    for r in rows:
        try:
            bars.append(
                DailyBar(
                    date=_iso_date(str(r["Date"])),
                    high=_milli(r["High"]),
                    low=_milli(r["Low"]),
                    close=_milli(r["Close"]),
                )
            )
        except (KeyError, ValueError):
            skipped += 1
    if skipped:
        # DK 欄位格式未實測(design Known Risk 1):略過計數是唯一診斷訊號
        logger.warning("DK rows 解析略過 %d/%d 列(欄位缺漏/格式)", skipped, len(rows))
    bars.sort(key=lambda b: b["date"])
    return bars


def _aggregate_1k_rows(rows: list[dict]) -> list[DailyBar]:
    """1K rows → 日 bar(per Date:high=max、low=min、close=最後一根 close,依 Time 序)。"""
    by_date: dict[str, list[tuple[str, int, int, int]]] = {}
    skipped = 0
    for r in rows:
        try:
            item = (str(r["Time"]), _milli(r["High"]), _milli(r["Low"]), _milli(r["Close"]))
        except (KeyError, ValueError):
            skipped += 1
            continue
        by_date.setdefault(str(r["Date"]), []).append(item)
    if skipped:
        logger.warning("1K rows 解析略過 %d/%d 列(欄位缺漏/格式)", skipped, len(rows))
    bars: list[DailyBar] = []
    for ymd in sorted(by_date):
        items = sorted(by_date[ymd], key=lambda x: x[0])
        bars.append(
            DailyBar(
                date=_iso_date(ymd),
                high=max(h for _, h, _lo, _c in items),
                low=min(lo for _, _h, lo, _c in items),
                close=items[-1][3],
            )
        )
    return bars


def stock_symbol(code: str) -> str:
    """股號 → TC4 symbol。上市/上櫃都掛 TWS 段(2026-07-21 spike:5483 上櫃推播成功)。

    `F:<prod>` 前綴 = 個股期(期現對照加訂)→ 期貨樹 HOT;誤走股票段時 SUBQUOTE
    照回 OK 零錯誤訊號(2026-07-21 real-env 實證),前綴分流是唯一防線。"""
    if code.startswith("F:"):
        return f"TC.F.TWF.{code[2:]}.HOT"
    return f"TC.S.TWS.{code}"


def stock_window(trade_date: str) -> tuple[str, str]:
    """台北交易日 YYYY-MM-DD → 日盤 UTC 窗(09:00–13:30 台北 = 01:00–05:30 UTC)。"""
    day = trade_date.replace("-", "")
    return f"{day}00", f"{day}06"


def in_trading_hours_now() -> bool:
    now = _dt.datetime.now().time()
    return _TRADING_START <= now <= _TRADING_END


class StockQuoteSource(TC4QuoteSource):
    def __init__(
        self,
        port: str = "50774",
        *,
        api: Any | None = None,
        session: str | None = None,
        trade_date: str | None = None,
        poll_wait_secs: float = 1.0,
        no_data_secs: float = 10.0,
        in_trading_hours: Callable[[], bool] = in_trading_hours_now,
    ) -> None:
        super().__init__(port, api=api, session=session, poll_wait_secs=poll_wait_secs)
        self._trade_date = trade_date or f"{_dt.date.today():%Y-%m-%d}"
        self._no_data_secs = no_data_secs
        self._in_trading_hours = in_trading_hours
        self._on_message: Callable[[dict], None] | None = None
        self._on_no_data: Callable[[str], None] | None = None
        self._seen: set[str] = set()  # 已收過推播的股號(健檢用)
        self._seen_lock = threading.Lock()

    # ---- 設定 ----

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        self._on_message = cb

    def set_on_no_data(self, cb: Callable[[str], None]) -> None:
        self._on_no_data = cb

    def set_trade_date(self, trade_date: str) -> None:
        """rollover 階段一:換日窗(重掛訂閱由呼叫端執行)。"""
        self._trade_date = trade_date

    # ---- 覆寫:REALTIME 窗 = 個股當日日盤窗 ----

    def _rt_request(self, request: str, symbol: str) -> dict:
        window = stock_window(self._trade_date)
        return self._session_req(lambda session: build_rt_request(request, session, symbol, window))

    # ---- 逐檔訂閱 ----

    def subscribe_symbol(self, code: str) -> None:
        """UNSUB→SUB 冪等重掛;失敗 raise(engine refcount 回滾依賴,design §2.4)。"""
        self._ensure_connected()
        if self._sub_port is not None:
            # 真連線才有 SubPort;漏啟 = 訂閱成功但永收不到推播(2026-07-21 real-env 實證)
            self._start_listener()
        sym = stock_symbol(code)
        self._rt_request("UNSUBQUOTE", sym)
        r = self._rt_request("SUBQUOTE", sym)
        if r.get("Success") != "OK":
            raise ConnectionError(f"SUBQUOTE fail {sym}: {r.get('ErrMsg')}")
        self._subscribed.add(sym)
        with self._seen_lock:
            self._seen.discard(code)
        # 個股期(F:)不做無推播健檢:seen 以 Security(=股號)為鍵,期貨鍵對不上
        if not code.startswith("F:") and self._in_trading_hours():
            timer = threading.Timer(self._no_data_secs, self._health_check, args=(code,))
            timer.daemon = True
            timer.start()

    def unsubscribe_symbol(self, code: str) -> None:
        sym = stock_symbol(code)
        if sym in self._subscribed:
            self._rt_request("UNSUBQUOTE", sym)
            self._subscribed.discard(sym)

    def _health_check(self, code: str) -> None:
        with self._seen_lock:
            seen = code in self._seen
        if not seen and stock_symbol(code) in self._subscribed:
            if self._on_no_data is not None:
                self._on_no_data(code)

    # ---- 回補(收割分頁;跨 symbol 序列化由 engine worker queue 統籌)----

    def backfill(self, code: str) -> list[StockTick]:
        self._ensure_connected()
        sym = stock_symbol(code)
        start, end = stock_window(self._trade_date)
        self._sub_history(sym, start, end)
        rows: list[dict] = []
        deadline = time.monotonic() + max(self._poll_wait * 30, 1.0)
        while time.monotonic() < deadline:
            first = self._get_history(sym, start, end, "0")
            if first.get("HisData"):
                break
            if self._poll_wait:
                time.sleep(self._poll_wait)
        else:
            return []

        def _page(qry_index: str) -> list[dict]:
            return self._get_history(sym, start, end, qry_index).get("HisData", [])

        for page in iter_qry_pages(_page):
            rows.extend(page)
        ticks = [t for r in rows if (t := parse_hist_tick(code, r)) is not None]
        logger.info("stock backfill %s: %d ticks", code, len(ticks))
        return ticks

    # ---- 日 K(overlay 資料源;SC-4)----

    def _collect_history(self, sym: str, data_type: str, start: str, end: str) -> list[dict]:
        """SubHistory → 首頁 poll → QryIndex 收割;TC4 通訊失敗由 _req 收斂 ConnectionError。"""
        self._sub_history(sym, start, end, data_type)
        deadline = time.monotonic() + max(self._poll_wait * 30, 1.0)
        while True:
            first = self._get_history(sym, start, end, "0", data_type)
            if first.get("HisData"):
                break
            if time.monotonic() >= deadline:
                return []
            if self._poll_wait:
                time.sleep(self._poll_wait)

        def _page(qry_index: str) -> list[dict]:
            return self._get_history(sym, start, end, qry_index, data_type).get("HisData", [])

        rows: list[dict] = []
        for page in iter_qry_pages(_page):
            rows.extend(page)
        return rows

    def fetch_daily_bars(self, code: str, n: int = 25) -> list[DailyBar]:
        """近 n 根日 bar(DK 優先;DK 空/不支援 → 1K 聚合 fallback,股票 1K 一年已實證)。

        含今日 partial bar 也照回 — 「已完成 bar」剔除在 overlay 層(design R1)。"""
        self._ensure_connected()
        sym = stock_symbol(code)
        end_d = _dt.date.today()
        start_d = end_d - _dt.timedelta(days=_DAILY_WINDOW_DAYS)
        start, end = f"{start_d:%Y%m%d}00", f"{end_d:%Y%m%d}23"
        bars = _parse_dk_rows(self._collect_history(sym, "DK", start, end))
        if not bars:
            logger.info("daily bars %s: DK 空,fallback 1K 聚合", code)
            bars = _aggregate_1k_rows(self._collect_history(sym, "1K", start, end))
        return bars[-n:]

    # ---- listener:原始分派(覆寫 TXO 的 Tick 解析路徑)----

    def handle_raw(self, raw: str) -> None:
        """SUB socket 一則原始電文 → REALTIME Quote dict 分派(listener 與測試共用)。"""
        idx = raw.find(":")
        if idx < 0:
            return
        try:
            msg = json.loads(raw[idx + 1 :])
        except json.JSONDecodeError:
            return
        if msg.get("DataType") != "REALTIME":
            return
        quote = msg.get("Quote", {})
        code = str(quote.get("Security", ""))
        if code:
            with self._seen_lock:
                self._seen.add(code)
        if self._on_message is not None:
            self._on_message(quote)

    def _listen_loop(self) -> None:
        import zmq

        ctx = zmq.Context()
        sock: Any | None = None
        bound_port: str | None = None
        while not self._stop.is_set():
            if sock is None or self._sub_port != bound_port:
                # generation-following:重連換 SubPort 必須跟隨(07-20 盤中實證,同 tc4.py)
                if sock is not None:
                    sock.close(linger=0)
                sock = ctx.socket(zmq.SUB)
                sock.connect(f"tcp://127.0.0.1:{self._sub_port}")
                sock.setsockopt_string(zmq.SUBSCRIBE, "")
                sock.setsockopt(zmq.RCVTIMEO, 1_000)
                bound_port = self._sub_port
            try:
                raw = (sock.recv()[:-1]).decode("utf-8")
            except zmq.ZMQError:
                self._check_stale()
                continue
            self._last_msg = time.monotonic()
            self.handle_raw(raw)
        if sock is not None:
            sock.close(linger=0)
        ctx.term()
