"""Phase B 停利出場判定(11 種 TP 機制)+ round 4 cfg 驅動決策樹 — _simulate_core 內部呼叫."""

from __future__ import annotations

from dataclasses import dataclass, field

from copycat.backtest.fade_config import FadeBacktestConfig, FadeTakeProfitCombo
from copycat.backtest.fade_simulate import FadeSample
from copycat.data.models import Bar1K


@dataclass(slots=True)
class PivotState:
    """墊高結構偵測狀態(round 4 tp_hl;change-spec §5.2)。

    pivot 於下一 bar 確認(無 lookahead):bar[i−1] 為 pivot low ⟺
    low[i−1] 嚴格低於前後鄰 bar(pivot high 對稱,嚴格高)。
    `update` 每個 post bar(含鎖死凍結 bar)都要餵;判定另走
    `check_higher_low_exit`(僅非凍結 bar)。
    """

    prev2: Bar1K | None = None
    prev1: Bar1K | None = None
    pivot_lows: list[float] = field(default_factory=list)
    pivot_highs: list[float] = field(default_factory=list)

    def update(self, bar: Bar1K) -> None:
        if self.prev2 is not None and self.prev1 is not None:
            if self.prev1.low < self.prev2.low and self.prev1.low < bar.low:
                self.pivot_lows.append(self.prev1.low)
            if self.prev1.high > self.prev2.high and self.prev1.high > bar.high:
                self.pivot_highs.append(self.prev1.high)
        self.prev2 = self.prev1
        self.prev1 = bar


def check_flush_exit(
    cfg: FadeBacktestConfig,
    bar: Bar1K,
    running_low_post: float,
    post_bars_so_far: list[Bar1K],
    profit: float,
) -> float | None:
    """出量殺收工(round 4):結構同 _tp1,新低錨 = 進場後最低(不含 trig bar)."""
    if cfg.tp_flush_z is None:
        return None
    assert cfg.tp_flush_lookback is not None  # validate_round4_fields 保證同設
    assert cfg.tp_flush_recovery is not None
    assert cfg.tp_flush_min_profit is not None
    if profit < cfg.tp_flush_min_profit:
        return None
    lb = cfg.tp_flush_lookback
    window = post_bars_so_far[-(lb + 1) : -1] if len(post_bars_so_far) > 1 else []
    if len(window) < lb:
        return None
    avg_vol = sum(b.volume for b in window) / len(window)
    if avg_vol <= 0 or bar.volume <= avg_vol * cfg.tp_flush_z:
        return None
    if bar.low > running_low_post:
        return None
    rng = bar.high - bar.low
    if rng <= 0:
        return None
    if (bar.close - bar.low) / rng < cfg.tp_flush_recovery:
        return None
    return bar.close


def check_higher_low_exit(
    state: PivotState,
    bar: Bar1K,
    profit: float,
    cfg: FadeBacktestConfig,
) -> float | None:
    """墊高竭盡收工(round 4):最近 k 對 pivot low 不破(≥)且 pivot high 遞增(>)."""
    if cfg.tp_hl_k is None:
        return None
    assert cfg.tp_hl_min_profit is not None  # validate_round4_fields 保證同設
    if profit < cfg.tp_hl_min_profit:
        return None
    k = cfg.tp_hl_k
    lows = state.pivot_lows
    highs = state.pivot_highs
    if len(lows) < k + 1 or len(highs) < k + 1:
        return None
    recent_lows = lows[-(k + 1) :]
    recent_highs = highs[-(k + 1) :]
    if any(recent_lows[i + 1] < recent_lows[i] for i in range(k)):
        return None
    if any(recent_highs[i + 1] <= recent_highs[i] for i in range(k)):
        return None
    return bar.close


