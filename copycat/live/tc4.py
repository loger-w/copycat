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
from copycat.live.session import session_key, session_window
from copycat.tc4common import TC4_APPID, TC4_SKEY, iter_qry_pages

__all__ = ["SPOT_SYMBOL", "TC4_APPID", "TC4_SKEY", "TC4QuoteSource", "group_series"]

logger = logging.getLogger(__name__)

_STALE_THRESHOLD_SECS = 30.0
_RECONNECT_BACKOFF_CAP = 60.0
# context 級 REQ timeout:app 死亡時 Connect/_rt_request 的裸 recv 才可返回、重連迴圈
# 才可被 _stop 中斷。10s = 實測最重呼叫 QUERYALLINSTRUMENT(Opt) 1.93s 的 5 倍裕度;
# GetHistory 分頁實測 max 1.1ms(3,482 次、10.7 萬 rows)不受影響(2026-07-20 probe)。
_REQ_TIMEOUT_MS = 10_000
# 回補收割輪數上限與零進展早停(fetch_backfill round 制;空頁無法區分未備妥/無資料)
_HARVEST_ROUNDS = 8
_HARVEST_DRY_LIMIT = 3


def build_rt_request(request: str, session: str, symbol: str, window: tuple[str, str]) -> dict:
    """SUBQUOTE/UNSUBQUOTE REALTIME 請求(必帶合法 UTC 時間窗,spike 實測)。"""
    start, end = window
    return {
        "Request": request,
        "SessionKey": session,
        "Param": {
            "Symbol": symbol,
            "SubDataType": "REALTIME",
            "StartTime": start,
            "EndTime": end,
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
        lock_timeout_secs: float = 5.0,
    ) -> None:
        self._port = port
        self._api = api
        self._session = session
        self._sub_port: str | None = None
        self._poll_wait = poll_wait_secs
        self._lock_timeout = lock_timeout_secs
        self._backfill_date = backfill_date.replace("-", "") if backfill_date else None
        self._on_tick: Callable[[Tick], None] | None = None
        self._subscribed: set[str] = set()
        self._listener: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_msg = time.monotonic()
        self._lock = threading.Lock()
        # _api/_session 指標讀寫專用小鎖:_dispose 的 check-then-clear 與
        # _ensure_connected 的指標發布必須原子,否則 REQ 失敗的 worker 可能清掉
        # _check_stale 剛建好的新連線(round-2 P1)。與 self._lock 分離,
        # _check_stale 持大鎖中經 _req → _dispose 不會自鎖。
        self._api_lock = threading.Lock()
        self.reconnects = 0
        self.on_reconnect: Callable[[], None] | None = None

    # ---- 連線 ----

    def _ensure_connected(self) -> None:
        if self._api is not None and self._session is not None:
            return
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "spikes" / "TCPY"))
        from tcoreapi_mq import QuoteAPI  # type: ignore[import-untyped]

        api = QuoteAPI(TC4_APPID, TC4_SKEY)
        # Connect() 內部裸 recv → context 級 timeout 讓之後建立的 socket 全部繼承;
        # LINGER=0 讓失敗被棄的 api 在 GC term 時不為 pending LOGIN 無限阻塞
        # (同 tc4_trade R2-2 / F-1 防護;timeout 值依據見 _REQ_TIMEOUT_MS 註解)
        api.context.setsockopt(zmq.RCVTIMEO, _REQ_TIMEOUT_MS)
        api.context.setsockopt(zmq.SNDTIMEO, _REQ_TIMEOUT_MS)
        api.context.setsockopt(zmq.LINGER, 0)
        try:
            q = api.Connect(self._port)
        except (zmq.ZMQError, OSError) as exc:
            raise ConnectionError(f"TC4 quote connect failed: {exc}") from exc
        if q.get("Success") != "OK":
            raise ConnectionError(f"TC4 login failed: {q}")
        with self._api_lock:
            self._api = api
            self._session = q["SessionKey"]
        self._sub_port = q["SubPort"]
        logger.info("TC4 connected, session=%s", q["SessionKey"][:8])

    def _dispose(self, api: Any) -> None:
        """REQ 失敗即棄連線:timeout 後 REQ EFSM 壞狀態不可重用,若不丟棄,SUB 有 tick
        流動時 _check_stale 永不觸發 → REQ 通道永久壞死(review F2;同 tc4_trade _dispose)。

        不取 self._lock:_check_stale 持鎖中經 _rt_request 走到這裡,取鎖即自鎖。
        """
        with self._api_lock:
            if self._api is not api:
                return
            self._api = None
            self._session = None
        if api.lock.acquire(timeout=self._lock_timeout):
            try:
                api.Disconnect()
            except (zmq.ZMQError, OSError):
                logger.exception("TC4 quote Disconnect failed (best-effort)")
            finally:
                api.lock.release()
        else:
            logger.warning("TC4 quote dispose: api.lock busy,跳過實體 close(洩漏優於 crash)")

    def _connection(self) -> tuple[Any, str]:
        """_api/_session 一致快照(_api_lock,與 _dispose/_ensure_connected 寫側對齊):
        重連瞬間不可拿到「新 api × 舊 session」的錯配對(review P2:讀側也持鎖)。
        未連線 → ConnectionError(不可裸 assert,見 _req)。"""
        with self._api_lock:
            api, session = self._api, self._session
        if api is None or session is None:
            raise ConnectionError("TC4 quote not connected")
        return api, session

    def _session_req(self, build: Callable[[str], dict], *, strip_prefix: bool = False) -> dict:
        """帶 SessionKey 的 REQ:同一把快照取 (api, session) 再送,配對一致。"""
        api, session = self._connection()
        return self._req(build(session), api=api, strip_prefix=strip_prefix)

    def _req(self, obj: dict, *, api: Any | None = None, strip_prefix: bool = False) -> dict:
        """自組電文 REQ:lock timeout + 錯誤收斂 ConnectionError + 失敗棄連線。

        wrapper 方法(QueryAllInstrumentInfo/GetHistory/SubHistory)內部 blocking
        acquire 無 timeout、無 try/finally,毒鎖下永久阻塞、timeout 下裸拋 → 一律
        不直呼 wrapper,REQ 全走這裡(review F1;同 tc4_trade 自組電文模式)。
        strip_prefix:GETHISDATA 回應帶 "<type>:" 前綴(wrapper GetHistory 同語意)。
        """
        if api is None:
            with self._api_lock:
                api = self._api
        if api is None:
            # dispose 後殘存呼叫:收斂 ConnectionError,不可裸 assert 讓
            # AssertionError 逃出 engine 的 except ConnectionError 攔截網
            raise ConnectionError("TC4 quote not connected")
        if not api.lock.acquire(timeout=self._lock_timeout):
            # wrapper KeepAlive Pong 無 try/finally,timeout 毒鎖 → 棄連線重建,
            # 而非永久卡死
            self._dispose(api)
            raise ConnectionError("TC4 quote api.lock timeout")
        error: Exception | None = None
        message = b""
        try:
            api.socket.send_string(json.dumps(obj))
            message = api.socket.recv()[:-1]
        except (zmq.ZMQError, OSError) as exc:
            error = exc
        finally:
            api.lock.release()
        if error is not None:
            self._dispose(api)
            raise ConnectionError(f"TC4 quote request failed: {error}") from error
        if strip_prefix:
            text = message.decode("utf-8")
            idx = text.find(":")
            return json.loads(text[idx + 1 :] if idx >= 0 else text)
        return json.loads(message)

    def _rt_request(self, request: str, symbol: str) -> dict:
        window = session_window(session_key())
        return self._session_req(lambda session: build_rt_request(request, session, symbol, window))

    # ---- QuoteSource 介面 ----

    def list_series(self) -> list[SeriesInfo]:
        self._ensure_connected()
        res = self._session_req(
            lambda session: {
                "Request": "QUERYALLINSTRUMENT",
                "SessionKey": session,
                "Type": "Opt",
            }
        )
        if res.get("Success") != "OK":
            raise ConnectionError(f"TC4 QUERYALLINSTRUMENT failed: {res.get('ErrMsg')}")
        strings: list[str] = []
        _walk_strings(res, strings)
        leaves = sorted({s for s in strings if s.startswith("TC.O.TWF.")})
        return group_series(leaves)

    def fetch_backfill(self, series: SeriesInfo) -> list[Tick]:
        self._ensure_connected()
        if self._backfill_date:
            # TXO_BACKFILL_DATE 休市日回補:指定日期固定日盤窗,不隨當下時段走
            start, end = f"{self._backfill_date}00", f"{self._backfill_date}06"
        else:
            start, end = session_window(session_key())
        # 先對全鏈送 SubHistory 讓 TC4 平行備資料再逐檔收割 —
        # 逐檔「Sub → 等 → 收」實測 280 檔 ~10 分鐘,先全訂可砍掉大部分等待(Phase 4 自評)
        for contract in series.contracts:
            self._sub_history(contract.symbol, start, end)
        # round 制收割:空 symbol 不逐檔空等(舊制每空檔 6 查 + 5 sleep,夜盤深價外
        # 大量無成交會拖到分鐘級),等待改全局輪間 sleep;連續 _HARVEST_DRY_LIMIT 輪
        # 零進展 = 剩餘皆真無資料,早停(GETHISDATA 空頁無法區分「未備妥」與
        # 「無資料」,只能以進展停滯收斂)
        ticks: list[Tick] = []
        pending = [c.symbol for c in series.contracts]
        dry_rounds = 0
        for rnd in range(1, _HARVEST_ROUNDS + 1):
            if rnd > 1 and self._poll_wait:
                time.sleep(self._poll_wait * 0.5)  # 輪間等待放頂端:早停時不多睡尾輪
            still: list[str] = []
            for sym in pending:
                symbol_ticks = self._fetch_symbol_ticks(sym, start, end)
                if symbol_ticks:
                    ticks.extend(symbol_ticks)
                else:
                    still.append(sym)
            progressed = len(still) < len(pending)
            pending = still
            logger.info("backfill round %d: %d pending, %d ticks", rnd, len(pending), len(ticks))
            if not pending:
                break
            dry_rounds = 0 if progressed else dry_rounds + 1
            if dry_rounds >= _HARVEST_DRY_LIMIT:
                break
        logger.info("backfill done: %d ticks from %d symbols", len(ticks), len(series.contracts))
        return ticks

    def _sub_history(self, symbol: str, start: str, end: str) -> dict:
        return self._session_req(
            lambda session: {
                "Request": "SUBQUOTE",
                "SessionKey": session,
                "Param": {
                    "Symbol": symbol,
                    "SubDataType": "TICKS",
                    "StartTime": start,
                    "EndTime": end,
                },
            }
        )

    def _get_history(self, symbol: str, start: str, end: str, qry_index: str) -> dict:
        return self._session_req(
            lambda session: {
                "Request": "GETHISDATA",
                "SessionKey": session,
                "Param": {
                    "Symbol": symbol,
                    "SubDataType": "TICKS",
                    "StartTime": start,
                    "EndTime": end,
                    "QryIndex": qry_index,
                },
            },
            strip_prefix=True,
        )

    def _fetch_symbol_ticks(self, symbol: str, start: str, end: str) -> list[Tick]:
        # 單發:首頁空即回空(未備妥的重試由 fetch_backfill 的 round 制統籌,不逐檔等)
        rows: list[dict] = []
        first = self._get_history(symbol, start, end, "0")
        if not first.get("HisData"):
            return []

        def _page(qry_index: str) -> list[dict]:
            return self._get_history(symbol, start, end, qry_index).get("HisData", [])

        for page in iter_qry_pages(_page):
            rows.extend(page)
        return [t for r in rows if (t := parse_history_tick(symbol, r)) is not None]

    def subscribe(self, series: SeriesInfo, on_tick: Callable[[Tick], None]) -> None:
        self._ensure_connected()
        self._on_tick = on_tick
        self._start_listener()
        symbols = [c.symbol for c in series.contracts]
        # TXF 現貨獨立於序列(DR-13);每次都重掛(UNSUB→SUB 冪等)— rollover 重訂閱
        # 必須讓 spot 也換新時段窗,否則其訂閱窗永遠停在最初時段(review F2)
        symbols.append(SPOT_SYMBOL)
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
        with self._api_lock:
            connected = self._api is not None
        if connected:
            for sym in list(self._subscribed):
                try:
                    self._rt_request("UNSUBQUOTE", sym)
                except (zmq.ZMQError, ConnectionError, OSError, json.JSONDecodeError):
                    # 收工路徑:退訂失敗多半是連線已死,其餘 symbol 也會失敗;
                    # 停止嘗試但仍必須收尾 Disconnect(§0a)
                    logger.exception("UNSUBQUOTE failed during close: %s", sym)
                    break
        # 失敗路徑 _req 內已 _dispose(含 best-effort Disconnect)→ _api 可能已是
        # None,不可無條件 Disconnect(round-2 P0);仍在線才由此關(§0a KeepAlive
        # 生命週期:不關則 process 不退出)
        with self._api_lock:
            api = self._api
        if api is not None:
            self._dispose(api)

    # ---- REALTIME 監聽(thread)----

    def _start_listener(self) -> None:
        if self._listener is not None:
            return
        if self._sub_port is None:
            # 注入 api/session 而未真連線的路徑:收斂 ConnectionError,
            # 不讓 AssertionError 逃出 engine 的 except ConnectionError 攔截網
            raise ConnectionError("TC4 quote listener 需要真連線的 SubPort")
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
                    old = self._api
                    if old is not None:
                        # 舊 api 拆除統一走 _dispose(round-2 P2:消滅無鎖 Disconnect
                        # 與 _dispose 的雙路徑並發)
                        self._dispose(old)
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
            except (ConnectionError, OSError, zmq.ZMQError):
                # zmq.ZMQError:Disconnect / wrapper 路徑仍可能裸拋,漏接會殺 listener
                logger.exception("reconnect attempt failed, backoff %.0fs", backoff)
                if self._stop.wait(backoff):
                    return
                backoff = min(backoff * 2, _RECONNECT_BACKOFF_CAP)
