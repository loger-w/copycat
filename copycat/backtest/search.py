"""規則搜索(design D4/D10/D13)— 謂詞 bitmask、窮舉 1-2 條件、GA、Jaccard 去重.

規則一律物化為 (feature, threshold, op) 凍結形式;跨 θ 評估用 apply_rule 套凍結數值,
不重算分位數。隨機性只來自 random.Random(seed)(D11)。
"""

from __future__ import annotations

import json
import logging
import math
import random
from dataclasses import dataclass

from copycat.backtest.config import BacktestConfig

logger = logging.getLogger(__name__)

Row = dict[str, float | None]
Condition = dict[str, object]  # {"feature": str, "threshold": float, "op": ">=" | "<="}

_PENALTY = -1e9  # 支持不足的 fitness 罰底


@dataclass(frozen=True, slots=True)
class Predicate:
    feature: str
    threshold: float
    ge: bool
    mask: int


def _quantile(sorted_vals: list[float], p: float) -> float:
    """Nearest-rank 分位數(deterministic)."""
    idx = min(len(sorted_vals) - 1, max(0, math.ceil(p * len(sorted_vals)) - 1))
    return sorted_vals[idx]


def _pred_mask(rows: list[Row], feature: str, threshold: float, ge: bool) -> int:
    mask = 0
    for i, r in enumerate(rows):
        v = r.get(feature)
        if v is None:
            continue
        if (ge and v >= threshold) or (not ge and v <= threshold):
            mask |= 1 << i
    return mask


def build_predicates(
    rows: list[Row], feature_names: list[str], probs: tuple[float, ...]
) -> list[Predicate]:
    """per-regime train 子集分位數 → 謂詞庫;None 值不命中任何謂詞."""
    preds: list[Predicate] = []
    for feat in feature_names:
        vals = sorted(v for r in rows if (v := r.get(feat)) is not None)
        if len(vals) < 2:
            continue
        for thr in sorted({_quantile(vals, p) for p in probs}):
            for ge in (True, False):
                preds.append(Predicate(feat, thr, ge, _pred_mask(rows, feat, thr, ge)))
    return preds


def _to_conditions(rule: tuple[Predicate, ...]) -> list[Condition]:
    conds: list[Condition] = [
        {"feature": p.feature, "threshold": p.threshold, "op": ">=" if p.ge else "<="} for p in rule
    ]
    conds.sort(key=lambda c: (str(c["feature"]), str(c["op"]), float(c["threshold"])))  # type: ignore[arg-type]
    return conds


def apply_rule(conditions: list[Condition], rows: list[Row]) -> int:
    """凍結門檻套任意 features 表(跨 θ 評估;D13)."""
    mask = (1 << len(rows)) - 1
    for c in conditions:
        mask &= _pred_mask(rows, str(c["feature"]), float(c["threshold"]), c["op"] == ">=")  # type: ignore[arg-type]
    return mask


def bit_indices(mask: int) -> list[int]:
    """bitmask → set-bit index list(pipeline 共用,勿另行實作)."""
    out = []
    while mask:
        lsb = mask & -mask
        out.append(lsb.bit_length() - 1)
        mask ^= lsb
    return out


_bit_indices = bit_indices  # 內部舊名沿用


def _evaluate(
    mask: int, pnl: list[float], weights: list[float], cfg: BacktestConfig
) -> tuple[float, float, int, float]:
    """回 (fitness, expectancy, support_raw, support_weighted);支持不足 → 罰底."""
    raw = 0
    wsum = 0.0
    acc = 0.0
    for i in _bit_indices(mask):
        w = weights[i]
        if w <= 0:
            continue
        raw += 1
        wsum += w
        acc += pnl[i] * w
    if raw < cfg.support_raw_min or wsum < cfg.support_weighted_min or wsum == 0:
        return (_PENALTY + raw, 0.0, raw, wsum)
    exp = acc / wsum
    return (exp, exp, raw, wsum)


def _entry(
    rule: tuple[Predicate, ...], pnl: list[float], weights: list[float], cfg: BacktestConfig
) -> dict[str, object]:
    if not rule:
        raise ValueError("規則至少需要一個謂詞(空規則的全樣本 mask 無法由謂詞推得)")
    mask = rule[0].mask
    for p in rule[1:]:
        mask &= p.mask
    fitness, exp, raw, wsum = _evaluate(mask, pnl, weights, cfg)
    return {
        "conditions": _to_conditions(rule),
        "fitness": fitness,
        "expectancy_train": exp,
        "support_raw": raw,
        "support_weighted": wsum,
        "mask": mask,
    }


