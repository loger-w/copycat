from __future__ import annotations

import logging

import pytest

from copycat.live.aggregate import ChainAggregator
from copycat.live.models import OptionContract, SeriesInfo, Tick

C44000 = OptionContract(symbol="TC.O.TWF.TX4.202607.C.44000", cp="C", strike_millipts=44_000_000)
P44000 = OptionContract(symbol="TC.O.TWF.TX4.202607.P.44000", cp="P", strike_millipts=44_000_000)
SERIES = SeriesInfo(
    series_id="TX4.202607",
    name="TX4 202607",
    expiry="202607",
    contracts=(C44000, P44000),
)
TXF = "TC.F.TWF.TXF.HOT"


def tick(
    symbol: str,
    *,
    price: int,
    qty: int = 1,
    bid: int | None = None,
    ask: int | None = None,
    cum: int | None = None,
    t: int = 90000_000000,
) -> Tick:
    return Tick(
        symbol=symbol,
        precise_time=t,
        price_millipts=price,
        qty=qty,
        bid_millipts=bid,
        ask_millipts=ask,
        cum_volume=cum,
    )


def make_agg() -> ChainAggregator:
    return ChainAggregator([C44000, P44000])


class TestClassification:
    def test_at_ask_is_outer_buy(self) -> None:
        agg = make_agg()
        agg.route(tick(C44000.symbol, price=100_000, qty=2, bid=99_000, ask=100_000))
        snap = agg.snapshot(series=SERIES, status="live", accumulated_from="08:45:00")
        assert snap["totals"]["call_net_qty"] == 2

    def test_at_bid_is_inner_sell(self) -> None:
        agg = make_agg()
        agg.route(tick(C44000.symbol, price=99_000, qty=1, bid=99_000, ask=100_000))
        snap = agg.snapshot(series=SERIES, status="live", accumulated_from="08:45:00")
        assert snap["totals"]["call_net_qty"] == -1

    def test_mid_or_missing_quote_unclassified(self) -> None:
        agg = make_agg()
        agg.route(tick(C44000.symbol, price=99_500, qty=3, bid=99_000, ask=100_000))
        agg.route(tick(P44000.symbol, price=99_000, qty=2, bid=None, ask=None))
        snap = agg.snapshot(series=SERIES, status="live", accumulated_from="08:45:00")
        assert snap["totals"]["call_net_qty"] == 0
        assert snap["totals"]["put_net_qty"] == 0
        assert snap["totals"]["unclassified_ticks"] == 2
        assert snap["totals"]["unclassified_qty"] == 5

    def test_put_side_accumulates_separately(self) -> None:
        agg = make_agg()
        agg.route(tick(P44000.symbol, price=50_000, qty=4, bid=49_000, ask=50_000))
        snap = agg.snapshot(series=SERIES, status="live", accumulated_from="08:45:00")
        assert snap["totals"]["call_net_qty"] == 0
        assert snap["totals"]["put_net_qty"] == 4


class TestLiveDedup:
    def test_cum_volume_must_increase(self) -> None:
        agg = make_agg()
        agg.route(tick(C44000.symbol, price=100_000, qty=2, bid=99_000, ask=100_000, cum=10))
        agg.route(tick(C44000.symbol, price=100_000, qty=2, bid=99_000, ask=100_000, cum=10))
        agg.route(tick(C44000.symbol, price=100_000, qty=1, bid=99_000, ask=100_000, cum=9))
        snap = agg.snapshot(series=SERIES, status="live", accumulated_from="08:45:00")
        assert snap["totals"]["call_net_qty"] == 2
        assert snap["totals"]["ticks"] == 1


