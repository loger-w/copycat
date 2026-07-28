"""FastAPI app:route 只 raise 不 catch;error contract {"detail": {"error": code}}(§2)。"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Final, Literal, cast

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
from copycat.server.audit import AuditWriteError
from copycat.server.engine import EngineRuntime, QuoteSource
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

# sentinel:trade_source=None = 不建 trade(既有測試零連線);__main__ 傳 DEFAULT_TRADE 才建真 source
DEFAULT_TRADE: Final = object()
DEFAULT_STOCK: Final = object()  # 同語意:__main__ 傳入才建真 StockQuoteSource

_TRADE_START_TIMEOUT_SECS = 15.0


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


def _default_trade_source() -> TradeSource:
    if os.environ.get("TXO_FAKE_TRADE") == "1":
        from copycat.server.fake_trade import FakeTradeSource

        return FakeTradeSource()
    from copycat.live.tc4_trade import TC4TradeSource  # 延遲 import:測試不觸 pyzmq/TC4

    return TC4TradeSource(port=os.environ.get("TC4_TRADE_PORT", "51207"))


def _default_stock_source() -> StockSource:
    from copycat.live.stock_source import StockQuoteSource  # 延遲 import:測試不觸 pyzmq

    return StockQuoteSource(port=os.environ.get("TC4_PORT", "50774"))


def create_app(
    source: QuoteSource | None = None,
    *,
    trade_source: TradeSource | object | None = None,
    stock_source: StockSource | object | None = None,
    stock_watchlist_path: Path | None = None,
    throttle_secs: float = 1.0,
    queue_maxsize: int = 10_000,
) -> FastAPI:
    wl_path = stock_watchlist_path if stock_watchlist_path is not None else WATCHLIST_DEFAULT_PATH

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
        # trade 初始化任何失敗都不得波及 quote(review B1):非預期例外 → 交易停用(503)
        trade: TradeRuntime | None = None
        try:
            resolved = _default_trade_source() if trade_source is DEFAULT_TRADE else trade_source
            if resolved is not None:
                trade = TradeRuntime(
                    cast(TradeSource, resolved),
                    live_enabled=os.environ.get("DQ4_LIVE") == "1",
                    sim_patterns=[
                        p for p in os.environ.get("DQ4_SIM_BROKERS", "SIM").split(",") if p
                    ],
                    audit_dir=Path(os.environ.get("TXO_AUDIT_DIR", "data/audit")),
                    allowed_symbols=runtime.orderable_symbols,
                )
                try:
                    await asyncio.wait_for(trade.start(), _TRADE_START_TIMEOUT_SECS)
                except (TimeoutError, TouchanceDownError):
                    # R2-7:中段逾時 best-effort 清理 listener;app 照常起,quote 不受影響
                    logger.warning("trade start 逾時/失敗,best-effort 清理後以 touchance_down 續行")
                    try:
                        await trade.close()
                    except (TouchanceDownError, OSError):
                        logger.exception("trade close 失敗(忽略)")
        except Exception:  # lifespan 邊界:交易停用但 app 必須照常起 + logger.exception(§2)
            logger.exception("trade 初始化非預期失敗,交易功能停用(quote 不受影響)")
            if trade is not None:
                try:
                    await trade.close()
                except Exception:
                    logger.exception("trade close 失敗(忽略)")
            trade = None
        app.state.trade = trade
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
        try:
            yield
        finally:
            if stock is not None:
                try:
                    await stock.close()
                except Exception:
                    logger.exception("stock close 失敗(關機續行)")
            # trade 清理失敗不得擋掉 quote runtime 清理(review B2)
            if trade is not None:
                try:
                    await trade.close()
                except Exception:
                    logger.exception("trade close 失敗(關機續行)")
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

    @app.get("/api/stock/state/{code}")
    async def stock_state(request: Request, code: str) -> dict:
        stock = _stock(request)
        if not validate_code(code):
            raise HTTPException(status_code=400, detail={"error": "BAD_CODE"})
        await stock.set_main(code)  # 含回補觸發(design §2.5)
        return stock.snapshot(code)

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
