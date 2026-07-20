"""Characterization:分位數 / 報告格式 / loader 錯誤字串(收斂前拍下,斷言值凍結).

refactor/shared-infra-helpers:步驟 1 對舊私有函式拍下行為,步驟 5 收斂到
quantiles / report_fmt 共用模組後僅改 import 指向 — **斷言值一字未改**。鎖住:
- round 版(原 fade_anatomy._quantiles / fade_cells._pctl)與 truncate 版
  (原 fade_diagnose._quantile)在 n=6, p=0.5 的分歧點(兩演算法不可互換)。
- 兩份 _fmt(現 fmt_cell / fmt_num)對 int / str / None 的不同語意。
- fmt_quantiles(原兩份逐字相同的 _fmtq)。
- 三份 config loader 的 unknown-key 錯誤訊息逐字(review R1)。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from copycat.backtest.config import load_backtest_config
from copycat.backtest.fade_config import load_fade_config
from copycat.backtest.quantiles import quantile_round, quantile_trunc, quantiles_round
from copycat.backtest.report_fmt import fmt_cell, fmt_num, fmt_quantiles
from copycat.strategy_config import load_config

# ---------- 分位數:round 版(_quantiles / _pctl 同演算法) ----------

_VALS5 = [10.0, 20.0, 30.0, 40.0, 50.0]
_VALS6 = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]


def test_quantiles_dict_round_vals5() -> None:
    assert quantiles_round(_VALS5) == {"p25": 20.0, "p50": 30.0, "p75": 40.0, "p90": 50.0, "n": 5}


def test_quantiles_dict_empty() -> None:
    assert quantiles_round([]) == {"p25": None, "p50": None, "p75": None, "p90": None, "n": 0}


def test_quantiles_dict_sorts_input() -> None:
    assert quantiles_round([30.0, 10.0, 50.0, 20.0, 40.0]) == quantiles_round(_VALS5)


def test_pctl_matches_quantiles_algorithm() -> None:
    q = quantiles_round(_VALS5)
    for p, key in ((0.25, "p25"), (0.50, "p50"), (0.75, "p75"), (0.90, "p90")):
        assert quantile_round(_VALS5, p) == q[key]
    assert quantile_round([], 0.5) is None


# ---------- 分位數:truncate 版與 round 版的分歧點 ----------


def test_round_vs_truncate_divergence_n6_p50() -> None:
    # round 版:idx = round(0.5 * 5) = 2 → 3.0;truncate 版:idx = int(0.5 * 6) = 3 → 4.0
    assert quantile_round(_VALS6, 0.5) == 3.0
    assert quantiles_round(_VALS6)["p50"] == 3.0
    assert quantile_trunc(_VALS6, 0.5) == 4.0


def test_truncate_quantile_vals5() -> None:
    assert quantile_trunc(_VALS5, 0.25) == 20.0
    assert quantile_trunc(_VALS5, 0.5) == 30.0
    assert quantile_trunc(_VALS5, 0.75) == 40.0
    assert quantile_trunc([], 0.5) is None
    assert quantile_trunc([7.0], 0.5) == 7.0


# ---------- _fmt 兩份(語意不同,不可合一) ----------


def test_tday_fmt_semantics() -> None:
    assert fmt_cell(None) == "—"
    assert fmt_cell(0.123456) == "+0.1235"
    assert fmt_cell(-0.5) == "-0.5000"
    assert fmt_cell(1.5) == "1.50"
    assert fmt_cell(1.0) == "1.00"  # abs >= 1 走 .2f
    assert fmt_cell(5) == "5"  # int → str,不格式化
    assert fmt_cell("abc") == "abc"  # str 原樣


def test_fade_fmt_semantics() -> None:
    assert fmt_num(None) == "—"
    assert fmt_num(0.123456) == "0.1235"
    assert fmt_num(1.5) == "1.5000"
    assert fmt_num(5) == "5.0000"  # int 也格式化(與 tday_fmt 不同)
    assert fmt_num("abc") == "—"  # str → —(與 tday_fmt 不同)
    assert fmt_num(0.5, ".2%") == "50.00%"


# ---------- _fmtq(原兩份逐字相同,已收斂為 fmt_quantiles 單一實作) ----------


def test_fmtq_semantics() -> None:
    q = {"p25": 0.1, "p50": 0.2, "p75": 0.3, "p90": 0.4, "n": 7}
    assert fmt_quantiles(q) == "10.00%/20.00%/30.00%/40.00%(n=7)"
    assert fmt_quantiles(None) == "—"
    assert (
        fmt_quantiles({"p25": None, "p50": None, "p75": None, "p90": None, "n": 0})
        == "—/—/—/—(n=0)"
    )
    assert (
        fmt_quantiles({"p25": 1, "p50": 0.2, "p75": 0.3, "p90": 0.4, "n": 2})
        == "—/20.00%/30.00%/40.00%(n=2)"
    )  # int 不是 float → —
    assert fmt_quantiles(q, ".1%") == "10.0%/20.0%/30.0%/40.0%(n=7)"
    cases: list[object] = [
        {"p25": 0.015, "p50": 0.02, "p75": 0.033, "p90": 0.05, "n": 12},
        {"n": 3},
        {},
        "not a dict",
    ]
    for c in cases:
        assert isinstance(fmt_quantiles(c), str)


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


def test_fade_loader_unknown_message(tmp_path: Path) -> None:
    with pytest.raises(ValueError) as exc:
        load_fade_config(_write_cfg(tmp_path, {"bogus": 1}))
    assert str(exc.value) == "未知回測參數: ['bogus']"
