"""SC-1: 空方模擬器正確性(方向反轉 + 鎖死 + S5 + 衝突)."""

from __future__ import annotations

from copycat.backtest.fade_config import FadeBacktestConfig, FadeStopCombo
from copycat.backtest.fade_simulate import FadeSample, simulate_fade_sample
from copycat.data.models import Bar1K
from copycat.market import tick_size

_CFG = FadeBacktestConfig.default()
_TICK = tick_size(52.0)  # = 0.1 for 50-100 range

_SAMPLE = FadeSample(
    stock_id="2330",
    date="2026-01-05",
    t1_date="2026-01-06",
    limit=50.0,
    t1_open=52.0,
    gap=0.04,
    broker_ids="9227",
)

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

_COST = 0.001425 * 2 + 0.0015  # 0.00435


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


def test_normal_closeout() -> None:
    bars = [
        _bar(0, 52.0, 53.0, 51.5, 52.5),
        _bar(1, 52.5, 52.5, 50.0, 50.5),
        _bar(2, 50.5, 51.0, 49.5, 49.8),
    ]
    result = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, _CFG, 1)
    assert result.status == "closeout"
    assert result.pnl_rate is not None
    entry = 52.5 - _TICK  # 52.4
    expected = 1.0 - 49.8 / entry - _COST
    assert abs(result.pnl_rate - expected) < 1e-9


def test_stopped_s4() -> None:
    combo = FadeStopCombo(
        s1_n=None,
        s1_phi=None,
        s2_m=None,
        s2_buf=None,
        s3_x=None,
        s4_x=0.03,
        s5_x=None,
        t1300=False,
    )
    bars = [
        _bar(0, 52.0, 52.5, 51.5, 52.0),
        _bar(1, 52.0, 54.0, 51.0, 53.5),
    ]
    result = simulate_fade_sample(bars, 0, _SAMPLE, combo, _CFG, 1)
    assert result.status == "stopped"
    assert result.pnl_rate is not None
    entry = 52.0 - _TICK  # 51.9
    s4_level = entry * 1.03
    exit_price = max(s4_level, 53.5)
    expected = 1.0 - exit_price / entry - _COST
    assert abs(result.pnl_rate - expected) < 1e-9
    assert result.pnl_rate < 0


def test_stopped_s3_trailing() -> None:
    combo = FadeStopCombo(
        s1_n=None,
        s1_phi=None,
        s2_m=None,
        s2_buf=None,
        s3_x=0.02,
        s4_x=None,
        s5_x=None,
        t1300=False,
    )
    bars = [
        _bar(0, 52.0, 52.5, 51.5, 52.0),  # trig, running_low = 51.5
        _bar(
            1, 51.0, 51.2, 50.0, 50.5
        ),  # running_low = 50.0; high=51.2, 50.0*1.02=51.0, 51.2>51.0 but close
        _bar(
            2, 50.5, 51.5, 49.8, 51.3
        ),  # running_low = 49.8; high=51.5, 49.8*1.02=50.796 → 51.5 > 50.796 → S3
    ]
    result = simulate_fade_sample(bars, 0, _SAMPLE, combo, _CFG, 1)
    assert result.status == "stopped"
    entry = 52.0 - _TICK  # 51.9
    # bar 1: running_low updates to 50.0, S3 level = 50.0*1.02=51.0, high=51.2 >= 51.0 → triggers on bar 1
    # Actually bar 1 already triggers. Need bar 1 high < running_low*1.02 after update.
    # running_low after bar 1 = 50.0, S3 = 51.0, bar 1 high = 51.2 >= 51.0 → yes triggers.
    # Fix: make bar 1 high lower.
    assert result.exit_m == 1  # triggers on bar 1
    s3_level = 50.0 * 1.02  # 51.0
    exit_price = max(s3_level, 50.5)  # 51.0
    expected = 1.0 - exit_price / entry - _COST
    assert result.pnl_rate is not None
    assert abs(result.pnl_rate - expected) < 1e-9


def test_stopped_s2_swing_high() -> None:
    combo = FadeStopCombo(
        s1_n=None,
        s1_phi=None,
        s2_m=3,
        s2_buf=0.005,
        s3_x=None,
        s4_x=None,
        s5_x=None,
        t1300=False,
    )
    bars = [
        _bar(0, 51.0, 52.0, 50.5, 51.5),
        _bar(1, 51.5, 53.0, 51.0, 52.5),
        _bar(2, 52.5, 52.8, 51.5, 52.0),  # trig, swing window bars[0:3] max high=53.0
        _bar(3, 52.0, 53.5, 51.5, 53.2),  # high=53.5 > 53.0*1.005=53.265
    ]
    result = simulate_fade_sample(bars, 2, _SAMPLE, combo, _CFG, 1)
    assert result.status == "stopped"
    swing = 53.0 * 1.005  # 53.265
    exit_price = max(swing, 53.2)  # 53.265
    entry = 52.0 - _TICK  # 51.9
    expected = 1.0 - exit_price / entry - _COST
    assert result.pnl_rate is not None
    assert abs(result.pnl_rate - expected) < 1e-9


