"""T+1 Fade pipeline(design.md v2 §8):universe → 觸發 → 特徵 → 模擬 → 搜索 → 驗證 → 報告.

兩階段 combo:baseline ranking → top3 S1 → 最終 4,640 組。
Outcome cache 移植 tday pipeline 慣例(三重失效:config hash / rows hash / grid flag)。
"""

from __future__ import annotations

import json
import logging
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
from copycat.backtest.fade_simulate import (
    TRADEABLE_STATUSES as _TRADEABLE,
)
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
from copycat.fileio import atomic_write_text

logger = logging.getLogger(__name__)

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


def _add_months(date_str: str, months: int) -> str:
    y, m, d = (int(x) for x in date_str.split("-"))
    m += months
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}-{d:02d}"


def _trade_stats(trades: list[Trade]) -> dict[str, float | int | None]:
    if not trades:
        return {"expectancy": None, "p_win": None, "payoff": None, "n": 0, "mdd": 0.0}
    s = weighted_stats(trades)
    return {
        "expectancy": s.get("expectancy"),
        "p_win": s.get("p_win"),
        "payoff": s.get("payoff"),
        "n": s.get("n_raw"),
        "mdd": max_drawdown(trades),
    }


def _sim_trades(
    indices: list[int],
    tradeable_samples: list[tuple[FadeSample, list[Bar1K], int]],
    combo: FadeStopCombo,
    tp: object,
    cfg: FadeBacktestConfig,
    slippage: int,
) -> tuple[list[Trade], list[str], int]:
    """模擬 indices → (trades, 對應 source list, lock_count)。tp=None 走無 TP 路徑."""
    from copycat.backtest.fade_simulate import simulate_fade_with_tp

    trades: list[Trade] = []
    sources: list[str] = []
    lock = 0
    for i in indices:
        sample, bars, trig_idx = tradeable_samples[i]
        out = simulate_fade_with_tp(bars, trig_idx, sample, combo, tp, cfg, slippage)  # type: ignore[arg-type]
        if out.status in _TRADEABLE and out.pnl_rate is not None:
            trades.append(Trade(date=sample.t1_date, stock_id=sample.stock_id, pnl=out.pnl_rate))
            sources.append(sample.source)
        if out.status == "locked_at_limit":
            lock += 1
    return trades, sources, lock


