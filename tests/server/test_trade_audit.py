"""SC-5:審計 JSONL — append-only / 並發序列化 / 失敗語意。"""

from __future__ import annotations

import json
import threading
from datetime import date
from pathlib import Path

import pytest

from copycat.server.audit import AuditWriteError, append_audit, audit_path

WHEN = date(2026, 7, 19)


class TestAuditPath:
    def test_date_based_filename(self, tmp_path: Path) -> None:
        assert audit_path(tmp_path, WHEN) == tmp_path / "orders-20260719.jsonl"


class TestAppendAudit:
    def test_two_appends_two_parseable_lines(self, tmp_path: Path) -> None:
        append_audit(tmp_path, {"event": "preview", "request_id": "a"}, when=WHEN)
        append_audit(tmp_path, {"event": "submit", "request_id": "a"}, when=WHEN)
        lines = (tmp_path / "orders-20260719.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert [json.loads(line)["event"] for line in lines] == ["preview", "submit"]

    def test_append_does_not_overwrite(self, tmp_path: Path) -> None:
        path = audit_path(tmp_path, WHEN)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"event": "existing"}\n', encoding="utf-8")
        append_audit(tmp_path, {"event": "new"}, when=WHEN)
        lines = path.read_text(encoding="utf-8").splitlines()
        assert json.loads(lines[0])["event"] == "existing"
        assert json.loads(lines[1])["event"] == "new"

    def test_creates_missing_dirs(self, tmp_path: Path) -> None:
        base = tmp_path / "nested" / "audit"
        append_audit(base, {"event": "preview"}, when=WHEN)
        assert audit_path(base, WHEN).exists()

    def test_chinese_not_escaped(self, tmp_path: Path) -> None:
        append_audit(tmp_path, {"event": "result", "msg": "價格錯誤"}, when=WHEN)
        text = audit_path(tmp_path, WHEN).read_text(encoding="utf-8")
        assert "價格錯誤" in text

    def test_concurrent_appends_all_lines_parseable(self, tmp_path: Path) -> None:
        def worker(n: int) -> None:
            for i in range(25):
                append_audit(tmp_path, {"event": "report", "n": n, "i": i}, when=WHEN)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        lines = audit_path(tmp_path, WHEN).read_text(encoding="utf-8").splitlines()
        assert len(lines) == 200
        for line in lines:
            json.loads(line)

    def test_write_failure_raises_audit_write_error(self, tmp_path: Path) -> None:
        blocker = tmp_path / "not-a-dir"
        blocker.write_text("x", encoding="utf-8")
        with pytest.raises(AuditWriteError):
            append_audit(blocker, {"event": "preview"}, when=WHEN)
