"""server 引擎 source 的共用 fake(index / futures / corr / stock)。

`fake_txo.py` 同款理由:同一個 Protocol 的 fake 散在八個測試檔各抄一份,Protocol 一改
就要八處同步,漏一處是 pyright 才會發現的靜默分岔。這裡各型別收斂成一份,內容取各檔
變體的**功能聯集**(記錄用的 list 一律保留 —— 多記幾筆不會改變被測行為,少記一筆就是
另一個檔的斷言失效)。

**特化行為不併進來**:`test_market_routes` 的 `NoHistoryIndexSource`(刻意缺
`fetch_bars_range_tagged`)、固定回傳的 `ZeroVol` / `Empty` / `Fixed` 都是「這條測試要的
那一種來源」,留在各檔以繼承覆寫表達。
"""

from __future__ import annotations

import datetime as _dt
from typing import Callable


def dbar(t: str, c: int) -> dict:
    """日 K bar 治具(毫點;h/l 各 ±1000,v 固定 10)。"""
    return {"t": t, "o": c, "h": c + 1000, "l": c - 1000, "c": c, "v": 10}


DEFAULT_DAILY = [
    dbar("2026-07-27", 23_000_000),
    dbar("2026-07-28", 23_100_000),
    dbar("2026-07-29", 23_200_000),
]


class FakeIndexSource:
    """IndexSource fake(index engine / index routes / market routes 共用)。

    - `day_minutes` 可指派成 `Exception` → `fetch_day_minutes` 拋(回補失敗路徑)。
    - `subscribe_error` 指派後 `subscribe_symbol` 拋(訂閱降級 / retry 路徑)。
    - `fetch_bars_range_tagged` 的 tag 與日 K 內容由建構子參數決定(market route 的
      「meta.source 必須是實際走到的分支」那組測試用)。
    """

    def __init__(
        self,
        *,
        day_minutes: dict[str, int] | None = None,
        tag: str = "tc4_dk",
        daily_bars: list[dict] | None = None,
    ) -> None:
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.trade_dates: list[str] = []
        self.day_minutes: dict[str, int] | Exception = {} if day_minutes is None else day_minutes
        self.on_message: Callable[[dict], None] | None = None
        self.subscribe_error: Exception | None = None
        self.closed = False
        self.calls: list[tuple[str, str, str, str]] = []
        self._tag = tag
        self._daily = DEFAULT_DAILY if daily_bars is None else daily_bars

    def subscribe_symbol(self, code: str) -> None:
        if self.subscribe_error is not None:
            raise self.subscribe_error
        self.subscribed.append(code)

    def unsubscribe_symbol(self, code: str) -> None:
        self.unsubscribed.append(code)

    def fetch_day_minutes(self, code: str) -> dict[str, int]:
        if isinstance(self.day_minutes, Exception):
            raise self.day_minutes
        return dict(self.day_minutes)

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        self.on_message = cb

    def set_trade_date(self, trade_date: str) -> None:
        self.trade_dates.append(trade_date)

    def close(self) -> None:
        self.closed = True

    def fetch_bars_range_tagged(
        self, code: str, tf: str, start: str, end: str
    ) -> tuple[list[dict], str]:
        self.calls.append((code, tf, start, end))
        if tf == "1":
            today = f"{_dt.date.today():%Y-%m-%d}"
            return [{"t": f"{today} 09:01", "o": 1, "h": 2, "l": 0, "c": 1, "v": 3}], "tc4_1k"
        # 深拷貝:`DEFAULT_DAILY` 是 module-level 共享的,`list()` 只換外層 list,內層 dict
        # 仍是同一批物件 —— 任何一條測試(或被測 route)改到 bar 的欄位,都會滲進其後
        # 每一條測試。
        return [dict(b) for b in self._daily], self._tag


class FakeFuturesSource:
    """FuturesSource fake(capital routes / market routes 共用)。

    `fetch_bars_range` 不在 `FuturesSource` Protocol 內(engine 以 getattr 取用,見
    `futures_engine.bars_range` 的註解)—— 這裡提供它,缺這個方法的降級路徑由各檔自己
    的特化 fake 表達。
    """

    def __init__(self) -> None:
        self.subscribed: list[str] = []
        self.leaves: list[tuple[str, str]] = []
        self.calls: list[tuple[str, str, str, str]] = []
        self.closed = False
        self.on_message: Callable[[dict], None] | None = None

    def subscribe_symbol(self, product: str) -> None:
        self.subscribed.append(product)

    def unsubscribe_symbol(self, product: str) -> None:
        return None

    def subscribe_leaf(self, product: str, ym: str) -> None:
        self.leaves.append((product, ym))

    def fetch_day_1k(self, product: str) -> list[tuple[int, int]]:
        return []  # 江波圖回補的路由測試在 test_river_routes.py

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        self.on_message = cb

    def close(self) -> None:
        self.closed = True

    def fetch_bars_range(self, product: str, tf: str, start: str, end: str) -> list[dict]:
        self.calls.append((product, tf, start, end))
        return [dbar("2026-07-29", 23_200_000)]


class FakeCorrSource:
    """CorrSource fake(corr routes / river routes 共用)。"""

    def __init__(self) -> None:
        self.subscribed: list[str] = []
        self.fetched: list[str] = []
        self.cb: Callable[[dict], None] | None = None

    def subscribe_raw(self, symbol: str) -> None:
        self.subscribed.append(symbol)

    def unsubscribe_raw(self, symbol: str) -> None:
        if symbol in self.subscribed:
            self.subscribed.remove(symbol)

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        self.cb = cb

    def fetch_day_1k(self, symbol: str) -> list[tuple[int, int]]:
        self.fetched.append(symbol)
        return []

    def close(self) -> None:
        return None


class FakeStockSource:
    """StockSource fake:全部 no-op,記錄呼叫(routes 測試不需要真行情)。"""

    def __init__(self) -> None:
        self.subscribed: list[str] = []
        self.on_message: Callable[[dict], None] | None = None
        self.daily_bars_result: list[dict] | Exception = []
        self.bars_calls: list[tuple[str, str, str, str]] = []
        self.bars_result: list[dict] = []

    def fetch_bars_range(self, code: str, tf: str, start_date: str, end_date: str) -> list:
        """Protocol 新增方法(change-spec R2-1)。"""
        self.bars_calls.append((code, tf, start_date, end_date))
        return self.bars_result

    def fetch_daily_bars(self, code: str, n: int = 25) -> list:
        if isinstance(self.daily_bars_result, Exception):
            raise self.daily_bars_result
        return self.daily_bars_result

    def subscribe_symbol(self, code: str) -> None:
        self.subscribed.append(code)

    def unsubscribe_symbol(self, code: str) -> None:
        pass

    def backfill(self, code: str) -> list:
        return []

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        self.on_message = cb

    def set_on_no_data(self, cb: Callable[[str], None]) -> None:
        pass

    def set_trade_date(self, trade_date: str) -> None:
        pass

    def close(self) -> None:
        pass
