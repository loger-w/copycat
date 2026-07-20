"""標準化 1K 的本機 JSON 儲存(atomic write,無 DB — 沿專案慣例)."""

from __future__ import annotations

import json
from pathlib import Path

from copycat.data.models import Bar1K
from copycat.fileio import atomic_write_text


def bars_path(data_dir: Path, stock_id: str, date: str) -> Path:
    return data_dir / "1k" / stock_id / f"{date}.json"


def write_bars(data_dir: Path, stock_id: str, date: str, bars: list[Bar1K]) -> None:
    if any(b2.m <= b1.m for b1, b2 in zip(bars, bars[1:])):
        raise ValueError(f"bars 未按分鐘索引遞增: {stock_id} {date}")
    payload = {
        "stock_id": stock_id,
        "date": date,
        "bars": [
            [
                b.m,
                b.open,
                b.high,
                b.low,
                b.close,
                b.volume,
                b.up_volume,
                b.down_volume,
                b.unch_volume,
            ]
            for b in bars
        ],
    }
    path = bars_path(data_dir, stock_id, date)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(payload, separators=(",", ":")))


def read_bars(data_dir: Path, stock_id: str, date: str) -> list[Bar1K] | None:
    path = bars_path(data_dir, stock_id, date)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        Bar1K(
            m=int(r[0]),
            open=r[1],
            high=r[2],
            low=r[3],
            close=r[4],
            volume=r[5],
            up_volume=r[6],
            down_volume=r[7],
            unch_volume=r[8],
        )
        for r in payload["bars"]
    ]
