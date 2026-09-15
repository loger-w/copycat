"""S3 盤後排程(spec #257 T5):fake clock + 注入 fake 轉檔呼叫端(不開子程序)。

同 `test_screen_engine` 的 08:00 task 寫法:`tick()` 是排程迴圈與測試共用的觀測點,
時鐘與呼叫端都注入;斷言只看「什麼時刻叫了幾次、留了什麼檔、印了什麼行」。
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
from pathlib import Path

import pytest

from copycat.live.tick_persist import TickPersist
from copycat.server.ticks_compactor import CompactRun, TicksCompactor
from copycat.ticks import book_parquet_path, jsonl_path, parquet_path
from copycat.ticks_config import TicksConfig

_TUE = _dt.date(2026, 7, 21)
_LOGGER = "copycat.server.ticks_compactor"


def _weekday(d: _dt.date) -> bool:
    return d.weekday() < 5


class _Clock:
    def __init__(self, start: _dt.datetime) -> None:
        self.t = start

    def now(self) -> _dt.datetime:
        return self.t


class _Runner:
    """記錄呼叫時刻;`results` 逐次 pop,取完沿用最後一個。"""

    def __init__(self, clock: _Clock, results: list[CompactRun]) -> None:
        self.clock = clock
        self.results = list(results)
        self.calls: list[tuple[_dt.date, _dt.datetime]] = []

    async def __call__(self, day: _dt.date) -> CompactRun:
        self.calls.append((day, self.clock.t))
        if len(self.results) > 1:
            return self.results.pop(0)
        return self.results[0]


_OK = CompactRun(
    0,
    "tick 轉檔 2026-07-21:jsonl 3 列 → 成交 2 列 + 簿 1 列(去重 0、壞行 0),耗時 0.1 秒,0.0 MB\n",
    "",
)
_FAIL = CompactRun(1, "", "tick 轉檔 2026-07-21 失敗:讀回列數對不上\n")


def _touch_jsonl(data_dir: Path, day: _dt.date = _TUE) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    p = jsonl_path(data_dir, day.isoformat())
    p.write_text('{"kind":"trade"}\n', encoding="utf-8")
    return p


def _make(
    tmp_path: Path,
    clock: _Clock,
    runner: _Runner,
    *,
    cfg: TicksConfig | None = None,
    persist: TickPersist | None = None,
) -> TicksCompactor:
    return TicksCompactor(
        cfg if cfg is not None else TicksConfig(dir=str(tmp_path), retry_secs=900.0, retry_max=3),
        data_dir=tmp_path,
        is_trading_day=_weekday,
        runner=runner,
        now_fn=clock.now,
        persist=persist,
    )


class TestSchedule:
    async def test_not_before_1345_once_at_1345_and_not_again_that_day(
        self, tmp_path: Path
    ) -> None:
        _touch_jsonl(tmp_path)
        clock = _Clock(_dt.datetime(2026, 7, 21, 13, 44, 0))
        runner = _Runner(clock, [_OK])
        eng = _make(tmp_path, clock, runner)
        await eng.tick()
        assert runner.calls == []
        clock.t = _dt.datetime(2026, 7, 21, 13, 45, 0)
        await eng.tick()
        assert [c[0] for c in runner.calls] == [_TUE]
        clock.t = _dt.datetime(2026, 7, 21, 15, 0, 0)
        await eng.tick()
        assert len(runner.calls) == 1

    async def test_non_trading_day_never_calls(self, tmp_path: Path) -> None:
        sat = _dt.date(2026, 7, 25)
        _touch_jsonl(tmp_path, sat)
        clock = _Clock(_dt.datetime(2026, 7, 25, 14, 0, 0))
        runner = _Runner(clock, [_OK])
        await _make(tmp_path, clock, runner).tick()
        assert runner.calls == []

    async def test_failure_retries_every_15_min_up_to_3_then_warns_and_stops(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        jsonl = _touch_jsonl(tmp_path)
        clock = _Clock(_dt.datetime(2026, 7, 21, 13, 45, 0))
        runner = _Runner(clock, [_FAIL])
        eng = _make(tmp_path, clock, runner)
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            for minute in (45, 50, 60, 74, 75, 90, 105, 120, 135):
                clock.t = _dt.datetime(2026, 7, 21, 13, 0, 0) + _dt.timedelta(minutes=minute)
                await eng.tick()
        assert [c[1].time() for c in runner.calls] == [
            _dt.time(13, 45),
            _dt.time(14, 0),
            _dt.time(14, 15),
            _dt.time(14, 30),
        ]
        assert jsonl.exists()  # 放棄不動 jsonl(手動 CLI 還能轉)
        warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 4  # 三次「再試」+ 一次「放棄」
        assert all("讀回列數對不上" in w for w in warnings[:3])
        assert "放棄" in warnings[3] and "ticks-compact --date 20260721" in warnings[3]
        assert [r.levelno for r in caplog.records if r.levelno > logging.WARNING] == []

    async def test_success_on_second_attempt_stops_and_relays_the_cli_line(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        _touch_jsonl(tmp_path)
        clock = _Clock(_dt.datetime(2026, 7, 21, 13, 45, 0))
        runner = _Runner(clock, [_FAIL, _OK])
        eng = _make(tmp_path, clock, runner)
        with caplog.at_level(logging.INFO, logger=_LOGGER):
            await eng.tick()
            clock.t = _dt.datetime(2026, 7, 21, 14, 0, 0)
            await eng.tick()
            clock.t = _dt.datetime(2026, 7, 21, 14, 15, 0)
            await eng.tick()
        assert len(runner.calls) == 2
        infos = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
        assert _OK.stdout.strip() in infos

    async def test_boot_after_1345_runs_immediately_only_if_jsonl_exists(
        self, tmp_path: Path
    ) -> None:
        clock = _Clock(_dt.datetime(2026, 7, 21, 18, 30, 0))
        runner = _Runner(clock, [_OK])
        await _make(tmp_path, clock, runner).tick()
        assert runner.calls == []  # 沒有 jsonl(已轉或沒開)→ 不叫
        _touch_jsonl(tmp_path)
        runner2 = _Runner(clock, [_OK])
        await _make(tmp_path, clock, runner2).tick()
        assert [c[1].time() for c in runner2.calls] == [_dt.time(18, 30)]

    async def test_timeout_counts_as_one_failure(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        _touch_jsonl(tmp_path)
        clock = _Clock(_dt.datetime(2026, 7, 21, 13, 45, 0))

        class _Hang(_Runner):
            async def __call__(self, day: _dt.date) -> CompactRun:
                self.calls.append((day, self.clock.t))
                await asyncio.Event().wait()
                raise AssertionError("unreachable")

        runner = _Hang(clock, [_OK])
        eng = _make(
            tmp_path,
            clock,
            runner,
            cfg=TicksConfig(dir=str(tmp_path), compact_timeout_secs=0.05),
        )
        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            await eng.tick()
        assert len(runner.calls) == 1
        assert any("逾時" in r.getMessage() for r in caplog.records)
        clock.t = _dt.datetime(2026, 7, 21, 13, 50, 0)
        await eng.tick()
        assert len(runner.calls) == 1  # 15 分鐘退避中
        clock.t = _dt.datetime(2026, 7, 21, 14, 0, 0)
        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            await eng.tick()
        assert len(runner.calls) == 2

    async def test_disabled_never_calls(self, tmp_path: Path) -> None:
        _touch_jsonl(tmp_path)
        clock = _Clock(_dt.datetime(2026, 7, 21, 14, 0, 0))
        runner = _Runner(clock, [_OK])
        eng = _make(tmp_path, clock, runner, cfg=TicksConfig(enabled=False, dir=str(tmp_path)))
        await eng.tick()
        assert runner.calls == []

    def test_sleep_targets_compact_time_today_then_tomorrow(self, tmp_path: Path) -> None:
        clock = _Clock(_dt.datetime(2026, 7, 21, 9, 0, 0))
        eng = _make(tmp_path, clock, _Runner(clock, [_OK]))
        assert eng._sleep_secs(clock.now()) == (4 * 3600 + 45 * 60) + 5  # 13:45:05
        clock.t = _dt.datetime(2026, 7, 21, 18, 0, 0)
        assert eng._sleep_secs(clock.now()) == (19 * 3600 + 45 * 60) + 5  # 明天 13:45:05


class TestPersistHandoff:
    async def test_first_attempt_prints_the_stats_line_and_releases_the_day_handle(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """13:45 先印「tick 存檔 <日>」那行、把當日 handle flush + 關掉,再叫轉檔 —— Windows 下
        開著的檔刪不掉,子程序的「列數核對後刪 jsonl」會直接 PermissionError。"""
        persist = TickPersist(TicksConfig(dir=str(tmp_path), flush_secs=3600.0))
        loop = asyncio.get_running_loop()
        persist.start(loop, "2026-07-21")
        jsonl = jsonl_path(tmp_path, "2026-07-21")
        assert jsonl.exists()
        clock = _Clock(_dt.datetime(2026, 7, 21, 13, 45, 0))
        runner = _Runner(clock, [_OK])
        eng = _make(tmp_path, clock, runner, persist=persist)
        with caplog.at_level(logging.INFO, logger="copycat.live.tick_persist"):
            await eng.tick()
        assert len(runner.calls) == 1
        stats = [
            r.getMessage()
            for r in caplog.records
            if r.getMessage().startswith("tick 存檔 2026-07-21:")
        ]
        assert len(stats) == 1
        jsonl.unlink()  # handle 已放掉才刪得掉(Windows)
        persist.close()


class TestRealSubprocess:
    async def test_subprocess_runner_compacts_a_real_jsonl(self, tmp_path: Path) -> None:
        """唯一 fake 蓋不到的一段:`sys.executable -m copycat ticks-compact --date … --dir …` 這條命令列
        真的跑得起來、rc=0、stdout 是那一行、jsonl 變成兩個 parquet。"""
        from copycat.server.ticks_compactor import run_compact_subprocess

        tmp_path.mkdir(exist_ok=True)
        row = {
            "kind": "trade",
            "code": "2330",
            "trade_date": "2026-07-21",
            "msg_seq": 1,
            "recv_ns": 1,
            "precise_time": "25751000000",
            "trade_status": "0",
            "bid0": 2_375_000,
            "bidq0": 10,
            "ask0": 2_380_000,
            "askq0": 10,
            "time": "10:57:51.000",
            "ms": 39_471_000,
            "price_milli": 2_380_000,
            "qty": 1,
            "cum_vol": 1,
            "flag": "2",
            "side": "outer",
            "seq": 1,
        }
        import json

        jsonl_path(tmp_path, "2026-07-21").write_text(json.dumps(row) + "\n", encoding="utf-8")
        run = await run_compact_subprocess(_TUE, tmp_path)
        assert run.rc == 0, run.stderr
        assert run.stdout.startswith(
            "tick 轉檔 2026-07-21:jsonl 1 列 → 成交 1 列 + 簿 0 列(去重 0、壞行 0)"
        )
        assert parquet_path(tmp_path, "2026-07-21").exists()
        assert book_parquet_path(tmp_path, "2026-07-21").exists()
        assert not jsonl_path(tmp_path, "2026-07-21").exists()


class TestRetention:
    async def test_book_files_older_than_keep_days_in_trading_days_are_deleted(
        self, tmp_path: Path
    ) -> None:
        """book_keep_days=3、週末不算:週一 07-27 轉檔成功後留 07-27 / 07-24 / 07-23 的簿檔,
        07-22 / 07-21 / 07-20 的簿檔刪;成交檔永不刪。"""
        mon = _dt.date(2026, 7, 27)
        _touch_jsonl(tmp_path, mon)
        days = ["2026-07-27", "2026-07-24", "2026-07-23", "2026-07-22", "2026-07-21", "2026-07-20"]
        for d in days:
            book_parquet_path(tmp_path, d).write_bytes(b"x")
            parquet_path(tmp_path, d).write_bytes(b"x")
        (tmp_path / "notes.txt").write_text("keep", encoding="utf-8")
        clock = _Clock(_dt.datetime(2026, 7, 27, 13, 45, 0))
        runner = _Runner(clock, [_OK])
        eng = _make(tmp_path, clock, runner, cfg=TicksConfig(dir=str(tmp_path), book_keep_days=3))
        await eng.tick()
        kept = sorted(p.name for p in tmp_path.iterdir())
        assert kept == sorted(
            [f"{d.replace('-', '')}.parquet" for d in days]
            + ["20260727-book.parquet", "20260724-book.parquet", "20260723-book.parquet"]
            + ["notes.txt", "20260727.jsonl"]
        )

    async def test_retention_does_not_run_when_compaction_failed(self, tmp_path: Path) -> None:
        _touch_jsonl(tmp_path)
        book_parquet_path(tmp_path, "2025-01-02").write_bytes(b"x")
        clock = _Clock(_dt.datetime(2026, 7, 21, 13, 45, 0))
        eng = _make(tmp_path, clock, _Runner(clock, [_FAIL]))
        await eng.tick()
        assert book_parquet_path(tmp_path, "2025-01-02").exists()
