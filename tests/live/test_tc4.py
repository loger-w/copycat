from __future__ import annotations

import json
import threading
import time
from typing import Any

import pytest
import zmq

import copycat.live.tc4 as tc4_mod
from copycat.live.tc4 import SPOT_SYMBOL, TC4QuoteSource, build_rt_request, group_series


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
        self.rt_requests: list[dict] = []
        self.disconnected = False

    def _handle(self, req: dict) -> bytes:
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


class TestConnectInterruptible:
    """條 1 核心:app 死亡時 Connect 裸 recv 必須有 timeout,重連迴圈可中斷。"""

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


class TestSpotSymbol:
    def test_spot_symbol_uses_txf_product_code(self) -> None:
        """item 2(2026-07-20 盤中驗證):TC4 symbol 樹的台指期產品碼是 TXF,FITX 不存在。

        FITX 只出現在 Quote.Security 欄位;SUBQUOTE 對不存在 symbol 照回 OK(平台不驗證)
        → 訂了永遠沒推播,spot 恆 None。證據:驗證報告 item 2 四步診斷鏈。
        """
        assert SPOT_SYMBOL == "TC.F.TWF.TXF.HOT"
