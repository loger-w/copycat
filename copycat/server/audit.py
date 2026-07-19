"""下單審計 JSONL(§7 閘三):append-only、跨執行緒序列化、失敗拋 AuditWriteError。

寫者有二:TradeRuntime 的 to_thread(preview/submit/result)與 TC4TradeSource listener
thread(report 筆)— module-level lock 序列化避免 Windows 並發 append 撕裂行(design R2-4)。
"""

from __future__ import annotations

import json
import threading
from datetime import date
from pathlib import Path
from typing import Any

_audit_lock = threading.Lock()


class AuditWriteError(Exception):
    """審計寫入失敗;NewOrder 送出前 = 拒單(500 AUDIT_WRITE_FAILED),送出後 = 降級旗標。"""


def audit_path(base: Path, when: date) -> Path:
    return base / f"orders-{when:%Y%m%d}.jsonl"


def append_audit(base: Path, record: dict[str, Any], *, when: date) -> None:
    path = audit_path(base, when)
    line = json.dumps(record, ensure_ascii=False)
    try:
        with _audit_lock:
            base.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
    except OSError as exc:
        raise AuditWriteError(str(exc)) from exc
