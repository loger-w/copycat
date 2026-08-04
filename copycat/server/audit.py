"""下單審計 JSONL(§7 閘三):append-only、跨執行緒序列化、失敗拋 AuditWriteError。

寫者 = 群益 CapitalClient(送單前後兩段 + COM 回報執行緒的 reply 筆)— module-level
lock 序列化避免 Windows 並發 append 撕裂行(design R2-4)。
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


def audit_path(base: Path, when: date, *, prefix: str = "orders") -> Path:
    # prefix 分檔:群益 CapitalClient 傳 capital-*;預設 orders-* 是舊 TC4 trade 路留下的
    # 值(該路已除役,現無 production caller —— 僅測試在覆蓋預設分支)
    return base / f"{prefix}-{when:%Y%m%d}.jsonl"


def append_audit(base: Path, record: dict[str, Any], *, when: date, prefix: str = "orders") -> None:
    path = audit_path(base, when, prefix=prefix)
    line = json.dumps(record, ensure_ascii=False)
    try:
        with _audit_lock:
            base.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
    except OSError as exc:
        raise AuditWriteError(str(exc)) from exc