def check_tp_exit(
    tp: FadeTakeProfitCombo,
    bar: Bar1K,
    entry: float,
    running_low: float,
    running_high: float,
    post_bars_so_far: list[Bar1K],
    cum_delta: float,
    prev_cum_delta: float,
    sample: FadeSample,
    elapsed_bars: int,
    cum_pv: float,
    cum_vol: float,
) -> float | None:
    profit = 1.0 - bar.close / entry
    t = tp.tp_type
    if t == "s5":
        target = entry * (1.0 - tp.get("s5_x"))
        return target if bar.low <= target else None
    if t == "tp1":
        return _tp1(tp, bar, entry, running_low, post_bars_so_far, profit)
    if t == "tp2":
        return _tp2(tp, bar, post_bars_so_far, profit)
    if t == "tp3":
        return _tp3(tp, bar, running_low, post_bars_so_far, profit, elapsed_bars)
    if t == "tp4":
        return _tp4(tp, bar, post_bars_so_far, profit)
    if t == "tp5":
        return _tp5(tp, bar, sample)
    if t == "tp6":
        return _tp6(tp, bar, cum_pv, cum_vol)
    if t == "tp7":
        return _tp7(tp, bar, entry, running_high, running_low)
    if t == "tp8":
        return _tp8(tp, bar, post_bars_so_far, profit)
    if t == "tp9":
        return _tp9(tp, bar, cum_delta, prev_cum_delta, profit)
    if t == "tp10":
        return _tp10(tp, bar, running_low, profit)
    if t == "tp11":
        return _tp11(tp, bar, entry, elapsed_bars)
    return None


def _tp1(
    tp: FadeTakeProfitCombo,
    bar: Bar1K,
    entry: float,
    running_low: float,
    post_bars: list[Bar1K],
    profit: float,
) -> float | None:
    if profit < tp.get("min_profit"):
        return None
    lb = int(tp.get("lookback"))
    window = post_bars[-(lb + 1) : -1] if len(post_bars) > 1 else []
    if len(window) < lb:
        return None
    avg_vol = sum(b.volume for b in window) / len(window)
    if avg_vol <= 0:
        return None
    z = tp.get("z")
    if bar.volume <= avg_vol * z:
        return None
    if bar.low > running_low:
        return None
    rng = bar.high - bar.low
    if rng <= 0:
        return None
    recovery = (bar.close - bar.low) / rng
    if recovery < tp.get("recovery"):
        return None
    return bar.close


def _tp2(
    tp: FadeTakeProfitCombo,
    bar: Bar1K,
    post_bars: list[Bar1K],
    profit: float,
) -> float | None:
    if profit < tp.get("min_profit"):
        return None
    trend_n = int(tp.get("trend_n"))
    window = post_bars[-(trend_n + 1) : -1] if len(post_bars) > 1 else []
    if len(window) < 2:
        return None
    new_low_count = 0
    for i in range(1, len(window)):
        if window[i].low < window[i - 1].low:
            new_low_count += 1
    if new_low_count < int(tp.get("new_low_count")):
        return None
    avg_vol = sum(b.volume for b in window) / len(window)
    if avg_vol <= 0 or bar.volume <= avg_vol * tp.get("z"):
        return None
    if bar.close <= bar.open:
        return None
    total = bar.up_volume + bar.down_volume
    if total <= 0 or bar.up_volume / total < tp.get("inner_flip"):
        return None
    return bar.close


def _tp3(
    tp: FadeTakeProfitCombo,
    bar: Bar1K,
    running_low: float,
    post_bars: list[Bar1K],
    profit: float,
    elapsed_bars: int,
) -> float | None:
    if profit < tp.get("min_profit"):
        return None
    n = int(tp.get("n"))
    if elapsed_bars < 2 * n:
        return None
    if bar.low > running_low:
        return None
    recent = post_bars[-(n + 1) : -1] if len(post_bars) > n else post_bars[:-1]
    prior = (
        post_bars[-(2 * n + 1) : -(n + 1)]
        if len(post_bars) >= 2 * n + 1
        else post_bars[: -(n + 1)]
        if len(post_bars) > n + 1
        else []
    )
    if len(recent) < 2 or len(prior) < 2:
        return None
    recent_drops = []
    for i in range(1, len(recent)):
        if recent[i - 1].close > 0:
            recent_drops.append((recent[i - 1].close - recent[i].close) / recent[i - 1].close)
    prior_drops = []
    for i in range(1, len(prior)):
        if prior[i - 1].close > 0:
            prior_drops.append((prior[i - 1].close - prior[i].close) / prior[i - 1].close)
    if not recent_drops or not prior_drops:
        return None
    avg_recent = sum(recent_drops) / len(recent_drops)
    avg_prior = sum(prior_drops) / len(prior_drops)
    if avg_prior <= 0:
        return None
    if avg_recent < avg_prior * tp.get("decel"):
        return bar.close
    return None


