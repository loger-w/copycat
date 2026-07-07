"""T 日進場模擬器(design §3 D6/D7/D9 + §4)— 零 IO,悲觀成交.

時序語意:
- 進場 = 觸發 bar close + slippage tick(cap 在漲停價);停損自觸發 bar 下一根起評估。
- 鎖死 bar(low ≥ limit − limit_eps)凍結全部停損、S1 計時與外盤窗(D9)。
- 同 bar 優先序:停損 > 時間出場 > 留倉;多重停損取最差成交價。
- 13:00 檢查點 = 觸發 bar 之後第一根 m ≥ t1300_min_idx 的 bar(one-shot;鎖死則通過)。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from copycat.backtest.config import BacktestConfig
from copycat.backtest.universe import LOCKABLE_GROUPS, Sample
from copycat.data.models import Bar1K
from copycat.market import tick_size


@dataclass(frozen=True, slots=True)
class StopCombo:
    s1_n: int | None
    s1_phi: float | None  # -1.0 = 外盤比條件 off;None = S1 off
    s2_m: int | None
    s2_buf: float | None
    s3_x: float | None
    s4_x: float | None
    t1300: bool

    @property
    def combo_id(self) -> str:
        return (
            f"s1={self.s1_n}/{self.s1_phi}|s2={self.s2_m}/{self.s2_buf}"
            f"|s3={self.s3_x}|s4={self.s4_x}|t1300={self.t1300}"
        )


@dataclass(frozen=True, slots=True)
class TradeOutcome:
    status: str  # excluded_* / stopped / time_1300 / closeout / hold_e1
    pnl_rate: float | None  # 扣成本報酬率;excluded_* → None
    exit_m: int | None  # 出場 bar 分鐘索引;hold_e1 → None


def enumerate_stop_combos(cfg: BacktestConfig) -> list[StopCombo]:
    """單族(S1/S2/S3/S4)+ S1×S2 疊加,× t1300 兩臂;固定順序(determinism)."""
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
    for n in cfg.s1_stall_bars:
        for phi in cfg.s1_outer_max:
            for m in cfg.s2_swing_lookback:
                for buf in cfg.s2_buffer:
                    bases.append({"s1_n": n, "s1_phi": phi, "s2_m": m, "s2_buf": buf})
    combos: list[StopCombo] = []
    for t13 in cfg.t1300_variants:
        for base in bases:
            combos.append(
                StopCombo(
                    s1_n=base.get("s1_n"),  # type: ignore[arg-type]
                    s1_phi=base.get("s1_phi"),  # type: ignore[arg-type]
                    s2_m=base.get("s2_m"),  # type: ignore[arg-type]
                    s2_buf=base.get("s2_buf"),  # type: ignore[arg-type]
                    s3_x=base.get("s3_x"),  # type: ignore[arg-type]
                    s4_x=base.get("s4_x"),  # type: ignore[arg-type]
                    t1300=t13,
                )
            )
    return combos


def _round_trip_cost(cfg: BacktestConfig, overnight: bool) -> float:
    fee = cfg.fee_rate * (1.0 - cfg.fee_discount) * 2.0
    return fee + (cfg.overnight_tax if overnight else cfg.intraday_tax)


def simulate_sample(
    bars: list[Bar1K],
    trig_idx: int,
    sample: Sample,
    t1_open: float | None,
    combo: StopCombo,
    cfg: BacktestConfig,
    slippage_ticks: int,
) -> TradeOutcome:
    if not bars or trig_idx >= len(bars):
        raise ValueError(f"bars 不含觸發 bar: {sample.stock_id} {sample.date}")
    trig = bars[trig_idx]
    if combo.t1300 and trig.m >= cfg.t1300_min_idx:
        return TradeOutcome("excluded_afternoon", None, None)
    if trig_idx == len(bars) - 1:
        return TradeOutcome("excluded_lastbar", None, None)

    limit = sample.limit_price
    eps = cfg.limit_eps
    if trig.low >= limit - eps:  # 觸發 bar 本身鎖死 → 無可成交賣單,進不了場(悲觀)
        return TradeOutcome("excluded_unfillable", None, None)
    entry = min(trig.close + slippage_ticks * tick_size(trig.close), limit)
    post = bars[trig_idx + 1 :]
    if entry >= limit - eps and all(b.low >= limit - eps for b in post):
        return TradeOutcome("excluded_unfillable", None, None)

    # S2 停損位:進場前 M 根(含觸發 bar)swing low − buffer
    stop2: float | None = None
    if combo.s2_m is not None:
        window = bars[max(0, trig_idx - combo.s2_m + 1) : trig_idx + 1]
        swing = min(b.low for b in window)
        stop2 = swing * (1.0 - (combo.s2_buf or 0.0))

    run_high = trig.high
    stall = 0
    outer_win: deque[tuple[float, float]] = deque(maxlen=cfg.s1_outer_window)
    t1300_consumed = not combo.t1300

    def _pnl(exit_price: float, overnight: bool) -> float:
        return exit_price / entry - 1.0 - _round_trip_cost(cfg, overnight)

    for b in post:
        locked = b.low >= limit - eps
        if locked:
            run_high = max(run_high, b.high)
            if not t1300_consumed and b.m >= cfg.t1300_min_idx:
                t1300_consumed = True  # 鎖死 → 通過檢查點,不出場
            continue

        # --- 非鎖死 bar:更新衍生序列(D9 凍結語意:只有這裡會動)---
        if b.high > run_high:
            run_high = b.high
            stall = 0
        else:
            stall += 1
        outer_win.append((b.up_volume, b.down_volume))

        fills: list[float] = []
        if combo.s4_x is not None:
            level = entry * (1.0 - combo.s4_x)
            if b.low < level:
                fills.append(min(level, b.close))
        if combo.s3_x is not None:
            level = run_high * (1.0 - combo.s3_x)
            if b.low < level:
                fills.append(min(level, b.close))
        if stop2 is not None and b.low < stop2:
            fills.append(min(stop2, b.close))
        if combo.s1_n is not None and stall >= combo.s1_n:
            phi = combo.s1_phi if combo.s1_phi is not None else -1.0
            if phi < 0:
                fills.append(b.close)
            else:
                uv = sum(u for u, _ in outer_win)
                dv = sum(d for _, d in outer_win)
                if uv + dv > 0 and uv / (uv + dv) < phi:
                    fills.append(b.close)

        time_fill: float | None = None
        if not t1300_consumed and b.m >= cfg.t1300_min_idx:
            t1300_consumed = True
            time_fill = b.close  # 未鎖 → 時間出場

        if fills:  # 停損 > 時間出場:同 bar 取最差
            price = min(fills + ([time_fill] if time_fill is not None else []))
            return TradeOutcome("stopped", _pnl(price, overnight=False), b.m)
        if time_fill is not None:
            return TradeOutcome("time_1300", _pnl(time_fill, overnight=False), b.m)

    # --- 收盤:留倉資格(D7 雙保險)---
    last = post[-1]
    closed_at_limit = last.close >= limit - eps
    lockable = sample.group in LOCKABLE_GROUPS
    if closed_at_limit != lockable:
        return TradeOutcome("excluded_lock_conflict", None, None)
    if closed_at_limit:
        if t1_open is None:
            return TradeOutcome("excluded_t1_missing", None, None)
        return TradeOutcome("hold_e1", _pnl(t1_open, overnight=True), None)
    return TradeOutcome("closeout", _pnl(last.close, overnight=False), last.m)
