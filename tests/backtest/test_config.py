from __future__ import annotations

import json
from pathlib import Path

import pytest

from copycat.backtest.config import BacktestConfig, load_backtest_config, sim_config_hash


def test_defaults() -> None:
    cfg = BacktestConfig.default()
    assert cfg.intraday_tax == 0.0015 and cfg.overnight_tax == 0.003
    assert len(cfg.theta_grid) == 11 and cfg.theta_grid[0] == 0.08 and cfg.theta_grid[-1] == 0.09
    assert cfg.anchor_thetas == (0.08,)
    assert cfg.ignition_touch_theta == 0.08
    assert cfg.near_miss_weight == 5.0
    assert cfg.support_weighted_min == 40.0 and cfg.support_raw_min == 20


def test_load_override_and_unknown_key(tmp_path: Path) -> None:
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({"ga_pop": 50, "ga_seeds": [1, 2]}), encoding="utf-8")
    cfg = load_backtest_config(p)
    assert cfg.ga_pop == 50 and cfg.ga_seeds == (1, 2)
    p2 = tmp_path / "bad.json"
    p2.write_text(json.dumps({"nope": 1}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_backtest_config(p2)


def test_sim_config_hash_sensitivity() -> None:
    base = BacktestConfig.default()
    h = sim_config_hash(base)
    assert h == sim_config_hash(BacktestConfig.default())  # 穩定
    # 模擬相關欄位 → hash 變
    assert h != sim_config_hash(BacktestConfig(intraday_tax=0.003))
    assert h != sim_config_hash(BacktestConfig(s3_trail=(0.02,)))
    # 搜索欄位 → hash 不變(cache 不因 GA 參數失效)
    assert h == sim_config_hash(BacktestConfig(ga_pop=7))