def _tp4(
    tp: FadeTakeProfitCombo,
    bar: Bar1K,
    post_bars: list[Bar1K],
    profit: float,
) -> float | None:
    if profit < tp.get("min_profit"):
        return None
    n = int(tp.get("n"))
    if len(post_bars) < n + 2:
        return None
    window = post_bars[-(n + 2) : -1]
    if len(window) < n + 1:
        return None
    for i in range(1, len(window)):
        if window[i].low >= window[i - 1].low:
            return None
    return bar.close


def _tp5(
    tp: FadeTakeProfitCombo,
    bar: Bar1K,
    sample: FadeSample,
) -> float | None:
    gap = sample.t1_open - sample.limit
    if gap <= 0:
        return None
    fill_pct = tp.get("fill_pct")
    fill_level = sample.t1_open - fill_pct * gap
    if bar.low <= fill_level:
        return fill_level
    return None


def _tp6(
    tp: FadeTakeProfitCombo,
    bar: Bar1K,
    cum_pv: float,
    cum_vol: float,
) -> float | None:
    if cum_vol <= 0:
        return None
    vwap = cum_pv / cum_vol
    if vwap <= 0:
        return None
    dist = (vwap - bar.close) / vwap
    if dist >= tp.get("distance"):
        return bar.close
    return None


def _tp7(
    tp: FadeTakeProfitCombo,
    bar: Bar1K,
    entry: float,
    running_high: float,
    running_low: float,
) -> float | None:
    rng = running_high - running_low
    if rng <= 0:
        return None
    profit_abs = entry - bar.close
    capture = profit_abs / rng
    if capture >= tp.get("capture"):
        return bar.close
    return None


def _tp8(
    tp: FadeTakeProfitCombo,
    bar: Bar1K,
    post_bars: list[Bar1K],
    profit: float,
) -> float | None:
    if profit < tp.get("min_profit"):
        return None
    n = int(tp.get("n"))
    window = post_bars[-n:] if len(post_bars) >= n else post_bars
    if not window:
        return None
    up = sum(b.up_volume for b in window)
    dn = sum(b.down_volume for b in window)
    total = up + dn
    if total <= 0:
        return None
    if up / total >= tp.get("threshold"):
        return bar.close
    return None


def _tp9(
    tp: FadeTakeProfitCombo,
    bar: Bar1K,
    cum_delta: float,
    prev_cum_delta: float,
    profit: float,
) -> float | None:
    if profit < tp.get("min_profit"):
        return None
    if prev_cum_delta < 0 and cum_delta >= 0:
        return bar.close
    return None


def _tp10(
    tp: FadeTakeProfitCombo,
    bar: Bar1K,
    running_low: float,
    profit: float,
) -> float | None:
    if profit < tp.get("min_profit"):
        return None
    if bar.low > running_low:
        return None
    rng = bar.high - bar.low
    if rng <= 0:
        return None
    wick = (bar.close - bar.low) / rng
    if wick >= tp.get("wick"):
        return bar.close
    return None


def _tp11(
    tp: FadeTakeProfitCombo,
    bar: Bar1K,
    entry: float,
    elapsed_bars: int,
) -> float | None:
    initial = tp.get("initial")
    decay = tp.get("decay")
    target = initial * (decay**elapsed_bars)
    profit = 1.0 - bar.close / entry
    if profit >= target:
        return bar.close
    return None
