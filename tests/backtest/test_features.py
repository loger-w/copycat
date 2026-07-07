"""觸發時點特徵(SC-2)與位階特徵族(SC-3)— 手算對照 + lookahead 防護."""

from __future__ import annotations

import csv
from pathlib import Path

from copycat.backtest.config import BacktestConfig
from copycat.backtest.features import (
    avg20_t1,
    find_trigger,
    structural_features,
    trigger_features,
)
from copycat.data.daily import DailyIndex
from copycat.data.models import Bar1K

_EPS = 1e-9


def _bar(
    m: int,
    o: float,
    h: float,
    lo: float,
    c: float,
    v: float,
    uv: float = 0.0,
    dv: float = 0.0,
) -> Bar1K:
    return Bar1K(
        m=m,
        open=o,
        high=h,
        low=lo,
        close=c,
        volume=v,
        up_volume=uv,
        down_volume=dv,
        unch_volume=0.0,
    )


_BARS = [
    _bar(0, 102.0, 103.0, 101.0, 103.0, 50.0, uv=30.0, dv=20.0),
    _bar(1, 103.0, 104.0, 102.5, 103.1, 10.0, uv=5.0, dv=5.0),  # 洗量 bar(高量平價)
    _bar(2, 104.0, 108.5, 103.0, 108.0, 100.0, uv=90.0, dv=10.0),
]


def test_find_trigger_and_eps_boundary() -> None:
    assert find_trigger(_BARS, 100.0, 0.08, _EPS) == 2
    assert find_trigger(_BARS, 100.0, 0.10, _EPS) is None
    # 浮點邊界:high 距門檻 < eps 仍觸發
    bars = [_bar(0, 100.0, 108.0 - 5e-10, 99.0, 100.0, 1.0)]
    assert find_trigger(bars, 100.0, 0.08, _EPS) == 0


def test_trigger_features_hand_computed() -> None:
    got = trigger_features(
        _BARS,
        2,
        prev_close=100.0,
        theta=0.08,
        avg20_lots=270.0,
        static={
            "amt_t1_m": 4.8,
            "ret5": 0.1,
            "ret20": 0.2,
            "prev_limitup": True,
            "dtr_t1": None,
            "prev_close": 100.0,
        },
    )
    assert got["trig_min"] == 2
    assert got["gap_open"] is not None and abs(got["gap_open"] - 0.02) < 1e-12
    assert got["auction_lots"] == 50.0
    assert got["auction_vol_ratio"] is not None and abs(got["auction_vol_ratio"] - 50 / 270) < 1e-12
    assert got["climb_rate"] is not None and abs(got["climb_rate"] - 0.03) < 1e-12
    assert got["burst3"] is not None and abs(got["burst3"] - (108.0 / 102.0 - 1)) < 1e-12
    assert got["up_min_frac"] == 1.0  # 三根皆收紅
    assert (
        got["max_pullback"] is not None and abs(got["max_pullback"] - (1 - 103.0 / 108.5)) < 1e-12
    )
    assert got["cumvol_ratio"] is not None and abs(got["cumvol_ratio"] - 160 / 270) < 1e-12
    assert got["max_minvol_x"] == 100.0  # avg_min_v = 270/270 = 1
    assert got["wash_bars"] == 1.0  # b1:v=10 ≥ 5×1 且 |0.1|/103 < 0.002
    assert got["outer_ratio"] is not None and abs(got["outer_ratio"] - 125 / 160) < 1e-12
    assert got["touches_back"] == 0.0
    assert got["prev_limitup"] == 1.0  # bool → float
    assert got["dtr_t1"] is None
    assert got["amt_t1_m"] == 4.8


def test_burst3_clamped_at_zero() -> None:
    bars = [_bar(0, 110.0, 112.0, 99.0, 100.0, 1.0), _bar(1, 100.0, 112.0, 95.0, 96.0, 1.0)]
    got = trigger_features(bars, 1, prev_close=100.0, theta=0.08, avg20_lots=270.0, static={})
    assert got["burst3"] == 0.0  # 全負 3-bar 報酬 → 下限 0(neigui 同源)


def test_touches_back_state_machine() -> None:
    # 摸 +7.5% → 收回 <+7% → 再摸 → 觸發
    bars = [
        _bar(0, 100.0, 107.6, 100.0, 106.5, 1.0),  # 上穿 7.5%,close 6.5% → touch 1
        _bar(1, 106.0, 107.0, 105.0, 106.0, 1.0),
        _bar(2, 106.0, 108.2, 106.0, 108.0, 1.0),  # 觸發
    ]
    got = trigger_features(bars, 2, prev_close=100.0, theta=0.08, avg20_lots=270.0, static={})
    assert got["touches_back"] == 1.0


