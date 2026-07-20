"""Dataclass config JSON 載入樣板 — 唯一實作,取代三份 loader 手刻.

樣板 = unknown-key 檢查(raise ValueError,錯誤字串由 caller 定)+ 指定欄位
list → tuple 轉換 + dataclass 建構。載入後的額外不變式檢查(如 fade_config 的
validate_*)留在 caller。
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import fields
from pathlib import Path
from typing import TypeVar

_T = TypeVar("_T")


def load_dataclass_json(
    path: Path, cls: type[_T], *, tuple_keys: Iterable[str], unknown_label: str
) -> _T:
    payload: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    known = {f.name for f in fields(cls)}  # type: ignore[arg-type]
    unknown = set(payload) - known
    if unknown:
        raise ValueError(f"{unknown_label}: {sorted(unknown)}")
    for key in tuple_keys:
        if key in payload:
            value = payload[key]
            assert isinstance(value, list)
            payload[key] = tuple(value)
    return cls(**payload)  # type: ignore[arg-type]
