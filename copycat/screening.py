"""盤前選股篩選純函式(零 IO)—— spec issue #173。

輸入 = 逐日全市場 FinMind `TaiwanStockPrice` rows(新→舊)+ 當沖資格 / 處置集合,
輸出 = 排序後候選名單。三硬條件:

1. 還原 20 日漲幅 ≥ +15% —— 還原係數自算:`prev_ref = close − spread`(除權息參考價,
   與 `limit_streaks` 同口徑),`ratio = Π(close / prev_ref)`。除權息日 prev_ref ≠ 前日
   close,係數鏈自動吸收;不需要逐檔查 `TaiwanStockPriceAdj`(那支 data_id 必填,全市場
   拉還原價要 ~1,800 次請求/晚)。
2. 窗內**收盤鎖板** ≥ 1 次(`close == limit_up(prev_ref)` 毫元精確等值;摸板不算)。
3. 均量 ≥ 5,000 張 —— 母體 = 基準日(最舊)以外的轉換日(「20 日均量」的 20 天)。

**記憶體紀律**(`limit_streaks` 同款):呼叫端逐日 fetch → 立即餵進來 → 丟棄 raw rows
的設計不適用於本模組 —— 係數鏈要跨日連乘,必須整窗持有;但只持有 4 位普通股的
(close, spread, volume) 三元組,~2,000 檔 × 21 日,KB 級。
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

from copycat.market import limit_up_milli
from copycat.market_breadth import classify_stock_id

#: 窗口交易日數(21 個收盤 = 20 個交易日轉換)—— 引擎抓取天數的單一來源。
WINDOW_DAYS = 21
#: 還原 20 日漲幅門檻(%)。
RET_MIN_PCT = 15.0
#: 20 日均量門檻(張)。
AVG_LOTS_MIN = 5000.0


@dataclass(frozen=True)
class ScreenCandidate:
    code: str
    ret_pct: float  # 還原 20 日漲幅(%)
    avg_lots: float  # 20 日均量(張)
    lock_dates: tuple[_dt.date, ...]  # 收盤鎖板日,新→舊(至少一筆)


def _to_float(value: object) -> float | None:
    """數值欄 → float;缺值 / 非數值 → None(`limit_streaks._to_float` 同語意)。

    `bool` 明確排除:True 靜默變 1.0 會推出荒謬前收。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def hard_candidates(days: list[tuple[_dt.date, list[dict]]]) -> list[ScreenCandidate]:
    """三硬條件 + universe + 排序。`days` = (交易日, 全市場 rows),**新→舊**。

    - Universe:`classify_stock_id(sid) is None`(ETF / 權證 / 指數 row 全剃除)。
    - 窗內缺日(新上市 / 停牌)或任一轉換日欄缺 / prev_ref ≤ 0 → 該檔不判。
    - 排序:最近鎖板日新→舊,同日比還原漲幅 desc。
    """
    n_days = len(days)
    if n_days < 2:
        return []
    dates = [d for d, _ in days]
    # per stock: {day_index: (close, spread_or_None, volume_shares)},index 0 = 最新
    series: dict[str, dict[int, tuple[float, float | None, float]]] = {}
    for idx, (_, rows) in enumerate(days):
        for row in rows:
            sid = row.get("stock_id")
            if not isinstance(sid, str) or classify_stock_id(sid) is not None:
                continue
            close = _to_float(row.get("close"))
            if close is None or close <= 0:
                continue
            spread = _to_float(row.get("spread"))
            volume = _to_float(row.get("Trading_Volume")) or 0.0
            series.setdefault(sid, {})[idx] = (close, spread, volume)

    out: list[ScreenCandidate] = []
    for sid, per_day in series.items():
        if len(per_day) < n_days:
            continue  # 窗內缺日
        ratio = 1.0
        vol_sum = 0.0
        lock_dates: list[_dt.date] = []
        usable = True
        # 由舊到新走轉換日(最舊 = 基準日,只出 close,量也不計)
        for idx in range(n_days - 2, -1, -1):
            close, spread, volume = per_day[idx]
            if spread is None:
                usable = False
                break
            prev_ref = close - spread
            if prev_ref <= 0:
                usable = False
                break
            ratio *= close / prev_ref
            vol_sum += volume
            if round(close * 1000) == limit_up_milli(round(prev_ref * 1000)):
                lock_dates.append(dates[idx])
        if not usable or not lock_dates:
            continue
        ret_pct = (ratio - 1.0) * 100.0
        avg_lots = vol_sum / (n_days - 1) / 1000.0
        if ret_pct < RET_MIN_PCT or avg_lots < AVG_LOTS_MIN:
            continue
        lock_dates.reverse()  # 新→舊
        out.append(
            ScreenCandidate(
                code=sid, ret_pct=ret_pct, avg_lots=avg_lots, lock_dates=tuple(lock_dates)
            )
        )
    out.sort(key=lambda c: (c.lock_dates[0], c.ret_pct), reverse=True)
    return out


def apply_eligibility(
    candidates: list[ScreenCandidate],
    *,
    daytrade_ok: set[str],
    disposed: set[str],
) -> list[ScreenCandidate]:
    """當沖資格 + 處置股過濾,保序。

    `daytrade_ok` = 逐檔查 `TaiwanStockDayTrading` 最近交易日**有列**的代號集合
    (僅先買後賣照收 —— 2026-09-01 grilling Q15 拍板);`disposed` = 處置期間
    涵蓋今日的代號集合(`parse_active_disposition` 產出)。
    """
    return [c for c in candidates if c.code in daytrade_ok and c.code not in disposed]
