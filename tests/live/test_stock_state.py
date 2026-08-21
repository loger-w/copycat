from __future__ import annotations

import json
from pathlib import Path

from copycat.live.stock_models import StockMeta, StockTick
from copycat.live.stock_state import StockDayState

#: VP 折法的跨語言 parity fixture(前端 `src/lib/vp-parity.test.ts` 讀同一個檔)
_VP_PARITY_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "vp_parity.json"


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
        m2 = st.minutes[9 * 60 + 2]
        # 全日累積走 Σ(minutes) —— `cum_outer`/`cum_inner` 欄位已隨 M3 移除
        assert m1.outer + m2.outer == 16
        assert m1.inner + m2.inner == 4
        # VWAP = (2380*10 + 2390*4 + 2400*6) / 20 = 47760/20 = 2388.0 元
        assert st.vwap_milli == 2_388_000

    def test_snapshot_shape_and_seq(self) -> None:
        st = StockDayState()
        st.ingest(_tick(10, qty=10))
        snap = st.snapshot()
        assert snap["seq"] == 1
        assert snap["last"]["p"] == 2_380_000
        assert snap["vwap"] == 2_380_000
        assert "cum_outer" not in snap  # M3:退出 wire,累積量由 minutes 還原
        assert snap["minutes"]["657"]["o"] == 10
        assert len(snap["ticks"]) == 1

    def test_snapshot_carries_vwap_denominator(self) -> None:
        """M4:vwap 的分母是「去重剔試撮後的 Σqty」,與 `last.cum_vol`(TC4 累積量)
        不同源。前端拿 cum_vol 當分母還原分子 → 兩者不等時增量 VWAP 靜默偏移,
        所以分母必須由後端顯式給。"""
        st = StockDayState()
        st.ingest(_tick(30, qty=10, price=2_380_000))
        st.ingest(_tick(31, qty=5, price=2_400_000))
        assert st.ingest(_tick(31, qty=99)) is False  # 去重丟棄不進分母
        assert st.ingest(_tick(40, qty=99, trial=True)) is False  # 試撮同理
        snap = st.snapshot()
        assert snap["vwap_vol"] == 15
        # 欄名不可再叫 `vol`(FC-2):WS `watchlist_quote` 的 `vol` 是 TC4 當日累積量
        # (= `last.cum_vol`)—— 同名反義。兩份訊息同時在前端手上,誤用哪一個都不會
        # 報錯,只會讓增量 VWAP 靜默偏移到下次全量 refetch。
        assert "vol" not in snap
        assert snap["last"]["cum_vol"] == 31  # 兩個口徑本來就不等

    def test_snapshot_omits_dead_wire_fields(self) -> None:
        """M3:cum_inner/cum_outer/meta.y_close 前端零讀取 → 退出 wire。
        內外盤累積量仍可由 `minutes` 的 i/o 還原(能量副圖本來就讀那一份)。"""
        st = StockDayState()
        st.ingest(_tick(10, qty=10, side="outer"))
        st.update_meta(
            StockMeta(
                name="台積電",
                ref_milli=2_320_000,
                upper_milli=2_550_000,
                lower_milli=2_090_000,
                y_close_milli=2_320_000,
                y_volume=100,
                open_time="09:00:00",
                close_time="13:30:00",
            )
        )
        snap = st.snapshot()
        assert "cum_inner" not in snap
        assert "cum_outer" not in snap
        assert snap["meta"] is not None
        assert "y_close" not in snap["meta"]
        assert snap["meta"]["y_vol"] == 100  # 同層仍在的欄位不受波及
        assert snap["minutes"]["657"]["o"] == 10  # 累積量的還原來源


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


class _ExplodingTick:
    """被讀任何欄位就炸 —— `tape=False` 的契約是「**跳過**逐筆展開」(D3''),不是
    「展開完再把結果丟掉」。只斷言 `ticks == []` 的話,後者照樣綠,而兩萬筆 dict 的
    建構成本(本輪要省的正是它)一分不少。"""

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"tape=False 不該讀 tick 欄位(讀了 {name})")


