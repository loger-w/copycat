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
    # --- 驗證三道 ---
    plateau_neighbor_steps: tuple[int, ...] = (1, 2)
    plateau_min_frac: float = 0.4

    @classmethod
    def default(cls) -> FadeBacktestConfig:
        return cls()


def enumerate_baseline_combos(cfg: FadeBacktestConfig) -> list[FadeStopCombo]:
    """S1/S2/S3/S4 單族 baseline(S5=off, t1300=baseline),用於 train 排名."""
    combos: list[FadeStopCombo] = []
    base = {"s5_x": None, "t1300": cfg.baseline_t1300}
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
    """最終停損網格:單族 + top3 S1×S2 疊加 × S5(on/off) × 13:00(on/off)."""
    bases: list[dict[str, object]] = []
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
