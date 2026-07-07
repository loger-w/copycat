"""樣本宇宙(SC-2/5):watchlist 分組、權重、limit 分軌與交叉、前置日剔除."""

from __future__ import annotations

import csv
from pathlib import Path

from copycat.backtest.config import BacktestConfig
from copycat.backtest.universe import build_universe
from copycat.data.daily import DailyIndex
from copycat.watchlist import Watchlist

_PRICE_FIELDS = ["stock_id", "date", "open", "high", "low", "close", "spread", "volume_lots"]


def _dates(n: int) -> list[str]:
    out = []
    m, d = 1, 1
    for _ in range(n):
        out.append(f"2026-{m:02d}-{d:02d}")
        d += 1
        if d > 28:
            m, d = m + 1, 1
    return out


def _write_data(tmp_path: Path, *, mismatch_limit: bool = False) -> Path:
    data = tmp_path / "data"
    (data / "daily").mkdir(parents=True)
    (data / "events").mkdir(parents=True)
    ds = _dates(30)
    rows: list[dict[str, str]] = []
    # 4 檔:1001(tiger core∩aux)/1002(僅 aux)/2001(control)/3001(near_miss);
    # 4001 = 前置日不足(只 5 天)
    for sid in ("1001", "1002", "2001", "3001"):
        for i, d in enumerate(ds):
            close, spread = (32.0, 2.9) if i == len(ds) - 1 else (29.1, 0.0)
            rows.append(
                dict(
                    zip(
                        _PRICE_FIELDS,
                        [sid, d, "29.1", str(close), "29.0", str(close), str(spread), "100"],
                    )
                )
            )
    for i, d in enumerate(ds[-5:]):
        rows.append(dict(zip(_PRICE_FIELDS, ["4001", d, "29.1", "32.0", "29.0", "32.0", "2.9", "100"])))
    with (data / "daily" / "prices.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_PRICE_FIELDS)
        w.writeheader()
        w.writerows(rows)
    with (data / "events" / "limitup_all.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["stock_id", "date", "close"])
        w.writeheader()
    ev_date = ds[-1]
    limit_1001 = "33.0" if mismatch_limit else "32.0"
    with (data / "events" / "events.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "stock_id",
                "date",
                "stock_name",
                "limitup_close",
                "t1_date",
                "source",
                "broker_ids",
            ],
        )
        w.writeheader()
        w.writerow(
            {
                "stock_id": "1001",
                "date": ev_date,
                "stock_name": "甲",
                "limitup_close": limit_1001,
                "t1_date": "",
                "source": "tiger_csv",
                "broker_ids": "779c|9600",  # core ∩ aux 同時命中 → core 優先
            }
        )
        w.writerow(
            {
                "stock_id": "1002",
                "date": ev_date,
                "stock_name": "乙",
                "limitup_close": "32.0",
                "t1_date": "",
                "source": "tiger_csv",
                "broker_ids": "9600",
            }
        )
        w.writerow(
            {
                "stock_id": "2001",
                "date": ev_date,
                "stock_name": "",
                "limitup_close": "32.0",
                "t1_date": "",
                "source": "control",
                "broker_ids": "",
            }
        )
        w.writerow(
            {
                "stock_id": "4001",
                "date": ev_date,
                "stock_name": "",
                "limitup_close": "32.0",
                "t1_date": "",
                "source": "control",
                "broker_ids": "",
            }
        )
    with (data / "events" / "near_miss.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["stock_id", "date"])
        w.writeheader()
        w.writerow({"stock_id": "3001", "date": ev_date})
    return data


_CORE = Watchlist(name="core", broker_ids=frozenset({"9227", "5854", "779c", "779Z"}))
_AUX = Watchlist(name="aux", broker_ids=frozenset({"9600"}))


def test_build_universe_groups_and_weights(tmp_path: Path) -> None:
    data = _write_data(tmp_path)
    daily = DailyIndex.load(data)
    cfg = BacktestConfig.default()
    samples, counts = build_universe(data, daily, _CORE, _AUX, cfg)
    by_id = {s.stock_id: s for s in samples}
    assert by_id["1001"].group == "tiger_core"  # core 優先於 aux
    assert by_id["1002"].group == "tiger_9600"
    assert by_id["2001"].group == "ctrl_lock"
    assert by_id["3001"].group == "near_miss"
    assert by_id["3001"].weight == 5.0 and by_id["1001"].weight == 1.0
    # near_miss:limit 用計算值(prev_close 29.1 → 32.0)、t1_date None
    assert by_id["3001"].prev_close == 29.1
    assert by_id["3001"].limit_price == 32.0
    assert by_id["3001"].t1_date is None
    # 鎖板組:limit 用 events.csv 標記
    assert by_id["1001"].limit_price == 32.0
    # 前置日不足剔除
    assert "4001" not in by_id and counts["insufficient_prior"] == 1
    # 輸出排序 (stock_id, date)
    assert [s.stock_id for s in samples] == sorted(s.stock_id for s in samples)


def test_build_universe_limit_mismatch_excluded(tmp_path: Path) -> None:
    data = _write_data(tmp_path, mismatch_limit=True)
    daily = DailyIndex.load(data)
    samples, counts = build_universe(data, daily, _CORE, _AUX, BacktestConfig.default())
    assert all(s.stock_id != "1001" for s in samples)
    assert counts["limit_mismatch"] == 1
