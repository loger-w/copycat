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
    assert cfg.event_cooldown_secs == 600.0  # 市場事件對帳冷卻(R4)
    assert cfg.chain_ttl_hours == 168.0  # chain 快取 TTL = 7 天(R4)


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


def test_load_override_r4_keys(tmp_path: Path) -> None:
    """R4 兩鍵同樣走逐鍵覆寫;未覆寫的既有鍵不受影響。"""
    p = tmp_path / "breadth.json"
    p.write_text(
        json.dumps({"event_cooldown_secs": 120.0, "chain_ttl_hours": 24.0}),
        encoding="utf-8",
    )
    cfg = load_breadth_config(p)
    assert cfg.event_cooldown_secs == 120.0
    assert cfg.chain_ttl_hours == 24.0
    assert cfg.poll_secs == 10.0
    assert cfg.quota_backoff_secs == 300.0


def test_unknown_key_near_r4_keys_raises(tmp_path: Path) -> None:
    """打錯字(`chain_ttl_hour` 少個 s)不該靜默套預設。"""
    p = tmp_path / "breadth.json"
    p.write_text(json.dumps({"chain_ttl_hour": 24.0}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_breadth_config(p)


@pytest.mark.parametrize("bad", [0, 0.0, -1.0])
def test_non_positive_event_cooldown_raises(tmp_path: Path, bad: float) -> None:
    """冷卻 ≤ 0 讓廣度事件的 id 唯一性假設崩潰 —— 值域也要驗,不只未知鍵。

    事件 id 不含 `touch_count`,同 `(code, kind, direction, as_of)` 的重覆抑制**全靠**
    正冷卻;關掉冷卻後同 id 兩則會被前端去重吃掉一則,而畫面上只是「這則沒出現」。
    """
    p = tmp_path / "breadth.json"
    p.write_text(json.dumps({"event_cooldown_secs": bad}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_breadth_config(p)


def test_unknown_key_raises(tmp_path: Path) -> None:
    p = tmp_path / "breadth.json"
    p.write_text(json.dumps({"no_such_param": 1}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_breadth_config(p)
