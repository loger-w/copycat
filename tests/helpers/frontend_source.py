"""後端測試讀**前端原始碼字面**的唯一入口(跨語言 parity 測試:river palette / AVG_SOURCES /
WATCHLIST_LIMIT;pr-131 F-01 起三個讀者全走這裡)。

`parents[N]` 各測試各數各的,測試檔搬目錄時靜默失準(review S-4);repo root 只在這裡算一次。
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"


def read_frontend_source(rel: str) -> str:
    """讀 `frontend/src/<rel>` 的文字(UTF-8);檔不存在直接 raise —— parity 測試要紅不要 skip。"""
    return (FRONTEND_SRC / rel).read_text(encoding="utf-8")
