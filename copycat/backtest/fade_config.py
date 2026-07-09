"""T+1 Fade 回測全參數(版本化;design.md v2 §5)— 空方當沖先賣.

兩階段 combo 產生:
1. enumerate_baseline_combos → 跑 train 排名取 S1 top-3
2. enumerate_fade_stop_combos(cfg, top3_s1) → 最終 4,640 組
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FadeStopCombo:
    s1_n: int | None
    s1_phi: float | None
    s2_m: int | None
    s2_buf: float | None
    s3_x: float | None
    s4_x: float | None
    s5_x: float | None
    t1300: bool

    @property
    def combo_id(self) -> str:
        return (
            f"s1={self.s1_n}/{self.s1_phi}|s2={self.s2_m}/{self.s2_buf}"
            f"|s3={self.s3_x}|s4={self.s4_x}|s5={self.s5_x}|t1300={self.t1300}"
        )


@dataclass(frozen=True, slots=True)
class FadeBacktestConfig:
    # --- 宇宙 ---
    fade_gap_min: float = 0.01
    fade_gap_max: float = 0.095
    split_date: str = "2026-03-01"
    min_prior_days: int = 21
    # --- 成本(當沖先賣)---
    fee_rate: float = 0.001425
    fee_discount: float = 0.0
    intraday_tax: float = 0.0015
    slippage_ticks: int = 1
    stress_slippage_ticks: int = 2
    # --- 數值 ---
    float_eps: float = 1e-9
    limit_eps: float = 1e-6
    # --- 停損網格(空方版,design §5)---
    s1_stall_bars: tuple[int, ...] = (3, 5, 7, 10, 12, 15, 20, 25, 30)
    s1_outer_max: tuple[float, ...] = (0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, -1.0)
    s1_outer_window: int = 10
    s2_swing_lookback: tuple[int, ...] = (3, 5, 8, 10, 15, 20, 30)
    s2_buffer: tuple[float, ...] = (0.0, 0.002, 0.005, 0.008, 0.010)
    s3_trail: tuple[float, ...] = (
        0.005,
        0.008,
        0.010,
        0.012,
        0.015,
        0.020,
        0.025,
        0.030,
        0.040,
        0.050,
    )
    s4_fixed: tuple[float, ...] = (
        0.010,
        0.015,
        0.020,
        0.025,
        0.030,
        0.035,
        0.040,
        0.050,
        0.060,
        0.070,
    )
    s5_target: tuple[float, ...] = (0.005, 0.008, 0.010, 0.015, 0.020, 0.025, 0.030, 0.040, 0.050)
    t1300_variants: tuple[bool, ...] = (True, False)
    t1300_min_idx: int = 239
    # --- baseline(用於 S1 top-3 排名)---
    baseline_t1300: bool = True
    # --- GA / 搜索 ---
    ga_pop: int = 800
    ga_generations: int = 200
    ga_seeds: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
    ga_max_conditions: int = 5
    jaccard_max: float = 0.8
    support_weighted_min: float = 30.0
    support_raw_min: int = 15
    quantile_probs: tuple[float, ...] = (
        0.05,
        0.10,
        0.15,
        0.20,
        0.25,
        0.30,
        0.35,
        0.40,
        0.45,
        0.50,
        0.55,
        0.60,
        0.65,
        0.70,
        0.75,
        0.80,
        0.85,
        0.90,
        0.95,
    )
    # --- 時間窗 ---
    max_window_grid: tuple[int, ...] = (10, 15, 20, 30, 45, 60, 90, 120)
    # --- 位階特徵(structural_features 需要,沿 BacktestConfig 預設)---
    lowbase_dist_ma60_abs: float = 0.05
    lowbase_bb_pct: float = 0.20
    ignition_lookback: int = 20
    ignition_ret5_abs: float = 0.03
    ignition_days_since_limitup: int = 20
    ignition_touch_theta: float = 0.08
    touchback_upper: float = 0.075
    touchback_lower: float = 0.07
    # --- 驗證三道 ---
    plateau_neighbor_steps: tuple[int, ...] = (1, 2)
    plateau_min_frac: float = 0.4
    # --- TP 停利網格(Phase B)---
    tp1_min_profit: tuple[float, ...] = (0.003, 0.005, 0.008, 0.01, 0.015, 0.02)
    tp1_z: tuple[float, ...] = (1.5, 2.0, 2.5, 3.0, 4.0, 5.0)
    tp1_lookback: tuple[int, ...] = (3, 5, 8, 10, 15)
    tp1_recovery: tuple[float, ...] = (0.3, 0.4, 0.5, 0.6, 0.7)
    tp2_trend_n: tuple[int, ...] = (3, 5, 8, 10)
    tp2_new_low_count: tuple[int, ...] = (2, 3, 4)
    tp2_z: tuple[float, ...] = (1.5, 2.0, 2.5, 3.0)
    tp2_inner_flip: tuple[float, ...] = (0.50, 0.55, 0.60, 0.65, 0.70)
    tp2_min_profit: tuple[float, ...] = (0.003, 0.005, 0.008)
    tp3_n: tuple[int, ...] = (3, 4, 5, 6, 8)
    tp3_decel: tuple[float, ...] = (0.3, 0.4, 0.5, 0.6, 0.7)
    tp3_min_profit: tuple[float, ...] = (0.003, 0.005, 0.008, 0.01)
    tp4_n: tuple[int, ...] = (3, 4, 5, 6, 7, 8, 10, 12, 15)
    tp4_min_profit: tuple[float, ...] = (0.003, 0.005, 0.008, 0.01, 0.015)
    tp5_fill: tuple[float, ...] = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
    tp6_dist: tuple[float, ...] = (0.005, 0.008, 0.01, 0.012, 0.015, 0.02, 0.025, 0.03)
    tp7_capture: tuple[float, ...] = (0.3, 0.4, 0.5, 0.6, 0.7, 0.8)
    tp8_n: tuple[int, ...] = (1, 2, 3, 4, 5)
    tp8_threshold: tuple[float, ...] = (0.50, 0.55, 0.60, 0.65, 0.70, 0.75)
    tp8_min_profit: tuple[float, ...] = (0.003, 0.005, 0.008)
    tp9_min_profit: tuple[float, ...] = (0.003, 0.005, 0.008, 0.01)
    tp10_wick: tuple[float, ...] = (0.5, 0.6, 0.7, 0.8)
    tp10_min_profit: tuple[float, ...] = (0.003, 0.005, 0.008, 0.01)
    tp11_initial: tuple[float, ...] = (0.01, 0.015, 0.02, 0.025, 0.03)
    tp11_decay: tuple[float, ...] = (0.95, 0.97, 0.98, 0.99)

    @classmethod
    def default(cls) -> FadeBacktestConfig:
        return cls()


def enumerate_baseline_combos(cfg: FadeBacktestConfig) -> list[FadeStopCombo]:
    """S1/S2/S3/S4 單族 baseline + 無停損 baseline(S5=off, t1300=baseline),用於 train 排名."""
    combos: list[FadeStopCombo] = []
    base = {"s5_x": None, "t1300": cfg.baseline_t1300}
    combos.append(
        FadeStopCombo(s1_n=None, s1_phi=None, s2_m=None, s2_buf=None, s3_x=None, s4_x=None, **base)
    )
    for n in cfg.s1_stall_bars:
        for phi in cfg.s1_outer_max:
            combos.append(
                FadeStopCombo(
                    s1_n=n, s1_phi=phi, s2_m=None, s2_buf=None, s3_x=None, s4_x=None, **base
                )
            )
    for m in cfg.s2_swing_lookback:
        for buf in cfg.s2_buffer:
            combos.append(
                FadeStopCombo(
                    s1_n=None, s1_phi=None, s2_m=m, s2_buf=buf, s3_x=None, s4_x=None, **base
                )
            )
    for x in cfg.s3_trail:
        combos.append(
            FadeStopCombo(s1_n=None, s1_phi=None, s2_m=None, s2_buf=None, s3_x=x, s4_x=None, **base)
        )
    for x in cfg.s4_fixed:
        combos.append(
            FadeStopCombo(s1_n=None, s1_phi=None, s2_m=None, s2_buf=None, s3_x=None, s4_x=x, **base)
        )
    return combos


def enumerate_fade_stop_combos(
    cfg: FadeBacktestConfig,
    top3_s1: list[tuple[int, float]],
) -> list[FadeStopCombo]:
    """最終停損網格:無停損 + 單族 + top3 S1×S2 疊加 × S5(on/off) × 13:00(on/off)."""
    bases: list[dict[str, object]] = [{}]
    for n in cfg.s1_stall_bars:
        for phi in cfg.s1_outer_max:
            bases.append({"s1_n": n, "s1_phi": phi})
    for m in cfg.s2_swing_lookback:
        for buf in cfg.s2_buffer:
            bases.append({"s2_m": m, "s2_buf": buf})
    for x in cfg.s3_trail:
        bases.append({"s3_x": x})
    for x in cfg.s4_fixed:
        bases.append({"s4_x": x})
    for s1_n, s1_phi in top3_s1:
        for m in cfg.s2_swing_lookback:
            for buf in cfg.s2_buffer:
                bases.append({"s1_n": s1_n, "s1_phi": s1_phi, "s2_m": m, "s2_buf": buf})

    combos: list[FadeStopCombo] = []
    for t13 in cfg.t1300_variants:
        for s5 in (None, *cfg.s5_target):
            for base in bases:
                combos.append(
                    FadeStopCombo(
                        s1_n=base.get("s1_n"),  # type: ignore[arg-type]
                        s1_phi=base.get("s1_phi"),  # type: ignore[arg-type]
                        s2_m=base.get("s2_m"),  # type: ignore[arg-type]
                        s2_buf=base.get("s2_buf"),  # type: ignore[arg-type]
                        s3_x=base.get("s3_x"),  # type: ignore[arg-type]
                        s4_x=base.get("s4_x"),  # type: ignore[arg-type]
                        s5_x=s5,
                        t1300=t13,
                    )
                )
    return combos


_TUPLE_KEYS = {
    "s1_stall_bars",
    "s1_outer_max",
    "s2_swing_lookback",
    "s2_buffer",
    "s3_trail",
    "s4_fixed",
    "s5_target",
    "t1300_variants",
    "ga_seeds",
    "quantile_probs",
    "max_window_grid",
    "plateau_neighbor_steps",
    "tp1_min_profit",
    "tp1_z",
    "tp1_lookback",
    "tp1_recovery",
    "tp2_trend_n",
    "tp2_new_low_count",
    "tp2_z",
    "tp2_inner_flip",
    "tp2_min_profit",
    "tp3_n",
    "tp3_decel",
    "tp3_min_profit",
    "tp4_n",
    "tp4_min_profit",
    "tp5_fill",
    "tp6_dist",
    "tp7_capture",
    "tp8_n",
    "tp8_threshold",
    "tp8_min_profit",
    "tp9_min_profit",
    "tp10_wick",
    "tp10_min_profit",
    "tp11_initial",
    "tp11_decay",
}

_SIM_FIELDS = (
    "fee_rate",
    "fee_discount",
    "intraday_tax",
    "slippage_ticks",
    "stress_slippage_ticks",
    "float_eps",
    "limit_eps",
    "s1_stall_bars",
    "s1_outer_max",
    "s1_outer_window",
    "s2_swing_lookback",
    "s2_buffer",
    "s3_trail",
    "s4_fixed",
    "s5_target",
    "t1300_variants",
    "t1300_min_idx",
    "min_prior_days",
    "tp1_min_profit",
    "tp1_z",
    "tp1_lookback",
    "tp1_recovery",
    "tp2_trend_n",
    "tp2_new_low_count",
    "tp2_z",
    "tp2_inner_flip",
    "tp2_min_profit",
    "tp3_n",
    "tp3_decel",
    "tp3_min_profit",
    "tp4_n",
    "tp4_min_profit",
    "tp5_fill",
    "tp6_dist",
    "tp7_capture",
    "tp8_n",
    "tp8_threshold",
    "tp8_min_profit",
    "tp9_min_profit",
    "tp10_wick",
    "tp10_min_profit",
    "tp11_initial",
    "tp11_decay",
)


def load_fade_config(path: Path) -> FadeBacktestConfig:
    payload: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    known = {f.name for f in fields(FadeBacktestConfig)}
    unknown = set(payload) - known
    if unknown:
        raise ValueError(f"未知回測參數: {sorted(unknown)}")
    for key in _TUPLE_KEYS:
        if key in payload:
            value = payload[key]
            assert isinstance(value, list)
            payload[key] = tuple(value)
    return FadeBacktestConfig(**payload)  # type: ignore[arg-type]


def fade_sim_config_hash(cfg: FadeBacktestConfig) -> str:
    payload = {name: getattr(cfg, name) for name in _SIM_FIELDS}
    blob = json.dumps(payload, sort_keys=True, default=list)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True, slots=True)
class FadeTakeProfitCombo:
    tp_type: str | None
    params: tuple[tuple[str, float], ...]

    @property
    def tp_id(self) -> str:
        if self.tp_type is None:
            return "tp=None"
        parts = "|".join(f"{k}={v}" for k, v in self.params)
        return f"tp={self.tp_type}|{parts}" if parts else f"tp={self.tp_type}"

    def get(self, key: str) -> float:
        for k, v in self.params:
            if k == key:
                return v
        raise KeyError(key)


def _tp(tp_type: str, **kwargs: float) -> FadeTakeProfitCombo:
    return FadeTakeProfitCombo(tp_type, tuple(sorted(kwargs.items())))


def enumerate_tp_combos(cfg: FadeBacktestConfig) -> list[FadeTakeProfitCombo]:
    """全 TP 網格:None + S5 + TP1-TP11."""
    combos: list[FadeTakeProfitCombo] = [FadeTakeProfitCombo(None, ())]
    for x in cfg.s5_target:
        combos.append(_tp("s5", s5_x=x))
    for mp in cfg.tp1_min_profit:
        for z in cfg.tp1_z:
            for lb in cfg.tp1_lookback:
                for rc in cfg.tp1_recovery:
                    combos.append(_tp("tp1", min_profit=mp, z=z, lookback=float(lb), recovery=rc))
    for tn in cfg.tp2_trend_n:
        for nlc in cfg.tp2_new_low_count:
            for z in cfg.tp2_z:
                for ifl in cfg.tp2_inner_flip:
                    for mp in cfg.tp2_min_profit:
                        combos.append(
                            _tp(
                                "tp2",
                                trend_n=float(tn),
                                new_low_count=float(nlc),
                                z=z,
                                inner_flip=ifl,
                                min_profit=mp,
                            )
                        )
    for n in cfg.tp3_n:
        for d in cfg.tp3_decel:
            for mp in cfg.tp3_min_profit:
                combos.append(_tp("tp3", n=float(n), decel=d, min_profit=mp))
    for n in cfg.tp4_n:
        for mp in cfg.tp4_min_profit:
            combos.append(_tp("tp4", n=float(n), min_profit=mp))
    for f in cfg.tp5_fill:
        combos.append(_tp("tp5", fill_pct=f))
    for d in cfg.tp6_dist:
        combos.append(_tp("tp6", distance=d))
    for c in cfg.tp7_capture:
        combos.append(_tp("tp7", capture=c))
    for n in cfg.tp8_n:
        for t in cfg.tp8_threshold:
            for mp in cfg.tp8_min_profit:
                combos.append(_tp("tp8", n=float(n), threshold=t, min_profit=mp))
    for mp in cfg.tp9_min_profit:
        combos.append(_tp("tp9", min_profit=mp))
    for w in cfg.tp10_wick:
        for mp in cfg.tp10_min_profit:
            combos.append(_tp("tp10", wick=w, min_profit=mp))
    for ini in cfg.tp11_initial:
        for dc in cfg.tp11_decay:
            combos.append(_tp("tp11", initial=ini, decay=dc))
    return combos
