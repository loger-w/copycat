"""逼近漲停診斷(SC-7)+ round 2 三池無條件 fade 複驗(SC-3).

前者回答 guard 設計的核心經驗問題(P(鎖|逼近)/ 回落深度);後者回答主問題
「優式池 fade 是否值得做」——判定式與門檻全部 pre-registered 於 config
(docs/strategy-decisions.md §4)。純統計、不涉及任何規則選擇。
"""

from __future__ import annotations

import csv
import dataclasses
import json
import logging
import math
import os
import random
from collections import defaultdict
from pathlib import Path

from copycat.backtest.fade_config import NO_STOP_HOLD_COMBO, FadeBacktestConfig
from copycat.backtest.fade_report import _fmt
from copycat.backtest.fade_simulate import FadeSample, simulate_fade_sample
from copycat.data.models import Bar1K
from copycat.market import limit_up_price

logger = logging.getLogger(__name__)

_EARLY_M = 59  # < 10:00
_HEAVY_VOL_RATIO = 2.0  # 逼近 bar 量 / 前 20bar 均量


def _quantile(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    idx = min(len(s) - 1, int(p * len(s)))
    return s[idx]


def _classify_approach(
    bars: list[Bar1K], limit: float, level: float, eps: float
) -> dict[str, object] | None:
    """回傳逼近事件分類;未逼近 → None."""
    approach_i: int | None = None
    for i, b in enumerate(bars):
        if b.high >= level:
            approach_i = i
            break
    if approach_i is None:
        return None
    ended_locked = bars[-1].low >= limit - eps
    after = bars[approach_i:]
    min_low_after = min(b.low for b in after)
    reversal_depth = max(0.0, (level - min_low_after) / level)

    prior = bars[max(0, approach_i - 20) : approach_i]
    avg_vol = sum(b.volume for b in prior) / len(prior) if prior else 0.0
    vol_ratio = bars[approach_i].volume / avg_vol if avg_vol > 0 else None
    return {
        "ended_locked": ended_locked,
        "reversal_depth": None if ended_locked else reversal_depth,
        "early": bars[approach_i].m < _EARLY_M,
        "heavy": (vol_ratio is not None and vol_ratio >= _HEAVY_VOL_RATIO),
        "vol_known": vol_ratio is not None,
    }


def _bucket_stats(events: list[dict[str, object]]) -> dict[str, float | int | None]:
    n = len(events)
    locked = sum(1 for e in events if e["ended_locked"])
    depths = [e["reversal_depth"] for e in events if e["reversal_depth"] is not None]
    depths_f = [d for d in depths if isinstance(d, float)]
    return {
        "n": n,
        "p_lock": (locked / n) if n else None,
        "p_reverse": ((n - locked) / n) if n else None,
        "reversal_depth_med": _quantile(depths_f, 0.5),
        "reversal_depth_p25": _quantile(depths_f, 0.25),
        "reversal_depth_p75": _quantile(depths_f, 0.75),
    }


def diagnose_limit_approach(
    samples_bars: list[tuple[FadeSample, list[Bar1K]]],
    cfg: FadeBacktestConfig,
) -> dict[str, object]:
    """全 universe 逼近漲停統計,per guard dist × (量能 × 時段) 分桶."""
    out: dict[str, object] = {"n_samples": len(samples_bars)}
    per_dist: dict[str, object] = {}
    for dist in cfg.guard_dist_grid:
        events: list[dict[str, object]] = []
        for sample, bars in samples_bars:
            if not bars:
                continue
            t1_limit = limit_up_price(sample.limit)
            level = t1_limit * (1.0 - dist)
            ev = _classify_approach(bars, t1_limit, level, cfg.limit_eps)
            if ev is not None:
                events.append(ev)
        buckets = {
            "early_heavy": [e for e in events if e["early"] and e["heavy"]],
            "early_light": [e for e in events if e["early"] and not e["heavy"] and e["vol_known"]],
            "late_heavy": [e for e in events if not e["early"] and e["heavy"]],
            "late_light": [
                e for e in events if not e["early"] and not e["heavy"] and e["vol_known"]
            ],
        }
        per_dist[f"{dist}"] = {
            "overall": _bucket_stats(events),
            "buckets": {k: _bucket_stats(v) for k, v in buckets.items()},
        }
    out["per_dist"] = per_dist
    return out


# ---------- round 2:三池無條件 fade 複驗(SC-3)----------

_POOLS = ("tiger_2plus", "tiger_1", "control", "scan")

_NO_STOP_COMBO = NO_STOP_HOLD_COMBO


@dataclasses.dataclass(frozen=True, slots=True)
class _PoolTrade:
    pnl: float
    day: str  # t1_date(日聚類/分層鍵)
    status: str
    turnover: float  # T 日成交額(雙重分層用;查無 → 0.0)


def assign_pool(sample: FadeSample, watchlist_ids: frozenset[str]) -> str:
    """R5 分派優先序:broker_ids 命中 watchlist → tiger(不論 source);否則按 source."""
    hits = [b for b in sample.broker_ids.split("|") if b and b in watchlist_ids]
    if len(hits) >= 2:
        return "tiger_2plus"
    if len(hits) == 1:
        return "tiger_1"
    return "control" if sample.source == "control" else "scan"


def cluster_se(values: list[float], days: list[str]) -> float:
    """日聚類(CR0)標準誤:sqrt(Σ_d (Σ_{i∈d}(x_i − mean))²) / n."""
    if not values:
        return 0.0
    m = sum(values) / len(values)
    by_day: dict[str, float] = defaultdict(float)
    for x, d in zip(values, days):
        by_day[d] += x - m
    return math.sqrt(sum(v * v for v in by_day.values())) / len(values)


def _normal_tail(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def stratified_permutation_p(
    values_a: list[float],
    strata_a: list[str],
    values_b: list[float],
    strata_b: list[str],
    iters: int,
    seed: int,
) -> tuple[float, float]:
    """層內洗牌單尾檢定(H1: mean_a − mean_b > 0)→ (觀察差, p)."""
    obs = (sum(values_a) / len(values_a)) - (sum(values_b) / len(values_b))
    by_stratum: dict[str, list[tuple[float, bool]]] = defaultdict(list)
    for v, s in zip(values_a, strata_a):
        by_stratum[s].append((v, True))
    for v, s in zip(values_b, strata_b):
        by_stratum[s].append((v, False))
    rng = random.Random(seed)
    hits = 0
    for _ in range(iters):
        sa = sb = 0.0
        na = nb = 0
        for items in by_stratum.values():
            k = sum(1 for _, is_a in items if is_a)
            vals = [v for v, _ in items]
            rng.shuffle(vals)
            sa += sum(vals[:k])
            na += k
            sb += sum(vals[k:])
            nb += len(vals) - k
        if na and nb and (sa / na - sb / nb) >= obs:
            hits += 1
    return obs, hits / iters


def _pool_run(
    samples_bars: list[tuple[FadeSample, list[Bar1K]]],
    turnover_map: dict[tuple[str, str], float],
    label_cutoff: str,
    cfg: FadeBacktestConfig,
    watchlist_ids: frozenset[str],
    slippage_ticks: int,
) -> tuple[dict[str, dict[str, object]], dict[str, list[_PoolTrade]]]:
    """共同期間內全事件無條件 fade(首根 open 進場)→ (per-pool 統計, per-pool 交易)."""
    trades: dict[str, list[_PoolTrade]] = {p: [] for p in _POOLS}
    excluded_guard: dict[str, int] = dict.fromkeys(_POOLS, 0)
    excluded_other: dict[str, int] = dict.fromkeys(_POOLS, 0)
    for sample, bars in samples_bars:
        if not bars or sample.t1_date > label_cutoff:
            continue
        pool = assign_pool(sample, watchlist_ids)
        out = simulate_fade_sample(
            bars,
            0,
            sample,
            _NO_STOP_COMBO,
            cfg,
            slippage_ticks,
            entry_price_override=bars[0].open,
        )
        if out.status == "excluded_guard_at_entry":
            excluded_guard[pool] += 1
        elif out.pnl_rate is None:
            excluded_other[pool] += 1
        else:
            trades[pool].append(
                _PoolTrade(
                    pnl=out.pnl_rate,
                    day=sample.t1_date,
                    status=out.status,
                    turnover=turnover_map.get((sample.stock_id, sample.date), 0.0),
                )
            )

    pools: dict[str, dict[str, object]] = {}
    for p in _POOLS:
        pnl = [t.pnl for t in trades[p]]
        days = [t.day for t in trades[p]]
        locked = sum(1 for t in trades[p] if t.status == "locked_at_limit")
        pools[p] = {
            "n": len(pnl),
            "days": len(set(days)),
            "mean": (sum(pnl) / len(pnl)) if pnl else None,
            "cluster_se": cluster_se(pnl, days) if pnl else None,
            "median": _quantile(pnl, 0.5),
            "p_win": (sum(1 for x in pnl if x > 0) / len(pnl)) if pnl else None,
            "relock_rate": (locked / len(pnl)) if pnl else None,
            "excluded_guard_at_entry": excluded_guard[p],
            "excluded_other": excluded_other[p],
        }
    return pools, trades


def _comparison_and_verdict(
    trades: dict[str, list[_PoolTrade]], cfg: FadeBacktestConfig
) -> tuple[dict[str, object], dict[str, object]]:
    """判定式 (i)(ii) 計算(全期間主判定與 forward 段複核共用;數值路徑不變)."""
    tiger = trades["tiger_1"] + trades["tiger_2plus"]
    others = trades["control"] + trades["scan"]
    comparison: dict[str, object] = {"n_tiger": len(tiger), "n_others": len(others)}
    verdict: dict[str, object] = {"continue_uc": False, "criteria": {}}
    if tiger and others:
        t_pnl = [t.pnl for t in tiger]
        t_days = [t.day for t in tiger]
        t_mean = sum(t_pnl) / len(t_pnl)
        t_se = cluster_se(t_pnl, t_days)
        if t_se > 0:
            z = t_mean / t_se
            p_pos = _normal_tail(z) if t_mean > 0 else 1.0
        else:  # 退化(全數相同):SE=0,正均值視為確定為正
            z = math.inf if t_mean > 0 else 0.0
            p_pos = 0.0 if t_mean > 0 else 1.0

        o_pnl = [t.pnl for t in others]
        o_days = [t.day for t in others]
        diff, p_diff = stratified_permutation_p(
            t_pnl, t_days, o_pnl, o_days, cfg.diagnose_perm_iters, cfg.diagnose_perm_seed
        )

        # 日 × T 日成交額中位數 雙重分層(成分混淆控制,報告項不入判定)
        all_turn = [t.turnover for t in tiger + others if t.turnover > 0]
        med_turn = _quantile(all_turn, 0.5) or 0.0
        strata2_t = [f"{t.day}|{int(t.turnover > med_turn)}" for t in tiger]
        strata2_o = [f"{t.day}|{int(t.turnover > med_turn)}" for t in others]
        _, p_diff2 = stratified_permutation_p(
            t_pnl, strata2_t, o_pnl, strata2_o, cfg.diagnose_perm_iters, cfg.diagnose_perm_seed
        )

        criteria = {
            "tiger_mean_gt0": t_mean > 0,
            "p_positive_lt_threshold": p_pos < cfg.diagnose_p_threshold,
            "diff_ge_min_edge": diff >= cfg.diagnose_min_edge_pp,
            "diff_p_lt_threshold": p_diff < cfg.diagnose_p_threshold,
        }
        comparison.update(
            {
                "tiger_mean": t_mean,
                "tiger_cluster_se": t_se,
                "tiger_z": z,
                "tiger_p_positive": p_pos,
                "others_mean": sum(o_pnl) / len(o_pnl),
                "diff": diff,
                "diff_perm_p": p_diff,
                "diff_perm_p_double_strat": p_diff2,
                "median_turnover": med_turn,
            }
        )
        verdict = {"continue_uc": all(criteria.values()), "criteria": criteria}
    return comparison, verdict


def diagnose_pool_fade(
    samples_bars: list[tuple[FadeSample, list[Bar1K]]],
    turnover_map: dict[tuple[str, str], float],
    label_cutoff: str,
    cfg: FadeBacktestConfig,
    watchlist_ids: frozenset[str],
) -> dict[str, object]:
    """四池無條件 fade 複驗 + 判定式(base config 判定;stress / lock_penalty 僅敏感度).

    判定式(pre-registered,change-spec SC-3):tiger = tiger_1 ∪ tiger_2plus;
    對照 = control + scan(無標記全池);
    (i) tiger mean > 0 且日聚類 z 單尾 p < diagnose_p_threshold;
    (ii) diff ≥ diagnose_min_edge_pp 且日內分層 permutation 單尾 p < diagnose_p_threshold。
    """
    pools, trades = _pool_run(
        samples_bars, turnover_map, label_cutoff, cfg, watchlist_ids, cfg.slippage_ticks
    )
    comparison, verdict = _comparison_and_verdict(trades, cfg)

    # round 3(SC-7/二輪 R2):forward 段(≥ forward_start)同式複核,
    # 機制事先凍結;門檻(≥20 交易日)未到僅列數不判定。主判定仍以全共同期間計。
    fwd_samples = [(s, b) for s, b in samples_bars if s.t1_date >= cfg.forward_start]
    fwd_pools, fwd_trades = _pool_run(
        fwd_samples, turnover_map, label_cutoff, cfg, watchlist_ids, cfg.slippage_ticks
    )
    fwd_comparison, fwd_verdict = _comparison_and_verdict(fwd_trades, cfg)
    fwd_tiger_days = {
        t.day for t in fwd_trades["tiger_1"] + fwd_trades["tiger_2plus"]
    }
    forward = {
        "forward_start": cfg.forward_start,
        "pools": fwd_pools,
        "comparison": fwd_comparison,
        "verdict": fwd_verdict,
        "tiger_days": len(fwd_tiger_days),
        "threshold_met": len(fwd_tiger_days) >= 20,
    }

    variants: dict[str, object] = {}
    stress_pools, _ = _pool_run(
        samples_bars,
        turnover_map,
        label_cutoff,
        dataclasses.replace(cfg, stress_guard_fill_high=True),
        watchlist_ids,
        cfg.stress_slippage_ticks,
    )
    variants["stress"] = stress_pools
    for pen in cfg.lock_penalty_grid:
        pen_pools, _ = _pool_run(
            samples_bars,
            turnover_map,
            label_cutoff,
            dataclasses.replace(cfg, lock_penalty=pen),
            watchlist_ids,
            cfg.slippage_ticks,
        )
        variants[f"lock_penalty_{pen}"] = pen_pools

    logger.info(
        "diagnose_pool_fade cutoff=%s tiger n=%s verdict=%s",
        label_cutoff,
        comparison.get("n_tiger"),
        verdict.get("continue_uc"),
    )
    return {
        "label_cutoff": label_cutoff,
        "pools": pools,
        "comparison": comparison,
        "verdict": verdict,
        "forward": forward,
        "variants": variants,
    }


def _pool_table_lines(pools: dict[str, object], title: str) -> list[str]:
    lines = [f"### {title}", ""]
    lines.append("| pool | n | days | 淨EV | 日聚類SE | med | p_win | 再鎖率 | guard排除 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for p in _POOLS:
        s = pools.get(p)
        if not isinstance(s, dict):
            continue
        lines.append(
            f"| {p} | {s.get('n', 0)} | {s.get('days', 0)}"
            f" | {_fmt(s.get('mean'))} | {_fmt(s.get('cluster_se'))}"
            f" | {_fmt(s.get('median'))} | {_fmt(s.get('p_win'), '.2f')}"
            f" | {_fmt(s.get('relock_rate'), '.1%')}"
            f" | {s.get('excluded_guard_at_entry', 0)} |"
        )
    lines.append("")
    return lines


def write_pool_fade_report(
    result: dict[str, object],
    cfg: FadeBacktestConfig,
    report_date: str,
    path: Path,
) -> None:
    """三池複驗 markdown 報告(獨立檔,不動 fade_report.py 既有章節)."""
    cost = cfg.fee_rate * (1.0 - cfg.fee_discount) * 2.0 + cfg.intraday_tax
    lines: list[str] = []
    lines.append(f"# UC 池無條件 fade 複驗(1K + guard;{report_date})")
    lines.append("")
    lines.append("## 方法論")
    lines.append("")
    lines.append("- 進場 = T+1 首根 1K bar open − slippage(悲觀);出場 = guard/災難/鎖死/收盤。")
    lines.append(
        f"- 成本 {cost:.4%}/來回;guard {_fmt(cfg.guard_limit_dist, '.1%')}、"
        f"災難 {_fmt(cfg.disaster_x, '.1%')}、鎖死懲罰 {_fmt(cfg.lock_penalty, '.2f')}。"
    )
    lines.append(f"- 共同期間:t1_date ≤ {result.get('label_cutoff')}(標記截止;期間外不進對照)。")
    lines.append(
        "- 判定式(pre-registered):(i) tiger 淨 EV>0 且日聚類 z 單尾 p"
        f" < {cfg.diagnose_p_threshold};(ii) tiger − (control+scan) ≥"
        f" {cfg.diagnose_min_edge_pp:.3f} 且日內分層洗牌單尾 p < {cfg.diagnose_p_threshold}。"
    )
    lines.append("")
    pools = result.get("pools")
    if isinstance(pools, dict):
        lines.extend(_pool_table_lines(pools, "四池(base config)"))

    comp = result.get("comparison")
    verdict = result.get("verdict")
    if isinstance(comp, dict) and isinstance(verdict, dict):
        lines.append("## 判定 Q1(池子有肉;SC-3 拆兩題,本檔僅答 Q1)")
        lines.append("")
        lines.append(
            f"- tiger(合併)淨 EV = {_fmt(comp.get('tiger_mean'))}"
            f"(日聚類 SE {_fmt(comp.get('tiger_cluster_se'))},z = {_fmt(comp.get('tiger_z'), '.2f')},"
            f"單尾 p = {_fmt(comp.get('tiger_p_positive'))})"
        )
        lines.append(
            f"- tiger − 對照(control+scan)差 = {_fmt(comp.get('diff'))}"
            f"(日內分層洗牌 p = {_fmt(comp.get('diff_perm_p'))};"
            f"日×成交額雙重分層 p = {_fmt(comp.get('diff_perm_p_double_strat'))})"
        )
        crit = verdict.get("criteria")
        if isinstance(crit, dict):
            for k, v in crit.items():
                lines.append(f"- {k}: {'PASS' if v else 'FAIL'}")
        lines.append("")
        lines.append(f"**UC 方向值得繼續:{'是' if verdict.get('continue_uc') else '否(見上列未過項)'}**")
        lines.append("")

    forward = result.get("forward")
    if isinstance(forward, dict):
        lines.append(f"## forward 段(t1 ≥ {forward.get('forward_start')};同式複核)")
        lines.append("")
        met = forward.get("threshold_met")
        lines.append(
            f"- tiger 交易日 = {forward.get('tiger_days')};門檻(≥20 交易日)"
            f"{'已到,判定生效' if met else '未到,僅列數不判定'}。"
        )
        lines.append("")
        fwd_pools = forward.get("pools")
        if isinstance(fwd_pools, dict):
            lines.extend(_pool_table_lines(fwd_pools, "forward 四池"))
        fwd_comp = forward.get("comparison")
        if isinstance(fwd_comp, dict) and fwd_comp.get("tiger_mean") is not None:
            lines.append(
                f"- forward tiger 淨 EV = {_fmt(fwd_comp.get('tiger_mean'))}"
                f"(z = {_fmt(fwd_comp.get('tiger_z'), '.2f')},"
                f"diff = {_fmt(fwd_comp.get('diff'))},"
                f"洗牌 p = {_fmt(fwd_comp.get('diff_perm_p'))})"
            )
            lines.append("")

    variants = result.get("variants")
    if isinstance(variants, dict):
        lines.append("## 敏感度(僅診斷,不入判定)")
        lines.append("")
        for name, v_pools in variants.items():
            if isinstance(v_pools, dict):
                lines.extend(_pool_table_lines(v_pools, str(name)))

    counts = result.get("universe_counts")
    if isinstance(counts, dict):
        parts = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        lines.append(f"Universe counts:{parts}")
        lines.append("")

    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def load_turnover_map(data_dir: Path) -> dict[tuple[str, str], float]:
    """T 日成交額(close × volume_lots)map,雙重分層用;缺檔回空 map."""
    path = data_dir / "daily" / "prices.csv"
    out: dict[tuple[str, str], float] = {}
    if not path.exists():
        return out
    bad = 0
    with path.open("r", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                out[(r["stock_id"], r["date"])] = float(r["close"]) * float(r["volume_lots"])
            except (ValueError, KeyError):
                bad += 1  # 已知資料不齊型態(空值列);計數不靜默
    if bad:
        logger.warning("load_turnover_map:跳過 %d 列無法解析的 daily rows", bad)
    return out


def run_pool_diagnose(
    data_dir: Path,
    out_dir: Path,
    cfg: FadeBacktestConfig,
    report_date: str,
    label_cutoff: str,
    watchlist_path: Path,
    report_dir: Path | None = None,
) -> Path:
    """CLI 協調:universe → bars → turnover → diagnose_pool_fade → JSON + 報告."""
    from copycat.backtest.fade_pipeline import build_fade_universe  # 延遲:避免與 pipeline 互import

    from copycat.data.store import read_bars
    from copycat.watchlist import load_watchlist

    samples, counts = build_fade_universe(data_dir, data_dir / "events" / "events.csv", cfg)
    samples_bars: list[tuple[FadeSample, list[Bar1K]]] = []
    for s in samples:
        bars = read_bars(data_dir, s.stock_id, s.t1_date)
        if bars:
            samples_bars.append((s, bars))
    turnover_map = load_turnover_map(data_dir)
    watchlist = load_watchlist(watchlist_path)

    result = diagnose_pool_fade(samples_bars, turnover_map, label_cutoff, cfg, watchlist.broker_ids)
    result["universe_counts"] = counts

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"pool_fade_{report_date}.json"
    tmp = json_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, json_path)

    report_path = out_dir / f"uc_pool_fade_{report_date}.md"
    write_pool_fade_report(result, cfg, report_date, report_path)
    if report_dir is not None:
        report_dir.mkdir(parents=True, exist_ok=True)
        write_pool_fade_report(result, cfg, report_date, report_dir / report_path.name)
    return report_path
