"""tick 存檔設定(spec #257)— `test_breadth_config` 同款 parity。

檔案不存在 = 全預設(repo 不附 `configs/ticks.json`);未知鍵 raise(打錯字不靜默)。
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from copycat.ticks_config import CONFIG_PATH, TicksConfig, load_ticks_config


def test_default_values() -> None:
    cfg = TicksConfig()
    assert cfg.enabled is True
    assert cfg.dir == "data/ticks"
    assert cfg.flush_secs == 30.0
    assert cfg.compact_time == "13:45"
    assert cfg.retry_secs == 900.0
    assert cfg.retry_max == 3
    assert cfg.compact_timeout_secs == 300.0
    assert cfg.book_keep_days == 120


def test_frozen() -> None:
    cfg = TicksConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.flush_secs = 1.0  # type: ignore[misc]


def test_default_config_path_points_at_configs_ticks_json() -> None:
    assert CONFIG_PATH.name == "ticks.json"
    assert CONFIG_PATH.parent.name == "configs"


def test_missing_file_falls_back_to_defaults(tmp_path: Path) -> None:
    assert load_ticks_config(tmp_path / "nope.json") == TicksConfig()


def test_load_override(tmp_path: Path) -> None:
    p = tmp_path / "ticks.json"
    p.write_text(json.dumps({"enabled": False, "flush_secs": 5.0, "dir": "D:/ticks"}), "utf-8")
    cfg = load_ticks_config(p)
    assert cfg.enabled is False
    assert cfg.flush_secs == 5.0
    assert cfg.dir == "D:/ticks"
    assert cfg.compact_time == "13:45"  # 未覆寫者保留預設


def test_unknown_key_raises(tmp_path: Path) -> None:
    p = tmp_path / "ticks.json"
    p.write_text(json.dumps({"no_such_param": 1}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_ticks_config(p)
