"""CLI 三子命令 smoke(monkeypatch 入口)+ FINMIND_TOKEN 讀取順序."""

from __future__ import annotations

from pathlib import Path

import pytest

from copycat.cli import main


def test_backfill_daily_token_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    called: dict[str, object] = {}

    def fake(data_dir: Path, start: str, end: str, token: str, **kw: object) -> dict[str, int]:
        called.update({"data_dir": data_dir, "start": start, "end": end, "token": token})
        return {"fetched_days": 0, "skipped_days": 0, "added_rows": 0}

    monkeypatch.setattr("copycat.data.backfill_finmind.run_backfill", fake)
    monkeypatch.setenv("FINMIND_TOKEN", "tok-env")
    assert main(["backfill-daily", "--data-dir", str(tmp_path)]) == 0
    assert called["token"] == "tok-env" and called["start"] == "2024-06-02"


def test_backfill_daily_token_from_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    called: dict[str, object] = {}

    def fake(data_dir: Path, start: str, end: str, token: str, **kw: object) -> dict[str, int]:
        called["token"] = token
        return {"fetched_days": 0, "skipped_days": 0, "added_rows": 0}

    monkeypatch.setattr("copycat.data.backfill_finmind.run_backfill", fake)
    monkeypatch.delenv("FINMIND_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("OTHER=x\nFINMIND_TOKEN=tok-file\n", encoding="utf-8")
    assert main(["backfill-daily", "--data-dir", str(tmp_path)]) == 0
    assert called["token"] == "tok-file"


def test_backfill_daily_token_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("FINMIND_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError):
        main(["backfill-daily", "--data-dir", str(tmp_path)])


def test_tday_features_and_search_dispatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "copycat.backtest.pipeline.run_features",
        lambda *a, **k: calls.append("features") or tmp_path,
    )
    monkeypatch.setattr(
        "copycat.backtest.pipeline.run_search",
        lambda *a, **k: calls.append("search") or tmp_path / "r.md",
    )
    assert main(["tday-features", "--data-dir", str(tmp_path), "--out", str(tmp_path)]) == 0
    assert (
        main(
            [
                "tday-search",
                "--data-dir",
                str(tmp_path),
                "--out",
                str(tmp_path),
                "--report-date",
                "2026-07-07",
            ]
        )
        == 0
    )
    assert calls == ["features", "search"]
