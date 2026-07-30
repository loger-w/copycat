from __future__ import annotations

import pytest

from copycat.live.models import (
    OptionContract,
    Tick,
    parse_history_tick,
    parse_option_symbol,
    parse_realtime,
    to_millipts,
)

# spike 真實樣本(docs/research/2026-07-18-txo-chain-probe.md)
HISTORY_RAW = {
    "Date": "20260717",
    "FilledTime": "25924",
    "TradeQuantity": "1",
    "TradeVolume": "0",
    "Bid": "330",
    "Ask": "348",
    "TradingPrice": "330",
    "PreciseTime": "25924127000",
    "OI": "",
    "QryIndex": "1",
}

REALTIME_RAW = {
    "Symbol": "TC.O.TWF.TX4.202607.C.44550",
    "Security": "TX4",
    "CallPut": "C",
    "TradeQuantity": "1",
    "TradeVolume": "537",
    "TradingPrice": "102",
    "Bid": "68",
    "Ask": "131",
    "PreciseTime": "205957777000",
    "StrikePrice": "44550",
}


class TestToMillipts:
    def test_integer_points(self) -> None:
        assert to_millipts("102") == 102_000

    def test_decimal_tick(self) -> None:
        assert to_millipts("0.1") == 100

    def test_fractional_price(self) -> None:
        assert to_millipts("43735.46") == 43_735_460

    def test_empty_is_none(self) -> None:
        assert to_millipts("") is None

    def test_garbage_is_none(self) -> None:
        assert to_millipts("N/A") is None


class TestParseHistoryTick:
    def test_spike_sample_fields(self) -> None:
        tick = parse_history_tick("TC.O.TWF.TX4.202607.C.44550", HISTORY_RAW)
        assert tick == Tick(
            symbol="TC.O.TWF.TX4.202607.C.44550",
            precise_time=25924127000,
            price_millipts=330_000,
            qty=1,
            bid_millipts=330_000,
            ask_millipts=348_000,
            cum_volume=None,  # 歷史 TICKS 無累積量(spike 實測 TradeVolume 全 0)
            seq=1,
        )

    def test_missing_price_is_none(self) -> None:
        raw = dict(HISTORY_RAW, TradingPrice="")
        assert parse_history_tick("TC.O.TWF.TX4.202607.C.44550", raw) is None

    def test_missing_bid_ask_kept_as_none(self) -> None:
        raw = dict(HISTORY_RAW, Ask="")
        tick = parse_history_tick("TC.O.TWF.TX4.202607.C.44550", raw)
        assert tick is not None
        assert tick.ask_millipts is None
        assert tick.bid_millipts == 330_000


class TestParseRealtime:
    def test_spike_sample_fields(self) -> None:
        tick = parse_realtime(REALTIME_RAW)
        assert tick == Tick(
            symbol="TC.O.TWF.TX4.202607.C.44550",
            precise_time=205957777000,
            price_millipts=102_000,
            qty=1,
            bid_millipts=68_000,
            ask_millipts=131_000,
            cum_volume=537,
            seq=0,
        )

    def test_no_trade_is_none(self) -> None:
        assert parse_realtime(dict(REALTIME_RAW, TradeQuantity="0")) is None
        assert parse_realtime(dict(REALTIME_RAW, TradeQuantity="")) is None

    def test_spot_snapshot_without_trade_qty_still_parses(self) -> None:
        """TC.F.*(現價源)休市 snapshot 的 TradeQuantity 可為 0,只需 price(Phase 6 實測)。"""
        raw = dict(
            REALTIME_RAW,
            Symbol="TC.F.TWF.TXF.HOT",
            TradeQuantity="0",
            TradingPrice="43735.46",
        )
        tick = parse_realtime(raw)
        assert tick is not None
        assert tick.symbol == "TC.F.TWF.TXF.HOT"
        assert tick.price_millipts == 43_735_460
        assert tick.qty == 0

    def test_txf_month_leaf_zero_qty_also_parses(self) -> None:
        """leaf 契約(futures_engine fallback)同屬現價源。"""
        raw = dict(
            REALTIME_RAW, Symbol="TC.F.TWF.TXF.202609", TradeQuantity="0", TradingPrice="43800"
        )
        assert parse_realtime(raw) is not None

    @pytest.mark.parametrize(
        "symbol",
        ["TC.F.TWF.DHF.HOT", "TC.F.CME.YM.HOT", "TC.F.SGX.TWN.HOT", "TC.F.TWF.MXF.HOT"],
    )
    def test_non_txf_futures_zero_qty_is_dropped(self, symbol: str) -> None:
        """零量放行的特例只給台指期(現價源)。放寬到整棵 TC.F.* 會讓個股期 / 海外腿的
        零量 snapshot 也流進 ChainAggregator.route,放大 spot 被覆寫的頻率。"""
        raw = dict(REALTIME_RAW, Symbol=symbol, TradeQuantity="0", TradingPrice="232.5")
        assert parse_realtime(raw) is None


class TestParseOptionSymbol:
    def test_leaf_symbol(self) -> None:
        assert parse_option_symbol("TC.O.TWF.TX4.202607.C.44550") == (
            "TX4",
            "202607",
            "C",
            44550,
        )

    def test_non_option_is_none(self) -> None:
        assert parse_option_symbol("TC.F.TWF.TXF.HOT") is None
        assert parse_option_symbol("TC.O.TWF.TX4.202607") is None


class TestOptionContract:
    def test_frozen_value_semantics(self) -> None:
        a = OptionContract(symbol="TC.O.TWF.TX4.202607.C.44550", cp="C", strike_millipts=44_550_000)
        b = OptionContract(symbol="TC.O.TWF.TX4.202607.C.44550", cp="C", strike_millipts=44_550_000)
        assert a == b