class TestSnapshotTape:
    """`snapshot(tape=False)`:群組檢視點卡片時沒有 tape 讀者(B15)。"""

    def test_tape_false_returns_empty_ticks_without_touching_them(self) -> None:
        st = StockDayState()
        for i in range(5):
            st.ingest(_tick(10 + i, price=2_380_000 + i * 1_000))
        full = st.snapshot()
        assert len(full["ticks"]) == 5  # 基準非空,否則兩邊都空是 vacuous
        st.ticks.append(_ExplodingTick())  # type: ignore[arg-type]
        light = st.snapshot(tape=False)
        assert light["ticks"] == []
        # tape 以外一鍵不少、一值不改(route 的 `tape=0` 只省 tape)
        assert light["seq"] == full["seq"]
        assert light["last"] == full["last"]
        assert light["vwap"] == full["vwap"]
        assert light["vwap_vol"] == full["vwap_vol"]
        assert set(light) == set(full)

    def test_default_is_full_tape(self) -> None:
        """預設值不可漂:唯一呼叫點(單檔頁)漏帶參數時要回全量,不是靜默空 tape。"""
        st = StockDayState()
        st.ingest(_tick(10))
        assert len(st.snapshot()["ticks"]) == 1


class TestLightSnapshot:
    """群組 batch 專用的輕量 payload(code review A1)。

    `group_snapshot` 對最多 50 檔、每 60s 各建一次全量 `snapshot()`,而那份會把當日
    數千筆 tick 逐筆組成 dict 之後**整份丟掉** —— 畫面只用得到 minutes / meta 兩鍵。

    抽 `_minutes_payload` / `_meta_payload` 共用而不是在 engine 那邊另寫一份對映,
    是為了讓**鍵名只有一份定義**:各寫一份的漂移樣態是前端 `meta.ref` 讀成
    undefined → `hasRef=false` → 紅綠面積與平盤線靜默消失。
    """

    def _filled(self) -> StockDayState:
        st = StockDayState()
        st.ingest(_tick(10, qty=10, price=2_380_000, time="09:01:30.000"))
        st.ingest(_tick(20, qty=5, price=2_400_000, time="09:02:10.000"))
        st.update_meta(
            StockMeta(
                name="台積電",
                ref_milli=2_320_000,
                upper_milli=2_550_000,
                lower_milli=2_090_000,
                y_close_milli=2_320_000,
                y_volume=100,
                open_time="09:00:00",
                close_time="13:30:00",
            )
        )
        return st

    def test_light_snapshot_is_exactly_minutes_and_meta(self) -> None:
        light = self._filled().light_snapshot()
        # 🔴 group-grid-full-chart:卡片要畫「完全同款」的分時圖 → VWAP 白線 / 日高低圈 /
        # VP 水平條所需的四鍵一併帶出。由 minutes 在前端近似會畫出與單檔頁不同的圖。
        assert set(light) == {"minutes", "meta", "vwap", "high", "low", "vp"}
        # ticks 仍是本輪要省掉的那一份(50 檔 × 數千筆 = 頻寬與 CPU 雙重浪費);
        # vp 是**它的聚合**(O(當日成交檔位數),與 tick 筆數脫鉤)才進得了 light
        assert "ticks" not in light

    def test_light_and_full_snapshot_share_one_key_mapping(self) -> None:
        """同一份資料兩條路產出的 minutes / meta / vwap / high / low 必須逐鍵相同 ——
        這條測試就是「單一定義」的證明;兩邊各自維護時它會第一個紅。"""
        st = self._filled()
        light = st.light_snapshot()
        full = st.snapshot()
        assert light["minutes"] == full["minutes"]
        assert light["meta"] == full["meta"]
        assert light["vwap"] == full["vwap"]
        assert light["high"] == full["high"]
        assert light["low"] == full["low"]
        assert light["minutes"]["541"]["c"] == 2_380_000  # 非空基準:比對的不是兩個空 dict
        assert light["meta"]["ref"] == 2_320_000
        assert light["vwap"] is not None  # 同上:三個 None 互等是 vacuous
        assert light["high"] == 2_400_000
        assert light["low"] == 2_380_000

    def test_light_snapshot_without_meta_is_none_not_missing(self) -> None:
        """缺 meta 回 `None` 而不是漏鍵:前端 `raw.meta ?? null` 對兩者同解,但
        route 的 response 形若少一個鍵,契約測試與 pyright 都看不出來。

        空態的 `vp` 是 `{}` 而不是 `None`:前端型別是 `Map`,兩者在 `?? new Map()`
        之後才等價,而少一個鍵時端點契約測試看不出來(同 meta 的理由)。"""
        light = StockDayState().light_snapshot()
        assert light == {
            "minutes": {},
            "meta": None,
            "vwap": None,
            "high": None,
            "low": None,
            "vp": {},
        }


