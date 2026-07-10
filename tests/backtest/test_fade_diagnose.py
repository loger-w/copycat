"""SC-7:逼近漲停診斷 — 逼近後鎖死 / 回落分類與分桶."""

from __future__ import annotations

from copycat.backtest.fade_config import FadeBacktestConfig
from copycat.backtest.fade_diagnose import diagnose_limit_approach
from copycat.backtest.fade_simulate import FadeSample
from copycat.data.models import Bar1K


def _bar(m: int, h: float, lo: float, c: float, vol: float = 100) -> Bar1K:
    return Bar1K(
        m=m,
        open=c,
        high=h,
        low=lo,
        close=c,
        volume=vol,
        up_volume=50,
        down_volume=50,
        unch_volume=0,
    )


def _sample(sid: str) -> FadeSample:
    return FadeSample(
        stock_id=sid,
        date="2026-07-01",
        t1_date="2026-07-02",
        limit=50.0,  # t1_limit = 55.0;dist 0.03 → level 53.35
        t1_open=52.0,
        gap=0.04,
        broker_ids="",
        source="control",
    )


def test_diagnose_lock_vs_reversal() -> None:
    cfg = FadeBacktestConfig(guard_dist_grid=(0.03,))
    lock_bars = [_bar(0, 52.5, 51.5, 52.0), _bar(1, 55.0, 55.0, 55.0), _bar(2, 55.0, 55.0, 55.0)]
    # 嘎空回落:逼近(高 54)後跌回 50 → depth = (53.35×… 以 level 計) > 0
    fade_bars = [
        _bar(0, 52.5, 51.5, 52.0),
        _bar(30, 54.0, 52.0, 53.0, vol=500),
        _bar(31, 53.0, 50.0, 50.2),
    ]
    no_approach = [_bar(0, 52.5, 51.5, 52.0), _bar(1, 53.0, 51.0, 51.5)]
    result = diagnose_limit_approach(
        [(_sample("A"), lock_bars), (_sample("B"), fade_bars), (_sample("C"), no_approach)], cfg
    )
    per = result["per_dist"]
    assert isinstance(per, dict)
    overall = per["0.03"]["overall"]
    assert overall["n"] == 2  # C 未逼近
    assert overall["p_lock"] == 0.5
    assert overall["p_reverse"] == 0.5
    med = overall["reversal_depth_med"]
    assert isinstance(med, float) and med > 0.05  # (53.35−50)/53.35 ≈ 6.3%


def test_diagnose_buckets_by_volume_and_time() -> None:
    cfg = FadeBacktestConfig(guard_dist_grid=(0.03,))
    # 早盤(m=1)薄量逼近(vol 與前均量同)
    early_light = [_bar(0, 52.5, 51.5, 52.0, vol=100), _bar(1, 54.0, 52.0, 53.0, vol=100)]
    # 午後(m=200)厚量逼近(500 vs 100)
    late_heavy = [_bar(0, 52.5, 51.5, 52.0, vol=100), _bar(200, 54.0, 52.0, 53.0, vol=500)]
    result = diagnose_limit_approach([(_sample("A"), early_light), (_sample("B"), late_heavy)], cfg)
    per = result["per_dist"]
    assert isinstance(per, dict)
    buckets = per["0.03"]["buckets"]
    assert buckets["early_light"]["n"] == 1
    assert buckets["late_heavy"]["n"] == 1
    assert buckets["early_heavy"]["n"] == 0
