"""Phase B TP 機制測試(config + 模擬器)."""

from __future__ import annotations

from copycat.backtest.fade_config import (
    FadeBacktestConfig,
    FadeStopCombo,
    FadeTakeProfitCombo,
    enumerate_tp_combos,
)
from copycat.backtest.fade_simulate import (
    FadeSample,
    FadeTradeOutcome,
    simulate_fade_sample,
    simulate_fade_with_tp,
)
from copycat.data.models import Bar1K

_CFG = FadeBacktestConfig.default()
_NONE_COMBO = FadeStopCombo(
    s1_n=None,
    s1_phi=None,
    s2_m=None,
    s2_buf=None,
    s3_x=None,
    s4_x=None,
    s5_x=None,
    t1300=False,
)
_SAMPLE = FadeSample(
    stock_id="2330",
    date="2026-01-05",
    t1_date="2026-01-06",
    limit=50.0,
    t1_open=52.0,
    gap=0.04,
    broker_ids="9227",
)


def _bar(
    m: int,
    o: float,
    h: float,
    lo: float,
    c: float,
    vol: float = 100,
    up: float = 50,
    dn: float = 50,
    unch: float = 0,
) -> Bar1K:
    return Bar1K(
        m=m,
        open=o,
        high=h,
        low=lo,
        close=c,
        volume=vol,
        up_volume=up,
        down_volume=dn,
        unch_volume=unch,
    )


def _tp(tp_type: str, **kw: float) -> FadeTakeProfitCombo:
    return FadeTakeProfitCombo(tp_type, tuple(sorted(kw.items())))


# --- Config tests ---


class TestTpConfig:
    def test_enumerate_tp_combos_count(self) -> None:
        cfg = FadeBacktestConfig.default()
        combos = enumerate_tp_combos(cfg)
        expected = (
            1
            + 9
            + 6 * 6 * 5 * 5
            + 4 * 3 * 4 * 5 * 3
            + 5 * 5 * 4
            + 9 * 5
            + 8
            + 8
            + 6
            + 5 * 6 * 3
            + 4
            + 4 * 4
            + 5 * 4
        )
        assert len(combos) == expected

    def test_tp_combo_id_unique(self) -> None:
        combos = enumerate_tp_combos(FadeBacktestConfig.default())
        ids = [c.tp_id for c in combos]
        assert len(ids) == len(set(ids))

    def test_tp_combo_none(self) -> None:
        combo = FadeTakeProfitCombo(None, ())
        assert combo.tp_id == "tp=None"

    def test_tp_combo_get(self) -> None:
        combo = FadeTakeProfitCombo("tp1", (("min_profit", 0.005), ("z", 2.0)))
        assert combo.get("z") == 2.0


# --- simulate_fade_with_tp(tp=None) == simulate_fade_sample ---


class TestTpNoneEquivalence:
    def test_simulate_fade_with_tp_none_equals_original(self) -> None:
        bars = [
            _bar(0, 52.0, 53.0, 51.5, 52.5),
            _bar(1, 52.5, 52.5, 50.0, 50.5),
            _bar(2, 50.5, 51.0, 49.5, 49.8),
        ]
        r1 = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, _CFG, 1)
        r2 = simulate_fade_with_tp(bars, 0, _SAMPLE, _NONE_COMBO, None, _CFG, 1)
        assert r1 == r2


# --- TP1: volume climax ---


