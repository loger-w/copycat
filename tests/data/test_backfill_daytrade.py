"""backfill_daytrade 單元測試:fetch 合併冪等、DayTradeIndex 資格判定."""

from __future__ import annotations

import csv
from pathlib import Path

from copycat.data.backfill_daytrade import DayTradeIndex, run_backfill_daytrade


def _fake_fetch(dataset: str, start: str, end: str) -> list[dict[str, object]]:
    if dataset == "TaiwanStockDayTrading":
        if start == "2026-07-01":
            return [
                {"stock_id": "2330", "date": "2026-07-01", "BuyAfterSale": ""},
                {"stock_id": "1101", "date": "2026-07-01", "BuyAfterSale": ""},
                {"stock_id": "3037", "date": "2026-07-01", "BuyAfterSale": "Y"},  # 禁先賣
                {"stock_id": "6182", "date": "2026-07-01", "BuyAfterSale": "＊"},  # 禁先賣
            ]
        if start == "2026-07-02":
            return [{"stock_id": "2330", "date": "2026-07-02", "BuyAfterSale": ""}]
        return []
    return [
        {"stock_id": "5321", "period_start": "2026-06-28", "period_end": "2026-07-05"},
    ]


def test_run_backfill_writes_and_dedups(tmp_path: Path) -> None:
    stats = run_backfill_daytrade(tmp_path, "2026-07-01", "2026-07-02", "t", fetch=_fake_fetch)
    assert stats["added_rows"] == 5
    assert stats["disposition_rows"] == 1
    stats2 = run_backfill_daytrade(tmp_path, "2026-07-01", "2026-07-02", "t", fetch=_fake_fetch)
    assert stats2["added_rows"] == 0  # manifest 續傳 + (sid,date) 冪等
    with (tmp_path / "daytrade" / "day_trading.csv").open(encoding="utf-8") as fh:
        assert len(list(csv.DictReader(fh))) == 5


def test_index_sell_first_restricted_is_ineligible(tmp_path: Path) -> None:
    # BuyAfterSale 非空('Y' / '＊')= 僅可先買後賣 → 當沖「先賣」策略不可交易
    run_backfill_daytrade(tmp_path, "2026-07-01", "2026-07-02", "t", fetch=_fake_fetch)
    idx = DayTradeIndex.load(tmp_path)
    assert idx is not None
    assert idx.eligible("3037", "2026-07-01") is False
    assert idx.eligible("6182", "2026-07-01") is False


def test_index_eligible_in_list(tmp_path: Path) -> None:
    run_backfill_daytrade(tmp_path, "2026-07-01", "2026-07-02", "t", fetch=_fake_fetch)
    idx = DayTradeIndex.load(tmp_path)
    assert idx is not None
    assert idx.eligible("2330", "2026-07-01") is True
    assert idx.eligible("9999", "2026-07-01") is False  # 該日有覆蓋但不在名單


def test_index_disposition_period_boundaries(tmp_path: Path) -> None:
    run_backfill_daytrade(tmp_path, "2026-07-01", "2026-07-02", "t", fetch=_fake_fetch)
    idx = DayTradeIndex.load(tmp_path)
    assert idx is not None
    # 5321 處置期間 2026-06-28 ~ 2026-07-05(含界),即使在當沖名單也 False
    with (tmp_path / "daytrade" / "day_trading.csv").open("a", encoding="utf-8", newline="") as fh:
        fh.write("5321,2026-07-01,\n")
    idx2 = DayTradeIndex.load(tmp_path)
    assert idx2 is not None
    assert idx2.eligible("5321", "2026-07-01") is False
    assert idx2.eligible("5321", "2026-07-05") is False


def test_index_uncovered_date_returns_none(tmp_path: Path) -> None:
    run_backfill_daytrade(tmp_path, "2026-07-01", "2026-07-02", "t", fetch=_fake_fetch)
    idx = DayTradeIndex.load(tmp_path)
    assert idx is not None
    assert idx.eligible("2330", "2026-07-09") is None  # 該日整日無 rows → 未覆蓋


def test_index_load_missing_returns_none(tmp_path: Path) -> None:
    assert DayTradeIndex.load(tmp_path) is None
