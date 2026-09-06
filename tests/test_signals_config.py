from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from copycat.signals_config import CONFIG_PATH, SignalsConfig, load_signals_config


def test_default_values() -> None:
    cfg = SignalsConfig()
    assert cfg.cdp_rearm_ticks == 5
    assert cfg.cdp_rearm_dwell_secs == 300.0
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
    # spec #192:掃單簇六欄 + 政策層六欄(拍板值,影子四週凍結)
    assert cfg.sweep_cluster_window_secs == 30.0
    assert cfg.sweep_min_sweeps == 2
    assert cfg.sweep_min_levels == 2
    assert cfg.sweep_up_pct == 0.3
    assert cfg.sweep_up_window_secs == 60.0
    assert cfg.sweep_cooldown_secs == 60.0
    assert cfg.policy_peer_up_pct == 3.0
    assert cfg.policy_max_chg_pct == 6.0
    assert cfg.policy_push_end == "12:30:00"
    assert cfg.policy_exclude_groups == ("ALL IN",)
    assert cfg.policy_outcome_time == "13:40:00"
    assert cfg.policy_outcome_days == 5


def test_load_policy_keys_and_exclude_groups_as_tuple(tmp_path: Path) -> None:
    """`policy_exclude_groups` 是 tuple 欄(JSON 陣列 → tuple,frozen dataclass 才 hashable);
    其餘新鍵逐鍵覆寫。"""
    p = tmp_path / "signals.json"
    p.write_text(
        json.dumps(
            {
                "policy_exclude_groups": ["ALL IN", "觀察"],
                "policy_peer_up_pct": 2.5,
                "policy_push_end": "12:00:00",
                "sweep_min_levels": 3,
                "policy_outcome_days": 7,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    cfg = load_signals_config(p)
    assert cfg.policy_exclude_groups == ("ALL IN", "觀察")
    assert cfg.policy_peer_up_pct == 2.5
    assert cfg.policy_push_end == "12:00:00"
    assert cfg.sweep_min_levels == 3
    assert cfg.policy_outcome_days == 7
    assert cfg.policy_max_chg_pct == 6.0  # 未覆寫者保留預設


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
    p.write_text(
        json.dumps({"surge_pct": 3.5, "cdp_rearm_ticks": 7, "cdp_rearm_dwell_secs": 120.0}),
        encoding="utf-8",
    )
    cfg = load_signals_config(p)
    assert cfg.surge_pct == 3.5
    assert cfg.cdp_rearm_ticks == 7
    assert cfg.cdp_rearm_dwell_secs == 120.0
    assert cfg.vol_ratio == 3.0  # 未覆寫者保留預設


def test_unknown_key_raises(tmp_path: Path) -> None:
    p = tmp_path / "signals.json"
    p.write_text(json.dumps({"no_such_param": 1}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_signals_config(p)
