"""可替換分點集合 — 只影響事件標記與報表分組,不進評分邏輯(spec §2)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Watchlist:
    name: str
    broker_ids: frozenset[str]  # 大小寫敏感(779Z ≠ 779z)


def load_watchlist(path: Path) -> Watchlist:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return Watchlist(
        name=payload["name"],
        broker_ids=frozenset(m["broker_id"] for m in payload["members"]),
    )