class TestTP1:
    def test_tp1_triggers_on_volume_spike(self) -> None:
        tp = _tp("tp1", min_profit=0.003, z=2.0, lookback=3.0, recovery=0.5)
        bars = [
            _bar(0, 52.0, 52.5, 51.5, 52.0),
            _bar(1, 52.0, 52.0, 51.0, 51.5, vol=100),
            _bar(2, 51.5, 51.5, 50.5, 51.0, vol=100),
            _bar(3, 51.0, 51.0, 50.0, 50.5, vol=100),
            _bar(
                4, 50.5, 50.8, 49.0, 50.5, vol=300
            ),  # spike: vol=300 > 100*2, new low, recovery=(50.5-49)/(50.8-49)=0.83
        ]
        r = simulate_fade_with_tp(bars, 0, _SAMPLE, _NONE_COMBO, tp, _CFG, 1)
        assert r.status == "target_hit"

    def test_tp1_no_trigger_low_volume(self) -> None:
        tp = _tp("tp1", min_profit=0.003, z=2.0, lookback=3.0, recovery=0.5)
        bars = [
            _bar(0, 52.0, 52.5, 51.5, 52.0),
            _bar(1, 52.0, 52.0, 51.0, 51.5, vol=100),
            _bar(2, 51.5, 51.5, 50.5, 51.0, vol=100),
            _bar(3, 51.0, 51.0, 50.0, 50.5, vol=100),
            _bar(4, 50.5, 50.8, 49.5, 50.5, vol=150),  # vol=150 < 100*2
        ]
        r = simulate_fade_with_tp(bars, 0, _SAMPLE, _NONE_COMBO, tp, _CFG, 1)
        assert r.status == "closeout"


# --- TP2: volume reversal after new lows ---


class TestTP2:
    def test_tp2_triggers_on_reversal(self) -> None:
        tp = _tp("tp2", trend_n=3.0, new_low_count=2.0, z=1.5, inner_flip=0.55, min_profit=0.003)
        bars = [
            _bar(0, 52.0, 52.5, 51.5, 52.0),
            _bar(1, 52.0, 52.0, 51.0, 51.5, vol=100, up=40, dn=60),
            _bar(2, 51.5, 51.5, 50.5, 51.0, vol=100, up=40, dn=60),  # new low
            _bar(3, 51.0, 51.0, 50.0, 50.5, vol=100, up=40, dn=60),  # new low
            _bar(
                4, 50.5, 51.5, 50.2, 51.2, vol=200, up=130, dn=70
            ),  # reversal: close>open, up/total=0.65>0.55
        ]
        r = simulate_fade_with_tp(bars, 0, _SAMPLE, _NONE_COMBO, tp, _CFG, 1)
        assert r.status == "target_hit"

    def test_tp2_no_trigger_no_trend(self) -> None:
        tp = _tp("tp2", trend_n=3.0, new_low_count=2.0, z=1.5, inner_flip=0.55, min_profit=0.003)
        bars = [
            _bar(0, 52.0, 52.5, 51.5, 52.0),
            _bar(1, 52.0, 52.0, 51.5, 51.8, vol=100, up=40, dn=60),
            _bar(2, 51.8, 52.0, 51.5, 51.7, vol=100, up=40, dn=60),  # no new low
            _bar(3, 51.7, 52.0, 51.5, 51.6, vol=100, up=40, dn=60),  # no new low
            _bar(4, 51.6, 52.0, 51.0, 51.8, vol=200, up=130, dn=70),
        ]
        r = simulate_fade_with_tp(bars, 0, _SAMPLE, _NONE_COMBO, tp, _CFG, 1)
        assert r.status == "closeout"


# --- TP3: deceleration ---


