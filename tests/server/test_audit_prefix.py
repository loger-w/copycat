"""SC-9:審計 prefix 分檔 — orders-*(TC4 trade)與 capital-*(群益)同 base 不同檔。

既有 caller 零改動:prefix 預設 "orders",tests/server/test_trade_audit.py 不動即綠。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from copycat.server.audit import append_audit, audit_path

WHEN = date(2026, 7, 28)


class TestAuditPathPrefix:
    def test_default_prefix_is_orders(self, tmp_path: Path) -> None:
        assert audit_path(tmp_path, WHEN) == tmp_path / "orders-20260728.jsonl"

    def test_capital_prefix_names_capital_file(self, tmp_path: Path) -> None:
        assert audit_path(tmp_path, WHEN, prefix="capital") == tmp_path / "capital-20260728.jsonl"


class TestAppendAuditPrefix:
    def test_prefixes_split_files_under_same_base(self, tmp_path: Path) -> None:
        append_audit(tmp_path, {"event": "tc4"}, when=WHEN)
        append_audit(tmp_path, {"event": "capital"}, when=WHEN, prefix="capital")
        orders = (tmp_path / "orders-20260728.jsonl").read_text(encoding="utf-8").splitlines()
        capital = (tmp_path / "capital-20260728.jsonl").read_text(encoding="utf-8").splitlines()
        assert [json.loads(line)["event"] for line in orders] == ["tc4"]
        assert [json.loads(line)["event"] for line in capital] == ["capital"]
