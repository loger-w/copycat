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

from copycat.live.stock_source import Bar
from copycat.server.mis import OtcSnap, fetch_otc_snapshot

logger = logging.getLogger(__name__)

_CLIENT_QUEUE_MAX = 32
_SYMBOL = "IX0001"
#: 盤中台指現價連續為 None 多久後開始 warn(SC-8 反向判準:連續 3 分鐘 = 未通過)
_SPOT_SILENCE_SECS = 180.0

# watchdog 判定窗:台北 09:00–13:25(13:25–13:30 試撮窗凍結計時 — design F4)
_WATCH_START = _dt.time(9, 0)
_WATCH_END = _dt.time(13, 25)


class IndexSource(Protocol):
    """指數行情來源(StockQuoteSource 相容子集);測試注入 fake。"""

    def subscribe_symbol(self, code: str) -> None: ...

    def unsubscribe_symbol(self, code: str) -> None: ...

    def fetch_day_minutes(self, code: str) -> dict[str, int]: ...

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
        self._now_fn = now_fn
        self._poll = poll_secs
        self._throttle = throttle_secs
        self._stale_secs = stale_secs
        self._retry_secs = retry_secs
        self._rollover_check_secs = 60.0

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
        self._clients: set[asyncio.Queue[dict]] = set()
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

    def _subscribe_and_backfill(self) -> None:
        self._source.subscribe_symbol(_SYMBOL)
        minutes = self._source.fetch_day_minutes(_SYMBOL)
        self._twse.minutes.update(minutes)

    # ---- 重試(R5/IR8:single-flight)----

    def _schedule_retry(self) -> None:
        if self._retry_task is not None and not self._retry_task.done():
            self._retry_task.cancel()
        self._retry_task = asyncio.create_task(self._retry_loop())

    async def _retry_loop(self) -> None:
        backoff = self._retry_secs
        while True:
            await asyncio.sleep(backoff)
            try:
                await asyncio.to_thread(self._subscribe_and_backfill)
            except ConnectionError:
                backoff = min(backoff * 2, 60.0)
                continue
            except Exception:
                logger.exception("index retry 非預期失敗(續試)")
                backoff = min(backoff * 2, 60.0)
                continue
            self._twse.stale = False
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
            return await asyncio.to_thread(fetch, _SYMBOL, tf, start, end)
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

    def _check_spot_silence(self, p: int | None) -> None:
        """盤中台指現價長時間為 None → 節流 warning(index-board review P1-1)。

        現價源自 2026-07-30 起收斂為 `TC.F.TWF.TXF.*`(修掉「任何期貨都當台指」的亂跳)。
        代價是多了一個**安靜**的新失效態:若 TXF 推播被 futures session 搶走
        (同 symbol 跨 session 只推一邊)或 futures engine 整段零推播(CLAUDE.md §8 的
        間歇性症狀),`spot` 會恆 `None` —— 右上角台指與 TXO 綜合損益的現貨點位一起
        空白,比亂跳更難察覺。固定字串供 grep:`txo spot 無 TXF 推播`。
        """
        if p is not None:
            self._spot_silent_since = None
            return
        if not self._in_watch_window():
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
        return {
            "type": "index",
            "trade_date": self._trade_date,
            "twse": self._twse.scalar(),
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
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=_CLIENT_QUEUE_MAX)
        self._clients.add(queue)

        async def _gen() -> AsyncGenerator[dict, None]:
            try:
                while True:
                    yield await queue.get()
            finally:
                self._clients.discard(queue)

        return _gen()

    def _publish(self, msg: dict) -> None:
        for queue in self._clients:
            try:
                queue.put_nowait(msg)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(msg)
                except asyncio.QueueFull:
                    pass