class TestTP3:
    def test_tp3_triggers_on_deceleration(self) -> None:
        tp = _tp("tp3", n=2.0, decel=0.5, min_profit=0.003)
        bars = [
            _bar(0, 52.0, 52.5, 51.5, 52.0),
            _bar(1, 52.0, 52.0, 50.0, 50.5),  # big drop
            _bar(2, 50.5, 50.5, 49.0, 49.2),  # big drop (prior window)
            _bar(3, 49.2, 49.2, 48.9, 49.0),  # small drop
            _bar(4, 49.0, 49.0, 48.8, 48.9),  # small drop (recent window)
            _bar(
                5, 48.9, 48.9, 48.7, 48.8
            ),  # elapsed=5 >= 2*2; recent=[bar4,bar5], prior=[bar2,bar3]
        ]
        r = simulate_fade_with_tp(bars, 0, _SAMPLE, _NONE_COMBO, tp, _CFG, 1)
        assert r.status == "target_hit"

    def test_tp3_no_trigger_still_fast(self) -> None:
        tp = _tp("tp3", n=2.0, decel=0.5, min_profit=0.003)
        bars = [
            _bar(0, 52.0, 52.5, 51.5, 52.0),
            _bar(1, 52.0, 52.0, 50.5, 51.0),
            _bar(2, 51.0, 51.0, 49.5, 50.0),
            _bar(3, 50.0, 50.0, 48.5, 49.0),
            _bar(4, 49.0, 49.0, 47.5, 48.0),
            _bar(5, 48.0, 48.0, 46.5, 47.0),  # still dropping fast
        ]
        r = simulate_fade_with_tp(bars, 0, _SAMPLE, _NONE_COMBO, tp, _CFG, 1)
        assert r.status == "closeout"


# --- TP4: consecutive new lows ---


class TestTP4:
    def test_tp4_triggers_on_consecutive_lows(self) -> None:
        tp = _tp("tp4", n=3.0, min_profit=0.003)
        bars = [
            _bar(0, 52.0, 52.5, 51.5, 52.0),
            _bar(1, 52.0, 52.0, 51.0, 51.5),
            _bar(2, 51.5, 51.5, 50.5, 51.0),  # new low
            _bar(3, 51.0, 51.0, 50.0, 50.5),  # new low
            _bar(4, 50.5, 50.5, 49.5, 50.0),  # new low -> 3 consecutive
        ]
        r = simulate_fade_with_tp(bars, 0, _SAMPLE, _NONE_COMBO, tp, _CFG, 1)
        assert r.status == "target_hit"

    def test_tp4_no_trigger_not_enough(self) -> None:
        tp = _tp("tp4", n=3.0, min_profit=0.003)
        bars = [
            _bar(0, 52.0, 52.5, 51.5, 52.0),
            _bar(1, 52.0, 52.0, 51.0, 51.5),
            _bar(2, 51.5, 51.5, 50.5, 51.0),  # new low
            _bar(3, 51.0, 51.0, 50.8, 50.9),  # not new low (50.8 > 50.5)
            _bar(4, 50.9, 50.9, 49.5, 50.0),
        ]
        r = simulate_fade_with_tp(bars, 0, _SAMPLE, _NONE_COMBO, tp, _CFG, 1)
        assert r.status == "closeout"


# --- TP5: gap fill ---


class TestTP5:
    def test_tp5_triggers_on_gap_fill(self) -> None:
        tp = _tp("tp5", fill_pct=0.5)
        # gap = 52.0 - 50.0 = 2.0; fill_level = 52.0 - 0.5*2.0 = 51.0
        bars = [
            _bar(0, 52.0, 52.5, 51.5, 52.0),
            _bar(1, 52.0, 52.0, 50.5, 51.5),  # low=50.5 < 51.0 -> fills
        ]
        r = simulate_fade_with_tp(bars, 0, _SAMPLE, _NONE_COMBO, tp, _CFG, 1)
        assert r.status == "target_hit"

    def test_tp5_no_trigger_gap_unfilled(self) -> None:
        tp = _tp("tp5", fill_pct=0.5)
        bars = [
            _bar(0, 52.0, 52.5, 51.5, 52.0),
            _bar(1, 52.0, 52.0, 51.2, 51.5),  # low=51.2 > 51.0
        ]
        r = simulate_fade_with_tp(bars, 0, _SAMPLE, _NONE_COMBO, tp, _CFG, 1)
        assert r.status == "closeout"


# --- TP6: VWAP distance ---


