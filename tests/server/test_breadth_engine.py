"""家數帶 / 騰落線引擎(market-overview R2 Task 6;design §5 逐條款)。

**禁止真打 FinMind**:三個取數點全部注入 fake callable,整條路不碰網路
(conftest 另把 FINMIND_TOKEN 中和,漏注入也不會流出去)。

輪詢節奏不靠真 sleep 測:一輪被抽成 `_run_cycle()`,絕大多數案例直接 await 它;
只有「首圈無條件 fetch / 窗外不 fetch」與「restore + 首輪」需要真的跑 loop,
那兩處才用 `start()` + 極短 poll 間隔 + 條件等待。
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import time as _time
from pathlib import Path
from typing import Any, Callable

import pytest

import copycat.server.breadth_engine as be
from copycat.breadth_config import BreadthConfig
from copycat.server.breadth_fetch import BreadthFetchError

_TRADE_DATE = "2026-08-05"
_STAMP = f"{_TRADE_DATE} 10:23:45"
#: `_STAMP` 對應的分鐘鍵(index_engine.minute_key 的 floor+1 終點標記)
_KEY = "1024"

# ---------------------------------------------------------------------------
# fixture rows(手算對照 — 見 _EXPECTED)
# ---------------------------------------------------------------------------

_INFO_ROWS: list[dict] = [
    {
        "date": "2026-08-01",
        "stock_id": "2330",
        "stock_name": "台積電",
        "type": "twse",
        "industry_category": "半導體業",
    },
    {
        "date": "2026-08-01",
        "stock_id": "1101",
        "stock_name": "台泥",
        "type": "twse",
        "industry_category": "水泥工業",
    },
    {
        "date": "2026-08-01",
        "stock_id": "2317",
        "stock_name": "鴻海",
        "type": "twse",
        "industry_category": "其他電子業",
    },
    {
        "date": "2026-08-01",
        "stock_id": "6488",
        "stock_name": "環球晶",
        "type": "tpex",
        "industry_category": "半導體業",
    },
    {
        "date": "2026-08-01",
        "stock_id": "0050",
        "stock_name": "元大台灣50",
        "type": "twse",
        "industry_category": "ETF",
    },
    {
        "date": "2026-08-01",
        "stock_id": "9999",
        "stock_name": "處置股",
        "type": "twse",
        "industry_category": "其他",
    },
]

_DISPOSITION_ROWS: list[dict] = [
    {"stock_id": "9999", "period_start": "2026-08-01", "period_end": "2026-08-10"}
]

#: 手算:1101 前收 10.0 → 漲停 11.0(cand 11000 毫元、tick 50、整除)
#: 6488 前收 10.0 → 跌停 9.0(cand 9000 毫元、tick 10、整除);2330 前收 99.0 →
#: 漲停 108.5 ≠ 100.0 故只是上漲;2317 平盤;0050 = ETF、9999 = 處置股、001 = 指數
#: row(不在對照表)三者皆排除。
_EXPECTED = {
    "twse": {"limit_up": 1, "up": 1, "flat": 1, "down": 0, "limit_down": 0},
    "tpex": {"limit_up": 0, "up": 0, "flat": 0, "down": 0, "limit_down": 1},
}
_EXPECTED_POINT = {"t": _KEY, "twse": [1, 1, 1, 0, 0], "tpex": [0, 0, 0, 0, 1]}


def _snapshot_rows(stamp: str = _STAMP) -> list[dict]:
    def row(sid: str, close: float, chg_price: float, chg_rate: float) -> dict:
        return {
            "date": stamp,
            "stock_id": sid,
            "close": close,
            "change_price": chg_price,
            "change_rate": chg_rate,
            "total_volume": 1000,
            "yesterday_volume": 500,
            "total_amount": 12_345,
        }

    return [
        row("2330", 100.0, 1.0, 1.01),
        row("1101", 11.0, 1.0, 10.0),
        row("2317", 50.0, 0.0, 0.0),
        row("6488", 9.0, -1.0, -10.0),
        row("0050", 200.0, 1.0, 0.5),
        row("9999", 20.0, 1.0, 5.0),
        row("001", 23_000.0, 100.0, 0.4),
    ]


# ---------------------------------------------------------------------------
# 替身
# ---------------------------------------------------------------------------


class FakeFetch:
    """取數替身:記錄呼叫次數;`error` 一設就丟(不設回 `rows`)。"""

    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.error: Exception | None = None
        self.calls = 0

    def __call__(self, token: str, *args: Any) -> list[dict]:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.rows


class FakeDaily:
    """單日全市場 EOD 取數替身(`daily_fetch`)。

    `calendar` 沒有的日期一律回空 list —— 即「假日」的真實樣態(FinMind 對非交易日
    回合法的空 `data` 陣列)。`on_call` 讓測試在掃描途中動時鐘(跨午夜情境)。
    """

    def __init__(self, calendar: dict[str, list[dict]]) -> None:
        self.calendar = calendar
        self.calls: list[str] = []
        self.error: Exception | None = None
        self.on_call: Callable[[int], None] | None = None

    def __call__(self, token: str, day: _dt.date) -> list[dict]:
        self.calls.append(day.isoformat())
        if self.on_call is not None:
            self.on_call(len(self.calls))
        if self.error is not None:
            raise self.error
        return self.calendar.get(day.isoformat(), [])


class FakeMono:
    """凍結的單調鐘(`breadth_engine._monotonic` 替身)。

    真時鐘在兩次呼叫之間必然前進,「剛剛成功」與「stale_secs 已過」就無法用門檻
    0 / 極小值區分 —— 要驗一個時間門檻只能真的控制時間,不是把門檻調到極端。
    """

    def __init__(self, start: float = 1_000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, secs: float) -> None:
        self.t += secs


@pytest.fixture
def mono(monkeypatch: pytest.MonkeyPatch) -> FakeMono:
    clock = FakeMono()
    monkeypatch.setattr(be, "_monotonic", clock)
    return clock


class Clock:
    """today_fn / now_fn 注入點;兩者可各自改(換日測試要它們錯開)。"""

    def __init__(self, today: str = _TRADE_DATE, now: str = "10:24:00") -> None:
        self.today = _dt.date.fromisoformat(today)
        self.now = _dt.datetime.fromisoformat(f"{today} {now}")

    def today_fn(self) -> _dt.date:
        return self.today

    def now_fn(self) -> _dt.datetime:
        return self.now


def _make(
    tmp_path: Path,
    *,
    snapshot: FakeFetch | None = None,
    info: FakeFetch | None = None,
    disposition: FakeFetch | None = None,
    daily: FakeDaily | None = None,
    clock: Clock | None = None,
    config: BreadthConfig | None = None,
) -> tuple[Any, FakeFetch, FakeFetch, FakeFetch, Clock]:
    snap = snapshot if snapshot is not None else FakeFetch(_snapshot_rows())
    inf = info if info is not None else FakeFetch(list(_INFO_ROWS))
    disp = disposition if disposition is not None else FakeFetch(list(_DISPOSITION_ROWS))
    clk = clock if clock is not None else Clock()
    engine = be.BreadthEngine(
        token="tok",
        config=config if config is not None else BreadthConfig(),
        snapshot_fetch=snap,
        stock_info_fetch=inf,
        disposition_fetch=disp,
        daily_fetch=daily,
        data_dir=tmp_path,
        today_fn=clk.today_fn,
        now_fn=clk.now_fn,
    )
    return engine, snap, inf, disp, clk


async def _wait_until(pred: Callable[[], bool], timeout: float = 2.0) -> None:
    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        if pred():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("條件未在時限內成立")


def _series_file(tmp_path: Path, trade_date: str = _TRADE_DATE) -> Path:
    return tmp_path / f"breadth-{trade_date}.json"


# ---------------------------------------------------------------------------
# 連板數(streak)用具 —— EOD 造值 / 造日曆 / 快取檔
# ---------------------------------------------------------------------------

#: today = 2026-08-05(週三)往回的 10 個交易日;夾著兩個週末(_HOLIDAYS)
_TRADING_DAYS = [
    "2026-08-04",
    "2026-08-03",
    "2026-07-31",
    "2026-07-30",
    "2026-07-29",
    "2026-07-28",
    "2026-07-27",
    "2026-07-24",
    "2026-07-23",
    "2026-07-22",
]
_HOLIDAYS = ["2026-08-02", "2026-08-01", "2026-07-26", "2026-07-25"]


def _eod_rows(limit_ups: tuple[str, ...] = (), *, pad: int = 3) -> list[dict]:
    """單日 EOD 造值:`limit_ups` 每檔一列**剛好漲停**,其餘為平盤墊列。

    前收 = `close − spread` = 10.0 → 漲停 11.0(tick 0.05,10% 整除)。墊列只為
    撐過 `_DAILY_MIN_ROWS` 健檢,代號取 9000 段避免與被判股撞號。
    """
    rows: list[dict] = [{"stock_id": sid, "close": 11.0, "spread": 1.0} for sid in limit_ups]
    rows += [{"stock_id": f"{9000 + i}", "close": 10.0, "spread": 0.0} for i in range(pad)]
    return rows


def _calendar(days: dict[str, tuple[str, ...]]) -> dict[str, list[dict]]:
    """{交易日: 該日漲停代號} → FakeDaily 的 calendar(不在鍵內的日期 = 假日空回應)。"""
    return {day: _eod_rows(sids) for day, sids in days.items()}


def _streaks_file(tmp_path: Path, day: str = _TRADE_DATE) -> Path:
    return tmp_path / f"streaks-{day}.json"


def _write_streaks_cache(
    tmp_path: Path,
    *,
    computed_for: str = _TRADE_DATE,
    data_end: str = "2026-08-04",
    dates: list[str] | None = None,
    skipped: list[str] | None = None,
    streaks: dict[str, int] | None = None,
    version: int = 1,
    file_day: str = _TRADE_DATE,
) -> Path:
    payload = {
        "_version": version,
        "computed_for": computed_for,
        "data_end": data_end,
        "dates": dates if dates is not None else ["2026-08-04", "2026-08-03", "2026-07-31"],
        "skipped": skipped if skipped is not None else ["2026-08-02", "2026-08-01"],
        "streaks": streaks if streaks is not None else {"1101": 3},
    }
    path = _streaks_file(tmp_path, file_day)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def fast_streaks(monkeypatch: pytest.MonkeyPatch) -> None:
    """streak 測試不靠真 sleep(檔頭慣例):request 間隔與重試秒數歸零。

    `_DAILY_MIN_ROWS` 一併降到墊列量級 —— 每個成功路徑案例都造 25,000 列會讓整個
    檔慢一個數量級;真門檻的邊界由 `TestStreakHealthChecks` 以真常數兩側取值把關。
    """
    monkeypatch.setattr(be, "_STREAK_REQ_GAP_SECS", 0.0)
    monkeypatch.setattr(be, "_STREAK_RETRY_SECS", 0.0)
    monkeypatch.setattr(be, "_DAILY_MIN_ROWS", 3)


# ---------------------------------------------------------------------------
# 正常輪
# ---------------------------------------------------------------------------


class TestNormalCycle:
    async def test_counts_series_and_file(self, tmp_path: Path) -> None:
        engine, snap, inf, disp, _ = _make(tmp_path)

        await engine._run_cycle()

        state = engine.state()
        assert state["enabled"] is True
        assert state["trade_date"] == _TRADE_DATE
        assert state["as_of"] == "10:23:45"
        assert state["counts"] == _EXPECTED
        assert state["series"] == [_EXPECTED_POINT]
        assert state["stale"] is False
        assert snap.calls == 1 and inf.calls == 1 and disp.calls == 1

        saved = json.loads(_series_file(tmp_path).read_text(encoding="utf-8"))
        assert saved == {"_version": 1, "trade_date": _TRADE_DATE, "series": [_EXPECTED_POINT]}

    async def test_rows_kept_on_engine_but_not_in_state(self, tmp_path: Path) -> None:
        """全量 rows 是 R3 輪的原料 —— 存在 engine 上,本輪不進 REST payload。"""
        engine, *_ = _make(tmp_path)

        await engine._run_cycle()

        assert {r["stock_id"] for r in engine.rows} == {"2330", "1101", "2317", "6488"}
        assert "rows" not in engine.state()

    async def test_state_before_first_cycle(self, tmp_path: Path) -> None:
        """引擎在但首輪未成 = 「載入中」三態之一:counts None、series 空、stale。"""
        engine, *_ = _make(tmp_path)

        state = engine.state()

        assert state == {
            "enabled": True,
            "trade_date": None,
            "as_of": None,
            "stale": True,
            "counts": None,
            "series": [],
        }

    async def test_publishes_payload_each_cycle(self, tmp_path: Path, mono: FakeMono) -> None:
        """成敗皆 publish 一則;`last_minute` 只在本輪有 append 時帶值。"""
        engine, snap, *_ = _make(tmp_path)
        stream = engine.stream()
        seed = await stream.__anext__()
        assert seed["type"] == "breadth" and seed["counts"] is None

        await engine._run_cycle()
        ok_msg = await stream.__anext__()

        snap.error = BreadthFetchError("down")
        mono.advance(60.0)  # 超過 stale_secs
        await engine._run_cycle()
        fail_msg = await stream.__anext__()
        await stream.aclose()

        assert ok_msg == {
            "type": "breadth",
            "trade_date": _TRADE_DATE,
            "as_of": "10:23:45",
            "stale": False,
            "counts": _EXPECTED,
            "last_minute": _EXPECTED_POINT,
        }
        assert fail_msg["last_minute"] is None
        assert fail_msg["counts"] == _EXPECTED  # 失敗保前值
        assert fail_msg["stale"] is True


# ---------------------------------------------------------------------------
# 失敗處理 / 退避 / stale
# ---------------------------------------------------------------------------


class TestFailureHandling:
    async def test_fetch_error_keeps_counts_and_marks_stale(
        self, tmp_path: Path, mono: FakeMono
    ) -> None:
        engine, snap, *_ = _make(tmp_path)  # stale_secs 預設 30
        await engine._run_cycle()
        assert engine.state()["stale"] is False

        snap.error = BreadthFetchError("upstream down")
        mono.advance(20.0)
        await engine._run_cycle()
        assert engine.state()["stale"] is False  # 門檻內的一次失敗不算延遲

        mono.advance(20.0)
        await engine._run_cycle()

        state = engine.state()
        assert state["counts"] == _EXPECTED  # 保前值,不清空
        assert state["series"] == [_EXPECTED_POINT]
        assert state["stale"] is True

    async def test_not_stale_outside_window_even_without_success(self, tmp_path: Path) -> None:
        """窗外沒有新資料是正常態,不該亮延遲(degraded 另計)。"""
        engine, *_ = _make(tmp_path, clock=Clock(now="16:00:00"))
        await engine._run_cycle()

        assert engine.state()["stale"] is False

    async def test_quota_error_uses_long_backoff(self, tmp_path: Path) -> None:
        """402 = 配額用盡,短退避只會繼續燒 —— 直接跳 quota_backoff_secs。"""
        engine, snap, *_ = _make(tmp_path)
        snap.error = BreadthFetchError("配額用盡", quota=True)

        await engine._run_cycle()

        assert engine._effective_interval() == 300.0

    async def test_backoff_grows_and_resets_on_success(self, tmp_path: Path) -> None:
        engine, snap, *_ = _make(tmp_path)
        assert engine._effective_interval() == 10.0

        snap.error = BreadthFetchError("down")
        seen: list[float] = []
        for _ in range(4):
            await engine._run_cycle()
            seen.append(engine._effective_interval())
        assert seen == [10.0, 20.0, 40.0, 60.0]

        snap.error = None
        await engine._run_cycle()
        assert engine._effective_interval() == 10.0

    async def test_unexpected_exception_counted_as_failure(self, tmp_path: Path) -> None:
        """注入的取數層不保證只丟 BreadthFetchError;任何例外都算該輪失敗(不得逃逸)。"""
        engine, snap, *_ = _make(tmp_path)
        snap.error = RuntimeError("boom")

        await engine._run_cycle()

        assert engine.state()["counts"] is None
        assert engine._effective_interval() == 10.0

    async def test_backoff_exponent_clamped_against_overflow(self, tmp_path: Path) -> None:
        """退避指數必須先夾制再取冪:`2 ** 1999` 乘 float 會 OverflowError,而它是在
        `_poll_loop` 的 `await asyncio.sleep(...)` 那行拋 —— 傘罩包不到,poll task
        當場死透且面板只是凍住(review P2-2)。"""
        engine, *_ = _make(tmp_path)
        engine._fail_streak = 2_000

        assert engine._effective_interval() == 60.0  # backoff_max_secs

    async def test_empty_sector_map_is_degraded(self, tmp_path: Path) -> None:
        """對照表空 → 白名單剃光 → 統計全空;degraded 必須拉起 stale 且每輪重試。"""
        info = FakeFetch([])
        engine, _snap, inf, _disp, _ = _make(tmp_path, info=info, clock=Clock(now="16:00:00"))

        await engine._run_cycle()
        await engine._run_cycle()

        state = engine.state()
        assert state["counts"] is None
        assert state["stale"] is True  # 窗外也 stale:degraded 不受窗限制
        assert inf.calls == 2  # 空表不刷 TTL,下一輪照樣重試

    async def test_no_parsable_tick_time_is_failure(self, tmp_path: Path) -> None:
        """時刻推不出來就無從標記 as_of / 分鐘鍵 —— 該輪視同失敗,不動既有值。"""
        rows = [{**r, "date": None} for r in _snapshot_rows()]
        engine, *_ = _make(tmp_path, snapshot=FakeFetch(rows))

        await engine._run_cycle()

        state = engine.state()
        assert state["counts"] is None and state["trade_date"] is None
        assert not _series_file(tmp_path).exists()


# ---------------------------------------------------------------------------
# 對照表 TTL(R9)
# ---------------------------------------------------------------------------


class TestMapCache:
    async def test_failure_retries_after_backoff_then_ttl_holds(
        self, tmp_path: Path, mono: FakeMono
    ) -> None:
        """失敗不刷時戳(退避後重試);成功才刷(24h 內不再打)。

        「下輪即重試」是 P2-4 之前的契約 —— 以 poll 節奏重打壞掉的最重 endpoint 只會
        加速燒配額,改為 60s 退避(重試條件本身不變:時戳仍未刷)。
        """
        info = FakeFetch(list(_INFO_ROWS))
        info.error = BreadthFetchError("info down")
        engine, _snap, inf, disp, _ = _make(tmp_path, info=info)

        await engine._run_cycle()
        assert engine.state()["counts"] is None
        assert inf.calls == 1

        info.error = None
        mono.advance(be._MAP_RETRY_SECS + 1.0)
        await engine._run_cycle()
        assert engine.state()["counts"] == _EXPECTED
        assert inf.calls == 2

        await engine._run_cycle()
        assert inf.calls == 2  # TTL 內不再取
        # 處置股在第一輪就成功了(兩份對照表各自計時)→ 之後三輪都被自己的 TTL 擋
        assert disp.calls == 1

    async def test_failure_keeps_previous_maps(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TTL 到期後取數失敗 → 沿用前一份對照表,該輪照樣算得出 counts。"""
        monkeypatch.setattr(be, "_MAP_TTL_SECS", 0.0)
        info = FakeFetch(list(_INFO_ROWS))
        engine, *_ = _make(tmp_path, info=info)
        await engine._run_cycle()

        info.error = BreadthFetchError("info down")
        await engine._run_cycle()

        assert engine.state()["counts"] == _EXPECTED

    async def test_maps_refetched_on_new_trade_day(self, tmp_path: Path, mono: FakeMono) -> None:
        """24h TTL 走單調鐘,不隨交易日換 —— 跨日必須重取,否則沿用前一日的處置名單
        (那份名單每天都變)整個交易日(review P1-3)。"""
        engine, _snap, inf, disp, clock = _make(tmp_path)
        await engine._run_cycle()
        assert (inf.calls, disp.calls) == (1, 1)

        clock.today = _dt.date(2026, 8, 6)
        clock.now = _dt.datetime(2026, 8, 6, 10, 24)
        mono.advance(3_600.0)  # 遠短於 24h TTL:光靠單調鐘不會到期

        await engine._run_cycle()

        assert (inf.calls, disp.calls) == (2, 2)

    async def test_map_failure_backs_off_before_retry(
        self, tmp_path: Path, mono: FakeMono
    ) -> None:
        """對照表取數失敗 → 退避 60s 才重試(review P2-4)。

        `TaiwanStockInfo` 是這條路上最重的 endpoint,以 poll 節奏(10s)重打壞掉的
        上游只會加速燒配額,而配額用盡的表現是**整個面板**跟著死。
        """
        info = FakeFetch(list(_INFO_ROWS))
        info.error = BreadthFetchError("info down")
        engine, _snap, inf, *_ = _make(tmp_path, info=info)

        await engine._run_cycle()
        assert inf.calls == 1

        mono.advance(10.0)  # 下一輪 poll
        await engine._run_cycle()
        assert inf.calls == 1  # 退避中:不重打

        mono.advance(51.0)  # 越過 60s
        info.error = None
        await engine._run_cycle()
        assert inf.calls == 2

    async def test_map_quota_failure_uses_quota_backoff(
        self, tmp_path: Path, mono: FakeMono
    ) -> None:
        """402 = 配額用盡 → 沿用 `quota_backoff_secs`(300s),不是一般 60s。"""
        info = FakeFetch(list(_INFO_ROWS))
        info.error = BreadthFetchError("配額用盡", quota=True)
        engine, _snap, inf, *_ = _make(tmp_path, info=info)

        await engine._run_cycle()
        mono.advance(299.0)
        await engine._run_cycle()
        assert inf.calls == 1

        mono.advance(2.0)
        await engine._run_cycle()
        assert inf.calls == 2

    async def test_disposition_success_then_failure_keeps_previous_list(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """**先成功後失敗 → 前一份名單仍生效**(design「保前值」的字面;review SPEC-5)。

        「以空集合續行」只描述了冷啟動那一半:已經拿到過名單之後再失敗,處置股不會突然
        被算回家數裡(否則 counts 會在上游抖一下時跳一階,而那一階看起來像真的行情)。
        """
        monkeypatch.setattr(be, "_MAP_TTL_SECS", 0.0)  # 每輪都重取(才走得到第二次失敗)
        disp = FakeFetch(list(_DISPOSITION_ROWS))
        engine, *_ = _make(tmp_path, disposition=disp, clock=Clock(now="16:00:00"))

        await engine._run_cycle()
        assert engine.state()["counts"]["twse"]["up"] == 1  # 9999 被名單剔除

        disp.error = BreadthFetchError("disposition down")
        await engine._run_cycle()

        state = engine.state()
        assert state["counts"]["twse"]["up"] == 1  # 前一份名單仍生效(不是空集合)
        assert state["stale"] is True  # 但誠實標 degraded

    async def test_disposition_failure_is_degraded_but_continues(self, tmp_path: Path) -> None:
        """處置股表**冷啟動**就拿不到 → 空集合續行(那幾檔會被算進去),但要亮 degraded。"""
        disp = FakeFetch(list(_DISPOSITION_ROWS))
        disp.error = BreadthFetchError("disposition down")
        engine, *_ = _make(tmp_path, disposition=disp, clock=Clock(now="16:00:00"))

        await engine._run_cycle()

        state = engine.state()
        assert state["counts"]["twse"]["up"] == 2  # 9999 未被處置股名單剔除
        assert state["stale"] is True


# ---------------------------------------------------------------------------
# 序列 append / 落檔 / restore(R1/R2/R3)
# ---------------------------------------------------------------------------


class TestSeriesPersistence:
    async def test_today_ahead_of_snapshot_does_not_append_or_truncate(
        self, tmp_path: Path
    ) -> None:
        """跨午夜 / 假日重啟讀到上一交易日快照:counts 照更新,但**不 append 不寫檔**
        —— 前一日的完整落檔絕不可被單點覆寫成一格(R1)。"""
        prior = {
            "_version": 1,
            "trade_date": _TRADE_DATE,
            "series": [
                {"t": "0931", "twse": [0, 1, 2, 3, 0], "tpex": [0, 0, 0, 0, 0]},
                {"t": "0932", "twse": [0, 2, 2, 2, 0], "tpex": [0, 0, 0, 0, 0]},
                {"t": "0933", "twse": [1, 2, 2, 1, 0], "tpex": [0, 0, 0, 0, 0]},
            ],
        }
        _series_file(tmp_path).write_text(json.dumps(prior), encoding="utf-8")
        engine, *_ = _make(tmp_path, clock=Clock(today="2026-08-06", now="09:10:00"))
        engine._restore()

        await engine._run_cycle()

        state = engine.state()
        assert state["counts"] == _EXPECTED  # scalar 照更新
        assert state["series"] == []  # 不 append
        assert not _series_file(tmp_path, "2026-08-06").exists()
        assert json.loads(_series_file(tmp_path).read_text(encoding="utf-8")) == prior

    async def test_restore_then_first_cycle_merges_series(self, tmp_path: Path) -> None:
        """落檔 → 新 engine start → 首輪同日快照:序列 = 落檔 + 本輪(R2)。"""
        prior_points = [
            {"t": "0931", "twse": [0, 1, 2, 3, 0], "tpex": [0, 0, 0, 0, 0]},
            {"t": "0932", "twse": [0, 2, 2, 2, 0], "tpex": [0, 0, 0, 0, 0]},
        ]
        _series_file(tmp_path).write_text(
            json.dumps({"_version": 1, "trade_date": _TRADE_DATE, "series": prior_points}),
            encoding="utf-8",
        )
        engine, *_ = _make(tmp_path, config=BreadthConfig(poll_secs=60.0))

        await engine.start()
        try:
            await _wait_until(lambda: engine.state()["counts"] is not None)
        finally:
            await engine.close()

        assert engine.state()["series"] == [*prior_points, _EXPECTED_POINT]
        saved = json.loads(_series_file(tmp_path).read_text(encoding="utf-8"))
        assert saved["series"] == [*prior_points, _EXPECTED_POINT]

    async def test_start_does_no_network_io(self, tmp_path: Path) -> None:
        """start() 只做本地 restore + 起 task;boot 不得被 FinMind 拖住(R6)。"""
        engine, snap, inf, disp, _ = _make(tmp_path, config=BreadthConfig(poll_secs=60.0))

        await engine.start()
        assert (snap.calls, inf.calls, disp.calls) == (0, 0, 0)
        await engine.close()

    @pytest.mark.parametrize("bad", ["not json at all", '{"_version": 99, "series": []}'])
    async def test_bad_or_versioned_out_file_restores_empty(
        self, tmp_path: Path, bad: str
    ) -> None:
        _series_file(tmp_path).write_text(bad, encoding="utf-8")
        engine, *_ = _make(tmp_path)

        engine._restore()  # never-raise

        state = engine.state()
        assert state["series"] == [] and state["trade_date"] is None

    @pytest.mark.parametrize(
        "bad_point",
        [
            pytest.param("not a dict", id="非 dict"),
            pytest.param({"t": 931, "twse": [0] * 5, "tpex": [0] * 5}, id="t 非 str"),
            pytest.param({"t": "0940", "twse": [0, 1, 2, 3], "tpex": [0] * 5}, id="twse 長度 4"),
            pytest.param({"t": "0941", "twse": [0] * 5, "tpex": [0, 0, 0, 0, "x"]}, id="含字串"),
            pytest.param(
                {"t": "0942", "twse": [0, 0, 0, 0, True], "tpex": [0] * 5}, id="bool 混入"
            ),
            pytest.param({"t": "0943", "twse": [0] * 5}, id="缺 tpex"),
        ],
    )
    async def test_restore_drops_malformed_points_only(
        self, tmp_path: Path, bad_point: object
    ) -> None:
        """畸形點**逐點丟棄**、合法點照收(review TC-2)。

        形狀防禦零覆蓋時 `_is_bucket_row` 恆 True 的 mutation 全綠 —— 而畸形點會一路
        流到前端變成 NaN(圖上是斷線或整段空白,不是錯誤)。`bool` 是 `int` 的子類,
        `[.., True]` 這種值必須擋在後端。
        """
        good = {"t": "0931", "twse": [0, 1, 2, 3, 0], "tpex": [0, 0, 0, 0, 0]}
        _series_file(tmp_path).write_text(
            json.dumps({"_version": 1, "trade_date": _TRADE_DATE, "series": [good, bad_point]}),
            encoding="utf-8",
        )
        engine, *_ = _make(tmp_path)

        engine._restore()

        assert engine.state()["series"] == [good]
        assert engine.state()["trade_date"] == _TRADE_DATE

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({"_version": 1, "trade_date": _TRADE_DATE, "series": {}}, id="series 非 list"),
            pytest.param({"_version": 1, "trade_date": 20260805, "series": []}, id="日期非 str"),
        ],
    )
    async def test_restore_rejects_bad_top_level_shape(self, tmp_path: Path, payload: dict) -> None:
        """頂層形狀不符 → 整份不採用(空序列起步),不是半份。"""
        _series_file(tmp_path).write_text(json.dumps(payload), encoding="utf-8")
        engine, *_ = _make(tmp_path)

        engine._restore()

        state = engine.state()
        assert state["series"] == [] and state["trade_date"] is None

    async def test_save_oserror_degrades_without_killing_cycle(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """落檔失敗只降級:記憶體序列照在、該輪照樣廣播 —— 磁碟滿不得拖垮 poll(review TC-2)。"""

        def _boom(*_a: object, **_k: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(be.os, "replace", _boom)
        engine, *_ = _make(tmp_path)

        with caplog.at_level("WARNING"):
            await engine._run_cycle()

        assert engine.state()["series"] == [_EXPECTED_POINT]  # 記憶體序列不受影響
        assert not _series_file(tmp_path).exists()
        assert any("落檔失敗" in r.message for r in caplog.records)

    async def test_rollover_clears_series(self, tmp_path: Path) -> None:
        engine, snap, _inf, _disp, clock = _make(tmp_path)
        await engine._run_cycle()
        assert engine.state()["series"] == [_EXPECTED_POINT]

        clock.today = _dt.date(2026, 8, 6)
        clock.now = _dt.datetime(2026, 8, 6, 10, 24)
        snap.rows = _snapshot_rows("2026-08-06 09:30:10")
        await engine._run_cycle()

        state = engine.state()
        assert state["trade_date"] == "2026-08-06"
        assert state["series"] == [{**_EXPECTED_POINT, "t": "0931"}]

    async def test_stale_date_snapshot_does_not_clobber_today_series(self, tmp_path: Path) -> None:
        """快照日期既非今日、也非目前序列日 → **不採用日期變更、不清序列**(review P1-1)。

        清序列的條件原本只看「與前值不同」,而 append 的條件是「== 今天」—— 兩者不對稱:
        一輪拿到上一交易日(或髒 row 推出來的別日)就會把當天已累積的整段序列連同落檔
        一起抹掉,而下一輪又因 `!= today` 不 append,畫面從此空著且零錯誤訊號。
        """
        engine, snap, *_ = _make(tmp_path)
        await engine._run_cycle()
        assert engine.state()["series"] == [_EXPECTED_POINT]
        before = _series_file(tmp_path).read_text(encoding="utf-8")

        snap.rows = _snapshot_rows("2026-08-04 13:20:00")  # 上一交易日
        await engine._run_cycle()

        state = engine.state()
        assert state["trade_date"] == _TRADE_DATE  # 日期不採用
        assert state["series"] == [_EXPECTED_POINT]  # 序列不清
        assert state["as_of"] == "13:20:00"  # scalar 仍誠實反映該輪快照
        assert _series_file(tmp_path).read_text(encoding="utf-8") == before  # 落檔不被截短
        assert not _series_file(tmp_path, "2026-08-04").exists()

    async def test_future_dirty_row_does_not_freeze_minute_key(self, tmp_path: Path) -> None:
        """單一越界髒 row 不得決定 as_of / 分鐘鍵(review P1-2)。

        `max(date)` 取自未過濾全快照:上游偶發回一列收盤時刻,整個交易日的序列就會塌成
        那一格(同鍵 last-wins),檔案還在、格式還對,只有內容從整天縮成一點。
        """
        clock = Clock(now="09:30:00")
        dirty = {
            "date": f"{_TRADE_DATE} 13:30:00",
            "stock_id": "001",  # 指數 row:不在對照表 → 不影響家數
            "close": 23_000.0,
            "change_price": 100.0,
            "change_rate": 0.4,
        }
        snap = FakeFetch([*_snapshot_rows(f"{_TRADE_DATE} 09:29:30"), dirty])
        engine, *_ = _make(tmp_path, snapshot=snap, clock=clock)

        await engine._run_cycle()
        assert engine.state()["as_of"] == "09:29:30"

        clock.now = _dt.datetime.fromisoformat(f"{_TRADE_DATE} 09:31:00")
        snap.rows = [*_snapshot_rows(f"{_TRADE_DATE} 09:30:30"), dirty]
        await engine._run_cycle()

        state = engine.state()
        assert state["as_of"] == "09:30:30"
        assert [p["t"] for p in state["series"]] == ["0930", "0931"]  # 逐分鐘長格,不塌成一格

    @pytest.mark.parametrize("stamp_time", ["14:30:00", "08:59:00"])
    async def test_tick_outside_minute_domain_not_appended(
        self, tmp_path: Path, stamp_time: str
    ) -> None:
        """盤後定盤 14:30 與盤前 08:59 都在分鐘域(0901–1330)之外 —— scalar 更新、
        序列不收、檔不寫。

        `now` 跟著快照時刻走(P1-2 之後兩者必須自洽:快照時刻超前本機時鐘 10 分鐘
        以上即視為髒 row 忽略,而 14:30 的定盤本來就是 14:30 當下收到的)。
        """
        snap = FakeFetch(_snapshot_rows(f"{_TRADE_DATE} {stamp_time}"))
        engine, *_ = _make(tmp_path, snapshot=snap, clock=Clock(now=stamp_time))

        await engine._run_cycle()

        state = engine.state()
        assert state["counts"] == _EXPECTED
        assert state["as_of"] == stamp_time
        assert state["series"] == []
        assert not _series_file(tmp_path).exists()

    async def test_same_minute_last_wins(self, tmp_path: Path) -> None:
        engine, snap, *_ = _make(tmp_path)
        await engine._run_cycle()

        rows = _snapshot_rows(f"{_TRADE_DATE} 10:23:59")
        rows[0]["change_rate"] = -1.0  # 2330 轉跌
        rows[0]["close"] = 98.0
        rows[0]["change_price"] = -1.0
        snap.rows = rows
        await engine._run_cycle()

        series = engine.state()["series"]
        assert len(series) == 1
        assert series[0] == {"t": _KEY, "twse": [1, 0, 1, 1, 0], "tpex": [0, 0, 0, 0, 1]}


# ---------------------------------------------------------------------------
# poll loop 窗判定
# ---------------------------------------------------------------------------


class TestPollLoop:
    async def test_outside_window_only_first_cycle_fetches(self, tmp_path: Path) -> None:
        """首圈無條件跑(盤後開站也要有數字);之後窗外一律不打 FinMind。"""
        engine, snap, *_ = _make(
            tmp_path,
            clock=Clock(now="07:00:00"),
            config=BreadthConfig(poll_secs=0.01),
        )

        await engine.start()
        try:
            await _wait_until(lambda: snap.calls >= 1)
            await asyncio.sleep(0.1)  # 夠跑約 10 圈
        finally:
            await engine.close()

        assert snap.calls == 1

    async def test_inside_window_keeps_fetching(self, tmp_path: Path) -> None:
        engine, snap, *_ = _make(tmp_path, config=BreadthConfig(poll_secs=0.01))

        await engine.start()
        try:
            await _wait_until(lambda: snap.calls >= 3)
        finally:
            await engine.close()

        assert snap.calls >= 3

    async def test_arm_streaks_exception_does_not_kill_poll_loop(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """武裝檢查拋例外 → poll loop 續行(review R9)。

        `_maybe_arm_streaks` 放在 `try:` **之外**的話,一次例外就殺掉整條 poll task ——
        表現是家數面板從此凍在最後一則、零錯誤訊號,而肇因只是連板數那條旁支。
        前兩圈拋、之後放行:同時驗「迴圈沒死」與「後續照常取數」。
        """
        seen = {"n": 0}

        def _boom(_self: object) -> None:
            seen["n"] += 1
            if seen["n"] <= 2:
                raise RuntimeError("boom")

        monkeypatch.setattr(be.BreadthEngine, "_maybe_arm_streaks", _boom)
        engine, snap, *_ = _make(tmp_path, config=BreadthConfig(poll_secs=0.01))

        await engine.start()
        try:
            await _wait_until(lambda: seen["n"] >= 3 and snap.calls >= 1)
        finally:
            await engine.close()

    async def test_loop_survives_cycle_exception(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """一輪炸掉不得讓 poll task 死透(index `_mis_loop` 同款傘罩)。

        注入點必須在 `_fetch_snapshot` 的 try/except **之外**(review TC-3):注在取數層
        時例外根本到不了 `_poll_loop`,測到的是那個 catch 而不是傘罩 —— 把傘罩整段刪掉
        原測試照樣綠。`compute_breadth` 在 `_apply` 內、全程無保護,是真的會逃到迴圈的路。
        """

        def _boom(*_a: object, **_k: object) -> dict:
            raise RuntimeError("boom")

        monkeypatch.setattr(be, "compute_breadth", _boom)
        engine, snap, *_ = _make(tmp_path, config=BreadthConfig(poll_secs=0.01))

        await engine.start()
        try:
            await _wait_until(lambda: snap.calls >= 3)
        finally:
            await engine.close()

        assert snap.calls >= 3


# ---------------------------------------------------------------------------
# 連板數重算(design §3.3;R3/R4/R13/R15/R16)
# ---------------------------------------------------------------------------


class TestStreakCompute:
    async def test_success_path_skips_holidays_and_caches(
        self, tmp_path: Path, fast_streaks: None
    ) -> None:
        """回看 10 交易日:空回應日跳過(不中斷)、收滿即停、成果落檔。

        1101 十日皆漲停 → 10(撞窗上限);2330 只有最近兩日 → 2;2317 漲停不含最近
        一日 → 不在結果內(streak 已中斷)。
        """
        limits: dict[str, tuple[str, ...]] = {d: ("1101",) for d in _TRADING_DAYS}
        limits["2026-08-04"] = ("1101", "2330")
        limits["2026-08-03"] = ("1101", "2330", "2317")
        daily = FakeDaily(_calendar(limits))
        engine, *_ = _make(tmp_path, daily=daily)

        assert await engine._compute_streaks_once() is True

        assert engine._streaks == {"1101": 10, "2330": 2}
        assert engine._streaks_day == _TRADE_DATE
        assert engine._streaks_end == "2026-08-04"
        assert engine._streaks_span == 10
        assert engine._streaks_skipped == set(_HOLIDAYS)
        # 掃描自 day−1 起、收滿 10 個交易日即停(不會掃滿 25 日曆日)
        assert daily.calls == sorted([*_TRADING_DAYS, *_HOLIDAYS], reverse=True)

        saved = json.loads(_streaks_file(tmp_path).read_text(encoding="utf-8"))
        assert saved == {
            "_version": 1,
            "computed_for": _TRADE_DATE,
            "data_end": "2026-08-04",
            "dates": _TRADING_DAYS,
            "skipped": sorted(_HOLIDAYS),
            "streaks": {"1101": 10, "2330": 2},
        }

    async def test_scan_stops_at_calendar_limit_with_short_window(
        self, tmp_path: Path, fast_streaks: None
    ) -> None:
        """窗收不滿(長假 / 上市未滿 10 日)照樣成立:span < 10,封頂語意由 span 表達。"""
        daily = FakeDaily(_calendar({"2026-08-04": ("1101",), "2026-08-03": ("1101",)}))
        engine, *_ = _make(tmp_path, daily=daily)

        assert await engine._compute_streaks_once() is True

        assert engine._streaks == {"1101": 2}
        assert engine._streaks_span == 2
        assert len(daily.calls) == 25  # 收不滿 → 掃到 _STREAK_SCAN_CAL_DAYS 上限為止
        assert daily.calls[-1] == "2026-07-11"  # day − 25

    async def test_result_discarded_when_day_rolls_over_mid_scan(
        self, tmp_path: Path, fast_streaks: None
    ) -> None:
        """跨午夜完成的結果是「以昨日為基準」的錯值,且會被快取固化 → 丟棄(R3)。"""
        daily = FakeDaily(_calendar({"2026-08-04": ("1101",)}))
        engine, _s, _i, _d, clock = _make(tmp_path, daily=daily)

        def _roll(n: int) -> None:
            if n == 1:
                clock.today = _dt.date(2026, 8, 6)

        daily.on_call = _roll

        assert await engine._compute_streaks_once() is False

        assert engine._streaks == {} and engine._streaks_day is None
        assert not _streaks_file(tmp_path).exists()
        assert not _streaks_file(tmp_path, "2026-08-06").exists()

    async def test_data_end_not_yesterday_logs_warning(
        self, tmp_path: Path, fast_streaks: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        """昨日被當假日跳過 → 盤中判式仍會 +1(KR-1 殘餘風險)。落檔前留下觀測訊號。"""
        daily = FakeDaily(_calendar({"2026-08-03": ("1101",)}))
        engine, *_ = _make(tmp_path, daily=daily)

        with caplog.at_level("WARNING"):
            assert await engine._compute_streaks_once() is True

        assert engine._streaks_end == "2026-08-03"
        assert any("2026-08-04" in r.getMessage() for r in caplog.records)


class TestStreakHealthChecks:
    """空回應 = 假日的兩道防禦(R4/R16)—— 真交易日回空 / 回半份都會高估連板數。"""

    async def test_row_count_below_threshold_fails_whole_round(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """非空但列數不足 = 部分截斷,**不可當假日跳過**:整輪失敗(真門檻 − 1)。"""
        monkeypatch.setattr(be, "_STREAK_REQ_GAP_SECS", 0.0)
        short = _eod_rows(("1101",), pad=be._DAILY_MIN_ROWS - 2)
        assert len(short) == be._DAILY_MIN_ROWS - 1
        daily = FakeDaily({"2026-08-04": short})
        engine, *_ = _make(tmp_path, daily=daily)

        assert await engine._compute_streaks_once() is False

        assert engine._streaks_day is None
        assert daily.calls == ["2026-08-04"]  # 立即中止,不繼續往回掃
        assert not _streaks_file(tmp_path).exists()

    async def test_row_count_at_threshold_accepted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """門檻**含等值**:剛好 25,000 列是可用的一日(邊界另一側)。"""
        monkeypatch.setattr(be, "_STREAK_REQ_GAP_SECS", 0.0)
        exact = _eod_rows(("1101",), pad=be._DAILY_MIN_ROWS - 1)
        assert len(exact) == be._DAILY_MIN_ROWS
        daily = FakeDaily({"2026-08-04": exact})
        engine, *_ = _make(tmp_path, daily=daily)

        assert await engine._compute_streaks_once() is True

        assert engine._streaks == {"1101": 1}
        assert engine._streaks_span == 1

    async def test_calendar_gap_beyond_limit_is_not_adopted(
        self, tmp_path: Path, fast_streaks: None
    ) -> None:
        """收到的相鄰交易日日曆間距 > 12 日 = 中間有整段被當假日吃掉 → 該輪不採用。"""
        daily = FakeDaily(_calendar({"2026-08-04": ("1101",), "2026-07-20": ("1101",)}))
        engine, *_ = _make(tmp_path, daily=daily)

        assert await engine._compute_streaks_once() is False

        assert engine._streaks_day is None
        assert not _streaks_file(tmp_path).exists()

    async def test_gap_within_limit_is_adopted(self, tmp_path: Path, fast_streaks: None) -> None:
        """春節等級的連假(≤ 12 日)不誤殺(KR-3 的另一側)。"""
        daily = FakeDaily(_calendar({"2026-08-04": ("1101",), "2026-07-23": ("1101",)}))
        engine, *_ = _make(tmp_path, daily=daily)

        assert await engine._compute_streaks_once() is True

        assert engine._streaks == {"1101": 2}


class TestStreakScheduling:
    """武裝(排程)與成功分離 —— `_streak_armed_day` vs `_streaks_day`(R13)。"""

    async def test_not_armed_before_arm_time(self, tmp_path: Path, fast_streaks: None) -> None:
        """06:00 前不武裝:T-1 EOD 未發布時重算會把 T-1 當假日跳過並**成功**固化錯值。"""
        daily = FakeDaily(_calendar({"2026-08-04": ("1101",)}))
        engine, *_ = _make(tmp_path, daily=daily, clock=Clock(now="05:59:59"))

        engine._maybe_arm_streaks()

        assert engine._streak_task is None
        assert engine._streak_armed_day is None
        assert daily.calls == []

    async def test_armed_at_arm_time(self, tmp_path: Path, fast_streaks: None) -> None:
        daily = FakeDaily(_calendar({"2026-08-04": ("1101",)}))
        engine, *_ = _make(tmp_path, daily=daily, clock=Clock(now="06:00:00"))

        engine._maybe_arm_streaks()

        task = engine._streak_task
        assert task is not None
        assert engine._streak_armed_day == _TRADE_DATE
        await task
        assert engine._streaks == {"1101": 1}

    async def test_disabled_when_no_daily_fetch(self, tmp_path: Path, fast_streaks: None) -> None:
        """`daily_fetch=None` = 連板停用:不武裝、rows 端點照常(streak 恆 null)。"""
        engine, *_ = _make(tmp_path)

        engine._maybe_arm_streaks()

        assert engine._streak_task is None and engine._streak_armed_day is None

    async def test_attempt_limit_then_no_rearm_same_day(
        self, tmp_path: Path, fast_streaks: None
    ) -> None:
        """壞上游不整天燒配額:10 次用完 task 結束,同日再檢查也不重起(R13)。"""
        daily = FakeDaily({})
        daily.error = BreadthFetchError("upstream down")
        engine, *_ = _make(tmp_path, daily=daily)

        engine._maybe_arm_streaks()
        task = engine._streak_task
        assert task is not None
        await task

        assert len(daily.calls) == be._STREAK_MAX_ATTEMPTS
        assert engine._streak_attempts == be._STREAK_MAX_ATTEMPTS
        assert engine._streaks_day is None

        engine._maybe_arm_streaks()  # task 已 done,但 armed_day 相符 → 不再起
        assert engine._streak_task is task
        assert len(daily.calls) == be._STREAK_MAX_ATTEMPTS

    @pytest.mark.parametrize(
        ("quota", "expected"),
        [pytest.param(False, 60.0, id="一般失敗 60s"), pytest.param(True, 300.0, id="配額 300s")],
    )
    async def test_retry_backoff_seconds(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, quota: bool, expected: float
    ) -> None:
        """退避秒數以「sleep 被呼叫的值」驗,不真等(檔頭慣例)。

        402 走 `config.quota_backoff_secs`,其餘走 `_STREAK_RETRY_SECS`;最後一次
        嘗試後不再睡(直接放棄)→ 10 次嘗試對應 9 段退避。
        """
        sleeps: list[float] = []

        async def _fake_sleep(secs: float) -> None:
            sleeps.append(secs)

        monkeypatch.setattr(be.asyncio, "sleep", _fake_sleep)
        daily = FakeDaily({})
        daily.error = BreadthFetchError("down", quota=quota)
        engine, *_ = _make(tmp_path, daily=daily)

        await engine._compute_streaks_loop()

        assert sleeps == [expected] * (be._STREAK_MAX_ATTEMPTS - 1)

    async def test_unexpected_exception_retries_and_survives(
        self, tmp_path: Path, fast_streaks: None
    ) -> None:
        """注入的取數層不保證只丟 BreadthFetchError;漏接會讓 task 當場死透。"""
        daily = FakeDaily(_calendar({"2026-08-04": ("1101",)}))
        daily.error = RuntimeError("boom")

        def _heal(n: int) -> None:
            if n >= 3:
                daily.error = None

        daily.on_call = _heal
        engine, *_ = _make(tmp_path, daily=daily)

        await engine._compute_streaks_loop()

        assert engine._streaks == {"1101": 1}
        assert engine._streak_attempts == 3

    async def test_close_cancels_streak_task(self, tmp_path: Path) -> None:
        """`close()` 一併收攤 streak task(與 poll task 同款),否則 shutdown 掛著孤兒。"""
        daily = FakeDaily({})
        daily.error = BreadthFetchError("down")
        engine, *_ = _make(tmp_path, daily=daily)

        engine._maybe_arm_streaks()
        task = engine._streak_task
        assert task is not None
        await _wait_until(lambda: len(daily.calls) >= 1)

        await engine.close()

        assert task.done()
        assert engine._streak_task is None


class TestStreakCache:
    async def test_restore_same_day_does_not_refetch(
        self, tmp_path: Path, fast_streaks: None
    ) -> None:
        """同日第二次啟動不打 FinMind —— restore 命中即視同**已武裝**(SC-2 的機制)。"""
        _write_streaks_cache(tmp_path)
        daily = FakeDaily(_calendar({"2026-08-04": ("1101",)}))
        engine, *_ = _make(tmp_path, daily=daily, config=BreadthConfig(poll_secs=0.01))

        await engine.start()
        try:
            await _wait_until(lambda: engine.state()["counts"] is not None)
            await asyncio.sleep(0.1)  # 夠跑約 10 圈武裝檢查
        finally:
            await engine.close()

        assert daily.calls == []
        assert engine._streak_armed_day == _TRADE_DATE
        assert engine._streaks == {"1101": 3}
        assert engine._streaks_day == _TRADE_DATE
        assert engine._streaks_end == "2026-08-04"
        assert engine._streaks_span == 3
        assert engine._streaks_skipped == {"2026-08-02", "2026-08-01"}

    async def test_start_does_not_start_streak_task(
        self, tmp_path: Path, fast_streaks: None
    ) -> None:
        """start() 維持零網路 IO:streak task 由 poll loop 的武裝檢查起(時間閘一致)。"""
        daily = FakeDaily(_calendar({"2026-08-04": ("1101",)}))
        engine, *_ = _make(
            tmp_path,
            daily=daily,
            config=BreadthConfig(poll_secs=60.0),
            clock=Clock(now="03:00:00"),
        )

        await engine.start()
        try:
            assert daily.calls == []
            assert engine._streak_task is None
        finally:
            await engine.close()

    @pytest.mark.parametrize(
        "kwargs",
        [
            pytest.param({"computed_for": "2026-08-04"}, id="computed_for 非今日"),
            pytest.param({"version": 99}, id="版本不符"),
            pytest.param({"data_end": 20260804}, id="data_end 非 str"),
            pytest.param({"streaks": ["1101"]}, id="streaks 非 dict"),
        ],
    )
    async def test_restore_rejects_unusable_cache(self, tmp_path: Path, kwargs: dict) -> None:
        """不合用的快取一律當沒有(今日重算),不半採用 —— 錯的連板數比沒有更糟。"""
        _write_streaks_cache(tmp_path, **kwargs)
        engine, *_ = _make(tmp_path, daily=FakeDaily({}))

        engine._restore_streaks()

        assert engine._streaks == {} and engine._streaks_day is None
        assert engine._streak_armed_day is None

    async def test_restore_bad_json_is_never_raise(self, tmp_path: Path) -> None:
        _streaks_file(tmp_path).write_text("not json at all", encoding="utf-8")
        engine, *_ = _make(tmp_path, daily=FakeDaily({}))

        engine._restore_streaks()

        assert engine._streaks_day is None and engine._streak_armed_day is None

    async def test_new_day_rearms_and_replaces_stale_result(
        self, tmp_path: Path, fast_streaks: None
    ) -> None:
        """換日:先清舊成果再重算 —— 昨日那份留著會讓連板數整天多算一板(R9/R13)。

        情境刻意選「restore 命中、streak task 從未存在」:守門若寫成 `task.done()`
        而沒有 `task is None` 分支,這條路永遠武裝不了。
        """
        _write_streaks_cache(tmp_path)
        daily = FakeDaily(_calendar({"2026-08-05": ("1101",), "2026-08-04": ("1101",)}))
        engine, _s, _i, _d, clock = _make(tmp_path, daily=daily)
        engine._restore_streaks()
        assert engine._streak_task is None and engine._streaks == {"1101": 3}

        clock.today = _dt.date(2026, 8, 6)
        clock.now = _dt.datetime(2026, 8, 6, 6, 30)
        engine._maybe_arm_streaks()

        # 起 task 的同一個同步區塊內就得清空:舊值不得在重算完成前被當今日的答案
        assert engine._streaks == {} and engine._streaks_day is None
        assert engine._streaks_end is None and engine._streaks_span == 0
        assert engine._streaks_skipped == set()
        assert engine._streak_attempts == 0
        assert engine._streak_armed_day == "2026-08-06"
        task = engine._streak_task
        assert task is not None
        await task

        assert engine._streaks == {"1101": 2}
        assert engine._streaks_day == "2026-08-06"
        assert engine._streaks_end == "2026-08-05"
        assert _streaks_file(tmp_path, "2026-08-06").exists()

    async def test_save_oserror_degrades_only(
        self,
        tmp_path: Path,
        fast_streaks: None,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """落檔失敗只降級:記憶體成果照在(重啟才會重算),不得讓整輪失敗。"""

        def _boom(*_a: object, **_k: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(be.os, "replace", _boom)
        daily = FakeDaily(_calendar({"2026-08-04": ("1101",)}))
        engine, *_ = _make(tmp_path, daily=daily)

        with caplog.at_level("WARNING"):
            assert await engine._compute_streaks_once() is True

        assert engine._streaks == {"1101": 1}
        assert not _streaks_file(tmp_path).exists()
        assert any("落檔失敗" in r.getMessage() for r in caplog.records)
