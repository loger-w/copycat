"""群益報告列 fixture 的共用變異器 —— `balance_rows` / `profit_rows` 各留一行 wrapper
保住各自的欄位提示 docstring(pr-160 review F-07:兩份逐位元組相同的實作收斂於此)。"""

from __future__ import annotations


def csv_variant(row: str, changes: dict[int, str]) -> str:
    """按欄索引改值。`.replace` 靠子字串唯一性猜欄位,欄形一改就靜默改錯欄 —— 一律走本函式。"""
    parts = row.split(",")
    for i, v in changes.items():
        parts[i] = v
    return ",".join(parts)
