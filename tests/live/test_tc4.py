from __future__ import annotations

from typing import Any

from copycat.live.tc4 import SPOT_SYMBOL, TC4QuoteSource, build_rt_request, group_series

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
        obj = build_rt_request("SUBQUOTE", "sess-1", "TC.F.TWF.TXF.HOT", "20260718")
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


class FakeApi:
    """最小 QuoteAPI 替身:GetHistory 分頁 + 呼叫記錄。"""

    def __init__(self, pages: dict[str, list[list[dict]]]) -> None:
        self.pages = pages
        self.sub_history_calls: list[str] = []
        self.disconnected = False

    def SubHistory(self, session: str, sym: str, dtype: str, start: str, end: str) -> None:  # noqa: N802
        self.sub_history_calls.append(sym)

    def GetHistory(  # noqa: N802
        self, session: str, sym: str, dtype: str, start: str, end: str, qry_index: str
    ) -> dict[str, Any]:
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

        class _Stuck:
            def GetHistory(self, *args: Any) -> dict[str, Any]:  # noqa: N802
                return {"HisData": [row]}

        src = TC4QuoteSource(port="0", api=_Stuck(), session="sess-1", poll_wait_secs=0.0)
        ticks = src._fetch_symbol_ticks("TC.O.TWF.TX4.202607.C.44550", "2026071800", "2026071806")
        assert len(ticks) == 1

    def test_stops_on_empty_qry_index(self) -> None:
        # 末筆 QryIndex 空字串 = 分頁結束
        row = hist_row(1)
        row["QryIndex"] = ""

        class _LastPage:
            def GetHistory(self, *args: Any) -> dict[str, Any]:  # noqa: N802
                return {"HisData": [row]}

        src = TC4QuoteSource(port="0", api=_LastPage(), session="sess-1", poll_wait_secs=0.0)
        ticks = src._fetch_symbol_ticks("TC.O.TWF.TX4.202607.C.44550", "2026071800", "2026071806")
        assert len(ticks) == 1


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


class TestSpotSymbol:
    def test_spot_symbol_uses_txf_product_code(self) -> None:
        """item 2(2026-07-20 盤中驗證):TC4 symbol 樹的台指期產品碼是 TXF,FITX 不存在。

        FITX 只出現在 Quote.Security 欄位;SUBQUOTE 對不存在 symbol 照回 OK(平台不驗證)
        → 訂了永遠沒推播,spot 恆 None。證據:驗證報告 item 2 四步診斷鏈。
        """
        assert SPOT_SYMBOL == "TC.F.TWF.TXF.HOT"
