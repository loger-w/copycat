"""相關係數引擎:每秒 pull 六腿中價 → 滾動相關 → 廣播(SC-5/6;design §6)。

**pull 而非 push**:需求是每秒更新,不是每 tick 更新。每秒主動讀各腿當前最佳買賣算
中價,取樣率與推播率解耦(台指 516 則/分 vs 費半 146 則/分不需對齊)。更關鍵的是
base 腿(台指)因此可以直接讀既有 `FuturesEngine.state()`,完全不發 SUBQUOTE ——
`TC.F.TWF.TXF.HOT` 已被 futures_engine 訂閱,同 symbol 跨 session 只推一邊
(CLAUDE.md §8,2026-07-28 實證),重複訂閱會讓其中一邊永久零推播且無錯誤訊號。

**兩種腿的新鮮度判定不同**:
- `tc4` 腿:收到推播即更新 `last_update`。
- `futures_engine` 腿:不經推播路徑,改以**內容變化**判定 —— 取到的 (bids, asks, p)
  與上次不同才更新。若沿用「收到推播才更新」,該腿會恆判 stale → base 恆 None →
  所有配對恆 None,而端點照常有回應,失效完全靜默(impl review P0-3)。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Protocol

from copycat.corr_config import SOURCE_FUTURES_ENGINE, SOURCE_TC4, CorrConfig
from copycat.live.corr_models import mid_from_book
from copycat.live.corr_state import CorrState, SessionKey
from copycat.live.river_models import minute_end_from_taipei
from copycat.live.river_state import RiverState
from copycat.live.session import session_key
from copycat.live.stock_models import parse_stock_realtime

logger = logging.getLogger(__name__)


def _taipei_hhmmss() -> str:
    """本機時鐘的台北時刻(server 機器時區 = 台北,同 index_engine 的 txf 時刻處理)。"""
    return time.strftime("%H%M%S")


class CorrSource(Protocol):
    """行情源抽象;TC4 實作在 copycat.live.corr_source,測試注入 fake。"""

    def subscribe_raw(self, symbol: str) -> None: ...

    def unsubscribe_raw(self, symbol: str) -> None: ...

    def set_on_message(self, cb: Callable[[dict], None]) -> None: ...

    def fetch_day_1k(self, symbol: str) -> list[tuple[int, int]]: ...

    def close(self) -> None: ...


class _LegState:
    __slots__ = ("mid", "last_update", "fingerprint")

    def __init__(self) -> None:
        self.mid: int | None = None
        self.last_update: float | None = None
        # futures_engine 腿的內容變化判定用(impl review P0-3)
        self.fingerprint: tuple[Any, ...] | None = None


class CorrelationEngine:
    def __init__(
        self,
        source_factory: Callable[[], CorrSource],
        *,
        config: CorrConfig,
        txf_state_getter: Callable[[], dict],
        broadcast: Callable[[dict], None] | None = None,
        river_broadcast: Callable[[dict], None] | None = None,
        futures_minutes_fetch: Callable[[str], list[tuple[int, int]]] | None = None,
        tick_secs: float = 1.0,
        now_fn: Callable[[], float] = time.monotonic,
        session_fn: Callable[[], SessionKey] = session_key,
        taipei_time_fn: Callable[[], str] = _taipei_hhmmss,
    ) -> None:
        self._source_factory = source_factory
        self._config = config
        self._txf_state_getter = txf_state_getter
        self._broadcast = broadcast
        self._river_broadcast = river_broadcast
        self._futures_minutes_fetch = futures_minutes_fetch
        self._tick_secs = tick_secs
        self._now = now_fn
        self._session_fn = session_fn
        self._taipei_time_fn = taipei_time_fn
        self._by_symbol = {leg.symbol: leg for leg in config.legs}
        self._legs = {leg.key: _LegState() for leg in config.legs}
        self._books: dict[str, tuple[list, list]] = {}
        self._state = CorrState(
            [leg.key for leg in config.legs],
            config.base,
            windows=config.windows,
            min_samples=config.min_samples,
            sample_secs=tick_secs,
        )
        self._seq = 0
        self._source: CorrSource | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[None] | None = None
        # 江波圖(index-river-chart):同一份報價流餵第二個狀態機,零新增訂閱
        self._river = RiverState([leg.key for leg in config.legs], base=config.base)
        self._river_seq = 0
        self._backfill_task: asyncio.Task[None] | None = None
        self._backfill_inflight = False

    # ---- 生命週期 ----

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._source = self._source_factory()
        self._source.set_on_message(self._on_quote_threadsafe)
        await asyncio.to_thread(self._subscribe_all)
        self._task = self._loop.create_task(self._run())
        # 回補放背景:六腿各要 SubHistory + 分頁收割,阻塞 start 會讓整個 app 起動變慢,
        # 而畫面本來就可以先有 live 點再補歷史(design §3)
        self._backfill_task = self._loop.create_task(self._backfill_river())
        if hasattr(self._source, "on_reconnect"):
            # 重連後補跑一次:斷線期間的分鐘只能靠回補補齊(edge case 5)
            self._source.on_reconnect = self._on_reconnect_threadsafe  # type: ignore[attr-defined]

    def _subscribe_all(self) -> None:
        """只訂 source == tc4 的腿;單腿失敗降級續行(沿用 futures_engine 慣例)。"""
        assert self._source is not None
        for leg in self._config.tc4_legs():
            try:
                self._source.subscribe_raw(leg.symbol)
            except ConnectionError:
                logger.warning("corr subscribe %s(%s)失敗,該腿停用", leg.key, leg.symbol)

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._tick_secs)
            try:
                self.tick_once()
            except Exception:
                # tick 失敗不得讓迴圈死掉(否則整個面板靜止且無訊號)
                logger.exception("corr tick 失敗(續行)")

    async def close(self) -> None:
        # 先斷 threadsafe 入口:close 期間推播不得再 call_soon_threadsafe 到即將關閉的
        # loop(futures_engine / index_engine review A1 同款)
        self._loop = None
        tick_task, self._task = self._task, None
        backfill_task, self._backfill_task = self._backfill_task, None
        for task in (tick_task, backfill_task):
            if task is None:
                continue
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        source, self._source = self._source, None
        if source is not None:
            await asyncio.to_thread(source.close)

    # ---- 推播處理(source thread → loop)----

    def _on_quote_threadsafe(self, quote: dict) -> None:
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._handle_quote, quote)
        # _loop is None = close 中/後 → 丟棄,不得再排進即將關閉的 loop

    def _handle_quote(self, quote: dict) -> None:
        leg = self._by_symbol.get(str(quote.get("Symbol", "")))
        if leg is None or leg.source != SOURCE_TC4:
            return
        tick, book, _meta = parse_stock_realtime(quote)
        if tick is not None:
            # 江波圖走**成交價**(不是中價):1K 回補給的是 close,live 用中價會讓
            # 回補段與 live 段不同尺(design §9-3)
            minute = minute_end_from_taipei(tick.time)
            if minute is not None:
                self._river.push(leg.key, minute, tick.price_milli, self._session_fn())
        if not book.bids and not book.asks:
            return
        self._books[leg.key] = (list(book.bids), list(book.asks))
        self._legs[leg.key].last_update = self._now()

    # ---- 每秒取樣 ----

    def _futures_leg_book(self, key: str) -> tuple[list, list, Any]:
        products = (self._txf_state_getter() or {}).get("products", {})
        payload = products.get(key) or {}
        return (
            list(payload.get("bids") or []),
            list(payload.get("asks") or []),
            payload.get("p"),
        )

    def tick_once(self) -> None:
        """一次取樣 + 計算 + 廣播(tick task 每 tick_secs 呼叫;測試直接呼叫)。"""
        now = self._now()
        mids: dict[str, int | None] = {}
        for leg in self._config.legs:
            st = self._legs[leg.key]
            if leg.source == SOURCE_FUTURES_ENGINE:
                bids, asks, price = self._futures_leg_book(leg.key)
                fingerprint = (tuple(bids), tuple(asks), price)
                if bids or asks:
                    # 內容變化才算「有更新」—— 該腿不經推播路徑(impl review P0-3)
                    if fingerprint != st.fingerprint:
                        st.fingerprint = fingerprint
                        st.last_update = now
            else:
                bids, asks = self._books.get(leg.key, ([], []))
            fresh = (
                st.last_update is not None and (now - st.last_update) <= self._config.stale_secs
            )
            st.mid = mid_from_book(bids, asks) if fresh else None
            mids[leg.key] = st.mid
        session = self._session_fn()
        self._state.push(now, mids, session)
        self._seq += 1
        if self._broadcast is not None:
            self._broadcast(self.state())
        self._river_tick(session)

    # ---- 江波圖(index-river-chart)----

    def _river_tick(self, session: SessionKey) -> None:
        """台指腿的分鐘點 + 每秒 delta 廣播。

        台指腿走 pull 不走推播,分鐘桶用本機時鐘 —— `futures_engine` 的 `st.t` 在既有 bug 1
        情境下可能是 None,且 pull 型取樣的語意本來就是「這一秒讀到的值」(同 index_engine
        IR1 對 txf 的處理)。
        """
        self._river.set_session(session)
        minute = minute_end_from_taipei(self._taipei_time_fn())
        for leg in self._config.legs:
            if leg.source != SOURCE_FUTURES_ENGINE:
                continue
            _bids, _asks, price = self._futures_leg_book(leg.key)
            if minute is not None and isinstance(price, int):
                self._river.push(leg.key, minute, price, session)
        self._river_seq += 1
        if self._river_broadcast is not None:
            self._river_broadcast(self._river.delta(self._river_seq))

    async def _backfill_river(self) -> None:
        """逐腿 1K 回補(single-flight);單腿失敗只降級該腿(SC-3)。"""
        if self._backfill_inflight:
            return
        self._backfill_inflight = True
        try:
            session = self._session_fn()
            # 這裡**不呼叫** set_session:回補是慢動作(每腿 SubHistory + 分頁收割),
            # 換場邊界上晚到的回補會把狀態機拉回發起時那一場,清掉新場已累積的點並退回舊窗
            # (Phase 4 自評 finding)。盤別由每秒的 _river_tick 單點驅動;
            # apply_backfill 自己會用 session 比對丟棄過期回補。
            for leg in self._config.legs:
                rows = await self._fetch_leg_minutes(leg.key, leg.symbol, leg.source)
                if rows:
                    filled = self._river.apply_backfill(leg.key, rows, session)
                    logger.info("river 回補 %s:%d 分鐘", leg.key, filled)
        finally:
            self._backfill_inflight = False

    async def _fetch_leg_minutes(
        self, key: str, symbol: str, source_kind: str
    ) -> list[tuple[int, int]]:
        """一條腿的 1K 取得;失敗回空(該腿只從啟動後累積,不影響其餘腿)。

        `futures_engine` 腿走注入的 fetch —— 台指的歷史也必須從持有 TXF 訂閱的那條 session 問
        (同 symbol 跨 session 只推一邊,CLAUDE.md §8)。leg.key 即期貨產品碼(design §4 假設,
        與既有 `_futures_leg_book` 同一個假設)。
        """
        try:
            if source_kind == SOURCE_FUTURES_ENGINE:
                fetch = self._futures_minutes_fetch
                if fetch is None:
                    return []
                return await asyncio.to_thread(fetch, key)
            source = self._source
            if source is None:
                return []
            return await asyncio.to_thread(source.fetch_day_1k, symbol)
        except ConnectionError:
            logger.warning("river 回補 %s(%s)失敗,該腿只從啟動後累積", key, symbol)
            return []

    def _on_reconnect_threadsafe(self) -> None:
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._schedule_backfill)

    def _schedule_backfill(self) -> None:
        loop = self._loop
        if loop is None or self._backfill_inflight:
            return
        self._backfill_task = loop.create_task(self._backfill_river())

    def river_snapshot(self) -> dict:
        labels = {leg.key: leg.label for leg in self._config.legs}
        return self._river.snapshot(labels, self._river_seq)

    # ---- 對外查詢 ----

    def state(self) -> dict:
        now = self._now()
        labels = {leg.key: leg.label for leg in self._config.legs}
        return {
            "type": "corr",
            "seq": self._seq,
            "session": self._session_fn()[1],
            "base": self._config.base,
            "windows": list(self._config.windows),
            "legs": {
                key: {
                    "label": labels[key],
                    "mid": st.mid,
                    "stale": st.mid is None,
                }
                for key, st in self._legs.items()
            },
            "pairs": self._state.correlations(now),
        }