def test_target_hit_s5() -> None:
    combo = FadeStopCombo(
        s1_n=None,
        s1_phi=None,
        s2_m=None,
        s2_buf=None,
        s3_x=None,
        s4_x=None,
        s5_x=0.02,
        t1300=False,
    )
    bars = [
        _bar(0, 52.0, 52.5, 51.5, 52.0),
        _bar(1, 52.0, 52.0, 50.0, 51.0),
    ]
    result = simulate_fade_sample(bars, 0, _SAMPLE, combo, _CFG, 1)
    assert result.status == "target_hit"
    entry = 52.0 - _TICK  # 51.9
    target = entry * 0.98  # 50.862
    expected = 1.0 - target / entry - _COST
    assert result.pnl_rate is not None
    assert abs(result.pnl_rate - expected) < 1e-9
    assert result.pnl_rate > 0


def test_locked_at_limit() -> None:
    t1_limit = 55.0
    bars = [
        _bar(0, 52.0, 52.5, 51.5, 52.0),
        _bar(1, 54.0, 55.0, 54.999999, 55.0),  # locked
        _bar(2, 55.0, 55.0, 55.0, 55.0),  # still locked, last bar
    ]
    result = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, _CFG, 1)
    assert result.status == "locked_at_limit"
    assert result.lock_flag is True
    entry = 52.0 - _TICK  # 51.9
    expected = 1.0 - t1_limit / entry - _COST
    assert result.pnl_rate is not None
    assert abs(result.pnl_rate - expected) < 1e-9
    assert result.pnl_rate < -0.05


def test_conflict_stop_and_target() -> None:
    combo = FadeStopCombo(
        s1_n=None,
        s1_phi=None,
        s2_m=None,
        s2_buf=None,
        s3_x=None,
        s4_x=0.02,
        s5_x=0.02,
        t1300=False,
    )
    bars = [
        _bar(0, 52.0, 52.5, 51.5, 52.0),
        _bar(1, 52.0, 54.0, 50.0, 52.0),  # both S4 and S5 hit
    ]
    result = simulate_fade_sample(bars, 0, _SAMPLE, combo, _CFG, 1)
    assert result.status == "stopped"
    entry = 52.0 - _TICK  # 51.9
    s4_level = entry * 1.02
    target = entry * 0.98
    exit_price = max(s4_level, target, 52.0)  # worst
    expected = 1.0 - exit_price / entry - _COST
    assert result.pnl_rate is not None
    assert abs(result.pnl_rate - expected) < 1e-9


def test_excluded_at_limit() -> None:
    bars = [
        _bar(0, 55.0, 55.0, 55.0, 55.0, vol=1000, up=900, dn=100),
        _bar(1, 55.0, 55.0, 55.0, 55.0),  # need 2nd bar so lastbar doesn't fire first
    ]
    sample = FadeSample(
        stock_id="2330",
        date="2026-01-05",
        t1_date="2026-01-06",
        limit=50.0,
        t1_open=55.0,
        gap=0.10,
        broker_ids="9227",
    )
    result = simulate_fade_sample(bars, 0, sample, _NONE_COMBO, _CFG, 1)
    assert result.status == "excluded_at_limit"
    assert result.pnl_rate is None


def test_excluded_lastbar() -> None:
    bars = [
        _bar(269, 52.0, 52.5, 51.5, 52.0),
    ]
    result = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, _CFG, 1)
    assert result.status == "excluded_lastbar"
    assert result.pnl_rate is None


def test_s1_outer_ratio_direction() -> None:
    combo = FadeStopCombo(
        s1_n=2,
        s1_phi=0.55,
        s2_m=None,
        s2_buf=None,
        s3_x=None,
        s4_x=None,
        s5_x=None,
        t1300=False,
    )
    bars = [
        _bar(0, 52.0, 52.5, 51.5, 52.0),
        _bar(1, 52.0, 52.2, 51.8, 52.1, up=70, dn=30),
        _bar(2, 52.1, 52.3, 51.9, 52.2, up=60, dn=40),
    ]
    result = simulate_fade_sample(bars, 0, _SAMPLE, combo, _CFG, 1)
    assert result.status == "stopped"

    bars_low = [
        _bar(0, 52.0, 52.5, 51.5, 52.0),
        _bar(1, 52.0, 52.2, 51.8, 52.1, up=30, dn=70),
        _bar(2, 52.1, 52.3, 51.9, 52.2, up=20, dn=80),
        _bar(3, 52.0, 52.1, 51.0, 51.2),
    ]
    result2 = simulate_fade_sample(bars_low, 0, _SAMPLE, combo, _CFG, 1)
    assert result2.status == "closeout"
