"""IndexEngine 測試 — index-board SC-4(design v4)."""

from __future__ import annotations

import asyncio
import datetime as _dt
from typing import Any, Callable

from copycat.server.index_engine import IndexEngine, minute_key
from copycat.server.mis import OtcSnap


class FakeIndexSource:
    def __init__(self) -> None:
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.trade_dates: list[str] = []
        self.day_minutes: dict[str, int] | Exception = {}
        self.on_message: Callable[[dict], None] | None = None
        self.subscribe_error: Exception | None = None
        self.closed = False

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


def _quote(price: str = "42039.92", filled: str = "13015") -> dict:
    return {
        "Security": "IX0001",
        "TradingPrice": price,
        "ReferencePrice": "43634.19",
        "HighPrice": "43221.93",
        "LowPrice": "41815.78",
        "FilledTime": filled,
    }


OTC_SNAP = OtcSnap(p=359_800, ref=378_090, open=373_420, high=373_420, low=358_430, time="101610")


def make_engine(
    fake: FakeIndexSource,
    *,
    mis_fetch: Any = lambda: None,
    txf_getter: Callable[[], int | None] = lambda: None,
    trade_date: str = "2026-07-28",
    rollover: bool = False,
    today_fn: Any = None,
    in_watch_window: Any = None,
    stale_secs: float = 999.0,
    retry_secs: float = 0.01,
) -> IndexEngine:
    return IndexEngine(
        fake,  # type: ignore[arg-type]
        txf_getter=txf_getter,
        mis_fetch=mis_fetch,
        trade_date=trade_date,
        rollover=rollover,
        today_fn=today_fn or (lambda: _dt.date(2026, 7, 28)),
        in_watch_window=in_watch_window or (lambda: False),
        poll_secs=0.02,
        throttle_secs=0.02,
        stale_secs=stale_secs,
        retry_secs=retry_secs,
    )


class TestMinuteKey:
    def test_utc_realtime_floor_plus_one(self) -> None:
        assert minute_key("13015", utc=True) == "0931"  # 01:30:15 UTC → 09:30 → +1
        assert minute_key("10005", utc=True) == "0901"  # 09:00:05 → 0901
        assert minute_key("52959", utc=True) == "1330"  # 13:29:59 → 1330
        assert minute_key("53000", utc=True) == "1330"  # 13:30:00 → 1331 clamp
        assert minute_key("53600", utc=True) is None  # 13:36 → 丟棄
        assert minute_key("5900", utc=True) is None  # 08:59 → 域外

    def test_taipei_mis_no_double_shift(self) -> None:
        assert minute_key("101610", utc=False) == "1017"  # IR3:不 +8
        assert minute_key("090005", utc=False) == "0901"


async def test_start_subscribes_and_loads_backfill() -> None:
    fake = FakeIndexSource()
    fake.day_minutes = {"0901": 43_000_000, "0902": 43_100_000}
    eng = make_engine(fake)
    await eng.start()
    try:
        assert fake.subscribed == ["IX0001"]
        assert fake.trade_dates[0] == "2026-07-28"
        state = eng.state()
        assert state["trade_date"] == "2026-07-28"
        assert state["twse"]["minutes"] == {"0901": 43_000_000, "0902": 43_100_000}
        assert state["twse"]["stale"] is False
        assert state["txf"] is None
    finally:
        await eng.close()
    assert fake.closed is True


async def test_quote_updates_and_broadcasts() -> None:
    fake = FakeIndexSource()
    eng = make_engine(fake)
    await eng.start()
    try:
        stream = eng.stream()
        assert fake.on_message is not None
        fake.on_message(_quote())
        await asyncio.sleep(0.06)
        state = eng.state()
        assert state["twse"]["p"] == 42_039_920
        assert state["twse"]["ref"] == 43_634_190
        assert state["twse"]["minutes"]["0931"] == 42_039_920
        msg = await asyncio.wait_for(stream.__anext__(), timeout=1)
        assert msg["type"] == "index"
        assert msg["trade_date"] == "2026-07-28"
        assert msg["twse"]["last_minute"] == ["0931", 42_039_920]
    finally:
        await eng.close()


async def test_mis_updates_and_survives_failures() -> None:
    calls: list[int] = []
    results: list[Any] = [OTC_SNAP, RuntimeError("boom"), None, OTC_SNAP]

    def mis_fetch() -> OtcSnap | None:
        calls.append(1)
        r = results.pop(0) if results else None
        if isinstance(r, Exception):
            raise r
        return r

    fake = FakeIndexSource()
    eng = make_engine(fake, mis_fetch=mis_fetch)
    await eng.start()
    try:
        await asyncio.sleep(0.15)
        state = eng.state()
        assert state["otc"]["p"] == 359_800  # 首拍成功
        assert state["otc"]["minutes"] == {"1017": 359_800}
        assert len(calls) >= 3  # RuntimeError 沒殺死 loop
    finally:
        await eng.close()


