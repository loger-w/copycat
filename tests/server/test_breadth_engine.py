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
import logging
import threading
import time as _time
from pathlib import Path
from typing import Any, Callable

import pytest

import copycat.server.breadth_engine as be
from copycat.breadth_config import BreadthConfig
from copycat.server.breadth_fetch import BreadthFetchError
from copycat.server.chain_store import load_chain, save_chain
from copycat.server.signal_hub import SignalHub
from copycat.signals_config import SignalsConfig

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
    chain: Callable[[str], list[dict]] | None = None,
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
        chain_fetch=chain,
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


def _eod_rows(day: str, limit_ups: tuple[str, ...] = (), *, pad: int = 3) -> list[dict]:
    """單日 EOD 造值:`limit_ups` 每檔一列**剛好漲停**,其餘為平盤墊列。

    前收 = `close − spread` = 10.0 → 漲停 11.0(tick 0.05,10% 整除)。墊列只為
    撐過 `_DAILY_MIN_ROWS` 健檢,代號取 9000 段避免與被判股撞號。

    `day` 進 `date` 欄 —— 真回應(`TaiwanStockPrice`)每列都帶資料日,而引擎以
    `rows[0]["date"]` 做回聲檢查;fake 少這一欄就跟真回應脫節(review R3-T3)。
    """
    rows: list[dict] = [
        {"date": day, "stock_id": sid, "close": 11.0, "spread": 1.0} for sid in limit_ups
    ]
    rows += [
        {"date": day, "stock_id": f"{9000 + i}", "close": 10.0, "spread": 0.0}
        for i in range(pad)
    ]
    return rows


def _calendar(days: dict[str, tuple[str, ...]]) -> dict[str, list[dict]]:
    """{交易日: 該日漲停代號} → FakeDaily 的 calendar(不在鍵內的日期 = 假日空回應)。"""
    return {day: _eod_rows(day, sids) for day, sids in days.items()}


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

    async def test_streaks_armed_outside_window_via_poll_loop(
        self, tmp_path: Path, fast_streaks: None
    ) -> None:
        """**窗外**(06:30,poll 窗 08:55–13:40)照樣武裝 —— 走真的 `start()` + poll loop。

        連板重算刻意排在盤前:`_maybe_arm_streaks()` 在傘罩**內**、窗 gate **外**。
        直接呼叫 `_maybe_arm_streaks()` 的既有測試驗的是那個方法自己,對「它掛在迴圈的
        哪一層」零覆蓋 —— 把它移進 `if first or self._in_window():` 之後,連板數會退化成
        「只有盤中才可能算」,而盤中算出來的是**當天已在漲的**那份,設計上就是錯的。

        mutation 鎖靠時序:起跑時 05:30 < `_STREAK_ARM_TIME`(06:00)→ 首圈那次
        `first=True` 也武裝不了;等時鐘推到 06:30(仍在窗外)之後,只有窗 gate 之外的
        呼叫點還會執行 → 移進 gate 內本測試必逾時。
        """
        daily = FakeDaily(_calendar({d: ("1101",) for d in _TRADING_DAYS}))
        engine, snap, _i, _d, clock = _make(
            tmp_path,
            daily=daily,
            clock=Clock(now="05:30:00"),
            config=BreadthConfig(poll_secs=0.01),
        )

        await engine.start()
        try:
            await _wait_until(lambda: snap.calls >= 1)  # 首圈(無條件)已跑過
            assert engine._streak_armed_day is None  # 05:30 未到武裝時刻
            assert daily.calls == []

            clock.now = _dt.datetime.fromisoformat(f"{_TRADE_DATE} 06:30:00")
            await _wait_until(lambda: engine._streaks_day == _TRADE_DATE)
        finally:
            await engine.close()

        assert engine._in_window() is False  # 06:30 確實在 poll 窗外
        assert engine._streak_armed_day == _TRADE_DATE
        assert daily.calls != []
        assert engine._streaks == {"1101": 10}

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
        short = _eod_rows("2026-08-04", ("1101",), pad=be._DAILY_MIN_ROWS - 2)
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
        exact = _eod_rows("2026-08-04", ("1101",), pad=be._DAILY_MIN_ROWS - 1)
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

    async def test_leading_gap_beyond_limit_is_not_adopted(
        self, tmp_path: Path, fast_streaks: None
    ) -> None:
        """**前緣**間距(today ↔ dates[0])同樣要檢查(review R3-BE-1)。

        相鄰兩日的間距檢查只覆蓋窗**內部**:上游把最近 N 個交易日整段丟掉時,收到的
        序列自己是連續的(內部間距全 1),但它止於兩週前 —— 交集遞進照樣成功、成果照樣
        被當日快取固化,而盤中判式仍以 `rows_date > data_end` 分支 +1,連板數靜默少計
        整段。夾在中間的那些真交易日一個訊號都不會發。
        """
        daily = FakeDaily(_calendar({"2026-07-22": ("1101",), "2026-07-21": ("1101",)}))
        engine, *_ = _make(tmp_path, daily=daily)  # today = 2026-08-05 → 前緣 14 日

        assert await engine._compute_streaks_once() is False

        assert engine._streaks_day is None
        assert not _streaks_file(tmp_path).exists()

    async def test_leading_gap_at_limit_is_adopted(
        self, tmp_path: Path, fast_streaks: None
    ) -> None:
        """前緣門檻與內部同一個常數且**含等值**:剛好 12 日仍採用(邊界另一側)。"""
        daily = FakeDaily(_calendar({"2026-07-24": ("1101",)}))
        engine, *_ = _make(tmp_path, daily=daily)  # today − 2026-07-24 = 12 日

        assert await engine._compute_streaks_once() is True

        assert engine._streaks == {"1101": 1}

    async def test_wrong_date_echo_fails_whole_round(
        self, tmp_path: Path, fast_streaks: None
    ) -> None:
        """回應的資料日與請求日不符 → 該日視同取數失敗 → 整輪重試(review R3-T3)。

        `TaiwanStockPrice` 是 start_date/end_date 查詢,參數被忽略或回到別日的快取時,
        回應形狀完全合法(列數也夠)—— 沒有回聲檢查的話,別日的漲停集合會被當成該日的
        答案填進窗裡,連板數錯著且被當日快取固化,整天不會再重算。
        """
        daily = FakeDaily({"2026-08-04": _eod_rows("2026-07-31", ("1101",))})
        engine, *_ = _make(tmp_path, daily=daily)

        assert await engine._compute_streaks_once() is False

        assert engine._streaks_day is None
        assert daily.calls == ["2026-08-04"]  # 立即中止,不繼續往回掃
        assert not _streaks_file(tmp_path).exists()

    async def test_zero_limitup_day_logs_warning(
        self, tmp_path: Path, fast_streaks: None, caplog: pytest.LogCaptureFixture
    ) -> None:
        """全市場單日零漲停極罕見(多半是 close/spread 欄位語意變了)—— 不中斷,但要
        留下觀測訊號:否則連板欄整片空白與「今天真的沒人漲停」完全同形。"""
        daily = FakeDaily(_calendar({"2026-08-04": ()}))
        engine, *_ = _make(tmp_path, daily=daily)

        with caplog.at_level("WARNING"):
            assert await engine._compute_streaks_once() is True

        assert engine._streaks == {}
        assert any("零漲停" in r.getMessage() for r in caplog.records)


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

    async def test_retry_reuses_days_already_fetched(
        self, tmp_path: Path, fast_streaks: None
    ) -> None:
        """重試保留部分進度(review R3-BE-2)。

        每一日都是 MB 級回應,而重試是整輪從頭掃 —— 第 25 日才失敗的情境下,10 次
        嘗試會把前 24 日各重抓 10 遍(最壞 250 次 MB 級請求),配額燒光的表現是**整個**
        家數面板跟著死。memo 是武裝日內的,已成功取得的日不重取。
        """
        daily = FakeDaily(_calendar({d: ("1101",) for d in _TRADING_DAYS}))

        def _fail_third(n: int) -> None:
            daily.error = BreadthFetchError("upstream down") if n == 3 else None

        daily.on_call = _fail_third
        engine, *_ = _make(tmp_path, daily=daily)

        await engine._compute_streaks_loop()

        assert engine._streaks == {"1101": 10}
        assert engine._streak_attempts == 2
        # 前兩日在 attempt 1 就取到了 → attempt 2 直接重用,不再打上游
        assert daily.calls.count("2026-08-04") == 1
        assert daily.calls.count("2026-08-03") == 1
        assert daily.calls.count("2026-08-02") == 2  # 失敗那日照樣重取

    async def test_success_after_midnight_aligns_armed_day(
        self, tmp_path: Path, fast_streaks: None
    ) -> None:
        """跨午夜完成 → `_streak_armed_day` 對齊**成果日**(review R3-BE-3)。

        attempt 1 掃到一半換日 → 丟棄(R3);attempt 2 以 D+1 為基準成功。此時
        `_streaks_day` 是 D+1 而 `_streak_armed_day` 還停在 D —— 下一圈武裝檢查看到
        「今日尚未武裝」,會把剛算好的成果整組清掉再全掃一次(白燒一輪 25 次 MB 級
        請求,期間連板欄全 null)。
        """
        daily = FakeDaily(_calendar({"2026-08-05": ("1101",), "2026-08-04": ("1101",)}))
        engine, _s, _i, _d, clock = _make(tmp_path, daily=daily, clock=Clock(now="06:30:00"))

        def _roll(n: int) -> None:
            if n == 1:
                clock.today = _dt.date(2026, 8, 6)
                clock.now = _dt.datetime(2026, 8, 6, 6, 30)

        daily.on_call = _roll
        engine._maybe_arm_streaks()
        task = engine._streak_task
        assert task is not None
        await task

        assert engine._streaks == {"1101": 2}
        assert engine._streaks_day == "2026-08-06"
        assert engine._streak_armed_day == "2026-08-06"

        calls = len(daily.calls)
        engine._maybe_arm_streaks()  # 下一圈 poll

        assert engine._streaks == {"1101": 2}  # 成果沒被清掉
        assert len(daily.calls) == calls

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
            pytest.param({"dates": []}, id="dates 空"),
            pytest.param(
                {"dates": ["2026-08-03", "2026-08-04"]}, id="dates[0] 與 data_end 不符"
            ),
            pytest.param({"dates": ["2026-08-04", 20260803]}, id="dates 含非 str"),
        ],
    )
    async def test_restore_rejects_unusable_cache(self, tmp_path: Path, kwargs: dict) -> None:
        """不合用的快取一律當沒有(今日重算),不半採用 —— 錯的連板數比沒有更糟。

        後三例是 review R3-BE-4:`dates` 是 `_streaks_span`(封頂判定的分母)與
        `data_end`(盤中 +1 判定的基準)的唯一來源,逐項過濾後**不驗自洽**就採用,
        會讓一份半壞的快取整天生效。
        """
        _write_streaks_cache(tmp_path, **kwargs)
        engine, *_ = _make(tmp_path, daily=FakeDaily({}))

        engine._restore_streaks()

        assert engine._streaks == {} and engine._streaks_day is None
        assert engine._streak_armed_day is None

    async def test_restore_empty_dates_does_not_flag_every_row_capped(
        self, tmp_path: Path
    ) -> None:
        """`dates: []` 的快取:`_streaks_span` = 0 → `prev >= span` 恆真 → **每一列**
        漲停都被標成「N+ 板」封頂(review R3-BE-4)。

        形狀檢查擋在採用之前才是誠實的降級:整片 null(不知道)勝過整片假封頂。
        """
        _write_streaks_cache(tmp_path, dates=[], streaks={"1101": 2})
        engine, *_ = _make(tmp_path, daily=FakeDaily({}))
        engine._restore_streaks()

        await engine._run_cycle()
        state = engine.rows_state()

        assert state["streaks_ready"] is False
        assert _row_of(state, "1101")["streak"] is None
        assert _row_of(state, "1101")["streak_capped"] is False

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
        # 綁區域變數再斷言:直接對 `engine._streak_task` 斷言 is None 會讓 pyright 把
        # 那個 member expression 一路窄化成 None,後面的 `await task` 就變成 await Never
        restored_task = engine._streak_task
        assert restored_task is None and engine._streaks == {"1101": 3}

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
# ---------------------------------------------------------------------------
# rows_state():連板算術與 rows 同源日(design §3.3 code block;R1/R14/R15)
# ---------------------------------------------------------------------------


