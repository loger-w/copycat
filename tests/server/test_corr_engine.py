"""CorrelationEngine:訂閱邊界、stale 判定、每秒 tick 廣播(SC-5/6)。"""

from __future__ import annotations

import asyncio
from typing import Callable

from copycat.corr_config import CorrConfig, Leg
from copycat.server.corr_engine import CorrelationEngine

NIGHT = ("20260730", "night")

CONFIG = CorrConfig(
    legs=(
        Leg("TXF", "台指", "TC.F.TWF.TXF.HOT", "futures_engine"),
        Leg("NQ", "納指", "TC.F.CME.NQ.HOT", "tc4"),
        Leg("SXF", "費半", "TC.F.TWF.SXF.HOT", "tc4"),
    ),
    base="TXF",
    windows=(60,),
    min_samples={60: 3},
    stale_secs=30.0,
)


class _FakeSource:
    def __init__(self, *, fail_on: set[str] | None = None) -> None:
        self.subscribed: list[str] = []
        self.closed = False
        self.cb: Callable[[dict], None] | None = None
        self._fail_on = fail_on or set()

    def subscribe_raw(self, symbol: str) -> None:
        if symbol in self._fail_on:
            raise ConnectionError(f"SUBQUOTE fail {symbol}")
        self.subscribed.append(symbol)

    def unsubscribe_raw(self, symbol: str) -> None:
        if symbol in self.subscribed:
            self.subscribed.remove(symbol)

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        self.cb = cb

    def fetch_day_1k(self, symbol: str) -> list[tuple[int, int]]:
        return []  # 江波圖回補在本檔不受測(CorrSource Protocol 對齊用)

    def close(self) -> None:
        self.closed = True


def _quote(symbol: str, bid: int, ask: int) -> dict:
    return {
        "Symbol": symbol,
        "SecurityName": "x",
        "Bid": str(bid / 1000),
        "BidVolume": "5",
        "Ask": str(ask / 1000),
        "AskVolume": "5",
    }


def _futures_state(bid: int, ask: int, price: int = 40_400_000) -> dict:
    """futures_engine.state() 的形狀(products[key].bids/asks 為 (價毫元, 量) list)。"""
    return {
        "seq": 1,
        "products": {
            "TXF": {
                "product": "TXF",
                "p": price,
                "bids": [(bid, 5)],
                "asks": [(ask, 5)],
            }
        },
    }


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _engine(
    source: _FakeSource,
    *,
    txf_state: Callable[[], dict],
    clock: _Clock,
    broadcast: Callable[[dict], None] | None = None,
    resub_interval_secs: float = 10.0,
) -> CorrelationEngine:
    return CorrelationEngine(
        lambda: source,
        config=CONFIG,
        txf_state_getter=txf_state,
        broadcast=broadcast,
        tick_secs=1.0,
        now_fn=clock,
        session_fn=lambda: NIGHT,
        resub_interval_secs=resub_interval_secs,
    )


class TestSubscriptionBoundary:
    async def test_does_not_subscribe_base_leg_symbol(self) -> None:
        """SC-5:台指腿走 futures_engine,重複訂 TXF.HOT 會讓其中一邊永久零推播。"""
        src = _FakeSource()
        eng = _engine(src, txf_state=lambda: _futures_state(1, 2), clock=_Clock())

        await eng.start()
        try:
            assert "TC.F.TWF.TXF.HOT" not in src.subscribed
            assert set(src.subscribed) == {"TC.F.CME.NQ.HOT", "TC.F.TWF.SXF.HOT"}
        finally:
            await eng.close()

    async def test_single_leg_subscribe_failure_does_not_kill_engine(self) -> None:
        src = _FakeSource(fail_on={"TC.F.CME.NQ.HOT"})
        eng = _engine(src, txf_state=lambda: _futures_state(1, 2), clock=_Clock())

        await eng.start()
        try:
            assert src.subscribed == ["TC.F.TWF.SXF.HOT"]
        finally:
            await eng.close()

    async def test_close_closes_source(self) -> None:
        src = _FakeSource()
        eng = _engine(src, txf_state=lambda: _futures_state(1, 2), clock=_Clock())
        await eng.start()
        await eng.close()
        assert src.closed is True


