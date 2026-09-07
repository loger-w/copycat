"""T+1 / T+2 開盤價回填 worker(spec #192 T4)—— 檔案 seam(seam 3)。

tmp 日檔(政策列 + 一般列)+ fake 日 K(`outcome_bars`:(code, start, end) → 日 K bars)→
只補 null、只碰過去日、其餘列原文逐字不變(byte 比對)、失敗續行;排程以注入時鐘 +
縮短的輪詢常數驗;無日 K 來源不啟動。
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from copycat.live.stock_source import Bar
from copycat.server import signal_hub as hub_mod
from copycat.server.bars import BarsResult
from tests.server.test_signal_hub import _DATE, _Clock, _Harness, _write_rules
from tests.server.test_signal_policy import _POLICY_KEYS

_PREV = "2026-08-03"  # 已封閉日檔(< hub 日別 2026-08-04 = 牆鐘日)


def _bar(t: str, o: int) -> Bar:
    return Bar(t=t, o=o, h=o + 500, l=o - 500, c=o + 100, v=1000)


_Outcome = list[Bar] | BarsResult | Exception


class _FakeDayBars:
    """`outcome_bars` 替身(形狀 = app 的 `_outcome_bars` → `BarsResult`):code → bars(status ok)
    / `BarsResult`(空 + timeout / disconnected:`bars_range` 把逾時 / 斷線吃成這樣,review F-08)
    / 例外;`calls` 記 (code, start, end)。"""

    def __init__(self, table: dict[str, _Outcome] | None = None) -> None:
        self.table: dict[str, _Outcome] = dict(table or {})
        self.calls: list[tuple[str, str, str]] = []

    async def __call__(self, code: str, start: str, end: str) -> BarsResult:
        self.calls.append((code, start, end))
        item = self.table.get(code, [])
        if isinstance(item, Exception):
            raise item
        if isinstance(item, BarsResult):
            return item
        return BarsResult(list(item), "ok")


class _PollClock(_Clock):
    """`now_fn` 讀取計數:worker 每輪輪詢讀一次時鐘,「沒再跑」要等它真的輪詢過 N 次才斷
    (review F-32:`sleep(0.05)` 在機器忙時可能零輪詢、斷言空轉)。"""

    def __init__(self, start: _dt.datetime | None = None) -> None:
        super().__init__(start)
        self.reads = 0

    def __call__(self) -> _dt.datetime:
        self.reads += 1
        return self.now


def _policy_row(code: str, policy: str = "P", **over: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "type": "signal",
        "id": f"{_PREV}-r-1-000-{code}-policy-{policy}-10:01:30.500",
        "rule_id": "r-1-000",
        "rule_name": "掃單簇",
        "kind": "policy",
        "policy": policy,
        "code": code,
        "name": "名",
        "price": 50_400,
        "time": "10:01:30",
        "levels": [],
        "direction": None,
        "pct": 0.8,
        "touch_count": 1,
        "notify": True,
        "first_of_day": True,
        "late": False,
        "tod": "0930",
        "sweep": {"n30": 2, "levels": 2, "qty": 6, "up_pct": 0.8},
        "self": {"chg_pct": 0.8, "to_limit_pct": 9.1, "touched_upper": False, "locked_up": False},
        "groups": ["記憶體"],
        "screen_member": False,
        "peers": [],
        "peers_up": 0,
        "peer_max": None,
        "leader": False,
        "peer_touched": False,
        "t1_open": None,
        "t1_date": None,
        "t2_open": None,
        "t2_date": None,
        "trade_date": _PREV,
    }
    row.update(over)
    return row


def _plain_row(code: str = "2317") -> dict[str, Any]:
    return {
        "type": "signal",
        "id": f"{_PREV}-r-1-001-{code}-cdp_cross-nh-10:00:00.123",
        "rule_id": "r-1-001",
        "rule_name": "CDP 穿越",
        "kind": "cdp_cross",
        "code": code,
        "name": "鴻海",
        "price": 80_500,
        "time": "10:00:00",
        "levels": ["nh"],
        "direction": "from_below",
        "pct": None,
        "touch_count": 1,
        "notify": False,
        "trade_date": _PREV,
    }


def _write_day(tmp_path: Path, date: str, lines: list[str], *, eol: str = "\n") -> Path:
    """逐行原文落檔(含刻意保留的空行 / 壞行),回路徑。`eol` 預設 LF 只是省事;prod 檔在 Windows
    是 CRLF(`_append_jsonl` 文字模式 append),byte 比對案兩種都跑(review F-27)。"""
    path = tmp_path / "signals" / f"{date.replace('-', '')}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((eol.join(lines) + eol).encode("utf-8"))
    return path


def _dump(row: dict[str, Any]) -> str:
    return json.dumps(row, ensure_ascii=False)


def _read(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


def _harness(tmp_path: Path, clock: _Clock, bars: _FakeDayBars | None, **over: Any) -> _Harness:
    _write_rules(tmp_path, [])
    return _Harness(tmp_path, clock, outcome_bars=bars, **over)


class TestFileBackfill:
    def test_policy_row_fixture_matches_policy_keys(self) -> None:
        """手抄的政策列形狀釘到主 seam 的 `_POLICY_KEYS`(review F-31):hub 加欄 / 改欄時這裡先紅。"""
        assert set(_policy_row("2330")) == _POLICY_KEYS | {"trade_date"}

    @pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["lf", "crlf"])
    async def test_fills_t1_t2_and_leaves_other_lines_byte_identical(
        self, tmp_path: Path, clock: _Clock, eol: str
    ) -> None:
        """整段 bytes 比對(review F-27):prod 檔在 Windows 是 CRLF,被補的列行尾必須原樣接回 ——
        把實作的行尾硬寫成 LF,LF 案照綠、只有 CRLF 案紅。"""
        bars = _FakeDayBars(
            {
                "2330": [
                    _bar("2026-08-03", 49_000),
                    _bar("2026-08-04", 51_000),
                    _bar("2026-08-05", 52_000),
                ]
            }
        )
        plain = _dump(_plain_row())
        broken = '{"kind": "policy", "code": "2330", "t1_open": null  # 壞行'
        lines = [plain, _dump(_policy_row("2330")), "", broken, _dump(_policy_row("2330", "S"))]
        path = _write_day(tmp_path, _PREV, lines, eol=eol)
        h = _harness(tmp_path, clock, bars)
        await h.hub.backfill_policy_outcomes()
        filled: dict[str, Any] = {
            "t1_open": 51_000,
            "t1_date": "2026-08-04",
            "t2_open": 52_000,
            "t2_date": "2026-08-05",
        }
        expected = [
            plain,  # 一般列逐字不變
            _dump(_policy_row("2330", **filled)),  # 只換 JSON 本體(鍵序不變)、行尾原樣接回
            "",  # 空行 / 壞行原樣保留
            broken,
            _dump(_policy_row("2330", "S", **filled)),
        ]
        assert path.read_bytes() == (eol.join(expected) + eol).encode("utf-8")  # 檔尾換行不變
        # 同檔兩列只取一次日 K;範圍 = 日檔日 .. 牆鐘日
        assert bars.calls == [("2330", _PREV, _DATE)]

    async def test_undecodable_line_kept_and_other_rows_filled(
        self, tmp_path: Path, clock: _Clock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """半寫入切在中文中間的壞行(review F-09,2026-09-07 拍板逐行 bytes):那一行位元組原樣保留、
        其餘政策列照補、WARNING 一行;整檔嚴格解碼會讓那一天連續 `policy_outcome_days` 天整檔跳過。"""
        bars = _FakeDayBars({"2330": [_bar("2026-08-04", 51_000), _bar("2026-08-05", 52_000)]})
        good = _dump(_policy_row("2330")).encode("utf-8")
        # 切在中文「積」的最後一個位元組 → 不是合法 UTF-8
        torn = '{"kind": "policy", "code": "2330", "name": "台積'.encode("utf-8")[:-1]
        path = tmp_path / "signals" / f"{_PREV.replace('-', '')}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(good + b"\n" + torn + b"\n" + good + b"\n")
        h = _harness(tmp_path, clock, bars)
        with caplog.at_level(logging.WARNING, logger="copycat.server.signal_hub"):
            await h.hub.backfill_policy_outcomes()
        out = path.read_bytes().split(b"\n")
        assert out[1] == torn  # 壞行位元組原樣
        for idx in (0, 2):
            row = json.loads(out[idx].decode("utf-8"))
            assert (row["t1_open"], row["t2_open"]) == (51_000, 52_000)
        assert "1 行不是合法 UTF-8" in caplog.text

    async def test_only_null_fields_filled_and_complete_rows_not_fetched(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        bars = _FakeDayBars(
            {
                "2330": [_bar("2026-08-04", 51_000), _bar("2026-08-05", 52_000)],
                "2344": [_bar("2026-08-04", 91_000), _bar("2026-08-05", 92_000)],
            }
        )
        has_t1 = _policy_row("2330", t1_open=50_000, t1_date="2026-08-04")
        complete = _policy_row(
            "2344", t1_open=1, t1_date="2026-08-04", t2_open=2, t2_date="2026-08-05"
        )
        path = _write_day(tmp_path, _PREV, [_dump(has_t1), _dump(complete)])
        h = _harness(tmp_path, clock, bars)
        await h.hub.backfill_policy_outcomes()
        rows = _read(path)
        assert (rows[0]["t1_open"], rows[0]["t1_date"]) == (50_000, "2026-08-04")  # 已有的不動
        assert (rows[0]["t2_open"], rows[0]["t2_date"]) == (52_000, "2026-08-05")
        assert rows[1] == complete  # 兩者皆有 → 原樣
        assert [c[0] for c in bars.calls] == ["2330"]  # 2344 不取日 K

    async def test_only_past_files_within_days_window(self, tmp_path: Path, clock: _Clock) -> None:
        """日期 = hub 日別 / 牆鐘日的檔不動;超出 `policy_outcome_days` 的舊檔不動。"""
        bars = _FakeDayBars({"2330": [_bar("2026-08-10", 60_000), _bar("2026-08-11", 61_000)]})
        dates_old = ["2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31"]
        for d in dates_old + [_PREV, _DATE]:
            row = _policy_row("2330", trade_date=d, id=f"{d}-x")
            _write_day(tmp_path, d, [_dump(row)])
        # 牆鐘日 = hub 日別 = 2026-08-04;policy_outcome_days=5 → 最近五個過去日檔
        h = _harness(tmp_path, clock, bars, policy_outcome_days=5)
        await h.hub.backfill_policy_outcomes()
        touched = {
            d
            for d in dates_old + [_PREV, _DATE]
            if _read(tmp_path / "signals" / f"{d.replace('-', '')}.jsonl")[0]["t1_open"] is not None
        }
        assert touched == {"2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31", _PREV}
        assert len(bars.calls) == 1  # 同一輪同檔只取一次(範圍 = 最早日檔日 .. 牆鐘日)
        assert bars.calls[0] == ("2330", "2026-07-28", _DATE)

    async def test_hub_date_ahead_of_wall_clock_keeps_wall_day_untouched(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """兩個日別取較小者當「已封閉」的界:hub 日別已前進到 08-05、牆鐘還在 08-04 →
        08-04 檔仍不動(T+1 就是今天,開盤價還沒定)。"""
        bars = _FakeDayBars({"2330": [_bar("2026-08-05", 51_000)]})
        _write_day(tmp_path, _DATE, [_dump(_policy_row("2330", trade_date=_DATE))])
        _write_day(tmp_path, _PREV, [_dump(_policy_row("2330"))])
        h = _harness(tmp_path, clock, bars)
        h.date = "2026-08-05"
        await h.hub.backfill_policy_outcomes()
        assert _read(tmp_path / "signals" / "20260804.jsonl")[0]["t1_open"] is None
        assert _read(tmp_path / "signals" / "20260803.jsonl")[0]["t1_open"] == 51_000

    async def test_only_t1_available_then_t2_next_round(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        bars = _FakeDayBars({"2330": [_bar("2026-08-03", 49_000), _bar("2026-08-04", 51_000)]})
        path = _write_day(tmp_path, _PREV, [_dump(_policy_row("2330"))])
        h = _harness(tmp_path, clock, bars)
        await h.hub.backfill_policy_outcomes()
        row = _read(path)[0]
        assert (row["t1_open"], row["t1_date"], row["t2_open"], row["t2_date"]) == (
            51_000,
            "2026-08-04",
            None,
            None,
        )
        bars.table["2330"] = [_bar("2026-08-04", 51_000), _bar("2026-08-05", 52_000)]
        await h.hub.backfill_policy_outcomes()
        row = _read(path)[0]
        assert (row["t1_open"], row["t2_open"], row["t2_date"]) == (51_000, 52_000, "2026-08-05")

    async def test_zero_open_bar_not_used_and_not_shifted(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """今日 partial bar 開盤前 open 可能為 0 → 不算,留 null 下輪再補;**T+2 那根不得
        往前冒充 T+1**(日期大於該日的前兩根就是 T+1 / T+2,spec 字面;spec review F-03)。"""
        bars = _FakeDayBars({"2330": [_bar("2026-08-04", 0), _bar("2026-08-05", 52_000)]})
        path = _write_day(tmp_path, _PREV, [_dump(_policy_row("2330"))])
        h = _harness(tmp_path, clock, bars)
        await h.hub.backfill_policy_outcomes()
        row = _read(path)[0]
        assert row["t1_open"] is None and row["t1_date"] is None
        assert (row["t2_open"], row["t2_date"]) == (52_000, "2026-08-05")  # T+2 照補,不位移

    @pytest.mark.parametrize(
        ("failure", "expect_exc", "mark"),
        [
            # 逾時 / 斷線由 `bars_range` 吃成空 + status(app 的 `_outcome_bars` 整顆回來,review F-08):
            # WARNING 帶 status、無 traceback(預期中的暫時態)
            (BarsResult([], "timeout"), False, "timeout"),
            (BarsResult([], "disconnected"), False, "disconnected"),
            # 例外 → traceback(真的壞了才值得堆疊)
            (ConnectionError("TC4 不可用"), True, "取得失敗"),
            (RuntimeError("炸"), True, "取得失敗"),
        ],
        ids=["timeout", "disconnected", "connection-error", "runtime-error"],
    )
    async def test_failure_leaves_null_and_continues_other_codes(
        self,
        tmp_path: Path,
        clock: _Clock,
        failure: _Outcome,
        expect_exc: bool,
        mark: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """三種失敗分得出來(review F-28):warning ↔ exception 以 `exc_info` 斷,不只比子字串。"""
        bars = _FakeDayBars({"2330": failure, "2344": [_bar("2026-08-04", 91_000)]})
        path = _write_day(tmp_path, _PREV, [_dump(_policy_row("2330")), _dump(_policy_row("2344"))])
        h = _harness(tmp_path, clock, bars)
        with caplog.at_level(logging.WARNING, logger="copycat.server.signal_hub"):
            await h.hub.backfill_policy_outcomes()
        rows = _read(path)
        assert rows[0]["t1_open"] is None
        assert rows[1]["t1_open"] == 91_000
        hits = [r for r in caplog.records if "2330" in r.getMessage() and "回填" in r.getMessage()]
        assert len(hits) == 1
        assert mark in hits[0].getMessage()
        assert (hits[0].exc_info is not None) is expect_exc

    async def test_empty_bars_leaves_null_and_file_untouched(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        bars = _FakeDayBars({"2330": []})
        path = _write_day(tmp_path, _PREV, [_dump(_policy_row("2330"))])
        before = path.read_bytes()
        h = _harness(tmp_path, clock, bars)
        await h.hub.backfill_policy_outcomes()
        assert path.read_bytes() == before  # 零補 → 不重寫檔案

    async def test_log_reports_filled_rows(
        self, tmp_path: Path, clock: _Clock, caplog: pytest.LogCaptureFixture
    ) -> None:
        bars = _FakeDayBars({"2330": [_bar("2026-08-04", 51_000), _bar("2026-08-05", 52_000)]})
        _write_day(tmp_path, _PREV, [_dump(_policy_row("2330")), _dump(_policy_row("2330", "S"))])
        h = _harness(tmp_path, clock, bars)
        with caplog.at_level(logging.INFO, logger="copycat.server.signal_hub"):
            await h.hub.backfill_policy_outcomes()
        # 逐檔行與彙總行分開斷(review F-29):只比「回填 2 列」時刪掉逐檔 INFO 照綠
        assert f"T+1/T+2 回填 {_PREV}:回填 2 列(1 檔)" in caplog.text
        assert "共回填 2 列" in caplog.text


class TestSchedule:
    async def test_runs_at_start_then_daily_at_outcome_time(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(hub_mod, "POLICY_OUTCOME_POLL_SECS", 0.01)
        clock = _PollClock(_dt.datetime(2026, 8, 4, 10, 0, 0))
        bars = _FakeDayBars({"2330": [_bar("2026-08-04", 51_000)]})
        _write_day(tmp_path, _PREV, [_dump(_policy_row("2330"))])
        h = _harness(tmp_path, clock, bars)
        with caplog.at_level(logging.INFO, logger="copycat.server.signal_hub"):
            await h.hub.start()
        assert "回填 worker 起動" in caplog.text  # 盤後可驗判準:啟動 log 一行
        try:
            await _wait_calls(bars, 1)  # start 後立即一次
            await _wait_polls(clock, 10)
            assert len(bars.calls) == 1  # 10:00 未到 13:40 → 不再跑
            clock.now = _dt.datetime(2026, 8, 4, 13, 40, 0)
            await _wait_calls(bars, 2)  # 推到 13:40 → 當日那一次
            clock.now = _dt.datetime(2026, 8, 4, 13, 41, 0)
            await _wait_polls(clock, 10)
            assert len(bars.calls) == 2  # 同日不重跑
            clock.now = _dt.datetime(2026, 8, 5, 13, 40, 0)
            await _wait_calls(bars, 3)  # 隔天再跑
        finally:
            await asyncio.wait_for(h.hub.close(), 5)  # close 取消 worker 不吊死

    async def test_start_after_outcome_time_counts_as_today(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(hub_mod, "POLICY_OUTCOME_POLL_SECS", 0.01)
        clock = _PollClock(_dt.datetime(2026, 8, 4, 13, 50, 0))
        bars = _FakeDayBars({"2330": [_bar("2026-08-04", 51_000)]})
        _write_day(tmp_path, _PREV, [_dump(_policy_row("2330"))])
        h = _harness(tmp_path, clock, bars)
        await h.hub.start()
        try:
            await _wait_calls(bars, 1)
            await _wait_polls(clock, 10)
            assert len(bars.calls) == 1  # 13:50 起動的那一次就是今天的那一次
        finally:
            await asyncio.wait_for(h.hub.close(), 5)

    async def test_custom_outcome_time_from_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(hub_mod, "POLICY_OUTCOME_POLL_SECS", 0.01)
        clock = _PollClock(_dt.datetime(2026, 8, 4, 10, 0, 0))
        bars = _FakeDayBars({"2330": [_bar("2026-08-04", 51_000)]})
        _write_day(tmp_path, _PREV, [_dump(_policy_row("2330"))])
        h = _harness(tmp_path, clock, bars, policy_outcome_time="14:30:00")
        await h.hub.start()
        try:
            await _wait_calls(bars, 1)
            clock.now = _dt.datetime(2026, 8, 4, 13, 40, 0)
            await _wait_polls(clock, 10)
            assert len(bars.calls) == 1  # 設定改 14:30 → 13:40 不跑
            clock.now = _dt.datetime(2026, 8, 4, 14, 30, 0)
            await _wait_calls(bars, 2)
        finally:
            await asyncio.wait_for(h.hub.close(), 5)

    @pytest.mark.parametrize("label", ["policy_outcome_time", "policy_push_end"])
    async def test_bad_hhmmss_config_raises_at_construction(
        self, tmp_path: Path, clock: _Clock, label: str
    ) -> None:
        """壞的 HH:MM:SS 設定在建構時就炸(review F-06):hub None → routes 503 大聲,
        不是每 30 s 一行 WARNING 印一整天。"""
        with pytest.raises(ValueError, match=label):
            _harness(tmp_path, clock, None, **{label: "13:40"})  # 缺秒 → 不是 HH:MM:SS

    async def test_no_source_not_started_with_info(
        self, tmp_path: Path, clock: _Clock, caplog: pytest.LogCaptureFixture
    ) -> None:
        h = _harness(tmp_path, clock, None)
        with caplog.at_level(logging.INFO, logger="copycat.server.signal_hub"):
            await h.hub.start()
        try:
            assert "無日 K 來源" in caplog.text and "回填" in caplog.text
            names = {getattr(t.get_coro(), "__name__", "") for t in h.hub._tasks}
            # 綁實際的 coroutine 名(review F-30):worker 改名時這行跟著動,不會退化成恆真
            assert hub_mod.SignalHub._policy_outcome_worker.__name__ not in names
        finally:
            await h.hub.close()


async def _wait_calls(bars: _FakeDayBars, n: int) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 2.0
    while loop.time() < deadline:
        if len(bars.calls) >= n:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"outcome_bars 只被打了 {len(bars.calls)} 次,等不到 {n} 次")


async def _wait_polls(clock: _PollClock, n: int) -> None:
    """等 worker 真的再輪詢過 n 次(每輪讀一次時鐘)再做「沒再跑」的否定斷言。"""
    target = clock.reads + n
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 2.0
    while loop.time() < deadline:
        if clock.reads >= target:
            return
        await asyncio.sleep(0.005)
    raise AssertionError(f"時鐘只被讀了 {clock.reads} 次,等不到 {target} 次")
