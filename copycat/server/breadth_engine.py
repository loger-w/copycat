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
        now_fn: Callable[[], _dt.datetime] = _dt.datetime.now,
    ) -> None:
        self._token = token
        self._config = config
        self._snapshot_fetch = snapshot_fetch
        self._stock_info_fetch = stock_info_fetch
        self._disposition_fetch = disposition_fetch
        self._data_dir = data_dir if data_dir is not None else _DEFAULT_DATA_DIR
        self._today_fn = today_fn
        self._now_fn = now_fn
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
        """對照表 24h TTL:**成功才寫入與刷時戳**,失敗保前值、不動時戳 → 下輪即重試。

        失敗時刷時戳的話,冷啟動那次失敗會把 degraded 鎖死 24 小時(白名單空 →
        家數恆為 0),而每一輪都「成功」地算出一組全零 —— neigui「失敗不寫 cache」
        同語意(design R9)。取數**成功但空表**同樣視為失敗:空對照表會把整個宇宙
        剃光,跟拿不到沒有差別。
        """
        now = _monotonic()
        if self._info_at is None or now - self._info_at >= _MAP_TTL_SECS:
            await self._refresh_stock_info()
        if self._disp_at is None or now - self._disp_at >= _MAP_TTL_SECS:
            await self._refresh_disposition()

    async def _refresh_stock_info(self) -> None:
        try:
            rows = await asyncio.to_thread(self._stock_info_fetch, self._token)
        except BreadthFetchError as e:
            logger.warning("breadth stock_info 取數失敗(保留前值,下輪重試):%s", e)
            return
        except Exception:
            logger.exception("breadth stock_info 取數非預期失敗(保留前值,下輪重試)")
            return
        if not rows:
            logger.warning("breadth stock_info 回空表(保留前值,下輪重試)")
            return
        self._sector_map = dedup_sector_map(rows)
        self._type_map = build_type_map(rows)
        self._name_map = build_name_map(rows)
        self._info_at = _monotonic()

    async def _refresh_disposition(self) -> None:
        today = self._today_fn()
        try:
            rows = await asyncio.to_thread(self._disposition_fetch, self._token, today)
        except BreadthFetchError as e:
            logger.warning("breadth 處置股取數失敗(以空集合續行,標 degraded):%s", e)
            self._disposition_ok = False
            return
        except Exception:
            logger.exception("breadth 處置股取數非預期失敗(以空集合續行,標 degraded)")
            self._disposition_ok = False
            return
        # 空 list 是合法結果(當下沒有處置中的股票),與 stock_info 的空表不同
        self._disposition = parse_active_disposition(rows, today)
        self._disposition_ok = True
        self._disp_at = _monotonic()

    def _apply(self, rows: list[dict]) -> dict | None:
        """快照 rows → counts / as_of / trade_date / 序列;回傳本輪 append 的那一格。"""
        dt = max_tick_datetime(rows)
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
        if self._trade_date is not None and self._trade_date != trade_date:
            logger.info("breadth 換日 %s → %s(清當日序列)", self._trade_date, trade_date)
            self._series = {}
        counts = {"twse": breadth["twse"], "tpex": breadth["tpex"]}
        self._trade_date = trade_date
        self._as_of = dt.strftime("%H:%M:%S")
        self._counts = counts
        self.rows = breadth["rows"]
        self._fail_streak = 0
        self._quota = False
        self._last_success = _monotonic()
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
        grown = self._config.poll_secs * (2 ** (self._fail_streak - 1))
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
