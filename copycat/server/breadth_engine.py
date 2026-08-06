"""家數帶 / 騰落線引擎(market-overview R2 design §5)—— SC-2 / SC-3。

編排層:每 10 秒問一次 FinMind 全市場快照 → 純函式層算家數 → 當日分鐘序列落檔 +
WS 廣播。純函式在 `copycat.market_breadth`,取數在 `copycat.server.breadth_fetch`,
本檔只負責節奏、快取、序列與失效表述。

**失效域隔離(SC-3)**:完全不碰 TC4 / ZMQ,`start()` 零網路 IO(restore 本地檔 +
起 poll task 即返回)—— FinMind 掛掉只讓家數面板 stale,boot 不被拖住、TC4 系零波及。

**trade_date 語意(design R1/R2,最容易寫錯的一處)**:append 與落檔**只在
快照時刻的日期 == 今天**時發生。跨午夜或假日重啟時 FinMind 會回上一交易日的收盤
快照,若照樣 append,那一天的完整序列會被單一格覆寫成一格 —— 檔案還在、格式還對、
畫面照畫,只有內容從整天縮成一點,沒有任何錯誤訊號。

**分鐘鍵**沿用 `index_engine.minute_key`(1K 終點標記 floor+1、域 0901–1330、
1331–1335 clamp):同一頁的指數分時圖用同一把尺,兩張圖的 x 軸才對得起來;域外
(盤後定盤 14:30、盤前)一律丟棄。
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
import os
import time as _time
from pathlib import Path
from typing import AsyncGenerator, Callable, TypeGuard

from copycat.breadth_config import BreadthConfig
from copycat.market_breadth import (
    assemble_universe,
    build_name_map,
    build_type_map,
    compute_breadth,
    dedup_sector_map,
    max_tick_datetime,
    parse_active_disposition,
)
from copycat.server.breadth_fetch import BreadthFetchError
from copycat.server.index_engine import minute_key
from copycat.server.ws import WsBroadcaster

logger = logging.getLogger(__name__)

#: 每 10 秒一則、單一面板 —— 32 則的積壓遠超過任何有意義的補送量
_CLIENT_QUEUE_MAX = 32
#: 對照表(TaiwanStockInfo / 處置股)快取壽命;一天打幾次而已
_MAP_TTL_SECS = 86_400.0
#: 對照表取數失敗後的最短重試間隔(quota 失敗改用 `config.quota_backoff_secs`)。
#: TaiwanStockInfo 是這條路上最重的 endpoint,以 poll 節奏(10s)重打壞掉的上游只會
#: 加速燒配額,而配額用盡的表現是整個面板跟著死(review P2-4)。
_MAP_RETRY_SECS = 60.0
#: 快照時刻可超前本機時鐘的容差;越過即視為髒 row(review P1-2)。10 分鐘 = 遠寬於
#: FinMind 的正常延遲與本機時鐘偏差,又足以擋掉「收盤時刻 / 未來日期」這類真髒值。
_TICK_FUTURE_TOLERANCE = _dt.timedelta(minutes=10)
#: 序列落檔格式版本;不相容改動時 +1(舊檔 restore 直接略過 → 空序列起步)
_FILE_VERSION = 1
#: 桶序 = `[limit_up, up, flat, down, limit_down]`,與 types.ts / 前端 x 軸同一份約定
_BUCKETS: tuple[str, ...] = ("limit_up", "up", "flat", "down", "limit_down")
#: 錨定 repo root(`__main__.LOG_DIR` 同慣例):cwd 相對會在子目錄起 server 時
#: 長出第二份 data/,而序列檔「換個地方存」的表現是重啟後序列莫名歸零
_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "market"

SnapshotFetch = Callable[[str], list[dict]]
StockInfoFetch = Callable[[str], list[dict]]
DispositionFetch = Callable[[str, _dt.date], list[dict]]


def _monotonic() -> float:
    """stale 與對照表 TTL 的時間基準(單調鐘,不受系統時間調整影響)。

    模組層一個名字而非建構子參數:類簽名由 design §5 釘死,而「經過 N 秒」這件事
    只有測試需要控制 —— `monkeypatch.setattr(breadth_engine, "_monotonic", fake)`
    即可推進時間,不必真 sleep 30 秒去驗一個門檻。
    """
    return _time.monotonic()


def _now() -> _dt.datetime:
    """`now_fn` 未注入時的本機牆上時鐘(模組層一個名字,與 `_monotonic` 同理由)。

    它同時決定「窗內與否」與「快照時刻的上界」,而 server route 測試沒有 now_fn 的
    注入點(引擎在 lifespan 內建構)—— 沒有這個名字的話,那些測試會跟著實跑時刻
    飄:同一份固定快照在 09:00 跑是「未來時刻」、在 11:00 跑是正常值。
    """
    return _dt.datetime.now()


def _parse_hhmm(value: str) -> _dt.time:
    """`"08:55"` → `time(8, 55)`;格式錯直接 raise(config 打錯字不該靜默套預設)。"""
    return _dt.datetime.strptime(value, "%H:%M").time()


def _is_bucket_row(value: object) -> TypeGuard[list[int]]:
    return (
        isinstance(value, list)
        and len(value) == len(_BUCKETS)
        and all(isinstance(v, int) and not isinstance(v, bool) for v in value)
    )


class BreadthEngine:
    """FinMind 全市場家數輪詢引擎;取數三元組由呼叫端注入(測試 fake / prod 真取數)。"""

    def __init__(
        self,
        *,
        token: str,
        config: BreadthConfig,
        snapshot_fetch: SnapshotFetch,
        stock_info_fetch: StockInfoFetch,
        disposition_fetch: DispositionFetch,
        data_dir: Path | None = None,
        today_fn: Callable[[], _dt.date] = _dt.date.today,
        now_fn: Callable[[], _dt.datetime] | None = None,
    ) -> None:
        self._token = token
        self._config = config
        self._snapshot_fetch = snapshot_fetch
        self._stock_info_fetch = stock_info_fetch
        self._disposition_fetch = disposition_fetch
        self._data_dir = data_dir if data_dir is not None else _DEFAULT_DATA_DIR
        self._today_fn = today_fn
        # 預設走模組層 `_now`(不是直接綁 `datetime.now`)—— 測試 monkeypatch 的是那個名字
        self._now_fn = now_fn if now_fn is not None else _now
        self._window = (_parse_hhmm(config.window_start), _parse_hhmm(config.window_end))

        # ---- scalar 狀態 ----
        self._trade_date: str | None = None
        self._as_of: str | None = None
        self._counts: dict[str, dict[str, int]] | None = None
        #: 全量逐檔 rows(漲跌停列表 / 類股熱力圖的原料 — R3 輪用)。
        #: 刻意**不進 `state()`**:本輪對外契約只有 counts + series,四千列 rows
        #: 每 10 秒進一次 REST payload 是純浪費。
        self.rows: list[dict] = []

        # ---- 當日分鐘序列(分鐘鍵 → point,last-wins)----
        self._series: dict[str, dict] = {}

        # ---- 對照表快取 ----
        self._sector_map: dict[str, str] = {}
        self._type_map: dict[str, str] = {}
        self._name_map: dict[str, str] = {}
        self._disposition: set[str] = set()
        self._info_at: float | None = None
        self._disp_at: float | None = None
        #: 上次成功刷新的**交易日**(單調鐘的 24h TTL 不隨換日到期;review P1-3)
        self._info_day: _dt.date | None = None
        self._disp_day: _dt.date | None = None
        #: 取數失敗後的重試不早於此單調時刻(review P2-4)
        self._info_retry_at: float | None = None
        self._disp_retry_at: float | None = None
        self._disposition_ok = False

        # ---- 節奏 / 失效 ----
        self._last_success: float | None = None
        self._fail_streak = 0
        self._quota = False

        self._task: asyncio.Task[None] | None = None
        self._ws = WsBroadcaster(maxsize=_CLIENT_QUEUE_MAX)

    # ---- 生命週期 ----

    async def start(self) -> None:
        """restore 當日落檔 + 起 poll task。**零網路 IO** —— 首輪 fetch 在 task 上跑,
        FinMind 慢或掛都不得延後 lifespan(design R6)。"""
        self._restore()
        self._task = asyncio.create_task(self._poll_loop())

    async def close(self) -> None:
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # ---- 對外狀態 ----

    def state(self) -> dict:
        """REST 全量(`GET /api/market/breadth`)。`counts` 為 None = 首輪未成 = 載入中。"""
        return {
            "enabled": True,
            "trade_date": self._trade_date,
            "as_of": self._as_of,
            "stale": self._stale(),
            "counts": self._counts,
            "series": self._series_list(),
        }

    def payload(self, last_minute: dict | None = None) -> dict:
        """WS scalar 訊息;`last_minute` 只在本輪真的 append 了一格時帶值。"""
        return {
            "type": "breadth",
            "trade_date": self._trade_date,
            "as_of": self._as_of,
            "stale": self._stale(),
            "counts": self._counts,
            "last_minute": last_minute,
        }

    def stream(self) -> AsyncGenerator[dict, None]:
        # 連線先送當前快照(`ws_corr` / `ws_river` / `stock_engine.stream` 同慣例):
        # 沒有種子的話,新 client 要等到下一輪 poll 才有第一則,盤後開站則永遠是空的。
        return self._ws.stream([self.payload()])

    # ---- poll loop ----

    async def _poll_loop(self) -> None:
        """首圈無條件跑一輪(盤後開站也要有數字),之後只在台北窗內取數。

        `except Exception` 是**任務存活邊界**(index `_mis_loop` 同款):一輪內的
        失敗分類已在 `_run_cycle` 內做完,這裡只保證 poll task 不會因為漏網的例外
        整條死掉 —— 死掉的表現是「面板凍在最後一則,沒有任何錯誤」。
        """
        first = True
        while True:
            try:
                if first or self._in_window():
                    await self._run_cycle()
            except Exception:
                logger.exception("breadth poll loop 非預期失敗(續行)")
            first = False
            await asyncio.sleep(self._effective_interval())

    async def _run_cycle(self) -> None:
        """一輪:快照 → 對照表 → 統計 → append/落檔 → 廣播(成敗皆廣播一則)。"""
        last_minute: dict | None = None
        rows = await self._fetch_snapshot()
        if rows is not None:
            await self._refresh_maps()
            last_minute = self._apply(rows)
        self._ws.publish(self.payload(last_minute))

    async def _fetch_snapshot(self) -> list[dict] | None:
        try:
            return await asyncio.to_thread(self._snapshot_fetch, self._token)
        except BreadthFetchError as e:
            logger.warning("breadth snapshot 取數失敗(quota=%s):%s", e.quota, e)
            self._fail(quota=e.quota)
        except Exception:
            # 注入的取數層不保證只丟 BreadthFetchError;漏接會讓退避與 stale 完全不動
            logger.exception("breadth snapshot 取數非預期失敗(該輪視同失敗)")
            self._fail(quota=False)
        return None

    async def _refresh_maps(self) -> None:
        """對照表 24h TTL:**成功才寫入與刷時戳**,失敗保前值 → 退避後重試。

        失敗時刷時戳的話,冷啟動那次失敗會把 degraded 鎖死 24 小時(白名單空 →
        家數恆為 0),而每一輪都「成功」地算出一組全零 —— neigui「失敗不寫 cache」
        同語意(design R9)。取數**成功但空表**同樣視為失敗:空對照表會把整個宇宙
        剃光,跟拿不到沒有差別(空表不設退避 —— 那是上游回了合法回應,下輪即重試)。
        """
        now = _monotonic()
        today = self._today_fn()
        if self._map_due(self._info_at, self._info_day, self._info_retry_at, now, today):
            await self._refresh_stock_info()
        if self._map_due(self._disp_at, self._disp_day, self._disp_retry_at, now, today):
            await self._refresh_disposition()

    @staticmethod
    def _map_due(
        at: float | None,
        day: _dt.date | None,
        retry_at: float | None,
        now: float,
        today: _dt.date,
    ) -> bool:
        """該不該重取這張對照表。三個條件的**順序即語意**:

        1. 退避中 → 一律不取(失敗剛發生,再打也是同一個壞上游)。
        2. 上次成功不是今天(含冷啟動 `day is None`)→ 取。TTL 走單調鐘,24h 不隨
           交易日換 —— 早上 09:00 起的 server 到隔天 09:00 才過期,而處置股名單**每天
           都變**,那一整個交易日都會沿用昨天的名單(review P1-3)。
        3. 其餘照 TTL。
        """
        if retry_at is not None and now < retry_at:
            return False
        if day != today:
            return True
        return at is None or now - at >= _MAP_TTL_SECS

    def _map_backoff(self, quota: bool) -> float:
        return self._config.quota_backoff_secs if quota else _MAP_RETRY_SECS

    async def _refresh_stock_info(self) -> None:
        try:
            rows = await asyncio.to_thread(self._stock_info_fetch, self._token)
        except BreadthFetchError as e:
            wait = self._map_backoff(e.quota)
            logger.warning("breadth stock_info 取數失敗(保前值,%.0fs 後重試):%s", wait, e)
            self._info_retry_at = _monotonic() + wait
            return
        except Exception:
            logger.exception(
                "breadth stock_info 取數非預期失敗(保前值,%.0fs 後重試)", _MAP_RETRY_SECS
            )
            self._info_retry_at = _monotonic() + _MAP_RETRY_SECS
            return
        if not rows:
            logger.warning("breadth stock_info 回空表(保前值,下輪重試)")
            return
        self._sector_map = dedup_sector_map(rows)
        self._type_map = build_type_map(rows)
        self._name_map = build_name_map(rows)
        self._info_at = _monotonic()
        self._info_day = self._today_fn()
        self._info_retry_at = None

    async def _refresh_disposition(self) -> None:
        today = self._today_fn()
        try:
            rows = await asyncio.to_thread(self._disposition_fetch, self._token, today)
        except BreadthFetchError as e:
            # 「保前值」而非「以空集合續行」:前一份名單仍生效,冷啟動時才真的是空集合
            wait = self._map_backoff(e.quota)
            logger.warning(
                "breadth 處置股取數失敗(保前值(冷啟動為空),標 degraded,%.0fs 後重試):%s",
                wait,
                e,
            )
            self._disposition_ok = False
            self._disp_retry_at = _monotonic() + wait
            return
        except Exception:
            logger.exception(
                "breadth 處置股取數非預期失敗(保前值(冷啟動為空),標 degraded,%.0fs 後重試)",
                _MAP_RETRY_SECS,
            )
            self._disposition_ok = False
            self._disp_retry_at = _monotonic() + _MAP_RETRY_SECS
            return
        # 空 list 是合法結果(當下沒有處置中的股票),與 stock_info 的空表不同
        self._disposition = parse_active_disposition(rows, today)
        self._disposition_ok = True
        self._disp_at = _monotonic()
        self._disp_day = today
        self._disp_retry_at = None

    def _apply(self, rows: list[dict]) -> dict | None:
        """快照 rows → counts / as_of / trade_date / 序列;回傳本輪 append 的那一格。"""
        # 上界 = 本機時鐘 + 容差:單一列偶發帶著收盤時刻時,`max()` 會讓整份快照的
        # 時刻被那一列決定,分鐘鍵因此恆定 → 整日序列塌成一格(review P1-2)
        dt = max_tick_datetime(rows, upper_bound=self._now_fn() + _TICK_FUTURE_TOLERANCE)
        if dt is None:
            # 時刻推不出來就沒有 as_of 也沒有分鐘鍵,硬記會標成錯的時間(design R9)
            logger.warning("breadth 快照無可解析時刻(%d 列),該輪視同失敗", len(rows))
            self._fail(quota=False)
            return None

        universe = assemble_universe(rows, self._sector_map, self._disposition)
        breadth = compute_breadth(universe, self._type_map, self._name_map)
        if breadth is None:
            logger.warning(
                "breadth 統計全空(快照 %d 列 / universe %d 檔),該輪視同失敗",
                len(rows),
                len(universe),
            )
            self._fail(quota=False)
            return None

        trade_date = dt.date().isoformat()
        today = self._today_fn().isoformat()
        # 日期變更的三分法(review P1-1)。清序列的條件必須與 append 的條件對稱:
        # 「與前值不同」就清、但只有「== 今天」才 append —— 兩者不對稱時,一輪拿到
        # 上一交易日(跨午夜 / 假日重啟 / 上游回舊日)就會把當天已累積的整段序列連同
        # 落檔一起抹掉,而其後每一輪又都不 append,畫面從此空著且零錯誤訊號。
        adopt_date = True
        if self._trade_date is None or trade_date == self._trade_date:
            pass  # 首次 / 同日:照常
        elif trade_date == today:
            logger.info("breadth 換日 %s → %s(清當日序列)", self._trade_date, trade_date)
            self._series = {}
        else:
            adopt_date = False
            logger.warning(
                "breadth 快照日期 %s 既非今日 %s 也非序列日 %s:不採用日期變更(序列保留)",
                trade_date,
                today,
                self._trade_date,
            )
        counts = {"twse": breadth["twse"], "tpex": breadth["tpex"]}
        if adopt_date:
            self._trade_date = trade_date
        self._as_of = dt.strftime("%H:%M:%S")
        self._counts = counts
        self.rows = breadth["rows"]
        self._fail_streak = 0
        self._quota = False
        self._last_success = _monotonic()
        if not adopt_date:
            return None  # scalar 已更新;序列與落檔一概不動
        return self._append(dt, trade_date, counts)

    def _append(
        self, dt: _dt.datetime, trade_date: str, counts: dict[str, dict[str, int]]
    ) -> dict | None:
        if trade_date != self._today_fn().isoformat():
            # 上一交易日的快照(跨午夜 / 假日重啟):scalar 更新,序列與檔案一概不動
            return None
        key = minute_key(dt.strftime("%H%M%S"), utc=False)
        if key is None:
            return None  # 分鐘域外(盤後定盤 14:30 / 盤前)
        point = {
            "t": key,
            "twse": [counts["twse"][b] for b in _BUCKETS],
            "tpex": [counts["tpex"][b] for b in _BUCKETS],
        }
        self._series[key] = point  # 同分鐘 last-wins
        self._save()
        return point

    def _fail(self, *, quota: bool) -> None:
        self._fail_streak += 1
        self._quota = quota

    def _effective_interval(self) -> float:
        """下一圈的等待秒數:成功 = poll_secs;連續失敗 10→20→40→60;402 直接 300。"""
        if self._fail_streak == 0:
            return self._config.poll_secs
        if self._quota:
            return self._config.quota_backoff_secs
        # 指數**先夾制再取冪**:`2 ** 1999` 是合法 int,但乘上 float 會 OverflowError,
        # 而那行在 `_poll_loop` 的 `await asyncio.sleep(...)`(傘罩外)→ poll task 當場
        # 死透、面板只是凍住(review P2-2)。6 已遠超上限所需(10×64 = 640s > 60s)。
        grown = self._config.poll_secs * (2 ** min(self._fail_streak - 1, 6))
        return min(grown, self._config.backoff_max_secs)

    def _in_window(self) -> bool:
        t = self._now_fn().time()
        return self._window[0] <= t <= self._window[1]

    def _stale(self) -> bool:
        """degraded(對照表殘缺)恆 stale;其餘只在**窗內**才以「距上次成功多久」判。

        窗外沒有新資料是正常態 —— 盤後把整片家數標成延遲只會訓練人忽略這個旗標。
        """
        if not self._sector_map or not self._disposition_ok:
            return True
        if not self._in_window():
            return False
        if self._last_success is None:
            return True
        return _monotonic() - self._last_success > self._config.stale_secs

    # ---- 序列落檔 / restore ----

    def _series_list(self) -> list[dict]:
        return [self._series[k] for k in sorted(self._series)]

    def _series_path(self, trade_date: str) -> Path:
        return self._data_dir / f"breadth-{trade_date}.json"

    def _save(self) -> None:
        """tmp + `os.replace` 原子寫。落檔失敗只降級(記憶體序列照在),不得拖垮 poll。"""
        trade_date = self._trade_date
        if trade_date is None:  # pragma: no cover - _append 已保證有值
            return
        path = self._series_path(trade_date)
        payload = {
            "_version": _FILE_VERSION,
            "trade_date": trade_date,
            "series": self._series_list(),
        }
        tmp = path.with_name(f"{path.name}.tmp")
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
        except OSError as e:
            logger.warning("breadth 序列落檔失敗(續行):%r", e)

    def _restore(self) -> None:
        """讀 `breadth-<today>.json` 還原 trade_date + series;壞檔一律空序列起步。

        檔名鍵 = `today_fn()`(與 append 條件同源)—— 讀「今天」的檔才可能是要續寫的
        那一份;讀到別天的檔會讓換日判定與 append 條件互相矛盾。
        """
        path = self._series_path(self._today_fn().isoformat())
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError) as e:
            logger.warning("breadth 序列檔讀取失敗,以空序列啟動:%r", e)
            return
        if not isinstance(payload, dict) or payload.get("_version") != _FILE_VERSION:
            logger.warning("breadth 序列檔版本不符,以空序列啟動:%s", path)
            return
        trade_date = payload.get("trade_date")
        series = payload.get("series")
        if not isinstance(trade_date, str) or not isinstance(series, list):
            logger.warning("breadth 序列檔形狀不符,以空序列啟動:%s", path)
            return
        restored: dict[str, dict] = {}
        for point in series:
            if not isinstance(point, dict):
                continue
            key = point.get("t")
            twse = point.get("twse")
            tpex = point.get("tpex")
            if not isinstance(key, str) or not _is_bucket_row(twse) or not _is_bucket_row(tpex):
                continue
            restored[key] = {"t": key, "twse": list(twse), "tpex": list(tpex)}
        self._trade_date = trade_date
        self._series = restored
        logger.info("breadth restore %s:%d 分鐘", trade_date, len(restored))
