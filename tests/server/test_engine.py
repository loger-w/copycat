from __future__ import annotations

import asyncio
import re
import threading
from contextlib import suppress
from typing import Any, AsyncGenerator, Callable

import pytest

from copycat.live.models import OptionContract, SeriesInfo, Tick
from copycat.server.engine import EngineRuntime, HandoverBusyError, _content

C44000 = OptionContract(symbol="TC.O.TWF.TX4.202607.C.44000", cp="C", strike_millipts=44_000_000)
C45000 = OptionContract(symbol="TC.O.TWF.TX5.202607.C.45000", cp="C", strike_millipts=45_000_000)
SERIES_A = SeriesInfo(
    series_id="TX4.202607", name="TX4 202607", expiry="202607", contracts=(C44000,)
)
SERIES_B = SeriesInfo(
    series_id="TX5.202607", name="TX5 202607", expiry="202607", contracts=(C45000,)
)
TXF = "TC.F.TWF.TXF.HOT"  # 台指期(SPOT_PREFIX);TXO runtime 只拿它更新現價


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


async def test_spot_millipts_public_accessor() -> None:
    """index-board IR1:txf_getter 依賴的 public 現貨價 accessor."""
    fake = FakeQuoteSource()
    rt = EngineRuntime(fake, throttle_secs=0.01)
    assert rt.spot_millipts() is None  # 未就緒
    await rt.start()
    try:
        assert fake.on_tick is not None
        fake.on_tick(tick("TC.F.TWF.TXF.HOT", price=42_142_000, qty=0, t=9))
        await asyncio.sleep(0.05)
        assert rt.spot_millipts() == 42_142_000
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


class TestSessionRollover:
    """時段切換偵測:跨盤界(日↔夜)自動 reset + 重跑交接,新時段從零累積(SC-3)。"""

    def _patch_key(self, monkeypatch: Any) -> dict[str, tuple[str, str]]:
        key = {"v": ("20260720", "day")}
        monkeypatch.setattr("copycat.server.engine.session_key", lambda: key["v"])
        return key

    async def test_key_change_triggers_rehandover_with_resubscribe(self, monkeypatch: Any) -> None:
        key = self._patch_key(monkeypatch)
        fake = FakeQuoteSource(
            backfill={"TX4.202607": [tick(C44000.symbol, price=100_000, qty=3, t=1)]}
        )
        rt = EngineRuntime(fake, throttle_secs=0.01)
        await rt.start()
        try:
            assert fake.subscribed == ["TX4.202607"]
            key["v"] = ("20260720", "night")
            await asyncio.sleep(0.3)
            # 重跑交接 + 重訂閱(REALTIME 以新時段窗重掛;spec R1)
            assert len(fake.backfill_calls) == 2
            assert fake.subscribed == ["TX4.202607", "TX4.202607"]
            snap = rt.latest_snapshot()
            assert snap["status"] == "live"
            # reset 後重灌:累積是重建值不是疊加(3 不是 6)
            assert snap["totals"]["call_net_qty"] == 3
        finally:
            await rt.close()

    async def test_same_key_does_not_rehandover(self, monkeypatch: Any) -> None:
        self._patch_key(monkeypatch)
        fake = FakeQuoteSource()
        rt = EngineRuntime(fake, throttle_secs=0.01)
        await rt.start()
        try:
            await asyncio.sleep(0.3)
            assert len(fake.backfill_calls) == 1
        finally:
            await rt.close()

    async def test_rollover_disabled_ignores_key_change(self, monkeypatch: Any) -> None:
        # TXO_BACKFILL_DATE 固定日模式:app 層以 session_rollover=False 組裝(spec R5)
        key = self._patch_key(monkeypatch)
        fake = FakeQuoteSource()
        rt = EngineRuntime(fake, throttle_secs=0.01, session_rollover=False)
        await rt.start()
        try:
            key["v"] = ("20260720", "night")
            await asyncio.sleep(0.3)
            assert len(fake.backfill_calls) == 1
        finally:
            await rt.close()

    async def test_rollover_during_inflight_handover_serializes(self, monkeypatch: Any) -> None:
        # review F1(repro 實證):交接 to_thread 期間 key 跨界不得並發第二個交接
        # (雙份 backfill 疊加 + buffer 互搶);完成後下一輪 timeout 補跑恰一次。
        import time as _time

        key = self._patch_key(monkeypatch)

        class _Slow(FakeQuoteSource):
            def fetch_backfill(self, series: SeriesInfo) -> list[Tick]:
                _time.sleep(0.15)
                return super().fetch_backfill(series)

        fake = _Slow(backfill={"TX4.202607": [tick(C44000.symbol, price=100_000, qty=3, t=1)]})
        rt = EngineRuntime(fake, throttle_secs=0.01)
        start_task = asyncio.create_task(rt.start())
        await asyncio.sleep(0.05)  # 初始交接進行中
        key["v"] = ("20260720", "night")
        await start_task
        try:
            await asyncio.sleep(0.3)
            assert len(fake.backfill_calls) == 2  # 初始 + 完成後補跑一次,無並發
            assert rt.latest_snapshot()["totals"]["call_net_qty"] == 3  # 單份重建,非疊加
        finally:
            await rt.close()

    async def test_rollover_during_source_down_degrades_then_recovers(
        self, monkeypatch: Any
    ) -> None:
        # rollover 當下 TC4 死亡:degraded 且 _consume 存活,恢復依 on_reconnect 鏈(spec R7-2)
        key = self._patch_key(monkeypatch)

        class _FailToggle(FakeQuoteSource):
            fail = False

            def fetch_backfill(self, series: SeriesInfo) -> list[Tick]:
                if self.fail:
                    raise ConnectionError("tc4 down")
                return super().fetch_backfill(series)

        fake = _FailToggle()
        rt = EngineRuntime(fake, throttle_secs=0.01)
        await rt.start()
        try:
            fake.fail = True
            key["v"] = ("20260720", "night")
            await asyncio.sleep(0.3)
            assert rt.latest_snapshot()["status"] == "degraded"
            fake.fail = False
            rt.request_self_heal()
            await asyncio.sleep(0.3)
            assert rt.latest_snapshot()["status"] == "live"
        finally:
            await rt.close()


