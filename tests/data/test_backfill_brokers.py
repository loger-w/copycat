"""backfill-brokers:分點日報回補(聚合/manifest 續傳/空回應/冪等;change-spec SC-1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from copycat.data.backfill_brokers import (
    aggregate_brokers,
    brokers_path,
    read_brokers,
    run_backfill_brokers,
)


def _write_events(path: Path, rows: list[tuple[str, str]]) -> None:
    lines = ["stock_id,date,stock_name,limitup_close,t1_date,source,broker_ids"]
    for sid, d in rows:
        lines.append(f"{sid},{d},,10.0,2026-01-02,scan,")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_aggregate_sums_price_level_rows_per_broker() -> None:
    rows: list[dict[str, object]] = [
        {"securities_trader_id": "9227", "securities_trader": "凱基城中", "buy": 1000, "sell": 0},
        {"securities_trader_id": "9227", "securities_trader": "凱基城中", "buy": 500, "sell": 200},
        {"securities_trader_id": "5854", "securities_trader": "統一城中", "buy": 300, "sell": 100},
    ]
    agg = aggregate_brokers(rows)
    assert agg == [
        {"broker_id": "5854", "name": "統一城中", "buy": 300, "sell": 100},
        {"broker_id": "9227", "name": "凱基城中", "buy": 1500, "sell": 200},
    ]


def test_backfill_writes_full_broker_file(tmp_path: Path) -> None:
    events = tmp_path / "events.csv"
    _write_events(events, [("2330", "2026-01-01")])

    def fetch(sid: str, day: str) -> list[dict[str, object]]:
        return [
            {"securities_trader_id": "9227", "securities_trader": "凱基城中", "buy": 9, "sell": 1}
        ]

    stats = run_backfill_brokers(tmp_path, events, token="t", fetch=fetch)
    assert stats["fetched"] == 1
    brokers = read_brokers(tmp_path, "2330", "2026-01-01")
    assert brokers == [{"broker_id": "9227", "name": "凱基城中", "buy": 9, "sell": 1}]
    manifest = json.loads((tmp_path / "brokers" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["done"] == ["2330|2026-01-01"]


def test_manifest_resume_skips_done(tmp_path: Path) -> None:
    events = tmp_path / "events.csv"
    _write_events(events, [("2330", "2026-01-01"), ("1101", "2026-01-01")])
    (tmp_path / "brokers").mkdir(parents=True)
    (tmp_path / "brokers" / "manifest.json").write_text(
        json.dumps({"done": ["2330|2026-01-01"]}), encoding="utf-8"
    )
    calls: list[str] = []

    def fetch(sid: str, day: str) -> list[dict[str, object]]:
        calls.append(sid)
        return [{"securities_trader_id": "9600", "securities_trader": "富邦", "buy": 1, "sell": 0}]

    stats = run_backfill_brokers(tmp_path, events, token="t", fetch=fetch)
    assert calls == ["1101"]
    assert stats["skipped"] == 1


def test_existing_file_skipped_idempotent(tmp_path: Path) -> None:
    events = tmp_path / "events.csv"
    _write_events(events, [("2330", "2026-01-01")])
    path = brokers_path(tmp_path, "2330", "2026-01-01")
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"stock_id": "2330", "date": "2026-01-01", "brokers": []}), encoding="utf-8"
    )

    def fetch(sid: str, day: str) -> list[dict[str, object]]:
        raise AssertionError("不應呼叫 fetch")

    stats = run_backfill_brokers(tmp_path, events, token="t", fetch=fetch)
    assert stats["fetched"] == 0
    assert stats["skipped"] == 1


def test_empty_response_not_in_manifest(tmp_path: Path) -> None:
    events = tmp_path / "events.csv"
    _write_events(events, [("2330", "2026-01-01")])

    def fetch(sid: str, day: str) -> list[dict[str, object]]:
        return []

    stats = run_backfill_brokers(tmp_path, events, token="t", fetch=fetch)
    assert stats["empty"] == 1
    assert read_brokers(tmp_path, "2330", "2026-01-01") is None
    manifest = json.loads((tmp_path / "brokers" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["done"] == []


def test_quota_error_propagates(tmp_path: Path) -> None:
    events = tmp_path / "events.csv"
    _write_events(events, [("2330", "2026-01-01")])

    def fetch(sid: str, day: str) -> list[dict[str, object]]:
        raise RuntimeError("FinMind 配額用盡(HTTP 402),停止回補")

    with pytest.raises(RuntimeError, match="402"):
        run_backfill_brokers(tmp_path, events, token="t", fetch=fetch)


def test_limit_caps_fetch_count(tmp_path: Path) -> None:
    events = tmp_path / "events.csv"
    _write_events(events, [("2330", "2026-01-01"), ("1101", "2026-01-01"), ("2317", "2026-01-02")])

    def fetch(sid: str, day: str) -> list[dict[str, object]]:
        return [{"securities_trader_id": "9600", "securities_trader": "富邦", "buy": 1, "sell": 0}]

    stats = run_backfill_brokers(tmp_path, events, token="t", fetch=fetch, limit=2)
    assert stats["fetched"] == 2
