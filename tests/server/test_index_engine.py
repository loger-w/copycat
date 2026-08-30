"""IndexEngine 測試 — index-board SC-4(design v4)."""

from __future__ import annotations

import asyncio
import datetime as _dt
import threading
import logging
from typing import Any, Callable

import pytest

from copycat.live.stock_source import in_index_heal_window_now
from copycat.server.index_engine import _WATCH_END, IndexEngine, minute_key
from copycat.server.mis import OtcSnap
from tests.helpers.fake_sources import FakeIndexSource
from tests.helpers.wait import wait_until


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
    is_trading_day: Any = None,
    stale_secs: float = 999.0,
    retry_secs: float = 0.01,
) -> IndexEngine:
    extra = {} if is_trading_day is None else {"is_trading_day": is_trading_day}
    return IndexEngine(
        fake,  # type: ignore[arg-type]
        txf_getter=txf_getter,
        mis_fetch=mis_fetch,
        trade_date=trade_date,
        rollover=rollover,
        **extra,
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


async def test_reconnect_retry_keeps_the_heal_variant() -> None:
    """review §3.4(A6):`_on_reconnect_threadsafe` 原本走 `_schedule_retry()` 預設 —— variant 0。
    盤後分時自癒已把窗口階梯爬到 N(0..N-1 已證明毒化,L1-P1-3「variant 黏在成功值」)時,
    TC4 重連(`_check_stale`)那一發用 0 號窗重抓 → 拿回凍結 stub、`clear_stale=True` 卻把
    stale 樂觀清掉,`_heal_variant` / `_heal_interval` 不動 → 下次自癒最遠等 900 s;畫面 =
    徽章健康、加權分時凍結。重連的那一發要沿用當前 variant。"""
    fake = FakeIndexSource()
    fake.variant_minutes = {2: {"0959": 2_000}}  # 0 / 1 號窗恆空(毒化),2 號窗才有資料
    eng = make_engine(fake)
    await eng.start()
    try:
        assert fake.window_variants == [0]
        eng._heal_variant = 2  # type: ignore[attr-defined]  # 自癒已爬到 2
        eng._on_reconnect_threadsafe()  # type: ignore[attr-defined]
        await wait_until(
            lambda: len(fake.window_variants) >= 2 and bool(eng.state()["twse"]["minutes"])
        )
        assert fake.window_variants[-1] == 2, f"重連重抓退回 0 號毒窗:{fake.window_variants}"
        assert eng.state()["twse"]["minutes"] == {"0959": 2_000}
        assert eng._heal_variant == 2  # type: ignore[attr-defined]  # 仍黏住
    finally:
        await eng.close()


async def test_reconnect_retry_without_progress_advances_the_variant(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """review A6 round-1 SP1:重連那一發沿用 variant N,但新 session 的 N 號窗也可能是凍結 stub ——
    `clear_stale=True` 分支原本不判進展,拿回 stub 照樣 `stale=False`、variant 不動,下一發自癒
    又用 N 號窗。**只在 variant > 0(重連時本就在自癒中)** 且零新鍵時 bump:boot / rollover 的
    variant 0 路徑不動(盤外重抓「零新鍵」是資料已完整,不是毒化,不能當失敗)。
    stale 語意維持樂觀清(推播死活由 watchdog 判)。"""
    fake = FakeIndexSource()  # 所有窗口恆空
    eng = make_engine(fake)
    await eng.start()
    try:
        eng._heal_variant = 2  # type: ignore[attr-defined]
        with caplog.at_level(logging.WARNING):
            eng._on_reconnect_threadsafe()  # type: ignore[attr-defined]
            await wait_until(lambda: eng._heal_variant == 3)  # type: ignore[attr-defined]
        assert fake.window_variants[-1] == 2
        assert "index 重連重抓無進展" in caplog.text
        assert eng.state()["twse"]["stale"] is False  # 既有語意:重連成功仍樂觀清
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
    之後回到 scalar-only(頻寬慣例不變)。

    治具的 minutes 必須真的**追上牆鐘**(fix/index-line-vanish 起,heal 的成功判準是
    產出面):只回一根 0901 而牆鐘 10:00 是「無進展」,那條路徑刻意不帶 minutes 出去。"""
    fake = FakeIndexSource()
    eng = make_engine(fake, in_watch_window=lambda: True, now_fn=lambda: _dt.time(10, 0))
    eng._heal_secs = 0.05  # type: ignore[attr-defined]
    await eng.start()
    try:
        stream = eng.stream()
        fake.day_minutes = {"0901": 1_000, "0959": 2_000}
        deadline = asyncio.get_running_loop().time() + 2.0
        carried: dict | None = None
        while asyncio.get_running_loop().time() < deadline:
            msg = await asyncio.wait_for(stream.__anext__(), timeout=1)
            if "minutes" in msg["twse"]:
                carried = msg["twse"]["minutes"]
                break
        assert carried == {"0901": 1_000, "0959": 2_000}
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


async def test_heal_runs_after_hours_on_a_trading_day() -> None:
    """N105:盤後 / 晚間啟動踩 1K timeout,當晚就要自癒 —— 不是等到次日 09:06。

    改動前 heal 窗上界是 13:40(`_HEAL_TAIL_END`),20:00 起的 server 整晚不重抓,
    而 `_minutes_lag_exceeded` 的 `min(now, 13:30)` 封頂本來就已經表達了「窗外以
    13:30 為期望覆蓋終點」—— 缺的只是讓 gate 開著。**放寬只在有日曆時生效**(SP1)。
    """
    fake = FakeIndexSource()  # day_minutes 空 = 回補 timeout 靜默降級成空
    eng = make_engine(
        fake,
        in_watch_window=lambda: False,
        now_fn=lambda: _dt.time(20, 0),
        is_trading_day=lambda _d: True,
    )
    eng._heal_secs = 0.05  # type: ignore[attr-defined]
    await eng.start()
    try:
        fake.day_minutes = {"0901": 1_000, "1330": 2_000}  # TC4 端其實整天都取得到
        await asyncio.sleep(0.3)
        assert eng.state()["twse"]["minutes"] == {"0901": 1_000, "1330": 2_000}
    finally:
        await eng.close()


async def test_heal_after_hours_falls_back_to_the_old_window_without_a_calendar() -> None:
    """SP1(a):**沒有日曆**時盤外放寬必須退回舊行為,不得退成「恆真」。

    `is_trading_day=None` 在 engine 內是 `lambda _d: True`(W9 的既有預設),拿它
    當交易日閘等於閘恆開 —— 配上放寬到午夜的窗,休市日的噪音比改動前**更大**
    (改動前至少 13:40 就收工)。沒有日曆時唯一誠實的答案是「不知道今天開不開盤」,
    而不知道就不該放寬。
    """
    fake = FakeIndexSource()  # is_trading_day 不傳 = 無日曆
    eng = make_engine(fake, in_watch_window=lambda: False, now_fn=lambda: _dt.time(20, 0))
    eng._heal_secs = 0.01  # type: ignore[attr-defined]
    await eng.start()
    try:
        fake.day_minutes = {"0901": 1_000, "1330": 2_000}
        await asyncio.sleep(0.3)
        assert fake.fetch_minutes_calls == 1, "無日曆 → 盤外一發 heal 都不許出"
        assert eng.state()["twse"]["minutes"] == {}
    finally:
        await eng.close()


async def test_heal_inside_watch_window_skips_a_calendar_holiday() -> None:
    """N105 補窗內閘(2026-08-28 user 拍板 A5「休市日就不要抓」;事前標該變:原
    `test_heal_inside_watch_window_ignores_the_calendar` 釘的是相反行為)。

    休市日 minutes 恆空 → 窗內 09:04–13:25 每 60 s→900 s 空打 TC4,抓回來永遠是空的。
    有日曆且日曆說休市 → 窗內一發都不打。代價 = 日曆誤標交易日為休市那天整天不自癒,
    但那天整個畫面都掛休市膠囊、圖是前一日的,錯得看得見(user 08-28 知情接受)。
    """
    fake = FakeIndexSource()
    market_open = {"v": False}  # 日曆說今天休市;後段翻成交易日當對照組
    eng = make_engine(
        fake,
        in_watch_window=lambda: True,
        now_fn=lambda: _dt.time(10, 0),
        is_trading_day=lambda _d: market_open["v"],
    )
    eng._heal_secs = 0.01  # type: ignore[attr-defined]
    await eng.start()
    try:
        fake.day_minutes = {"0901": 1_000, "0959": 2_000}
        await asyncio.sleep(0.3)
        # boot 那一發回補仍照打(start 不受 heal 閘管);之後窗內零 heal
        assert fake.fetch_minutes_calls == 1, "有日曆的休市日 → 窗內一發 heal 都不許出"
        assert eng.state()["twse"]["minutes"] == {}
        # 對照組(否定型斷言的活性證明,`tests/helpers/wait.py` 檔頭紀律):日曆翻成交易日,
        # 同一顆 engine、同一個迴圈立刻救 —— 證明閘是唯一擋人的東西、迴圈一直活著
        market_open["v"] = True
        await wait_until(lambda: fake.fetch_minutes_calls == 2)
        await wait_until(lambda: eng.state()["twse"]["minutes"] == {"0901": 1_000, "0959": 2_000})
    finally:
        await eng.close()


async def test_heal_inside_watch_window_without_a_calendar_still_heals() -> None:
    """窗內閘只在**有日曆**時生效:無日曆 = 不知道今天開不開盤,窗內逐字沿用舊判準照救
    (與盤外「無日曆退回舊尾窗」同一個原則:不知道就不改行為)。
    """
    fake = FakeIndexSource()  # is_trading_day 不傳 = 無日曆
    eng = make_engine(fake, in_watch_window=lambda: True, now_fn=lambda: _dt.time(10, 0))
    eng._heal_secs = 0.01  # type: ignore[attr-defined]
    await eng.start()
    try:
        fake.day_minutes = {"0901": 1_000, "0959": 2_000}
        await wait_until(lambda: eng.state()["twse"]["minutes"] == {"0901": 1_000, "0959": 2_000})
    finally:
        await eng.close()


async def test_rollover_pending_cancels_the_inflight_retry() -> None:
    """review 08-25 §2.5 Spec 2(A5 第二部分):heal / 連線 retry 若在 rollover `set_trade_date`
    **之前**起跑、之後返回,抓的是**舊日**整天分鐘,卻因 `_pending_date` 已設而落進
    `_pending_backfill`,swap 時當最低層疊進新日 → 舊日 09:00–13:30 整段留在新日線上直到逐分
    被覆寫。rollover 設 pending 那一刻要讓在飛的 retry 作廢:世代 +1(executor 內未起跑的
    工作項早退)+ cancel(已 await 的那發走不到合併點,N094)。
    """
    fake = FakeIndexSource()
    fake.day_minutes = {}  # rollover 抓不到新日 1K → 不 swap,pending 留著可觀察
    eng = make_engine(
        fake,
        rollover=True,
        trade_date="2026-08-13",
        today_fn=lambda: _dt.date(2026, 8, 14),  # 週五
        is_trading_day=lambda d: d.weekday() < 5,
    )
    eng._rollover_check_secs = 0.005  # type: ignore[attr-defined]
    await eng.start()
    inflight = asyncio.create_task(asyncio.sleep(10))  # 模擬 rollover 前已在 await 的 retry
    eng._retry_task = inflight  # type: ignore[attr-defined]
    epoch_before = eng._retry_epoch  # type: ignore[attr-defined]
    try:
        await wait_until(lambda: eng._pending_date == "2026-08-14")  # type: ignore[attr-defined]
        assert eng._retry_epoch > epoch_before, "設 pending 必須 bump 世代"  # type: ignore[attr-defined]
        await wait_until(inflight.cancelled)
    finally:
        if not inflight.done():
            inflight.cancel()
        await eng.close()


async def test_rollover_keeps_old_day_backfill_out_of_pending() -> None:
    """同一條的**結果面**(review Spec P2-3):真的 `_retry_loop` 在 rollover 前起跑、fetch 卡在
    worker thread 上、rollover 後才返回 —— 它抓的是舊日整天分鐘,一格都不得落進
    `_pending_backfill`(否則 swap 時當最低層疊進新日線)。改動前:merge 照做,
    `_pending_backfill == {"0901": 1_000, "1330": 2_000}`。
    """
    fake = FakeIndexSource()
    eng = make_engine(
        fake,
        rollover=True,
        trade_date="2026-08-13",
        today_fn=lambda: _dt.date(2026, 8, 14),  # 週五
        is_trading_day=lambda d: d.weekday() < 5,
        retry_secs=0.01,
    )
    eng._rollover_check_secs = 0.02  # type: ignore[attr-defined]
    await eng.start()
    gate = threading.Event()
    try:
        fake.day_minutes = {"0901": 1_000, "1330": 2_000}  # 舊日整天分鐘
        fake.fetch_gate = gate  # 下一次 fetch = 在飛 retry 的那一次,卡住
        eng._schedule_retry(clear_stale=False)  # type: ignore[attr-defined]  # 盤外分時自癒那一發
        await wait_until(lambda: fake.fetch_minutes_calls == 2)  # retry 已進 fetch、卡在閘上
        fake.day_minutes = {}  # rollover 自己那趟回補抓空 → 不 swap,pending 留著可觀察
        await wait_until(lambda: eng._pending_date == "2026-08-14")  # type: ignore[attr-defined]
        gate.set()  # 在飛的 retry 現在才返回
        # 等那發 retry 真的收場(被 cancel → done;沒被 cancel → merge 後 return → 也 done),
        # 再看結果 —— 固定 sleep 會在 worker 還沒返回時假綠(本測試第一版就是這樣)
        await wait_until(lambda: eng._retry_task is not None and eng._retry_task.done())  # type: ignore[attr-defined]
        assert eng._pending_backfill == {}, "舊日窗起跑的回補不得疊進新日"  # type: ignore[attr-defined]
        assert eng.state()["twse"]["minutes"] == {}  # 舊日 dict 也沒被寫(retry 沒走到合併)
    finally:
        gate.set()
        await eng.close()


async def test_heal_never_runs_after_hours_on_a_non_trading_day() -> None:
    """N105 條文明寫的另一半:休市日 minutes 恆空 → 放寬後的盤外段會從 13:25 一路
    空打到午夜。交易日閘讓**盤外**一發都不打(窗內另有 SP1(b) 的界)。"""
    fake = FakeIndexSource()
    eng = make_engine(
        fake,
        in_watch_window=lambda: False,
        now_fn=lambda: _dt.time(20, 0),
        is_trading_day=lambda _d: False,
    )
    eng._heal_secs = 0.01  # type: ignore[attr-defined]
    await eng.start()
    try:
        fake.day_minutes = {"0901": 1_000, "0959": 2_000}
        await asyncio.sleep(0.3)
        # boot 那一發回補仍照打(start 不受 heal 閘管);之後零 heal
        assert fake.fetch_minutes_calls == 1
        assert eng.state()["twse"]["minutes"] == {}
    finally:
        await eng.close()


async def test_pending_retry_keeps_new_day_minutes_out_of_state() -> None:
    """N107:pending 期間的連線類 retry 抓的是**新日**窗,不得 merge 進舊日 dict。

    T-1 已擋住廣播面;`state()` 這一面沒擋 —— swap 前(≤60s)重整頁面就會拿到混日
    minutes(舊日 trade_date + 新舊混在一起的分鐘),畫面上是一條短暫的混日線。
    """
    fake = FakeIndexSource()
    fake.subscribe_error = ConnectionError("down")
    eng = make_engine(fake)
    await eng.start()
    try:
        eng._twse.minutes = {"0901": 1}  # type: ignore[attr-defined]  # 舊日既有分鐘
        eng._pending_date = "2026-07-29"  # type: ignore[attr-defined]
        eng._pending_minutes["0902"] = 22  # 新日 live pending
        fake.subscribe_error = None
        fake.day_minutes = {"0901": 9, "0902": 99}  # retry 抓回的是「新日」1K
        await asyncio.sleep(0.15)
        # 舊日 dict 一格都不許被新日資料蓋掉 / 加料
        assert eng.state()["twse"]["minutes"] == {"0901": 1}
        # 回補列落在**回補區**,live pending 區一格都不動(兩者分開存)
        assert eng._pending_backfill == {"0901": 9, "0902": 99}  # type: ignore[attr-defined]
        assert eng._pending_minutes == {"0902": 22}  # type: ignore[attr-defined]
    finally:
        await eng.close()


async def test_pending_worker_never_rebinds_the_live_pending_dict() -> None:
    """SP2(a):worker thread 不得**重新綁定** `_pending_minutes`。

    `{**minutes, **self._pending_minutes}` 是「讀快照 → 換一顆新 dict」:讀與寫之間
    event loop 的 `_handle_quote` 若寫進舊 dict,那一筆就人間蒸發(而畫面上只是少一個
    分鐘點)。既有姿態是 in-place,worker 側必須維持它 —— 用物件恆等釘住,因為那個
    race 本身沒有辦法在測試裡穩定重現。
    """
    fake = FakeIndexSource()
    fake.subscribe_error = ConnectionError("down")
    eng = make_engine(fake)
    await eng.start()
    try:
        eng._pending_date = "2026-07-29"  # type: ignore[attr-defined]
        live_dict = eng._pending_minutes  # type: ignore[attr-defined]
        fake.subscribe_error = None
        fake.day_minutes = {"0901": 9}
        await asyncio.sleep(0.15)
        assert eng._pending_minutes is live_dict  # type: ignore[attr-defined]
    finally:
        await eng.close()


async def test_swap_merges_retry_backfill_under_the_final_backfill() -> None:
    """SP2(b):合併順序 = **早輪 retry 回補 < 最終回補 < live pending**。

    改動前把 retry 抓的那份塞進 `_pending_minutes`,swap 的 `{**backfill, **pending}`
    就讓**早輪**回補贏過 rollover 當下的最終回補 —— 與 N058 同一種失效(先佔的近似值
    擋掉後到的真值),而兩份都是合法分鐘,畫面上零錯誤訊號。
    """
    fake = FakeIndexSource()
    eng = make_engine(fake)
    await eng.start()
    try:
        eng._pending_date = "2026-07-29"  # type: ignore[attr-defined]
        eng._pending_backfill.update({"0901": 1, "0902": 2, "0903": 3})  # type: ignore[attr-defined]
        eng._pending_minutes["0903"] = 33  # type: ignore[attr-defined]  # live 最大
        eng._swap_day(backfill={"0902": 22, "0903": 999})  # type: ignore[attr-defined]
        assert eng.state()["twse"]["minutes"] == {
            "0901": 1,  # 只有早輪 retry 有 → 留著
            "0902": 22,  # 最終回補贏過早輪 retry
            "0903": 33,  # live pending 贏過兩份回補
        }
        assert eng._pending_backfill == {}  # type: ignore[attr-defined]  # swap 後清空
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
    全量一次(#45 的送達行為銜接),退避歸零。

    **variant 停在成功值不歸零**(review L1-P1-3):0 號窗口已證明毒化,回到它等於
    每兩發浪費一發;天然全新的窗口字串只有換交易日才有(`_swap_day` 才歸零)。"""
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
        assert eng._heal_variant == 1  # type: ignore[attr-defined]  # 黏在成功值(L1-P1-3)
        assert eng._heal_interval is None  # type: ignore[attr-defined]
    finally:
        await eng.close()


async def test_heal_partial_progress_still_reaches_clients() -> None:
    """SC-6(review L1-P1-1 + L1-P1-2):進展 = **新分鐘鍵**,不是「已追上牆鐘」。

    推播盤中死、1K 只回補到 t-10 分(仍 lag)的那條路回的是真資料:以絕對 lag 判
    「無進展」會把它扣在引擎內不廣播(回退 #45 的送達保證),還順手把 variant 階梯
    燒在健康路徑上。有新鍵 → minutes 照送前端、variant 不動(該窗口在產出)。"""
    fake = FakeIndexSource()  # boot 那發回空
    eng = make_engine(fake, in_watch_window=lambda: True, now_fn=lambda: _dt.time(10, 0))
    await eng.start()  # _heal_secs 維持預設 60 → 本測試窗內只發得出一次 heal
    try:
        fake.day_minutes = {"0901": 1_000, "0950": 2_000}  # 有新鍵,但落後牆鐘 10 分
        stream = eng.stream()
        msg = await asyncio.wait_for(stream.__anext__(), timeout=2)
        assert msg["twse"]["minutes"] == {"0901": 1_000, "0950": 2_000}
        assert eng._heal_variant == 0  # type: ignore[attr-defined]
        assert fake.window_variants == [0, 0]  # boot + 首發 heal,都還在 0 號窗口
    finally:
        await eng.close()


async def test_frozen_stub_value_drift_is_not_progress(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SC-6(review L1-P1-2):凍結 stub 的 Close 隨現價漂 —— 同鍵不同值不是進展。

    以「fetch 有沒有回東西」或「值有沒有變」判定,毒化訂閱的每一發都像治好了;
    只有鍵集合差量看得出「一直是同一根」→ 判無進展、換窗口。"""
    fake = FakeIndexSource()
    # 第一發(boot)拿到那根 stub;第二發(heal)同鍵、Close 漂了
    fake.minutes_sequence = [{"0901": 23_000_000}, {"0901": 23_050_000}]
    eng = make_engine(fake, in_watch_window=lambda: True, now_fn=lambda: _dt.time(10, 0))
    with caplog.at_level(logging.WARNING, logger="copycat.server.index_engine"):
        await eng.start()
        try:
            stream = eng.stream()
            await asyncio.sleep(0.3)
            assert fake.fetch_minutes_calls == 2  # boot + 一發 heal
            with pytest.raises(TimeoutError):  # 無進展 → 不設 dirty → 零廣播
                await asyncio.wait_for(stream.__anext__(), timeout=0.1)
            assert eng._heal_variant == 1  # type: ignore[attr-defined]
        finally:
            await eng.close()
    assert "index 分時自癒無進展" in caplog.text


async def test_lag_recovery_keeps_variant_and_swap_day_resets_it() -> None:
    """SC-6(review L1-P1-3):覆蓋度追上只歸零**退避**,不歸零 variant。

    0 號窗口一旦毒化就一直是毒的,恢復時打回 0 等於推播死的日子每兩發浪費一發在
    已知死窗上。天然全新的窗口字串只有換交易日才有 → 只有 `_swap_day` 歸零。"""
    fake = FakeIndexSource(day_minutes={"0959": 2_000})  # 已追上牆鐘 10:00
    eng = make_engine(fake, in_watch_window=lambda: True, now_fn=lambda: _dt.time(10, 0))
    await eng.start()
    try:
        eng._heal_variant = 3  # type: ignore[attr-defined]  # 已爬過三階
        eng._heal_interval = 240.0  # type: ignore[attr-defined]
        await asyncio.sleep(0.1)  # 走過廣播 loop 的「覆蓋度跟上」分支
        assert eng._heal_interval is None  # type: ignore[attr-defined]  # 退避歸零(既有)
        assert eng._heal_variant == 3  # type: ignore[attr-defined]  # variant 黏住
        eng._pending_date = "2026-07-29"
        eng._swap_day(backfill={})
        assert eng._heal_variant == 0  # type: ignore[attr-defined]
    finally:
        await eng.close()


async def test_window_variant_cap_logs_separately(caplog: pytest.LogCaptureFixture) -> None:
    """SC-6(review L1-P2-2):階梯用盡與「還在爬」必須在 log 上可分。

    `fetch_day_minutes` 的 end hour 封頂 23(= variant 17),之後每一發都是同一個
    窗口字串、再無逃逸維度,而「無進展」那行字面上與第 1 次一模一樣 —— 值班的人
    看不出該不該換手段(換 session / 重啟 TC4)。"""
    fake = FakeIndexSource()  # 恆空 = 恆無進展
    eng = make_engine(fake, in_watch_window=lambda: True, now_fn=lambda: _dt.time(10, 0))
    with caplog.at_level(logging.WARNING, logger="copycat.server.index_engine"):
        await eng.start()
        try:
            eng._heal_variant = 16  # type: ignore[attr-defined]  # 下一發無進展就踏上封頂階
            await asyncio.sleep(0.3)
            assert fake.window_variants[-1] == 16
            assert eng._heal_variant == 17  # type: ignore[attr-defined]
        finally:
            await eng.close()
    assert "index 分時自癒:窗口階梯已達封頂" in caplog.text


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


async def test_rollover_skips_non_trading_day() -> None:
    """SC-3:非交易日不設 pending、不 `set_trade_date`、不重掛、不 `fetch_day_minutes`。

    現行判準是**純日曆日**(`new_date > trade_date`)—— 週末 / 國定假日整天每 60s 打一次
    TC4 1K,恆空、不 swap,凍在上一交易日。畫面「看起來對」是副作用而非設計,而那條
    空打是真的在燒 TC4 請求。
    """
    fake = FakeIndexSource()
    fake.day_minutes = {"0901": 1_000}
    ticks = {"n": 0}

    def _today() -> _dt.date:
        # `_today_fn` 是 rollover loop 每拍的第一件事(引擎內唯一呼叫點)→ 拿它當
        # 圈數計。否定型斷言必須先證明迴圈真的轉過,才有資格說「沒多打」。
        ticks["n"] += 1
        return _dt.date(2026, 8, 15)  # 週六

    eng = make_engine(
        fake,
        rollover=True,
        trade_date="2026-08-14",
        today_fn=_today,
        is_trading_day=lambda d: d.weekday() < 5,
    )
    eng._rollover_check_secs = 0.005  # type: ignore[attr-defined]
    await eng.start()
    try:
        calls_after_start = fake.fetch_minutes_calls  # start() 的回補那一次
        await wait_until(lambda: ticks["n"] >= 3)
        assert eng.state()["trade_date"] == "2026-08-14"
        assert eng._pending_date is None  # type: ignore[attr-defined]
        assert fake.trade_dates == ["2026-08-14"]  # 只有 start 同步那次
        assert fake.subscribed == ["IX0001"]  # 沒有重掛
        assert fake.fetch_minutes_calls == calls_after_start  # 沒有多打 1K
    finally:
        await eng.close()


async def test_rollover_runs_on_trading_day() -> None:
    """對照組:注入日曆且今天是交易日 → 兩段式換日語意逐字不變(W1)。"""
    fake = FakeIndexSource()
    fake.day_minutes = {"0901": 2_000}
    eng = make_engine(
        fake,
        rollover=True,
        trade_date="2026-08-13",
        today_fn=lambda: _dt.date(2026, 8, 14),  # 週五
        is_trading_day=lambda d: d.weekday() < 5,
    )
    eng._rollover_check_secs = 0.005  # type: ignore[attr-defined]
    await eng.start()
    try:
        # 等的是**結果**不是時間:換日要經 pending → 重掛 → 回補 → swap 四步,
        # 固定 sleep 只要有一步比預期慢就是 flake(慢機 / CI 上必現)。
        await wait_until(lambda: eng.state()["trade_date"] == "2026-08-14")
        state = eng.state()
        assert state["trade_date"] == "2026-08-14"
        assert state["twse"]["minutes"] == {"0901": 2_000}
        assert "2026-08-14" in fake.trade_dates
    finally:
        await eng.close()


async def test_default_rolls_over_on_weekend() -> None:
    """W9 預設鎖(S7):**不注入** `is_trading_day` 時語意逐字是純日曆日 —— 週六照換。

    預設值若被寫成 `weekday() < 5`(直覺上「更合理」),直接建構的既有 caller 會在
    週末靜默改行為,而所有既有測試都不會紅(它們都在平日日期上跑)。這條反向鎖住:
    週六仍要換日。
    """
    fake = FakeIndexSource()
    fake.day_minutes = {"0901": 2_000}
    eng = make_engine(
        fake,
        rollover=True,
        trade_date="2026-08-14",
        today_fn=lambda: _dt.date(2026, 8, 15),  # 週六
    )
    eng._rollover_check_secs = 0.005  # type: ignore[attr-defined]
    await eng.start()
    try:
        await wait_until(lambda: eng.state()["trade_date"] == "2026-08-15")
        assert eng.state()["twse"]["minutes"] == {"0901": 2_000}
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
class TestBackfillMergesOnEventLoop:
    """N094:`_subscribe_and_backfill` 跑在 worker thread 卻直接 in-place 寫
    `_twse.minutes` / `_pending_backfill` —— 被取消的 retry 其 orphan `to_thread` 仍會
    `update()`,與 event loop 端 `_minutes_lag_exceeded` 的 `max(m)` / `_payload` 的
    `dict(...)` 理論可撞 `RuntimeError: dictionary changed size during iteration`,
    而炸點在 `_broadcast_loop` 的 try/except **之外** —— 該發的自癒靜默消失。
    收法:worker 只回傳 dict、合併在 event loop 端做。
    """

    async def test_worker_does_not_write_shared_dicts(self) -> None:
        fake = FakeIndexSource()
        fake.day_minutes = {"0901": 43_000_000}
        eng = make_engine(fake)
        eng._loop = asyncio.get_running_loop()  # SP5 的副作用閘看它;直呼要自己備妥
        got = eng._subscribe_and_backfill()
        assert got == {"0901": 43_000_000}
        assert eng._twse.minutes == {}, "worker thread 直接寫共享 dict(N094)"
        assert eng._merge_backfill(got) is True  # 合併在 loop 端做,回「有沒有新鍵」
        assert eng._twse.minutes == {"0901": 43_000_000}
        assert eng._merge_backfill(got) is False  # 同一份再合併 = 零新鍵

    async def test_cancelled_retry_never_merges(self) -> None:
        """被取消的 retry:orphan 的 executor 工作項照樣跑完 fetch,但它的結果**不得**
        落進 `minutes` —— 舊碼在 worker 裡直接 `update()`,cancel 攔不到。"""
        fake = FakeIndexSource()
        gate = threading.Event()
        entered = threading.Event()
        orig = fake.fetch_day_minutes

        def _gated(code: str, *, window_variant: int = 0) -> dict[str, int]:
            entered.set()
            assert gate.wait(timeout=2)
            return {"0901": 43_000_000}

        fake.fetch_day_minutes = _gated  # type: ignore[method-assign]
        eng = make_engine(fake, retry_secs=0.001)
        eng._loop = asyncio.get_running_loop()
        eng._schedule_retry()
        await asyncio.to_thread(entered.wait, 2)
        assert eng._retry_task is not None
        eng._retry_task.cancel()
        gate.set()
        try:
            await eng._retry_task
        except asyncio.CancelledError:
            pass
        await asyncio.sleep(0.05)
        assert eng._twse.minutes == {}, "取消的 retry 仍把結果寫進 minutes"
        assert orig is not None
class TestRetrySupersededSideEffects:
    """review SP5:合併點搬到 loop 端之後,orphan 的 executor 工作項仍會執行
    `subscribe_symbol`(**帶著已作廢那一發的 window variant**)—— 訂閱是副作用不是
    回傳值,cancel 攔不到。副作用前要先看世代。
    """

    async def test_superseded_worker_skips_the_subscribe_side_effect(self) -> None:
        fake = FakeIndexSource()
        eng = make_engine(fake)
        eng._loop = asyncio.get_running_loop()
        eng._schedule_retry()  # 取號
        stale_epoch = eng._retry_epoch
        eng._schedule_retry()  # 再取一次 → 上一發作廢
        assert eng._retry_task is not None
        eng._retry_task.cancel()
        fake.subscribed.clear()
        assert eng._subscribe_and_backfill(0, epoch=stale_epoch) == {}
        assert fake.subscribed == [], "作廢的 retry 仍對 TC4 送了 SUBQUOTE"

    async def test_current_epoch_worker_still_subscribes(self) -> None:
        fake = FakeIndexSource()
        fake.day_minutes = {"0901": 43_000_000}
        eng = make_engine(fake)
        eng._loop = asyncio.get_running_loop()
        eng._schedule_retry()
        epoch = eng._retry_epoch
        assert eng._retry_task is not None
        eng._retry_task.cancel()
        fake.subscribed.clear()
        assert eng._subscribe_and_backfill(0, epoch=epoch) == {"0901": 43_000_000}
        assert fake.subscribed == ["IX0001"]

    async def test_closing_engine_skips_the_subscribe_side_effect(self) -> None:
        """`close()` 先把 `_loop` 斷掉(既有不變式)—— 之後起跑的 orphan 也不得再碰 source。"""
        fake = FakeIndexSource()
        eng = make_engine(fake)
        eng._loop = None
        assert eng._subscribe_and_backfill() == {}
        assert fake.subscribed == []


class _IdentIndexSource(FakeIndexSource):
    """記錄 `set_trade_date` 在哪一條執行緒被呼叫(SP1 的 index 側)。"""

    def __init__(self) -> None:
        super().__init__()
        self.trade_date_idents: list[int] = []

    def set_trade_date(self, trade_date: str) -> None:
        self.trade_date_idents.append(threading.get_ident())
        super().set_trade_date(trade_date)


async def test_index_rollover_switches_the_source_date_off_the_loop() -> None:
    """review SP1(index 側):`_rollover_loop` 直呼 `set_trade_date`,而它現在含一批
    同步 UNSUBQUOTE —— TC4 半死時整條 loop 停擺(廣播 / watchdog / MIS 全卡)。"""
    fake = _IdentIndexSource()
    eng = make_engine(
        fake,
        trade_date="2026-07-28",
        rollover=True,
        today_fn=lambda: _dt.date(2026, 7, 29),
    )
    eng._rollover_check_secs = 0.01
    loop_ident = threading.get_ident()
    await eng.start()
    try:
        await wait_until(lambda: "2026-07-29" in fake.trade_dates)
        idx = fake.trade_dates.index("2026-07-29")
        assert fake.trade_date_idents[idx] != loop_ident, (
            "換日的 ZMQ REQ 跑在 event loop 上"
        )
    finally:
        await eng.close()


# ---------------------------------------------------------------------------
# fix/index-quote-no-filledtime:IX0001 的 REALTIME quote 沒有時間欄位
# ---------------------------------------------------------------------------


class TestQuoteWithoutFilledTime:
    """2026-08-26 12:23 只聽不訂 probe 實證:TC4 推的 IX0001 quote `FilledTime` / `PreciseTime` 恆 `'0'`
    (只有 TradeDate)。舊碼 `minute_key('0', utc=True)` → 0801 域外 → None → 分鐘永遠不由推播寫、
    只更新現價;分鐘全靠 1K 自癒每 7 分鐘補一段,窗口階梯封頂後就停在那一分鐘(08-26 停在 1059)。"""

    async def test_quote_without_filled_time_keys_minute_by_wall_clock(self) -> None:
        fake = FakeIndexSource()
        eng = make_engine(fake, now_fn=lambda: _dt.time(10, 5, 30))
        await eng.start()
        try:
            assert fake.on_message is not None
            fake.on_message(_quote(filled="0"))
            await asyncio.sleep(0.06)
            state = eng.state()
            assert state["twse"]["p"] == 42_039_920
            # 牆鐘 10:05:30 → 1K 終點標記語意 = floor + 1 → 1006(與 FilledTime 路徑同一把尺)
            assert state["twse"]["minutes"] == {"1006": 42_039_920}
        finally:
            await eng.close()

    async def test_quote_without_filled_time_outside_domain_writes_price_only(self) -> None:
        # 08:20 試撮前的指數快照:牆鐘落在 0901–1330 域外 → 不寫分鐘、現價照更新、不炸
        fake = FakeIndexSource()
        eng = make_engine(fake, now_fn=lambda: _dt.time(8, 20, 0))
        await eng.start()
        try:
            assert fake.on_message is not None
            fake.on_message(_quote(filled="0"))
            await asyncio.sleep(0.06)
            state = eng.state()
            assert state["twse"]["p"] == 42_039_920
            assert state["twse"]["minutes"] == {}
        finally:
            await eng.close()

    async def test_quote_with_filled_time_still_uses_it_not_wall_clock(self) -> None:
        # 白名單:有時間欄位的 quote 照舊用 FilledTime(UTC+8),牆鐘不介入
        fake = FakeIndexSource()
        eng = make_engine(fake, now_fn=lambda: _dt.time(12, 0, 0))
        await eng.start()
        try:
            assert fake.on_message is not None
            fake.on_message(_quote(filled="13015"))  # 01:30:15 UTC → 0931
            await asyncio.sleep(0.06)
            assert eng.state()["twse"]["minutes"] == {"0931": 42_039_920}
        finally:
            await eng.close()

    async def test_first_in_domain_quote_swaps_pending_day_before_any_1k(self) -> None:
        """review SP2:修前 IX0001 的 key 恆 None,`_handle_quote` 的 pending 分支與 `_maybe_swap_day`
        在 prod 是死碼;修後 09:00 起第一筆入域推播就寫 `_pending_minutes` 並**立刻換日**(backfill={}),
        搶在 rollover loop 那趟 1K 之前 —— 這是 `_swap_day` 三層疊法本來就允許的路徑(live 推播最新),
        1K 之後由自癒(lag >3)接手。這條把該語意釘住,換日不再靠 1K 有料才發生。"""
        fake = FakeIndexSource()
        today = [_dt.date(2026, 7, 28)]
        now = [_dt.time(10, 5, 30)]
        eng = make_engine(fake, rollover=True, today_fn=lambda: today[0], now_fn=lambda: now[0])
        eng._rollover_check_secs = 0.03  # type: ignore[attr-defined]
        await eng.start()
        try:
            assert fake.on_message is not None
            fake.on_message(_quote(filled="0"))
            await asyncio.sleep(0.05)
            assert eng.state()["twse"]["minutes"] == {"1006": 42_039_920}
            # 換日:新日 1K 還沒有料(08:3x–09:00 真實形狀)→ 進 pending,舊分鐘不清
            fake.day_minutes = {}
            today[0] = _dt.date(2026, 7, 29)
            await asyncio.sleep(0.1)
            assert "2026-07-29" in fake.trade_dates
            assert eng.state()["trade_date"] == "2026-07-28"
            assert "1006" in eng.state()["twse"]["minutes"]
            # 09:00:05 第一筆入域推播 → 立刻 swap,新日 minutes 只有這一鍵、櫃買清空
            now[0] = _dt.time(9, 0, 5)
            fake.on_message(_quote(price="43000.00", filled="0"))
            await asyncio.sleep(0.05)
            state = eng.state()
            assert state["trade_date"] == "2026-07-29"
            assert state["twse"]["minutes"] == {"0901": 43_000_000}
            assert state["otc"]["minutes"] == {}
        finally:
            await eng.close()


def test_watch_end_is_the_index_heal_gate_boundary() -> None:
    """跨層 parity(CLAUDE.md §4「index session 自癒閘上界 = `_WATCH_END`」):`_WATCH_END` 是推播靜默
    (stale)watchdog 的凍結點(分時自癒 09:00 起全程都在,`_WATCH_END` 後只是換尾段判準接手),`stock_source._INDEX_HEAL_END` 是 TC4
    session 層 REALTIME 零推播自癒 / 健檢的上界 —— 兩把都釘在「收盤試撮起指數不更新」這一個事實,
    必須同值。漂掉的可觀測症狀:值被放寬 → 13:25 後 `零推播自癒 … IX0001` 又出現;值被收緊 → 加權
    stale 徽章 13:2x 提早熄滅。放在 server 側是因為依賴方向 server → live(pr-128 F-06)。"""
    assert in_index_heal_window_now(_WATCH_END) is False
    earlier = (
        _dt.datetime.combine(_dt.date(2026, 1, 1), _WATCH_END) - _dt.timedelta(seconds=1)
    ).time()
    assert in_index_heal_window_now(earlier) is True


class TestHolidayPushWarning:
    """L3(2026-08-28 triage):有日曆的休市日 index 自癒整天不打(PR #139)—— 日曆把真交易日誤標成
    休市那天,畫面掛休市膠囊、圖是前一日的,但 log 零訊號。09:00 後 IX0001 仍有推播就是「日曆錯了」
    的直接證據:同一日曆日收到 ≥ 5 個相異現價才 WARNING 一次(休市日 server 啟動時 SUBQUOTE 回一則
    前日收盤 snapshot 是單一價,不能算)。

    純同步:本組只驗 `_note_holiday_push` 的記帳,直呼 `_handle_quote`、不起 loop 不走廣播
    (同檔其他測試走 `fake.on_message` 是因為要涵蓋 `_on_quote_threadsafe` 那一跳)。"""

    @staticmethod
    def _engine(**kw: Any) -> IndexEngine:
        base: dict[str, Any] = {
            "now_fn": lambda: _dt.time(10, 0),
            "is_trading_day": lambda _d: False,
        }
        base.update(kw)
        return make_engine(FakeIndexSource(), **base)

    def test_five_distinct_prices_on_a_calendar_holiday_warn_once(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        eng = self._engine()
        with caplog.at_level(logging.WARNING, logger="copycat.server.index_engine"):
            for i in range(4):
                eng._handle_quote(_quote(price=f"4200{i}.00"))
            assert "可能誤標" not in caplog.text, "4 個相異價還不夠(啟動 snapshot 那種單價不算)"
            eng._handle_quote(_quote(price="42000.00"))  # 重複價不算新的一個
            assert "可能誤標" not in caplog.text
            eng._handle_quote(_quote(price="42004.00"))
            assert caplog.text.count("日曆說 2026-07-28 休市但 IX0001 09:00 後仍有推播") == 1
            for i in range(10):
                eng._handle_quote(_quote(price=f"4300{i}.00"))
        assert caplog.text.count("可能誤標") == 1, "同一日曆日只印一次"
        assert "configs/trading_holidays.json" in caplog.text

    def test_next_calendar_day_warns_again_and_restarts_the_count(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # prod server 連跑數日不重啟:日曆連錯兩天,第二天要能再印一次,而且相異價從 0 重數
        # (退化成「每 process 一次」或跨日累積,這裡都會紅;pr-145 F-04)
        today = [_dt.date(2026, 7, 28)]
        eng = self._engine(today_fn=lambda: today[0])
        with caplog.at_level(logging.WARNING, logger="copycat.server.index_engine"):
            for i in range(5):
                eng._handle_quote(_quote(price=f"4200{i}.00"))
            assert caplog.text.count("日曆說 2026-07-28 休市") == 1
            today[0] = _dt.date(2026, 7, 29)
            for i in range(4):
                eng._handle_quote(_quote(price=f"4300{i}.00"))
            assert "2026-07-29" not in caplog.text, "新日曆日要重新湊滿 5 個相異價,不能沿用前一天的"
            eng._handle_quote(_quote(price="43004.00"))
        assert caplog.text.count("日曆說 2026-07-29 休市") == 1
        assert caplog.text.count("可能誤標") == 2

    def test_no_warning_on_trading_day_before_nine_or_without_calendar(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # 白名單 4:交易日 / 09:00 前 / 無日曆三條路零新 log
        engines = [
            self._engine(is_trading_day=lambda _d: True),
            self._engine(now_fn=lambda: _dt.time(8, 40)),
            self._engine(is_trading_day=None),
        ]
        with caplog.at_level(logging.WARNING, logger="copycat.server.index_engine"):
            for eng in engines:
                for i in range(8):
                    eng._handle_quote(_quote(price=f"4200{i}.00"))
        assert "可能誤標" not in caplog.text
