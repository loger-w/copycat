from __future__ import annotations

import datetime
import json

from copycat.live.futures_source import (
    FuturesQuoteSource,
    futures_symbol,
    in_futures_session_now,
)
from copycat.live.session import session_key, session_window
from tests.helpers.tc4_fakes import FakeApi, ok


class TestSymbol:
    def test_futures_symbol_hot(self) -> None:
        assert futures_symbol("TXF") == "TC.F.TWF.TXF.HOT"
        assert futures_symbol("TMF") == "TC.F.TWF.TMF.HOT"


def test_in_futures_session_now_uses_pad5() -> None:
    """期貨盤別閘 = TXO 時段各寬 5 分(不另建第二張時段表)。"""
    assert in_futures_session_now(datetime.time(13, 48)) is True  # 日盤收後寬限內
    assert in_futures_session_now(datetime.time(13, 52)) is False  # 寬限外 = 盤外
    assert in_futures_session_now(datetime.time(5, 3)) is True  # 夜盤收後寬限內


class TestHealDefaults:
    """自癒門檻(change-spec §3):三檔 HOT 全天都該有推播 → 30 / 60,盤外照跑
    (churn 上限 = 3 symbol / 300s,可接受;夜盤反而是最需要自癒的時段)。"""

    def test_thresholds_and_always_active(self) -> None:
        src = FuturesQuoteSource(api=FakeApi(lambda o: ok()), session="s1")
        assert src._heal_silence == 30.0
        assert src._heal_symbol_silence == 60.0
        assert src._heal_active() is True


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

    def test_realtime_without_quote_still_dispatched_as_empty(self) -> None:
        """`_realtime_msg` 回**整則 msg** 而非 `Quote` 的理由(tc4.py 檔內註解的行為面)。

        回 Quote 的話呼叫端只剩 truthy 可判,空 Quote 會跟「非 REALTIME」一起被吞掉。
        現況是空 Quote 照送 `{}`,下游自己決定怎麼處理 —— 這條沒有測試釘住時,
        改成回 Quote 的重構不會有任何測試變紅。
        """
        src = FuturesQuoteSource(api=FakeApi(lambda o: ok()), session="s1")
        got: list[dict] = []
        src.set_on_message(got.append)
        src.handle_raw("Q:" + json.dumps({"DataType": "REALTIME"}))
        assert got == [{}]
