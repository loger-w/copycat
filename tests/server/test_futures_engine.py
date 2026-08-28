from __future__ import annotations

import asyncio
import logging
import threading
from typing import Callable

import pytest

from copycat.live.tc4 import HistoryTimeoutError
from copycat.live.stock_source import Bar, BarsStatus
from copycat.server.futures_engine import FuturesEngine
from tests.helpers.wait import wait_until


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
        self.leaf_subscribed: list[tuple[str, str]] = []
        self.fail_subscribe: set[str] = set()
        self.fail_leaf: set[str] = set()
        self.fail_1k: set[str] = set()
        self.fetched_1k: list[str] = []
        self.minutes_1k: list[tuple[int, int]] = [(526, 23_400_000)]
        self.closed = False
        self.on_message: Callable[[dict], None] | None = None

    def subscribe_symbol(self, product: str) -> None:
        if product in self.fail_subscribe:
            raise ConnectionError(f"SUBQUOTE fail {product}")
        self.subscribed.append(product)

    def subscribe_leaf(self, product: str, ym: str) -> None:
        if product in self.fail_leaf:
            raise ConnectionError(f"SUBQUOTE fail {product} {ym}")
        self.leaf_subscribed.append((product, ym))

    def unsubscribe_symbol(self, product: str) -> None:
        self.unsubscribed.append(product)

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        self.on_message = cb

    def fetch_day_1k(self, product: str) -> list[tuple[int, int]]:
        if product in self.fail_1k:
            raise ConnectionError(f"1K fail {product}")
        self.fetched_1k.append(product)
        return self.minutes_1k

    def close(self) -> None:
        self.closed = True


async def _drain() -> None:
    """讓 loop 消化 call_soon_threadsafe 排入的 handler。"""
    for _ in range(20):
        await asyncio.sleep(0.001)


async def _make() -> tuple[FuturesEngine, FakeSource, list[dict]]:
    src = FakeSource()
    events: list[dict] = []
    # flush_interval_secs=0.0:coalesce 後仍走同一條 flush 路徑,但下一輪 loop 就送出,
    # `_drain` 的「消化 call_soon 排入的 handler」語意不變(既有 assert 一則不動)
    engine = FuturesEngine(lambda: src, broadcast=events.append, flush_interval_secs=0.0)
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


