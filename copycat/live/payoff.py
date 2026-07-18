"""到期損益曲線純函數(毫點整數運算;NTD 僅出現在回傳邊界)。

部位到期損益為分段線性、轉折只在履約價 → 網格 = 履約價 ∪ 兩端外推一步,
BEP 由線段線性插值取得精確解(design.md §2.4)。
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from copycat.live.models import MULTIPLIER, OptionContract


@dataclass(frozen=True)
class PositionRow:
    contract: OptionContract
    net_qty: int
    net_cost_millipts: int  # 簽名成本(外盤 +qty×price / 內盤 −qty×price)


def intrinsic_millipts(cp: str, strike_millipts: int, k_millipts: int) -> int:
    if cp == "C":
        return max(0, k_millipts - strike_millipts)
    return max(0, strike_millipts - k_millipts)


def build_grid(strikes_millipts: list[int]) -> list[int]:
    """去重排序的履約價 ∪ {min−step, max+step};step = 相鄰間距中位數。"""
    uniq = sorted(set(strikes_millipts))
    if not uniq:
        return []
    if len(uniq) == 1:
        step = 1_000_000  # 單一履約價無間距可估,取 1000 點外推僅供顯示
    else:
        gaps = [b - a for a, b in zip(uniq, uniq[1:])]
        step = int(median(gaps))
    return [uniq[0] - step, *uniq, uniq[-1] + step]


def _pnl_ntd(rows: list[PositionRow], k_millipts: int) -> float:
    total_millipts = sum(
        row.net_qty * intrinsic_millipts(row.contract.cp, row.contract.strike_millipts, k_millipts)
        - row.net_cost_millipts
        for row in rows
    )
    return total_millipts * MULTIPLIER / 1000


def curve_points(rows: list[PositionRow], grid: list[int]) -> list[tuple[int, float]]:
    return [(k, _pnl_ntd(rows, k)) for k in grid]


def find_beps(curve: list[tuple[int, float]]) -> list[float]:
    """相鄰網格點符號翻轉 → 線性插值零點(點位);曲線分段線性故為精確解。"""
    beps: list[float] = []
    for (x0, y0), (x1, y1) in zip(curve, curve[1:]):
        if y0 == 0.0:
            beps.append(x0 / 1000)
            continue
        if y0 * y1 < 0:
            x = x0 + (x1 - x0) * (-y0) / (y1 - y0)
            beps.append(round(x / 1000, 1))
    if curve and curve[-1][1] == 0.0:
        beps.append(curve[-1][0] / 1000)
    return beps


def extremes(
    curve: list[tuple[int, float]],
) -> tuple[tuple[float, float], tuple[float, float]]:
    """(max_profit, max_loss),各為 (x_pts, y_ntd);語意 = 顯示範圍內極值。curve 不可為空。"""
    best = max(curve, key=lambda p: p[1])
    worst = min(curve, key=lambda p: p[1])
    return (best[0] / 1000, best[1]), (worst[0] / 1000, worst[1])


def interp_pnl(curve: list[tuple[int, float]], x_millipts: int) -> float | None:
    """x 落在網格線段上的線性插值;範圍外 None。"""
    for (x0, y0), (x1, y1) in zip(curve, curve[1:]):
        if x0 <= x_millipts <= x1:
            if x1 == x0:
                return y0
            return y0 + (y1 - y0) * (x_millipts - x0) / (x1 - x0)
    return None