def rule_fitness(e: dict[str, object]) -> float:
    v = e["fitness"]
    assert isinstance(v, float | int)
    return float(v)


def rule_sort_key(e: dict[str, object]) -> tuple[float, str]:
    return (-rule_fitness(e), json.dumps(e["conditions"], sort_keys=True))


def exhaustive_scan(
    predicates: list[Predicate],
    pnl: list[float],
    weights: list[float],
    cfg: BacktestConfig,
    top_n: int = 200,
) -> list[dict[str, object]]:
    """1-2 條件全掃;只回支持達標者,fitness 排序(tie-break 用條件序列化)."""
    seen: set[tuple[int, ...]] = set()
    out: list[dict[str, object]] = []

    def _try(rule: tuple[Predicate, ...], key: tuple[int, ...]) -> None:
        if key in seen:
            return
        seen.add(key)
        e = _entry(rule, pnl, weights, cfg)
        if rule_fitness(e) > _PENALTY + len(pnl):  # 支持達標
            out.append(e)

    for i, p in enumerate(predicates):
        _try((p,), (i,))
    for i in range(len(predicates)):
        for j in range(i + 1, len(predicates)):
            _try((predicates[i], predicates[j]), (i, j))
    out.sort(key=rule_sort_key)
    return out[:top_n]


def ga_search(
    predicates: list[Predicate],
    pnl: list[float],
    weights: list[float],
    cfg: BacktestConfig,
    seed: int,
    top_n: int = 20,
) -> list[dict[str, object]]:
    """GA(tournament + 交配 + 突變,elite 保留);同 seed 重跑結果 byte-identical."""
    rng = random.Random(seed)
    n_preds = len(predicates)
    if n_preds == 0:
        return []
    cache: dict[tuple[int, ...], float] = {}

    def _fit(rule_idx: tuple[int, ...]) -> float:
        if rule_idx not in cache:
            e = _entry(tuple(predicates[i] for i in rule_idx), pnl, weights, cfg)
            cache[rule_idx] = rule_fitness(e)
        return cache[rule_idx]

    def _new_rule() -> tuple[int, ...]:
        size = rng.randint(1, min(cfg.ga_max_conditions, n_preds))
        return tuple(sorted(rng.sample(range(n_preds), size)))

    def _tournament(pop: list[tuple[int, ...]]) -> tuple[int, ...]:
        a, b = rng.randrange(len(pop)), rng.randrange(len(pop))
        ra, rb = pop[a], pop[b]
        return ra if (_fit(ra), ra) >= (_fit(rb), rb) else rb

    pop = [_new_rule() for _ in range(cfg.ga_pop)]
    elite_n = max(2, cfg.ga_pop // 10)
    for _ in range(cfg.ga_generations):
        pop.sort(key=lambda r: (-_fit(r), r))
        new_pop = pop[:elite_n]
        while len(new_pop) < cfg.ga_pop:
            a, b = _tournament(pop), _tournament(pop)
            union = sorted(set(a) | set(b))
            size = rng.randint(1, min(cfg.ga_max_conditions, len(union)))
            child = tuple(sorted(rng.sample(union, size)))
            if rng.random() < 0.3:  # 突變:換一個謂詞
                mutable = list(child)
                mutable[rng.randrange(len(mutable))] = rng.randrange(n_preds)
                child = tuple(sorted(set(mutable)))
            new_pop.append(child)
        pop = new_pop
    pop.sort(key=lambda r: (-_fit(r), r))
    out: list[dict[str, object]] = []
    seen_masks: set[int] = set()
    for rule_idx in pop:
        if _fit(rule_idx) <= _PENALTY + len(pnl):
            continue
        e = _entry(tuple(predicates[i] for i in rule_idx), pnl, weights, cfg)
        if int(e["mask"]) in seen_masks:  # type: ignore[call-overload]
            continue
        seen_masks.add(int(e["mask"]))  # type: ignore[call-overload]
        out.append(e)
        if len(out) >= top_n:
            break
    return out


def jaccard_dedupe(items: list[dict[str, object]], max_j: float) -> list[dict[str, object]]:
    """依輸入順序(caller 先按 fitness 排)貪婪保留;hit-set Jaccard > max_j 淘汰."""
    kept: list[dict[str, object]] = []
    for item in items:
        mask = int(item["mask"])  # type: ignore[call-overload]
        dup = False
        for k in kept:
            km = int(k["mask"])  # type: ignore[call-overload]
            union = (mask | km).bit_count()
            if union and (mask & km).bit_count() / union > max_j:
                dup = True
                break
        if not dup:
            kept.append(item)
    return kept
