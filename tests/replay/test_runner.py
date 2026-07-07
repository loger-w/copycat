from __future__ import annotations

import json
from pathlib import Path

from copycat.replay.runner import run_replay


def test_run_replay(imported_data: Path, watchlist_four: Path, tmp_path: Path) -> None:
    run_dir = run_replay(imported_data, watchlist_four, tmp_path / "out")
    lines = [json.loads(x) for x in
             (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    by_key = {(e["stock_id"], e["date"]): e for e in lines}

    tiger = by_key[("1104", "2025-09-10")]
    assert tiger["cohort"] == "tiger"
    # fixture 的 1104 T 日兩根 bar 全在漲停(32)→ 開盤鎖
    assert tiger["lock"] is not None and tiger["lock"]["lock_time_bucket"] == "<09:05"
    # T+1 開 33 → gap 3.125% → "3-7%"
    assert tiger["t1"] is not None and tiger["t1"]["gap_bucket"] == "3-7%"
    assert tiger["again"] is False

    ctrl = by_key[("2001", "2025-09-10")]
    assert ctrl["cohort"] == "control"
    assert ctrl["t1"] is None and "missing_t1_1k" in ctrl["skip"]

    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["n_tiger"] == 1 and meta["n_control"] == 1 and meta["missing_t1"] == 1


def test_watchlist_excludes(imported_data: Path, tmp_path: Path) -> None:
    # watchlist 只含 9227 → 1104 事件(779c/779Z)變 excluded
    wl = tmp_path / "wl2.json"
    wl.write_text(json.dumps({"name": "kgi_only", "members": [
        {"broker_id": "9227", "name": "凱基城中"}]}), encoding="utf-8")
    run_dir = run_replay(imported_data, wl, tmp_path / "out2")
    lines = [json.loads(x) for x in
             (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    ev = next(e for e in lines if e["stock_id"] == "1104")
    assert ev["cohort"] == "excluded"
