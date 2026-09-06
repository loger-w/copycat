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
from copycat.live.tc4 import HistoryTimeoutError
from copycat.server import signal_hub as hub_mod
from tests.server.test_signal_hub import _DATE, _Clock, _Harness, _write_rules

_PREV = "2026-08-03"  # 已封閉日檔(< hub 日別 2026-08-04 = 牆鐘日)


def _bar(t: str, o: int) -> Bar:
    return Bar(t=t, o=o, h=o + 500, l=o - 500, c=o + 100, v=1000)


class _FakeDayBars:
    """`outcome_bars` 替身:code → bars 或例外;`calls` 記 (code, start, end)。"""

    def __init__(self, table: dict[str, list[Bar] | Exception] | None = None) -> None:
        self.table: dict[str, list[Bar] | Exception] = dict(table or {})
        self.calls: list[tuple[str, str, str]] = []

    async def __call__(self, code: str, start: str, end: str) -> list[Bar]:
        self.calls.append((code, start, end))
        item = self.table.get(code, [])
        if isinstance(item, Exception):
            raise item
        return list(item)


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


def _write_day(tmp_path: Path, date: str, lines: list[str]) -> Path:
    """逐行原文落檔(含刻意保留的空行 / 壞行),回路徑。"""
    path = tmp_path / "signals" / f"{date.replace('-', '')}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
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
    async def test_fills_t1_t2_and_leaves_other_lines_byte_identical(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
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
        path = _write_day(tmp_path, _PREV, lines)
        h = _harness(tmp_path, clock, bars)
        await h.hub.backfill_policy_outcomes()
        out = path.read_bytes().decode("utf-8").split("\n")
        assert out[0] == plain  # 一般列逐字不變
        assert out[2] == "" and out[3] == broken  # 空行 / 壞行原樣保留
        assert out[-1] == ""  # 檔尾換行不變
        for idx in (1, 4):
            row = json.loads(out[idx])
            assert (row["t1_open"], row["t1_date"], row["t2_open"], row["t2_date"]) == (
                51_000,
                "2026-08-04",
                52_000,
                "2026-08-05",
            )
        # 其餘欄位逐字保留(鍵序也不變)
        assert list(json.loads(out[1])) == list(_policy_row("2330"))
        # 同檔兩列只取一次日 K;範圍 = 日檔日 .. 牆鐘日
        assert bars.calls == [("2330", _PREV, _DATE)]

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

    async def test_zero_open_bar_not_used(self, tmp_path: Path, clock: _Clock) -> None:
        """今日 partial bar 開盤前 open 可能為 0 → 不算,留 null 下輪再補。"""
        bars = _FakeDayBars({"2330": [_bar("2026-08-04", 0)]})
        path = _write_day(tmp_path, _PREV, [_dump(_policy_row("2330"))])
        h = _harness(tmp_path, clock, bars)
        await h.hub.backfill_policy_outcomes()
        assert _read(path)[0]["t1_open"] is None

    @pytest.mark.parametrize(
        "failure",
        [HistoryTimeoutError("DK 逾時"), ConnectionError("TC4 不可用"), RuntimeError("炸")],
    )
    async def test_failure_leaves_null_and_continues_other_codes(
        self, tmp_path: Path, clock: _Clock, failure: Exception, caplog: pytest.LogCaptureFixture
    ) -> None:
        bars = _FakeDayBars({"2330": failure, "2344": [_bar("2026-08-04", 91_000)]})
        path = _write_day(tmp_path, _PREV, [_dump(_policy_row("2330")), _dump(_policy_row("2344"))])
        h = _harness(tmp_path, clock, bars)
        with caplog.at_level(logging.WARNING, logger="copycat.server.signal_hub"):
            await h.hub.backfill_policy_outcomes()
        rows = _read(path)
        assert rows[0]["t1_open"] is None
        assert rows[1]["t1_open"] == 91_000
        assert "2330" in caplog.text and "回填" in caplog.text

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
        assert "回填 2 列" in caplog.text


class TestSchedule:
    async def test_runs_at_start_then_daily_at_outcome_time(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(hub_mod, "POLICY_OUTCOME_POLL_SECS", 0.01)
        clock = _Clock(_dt.datetime(2026, 8, 4, 10, 0, 0))
        bars = _FakeDayBars({"2330": [_bar("2026-08-04", 51_000)]})
        _write_day(tmp_path, _PREV, [_dump(_policy_row("2330"))])
        h = _harness(tmp_path, clock, bars)
        await h.hub.start()
        try:
            await _wait_calls(bars, 1)  # start 後立即一次
            await asyncio.sleep(0.05)
            assert len(bars.calls) == 1  # 10:00 未到 13:40 → 不再跑
            clock.now = _dt.datetime(2026, 8, 4, 13, 40, 0)
            await _wait_calls(bars, 2)  # 推到 13:40 → 當日那一次
            clock.now = _dt.datetime(2026, 8, 4, 13, 41, 0)
            await asyncio.sleep(0.05)
            assert len(bars.calls) == 2  # 同日不重跑
            clock.now = _dt.datetime(2026, 8, 5, 13, 40, 0)
            await _wait_calls(bars, 3)  # 隔天再跑
        finally:
            await asyncio.wait_for(h.hub.close(), 5)  # close 取消 worker 不吊死

    async def test_start_after_outcome_time_counts_as_today(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(hub_mod, "POLICY_OUTCOME_POLL_SECS", 0.01)
        clock = _Clock(_dt.datetime(2026, 8, 4, 13, 50, 0))
        bars = _FakeDayBars({"2330": [_bar("2026-08-04", 51_000)]})
        _write_day(tmp_path, _PREV, [_dump(_policy_row("2330"))])
        h = _harness(tmp_path, clock, bars)
        await h.hub.start()
        try:
            await _wait_calls(bars, 1)
            await asyncio.sleep(0.05)
            assert len(bars.calls) == 1  # 13:50 起動的那一次就是今天的那一次
        finally:
            await asyncio.wait_for(h.hub.close(), 5)

    async def test_custom_outcome_time_from_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(hub_mod, "POLICY_OUTCOME_POLL_SECS", 0.01)
        clock = _Clock(_dt.datetime(2026, 8, 4, 10, 0, 0))
        bars = _FakeDayBars({"2330": [_bar("2026-08-04", 51_000)]})
        _write_day(tmp_path, _PREV, [_dump(_policy_row("2330"))])
        h = _harness(tmp_path, clock, bars, policy_outcome_time="14:30:00")
        await h.hub.start()
        try:
            await _wait_calls(bars, 1)
            clock.now = _dt.datetime(2026, 8, 4, 13, 40, 0)
            await asyncio.sleep(0.05)
            assert len(bars.calls) == 1  # 設定改 14:30 → 13:40 不跑
            clock.now = _dt.datetime(2026, 8, 4, 14, 30, 0)
            await _wait_calls(bars, 2)
        finally:
            await asyncio.wait_for(h.hub.close(), 5)

    async def test_no_source_not_started_with_info(
        self, tmp_path: Path, clock: _Clock, caplog: pytest.LogCaptureFixture
    ) -> None:
        h = _harness(tmp_path, clock, None)
        with caplog.at_level(logging.INFO, logger="copycat.server.signal_hub"):
            await h.hub.start()
        try:
            assert "無日 K 來源" in caplog.text and "回填" in caplog.text
            names = {getattr(t.get_coro(), "__name__", "") for t in h.hub._tasks}
            assert "_policy_outcome_worker" not in names
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
