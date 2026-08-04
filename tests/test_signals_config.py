from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from copycat.signals_config import CONFIG_PATH, SignalsConfig, load_signals_config


def test_default_values() -> None:
    cfg = SignalsConfig()
    assert cfg.cdp_rearm_ticks == 5
    assert cfg.cdp_cooldown_secs == 600
    assert cfg.surge_pct == 2.0
    assert cfg.surge_window_secs == 300
    assert cfg.surge_cooldown_secs == 1800
    assert cfg.vol_ratio == 3.0
    assert cfg.vol_min_elapsed_min == 15
    assert cfg.vol_min_window_lots == 100
    assert cfg.vol_min_day_lots == 500
    assert cfg.vol_cooldown_secs == 1800
    assert cfg.limit_cooldown_secs == 600
    assert cfg.discord_per_min == 30
    assert cfg.basis_gap_secs == 0.2


def test_frozen() -> None:
    cfg = SignalsConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.surge_pct = 9.0  # type: ignore[misc]


def test_default_config_path_points_at_configs_signals_json() -> None:
    assert CONFIG_PATH.name == "signals.json"
    assert CONFIG_PATH.parent.name == "configs"


def test_missing_file_falls_back_to_defaults(tmp_path: Path) -> None:
    cfg = load_signals_config(tmp_path / "nope.json")
    assert cfg == SignalsConfig()


def test_load_override(tmp_path: Path) -> None:
    p = tmp_path / "signals.json"
    p.write_text(json.dumps({"surge_pct": 3.5, "cdp_rearm_ticks": 7}), encoding="utf-8")
    cfg = load_signals_config(p)
    assert cfg.surge_pct == 3.5
    assert cfg.cdp_rearm_ticks == 7
    assert cfg.vol_ratio == 3.0  # 未覆寫者保留預設


def test_unknown_key_raises(tmp_path: Path) -> None:
    p = tmp_path / "signals.json"
    p.write_text(json.dumps({"no_such_param": 1}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_signals_config(p)
