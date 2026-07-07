"""觸發時點特徵(neigui extract_trigger_features.py 同源移植;characterization 錨點 SC-2)
與位階特徵族(T-1,SC-3)— 零 IO,bars / DailyIndex 由 caller 注入。

公式與 guard 逐條對照 PLAN.md 對照表;偏離 neigui 之處(觸發 eps、匯入層清洗)
已列 characterization 已知差異。
"""

from __future__ import annotations

from copycat.backtest.config import BacktestConfig
from copycat.data.daily import DailyIndex
from copycat.data.models import Bar1K


def find_trigger(bars: list[Bar1K], prev_close: float, theta: float, eps: float) -> int | None:
    """第一根 high ≥ prev_close×(1+θ) − eps 的 bar index;無 → None."""
    threshold = prev_close * (1.0 + theta) - eps
    for i, b in enumerate(bars):
        if b.high >= threshold:
            return i
    return None


def avg20_t1(daily: DailyIndex, stock_id: str, t_date: str) -> float | None:
    """20 日均量(張),基準 = T-1(neigui prevs[-20:] 同源,不含 T 日)."""
    prev = daily.prev_date(stock_id, t_date)
    if prev is None:
        return None
    return daily.adv20(stock_id, prev)


def trigger_features(
    bars: list[Bar1K],
    trig_idx: int,
    prev_close: float,
    theta: float,
    avg20_lots: float,
    static: dict[str, float | bool | None],
    tb_upper: float = 0.075,
    tb_lower: float = 0.07,
) -> dict[str, float | None]:
    """觸發窗 w = bars[:trig_idx+1] 上的 13 盤中特徵 + 靜態 6 欄(bool → 1.0/0.0)."""
    w = bars[: trig_idx + 1]
    pc = prev_close
    gap = w[0].open / pc - 1.0
    cum_v = sum(b.volume for b in w)
    avg_min_v = avg20_lots / 270.0 if avg20_lots > 0 else None

    burst3 = 0.0
    last = len(w) - 1
    for i in range(len(w)):
        if w[i].open > 0:
            j = min(last, i + 2)
            burst3 = max(burst3, w[j].close / w[i].open - 1.0)

    run_hi = 0.0
    max_pb = 0.0
    for b in w:
        run_hi = max(run_hi, b.high)
        if run_hi > 0:
            max_pb = max(max_pb, 1.0 - b.low / run_hi)

    wash = 0
    if avg_min_v:
        wash = sum(
            1
            for b in w
            if b.volume >= 5 * avg_min_v and b.open > 0 and abs(b.close - b.open) / b.open < 0.002
        )

    uv = sum(b.up_volume for b in w)
    dv = sum(b.down_volume for b in w)

    touches = 0
    above = False
    for b in w:
        if b.high / pc - 1.0 >= tb_upper and not above:  # 門檻固定,不隨 θ 縮放(同源)
            above = True
        elif above and b.close / pc - 1.0 < tb_lower:
            touches += 1
            above = False

    trig_min = w[-1].m
    out: dict[str, float | None] = {
        "trig_min": float(trig_min),
        "gap_open": gap,
        "auction_lots": w[0].volume,
        "auction_vol_ratio": w[0].volume / avg20_lots if avg20_lots > 0 else None,
        "climb_rate": (theta - gap) / max(1, trig_min),
        "burst3": burst3,
        "up_min_frac": sum(1 for b in w if b.close > b.open) / len(w),
        "max_pullback": max_pb,
        "cumvol_ratio": cum_v / avg20_lots if avg20_lots > 0 else None,
        "max_minvol_x": max(b.volume for b in w) / avg_min_v if avg_min_v else None,
        "wash_bars": float(wash),
        "outer_ratio": uv / (uv + dv) if uv + dv > 0 else None,
        "touches_back": float(touches),
    }
    for key, value in static.items():
        if isinstance(value, bool):
            out[key] = 1.0 if value else 0.0
        else:
            out[key] = value
    return out