class TestRouting:
    def test_txf_updates_spot_only(self) -> None:
        agg = make_agg()
        agg.route(tick(TXF, price=43_735_460, qty=1, cum=100))
        snap = agg.snapshot(series=SERIES, status="live", accumulated_from="08:45:00")
        assert snap["spot"]["price"] == 43735.46
        assert snap["totals"]["ticks"] == 0

    def test_foreign_symbol_dropped_and_counted(self) -> None:
        agg = make_agg()
        agg.route(tick("TC.O.TWF.TXO.202608.C.44000", price=100_000, qty=1))
        snap = agg.snapshot(series=SERIES, status="live", accumulated_from="08:45:00")
        assert snap["totals"]["dropped_foreign_ticks"] == 1
        assert snap["totals"]["ticks"] == 0

    def test_txf_month_leaf_also_updates_spot(self) -> None:
        """futures_engine 的 leaf fallback 訂 TC.F.TWF.TXF.<YYYYMM> —— 同一標的同一價位,
        HOT 推播被搶走時它是唯一的現價來源(CLAUDE.md §8 同 symbol 跨 session 只推一邊)。"""
        agg = make_agg()
        agg.route(tick("TC.F.TWF.TXF.202609", price=43_800_000, qty=1))
        snap = agg.snapshot(series=SERIES, status="live", accumulated_from="08:45:00")
        assert snap["spot"]["price"] == 43800.0

    @pytest.mark.parametrize(
        "symbol",
        [
            "TC.F.TWF.DHF.HOT",  # 個股期(2317;stock_engine 期現對照訂的)
            "TC.F.CME.YM.HOT",  # 海外腿(corr_engine 六腿)
            "TC.F.CME.ES.HOT",
            "TC.F.CBOT.NQ.HOT",
            "TC.F.SGX.TWN.HOT",  # 富台
            "TC.F.TWF.SXF.HOT",  # 費半(台期交段但非台指期)
            "TC.F.TWF.MXF.HOT",  # 小台(futures_engine 訂的,非 TXO runtime 的現價源)
        ],
    )
    def test_non_txf_futures_must_not_overwrite_spot(self, symbol: str) -> None:
        """TXO runtime 的 ZMQ SUB 訂 "" 會收到同 process 其他引擎訂的所有期貨推播。
        整棵 TC.F.* 樹當現價源 → spot 被不同商品輪流覆寫(右上角台指與 spot_pnl 一起亂跳,
        2026-07-29 盤中實測個股期 232.5)。"""
        agg = make_agg()
        agg.route(tick(TXF, price=43_735_460, qty=1, cum=100))
        agg.route(tick(symbol, price=232_500, qty=1, cum=200))
        snap = agg.snapshot(series=SERIES, status="live", accumulated_from="08:45:00")
        assert snap["spot"]["price"] == 43735.46
        assert snap["totals"]["dropped_foreign_ticks"] == 1
        assert snap["totals"]["ticks"] == 0  # 非合約 → 不進內外盤累積

    def test_backfill_skips_non_txf_futures(self) -> None:
        """回補路徑同樣不得把其他期貨當合約灌進累積(ingest_backfill 與 route 共用同一判斷)。"""
        agg = make_agg()
        rebuilt = agg.ingest_backfill(
            [
                tick(TXF, price=43_735_460, qty=1),
                tick("TC.F.TWF.DHF.HOT", price=232_500, qty=1),
                tick(C44000.symbol, price=100_000, qty=2, bid=99_000, ask=100_000),
            ]
        )
        assert rebuilt == {C44000.symbol: 2}


class TestBackfillIngest:
    def test_rebuilds_cum_from_qty(self) -> None:
        agg = make_agg()
        rebuilt = agg.ingest_backfill(
            [
                tick(C44000.symbol, price=100_000, qty=3, bid=99_000, ask=100_000, t=1),
                tick(C44000.symbol, price=100_000, qty=2, bid=99_000, ask=100_000, t=2),
            ]
        )
        assert rebuilt == {C44000.symbol: 5}
        # live tick 帶 cum ≤ 重建值 → 丟棄
        agg.route(tick(C44000.symbol, price=100_000, qty=5, bid=99_000, ask=100_000, cum=5))
        snap = agg.snapshot(series=SERIES, status="live", accumulated_from="08:45:00")
        assert snap["totals"]["call_net_qty"] == 5

    def test_ingest_sorts_by_time(self) -> None:
        agg = make_agg()
        agg.ingest_backfill(
            [
                tick(C44000.symbol, price=100_000, qty=1, bid=99_000, ask=100_000, t=2),
                tick(C44000.symbol, price=99_000, qty=1, bid=99_000, ask=100_000, t=1),
            ]
        )
        snap = agg.snapshot(series=SERIES, status="live", accumulated_from="08:45:00")
        assert snap["totals"]["ticks"] == 2


class TestReset:
    def test_reset_clears_everything(self) -> None:
        agg = make_agg()
        agg.route(tick(C44000.symbol, price=100_000, qty=2, bid=99_000, ask=100_000, cum=10))
        agg.reset([P44000])
        snap = agg.snapshot(series=SERIES, status="live", accumulated_from="08:45:00")
        assert snap["totals"]["ticks"] == 0
        assert snap["totals"]["call_net_qty"] == 0
        # 舊合約變 foreign
        agg.route(tick(C44000.symbol, price=100_000, qty=1, bid=99_000, ask=100_000, cum=11))
        snap = agg.snapshot(series=SERIES, status="live", accumulated_from="08:45:00")
        assert snap["totals"]["dropped_foreign_ticks"] == 1


class TestSnapshot:
    def test_empty_state_no_fake_curve(self) -> None:
        agg = make_agg()
        snap = agg.snapshot(series=SERIES, status="backfilling", accumulated_from="08:45:00")
        assert snap["curve"] == []
        assert snap["beps"] == []
        assert snap["max_profit"] is None
        assert snap["max_loss"] is None
        assert snap["spot_pnl"] is None
        assert snap["totals"]["ticks"] == 0

    def test_populated_snapshot_shape(self) -> None:
        agg = make_agg()
        # sell 2 C44000 @100pt(內盤)
        agg.route(tick(C44000.symbol, price=100_000, qty=2, bid=100_000, ask=101_000))
        agg.route(tick(TXF, price=44_000_000, qty=1))
        snap = agg.snapshot(
            series=SERIES, status="live", accumulated_from="08:45:00", queue_dropped=7
        )
        assert snap["series_id"] == "TX4.202607"
        assert snap["status"] == "live"
        assert snap["totals"]["queue_dropped"] == 7
        assert snap["totals"]["contracts_active"] == 1
        # 賣方收 200pt 權利金:K=44000 → +10,000 NTD
        assert (44_000_000, 10_000.0) in snap["curve"]
        assert snap["spot"]["price"] == 44000.0
        assert snap["spot_pnl"] == 10_000.0


