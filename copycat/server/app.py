"""FastAPI app:route 只 raise 不 catch;error contract {"detail": {"error": code}}(§2)。"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import date as _date
from pathlib import Path
from typing import AsyncGenerator, Awaitable, Callable, Final, Literal, TypeVar, cast

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from copycat.live.trade_models import (
    BrokerRejectedError,
    OrderRequest,
    TouchanceDownError,
    millipts_from_price_str,
)
from copycat.capital import factory as capital_factory
from copycat.capital.client import CapitalClient
from copycat.server import build_info
from copycat.server.audit import AuditWriteError
from copycat.corr_config import load_config as load_corr_config
from copycat.server.capital_api import register_capital
from copycat.server.ws import WsBroadcaster, relay
from copycat.server.corr_engine import CorrelationEngine, CorrSource
from copycat.server.engine import EngineRuntime, QuoteSource
from copycat.server.futures_engine import FuturesEngine, FuturesSource
from copycat.server.index_engine import IndexEngine, IndexSource
from copycat.live.stock_source import Bar
from copycat.server.mis import OtcSnap, fetch_otc_snapshot
from copycat.server.bars import (
    BarsCache,
    build_daily,
    build_minute,
    build_period,
    clamp_days,
    is_partial_last,
)
from copycat.notify import notify_discord
from copycat.server.discord_bot import Bot, create_bot
from copycat.server.overlay import OverlayCache, build_overlay
from copycat.server.signal_hub import SignalHub
from copycat.server.stock_engine import StockEngine, StockSource
from copycat.server.watchlist_service import WatchlistService
from copycat.signals_config import load_signals_config
from copycat.stock_watchlist import (
    Group,
    WatchlistError,
    load_watchlist,
    union,
    validate_code,
)
from copycat.stock_watchlist import DEFAULT_PATH as WATCHLIST_DEFAULT_PATH
from copycat.stock_names import DEFAULT_PATH as NAMES_DEFAULT_PATH
from copycat.stock_names import load_names as load_stock_names
from copycat.tc4common import TC4_DEFAULT_PORT
from copycat.server.trade import (
    ConfirmRequiredError,
    InvalidOrderError,
    LiveBlockedError,
    NotReadyError,
    PreviewExpiredError,
    SymbolNotAllowedError,
    TradeRuntime,
    TradeSource,
)

logger = logging.getLogger(__name__)

#: 大盤頁支援的標的鍵。值域小且固定 → 白名單比 regex 好:非法鍵一律 400 BAD_KEY,
#: 不讓打錯的字串一路走到 TC4 才回空(那會被誤讀成「沒資料」)。
MARKET_KEYS = ("TWSE", "OTC", "TXF", "MXF", "TMF")


def _market_payload(
    key: str,
    tf: str,
    bars: list[Bar],
    *,
    source: str,
    volume: bool | None = None,
    partial_last: bool = False,
    refusal: str | None = None,
    synth_since: str | None = None,
) -> dict:
    """大盤 K 線回應(index-board N-5)。

    `meta` 不是裝飾:前端固定把它渲染成一行「來源 · 涵蓋期間」,讓「壞了 vs 沒資料」
    看畫面就能答(/adhd 三個 frame 收斂到的同一點)。`source` 必須是**實際走到的分支**,
    不能是預期值 —— DK 空時 fallback 成 1K 聚合而 meta 仍標 tc4_dk,等於在最可能出事的
    那條路上說謊(review P1-4)。
    """
    # volume 未指定時**由資料判定**:指數(IX0001)的 DK/1K 沒有量欄位,`_int_field`
    # 缺值回 0 → 整條序列 v=0。標 volume=true 會讓前端畫一排貼底的 0 高柱,與「真的
    # 零成交」在畫面上無法區分 —— 正是 SC-6 要避免的假造零(2026-07-30 real-env 抓到)。
    has_volume = volume if volume is not None else any(b["v"] > 0 for b in bars)
    return {
        "key": key,
        "tf": tf,
        "bars": bars,
        "meta": {
            "source": source,
            "coverage_from": bars[0]["t"][:10] if bars else None,
            "coverage_to": bars[-1]["t"][:10] if bars else None,
            "partial_last": partial_last,
            "volume": has_volume,
            "refusal": refusal,
            "synth_since": synth_since,
        },
    }


# sentinel:__main__ 傳 DEFAULT_TRADE = 正式啟動旗標(TradeRuntime 已停用,SC-11;
# 現僅用於 futures 行情引擎的預設接線 — __main__ 不動,lifespan 見 futures 段)
DEFAULT_TRADE: Final = object()
DEFAULT_STOCK: Final = object()  # 同語意:__main__ 傳入才建真 StockQuoteSource
DEFAULT_INDEX: Final = object()  # 同語意(index-board IR9)
DEFAULT_FUTURES: Final = object()  # 同語意(capital-order SC-8)
DEFAULT_CORR: Final = object()  # 同語意(realtime-correlation SC-6)


class SelectBody(BaseModel):
    series_id: str


class GroupBody(BaseModel):
    name: str
    codes: list[str]


class GroupsBody(BaseModel):
    groups: list[GroupBody]
    codes: list[str] | None = None  # v3 自選全體;缺省 → union(groups)(舊 client 相容)


class PreviewBody(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    kind: Literal["limit", "market"]
    qty: int
    price: str | None = None


class SubmitBody(BaseModel):
    preview_id: str


class SignalsEnabledBody(BaseModel):
    #: 值刻意宣告成 `object` 而非 `bool`:pydantic v2 的寬鬆模式會把 "yes"/"1" 轉成 True,
    #: 打錯的值就會被靜默接受成「開啟」。四鍵與型別一律由 `hub.set_enabled` 驗
    #: (ValueError → 400 INVALID_SIGNALS_ENABLED),驗證規則單一定義在 hub。
    enabled: dict[str, object]


def _tc4_port() -> str:
    return os.environ.get("TC4_PORT", TC4_DEFAULT_PORT)


_BootT = TypeVar("_BootT")


async def _boot(
    name: str,
    fail_msg: str,
    make: Callable[[], _BootT | None],
    start: Callable[[_BootT], Awaitable[None]],
    close: Callable[[_BootT], Awaitable[None]],
) -> _BootT | None:
    """引擎起停樣板(B-D7):任一引擎起不來都只讓自己停用,不波及其他引擎。

    兩段式而非單一 `build`:**`make` 與 `start` 都必須在同一個 try 內**,而 except
    分支要拿得到已建好的物件才關得掉 —— 「建構成功但 start 失敗」若沒 close,會洩漏
    一條已連線的 TC4 session,畫面只看得到 503。

    - `make` 回 `None` = sentinel 解析結果為「不啟動」→ 整段跳過,**不記失敗 log**。
    - `start` 語意 = 「帶到就緒的全部工作」,不只 `o.start()`:stock 的自選回填也在內
      (`load_watchlist` 對壞檔不吞例外,現況正是由這個 except 接住)。
    """
    obj: _BootT | None = None
    try:
        obj = make()
        if obj is None:
            return None
        await start(obj)
        return obj
    except Exception:
        logger.exception("%s", fail_msg)
        if obj is not None:
            try:
                await close(obj)
            except Exception:
                logger.exception("%s close 失敗(忽略)", name)
        return None


def _default_source() -> QuoteSource:
    from copycat.live.tc4 import TC4QuoteSource  # 延遲 import:測試不觸 pyzmq/TC4

    return TC4QuoteSource(
        port=_tc4_port(),
        backfill_date=os.environ.get("TXO_BACKFILL_DATE"),
    )


def _default_stock_source() -> StockSource:
    from copycat.live.stock_source import StockQuoteSource  # 延遲 import:測試不觸 pyzmq

    return StockQuoteSource(port=_tc4_port())


def _default_index_source() -> IndexSource:
    from copycat.live.stock_source import StockQuoteSource  # 獨立 session(指數專用)

    return StockQuoteSource(port=_tc4_port())


def _default_futures_source() -> FuturesSource:
    from copycat.live.futures_source import FuturesQuoteSource  # 延遲 import:測試不觸 pyzmq

    return FuturesQuoteSource(port=_tc4_port())


def _default_corr_source() -> CorrSource:
    from copycat.live.corr_source import CorrQuoteSource  # 延遲 import:測試不觸 pyzmq

    return CorrQuoteSource(port=_tc4_port())


def create_app(
    source: QuoteSource | None = None,
    *,
    trade_source: TradeSource | object | None = None,
    stock_source: StockSource | object | None = None,
    index_source: IndexSource | object | None = None,
    futures_source: FuturesSource | object | None = None,
    corr_source: CorrSource | object | None = None,
    index_mis_fetch: Callable[[], OtcSnap | None] = fetch_otc_snapshot,
    stock_watchlist_path: Path | None = None,
    stock_names_path: Path | None = None,
    throttle_secs: float = 1.0,
    queue_maxsize: int = 10_000,
) -> FastAPI:
    wl_path = stock_watchlist_path if stock_watchlist_path is not None else WATCHLIST_DEFAULT_PATH
    # 名稱表是版控檔(必然存在)→ 沒有注入點的話「表不可用」這條降級路徑無法測
    names_path = stock_names_path if stock_names_path is not None else NAMES_DEFAULT_PATH
    overlay_cache = OverlayCache()  # per-app 實例(impl-spec R9:module-level 跨測試汙染)
    bars_cache = BarsCache()  # 同上;K 線兩段式 cache(server/bars.py)
    capital_ws = WsBroadcaster()  # capital/futures WS fanout(lifespan 綁 publish)
    futures_ws = WsBroadcaster()
    corr_ws = WsBroadcaster()
    river_ws = WsBroadcaster()  # 江波圖每秒 delta(全量走 REST/WS 首則;index-river-chart SC-5)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        # 最先做:引擎起不來時 banner 也要印得出來(「這台是哪一版」是排查的第一個問題)
        app.state.build = build_info.capture()
        logger.info("%s", app.state.build.banner())
        runtime = EngineRuntime(
            source if source is not None else _default_source(),
            throttle_secs=throttle_secs,
            queue_maxsize=queue_maxsize,
            # 固定日回補模式(休市日)停用時段切換偵測:跨界重跑只會重拿同一份
            # 指定日資料(spec R5)
            session_rollover=os.environ.get("TXO_BACKFILL_DATE") is None,
        )
        app.state.runtime = runtime
        await runtime.start()
        # TradeRuntime 停用(deprecated 2026-07-28 群益接手,capital-order SC-11):
        # /api/trade routes 與 _TRADE_ERROR_MAP 保留,state.trade=None → _trade() 的
        # NotReadyError 路徑天然 503 TRADE_NOT_READY;trade_source 參數(含 DEFAULT_TRADE
        # sentinel)不再啟動任何東西,僅剩「正式啟動旗標」語意(futures 接線用,見下);
        # TXO_FAKE_TRADE 分支一併失效。舊路 code(trade.py/tc4_trade.py/fake_trade.py)
        # 保留,刪除候選記 docs/next-time.md。
        app.state.trade = None

        # stock engine:與 TXO runtime 並存;失敗不得波及 quote(同 trade 邊界慣例)
        def _make_stock() -> StockEngine | None:
            resolved_stock = (
                _default_stock_source() if stock_source is DEFAULT_STOCK else stock_source
            )
            if resolved_stock is None:
                return None
            import datetime as _dt

            backfill_date = os.environ.get("TXO_BACKFILL_DATE")
            return StockEngine(
                cast(StockSource, resolved_stock),
                trade_date=backfill_date or f"{_dt.date.today():%Y-%m-%d}",
                throttle_secs=throttle_secs,
                checkpoint=backfill_date is None,
            )

        async def _start_stock(o: StockEngine) -> None:
            await o.start()
            # 自選回填屬於「帶到就緒」的一部分:load_watchlist 對壞檔不吞例外,
            # 現況正是由 _boot 的 except 接住(留在 try 內是行為契約)
            persisted = load_watchlist(wl_path)["codes"]
            if persisted:
                await o.set_watchlist(persisted)

        stock = await _boot(
            "stock",
            "stock engine 初始化非預期失敗,個股功能停用(quote 不受影響)",
            _make_stock,
            _start_stock,
            lambda o: o.close(),
        )
        app.state.stock = stock

        # 自選複合操作(design §6):落檔 + 訂閱池 + 廣播三件事的單一定義,前端 PUT 與
        # Discord `/watch` 共用同一把 lock。**必須先於 signals `_boot`**(impl-review R3):
        # 它是 `_start_signals` closure 的自由變數,順序反了會是 NameError,而 `_boot` 的
        # except 會把它吞成「訊號功能靜默停用」—— 從畫面上只看得到「今天都沒訊號」。
        service = WatchlistService(wl_path, stock) if stock is not None else None
        app.state.watchlist_service = service

        # 訊號引擎(design §4.5):整段套 `_boot` 隔離 —— discord 登入失敗 / 壞自選檔
        # 只讓訊號停用,不波及其他引擎。bot 由 start 建立、close 收攤(成對)。
        bot: Bot | None = None

        def _make_signals() -> SignalHub | None:
            if stock is None:
                return None
            engine = stock
            return SignalHub(
                load_signals_config(),
                publish=engine._publish,
                daily_bars=engine.daily_bars,
                notify_fallback=notify_discord,
                # 自選檔所在目錄 = 本專案的 data 根(`data/stock_watchlist.json`)→
                # jsonl 與開關檔天然跟著它走,測試注入自選路徑即整組落在 tmp_path
                data_dir=wl_path.parent,
                # 日別語意由 engine 單一持有(兩段式 rollover 期間 stage2 才前進)
                trade_date_fn=lambda: engine.trade_date,
            )

        async def _start_signals(hub: SignalHub) -> None:
            nonlocal bot
            await hub.start()
            # membership 種子:沒有這一步,開機後所有 tick 都被 hub 的 membership gate 擋掉
            hub.on_watchlist(load_watchlist(wl_path)["codes"])
            bot = create_bot(service, hub)  # token 未設 / extras 未裝 → None(SC-8 降級)
            if bot is not None:
                bot.start_bg()
                hub.attach_discord(bot.send_signal)
            # **必須是最後一行**(CC-2):attach 之後這個 hub 就在 engine 熱路徑上了,
            # 而 `_boot` 的 except 只會把它 close 掉、不會從 engine 摘下來 —— 提早 attach
            # 再讓後面任何一步拋,留下的是「WS 有訊號、jsonl 與 today 全空」的殭屍。
            if stock is not None:  # `_make_signals` 已保證;narrowing 用
                stock.attach_signal_hub(hub)

        async def _close_signals(hub: SignalHub) -> None:
            # try/finally(CC-1):bot.close 拋(token 失效)不得讓 hub 的 worker 洩漏、
            # 也不得跳過關機盡力落檔
            try:
                if bot is not None:
                    await bot.close()
            finally:
                if stock is not None:
                    stock.detach_signal_hub()  # 先摘掛點:hub 收攤後熱路徑不得再打到它
                await hub.close()

        signals = await _boot(
            "signals",
            "訊號引擎啟動失敗,訊號功能停用(其餘不受影響)",
            _make_signals,
            _start_signals,
            _close_signals,
        )
        app.state.signal_hub = signals
        # 啟動失敗時 `_boot` 已呼叫 `_close_signals`(bot 也收了)→ 不對外暴露死掉的 bot
        app.state.discord_bot = bot if signals is not None else None

        # index engine:失敗不得波及其他引擎(同 trade/stock 邊界慣例)
        def _make_index() -> IndexEngine | None:
            resolved_index = (
                _default_index_source() if index_source is DEFAULT_INDEX else index_source
            )
            if resolved_index is None:
                return None
            import datetime as _dt

            backfill_date = os.environ.get("TXO_BACKFILL_DATE")
            return IndexEngine(
                cast(IndexSource, resolved_index),
                # TXO runtime 現貨轉供(design IR1);runtime 掛掉時恆 None
                txf_getter=runtime.spot_millipts,
                mis_fetch=index_mis_fetch,
                trade_date=backfill_date or f"{_dt.date.today():%Y-%m-%d}",
                rollover=backfill_date is None,
                throttle_secs=throttle_secs,
            )

        index = await _boot(
            "index",
            "index engine 初始化非預期失敗,指數功能停用(其餘不受影響)",
            _make_index,
            lambda o: o.start(),
            lambda o: o.close(),
        )
        app.state.index = index

        # capital(群益下單;capital-order design §13):factory 未設定 → None = disabled;
        # 啟動失敗 catch → None 降級,server 照起(stock/index 同慣例)
        async def _start_capital(c: CapitalClient) -> None:
            loop = asyncio.get_running_loop()

            def _capital_broadcast(payload: dict[str, object]) -> None:
                # COM 執行緒 → loop threadsafe 排入 WS fanout(publish 只能在 loop 上跑)
                loop.call_soon_threadsafe(capital_ws.publish, payload)

            c.set_broadcast(_capital_broadcast)  # 先掛再 start:啟動狀態事件不漏
            c.start(loop)

        capital = await _boot(
            "capital",
            "capital 初始化非預期失敗,群益功能停用(其餘不受影響)",
            capital_factory.get_capital,
            _start_capital,
            lambda c: asyncio.to_thread(c.close),  # COM 執行緒 join 是同步的
        )
        app.state.capital = capital

        # futures 行情引擎(SC-8):__main__ 不改 — 正式啟動(trade_source=DEFAULT_TRADE,
        # TradeRuntime 停用後該 sentinel 僅剩「正式啟動旗標」語意)即建真 source;
        # 測試未傳(None)零連線;顯式 DEFAULT_FUTURES / source 實例亦可
        def _make_futures() -> FuturesEngine | None:
            if futures_source is DEFAULT_FUTURES or (
                futures_source is None and trade_source is DEFAULT_TRADE
            ):
                resolved_futures: FuturesSource | None = _default_futures_source()
            else:
                resolved_futures = cast("FuturesSource | None", futures_source)
            if resolved_futures is None:
                return None
            fut_src = resolved_futures
            return FuturesEngine(lambda: fut_src, broadcast=futures_ws.publish)

        futures = await _boot(
            "futures",
            "futures engine 初始化非預期失敗,期貨行情停用(其餘不受影響)",
            _make_futures,
            lambda o: o.start(),
            lambda o: o.close(),
        )
        app.state.futures = futures

        # 相關係數引擎(realtime-correlation SC-6):必須在 futures 之後建 —— base 腿
        # (台指)直接讀 futures.state(),不自行訂閱 TXF.HOT(同 symbol 跨 session 只推
        # 一邊,CLAUDE.md §8)。futures 掛掉時 getter 回空 dict,base 腿 None、配對全 None。
        def _make_corr() -> CorrelationEngine | None:
            if corr_source is DEFAULT_CORR or (
                corr_source is None and trade_source is DEFAULT_TRADE
            ):
                resolved_corr: CorrSource | None = _default_corr_source()
            else:
                resolved_corr = cast("CorrSource | None", corr_source)
            if resolved_corr is None:
                return None
            corr_src = resolved_corr
            futures_engine = futures
            return CorrelationEngine(
                lambda: corr_src,
                config=load_corr_config(),
                txf_state_getter=(
                    lambda: futures_engine.state() if futures_engine is not None else {}
                ),
                broadcast=corr_ws.publish,
                river_broadcast=river_ws.publish,
                # 台指腿的 1K 必須從持有 TXF 訂閱的 futures session 問(CLAUDE.md §8)
                futures_minutes_fetch=(
                    lambda product: (
                        futures_engine.fetch_day_1k(product) if futures_engine is not None else []
                    )
                ),
            )

        corr = await _boot(
            "corr",
            "corr engine 初始化非預期失敗,相關係數停用(其餘不受影響)",
            _make_corr,
            lambda o: o.start(),
            lambda o: o.close(),
        )
        app.state.corr = corr
        try:
            yield
        finally:
            # 關機反序:signals → corr → futures → capital → index → stock → (trade) → runtime
            # (corr 依賴 futures.state(),必須先收;signals 最前 —— fanout worker 還活著時
            # 對已收攤的 stock engine publish 會炸在關機路徑上)
            if signals is not None:
                try:
                    await _close_signals(signals)  # bot 先於 hub(hub 的 sender 指向 bot)
                except Exception:
                    logger.exception("signals close 失敗(關機續行)")
            if corr is not None:
                try:
                    await corr.close()
                except Exception:
                    logger.exception("corr close 失敗(關機續行)")
            if futures is not None:
                try:
                    await futures.close()
                except Exception:
                    logger.exception("futures close 失敗(關機續行)")
            if capital is not None:
                try:
                    await asyncio.to_thread(capital.close)  # join COM 執行緒(≤5s)
                except Exception:
                    logger.exception("capital close 失敗(關機續行)")
            if index is not None:
                try:
                    await index.close()
                except Exception:
                    logger.exception("index close 失敗(關機續行)")
            if stock is not None:
                try:
                    await stock.close()
                except Exception:
                    logger.exception("stock close 失敗(關機續行)")
            await runtime.close()

    app = FastAPI(lifespan=lifespan)
    origin = os.environ.get("FRONTEND_ORIGIN")
    if origin:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[origin],
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.state.capital_ws = capital_ws
    app.state.futures_ws = futures_ws
    app.state.corr_ws = corr_ws
    app.state.river_ws = river_ws
    register_capital(app)  # capital/futures routes + 例外映射(capital-order design §6)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error on %s", request.url.path, exc_info=exc)
        return JSONResponse(status_code=502, content={"detail": {"error": "TC4_DOWN"}})

    @app.get("/api/health")
    async def health(request: Request) -> dict:
        """執行中 server 的建置身分 —— 「這台是不是舊版」的唯一可視管道。

        用法:`git log <git_sha>..HEAD -- copycat/` 有輸出 = 後端 code 比跑著的新,該重啟。
        刻意不含引擎健康度:那是另一個問題,混進來會讓這條在引擎壞掉時也答不出版本。
        """
        return request.app.state.build.as_dict()

    def _runtime(request: Request) -> EngineRuntime:
        return request.app.state.runtime

    @app.get("/api/txo/series")
    async def list_series(request: Request) -> dict:
        runtime = _runtime(request)
        series = runtime.list_series()
        if not series:
            raise HTTPException(status_code=503, detail={"error": "NOT_READY"})
        return {
            "series": [
                {"series_id": s.series_id, "name": s.name, "expiry": s.expiry} for s in series
            ]
        }

    @app.post("/api/txo/select")
    async def select_series(request: Request, body: SelectBody) -> dict:
        runtime = _runtime(request)
        try:
            await runtime.activate(body.series_id)
        except KeyError:
            raise HTTPException(status_code=400, detail={"error": "UNKNOWN_SERIES"}) from None
        return runtime.latest_snapshot()

    @app.get("/api/txo/contracts")
    async def txo_contracts(request: Request) -> dict:
        """Active 序列全鏈合約(OrderPanel 選單;snapshot.contracts 僅成交子集)。"""
        runtime = _runtime(request)
        symbols = sorted(s for s in runtime.orderable_symbols() if s.startswith("TC.O."))
        return {"contracts": symbols}

    @app.get("/api/txo/snapshot")
    async def snapshot(request: Request) -> dict:
        runtime = _runtime(request)
        snap = runtime.latest_snapshot()
        if snap["series_id"] is None:
            raise HTTPException(status_code=503, detail={"error": "NOT_READY"})
        return snap

    @app.websocket("/ws/txo-pnl")
    async def ws_txo_pnl(websocket: WebSocket) -> None:
        runtime: EngineRuntime = websocket.app.state.runtime
        await websocket.accept()
        try:
            await websocket.send_json(runtime.latest_snapshot())
            await relay(websocket, runtime.snapshots())
        except WebSocketDisconnect:
            return

    # ---- stock(個股看盤;design v4 §2.5)----

    @app.exception_handler(WatchlistError)
    async def _watchlist_error(request: Request, exc: WatchlistError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": {"error": str(exc)}})

    def _stock(request: Request) -> StockEngine:
        stock: StockEngine | None = request.app.state.stock
        if stock is None:
            raise HTTPException(status_code=503, detail={"error": "NOT_READY"})
        return stock

    def _watchlist_service(request: Request) -> WatchlistService:
        _stock(request)  # 引擎未就緒的 503 優先(既有 PUT 行為)
        service: WatchlistService | None = request.app.state.watchlist_service
        if service is None:
            raise HTTPException(status_code=503, detail={"error": "NOT_READY"})
        return service

    def _signals(request: Request) -> SignalHub:
        """訊號 route 的共同閘(design §7):先 `_stock()` 再 hub —— 兩者皆 503 NOT_READY,
        但順序決定「達錢 4 沒開」與「訊號層單獨降級」在 log 上的可分辨性。"""
        _stock(request)
        hub: SignalHub | None = request.app.state.signal_hub
        if hub is None:
            raise HTTPException(status_code=503, detail={"error": "NOT_READY"})
        return hub

    def _valid_code(code: str) -> None:
        """個股代號閘。**必須在 `_stock(request)` 之後呼叫** —— 「引擎沒起來 + 代號非法」
        現況回 503 不是 400,那個優先序是既有行為(做成 Depends 會被 FastAPI 提前跑)。"""
        if not validate_code(code):
            raise HTTPException(status_code=400, detail={"error": "BAD_CODE"})

    @app.get("/api/stock/names")
    async def stock_names() -> dict:
        """全市場代號↔名稱(搜尋提示列用)。**刻意不過 `_stock()` 閘** —— 名稱表與 TC4
        連線無關,達錢 4 沒開時也該能搜尋。表不存在 / 壞檔 → 空陣列(不 500)。"""
        names = load_stock_names(names_path)
        return {
            "names": [{"code": code, "name": name} for code, name in names.items()],
            "count": len(names),
        }

    @app.get("/api/stock/watchlist")
    async def stock_watchlist_get(request: Request) -> dict:
        _stock(request)
        wl = load_watchlist(wl_path)
        return {"codes": wl["codes"], "groups": wl["groups"]}

    @app.put("/api/stock/watchlist")
    async def stock_watchlist_put(request: Request, body: GroupsBody) -> dict:
        """整份取代。**改走 `WatchlistService`**(design §6):落檔 + 訂閱池 + 廣播三件事
        與 Discord `/watch` 共用同一把 lock,兩邊同時改自選不再互相覆蓋。

        對外形狀不變,但**同內容 PUT 現在是 no-op**(🔴):舊碼照樣跑一輪 `set_watchlist`
        對整份名單 UNSUB/SUB,盤中存個檔就讓所有自選股斷訂一次。
        """
        service = _watchlist_service(request)
        groups: list[Group] = [{"name": g.name, "codes": g.codes} for g in body.groups]
        codes = body.codes if body.codes is not None else union(groups)
        saved = await service.apply({"codes": codes, "groups": groups})  # 400 由 handler
        return {"codes": saved["codes"], "groups": saved["groups"]}

    @app.get("/api/stock/overlay/{code}")
    async def stock_overlay(request: Request, code: str) -> dict:
        stock = _stock(request)
        _valid_code(code)
        # today = 本機日界(= 台北,部署綁本機;design R6/R13);backfill 模式亦以本機為準
        today = f"{_date.today():%Y-%m-%d}"
        cached = overlay_cache.get(code, today)
        if cached is not None:
            return cached
        result = build_overlay(await stock.daily_bars(code), today)
        overlay_cache.put(code, today, result)  # 空結果不 cache(overlay.py 規則)
        return result

    @app.get("/api/stock/bars/{code}")
    async def stock_bars(request: Request, code: str, tf: str = "D", days: str = "5") -> dict:
        """K 線 bar(SC-7)。tf=D 忽略 days(D-15:忽略的參數不該進 cache/query key)。"""
        stock = _stock(request)
        _valid_code(code)
        if tf not in ("D", "1"):
            raise HTTPException(status_code=400, detail={"error": "BAD_TF"})
        # today = 本機日界(= 台北,部署綁本機;同 overlay 的 design R6/R13)
        today = _date.today()
        if tf == "D":
            # days 在日線路徑完全不參與(不進 cache/query key,D-15)→ 連驗都不驗:
            # 對忽略的參數回 400 會讓「多帶一個沒用的 query」變成擋下日 K 的理由(M1)
            bars = await build_daily(stock.bars_range, bars_cache, code, today)
        else:
            # days 自行解析:交給 FastAPI 轉 int 時,轉換失敗回的是 422 + list 形 detail,
            # 不符全站 {"detail": {"error": "<code>"}} 契約(W-D3;review P2-6)
            try:
                days_n = int(days)
            except ValueError:
                raise HTTPException(status_code=400, detail={"error": "BAD_DAYS"}) from None
            bars = await build_minute(stock.bars_range, bars_cache, code, clamp_days(days_n), today)
        return {"code": code, "tf": tf, "bars": bars}

    # ---- stock signals(stock-signals design §7)----

    @app.get("/api/stock/signals/today")
    async def stock_signals_today(request: Request) -> dict:
        """當日訊號歷史(SC-7):讀 hub 的 jsonl,壞行跳過。

        前端 reconnect 後拿它當 baseline 自癒 —— WS 斷線期間丟掉的訊號由這裡補回。
        """
        return {"signals": _signals(request).today_signals()}

    @app.get("/api/stock/signals/enabled")
    async def stock_signals_enabled(request: Request) -> dict:
        return {"enabled": _signals(request).enabled()}

    @app.put("/api/stock/signals/enabled")
    async def stock_signals_enabled_put(request: Request, body: SignalsEnabledBody) -> dict:
        """部分更新(只送要改的鍵);回傳合併後的完整四鍵狀態。"""
        hub = _signals(request)
        try:
            # 值型別由 hub 驗(見 SignalsEnabledBody);cast 只是把驗證責任交出去
            await hub.set_enabled(cast("dict[str, bool]", body.enabled))
        except ValueError:
            raise HTTPException(
                status_code=400, detail={"error": "INVALID_SIGNALS_ENABLED"}
            ) from None
        return {"enabled": hub.enabled()}

    @app.get("/api/stock/state/{code}")
    async def stock_state(request: Request, code: str) -> dict:
        stock = _stock(request)
        _valid_code(code)
        await stock.set_main(code)  # 含回補觸發(design §2.5)
        return stock.snapshot(code)

    # ---- index(指數看盤;index-board SC-4)----

    def _index(request: Request) -> IndexEngine:
        index: IndexEngine | None = request.app.state.index
        if index is None:
            raise HTTPException(status_code=503, detail={"error": "NOT_READY"})
        return index

    @app.get("/api/index/state")
    async def index_state(request: Request) -> dict:
        return _index(request).state()

    # ---- market(大盤 K 線;index-board SC-4/5/6)----

    @app.get("/api/market/bars/{key}")
    async def market_bars(request: Request, key: str, tf: str = "D", days: str = "30") -> dict:
        """大盤頁 K 線(index-board N-5)。

        **拒繪走 200 + `meta.refusal`,不用 4xx**:4xx 會被 TanStack Query 的 error 路徑
        吞成同一種紅色,分不出「平台不支援」與「TC4 掛了」—— 而那正是本輪要讓使用者
        五秒內答出來的問題。400/503 只留給「請求本身錯」與「引擎沒起來」。

        分派 = 每個 symbol 都向**持有它 REALTIME 訂閱的那條 session** 問歷史
        (CLAUDE.md §8 同 symbol 跨 session 只推一邊):
        `TWSE` → index 引擎、`TXF/MXF/TMF` → futures 引擎、`OTC` → 本機合成(無 TC4 來源)。
        """
        if key not in MARKET_KEYS:
            raise HTTPException(status_code=400, detail={"error": "BAD_KEY"})
        if tf not in ("1", "D", "W", "M"):
            raise HTTPException(status_code=400, detail={"error": "BAD_TF"})
        try:
            days_n = clamp_days(int(days))
        except ValueError:
            raise HTTPException(status_code=400, detail={"error": "BAD_DAYS"}) from None
        today = _date.today()

        if key == "OTC":
            index = _index(request)
            if tf != "1":
                # 櫃買指數不在 TC4 symbol 樹(CLAUDE.md §8 掃盡確認)→ 沒有任何歷史來源。
                # 給空陣列 + 明確理由,不拿當日合成假裝成日/週/月 K。
                return _market_payload(key, tf, [], source="none", refusal="NO_HISTORICAL_SOURCE")
            bars, since = index.otc_bars()
            return _market_payload(
                key,
                tf,
                bars,
                source="mis_poll_synth",
                volume=False,
                synth_since=since,
                partial_last=is_partial_last(bars, tf, today),
            )

        if key == "TWSE":
            index = _index(request)

            async def tagged(_c: str, tf_: str, s: str, e: str) -> tuple[list[Bar], str]:
                return await index.bars_range(tf_, s, e)
        else:
            futures: FuturesEngine | None = request.app.state.futures
            if futures is None:
                raise HTTPException(status_code=503, detail={"error": "NOT_READY"})

            async def tagged(_c: str, tf_: str, s: str, e: str) -> tuple[list[Bar], str]:
                # 期指沒有 DK→1K 的 fallback 分支,tag 恆定;回空 = 借不到(engine 已 log)
                got = await futures.bars_range(key, tf_, s, e)
                return got, ("tc4_dk" if got else "unavailable")

        async def plain(c: str, tf_: str, s: str, e: str) -> list[Bar]:
            return (await tagged(c, tf_, s, e))[0]

        # 分鐘路徑的 cache code 加 |M 後綴:裸 "IX0001" 會與 /api/stock/bars/IX0001
        # (走 **stock** session)共用 `_hist` / `_today` / `_empty` 同一格 —— 那會讓
        # W-12「歷史一律從持有其 REALTIME 訂閱的 session 問」在快取層被繞過(review P1-6)。
        # 長窗路徑的 |L 後綴同理(review P2-1)。期指的 F: 前綴含冒號,本來就撞不到。
        code = ("IX0001|M" if tf == "1" else "IX0001") if key == "TWSE" else f"F:{key}"
        if tf == "1":
            bars = await build_minute(plain, bars_cache, code, days_n, today)
            return _market_payload(
                key,
                tf,
                bars,
                source="tc4_1k" if bars else "unavailable",
                partial_last=is_partial_last(bars, tf, today),
            )
        bars, tag = await build_period(tagged, bars_cache, code, today, tf)
        return _market_payload(
            key, tf, bars, source=tag, partial_last=is_partial_last(bars, tf, today)
        )

    @app.get("/api/corr/state")
    async def corr_state(request: Request) -> dict:
        corr: CorrelationEngine | None = request.app.state.corr
        if corr is None:
            raise HTTPException(status_code=503, detail={"error": "CORR_NOT_READY"})
        return corr.state()

    @app.websocket("/ws/corr")
    async def ws_corr(websocket: WebSocket) -> None:
        corr: CorrelationEngine | None = websocket.app.state.corr
        await websocket.accept()
        if corr is None:
            await websocket.close()
            return
        try:
            # 先送當前快照:client 不必等到下一個 tick 才有畫面
            await websocket.send_json(corr.state())
            await relay(websocket, corr_ws.stream())
        except WebSocketDisconnect:
            return

    # ---- river(六腿江波圖;index-river-chart SC-5)----

    @app.get("/api/river/state")
    async def river_state(request: Request) -> dict:
        corr: CorrelationEngine | None = request.app.state.corr
        if corr is None:
            raise HTTPException(status_code=503, detail={"error": "RIVER_NOT_READY"})
        return corr.river_snapshot()

    @app.websocket("/ws/river")
    async def ws_river(websocket: WebSocket) -> None:
        corr: CorrelationEngine | None = websocket.app.state.corr
        await websocket.accept()
        if corr is None:
            await websocket.close()
            return
        try:
            # 首則送全量 snapshot;之後每秒只送當前分鐘的 delta(全量每秒推 = 每分鐘數 MB)
            await websocket.send_json(corr.river_snapshot())
            await relay(websocket, river_ws.stream())
        except WebSocketDisconnect:
            return

    @app.websocket("/ws/index")
    async def ws_index(websocket: WebSocket) -> None:
        index: IndexEngine | None = websocket.app.state.index
        await websocket.accept()
        if index is None:
            await websocket.close()
            return
        try:
            await relay(websocket, index.stream())
        except WebSocketDisconnect:
            return

    @app.websocket("/ws/stock")
    async def ws_stock(websocket: WebSocket) -> None:
        stock: StockEngine | None = websocket.app.state.stock
        await websocket.accept()
        if stock is None:
            await websocket.close()
            return
        try:
            await relay(websocket, stock.stream())
        except WebSocketDisconnect:
            return

    # ---- trade(§7 三道閘;錯誤分流 design §2.3/§2.5) ----

    _TRADE_ERROR_MAP: dict[type[Exception], tuple[int, str]] = {
        TouchanceDownError: (502, "TOUCHANCE_DOWN"),
        NotReadyError: (503, "TRADE_NOT_READY"),
        LiveBlockedError: (403, "LIVE_DISABLED"),
        ConfirmRequiredError: (400, "CONFIRM_REQUIRED"),
        PreviewExpiredError: (400, "PREVIEW_EXPIRED"),
        InvalidOrderError: (400, "INVALID_ORDER"),
        SymbolNotAllowedError: (400, "SYMBOL_NOT_ALLOWED"),
        AuditWriteError: (500, "AUDIT_WRITE_FAILED"),
    }

    for exc_type, (status_code, code) in _TRADE_ERROR_MAP.items():

        def _make_handler(sc: int, error_code: str):  # noqa: ANN202 - closure factory
            async def _handler(request: Request, exc: Exception) -> JSONResponse:
                return JSONResponse(status_code=sc, content={"detail": {"error": error_code}})

            return _handler

        app.add_exception_handler(exc_type, _make_handler(status_code, code))

    @app.exception_handler(BrokerRejectedError)
    async def _broker_rejected(request: Request, exc: BrokerRejectedError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "detail": {
                    "error": "BROKER_REJECTED",
                    "err_code": exc.err_code,
                    "err_msg": exc.err_msg,
                }
            },
        )

    def _trade(request: Request) -> TradeRuntime:
        trade: TradeRuntime | None = request.app.state.trade
        if trade is None:
            raise NotReadyError("trade source not configured")
        return trade

    @app.get("/api/trade/account")
    async def trade_account(request: Request) -> dict:
        return _trade(request).account_view()

    @app.post("/api/trade/preview")
    async def trade_preview(request: Request, body: PreviewBody) -> dict:
        trade = _trade(request)
        price_millipts: int | None = None
        if body.kind == "limit":
            if body.price is None:
                raise InvalidOrderError("limit order requires price")
            try:
                price_millipts = millipts_from_price_str(body.price)
            except ValueError:
                raise InvalidOrderError(f"invalid price: {body.price!r}") from None
        req = OrderRequest(
            symbol=body.symbol,
            side=body.side,
            kind=body.kind,
            qty=body.qty,
            price_millipts=price_millipts,
        )
        return await trade.preview(req)

    @app.post("/api/trade/orders")
    async def trade_submit(request: Request, body: SubmitBody) -> dict:
        return await _trade(request).submit(body.preview_id)

    @app.get("/api/trade/orders")
    async def trade_orders(request: Request) -> dict:
        return _trade(request).orders_view()

    return app
