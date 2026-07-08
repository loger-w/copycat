"""T+1 空方模擬器(design.md v2 §4)— 零 IO,悲觀成交,當沖先賣.

方向反轉語意(vs 多方 simulate.py):
- 進場 = 賣出(entry = trig.close − slippage,cap 跌停價)
- 停損 = 逆風上漲(bar.high >= level → exit at max(level, bar.close))
- 停利 S5 = 順風下跌(bar.low <= level → exit at target_level,限價單)
- S1 外盤比:>= phi 觸發(買盤強 = 空方不利;多方版是 < phi)
- running_low 初始 = trig.low(對稱多方 run_high = trig.high)
- 鎖死 = bar.low >= t1_limit − eps → 凍結,全日鎖 → 漲停價回補
- 衝突:停損 > 停利 > 13:00 > 收盤(取最差 = 最高回補價)
- 無留倉(當沖先賣制度)
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from copycat.backtest.fade_config import FadeBacktestConfig, FadeStopCombo
from copycat.data.models import Bar1K
from copycat.market import limit_up_price, tick_size


@dataclass(frozen=True, slots=True)
class FadeSample:
    stock_id: str
    date: str
    t1_date: str
    limit: float
    t1_open: float
    gap: float
    broker_ids: str


@dataclass(frozen=True, slots=True)
class FadeTradeOutcome:
    status: str
    pnl_rate: float | None
    exit_m: int | None
    lock_flag: bool


def _round_trip_cost(cfg: FadeBacktestConfig) -> float:
    fee = cfg.fee_rate * (1.0 - cfg.fee_discount) * 2.0
    return fee + cfg.intraday_tax


def simulate_fade_sample(
    bars: list[Bar1K],
    trig_idx: int,
    sample: FadeSample,
    combo: FadeStopCombo,
    cfg: FadeBacktestConfig,
    slippage_ticks: int,
) -> FadeTradeOutcome:
    if not bars or trig_idx >= len(bars):
        raise ValueError(f"bars 不含觸發 bar: {sample.stock_id} {sample.t1_date}")

    trig = bars[trig_idx]
    t1_limit = limit_up_price(sample.limit)
    t1_down_limit = sample.limit * 0.90
    eps = cfg.limit_eps

    if combo.t1300 and trig.m >= cfg.t1300_min_idx:
        return FadeTradeOutcome("excluded_afternoon", None, None, False)
    if trig_idx == len(bars) - 1:
        return FadeTradeOutcome("excluded_lastbar", None, None, False)
    if trig.low >= t1_limit - eps:
        return FadeTradeOutcome("excluded_at_limit", None, None, False)

    entry = max(trig.close - slippage_ticks * tick_size(trig.close), t1_down_limit)
    post = bars[trig_idx + 1 :]

    swing_high: float | None = None
    if combo.s2_m is not None:
        window = bars[max(0, trig_idx - combo.s2_m + 1) : trig_idx + 1]
        swing = max(b.high for b in window)
        swing_high = swing * (1.0 + (combo.s2_buf or 0.0))

    running_low = trig.low
    stall = 0
    outer_win: deque[tuple[float, float]] = deque(maxlen=cfg.s1_outer_window)
    t1300_consumed = not combo.t1300
    cost = _round_trip_cost(cfg)
    ever_locked = False

    def _pnl(exit_price: float) -> float:
        return 1.0 - exit_price / entry - cost

    for b in post:
        locked = b.low >= t1_limit - eps
        if locked:
            ever_locked = True
            running_low = min(running_low, b.low)
            if not t1300_consumed and b.m >= cfg.t1300_min_idx:
                t1300_consumed = True
            continue

        if b.low < running_low:
            running_low = b.low
            stall = 0
        else:
            stall += 1
        outer_win.append((b.up_volume, b.down_volume))

        stop_fills: list[float] = []
        if combo.s4_x is not None:
            level = entry * (1.0 + combo.s4_x)
            if b.high >= level:
                stop_fills.append(max(level, b.close))
        if combo.s3_x is not None:
            level = running_low * (1.0 + combo.s3_x)
            if b.high >= level:
                stop_fills.append(max(level, b.close))
        if swing_high is not None and b.high >= swing_high:
            stop_fills.append(max(swing_high, b.close))
        if combo.s1_n is not None and stall >= combo.s1_n:
            phi = combo.s1_phi if combo.s1_phi is not None else -1.0
            if phi < 0:
                stop_fills.append(b.close)
            else:
                uv = sum(u for u, _ in outer_win)
                dv = sum(d for _, d in outer_win)
                if uv + dv > 0 and uv / (uv + dv) >= phi:
                    stop_fills.append(b.close)

        target_fill: float | None = None
        if combo.s5_x is not None:
            target_level = entry * (1.0 - combo.s5_x)
            if b.low <= target_level:
                target_fill = target_level

        time_fill: float | None = None
        if not t1300_consumed and b.m >= cfg.t1300_min_idx:
            t1300_consumed = True
            time_fill = b.close

        if stop_fills:
            worst = max(stop_fills)
            if target_fill is not None:
                worst = max(worst, target_fill)
            if time_fill is not None:
                worst = max(worst, time_fill)
            return FadeTradeOutcome("stopped", _pnl(worst), b.m, ever_locked)

        if target_fill is not None:
            return FadeTradeOutcome("target_hit", _pnl(target_fill), b.m, ever_locked)

        if time_fill is not None:
            return FadeTradeOutcome("time_1300", _pnl(time_fill), b.m, ever_locked)

    last = post[-1]
    if last.low >= t1_limit - eps:
        return FadeTradeOutcome("locked_at_limit", _pnl(t1_limit), None, True)
    return FadeTradeOutcome("closeout", _pnl(last.close), last.m, ever_locked)