def static_features(
    daily: DailyIndex, stock_id: str, t_date: str
) -> dict[str, float | bool | None] | None:
    """靜態 6 欄(neigui daily_ctx 同源;dtr_t1 Phase A 無資料源 → None)."""
    prev = daily.prev_date(stock_id, t_date)
    if prev is None:
        return None
    c1 = daily.close_of(stock_id, prev)
    v1 = daily.volume_of(stock_id, prev)
    d6 = daily.shift_date(stock_id, t_date, 6)
    d21 = daily.shift_date(stock_id, t_date, 21)
    c6 = daily.close_of(stock_id, d6) if d6 else None
    c21 = daily.close_of(stock_id, d21) if d21 else None
    pc = daily.ref_prev_close(stock_id, t_date)
    if c1 is None or v1 is None or pc is None:
        return None
    return {
        # neigui v1 為股、我方 volume_lots 為張 → 金額(百萬)= 張×1000×價/1e6 = 張×價/1e3
        "amt_t1_m": v1 * c1 / 1e3,
        "ret5": c1 / c6 - 1.0 if c6 and c6 > 0 else None,
        "ret20": c1 / c21 - 1.0 if c21 and c21 > 0 else None,
        "prev_limitup": daily.is_limitup(stock_id, prev),
        "dtr_t1": None,  # Phase A 無當沖資料源(報告 known limitation)
        "prev_close": pc,
    }


def structural_features(
    daily: DailyIndex, stock_id: str, t_date: str, cfg: BacktestConfig
) -> dict[str, float | None]:
    """位階特徵族(全部以 T-1 為基準,無 lookahead)."""
    prev = daily.prev_date(stock_id, t_date)
    if prev is None:
        return {
            "dist_ma20": None,
            "dist_ma60": None,
            "bb_width_pct120": None,
            "pos_52w": None,
            "ignition_first": None,
        }
    close = daily.close_of(stock_id, prev)
    ma20 = daily.ma(stock_id, prev, 20)
    ma60 = daily.ma(stock_id, prev, 60)
    return {
        "dist_ma20": close / ma20 - 1.0 if close and ma20 and ma20 > 0 else None,
        "dist_ma60": close / ma60 - 1.0 if close and ma60 and ma60 > 0 else None,
        "bb_width_pct120": daily.bb_width_pct(stock_id, prev, 20, 2.0, 120),
        "pos_52w": daily.pos_52w(stock_id, prev),
        "ignition_first": _ignition_first(daily, stock_id, t_date, cfg),
    }


def _ignition_first(
    daily: DailyIndex, stock_id: str, t_date: str, cfg: BacktestConfig
) -> float | None:
    """啟動第一根:近 lookback 日未觸 +θ、近 5 日盤整、近 N 日無漲停(全部 T-1 止)."""
    prev = daily.prev_date(stock_id, t_date)
    if prev is None:
        return None
    # 近 lookback 日(含 T-1)是否觸過 +θ(以各日 high / 各日參考前收)
    d = prev
    for _ in range(cfg.ignition_lookback):
        ohlc = daily.ohlc(stock_id, d)
        rpc = daily.ref_prev_close(stock_id, d)
        if ohlc is not None and rpc is not None and ohlc[1] / rpc - 1.0 >= cfg.ignition_touch_theta:
            return 0.0
        nxt = daily.prev_date(stock_id, d)
        if nxt is None:
            break
        d = nxt
    # 近 5 日盤整:|ret5| ≤ 閾值
    d6 = daily.shift_date(stock_id, t_date, 6)
    c1 = daily.close_of(stock_id, prev)
    c6 = daily.close_of(stock_id, d6) if d6 else None
    if c1 is None or c6 is None or c6 <= 0:
        return None
    if abs(c1 / c6 - 1.0) > cfg.ignition_ret5_abs:
        return 0.0
    # 近 N 日無漲停
    d = prev
    for _ in range(cfg.ignition_days_since_limitup):
        if daily.is_limitup(stock_id, d):
            return 0.0
        nxt = daily.prev_date(stock_id, d)
        if nxt is None:
            break
        d = nxt
    return 1.0
