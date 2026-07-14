"""scan_events 單元測試:漲停判定、冪等、limitup_all 同步、空 t1_date 修復."""

from __future__ import annotations

import csv
from pathlib import Path

from copycat.data.daily import DailyIndex
from copycat.data.scan_events import scan_limitup_events


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


_PRICE_FIELDS = ["stock_id", "date", "open", "high", "low", "close", "spread", "volume_lots"]


def _price(sid: str, date: str, close: float, spread: float) -> dict[str, str]:
    return {
        "stock_id": sid,
        "date": date,
        "open": str(close),
        "high": str(close),
        "low": str(close),
        "close": str(close),
        "spread": str(spread),
        "volume_lots": "100",
    }


def _setup(tmp_path: Path) -> Path:
    # 2330:07-01 收 10.0 → 07-02 收 11.0(= limit_up_price(10.0))漲停,07-03 收 11.0(非漲停,spread 0)
    # 1101:07-02 收 10.5(非漲停)
    prices = [
        _price("2330", "2026-07-01", 10.0, 0.0),
        _price("2330", "2026-07-02", 11.0, 1.0),  # ref_prev_close = 11.0 - 1.0 = 10.0 → 漲停
        _price("2330", "2026-07-03", 11.0, 0.0),  # ref = 11.0,limit=12.1 ≠ 11.0
        _price("1101", "2026-07-01", 10.0, 0.0),
        _price("1101", "2026-07-02", 10.5, 0.5),
    ]
    _write_csv(tmp_path / "daily" / "prices.csv", _PRICE_FIELDS, prices)
    _write_csv(
        tmp_path / "events" / "limitup_all.csv",
        ["stock_id", "date", "close"],
        [{"stock_id": "9999", "date": "2026-06-01", "close": "5.0"}],
    )
    _write_csv(
        tmp_path / "events" / "events.csv",
        ["stock_id", "date", "stock_name", "limitup_close", "t1_date", "source", "broker_ids"],
        [
            {
                "stock_id": "1101",
                "date": "2026-07-01",
                "stock_name": "台泥",
                "limitup_close": "10.0",
                "t1_date": "",  # 空 t1:daily 有 07-02 → 應修復
                "source": "tiger_csv",
                "broker_ids": "9227",
            }
        ],
    )
    return tmp_path


def test_scan_detects_limitup_and_appends(tmp_path: Path) -> None:
    data = _setup(tmp_path)
    stats = scan_limitup_events(data, "2026-07-01", "2026-07-03")
    assert stats["events_appended"] == 1
    with (data / "events" / "events.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    new = [r for r in rows if r["source"] == "scan"]
    assert len(new) == 1
    assert new[0]["stock_id"] == "2330"
    assert new[0]["date"] == "2026-07-02"
    assert new[0]["t1_date"] == "2026-07-03"
    assert new[0]["broker_ids"] == ""


def test_scan_idempotent(tmp_path: Path) -> None:
    data = _setup(tmp_path)
    scan_limitup_events(data, "2026-07-01", "2026-07-03")
    stats2 = scan_limitup_events(data, "2026-07-01", "2026-07-03")
    assert stats2["events_appended"] == 0
    assert stats2["limitup_appended"] == 0
    assert stats2["t1_fixed"] == 0


def test_scan_syncs_limitup_all_and_is_limitup(tmp_path: Path) -> None:
    data = _setup(tmp_path)
    stats = scan_limitup_events(data, "2026-07-01", "2026-07-03")
    assert stats["limitup_appended"] == 1
    daily = DailyIndex.load(data)
    assert daily.is_limitup("2330", "2026-07-02")
    assert daily.board_streak("2330", "2026-07-02") == 1


def test_scan_fixes_empty_t1_date(tmp_path: Path) -> None:
    data = _setup(tmp_path)
    stats = scan_limitup_events(data, "2026-07-01", "2026-07-03")
    assert stats["t1_fixed"] == 1
    with (data / "events" / "events.csv").open(encoding="utf-8") as fh:
        rows = {(r["stock_id"], r["date"]): r for r in csv.DictReader(fh)}
    assert rows[("1101", "2026-07-01")]["t1_date"] == "2026-07-02"


def test_scan_skips_non_limitup(tmp_path: Path) -> None:
    data = _setup(tmp_path)
    scan_limitup_events(data, "2026-07-01", "2026-07-03")
    with (data / "events" / "events.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert not any(r["stock_id"] == "2330" and r["date"] == "2026-07-03" for r in rows)
    assert not any(r["stock_id"] == "1101" and r["date"] == "2026-07-02" for r in rows)


def test_scan_rerun_preserves_existing_broker_ids(tmp_path: Path) -> None:
    """R11 characterization:scan-events 重跑不得清空既有列的 broker_ids(每日更新鏈契約)."""
    data = _setup(tmp_path)
    scan_limitup_events(data, "2026-07-01", "2026-07-03")
    scan_limitup_events(data, "2026-07-01", "2026-07-03")  # 冪等重跑
    with (data / "events" / "events.csv").open(encoding="utf-8") as fh:
        rows = {(r["stock_id"], r["date"]): r for r in csv.DictReader(fh)}
    assert rows[("1101", "2026-07-01")]["broker_ids"] == "9227"
