"""round 1 強制風控:guard / disaster / lock_penalty / 全 None 等價舊行為(SC-4)."""

from __future__ import annotations

from copycat.backtest.fade_config import FadeBacktestConfig, FadeStopCombo
from copycat.backtest.fade_optimize import _TRADEABLE as _TRADEABLE_OPT
from copycat.backtest.fade_pipeline import _TRADEABLE as _TRADEABLE_PIPE
from copycat.backtest.fade_simulate import TRADEABLE_STATUSES, FadeSample, simulate_fade_sample
from copycat.data.models import Bar1K
from copycat.market import tick_size

_TICK = tick_size(52.0)

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


def test_guard_triggers_near_limit() -> None:
    cfg = FadeBacktestConfig(guard_limit_dist=0.03)  # guard_level = 55×0.97 = 53.35
    bars = [
        _bar(0, 52.0, 52.5, 51.5, 52.0),  # entry = 52.0 − tick < 53.35
        _bar(1, 52.0, 53.5, 52.0, 53.0),  # high 53.5 >= 53.35 → guard
        _bar(2, 53.0, 53.0, 50.0, 50.5),
    ]
    r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1)
    assert r.status == "guard_exit"
    assert r.exit_m == 1
    entry = 52.0 - _TICK
    assert r.pnl_rate is not None
    assert abs(r.pnl_rate - (1.0 - 53.35 / entry - _cost(cfg))) < 1e-9  # max(level, close=53.0)


def test_guard_not_triggered_stays_in() -> None:
    cfg = FadeBacktestConfig(guard_limit_dist=0.03)
    bars = [
        _bar(0, 52.0, 52.5, 51.5, 52.0),
        _bar(1, 52.0, 53.0, 50.0, 50.5),  # high 53.0 < 53.35
    ]
    r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1)
    assert r.status == "closeout"


def test_disaster_triggers() -> None:
    cfg = FadeBacktestConfig(disaster_x=0.02)
    bars = [
        _bar(0, 50.5, 50.6, 50.0, 50.5),  # entry = 50.5 − tick = 50.4;disaster = 51.408
    ]
    bars.append(_bar(1, 50.5, 51.5, 50.4, 51.4))  # high 51.5 >= 51.408 → disaster
    r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1)
    assert r.status == "guard_exit"


def test_guard_and_s4_same_bar_takes_worst_price_with_guard_status() -> None:
    cfg = FadeBacktestConfig(guard_limit_dist=0.03)
    combo = FadeStopCombo(
        s1_n=None, s1_phi=None, s2_m=None, s2_buf=None, s3_x=None, s4_x=0.01, s5_x=None, t1300=False
    )
    bars = [
        _bar(0, 52.0, 52.5, 51.5, 52.0),  # entry 51.9;s4 level = 52.419;guard 53.35
        _bar(1, 52.0, 54.0, 52.0, 53.8),  # 兩者同 bar 觸發;worst = max(52.419, 53.35, close 53.8)
    ]
    r = simulate_fade_sample(bars, 0, _SAMPLE, combo, cfg, 1)
    assert r.status == "guard_exit"
    entry = 52.0 - _TICK
    assert r.pnl_rate is not None
    assert abs(r.pnl_rate - (1.0 - 53.8 / entry - _cost(cfg))) < 1e-9


def test_entry_inside_guard_zone_excluded() -> None:
    cfg = FadeBacktestConfig(guard_limit_dist=0.03)  # guard_level 53.35
    bars = [
        _bar(0, 54.0, 54.5, 53.5, 54.0),  # entry = 54.0 − tick >= 53.35
        _bar(1, 54.0, 54.0, 53.0, 53.2),
    ]
    r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1)
    assert r.status == "excluded_guard_at_entry"
    assert r.pnl_rate is None


def test_disaster_frozen_during_lock() -> None:
    # 鎖死凍結 bar 中 disaster 不觸發,全日鎖 → lock_penalty 語意結算(R15)
    cfg = FadeBacktestConfig(disaster_x=0.02, lock_penalty=0.03)
    bars = [
        _bar(0, 52.0, 52.5, 51.5, 52.0),
        _bar(1, 55.0, 55.0, 55.0, 55.0),  # 鎖死(low >= 55)高過 disaster,不得出場
        _bar(2, 55.0, 55.0, 55.0, 55.0),  # 全日鎖到收盤
    ]
    r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1)
    assert r.status == "locked_at_limit"
    entry = 52.0 - _TICK
    assert r.pnl_rate is not None
    assert abs(r.pnl_rate - (1.0 - 55.0 * 1.03 / entry - _cost(cfg))) < 1e-9


def test_lock_penalty_none_keeps_legacy_price() -> None:
    cfg = FadeBacktestConfig()
    bars = [
        _bar(0, 52.0, 52.5, 51.5, 52.0),
        _bar(1, 55.0, 55.0, 55.0, 55.0),
    ]
    r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1)
    assert r.status == "locked_at_limit"
    entry = 52.0 - _TICK
    assert r.pnl_rate is not None
    assert abs(r.pnl_rate - (1.0 - 55.0 / entry - _cost(cfg))) < 1e-9


def test_all_none_equals_legacy_output() -> None:
    cfg = FadeBacktestConfig()
    bars = [
        _bar(0, 52.0, 53.0, 51.5, 52.5),
        _bar(1, 52.5, 52.5, 50.0, 50.5),
        _bar(2, 50.5, 51.0, 49.5, 49.8),
    ]
    r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1)
    assert r.status == "closeout"
    entry = 52.5 - _TICK
    assert r.pnl_rate is not None
    assert abs(r.pnl_rate - (1.0 - 49.8 / entry - _cost(cfg))) < 1e-9


def test_tradeable_statuses_single_source_of_truth() -> None:
    assert _TRADEABLE_PIPE is TRADEABLE_STATUSES
    assert _TRADEABLE_OPT is TRADEABLE_STATUSES
    assert "guard_exit" in TRADEABLE_STATUSES
    assert "excluded_guard_at_entry" not in TRADEABLE_STATUSES