async def test_empty_backfill_clears_accumulated_from() -> None:
    # 空回補不得殘留上一次起點(rollover 後顯示舊時段起點會誤導;change-spec R3)
    fake = FakeQuoteSource(
        backfill={"TX4.202607": [tick(C44000.symbol, price=100_000, qty=3, t=1)]}
    )
    rt = EngineRuntime(fake, throttle_secs=0.01)
    await rt.start()
    try:
        assert rt.latest_snapshot()["accumulated_from"] != "-"
        fake.backfill = {}
        await rt.activate("TX4.202607")
        assert rt.latest_snapshot()["accumulated_from"] == "-"
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
    assert snap["handover"] is None  # 交接尚未跑過


class FlakyQuoteSource(FakeQuoteSource):
    """fetch_backfill 依 fail 旗標拋 ConnectionError(模擬 TC4 app 死亡期)。"""

    def __init__(self) -> None:
        super().__init__(backfill={"TX4.202607": [tick(C44000.symbol, price=100_000, qty=3, t=1)]})
        self.fail = False

    def fetch_backfill(self, series: SeriesInfo) -> list[Tick]:
        if self.fail:
            self.backfill_calls.append(series.series_id)
            raise ConnectionError("TC4 quote request failed (simulated)")
        return super().fetch_backfill(series)


async def test_self_heal_source_error_degrades_then_recovers() -> None:
    """review F3:自癒路徑來源拋 ConnectionError 不可殺死 _consume task(靜默永久停擺);

    降 degraded + 清孤兒 buffer,TC4 重連後再度 force_heal 自癒回 live。
    (user 路徑 select/start 維持立即 raise → route 502,見 test_app 502 測試。)
    """
    fake = FlakyQuoteSource()
    rt = EngineRuntime(fake, throttle_secs=0.01)
    await rt.start()
    try:
        assert rt.status == "live"
        fake.fail = True  # app「死亡」
        rt.request_self_heal()
        await asyncio.sleep(0.2)
        assert rt.status == "degraded"
        assert rt._consume_task is not None and not rt._consume_task.done()
        assert rt._buffer is None, "例外路徑孤兒 buffer 未清,後續 tick 會被吞"
        fake.fail = False  # app「回來」→ 重連 callback 觸發自癒
        rt.request_self_heal()
        await asyncio.sleep(0.2)
        assert rt.status == "live"
        assert rt.latest_snapshot()["totals"]["call_net_qty"] == 3
    finally:
        await rt.close()


class _BlockingBackfillSource(FakeQuoteSource):
    """`fetch_backfill` 卡在 gate 上 —— 交接期最長的那個讓出點,cancel 真的穿得過去。"""

    def __init__(self) -> None:
        super().__init__()
        self.gate = threading.Event()
        self.entered = threading.Event()

    def fetch_backfill(self, series: SeriesInfo) -> list[Tick]:
        self.entered.set()
        self.gate.wait(15)
        return super().fetch_backfill(series)


