"""T+1 空方模擬器(design.md v2 §4)— 零 IO,悲觀成交,當沖先賣.

方向反轉語意(vs 多方 simulate.py):
- 進場 = 賣出(entry = trig.close − slippage,cap 跌停價)
- 停損 = 逆風上漲(bar.high >= level → exit at max(level, bar.close))
- 停利 S5 = 順風下跌(bar.low <= level → exit at target_level,限價單)
- S1 外盤比:>= phi 觸發(買盤強 = 空方不利;多方版是 < phi)
- running_low 初始 = trig.low(對稱多方 run_high = trig.high)
- 鎖死 = bar.low >= t1_limit − eps → 凍結,全日鎖 → 漲停價回補
- 衝突:停損 > 停利/TP > 13:00 > 收盤(取最差 = 最高回補價)
- 無留倉(當沖先賣制度)
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from copycat.backtest.fade_config import FadeBacktestConfig, FadeStopCombo
from copycat.data.models import Bar1K
from copycat.market import limit_up_price, tick_size

if TYPE_CHECKING:
    from copycat.backtest.fade_config import FadeTakeProfitCombo


@dataclass(frozen=True, slots=True)
class FadeSample:
    stock_id: str
    date: str
    t1_date: str
    limit: float
    t1_open: float
    gap: float
    broker_ids: str
    source: str = ""  # tiger_csv / control / scan(分層報告用)


@dataclass(frozen=True, slots=True)
class FadeTradeOutcome:
    status: str
    pnl_rate: float | None
    exit_m: int | None
    lock_flag: bool


# 入統計的出場 status 單一定義(消費端 fade_pipeline / fade_optimize 一律 import,不各自複製)。
# guard_exit 必須在列(R1):強制風控停出的正是最差虧損交易,不入統計 = 期望值灌水。
# 新增出場 status 時只改這裡;excluded_* 前綴 = 未進場,永不在列。
TRADEABLE_STATUSES = frozenset(
    {"stopped", "target_hit", "time_1300", "closeout", "locked_at_limit", "guard_exit"}
)


def _round_trip_cost(cfg: FadeBacktestConfig) -> float:
    fee = cfg.fee_rate * (1.0 - cfg.fee_discount) * 2.0
    return fee + cfg.intraday_tax


def _simulate_core(
    bars: list[Bar1K],
    trig_idx: int,
    sample: FadeSample,
    combo: FadeStopCombo,
    tp: FadeTakeProfitCombo | None,
    cfg: FadeBacktestConfig,
    slippage_ticks: int,
    entry_price_override: float | None = None,
    fixed_stop_level: float | None = None,
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

    # round 2:entry_price_override(None = 舊行為,以觸發 bar close 為進場參考價)
    entry_ref = entry_price_override if entry_price_override is not None else trig.close
    entry = max(entry_ref - slippage_ticks * tick_size(entry_ref), t1_down_limit)

    # 強制風控(round 1;None = 停用):guard = 距漲停強制回補、disaster = 災難停損
    guard_level: float | None = None
    if cfg.guard_limit_dist is not None:
        guard_level = t1_limit * (1.0 - cfg.guard_limit_dist)
        if entry >= guard_level:  # 進場已在 guard 區內(高 gap)→ 排除而非即時虧損出場
            return FadeTradeOutcome("excluded_guard_at_entry", None, None, False)
    disaster_level = entry * (1.0 + cfg.disaster_x) if cfg.disaster_x is not None else None

    post = bars[trig_idx + 1 :]

    swing_high: float | None = None
    if combo.s2_m is not None:
        window = bars[max(0, trig_idx - combo.s2_m + 1) : trig_idx + 1]
        swing = max(b.high for b in window)
        swing_high = swing * (1.0 + (combo.s2_buf or 0.0))

    running_low = trig.low
    running_high = trig.high
    stall = 0
    outer_win: deque[tuple[float, float]] = deque(maxlen=cfg.s1_outer_window)
    t1300_consumed = not combo.t1300
    cost = _round_trip_cost(cfg)
    ever_locked = False

    post_bars_so_far: list[Bar1K] = []
    cum_pv = 0.0
    cum_vol = 0.0
    cum_delta = 0.0
    prev_cum_delta = 0.0
    elapsed_bars = 0

    def _pnl(exit_price: float) -> float:
        return 1.0 - exit_price / entry - cost

    for b in post:
        locked = b.low >= t1_limit - eps
        if locked:
            ever_locked = True
            running_low = min(running_low, b.low)
            running_high = max(running_high, b.high)
            if not t1300_consumed and b.m >= cfg.t1300_min_idx:
                t1300_consumed = True
            elapsed_bars += 1
            post_bars_so_far.append(b)
            continue

        if b.low < running_low:
            running_low = b.low
            stall = 0
        else:
            stall += 1
        running_high = max(running_high, b.high)
        outer_win.append((b.up_volume, b.down_volume))

        prev_cum_delta = cum_delta
        cum_delta += b.up_volume - b.down_volume
        cum_pv += b.close * b.volume
        cum_vol += b.volume
        post_bars_so_far.append(b)
        elapsed_bars += 1

        # guard/disaster/fixed_stop(鎖死凍結 bar 不會走到這裡);
        # stress_guard_fill_high:嘎空瞬間全市場搶買 → 壓測成交價改取 bar 最高價
        forced_ref = b.high if cfg.stress_guard_fill_high else b.close
        forced_fills: list[float] = []
        if guard_level is not None and b.high >= guard_level:
            forced_fills.append(max(guard_level, forced_ref))
        if disaster_level is not None and b.high >= disaster_level:
            forced_fills.append(max(disaster_level, forced_ref))
        if fixed_stop_level is not None and b.high >= fixed_stop_level:
            forced_fills.append(max(fixed_stop_level, forced_ref))

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

        tp_fill: float | None = None
        if tp is not None:
            from copycat.backtest.fade_tp import check_tp_exit

            tp_fill = check_tp_exit(
                tp,
                b,
                entry,
                running_low,
                running_high,
                post_bars_so_far,
                cum_delta,
                prev_cum_delta,
                sample,
                elapsed_bars,
                cum_pv,
                cum_vol,
            )

        time_fill: float | None = None
        if not t1300_consumed and b.m >= cfg.t1300_min_idx:
            t1300_consumed = True
            time_fill = b.close

        if stop_fills or forced_fills:
            worst = max(stop_fills + forced_fills)
            if target_fill is not None:
                worst = max(worst, target_fill)
            if tp_fill is not None:
                worst = max(worst, tp_fill)
            if time_fill is not None:
                worst = max(worst, time_fill)
            status = "guard_exit" if forced_fills else "stopped"
            return FadeTradeOutcome(status, _pnl(worst), b.m, ever_locked)

        if target_fill is not None:
            exit_price = target_fill
            if tp_fill is not None:
                exit_price = max(target_fill, tp_fill)
            return FadeTradeOutcome("target_hit", _pnl(exit_price), b.m, ever_locked)

        if tp_fill is not None:
            return FadeTradeOutcome("target_hit", _pnl(tp_fill), b.m, ever_locked)

        if time_fill is not None:
            return FadeTradeOutcome("time_1300", _pnl(time_fill), b.m, ever_locked)

    last = post[-1]
    if last.low >= t1_limit - eps:
        lock_exit = (
            t1_limit * (1.0 + cfg.lock_penalty) if cfg.lock_penalty is not None else t1_limit
        )
        return FadeTradeOutcome("locked_at_limit", _pnl(lock_exit), None, True)
    return FadeTradeOutcome("closeout", _pnl(last.close), last.m, ever_locked)


def simulate_fade_sample(
    bars: list[Bar1K],
    trig_idx: int,
    sample: FadeSample,
    combo: FadeStopCombo,
    cfg: FadeBacktestConfig,
    slippage_ticks: int,
    entry_price_override: float | None = None,
    fixed_stop_level: float | None = None,
) -> FadeTradeOutcome:
    return _simulate_core(
        bars,
        trig_idx,
        sample,
        combo,
        None,
        cfg,
        slippage_ticks,
        entry_price_override=entry_price_override,
        fixed_stop_level=fixed_stop_level,
    )


def simulate_fade_with_tp(
    bars: list[Bar1K],
    trig_idx: int,
    sample: FadeSample,
    combo: FadeStopCombo,
    tp: FadeTakeProfitCombo | None,
    cfg: FadeBacktestConfig,
    slippage_ticks: int,
) -> FadeTradeOutcome:
    return _simulate_core(bars, trig_idx, sample, combo, tp, cfg, slippage_ticks)
