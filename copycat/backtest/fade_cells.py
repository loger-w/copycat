"""三個 pre-registered 劇本格子(change-spec SC-4;門檻全在 config,不做搜索).

宇宙 = UC 池(broker_ids 命中 watchlist 才進統計;R1 P0)。
cell_a 先拉再出:headroom ≥ 門檻 × 拉高 ≥ min_rally 後回落 ≥ pullback_x ×
  進場當下累計內盤比 ≥ 閾值(任何時點可算,無偷看未來)。
cell_b 衝停失敗:逼近漲停 ≤d 後自逼近高點回落 ≥ fail_confirm 進場;自帶風控
  (fixed stop = 逼近高點 ×(1+buffer),不用距離式 guard)。
cell_c 低開反拉(觀察格):低開宇宙,反拉 ≥r 後回落進場;只統計不入 D5 對決。
每 cell 附同宇宙「第 7 分鐘無條件空」基準線(R7);評估 = 全期間等日曆四等分
方向一致 + D5 判定 —— D5 全部以壓測組合(stress_slippage + guard_fill_high)計(R6)。
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
from datetime import date as _date
from pathlib import Path

from copycat.backtest.fade_config import NO_STOP_HOLD_COMBO, FadeBacktestConfig
from copycat.backtest.fade_report import _fmt
from copycat.backtest.fade_simulate import (
    TRADEABLE_STATUSES as _TRADEABLE,
)
from copycat.backtest.fade_simulate import (
    FadeSample,
    simulate_fade_sample,
)
from copycat.data.models import Bar1K
from copycat.market import limit_up_price

logger = logging.getLogger(__name__)

_NO_STOP_COMBO = NO_STOP_HOLD_COMBO

_BASELINE_M = 6  # 09:07 bar(m 索引 6)= 「第 7 分鐘無條件空」基準線


def is_uc_sample(sample: FadeSample, watchlist_ids: frozenset[str]) -> bool:
    """UC 池過濾(R1):broker_ids 至少一個 watchlist 命中."""
    return any(b and b in watchlist_ids for b in sample.broker_ids.split("|"))


def find_cell_a_entry(
    bars: list[Bar1K], t1_limit: float, inner_threshold: float, cfg: FadeBacktestConfig
) -> int | None:
    """先拉再出:窗內拉高 ≥ min_rally 後,收盤自高點回落 ≥ pullback_x,
    且進場當下(累計至該 bar)內盤比 ≥ 閾值、headroom ≥ 門檻."""
    open_p = bars[0].open
    if open_p <= 0:
        return None
    run_high = 0.0
    cum_up = cum_dn = 0.0
    for i, b in enumerate(bars):
        cum_up += b.up_volume
        cum_dn += b.down_volume
        run_high = max(run_high, b.high)
        if b.m > cfg.cell_a_window_m:
            return None
        if run_high < open_p * (1.0 + cfg.cell_a_min_rally):
            continue
        if b.close > run_high * (1.0 - cfg.cell_a_pullback_x):
            continue
        if (t1_limit - b.close) / b.close < cfg.cell_a_headroom_min:
            continue
        total = cum_up + cum_dn
        if total > 0 and cum_dn / total >= inner_threshold:
            return i
    return None


def find_cell_b_entry(
    bars: list[Bar1K], t1_limit: float, approach_dist: float, cfg: FadeBacktestConfig
) -> tuple[int, float] | None:
    """衝停失敗:曾逼近漲停 ≤d 後,收盤自逼近高點回落 ≥ fail_confirm →
    (entry_idx, approach_high)."""
    level = t1_limit * (1.0 - approach_dist)
    approach_high: float | None = None
    for i, b in enumerate(bars):
        if b.high >= level:
            approach_high = max(approach_high or 0.0, b.high)
            continue  # 逼近中的 bar 不進場(等失敗確認)
        if approach_high is not None and b.close <= approach_high * (1.0 - cfg.cell_b_fail_confirm):
            return i, approach_high
    return None


def find_cell_c_entry(
    bars: list[Bar1K], rally_pct: float, cfg: FadeBacktestConfig
) -> int | None:
    """低開反拉:自開盤反拉 ≥ r 後,收盤自高點回落 ≥ pullback_x 進場."""
    open_p = bars[0].open
    if open_p <= 0:
        return None
    run_high = 0.0
    for i, b in enumerate(bars):
        run_high = max(run_high, b.high)
        if run_high < open_p * (1.0 + rally_pct):
            continue
        if b.close <= run_high * (1.0 - cfg.cell_c_pullback_x):
            return i
    return None


def _baseline_entry_idx(bars: list[Bar1K]) -> int | None:
    for i, b in enumerate(bars):
        if b.m >= _BASELINE_M:
            return i
    return None


@dataclasses.dataclass(frozen=True, slots=True)
class _CellSpec:
    cell: str
    variant: str
    observation: bool


def _calendar_segment(day: str, start: _date, seg_days: float, k: int) -> int:
    if seg_days <= 0:
        return 0
    idx = int((_date.fromisoformat(day) - start).days / seg_days)
    return min(k - 1, max(0, idx))


def _stats_block(
    trades: list[tuple[float, str]], start: _date, seg_days: float, k: int
) -> dict[str, object]:
    pnl = [t[0] for t in trades]
    seg_sums = [0.0] * k
    seg_ns = [0] * k
    for p, d in trades:
        si = _calendar_segment(d, start, seg_days, k)
        seg_sums[si] += p
        seg_ns[si] += 1
    return {
        "n": len(pnl),
        "mean": (sum(pnl) / len(pnl)) if pnl else None,
        "p_win": (sum(1 for x in pnl if x > 0) / len(pnl)) if pnl else None,
        "segments": [
            {"n": n, "sum": s, "positive": s > 0} for s, n in zip(seg_sums, seg_ns)
        ],
        "positive_segments": sum(1 for s, n in zip(seg_sums, seg_ns) if n > 0 and s > 0),
    }


def _simulate_cell_trades(
    universe: list[tuple[FadeSample, list[Bar1K]]],
    spec: _CellSpec,
    param: float,
    cfg: FadeBacktestConfig,
    slippage_ticks: int,
) -> list[tuple[float, str]]:
    """單一 cell×variant 於 universe 上的成交(pnl, t1_date)清單."""
    out: list[tuple[float, str]] = []
    for sample, bars in universe:
        if not bars:
            continue
        t1_limit = limit_up_price(sample.limit)
        fixed_stop: float | None = None
        sim_cfg = cfg
        if spec.cell == "cell_a":
            idx = find_cell_a_entry(bars, t1_limit, param, cfg)
        elif spec.cell == "cell_b":
            found = find_cell_b_entry(bars, t1_limit, param, cfg)
            if found is None:
                continue
            idx, approach_high = found
            fixed_stop = approach_high * (1.0 + cfg.cell_b_stop_buffer)
            sim_cfg = dataclasses.replace(cfg, guard_limit_dist=None)  # 自帶風控(SC-4)
        elif spec.cell == "cell_c":
            idx = find_cell_c_entry(bars, param, cfg)
        else:  # baseline_m7
            idx = _baseline_entry_idx(bars)
        if idx is None or idx >= len(bars) - 1:
            continue
        r = simulate_fade_sample(
            bars, idx, sample, _NO_STOP_COMBO, sim_cfg, slippage_ticks,
            fixed_stop_level=fixed_stop,
        )
        if r.status in _TRADEABLE and r.pnl_rate is not None:
            out.append((r.pnl_rate, sample.t1_date))
    return out


def evaluate_cells_from_universe(
    main_universe: list[tuple[FadeSample, list[Bar1K]]],
    low_universe: list[tuple[FadeSample, list[Bar1K]]],
    cfg: FadeBacktestConfig,
    watchlist_ids: frozenset[str],
) -> dict[str, object]:
    """純評估(IO 由 run_cells 負責):UC 過濾 → 觸發 → base/stress 模擬 →
    四等分 + D5(壓測組合)+ 基準線對照."""
    main_uc = [(s, b) for s, b in main_universe if is_uc_sample(s, watchlist_ids)]
    low_uc = [(s, b) for s, b in low_universe if is_uc_sample(s, watchlist_ids)]

    all_days = [s.t1_date for s, _ in main_uc + low_uc]
    k = cfg.cells_eval_segments
    if all_days:
        start = _date.fromisoformat(min(all_days))
        end = _date.fromisoformat(max(all_days))
        seg_days = max(((end - start).days + 1) / k, 1.0)
    else:
        start = _date(2025, 1, 1)
        seg_days = 1.0

    stress_cfg = dataclasses.replace(cfg, stress_guard_fill_high=True)

    specs: list[tuple[_CellSpec, float, list[tuple[FadeSample, list[Bar1K]]]]] = []
    for thr in cfg.cell_a_inner_thresholds:
        specs.append((_CellSpec("cell_a", f"inner_{thr}", False), thr, main_uc))
    for d in cfg.cell_b_approach_dists:
        specs.append((_CellSpec("cell_b", f"dist_{d}", False), d, main_uc))
    for r in cfg.cell_c_rally_pcts:
        specs.append((_CellSpec("cell_c", f"rally_{r}", True), r, low_uc))

    baselines: dict[str, dict[str, object]] = {}
    for name, uni in (("main", main_uc), ("low", low_uc)):
        base_trades = _simulate_cell_trades(
            uni, _CellSpec("baseline_m7", "-", False), 0.0, cfg, cfg.slippage_ticks
        )
        stress_trades = _simulate_cell_trades(
            uni,
            _CellSpec("baseline_m7", "-", False),
            0.0,
            stress_cfg,
            cfg.stress_slippage_ticks,
        )
        baselines[name] = {
            "base": _stats_block(base_trades, start, seg_days, k),
            "stress": _stats_block(stress_trades, start, seg_days, k),
        }

    cells: dict[str, object] = {}
    for spec, param, uni in specs:
        base_trades = _simulate_cell_trades(uni, spec, param, cfg, cfg.slippage_ticks)
        stress_trades = _simulate_cell_trades(
            uni, spec, param, stress_cfg, cfg.stress_slippage_ticks
        )
        base_stats = _stats_block(base_trades, start, seg_days, k)
        stress_stats = _stats_block(stress_trades, start, seg_days, k)
        baseline_key = "low" if spec.cell == "cell_c" else "main"
        baseline_mean = baselines[baseline_key]["base"].get("mean")  # type: ignore[union-attr]

        d5: dict[str, object] = {"applicable": not spec.observation}
        if not spec.observation:
            s_mean = stress_stats.get("mean")
            s_n = stress_stats.get("n")
            pos = stress_stats.get("positive_segments")
            total_pos = isinstance(s_mean, float) and s_mean > 0
            crit = {
                "stress_ev_ge_min": isinstance(s_mean, float) and s_mean >= cfg.d5_min_ev,
                "n_ge_min": isinstance(s_n, int) and s_n >= cfg.d5_min_n,
                "segments_direction": (
                    isinstance(pos, int) and pos >= cfg.d5_min_positive_segments and total_pos
                ),
            }
            d5.update({"criteria": crit, "passed": all(crit.values())})

        vs_baseline = None
        b_mean = base_stats.get("mean")
        if isinstance(b_mean, float) and isinstance(baseline_mean, float):
            vs_baseline = b_mean - baseline_mean
        cells[f"{spec.cell}:{spec.variant}"] = {
            "cell": spec.cell,
            "variant": spec.variant,
            "observation": spec.observation,
            "base": base_stats,
            "stress": stress_stats,
            "vs_baseline_mean": vs_baseline,
            "d5": d5,
        }

    return {
        "n_uc_main": len(main_uc),
        "n_uc_low": len(low_uc),
        "segments": k,
        "cells": cells,
        "baselines": baselines,
    }


def write_cells_report(
    result: dict[str, object], cfg: FadeBacktestConfig, report_date: str, path: Path
) -> None:
    lines: list[str] = []
    lines.append(f"# UC 池劇本格子評估(pre-registered;{report_date})")
    lines.append("")
    lines.append(
        f"- 宇宙:UC 池(main n={result.get('n_uc_main')} / 低開 n={result.get('n_uc_low')});"
        f"等日曆 {result.get('segments')} 段方向一致;D5 門檻 = 壓測後淨 EV ≥ {cfg.d5_min_ev}"
        f" + n ≥ {cfg.d5_min_n} + ≥{cfg.d5_min_positive_segments} 段為正且合計正。"
    )
    lines.append("- D5 壓測組合 = stress_slippage + guard fill = bar.high 疊加(R6)。")
    lines.append("- 門檻源自同期診斷(meta 汙染),最終判定 = forward。")
    lines.append("")
    lines.append("| cell | variant | n | 淨EV | p_win | 壓測EV | 壓測n | 段+ | vs基準線 | D5 |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---|")
    cells = result.get("cells")
    assert isinstance(cells, dict)
    _f = _fmt

    for key in sorted(cells):
        c = cells[key]
        if not isinstance(c, dict):
            continue
        base = c.get("base", {})
        stress = c.get("stress", {})
        assert isinstance(base, dict) and isinstance(stress, dict)
        d5 = c.get("d5", {})
        assert isinstance(d5, dict)
        d5_txt = (
            "觀察格"
            if c.get("observation")
            else ("PASS" if d5.get("passed") else "FAIL")
        )
        lines.append(
            f"| {c.get('cell')} | {c.get('variant')} | {base.get('n', 0)}"
            f" | {_f(base.get('mean'))} | {_f(base.get('p_win'), '.2f')}"
            f" | {_f(stress.get('mean'))} | {stress.get('n', 0)}"
            f" | {base.get('positive_segments', 0)}/{result.get('segments')}"
            f" | {_f(c.get('vs_baseline_mean'))} | {d5_txt} |"
        )
    lines.append("")
    baselines = result.get("baselines")
    if isinstance(baselines, dict):
        lines.append("## 基準線(同宇宙第 7 分鐘無條件空)")
        lines.append("")
        lines.append("| universe | n | 淨EV | 壓測EV |")
        lines.append("|---|---:|---:|---:|")
        for name, b in sorted(baselines.items()):
            if not isinstance(b, dict):
                continue
            base = b.get("base", {})
            stress = b.get("stress", {})
            assert isinstance(base, dict) and isinstance(stress, dict)
            lines.append(
                f"| {name} | {base.get('n', 0)} | {_f(base.get('mean'))}"
                f" | {_f(stress.get('mean'))} |"
            )
        lines.append("")

    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def run_cells(
    data_dir: Path,
    out_dir: Path,
    cfg: FadeBacktestConfig,
    report_date: str,
    watchlist_path: Path,
    report_dir: Path | None = None,
) -> Path:
    """CLI 協調:主池 + 低開池 universe → bars → 評估 → JSON + 報告."""
    from copycat.backtest.fade_pipeline import build_fade_universe  # 延遲:避免與 pipeline 互import

    from copycat.data.store import read_bars
    from copycat.watchlist import load_watchlist

    events = data_dir / "events" / "events.csv"
    main_samples, main_counts = build_fade_universe(data_dir, events, cfg)
    low_cfg = dataclasses.replace(cfg, fade_gap_min=-0.095, fade_gap_max=0.01)
    low_samples, low_counts = build_fade_universe(data_dir, events, low_cfg)

    def _with_bars(samples: list[FadeSample]) -> list[tuple[FadeSample, list[Bar1K]]]:
        out: list[tuple[FadeSample, list[Bar1K]]] = []
        for s in samples:
            bars = read_bars(data_dir, s.stock_id, s.t1_date)
            if bars:
                out.append((s, bars))
        return out

    watchlist = load_watchlist(watchlist_path)
    result = evaluate_cells_from_universe(
        _with_bars(main_samples), _with_bars(low_samples), cfg, watchlist.broker_ids
    )
    result["universe_counts_main"] = main_counts
    result["universe_counts_low"] = low_counts

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"cells_{report_date}.json"
    tmp = json_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, json_path)

    report_path = out_dir / f"uc_cells_{report_date}.md"
    write_cells_report(result, cfg, report_date, report_path)
    if report_dir is not None:
        report_dir.mkdir(parents=True, exist_ok=True)
        write_cells_report(result, cfg, report_date, report_dir / report_path.name)
    return report_path
