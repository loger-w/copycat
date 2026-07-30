"""CorrelationEngine 的江波圖接線(SC-3/SC-4/SC-5):live 餵值、背景回補、delta 廣播。"""

from __future__ import annotations

import asyncio
from typing import Callable

from copycat.corr_config import CorrConfig, Leg
from copycat.server.corr_engine import CorrelationEngine

DAY = ("20260730", "day")

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
    def __init__(self) -> None:
        self.subscribed: list[str] = []
        self.closed = False
        self.cb: Callable[[dict], None] | None = None
        self.fetched: list[str] = []
        self.minutes: dict[str, list[tuple[int, int]]] = {}
        self.fail_1k: set[str] = set()

    def subscribe_raw(self, symbol: str) -> None:
        self.subscribed.append(symbol)

    def unsubscribe_raw(self, symbol: str) -> None:
        if symbol in self.subscribed:
            self.subscribed.remove(symbol)

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        self.cb = cb

    def fetch_day_1k(self, symbol: str) -> list[tuple[int, int]]:
        self.fetched.append(symbol)
        if symbol in self.fail_1k:
            raise ConnectionError(f"1K fail {symbol}")
        return self.minutes.get(symbol, [])

    def close(self) -> None:
        self.closed = True


def _trade_quote(symbol: str, price_milli: int, *, precise: str = "030030000000") -> dict:
    """帶成交的 REALTIME。

    `PreciseTime` 是 **12 位 HHMMSSffffff**(微秒;`stock_models._taipei_time` 以 zfill(12) 解析)
    → "030030000000" = UTC 03:00:30 = 台北 11:00:30 → 桶 11:01 = minute 661 → 日盤 offset 136。
    位數寫短會被 zfill 從左邊補零成完全不同的時刻(本測試第一版踩過:9 位 → UTC 00:00:30)。
    """
    return {
        "Symbol": symbol,
        "SecurityName": "x",
        "TradingPrice": str(price_milli / 1000),
        "TradeQuantity": "3",
        "TradeVolume": "100",
        "TradeDate": "20260730",
        "PreciseTime": precise,
        "Bid": str((price_milli - 1000) / 1000),
        "BidVolume": "5",
        "Ask": str((price_milli + 1000) / 1000),
        "AskVolume": "5",
    }


def _foreign_trade_quote(symbol: str, price_milli: int) -> dict:
    """海外腿(CME/CBOT/SGX)實測形狀:`PreciseTime` 是 **6 位 HHMMSS**,不是台期交的 12 位。

    Phase 6 real-env finding —— 用 zfill(12) 解讀 "41256" 會得到台北 08:00:00.041 的假時刻,
    分鐘落在日盤窗外 → 該腿永遠不進點。`FilledTime` 兩段同寬,改吃它。
    """
    return {
        "Symbol": symbol,
        "SecurityName": "x",
        "TradingPrice": str(price_milli / 1000),
        "TradeQuantity": "4",
        "TradeVolume": "100",
        "TradeDate": "20260730",
        "PreciseTime": "41256",  # 6 位;zfill(12) 會解成 00:00:00.041
        "FilledTime": "41256",  # 04:12:56 UTC → 台北 12:12:56 → 桶 12:13 = 733 → offset 208
        "Bid": str((price_milli - 1000) / 1000),
        "BidVolume": "5",
        "Ask": str((price_milli + 1000) / 1000),
        "AskVolume": "5",
    }


def _book_quote(symbol: str, bid: int, ask: int) -> dict:
    return {
        "Symbol": symbol,
        "SecurityName": "x",
        "Bid": str(bid / 1000),
        "BidVolume": "5",
        "Ask": str(ask / 1000),
        "AskVolume": "5",
    }


def _futures_state(price: int | None = 40_400_000) -> dict:
    return {
        "seq": 1,
        "products": {
            "TXF": {
                "product": "TXF",
                "p": price,
                "bids": [(price - 1000, 5)] if price is not None else [],
                "asks": [(price + 1000, 5)] if price is not None else [],
            }
        },
    }


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


async def _drain() -> None:
    for _ in range(30):
        await asyncio.sleep(0.001)


def _engine(
    source: _FakeSource,
    *,
    txf_state: Callable[[], dict] = lambda: _futures_state(),
    clock: _Clock | None = None,
    river_broadcast: Callable[[dict], None] | None = None,
    futures_minutes_fetch: Callable[[str], list[tuple[int, int]]] | None = None,
    taipei_time: str = "110030",
) -> CorrelationEngine:
    return CorrelationEngine(
        lambda: source,
        config=CONFIG,
        txf_state_getter=txf_state,
        tick_secs=1.0,
        now_fn=clock or _Clock(),
        session_fn=lambda: DAY,
        river_broadcast=river_broadcast,
        futures_minutes_fetch=futures_minutes_fetch,
        taipei_time_fn=lambda: taipei_time,
    )


