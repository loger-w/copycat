"""events.csv 分點標籤:brokers store × watchlist → broker_ids 就地補值.

標籤語意(change-spec SC-2,寫死、與 neigui 舊池一致):watchlist broker ∈ 該股
T 日 **top-5 淨買超**(net = buy − sell,排序 net desc、tie-break broker_id asc)。
(2026-07-15 Phase 7 實證修正:top-30 是 neigui 儲存層截斷,標籤準則是 top-5 ——
對既有 1,029 筆重算,top-5 一致率 100.00%、top-30 僅 48.98% 且 mismatch 全為
old ⊂ new;佐證 = neigui event_top5.csv 與 strategy.md「top-5 買超」。)
只補空值不改既有值(冪等);--verify-existing 對既有非空 broker_ids 重算比對,
輸出一致率(不寫檔)。
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

from copycat.data.backfill_brokers import read_brokers
from copycat.fileio import atomic_open_text
from copycat.watchlist import load_watchlist

logger = logging.getLogger(__name__)

_TOP_N = 5


def top_netbuy_hits(brokers: list[dict[str, object]], watchlist_ids: frozenset[str]) -> list[str]:
    """top-5 淨買超中的 watchlist 命中(回傳 broker_id asc;命中順序不進語意)."""
    ranked = sorted(
        brokers,
        key=lambda b: (
            -(int(str(b.get("buy", 0))) - int(str(b.get("sell", 0)))),
            str(b.get("broker_id", "")),
        ),
    )
    top = ranked[:_TOP_N]
    return sorted(str(b["broker_id"]) for b in top if str(b.get("broker_id")) in watchlist_ids)


def label_events(
    data_dir: Path,
    events_csv: Path,
    watchlist_path: Path,
    verify_existing: bool = False,
) -> dict[str, int]:
    watchlist = load_watchlist(watchlist_path)
    with events_csv.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    stats = {
        "labeled_hit": 0,
        "labeled_no_hit": 0,
        "uncovered": 0,
        "already_labeled": 0,
        "verified_matched": 0,
        "verified_mismatched": 0,
        "verified_uncovered": 0,
    }

    changed = False
    for r in rows:
        existing = r.get("broker_ids", "").strip()
        if verify_existing:
            if not existing:
                continue
            brokers = read_brokers(data_dir, r["stock_id"], r["date"])
            if brokers is None:
                stats["verified_uncovered"] += 1
                continue
            recomputed = set(top_netbuy_hits(brokers, watchlist.broker_ids))
            if recomputed == set(existing.split("|")):
                stats["verified_matched"] += 1
            else:
                stats["verified_mismatched"] += 1
                logger.warning(
                    "標籤不一致 %s %s:既有=%s 重算=%s",
                    r["stock_id"],
                    r["date"],
                    existing,
                    "|".join(sorted(recomputed)),
                )
            continue

        if existing:  # 只補空值,不改既有值(SC-2 白名單)
            stats["already_labeled"] += 1
            continue
        brokers = read_brokers(data_dir, r["stock_id"], r["date"])
        if brokers is None:
            stats["uncovered"] += 1
            continue
        hits = top_netbuy_hits(brokers, watchlist.broker_ids)
        if hits:
            r["broker_ids"] = "|".join(hits)
            stats["labeled_hit"] += 1
            changed = True
        else:
            stats["labeled_no_hit"] += 1

    if changed and not verify_existing:
        with atomic_open_text(events_csv) as fh:
            w = csv.DictWriter(fh, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)

    logger.info("label-events(%s):%s", watchlist.name, stats)
    return stats
