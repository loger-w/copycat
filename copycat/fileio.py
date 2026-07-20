"""Atomic 檔案寫入(tmp + os.replace)— 全專案唯一實作,取代各站點手刻.

兩個 helper 對應既有兩種形狀,newline 語意不同**不可互換**:
- atomic_write_text:`Path.write_text` 版(預設 newline 翻譯),JSON / Markdown 用。
- atomic_open_text:`open("w", encoding="utf-8", newline="")` 版,csv.writer 用。

例外路徑沿既有語意:寫 tmp 中途失敗 → tmp 殘留、目標檔不動(不加 cleanup)。
"""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO


def atomic_write_text(path: Path, content: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


@contextmanager
def atomic_open_text(path: Path) -> Generator[TextIO]:
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        yield fh
    os.replace(tmp, path)
