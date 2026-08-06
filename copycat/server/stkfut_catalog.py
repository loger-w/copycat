"""個股期合約目錄:當日 in-memory cache + 單飛 + 白名單查詢(stkfut-contracts SC-1)。

**不落檔**:合約每月換(第三週三到期後近月即從清單消失),檔案 cache 只是多一個會
過期的真相源;TC4 是唯一權威。當日 cache 的作用是「一天問一次」,不是可靠性。

**失敗與跨日都不得回退到舊日資料**:過期月份被畫進下拉 → 使用者選了之後訂閱零推播,
而 TC4 對不存在的 symbol 照回 `Success: OK`(CLAUDE.md §8),整條路徑毫無錯誤訊號。
所以跨日之後先作廢再抓,抓不到就 raise(route 轉 502),讓「查不到」是明確的。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date as _date
from typing import Callable

logger = logging.getLogger(__name__)


def _today() -> str:
    """本機日界(= 台北;部署綁本機,同 overlay / bars 的既有慣例)。"""
    return f"{_date.today():%Y-%m-%d}"


class StkfutCatalog:
    """`fetch` = 同步的 TC4 查詢(`TC4QuoteSource.list_stock_futures`),丟 to_thread 跑。"""

    def __init__(
        self,
        fetch: Callable[[], dict[str, dict]],
        *,
        today: Callable[[], str] = _today,
    ) -> None:
        self._fetch = fetch
        self._today = today
        self._day: str | None = None
        self._data: dict[str, dict] | None = None
        # 單飛:開盤瞬間多個 client 同時開下拉,不可對 TC4 併發送同一份查詢
        # (QUERYALLINSTRUMENT 是重呼叫,Opt 實測 1.93s)
        self._lock = asyncio.Lock()

    async def _load(self) -> dict[str, dict]:
        day = self._today()
        async with self._lock:
            if self._day == day and self._data is not None:
                return self._data
            # 先作廢再抓:抓取失敗時不得留下「昨天的合約清單」可回
            self._day = None
            self._data = None
            data = await asyncio.to_thread(self._fetch)
            self._day, self._data = day, data
            logger.info("stkfut catalog 更新:%d 檔(%s)", len(data), day)
            return data

    async def prewarm(self) -> None:
        """boot 尾段預熱(code review A3):把冷查詢移出盤中熱路徑。

        冷 cache 的第一次 `QUERYALLINSTRUMENT(Fut2)` 是**秒級且持鎖**(Opt 實測 1.93s)
        —— 沒有預熱的話,開盤第一個打開合約下拉的請求要等它,而那正是最不能等的時刻。

        **失敗只 log 不拋**:TC4 沒開的早上照樣要開得起來(同 `_boot` 的降級語意),
        代價僅是退回「第一次請求時再查」的既有行為。
        """
        try:
            await self._load()
        except Exception:
            logger.warning("stkfut catalog 預熱失敗(降級:第一次請求時再查)", exc_info=True)

    async def get(self, code: str) -> dict | None:
        """股號 → `{name, std, mini}`;無期貨 → None。查詢失敗原樣拋(route 轉 502)。"""
        return (await self._load()).get(code)

    async def contains(self, code: str, prod: str, ym: str) -> bool:
        """`?contract=` 白名單:prod 屬該股號(標準或小型)且 ym 在該產品的月份清單內。

        沒有這道閘,使用者可以把 `/api/stock/state/2330?contract=EEF:202609` 打進來 ——
        主圖畫的是國喬期貨,而 URL 與下單面的股號是台積電。
        """
        entry = await self.get(code)
        if entry is None:
            return False
        for leg in (entry.get("std"), entry.get("mini")):
            if leg is not None and leg["prod"] == prod and ym in leg["contracts"]:
                return True
        return False
