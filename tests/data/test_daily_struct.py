"""DailyIndex 位階/結構擴充(SC-3):ma / bb_width / pos_52w / ref_prev_close / 導覽器."""

from __future__ import annotations

import csv
from pathlib import Path

from copycat.data.daily import DailyIndex

_FIELDS = ["stock_id", "date", "open", "high", "low", "close", "spread", "volume_lots"]


def _write(tmp_path: Path, rows: list[dict[str, str]], *, with_spread: bool = True) -> None:
    daily = tmp_path / "daily"
    events = tmp_path / "events"
    daily.mkdir(exist_ok=True)
    events.mkdir(exist_ok=True)
    fields = _FIELDS if with_spread else [f for f in _FIELDS if f != "spread"]
    with (daily / "prices.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: v for k, v in r.items() if k in fields})
    with (events / "limitup_all.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["stock_id", "date", "close"])
        w.writeheader()


def _row(date: str, close: float, spread: float = 0.0, vol: float = 100.0) -> dict[str, str]:
    return {
        "stock_id": "1101",
        "date": date,
        "open": str(close),
        "high": str(close),
        "low": str(close),
        "close": str(close),
        "spread": str(spread),
        "volume_lots": str(vol),
    }


def _dates(n: int) -> list[str]:
    # 產 n 個遞增日期字串(跨月安全)
    out = []
    m, d = 1, 1
    for _ in range(n):
        out.append(f"2026-{m:02d}-{d:02d}")
        d += 1
        if d > 28:
            m, d = m + 1, 1
    return out


def test_ma(tmp_path: Path) -> None:
    _write(tmp_path, [_row(d, c) for d, c in zip(_dates(3), (10.0, 12.0, 14.0))])
    idx = DailyIndex.load(tmp_path)
    d1, d2, d3 = _dates(3)
    assert idx.ma("1101", d3, 3) == 12.0
    assert idx.ma("1101", d2, 2) == 11.0
    assert idx.ma("1101", d2, 3) is None  # 不足 n 日
    assert idx.ma("9999", d2, 2) is None


def test_bb_width(tmp_path: Path) -> None:
    # closes [10, 12]:mean=11,母體 σ=1 → 帶寬 = 2×2×1/11
    _write(tmp_path, [_row(d, c) for d, c in zip(_dates(2), (10.0, 12.0))])
    idx = DailyIndex.load(tmp_path)
    _, d2 = _dates(2)
    got = idx.bb_width("1101", d2, 2, 2.0)
    assert got is not None and abs(got - 4.0 / 11.0) < 1e-12
    assert idx.bb_width("1101", d2, 3, 2.0) is None


def test_bb_width_pct(tmp_path: Path) -> None:
    # 4 日 close:前 3 日波動大、後段壓縮 → 最後一日帶寬在 window 內百分位低
    closes = (10.0, 14.0, 14.0, 14.0)
    _write(tmp_path, [_row(d, c) for d, c in zip(_dates(4), closes)])
    idx = DailyIndex.load(tmp_path)
    ds = _dates(4)
    # n=2:各日帶寬 d2=大、d3=大、d4=0 → d4 在 window=3 的 rank 最低
    pct = idx.bb_width_pct("1101", ds[3], 2, 2.0, 3)
    assert pct is not None and pct == 0.0
    hi = idx.bb_width_pct("1101", ds[1], 2, 2.0, 1)
    assert hi is not None  # window=1 → 只有自己,rank = 0
    assert idx.bb_width_pct("1101", ds[1], 2, 2.0, 5) is None  # window 不足


def test_pos_52w(tmp_path: Path) -> None:
    # 61 日:前 60 日 close 10..與最後一日 20 → pos = (20-10)/(高-低)
    closes = [10.0] * 30 + [30.0] * 30 + [20.0]
    _write(tmp_path, [_row(d, c) for d, c in zip(_dates(61), closes)])
    idx = DailyIndex.load(tmp_path)
    last = _dates(61)[-1]
    got = idx.pos_52w("1101", last)
    assert got is not None and abs(got - 0.5) < 1e-12


def test_pos_52w_insufficient_and_flat(tmp_path: Path) -> None:
    _write(tmp_path, [_row(d, 10.0) for d in _dates(61)])
    idx = DailyIndex.load(tmp_path)
    assert idx.pos_52w("1101", _dates(61)[-1]) is None  # max == min
    _write(tmp_path, [_row(d, 10.0 + i) for i, d in enumerate(_dates(30))])
    idx2 = DailyIndex.load(tmp_path)
    assert idx2.pos_52w("1101", _dates(30)[-1]) is None  # 不足 60 日


def test_ref_prev_close(tmp_path: Path) -> None:
    rows = [_row(*a) for a in zip(_dates(2), (29.1, 32.0))]
    rows[1]["spread"] = "2.9"  # 除權息安全:close − spread = 參考前收
    _write(tmp_path, rows)
    idx = DailyIndex.load(tmp_path)
    d1, d2 = _dates(2)
    assert idx.ref_prev_close("1101", d2) == 29.1
    # close − spread ≤ 0 → None
    rows[1]["spread"] = "40.0"
    _write(tmp_path, rows)
    assert DailyIndex.load(tmp_path).ref_prev_close("1101", d2) is None


def test_ref_prev_close_mixed_missing_spread(tmp_path: Path) -> None:
    """同檔混合:有 spread 欄但某 row 值缺(空字串)→ 該 row 走 fallback 前日 close."""
    rows = [_row(*a) for a in zip(_dates(3), (29.1, 30.0, 32.0))]
    rows[1]["spread"] = ""  # 缺值(舊匯入資料)
    rows[2]["spread"] = "2.0"
    _write(tmp_path, rows)
    idx = DailyIndex.load(tmp_path)
    d1, d2, d3 = _dates(3)
    assert idx.ref_prev_close("1101", d2) == 29.1  # 缺值 → fallback 前日 close
    assert idx.ref_prev_close("1101", d3) == 30.0  # 有值 → close − spread


def test_ref_prev_close_fallback_without_spread_column(tmp_path: Path) -> None:
    rows = [_row(*a) for a in zip(_dates(2), (29.1, 32.0))]
    _write(tmp_path, rows, with_spread=False)
    idx = DailyIndex.load(tmp_path)
    d1, d2 = _dates(2)
    assert idx.ref_prev_close("1101", d2) == 29.1  # fallback 前日 close
    assert idx.ref_prev_close("1101", d1) is None  # 無前日


def test_navigation(tmp_path: Path) -> None:
    _write(tmp_path, [_row(d, c) for d, c in zip(_dates(3), (10.0, 11.0, 12.0))])
    idx = DailyIndex.load(tmp_path)
    d1, d2, d3 = _dates(3)
    assert idx.prev_date("1101", d2) == d1
    assert idx.prev_date("1101", d1) is None
    assert idx.close_of("1101", d2) == 11.0
    assert idx.volume_of("1101", d2) == 100.0
    assert idx.shift_date("1101", d3, 2) == d1
    assert idx.shift_date("1101", d3, 3) is None
