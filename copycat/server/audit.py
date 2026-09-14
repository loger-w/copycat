"""下單審計 JSONL(§7 閘三):append-only、跨執行緒序列化、失敗拋 AuditWriteError。

寫者 = 群益 CapitalClient(送單前後兩段 + COM 回報執行緒的 reply 筆)— module-level
lock 序列化避免 Windows 並發 append 撕裂行(design R2-4)。

目錄建立(perf #245):舊版每 append 在鎖內 `mkdir(exist_ok=True)` 一次(206 µs 裡約 70 µs);
現版 `ensure_audit_dir` 在 CapitalClient 建構時建一次,`append_audit` 熱路徑直接開檔,只在
`FileNotFoundError`(目錄盤中被人刪)時才補建重試一次 —— 「append 自建缺目錄」這條行為合約
(`test_creates_missing_dirs`)保留,只是不再每筆付。
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import date
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_audit_lock = threading.Lock()


class AuditWriteError(Exception):
    """審計寫入失敗;NewOrder 送出前 = 拒單(500 AUDIT_WRITE_FAILED),送出後 = 降級旗標。"""


def audit_path(base: Path, when: date, *, prefix: str = "orders") -> Path:
    # prefix 分檔:群益 CapitalClient 傳 capital-*;預設 orders-* 是舊 TC4 trade 路留下的
    # 值(該路已除役,現無 production caller —— 僅測試在覆蓋預設分支)
    return base / f"{prefix}-{when:%Y%m%d}.jsonl"


def ensure_audit_dir(base: Path) -> None:
    """啟動時建一次審計目錄(perf #245);never-raise —— 建不起來只 WARNING,真正的失敗由第一筆
    `append_audit` 以 `AuditWriteError` 報(送單前 = 拒單),不讓 server 因審計目錄起不來。"""
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("審計目錄建立失敗(%s):%s;首筆審計寫入時會以 AuditWriteError 拒單", base, exc)


def append_audit(base: Path, record: dict[str, Any], *, when: date, prefix: str = "orders") -> None:
    path = audit_path(base, when, prefix=prefix)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    try:
        with _audit_lock:
            try:
                _append_line(path, line)
            except FileNotFoundError:
                # 目錄缺(啟動時建過、盤中被刪 / 測試裸呼叫):補建一次再寫,不每筆 mkdir
                base.mkdir(parents=True, exist_ok=True)
                _append_line(path, line)
    except OSError as exc:
        raise AuditWriteError(str(exc)) from exc


def _append_line(path: Path, line: str) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line)
        fh.flush()
