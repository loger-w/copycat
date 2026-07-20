from __future__ import annotations

import json
from pathlib import Path

from copycat.replay.validate import _within_pp, _within_rel, format_validate, run_validate


def test_within_rel() -> None:
    assert _within_rel(actual=100, golden=104, tol=0.05) is True
    assert _within_rel(actual=100, golden=111, tol=0.05) is False


def test_within_pp() -> None:
    assert _within_pp(actual=0.074, golden=0.070, tol=0.005) is True
    assert _within_pp(actual=0.074, golden=0.060, tol=0.005) is False
    assert _within_pp(actual=None, golden=0.06, tol=0.005) is False  # 缺值 = FAIL


def _ev(source: str, **over: object) -> dict:
    ev = {
        "source": source,
        "cohort": "tiger",
        "again": False,
        "skip": [],
        "lock": {
            "lock_time_bucket": "<09:05",
            "violent_pull": False,
            "lock_idx": 2,
            "queue_bucket": ">=40%",
        },
        "t1": {
            "gap": 0.05,
            "gap_bucket": "<0%",
            "close_vs_open": 0.01,
            "touched_limit": False,
            "auction_share_dayvol": 0.05,
            "auction_tell": "<3%",
        },
    }
    ev.update(over)
    return ev


def _write_run(run_dir: Path, events: list[dict]) -> Path:
    run_dir.mkdir(parents=True)
    (run_dir / "events.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events), encoding="utf-8"
    )
    return run_dir


def test_run_validate_ignores_scan_events(tmp_path: Path) -> None:
    """Gate 凍結在種子池(tiger_csv/control):scan 事件不得影響任何一格 actual."""
    seed = [
        _ev("tiger_csv"),
        _ev("tiger_csv", again=True),
        _ev("control", cohort="control"),
    ]
    noise = [
        _ev(
            "scan",
            again=True,
            lock={
                "lock_time_bucket": "<09:05",
                "violent_pull": True,
                "lock_idx": 0,
                "queue_bucket": "<15%",
            },
        ),
        _ev(
            "scan",
            t1={
                "gap": 0.09,
                "gap_bucket": "漲停開",
                "close_vs_open": -0.08,
                "touched_limit": True,
                "auction_share_dayvol": 0.5,
                "auction_tell": ">=8%",
            },
        ),
    ]
    run5_a = _write_run(tmp_path / "a5", seed)
    run4_a = _write_run(tmp_path / "a4", seed)
    run5_b = _write_run(tmp_path / "b5", seed + noise)
    run4_b = _write_run(tmp_path / "b4", seed + noise)

    actual_a = [(c["sc"], c["name"], c["actual"]) for c in run_validate(run5_a, run4_a)]
    actual_b = [(c["sc"], c["name"], c["actual"]) for c in run_validate(run5_b, run4_b)]
    assert actual_a == actual_b


def test_format_validate_marks_fail() -> None:
    checks = [
        {"sc": "SC-2", "name": "x", "golden": "175", "actual": "170", "tol": "±5%", "ok": True},
        {
            "sc": "SC-5",
            "name": "y",
            "golden": "+0.72%",
            "actual": "+2.0%",
            "tol": "±0.5pp",
            "ok": False,
        },
    ]
    text = format_validate(checks)
    assert "PASS" in text and "FAIL" in text