def _run_walk_forward(
    tradeable_samples: list[tuple[FadeSample, list[Bar1K], int]],
    all_feat: list[dict[str, float | None]],
    all_pnl: list[float],
    all_dates: list[str],
    cfg: FadeBacktestConfig,
) -> dict[str, object]:
    """walk-forward:fold 內 GA(core)→ val 三道選 top-1 → t1300/TP 對決(train)→
    fold-test [start, end) 評估;OOS = 各 fold top-1 串接(R13)。test 不進任何選擇。"""
    import dataclasses

    from copycat.backtest.fade_config import enumerate_tp_combos
    from copycat.backtest.fade_optimize import _fold_test_indices, optimize_tp_for_indices

    tp_combos = enumerate_tp_combos(cfg)
    folds_out: list[dict[str, object]] = []
    oos_trades: list[Trade] = []
    oos_sources: list[str] = []
    stress_trades: list[Trade] = []
    sens_trades: dict[float, list[Trade]] = {d: [] for d in cfg.guard_dist_grid}
    total_test_idx = 0
    total_lock = 0
    fold_positive = 0
    val_exps: list[float] = []

    for test_start in cfg.wf_test_starts:
        test_end = _add_months(test_start, cfg.wf_test_months)
        train_ids = sorted(
            (i for i in range(len(all_dates)) if all_dates[i] < test_start),
            key=lambda i: all_dates[i],
        )
        fold_rec: dict[str, object] = {"test_start": test_start, "test_end": test_end}
        if len(train_ids) < cfg.support_raw_min * 2:
            fold_rec["skipped"] = "train 樣本不足"
            folds_out.append(fold_rec)
            continue

        val_n = max(1, int(len(train_ids) * cfg.wf_val_frac))
        val_cut = all_dates[train_ids[-val_n]]  # 按日期切,同日不跨界
        core_ids = [i for i in train_ids if all_dates[i] < val_cut]
        val_ids = [i for i in train_ids if all_dates[i] >= val_cut]
        if not core_ids or not val_ids:
            fold_rec["skipped"] = "core/val 切分退化"
            folds_out.append(fold_rec)
            continue

        core_feat = [all_feat[i] for i in core_ids]
        core_pnl = [all_pnl[i] for i in core_ids]
        core_w = [1.0] * len(core_ids)
        feature_names = sorted({k2 for row in core_feat for k2 in row if row[k2] is not None})
        predicates = build_predicates(core_feat, feature_names, cfg.quantile_probs)
        ga_all: list[dict[str, object]] = list(exhaustive_scan(predicates, core_pnl, core_w, cfg))  # type: ignore[arg-type]
        for seed in cfg.ga_seeds:
            ga_all.extend(ga_search(predicates, core_pnl, core_w, cfg, seed))  # type: ignore[arg-type]
        ga_all.sort(key=rule_sort_key)
        candidates = jaccard_dedupe(ga_all, cfg.jaccard_max)[:30]

        # val 三道(val_exp>0 + 月度)→ top-1;val 用 default-combo pnl(與 GA fitness 同基準)
        best_rule: dict[str, object] | None = None
        best_val_exp = -1e18
        val_start = min(all_dates[i] for i in val_ids)
        val_end = max(all_dates[i] for i in val_ids)
        for rule in candidates:
            conds = rule["conditions"]
            assert isinstance(conds, list)
            mask = apply_rule(conds, all_feat)
            val_t = [
                Trade(date=all_dates[i], stock_id="", pnl=all_pnl[i])
                for i in val_ids
                if mask & (1 << i)
            ]
            if not val_t:
                continue
            v = weighted_stats(val_t).get("expectancy")
            if v is None or v <= 0:
                continue
            if not bool(monthly_consistency(val_t, val_start, val_end)["passed"]):
                continue
            if v > best_val_exp:
                best_val_exp = float(v)
                best_rule = rule

        if best_rule is None:
            fold_rec["skipped"] = "無規則過 val 三道"
            folds_out.append(fold_rec)
            continue

        conds = best_rule["conditions"]
        assert isinstance(conds, list)
        mask = apply_rule(conds, all_feat)
        matched_train = [i for i in train_ids if mask & (1 << i)]

        # t1300 對決(train,tp=None)→ TP 對決(train)
        chosen_combo: FadeStopCombo | None = None
        chosen_exp = -1e18
        for t13 in (True, False):
            combo = FadeStopCombo(
                s1_n=None, s1_phi=None, s2_m=None, s2_buf=None,
                s3_x=None, s4_x=None, s5_x=None, t1300=t13,
            )
            tr, _, _ = _sim_trades(
                matched_train, tradeable_samples, combo, None, cfg, cfg.slippage_ticks
            )
            ev = _trade_stats(tr).get("expectancy")
            if ev is not None and float(ev) > chosen_exp:
                chosen_exp = float(ev)
                chosen_combo = combo
        if chosen_combo is None:
            fold_rec["skipped"] = "train 無可交易樣本"
            folds_out.append(fold_rec)
            continue

        best_tp, _ = optimize_tp_for_indices(
            matched_train, tradeable_samples, chosen_combo, tp_combos, cfg
        )

        test_idx = _fold_test_indices(mask, all_dates, test_start, test_end)
        f_trades, f_sources, f_lock = _sim_trades(
            test_idx, tradeable_samples, chosen_combo, best_tp, cfg, cfg.slippage_ticks
        )
        s_trades, _, _ = _sim_trades(
            test_idx, tradeable_samples, chosen_combo, best_tp, cfg, cfg.stress_slippage_ticks
        )
        for dist in cfg.guard_dist_grid:  # 敏感度診斷:凍結選擇,只換 guard(R5:不入選擇)
            cfg_d = dataclasses.replace(cfg, guard_limit_dist=dist)
            d_trades, _, _ = _sim_trades(
                test_idx, tradeable_samples, chosen_combo, best_tp, cfg_d, cfg.slippage_ticks
            )
            sens_trades[dist].extend(d_trades)

        oos_trades.extend(f_trades)
        oos_sources.extend(f_sources)
        stress_trades.extend(s_trades)
        total_test_idx += len(test_idx)
        total_lock += f_lock
        val_exps.append(best_val_exp)
        f_stats = _trade_stats(f_trades)
        exp = f_stats.get("expectancy")
        if isinstance(exp, float | int) and exp > 0:
            fold_positive += 1
        fold_rec.update(
            {
                "n_core": len(core_ids),
                "n_val": len(val_ids),
                "n_test_matched": len(test_idx),
                "conditions": conds,
                "val_exp": best_val_exp,
                "t1300": chosen_combo.t1300,
                "tp": best_tp.tp_id,
                "fold_oos": f_stats,
            }
        )
        folds_out.append(fold_rec)

    oos = _trade_stats(oos_trades)
    oos["lock_pct"] = (total_lock / total_test_idx) if total_test_idx else 0.0
    by_source: dict[str, dict[str, float | int | None]] = {}
    for src in sorted(set(oos_sources)):
        by_source[src] = _trade_stats(
            [t for t, s in zip(oos_trades, oos_sources) if s == src]
        )
    tp_choices = "|".join(
        str(f.get("tp", "-")) for f in folds_out if "tp" in f
    )
    t1300_choices = "|".join(
        str(f.get("t1300", "-")) for f in folds_out if "t1300" in f
    )
    return {
        "folds": folds_out,
        "oos": oos,
        "oos_by_source": by_source,
        "oos_stress": _trade_stats(stress_trades),
        "guard_sensitivity": {
            str(d): _trade_stats(ts) for d, ts in sens_trades.items()
        },
        "fold_positive": fold_positive,
        "n_folds": sum(1 for f in folds_out if "fold_oos" in f),
        "mean_val_exp": (sum(val_exps) / len(val_exps)) if val_exps else None,
        "tp_choices": tp_choices,
        "t1300_choices": t1300_choices,
        "oos_trades": [
            {"date": t.date, "stock_id": t.stock_id, "pnl": t.pnl, "source": s}
            for t, s in zip(oos_trades, oos_sources)
        ],
    }


