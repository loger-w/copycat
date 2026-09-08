"""盤前選股篩選引擎(#173 → W2 T4 #207 改 08:00 目標交易日制)—— 每個交易日 08:00 重算 +
啟動補跑 + 覆寫自選群組「盤前篩選」。

排程判定是純函式(`screening.expected_target_date`):快取 `target_date` ≠ expected 即該跑,
所以「08:00 定時」與「server 啟動補跑」是同一條路 —— 迴圈醒來時算一次 expected,不對就補;
非交易日早上醒來 expected 仍是上一個交易日(已算過)→ 零動作。名單服務的是**目標交易日 = 今天**:
EOD 窗自**資料日**(昨天 = 前一交易日,`screening.data_date_of`)往回湊 21 交易日,當沖名單與處置股
抓 / 判**今天**的(CONTEXT.md「盤前篩選」節兩個詞)。
篩選演算法全在 `copycat.screening`(議定 seam,測試在那邊);本模組只做 IO 接線:
逐日 fetch(縮列後才累積,記憶體紀律見 `screening.shrink_rows`)、逐檔資格查、
落檔快取、經 `WatchlistService.replace_group` 覆寫群組(同鎖 + 訂閱 + 廣播)。

失敗處理(W2 T5 #209,user 2026-09-08 拍板 Q8):08:00 起每 `_RETRY_SECS` 再試,**到 `RETRY_UNTIL`
(09:00)為止**(時間盒,不是次數盒 —— 名單盤前幾點出還沒實錄,10 分鐘一發到開盤前盡量趕上);
下一次會落在 09:00 之後就放棄(`_gave_up_for`,目標日換日自動重武裝),群組維持前一日名單。
09:00 後才啟動的補跑失敗 = 直接放棄(當日名單過了開盤就不追,明日 08:00 再來)。每次失敗一行
WARNING、放棄那行也是 WARNING(FinMind 晚出不是 bug,不印 ERROR);非預期例外仍 `logger.exception`。
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
    data_date_of,
    expected_target_date,
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
#: v2(W2 T4 #207):以 `target_date` 判「做過沒」、`data_date` 降為推導值;v1(21:00 制,只有
#: `data_date`)讀到即 None → 換制後第一次啟動補跑一次,不會把舊制的「資料日」誤判成今天已完成。
_CACHE_VERSION = 2
_CACHE_NAME = "premarket_screen.json"
#: 重試間隔(沿 breadth streak 量級);重試的界是**時刻**不是次數(W2 T5 #209)。
_RETRY_SECS = 600.0
#: 重試時間盒的上界(台北牆鐘,end-exclusive):下一次嘗試時刻 ≥ 這一刻就不再排。08:00:30 起
#: 每 600 s → 08:00:30 … 08:50:30 共 6 次。**402 配額用盡不重試、當天直接放棄**(round-1 F-04 / S-02:
#: 一小時的盒裡沒有「長退避」可言,借退避值越界來間接放棄是障眼法,改成明講)。
_RETRY_UNTIL = _dt.time(9, 0)
#: 逐請求間距(breadth streak 同款 —— 21 次全市場 + ~60 次資格查,別打成 burst)。
_REQ_GAP_SECS = 0.3
#: 單日全市場列數下限(breadth `_DAILY_MIN_ROWS` 同值):部分截斷的日子入窗會讓
#: 缺列的檔靜默斷窗(「窗內缺日不判」),整批候選無聲少一截。
_DAILY_MIN_ROWS = 25_000
#: 湊 21 交易日的日曆天保險絲(春節連假最長 ~10 日曆天,45 天綽綽有餘)。
_SCAN_CAL_DAYS = 45
#: 當沖名單的**相對閘**(W2 T6 #210,user 2026-09-08 拍板 Q4 / Q11):今天列數 < 前一個交易日列數 ×
#: 這個係數 → 視同 FinMind 還在寫、只寫了一半(可重試錯誤,走 T5 的 10 分鐘重試)—— 半份名單拿去剔會把
#: 沒寫進來的那一半候選誤當「非當沖」踢掉,群組少一截且零錯誤訊號。前值 = 快取 `daytrade_rows`(只在成功
#: 落檔時更新 —— 常態 = 前一個交易日那份,server 關了幾天就是更早那份;round-1 S-03 校正 spec 字面);
#: 無前值(首次 / 舊版快取)退到絕對下限 `_DAYTRADE_MIN_ROWS`(09-08 實測全市場 2,079 列)。
#: 名單真的長期縮 > 20%(例如 server 關一個月)會每天擋 —— 不自動放寬,log 印兩數並提示刪鍵重置。
_DAYTRADE_SHRINK_RATIO = 0.8
_DAYTRADE_MIN_ROWS = 1_000


class ScreenEngine:
    """`service=None` = 只算不寫(CLI 預覽路徑用 `compute`,不起迴圈)。"""

    def __init__(
        self,
        *,
        token: str,
        calendar: TradingCalendar,
        daily_fetch: Callable[[str, _dt.date], list[dict]],
        day_trading_fetch: Callable[[str, _dt.date], list[dict]],
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
        # repo-root 錨定(review F-11,breadth `_DEFAULT_DATA_DIR` 同款):CWD 相對路徑
        # 在非 repo root 起 server 時會讓快取恆 miss → 每次 boot 整輪重跑,零訊號。
        self._dir = (
            data_dir
            if data_dir is not None
            else Path(__file__).resolve().parents[2] / "data" / "market"
        )
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
            await self.tick()
            if self._due() is not None:
                # tick 跑了很久(補跑昨天那份一路重試到 08:50 才放棄)期間跨過今天 08:00 → expected 已換成
                # 今天:不能照 `_sleep_secs` 睡到明天 08:00:30 把今天整天跳掉(round-1 spec S-01),立刻再 tick。
                continue
            await asyncio.sleep(self._sleep_secs(self._now_fn()))

    def _due(self) -> _dt.date | None:
        """此刻該跑的目標交易日;沒算過且沒放棄才回值,否則 None。"""
        expected = expected_target_date(self._now_fn(), self._cal)
        if self._cached_target_date() != expected and self._gave_up_for != expected:
            return expected
        return None

    async def tick(self) -> None:
        """一次排程迭代(排程迴圈與測試共用的觀測點):算目標交易日,沒算過且沒放棄就跑。
        非交易日早上 expected = 上一個交易日(已算過)→ 什麼都不做。"""
        target = self._due()
        if target is not None:
            await self._run_attempts(target)

    def _sleep_secs(self, now: _dt.datetime) -> float:
        """睡到下一個 `RUN_TIME`(+30s 緩衝,避免踩在 08:00:00.000 判定邊上)。每個日曆日都醒:
        非交易日醒來由 `tick` 判零動作,不必在這裡算下一個交易日。"""
        target = _dt.datetime.combine(now.date(), RUN_TIME) + _dt.timedelta(seconds=30)
        if now >= target:
            target += _dt.timedelta(days=1)
        return max(30.0, (target - now).total_seconds())

    def _next_attempt_at(self) -> _dt.datetime | None:
        """下一次嘗試的時刻(`_RETRY_SECS` 後);會落在 `_RETRY_UNTIL`(含)之後 → None(時間盒到頂,放棄)。"""
        now = self._now_fn()
        nxt = now + _dt.timedelta(seconds=_RETRY_SECS)
        deadline = _dt.datetime.combine(now.date(), _RETRY_UNTIL)
        return nxt if nxt < deadline else None

    def _give_up(self, target: _dt.date, attempt: int, reason: str, why_stop: str) -> None:
        self._gave_up_for = target
        logger.warning(
            "盤前篩選 %s 第 %d 次%s;%s,今日放棄(群組維持前一日名單,下一交易日 %s 再武裝)",
            target,
            attempt,
            reason,
            why_stop,
            RUN_TIME.strftime("%H:%M"),
        )

    async def _run_attempts(self, target: _dt.date) -> None:
        attempt = 0
        while True:
            attempt += 1
            reason = ""
            try:
                await self._run_once(target)
                return
            except BreadthFetchError as e:
                if e.quota:
                    # 配額用盡:一小時的盒裡沒有退避可言,今天就別再燒(round-1 F-04 / S-02)
                    self._give_up(target, attempt, f"取數失敗:{e}", "FinMind 配額用盡(402)")
                    return
                reason = f"取數失敗:{e}"
            except asyncio.CancelledError:
                raise
            except Exception:
                # 任務存活邊界(breadth streak 同款):落檔 / 群組寫入的意外不能殺掉
                # 排程迴圈 —— 死透的表現只是「群組再也不更新」,零錯誤訊號。
                logger.exception("盤前篩選 %s 非預期失敗(第 %d 次)", target, attempt)
                reason = "非預期失敗(見上方 traceback)"
            nxt = self._next_attempt_at()
            if nxt is None:
                self._give_up(
                    target, attempt, reason, f"下一次會落在 {_RETRY_UNTIL.strftime('%H:%M')} 之後"
                )
                return
            logger.warning(
                "盤前篩選 %s 第 %d 次%s;%s 再試", target, attempt, reason, nxt.strftime("%H:%M:%S")
            )
            await asyncio.sleep(_RETRY_SECS)

    # ---- 單次重算 ----

    @staticmethod
    def _require_date_echo(rows: list[dict], day: _dt.date, label: str) -> None:
        """資料日回聲閘(review F-07,breadth 第二道守門同款;J1 收單份):上游忽略
        日期參數 / 回錯日快取時回應是別日的列 —— 日 K 窗格會整批同一天(ratio 把單日
        漲幅複利 20 次)、當沖名單會是別日集合,兩者都與正常結果同形零訊號。
        `shrink_rows` 後 date 欄已丟,只能在 fetch 當下驗。"""
        if rows[0].get("date") != day.isoformat():
            raise BreadthFetchError(
                f"盤前篩選 {day} {label}資料日回聲不符({rows[0].get('date')!r}),視同取數失敗"
            )

    async def compute(self, target: _dt.date) -> list[ScreenCandidate]:
        """抓窗 → 三硬條件 → 全市場當沖資格 → 處置剔除。純結果,不落檔不寫群組、不改引擎狀態(CLI 共用)。

        `target` = 目標交易日(名單服務的交易日,通常是今天):EOD 窗自資料日(前一交易日)往回,
        當沖名單與處置股用 `target` 本人 —— 昨天剛停當沖的今天不會還在名單裡、昨天剛結束處置的
        今天能進、今天剛開始處置的今天被剔(W2 T4 #207)。"""
        final, _ = await self._compute_with_daytrade_rows(target)
        return final

    async def _compute_with_daytrade_rows(
        self, target: _dt.date
    ) -> tuple[list[ScreenCandidate], int]:
        """`compute` 的本體,多帶回過閘的當沖名單列數(`_run_once` 落檔當下一次的前值;round-1 F-01:
        用回值傳,不留 instance 欄位)。"""
        data_date = data_date_of(target, self._cal)
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
                self._require_date_echo(rows, d, "")
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
        # 當沖資格 = 單次全市場查詢(review F-02:「data_id 必填」是週六探測誤判,
        # 逐檔 fan-out ~60 次收斂成 1 次;口徑同 spec「最近交易日有列」,7 日回看退役)
        # 當沖名單抓**目標交易日**的(今天的正式名單,盤前先出;W2 T4 #207)
        dt_rows = await asyncio.to_thread(self._day_trading_fetch, self._token, target)
        await asyncio.sleep(_REQ_GAP_SECS)
        if not dt_rows:
            # 空集合拿去過濾會把**全部**候選當非當沖標的誤剔,群組被清空還零訊號 ——
            # 當日名單未發布視同取數失敗,走重試
            raise BreadthFetchError(f"盤前篩選 {target} 當沖名單尚無資料(FinMind 未更新?)")
        self._require_date_echo(dt_rows, target, "當沖名單")
        daytrade_rows = self._require_daytrade_complete(dt_rows, target)
        daytrade_ok = {sid for row in dt_rows if isinstance(sid := row.get("stock_id"), str)}
        disp_rows = await asyncio.to_thread(self._disposition_fetch, self._token, target)
        disposed = parse_active_disposition(disp_rows, target)  # 處置期間涵蓋**今天**
        final = apply_eligibility(cands, daytrade_ok=daytrade_ok, disposed=disposed)
        logger.info(
            "盤前篩選 %s(資料日 %s):硬條件 %d 檔 → 資格後 %d 檔(非當沖 %d / 處置 %d)",
            target,
            data_date,
            len(cands),
            len(final),
            sum(1 for c in cands if c.code not in daytrade_ok),
            sum(1 for c in cands if c.code in disposed),
        )
        return final, daytrade_rows

    @staticmethod
    def _prior_text(prior: int | None) -> str:
        return str(prior) if prior is not None else "無(用絕對下限)"

    def _require_daytrade_complete(self, dt_rows: list[dict], target: _dt.date) -> int:
        """相對閘(理由見 `_DAYTRADE_SHRINK_RATIO`):今天列數 < 前值 × 0.8(無前值 → < 絕對下限)
        → 可重試錯誤;過閘回列數(`_run_once` 落檔當下一次的前值)。"""
        n = len(dt_rows)
        prior = self._cached_daytrade_rows()
        floor = int(prior * _DAYTRADE_SHRINK_RATIO) if prior is not None else _DAYTRADE_MIN_ROWS
        if n < floor:
            logger.warning(
                "盤前篩選 %s 當沖名單只有 %d 列(前值 %s,門檻 %d),視同尚未發布完 —— "
                "名單若真的縮了,刪快取 %s 的 daytrade_rows 鍵可重置基準",
                target,
                n,
                self._prior_text(prior),
                floor,
                _CACHE_NAME,
            )
            raise BreadthFetchError(
                f"盤前篩選 {target} 當沖名單只有 {n} 列(前值 {self._prior_text(prior)},門檻 {floor}),"
                "視同尚未發布完"
            )
        return n

    async def _run_once(self, target: _dt.date) -> None:
        final, daytrade_rows = await self._compute_with_daytrade_rows(target)
        written = await self._write_group(final)
        prior = self._cached_daytrade_rows()
        self._write_cache(target, final, written, daytrade_rows)
        # 落檔**之後**才印(round-1 S-05):印了 = 前值已更新,對帳時不會誤讀
        logger.info(
            "盤前篩選 %s 當沖名單 %d 列(前值 %s)", target, daytrade_rows, self._prior_text(prior)
        )

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

    # ---- 快取(= 「這個目標交易日已完成」的判定依據)----

    def _cache_path(self) -> Path:
        return self._dir / _CACHE_NAME

    def _read_cache(self) -> dict | None:
        try:
            payload = json.loads(self._cache_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(payload, dict) or payload.get("_cache_version") != _CACHE_VERSION:
            return None
        return payload

    def _cached_target_date(self) -> _dt.date | None:
        payload = self._read_cache()
        if payload is None:
            return None
        try:
            return _dt.date.fromisoformat(payload["target_date"])
        except (ValueError, KeyError, TypeError):
            return None

    def _cached_daytrade_rows(self) -> int | None:
        """前一次成功落檔的當沖名單列數(相對閘的前值);缺鍵 / 非整數 → None(走絕對下限)。"""
        payload = self._read_cache()
        if payload is None:
            return None
        n = payload.get("daytrade_rows")
        return n if isinstance(n, int) and not isinstance(n, bool) else None

    def _write_cache(
        self,
        target: _dt.date,
        final: list[ScreenCandidate],
        written: list[str],
        daytrade_rows: int,
    ) -> None:
        payload = {
            "_cache_version": _CACHE_VERSION,
            "target_date": target.isoformat(),
            "data_date": data_date_of(target, self._cal).isoformat(),
            "computed_at": self._now_fn().isoformat(timespec="seconds"),
            "daytrade_rows": daytrade_rows,
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
