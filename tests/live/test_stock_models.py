from __future__ import annotations

import logging
from dataclasses import replace

from copycat.live.stock_models import (
    StockTick,
    derive_side,
    is_trial_window,
    parse_hist_tick,
    parse_stock_realtime,
    relabel_locked_side,
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

    def test_trade_status_one_is_known_no_warning(self, caplog) -> None:
        # 2026-07-21 13:25-13:30 實測:試撮期簿更新帶 TradeStatus=1(213 筆),
        # 屬已知狀態,不 warning(否則每天收盤前刷 213 條)
        msg = {**REALTIME_MSG, "TradeStatus": "1"}
        with caplog.at_level(logging.WARNING):
            tick, _, _ = parse_stock_realtime(msg)
        assert tick is not None
        assert not any("TradeStatus" in r.message for r in caplog.records)

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


class TestMarketOrderPseudoLevel:
    """round6 項 2:鎖漲跌停時 TC4 會在簿的第一檔推「市價單佇列」,價格欄是 `0`。

    `0` 不是價格 —— 它是「這些單沒有限價」。拿它當 bid0/ask0 餵 `derive_side`,
    兩側都會壞掉,而且是**靜默**的:

    - 鎖漲停(ask 側空、`bids[0] = (0, N)`):`price <= 0` 恆假 → 每一筆成交判 neutral。
      2026-07-31 盤中實測 2327 國巨:全日 5450 張成交,`cum_outer = cum_inner = 0`,
      內外盤副圖整片灰、外盤比分母 0 算不出來。
    - 鎖跌停(bid 側空、`asks[0] = (0, N)`):`price >= 0` **恆真** → 一律判 outer。
      方向碰巧對(鎖跌停的成交確為主動買),但 bid 側判定被完全短路,
      而且 `ask_milli` 會留下一個假的 `0` 進明細欄位。

    修法只動「餵給 derive_side 的最佳價取值」,**簿本身原樣保留 0 檔位**(W-23)——
    五檔與閃電梯要把它顯示成「市價」。
    """

    # 2026-07-31 盤中實測 2327 國巨的簿形狀(bids[0] 是 15966 張市價買單)
    LOCK_UP_MSG = {
        **REALTIME_MSG,
        "Security": "2327",
        "SecurityName": "國巨*",
        "TradingPrice": "502",
        "ReferencePrice": "456.5",
        "UpperLimitPrice": "502",
        "LowerLimitPrice": "411",
        "Bid": "0",
        "BidVolume": "15966",
        "Bid1": "502",
        "BidVolume1": "9385",
        "Bid2": "501",
        "Bid3": "500",
        "Bid4": "499.5",
        "Ask": "",
        "Ask1": "",
        "Ask2": "",
        "Ask3": "",
        "Ask4": "",
        "Ask5": "",
    }

    def test_lock_up_market_bid_level_no_longer_swallows_side(self) -> None:
        tick, _book, _meta = parse_stock_realtime(self.LOCK_UP_MSG)
        assert tick is not None
        # 最佳「限價」買 = 漲停價本身,不是市價佇列的 0
        assert tick.bid_milli == 502_000
        assert tick.ask_milli is None
        # 成交價 == 最佳限價買 → 內盤(鎖漲停的成交都是賣方主動撞排隊的買單)
        assert tick.side == "inner"

    def test_lock_up_book_still_carries_the_zero_level(self) -> None:
        """W-23:簿原樣保留 —— 五檔要把它畫成「市價 15966」。"""
        _tick, book, _meta = parse_stock_realtime(self.LOCK_UP_MSG)
        assert book.bids[0] == (0, 15966)
        assert book.bids[1] == (502_000, 9385)

    def test_lock_down_market_ask_level_no_longer_shortcircuits(self) -> None:
        msg = {
            **REALTIME_MSG,
            "TradingPrice": "411",
            "ReferencePrice": "456.5",
            "UpperLimitPrice": "502",
            "LowerLimitPrice": "411",
            "Ask": "0",
            "AskVolume": "20000",
            "Ask1": "411",
            "AskVolume1": "5000",
            "Ask2": "",
            "Ask3": "",
            "Ask4": "",
            "Bid": "",
            "Bid1": "",
            "Bid2": "",
            "Bid3": "",
            "Bid4": "",
            "Bid5": "",
        }
        tick, book, _meta = parse_stock_realtime(msg)
        assert tick is not None
        # 假的 0 不可進明細欄位
        assert tick.ask_milli == 411_000
        assert tick.bid_milli is None
        assert tick.side == "outer"
        assert book.asks[0] == (0, 20000)  # 簿仍保留(W-23)

    def test_normal_book_unaffected(self) -> None:
        """回歸鎖:沒有 0 檔位的正常簿,判定與取值一字不差。"""
        tick, _book, _meta = parse_stock_realtime(REALTIME_MSG)
        assert tick is not None
        assert tick.bid_milli == 2_380_000
        assert tick.ask_milli == 2_385_000
        assert tick.side == "inner"

    def test_locked_relabel_recovers_side_when_book_column_is_unusable(self) -> None:
        """歷史 TICKS row 只有單一 Bid/Ask 欄,鎖停日該欄就是市價佇列的 0,**沒有第二檔可退**
        → `derive_side` 只能誠實回 neutral。

        但「鎖漲停 + 委賣側不可得」這個組合本身就決定了主動方:漲停價之上沒有更高價可掛,
        主動買方只能排隊,所以**唯一**能促成成交的是主動賣方 → 內盤。鎖跌停對稱。
        這不是猜測,是漲跌停制度下的恆等式,所以可以在拿得到 upper/lower 的地方補判。
        """
        neutral = StockTick(
            code="2327",
            price_milli=502_000,
            qty=3,
            cum_vol=5448,
            time="12:00:00.000",
            trade_date="2026-07-31",
            side="neutral",
            is_trial=False,
            bid_milli=None,
            ask_milli=None,
        )
        up = relabel_locked_side(neutral, upper_milli=502_000, lower_milli=411_000)
        assert up.side == "inner"

        at_lower = replace(neutral, price_milli=411_000)
        assert relabel_locked_side(at_lower, upper_milli=502_000, lower_milli=411_000).side == "outer"

    def test_locked_relabel_leaves_everything_else_alone(self) -> None:
        base = StockTick(
            code="2330",
            price_milli=2_382_500,
            qty=1,
            cum_vol=1,
            time="10:00:00.000",
            trade_date="2026-07-31",
            side="neutral",
            is_trial=False,
            bid_milli=2_380_000,
            ask_milli=2_385_000,
        )
        # 價差內成交,不在漲跌停 → 維持 neutral(本輪不動這條,誠實留白)
        assert relabel_locked_side(base, upper_milli=2_550_000, lower_milli=2_090_000) is base
        # 已判定的 tick 一律不動(即使價格恰在漲停)
        decided = replace(base, side="outer", price_milli=2_550_000)
        assert relabel_locked_side(decided, upper_milli=2_550_000, lower_milli=2_090_000) is decided
        # 漲跌停不可得 → 不猜
        assert relabel_locked_side(base, upper_milli=None, lower_milli=None) is base
        # 對手側**拿得到**時不套用 —— 有 ask 還判不出來是另一回事,不可用鎖停規則蓋過去
        with_ask = replace(base, price_milli=2_550_000, bid_milli=None)
        assert relabel_locked_side(with_ask, upper_milli=2_550_000, lower_milli=2_090_000) is with_ask

    def test_first_touch_of_limit_is_not_relabelled(self) -> None:
        """Phase 5 review P2:`ask is None` 不等於「鎖住了」。

        「首次攻上漲停、把賣方掛單一次吃光」的那一筆,成交後簿的 ask 側同樣是空的,
        但它實際是**主動買**(outer)。只看 ask 空會把它反向標成 inner,偏誤方向固定
        (系統性低估攻擊方)—— 恰好打到本輪要修對的外盤比。
        真鎖停時歷史 row 的 Bid 是市價佇列的 0(已歸零成 None),首攻那筆的 Bid 有值。
        """
        first_touch = StockTick(
            code="2327",
            price_milli=502_000,
            qty=50,
            cum_vol=1200,
            time="09:30:00.000",
            trade_date="2026-07-31",
            side="neutral",
            is_trial=False,
            bid_milli=501_000,  # 買方還掛著限價 → 不是鎖死
            ask_milli=None,  # 賣單剛被吃光
        )
        assert (
            relabel_locked_side(first_touch, upper_milli=502_000, lower_milli=411_000)
            is first_touch
        )

    def test_hist_row_zero_bid_is_not_a_price(self) -> None:
        row = {
            "Date": "20260731",
            "PreciseTime": "40000000000",
            "TradeQuantity": "3",
            "TradingPrice": "502",
            "TradeVolume": "5448",
            "Bid": "0",
            "Ask": "",
        }
        tick = parse_hist_tick("2327", row)
        assert tick is not None
        assert tick.bid_milli is None  # 0 不是價格
        assert tick.side == "neutral"  # 兩側都不可得 → 誠實地判不出來


class TestTickCarriesBidAsk:
    """round5 項 3:明細要顯示成交當下的買賣價。

    `derive_side` 早就取了 bid0/ask0(`:139-140`)只是沒留存 —— 補欄位不是新資料源。
    """

    def test_realtime_tick_keeps_best_bid_ask(self) -> None:
        tick, _book, _meta = parse_stock_realtime(REALTIME_MSG)
        assert tick is not None
        assert tick.bid_milli == 2_380_000  # Bid=2380
        assert tick.ask_milli == 2_385_000  # Ask=2385

    def test_realtime_missing_book_side_gives_none_without_changing_side(self) -> None:
        # 漲停鎖死(賣方掛單被吃光)→ ask 側空。side 判定必須與現況一字不差(W-18)
        msg = dict(REALTIME_MSG)
        for key in ("Ask", "Ask1", "Ask2", "Ask3", "Ask4", "Ask5"):
            msg[key] = ""
        tick, _book, _meta = parse_stock_realtime(msg)
        assert tick is not None
        assert tick.ask_milli is None
        assert tick.bid_milli == 2_380_000
        # ask 不可得 → derive_side 第一條(price >= ask → outer)整條跳過,落到第二條
        # price(2380)<= bid(2380)→ inner。這是**既有**判定,補欄位不得改動它(W-18)。
        assert tick.side == "inner"

    def test_hist_tick_keeps_bid_ask(self) -> None:
        row = {
            "Date": "20260703",
            "FilledTime": "10006",
            "TradeQuantity": "4182",
            "TradeVolume": "0",
            "Bid": "2415",
            "Ask": "2420",
            "TradingPrice": "2415",
            "PreciseTime": "10006840000",
            "QryIndex": "1",
        }
        tick = parse_hist_tick("2330", row)
        assert tick is not None
        assert tick.bid_milli == 2_415_000
        assert tick.ask_milli == 2_420_000
        assert tick.side == "inner"  # 既有判定不變(W-18)

    def test_hist_tick_without_bid_ask_columns(self) -> None:
        row = {
            "Date": "20260703",
            "FilledTime": "10006",
            "TradeQuantity": "1",
            "TradingPrice": "2415",
            "PreciseTime": "10006840000",
        }
        tick = parse_hist_tick("2330", row)
        assert tick is not None
        assert tick.bid_milli is None
        assert tick.ask_milli is None
