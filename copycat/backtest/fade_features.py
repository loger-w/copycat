"""T+1 Fade 竭盡特徵(design.md v2 §6e/6f/6g)— 觸發 bar 時點計算,零 IO.

~224 欄:盤中基礎 7 + 微結構 189 + 鎖板品質 5 + T+1 開盤 3 + 靜態位階 10 + 大盤 7 + 鎖死風險 3。
"""

from __future__ import annotations

from copycat.data.models import Bar1K


def _safe_div(a: float, b: float) -> float | None:
    return a / b if b != 0 else None


def _intraday_basic(bars: list[Bar1K], trig_idx: int) -> dict[str, float | None]:
    """盤中基礎 7 欄(§6e)."""
    w = bars[: trig_idx + 1]
    out: dict[str, float | None] = {}

    if len(w) >= 4:
        ranges = [(b.high - b.low) for b in w[:-1]]
        avg_range = sum(ranges[-3:]) / 3 if len(ranges) >= 3 else sum(ranges) / len(ranges)
        cur_range = w[-1].high - w[-1].low
        out["bar_range_expansion"] = _safe_div(cur_range, avg_range)
    else:
        out["bar_range_expansion"] = None

    if len(w) >= 7:
        slope_3 = (w[-1].close - w[-4].close) / w[-4].close / 3 if w[-4].close > 0 else None
        slope_6 = (w[-1].close - w[-7].close) / w[-7].close / 6 if w[-7].close > 0 else None
        if slope_3 is not None and slope_6 is not None and slope_6 != 0:
            out["momentum_decel"] = slope_3 / slope_6
        else:
            out["momentum_decel"] = None
    else:
        out["momentum_decel"] = None

    cum_pv = sum(b.close * b.volume for b in w)
    cum_v = sum(b.volume for b in w)
    if cum_v > 0:
        vwap = cum_pv / cum_v
        above_vol = sum(b.volume for b in w if b.close >= vwap)
        below_vol = sum(b.volume for b in w if b.close < vwap)
        out["volume_profile_skew"] = _safe_div(above_vol, below_vol)
    else:
        out["volume_profile_skew"] = None

    red_count = 0
    for b in reversed(w[:-1]):
        if b.close < b.open:
            red_count += 1
        else:
            break
    out["consecutive_red"] = float(red_count)

    open_px = w[0].open
    limit_prev = open_px  # fallback
    current = w[-1].close
    if open_px > 0:
        out["gap_fill_pct"] = (open_px - current) / open_px if open_px != limit_prev else None
    else:
        out["gap_fill_pct"] = None

    rolling_high_idx = 0
    rolling_high = 0.0
    for i, b in enumerate(w):
        if b.high > rolling_high:
            rolling_high = b.high
            rolling_high_idx = i
    out["time_since_high"] = float(trig_idx - rolling_high_idx)

    if w[0].open > 0:
        out["auction_direction"] = w[0].close / w[0].open - 1.0
    else:
        out["auction_direction"] = None

    return out


def _unch_vol_spike(bars: list[Bar1K], trig_idx: int) -> dict[str, float | None]:
    """unch_vol_spike 8 欄(§6f)."""
    w = bars[: trig_idx + 1]
    ns = [1, 2, 3, 4, 5, 6, 8, 10]
    out: dict[str, float | None] = {}
    for n in ns:
        window = w[-n:] if len(w) >= n else w
        vals = [b.unch_volume / b.volume for b in window if b.volume > 0]
        out[f"unch_vol_spike_n{n}"] = sum(vals) / len(vals) if vals else None
    return out


def _price_vol_divergence(bars: list[Bar1K], trig_idx: int) -> dict[str, float | None]:
    """price_vol_divergence 45 欄(§6f)."""
    w = bars[: trig_idx + 1]
    ns = [3, 4, 5, 6, 7, 8, 10, 12, 15]
    ds = [0.00, 0.05, 0.10, 0.15, 0.20]
    out: dict[str, float | None] = {}
    for n in ns:
        if len(w) < n:
            for d in ds:
                out[f"pvd_n{n}_d{int(d * 100)}"] = None
            continue
        window = w[-n:]
        for d in ds:
            count = 0
            for i in range(1, len(window)):
                if window[i].high > window[i - 1].high and window[i].volume < window[
                    i - 1
                ].volume * (1 - d):
                    count += 1
            out[f"pvd_n{n}_d{int(d * 100)}"] = count / (len(window) - 1)
    return out


def _open_eq_high_count(bars: list[Bar1K], trig_idx: int) -> dict[str, float | None]:
    """open_eq_high_count 64 欄(§6f)."""
    w = bars[: trig_idx + 1]
    ns = [3, 4, 5, 6, 8, 10, 12, 15]
    tols = [0.0002, 0.0005, 0.0008, 0.0010, 0.0015, 0.0020, 0.0030, 0.0050]
    out: dict[str, float | None] = {}
    for n in ns:
        if len(w) < n:
            for t in tols:
                out[f"oeh_n{n}_t{int(t * 10000)}"] = None
            continue
        window = w[-n:]
        for t in tols:
            count = sum(1 for b in window if b.open > 0 and (b.high - b.open) / b.open < t)
            out[f"oeh_n{n}_t{int(t * 10000)}"] = count / len(window)
    return out


