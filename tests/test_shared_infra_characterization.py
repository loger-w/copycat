"""Characterization:分位數三份 / _fmt 兩份 / _fmtq 兩份 / loader 錯誤字串.

refactor/shared-infra-helpers 步驟 1(🟢):把當前行為拍下來,收斂到共用模組時
斷言值一字不得改(改了 = 行為變了 = 停)。重點鎖住:
- round 版(fade_anatomy._quantiles / fade_cells._pctl)與 truncate 版
  (fade_diagnose._quantile)在 n=6, p=0.5 的分歧點。
- 兩份 _fmt 對 int / str / None 的不同語意。
- 兩份 _fmtq 逐字相同(同輸入同輸出)。
- 三份 config loader 的 unknown-key 錯誤訊息逐字(review R1)。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from copycat.backtest.config import load_backtest_config
from copycat.backtest.fade_anatomy import _fmtq as anatomy_fmtq
from copycat.backtest.fade_anatomy import _quantiles
from copycat.backtest.fade_cells import _pctl
from copycat.backtest.fade_config import load_fade_config
from copycat.backtest.fade_diagnose import _quantile
from copycat.backtest.fade_entry_anatomy import _fmtq as entry_fmtq
from copycat.backtest.fade_report import _fmt as fade_fmt
from copycat.backtest.report import _fmt as tday_fmt
from copycat.strategy_config import load_config

# ---------- 分位數:round 版(_quantiles / _pctl 同演算法) ----------

_VALS5 = [10.0, 20.0, 30.0, 40.0, 50.0]
_VALS6 = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]


def test_quantiles_dict_round_vals5() -> None:
    assert _quantiles(_VALS5) == {"p25": 20.0, "p50": 30.0, "p75": 40.0, "p90": 50.0, "n": 5}


def test_quantiles_dict_empty() -> None:
    assert _quantiles([]) == {"p25": None, "p50": None, "p75": None, "p90": None, "n": 0}


def test_quantiles_dict_sorts_input() -> None:
    assert _quantiles([30.0, 10.0, 50.0, 20.0, 40.0]) == _quantiles(_VALS5)


def test_pctl_matches_quantiles_algorithm() -> None:
    q = _quantiles(_VALS5)
    for p, key in ((0.25, "p25"), (0.50, "p50"), (0.75, "p75"), (0.90, "p90")):
        assert _pctl(_VALS5, p) == q[key]
    assert _pctl([], 0.5) is None


# ---------- 分位數:truncate 版與 round 版的分歧點 ----------


def test_round_vs_truncate_divergence_n6_p50() -> None:
    # round 版:idx = round(0.5 * 5) = 2 → 3.0;truncate 版:idx = int(0.5 * 6) = 3 → 4.0
    assert _pctl(_VALS6, 0.5) == 3.0
    assert _quantiles(_VALS6)["p50"] == 3.0
    assert _quantile(_VALS6, 0.5) == 4.0


def test_truncate_quantile_vals5() -> None:
    assert _quantile(_VALS5, 0.25) == 20.0
    assert _quantile(_VALS5, 0.5) == 30.0
    assert _quantile(_VALS5, 0.75) == 40.0
    assert _quantile([], 0.5) is None
    assert _quantile([7.0], 0.5) == 7.0


# ---------- _fmt 兩份(語意不同,不可合一) ----------


def test_tday_fmt_semantics() -> None:
    assert tday_fmt(None) == "—"
    assert tday_fmt(0.123456) == "+0.1235"
    assert tday_fmt(-0.5) == "-0.5000"
    assert tday_fmt(1.5) == "1.50"
    assert tday_fmt(1.0) == "1.00"  # abs >= 1 走 .2f
    assert tday_fmt(5) == "5"  # int → str,不格式化
    assert tday_fmt("abc") == "abc"  # str 原樣


def test_fade_fmt_semantics() -> None:
    assert fade_fmt(None) == "—"
    assert fade_fmt(0.123456) == "0.1235"
    assert fade_fmt(1.5) == "1.5000"
    assert fade_fmt(5) == "5.0000"  # int 也格式化(與 tday_fmt 不同)
    assert fade_fmt("abc") == "—"  # str → —(與 tday_fmt 不同)
    assert fade_fmt(0.5, ".2%") == "50.00%"


# ---------- _fmtq 兩份(逐字相同,同輸入同輸出) ----------


@pytest.mark.parametrize("fmtq", [anatomy_fmtq, entry_fmtq], ids=["anatomy", "entry_anatomy"])
def test_fmtq_semantics(fmtq: Callable[..., str]) -> None:
    q = {"p25": 0.1, "p50": 0.2, "p75": 0.3, "p90": 0.4, "n": 7}
    assert fmtq(q) == "10.00%/20.00%/30.00%/40.00%(n=7)"
    assert fmtq(None) == "—"
    assert fmtq({"p25": None, "p50": None, "p75": None, "p90": None, "n": 0}) == "—/—/—/—(n=0)"
    assert (
        fmtq({"p25": 1, "p50": 0.2, "p75": 0.3, "p90": 0.4, "n": 2})
        == "—/20.00%/30.00%/40.00%(n=2)"
    )  # int 不是 float → —
    assert fmtq(q, ".1%") == "10.0%/20.0%/30.0%/40.0%(n=7)"


def test_fmtq_copies_identical_on_same_inputs() -> None:
    cases: list[object] = [
        {"p25": 0.015, "p50": 0.02, "p75": 0.033, "p90": 0.05, "n": 12},
        {"n": 3},
        {},
        "not a dict",
        None,
    ]
    for c in cases:
        assert anatomy_fmtq(c) == entry_fmtq(c)


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
