"""Phase B 停損/停利對決 + 滑價壓測(兩階段搜索)."""

from __future__ import annotations

import logging
from dataclasses import asdict

from copycat.backtest.fade_config import (
    FadeBacktestConfig,
    FadeStopCombo,
    FadeTakeProfitCombo,
)
from copycat.backtest.fade_simulate import (
    FadeSample,
    simulate_fade_sample,
    simulate_fade_with_tp,
)
from copycat.backtest.search import apply_rule, bit_indices
from copycat.backtest.stats import Trade, max_drawdown, weighted_stats
from copycat.data.models import Bar1K

logger = logging.getLogger(__name__)

_TRADEABLE = {"stopped", "target_hit", "time_1300", "closeout", "locked_at_limit"}


def _test_indices(
    mask: int,
    all_dates: list[str],
    split_date: str,
    is_train: bool,
) -> list[int]:
    indices = bit_indices(mask)
    if is_train:
        return [i for i in indices if all_dates[i] < split_date]
    return [i for i in indices if all_dates[i] >= split_date]


def _eval_combo(
    indices: list[int],
    tradeable_samples: list[tuple[FadeSample, list[Bar1K], int]],
    combo: FadeStopCombo,
    tp: FadeTakeProfitCombo | None,
    cfg: FadeBacktestConfig,
    slippage: int,
) -> dict[str, float | int | None]:
    trades: list[Trade] = []
    lock_count = 0
    for i in indices:
        sample, bars, trig_idx = tradeable_samples[i]
        if tp is not None:
            out = simulate_fade_with_tp(bars, trig_idx, sample, combo, tp, cfg, slippage)
        else:
            out = simulate_fade_sample(bars, trig_idx, sample, combo, cfg, slippage)
        if out.status in _TRADEABLE and out.pnl_rate is not None:
            trades.append(Trade(date=sample.t1_date, stock_id=sample.stock_id, pnl=out.pnl_rate))
        if out.status == "locked_at_limit":
            lock_count += 1
    if not trades:
        return {
            "expectancy": None,
            "p_win": None,
            "payoff": None,
            "n": 0,
            "mdd": 0.0,
            "lock_pct": 0.0,
        }
    stats = weighted_stats(trades)
    mdd = max_drawdown(trades)
    lock_pct = lock_count / len(indices) if indices else 0.0
    return {
        "expectancy": stats.get("expectancy"),
        "p_win": stats.get("p_win"),
        "payoff": stats.get("payoff"),
        "n": stats.get("n_raw"),
        "mdd": mdd,
        "lock_pct": lock_pct,
    }


def optimize_rule_stops(
    tradeable_samples: list[tuple[FadeSample, list[Bar1K], int]],
    rules: list[dict[str, object]],
    all_combos: list[FadeStopCombo],
    all_feat: list[dict[str, float | None]],
    all_dates: list[str],
    cfg: FadeBacktestConfig,
) -> None:
    """Stage 1: train set 上找每條規則的最佳停損。就地擴充 rule dict。"""
    for ri, rule in enumerate(rules):
        conds = rule["conditions"]
        assert isinstance(conds, list)
        mask = apply_rule(conds, all_feat)
        train_idx = _test_indices(mask, all_dates, cfg.split_date, is_train=True)
        if not train_idx:
            rule["best_stop"] = None
            rule["best_stop_params"] = None
            continue

        best_exp = -1e18
        best_combo = all_combos[0]
        for combo in all_combos:
            ev = _eval_combo(train_idx, tradeable_samples, combo, None, cfg, cfg.slippage_ticks)
            exp = ev.get("expectancy")
            if exp is not None and exp > best_exp:
                best_exp = exp
                best_combo = combo

        rule["best_stop"] = best_combo.combo_id
        rule["best_stop_params"] = asdict(best_combo)
        logger.info(
            "rule %d/%d: best_stop=%s train_exp=%.4f",
            ri + 1,
            len(rules),
            best_combo.combo_id,
            best_exp,
        )


def _strip_s5(combo: FadeStopCombo) -> FadeStopCombo:
    if combo.s5_x is None:
        return combo
    return FadeStopCombo(
        s1_n=combo.s1_n,
        s1_phi=combo.s1_phi,
        s2_m=combo.s2_m,
        s2_buf=combo.s2_buf,
        s3_x=combo.s3_x,
        s4_x=combo.s4_x,
        s5_x=None,
        t1300=combo.t1300,
    )


def _rebuild_combo(params: dict[str, object]) -> FadeStopCombo:
    return FadeStopCombo(
        s1_n=params.get("s1_n"),  # type: ignore[arg-type]
        s1_phi=params.get("s1_phi"),  # type: ignore[arg-type]
        s2_m=params.get("s2_m"),  # type: ignore[arg-type]
        s2_buf=params.get("s2_buf"),  # type: ignore[arg-type]
        s3_x=params.get("s3_x"),  # type: ignore[arg-type]
        s4_x=params.get("s4_x"),  # type: ignore[arg-type]
        s5_x=params.get("s5_x"),  # type: ignore[arg-type]
        t1300=bool(params.get("t1300", True)),
    )


