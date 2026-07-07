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
from copycat.engine.t1_open import EventContext, T1Tracker, gap_bucket_label
from copycat.strategy_config import StrategyConfig, load_config
from copycat.watchlist import load_watchlist

logger = logging.getLogger(__name__)


def _load_tick_auction(data_dir: Path) -> dict[tuple[str, str], float]:
    path = data_dir / "events" / "tick_auction.csv"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return {(r["stock_id"], r["date"]): float(r["auction_lots"]) for r in csv.DictReader(fh)}


def _t1_daily_fallback(
    cfg: StrategyConfig, daily: DailyIndex, ev: dict[str, str], limit: float
) -> dict | None:
    """T+1 1K 缺但日線在:給出日線可得的部分訊號(golden gap 矩陣同源為日線)."""
    row = daily.ohlc(ev["stock_id"], ev["t1_date"])
    if row is None:
        return None
    o, h, _low, c = row
    if o <= 0:
        return None
    gap = o / limit - 1
    return {
        "open_px": o,
        "gap": gap,
        "gap_bucket": gap_bucket_label(cfg, gap),
        "auction_lots": None,
        "auction_share_adv20": None,
        "auction_tell": "n/a",
        "auction_share_dayvol": None,
        "inner15": None,
        "high_idx": None,
        "high_time": None,
        "high_vs_open": h / o - 1,
        "close_vs_open": c / o - 1,
        "touched_limit": h >= limit * cfg.t1_limit_mult - cfg.limit_eps,
        "path": "(daily)",
        "daily_fallback": True,
    }


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
    tick_auction = _load_tick_auction(data_dir)
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

            t1_out: dict | None = None
            again = False
            if not ev["t1_date"]:
                skip.append("no_t1_date")
            else:
                again = daily.is_limitup(ev["stock_id"], ev["t1_date"])
                t1_bars = read_bars(data_dir, ev["stock_id"], ev["t1_date"])
                if t1_bars is None:
                    skip.append("missing_t1_1k")
                    missing_t1 += 1
                    t1_out = _t1_daily_fallback(cfg, daily, ev, limit)
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
                        t1_open_px=daily.open_of(ev["stock_id"], ev["t1_date"]),
                        auction_lots_tick=tick_auction.get((ev["stock_id"], ev["t1_date"])),
                    )
                    t1 = T1Tracker(cfg, ctx)
                    for b in t1_bars:
                        t1.feed(b)
                    t1_sig = t1.finalize(again)
                    if t1_sig is not None:
                        t1_out = dataclasses.asdict(t1_sig)
                        t1_out["daily_fallback"] = False
                    else:
                        # 1K 在但無有效量(處置股分盤等)→ 日線 fallback
                        skip.append("t1_1k_empty")
                        t1_out = _t1_daily_fallback(cfg, daily, ev, limit)

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
                        "t1": t1_out,
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