def _minutes(eng: CorrelationEngine, key: str) -> dict[int, int]:
    return eng.river_snapshot()["legs"][key]["minutes"]


class TestLiveFeed:
    async def test_trade_tick_becomes_minute_point(self) -> None:
        src = _FakeSource()
        eng = _engine(src)
        await eng.start()
        try:
            assert src.cb is not None
            src.cb(_trade_quote("TC.F.CME.NQ.HOT", 27_638_000))
            await _drain()
            assert _minutes(eng, "NQ") == {136: 27_638_000}  # 11:01 → offset 136
        finally:
            await eng.close()

    async def test_book_only_quote_adds_no_point_but_mid_still_works(self) -> None:
        src = _FakeSource()
        eng = _engine(src)
        await eng.start()
        try:
            assert src.cb is not None
            src.cb(_book_quote("TC.F.CME.NQ.HOT", 27_637_000, 27_639_000))
            await _drain()
            assert _minutes(eng, "NQ") == {}
            eng.tick_once()
            assert eng.state()["legs"]["NQ"]["mid"] == 27_638_000  # 既有中價行為不變
        finally:
            await eng.close()

    async def test_foreign_leg_uses_filled_time_not_precise_time(self) -> None:
        """Phase 6 real-env finding:海外腿的 PreciseTime 是 6 位 → 必須用 FilledTime 分桶。"""
        src = _FakeSource()
        eng = _engine(src)
        await eng.start()
        try:
            assert src.cb is not None
            src.cb(_foreign_trade_quote("TC.F.CME.NQ.HOT", 27_638_000))
            await _drain()
            assert _minutes(eng, "NQ") == {208: 27_638_000}  # 12:13 → offset 208
        finally:
            await eng.close()

    async def test_tc4_leg_without_filled_time_falls_back_to_local_clock(self) -> None:
        """FilledTime 缺值/壞值 → 退回本機時鐘(與台指腿同款),不是丟掉這一點。"""
        src = _FakeSource()
        eng = _engine(src, taipei_time="110030")  # → 桶 11:01 = 661 → offset 136
        await eng.start()
        try:
            assert src.cb is not None
            quote = _foreign_trade_quote("TC.F.CME.NQ.HOT", 27_638_000)
            quote["FilledTime"] = ""
            src.cb(quote)
            await _drain()
            assert _minutes(eng, "NQ") == {136: 27_638_000}
        finally:
            await eng.close()

    async def test_futures_leg_point_from_tick_with_injected_clock(self) -> None:
        src = _FakeSource()
        eng = _engine(src)
        await eng.start()
        try:
            eng.tick_once()
            assert _minutes(eng, "TXF") == {136: 40_400_000}
        finally:
            await eng.close()

    async def test_futures_leg_empty_when_upstream_has_no_data(self) -> None:
        """SC-4:既有 bug 1 發作(futures_engine 零推播)→ 台指腿空著,其餘腿照常。"""
        src = _FakeSource()
        eng = _engine(src, txf_state=lambda: {})
        await eng.start()
        try:
            assert src.cb is not None
            src.cb(_trade_quote("TC.F.CME.NQ.HOT", 27_638_000))
            await _drain()
            eng.tick_once()
            assert _minutes(eng, "TXF") == {}
            assert _minutes(eng, "NQ") == {136: 27_638_000}
            assert eng.river_snapshot()["legs"]["TXF"]["last"] is None
        finally:
            await eng.close()


