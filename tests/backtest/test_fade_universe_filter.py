"""SC-2/SC-6:宇宙當沖過濾(fail-fast / 剔除 / 未覆蓋不過濾)+ FadeSample.source."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from copycat.backtest.fade_config import FadeBacktestConfig
from copycat.backtest.fade_pipeline import build_fade_universe
from copycat.data.models import Bar1K
from copycat.data.store import write_bars


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def _event(sid: str, t1: str, source: str) -> dict[str, str]:
    return {
        "stock_id": sid,
        "date": "2026-07-01",
        "stock_name": "",
        "limitup_close": "50.0",
        "t1_date": t1,
        "source": source,
        "broker_ids": "",
    }


_EV_FIELDS = ["stock_id", "date", "stock_name", "limitup_close", "t1_date", "source", "broker_ids"]


def _setup(tmp_path: Path, *, with_daytrade: bool) -> Path:
    events = [
        _event("2330", "2026-07-02", "tiger_csv"),  # 在當沖名單
        _event("1101", "2026-07-02", "control"),  # 不在名單 → 剔除
        _event("5321", "2026-07-02", "control"),  # 處置期間 → 剔除
        _event("9910", "2026-07-03", "scan"),  # t1 未覆蓋日 → 不過濾
    ]
    _write_csv(tmp_path / "events" / "events.csv", _EV_FIELDS, events)
    bar = Bar1K(
        m=0,
        open=52.0,
        high=52.5,
        low=51.5,
        close=52.0,
        volume=100,
        up_volume=50,
        down_volume=50,
        unch_volume=0,
    )
    for sid, t1 in [
        ("2330", "2026-07-02"),
        ("1101", "2026-07-02"),
        ("5321", "2026-07-02"),
        ("9910", "2026-07-03"),
    ]:
        write_bars(tmp_path, sid, t1, [bar])
    if with_daytrade:
        _write_csv(
            tmp_path / "daytrade" / "day_trading.csv",
            ["stock_id", "date", "buy_after_sale"],
            [
                {"stock_id": "2330", "date": "2026-07-02", "buy_after_sale": ""},
                {"stock_id": "5321", "date": "2026-07-02", "buy_after_sale": ""},
            ],
        )
        _write_csv(
            tmp_path / "daytrade" / "disposition.csv",
            ["stock_id", "period_start", "period_end"],
            [{"stock_id": "5321", "period_start": "2026-06-28", "period_end": "2026-07-05"}],
        )
    return tmp_path


def test_filter_excludes_and_counts(tmp_path: Path) -> None:
    data = _setup(tmp_path, with_daytrade=True)
    cfg = FadeBacktestConfig(universe_daytrade_filter=True)
    samples, counts = build_fade_universe(data, data / "events" / "events.csv", cfg)
    ids = {s.stock_id for s in samples}
    assert ids == {"2330", "9910"}
    assert counts["excluded_no_daytrade"] == 1  # 1101
    assert counts["excluded_disposition"] == 1  # 5321
    assert counts["daytrade_uncovered_date"] == 1  # 9910


def test_filter_missing_data_raises(tmp_path: Path) -> None:
    data = _setup(tmp_path, with_daytrade=False)
    cfg = FadeBacktestConfig(universe_daytrade_filter=True)
    with pytest.raises(RuntimeError):
        build_fade_universe(data, data / "events" / "events.csv", cfg)


def test_filter_disabled_keeps_all(tmp_path: Path) -> None:
    data = _setup(tmp_path, with_daytrade=False)
    cfg = FadeBacktestConfig()
    samples, counts = build_fade_universe(data, data / "events" / "events.csv", cfg)
    assert {s.stock_id for s in samples} == {"2330", "1101", "5321", "9910"}
    assert counts["excluded_no_daytrade"] == 0


def test_samples_carry_source(tmp_path: Path) -> None:
    data = _setup(tmp_path, with_daytrade=False)
    cfg = FadeBacktestConfig()
    samples, _ = build_fade_universe(data, data / "events" / "events.csv", cfg)
    by_id = {s.stock_id: s.source for s in samples}
    assert by_id["2330"] == "tiger_csv"
    assert by_id["1101"] == "control"
    assert by_id["9910"] == "scan"
