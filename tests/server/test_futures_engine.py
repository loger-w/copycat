from __future__ import annotations

import asyncio
from typing import Callable

from copycat.server.futures_engine import FuturesEngine


def _quote(product: str = "TXF", **over: object) -> dict:
    q: dict = {
        "Symbol": f"TC.F.TWF.{product}.HOT",
        "Security": "FITX",
        "SecurityName": "臺股期貨",
        "TradingPrice": "23500",
        "TradeQuantity": "2",
        "TradeVolume": "1000",
        "TradeDate": "20260728",
        "PreciseTime": "10000000000",
        "Bid": "23499",
        "Bid1": "23498",
        "BidVolume": "10",
        "BidVolume1": "20",
        "Ask": "23500",
        "Ask1": "23501",
        "AskVolume": "12",
        "AskVolume1": "22",
        "ReferencePrice": "23400",
        "UpperLimitPrice": "25740",
        "LowerLimitPrice": "21060",
    }
    q.update(over)
    return q


class FakeSource:
    def __init__(self) -> None:
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.fail_subscribe: set[str] = set()
        self.closed = False
        self.on_message: Callable[[dict], None] | None = None

    def subscribe_symbol(self, product: str) -> None:
        if product in self.fail_subscribe:
            raise ConnectionError(f"SUBQUOTE fail {product}")
        self.subscribed.append(product)

    def unsubscribe_symbol(self, product: str) -> None:
        self.unsubscribed.append(product)

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        self.on_message = cb

    def close(self) -> None:
        self.closed = True


async def _drain() -> None:
    """讓 loop 消化 call_soon_threadsafe 排入的 handler。"""
    for _ in range(20):
        await asyncio.sleep(0.001)


async def _make() -> tuple[FuturesEngine, FakeSource, list[dict]]:
    src = FakeSource()
    events: list[dict] = []
    engine = FuturesEngine(lambda: src, broadcast=events.append)
    await engine.start()
    return engine, src, events


def _push(src: FakeSource, quote: dict) -> None:
    assert src.on_message is not None
    src.on_message(quote)


class TestLifecycle:
    async def test_start_subscribes_all_products(self) -> None:
        engine, src, _ = await _make()
        assert src.subscribed == ["TXF", "MXF", "TMF"]
        await engine.close()
        assert src.closed

    async def test_subscribe_failure_degrades_not_fatal(self) -> None:
        src = FakeSource()
        src.fail_subscribe.add("MXF")
        engine = FuturesEngine(lambda: src)
        await engine.start()  # 單品失敗不炸 start(app 層照起)
        assert src.subscribed == ["TXF", "TMF"]
        await engine.close()


class TestState:
    async def test_quote_updates_trade_book_and_limits(self) -> None:
        engine, src, _ = await _make()
        _push(src, _quote())
        await _drain()
        st = engine.state()
        assert st["seq"] == 1
        prod = st["products"]["TXF"]
        assert prod["p"] == 23_500_000
        assert prod["q"] == 2
        assert prod["cum_vol"] == 1000
        assert prod["t"] == "09:00:00.000"
        assert prod["date"] == "2026-07-28"
        assert prod["bids"] == [(23_499_000, 10), (23_498_000, 20)]
        assert prod["asks"] == [(23_500_000, 12), (23_501_000, 22)]
        assert prod["ref"] == 23_400_000
        assert prod["upper"] == 25_740_000
        assert prod["lower"] == 21_060_000
        assert prod["name"] == "臺股期貨"
        await engine.close()

    async def test_seq_increments_across_products(self) -> None:
        engine, src, events = await _make()
        _push(src, _quote())
        _push(src, _quote("MXF", Security="FIMTX", SecurityName="小型臺指"))
        await _drain()
        assert engine.state()["seq"] == 2
        assert [e["seq"] for e in events] == [1, 2]
        assert [e["product"] for e in events] == ["TXF", "MXF"]
        await engine.close()

    async def test_book_only_update_keeps_last_trade(self) -> None:
        engine, src, _ = await _make()
        _push(src, _quote())
        _push(src, _quote(TradingPrice="", TradeQuantity="", Bid="23480", BidVolume="7"))
        await _drain()
        prod = engine.state()["products"]["TXF"]
        assert prod["p"] == 23_500_000  # 純簿更新不清成交
        assert prod["bids"][0] == (23_480_000, 7)
        await engine.close()

    async def test_unknown_symbol_ignored(self) -> None:
        engine, src, events = await _make()
        _push(src, _quote(Symbol="TC.S.TWS.2330"))
        _push(src, _quote(Symbol="TC.F.TWF.CDF.HOT"))  # 非本引擎商品
        await _drain()
        assert engine.state()["seq"] == 0
        assert events == []
        await engine.close()


