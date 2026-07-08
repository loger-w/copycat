"""SC-2: 7 臂竭盡點觸發定義正確性(每臂 ≥ 2 case)."""

from __future__ import annotations

from copycat.backtest.fade_arms import (
    find_trigger_delta_flip,
    find_trigger_fixed_time,
    find_trigger_inner_flip,
    find_trigger_pin_bar,
    find_trigger_pullback,
    find_trigger_vol_exhaust,
    find_trigger_vwap_break,
)
from copycat.data.models import Bar1K


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


class TestPullback:
    def test_triggers_on_pullback(self) -> None:
        bars = [
            _bar(0, 50.0, 52.0, 50.0, 51.5),  # rolling high = 52.0
            _bar(1, 51.5, 52.0, 51.0, 51.5),  # pullback = 1-51.5/52=0.96% < 1%
            _bar(2, 51.5, 51.8, 50.5, 51.0),  # pullback = 1-51.0/52=1.92% >= 1%
        ]
        assert find_trigger_pullback(bars, 0.01, max_m=30) == 2

    def test_no_trigger_within_window(self) -> None:
        bars = [
            _bar(0, 50.0, 52.0, 50.0, 51.8),
            _bar(1, 51.8, 52.0, 51.5, 51.9),  # barely any pullback
        ]
        assert find_trigger_pullback(bars, 0.01, max_m=30) is None

    def test_respects_max_m(self) -> None:
        bars = [
            _bar(0, 50.0, 52.0, 50.0, 51.5),
            _bar(31, 51.5, 51.8, 50.0, 50.5),  # pullback enough but past window
        ]
        assert find_trigger_pullback(bars, 0.01, max_m=30) is None


class TestInnerFlip:
    def test_triggers_on_selling_pressure(self) -> None:
        bars = [
            _bar(0, 50.0, 51.0, 50.0, 50.5, up=70, dn=30),
            _bar(1, 50.5, 51.0, 50.0, 50.3, up=40, dn=60),
            _bar(2, 50.3, 50.5, 49.5, 49.8, up=30, dn=70),  # 2-bar window: dn/(up+dn)=130/200=0.65
        ]
        assert find_trigger_inner_flip(bars, n_window=2, y_threshold=0.55, max_m=30) == 2

    def test_no_trigger_when_buying_dominates(self) -> None:
        bars = [
            _bar(0, 50.0, 51.0, 50.0, 50.5, up=80, dn=20),
            _bar(1, 50.5, 51.0, 50.0, 50.8, up=70, dn=30),
            _bar(2, 50.8, 51.0, 50.5, 50.9, up=60, dn=40),
        ]
        assert find_trigger_inner_flip(bars, n_window=2, y_threshold=0.55, max_m=30) is None


class TestPinBar:
    def test_triggers_on_upper_wick(self) -> None:
        bars = [
            _bar(0, 50.0, 52.0, 50.0, 51.5),  # rolling high = 52.0
            # bar 1: high=52.0, open=51.0, close=50.5 → wick = (52-51)/1.5 = 0.667
            _bar(1, 51.0, 52.0, 50.5, 50.5),
        ]
        assert find_trigger_pin_bar(bars, w_threshold=0.60, near_pct=0.005, max_m=30) == 1

    def test_no_trigger_when_not_near_high(self) -> None:
        bars = [
            _bar(0, 50.0, 55.0, 50.0, 54.0),  # rolling high = 55.0
            # bar 1 high=51.0, far from 55.0 → not near high
            _bar(1, 50.5, 51.0, 50.0, 50.2),
        ]
        assert find_trigger_pin_bar(bars, w_threshold=0.40, near_pct=0.005, max_m=30) is None

    def test_no_trigger_when_small_wick(self) -> None:
        bars = [
            _bar(0, 50.0, 52.0, 50.0, 51.8),  # rolling high = 52.0
            # bar 1: high=52.0, close=51.8 → wick = (52-51.8)/(52-51.5)=0.2/0.5=0.4
            _bar(1, 51.5, 52.0, 51.5, 51.8),
        ]
        assert find_trigger_pin_bar(bars, w_threshold=0.60, near_pct=0.005, max_m=30) is None


