from __future__ import annotations

import asyncio
import logging
from typing import Callable

import pytest

from copycat.live.stock_source import Bar
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


class TestLeafFallbackSubscribe:
    """Phase 6 real-env finding:TXO runtime 同 process 已訂 TC.F.TWF.TXF.HOT(spot),
    TC4 對同 symbol 跨 session 只推一邊 → futures 的 TXF HOT 永收不到。
    解法:resolve 已知後,寬限期內仍零推播的商品補訂 leaf 契約(symbol 字串不同無衝突)。"""

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


async def _wait_until(pred: Callable[[], bool], timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if pred():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("條件逾時未成立")


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
            await _wait_until(lambda: {"TXF", "MXF"} <= set(src.subscribed))
            # P2-3 收斂不變式:pending 清空後迴圈必須自然結束(while True mutant 下
            # task 常駐洩漏,原測試無任何斷言會紅)
            await _wait_until(
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
        await _wait_until(lambda: "TXF" in src.subscribed)
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
        await _wait_until(lambda: len(src.attempts) > 3)  # 重試迴圈確實在跑
        await engine.close()
        await asyncio.sleep(0.05)  # close 當下真正 in-flight 的 thread 結清
        n = len(src.attempts)
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        assert pending == []
        await asyncio.sleep(0.05)  # 5 個間隔
        # P1-2:原斷言 <= n+1 把「close 後 orphan worker 再碰 source」寫成允許值;
        # _EngineClosing 縮窗後 close 之後不得再有任何新 subscribe
        assert len(src.attempts) == n

    async def test_retry_worker_refuses_to_touch_source_after_close(self) -> None:
        """P1-2:close 後才輪到的 executor 工作項不得再碰 source(_EngineClosing 縮窗)。

        cancel 正 await to_thread 的 task 時 asyncio 立即返回,已排入 executor 但未
        啟動的工作項仍會跑 —— 真 source 上那一下 subscribe 會經 _ensure_connected
        重建 TC4 連線,KeepAlive 洩漏 process 不退。整合層無法決定性製造「排入但
        未啟動」窗,以 worker 直呼鎖 guard 語意(stock_engine._retry_acquire 同款)。
        """
        from copycat.server.futures_engine import _EngineClosing

        src = _FlakySource({"TXF": 10_000})
        engine = FuturesEngine(lambda: src, resub_interval_secs=0.01)
        await engine.start()
        await engine.close()
        before = len(src.attempts)
        with pytest.raises(_EngineClosing):
            engine._retry_subscribe(src, "TXF")
        assert len(src.attempts) == before  # source 未被碰

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
            await _wait_until(lambda: "TXF" in src.subscribed)
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
        await _wait_until(lambda: len(src.attempts) > 3)  # 至少一次 retry 已拋 ValueError
        await engine.close()  # 不得重拋 ValueError
        assert src.closed  # source.close() 必達(KeepAlive 不洩漏)


class TestRetrySuccessLeafBookkeeping:
    """P2-1:重試把 HOT 掛回後,leaf fallback 記帳(`_leaf_fed`)必須撤銷。

    不撤銷的話:跨日重武裝把 leaf-fed 商品 p 清 None → 每天再補一次新月 leaf,
    同商品 HOT + leaf 雙訂閱天天複製(兩路餵同一 _handle_quote,seq/廣播加倍、
    tick 可短暫倒退)。當日已存在的雙訂閱接受(leaf 無退訂路、兩邊值相同)。
    """

    async def test_retry_success_discards_leaf_fed(self) -> None:
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
            await _wait_until(lambda: "TXF" in src.subscribed)
            await _drain()
            assert "TXF" not in engine._leaf_fed  # HOT 已回,跨日不得再複製 leaf
        finally:
            await engine.close()


class _ReconnectSource(FakeSource):
    """帶 on_reconnect 屬性的 source(對齊 TC4QuoteSource 介面;stock/corr fake 同款)。"""

    def __init__(self) -> None:
        super().__init__()
        self.on_reconnect: Callable[[], None] | None = None


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
        src.on_reconnect()
        try:
            await _wait_until(lambda: {"TXF", "MXF", "TMF"} <= set(src.subscribed))
        finally:
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

    async def _run(self, engine: FuturesEngine, caplog) -> list[Bar]:
        with caplog.at_level(logging.WARNING):
            return await engine.bars_range("TXF", "D", "2026-07-01", "2026-07-30")

    @pytest.mark.asyncio
    async def test_source_absent_returns_empty_with_fixed_log(self, caplog) -> None:
        engine = FuturesEngine(lambda: FakeSource())  # 未 start → _source is None
        got = await self._run(engine, caplog)
        assert got == []
        assert "market: futures history proxy miss" in caplog.text

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
        assert got == []
        assert "market: futures history proxy miss" in caplog.text


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