async def test_cancel_during_backfill_clears_orphan_buffer() -> None:
    """cancel 穿過交接時孤兒 buffer 也要清(ConnectionError 那條分支的對稱面)。

    留著的 buffer 會把其後每一則 tick 吞進沒人 flush 的容器裡(totals 靜默凍結)。
    現況 cancel 只來自關機(engine 隨即整個收掉)所以看不到症狀 —— 這條把那個沒寫
    下來的不變式釘成合約,日後新增別的 cancel 來源時不會靜默壞掉。
    """
    fake = _BlockingBackfillSource()
    rt = EngineRuntime(fake, throttle_secs=0.01)
    task = asyncio.create_task(rt.start())
    entered = await asyncio.to_thread(fake.entered.wait, 5)
    assert entered, "boot 沒卡在 fetch_backfill 上,cancel 路徑不會被執行"
    task.cancel()
    fake.gate.set()  # 放行卡住的 executor 執行緒(否則收尾 join 它會掛住)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert rt._buffer is None, "cancel 路徑孤兒 buffer 未清,其後 tick 全被吞"
    await rt.close()


async def test_snapshot_reports_handover_stats() -> None:
    """條 2(next-time 2026-07-20):回補逾時預警的 snapshot 欄位(degraded 時可診斷)。"""
    fake = FakeQuoteSource(
        backfill={"TX4.202607": [tick(C44000.symbol, price=100_000, qty=3, t=1)]}
    )
    rt = EngineRuntime(fake, throttle_secs=0.01)
    await rt.start()
    try:
        h = rt.latest_snapshot()["handover"]
        assert h["buffer_used"] == 0  # fake 交接期無 live tick
        assert h["buffer_cap"] == 200_000
        assert h["buffer_warned"] is False
        assert h["overflows"] == 0
        assert h["backfill_secs"] >= 0.0
    finally:
        await rt.close()


class _GatedOverflowSource(FakeQuoteSource):
    """指定的 attempt 讓交接 buffer 溢出(engine 因此重試),並可在回補中途交握。

    溢出的製造方式是**直接翻 `rt._buffer.overflowed`**(私寫;沿本檔 `rt._handover = …`
    的前例):真溢出要灌滿 20 萬則 tick,而這條測的是「重試期間進度欄有沒有推出去」,
    不是 buffer 自己的計數。

    `gated=True` 時每次進 `fetch_backfill` 先 `entered.set()` 再等 `gate` —— 回補跑在
    `to_thread` 上、event loop 是空的,測試因此能停在「attempt N 已開始、還沒結束」
    的那一刻讀 `latest_snapshot()`。沒有這個交握就只看得到最後一則,而「重試期間畫面
    卡在『回補中』不知第幾次」正是本輪要修的東西。
    """

    def __init__(self, *, overflow_on: set[int], gated: bool = True) -> None:
        super().__init__(backfill={"TX4.202607": [tick(C44000.symbol, price=100_000, qty=3, t=1)]})
        self.overflow_on = overflow_on
        self.gated = gated
        self.rt: EngineRuntime | None = None
        self.attempts = 0
        self.entered = threading.Event()
        self.gate = threading.Event()

    def fetch_backfill(self, series: SeriesInfo) -> list[Tick]:
        self.attempts += 1
        if self.gated:
            self.entered.set()
            self.gate.wait(15)
            self.gate.clear()
        if self.attempts in self.overflow_on:
            rt = self.rt
            assert rt is not None and rt._buffer is not None
            rt._buffer.overflowed = True
        return super().fetch_backfill(series)


async def _await_attempt(fake: _GatedOverflowSource, n: int) -> None:
    """等到第 n 次回補真的進了 `fetch_backfill`(交握點)。"""
    entered = await asyncio.to_thread(fake.entered.wait, 5)
    assert entered, f"attempt {n} 沒進 fetch_backfill"
    assert fake.attempts == n
    fake.entered.clear()  # 先清再放行:worker 下一輪才不會撞到上一輪殘留的旗標


async def _await_push(
    pushed: list[dict], pred: Callable[[dict], bool], *, what: str
) -> dict:
    """輪詢 `pushed` 直到出現符合 `pred` 的那一則(上限 200 × 0.01s = 2s)。

    **不可改回 `await asyncio.sleep(0.05)` 之後直接斷言**:那是在賭「節流 + consumer
    排程 + to_thread 交握」三者的時序,慢機器上偶紅、而且紅的訊息會指向斷言不是時序。
    輪詢的上限是**失敗上限**不是等待時間 —— 正常路徑第一圈就命中。
    """
    for _ in range(200):
        for snap in pushed:
            if pred(snap):
                return snap
        await asyncio.sleep(0.01)
    raise AssertionError(what)


