"""加權統計(SC-5)與三道驗證(SC-7)— 手算對照."""

from __future__ import annotations

from copycat.backtest.config import BacktestConfig
from copycat.backtest.stats import (
    Trade,
    max_drawdown,
    monthly_consistency,
    plateau_check,
    weighted_stats,
)


def _t(date: str, pnl: float, weight: float = 1.0, sid: str = "1101") -> Trade:
    return Trade(date=date, stock_id=sid, pnl=pnl, weight=weight)


def _f(stats: dict[str, float | int | None], key: str) -> float:
    v = stats[key]
    assert isinstance(v, float | int)
    return float(v)


def test_weighted_stats_hand_computed() -> None:
    trades = [_t("2026-03-02", 0.10, 1.0), _t("2026-03-03", -0.05, 5.0)]
    s = weighted_stats(trades)
    assert abs(_f(s, "expectancy") - (0.10 * 1 - 0.05 * 5) / 6) < 1e-12
    assert abs(_f(s, "p_win") - 1 / 6) < 1e-12
    assert abs(_f(s, "avg_win") - 0.10) < 1e-12
    assert abs(_f(s, "avg_loss") - (-0.05)) < 1e-12
    assert abs(_f(s, "payoff") - 2.0) < 1e-12
    assert s["n_raw"] == 2 and s["n_weighted"] == 6.0
    # 權重差異斷言:不加權期望值 = +0.025,加權 = −0.025(正負翻轉)
    unweighted = weighted_stats([_t("a", 0.10), _t("b", -0.05)])
    assert _f(unweighted, "expectancy") > 0 > _f(s, "expectancy")


def test_weighted_stats_empty() -> None:
    s = weighted_stats([])
    assert s["n_raw"] == 0 and s["expectancy"] is None


def test_max_drawdown_time_order() -> None:
    # 按 (date, stock_id) 時間序:+0.1 → −0.05×5 → curve [0.1, −0.15] → MDD 0.25
    trades = [_t("2026-03-03", -0.05, 5.0), _t("2026-03-02", 0.10, 1.0)]  # 亂序輸入
    assert abs(max_drawdown(trades) - 0.25) < 1e-12
    assert max_drawdown([]) == 0.0


def test_monthly_consistency_pass_and_fail() -> None:
    # test 期 2026-03-01~2026-06-26 → N=4,門檻 = floor(4/2)+1 = 3 個正月
    ok = [_t("2026-03-02", 0.01), _t("2026-04-02", 0.01), _t("2026-05-04", 0.01)]
    r = monthly_consistency(ok, "2026-03-01", "2026-06-26")
    assert r["n_months"] == 4 and r["positive_months"] == 3 and r["passed"] is True
    # 只有 2 個正月(6 月零成交非正月)→ fail
    weak = [_t("2026-03-02", 0.01), _t("2026-04-02", 0.01), _t("2026-05-04", -0.01)]
    assert monthly_consistency(weak, "2026-03-01", "2026-06-26")["passed"] is False


def test_monthly_consistency_single_month_blowup() -> None:
    # 3 正月達標,但單月暴虧 0.02 > 其餘正貢獻 0.03×50% → fail
    trades = [
        _t("2026-03-02", 0.01),
        _t("2026-04-02", 0.01),
        _t("2026-05-04", 0.01),
        _t("2026-06-02", -0.02),
    ]
    r = monthly_consistency(trades, "2026-03-01", "2026-06-26")
    assert r["positive_months"] == 3 and r["passed"] is False
    # 無虧損月 → 第二條件自動通過
    clean = [_t("2026-03-02", 0.01), _t("2026-04-02", 0.01), _t("2026-05-04", 0.01)]
    assert monthly_consistency(clean, "2026-03-01", "2026-06-26")["passed"] is True


def test_plateau_check() -> None:
    cfg = BacktestConfig.default()
    curve = {0.08: 0.010, 0.081: 0.009, 0.082: 0.008}
    assert plateau_check(curve, 0.08, cfg) is True  # 鄰域同號且 ≥40%
    assert plateau_check({0.08: 0.010, 0.081: -0.001, 0.082: 0.008}, 0.08, cfg) is False  # 變號
    assert plateau_check({0.08: 0.010, 0.081: 0.003, 0.082: 0.008}, 0.08, cfg) is False  # <40%
