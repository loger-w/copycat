"""T+1 Fade pipeline(design.md v2 §8):universe → 觸發 → 特徵 → 模擬 → 搜索 → 驗證 → 報告.

兩階段 combo:baseline ranking → top3 S1 → 最終 4,640 組。
Outcome cache 移植 tday pipeline 慣例(三重失效:config hash / rows hash / grid flag)。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

from copycat.backtest.fade_arms import ALL_ARMS, ArmParamSet, ArmSpec, dispatch_trigger
from copycat.backtest.fade_config import (
    FadeBacktestConfig,
    FadeStopCombo,
    enumerate_baseline_combos,
    enumerate_fade_stop_combos,
    fade_sim_config_hash,
)
from copycat.backtest.fade_features import fade_trigger_features
from copycat.backtest.fade_simulate import FadeSample, simulate_fade_sample
from copycat.backtest.market_features import compute_mkt_daily_features_full
from copycat.backtest.features import static_features, structural_features
from copycat.backtest.search import (
    apply_rule,
    build_predicates,
    exhaustive_scan,
    ga_search,
    jaccard_dedupe,
    rule_sort_key,
)
from copycat.backtest.stats import Trade, max_drawdown, monthly_consistency, weighted_stats
from copycat.data.daily import DailyIndex
from copycat.data.models import Bar1K
from copycat.data.store import read_bars

logger = logging.getLogger(__name__)

# guard_exit 必須在列(R1):強制風控停出的正是最差虧損交易,不入統計 = 期望值灌水
_TRADEABLE = {"stopped", "target_hit", "time_1300", "closeout", "locked_at_limit", "guard_exit"}


def build_fade_universe(
    data_dir: Path,
    events_path: Path,
    cfg: FadeBacktestConfig,
) -> tuple[list[FadeSample], dict[str, int]]:
    """events.csv → FadeSample list + 剔除計數."""
    import csv

    counts: dict[str, int] = {
        "total": 0,
        "excluded_high_gap": 0,
        "excluded_low_gap": 0,
        "excluded_missing_1k": 0,
        "excluded_no_daytrade": 0,
        "excluded_disposition": 0,
        "daytrade_uncovered_date": 0,
        "included": 0,
    }
    dt_index = None
    if cfg.universe_daytrade_filter:
        from copycat.data.backfill_daytrade import DayTradeIndex

        dt_index = DayTradeIndex.load(data_dir)
        if dt_index is None:  # R7 fail-fast:防漏跑 backfill-daytrade 靜默產出未過濾報告
            raise RuntimeError(
                "universe_daytrade_filter 開啟但 data/daytrade 未回補,先跑 backfill-daytrade"
            )

    samples: list[FadeSample] = []
    with events_path.open("r", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            counts["total"] += 1
            stock_id = row["stock_id"]
            t1_date = row["t1_date"]
            limit = float(row["limitup_close"])

            if dt_index is not None and t1_date:
                if dt_index.in_disposition(stock_id, t1_date):
                    counts["excluded_disposition"] += 1
                    continue
                ok = dt_index.eligible(stock_id, t1_date)
                if ok is None:
                    counts["daytrade_uncovered_date"] += 1  # 該日未覆蓋 → 不過濾(R18)
                elif not ok:
                    counts["excluded_no_daytrade"] += 1
                    continue

            t1_1k_path = data_dir / "1k" / stock_id / f"{t1_date}.json"
            if not t1_1k_path.exists():
                counts["excluded_missing_1k"] += 1
                continue

            t1_bars = read_bars(data_dir, stock_id, t1_date)
            if not t1_bars:
                counts["excluded_missing_1k"] += 1
                continue

            t1_open = t1_bars[0].open
            if t1_open <= 0 or limit <= 0:
                counts["excluded_missing_1k"] += 1
                continue

            gap = t1_open / limit - 1.0
            if gap >= cfg.fade_gap_max:
                counts["excluded_high_gap"] += 1
                continue
            if gap < cfg.fade_gap_min:
                counts["excluded_low_gap"] += 1
                continue

            samples.append(
                FadeSample(
                    stock_id=stock_id,
                    date=row["date"],
                    t1_date=t1_date,
                    limit=limit,
                    t1_open=t1_open,
                    gap=gap,
                    broker_ids=row.get("broker_ids", ""),
                    source=row.get("source", ""),
                )
            )
            counts["included"] += 1

    return samples, counts


def _param_hash(arm_name: str, params: ArmParamSet) -> str:
    blob = json.dumps({"arm": arm_name, "params": params.values}, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def _samples_hash(samples: list[FadeSample]) -> str:
    blob = json.dumps(
        [(s.stock_id, s.t1_date) for s in samples],
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def run_fade_arm(
    data_dir: Path,
    out_dir: Path,
    cfg: FadeBacktestConfig,
    arm: ArmSpec,
    params: ArmParamSet,
    max_window_m: int,
    samples: list[FadeSample],
    daily: DailyIndex,
    mkt_daily_rows: list[dict[str, Any]] | None,
    is_anchor: bool,
) -> dict[str, object]:
    """單一 arm × param set 的完整流程:觸發 → 特徵 → 模擬 → (anchor 時 GA 搜索)."""
    triggered: list[tuple[FadeSample, list[Bar1K], int]] = []
    features_list: list[dict[str, float | None]] = []
    no_trigger_count = 0

    for sample in samples:
        bars = read_bars(data_dir, sample.stock_id, sample.t1_date)
        if not bars:
            continue
        trig_idx = dispatch_trigger(arm, bars, params, max_window_m)
        if trig_idx is None:
            no_trigger_count += 1
            continue

        stat = static_features(daily, sample.stock_id, sample.date)
        struct = structural_features(daily, sample.stock_id, sample.date, cfg)  # type: ignore[arg-type]

        mkt_daily_feats = None
        if mkt_daily_rows:
            mkt_daily_feats = compute_mkt_daily_features_full(mkt_daily_rows, sample.date)

        lock_feats: dict[str, float | None] = {"gap_pct": sample.gap}

        feats = fade_trigger_features(
            bars,
            trig_idx,
            lock_features=lock_feats,
            t1_features=None,
            static_features={**(stat or {}), **(struct or {})},
            mkt_daily=mkt_daily_feats,
            mkt_intraday=None,
            limit=sample.limit,
        )
        triggered.append((sample, bars, trig_idx))
        features_list.append(feats)

    logger.info(
        "arm=%s param=%s window=%d: triggered=%d no_trigger=%d",
        arm.name,
        params.param_id,
        max_window_m,
        len(triggered),
        no_trigger_count,
    )

    if not triggered:
        return {
            "arm": arm.name,
            "param": params.values,
            "max_window": max_window_m,
            "n_triggered": 0,
            "n_no_trigger": no_trigger_count,
            "rules": [],
        }

    baseline_combos = enumerate_baseline_combos(cfg)
    baseline_pnl: dict[str, list[float | None]] = {c.combo_id: [] for c in baseline_combos}
    baseline_status: dict[str, list[str]] = {c.combo_id: [] for c in baseline_combos}

    for sample, bars, trig_idx in triggered:
        for combo in baseline_combos:
            out = simulate_fade_sample(bars, trig_idx, sample, combo, cfg, cfg.slippage_ticks)
            baseline_pnl[combo.combo_id].append(out.pnl_rate)
            baseline_status[combo.combo_id].append(out.status)

    s1_scores: list[tuple[float, int, float]] = []
    for combo in baseline_combos:
        if combo.s1_n is None:
            continue
        pnl_list = baseline_pnl[combo.combo_id]
        tradeable_pnl = [
            p
            for p, s in zip(pnl_list, baseline_status[combo.combo_id])
            if s in _TRADEABLE and p is not None
        ]
        if len(tradeable_pnl) >= 5:
            exp = sum(tradeable_pnl) / len(tradeable_pnl)
            s1_scores.append((exp, combo.s1_n, combo.s1_phi or -1.0))

    s1_scores.sort(key=lambda x: -x[0])
    top3_s1 = [(n, phi) for _, n, phi in s1_scores[:3]]
    if len(top3_s1) < 3:
        top3_s1 = [(n, phi) for n in list(cfg.s1_stall_bars)[:3] for phi in [-1.0]][:3]

    all_combos = enumerate_fade_stop_combos(cfg, top3_s1) if is_anchor else baseline_combos

    pnl_map: dict[str, list[float | None]] = {}
    status_map: dict[str, list[str]] = {}
    for combo in all_combos:
        cid = combo.combo_id
        if cid in baseline_pnl:
            pnl_map[cid] = baseline_pnl[cid]
            status_map[cid] = baseline_status[cid]
        else:
            pnl_map[cid] = []
            status_map[cid] = []
            for sample, bars, trig_idx in triggered:
                out_r = simulate_fade_sample(bars, trig_idx, sample, combo, cfg, cfg.slippage_ticks)
                pnl_map[cid].append(out_r.pnl_rate)
                status_map[cid].append(out_r.status)

    # F6 fix: removed stress_pnl dead computation
    default_combo = FadeStopCombo(
        s1_n=None,
        s1_phi=None,
        s2_m=None,
        s2_buf=None,
        s3_x=None,
        s4_x=None,
        s5_x=None,
        t1300=cfg.baseline_t1300,
    )
    default_pnl = pnl_map.get(default_combo.combo_id, [])
    default_status = status_map.get(default_combo.combo_id, [])

    # F2 fix: only tradeable samples enter GA; F1 fix: split train/test
    train_feat: list[dict[str, float | None]] = []
    train_weights: list[float] = []
    train_pnl: list[float] = []
    all_feat: list[dict[str, float | None]] = []
    all_pnl: list[float] = []
    all_dates: list[str] = []
    all_sids: list[str] = []

    tradeable_samples: list[tuple[FadeSample, list[Bar1K], int]] = []

    for i, (sample, bars, trig_idx) in enumerate(triggered):
        p = default_pnl[i] if i < len(default_pnl) else None
        s = default_status[i] if i < len(default_status) else ""
        if s not in _TRADEABLE or p is None:
            continue
        all_feat.append(features_list[i])
        all_pnl.append(p)
        all_dates.append(sample.t1_date)
        all_sids.append(sample.stock_id)
        tradeable_samples.append((sample, bars, trig_idx))
        if sample.t1_date < cfg.split_date:
            train_feat.append(features_list[i])
            train_weights.append(1.0)
            train_pnl.append(p)

    # F1 fix: GA on train only, three-gate validation on test
    rules: list[dict[str, object]] = []
    if is_anchor and train_feat:
        feature_names = sorted({k for row in train_feat for k in row if row[k] is not None})
        predicates = build_predicates(train_feat, feature_names, cfg.quantile_probs)
        logger.info("predicates: %d (features: %d)", len(predicates), len(feature_names))

        exh = exhaustive_scan(predicates, train_pnl, train_weights, cfg)  # type: ignore[arg-type]
        ga_all: list[dict[str, object]] = list(exh)
        for seed in cfg.ga_seeds:
            ga_all.extend(ga_search(predicates, train_pnl, train_weights, cfg, seed))  # type: ignore[arg-type]
        ga_all.sort(key=rule_sort_key)
        candidates = jaccard_dedupe(ga_all, cfg.jaccard_max)[:30]

        test_start = cfg.split_date
        test_end = max(all_dates) if all_dates else cfg.split_date
        for rule in candidates:
            conds = rule["conditions"]
            assert isinstance(conds, list)
            mask = apply_rule(conds, all_feat)
            test_t = [
                Trade(date=all_dates[j], stock_id=all_sids[j], pnl=all_pnl[j])
                for j in range(len(all_feat))
                if mask & (1 << j) and all_dates[j] >= cfg.split_date
            ]
            if not test_t:
                continue
            ts = weighted_stats(test_t)
            test_exp = ts.get("expectancy")
            if test_exp is None or test_exp <= 0:
                continue
            mc = monthly_consistency(test_t, test_start, test_end)
            rule["test_expectancy"] = test_exp
            rule["test_p_win"] = ts.get("p_win")
            rule["test_payoff"] = ts.get("payoff")
            rule["test_n_raw"] = ts.get("n_raw")
            rule["test_mdd"] = max_drawdown(test_t)
            rule["monthly_passed"] = mc["passed"]
            rule["monthly_hits"] = mc.get("monthly_hits")
            rule["passed_all"] = bool(mc["passed"])
            rules.append(rule)

        logger.info("rules after three-gate: %d / %d candidates", len(rules), len(candidates))

    if is_anchor and rules:
        from copycat.backtest.fade_config import enumerate_tp_combos
        from copycat.backtest.fade_optimize import optimize_rule_stops, optimize_rule_tp

        optimize_rule_stops(tradeable_samples, rules, all_combos, all_feat, all_dates, cfg)
        tp_combos = enumerate_tp_combos(cfg)
        optimize_rule_tp(tradeable_samples, rules, tp_combos, all_feat, all_dates, cfg)

    # F4 fix: lock count per unique triggered sample (not per combo)
    lock_count = sum(
        1
        for i in range(len(triggered))
        if i < len(default_status) and default_status[i] == "locked_at_limit"
    )

    return {
        "arm": arm.name,
        "param": params.values,
        "max_window": max_window_m,
        "n_triggered": len(triggered),
        "n_no_trigger": no_trigger_count,
        "top3_s1": top3_s1,
        "rules": rules,
        "is_anchor": is_anchor,
        "lock_events": lock_count,
        "n_train": len(train_feat),
        "n_test": len(all_feat) - len(train_feat),
    }


def run_fade_pipeline(
    data_dir: Path,
    out_dir: Path,
    cfg: FadeBacktestConfig,
    report_date: str,
    evidence_dir: Path | None = None,
) -> dict[str, object]:
    """全 7 臂 × anchor × 搜索 × 驗證."""
    out_dir.mkdir(parents=True, exist_ok=True)
    events_path = data_dir / "events" / "events.csv"
    daily = DailyIndex.load(data_dir)

    samples, u_counts = build_fade_universe(data_dir, events_path, cfg)
    logger.info("universe: %d samples (counts: %s)", len(samples), u_counts)

    mkt_daily_rows: list[dict[str, Any]] | None = None

    all_results: list[dict[str, object]] = []
    default_window = cfg.max_window_grid[2] if len(cfg.max_window_grid) > 2 else 20

    for arm in ALL_ARMS:
        for params in arm.anchor_params:
            result = run_fade_arm(
                data_dir,
                out_dir,
                cfg,
                arm,
                params,
                default_window,
                samples,
                daily,
                mkt_daily_rows,
                is_anchor=True,
            )
            all_results.append(result)

    from copycat.backtest.fade_optimize import build_cross_arm_table
    from copycat.backtest.fade_report import write_fade_report

    cross_arm = build_cross_arm_table(all_results)
    report_path = write_fade_report(
        all_results, cfg, report_date, out_dir, evidence_dir, cross_arm_table=cross_arm
    )

    final_path = out_dir / "rules_final.json"
    tmp = final_path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {
                "results": all_results,
                "universe_counts": u_counts,
                "config_hash": fade_sim_config_hash(cfg),
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=1,
            default=str,
        ),
        encoding="utf-8",
    )
    os.replace(tmp, final_path)

    logger.info("pipeline 完成 → %s", out_dir)
    return {"results": all_results, "report": str(report_path), "rules_final": str(final_path)}