class TestCoalesce:
    """SC-0~4:廣播改 per-product coalesce(flush 週期 0.1 s),`seq` 在 flush 時每則 +1。

    行情叢發(夜盤實測 20 s / 312 則)每則都帶五檔全量 → WS 寫入量與前端 render 壓力
    正比於 tick 數。state 仍每 quote 即時更新(W3),只有廣播被合併。
    """

    async def test_default_flush_interval_is_100ms(self) -> None:
        engine = FuturesEngine(lambda: FakeSource())
        assert engine._flush_interval_secs == 0.1

    async def test_burst_same_product_coalesced(self) -> None:
        src = FakeSource()
        events: list[dict] = []
        engine = FuturesEngine(lambda: src, broadcast=events.append, flush_interval_secs=0.05)
        await engine.start()
        try:
            for price in ("23500", "23510", "23520", "23530", "23540"):
                _push(src, _quote(TradingPrice=price))
            await asyncio.sleep(0.2)
            assert len(events) == 1
            assert events[0]["state"]["p"] == 23_540_000  # payload = 最新 state
            assert events[0]["seq"] == 1
            assert engine.state()["seq"] == 1  # GET 與 WS 同源
        finally:
            await engine.close()

    async def test_burst_two_products_two_messages_seq_contiguous(self) -> None:
        # 推送順序刻意反 `PRODUCTS`(MXF→TXF):順推的話「按 PRODUCTS 順序送」的實作
        # 也會過,斷言就釘不住 dirty 插入序(review T3)
        src = FakeSource()
        events: list[dict] = []
        engine = FuturesEngine(lambda: src, broadcast=events.append, flush_interval_secs=0.05)
        await engine.start()
        try:
            for price in ("23400", "23410"):
                _push(src, _quote("MXF", Security="FIMTX", TradingPrice=price))
            for price in ("23500", "23510", "23520"):
                _push(src, _quote(TradingPrice=price))
            await asyncio.sleep(0.2)
            assert [e["product"] for e in events] == ["MXF", "TXF"]  # dirty 插入序
            assert [e["seq"] for e in events] == [1, 2]
            assert engine.state()["seq"] == 2
        finally:
            await engine.close()

    async def test_seq_increments_without_broadcast(self) -> None:
        """D2f:`_broadcast is None` 只是不送,`seq` 一樣每則 +1(與 coalesce 前同語意)。"""
        src = FakeSource()
        engine = FuturesEngine(lambda: src, flush_interval_secs=0.0)
        await engine.start()
        try:
            _push(src, _quote())
            _push(src, _quote("MXF", Security="FIMTX"))
            await _drain()
            assert engine.state()["seq"] == 2
        finally:
            await engine.close()

    async def test_burst_reuses_single_flush_timer(self) -> None:
        """叢發期間只有一顆 timer(每 quote 都 `call_later` 的退化 = 節流形同虛設)。"""
        src = FakeSource()
        events: list[dict] = []
        engine = FuturesEngine(lambda: src, broadcast=events.append, flush_interval_secs=0.05)
        await engine.start()
        try:
            _push(src, _quote())
            await asyncio.sleep(0)
            handle = engine._flush_timer
            assert handle is not None
            for price in ("23510", "23520", "23530", "23540"):
                _push(src, _quote(TradingPrice=price))
            await asyncio.sleep(0)
            assert engine._flush_timer is handle  # 同一顆,沒有被重排
            assert events == []
        finally:
            await engine.close()

    async def test_state_updates_immediately_before_flush(self) -> None:
        """W3:state 每 quote 即時更新(corr pull 讀 / GET 全量不受 flush 週期影響)。"""
        src = FakeSource()
        events: list[dict] = []
        engine = FuturesEngine(lambda: src, broadcast=events.append, flush_interval_secs=5.0)
        await engine.start()
        try:
            _push(src, _quote())
            await asyncio.sleep(0)
            assert engine.state()["products"]["TXF"]["p"] == 23_500_000
            assert events == []  # 廣播還沒到週期
        finally:
            await engine.close()

    async def test_second_wave_after_flush(self) -> None:
        src = FakeSource()
        events: list[dict] = []
        engine = FuturesEngine(lambda: src, broadcast=events.append, flush_interval_secs=0.05)
        await engine.start()
        try:
            _push(src, _quote(TradingPrice="23500"))
            await asyncio.sleep(0.2)
            _push(src, _quote(TradingPrice="23600"))
            await asyncio.sleep(0.2)
            assert [e["seq"] for e in events] == [1, 2]
            assert events[1]["state"]["p"] == 23_600_000
        finally:
            await engine.close()

    async def test_single_quote_delivered_within_interval(self) -> None:
        """SC-4:latency 上限 = flush 週期(單筆不得被拖到下一輪)。

        週期取 0.2 s 並實量耗時,裕度只留 0.05 s:週期若被誤實作成兩倍(或單筆要等
        下一輪才送),0.4 s 會直接撞穿門檻(review T6:原本 3× 裕度什麼都殺不掉)。
        """
        src = FakeSource()
        events: list[dict] = []
        engine = FuturesEngine(lambda: src, broadcast=events.append, flush_interval_secs=0.2)
        await engine.start()
        try:
            loop = asyncio.get_running_loop()
            t0 = loop.time()
            _push(src, _quote())
            for _ in range(100):
                if events:
                    break
                await asyncio.sleep(0.01)
            elapsed = loop.time() - t0
            assert len(events) == 1
            assert elapsed < 0.25, f"單筆 quote 等了 {elapsed:.3f}s(週期 0.2s)"
        finally:
            await engine.close()

    async def test_broadcast_exception_does_not_stall_stream(self) -> None:
        """SC-0:單則廣播拋例外 → 記 log 續行,timer 不留殘骸(下一筆照排)。"""
        src = FakeSource()
        events: list[dict] = []
        calls = 0

        def broadcast(ev: dict) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("boom")
            events.append(ev)

        engine = FuturesEngine(lambda: src, broadcast=broadcast, flush_interval_secs=0.0)
        await engine.start()
        try:
            _push(src, _quote())
            await _drain()
            # 失敗那則回標 dirty(review C1)→ 下一週期(interval 0.0 = 下一輪 loop)重送
            assert [e["seq"] for e in events] == [2]
            _push(src, _quote(TradingPrice="23600"))
            await _drain()
            assert [e["seq"] for e in events] == [2, 3]  # seq 續增,不因例外卡住
        finally:
            await engine.close()

    async def test_broadcast_failure_requeues_latest_state(self) -> None:
        """review C1:廣播失敗那則不得永久遺失(叢發尾巴無後續 quote = client 停舊價)。

        重送耗掉的 seq 1 不回收(D2f:每則 flush 一律 +1)→ client 看到 seq 由 0 跳到 2,
        前端 `useFuturesStream` 判跳號後 REST refetch 全量,收斂到同一份 state,可接受。
        """
        src = FakeSource()
        events: list[dict] = []
        calls = 0

        def broadcast(ev: dict) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("boom")
            events.append(ev)

        engine = FuturesEngine(lambda: src, broadcast=broadcast, flush_interval_secs=0.05)
        await engine.start()
        try:
            _push(src, _quote(TradingPrice="23555"))
            await asyncio.sleep(0.2)
            assert len(events) == 1
            assert events[0]["state"]["p"] == 23_555_000  # 重送的是最新 state,不是空的
            assert events[0]["seq"] == 2
        finally:
            await engine.close()

    async def test_close_with_pending_flush_timer_does_not_broadcast(self) -> None:
        """W4 / SC-0 close 不變式:timer pending 時 close → 取消、不廣播、seq 不變。

        決定性版本(review T1):單次 `sleep(0)` 讓 `_handle_quote` 跑完並先斷言 timer
        真的在 pending(否則「根本沒排」也會 vacuous 綠);週期取 5 s —— 遠大於 close
        自身耗時(~ms),不必等待也不會有 false-red,且 close 漏 cancel 時那顆
        TimerHandle 會原樣留在 loop 上 → `handle.cancelled()` 直接抓到。
        """
        src = FakeSource()
        events: list[dict] = []
        engine = FuturesEngine(lambda: src, broadcast=events.append, flush_interval_secs=5.0)
        await engine.start()
        _push(src, _quote())
        await asyncio.sleep(0)
        handle = engine._flush_timer
        assert handle is not None  # 前提:真的有 pending timer
        await engine.close()  # 不等 flush
        assert handle.cancelled()  # 漏 cancel = 這顆還掛在 loop 上活到週期結束
        assert engine._flush_timer is None
        assert events == []
        assert engine.state()["seq"] == 0

    async def test_handle_quote_after_close_schedules_nothing(self) -> None:
        """Edge 3:`_loop is None`(close 後)時 `_handle_quote` 不排 timer、不炸。"""
        src = FakeSource()
        events: list[dict] = []
        engine = FuturesEngine(lambda: src, broadcast=events.append, flush_interval_secs=0.0)
        await engine.start()
        await engine.close()
        engine._handle_quote(_quote())  # 繞過 threadsafe 入口直呼:不得 raise
        await _drain()
        assert engine._flush_timer is None
        assert events == []
        assert engine.state()["seq"] == 0


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