def _handover_of(snap: dict) -> dict:
    return snap.get("handover") or {}


async def test_handover_attempt_progress_visible_during_retries() -> None:
    """SC-1:重試期間 `handover.attempt` / `phase` 要跟著走,且**每 attempt 推一則**。

    08-19 R1 起快照只在內容有變才推,而重試期間唯一會變的就是這幾個欄位 —— 沒有它們
    的話 WS 整段靜默(心跳已解保活),前端 badge 固定「回補中」,使用者分不出「還在
    第一次」與「重試到第三次」。
    """
    fake = _GatedOverflowSource(overflow_on={1})
    rt = EngineRuntime(fake, throttle_secs=0.01)
    fake.rt = rt
    pushed: list[dict] = []

    async def consume() -> None:
        async for snap in rt.snapshots():
            pushed.append(snap)

    consumer = asyncio.create_task(consume())
    task = asyncio.create_task(rt.start())
    try:
        await _await_attempt(fake, 1)
        h = rt.latest_snapshot()["handover"]
        assert h["attempt"] == 1
        assert h["attempts_max"] == 3
        assert h["phase"] == "backfilling"
        await _await_push(
            pushed,
            lambda s: _handover_of(s).get("attempt") == 1
            and _handover_of(s).get("phase") == "backfilling",
            what="attempt 1 的開頭那則從沒被推出去 → 前端看不到第一次",
        )
        fake.gate.set()  # 放行 attempt 1 → buffer 溢出 → 重試

        await _await_attempt(fake, 2)
        h = rt.latest_snapshot()["handover"]
        assert h["attempt"] == 2
        assert h["phase"] == "backfilling"
        # D1'' 的鎖**掛在 attempt 2 的開頭**(review T1):attempt 1 的開頭斷言是同義
        # 反覆 —— 那時根本還沒有任何一輪寫過這五個欄。到這裡 attempt 1 已經寫完
        # (backfill_secs / buffer_used / overflows 都有值),此刻仍不得出現,才真的
        # 證明「不 merge 上一輪」。merge 的失效樣態是上一輪的耗時掛在新一輪的進度上,
        # 畫面看起來完全正常。
        assert "buffer_used" not in h
        assert "backfill_secs" not in h
        assert "overflows" not in h
        assert "buffer_cap" not in h
        assert "buffer_warned" not in h
        # 「推播」這半的鑑別點也在**這一刻**(review T2):attempt 2 還卡在 gate 上,
        # 它的結束那則(phase=live/degraded)根本還沒寫 —— 現在能看到一則
        # `attempt == 2 且 phase == "backfilling"`,就只可能來自重試開頭那次
        # `_mark_changed`。等到跑完再攤平序列的話,末則的 attempt 也是 2,斷言
        # 對「重試期間有沒有推」毫無鑑別力。
        await _await_push(
            pushed,
            lambda s: _handover_of(s).get("attempt") == 2
            and _handover_of(s).get("phase") == "backfilling",
            what="重試那一則沒推 → 畫面停在第 1 次(本輪的病灶)",
        )
        fake.gate.set()
        await task

        h = rt.latest_snapshot()["handover"]
        assert h["attempt"] == 2
        assert h["phase"] == "live"
        assert h["overflows"] == 1  # 既有欄位語意不變(W1)
        assert h["buffer_cap"] == 200_000
        assert rt.status == "live"
    finally:
        consumer.cancel()
        with suppress(asyncio.CancelledError):
            await consumer
        await rt.close()


async def test_handover_degraded_reports_last_attempt_and_phase() -> None:
    """SC-1 降級面:三次全溢出 → `attempt == 3`、`phase == "degraded"`(與 status 同義)。"""
    fake = _GatedOverflowSource(overflow_on={1, 2, 3}, gated=False)
    rt = EngineRuntime(fake, throttle_secs=0.01)
    fake.rt = rt
    await rt.start()
    try:
        assert rt.status == "degraded"
        h = rt.latest_snapshot()["handover"]
        assert h["attempt"] == 3
        assert h["attempts_max"] == 3
        assert h["phase"] == "degraded"
        assert h["overflows"] == 3
    finally:
        await rt.close()


