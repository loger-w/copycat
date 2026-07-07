"""Evidence 報告(SC-8):章節 checklist、無合格規則、byte 穩定."""

from __future__ import annotations

from pathlib import Path

from copycat.backtest.config import BacktestConfig
from copycat.backtest.report import write_report

_SECTIONS = [
    "方法論",
    "θ 曲線",
    "regime × 規則",
    "停損族對決",
    "出場對決",
    "開盤即攻",
    "滑價壓測",
    "3055",
    "剔除計數",
    "負結果",
]


def _empty_result() -> dict[str, object]:
    return {
        "rules": [],
        "theta_curves": {},
        "stop_duel": {},
        "early_attack": {},
        "slippage_stress": {},
        "case_3055": None,
        "negative_findings": ["無任何規則通過三道驗證"],
    }


def test_report_sections_and_no_rule(tmp_path: Path) -> None:
    out = write_report(
        tmp_path, _empty_result(), {"missing_1k": 3}, "2026-07-07", BacktestConfig.default()
    )
    assert out.name == "tday_join_ga_backtest_2026-07-07.md"
    text = out.read_text(encoding="utf-8")
    for sec in _SECTIONS:
        assert sec in text, f"缺章節: {sec}"
    assert "無" in text  # 無合格規則 → 明寫
    assert "E2/E3" in text  # E1-only 注記
    assert "missing_1k" in text and "3" in text  # 剔除計數
    assert "MDD" in text or "fitness" in text  # spec §8 偏離注記所在的方法論段


def test_report_byte_stable(tmp_path: Path) -> None:
    a = write_report(
        tmp_path / "a", _empty_result(), {}, "2026-07-07", BacktestConfig.default()
    ).read_text(encoding="utf-8")
    b = write_report(
        tmp_path / "b", _empty_result(), {}, "2026-07-07", BacktestConfig.default()
    ).read_text(encoding="utf-8")
    assert a == b
