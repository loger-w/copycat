from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

import pytest
import zmq

import copycat.live.tc4 as tc4_mod
from copycat.live.tc4 import SPOT_SYMBOL, TC4QuoteSource, build_rt_request, group_series
from tests.conftest import requires_tcpy


def _free_port() -> int:
    """取一個當下無 listener 的 port(bind 後立即釋放)。"""
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


SYMS = [
    "TC.O.TWF.TX4.202607.C.44550",
    "TC.O.TWF.TX4.202607.P.44550",
    "TC.O.TWF.TX4.202607.C.44600",
    "TC.O.TWF.TX5.202607.C.44550",
    "TC.O.TWF.TXO.202608.C.44550",
    "TC.O.TWF.TXO.202608.P.44000",
    "TC.F.TWF.TXF.HOT",  # 非期權,應被忽略
    "TC.O.TWF.TXO.202608",  # 產品層節點,非葉子
]


class TestGroupSeries:
    def test_groups_leaf_symbols_by_prod_expiry(self) -> None:
        series = group_series(SYMS)
        ids = [s.series_id for s in series]
        assert ids == ["TX4.202607", "TX5.202607", "TXO.202608"]
        tx4 = series[0]
        assert len(tx4.contracts) == 3
        assert tx4.contracts[0].strike_millipts == 44_550_000
        assert tx4.name == "TX4 202607"

    def test_nearest_expiry_sorts_first(self) -> None:
        series = group_series(["TC.O.TWF.TXO.202612.C.44000", "TC.O.TWF.TXO.202608.C.44000"])
        assert [s.series_id for s in series] == ["TXO.202608", "TXO.202612"]


class TestBuildRtRequest:
    def test_subquote_carries_time_window(self) -> None:
        obj = build_rt_request(
            "SUBQUOTE", "sess-1", "TC.F.TWF.TXF.HOT", ("2026071800", "2026071806")
        )
        assert obj == {
            "Request": "SUBQUOTE",
            "SessionKey": "sess-1",
            "Param": {
                "Symbol": "TC.F.TWF.TXF.HOT",
                "SubDataType": "REALTIME",
                "StartTime": "2026071800",
                "EndTime": "2026071806",
            },
        }


class _JsonSocket:
    """socket 替身:send 的 JSON 電文交 handler 分派,recv 回其回應(自組電文路徑)。"""

    def __init__(self, handler: Any) -> None:
        self._handler = handler
        self._resp = b""
        self.sockopts: list[tuple[int, int]] = []

    def setsockopt(self, opt: int, value: int) -> None:
        self.sockopts.append((opt, value))

    def send_string(self, payload: str) -> None:
        self._resp = self._handler(json.loads(payload))

    def recv(self) -> bytes:
        return self._resp


class FakeApi:
    """最小 QuoteAPI 替身:socket 層分派(GETHISDATA 分頁語意 + SubHistory 呼叫記錄)。"""

    def __init__(self, pages: dict[str, list[list[dict]]]) -> None:
        self.lock = threading.Lock()
        self.socket = _JsonSocket(self._handle)
        self.pages = pages
        self.sub_history_calls: list[str] = []
        self.sub_history_windows: list[tuple[str, str]] = []
        # rt_requests = REALTIME 子集,既有測試拿它當分段視窗(clear 後看下一段),不可改成推導;
        # requests = 全部 REQ 依序,Disconnect 以 "<Disconnect>" 標記入列,收工序
        # UNSUB → LOGOUT → Disconnect 才在同一把尺上可斷言(review SP5;ST6 反駁見 JSON)
        self.rt_requests: list[dict] = []
        self.requests: list[dict] = []
        self.disconnected = False

    def _handle(self, req: dict) -> bytes:
        self.requests.append(req)
        kind = req.get("Request")
        if kind == "GETHISDATA":
            param = req["Param"]
            # GETHISDATA 回應帶 "<type>:" 前綴(真 TC4 / wrapper GetHistory 同語意)
            data = self._page(param["Symbol"], param["QryIndex"])
            return b"TICKS:" + json.dumps(data).encode() + b"\x00"
        if kind == "SUBQUOTE" and req.get("Param", {}).get("SubDataType") == "TICKS":
            self.sub_history_calls.append(req["Param"]["Symbol"])
            self.sub_history_windows.append(
                (req["Param"]["StartTime"], req["Param"]["EndTime"])
            )
        if req.get("Param", {}).get("SubDataType") == "REALTIME":
            self.rt_requests.append(req)
        return b'{"Success": "OK"}\x00'

    def _page(self, sym: str, qry_index: str) -> dict:
        # 真 TC4 語意:回傳 QryIndex 大於游標的下一批(耗盡 → 空頁)
        rows = [r for page in self.pages.get(sym, []) for r in page]
        idx = int(qry_index) if qry_index.isdigit() else 0
        remaining = [r for r in rows if int(r["QryIndex"]) > idx]
        return {"HisData": remaining[:100]}

    def Disconnect(self) -> None:  # noqa: N802
        self.requests.append({"Request": "<Disconnect>"})
        self.disconnected = True


def hist_row(i: int, *, price: str = "100", qty: str = "1") -> dict:
    return {
        "TradingPrice": price,
        "TradeQuantity": qty,
        "Bid": "99",
        "Ask": "100",
        "PreciseTime": str(10000000000 + i),
        "QryIndex": str(i),
    }