class _BufferEatenSource(FakeQuoteSource):
    """回補期間 buffer 被抽掉(`_run_handover_locked` 的 `buffer is None` 防禦分支)。

    生產上 `_buffer` 只在兩條 except 裡被清成 None,而那兩條都 raise —— 這條分支因此
    在真實流程上不可達,只能用私寫注入。它值得測是因為它是**唯一**一條走到迴圈盡頭
    卻沒寫過 `phase` 的路:`phase` 會停在 `"backfilling"`,而 `status` 已經 `degraded`
    (SC-1「phase 與 status 同義」在此不成立)。
    """

    def __init__(self) -> None:
        super().__init__(backfill={"TX4.202607": [tick(C44000.symbol, price=100_000, qty=3, t=1)]})
        self.rt: EngineRuntime | None = None

    def fetch_backfill(self, series: SeriesInfo) -> list[Tick]:
        rt = self.rt
        assert rt is not None
        rt._buffer = None
        return super().fetch_backfill(series)


async def test_handover_buffer_vanished_still_reports_phase_degraded() -> None:
    """N020:`buffer is None` 走到迴圈盡頭時,`phase` 必須與 `status` 一起降 degraded。"""
    fake = _BufferEatenSource()
    rt = EngineRuntime(fake, throttle_secs=0.01)
    fake.rt = rt
    await rt.start()
    try:
        assert rt.status == "degraded"
        h = rt.latest_snapshot()["handover"]
        assert h["attempt"] == 3
        assert h["attempts_max"] == 3
        assert h["phase"] == "degraded"
    finally:
        await rt.close()


async def test_handover_source_error_marks_phase_degraded() -> None:
    """review C1:來源 REQ 失敗時 `status` 降 degraded,`phase` 不可停在 "backfilling"。

    兩者是同義欄(SC-1:phase = 這一次 attempt 結束後的去向)。分岔的樣態是後端早已
    放棄、badge 卻掛著「回補中(第 n 次)」—— 使用者等一個永遠不會來的完成,而畫面上
    零錯誤訊號。`attempt` 保留:失敗在第幾次仍是診斷資訊。
    """
    fake = FlakyQuoteSource()
    rt = EngineRuntime(fake, throttle_secs=0.01)
    await rt.start()
    try:
        fake.fail = True  # TC4 app「死亡」
        rt.request_self_heal()
        await asyncio.sleep(0.2)
        assert rt.status == "degraded"
        h = rt.latest_snapshot()["handover"]
        assert h["phase"] == "degraded"
        assert h["attempt"] == 1  # 例外從 attempt 1 直接穿出去(不重試)
    finally:
        await rt.close()


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


async def _drain(
    task: "asyncio.Task[dict] | None", agen: AsyncGenerator[dict, None] | None
) -> None:
    """收尾規約:pending 的 task 一律 cancel(取消過的 generator 視為終結、不再迭代);
    只有 task 已完成(或從未起 task)的路徑才 aclose generator。

    已完成但帶例外的 task 一律 re-raise:不撈出來的話真 traceback 只會退化成一則
    「exception was never retrieved」GC 警告,測試看到的失敗訊息會與根因無關。
    """
    if task is not None and not task.done():
        task.cancel()
        with suppress(asyncio.CancelledError, StopAsyncIteration):
            await task
        return
    if task is not None and not task.cancelled():
        exc = task.exception()
        if exc is not None:
            raise exc
    if agen is not None:
        await agen.aclose()


