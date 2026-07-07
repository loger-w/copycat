"""日線索引:adv20 / 一價到底 / 下一交易日 / 漲停集合 / 連板數."""

from __future__ import annotations

import csv
import logging
from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _DayRow:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume_lots: float


class DailyIndex:
    def __init__(self, rows: dict[str, list[_DayRow]], limitup: set[tuple[str, str]]) -> None:
        self._rows = rows  # stock_id → 按 date 排序的日線
        self._limitup = limitup  # {(stock_id, date)}

    @classmethod
    def load(cls, data_dir: Path) -> DailyIndex:
        rows: dict[str, list[_DayRow]] = {}
        with (data_dir / "daily" / "prices.csv").open("r", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                rows.setdefault(r["stock_id"], []).append(
                    _DayRow(
                        date=r["date"],
                        open=float(r["open"]),
                        high=float(r["high"]),
                        low=float(r["low"]),
                        close=float(r["close"]),
                        volume_lots=float(r["volume_lots"]),
                    )
                )
        for lst in rows.values():
            lst.sort(key=lambda x: x.date)
        limitup: set[tuple[str, str]] = set()
        with (data_dir / "events" / "limitup_all.csv").open("r", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                limitup.add((r["stock_id"], r["date"]))
        logger.info("DailyIndex: %d stocks, %d limitup events", len(rows), len(limitup))
        return cls(rows, limitup)

    def _find(self, stock_id: str, date: str) -> tuple[list[_DayRow], int] | None:
        lst = self._rows.get(stock_id)
        if not lst:
            return None
        i = bisect_left([r.date for r in lst], date)
        if i >= len(lst) or lst[i].date != date:
            return None
        return lst, i

    def open_of(self, stock_id: str, date: str) -> float | None:
        hit = self._find(stock_id, date)
        return hit[0][hit[1]].open if hit else None

    def one_price(self, stock_id: str, date: str) -> bool | None:
        hit = self._find(stock_id, date)
        if not hit:
            return None
        row = hit[0][hit[1]]
        return row.high == row.low

    def adv20(self, stock_id: str, date: str) -> float | None:
        hit = self._find(stock_id, date)
        if not hit:
            return None
        lst, i = hit
        window = lst[max(0, i - 19) : i + 1]
        return sum(r.volume_lots for r in window) / len(window)

    def next_date(self, stock_id: str, date: str) -> str | None:
        hit = self._find(stock_id, date)
        if not hit:
            return None
        lst, i = hit
        return lst[i + 1].date if i + 1 < len(lst) else None

    def is_limitup(self, stock_id: str, date: str) -> bool:
        return (stock_id, date) in self._limitup

    def board_streak(self, stock_id: str, date: str) -> int:
        hit = self._find(stock_id, date)
        if not hit or not self.is_limitup(stock_id, date):
            return 0
        lst, i = hit
        streak = 0
        while i >= 0 and self.is_limitup(stock_id, lst[i].date):
            streak += 1
            i -= 1
        return streak
