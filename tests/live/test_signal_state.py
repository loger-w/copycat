"""SignalDetector 行為合約(design §3;SC-1/2/3/4/6)。

時鐘一律注入 `_Clock`(design §3.1 時間軸單一化):窗 / elapsed / cooldown / rearm
全部讀 `now_fn`,`SignalEvent.time` 只是顯示用的 tick 時刻。
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import replace

from copycat.live.signal_state import SignalDetector, TickContext
from copycat.live.stock_models import StockTick
from copycat.signals_config import SignalsConfig

_DATE = "2026-08-04"
_ALL = frozenset({"cdp_cross", "surge_crash", "vol_burst", "limit_lock"})
# 跳空幅度大的 CDP 案例用它隔離:同一批 tick 的漲跌幅同時滿足 surge/crash,
# 只開 cdp_cross 才能斷言「合併成單一事件」而不是把 surge 一起數進去。
_CDP = frozenset({"cdp_cross"})
# 真實 CDP 五線(al < nl < cdp < nh < ah);AH = 80.00 元 → tick 0.1 元、rearm 門檻 0.5 元
_BASIS = {"al": 50_000, "nl": 60_000, "cdp": 68_000, "nh": 75_000, "ah": 80_000}


class _Clock:
    def __init__(self, start: _dt.datetime | None = None) -> None:
        self.now = start if start is not None else _dt.datetime(2026, 8, 4, 10, 0, 0)

    def __call__(self) -> _dt.datetime:
        return self.now

    def advance(self, secs: float) -> None:
        self.now += _dt.timedelta(seconds=secs)


def _det(clock: _Clock, **over: float | int) -> SignalDetector:
    cfg = replace(SignalsConfig(), **over) if over else SignalsConfig()
    return SignalDetector(cfg, now_fn=clock)


def _tick(
    price: int,
    *,
    qty: int = 1,
    cum: int = 0,
    time: str = "10:00:00.123",
    trade_date: str = _DATE,
) -> StockTick:
    return StockTick(
        code="2330",
        price_milli=price,
        qty=qty,
        cum_vol=cum,
        time=time,
        trade_date=trade_date,
        side="neutral",
        is_trial=False,
    )


def _ctx(
    *,
    trade_date: str = _DATE,
    upper: int | None = None,
    lower: int | None = None,
    ask_limit: bool = True,
    bid_limit: bool = True,
    bids0_market: bool = False,
    asks0_market: bool = False,
    best_bid: int | None = None,
    best_ask: int | None = None,
    day_volume: int = 0,
) -> TickContext:
    return TickContext(
        trade_date=trade_date,
        upper_milli=upper,
        lower_milli=lower,
        ask_limit_available=ask_limit,
        bid_limit_available=bid_limit,
        bids0_is_market=bids0_market,
        asks0_is_market=asks0_market,
        best_bid_limit_milli=best_bid,
        best_ask_limit_milli=best_ask,
        day_volume=day_volume,
    )


def _locked_up(upper: int = 110_000) -> TickContext:
    """真鎖漲停簽名:ask 側無限價檔 + bids[0] 為市價佇列(design §3.5)。"""
    return _ctx(upper=upper, ask_limit=False, bids0_market=True)


def _locked_down(lower: int = 90_000) -> TickContext:
    return _ctx(lower=lower, bid_limit=False, asks0_market=True)


class TestCdpCross:
    def test_from_below_cross_ah_emits_one(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.set_basis("2330", _BASIS)
        assert det.evaluate("2330", _tick(79_000), _ctx(), _ALL) == []  # 首 tick 只初始化
        events = det.evaluate("2330", _tick(80_500), _ctx(), _ALL)
        assert len(events) == 1
        ev = events[0]
        assert ev.kind == "cdp_cross"
        assert ev.code == "2330"
        assert ev.levels == ("ah",)
        assert ev.direction == "from_below"
        assert ev.touch_count == 1
        assert ev.price_milli == 80_500
        assert ev.time == "10:00:00"
        assert ev.time_key == "10:00:00.123"

    def test_flat_below_level_no_event(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.set_basis("2330", _BASIS)
        det.evaluate("2330", _tick(79_000), _ctx(), _ALL)
        assert det.evaluate("2330", _tick(79_500), _ctx(), _ALL) == []

    def test_rearm_not_released_within_five_ticks(self) -> None:
        """AH=80.00 元 → tick 0.1 元、rearm 門檻 0.5 元;79.95 / 80.05 都在門檻內 →
        suppressed 不解除,兩個方向的重觸皆不發(cooldown 已過,只剩 rearm 擋著)。"""
        clock = _Clock()
        det = _det(clock)
        det.set_basis("2330", _BASIS)
        det.evaluate("2330", _tick(79_000), _ctx(), _ALL)
        assert len(det.evaluate("2330", _tick(80_500), _ctx(), _ALL)) == 1
        clock.advance(700)
        assert det.evaluate("2330", _tick(79_950), _ctx(), _ALL) == []  # 跌破,未解除
        assert det.evaluate("2330", _tick(80_050), _ctx(), _ALL) == []  # 再穿回,仍未解除

    def test_rearm_released_at_five_ticks(self) -> None:
        """距離門檻仍是 5 × 0.1 元,但解除多一道「連續線外滿 `cdp_rearm_dwell_secs`」
        (SC-1;預設 300s)。穿越當筆 80.50 已距 AH 0.5 元 → 駐留自該筆起算:
        100s 時 79.50 雖已離線 5 tick 仍不解除,700s 後才解除,重觸照發。"""
        clock = _Clock()
        det = _det(clock)
        det.set_basis("2330", _BASIS)
        det.evaluate("2330", _tick(79_000), _ctx(), _ALL)
        det.evaluate("2330", _tick(80_500), _ctx(), _ALL)
        clock.advance(100)
        assert det.evaluate("2330", _tick(79_500), _ctx(), _ALL) == []  # 駐留未滿 300s
        clock.advance(600)
        events = det.evaluate("2330", _tick(80_500), _ctx(), _ALL)
        assert len(events) == 1
        assert events[0].levels == ("ah",)
        assert events[0].direction == "from_below"
        assert events[0].touch_count == 2

    def test_dwell_resets_when_price_returns_inside_band(self) -> None:
        """線外 260s 後回到帶內 → 駐留歸零重算(SC-1 edge 2):冷卻早過了也不解除,
        要再從歸零後那筆線外 tick 起連續滿 300s。"""
        clock = _Clock()
        det = _det(clock)
        det.set_basis("2330", _BASIS)
        det.evaluate("2330", _tick(79_000), _ctx(), _CDP)
        det.evaluate("2330", _tick(80_500), _ctx(), _CDP)  # 穿 AH,駐留自此起算
        clock.advance(250)
        assert det.evaluate("2330", _tick(80_600), _ctx(), _CDP) == []  # 線外 250s
        clock.advance(10)
        assert det.evaluate("2330", _tick(80_100), _ctx(), _CDP) == []  # 回帶內 → 歸零
        clock.advance(400)  # 距首次穿越 660s(冷卻已過),但駐留自本筆才重新起算
        assert det.evaluate("2330", _tick(79_500), _ctx(), _CDP) == []
        clock.advance(300)
        events = det.evaluate("2330", _tick(80_500), _ctx(), _CDP)
        assert [e.levels for e in events] == [("ah",)]

    def test_dwell_zero_releases_immediately(self) -> None:
        """W3:`cdp_rearm_dwell_secs = 0` 完全等於現行「離線即解除」。"""
        clock = _Clock()
        det = _det(clock, cdp_rearm_dwell_secs=0.0, cdp_cooldown_secs=0.0)
        det.set_basis("2330", _BASIS)
        det.evaluate("2330", _tick(79_000), _ctx(), _ALL)
        det.evaluate("2330", _tick(80_500), _ctx(), _ALL)
        clock.advance(10)
        events = det.evaluate("2330", _tick(79_500), _ctx(), _ALL)
        assert len(events) == 1
        assert events[0].direction == "from_above"
        assert events[0].touch_count == 2

    def test_dwell_starts_at_crossing_tick_when_outside_band(self) -> None:
        """跳空穿越:寫入 suppressed 的當筆已距線 ≥ gap → 駐留自該筆起算,
        不必等下一筆線外 tick(SC-1 起算時點)。"""
        clock = _Clock()
        det = _det(clock)
        det.set_basis("2330", _BASIS)
        det.evaluate("2330", _tick(79_000), _ctx(), _CDP)
        det.evaluate("2330", _tick(85_000), _ctx(), _CDP)  # 距 AH 5 元 ≫ gap
        clock.advance(700)  # 冷卻 600 + 駐留 300 都靠這一筆的起算滿足
        events = det.evaluate("2330", _tick(79_000), _ctx(), _CDP)
        assert len(events) == 1
        assert events[0].levels == ("ah",)
        assert events[0].direction == "from_above"

    def test_dwell_starts_at_first_outside_tick_when_cross_inside_band(self) -> None:
        """穿越當筆仍在帶內(80.10 距 AH 0.1 元 < 0.5 元)→ 起算值 None,
        之後第一筆線外 tick 才起算。"""
        clock = _Clock()
        det = _det(clock)
        det.set_basis("2330", _BASIS)
        det.evaluate("2330", _tick(79_000), _ctx(), _CDP)
        det.evaluate("2330", _tick(80_100), _ctx(), _CDP)  # 穿 AH 但仍貼線
        clock.advance(700)
        assert det.evaluate("2330", _tick(79_900), _ctx(), _CDP) == []  # 帶內 → 未起算
        clock.advance(10)
        assert det.evaluate("2330", _tick(79_400), _ctx(), _CDP) == []  # 線外首筆 → 起算
        clock.advance(300)
        events = det.evaluate("2330", _tick(80_500), _ctx(), _CDP)
        assert [e.levels for e in events] == [("ah",)]

    def test_touch_line_is_not_a_cross(self) -> None:
        """SC-2:price == 線價是「線上」,不觸發也不改變側別。"""
        clock = _Clock()
        det = _det(clock)
        det.set_basis("2330", _BASIS)
        det.evaluate("2330", _tick(79_000), _ctx(), _CDP)
        assert det.evaluate("2330", _tick(80_000), _ctx(), _CDP) == []

    def test_cross_through_line_point_emits_once(self) -> None:
        """逐 tick 走過線價(79.50 → 80.00 → 80.50)仍算一次 from_below —— 事件落在
        真正到達線另一側的那一筆。"""
        clock = _Clock()
        det = _det(clock)
        det.set_basis("2330", _BASIS)
        det.evaluate("2330", _tick(79_500), _ctx(), _CDP)
        assert det.evaluate("2330", _tick(80_000), _ctx(), _CDP) == []
        events = det.evaluate("2330", _tick(80_500), _ctx(), _CDP)
        assert len(events) == 1
        assert events[0].levels == ("ah",)
        assert events[0].direction == "from_below"

    def test_touching_line_round_trip_no_event(self) -> None:
        """80.00(線上)→ 79.50 → 80.00 → 79.50:全程只在線下與線上之間來回,
        沒有到過線的另一側 → 一則都不發(user 指名的噪音樣態)。"""
        clock = _Clock()
        det = _det(clock)
        det.set_basis("2330", _BASIS)
        det.evaluate("2330", _tick(80_000), _ctx(), _CDP)
        assert det.evaluate("2330", _tick(79_500), _ctx(), _CDP) == []
        assert det.evaluate("2330", _tick(80_000), _ctx(), _CDP) == []
        assert det.evaluate("2330", _tick(79_500), _ctx(), _CDP) == []

    def test_basis_reset_midday_does_not_fake_cross(self) -> None:
        """SC-2 edge 3:`set_basis` 換了線價 → 舊側別連同舊線價一起失效(不會把
        「在 80.00 之上」當成「在 79.00 之上」),首筆不假發;新線的真穿越照發。"""
        clock = _Clock()
        det = _det(clock)
        det.set_basis("2330", {"ah": 80_000})
        det.evaluate("2330", _tick(79_000), _ctx(), _CDP)
        assert det.evaluate("2330", _tick(79_500), _ctx(), _CDP) == []  # 線下,側別 = −1
        det.set_basis("2330", {"ah": 79_000})  # 盤中重設:價格現在在新線之上
        assert det.evaluate("2330", _tick(79_500), _ctx(), _CDP) == []
        events = det.evaluate("2330", _tick(78_500), _ctx(), _CDP)
        assert len(events) == 1
        assert events[0].direction == "from_above"

    def test_side_advances_while_disabled_without_backfill(self) -> None:
        """SC-2 (b):側別推進在 enabled gate 之前 —— 停用期間的穿越不發、重開也不補發,
        但重開後的反向穿越方向要對(側別在停用期間已經推進到線上方)。"""
        clock = _Clock()
        det = _det(clock)
        det.set_basis("2330", _BASIS)
        off = frozenset({"surge_crash", "vol_burst", "limit_lock"})
        det.evaluate("2330", _tick(79_000), _ctx(), off)
        assert det.evaluate("2330", _tick(80_500), _ctx(), off) == []  # 停用期間穿越
        assert det.evaluate("2330", _tick(80_600), _ctx(), _CDP) == []  # 重開不補發
        events = det.evaluate("2330", _tick(79_500), _ctx(), _CDP)
        assert len(events) == 1
        assert events[0].levels == ("ah",)
        assert events[0].direction == "from_above"

    def test_cooldown_blocks_second_cross(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.set_basis("2330", _BASIS)
        det.evaluate("2330", _tick(79_000), _ctx(), _ALL)
        det.evaluate("2330", _tick(80_500), _ctx(), _ALL)
        clock.advance(100)
        assert det.evaluate("2330", _tick(79_500), _ctx(), _ALL) == []  # 駐留未滿,仍 suppressed
        assert det.evaluate("2330", _tick(80_500), _ctx(), _ALL) == []  # 仍在 600s cooldown

    def test_same_tick_merges_levels_ascending(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.set_basis("2330", _BASIS)
        det.evaluate("2330", _tick(70_000), _ctx(), _CDP)
        events = det.evaluate("2330", _tick(85_000), _ctx(), _CDP)
        assert len(events) == 1
        assert events[0].levels == ("nh", "ah")  # from_below → 線價低到高
        assert events[0].direction == "from_below"
        assert events[0].touch_count == 1  # levels[0] 的計數

    def test_from_above_levels_descending(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.set_basis("2330", _BASIS)
        det.evaluate("2330", _tick(85_000), _ctx(), _CDP)
        events = det.evaluate("2330", _tick(70_000), _ctx(), _CDP)
        assert len(events) == 1
        assert events[0].levels == ("ah", "nh")
        assert events[0].direction == "from_above"

    def test_cooled_level_excluded_from_levels(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.set_basis("2330", _BASIS)
        det.evaluate("2330", _tick(76_000), _ctx(), _CDP)  # nh 與 ah 之間
        assert det.evaluate("2330", _tick(85_000), _ctx(), _CDP)[0].levels == ("ah",)
        # 回落同時穿 nh(新)與 ah(冷卻中)→ 只列 nh
        events = det.evaluate("2330", _tick(74_000), _ctx(), _CDP)
        assert len(events) == 1
        assert events[0].levels == ("nh",)
        assert events[0].direction == "from_above"
        # 兩線都在冷卻 → 整則不發
        assert det.evaluate("2330", _tick(85_000), _ctx(), _CDP) == []

    def test_no_basis_skips_cdp_only(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.evaluate("2330", _tick(79_000), _ctx(), _CDP)
        assert det.evaluate("2330", _tick(85_000), _ctx(), _CDP) == []  # 無基準 → 跳過 CDP
        # 其他 kind 不受影響:停用期間窗照常推進,重開後漲幅達門檻照發 surge
        clock.advance(30)
        kinds = [e.kind for e in det.evaluate("2330", _tick(90_000), _ctx(), _ALL)]
        assert kinds == ["surge"]

    def test_basis_none_skips_cdp(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.set_basis("2330", None)
        det.evaluate("2330", _tick(79_000), _ctx(), _ALL)
        assert det.evaluate("2330", _tick(80_500), _ctx(), _ALL) == []

    def test_disabled_kind_writes_no_cooldown_or_touch(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.set_basis("2330", _BASIS)
        off = frozenset({"surge_crash", "vol_burst", "limit_lock"})
        det.evaluate("2330", _tick(79_000), _ctx(), off)
        assert det.evaluate("2330", _tick(80_500), _ctx(), off) == []
        det.evaluate("2330", _tick(79_000), _ctx(), off)
        events = det.evaluate("2330", _tick(80_500), _ctx(), _ALL)
        assert len(events) == 1
        assert events[0].touch_count == 1  # 停用期間未寫入計數


class TestSurgeCrash:
    def test_surge_emits(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.evaluate("2330", _tick(100_000), _ctx(), _ALL)
        clock.advance(60)
        events = det.evaluate("2330", _tick(102_100), _ctx(), _ALL)
        assert len(events) == 1
        assert events[0].kind == "surge"
        assert events[0].pct is not None
        assert abs(events[0].pct - 2.1) < 1e-6
        assert events[0].levels == ()

    def test_crash_emits(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.evaluate("2330", _tick(100_000), _ctx(), _ALL)
        clock.advance(60)
        events = det.evaluate("2330", _tick(97_900), _ctx(), _ALL)
        assert len(events) == 1
        assert events[0].kind == "crash"
        assert events[0].pct is not None
        assert events[0].pct < 0

    def test_below_threshold_no_event(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.evaluate("2330", _tick(100_000), _ctx(), _ALL)
        clock.advance(60)
        assert det.evaluate("2330", _tick(101_900), _ctx(), _ALL) == []

    def test_cooldown_blocks_second_surge(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.evaluate("2330", _tick(100_000), _ctx(), _ALL)
        clock.advance(60)
        assert len(det.evaluate("2330", _tick(102_100), _ctx(), _ALL)) == 1
        clock.advance(60)
        assert det.evaluate("2330", _tick(105_000), _ctx(), _ALL) == []

    def test_crash_blocked_by_surge_cooldown(self) -> None:
        """SC-3:同 code 的爆拉 / 爆跌共用一個冷卻桶 —— 拉上去又摔下來是同一段行情,
        兩則訊號的資訊量不獨立。"""
        clock = _Clock()
        det = _det(clock)
        det.evaluate("2330", _tick(100_000), _ctx(), _ALL)
        clock.advance(60)
        assert [e.kind for e in det.evaluate("2330", _tick(102_100), _ctx(), _ALL)] == ["surge"]
        clock.advance(60)
        assert det.evaluate("2330", _tick(97_900), _ctx(), _ALL) == []

    def test_crash_after_shared_cooldown_expires(self) -> None:
        """共用桶滿 1800s 後照發,且 `touch_count` 仍分 kind 計。"""
        clock = _Clock()
        det = _det(clock)
        det.evaluate("2330", _tick(100_000), _ctx(), _ALL)
        clock.advance(60)
        assert [e.kind for e in det.evaluate("2330", _tick(102_100), _ctx(), _ALL)] == ["surge"]
        clock.advance(1741)  # 距 surge 1741s;窗內舊點已被裁掉,本筆只重建窗
        assert det.evaluate("2330", _tick(100_000), _ctx(), _ALL) == []
        clock.advance(60)  # 距 surge 1801s
        events = det.evaluate("2330", _tick(97_900), _ctx(), _ALL)
        assert [e.kind for e in events] == ["crash"]
        assert events[0].touch_count == 1

    def test_window_trims_old_points(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.evaluate("2330", _tick(100_000), _ctx(), _ALL)
        clock.advance(60)
        det.evaluate("2330", _tick(101_000), _ctx(), _ALL)
        clock.advance(280)  # 首點已出 300s 窗,窗內最舊 = 101_000
        assert det.evaluate("2330", _tick(102_100), _ctx(), _ALL) == []


class TestVolumeBurst:
    def test_vol_burst_emits(self) -> None:
        clock = _Clock(_dt.datetime(2026, 8, 4, 9, 30, 0))
        det = _det(clock)
        det.evaluate("2330", _tick(100_000, qty=1, cum=400), _ctx(day_volume=400), _ALL)
        clock.advance(10)
        events = det.evaluate(
            "2330", _tick(100_000, qty=600, cum=1_000), _ctx(day_volume=1_000), _ALL
        )
        assert len(events) == 1
        assert events[0].kind == "vol_burst"
        assert events[0].pct is not None
        assert events[0].pct >= 3.0

    def test_before_min_elapsed_no_event(self) -> None:
        clock = _Clock(_dt.datetime(2026, 8, 4, 9, 10, 0))
        det = _det(clock)
        det.evaluate("2330", _tick(100_000, qty=1, cum=400), _ctx(day_volume=400), _ALL)
        clock.advance(10)
        assert (
            det.evaluate("2330", _tick(100_000, qty=600, cum=1_000), _ctx(day_volume=1_000), _ALL)
            == []
        )

    def test_low_volume_stock_no_event(self) -> None:
        clock = _Clock(_dt.datetime(2026, 8, 4, 9, 30, 0))
        det = _det(clock)
        det.evaluate("2330", _tick(100_000, qty=1, cum=5), _ctx(day_volume=5), _ALL)
        clock.advance(10)
        assert det.evaluate("2330", _tick(100_000, qty=5, cum=10), _ctx(day_volume=10), _ALL) == []

    def test_vol_burst_still_fires_when_surge_disabled(self) -> None:
        clock = _Clock(_dt.datetime(2026, 8, 4, 9, 30, 0))
        det = _det(clock)
        off = frozenset({"cdp_cross", "vol_burst", "limit_lock"})
        det.evaluate("2330", _tick(100_000, qty=1, cum=400), _ctx(day_volume=400), off)
        clock.advance(10)
        events = det.evaluate(
            "2330", _tick(103_000, qty=600, cum=1_000), _ctx(day_volume=1_000), off
        )
        assert [e.kind for e in events] == ["vol_burst"]

    def test_zero_day_volume_no_event(self) -> None:
        clock = _Clock(_dt.datetime(2026, 8, 4, 9, 30, 0))
        det = _det(clock)
        det.evaluate("2330", _tick(100_000, qty=1), _ctx(day_volume=0), _ALL)
        clock.advance(10)
        assert det.evaluate("2330", _tick(100_000, qty=600), _ctx(day_volume=0), _ALL) == []


class TestLimitLock:
    def test_composite_signature_emits_lock(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.evaluate("2330", _tick(109_000), _ctx(upper=110_000), _ALL)
        events = det.evaluate("2330", _tick(110_000), _locked_up(), _ALL)
        assert len(events) == 1
        assert events[0].kind == "limit_lock"
        assert events[0].direction == "up"
        assert events[0].price_milli == 110_000
        assert events[0].touch_count == 1

    def test_first_attack_not_lock(self) -> None:
        """首攻吃光賣盤:ask 側同樣空,但買方市價佇列未形成、最佳限價買仍在漲停價下。"""
        clock = _Clock()
        det = _det(clock)
        ctx = _ctx(upper=110_000, ask_limit=False, bids0_market=False, best_bid=109_500)
        det.evaluate("2330", _tick(109_000), _ctx(upper=110_000), _ALL)
        assert det.evaluate("2330", _tick(110_000), ctx, _ALL) == []
        # 未 latch → 之後跌回漲停價下也不會誤發 limit_open
        assert det.evaluate("2330", _tick(109_500), _ctx(upper=110_000), _ALL) == []

    def test_best_bid_at_upper_also_locks(self) -> None:
        clock = _Clock()
        det = _det(clock)
        ctx = _ctx(upper=110_000, ask_limit=False, bids0_market=False, best_bid=110_000)
        det.evaluate("2330", _tick(109_000), _ctx(upper=110_000), _ALL)
        assert det.evaluate("2330", _tick(110_000), ctx, _ALL)[0].kind == "limit_lock"

    def test_relock_same_day_no_duplicate(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.evaluate("2330", _tick(109_000), _ctx(upper=110_000), _ALL)
        assert len(det.evaluate("2330", _tick(110_000), _locked_up(), _ALL)) == 1
        assert det.evaluate("2330", _tick(110_000, qty=5), _locked_up(), _ALL) == []

    def test_limit_open_trade_path(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.evaluate("2330", _tick(109_000), _ctx(upper=110_000), _ALL)
        det.evaluate("2330", _tick(110_000), _locked_up(), _ALL)
        # 該變的 assertion:原本 advance(700) 是為了繞開「lock/open 共用桶」才等過
        # 600s;分桶後(design §3.5 amendment)open 有自己的桶,60s 就該發。
        clock.advance(60)
        events = det.evaluate("2330", _tick(109_500), _ctx(upper=110_000), _ALL)
        assert len(events) == 1
        assert events[0].kind == "limit_open"
        assert events[0].direction == "up"

    def test_lock_and_open_cooldown_buckets_are_separate(self) -> None:
        """cooldown per (code, kind, direction) 分桶(design §3.5 amendment 2026-08-04):
        鎖上後短窗內的打開不可被 lock 的冷卻吃掉;而各自的 600s 照樣擋重複。"""
        clock = _Clock()
        det = _det(clock)
        det.evaluate("2330", _tick(109_000), _ctx(upper=110_000), _ALL)
        locked = det.evaluate("2330", _tick(110_000), _locked_up(), _ALL)
        assert [e.kind for e in locked] == ["limit_lock"]

        clock.advance(60)  # 遠短於 limit_cooldown_secs(600)
        opened = det.evaluate("2330", _tick(109_500), _ctx(upper=110_000), _ALL)
        assert [e.kind for e in opened] == ["limit_open"]
        assert opened[0].touch_count == 1  # open 自己的計數,不跟 lock 混

        clock.advance(60)  # 距首次 lock 120s → limit_lock 仍在自己的 600s 內
        assert det.evaluate("2330", _tick(110_000), _locked_up(), _ALL) == []

        clock.advance(60)  # 距首次 open 120s → limit_open 也仍在自己的 600s 內
        assert det.evaluate("2330", _tick(109_500), _ctx(upper=110_000), _ALL) == []

    def test_limit_open_book_path_uses_now_fn(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.evaluate("2330", _tick(109_000), _ctx(upper=110_000), _ALL)
        det.evaluate("2330", _tick(110_000), _locked_up(), _ALL)
        # 原 advance(700) 為繞共用桶而設,分桶後多餘(下一行直接指定絕對時刻)
        clock.now = clock.now.replace(hour=13, minute=24, second=59, microsecond=250_000)
        events = det.evaluate_book("2330", _ctx(upper=110_000, ask_limit=True), _ALL)
        assert len(events) == 1
        assert events[0].kind == "limit_open"
        assert events[0].price_milli == 110_000  # 簿路無成交 → 用漲停價
        assert events[0].time_key == "13:24:59.250"
        assert events[0].time == "13:24:59"
        # latch 已解除 → 不重發
        assert det.evaluate_book("2330", _ctx(upper=110_000, ask_limit=True), _ALL) == []

    def test_book_path_respects_enabled_but_latch_moves(self) -> None:
        clock = _Clock()
        det = _det(clock)
        off = frozenset({"cdp_cross", "surge_crash", "vol_burst"})
        det.evaluate("2330", _tick(109_000), _ctx(upper=110_000), _ALL)
        det.evaluate("2330", _tick(110_000), _locked_up(), _ALL)
        clock.advance(60)  # 分桶後 open 不受 lock 冷卻影響,這裡只驗 enabled 與 latch
        assert det.evaluate_book("2330", _ctx(upper=110_000, ask_limit=True), off) == []
        # latch 照常轉移 → 重開後不會補發
        assert det.evaluate_book("2330", _ctx(upper=110_000, ask_limit=True), _ALL) == []

    def test_book_path_no_event_while_still_locked(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.evaluate("2330", _tick(109_000), _ctx(upper=110_000), _ALL)
        det.evaluate("2330", _tick(110_000), _locked_up(), _ALL)
        clock.advance(60)
        assert det.evaluate_book("2330", _locked_up(), _ALL) == []

    def test_limit_down_symmetric(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.evaluate("2330", _tick(91_000), _ctx(lower=90_000), _ALL)
        events = det.evaluate("2330", _tick(90_000), _locked_down(), _ALL)
        assert len(events) == 1
        assert events[0].kind == "limit_lock"
        assert events[0].direction == "down"
        clock.advance(60)  # 分桶後 open 有自己的桶,60s 即可發(原 700 為繞共用桶)
        opened = det.evaluate("2330", _tick(90_500), _ctx(lower=90_000), _ALL)
        assert [e.kind for e in opened] == ["limit_open"]
        assert opened[0].direction == "down"

    def test_restart_on_locked_stock_refires_once(self) -> None:
        """design §9 已接受代價:重啟後首 tick 只初始化,第二筆鎖停 tick 會重發一次。"""
        clock = _Clock()
        det = _det(clock)
        assert det.evaluate("2330", _tick(110_000), _locked_up(), _ALL) == []
        events = det.evaluate("2330", _tick(110_000, qty=3), _locked_up(), _ALL)
        assert [e.kind for e in events] == ["limit_lock"]

    def test_no_upper_skips(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.evaluate("2330", _tick(109_000), _ctx(), _ALL)
        assert (
            det.evaluate("2330", _tick(110_000), _ctx(ask_limit=False, bids0_market=True), _ALL)
            == []
        )


class TestSessionGates:
    def test_outside_window_no_event_and_no_state(self) -> None:
        clock = _Clock(_dt.datetime(2026, 8, 4, 8, 59, 59))
        det = _det(clock)
        assert det.evaluate("2330", _tick(109_000), _ctx(upper=110_000), _ALL) == []
        assert det.evaluate("2330", _tick(110_000), _locked_up(), _ALL) == []
        # 盤外未推進任何狀態 → 進窗後第一筆仍是「首 tick」
        clock.now = _dt.datetime(2026, 8, 4, 9, 0, 0)
        assert det.evaluate("2330", _tick(110_000), _locked_up(), _ALL) == []
        assert [e.kind for e in det.evaluate("2330", _tick(110_000), _locked_up(), _ALL)] == [
            "limit_lock"
        ]

    def test_close_boundary_is_exclusive(self) -> None:
        clock = _Clock(_dt.datetime(2026, 8, 4, 13, 30, 0))
        det = _det(clock)
        assert det.evaluate("2330", _tick(109_000), _ctx(upper=110_000), _ALL) == []
        assert det.evaluate_book("2330", _ctx(upper=110_000), _ALL) == []

    def test_stale_trade_date_dropped(self) -> None:
        clock = _Clock()
        det = _det(clock)
        stale = _tick(110_000, trade_date="2026-08-01")
        assert det.evaluate("2330", stale, _locked_up(), _ALL) == []
        assert det.evaluate("2330", stale, _locked_up(), _ALL) == []
        # 舊日 tick 未推進狀態 → 當日首筆仍只初始化
        assert det.evaluate("2330", _tick(110_000), _locked_up(), _ALL) == []
        assert len(det.evaluate("2330", _tick(110_000), _locked_up(), _ALL)) == 1

    def test_first_tick_only_initializes(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.set_basis("2330", _BASIS)
        assert det.evaluate("2330", _tick(85_000), _ctx(), _ALL) == []


class TestLifecycle:
    def test_reset_day_clears_everything(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.set_basis("2330", _BASIS)
        det.evaluate("2330", _tick(79_000), _ctx(), _ALL)
        det.evaluate("2330", _tick(80_500), _ctx(), _ALL)
        det.reset_day()
        # 基準清空 + 首 tick gate 回到起點
        det.evaluate("2330", _tick(79_000), _ctx(), _ALL)
        assert det.evaluate("2330", _tick(80_500), _ctx(), _ALL) == []

    def test_stage_and_swap_basis(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.stage_basis("2330", _BASIS, "2026-08-05")
        det.evaluate("2330", _tick(79_000), _ctx(), _ALL)
        assert det.evaluate("2330", _tick(80_500), _ctx(), _ALL) == []  # 暫存未生效
        det.reset_day()
        assert det.swap_staged_basis("2026-08-05") is True
        det.evaluate("2330", _tick(79_000), _ctx(), _ALL)
        assert len(det.evaluate("2330", _tick(80_500), _ctx(), _ALL)) == 1

    def test_swap_without_staged_returns_false(self) -> None:
        det = _det(_Clock())
        assert det.swap_staged_basis("2026-08-05") is False

    def test_swap_rejects_stale_staged_date(self) -> None:
        """MFS-2:暫存區帶基準日 —— 日別不符 = 上一輪換日留下的殘渣。

        沿用它不會有任何錯誤訊號,只是整天用昨天的 CDP 基準;所以要回 False(讓 hub 走
        「清空重抓」fallback)並且**把殘渣清掉**,否則下一輪又會撞上同一份。
        """
        det = _det(_Clock())
        det.stage_basis("2330", _BASIS, "2026-08-05")
        det.reset_day()

        assert det.swap_staged_basis("2026-08-06") is False
        assert det.swap_staged_basis("2026-08-05") is False

    def test_clear_all_basis(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.set_basis("2330", _BASIS)
        det.clear_all_basis()
        det.evaluate("2330", _tick(79_000), _ctx(), _ALL)
        assert det.evaluate("2330", _tick(80_500), _ctx(), _ALL) == []

    def test_drop_code_clears_only_that_code(self) -> None:
        clock = _Clock()
        det = _det(clock)
        det.set_basis("2330", _BASIS)
        det.set_basis("2317", _BASIS)
        det.evaluate("2330", _tick(79_000), _ctx(), _ALL)
        det.evaluate("2317", _tick(79_000), _ctx(), _ALL)
        det.drop_code("2330")
        assert det.evaluate("2330", _tick(80_500), _ctx(), _ALL) == []  # 回到首 tick
        assert len(det.evaluate("2317", _tick(80_500), _ctx(), _ALL)) == 1
