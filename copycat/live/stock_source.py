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
from copycat.live.tc4 import BARS_POLL_DEADLINE, TC4QuoteSource, build_rt_request
from copycat.tc4common import TC4_DEFAULT_PORT, iter_qry_pages

logger = logging.getLogger(__name__)

_TRADING_START = _dt.time(8, 30)
_TRADING_END = _dt.time(13, 35)

_DAILY_WINDOW_DAYS = 40  # 日 K 抓取視窗(日曆日;25 交易日 + 假日餘裕)

# K 線 fallback:DK 空時改走 1K 聚合,但 1K 量級是 DK 的數百倍(180 日曆日 ≈ 4.8 萬列
# 分頁收割)→ fallback 另用較小視窗,寧可根數不足也不打爆 REQ 往返(change-spec R2-7)
_OHLC_FALLBACK_WINDOW_DAYS = 90

# 1K 分鐘域(台北,終點標記;與 fetch_day_minutes 同一把尺)
_MIN_DOMAIN_START = "0901"
_MIN_DOMAIN_END = "1330"
_MIN_CLAMP_END = "1335"


class DailyBar(TypedDict):
    """overlay 用日 bar(毫元;date = YYYY-MM-DD)。定義在 source 層避免 live→server 逆依賴。"""

    date: str
    high: int
    low: int
    close: int


class Bar(TypedDict):
    """K 線 bar(毫元整數;`t` 日 K = YYYY-MM-DD、分 K = "YYYY-MM-DD HH:MM" 台北)。

    與 DailyBar 分開定義:後者是 overlay(實盤路徑)在用的,只有 high/low/close,
    不得為了畫蠟燭去動它(change-spec W-D2)。"""

    t: str
    o: int
    h: int
    l: int  # noqa: E741 - 與前端 Bar 欄位對齊(o/h/l/c/v)
    c: int
    v: int


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


def _int_field(row: dict, *names: str) -> int:
    """量欄位名未實測(DK 尤其)→ 依序試,全缺回 0(缺量不該讓整根 bar 掉)。"""
    for name in names:
        raw = row.get(name)
        if raw is None or raw == "":
            continue
        try:
            return int(float(raw))
        except ValueError:
            continue
    return 0


def parse_dk_bars(rows: list[dict]) -> list[Bar]:
    """DK rows → 日 Bar。缺 Open → 用 Close(欄位名未實測,CLAUDE.md §8 只實證 H/L/C)。"""
    bars: list[Bar] = []
    skipped = 0
    for r in rows:
        try:
            close = _milli(r["Close"])
            bars.append(
                Bar(
                    t=_iso_date(str(r["Date"])),
                    o=_milli(r["Open"]) if r.get("Open") else close,
                    h=_milli(r["High"]),
                    l=_milli(r["Low"]),
                    c=close,
                    v=_int_field(r, "Volume", "TotalVolume", "Vol"),
                )
            )
        except (KeyError, ValueError):
            skipped += 1
    if skipped:
        logger.warning("DK bars 解析略過 %d/%d 列(欄位缺漏/格式)", skipped, len(rows))
    bars.sort(key=lambda b: b["t"])
    return bars


def _taipei_minute_key(
    raw_time: str,
    domain_start: str = _MIN_DOMAIN_START,
    domain_end: str = _MIN_DOMAIN_END,
    clamp_end: str = _MIN_CLAMP_END,
) -> str | None:
    """1K Time(UTC HHMMSS)→ 台北 HHMM 終點標記;域外回 None。

    `domain_end`+1 ~ `clamp_end` clamp 為 `domain_end`(收盤補正),與 `fetch_day_minutes` 同規則。

    **域是可換的尺**(index-board R-3 修正):預設值是**個股**日盤 09:00–13:30;
    台指期日盤是 08:45–13:45,套個股的尺會丟掉 08:46–09:00(開盤跳空是看盤重點)、
    把 13:31–13:35 的成交錯併進 13:30 那根、再丟掉 13:36–13:45 —— 圖畫得出來、
    根數也合理,沒有任何 assertion 會紅。"""
    raw = raw_time.zfill(6)
    hh = (int(raw[:2]) + 8) % 24
    key = f"{hh:02d}{raw[2:4]}"
    if domain_end < key <= clamp_end:
        key = domain_end
    if not (domain_start <= key <= domain_end):
        return None
    return key


