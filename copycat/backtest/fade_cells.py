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
    _round_trip_cost,
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
) -> tuple[int, float] | None:
    """先拉再出:窗內拉高 ≥ min_rally 後,收盤自高點回落 ≥ pullback_x,
    且進場當下(累計至該 bar)內盤比 ≥ 閾值、headroom ≥ 門檻 →
    (entry_idx, 結構高 = 進場前盤中高點)."""
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
            return i, run_high
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
) -> tuple[int, float] | None:
    """低開反拉:自開盤反拉 ≥ r 後,收盤自高點回落 ≥ pullback_x 進場 →
    (entry_idx, 結構高 = 反拉高點)."""
    open_p = bars[0].open
    if open_p <= 0:
        return None
    run_high = 0.0
    for i, b in enumerate(bars):
        run_high = max(run_high, b.high)
        if run_high < open_p * (1.0 + rally_pct):
            continue
        if b.close <= run_high * (1.0 - cfg.cell_c_pullback_x):
            return i, run_high
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
    wins = [x for x in pnl if x > 0]
    losses = [x for x in pnl if x < 0]
    return {
        "n": len(pnl),
        "mean": (sum(pnl) / len(pnl)) if pnl else None,
        "p_win": (sum(1 for x in pnl if x > 0) / len(pnl)) if pnl else None,
        # round 4 報告義務:賺賠比(判定仍以淨 EV 為準)
        "avg_win": (sum(wins) / len(wins)) if wins else None,
        "avg_loss": (sum(losses) / len(losses)) if losses else None,
        "profit_factor": (sum(wins) / abs(sum(losses))) if wins and losses else None,
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
            found_a = find_cell_a_entry(bars, t1_limit, param, cfg)
            idx = found_a[0] if found_a is not None else None
        elif spec.cell == "cell_b":
            found = find_cell_b_entry(bars, t1_limit, param, cfg)
            if found is None:
                continue
            idx, approach_high = found
            fixed_stop = approach_high * (1.0 + cfg.cell_b_stop_buffer)
            sim_cfg = dataclasses.replace(cfg, guard_limit_dist=None)  # 自帶風控(SC-4)
        elif spec.cell == "cell_c":
            found_c = find_cell_c_entry(bars, param, cfg)
            idx = found_c[0] if found_c is not None else None
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
    cellb_universe: list[tuple[FadeSample, list[Bar1K]]] | None = None,
) -> dict[str, object]:
    """純評估(IO 由 run_cells 負責):UC 過濾 → 觸發 → base/stress 模擬 →
    四等分 + D5(壓測組合)+ 基準線對照.

    round 4 gate(change-spec §5.4,優先於 round 3):tp_flush_z / tp_hl_k /
    inner_flip_phi_grid 任一啟用 → round 4 路徑(劇本結構化出場)。
    round 3 gate(change-spec §9.3):struct_stop_buffers 非空 → round 3 路徑
    (結構停損 × b 變體 + 底倉臂 + 精算表 + forward 切分);空 = round 2 形狀,
    cellb_universe 被忽略(舊 config 行為完全不變)。
    """
    if _round4_enabled(cfg):
        return _evaluate_round4(
            main_universe,
            low_universe,
            cellb_universe if cellb_universe is not None else main_universe,
            cfg,
            watchlist_ids,
        )
    if cfg.struct_stop_buffers:
        return _evaluate_round3(
            main_universe,
            low_universe,
            cellb_universe if cellb_universe is not None else main_universe,
            cfg,
            watchlist_ids,
        )
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


# ---------- round 3(change-spec §9.3;gate = struct_stop_buffers 非空)----------


@dataclasses.dataclass(frozen=True, slots=True)
class _TradeRec:
    pnl: float
    day: str
    exit_reason: str | None
    locked_close: bool
    gap: float
    hits: int
    # round 4:MFE(毛)/ 抱到收盤對照(收盤鎖死日 = None)/ 引擎進場價
    mfe: float | None = None
    hold_pnl: float | None = None
    entry_price: float | None = None


def _broker_hits(sample: FadeSample, watchlist_ids: frozenset[str]) -> int:
    return len([x for x in sample.broker_ids.split("|") if x and x in watchlist_ids])


def _simulate_r3_trades(
    universe: list[tuple[FadeSample, list[Bar1K]]],
    kind: str,
    param: float,
    b: float,
    cfg: FadeBacktestConfig,
    slippage_ticks: int,
    watchlist_ids: frozenset[str],
    inner_flip_phi: float | None = None,
    disable_struct: bool = False,
) -> tuple[list[_TradeRec], dict[str, int]]:
    """單一 kind×param×b 的成交紀錄 + b_capped 計數(依 forward_start 分段)。

    主停損 = min(結構高×(1+b), 硬線):capped(結構停損 ≥ guard_level)時傳
    fixed_stop=None 由 guard 單獨實現(change-spec §3a 二輪 R1),事件保留。
    round 4:inner_flip_phi 穿透引擎;disable_struct = 消融「停損只 inner_flip」
    (fixed_stop 與 ratchet 傳 None,硬線災難保留);kind "m7_arm" 與 baseline_m7
    同進場(差異只在 caller 給不給 round 4 出場)。
    """
    trades: list[_TradeRec] = []
    capped = {"in_window": 0, "forward": 0}
    guard_level_dist = cfg.guard_limit_dist
    for sample, bars in universe:
        if not bars:
            continue
        t1_limit = limit_up_price(sample.limit)
        guard_level = (
            t1_limit * (1.0 - guard_level_dist) if guard_level_dist is not None else None
        )
        fixed_stop: float | None = None
        ratchet: float | None = None
        entry_override: float | None = None
        struct_high: float | None = None
        idx: int | None
        if kind == "cell_a":
            found_a = find_cell_a_entry(bars, t1_limit, param, cfg)
            if found_a is None:
                continue
            idx, struct_high = found_a
        elif kind == "cell_b":
            found_b = find_cell_b_entry(bars, t1_limit, param, cfg)
            if found_b is None:
                continue
            idx, struct_high = found_b
        elif kind == "cell_c":
            found_c = find_cell_c_entry(bars, param, cfg)
            if found_c is None:
                continue
            idx, struct_high = found_c
        elif kind == "base_arm":
            idx = 0
            entry_override = bars[0].open
            ratchet = b
        else:  # baseline_m7 / m7_arm(第 7 分鐘進場;風控 = ratchet + 災難 + 硬線)
            idx = _baseline_entry_idx(bars)
            ratchet = b
        if idx is None or idx >= len(bars) - 1:
            continue
        was_capped = False
        if struct_high is not None:
            fixed_stop = struct_high * (1.0 + b)
            if guard_level is not None and fixed_stop >= guard_level:
                fixed_stop = None  # 硬線封頂(min() 語意)
                was_capped = True
        if disable_struct:
            fixed_stop = None
            ratchet = None
            was_capped = False
        r = simulate_fade_sample(
            bars,
            idx,
            sample,
            _NO_STOP_COMBO,
            cfg,
            slippage_ticks,
            entry_price_override=entry_override,
            fixed_stop_level=fixed_stop,
            ratchet_stop_b=ratchet,
            inner_flip_phi=inner_flip_phi,
        )
        if r.status in _TRADEABLE and r.pnl_rate is not None:
            if was_capped:  # 只計入統計的交易(封頂數 ≤ n;review A4)
                seg = "forward" if sample.t1_date >= cfg.forward_start else "in_window"
                capped[seg] += 1
            locked_close = bars[-1].low >= t1_limit - cfg.limit_eps
            hold_pnl: float | None = None
            if not locked_close and r.entry_price is not None:
                # 抱到收盤對照(entry 取引擎回傳,cost 取引擎單一定義 — review P1)
                hold_pnl = 1.0 - bars[-1].close / r.entry_price - _round_trip_cost(cfg)
            trades.append(
                _TradeRec(
                    pnl=r.pnl_rate,
                    day=sample.t1_date,
                    exit_reason=r.exit_reason,
                    locked_close=locked_close,
                    gap=sample.gap,
                    hits=_broker_hits(sample, watchlist_ids),
                    mfe=r.mfe_rate,
                    hold_pnl=hold_pnl,
                    entry_price=r.entry_price,
                )
            )
    return trades, capped