class TestFetchBackfill:
    def test_paged_history_parsed_and_flattened(self) -> None:
        sym = "TC.O.TWF.TX4.202607.C.44550"
        pages = {
            sym: [[hist_row(i) for i in range(1, 101)], [hist_row(i) for i in range(101, 121)]]
        }
        src = TC4QuoteSource(port="0", api=FakeApi(pages), session="sess-1", poll_wait_secs=0.0)
        series = group_series([sym])[0]
        ticks = src.fetch_backfill(series)
        assert len(ticks) == 120
        assert ticks[0].symbol == sym
        assert ticks[0].price_millipts == 100_000

    def test_stops_when_qry_index_does_not_advance(self) -> None:
        # TC4 若回傳停滯的 QryIndex(永遠指回同一頁),不可無限迴圈(同 backfill 停滯防呆)
        row = hist_row(1)
        row["QryIndex"] = "0"

        class _Stuck(FakeApi):
            def _page(self, sym: str, qry_index: str) -> dict:
                return {"HisData": [row]}

        src = TC4QuoteSource(port="0", api=_Stuck({}), session="sess-1", poll_wait_secs=0.0)
        ticks = src._fetch_symbol_ticks("TC.O.TWF.TX4.202607.C.44550", "2026071800", "2026071806")
        assert len(ticks) == 1

    def test_stops_on_empty_qry_index(self) -> None:
        # 末筆 QryIndex 空字串 = 分頁結束
        row = hist_row(1)
        row["QryIndex"] = ""

        class _LastPage(FakeApi):
            def _page(self, sym: str, qry_index: str) -> dict:
                return {"HisData": [row]}

        src = TC4QuoteSource(port="0", api=_LastPage({}), session="sess-1", poll_wait_secs=0.0)
        ticks = src._fetch_symbol_ticks("TC.O.TWF.TX4.202607.C.44550", "2026071800", "2026071806")
        assert len(ticks) == 1

    def test_late_ready_symbol_harvested_in_later_round(self) -> None:
        # round 制:首輪查詢時 TC4 尚未備妥(空頁)、之後備妥的 symbol 仍要被收割
        sym = "TC.O.TWF.TX4.202607.C.44550"

        class _LateReady(FakeApi):
            def __init__(self) -> None:
                super().__init__({sym: [[hist_row(1), hist_row(2)]]})
                self.first_page_queries = 0

            def _page(self, s: str, qry_index: str) -> dict:
                if qry_index == "0":
                    self.first_page_queries += 1
                    if self.first_page_queries <= 2:
                        return {"HisData": []}
                return super()._page(s, qry_index)

        src = TC4QuoteSource(port="0", api=_LateReady(), session="sess-1", poll_wait_secs=0.0)
        series = group_series([sym])[0]
        ticks = src.fetch_backfill(series)
        assert len(ticks) == 2

    def test_night_session_uses_night_window(self, monkeypatch: Any) -> None:
        # 夜盤時刻:回補與 REALTIME 訂閱都要用夜盤窗(cum 基準對齊的前提)
        sym = "TC.O.TWF.TX4.202607.C.44550"
        api = FakeApi({sym: [[hist_row(1)]]})
        src = TC4QuoteSource(port="0", api=api, session="sess-1", poll_wait_secs=0.0)
        monkeypatch.setattr("copycat.live.tc4.session_key", lambda: ("20260720", "night"))
        src.fetch_backfill(group_series([sym])[0])
        assert api.sub_history_windows[0] == ("2026072006", "2026072022")
        src._rt_request("SUBQUOTE", sym)
        param = api.rt_requests[-1]["Param"]
        assert (param["StartTime"], param["EndTime"]) == ("2026072006", "2026072022")

    def test_backfill_date_mode_pins_day_window(self, monkeypatch: Any) -> None:
        # TXO_BACKFILL_DATE 休市日回補:指定日期 = 該日日盤窗,不隨當下時段走(白名單 1)
        sym = "TC.O.TWF.TX4.202607.C.44550"
        api = FakeApi({sym: [[hist_row(1)]]})
        src = TC4QuoteSource(
            port="0", api=api, session="sess-1", poll_wait_secs=0.0, backfill_date="2026-07-18"
        )
        monkeypatch.setattr("copycat.live.tc4.session_key", lambda: ("20260720", "night"))
        src.fetch_backfill(group_series([sym])[0])
        assert api.sub_history_windows[0] == ("2026071800", "2026071806")

    def test_spot_resubscribed_on_every_subscribe(self, monkeypatch: Any) -> None:
        # review F2:spot 必須隨每次 subscribe 重掛(rollover 重訂閱要帶新時段窗;
        # 舊寫法 spot 已在 _subscribed 即跳過,訂閱窗永遠停在最初時段)
        sym = "TC.O.TWF.TX4.202607.C.44550"
        api = FakeApi({})
        src = TC4QuoteSource(port="0", api=api, session="sess-1", poll_wait_secs=0.0)
        monkeypatch.setattr(src, "_start_listener", lambda: None)
        series = group_series([sym])[0]
        src.subscribe(series, lambda t: None)
        src.subscribe(series, lambda t: None)
        spot_subs = [
            r
            for r in api.rt_requests
            if r["Request"] == "SUBQUOTE" and r["Param"]["Symbol"] == SPOT_SYMBOL
        ]
        assert len(spot_subs) == 2

    def test_empty_symbols_share_bounded_sleep_budget(self, monkeypatch: Any) -> None:
        """空 symbol 不逐檔空等:等待為全局輪間 sleep(≤ 輪數上限),與空 symbol 數無關。

        舊制每個空 symbol 自帶 5 次 sleep(3 檔 = 15 次);round 制下連續零進展
        即早停,sleep 次數必須遠小於逐檔制。
        """
        sleeps: list[float] = []
        monkeypatch.setattr("copycat.live.tc4.time.sleep", lambda s: sleeps.append(s))
        syms = [f"TC.O.TWF.TX4.202607.C.4{i}000" for i in range(3)]

        class _Counting(FakeApi):
            def __init__(self) -> None:
                super().__init__({})
                self.first_page_queries = 0

            def _page(self, sym: str, qry_index: str) -> dict:
                if qry_index == "0":
                    self.first_page_queries += 1
                return super()._page(sym, qry_index)

        api = _Counting()
        src = TC4QuoteSource(port="0", api=api, session="sess-1", poll_wait_secs=1.0)
        series = group_series(syms)[0]
        ticks = src.fetch_backfill(series)
        assert ticks == []
        # 連續 3 輪(_HARVEST_DRY_LIMIT)零進展早停:輪間 sleep 恰 2 次(輪 2、3 前),
        # 每 symbol 首頁查詢恰 3 次;舊制 3 檔 × 5 次 sleep = 15 會炸
        assert len(sleeps) == 2
        assert api.first_page_queries == 3 * len(syms)


def _rt_payload(symbol: str, vol: str) -> bytes:
    quote = {
        "Symbol": symbol,
        "TradingPrice": "100",
        "TradeQuantity": "1",
        "TradeVolume": vol,
        "PreciseTime": "20000000000",
    }
    import json as _json

    return b"Q:" + _json.dumps({"DataType": "REALTIME", "Quote": quote}).encode() + b"\x00"


class TestListenerFollowsSubPort:
    def test_listener_rebinds_when_sub_port_changes(self) -> None:
        """item 3(2026-07-20 盤中驗證):重連換 SubPort 後 listener 必須跟隨。

        盤中實證:達錢 4 重啟後重連成功,但 listener 停在舊 SubPort → 新 session 推播
        (含 PING)收不到 → 每 30 秒無限重連(實測 30 次),自癒永不收斂。
        """
        import zmq

        sym_a = "TC.O.TWF.TX4.202607.C.44000"
        sym_b = "TC.O.TWF.TX4.202607.C.44100"
        ctx = zmq.Context()
        pub_a = ctx.socket(zmq.PUB)
        port_a = pub_a.bind_to_random_port("tcp://127.0.0.1")
        pub_b = ctx.socket(zmq.PUB)
        port_b = pub_b.bind_to_random_port("tcp://127.0.0.1")
        got: list[str] = []
        src = TC4QuoteSource(port="0", api=FakeApi({}), session="sess-1")
        src._sub_port = str(port_a)
        src._on_tick = lambda t: got.append(t.symbol)
        src._start_listener()
        try:
            import time as _time

            deadline = _time.monotonic() + 5.0
            while sym_a not in got and _time.monotonic() < deadline:
                pub_a.send(_rt_payload(sym_a, "1"))  # PUB/SUB slow joiner:輪發到送達
                _time.sleep(0.05)
            assert sym_a in got, "baseline:port A 訊息未送達"
            src._sub_port = str(port_b)  # 模擬 _check_stale 重連換 SubPort
            deadline = _time.monotonic() + 5.0
            while sym_b not in got and _time.monotonic() < deadline:
                pub_b.send(_rt_payload(sym_b, "2"))
                _time.sleep(0.05)
            assert sym_b in got, "listener 未跟隨新 SubPort(item 3)"
        finally:
            src._stop.set()
            listener = src._listener
            if listener is not None:
                listener.join(timeout=3.0)
            pub_a.close(linger=0)
            pub_b.close(linger=0)
            ctx.term()


class TestListenerRawFiltering:
    """characterization(refactor C6 前置):listener 對壞電文的四道過濾與存活性。

    `_listen_loop` 的訊息處理段即將上提成 `handle_raw` hook,而 TXO 解析是唯一的
    實盤路徑 —— 搬移前先把「哪些電文會被靜默丟掉、丟掉後執行緒仍活著」釘住。
    走 real-PUB harness(基底此時尚無可直呼的 hook)。
    """

    def test_bad_messages_dropped_and_listener_survives(self) -> None:
        import json as _json
        import time as _time

        import zmq

        sym_warm = "TC.O.TWF.TX4.202607.C.43000"
        sym_ok = "TC.O.TWF.TX4.202607.C.44000"
        sym_noqty = "TC.O.TWF.TX4.202607.C.45000"
        sym_ping = "TC.O.TWF.TX4.202607.C.46000"
        ctx = zmq.Context()
        pub = ctx.socket(zmq.PUB)
        port = pub.bind_to_random_port("tcp://127.0.0.1")
        got: list[str] = []
        src = TC4QuoteSource(port="0", api=FakeApi({}), session="sess-1")
        src._sub_port = str(port)
        src._on_tick = lambda t: got.append(t.symbol)
        src._start_listener()
        try:
            # 暖身:PUB/SUB slow joiner,先確認連線已建立才能單發後斷言順序
            deadline = _time.monotonic() + 5.0
            while not got and _time.monotonic() < deadline:
                pub.send(_rt_payload(sym_warm, "1"))
                _time.sleep(0.05)
            assert got, "baseline:暖身訊息未送達"
            got.clear()

            no_qty = {
                "Symbol": sym_noqty,
                "TradingPrice": "100",
                "TradeQuantity": "0",  # 非台指期 + 零量 → parse_realtime 回 None
                "TradeVolume": "9",
                "PreciseTime": "20000000000",
            }
            # PING 帶**合法** Quote(與 sym_ok 那則同形,只換 symbol):空 PING 沒有 Quote,
            # DataType 過濾拿掉後解析照樣回 None → 那條過濾根本沒被鎖住。帶了 Quote,
            # 過濾一失效 got 就會多出 sym_ping(且 FIFO 排在 sym_ok 前面)。
            ping_with_quote = {
                "DataType": "PING",
                "Quote": {
                    "Symbol": sym_ping,
                    "TradingPrice": "100",
                    "TradeQuantity": "1",
                    "TradeVolume": "3",
                    "PreciseTime": "20000000000",
                },
            }
            # FIFO:壞電文全排在合法那則之前 → 任何一則沒被丟掉都會先出現在 got
            pub.send(b"nocolon-no-topic-separator\x00")
            pub.send(b"Q:not-json\x00")
            pub.send(b"Q:" + _json.dumps(ping_with_quote).encode() + b"\x00")
            rt_no_qty = _json.dumps({"DataType": "REALTIME", "Quote": no_qty}).encode()
            pub.send(b"Q:" + rt_no_qty + b"\x00")
            pub.send(_rt_payload(sym_ok, "2"))

            deadline = _time.monotonic() + 5.0
            while not got and _time.monotonic() < deadline:
                _time.sleep(0.05)
            assert got == [sym_ok]
            listener = src._listener
            assert listener is not None and listener.is_alive(), "壞電文不得殺死 listener 執行緒"
        finally:
            src._stop.set()
            listener = src._listener
            if listener is not None:
                listener.join(timeout=3.0)
            pub.close(linger=0)
            ctx.term()


