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

**產業鏈(R4 design §4.3/§5)**:第三條背景 task —— `TaiwanStockIndustryChain`
的 7 天 TTL 快取,成功即換表 + 落檔。刷新**刻意不 await**:那張表壞掉或上游卡住
只該讓類股面板 degraded,家數輪一秒都不能被它拖住(§1 失效域的前提)。載入紀律
是「**過期也先用**」—— stale 的產業對照勝於整片空白,而空白與「FinMind 掛了」
在畫面上完全同形。取數成功但 parse 後為空(欄位語意變 / 上游回殘表)時**不換表
也不落檔**:照樣換的話,一份可用的舊快取會被空表覆寫並固化到磁碟。

**全市場鎖板事件(R4 design §6)**:每輪 append 成功後對 rows 做一次**對帳** ——
比的是「事件流已對外宣告的狀態」(`_mkt_last_emitted`,重啟時自 jsonl 回放)而不是
「上一輪的實況」。差別在兩個邊界上是致命的:開盤即鎖(一價到底)沒有轉移可偵測、
盤中重啟後記憶體是空的 —— 兩者在 raw 轉移偵測下都靜默漏發,而漏發的表現就是畫面
少一列。冷卻(`event_cooldown_secs`)只**延後**對帳不丟棄,所以抖動有上界而終態
仍收斂到實況。

**連板數(R3 design §3.3)**:另有一條每日一次的背景 task —— FinMind EOD 回看
10 個交易日算連續漲停日數,成果落 `streaks-<today>.json`。與 poll 迴圈共用同一個
FinMind 失效域(壞了只讓連板欄 null),排程狀態刻意與成果分離:`_streak_armed_day`
(今日已排程過,不論成敗)決定要不要再起 task,`_streaks_day`(算成功的那個 today)
決定成果能不能用 —— 兩者合一的話,失敗會讓「嘗試上限」形同虛設(整天重跑燒配額)。
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
import os
import time as _time
from pathlib import Path
from typing import AsyncGenerator, Callable, Protocol, TypeGuard

from copycat.breadth_config import BreadthConfig
from copycat.limit_streaks import (
    STREAK_WINDOW_DAYS,
    compute_day_limitups,
    compute_prev_streaks,
)
from copycat.market_breadth import (
    assemble_universe,
    build_name_map,
    build_type_map,
    compute_breadth,
    dedup_sector_map,
    max_tick_datetime,
    parse_active_disposition,
)
from copycat.sector_rotation import (
    ChainMap,
    compute_sector_members,
    compute_sector_rotation,
    rows_to_chain_map,
)
from copycat.server.breadth_fetch import BreadthFetchError
from copycat.server.chain_store import load_chain, save_chain
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

# ---- 連板數(streak)重算 ----
#: streak 快取格式版本(與序列檔各自獨立;不相容改動時 +1 → 舊檔略過即重算)
_STREAK_FILE_VERSION = 1
#: 單日 EOD 的最低列數;**低於此視同取數失敗而非假日**。實測 2026-08-05 全市場單日
#: 42,074 列(4 位普通股 2,334 檔),門檻取 ~0.6×。部分截斷若被當成假日跳過,那一天
#: 就從回看窗裡消失 —— 連板數靜默高估,且會被當日快取固化(design R4/R16)。
_DAILY_MIN_ROWS = 25_000
#: 06:00 前不武裝:T-1 的 EOD 尚未發布時重算,T-1 會被當假日跳過而該輪**成功**,
#: 盤中判式仍 +1 → 整天連板數少 1 並落檔固化(design R15)。
_STREAK_ARM_TIME = _dt.time(6, 0)
#: 自 day−1 起往回掃的日曆日上限(容得下長假;收不滿即 span < 10,封頂語意照樣成立)
_STREAK_SCAN_CAL_DAYS = 25
#: 單一武裝日內的嘗試上限;用完當日放棄(連板欄 null),不整天燒配額
_STREAK_MAX_ATTEMPTS = 10
#: 相鄰兩個「收到的交易日」容許的日曆間距上限(春節極端連假 ~9–11 日);超過代表
#: 中間有整段真交易日被當假日吃掉 → 該輪不採用
_STREAK_GAP_CAL_DAYS = 12
#: 逐日 request 間隔 / 重試間隔。**模組層名字**是為了測試 monkeypatch 成 0
#: (`_monotonic` 同理由):要驗退避不該真的等 60 秒。
_STREAK_REQ_GAP_SECS = 0.3
_STREAK_RETRY_SECS = 60.0

# ---- 產業鏈(chain)刷新 ----
#: chain 快取檔名(`<data_dir>/industry_chain.json`;格式與讀寫在 `chain_store`)
_CHAIN_FILE = "industry_chain.json"