_ACTUARIAL_REASONS = (
    "hardline",
    "struct_fixed",
    "struct_ratchet",
    "disaster_retrace",
    "disaster_x",  # 舊式災難(round3 gate 與 disaster_x 可合法共存,不得漏列;review A2)
)

# round 4:inner_flip 入停損精算;round 3 路徑沿用舊 tuple(白名單:輸出不變)
_ACTUARIAL_REASONS_R4 = (*_ACTUARIAL_REASONS, "inner_flip")


def _pctl(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[idx]


def _tp_actuarial_block(trades: list[_TradeRec]) -> dict[str, object]:
    """停利精算表(round 4):saved = pnl − hold_pnl(同淨口徑,成本相消);
    收盤鎖死日 hold_pnl=None 排除並計數(防省肉灌水)."""
    n_total = len(trades)
    out: dict[str, object] = {}
    for reason in ("tp_flush", "tp_hl"):
        sub = [t for t in trades if t.exit_reason == reason]
        saved = [t.pnl - t.hold_pnl for t in sub if t.hold_pnl is not None]
        out[reason] = {
            "n": len(sub),
            "rate": (len(sub) / n_total) if n_total else None,
            "avg_pnl": (sum(t.pnl for t in sub) / len(sub)) if sub else None,
            "saved_mean": (sum(saved) / len(saved)) if saved else None,
            "saved_p25": _pctl(saved, 0.25),
            "saved_p50": _pctl(saved, 0.50),
            "saved_p75": _pctl(saved, 0.75),
            "saved_excluded_lock": sum(1 for t in sub if t.hold_pnl is None),
        }
    return out


def _actuarial_block(
    trades: list[_TradeRec], reasons: tuple[str, ...] = _ACTUARIAL_REASONS
) -> dict[str, object]:
    """保險精算表(SC-4):每機制觸發率 / 均成本 / 砍對(收盤鎖死)vs 砍錯比例."""
    n_total = len(trades)
    out: dict[str, object] = {}
    for reason in reasons:
        sub = [t for t in trades if t.exit_reason == reason]
        out[reason] = {
            "n": len(sub),
            "rate": (len(sub) / n_total) if n_total else None,
            "avg_pnl": (sum(t.pnl for t in sub) / len(sub)) if sub else None,
            "cut_right": (sum(1 for t in sub if t.locked_close) / len(sub)) if sub else None,
            "cut_wrong": (sum(1 for t in sub if not t.locked_close) / len(sub)) if sub else None,
        }
    return out


def _cluster_z_block(trades: list[_TradeRec], p_threshold: float) -> dict[str, object]:
    """日聚類 z 單尾檢定(Q2 / 底倉格開放判定共用)."""
    from copycat.backtest.fade_diagnose import _normal_tail, cluster_se

    if not trades:
        return {"n": 0, "mean": None, "se": None, "z": None, "p": None, "pass": False}
    pnl = [t.pnl for t in trades]
    days = [t.day for t in trades]
    mean = sum(pnl) / len(pnl)
    se = cluster_se(pnl, days)
    if se > 0:
        z = mean / se
        p = _normal_tail(z) if mean > 0 else 1.0
    else:
        z = float("inf") if mean > 0 else 0.0
        p = 0.0 if mean > 0 else 1.0
    return {
        "n": len(pnl),
        "mean": mean,
        "se": se,
        "z": z,
        "p": p,
        "pass": mean > 0 and p < p_threshold,
    }


def _split_fw(
    trades: list[_TradeRec], forward_start: str
) -> tuple[list[_TradeRec], list[_TradeRec]]:
    in_w = [t for t in trades if t.day < forward_start]
    fwd = [t for t in trades if t.day >= forward_start]
    return in_w, fwd


def _rec_stats(
    trades: list[_TradeRec], start: _date, seg_days: float, k: int
) -> dict[str, object]:
    return _stats_block([(t.pnl, t.day) for t in trades], start, seg_days, k)


def _evaluate_round3(
    main_universe: list[tuple[FadeSample, list[Bar1K]]],
    low_universe: list[tuple[FadeSample, list[Bar1K]]],
    cellb_universe: list[tuple[FadeSample, list[Bar1K]]],
    cfg: FadeBacktestConfig,
    watchlist_ids: frozenset[str],
) -> dict[str, object]:
    """round 3 評估:b 變體 × cells + 底倉臂 + Q2 + 精算表 + forward 切分。

    判定段紀律(SC-7):D5 / Q2 / 底倉格開放一律以 in-window(< forward_start)計,
    forward 段僅複核輸出(門檻見 SC-2)。
    """
    main_uc = [(s, b) for s, b in main_universe if is_uc_sample(s, watchlist_ids)]
    low_uc = [(s, b) for s, b in low_universe if is_uc_sample(s, watchlist_ids)]
    cellb_uc = [(s, b) for s, b in cellb_universe if is_uc_sample(s, watchlist_ids)]

    k = cfg.cells_eval_segments
    in_days = [
        s.t1_date for s, _ in main_uc + low_uc + cellb_uc if s.t1_date < cfg.forward_start
    ]
    if in_days:
        start = _date.fromisoformat(min(in_days))
        end = _date.fromisoformat(max(in_days))
        seg_days = max(((end - start).days + 1) / k, 1.0)
    else:
        start = _date(2025, 1, 1)
        seg_days = 1.0

    stress_cfg = dataclasses.replace(cfg, stress_guard_fill_high=True)

    specs: list[tuple[str, str, float, list[tuple[FadeSample, list[Bar1K]]], str]] = []
    for thr in cfg.cell_a_inner_thresholds:
        specs.append(("cell_a", f"inner_{thr}", thr, main_uc, "main"))
    for d in cfg.cell_b_approach_dists:
        specs.append(("cell_b", f"dist_{d}", d, cellb_uc, "cellb"))
    for r in cfg.cell_c_rally_pcts:
        specs.append(("cell_c", f"rally_{r}", r, low_uc, "low"))

    # 基準線(同宇宙同風控):per 宇宙 × b
    baselines: dict[str, dict[str, object]] = {}
    for name, uni in (("main", main_uc), ("low", low_uc), ("cellb", cellb_uc)):
        for b in cfg.struct_stop_buffers:
            base_tr, _ = _simulate_r3_trades(
                uni, "baseline_m7", 0.0, b, cfg, cfg.slippage_ticks, watchlist_ids
            )
            in_w, fwd = _split_fw(base_tr, cfg.forward_start)
            baselines[f"{name}:b{b:g}"] = {
                "in_window": _rec_stats(in_w, start, seg_days, k),
                "forward": _rec_stats(fwd, start, seg_days, k),
            }

    cells: dict[str, object] = {}
    for b in cfg.struct_stop_buffers:
        for kind, variant, param, uni, base_key in specs:
            base_tr, capped = _simulate_r3_trades(
                uni, kind, param, b, cfg, cfg.slippage_ticks, watchlist_ids
            )
            stress_tr, _ = _simulate_r3_trades(
                uni, kind, param, b, stress_cfg, cfg.stress_slippage_ticks, watchlist_ids
            )
            in_w, fwd = _split_fw(base_tr, cfg.forward_start)
            s_in, _ = _split_fw(stress_tr, cfg.forward_start)
            in_stats = _rec_stats(in_w, start, seg_days, k)
            stress_stats = _rec_stats(s_in, start, seg_days, k)

            s_mean = stress_stats.get("mean")
            s_n = stress_stats.get("n")
            pos = stress_stats.get("positive_segments")
            crit = {
                "stress_ev_ge_min": isinstance(s_mean, float) and s_mean >= cfg.d5_min_ev,
                "n_ge_min": isinstance(s_n, int) and s_n >= cfg.d5_min_n,
                "segments_direction": (
                    isinstance(pos, int)
                    and pos >= cfg.d5_min_positive_segments
                    and isinstance(s_mean, float)
                    and s_mean > 0
                ),
            }
            baseline_stats = baselines[f"{base_key}:b{b:g}"]["in_window"]
            baseline_mean = (
                baseline_stats.get("mean") if isinstance(baseline_stats, dict) else None
            )
            vs_baseline = None
            b_mean = in_stats.get("mean")
            if isinstance(b_mean, float) and isinstance(baseline_mean, float):
                vs_baseline = b_mean - baseline_mean
            cells[f"{kind}:{variant}:b{b:g}"] = {
                "cell": kind,
                "variant": variant,
                "b": b,
                "observation": False,  # round 3:cell_c 升正式,全變體入 D5
                "in_window": {
                    "base": in_stats,
                    "stress": stress_stats,
                    "actuarial": _actuarial_block(in_w),
                    "b_capped": capped["in_window"],
                },
                "forward": {"base": _rec_stats(fwd, start, seg_days, k)},
                "vs_baseline_mean": vs_baseline,
                "d5": {"applicable": True, "criteria": crit, "passed": all(crit.values())},
            }

    # 底倉臂:分點數(2+/1)× gap 桶;Q2 = tiger 合併(in-window),b1 為判定主變體
    base_arm: dict[str, object] = {}
    if cfg.base_arm:
        edges = cfg.base_arm_gap_edges
        for i, b in enumerate(cfg.struct_stop_buffers):
            arm_tr, _ = _simulate_r3_trades(
                main_uc, "base_arm", 0.0, b, cfg, cfg.slippage_ticks, watchlist_ids
            )
            in_w, fwd = _split_fw(arm_tr, cfg.forward_start)
            grid: dict[str, object] = {}
            for lo, hi in zip(edges, edges[1:]):
                for tag, cond in (("2plus", 2), ("1", 1)):
                    sub = [
                        t
                        for t in in_w
                        if lo <= t.gap < hi
                        and (t.hits >= 2 if cond == 2 else t.hits == 1)
                    ]
                    blk = _cluster_z_block(sub, cfg.diagnose_p_threshold)
                    blk["open"] = bool(blk["pass"]) and (
                        isinstance(blk["n"], int) and blk["n"] >= cfg.d5_min_n
                    )
                    grid[f"{tag}:gap_{lo:g}_{hi:g}"] = blk
            q2 = _cluster_z_block(in_w, cfg.diagnose_p_threshold)
            q2["primary"] = i == 0  # b1 = 判定主變體(change-spec §9.3,事先寫死)
            base_arm[f"b{b:g}"] = {
                "grid": grid,
                "in_window": {
                    "base": _rec_stats(in_w, start, seg_days, k),
                    "actuarial": _actuarial_block(in_w),
                },
                "forward": {"base": _rec_stats(fwd, start, seg_days, k)},
                "q2": q2,
            }

    logger.info(
        "evaluate_round3 main=%d low=%d cellb=%d cells=%d base_arm=%s",
        len(main_uc),
        len(low_uc),
        len(cellb_uc),
        len(cells),
        sorted(base_arm),
    )
    return {
        "round3": True,
        "n_uc_main": len(main_uc),
        "n_uc_low": len(low_uc),
        "n_uc_cellb": len(cellb_uc),
        "segments": k,
        "forward_start": cfg.forward_start,
        "cells": cells,
        "base_arm": base_arm,
        "baselines": baselines,
    }


# ---------- round 4(change-spec §5.4;gate = tp_flush_z / tp_hl_k / inner_flip_phi_grid)----------


def _round4_enabled(cfg: FadeBacktestConfig) -> bool:
    return (
        cfg.tp_flush_z is not None or cfg.tp_hl_k is not None or bool(cfg.inner_flip_phi_grid)
    )


_R4_TP_OFF = {
    "tp_flush_z": None,
    "tp_flush_lookback": None,
    "tp_flush_recovery": None,
    "tp_flush_min_profit": None,
    "tp_hl_k": None,
    "tp_hl_min_profit": None,
}


def _evaluate_round4(
    main_universe: list[tuple[FadeSample, list[Bar1K]]],
    low_universe: list[tuple[FadeSample, list[Bar1K]]],
    cellb_universe: list[tuple[FadeSample, list[Bar1K]]],
    cfg: FadeBacktestConfig,
    watchlist_ids: frozenset[str],
) -> dict[str, object]:
    """round 4 評估:劇本結構化出場(inner_flip 停損 + TP 決策樹)。

    主判定 5 變體(cell_a/b/c×2/m7_arm)× b 主值 × φ 主值;量尺 = 第 7 分鐘 +
    round 3 舊出場;消融 / 敏感度不入判定;Q2′ = base_arm 套新出場(in-window)。
    fallback(事先寫死):φ grid 空 → φ=None 跑並註記 DEMOTED;tp_hl_k=None →
    樹只剩 flush 並註記 DEMOTED(prereg 2026-07-16 §0(c)(d))。
    """
    main_uc = [(s, b) for s, b in main_universe if is_uc_sample(s, watchlist_ids)]
    low_uc = [(s, b) for s, b in low_universe if is_uc_sample(s, watchlist_ids)]
    cellb_uc = [(s, b) for s, b in cellb_universe if is_uc_sample(s, watchlist_ids)]

    k = cfg.cells_eval_segments
    in_days = [
        s.t1_date for s, _ in main_uc + low_uc + cellb_uc if s.t1_date < cfg.forward_start
    ]
    if in_days:
        start = _date.fromisoformat(min(in_days))
        end = _date.fromisoformat(max(in_days))
        seg_days = max(((end - start).days + 1) / k, 1.0)
    else:
        start = _date(2025, 1, 1)
        seg_days = 1.0

    if not cfg.struct_stop_buffers:
        raise ValueError("round 4 config 仍需 struct_stop_buffers 提供 b 值")
    b_main = cfg.struct_stop_buffers[0]
    b_sens = cfg.struct_stop_buffers[1] if len(cfg.struct_stop_buffers) > 1 else None
    phi_main = cfg.inner_flip_phi_grid[0] if cfg.inner_flip_phi_grid else None
    phi_sens = cfg.inner_flip_phi_grid[1] if len(cfg.inner_flip_phi_grid) > 1 else None
    inner_demoted = phi_main is None  # fallback #1
    hl_demoted = cfg.tp_hl_k is None  # fallback #2

    stress_cfg = dataclasses.replace(cfg, stress_guard_fill_high=True)
    cfg_legacy = dataclasses.replace(cfg, **_R4_TP_OFF)  # 量尺 = round 3 舊出場

    # 主判定 5 變體(round 4 config 收斂單值 tuple;cell_c 兩值皆跑)
    specs: list[tuple[str, str, float, list[tuple[FadeSample, list[Bar1K]]], str]] = []
    for thr in cfg.cell_a_inner_thresholds:
        specs.append(("cell_a", f"inner_{thr}", thr, main_uc, "main"))
    for d in cfg.cell_b_approach_dists:
        specs.append(("cell_b", f"dist_{d}", d, cellb_uc, "cellb"))
    for r in cfg.cell_c_rally_pcts:
        specs.append(("cell_c", f"rally_{r}", r, low_uc, "low"))
    specs.append(("m7_arm", "m7", 0.0, main_uc, "main"))

    def _run(
        uni: list[tuple[FadeSample, list[Bar1K]]],
        kind: str,
        param: float,
        b: float,
        phi: float | None,
        run_cfg: FadeBacktestConfig,
        slippage: int,
        disable_struct: bool = False,
    ) -> tuple[list[_TradeRec], dict[str, int]]:
        return _simulate_r3_trades(
            uni,
            kind,
            param,
            b,
            run_cfg,
            slippage,
            watchlist_ids,
            inner_flip_phi=phi,
            disable_struct=disable_struct,
        )

    # 量尺基準線:第 7 分鐘 + round 3 舊出場(φ=None、TP off),per 宇宙
    baselines: dict[str, dict[str, object]] = {}
    for name, uni in (("main", main_uc), ("low", low_uc), ("cellb", cellb_uc)):
        base_tr, _ = _run(uni, "baseline_m7", 0.0, b_main, None, cfg_legacy, cfg.slippage_ticks)
        in_w, fwd = _split_fw(base_tr, cfg.forward_start)
        baselines[f"{name}:legacy_b{b_main:g}"] = {
            "in_window": _rec_stats(in_w, start, seg_days, k),
            "forward": _rec_stats(fwd, start, seg_days, k),
        }

    def _variant_block(
        kind: str,
        variant: str,
        param: float,
        uni: list[tuple[FadeSample, list[Bar1K]]],
        base_key: str,
        b: float,
        phi: float | None,
    ) -> dict[str, object]:
        base_tr, capped = _run(uni, kind, param, b, phi, cfg, cfg.slippage_ticks)
        stress_tr, _ = _run(uni, kind, param, b, phi, stress_cfg, cfg.stress_slippage_ticks)
        in_w, fwd = _split_fw(base_tr, cfg.forward_start)
        s_in, _ = _split_fw(stress_tr, cfg.forward_start)
        in_stats = _rec_stats(in_w, start, seg_days, k)
        stress_stats = _rec_stats(s_in, start, seg_days, k)
        s_mean = stress_stats.get("mean")
        s_n = stress_stats.get("n")
        pos = stress_stats.get("positive_segments")
        crit = {
            "stress_ev_ge_min": isinstance(s_mean, float) and s_mean >= cfg.d5_min_ev,
            "n_ge_min": isinstance(s_n, int) and s_n >= cfg.d5_min_n,
            "segments_direction": (
                isinstance(pos, int)
                and pos >= cfg.d5_min_positive_segments
                and isinstance(s_mean, float)
                and s_mean > 0
            ),
        }
        baseline_stats = baselines[f"{base_key}:legacy_b{b_main:g}"]["in_window"]
        baseline_mean = baseline_stats.get("mean") if isinstance(baseline_stats, dict) else None
        vs_baseline = None
        b_mean = in_stats.get("mean")
        if isinstance(b_mean, float) and isinstance(baseline_mean, float):
            vs_baseline = b_mean - baseline_mean
        return {
            "cell": kind,
            "variant": variant,
            "b": b,
            "phi": phi,
            "in_window": {
                "base": in_stats,
                "stress": stress_stats,
                "actuarial": _actuarial_block(in_w, _ACTUARIAL_REASONS_R4),
                "tp_actuarial": _tp_actuarial_block(in_w),
                "b_capped": capped["in_window"],
            },
            "forward": {"base": _rec_stats(fwd, start, seg_days, k)},
            "vs_baseline_mean": vs_baseline,
            "d5": {"applicable": True, "criteria": crit, "passed": all(crit.values())},
        }

    cells: dict[str, object] = {}
    for kind, variant, param, uni, base_key in specs:
        cells[f"{kind}:{variant}:b{b_main:g}"] = _variant_block(
            kind, variant, param, uni, base_key, b_main, phi_main
        )

    # 敏感度列(不入 D5;報告獨立節):φ 次值 / b 次值重跑主 5 變體
    sensitivity: dict[str, object] = {}
    if phi_sens is not None and not inner_demoted:
        for kind, variant, param, uni, base_key in specs:
            sensitivity[f"phi{phi_sens:g}:{kind}:{variant}"] = _variant_block(
                kind, variant, param, uni, base_key, b_main, phi_sens
            )
    if b_sens is not None:
        for kind, variant, param, uni, base_key in specs:
            sensitivity[f"b{b_sens:g}:{kind}:{variant}"] = _variant_block(
                kind, variant, param, uni, base_key, b_sens, phi_main
            )

    # 底倉臂 + Q2′(交易集合寫死 = base_arm 套新出場、in-window;主 5 變體不入)
    base_arm: dict[str, object] = {}
    if cfg.base_arm:
        edges = cfg.base_arm_gap_edges
        arm_tr, _ = _run(main_uc, "base_arm", 0.0, b_main, phi_main, cfg, cfg.slippage_ticks)
        in_w, fwd = _split_fw(arm_tr, cfg.forward_start)
        grid: dict[str, object] = {}
        for lo, hi in zip(edges, edges[1:]):
            for tag, cond in (("2plus", 2), ("1", 1)):
                sub = [
                    t
                    for t in in_w
                    if lo <= t.gap < hi and (t.hits >= 2 if cond == 2 else t.hits == 1)
                ]
                blk = _cluster_z_block(sub, cfg.diagnose_p_threshold)
                blk["open"] = bool(blk["pass"]) and (
                    isinstance(blk["n"], int) and blk["n"] >= cfg.d5_min_n
                )
                grid[f"{tag}:gap_{lo:g}_{hi:g}"] = blk
        q2 = _cluster_z_block(in_w, cfg.diagnose_p_threshold)
        q2["primary"] = True
        base_arm[f"b{b_main:g}"] = {
            "grid": grid,
            "in_window": {
                "base": _rec_stats(in_w, start, seg_days, k),
                "actuarial": _actuarial_block(in_w, _ACTUARIAL_REASONS_R4),
                "tp_actuarial": _tp_actuarial_block(in_w),
            },
            "forward": {"base": _rec_stats(fwd, start, seg_days, k)},
            "q2": q2,
        }

    # 消融(診斷,不入判定;聚合 = 主 5 變體同陣容合併 in-window)
    def _ablation_run(
        run_cfg: FadeBacktestConfig, phi: float | None, disable_struct: bool
    ) -> dict[str, object]:
        merged: list[_TradeRec] = []
        for kind, _variant, param, uni, _bk in specs:
            tr, _ = _simulate_r3_trades(
                uni,
                kind,
                param,
                b_main,
                run_cfg,
                cfg.slippage_ticks,
                watchlist_ids,
                inner_flip_phi=phi,
                disable_struct=disable_struct,
            )
            merged.extend(tr)
        in_w, _fwd = _split_fw(merged, cfg.forward_start)
        return _rec_stats(in_w, start, seg_days, k)

    ablation: dict[str, object] = {
        "tp_off": _ablation_run(cfg_legacy, phi_main, False),
        "stop_struct_only": _ablation_run(cfg, None, False),
    }
    if not hl_demoted:
        ablation["flush_only"] = _ablation_run(
            dataclasses.replace(cfg, tp_hl_k=None, tp_hl_min_profit=None), phi_main, False
        )
        ablation["hl_only"] = _ablation_run(
            dataclasses.replace(
                cfg,
                tp_flush_z=None,
                tp_flush_lookback=None,
                tp_flush_recovery=None,
                tp_flush_min_profit=None,
            ),
            phi_main,
            False,
        )
    elif cfg.tp_flush_z is not None:
        ablation["flush_only"] = _ablation_run(cfg, phi_main, False)
    if not inner_demoted:
        ablation["stop_inner_only"] = _ablation_run(cfg, phi_main, True)

    logger.info(
        "evaluate_round4 main=%d low=%d cellb=%d cells=%d base_arm=%s ablation=%s",
        len(main_uc),
        len(low_uc),
        len(cellb_uc),
        len(cells),
        sorted(base_arm),
        sorted(ablation),
    )
    return {
        "round4": True,
        "n_uc_main": len(main_uc),
        "n_uc_low": len(low_uc),
        "n_uc_cellb": len(cellb_uc),
        "segments": k,
        "forward_start": cfg.forward_start,
        "b_main": b_main,
        "phi_main": phi_main,
        "cells": cells,
        "sensitivity": sensitivity,
        "base_arm": base_arm,
        "ablation": ablation,
        "baselines": baselines,
        "fallbacks": {"inner_flip_demoted": inner_demoted, "tp_hl_demoted": hl_demoted},
    }


def _fwd_note(stats: dict[str, object]) -> str:
    n = stats.get("n", 0)
    return "forward 樣本 0,僅候選" if n == 0 else f"n={n}, EV={_fmt(stats.get('mean'))}"


def _write_round3_report(
    result: dict[str, object], cfg: FadeBacktestConfig, report_date: str, path: Path
) -> None:
    """round 3 報告:b 變體表 + Q2(候選)+ 底倉格 + 精算表 + forward 段(SC-2/4/7)。"""
    _f = _fmt
    lines: list[str] = []
    lines.append(f"# UC 池劇本格子評估 round 3(pre-registered;{report_date})")
    lines.append("")
    lines.append(
        f"- 宇宙:main n={result.get('n_uc_main')} / 低開 n={result.get('n_uc_low')}"
        f" / cell_b n={result.get('n_uc_cellb')};停損 = 結構高×(1+b) ∧ 硬線"
        f"(guard {_f(cfg.guard_limit_dist, '.1%')});災難 = 回落式"
        f"(D {_f(cfg.disaster_arm_x, '.1%')} / r {_f(cfg.disaster_retrace_r, '.1%')});"
        f"b 候選 = {list(cfg.struct_stop_buffers)}。"
    )
    lines.append(
        f"- 判定段 = in-window(< {result.get('forward_start')},候選;b/D/r 參數同源,"
        "循環風險註記);forward 段僅複核,門檻 = ≥20 交易日(SC-2)。"
    )
    lines.append("- D5 壓測組合 = stress_slippage + guard fill = bar.high 疊加;等日曆 4 段。")
    lines.append("")

    lines.append("## 變體表(in-window)")
    lines.append("")
    lines.append(
        "| cell | variant | b | n | 淨EV | p_win | 壓測EV | 壓測n | 段+ | vs基準線 | 封頂b_capped | D5 |"
    )
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    cells = result.get("cells")
    assert isinstance(cells, dict)
    for key in sorted(cells):
        c = cells[key]
        if not isinstance(c, dict):
            continue
        in_w = c.get("in_window", {})
        assert isinstance(in_w, dict)
        base = in_w.get("base", {})
        stress = in_w.get("stress", {})
        d5 = c.get("d5", {})
        assert isinstance(base, dict) and isinstance(stress, dict) and isinstance(d5, dict)
        lines.append(
            f"| {c.get('cell')} | {c.get('variant')} | {c.get('b')} | {base.get('n', 0)}"
            f" | {_f(base.get('mean'))} | {_f(base.get('p_win'), '.2f')}"
            f" | {_f(stress.get('mean'))} | {stress.get('n', 0)}"
            f" | {base.get('positive_segments', 0)}/{result.get('segments')}"
            f" | {_f(c.get('vs_baseline_mean'))} | {in_w.get('b_capped', 0)}"
            f" | {'PASS' if d5.get('passed') else 'FAIL'} |"
        )
    lines.append("")

    lines.append("## forward 段(≥ forward_start;複核輸出)")
    lines.append("")
    for key in sorted(cells):
        c = cells[key]
        if isinstance(c, dict):
            fwd = c.get("forward", {})
            assert isinstance(fwd, dict)
            base = fwd.get("base", {})
            assert isinstance(base, dict)
            lines.append(f"- {key}:{_fwd_note(base)}")
    lines.append("")

    base_arm = result.get("base_arm")
    if isinstance(base_arm, dict) and base_arm:
        lines.append("## 底倉臂 + Q2(吃法可行;in-window 候選判定)")
        lines.append("")
        for bkey in sorted(base_arm):
            arm = base_arm[bkey]
            if not isinstance(arm, dict):
                continue
            q2 = arm.get("q2", {})
            assert isinstance(q2, dict)
            tag = "主變體(判定用)" if q2.get("primary") else "敏感度列"
            verdict = "候選 PASS" if q2.get("pass") else "候選 FAIL"
            lines.append(
                f"### {bkey}({tag})— Q2:{verdict}(in-window,參數同源)"
            )
            lines.append("")
            lines.append(
                f"- tiger 合併:n={q2.get('n')} 淨EV={_f(q2.get('mean'))}"
                f" SE={_f(q2.get('se'))} z={_f(q2.get('z'), '.2f')} p={_f(q2.get('p'))}"
            )
            fwd = arm.get("forward", {})
            assert isinstance(fwd, dict)
            fwd_base = fwd.get("base", {})
            assert isinstance(fwd_base, dict)
            lines.append(f"- forward:{_fwd_note(fwd_base)}")
            lines.append("")
            lines.append("| 格(分點數:gap 桶) | n | 淨EV | z | p | 開放 |")
            lines.append("|---|---:|---:|---:|---:|---|")
            grid = arm.get("grid", {})
            assert isinstance(grid, dict)
            for gkey in sorted(grid):
                g = grid[gkey]
                if not isinstance(g, dict):
                    continue
                lines.append(
                    f"| {gkey} | {g.get('n')} | {_f(g.get('mean'))}"
                    f" | {_f(g.get('z'), '.2f')} | {_f(g.get('p'))}"
                    f" | {'是' if g.get('open') else '否'} |"
                )
            lines.append("")

    lines.append("## 保險精算表(SC-4;in-window)")
    lines.append("")
    lines.append("| 變體 | 機制 | 觸發 n | 觸發率 | 均pnl | 砍對(收盤鎖死) | 砍錯 |")
    lines.append("|---|---|---:|---:|---:|---:|---:|")

    def _act_rows(label: str, act: object) -> None:
        if not isinstance(act, dict):
            return
        for reason in _ACTUARIAL_REASONS:
            a = act.get(reason)
            if not isinstance(a, dict):
                continue
            lines.append(
                f"| {label} | {reason} | {a.get('n')} | {_f(a.get('rate'), '.1%')}"
                f" | {_f(a.get('avg_pnl'))} | {_f(a.get('cut_right'), '.1%')}"
                f" | {_f(a.get('cut_wrong'), '.1%')} |"
            )

    for key in sorted(cells):
        c = cells[key]
        if isinstance(c, dict):
            in_w = c.get("in_window", {})
            assert isinstance(in_w, dict)
            _act_rows(key, in_w.get("actuarial"))
    if isinstance(base_arm, dict):
        for bkey in sorted(base_arm):
            arm = base_arm[bkey]
            if isinstance(arm, dict):
                in_w = arm.get("in_window", {})
                assert isinstance(in_w, dict)
                _act_rows(f"base_arm:{bkey}", in_w.get("actuarial"))
    lines.append("")

    lines.append("## 基準線(同宇宙同風控:ratchet b + 災難 + 硬線)")
    lines.append("")
    lines.append("| universe:b | in-window n | 淨EV | forward |")
    lines.append("|---|---:|---:|---|")
    baselines = result.get("baselines")
    if isinstance(baselines, dict):
        for name in sorted(baselines):
            v = baselines[name]
            if not isinstance(v, dict):
                continue
            in_w = v.get("in_window", {})
            fwd = v.get("forward", {})
            assert isinstance(in_w, dict) and isinstance(fwd, dict)
            lines.append(
                f"| {name} | {in_w.get('n', 0)} | {_f(in_w.get('mean'))} | {_fwd_note(fwd)} |"
            )
    lines.append("")
    lines.append(
        "限制:D=0.060 為 0.5% 步進中點 banker's tie-break(需補 D=0.065 敏感度);"
        "D 以開盤錨校準、套用為進場錨(entry×(1+D)),盤中進場臂武裝偏早(保守向)。"
    )

    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _write_round4_report(
    result: dict[str, object], cfg: FadeBacktestConfig, report_date: str, path: Path
) -> None:
    """round 4 報告:主判定變體表(含賺賠比)+ Q2′ + 消融 + 敏感度 + 雙精算表."""
    _f = _fmt
    lines: list[str] = []
    lines.append(f"# UC 池劇本格子評估 round 4(pre-registered;{report_date})")
    lines.append("")
    lines.append(
        f"- 宇宙:main n={result.get('n_uc_main')} / 低開 n={result.get('n_uc_low')}"
        f" / cell_b n={result.get('n_uc_cellb')};停損樹 = inner_flip"
        f"(φ {_f(result.get('phi_main'))},m≥{cfg.inner_flip_min_bars})→ 結構高×(1+b)"
        f"(b {_f(result.get('b_main'))})∧ 硬線(guard {_f(cfg.guard_limit_dist, '.1%')})"
        f" → 災難回落(D {_f(cfg.disaster_arm_x, '.1%')} / r {_f(cfg.disaster_retrace_r, '.1%')})。"
    )
    lines.append(
        f"- 停利樹 = 出量殺(z {_f(cfg.tp_flush_z)} / lookback {cfg.tp_flush_lookback}"
        f" / recovery {_f(cfg.tp_flush_recovery)} / min_profit {_f(cfg.tp_flush_min_profit)})"
        f" + 墊高竭盡(k {cfg.tp_hl_k} / min_profit {_f(cfg.tp_hl_min_profit)}),"
        "先到先收;都沒觸發抱到收盤。"
    )
    lines.append(
        f"- 判定段 = in-window(< {result.get('forward_start')},候選);"
        "forward 段僅複核(≥20 交易日)。量尺 = 第 7 分鐘 + round 3 舊出場。"
    )
    fallbacks = result.get("fallbacks")
    if isinstance(fallbacks, dict):
        if fallbacks.get("inner_flip_demoted"):
            lines.append("- **inner_flip: DEMOTED**(§0(d) gate FAIL → φ=None 跑,prereg fallback #1)")
        if fallbacks.get("tp_hl_demoted"):
            lines.append("- **tp_hl: DEMOTED**(§0(c) 讓肉判準 → 樹只剩 flush,prereg fallback #2)")
    lines.append("")

    lines.append("## 主判定變體表(in-window)")
    lines.append("")
    lines.append(
        "| cell | variant | b | φ | n | 淨EV | p_win | avg win | avg loss | PF"
        " | 壓測EV | 壓測n | 段+ | vs量尺 | D5 |"
    )
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|")

    def _variant_row(key: str, c: dict[str, object]) -> str:
        in_w = c.get("in_window", {})
        assert isinstance(in_w, dict)
        base = in_w.get("base", {})
        stress = in_w.get("stress", {})
        d5 = c.get("d5", {})
        assert isinstance(base, dict) and isinstance(stress, dict) and isinstance(d5, dict)
        return (
            f"| {c.get('cell')} | {c.get('variant')} | {c.get('b')} | {_f(c.get('phi'))}"
            f" | {base.get('n', 0)} | {_f(base.get('mean'))} | {_f(base.get('p_win'), '.2f')}"
            f" | {_f(base.get('avg_win'))} | {_f(base.get('avg_loss'))}"
            f" | {_f(base.get('profit_factor'), '.2f')}"
            f" | {_f(stress.get('mean'))} | {stress.get('n', 0)}"
            f" | {base.get('positive_segments', 0)}/{result.get('segments')}"
            f" | {_f(c.get('vs_baseline_mean'))}"
            f" | {'PASS' if d5.get('passed') else 'FAIL'} |"
        )

    cells = result.get("cells")
    assert isinstance(cells, dict)
    for key in sorted(cells):
        c = cells[key]
        if isinstance(c, dict):
            lines.append(_variant_row(key, c))
    lines.append("")

    lines.append("## forward 段(≥ forward_start;複核輸出)")
    lines.append("")
    for key in sorted(cells):
        c = cells[key]
        if isinstance(c, dict):
            fwd = c.get("forward", {})
            assert isinstance(fwd, dict)
            fbase = fwd.get("base", {})
            assert isinstance(fbase, dict)
            lines.append(f"- {key}:{_fwd_note(fbase)}")
    lines.append("")

    base_arm = result.get("base_arm")
    if isinstance(base_arm, dict) and base_arm:
        lines.append("## 底倉臂 + Q2′(吃法可行;交易集合 = base_arm 套新出場,in-window)")
        lines.append("")
        for bkey in sorted(base_arm):
            arm = base_arm[bkey]
            if not isinstance(arm, dict):
                continue
            q2 = arm.get("q2", {})
            assert isinstance(q2, dict)
            verdict = "候選 PASS" if q2.get("pass") else "候選 FAIL"
            lines.append(f"### {bkey}(主變體(判定用))— Q2′:{verdict}(in-window)")
            lines.append("")
            lines.append(
                f"- tiger 合併:n={q2.get('n')} 淨EV={_f(q2.get('mean'))}"
                f" SE={_f(q2.get('se'))} z={_f(q2.get('z'), '.2f')} p={_f(q2.get('p'))}"
            )
            fwd = arm.get("forward", {})
            assert isinstance(fwd, dict)
            fwd_base = fwd.get("base", {})
            assert isinstance(fwd_base, dict)
            lines.append(f"- forward:{_fwd_note(fwd_base)}")
            lines.append("")
            lines.append("| 格(分點數:gap 桶) | n | 淨EV | z | p | 開放 |")
            lines.append("|---|---:|---:|---:|---:|---|")
            grid = arm.get("grid", {})
            assert isinstance(grid, dict)
            for gkey in sorted(grid):
                g = grid[gkey]
                if not isinstance(g, dict):
                    continue
                lines.append(
                    f"| {gkey} | {g.get('n')} | {_f(g.get('mean'))}"
                    f" | {_f(g.get('z'), '.2f')} | {_f(g.get('p'))}"
                    f" | {'是' if g.get('open') else '否'} |"
                )
            lines.append("")

    lines.append("## 停損精算表(in-window)")
    lines.append("")
    lines.append("| 變體 | 機制 | 觸發 n | 觸發率 | 均pnl | 砍對(收盤鎖死) | 砍錯 |")
    lines.append("|---|---|---:|---:|---:|---:|---:|")

    def _act_rows(label: str, act: object) -> None:
        if not isinstance(act, dict):
            return
        for reason in _ACTUARIAL_REASONS_R4:
            a = act.get(reason)
            if not isinstance(a, dict):
                continue
            lines.append(
                f"| {label} | {reason} | {a.get('n')} | {_f(a.get('rate'), '.1%')}"
                f" | {_f(a.get('avg_pnl'))} | {_f(a.get('cut_right'), '.1%')}"
                f" | {_f(a.get('cut_wrong'), '.1%')} |"
            )

    def _tp_rows(label: str, act: object) -> None:
        if not isinstance(act, dict):
            return
        for reason in ("tp_flush", "tp_hl"):
            a = act.get(reason)
            if not isinstance(a, dict):
                continue
            tp_lines.append(
                f"| {label} | {reason} | {a.get('n')} | {_f(a.get('rate'), '.1%')}"
                f" | {_f(a.get('avg_pnl'))} | {_f(a.get('saved_mean'))}"
                f" | {_f(a.get('saved_p25'))}/{_f(a.get('saved_p50'))}/{_f(a.get('saved_p75'))}"
                f" | {a.get('saved_excluded_lock')} |"
            )

    tp_lines: list[str] = []
    for key in sorted(cells):
        c = cells[key]
        if isinstance(c, dict):
            in_w = c.get("in_window", {})
            assert isinstance(in_w, dict)
            _act_rows(key, in_w.get("actuarial"))
            _tp_rows(key, in_w.get("tp_actuarial"))
    if isinstance(base_arm, dict):
        for bkey in sorted(base_arm):
            arm = base_arm[bkey]
            if isinstance(arm, dict):
                in_w = arm.get("in_window", {})
                assert isinstance(in_w, dict)
                _act_rows(f"base_arm:{bkey}", in_w.get("actuarial"))
                _tp_rows(f"base_arm:{bkey}", in_w.get("tp_actuarial"))
    lines.append("")

    lines.append("## 停利精算表(in-window;saved = pnl − 抱到收盤,鎖死日排除)")
    lines.append("")
    lines.append("| 變體 | 機制 | n | 率 | 均pnl | saved均 | saved p25/p50/p75 | 鎖死排除 |")
    lines.append("|---|---|---:|---:|---:|---:|---|---:|")
    lines.extend(tp_lines)
    lines.append("")

    ablation = result.get("ablation")
    if isinstance(ablation, dict) and ablation:
        lines.append("## 消融對照(診斷,不入判定;主 5 變體同陣容合併,in-window)")
        lines.append("")
        lines.append("| 組 | n | 淨EV | p_win | PF |")
        lines.append("|---|---:|---:|---:|---:|")
        for name in sorted(ablation):
            a = ablation[name]
            if not isinstance(a, dict):
                continue
            lines.append(
                f"| {name} | {a.get('n', 0)} | {_f(a.get('mean'))}"
                f" | {_f(a.get('p_win'), '.2f')} | {_f(a.get('profit_factor'), '.2f')} |"
            )
        lines.append("")

    sensitivity = result.get("sensitivity")
    if isinstance(sensitivity, dict) and sensitivity:
        lines.append("## 敏感度列(φ 次值 / b 次值;不入判定)")
        lines.append("")
        lines.append(
            "| key | n | 淨EV | p_win | 壓測EV | 段+ | vs量尺 | D5(參考) |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
        for key in sorted(sensitivity):
            c = sensitivity[key]
            if not isinstance(c, dict):
                continue
            in_w = c.get("in_window", {})
            assert isinstance(in_w, dict)
            base = in_w.get("base", {})
            stress = in_w.get("stress", {})
            d5 = c.get("d5", {})
            assert isinstance(base, dict) and isinstance(stress, dict) and isinstance(d5, dict)
            lines.append(
                f"| {key} | {base.get('n', 0)} | {_f(base.get('mean'))}"
                f" | {_f(base.get('p_win'), '.2f')} | {_f(stress.get('mean'))}"
                f" | {base.get('positive_segments', 0)}/{result.get('segments')}"
                f" | {_f(c.get('vs_baseline_mean'))}"
                f" | {'PASS' if d5.get('passed') else 'FAIL'} |"
            )
        lines.append("")

    lines.append("## 量尺基準線(第 7 分鐘 + round 3 舊出場)")
    lines.append("")
    lines.append("| universe | in-window n | 淨EV | forward |")
    lines.append("|---|---:|---:|---|")
    baselines = result.get("baselines")
    if isinstance(baselines, dict):
        for name in sorted(baselines):
            v = baselines[name]
            if not isinstance(v, dict):
                continue
            in_w = v.get("in_window", {})
            fwd = v.get("forward", {})
            assert isinstance(in_w, dict) and isinstance(fwd, dict)
            lines.append(
                f"| {name} | {in_w.get('n', 0)} | {_f(in_w.get('mean'))} | {_fwd_note(fwd)} |"
            )
    lines.append("")

    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def write_cells_report(
    result: dict[str, object], cfg: FadeBacktestConfig, report_date: str, path: Path
) -> None:
    if result.get("round4") is True:
        _write_round4_report(result, cfg, report_date, path)
        return
    if result.get("round3") is True:
        _write_round3_report(result, cfg, report_date, path)
        return
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


def build_universes(
    data_dir: Path, cfg: FadeBacktestConfig
) -> tuple[
    dict[str, list[tuple[FadeSample, list[Bar1K]]]],
    dict[str, dict[str, int]],
]:
    """main / low(/ cellb)宇宙構建 + 1K 掛載(run_cells 與 fade_anatomy 共用)。

    cellb 僅在 round 3 形狀(struct_stop_buffers + cell_b_gap_max)下產生,
    round 3(§9.3/R7):cell_b 獨立宇宙(貼板線例外,gap 上限 = cell_b_gap_max)。
    """
    from copycat.backtest.fade_pipeline import build_fade_universe  # 延遲:避免與 pipeline 互import

    from copycat.data.store import read_bars

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

    universes = {"main": _with_bars(main_samples), "low": _with_bars(low_samples)}
    counts = {"main": main_counts, "low": low_counts}
    if cfg.struct_stop_buffers and cfg.cell_b_gap_max is not None:
        cellb_cfg = dataclasses.replace(cfg, fade_gap_max=cfg.cell_b_gap_max)
        cellb_samples, cellb_counts = build_fade_universe(data_dir, events, cellb_cfg)
        universes["cellb"] = _with_bars(cellb_samples)
        counts["cellb"] = cellb_counts
    return universes, counts


def run_cells(
    data_dir: Path,
    out_dir: Path,
    cfg: FadeBacktestConfig,
    report_date: str,
    watchlist_path: Path,
    report_dir: Path | None = None,
) -> Path:
    """CLI 協調:主池 + 低開池 universe → bars → 評估 → JSON + 報告."""
    from copycat.watchlist import load_watchlist

    watchlist = load_watchlist(watchlist_path)
    universes, counts = build_universes(data_dir, cfg)
    result = evaluate_cells_from_universe(
        universes["main"],
        universes["low"],
        cfg,
        watchlist.broker_ids,
        cellb_universe=universes.get("cellb"),
    )
    result["universe_counts_main"] = counts["main"]
    result["universe_counts_low"] = counts["low"]
    if "cellb" in counts:
        result["universe_counts_cellb"] = counts["cellb"]

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