def test_zero_denominator_guards() -> None:
    got = trigger_features(_BARS, 2, prev_close=100.0, theta=0.08, avg20_lots=0.0, static={})
    assert got["auction_vol_ratio"] is None
    assert got["cumvol_ratio"] is None
    assert got["max_minvol_x"] is None
    assert got["wash_bars"] == 0.0
    bars = [_bar(0, 100.0, 108.5, 99.0, 108.0, 10.0, uv=0.0, dv=0.0)]
    got2 = trigger_features(bars, 0, prev_close=100.0, theta=0.08, avg20_lots=270.0, static={})
    assert got2["outer_ratio"] is None


def test_lookahead_guard() -> None:
    """觸發後 bar 改動不得影響特徵值."""
    tampered = _BARS + [_bar(3, 108.0, 130.0, 50.0, 60.0, 9999.0, uv=9999.0)]
    a = trigger_features(_BARS, 2, prev_close=100.0, theta=0.08, avg20_lots=270.0, static={})
    b = trigger_features(tampered, 2, prev_close=100.0, theta=0.08, avg20_lots=270.0, static={})
    assert a == b


# ---- 位階特徵族(daily fixture) ----

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


def _write_daily(
    tmp_path: Path,
    closes: list[float],
    highs: list[float] | None = None,
    vols: list[float] | None = None,
    limitup_dates: list[str] | None = None,
) -> DailyIndex:
    data = tmp_path / "data"
    (data / "daily").mkdir(parents=True, exist_ok=True)
    (data / "events").mkdir(parents=True, exist_ok=True)
    ds = _dates(len(closes))
    with (data / "daily" / "prices.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_PRICE_FIELDS)
        w.writeheader()
        for i, d in enumerate(ds):
            h = highs[i] if highs else closes[i]
            v = vols[i] if vols else 100.0
            w.writerow(
                dict(
                    zip(
                        _PRICE_FIELDS,
                        [
                            "1101",
                            d,
                            str(closes[i]),
                            str(h),
                            str(closes[i]),
                            str(closes[i]),
                            "0.0",
                            str(v),
                        ],
                    )
                )
            )
    with (data / "events" / "limitup_all.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["stock_id", "date", "close"])
        w.writeheader()
        for d in limitup_dates or []:
            w.writerow({"stock_id": "1101", "date": d, "close": "0"})
    return DailyIndex.load(data)


def test_structural_features_flat_base(tmp_path: Path) -> None:
    idx = _write_daily(tmp_path, [10.0] * 70)
    cfg = BacktestConfig.default()
    t_date = _dates(70)[-1]
    got = structural_features(idx, "1101", t_date, cfg)
    assert got["dist_ma20"] == 0.0 and got["dist_ma60"] == 0.0
    assert got["bb_width_pct120"] is None  # window 120 不足
    assert got["pos_52w"] is None  # max == min
    assert got["ignition_first"] == 1.0  # 盤整、未觸 8%、無近期漲停


def test_structural_ignition_false_when_recent_touch(tmp_path: Path) -> None:
    closes = [10.0] * 70
    highs = [10.0] * 70
    highs[65] = 10.9  # 近 20 日內摸過 +9%
    idx = _write_daily(tmp_path, closes, highs=highs)
    got = structural_features(idx, "1101", _dates(70)[-1], BacktestConfig.default())
    assert got["ignition_first"] == 0.0


def test_structural_ignition_false_when_recent_limitup(tmp_path: Path) -> None:
    ds = _dates(70)
    idx = _write_daily(tmp_path, [10.0] * 70, limitup_dates=[ds[60]])
    got = structural_features(idx, "1101", ds[-1], BacktestConfig.default())
    assert got["ignition_first"] == 0.0


def test_avg20_t1_no_lookahead(tmp_path: Path) -> None:
    """avg20 基準 = T-1;T 日爆量不得影響."""
    vols = [100.0] * 69 + [99999.0]
    idx = _write_daily(tmp_path, [10.0] * 70, vols=vols)
    t_date = _dates(70)[-1]
    got = avg20_t1(idx, "1101", t_date)
    assert got == 100.0
