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
    spread: float | None = None  # None = 該 row 無 spread 資訊(舊資料),非 0.0


class DailyIndex:
    def __init__(self, rows: dict[str, list[_DayRow]], limitup: set[tuple[str, str]]) -> None:
        self._rows = rows  # stock_id → 按 date 排序的日線
        self._limitup = limitup  # {(stock_id, date)}
        self._dates = {sid: [r.date for r in lst] for sid, lst in rows.items()}  # bisect 索引

    @classmethod
    def load(cls, data_dir: Path) -> DailyIndex:
        rows: dict[str, list[_DayRow]] = {}
        with (data_dir / "daily" / "prices.csv").open("r", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                raw_spread = r.get("spread")
                rows.setdefault(r["stock_id"], []).append(
                    _DayRow(
                        date=r["date"],
                        open=float(r["open"]),
                        high=float(r["high"]),
                        low=float(r["low"]),
                        close=float(r["close"]),
                        volume_lots=float(r["volume_lots"]),
                        # row-level 缺值語意:空字串/缺欄 → None(0.0 是合法的平盤值)
                        spread=float(raw_spread) if raw_spread else None,
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
        i = bisect_left(self._dates[stock_id], date)
        if i >= len(lst) or lst[i].date != date:
            return None
        return lst, i

    def open_of(self, stock_id: str, date: str) -> float | None:
        hit = self._find(stock_id, date)
        return hit[0][hit[1]].open if hit else None

    def ohlc(self, stock_id: str, date: str) -> tuple[float, float, float, float] | None:
        hit = self._find(stock_id, date)
        if not hit:
            return None
        row = hit[0][hit[1]]
        return (row.open, row.high, row.low, row.close)

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

    def prev_date(self, stock_id: str, date: str) -> str | None:
        return self.shift_date(stock_id, date, 1)

    def shift_date(self, stock_id: str, date: str, n: int) -> str | None:
        """n 個交易日前的 date;不足 → None."""
        hit = self._find(stock_id, date)
        if not hit:
            return None
        lst, i = hit
        return lst[i - n].date if i - n >= 0 else None

    def close_of(self, stock_id: str, date: str) -> float | None:
        hit = self._find(stock_id, date)
        return hit[0][hit[1]].close if hit else None

    def volume_of(self, stock_id: str, date: str) -> float | None:
        hit = self._find(stock_id, date)
        return hit[0][hit[1]].volume_lots if hit else None

    def ref_prev_close(self, stock_id: str, date: str) -> float | None:
        """參考前收 = close − spread(neigui 同源,除權息安全);≤0 → None。

        該 row 無 spread 資訊(None)→ fallback 前一交易日 close(row-level,
        混合新舊資料安全;重跑 import 後全 row 有值)。
        """
        hit = self._find(stock_id, date)
        if not hit:
            return None
        lst, i = hit
        spread = lst[i].spread
        if spread is not None:
            v = lst[i].close - spread
            return v if v > 0 else None
        if i == 0:
            return None
        v = lst[i - 1].close
        return v if v > 0 else None

    def _close_window(self, stock_id: str, date: str, n: int) -> list[float] | None:
        """含當日往前 n 個 close;不足 → None."""
        hit = self._find(stock_id, date)
        if not hit:
            return None
        lst, i = hit
        if i - n + 1 < 0:
            return None
        return [r.close for r in lst[i - n + 1 : i + 1]]

    def ma(self, stock_id: str, date: str, n: int) -> float | None:
        window = self._close_window(stock_id, date, n)
        return sum(window) / n if window else None

    def bb_width(self, stock_id: str, date: str, n: int, k: float) -> float | None:
        """布林帶寬 = 2kσ/MA(母體 σ);MA ≤ 0 或資料不足 → None."""
        window = self._close_window(stock_id, date, n)
        if not window:
            return None
        mean = sum(window) / n
        if mean <= 0:
            return None
        var = sum((c - mean) ** 2 for c in window) / n
        return 2 * k * (var**0.5) / mean

    def bb_width_pct(self, stock_id: str, date: str, n: int, k: float, window: int) -> float | None:
        """當日帶寬在近 window 日帶寬中的百分位 rank(嚴格小於比例);資料不足 → None."""
        hit = self._find(stock_id, date)
        if not hit:
            return None
        lst, i = hit
        widths: list[float] = []
        for j in range(i - window + 1, i + 1):
            if j < 0:
                return None
            w = self.bb_width(stock_id, lst[j].date, n, k)
            if w is None:
                return None
            widths.append(w)
        today = widths[-1]
        others = widths[:-1]
        if not others:
            return 0.0
        return sum(1 for w in others if w < today) / len(others)

    def pos_52w(self, stock_id: str, date: str) -> float | None:
        """(close − 250 日低)/(高 − 低);不足 60 日或高 == 低 → None."""
        hit = self._find(stock_id, date)
        if not hit:
            return None
        lst, i = hit
        window = [r.close for r in lst[max(0, i - 249) : i + 1]]
        if len(window) < 60:
            return None
        lo, hi = min(window), max(window)
        if hi == lo:
            return None
        return (lst[i].close - lo) / (hi - lo)

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
