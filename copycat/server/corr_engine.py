"""相關係數引擎:每秒 pull 各腿中價 → 滾動相關 → 廣播(SC-5/6;design §6)。

**pull 而非 push**:需求是每秒更新,不是每 tick 更新。每秒主動讀各腿當前最佳買賣算
中價,取樣率與推播率解耦(台指 516 則/分 vs 費半 146 則/分不需對齊)。更關鍵的是
base 腿(台指)因此可以直接讀既有 `FuturesEngine.state()`,完全不發 SUBQUOTE ——
`TC.F.TWF.TXF.HOT` 已被 futures_engine 訂閱,本引擎不對同一個 symbol 再掛一把 TC4
refcount key —— 上游 feed 以 symbol 為單位,任一把 key 歸零就退訂整個 symbol,失效樣態是
永久零推播且無錯誤訊號(2026-08-18 實證,見 `.claude/skills/tc4-market-facts/SKILL.md`)。

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
from copycat.live.river_models import minute_end_from_taipei, minute_end_from_utc_hhmmss
from copycat.live.river_state import RiverState
from copycat.live.session import session_key
from copycat.live.stock_models import parse_stock_realtime
from copycat.live.tc4 import HistoryTimeoutError

logger = logging.getLogger(__name__)

#: 逾時腿的重補退避(秒)與輪數上限。真實事故是「三腿同秒逾時 → 整天不再回補」,
#: 而 TC4 端的 1K 一直都在;沒有輪數上限則反過來變成整天重打必敗請求。
_BACKFILL_RETRY_SECS = 30.0
_BACKFILL_RETRY_MAX_ROUNDS = 3


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
        resub_interval_secs: float = 10.0,
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
        # 逾時腿的重補記帳(bug/history-timeout-propagation):`_backfill_pending_legs`
        # 由 `_fetch_leg_minutes` 在逾時分支寫入、每輪開頭重置;`_backfill_retry_round`
        # 是**連續**失敗輪數(補齊一輪就歸零),`_backfill_retry_tasks` 讓 close() 有
        # 唯一取消點(專用欄位存放會被下一次排程覆寫成孤兒 task)。
        self._backfill_pending_legs: set[str] = set()
        self._backfill_retry_round = 0
        self._backfill_retry_tasks: set[asyncio.Task[None]] = set()
        # 訂閱失敗腿的唯一重試路徑(照抄 futures_engine 形狀):`_on_reconnect` 只重跑
        # 江波圖回補、不重訂閱 → 首輪 SUBQUOTE 失敗的腿整天零推播且無錯誤訊號
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
            # 只有失敗腿才起這個 task —— 訂閱全成功時行為與修復前完全相同
            self._resub_task = self._loop.create_task(self._resub_loop())
        self._task = self._loop.create_task(self._run())
        # 回補放背景:各腿各要 SubHistory + 分頁收割,阻塞 start 會讓整個 app 起動變慢,
        # 而畫面本來就可以先有 live 點再補歷史(design §3)
        self._backfill_task = self._loop.create_task(self._backfill_river())
        if hasattr(self._source, "on_reconnect"):
            # 重連後補跑一次:斷線期間的分鐘只能靠回補補齊(edge case 5)
            self._source.on_reconnect = self._on_reconnect_threadsafe  # type: ignore[attr-defined]

    def _subscribe_all(self) -> None:
        """只訂 source == tc4 的腿;單腿失敗降級續行,失敗品進 `_pending_subs` 由重試迴圈接手。

        (寫入安全:start() 正 await 這個 to_thread,期間無並發讀寫;同 futures_engine 註解。)
        """
        assert self._source is not None
        for leg in self._config.tc4_legs():
            try:
                self._source.subscribe_raw(leg.symbol)
            except ConnectionError:
                logger.warning("corr subscribe %s(%s)失敗,進重試佇列", leg.key, leg.symbol)
                self._pending_subs.add(leg.symbol)

    async def _resub_loop(self) -> None:
        """pending 腿每 `resub_interval_secs` 重訂一次,成功即出列;全清空即結束。

        迭代 `tc4_legs()` 而非 `_pending_subs` 本身:base 腿(futures_engine 來源)因此
        結構上不可能被重試訂閱 —— 重複訂 `TXF.HOT` 會讓其中一邊永久零推播(CLAUDE.md §8)。
        """
        while self._pending_subs:
            await asyncio.sleep(self._resub_interval_secs)
            source = self._source  # 每輪重讀:close 中會變 None
            if source is None:
                return
            try:
                await self._resub_round(source)
            except Exception:
                # 非 ConnectionError 的例外(壞電文 / wrapper 內部型別錯)不得殺掉迴圈:
                # 死掉 = 復原路徑本身靜默失效,而 close() 的收尾又會把 task 例外吞掉
                # (同 corr `_run` 的 rationale)。CancelledError 是 BaseException,不被接住
                logger.exception("corr 訂閱重試輪失敗(續行)")

    async def _resub_round(self, source: CorrSource) -> None:
        recovered = False
        for leg in self._config.tc4_legs():
            if leg.symbol not in self._pending_subs:
                continue
            try:
                await asyncio.to_thread(source.subscribe_raw, leg.symbol)
            except ConnectionError:
                # 留在 pending,下輪再試(log 字串與首輪一致 = 單一 grep 判準)
                logger.warning("corr subscribe %s(%s)失敗,進重試佇列", leg.key, leg.symbol)
                continue
            self._pending_subs.discard(leg.symbol)
            logger.info("corr %s subscribe retry ok", leg.key)
            recovered = True
        if recovered:
            # 失敗窗內漏掉的江波圖分鐘只能靠回補補齊。`_schedule_backfill` 在
            # inflight 時是**丟棄**不是排隊 → 本輪定調 best-effort,被擋下時留一行
            # 痕跡才追得到(排隊化屬 `_backfill_task` 覆寫孤兒那條 next-time 條目)
            if self._backfill_inflight:
                logger.info("corr 重訂成功但回補進行中,本次補分鐘略過(best-effort)")
            self._schedule_backfill()

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
        resub_task, self._resub_task = self._resub_task, None
        # 快照後清空:`add_done_callback` 會在 cancel 期間就地 discard,直接迭代本體
        # 就是 RuntimeError(而 close 之後的每一步都不會跑)
        retry_tasks = list(self._backfill_retry_tasks)
        self._backfill_retry_tasks.clear()
        # 重試迴圈**排最前**:留著會在 source close 後繼續 subscribe → 重連 TC4
        # (同 futures_engine close 的理由)
        for task in (resub_task, tick_task, backfill_task, *retry_tasks):
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
            # 回補段與 live 段不同尺(design §9-3)。
            #
            # 分鐘桶用 `FilledTime` 而**不是** `tick.time` —— tick.time 由
            # `stock_models._taipei_time` 以 zfill(12) 解 `PreciseTime`,而該欄寬度跨交易所段
            # 不同(台期交 12 位微秒 / CME·CBOT·SGX 6 位 HHMMSS,2026-07-30 real-env 實證)。
            # 對海外腿那個假設會算出恆為台北 08:00:00.0xx 的時刻 → 分鐘落在窗外 → 該腿永遠
            # 不進點。FilledTime 兩段同寬;缺值才退回本機時鐘(同台指腿處理)。
            minute = minute_end_from_utc_hhmmss(str(quote.get("FilledTime", "")))
            if minute is None:
                minute = minute_end_from_taipei(self._taipei_time_fn())
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
            fresh = st.last_update is not None and (now - st.last_update) <= self._config.stale_secs
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

    async def _backfill_river(self, legs: set[str] | None = None) -> None:
        """逐腿 1K 回補(single-flight);單腿失敗只降級該腿(SC-3)。

        `legs` = 只補這些腿(逾時重試輪用)。`None` = 全部腿,與修復前逐字相同。
        """
        if self._backfill_inflight:
            self._merge_into_inflight_round(legs)
            return
        self._backfill_inflight = True
        try:
            session = self._session_fn()
            # 這裡**不呼叫** set_session:回補是慢動作(每腿 SubHistory + 分頁收割),
            # 換場邊界上晚到的回補會把狀態機拉回發起時那一場,清掉新場已累積的點並退回舊窗
            # (Phase 4 自評 finding)。盤別由每秒的 _river_tick 單點驅動;
            # apply_backfill 自己會用 session 比對丟棄過期回補。
            self._backfill_pending_legs = set()  # 本輪重新收集(上一輪的名單已用完)
            for leg in self._config.legs:
                if legs is not None and leg.key not in legs:
                    continue
                rows = await self._fetch_leg_minutes(leg.key, leg.symbol, leg.source)
                if rows:
                    filled = self._river.apply_backfill(leg.key, rows, session)
                    logger.info("river 回補 %s:%d 分鐘", leg.key, filled)
            pending = set(self._backfill_pending_legs)
        finally:
            self._backfill_inflight = False
        # 排程放在 inflight 旗標之外:重試 task 自己也要能通過 single-flight 的門
        if not pending:
            self._backfill_retry_round = 0  # 補齊一輪 → 連續失敗歸零
            return
        if self._backfill_retry_round >= _BACKFILL_RETRY_MAX_ROUNDS:
            logger.warning(
                "river 回補逾時腿 %s 已重試 %d 輪仍未補齊,放棄(只從啟動後累積)",
                sorted(pending),
                _BACKFILL_RETRY_MAX_ROUNDS,
            )
            # 計數是**連續**失敗輪數 → 放棄那一刻也要歸零(同「補齊一輪」那條路)。
            # 不歸零的話它永久停在上限:當天稍後每一次 reconnect 回補都會在第一次逾時
            # 就直接放棄(零重試),而 log 只有一行「已重試 3 輪」讀起來像真的試過。
            # 第二個 episode 是新的抖動,該有自己的完整預算。
            self._backfill_retry_round = 0
            return
        self._backfill_retry_round += 1
        self._schedule_backfill_retry(pending)

    def _merge_into_inflight_round(self, legs: set[str] | None) -> None:
        """single-flight 互吃:把被擋下那一發的腿併回進行中那一輪的 pending。

        舊碼兩處都是靜默 `return`(`_schedule_backfill` 連 task 都不建、零 log;
        `_backfill_river` 的重試腿蒸發),全鏈零訊號 —— 江波圖只是缺前半段。併回之後由
        **進行中那一輪的尾巴**接手重排(它的 `pending` 快照與 `_backfill_inflight = False`
        之間沒有 await,此刻的寫入必定被它讀到,恰好排一次)。
        `None` = 整輪(reconnect 觸發)= 全部腿;`set()` 空集合照字面 = 一腿都不補
        (與 `_backfill_river` 的 `legs is not None` 語意一致)。
        整輪併回 = 新 episode:連續失敗輪數歸零,否則它會吃掉上一個 episode 剩下的逾時
        重試預算,round 已達上限時更會整批落進「放棄」分支、log 還誣賴健康腿逾時。
        重試腿併回則**不**動輪數:被擋下不等於試過一次。
        """
        merged = set(self._legs) if legs is None else set(legs)
        logger.info(
            "river 回補 single-flight:已有一輪進行中,本次併回 pending(legs=%s)",
            sorted(merged),
        )
        self._backfill_pending_legs |= merged
        if legs is None:
            self._backfill_retry_round = 0

    def _schedule_backfill_retry(self, legs: set[str]) -> None:
        """`_BACKFILL_RETRY_SECS` 後只補 `legs`;task 進集合供 close() 統一取消。"""
        loop = self._loop
        if loop is None:  # close 中 / 尚未 start
            return
        task = loop.create_task(self._backfill_retry(legs))
        self._backfill_retry_tasks.add(task)
        task.add_done_callback(self._backfill_retry_tasks.discard)

    async def _backfill_retry(self, legs: set[str]) -> None:
        await asyncio.sleep(_BACKFILL_RETRY_SECS)
        logger.info("river 回補重試(第 %d 輪):%s", self._backfill_retry_round, sorted(legs))
        try:
            await self._backfill_river(legs=legs)
        except Exception:
            # `_fetch_leg_minutes` 只接 ConnectionError 家族;apply_backfill / 換場等處的其他
            # 例外會讓這支 task 以「Task exception was never retrieved」收場,
            # `_backfill_retry_round` 卡在非零 → 當天稍後的新 episode 拿到被削過的預算。
            # 具體處置 = 留 traceback + 連續失敗輪數歸零(與「放棄」分支同語意)。
            logger.exception("river 回補重試 task 非預期例外(第 %d 輪),輪數歸零", self._backfill_retry_round)
            self._backfill_retry_round = 0

    async def _fetch_leg_minutes(
        self, key: str, symbol: str, source_kind: str
    ) -> list[tuple[int, int]]:
        """一條腿的 1K 取得;失敗回空(該腿只從啟動後累積,不影響其餘腿)。

        `futures_engine` 腿走注入的 fetch —— 台指的歷史也必須從持有 TXF 訂閱的那條 session 問
        (別條 session 問會多掛一把 refcount key,歸零時退訂整個 symbol;見
        `.claude/skills/tc4-market-facts/SKILL.md`)。leg.key 即期貨產品碼(design §4 假設,
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
        except HistoryTimeoutError:
            # **先於** ConnectionError(它是子類):TC4 沒掛,只是這一檔的 history 首頁
            # 還沒備妥 —— 這條路本來就會在幾十秒後成功。舊碼把它與斷線一起降級成
            # 「只從啟動後累積」,08:23 三腿同秒逾時就讓江波圖整天缺前半段。
            logger.warning("river 回補 %s(%s)逾時(非 TC4 down),排入重補", key, symbol)
            self._backfill_pending_legs.add(key)
            return []
        except ConnectionError:
            logger.warning("river 回補 %s(%s)失敗,該腿只從啟動後累積", key, symbol)
            return []

    def _on_reconnect_threadsafe(self) -> None:
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._schedule_backfill)

    def _schedule_backfill(self) -> None:
        loop = self._loop
        if loop is None:
            return
        if self._backfill_inflight:
            # reconnect 撞上進行中那一輪:這裡才是整輪真正的丟棄點(2026-08-22 review P1),
            # 不建 task 但要併回,否則 reconnect 後的整輪回補零訊號蒸發。
            self._merge_into_inflight_round(None)
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
