"""連板數純函式(零 IO)—— SC-2。

輸入 = FinMind `TaiwanStockPrice` 的單日全市場 rows(無 data_id);輸出 = 該日
收盤漲停的普通股集合,再由 `compute_prev_streaks` 逐日交集遞進成連續漲停日數。

**記憶體紀律**:呼叫端(`server/breadth_engine.py`)逐日 fetch → 立即
`compute_day_limitups` → 丟棄 raw rows;本模組只吃 `list[set[str]]`。全市場單日
~3 萬列(含權證),10 日全持有是數百 MB 級,live server 內不可接受。

漲停判定與 `market_breadth._is_limit` 同口徑(毫元精確等值),但**前收來源不同**:
snapshot 有 `change_price`,EOD 只有 `spread` → `prev_close = close − spread`
(除權息參考價,neigui `DailyIndex.ref_prev_close` 同源;直接拿前一日 close 會在
除權息日整批誤判)。上市首五日無漲跌幅限制,close 天然不等於公式漲停價,自然不計。
"""

from __future__ import annotations

from copycat.market import limit_up_milli
from copycat.market_breadth import classify_stock_id

#: 回看交易日數(= streak 上限;撞頂由呼叫端以 `streak_capped` 表達)。
STREAK_WINDOW_DAYS = 10


def _to_float(value: object) -> float | None:
    """數值欄 → float;缺值 / 非數值 → None(`backfill_finmind._map_row` 同語意)。

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


def compute_day_limitups(rows: list[dict]) -> set[str]:
    """單日 TaiwanStockPrice 全市場 rows → 該日收盤漲停的 4 位普通股代號集合。

    - Universe:`classify_stock_id(sid) is None`(ETF / 權證 / 指數 row 全剃除)。
    - `prev_close = close − spread`;欄缺 / 非數值 / `prev_close <= 0` → 不判
      (該檔的 streak 於該日自然中斷)。
    - 漲停 = 毫元精確等值,無容差。
    """
    out: set[str] = set()
    for row in rows:
        sid = row.get("stock_id")
        if not isinstance(sid, str) or classify_stock_id(sid) is not None:
            continue
        close = _to_float(row.get("close"))
        spread = _to_float(row.get("spread"))
        if close is None or spread is None:
            continue
        prev_close = close - spread
        if prev_close <= 0:
            continue
        if round(close * 1000) == limit_up_milli(round(prev_close * 1000)):
            out.add(sid)
    return out


def compute_prev_streaks(day_sets: list[set[str]]) -> dict[str, int]:
    """`day_sets` = 連續交易日的漲停集合,**新 → 舊**排序(day_sets[0] = 最近可得
    交易日)。回傳 {stock_id: 截至 day_sets[0] 的連續漲停日數},只含 streak ≥ 1。

    演算法 = 交集遞進:候選 = day_sets[0],逐個較舊日取交集,存活者 +1。窗內缺 row
    的檔(新上市 / 停牌)不在該日集合 → 自然出局。streak 上限 = `len(day_sets)`。
    """
    if not day_sets:
        return {}
    candidates = set(day_sets[0])
    streaks = {sid: 1 for sid in candidates}
    for older in day_sets[1:]:
        candidates &= older
        if not candidates:
            break
        for sid in candidates:
            streaks[sid] += 1
    return streaks