def _row_of(state: dict, sid: str) -> dict:
    return next(r for r in state["rows"] if r["stock_id"] == sid)


class TestRowsState:
    async def test_shape_before_first_cycle(self, tmp_path: Path) -> None:
        """引擎在、首輪未成:契約欄位齊全,`as_of` 為 None(前端據它判「載入中」)。"""
        engine, *_ = _make(tmp_path, daily=FakeDaily({}))

        assert engine.rows_state() == {
            "enabled": True,
            "trade_date": None,
            "as_of": None,
            "stale": True,
            "streaks_ready": False,
            "rows": [],
        }

    async def test_streak_null_until_ready(self, tmp_path: Path) -> None:
        """streak 未就緒(含 `daily_fetch=None` 停用)→ 每列 null,不是 0 也不是猜值。"""
        engine, *_ = _make(tmp_path)

        await engine._run_cycle()
        state = engine.rows_state()

        assert state["streaks_ready"] is False
        assert state["trade_date"] == _TRADE_DATE
        assert all(
            r["streak"] is None and r["streak_capped"] is False for r in state["rows"]
        )
        assert len(state["rows"]) == 4

    async def test_intraday_rows_add_today_and_keep_row_fields(
        self, tmp_path: Path
    ) -> None:
        """rows 是今日盤中(rows_date > data_end)→ 昨日止的 streak + 今日這根。

        同時釘住 merge 是**加欄不改欄**:原本的 rows 欄位一個不漏地原樣帶出去。
        """
        _write_streaks_cache(tmp_path, streaks={"1101": 2})
        engine, *_ = _make(tmp_path, daily=FakeDaily({}))
        engine._restore_streaks()

        await engine._run_cycle()
        state = engine.rows_state()

        assert state["streaks_ready"] is True
        assert state["trade_date"] == _TRADE_DATE
        assert _row_of(state, "1101") == {
            "stock_id": "1101",
            "name": "台泥",
            "market": "twse",
            "close": 11.0,
            "change_rate": 10.0,
            "volume_ratio": 2.0,
            "total_amount": 12_345,
            "limit_up": True,
            "limit_down": False,
            "limit_judged": True,
            "touched_limit_up": False,
            "touched_limit_down": False,
            "streak": 3,
            "streak_capped": False,
        }
        # 非漲停列一律 null(跌停的 6488 也不例外 —— 連板只描述漲停)
        assert _row_of(state, "6488")["streak"] is None
        assert _row_of(state, "2330")["streak"] is None

    async def test_previous_session_snapshot_does_not_add_one(
        self, tmp_path: Path
    ) -> None:
        """rows 是**上一交易日收盤快照**(盤前 / 假日開站)→ 該日已在 streak 內,不 +1。

        這是 R1 的核心:前端 +1 的舊設計在這條路上會憑空多一板,而畫面看起來完全正常。
        """
        _write_streaks_cache(
            tmp_path,
            computed_for="2026-08-06",
            data_end=_TRADE_DATE,
            dates=[_TRADE_DATE, "2026-08-04", "2026-08-03"],
            streaks={"1101": 3},
            file_day="2026-08-06",
        )
        engine, *_ = _make(
            tmp_path,
            snapshot=FakeFetch(_snapshot_rows(f"{_TRADE_DATE} 13:30:00")),
            daily=FakeDaily({}),
            clock=Clock(today="2026-08-06"),
        )
        engine._restore_streaks()

        await engine._run_cycle()
        state = engine.rows_state()

        assert state["trade_date"] == _TRADE_DATE
        assert _row_of(state, "1101")["streak"] == 3
        assert _row_of(state, "1101")["streak_capped"] is True  # prev 撞上 span=3

    async def test_previous_session_snapshot_floors_at_one(self, tmp_path: Path) -> None:
        """`rows_date == data_end` 且該檔不在 streak 表(prev = 0)→ 下界 1(review R3-T2)。

        該日**已在** streak 窗內,所以不 +1;但它自己就是一根漲停,回 0 說不通。
        `max(prev, 1)` 的下界原本零覆蓋:寫成 `prev` 的 mutation 全綠,而畫面上會是
        「漲停 0 板」—— 比 null 更誤導(看起來像個真數字)。
        """
        _write_streaks_cache(
            tmp_path,
            computed_for="2026-08-06",
            data_end=_TRADE_DATE,
            dates=[_TRADE_DATE, "2026-08-04", "2026-08-03"],
            streaks={},  # 1101 不在表內 → prev = 0
            file_day="2026-08-06",
        )
        engine, *_ = _make(
            tmp_path,
            snapshot=FakeFetch(_snapshot_rows(f"{_TRADE_DATE} 13:30:00")),
            daily=FakeDaily({}),
            clock=Clock(today="2026-08-06"),
        )
        engine._restore_streaks()

        await engine._run_cycle()
        state = engine.rows_state()

        assert state["streaks_ready"] is True
        assert _row_of(state, "1101")["streak"] == 1
        assert _row_of(state, "1101")["streak_capped"] is False  # prev 0 < span 3

    async def test_uses_rows_date_not_trade_date(self, tmp_path: Path) -> None:
        """`adopt_date=False` 路徑:`_trade_date` 與 rows 脫鉤 → 判式必須用 `_rows_date`。

        第二輪拿到的快照日既非今日也非序列日 → 日期變更不採用(`_trade_date` 停在
        08-05),但 `self.rows` 已經換成 08-04 那份。用 `_trade_date` 判會得到
        「08-05 > data_end 08-04」→ 多一板,而畫面與 counts 全部正常(R14)。
        """
        _write_streaks_cache(tmp_path, streaks={"1101": 3})
        engine, snap, *_ = _make(tmp_path, daily=FakeDaily({}))
        engine._restore_streaks()
        await engine._run_cycle()
        assert _row_of(engine.rows_state(), "1101")["streak"] == 4  # 盤中:3 + 今日

        snap.rows = _snapshot_rows("2026-08-04 13:30:00")
        await engine._run_cycle()
        state = engine.rows_state()

        assert engine._trade_date == _TRADE_DATE  # 日期變更不採用(序列保護)
        assert state["trade_date"] == "2026-08-04"  # 但 payload 與 rows 同源
        assert _row_of(state, "1101")["streak"] == 3  # 不是 4

    async def test_rows_date_in_skipped_is_null(self, tmp_path: Path) -> None:
        """rows 的資料日在掃描時被當假日跳過 → 兩者關係不明,誠實回 null(R15)。

        沒有這道 guard 時它會走 `rows_date > data_end` 分支 +1 —— 而那一天到底有沒有
        漲停過根本不知道(FinMind 當時回空)。
        """
        _write_streaks_cache(
            tmp_path,
            data_end="2026-08-03",
            dates=["2026-08-03", "2026-07-31", "2026-07-30"],
            skipped=["2026-08-04", "2026-08-02", "2026-08-01"],
            streaks={"1101": 3},
        )
        engine, snap, *_ = _make(tmp_path, daily=FakeDaily({}))
        engine._restore_streaks()
        snap.rows = _snapshot_rows("2026-08-04 13:30:00")

        await engine._run_cycle()
        state = engine.rows_state()

        assert state["streaks_ready"] is True
        assert state["trade_date"] == "2026-08-04"
        assert _row_of(state, "1101")["streak"] is None

    async def test_streaks_from_other_day_are_not_ready(self, tmp_path: Path) -> None:
        """成果是為別的 today 算的(00:00–06:00 之間 / 換日未重算完)→ 整片 null。"""
        _write_streaks_cache(tmp_path, streaks={"1101": 2})
        engine, _s, _i, _d, clock = _make(tmp_path, daily=FakeDaily({}))
        engine._restore_streaks()
        await engine._run_cycle()

        clock.today = _dt.date(2026, 8, 6)
        state = engine.rows_state()

        assert state["streaks_ready"] is False
        assert _row_of(state, "1101")["streak"] is None


