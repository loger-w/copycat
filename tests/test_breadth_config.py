"""家數帶 / 騰落線設定(market-overview R2 Task 4)— `test_signals_config` 同款。

檔案不存在 = 全預設(repo 不附 `configs/breadth.json`);未知鍵 raise(打錯字不靜默)。
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from copycat.breadth_config import CONFIG_PATH, BreadthConfig, load_breadth_config


def test_default_values() -> None:
    cfg = BreadthConfig()
    assert cfg.poll_secs == 10.0
    # 09:00 起 = 排除 08:55–09:00 試撮窗(2026-08-12 拍板:試撮價可被假單操縱,
    # 不進系統;開盤前畫面顯示昨日收盤資料是合理狀態)
    assert cfg.window_start == "09:00"
    assert cfg.window_end == "13:40"
    assert cfg.stale_secs == 30.0
    assert cfg.backoff_max_secs == 60.0
    assert cfg.quota_backoff_secs == 300.0


def test_frozen() -> None:
    cfg = BreadthConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.poll_secs = 1.0  # type: ignore[misc]


def test_default_config_path_points_at_configs_breadth_json() -> None:
    assert CONFIG_PATH.name == "breadth.json"
    assert CONFIG_PATH.parent.name == "configs"


def test_missing_file_falls_back_to_defaults(tmp_path: Path) -> None:
    cfg = load_breadth_config(tmp_path / "nope.json")
    assert cfg == BreadthConfig()


def test_load_override(tmp_path: Path) -> None:
    p = tmp_path / "breadth.json"
    p.write_text(
        json.dumps({"poll_secs": 5.0, "window_end": "14:30", "quota_backoff_secs": 60.0}),
        encoding="utf-8",
    )
    cfg = load_breadth_config(p)
    assert cfg.poll_secs == 5.0
    assert cfg.window_end == "14:30"
    assert cfg.quota_backoff_secs == 60.0
    assert cfg.window_start == "09:00"  # 未覆寫者保留預設
    assert cfg.stale_secs == 30.0


def test_unknown_key_raises(tmp_path: Path) -> None:
    p = tmp_path / "breadth.json"
    p.write_text(json.dumps({"no_such_param": 1}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_breadth_config(p)
