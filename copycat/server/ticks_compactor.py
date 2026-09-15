"""tick 存檔的盤後排程(spec #257 T5):交易日 `compact_time` 以子程序呼叫 `ticks-compact`。

樣板同 `screen_engine` 的 08:00 task(poll-loop + armed-day):`tick()` 是排程迴圈與測試共用的
觀測點,時鐘與呼叫端都可注入。一天的狀態機:

    到 `compact_time`(或啟動時已過)且當日 jsonl 存在 → 第一次嘗試前先請寫入端印當日那行
    並 **seal 當日 handle**(flush + 關;Windows 開著的檔刪不掉,子程序「列數核對後刪 jsonl」
    會 PermissionError)→ 子程序 exit 0 = 成功(轉發它 stdout 那行到 server log、跑簿檔保留)
    → 非 0 / 逾時 = 失敗一次,`retry_secs` 後再試,重試 `retry_max` 次仍失敗 WARNING 一行放棄
    (jsonl 留著,手動 CLI 可重轉)。

pyarrow 不進 server 進程:子程序 = `sys.executable -m copycat ticks-compact --date … --dir …`;
exit 非 0 含「pyarrow 未裝」(CLI 的 ImportError)。
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from copycat.live.tick_persist import TickPersist
from copycat.ticks import jsonl_path
from copycat.ticks_config import TicksConfig

__all__ = ["CompactRun", "TicksCompactor", "run_compact_subprocess"]

logger = logging.getLogger(__name__)

#: 排程迴圈醒來的最短間隔 / 到點後的緩衝(避免踩在 13:45:00.000 判定邊上)
_MIN_SLEEP_SECS = 5.0
_AFTER_DUE_SECS = 5.0


@dataclass(frozen=True, slots=True)
class CompactRun:
    """一次轉檔呼叫的結果:exit code + 子程序輸出(逾時由 compactor 用 `wait_for` 判,不在這裡)。"""

    rc: int
    stdout: str
    stderr: str


Runner = Callable[[_dt.date], Awaitable[CompactRun]]


def make_subprocess_runner(data_dir: Path) -> Runner:
    """prod 呼叫端:同一支 CLI、同一個目錄;被 `wait_for` cancel 時殺掉子程序(不留孤兒)。"""

    async def _run(day: _dt.date) -> CompactRun:
        return await run_compact_subprocess(day, data_dir)

    return _run


async def run_compact_subprocess(day: _dt.date, data_dir: Path) -> CompactRun:
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "copycat",
        "ticks-compact",
        "--date",
        day.strftime("%Y%m%d"),
        "--dir",
        str(data_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await proc.communicate()
    except asyncio.CancelledError:
        # 逾時(`wait_for` cancel)或關機:卡住的子程序不能留著繼續佔 jsonl / 寫半個 parquet
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        raise
    return CompactRun(
        proc.returncode if proc.returncode is not None else -1,
        out.decode("utf-8", errors="replace"),
        err.decode("utf-8", errors="replace"),
    )


class TicksCompactor:
    def __init__(
        self,
        config: TicksConfig,
        *,
        data_dir: Path,
        is_trading_day: Callable[[_dt.date], bool],
        runner: Runner | None = None,
        now_fn: Callable[[], _dt.datetime] = _dt.datetime.now,
        persist: TickPersist | None = None,
    ) -> None:
        self._cfg = config
        self._dir = data_dir
        self._is_trading_day = is_trading_day
        self._runner = runner if runner is not None else make_subprocess_runner(data_dir)
        self._now_fn = now_fn
        self._persist = persist
        hh, mm = config.compact_time.split(":")
        self._due_time = _dt.time(int(hh), int(mm))
        self._task: asyncio.Task[None] | None = None
        # 日別狀態(armed-day):哪一天做完 / 放棄、當日已試幾次、下一次最早幾點
        self._done_for: _dt.date | None = None
        self._gave_up_for: _dt.date | None = None
        self._attempts_for: _dt.date | None = None
        self._attempts = 0
        self._next_attempt_at: _dt.datetime | None = None

    # ---- 生命週期 ----

    async def start(self) -> None:
        if not self._cfg.enabled:
            return
        self._task = asyncio.create_task(self._loop())

    async def close(self) -> None:
        task = self._task
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # ---- 排程 ----

    async def _loop(self) -> None:
        while True:
            await self.tick()
            await asyncio.sleep(self._sleep_secs(self._now_fn()))

    def _sleep_secs(self, now: _dt.datetime) -> float:
        """退避中 → 睡到下一次嘗試;否則睡到今天(已過則明天)的 `compact_time` + 緩衝。
        每個日曆日都醒,非交易日由 `tick` 判零動作。"""
        if self._next_attempt_at is not None and now < self._next_attempt_at:
            target = self._next_attempt_at
        else:
            target = _dt.datetime.combine(now.date(), self._due_time) + _dt.timedelta(
                seconds=_AFTER_DUE_SECS
            )
            if now >= target:
                target += _dt.timedelta(days=1)
        return max(_MIN_SLEEP_SECS, (target - now).total_seconds())

    async def tick(self) -> None:
        """一次排程迭代:今天是交易日、已到點、當日 jsonl 在、沒做完也沒放棄、不在退避中 → 叫一次。"""
        if not self._cfg.enabled:
            return
        now = self._now_fn()
        today = now.date()
        if not self._is_trading_day(today) or now.time() < self._due_time:
            return
        if today in (self._done_for, self._gave_up_for):
            return
        if self._next_attempt_at is not None and now < self._next_attempt_at:
            return
        if not jsonl_path(self._dir, today.isoformat()).exists():
            # 已轉過(parquet 在、jsonl 不在)或當天沒開存檔:沒有事可做,今天到此為止
            self._done_for = today
            return
        if self._attempts_for != today:
            self._attempts_for = today
            self._attempts = 0
        if self._attempts == 0 and self._persist is not None:
            # 第一次嘗試前:當日那行 + 放掉 handle(見模組說明)
            self._persist.log_stats(today.isoformat())
            self._persist.seal_day(today.isoformat())
        self._attempts += 1
        self._next_attempt_at = None
        reason = await self._attempt_once(today)
        if reason is None:
            self._done_for = today
            self._retain_books(today)
            return
        if self._attempts > self._cfg.retry_max:
            # 最後一次失敗與放棄合成同一行(screen_engine 同款)
            self._gave_up_for = today
            logger.warning(
                "tick 轉檔 %s 第 %d 次%s,放棄(jsonl 留著;手動:python -m copycat ticks-compact --date %s)",
                today,
                self._attempts,
                reason,
                today.strftime("%Y%m%d"),
            )
            return
        self._next_attempt_at = now + _dt.timedelta(seconds=self._cfg.retry_secs)
        logger.warning(
            "tick 轉檔 %s 第 %d 次%s;%.0f s 後再試",
            today,
            self._attempts,
            reason,
            self._cfg.retry_secs,
        )

    async def _attempt_once(self, day: _dt.date) -> str | None:
        """叫一次轉檔;成功回 None(並轉發 CLI 那行),失敗回原因字串(逾時 / rc + stderr 尾行)。"""
        try:
            run = await asyncio.wait_for(self._runner(day), timeout=self._cfg.compact_timeout_secs)
        except TimeoutError:
            return f"逾時(> {self._cfg.compact_timeout_secs:.0f} s,子程序已殺)"
        if run.rc == 0:
            for line in run.stdout.splitlines():
                if line.strip():
                    logger.info("%s", line.strip())  # 轉發 CLI 的「tick 轉檔 …」那行(盤後判準)
            return None
        detail = (run.stderr.strip() or run.stdout.strip()).splitlines()
        return f"失敗 rc={run.rc}:{detail[-1] if detail else '(無輸出)'}"

    # ---- 保留 ----

    def _retain_books(self, today: _dt.date) -> None:
        """刪超過 `book_keep_days` 個**交易日**的簿檔;成交檔永不刪。只認 `YYYYMMDD-book.parquet`。"""
        cutoff = self._cutoff_trading_day(today)
        for path in self._dir.glob("*-book.parquet"):
            stem = path.name[: -len("-book.parquet")]
            try:
                day = _dt.datetime.strptime(stem, "%Y%m%d").date()
            except ValueError:
                continue
            if day < cutoff:
                try:
                    path.unlink()
                    logger.info(
                        "tick 簿檔保留:刪 %s(> %d 交易日)", path.name, self._cfg.book_keep_days
                    )
                except OSError as exc:
                    logger.warning("tick 簿檔保留:刪 %s 失敗:%s", path.name, exc)

    def _cutoff_trading_day(self, today: _dt.date) -> _dt.date:
        """含今天往回數 `book_keep_days` 個交易日,回最舊要留的那一天(連假不算)。"""
        day = today
        remaining = self._cfg.book_keep_days
        while True:
            if self._is_trading_day(day):
                remaining -= 1
                if remaining <= 0:
                    return day
            day -= _dt.timedelta(days=1)