class TestBroadcast:
    async def test_event_shape_aligned(self) -> None:
        engine, src, events = await _make()
        _push(src, _quote())
        await _drain()
        assert len(events) == 1
        ev = events[0]
        assert ev["type"] == "futures"
        assert ev["seq"] == 1
        assert ev["product"] == "TXF"
        assert ev["state"]["p"] == 23_500_000
        await engine.close()


class TestClosedEngine:
    async def test_push_after_close_no_broadcast_no_seq_no_error(self) -> None:
        # review C9:close 先斷 threadsafe 入口 — 之後 TC4 推播不得
        # call_soon_threadsafe 到關閉中的 loop(不炸、seq 不變、無新廣播)
        engine, src, events = await _make()
        _push(src, _quote())
        await _drain()
        assert engine.state()["seq"] == 1
        await engine.close()
        n = len(events)
        _push(src, _quote(TradingPrice="23600"))  # 不得 raise
        await _drain()
        assert engine.state()["seq"] == 1  # 狀態凍結
        assert len(events) == n  # 無新 broadcast


class TestResolvedContract:
    async def test_none_before_any_signal(self) -> None:
        engine, src, _ = await _make()
        assert engine.resolved_contract("TXF") is None
        _push(src, _quote())  # HOT 形且無月份欄位 → 仍 None
        await _drain()
        assert engine.resolved_contract("TXF") is None
        await engine.close()

    async def test_resolved_from_end_date_and_cached(self) -> None:
        engine, src, _ = await _make()
        _push(src, _quote(EndDate="20260916"))
        await _drain()
        assert engine.resolved_contract("TXF") == "202609"
        _push(src, _quote())  # 後續推播無月份訊號 → 快取保留
        await _drain()
        assert engine.resolved_contract("TXF") == "202609"
        assert engine.state()["products"]["TXF"]["resolved_contract"] == "202609"
        await engine.close()

    async def test_month_change_updates_resolved(self) -> None:
        engine, src, _ = await _make()
        _push(src, _quote(Symbol="TC.F.TWF.TXF.202609"))
        await _drain()
        assert engine.resolved_contract("TXF") == "202609"
        _push(src, _quote(Symbol="TC.F.TWF.TXF.202610"))  # 換月:payload symbol 換月
        await _drain()
        assert engine.resolved_contract("TXF") == "202610"
        await engine.close()

    async def test_new_day_clears_cache(self) -> None:
        engine, src, _ = await _make()
        _push(src, _quote(EndDate="20260916"))
        await _drain()
        assert engine.resolved_contract("TXF") == "202609"
        _push(src, _quote(TradeDate="20260729"))  # 跨日且此筆無月份訊號 → 失效
        await _drain()
        assert engine.resolved_contract("TXF") is None
        assert engine.state()["products"]["TXF"]["date"] == "2026-07-29"
        await engine.close()

    async def test_new_day_with_signal_resolves_fresh(self) -> None:
        engine, src, _ = await _make()
        _push(src, _quote(EndDate="20260916"))
        _push(src, _quote(TradeDate="20260729", EndDate="20261021"))  # 跨日 + 新月份訊號
        await _drain()
        assert engine.resolved_contract("TXF") == "202610"
        await engine.close()

    async def test_per_product_isolation(self) -> None:
        engine, src, _ = await _make()
        _push(src, _quote(EndDate="20260916"))
        await _drain()
        assert engine.resolved_contract("TXF") == "202609"
        assert engine.resolved_contract("MXF") is None
        assert engine.resolved_contract("NOPE") is None
        await engine.close()
