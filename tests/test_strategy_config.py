from __future__ import annotations

import json
from pathlib import Path

import pytest

from copycat.strategy_config import StrategyConfig, load_config


def test_default_values() -> None:
    cfg = StrategyConfig.default()
    assert cfg.violent_pull_min_gain == 0.06
    assert cfg.queue_strong_min == 0.40
    assert cfg.t1_limit_mult == 1.095
    assert cfg.gap_buckets == (0.0, 0.01, 0.03, 0.07, 0.095)


def test_load_override(tmp_path: Path) -> None:
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({"violent_pull_min_gain": 0.05}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.violent_pull_min_gain == 0.05
    assert cfg.queue_strong_min == 0.40  # 未覆寫者保留預設


def test_unknown_key_raises(tmp_path: Path) -> None:
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({"no_such_param": 1}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(p)
