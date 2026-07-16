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

from copycat.backtest.fade_config import (
    FadeBacktestConfig,
    FadeStopCombo,
    validate_disaster_fields,
    validate_round4_fields,
)
from copycat.data.models import Bar1K
from copycat.market import limit_up_price, tick_size

if TYPE_CHECKING:
    from copycat.backtest.fade_config import FadeTakeProfitCombo
    from copycat.backtest.fade_tp import PivotState


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
    # 精算表歸因:round 3 強制出場 = hardline / struct_fixed / struct_ratchet /
    # disaster_x / disaster_retrace / inner_flip;round 4 停利 = tp_flush / tp_hl;
    # 其他出場 = None
    exit_reason: str | None = None
    # round 4:最大有利波動(毛,不扣成本)與引擎內部進場價;excluded_* = None
    mfe_rate: float | None = None
    entry_price: float | None = None


# 強制出場同價 tie-break 優先序(change-spec §9.2:hardline > struct > disaster;
# round 4 inner_flip 與 struct 同級,同價同級取 append 序前者 = struct 優先)
_REASON_RANK = {
    "hardline": 3,
    "struct_fixed": 2,
    "struct_ratchet": 2,
    "inner_flip": 2,
    "disaster_x": 1,
    "disaster_retrace": 1,
}


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
    ratchet_stop_b: float | None = None,
    inner_flip_phi: float | None = None,
) -> FadeTradeOutcome:
    if not bars or trig_idx >= len(bars):
        raise ValueError(f"bars 不含觸發 bar: {sample.stock_id} {sample.t1_date}")
    validate_disaster_fields(cfg)  # 擋 dataclasses.replace 繞過 config 驗證(round 3)
    validate_round4_fields(cfg)  # 同上(round 4)
    retrace_on = cfg.disaster_arm_x is not None and cfg.disaster_retrace_r is not None

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

    # round 4:累計內外盤自開盤起算(含 trig bar;與 cell_a gate / 全池證據同語意)
    cum_up = sum(pb.up_volume for pb in bars[: trig_idx + 1])
    cum_dn = sum(pb.down_volume for pb in bars[: trig_idx + 1])
    post_low: float | None = None  # 進場後最低(不含 trig bar;MFE / flush 錨)
    pivot_state: PivotState | None = None
    if cfg.tp_hl_k is not None:
        from copycat.backtest.fade_tp import PivotState as _PivotState

        pivot_state = _PivotState()

    def _pnl(exit_price: float) -> float:
        return 1.0 - exit_price / entry - cost

    def _mfe() -> float | None:
        return None if post_low is None else 1.0 - post_low / entry

    for b in post:
        prev_high = running_high  # 不含當前 bar(ratchet / 災難回落錨;無 lookahead)
        locked = b.low >= t1_limit - eps
        if locked:
            ever_locked = True
            running_low = min(running_low, b.low)
            running_high = max(running_high, b.high)
            if not t1300_consumed and b.m >= cfg.t1300_min_idx:
                t1300_consumed = True
            elapsed_bars += 1
            post_bars_so_far.append(b)
            # round 4:凍結 bar 資訊真實存在 → 累計/錨/pivot 照餵,僅不做出場檢查
            cum_up += b.up_volume
            cum_dn += b.down_volume
            post_low = b.low if post_low is None else min(post_low, b.low)
            if pivot_state is not None:
                pivot_state.update(b)
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
        cum_up += b.up_volume
        cum_dn += b.down_volume
        post_low = b.low if post_low is None else min(post_low, b.low)
        if pivot_state is not None:
            pivot_state.update(b)

        # guard/disaster/fixed_stop/ratchet(鎖死凍結 bar 不會走到這裡);
        # stress_guard_fill_high:嘎空瞬間全市場搶買 → 壓測成交價改取 bar 最高價
        forced_ref = b.high if cfg.stress_guard_fill_high else b.close
        forced_fills: list[tuple[float, str]] = []
        if guard_level is not None and b.high >= guard_level:
            forced_fills.append((max(guard_level, forced_ref), "hardline"))
        if disaster_level is not None and b.high >= disaster_level:
            forced_fills.append((max(disaster_level, forced_ref), "disaster_x"))
        if fixed_stop_level is not None and b.high >= fixed_stop_level:
            forced_fills.append((max(fixed_stop_level, forced_ref), "struct_fixed"))
        if ratchet_stop_b is not None:
            ratchet_level = prev_high * (1.0 + ratchet_stop_b)
            if b.high >= ratchet_level:
                forced_fills.append((max(ratchet_level, forced_ref), "struct_ratchet"))
        # round 4 inner_flip:累計內盤比跌破 φ = 買壓吃掉賣壓(劇本走樣)。
        # 成交 = close(訊號性市價出場,同 S1 慣例,不吃 stress);append 在 struct
        # 之後 → 同價同級歸因 struct 優先(change-spec §5.3)
        if (
            inner_flip_phi is not None
            and b.m >= cfg.inner_flip_min_bars
            and cum_up + cum_dn > 0
            and cum_dn / (cum_up + cum_dn) < inner_flip_phi
        ):
            forced_fills.append((b.close, "inner_flip"))
        # 回落式災難(round 3):prev_high 武裝 + 回落確認,成交 = level(限價語意,
        # 同 S5,不吃 stress);當前 bar 只更新錨,觸發自下一 bar 起
        if retrace_on and prev_high >= entry * (1.0 + cfg.disaster_arm_x):  # type: ignore[operator]
            retrace_level = prev_high * (1.0 - cfg.disaster_retrace_r)  # type: ignore[operator]
            if b.low <= retrace_level:
                forced_fills.append((retrace_level, "disaster_retrace"))

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

        # round 4 TP 決策樹(cfg 驅動,獨立於 combo tp):flush 優先於 hl(同 bar 寫死)
        tp_reason: str | None = None
        if cfg.tp_flush_z is not None or pivot_state is not None:
            from copycat.backtest.fade_tp import check_flush_exit, check_higher_low_exit

            profit_gross = 1.0 - b.close / entry
            tree_fill: float | None = None
            tree_reason: str | None = None
            if cfg.tp_flush_z is not None and post_low is not None:
                tree_fill = check_flush_exit(cfg, b, post_low, post_bars_so_far, profit_gross)
                if tree_fill is not None:
                    tree_reason = "tp_flush"
            if tree_fill is None and pivot_state is not None:
                tree_fill = check_higher_low_exit(pivot_state, b, profit_gross, cfg)
                if tree_fill is not None:
                    tree_reason = "tp_hl"
            if tree_fill is not None:
                if tp_fill is None or tree_fill >= tp_fill:
                    tp_reason = tree_reason
                tp_fill = tree_fill if tp_fill is None else max(tp_fill, tree_fill)

        time_fill: float | None = None
        if not t1300_consumed and b.m >= cfg.t1300_min_idx:
            t1300_consumed = True
            time_fill = b.close

        if stop_fills or forced_fills:
            worst = max(stop_fills + [f for f, _ in forced_fills])
            if target_fill is not None:
                worst = max(worst, target_fill)
            if tp_fill is not None:
                worst = max(worst, tp_fill)
            if time_fill is not None:
                worst = max(worst, time_fill)
            status = "guard_exit" if forced_fills else "stopped"
            reason: str | None = None
            if forced_fills:  # 歸因 = worst 強制成交價所屬機制,同價依 _REASON_RANK
                best_fill, best_reason = max(forced_fills, key=lambda t: (t[0], _REASON_RANK[t[1]]))
                # worst 若由非強制來源(combo stop/target/tp/time)決定 → 不歸因(review A3)
                if best_fill >= worst:
                    reason = best_reason
            return FadeTradeOutcome(status, _pnl(worst), b.m, ever_locked, reason, _mfe(), entry)

        if target_fill is not None:
            exit_price = target_fill
            if tp_fill is not None:
                exit_price = max(target_fill, tp_fill)
            # 歸因給 TP 樹僅當出場價由它決定(combo target 勝出 → None,現規則不變)
            reason_tp = tp_reason if tp_fill is not None and tp_fill >= target_fill else None
            return FadeTradeOutcome(
                "target_hit", _pnl(exit_price), b.m, ever_locked, reason_tp, _mfe(), entry
            )

        if tp_fill is not None:
            return FadeTradeOutcome(
                "target_hit", _pnl(tp_fill), b.m, ever_locked, tp_reason, _mfe(), entry
            )

        if time_fill is not None:
            return FadeTradeOutcome(
                "time_1300", _pnl(time_fill), b.m, ever_locked, None, _mfe(), entry
            )

    last = post[-1]
    if last.low >= t1_limit - eps:
        lock_exit = (
            t1_limit * (1.0 + cfg.lock_penalty) if cfg.lock_penalty is not None else t1_limit
        )
        return FadeTradeOutcome("locked_at_limit", _pnl(lock_exit), None, True, None, _mfe(), entry)
    return FadeTradeOutcome("closeout", _pnl(last.close), last.m, ever_locked, None, _mfe(), entry)


def simulate_fade_sample(
    bars: list[Bar1K],
    trig_idx: int,
    sample: FadeSample,
    combo: FadeStopCombo,
    cfg: FadeBacktestConfig,
    slippage_ticks: int,
    entry_price_override: float | None = None,
    fixed_stop_level: float | None = None,
    ratchet_stop_b: float | None = None,
    inner_flip_phi: float | None = None,
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
        ratchet_stop_b=ratchet_stop_b,
        inner_flip_phi=inner_flip_phi,
    )


def simulate_fade_with_tp(
    bars: list[Bar1K],
    trig_idx: int,
    sample: FadeSample,
    combo: FadeStopCombo,
    tp: FadeTakeProfitCombo | None,
    cfg: FadeBacktestConfig,
    slippage_ticks: int,
    inner_flip_phi: float | None = None,
) -> FadeTradeOutcome:
    return _simulate_core(
        bars, trig_idx, sample, combo, tp, cfg, slippage_ticks, inner_flip_phi=inner_flip_phi
    )