def _merge_into(bar: Bar, o: int, h: int, low: int, c: int, v: int) -> None:
    """同 t 的後續列併入(o 保留第一根、c 取最後一根)。"""
    bar["h"] = max(bar["h"], h)
    bar["l"] = min(bar["l"], low)
    bar["c"] = c
    bar["v"] += v


class _RawK(TypedDict):
    date: str  # YYYY-MM-DD
    time: str  # 原始 UTC HHMMSS(排序用)
    o: int
    h: int
    l: int  # noqa: E741
    c: int
    v: int


def _parse_1k_rows(rows: list[dict]) -> list[_RawK]:
    """1K rows → 中性列(不套分鐘域過濾;分鐘域是 x 軸語意,日聚合不該吃)。"""
    out: list[_RawK] = []
    skipped = 0
    for r in rows:
        try:
            close = _milli(r["Close"])
            out.append(
                _RawK(
                    date=_iso_date(str(r["Date"])),
                    time=str(r["Time"]).zfill(6),
                    o=_milli(r["Open"]) if r.get("Open") else close,
                    h=_milli(r["High"]),
                    l=_milli(r["Low"]),
                    c=close,
                    v=_int_field(r, "Volume", "TotalVolume", "Vol"),
                )
            )
        except (KeyError, ValueError):
            skipped += 1
    if skipped:
        logger.warning("1K bars 解析略過 %d/%d 列(欄位缺漏/格式)", skipped, len(rows))
    out.sort(key=lambda k: (k["date"], k["time"]))
    return out


def _fold(bars: dict[str, Bar], order: list[str], t: str, k: _RawK) -> None:
    existing = bars.get(t)
    if existing is None:
        bars[t] = Bar(t=t, o=k["o"], h=k["h"], l=k["l"], c=k["c"], v=k["v"])
        order.append(t)
    else:
        _merge_into(existing, k["o"], k["h"], k["l"], k["c"], k["v"])


def parse_1k_bars(rows: list[dict], domain: tuple[str, str, str] | None = None) -> list[Bar]:
    """1K rows → 分鐘 Bar(台北終點標記;域外丟棄)。

    clamp 後同 t 會有多列(個股 13:31–13:35 全標 1330)→ **必須合併**:`fetch_day_minutes`
    回 dict 靠 key 覆寫躲掉了這件事,list 不會(change-spec R2-6)。

    `domain` = `(start, end, clamp_end)`;`None` = 個股日盤(既有行為)。
    期貨傳 `FUTURES_MINUTE_DOMAIN`。"""
    d = domain if domain is not None else (_MIN_DOMAIN_START, _MIN_DOMAIN_END, _MIN_CLAMP_END)
    by_key: dict[str, Bar] = {}
    order: list[str] = []
    for k in _parse_1k_rows(rows):
        key = _taipei_minute_key(k["time"], d[0], d[1], d[2])
        if key is None:
            continue
        _fold(by_key, order, f"{k['date']} {key[:2]}:{key[2:]}", k)
    return [by_key[t] for t in order]


