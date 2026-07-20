"""FinMind 日線回補(SC-1):欄位映射 / 冪等合併 / marker 續傳 / retry."""

from __future__ import annotations

import csv
import json
import urllib.error
from pathlib import Path

import pytest

from copycat.data.backfill_finmind import _map_row, run_backfill

_FIELDS = ["stock_id", "date", "open", "high", "low", "close", "spread", "volume_lots"]


def _seed_prices(data_dir: Path, rows: list[dict[str, str]]) -> None:
    out = data_dir / "daily" / "prices.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_FIELDS)
        w.writeheader()
        w.writerows(rows)


def _read_prices(data_dir: Path) -> list[dict[str, str]]:
    with (data_dir / "daily" / "prices.csv").open("r", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _fm_row(sid: str, date: str, vol_shares: float = 25000000) -> dict[str, object]:
    return {
        "stock_id": sid,
        "date": date,
        "open": 900.0,
        "max": 920.0,
        "min": 895.0,
        "close": 910.0,
        "spread": 10.0,
        "Trading_Volume": vol_shares,
        "Trading_money": 1,
        "Trading_turnover": 1,
    }


def test_map_row_units() -> None:
    got = _map_row(_fm_row("2330", "2024-06-03"))
    assert got == {
        "stock_id": "2330",
        "date": "2024-06-03",
        "open": "900.0",
        "high": "920.0",
        "low": "895.0",
        "close": "910.0",
        "spread": "10.0",
        "volume_lots": "25000.0",  # 股 ÷1000 → 張
    }
    assert _map_row({"stock_id": "2330", "date": "x", "open": "bad"}) is None


def test_backfill_merge_and_manifest(tmp_path: Path) -> None:
    # [assertion 事前標記該變 2026-07-07] backfill 改為只收既有檔已知的 stock_id
    # (真跑踩到:FinMind 全市場含權證 → 4.2M rows 撐爆 DailyIndex)→ 種子加入 2330
    _seed_prices(
        tmp_path,
        [
            dict(zip(_FIELDS, ["1104", "2025-05-02", "29", "30", "29", "30", "1", "150.0"])),
            dict(zip(_FIELDS, ["2330", "2025-05-02", "900", "910", "890", "900", "1", "30000"])),
        ],
    )
    calls: list[str] = []

    def fake_fetch(date: str, token: str) -> list[dict[str, object]]:
        calls.append(date)
        # 2330 已知 → 收;9999U(權證類未知代碼)→ 過濾
        return [_fm_row("2330", date), _fm_row("9999U", date)] if date == "2024-06-03" else []

    stats = run_backfill(tmp_path, "2024-06-03", "2024-06-04", "tok", fetch=fake_fetch, sleep_s=0.0)
    assert stats["fetched_days"] == 2 and stats["added_rows"] == 1
    assert stats["filtered_rows"] == 1  # 未知代碼被過濾且有計數(no silent caps)
    rows = _read_prices(tmp_path)
    # sorted (stock_id, date),舊 row 保留、新 row 併入、spread 欄在
    assert [(r["stock_id"], r["date"]) for r in rows] == [
        ("1104", "2025-05-02"),
        ("2330", "2024-06-03"),
        ("2330", "2025-05-02"),
    ]
    assert rows[1]["volume_lots"] == "25000.0" and rows[1]["spread"] == "10.0"
    manifest = json.loads((tmp_path / "daily" / "backfill_manifest.json").read_text("utf-8"))
    # [assertion 事前標記該變 2026-07-20] 空回應日(06-04)不再進 marker(修永久跳過 bug)
    assert set(manifest["done_dates"]) == {"2024-06-03"}

    # 續傳:同範圍重跑 → 已成功日跳過,空日重抓
    calls.clear()
    stats2 = run_backfill(
        tmp_path, "2024-06-03", "2024-06-04", "tok", fetch=fake_fetch, sleep_s=0.0
    )
    assert calls == ["2024-06-04"] and stats2["skipped_days"] == 1 and stats2["added_rows"] == 0


def test_backfill_empty_day_not_marked_done(tmp_path: Path) -> None:
    """空回應日(FinMind 尚未發布 vs 真假日不可分)不得進 done_dates,下次重跑要再抓.

    比照 backfill_daytrade 的 if data 判斷(2026-07-10 真跑踩到:當日盤後跑
    永久跳過該日,得手動改 manifest)。
    """
    _seed_prices(
        tmp_path,
        [dict(zip(_FIELDS, ["2330", "2025-05-02", "900", "910", "890", "900", "1", "30000"]))],
    )
    calls: list[str] = []
    payload: dict[str, list[dict[str, object]]] = {"2024-06-03": []}

    def fake_fetch(date: str, token: str) -> list[dict[str, object]]:
        calls.append(date)
        return payload.get(date, [])

    run_backfill(tmp_path, "2024-06-03", "2024-06-03", "tok", fetch=fake_fetch, sleep_s=0.0)
    manifest = json.loads((tmp_path / "daily" / "backfill_manifest.json").read_text("utf-8"))
    assert manifest["done_dates"] == []  # 空日不進 marker

    # FinMind 盤後補發布 → 重跑同日要真的再抓、抓到後才進 marker
    payload["2024-06-03"] = [_fm_row("2330", "2024-06-03")]
    calls.clear()
    stats = run_backfill(tmp_path, "2024-06-03", "2024-06-03", "tok", fetch=fake_fetch, sleep_s=0.0)
    assert calls == ["2024-06-03"] and stats["added_rows"] == 1
    manifest = json.loads((tmp_path / "daily" / "backfill_manifest.json").read_text("utf-8"))
    assert manifest["done_dates"] == ["2024-06-03"]


def test_backfill_no_overwrite_existing_key(tmp_path: Path) -> None:
    _seed_prices(
        tmp_path,
        [dict(zip(_FIELDS, ["2330", "2024-06-03", "1", "1", "1", "1", "0", "999.0"]))],
    )

    def fake_fetch(date: str, token: str) -> list[dict[str, object]]:
        return [_fm_row("2330", date)]

    run_backfill(tmp_path, "2024-06-03", "2024-06-03", "tok", fetch=fake_fetch, sleep_s=0.0)
    rows = _read_prices(tmp_path)
    assert len(rows) == 1 and rows[0]["volume_lots"] == "999.0"  # 既有鍵不覆寫


def test_backfill_cold_start_warns_unfiltered(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """冷啟動(既有檔空)→ 不過濾屬預期,但必須顯性 warning(增量 review P1)."""
    _seed_prices(tmp_path, [])

    def fake_fetch(date: str, token: str) -> list[dict[str, object]]:
        return [_fm_row("2330", date)]

    import logging

    with caplog.at_level(logging.WARNING):
        run_backfill(tmp_path, "2024-06-03", "2024-06-03", "tok", fetch=fake_fetch, sleep_s=0.0)
    assert any("未過濾" in r.message for r in caplog.records)


def test_backfill_retries_socket_timeout(tmp_path: Path) -> None:
    """SSL read timeout 以 TimeoutError 拋出(非 URLError)— retry 必須接住(真跑踩到)."""
    _seed_prices(tmp_path, [])
    attempts = {"n": 0}

    def flaky(date: str, token: str) -> list[dict[str, object]]:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise TimeoutError("The read operation timed out")
        return [_fm_row("2330", date)]

    stats = run_backfill(tmp_path, "2024-06-03", "2024-06-03", "tok", fetch=flaky, sleep_s=0.0)
    assert attempts["n"] == 3 and stats["added_rows"] == 1


def test_backfill_retry_and_progress_kept(tmp_path: Path) -> None:
    _seed_prices(tmp_path, [])
    attempts: dict[str, int] = {}

    def flaky(date: str, token: str) -> list[dict[str, object]]:
        attempts[date] = attempts.get(date, 0) + 1
        if date == "2024-06-03" and attempts[date] < 3:
            raise urllib.error.URLError("boom")
        if date == "2024-06-04":
            raise urllib.error.URLError("dead")
        return [_fm_row("2330", date)]

    with pytest.raises(urllib.error.URLError):
        run_backfill(tmp_path, "2024-06-03", "2024-06-04", "tok", fetch=flaky, sleep_s=0.0)
    assert attempts["2024-06-03"] == 3  # retry 到第 3 次成功
    assert attempts["2024-06-04"] == 3  # 3 次上限後 raise
    # 已成功的 06-03 進度保留(rows + manifest)
    rows = _read_prices(tmp_path)
    assert [(r["stock_id"], r["date"]) for r in rows] == [("2330", "2024-06-03")]
    manifest = json.loads((tmp_path / "daily" / "backfill_manifest.json").read_text("utf-8"))
    assert manifest["done_dates"] == ["2024-06-03"]