class TestVolumeProfile:
    """價位別成交量(VP)由狀態機**增量維護**(change-spec AD-1 amendment R6)。

    請求時全掃 `ticks` 跑在事件迴圈上,最壞 50 檔 × 20k 筆的同步迴圈會卡住 WS fanout;
    而 `_apply` 內累加是 O(1)/tick 且 `ticks` deque 的 20k 截斷影響不到它。

    折法與前端 `stock-accum.ts::foldVp` 同規(parity fixture 鎖):剔 p<=0、
    分鐘窗 [540, 810]、key = `snap_down_milli`、cell = [總張, 外盤張, 內盤張]。
    """

    def test_ingest_accumulates_by_snapped_price(self) -> None:
        st = StockDayState()
        st.ingest(_tick(10, price=23_456, qty=8, time="09:05:00.000", side="outer"))
        st.ingest(_tick(20, price=23_450, qty=2, time="09:06:00.000", side="inner"))
        st.ingest(_tick(30, price=23_499, qty=1, time="09:07:00.000", side="neutral"))
        # 23.456 / 23.45 / 23.499 全部歸到 23.45 元那一檔;neutral 只進總張
        assert st.light_snapshot()["vp"] == {"23450": [11, 8, 2]}

    def test_market_queue_price_zero_is_dropped(self) -> None:
        """鎖漲跌停時 TC4 會推價格欄 `0` 的市價佇列 —— `snap_down_milli(0)` 是合法運算,
        不剔的話 VP 會憑空長出一個 0 元檔位(前端 `isMarketLevel` 同一條規則)。"""
        st = StockDayState()
        st.ingest(_tick(10, price=0, qty=5, time="09:05:00.000"))
        assert st.light_snapshot()["vp"] == {}

    def test_out_of_window_ticks_are_dropped(self) -> None:
        """窗 = 前端幾何的 [09:00, 13:30](含端點);盤前試撮成交與 13:31 的收盤
        撮合不進 VP,否則卡片 VP 的總張與說明列的外/內/未分類三數對不起來。"""
        st = StockDayState()
        st.ingest(_tick(10, price=99_900, qty=5, time="08:59:59.999", side="outer"))
        st.ingest(_tick(20, price=99_900, qty=7, time="13:31:00.000", side="outer"))
        assert st.light_snapshot()["vp"] == {}
        st.ingest(_tick(30, price=99_900, qty=1, time="09:00:00.000", side="outer"))
        st.ingest(_tick(40, price=99_900, qty=1, time="13:30:59.999", side="outer"))
        assert st.light_snapshot()["vp"] == {"99900": [2, 2, 0]}  # 兩個端點都在窗內

    def test_reset_clears_vp(self) -> None:
        st = StockDayState()
        st.ingest(_tick(10, price=99_900, qty=5, time="09:05:00.000", side="outer"))
        st.reset()
        assert st.light_snapshot()["vp"] == {}

    def test_apply_backfill_rebuilds_vp_identically_to_live_ingest(self) -> None:
        """回補走 reset + 重放 → VP 自然重建。這條是「增量維護」的核心風險:
        漏了 reset 就會與 live 期間的量疊加成兩倍,而畫面上只是 VP 條變長,零訊號。"""
        ticks = [
            _tick(10, price=23_456, qty=8, time="09:05:00.000", side="outer"),
            _tick(20, price=23_450, qty=2, time="09:06:00.000", side="inner"),
        ]
        live = StockDayState()
        for t in ticks:
            live.ingest(t)

        rebuilt = StockDayState()
        for t in ticks:
            rebuilt.ingest(t)  # 回補前已有 live 狀態(重疊窗)
        rebuilt.apply_backfill(ticks)
        assert rebuilt.light_snapshot()["vp"] == live.light_snapshot()["vp"]


def test_vp_parity_with_frontend_fold() -> None:
    """跨語言 parity:同一份 ticks 折出同一份直方圖(change-spec AD-2)。

    `expected` 是**手算寫死**在 fixture 裡的(不是跑程式回填),前端
    `src/lib/vp-parity.test.ts` 對同一個檔各自斷言 —— 任一邊改了規則就只有一邊紅。
    """
    fixture = json.loads(_VP_PARITY_PATH.read_text(encoding="utf-8"))
    st = StockDayState()
    for i, row in enumerate(fixture["ticks"]):
        st.ingest(_tick(i + 1, price=row["p"], qty=row["q"], time=row["t"], side=row["side"]))
    assert st.light_snapshot()["vp"] == fixture["expected"]
