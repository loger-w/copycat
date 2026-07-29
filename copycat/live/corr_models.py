"""相關係數引擎的純函數層:中價與對數報酬(design §1.2 / SC-2)。

秒級取樣一律用 **Bid/Ask 中價**,不用成交價 —— 成交在秒級是非同步的(Epps 效應),
費半 SXF 平均每分鐘約 1 口成交,以成交價取樣會讓大多數秒為零報酬,相關係數系統性
偏向 0 且窗越短偏得越兇。中價由造市商報價驅動,每秒都有值。

價格單位沿用專案慣例:毫點/毫元整數(`stock_models.to_milli`),不用 float 表價。
"""

from __future__ import annotations

import math
from collections.abc import Sequence

__all__ = ["log_return", "mid_from_book"]

Level = tuple[int, int]  # (價毫元, 量)


def mid_from_book(bids: Sequence[Level], asks: Sequence[Level]) -> int | None:
    """最佳買賣中價(毫點整數);任一側無報價 → None。

    單邊缺檔不用另一側硬湊 —— 單邊價不是市場對該商品的共識定價,拿來算報酬會製造
    假波動。整除的 0.5 毫點誤差在 40,400,000 毫點量級上是 1.2e-8 相對誤差,可忽略。
    """
    if not bids or not asks:
        return None
    return (bids[0][0] + asks[0][0]) // 2


def log_return(prev: int, cur: int) -> float | None:
    """對數報酬 ln(cur/prev);任一端非正 → None(取 log 前的定義域防護)。"""
    if prev <= 0 or cur <= 0:
        return None
    return math.log(cur / prev)