class TestStaleHandling:
    async def test_leg_without_quotes_is_stale_and_mid_none(self) -> None:
        src = _FakeSource()
        clock = _Clock()
        eng = _engine(src, txf_state=lambda: _futures_state(1, 2), clock=clock)
        await eng.start()
        try:
            eng.tick_once()
            assert eng.state()["legs"]["NQ"]["mid"] is None
            assert eng.state()["legs"]["NQ"]["stale"] is True
        finally:
            await eng.close()

    async def test_quote_makes_leg_fresh(self) -> None:
        src = _FakeSource()
        clock = _Clock()
        eng = _engine(src, txf_state=lambda: _futures_state(1, 2), clock=clock)
        await eng.start()
        try:
            assert src.cb is not None
            src.cb(_quote("TC.F.CME.NQ.HOT", 27_000_000, 27_002_000))
            await asyncio.sleep(0)
            eng.tick_once()

            leg = eng.state()["legs"]["NQ"]
            assert leg["mid"] == 27_001_000
            assert leg["stale"] is False
        finally:
            await eng.close()

    async def test_stale_leg_does_not_carry_forward(self) -> None:
        """超過 stale_secs 沒更新 → None,不得沿用最後一筆中價(SC-2 界線)。"""
        src = _FakeSource()
        clock = _Clock()
        eng = _engine(src, txf_state=lambda: _futures_state(1, 2), clock=clock)
        await eng.start()
        try:
            assert src.cb is not None
            src.cb(_quote("TC.F.CME.NQ.HOT", 27_000_000, 27_002_000))
            await asyncio.sleep(0)
            eng.tick_once()
            assert eng.state()["legs"]["NQ"]["mid"] == 27_001_000

            clock.t += 31.0
            eng.tick_once()

            assert eng.state()["legs"]["NQ"]["mid"] is None
            assert eng.state()["legs"]["NQ"]["stale"] is True
        finally:
            await eng.close()


class TestFuturesEngineLeg:
    async def test_base_leg_stays_fresh_while_book_changes(self) -> None:
        """impl review P0-3 迴歸鎖。

        base 腿刻意不訂閱 → 永遠不進 _handle_quote。若沿用「收到推播才更新
        last_update」會恆判 stale,導致 base 恆 None、**所有配對恆 None** 而無錯誤訊號。
        新鮮度必須改以內容變化判定。
        """
        src = _FakeSource()
        clock = _Clock()
        book = {"bid": 40_399_000, "ask": 40_401_000}
        eng = _engine(
            src,
            txf_state=lambda: _futures_state(book["bid"], book["ask"]),
            clock=clock,
        )
        await eng.start()
        try:
            for i in range(40):
                book["bid"] += 1000
                book["ask"] += 1000
                clock.t += 1.0
                eng.tick_once()

            base = eng.state()["legs"]["TXF"]
            assert base["stale"] is False
            assert base["mid"] is not None
        finally:
            await eng.close()

    async def test_base_leg_goes_stale_when_book_frozen(self) -> None:
        src = _FakeSource()
        clock = _Clock()
        eng = _engine(src, txf_state=lambda: _futures_state(40_399_000, 40_401_000), clock=clock)
        await eng.start()
        try:
            eng.tick_once()
            assert eng.state()["legs"]["TXF"]["stale"] is False

            clock.t += 31.0
            eng.tick_once()

            assert eng.state()["legs"]["TXF"]["stale"] is True
        finally:
            await eng.close()

    async def test_empty_futures_state_yields_none_pairs_without_raising(self) -> None:
        src = _FakeSource()
        eng = _engine(src, txf_state=dict, clock=_Clock())
        await eng.start()
        try:
            eng.tick_once()

            state = eng.state()
            assert state["legs"]["TXF"]["mid"] is None
            assert all(row["w60"] is None for row in state["pairs"].values())
        finally:
            await eng.close()