class TestTP6:
    def test_tp6_triggers_on_vwap_distance(self) -> None:
        tp = _tp("tp6", distance=0.01)
        # VWAP only accumulates post-trigger bars (not bar 0)
        # bar1: cum_pv=52*500=26000, cum_vol=500, vwap=52.0
        # bar2: cum_pv=26000+49*500=50500, cum_vol=1000, vwap=50.5; dist=(50.5-49)/50.5=0.030 > 0.01
        bars = [
            _bar(0, 52.0, 52.5, 51.5, 52.0, vol=1000),
            _bar(1, 52.0, 52.0, 51.0, 52.0, vol=500),
            _bar(2, 51.0, 51.0, 48.5, 49.0, vol=500),
        ]
        r = simulate_fade_with_tp(bars, 0, _SAMPLE, _NONE_COMBO, tp, _CFG, 1)
        assert r.status == "target_hit"

    def test_tp6_no_trigger_near_vwap(self) -> None:
        tp = _tp("tp6", distance=0.05)
        bars = [
            _bar(0, 52.0, 52.5, 51.5, 52.0, vol=1000),
            _bar(1, 52.0, 52.0, 51.5, 51.8, vol=1000),  # close near vwap
        ]
        r = simulate_fade_with_tp(bars, 0, _SAMPLE, _NONE_COMBO, tp, _CFG, 1)
        assert r.status == "closeout"


# --- TP7: range capture ---


class TestTP7:
    def test_tp7_triggers_on_range_capture(self) -> None:
        tp = _tp("tp7", capture=0.5)
        # entry ~ 51.9; bars: high=52.5, low=49.5 -> range=3.0; profit=51.9-49.8=2.1; capture=2.1/3.0=0.7 > 0.5
        bars = [
            _bar(0, 52.0, 52.5, 51.5, 52.0),
            _bar(1, 52.0, 52.0, 49.5, 49.8),
        ]
        r = simulate_fade_with_tp(bars, 0, _SAMPLE, _NONE_COMBO, tp, _CFG, 1)
        assert r.status == "target_hit"

    def test_tp7_no_trigger_small_capture(self) -> None:
        tp = _tp("tp7", capture=0.8)
        bars = [
            _bar(0, 52.0, 52.5, 51.5, 52.0),
            _bar(1, 52.0, 52.0, 51.0, 51.5),  # small capture
        ]
        r = simulate_fade_with_tp(bars, 0, _SAMPLE, _NONE_COMBO, tp, _CFG, 1)
        assert r.status == "closeout"


# --- TP8: inner ratio flip ---


class TestTP8:
    def test_tp8_triggers_on_inner_flip(self) -> None:
        tp = _tp("tp8", n=1.0, threshold=0.6, min_profit=0.003)
        bars = [
            _bar(0, 52.0, 52.5, 51.5, 52.0),
            _bar(1, 52.0, 52.0, 50.0, 50.5, up=30, dn=70),  # profitable
            _bar(2, 50.5, 51.0, 49.5, 50.0, up=80, dn=20),  # up ratio=0.8 > 0.6
        ]
        r = simulate_fade_with_tp(bars, 0, _SAMPLE, _NONE_COMBO, tp, _CFG, 1)
        assert r.status == "target_hit"

    def test_tp8_no_trigger_still_selling(self) -> None:
        tp = _tp("tp8", n=1.0, threshold=0.6, min_profit=0.003)
        bars = [
            _bar(0, 52.0, 52.5, 51.5, 52.0),
            _bar(1, 52.0, 52.0, 50.0, 50.5, up=30, dn=70),
            _bar(2, 50.5, 51.0, 49.5, 50.0, up=30, dn=70),  # still selling
        ]
        r = simulate_fade_with_tp(bars, 0, _SAMPLE, _NONE_COMBO, tp, _CFG, 1)
        assert r.status == "closeout"


# --- TP9: cumulative delta flip ---


