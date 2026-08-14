"""指數引擎(index-board SC-4;design v4).

三檔:加權(TC4 IX0001 push + 1K 回補)、櫃買(MIS 5s poll)、台指期(TXO runtime
現貨轉供 — txf_getter 只回毫點價,時間由本引擎於價變動時自記)。
分鐘鍵統一 1K 終點標記(floor+1;域 0901–1330,1331–1335 clamp,其餘丟棄)。
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import time as _time
from typing import AsyncGenerator, Callable, Protocol

from copycat.live.stock_source import (
    WINDOW_VARIANT_END_BASE,
    WINDOW_VARIANT_END_CAP,
    Bar,
)
from copycat.server.mis import OtcSnap, fetch_otc_snapshot
from copycat.server.ws import WsBroadcaster

logger = logging.getLogger(__name__)

_CLIENT_QUEUE_MAX = 32
_SYMBOL = "IX0001"
#: 盤中台指現價連續為 None 多久後開始 warn(SC-8 反向判準:連續 3 分鐘 = 未通過)
_SPOT_SILENCE_SECS = 180.0
#: 台指期交易時段(台北):日盤 08:45–13:45、夜盤 15:00–次日 05:00。
#: **不可沿用 watchdog 的 09:00–13:25** —— CLAUDE.md §8 記載的 futures_engine 整段
#: 零推播實測案例(2026-07-29 17:33 起跑、到 00:50 為止 TXF/MXF/TMF 全 p=null)發生在
#: **夜盤**,完全落在那個窗之外;用 watchdog 窗等於這道安全網對它要偵測的那個 bug
#: 時間上零覆蓋(review P1-2)。
_FUT_DAY = (_dt.time(8, 45), _dt.time(13, 45))
_FUT_NIGHT_OPEN = _dt.time(15, 0)
_FUT_NIGHT_CLOSE = _dt.time(5, 0)


def in_futures_session(now: _dt.time | None = None) -> bool:
    """台指期交易時段(跨午夜的夜盤以「或」拆兩段判)。"""
    t = now if now is not None else _dt.datetime.now().time()
    if _FUT_DAY[0] <= t <= _FUT_DAY[1]:
        return True
    return t >= _FUT_NIGHT_OPEN or t <= _FUT_NIGHT_CLOSE


# watchdog 判定窗:台北 09:00–13:25(13:25–13:30 試撮窗凍結計時 — design F4)
_WATCH_START = _dt.time(9, 0)
_WATCH_END = _dt.time(13, 25)
#: 分時自癒門檻:heal 窗內 minutes 最後一鍵落後牆鐘超過此分鐘數 → 重掛+重抓。
#: 開盤頭幾分鐘 minutes 空是正常(域 0901 起),空集合以窗起點 09:00 起算即天然豁免。
_LAG_HEAL_MIN = 3
#: heal 尾窗終點:watchdog 窗 13:25 凍結的理由(試撮不推成交)對「重抓 1K」不成立,
#: 1K 域到 1330 —— 尾段 13:25–13:30 正是要補的那截,收盤後留 10 分鐘做最後回補
#: (review T-3)。lag 的期望覆蓋終點同步封頂 13:30。
_HEAL_TAIL_END = _dt.time(13, 40)
#: 期望覆蓋終點(分鐘數):1330 = 13*60+30
_HEAL_TARGET_MIN = 13 * 60 + 30
#: 無進展退避封頂:1K 持續回空(假日 / 該日資料不可得)時 heal 間隔倍增至此為止,
#: 不以固定 60s 整窗空轉(UNSUB→SUB churn + log 噪音;review T-5)。
_HEAL_BACKOFF_CAP = 900.0


class IndexSource(Protocol):
    """指數行情來源(StockQuoteSource 相容子集);測試注入 fake。"""

    def subscribe_symbol(self, code: str) -> None: ...

    def unsubscribe_symbol(self, code: str) -> None: ...

    def fetch_day_minutes(self, code: str, *, window_variant: int = 0) -> dict[str, int]: ...

    def set_on_message(self, cb: Callable[[dict], None]) -> None: ...

    def set_trade_date(self, trade_date: str) -> None: ...

    def close(self) -> None: ...


def in_watch_window_now(now: _dt.time | None = None) -> bool:
    """watchdog 判定窗;end-exclusive(13:25:00 起即試撮窗凍結 — review F4 界義)。"""
    t = now if now is not None else _dt.datetime.now().time()
    return _WATCH_START <= t < _WATCH_END


def now_time() -> _dt.time:
    """當下牆鐘時刻(換日 08:30 門檻用)。建構子注入點 — 測試傳固定值。"""
    return _dt.datetime.now().time()


def minute_key(hhmmss: str, *, utc: bool) -> str | None:
    """時刻 → 分鐘鍵(1K 終點標記 = floor+1;IR3/IR4/F5)。utc=True 先 +8。"""
    raw = str(hhmmss).zfill(6)
    try:
        hh, mm = int(raw[:2]), int(raw[2:4])
    except ValueError:
        return None
    if utc:
        hh = (hh + 8) % 24
    mm += 1
    if mm == 60:
        mm = 0
        hh = (hh + 1) % 24  # 防禦:域檢查會擋 24 時,但鍵格式不得出現 "24xx"(review A2)
    key = f"{hh:02d}{mm:02d}"
    if "1330" < key <= "1335":
        key = "1330"
    if not ("0901" <= key <= "1330"):
        return None
    return key


def _millipt(raw: str) -> int | None:
    try:
        return round(float(raw) * 1000)
    except ValueError:
        return None


class _Series:
    __slots__ = ("p", "ref", "high", "low", "stale", "minutes", "last_minute", "ohlc")

    def __init__(self) -> None:
        self.p: int | None = None
        self.ref: int | None = None
        self.high: int | None = None
        self.low: int | None = None
        self.stale = False
        self.minutes: dict[str, int] = {}
        self.last_minute: tuple[str, int] | None = None
        #: 分鐘鍵 → [o, h, l, c] 毫點(櫃買本機合成用;index-board N-4)。
        #: 只有櫃買會填 —— 加權的分 K 有 TC4 1K 這個真來源,不必用 push 湊。
        self.ohlc: dict[str, list[int]] = {}

    def scalar(self) -> dict:
        return {
            "p": self.p,
            "ref": self.ref,
            "high": self.high,
            "low": self.low,
            "stale": self.stale,
            "last_minute": list(self.last_minute) if self.last_minute else None,
        }


class IndexEngine:
    def __init__(
        self,
        source: IndexSource,
        *,
        txf_getter: Callable[[], int | None],
        mis_fetch: Callable[[], OtcSnap | None] = fetch_otc_snapshot,
        trade_date: str,
        rollover: bool = True,
        today_fn: Callable[[], _dt.date] = _dt.date.today,
        in_watch_window: Callable[[], bool] = in_watch_window_now,
        in_futures_session: Callable[[], bool] = in_futures_session,
        now_fn: Callable[[], _dt.time] = now_time,
        poll_secs: float = 5.0,
        throttle_secs: float = 1.0,
        stale_secs: float = 30.0,
        retry_secs: float = 5.0,
    ) -> None:
        self._source = source
        self._txf_getter = txf_getter
        self._mis_fetch = mis_fetch
        self._trade_date = trade_date
        self._rollover_enabled = rollover
        self._today_fn = today_fn
        self._in_watch_window = in_watch_window
        self._in_futures_session = in_futures_session
        self._now_fn = now_fn
        self._poll = poll_secs
        self._throttle = throttle_secs
        self._stale_secs = stale_secs
        self._retry_secs = retry_secs
        self._rollover_check_secs = 60.0
        # 分時自癒節流:lag 觸發的 retry 排程間隔下限(retry 本身 single-flight);
        # _heal_interval = 無進展退避的當前間隔(None = 用基準值;恢復健康即歸零)
        self._heal_secs = 60.0
        self._last_heal = float("-inf")
        self._heal_interval: float | None = None
        # heal 的 1K 窗口 variant:無進展一次 +1(= 換窗口字串 = TC4 端全新 history
        # 訂閱)。重用同一個訂閱逃不出 stub 態,重送 SubHistory 也不行(2026-08-14 實證)。
        # 唯一的歸零點是 `_swap_day`(新交易日窗口字串天然全新);lag 恢復**不**歸零。
        self._heal_variant = 0
        # retry 回補成功 → 下一則廣播帶 minutes 全量一次(送達已連線前端;平常
        # scalar-only 的頻寬慣例不變,前端 toSeries 對 w.minutes 是整份替換)
        self._push_minutes_once = False

        # 換日 pending(IR2):偵測新日後 realtime 分鐘先進 pending,swap 才入 minutes
        self._pending_date: str | None = None
        self._pending_minutes: dict[str, int] = {}

        self._twse = _Series()
        self._otc = _Series()
        self._txf_p: int | None = None
        self._txf_time: str | None = None

        self._loop: asyncio.AbstractEventLoop | None = None
        self._tasks: list[asyncio.Task[None]] = []
        self._retry_task: asyncio.Task[None] | None = None
        self._ws = WsBroadcaster(maxsize=_CLIENT_QUEUE_MAX)
        self._dirty = False
        self._last_push = _time.monotonic()
        self._spot_silent_since: float | None = None
        self._spot_warned_at = 0.0

    # ---- 生命週期 ----

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._source.set_trade_date(self._trade_date)  # IR5:日窗同步(含 backfill 模式)
        self._source.set_on_message(self._on_quote_threadsafe)
        if hasattr(self._source, "on_reconnect"):
            self._source.on_reconnect = self._on_reconnect_threadsafe  # type: ignore[attr-defined]
        try:
            await asyncio.to_thread(self._subscribe_and_backfill)
        except ConnectionError:
            logger.warning("index start:TC4 不可用,標 stale 並背景重試(design R5)")
            self._twse.stale = True
            self._schedule_retry()
        self._tasks.append(asyncio.create_task(self._mis_loop()))
        self._tasks.append(asyncio.create_task(self._broadcast_loop()))
        if self._rollover_enabled:
            self._tasks.append(asyncio.create_task(self._rollover_loop()))

    async def close(self) -> None:
        # 先斷 threadsafe callback 入口:close 期間 TC4 推播不得再 call_soon_threadsafe
        # 到即將關閉的 loop(review A1)
        self._loop = None
        tasks = list(self._tasks)
        if self._retry_task is not None:
            tasks.append(self._retry_task)
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        await asyncio.to_thread(self._source.close)

    def _subscribe_and_backfill(self, variant: int = 0) -> bool:
        """訂閱 + 回補當日 1K;回傳「本次是否帶來**新分鐘鍵**」。

        判準是鍵集合差而非值(review L1-P1-2):毒化訂閱回的凍結 stub 只有一根,
        但它的 Close 隨現價漂 —— 以值比對會把同一根 stub 每發都算成進展,自癒又回到
        「宣告治好、重用死窗口」的原狀。回傳 False 只代表「零新鍵」,不代表 fetch 失敗
        (失敗一律是 ConnectionError)。
        """
        self._source.subscribe_symbol(_SYMBOL)
        minutes = self._source.fetch_day_minutes(_SYMBOL, window_variant=variant)
        new_keys = minutes.keys() - self._twse.minutes.keys()
        self._twse.minutes.update(minutes)
        return bool(new_keys)

    # ---- 重試(R5/IR8:single-flight)----

    def _schedule_retry(self, *, clear_stale: bool = True, variant: int = 0) -> None:
        if self._retry_task is not None and not self._retry_task.done():
            self._retry_task.cancel()
        self._retry_task = asyncio.create_task(self._retry_loop(clear_stale, variant))

    async def _retry_loop(self, clear_stale: bool, variant: int = 0) -> None:
        backoff = self._retry_secs
        while True:
            await asyncio.sleep(backoff)
            try:
                progressed = await asyncio.to_thread(self._subscribe_and_backfill, variant)
            except ConnectionError:
                backoff = min(backoff * 2, 60.0)
                continue
            except Exception:
                logger.exception("index retry 非預期失敗(續試)")
                backoff = min(backoff * 2, 60.0)
                continue
            if not clear_stale and not progressed:
                # heal 型的「成功」判準是**產出面的差量**:fetch 沒丟例外不等於 minutes
                # 前進(TC4 對毒化訂閱回的是凍結 stub),而「有沒有追上牆鐘」也不是判準
                # ——「回補到 t-10 分」是真進展,拿它當失敗會把真資料扣住不廣播、還把
                # 窗口階梯燒在健康路徑上(review L1-P1-1/L1-P1-2)。零新鍵才是無進展:
                # 不設 _push_minutes_once / _dirty,下一發由既有 heal 退避帶新 variant 出手。
                logger.warning(
                    "index 分時自癒無進展(window_variant=%d):零新分鐘鍵,下一發換窗口",
                    variant,
                )
                self._heal_variant += 1
                if WINDOW_VARIANT_END_BASE + self._heal_variant >= WINDOW_VARIANT_END_CAP:
                    # 與上一行分開的獨立固定字串:封頂後每一發都是同一個窗口字串、
                    # 再無逃逸維度,而「無進展」那行字面上與第 1 次一模一樣 ——
                    # 值班的人看不出該不該換手段(換 session / 重啟 TC4)(review L1-P2-2)。
                    logger.warning(
                        "index 分時自癒:窗口階梯已達封頂(window_variant=%d,end hour %d)",
                        self._heal_variant,
                        WINDOW_VARIANT_END_CAP,
                    )
                return
            if clear_stale:
                # 連線類 retry(start 失敗 / reconnect / rollover 失敗)成功 = 樂觀清
                # stale(推播即將恢復);分時自癒的 retry 不清 —— stale 是推播死活的
                # 訊號(watchdog 職權),回補成功不代表推播活著。
                self._twse.stale = False
            if self._pending_date is None:
                # pending 期間 retry 抓的是新日窗、merge 進舊日 dict(既有 latent),
                # 廣播 trade_date 仍是舊日 → 前端不走換日分支、整份替換成混日線;
                # 不帶出去,等 swap 後由換日 refetch 對齊(review T-1)。
                self._push_minutes_once = True
            self._dirty = True
            return

    # ---- TC4 推播 ----

    def _on_quote_threadsafe(self, quote: dict) -> None:
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._handle_quote, quote)

    def _on_reconnect_threadsafe(self) -> None:
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._schedule_retry)

    def _handle_quote(self, quote: dict) -> None:
        if str(quote.get("Security", "")) != _SYMBOL:
            return
        p = _millipt(str(quote.get("TradingPrice", "")))
        if p is None:
            return
        s = self._twse
        s.p = p
        s.ref = _millipt(str(quote.get("ReferencePrice", ""))) or s.ref
        s.high = _millipt(str(quote.get("HighPrice", ""))) or s.high
        s.low = _millipt(str(quote.get("LowPrice", ""))) or s.low
        key = minute_key(str(quote.get("FilledTime", "")), utc=True)
        if key is not None:
            if self._pending_date is not None:
                self._pending_minutes[key] = p
                self._maybe_swap_day()
            else:
                s.minutes[key] = p
                s.last_minute = (key, p)
        if s.stale:
            s.stale = False
        self._last_push = _time.monotonic()
        self._dirty = True

    # ---- MIS(櫃買)----

    async def _mis_loop(self) -> None:
        while True:
            try:
                snap = await asyncio.to_thread(self._mis_fetch)
                if snap is not None:
                    self._apply_otc(snap)
            except Exception:
                # 任務存活邊界(design R8):fetch 層已具體列舉,這裡守 loop 不死
                logger.exception("MIS loop 非預期失敗(續行)")
            await asyncio.sleep(self._poll)

    def _apply_otc(self, snap: OtcSnap) -> None:
        s = self._otc
        s.p = snap["p"]
        s.ref = snap["ref"]
        s.high = snap["high"]
        s.low = snap["low"]
        key = minute_key(snap["time"], utc=False)
        if key is not None and self._pending_date is None:
            s.minutes[key] = snap["p"]
            s.last_minute = (key, snap["p"])
            # 分鐘 OHLC:同一分鐘內約 12 筆 5 秒快照 → o 首筆 / h 最大 / l 最小 / c 末筆。
            # 這是**取樣合成**不是交易所發布的 bar,由 meta 的 source 標明(SC-6)。
            cell = s.ohlc.get(key)
            if cell is None:
                s.ohlc[key] = [snap["p"], snap["p"], snap["p"], snap["p"]]
            else:
                cell[1] = max(cell[1], snap["p"])
                cell[2] = min(cell[2], snap["p"])
                cell[3] = snap["p"]
        self._dirty = True

    def otc_bars(self) -> tuple[list[Bar], str | None]:
        """櫃買當日分 bar + 起始時刻(`HH:MM`;無資料 → `None`)。

        `t` 必須是 `"YYYY-MM-DD HH:MM"` —— 前端 `candle.ts:splitStamp` 靠**有無空格**
        判斷日 K / 分 K,格式不對會讓 30/60/90 分完全不聚合,而畫面看起來仍是正常
        K 線圖(review P1-9)。`v` 固定 0:MIS 快照沒有量,由 meta 的 `volume: false`
        標明「無量資料」而不是畫一排 0 柱。
        """
        keys = sorted(self._otc.ohlc)
        bars: list[Bar] = [
            {
                "t": f"{self._trade_date} {k[:2]}:{k[2:]}",
                "o": self._otc.ohlc[k][0],
                "h": self._otc.ohlc[k][1],
                "l": self._otc.ohlc[k][2],
                "c": self._otc.ohlc[k][3],
                "v": 0,
            }
            for k in keys
        ]
        since = f"{keys[0][:2]}:{keys[0][2:]}" if keys else None
        return bars, since

    async def bars_range(self, tf: str, start: str, end: str) -> tuple[list[Bar], str]:
        """加權 K 線歷史 —— **必須從本引擎的 session 問**(review P0-1)。

        `IX0001` 的 REALTIME 訂閱與當日 1K 回補都在這條 session 上;TC4 同 symbol 跨
        session 只推一邊(CLAUDE.md §8),從個股 session 問同一檔有把推播搶走的風險,
        而失效樣態是「訂閱成功但零推播」—— 右上角加權、大盤分時線、watchdog stale
        會同時安靜失效,且大盤是預設著陸頁 = 每次開站必觸發。

        TC4 不可用 → 回 `([], "unavailable")` + 固定可 grep 的 log(不 raise:
        K 線是可降級的,同 `bars_range` 的 best-effort 慣例)。
        """
        fetch = getattr(self._source, "fetch_bars_range_tagged", None)
        if fetch is None:
            logger.warning("market: index history proxy miss(source 無 fetch_bars_range_tagged)")
            return [], "unavailable"
        try:
            # source 另回第三元素 status(個股 K 線的三態);大盤的空態表述走自己的
            # source tag 體系,對外簽名不變(bars-tristate-status 白名單 9)
            bars, tag, _status = await asyncio.to_thread(fetch, _SYMBOL, tf, start, end)
            return bars, tag
        except ConnectionError as e:
            logger.warning("market: index history proxy miss(%s)", e)
            return [], "unavailable"

    # ---- 換日(R1/F6/IR2:兩段式 + pending buffer)----

    async def _rollover_loop(self) -> None:
        while True:
            await asyncio.sleep(self._rollover_check_secs)
            try:
                today = self._today_fn()
                new_date = f"{today:%Y-%m-%d}"
                now = self._now_fn()
                if new_date <= self._trade_date or now < _dt.time(8, 30):
                    continue
                if self._pending_date != new_date:
                    self._pending_date = new_date
                    self._pending_minutes = {}
                    self._source.set_trade_date(new_date)
                    try:
                        await asyncio.to_thread(
                            self._source.subscribe_symbol, _SYMBOL
                        )  # 重掛新日窗
                    except ConnectionError:
                        self._schedule_retry()  # IR8:失敗收斂 single-flight 重試
                        continue
                pending_date = self._pending_date
                try:
                    minutes = await asyncio.to_thread(self._source.fetch_day_minutes, _SYMBOL)
                except ConnectionError:
                    self._schedule_retry()
                    continue
                if pending_date != self._pending_date:
                    continue  # F2:發起時日別已變,丟棄
                if minutes or self._pending_minutes:
                    self._swap_day(backfill=minutes)
            except Exception:
                logger.exception("rollover loop 非預期失敗(續行)")

    def _maybe_swap_day(self) -> None:
        if self._pending_minutes:
            self._swap_day(backfill={})

    def _swap_day(self, *, backfill: dict[str, int]) -> None:
        assert self._pending_date is not None
        self._trade_date = self._pending_date
        self._pending_date = None
        self._twse.minutes = {**backfill, **self._pending_minutes}
        self._pending_minutes = {}
        self._twse.last_minute = None
        self._twse.high = None
        self._twse.low = None
        self._otc.minutes = {}
        self._otc.last_minute = None
        self._otc.ohlc = {}  # 換日必清:否則昨日的合成分 bar 會混進新交易日(review P1-9)
        # 新交易日的窗口字串天然全新(start/end 都帶日期)→ 昨日爬過的階梯不必沿用,
        # 這是 variant 唯一的歸零點(review L1-P1-3)。
        self._heal_variant = 0
        self._dirty = True
        logger.info("index rollover → %s(回補 %d 分鐘)", self._trade_date, len(backfill))

    # ---- 廣播(週期型;watchdog/txf 每拍檢查 — IR7)----

    async def _broadcast_loop(self) -> None:
        while True:
            await asyncio.sleep(self._throttle)
            # watchdog(R4/F4)
            if (
                not self._twse.stale
                and self._in_watch_window()
                and _time.monotonic() - self._last_push > self._stale_secs
            ):
                self._twse.stale = True
                self._dirty = True
            # 分時自癒(fix/index-chart-empty-minutes):開機 1K 回補 timeout 被靜默降級
            # 成空(_collect_history 不 raise → start 不排 retry)+ 當日推播整段靜默時,
            # minutes 沒有任何回復路徑,而 TC4 端 1K 資料整天可取(2026-08-13 事故)。
            # 偵測產出面(minutes 覆蓋度)而非輸入面:對「回補 timeout」「推播死」
            # 「推播鍵不可用」三種上游失效同構。固定字串供 grep:index 分時自癒。
            # heal 窗 = watchdog 窗 ∪ 收盤尾窗(13:25–13:40;review T-3)。
            if self._in_watch_window() or _WATCH_END <= self._now_fn() < _HEAL_TAIL_END:
                if not self._minutes_lag_exceeded():
                    # 覆蓋度跟上 → 退避歸零。**variant 不歸零**(review L1-P1-3):
                    # 0 號窗口一旦毒化就一直是毒的,恢復時打回 0 等於推播死的日子每兩發
                    # 浪費一發在已知死窗上;天然全新的窗口字串只有換交易日才有,
                    # 所以歸零點在 `_swap_day`。
                    self._heal_interval = None
                elif (
                    self._pending_date is None
                    and (self._retry_task is None or self._retry_task.done())
                    and _time.monotonic() - self._last_heal
                    >= (self._heal_interval or self._heal_secs)
                ):
                    self._last_heal = _time.monotonic()
                    # 連續無進展(下一拍 lag 仍在才會再進來)→ 間隔倍增(review T-5)
                    self._heal_interval = min(
                        (self._heal_interval or self._heal_secs) * 2, _HEAL_BACKOFF_CAP
                    )
                    logger.warning(
                        "index 分時自癒:minutes 落後 >%d 分,重掛訂閱+重抓 1K(window_variant=%d)",
                        _LAG_HEAL_MIN,
                        self._heal_variant,
                    )
                    self._schedule_retry(clear_stale=False, variant=self._heal_variant)
            # txf(IR1:價變動自記 wall-clock)
            p = self._txf_getter()
            if p is not None and p != self._txf_p:
                self._txf_p = p
                self._txf_time = _time.strftime("%H:%M:%S")
                self._dirty = True
            self._check_spot_silence(p)
            if not self._dirty:
                continue
            self._dirty = False
            self._publish(self._payload())
            self._twse.last_minute = None
            self._otc.last_minute = None

    def _minutes_lag_exceeded(self) -> bool:
        """加權 minutes 最後一鍵是否落後牆鐘超過 `_LAG_HEAL_MIN` 分(僅 heal 窗內呼叫)。

        牆鐘封頂 `_HEAL_TARGET_MIN`(13:30):收盤後(尾窗 13:30–13:40)只要 minutes
        已覆蓋到 1330 就是完整,不得再觸發(review T-3 的停止條件)。"""
        now = self._now_fn()
        now_min = min(now.hour * 60 + now.minute, _HEAL_TARGET_MIN)
        m = self._twse.minutes
        if m:
            last = max(m)
            last_min = int(last[:2]) * 60 + int(last[2:4])
        else:
            last_min = 9 * 60  # 空 minutes 以窗起點 09:00 起算(開盤頭幾分鐘的空是正常)
        return now_min - last_min > _LAG_HEAL_MIN

    def _check_spot_silence(self, p: int | None) -> None:
        """盤中台指現價長時間為 None → 節流 warning(index-board review P1-1)。

        現價源自 2026-07-30 起收斂為 `TC.F.TWF.TXF.*`(修掉「任何期貨都當台指」的亂跳)。
        判定窗用**台指期交易時段**(日盤 + 夜盤),不是 watchdog 的 09:00–13:25 ——
        已實證的零推播案例發生在夜盤(review P1-2)。
        代價是多了一個**安靜**的新失效態:若 TXF 推播被 futures session 搶走
        (同 symbol 跨 session 只推一邊)或 futures engine 整段零推播(CLAUDE.md §8 的
        間歇性症狀),`spot` 會恆 `None` —— 右上角台指與 TXO 綜合損益的現貨點位一起
        空白,比亂跳更難察覺。固定字串供 grep:`txo spot 無 TXF 推播`。
        """
        if p is not None:
            self._spot_silent_since = None
            return
        if not self._in_futures_session():
            self._spot_silent_since = None  # 非交易時段的 None 是正常,不累積計時
            return
        now = _time.monotonic()
        if self._spot_silent_since is None:
            self._spot_silent_since = now
            return
        elapsed = now - self._spot_silent_since
        if elapsed >= _SPOT_SILENCE_SECS and now - self._spot_warned_at >= _SPOT_SILENCE_SECS:
            self._spot_warned_at = now
            logger.warning("txo spot 無 TXF 推播 %ds(右上角台指與 TXO 現貨損益皆空)", int(elapsed))

    def _payload(self) -> dict:
        twse = self._twse.scalar()
        if self._push_minutes_once:
            self._push_minutes_once = False
            twse["minutes"] = dict(self._twse.minutes)
        return {
            "type": "index",
            "trade_date": self._trade_date,
            "twse": twse,
            "otc": self._otc.scalar(),
            "txf": self._txf(),
        }

    def _txf(self) -> dict | None:
        if self._txf_p is None:
            return None
        return {"p": self._txf_p, "time": self._txf_time}

    def state(self) -> dict:
        return {
            "trade_date": self._trade_date,
            "twse": {**self._twse.scalar(), "minutes": dict(self._twse.minutes)},
            "otc": {**self._otc.scalar(), "minutes": dict(self._otc.minutes)},
            "txf": self._txf(),
        }

    # ---- WS 廣播(沿 stock_engine per-client 有界 queue)----

    def stream(self) -> AsyncGenerator[dict, None]:
        return self._ws.stream()

    def _publish(self, msg: dict) -> None:
        self._ws.publish(msg)