# ---------------------------------------------------------------------------
# 產業鏈快取刷新 + 類股輪動掛點(R4 design §4.3 / §5)
# ---------------------------------------------------------------------------

#: chain fixture 只涵蓋 universe 內的三檔(2317 刻意不入鏈 —— 未涵蓋的股不該
#: 憑空長出產業);2330 / 6488 同產業不同次產業,用來釘 industry 層的聯集語意。
_CHAIN_ROWS: list[dict] = [
    {"stock_id": "2330", "industry": "半導體", "sub_industry": "晶圓代工"},
    {"stock_id": "6488", "industry": "半導體", "sub_industry": "矽晶圓"},
    {"stock_id": "1101", "industry": "水泥", "sub_industry": "水泥製造"},
]
_CHAIN_MAP: dict[str, dict[str, list[str]]] = {
    "半導體": {"晶圓代工": ["2330"], "矽晶圓": ["6488"]},
    "水泥": {"水泥製造": ["1101"]},
}


def _chain_file(tmp_path: Path) -> Path:
    return tmp_path / "industry_chain.json"


class HangingFetch:
    """在 worker thread 內真的卡住的取數替身 —— 驗 poll loop 不 await chain task。

    「不阻塞」不能用快 fake 驗:快 fake 之下即使把 `await` 寫進 poll loop,家數輪
    照樣跑得動,測試全綠而 §1 的失效域宣稱是假的。要卡住才測得到。
    """

    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.calls = 0
        self.release = threading.Event()

    def __call__(self, token: str) -> list[dict]:
        self.calls += 1
        self.release.wait(5.0)
        return self.rows


