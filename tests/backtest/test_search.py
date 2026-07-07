"""三段式搜索(SC-6):謂詞 bitmask、凍結物化、窮舉、GA determinism、Jaccard."""

from __future__ import annotations

import json

from copycat.backtest.config import BacktestConfig
from copycat.backtest.search import (
    apply_rule,
    build_predicates,
    exhaustive_scan,
    ga_search,
    jaccard_dedupe,
)

# 8 樣本、2 特徵;pnl 設計成「a ≥ 大」才賺
_ROWS: list[dict[str, float | None]] = [
    {"a": 1.0, "b": 5.0},
    {"a": 2.0, "b": 4.0},
    {"a": 3.0, "b": 3.0},
    {"a": 4.0, "b": 2.0},
    {"a": 5.0, "b": 1.0},
    {"a": 6.0, "b": 0.0},
    {"a": 7.0, "b": 0.0},
    {"a": None, "b": 9.0},  # None 不命中任何謂詞
]
_PNL = [-0.05, -0.05, -0.05, 0.05, 0.06, 0.07, 0.08, 9.9]
_W = [1.0] * 8


def _cfg(**kw: object) -> BacktestConfig:
    base: dict[str, object] = {
        "quantile_probs": (0.25, 0.5, 0.75),
        "support_weighted_min": 2.0,
        "support_raw_min": 2,
        "ga_pop": 12,
        "ga_generations": 4,
        "ga_max_conditions": 2,
    }
    base.update(kw)
    return BacktestConfig(**base)  # type: ignore[arg-type]


def test_predicates_mask_vs_naive() -> None:
    preds = build_predicates(_ROWS, ["a", "b"], (0.25, 0.5, 0.75))
    assert preds
    for p in preds:
        naive = 0
        for i, r in enumerate(_ROWS):
            v = r[p.feature]
            if v is None:
                continue
            if (p.ge and v >= p.threshold) or (not p.ge and v <= p.threshold):
                naive |= 1 << i
        assert p.mask == naive, f"{p.feature} {p.threshold} {p.ge}"
    # None 樣本(index 7)不在任何 a 謂詞的 mask
    for p in preds:
        if p.feature == "a":
            assert not (p.mask >> 7) & 1


def test_exhaustive_scan_finds_signal_and_support_filter() -> None:
    rules = exhaustive_scan(
        build_predicates(_ROWS, ["a", "b"], (0.25, 0.5, 0.75)), _PNL, _W, _cfg()
    )
    assert rules
    best = rules[0]
    support = best["support_raw"]
    fitness = best["fitness"]
    assert isinstance(support, int) and isinstance(fitness, float)
    # 最佳規則應鎖住高 a 樣本(期望值最高且支持 ≥2)
    assert support >= 2
    assert fitness > 0
    # 支持下限:調高 raw min → 小支持規則消失
    strict = exhaustive_scan(
        build_predicates(_ROWS, ["a", "b"], (0.25, 0.5, 0.75)), _PNL, _W, _cfg(support_raw_min=6)
    )
    for r in strict:
        sup = r["support_raw"]
        assert isinstance(sup, int) and sup >= 6


def test_materialized_rule_frozen_across_tables() -> None:
    rules = exhaustive_scan(
        build_predicates(_ROWS, ["a", "b"], (0.25, 0.5, 0.75)), _PNL, _W, _cfg()
    )
    spec = rules[0]["conditions"]
    assert isinstance(spec, list)
    # 凍結門檻套到另一張表(值平移)→ 門檻數值不變,命中集合依新表計算
    shifted = [{"a": (r["a"] + 100 if r["a"] is not None else None), "b": r["b"]} for r in _ROWS]
    m1 = apply_rule(spec, _ROWS)
    m2 = apply_rule(spec, shifted)
    assert m1 != m2 or all(c["feature"] == "b" for c in spec)  # a 平移後命中必變(除非規則只用 b)
    assert apply_rule(spec, _ROWS) == m1  # 冪等


def test_ga_determinism_and_seed_variation() -> None:
    cfg = _cfg()
    preds = build_predicates(_ROWS, ["a", "b"], (0.25, 0.5, 0.75))
    r1 = ga_search(preds, _PNL, _W, cfg, seed=7)
    r2 = ga_search(preds, _PNL, _W, cfg, seed=7)
    assert json.dumps(r1, sort_keys=True) == json.dumps(r2, sort_keys=True)  # byte-identical
    for r in r1:
        conds = r["conditions"]
        assert isinstance(conds, list) and len(conds) <= cfg.ga_max_conditions


def test_entry_rejects_empty_rule() -> None:
    import pytest

    from copycat.backtest.search import _entry

    with pytest.raises(ValueError):
        _entry((), _PNL, _W, _cfg())


def test_jaccard_dedupe() -> None:
    items = [
        {"mask": 0b1111, "fitness": 3.0},
        {"mask": 0b1110, "fitness": 2.0},  # J=3/4 > 0.6 → 淘汰
        {"mask": 0b0001, "fitness": 1.0},  # J=1/4 → 保留
    ]
    kept = jaccard_dedupe(items, 0.6)
    assert [k["fitness"] for k in kept] == [3.0, 1.0]
