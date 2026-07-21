from __future__ import annotations

from copycat.live.stock_models import StockTick
from copycat.live.stock_state import StockDayState


def _tick(
    cum: int,
    *,
    price: int = 2_380_000,
    qty: int = 1,
    time: str = "10:57:51.000",
    side: str = "outer",
    trial: bool = False,
) -> StockTick:
    return StockTick(
        code="2330",
        price_milli=price,
        qty=qty,
        cum_vol=cum,
        time=time,
        trade_date="2026-07-21",
        side=side,
        buy_sell_flag=None,
        is_trial=trial,
    )


class TestDedup:
    def test_cum_vol_regression_dropped(self) -> None:
        st = StockDayState()
        assert st.ingest(_tick(100)) is True
        assert st.ingest(_tick(100)) is False  # equal 重送
        assert st.ingest(_tick(99)) is False  # 回退
        assert st.ingest(_tick(101)) is True

    def test_trial_dropped_before_dedup_and_does_not_touch_last_cum(self) -> None:
        st = StockDayState()
        # 試撮期 TradeVolume 為模擬值,不得墊高 max(design §2.1)
        assert st.ingest(_tick(5000, time="08:35:00.000", trial=True)) is False
        assert st.ingest(_tick(50, time="09:00:01.000")) is True  # 真開盤首筆不被 stale-drop

    def test_reset_allows_small_cum(self) -> None:
        st = StockDayState()
        st.ingest(_tick(12000))
        st.reset()
        assert st.seq == 0
        assert st.ingest(_tick(50)) is True


class TestAggregation:
    def test_minute_agg_and_vwap(self) -> None:
        st = StockDayState()
        st.ingest(_tick(10, price=2_380_000, qty=10, time="09:01:30.000", side="outer"))
        st.ingest(_tick(14, price=2_390_000, qty=4, time="09:01:59.000", side="inner"))
        st.ingest(_tick(20, price=2_400_000, qty=6, time="09:02:10.000", side="outer"))
        m1 = st.minutes[9 * 60 + 1]  # key = 台北分鐘序
        assert m1.close_milli == 2_390_000
        assert m1.volume == 14
        assert m1.outer == 10
        assert m1.inner == 4
        assert st.cum_outer == 16
        assert st.cum_inner == 4
        # VWAP = (2380*10 + 2390*4 + 2400*6) / 20 = 47760/20 = 2388.0 元
        assert st.vwap_milli == 2_388_000

    def test_snapshot_shape_and_seq(self) -> None:
        st = StockDayState()
        st.ingest(_tick(10, qty=10))
        snap = st.snapshot()
        assert snap["seq"] == 1
        assert snap["last"]["p"] == 2_380_000
        assert snap["vwap"] == 2_380_000
        assert snap["cum_outer"] == 10
        assert len(snap["ticks"]) == 1
        assert snap["minutes"]


class TestApplyBackfill:
    def test_atomic_rebuild_and_seq_jump(self) -> None:
        st = StockDayState()
        st.ingest(_tick(3, qty=3))
        ticks = [
            _tick(10, qty=10, time="09:01:00.000"),
            _tick(15, qty=5, time="09:02:00.000"),
        ]
        st.apply_backfill(ticks)
        assert st.seq > 100  # seq 跳增(design:前端跳號規則觸發 refetch)
        assert len(st.ticks) == 2
        # 回補後 live 續行:cum 接在回補 max 之後
        assert st.ingest(_tick(16)) is True
        assert st.ingest(_tick(15)) is False

    def test_backfill_skips_trial_ticks(self) -> None:
        st = StockDayState()
        st.apply_backfill([_tick(5, time="08:40:00.000", trial=True), _tick(8)])
        assert len(st.ticks) == 1

    def test_backfill_merges_live_ticks_newer_than_backfill(self) -> None:
        # 回補期間持續 ingest 的 live tick(cum > 回補上限)不得被原子重建洗掉;
        # 空回補 = 全數倖存(rollover stage2 後 TC4 尚無資料的場景)
        st = StockDayState()
        st.ingest(_tick(10, qty=10, time="09:05:00.000"))
        st.ingest(_tick(12, qty=2, time="09:05:01.000"))
        st.apply_backfill([_tick(11, qty=11, time="09:04:00.000")])
        cums = [t.cum_vol for t in st.ticks]
        assert cums == [11, 12]  # 回補列 + 倖存者(cum 10 被回補覆蓋、cum 12 保留)
        assert st.ingest(_tick(13)) is True

    def test_empty_backfill_preserves_live_state(self) -> None:
        st = StockDayState()
        st.ingest(_tick(50, qty=50, time="09:00:01.000"))
        st.apply_backfill([])
        assert st.last is not None
        assert st.last.cum_vol == 50
