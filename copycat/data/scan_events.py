"""自產漲停事件掃描:daily prices → 收盤漲停 → append events.csv + limitup_all.csv.

取代 neigui 種子池的滾動延伸(種子池截止 2026-06-26,CLAUDE.md §8 邊界教訓)。
冪等:已存在 (stock_id, date) 不重複 append;同時修復既有空 t1_date rows
(事件日當時 daily 無次一交易日 → 回補 daily 後可推導)。
limitup_all.csv 必須同步(DailyIndex.is_limitup / board_streak / prev_limitup 的資料源,
不同步會讓新期間連板特徵過期)。
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

from copycat.data.daily import DailyIndex
from copycat.fileio import atomic_open_text
from copycat.market import limit_up_price

logger = logging.getLogger(__name__)

_LIMIT_EPS = 1e-6


def _read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        return fieldnames, list(reader)


def _write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with atomic_open_text(path) as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def scan_limitup_events(data_dir: Path, start: str, end: str) -> dict[str, int]:
    """掃描 [start, end] 收盤漲停事件,冪等 append;回傳統計."""
    daily = DailyIndex.load(data_dir)

    events_path = data_dir / "events" / "events.csv"
    ev_fields, ev_rows = _read_rows(events_path)
    existing = {(r["stock_id"], r["date"]) for r in ev_rows}

    t1_fixed = 0
    for r in ev_rows:
        if not r["t1_date"]:
            t1 = daily.next_date(r["stock_id"], r["date"])
            if t1:
                r["t1_date"] = t1
                t1_fixed += 1

    lu_path = data_dir / "events" / "limitup_all.csv"
    lu_fields, lu_rows = _read_rows(lu_path)
    lu_existing = {(r["stock_id"], r["date"]) for r in lu_rows}

    scanned = 0
    appended = 0
    lu_appended = 0
    with (data_dir / "daily" / "prices.csv").open("r", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            d = r["date"]
            if d < start or d > end:
                continue
            sid = r["stock_id"]
            scanned += 1
            try:
                close = float(r["close"])
            except ValueError:
                continue
            if close <= 0:
                continue
            ref = daily.ref_prev_close(sid, d)
            if ref is None:
                continue
            if abs(close - limit_up_price(ref)) > _LIMIT_EPS:
                continue

            if (sid, d) not in lu_existing:
                lu_rows.append(
                    {k: "" for k in lu_fields}
                    | {"stock_id": sid, "date": d}
                    | ({"close": str(close)} if "close" in lu_fields else {})
                )
                lu_existing.add((sid, d))
                lu_appended += 1

            if (sid, d) in existing:
                continue
            ev_rows.append(
                {
                    "stock_id": sid,
                    "date": d,
                    "stock_name": "",
                    "limitup_close": str(close),
                    "t1_date": daily.next_date(sid, d) or "",
                    "source": "scan",
                    "broker_ids": "",
                }
            )
            existing.add((sid, d))
            appended += 1

    _write_rows(events_path, ev_fields, ev_rows)
    _write_rows(lu_path, lu_fields, lu_rows)
    logger.info(
        "scan-events [%s..%s]: scanned=%d appended=%d limitup_appended=%d t1_fixed=%d",
        start,
        end,
        scanned,
        appended,
        lu_appended,
        t1_fixed,
    )
    return {
        "scanned_rows": scanned,
        "events_appended": appended,
        "limitup_appended": lu_appended,
        "t1_fixed": t1_fixed,
    }
