"""版本化策略參數 — 全部門檻在此,引擎 code 不出現 magic number(spec §2).

預設值 = docs/strategy.md 當前假設;調策略 = 改 JSON 重跑,不動 code。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from copycat.configio import load_dataclass_json


@dataclass(frozen=True, slots=True)
class StrategyConfig:
    # --- 通用 ---
    limit_eps: float = 1e-6  # 漲停價比較容差(浮點)
    # --- Phase 2 鎖板品質 ---
    lock_time_buckets: tuple[int, ...] = (4, 59, 179, 239)  # 分鐘索引切點(09:05/10:00/12:00/13:00)
    early_lock_max_idx: int = 59  # tier: 早鎖 = 首鎖 < 10:00
    tail_lock_min_idx: int = 239  # 尾盤鎖 = 13:00+
    violent_pull_window: int = 10  # 暴力拉板觀察窗(bar 數)
    violent_pull_min_gain: float = 0.06  # 窗內推升 ≥6% = 暴力拉板
    queue_strong_min: float = 0.40  # 鎖後排隊消耗 ≥40% 日量 = 真需求
    queue_dead_max: float = 0.15  # <15% = 死鎖無量
    open_count_weak: int = 6  # 打開 ≥6 次 → weak(續鎖 0%)
    open_count_strong_max: int = 1  # strong 允許的最大打開次數
    # --- Phase 3 T+1 ---
    t1_limit_mult: float = 1.095  # T+1 觸停/漲停開閾值 = 前日漲停 ×1.095
    gap_buckets: tuple[float, ...] = (0.0, 0.01, 0.03, 0.07, 0.095)
    auction_buckets: tuple[float, ...] = (0.03, 0.08)  # 競價量占比三桶切點
    inner_window: int = 15  # 內盤比觀察窗(分鐘)
    pull_high_min: float = 0.02  # t1 路徑分類:拉高出貨的最小拉幅
    pull_high_max_idx: int = 90  # 拉高出貨的高點須在前 90 分鐘內
    adv_window: int = 20  # 均量窗(DailyIndex.adv20 已固定 20,此值供文件化)

    @classmethod
    def default(cls) -> StrategyConfig:
        return cls()


def load_config(path: Path) -> StrategyConfig:
    return load_dataclass_json(
        path,
        StrategyConfig,
        tuple_keys=("lock_time_buckets", "gap_buckets", "auction_buckets"),
        unknown_label="未知策略參數",
    )