class TestBackfill:
    async def test_applies_per_tc4_leg(self) -> None:
        src = _FakeSource()
        src.minutes["TC.F.CME.NQ.HOT"] = [(600, 27_600_000), (601, 27_610_000)]
        eng = _engine(src)
        await eng.start()
        try:
            await _drain()
            assert _minutes(eng, "NQ") == {75: 27_600_000, 76: 27_610_000}
        finally:
            await eng.close()

    async def test_one_leg_failure_does_not_block_others(self) -> None:
        src = _FakeSource()
        src.minutes["TC.F.CME.NQ.HOT"] = [(600, 27_600_000)]
        src.fail_1k.add("TC.F.TWF.SXF.HOT")
        eng = _engine(src)
        await eng.start()
        try:
            await _drain()
            assert _minutes(eng, "NQ") == {75: 27_600_000}
            assert _minutes(eng, "SXF") == {}
        finally:
            await eng.close()

    async def test_never_requests_base_leg_symbol(self) -> None:
        """SC-4:台指的歷史也不可從 corr session 問(同 symbol 跨 session 只推一邊)。"""
        src = _FakeSource()
        eng = _engine(src, futures_minutes_fetch=lambda p: [])
        await eng.start()
        try:
            await _drain()
            assert "TC.F.TWF.TXF.HOT" not in src.fetched
            assert "TC.F.TWF.TXF.HOT" not in src.subscribed
        finally:
            await eng.close()

    async def test_futures_leg_backfill_goes_through_injected_fetch(self) -> None:
        src = _FakeSource()
        seen: list[str] = []

        def fetch(product: str) -> list[tuple[int, int]]:
            seen.append(product)
            return [(700, 40_300_000)]

        eng = _engine(src, futures_minutes_fetch=fetch)
        await eng.start()
        try:
            await _drain()
            assert seen == ["TXF"]  # leg.key == 期貨產品碼(design §4 假設)
            assert _minutes(eng, "TXF") == {175: 40_300_000}
        finally:
            await eng.close()

    async def test_backfill_does_not_overwrite_live_minute(self) -> None:
        src = _FakeSource()
        src.minutes["TC.F.CME.NQ.HOT"] = [(661, 27_000_000)]
        eng = _engine(src)
        await eng.start()
        try:
            assert src.cb is not None
            src.cb(_trade_quote("TC.F.CME.NQ.HOT", 27_638_000))  # live 先到,桶 661
            await _drain()
            assert _minutes(eng, "NQ") == {136: 27_638_000}
        finally:
            await eng.close()


class TestBackfillSessionOrdering:
    """Phase 4 自評 finding:回補任務不得把狀態機的盤別「拉回」發起時的那一場。

    情境:14:59:58 起跑的回補在 15:00:01 才回來 —— 此時 tick 已把 river 切到夜盤。
    若回補流程對狀態機重設發起時的 session,夜盤已累積的點會被清掉、窗也退回日盤,
    畫面出現一秒的錯盤別資料(下一拍才自我修正)。
    直呼私有 `_backfill_river` 是為了精確控制「回補晚於換場」的時序 —— 走 start() 無法
    穩定重現這個順序。
    """

    async def test_late_backfill_does_not_revert_session(self) -> None:
        src = _FakeSource()
        src.minutes["TC.F.CME.NQ.HOT"] = [(600, 27_600_000)]  # 日盤窗的分鐘
        sessions = [("20260730", "night")]
        eng = CorrelationEngine(
            lambda: src,
            config=CONFIG,
            txf_state_getter=lambda: _futures_state(),
            tick_secs=1.0,
            now_fn=_Clock(),
            session_fn=lambda: sessions[0],
            taipei_time_fn=lambda: "230030",  # 夜盤 23:01 → offset 481
        )
        await eng.start()
        try:
            await _drain()
            eng.tick_once()  # 夜盤點入帳
            assert _minutes(eng, "TXF") == {481: 40_400_000}

            sessions[0] = ("20260730", "day")  # 回補以「日盤」身分晚到
            await eng._backfill_river()

            snap = eng.river_snapshot()
            assert snap["session"] == "night"
            assert snap["window"] == {"start_min": 900, "end_min": 1740}
            assert _minutes(eng, "TXF") == {481: 40_400_000}  # 夜盤點沒被清掉
            assert _minutes(eng, "NQ") == {}  # 日盤回補資料不得混入夜盤
        finally:
            await eng.close()


class TestRiverBroadcast:
    async def test_one_delta_per_tick_with_monotonic_seq(self) -> None:
        src = _FakeSource()
        events: list[dict] = []
        eng = _engine(src, river_broadcast=events.append)
        await eng.start()
        try:
            eng.tick_once()
            eng.tick_once()
            assert [e["type"] for e in events] == ["river_delta", "river_delta"]
            assert [e["seq"] for e in events] == [1, 2]
            assert events[-1]["legs"]["TXF"] == {"m": 136, "p": 40_400_000}
            assert events[-1]["window"] == {"start_min": 525, "end_min": 825}
        finally:
            await eng.close()

    async def test_no_broadcast_after_close(self) -> None:
        src = _FakeSource()
        events: list[dict] = []
        eng = _engine(src, river_broadcast=events.append)
        await eng.start()
        eng.tick_once()
        await eng.close()
        n = len(events)
        assert src.cb is not None
        src.cb(_trade_quote("TC.F.CME.NQ.HOT", 27_638_000))  # close 後推播不得再進狀態
        await _drain()
        assert len(events) == n


class TestSnapshotShape:
    async def test_snapshot_carries_labels_window_and_base(self) -> None:
        src = _FakeSource()
        eng = _engine(src)
        await eng.start()
        try:
            snap = eng.river_snapshot()
            assert snap["type"] == "river"
            assert snap["base"] == "TXF"
            assert snap["session"] == "day"
            assert snap["window"] == {"start_min": 525, "end_min": 825}
            assert snap["legs"]["SXF"]["label"] == "費半"
        finally:
            await eng.close()
