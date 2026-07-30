"""1K 當日回補的共用收割器(SC-3;`corr_source` 與 `futures_source` 各自的 session 都用它)。

**為什麼吃 callable 而不是吃 source 物件**:`_sub_history` / `_get_history` 是 `TC4QuoteSource`
的保護成員,從模組外面點進去是壞味道;各 source 傳自己的 bound method 進來即可,DRY 又不
碰別人的私有面。`stock_source._collect_history` 是同型邏輯的既有實作(那條服務 K 線 / overlay,
語意與參數已被四個呼叫點綁住,不在本輪動它;共用化條件記 `docs/next-time.md`)。

**為什麼回補要各走自己的 session**:TC4 同 symbol 跨 session 只推一邊(CLAUDE.md §8),
台指 `TC.F.TWF.TXF.HOT` 的訂閱在 futures session 手上 → 台指的 1K 也必須從那條 session 問,
不可從 corr session 發(疑似與既有 bug 1 同源)。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from copycat.live.river_models import all_day_utc_window, parse_1k_minutes
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

    首頁在預算內未備妥 → 回 `[]`(呼叫端據此降級為「只從啟動後累積」)。
    `poll_wait == 0` 是測試組態,語意 = 不等待(探測一次就回,不 busy loop)。
    TC4 通訊失敗由 `_req` 收斂成 `ConnectionError` 往外拋 —— 引擎層逐腿降級,不在這裡吞。
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
            logger.info("1K 回補 %s:%.1fs 內首頁未備妥,回空", symbol, budget)
            return []
        time.sleep(min(wait, remaining))
        wait = min(wait * 2, poll_wait)

    def _page(qry_index: str) -> list[dict]:
        return get_history(symbol, start, end, qry_index, "1K").get("HisData", [])

    rows: list[dict] = []
    for page in iter_qry_pages(_page):
        rows.extend(page)
    minutes = parse_1k_minutes(rows)
    logger.info("1K 回補 %s:%d 列 → %d 分鐘", symbol, len(rows), len(minutes))
    return minutes