class TestBroadcastAndState:
    async def test_each_tick_broadcasts_once_with_increasing_seq(self) -> None:
        src = _FakeSource()
        sent: list[dict] = []
        eng = _engine(
            src, txf_state=lambda: _futures_state(1, 2), clock=_Clock(), broadcast=sent.append
        )
        await eng.start()
        try:
            for _ in range(5):
                eng.tick_once()

            assert len(sent) == 5
            assert [m["seq"] for m in sent] == [1, 2, 3, 4, 5]
            assert all(m["type"] == "corr" for m in sent)
        finally:
            await eng.close()

    async def test_state_exposes_labels_and_base(self) -> None:
        src = _FakeSource()
        eng = _engine(src, txf_state=lambda: _futures_state(1, 2), clock=_Clock())
        await eng.start()
        try:
            eng.tick_once()
            state = eng.state()

            assert state["base"] == "TXF"
            assert state["legs"]["SXF"]["label"] == "費半"
            assert set(state["pairs"]) == {"NQ", "SXF"}
        finally:
            await eng.close()

    async def test_correlation_appears_after_enough_samples(self) -> None:
        src = _FakeSource()
        clock = _Clock()
        book = {"bid": 40_399_000, "ask": 40_401_000}
        eng = _engine(src, txf_state=lambda: _futures_state(book["bid"], book["ask"]), clock=clock)
        await eng.start()
        try:
            assert src.cb is not None
            nq = 27_000_000
            for i in range(10):
                step = 1000 if i % 2 == 0 else -500
                book["bid"] += step
                book["ask"] += step
                nq += step
                src.cb(_quote("TC.F.CME.NQ.HOT", nq, nq + 2000))
                await asyncio.sleep(0)
                clock.t += 1.0
                eng.tick_once()

            assert eng.state()["pairs"]["NQ"]["w60"] is not None
        finally:
            await eng.close()


class _FlakySource(_FakeSource):
    """前 N 次 subscribe_raw raise ConnectionError,之後成功;attempts 記每次呼叫。

    (仿 tests/server/test_futures_engine.py 的 `_FlakySource`:失敗次數本身是被鎖的行為,
    `subscribed` 只記成功,測不到「重試了幾次」。)
    """

    def __init__(self, fail_times: dict[str, int] | None = None) -> None:
        super().__init__()
        self._left = dict(fail_times or {})
        self.attempts: list[str] = []

    def subscribe_raw(self, symbol: str) -> None:
        self.attempts.append(symbol)
        left = self._left.get(symbol, 0)
        if left > 0:
            self._left[symbol] = left - 1
            raise ConnectionError(f"SUBQUOTE fail {symbol}")
        super().subscribe_raw(symbol)


