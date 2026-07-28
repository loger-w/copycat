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
import logging
from typing import Callable, Protocol

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

    # ---- 生命週期 ----

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._source = self._source_factory()
        self._source.set_on_message(self._on_quote_threadsafe)
        await asyncio.to_thread(self._subscribe_all)

    def _subscribe_all(self) -> None:
        assert self._source is not None
        for product in self._products:
            try:
                self._source.subscribe_symbol(product)
            except ConnectionError:
                # 單品訂閱失敗降級續行(app 層照起;stale 重連時基底會重掛成功品)
                logger.warning("futures subscribe %s failed", product)

    async def close(self) -> None:
        # 先斷 threadsafe 入口:close 期間 TC4 推播不得再 call_soon_threadsafe
        # 到即將關閉的 loop(index_engine review A1 同款);_loop=None 同時擋
        # leaf task 的收尾回寫(review I1)
        self._loop = None
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

    def resolved_contract(self, product: str) -> str | None:
        """HOT → 實際契約月份 YYYYMM;未解析/未知商品 → None(送單層拒單,不猜月份)。"""
        st = self._states.get(product)
        return st.resolved_ym if st is not None else None

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
