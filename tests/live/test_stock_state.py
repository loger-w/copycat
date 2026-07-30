from __future__ import annotations

from copycat.live.stock_models import StockMeta, StockTick
from copycat.live.stock_state import StockDayState


def _tick(
    cum: int,
    *,
    price: int = 2_380_000,
    qty: int = 1,
    time: str = "10:57:51.000",
    side: str = "outer",
    trial: bool = False,
    bid: int | None = None,
    ask: int | None = None,
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
        bid_milli=bid,
        ask_milli=ask,
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


class TestMinuteHighLow:
    """per-minute 高低(round4 項 1):分時圖要把當日高低標在**摸到的那一分鐘**上,
    而 top-level high/low 只有值沒有時間歸屬。"""

    def test_minute_high_low_tracks_intra_minute_swing(self) -> None:
        st = StockDayState()
        st.ingest(_tick(10, price=2_380_000, time="09:01:10.000"))
        st.ingest(_tick(20, price=2_395_000, time="09:01:30.000"))
        st.ingest(_tick(30, price=2_370_000, time="09:01:50.000"))
        st.ingest(_tick(40, price=2_385_000, time="09:02:10.000"))
        m1 = st.minutes[9 * 60 + 1]
        assert m1.high_milli == 2_395_000
        assert m1.low_milli == 2_370_000
        assert m1.close_milli == 2_370_000  # 收盤仍是最後一筆,與高低分離
        m2 = st.minutes[9 * 60 + 2]
        assert m2.high_milli == 2_385_000
        assert m2.low_milli == 2_385_000  # 單筆分鐘:高 = 低 = 該筆

    def test_low_default_is_none_not_zero(self) -> None:
        # 預設 0 會讓 min(0, p) 把最低價永久卡在 0(靜默錯值,畫面上就是標記黏在 0 元)
        st = StockDayState()
        st.ingest(_tick(10, price=2_380_000, time="09:01:10.000"))
        assert st.minutes[9 * 60 + 1].low_milli == 2_380_000

    def test_snapshot_minutes_carry_h_l(self) -> None:
        st = StockDayState()
        st.ingest(_tick(10, price=2_380_000, time="09:01:10.000"))
        st.ingest(_tick(20, price=2_395_000, time="09:01:30.000"))
        entry = st.snapshot()["minutes"]["541"]
        assert entry["h"] == 2_395_000
        assert entry["l"] == 2_380_000
        assert entry["c"] == 2_395_000

    def test_day_high_equals_max_of_minute_highs(self) -> None:
        """前端靠 `minute.h === accum.high` 等值反查定位 —— 這條等式必須由建構保證,
        否則標記會落空(或更糟:命中錯的分鐘)。"""
        st = StockDayState()
        st.ingest(_tick(10, price=2_380_000, time="09:01:10.000"))
        st.ingest(_tick(20, price=2_395_000, time="09:03:30.000"))
        st.ingest(_tick(30, price=2_370_000, time="09:05:50.000"))
        assert st.high_milli == max(m.high_milli or 0 for m in st.minutes.values())
        assert st.low_milli == min(m.low_milli or 0 for m in st.minutes.values())

    def test_backfill_replay_equals_incremental_ingest(self) -> None:
        """回補重放路徑也要維持等式(apply_backfill 走 _apply,不是另一條計算)。"""
        ticks = [
            _tick(10, price=2_380_000, time="09:01:10.000"),
            _tick(20, price=2_395_000, time="09:01:30.000"),
            _tick(30, price=2_370_000, time="09:01:50.000"),
        ]
        live = StockDayState()
        for t in ticks:
            live.ingest(t)
        back = StockDayState()
        back.apply_backfill(ticks)
        key = 9 * 60 + 1
        assert back.minutes[key].high_milli == live.minutes[key].high_milli == 2_395_000
        assert back.minutes[key].low_milli == live.minutes[key].low_milli == 2_370_000
        assert back.high_milli == max(m.high_milli or 0 for m in back.minutes.values())


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


class TestDayHighLow:
    """round5 項 1:當日最高 / 最低。

    資料源刻意選「後端逐 tick running max/min」而不是 TC4 的 HighPrice/LowPrice ——
    2026-07-21 個股 REALTIME probe 樣本裡沒有那兩個欄位(帶不帶沒實證),而本狀態機
    握有當日全部 tick(含回補重放),算出來是建構保證正確的。
    """

    def test_running_max_min_over_ingested_ticks(self) -> None:
        st = StockDayState()
        st.ingest(_tick(10, price=2_380_000))
        st.ingest(_tick(20, price=2_395_000))
        st.ingest(_tick(30, price=2_370_000))
        assert st.high_milli == 2_395_000
        assert st.low_milli == 2_370_000

    def test_no_ticks_leaves_none(self) -> None:
        st = StockDayState()
        assert st.high_milli is None
        assert st.low_milli is None

    def test_dropped_ticks_do_not_move_extremes(self) -> None:
        # 去重丟棄與試撮丟棄都走不到 _apply,極值不該被它們污染
        st = StockDayState()
        st.ingest(_tick(10, price=2_380_000))
        assert st.ingest(_tick(10, price=9_990_000)) is False  # cum 重送
        assert st.ingest(_tick(5, price=1_000)) is False  # cum 回退
        assert st.ingest(_tick(99, price=9_990_000, time="08:40:00.000", trial=True)) is False
        assert st.high_milli == 2_380_000
        assert st.low_milli == 2_380_000

    def test_reset_clears_extremes_but_keeps_meta(self) -> None:
        # 當日衍生狀態必須跟著 reset 清掉(W-24);book/meta 是盤外靜態值,照舊保留
        st = StockDayState()
        st.ingest(_tick(10, price=2_380_000))
        st.meta = StockMeta(
            name="台積電",
            ref_milli=2_320_000,
            upper_milli=2_550_000,
            lower_milli=2_090_000,
            y_close_milli=2_320_000,
            y_volume=45_197,
            open_time="09:00:00",
            close_time="13:30:00",
        )
        st.reset()
        assert st.high_milli is None
        assert st.low_milli is None
        assert st.meta is not None  # 盤外顯示昨收靜態值依賴它

    def test_backfill_replay_rebuilds_extremes(self) -> None:
        st = StockDayState()
        st.ingest(_tick(5, price=9_990_000))  # 會被原子重建洗掉
        st.apply_backfill(
            [
                _tick(10, price=2_400_000, time="09:01:00.000"),
                _tick(20, price=2_360_000, time="09:02:00.000"),
            ]
        )
        assert st.high_milli == 2_400_000
        assert st.low_milli == 2_360_000

    def test_snapshot_exposes_extremes_at_top_level(self) -> None:
        # 刻意放 top-level(與 vwap 同層)不放 meta:meta 是 TC4 來的靜態盤別資料,
        # 而高低是由成交推導的當日狀態;放 top-level 後 meta 為 None 時高低照樣有值
        st = StockDayState()
        st.ingest(_tick(10, price=2_380_000))
        snap = st.snapshot()
        assert snap["high"] == 2_380_000
        assert snap["low"] == 2_380_000
        assert snap["meta"] is None

    def test_snapshot_ticks_carry_bid_ask(self) -> None:
        st = StockDayState()
        st.ingest(_tick(10, bid=2_375_000, ask=2_380_000))
        assert st.snapshot()["ticks"][0]["b"] == 2_375_000
        assert st.snapshot()["ticks"][0]["a"] == 2_380_000
