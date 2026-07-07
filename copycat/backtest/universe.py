"""樣本宇宙(design §2 universe / D7 limit 分軌)— 分組由 watchlist 輸入,不 hardcode 分點."""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

from copycat.backtest.config import BacktestConfig
from copycat.data.daily import DailyIndex
from copycat.market import limit_up_price
from copycat.watchlist import Watchlist

logger = logging.getLogger(__name__)

# 可鎖板留倉的 group(single source;simulate 依此判留倉資格,新分組在此登記)
LOCKABLE_GROUPS = ("tiger_core", "tiger_9600", "ctrl_lock")


@dataclass(frozen=True, slots=True)
class Sample:
    stock_id: str
    date: str
    group: str  # tiger_core / tiger_9600 / ctrl_lock / near_miss
    weight: float
    prev_close: float
    limit_price: float
    t1_date: str | None


def _classify(source: str, broker_ids: str, core: Watchlist, aux: Watchlist) -> str | None:
    if source == "control":
        return "ctrl_lock"
    ids = {b for b in broker_ids.split("|") if b}
    if ids & core.broker_ids:
        return "tiger_core"
    if ids & aux.broker_ids:
        return "tiger_9600"
    return None  # watchlist 外的虎事件 → 剔除記數


def build_universe(
    data_dir: Path,
    daily: DailyIndex,
    core_wl: Watchlist,
    aux_wl: Watchlist,
    cfg: BacktestConfig,
) -> tuple[list[Sample], dict[str, int]]:
    counts = {
        "tiger_no_watchlist": 0,
        "insufficient_prior": 0,
        "missing_prev_close": 0,
        "limit_mismatch": 0,
    }
    samples: list[Sample] = []

    def _add(
        stock_id: str, date: str, group: str, marked_limit: float | None, t1_date: str | None
    ) -> None:
        if daily.shift_date(stock_id, date, cfg.min_prior_days) is None:
            counts["insufficient_prior"] += 1
            return
        prev_close = daily.ref_prev_close(stock_id, date)
        if prev_close is None:
            counts["missing_prev_close"] += 1
            return
        computed = limit_up_price(prev_close)
        if marked_limit is not None:
            # D7:鎖板組用標記,與計算值交叉;矛盾(疑除權息)→ 剔除記數
            if abs(marked_limit - computed) > cfg.limit_eps:
                counts["limit_mismatch"] += 1
                return
            limit = marked_limit
        else:
            limit = computed
        weight = cfg.near_miss_weight if group == "near_miss" else 1.0
        samples.append(
            Sample(
                stock_id=stock_id,
                date=date,
                group=group,
                weight=weight,
                prev_close=prev_close,
                limit_price=limit,
                t1_date=t1_date,
            )
        )

    with (data_dir / "events" / "events.csv").open("r", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            group = _classify(r["source"], r["broker_ids"], core_wl, aux_wl)
            if group is None:
                counts["tiger_no_watchlist"] += 1
                continue
            _add(r["stock_id"], r["date"], group, float(r["limitup_close"]), r["t1_date"] or None)

    with (data_dir / "events" / "near_miss.csv").open("r", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            _add(r["stock_id"], r["date"], "near_miss", None, None)

    if not samples:
        raise ValueError("樣本宇宙為空 — 檢查 data/events/ 與 watchlist")
    samples.sort(key=lambda s: (s.stock_id, s.date))
    logger.info(
        "universe: %d samples, groups=%s, excluded=%s",
        len(samples),
        {g: sum(1 for s in samples if s.group == g) for g in sorted({s.group for s in samples})},
        counts,
    )
    return samples, counts