class _ReqApi:
    """_rt_request 測試替身:真 threading.Lock + 可注入 socket 行為。"""

    def __init__(self, socket: Any) -> None:
        self.lock = threading.Lock()
        self.socket = socket
        self.disconnected = False

    def Disconnect(self) -> None:  # noqa: N802
        self.disconnected = True


class _RaisingSocket:
    def send_string(self, _payload: str) -> None:
        raise zmq.ZMQError()

    def recv(self) -> bytes:
        raise AssertionError("recv 不應被呼叫")


class TestLockTimeoutContract:
    """X-2a:等鎖上界必須大於單次 REQ 的上界(不等式契約,不是某個數字)。

    **健康慢路徑**的持鎖上界 ≈ RCVTIMEO(形式上界是 send+recv = 2×RCVTIMEO,但
    localhost REQ 的 send 只有對端死了才塞得滿 SNDTIMEO,那條路棄連線本來就正確);
    等鎖上界比健康上界小的話,一個**正常但慢**的 REQ(QUERYALLINSTRUMENT 實測
    1.93s,最壞到 RCVTIMEO)就會讓所有等鎖者 `_dispose` 整條連線 —— 那是把健康慢
    當成毒鎖治。
    """

    def test_default_lock_timeout_exceeds_req_timeout(self) -> None:
        src = TC4QuoteSource(port="0", api=object(), session="sess-1")
        assert src._lock_timeout * 1000 > tc4_mod._REQ_TIMEOUT_MS


class TestRtRequestResilience:
    """條 1(next-time 2026-07-20):REQ 路徑錯誤收斂 ConnectionError + lock timeout。"""

    def test_lock_timeout_raises_connection_error(self) -> None:
        api = _ReqApi(_RaisingSocket())
        api.lock.acquire()  # 模擬 Pong 毒鎖(wrapper 無 try/finally 路徑)
        src = TC4QuoteSource(port="0", api=api, session="sess-1", lock_timeout_secs=0.05)
        with pytest.raises(ConnectionError):
            src._rt_request("SUBQUOTE", "TC.F.TWF.TXF.HOT")

    def test_zmq_error_converted_and_lock_released(self) -> None:
        api = _ReqApi(_RaisingSocket())
        src = TC4QuoteSource(port="0", api=api, session="sess-1", lock_timeout_secs=0.5)
        with pytest.raises(ConnectionError):
            src._rt_request("SUBQUOTE", "TC.F.TWF.TXF.HOT")
        # lock 必須釋放(try/finally),否則下一次請求永久卡死
        assert api.lock.acquire(timeout=0.5) is True


class TestReqProtection:
    """review F1/F2:wrapper 直呼路徑收斂 _req(lock timeout + 錯誤轉換 + 失敗棄連線)。"""

    def test_list_series_converts_socket_error_to_connection_error(self) -> None:
        api = _ReqApi(_RaisingSocket())
        src = TC4QuoteSource(port="0", api=api, session="sess-1", lock_timeout_secs=0.5)
        with pytest.raises(ConnectionError):
            src.list_series()

    def test_fetch_backfill_lock_timeout_raises_connection_error(self) -> None:
        api = _ReqApi(_RaisingSocket())
        api.lock.acquire()  # 模擬 Pong 毒鎖:不可永久阻塞(修前 wrapper blocking acquire)
        src = TC4QuoteSource(port="0", api=api, session="sess-1", lock_timeout_secs=0.05)
        series = group_series(["TC.O.TWF.TX4.202607.C.44550"])[0]
        with pytest.raises(ConnectionError):
            src.fetch_backfill(series)

    def test_close_survives_unsub_failure(self) -> None:
        # round-2 P0:UNSUBQUOTE 失敗 → _req 內 _dispose 已清 self._api,
        # close() 收尾不可再 None.Disconnect() 炸 AttributeError(收工路徑必須乾淨)
        api = _ReqApi(_RaisingSocket())
        src = TC4QuoteSource(port="0", api=api, session="sess-1", lock_timeout_secs=0.5)
        src._subscribed = {SPOT_SYMBOL}
        src.close()  # 不得拋例外
        assert api.disconnected is True  # dispose best-effort 已關

    def test_request_after_dispose_raises_connection_error_not_assert(self) -> None:
        # round-2 P1 衍生:dispose 後殘存呼叫要收斂 ConnectionError,
        # 不可裸 assert 拋 AssertionError 逃出 engine 的 except ConnectionError 攔截網
        api = _ReqApi(_RaisingSocket())
        src = TC4QuoteSource(port="0", api=api, session="sess-1", lock_timeout_secs=0.5)
        with pytest.raises(ConnectionError):
            src._rt_request("SUBQUOTE", SPOT_SYMBOL)  # 第一次:失敗 + dispose
        with pytest.raises(ConnectionError):
            src._rt_request("SUBQUOTE", SPOT_SYMBOL)  # 第二次:已 dispose,仍是 ConnectionError

    def test_req_failure_disposes_api_for_lazy_reconnect(self) -> None:
        # REQ timeout 後 EFSM 壞狀態不可重用;若不棄連線,SUB 有 tick 流動時
        # _check_stale 永不觸發 → REQ 通道永久壞死(review F2)
        api = _ReqApi(_RaisingSocket())
        src = TC4QuoteSource(port="0", api=api, session="sess-1", lock_timeout_secs=0.5)
        with pytest.raises(ConnectionError):
            src._rt_request("SUBQUOTE", SPOT_SYMBOL)
        assert src._api is None, "失敗後未棄連線,下一次呼叫仍用壞 socket"


