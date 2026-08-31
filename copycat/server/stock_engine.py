"""StockEngine:個股訂閱池 + 當日狀態機編排 + WS 廣播(design v4 §2.4)。

- refcount 訂閱池:owner ∈ {"watchlist", "main", "stkfut:<code>"};0→1 真訂、
  last-out 真退、真訂失敗回滾 bookkeeping 並 raise(treading-king WSPool 模型)。
- backfill 單工 worker queue(engine 持有;source 只提供同步 backfill,r2-1 定案),
  job 帶 (code, day_generation),套用 guard = **generation 一致**(收件人 = job 自帶的
  code,不綁 `_main` —— 群組成員也要能補;design v3 R12)。
- 兩段式 rollover:階段一(換日窗 + 重掛,不清狀態)→ 階段二(首筆新日 tick 才
  reset + 重回補;假日無新日推播天然不清空)。
- 廣播:per-client 有界 queue,滿丟最舊;側欄 watchlist_quote 1s 節流合併。
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
from collections.abc import Set as AbstractSet
from typing import AsyncGenerator, Callable, Protocol

from copycat.live.stock_models import (
    TRIAL_WINDOWS,
    StockTick,
    is_trial_window,
    parse_stock_realtime,
    to_milli,
)
from copycat.live.stock_source import (
    Bar,
    BarsStatus,
    DailyBar,
    is_futures_key,
    trial_windows_for,
)
from copycat.live.stock_state import StockDayState
from copycat.live.tc4 import HistoryTimeoutError
from copycat.server.bars import BarsResult
from copycat.server.ws import WsBroadcaster
from copycat.stkfut_map import load_map

logger = logging.getLogger(__name__)

#: `set_watchlist(seq=...)` 的 **boot 還原哨兵**(N112):恆小於 `WatchlistService` 的
#: 取號(自 1 起),所以「使用者的 PUT 先到、boot 還原後到」時贏的是新的那一份。
#: 舊碼的 `seq=None` 是無條件全套,它的安全前提(「service 在 restore 之後才建構 +
#: routes 前置 503」)只寫在註解裡、沒有任何斷言;哨兵讓它變成結構性的。
WATCHLIST_BOOT_SEQ = 0
#: **非生產**的直呼(測試 / 一次性腳本)= 不參與定序。生產路徑只有兩個 caller:
#: app boot(帶 `WATCHLIST_BOOT_SEQ`)與 `WatchlistService`(帶自己的取號),而
#: `watchlist_service.StockPool` 那一側的簽名**沒有預設值** —— 未來的生產 caller
#: 漏帶 keyword 在 pyright 期就紅,不會靜默拿到豁免。
WATCHLIST_UNORDERED = -1

_CLIENT_QUEUE_MAX = 1000
# 同一檔當日回補失敗幾次之後就不再入列(code review A2)。群組 batch 每 60s 一輪,
# 沒有這道冷卻的話一檔壞碼會對 TC4 發整天的必敗請求,還把單工 worker 排到滿。
_BACKFILL_MAX_FAILS = 3
# 回補**逾時**(`HistoryTimeoutError`)的處置與斷線不同:TC4 好得很,只是這一檔的
# history 首頁還沒備妥 → 隔一段時間重排即可。退避固定 15s(= server 層負向快取的同
# 一個節奏),per-code 上限 2 次:沒有上限的話一檔冷門股會對 TC4 發整天的必敗請求。
_BACKFILL_TIMEOUT_RETRY_SECS = 15.0
_BACKFILL_TIMEOUT_MAX_RETRIES = 2
# 未知 / 未訂閱 code 的空 payload。由狀態機自己產一次(而不是手抄一份字面值):
# 鍵名只有 `light_snapshot()` 一份定義,抄第二份就是下一個會漂的地方。
# 建構一次是為了避開每格空卡都 new 一個 `deque(maxlen=20_000)` 的狀態機;
# 取用端一律 `dict(...)` 淺拷後才放進回應(payload 到消費端只被序列化,不被就地改)。
_EMPTY_LIGHT: dict = StockDayState().light_snapshot()

#: 個股期日盤窗(台北 HH:MM,含端點;台指期同表 08:45–13:45)。夜盤 tick 一律不進當日
#: 狀態(D14b):REALTIME 訂閱窗(UTC 00–06)只是「不主動要夜盤」,TC4 在窗邊界仍可能
#: 推進來,而夜盤成交混進日盤分時圖的失效樣態是 x 軸左右各長出一段沒有位置的資料
#: (前端的窗是 08:45–13:45),圖畫得出來、根數也合理,沒有任何 assertion 會紅。
_FUT_SESSION_START = "08:45"
_FUT_SESSION_END = "13:45"


def _in_futures_session(time_taipei: str) -> bool:
    """台北 HH:MM:SS.fff 是否落在個股期日盤窗(兩端含)。"""
    return _FUT_SESSION_START <= time_taipei[:5] <= _FUT_SESSION_END


def _now_taipei_hhmm() -> str:
    """本機時鐘的台北 `HH:MM`(部署綁本機 = 台北,同 `stkfut_catalog._today` 慣例)。

    純簿更新(`TradeQuantity=0`)解不出 tick,窗判準只剩本機時鐘 —— 而個股期夜盤
    大部分時間**只有簿在動**,不判就等於整夜的五檔覆蓋日盤收盤簿。
    """
    return f"{_dt.datetime.now():%H:%M}"


def _now_taipei_time() -> str:
    """本機時鐘的台北 `HH:MM:SS.fff`(部署綁本機 = 台北,同 `_now_taipei_hhmm`)。

    尺寸對齊 `is_trial_window` 的入參(它做字串比對,`HH:MM` 那把尺會在
    `"08:30" < "08:30:00.000"` 這種比較上靜默錯邊)。模組級而非 method:測試一律
    monkeypatch 模組屬性注入假時鐘(同 `_now_taipei_hhmm` 的既成用法)。
    """
    return f"{_dt.datetime.now():%H:%M:%S.%f}"[:-3]


def _spot_trial_window_now() -> bool:
    """現貨那把尺的「當下在試撮**時間窗**內」——**純窗**,不看交易日曆。

    per-instrument 判定走 `StockEngine._trial_now`(期貨空窗恆 False);這裡要的是
    「現貨窗有沒有跨過邊界」這**單一**事件,拿某一檔的 key 去算會在自選全空 /
    只剩期貨主圖時失去判準。窗顯式傳 `TRIAL_WINDOWS` 不吃預設值(同
    `parse_stock_realtime` 的 keyword-only 理由:傳錯的失效是靜默的)。

    對外的旗標請走 `StockEngine._spot_trial_now()`(= 本函式 AND 交易日曆,D4');
    這一支只留給「要的就是窗本身」的地方(觀測分級、格式契約測試)。

    **窗與日的時鐘是兩顆,窗這顆不吃 `now_fn` 注入**(review C-5):日別走
    `StockEngine._now_fn`(可注入),窗走這裡的模組級 `_now_taipei_time()`(只能
    monkeypatch 模組屬性)。兩顆在 prod 都是本機牆鐘、同一台機器,但**測試裡可以被設成
    互相矛盾**(now_fn 給週二、窗時鐘給 08:50 卻是另一天的 08:50)—— 寫測試時兩顆都要
    設,只設一顆的那半會靜默沿用真牆鐘。合併成一顆的代價是窗判定得繞過 `%H:%M:%S.%f`
    的字串尺(`is_trial_window` 做字串比對),而那把尺的邊界語意已由 `TestObserveClock
    Contract` 釘死,不值得為對稱去動它。
    """
    return is_trial_window(_now_taipei_time(), TRIAL_WINDOWS)


#: TradeStatus 轉態觀測的**固定 grep 前綴 + 格式**(D6/R10)。與 parse 層值域外 warning
#: 是同事件兩則(那邊管值域、這邊管轉態時序),蒐證對帳一律以本前綴為準。
_TRADE_STATUS_FMT = "trade-status-observe code=%s %s->%s t=%s trial_window=%s qty=%s"
#: 首見值(前值不明)的形:**不套 `%s->%s`** —— 把未知前值印成 "0" 就是在蒐證檔裡
#: 編造一次轉態,而讀 log 的人分不出來(code review IC-1)。前綴與其餘欄位相同。
_TRADE_STATUS_FIRST_FMT = (
    "trade-status-observe code=%s first_seen=1 status=%s t=%s trial_window=%s qty=%s"
)

#: 觀測分級用的窗寬限(秒)。**只作用於 `_observe_trade_status` 的 WARNING/DEBUG 分級**,
#: payload 的 `trial` 一律走原窗(寬限外洩到 wire 會讓畫面的「(緩)」早亮晚熄)。
_OBSERVE_GRACE_SECS = 2


def _widen(t: str, secs: int) -> str:
    """台北 `HH:MM:SS.fff` ± 秒(模組載入期用;窗都在日中,不處理跨日繞回)。"""
    shifted = _dt.datetime.strptime(t, "%H:%M:%S.%f") + _dt.timedelta(seconds=secs)
    return f"{shifted:%H:%M:%S.%f}"[:-3]


#: 觀測專用窗 = `TRIAL_WINDOWS` 兩端各放寬 `_OBSERVE_GRACE_SECS`(code review D6-1)。
#: 由 `TRIAL_WINDOWS` **推導**而不是抄一份字面值:抄的那份會在窗調整時靜默地錯邊。
_OBSERVE_WINDOWS: tuple[tuple[str, str], ...] = tuple(
    (_widen(lo, -_OBSERVE_GRACE_SECS), _widen(hi, _OBSERVE_GRACE_SECS)) for lo, hi in TRIAL_WINDOWS
)


def _observe_window_now() -> bool:
    """觀測分級的「當下在(放寬後的)試撮窗內」——**純窗**,不看交易日曆(D4')。

    因此它與 payload 的 `trial` 在休市日會不同值(這裡 True、那邊 False):蒐證要看
    的是窗本身有沒有事件,把日曆 AND 進來等於在休市日把整段紀錄降級成「窗外」。

    寬限的理由:窗判準是**本機時鐘**而事件來自 **TC4 時戳**,兩者的秒級偏移會把
    13:25:00 進窗的 0→1 判成「窗外非 0」→ 每檔每日最多產出一對假 WARNING
    (進窗一則、出窗一則)。真要抓的盤中延緩撮合離窗邊界遠,放寬 2s 不吃掉它。
    只有現貨會走到這裡(期貨鍵在 `_observe_trade_status` 開頭就跳過)。
    """
    return is_trial_window(_now_taipei_time(), _OBSERVE_WINDOWS)


def _round_robin(items: list[str], round_no: int) -> list[str]:
    """段內迭代起點逐輪輪轉(C-1)。

    段級 break 只解跨段餓死;固定順序 + 首個失敗就 break,排最前的恆失敗檔會永久
    餓死同段後面所有檔(head-of-line blocking)—— 而那些檔的失效同樣是靜默的。
    輪轉不影響持鎖上界:每段仍至多一次失敗 subscribe。
    """
    if not items:
        return items
    k = round_no % len(items)
    return items[k:] + items[:k]


class _EngineClosing(Exception):
    """關機中的早退訊號(訂閱重試迴圈內部用)。

    刻意**不是** `ConnectionError`:那會被重試段的 except 接住,打出與「TC4 訂閱失敗」
    一模一樣的 warning,污染 `grep 'subscribe .* failed'` 這條運維判準。
    """


class StockSource(Protocol):
    """個股行情來源抽象;TC4 實作在 copycat.live.stock_source,測試注入 fake。

    `code` 一律是 **instrument key**:股號 / `F:<prod>`(期現對照腿)/ `F:<prod>:<ym>`
    (選定的月契約主圖)。key → TC4 symbol 的對映**只有 source 知道**(`symbol_of`)。
    """

    def subscribe_symbol(self, code: str) -> None: ...

    def unsubscribe_symbol(self, code: str) -> None: ...

    def symbol_of(self, key: str) -> str: ...

    def backfill(self, code: str) -> list[StockTick]: ...

    def prepare_backfill(self, codes: list[str]) -> None:
        """整批預熱:對每檔先送 SubHistory 讓 TC4 平行備資料,之後逐檔 `backfill` 收割
        (perf/opening-backfill-parallel S1-b)。best-effort:傳輸失敗(`ConnectionError`)
        只 log 就停、壞電文(`ValueError`)只 log 並跳過那一檔;都不 raise。其餘例外由 worker 的
        `except Exception` 兜住(pr-153 F-05 / round-1 F-C)。"""
        ...

    def fetch_daily_bars(self, code: str, n: int = 25) -> list[DailyBar]: ...

    def fetch_bars_range(
        self, code: str, tf: str, start_date: str, end_date: str
    ) -> tuple[list[Bar], BarsStatus]: ...

    def set_on_message(self, cb: Callable[[dict], None]) -> None: ...

    def set_on_no_data(self, cb: Callable[[str], None]) -> None: ...

    def set_trade_date(self, trade_date: str) -> None: ...

    def close(self) -> None: ...


class SignalSink(Protocol):
    """訊號層掛點(實作 = `copycat.server.signal_hub.SignalHub`;測試注入 fake)。

    **全部同步方法**:engine 熱路徑不 await。例外由 hub 自己吞(`on_tick`/`on_book`
    內已全包 try/except + log),engine 側不再包一層 —— 包兩層會讓「訊號層出錯」
    在兩個地方各記一次,且掩蓋 hub 內的具體處理。
    """

    def on_tick(self, code: str, tick: StockTick, state: StockDayState) -> None: ...

    def on_book(self, code: str, state: StockDayState) -> None: ...

    def on_rollover_pending(self, new_date: str) -> None: ...

    def on_rollover(self) -> None: ...

    def on_watchlist(self, codes: list[str]) -> None: ...


class StockEngine:
    def __init__(
        self,
        source: StockSource,
        *,
        trade_date: str,
        throttle_secs: float = 1.0,
        checkpoint: bool = True,
        stkfut_map: dict[str, dict] | None = None,
        resub_interval_secs: float = 10.0,
        ws: WsBroadcaster | None = None,
        is_trading_day: Callable[[_dt.date], bool] | None = None,
        now_fn: Callable[[], _dt.datetime] | None = None,
        # 處置股名單(L75):breadth 引擎的 FinMind 處置名單 late-bound 注入;
        # None(breadth 停用 / 無 token)= 恆空 → trial 全部照標(緩)= 降級即修前行為。
        disposition_codes: Callable[[], AbstractSet[str]] | None = None,
    ) -> None:
        self._source = source
        self._trade_date = trade_date
        self._pending_date: str | None = None
        self._throttle = throttle_secs
        self._checkpoint_enabled = checkpoint
        # 交易日曆注入(mod/trading-calendar SC-4)。**預設 = 現行 `weekday() < 5` 逐字**
        # (W9):engine 直接建構的既有 caller 行為不得有一絲變化,真日曆只由 app 層在
        # prod 顯式傳(測試預設關,同 DEFAULT_STOCK / DEFAULT_BREADTH 慣例)。
        self._is_trading_day = (
            is_trading_day if is_trading_day is not None else (lambda d: d.weekday() < 5)
        )
        # checkpoint 的時鐘同樣可注入:換日窗判定唯一的時間讀取點,不注入就只能靠真
        # 牆鐘決定測試綠不綠(index `now_fn` 的同款理由)。
        self._now_fn = now_fn if now_fn is not None else _dt.datetime.now
        self._disposition_codes = disposition_codes
        #: checkpoint 迴圈間隔(秒)。測試把它調小以換得「迴圈真的轉過 N 拍」的觀察點。
        self._checkpoint_secs = 60.0
        self._map = stkfut_map if stkfut_map is not None else load_map()
        self._prod_to_code = {v["prod"]: k for k, v in self._map.items()}
        self._refs: dict[str, set[str]] = {}
        self._states: dict[str, StockDayState] = {}
        # 推播路由表 symbol → instrument key(D1/R2-2)。`Security` **不是**路由鍵:
        # 個股期 leaf 的該欄值域未實證(產品碼 / 股號都可能),同一個值可同時出現在
        # 現貨與合約推播上,拿它當鍵時「合約推播蓋掉現貨狀態」完全靜默。
        # 只增不減(同 `_states`):退訂後殘留的鍵指向仍存在的 state,晚到的推播照舊
        # 落在原處;真正的失效是「訂閱失敗卻留著鍵」,那條在 `_acquire` 回滾。
        self._symbol_to_key: dict[str, str] = {}
        self._no_data: set[str] = set()
        self._watchlist: list[str] = []
        self._main: str | None = None
        self._generation = 1
        self._backfill_jobs: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
        self._backfilling: str | None = None
        # 回補記帳(design v3 R12/R3 + code review A2/A3)。worker 的 guard 去掉 `_main`
        # 綁定之後,「這一檔今天補過了沒」不再能從 `_main` 推導,得自己記:
        #   `_backfill_pending` = 在途**計數**(入列時 +1、worker 取件後不論套用/失敗/
        #     丟棄一律 −1 並在歸零時移除鍵)= 群組入列的 dedup 與 `backfilling` 旗標
        #     的唯一來源。**計數而不是集合**:同一檔可能同時有兩個入列點(漲跌停值變
        #     + 群組輪詢),集合版的第一個 job 結清就把旗標翻掉,卡片在第二個 job 還在
        #     跑的時候從「回補中…」跳成「無資料」;也因此它**不可被外部整批清空**
        #     (在途 job 之後仍會來扣一次 → 計數負值 / 旗標永久假)。
        #   `_backfilled` = **套用成功**才加 = 今日已回補判準
        #   `_backfill_failed` = 當日失敗次數;≥ `_BACKFILL_MAX_FAILS` 就不再入列(A2)
        # 後兩者是**日別**語意:rollover stage2 顯式清空;reconnect 只清 `_backfilled`
        # (R4 —— reconnect 不 bump generation 是實碼事實,漏清 = 斷線缺口整天補不回來
        # 而畫面毫無異狀)。
        self._backfill_pending: dict[str, int] = {}
        self._backfilled: set[str] = set()
        #: 首筆當日成交 tick 已點火過的檔(perf/opening-backfill-parallel S2;review F-2):
        #: tick 節拍是次秒級,點火只許**每個訂閱期一次**,否則逾時 settle 後的下一筆
        #: tick 立刻重排,15 s 退避與 2 次上限在毫秒內燒完 → 「放棄」→ 當日不再回補。
        #: 之後的重試仍走原本的 timer / 60 s 輪詢。與 `_backfilled` 同界:真退訂 discard、
        #: rollover stage2 與 reconnect clear(重連後首筆再補一次斷線缺口)。
        self._tick_armed: set[str] = set()
        self._backfill_failed: dict[str, int] = {}
        #   `_backfill_timeouts` = 當日**逾時**重排次數(與 `_backfill_failed` 分帳:
        #     逾時不是失敗,不該吃掉「三次就冷卻」那個給真失敗用的額度)。日別語意,
        #     與 `_backfill_failed` 同在 rollover 清空。
        self._backfill_timeouts: dict[str, int] = {}
        #   `_backfill_timeout_handles` = 上面那條重排的 `loop.call_later` handle,per code。
        #     排了就要有取消點:close 之後醒來的 callback 會對已關閉的 engine 起
        #     `_backfill_pending` 帳並塞一筆沒有 worker 會取的 job;rollover 之後醒來的
        #     則是用新一天的 generation 重排一筆 stage2 已經排過的 job。per code 是為了
        #     「同一檔重排前先取消上一支」—— 五個入列點任一個在 timer 在途時把同一檔
        #     再送進 worker,就會多出一支孤兒 timer(重試預算雙倍燒,而上界看起來還在)。
        self._backfill_timeout_handles: dict[str, asyncio.TimerHandle] = {}
        # 可注入(XR-3):app 層要把同一顆 broadcaster 同時給 engine 與 SignalHub,
        # 讓 `/ws/stock` 這條匯流排的存在性不再綁 engine 的生命週期。不傳 = 自建,
        # 既有 caller(直接建構的測試)行為逐字不變。
        self._ws = ws if ws is not None else WsBroadcaster(maxsize=_CLIENT_QUEUE_MAX)
        self._dirty_watchlist: set[str] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        # 長駐迴圈 + 每次 rollover 的重掛 task 都進這裡:唯一持有點 = 唯一取消點,
        # close() 的 cancel+await 鏈自然涵蓋(專用欄位存放會漏掉關機取消,且連跑
        # 兩次 rollover 時後者覆寫前者 → 前一個 task 失去參照被中途 GC)
        self._tasks: list[asyncio.Task[None]] = []
        # 訂閱池變更(set_watchlist/set_main/重掛)全程序列化:_refs/_main/_watchlist
        # 被 to_thread 與 loop 並發讀寫,check-then-act 交錯會退訂主圖/洩漏 owner(CR2)
        self._pool_lock = asyncio.Lock()
        # 已套用的自選定序號(X-3):service 在自己的鎖內取號,訂閱在鎖外送達 →
        # 抵達順序不保證。初值比 `WATCHLIST_BOOT_SEQ` 再小一號 = 「還沒套過任何名單」,
        # 於是 boot 的哨兵(恆為最舊)在乾淨的引擎上仍套得進去(N112)。
        self._wl_seq_applied = WATCHLIST_BOOT_SEQ - 1
        # 訂閱失敗的復原路徑(mod/subscribe-retry-recovery):三處失敗各自靜默 ——
        # watchlist 檔回滾出 `_refs` 後畫面永遠 `-`、stkfut 腿要切走再切回才會重掛、
        # rollover 重掛失敗更是連 `_refs` 都不動,對帳判準看不到
        self._resub_interval_secs = resub_interval_secs
        # `_resubscribe_all` 的失敗檔:owner 還在 `_refs` 裡,只是 SUB 沒掛上 →
        # 「owner 缺席」的對帳判準涵蓋不到,得另記(P1-1)
        self._failed_resubs: set[str] = set()
        self._retry_round_no = 0  # 段內輪轉起點(C-1);單調遞增,不回捲
        # 現貨試撮窗的**上一輪**值(D3):`_flush_watchlist_loop` 每輪比對,翻轉才補推。
        # 真值在 `start()` 內以現算播種 —— 這裡給 False 只是型別上的初值,窗內啟動時
        # 若不播種,第一輪 flush 會看到一次「假翻轉」並替全自選各發一則。
        self._trial_on: bool = False
        # TradeStatus 轉態觀測狀態(D6):code → (前值, episode 已記 WARNING)。
        # 前值是為了「只在轉態時記」;episode 旗標讓起訖成對(恢復那一則才記得住
        # 自己有沒有對應的起點)。**日別語意**:`rollover_stage1` 顯式清空(stage2 保留
        # 為快路徑雙保險,IC-5);**訂閱期語意**:真退訂時 pop(IC-6,同 `_backfilled`)。
        self._trade_status: dict[str, tuple[str, bool]] = {}
        # 未 attach 時全部掛點跳過:訊號層是可選功能(lifespan `_boot` 失敗即降級),
        # 引擎本體不得因它缺席而改變行為
        self._signal_hub: SignalSink | None = None
        self.tc4_status = "up"

    @property
    def trade_date(self) -> str:
        """當前交易日(SignalHub 的 `trade_date_fn`)。

        對外唯讀存取器而非讓 hub 讀 `_trade_date`:兩段式 rollover 期間這個值會在
        stage2 才前進,語意由 engine 單一持有。
        """
        return self._trade_date

    def attach_signal_hub(self, hub: SignalSink) -> None:
        self._signal_hub = hub

    def detach_signal_hub(self) -> None:
        """摘掉掛點(hub 收攤前呼叫):對已收攤的 hub 繼續打熱路徑 = 訊號靜默全失。"""
        self._signal_hub = None

    # ---- 生命週期 ----

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        # 試撮窗基準**現算播種**(D3 amendment R3):窗內啟動(08:30–09:00 / 13:25–13:30)
        # 時若沿用 `__init__` 的 False,第一輪 flush 會判成「剛進窗」並替全自選各補推
        # 一則 —— 那是假翻轉,而它與真翻轉在 log 與線上都無從分辨。
        self._trial_on = self._spot_trial_now()
        self._source.set_trade_date(self._trade_date)  # 休市日回補模式與 source 日窗同步
        self._source.set_on_message(self._on_raw_threadsafe)
        self._source.set_on_no_data(self._on_no_data_threadsafe)
        if hasattr(self._source, "on_reconnect"):
            self._source.on_reconnect = self._on_reconnect_threadsafe  # type: ignore[attr-defined]
        self._tasks.append(asyncio.create_task(self._backfill_worker()))
        self._tasks.append(asyncio.create_task(self._flush_watchlist_loop()))
        self._tasks.append(asyncio.create_task(self._retry_subscribe_loop()))
        if self._checkpoint_enabled:
            self._tasks.append(asyncio.create_task(self._checkpoint_loop()))

    async def close(self) -> None:
        # 先斷 threadsafe callback 入口(比照 index_engine):close 期間 TC4 推播不得再
        # `call_soon_threadsafe` 到即將關閉的 loop
        self._loop = None
        # 在途的逾時重排 timer 不歸 `_tasks` 管(它們是 `call_later` handle 不是 task)
        # → 這裡是唯一的取消點。留著的話 callback 會在已關閉的 engine 上起
        # `_backfill_pending` 帳並塞一筆永遠沒有 worker 會取的 job。
        self._cancel_backfill_timeout_retries()
        # 快照:cancel/await 期間 rollover 仍可能 append(`_tasks` 是唯一持有點),
        # 迭代中被改動會漏取消或炸 RuntimeError
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        # `gather(return_exceptions=True)`:逐個 `await task` 會被「已帶例外結束的 task」
        # 就地重拋 → 後面的 task 不被 await、`source.close()` 永不執行(ZMQ session 洩漏)。
        # 關機是最後一棒,沒有人會再呼叫第二次,所以這裡吞例外但**留紀錄**。
        for task, result in zip(tasks, await asyncio.gather(*tasks, return_exceptions=True)):
            if isinstance(result, BaseException) and not isinstance(result, asyncio.CancelledError):
                logger.exception("close: 背景 task %r 帶例外結束", task.get_name(), exc_info=result)
        await asyncio.to_thread(self._source.close)

    # ---- refcount 訂閱池 ----

    def _acquire(self, code: str, owner: str) -> None:
        owners = self._refs.setdefault(code, set())
        if owner in owners:
            return
        if not owners:
            # **先寫記帳再訂閱**(R2-2):TC4 在 SUB 回來後毫秒級推第一則 REALTIME
            # (§8 實證),而 `subscribe_symbol` 走 to_thread —— 期間 loop 是空的,
            # 那一則會直接進 `_handle_quote`。路由表或 state 任一後寫都會讓首則被丟,
            # 而冷門標的整天可能只有那一則(meta / 參考價),畫面只是空著。
            symbol = self._source.symbol_of(code)
            self._symbol_to_key[symbol] = code
            self._states.setdefault(code, StockDayState())
            try:
                self._source.subscribe_symbol(code)
            except ConnectionError:
                # 真訂失敗回滾 bookkeeping(design §2.4):不留空 owner set,也不留
                # 指向無 owner 的路由鍵(state 照留 —— 只增不減,`_release` 亦不清)
                if not owners:
                    self._refs.pop(code, None)
                    self._symbol_to_key.pop(symbol, None)
                raise
        owners.add(owner)
        self._states.setdefault(code, StockDayState())

    def _release(self, code: str, owner: str) -> None:
        owners = self._refs.get(code)
        if owners is None or owner not in owners:
            return
        owners.discard(owner)
        if not owners:
            self._refs.pop(code, None)
            try:
                self._source.unsubscribe_symbol(code)
            except ConnectionError:
                logger.warning("unsubscribe %s failed (ignored)", code)

    # ---- 對外操作 ----

    async def set_watchlist(self, codes: list[str], *, seq: int = WATCHLIST_UNORDERED) -> None:
        """`seq` = 呼叫端(`WatchlistService`)在**它自己的鎖內**取的定序號(X-3)。

        `seq <= 已套用` = 舊名單後到 → **整段跳過**(不訂不退不廣播不通知 hub),
        照套的話訂閱池 / hub membership / 種子廣播會一起退回上一版,而畫面上只是
        「剛加的股票又不見了」,零錯誤訊號。

        **`WATCHLIST_BOOT_SEQ`(= 0)是 boot 還原專用的哨兵**(N112,取代舊的
        `seq=None` 豁免):它恆小於 service 的取號(自 1 起),所以「PUT 先到、boot
        還原後到」時贏的是使用者剛存的那一份。舊碼的 `None` 分支是**無條件全套**,
        它的安全前提(「service 在 restore 之後才建構 + routes 前置 503」)沒有在任何
        地方被斷言 —— 現在這條不變式是結構性的,不再靠讀 boot 序列來確認。
        `WATCHLIST_UNORDERED` 是**非生產**的直呼(測試 / 一次性腳本)= 不參與定序;
        `WatchlistService` 的 Protocol 那一側沒有預設值,漏帶 keyword 在 pyright 期就紅。

        **逐項取鎖,不是整段一鎖**(N111,照同檔 `_retry_round`):TC4 故障時單檔
        SUBQUOTE 要等 `_REQ_TIMEOUT_MS`(10 s)才失敗,整段持鎖會讓第二個寫入者
        (PUT / Discord `/watch` 的 `_settle`、切主圖)等**整段**迴圈走完 —— 50 檔
        就是 500 s —— Discord `/watch` 已 defer(token 15 分鐘,見 `watchlist_service.py` /
        `discord_bot.py`)未必逾時,但前端 PUT / 切主圖的使用者就是等整段。逐項取鎖之後,
        等待上界降到「當下這一檔」(≈ `_api_lock` 等待 + `_REQ_TIMEOUT_MS` ≈ 20 s)。ZMQ IO
        仍在鎖內(per-code in-flight 狀態才能把 IO 完全移出鎖,那是新的不變式;**N111 的
        退訂正確性依賴 IO 在鎖內**,移出時 ST1 洩漏會原樣復發 —— 見 next-time 08-26 節)。

        逐項取鎖打開了一條舊碼結構上不可能發生的窗:**較舊**的那一發可能在較新的名單
        套用之後才跑完剩下的檔。`_superseded` 因此在每一項重驗一次,過期即整段放棄
        (`seq` 本來就是為這條路存在的,只是以前走不到)。
        """
        async with self._pool_lock:  # CR2:判定 + 名單指派仍是一個原子區(無 await)
            if seq != WATCHLIST_UNORDERED:
                if seq <= self._wl_seq_applied:
                    logger.info(
                        "watchlist seq %d 已過期(已套用 %d),跳過", seq, self._wl_seq_applied
                    )
                    return
                self._wl_seq_applied = seq
            # added / removed **都**以 `_refs` 實況為準(不是 `self._watchlist` 名單):
            # - added:真訂失敗回滾後重送同名單要能重試。
            # - removed:名單那份會被**較舊**那一發覆寫(review ST1/SP3)—— 舊發若在
            #   added 迴圈被 `_superseded` 中斷,它還沒退的檔既不在本發以名單算出的
            #   `removed`(算的時候名單已經是舊發那份),也不在任何人的待辦裡 →
            #   `"watchlist"` ref 永久佔著訂閱位,而畫面上那一檔早就不見了,零訊號。
            #   「持有 watchlist ref 卻不在最新名單」是唯一不會被名單覆寫誤導的判準。
            added = [c for c in codes if "watchlist" not in self._refs.get(c, set())]
            removed = sorted(
                c for c, owners in self._refs.items() if "watchlist" in owners and c not in codes
            )
            # **名單先指派再訂閱**(round4 項 4):每個 `await to_thread` 都讓出 loop,而 TC4
            # 在 SUB 回來後幾乎立刻推第一則 REALTIME。名單留到最後才指派的話,那一則會在
            # `code not in self._watchlist` 的窗內進 `_handle_quote` → meta 轉態補推被擋掉;
            # 盤後沒有後續 tick、flush 又只推 dirty,該檔就卡在 `-` 直到使用者重整。
            # 名單是「意圖」、訂閱是副作用;最終狀態與舊順序等價(舊碼也是不論成敗都指派)。
            self._watchlist = list(codes)
        for code in added:
            async with self._pool_lock:
                if self._superseded(seq):
                    # **break 不是 return**(review ST1/SP3):過期的是「還要訂什麼」,
                    # 不是「還要退什麼」—— 退訂在任何名單下都仍然正確(逐項另有
                    # `code in self._watchlist` 重驗),跳過它就是洩漏訂閱位。
                    break
                if code not in self._watchlist:
                    continue  # 這一檔在等鎖期間已被更新的名單移除
                try:
                    await asyncio.to_thread(self._acquire, code, "watchlist")
                except ConnectionError:
                    logger.warning("watchlist subscribe %s failed", code)
        for code in removed:
            async with self._pool_lock:
                if code in self._watchlist:
                    continue  # 更新的名單又把它加回來了,不退
                await asyncio.to_thread(self._release, code, "watchlist")
                if code not in self._refs:
                    # **真正退訂了才**清(code review A7d,鏡像路徑 `set_main_contract`
                    # 的同款處理)。同一檔可能同時是主圖:無條件清會讓主圖那格的
                    # 「無資料」在使用者把它移出自選之後永久消失 —— TC4 的 no-data
                    # 回呼只在訂閱當下發一次,之後 snapshot 恆 no_data=False。
                    self._no_data.discard(code)
                    # 回補記帳同樣以**訂閱期**為界:真退訂後「今日已回補 / 失敗冷卻」
                    # 的判斷作廢,重新訂閱時回補機會重新開始。不清的話 `_acquire` 的
                    # setdefault 用回同一個舊 state,`group_snapshot` 的入列 guard 恆擋
                    # → 退訂期間的分鐘缺口整天補不回來,而 backfilling / no_data 都是
                    # False,卡片零訊號地空著。冷卻歸零是接受的:re-acquire 是使用者
                    # 驅動(把股票加回自選),不是重試風暴。
                    # **在 loop 側清**:記帳集合是 loop-only 不變式,不可下沉到
                    # `_release`(那個是在 executor thread 跑的)。
                    # `_backfill_pending` 不清 —— 在途 job 之後仍會來扣一次(A3)。
                    #
                    # ⚠ **已知殘留窗**(review A-1,本輪不修):清點只作用於「清的那一刻」。
                    # 退訂當下若有一個 job 還在佇列裡或正跑著 `to_thread(backfill)`,
                    # 它完成時 `_backfilled.add(code)` 會把記帳寫回去 —— 而 generation
                    # 只在 rollover stage1 才 bump,退訂不 bump,worker 的 guard 攔不住。
                    # 窗是秒級(一次 SubHistory 的時間;逾時重排 timer 另由
                    # `_forget_backfill_timeout` 在此一併取消,不會把窗拉到 15s+)且後果與 E-2 同構(那一檔在
                    # 群組輪詢裡被 dedup 擋到下一次日別清空為止)。完整解要 per-code
                    # epoch(退訂時 +1,job 自帶取件時的 epoch,套用前比對),那是新的
                    # 不變式不是註解能帶過的,記 next-time。
                    self._backfilled.discard(code)
                    self._backfill_failed.pop(code, None)
                    self._tick_armed.discard(code)
                    self._forget_backfill_timeout(code)
                    # TradeStatus 前值同以**訂閱期**為界(code review IC-6):留著的話
                    # 重新訂閱後拿上一段訂閱期的前值跟新的第一則比對 = 一則跨訂閱期的
                    # 假轉態,而 episode 旗標還武裝著時更會生出一則沒有起點的假「恢復」。
                    self._trade_status.pop(code, None)
        async with self._pool_lock:
            if self._superseded(seq):
                return
            # 新增的檔立刻給一則種子:不等第一筆成交(冷門股整天可能只有簿更新),
            # 盤後加股也要馬上看得到參考價。啟動期 `_clients` 為空 = no-op,
            # 開機路徑由 `stream()` 的 per-client 種子涵蓋。
            for code in added:
                self._publish(self._quote_payload(code))
            if self._signal_hub is not None:
                # 全量替換 hub 的 membership(新增排 CDP 基準、移除逐出狀態)
                self._signal_hub.on_watchlist(list(codes))

    def _superseded(self, seq: int) -> bool:
        """這一發是否已被更新的名單取代(N111 的逐項重驗判準)。

        `WATCHLIST_UNORDERED`(非生產的直呼)沒有定序資訊,答不出來 → 一律回 False,
        逐項的 `code in self._watchlist` 重驗仍在。生產路徑全部帶號。
        """
        return seq != WATCHLIST_UNORDERED and seq < self._wl_seq_applied

    async def set_main(self, code: str) -> None:
        """現貨主圖(既有 route 入口)= `set_main_contract` 的股號形。"""
        await self.set_main_contract(code)

    async def set_main_contract(self, key: str) -> None:
        """主圖槽位轉移(D15);`key` = 股號 或 `F:<prod>:<ym>` 合約鍵。

        四種轉移共用同一段程式,差別只有兩處條件:

        | 轉移 | 動作 |
        |---|---|
        | 現貨→期貨 | acquire(F:key,main) → release(舊,main) → release_stkfut(舊) → 回補;**不**加對照腿 |
        | 期貨→現貨 | acquire(股號,main) → release(F:舊,main) → release_stkfut(F:舊)(map 查無 → 無害早退) → acquire_stkfut → 回補 |
        | 期貨→期貨 / 現貨→現貨 | 同構類推 |

        **先 acquire 新的再 release 舊的**(既有順序):反過來的話同一檔在
        「現貨→現貨」時會被真退訂再真訂,盤中切回上一檔要重等一次 SUB。
        合約態不加期現對照腿 —— 主圖已經是期貨,再掛一條 HOT 腿只會讓期現價差列
        拿自己跟自己比。
        """
        async with self._pool_lock:  # CR2
            old = self._main
            if old == key:
                return
            await asyncio.to_thread(self._acquire, key, "main")
            self._main = key
            if old is not None:
                await asyncio.to_thread(self._release, old, "main")
                await asyncio.to_thread(self._release_stkfut, old)  # CR3:UNSUB 不佔 loop
                if old not in self._refs:
                    # **真正退訂了才**清「無資料」旗標(code review A7d,同 set_watchlist
                    # 移除檔的既有處理)。留著的話下次切回那一檔,畫面在任何新推播之前
                    # 就先掛上「無資料」—— 而那是上一輪訂閱期的答案,重新訂閱後 TC4 若
                    # 這次有推,旗標也要等到推播到達那一刻才會被清掉。
                    # 還有 owner(例:仍在自選)時**不清**:那格旗標歸側欄不歸主圖,
                    # 無條件清會讓側欄的「無資料」在使用者點開再切走之後永久消失
                    # (TC4 的 no-data 回呼只在訂閱當下發一次)。
                    self._no_data.discard(old)
                    # 回補記帳同以訂閱期為界(理由見 `set_watchlist` removed 迴圈):
                    # 主圖槽位真退訂時,那一檔的「今日已回補 / 失敗冷卻」一併作廢。
                    self._backfilled.discard(old)
                    self._backfill_failed.pop(old, None)
                    self._tick_armed.discard(old)
                    self._forget_backfill_timeout(old)
                    # TradeStatus 前值同以訂閱期為界(理由見 `set_watchlist` removed 迴圈)
                    self._trade_status.pop(old, None)
            if not is_futures_key(key):
                await self._acquire_stkfut(key)
            # 已回補 / 在途不重排(next-time L69):來回切主圖曾讓 2455 一天重複回補
            # 75 次(08-31 實測),每次 = SubHistory + 全量收割。切主圖「順便修補 live
            # 缺口」的保險由 reconnect 清 `_backfilled` 承接(斷線缺口仍會補);真退訂
            # 再切回的檔記帳已清,照樣入列。**只擋這兩道**,no_data / 冷卻不下沉到這裡
            # (`group_snapshot` docstring:被冷卻擋掉會變成主圖整天補不回來)。
            if key not in self._backfilled and self._backfill_pending.get(key, 0) == 0:
                self._enqueue_backfill(key)

    def _spot_trial_now(self) -> bool:
        """現貨試撮旗標 = 交易日曆 AND 時間窗(D4')——`_flush_watchlist_loop` 的翻轉判準。

        日曆來源是 engine 既有的 `is_trading_day` 注入(單一來源);少了它,休市日的
        四個窗邊界各會替全自選補推一輪空 quote,畫面在沒有撮合的日子亮起「(緩)」。
        時鐘走 `self._now_fn`(同 checkpoint 換日判定那顆),窗走模組級純窗函式。
        """
        return self._is_trading_day(self._now_fn().date()) and _spot_trial_window_now()

    def _trial_now(self, code: str) -> bool:
        """該 instrument 當下是否在試撮/緩撮窗內(D1)+ 今天是不是交易日(D4')。

        **每次組 payload 當下現算**,不落 `StockDayState`:試撮期 TC4 不推成交 tick
        (2026-07-21 實測),tick 路徑萃取不到「進窗」事件 —— 掛在狀態機上的旗標
        永遠不會被翻起來,而畫面只是一直不標。現算也天然沒有 stale / 清除的路。

        窗對映走 `trial_windows_for`(唯一定義):期貨鍵空窗 → 恆 False,前端因此
        不必自己判 instrument 種類。
        """
        if not self._is_trading_day(self._now_fn().date()):
            return False
        if is_trial_window(_now_taipei_time(), trial_windows_for(code)):
            return True
        # 第二段(L75,2026-08-31):per-code TradeStatus==1 = 延緩撮合中(2026-08-28 蒐證:
        # 開盤段 11 檔 episode ≈2 min、TWSE「延緩撮合 2 分鐘」形狀;tc4-market-facts)。
        # 只在盤中 09:00–13:30 採信:TradeStatus 只隨 REALTIME 更新,收盤後沒有恢復推播,
        # 最後一則若是 1 會把旗標掛整晚。期貨鍵不進 `_trade_status`(觀測開頭即跳過)→ 恆 False。
        # 值認 "1" 不認「非 0」:值域實測 {0, 1},未知新值走 parse 層 warning,不猜語意。
        st = self._trade_status.get(code)
        return st is not None and st[0] == "1" and "09:00" <= _now_taipei_time()[:5] < "13:30"

    def _disposition_now(self, code: str) -> bool:
        """該檔是否在處置名單(L75):trial 亮起時前端把標籤改「(處置)」——
        分盤撮合的等待期不是暴漲暴跌延緩,標(緩)是錯的敘事。名單 late-bound
        (breadth 引擎盤中更新,整份替換 = 一致快照);期貨鍵恆 False。"""
        if is_futures_key(code) or self._disposition_codes is None:
            return False
        return code in self._disposition_codes()

    def snapshot(self, code: str, *, tape: bool = True) -> dict:
        """`tape=False` 只轉發給 state(見 `StockDayState.snapshot`):群組檢視點卡片
        時沒有明細讀者,兩萬筆逐筆 dict 純浪費。其餘附加欄與全量完全相同。"""
        state = self._states.get(code)
        snap = (
            state.snapshot(tape=tape) if state is not None else StockDayState().snapshot(tape=tape)
        )
        snap["code"] = code
        snap["no_data"] = code in self._no_data
        # 附加點在 engine 而非 `StockDayState.snapshot()`(同 `no_data` 慣例):
        # trial 是引擎時鐘推導的,不是日內狀態機資料。
        snap["trial"] = self._trial_now(code)
        snap["disposition"] = self._disposition_now(code)
        # tc4 / backfilling **不進 snapshot**:畫面的唯一來源是 WS `status` 訊息
        # (那邊是活碼)。同時送兩份等於讓同一個狀態有兩個真相,而 REST 那份是
        # 請求當下的凍結值,重整時機不對就會與 WS 打架。
        # stkfut_prod 同理零讀者(期現價差走 WS `stkfut` 訊息的 prod)。
        return snap

    def quotes(self) -> dict[str, tuple[str, float | None]]:
        """自選各檔的 `(名稱, 漲跌幅%)`(SC-2:同群摘要的資料面)。

        名稱來源只有 `state.meta.name` —— 摘要要印成員名,而 `watchlist_quote` 沒帶。
        缺 meta(盤前 / 冷啟動)回空字串、缺行情回 None,但**該檔仍在字典裡**:
        整檔缺席會讓「群組有幾檔」跟著行情波動。

        名單先取 local 參照(R16):`_watchlist` 以**整份重新指派**更新,所以這一份
        是一致快照。刻意不對 `_states` 做 dict 迭代 —— 那會在並行 `set_watchlist`
        寫入新 state 時炸 RuntimeError(size changed),而本方法是在 Discord worker
        呼叫的,盤中隨時可能交錯。走 `_watchlist` 也天然排除 `F:` 期貨偽鍵
        (`_states` 兩種鍵都有)。

        `chg_pct` 一律走 `_quote_payload` 這個唯一定義,不自己再算一次 —— 除權息日
        的分母是 `meta.ref_milli` 而不是昨收,兩份算式遲早會岔開。
        """
        codes = self._watchlist
        out: dict[str, tuple[str, float | None]] = {}
        for code in codes:
            state = self._states.get(code)
            meta = state.meta if state is not None else None
            name = meta.name if meta is not None else ""
            out[code] = (name, self._quote_payload(code)["chg_pct"])
        return out

    def group_snapshot(self, codes: list[str]) -> dict[str, dict]:
        """群組檢視的唯讀 batch(SC-4)。**不 set_main、不改訂閱池。**

        不得重用 `/api/stock/state/{code}`:那條路會 `set_main`,群組檢視每分鐘 50 次
        會把主圖搶走 → 主圖分時線凍結。

        payload = `light_snapshot()` **整份展開** + 兩個旗標(A1):`ticks` 是數千筆,
        50 檔每 60s 各建一份全量 snapshot 再整份丟掉,既是頻寬炸彈也是白燒 CPU;
        而鍵名沿 `StockDayState` 的單一對映(直接丟 dataclass 會讓前端 `meta.ref`
        undefined → hasRef=false → 紅綠面積靜默消失)。`vp` 是 tick 的**聚合**
        (O(當日成交過的檔位數)),與 tick 筆數脫鉤,故它進得了 light 而 `ticks` 不行。

        ⚠ `no_data` 的推導式**刻意與別處不同**:這裡把「未訂閱」也算 no_data。
        `StockDayState.snapshot()` 根本沒這個鍵,而 `engine.snapshot()` 對未知 code
        回 `False`(語意 = 「TC4 說查無此檔」)—— 群組卡片要答的是「這格畫不畫得出
        東西」,未訂閱與查無此檔對它是同一件事。

        「已訂閱」與 `no_data` 都以**訂閱池 `_refs`** 為準(A6-3),不是 `_states`:
        後者只增不減(退訂只動 `_refs`),拿它當判準會讓卡片對一檔早就退出自選的
        股票答「有資料」,還每 60s 替它發一次 SubHistory。

        順帶把「今日還沒回補」的**已訂閱**成員入列(R12):群組成員多半不是主圖,
        沒有這個入列點就只有當日 live tick、開盤前的分鐘全缺。queue put 不是訂閱
        變更,前一段的「不改訂閱池」仍成立。入列的四道 guard:
          - 未訂閱 → 不入列(等於替不在訂閱池的股票發 SubHistory)
          - `_no_data` → 不入列(A6-4;TC4 已經說沒有這檔,再問也是同一個答案)
          - 已回補 / 在途 → dedup
          - 當日失敗 ≥ `_BACKFILL_MAX_FAILS` → 冷卻(A2)
        冷卻**只擋這條 60s 輪詢的路**與首筆成交 tick 那條(兩者共用 `_backfill_wanted`),
        不下沉到 `_enqueue_backfill`:另外四個入列點(set_main / rollover / reconnect /
        漲跌停值變)都是低頻且對應「使用者當下在看的那一檔」或「日別重來」,被冷卻擋掉
        會變成主圖整天補不回來。
        """
        out: dict[str, dict] = {}
        for code in codes:
            state = self._states.get(code)
            subscribed = code in self._refs
            light = state.light_snapshot() if state is not None else dict(_EMPTY_LIGHT)
            if subscribed and self._backfill_wanted(code):
                # 先入列再讀旗標:順序反了的話第一次請求會回 backfilling=False,
                # 卡片顯示「無資料」而不是「回補中…」,而下一輪(60s 後)才會更正
                self._enqueue_backfill(code)
            # `{**light, ...}`:鍵名的**單一定義**留在 `light_snapshot()`,這裡只轉發。
            # 逐鍵手抄的漂移樣態是後端補了鍵(vwap/high/low/vp)、卡片卻收不到 ——
            # 圖照樣畫得出來,只是少了 VWAP 線 / 高低圈 / VP 條,沒有任何錯誤訊號。
            out[code] = {
                **light,
                "no_data": code in self._no_data or not subscribed,
                "backfilling": self._backfill_pending.get(code, 0) > 0,
            }
        return out

    def _backfill_wanted(self, code: str) -> bool:
        """「今日還沒回補、也沒理由不補」的四道 guard(`group_snapshot` docstring 列的
        那四道,抽出來讓別的入列點共用同一把尺;訂閱與否由呼叫端自己判)。"""
        return (
            code not in self._no_data
            and code not in self._backfilled
            and self._backfill_pending.get(code, 0) == 0
            and self._backfill_failed.get(code, 0) < _BACKFILL_MAX_FAILS
        )

    async def daily_bars(self, code: str, n: int = 25) -> list[DailyBar]:
        """overlay 日 bar;TC4 離線降級空(具體處理 = best-effort null,design R3)。

        **逾時例外照原樣往外拋**(bug/history-timeout-propagation):兩個消費端就是靠
        「空清單 vs 例外」分辨資料面與暫時性 —— SignalHub 對空清單的處置是「無已完成
        日 K,CDP 停用」且當日不再重試(app.py:369-375),對例外才走 X-2b 有限重試;
        overlay route 則把它與既有 `OVERLAY_FETCH_TIMEOUT_S` 逾時歸同一條降級。
        """
        try:
            return await asyncio.to_thread(self._source.fetch_daily_bars, code, n)
        except HistoryTimeoutError:
            raise
        except ConnectionError as e:
            logger.warning("daily_bars %s: TC4 不可用,overlay 降級空(%s)", code, e)
            return []

    async def bars_range(self, code: str, tf: str, start_date: str, end_date: str) -> BarsResult:
        """K 線 bar;TC4 離線降級空(同 daily_bars 的 best-effort 慣例)。

        降級**照舊回空不 raise**,但原因跟著空一起送出去:斷線與「這檔真的沒資料」
        原本在前端收斂成同一句「無 K 線資料」,那正是使用者最需要分清的兩件事。
        """
        try:
            bars, status = await asyncio.to_thread(
                self._source.fetch_bars_range, code, tf, start_date, end_date
            )
            return BarsResult(bars, status)
        except ConnectionError as e:
            logger.warning("bars_range %s(%s): TC4 不可用,降級空(%s)", code, tf, e)
            return BarsResult([], "disconnected")

    # ---- stkfut ----

    async def _acquire_stkfut(self, code: str) -> None:
        entry = self._map.get(code)
        if entry is None:
            return
        try:
            # F: 前綴 = 期貨鍵(source 對映到 TC.F.TWF.<prod>.HOT;real-env 修正)
            await asyncio.to_thread(self._acquire, f"F:{entry['prod']}", f"stkfut:{code}")
        except ConnectionError:
            logger.warning("stkfut subscribe %s failed", entry["prod"])

    def _release_stkfut(self, code: str) -> None:
        entry = self._map.get(code)
        if entry is None:
            return
        self._release(f"F:{entry['prod']}", f"stkfut:{code}")

    # ---- rollover(兩段式,design §2.4)----

    def rollover_stage1(self, new_date: str) -> None:
        """階段一:換日窗(同步、即返)+ 全量重掛(背景 to_thread,CR3);不清狀態;
        generation bump 作廢 in-flight 回補。

        **`set_trade_date` 隨重掛一起下沉到背景 to_thread**(review SP1):N052 之後它
        含一批同步 UNSUBQUOTE(舊窗歸零),而本方法跑在 event loop 上 —— TC4 半死時
        50 檔各等 `_REQ_TIMEOUT_MS`(10 s)= 整條 loop 停擺幾分鐘(WS 心跳、廣播、
        route 全卡)。同檔 `_resubscribe_all` 的「ZMQ REQ 全程 to_thread」是同一個
        不變式,這裡只是把漏網那一支收進去,順序(換窗 → 重掛)也因此仍在同一條
        worker thread 上依序執行。
        代價(接受):stage1 返回到 worker 真的跑到 `set_trade_date` 之間有一個
        **次毫秒級**的窗,期間 source 的日窗還是舊的 —— 那個窗內若有人發回補會抓到
        昨日窗。`_generation` 已在本方法同步 bump,那些結果套用時會被 worker 的
        generation guard 丟掉。
        """
        self._generation += 1
        self._pending_date = new_date
        # TradeStatus 觀測記帳是**日內**語意,清在 stage1(code review IC-5)。只掛 stage2
        # 的話 08:00(checkpoint 武裝)~ 新日首筆之間整段沿用昨日前值與 episode 旗標 →
        # 今天第一則帶 "0" 的推播被判成「恢復」,記出一則帶**今日時戳**卻對照**昨日起點**
        # 的 WARNING,而它讀起來完全像真事件(污染的正是蒐證樣本本身)。
        # stage2 的清空保留 = 快路徑雙保險(那裡是「首筆新日 tick」才跑)。
        self._trade_status.clear()
        # 進 `_tasks` 而非專用欄位:持有參照防 GC(asyncio 不強引用 task)之外,
        # 關機時一併被 close() 取消,且連跑兩次 rollover 不會互相覆寫掉參照
        self._tasks.append(
            asyncio.get_running_loop().create_task(self._resubscribe_all(new_date=new_date))
        )
        logger.info("rollover stage1 → %s (gen=%d)", new_date, self._generation)
        if self._signal_hub is not None:
            # 盤前預抓次日 CDP 基準進暫存區(stage2 只做 swap,開盤第一筆即可用)
            self._signal_hub.on_rollover_pending(new_date)

    async def _resubscribe_all(self, *, new_date: str | None = None) -> None:
        """全量重掛(UNSUB→SUB 冪等,新日窗);ZMQ REQ 全程 to_thread,不佔 event loop。

        `new_date` 非 None(rollover stage1)時,**先**在同一條 worker thread 上換窗
        (含 N052 的舊窗歸零),**再**逐檔重掛 —— 順序是這條修法的整個重點:舊窗 key
        歸零 → 新窗 SUB 走 0→1 才會觸發上游 `ReqSubQuote`。反過來的話舊窗那把 key
        仍 >0,新窗只是多一把,feed 沒被重掛(review SP1)。
        """
        async with self._pool_lock:
            codes = list(self._refs)

        def _do() -> list[str]:
            if new_date is not None:
                self._source.set_trade_date(new_date)
            failed: list[str] = []
            for code in codes:
                try:
                    self._source.subscribe_symbol(code)
                except ConnectionError:
                    # 只收 ConnectionError:其他例外照舊往外拋(壞電文那類要能穿到
                    # close() 的收尾記錄,test_close_completes_even_if_a_task_died_with_exception)
                    logger.warning("rollover resubscribe %s failed", code)
                    failed.append(code)
            return failed

        failed = await asyncio.to_thread(_do)
        async with self._pool_lock:
            # `_failed_resubs` 一律鎖內存取(C-2)。不持鎖合併的話,這一筆可能落在
            # `_retry_round` 段 3 的 `await` 窗內 → 隨後那句成功 discard 直接把它抹掉,
            # 該檔從此不再重掛,而 log 只有換日當下那一行 warning
            self._failed_resubs |= set(failed)

    # ---- 訂閱失敗的對帳式重試(mod/subscribe-retry-recovery)----

    async def _retry_subscribe_loop(self) -> None:
        """常駐迴圈:每輪對帳「該訂而沒訂上的」並補訂。

        與 futures/corr 的 pending-resub 不同,這裡的重試項目是**動態集合**(使用者
        隨時增刪自選、切主圖),所以不留待辦清單、每輪重新對帳 —— 清單式會在
        「使用者已移除該檔」時替不看的股票掛訂閱。
        """
        while True:
            await asyncio.sleep(self._resub_interval_secs)
            try:
                await self._retry_round()
            except Exception:
                # 迴圈死掉 = 復原路徑本身靜默失效(同 corr `_run` 的 rationale)
                logger.exception("訂閱重試輪失敗(續行)")

    async def _retry_round(self) -> None:
        """一輪對帳:快照判準(短鎖)→ 三段重試,每項各自重拿鎖重驗。

        **不是整輪一鎖**:TC4 斷線時單檔 SUBQUOTE 要等 `_REQ_TIMEOUT_MS`(10s)才失敗,
        整輪持鎖會讓 `_pool_lock` 佔用率趨近 100% → set_main / PUT watchlist 卡死。
        每段遇到第一個 `ConnectionError` 就 `break` 出**該段**(不是整輪):`_resub` 對
        單一壞碼可穩定 raise(與連線健康無關),round 級早停會讓一檔壞碼永久餓死後面兩段。
        段內另以 `_round_robin` 輪轉起點:段級 break 只解跨段餓死,固定迭代順序下
        排最前的恆失敗檔會永久餓死**同段**後面所有檔(head-of-line blocking,C-1)。
        """
        self._retry_round_no += 1
        try:
            async with self._pool_lock:
                pending_wl = [
                    c for c in self._watchlist if "watchlist" not in self._refs.get(c, set())
                ]
                # prune:已退訂的檔不再重掛(owner 都沒了,重掛等於訂閱不看的股票)
                self._failed_resubs &= set(self._refs)
                pending_resubs = sorted(self._failed_resubs)
                main = self._main
                stkfut_pending = self._stkfut_owner_missing(main)

            for code in _round_robin(pending_wl, self._retry_round_no):
                async with self._pool_lock:
                    # 鎖內重驗:快照後使用者可能已移除該檔,或重送名單已把它修好
                    if code not in self._watchlist or "watchlist" in self._refs.get(code, set()):
                        continue
                    try:
                        await asyncio.to_thread(self._retry_acquire, code, "watchlist")
                    except ConnectionError:
                        logger.warning("watchlist subscribe %s failed", code)
                        break
                    # 對齊 set_watchlist added 的種子:冷門股整天可能只有簿更新,
                    # 沒有這一則就要等下一筆成交才看得到值。
                    # 不重呼 `signal_hub.on_watchlist` —— membership 在 set_watchlist 已全量設定
                    self._publish(self._quote_payload(code))

            for code in _round_robin(pending_resubs, self._retry_round_no):
                async with self._pool_lock:
                    # 快照是舊值:取鎖前該檔可能已被退訂(`_refs`),或已由並行的
                    # `_resubscribe_all` 動過 `_failed_resubs`。C-2 之後那個集合一律鎖內
                    # 存取,所以這裡重驗讀到的是最新值 —— 不會拿舊快照對已不需要的檔發 SUB
                    if code not in self._refs or code not in self._failed_resubs:
                        continue
                    try:
                        await asyncio.to_thread(self._retry_resubscribe, code)
                    except ConnectionError:
                        logger.warning("rollover resubscribe %s failed", code)
                        break
                    self._failed_resubs.discard(code)

            if main is not None and stkfut_pending:
                async with self._pool_lock:
                    # 主圖切走後不得補掛:替已不看的股票掛腿 + owner refcount 洩漏
                    if self._main == main and self._stkfut_owner_missing(main):
                        entry = self._map[main]
                        try:
                            await asyncio.to_thread(
                                self._retry_acquire, f"F:{entry['prod']}", f"stkfut:{main}"
                            )
                        except ConnectionError:
                            logger.warning("stkfut subscribe %s failed", entry["prod"])
        except _EngineClosing:
            return  # 關機:靜默結束該輪(不得偽裝成 TC4 訂閱失敗的 warning)

    def _stkfut_owner_missing(self, code: str | None) -> bool:
        """該主圖檔有個股期對映、但期貨鍵上沒掛它的 owner(= 這一腿沒訂上)。"""
        if code is None:
            return False
        entry = self._map.get(code)
        if entry is None:
            return False
        return f"stkfut:{code}" not in self._refs.get(f"F:{entry['prod']}", set())

    def _retry_acquire(self, code: str, owner: str) -> None:
        """executor thread:關機中早退,縮小「close 後 source 再被呼叫」的窗。

        cancel 一個正 await `to_thread` 的 task 時 asyncio 側立即回(executor future
        無法中斷),orphan thread 可能跨過 `source.close()` 再 subscribe → TC4 重連
        session 洩漏。此暴露與已出貨的 futures `_resub_loop` 同款,以檢查縮窗即可。
        """
        if self._loop is None:
            raise _EngineClosing
        self._acquire(code, owner)

    def _retry_resubscribe(self, code: str) -> None:
        """executor thread:owner 已在池內,只需重掛 SUB(UNSUB→SUB 冪等)。"""
        if self._loop is None:
            raise _EngineClosing
        self._source.subscribe_symbol(code)

    def _rollover_stage2(self, first_tick: StockTick) -> None:
        """階段二:首筆新日 tick 確認 → reset 全部狀態,觸發 tick 重新 ingest。"""
        assert self._pending_date is not None
        self._trade_date = self._pending_date
        self._pending_date = None
        # **快照後迭代**:`_acquire` 在 executor thread 對 `_states` setdefault 新鍵
        # (自選新增 / 重試輪 / stkfut 腿隨時可能發生),直接迭代 `.values()` 撞上就是
        # RuntimeError —— 迴圈之後的每一步(記帳清空、主圖重回補、hub 的 on_rollover)
        # 全部不跑,而 `_pending_date` 已在上一行清掉 → 這一天不會再有第二次 stage2。
        # 同 `quotes()` 的 R16(那裡顯式辨識過這條 hazard,這裡是漏網的第二處)。
        for state in list(self._states.values()):
            state.reset()
        self._no_data.clear()
        # 回補記帳是**日別**語意:不清的話「今日已回補」會沿用昨天的判斷,新的一天
        # 所有群組成員都不再被入列(而畫面只是空著,沒有任何錯誤訊號)。失敗計數同理
        # ——昨天壞了三次的檔今天要重新有機會。`_backfill_pending` 不清,理由同 reconnect
        # (在途 job 自己會結清;跨日的 in-flight 另由 generation guard 作廢)
        self._backfilled.clear()
        self._backfill_failed.clear()
        self._backfill_timeouts.clear()
        self._tick_armed.clear()
        # 記帳清空了,在途的那幾支 timer 也要一起 —— 它們醒來時會用**新一天**的
        # generation 重排一筆沒有人要的 job(主圖那筆 stage2 自己下面就排了)。
        self._cancel_backfill_timeout_retries()
        # TradeStatus 前值同屬**日別**(D6/S4):跨日殘留會把隔日首則推播誤判成「恢復」
        # 並帶昨日值記一則 WARNING —— 污染的正是蒐證樣本本身,而那一則讀起來像真事件。
        self._trade_status.clear()
        if self._main is not None:
            self._enqueue_backfill(self._main)
        logger.info("rollover stage2 → %s(首筆 %s)", self._trade_date, first_tick.code)
        if self._signal_hub is not None:
            # `_trade_date` 已前進、`_pending_date` 已清 → hub 的 reset_day + swap
            # 拿到的都是新日別
            self._signal_hub.on_rollover()

    async def _checkpoint_loop(self) -> None:
        while True:
            await asyncio.sleep(self._checkpoint_secs)
            now = self._now_fn()
            today = f"{now:%Y-%m-%d}"
            if (
                # 候選交易日(假日靠階段二天然不清空)。判準由 `is_trading_day` 注入:
                # 週末靠 `weekday()` 擋得住,國定假日(平日)擋不住 —— 那天 08:00 一到
                # 就把 source 日窗切到假日,而 stage2 等的新日首筆永遠不會來。
                self._is_trading_day(now.date())
                and now.hour >= 8
                and today != self._trade_date
                and self._pending_date != today
            ):
                self.rollover_stage1(today)

    # ---- source callbacks(source thread → loop)----

    def _on_raw_threadsafe(self, quote: dict) -> None:
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._handle_quote, quote)

    def _on_no_data_threadsafe(self, code: str) -> None:
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._handle_no_data, code)

    def _on_reconnect_threadsafe(self) -> None:
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(
                self._handle_reconnect,
            )

    def _handle_no_data(self, code: str) -> None:
        self._no_data.add(code)
        # 走共用 builder(`no_data` 由 `_no_data` 實況決定,上一行剛加進去)
        self._publish(self._quote_payload(code))

    def _handle_reconnect(self) -> None:
        """TC4 重連:status 推播 + 主圖自癒重回補(design §2.4)。"""
        self.tc4_status = "up"
        self._publish({"type": "status", "tc4": "up", "backfilling": self._backfilling, "engine": True})
        # reconnect **不** bump generation(實碼事實)→ 記帳不會被 generation 作廢帶走,
        # 得顯式清。漏清的話斷線那段的缺口整天補不回來:主圖靠下一行自癒,主圖以外的
        # 成員全靠這次清空才有機會再被 `group_snapshot` / 重連後的首筆成交 tick 入列(R4)。
        # **只清 `_backfilled`**(A3):`_backfill_pending` 是在途計數,清掉之後那些
        # job 回來仍會各扣一次 → 旗標永久假、同一檔又被重複入列一次。斷線期間發出的
        # job 由 worker 自己走失敗路徑結清,不需要外力。
        self._backfilled.clear()
        self._tick_armed.clear()  # 成員靠重連後的首筆成交再補一次斷線缺口
        if self._main is not None:
            self._enqueue_backfill(self._main)

    def _handle_quote(self, quote: dict) -> None:
        symbol = str(quote.get("Symbol", ""))
        # 期現對照腿的判定是 **`.HOT` 後綴**,不是 `TC.F.` 前綴(D1):後者會把月契約
        # leaf(`TC.F.TWF.CDF.202609`)一起吃掉 → 合約主圖永遠收不到自己的推播,
        # 而畫面只是空著。
        if symbol.endswith(".HOT"):
            self._handle_stkfut(quote)
            return
        code = self._symbol_to_key.get(symbol)
        if code is None:
            # 訂閱池外的推播(退訂競態 / 未知 symbol):顯式丟棄。debug 而非 warning ——
            # UNSUB 之後 TC4 仍可能推幾則,那是常態不是異常
            logger.debug("未對映的推播 symbol=%s(訂閱池外,丟棄)", symbol)
            return
        state = self._states.get(code)
        if state is None:
            return
        tick, book, meta = parse_stock_realtime(quote, trial_windows=trial_windows_for(code))
        if is_futures_key(code) and not _in_futures_session(
            tick.time if tick is not None else _now_taipei_hhmm()
        ):
            # 夜盤**整則**早退(D14b + code review A1):tick / book / meta 全擋。
            #
            # 只丟 tick 的舊寫法擋不住另外兩條:夜盤的五檔會蓋掉日盤收盤簿(閃電梯與
            # 五檔整晚跟著夜盤跳,而分時圖與 seq 都不動 → 目視像「還在盤中」)、夜盤的
            # 參考價 / 漲跌停會寫進 meta(隔天早上開盤前拿它算漲跌幅與亮燈)。兩者都
            # 沒有任何錯誤訊號。前端 x 軸窗是 08:45–13:45,收下的夜盤資料本來就沒有
            # 位置可畫。
            #
            # **窗判準的取捨**:有 tick 就用 tick 時刻(TC4 時戳,權威);純簿更新
            # (`TradeQuantity=0`)沒有時刻欄可用,只能退到本機時鐘。代價是窗邊界前後
            # 幾秒可能誤判一兩則簿更新 —— 相對於「整夜的簿覆蓋日盤簿」,這是划算的。
            return
        # 蒐證通道(D6):**只記錄不判定**。落點在夜盤早退之後(code 已解出、parse
        # 已完成),不影響下面任何一條既有路徑。
        self._observe_trade_status(code, quote)
        # 「無資料」復原:**命中才推**。寫成無條件 discard + publish 會變成每 tick 廣播,
        # 直接打穿 1s 節流(W-17)。
        recovered = code in self._no_data
        self._no_data.discard(code)
        was_meta_none = state.meta is None
        prev_limits = (
            None if state.meta is None else (state.meta.upper_milli, state.meta.lower_milli)
        )
        state.update_book(book)
        state.update_meta(meta)
        # 漲跌停值變化 → 主檔重跑回補(round6 項 2 / Phase 5 review P1)。
        # `apply_backfill` 的鎖停補判要拿 upper/lower 當依據,但**meta 與回補 tick 不同源**:
        #   (a) `set_main` 訂閱後立刻把回補入列,而 meta 只有 REALTIME 才寫入 ——
        #       冷啟動後第一次開一檔鎖停股時回補可能先跑完,補判整段跳過
        #   (b) `_rollover_stage2` 對每個 state `reset()` 而 reset 刻意保留 meta ——
        #       主檔若不是觸發 rollover 的那一檔,會拿**昨日**的漲跌停比對今日 tick
        # 兩種失效都零錯誤訊號。用「值變了就重跑」一次涵蓋兩者:冷啟動是 None → 有值,
        # 跨日是舊值 → 新值。值沒變就不重跑,避免每則 REALTIME 都排隊。
        #
        # 收件人放寬到「今日已回補過的檔」(A6-5):群組成員走 `group_snapshot` 入列,
        # 同樣是「回補先跑完、meta 後到」的順序,舊條件只認 `_main` 的話成員的鎖停側標
        # 整天停在 neutral(內外盤副圖整片灰、外盤比分母為 0),而畫面毫無異狀。
        # 限定 `_backfilled` 而不是所有檔:沒補過的檔本來就會被入列點涵蓋,無條件重跑
        # 等於讓每一檔的第一則 REALTIME 都多排一次 job。
        if (
            (code == self._main or code in self._backfilled)
            and meta.upper_milli is not None
            and (meta.upper_milli, meta.lower_milli) != prev_limits
        ):
            self._enqueue_backfill(code)
        # **期貨 instrument 不武裝換日**(D14a,夜盤雙保險之一):個股期夜盤跨午夜,
        # 那些 tick 的 `trade_date` 會比日盤主圖早一天到 → 拿它武裝 stage1 會在夜盤把
        # 全部現貨狀態 reset(當日分時線整條消失,而畫面上只是「圖突然空了」)。
        arms_the_day = not is_futures_key(code)
        if (
            tick is not None
            and arms_the_day
            and self._pending_date is None
            and tick.trade_date > self._trade_date
        ):
            # 快路徑(CR5 / design §2.4):checkpoint 沒跑(週六補市日 weekday≥5)仍收到
            # 新日 tick → 先補 stage1 再走 stage2
            self.rollover_stage1(tick.trade_date)
        # **完成(stage2)不限現貨鍵**(E-3):期貨日盤 08:45 開盤而現貨 09:00 才有首筆,
        # 舊條件讓那 15 分鐘的合約 tick 落到下面的 `state.ingest` —— 昨日 `_last_cum`
        # 使它恆 False(不 apply 不推播),分時圖左緣整段消失且零錯誤訊號;自選空 +
        # 主圖合約時更是永遠等不到現貨首筆 → 整天不換日。
        # 夜盤沒有誤觸的路:(a) 夜盤 tick 在上面的 `_in_futures_session` 就整則早退,
        # 到得了這裡的期貨 tick 必屬日盤 08:45–13:45,其 `trade_date` 即當日;
        # (b) 00:00–05:00 夜盤時段 `_pending_date` 恆 None(checkpoint 08:00 才武裝)。
        #
        # **對現貨側的既定效果**(review A-3,不是副作用是語意):`_rollover_stage2`
        # 是**全池** reset,觸發者是誰不改變作用範圍 —— 放寬之後那一刻從現貨首筆
        # (09:00)提前到期貨開盤(08:45)。也就是 08:45–09:00 之間:現貨的盤前圖被
        # 清空(昨日殘留本來就該清)、`seq` 歸零觸發前端全量 refetch、stage1 重掛時
        # 掛上的 no-data 旗標(`_no_data`)一併被清。三者都是兩段式 rollover 原本就
        # 有的語意,只是「首筆」的定義從現貨放寬到日盤合約而提早了十五分鐘。
        # 合約鍵觸發、現貨池被 reset 的這條跨 instrument 邊界由
        # `test_daytime_contract_tick_stage2_resets_the_spot_pool` 鎖住。
        #
        # 已知殘留限制:補市日(週六)+ 自選空 + 主圖合約時 checkpoint 不武裝、現貨
        # 快路徑也沒有現貨 tick → 仍整天不換日(極罕見,不在本輪展開)。
        if (
            tick is not None
            and self._pending_date is not None
            and tick.trade_date == self._pending_date
        ):
            self._rollover_stage2(tick)
        # **首筆當日成交 tick → 入列回補**(perf/opening-backfill-parallel S2):其餘入列點
        # 全是需求驅動(set_main / 群組檢視 60 s 輪詢 / rollover 與 reconnect 只排主圖 /
        # 漲跌停值變只認已補過的檔),08-28 開盤 09:00→09:02 零回補、直到 user 打開群組
        # 檢視。不改成「訂閱當下入列」:08:14 開站對 TC4 建當日 TICKS 歷史訂閱只會
        # 30 s 逾時 ×3 再「放棄」(08-28 主圖 6207 實錄),40 檔 = 20 分鐘必敗 REQ;
        # 首筆成交才是「TC4 有東西可補」的正面訊號,薄股沒成交也不會卡住單工 worker。
        # 放在 stage2 **之後**:換日首筆排的是新一天(新 generation)的 job。
        # 試撮成交帶 `is_trial`(`ingest` 也不收),盤前 08:30–09:00 不觸發。guard 與
        # `group_snapshot` 同一把尺(`_backfill_wanted`):在途 / 已補 / 冷卻都不重排。
        # **每個訂閱期只點火一次**(`_tick_armed`,review F-2)、**主圖不走這條**
        # (review F-3:主圖有 set_main / rollover / reconnect 三個入列點,而它的失敗會把
        # 全站 tc4_status 打 down —— 多一條高頻入列點只是多一條誤報路)。
        if (
            tick is not None
            and code not in self._tick_armed  # 最具選擇性的判斷放最前:訂閱期內第 2 筆起全在這裡早退
            and not tick.is_trial
            and tick.trade_date == self._trade_date
            and code != self._main
            and code in self._refs
        ):
            self._tick_armed.add(code)
            if self._backfill_wanted(code):
                self._enqueue_backfill(code)
        if tick is not None and state.ingest(tick):
            if code == self._main:
                self._publish(
                    {
                        "type": "tick",
                        "code": code,
                        "t": tick.time,
                        "p": tick.price_milli,
                        "q": tick.qty,
                        "side": tick.side,
                        "b": tick.bid_milli,
                        "a": tick.ask_milli,
                        # 當日高低掛 tick 而不另立 meta 訊息型別:engine 只發
                        # tick / book / watchlist_quote 三種,而高低本來就只在成交時
                        # 才會變,與 tick 同步天然正確。ingest 為真必已跑過 _apply,
                        # 所以這兩個在此必不為 None。
                        "h": state.high_milli,
                        "l": state.low_milli,
                        "seq": state.seq,
                    }
                )
            # **只收自選碼**(D16):`watchlist_quote` 的消費端是側欄,它以 code 對照
            # 自選名單 —— 合約鍵(或任何非自選的主圖檔)混進去就是一則對不上任何項目
            # 的訊息,而側欄不會報錯,只會多出一格幽靈卡片。
            if code in self._watchlist:
                self._dirty_watchlist.add(code)
            if self._signal_hub is not None:
                # 掛在 `ingest` 為真的分支內:試撮與重複 tick 已被短路,訊號層天然
                # 不必重複判(回補重放走 `apply_backfill`,不經過這裡 — SC-5)
                self._signal_hub.on_tick(code, tick, state)
        # 轉態補推(round4 項 4):meta 由 None → 有值 = 這一檔第一次拿到參考價;
        # 「無資料」復原同理。冷門股整天可能只有簿更新、盤後更是零成交,
        # `_dirty_watchlist` 永遠不會被加進去 → 不補推就永遠是 `-`。
        # 放在 ingest **之後**:同一則若也帶成交,推出去的就是新價而不是空值。
        if (recovered or was_meta_none) and code in self._watchlist:
            self._publish(self._quote_payload(code))
        if code == self._main:
            self._publish({"type": "book", "code": code, "bids": book.bids, "asks": book.asks})
        # 簿路(鎖板打開的無成交觸發)掛在**函式尾端** — 兩段式 rollover 的快路徑與
        # stage2 都在上面跑完,這裡看到的 `state` 與日別已是最終態。
        # `_pending_date` 未清 = stage1 已觸發但新日首筆未到:此刻的簿是今日的、
        # latch 還是昨日的,對照下去會誤發 `limit_open`(design R2-2)。
        if self._signal_hub is not None and self._pending_date is None:
            self._signal_hub.on_book(code, state)

    def _observe_trade_status(self, code: str, quote: dict) -> None:
        """per-code `TradeStatus` 轉態觀測 log(D6)——「盤中延緩撮合」的蒐證工具。

        本輪**不據此判定任何狀態**(值域 / 起訖 / 恢復皆未實測,第二段才做 per-code
        偵測);這裡只留可 grep 的紀錄,前綴 `trade-status-observe`。從 raw quote dict
        讀而不動 parse 層簽名:parse 那則 warning 管值域(r2-F5 契約,原文不動),
        engine 這則管轉態時序,對帳時是同事件兩則。

        分層(窗外 WARNING / 其餘 DEBUG):窗內 0↔1 是已知常態(2026-07-21 實測
        13:25–13:30 共 213 筆),全部升級成 WARNING 會把真正要抓的窗外事件淹掉。
        **蒐證要併看 DEBUG 級**:窗內起 / 窗外訖的 episode(例:13:25 試撮窗內開始、
        跨過 13:30 才恢復的延緩撮合)在本段規則下全程只有 DEBUG —— 13:25–13:30 前後的
        樣本只 grep WARNING 會整段看不到(code review D6-2;第一段刻意不改,改了就動到
        SC-5(c) 的「窗內轉態不進 WARNING」口徑)。

        窗判準走 `_observe_window_now`(**觀測專用窗**,兩端各寬 2s)而不是 `_trial_now`:
        本機時鐘與 TC4 時戳的秒級偏移會在窗邊界產出成對假 WARNING(D6-1,理由詳見那支)。

        守門各自對應一種會污染樣本的假事件:
        - **期貨鍵跳過**:空窗讓 `_trial_now` 恆 False → 任何轉態都誤落「窗外」分支,
          個股期整天噴假 WARNING。
        - **首見值三分**(IC-1):首見 "0",或首見非 "0" 但在窗內 → 只播種
          (`None→x` 不是轉態;冷啟動落在試撮窗內時 255 檔齊帶 "1" 更不能齊噴);
          首見非 "0" 且窗外 → **記一則** `first_seen=1` + 武裝 episode ——「訂閱前那一檔
          就已經在延緩撮合」是最可能的取樣路徑,靜默掉等於整段 episode 蒐證消失。
        - **同值不記**:每則 REALTIME 都帶 TradeStatus,不比對前值就等於逐則記錄。
        """
        if is_futures_key(code):
            return
        # 缺欄 / 空字串視同 "0"(parse 既有 `or "0"` 語意,觀測與判定同基準)
        status = str(quote.get("TradeStatus", "0") or "0")
        # 缺欄印 `-`(IC-6):純簿更新沒有 `TradeQuantity`,印空字串的話蒐證檔會留下
        # `qty=` 這種讀不出是「沒這欄」還是「零成交」的紀錄。
        qty = quote.get("TradeQuantity") or "-"
        in_window = _observe_window_now()
        prev = self._trade_status.get(code)
        if prev is None:
            trial_before = self._trial_now(code)
            if status != "0" and not in_window:
                logger.warning(
                    _TRADE_STATUS_FIRST_FMT, code, status, _now_taipei_time(), in_window, qty
                )
                self._trade_status[code] = (status, True)
            else:
                self._trade_status[code] = (status, False)
            # 「訂閱前那一檔就已經在延緩撮合」的首見 1:亮燈與蒐證同一時刻(pr-167 F-01)
            self._notify_trade_status_flip(code, trial_before)
            return
        prev_status, episode = prev
        if status == prev_status:
            return
        # 轉態才算(同值已早退):此刻 dict 還是舊值,先取翻轉前答案(熱路徑零成本)
        trial_before = self._trial_now(code)
        args = (
            code,
            prev_status,
            status,
            _now_taipei_time(),
            in_window,
            qty,
        )
        if status != "0" and not in_window:
            # 盤中延緩撮合的候選 evidence:窗外出現非正常狀態
            logger.warning(_TRADE_STATUS_FMT, *args)
            episode = True
        elif status == "0" and episode:
            # 起訖成對(蒐證要看得出持續多久);沒有起點的恢復不記,否則常態推播
            # 每回到 "0" 都噴一則
            logger.warning(_TRADE_STATUS_FMT, *args)
            episode = False
        else:
            logger.debug(_TRADE_STATUS_FMT, *args)
        self._trade_status[code] = (status, episode)
        self._notify_trade_status_flip(code, trial_before)

    def _notify_trade_status_flip(self, code: str, trial_before: bool) -> None:
        """per-code TradeStatus 轉態的推播接點(pr-167 F-01)。

        延緩撮合的定義就是期間沒有成交 tick —— tick 驅動的 `_dirty_watchlist` 路徑
        整段 episode 不會替這檔發 quote(flush 的 `state.last is None` skip 也會把
        盤前 / 無成交檔擋掉),`_trial_now` 第二段的值算對了也推不出去。這裡在
        「轉態且改變 `_trial_now(code)` 答案」時直接 publish(繞過 dirty 路徑;
        對任意 code 直發 `watchlist_quote` 是 `_handle_no_data` 的既有先例),
        收件人沿 `_trial_flip_targets` 同一套規則:自選碼 + 現貨主圖碼。
        期貨鍵到不了這裡(`_observe_trade_status` 開頭已跳過)。
        一次轉態最多一則,episode 一天量級是「檔 × 起訖」,不打穿 1s 節流。"""
        if self._trial_now(code) == trial_before:
            return
        if code in self._watchlist or code == self._main:
            self._publish(self._quote_payload(code))

    def _handle_stkfut(self, quote: dict) -> None:
        prod = str(quote.get("Security", ""))
        code = self._prod_to_code.get(prod)
        if code is None:
            return
        name = str(quote.get("SecurityName", ""))
        if code not in name:
            logger.warning("stkfut 對映不符:%s 推播 SecurityName=%s(對映表過期?)", prod, name)
        price = to_milli(str(quote.get("TradingPrice", "")))
        if price is None:
            return
        state = self._states.get(code)
        last = state.last if state is not None else None
        basis = price - last.price_milli if last is not None else None
        self._publish({"type": "stkfut", "code": code, "prod": prod, "p": price, "basis": basis})

    # ---- backfill worker(單工;guard = job 自帶 code ∧ generation)----

    def _enqueue_backfill(self, code: str) -> None:
        """入列回補 job 的**唯一**接點(六個產出點共用:set_main / rollover stage2 /
        reconnect / 漲跌停值變 / group_snapshot / 首筆當日成交 tick)。

        `_backfill_pending` 必須與 put 同步寫入 —— 分開寫的話,某個入列點漏寫就會讓
        `backfilling` 旗標與群組 dedup 對那條路徑靜默失準(卡片顯示「無資料」而不是
        「回補中…」,或同一檔被重複入列灌爆單工 worker)。
        """
        self._backfill_pending[code] = self._backfill_pending.get(code, 0) + 1
        self._backfill_jobs.put_nowait((code, self._generation))

    def _backfill_settled(self, code: str) -> None:
        """在途計數 −1(worker 的每一條離開路徑都要經過)。

        歸零就移除鍵而不是留一個 0:`in` 形式的判斷在別處(測試、日後的程式碼)是
        自然寫法,留著 0 會讓它答錯而型別上完全合法。
        """
        left = self._backfill_pending.get(code, 0) - 1
        if left > 0:
            self._backfill_pending[code] = left
        else:
            self._backfill_pending.pop(code, None)

    def _arm_backfill_timeout_retry(self, loop: asyncio.AbstractEventLoop, code: str) -> None:
        """`_BACKFILL_TIMEOUT_RETRY_SECS` 後重新入列;**同 code 的舊 timer 先取消**。

        孤兒 timer 的失效樣態(同 SignalHub `_schedule_basis_retry` 那條):它照樣醒來
        多打一次 TC4,重試預算雙倍燒掉,而 `_backfill_timeouts` 的上界看起來還在。
        """
        old = self._backfill_timeout_handles.pop(code, None)
        if old is not None:
            old.cancel()
        self._backfill_timeout_handles[code] = loop.call_later(
            _BACKFILL_TIMEOUT_RETRY_SECS, self._fire_backfill_timeout_retry, code
        )

    def _fire_backfill_timeout_retry(self, code: str) -> None:
        """timer 到期 → 出帳後入列。

        **先出帳**:handle 已經用掉了,留在 dict 裡會讓 `close()` / rollover 去取消一支
        死 handle,而下一輪逾時排的那支新 timer 反而被當成「舊的」取消掉。
        """
        self._backfill_timeout_handles.pop(code, None)
        self._enqueue_backfill(code)

    def _forget_backfill_timeout(self, code: str) -> None:
        """退訂 / 主圖槽位真退訂時呼叫:取消該 code 在途的逾時重排 timer + 清逾時記帳。

        兩份記帳同以**訂閱期**為界(與 `_backfilled` / `_backfill_failed` 同款)。不清的話
        孤兒 timer 15s 後照樣對已 release 的 code 發 SubHistory,成功時 `_backfilled.add`
        把剛清掉的記帳寫回去;而重新訂閱時重試預算已被上一段訂閱期吃掉。
        """
        handle = self._backfill_timeout_handles.pop(code, None)
        if handle is not None:
            handle.cancel()
        self._backfill_timeouts.pop(code, None)

    def _cancel_backfill_timeout_retries(self) -> None:
        """取消並清空全部在途重排 timer(`close()` 與 rollover stage2 共用的唯一取消點)。"""
        for handle in self._backfill_timeout_handles.values():
            handle.cancel()
        self._backfill_timeout_handles.clear()

    async def _backfill_worker(self) -> None:
        """單工 worker;出隊時把佇列裡**當下全部**的 job 一次取出,整批先交 source
        `prepare_backfill`(對每檔送 SubHistory 讓 TC4 平行備資料),再逐檔收割
        (perf/opening-backfill-parallel S1-b;TXO `fetch_backfill` 的「先全訂再收割」樣板)。

        逐檔「Sub → 等首頁 → 收」讓每檔各付一次 TC4 備資料的等待,單工串起來就是
        prod 08-28 的一秒一檔;先全訂之後輪到第 2 檔起首頁多半已備妥。每檔的處置
        (generation 早退 / 逾時重排 / 失敗記帳 / 套用)逐字沿用 `_run_backfill_job`,
        批次只是把「誰先 Sub」提前,不改順序、不改單工套用。

        單筆不 prepare:`backfill` 自己就會 Sub,多發一次是純代價。過期 job 不進批次
        (它們在 `_run_backfill_job` 一進門就被丟棄結清,對它們 Sub 是替沒人要的 job 打 TC4)。
        """
        while True:
            batch = [await self._backfill_jobs.get()]
            while True:
                try:
                    batch.append(self._backfill_jobs.get_nowait())
                except asyncio.QueueEmpty:
                    break
            fresh = list(
                dict.fromkeys(code for code, generation in batch if generation == self._generation)
            )  # 去重(review J2):set_main 不過 guard,同批同 code 只 Sub 一次
            if len(fresh) >= 2:
                try:
                    await asyncio.to_thread(self._source.prepare_backfill, fresh)
                except ConnectionError as e:
                    # source 已是 best-effort;這裡再擋一層是因為逸出 = worker 整條死掉
                    # (review F-1)。失敗交逐檔 backfill 自己去撞,那條路的處置齊全。
                    logger.warning("prepare_backfill 失敗(%s);改逐檔回補", e)
                except Exception:
                    # CR4 同款:非連線類例外不得殺死 worker
                    logger.exception("prepare_backfill unexpected failure(worker 續行)")
            for code, generation in batch:
                await self._run_backfill_job(code, generation)

    async def _run_backfill_job(self, code: str, generation: int) -> None:
        """一筆回補 job 的完整處置(原 `_backfill_worker` 迴圈本體,逐字搬出)。"""
        # 取件早退**只比 generation**(design v3 R12):job 自帶 code,收件人是那一檔
        # 自己的 state 而不是「當下的主圖」。綁 `_main` 會讓群組成員的 job 全部被
        # 靜默丟棄(零錯誤訊號,卡片只是一直空著)。
        if generation != self._generation:
            self._backfill_settled(code)
            return
        self._backfilling = code
        self._publish({"type": "status", "tc4": self.tc4_status, "backfilling": code, "engine": True})
        try:
            ticks = await asyncio.to_thread(self._source.backfill, code)
        except HistoryTimeoutError:
            # **先於** ConnectionError(它是子類):逾時 ≠ TC4 掛了。打 `tc4_status`
            # 會讓整個畫面掛上「達錢 4 連線中斷」而達錢 4 好得很;計進
            # `_backfill_failed` 則會吃掉真失敗的冷卻額度。這條路唯一該做的是
            # **隔一會兒再排一次** —— 而那正是舊碼(回空)整天都不會做的事。
            self._backfilling = None
            self._backfill_settled(code)
            if code not in self._refs:
                # release 時已在佇列 / 正跑的 job 之後才逾時:這一檔已無 owner,不記帳
                # 不武裝 —— 否則 15s 後對已退訂的 code 再打 TC4,終局 `_backfilled.add`
                # 把 release 清掉的記帳寫回去(2026-08-22 review;判準 = 訂閱池 `_refs`)。
                logger.info("backfill %s timeout 但已退訂,不重排", code)
                # 補推與其他離開路徑同款:不推的話「回補中…」徽章永遠掛著(TQ-4)
                self._publish({"type": "status", "tc4": self.tc4_status, "backfilling": None, "engine": True})
                return
            tries = self._backfill_timeouts.get(code, 0) + 1
            if tries <= _BACKFILL_TIMEOUT_MAX_RETRIES:
                self._backfill_timeouts[code] = tries
                logger.warning(
                    "backfill %s timeout(非 TC4 down),%.0fs 後重排(第 %d/%d 次)",
                    code,
                    _BACKFILL_TIMEOUT_RETRY_SECS,
                    tries,
                    _BACKFILL_TIMEOUT_MAX_RETRIES,
                )
                loop = self._loop
                if loop is not None:
                    self._arm_backfill_timeout_retry(loop, code)
            else:
                logger.warning(
                    "backfill %s timeout 重試 %d 次仍未備妥,放棄(當日不再重排)",
                    code,
                    _BACKFILL_TIMEOUT_MAX_RETRIES,
                )
                # 放棄 = **當日不再入列**(與逾時旗標之前的行為逐字相同)。
                # `group_snapshot` 那條 60s 輪詢的四道 guard 看得到的是 `_backfilled`
                # / `_no_data` / 在途 / `_backfill_failed`,唯獨看不到逾時記帳 ——
                # 不進 `_backfilled` 的話它會每 60s 把同一檔重新推回單工 worker,
                # 重試上界形同虛設,而 TC4 歷史通道是整個群組檢視共用的稀缺資源。
                self._backfilled.add(code)
            self._publish({"type": "status", "tc4": self.tc4_status, "backfilling": None, "engine": True})
            return
        except ConnectionError:
            # 全域 `tc4_status` **只由主圖的失敗決定**(A2)。群組檢視把非主圖成員
            # 也送進這條單工 worker 之後,一檔成員的 SubHistory 失敗會把整個畫面
            # 打上「達錢 4 連線中斷」而達錢 4 好得很 —— 使用者據此判斷的每一件事
            # (要不要重開、要不要相信盤面)都被誤導。主圖那條路維持舊語意:
            # 使用者當下就在看那一檔,靜默降級會讓他以為畫面是真的。
            self._backfilling = None
            self._backfill_settled(code)
            fails = self._backfill_failed.get(code, 0) + 1
            self._backfill_failed[code] = fails
            if code == self._main:
                logger.exception("backfill %s failed(主圖 → tc4 down)", code)
                self.tc4_status = "down"
            else:
                logger.warning(
                    "backfill %s failed(成員;當日第 %d 次,達 %d 次即停止入列)",
                    code,
                    fails,
                    _BACKFILL_MAX_FAILS,
                )
                # 這條路不設 `_backfilled`、也不武裝 timer,tick 點火權若已用掉,該檔當日就只剩
                # 群組檢視 60 s 輪詢救得回來(pr-153 F-01)。還回點火權讓下一筆成交再排一次;
                # 預算由 `_BACKFILL_MAX_FAILS` 封口 —— 每次重排都先付一次真失敗 REQ,第 3 次後
                # `_backfill_wanted` 自然擋下,不會重演逾時路徑那種毫秒燒盡(那條靠 timer 節奏)。
                self._tick_armed.discard(code)
            # 兩條路都要補推:不推的話「回補中…」徽章永遠掛著而內部態早就清了(TQ-4)
            self._publish({"type": "status", "tc4": self.tc4_status, "backfilling": None, "engine": True})
            return
        except Exception:
            # CR4:非連線類例外(壞電文 JSONDecodeError 等)不得殺死 worker —
            # 死掉 = 之後所有回補靜默失效、backfilling 永久卡住
            logger.exception("backfill %s unexpected failure(worker 續行)", code)
            self._backfilling = None
            self._backfill_settled(code)
            self._backfill_failed[code] = self._backfill_failed.get(code, 0) + 1
            # 與 ConnectionError 成員分支同款(pr-153 F-01 / round-1 F-D):這條也不設
            # `_backfilled`、不武裝 timer,點火權不還回就是當日 tick 通道死掉;預算同由
            # `_BACKFILL_MAX_FAILS` 封口。主圖本來就不走 tick 路徑,discard 對它是 no-op。
            self._tick_armed.discard(code)
            self._publish({"type": "status", "tc4": self.tc4_status, "backfilling": None, "engine": True})
            return
        self._backfilling = None
        # 套用 guard:rollover 作廢 in-flight 回補 → 丟棄(design §2.3);
        # 另過濾非當日列(防舊日窗殘留資料混入新日狀態)。
        # **不再比 `_main`**(design v3 R12,同取件早退的 rationale)。
        if generation == self._generation:
            state = self._states.get(code)
            if state is not None:
                state.apply_backfill([t for t in ticks if t.trade_date == self._trade_date])
                self._backfilled.add(code)  # 套用成功才記帳
        # 在途記帳一律在此結清(套用 / 失敗 / 丟棄三條路都經過)
        self._backfill_settled(code)
        self._publish({"type": "status", "tc4": self.tc4_status, "backfilling": None, "engine": True})

    # ---- 廣播 ----

    def _quote_payload(self, code: str) -> dict:
        """`watchlist_quote` 的**唯一** payload builder(round4 項 4)。

        所有產生點共用這一份,否則同一個訊息型別會長出多種形狀,而消費端只會在缺欄位
        那一刻靜默降級。

        **判準,不是清單**(N101):凡是要把 `watchlist_quote` 推出去的地方一律呼叫本
        函式,不得就地組 dict。要看現況有幾處走
        `grep -n "_quote_payload" copycat/server/stock_engine.py` —— 原本這裡寫「四個
        產出點」,到 2026-08-13 spec review 就已經對不上,再寫一次只是換一個會漂的數字。

        尚無成交時參考價走**獨立欄位 `ref`**,絕不塞進 `p` —— 塞進 `p` 會讓新舊 client
        都把昨收讀成今價。取 `meta.ref_milli` 而不是 `y_close`:`chg_pct` 的分母就是它,
        除權息日拿昨收顯示、漲幅卻對 ref 算會做出自相矛盾的側欄。
        """
        # 「無資料」時**所有值欄位一律 None**(round4 之前的既有契約)。改走共用 builder
        # 之後若讓 p/vol 沿用最後已知值,訊息就變成「no_data=True 卻夾帶成交價」——
        # 現行側欄先判 no_data 所以畫面不會錯,但那是巧合式的保護,任何沒有同款判斷順序
        # 的消費端會把它讀成有效報價。
        no_data = code in self._no_data
        state = self._states.get(code)
        last = None if no_data or state is None else state.last
        meta = None if no_data or state is None else state.meta
        chg_pct: float | None = None
        if last is not None and meta is not None and meta.ref_milli:
            chg_pct = round((last.price_milli - meta.ref_milli) / meta.ref_milli * 100, 2)
        return {
            "type": "watchlist_quote",
            "code": code,
            "p": last.price_milli if last is not None else None,
            "chg_pct": chg_pct,
            # 這個 `vol` = TC4 當日累積量(`last.cum_vol`),**不是** REST snapshot 的
            # `vwap_vol`(去重剔試撮後的 Σqty / vwap 分母)。兩者曾同名反義,
            # 改名理由與對照見 `live/stock_state.py::snapshot` 的 `vwap_vol`(FC-2)。
            "vol": last.cum_vol if last is not None else None,
            # 尚無成交才給參考價,與 `p` **互斥** —— 兩者同時有值會讓消費端分不出
            # 「今天的價」與「昨天的基準」
            "ref": None if last is not None else (meta.ref_milli if meta is not None else None),
            # 側欄漲跌停亮燈用。**不可讓前端拿 chg_pct ≈ ±10% 猜** —— ETF ±20%、
            # 無漲跌幅商品都會誤判。`no_data` 時 meta 已為 None → 自動滿足
            # 「所有值欄位一律 None」的既有契約,不新增例外路徑。
            "upper": meta.upper_milli if meta is not None else None,
            "lower": meta.lower_milli if meta is not None else None,
            "no_data": no_data,
            # 試撮/緩撮窗旗標(D2)。**旗標類,不受「no_data 時值欄位一律 None」約束**
            # (同 `no_data` 自身):它答的是「這個時刻交易所在不在撮合」,與該檔有沒有
            # 資料無關 —— no_data 列由前端規則決定不標(SC-1),不在這裡分岔。
            "trial": self._trial_now(code),
            "disposition": self._disposition_now(code),
        }

    def stream(self) -> AsyncGenerator[dict, None]:
        # 連線先送一輪自選種子(round4 項 4)。側欄開頁 / 盤後全是 `-` 的根因是
        # 「quote 只有 tick 驅動的生產點」—— 新 client 連上時沒有任何歷史訊息可收,
        # 而不是節流太慢。修在這個接點,開頁與重連都天然自癒(與 ws_corr / ws_river
        # 「連線先送快照」的既成慣例一致)。種子走 `stream(seed=...)` 而非 `publish`
        # (後者會打到所有 client);50 檔對 queue maxsize 安全。
        return self._ws.stream([self._quote_payload(code) for code in self._watchlist])

    def _publish(self, msg: dict) -> None:
        self._ws.publish(msg)

    def _trial_flip_targets(self) -> list[str]:
        """窗翻轉要補推的收件人:自選全碼 + **現貨**主圖碼(D3)。

        主圖也收 `watchlist_quote` 是既有先例(`_handle_no_data` 對任意 code 發,
        前端靠它把 noData 帶進 accum):非自選的預覽檔開著頁時,轉態只有這條路帶得進去。
        期貨主圖鍵不推 —— `trial` 恆 False,推出去只是一則側欄對不上任何項目的訊息。
        去重是為了「各一則」:同一檔既是自選又是主圖時發兩則,節流語意就開始漂。
        """
        codes = list(self._watchlist)
        main = self._main
        if main is not None and not is_futures_key(main) and main not in codes:
            codes.append(main)
        return codes

    async def _flush_watchlist_loop(self) -> None:
        """側欄節流:1s 合併一則(design §2.4)+ 試撮窗翻轉補推(D3)。"""
        while True:
            await asyncio.sleep(self._throttle)
            # 掛既有 1s loop 而不加新 task:一天僅 4 次邊界事件(08:30 / 09:00 /
            # 13:25 / 13:30),直接 publish 不打穿節流。
            trial_on = self._spot_trial_now()
            if trial_on != self._trial_on:
                self._trial_on = trial_on
                for code in self._trial_flip_targets():
                    # **繞過下面 dirty 路徑的 `state.last is None` skip**:盤前無成交
                    # 正是要標「(緩)」的時刻,而那條 skip 讓那些檔永遠不進補推路徑
                    # (試撮期 TC4 也不推成交 tick → dirty 永遠不會被加進去)。
                    self._publish(self._quote_payload(code))
            dirty, self._dirty_watchlist = self._dirty_watchlist, set()
            for code in dirty:
                state = self._states.get(code)
                if state is None or state.last is None:
                    continue
                self._publish(self._quote_payload(code))
