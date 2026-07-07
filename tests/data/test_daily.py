from __future__ import annotations

import csv
from pathlib import Path

from copycat.data.daily import DailyIndex


def _write_fixture(tmp_path: Path) -> None:
    daily = tmp_path / "daily"
    events = tmp_path / "events"
    daily.mkdir()
    events.mkdir()
    rows = [
        # 3 個交易日,量 100/200/300 張
        {
            "stock_id": "1101",
            "date": "2026-07-01",
            "open": "10.0",
            "high": "10.5",
            "low": "9.9",
            "close": "10.2",
            "volume_lots": "100",
        },
        {
            "stock_id": "1101",
            "date": "2026-07-02",
            "open": "10.2",
            "high": "11.2",
            "low": "11.2",
            "close": "11.2",
            "volume_lots": "200",
        },
        {
            "stock_id": "1101",
            "date": "2026-07-03",
            "open": "11.5",
            "high": "12.3",
            "low": "11.4",
            "close": "12.3",
            "volume_lots": "300",
        },
    ]
    with (daily / "prices.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with (events / "limitup_all.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["stock_id", "date", "close"])
        w.writeheader()
        # 07-02 與 07-03 連續漲停
        w.writerow({"stock_id": "1101", "date": "2026-07-02", "close": "11.2"})
        w.writerow({"stock_id": "1101", "date": "2026-07-03", "close": "12.3"})


def test_open_and_one_price(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    idx = DailyIndex.load(tmp_path)
    assert idx.open_of("1101", "2026-07-03") == 11.5
    assert idx.one_price("1101", "2026-07-02") is True  # high == low(一價到底 proxy)
    assert idx.one_price("1101", "2026-07-03") is False
    assert idx.open_of("9999", "2026-07-03") is None


def test_adv20_partial_window(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    idx = DailyIndex.load(tmp_path)
    # 含當日往前:07-02 的 adv = (100+200)/2
    assert idx.adv20("1101", "2026-07-02") == 150.0


def test_ohlc(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    idx = DailyIndex.load(tmp_path)
    assert idx.ohlc("1101", "2026-07-03") == (11.5, 12.3, 11.4, 12.3)
    assert idx.ohlc("9999", "2026-07-03") is None


def test_next_date(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    idx = DailyIndex.load(tmp_path)
    assert idx.next_date("1101", "2026-07-02") == "2026-07-03"
    assert idx.next_date("1101", "2026-07-03") is None


def test_limitup_and_board_streak(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    idx = DailyIndex.load(tmp_path)
    assert idx.is_limitup("1101", "2026-07-02") is True
    assert idx.is_limitup("1101", "2026-07-01") is False
    assert idx.board_streak("1101", "2026-07-03") == 2  # 07-02、07-03 連兩板
    assert idx.board_streak("1101", "2026-07-02") == 1
    assert idx.board_streak("1101", "2026-07-01") == 0
