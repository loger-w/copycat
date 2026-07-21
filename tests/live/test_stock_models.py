from __future__ import annotations

import logging

from copycat.live.stock_models import (
    derive_side,
    is_trial_window,
    parse_hist_tick,
    parse_stock_realtime,
)

# 2026-07-21 盤中 probe 真實樣本(docs/research/2026-07-21-stock-spot-quote-order-probe.md)
REALTIME_MSG = {
    "Symbol": "TC.S.TWS.2330",
    "Exchange": "TWS",
    "Security": "2330",
    "SecurityName": "台積電",
    "TradeQuantity": "1",
    "FilledTime": "25751",
    "TradeDate": "20260721",
    "OpenTime": "90000",
    "CloseTime": "133000",
    "BidVolume": "125",
    "BidVolume1": "257",
    "BidVolume2": "605",
    "BidVolume3": "415",
    "BidVolume4": "502",
    "AskVolume": "461",
    "AskVolume1": "572",
    "AskVolume2": "506",
    "AskVolume3": "808",
    "AskVolume4": "222",
    "TradingPrice": "2380",
    "TradeVolume": "12479",
    "ReferencePrice": "2320",
    "UpperLimitPrice": "2550",
    "LowerLimitPrice": "2090",
    "YClosedPrice": "2320",
    "YTradeVolume": "45197",
    "Bid": "2380",
    "Bid1": "2375",
    "Bid2": "2370",
    "Bid3": "2365",
    "Bid4": "2360",
    "Bid5": "",
    "Ask": "2385",
    "Ask1": "2390",
    "Ask2": "2395",
    "Ask3": "2400",
    "Ask4": "2405",
    "Ask5": "",
    "PreciseTime": "25751000000",
    "TradeStatus": "0",
}


class TestParseStockRealtime:
    def test_full_sample_tick_book_meta(self) -> None:
        tick, book, meta = parse_stock_realtime(REALTIME_MSG)
        assert tick is not None
        assert tick.code == "2330"
        assert tick.price_milli == 2_380_000
        assert tick.qty == 1
        assert tick.cum_vol == 12479
        assert tick.time == "10:57:51.000"  # UTC 02:57:51 + 8h
        assert tick.trade_date == "2026-07-21"
        assert tick.is_trial is False
        assert tick.side == "inner"  # 2380 貼 Bid
        # 位移命名歸一:Bid=最佳(L0)、Bid1=第二檔(L1)
        assert book.bids == [
            (2_380_000, 125),
            (2_375_000, 257),
            (2_370_000, 605),
            (2_365_000, 415),
            (2_360_000, 502),
        ]
        assert book.asks == [
            (2_385_000, 461),
            (2_390_000, 572),
            (2_395_000, 506),
            (2_400_000, 808),
            (2_405_000, 222),
        ]
        assert meta.name == "台積電"
        assert meta.ref_milli == 2_320_000
        assert meta.upper_milli == 2_550_000
        assert meta.lower_milli == 2_090_000
        assert meta.y_close_milli == 2_320_000
        assert meta.y_volume == 45197
        assert meta.open_time == "09:00:00"
        assert meta.close_time == "13:30:00"

    def test_book_update_without_trade_returns_none_tick(self) -> None:
        msg = {**REALTIME_MSG, "TradeQuantity": "0"}
        tick, book, meta = parse_stock_realtime(msg)
        assert tick is None
        assert book.bids  # 簿更新照收
        assert meta.name == "台積電"

    def test_limit_up_empty_ask_side(self) -> None:
        msg = {**REALTIME_MSG}
        for key in ("Ask", "Ask1", "Ask2", "Ask3", "Ask4"):
            msg[key] = ""
        _, book, _ = parse_stock_realtime(msg)
        assert book.asks == []
        assert len(book.bids) == 5

    def test_trade_status_nonzero_warns_but_keeps_tick(self, caplog) -> None:
        msg = {**REALTIME_MSG, "TradeStatus": "3"}
        with caplog.at_level(logging.WARNING):
            tick, _, _ = parse_stock_realtime(msg)
        assert tick is not None  # r2-F5:未驗值域不丟,只觀測
        assert any("TradeStatus" in r.message for r in caplog.records)

    def test_trial_window_tick_marked(self) -> None:
        # UTC 00:35:00 = 台北 08:35(試撮窗內)
        msg = {**REALTIME_MSG, "FilledTime": "3500", "PreciseTime": "3500000000"}
        tick, _, _ = parse_stock_realtime(msg)
        assert tick is not None
        assert tick.is_trial is True

    def test_utc_rollover_advances_trade_date(self) -> None:
        # UTC 17:00:01 = 台北次日 01:00:01
        msg = {**REALTIME_MSG, "FilledTime": "170001", "PreciseTime": "170001000000"}
        tick, _, _ = parse_stock_realtime(msg)
        assert tick is not None
        assert tick.time == "01:00:01.000"
        assert tick.trade_date == "2026-07-22"


class TestTrialWindow:
    def test_boundaries(self) -> None:
        # [08:30, 09:00) 與 [13:25, 13:30) — 端點不含(design §2.1)
        assert is_trial_window("08:29:59.999") is False
        assert is_trial_window("08:30:00.000") is True
        assert is_trial_window("08:59:59.900") is True
        assert is_trial_window("09:00:00.000") is False
        assert is_trial_window("09:00:01.000") is False
        assert is_trial_window("13:24:59.000") is False
        assert is_trial_window("13:25:00.000") is True
        assert is_trial_window("13:29:59.000") is True
        assert is_trial_window("13:30:00.000") is False


class TestDeriveSide:
    def test_outer_inner_neutral(self) -> None:
        assert derive_side(2_385_000, 2_380_000, 2_385_000) == "outer"
        assert derive_side(2_380_000, 2_380_000, 2_385_000) == "inner"
        assert derive_side(2_382_500, 2_380_000, 2_385_000) == "neutral"
        assert derive_side(2_380_000, None, None) == "neutral"


class TestParseHistTick:
    def test_hist_row(self) -> None:
        # 2026-07-06 報告 §4 真實樣本
        row = {
            "Date": "20260703",
            "FilledTime": "10006",
            "TradeQuantity": "4182",
            "TradeVolume": "0",
            "Bid": "2415",
            "Ask": "2420",
            "TradingPrice": "2415",
            "PreciseTime": "10006840000",
            "OI": "",
            "QryIndex": "1",
        }
        tick = parse_hist_tick("2330", row)
        assert tick is not None
        assert tick.code == "2330"
        assert tick.price_milli == 2_415_000
        assert tick.qty == 4182
        assert tick.cum_vol == 0
        assert tick.time == "09:00:06.840"
        assert tick.trade_date == "2026-07-03"
        assert tick.side == "inner"  # 2415 貼 Bid

    def test_hist_row_missing_price_returns_none(self) -> None:
        row = {"Date": "20260703", "FilledTime": "10006", "TradeQuantity": "1",
               "TradingPrice": "", "PreciseTime": "10006840000"}
        assert parse_hist_tick("2330", row) is None
