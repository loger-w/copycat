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
from copycat.server.bars import BarsResult
from copycat.server.ws import WsBroadcaster
from copycat.stkfut_map import load_map

logger = logging.getLogger(__name__)

_CLIENT_QUEUE_MAX = 1000
# 同一檔當日回補失敗幾次之後就不再入列(code review A2)。群組 batch 每 60s 一輪,
# 沒有這道冷卻的話一檔壞碼會對 TC4 發整天的必敗請求,還把單工 worker 排到滿。
_BACKFILL_MAX_FAILS = 3
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


def _spot_trial_now() -> bool:
    """現貨那把尺的「當下在試撮窗內」——`_flush_watchlist_loop` 的翻轉偵測用。

    per-instrument 判定走 `StockEngine._trial_now`(期貨空窗恆 False);這裡要的是
    「現貨窗有沒有跨過邊界」這**單一**事件,拿某一檔的 key 去算會在自選全空 /
    只剩期貨主圖時失去判準。窗顯式傳 `TRIAL_WINDOWS` 不吃預設值(同
    `parse_stock_realtime` 的 keyword-only 理由:傳錯的失效是靜默的)。
    """
    return is_trial_window(_now_taipei_time(), TRIAL_WINDOWS)


#: TradeStatus 轉態觀測的**固定 grep 前綴 + 格式**(D6/R10)。與 parse 層值域外 warning
#: 是同事件兩則(那邊管值域、這邊管轉態時序),蒐證對帳一律以本前綴為準。
_TRADE_STATUS_FMT = "trade-status-observe code=%s %s->%s t=%s trial_window=%s qty=%s"


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
    ) -> None:
        self._source = source
        self._trade_date = trade_date
        self._pending_date: str | None = None
        self._throttle = throttle_secs
        self._checkpoint_enabled = checkpoint
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
        self._backfill_failed: dict[str, int] = {}
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
        # 抵達順序不保證。0 = 還沒套過任何帶號的名單(取號自 1 起)。
        self._wl_seq_applied = 0
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
        # 自己有沒有對應的起點)。**日別語意**:`_rollover_stage2` 顯式清空。
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
        self._trial_on = _spot_trial_now()
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

    async def set_watchlist(self, codes: list[str], *, seq: int | None = None) -> None:
        """`seq` = 呼叫端(`WatchlistService`)在**它自己的鎖內**取的定序號(X-3)。

        `seq <= 已套用` = 舊名單後到 → **整段跳過**(不訂不退不廣播不通知 hub),
        照套的話訂閱池 / hub membership / 種子廣播會一起退回上一版,而畫面上只是
        「剛加的股票又不見了」,零錯誤訊號。

        誠實記帳:現況下取號(service 鎖內,同步)到本 method 進 `_pool_lock`
        (FIFO)之間**沒有 yield 點**(無競爭的 `asyncio.Lock.acquire` 不讓出),
        抵達順序 = 取號順序,這個防線今天走不到 —— `seq` 是 belt-and-braces。
        它防的是那條保證**靜默消失**的未來:任何人在該窗內插入 await(例:落檔改
        `to_thread`)後亂序就真的可能發生,而屆時不會有任何測試驅動 service→engine
        的 reorder 提醒你。

        `None`(boot 還原 / 既有 caller)= 不參與定序,照舊全套。
        """
        async with self._pool_lock:  # CR2
            if seq is not None:
                if seq <= self._wl_seq_applied:
                    logger.info(
                        "watchlist seq %d 已過期(已套用 %d),跳過", seq, self._wl_seq_applied
                    )
                    return
                self._wl_seq_applied = seq
            # added 以 refs 實況為準(非 _watchlist 名單):真訂失敗回滾後重送同名單要能重試
            added = [c for c in codes if "watchlist" not in self._refs.get(c, set())]
            removed = [c for c in self._watchlist if c not in codes]
            # **名單先指派再訂閱**(round4 項 4):每個 `await to_thread` 都讓出 loop,而 TC4
            # 在 SUB 回來後幾乎立刻推第一則 REALTIME。名單留到最後才指派的話,那一則會在
            # `code not in self._watchlist` 的窗內進 `_handle_quote` → meta 轉態補推被擋掉;
            # 盤後沒有後續 tick、flush 又只推 dirty,該檔就卡在 `-` 直到使用者重整。
            # 名單是「意圖」、訂閱是副作用;最終狀態與舊順序等價(舊碼也是不論成敗都指派)。
            self._watchlist = list(codes)
            for code in added:
                try:
                    await asyncio.to_thread(self._acquire, code, "watchlist")
                except ConnectionError:
                    logger.warning("watchlist subscribe %s failed", code)
            for code in removed:
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
                    # 窗是秒級(一次 SubHistory 的時間)且後果與 E-2 同構(那一檔在
                    # 群組輪詢裡被 dedup 擋到下一次日別清空為止)。完整解要 per-code
                    # epoch(退訂時 +1,job 自帶取件時的 epoch,套用前比對),那是新的
                    # 不變式不是註解能帶過的,記 next-time。
                    self._backfilled.discard(code)
                    self._backfill_failed.pop(code, None)
            # 新增的檔立刻給一則種子:不等第一筆成交(冷門股整天可能只有簿更新),
            # 盤後加股也要馬上看得到參考價。啟動期 `_clients` 為空 = no-op,
            # 開機路徑由 `stream()` 的 per-client 種子涵蓋。
            for code in added:
                self._publish(self._quote_payload(code))
            if self._signal_hub is not None:
                # 全量替換 hub 的 membership(新增排 CDP 基準、移除逐出狀態)
                self._signal_hub.on_watchlist(list(codes))

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
            if not is_futures_key(key):
                await self._acquire_stkfut(key)
            self._enqueue_backfill(key)

    def _trial_now(self, code: str) -> bool:
        """該 instrument 當下是否在試撮/緩撮窗內(D1)。

        **每次組 payload 當下現算**,不落 `StockDayState`:試撮期 TC4 不推成交 tick
        (2026-07-21 實測),tick 路徑萃取不到「進窗」事件 —— 掛在狀態機上的旗標
        永遠不會被翻起來,而畫面只是一直不標。現算也天然沒有 stale / 清除的路。

        窗對映走 `trial_windows_for`(唯一定義):期貨鍵空窗 → 恆 False,前端因此
        不必自己判 instrument 種類。
        """
        return is_trial_window(_now_taipei_time(), trial_windows_for(code))

    def snapshot(self, code: str) -> dict:
        state = self._states.get(code)
        snap = state.snapshot() if state is not None else StockDayState().snapshot()
        snap["code"] = code
        snap["no_data"] = code in self._no_data
        # 附加點在 engine 而非 `StockDayState.snapshot()`(同 `no_data` 慣例):
        # trial 是引擎時鐘推導的,不是日內狀態機資料。
        snap["trial"] = self._trial_now(code)
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

        不得重用 `/api/stock/state/{code}`:那條路會 `set_main`,群組檢視每分鐘 30 次
        會把主圖搶走 → 主圖分時線凍結。

        payload 走 `light_snapshot()` 的 minutes/meta 兩鍵(+ 兩個旗標,A1):`ticks`
        是數千筆,30 檔每 60s 各建一份全量 snapshot 再整份丟掉,既是頻寬炸彈也是
        白燒 CPU;而鍵名沿 `StockDayState` 的單一對映(直接丟 dataclass 會讓前端
        `meta.ref` undefined → hasRef=false → 紅綠面積靜默消失)。

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
        冷卻**只擋這條 60s 輪詢的路**,不下沉到 `_enqueue_backfill`:另外四個入列點
        (set_main / rollover / reconnect / 漲跌停值變)都是低頻且對應「使用者當下在
        看的那一檔」或「日別重來」,被冷卻擋掉會變成主圖整天補不回來。
        """
        out: dict[str, dict] = {}
        for code in codes:
            state = self._states.get(code)
            subscribed = code in self._refs
            light = state.light_snapshot() if state is not None else dict(_EMPTY_LIGHT)
            if (
                subscribed
                and code not in self._no_data
                and code not in self._backfilled
                and self._backfill_pending.get(code, 0) == 0
                and self._backfill_failed.get(code, 0) < _BACKFILL_MAX_FAILS
            ):
                # 先入列再讀旗標:順序反了的話第一次請求會回 backfilling=False,
                # 卡片顯示「無資料」而不是「回補中…」,而下一輪(60s 後)才會更正
                self._enqueue_backfill(code)
            out[code] = {
                "minutes": light["minutes"],
                "meta": light["meta"],
                "no_data": code in self._no_data or not subscribed,
                "backfilling": self._backfill_pending.get(code, 0) > 0,
            }
        return out

    async def daily_bars(self, code: str, n: int = 25) -> list[DailyBar]:
        """overlay 日 bar;TC4 離線降級空(具體處理 = best-effort null,design R3)。"""
        try:
            return await asyncio.to_thread(self._source.fetch_daily_bars, code, n)
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
        generation bump 作廢 in-flight 回補。"""
        self._generation += 1
        self._pending_date = new_date
        self._source.set_trade_date(new_date)
        # 進 `_tasks` 而非專用欄位:持有參照防 GC(asyncio 不強引用 task)之外,
        # 關機時一併被 close() 取消,且連跑兩次 rollover 不會互相覆寫掉參照
        self._tasks.append(asyncio.get_running_loop().create_task(self._resubscribe_all()))
        logger.info("rollover stage1 → %s (gen=%d)", new_date, self._generation)
        if self._signal_hub is not None:
            # 盤前預抓次日 CDP 基準進暫存區(stage2 只做 swap,開盤第一筆即可用)
            self._signal_hub.on_rollover_pending(new_date)

    async def _resubscribe_all(self) -> None:
        """全量重掛(UNSUB→SUB 冪等,新日窗);ZMQ REQ 全程 to_thread,不佔 event loop。"""
        async with self._pool_lock:
            codes = list(self._refs)

        def _do() -> list[str]:
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
        import datetime as _dt

        while True:
            await asyncio.sleep(60)
            now = _dt.datetime.now()
            today = f"{now:%Y-%m-%d}"
            if (
                now.weekday() < 5  # 候選交易日(週一~五;假日靠階段二天然不清空)
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
        self._publish({"type": "status", "tc4": "up", "backfilling": self._backfilling})
        # reconnect **不** bump generation(實碼事實)→ 記帳不會被 generation 作廢帶走,
        # 得顯式清。漏清的話斷線那段的缺口整天補不回來:主圖靠下一行自癒,主圖以外的
        # 成員全靠這次清空才有機會再被 `group_snapshot` 入列(R4)。
        # **只清 `_backfilled`**(A3):`_backfill_pending` 是在途計數,清掉之後那些
        # job 回來仍會各扣一次 → 旗標永久假、同一檔又被重複入列一次。斷線期間發出的
        # job 由 worker 自己走失敗路徑結清,不需要外力。
        self._backfilled.clear()
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

        三道守門各自對應一種會污染樣本的假事件:
        - **期貨鍵跳過**:空窗讓 `_trial_now` 恆 False → 任何轉態都誤落「窗外」分支,
          個股期整天噴假 WARNING。
        - **首見值只播種**:`None→x` 不是轉態,否則每交易日 255 檔各噴一則。
        - **同值不記**:每則 REALTIME 都帶 TradeStatus,不比對前值就等於逐則記錄。
        """
        if is_futures_key(code):
            return
        # 缺欄 / 空字串視同 "0"(parse 既有 `or "0"` 語意,觀測與判定同基準)
        status = str(quote.get("TradeStatus", "0") or "0")
        prev = self._trade_status.get(code)
        if prev is None:
            self._trade_status[code] = (status, False)
            return
        prev_status, episode = prev
        if status == prev_status:
            return
        in_window = self._trial_now(code)
        args = (
            code,
            prev_status,
            status,
            _now_taipei_time(),
            in_window,
            quote.get("TradeQuantity", ""),
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
        """入列回補 job 的**唯一**接點(五個產出點共用:set_main / rollover stage2 /
        reconnect / 漲跌停值變 / group_snapshot)。

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

    async def _backfill_worker(self) -> None:
        while True:
            code, generation = await self._backfill_jobs.get()
            # 取件早退**只比 generation**(design v3 R12):job 自帶 code,收件人是那一檔
            # 自己的 state 而不是「當下的主圖」。綁 `_main` 會讓群組成員的 job 全部被
            # 靜默丟棄(零錯誤訊號,卡片只是一直空著)。
            if generation != self._generation:
                self._backfill_settled(code)
                continue
            self._backfilling = code
            self._publish({"type": "status", "tc4": self.tc4_status, "backfilling": code})
            try:
                ticks = await asyncio.to_thread(self._source.backfill, code)
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
                # 兩條路都要補推:不推的話「回補中…」徽章永遠掛著而內部態早就清了(TQ-4)
                self._publish({"type": "status", "tc4": self.tc4_status, "backfilling": None})
                continue
            except Exception:
                # CR4:非連線類例外(壞電文 JSONDecodeError 等)不得殺死 worker —
                # 死掉 = 之後所有回補靜默失效、backfilling 永久卡住
                logger.exception("backfill %s unexpected failure(worker 續行)", code)
                self._backfilling = None
                self._backfill_settled(code)
                self._backfill_failed[code] = self._backfill_failed.get(code, 0) + 1
                self._publish({"type": "status", "tc4": self.tc4_status, "backfilling": None})
                continue
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
            self._publish({"type": "status", "tc4": self.tc4_status, "backfilling": None})

    # ---- 廣播 ----

    def _quote_payload(self, code: str) -> dict:
        """`watchlist_quote` 的**唯一** payload builder(round4 項 4)。

        四個產出點(連線種子 / set_watchlist 新增 / 轉態補推 / 1s flush)共用這一份,
        否則同一個訊息型別會長出多種形狀,而消費端只會在缺欄位那一刻靜默降級。

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
        }

    def stream(self) -> AsyncGenerator[dict, None]:
        # 連線先送一輪自選種子(round4 項 4)。側欄開頁 / 盤後全是 `-` 的根因是
        # 「quote 只有 tick 驅動的生產點」—— 新 client 連上時沒有任何歷史訊息可收,
        # 而不是節流太慢。修在這個接點,開頁與重連都天然自癒(與 ws_corr / ws_river
        # 「連線先送快照」的既成慣例一致)。種子走 `stream(seed=...)` 而非 `publish`
        # (後者會打到所有 client);30 檔對 queue maxsize 安全。
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
            trial_on = _spot_trial_now()
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