class TestLeafFallbackSubscribe:
    """Phase 6 real-env finding:TXO runtime 同 process 已訂 TC.F.TWF.TXF.HOT(spot),
    TC4 refcount 的另一把 key 歸零時上游退訂整個 symbol → futures 的 TXF HOT 永收不到
    (2026-08-18 定調,見 `.claude/skills/tc4-market-facts/SKILL.md`)。
    解法:resolve 已知後,寬限期內仍零推播的商品補訂 leaf 契約 —— leaf 是不同 symbol,
    天然是一把新 key,所以補得回來。"""

    async def test_empty_product_gets_leaf_subscribe_after_grace(self) -> None:
        src = FakeSource()
        events: list[dict] = []
        engine = FuturesEngine(lambda: src, broadcast=events.append, leaf_grace_secs=0.01)
        await engine.start()
        _push(src, _quote("MXF", Symbol="TC.F.TWF.MXF.202608"))
        await asyncio.sleep(0.05)
        await _drain()
        assert ("TXF", "202608") in src.leaf_subscribed
        assert ("TMF", "202608") in src.leaf_subscribed
        assert ("MXF", "202608") not in src.leaf_subscribed  # 有推播的不補訂
        await engine.close()

    async def test_leaf_subscribe_once_per_ym(self) -> None:
        src = FakeSource()
        engine = FuturesEngine(lambda: src, leaf_grace_secs=0.01)
        await engine.start()
        _push(src, _quote("MXF", Symbol="TC.F.TWF.MXF.202608"))
        _push(src, _quote("MXF", Symbol="TC.F.TWF.MXF.202608"))
        await asyncio.sleep(0.05)
        await _drain()
        assert src.leaf_subscribed.count(("TXF", "202608")) == 1
        await engine.close()

    async def test_leaf_quote_populates_state(self) -> None:
        src = FakeSource()
        engine = FuturesEngine(lambda: src, leaf_grace_secs=0.01)
        await engine.start()
        _push(src, _quote(Symbol="TC.F.TWF.TXF.202608"))
        await _drain()
        st = engine.state()["products"]["TXF"]
        assert st["p"] is not None
        assert st["resolved_contract"] == "202608"
        await engine.close()

    async def test_no_leaf_subscribe_after_close(self) -> None:
        # review I1:close 前排入 leaf(grace 內)→ close() → 不得重連(無 subscribe_leaf、無例外)
        src = FakeSource()
        engine = FuturesEngine(lambda: src, leaf_grace_secs=0.05)
        await engine.start()
        _push(src, _quote("MXF", Symbol="TC.F.TWF.MXF.202608"))
        await engine.close()
        await asyncio.sleep(0.1)
        assert src.leaf_subscribed == []
        assert src.closed

    async def test_month_rollover_rearms_leaf_fed_products(self) -> None:
        # review I2/T6:結算換月後 leaf-fed 商品不可永久凍結 — 跨日重新武裝,補訂新月 leaf
        src = FakeSource()
        engine = FuturesEngine(lambda: src, leaf_grace_secs=0.01)
        await engine.start()
        _push(src, _quote("MXF", Symbol="TC.F.TWF.MXF.202608"))
        await asyncio.sleep(0.05)
        await _drain()
        assert ("TXF", "202608") in src.leaf_subscribed
        _push(src, _quote(Symbol="TC.F.TWF.TXF.202608"))  # leaf 推播回填 → pending 判準已消耗
        await _drain()
        assert engine.state()["products"]["TXF"]["p"] is not None
        # 換月:MXF 推新月 ym + 跨日 date 變更 → TXF(曾 leaf-fed)p 清 None 重新武裝
        _push(src, _quote("MXF", Symbol="TC.F.TWF.MXF.202609", TradeDate="20260819"))
        await asyncio.sleep(0.05)
        await _drain()
        assert ("TXF", "202609") in src.leaf_subscribed
        await engine.close()

    async def test_leaf_failure_not_fatal_and_retried_next_round(self) -> None:
        # review I3/T7:leaf 失敗不炸 engine、不消耗 one-shot — 下輪推播重排重試
        src = FakeSource()
        src.fail_leaf.add("TXF")
        engine = FuturesEngine(lambda: src, leaf_grace_secs=0.01)
        await engine.start()
        _push(src, _quote("MXF", Symbol="TC.F.TWF.MXF.202608"))
        await asyncio.sleep(0.05)
        await _drain()
        assert ("TXF", "202608") not in src.leaf_subscribed  # 失敗(raise)但 engine 不炸
        assert ("TMF", "202608") in src.leaf_subscribed  # 其他商品不受牽連
        src.fail_leaf.clear()
        _push(src, _quote("MXF", Symbol="TC.F.TWF.MXF.202608"))  # 下輪推播 → 重排重試
        await asyncio.sleep(0.05)
        await _drain()
        assert ("TXF", "202608") in src.leaf_subscribed
        await engine.close()


class _FlakySource(FakeSource):
    """前 N 次 subscribe_symbol raise ConnectionError,之後成功;attempts 記每次呼叫。"""

    def __init__(self, fail_times: dict[str, int]) -> None:
        super().__init__()
        self._left = dict(fail_times)
        self.attempts: list[str] = []

    def subscribe_symbol(self, product: str) -> None:
        self.attempts.append(product)
        left = self._left.get(product, 0)
        if left > 0:
            self._left[product] = left - 1
            raise ConnectionError(f"SUBQUOTE fail {product}")
        super().subscribe_symbol(product)


class _BadRetrySource(FakeSource):
    """retry 途中拋非 ConnectionError:首輪 ConnectionError、第 2 次 ValueError、第 3 次成功。

    照抄 test_corr_engine 的 _BadRetrySource 形狀(C-3 的 futures 版)。
    """

    def __init__(self, product: str) -> None:
        super().__init__()
        self._product = product
        self.attempts: list[str] = []

    def subscribe_symbol(self, product: str) -> None:
        self.attempts.append(product)
        if product != self._product:
            super().subscribe_symbol(product)
            return
        n = self.attempts.count(product)
        if n == 1:
            raise ConnectionError(f"SUBQUOTE fail {product}")
        if n == 2:
            raise ValueError("wrapper 內部型別錯")
        super().subscribe_symbol(product)


class _AlwaysBadRetrySource(FakeSource):
    """首輪 ConnectionError 全品進 pending,之後每次 retry 一律拋 ValueError。"""

    def __init__(self) -> None:
        super().__init__()
        self.attempts: list[str] = []

    def subscribe_symbol(self, product: str) -> None:
        self.attempts.append(product)
        if self.attempts.count(product) == 1:
            raise ConnectionError(f"SUBQUOTE fail {product}")
        raise ValueError("wrapper 內部型別錯")


