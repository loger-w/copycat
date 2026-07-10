"""round 1 config 欄位:載入、tuple 轉換、hash 失效、預設等價舊行為."""

from __future__ import annotations

import json
from pathlib import Path

from copycat.backtest.fade_config import (
    FadeBacktestConfig,
    fade_sim_config_hash,
    load_fade_config,
)

_REPO = Path(__file__).resolve().parent.parent.parent


def test_defaults_keep_legacy_behavior() -> None:
    cfg = FadeBacktestConfig()
    assert cfg.guard_limit_dist is None
    assert cfg.disaster_x is None
    assert cfg.lock_penalty is None
    assert cfg.wf_test_starts == ()
    assert cfg.universe_daytrade_filter is False


def test_load_legacy_config_subset(tmp_path: Path) -> None:
    p = tmp_path / "legacy.json"
    p.write_text(json.dumps({"fee_discount": 0.5, "ga_seeds": [1, 2]}), encoding="utf-8")
    cfg = load_fade_config(p)
    assert cfg.fee_discount == 0.5
    assert cfg.ga_seeds == (1, 2)
    assert cfg.guard_limit_dist is None


def test_load_round1_config_from_repo() -> None:
    cfg = load_fade_config(_REPO / "configs" / "fade_uc_round1.json")
    assert cfg.fee_discount == 0.84
    assert cfg.guard_limit_dist == 0.03
    assert cfg.disaster_x == 0.04
    assert cfg.lock_penalty == 0.03
    assert cfg.wf_test_starts == ("2026-01-01", "2026-03-01", "2026-05-01", "2026-07-01")
    assert cfg.universe_daytrade_filter is True
    # 成本:0.001425×0.16×2 + 0.0015 ≈ 0.1956%
    cost = cfg.fee_rate * (1 - cfg.fee_discount) * 2 + cfg.intraday_tax
    assert abs(cost - 0.001956) < 1e-9


def test_guard_dist_grid_tuple_conversion(tmp_path: Path) -> None:
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"guard_dist_grid": [0.02, 0.05]}), encoding="utf-8")
    cfg = load_fade_config(p)
    assert cfg.guard_dist_grid == (0.02, 0.05)


def test_sim_hash_invalidates_on_guard_fields() -> None:
    base = FadeBacktestConfig()
    h0 = fade_sim_config_hash(base)
    assert fade_sim_config_hash(FadeBacktestConfig(guard_limit_dist=0.03)) != h0
    assert fade_sim_config_hash(FadeBacktestConfig(disaster_x=0.04)) != h0
    assert fade_sim_config_hash(FadeBacktestConfig(lock_penalty=0.03)) != h0
