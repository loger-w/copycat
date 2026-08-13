"""IndexEngine 測試 — index-board SC-4(design v4)."""

from __future__ import annotations

import asyncio
import datetime as _dt
from typing import Any, Callable

from copycat.server.index_engine import IndexEngine, minute_key
from copycat.server.mis import OtcSnap
from tests.helpers.fake_sources import FakeIndexSource


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
    now_fn: Any = None,
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
        # 換日 08:30 門檻的時鐘也必須注入:預設固定 10:00(門檻後),否則整份測試
        # 只在真實牆鐘 ≥ 08:30 才綠(00:2x 跑 5/5 紅、09:5x 跑 6/6 綠,2026-07-30 實測)
        now_fn=now_fn or (lambda: _dt.time(10, 0)),
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
    eng = make_engine(fake, in_watch_window=lambda: True, stale_secs=0.06)
    await eng.start()
    try:
        stream = eng.stream()
        await asyncio.sleep(0.15)
        assert eng.state()["twse"]["stale"] is True
        msg = await asyncio.wait_for(stream.__anext__(), timeout=1)
        assert msg["twse"]["stale"] is True  # IR7:停止推播仍廣播
        assert fake.on_message is not None
        fake.on_message(_quote())
        # push 後在 stale_secs 內查驗(真實世界推播連續;等太久 watchdog 會再標)
        await asyncio.sleep(0.03)
        assert eng.state()["twse"]["stale"] is False
    finally:
        await eng.close()


class TestWatchWindowBoundaries:
    """lock:watchdog 窗界(09:00–13:25 end-exclusive;design F4/IR10)."""

    def test_boundaries(self) -> None:
        from copycat.server.index_engine import in_watch_window_now

        assert in_watch_window_now(_dt.time(8, 59)) is False
        assert in_watch_window_now(_dt.time(9, 0)) is True
        assert in_watch_window_now(_dt.time(13, 24)) is True
        assert in_watch_window_now(_dt.time(13, 25)) is False  # 試撮窗起點即凍結
        assert in_watch_window_now(_dt.time(13, 26)) is False


async def test_schedule_retry_single_flight() -> None:
    """lock:重複 _schedule_retry 取消舊 task(design F2/IR8)."""
    fake = FakeIndexSource()
    fake.subscribe_error = ConnectionError("down")
    eng = make_engine(fake, retry_secs=10.0)  # 長 backoff:task 存活期間再排一次
    await eng.start()
    try:
        first = eng._retry_task  # type: ignore[attr-defined]
        assert first is not None and not first.done()
        eng._schedule_retry()  # type: ignore[attr-defined]
        second = eng._retry_task  # type: ignore[attr-defined]
        await asyncio.sleep(0)
        assert first.cancelled()
        assert second is not None and second is not first and not second.done()
    finally:
        await eng.close()


async def test_minutes_lag_self_heal_refetches_backfill() -> None:
    """分時自癒(fix/index-chart-empty-minutes):開機 1K 回補 timeout 被靜默降級成空
    + 當日推播整段靜默(TC4 已知間歇失效)→ minutes 全日空白,而 TC4 端 1K 資料
    整天可取(2026-08-13 事故實錄)。watch window 內 minutes 落後牆鐘超過門檻,
    引擎必須自己重掛訂閱 + 重抓 1K,不能等使用者重啟。"""
    fake = FakeIndexSource()  # day_minutes 空 = timeout 靜默回空(不 raise)
    eng = make_engine(fake, in_watch_window=lambda: True, now_fn=lambda: _dt.time(10, 0))
    eng._heal_secs = 0.05  # type: ignore[attr-defined]
    await eng.start()
    try:
        fake.day_minutes = {"0901": 1_000, "0959": 2_000}  # TC4 端其實有資料
        await asyncio.sleep(0.3)
        state = eng.state()
        assert state["twse"]["minutes"] == {"0901": 1_000, "0959": 2_000}
        assert fake.subscribed.count("IX0001") >= 2  # 重掛 = 順帶重武裝死掉的推播訂閱
    finally:
        await eng.close()


async def test_minutes_lag_heal_not_triggered_when_current() -> None:
    """推播健康(minutes 跟上牆鐘)→ 自癒不得空轉重抓(fetch 只有 start 那一次)。"""
    fake = FakeIndexSource()
    eng = make_engine(fake, in_watch_window=lambda: True, now_fn=lambda: _dt.time(9, 30))
    eng._heal_secs = 0.05  # type: ignore[attr-defined]
    await eng.start()
    try:
        assert fake.on_message is not None
        fake.on_message(_quote(filled="13005"))  # 01:30:05 UTC → key 0931(跟上 09:30)
        await asyncio.sleep(0.2)
        assert fake.fetch_minutes_calls == 1
        assert fake.subscribed.count("IX0001") == 1
    finally:
        await eng.close()


async def test_minutes_lag_heal_grace_at_open() -> None:
    """開盤頭幾分鐘 minutes 空是正常(域 0901 起):09:02 不觸發、09:04 越門檻觸發。"""
    fake = FakeIndexSource()
    clock = [_dt.time(9, 2)]
    eng = make_engine(fake, in_watch_window=lambda: True, now_fn=lambda: clock[0])
    eng._heal_secs = 0.05  # type: ignore[attr-defined]
    await eng.start()
    try:
        await asyncio.sleep(0.15)
        assert fake.fetch_minutes_calls == 1  # 09:02 − 09:00 = 2 ≤ 門檻,不觸發
        clock[0] = _dt.time(9, 4)
        await asyncio.sleep(0.15)
        assert fake.fetch_minutes_calls >= 2  # 4 分 > 門檻 → 自癒重抓
    finally:
        await eng.close()