class TestPendingResubscribe:
    """bug startup-names-futures-resub 症狀 3:訂閱失敗品**零重試路徑**。

    source 層 `_resub` 只重掛成功過的 symbol、`_leaf_fallback` 需先由推播解析 ym →
    「一開始就訂不到」的商品兩條路都接不了手,期貨面板整段 p=null 且無錯誤訊號。
    """

    async def test_failed_products_retried_until_success(self) -> None:
        src = _FlakySource({"TXF": 2, "MXF": 1})
        engine = FuturesEngine(lambda: src, resub_interval_secs=0.01)
        await engine.start()
        assert src.subscribed == ["TMF"]  # 首輪只有 TMF 成功
        try:
            await wait_until(lambda: {"TXF", "MXF"} <= set(src.subscribed))
            # P2-3 收斂不變式:pending 清空後迴圈必須自然結束(while True mutant 下
            # task 常駐洩漏,原測試無任何斷言會紅)
            await wait_until(
                lambda: engine._resub_task is not None and engine._resub_task.done()
            )
            assert engine._pending_subs == set()
        finally:
            await engine.close()
        assert sorted(src.subscribed) == ["MXF", "TMF", "TXF"]
        assert src.attempts.count("TXF") == 3  # 失敗 2 次 + 成功 1 次
        assert src.attempts.count("TMF") == 1  # 成功品不重訂

    async def test_state_updates_after_retry_success(self) -> None:
        src = _FlakySource({"TXF": 1})
        engine = FuturesEngine(lambda: src, resub_interval_secs=0.01)
        await engine.start()
        await wait_until(lambda: "TXF" in src.subscribed)
        _push(src, _quote())
        await _drain()
        assert engine.state()["products"]["TXF"]["p"] == 23_500_000
        await engine.close()

    async def test_all_success_no_retry_task(self) -> None:
        src = _FlakySource({})
        engine = FuturesEngine(lambda: src, resub_interval_secs=0.01)
        await engine.start()
        await asyncio.sleep(0.05)
        assert src.attempts == ["TXF", "MXF", "TMF"]  # 每品恰一次
        # P2-3:原斷言 len(all_tasks()) == baseline 對「無守衛必起 task」mutant 全綠
        # (已完成 task 不在 all_tasks)。照 corr 版鎖結構性事實:task 根本沒被建出來
        assert engine._resub_task is None
        await engine.close()

    async def test_close_stops_retry_loop(self) -> None:
        src = _FlakySource({p: 10_000 for p in ("TXF", "MXF", "TMF")})
        engine = FuturesEngine(lambda: src, resub_interval_secs=0.01)
        await engine.start()
        await wait_until(lambda: len(src.attempts) > 3)  # 重試迴圈確實在跑
        await engine.close()
        # T-9:in-flight worker(close 前已過 guard)脫鉤跑完 —— 用靜止條件取代
        # 固定 sleep(快照連續兩次相等),斷言不再吃 OS 排程時序
        prev = -1
        n = len(src.attempts)
        while n != prev:
            await asyncio.sleep(0.05)
            prev, n = n, len(src.attempts)
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        assert pending == []
        await asyncio.sleep(0.05)  # 5 個間隔
        # P1-2:原斷言 <= n+1 把「close 後 orphan worker 再碰 source」寫成允許值;
        # _EngineClosing 縮窗後靜止之後不得再有任何新 subscribe
        assert len(src.attempts) == n

    async def test_retry_worker_refuses_to_touch_source_after_close(self) -> None:
        """P1-2:close 後才輪到的 executor 工作項不得再碰 source(_EngineClosing 縮窗)。

        cancel 正 await to_thread 的 task 時 asyncio 立即返回,已排入 executor 但未
        啟動的工作項仍會跑 —— 真 source 上那一下 subscribe 會經 _ensure_connected
        重建 TC4 連線,KeepAlive 洩漏 process 不退。整合層無法決定性製造「排入但
        未啟動」窗,以 worker 直呼鎖 guard 語意(stock_engine._retry_acquire 同款)。

        T-8:用「close 第一步(_loop 斷、_source 尚在)」的半關狀態構造 —— 哨兵
        必須是 _loop 而非 _source(_source 到 leaf gather 之後才斷,用它當哨兵
        等於整段收尾期間窗子還開著)。
        """
        from copycat.server.futures_engine import _EngineClosing

        src = _FlakySource({"TXF": 10_000})
        engine = FuturesEngine(lambda: src, resub_interval_secs=0.01)
        await engine.start()
        loop = engine._loop
        engine._loop = None  # close 第一步;_source 仍在
        before = len(src.attempts)
        with pytest.raises(_EngineClosing):
            engine._retry_subscribe(src, "TXF")
        assert len(src.attempts) == before  # source 未被碰
        engine._loop = loop
        await engine.close()

    async def test_close_swallows_dead_resub_task_exception(self) -> None:
        """T-5:close suppress 放寬的直測 —— 迴圈圍籬失守、task 以例外終態落定時,
        close() 不得重拋、source.close() 必達(與 _resub_loop 的 except Exception
        正交:那道圍籬讓例外終態在整合路徑不可達,這裡直接構造終態)。"""
        src = FakeSource()
        engine = FuturesEngine(lambda: src)
        await engine.start()

        async def _boom() -> None:
            raise ValueError("task 已死於非連線例外")

        engine._resub_task = asyncio.get_running_loop().create_task(_boom())
        await asyncio.sleep(0)  # 讓 task 以 ValueError 終態落定
        await engine.close()  # 不得重拋
        assert src.closed

    async def test_engine_closing_exits_loop_without_failure_log(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """T-7:_EngineClosing 必須走專屬分支靜默結束 —— 落到 except Exception 會在
        每次關機吐「訂閱重試輪失敗」假 log(3am grep 噪音;分支註解的承諾在此上鎖)。"""
        src = _FlakySource({p: 10_000 for p in ("TXF", "MXF", "TMF")})
        engine = FuturesEngine(lambda: src, resub_interval_secs=0.01)
        await engine.start()
        await wait_until(lambda: len(src.attempts) > 3)
        loop = engine._loop
        task = engine._resub_task
        assert task is not None
        with caplog.at_level(logging.ERROR):
            engine._loop = None  # 模擬 close 第一步(worker guard 生效)
            await wait_until(lambda: task.done())
        assert "訂閱重試輪失敗" not in caplog.text
        engine._loop = loop
        await engine.close()

    async def test_retry_loop_survives_non_connection_error(self) -> None:
        """P1-1:非 ConnectionError 例外(壞電文/型別錯)不得殺掉重試路徑。

        迴圈死掉 = 復原路徑本身靜默失效,而 close() 的收尾又把 task 例外吞掉 ——
        兩層靜默疊起來,該品整天零推播且 log 只有首輪一行 warning(復刻原 bug 的
        零訊號終態)。corr 版:test_corr_engine test_retry_loop_survives_non_connection_error。
        """
        src = _BadRetrySource("TXF")
        engine = FuturesEngine(lambda: src, resub_interval_secs=0.01)
        await engine.start()
        try:
            await wait_until(lambda: "TXF" in src.subscribed)
            assert src.attempts.count("TXF") == 3  # 連線類 + 非連線類 + 成功
        finally:
            await engine.close()

    async def test_close_after_bad_retry_exception_still_closes_source(self) -> None:
        """P1-1 後半:retry 拋過非 ConnectionError 之後,close() 仍必須關到 source。

        現行 close() 只 suppress CancelledError → task 已死於 ValueError 時
        await resub 重拋 → leaf gather 與 source.close() 全跳過 → TC4 KeepAlive
        執行緒洩漏 process 不退(回溯審 repro 實測)。
        """
        src = _AlwaysBadRetrySource()
        engine = FuturesEngine(lambda: src, resub_interval_secs=0.01)
        await engine.start()
        await wait_until(lambda: len(src.attempts) > 3)  # 至少一次 retry 已拋 ValueError
        await engine.close()  # 不得重拋 ValueError
        assert src.closed  # source.close() 必達(KeepAlive 不洩漏)


class TestRetrySuccessLeafBookkeeping:
    """P2-1 + review C-2/T-10:leaf 記帳的撤銷判準是「HOT 真的推了成交」,不是 SUB 回 OK。

    SUBQUOTE 對 spot 衝突品恆回 OK 但零推播(leaf fallback 存在的理由)——
    以「訂閱成功」當撤銷判準會在重連對帳後清掉還在靠 leaf 活著的品,
    跨日重武裝失效 → 隔日凍結價零訊號。不撤銷又會讓跨日每天複製新月 leaf、
    HOT + leaf 雙訂閱(seq/廣播加倍)。真判準 = 收到該品 HOT 成交 tick。
    """

    async def test_hot_tick_after_retry_discards_leaf_fed(self) -> None:
        src = FakeSource()
        src.fail_subscribe.add("TXF")
        engine = FuturesEngine(lambda: src, leaf_grace_secs=0.01, resub_interval_secs=0.05)
        await engine.start()
        _push(src, _quote("MXF", Symbol="TC.F.TWF.MXF.202608"))
        await asyncio.sleep(0.05)
        await _drain()
        assert ("TXF", "202608") in src.leaf_subscribed  # 訂不到的品先由 leaf 接手
        assert "TXF" in engine._leaf_fed
        src.fail_subscribe.discard("TXF")  # TC4 恢復 → 下一輪重試成功
        try:
            await wait_until(lambda: "TXF" in src.subscribed)
            await _drain()
            assert "TXF" in engine._leaf_fed  # SUB 成功 ≠ HOT 已回:記帳保留
            _push(src, _quote())  # TXF 的 HOT 成交推播 = 真判準
            await _drain()
            assert "TXF" not in engine._leaf_fed  # HOT 已回:撤銷記帳
            # 症狀層(T-10):換日 + 新 ym → TXF 不再補新月 leaf
            _push(src, _quote("MXF", Symbol="TC.F.TWF.MXF.202609", TradeDate="20260819"))
            await asyncio.sleep(0.05)
            await _drain()
            assert ("TXF", "202609") not in src.leaf_subscribed
        finally:
            await engine.close()


class _ReconnectSource(FakeSource):
    """帶 on_reconnect 屬性的 source(對齊 TC4QuoteSource 介面;stock/corr fake 同款)。"""

    def __init__(self) -> None:
        super().__init__()
        self.on_reconnect: Callable[[], None] | None = None


class _FlakyReconnectSource(_FlakySource):
    """_FlakySource + on_reconnect 屬性(重連對帳 × 重試迴圈的交互測試用)。"""

    def __init__(self, fail_times: dict[str, int]) -> None:
        super().__init__(fail_times)
        self.on_reconnect: Callable[[], None] | None = None


class _GatedRetrySource(FakeSource):
    """首輪全失敗;retry 的 subscribe 卡在 gate 上,放行後成功(製造 in-flight 窗)。"""

    def __init__(self) -> None:
        super().__init__()
        self.gate = threading.Event()
        self.retrying = threading.Event()
        self.first_round_done = False

    def subscribe_symbol(self, product: str) -> None:
        if not self.first_round_done:
            raise ConnectionError("initial down")
        self.retrying.set()
        assert self.gate.wait(timeout=2)
        super().subscribe_symbol(product)


class TestReconnectReconciliation:
    """P1-3:`_check_stale` 重連可能靜默掉訂(SUBQUOTE 失敗零 log / 迴圈中途拋錯
    尾段 symbol 蒸發),掉訂品不進 `_pending_subs`、`_leaf_fallback` 判準(p is None)
    也不武裝 —— FuturesEngine 是四引擎唯一沒接 on_reconnect 的,零復原零覆蓋。

    修法 = on_reconnect 對帳:全品回填 pending 由重試迴圈重掛
    (subscribe 走 UNSUB→SUB 冪等,重掛仍活著的品無害)。
    """

    async def test_engine_wires_on_reconnect(self) -> None:
        src = _ReconnectSource()
        engine = FuturesEngine(lambda: src, resub_interval_secs=0.01)
        await engine.start()
        try:
            assert src.on_reconnect is not None
        finally:
            await engine.close()

    async def test_reconnect_resubscribes_dropped_products(self) -> None:
        src = _ReconnectSource()
        engine = FuturesEngine(lambda: src, resub_interval_secs=0.01)
        await engine.start()  # 全成功 → 無 retry task(對帳必須能重啟迴圈,不能只靠 start)
        src.subscribed.clear()  # 模擬重連:source 端重掛全數靜默失敗,engine 不知情
        assert src.on_reconnect is not None
        # T-4:prod 路徑是 TC4 listener thread 呼叫 —— 走 to_thread 讓
        # 「threadsafe hop 改直呼 _handle_reconnect」的 mutant(listener 死於
        # no running event loop → 全引擎斷流)必紅
        await asyncio.to_thread(src.on_reconnect)
        try:
            await wait_until(lambda: {"TXF", "MXF", "TMF"} <= set(src.subscribed))
        finally:
            await engine.close()

    async def test_reconnect_restarts_converged_retry_loop(self) -> None:
        """T-2:start 曾有失敗品 → 迴圈收斂後 `_resub_task` 是 done 的 task(非 None),
        對帳 guard 的 done() 半邊 —— 砍掉它 = 收斂後的重連零復原(原 bug 樣態)。"""
        src = _FlakyReconnectSource({"TXF": 1})
        engine = FuturesEngine(lambda: src, resub_interval_secs=0.01)
        await engine.start()
        await wait_until(lambda: engine._resub_task is not None and engine._resub_task.done())
        old = engine._resub_task
        src.subscribed.clear()
        assert src.on_reconnect is not None
        await asyncio.to_thread(src.on_reconnect)
        try:
            await wait_until(lambda: {"TXF", "MXF", "TMF"} <= set(src.subscribed))
            assert engine._resub_task is not old
        finally:
            await engine.close()

    async def test_reconnect_does_not_duplicate_running_loop(self) -> None:
        """T-3:對帳打進來時 retry loop 還活著 → 不得覆寫成孤兒(close 只 cancel
        最後一顆,孤兒在 close 進行中仍可能碰 source)。"""
        src = _FlakyReconnectSource({p: 10_000 for p in ("TXF", "MXF", "TMF")})
        engine = FuturesEngine(lambda: src, resub_interval_secs=0.01)
        await engine.start()
        await wait_until(lambda: len(src.attempts) > 3)
        task = engine._resub_task
        assert task is not None and not task.done()
        assert src.on_reconnect is not None
        await asyncio.to_thread(src.on_reconnect)
        await _drain()
        assert engine._resub_task is task
        await engine.close()

    async def test_reconnect_during_close_is_noop(self) -> None:
        # close 已開始(_loop 斷)後的 on_reconnect 不得再排工作
        src = _ReconnectSource()
        engine = FuturesEngine(lambda: src, resub_interval_secs=0.01)
        await engine.start()
        await engine.close()
        n = len(src.subscribed)
        assert src.on_reconnect is not None
        src.on_reconnect()
        await asyncio.sleep(0.05)
        assert len(src.subscribed) == n

    async def test_reconnect_callback_after_close_creates_no_task(self) -> None:
        """review C-3:threadsafe 檢查在 listener thread、_handle_reconnect 在 loop
        thread,中間 close() 可整段插入 —— close 讓出(await resub)期間 ready queue
        裡的回呼被消化,不得建出 close() 永不 cancel 的孤兒 task(corr
        _schedule_backfill 的二次檢查同款)。"""
        src = _ReconnectSource()
        engine = FuturesEngine(lambda: src, resub_interval_secs=0.01)
        await engine.start()
        await engine.close()
        engine._handle_reconnect()  # 模擬 close 期間已排入、close 後才消化的在途回呼
        assert engine._resub_task is None
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        assert pending == []

    async def test_reconnect_does_not_clear_leaf_fed(self) -> None:
        """review C-2/T-6:leaf-fed 品(SUB 恆 OK 但 HOT 零推播)在重連對帳的重掛
        成功後,leaf 記帳必須保留 —— 清掉 = 跨日重武裝迴圈掃不到它,新月 leaf
        不補,隔日凍結昨日價且零錯誤訊號(本 /bug 要消滅的失效樣態被重新引進)。"""
        src = _ReconnectSource()
        engine = FuturesEngine(lambda: src, leaf_grace_secs=0.01, resub_interval_secs=0.01)
        await engine.start()
        _push(src, _quote("MXF", Symbol="TC.F.TWF.MXF.202608"))
        await asyncio.sleep(0.05)
        await _drain()
        assert "TXF" in engine._leaf_fed  # TXF HOT 零推播 → leaf 接手
        assert src.on_reconnect is not None
        await asyncio.to_thread(src.on_reconnect)
        try:
            await wait_until(lambda: src.subscribed.count("TXF") >= 2)  # 對帳重掛完成
            await _drain()
            assert "TXF" in engine._leaf_fed  # SUB OK ≠ HOT 已回:記帳不得清
        finally:
            await engine.close()

    async def test_reconcile_survives_inflight_retry_success(self) -> None:
        """review C-4:重試輪 await 期間發生重連 → 該筆成功掛在**舊連線**上
        (SUB 隨 dispose 蒸發),不得出列 —— 出列 = 兩邊都認為已訂上、實際
        零推播零 log,對帳在自己最需要生效的時序上被自己撤銷。"""
        src = _GatedRetrySource()
        engine = FuturesEngine(lambda: src, resub_interval_secs=0.01)
        await engine.start()
        src.first_round_done = True
        await asyncio.to_thread(src.retrying.wait, 2)  # retry in-flight(卡在 gate)
        engine._handle_reconnect()  # 重連插入
        src.gate.set()
        try:
            # 舊連線上的成功若被出列,MXF 永遠不會再被重掛(count 停在 1)
            await wait_until(lambda: src.subscribed.count("MXF") >= 2)
        finally:
            await engine.close()


class TestFetchDay1kPassthrough:
    """江波圖回補(index-river-chart SC-4):台指 1K 必須從持有 TXF 訂閱的這條 session 問。"""

    async def test_passthrough_returns_source_minutes(self) -> None:
        engine, src, _ = await _make()
        assert engine.fetch_day_1k("TXF") == [(526, 23_400_000)]
        assert src.fetched_1k == ["TXF"]
        await engine.close()

    async def test_without_source_returns_empty(self) -> None:
        engine = FuturesEngine(lambda: FakeSource())  # 未 start → 無 source
        assert engine.fetch_day_1k("TXF") == []

    async def test_connection_error_propagates_for_caller_degradation(self) -> None:
        engine, src, _ = await _make()
        src.fail_1k.add("TXF")
        with pytest.raises(ConnectionError):
            engine.fetch_day_1k("TXF")
        await engine.close()


class TestBarsRangeProxy:
    """借不到就回空 + 固定可 grep 的 log 字串(index-board N-3;3am frame)。

    那條字串是「TC4 掛了 vs 真沒資料」的唯一五秒判準,沒有測試等於沒人驗過它真的會印。
    """

    async def _run(self, engine: FuturesEngine, caplog) -> tuple[list[Bar], BarsStatus]:
        with caplog.at_level(logging.WARNING):
            return await engine.bars_range("TXF", "D", "2026-07-01", "2026-07-30")

    @pytest.mark.asyncio
    async def test_source_absent_returns_empty_with_fixed_log(self, caplog) -> None:
        engine = FuturesEngine(lambda: FakeSource())  # 未 start → _source is None
        got = await self._run(engine, caplog)
        # N104:回傳形狀 = (bars, status);source 未建 = 連不上,不是「TC4 忙」
        assert got == ([], "disconnected")
        assert "market: futures history proxy miss" in caplog.text

    @pytest.mark.asyncio
    async def test_history_timeout_degrades_here_with_its_own_log(self, caplog) -> None:
        """逾時在 **engine 內**降級成空 bars,但**帶著 `timeout` 出去**(N104)。

        `HistoryTimeoutError` 是 `ConnectionError` 子類 → 沒有專屬分支的話會被下面那條
        接走並印成 proxy miss,3am 判準就把「忙一下」讀成「TC4 掛了」;而少了 status
        這一格,前端的空態文案也分不出「TC4 忙」與「這個商品真沒 K 線」。
        """

        class Slow(FakeSource):
            def fetch_bars_range(
                self, product: str, tf: str, start: str, end: str, *, session: str = "day"
            ) -> list[dict]:
                raise HistoryTimeoutError("first page not ready")

        engine = FuturesEngine(lambda: Slow())
        await engine.start()
        try:
            got = await self._run(engine, caplog)
        finally:
            await engine.close()
        assert got == ([], "timeout")
        assert "期貨 K 線 timeout(非 TC4 down)" in caplog.text
        assert "market: futures history proxy miss" not in caplog.text

    @pytest.mark.asyncio
    async def test_connection_error_returns_empty_with_fixed_log(self, caplog) -> None:
        class Boom(FakeSource):
            def fetch_bars_range(
                self, product: str, tf: str, start: str, end: str, *, session: str = "day"
            ) -> list[dict]:
                raise ConnectionError("TC4 down")

        engine = FuturesEngine(lambda: Boom())
        await engine.start()
        try:
            got = await self._run(engine, caplog)
        finally:
            await engine.close()
        assert got == ([], "disconnected")
        assert "market: futures history proxy miss" in caplog.text

    @pytest.mark.asyncio
    async def test_healthy_path_reports_ok(self, caplog) -> None:
        """有貨的那條要明確是 `ok` —— 少了這條,把 status 寫死成常數也全綠。"""

        class Fine(FakeSource):
            def fetch_bars_range(
                self, product: str, tf: str, start: str, end: str, *, session: str = "day"
            ) -> list[dict]:
                return [{"t": "2026-07-29", "o": 1, "h": 2, "l": 0, "c": 1, "v": 3}]

        engine = FuturesEngine(lambda: Fine())
        await engine.start()
        try:
            got = await self._run(engine, caplog)
        finally:
            await engine.close()
        bars, status = got
        assert status == "ok"
        assert len(bars) == 1


class TestBarsRangeSession:
    """futures-allday §1.4:`session` 必須原樣轉給 source(三層貫通的中間那層)。

    轉不下去的失效樣態是「近全模式照樣只有日盤」—— route 200、bars 非空、
    沒有任何錯誤訊號,所以這一層要有自己的斷言。
    """

    class _WithBars(FakeSource):
        def __init__(self) -> None:
            super().__init__()
            self.bars_calls: list[tuple[str, str, str, str, str]] = []

        def fetch_bars_range(
            self, product: str, tf: str, start: str, end: str, *, session: str = "day"
        ) -> list[dict]:
            self.bars_calls.append((product, tf, start, end, session))
            return []

    @pytest.mark.asyncio
    async def test_session_forwarded_and_defaults_to_day(self) -> None:
        src = self._WithBars()
        engine = FuturesEngine(lambda: src)
        await engine.start()
        try:
            await engine.bars_range("TXF", "1", "2026-07-30", "2026-07-30", session="allday")
            await engine.bars_range("TXF", "1", "2026-07-30", "2026-07-30")
        finally:
            await engine.close()
        assert [c[4] for c in src.bars_calls] == ["allday", "day"]
class TestReconnectLeafReconcile:
    """N260:重連對帳只回填 HOT —— 重連若掉了 leaf 契約訂閱(`_check_stale` 的重掛
    迴圈中途拋錯會讓尾段 symbol 靜默蒸發),`_leaf_done` 記帳仍在、`st.p` 還留著 leaf
    推來的舊值,`_leaf_fallback` 的兩道判準都不武裝 → 要等跨日重武裝才補得回來。
    """

    async def test_reconnect_rearms_leaf_for_leaf_fed_products(self) -> None:
        src = _ReconnectSource()
        engine = FuturesEngine(
            lambda: src, leaf_grace_secs=0.01, resub_interval_secs=0.01
        )
        await engine.start()
        _push(src, _quote("MXF", Symbol="TC.F.TWF.MXF.202608"))
        await asyncio.sleep(0.05)
        await _drain()
        assert ("TXF", "202608") in src.leaf_subscribed  # TXF HOT 零推播 → leaf 接手
        _push(src, _quote(Symbol="TC.F.TWF.TXF.202608"))  # leaf 推播回填 p
        await _drain()
        assert engine.state()["products"]["TXF"]["p"] is not None
        src.leaf_subscribed.clear()
        assert src.on_reconnect is not None
        await asyncio.to_thread(src.on_reconnect)
        try:
            await wait_until(
                lambda: src.subscribed.count("TXF") >= 2
            )  # HOT 對帳重掛完成
            await _drain()
            _push(
                src, _quote("MXF", Symbol="TC.F.TWF.MXF.202608")
            )  # 同月:別品帶 ym 進來
            await asyncio.sleep(0.05)
            await _drain()
            assert ("TXF", "202608") in src.leaf_subscribed, "重連掉了 leaf 卻不重武裝"
        finally:
            await engine.close()

    async def test_reconnect_keeps_price_of_products_that_never_needed_leaf(
        self,
    ) -> None:
        """只有 `_leaf_fed` 的品要清 p 重武裝 —— HOT 自己在推的品不得被清成 null
        (那是「重連一下右上角期貨價就空一格」的新失效)。"""
        src = _ReconnectSource()
        engine = FuturesEngine(
            lambda: src, leaf_grace_secs=999.0, resub_interval_secs=0.01
        )
        await engine.start()
        _push(src, _quote("MXF", Symbol="TC.F.TWF.MXF.202608"))
        await _drain()
        assert engine.state()["products"]["MXF"]["p"] is not None
        assert src.on_reconnect is not None
        await asyncio.to_thread(src.on_reconnect)
        try:
            await _drain()
            assert engine.state()["products"]["MXF"]["p"] is not None
        finally:
            await engine.close()
class TestReconnectLeafRearmKeepsPrice:
    """review SP4:重連重武裝**不得**把 `st.p` 清成 None —— 那是使用者看得到的空一格
    (期貨面三檔的價位),而 leaf 真的還活著時它根本不該消失。重武裝是**引擎的判定
    狀態**,用自己的集合表達,不要借畫面欄位當旗標。
    """

    async def test_reconnect_keeps_the_leaf_fed_price_visible(self) -> None:
        src = _ReconnectSource()
        engine = FuturesEngine(
            lambda: src, leaf_grace_secs=0.01, resub_interval_secs=0.01
        )
        await engine.start()
        _push(src, _quote("MXF", Symbol="TC.F.TWF.MXF.202608"))
        await asyncio.sleep(0.05)
        await _drain()
        assert ("TXF", "202608") in src.leaf_subscribed
        _push(src, _quote(Symbol="TC.F.TWF.TXF.202608"))  # leaf 推播回填 p
        await _drain()
        before = engine.state()["products"]["TXF"]["p"]
        assert before is not None
        assert src.on_reconnect is not None
        await asyncio.to_thread(src.on_reconnect)
        try:
            await wait_until(lambda: src.subscribed.count("TXF") >= 2)
            await _drain()
            assert engine.state()["products"]["TXF"]["p"] == before, (
                "重連把使用者看的價清空了"
            )
        finally:
            await engine.close()

    async def test_rearm_is_consumed_once_the_leaf_is_back(self) -> None:
        """重武裝旗標必須在補訂成功後消掉 —— 留著的話每一則別品推播都會重排一次
        fallback,變成對 TC4 的持續 churn(而 log 只是照設計在跑)。"""
        src = _ReconnectSource()
        engine = FuturesEngine(
            lambda: src, leaf_grace_secs=0.01, resub_interval_secs=0.01
        )
        await engine.start()
        _push(src, _quote("MXF", Symbol="TC.F.TWF.MXF.202608"))
        await asyncio.sleep(0.05)
        await _drain()
        _push(src, _quote(Symbol="TC.F.TWF.TXF.202608"))
        await _drain()
        assert src.on_reconnect is not None
        await asyncio.to_thread(src.on_reconnect)
        try:
            await wait_until(lambda: src.subscribed.count("TXF") >= 2)
            await _drain()
            _push(src, _quote("MXF", Symbol="TC.F.TWF.MXF.202608"))
            await asyncio.sleep(0.05)
            await _drain()
            assert src.leaf_subscribed.count(("TXF", "202608")) == 2  # 重武裝那一次
            _push(src, _quote("MXF", Symbol="TC.F.TWF.MXF.202608"))
            await asyncio.sleep(0.05)
            await _drain()
            assert src.leaf_subscribed.count(("TXF", "202608")) == 2, (
                "重武裝旗標沒消掉 → churn"
            )
        finally:
            await engine.close()


class TestOneKHealthWarnings:
    """L262(2026-08-28 triage):期貨 1K「落後」/「中段缺格」以前只在前端 gate 5 判,後端零 log,
    事後分不出 H1(TC4 暫時落後)與 H3(memo 釘住)。`bars_range` tf=1 成功回非空時檢查,固定前綴供 grep;
    同商品同尾根只印一次(前端每分鐘輪詢不洗版)。"""

    class _Bars(FakeSource):
        def __init__(self, bars: list[dict]) -> None:
            super().__init__()
            self.bars = bars

        def fetch_bars_range(
            self, product: str, tf: str, start: str, end: str, *, session: str = "day"
        ) -> list[dict]:
            return self.bars

    @staticmethod
    def _bar(t: str) -> dict:
        return {"t": t, "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}

    @pytest.mark.asyncio
    async def test_lag_behind_last_trade_warns_once_per_tail(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        src = self._Bars([self._bar("2026-07-28 09:00"), self._bar("2026-07-28 09:01")])
        engine = FuturesEngine(lambda: src)
        await engine.start()
        try:
            st = engine._states["TXF"]
            st.date, st.t = "2026-07-28", "09:10:30.000"  # 最後成交 09:10 vs 尾根 09:01 → 落後 9 分
            with caplog.at_level(logging.WARNING, logger="copycat.server.futures_engine"):
                await engine.bars_range("TXF", "1", "2026-07-28", "2026-07-28", session="allday")
                await engine.bars_range("TXF", "1", "2026-07-28", "2026-07-28", session="allday")
        finally:
            await engine.close()
        assert caplog.text.count("期貨 1K 落後 TXF") == 1, "同尾根第二次輪詢不再印"
        assert "尾根 2026-07-28 09:01" in caplog.text and "落後 9 分" in caplog.text

    @pytest.mark.asyncio
    async def test_no_lag_warning_within_threshold_daily_or_historical(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # 白名單 5:門檻內 / 日 K / 歷史窗(end 早於最後成交日)/ 尚無成交 → 零新 log
        src = self._Bars([self._bar("2026-07-28 09:00"), self._bar("2026-07-28 09:01")])
        engine = FuturesEngine(lambda: src)
        await engine.start()
        try:
            st = engine._states["TXF"]
            with caplog.at_level(logging.WARNING, logger="copycat.server.futures_engine"):
                await engine.bars_range(
                    "TXF", "1", "2026-07-28", "2026-07-28", session="allday"
                )  # st.t None
                st.date, st.t = "2026-07-28", "09:04:00.000"  # 落後 3 分 = 門檻,不印
                await engine.bars_range("TXF", "1", "2026-07-28", "2026-07-28", session="allday")
                st.t = "09:30:00.000"
                await engine.bars_range("TXF", "D", "2026-07-01", "2026-07-28")  # 日 K 不查
                await engine.bars_range(
                    "TXF", "1", "2026-07-20", "2026-07-27", session="allday"
                )  # 歷史窗
        finally:
            await engine.close()
        assert "期貨 1K" not in caplog.text

    @pytest.mark.asyncio
    async def test_mid_gap_warns_but_segment_jumps_do_not(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        bars = [
            self._bar("2026-07-28 13:44"),
            self._bar("2026-07-28 13:45"),
            self._bar("2026-07-28 15:01"),  # 日盤尾 → 夜盤首:段界,不是缺格
            self._bar("2026-07-28 15:02"),
            self._bar("2026-07-28 15:06"),  # 15:03–15:05 三根缺
            self._bar("2026-07-28 15:07"),
            self._bar(
                "2026-07-29 05:00"
            ),  # 跨午夜段內(23:59 → 00:00 也是段界)但這裡直接跳到收盤:缺格
            self._bar("2026-07-29 08:46"),  # 夜盤尾 → 日盤首:段界
        ]
        engine = FuturesEngine(lambda: self._Bars(bars))
        await engine.start()
        try:
            with caplog.at_level(logging.WARNING, logger="copycat.server.futures_engine"):
                await engine.bars_range("TXF", "1", "2026-07-28", "2026-07-29", session="allday")
                await engine.bars_range("TXF", "1", "2026-07-28", "2026-07-29", session="allday")
        finally:
            await engine.close()
        assert caplog.text.count("期貨 1K 中段缺格 TXF") == 1
        assert "2 段" in caplog.text and "2026-07-28 15:07→2026-07-29 05:00" in caplog.text
