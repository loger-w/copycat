"""screen engine 的跨模組常數 parity(review B1)+ compute() 資料完整性閘(review S3)。

演算法測試在 `tests/test_screening.py`、群組寫入在 `tests/server/test_watchlist_service.py`(#173 議定 seam)。
本檔以 fake fetcher + 注入時鐘 / fake sleep 釘住引擎的行為分歧點(零 IO):`compute()` 的取數守門
(日 K 回聲 / 空當沖名單 / 當沖回聲 / 相對閘)、08:00 目標交易日制的排程判定(W2 T4)、重試時間盒與
放棄(W2 T5,直接驅動 `_run_once` / `_run_attempts` / `tick`)、當沖名單三道閘先於 EOD 的 fail-fast(pr-211)。
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
import re
from collections.abc import Callable

import pytest

from copycat.server import breadth_engine, screen_engine
from copycat.server.breadth_fetch import BreadthFetchError
from copycat.server.screen_engine import SCREEN_GROUP, ScreenEngine
from copycat.trading_calendar import WEEKEND_ONLY
from tests.helpers.frontend_source import read_frontend_source


def test_daily_min_rows_parity_with_breadth() -> None:
    """單日全市場列數守門與 breadth 同值:兩邊守的是同一個上游(TaiwanStockPrice 分頁
    截斷),漂開的症狀是一邊當髒資料重試、另一邊照收 → 篩選候選無聲少一截。"""
    assert screen_engine._DAILY_MIN_ROWS == breadth_engine._DAILY_MIN_ROWS


def test_screen_group_name_parity_with_frontend() -> None:
    """跨語言契約(CLAUDE.md §4「盤前篩選群組名」;mod/group-grid-ticks T5 #181):後端
    `SCREEN_GROUP` 是產生點(nightly 寫進自選的群組名),前端 `lib/constants.ts::SCREEN_GROUP_NAME`
    是群組檢視 pill 的**過濾鍵**。後端改名而前端沒跟 → 圖牆又列出 ~60 張卡,兩側各自的測試全綠,
    零錯誤訊號。同 `test_avg_source_parity_with_frontend` 姿態:直讀前端原始碼字面。"""
    text = read_frontend_source("lib/constants.ts")
    m = re.search(r'export const SCREEN_GROUP_NAME = "([^"]+)";', text)
    assert m, 'constants.ts 找不到 `export const SCREEN_GROUP_NAME = "...";` 字面'
    assert m.group(1) == SCREEN_GROUP


# ---------------------------------------------------------------------------
# compute() 資料完整性閘(review S3)—— fake fetcher、零 IO
# ---------------------------------------------------------------------------

_DAY = _dt.date(2026, 9, 1)  # 週二(交易日)= 目標交易日;資料日(EOD 窗末日)= 週一 08-31
_DATA = _dt.date(2026, 8, 31)


def _daily_rows(day: _dt.date, n: int = 5) -> list[dict]:
    return [
        {"stock_id": f"{1000 + i}", "date": day.isoformat(), "close": 100.0, "spread": 0.0}
        for i in range(n)
    ]


Fetch = Callable[[str, _dt.date], list[dict]]


def _engine(
    daily: Fetch,
    day_trading: Fetch,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
    *,
    disposition: Fetch = lambda token, day: [],
    now_fn: Callable[[], _dt.datetime] = _dt.datetime.now,
    daytrade_floor: int = 1,
) -> ScreenEngine:
    monkeypatch.setattr(screen_engine, "_REQ_GAP_SECS", 0.0)
    # 列數守門降到 fixture 量級 —— 本組測的是回聲/空集合閘,不是列數閘(它有 parity 測試)
    monkeypatch.setattr(screen_engine, "_DAILY_MIN_ROWS", 1)
    # 當沖名單絕對下限同理(T6 #210 的閘;TestDayTradeRelativeGate 傳 daytrade_floor=1000 測真值)
    monkeypatch.setattr(screen_engine, "_DAYTRADE_MIN_ROWS", daytrade_floor)
    return ScreenEngine(
        token="tok",
        calendar=WEEKEND_ONLY,
        daily_fetch=daily,
        day_trading_fetch=day_trading,
        disposition_fetch=disposition,
        data_dir=tmp_path_factory.mktemp("screen"),
        now_fn=now_fn,
    )


def _dt_rows(day: _dt.date, n: int = 5) -> list[dict]:
    return [{"stock_id": f"{1000 + i}", "date": day.isoformat()} for i in range(n)]


def _write_prior(eng: ScreenEngine, rows: int) -> None:
    """寫一份 v2 快取當相對閘的前值(`daytrade_rows`);目標日 = 前一交易日(今天還沒算過)。"""
    path = eng._cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "_cache_version": screen_engine._CACHE_VERSION,
                "target_date": _DATA.isoformat(),
                "data_date": "2026-08-28",
                "daytrade_rows": rows,
                "written": [],
                "candidates": [],
            }
        ),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# W2 T4(#207):08:00 目標交易日制 —— compute 吃目標交易日;EOD 窗自資料日(前一交易日)往回,
# 當沖名單 / 處置股用目標交易日;快取 v2 以 target_date 判「做過沒」;非交易日早上不跑。
# ---------------------------------------------------------------------------


async def test_compute_fetches_eod_from_previous_trading_day_and_daytrade_disposition_on_target(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """三個 fetcher 各收到哪一天:EOD 第一發 = 資料日(目標日前一交易日、然後往回),
    當沖名單與處置股 = 目標交易日本人(今天的正式名單;昨天剛停當沖的今天不會還在名單裡)。
    處置判定的「涵蓋今天」也是目標日。"""
    daily_days: list[_dt.date] = []
    dt_days: list[_dt.date] = []
    disp_days: list[_dt.date] = []
    parsed_on: list[_dt.date] = []

    def daily(token: str, day: _dt.date) -> list[dict]:
        daily_days.append(day)
        return _daily_rows(day)

    def day_trading(token: str, day: _dt.date) -> list[dict]:
        dt_days.append(day)
        return _dt_rows(day)

    def disposition(token: str, day: _dt.date) -> list[dict]:
        disp_days.append(day)
        return []

    def fake_parse(rows: list[dict], today: _dt.date) -> set[str]:
        parsed_on.append(today)
        return set()

    monkeypatch.setattr(screen_engine, "parse_active_disposition", fake_parse)
    eng = _engine(daily, day_trading, monkeypatch, tmp_path_factory, disposition=disposition)
    await eng.compute(_DAY)
    assert daily_days[0] == _DATA  # EOD 窗末日 = 前一交易日,不是目標日(今天的 EOD 還不存在)
    assert all(d <= _DATA for d in daily_days)
    assert dt_days == [_DAY]
    assert disp_days == [_DAY]
    assert parsed_on == [_DAY]


async def test_cache_v2_records_target_and_data_date_and_old_version_is_void(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """換制的 migration:舊版(v1,21:00 制的「資料日」)快取讀為 None → 啟動補跑一次;
    新快取 v2 以 `target_date` 判「做過沒」,`data_date` 保留為推導值。"""
    eng = _engine(
        lambda token, day: _daily_rows(day),
        lambda token, day: _dt_rows(day),
        monkeypatch,
        tmp_path_factory,
    )
    path = eng._cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"_cache_version": 1, "data_date": _DAY.isoformat(), "candidates": []}),
        encoding="utf-8",
    )
    assert eng._cached_target_date() is None  # v1 作廢
    await eng._run_once(_DAY)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["_cache_version"] == 2
    assert payload["target_date"] == _DAY.isoformat()
    assert payload["data_date"] == _DATA.isoformat()
    assert eng._cached_target_date() == _DAY


class TestTick:
    """一次排程迭代(`tick`):以注入時鐘 + fake fetcher 觀測「該不該跑、跑哪一天」。"""

    @staticmethod
    def _counting(daily_days: list[_dt.date], dt_days: list[_dt.date]) -> tuple[Fetch, Fetch]:
        def daily(token: str, day: _dt.date) -> list[dict]:
            daily_days.append(day)
            return _daily_rows(day)

        def day_trading(token: str, day: _dt.date) -> list[dict]:
            dt_days.append(day)
            return _dt_rows(day)

        return daily, day_trading

    async def test_trading_day_at_run_time_computes_today(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        daily_days: list[_dt.date] = []
        dt_days: list[_dt.date] = []
        daily, day_trading = self._counting(daily_days, dt_days)
        eng = _engine(
            daily,
            day_trading,
            monkeypatch,
            tmp_path_factory,
            now_fn=lambda: _dt.datetime(2026, 9, 1, 8, 0, 30),  # 週二 08:00:30
        )
        await eng.tick()
        assert dt_days == [_DAY]  # 今天用的名單
        assert daily_days[0] == _DATA
        assert eng._cached_target_date() == _DAY
        # 同一目標日再 tick 不重跑
        await eng.tick()
        assert dt_days == [_DAY]

    async def test_non_trading_day_morning_does_not_run_when_friday_is_cached(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        """週六 08:01:目標交易日 = 週五,週五 08:00 已算過 → 零 fetch(非交易日沒有自己的名單)。"""
        daily_days: list[_dt.date] = []
        dt_days: list[_dt.date] = []
        daily, day_trading = self._counting(daily_days, dt_days)
        fri = _dt.date(2026, 9, 4)
        eng = _engine(
            daily,
            day_trading,
            monkeypatch,
            tmp_path_factory,
            now_fn=lambda: _dt.datetime(2026, 9, 4, 8, 0, 30),  # 週五 08:00:30
        )
        await eng.tick()
        assert dt_days == [fri]
        eng._now_fn = lambda: _dt.datetime(2026, 9, 5, 8, 1, 0)  # type: ignore[assignment]  # 週六 08:01
        await eng.tick()
        assert dt_days == [fri]  # 零新請求
        assert daily_days.count(fri - _dt.timedelta(days=1)) == 1

    async def test_loop_reruns_immediately_when_a_long_tick_crossed_today_run_time(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        """round-1 spec S-01:週二 07:00 啟動、週一那份沒算過 → 為週一補跑一路失敗到 08:50 放棄;
        這時 expected 已是週二(≥ 08:00),`_loop` 必須**立刻再 tick** 算今天,不能睡到明天 08:00:30。
        fetcher 以「第幾次被問到 08-28(週一那份 EOD 窗的第一天)」分辨:前 12 次(07:00 … 08:50 的 12 次
        週一嘗試)壞,之後好 —— 週二那份的窗第二天也問 08-28,那時已放行。"""
        clock = _Clock(_dt.datetime(2026, 9, 1, 7, 0, 0))  # 週二 07:00
        fri = _dt.date(2026, 8, 28)
        asked_fri = 0

        def daily(token: str, day: _dt.date) -> list[dict]:
            nonlocal asked_fri
            if day == fri:
                asked_fri += 1
                if asked_fri <= 12:
                    raise BreadthFetchError("FinMind down")
            return _daily_rows(day)

        sleeps: list[float] = []

        async def fake_sleep(secs: float) -> None:
            # 只放行 compute 節奏(0)與重試(600);第一次落到 `_sleep_secs` 的日等待就結束迴圈
            if secs not in (0.0, 600.0):
                raise asyncio.CancelledError
            if secs > 0:
                sleeps.append(secs)
            clock.t = clock.t + _dt.timedelta(seconds=secs)

        monkeypatch.setattr(screen_engine.asyncio, "sleep", fake_sleep)
        eng = _engine(
            daily, lambda token, day: _dt_rows(day), monkeypatch, tmp_path_factory, now_fn=clock.now
        )
        with pytest.raises(asyncio.CancelledError):
            await eng._loop()
        assert eng._gave_up_for == _dt.date(2026, 8, 31)  # 週一那份放棄
        assert eng._cached_target_date() == _DAY  # 週二那份緊接著算完,沒有睡到明天
        assert sleeps == [600.0] * 11  # 07:00 → 08:50 共 12 次嘗試、11 段;之後零等待直接跑週二

    async def test_sleep_targets_next_run_time_plus_buffer(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        eng = _engine(lambda token, day: [], lambda token, day: [], monkeypatch, tmp_path_factory)
        # 07:00 → 今天 08:00:30;08:00:31 → 明天 08:00:30
        assert eng._sleep_secs(_dt.datetime(2026, 9, 1, 7, 0, 0)) == 3630.0
        assert eng._sleep_secs(_dt.datetime(2026, 9, 1, 8, 0, 31)) == 24 * 3600 - 1


# ---------------------------------------------------------------------------
# W2 T5(#209):08:00–09:00 每 10 分鐘重試時間盒(不是三次盒)—— 以注入時鐘 + fake sleep 觀測序列。
# ---------------------------------------------------------------------------


class _Clock:
    def __init__(self, start: _dt.datetime) -> None:
        self.t = start

    def now(self) -> _dt.datetime:
        return self.t


def _install_fake_sleep(monkeypatch: pytest.MonkeyPatch, clock: _Clock) -> list[float]:
    """記錄 sleep 秒數並推進注入時鐘;`_REQ_GAP_SECS` 的 0 s 不計(compute 內的節奏 sleep)。"""
    sleeps: list[float] = []

    async def fake_sleep(secs: float) -> None:
        if secs > 0:
            sleeps.append(secs)
        clock.t = clock.t + _dt.timedelta(seconds=secs)

    monkeypatch.setattr(screen_engine.asyncio, "sleep", fake_sleep)
    return sleeps


def _failing(calls: list[_dt.datetime], clock: _Clock, *, quota: bool = False, succeed_on: int = 0):
    """EOD fetcher:每呼叫記時刻;第 `succeed_on` 次(1 起算)起成功,0 = 永遠失敗。"""

    def daily(token: str, day: _dt.date) -> list[dict]:
        calls.append(clock.t)
        if succeed_on and len(calls) >= succeed_on:
            return _daily_rows(day)
        raise BreadthFetchError("FinMind 尚未更新", quota=quota)

    return daily


class TestRetryWindow:
    TUE_0800 = _dt.datetime(2026, 9, 1, 8, 0, 30)

    async def test_fails_every_10_min_until_0900_then_gives_up_with_warnings_only(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path_factory: pytest.TempPathFactory,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """08:00:30 起每 600 s 再試,下一次會落在 09:00 之後就停:6 次嘗試(08:00:30 … 08:50:30)、
        5 段 600 s;放棄記在目標日,同日再 tick 不跑;log 全 WARNING、零 ERROR。"""
        clock = _Clock(self.TUE_0800)
        calls: list[_dt.datetime] = []
        sleeps = _install_fake_sleep(monkeypatch, clock)
        eng = _engine(
            _failing(calls, clock),
            lambda token, day: _dt_rows(day),
            monkeypatch,
            tmp_path_factory,
            now_fn=clock.now,
        )
        with caplog.at_level(logging.WARNING, logger="copycat.server.screen_engine"):
            await eng.tick()
        assert sleeps == [600.0] * 5
        assert [c.time() for c in calls] == [
            _dt.time(8, 0, 30),
            _dt.time(8, 10, 30),
            _dt.time(8, 20, 30),
            _dt.time(8, 30, 30),
            _dt.time(8, 40, 30),
            _dt.time(8, 50, 30),
        ]
        assert eng._gave_up_for == _DAY
        assert eng._cached_target_date() is None
        # 5 行「HH:MM:SS 再試」+ 1 行「第 6 次…今日放棄」(最後一次失敗與放棄合成同一行)
        assert [r.levelno for r in caplog.records] == [logging.WARNING] * 6
        assert sum("再試" in r.message for r in caplog.records[:-1]) == 5
        assert "放棄" in caplog.records[-1].message
        # 同一目標日再 tick(例如 09:30 別的事件)不再跑
        clock.t = _dt.datetime(2026, 9, 1, 9, 30)
        await eng.tick()
        assert len(calls) == 6

    async def test_succeeds_on_third_attempt_stops_retrying(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        clock = _Clock(self.TUE_0800)
        calls: list[_dt.datetime] = []
        sleeps = _install_fake_sleep(monkeypatch, clock)
        eng = _engine(
            _failing(calls, clock, succeed_on=3),
            lambda token, day: _dt_rows(day),
            monkeypatch,
            tmp_path_factory,
            now_fn=clock.now,
        )
        await eng.tick()
        assert sleeps == [600.0, 600.0]
        assert eng._cached_target_date() == _DAY
        assert eng._gave_up_for is None

    async def test_boot_after_0900_fails_gives_up_immediately(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        """09:05 才啟動的補跑失敗 → 下一次會在 09:15 > 09:00 → 零 sleep、一次嘗試、記放棄。"""
        clock = _Clock(_dt.datetime(2026, 9, 1, 9, 5))
        calls: list[_dt.datetime] = []
        sleeps = _install_fake_sleep(monkeypatch, clock)
        eng = _engine(
            _failing(calls, clock),
            lambda token, day: _dt_rows(day),
            monkeypatch,
            tmp_path_factory,
            now_fn=clock.now,
        )
        await eng.tick()
        assert sleeps == []
        assert len(calls) == 1
        assert eng._gave_up_for == _DAY

    async def test_quota_402_gives_up_today_with_explicit_warning(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path_factory: pytest.TempPathFactory,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """402 = 配額用盡 → 一次嘗試、零 sleep、當日放棄,WARNING 明講「配額」(round-1 F-04 / S-02:
        不再借 3600 s 退避越界來間接放棄)。"""
        clock = _Clock(self.TUE_0800)
        calls: list[_dt.datetime] = []
        sleeps = _install_fake_sleep(monkeypatch, clock)
        eng = _engine(
            _failing(calls, clock, quota=True),
            lambda token, day: _dt_rows(day),
            monkeypatch,
            tmp_path_factory,
            now_fn=clock.now,
        )
        with caplog.at_level(logging.WARNING, logger="copycat.server.screen_engine"):
            await eng.tick()
        assert sleeps == []
        assert len(calls) == 1
        assert eng._gave_up_for == _DAY
        assert [r.levelno for r in caplog.records] == [logging.WARNING]
        assert "配額" in caplog.records[0].message and "放棄" in caplog.records[0].message

    async def test_next_trading_day_rearms_after_give_up(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        clock = _Clock(_dt.datetime(2026, 9, 1, 9, 5))
        calls: list[_dt.datetime] = []
        _install_fake_sleep(monkeypatch, clock)
        eng = _engine(
            _failing(calls, clock, succeed_on=2),
            lambda token, day: _dt_rows(day),
            monkeypatch,
            tmp_path_factory,
            now_fn=clock.now,
        )
        await eng.tick()  # 週二 09:05 失敗 → 放棄
        assert eng._gave_up_for == _DAY
        clock.t = _dt.datetime(2026, 9, 2, 8, 0, 30)  # 週三 08:00:30
        await eng.tick()
        assert eng._cached_target_date() == _dt.date(2026, 9, 2)
        # `calls` 記每個 EOD 日的 fetch:週二那次失敗在第一發、週三成功那趟走完整個窗
        assert calls[0] == _dt.datetime(2026, 9, 1, 9, 5)
        assert calls[1] == _dt.datetime(2026, 9, 2, 8, 0, 30)
        assert all(c == calls[1] for c in calls[1:])


# ---------------------------------------------------------------------------
# W2 T6(#210):當沖名單相對閘 —— 今天列數 < 前一個交易日列數 × 0.8 視同未發布完(可重試錯誤),
# 無前值用絕對下限 1,000;列數落進快取 `daytrade_rows`(只在成功時更新);log 印今日 / 前值。
# 名單裡「有列 = 可當沖」的資格語意不變。
# ---------------------------------------------------------------------------


class TestDayTradeRelativeGate:
    @staticmethod
    def _gate_engine(
        rows: int,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path_factory: pytest.TempPathFactory,
        *,
        now_fn: Callable[[], _dt.datetime] = _dt.datetime.now,
    ) -> ScreenEngine:
        return _engine(
            lambda token, day: _daily_rows(day),
            lambda token, day: _dt_rows(day, rows),
            monkeypatch,
            tmp_path_factory,
            daytrade_floor=1000,
            now_fn=now_fn,
        )

    async def test_below_80_percent_of_prior_is_retryable_and_message_carries_both_counts(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path_factory: pytest.TempPathFactory,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """pr-211 F-05:閘本身**不自印** WARNING(其他五道 BreadthFetchError 閘都只 raise);兩數與
        「刪 daytrade_rows 鍵重置基準」的提示都在 exception 訊息裡,由 `_run_attempts` 那一行帶出。"""
        eng = self._gate_engine(1500, monkeypatch, tmp_path_factory)
        _write_prior(eng, 2000)
        with caplog.at_level(logging.WARNING, logger="copycat.server.screen_engine"):
            with pytest.raises(BreadthFetchError, match="1500") as ei:
                await eng._run_once(_DAY)
        assert "2000" in str(ei.value)
        assert "daytrade_rows" in str(ei.value)  # 重置基準的提示
        assert ei.value.quota is False
        assert caplog.records == []

    async def test_gate_failure_is_logged_exactly_once_by_the_attempt_loop(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path_factory: pytest.TempPathFactory,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """pr-211 F-05 的可觀測面:相對閘擋下 → 整輪只有 `_run_attempts` 的一行 WARNING(09:00 後
        補跑 = 直接放棄那行),兩數 + 刪鍵提示都在同一行,不再「閘一行 + 迴圈一行」雙印。"""
        eng = self._gate_engine(
            1500, monkeypatch, tmp_path_factory, now_fn=lambda: _dt.datetime(2026, 9, 1, 9, 5, 0)
        )
        _write_prior(eng, 2000)
        with caplog.at_level(logging.WARNING, logger="copycat.server.screen_engine"):
            await eng._run_attempts(_DAY)
        assert len(caplog.records) == 1
        msg = caplog.records[0].message
        assert "1500" in msg and "2000" in msg and "daytrade_rows" in msg and "放棄" in msg

    async def test_gate_failure_on_the_retry_path_is_one_line_per_attempt(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path_factory: pytest.TempPathFactory,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """同上、換 08:00:30 的重試路徑(two-axis S-04):每次 attempt 恰一行 WARNING、每行都帶刪鍵提示,
        5 行「再試」+ 1 行「放棄」,沒有閘自印的第二行。"""
        clock = _Clock(_dt.datetime(2026, 9, 1, 8, 0, 30))
        _install_fake_sleep(monkeypatch, clock)
        eng = self._gate_engine(1500, monkeypatch, tmp_path_factory, now_fn=clock.now)
        _write_prior(eng, 2000)
        with caplog.at_level(logging.WARNING, logger="copycat.server.screen_engine"):
            await eng.tick()
        assert [r.levelno for r in caplog.records] == [logging.WARNING] * 6
        assert all("daytrade_rows" in r.message and "1500" in r.message for r in caplog.records)
        assert sum("再試" in r.message for r in caplog.records[:-1]) == 5
        assert "放棄" in caplog.records[-1].message

    async def test_at_or_above_80_percent_passes(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        eng = self._gate_engine(1600, monkeypatch, tmp_path_factory)
        _write_prior(eng, 2000)
        await eng._run_once(_DAY)  # 不炸

    async def test_compute_cli_preview_ignores_server_prior(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        """pr-211 F-04:`compute()`(CLI 預覽路徑)**不吃** server 快取的前值 —— 同一顆引擎、同一份
        1500 列名單:`compute` 只走絕對下限(1,000)放行,`_run_once` 用前值 2000 × 0.8 擋下。
        CLI 不帶 data_dir 落的是 prod 那份快取,吃前值會讓 `screen --date <過去日>` 被 server 基準擋。"""
        eng = self._gate_engine(1500, monkeypatch, tmp_path_factory)
        _write_prior(eng, 2000)
        await eng.compute(_DAY)  # 不炸:CLI 預覽不被 server 前值影響
        with pytest.raises(BreadthFetchError, match="2000"):
            await eng._run_once(_DAY)

    async def test_no_prior_uses_absolute_floor_1000(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path_factory: pytest.TempPathFactory,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with pytest.raises(BreadthFetchError, match="900") as ei:
            await self._gate_engine(900, monkeypatch, tmp_path_factory)._run_once(_DAY)
        assert "前值 無(用絕對下限)" in str(ei.value)
        eng = self._gate_engine(1000, monkeypatch, tmp_path_factory)  # 恰 1,000 過
        with caplog.at_level(logging.INFO, logger="copycat.server.screen_engine"):
            await eng._run_once(_DAY)
        # 08:00 制第一天的驗收字串(W2 verification §6 / pr-211 F-01)—— 原始碼裡沒有連續字面,由這裡釘
        assert any("當沖名單 1000 列(前值 無(用絕對下限))" in r.message for r in caplog.records)

    async def test_success_records_count_and_failure_keeps_prior(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path_factory: pytest.TempPathFactory,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        eng = self._gate_engine(1700, monkeypatch, tmp_path_factory)
        _write_prior(eng, 2000)
        with caplog.at_level(logging.INFO, logger="copycat.server.screen_engine"):
            await eng._run_once(_DAY)
        payload = json.loads(eng._cache_path().read_text(encoding="utf-8"))
        assert payload["daytrade_rows"] == 1700
        assert any("1700" in r.message and "2000" in r.message for r in caplog.records)
        # round-1 S-05 / F-01:那行 INFO 在**落檔之後**才印(印了 = 前值已更新);compute 本身不印、不留 instance 欄位
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="copycat.server.screen_engine"):
            await eng.compute(_DAY)
        assert not any("前值" in r.message for r in caplog.records)
        assert not hasattr(eng, "_daytrade_rows_seen")
        # 下一天只給 1,300 列(< 1700 × 0.8 = 1360)→ 擋下,前值不動、目標日也不動
        eng._day_trading_fetch = lambda token, day: _dt_rows(day, 1300)  # type: ignore[assignment]
        with pytest.raises(BreadthFetchError):
            await eng._run_once(_dt.date(2026, 9, 2))
        payload = json.loads(eng._cache_path().read_text(encoding="utf-8"))
        assert payload["daytrade_rows"] == 1700
        assert payload["target_date"] == _DAY.isoformat()


# ---------------------------------------------------------------------------
# pr-211 F-02 (a):當沖名單三道閘(空集合 / 回聲 / 相對閘)排在 21 次 EOD **之前**(fail-fast)——
# 「名單沒出齊」是 T6 立論的最常走失敗路徑,原本每次都先重下載 21 個不會變的過去日 EOD 才發現;
# 提前後失敗路徑 22 → 1 個請求,10 分鐘重試節奏在失敗路徑上才成真。閘語意與 `_REQ_GAP_SECS` 節奏不變。
# ---------------------------------------------------------------------------


class TestDayTradeFailFast:
    @staticmethod
    def _counting_daily(calls: list[_dt.date]) -> Fetch:
        def daily(token: str, day: _dt.date) -> list[dict]:
            calls.append(day)
            return _daily_rows(day)

        return daily

    async def test_empty_daytrade_list_fails_before_any_eod_fetch(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        calls: list[_dt.date] = []
        eng = _engine(
            self._counting_daily(calls), lambda token, day: [], monkeypatch, tmp_path_factory
        )
        with pytest.raises(BreadthFetchError, match="當沖名單尚無資料"):
            await eng.compute(_DAY)
        assert calls == []  # EOD fetcher 零呼叫

    async def test_relative_gate_fails_before_any_eod_fetch(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        calls: list[_dt.date] = []
        eng = _engine(
            self._counting_daily(calls),
            lambda token, day: _dt_rows(day, 1500),
            monkeypatch,
            tmp_path_factory,
            daytrade_floor=1000,
        )
        _write_prior(eng, 2000)
        with pytest.raises(BreadthFetchError, match="1500"):
            await eng._run_once(_DAY)
        assert calls == []

    async def test_healthy_daytrade_list_still_fetches_the_full_eod_window(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        """對照組:名單健康 → EOD 窗照抓(21 個交易日),閘提前不是少抓。"""
        calls: list[_dt.date] = []
        eng = _engine(
            self._counting_daily(calls),
            lambda token, day: _dt_rows(day),
            monkeypatch,
            tmp_path_factory,
        )
        await eng.compute(_DAY)
        assert len(calls) == screen_engine.WINDOW_DAYS


async def test_daily_date_echo_mismatch_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """日 K 回聲不符(上游回錯日)必須炸成可重試錯誤 —— 靜默收下會把單日漲幅複利
    20 次算出全假名單(review F-07 的閘,S3 補錨)。"""
    wrong = _DAY - _dt.timedelta(days=30)
    eng = _engine(
        lambda token, day: _daily_rows(wrong),
        lambda token, day: [{"stock_id": "1234", "date": _DAY.isoformat()}],
        monkeypatch,
        tmp_path_factory,
    )
    with pytest.raises(BreadthFetchError, match="回聲不符"):
        await eng.compute(_DAY)


async def test_empty_day_trading_rows_raise_instead_of_wiping_group(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """當沖名單空 = 取數失敗重試,**不是**「全部候選非當沖」—— 後者會把群組清空還
    零訊號(review F-02 的空回應閘,S3 補錨)。"""
    eng = _engine(
        lambda token, day: _daily_rows(day),
        lambda token, day: [],
        monkeypatch,
        tmp_path_factory,
    )
    with pytest.raises(BreadthFetchError, match="當沖名單尚無資料"):
        await eng.compute(_DAY)


async def test_day_trading_date_echo_mismatch_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    wrong = (_DAY - _dt.timedelta(days=30)).isoformat()
    eng = _engine(
        lambda token, day: _daily_rows(day),
        lambda token, day: [{"stock_id": "1234", "date": wrong}],
        monkeypatch,
        tmp_path_factory,
    )
    with pytest.raises(BreadthFetchError, match="當沖名單資料日回聲不符"):
        await eng.compute(_DAY)


# ---------------------------------------------------------------------------
# 跨 attempt EOD memo + 處置股 fail-fast(next-time 「screen_engine 跨 attempt memo」,09-08 另 session 帶入):
# 同一目標交易日內重試不重抓上一輪已拿到的 EOD(抄 breadth `_streak_memo`:存縮列後 rows、目標日換日清空);
# 處置股取數提到 EOD 之前(取數失敗 22 → 2 個請求)。
# ---------------------------------------------------------------------------


class TestEodAttemptMemo:
    @staticmethod
    def _counting_daily(
        counts: dict[_dt.date, int], *, fail_once_on: _dt.date | None = None
    ) -> Fetch:
        def daily(token: str, day: _dt.date) -> list[dict]:
            counts[day] = counts.get(day, 0) + 1
            if day == fail_once_on and counts[day] == 1:
                raise BreadthFetchError(f"FinMind {day} 暫時失敗")
            return _daily_rows(day)

        return daily

    async def test_retry_reuses_eod_rows_fetched_by_the_previous_attempt(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        """第 1 次 attempt 抓到第 5 個交易日(08-25)才失敗 → 第 2 次只補抓 08-25 起未拿到的日子:
        前 4 日各 1 次、08-25 兩次、總呼叫 = 21 + 1;成功落檔、只睡一段 600 s。"""
        clock = _Clock(_dt.datetime(2026, 9, 1, 8, 0, 30))
        sleeps = _install_fake_sleep(monkeypatch, clock)
        counts: dict[_dt.date, int] = {}
        bad = _dt.date(2026, 8, 25)
        eng = _engine(
            self._counting_daily(counts, fail_once_on=bad),
            lambda token, day: _dt_rows(day),
            monkeypatch,
            tmp_path_factory,
            now_fn=clock.now,
        )
        await eng.tick()
        assert eng._cached_target_date() == _DAY
        assert sleeps == [600.0]
        assert counts[bad] == 2
        assert all(counts[d] == 1 for d in counts if d != bad)
        assert sum(counts.values()) == screen_engine.WINDOW_DAYS + 1

    async def test_memo_is_dropped_when_the_target_trading_day_changes(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        """週二整早都在 08-25 那天失敗、09:00 放棄(memo 留著 08-31 … 08-26 四天)→ 週三 08:00:30 再 tick:
        窗重疊的日子(08-31 等)要重抓,不沿用昨天那份 memo(同一日期的 EOD 不會變,但 memo 只服務當次目標日;
        抄 breadth 武裝時清空)。同時釘週二六次 attempt 之間 08-31 只抓一次(memo 跨失敗 attempt 有效)。"""
        clock = _Clock(_dt.datetime(2026, 9, 1, 8, 0, 30))
        _install_fake_sleep(monkeypatch, clock)
        counts: dict[_dt.date, int] = {}
        bad = _dt.date(2026, 8, 25)

        def daily(token: str, day: _dt.date) -> list[dict]:
            counts[day] = counts.get(day, 0) + 1
            if day == bad and clock.t.date() == _DAY:
                raise BreadthFetchError(f"FinMind {day} 週二整早失敗")
            return _daily_rows(day)

        eng = _engine(
            daily, lambda token, day: _dt_rows(day), monkeypatch, tmp_path_factory, now_fn=clock.now
        )
        await eng.tick()
        assert eng._gave_up_for == _DAY
        assert counts[_DATA] == 1  # 六次 attempt 只抓一次 08-31
        assert counts[bad] == 6  # 失敗那天每次都重試
        clock.t = _dt.datetime(2026, 9, 2, 8, 0, 30)  # 週三
        await eng.tick()
        assert eng._cached_target_date() == _dt.date(2026, 9, 2)
        assert counts[_DATA] == 2  # 週三的窗也含 08-31,重抓而非沿用

    async def test_disposition_fetch_failure_happens_before_any_eod_fetch(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        counts: dict[_dt.date, int] = {}

        def disposition(token: str, day: _dt.date) -> list[dict]:
            raise BreadthFetchError("處置股 暫時失敗")

        eng = _engine(
            self._counting_daily(counts),
            lambda token, day: _dt_rows(day),
            monkeypatch,
            tmp_path_factory,
            disposition=disposition,
        )
        with pytest.raises(BreadthFetchError, match="處置股"):
            await eng.compute(_DAY)
        assert counts == {}
