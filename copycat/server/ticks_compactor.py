"""tick 存檔的盤後排程(spec #257 T5):交易日 `compact_time` 以子程序呼叫 `ticks-compact`。

樣板同 `screen_engine` 的 08:00 task(poll-loop + armed-day):`tick()` 是排程迴圈與測試共用的
觀測點,時鐘與呼叫端都可注入。每輪掃目錄內所有 jsonl(round-1 Standards F-02 / Spec F-05:
只看「今天」的話,server 13:45 沒開著或 engine 沒換日留下的昨日檔永遠不會自動轉):

    過去日的 jsonl → 到了就轉(啟動補跑);今天的 → 到 `compact_time` 才轉。每一天各自一台
    狀態機:第一次嘗試前先請寫入端印當日那行並 **seal 該日 handle**(flush + 關;Windows 開著
    的檔刪不掉,子程序「列數核對後刪 jsonl」會 PermissionError)→ 子程序 exit 0 = 成功(轉發
    它 stdout 那行到 server log、跑簿檔保留)→ 非 0 / 逾時 / 非預期例外 = 失敗一次,`retry_secs`
    後再試,重試 `retry_max` 次仍失敗 WARNING 一行放棄(jsonl 留著,手動 CLI 可重轉)。
    該日 parquet 已在(殘餘 jsonl)→ 不轉、WARNING 一次(round-1 Spec F-01);非交易日的
    jsonl 不該存在 → 略過 WARNING 一次。

pyarrow 不進 server 進程:子程序 = `sys.executable -m copycat ticks-compact --date … --dir …`;
exit 非 0 含「pyarrow 未裝」(CLI 的 ImportError)。
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from copycat.live.tick_persist import TickPersist
from copycat.ticks import parquet_path
from copycat.ticks_config import TicksConfig

__all__ = ["CompactRun", "TicksCompactor", "run_compact_subprocess"]

logger = logging.getLogger(__name__)

#: 子程序的 cwd:本檔所屬 repo root(`copycat/server/` 上兩層),與 `ticks_config._REPO_ROOT` 同一棵樹
_REPO_ROOT = Path(__file__).resolve().parents[2]
#: 排程迴圈醒來的最短間隔 / 到點後的緩衝(避免踩在 13:45:00.000 判定邊上)
_MIN_SLEEP_SECS = 5.0
_AFTER_DUE_SECS = 5.0
#: 保留計算往回找交易日的保險絲(同 trading_calendar 的 `_LOOKBACK_LIMIT_DAYS` 精神):
#: `book_keep_days` 上限 ~5 年;超過 = 日曆或設定壞了,raise 勝過無限迴圈
_RETAIN_LOOKBACK_LIMIT_DAYS = 366 * 5 + 30


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
    """`python -m copycat` 以 **cwd** 決定載哪一份 copycat(venv 是 editable 安裝,`.pth` 釘主樹,
    別的 cwd 會靜默跑到另一棵樹;pr-263 F-08)—— 一律釘在本檔所屬的 repo root。"""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "copycat",
        "ticks-compact",
        "--date",
        day.strftime("%Y%m%d"),
        "--dir",
        str(data_dir),
        cwd=_REPO_ROOT,
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


@dataclass(slots=True)
class _DayState:
    """一個交易日的轉檔狀態機(armed-day):試了幾次、下一次最早幾點、做完 / 放棄。"""

    attempts: int = 0
    next_attempt_at: _dt.datetime | None = None
    done: bool = False
    gave_up: bool = False
    warned: set[str] = field(default_factory=set)  # 已印過的一次性 WARNING 種類


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
        self._due_time = config.due_time()  # 驗證與解析同一處(pr-263 F-24)
        self._task: asyncio.Task[None] | None = None
        self._days: dict[_dt.date, _DayState] = {}

    @property
    def dir(self) -> Path:
        return self._dir

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
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                # 任務存活邊界(screen_engine 同款):目錄掃描 / 保留刪檔的意外不能殺掉排程迴圈 ——
                # 死透的表現只是「jsonl 再也不轉」,例外要到關機 `_close_segment` 才浮現
                logger.exception("tick 轉檔排程非預期失敗(下一輪再試)")
            await asyncio.sleep(self._sleep_secs(self._now_fn()))

    def _sleep_secs(self, now: _dt.datetime) -> float:
        """退避中 → 睡到最早的下一次嘗試;否則睡到今天(已過則明天)的 `compact_time` + 緩衝。
        每個日曆日都醒,非交易日由 `tick` 判零動作。"""
        pending = [
            s.next_attempt_at
            for s in self._days.values()
            if s.next_attempt_at is not None
            and now < s.next_attempt_at
            and not (s.done or s.gave_up)
        ]
        if pending:
            target = min(pending)
        else:
            target = _dt.datetime.combine(now.date(), self._due_time) + _dt.timedelta(
                seconds=_AFTER_DUE_SECS
            )
            if now >= target:
                target += _dt.timedelta(days=1)
        return max(_MIN_SLEEP_SECS, (target - now).total_seconds())

    def _pending_days(self, now: _dt.datetime) -> list[_dt.date]:
        """目錄內有 jsonl、此刻該轉的日(過去日隨時;今天到點後;未來日不理),舊的在前。"""
        today = now.date()
        days: list[_dt.date] = []
        for path in self._dir.glob("*.jsonl"):
            try:
                day = _dt.datetime.strptime(path.stem, "%Y%m%d").date()
            except ValueError:
                continue
            if day > today or (day == today and now.time() < self._due_time):
                continue
            days.append(day)
        return sorted(days)

    async def tick(self) -> None:
        """一次排程迭代:對每個該轉的日各推一步(沒做完也沒放棄、不在退避中 → 叫一次)。"""
        if not self._cfg.enabled:
            return
        now = self._now_fn()
        for day in self._pending_days(now):
            await self._tick_day(day, now)

    async def _tick_day(self, day: _dt.date, now: _dt.datetime) -> None:
        st = self._days.setdefault(day, _DayState())
        if st.done or st.gave_up:
            return
        if not self._is_trading_day(day):
            self._warn_once(
                st, "non_trading", "tick 轉檔 %s:非交易日卻有 jsonl,略過(不轉、不刪)", day
            )
            return
        if parquet_path(self._dir, day.isoformat()).exists():
            # round-1 Spec F-01:已轉檔的日旁邊又冒出 jsonl(寫入端已擋預開;殘餘 = 手動 CLI 半途 /
            # 舊版留下),再轉會把真 parquet 蓋掉 —— 不轉、留著、講一次
            self._warn_once(
                st,
                "stray",
                "tick 轉檔 %s:parquet 已在但殘餘 jsonl 仍在,不轉不刪(要重轉先刪 parquet)",
                day,
            )
            return
        if st.next_attempt_at is not None and now < st.next_attempt_at:
            return
        if st.attempts == 0 and self._persist is not None:
            # 第一次嘗試前:當日那行 + 放掉 handle(見模組說明)。那行只對寫入端**當前**的日印
            # (pr-263 F-05):開機補跑過去日時計數器是今天的、剛歸零,印成「昨天 成交 0」是假陳述
            if self._persist.current_day == day.isoformat():
                self._persist.log_stats(day.isoformat())
            self._persist.seal_day(day.isoformat())
        st.attempts += 1
        st.next_attempt_at = None
        reason = await self._attempt_once(day, st.attempts)
        # 嘗試本身可能耗掉整個 `compact_timeout_secs`:退避與保留都用 await **之後**的時刻
        # (pr-263 F-18),否則一次逾時後下一次只等 900 − 300 s
        now = self._now_fn()
        if reason is None:
            st.done = True
            self._retain_books(now.date())
            return
        if st.attempts > self._cfg.retry_max:
            # 最後一次失敗與放棄合成同一行(screen_engine 同款)
            st.gave_up = True
            logger.warning(
                "tick 轉檔 %s 第 %d 次%s,放棄(jsonl 留著;手動:python -m copycat ticks-compact --date %s)",
                day,
                st.attempts,
                reason,
                day.strftime("%Y%m%d"),
            )
            return
        st.next_attempt_at = now + _dt.timedelta(seconds=self._cfg.retry_secs)
        logger.warning(
            "tick 轉檔 %s 第 %d 次%s;%.0f s 後再試", day, st.attempts, reason, self._cfg.retry_secs
        )

    @staticmethod
    def _warn_once(st: _DayState, kind: str, fmt: str, day: _dt.date) -> None:
        if kind in st.warned:
            return
        st.warned.add(kind)
        logger.warning(fmt, day)

    async def _attempt_once(self, day: _dt.date, attempt: int) -> str | None:
        """叫一次轉檔;成功回 None(並轉發 CLI 那行),失敗回原因字串(逾時 / rc + stderr 尾行 /
        非預期例外)。"""
        try:
            run = await asyncio.wait_for(self._runner(day), timeout=self._cfg.compact_timeout_secs)
        except TimeoutError:
            return f"逾時(> {self._cfg.compact_timeout_secs:.0f} s,子程序已殺)"
        except asyncio.CancelledError:
            raise
        except Exception:
            # 存活邊界的另一半:呼叫端本身炸了(子程序起不來 / OSError)—— 記 traceback、算失敗一次
            logger.exception("tick 轉檔 %s 第 %d 次呼叫端非預期失敗", day, attempt)
            return "非預期失敗(見上方 traceback)"
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
        """含今天往回數 `book_keep_days` 個交易日,回最舊要留的那一天(連假不算)。
        超過保險絲仍數不滿 = 日曆或設定壞了 → RuntimeError(由 `_loop` 的存活邊界接住)。"""
        day = today
        remaining = self._cfg.book_keep_days
        for _ in range(_RETAIN_LOOKBACK_LIMIT_DAYS):
            if self._is_trading_day(day):
                remaining -= 1
                if remaining <= 0:
                    return day
            day -= _dt.timedelta(days=1)
        raise RuntimeError(
            f"往回 {_RETAIN_LOOKBACK_LIMIT_DAYS} 天數不滿 {self._cfg.book_keep_days} 個交易日(起點 {today})"
        )
