"""FastAPI app:route 只 raise 不 catch;error contract {"detail": {"error": code}}(§2)。"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import date as _date
from pathlib import Path
from typing import AsyncGenerator, Callable, Final, Literal, cast

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
from copycat.server.audit import AuditWriteError
from copycat.server.capital_api import WsBroadcaster, register_capital
from copycat.server.engine import EngineRuntime, QuoteSource
from copycat.server.futures_engine import FuturesEngine, FuturesSource
from copycat.server.index_engine import IndexEngine, IndexSource
from copycat.server.mis import OtcSnap, fetch_otc_snapshot
from copycat.server.overlay import OverlayCache, build_overlay
from copycat.server.stock_engine import StockEngine, StockSource
from copycat.stock_watchlist import (
    Group,
    WatchlistError,
    load_watchlist_groups,
    save_watchlist_groups,
    union,
    validate_code,
)
from copycat.stock_watchlist import DEFAULT_PATH as WATCHLIST_DEFAULT_PATH
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

# sentinel:__main__ 傳 DEFAULT_TRADE = 正式啟動旗標(TradeRuntime 已停用,SC-11;
# 現僅用於 futures 行情引擎的預設接線 — __main__ 不動,lifespan 見 futures 段)
DEFAULT_TRADE: Final = object()
DEFAULT_STOCK: Final = object()  # 同語意:__main__ 傳入才建真 StockQuoteSource
DEFAULT_INDEX: Final = object()  # 同語意(index-board IR9)
DEFAULT_FUTURES: Final = object()  # 同語意(capital-order SC-8)


class SelectBody(BaseModel):
    series_id: str


class GroupBody(BaseModel):
    name: str
    codes: list[str]


class GroupsBody(BaseModel):
    groups: list[GroupBody]


class PreviewBody(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    kind: Literal["limit", "market"]
    qty: int
    price: str | None = None


class SubmitBody(BaseModel):
    preview_id: str


def _default_source() -> QuoteSource:
    from copycat.live.tc4 import TC4QuoteSource  # 延遲 import:測試不觸 pyzmq/TC4

    return TC4QuoteSource(
        port=os.environ.get("TC4_PORT", "50774"),
        backfill_date=os.environ.get("TXO_BACKFILL_DATE"),
    )


def _default_stock_source() -> StockSource:
    from copycat.live.stock_source import StockQuoteSource  # 延遲 import:測試不觸 pyzmq

    return StockQuoteSource(port=os.environ.get("TC4_PORT", "50774"))


def _default_index_source() -> IndexSource:
    from copycat.live.stock_source import StockQuoteSource  # 獨立 session(指數專用)

    return StockQuoteSource(port=os.environ.get("TC4_PORT", "50774"))


def _default_futures_source() -> FuturesSource:
    from copycat.live.futures_source import FuturesQuoteSource  # 延遲 import:測試不觸 pyzmq

    return FuturesQuoteSource(port=os.environ.get("TC4_PORT", "50774"))


def create_app(
    source: QuoteSource | None = None,
    *,
    trade_source: TradeSource | object | None = None,
    stock_source: StockSource | object | None = None,
    index_source: IndexSource | object | None = None,
    futures_source: FuturesSource | object | None = None,
    index_mis_fetch: Callable[[], OtcSnap | None] = fetch_otc_snapshot,
    stock_watchlist_path: Path | None = None,
    throttle_secs: float = 1.0,
    queue_maxsize: int = 10_000,
) -> FastAPI:
    wl_path = stock_watchlist_path if stock_watchlist_path is not None else WATCHLIST_DEFAULT_PATH
    overlay_cache = OverlayCache()  # per-app 實例(impl-spec R9:module-level 跨測試汙染)
    capital_ws = WsBroadcaster()  # capital/futures WS fanout(lifespan 綁 publish)
    futures_ws = WsBroadcaster()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
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
        stock: StockEngine | None = None
        try:
            resolved_stock = (
                _default_stock_source() if stock_source is DEFAULT_STOCK else stock_source
            )
            if resolved_stock is not None:
                import datetime as _dt

                backfill_date = os.environ.get("TXO_BACKFILL_DATE")
                stock = StockEngine(
                    cast(StockSource, resolved_stock),
                    trade_date=backfill_date or f"{_dt.date.today():%Y-%m-%d}",
                    throttle_secs=throttle_secs,
                    checkpoint=backfill_date is None,
                )
                await stock.start()
                persisted = union(load_watchlist_groups(wl_path))
                if persisted:
                    await stock.set_watchlist(persisted)
        except Exception:
            logger.exception("stock engine 初始化非預期失敗,個股功能停用(quote 不受影響)")
            if stock is not None:
                try:
                    await stock.close()
                except Exception:
                    logger.exception("stock close 失敗(忽略)")
            stock = None
        app.state.stock = stock
        # index engine:失敗不得波及其他引擎(同 trade/stock 邊界慣例)
        index: IndexEngine | None = None
        try:
            resolved_index = (
                _default_index_source() if index_source is DEFAULT_INDEX else index_source
            )
            if resolved_index is not None:
                import datetime as _dt

                backfill_date = os.environ.get("TXO_BACKFILL_DATE")
                index = IndexEngine(
                    cast(IndexSource, resolved_index),
                    # TXO runtime 現貨轉供(design IR1);runtime 掛掉時恆 None
                    txf_getter=runtime.spot_millipts,
                    mis_fetch=index_mis_fetch,
                    trade_date=backfill_date or f"{_dt.date.today():%Y-%m-%d}",
                    rollover=backfill_date is None,
                    throttle_secs=throttle_secs,
                )
                await index.start()
        except Exception:
            logger.exception("index engine 初始化非預期失敗,指數功能停用(其餘不受影響)")
            if index is not None:
                try:
                    await index.close()
                except Exception:
                    logger.exception("index close 失敗(忽略)")
            index = None
        app.state.index = index
        # capital(群益下單;capital-order design §13):factory 未設定 → None = disabled;
        # 啟動失敗 catch → None 降級,server 照起(stock/index 同慣例)
        capital: CapitalClient | None = None
        try:
            capital = capital_factory.get_capital()
            if capital is not None:
                loop = asyncio.get_running_loop()

                def _capital_broadcast(payload: dict[str, object]) -> None:
                    # COM 執行緒 → loop threadsafe 排入 WS fanout(publish 只能在 loop 上跑)
                    loop.call_soon_threadsafe(capital_ws.publish, payload)

                capital.set_broadcast(_capital_broadcast)  # 先掛再 start:啟動狀態事件不漏
                capital.start(loop)
        except Exception:
            logger.exception("capital 初始化非預期失敗,群益功能停用(其餘不受影響)")
            if capital is not None:
                try:
                    await asyncio.to_thread(capital.close)
                except Exception:
                    logger.exception("capital close 失敗(忽略)")
            capital = None
        app.state.capital = capital
        # futures 行情引擎(SC-8):__main__ 不改 — 正式啟動(trade_source=DEFAULT_TRADE,
        # TradeRuntime 停用後該 sentinel 僅剩「正式啟動旗標」語意)即建真 source;
        # 測試未傳(None)零連線;顯式 DEFAULT_FUTURES / source 實例亦可
        futures: FuturesEngine | None = None
        try:
            if futures_source is DEFAULT_FUTURES or (
                futures_source is None and trade_source is DEFAULT_TRADE
            ):
                resolved_futures: FuturesSource | None = _default_futures_source()
            else:
                resolved_futures = cast("FuturesSource | None", futures_source)
            if resolved_futures is not None:
                fut_src = resolved_futures
                futures = FuturesEngine(lambda: fut_src, broadcast=futures_ws.publish)
                await futures.start()
        except Exception:
            logger.exception("futures engine 初始化非預期失敗,期貨行情停用(其餘不受影響)")
            if futures is not None:
                try:
                    await futures.close()
                except Exception:
                    logger.exception("futures close 失敗(忽略)")
            futures = None
        app.state.futures = futures
        try:
            yield
        finally:
            # 關機反序:futures → capital → index → stock → (trade) → runtime
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
    register_capital(app)  # capital/futures routes + 例外映射(capital-order design §6)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error on %s", request.url.path, exc_info=exc)
        return JSONResponse(status_code=502, content={"detail": {"error": "TC4_DOWN"}})

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
            async for snap in runtime.snapshots():
                await websocket.send_json(snap)
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

    @app.get("/api/stock/watchlist")
    async def stock_watchlist_get(request: Request) -> dict:
        _stock(request)
        return {"groups": load_watchlist_groups(wl_path)}

    @app.put("/api/stock/watchlist")
    async def stock_watchlist_put(request: Request, body: GroupsBody) -> dict:
        stock = _stock(request)
        groups: list[Group] = [{"name": g.name, "codes": g.codes} for g in body.groups]
        saved = save_watchlist_groups(wl_path, groups)  # WatchlistError → 400(handler)
        await stock.set_watchlist(union(saved))
        return {"groups": saved}

    @app.get("/api/stock/overlay/{code}")
    async def stock_overlay(request: Request, code: str) -> dict:
        stock = _stock(request)
        if not validate_code(code):
            raise HTTPException(status_code=400, detail={"error": "BAD_CODE"})
        # today = 本機日界(= 台北,部署綁本機;design R6/R13);backfill 模式亦以本機為準
        today = f"{_date.today():%Y-%m-%d}"
        cached = overlay_cache.get(code, today)
        if cached is not None:
            return cached
        result = build_overlay(await stock.daily_bars(code), today)
        overlay_cache.put(code, today, result)  # 空結果不 cache(overlay.py 規則)
        return result

    @app.get("/api/stock/state/{code}")
    async def stock_state(request: Request, code: str) -> dict:
        stock = _stock(request)
        if not validate_code(code):
            raise HTTPException(status_code=400, detail={"error": "BAD_CODE"})
        await stock.set_main(code)  # 含回補觸發(design §2.5)
        return stock.snapshot(code)

    # ---- index(指數看盤;index-board SC-4)----

    @app.get("/api/index/state")
    async def index_state(request: Request) -> dict:
        index: IndexEngine | None = request.app.state.index
        if index is None:
            raise HTTPException(status_code=503, detail={"error": "NOT_READY"})
        return index.state()

    @app.websocket("/ws/index")
    async def ws_index(websocket: WebSocket) -> None:
        index: IndexEngine | None = websocket.app.state.index
        await websocket.accept()
        if index is None:
            await websocket.close()
            return
        try:
            async for msg in index.stream():
                await websocket.send_json(msg)
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
            async for msg in stock.stream():
                await websocket.send_json(msg)
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
