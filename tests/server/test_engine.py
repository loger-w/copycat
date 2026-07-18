from __future__ import annotations

import asyncio
from typing import Callable

from copycat.live.models import OptionContract, SeriesInfo, Tick
from copycat.server.engine import EngineRuntime

C44000 = OptionContract(symbol="TC.O.TWF.TX4.202607.C.44000", cp="C", strike_millipts=44_000_000)
C45000 = OptionContract(symbol="TC.O.TWF.TX5.202607.C.45000", cp="C", strike_millipts=45_000_000)
SERIES_A = SeriesInfo(
    series_id="TX4.202607", name="TX4 202607", expiry="202607", contracts=(C44000,)
)
SERIES_B = SeriesInfo(
    series_id="TX5.202607", name="TX5 202607", expiry="202607", contracts=(C45000,)
)


def tick(symbol: str, *, price: int, qty: int, cum: int | None = None, t: int = 1) -> Tick:
    return Tick(
        symbol=symbol,
        precise_time=t,
        price_millipts=price,
        qty=qty,
        bid_millipts=price - 1_000,
        ask_millipts=price,
        cum_volume=cum,
    )


class FakeQuoteSource:
    def __init__(self, backfill: dict[str, list[Tick]] | None = None) -> None:
        self.backfill = backfill or {}
        self.on_tick: Callable[[Tick], None] | None = None
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.backfill_calls: list[str] = []
        self.closed = False

    def list_series(self) -> list[SeriesInfo]:
        return [SERIES_A, SERIES_B]

    def fetch_backfill(self, series: SeriesInfo) -> list[Tick]:
        self.backfill_calls.append(series.series_id)
        return list(self.backfill.get(series.series_id, []))

    def subscribe(self, series: SeriesInfo, on_tick: Callable[[Tick], None]) -> None:
        self.on_tick = on_tick
        self.subscribed.append(series.series_id)

    def unsubscribe(self, series: SeriesInfo) -> None:
        self.unsubscribed.append(series.series_id)

    def close(self) -> None:
        self.closed = True


async def test_start_activates_first_series_with_backfill() -> None:
    fake = FakeQuoteSource(
        backfill={"TX4.202607": [tick(C44000.symbol, price=100_000, qty=3, t=1)]}
    )
    rt = EngineRuntime(fake, throttle_secs=0.01)
    await rt.start()
    try:
        snap = rt.latest_snapshot()
        assert snap["series_id"] == "TX4.202607"
        assert snap["status"] == "live"
        assert snap["totals"]["call_net_qty"] == 3
        assert fake.subscribed == ["TX4.202607"]
    finally:
        await rt.close()
    assert fake.closed is True


async def test_live_tick_after_handover_flows_into_snapshot() -> None:
    fake = FakeQuoteSource()
    rt = EngineRuntime(fake, throttle_secs=0.01)
    await rt.start()
    try:
        assert fake.on_tick is not None
        fake.on_tick(tick(C44000.symbol, price=100_000, qty=2, cum=2, t=5))
        await asyncio.sleep(0.05)
        assert rt.latest_snapshot()["totals"]["call_net_qty"] == 2
    finally:
        await rt.close()


async def test_activate_switches_series_and_resets() -> None:
    fake = FakeQuoteSource(
        backfill={"TX4.202607": [tick(C44000.symbol, price=100_000, qty=3, t=1)]}
    )
    rt = EngineRuntime(fake, throttle_secs=0.01)
    await rt.start()
    try:
        await rt.activate("TX5.202607")
        snap = rt.latest_snapshot()
        assert snap["series_id"] == "TX5.202607"
        assert snap["totals"]["call_net_qty"] == 0
        assert snap["totals"]["ticks"] == 0
        assert "TX4.202607" in fake.unsubscribed
    finally:
        await rt.close()


async def test_unknown_series_raises() -> None:
    fake = FakeQuoteSource()
    rt = EngineRuntime(fake, throttle_secs=0.01)
    await rt.start()
    try:
        import pytest

        with pytest.raises(KeyError):
            await rt.activate("NOPE")
    finally:
        await rt.close()


async def test_queue_overflow_counts_and_self_heals() -> None:
    fake = FakeQuoteSource()
    rt = EngineRuntime(fake, throttle_secs=0.01, queue_maxsize=1)
    await rt.start()
    try:
        assert fake.on_tick is not None
        rt.pause_consume_for_test()
        fake.on_tick(tick(C44000.symbol, price=100_000, qty=1, cum=1, t=1))
        fake.on_tick(tick(C44000.symbol, price=100_000, qty=1, cum=2, t=2))  # 滿載 → 丟
        await asyncio.sleep(0.05)  # 讓 call_soon_threadsafe 的 _enqueue 執行
        assert rt.queue_dropped == 1
        rt.resume_consume_for_test()
        await asyncio.sleep(0.1)
        # 自癒:queue 清空後重跑交接(re-backfill 被呼叫第二次)
        assert fake.backfill_calls.count("TX4.202607") >= 2
        assert rt.latest_snapshot()["totals"]["queue_dropped"] == 1
    finally:
        await rt.close()


def test_fmt_precise_time_converts_utc_to_taipei() -> None:
    """PreciseTime 為 UTC(spike 實測 00:45 = 台北 08:45 開盤),顯示須 +8。"""
    from copycat.server.engine import _fmt_precise_time

    assert _fmt_precise_time(4500127000) == "08:45:00"  # 004500.127 UTC
    assert _fmt_precise_time(235959000000) == "07:59:59"  # 跨日 wrap


async def test_not_ready_snapshot_totals_is_none() -> None:
    """engine 未就緒時 totals 必須是 None(非空 dict),前端 truthy guard 才會生效。"""
    rt = EngineRuntime(FakeQuoteSource(), throttle_secs=0.01)
    snap = rt.latest_snapshot()
    assert snap["series_id"] is None
    assert snap["totals"] is None


async def test_reconnect_self_heal_fires_under_continuous_ticks() -> None:
    """request_self_heal 後即使 tick 連續流入(queue 永不 timeout),自癒仍須觸發。"""
    fake = FakeQuoteSource()
    rt = EngineRuntime(fake, throttle_secs=0.01)
    await rt.start()
    try:
        assert fake.on_tick is not None
        rt.request_self_heal()

        async def feeder() -> None:
            for i in range(120):
                assert fake.on_tick is not None
                fake.on_tick(tick(C44000.symbol, price=100_000, qty=1, cum=i + 1, t=i + 1))
                await asyncio.sleep(0.005)

        task = asyncio.create_task(feeder())
        await asyncio.sleep(0.25)  # feed 進行中(gap << timeout,timeout 分支不會觸發)
        healed = fake.backfill_calls.count("TX4.202607")
        task.cancel()
        assert healed >= 2
    finally:
        await rt.close()


async def test_snapshots_throttled_stream_yields_on_change() -> None:
    fake = FakeQuoteSource()
    rt = EngineRuntime(fake, throttle_secs=0.01)
    await rt.start()
    try:
        assert fake.on_tick is not None
        agen = rt.snapshots()
        fake.on_tick(tick(C44000.symbol, price=100_000, qty=1, cum=1, t=1))
        snap = await asyncio.wait_for(agen.__anext__(), timeout=1.0)
        assert snap["totals"]["call_net_qty"] == 1
        await agen.aclose()
    finally:
        await rt.close()