async def test_minutes_lag_heal_does_not_clear_stale() -> None:
    """自癒回補成功不清 stale —— stale 是推播死活訊號(watchdog 職權),
    回補成功不代表推播活著;連線類 retry 的樂觀清 stale 語意不變。"""
    fake = FakeIndexSource()
    eng = make_engine(fake, in_watch_window=lambda: True, stale_secs=0.03)
    eng._heal_secs = 0.02  # type: ignore[attr-defined]
    await eng.start()
    try:
        fake.day_minutes = {"0901": 1_000}
        await asyncio.sleep(0.25)
        state = eng.state()
        assert state["twse"]["minutes"] == {"0901": 1_000}  # 自癒有跑
        assert state["twse"]["stale"] is True  # 但 stale 不被洗掉
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


async def test_rollover_gate_opens_at_0830() -> None:
    """08:30 門檻:門檻前即使日期已跨也不換日,到門檻才換。

    門檻本身原本無測試覆蓋(唯一的時鐘讀取沒有注入點),補上。
    """
    fake = FakeIndexSource()
    fake.day_minutes = {"0901": 1_000}
    clock = [_dt.time(8, 29)]
    eng = make_engine(
        fake,
        rollover=True,
        today_fn=lambda: _dt.date(2026, 7, 29),
        now_fn=lambda: clock[0],
    )
    eng._rollover_check_secs = 0.03  # type: ignore[attr-defined]
    await eng.start()
    try:
        await asyncio.sleep(0.15)
        assert eng.state()["trade_date"] == "2026-07-28"  # 門檻前不動
        assert fake.trade_dates == ["2026-07-28"]  # 只有 start 同步那次
        clock[0] = _dt.time(8, 30)  # 門檻含界(now < 08:30 才擋)
        await asyncio.sleep(0.15)
        assert eng.state()["trade_date"] == "2026-07-29"
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


class TestOtcSynthBars:
    """櫃買當日分 bar 由 5 秒 MIS 快照合成(index-board N-4 / SC-6)。

    TC4 沒有櫃買指數 symbol(CLAUDE.md §8 掃盡確認)→ 這是唯一可能的分 K 來源,
    也因此必須誠實標成 `mis_poll_synth` 且不畫量。
    """

    def _engine(self) -> IndexEngine:
        return IndexEngine(
            FakeIndexSource(),
            txf_getter=lambda: None,
            mis_fetch=lambda: None,
            trade_date="2026-07-30",
            rollover=False,
        )

    def _snap(self, p: int, time: str) -> OtcSnap:
        return OtcSnap(p=p, ref=378_090, open=0, high=0, low=0, time=time)

    def test_ohlc_from_samples_within_minute(self) -> None:
        eng = self._engine()
        for p, t in [(100, "101601"), (130, "101606"), (90, "101611"), (110, "101656")]:
            eng._apply_otc(self._snap(p, t))
        bars, since = eng.otc_bars()
        assert len(bars) == 1
        assert (bars[0]["o"], bars[0]["h"], bars[0]["l"], bars[0]["c"]) == (100, 130, 90, 110)
        assert bars[0]["v"] == 0  # MIS 無量欄位 → 由 meta.volume=False 標明,不畫 0 柱
        assert since == "10:17"

    def test_t_is_date_space_hhmm(self) -> None:
        """前端 candle.ts:splitStamp 靠**有無空格**判斷日 K / 分 K —— 格式錯了
        30/60/90 分完全不聚合,而畫面看起來仍是正常 K 線圖(review P1-9)。"""
        eng = self._engine()
        eng._apply_otc(self._snap(100, "090030"))
        bars, _ = eng.otc_bars()
        assert bars[0]["t"] == "2026-07-30 09:01"

    def test_minutes_are_sorted(self) -> None:
        eng = self._engine()
        for p, t in [(3, "110000"), (1, "090100"), (2, "100000")]:
            eng._apply_otc(self._snap(p, t))
        bars, _ = eng.otc_bars()
        assert [b["c"] for b in bars] == [1, 2, 3]

    def test_empty_before_any_snapshot(self) -> None:
        assert self._engine().otc_bars() == ([], None)

    def test_rollover_clears_synth_bars(self) -> None:
        """換日必清:否則昨日的合成分 bar 會混進新交易日(review P1-9)。"""
        eng = self._engine()
        eng._apply_otc(self._snap(100, "101601"))
        eng._pending_date = "2026-07-31"
        eng._swap_day(backfill={})
        assert eng.otc_bars() == ([], None)

    def test_pending_day_snapshots_do_not_leak_into_bars(self) -> None:
        """偵測到新交易日後、swap 前的快照不得進當日桶(沿用 _apply_otc 既有守衛)。"""
        eng = self._engine()
        eng._pending_date = "2026-07-31"
        eng._apply_otc(self._snap(100, "101601"))
        assert eng.otc_bars() == ([], None)