class TestContractsDetail:
    """SC-1:snapshot per-contract 明細(design.md §2;內外盤分量 + 排序 + 不變量)。"""

    def test_snapshot_contracts_detail(self) -> None:
        agg = make_agg()
        # C44000:外盤 2 @100pt、內盤 1 @99pt、未分類 3 @99.5pt
        agg.route(tick(C44000.symbol, price=100_000, qty=2, bid=99_000, ask=100_000))
        agg.route(tick(C44000.symbol, price=99_000, qty=1, bid=99_000, ask=100_000))
        agg.route(tick(C44000.symbol, price=99_500, qty=3, bid=99_000, ask=100_000))
        # P44000:內盤 4 @50pt
        agg.route(tick(P44000.symbol, price=50_000, qty=4, bid=50_000, ask=51_000))
        snap = agg.snapshot(series=SERIES, status="live", accumulated_from="08:45:00")
        assert snap["contracts"] == [
            {
                "symbol": C44000.symbol,
                "cp": "C",
                "strike": 44000,
                "net_qty": 1,
                "volume": 6,
                "outer_qty": 2,
                "inner_qty": 1,
            },
            {
                "symbol": P44000.symbol,
                "cp": "P",
                "strike": 44000,
                "net_qty": -4,
                "volume": 4,
                "outer_qty": 0,
                "inner_qty": 4,
            },
        ]

    def test_contracts_invariants(self) -> None:
        # 手寫固定序列覆蓋外/內/未分類三分支(IR-5:不用 random)
        c43 = OptionContract(
            symbol="TC.O.TWF.TX4.202607.C.43000", cp="C", strike_millipts=43_000_000
        )
        agg = ChainAggregator([C44000, P44000, c43])
        for t in [
            tick(C44000.symbol, price=100_000, qty=2, bid=99_000, ask=100_000),
            tick(C44000.symbol, price=99_000, qty=5, bid=99_000, ask=100_000),
            tick(c43.symbol, price=99_500, qty=3, bid=99_000, ask=100_000),
            tick(c43.symbol, price=100_000, qty=7, bid=99_000, ask=100_000),
            tick(P44000.symbol, price=50_000, qty=4, bid=50_000, ask=51_000),
            tick(P44000.symbol, price=50_200, qty=6, bid=50_000, ask=51_000),
        ]:
            agg.route(t)
        snap = agg.snapshot(series=SERIES, status="live", accumulated_from="08:45:00")
        rows = snap["contracts"]
        assert len(rows) == 3
        for row in rows:
            assert row["net_qty"] == row["outer_qty"] - row["inner_qty"]
            assert row["volume"] - row["outer_qty"] - row["inner_qty"] >= 0
        unclassified = sum(r["volume"] - r["outer_qty"] - r["inner_qty"] for r in rows)
        assert unclassified == snap["totals"]["unclassified_qty"]
        # 排序 deterministic:strike 升冪、同 strike C 在前
        assert [(r["strike"], r["cp"]) for r in rows] == [
            (43000, "C"),
            (44000, "C"),
            (44000, "P"),
        ]

    def test_contracts_reset_cleared(self) -> None:
        agg = make_agg()
        agg.route(tick(C44000.symbol, price=100_000, qty=2, bid=99_000, ask=100_000))
        agg.reset([P44000])
        snap = agg.snapshot(series=SERIES, status="live", accumulated_from="08:45:00")
        assert snap["contracts"] == []

    def test_non_integer_strike_warns_once_at_reset(self, caplog: pytest.LogCaptureFixture) -> None:
        # DR-5 + CR-2:非整數點履約價於合約集合載入時 warning 一次,
        # snapshot(~1/s 廣播路徑)不重複洗版
        odd = OptionContract(
            symbol="TC.O.TWF.TX4.202607.C.42500", cp="C", strike_millipts=42_500_500
        )
        with caplog.at_level(logging.WARNING, logger="copycat.live.aggregate"):
            agg = ChainAggregator([odd])
        assert any("strike" in rec.message for rec in caplog.records)
        caplog.clear()
        agg.route(tick(odd.symbol, price=100_000, qty=1, bid=99_000, ask=100_000))
        with caplog.at_level(logging.WARNING, logger="copycat.live.aggregate"):
            snap = agg.snapshot(series=SERIES, status="live", accumulated_from="08:45:00")
            agg.snapshot(series=SERIES, status="live", accumulated_from="08:45:00")
        assert not caplog.records  # snapshot 路徑零 warning
        assert snap["contracts"][0]["strike"] == 42500