def optimize_rule_tp(
    tradeable_samples: list[tuple[FadeSample, list[Bar1K], int]],
    rules: list[dict[str, object]],
    tp_combos: list[FadeTakeProfitCombo],
    all_feat: list[dict[str, float | None]],
    all_dates: list[str],
    cfg: FadeBacktestConfig,
) -> None:
    """Stage 2 + 3: train 上找最佳 TP,test 上驗證 + 壓測。就地擴充 rule dict。"""
    for ri, rule in enumerate(rules):
        stop_params = rule.get("best_stop_params")
        if stop_params is None:
            rule["best_tp"] = None
            rule["best_tp_params"] = None
            rule["best_test_expectancy"] = None
            rule["stress_passed"] = False
            rule["stress_expectancy"] = None
            continue

        assert isinstance(stop_params, dict)
        best_stop = _strip_s5(_rebuild_combo(stop_params))

        conds = rule["conditions"]
        assert isinstance(conds, list)
        mask = apply_rule(conds, all_feat)
        train_idx = _test_indices(mask, all_dates, cfg.split_date, is_train=True)
        test_idx = _test_indices(mask, all_dates, cfg.split_date, is_train=False)

        best_tp_exp = -1e18
        best_tp = tp_combos[0]
        for tp in tp_combos:
            if not train_idx:
                break
            ev = _eval_combo(train_idx, tradeable_samples, best_stop, tp, cfg, cfg.slippage_ticks)
            exp = ev.get("expectancy")
            if exp is not None and exp > best_tp_exp:
                best_tp_exp = exp
                best_tp = tp

        rule["best_tp"] = best_tp.tp_id
        rule["best_tp_params"] = {"tp_type": best_tp.tp_type, "params": dict(best_tp.params)}

        if test_idx:
            test_ev = _eval_combo(
                test_idx, tradeable_samples, best_stop, best_tp, cfg, cfg.slippage_ticks
            )
            rule["best_test_expectancy"] = test_ev.get("expectancy")
            rule["best_test_p_win"] = test_ev.get("p_win")
            rule["best_test_payoff"] = test_ev.get("payoff")
            rule["best_test_mdd"] = test_ev.get("mdd")
            rule["best_test_n"] = test_ev.get("n")
            rule["best_lock_pct"] = test_ev.get("lock_pct")

            stop_only_ev = _eval_combo(
                test_idx, tradeable_samples, best_stop, None, cfg, cfg.slippage_ticks
            )
            rule["stop_only_expectancy"] = stop_only_ev.get("expectancy")

            stress_ev = _eval_combo(
                test_idx, tradeable_samples, best_stop, best_tp, cfg, cfg.stress_slippage_ticks
            )
            stress_exp = stress_ev.get("expectancy")
            rule["stress_expectancy"] = stress_exp
            rule["stress_passed"] = stress_exp is not None and stress_exp > 0
        else:
            rule["best_test_expectancy"] = None
            rule["best_test_p_win"] = None
            rule["best_test_payoff"] = None
            rule["best_test_mdd"] = None
            rule["best_test_n"] = 0
            rule["best_lock_pct"] = None
            rule["stop_only_expectancy"] = None
            rule["stress_expectancy"] = None
            rule["stress_passed"] = False

        logger.info(
            "rule %d/%d: best_tp=%s test_exp=%s stress=%s",
            ri + 1,
            len(rules),
            best_tp.tp_id,
            rule.get("best_test_expectancy"),
            rule.get("stress_passed"),
        )


def build_cross_arm_table(
    all_results: list[dict[str, object]],
) -> list[dict[str, object]]:
    """7 臂 top-1 rule 橫向比較表(best_test_expectancy DESC)."""
    rows: list[dict[str, object]] = []
    for result in all_results:
        rules = result.get("rules")
        if not isinstance(rules, list) or not rules:
            continue
        best_rule = None
        best_exp = -1e18
        for rule in rules:
            exp = rule.get("best_test_expectancy")
            if isinstance(exp, float | int) and exp > best_exp:
                best_exp = float(exp)
                best_rule = rule
        if best_rule is None:
            continue
        rows.append(
            {
                "arm": result.get("arm", "?"),
                "param": result.get("param", {}),
                "test_exp": best_rule.get("best_test_expectancy"),
                "stress_exp": best_rule.get("stress_expectancy"),
                "p_win": best_rule.get("best_test_p_win"),
                "payoff": best_rule.get("best_test_payoff"),
                "mdd": best_rule.get("best_test_mdd"),
                "lock_pct": best_rule.get("best_lock_pct"),
                "stress_passed": best_rule.get("stress_passed"),
                "best_stop": best_rule.get("best_stop"),
                "best_tp": best_rule.get("best_tp"),
                "n_test": best_rule.get("best_test_n"),
            }
        )

    def _sort_key(r: dict[str, object]) -> tuple[float, float]:
        te = r.get("test_exp")
        md = r.get("mdd")
        return (
            -float(te if isinstance(te, float | int) else -1e18),
            float(md if isinstance(md, float | int) else 0),
        )

    rows.sort(key=_sort_key)
    for i, row in enumerate(rows):
        row["rank"] = i + 1
    return rows
