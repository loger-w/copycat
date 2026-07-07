"""對事件清單跑引擎(T 日 LockTracker → EventContext → T+1 T1Tracker)."""

from __future__ import annotations

import csv
import dataclasses
import json
import logging
from pathlib import Path

from copycat.data.daily import DailyIndex
from copycat.data.store import read_bars
from copycat.replay.report import write_summary
from copycat.engine.lock_quality import LockTracker
from copycat.engine.t1_open import EventContext, T1Tracker
from copycat.strategy_config import StrategyConfig, load_config
from copycat.watchlist import load_watchlist

logger = logging.getLogger(__name__)


def _cohort(source: str, broker_ids: str, members: frozenset[str]) -> str:
    if source == "control":
        return "control"
    brokers = set(broker_ids.split("|")) if broker_ids else set()
    return "tiger" if brokers & members else "excluded"


def run_replay(
    data_dir: Path, watchlist_path: Path, out_dir: Path, config_path: Path | None = None
) -> Path:
    cfg = load_config(config_path) if config_path else StrategyConfig.default()
    wl = load_watchlist(watchlist_path)
    daily = DailyIndex.load(data_dir)
    run_dir = out_dir / wl.name
    run_dir.mkdir(parents=True, exist_ok=True)

    counts = {"tiger": 0, "control": 0, "excluded": 0}
    missing_t = 0
    missing_t1 = 0
    n_events = 0
    with (
        (data_dir / "events" / "events.csv").open("r", encoding="utf-8") as fh,
        (run_dir / "events.jsonl").open("w", encoding="utf-8") as out,
    ):
        for ev in csv.DictReader(fh):
            n_events += 1
            cohort = _cohort(ev["source"], ev["broker_ids"], wl.broker_ids)
            counts[cohort] += 1
            limit = float(ev["limitup_close"])
            skip: list[str] = []

            lock_sig = None
            t_bars = read_bars(data_dir, ev["stock_id"], ev["date"])
            if t_bars is None:
                skip.append("missing_t_1k")
                missing_t += 1
            else:
                tracker = LockTracker(cfg, limit)
                for b in t_bars:
                    tracker.feed(b)
                lock_sig = tracker.finalize()

            t1_sig = None
            again = False
            if not ev["t1_date"]:
                skip.append("no_t1_date")
            else:
                again = daily.is_limitup(ev["stock_id"], ev["t1_date"])
                t1_bars = read_bars(data_dir, ev["stock_id"], ev["t1_date"])
                if t1_bars is None:
                    skip.append("missing_t1_1k")
                    missing_t1 += 1
                else:
                    ctx = EventContext(
                        stock_id=ev["stock_id"],
                        date=ev["date"],
                        t1_date=ev["t1_date"],
                        limit=limit,
                        adv20_lots=daily.adv20(ev["stock_id"], ev["date"]),
                        one_price=daily.one_price(ev["stock_id"], ev["date"]),
                        board_streak=daily.board_streak(ev["stock_id"], ev["date"]),
                        lock=lock_sig,
                    )
                    t1 = T1Tracker(cfg, ctx)
                    for b in t1_bars:
                        t1.feed(b)
                    t1_sig = t1.finalize(again)

            out.write(
                json.dumps(
                    {
                        "stock_id": ev["stock_id"],
                        "date": ev["date"],
                        "t1_date": ev["t1_date"],
                        "source": ev["source"],
                        "cohort": cohort,
                        "broker_ids": ev["broker_ids"],
                        "again": again,
                        "lock": dataclasses.asdict(lock_sig) if lock_sig else None,
                        "t1": dataclasses.asdict(t1_sig) if t1_sig else None,
                        "skip": skip,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    meta = {
        "watchlist": wl.name,
        "config_path": str(config_path) if config_path else "(default)",
        "n_events": n_events,
        "n_tiger": counts["tiger"],
        "n_control": counts["control"],
        "n_excluded": counts["excluded"],
        "missing_t": missing_t,
        "missing_t1": missing_t1,
    }
    (run_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_summary(run_dir)
    logger.info("replay 完成: %s", meta)
    return run_dir