class TestVolExhaust:
    def test_triggers_on_volume_drop(self) -> None:
        bars = [
            _bar(0, 50.0, 52.0, 50.0, 51.5, vol=500),  # excluded from avg (i==0)
            _bar(1, 51.5, 52.0, 51.0, 51.8, vol=400),  # avg so far = 500
            _bar(2, 51.8, 52.0, 51.5, 51.9, vol=300),  # avg = (500+400)/2 = 450
            _bar(3, 51.9, 52.0, 51.8, 51.9, vol=50),  # 50/433 = 0.115 < 0.3, near high
        ]
        assert find_trigger_vol_exhaust(bars, z_ratio=0.30, near_pct=0.005, max_m=30) == 3

    def test_no_trigger_when_volume_normal(self) -> None:
        bars = [
            _bar(0, 50.0, 52.0, 50.0, 51.5, vol=100),
            _bar(1, 51.5, 52.0, 51.0, 51.8, vol=100),
            _bar(2, 51.8, 52.0, 51.5, 51.9, vol=90),  # 90/100=0.9 > 0.3
        ]
        assert find_trigger_vol_exhaust(bars, z_ratio=0.30, near_pct=0.005, max_m=30) is None


class TestDeltaFlip:
    def test_triggers_on_delta_flip(self) -> None:
        bars = [
            _bar(0, 50.0, 51.0, 50.0, 50.5, up=80, dn=20),  # delta = +60
            _bar(1, 50.5, 51.0, 50.0, 50.3, up=70, dn=30),  # delta = +60+40 = +100
            _bar(2, 50.3, 50.5, 49.5, 49.8, up=10, dn=120),  # delta = +100-110 = -10 → flip
        ]
        assert find_trigger_delta_flip(bars, max_m=30) == 2

    def test_no_trigger_when_delta_stays_positive(self) -> None:
        bars = [
            _bar(0, 50.0, 51.0, 50.0, 50.5, up=80, dn=20),
            _bar(1, 50.5, 51.0, 50.0, 50.8, up=60, dn=40),
        ]
        assert find_trigger_delta_flip(bars, max_m=30) is None


class TestVwapBreak:
    def test_triggers_on_vwap_break(self) -> None:
        bars = [
            _bar(0, 50.0, 52.0, 50.0, 51.0, vol=200),  # VWAP = 51.0
            _bar(
                1, 51.0, 51.5, 50.5, 51.2, vol=100
            ),  # VWAP = (51*200+51.2*100)/300 ≈ 51.067, above
            _bar(
                2, 51.2, 51.3, 50.0, 50.5, vol=100
            ),  # VWAP ≈ (51*200+51.2*100+50.5*100)/400 ≈ 50.925, close=50.5 < VWAP
        ]
        assert find_trigger_vwap_break(bars, max_m=30) == 2

    def test_no_trigger_when_above_vwap(self) -> None:
        bars = [
            _bar(0, 50.0, 52.0, 50.0, 51.0, vol=100),
            _bar(1, 51.0, 52.0, 50.5, 51.5, vol=100),  # stays above
        ]
        assert find_trigger_vwap_break(bars, max_m=30) is None


class TestFixedTime:
    def test_triggers_at_target(self) -> None:
        bars = [
            _bar(0, 50.0, 51.0, 50.0, 50.5),
            _bar(4, 50.5, 51.0, 50.0, 50.3),  # m=4 = 09:05
            _bar(5, 50.3, 50.5, 49.5, 49.8),
        ]
        assert find_trigger_fixed_time(bars, target_m=4) == 1

    def test_no_trigger_when_past_target(self) -> None:
        bars = [
            _bar(5, 50.0, 51.0, 50.0, 50.5),  # first bar already past m=4
        ]
        assert find_trigger_fixed_time(bars, target_m=4) is None

    def test_no_trigger_when_gap_in_bars(self) -> None:
        bars = [
            _bar(0, 50.0, 51.0, 50.0, 50.5),
            _bar(6, 50.5, 51.0, 50.0, 50.3),  # skips m=4
        ]
        assert find_trigger_fixed_time(bars, target_m=4) is None
