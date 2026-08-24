"""1K 當日回補的共用收割器(SC-3;`corr_source` 與 `futures_source` 各自的 session 都用它)。

**為什麼吃 callable 而不是吃 source 物件**:`_sub_history` / `_get_history` 是 `TC4QuoteSource`
的保護成員,從模組外面點進去是壞味道;各 source 傳自己的 bound method 進來即可,DRY 又不
碰別人的私有面。`stock_source._collect_history` 是同型邏輯的既有實作(那條服務 K 線 / overlay,
語意與參數已被四個呼叫點綁住,不在本輪動它;共用化條件記 `docs/next-time.md`)。

**為什麼回補要各走自己的 session**:台指 `TC.F.TWF.TXF.HOT` 的 REALTIME 訂閱在 futures
session 手上 → 台指的 1K 也必須從那條 session 問,不可從 corr session 發。corr 那邊發等於
對同一個 symbol 多掛一把 TC4 refcount key,而上游 feed 以 symbol 為單位 —— 那把 key 歸零就
把整個 symbol 的推播帶走(2026-08-18 實證,見 `.claude/skills/tc4-market-facts/SKILL.md`)。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from copycat.live.river_models import all_day_utc_window, parse_1k_minutes
from copycat.live.tc4 import HistoryTimeoutError
from copycat.tc4common import iter_qry_pages

logger = logging.getLogger(__name__)

__all__ = ["collect_1k_minutes"]

#: 首頁備妥的等待預算 = poll_wait × 10(沿用 stock_source 的「退避輪詢 + 上限」形狀,
#: 但預算比歷史 K 線路徑短:回補跑在背景,拉不到就降級成「只累積」,不值得等滿 30s)
_POLL_BUDGET_FACTOR = 10.0
_POLL_BACKOFF_START = 0.15


def collect_1k_minutes(
    *,
    sub_history: Callable[[str, str, str, str], Any],
    get_history: Callable[[str, str, str, str, str], dict],
    symbol: str,
    poll_wait: float,
) -> list[tuple[int, int]]:
    """SubHistory(1K)→ 首頁退避輪詢 → QryIndex 收割 → `[(minute_end, close 毫點)]`。

    **首頁在預算內未備妥 → `HistoryTimeoutError`**(2026-08-23 08:23 事故:TXF/TWN/SXF
    三腿同秒逾時回空 → 引擎讀成「這幾腿今天沒有 1K」,整天不再回補而江波圖缺前半段)。
    回空是唯一把「暫時取不到」這個訊號丟掉的地方;**首頁備妥但收割 0 列仍回 `[]`**
    —— TC4 答得出首頁就代表它不忙,空就是空,不該讓引擎排重試。
    `poll_wait == 0` 是測試組態,語意 = 不等待(探測一次就回,不 busy loop)。
    TC4 通訊失敗由 `_req` 收斂成 `ConnectionError` 往外拋 —— 引擎層逐腿降級,不在這裡吞
    (`HistoryTimeoutError` 是它的子類,所以沒特別處置的呼叫端行為不變)。
    """
    start, end = all_day_utc_window()
    sub_history(symbol, start, end, "1K")
    budget = max(poll_wait * _POLL_BUDGET_FACTOR, 1.0)
    deadline = time.monotonic() + budget
    wait = min(_POLL_BACKOFF_START, poll_wait)
    while True:
        first = get_history(symbol, start, end, "0", "1K")
        if first.get("HisData"):
            break
        remaining = deadline - time.monotonic()
        if wait <= 0 or remaining <= 0:
            logger.info("1K 回補 %s:%.1fs 內首頁未備妥(timeout,非無資料)", symbol, budget)
            raise HistoryTimeoutError(f"1K 回補 {symbol}:{budget:.1f}s 內首頁未備妥")
        time.sleep(min(wait, remaining))
        wait = min(wait * 2, poll_wait)

    def _page(qry_index: str) -> list[dict]:
        return get_history(symbol, start, end, qry_index, "1K").get("HisData", [])

    rows: list[dict] = []
    for page in iter_qry_pages(_page):
        rows.extend(page)
    # 窗口日比對交給 parse_1k_minutes(純 UTC,不做台北換算 —— 窗本身就是 UTC 全天窗)
    parsed = parse_1k_minutes(rows, start[:8])
    minutes = parsed.minutes
    if rows and not minutes and not parsed.skipped:
        # 沿 `stock_source._taipei_minute_key` 那條的固定字串:rows 非空但一分鐘都留不下來
        # = 毒化 / 凍結的 history 訂閱簽名。
        # **`not parsed.skipped` 是判準的一半**:欄位缺漏 / 格式壞掉也會讓 minutes 全空,
        # 但那要查的是 TC4 換沒換欄名,不是換窗口逃逸。誤報會讓這句固定字串(這條路上
        # 唯一的 grep 判準)失去診斷力,而 `parse_1k_minutes` 對 skipped 另有自己的 warning。
        #
        # **回空 → 拋 `HistoryTimeoutError`**(N092:ready-check 三態化):「首頁非空即
        # break」擋不住凍結 stub —— break 出來的是一列假資料,`timed_out` 為 False,
        # 呼叫端拿到空 list 讀成「這條腿今天沒有 1K」而整天不再回補(與 08-23 三腿同秒
        # 逾時同一個失效)。凍結 stub 的語意恰恰是「**現在**取不到,不是沒有」= 這個
        # 例外的語意;它是 `ConnectionError` 子類,只寫 `except ConnectionError` 的呼叫端
        # 行為不變,而 `corr_engine` 的逾時重補階梯(3 輪、每 30 s)就此接得到手。
        logger.warning("1K 回補 %s:%d 列全數丟棄(疑似凍結 stub)", symbol, len(rows))
        raise HistoryTimeoutError(f"1K 回補 {symbol}:{len(rows)} 列全數丟棄(疑似凍結 stub)")
    logger.info("1K 回補 %s:%d 列 → %d 分鐘", symbol, len(rows), len(minutes))
    return minutes
