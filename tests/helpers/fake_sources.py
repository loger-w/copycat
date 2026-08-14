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

from copycat.live.stock_source import BarsStatus, stock_symbol


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
    - `variant_minutes[v]` 指派後,`window_variant=v` 那一發改回這份(其餘仍回
      `day_minutes`)。真 TC4 的失效是「舊窗口字串的訂閱已毒化、換窗口才拿得到資料」,
      沒有 per-variant 回傳就只驗得到「variant 有傳下去」,驗不到「換窗口真的救得回來」。
    - `window_variants` 記錄每次 `fetch_day_minutes` 收到的 variant。
    - `subscribe_error` 指派後 `subscribe_symbol` 拋(訂閱降級 / retry 路徑)。
    - `fetch_bars_range_tagged` 的 tag 與日 K 內容由建構子參數決定(market route 的
      「meta.source 必須是實際走到的分支」那組測試用)。
    - `today` 決定 1K 治具那根的日期。消費端多半在 import 期就把「今天」算成模組常數
      再拿去斷言,呼叫期重算會與它脫鉤(跨午夜的假紅路徑)→ 有斷言依賴它的測試一律
      顯式傳入自己那份,不傳才退回呼叫期。
    """

    def __init__(
        self,
        *,
        day_minutes: dict[str, int] | None = None,
        tag: str = "tc4_dk",
        daily_bars: list[dict] | None = None,
        today: str | None = None,
    ) -> None:
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.trade_dates: list[str] = []
        # 拷貝:module 常數當預設值傳進來時(同 `_daily` 的理由),被測 route 或測試
        # 改到內容會滲進其後每一條測試
        self.day_minutes: dict[str, int] | Exception = (
            {} if day_minutes is None else dict(day_minutes)
        )
        self.variant_minutes: dict[int, dict[str, int]] = {}
        self.window_variants: list[int] = []
        self.on_message: Callable[[dict], None] | None = None
        self.subscribe_error: Exception | None = None
        self.fetch_minutes_calls = 0
        self.closed = False
        self.calls: list[tuple[str, str, str, str]] = []
        self._tag = tag
        self._daily = DEFAULT_DAILY if daily_bars is None else daily_bars
        self._today = today

    def subscribe_symbol(self, code: str) -> None:
        if self.subscribe_error is not None:
            raise self.subscribe_error
        self.subscribed.append(code)

    def unsubscribe_symbol(self, code: str) -> None:
        self.unsubscribed.append(code)

    def fetch_day_minutes(self, code: str, *, window_variant: int = 0) -> dict[str, int]:
        self.fetch_minutes_calls += 1
        self.window_variants.append(window_variant)
        if isinstance(self.day_minutes, Exception):
            raise self.day_minutes
        override = self.variant_minutes.get(window_variant)
        return dict(self.day_minutes if override is None else override)

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        self.on_message = cb

    def set_trade_date(self, trade_date: str) -> None:
        self.trade_dates.append(trade_date)

    def close(self) -> None:
        self.closed = True

    def fetch_bars_range_tagged(
        self, code: str, tf: str, start: str, end: str
    ) -> tuple[list[dict], str, str]:
        self.calls.append((code, tf, start, end))
        if tf == "1":
            today = self._today or f"{_dt.date.today():%Y-%m-%d}"
            return (
                [{"t": f"{today} 09:01", "o": 1, "h": 2, "l": 0, "c": 1, "v": 3}],
                "tc4_1k",
                "ok",
            )
        # 深拷貝:`DEFAULT_DAILY` 是 module-level 共享的,`list()` 只換外層 list,內層 dict
        # 仍是同一批物件 —— 任何一條測試(或被測 route)改到 bar 的欄位,都會滲進其後
        # 每一條測試。
        return [dict(b) for b in self._daily], self._tag, "ok"


class FakeFuturesSource:
    """FuturesSource fake(capital routes / market routes 共用)。

    `fetch_bars_range` 不在 `FuturesSource` Protocol 內(engine 以 getattr 取用,見
    `futures_engine.bars_range` 的註解)—— 這裡提供它,缺這個方法的降級路徑由各檔自己
    的特化 fake 表達。

    `sessions` 記錄每次收到的 `session`(futures-allday §1.4:route → engine → source
    三層貫通,少了記錄就只能驗到「沒爆」而驗不到「真的傳下去了」)。
    `today` 同 `FakeIndexSource`:分 K 治具那根的日期,有斷言依賴它的測試顯式傳入。
    """

    def __init__(self, *, today: str | None = None) -> None:
        self.subscribed: list[str] = []
        self.leaves: list[tuple[str, str]] = []
        self.calls: list[tuple[str, str, str, str]] = []
        self.sessions: list[str] = []
        self.closed = False
        self.on_message: Callable[[dict], None] | None = None
        self._today = today

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

    def fetch_bars_range(
        self, product: str, tf: str, start: str, end: str, *, session: str = "day"
    ) -> list[dict]:
        self.calls.append((product, tf, start, end))
        self.sessions.append(session)
        if tf != "1":
            return [dbar("2026-07-29", 23_200_000)]
        # 分 K 治具用**今日**日期:當日段(fetch(code, "1", today, today))不做日期過濾,
        # 寫死的過去日期會在歷史段被 put_hist_range 丟掉,測試看到的就是一片空
        today = self._today or f"{_dt.date.today():%Y-%m-%d}"
        bars = [{"t": f"{today} 09:01", "o": 1, "h": 2, "l": 0, "c": 1, "v": 3}]
        if session == "allday":
            # 近全那條帶 uv/dv(內外盤量):route → cache → payload 全程是**原封轉發**,
            # 少了治具就只驗得到「沒爆」,驗不到欄位真的到得了前端(review TC-7)。
            # 日盤那條刻意不帶 —— 兩條同形的話「allday 專屬」就測不出差別。
            bars[0]["uv"], bars[0]["dv"] = 2, 1
            bars.append(
                {"t": f"{today} 15:01", "o": 1, "h": 2, "l": 0, "c": 1, "v": 4, "uv": 3, "dv": 1}
            )
        return bars


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
        #: 三態 status 的注入點(bars-tristate-status);預設 "ok" = 現況等價。
        #: 標 `BarsStatus` 讓「隨手指派一個域外字串」在 pyright 期就被擋下 ——
        #: runtime 的那道防線在 `bars._coerce_status`,兩道各管一半。
        self.bars_status: BarsStatus = "ok"
        #: Fut2 合約發現(stkfut-contracts SC-1);指派 Exception → 查詢拋(502 路徑)
        self.stkfut_catalog: dict[str, dict] | Exception = {}
        #: 真查詢次數 —— 「當日 cache 只問一次」與「boot 預熱過了」都只有這個計數看得出來
        self.stkfut_calls = 0

    def list_stock_futures(self) -> dict[str, dict]:
        """個股期合約清單(真實作 = TC4QuoteSource.list_stock_futures;StockSource
        Protocol 之外的能力,由 app 以 getattr 接線)。"""
        self.stkfut_calls += 1
        if isinstance(self.stkfut_catalog, Exception):
            raise self.stkfut_catalog
        return {k: dict(v) for k, v in self.stkfut_catalog.items()}

    def fetch_bars_range(
        self, code: str, tf: str, start_date: str, end_date: str
    ) -> tuple[list, BarsStatus]:
        """Protocol 新增方法(change-spec R2-1);三態 status 隨 bars 一起回。"""
        self.bars_calls.append((code, tf, start_date, end_date))
        return self.bars_result, self.bars_status

    def fetch_daily_bars(self, code: str, n: int = 25) -> list:
        if isinstance(self.daily_bars_result, Exception):
            raise self.daily_bars_result
        return self.daily_bars_result

    def subscribe_symbol(self, code: str) -> None:
        self.subscribed.append(code)

    def unsubscribe_symbol(self, code: str) -> None:
        pass

    def symbol_of(self, key: str) -> str:
        """instrument key → TC4 symbol(stkfut-contracts R2-2:engine 的推播路由鍵)。

        **一律委派 `stock_symbol`**(R1):fake 自寫第二份對映時,路由表的鍵在測試裡
        永遠自洽、在 prod 永遠對不上真實 symbol,而那條路的失效是「訂閱成功但零推播」。
        """
        return stock_symbol(key)

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
