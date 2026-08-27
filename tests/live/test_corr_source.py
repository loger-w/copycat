"""CorrQuoteSource:泛化 symbol 訂閱 + 全天窗覆寫(SC-5;design §5.5)。"""

from __future__ import annotations

import datetime
import json
import time
from typing import Callable

import pytest

from copycat.live.corr_source import CorrQuoteSource, all_day_window, segment_leg_gate
from copycat.live.stock_source import stock_window
from copycat.live.session import session_key, session_window
from copycat.live.stock_source import in_trading_hours_now
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


class TestHealDefaults:
    """自癒門檻(change-spec §3):海外腿推播稀疏 → 門檻放寬到 120 / 240,盤外照跑。"""

    def test_thresholds_and_always_active(self) -> None:
        src = CorrQuoteSource(api=FakeApi(lambda o: ok()), session="s1")
        assert src._heal_silence == 120.0
        assert src._heal_symbol_silence == 240.0
        assert src._heal_active() is True
        assert src._heal_sparse == frozenset()  # 預設不豁免任何腿;prod 由 app 從設定檔帶

    def test_sparse_symbols_pass_through_to_the_watchdog(self) -> None:
        sparse = frozenset({"TC.F.TWF.SXF.HOT"})
        src = CorrQuoteSource(api=FakeApi(lambda o: ok()), session="s1", heal_sparse_symbols=sparse)
        assert src._heal_sparse == sparse


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


class TestSegmentLegGate:
    """逐腿自癒閘的**前綴分派**(N051 + 2026-08-26 F4 台積電現貨腿)。

    corr 是唯一一條 session 上掛著時段各不相同的腿的:台期交段(TXF/SXF)、台股現貨段
    (2330)、以及 SGX / CME / CBOT / CFE / OSE 各段。閘分派錯的失效樣態沒有錯誤訊號 ——
    要嘛整晚對一條收盤的腿發 UNSUB+SUB(churn),要嘛該救的腿整場不救(永久零推播)。
    """

    @staticmethod
    def _gate(*, taifex: bool, tws: bool) -> Callable[[str], bool]:
        return segment_leg_gate(taifex=lambda: taifex, tws=lambda: tws)

    @pytest.mark.parametrize("clock", [True, False])
    def test_taifex_segment_follows_the_futures_gate(self, clock: bool) -> None:
        gate = self._gate(taifex=clock, tws=not clock)
        assert gate("TC.F.TWF.SXF.HOT") is clock
        assert gate("TC.F.TWF.TXF.HOT") is clock

    @pytest.mark.parametrize("clock", [True, False])
    def test_tws_segment_follows_the_stock_gate(self, clock: bool) -> None:
        """台積電現貨腿吃**個股日盤**閘,不是台期交閘(兩者收盤 13:30 vs 13:45 不同尺)。"""
        gate = self._gate(taifex=not clock, tws=clock)
        assert gate("TC.S.TWS.2330") is clock

    def test_overseas_segments_stay_ungated(self) -> None:
        """SGX / CME / CBOT / CFE / OSE 段恆 True:時段未實測,猜錯 = 該救的腿整場不救。"""
        gate = self._gate(taifex=False, tws=False)
        for symbol in (
            "TC.F.SGX.TWN.HOT",
            "TC.F.CBOT.YM.HOT",
            "TC.F.CME.ES.HOT",
            "TC.F.CME.CL.HOT",
            "TC.F.CME.GC.HOT",
            "TC.F.CFE.VX.HOT",
            "TC.F.OSE.NK225M.HOT",
        ):
            assert gate(symbol) is True, symbol

    def test_the_two_clocks_are_independent(self) -> None:
        """台股現貨 09:00–13:30 收盤後、台期交夜盤仍開的那一段:一關一開,不得互相牽動。"""
        gate = self._gate(taifex=True, tws=False)
        assert gate("TC.F.TWF.SXF.HOT") is True
        assert gate("TC.S.TWS.2330") is False


class TestTwsLegClock:
    """台積電腿吃的那把牆鐘 = 個股 session 既有的 `in_trading_hours_now`(不另立第二張表)。

    日曆 AND 那一半在 `app._default_corr_source`(見 tests/server/test_main_wiring.py)。
    """

    @pytest.mark.parametrize(
        ("hh", "mm", "expected"),
        [
            (10, 0, True),  # 盤中
            (8, 30, True),  # 試撮開始(現貨這段有推播,閘要開著才救得到)
            (13, 25, True),  # 收盤試撮起點那一分仍開(含端點;13:25:xx 前最後一筆成交推播還在路上)
            (13, 26, False),  # 收盤試撮 13:25–13:30 交易所不更新:看門狗誤判 19 發/日(2026-08-27 拍板 13:25)
            (13, 30, False),  # 收盤那筆推播照收(閘只管看門狗不管訂閱);訂閱若在試撮 5 分鐘死掉由 1K 尾段回補兜底
            (13, 35, False),  # 舊上界「收盤補正止」:夾到分鐘精度,改回 13:35 會紅
            (14, 0, False),  # 收盤後:整個下午 + 夜盤不得 churn
            (8, 29, False),
            (2, 0, False),  # 凌晨(台期交夜盤仍開,現貨腿必須關)
        ],
    )
    def test_stock_cash_session_only(self, hh: int, mm: int, expected: bool) -> None:
        assert in_trading_hours_now(datetime.time(hh, mm)) is expected


class TestTwsLegWindow:
    """review F-01:TWS 現貨腿必須與個股引擎同一把訂閱窗 key(refcount 兩邊各持一份,永不歸零);
    海外腿維持全天窗。"""

    def test_tws_leg_uses_stock_window_same_as_stock_engine(self) -> None:
        import datetime as _dt

        src = CorrQuoteSource(port="0")
        assert src._rt_window("TC.S.TWS.2330") == stock_window(f"{_dt.date.today():%Y-%m-%d}")
        assert src._rt_window("TC.S.TWS.2330") != all_day_window()

    def test_overseas_and_taifex_legs_keep_all_day_window(self) -> None:
        src = CorrQuoteSource(port="0")
        for sym in ("TC.F.CME.CL.HOT", "TC.F.CFE.VX.HOT", "TC.F.TWF.SXF.HOT", "TC.F.OSE.NK225M.HOT"):
            assert src._rt_window(sym) == all_day_window(), sym
