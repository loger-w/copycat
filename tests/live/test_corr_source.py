"""CorrQuoteSource:泛化 symbol 訂閱 + 全天窗覆寫(SC-5;design §5.5)。"""

from __future__ import annotations

import json
import time

import pytest

from copycat.live.corr_source import CorrQuoteSource, all_day_window
from copycat.live.session import session_key, session_window
from tests.helpers.tc4_fakes import FakeApi, ok


def _fail() -> bytes:
    return (json.dumps({"Success": "Fail", "ErrMsg": "nope"}) + "\0").encode()


class TestAllDayWindow:
    def test_covers_full_utc_day(self) -> None:
        ymd = time.strftime("%Y%m%d", time.gmtime())
        assert all_day_window() == (f"{ymd}00", f"{ymd}23")

    def test_differs_from_taifex_session_window(self) -> None:
        """P0-1 迴歸鎖:海外腿不得沿用台指盤別窗。

        日盤 session 窗為 UTC 00–06,美股現貨時段 UTC 13:30–20:00 完全落在窗外;
        TC4 對訂閱一律回 Success OK,窗不匹配的失效樣態是「訂閱成功但零推播」,
        沒有錯誤訊號。
        """
        assert all_day_window() != session_window(session_key())


class TestSubscribe:
    def test_subscribe_raw_uses_all_day_window_not_session_window(self) -> None:
        sent: list[dict] = []

        def handler(obj: dict) -> bytes:
            sent.append(obj)
            return ok()

        src = CorrQuoteSource(api=FakeApi(handler), session="s1")
        src.subscribe_raw("TC.F.CME.ES.HOT")

        assert [o["Request"] for o in sent] == ["UNSUBQUOTE", "SUBQUOTE"]
        param = sent[1]["Param"]
        assert param["Symbol"] == "TC.F.CME.ES.HOT"
        assert param["SubDataType"] == "REALTIME"
        assert (param["StartTime"], param["EndTime"]) == all_day_window()
        assert (param["StartTime"], param["EndTime"]) != session_window(session_key())

    def test_accepts_any_exchange_segment(self) -> None:
        """SGX / CBOT / CME / TWF 四段都要能訂 —— futures_source 寫死 TC.F.TWF. 段。"""
        sent: list[dict] = []

        def handler(obj: dict) -> bytes:
            sent.append(obj)
            return ok()

        src = CorrQuoteSource(api=FakeApi(handler), session="s1")
        for sym in (
            "TC.F.SGX.TWN.HOT",
            "TC.F.CBOT.YM.HOT",
            "TC.F.CME.NQ.HOT",
            "TC.F.TWF.SXF.HOT",
        ):
            src.subscribe_raw(sym)

        subscribed = [o["Param"]["Symbol"] for o in sent if o["Request"] == "SUBQUOTE"]
        assert subscribed == [
            "TC.F.SGX.TWN.HOT",
            "TC.F.CBOT.YM.HOT",
            "TC.F.CME.NQ.HOT",
            "TC.F.TWF.SXF.HOT",
        ]

    def test_failed_subscribe_raises_connection_error(self) -> None:
        def handler(obj: dict) -> bytes:
            return ok() if obj["Request"] == "UNSUBQUOTE" else _fail()

        src = CorrQuoteSource(api=FakeApi(handler), session="s1")
        with pytest.raises(ConnectionError):
            src.subscribe_raw("TC.F.CME.ES.HOT")

    def test_unsubscribe_only_sends_for_subscribed_symbol(self) -> None:
        sent: list[dict] = []

        def handler(obj: dict) -> bytes:
            sent.append(obj)
            return ok()

        src = CorrQuoteSource(api=FakeApi(handler), session="s1")
        src.unsubscribe_raw("TC.F.CME.ES.HOT")  # 未訂閱 → no-op
        assert sent == []


class TestHandleRaw:
    def test_realtime_quote_dispatched(self) -> None:
        got: list[dict] = []
        src = CorrQuoteSource(api=FakeApi(lambda o: ok()), session="s1")
        src.set_on_message(got.append)

        src.handle_raw('TOPIC:{"DataType":"REALTIME","Quote":{"Symbol":"TC.F.CME.ES.HOT"}}')

        assert got == [{"Symbol": "TC.F.CME.ES.HOT"}]

    def test_non_realtime_ignored(self) -> None:
        got: list[dict] = []
        src = CorrQuoteSource(api=FakeApi(lambda o: ok()), session="s1")
        src.set_on_message(got.append)

        src.handle_raw('TOPIC:{"DataType":"PING"}')

        assert got == []

    def test_malformed_payload_ignored(self) -> None:
        got: list[dict] = []
        src = CorrQuoteSource(api=FakeApi(lambda o: ok()), session="s1")
        src.set_on_message(got.append)

        src.handle_raw("no-colon-here")
        src.handle_raw("TOPIC:{not json")

        assert got == []
