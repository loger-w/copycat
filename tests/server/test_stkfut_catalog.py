"""StkfutCatalog:當日 cache + 單飛 + 白名單查詢(stkfut-contracts SC-1 / R11)。

合約每月換 → 不可 hardcode、不落檔;當日 in-memory cache 是「一天問 TC4 一次」的
唯一機制,而失敗與跨日**都不得**回退到舊日資料(選單殘留過期月份 → 訂閱零推播,
失效樣態毫無錯誤訊號)。
"""

from __future__ import annotations

import asyncio
import time

from copycat.server.stkfut_catalog import StkfutCatalog

SAMPLE: dict[str, dict] = {
    "2330": {
        "name": "台積電",
        "std": {"prod": "CDF", "contracts": ["202608", "202609"]},
        "mini": {"prod": "QFF", "contracts": ["202608", "202609"]},
    },
    "1312": {
        "name": "國喬",
        "std": {"prod": "EEF", "contracts": ["202608"]},
        "mini": None,
    },
}


class _Clock:
    def __init__(self, day: str = "2026-08-06") -> None:
        self.day = day

    def __call__(self) -> str:
        return self.day


class _Fetch:
    """同步 fetch 替身(真實作是 ZMQ REQ,由 catalog 丟 to_thread)。"""

    def __init__(self, *, delay: float = 0.0, error: Exception | None = None) -> None:
        self.calls = 0
        self.delay = delay
        self.error = error

    def __call__(self) -> dict[str, dict]:
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return {k: dict(v) for k, v in SAMPLE.items()}


class TestDayCache:
    async def test_same_day_second_get_does_not_hit_source(self) -> None:
        fetch = _Fetch()
        catalog = StkfutCatalog(fetch, today=_Clock())
        assert (await catalog.get("2330"))["std"]["prod"] == "CDF"
        assert await catalog.get("1312") is not None
        assert fetch.calls == 1

    async def test_concurrent_gets_single_flight(self) -> None:
        """併發只打一次:開盤瞬間多個 client 同時開下拉,不可對 TC4 併發送同一查詢。"""
        fetch = _Fetch(delay=0.05)
        catalog = StkfutCatalog(fetch, today=_Clock())
        results = await asyncio.gather(*(catalog.get("2330") for _ in range(5)))
        assert all(r is not None for r in results)
        assert fetch.calls == 1

    async def test_unknown_code_returns_none(self) -> None:
        catalog = StkfutCatalog(_Fetch(), today=_Clock())
        assert await catalog.get("9999") is None

    async def test_new_day_refetches(self) -> None:
        clock = _Clock()
        fetch = _Fetch()
        catalog = StkfutCatalog(fetch, today=clock)
        await catalog.get("2330")
        clock.day = "2026-08-07"
        await catalog.get("2330")
        assert fetch.calls == 2

    async def test_failure_after_rollover_raises_instead_of_serving_stale_day(self) -> None:
        """跨日 + 抓取失敗 → raise(**不得**回舊日):到期月已消失的合約會被畫進選單,
        使用者選了之後只會看到一條沒有推播的空線。"""
        clock = _Clock()
        fetch = _Fetch()
        catalog = StkfutCatalog(fetch, today=clock)
        await catalog.get("2330")
        clock.day = "2026-08-07"
        fetch.error = ConnectionError("tc4 down")
        try:
            await catalog.get("2330")
        except ConnectionError:
            pass
        else:  # pragma: no cover - 失敗時才會走到
            raise AssertionError("跨日抓取失敗必須 raise,不得回舊日 cache")


class TestContains:
    async def test_true_for_own_products(self) -> None:
        catalog = StkfutCatalog(_Fetch(), today=_Clock())
        assert await catalog.contains("2330", "CDF", "202609") is True
        assert await catalog.contains("2330", "QFF", "202608") is True

    async def test_false_for_other_stock_product(self) -> None:
        """別檔的產品碼(EEF 屬 1312)不得通過 2330 的白名單 —— 這是 `?contract=`
        驗證的核心:否則使用者可以把主圖切成任意一檔的期貨,而 URL 上的 code 是另一檔。
        """
        catalog = StkfutCatalog(_Fetch(), today=_Clock())
        assert await catalog.contains("2330", "EEF", "202608") is False

    async def test_false_for_unknown_month_and_unknown_code(self) -> None:
        catalog = StkfutCatalog(_Fetch(), today=_Clock())
        assert await catalog.contains("2330", "CDF", "209912") is False
        assert await catalog.contains("9999", "CDF", "202608") is False