async def _arm_chain(engine: Any) -> None:
    """武裝一次並等 chain task 收工(引擎本身絕不 await 它 —— 那是 poll loop 的紀律)。

    武裝條件不成立時 `_chain_task` 可能是上一輪留下的 done task,await 無副作用;
    「這次到底有沒有真的去打上游」一律以取數替身的 `calls` 為準。
    """
    engine._maybe_arm_chain()
    task = engine._chain_task
    if task is not None:
        await task


async def _ready_engine(tmp_path: Path) -> Any:
    """chain 表就緒 + 跑完一輪家數的引擎(rotation 掛點的前置)。"""
    engine, *_ = _make(tmp_path, chain=FakeFetch(list(_CHAIN_ROWS)))
    await _arm_chain(engine)
    await engine._run_cycle()
    return engine


class TestChainCache:
    async def test_start_loads_expired_cache_without_network(self, tmp_path: Path) -> None:
        """start() 讀本地 chain 快取 —— **過期也先用**(stale 勝於無),且零網路 IO。

        過期就不載入的話,冷啟動到首次刷新完成之間類股面板整片空白,而那段空白與
        「FinMind 掛了」完全同形。
        """
        save_chain(_chain_file(tmp_path), list(_CHAIN_ROWS), 0.0)  # epoch 0 = 遠古
        chain = FakeFetch([])
        engine, *_ = _make(tmp_path, chain=chain, config=BreadthConfig(poll_secs=60.0))

        await engine.start()
        try:
            assert engine._chain_map == _CHAIN_MAP
            assert engine._chain_fetched_at == 0.0
            assert chain.calls == 0
        finally:
            await engine.close()

    async def test_fresh_cache_within_ttl_not_refetched(self, tmp_path: Path) -> None:
        """TTL(7 天)內不重打:chain 是一天最多幾次的重表,不該跟著 poll 節奏走。"""
        save_chain(_chain_file(tmp_path), list(_CHAIN_ROWS), _time.time())
        chain = FakeFetch(list(_CHAIN_ROWS))
        engine, *_ = _make(tmp_path, chain=chain)
        engine._restore_chain()

        await _arm_chain(engine)

        assert engine._chain_task is None
        assert chain.calls == 0

    async def test_expired_arms_task_then_swaps_and_saves(self, tmp_path: Path) -> None:
        """從未成功(冷啟動無快取)→ 武裝 → 成功即換表 + 落檔;之後 TTL 內不再打。"""
        chain = FakeFetch(list(_CHAIN_ROWS))
        engine, *_ = _make(tmp_path, chain=chain)

        await _arm_chain(engine)

        assert chain.calls == 1
        assert engine._chain_map == _CHAIN_MAP
        fetched_at = engine._chain_fetched_at
        assert fetched_at is not None
        assert load_chain(_chain_file(tmp_path)) == (_CHAIN_ROWS, fetched_at)

        await _arm_chain(engine)
        assert chain.calls == 1  # TTL 內

    async def test_fetch_failure_keeps_old_map_and_backs_off(
        self, tmp_path: Path, mono: FakeMono
    ) -> None:
        """取數失敗 → 沿用舊表 + 60s 退避;退避內不重打(壞上游不跟著 poll 節奏燒配額)。"""
        save_chain(_chain_file(tmp_path), list(_CHAIN_ROWS), 0.0)
        chain = FakeFetch([])
        chain.error = BreadthFetchError("chain down")
        engine, *_ = _make(tmp_path, chain=chain)
        engine._restore_chain()

        await _arm_chain(engine)
        assert chain.calls == 1
        assert engine._chain_map == _CHAIN_MAP  # 沿用舊表,不清空

        mono.advance(be._MAP_RETRY_SECS - 1.0)
        await _arm_chain(engine)
        assert chain.calls == 1  # 退避中

        mono.advance(2.0)
        chain.error = None
        chain.rows = list(_CHAIN_ROWS)
        await _arm_chain(engine)
        assert chain.calls == 2
        assert engine._chain_fetched_at != 0.0  # 成功才刷時戳

    async def test_quota_failure_uses_quota_backoff(self, tmp_path: Path, mono: FakeMono) -> None:
        """402 = 配額用盡 → 走 `quota_backoff_secs`(300s),不是一般 60s。"""
        chain = FakeFetch([])
        chain.error = BreadthFetchError("配額用盡", quota=True)
        engine, *_ = _make(tmp_path, chain=chain)

        await _arm_chain(engine)
        assert chain.calls == 1

        mono.advance(299.0)
        await _arm_chain(engine)
        assert chain.calls == 1

        mono.advance(2.0)
        await _arm_chain(engine)
        assert chain.calls == 2

    async def test_empty_parse_keeps_old_map_and_file(
        self, tmp_path: Path, mono: FakeMono
    ) -> None:
        """取數成功但 parse 後為空 → **不換表、不落檔、不刷時戳**,rotation 仍有值(R6)。

        欄位語意變更(或上游回一份殘表)時 `rows_to_chain_map` 會整份丟成空 dict:
        照樣換表的話,一份可用的舊快取會被空表覆寫**並固化到磁碟**,重啟後連 stale
        的類股資料都沒有,而畫面上只是「類股資料未就緒」零錯誤訊號。
        """
        save_chain(_chain_file(tmp_path), list(_CHAIN_ROWS), 0.0)
        before = _chain_file(tmp_path).read_text(encoding="utf-8")
        chain = FakeFetch([{"stock_id": "2330", "industry": "半導體"}])  # 缺 sub → 整列丟
        engine, *_ = _make(tmp_path, chain=chain)
        engine._restore_chain()

        await _arm_chain(engine)

        assert chain.calls == 1
        assert engine._chain_map == _CHAIN_MAP
        assert engine._chain_fetched_at == 0.0
        assert _chain_file(tmp_path).read_text(encoding="utf-8") == before

        mono.advance(be._MAP_RETRY_SECS - 1.0)
        await _arm_chain(engine)
        assert chain.calls == 1  # 空表同樣走退避

        await engine._run_cycle()
        assert engine.sector_state()["rotation"] is not None  # 舊表照樣算得出來

    async def test_parse_crash_keeps_old_map_and_backs_off(
        self, tmp_path: Path, mono: FakeMono, caplog: pytest.LogCaptureFixture
    ) -> None:
        """parse 炸掉(髒值打穿 `rows_to_chain_map`)→ 沿用舊表 + 退避,不外拋(review S-3)。

        `_refresh_chain` 是 fire-and-forget task 的身體:逃出去的例外只會變成 asyncio
        的「Task exception was never retrieved」,而 `_chain_retry_at` 沒設 → 下一圈
        立刻重武裝、以 poll 節奏(10s)對著壞上游重打,類股面板停在舊表上零錯誤訊號。
        """
        save_chain(_chain_file(tmp_path), list(_CHAIN_ROWS), 0.0)
        # 形狀合法(是 dict)但 industry 不可雜湊 → setdefault 當場 TypeError
        chain = FakeFetch([{"stock_id": "2330", "industry": ["半導體"], "sub_industry": "晶圓"}])
        engine, *_ = _make(tmp_path, chain=chain)
        engine._restore_chain()

        with caplog.at_level(logging.WARNING, logger="copycat.server.breadth_engine"):
            await _arm_chain(engine)

        assert chain.calls == 1
        assert engine._chain_map == _CHAIN_MAP  # 舊表原封不動
        assert engine._chain_fetched_at == 0.0
        assert engine._chain_retry_at is not None
        assert any(r.levelno >= logging.WARNING for r in caplog.records)

        mono.advance(be._MAP_RETRY_SECS - 1.0)
        await _arm_chain(engine)
        assert chain.calls == 1  # 退避中不重打

    async def test_restore_parse_crash_treated_as_no_cache(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """快取檔 parse 炸 → 當作沒有快取(**不得外拋**:`_restore_chain` 在 boot 路徑)。

        一份壞快取檔讓整台 server 起不來的話,失效半徑從「類股面板」擴到「全部面板」。
        """
        save_chain(
            _chain_file(tmp_path),
            [{"stock_id": "2330", "industry": ["半導體"], "sub_industry": "晶圓"}],
            123.0,
        )
        engine, *_ = _make(tmp_path, chain=FakeFetch(list(_CHAIN_ROWS)))

        with caplog.at_level(logging.WARNING, logger="copycat.server.breadth_engine"):
            engine._restore_chain()

        assert engine._chain_map == {}
        assert engine._chain_fetched_at is None  # 視同無快取 → 下一圈立刻武裝
        assert any(r.levelno >= logging.WARNING for r in caplog.records)

    async def test_no_chain_fetch_disables_rotation(self, tmp_path: Path) -> None:
        """`chain_fetch=None` = 類股停用:不武裝、rotation 恆 null、members 恆 None。"""
        engine, *_ = _make(tmp_path)

        await _arm_chain(engine)
        await engine._run_cycle()

        assert engine._chain_task is None
        assert engine.sector_state()["rotation"] is None
        assert engine.sector_members("半導體", None) is None

    async def test_poll_loop_not_blocked_by_hanging_chain_fetch(self, tmp_path: Path) -> None:
        """chain 取數卡死 → 家數輪照跑(§1 失效域:類股壞不得拖慢家數)。

        `_maybe_arm_chain` 起的是 fire-and-forget task,poll loop 不 await 它;
        寫成 `await self._refresh_chain()` 的話這裡會停在 chain.calls == 1 那一刻,
        整片家數面板跟著卡住而唯一的肇因只是類股這條旁支。
        """
        chain = HangingFetch(list(_CHAIN_ROWS))
        engine, snap, *_ = _make(tmp_path, chain=chain, config=BreadthConfig(poll_secs=0.01))

        await engine.start()
        try:
            await _wait_until(lambda: snap.calls >= 3)
            assert chain.calls == 1  # 卡住的 task 不重複武裝
            task = engine._chain_task
            assert task is not None and not task.done()
        finally:
            chain.release.set()
            await engine.close()

    async def test_close_cancels_chain_task(self, tmp_path: Path) -> None:
        """`close()` 一併收攤 chain task(與 poll / streak 同款),否則 shutdown 掛孤兒。"""
        chain = HangingFetch(list(_CHAIN_ROWS))
        engine, *_ = _make(tmp_path, chain=chain)
        engine._maybe_arm_chain()
        task = engine._chain_task
        assert task is not None
        try:
            await _wait_until(lambda: chain.calls >= 1)

            await engine.close()

            assert task.done()
            assert engine._chain_task is None
        finally:
            chain.release.set()

    async def test_chain_armed_via_poll_loop(self, tmp_path: Path) -> None:
        """武裝掛在 poll loop(與 streak 同一處)—— start() 本身仍零網路 IO。"""
        chain = FakeFetch(list(_CHAIN_ROWS))
        engine, *_ = _make(tmp_path, chain=chain, config=BreadthConfig(poll_secs=0.01))

        await engine.start()
        try:
            assert chain.calls == 0  # start() 不打上游
            await _wait_until(lambda: engine._chain_map != {})
        finally:
            await engine.close()

        assert engine._chain_map == _CHAIN_MAP


class TestSectorState:
    async def test_state_before_first_cycle(self, tmp_path: Path) -> None:
        """引擎在、首輪未成 → rotation null(前端「類股資料未就緒」的三態之一)。"""
        engine, *_ = _make(tmp_path, chain=FakeFetch(list(_CHAIN_ROWS)))

        assert engine.sector_state() == {
            "enabled": True,
            "trade_date": None,
            "as_of": None,
            "stale": True,
            "rotation": None,
        }

    async def test_rotation_and_universe_rows_after_cycle(self, tmp_path: Path) -> None:
        """`_apply` 成功 → rotation 與 universe_rows 同輪同源更新。

        手算(universe = 2330 +1.01 / 1101 +10.0 / 2317 0.0 / 6488 −10.0,每檔量
        1000、昨量 500):水泥 +10.00 排在半導體 (1.01 − 10.0)/2 之前;半導體
        industry 層是兩個 sub 的聯集(members 2),subs 各自 1 檔按 avg desc。
        2317 不在 chain 內 → 不長出產業。
        """
        engine = await _ready_engine(tmp_path)

        state = engine.sector_state()
        assert state["enabled"] is True
        assert state["trade_date"] == _TRADE_DATE
        assert state["as_of"] == "10:23:45"
        assert state["stale"] is False

        industries = state["rotation"]["industries"]
        assert [i["name"] for i in industries] == ["水泥", "半導體"]
        cement, semi = industries
        assert (cement["members"], cement["vol_ratio"]) == (1, 2.0)
        assert cement["avg_change_rate"] == pytest.approx(10.0)
        assert [s["name"] for s in cement["subs"]] == ["水泥製造"]
        assert semi["members"] == 2  # 聯集去重,不是兩個 sub 相加
        assert semi["avg_change_rate"] == pytest.approx(-4.495)
        assert semi["vol_ratio"] == pytest.approx(2.0)
        assert [s["name"] for s in semi["subs"]] == ["晶圓代工", "矽晶圓"]

        # universe_rows = members drill-down 的原料(compute_breadth 的 rows 已把量欄
        # 收成 volume_ratio,分子分母不可再同步剔除 → 必須是 universe 那份)
        assert {r["stock_id"] for r in engine._universe_rows} == {"2330", "1101", "2317", "6488"}
        assert "yesterday_volume" in engine._universe_rows[0]

    async def test_rotation_null_when_chain_missing(self, tmp_path: Path) -> None:
        """chain 表還沒到(首次刷新未完成)→ 家數照常,rotation null。"""
        engine, *_ = _make(tmp_path, chain=FakeFetch(list(_CHAIN_ROWS)))

        await engine._run_cycle()

        assert engine.state()["counts"] == _EXPECTED
        assert engine.sector_state()["rotation"] is None

    async def test_chain_arriving_after_cycle_recomputes_rotation(self, tmp_path: Path) -> None:
        """chain 換表發生在 `_run_cycle` **之後** → 當場重算 rotation(review C-1)。

        盤後首次部署(無 chain 快取)的真實順序就是這個:家數首輪先成、chain task
        幾秒後才換表。換表不重算的話 rotation 要等下一次 `_apply` —— 而窗外根本不會
        有下一輪,整晚 rotation 恆 null,與「chain 取數失敗」在畫面上完全同形。
        """
        chain = FakeFetch(list(_CHAIN_ROWS))
        engine, *_ = _make(tmp_path, chain=chain)

        await engine._run_cycle()
        assert engine.sector_state()["rotation"] is None  # 前置:chain 尚未到

        await _arm_chain(engine)  # 換表(**不再跑第二輪 cycle**)

        assert chain.calls == 1
        rotation = engine.sector_state()["rotation"]
        assert rotation is not None
        assert [i["name"] for i in rotation["industries"]] == ["水泥", "半導體"]

    async def test_chain_swap_before_first_cycle_keeps_rotation_none(
        self, tmp_path: Path
    ) -> None:
        """首輪未成(universe 空)時換表 → rotation 保持 **None**,不得變成空 industries。

        `{"industries": []}` 在前端是「產業都算得出來、只是沒有成員」;None 才是
        「類股資料未就緒」—— 兩句文案語意不同,而首輪未成時說的是後者。
        """
        engine, *_ = _make(tmp_path, chain=FakeFetch(list(_CHAIN_ROWS)))

        await _arm_chain(engine)

        assert engine._chain_map == _CHAIN_MAP  # 前置:表真的換上去了
        assert engine.sector_state()["rotation"] is None

    async def test_sector_members_known(self, tmp_path: Path) -> None:
        """成員 drill-down:名稱走 `_name_map`,按 change_rate desc。"""
        engine = await _ready_engine(tmp_path)

        assert engine.sector_members("半導體", None) == {
            "industry": "半導體",
            "sub_industry": None,
            "members": [
                {
                    "stock_id": "2330",
                    "name": "台積電",
                    "change_rate": 1.01,
                    "vol_ratio": 2.0,
                    "total_amount": 12_345,
                },
                {
                    "stock_id": "6488",
                    "name": "環球晶",
                    "change_rate": -10.0,
                    "vol_ratio": 2.0,
                    "total_amount": 12_345,
                },
            ],
        }

    async def test_sector_members_sub_narrows(self, tmp_path: Path) -> None:
        engine = await _ready_engine(tmp_path)

        result = engine.sector_members("半導體", "矽晶圓")

        assert result["sub_industry"] == "矽晶圓"
        assert [m["stock_id"] for m in result["members"]] == ["6488"]

    @pytest.mark.parametrize(
        ("industry", "sub"),
        [
            pytest.param("不存在", None, id="未知產業"),
            pytest.param("半導體", "不存在", id="未知次產業"),
            pytest.param("", None, id="空字串產業"),
        ],
    )
    async def test_sector_members_unknown_is_none(
        self, tmp_path: Path, industry: str, sub: str | None
    ) -> None:
        """查無 → None(呼叫端轉 404 SECTOR_NOT_FOUND),不是空 members。"""
        engine = await _ready_engine(tmp_path)

        assert engine.sector_members(industry, sub) is None


# ---------------------------------------------------------------------------
# 全市場鎖板事件 diff(R4 design §6 — SC-5)
# ---------------------------------------------------------------------------

#: 事件層讀到的鍵(`compute_breadth` rows_out 的子集)。**刻意不是快照 rows 的形狀** ——
#: 那正是 (i) 案要擋的東西:入參餵錯一份 rows,事件會整批靜默消失。
_LOCK_KIND = "market_limit_lock"
_OPEN_KIND = "market_limit_open"


def _row_out(
    sid: str,
    *,
    name: str = "台泥",
    close: float = 11.0,
    up: bool = False,
    down: bool = False,
    judged: bool = True,
) -> dict:
    """`compute_breadth` rows_out 的最小形狀(diff 只讀這幾鍵)。"""
    return {
        "stock_id": sid,
        "name": name,
        "close": close,
        "limit_up": up,
        "limit_down": down,
        "limit_judged": judged,
    }


class FakeHub:
    """訊號匯流排替身:收批次 + 供 seed(engine 對它的唯一兩個要求)。

    `market_event_state` 每次回**新 dict**:engine 會就地改那兩份(對帳狀態與計數),
    共用同一個物件的話,替身的 seed 會被受測物改掉而測試仍然綠。
    """

    def __init__(
        self,
        seed: dict[tuple[str, str], bool] | None = None,
        counts: dict[tuple[str, str, str], int] | None = None,
    ) -> None:
        self.seed: dict[tuple[str, str], bool] = seed if seed is not None else {}
        self.counts: dict[tuple[str, str, str], int] = counts if counts is not None else {}
        self.batches: list[tuple[list[dict], str]] = []
        self.state_calls: list[str] = []
        self.publish_error: Exception | None = None

    @property
    def events(self) -> list[dict]:
        return [e for batch, _ in self.batches for e in batch]

    def publish_market_events(self, events: list[dict], *, trade_date: str) -> None:
        if self.publish_error is not None:
            raise self.publish_error
        self.batches.append(([dict(e) for e in events], trade_date))

    def market_event_state(
        self, trade_date: str
    ) -> tuple[dict[tuple[str, str], bool], dict[tuple[str, str, str], int]]:
        self.state_calls.append(trade_date)
        return dict(self.seed), dict(self.counts)


def _real_hub(tmp_path: Path, published: list[dict]) -> SignalHub:
    """真 SignalHub(fake publish + tmp data_dir)—— id 文法與 jsonl seed 的端到端證據。"""

    async def _bars(code: str, days: int) -> list:
        return []

    return SignalHub(
        SignalsConfig(),
        publish=published.append,
        daily_bars=_bars,
        notify_fallback=lambda text: True,
        data_dir=tmp_path,
        trade_date_fn=lambda: _TRADE_DATE,
    )


def _write_market_jsonl(tmp_path: Path, rows: list[dict], day: str = _TRADE_DATE) -> Path:
    """前一個 process 留下的當日 jsonl(重啟 seed 的真實來源)。"""
    path = tmp_path / "signals" / f"{day.replace('-', '')}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps({**r, "trade_date": day}, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )
    return path


def _tuples(events: list[dict]) -> list[tuple]:
    return [(e["kind"], e["code"], e["direction"], e["time"], e["touch_count"]) for e in events]


class TestMarketLimitEvents:
    """對帳制(design §6.4):`last_emitted` 是「事件流已對外宣告的狀態」。

    不是 raw 轉移偵測 —— 那一式在「開盤即鎖」與「盤中重啟」兩個邊界都會靜默漏發,
    而漏發沒有任何觀測訊號(畫面就是少一列)。
    """

    async def test_lock_open_relock_emits_three_events(self, tmp_path: Path, mono: FakeMono) -> None:
        """(a) lock → open → relock 三轉移三則,每則五欄位正確。"""
        engine, *_ = _make(tmp_path)
        hub = FakeHub()
        engine.attach_signal_hub(hub)

        engine._diff_limit_events(_TRADE_DATE, [_row_out("1101", up=True)], "09:01:05")
        engine._diff_limit_events(_TRADE_DATE, [_row_out("1101")], "09:05:05")
        mono.advance(601.0)  # lock 桶冷卻已過
        engine._diff_limit_events(_TRADE_DATE, [_row_out("1101", up=True)], "09:20:05")

        assert _tuples(hub.events) == [
            (_LOCK_KIND, "1101", "up", "09:01:05", 1),
            (_OPEN_KIND, "1101", "up", "09:05:05", 1),
            (_LOCK_KIND, "1101", "up", "09:20:05", 2),  # 同桶第 2 次
        ]
        assert hub.events[0]["name"] == "台泥"
        assert hub.events[0]["price"] == 11_000  # 毫元
        assert len(hub.batches) == 3  # 每輪一批

    async def test_real_hub_gets_deterministic_id(self, tmp_path: Path) -> None:
        """(a-整合)真 SignalHub 接上 → id 文法端到端(`<日>-breadth-<code>-<kind>-<dir>-<time>`)。"""
        published: list[dict] = []
        hub = _real_hub(tmp_path, published)
        engine, *_ = _make(tmp_path)
        engine.attach_signal_hub(hub)

        engine._diff_limit_events(_TRADE_DATE, [_row_out("1101", up=True)], "09:01:05")

        assert [m["id"] for m in published] == [
            f"{_TRADE_DATE}-breadth-1101-{_LOCK_KIND}-up-09:01:05"
        ]
        assert published[0]["price"] == 11_000
        assert published[0]["touch_count"] == 1

    async def test_first_round_already_locked_emits_lock(self, tmp_path: Path) -> None:
        """(b) 開盤首輪(seed 空)已鎖的檔照發 —— 一價到底不再靜默(design R1 主修)。"""
        engine, *_ = _make(tmp_path)
        hub = FakeHub()
        engine.attach_signal_hub(hub)

        engine._diff_limit_events(
            _TRADE_DATE,
            [
                _row_out("1101", up=True),
                _row_out("6488", name="環球晶", close=9.0, down=True),
            ],
            "09:01:05",
        )

        assert hub.state_calls == [_TRADE_DATE]  # 首輪 seed 一次
        assert _tuples(hub.events) == [
            (_LOCK_KIND, "1101", "up", "09:01:05", 1),
            (_LOCK_KIND, "6488", "down", "09:01:05", 1),
        ]
        assert hub.events[1]["price"] == 9_000

    async def test_restart_seed_replays_jsonl(self, tmp_path: Path) -> None:
        """(c) 盤中重啟:既有 jsonl 回放 → 已發布的不重發,停機期轉移補發 open。

        seed 若空著(靜默 baseline),重啟後整片已鎖的檔會被當成新鎖再發一遍;
        seed 若當成「當下實況」,停機期間打開的那些檔就永遠不會有 open。
        """
        _write_market_jsonl(
            tmp_path,
            [
                {"id": "x1", "kind": _LOCK_KIND, "code": "2330", "direction": "up"},
                {"id": "x2", "kind": _LOCK_KIND, "code": "1101", "direction": "up"},
            ],
        )
        published: list[dict] = []
        hub = _real_hub(tmp_path, published)
        engine, *_ = _make(tmp_path)
        engine.attach_signal_hub(hub)

        engine._diff_limit_events(
            _TRADE_DATE,
            [
                _row_out("2330", name="台積電", close=100.0, up=True),  # 仍鎖 → 不重發
                _row_out("1101"),  # 停機期打開 → 補發 open
            ],
            "10:00:05",
        )

        assert [(m["code"], m["kind"], m["touch_count"]) for m in published] == [
            ("1101", _OPEN_KIND, 1)
        ]
        assert published[0]["time"] == "10:00:05"  # 帶當下時刻(jsonl 缺角自癒)

    async def test_cooldown_defers_reconciliation_not_drops(
        self, tmp_path: Path, mono: FakeMono
    ) -> None:
        """(d) 冷卻內抖動不丟棄:冷卻結束後 desired 仍不符 → 補發,終態收斂到實況。"""
        engine, *_ = _make(tmp_path)
        hub = FakeHub()
        engine.attach_signal_hub(hub)

        engine._diff_limit_events(_TRADE_DATE, [_row_out("1101", up=True)], "09:01:05")
        engine._diff_limit_events(_TRADE_DATE, [_row_out("1101")], "09:02:05")
        mono.advance(60.0)
        engine._diff_limit_events(_TRADE_DATE, [_row_out("1101", up=True)], "09:03:05")

        assert _tuples(hub.events) == [
            (_LOCK_KIND, "1101", "up", "09:01:05", 1),
            (_OPEN_KIND, "1101", "up", "09:02:05", 1),
        ]
        # 冷卻中那輪不得更新 last_emitted,否則對帳會停在「已宣告鎖定」而永不補發
        mono.advance(600.0)
        engine._diff_limit_events(_TRADE_DATE, [_row_out("1101", up=True)], "09:13:05")

        assert _tuples(hub.events)[-1] == (_LOCK_KIND, "1101", "up", "09:13:05", 2)

    async def test_opposite_direction_bucket_not_swallowed(
        self, tmp_path: Path, mono: FakeMono
    ) -> None:
        """(d) 對向桶不互吃:up 的 lock 桶冷卻中,down 的 lock 照發。"""
        engine, *_ = _make(tmp_path)
        hub = FakeHub()
        engine.attach_signal_hub(hub)

        engine._diff_limit_events(_TRADE_DATE, [_row_out("1101", up=True)], "09:01:05")
        engine._diff_limit_events(_TRADE_DATE, [_row_out("1101", down=True)], "09:01:15")

        assert _tuples(hub.events) == [
            (_LOCK_KIND, "1101", "up", "09:01:05", 1),
            (_OPEN_KIND, "1101", "up", "09:01:15", 1),
            (_LOCK_KIND, "1101", "down", "09:01:15", 1),
        ]

    async def test_limit_judged_false_row_skipped_entirely(self, tmp_path: Path) -> None:
        """(e) 缺值輪(`limit_judged=False`)整列跳過:不發事件、`last_emitted` 不動。

        缺值列的 `limit_up` 恆 False,與「真的打開了」同形 —— 不跳過就會產假 open,
        而下一個正常輪又補回一則 lock,事件流變成一串不存在的抖動。
        """
        engine, *_ = _make(tmp_path)
        hub = FakeHub()
        engine.attach_signal_hub(hub)

        engine._diff_limit_events(_TRADE_DATE, [_row_out("1101", up=True, judged=False)], "09:01:05")
        assert hub.events == []

        # 狀態零推進 → 之後判得出來的那輪照樣發 lock(不是被吃掉的一次轉移)
        engine._diff_limit_events(_TRADE_DATE, [_row_out("1101", up=True)], "09:02:05")
        assert _tuples(hub.events) == [(_LOCK_KIND, "1101", "up", "09:02:05", 1)]

        # 已發布 lock 後的缺值輪:不得產假 open
        engine._diff_limit_events(_TRADE_DATE, [_row_out("1101", judged=False)], "09:03:05")
        assert len(hub.events) == 1

    async def test_hub_none_does_not_advance_state(self, tmp_path: Path) -> None:
        """(f) 未 attach → 早退:不 seed、不 latch 日別、不動對帳狀態(design R2-1)。

        attach 前推進了狀態的話,那些轉移會被「假發布」—— 當日不再回放 seed,
        而事件流少的正是開盤那一批。
        """
        engine, *_ = _make(tmp_path)

        engine._diff_limit_events(_TRADE_DATE, [_row_out("1101", up=True)], "09:01:05")

        assert engine._mkt_emitted_date is None
        assert engine._mkt_last_emitted == {}
        assert engine._mkt_cooldown == {}

        hub = FakeHub()
        engine.attach_signal_hub(hub)
        engine._diff_limit_events(_TRADE_DATE, [_row_out("1101", up=True)], "09:02:05")

        assert hub.state_calls == [_TRADE_DATE]
        assert _tuples(hub.events) == [(_LOCK_KIND, "1101", "up", "09:02:05", 1)]

    async def test_detach_stops_events(self, tmp_path: Path) -> None:
        """detach 後不再發(hub 收攤前的關機序;鏡射 stock_engine)。"""
        engine, *_ = _make(tmp_path)
        hub = FakeHub()
        engine.attach_signal_hub(hub)
        engine._diff_limit_events(_TRADE_DATE, [_row_out("1101", up=True)], "09:01:05")

        engine.detach_signal_hub()
        engine._diff_limit_events(_TRADE_DATE, [_row_out("1101")], "09:02:05")

        assert len(hub.events) == 1

    async def test_cycle_emits_from_computed_rows(self, tmp_path: Path) -> None:
        """整輪接線:diff 吃的是 `compute_breadth` 的 rows(帶 limit 旗標與 name)。

        餵 `_apply` 的入參(原始快照)會讓事件整批消失 —— 那份沒有 limit 鍵。
        """
        engine, *_ = _make(tmp_path)
        hub = FakeHub()
        engine.attach_signal_hub(hub)

        await engine._run_cycle()

        assert _tuples(hub.events) == [
            (_LOCK_KIND, "1101", "up", "10:23:45", 1),
            (_LOCK_KIND, "6488", "down", "10:23:45", 1),
        ]
        assert [e["name"] for e in hub.events] == ["台泥", "環球晶"]
        assert [e["price"] for e in hub.events] == [11_000, 9_000]

    async def test_out_of_domain_minute_does_not_trigger_diff(self, tmp_path: Path) -> None:
        """(g) `_append` 回 None(分鐘域外:盤後定盤 14:30)→ 完全不觸發 diff。"""
        stamp = f"{_TRADE_DATE} 14:30:00"
        engine, *_ = _make(
            tmp_path,
            snapshot=FakeFetch(_snapshot_rows(stamp)),
            clock=Clock(now="14:31:00"),
        )
        hub = FakeHub()
        engine.attach_signal_hub(hub)

        await engine._run_cycle()

        assert engine.state()["counts"] == _EXPECTED  # 家數照算
        assert hub.batches == []
        assert hub.state_calls == []
        assert engine._mkt_emitted_date is None

    async def test_other_day_snapshot_does_not_trigger_diff(self, tmp_path: Path) -> None:
        """(g) 上一交易日的快照(跨午夜 / 假日重啟)→ 不觸發 diff。"""
        stamp = "2026-08-04 10:23:45"
        engine, *_ = _make(tmp_path, snapshot=FakeFetch(_snapshot_rows(stamp)))
        hub = FakeHub()
        engine.attach_signal_hub(hub)

        await engine._run_cycle()

        assert hub.batches == []
        assert engine._mkt_emitted_date is None

    async def test_new_day_reseeds_and_clears_cooldown(self, tmp_path: Path) -> None:
        """(h) 換日 → 重 seed + 清冷卻:昨日的冷卻不得壓掉今日開盤的第一則。"""
        engine, *_ = _make(tmp_path)
        hub = FakeHub()
        engine.attach_signal_hub(hub)

        engine._diff_limit_events(_TRADE_DATE, [_row_out("1101", up=True)], "13:29:05")
        engine._diff_limit_events("2026-08-06", [_row_out("1101", up=True)], "09:01:05")

        assert hub.state_calls == [_TRADE_DATE, "2026-08-06"]
        assert _tuples(hub.events) == [
            (_LOCK_KIND, "1101", "up", "13:29:05", 1),
            (_LOCK_KIND, "1101", "up", "09:01:05", 1),  # 當日第 1 次(計數也重 seed)
        ]
        assert [batch[1] for batch in hub.batches] == [_TRADE_DATE, "2026-08-06"]

    async def test_raw_snapshot_rows_emit_nothing_with_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """(i) 餵原始快照列(無 limit 鍵)→ 0 則,且留下**可辨識**的 warning。

        靜默跳過的話,呼叫點餵錯 rows 的表現只是「事件流永遠空著」,而空事件流與
        「今天沒人鎖板」完全同形。
        """
        engine, *_ = _make(tmp_path)
        hub = FakeHub()
        engine.attach_signal_hub(hub)

        with caplog.at_level(logging.WARNING, logger="copycat.server.breadth_engine"):
            engine._diff_limit_events(_TRADE_DATE, _snapshot_rows(), "10:00:05")

        assert hub.batches == []
        assert any("limit_judged" in r.getMessage() for r in caplog.records)

    async def test_mixed_unjudged_rows_still_emit_the_judged_ones(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """(i) 混合列:缺鍵的跳過、其餘照發,warning 文案要與這個行為一致(review S-5)。

        原文案寫「該批不發事件」,但實作是逐列 `continue` —— 照文案排查的人會去找
        「為什麼整批消失」,而真相是只少了那幾列。文案與行為不符的 log 比沒有更貴。
        """
        engine, *_ = _make(tmp_path)
        hub = FakeHub()
        engine.attach_signal_hub(hub)

        with caplog.at_level(logging.WARNING, logger="copycat.server.breadth_engine"):
            engine._diff_limit_events(
                _TRADE_DATE,
                [
                    {k: v for k, v in _row_out("1101", up=True).items() if k != "limit_judged"},
                    _row_out("2330", name="台積電", close=100.0, up=True),
                ],
                "10:00:05",
            )

        assert _tuples(hub.events) == [(_LOCK_KIND, "2330", "up", "10:00:05", 1)]
        messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("limit_judged" in m for m in messages)
        assert not any("該批不發事件" in m for m in messages)  # 整批消失 ≠ 少幾列
        assert any("其餘照常" in m for m in messages)

    async def test_bad_row_value_drops_only_that_row(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """(j) 單列壞值(close 為字串)→ 只丟該筆,同輪其他檔照發。"""
        engine, *_ = _make(tmp_path)
        hub = FakeHub()
        engine.attach_signal_hub(hub)

        with caplog.at_level(logging.WARNING, logger="copycat.server.breadth_engine"):
            engine._diff_limit_events(
                _TRADE_DATE,
                [
                    {**_row_out("1101", up=True), "close": "壞值"},
                    _row_out("2330", name="台積電", close=100.0, up=True),
                ],
                "10:00:05",
            )

        assert [e["code"] for e in hub.events] == ["2330"]
        assert any(r.levelno >= logging.WARNING for r in caplog.records)

    async def test_hub_failure_does_not_kill_cycle(self, tmp_path: Path) -> None:
        """(j) 批次傘:事件層炸掉不得殺 poll 輪 —— 家數面板與事件流是兩件事。"""
        engine, *_ = _make(tmp_path)
        hub = FakeHub()
        hub.publish_error = RuntimeError("匯流排壞了")
        engine.attach_signal_hub(hub)

        await engine._run_cycle()

        assert engine.state()["counts"] == _EXPECTED
        assert engine._series_list() == [_EXPECTED_POINT]
