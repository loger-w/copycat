"""round 4 config 欄位:inner_flip 停損 / TP 決策樹(change-spec §5.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from copycat.backtest.fade_config import (
    FadeBacktestConfig,
    fade_sim_config_hash,
    load_fade_config,
)


def _write(tmp_path: Path, payload: dict[str, object]) -> Path:
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_round4_fields_default_disabled() -> None:
    cfg = FadeBacktestConfig()
    assert cfg.inner_flip_phi_grid == ()
    assert cfg.inner_flip_min_bars == 15
    assert cfg.tp_flush_z is None
    assert cfg.tp_flush_lookback is None
    assert cfg.tp_flush_recovery is None
    assert cfg.tp_flush_min_profit is None
    assert cfg.tp_hl_k is None
    assert cfg.tp_hl_min_profit is None


def test_round4_config_loads_with_tuple_keys(tmp_path: Path) -> None:
    cfg = load_fade_config(
        _write(
            tmp_path,
            {
                "inner_flip_phi_grid": [0.45, 0.55],
                "tp_flush_z": 3.0,
                "tp_flush_lookback": 5,
                "tp_flush_recovery": 0.5,
                "tp_flush_min_profit": 0.005,
                "tp_hl_k": 2,
                "tp_hl_min_profit": 0.005,
            },
        )
    )
    assert cfg.inner_flip_phi_grid == (0.45, 0.55)
    assert cfg.tp_flush_z == 3.0
    assert cfg.tp_flush_lookback == 5
    assert cfg.tp_flush_recovery == 0.5
    assert cfg.tp_flush_min_profit == 0.005
    assert cfg.tp_hl_k == 2
    assert cfg.tp_hl_min_profit == 0.005


def test_tp_flush_fields_all_or_none(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="同設"):
        load_fade_config(_write(tmp_path, {"tp_flush_z": 3.0}))
    with pytest.raises(ValueError, match="同設"):
        load_fade_config(
            _write(tmp_path, {"tp_flush_z": 3.0, "tp_flush_lookback": 5, "tp_flush_recovery": 0.5})
        )


def test_tp_hl_fields_all_or_none(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="同設"):
        load_fade_config(_write(tmp_path, {"tp_hl_k": 2}))
    with pytest.raises(ValueError, match="同設"):
        load_fade_config(_write(tmp_path, {"tp_hl_min_profit": 0.005}))


def test_inner_flip_min_bars_must_be_positive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="inner_flip_min_bars"):
        load_fade_config(_write(tmp_path, {"inner_flip_min_bars": 0}))


def test_sim_hash_sensitive_to_round4_engine_fields() -> None:
    h0 = fade_sim_config_hash(FadeBacktestConfig())
    h_flush = fade_sim_config_hash(
        FadeBacktestConfig(
            tp_flush_z=3.0, tp_flush_lookback=5, tp_flush_recovery=0.5, tp_flush_min_profit=0.005
        )
    )
    h_hl = fade_sim_config_hash(FadeBacktestConfig(tp_hl_k=2, tp_hl_min_profit=0.005))
    h_bars = fade_sim_config_hash(FadeBacktestConfig(inner_flip_min_bars=20))
    assert len({h0, h_flush, h_hl, h_bars}) == 4


def test_phi_grid_not_in_sim_hash() -> None:
    """inner_flip_phi_grid 是 cells 層變體(同 struct_stop_buffers 前例),不入 hash."""
    h0 = fade_sim_config_hash(FadeBacktestConfig())
    h1 = fade_sim_config_hash(FadeBacktestConfig(inner_flip_phi_grid=(0.45,)))
    assert h0 == h1
