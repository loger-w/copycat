"""StockEngine:個股訂閱池 + 當日狀態機編排 + WS 廣播(design v4 §2.4)。

- refcount 訂閱池:owner ∈ {"watchlist", "main", "stkfut:<code>"};0→1 真訂、
  last-out 真退、真訂失敗回滾 bookkeeping 並 raise(treading-king WSPool 模型)。
- backfill 單工 worker queue(engine 持有;source 只提供同步 backfill,r2-1 定案),
  job 帶 (code, day_generation),套用 guard = 仍為 main ∧ generation 一致。
- 兩段式 rollover:階段一(換日窗 + 重掛,不清狀態)→ 階段二(首筆新日 tick 才
  reset + 重回補;假日無新日推播天然不清空)。
- 廣播:per-client 有界 queue,滿丟最舊;側欄 watchlist_quote 1s 節流合併。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator, Callable, Protocol

from copycat.live.stock_models import StockTick, parse_stock_realtime
from copycat.live.stock_source import Bar, DailyBar
from copycat.live.stock_state import StockDayState
from copycat.stkfut_map import load_map

logger = logging.getLogger(__name__)

_CLIENT_QUEUE_MAX = 1000


class StockSource(Protocol):
    """個股行情來源抽象;TC4 實作在 copycat.live.stock_source,測試注入 fake。"""

    def subscribe_symbol(self, code: str) -> None: ...

    def unsubscribe_symbol(self, code: str) -> None: ...

    def backfill(self, code: str) -> list[StockTick]: ...

    def fetch_daily_bars(self, code: str, n: int = 25) -> list[DailyBar]: ...

    def fetch_bars_range(
        self, code: str, tf: str, start_date: str, end_date: str
    ) -> list[Bar]: ...

    def set_on_message(self, cb: Callable[[dict], None]) -> None: ...

    def set_on_no_data(self, cb: Callable[[str], None]) -> None: ...

    def set_trade_date(self, trade_date: str) -> None: ...

    def close(self) -> None: ...


class StockEngine:
    def __init__(
        self,
        source: StockSource,
        *,
        trade_date: str,
        throttle_secs: float = 1.0,
        checkpoint: bool = True,
        stkfut_map: dict[str, dict] | None = None,
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
        self._no_data: set[str] = set()
        self._watchlist: list[str] = []
        self._main: str | None = None
        self._generation = 1
        self._backfill_jobs: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
        self._backfilling: str | None = None
        self._clients: set[asyncio.Queue[dict]] = set()
        self._dirty_watchlist: set[str] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._tasks: list[asyncio.Task[None]] = []
        # 訂閱池變更(set_watchlist/set_main/重掛)全程序列化:_refs/_main/_watchlist
        # 被 to_thread 與 loop 並發讀寫,check-then-act 交錯會退訂主圖/洩漏 owner(CR2)
        self._pool_lock = asyncio.Lock()
        self._resub_task: asyncio.Task[None] | None = None
        self.tc4_status = "up"

    # ---- 生命週期 ----

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._source.set_trade_date(self._trade_date)  # 休市日回補模式與 source 日窗同步
        self._source.set_on_message(self._on_raw_threadsafe)
        self._source.set_on_no_data(self._on_no_data_threadsafe)
        if hasattr(self._source, "on_reconnect"):
            self._source.on_reconnect = self._on_reconnect_threadsafe  # type: ignore[attr-defined]
        self._tasks.append(asyncio.create_task(self._backfill_worker()))
        self._tasks.append(asyncio.create_task(self._flush_watchlist_loop()))
        if self._checkpoint_enabled:
            self._tasks.append(asyncio.create_task(self._checkpoint_loop()))

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        await asyncio.to_thread(self._source.close)

    # ---- refcount 訂閱池 ----

    def _acquire(self, code: str, owner: str) -> None:
        owners = self._refs.setdefault(code, set())
        if owner in owners:
            return
        if not owners:
            try:
                self._source.subscribe_symbol(code)
            except ConnectionError:
                # 真訂失敗回滾 bookkeeping(design §2.4):不留空 owner set
                if not owners:
                    self._refs.pop(code, None)
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

    async def set_watchlist(self, codes: list[str]) -> None:
        async with self._pool_lock:  # CR2
            # added 以 refs 實況為準(非 _watchlist 名單):真訂失敗回滾後重送同名單要能重試
            added = [c for c in codes if "watchlist" not in self._refs.get(c, set())]
            removed = [c for c in self._watchlist if c not in codes]
            for code in added:
                try:
                    await asyncio.to_thread(self._acquire, code, "watchlist")
                except ConnectionError:
                    logger.warning("watchlist subscribe %s failed", code)
            for code in removed:
                await asyncio.to_thread(self._release, code, "watchlist")
                self._no_data.discard(code)
            self._watchlist = list(codes)

    async def set_main(self, code: str) -> None:
        async with self._pool_lock:  # CR2
            old = self._main
            if old == code:
                return
            await asyncio.to_thread(self._acquire, code, "main")
            self._main = code
            if old is not None:
                await asyncio.to_thread(self._release, old, "main")
                await asyncio.to_thread(self._release_stkfut, old)  # CR3:UNSUB 不佔 loop
            await self._acquire_stkfut(code)
            self._backfill_jobs.put_nowait((code, self._generation))

    def snapshot(self, code: str) -> dict:
        state = self._states.get(code)
        snap = state.snapshot() if state is not None else StockDayState().snapshot()
        snap["code"] = code
        snap["no_data"] = code in self._no_data
        snap["tc4"] = self.tc4_status
        snap["backfilling"] = self._backfilling
        stkfut = self._map.get(code)
        snap["stkfut_prod"] = stkfut["prod"] if stkfut else None
        return snap

    def watchlist_codes(self) -> list[str]:
        return list(self._watchlist)

    async def daily_bars(self, code: str, n: int = 25) -> list[DailyBar]:
        """overlay 日 bar;TC4 離線降級空(具體處理 = best-effort null,design R3)。"""
        try:
            return await asyncio.to_thread(self._source.fetch_daily_bars, code, n)
        except ConnectionError as e:
            logger.warning("daily_bars %s: TC4 不可用,overlay 降級空(%s)", code, e)
            return []

    async def bars_range(
        self, code: str, tf: str, start_date: str, end_date: str
    ) -> list[Bar]:
        """K 線 bar;TC4 離線降級空(同 daily_bars 的 best-effort 慣例)。"""
        try:
            return await asyncio.to_thread(
                self._source.fetch_bars_range, code, tf, start_date, end_date
            )
        except ConnectionError as e:
            logger.warning("bars_range %s(%s): TC4 不可用,降級空(%s)", code, tf, e)
            return []

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
        self._resub_task = asyncio.get_running_loop().create_task(self._resubscribe_all())
        logger.info("rollover stage1 → %s (gen=%d)", new_date, self._generation)

    async def _resubscribe_all(self) -> None:
        """全量重掛(UNSUB→SUB 冪等,新日窗);ZMQ REQ 全程 to_thread,不佔 event loop。"""
        async with self._pool_lock:
            codes = list(self._refs)

        def _do() -> None:
            for code in codes:
                try:
                    self._source.subscribe_symbol(code)
                except ConnectionError:
                    logger.warning("rollover resubscribe %s failed", code)

        await asyncio.to_thread(_do)

    def _rollover_stage2(self, first_tick: StockTick) -> None:
        """階段二:首筆新日 tick 確認 → reset 全部狀態,觸發 tick 重新 ingest。"""
        assert self._pending_date is not None
        self._trade_date = self._pending_date
        self._pending_date = None
        for state in self._states.values():
            state.reset()
        self._no_data.clear()
        if self._main is not None:
            self._backfill_jobs.put_nowait((self._main, self._generation))
        logger.info("rollover stage2 → %s(首筆 %s)", self._trade_date, first_tick.code)

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
        self._publish(
            {
                "type": "watchlist_quote",
                "code": code,
                "p": None,
                "chg_pct": None,
                "vol": None,
                "no_data": True,
            }
        )

    def _handle_reconnect(self) -> None:
        """TC4 重連:status 推播 + 主圖自癒重回補(design §2.4)。"""
        self.tc4_status = "up"
        self._publish({"type": "status", "tc4": "up", "backfilling": self._backfilling})
        if self._main is not None:
            self._backfill_jobs.put_nowait((self._main, self._generation))

    def _handle_quote(self, quote: dict) -> None:
        symbol = str(quote.get("Symbol", ""))
        if symbol.startswith("TC.F."):
            self._handle_stkfut(quote)
            return
        tick, book, meta = parse_stock_realtime(quote)
        code = str(quote.get("Security", ""))
        state = self._states.get(code)
        if state is None:
            return
        self._no_data.discard(code)
        state.update_book(book)
        state.update_meta(meta)
        if tick is not None and self._pending_date is None and tick.trade_date > self._trade_date:
            # 快路徑(CR5 / design §2.4):checkpoint 沒跑(週六補市日 weekday≥5)仍收到
            # 新日 tick → 先補 stage1 再走 stage2
            self.rollover_stage1(tick.trade_date)
        if (
            tick is not None
            and self._pending_date is not None
            and tick.trade_date == self._pending_date
        ):
            self._rollover_stage2(tick)
            state = self._states[code]
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
                        "seq": state.seq,
                    }
                )
            self._dirty_watchlist.add(code)
        if code == self._main:
            self._publish({"type": "book", "code": code, "bids": book.bids, "asks": book.asks})

    def _handle_stkfut(self, quote: dict) -> None:
        prod = str(quote.get("Security", ""))
        code = self._prod_to_code.get(prod)
        if code is None:
            return
        name = str(quote.get("SecurityName", ""))
        if code not in name:
            logger.warning("stkfut 對映不符:%s 推播 SecurityName=%s(對映表過期?)", prod, name)
        from copycat.live.stock_models import to_milli

        price = to_milli(str(quote.get("TradingPrice", "")))
        if price is None:
            return
        state = self._states.get(code)
        last = state.last if state is not None else None
        basis = price - last.price_milli if last is not None else None
        self._publish({"type": "stkfut", "code": code, "prod": prod, "p": price, "basis": basis})

    # ---- backfill worker(單工;guard = main ∧ generation)----

    async def _backfill_worker(self) -> None:
        while True:
            code, generation = await self._backfill_jobs.get()
            if code != self._main or generation != self._generation:
                continue
            self._backfilling = code
            self._publish({"type": "status", "tc4": self.tc4_status, "backfilling": code})
            try:
                ticks = await asyncio.to_thread(self._source.backfill, code)
            except ConnectionError:
                logger.exception("backfill %s failed", code)
                self.tc4_status = "down"
                self._backfilling = None
                self._publish({"type": "status", "tc4": "down", "backfilling": None})
                continue
            except Exception:
                # CR4:非連線類例外(壞電文 JSONDecodeError 等)不得殺死 worker —
                # 死掉 = 之後所有回補靜默失效、backfilling 永久卡住
                logger.exception("backfill %s unexpected failure(worker 續行)", code)
                self._backfilling = None
                self._publish({"type": "status", "tc4": self.tc4_status, "backfilling": None})
                continue
            self._backfilling = None
            # 套用 guard:回補期間主圖切換或 rollover → 丟棄(design §2.3);
            # 另過濾非當日列(防舊日窗殘留資料混入新日狀態)
            if code == self._main and generation == self._generation:
                state = self._states.get(code)
                if state is not None:
                    state.apply_backfill([t for t in ticks if t.trade_date == self._trade_date])
            self._publish({"type": "status", "tc4": self.tc4_status, "backfilling": None})

    # ---- 廣播 ----

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
                    queue.get_nowait()  # 滿丟最舊(treading-king Broadcaster 模型)
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(msg)
                except asyncio.QueueFull:
                    pass

    async def _flush_watchlist_loop(self) -> None:
        """側欄節流:1s 合併一則(design §2.4)。"""
        while True:
            await asyncio.sleep(self._throttle)
            dirty, self._dirty_watchlist = self._dirty_watchlist, set()
            for code in dirty:
                state = self._states.get(code)
                if state is None or state.last is None:
                    continue
                last = state.last
                meta = state.meta
                chg_pct: float | None = None
                if meta is not None and meta.ref_milli:
                    chg_pct = round((last.price_milli - meta.ref_milli) / meta.ref_milli * 100, 2)
                self._publish(
                    {
                        "type": "watchlist_quote",
                        "code": code,
                        "p": last.price_milli,
                        "chg_pct": chg_pct,
                        "vol": last.cum_vol,
                        "no_data": False,
                    }
                )


# 型別匯出(routes 注入用)
StockEngineLike = StockEngine
AnyDict = dict[str, Any]
