"""round 3 config 欄位:災難回落式 / 結構停損 b / 貼板線 / 底倉臂(change-spec §9.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from copycat.backtest.fade_config import (
    FadeBacktestConfig,
    fade_sim_config_hash,
    load_fade_config,
)


def test_round3_fields_default_disabled() -> None:
    cfg = FadeBacktestConfig()
    assert cfg.disaster_arm_x is None
    assert cfg.disaster_retrace_r is None
    assert cfg.struct_stop_buffers == ()
    assert cfg.cell_b_gap_max is None
    assert cfg.base_arm is False
    assert cfg.base_arm_gap_edges == (0.01, 0.03, 0.055, 0.075)
    assert cfg.forward_start == "2026-07-11"


def _write(tmp_path: Path, payload: dict[str, object]) -> Path:
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_round3_config_loads_with_tuple_keys(tmp_path: Path) -> None:
    cfg = load_fade_config(
        _write(
            tmp_path,
            {
                "disaster_arm_x": 0.06,
                "disaster_retrace_r": 0.02,
                "struct_stop_buffers": [0.025, 0.0375],
                "cell_b_gap_max": 0.095,
                "base_arm": True,
                "base_arm_gap_edges": [0.01, 0.03, 0.055, 0.075],
            },
        )
    )
    assert cfg.disaster_arm_x == 0.06
    assert cfg.disaster_retrace_r == 0.02
    assert cfg.struct_stop_buffers == (0.025, 0.0375)
    assert cfg.base_arm_gap_edges == (0.01, 0.03, 0.055, 0.075)
    assert cfg.cell_b_gap_max == 0.095


def test_disaster_x_and_retrace_mutually_exclusive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="互斥"):
        load_fade_config(
            _write(
                tmp_path,
                {"disaster_x": 0.04, "disaster_arm_x": 0.06, "disaster_retrace_r": 0.02},
            )
        )


def test_disaster_arm_and_retrace_must_pair(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="同設"):
        load_fade_config(_write(tmp_path, {"disaster_arm_x": 0.06}))
    with pytest.raises(ValueError, match="同設"):
        load_fade_config(_write(tmp_path, {"disaster_retrace_r": 0.02}))


def test_sim_hash_sensitive_to_retrace_disaster() -> None:
    h0 = fade_sim_config_hash(FadeBacktestConfig())
    h1 = fade_sim_config_hash(FadeBacktestConfig(disaster_arm_x=0.06, disaster_retrace_r=0.02))
    assert h0 != h1
