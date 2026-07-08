"""CLI fade 子命令 smoke(monkeypatch 入口,對齊 test_cli_tday 慣例)."""

from __future__ import annotations

from pathlib import Path

import pytest

from copycat.cli import main


def test_fade_search_dispatches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    called: dict[str, object] = {}

    def fake_pipeline(
        data_dir: Path,
        out_dir: Path,
        cfg: object,
        report_date: str,
        evidence_dir: Path | None = None,
    ) -> dict[str, object]:
        called.update(
            {
                "data_dir": data_dir,
                "out_dir": out_dir,
                "report_date": report_date,
                "evidence_dir": evidence_dir,
            }
        )
        return {"report": str(out_dir / "report.md"), "rules_final": str(out_dir / "rules.json")}

    monkeypatch.setattr("copycat.backtest.fade_pipeline.run_fade_pipeline", fake_pipeline)
    out = tmp_path / "out"
    rc = main(
        [
            "fade-search",
            "--data-dir",
            str(tmp_path / "data"),
            "--out",
            str(out),
            "--report-date",
            "2026-07-08",
            "--report-dir",
            str(tmp_path / "evidence"),
        ]
    )
    assert rc == 0
    assert called["report_date"] == "2026-07-08"
    assert called["evidence_dir"] == tmp_path / "evidence"


def test_fade_search_default_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    called: dict[str, object] = {}

    def fake_pipeline(
        data_dir: Path,
        out_dir: Path,
        cfg: object,
        report_date: str,
        evidence_dir: Path | None = None,
    ) -> dict[str, object]:
        called["dispatched"] = True
        called["cfg_type"] = type(cfg).__name__
        return {"report": "", "rules_final": ""}

    monkeypatch.setattr("copycat.backtest.fade_pipeline.run_fade_pipeline", fake_pipeline)
    rc = main(
        [
            "fade-search",
            "--data-dir",
            str(tmp_path / "data"),
            "--out",
            str(tmp_path / "out"),
            "--report-date",
            "2026-07-08",
        ]
    )
    assert rc == 0
    assert called.get("dispatched") is True
    assert called.get("cfg_type") == "FadeBacktestConfig"
