"""盤前選股篩選引擎(#173)—— 交易日 21:00 重算 + 啟動補跑 + 覆寫自選群組「盤前篩選」。

排程判定是純函式(`screening.expected_data_date`):快取 `data_date` ≠ expected 即該跑,
所以「21:00 定時」與「server 啟動補跑」是同一條路 —— 迴圈醒來時算一次 expected,不對就補。
篩選演算法全在 `copycat.screening`(議定 seam,測試在那邊);本模組只做 IO 接線:
逐日 fetch(縮列後才累積,記憶體紀律見 `screening.shrink_rows`)、逐檔資格查、
落檔快取、經 `WatchlistService.replace_group` 覆寫群組(同鎖 + 訂閱 + 廣播)。

失敗處理:單一 expected 日最多 `_MAX_ATTEMPTS` 次(鐵則 F),用完當日放棄
(`_gave_up_for`,expected 換日自動重武裝)—— 壞上游不整夜燒配額。
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
from collections.abc import Callable
from pathlib import Path

from copycat.fileio import atomic_write_text
from copycat.market_breadth import parse_active_disposition
from copycat.screening import (
    RUN_TIME,
    WINDOW_DAYS,
    ScreenCandidate,
    apply_eligibility,
    expected_data_date,
    hard_candidates,
    shrink_rows,
)
from copycat.server.breadth_fetch import BreadthFetchError
from copycat.server.watchlist_service import WatchlistService
from copycat.stock_watchlist import WATCHLIST_LIMIT, WatchlistError, fit_group_codes
from copycat.trading_calendar import TradingCalendar

logger = logging.getLogger(__name__)

__all__ = ["SCREEN_GROUP", "ScreenEngine"]

#: 覆寫目標群組名(#173 Q19 拍板)。
SCREEN_GROUP = "盤前篩選"
_CACHE_VERSION = 1
_CACHE_NAME = "premarket_screen.json"
#: 單一 expected 日的嘗試上限(鐵則 F);間隔 / 配額退避沿 breadth streak 量級。
_MAX_ATTEMPTS = 3
_RETRY_SECS = 600.0
_QUOTA_RETRY_SECS = 3600.0
#: 逐請求間距(breadth streak 同款 —— 21 次全市場 + ~60 次資格查,別打成 burst)。
_REQ_GAP_SECS = 0.3
#: 單日全市場列數下限(breadth `_DAILY_MIN_ROWS` 同值):部分截斷的日子入窗會讓
#: 缺列的檔靜默斷窗(「窗內缺日不判」),整批候選無聲少一截。
_DAILY_MIN_ROWS = 25_000
#: 湊 21 交易日的日曆天保險絲(春節連假最長 ~10 日曆天,45 天綽綽有餘)。
_SCAN_CAL_DAYS = 45


class ScreenEngine:
    """`service=None` = 只算不寫(CLI 預覽路徑用 `compute`,不起迴圈)。"""

    def __init__(
        self,
        *,
        token: str,
        calendar: TradingCalendar,
        daily_fetch: Callable[[str, _dt.date], list[dict]],
        day_trading_fetch: Callable[[str, str, _dt.date], list[dict]],
        disposition_fetch: Callable[[str, _dt.date], list[dict]],
        service: WatchlistService | None = None,
        data_dir: Path | None = None,
        now_fn: Callable[[], _dt.datetime] = _dt.datetime.now,
    ) -> None:
        self._token = token
        self._cal = calendar
        self._daily_fetch = daily_fetch
        self._day_trading_fetch = day_trading_fetch
        self._disposition_fetch = disposition_fetch
        self._service = service
        self._dir = data_dir if data_dir is not None else Path("data") / "market"
        self._now_fn = now_fn
        self._task: asyncio.Task[None] | None = None
        self._gave_up_for: _dt.date | None = None

    # ---- 生命週期 ----

    async def start(self) -> None:
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

    # ---- 排程迴圈 ----

    async def _loop(self) -> None:
        while True:
            now = self._now_fn()
            expected = expected_data_date(now, self._cal)
            if self._cached_data_date() != expected and self._gave_up_for != expected:
                await self._run_attempts(expected)
            await asyncio.sleep(self._sleep_secs(self._now_fn()))

    def _sleep_secs(self, now: _dt.datetime) -> float:
        """睡到下一個 `RUN_TIME`(+30s 緩衝,避免踩在 21:00:00.000 判定邊上)。"""
        target = _dt.datetime.combine(now.date(), RUN_TIME) + _dt.timedelta(seconds=30)
        if now >= target:
            target += _dt.timedelta(days=1)
        return max(30.0, (target - now).total_seconds())

    async def _run_attempts(self, data_date: _dt.date) -> None:
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            wait = _RETRY_SECS
            try:
                await self._run_once(data_date)
                return
            except BreadthFetchError as e:
                wait = _QUOTA_RETRY_SECS if e.quota else _RETRY_SECS
                logger.warning(
                    "盤前篩選 %s 取數失敗(第 %d/%d 次,quota=%s,%.0fs 後重試):%s",
                    data_date,
                    attempt,
                    _MAX_ATTEMPTS,
                    e.quota,
                    wait,
                    e,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                # 任務存活邊界(breadth streak 同款):落檔 / 群組寫入的意外不能殺掉
                # 排程迴圈 —— 死透的表現只是「群組再也不更新」,零錯誤訊號。
                logger.exception(
                    "盤前篩選 %s 非預期失敗(第 %d/%d 次,%.0fs 後重試)",
                    data_date,
                    attempt,
                    _MAX_ATTEMPTS,
                )
            if attempt < _MAX_ATTEMPTS:
                await asyncio.sleep(wait)
        self._gave_up_for = data_date
        logger.error(
            "盤前篩選 %s 連續 %d 次未成,當日放棄(群組維持前一日名單,明日再武裝)",
            data_date,
            _MAX_ATTEMPTS,
        )

    # ---- 單次重算 ----

    async def compute(self, data_date: _dt.date) -> list[ScreenCandidate]:
        """抓窗 → 三硬條件 → 逐檔資格 → 處置剔除。純結果,不落檔不寫群組(CLI 共用)。"""
        days: list[tuple[_dt.date, list[dict]]] = []
        d = data_date
        floor = data_date - _dt.timedelta(days=_SCAN_CAL_DAYS)
        while d >= floor and len(days) < WINDOW_DAYS:
            if not self._cal.is_trading_day(d):
                # 日曆先剔(review F2):非交易日的空請求一天一發,21 個交易日的窗要多
                # 燒 ~10 次。空回應 fallback 仍在(無日曆年份只擋週末、臨時休市)。
                d -= _dt.timedelta(days=1)
                continue
            rows = await asyncio.to_thread(self._daily_fetch, self._token, d)
            await asyncio.sleep(_REQ_GAP_SECS)
            if rows:
                if len(rows) < _DAILY_MIN_ROWS:
                    raise BreadthFetchError(
                        f"盤前篩選 {d} 只有 {len(rows)} 列(門檻 {_DAILY_MIN_ROWS}),"
                        "視同取數失敗"
                    )
                days.append((d, shrink_rows(rows)))
            elif d == data_date:
                # 最新一天必須有資料:FinMind 當日 EOD 未落檔時,靜默拿更舊的日子湊窗
                # 會把過期窗記成 expected 完成 —— 名單整天停在昨日還零訊號。
                raise BreadthFetchError(f"盤前篩選 {d} 的 EOD 尚無資料(FinMind 未更新?)")
            d -= _dt.timedelta(days=1)
        if len(days) < WINDOW_DAYS:
            raise BreadthFetchError(
                f"盤前篩選 {data_date} 往回 {_SCAN_CAL_DAYS} 日曆天僅湊到 {len(days)} 交易日"
            )
        cands = hard_candidates(days)
        daytrade_ok: set[str] = set()
        for cand in cands:
            rows = await asyncio.to_thread(
                self._day_trading_fetch, self._token, cand.code, data_date
            )
            await asyncio.sleep(_REQ_GAP_SECS)
            if rows:
                daytrade_ok.add(cand.code)
        disp_rows = await asyncio.to_thread(self._disposition_fetch, self._token, data_date)
        disposed = parse_active_disposition(disp_rows, data_date)
        final = apply_eligibility(cands, daytrade_ok=daytrade_ok, disposed=disposed)
        logger.info(
            "盤前篩選 %s:硬條件 %d 檔 → 資格後 %d 檔(非當沖 %d / 處置 %d)",
            data_date,
            len(cands),
            len(final),
            sum(1 for c in cands if c.code not in daytrade_ok),
            sum(1 for c in cands if c.code in disposed),
        )
        return final

    async def _run_once(self, data_date: _dt.date) -> None:
        final = await self.compute(data_date)
        written = await self._write_group(final)
        self._write_cache(data_date, final, written)

    async def _write_group(self, final: list[ScreenCandidate]) -> list[str]:
        """截到上限後覆寫群組(截位語意單一份 `fit_group_codes`,CLI `--write` 同用)。"""
        service = self._service
        if service is None:  # pragma: no cover - prod 接線恆帶 service
            return [c.code for c in final]
        wl = await service.current()
        codes_out, dropped = fit_group_codes(wl, SCREEN_GROUP, [c.code for c in final])
        if dropped:
            logger.warning(
                "盤前篩選 %d 檔因自選上限 %d 被截掉(截的是排序尾段中尚不在自選的新檔;"
                "已在自選者不吃額度、無條件入列)",
                dropped,
                WATCHLIST_LIMIT,
            )
        try:
            _, changed = await service.replace_group(SCREEN_GROUP, codes_out)
        except WatchlistError as e:
            # current() 與 replace_group 之間使用者恰好改了自選 → 撞上限等。當一次
            # attempt 失敗重試,不吞:名單沒寫進去就不能記成完成。
            raise RuntimeError(f"盤前篩選寫入群組被拒:{e}") from e
        logger.info(
            "盤前篩選群組「%s」%s:%d 檔", SCREEN_GROUP, "已更新" if changed else "無變化", len(codes_out)
        )
        return codes_out

    # ---- 快取(= 「這個 expected 日已完成」的判定依據)----

    def _cache_path(self) -> Path:
        return self._dir / _CACHE_NAME

    def _cached_data_date(self) -> _dt.date | None:
        try:
            payload = json.loads(self._cache_path().read_text(encoding="utf-8"))
            if payload.get("_cache_version") != _CACHE_VERSION:
                return None
            return _dt.date.fromisoformat(payload["data_date"])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _write_cache(
        self, data_date: _dt.date, final: list[ScreenCandidate], written: list[str]
    ) -> None:
        payload = {
            "_cache_version": _CACHE_VERSION,
            "data_date": data_date.isoformat(),
            "computed_at": self._now_fn().isoformat(timespec="seconds"),
            "written": written,
            "candidates": [
                {
                    "code": c.code,
                    "ret_pct": round(c.ret_pct, 2),
                    "avg_lots": round(c.avg_lots),
                    "lock_dates": [d.isoformat() for d in c.lock_dates],
                }
                for c in final
            ],
        }
        self._dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(self._cache_path(), json.dumps(payload, ensure_ascii=False, indent=1))