def _simulate_default(
    triggered: list[tuple[FadeSample, list[Bar1K], int]],
    combo: FadeStopCombo,
    cfg: FadeBacktestConfig,
) -> tuple[list[float | None], list[str]]:
    """全 triggered 以單一 combo 模擬 → (pnl_rate 序列, status 序列)."""
    pnl: list[float | None] = []
    status: list[str] = []
    for sample, bars, trig_idx in triggered:
        out = simulate_fade_sample(bars, trig_idx, sample, combo, cfg, cfg.slippage_ticks)
        pnl.append(out.pnl_rate)
        status.append(out.status)
    return pnl, status


def _collect_tradeable(
    triggered: list[tuple[FadeSample, list[Bar1K], int]],
    features_list: list[dict[str, float | None]],
    pnl_list: list[float | None],
    status_list: list[str],
) -> tuple[
    list[dict[str, float | None]],
    list[float],
    list[str],
    list[str],
    list[tuple[FadeSample, list[Bar1K], int]],
    int,
]:
    """_TRADEABLE 過濾 → 組平行陣列(feat/pnl/dates/sids/tradeable)+ 鎖死計數(兩路徑共用)."""
    feat: list[dict[str, float | None]] = []
    pnl: list[float] = []
    dates: list[str] = []
    sids: list[str] = []
    tradeable: list[tuple[FadeSample, list[Bar1K], int]] = []
    lock = 0
    for i, (sample, bars, trig_idx) in enumerate(triggered):
        p = pnl_list[i] if i < len(pnl_list) else None
        s = status_list[i] if i < len(status_list) else ""
        if s == "locked_at_limit":
            lock += 1
        if s not in _TRADEABLE or p is None:
            continue
        feat.append(features_list[i])
        pnl.append(p)
        dates.append(sample.t1_date)
        sids.append(sample.stock_id)
        tradeable.append((sample, bars, trig_idx))
    return feat, pnl, dates, sids, tradeable, lock


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

    if cfg.wf_test_starts:  # walk-forward 路徑:固定停損(強制風控在 cfg)、GA per fold
        wf_default = FadeStopCombo(
            s1_n=None, s1_phi=None, s2_m=None, s2_buf=None,
            s3_x=None, s4_x=None, s5_x=None, t1300=cfg.baseline_t1300,
        )
        wf_pnl_list, wf_status_list = _simulate_default(triggered, wf_default, cfg)
        wf_feat, wf_pnl, wf_dates, _wf_sids, wf_tradeable, wf_lock = _collect_tradeable(
            triggered, features_list, wf_pnl_list, wf_status_list
        )
        wf = _run_walk_forward(wf_tradeable, wf_feat, wf_pnl, wf_dates, cfg)
        return {
            "arm": arm.name,
            "param": params.values,
            "max_window": max_window_m,
            "n_triggered": len(triggered),
            "n_no_trigger": no_trigger_count,
            "rules": [],
            "wf": wf,
            "is_anchor": is_anchor,
            "lock_events": wf_lock,
            "n_tradeable": len(wf_tradeable),
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
    all_feat, all_pnl, all_dates, all_sids, tradeable_samples, _lock_n = _collect_tradeable(
        triggered, features_list, default_pnl, default_status
    )
    train_feat: list[dict[str, float | None]] = []
    train_weights: list[float] = []
    train_pnl: list[float] = []
    for f, p, d in zip(all_feat, all_pnl, all_dates):
        if d < cfg.split_date:
            train_feat.append(f)
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

    from copycat.backtest.fade_optimize import build_cross_arm_table, build_wf_cross_arm_table
    from copycat.backtest.fade_report import write_fade_report

    if cfg.wf_test_starts:
        cross_arm = build_wf_cross_arm_table(all_results, cfg.min_n_test)
    else:
        cross_arm = build_cross_arm_table(all_results)

    diagnose: dict[str, object] | None = None
    if cfg.wf_test_starts:
        from copycat.backtest.fade_diagnose import diagnose_limit_approach

        samples_bars = [
            (s, read_bars(data_dir, s.stock_id, s.t1_date) or []) for s in samples
        ]
        diagnose = diagnose_limit_approach(samples_bars, cfg)

    report_path = write_fade_report(
        all_results,
        cfg,
        report_date,
        out_dir,
        evidence_dir,
        cross_arm_table=cross_arm,
        diagnose=diagnose,
        universe_counts=u_counts,
    )

    final_path = out_dir / "rules_final.json"
    atomic_write_text(
        final_path,
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
    )

    logger.info("pipeline 完成 → %s", out_dir)
    return {"results": all_results, "report": str(report_path), "rules_final": str(final_path)}
