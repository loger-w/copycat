"""三池無條件 fade 複驗:日聚類 SE / 分層洗牌 / 分派 / 共同期間 / 判定式(SC-3)."""

from __future__ import annotations

import math
from pathlib import Path

from copycat.backtest.fade_config import FadeBacktestConfig
from copycat.backtest.fade_diagnose import (
    assign_pool,
    cluster_se,
    diagnose_pool_fade,
    stratified_permutation_p,
    write_pool_fade_report,
)
from copycat.backtest.fade_simulate import FadeSample
from copycat.data.models import Bar1K


def _bar(m: int, o: float, h: float, lo: float, c: float) -> Bar1K:
    return Bar1K(
        m=m, open=o, high=h, low=lo, close=c, volume=100, up_volume=50, down_volume=50,
        unch_volume=0,
    )


def _sample(
    sid: str, t1: str, source: str = "scan", broker_ids: str = ""
) -> FadeSample:
    return FadeSample(
        stock_id=sid,
        date="2026-01-01",
        t1_date=t1,
        limit=50.0,  # t1_limit = 55.0
        t1_open=52.0,
        gap=0.04,
        broker_ids=broker_ids,
        source=source,
    )


def _win_bars() -> list[Bar1K]:  # 開盤 52 → 收 51:fade 賺
    return [_bar(0, 52.0, 52.2, 51.8, 52.0), _bar(1, 52.0, 52.1, 50.9, 51.0)]


def _flat_bars() -> list[Bar1K]:  # 開盤 52 → 收 52:fade ≈ −成本
    return [_bar(0, 52.0, 52.2, 51.8, 52.0), _bar(1, 52.0, 52.2, 51.9, 52.0)]


def test_cluster_se_hand_computed() -> None:
    # values [1, 2] days [a, b]:mean 1.5;day 偏差和 = ∓0.5 → sqrt(0.5)/2
    assert abs(cluster_se([1.0, 2.0], ["a", "b"]) - math.sqrt(0.5) / 2) < 1e-12
    # 同日互相抵銷 → 0
    assert cluster_se([1.0, 2.0], ["a", "a"]) < 1e-12


def test_stratified_permutation_detects_clear_difference() -> None:
    days = [f"d{i}" for i in range(10)]
    obs, p = stratified_permutation_p(
        [1.0] * 10, days, [0.0] * 10, days, iters=500, seed=1
    )
    assert abs(obs - 1.0) < 1e-12
    assert p < 0.05


def test_stratified_permutation_no_difference_is_insignificant() -> None:
    days = [f"d{i}" for i in range(10)]
    _, p = stratified_permutation_p([1.0] * 10, days, [1.0] * 10, days, iters=200, seed=1)
    assert p > 0.5


def test_assign_pool_priority() -> None:
    watch = frozenset({"9227", "9600"})
    assert assign_pool(_sample("a", "2026-01-02", broker_ids="9227"), watch) == "tiger_1"
    assert assign_pool(_sample("a", "2026-01-02", broker_ids="9227|9600"), watch) == "tiger_2plus"
    # control 來源但已標記 → tiger(R5 命中優先)
    assert (
        assign_pool(_sample("a", "2026-01-02", source="control", broker_ids="9600"), watch)
        == "tiger_1"
    )
    assert assign_pool(_sample("a", "2026-01-02", source="control"), watch) == "control"
    assert assign_pool(_sample("a", "2026-01-02", source="scan"), watch) == "scan"
    # 非 watchlist 的 broker id 不算命中
    assert assign_pool(_sample("a", "2026-01-02", broker_ids="1234"), watch) == "scan"


def _build_universe(
    n_days: int, tiger_win: bool = True
) -> list[tuple[FadeSample, list[Bar1K]]]:
    """每日一 tiger 一 scan;tiger 贏(收 51/50.9 交錯)、scan 平."""
    out: list[tuple[FadeSample, list[Bar1K]]] = []
    for i in range(n_days):
        day = f"2026-02-{i + 1:02d}"
        t_bars = _win_bars() if tiger_win else _flat_bars()
        # 加一點變異避免退化(交錯兩種收盤價)
        if tiger_win and i % 2:
            t_bars = [_bar(0, 52.0, 52.2, 51.8, 52.0), _bar(1, 52.0, 52.1, 50.8, 50.9)]
        out.append((_sample(f"t{i}", day, broker_ids="9227"), t_bars))
        out.append((_sample(f"s{i}", day, source="scan"), _flat_bars()))
    return out


_WATCH = frozenset({"9227", "9600"})


