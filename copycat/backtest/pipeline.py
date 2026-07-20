"""管線 IO 邊界(design §1):run_features / run_search(outcome cache + 三段式搜索).

determinism(D11):輸出無 timestamp、json sort_keys、樣本序 = features CSV 序、
隨機性只在 ga_search(seed)。
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from copycat.backtest.config import BacktestConfig, sim_config_hash
from copycat.backtest.features import (
    avg20_t1,
    find_trigger,
    static_features,
    structural_features,
    trigger_features,
)
from copycat.backtest.report import write_report
from copycat.backtest.search import (
    apply_rule,
    bit_indices,
    build_predicates,
    exhaustive_scan,
    ga_search,
    jaccard_dedupe,
    rule_sort_key,
)
from copycat.backtest.simulate import StopCombo, enumerate_stop_combos, simulate_sample
from copycat.backtest.stats import (
    Trade,
    max_drawdown,
    monthly_consistency,
    plateau_check,
    weighted_stats,
)
from copycat.backtest.universe import Sample, build_universe
from copycat.data.daily import DailyIndex
from copycat.data.store import read_bars
from copycat.fileio import atomic_open_text, atomic_write_text
from copycat.watchlist import load_watchlist

logger = logging.getLogger(__name__)

_CACHE_VERSION = 1
_META_COLS = [
    "stock_id",
    "date",
    "group",
    "weight",
    "prev_close",
    "limit_price",
    "t1_date",
    "t1_open",
    "trig_idx",
]
_TRIGGER_COLS = [
    "trig_min",
    "gap_open",
    "auction_lots",
    "auction_vol_ratio",
    "climb_rate",
    "burst3",
    "up_min_frac",
    "max_pullback",
    "cumvol_ratio",
    "max_minvol_x",
    "wash_bars",
    "outer_ratio",
    "touches_back",
]
_STATIC_COLS = ["amt_t1_m", "ret5", "ret20", "prev_limitup", "dtr_t1"]
_STRUCT_COLS = ["dist_ma20", "dist_ma60", "bb_width_pct120", "pos_52w", "ignition_first"]
# 謂詞特徵 = 盤中 + 靜態 + 位階 + prev_close(meta 兼特徵,neigui 同源)
FEATURE_NAMES = _TRIGGER_COLS + _STATIC_COLS + _STRUCT_COLS + ["prev_close"]
_TRADEABLE = {"stopped", "time_1300", "closeout", "hold_e1"}
_BASELINE = "baseline"
_BASELINE_STRESS = "baseline_stress"


def _theta_key(theta: float) -> str:
    return f"{theta:.3f}"


def _features_path(out_dir: Path, theta: float) -> Path:
    return out_dir / f"features_theta{_theta_key(theta)}.csv"


def _outcomes_path(out_dir: Path, theta: float) -> Path:
    return out_dir / f"outcomes_theta{_theta_key(theta)}.json"


def run_features(
    data_dir: Path, out_dir: Path, cfg: BacktestConfig, core_wl_path: Path, aux_wl_path: Path
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    daily = DailyIndex.load(data_dir)
    core = load_watchlist(core_wl_path)
    aux = load_watchlist(aux_wl_path)
    universe, u_counts = build_universe(data_dir, daily, core, aux, cfg)

    # θ 無關的每樣本前置(static/structural/avg20/t1_open/bars)只算一次(review F4)
    per_sample: list[
        tuple[
            Sample,
            list,
            dict[str, float | bool | None] | None,
            float | None,
            dict[str, float | None],
            float | None,
        ]
    ] = []
    for s in universe:
        bars = read_bars(data_dir, s.stock_id, s.date)
        if not bars:
            per_sample.append((s, [], None, None, {}, None))
            continue
        stat = static_features(daily, s.stock_id, s.date)
        avg20 = avg20_t1(daily, s.stock_id, s.date)
        struct = structural_features(daily, s.stock_id, s.date, cfg)
        t1_open = daily.open_of(s.stock_id, s.t1_date) if s.t1_date else None
        per_sample.append((s, bars, stat, avg20, struct, t1_open))

    per_theta: dict[str, dict[str, int]] = {}
    fields = _META_COLS + _TRIGGER_COLS + _STATIC_COLS + _STRUCT_COLS
    for theta in cfg.theta_grid:
        counts = {"rows": 0, "missing_1k": 0, "no_trigger": 0, "missing_static": 0}
        rows_out: list[dict[str, str]] = []
        for s, bars, stat, avg20, struct, t1_open in per_sample:
            if not bars:
                counts["missing_1k"] += 1
                continue
            trig = find_trigger(bars, s.prev_close, theta, cfg.float_eps)
            if trig is None:
                counts["no_trigger"] += 1
                continue
            if stat is None or avg20 is None:
                counts["missing_static"] += 1
                continue
            feats = trigger_features(
                bars,
                trig,
                s.prev_close,
                theta,
                avg20,
                stat,
                tb_upper=cfg.touchback_upper,
                tb_lower=cfg.touchback_lower,
            )
            row: dict[str, str] = {
                "stock_id": s.stock_id,
                "date": s.date,
                "group": s.group,
                "weight": str(s.weight),
                "prev_close": str(s.prev_close),
                "limit_price": str(s.limit_price),
                "t1_date": s.t1_date or "",
                "t1_open": "" if t1_open is None else str(t1_open),
                "trig_idx": str(trig),
            }
            for col in _TRIGGER_COLS + _STATIC_COLS:
                v = feats.get(col)
                row[col] = "" if v is None else str(v)
            for col in _STRUCT_COLS:
                v = struct.get(col)
                row[col] = "" if v is None else str(v)
            rows_out.append(row)
            counts["rows"] += 1
        path = _features_path(out_dir, theta)
        with atomic_open_text(path) as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(rows_out)
        per_theta[_theta_key(theta)] = counts
    counts_path = out_dir / "universe_counts.json"
    atomic_write_text(
        counts_path,
        json.dumps(
            {"universe": u_counts, "per_theta": per_theta},
            ensure_ascii=False,
            sort_keys=True,
            indent=1,
        ),
    )
    logger.info("features 完成 → %s", out_dir)
    return out_dir


def _read_features(out_dir: Path, theta: float) -> list[dict[str, object]]:
    path = _features_path(out_dir, theta)
    if not path.exists():
        raise RuntimeError(
            f"缺 {path.name} — 請先以同一份 config 跑 `python -m copycat tday-features`"
            f"(θ 網格不一致,review F10)"
        )
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            row: dict[str, object] = {
                "stock_id": r["stock_id"],
                "date": r["date"],
                "group": r["group"],
                "t1_date": r["t1_date"] or None,
            }
            for col in ("weight", "prev_close", "limit_price", "t1_open"):
                row[col] = float(r[col]) if r[col] else None
            row["trig_idx"] = int(r["trig_idx"])
            for col in _TRIGGER_COLS + _STATIC_COLS + _STRUCT_COLS:
                row[col] = float(r[col]) if r[col] else None
            rows.append(row)
    return rows


def _row_sample(row: dict[str, object]) -> Sample:
    weight = row["weight"]
    prev_close = row["prev_close"]
    limit_price = row["limit_price"]
    assert isinstance(weight, float) and isinstance(prev_close, float)
    assert isinstance(limit_price, float)
    t1_date = row["t1_date"]
    return Sample(
        stock_id=str(row["stock_id"]),
        date=str(row["date"]),
        group=str(row["group"]),
        weight=weight,
        prev_close=prev_close,
        limit_price=limit_price,
        t1_date=t1_date if isinstance(t1_date, str) else None,
    )


def _rows_hash(rows: list[dict[str, object]]) -> str:
    """樣本身分 hash(stock_id/date/trig_idx 序列)— cache 錯位防護(review F1)."""
    import hashlib

    blob = json.dumps(
        [(str(r["stock_id"]), str(r["date"]), r["trig_idx"]) for r in rows], sort_keys=True
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _load_or_simulate(
    data_dir: Path,
    out_dir: Path,
    cfg: BacktestConfig,
    theta: float,
    rows: list[dict[str, object]],
    with_grid: bool,
) -> dict[str, object]:
    path = _outcomes_path(out_dir, theta)
    sim_hash = sim_config_hash(cfg)
    rows_hash = _rows_hash(rows)
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            payload.get("_cache_version") == _CACHE_VERSION
            and payload.get("sim_hash") == sim_hash
            and payload.get("rows_hash") == rows_hash
            and payload.get("with_grid") == with_grid
        ):
            return payload
        logger.info("outcome cache 不符(%s)→ 重算", path.name)

    # 252 網格只在 anchor θ 展開(review F2:非 anchor 只需 baseline 供 θ 曲線)
    combos = enumerate_stop_combos(cfg) if with_grid else []
    baseline = StopCombo(
        s1_n=None,
        s1_phi=None,
        s2_m=cfg.baseline_s2_lookback,
        s2_buf=cfg.baseline_s2_buffer,
        s3_x=None,
        s4_x=None,
        t1300=cfg.baseline_t1300,
    )
    keyed: list[tuple[str, StopCombo, int]] = [
        (_BASELINE, baseline, cfg.slippage_ticks),
        (_BASELINE_STRESS, baseline, cfg.stress_slippage_ticks),
    ] + [(c.combo_id, c, cfg.slippage_ticks) for c in combos]
    pnl: dict[str, list[float | None]] = {k: [] for k, _, _ in keyed}
    status: dict[str, list[str]] = {k: [] for k, _, _ in keyed}
    for row in rows:
        sample = _row_sample(row)
        bars = read_bars(data_dir, sample.stock_id, sample.date)
        assert bars is not None  # features 產出過 → 1K 必在
        trig_idx = row["trig_idx"]
        assert isinstance(trig_idx, int)
        t1_open = row["t1_open"]
        t1o = t1_open if isinstance(t1_open, float) else None
        for key, combo, ticks in keyed:
            out = simulate_sample(bars, trig_idx, sample, t1o, combo, cfg, ticks)
            pnl[key].append(out.pnl_rate)
            status[key].append(out.status)
    payload: dict[str, object] = {
        "_cache_version": _CACHE_VERSION,
        "sim_hash": sim_hash,
        "rows_hash": rows_hash,
        "with_grid": with_grid,
        "theta": _theta_key(theta),
        "n_samples": len(rows),
        "combo_keys": [k for k, _, _ in keyed],
        "pnl": pnl,
        "status": status,
    }
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return payload


def _regime_filter(name: str, row: dict[str, object], cfg: BacktestConfig) -> bool:
    if name == "all":
        return True
    if name == "momentum":
        ret20 = row.get("ret20")
        return isinstance(ret20, float) and ret20 > 0
    dist = row.get("dist_ma60")
    bbp = row.get("bb_width_pct120")
    ign = row.get("ignition_first")
    return (
        (isinstance(dist, float) and abs(dist) <= cfg.lowbase_dist_ma60_abs)
        or (isinstance(bbp, float) and bbp <= cfg.lowbase_bb_pct)
        or ign == 1.0
    )


def _trades_for(
    rows: list[dict[str, object]],
    idxs: list[int],
    pnl: list[float | None],
    status: list[str],
) -> list[Trade]:
    out = []
    for i in idxs:
        p = pnl[i]
        if status[i] in _TRADEABLE and p is not None:
            weight = rows[i]["weight"]
            assert isinstance(weight, float)
            out.append(Trade(str(rows[i]["date"]), str(rows[i]["stock_id"]), p, weight))
    return out


def _feature_row(row: dict[str, object]) -> dict[str, float | None]:
    """features row → 謂詞用特徵 dict(單一出口,train/test/跨 θ 三處共用)."""
    return {k: (v if isinstance(v, float) else None) for k, v in row.items() if k in FEATURE_NAMES}


def run_search(
    data_dir: Path,
    out_dir: Path,
    cfg: BacktestConfig,
    report_date: str,
    report_dir: Path | None = None,
) -> Path:
    rows_by_theta = {t: _read_features(out_dir, t) for t in cfg.theta_grid}
    outcomes = {
        t: _load_or_simulate(
            data_dir, out_dir, cfg, t, rows_by_theta[t], with_grid=(t in cfg.anchor_thetas)
        )
        for t in cfg.theta_grid
    }

    test_end = max(
        (str(r["date"]) for rows in rows_by_theta.values() for r in rows), default=cfg.split_date
    )
    final_rules: list[dict[str, object]] = []
    theta_curves: dict[str, dict[str, float | None]] = {}
    negative: list[str] = []

    for regime in ("all", "momentum", "low_base"):
        for anchor in cfg.anchor_thetas:
            rows = rows_by_theta[anchor]
            oc = outcomes[anchor]
            pnl_map = oc["pnl"]
            status_map = oc["status"]
            assert isinstance(pnl_map, dict) and isinstance(status_map, dict)
            base_pnl: list[float | None] = pnl_map[_BASELINE]
            base_status: list[str] = status_map[_BASELINE]
            in_regime = [i for i, r in enumerate(rows) if _regime_filter(regime, r, cfg)]
            train_idx = [i for i in in_regime if str(rows[i]["date"]) < cfg.split_date]
            test_idx = [i for i in in_regime if str(rows[i]["date"]) >= cfg.split_date]
            if not train_idx or not test_idx:
                negative.append(f"regime={regime} θ={anchor}: train/test 樣本不足,跳過")
                continue
            train_rows = [rows[i] for i in train_idx]
            # fitness 向量:不可交易(excluded)→ weight 0
            fit_pnl: list[float] = []
            fit_w: list[float] = []
            for i in train_idx:
                p = base_pnl[i]
                weight = rows[i]["weight"]
                assert isinstance(weight, float)
                ok = base_status[i] in _TRADEABLE and p is not None
                fit_pnl.append(p if ok and p is not None else 0.0)
                fit_w.append(weight if ok else 0.0)
            preds = build_predicates(
                [_feature_row(r) for r in train_rows], FEATURE_NAMES, cfg.quantile_probs
            )
            cands = exhaustive_scan(preds, fit_pnl, fit_w, cfg)
            for seed in cfg.ga_seeds:
                cands += ga_search(preds, fit_pnl, fit_w, cfg, seed)
            cands.sort(key=rule_sort_key)
            cands = jaccard_dedupe(cands, cfg.jaccard_max)[:10]

            for rank, cand in enumerate(cands):
                conds = cand["conditions"]
                assert isinstance(conds, list)
                # θ 曲線(test,baseline 停損組;凍結門檻套各 θ 表)
                curve: dict[float, float] = {}
                curve_out: dict[str, float | None] = {}
                for theta in cfg.theta_grid:
                    t_rows = rows_by_theta[theta]
                    t_oc = outcomes[theta]
                    t_pnl = t_oc["pnl"][_BASELINE]  # type: ignore[index]
                    t_status = t_oc["status"][_BASELINE]  # type: ignore[index]
                    t_test = [
                        i
                        for i, r in enumerate(t_rows)
                        if str(r["date"]) >= cfg.split_date and _regime_filter(regime, r, cfg)
                    ]
                    feat_rows = [_feature_row(t_rows[i]) for i in t_test]
                    mask = apply_rule(conds, feat_rows)
                    hit_idx = [t_test[j] for j in bit_indices(mask)]
                    trades = _trades_for(t_rows, hit_idx, t_pnl, t_status)
                    stats = weighted_stats(trades)
                    exp = stats["expectancy"]
                    curve_out[_theta_key(theta)] = exp if isinstance(exp, float) else None
                    if isinstance(exp, float):
                        curve[round(theta, 4)] = exp
                # anchor θ test 統計 + 三道驗證
                feat_rows_anchor = [_feature_row(rows[i]) for i in test_idx]
                mask_a = apply_rule(conds, feat_rows_anchor)
                hits_a = [test_idx[j] for j in bit_indices(mask_a)]
                trades_a = _trades_for(rows, hits_a, base_pnl, base_status)
                stats_a = weighted_stats(trades_a)
                monthly = monthly_consistency(trades_a, cfg.split_date, test_end)
                plateau = plateau_check(curve, anchor, cfg)
                exp_a = stats_a["expectancy"]
                passed = (
                    isinstance(exp_a, float) and exp_a > 0 and bool(monthly["passed"]) and plateau
                )
                # 階段③:停損網格展開(test、rule 命中樣本)
                duel: dict[str, dict[str, object]] = {}
                for key in oc["combo_keys"]:  # type: ignore[union-attr]
                    if key in (_BASELINE, _BASELINE_STRESS):
                        continue
                    trades_c = _trades_for(rows, hits_a, pnl_map[key], status_map[key])
                    s = weighted_stats(trades_c)
                    duel[key] = {**s, "mdd": max_drawdown(trades_c)}
                stress_trades = _trades_for(
                    rows, hits_a, pnl_map[_BASELINE_STRESS], status_map[_BASELINE_STRESS]
                )
                record: dict[str, object] = {
                    "regime": regime,
                    "anchor_theta": _theta_key(anchor),
                    "rank": rank,
                    "conditions": conds,
                    "fitness_train": cand["fitness"],
                    "support_train_raw": cand["support_raw"],
                    "test_expectancy": stats_a["expectancy"],
                    "test_p_win": stats_a["p_win"],
                    "test_payoff": stats_a["payoff"],
                    "test_mdd": max_drawdown(trades_a),
                    "test_n_raw": stats_a["n_raw"],
                    "monthly_passed": bool(monthly["passed"]),
                    "monthly_hits": monthly["monthly_hits"],
                    "plateau_passed": plateau,
                    "passed_all": passed,
                    "theta_curve": curve_out,
                    "stop_duel": duel,
                    "stress_expectancy": weighted_stats(stress_trades)["expectancy"],
                }
                final_rules.append(record)
                if rank == 0:  # key 含 anchor,多錨點不互相覆蓋(review F7)
                    theta_curves[f"{regime}@{_theta_key(anchor)}#top"] = curve_out
                if not passed:
                    negative.append(
                        f"regime={regime} rank={rank}: "
                        f"test>0={isinstance(exp_a, float) and exp_a > 0} "
                        f"月度={bool(monthly['passed'])} 平台={plateau}"
                    )

    # 開盤即攻分桶(<09:05 觸發)與 3055 case(anchor θ、baseline)
    anchor0 = cfg.anchor_thetas[0]
    rows0 = rows_by_theta[anchor0]
    oc0 = outcomes[anchor0]
    early_idx = [
        i for i, r in enumerate(rows0) if isinstance(r["trig_min"], float) and r["trig_min"] < 5
    ]
    early_trades = _trades_for(rows0, early_idx, oc0["pnl"][_BASELINE], oc0["status"][_BASELINE])  # type: ignore[index]
    early = {"n_candidates": len(early_idx), **weighted_stats(early_trades)}
    case_3055 = next(
        (
            {
                "date": str(r["date"]),
                "trig_min": r["trig_min"],
                "group": str(r["group"]),
                "dist_ma60": r["dist_ma60"],
                "bb_width_pct120": r["bb_width_pct120"],
                "ignition_first": r["ignition_first"],
            }
            for r in rows0
            if str(r["stock_id"]) == cfg.case_stock_id
        ),
        None,
    )
    counts_path = out_dir / "universe_counts.json"
    counts = json.loads(counts_path.read_text(encoding="utf-8")) if counts_path.exists() else {}

    result: dict[str, object] = {
        "rules": final_rules,
        "theta_curves": theta_curves,
        "stop_duel": (final_rules[0]["stop_duel"] if final_rules else {}),
        "early_attack": early,
        "slippage_stress": {
            r_key: {"base": r["test_expectancy"], "stress": r["stress_expectancy"]}
            for r_key, r in (
                (f"{r['regime']}@{r['anchor_theta']}#r{r['rank']}", r)
                for r in final_rules
                if r["rank"] == 0
            )
        },
        "case_3055": case_3055,
        "negative_findings": sorted(negative),
    }
    rules_path = out_dir / "rules_final.json"
    atomic_write_text(rules_path, json.dumps(result, ensure_ascii=False, sort_keys=True, indent=1))
    return write_report(report_dir or out_dir, result, counts, report_date, cfg)
