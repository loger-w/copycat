"""CorrelationEngine:訂閱邊界、stale 判定、每秒 tick 廣播(SC-5/6)。"""

from __future__ import annotations

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
) -> CorrelationEngine:
    return CorrelationEngine(
        lambda: source,
        config=CONFIG,
        txf_state_getter=txf_state,
        broadcast=broadcast,
        tick_secs=1.0,
        now_fn=clock,
        session_fn=lambda: NIGHT,
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
                clock.t += 1.0
                eng.tick_once()

            assert eng.state()["pairs"]["NQ"]["w60"] is not None
        finally:
            await eng.close()
