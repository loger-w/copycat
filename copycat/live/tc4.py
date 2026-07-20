"""TC4QuoteSource:達錢 4 ZMQ 介接(唯一碰 ZMQ 的模組;design.md §3)。

實測事實(docs/research/2026-07-18-txo-chain-probe.md):
- QUERYALLINSTRUMENT Type="Opt";symbol 葉子 = TC.O.TWF.<prod>.<expiry>.<C|P>.<strike>
- SUBQUOTE/UNSUBQUOTE(REALTIME)必須帶 StartTime/EndTime(當日 UTC 窗),wrapper 原
  SubQuote 未帶會回 "invalid Date Time Format" → 本模組自帶 raw request。
- 歷史 TICKS 分頁:QryIndex 迴圈 + 停滯防呆(同 backfill_tc4 慣例)。
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

import zmq

from copycat.live.models import (
    SPOT_SYMBOL,
    OptionContract,
    SeriesInfo,
    Tick,
    parse_history_tick,
    parse_option_symbol,
    parse_realtime,
)
from copycat.tc4common import TC4_APPID, TC4_SKEY, iter_qry_pages

__all__ = ["SPOT_SYMBOL", "TC4_APPID", "TC4_SKEY", "TC4QuoteSource", "group_series"]

logger = logging.getLogger(__name__)

_STALE_THRESHOLD_SECS = 30.0
_RECONNECT_BACKOFF_CAP = 60.0


def _today_ymd() -> str:
    return time.strftime("%Y%m%d", time.gmtime())


def build_rt_request(request: str, session: str, symbol: str, ymd: str) -> dict:
    """SUBQUOTE/UNSUBQUOTE REALTIME 請求(必帶當日 UTC 時間窗,spike 實測)。"""
    return {
        "Request": request,
        "SessionKey": session,
        "Param": {
            "Symbol": symbol,
            "SubDataType": "REALTIME",
            "StartTime": f"{ymd}00",
            "EndTime": f"{ymd}06",
        },
    }


def group_series(symbols: list[str]) -> list[SeriesInfo]:
    """期權葉子 symbol → 序列清單(expiry 近 → 遠,同 expiry 按產品代碼)。

    顯示名 = "<prod> <expiry>"(EndDate 僅 REALTIME 有,清單層拿不到 → fallback,IR-5)。
    """
    groups: dict[tuple[str, str], list[OptionContract]] = {}
    for sym in symbols:
        parsed = parse_option_symbol(sym)
        if parsed is None:
            continue
        prod, expiry, cp, strike = parsed
        groups.setdefault((prod, expiry), []).append(
            OptionContract(symbol=sym, cp=cp, strike_millipts=strike * 1000)
        )
    series = [
        SeriesInfo(
            series_id=f"{prod}.{expiry}",
            name=f"{prod} {expiry}",
            expiry=expiry,
            contracts=tuple(sorted(cs, key=lambda c: (c.strike_millipts, c.cp))),
        )
        for (prod, expiry), cs in groups.items()
    ]
    series.sort(key=lambda s: (s.expiry, s.series_id))
    return series


def _walk_strings(node: object, acc: list[str]) -> None:
    if isinstance(node, dict):
        for v in node.values():
            _walk_strings(v, acc)
    elif isinstance(node, list):
        for v in node:
            _walk_strings(v, acc)
    elif isinstance(node, str):
        acc.append(node)


class TC4QuoteSource:
    """QuoteSource 實作;api/session 可注入(測試),預設 lazy 連線真 TC4。"""

    def __init__(
        self,
        port: str = "50774",
        *,
        api: Any | None = None,
        session: str | None = None,
        poll_wait_secs: float = 1.0,
        backfill_date: str | None = None,
    ) -> None:
        self._port = port
        self._api = api
        self._session = session
        self._sub_port: str | None = None
        self._poll_wait = poll_wait_secs
        self._backfill_date = backfill_date.replace("-", "") if backfill_date else None
        self._on_tick: Callable[[Tick], None] | None = None
        self._subscribed: set[str] = set()
        self._listener: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_msg = time.monotonic()
        self._lock = threading.Lock()
        self.reconnects = 0
        self.on_reconnect: Callable[[], None] | None = None

    # ---- 連線 ----

    def _ensure_connected(self) -> None:
        if self._api is not None and self._session is not None:
            return
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "spikes" / "TCPY"))
        from tcoreapi_mq import QuoteAPI  # type: ignore[import-untyped]

        api = QuoteAPI(TC4_APPID, TC4_SKEY)
        q = api.Connect(self._port)
        if q.get("Success") != "OK":
            raise ConnectionError(f"TC4 login failed: {q}")
        self._api = api
        self._session = q["SessionKey"]
        self._sub_port = q["SubPort"]
        logger.info("TC4 connected, session=%s", self._session[:8])

    def _rt_request(self, request: str, symbol: str) -> dict:
        assert self._api is not None and self._session is not None
        obj = build_rt_request(request, self._session, symbol, _today_ymd())
        api = self._api
        api.lock.acquire()
        try:
            api.socket.send_string(json.dumps(obj))
            message = api.socket.recv()[:-1]
        finally:
            api.lock.release()
        return json.loads(message)

    # ---- QuoteSource 介面 ----

    def list_series(self) -> list[SeriesInfo]:
        self._ensure_connected()
        assert self._api is not None
        res = self._api.QueryAllInstrumentInfo(self._session, "Opt")
        if res.get("Success") != "OK":
            raise ConnectionError(f"TC4 QUERYALLINSTRUMENT failed: {res.get('ErrMsg')}")
        strings: list[str] = []
        _walk_strings(res, strings)
        leaves = sorted({s for s in strings if s.startswith("TC.O.TWF.")})
        return group_series(leaves)

    def fetch_backfill(self, series: SeriesInfo) -> list[Tick]:
        self._ensure_connected()
        assert self._api is not None
        ymd = self._backfill_date or _today_ymd()
        start, end = f"{ymd}00", f"{ymd}06"
        # 先對全鏈送 SubHistory 讓 TC4 平行備資料再逐檔收割 —
        # 逐檔「Sub → 等 → 收」實測 280 檔 ~10 分鐘,先全訂可砍掉大部分等待(Phase 4 自評)
        for contract in series.contracts:
            self._api.SubHistory(self._session, contract.symbol, "TICKS", start, end)
        ticks: list[Tick] = []
        for i, contract in enumerate(series.contracts):
            ticks.extend(self._fetch_symbol_ticks(contract.symbol, start, end))
            if (i + 1) % 20 == 0:
                logger.info(
                    "backfill %d/%d symbols, %d ticks", i + 1, len(series.contracts), len(ticks)
                )
        logger.info("backfill done: %d ticks from %d symbols", len(ticks), len(series.contracts))
        return ticks

    def _fetch_symbol_ticks(self, symbol: str, start: str, end: str) -> list[Tick]:
        assert self._api is not None
        api = self._api
        rows: list[dict] = []
        first: dict | None = None
        for attempt in range(6):
            first = api.GetHistory(self._session, symbol, "TICKS", start, end, "0")
            if first and first.get("HisData"):
                break
            if self._poll_wait and attempt < 5:
                time.sleep(self._poll_wait * 0.3)  # 全鏈已先 SubHistory,等待縮短
        if not first or not first.get("HisData"):
            return []

        def _page(qry_index: str) -> list[dict]:
            his = api.GetHistory(self._session, symbol, "TICKS", start, end, qry_index)
            return his.get("HisData", [])

        for page in iter_qry_pages(_page):
            rows.extend(page)
        return [t for r in rows if (t := parse_history_tick(symbol, r)) is not None]

    def subscribe(self, series: SeriesInfo, on_tick: Callable[[Tick], None]) -> None:
        self._ensure_connected()
        self._on_tick = on_tick
        self._start_listener()
        symbols = [c.symbol for c in series.contracts]
        if SPOT_SYMBOL not in self._subscribed:
            symbols.append(SPOT_SYMBOL)  # TXF 現貨獨立於序列(DR-13),首次順帶訂
        for sym in symbols:
            self._rt_request("UNSUBQUOTE", sym)
            r = self._rt_request("SUBQUOTE", sym)
            if r.get("Success") != "OK":
                logger.warning("SUBQUOTE fail %s: %s", sym, r.get("ErrMsg"))
                continue
            self._subscribed.add(sym)
        logger.info("subscribed %d symbols (series=%s)", len(self._subscribed), series.series_id)

    def unsubscribe(self, series: SeriesInfo) -> None:
        for contract in series.contracts:  # 不含 TXF(DR-13)
            if contract.symbol in self._subscribed:
                self._rt_request("UNSUBQUOTE", contract.symbol)
                self._subscribed.discard(contract.symbol)

    def close(self) -> None:
        self._stop.set()
        if self._api is not None:
            for sym in list(self._subscribed):
                try:
                    self._rt_request("UNSUBQUOTE", sym)
                except (zmq.ZMQError, ConnectionError, OSError, json.JSONDecodeError):
                    # 收工路徑:退訂失敗多半是連線已死,其餘 symbol 也會失敗;
                    # 停止嘗試但仍必須往下走 Disconnect(§0a)
                    logger.exception("UNSUBQUOTE failed during close: %s", sym)
                    break
            self._api.Disconnect()  # §0a KeepAlive 生命週期:不呼叫則 process 不退出
            self._api = None

    # ---- REALTIME 監聽(thread)----

    def _start_listener(self) -> None:
        if self._listener is not None:
            return
        assert self._sub_port is not None, "listener 需要真連線的 SubPort"
        self._listener = threading.Thread(target=self._listen_loop, daemon=True)
        self._listener.start()

    def _listen_loop(self) -> None:
        import zmq

        ctx = zmq.Context()
        sock: zmq.Socket | None = None
        bound_port: str | None = None
        while not self._stop.is_set():
            if sock is None or self._sub_port != bound_port:
                # 重連會換 SubPort(_check_stale → _ensure_connected);listener 不跟隨
                # 則新 session 推播(含 PING)永遠收不到 → 30 秒週期無限重連
                # (2026-07-20 盤中實證 30 次;同 tc4_trade R3-1 的跟隨語意)
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
            idx = raw.find(":")
            if idx < 0:
                continue
            try:
                msg = json.loads(raw[idx + 1 :])
            except json.JSONDecodeError:
                continue
            if msg.get("DataType") != "REALTIME":
                continue
            tick = parse_realtime(msg.get("Quote", {}))
            if tick is not None and self._on_tick is not None:
                self._on_tick(tick)
        if sock is not None:
            sock.close(linger=0)
        ctx.term()

    def _check_stale(self) -> None:
        """PING 都收不到超過閾值 → 判斷線,重連 + 重訂閱 + 通知 on_reconnect(補回遺失段)。"""
        if time.monotonic() - self._last_msg < _STALE_THRESHOLD_SECS:
            return
        backoff = 1.0
        while not self._stop.is_set():
            logger.warning("TC4 stale >%ss, reconnecting...", _STALE_THRESHOLD_SECS)
            try:
                with self._lock:
                    if self._api is not None:
                        self._api.Disconnect()
                    self._api = None
                    self._session = None
                    self._ensure_connected()
                    resub = list(self._subscribed)
                    self._subscribed = set()
                    for sym in resub:
                        self._rt_request("UNSUBQUOTE", sym)  # 冪等,與 subscribe 路徑一致(Alt-4)
                        r = self._rt_request("SUBQUOTE", sym)
                        if r.get("Success") == "OK":
                            self._subscribed.add(sym)
                self.reconnects += 1
                self._last_msg = time.monotonic()
                if self.on_reconnect is not None:
                    self.on_reconnect()
                logger.info("TC4 reconnected (total=%d)", self.reconnects)
                return
            except (ConnectionError, OSError):
                logger.exception("reconnect attempt failed, backoff %.0fs", backoff)
                if self._stop.wait(backoff):
                    return
                backoff = min(backoff * 2, _RECONNECT_BACKOFF_CAP)