# ---- 全市場鎖板事件(diff)----
#: 事件 kind。與自選股那條路的 `limit_lock` / `limit_open` **只差前綴**且刻意如此:
#: hub 的 seed 回放依這兩個字串把兩條路分開(signal_hub `_MARKET_LOCK` 同值)。
_MARKET_LOCK = "market_limit_lock"
_MARKET_OPEN = "market_limit_open"

SnapshotFetch = Callable[[str], list[dict]]
StockInfoFetch = Callable[[str], list[dict]]
DispositionFetch = Callable[[str, _dt.date], list[dict]]
DailyPricesFetch = Callable[[str, _dt.date], list[dict]]
ChainFetch = Callable[[str], list[dict]]


class MarketSignalSink(Protocol):
    """訊號匯流排掛點(實作 = `copycat.server.signal_hub.SignalHub`;測試注入 fake)。

    結構型協定而非直接 import `SignalHub`(`stock_engine.SignalSink` 同款):引擎不該
    為了型別去相依整個訊號層,測試也才能注入不繼承任何東西的替身。**全部同步方法** ——
    這條路徑跑在 poll 輪內,不 await。
    """

    def publish_market_events(self, events: list[dict], *, trade_date: str) -> None: ...

    def market_event_state(
        self, trade_date: str
    ) -> tuple[dict[tuple[str, str], bool], dict[tuple[str, str, str], int]]: ...


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


