"""round 3 模擬器:ratchet 結構停損 / 回落式災難停損 / exit_reason 歸因
(change-spec §9.2;新參數預設 = 舊行為 bit-for-bit)."""

from __future__ import annotations

import pytest

from copycat.backtest.fade_config import FadeBacktestConfig, FadeStopCombo
from copycat.backtest.fade_simulate import FadeSample, simulate_fade_sample
from copycat.data.models import Bar1K
from copycat.market import tick_size

_SAMPLE = FadeSample(
    stock_id="2330",
    date="2026-01-05",
    t1_date="2026-01-06",
    limit=50.0,  # t1_limit = 55.0
    t1_open=52.0,
    gap=0.04,
    broker_ids="",
)

_NONE_COMBO = FadeStopCombo(
    s1_n=None, s1_phi=None, s2_m=None, s2_buf=None, s3_x=None, s4_x=None, s5_x=None, t1300=False
)


def _bar(m: int, o: float, h: float, lo: float, c: float, vol: float = 100) -> Bar1K:
    return Bar1K(
        m=m,
        open=o,
        high=h,
        low=lo,
        close=c,
        volume=vol,
        up_volume=50,
        down_volume=50,
        unch_volume=0,
    )


# --- ratchet 結構停損(底倉臂)---


def test_ratchet_slow_grind_never_triggers() -> None:
    cfg = FadeBacktestConfig()
    bars = [  # 每根新高皆 < prev_high×1.025 → 慢磨不觸發
        _bar(0, 52.0, 52.2, 51.8, 52.1),
        _bar(1, 52.1, 53.0, 52.0, 52.9),  # 53.0 < 52.2×1.025=53.505
        _bar(2, 52.9, 53.8, 52.8, 53.7),  # 53.8 < 53.0×1.025=54.325
        _bar(3, 53.7, 53.9, 52.0, 52.2),
    ]
    r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1, ratchet_stop_b=0.025)
    assert r.status == "closeout"


def test_ratchet_jump_over_prev_high_triggers() -> None:
    cfg = FadeBacktestConfig()
    bars = [
        _bar(0, 52.0, 52.2, 51.8, 52.1),
        _bar(1, 52.1, 53.6, 52.0, 53.5),  # 53.6 ≥ 52.2×1.025=53.505 → 觸發
        _bar(2, 53.5, 53.6, 51.0, 51.2),
    ]
    r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1, ratchet_stop_b=0.025)
    assert r.status == "guard_exit"
    assert r.exit_reason == "struct_ratchet"
    assert r.exit_m == 1
    entry = 52.1 - tick_size(52.1)
    level = 52.2 * 1.025
    # fill = max(level, close=53.5) = 53.505
    assert r.pnl_rate is not None
    assert abs(r.pnl_rate - (1.0 - max(level, 53.5) / entry - 0.001425 * 2 - 0.0015)) < 1e-9


def test_ratchet_none_equals_legacy() -> None:
    cfg = FadeBacktestConfig()
    bars = [
        _bar(0, 52.0, 52.2, 51.8, 52.1),
        _bar(1, 52.1, 53.6, 52.0, 53.5),
        _bar(2, 53.5, 53.6, 51.0, 51.2),
    ]
    legacy = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1)
    explicit = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1, ratchet_stop_b=None)
    assert legacy == explicit
    assert legacy.status == "closeout"


# --- 回落式災難停損 ---

_RETRACE_CFG = FadeBacktestConfig(disaster_arm_x=0.06, disaster_retrace_r=0.02)


def test_disaster_retrace_not_armed_no_trigger() -> None:
    bars = [  # 最高 52.5 < entry(≈49.9)×1.06=52.89 → 未武裝,回落不出場
        _bar(0, 50.0, 50.2, 49.8, 50.0),
        _bar(1, 50.0, 52.5, 49.9, 52.4),
        _bar(2, 52.4, 52.4, 49.5, 49.6),
    ]
    r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, _RETRACE_CFG, 1)
    assert r.status == "closeout"
    assert r.exit_reason is None


def test_disaster_retrace_same_bar_spike_does_not_trigger() -> None:
    # entry ≈ 49.95;bar1 衝 54.0(≥ entry×1.06=52.95)同 bar 深回落——prev-high 語意:
    # 武裝與 level 用前一 bar 為止的 high(50.2),bar1 不觸發;bar2 才以 54.0 錨觸發。
    bars = [
        _bar(0, 50.0, 50.2, 49.8, 50.0),
        _bar(1, 50.0, 54.0, 49.7, 49.8),  # 同 bar 衝高+回落 → 不觸發(只更新錨)
        _bar(2, 49.8, 50.0, 49.0, 49.2),  # prev_high=54.0 已武裝;low ≤ 54×0.98=52.92 → 觸發
    ]
    r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, _RETRACE_CFG, 1)
    assert r.status == "guard_exit"
    assert r.exit_reason == "disaster_retrace"
    assert r.exit_m == 2
    entry = 50.0 - tick_size(50.0)
    level = 54.0 * 0.98
    assert r.pnl_rate is not None
    assert abs(r.pnl_rate - (1.0 - level / entry - 0.001425 * 2 - 0.0015)) < 1e-9