async def test_start_connection_error_sets_stale_then_retry_recovers() -> None:
    fake = FakeIndexSource()
    fake.subscribe_error = ConnectionError("tc4 down")
    eng = make_engine(fake)
    await eng.start()
    try:
        assert eng.state()["twse"]["stale"] is True
        fake.subscribe_error = None  # TC4 恢復
        await asyncio.sleep(0.2)
        assert eng.state()["twse"]["stale"] is False
        assert fake.subscribed == ["IX0001"]
    finally:
        await eng.close()


async def test_watchdog_marks_stale_and_broadcasts_without_pushes() -> None:
    fake = FakeIndexSource()
    eng = make_engine(fake, in_watch_window=lambda: True, stale_secs=0.03)
    await eng.start()
    try:
        stream = eng.stream()
        await asyncio.sleep(0.12)
        assert eng.state()["twse"]["stale"] is True
        msg = await asyncio.wait_for(stream.__anext__(), timeout=1)
        assert msg["twse"]["stale"] is True  # IR7:停止推播仍廣播
        assert fake.on_message is not None
        fake.on_message(_quote())
        await asyncio.sleep(0.08)
        assert eng.state()["twse"]["stale"] is False
    finally:
        await eng.close()


async def test_watchdog_inactive_outside_window() -> None:
    fake = FakeIndexSource()
    eng = make_engine(fake, in_watch_window=lambda: False, stale_secs=0.03)
    await eng.start()
    try:
        await asyncio.sleep(0.1)
        assert eng.state()["twse"]["stale"] is False
    finally:
        await eng.close()


async def test_txf_from_getter_with_selfrecorded_time() -> None:
    price: list[int | None] = [None]
    fake = FakeIndexSource()
    eng = make_engine(fake, txf_getter=lambda: price[0])
    await eng.start()
    try:
        assert eng.state()["txf"] is None
        price[0] = 42_142_000
        await asyncio.sleep(0.06)
        txf = eng.state()["txf"]
        assert txf is not None
        assert txf["p"] == 42_142_000
        assert len(txf["time"]) == 8  # HH:MM:SS 自記(IR1)
    finally:
        await eng.close()


async def test_rollover_two_phase() -> None:
    fake = FakeIndexSource()
    fake.day_minutes = {"0901": 1_000}
    today = [_dt.date(2026, 7, 28)]
    eng = make_engine(fake, rollover=True, today_fn=lambda: today[0])
    # rollover loop 檢查間隔綁 poll_secs 級(測試注入短間隔)
    eng._rollover_check_secs = 0.03  # type: ignore[attr-defined]
    await eng.start()
    try:
        assert fake.on_message is not None
        fake.on_message(_quote())
        await asyncio.sleep(0.05)
        assert eng.state()["twse"]["minutes"]["0931"] == 42_039_920
        # 換日:先讓回補回空 → 不清舊
        fake.day_minutes = {}
        today[0] = _dt.date(2026, 7, 29)
        await asyncio.sleep(0.1)
        assert "0931" in eng.state()["twse"]["minutes"]  # 空回補不清(F6)
        assert "2026-07-29" in fake.trade_dates  # set_trade_date 已切
        assert fake.subscribed.count("IX0001") >= 2  # 重掛(IR2)
        # 回補有料 → swap
        fake.day_minutes = {"0901": 2_000}
        await asyncio.sleep(0.1)
        state = eng.state()
        assert state["trade_date"] == "2026-07-29"
        assert state["twse"]["minutes"] == {"0901": 2_000}
        assert state["otc"]["minutes"] == {}
    finally:
        await eng.close()


async def test_rollover_disabled_does_nothing() -> None:
    fake = FakeIndexSource()
    today = [_dt.date(2026, 7, 29)]
    eng = make_engine(fake, rollover=False, today_fn=lambda: today[0], trade_date="2026-07-28")
    await eng.start()
    try:
        await asyncio.sleep(0.1)
        assert eng.state()["trade_date"] == "2026-07-28"
        assert fake.trade_dates == ["2026-07-28"]  # 只有 start 同步那次
    finally:
        await eng.close()


async def test_close_cancels_all_tasks() -> None:
    fake = FakeIndexSource()
    eng = make_engine(fake)
    await eng.start()
    await eng.close()
    assert fake.closed is True
    assert all(t.done() for t in eng._tasks)  # type: ignore[attr-defined]
