from __future__ import annotations

import csv
import json
from pathlib import Path

from copycat.data.import_neigui import run_import
from copycat.data.store import read_bars


def _bar_raw(time: str, px: str, vol: str) -> dict[str, str]:
    return {
        "Time": time,
        "Open": px,
        "High": px,
        "Low": px,
        "Close": px,
        "Volume": vol,
        "UpTick": "1",
        "UpVolume": vol,
        "DownTick": "0",
        "DownVolume": "0",
        "UnchVolume": "0",
    }


def _write_src(src: Path) -> None:
    src.mkdir()
    # 1104:T 日 2025-09-10(虎事件)+ T+1 2025-09-11;2001:control 事件
    recs = [
        {
            "stock_id": "1104",
            "date": "2025-09-10",
            "bars": [_bar_raw("10100", "32", "100"), _bar_raw("10200", "32", "50")],
        },
        {"stock_id": "1104", "date": "2025-09-11", "bars": [_bar_raw("10100", "33", "80")]},
    ]
    with (src / "k1_bars.jsonl").open("w", encoding="utf-8") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")
    with (src / "k1_control.jsonl").open("w", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {"stock_id": "2001", "date": "2025-09-10", "bars": [_bar_raw("10100", "50", "10")]}
            )
            + "\n"
        )
    prices = [
        {
            "stock_id": "1104",
            "date": "2025-09-10",
            "open": "29.5",
            "high": "32",
            "low": "29.5",
            "close": "32",
            "spread": "2.9",
            "volume": "150000",
        },
        {
            "stock_id": "1104",
            "date": "2025-09-11",
            "open": "33.6",
            "high": "34",
            "low": "31",
            "close": "31.5",
            "spread": "-0.5",
            "volume": "90000",
        },
        {
            "stock_id": "2001",
            "date": "2025-09-10",
            "open": "48",
            "high": "50",
            "low": "48",
            "close": "50",
            "spread": "4.5",
            "volume": "20000",
        },
        {
            "stock_id": "2001",
            "date": "2025-09-11",
            "open": "51",
            "high": "52",
            "low": "50",
            "close": "50.5",
            "spread": "0.5",
            "volume": "30000",
        },
    ]
    with (src / "prices.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(prices[0]))
        w.writeheader()
        w.writerows(prices)
    with (src / "all_limitup_events.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["stock_id", "date", "close", "spread", "pct", "volume"])
        w.writeheader()
        w.writerow(
            {
                "stock_id": "1104",
                "date": "2025-09-10",
                "close": "32.00",
                "spread": "2.90",
                "pct": "0.0997",
                "volume": "150000",
            }
        )
        w.writerow(
            {
                "stock_id": "2001",
                "date": "2025-09-10",
                "close": "50.00",
                "spread": "4.50",
                "pct": "0.0991",
                "volume": "20000",
            }
        )


def _write_events_csv(path: Path) -> None:
    fields = [
        "date",
        "stock_id",
        "stock_name",
        "tiger",
        "broker_id",
        "buy_lots",
        "limitup_close",
        "t1_date",
        "gap",
        "again",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        # 同事件兩虎 → 應去重為一個事件
        w.writerow(
            {
                "date": "2025-09-10",
                "stock_id": "1104",
                "stock_name": "環泥",
                "tiger": "國票敦北",
                "broker_id": "779c",
                "buy_lots": "100",
                "limitup_close": "32.0",
                "t1_date": "2025-09-11",
                "gap": "0.05",
                "again": "False",
            }
        )
        w.writerow(
            {
                "date": "2025-09-10",
                "stock_id": "1104",
                "stock_name": "環泥",
                "tiger": "國票安和",
                "broker_id": "779Z",
                "buy_lots": "50",
                "limitup_close": "32.0",
                "t1_date": "2025-09-11",
                "gap": "0.05",
                "again": "False",
            }
        )


def test_run_import(tmp_path: Path) -> None:
    src = tmp_path / "src"
    _write_src(src)
    ev_csv = tmp_path / "tigers.csv"
    _write_events_csv(ev_csv)
    data = tmp_path / "data"

    manifest = run_import(src, ev_csv, data)

    # 1K 標準化落地
    bars = read_bars(data, "1104", "2025-09-10")
    assert bars is not None and len(bars) == 2 and bars[0].m == 0
    # 日線 volume 轉張
    with (data / "daily" / "prices.csv").open("r", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["volume_lots"] == "150.0"
    # 事件:1 虎事件(去重)+ 1 control
    with (data / "events" / "events.csv").open("r", encoding="utf-8") as fh:
        events = list(csv.DictReader(fh))
    tiger = [e for e in events if e["source"] == "tiger_csv"]
    ctrl = [e for e in events if e["source"] == "control"]
    assert len(tiger) == 1 and tiger[0]["broker_ids"] == "779Z|779c"
    assert tiger[0]["t1_date"] == "2025-09-11"
    assert len(ctrl) == 1 and ctrl[0]["stock_id"] == "2001" and ctrl[0]["broker_ids"] == ""
    # manifest:control 的 T+1 1K 缺(2001/2025-09-11 沒有 1K)
    assert manifest["k1_days"] == 3
    assert manifest["tiger_events"] == 1 and manifest["control_events"] == 1
    assert "2001,2025-09-11" in manifest["missing_t1_1k"]
    assert (data / "manifest.json").exists()
