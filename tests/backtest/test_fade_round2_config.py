"""fade round 2 config 欄位:cells / diagnose / D5 / 壓測變體(change-spec SC-4/SC-6)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from copycat.backtest.fade_config import (
    FadeBacktestConfig,
    fade_sim_config_hash,
    load_fade_config,
)

_ROUND2 = Path(__file__).resolve().parents[2] / "configs" / "fade_uc_round2.json"


def test_round2_config_loads_all_fields() -> None:
    cfg = load_fade_config(_ROUND2)
    assert cfg.fee_discount == 0.84
    assert cfg.guard_limit_dist == 0.03
    assert cfg.disaster_x == 0.04
    assert cfg.lock_penalty == 0.03
    assert cfg.universe_daytrade_filter is True
    assert cfg.lock_penalty_grid == (0.03, 0.05, 0.07)
    assert cfg.cell_a_pullback_x == 0.008
    assert cfg.cell_a_headroom_min == 0.04
    assert cfg.cell_a_inner_thresholds == (0.45, 0.55)
    assert cfg.cell_a_window_m == 60
    assert cfg.cell_a_min_rally == 0.01
    assert cfg.cell_b_approach_dists == (0.02, 0.03)
    assert cfg.cell_b_fail_confirm == 0.01
    assert cfg.cell_b_stop_buffer == 0.005
    assert cfg.cell_c_rally_pcts == (0.03, 0.05)
    assert cfg.cell_c_pullback_x == 0.008
    assert cfg.cells_eval_segments == 4
    assert cfg.d5_min_ev == 0.01
    assert cfg.d5_min_n == 80
    assert cfg.d5_min_positive_segments == 3
    assert cfg.diagnose_perm_iters == 5000
    assert cfg.diagnose_perm_seed == 42
    assert cfg.diagnose_min_edge_pp == 0.003
    assert cfg.diagnose_p_threshold == 0.05
    assert cfg.stress_guard_fill_high is False  # 預設關閉


def test_round2_tuple_fields_load_as_tuples() -> None:
    cfg = load_fade_config(_ROUND2)
    assert isinstance(cfg.lock_penalty_grid, tuple)
    assert isinstance(cfg.cell_a_inner_thresholds, tuple)
    assert isinstance(cfg.cell_b_approach_dists, tuple)
    assert isinstance(cfg.cell_c_rally_pcts, tuple)


def test_stress_guard_fill_high_changes_sim_hash() -> None:
    base = FadeBacktestConfig.default()
    flipped = dataclasses.replace(base, stress_guard_fill_high=True)
    assert fade_sim_config_hash(base) != fade_sim_config_hash(flipped)


def test_cell_and_diagnose_params_do_not_affect_sim_hash() -> None:
    base = FadeBacktestConfig.default()
    tweaked = dataclasses.replace(
        base,
        cell_a_pullback_x=0.02,
        cell_b_stop_buffer=0.01,
        cells_eval_segments=8,
        d5_min_ev=0.05,
        diagnose_min_edge_pp=0.01,
        lock_penalty_grid=(0.09,),
    )
    assert fade_sim_config_hash(base) == fade_sim_config_hash(tweaked)


def test_round1_config_still_loads() -> None:
    round1 = _ROUND2.parent / "fade_uc_round1.json"
    cfg = load_fade_config(round1)
    assert cfg.fee_discount == 0.84
    assert cfg.wf_test_starts == ("2026-01-01", "2026-03-01", "2026-05-01", "2026-07-01")
