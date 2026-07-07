from __future__ import annotations

import json
from pathlib import Path

from copycat.replay.report import agg_gap_buckets, agg_lock_buckets, med, write_summary


def _event(gap_bucket: str, gap: float, close_vs_open: float, again: bool,
           lock_bucket: str = "<09:05", lock_idx: int = 0) -> dict:
    return {
        "stock_id": "1104", "date": "2025-09-10", "cohort": "tiger", "again": again,
        "skip": [],
        "lock": {"lock_time_bucket": lock_bucket, "lock_idx": lock_idx,
                 "violent_pull": False, "queue_bucket": ">=40%", "n_reopens": 0},
        "t1": {"gap": gap, "gap_bucket": gap_bucket, "close_vs_open": close_vs_open,
               "touched_limit": False, "auction_share_dayvol": 0.05,
               "auction_tell": "3-8%"},
    }


def test_med_matches_research_convention() -> None:
    assert med([1.0, 2.0, 4.0, 8.0]) == 4.0  # sorted[n//2],非平均中位


def test_agg_lock_buckets() -> None:
    events = [_event("3-7%", 0.05, 0.01, again=True),
              _event("3-7%", 0.03, -0.02, again=False)]
    rows = agg_lock_buckets(events, "tiger")
    b = next(r for r in rows if r["bucket"] == "<09:05")
    assert b["n"] == 2 and b["med_gap"] == 0.05 and b["again_rate"] == 0.5


def test_agg_gap_buckets_share_and_pwin() -> None:
    events = [_event("3-7%", 0.05, 0.01, True), _event("1-3%", 0.02, -0.02, False)]
    rows = agg_gap_buckets(events, "tiger")
    r37 = next(r for r in rows if r["bucket"] == "3-7%")
    assert r37["n"] == 1 and r37["share"] == 0.5 and r37["p_win"] == 1.0


def test_write_summary(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with (run_dir / "events.jsonl").open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(_event("3-7%", 0.05, 0.01, True), ensure_ascii=False) + "\n")
    out = write_summary(run_dir)
    text = out.read_text(encoding="utf-8")
    assert "鎖板時間" in text and "gap 分桶" in text and "cohort=tiger" in text
