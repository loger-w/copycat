from __future__ import annotations

import json
from pathlib import Path

import pytest

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
    # T+1 1K 缺,但日線在 → 部分訊號 fallback(gap 可算、盤中欄位 None)
    assert "missing_t1_1k" in ctrl["skip"]
    assert ctrl["t1"] is not None and ctrl["t1"]["daily_fallback"] is True
    assert ctrl["t1"]["gap"] == pytest.approx(51.0 / 50.0 - 1)
    assert ctrl["t1"]["gap_bucket"] == "1-3%"
    assert ctrl["t1"]["auction_share_dayvol"] is None and ctrl["t1"]["inner15"] is None

    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["n_tiger"] == 1 and meta["n_control"] == 1 and meta["missing_t1"] == 1


def test_t1_zero_volume_falls_back_to_daily(imported_data: Path, watchlist_four: Path,
                                            tmp_path: Path) -> None:
    # 處置股分盤:T+1 1K 在但全零量 → finalize None → 日線 fallback
    from copycat.data.models import Bar1K
    from copycat.data.store import write_bars

    zero = [Bar1K(m=0, open=33.0, high=33.0, low=33.0, close=33.0,
                  volume=0.0, up_volume=0.0, down_volume=0.0, unch_volume=0.0)]
    write_bars(imported_data, "1104", "2025-09-11", zero)
    run_dir = run_replay(imported_data, watchlist_four, tmp_path / "out3")
    lines = [json.loads(x) for x in
             (run_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    ev = next(e for e in lines if e["stock_id"] == "1104")
    assert "t1_1k_empty" in ev["skip"]
    assert ev["t1"] is not None and ev["t1"]["daily_fallback"] is True
    assert ev["t1"]["gap"] == pytest.approx(33.6 / 32.0 - 1)  # 日線 open 33.6


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
