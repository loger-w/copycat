from __future__ import annotations

import json

from copycat.live.futures_source import FuturesQuoteSource, futures_symbol
from copycat.live.session import session_key, session_window
from tests.helpers.tc4_fakes import FakeApi, ok


class TestSymbol:
    def test_futures_symbol_hot(self) -> None:
        assert futures_symbol("TXF") == "TC.F.TWF.TXF.HOT"
        assert futures_symbol("TMF") == "TC.F.TWF.TMF.HOT"


class TestSubscribe:
    def test_subscribe_unsub_then_sub_realtime_with_session_window(self) -> None:
        sent: list[dict] = []

        def handler(obj: dict) -> bytes:
            sent.append(obj)
            return ok()

        src = FuturesQuoteSource(api=FakeApi(handler), session="s1")
        src.subscribe_symbol("TXF")
        assert [o["Request"] for o in sent] == ["UNSUBQUOTE", "SUBQUOTE"]
        param = sent[1]["Param"]
        assert param["Symbol"] == "TC.F.TWF.TXF.HOT"
        assert param["SubDataType"] == "REALTIME"
        # 期貨與 TXO 同時段窗(日盤 08:45–13:45 / 夜盤 15:00–05:00)→ 沿用基底 session 窗
        start, end = session_window(session_key())
        assert param["StartTime"] == start
        assert param["EndTime"] == end

    def test_subscribe_all_covers_three_products(self) -> None:
        sent: list[dict] = []

        def handler(obj: dict) -> bytes:
            sent.append(obj)
            return ok()

        src = FuturesQuoteSource(api=FakeApi(handler), session="s1")
        src.subscribe_all()
        subs = [o["Param"]["Symbol"] for o in sent if o["Request"] == "SUBQUOTE"]
        assert subs == ["TC.F.TWF.TXF.HOT", "TC.F.TWF.MXF.HOT", "TC.F.TWF.TMF.HOT"]

    def test_subscribe_failure_raises(self) -> None:
        def handler(obj: dict) -> bytes:
            if obj["Request"] == "SUBQUOTE":
                return (json.dumps({"Success": "Fail", "ErrMsg": "x"}) + "\0").encode()
            return ok()

        src = FuturesQuoteSource(api=FakeApi(handler), session="s1")
        try:
            src.subscribe_symbol("TXF")
        except ConnectionError:
            pass
        else:
            raise AssertionError("subscribe 失敗必須 raise(engine 降級/重試依賴)")

    def test_subscribe_leaf_unsub_then_sub_realtime_with_session_window(self) -> None:
        # review T8:leaf 電文層(補訂實際月份契約,鏡射 subscribe_symbol)
        sent: list[dict] = []

        def handler(obj: dict) -> bytes:
            sent.append(obj)
            return ok()

        src = FuturesQuoteSource(api=FakeApi(handler), session="s1")
        src.subscribe_leaf("TXF", "202608")
        assert [o["Request"] for o in sent] == ["UNSUBQUOTE", "SUBQUOTE"]
        param = sent[1]["Param"]
        assert param["Symbol"] == "TC.F.TWF.TXF.202608"
        assert param["SubDataType"] == "REALTIME"
        start, end = session_window(session_key())
        assert param["StartTime"] == start
        assert param["EndTime"] == end

    def test_subscribe_leaf_failure_raises(self) -> None:
        def handler(obj: dict) -> bytes:
            if obj["Request"] == "SUBQUOTE":
                return (json.dumps({"Success": "Fail", "ErrMsg": "x"}) + "\0").encode()
            return ok()

        src = FuturesQuoteSource(api=FakeApi(handler), session="s1")
        try:
            src.subscribe_leaf("TXF", "202608")
        except ConnectionError:
            pass
        else:
            raise AssertionError("leaf subscribe 失敗必須 raise(engine 失敗重排依賴)")

    def test_unsubscribe_only_when_subscribed(self) -> None:
        sent: list[dict] = []

        def handler(obj: dict) -> bytes:
            sent.append(obj)
            return ok()

        src = FuturesQuoteSource(api=FakeApi(handler), session="s1")
        src.unsubscribe_symbol("TXF")  # 未訂閱 → 不送電文
        assert sent == []
        src.subscribe_symbol("TXF")
        sent.clear()
        src.unsubscribe_symbol("TXF")
        assert [o["Request"] for o in sent] == ["UNSUBQUOTE"]


class TestRawDispatch:
    def test_realtime_quote_dispatched(self) -> None:
        src = FuturesQuoteSource(api=FakeApi(lambda o: ok()), session="s1")
        got: list[dict] = []
        src.set_on_message(got.append)
        raw = "REALTIME:" + json.dumps(
            {"DataType": "REALTIME", "Quote": {"Symbol": "TC.F.TWF.TXF.HOT", "Security": "FITX"}}
        )
        src.handle_raw(raw)
        assert got == [{"Symbol": "TC.F.TWF.TXF.HOT", "Security": "FITX"}]

    def test_ping_ignored(self) -> None:
        src = FuturesQuoteSource(api=FakeApi(lambda o: ok()), session="s1")
        got: list[dict] = []
        src.set_on_message(got.append)
        src.handle_raw("PING:" + json.dumps({"DataType": "PING"}))
        src.handle_raw("not-json")
        assert got == []
