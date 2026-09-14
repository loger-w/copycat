"""Characterization:報告格式 / loader 錯誤字串(收斂前拍下,斷言值凍結).

refactor/shared-infra-helpers:步驟 1 對舊私有函式拍下行為,步驟 5 收斂到
report_fmt 共用模組後僅改 import 指向 — **斷言值一字未改**。鎖住:
- fmt_cell(原 report._fmt)對 int / str / None 的語意。
- 兩份 config loader 的 unknown-key 錯誤訊息逐字(review R1)。

2026-09-14 專案瘦身:fade 回測家族整批刪除,quantiles / fmt_num / fmt_quantiles /
load_fade_config 隨之退場,對應斷言一併移除(它們鎖的是已不存在的 caller)。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from copycat.backtest.config import load_backtest_config
from copycat.backtest.report_fmt import fmt_cell
from copycat.strategy_config import load_config

# ---------- fmt_cell(原 report._fmt) ----------


def test_tday_fmt_semantics() -> None:
    assert fmt_cell(None) == "—"
    assert fmt_cell(0.123456) == "+0.1235"
    assert fmt_cell(-0.5) == "-0.5000"
    assert fmt_cell(1.5) == "1.50"
    assert fmt_cell(1.0) == "1.00"  # abs >= 1 走 .2f
    assert fmt_cell(5) == "5"  # int → str,不格式化
    assert fmt_cell("abc") == "abc"  # str 原樣


# ---------- loader unknown-key 錯誤訊息逐字(review R1) ----------


def _write_cfg(tmp_path: Path, payload: dict[str, object]) -> Path:
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_strategy_loader_unknown_message(tmp_path: Path) -> None:
    with pytest.raises(ValueError) as exc:
        load_config(_write_cfg(tmp_path, {"bogus_b": 1, "bogus_a": 2}))
    assert str(exc.value) == "未知策略參數: ['bogus_a', 'bogus_b']"


def test_backtest_loader_unknown_message(tmp_path: Path) -> None:
    with pytest.raises(ValueError) as exc:
        load_backtest_config(_write_cfg(tmp_path, {"bogus": 1}))
    assert str(exc.value) == "未知回測參數: ['bogus']"