def test_disaster_retrace_locked_bar_updates_anchor_but_no_trigger() -> None:
    # bar1 鎖死(low ≥ 55):凍結不出場但更新錨;bar2 解鎖回落 → 以 55.0 錨觸發
    bars = [
        _bar(0, 50.0, 50.2, 49.8, 50.0),
        _bar(1, 55.0, 55.0, 55.0, 55.0),  # 鎖死凍結 bar
        _bar(2, 54.5, 54.6, 53.0, 53.2),  # low 53.0 ≤ 55×0.98=53.9 → 觸發
    ]
    r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, _RETRACE_CFG, 1)
    assert r.status == "guard_exit"
    assert r.exit_reason == "disaster_retrace"
    assert r.pnl_rate is not None
    level = 55.0 * 0.98
    entry = 50.0 - tick_size(50.0)
    assert abs(r.pnl_rate - (1.0 - level / entry - 0.001425 * 2 - 0.0015)) < 1e-9


def test_disaster_retrace_conflicts_with_stop_takes_worst() -> None:
    # 同 bar:S4 停損(entry×1.10 不可行,改 fixed_stop)與災難回落同時 → 取最高回補價
    cfg = FadeBacktestConfig(disaster_arm_x=0.03, disaster_retrace_r=0.02)
    bars = [
        _bar(0, 50.0, 50.2, 49.8, 50.0),
        _bar(1, 50.0, 52.0, 49.9, 51.9),  # prev 錨 50.2 → bar1 收盤後錨 52.0(≥ entry×1.03)
        _bar(2, 51.9, 53.0, 50.5, 52.8),  # 災難 level 52×0.98=50.96 觸發;fixed_stop 52.5 也觸發
    ]
    r = simulate_fade_sample(
        bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1, fixed_stop_level=52.5
    )
    assert r.status == "guard_exit"
    # worst = max(fixed fill=max(52.5, close 52.8)=52.8, 災難 level 50.96)→ fixed 側
    assert r.exit_reason == "struct_fixed"
    entry = 50.0 - tick_size(50.0)
    assert r.pnl_rate is not None
    assert abs(r.pnl_rate - (1.0 - 52.8 / entry - 0.001425 * 2 - 0.0015)) < 1e-9


def test_disaster_x_and_retrace_engine_fail_fast() -> None:
    cfg = FadeBacktestConfig(disaster_x=0.04)
    bad = __import__("dataclasses").replace(cfg, disaster_arm_x=0.06, disaster_retrace_r=0.02)
    bars = [_bar(0, 50.0, 50.2, 49.8, 50.0), _bar(1, 50.0, 50.5, 49.5, 49.6)]
    with pytest.raises(ValueError, match="互斥"):
        simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, bad, 1)


# --- exit_reason 歸因 ---


def test_hardline_exit_reason() -> None:
    cfg = FadeBacktestConfig(guard_limit_dist=0.03)  # guard_level = 55×0.97 = 53.35
    bars = [
        _bar(0, 52.0, 52.2, 51.8, 52.0),
        _bar(1, 52.0, 53.5, 51.9, 53.3),  # high ≥ 53.35 → guard
        _bar(2, 53.3, 53.4, 52.0, 52.1),
    ]
    r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1)
    assert r.status == "guard_exit"
    assert r.exit_reason == "hardline"


def test_fixed_stop_exit_reason() -> None:
    cfg = FadeBacktestConfig()
    bars = [
        _bar(0, 52.0, 52.2, 51.8, 52.0),
        _bar(1, 52.0, 53.0, 51.9, 52.5),  # ≥ fixed 52.8 → struct_fixed
        _bar(2, 52.5, 52.6, 52.0, 52.1),
    ]
    r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1, fixed_stop_level=52.8)
    assert r.status == "guard_exit"
    assert r.exit_reason == "struct_fixed"


def test_legacy_disaster_x_exit_reason() -> None:
    cfg = FadeBacktestConfig(disaster_x=0.02)
    bars = [
        _bar(0, 52.0, 52.2, 51.8, 52.0),
        _bar(1, 52.0, 53.2, 51.9, 53.1),  # entry 51.95×1.02=52.989 → 觸發
        _bar(2, 53.1, 53.2, 52.0, 52.1),
    ]
    r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1)
    assert r.status == "guard_exit"
    assert r.exit_reason == "disaster_x"


def test_same_price_priority_hardline_over_struct() -> None:
    # guard_level 與 fixed_stop 同價:成交同 → 歸因 hardline(優先序)
    cfg = FadeBacktestConfig(guard_limit_dist=0.03)  # 53.35
    bars = [
        _bar(0, 52.0, 52.2, 51.8, 52.0),
        _bar(1, 52.0, 53.5, 51.9, 53.2),
        _bar(2, 53.2, 53.3, 52.0, 52.1),
    ]
    r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1, fixed_stop_level=53.35)
    assert r.status == "guard_exit"
    assert r.exit_reason == "hardline"


def test_non_forced_exit_reason_is_none() -> None:
    cfg = FadeBacktestConfig()
    bars = [
        _bar(0, 52.0, 52.2, 51.8, 52.0),
        _bar(1, 52.0, 52.1, 51.0, 51.1),
    ]
    r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1)
    assert r.status == "closeout"
    assert r.exit_reason is None
