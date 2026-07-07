from __future__ import annotations

import json
from pathlib import Path

from copycat.replay.compare import write_compare
from tests.replay.test_report import _event


def _mk_run(path: Path, gap: float) -> Path:
    path.mkdir(parents=True)
    with (path / "events.jsonl").open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(_event("3-7%", gap, 0.01, True), ensure_ascii=False) + "\n")
    return path


def test_write_compare(tmp_path: Path) -> None:
    a = _mk_run(tmp_path / "a", 0.05)
    b = _mk_run(tmp_path / "b", 0.03)
    out = write_compare(a, b, tmp_path / "cmp.md")
    text = out.read_text(encoding="utf-8")
    assert "Δ" in text and "a" in text and "b" in text