@requires_tcpy
class TestConnectInterruptible:
    """條 1 核心:app 死亡時 Connect 裸 recv 必須有 timeout,重連迴圈可中斷。

    兩條都會真的走 `_ensure_connected` → import TCPY wrapper,缺 wrapper 時
    `test_connect_dead_port...` 直接紅,而 `test_check_stale...` 更糟:重連執行緒
    死於 ModuleNotFoundError 也滿足 `not worker.is_alive()` → 假綠(2026-07-30 實測)。
    故整個 class 一起 skip。
    """

    def test_connect_dead_port_raises_connection_error_fast(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(tc4_mod, "_REQ_TIMEOUT_MS", 300)
        src = TC4QuoteSource(port=str(_free_port()))
        t0 = time.monotonic()
        with pytest.raises(ConnectionError):
            src._ensure_connected()
        assert time.monotonic() - t0 < 3.0, "無 RCVTIMEO:recv 阻塞不返回"

    def test_check_stale_reconnect_loop_stoppable_when_app_dead(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(tc4_mod, "_REQ_TIMEOUT_MS", 300)
        src = TC4QuoteSource(port=str(_free_port()))
        src._last_msg = time.monotonic() - 999.0  # 觸發 stale 判定
        worker = threading.Thread(target=src._check_stale, daemon=True)
        worker.start()
        time.sleep(0.5)  # 讓迴圈至少失敗一次進 backoff
        src._stop.set()
        worker.join(timeout=3.0)
        assert not worker.is_alive(), "重連迴圈不可中斷(阻塞在裸 recv)"


class _SelectiveFailApi(FakeApi):
    """REALTIME SUBQUOTE 對指定 symbol 回 Success != OK,其餘照 FakeApi。"""

    def __init__(self, fail: set[str]) -> None:
        super().__init__({})
        self._fail = fail

    def _handle(self, req: dict) -> bytes:
        param = req.get("Param", {})
        if (
            req.get("Request") == "SUBQUOTE"
            and param.get("SubDataType") == "REALTIME"
            and param.get("Symbol") in self._fail
        ):
            self.rt_requests.append(req)
            return b'{"Success": "FAIL", "ErrMsg": "sub reject"}\x00'
        return super()._handle(req)


class TestReconnectResubWarning:
    """P1-3(共用層的「至少」防線):重連重掛 SUBQUOTE 失敗品原本靜默丟出
    `_subscribed` 且零 log —— 失效樣態是「該檔從此零推播,log 乾乾淨淨」。
    這裡鎖 grep 判準 warning;掉訂品的實際復原由 engine 端 on_reconnect 對帳接手。
    """

    def test_resub_failure_logs_warning_and_drops_symbol(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = _SelectiveFailApi(fail={"TC.F.TWF.TXF.HOT"})
        src = TC4QuoteSource(port="0", api=api, session="sess-1")
        src._subscribed = {"TC.F.TWF.TXF.HOT", "TC.F.TWF.MXF.HOT"}
        src._last_msg = time.monotonic() - 999.0  # 觸發 stale 判定

        def _reinstall() -> None:
            # _check_stale 先 _dispose 再 _ensure_connected;unit 層不真連線,
            # 重灌同一顆 fake api(測的是重掛迴圈,不是連線建立)
            with src._api_lock:
                src._api = api
                src._session = "sess-2"

        monkeypatch.setattr(src, "_ensure_connected", _reinstall)
        fired: list[int] = []
        src.on_reconnect = lambda: fired.append(1)
        with caplog.at_level(logging.WARNING):
            src._check_stale()
        assert "TC.F.TWF.MXF.HOT" in src._subscribed  # 成功品照舊
        assert "TC.F.TWF.TXF.HOT" not in src._subscribed  # 現行語意:失敗品出集合
        assert "TC4 reconnect resubscribe TC.F.TWF.TXF.HOT failed" in caplog.text
        # T-1:engine 對帳鏈的樞紐 —— 部分重掛失敗仍算重連成功、仍必須通知
        # on_reconnect(這一下沒發生,FuturesEngine 的對帳整條不可達)
        assert fired == [1]
        assert src.reconnects == 1


# ---- REALTIME 零推播自癒(fix/tc4-realtime-refcount-kill)----
#
# root cause(repro.md):TC4 的訂閱 refcount 以 key = symbol|DataType|StartTime|EndTime 計,
# 上游 feed 卻以 **symbol** 為單位 —— 任一把 key 歸零就退訂整個 symbol,而 count 仍 > 0 的
# 其他 key 再送 SUBQUOTE 不會重掛上游 → 那些 key 永久零推播,且全鏈零錯誤訊號。

HEAL_A = "TC.S.TWS.2317"
HEAL_B = "TC.S.TWS.2330"


def _rt_pairs(api: FakeApi) -> list[tuple[str, str]]:
    return [(r["Request"], r["Param"]["Symbol"]) for r in api.rt_requests]


def _rt_keys(api: FakeApi) -> list[tuple[str, str, str]]:
    """(Request, StartTime, EndTime) —— TC4 refcount 的鍵就是後兩者(repro.md)。"""
    return [
        (r["Request"], r["Param"]["StartTime"], r["Param"]["EndTime"]) for r in api.rt_requests
    ]


def _push_raw(symbol: str) -> str:
    return "Q:" + json.dumps({"DataType": "REALTIME", "Quote": {"Symbol": symbol}})


#: 四把在跑的 base 窗(stock 日窗 / TXO 日窗 / TXO 夜窗 / corr 全天窗)。
#: 變體必須對**每一把**都產出互異的新鍵 —— 塌回同一把 key 的失效樣態是
#: 「自癒照跑、log 照印,但 TC4 refcount 沒歸零 → 上游永遠不重掛」(零錯誤訊號)。
_BASE_WINDOWS = {
    "stock-day": ("2026081800", "2026081806"),
    "txo-day": ("2026081800", "2026081806"),
    "txo-night": ("2026081806", "2026081822"),
    "corr-all-day": ("2026081800", "2026081823"),
}


class TestApplyVariant:
    """C-1:窗變體必須恆為新鍵(舊規則對全天窗 no-op、對夜盤窗 k=1/2/3 塌成同一把)。"""

    @staticmethod
    def _src() -> TC4QuoteSource:
        return TC4QuoteSource(port="0", api=FakeApi({}), session="sess-1")

    @pytest.mark.parametrize("base", list(_BASE_WINDOWS.values()), ids=list(_BASE_WINDOWS))
    def test_variants_are_pairwise_distinct(self, base: tuple[str, str]) -> None:
        src = self._src()
        seen = {base}
        for k in (1, 2, 3):
            src._window_variant[HEAL_A] = k
            window = src._apply_variant(HEAL_A, base)
            assert window not in seen, f"variant {k} 撞既有鍵:{window}"
            seen.add(window)

    def test_variant_zero_is_the_base_window(self) -> None:
        base = _BASE_WINDOWS["stock-day"]
        assert self._src()._apply_variant(HEAL_A, base) == base

    def test_day_window_extends_the_end_hour(self) -> None:
        src = self._src()
        base = _BASE_WINDOWS["stock-day"]
        got = []
        for k in (1, 2, 3):
            src._window_variant[HEAL_A] = k
            got.append(src._apply_variant(HEAL_A, base))
        assert got == [
            ("2026081800", "2026081807"),
            ("2026081800", "2026081808"),
            ("2026081800", "2026081809"),
        ]

    def test_night_window_spills_the_remainder_into_start(self) -> None:
        # 夜盤窗 06–22 只剩 1 小時的 end 餘量 → 餘量往 StartTime 推
        src = self._src()
        base = _BASE_WINDOWS["txo-night"]
        got = []
        for k in (1, 2, 3):
            src._window_variant[HEAL_A] = k
            got.append(src._apply_variant(HEAL_A, base))
        assert got == [
            ("2026081806", "2026081823"),
            ("2026081805", "2026081823"),
            ("2026081804", "2026081823"),
        ]

    def test_all_day_window_shifts_start_forward(self) -> None:
        # 全天窗 00–23 兩端都到底 → 只能把 StartTime 往後推(往前推是 no-op)
        src = self._src()
        base = _BASE_WINDOWS["corr-all-day"]
        got = []
        for k in (1, 2, 3):
            src._window_variant[HEAL_A] = k
            got.append(src._apply_variant(HEAL_A, base))
        assert got == [
            ("2026081801", "2026081823"),
            ("2026081802", "2026081823"),
            ("2026081803", "2026081823"),
        ]


class TestHealSessionSilence:
    """T1(R1):整條 session 靜默超過門檻 → 對每個 sub 發 UNSUBQUOTE + SUBQUOTE。"""

    @staticmethod
    def _src(api: FakeApi, **kw: Any) -> TC4QuoteSource:
        src = TC4QuoteSource(port="0", api=api, session="sess-1", **kw)
        src._subscribed = {HEAL_A, HEAL_B}
        src._sub_at = {HEAL_A: 0.0, HEAL_B: 0.0}
        return src

    def test_silent_session_resubscribes_every_symbol(self) -> None:
        api = FakeApi({})
        src = self._src(api, heal_silence_secs=30.0)
        src._heal_tick(100.0)
        assert _rt_pairs(api) == [
            ("UNSUBQUOTE", HEAL_A),
            ("SUBQUOTE", HEAL_A),
            ("UNSUBQUOTE", HEAL_B),
            ("SUBQUOTE", HEAL_B),
        ]

    def test_inactive_gate_skips_heal(self) -> None:
        api = FakeApi({})
        src = self._src(api, heal_silence_secs=30.0, heal_active=lambda: False)
        src._heal_tick(100.0)
        assert api.rt_requests == []

    def test_recent_push_skips_heal(self) -> None:
        api = FakeApi({})
        src = self._src(api, heal_silence_secs=30.0)
        src._last_push = {HEAL_B: 90.0}  # 90 秒那則推播 = 整條 session 還活著
        src._heal_tick(100.0)
        assert api.rt_requests == []

    def test_recent_resubscribe_skips_heal(self) -> None:
        # 剛重掛過(訂閱窗才建立)不算靜默 —— 否則每輪都重掛,churn 到 TC4 上游
        api = FakeApi({})
        src = self._src(api, heal_silence_secs=30.0)
        src._sub_at = {HEAL_A: 0.0, HEAL_B: 95.0}
        src._heal_tick(100.0)
        assert api.rt_requests == []


class TestHealSymbolSilence:
    """T2(R2):曾有推播、之後單獨靜默的 symbol 才重掛(其餘照流)。"""

    @staticmethod
    def _src(api: FakeApi, **kw: Any) -> TC4QuoteSource:
        src = TC4QuoteSource(port="0", api=api, session="sess-1", **kw)
        src._subscribed = {HEAL_A, HEAL_B}
        src._sub_at = {HEAL_A: 0.0, HEAL_B: 0.0}
        return src

    def test_only_the_silent_symbol_is_healed(self) -> None:
        api = FakeApi({})
        src = self._src(api, heal_symbol_silence_secs=60.0)
        src._last_push = {HEAL_A: 10.0, HEAL_B: 95.0}
        src._heal_tick(100.0)
        assert _rt_pairs(api) == [("UNSUBQUOTE", HEAL_A), ("SUBQUOTE", HEAL_A)]

    def test_never_pushed_symbol_is_healed_after_the_grace_window(self) -> None:
        # C-6:**部分死亡**(訂閱起就從未推播過的腿)是 08-18 個股面的實際形狀 ——
        # 舊母體只收「曾有推播」,那些腿 R1(其他 symbol 還在流)與 R2 都收不到,
        # 永遠沒人救。訂閱後超過 T2 仍零推播 = 與「靜默」同一件事。
        api = FakeApi({})
        src = self._src(api, heal_symbol_silence_secs=60.0)
        src._sub_at = {HEAL_A: 0.0, HEAL_B: 95.0}
        src._last_push = {HEAL_B: 95.0}
        src._heal_tick(100.0)
        assert _rt_pairs(api) == [("UNSUBQUOTE", HEAL_A), ("SUBQUOTE", HEAL_A)]

    def test_never_pushed_symbol_within_the_grace_window_is_left_alone(self) -> None:
        # 剛訂閱就判死 = 每輪都重掛;TXO 深價外那類本就沒成交的 symbol 由
        # R2=None 豁免(app._default_source),不是靠這條窄母體擋
        api = FakeApi({})
        src = self._src(api, heal_symbol_silence_secs=60.0)
        src._sub_at = {HEAL_A: 50.0, HEAL_B: 50.0}
        src._heal_tick(100.0)
        assert api.rt_requests == []

    def test_push_resets_attempts(self) -> None:
        api = FakeApi({})
        src = self._src(api, heal_symbol_silence_secs=60.0)
        src._last_push = {HEAL_A: 10.0, HEAL_B: 95.0}
        src._heal_tick(100.0)
        assert src._heal_attempts[HEAL_A] == 1
        src.handle_raw(_push_raw(HEAL_A))
        assert HEAL_A not in src._heal_attempts  # 推播回來 = 這把 key 活了
        # T-8:退避也要一起清 —— 只清 attempts 的話,恢復後又靜默的 symbol 要等
        # 上一輪算出的 `_heal_next` 到期(最壞 300s)才救得回
        assert HEAL_A not in src._heal_next


class TestHealWindowVariantEscalation:
    """T3:同一把 key 連續兩次沒救回 → 換窗(TXF.HOT 由 TXO+futures 雙持,
    自己 UNSUB→SUB 到不了 count 0,TC4 就不會重掛上游 feed)。"""

    @staticmethod
    def _src(api: FakeApi) -> TC4QuoteSource:
        src = TC4QuoteSource(port="0", api=api, session="sess-1", heal_symbol_silence_secs=60.0)
        src._subscribed = {HEAL_A}
        src._sub_at = {HEAL_A: 0.0}
        src._last_push = {HEAL_A: 0.0}
        return src

    @staticmethod
    def _end_times(api: FakeApi) -> list[str]:
        return [r["Param"]["EndTime"] for r in api.rt_requests if r["Request"] == "SUBQUOTE"]

    def test_third_attempt_switches_window(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("copycat.live.tc4.session_key", lambda: ("20260818", "day"))
        api = FakeApi({})
        src = self._src(api)
        for now in (100.0, 300.0, 700.0):  # 退避 60 / 120 後仍靜默
            src._heal_tick(now)
        assert self._end_times(api) == ["2026081806", "2026081806", "2026081807"]
        assert src._window_variant[HEAL_A] == 1

    def test_fourth_attempt_switches_again(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("copycat.live.tc4.session_key", lambda: ("20260818", "day"))
        api = FakeApi({})
        src = self._src(api)
        for now in (100.0, 300.0, 700.0, 1500.0):
            src._heal_tick(now)
        assert self._end_times(api)[-1] == "2026081808"

    def test_variant_survives_a_push(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 推播回來只清 attempts:variant 指的那把 key 正是活著的那把,退回原窗等於自殺
        monkeypatch.setattr("copycat.live.tc4.session_key", lambda: ("20260818", "day"))
        api = FakeApi({})
        src = self._src(api)
        for now in (100.0, 300.0, 700.0):
            src._heal_tick(now)
        src.handle_raw(_push_raw(HEAL_A))
        src._resub(HEAL_A)
        assert self._end_times(api)[-1] == "2026081807"


class TestHealResilience:
    """T4:REQ 例外只退避、不得殺 watchdog 執行緒。"""

    def test_request_failure_is_swallowed_and_backs_off(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        api = _ReqApi(_RaisingSocket())
        src = TC4QuoteSource(
            port="0", api=api, session="sess-1", lock_timeout_secs=0.5, heal_silence_secs=30.0
        )
        src._subscribed = {HEAL_A}
        src._sub_at = {HEAL_A: 0.0}
        with caplog.at_level(logging.WARNING):
            src._heal_tick(100.0)  # 不得拋
        assert "TC4 REALTIME 零推播自癒" in caplog.text
        assert src._heal_attempts[HEAL_A] == 1
        assert src._heal_next[HEAL_A] == 130.0  # T·2^0 退避

    def test_backoff_blocks_the_next_tick(self) -> None:
        api = FakeApi({})
        src = TC4QuoteSource(port="0", api=api, session="sess-1", heal_silence_secs=30.0)
        src._subscribed = {HEAL_A}
        src._sub_at = {HEAL_A: 0.0}
        src._heal_tick(100.0)
        src._sub_at[HEAL_A] = 0.0  # 模擬重掛後仍零推播(退避期內不得再打)
        src._heal_tick(120.0)
        assert _rt_pairs(api) == [("UNSUBQUOTE", HEAL_A), ("SUBQUOTE", HEAL_A)]

    def test_heal_thread_survives_failing_requests(self) -> None:
        api = _ReqApi(_RaisingSocket())
        src = TC4QuoteSource(
            port="0",
            api=api,
            session="sess-1",
            lock_timeout_secs=0.5,
            heal_silence_secs=0.01,
            heal_poll_secs=0.01,
        )
        src._subscribed = {HEAL_A}
        src._sub_at = {HEAL_A: 0.0}
        try:
            src._start_healer()
            deadline = time.monotonic() + 3.0
            while src._heal_attempts.get(HEAL_A, 0) < 2 and time.monotonic() < deadline:
                time.sleep(0.02)
            assert src._heal_attempts.get(HEAL_A, 0) >= 2, "watchdog 未持續重試"
            healer = src._healer
            assert healer is not None and healer.is_alive(), "REQ 例外不得殺 watchdog"
        finally:
            src._stop.set()
            if src._healer is not None:
                src._healer.join(timeout=3.0)


class TestHealVariantReleasesOldKey:
    """C-7:換窗前必須先放掉舊窗那把 key。

    舊實作是「bump 之後才 UNSUB」→ UNSUBQUOTE 送的是**新窗**、舊窗 key 的 count
    永遠停在 >0。TC4 的上游 feed 以 symbol 為單位、任一 key 歸零才重掛,自己留著
    一把不歸零的舊 key 等於把 symbol 鎖在死狀態(repro.md root cause)。
    """

    def test_bump_shot_unsubscribes_old_window_first(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("copycat.live.tc4.session_key", lambda: ("20260818", "day"))
        api = FakeApi({})
        src = TC4QuoteSource(port="0", api=api, session="sess-1", heal_symbol_silence_secs=60.0)
        src._subscribed = {HEAL_A}
        src._sub_at = {HEAL_A: 0.0}
        src._last_push = {HEAL_A: 0.0}
        for now in (100.0, 300.0):  # 前兩發同窗(退避 60 / 120)
            src._heal_tick(now)
        api.rt_requests.clear()
        src._heal_tick(700.0)  # 第三發 = 換窗那一發
        assert _rt_keys(api) == [
            ("UNSUBQUOTE", "2026081800", "2026081806"),  # 先放掉舊窗 key
            ("UNSUBQUOTE", "2026081800", "2026081807"),  # 再對新窗冪等 UNSUB→SUB
            ("SUBQUOTE", "2026081800", "2026081807"),
        ]


class TestHealConcurrentUnsubscribe:
    """C-3:watchdog 取完快照後 engine 才退訂 —— 這一發不得把 symbol 掛回去。

    幽靈訂閱(沒有任何持有者的 REALTIME 訂閱)不會有錯誤訊號:推播照收、
    engine 沒有對應狀態機、TC4 那頭的 refcount 也回不去。
    """

    def test_heal_skips_a_symbol_the_engine_already_unsubscribed(self) -> None:
        api = FakeApi({})
        src = TC4QuoteSource(port="0", api=api, session="sess-1", heal_silence_secs=30.0)
        src._subscribed = set()
        src._heal(HEAL_A, 100.0, 30.0)
        assert api.rt_requests == []
        assert HEAL_A not in src._subscribed


class TestHealLoopResilience:
    """C-2:watchdog 迴圈的 catch-all —— 非 IO 例外(邏輯 bug)不得殺掉自癒。

    `_heal` 只吞 TC4 通訊類例外;`KeyError` / `RuntimeError` 這種逃出來就是
    thread 靜靜死掉,而它守的正是「零推播且零錯誤訊號」那條路。
    """

    def test_unexpected_exception_keeps_the_loop_running(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        src = TC4QuoteSource(
            port="0",
            api=FakeApi({}),
            session="sess-1",
            heal_silence_secs=30.0,
            heal_poll_secs=0.01,
        )
        calls: list[float] = []

        def _boom(now: float) -> None:
            calls.append(now)
            if len(calls) >= 3:
                src._stop.set()
            raise RuntimeError("watchdog 內部 bug")

        monkeypatch.setattr(src, "_heal_tick", _boom)
        thread = threading.Thread(target=src._heal_loop)
        with caplog.at_level(logging.ERROR):
            thread.start()
            thread.join(timeout=3.0)
        assert not thread.is_alive(), "watchdog 迴圈未收斂"
        assert len(calls) >= 3, "例外之後不得停止巡檢"
        assert "watchdog" in caplog.text


class TestHealRuleInteraction:
    """T-5:R1 / R2 同時開啟時的分工(TXO 之外的三條 session 都是這個組態)。"""

    @staticmethod
    def _src(api: FakeApi) -> TC4QuoteSource:
        src = TC4QuoteSource(
            port="0",
            api=api,
            session="sess-1",
            heal_silence_secs=30.0,
            heal_symbol_silence_secs=60.0,
        )
        src._subscribed = {HEAL_A, HEAL_B}
        src._sub_at = {HEAL_A: 0.0, HEAL_B: 0.0}
        return src

    def test_r1_batch_hit_short_circuits_r2_in_the_same_tick(self) -> None:
        api = FakeApi({})
        src = self._src(api)
        src._last_push = {HEAL_A: 0.0, HEAL_B: 0.0}
        src._heal_tick(100.0)
        assert _rt_pairs(api) == [
            ("UNSUBQUOTE", HEAL_A),
            ("SUBQUOTE", HEAL_A),
            ("UNSUBQUOTE", HEAL_B),
            ("SUBQUOTE", HEAL_B),
        ]
        # 同一輪不得再被 R2 收一次:attempts 多跳一格 = 退避與換窗階梯整條錯位
        assert src._heal_attempts == {HEAL_A: 1, HEAL_B: 1}

    def test_r2_still_fires_when_r1_does_not(self) -> None:
        api = FakeApi({})
        src = self._src(api)
        src._last_push = {HEAL_A: 0.0, HEAL_B: 95.0}  # B 還在流 → R1 不成立
        src._heal_tick(100.0)
        assert _rt_pairs(api) == [("UNSUBQUOTE", HEAL_A), ("SUBQUOTE", HEAL_A)]


class TestHealBookkeepingLifecycle:
    """C-8:五本帳的生命週期 —— 退訂即清,不得跨訂閱週期帶著舊 variant。"""

    def test_unsub_clears_every_heal_book(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("copycat.live.tc4.session_key", lambda: ("20260818", "day"))
        api = FakeApi({})
        src = TC4QuoteSource(port="0", api=api, session="sess-1", heal_symbol_silence_secs=60.0)
        src._subscribed = {HEAL_A}
        src._sub_at = {HEAL_A: 0.0}
        src._last_push = {HEAL_A: 0.0}
        src._heal_attempts[HEAL_A] = 2
        src._heal_next[HEAL_A] = 999.0
        src._window_variant[HEAL_A] = 2
        src._unsub(HEAL_A)
        for book in (
            src._last_push,
            src._sub_at,
            src._heal_attempts,
            src._heal_next,
            src._window_variant,
        ):
            assert HEAL_A not in book
        # 下一輪訂閱回到 base 窗(帶著舊 variant 訂的是一把沒人知道的窗)
        api.rt_requests.clear()
        src._resub(HEAL_A)
        assert _rt_keys(api)[-1] == ("SUBQUOTE", "2026081800", "2026081806")


class TestHealRecoveryCycle:
    """T-7:實驗 G 的形狀端到端 —— 流動 → 靜默 → 重掛 → 復活後不再 churn。"""

    def test_push_silence_heal_recovery_cycle(self) -> None:
        api = FakeApi({})
        src = TC4QuoteSource(port="0", api=api, session="sess-1", heal_symbol_silence_secs=60.0)
        src._subscribed = {HEAL_A}
        base = time.monotonic()
        src._sub_at = {HEAL_A: base}
        src._last_push = {HEAL_A: base}

        src._heal_tick(base + 10.0)  # 還在流動
        assert api.rt_requests == []

        src._heal_tick(base + 100.0)  # 靜默 100s > 60s
        assert _rt_pairs(api) == [("UNSUBQUOTE", HEAL_A), ("SUBQUOTE", HEAL_A)]
        assert src._heal_attempts[HEAL_A] == 1

        src.handle_raw(_push_raw(HEAL_A))  # 上游回來了
        assert HEAL_A not in src._heal_attempts
        assert HEAL_A not in src._heal_next

        api.rt_requests.clear()
        src._heal_tick(time.monotonic() + 10.0)
        assert api.rt_requests == [], "復活後不得繼續 churn"


class TestHealDisabledByDefault:
    """基底預設全關:各條 session 的門檻由子類建構子帶,基底不主動 churn。"""

    def test_defaults_are_off(self) -> None:
        api = FakeApi({})
        src = TC4QuoteSource(port="0", api=api, session="sess-1")
        assert src._heal_silence is None
        assert src._heal_symbol_silence is None
        src._subscribed = {HEAL_A}
        src._sub_at = {HEAL_A: 0.0}
        src._last_push = {HEAL_A: 0.0}
        src._heal_tick(10_000.0)
        assert api.rt_requests == []

    def test_healer_thread_not_started_when_disabled(self) -> None:
        src = TC4QuoteSource(port="0", api=FakeApi({}), session="sess-1")
        src._start_healer()
        assert src._healer is None


class TestSpotSymbol:
    def test_spot_symbol_uses_txf_product_code(self) -> None:
        """item 2(2026-07-20 盤中驗證):TC4 symbol 樹的台指期產品碼是 TXF,FITX 不存在。

        FITX 只出現在 Quote.Security 欄位;SUBQUOTE 對不存在 symbol 照回 OK(平台不驗證)
        → 訂了永遠沒推播,spot 恆 None。證據:驗證報告 item 2 四步診斷鏈。
        """
        assert SPOT_SYMBOL == "TC.F.TWF.TXF.HOT"
# ---- R8 TC4 連線/訂閱深水區 ----


class _FakeCtx:
    """QuoteAPI.context 替身:只需要吃得下 setsockopt。"""

    def __init__(self) -> None:
        self.opts: list[tuple[int, int]] = []

    def setsockopt(self, opt: int, value: int) -> None:
        self.opts.append((opt, value))


class _SlowQuoteAPI:
    """Connect 帶延遲的 QuoteAPI 替身 —— 把 check-then-act 的競賽窗放大到可觀測。"""

    created: list[Any] = []

    def __init__(self, appid: str, skey: str, delay: float = 0.2) -> None:
        self.context = _FakeCtx()
        self.socket = _JsonSocket(lambda _req: b'{"Success": "OK"}\x00')
        self.lock = threading.Lock()
        self.disconnected = False
        self._delay = delay
        _SlowQuoteAPI.created.append(self)

    def Connect(self, port: str) -> dict:  # noqa: N802 - wrapper 介面
        time.sleep(self._delay)
        return {"Success": "OK", "SessionKey": "sess-race", "SubPort": "54322"}

    def Disconnect(self) -> None:  # noqa: N802 - wrapper 介面
        self.disconnected = True


def _install_slow_quote_api(monkeypatch: pytest.MonkeyPatch) -> type[_SlowQuoteAPI]:
    """把 `tcoreapi_mq.QuoteAPI` 換成延遲替身。

    `_ensure_connected` 是 function 內 import,先塞 `sys.modules` 即可攔截 —— 不需要
    真的有 TCPY wrapper(所以本組測試不掛 `requires_tcpy`)。
    """
    import sys
    import types

    _SlowQuoteAPI.created = []
    module = types.ModuleType("tcoreapi_mq")
    module.QuoteAPI = _SlowQuoteAPI  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tcoreapi_mq", module)
    return _SlowQuoteAPI


def _source_classes() -> dict[str, Any]:
    """四個吃同一份 `_ensure_connected` 的 source(blast radius = 這四條 session)。"""
    from copycat.live.corr_source import CorrQuoteSource
    from copycat.live.futures_source import FuturesQuoteSource
    from copycat.live.stock_source import StockQuoteSource

    return {
        "txo": TC4QuoteSource,
        "stock": StockQuoteSource,
        "futures": FuturesQuoteSource,
        "corr": CorrQuoteSource,
    }


class TestEnsureConnectedAtomic:
    """N259:`_ensure_connected` 的 check(指標為 None)與建立/發布不是原子的 ——
    `_check_stale` 重連與任何 REQ 生產者同時進來時會建出**兩個** QuoteAPI,落敗的
    那一個永遠不會被 `Disconnect()`(KeepAlive 執行緒續跑 → process 不退,§0a),
    而兩邊都「連線成功」,零錯誤訊號。
    """

    @pytest.mark.parametrize("name", list(_source_classes()))
    def test_concurrent_ensure_connected_creates_one_api(
        self, name: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api_cls = _install_slow_quote_api(monkeypatch)
        src = _source_classes()[name](port="0")
        errors: list[BaseException] = []

        def _worker() -> None:
            try:
                src._ensure_connected()
            except BaseException as exc:  # noqa: BLE001 - 測試觀測點
                errors.append(exc)

        threads = [threading.Thread(target=_worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)
        assert errors == []
        assert len(api_cls.created) == 1, (
            "重連 race 建出兩條 TC4 連線(落敗者永不 Disconnect)"
        )
        assert src._api is api_cls.created[0]

    def test_stopped_source_refuses_to_reconnect(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """收工後(`close()` 已 set `_stop`)在途的 executor 工作項不得重建連線 ——
        重建 = 新的 KeepAlive 執行緒,process 不退(futures `_retry_subscribe` 的縮窗
        註解點名的殘餘 race)。"""
        api_cls = _install_slow_quote_api(monkeypatch)
        src = TC4QuoteSource(port="0")
        src._stop.set()
        with pytest.raises(ConnectionError):
            src._ensure_connected()
        assert api_cls.created == []


class TestSpotWindowOffset:
    """N050:TXO session 與 futures session 雙持 `TXF.HOT` **同一把** refcount key ——
    單 session 的 UNSUB→SUB 永遠到不了 SumSubCount 0,上游不會 `ReqSubQuote`,
    要靠第 3 次自癒的 window variant 才救得回(多一輪 backoff)。
    """

    @staticmethod
    def _series() -> Any:
        from copycat.live.models import OptionContract, SeriesInfo

        return SeriesInfo(
            series_id="TXO.202608",
            name="TXO 202608",
            expiry="202608",
            contracts=(
                OptionContract(
                    symbol="TC.O.TWF.TXO.202608.C.44550",
                    cp="C",
                    strike_millipts=44_550_000,
                ),
            ),
        )

    def test_txo_spot_window_differs_from_the_session_window(self) -> None:
        api = FakeApi({})
        src = TC4QuoteSource(port="0", api=api, session="sess-1")
        src._start_listener = lambda: None  # type: ignore[method-assign]
        src.subscribe(self._series(), lambda _t: None)
        windows = {
            r["Param"]["Symbol"]: (r["Param"]["StartTime"], r["Param"]["EndTime"])
            for r in api.rt_requests
        }
        assert windows[SPOT_SYMBOL] != windows["TC.O.TWF.TXO.202608.C.44550"], (
            "TXO 的 TXF.HOT 訂閱窗與盤別窗相同 = 與 futures session 同一把 key"
        )

    def test_spot_offset_survives_the_heal_variant_ladder(self) -> None:
        """自癒換窗時位移必須疊在 variant 之上,四把窗(variant 0/1/2/3)兩兩互異 ——
        塌回同一把的失效樣態是「自癒照跑但上游永不重掛」。"""
        api = FakeApi({})
        src = TC4QuoteSource(port="0", api=api, session="sess-1")
        src._start_listener = lambda: None  # type: ignore[method-assign]
        src.subscribe(self._series(), lambda _t: None)
        seen = set()
        for k in (0, 1, 2, 3):
            src._window_variant[SPOT_SYMBOL] = k
            api.rt_requests.clear()
            src._rt_request("SUBQUOTE", SPOT_SYMBOL)
            param = api.rt_requests[-1]["Param"]
            key = (param["StartTime"], param["EndTime"])
            assert key not in seen, f"variant {k} 撞既有鍵:{key}"
            seen.add(key)

    def test_futures_session_keeps_the_base_window_for_the_same_symbol(self) -> None:
        """位移只加在 TXO 那一邊 —— futures session 的 `TXF.HOT` 窗必須逐字不變,
        否則兩邊一起位移還是同一把 key(而期貨面的既有訂閱行為被改掉)。"""
        from copycat.live.futures_source import FuturesQuoteSource

        api = FakeApi({})
        fut = FuturesQuoteSource(port="0", api=api, session="sess-1")
        fut.subscribe_symbol("TXF")
        last = api.rt_requests[-1]["Param"]
        base = TC4QuoteSource(port="0", api=FakeApi({}), session="sess-1")
        assert (last["StartTime"], last["EndTime"]) == base._rt_window(SPOT_SYMBOL)


class TestHealSymbolGate:
    """N051:R2「從未推播」母體對**自身休市段**的腿一樣每 300s 一發 UNSUB+SUB。
    海外 / 台期交國外指數腿的時段各不相同,session 級的 `heal_active` 表達不了。
    """

    def test_symbol_gate_suppresses_heal_for_a_closed_leg(self) -> None:
        api = FakeApi({})
        closed = {HEAL_B}
        src = TC4QuoteSource(
            port="0",
            api=api,
            session="sess-1",
            heal_symbol_silence_secs=60.0,
            heal_symbol_active=lambda sym: sym not in closed,
        )
        src._subscribed = {HEAL_A, HEAL_B}
        src._sub_at = {HEAL_A: 0.0, HEAL_B: 0.0}
        src._last_push = {HEAL_A: 0.0, HEAL_B: 0.0}
        src._heal_tick(1000.0)
        assert _rt_pairs(api) == [("UNSUBQUOTE", HEAL_A), ("SUBQUOTE", HEAL_A)]

    def test_r1_population_excludes_gated_symbols(self) -> None:
        """R1(整條 session 靜默)的母體同樣要扣掉閘掉的腿:留在母體裡的話,
        休市腿的靜默會把還在流動的腿一起拖進「全場靜默」的整批重掛。"""
        api = FakeApi({})
        src = TC4QuoteSource(
            port="0",
            api=api,
            session="sess-1",
            heal_silence_secs=30.0,
            heal_symbol_active=lambda sym: sym != HEAL_B,
        )
        src._subscribed = {HEAL_A, HEAL_B}
        src._sub_at = {HEAL_A: 990.0, HEAL_B: 0.0}
        src._last_push = {HEAL_A: 990.0, HEAL_B: 0.0}
        src._heal_tick(1000.0)
        assert api.rt_requests == [], "活著的腿 10s 前才推過,不該因休市腿而整批重掛"

    def test_default_gate_keeps_every_symbol_active(self) -> None:
        api = FakeApi({})
        src = TC4QuoteSource(
            port="0", api=api, session="sess-1", heal_symbol_silence_secs=60.0
        )
        src._subscribed = {HEAL_A}
        src._sub_at = {HEAL_A: 0.0}
        src._last_push = {HEAL_A: 0.0}
        src._heal_tick(1000.0)
        assert _rt_pairs(api) == [("UNSUBQUOTE", HEAL_A), ("SUBQUOTE", HEAL_A)]


class TestFetchSymbolTicksStubSignature:
    """N092:ready-check「首頁非空即 break」被凍結 stub 騙 —— rows 非空但一筆都解不出來
    時,呼叫端只看得到空 list,與「這檔今天真沒成交」無從分辨且全鏈零 log。
    """

    def test_rows_all_dropped_logs_the_stub_signature(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        api = FakeApi({"S": [[{"QryIndex": "1", "FilledTime": "bad"}]]})
        src = TC4QuoteSource(port="0", api=api, session="sess-1")
        with caplog.at_level(logging.WARNING):
            ticks = src._fetch_symbol_ticks("S", "2026081800", "2026081806")
        assert ticks == []
        assert "疑似凍結 stub" in caplog.text


class TestSpotOffsetOutsideTheVariantLadder:
    """review SP2 / ST7:offset 疊在同一條 variant 階梯上(`k = variant + offset`)時,
    futures 自癒爬到 variant 1 的窗會**等於** TXO 的 offset 窗 —— 雙持同一把 key 的
    原病復發,而且是在「其中一邊正在自癒」這個最需要它不復發的時刻。
    offset 必須整段落在 variant 階梯之外。
    """

    @staticmethod
    def _windows(base: tuple[str, str], offset: int) -> list[tuple[str, str]]:
        src = TC4QuoteSource(port="0", api=FakeApi({}), session="sess-1")
        sym = "TC.F.TWF.TXF.HOT"
        if offset:
            src._window_offset[sym] = offset
        out = []
        for k in (0, 1, 2, 3):
            src._window_variant[sym] = k
            out.append(src._apply_variant(sym, base))
        return out

    @pytest.mark.parametrize("base", list(_BASE_WINDOWS.values()), ids=list(_BASE_WINDOWS))
    def test_futures_and_txo_ladders_never_collide(self, base: tuple[str, str]) -> None:
        futures = self._windows(base, 0)  # 期貨側:無 offset,自癒 variant 0..3
        txo = self._windows(base, tc4_mod.SPOT_WINDOW_OFFSET)  # TXO 側:offset + variant 0..3
        assert len(set(futures) | set(txo)) == 8, f"兩條階梯撞窗:{sorted(set(futures) & set(txo))}"

    @pytest.mark.parametrize("base", list(_BASE_WINDOWS.values()), ids=list(_BASE_WINDOWS))
    def test_offset_ladder_windows_stay_well_formed(self, base: tuple[str, str]) -> None:
        """ST7:總位移最大到 `offset + 3`,窗字串仍必須 start <= end 且小時在 00–23。"""
        for start, end in self._windows(base, tc4_mod.SPOT_WINDOW_OFFSET):
            assert len(start) == 10 and len(end) == 10
            assert 0 <= int(start[8:10]) <= 23
            assert 0 <= int(end[8:10]) <= 23
            assert start <= end, f"窗顛倒:{start} > {end}"

    def test_offset_clears_the_variant_cycle(self) -> None:
        """結構性判準(不靠列舉):offset 必須嚴格大於 variant 階梯的最大值。"""
        assert tc4_mod.SPOT_WINDOW_OFFSET > tc4_mod._HEAL_VARIANT_CYCLE


class TestEnsureConnectedShutdownRace:
    """review ST2:`_ensure_connected` 持 `_api_lock` 跨 `Connect()`(最壞 10 s),
    而 `close()` 開頭就要拿同一把鎖 —— 關機最壞多等一整個 10 s,正好把 run.ps1 的
    graceful 窗吃掉。在途那一發至少不得**發布**一條沒人會關的連線。
    """

    def test_connect_finishing_after_stop_is_disposed_not_published(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api_cls = _install_slow_quote_api(monkeypatch)
        src = TC4QuoteSource(port="0")
        errors: list[BaseException] = []

        def _worker() -> None:
            try:
                src._ensure_connected()
            except BaseException as exc:  # noqa: BLE001 - 測試觀測點
                errors.append(exc)

        t = threading.Thread(target=_worker)
        t.start()
        time.sleep(0.05)  # 讓它進到 Connect()(替身睡 0.2 s)
        src._stop.set()  # close() 的第一步
        t.join(timeout=5.0)
        assert len(api_cls.created) == 1
        assert api_cls.created[0].disconnected is True, "在途連線建成後沒被收掉(KeepAlive 洩漏)"
        assert src._api is None, "收工中仍把連線發布出去"
        assert errors and isinstance(errors[0], ConnectionError)


class TestCloseLogout:
    """fix/tc4-logout:收工要對 TC4 送 LOGOUT,不能只退訂 + 關 socket。

    2026-08-25 17:15:29 Ctrl+C 實證:708 筆 UNSUBQUOTE 貼秒,但五個 session 的
    `RemoveLoginInfo` 全在 17:16:31 由 `ExecuteCheckPingTime` reap —— wrapper 的
    `Disconnect()` 只關 KeepAlive + socket,送 LOGOUT 的是 `Logout()`,從沒被呼叫。
    """

    def test_close_sends_logout_for_the_live_session_after_unsub(self) -> None:
        api = FakeApi({})
        src = TC4QuoteSource(port="0", api=api, session="sess-1", lock_timeout_secs=0.5)
        src._subscribed = {SPOT_SYMBOL}
        src.close()
        kinds = [r.get("Request") for r in api.requests]
        assert "LOGOUT" in kinds, f"收工沒送 LOGOUT:{kinds}"
        assert [r for r in api.requests if r.get("Request") == "LOGOUT"] == [
            {"Request": "LOGOUT", "SessionKey": "sess-1"}
        ]
        # 退訂要在票還有效時做:UNSUB 全部在 LOGOUT 之前;LOGOUT 要在 socket 關掉之前(review SP5)
        assert max(i for i, k in enumerate(kinds) if k == "UNSUBQUOTE") < kinds.index("LOGOUT")
        assert kinds.index("LOGOUT") < kinds.index("<Disconnect>")
        assert api.disconnected is True
        # LOGOUT 的 recv 上界獨立縮短(review SP3):五條 session 串行也撞不破 run.ps1 15 s
        assert api.socket.sockopts == [(zmq.RCVTIMEO, tc4_mod._LOGOUT_TIMEOUT_MS)]
        assert tc4_mod._LOGOUT_TIMEOUT_MS * 5 < 15_000

    def test_close_without_live_connection_sends_nothing(self) -> None:
        # dispose 後(_api None)收工:不可為了 LOGOUT 重建連線
        api = FakeApi({})
        src = TC4QuoteSource(port="0", api=api, session="sess-1", lock_timeout_secs=0.5)
        src._dispose(api)
        api.requests.clear()
        src.close()
        assert api.requests == []

    def test_logout_rejected_by_tc4_still_disconnects(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        class _Rejects(FakeApi):
            def _handle(self, req: dict) -> bytes:
                if req.get("Request") == "LOGOUT":
                    self.requests.append(req)
                    return json.dumps({"Reply": "LOGOUT", "Success": "FAIL"}).encode() + b"\x00"
                return super()._handle(req)

        api = _Rejects({})
        src = TC4QuoteSource(port="0", api=api, session="sess-1", lock_timeout_secs=0.5)
        with caplog.at_level("WARNING"):
            src.close()
        assert any("TC4 quote LOGOUT 未被接受" in r.message for r in caplog.records)
        assert api.disconnected is True

    def test_logout_send_failure_disconnects_exactly_once(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # `_req` 失敗路徑自己 _dispose(Disconnect);close() 末段不得再 Disconnect 一次(review SP1)
        class _Raises(FakeApi):
            def _handle(self, req: dict) -> bytes:
                if req.get("Request") == "LOGOUT":
                    raise zmq.ZMQError()
                return super()._handle(req)

        api = _Raises({})
        src = TC4QuoteSource(port="0", api=api, session="sess-1", lock_timeout_secs=0.5)
        with caplog.at_level("WARNING"):
            src.close()
        assert any("TC4 quote LOGOUT 失敗" in r.message for r in caplog.records)
        assert [r["Request"] for r in api.requests].count("<Disconnect>") == 1
        assert src._api is None

    def test_close_with_api_but_no_session_skips_logout_and_still_disconnects(self) -> None:
        # 「仍在線」判準維持 `_api is not None`(review SP4):只注入 api 的建構路徑
        # 不可因為缺 session 就漏掉 Disconnect(KeepAlive 洩漏)
        api = FakeApi({})
        src = TC4QuoteSource(port="0", api=api, session=None, lock_timeout_secs=0.5)
        src.close()
        assert "LOGOUT" not in [r["Request"] for r in api.requests]


class TestCloseTiming:
    """A1(review #105 §2.6 S1):`close()` 要自己交代時間花在哪 —— 等 `_api_lock`(在途
    `Connect()`)還是逐檔 UNSUBQUOTE。lifespan 的彙總只看得到「這條 session 花了 12 s」,
    分不出是鎖還是 REQ;而處置不同(前者等它、後者 TC4 半死)。"""

    def test_close_logs_lock_wait_and_unsub_count(self, caplog: pytest.LogCaptureFixture) -> None:
        api = FakeApi({})
        src = TC4QuoteSource(port="0", api=api, session="sess-1")
        src._subscribed = {SPOT_SYMBOL, "TC.O.TWF.TXO.202608.C.44550"}
        with caplog.at_level(logging.INFO):
            src.close()
        # 兩行:進場(等鎖 + 檔數)與收尾(n/m + 秒數)—— 卡在 REQ 上被硬殺時只剩前一行
        assert "等 api 鎖" in caplog.text and "開始 UNSUBQUOTE 2 檔" in caplog.text
        assert "UNSUBQUOTE 2/2" in caplog.text
        assert api.disconnected is True