async def _wait_until(pred: Callable[[], bool], timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if pred():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("條件逾時未成立")


class TestPendingResubscribe:
    """腿訂閱失敗的**零重試路徑**(mod/subscribe-retry-recovery SC-1)。

    corr 的 `_on_reconnect` 只重跑江波圖回補、不重訂閱 → 首輪 SUBQUOTE 失敗的腿整天
    無相關係數也無 live 點,且沒有任何錯誤訊號。照抄 futures_engine 的 pending-resub 形狀。
    """

    async def test_failed_legs_retried_until_success(self) -> None:
        src = _FlakySource({"TC.F.CME.NQ.HOT": 2})
        eng = _engine(
            src, txf_state=lambda: _futures_state(1, 2), clock=_Clock(), resub_interval_secs=0.01
        )
        await eng.start()
        assert src.subscribed == ["TC.F.TWF.SXF.HOT"]  # 首輪只有費半成功
        try:
            await _wait_until(lambda: "TC.F.CME.NQ.HOT" in src.subscribed)
        finally:
            await eng.close()
        assert src.attempts.count("TC.F.CME.NQ.HOT") == 3  # 失敗 2 次 + 成功 1 次
        assert src.attempts.count("TC.F.TWF.SXF.HOT") == 1  # 成功腿不重訂

    async def test_quote_flows_after_retry_success(self) -> None:
        src = _FlakySource({"TC.F.CME.NQ.HOT": 1})
        clock = _Clock()
        eng = _engine(
            src, txf_state=lambda: _futures_state(1, 2), clock=clock, resub_interval_secs=0.01
        )
        await eng.start()
        try:
            await _wait_until(lambda: "TC.F.CME.NQ.HOT" in src.subscribed)
            assert src.cb is not None
            src.cb(_quote("TC.F.CME.NQ.HOT", 27_000_000, 27_002_000))
            await asyncio.sleep(0)
            eng.tick_once()
            assert eng.state()["legs"]["NQ"]["mid"] == 27_001_000
        finally:
            await eng.close()

    async def test_all_success_leaves_no_retry_task(self) -> None:
        src = _FlakySource()
        eng = _engine(
            src, txf_state=lambda: _futures_state(1, 2), clock=_Clock(), resub_interval_secs=0.01
        )
        await eng.start()
        try:
            await asyncio.sleep(0.05)  # 5 個間隔
            # 訂閱全成功時行為與修復前完全相同(SC-4);不看 `asyncio.all_tasks()` 數量 ——
            # start() 本來就會建 tick / backfill 兩個 task
            assert eng._resub_task is None
            assert sorted(src.attempts) == ["TC.F.CME.NQ.HOT", "TC.F.TWF.SXF.HOT"]
        finally:
            await eng.close()

    async def test_close_stops_retry_loop(self) -> None:
        src = _FlakySource({"TC.F.CME.NQ.HOT": 10_000, "TC.F.TWF.SXF.HOT": 10_000})
        eng = _engine(
            src, txf_state=lambda: _futures_state(1, 2), clock=_Clock(), resub_interval_secs=0.01
        )
        await eng.start()
        await _wait_until(lambda: len(src.attempts) > 4)  # 重試迴圈確實在跑
        await eng.close()
        n = len(src.attempts)
        await asyncio.sleep(0.05)  # 5 個間隔
        assert len(src.attempts) <= n + 1  # 至多一個 in-flight thread,不再新排

    async def test_base_leg_never_subscribed_by_retry(self) -> None:
        """白名單 1:base 腿(futures_engine 來源)永不 subscribe_raw。

        重試佇列只收 `tc4_legs()` 的腿 —— base 腿本來就不進 `_subscribe_all` 迭代,
        所以「失敗腿含 base」不可構造;這條鎖的是「重試迴圈不得自己去掃全部腿」。
        """
        src = _FlakySource({"TC.F.CME.NQ.HOT": 10_000})
        eng = _engine(
            src, txf_state=lambda: _futures_state(1, 2), clock=_Clock(), resub_interval_secs=0.01
        )
        await eng.start()
        try:
            await _wait_until(lambda: src.attempts.count("TC.F.CME.NQ.HOT") >= 5)
            assert "TC.F.TWF.TXF.HOT" not in src.attempts
            assert "TC.F.TWF.TXF.HOT" not in src.subscribed
        finally:
            await eng.close()


class TestNoHardcodedSymbols:
    def test_engine_module_has_no_tc4_symbol_literals(self) -> None:
        """SC-8 lock:商品清單走設定檔,引擎內不得出現 symbol 字面值。

        沒有這條鎖,日後有人為了除錯在引擎裡寫死一條 symbol,「加腿只需改設定檔」
        會靜默失效而沒有任何測試會紅。

        以 AST 取字串常數而非整檔 grep:docstring 裡為了說明而提到 symbol 是正當的
        (本檔自己就是例子),整檔 grep 會把說明誤判成 hardcode。
        """
        import ast
        from pathlib import Path

        import copycat.server.corr_engine as mod

        tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
        offending: list[str] = []

        class _Visitor(ast.NodeVisitor):
            def visit_Expr(self, node: ast.Expr) -> None:
                # 獨立字串陳述句 = docstring,不算字面值
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    return
                self.generic_visit(node)

            def visit_Constant(self, node: ast.Constant) -> None:
                if isinstance(node.value, str) and ("TC.F." in node.value or "TC.S." in node.value):
                    offending.append(node.value)

        _Visitor().visit(tree)
        assert offending == []