class TestTP9:
    def test_tp9_triggers_on_delta_flip(self) -> None:
        tp = _tp("tp9", min_profit=0.003)
        bars = [
            _bar(0, 52.0, 52.5, 51.5, 52.0),
            _bar(1, 52.0, 52.0, 50.0, 50.5, up=30, dn=70),  # delta = -40
            _bar(2, 50.5, 51.0, 49.5, 50.0, up=80, dn=20),  # delta = -40+60 = +20 -> flip
        ]
        r = simulate_fade_with_tp(bars, 0, _SAMPLE, _NONE_COMBO, tp, _CFG, 1)
        assert r.status == "target_hit"

    def test_tp9_no_trigger_delta_negative(self) -> None:
        tp = _tp("tp9", min_profit=0.003)
        bars = [
            _bar(0, 52.0, 52.5, 51.5, 52.0),
            _bar(1, 52.0, 52.0, 50.0, 50.5, up=30, dn=70),
            _bar(2, 50.5, 51.0, 49.5, 50.0, up=30, dn=70),  # delta still negative
        ]
        r = simulate_fade_with_tp(bars, 0, _SAMPLE, _NONE_COMBO, tp, _CFG, 1)
        assert r.status == "closeout"


# --- TP10: long lower wick ---


class TestTP10:
    def test_tp10_triggers_on_long_wick(self) -> None:
        tp = _tp("tp10", wick=0.6, min_profit=0.003)
        bars = [
            _bar(0, 52.0, 52.5, 51.5, 52.0),
            _bar(1, 52.0, 52.0, 50.0, 50.5),  # establish running_low=50.0
            _bar(
                2, 50.5, 50.8, 49.5, 50.5
            ),  # new low=49.5, wick=(50.5-49.5)/(50.8-49.5)=0.77 > 0.6
        ]
        r = simulate_fade_with_tp(bars, 0, _SAMPLE, _NONE_COMBO, tp, _CFG, 1)
        assert r.status == "target_hit"

    def test_tp10_no_trigger_short_wick(self) -> None:
        tp = _tp("tp10", wick=0.7, min_profit=0.003)
        bars = [
            _bar(0, 52.0, 52.5, 51.5, 52.0),
            _bar(1, 52.0, 52.0, 50.0, 50.5),
            _bar(2, 50.5, 50.8, 49.5, 49.6),  # wick=(49.6-49.5)/(50.8-49.5)=0.077 < 0.7
        ]
        r = simulate_fade_with_tp(bars, 0, _SAMPLE, _NONE_COMBO, tp, _CFG, 1)
        assert r.status == "closeout"


# --- TP11: time-decayed target ---


class TestTP11:
    def test_tp11_triggers_on_decayed_target(self) -> None:
        tp = _tp("tp11", initial=0.05, decay=0.90)
        # After 5 bars: target = 0.05 * 0.9^5 = 0.0295; profit = 1 - 49.8/51.9 = 0.0405 > 0.0295
        bars = [
            _bar(0, 52.0, 52.5, 51.5, 52.0),
            _bar(1, 52.0, 52.0, 51.0, 51.5),
            _bar(2, 51.5, 51.5, 50.5, 51.0),
            _bar(3, 51.0, 51.0, 50.0, 50.5),
            _bar(4, 50.5, 50.5, 49.5, 50.0),
            _bar(5, 50.0, 50.0, 49.5, 49.8),
        ]
        r = simulate_fade_with_tp(bars, 0, _SAMPLE, _NONE_COMBO, tp, _CFG, 1)
        assert r.status == "target_hit"

    def test_tp11_no_trigger_early(self) -> None:
        tp = _tp("tp11", initial=0.05, decay=0.99)
        # After 1 bar: target = 0.05 * 0.99^1 = 0.0495; profit = 1 - 51.5/51.9 = 0.0077 < 0.0495
        bars = [
            _bar(0, 52.0, 52.5, 51.5, 52.0),
            _bar(1, 52.0, 52.0, 51.0, 51.5),
        ]
        r = simulate_fade_with_tp(bars, 0, _SAMPLE, _NONE_COMBO, tp, _CFG, 1)
        assert r.status == "closeout"
