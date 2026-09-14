"""SC-5:審計 JSONL — append-only / 並發序列化 / 失敗語意。"""

from __future__ import annotations

import json
import logging
import threading
from datetime import date
from pathlib import Path

import pytest

from copycat.server.audit import AuditWriteError, append_audit, audit_path, ensure_audit_dir

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

    def test_existing_dir_appends_without_mkdir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """perf #245:目錄已在(啟動時 `ensure_audit_dir` 建過)→ append 熱路徑零 `mkdir`;
        下一案(目錄缺時自建)仍是行為合約,兩案合起來 = 「只在缺的時候才建」。"""
        base = tmp_path / "audit"
        ensure_audit_dir(base)
        calls = {"n": 0}
        real_mkdir = Path.mkdir

        def counting_mkdir(self: Path, *a: object, **kw: object) -> None:
            calls["n"] += 1
            real_mkdir(self, *a, **kw)  # type: ignore[arg-type]

        monkeypatch.setattr(Path, "mkdir", counting_mkdir)
        append_audit(base, {"a": 1}, when=WHEN)
        append_audit(base, {"a": 2}, when=WHEN)
        assert calls["n"] == 0
        assert audit_path(base, WHEN).read_text(encoding="utf-8").count("\n") == 2

    def test_ensure_audit_dir_never_raises(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """建不起來只 WARNING(server 照起),失敗留給首筆 append 以 AuditWriteError 報。"""
        blocker = tmp_path / "file"
        blocker.write_text("x", encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="copycat.server.audit"):
            ensure_audit_dir(blocker / "audit")  # 父路徑是檔案 → mkdir 必失敗
        assert any("審計目錄建立失敗" in r.getMessage() for r in caplog.records)

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
