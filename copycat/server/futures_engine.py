"""FuturesEngine:TXF/MXF/TMF HOT 五檔/成交狀態機 + HOT→實際契約解析(SC-8;design §10)。

- per-product 狀態:最新成交(價/量/累積量/時刻/日期)、五檔(REALTIME `Bid`=最佳位移
  歸一)、漲跌停/參考價;`seq` 全域遞增;`state()` 供 REST/WS 全量。
- `resolved_contract(product)`:HOT 推播月份欄位解析 YYYYMM(resolve_contract_ym 純函式,
  futures_models)快取;跨日失效(date 變更清空)、換月即更新;解析不到 None = 送單層
  拒單(design §5 edge case 4)。
- 期貨無試撮窗、分鐘聚合 out of scope(梯不需要)→ 不做兩段式換日/StockDayState。
- 成交欄位 last-write-wins 不做 cum 序 stale-drop:REALTIME TradeVolume 每時段(日/夜盤)
  重新起算(live/session 時區事實),同日 cum 回捲是正常換場,嚴格遞增 guard 會整段丟夜盤。
- 建構子吃 source factory + broadcast callback(app.py 接線是 Task 9;測試注入 fake)。
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
from typing import Callable, Protocol

from copycat.live.stock_source import Bar
from copycat.live.futures_models import (
    PRODUCTS,
    parse_futures_realtime,
    product_from_symbol,
    resolve_contract_ym,
)

logger = logging.getLogger(__name__)


class FuturesSource(Protocol):
    """期貨行情來源抽象;TC4 實作在 copycat.live.futures_source,測試注入 fake。"""

    def subscribe_symbol(self, product: str) -> None: ...

    def subscribe_leaf(self, product: str, ym: str) -> None: ...

    def unsubscribe_symbol(self, product: str) -> None: ...

    def fetch_day_1k(self, product: str) -> list[tuple[int, int]]: ...

    def set_on_message(self, cb: Callable[[dict], None]) -> None: ...

    def close(self) -> None: ...


class _ProductState:
    __slots__ = (
        "name",
        "p",
        "q",
        "cum_vol",
        "t",
        "date",
        "bids",
        "asks",
        "ref",
        "upper",
        "lower",
        "resolved_ym",
    )

    def __init__(self) -> None:
        self.name = ""
        self.p: int | None = None
        self.q: int | None = None
        self.cum_vol: int | None = None
        self.t: str | None = None
        self.date: str | None = None
        self.bids: list[tuple[int, int]] = []
        self.asks: list[tuple[int, int]] = []
        self.ref: int | None = None
        self.upper: int | None = None
        self.lower: int | None = None
        self.resolved_ym: str | None = None

    def payload(self, product: str) -> dict:
        return {
            "product": product,
            "name": self.name,
            "p": self.p,
            "q": self.q,
            "cum_vol": self.cum_vol,
            "t": self.t,
            "date": self.date,
            "bids": list(self.bids),
            "asks": list(self.asks),
            "ref": self.ref,
            "upper": self.upper,
            "lower": self.lower,
            "resolved_contract": self.resolved_ym,
        }


class FuturesEngine:
    def __init__(
        self,
        source_factory: Callable[[], FuturesSource],
        *,
        broadcast: Callable[[dict], None] | None = None,
        products: tuple[str, ...] = PRODUCTS,
        leaf_grace_secs: float = 3.0,
        resub_interval_secs: float = 10.0,
    ) -> None:
        self._source_factory = source_factory
        self._broadcast = broadcast
        self._products = products
        self._states: dict[str, _ProductState] = {p: _ProductState() for p in products}
        self._seq = 0
        self._source: FuturesSource | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        # leaf fallback:HOT 與 TXO runtime spot 同 symbol 跨 session 只推一邊
        # (2026-07-28 盤中實證)→ resolve 已知後,寬限期仍零推播的商品補訂 leaf 契約
        self._leaf_grace_secs = leaf_grace_secs
        self._leaf_done: set[tuple[str, str]] = set()
        self._leaf_inflight: set[tuple[str, str]] = set()
        self._leaf_fed: set[str] = set()  # 曾成功補訂 leaf 的商品(換月重武裝判準)
        self._leaf_tasks: set[asyncio.Task[None]] = set()
        self._leaf_timer: asyncio.TimerHandle | None = None
        # 訂閱失敗品的唯一重試路徑(bug startup-names-futures-resub 症狀 3):
        # source 層 `_resub` 只重掛成功過的 symbol、`_leaf_fallback` 需先由推播解析 ym,
        # 兩條都接不了「一開始就訂不到」的商品 → 面板整段零推播且無錯誤訊號。
        self._resub_interval_secs = resub_interval_secs
        self._pending_subs: set[str] = set()
        self._resub_task: asyncio.Task[None] | None = None

    # ---- 生命週期 ----

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._source = self._source_factory()
        self._source.set_on_message(self._on_quote_threadsafe)
        await asyncio.to_thread(self._subscribe_all)
        if self._pending_subs:
            self._resub_task = asyncio.create_task(self._resub_loop())

    def _subscribe_all(self) -> None:
        assert self._source is not None
        for product in self._products:
            try:
                self._source.subscribe_symbol(product)
            except ConnectionError:
                # 單品訂閱失敗降級續行(app 層照起),失敗品進 pending 由 _resub_loop 重試
                # (寫入安全:start() 正 await 這個 to_thread,期間無並發讀寫)
                logger.warning("futures subscribe %s failed", product)
                self._pending_subs.add(product)

    async def _resub_loop(self) -> None:
        """pending 商品每 `resub_interval_secs` 重訂一次,成功即出列;全清空即結束。

        只有失敗品才會起這個 task —— 訂閱全成功時行為與修復前完全相同。
        """
        while self._pending_subs:
            await asyncio.sleep(self._resub_interval_secs)
            source = self._source  # 每輪重讀:close 中會變 None
            if source is None:
                return
            for product in sorted(self._pending_subs):
                try:
                    await asyncio.to_thread(source.subscribe_symbol, product)
                except ConnectionError:
                    # 留在 pending,下輪再試(log 字串與首輪一致 = 單一 grep 判準)
                    logger.warning("futures subscribe %s failed", product)
                    continue
                self._pending_subs.discard(product)
                logger.info("futures %s subscribe retry ok", product)

    async def close(self) -> None:
        # 先斷 threadsafe 入口:close 期間 TC4 推播不得再 call_soon_threadsafe
        # 到即將關閉的 loop(index_engine review A1 同款);_loop=None 同時擋
        # leaf task 的收尾回寫(review I1)
        self._loop = None
        # 重試迴圈先收掉:留著會在 source close 後繼續 subscribe → 重連 TC4(同 leaf I1 理由)
        resub, self._resub_task = self._resub_task, None
        if resub is not None:
            resub.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await resub
        if self._leaf_timer is not None:
            self._leaf_timer.cancel()
            self._leaf_timer = None
        if self._leaf_tasks:
            # in-flight leaf 訂閱先收完再關 source:close 後 subscribe_leaf 的
            # _ensure_connected 會重連 TC4 → session/KeepAlive 洩漏,process 不退(review I1)
            await asyncio.gather(*self._leaf_tasks, return_exceptions=True)
        source, self._source = self._source, None
        if source is not None:
            await asyncio.to_thread(source.close)

    # ---- 對外查詢 ----

    def state(self) -> dict:
        return {
            "seq": self._seq,
            "products": {p: st.payload(p) for p, st in self._states.items()},
        }

    async def bars_range(
        self, product: str, tf: str, start: str, end: str, *, session: str = "day"
    ) -> list[Bar]:
        """期指 K 線歷史 —— **必須從本引擎的 session 問**(同 `fetch_day_1k` 的理由)。

        借不到就回空、不 fallback 不猜:回空 + 固定可 grep 的 log 字串,3am 時
        `grep 'market: futures history proxy miss'` 就能分辨「TC4 掛了」與「真沒資料」。

        `session`(`day` / `allday`)原樣轉給 source(futures-allday §1.4);**不做
        「source 沒有這個參數就退回不帶」的相容分支** —— 那會讓漏改的 fake 靜默走
        日盤路徑,近全模式只是少了夜盤而不會有任何錯誤。fake 一律同步升簽名。
        """
        source = self._source
        # getattr 而非加進 Protocol:既有測試 fake 沒有這個方法,加進 Protocol 會讓
        # 每個注入點都要補一個用不到的 stub(K 線是可選能力,不是行情來源的本質)
        fetch = getattr(source, "fetch_bars_range", None) if source is not None else None
        if fetch is None:
            logger.warning("market: futures history proxy miss %s(source 未建/不支援)", product)
            return []
        try:
            # partial 而非 lambda:閉包會在 executor thread 才取值,partial 當場綁定
            return await asyncio.to_thread(
                functools.partial(fetch, product, tf, start, end, session=session)
            )
        except ConnectionError as e:
            logger.warning("market: futures history proxy miss %s(%s)", product, e)
            return []

    def resolved_contract(self, product: str) -> str | None:
        """HOT → 實際契約月份 YYYYMM;未解析/未知商品 → None(送單層拒單,不猜月份)。"""
        st = self._states.get(product)
        return st.resolved_ym if st is not None else None

    def fetch_day_1k(self, product: str) -> list[tuple[int, int]]:
        """當日 1K 分鐘序列 passthrough(江波圖台指腿回補;index-river-chart SC-4)。

        阻塞呼叫,呼叫端負責丟 `asyncio.to_thread`。source 未建(未 start / 已 close)→ 回空;
        `ConnectionError` 照原樣往外拋 —— 回補是可降級的,由呼叫端逐腿處置。
        本引擎持有 `TC.F.TWF.<product>.HOT` 的 REALTIME 訂閱,所以這檔的歷史也只能從這裡問
        (同 symbol 跨 session 只推一邊,CLAUDE.md §8)。
        """
        source = self._source
        if source is None:
            return []
        return source.fetch_day_1k(product)

    # ---- 推播處理(source thread → loop)----

    def _schedule_leaf_fallback(self, ym: str) -> None:
        """寬限期後,對仍零推播的商品補訂 leaf 契約(每 (product, ym) 只補一次)。

        月份借同家族已 resolve 的 ym(TXF/MXF/TMF 同結算月序)。健康情境所有商品都在
        寬限期內收到 HOT 推播 → 零補訂;衝突情境(spot 同 symbol)該品 p 恆 None → 補訂。
        """
        if self._loop is None or self._leaf_timer is not None:
            return
        pending = [p for p, st in self._states.items() if st.p is None]
        if not pending or all((p, ym) in self._leaf_done for p in pending):
            return
        self._leaf_timer = self._loop.call_later(self._leaf_grace_secs, self._leaf_fallback, ym)

    def _leaf_fallback(self, ym: str) -> None:
        self._leaf_timer = None
        loop = self._loop
        if loop is None or self._source is None:
            return
        for product, st in self._states.items():
            key = (product, ym)
            if st.p is not None or key in self._leaf_done or key in self._leaf_inflight:
                continue
            # 成功才入 _leaf_done(_leaf_finish);失敗 discard in-flight,
            # 下輪推播的 _schedule_leaf_fallback 自然重排重試(review I3)
            self._leaf_inflight.add(key)
            logger.warning(
                "futures %s HOT 零推播,補訂 leaf %s(同 symbol 跨 session 衝突)", product, ym
            )
            task = loop.create_task(asyncio.to_thread(self._leaf_subscribe_blocking, product, ym))
            self._leaf_tasks.add(task)  # 存引用防 GC;close 時 gather 收尾(review I1)
            task.add_done_callback(self._leaf_tasks.discard)

    def _leaf_subscribe_blocking(self, product: str, ym: str) -> None:
        """executor thread:訂 leaf 後把結果經 call_soon_threadsafe 回寫集合
        (集合只在 loop thread 動;_loop 已斷 = close 中,放棄回寫)。"""
        source = self._source
        ok = False
        if source is not None:
            try:
                source.subscribe_leaf(product, ym)
                ok = True
            except ConnectionError:
                logger.warning("futures leaf subscribe %s %s failed", product, ym)
        loop = self._loop
        if loop is None:
            return
        loop.call_soon_threadsafe(self._leaf_finish, product, ym, ok)

    def _leaf_finish(self, product: str, ym: str, ok: bool) -> None:
        self._leaf_inflight.discard((product, ym))
        if ok:
            self._leaf_done.add((product, ym))
            self._leaf_fed.add(product)

    def _on_quote_threadsafe(self, quote: dict) -> None:
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._handle_quote, quote)

    def _handle_quote(self, quote: dict) -> None:
        product = product_from_symbol(str(quote.get("Symbol", "")))
        if product is None:
            return
        st = self._states.get(product)
        if st is None:
            return
        tick, book, meta = parse_futures_realtime(quote)
        if book.bids or book.asks:
            st.bids = book.bids
            st.asks = book.asks
        if meta.name:
            st.name = meta.name
        if meta.ref_milli is not None:
            st.ref = meta.ref_milli
        if meta.upper_milli is not None:
            st.upper = meta.upper_milli
        if meta.lower_milli is not None:
            st.lower = meta.lower_milli
        if tick is not None:
            if st.date is not None and tick.trade_date != st.date:
                st.resolved_ym = None  # 跨日失效:先清,同筆有月份訊號再重解
                # 換月重武裝(review I2):leaf-fed 商品的舊月 leaf 到期後零推播,
                # pending 判準(p is None)只會冷啟動觸發一次 → 跨日時把 date 仍停在
                # 舊日的 leaf-fed 商品 p 清 None,新 ym 到達即補訂新月 leaf。
                # 舊月 leaf 不退訂 — 到期契約零推播,session 訂閱殘留可接受。
                for fed in self._leaf_fed:
                    fed_st = self._states.get(fed)
                    if fed_st is not None and fed_st.date != tick.trade_date:
                        fed_st.p = None
            st.date = tick.trade_date
            st.p = tick.price_milli
            st.q = tick.qty
            st.cum_vol = tick.cum_vol
            st.t = tick.time
        ym = resolve_contract_ym(quote)
        if ym is not None:
            st.resolved_ym = ym  # 快取;換月推播即更新
            self._schedule_leaf_fallback(ym)
        self._seq += 1
        if self._broadcast is not None:
            self._broadcast(
                {
                    "type": "futures",
                    "seq": self._seq,
                    "product": product,
                    "state": st.payload(product),
                }
            )