def test_verdict_passes_when_tiger_clearly_wins() -> None:
    cfg = FadeBacktestConfig(diagnose_perm_iters=300, lock_penalty_grid=(0.05,))
    result = diagnose_pool_fade(_build_universe(24), {}, "2026-12-31", cfg, _WATCH)
    verdict = result["verdict"]
    assert isinstance(verdict, dict)
    assert verdict["continue_uc"] is True
    pools = result["pools"]
    assert isinstance(pools, dict)
    assert pools["tiger_1"]["n"] == 24
    assert pools["scan"]["n"] == 24
    variants = result["variants"]
    assert isinstance(variants, dict)
    assert "stress" in variants
    assert "lock_penalty_0.05" in variants


def test_verdict_fails_when_no_edge() -> None:
    cfg = FadeBacktestConfig(diagnose_perm_iters=300)
    result = diagnose_pool_fade(_build_universe(24, tiger_win=False), {}, "2026-12-31", cfg, _WATCH)
    verdict = result["verdict"]
    assert isinstance(verdict, dict)
    assert verdict["continue_uc"] is False


def test_label_cutoff_excludes_late_samples() -> None:
    cfg = FadeBacktestConfig(diagnose_perm_iters=100)
    universe = _build_universe(6)
    result = diagnose_pool_fade(universe, {}, "2026-02-03", cfg, _WATCH)
    pools = result["pools"]
    assert isinstance(pools, dict)
    assert pools["tiger_1"]["n"] == 3  # 02-04 之後不進
    assert pools["scan"]["n"] == 3


def test_excluded_guard_at_entry_counted_per_pool() -> None:
    cfg = FadeBacktestConfig(guard_limit_dist=0.03, diagnose_perm_iters=100)
    # 開盤 54.0 → override 進場價在 guard 區內(guard_level 53.35)
    near_limit = [_bar(0, 54.0, 54.2, 53.8, 54.0), _bar(1, 54.0, 54.2, 53.0, 53.2)]
    universe = _build_universe(4) + [(_sample("g1", "2026-02-01", broker_ids="9227"), near_limit)]
    result = diagnose_pool_fade(universe, {}, "2026-12-31", cfg, _WATCH)
    pools = result["pools"]
    assert isinstance(pools, dict)
    assert pools["tiger_1"]["excluded_guard_at_entry"] == 1


def test_report_writer_sections(tmp_path: Path) -> None:
    cfg = FadeBacktestConfig(diagnose_perm_iters=100)
    result = diagnose_pool_fade(_build_universe(8), {}, "2026-12-31", cfg, _WATCH)
    result["universe_counts"] = {"included": 16}
    path = tmp_path / "report.md"
    write_pool_fade_report(result, cfg, "2026-07-15", path)
    text = path.read_text(encoding="utf-8")
    assert "四池(base config)" in text
    assert "判定" in text
    assert "敏感度" in text
    assert "UC 方向值得繼續" in text
    assert "included=16" in text


# --- round 3:forward 段切分(change-spec §9.4;SC-7/二輪 R2)---


def _forward_universe() -> list[tuple[FadeSample, list[Bar1K]]]:
    """in-window 6 日(2026-02)+ forward 3 日(2026-07-13 起)."""
    out = _build_universe(6)
    for i in range(3):
        day = f"2026-07-{13 + i:02d}"
        out.append((_sample(f"ft{i}", day, broker_ids="9227"), _win_bars()))
        out.append((_sample(f"fs{i}", day, source="scan"), _flat_bars()))
    return out


def test_forward_section_splits_pools() -> None:
    cfg = FadeBacktestConfig(diagnose_perm_iters=100)
    result = diagnose_pool_fade(_forward_universe(), {}, "2026-12-31", cfg, _WATCH)
    fwd = result["forward"]
    assert isinstance(fwd, dict)
    pools = fwd["pools"]
    assert isinstance(pools, dict)
    assert pools["tiger_1"]["n"] == 3
    assert pools["scan"]["n"] == 3
    # forward 段完整判定式欄位存在,但門檻(≥20 交易日)未到 → 不判定
    assert fwd["threshold_met"] is False
    assert "comparison" in fwd and "verdict" in fwd


def test_forward_section_empty_marks_zero() -> None:
    cfg = FadeBacktestConfig(diagnose_perm_iters=100)
    result = diagnose_pool_fade(_build_universe(4), {}, "2026-12-31", cfg, _WATCH)
    fwd = result["forward"]
    assert isinstance(fwd, dict)
    pools = fwd["pools"]
    assert isinstance(pools, dict)
    assert pools["tiger_1"]["n"] == 0
    assert fwd["threshold_met"] is False


def test_main_verdict_unchanged_by_forward_section() -> None:
    # 白名單 2:主判定式仍以全共同期間計(含 forward 樣本),數值不因新節改變
    cfg = FadeBacktestConfig(diagnose_perm_iters=300, diagnose_perm_seed=42)
    universe = _build_universe(24)
    result = diagnose_pool_fade(universe, {}, "2026-12-31", cfg, _WATCH)
    assert isinstance(result["verdict"], dict)
    pools = result["pools"]
    assert isinstance(pools, dict)
    assert pools["tiger_1"]["n"] == 24
