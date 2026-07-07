"""回測全參數(版本化;configs/*.json 覆寫)— 樣式同 strategy_config(spec §8/design D5-D6).

sim_config_hash 只涵蓋「影響模擬結果」的欄位子集;GA/搜索參數改動不作廢 outcome cache。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    # --- 宇宙 / 切分 ---
    theta_grid: tuple[float, ...] = (
        0.08,
        0.081,
        0.082,
        0.083,
        0.084,
        0.085,
        0.086,
        0.087,
        0.088,
        0.089,
        0.09,
    )
    anchor_thetas: tuple[float, ...] = (0.08,)
    split_date: str = "2026-03-01"  # train < split ≤ test
    near_miss_weight: float = 5.0
    min_prior_days: int = 21  # neigui daily_ctx 同源
    # --- 成本(D6 分軌)---
    fee_rate: float = 0.001425
    fee_discount: float = 0.0
    intraday_tax: float = 0.0015  # 現股當沖減半
    overnight_tax: float = 0.003
    slippage_ticks: int = 1
    stress_slippage_ticks: int = 2
    # --- 數值 ---
    float_eps: float = 1e-9  # 觸發判定
    limit_eps: float = 1e-6  # limit 比較(鎖死/留倉/unfillable/交叉)
    # --- 停損網格(design §5)---
    s1_stall_bars: tuple[int, ...] = (5, 10, 15, 20)
    s1_outer_max: tuple[float, ...] = (0.35, 0.45, 0.55, -1.0)  # -1 = 外盤比條件 off
    s1_outer_window: int = 10
    s2_swing_lookback: tuple[int, ...] = (5, 15, 30)
    s2_buffer: tuple[float, ...] = (0.0, 0.005)
    s3_trail: tuple[float, ...] = (0.015, 0.02, 0.03, 0.04)
    s4_fixed: tuple[float, ...] = (0.02, 0.03, 0.04, 0.05)
    t1300_variants: tuple[bool, ...] = (True, False)
    t1300_min_idx: int = 239  # 13:00 bar 索引
    # --- baseline 停損組(GA fitness 用,D10)---
    baseline_s2_lookback: int = 5
    baseline_s2_buffer: float = 0.0
    baseline_t1300: bool = True
    # --- GA / 搜索 ---
    ga_pop: int = 500
    ga_generations: int = 100
    ga_seeds: tuple[int, ...] = (1, 2, 3, 4, 5)
    ga_max_conditions: int = 4
    jaccard_max: float = 0.8
    support_weighted_min: float = 40.0
    support_raw_min: int = 20
    quantile_probs: tuple[float, ...] = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
    # --- regime(D5)---
    lowbase_dist_ma60_abs: float = 0.05
    lowbase_bb_pct: float = 0.20
    ignition_lookback: int = 20
    ignition_ret5_abs: float = 0.03
    ignition_days_since_limitup: int = 20
    ignition_touch_theta: float = 0.08
    # --- 驗證三道 ---
    plateau_neighbor_steps: tuple[int, ...] = (1, 2)
    plateau_min_frac: float = 0.4

    @classmethod
    def default(cls) -> BacktestConfig:
        return cls()


_TUPLE_KEYS = {
    "theta_grid",
    "anchor_thetas",
    "s1_stall_bars",
    "s1_outer_max",
    "s2_swing_lookback",
    "s2_buffer",
    "s3_trail",
    "s4_fixed",
    "t1300_variants",
    "ga_seeds",
    "quantile_probs",
    "plateau_neighbor_steps",
}

# 影響模擬結果的欄位(outcome cache 失效判準,design D3)
_SIM_FIELDS = (
    "fee_rate",
    "fee_discount",
    "intraday_tax",
    "overnight_tax",
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
    "t1300_variants",
    "t1300_min_idx",
    "min_prior_days",
)


def load_backtest_config(path: Path) -> BacktestConfig:
    payload: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    known = {f.name for f in fields(BacktestConfig)}
    unknown = set(payload) - known
    if unknown:
        raise ValueError(f"未知回測參數: {sorted(unknown)}")
    for key in _TUPLE_KEYS:
        if key in payload:
            value = payload[key]
            assert isinstance(value, list)
            payload[key] = tuple(value)
    return BacktestConfig(**payload)  # type: ignore[arg-type]


def sim_config_hash(cfg: BacktestConfig) -> str:
    payload = {name: getattr(cfg, name) for name in _SIM_FIELDS}
    blob = json.dumps(payload, sort_keys=True, default=list)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]
