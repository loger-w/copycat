"""IndexEngine 測試 — index-board SC-4(design v4)."""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
from typing import Any, Callable

import pytest

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
    # now_fn 釘在窗起點附近:預設 10:00 會讓分時自癒(lag >3 分)同場觸發,retry 成功
    # 的早期廣播搶進 queue 首位 → 首則訊息 stale 斷言 flaky。本測試標的是 watchdog。
    eng = make_engine(
        fake, in_watch_window=lambda: True, stale_secs=0.06, now_fn=lambda: _dt.time(9, 1)
    )
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


async def test_heal_backfill_reaches_connected_clients_via_broadcast() -> None:
    """自癒回補必須送達已連線前端:廣播 payload 平常是 scalar-only(無 minutes),
    heal 後若不帶一次 minutes 全量,前端只有換日/重連才 refetch —— 引擎治好了、
    畫面上的線卻要等使用者重整才回來。retry 成功後下一則廣播帶 minutes 一次,
    之後回到 scalar-only(頻寬慣例不變)。"""
    fake = FakeIndexSource()
    eng = make_engine(fake, in_watch_window=lambda: True, now_fn=lambda: _dt.time(10, 0))
    eng._heal_secs = 0.05  # type: ignore[attr-defined]
    await eng.start()
    try:
        stream = eng.stream()
        fake.day_minutes = {"0901": 1_000}
        deadline = asyncio.get_running_loop().time() + 2.0
        carried: dict | None = None
        while asyncio.get_running_loop().time() < deadline:
            msg = await asyncio.wait_for(stream.__anext__(), timeout=1)
            if "minutes" in msg["twse"]:
                carried = msg["twse"]["minutes"]
                break
        assert carried == {"0901": 1_000}
        # 之後回到 scalar-only:觸發一則 dirty 廣播,不得再帶 minutes
        assert fake.on_message is not None
        fake.on_message(_quote(filled="20000"))  # 02:00 UTC → key 1001,跟上牆鐘不再觸發 heal
        msg = await asyncio.wait_for(stream.__anext__(), timeout=1)
        assert "minutes" not in msg["twse"]
    finally:
        await eng.close()


async def test_pending_retry_does_not_broadcast_minutes() -> None:
    """review T-1(P1):換日 pending 期間排到的連線類 retry 成功,不得帶出 minutes
    全量廣播 —— 此時 `_subscribe_and_backfill` 抓的是新日窗、merge 進舊日 dict,
    廣播 trade_date 仍是舊日 → 前端不走換日分支、整份替換成混日線。"""
    fake = FakeIndexSource()
    fake.subscribe_error = ConnectionError("down")
    eng = make_engine(fake)
    await eng.start()
    try:
        eng._pending_date = "2026-07-29"  # rollover 已偵測新日、source 日窗已切
        fake.subscribe_error = None
        fake.day_minutes = {"0901": 9}  # retry 成功抓回的是「新日」資料
        stream = eng.stream()
        await asyncio.sleep(0.1)
        msg = await asyncio.wait_for(stream.__anext__(), timeout=1)
        assert "minutes" not in msg["twse"]
    finally:
        await eng.close()


async def test_heal_active_in_closing_tail_window() -> None:
    """review T-3:收盤尾窗(13:25–13:40)heal 必須續跑 —— 1K 域到 1330,watchdog
    窗 13:25 凍結的理由(試撮不推成交)對「重抓 1K 回補」不成立,尾段 13:25–13:30
    正是要補的那截。"""
    fake = FakeIndexSource()
    eng = make_engine(fake, in_watch_window=lambda: False, now_fn=lambda: _dt.time(13, 35))
    eng._heal_secs = 0.05  # type: ignore[attr-defined]
    await eng.start()
    try:
        fake.day_minutes = {"1330": 7}
        await asyncio.sleep(0.3)
        assert eng.state()["twse"]["minutes"] == {"1330": 7}
    finally:
        await eng.close()


async def test_heal_backs_off_when_no_progress() -> None:
    """review T-5:1K 持續回空(假日 / 該日資料不可得)→ heal 間隔須倍增退避,
    不得以固定節流整窗空轉(UNSUB→SUB churn + log 噪音)。無退避時 0.8s 內
    約 14 次抓取,退避後應 ≤ 6 次。"""
    fake = FakeIndexSource()  # day_minutes 恆空
    eng = make_engine(fake, in_watch_window=lambda: True)
    eng._heal_secs = 0.05  # type: ignore[attr-defined]
    await eng.start()
    try:
        await asyncio.sleep(0.8)
        assert 2 <= fake.fetch_minutes_calls <= 6
    finally:
        await eng.close()