def _count_latest_snapshot(rt: EngineRuntime, monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """把「不變式 (b) 寫錯」從 hang 變成紅。

    `last = self._version` 若晚於內容比對,內容相同那輪會原地打轉;換代 Event 恆為
    set,迴圈裡一個 await 都不剩 → event loop 餓死,連 `asyncio.timeout` 都跑不到,
    測試表現為無限 hang 而非失敗。計數 wrapper 超過門檻就拋,tight loop 因此變成
    「task 帶例外完成」= 可斷言的紅。
    """
    calls = [0]
    orig = rt.latest_snapshot

    def counting() -> dict:
        calls[0] += 1
        if calls[0] > 50:
            raise RuntimeError("snapshots() tight loop")
        return orig()

    monkeypatch.setattr(rt, "latest_snapshot", counting)
    return calls


async def test_snapshots_two_clients_no_lost_wakeup() -> None:
    """SC-3(WS-TXO-SHARED-EVENT):A 在 throttle sleep 期間被 B `clear()` 掉喚醒 → 漏版本。

    以「內容真的會變」的方式 bump(新 cum 的合約 tick),避免與內容比對短路混淆。
    throttle 取 0.5:窗太窄的話高負載下 A 可能早就醒過來自己重讀 Event,測試會假綠。
    """
    fake = FakeQuoteSource()
    rt = EngineRuntime(fake, throttle_secs=0.5)
    await rt.start()
    agen_a = rt.snapshots()
    agen_b = rt.snapshots()
    task_a: asyncio.Task[dict] | None = None
    task_a2: asyncio.Task[dict] | None = None
    task_b: asyncio.Task[dict] | None = None
    try:
        assert fake.on_tick is not None
        task_a = asyncio.ensure_future(agen_a.__anext__())
        await asyncio.sleep(0)  # A 進入 wait()
        fake.on_tick(tick(C44000.symbol, price=100_000, qty=1, cum=1, t=1))
        first_a = await asyncio.wait_for(task_a, timeout=1.0)
        assert first_a["totals"]["call_net_qty"] == 1

        task_a2 = asyncio.ensure_future(agen_a.__anext__())
        await asyncio.sleep(0)  # A 停在 throttle sleep
        task_b = asyncio.ensure_future(agen_b.__anext__())
        await asyncio.sleep(0)  # B 停在 wait()
        assert not task_a2.done()  # A 確實還在 sleep 裡(否則下面驗不到漏喚醒)
        fake.on_tick(tick(C44000.symbol, price=100_000, qty=1, cum=2, t=2))
        snap_b = await asyncio.wait_for(task_b, timeout=1.0)
        assert snap_b["totals"]["call_net_qty"] == 2
        snap_a = await asyncio.wait_for(task_a2, timeout=1.0)
        assert snap_a["totals"]["call_net_qty"] == 2
    finally:
        await _drain(task_a, None)
        await _drain(task_a2, agen_a)
        await _drain(task_b, agen_b)
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


async def test_snapshots_ignores_foreign_and_stale_ticks() -> None:
    """SC-1:外來 symbol 與 stale(cum 未增)tick 不改 snapshot 內容 → 不推播。"""
    fake = FakeQuoteSource()
    rt = EngineRuntime(fake, throttle_secs=0.01)
    await rt.start()
    agen = rt.snapshots()
    task: asyncio.Task[dict] | None = None
    try:
        assert fake.on_tick is not None
        fake.on_tick(tick(C44000.symbol, price=100_000, qty=1, cum=1, t=1))
        first = await asyncio.wait_for(agen.__anext__(), timeout=1.0)
        assert first["totals"]["call_net_qty"] == 1

        task = asyncio.ensure_future(agen.__anext__())
        fake.on_tick(tick("TC.F.TWF.MXF.HOT", price=43_800_000, qty=1, cum=9, t=2))
        fake.on_tick(tick(C44000.symbol, price=100_000, qty=1, cum=1, t=3))  # stale:cum 未增
        await asyncio.sleep(0.3)
        assert not task.done(), task.result()

        fake.on_tick(tick(C44000.symbol, price=100_000, qty=1, cum=2, t=4))
        nxt = await asyncio.wait_for(task, timeout=1.0)
        assert nxt["totals"]["call_net_qty"] == 2
    finally:
        await _drain(task, agen)
        await rt.close()


async def test_snapshots_skips_identical_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """SC-2:version 有變但內容(排除 generated_at)相同 → 不 yield;真變動才推。"""
    fake = FakeQuoteSource()
    rt = EngineRuntime(fake, throttle_secs=0.01)
    await rt.start()
    calls = _count_latest_snapshot(rt, monkeypatch)
    agen = rt.snapshots()
    task: asyncio.Task[dict] | None = None
    try:
        assert fake.on_tick is not None
        fake.on_tick(tick(C44000.symbol, price=100_000, qty=1, cum=1, t=1))
        await asyncio.wait_for(agen.__anext__(), timeout=1.0)  # 建立 prev 基準

        task = asyncio.ensure_future(agen.__anext__())
        rt._mark_changed()
        rt._mark_changed()
        await asyncio.sleep(0.3)  # 正常返回 = 迴圈在 await,不是無 await 的 tight loop
        assert not task.done(), task.result()

        rt._set_status("degraded")
        snap = await asyncio.wait_for(task, timeout=1.0)
        assert snap["status"] == "degraded"
        assert re.fullmatch(r"\d{2}:\d{2}:\d{2}", snap["generated_at"]) is not None
        # 1 首則 + 1 兩次 bare _mark_changed 合併後的比對 + 1 degraded
        assert calls[0] <= 3
    finally:
        await _drain(task, agen)
        await rt.close()


async def test_snapshots_seed_pushes_only_if_changed(monkeypatch: pytest.MonkeyPatch) -> None:
    """SC-3b:seed = 已送出的首則;內容沒動不重推,首則之後發生的變動照推。"""
    fake = FakeQuoteSource()
    rt = EngineRuntime(fake, throttle_secs=0.01)
    await rt.start()
    calls = _count_latest_snapshot(rt, monkeypatch)
    task: asyncio.Task[dict] | None = None
    agen: AsyncGenerator[dict, None] | None = None
    try:
        assert fake.on_tick is not None
        # (a) seed 之後零變動 → 不重推首則
        agen = rt.snapshots(seed=rt.latest_snapshot())
        task = asyncio.ensure_future(agen.__anext__())
        await asyncio.sleep(0.3)
        assert not task.done(), task.result()
        assert calls[0] <= 3  # 1 取 seed + 1 首次迭代的比對
        await _drain(task, agen)
        task = None
        calls[0] = 0  # (b) 是另一組 seed / generator,分開計數

        # (b) 首則送出後、迭代開始前發生的 tick 仍會在首次迭代推出
        seed = rt.latest_snapshot()
        fake.on_tick(tick(C44000.symbol, price=100_000, qty=1, cum=1, t=1))
        await asyncio.sleep(0.05)
        agen = rt.snapshots(seed=seed)
        snap = await asyncio.wait_for(agen.__anext__(), timeout=1.0)
        assert snap["totals"]["call_net_qty"] == 1
        assert calls[0] <= 3  # 1 取 seed + 1 首次迭代的比對
    finally:
        await _drain(task, agen)
        await rt.close()


async def test_snapshots_spot_price_change_pushes_same_price_skips() -> None:
    """W4:spot(台指期)價變 → 推播;同價重送 → 不推。engine 層補 aggregate 層之外的覆蓋。"""
    fake = FakeQuoteSource()
    rt = EngineRuntime(fake, throttle_secs=0.01)
    await rt.start()
    agen = rt.snapshots()
    task: asyncio.Task[dict] | None = None
    try:
        assert fake.on_tick is not None
        fake.on_tick(tick(C44000.symbol, price=100_000, qty=1, cum=1, t=1))
        await asyncio.wait_for(agen.__anext__(), timeout=1.0)  # 建立 prev 基準

        task = asyncio.ensure_future(agen.__anext__())
        fake.on_tick(tick(TXF, price=43_735_460, qty=1, t=2))
        snap = await asyncio.wait_for(task, timeout=1.0)
        assert snap["spot"]["price"] == 43735.46

        task = asyncio.ensure_future(agen.__anext__())
        fake.on_tick(tick(TXF, price=43_735_460, qty=1, t=3))  # 同價重送
        await asyncio.sleep(0.3)
        assert not task.done(), task.result()
    finally:
        await _drain(task, agen)
        await rt.close()


async def test_snapshots_spot_zero_price_skips_and_keeps_last_real() -> None:
    """鎖停市價佇列 0 價 spot:route 回 False → 不 bump version、不推;spot_millipts 留最後真價。"""
    fake = FakeQuoteSource()
    rt = EngineRuntime(fake, throttle_secs=0.01)
    await rt.start()
    agen = rt.snapshots()
    task: asyncio.Task[dict] | None = None
    try:
        assert fake.on_tick is not None
        fake.on_tick(tick(C44000.symbol, price=100_000, qty=1, cum=1, t=1))
        await asyncio.wait_for(agen.__anext__(), timeout=1.0)

        task = asyncio.ensure_future(agen.__anext__())
        fake.on_tick(tick(TXF, price=43_735_460, qty=1, t=2))
        snap = await asyncio.wait_for(task, timeout=1.0)
        assert snap["spot"]["price"] == 43735.46

        task = asyncio.ensure_future(agen.__anext__())
        fake.on_tick(tick(TXF, price=0, qty=0, t=3))  # 鎖停市價佇列
        await asyncio.sleep(0.3)
        assert not task.done(), task.result()
        assert rt.spot_millipts() == 43_735_460
    finally:
        await _drain(task, agen)
        await rt.close()


async def test_content_compare_covers_whole_payload() -> None:
    """SC-2 / W8:內容比對範圍 = 整個 payload 減 `generated_at`,不得再縮。

    縮比對範圍 = 改契約:`test_ws_disconnect` 的 `batches >= 3` 全靠 `totals.ticks` /
    per-contract volume 每筆都動,少比一個鍵就會靜默丟掉推播(零錯誤訊號)。
    """
    fake = FakeQuoteSource()
    rt = EngineRuntime(fake, throttle_secs=0.01)
    await rt.start()
    try:
        assert fake.on_tick is not None
        fake.on_tick(tick(C44000.symbol, price=100_000, qty=1, cum=1, t=1))
        await asyncio.sleep(0.05)
        snap = rt.latest_snapshot()
        assert "generated_at" in snap
        assert set(_content(snap)) == set(snap) - {"generated_at"}
    finally:
        await rt.close()


async def test_snapshots_handover_in_place_key_change_pushes() -> None:
    """C1:`handover` 若與 `_handover` 同物件,就地改鍵會讓 prev 同步變動 → 永不推播。"""
    fake = FakeQuoteSource()
    rt = EngineRuntime(fake, throttle_secs=0.01)
    await rt.start()
    agen = rt.snapshots()
    task: asyncio.Task[dict] | None = None
    try:
        assert fake.on_tick is not None
        handover: dict = {"phase": "idle"}
        rt._handover = handover
        fake.on_tick(tick(C44000.symbol, price=100_000, qty=1, cum=1, t=1))
        first = await asyncio.wait_for(agen.__anext__(), timeout=1.0)
        assert first["handover"] == {"phase": "idle"}

        task = asyncio.ensure_future(agen.__anext__())
        handover["phase"] = "backfilling"  # 就地改鍵(不整體重新賦值)
        rt._mark_changed()
        snap = await asyncio.wait_for(task, timeout=1.0)
        assert snap["handover"] == {"phase": "backfilling"}
    finally:
        await _drain(task, agen)
        await rt.close()


class _BlockingUnsubSource(FakeQuoteSource):
    """`unsubscribe` 卡住 —— 那是 `activate` 在設交接旗標**之前**的讓出點。

    只查 `_handover_running` 擋不住相鄰兩個 select:A 停在這裡時旗標還沒設起,
    B 照樣一路通過 → 兩個交接共用 `_buffer`。互斥必須涵蓋整個 `activate`。
    """

    def __init__(self) -> None:
        super().__init__()
        self.gate = threading.Event()
        self.entered = threading.Event()

    def unsubscribe(self, series: SeriesInfo) -> None:
        self.entered.set()
        self.gate.wait(15)
        super().unsubscribe(series)


async def test_activate_while_handover_running_raises_busy() -> None:
    """交接進行中(rollover / 自癒 / 初始交接皆可能)的 activate 一律拒絕。"""
    fake = FakeQuoteSource()
    rt = EngineRuntime(fake, throttle_secs=0.01)
    await rt.start()
    try:
        rt._handover_running = True
        with pytest.raises(HandoverBusyError):
            await rt.activate("TX5.202607")
        assert fake.unsubscribed == [], "busy 時不得動到訂閱狀態(必須在 mutation 之前擋)"
    finally:
        rt._handover_running = False
        await rt.close()


async def test_concurrent_activate_second_raises_busy() -> None:
    fake = _BlockingUnsubSource()
    rt = EngineRuntime(fake, throttle_secs=0.01)
    await rt.start()  # 啟動即 activate A(_active 為 None → 不走 unsubscribe)
    try:
        first = asyncio.ensure_future(rt.activate("TX5.202607"))
        for _ in range(1_000):
            if fake.entered.is_set():
                break
            await asyncio.sleep(0.005)
        assert fake.entered.is_set(), "第一個 activate 沒停在 unsubscribe 的讓出點"

        with pytest.raises(HandoverBusyError):
            await rt.activate("TX5.202607")

        fake.gate.set()
        await asyncio.wait_for(first, timeout=5)
    finally:
        fake.gate.set()
        await rt.close()



class TestWindowIdentRollover:
    """L77:rollover 判準改比 window identity(預設 = session_key,行為逐字不變);
    app 層在 TXO 自動日模式組 (session_key, auto_date) —— 盤前固定日 → 開盤 live 窗
    的切換(08:45)也要觸發交接,否則前一交易日種子與開盤 live tick 混同一份 agg。"""

    async def test_ident_change_triggers_rehandover_without_session_key_change(self) -> None:
        ident: dict[str, tuple[tuple[str, str], str | None]] = {
            "v": (("20260817", "day"), "20260814")
        }  # (session_key, 自動日)
        fake = FakeQuoteSource()
        rt = EngineRuntime(fake, throttle_secs=0.01, window_ident_fn=lambda: ident["v"])
        await rt.start()
        try:
            assert len(fake.backfill_calls) == 1
            ident["v"] = (("20260817", "day"), None)  # 08:45 開盤:自動日 → live 窗
            await asyncio.sleep(0.3)
            assert len(fake.backfill_calls) == 2  # ident 變化觸發重交接
        finally:
            await rt.close()

    async def test_ident_constant_does_not_rehandover(self) -> None:
        fake = FakeQuoteSource()
        rt = EngineRuntime(fake, throttle_secs=0.01, window_ident_fn=lambda: (("k",), "20260814"))
        await rt.start()
        try:
            await asyncio.sleep(0.3)
            assert len(fake.backfill_calls) == 1
        finally:
            await rt.close()
