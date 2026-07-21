"""EngineRuntime:tick queue 消費、交接協定編排、節流 snapshot 流(design.md §4)。"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncGenerator, Callable, Protocol

from copycat.live.aggregate import ChainAggregator
from copycat.live.handover import HandoverBuffer, run_handover
from copycat.live.models import SeriesInfo, Tick
from copycat.live.session import SessionKey, session_key

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
        session_rollover: bool = True,
    ) -> None:
        self._source = source
        self._throttle = throttle_secs
        # TXO_BACKFILL_DATE 固定日回補模式要傳 False:偵測依真實時鐘,固定日模式下
        # 跨界重跑只會拿到同一份指定日資料,純浪費(spec R5)
        self._session_rollover = session_rollover
        self._session_key: SessionKey | None = None
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
        self._handover: dict | None = None
        self._version = 0
        self._changed = asyncio.Event()

    # ---- 對外查詢 ----

    def list_series(self) -> list[SeriesInfo]:
        return list(self._series.values())

    def orderable_symbols(self) -> set[str]:
        """可下單商品全集:active 序列合約(SeriesInfo 全集,非 snapshot 已成交子集)∪ TXF。

        trade 白名單資料驅動(design R5),序列動態發現、不 hardcode 產品碼(CLAUDE.md §8)。
        SPOT_SYMBOL 來自 zmq-free 的 models(review C1:fake-trade 場景不拉 pyzmq)。
        """
        from copycat.live.models import SPOT_SYMBOL

        symbols = {SPOT_SYMBOL}
        if self._active is not None:
            symbols.update(c.symbol for c in self._active.contracts)
        return symbols

    def latest_snapshot(self) -> dict:
        if self._agg is None or self._active is None:
            # totals 必須是 None 而非空 dict:前端以 truthy 判斷有無數據(C-1)
            return {
                "series_id": None,
                "status": self.status,
                "totals": None,
                "curve": [],
                "handover": self._handover,
            }
        snap = self._agg.snapshot(
            series=self._active,
            status=self.status,
            accumulated_from=self._accumulated_from,
            generated_at=time.strftime("%H:%M:%S"),
            queue_dropped=self.queue_dropped,
        )
        snap["handover"] = self._handover
        return snap

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
        # 交接起點即記時段 key:失敗也記(避免 rollover 條件無限重觸發;恢復走
        # on_reconnect 鏈,test_rollover_during_source_down 釘住)
        self._session_key = session_key()
        overflows = 0
        for attempt in range(1, _HANDOVER_RETRIES + 1):
            self._set_status("backfilling")
            self._buffer = HandoverBuffer()
            try:
                if subscribe or attempt > 1:
                    await asyncio.to_thread(self._source.subscribe, series, self.on_tick)
                    subscribe = False
                t0 = time.monotonic()
                backfill = await asyncio.to_thread(self._source.fetch_backfill, series)
            except ConnectionError:
                # 來源 REQ 失敗:孤兒 buffer 必清(否則後續 tick 全被吞、totals 凍結),
                # 狀態誠實降 degraded 後把例外交還呼叫端 — user 路徑(select/start)
                # 由 route 層轉 502(TC4_DOWN 合約);自癒路徑由 _maybe_self_heal 接住。
                self._buffer = None
                self._set_status("degraded")
                raise
            backfill_secs = time.monotonic() - t0
            buffer = self._buffer
            self._buffer = None
            if buffer is not None:
                # 回補逾時預警的觀測欄位(log 之外前端可診斷;next-time 2026-07-20 條 2)
                self._handover = {
                    "backfill_secs": round(backfill_secs, 1),
                    "buffer_used": len(buffer),
                    "buffer_cap": buffer.cap,
                    "buffer_warned": buffer.warned,
                    "overflows": overflows + (1 if buffer.overflowed else 0),
                }
            if buffer is None or buffer.overflowed:
                overflows += 1
                logger.warning(
                    "handover buffer overflow (attempt %d, backfill %.1fs), retrying",
                    attempt,
                    backfill_secs,
                )
                continue
            run_handover(self._agg, backfill, buffer)
            if backfill:
                first = min(t.precise_time for t in backfill)
                self._accumulated_from = _fmt_precise_time(first)
            else:
                # 空回補不得殘留上一次起點(時段 rollover 後會誤顯示舊時段起點)
                self._accumulated_from = "-"
            self._set_status("live")
            return
        self._set_status("degraded")
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
        rollover = (
            self._session_rollover
            and self._active is not None
            and self._session_key is not None
            and session_key() != self._session_key
        )
        if force or rollover or (self.queue_dropped > self._healed_dropped and self._queue.empty()):
            dropped = self.queue_dropped
            logger.warning(
                "self-heal: re-running handover (dropped=%d, forced=%s, rollover=%s)",
                dropped,
                force,
                rollover,
            )
            self._force_heal = False
            if self._active is not None and self._agg is not None:
                self._agg.reset(self._active.contracts)
                try:
                    # rollover 必須重訂閱:REALTIME 以新時段窗重掛(subscribe 冪等
                    # UNSUB→SUB;舊窗訂閱跨 UTC 日後 TC4 是否續推未驗證,spec R1)
                    await self._run_handover(self._active, subscribe=rollover)
                except ConnectionError:
                    # 背景自癒的來源失敗是預期事件(app 死亡期),不可炸出去殺死
                    # _consume task(靜默永久停擺;review F3)。已 degraded,
                    # 待 TC4 重連 on_reconnect 再度 force_heal 自癒。
                    logger.exception("self-heal handover failed (source down)")
            self._healed_dropped = dropped

    def _set_status(self, status: str) -> None:
        """狀態轉換一律經此(賦值 + 廣播喚醒),避免單邊漏 _mark_changed。"""
        self.status = status
        self._mark_changed()

    def _mark_changed(self) -> None:
        self._version += 1
        self._changed.set()

    # ---- 測試鉤(僅測試用;凍結消費以模擬 queue 壓力)----

    def pause_consume_for_test(self) -> None:
        self._paused = True

    def resume_consume_for_test(self) -> None:
        self._paused = False