def _bid_exhaustion(bars: list[Bar1K], trig_idx: int) -> dict[str, float | None]:
    """bid_exhaustion 40 欄(§6f)."""
    w = bars[: trig_idx + 1]
    thresholds = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45]
    lookbacks = [5, 10, 15, 20, 30]
    out: dict[str, float | None] = {}
    for thr in thresholds:
        for lb in lookbacks:
            window = w[-lb:] if len(w) >= lb else w
            count = 0
            for b in reversed(window):
                total = b.up_volume + b.down_volume
                if total > 0 and b.up_volume / total < thr:
                    count += 1
                else:
                    break
            out[f"bidex_t{int(thr * 100)}_lb{lb}"] = float(count)
    return out


def _speed_of_decline(bars: list[Bar1K], trig_idx: int) -> dict[str, float | None]:
    """speed_of_decline 12 欄(速率 7 + 加速度 5)(§6f)."""
    w = bars[: trig_idx + 1]
    out: dict[str, float | None] = {}

    for n in [2, 3, 4, 5, 6, 8, 10]:
        if len(w) > n and w[-(n + 1)].close > 0:
            out[f"decline_speed_n{n}"] = (w[-(n + 1)].close - w[-1].close) / w[-(n + 1)].close / n
        else:
            out[f"decline_speed_n{n}"] = None

    for n in [4, 6, 8, 10, 12]:
        half = n // 2
        if len(w) > n and w[-(n + 1)].close > 0 and w[-(half + 1)].close > 0:
            front = (w[-(n + 1)].close - w[-(half + 1)].close) / w[-(n + 1)].close
            back = (w[-(half + 1)].close - w[-1].close) / w[-(half + 1)].close
            out[f"decline_accel_n{n}"] = _safe_div(back, front) if front != 0 else None
        else:
            out[f"decline_accel_n{n}"] = None

    return out


def _retest_failure(bars: list[Bar1K], trig_idx: int) -> dict[str, float | None]:
    """retest_failure 12 欄(6 二元 + 6 連續)(§6f)."""
    w = bars[: trig_idx + 1]
    out: dict[str, float | None] = {}
    nears = [0.001, 0.002, 0.003, 0.005, 0.008, 0.010]

    peak = 0.0
    peak_idx = 0
    for i, b in enumerate(w):
        if b.high > peak:
            peak = b.high
            peak_idx = i

    for near in nears:
        tag = int(near * 10000)
        if peak <= 0 or peak_idx >= len(w) - 1:
            out[f"retest_fail_nr{tag}"] = 0.0
            out[f"retest_depth_nr{tag}"] = None
            continue
        retest_high = 0.0
        found = False
        for b in w[peak_idx + 1 :]:
            if b.high >= peak * (1 - near) and b.high < peak:
                found = True
                retest_high = max(retest_high, b.high)
        out[f"retest_fail_nr{tag}"] = 1.0 if found else 0.0
        out[f"retest_depth_nr{tag}"] = (peak - retest_high) / peak if found else None

    return out


def _auction_mismatch(bars: list[Bar1K], trig_idx: int) -> dict[str, float | None]:
    """auction_mismatch 8 欄(§6f)."""
    w = bars[: trig_idx + 1]
    ns = [2, 3, 4, 5, 6, 8, 10, 15]
    out: dict[str, float | None] = {}
    if len(w) < 2 or w[0].volume <= 0:
        for n in ns:
            out[f"auc_mismatch_n{n}"] = None
        return out
    auction_vol = w[0].volume
    for n in ns:
        subsequent = w[1 : n + 1]
        if not subsequent:
            out[f"auc_mismatch_n{n}"] = None
            continue
        avg = sum(b.volume for b in subsequent) / len(subsequent)
        out[f"auc_mismatch_n{n}"] = _safe_div(auction_vol, avg)
    return out


def fade_trigger_features(
    bars: list[Bar1K],
    trig_idx: int,
    lock_features: dict[str, float | None] | None,
    t1_features: dict[str, float | None] | None,
    static_features: dict[str, float | None] | None,
    mkt_daily: dict[str, float | None] | None,
    mkt_intraday: dict[str, float | None] | None,
) -> dict[str, float | None]:
    """觸發時點全特徵 ~224 欄."""
    out: dict[str, float | None] = {}

    out.update(_intraday_basic(bars, trig_idx))
    out.update(_unch_vol_spike(bars, trig_idx))
    out.update(_price_vol_divergence(bars, trig_idx))
    out.update(_open_eq_high_count(bars, trig_idx))
    out.update(_bid_exhaustion(bars, trig_idx))
    out.update(_speed_of_decline(bars, trig_idx))
    out.update(_retest_failure(bars, trig_idx))
    out.update(_auction_mismatch(bars, trig_idx))

    if lock_features:
        out.update(lock_features)
    if t1_features:
        out.update(t1_features)
    if static_features:
        out.update(static_features)
    if mkt_daily:
        out.update(mkt_daily)
    if mkt_intraday:
        out.update(mkt_intraday)

    return out
