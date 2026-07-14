"""round 2 模擬器參數:entry_price_override / fixed_stop_level / stress_guard_fill_high
(change-spec SC-3/SC-4/SC-6;三參數預設 = 舊行為 bit-for-bit)."""

from __future__ import annotations

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


def _cost(cfg: FadeBacktestConfig) -> float:
    return cfg.fee_rate * (1 - cfg.fee_discount) * 2 + cfg.intraday_tax


def test_entry_price_override_uses_given_reference() -> None:
    cfg = FadeBacktestConfig()
    bars = [
        _bar(0, 52.0, 52.5, 51.5, 51.0),  # open 52.0 ≠ close 51.0
        _bar(1, 51.0, 51.5, 50.0, 50.5),
    ]
    r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1, entry_price_override=52.0)
    entry = 52.0 - tick_size(52.0)
    assert r.status == "closeout"
    assert r.pnl_rate is not None
    assert abs(r.pnl_rate - (1.0 - 50.5 / entry - _cost(cfg))) < 1e-9


def test_entry_price_override_none_equals_legacy() -> None:
    cfg = FadeBacktestConfig()
    bars = [
        _bar(0, 52.0, 52.5, 51.5, 51.0),
        _bar(1, 51.0, 51.5, 50.0, 50.5),
    ]
    legacy = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1)
    explicit = simulate_fade_sample(
        bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1, entry_price_override=None
    )
    assert legacy == explicit


def test_entry_price_override_respects_guard_at_entry() -> None:
    cfg = FadeBacktestConfig(guard_limit_dist=0.03)  # guard_level = 53.35
    bars = [
        _bar(0, 53.6, 53.8, 52.8, 53.0),  # close 進場 52.9 < 53.35;open 進場 53.5 >= 53.35
        _bar(1, 53.0, 53.2, 52.0, 52.5),
    ]
    by_close = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1)
    assert by_close.status != "excluded_guard_at_entry"
    by_open = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1, entry_price_override=53.6)
    assert by_open.status == "excluded_guard_at_entry"
    assert by_open.pnl_rate is None


def test_fixed_stop_level_triggers_forced_exit() -> None:
    cfg = FadeBacktestConfig()
    bars = [
        _bar(0, 52.0, 52.5, 51.5, 52.0),
        _bar(1, 52.0, 53.0, 51.8, 52.2),  # high 53.0 >= 52.8 → 強制回補 max(52.8, close 52.2)
        _bar(2, 52.2, 52.4, 50.0, 50.2),
    ]
    r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1, fixed_stop_level=52.8)
    assert r.status == "guard_exit"
    assert r.exit_m == 1
    entry = 52.0 - tick_size(52.0)
    assert r.pnl_rate is not None
    assert abs(r.pnl_rate - (1.0 - 52.8 / entry - _cost(cfg))) < 1e-9


def test_fixed_stop_level_not_triggered_runs_to_close() -> None:
    cfg = FadeBacktestConfig()
    bars = [
        _bar(0, 52.0, 52.5, 51.5, 52.0),
        _bar(1, 52.0, 52.6, 50.0, 50.5),  # high 52.6 < 52.8
    ]
    r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1, fixed_stop_level=52.8)
    assert r.status == "closeout"


def test_fixed_stop_frozen_during_lock() -> None:
    # 鎖死凍結 bar 內即使 high 超過 fixed_stop_level 也不得出場(沿 R15)
    cfg = FadeBacktestConfig(lock_penalty=0.03)
    bars = [
        _bar(0, 52.0, 52.5, 51.5, 52.0),
        _bar(1, 55.0, 55.0, 55.0, 55.0),  # 鎖死 bar,high 55 >= 52.8
        _bar(2, 55.0, 55.0, 55.0, 55.0),  # 全日鎖到收盤
    ]
    r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1, fixed_stop_level=52.8)
    assert r.status == "locked_at_limit"


def test_stress_guard_fill_high_worsens_forced_fill() -> None:
    bars = [
        _bar(0, 52.0, 52.5, 51.5, 52.0),
        _bar(1, 52.0, 54.0, 52.0, 53.0),  # guard 53.35;close 53.0 < high 54.0
    ]
    base_cfg = FadeBacktestConfig(guard_limit_dist=0.03)
    stress_cfg = FadeBacktestConfig(guard_limit_dist=0.03, stress_guard_fill_high=True)
    entry = 52.0 - tick_size(52.0)

    base = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, base_cfg, 1)
    assert base.pnl_rate is not None
    assert abs(base.pnl_rate - (1.0 - 53.35 / entry - _cost(base_cfg))) < 1e-9

    stressed = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, stress_cfg, 1)
    assert stressed.status == "guard_exit"
    assert stressed.pnl_rate is not None
    assert abs(stressed.pnl_rate - (1.0 - 54.0 / entry - _cost(stress_cfg))) < 1e-9
    assert stressed.pnl_rate < base.pnl_rate