async def _cancel(task: asyncio.Task[None] | None) -> None:
    """收攤一條背景 task(poll / streak 同款):cancel 後等它真的結束。"""
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


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
        daily_fetch: DailyPricesFetch | None = None,
        chain_fetch: ChainFetch | None = None,
        data_dir: Path | None = None,
        today_fn: Callable[[], _dt.date] = _dt.date.today,
        now_fn: Callable[[], _dt.datetime] | None = None,
    ) -> None:
        self._token = token
        self._config = config
        self._snapshot_fetch = snapshot_fetch
        self._stock_info_fetch = stock_info_fetch
        self._disposition_fetch = disposition_fetch
        #: None = 連板數停用(rows 端點照常,`streak` 恆 null)
        self._daily_fetch = daily_fetch
        #: None = 類股輪動停用(`sector_state().rotation` 恆 null,家數面板不受影響)
        self._chain_fetch = chain_fetch
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
        #: 每 10 秒進一次 REST payload 是純浪費(`rows_state()` 才給)。
        self.rows: list[dict] = []
        #: `self.rows` 的資料日 —— 與 `self.rows` **同步無條件更新**。連板判式不得用
        #: `_trade_date`:`_apply` 的 `adopt_date=False` 路徑會讓它與 rows 脫鉤
        #: (rows 是上一交易日的,`_trade_date` 還停在今日)→ 誤判成「今日盤中」再 +1。
        self._rows_date: str | None = None
        # ---- 連板數:成果 vs 排程(design R13,兩組不可合一)----
        self._streaks: dict[str, int] = {}
        self._streaks_day: str | None = None  # 這份成果是為哪個 today 算的
        self._streaks_end: str | None = None  # 最新資料日(= dates[0])
        self._streaks_dates: list[str] = []  # 實收交易日(新→舊),供稽核與 span
        self._streaks_span = 0  # 實收交易日數(= streak 的封頂值)
        self._streaks_skipped: set[str] = set()  # 掃描中被當假日跳過的日期(R15 guard)
        self._streak_armed_day: str | None = None  # 今日已排程過(不論成敗)
        self._streak_task: asyncio.Task[None] | None = None
        self._streak_attempts = 0  # 武裝日內的嘗試計數
        #: 武裝日內跨重試重用的逐日成果(日期 → 漲停集合;None = 空回應 = 假日候選)。
        #: 每日 EOD 是 MB 級回應而重試是整輪從頭掃 —— 沒有它,第 25 日才失敗會把前 24 日
        #: 各重抓 10 遍,而配額燒光的表現是**整個**家數面板跟著死(review R3-BE-2)。
        #: 武裝時清空:同一日期的 EOD 不會變,但成果只服務當次武裝日的窗。
        self._streak_memo: dict[str, set[str] | None] = {}

        # ---- 產業鏈 / 類股輪動(design §4.3;成果 vs 排程同樣分離)----
        self._chain_map: ChainMap = {}
        #: **epoch**(不是單調鐘):TTL 要跨重啟算得準,而單調鐘的原點每次重啟都不同。
        #: None = 從未成功(含快取檔壞掉)→ 武裝判定視同過期。
        self._chain_fetched_at: float | None = None
        self._chain_task: asyncio.Task[None] | None = None
        #: 取數失敗後的重試不早於此**單調**時刻(對照表的 `_info_retry_at` 同語意)
        self._chain_retry_at: float | None = None
        #: 最近一輪成功的 rotation(None = chain 缺 / 首輪未成 → 面板 degraded)
        self._rotation: dict | None = None
        #: members drill-down 的原料 = `assemble_universe` 輸出(**不是** `self.rows`:
        #: 後者的量欄已收成 `volume_ratio`,分子分母不可再同步剔除)
        self._universe_rows: list[dict] = []

        # ---- 全市場鎖板事件的對帳狀態(design §6.2)----
        #: `(code, direction)` → **事件流已對外宣告的**鎖定狀態(不是「當下實況」)。
        #: 兩者的差就是還沒發出去的帳,對帳制的全部語意都建立在這個區別上。
        self._mkt_last_emitted: dict[tuple[str, str], bool] = {}
        #: `_mkt_last_emitted` 服務的資料日;不符即重 seed(首輪 / 換日 / 重啟)
        self._mkt_emitted_date: str | None = None
        #: `(code, kind, direction)` → 冷卻**單調** deadline。冷卻只延後對帳不丟棄
        self._mkt_cooldown: dict[tuple[str, str, str], float] = {}
        #: `(code, kind, direction)` → 當日第 N 次(seed 自 jsonl,重啟後不從 1 重數)
        self._mkt_touch: dict[tuple[str, str, str], int] = {}
        #: 未 attach 時整條路早退:發布通道與狀態機推進不得解耦(design R2-1)
        self._signal_hub: MarketSignalSink | None = None

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

    # ---- 訊號匯流排掛點(鏡射 `stock_engine`)----

    def attach_signal_hub(self, hub: MarketSignalSink) -> None:
        self._signal_hub = hub

    def detach_signal_hub(self) -> None:
        """摘掉掛點(hub 收攤前呼叫):對已收攤的 hub 繼續發事件 = 靜默全丟。"""
        self._signal_hub = None

    # ---- 生命週期 ----

    async def start(self) -> None:
        """restore 本地落檔(序列 + streak + chain)+ 起 poll task。**零網路 IO** ——
        首輪 fetch 在 task 上跑,FinMind 慢或掛都不得延後 lifespan(design R6)。

        streak / chain task 刻意**不在這裡起**:武裝條件含時間閘與 TTL,交給
        `_poll_loop` 每圈檢查才只有一處判定(start() 另起一份就會繞過那些閘)。
        """
        self._restore()
        self._restore_streaks()
        self._restore_chain()
        self._task = asyncio.create_task(self._poll_loop())

    async def close(self) -> None:
        task, self._task = self._task, None
        streak, self._streak_task = self._streak_task, None
        chain, self._chain_task = self._chain_task, None
        await _cancel(task)
        await _cancel(streak)
        await _cancel(chain)

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

    def rows_state(self) -> dict:
        """REST 全量逐檔(`GET /api/market/breadth/rows`)—— **連板算術只在這裡**。

        `streak` 三值語意:int(含今日的連板數,僅 `limit_up` 列)/ null(非漲停列、
        未就緒、停用、或 rows 資料日與 streak 資料日的關係不明)。前端零日期推理。

        日期基準 = `_rows_date`(rows 的資料日),不是 `_trade_date`:
        - `rows_date > data_end` → rows 是今日盤中,昨日止的 streak 要 +1。
        - `rows_date == data_end` → rows 是上一交易日的收盤快照,該日**已在** streak
          內(盤前 / 假日開站),再 +1 就是憑空多一板。
        - `rows_date ∈ skipped` → 那天在掃描時被當假日跳過,關係不明 → null(R15)。
        """
        today = self._today_fn().isoformat()
        # 綁區域變數再比較:pyright basic 不把「經 bool 變數的 narrowing」傳遞下去,
        # `rows_date > self._streaks_end` 會報 reportOptionalOperand(禁 type: ignore)
        end = self._streaks_end
        ready = self._streaks_day == today and end is not None
        rows_date = self._rows_date
        rows_out: list[dict] = []
        for row in self.rows:
            streak: int | None = None
            capped = False
            if ready and end is not None and row["limit_up"] and rows_date is not None:
                prev = self._streaks.get(row["stock_id"], 0)
                if rows_date in self._streaks_skipped:
                    pass
                elif rows_date > end:
                    streak = prev + 1
                elif rows_date == end:
                    streak = max(prev, 1)
                # rows_date < data_end(理論不可能)→ 保持 None
                if streak is not None and prev >= self._streaks_span:
                    capped = True  # streak 撞到回看窗邊緣 → 前端顯示「N+ 板」
            rows_out.append({**row, "streak": streak, "streak_capped": capped})
        return {
            "enabled": True,
            "trade_date": rows_date,
            "as_of": self._as_of,
            "stale": self._stale(),
            "streaks_ready": ready,
            "rows": rows_out,
        }

    def sector_state(self) -> dict:
        """REST 全量類股輪動(`GET /api/market/sector`)。`rotation` None = 未就緒。

        日期基準 = `_rows_date`(與 rotation 同一輪的資料日),不是 `_trade_date`:
        `adopt_date=False` 路徑會讓後者與 rows 脫鉤,而 rotation 是從那一輪的
        universe 算的 —— 報錯日期的表現是「畫面全對、只有標頭日期是別天的」。
        """
        return {
            "enabled": True,
            "trade_date": self._rows_date,
            "as_of": self._as_of,
            "stale": self._stale(),
            "rotation": self._rotation,
        }

    def sector_members(self, industry: str, sub_industry: str | None) -> dict | None:
        """成員股 drill-down;未知 industry / sub_industry → None(呼叫端轉 404)。"""
        return compute_sector_members(
            self._universe_rows,
            self._chain_map,
            self._name_map,
            industry,
            sub_industry,
        )

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
                # 武裝檢查在傘罩**內**、窗 gate **外**:盤前(窗外)也要能重算,而它
                # 拋例外絕不能殺掉整條 poll task —— 那會讓家數面板為了連板數這條旁支
                # 凍在最後一則且零錯誤訊號(review R9)。
                self._maybe_arm_streaks()
                self._maybe_arm_chain()
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
        as_of = dt.strftime("%H:%M:%S")
        self._as_of = as_of
        self._counts = counts
        self.rows = breadth["rows"]
        # 與 rows 同行、**無條件**更新(含 adopt_date=False 路徑)—— 這正是它存在的
        # 理由:rows 換了而日期沒換的話,連板判式會拿舊日期去比 data_end(R14)
        self._rows_date = trade_date
        # 類股輪動與 rows 同輪同源(design §5):`sector_state()` 報的 trade_date /
        # as_of 就是這一輪的,rotation 落後一輪的話兩者會在畫面上互相矛盾
        self._universe_rows = universe
        self._rotation = compute_sector_rotation(universe, self._chain_map)
        self._fail_streak = 0
        self._quota = False
        self._last_success = _monotonic()
        if not adopt_date:
            return None  # scalar 已更新;序列與落檔一概不動
        point = self._append(dt, trade_date, counts)
        if point is not None:
            # 事件的觸發 gate = **append 成功**(design §6.3):盤前試撮輪(分鐘域外)
            # 與他日快照輪天然不觸發,「試撮殘留假事件」整個分支因此不存在。
            # 傘罩:事件流是旁支,它炸掉不得把家數輪一起帶走(逐列容錯在裡面另有一層)。
            try:
                self._diff_limit_events(trade_date, breadth["rows"], as_of)
            except Exception:
                logger.exception("breadth 廣度事件對帳非預期失敗(本輪事件丟棄,家數不受影響)")
        return point

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

    # ---- 全市場鎖板事件 diff(design §6.3 / §6.4)----

    def _diff_limit_events(self, trade_date: str, rows_out: list[dict], as_of: str) -> None:
        """`compute_breadth` 的 rows 對帳 → 鎖板 / 開板事件批次交給匯流排。

        **入參是 `compute_breadth` 的輸出**(帶 `limit_*` 與 `name`),不是 `_apply` 收到的
        原始快照 —— 餵錯那份的表現是事件流永遠空著,而空事件流與「今天沒人鎖板」同形,
        所以缺鍵在收尾記一則 warning(逐列記會在四千列的輪次把 log 洗掉)。

        `last_emitted` = 事件流**已對外宣告**的狀態(不是當下實況):
        - 開盤首輪 seed 空 → 一價到底的檔照發 lock(raw 轉移偵測會靜默漏掉)。
        - 重啟 seed 自 jsonl 回放 → 已發過的不重發、停機期間的轉移補發一則。
        - 冷卻中**只跳過本輪、不動 `last_emitted`** → 帳還欠著,冷卻一過自然補發,
          事件流終態恆收斂到實況(冷卻是抖動上界,不是丟棄)。
        """
        hub = self._signal_hub
        if hub is None:
            # 未 attach:不 seed、不 latch 日別、不動任何狀態(design R2-1)。推進了狀態
            # 等於把這些轉移當成「已發布」,當日不再回放 seed → 開盤那一批永遠不見。
            return
        if self._mkt_emitted_date != trade_date:
            self._mkt_last_emitted, self._mkt_touch = hub.market_event_state(trade_date)
            self._mkt_cooldown.clear()  # 昨日的冷卻不得壓掉今日開盤的第一則
            self._mkt_emitted_date = trade_date
            logger.info(
                "breadth 廣度事件 seed %s:%d 檔已發布狀態 / %d 桶計數",
                trade_date,
                len(self._mkt_last_emitted),
                len(self._mkt_touch),
            )

        now = _monotonic()
        cooldown = self._config.event_cooldown_secs
        events: list[dict] = []
        unjudged = 0
        for row in rows_out:
            try:
                if "limit_judged" not in row:
                    unjudged += 1
                    continue
                if row["limit_judged"] is not True:
                    # 缺值列的 `limit_up` 恆 False,與「真的打開了」同形 → 整列跳過,
                    # 對帳狀態不動(不然缺欄輪會產假 open,下一輪再補一則假 lock)
                    continue
                code = row["stock_id"]
                name = row["name"]
                # 先算出這列要用的值再動狀態:壞值在這裡就拋,`last_emitted` 不會被
                # 推進到一個「已宣告」卻沒有事件出去的位置(那筆帳會永遠對不回來)
                price = round(row["close"] * 1000)
                for direction, desired in (
                    ("up", bool(row["limit_up"])),
                    ("down", bool(row["limit_down"])),
                ):
                    key = (code, direction)
                    if desired == self._mkt_last_emitted.get(key, False):
                        continue
                    kind = _MARKET_LOCK if desired else _MARKET_OPEN
                    bucket = (code, kind, direction)
                    deadline = self._mkt_cooldown.get(bucket)
                    if deadline is not None and now < deadline:
                        continue  # 本輪不發;desired 持續不符則冷卻結束後補發
                    self._mkt_cooldown[bucket] = now + cooldown
                    self._mkt_last_emitted[key] = desired
                    touch = self._mkt_touch.get(bucket, 0) + 1
                    self._mkt_touch[bucket] = touch
                    events.append(
                        {
                            "kind": kind,
                            "code": code,
                            "name": name,
                            "price": price,
                            "time": as_of,
                            "direction": direction,
                            "touch_count": touch,
                        }
                    )
            except Exception:
                # 逐列容錯:一列髒值只丟那一列,同輪其他檔照發(design R5)
                logger.warning("breadth 廣度事件單列處理失敗(丟棄該列):%r", row, exc_info=True)
        if unjudged:
            logger.warning(
                "breadth 廣度事件:%d/%d 列無 limit_judged 鍵(疑似餵入原始快照 rows"
                " 而非 compute_breadth 輸出),該批不發事件",
                unjudged,
                len(rows_out),
            )
        if events:
            hub.publish_market_events(events, trade_date=trade_date)

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

    # ---- 產業鏈刷新(design §4.3)----

    def _chain_path(self) -> Path:
        return self._data_dir / _CHAIN_FILE

    def _restore_chain(self) -> None:
        """讀本地 chain 快取進表 —— **過期也先用**(TTL 只決定要不要重取,不決定能不能用)。

        parse 後為空(舊格式 / 殘表)則當沒有快取:時戳留 None → 下一圈立刻武裝。
        """
        loaded = load_chain(self._chain_path())
        if loaded is None:
            return
        rows, fetched_at = loaded
        chain_map = rows_to_chain_map(rows)
        if not chain_map:
            logger.warning("breadth industry_chain 快取解析後為空(%d 列),視同無快取", len(rows))
            return
        self._chain_map = chain_map
        self._chain_fetched_at = fetched_at
        logger.info(
            "breadth industry_chain restore:%d 列 / %d 產業(取數於 epoch %.0f)",
            len(rows),
            len(chain_map),
            fetched_at,
        )

    def _maybe_arm_chain(self) -> None:
        """該不該起 chain 刷新 task。四個條件缺一不可(順序即語意):

        1. `chain_fetch` 有值 —— None = 類股停用。
        2. task 不在跑 —— 上游卡住時不重複武裝(`is None` 分支不可省:第一次武裝前
           task 從未存在)。
        3. TTL 過期(`chain_ttl_hours`;`_chain_fetched_at is None` = 從未成功 → 視同
           過期)。TTL 走 **epoch**,重啟後照樣算得準。
        4. 退避冷卻已過 —— 壞上游不跟著 poll 節奏(10s)重打。
        """
        if self._chain_fetch is None:
            return
        task = self._chain_task
        if task is not None and not task.done():
            return
        fetched_at = self._chain_fetched_at
        ttl = self._config.chain_ttl_hours * 3600.0
        if fetched_at is not None and _time.time() - fetched_at < ttl:
            return
        retry_at = self._chain_retry_at
        if retry_at is not None and _monotonic() < retry_at:
            return
        self._chain_task = asyncio.create_task(self._refresh_chain())

    async def _refresh_chain(self) -> None:
        """一次刷新:取數 → parse → 落檔 → 換表。**失敗一律沿用舊表**。

        整個 method 是 fire-and-forget task 的身體,所以每條失敗路徑都自己收尾(退避
        時刻),不外拋 —— 逃出去的例外只會變成 asyncio 的「Task exception was never
        retrieved」,而類股面板停在舊表上零錯誤訊號。
        """
        fetch = self._chain_fetch
        if fetch is None:  # pragma: no cover - 武裝條件已擋掉
            return
        try:
            rows = await asyncio.to_thread(fetch, self._token)
        except BreadthFetchError as e:
            wait = self._map_backoff(e.quota)
            logger.warning(
                "breadth industry_chain 取數失敗(沿用舊表,%.0fs 後重試):%s", wait, e
            )
            self._chain_retry_at = _monotonic() + wait
            return
        except Exception:
            logger.exception(
                "breadth industry_chain 取數非預期失敗(沿用舊表,%.0fs 後重試)", _MAP_RETRY_SECS
            )
            self._chain_retry_at = _monotonic() + _MAP_RETRY_SECS
            return
        chain_map = rows_to_chain_map(rows)
        if not chain_map:
            # 換表 = 連磁碟那份一起覆寫;空表照換的話重啟後連 stale 的類股都沒有
            logger.warning(
                "breadth industry_chain 解析後為空(%d 列;沿用舊表不落檔,%.0fs 後重試)",
                len(rows),
                _MAP_RETRY_SECS,
            )
            self._chain_retry_at = _monotonic() + _MAP_RETRY_SECS
            return
        fetched_at = _time.time()
        save_chain(self._chain_path(), rows, fetched_at)
        self._chain_map = chain_map
        self._chain_fetched_at = fetched_at
        self._chain_retry_at = None
        logger.info("breadth industry_chain 刷新:%d 列 / %d 產業", len(rows), len(chain_map))

    # ---- 連板數重算(design §3.3)----

    def _maybe_arm_streaks(self) -> None:
        """今日該不該起重算 task。四個條件缺一不可(順序即語意):

        1. `daily_fetch` 有值 —— None = 連板停用。
        2. `now >= 06:00` —— T-1 的 EOD 發布餘裕(R15)。
        3. `_streak_armed_day != today` —— **武裝日不是成功日**:失敗用完 10 次後
           同日不再重跑(壞上游不整天燒配額),restore 命中也算已武裝(同日重啟不重打)。
        4. task 不在跑 —— `is None` 分支不可省:restore 命中後換日時 task 從未存在。
        """
        if self._daily_fetch is None:
            return
        if self._now_fn().time() < _STREAK_ARM_TIME:
            return
        today = self._today_fn().isoformat()
        if self._streak_armed_day == today:
            return
        task = self._streak_task
        if task is not None and not task.done():
            return
        # 先清再算:昨日那份留到重算完成之前會被當成今日的答案 → 整段窗口多算一板
        self._streaks = {}
        self._streaks_day = None
        self._streaks_end = None
        self._streaks_dates = []
        self._streaks_span = 0
        self._streaks_skipped = set()
        self._streak_attempts = 0
        self._streak_memo = {}
        self._streak_armed_day = today
        self._streak_task = asyncio.create_task(self._compute_streaks_loop())
        logger.info("breadth streak 武裝 %s(回看 %d 交易日)", today, STREAK_WINDOW_DAYS)

    async def _compute_streaks_loop(self) -> None:
        """重試 / 退避 / 上限。成功即結束;用完 `_STREAK_MAX_ATTEMPTS` 當日放棄。

        `except Exception` 是**任務存活邊界**(`_poll_loop` 同款):注入的取數層不保證
        只丟 `BreadthFetchError`,漏接會讓這條 task 在第一個意外上當場死透,而表現只是
        連板欄整天 null —— 沒有人會知道它死了。
        """
        while self._streak_attempts < _STREAK_MAX_ATTEMPTS:
            self._streak_attempts += 1
            wait = _STREAK_RETRY_SECS
            try:
                if await self._compute_streaks_once():
                    logger.info(
                        "breadth streak %s 完成:%d 檔 / %d 交易日(資料至 %s)",
                        self._streaks_day,
                        len(self._streaks),
                        self._streaks_span,
                        self._streaks_end,
                    )
                    return
            except BreadthFetchError as e:
                wait = self._config.quota_backoff_secs if e.quota else _STREAK_RETRY_SECS
                logger.warning(
                    "breadth streak 取數失敗(第 %d/%d 次,quota=%s,%.0fs 後重試):%s",
                    self._streak_attempts,
                    _STREAK_MAX_ATTEMPTS,
                    e.quota,
                    wait,
                    e,
                )
            except Exception:
                logger.exception(
                    "breadth streak 重算非預期失敗(第 %d/%d 次,%.0fs 後重試)",
                    self._streak_attempts,
                    _STREAK_MAX_ATTEMPTS,
                    wait,
                )
            if self._streak_attempts < _STREAK_MAX_ATTEMPTS:
                await asyncio.sleep(wait)
        logger.error(
            "breadth streak 連續 %d 次未成,當日放棄(連板欄 null,明日再武裝)",
            _STREAK_MAX_ATTEMPTS,
        )

    async def _compute_streaks_once(self) -> bool:
        """單次嘗試:自 `today − 1` 往回掃 → 逐日收成漲停集合 → 交集遞進 → 落檔。

        `today` **進場取樣一次**:掃描起點 / 檔名 / `computed_for` / 收尾檢查全用同一個
        值,否則跨午夜完成的那一輪會以昨日為基準算出錯值並被快取固化(R3)。

        記憶體紀律(R5):每日 rows 一拿到就收成集合後丟棄 —— 全市場單日 ~3 萬列,
        10 日全持有是數百 MB 級,live server 內不可接受。`_streak_memo` 只留收成後的
        集合(每日數十個代號),重試因此不必重抓已成功的日(R3-BE-2)。
        """
        fetch = self._daily_fetch
        if fetch is None:  # pragma: no cover - 武裝條件已擋掉
            return False
        day = self._today_fn()
        memo = self._streak_memo
        day_sets: list[set[str]] = []
        dates: list[str] = []
        skipped: list[str] = []
        d = day - _dt.timedelta(days=1)
        floor = day - _dt.timedelta(days=_STREAK_SCAN_CAL_DAYS)
        while d >= floor and len(day_sets) < STREAK_WINDOW_DAYS:
            key = d.isoformat()
            if key in memo:
                cached = memo[key]
                if cached is None:
                    skipped.append(key)
                else:
                    day_sets.append(set(cached))
                    dates.append(key)
                d -= _dt.timedelta(days=1)
                continue
            rows = await asyncio.to_thread(fetch, self._token, d)
            await asyncio.sleep(_STREAK_REQ_GAP_SECS)
            if not rows:
                skipped.append(key)  # 假日候選(FinMind 對非交易日回空陣列)
                memo[key] = None
            elif len(rows) < _DAILY_MIN_ROWS:
                # 部分截斷若被當假日跳過,那一天就從回看窗裡消失 → 連板數靜默高估
                logger.warning(
                    "breadth streak %s 只有 %d 列(門檻 %d),視同該日取數失敗 → 整輪重試",
                    key,
                    len(rows),
                    _DAILY_MIN_ROWS,
                )
                return False
            elif rows[0].get("date") != key:
                # 資料日回聲不符 = 參數被忽略 / 回到別日的快取。回應形狀完全合法且列數
                # 也夠 —— 沒有這道檢查,別日的漲停集合會被當成該日的答案填進窗裡,而
                # 錯值會被當日快取固化,整天不再重算(review R3-T3)
                logger.warning(
                    "breadth streak %s 回應資料日為 %r(不符請求日),視同該日取數失敗 → 整輪重試",
                    key,
                    rows[0].get("date"),
                )
                return False
            else:
                day_set = compute_day_limitups(rows)
                if not day_set:
                    # 全市場單日零漲停極罕見(多半是 close/spread 欄位語意變了);不中斷,
                    # 但連板欄整片空白與「今天真的沒人漲停」同形,要留下觀測訊號
                    logger.warning(
                        "breadth streak %s 零漲停(%d 列)—— 欄位語意可能已變,請核對",
                        key,
                        len(rows),
                    )
                logger.info("breadth streak %s:%d 列 / %d 檔漲停", key, len(rows), len(day_set))
                memo[key] = day_set
                day_sets.append(set(day_set))
                dates.append(key)
            d -= _dt.timedelta(days=1)

        if not dates:
            logger.warning(
                "breadth streak 自 %s 往回掃 %d 日曆日仍無任何交易日資料 → 整輪重試",
                day.isoformat(),
                _STREAK_SCAN_CAL_DAYS,
            )
            return False
        lead_gap = (day - _dt.date.fromisoformat(dates[0])).days
        if lead_gap > _STREAK_GAP_CAL_DAYS:
            # **前緣**同閾值(review R3-BE-1):上游把最近 N 個交易日整段丟掉時,收到的
            # 序列自己是連續的(內部間距全 1),交集遞進照樣成功、成果照樣被當日快取固化,
            # 而盤中判式仍走 `rows_date > data_end` 分支 +1 → 連板數靜默少計整段
            logger.warning(
                "breadth streak 最新資料日 %s 距 %s 已 %d 日(上限 %d),該輪不採用",
                dates[0],
                day.isoformat(),
                lead_gap,
                _STREAK_GAP_CAL_DAYS,
            )
            return False
        for newer, older in zip(dates, dates[1:]):
            gap = (_dt.date.fromisoformat(newer) - _dt.date.fromisoformat(older)).days
            if gap > _STREAK_GAP_CAL_DAYS:
                # 中間有整段真交易日被當成假日吃掉 → 交集遞進會跨過斷層算出高估的 streak
                logger.warning(
                    "breadth streak 交易日 %s → %s 間距 %d 日(上限 %d),該輪不採用",
                    older,
                    newer,
                    gap,
                    _STREAK_GAP_CAL_DAYS,
                )
                return False

        streaks = compute_prev_streaks(day_sets)
        if self._today_fn() != day:
            logger.warning(
                "breadth streak 重算期間換日(%s → %s),丟棄本輪結果",
                day.isoformat(),
                self._today_fn().isoformat(),
            )
            return False

        self._streaks = streaks
        self._streaks_day = day.isoformat()
        self._streaks_end = dates[0]
        self._streaks_dates = dates
        self._streaks_span = len(dates)
        self._streaks_skipped = set(skipped)
        # 武裝日對齊**成果日**:跨午夜完成時 `day` 已是 D+1,armed_day 若還停在 D,
        # 下一圈武裝檢查會判「今日尚未武裝」把剛算好的成果整組清掉再全掃一次
        # (白燒一輪 MB 級請求,期間連板欄全 null;review R3-BE-3)
        self._streak_armed_day = day.isoformat()
        yesterday = (day - _dt.timedelta(days=1)).isoformat()
        if dates[0] != yesterday:
            # 昨日若其實是交易日(FinMind 丟資料)→ 盤中判式仍會 +1 而少計一板(KR-1)
            logger.warning(
                "breadth streak 最新資料日 %s 不是昨日 %s(昨日若為交易日則連板數少計)",
                dates[0],
                yesterday,
            )
        self._save_streaks()
        return True

    def _streaks_path(self, day: str) -> Path:
        return self._data_dir / f"streaks-{day}.json"

    def _save_streaks(self) -> None:
        """tmp + `os.replace` 原子寫;失敗只降級(記憶體成果照在,重啟才會重算)。"""
        day = self._streaks_day
        if day is None:  # pragma: no cover - 呼叫端已保證有值
            return
        path = self._streaks_path(day)
        payload = {
            "_version": _STREAK_FILE_VERSION,
            "computed_for": day,
            "data_end": self._streaks_end,
            "dates": self._streaks_dates,
            "skipped": sorted(self._streaks_skipped),
            "streaks": self._streaks,
        }
        tmp = path.with_name(f"{path.name}.tmp")
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
        except OSError as e:
            logger.warning("breadth streak 落檔失敗(續行):%r", e)

    def _restore_streaks(self) -> None:
        """讀 `streaks-<today>.json`;**命中即連 `_streak_armed_day` 一併設為 today**。

        那個副作用就是「同日第二次啟動不打 FinMind」的實際機制(SC-2)。形狀 / 版本 /
        `computed_for` 任一不符一律當沒有(今日重算)—— 半採用一份舊快取會讓連板數
        整天錯著,而錯的連板數比沒有更糟。
        """
        today = self._today_fn().isoformat()
        path = self._streaks_path(today)
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError) as e:
            logger.warning("breadth streak 快取讀取失敗,今日重算:%r", e)
            return
        if not isinstance(payload, dict) or payload.get("_version") != _STREAK_FILE_VERSION:
            logger.warning("breadth streak 快取版本不符,今日重算:%s", path)
            return
        if payload.get("computed_for") != today:
            logger.warning(
                "breadth streak 快取 computed_for=%s ≠ 今日 %s,不採用",
                payload.get("computed_for"),
                today,
            )
            return
        data_end = payload.get("data_end")
        dates = payload.get("dates")
        skipped = payload.get("skipped")
        streaks = payload.get("streaks")
        if (
            not isinstance(data_end, str)
            or not isinstance(dates, list)
            or not isinstance(skipped, list)
            or not isinstance(streaks, dict)
        ):
            logger.warning("breadth streak 快取形狀不符,今日重算:%s", path)
            return
        # `dates` 是 `_streaks_span`(封頂判定的分母)與 `data_end`(盤中 +1 判定的基準)
        # 的唯一來源,三條自洽檢查缺一不可(review R3-BE-4):空 list 讓 span=0 →
        # `prev >= span` 恆真 → **每一列**漲停都被標成假的「N+ 板」;dates[0] ≠ data_end
        # 則兩個判定各自以不同的日為基準;逐項過濾掉髒值後照樣採用等於半份快取生效
        dates_out = [d for d in dates if isinstance(d, str)]
        if not dates_out or len(dates_out) != len(dates) or dates_out[0] != data_end:
            logger.warning(
                "breadth streak 快取 dates 與 data_end 不自洽(%d 筆 / data_end=%s),今日重算:%s",
                len(dates),
                data_end,
                path,
            )
            return
        self._streaks = {
            k: v
            for k, v in streaks.items()
            if isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool)
        }
        self._streaks_dates = dates_out
        self._streaks_day = today
        self._streaks_end = data_end
        self._streaks_span = len(self._streaks_dates)
        self._streaks_skipped = {s for s in skipped if isinstance(s, str)}
        self._streak_armed_day = today
        logger.info(
            "breadth streak restore %s:%d 檔 / %d 交易日(資料至 %s)",
            today,
            len(self._streaks),
            self._streaks_span,
            data_end,
        )

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
