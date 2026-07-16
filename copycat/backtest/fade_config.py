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
    # --- 強制風控(round 1;None = 停用 = 舊行為)---
    guard_limit_dist: float | None = None  # 距漲停 x 強制回補(防鎖 guard)
    disaster_x: float | None = None  # 災難停損 entry×(1+x),獨立於 combo 永遠生效
    lock_penalty: float | None = None  # 全日鎖死回補 = 漲停×(1+p)(悲觀化)
    guard_dist_grid: tuple[float, ...] = (0.02, 0.03, 0.04)  # 敏感度診斷(不入選擇)
    # --- round 3:回落式災難停損(兩欄同設才啟用;與 disaster_x 互斥)---
    disaster_arm_x: float | None = None  # 武裝深度 D:prev_high ≥ entry×(1+D)
    disaster_retrace_r: float | None = None  # 回落確認 r:bar.low ≤ prev_high×(1−r)
    # --- round 3:結構停損 b 候選 + 貼板線 + 底倉臂(cells 層;空/False = round 2 形狀)---
    struct_stop_buffers: tuple[float, ...] = ()
    cell_b_gap_max: float | None = None  # cell_b 獨立宇宙上限(None = 沿 fade_gap_max)
    base_arm: bool = False
    base_arm_gap_edges: tuple[float, ...] = (0.01, 0.03, 0.055, 0.075)
    forward_start: str = "2026-07-11"  # SC-7 考場切分日
    # --- round 4:劇本結構化出場(prereg 2026-07-16;None/空 = round 3 行為)---
    inner_flip_phi_grid: tuple[float, ...] = ()  # cells 層 φ 變體(主值 + 敏感度次值)
    inner_flip_min_bars: int = 15  # 累計比最短觀察(b.m 分鐘索引口徑,15 = 09:16 起)
    tp_flush_z: float | None = None  # 出量殺:量 > 前 lookback 均量 z 倍
    tp_flush_lookback: int | None = None
    tp_flush_recovery: float | None = None  # 長下影收回比例
    tp_flush_min_profit: float | None = None  # 毛利 gate(1 − close/entry)
    tp_hl_k: int | None = None  # 墊高:連續 k 對 pivot 確認
    tp_hl_min_profit: float | None = None
    # --- walk-forward(空 = 舊單 split 路徑)---
    wf_test_starts: tuple[str, ...] = ()
    wf_test_months: int = 2
    wf_val_frac: float = 0.25
    wf_top_rules: int = 5
    # --- 報告 ---
    min_n_test: int = 15
    # --- 宇宙 ---
    universe_daytrade_filter: bool = False
    # --- round 2:壓測變體(SC-6;影響模擬 → 入 _SIM_FIELDS)---
    stress_guard_fill_high: bool = False  # guard/disaster/fixed_stop 成交 = max(level, bar.high)
    # --- round 2:三池複驗(SC-3;不影響 fade-search 模擬)---
    lock_penalty_grid: tuple[float, ...] = ()  # 鎖死懲罰敏感度(診斷用)
    diagnose_perm_iters: int = 5000
    diagnose_perm_seed: int = 42
    diagnose_min_edge_pp: float = 0.003  # 判定式 (ii) tiger−對照 差值門檻
    diagnose_p_threshold: float = 0.05  # 判定式 (i)/(ii) 顯著門檻
    # --- round 2:劇本格子 pre-registration(SC-4;不影響 fade-search 模擬)---
    cell_a_pullback_x: float = 0.008
    cell_a_headroom_min: float = 0.04
    cell_a_inner_thresholds: tuple[float, ...] = (0.45, 0.55)
    cell_a_window_m: int = 60
    cell_a_min_rally: float = 0.01
    cell_b_approach_dists: tuple[float, ...] = (0.02, 0.03)
    cell_b_fail_confirm: float = 0.01
    cell_b_stop_buffer: float = 0.005
    cell_c_rally_pcts: tuple[float, ...] = (0.03, 0.05)
    cell_c_pullback_x: float = 0.008
    cells_eval_segments: int = 4
    d5_min_ev: float = 0.01
    d5_min_n: int = 80
    d5_min_positive_segments: int = 3
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


# 無停損、持有到收盤(t1300 off)— diagnose/cells 無條件模擬共用(單一定義防漂移)
NO_STOP_HOLD_COMBO = FadeStopCombo(
    s1_n=None, s1_phi=None, s2_m=None, s2_buf=None, s3_x=None, s4_x=None, s5_x=None, t1300=False
)


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
                combos.append(_combo_from_base(base, s5_x=s5, t1300=t13))
    return combos


def _combo_from_base(base: dict[str, object], **overrides: object) -> FadeStopCombo:
    """dict 基底 + 覆寫 → FadeStopCombo(欄位由 dataclass fields 驅動,新增欄位不需改此處)."""
    kwargs: dict[str, object] = {f.name: base.get(f.name) for f in fields(FadeStopCombo)}
    kwargs.update(overrides)
    return FadeStopCombo(**kwargs)  # type: ignore[arg-type]


_TUPLE_KEYS = {
    "inner_flip_phi_grid",
    "guard_dist_grid",
    "wf_test_starts",
    "lock_penalty_grid",
    "struct_stop_buffers",
    "base_arm_gap_edges",
    "cell_a_inner_thresholds",
    "cell_b_approach_dists",
    "cell_c_rally_pcts",
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
    "guard_limit_dist",
    "disaster_x",
    "disaster_arm_x",
    "disaster_retrace_r",
    "lock_penalty",
    "stress_guard_fill_high",
    "inner_flip_min_bars",
    "tp_flush_z",
    "tp_flush_lookback",
    "tp_flush_recovery",
    "tp_flush_min_profit",
    "tp_hl_k",
    "tp_hl_min_profit",
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
    cfg = FadeBacktestConfig(**payload)  # type: ignore[arg-type]
    validate_disaster_fields(cfg)
    validate_round4_fields(cfg)
    return cfg


def validate_disaster_fields(cfg: FadeBacktestConfig) -> None:
    """round 3 災難停損欄位不變式(load 與引擎共用;change-spec §9.1/二輪 P2-5)."""
    retrace_on = cfg.disaster_arm_x is not None or cfg.disaster_retrace_r is not None
    if retrace_on and (cfg.disaster_arm_x is None or cfg.disaster_retrace_r is None):
        raise ValueError("disaster_arm_x 與 disaster_retrace_r 必須同設")
    if cfg.disaster_x is not None and retrace_on:
        raise ValueError("disaster_x 與回落式災難停損(arm/retrace)互斥")


def validate_round4_fields(cfg: FadeBacktestConfig) -> None:
    """round 4 出場欄位不變式(load 與引擎共用;change-spec §5.1)."""
    flush_fields = (
        cfg.tp_flush_z,
        cfg.tp_flush_lookback,
        cfg.tp_flush_recovery,
        cfg.tp_flush_min_profit,
    )
    flush_set = sum(1 for f in flush_fields if f is not None)
    if flush_set not in (0, len(flush_fields)):
        raise ValueError("tp_flush_z/lookback/recovery/min_profit 四欄必須同設")
    hl_set = sum(1 for f in (cfg.tp_hl_k, cfg.tp_hl_min_profit) if f is not None)
    if hl_set not in (0, 2):
        raise ValueError("tp_hl_k 與 tp_hl_min_profit 必須同設")
    if cfg.inner_flip_min_bars < 1:
        raise ValueError("inner_flip_min_bars 必須 ≥ 1")


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
