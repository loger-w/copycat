"""大盤特徵(MTX 小台指)— 日線 + 盤中 1K(design.md v2 §6d)."""

from __future__ import annotations

from copycat.data.models import Bar1K


def compute_mkt_daily_features(
    closes: list[tuple[str, float]],
    t_date: str,
) -> dict[str, float | None]:
    """MTX 日線特徵。closes = [(date, close), ...] 已排序。"""
    idx = None
    for i, (d, _) in enumerate(closes):
        if d == t_date:
            idx = i
            break
    if idx is None:
        return {"mkt_t_ret": None, "mkt_t_range_pos": None, "mkt_t5_ret": None}

    out: dict[str, float | None] = {}

    if idx >= 1:
        out["mkt_t_ret"] = closes[idx][1] / closes[idx - 1][1] - 1.0
    else:
        out["mkt_t_ret"] = None

    out["mkt_t_range_pos"] = None

    if idx >= 5:
        out["mkt_t5_ret"] = closes[idx][1] / closes[idx - 5][1] - 1.0
    else:
        out["mkt_t5_ret"] = None

    return out


def compute_mkt_daily_features_full(
    daily_rows: list[dict[str, float]],
    t_date: str,
    date_key: str = "date",
) -> dict[str, float | None]:
    """MTX 日線特徵(含 range_pos)。daily_rows 有 date/open/high/low/close 欄。"""
    idx = None
    for i, row in enumerate(daily_rows):
        if str(row.get(date_key, "")) == t_date:
            idx = i
            break
    if idx is None:
        return {"mkt_t_ret": None, "mkt_t_range_pos": None, "mkt_t5_ret": None}

    row = daily_rows[idx]
    out: dict[str, float | None] = {}

    if idx >= 1:
        prev_close = daily_rows[idx - 1].get("close")
        cur_close = row.get("close")
        if prev_close and cur_close and prev_close > 0:
            out["mkt_t_ret"] = cur_close / prev_close - 1.0
        else:
            out["mkt_t_ret"] = None
    else:
        out["mkt_t_ret"] = None

    hi = row.get("high")
    lo = row.get("low")
    cl = row.get("close")
    if hi is not None and lo is not None and cl is not None and hi > lo:
        out["mkt_t_range_pos"] = (cl - lo) / (hi - lo)
    else:
        out["mkt_t_range_pos"] = None

    if idx >= 5:
        prev5_close = daily_rows[idx - 5].get("close")
        cur_close = row.get("close")
        if prev5_close and cur_close and prev5_close > 0:
            out["mkt_t5_ret"] = cur_close / prev5_close - 1.0
        else:
            out["mkt_t5_ret"] = None
    else:
        out["mkt_t5_ret"] = None

    return out


def compute_mkt_intraday_features(
    mtx_bars: list[Bar1K],
    trigger_m: int,
) -> dict[str, float | None]:
    """MTX 1K 盤中特徵(在觸發 bar 時刻計算)。"""
    if not mtx_bars:
        return {
            "mkt_t1_ret_to_trigger": None,
            "mkt_t1_from_high": None,
            "mkt_t1_range_pos": None,
            "mkt_t1_inner": None,
        }

    open_px = mtx_bars[0].open
    window = [b for b in mtx_bars if b.m <= trigger_m]
    if not window:
        return {
            "mkt_t1_ret_to_trigger": None,
            "mkt_t1_from_high": None,
            "mkt_t1_range_pos": None,
            "mkt_t1_inner": None,
        }

    current = window[-1].close
    rolling_high = max(b.high for b in window)
    rolling_low = min(b.low for b in window)

    out: dict[str, float | None] = {}

    out["mkt_t1_ret_to_trigger"] = current / open_px - 1.0 if open_px > 0 else None

    out["mkt_t1_from_high"] = 1.0 - current / rolling_high if rolling_high > 0 else None

    rng = rolling_high - rolling_low
    out["mkt_t1_range_pos"] = (current - rolling_low) / rng if rng > 0 else None

    inner_n = 5
    inner_window = window[-inner_n:] if len(window) >= inner_n else window
    up = sum(b.up_volume for b in inner_window)
    dn = sum(b.down_volume for b in inner_window)
    total = up + dn
    out["mkt_t1_inner"] = dn / total if total > 0 else None

    return out
