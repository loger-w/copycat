"""Scratch: 只讀指定代號的 09-16 tick 存檔列(pyarrow 過濾,省記憶體)→ TickRow → replay_books。"""

from __future__ import annotations

from collections.abc import Iterator

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from copycat.book_replay import BookReplay, replay_books
from copycat.ticks import TickRow, _row_from_dict

TICKS = r"C:\side-project\copycat\data\ticks"


def rows_for(codes: list[str], date: str = "20260916") -> list[TickRow]:
    out: list[TickRow] = []
    for name in (f"{date}.parquet", f"{date}-book.parquet"):
        table = pq.read_table(f"{TICKS}\\{name}", filters=[("code", "in", codes)])
        out.extend(_row_from_dict(r) for r in table.to_pylist())
    out.sort(key=lambda r: r.msg_seq)
    return out


def replay_for(codes: list[str], date: str = "20260916") -> dict[str, BookReplay]:
    return replay_books(rows_for(codes, date))


def iter_all(date: str = "20260916") -> Iterator[tuple[str, BookReplay]]:
    """整天讀一次(pyarrow 表約 1 GB),逐檔轉 TickRow 重播,用完即丟。"""
    trade = pq.read_table(f"{TICKS}\\{date}.parquet")
    book = pq.read_table(f"{TICKS}\\{date}-book.parquet")
    codes = sorted(
        set(trade.column("code").to_pylist()) | set(book.column("code").to_pylist())
    )
    for code in codes:
        rows: list[TickRow] = []
        for table in (trade, book):
            sub = table.filter(pc.equal(table["code"], pa.scalar(code)))
            rows.extend(_row_from_dict(r) for r in sub.to_pylist())
        rows.sort(key=lambda r: r.msg_seq)
        yield code, replay_books(rows)[code]


def all_codes(date: str = "20260916") -> list[str]:
    t = pq.read_table(f"{TICKS}\\{date}.parquet", columns=["code"])
    return sorted(set(t.column("code").to_pylist()))


def hms(ms: int) -> str:
    s = ms // 1000
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}.{ms % 1000:03d}"