async def test_heal_no_progress_is_not_claimed_as_success(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SC-1(fix/index-line-vanish):heal 的「成功」判準必須是**產出面**。

    2026-08-14 prod 實錄:heal 觸發 9 次,每次 `fetch_day_minutes` 都快速返回、不拋、
    帶回零有效分鐘(TC4 回窗外 stub),而 `_retry_loop` 以「沒丟例外」當成功 → 設
    `_push_minutes_once`/`_dirty` 宣告治好了、退避倍增,全日缺線且整天零 log。
    無進展的那一發不得帶 minutes 出去,且必須留下可 grep 的 WARNING。"""
    fake = FakeIndexSource()  # day_minutes 恆空 = TC4 回窗外 stub 被濾光後的形狀
    eng = make_engine(fake, in_watch_window=lambda: True, now_fn=lambda: _dt.time(10, 0))
    eng._heal_secs = 0.05  # type: ignore[attr-defined]
    with caplog.at_level(logging.WARNING, logger="copycat.server.index_engine"):
        await eng.start()
        try:
            stream = eng.stream()
            await asyncio.sleep(0.3)
            assert fake.fetch_minutes_calls >= 2  # heal 確實跑過
            with pytest.raises(TimeoutError):  # 無進展 → 不設 dirty → 沒有任何廣播
                await asyncio.wait_for(stream.__anext__(), timeout=0.1)
            assert eng._push_minutes_once is False  # type: ignore[attr-defined]
        finally:
            await eng.close()
    assert "index 分時自癒無進展" in caplog.text


async def test_heal_escalates_window_variant_until_data_returns() -> None:
    """SC-2:無進展的下一發 heal 必須換窗口字串(variant+1)—— 重用同一個
    (session, symbol, 1K, 窗口)訂閱逃不出 TC4 的 stub 態(repro 實證:換窗口或換
    session 才逃得掉)。variant 首次帶回資料 → minutes 恢復,且下一則廣播帶 minutes
    全量一次(#45 的送達行為銜接),退避與 variant 一併歸零。"""
    fake = FakeIndexSource()  # 舊窗口(variant 0)恆空
    fake.variant_minutes = {1: {"0959": 2_000}}  # 換一次窗口就拿得到
    eng = make_engine(fake, in_watch_window=lambda: True, now_fn=lambda: _dt.time(10, 0))
    eng._heal_secs = 0.05  # type: ignore[attr-defined]
    await eng.start()
    try:
        stream = eng.stream()
        msg = await asyncio.wait_for(stream.__anext__(), timeout=2)
        assert msg["twse"]["minutes"] == {"0959": 2_000}  # 全量送達已連線前端
        assert eng.state()["twse"]["minutes"] == {"0959": 2_000}
        # boot=0、首發 heal 沿用 0(無進展)、次發換 1(命中)
        assert fake.window_variants[:3] == [0, 0, 1]
        assert eng._heal_variant == 0  # type: ignore[attr-defined]
        assert eng._heal_interval is None  # type: ignore[attr-defined]
    finally:
        await eng.close()


async def test_heal_throttled_between_attempts() -> None:
    """lock(review T-2):heal 節流是 load-bearing —— 沒有它,推播死時 IX0001 每
    ~retry_secs 被 UNSUB→SUB 一次(重掛正是「訂閱成功零推播」家族的觸發面)。
    預設 _heal_secs=60 下,0.3s 內只允許 start + 首次 heal 兩次抓取。"""
    fake = FakeIndexSource()
    eng = make_engine(fake, in_watch_window=lambda: True)  # _heal_secs 維持預設 60
    await eng.start()
    try:
        await asyncio.sleep(0.3)
        assert fake.fetch_minutes_calls == 2
    finally:
        await eng.close()


async def test_heal_stops_when_day_complete() -> None:
    """lock(review T-3 停止條件):尾窗內 minutes 已覆蓋到 1330 = 完整,不得再觸發
    (牆鐘期望封頂 13:30;沒有封頂的話 13:35 時 lag=5 會空轉重抓)。"""
    fake = FakeIndexSource(day_minutes={"1330": 7})
    eng = make_engine(fake, in_watch_window=lambda: False, now_fn=lambda: _dt.time(13, 35))
    eng._heal_secs = 0.05  # type: ignore[attr-defined]
    await eng.start()
    try:
        await asyncio.sleep(0.2)
        assert fake.fetch_minutes_calls == 1  # 只有 start 那一次
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
