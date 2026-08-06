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

    async def test_disposition_failure_is_degraded_but_continues(self, tmp_path: Path) -> None:
        """處置股表拿不到 → 空集合續行(那幾檔會被算進去),但要亮 degraded。"""
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

    async def test_loop_survives_cycle_exception(self, tmp_path: Path) -> None:
        """一輪炸掉不得讓 poll task 死透(index `_mis_loop` 同款傘罩)。"""
        engine, snap, *_ = _make(tmp_path, config=BreadthConfig(poll_secs=0.01))
        snap.error = RuntimeError("boom")

        await engine.start()
        try:
            await _wait_until(lambda: snap.calls >= 3)
        finally:
            await engine.close()

        assert snap.calls >= 3
