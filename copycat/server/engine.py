"""EngineRuntime:tick queue 消費、交接協定編排、節流 snapshot 流(design.md §4)。"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncGenerator, Callable, Protocol

from copycat.live.aggregate import ChainAggregator
from copycat.live.handover import HandoverBuffer, run_handover
from copycat.live.models import SeriesInfo, Tick

logger = logging.getLogger(__name__)

_HANDOVER_RETRIES = 3


class QuoteSource(Protocol):
    """行情來源抽象;TC4 實作在 copycat.live.tc4,測試注入 fake。"""

    def list_series(self) -> list[SeriesInfo]: ...

    def fetch_backfill(self, series: SeriesInfo) -> list[Tick]: ...

    def subscribe(self, series: SeriesInfo, on_tick: Callable[[Tick], None]) -> None: ...

    def unsubscribe(self, series: SeriesInfo) -> None: ...

    def close(self) -> None: ...


def _fmt_precise_time(precise_time: int) -> str:
    """PreciseTime(UTC HHMMSS+µs)→ 台北 HH:MM:SS(+8,Phase 6 實測 00:45=開盤 08:45)。"""
    hhmmss = str(precise_time).zfill(12)[:6]
    hour = (int(hhmmss[0:2]) + 8) % 24
    return f"{hour:02d}:{hhmmss[2:4]}:{hhmmss[4:6]}"


class EngineRuntime:
    """單一 active 序列的執行時:queue 消費 + 交接 + 自癒 + 節流廣播。"""

    def __init__(
        self,
        source: QuoteSource,
        *,
        throttle_secs: float = 1.0,
        queue_maxsize: int = 10_000,
    ) -> None:
        self._source = source
        self._throttle = throttle_secs
        self._queue: asyncio.Queue[Tick] = asyncio.Queue(maxsize=queue_maxsize)
        self._agg: ChainAggregator | None = None
        self._series: dict[str, SeriesInfo] = {}
        self._active: SeriesInfo | None = None
        self._buffer: HandoverBuffer | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._consume_task: asyncio.Task[None] | None = None
        self._paused = False
        self.status = "connecting"
        self.queue_dropped = 0
        self._healed_dropped = 0
        self._force_heal = False
        self._accumulated_from = "-"
        self._version = 0
        self._changed = asyncio.Event()

    # ---- 對外查詢 ----

    def list_series(self) -> list[SeriesInfo]:
        return list(self._series.values())

    def latest_snapshot(self) -> dict:
        if self._agg is None or self._active is None:
            # totals 必須是 None 而非空 dict:前端以 truthy 判斷有無數據(C-1)
            return {"series_id": None, "status": self.status, "totals": None, "curve": []}
        return self._agg.snapshot(
            series=self._active,
            status=self.status,
            accumulated_from=self._accumulated_from,
            generated_at=time.strftime("%H:%M:%S"),
            queue_dropped=self.queue_dropped,
        )

    async def snapshots(self) -> AsyncGenerator[dict, None]:
        """節流 snapshot 流:版本有變才 yield,間隔 ≥ throttle_secs。"""
        last = self._version
        while True:
            await self._changed.wait()
            self._changed.clear()
            if self._version == last:
                continue
            last = self._version
            yield self.latest_snapshot()
            await asyncio.sleep(self._throttle)

    # ---- 生命週期 ----

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        if hasattr(self._source, "on_reconnect"):
            self._source.on_reconnect = self.request_self_heal  # type: ignore[attr-defined]
        series = await asyncio.to_thread(self._source.list_series)
        self._series = {s.series_id: s for s in series}
        self._consume_task = asyncio.create_task(self._consume())
        if series:
            await self.activate(series[0].series_id)

    async def close(self) -> None:
        if self._consume_task is not None:
            self._consume_task.cancel()
            try:
                await self._consume_task
            except asyncio.CancelledError:
                pass
        await asyncio.to_thread(self._source.close)

    # ---- 序列切換與交接 ----

    async def activate(self, series_id: str) -> None:
        """§4 select 流程:unsub 舊 → reset → 交接協定(訂閱 buffer → 回補 → flush)→ live。"""
        series = self._series[series_id]  # 未知 series → KeyError(route 層轉 400)
        if self._active is not None and self._active.series_id != series_id:
            await asyncio.to_thread(self._source.unsubscribe, self._active)
        self._active = series
        if self._agg is None:
            self._agg = ChainAggregator(series.contracts)
        else:
            self._agg.reset(series.contracts)
        await self._run_handover(series, subscribe=True)

    async def _run_handover(self, series: SeriesInfo, *, subscribe: bool) -> None:
        assert self._agg is not None
        for attempt in range(1, _HANDOVER_RETRIES + 1):
            self.status = "backfilling"
            self._mark_changed()
            self._buffer = HandoverBuffer()
            if subscribe or attempt > 1:
                await asyncio.to_thread(self._source.subscribe, series, self.on_tick)
                subscribe = False
            backfill = await asyncio.to_thread(self._source.fetch_backfill, series)
            buffer = self._buffer
            self._buffer = None
            if buffer is None or buffer.overflowed:
                logger.warning("handover buffer overflow (attempt %d), retrying", attempt)
                continue
            run_handover(self._agg, backfill, buffer)
            if backfill:
                first = min(t.precise_time for t in backfill)
                self._accumulated_from = _fmt_precise_time(first)
            self.status = "live"
            self._mark_changed()
            return
        self.status = "degraded"
        self._mark_changed()
        logger.warning("handover degraded after %d attempts", _HANDOVER_RETRIES)

    # ---- tick 入口(source thread → loop)----

    def on_tick(self, tick: Tick) -> None:
        loop = self._loop
        if loop is None:
            return
        loop.call_soon_threadsafe(self._enqueue, tick)

    def _enqueue(self, tick: Tick) -> None:
        if self._buffer is not None:
            self._buffer.append(tick)  # 溢出由 _run_handover 檢查重跑
            return
        try:
            self._queue.put_nowait(tick)
        except asyncio.QueueFull:
            self.queue_dropped += 1
            logger.warning("tick queue full, dropped (total=%d)", self.queue_dropped)

    async def _consume(self) -> None:
        while True:
            if self._paused:
                await asyncio.sleep(0.01)
                continue
            try:
                tick = await asyncio.wait_for(self._queue.get(), timeout=0.05)
            except TimeoutError:
                await self._maybe_self_heal()
                continue
            if self._agg is not None:
                self._agg.route(tick)
                self._mark_changed()
            if self._force_heal:
                # 重連自癒不能只靠 timeout 分支:盤中連續 tick 下 timeout 永不觸發(Alt-3)
                await self._maybe_self_heal()

    def request_self_heal(self) -> None:
        """外部(如 TC4 重連後)要求重跑交接補回遺失段;thread-safe。"""
        loop = self._loop
        if loop is None:
            return
        loop.call_soon_threadsafe(setattr, self, "_force_heal", True)

    async def _maybe_self_heal(self) -> None:
        """DR-10:queue 滿載丟過 tick 且壓力解除(queue 清空)→ 重跑交接補回遺失段。

        force(重連後)不等 queue 清空 — 交接期間新 tick 進 buffer,不會遺失(Alt-3)。
        """
        force = self._force_heal
        if force or (self.queue_dropped > self._healed_dropped and self._queue.empty()):
            dropped = self.queue_dropped
            logger.warning("self-heal: re-running handover (dropped=%d, forced=%s)", dropped, force)
            self._force_heal = False
            if self._active is not None and self._agg is not None:
                self._agg.reset(self._active.contracts)
                await self._run_handover(self._active, subscribe=False)
            self._healed_dropped = dropped

    def _mark_changed(self) -> None:
        self._version += 1
        self._changed.set()

    # ---- 測試鉤(僅測試用;凍結消費以模擬 queue 壓力)----

    def pause_consume_for_test(self) -> None:
        self._paused = True

    def resume_consume_for_test(self) -> None:
        self._paused = False