def aggregate_1k_to_daily(rows: list[dict]) -> list[Bar]:
    """1K rows → 日 Bar(DK 不支援時的 fallback;o = 當日第一根 open、v = 加總)。

    **不套分鐘域過濾** —— 域(0901–1330)是江波圖 x 軸語意,套進日聚合會把域外列
    (如試撮/開盤前後)的量與極值靜默丟掉,與既有 `_aggregate_1k_rows` 行為也不一致。"""
    by_date: dict[str, Bar] = {}
    order: list[str] = []
    for k in _parse_1k_rows(rows):
        _fold(by_date, order, k["date"], k)
    return [by_date[d] for d in order]


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
        port: str = TC4_DEFAULT_PORT,
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
    #
    # `_collect_history` 已上提到基底 `TC4QuoteSource`(index-board R-3):futures_source
    # 的 K 線路徑要用同一份收割/退避/deadline 邏輯,各寫一份必然漂移。

    def fetch_day_minutes(self, code: str) -> dict[str, int]:
        """當日 1K → {HHMM(台北,bar 終點標記): close 毫點}(index-board SC-4)。

        1K Time 為 UTC 終點標記(實測 09:01 起);域 0901–1330 inclusive,
        1331–1335 clamp "1330"(收盤補正),其餘丟棄(design F5/IR4)。"""
        self._ensure_connected()
        sym = stock_symbol(code)
        start, end = stock_window(self._trade_date)
        rows = self._collect_history(sym, "1K", start, end)
        minutes: dict[str, int] = {}
        skipped = 0
        for r in rows:
            try:
                key = _taipei_minute_key(str(r["Time"]))
                value = round(float(r["Close"]) * 1000)
            except (KeyError, ValueError):
                skipped += 1
                continue
            if key is None:  # 域外靜默丟棄(不計入 skipped)
                continue
            minutes[key] = value
        if skipped:
            logger.warning("1K minutes 解析略過 %d/%d 列", skipped, len(rows))
        return minutes

    def fetch_bars_range(self, code: str, tf: str, start_date: str, end_date: str) -> list[Bar]:
        """K 線 bar(`tf` = "D" 日 K / "1" 分 K;start/end = YYYY-MM-DD 含端點)。

        range 型而非 days 型:server 層要把「歷史段(永久 memo)」與「當日段(短 TTL)」
        分開取,才不會每次輪詢都重拉整段歷史(change-spec R2-1/R2-2)。

        `tf="D"` 走 DK,空則 fallback 1K 聚合 —— fallback 視窗另行縮到
        `_OHLC_FALLBACK_WINDOW_DAYS`,避免 4.5× 量級放大(R2-7)。"""
        return self.fetch_bars_range_tagged(code, tf, start_date, end_date)[0]

    def fetch_bars_range_tagged(
        self, code: str, tf: str, start_date: str, end_date: str
    ) -> tuple[list[Bar], str]:
        """同 `fetch_bars_range`,另回**實際走到的資料源標籤**。

        大盤頁的 meta 行要誠實說出這一份 bar 從哪來(index-board review P1-4):
        `tf="D"` 在 DK 空時會 fallback 成 90 日窗的 1K 聚合,若 meta 仍標 `tc4_dk`,
        「壞了 vs 沒資料看畫面即可答」的設計主軸剛好在最可能出事的那條路上失效。

        `source_tag ∈ {"tc4_1k", "tc4_dk", "tc4_dk_1k_agg"}`。
        """
        self._ensure_connected()
        sym = stock_symbol(code)
        start = f"{start_date.replace('-', '')}00"
        end = f"{end_date.replace('-', '')}23"
        if tf == "1":
            rows = self._collect_history(sym, "1K", start, end, BARS_POLL_DEADLINE)
            return parse_1k_bars(rows), "tc4_1k"

        bars = parse_dk_bars(self._collect_history(sym, "DK", start, end, BARS_POLL_DEADLINE))
        if bars:
            return bars, "tc4_dk"
        fb_start = max(
            _dt.date.fromisoformat(start_date),
            _dt.date.fromisoformat(end_date) - _dt.timedelta(days=_OHLC_FALLBACK_WINDOW_DAYS),
        )
        logger.info("bars %s: DK 空,fallback 1K 聚合(視窗縮至 %s..%s)", code, fb_start, end_date)
        # fallback 也要傳短 budget:漏傳的話 tf=D 無資料標的變成 10 + 30 = 40s
        fb = aggregate_1k_to_daily(
            self._collect_history(sym, "1K", f"{fb_start:%Y%m%d}00", end, BARS_POLL_DEADLINE)
        )
        return fb, "tc4_dk_1k_agg"

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
