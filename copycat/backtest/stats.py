"""加權統計與三道驗證(design D12、§4 月度一致性 / θ 平台檢定).

- 每筆 PnL = 扣成本報酬率 × weight,等額名目、不複投;MDD = 時間序累加曲線峰谷差(報酬率單位)。
- 輸出排序(D11)與 MDD 時間序(D12)是不同排序,不可混用。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date

from copycat.backtest.config import BacktestConfig


@dataclass(frozen=True, slots=True)
class Trade:
    date: str
    stock_id: str
    pnl: float  # 扣成本報酬率(未乘權重)
    weight: float = 1.0


def weighted_stats(trades: list[Trade]) -> dict[str, float | int | None]:
    if not trades:
        return {
            "expectancy": None,
            "p_win": None,
            "avg_win": None,
            "avg_loss": None,
            "payoff": None,
            "n_raw": 0,
            "n_weighted": 0.0,
        }
    wsum = sum(t.weight for t in trades)
    expectancy = sum(t.pnl * t.weight for t in trades) / wsum
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl < 0]
    w_wins = sum(t.weight for t in wins)
    w_losses = sum(t.weight for t in losses)
    avg_win = sum(t.pnl * t.weight for t in wins) / w_wins if w_wins > 0 else None
    avg_loss = sum(t.pnl * t.weight for t in losses) / w_losses if w_losses > 0 else None
    payoff = avg_win / abs(avg_loss) if avg_win is not None and avg_loss else None
    return {
        "expectancy": expectancy,
        "p_win": w_wins / wsum,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "payoff": payoff,
        "n_raw": len(trades),
        "n_weighted": wsum,
    }


def max_drawdown(trades: list[Trade]) -> float:
    """(date, stock_id) 時間序逐筆累加加權 PnL 的 equity curve 峰谷差(D12)."""
    equity = 0.0
    peak = 0.0
    mdd = 0.0
    for t in sorted(trades, key=lambda t: (t.date, t.stock_id)):
        equity += t.pnl * t.weight
        peak = max(peak, equity)
        mdd = max(mdd, peak - equity)
    return mdd


def _months_between(start: str, end: str) -> list[str]:
    d0, d1 = _date.fromisoformat(start), _date.fromisoformat(end)
    out: list[str] = []
    y, m = d0.year, d0.month
    while (y, m) <= (d1.year, d1.month):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def monthly_consistency(trades: list[Trade], test_start: str, test_end: str) -> dict[str, object]:
    """N = 日曆月數固定;正月 = 加權月期望值 > 0(零成交月非正月);
    第二條件:最差單月虧損絕對值 ≤ 正貢獻月加總 × 50%(無虧損月自動通過)."""
    months = _months_between(test_start, test_end)
    sums: dict[str, float] = {mo: 0.0 for mo in months}
    hits: dict[str, int] = {mo: 0 for mo in months}
    for t in trades:
        mo = t.date[:7]
        if mo in sums and test_start <= t.date <= test_end:
            sums[mo] += t.pnl * t.weight
            hits[mo] += 1
    positive = sum(1 for v in sums.values() if v > 0)
    threshold = len(months) // 2 + 1
    passed_majority = positive >= threshold
    losses = [v for v in sums.values() if v < 0]
    pos_sum = sum(v for v in sums.values() if v > 0)
    passed_blowup = True if not losses else abs(min(losses)) <= 0.5 * pos_sum
    return {
        "n_months": len(months),
        "positive_months": positive,
        "threshold": threshold,
        "passed": passed_majority and passed_blowup,
        "monthly_sums": sums,
        "monthly_hits": hits,
    }


def plateau_check(curve: dict[float, float], theta_star: float, cfg: BacktestConfig) -> bool:
    """θ*±step 鄰域(存在的網格點)test 期望值同號且 ≥ |θ* 值| × plateau_min_frac."""
    star = curve.get(round(theta_star, 4))
    if star is None or star == 0.0:
        return False
    for step in cfg.plateau_neighbor_steps:
        for sign in (1, -1):
            key = round(theta_star + sign * step * 0.001, 4)
            v = curve.get(key)
            if v is None:
                continue
            if v * star <= 0 or abs(v) < abs(star) * cfg.plateau_min_frac:
                return False
    return True
