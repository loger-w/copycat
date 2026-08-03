"""群益 capital routes + WS 廣播 + futures 行情 REST/WS(design §6/§10;SC-2/3/4/5/6/8)。

- APIRouter 掛 /api/capital/*、/ws/capital,futures 行情 /api/futures/state、/ws/futures
  就近同檔註冊(review R3;吃 app.state.futures)。
- pydantic body 只在 server 層,進 runtime 前轉 dataclass(capital/ stdlib-only 分界)。
- 例外映射由 register_capital 顯式註冊:未註冊的例外會被 app.py 全域 handler 吞成
  502 TC4_DOWN,故群益四類全部顯式列出;AuditWriteError/BrokerRejectedError 沿用
  app.py 既有 handler。
- ValueError(symbol/乘數解析)只在 route 邊界 catch → 400 INVALID_ORDER —— 不可
  全域註冊 ValueError handler,會攔走其他 route 的 ValueError。
- WsBroadcaster:loop-context fanout(index_engine per-client 有界 queue 同款)。
  futures engine 的 broadcast 已在 loop 上(call_soon_threadsafe 進來)可直掛 publish;
  capital 推播來自 COM 執行緒,由 app.py 以 loop.call_soon_threadsafe 包裝後注入。
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from copycat.capital.client import CapitalClient
from copycat.capital.mapping import multiplier_of, product_of, to_exchange_symbol
from copycat.capital.models import (
    CancelOrderRequest,
    CapitalDisabledError,
    CapitalDownError,
    CapitalGateBlockedError,
    CapitalNotReadyError,
    CorrectPriceRequest,
    DecreaseQtyRequest,
    FutureOrderRequest,
    PositionCloseRequest,
    StockOrderRequest,
)
from copycat.server.futures_engine import FuturesEngine
from copycat.server.ws import WsBroadcaster

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# request body(server 層 pydantic → runtime dataclass)
# ---------------------------------------------------------------------------

_BuySell = Literal["buy", "sell"]
_PriceType = Literal["limit", "market"]
_Tif = Literal["ROD", "IOC", "FOK"]
_Market = Literal["sec", "fut"]


class StockOrderBody(BaseModel):
    stock_no: str
    buy_sell: _BuySell
    price: float
    qty: int
    price_type: _PriceType = "limit"
    time_in_force: _Tif = "ROD"
    trade_kind: Literal["cash", "margin", "short", "daytrade_sell"] = "cash"
    source: str = "panel"


class FutureOrderBody(BaseModel):
    tc4_symbol: str
    buy_sell: _BuySell
    price: float
    qty: int
    price_type: _PriceType = "limit"
    time_in_force: _Tif = "ROD"
    day_trade: bool = False
    source: str = "panel"


class CancelBody(BaseModel):
    seq_no: str
    market: _Market


class CorrectPriceBody(BaseModel):
    seq_no: str
    market: _Market
    price: float


class DecreaseBody(BaseModel):
    seq_no: str
    market: _Market
    qty: int


class PositionCloseBody(BaseModel):
    market: _Market
    key: str
    price: float  # 閘用估價,市價單也必帶(review R1)
    qty: int | None = None
    price_type: _PriceType = "market"
    source: str = "panel"


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------

router = APIRouter()


def _capital(request: Request) -> CapitalClient:
    client: CapitalClient | None = request.app.state.capital
    if client is None:
        raise CapitalDisabledError("群益下單未啟用(CAPITAL_USER_ID 未設定)")
    return client


def _invalid_order() -> HTTPException:
    return HTTPException(status_code=400, detail={"error": "INVALID_ORDER"})


@router.get("/api/capital/status")
async def capital_status(request: Request) -> dict:
    client: CapitalClient | None = request.app.state.capital
    if client is None:
        return {"status": "disabled"}  # 未啟用是常態組態,不是錯誤(200 不 raise)
    return client.status_view()


@router.get("/api/capital/orders")
async def capital_orders(request: Request) -> dict:
    client = _capital(request)
    return {"orders": [dataclasses.asdict(o) for o in client.store.orders()]}


@router.get("/api/capital/positions")
async def capital_positions(request: Request) -> dict:
    client = _capital(request)
    return {"positions": [dataclasses.asdict(p) for p in client.store.positions()]}


@router.post("/api/capital/order/stock")
async def capital_order_stock(request: Request, body: StockOrderBody) -> dict:
    client = _capital(request)
    req = StockOrderRequest(
        stock_no=body.stock_no,
        buy_sell=body.buy_sell,
        price=body.price,
        qty=body.qty,
        price_type=body.price_type,
        time_in_force=body.time_in_force,
        trade_kind=body.trade_kind,
        source=body.source,
    )
    return dataclasses.asdict(await client.submit_stock_order(req))


@router.post("/api/capital/order/future")
async def capital_order_future(request: Request, body: FutureOrderBody) -> dict:
    client = _capital(request)
    req = FutureOrderRequest(
        tc4_symbol=body.tc4_symbol,
        buy_sell=body.buy_sell,
        price=body.price,
        qty=body.qty,
        price_type=body.price_type,
        time_in_force=body.time_in_force,
        day_trade=body.day_trade,
        source=body.source,
    )
    # product → 乘數 → HOT 解析 → 期交所契約碼(任一步 ValueError = 拒單,不猜月份)
    try:
        product = product_of(req.tc4_symbol)
        multiplier = multiplier_of(product)
        futures: FuturesEngine | None = request.app.state.futures
        resolved = futures.resolved_contract(product) if futures is not None else None
        contract = to_exchange_symbol(req.tc4_symbol, resolved_ym=resolved)
    except ValueError as exc:
        logger.info("order/future 符號解析拒單: %s", exc)
        raise _invalid_order() from None
    result = await client.submit_future_order(req, contract=contract, multiplier=multiplier)
    return dataclasses.asdict(result)


@router.post("/api/capital/order/cancel")
async def capital_order_cancel(request: Request, body: CancelBody) -> dict:
    client = _capital(request)
    result = await client.cancel_order(CancelOrderRequest(seq_no=body.seq_no, market=body.market))
    return dataclasses.asdict(result)


@router.post("/api/capital/order/correct-price")
async def capital_order_correct_price(request: Request, body: CorrectPriceBody) -> dict:
    client = _capital(request)
    result = await client.correct_price(
        CorrectPriceRequest(seq_no=body.seq_no, market=body.market, price=body.price)
    )
    return dataclasses.asdict(result)


@router.post("/api/capital/order/decrease")
async def capital_order_decrease(request: Request, body: DecreaseBody) -> dict:
    client = _capital(request)
    result = await client.decrease_qty(
        DecreaseQtyRequest(seq_no=body.seq_no, market=body.market, qty=body.qty)
    )
    return dataclasses.asdict(result)


@router.post("/api/capital/position/close")
async def capital_position_close(request: Request, body: PositionCloseBody) -> dict:
    client = _capital(request)
    req = PositionCloseRequest(
        market=body.market,
        key=body.key,
        price=body.price,
        qty=body.qty,
        price_type=body.price_type,
        source=body.source,
    )
    return dataclasses.asdict(await client.close_position(req))


def _consume_ws_task(task: "asyncio.Task[None]") -> None:
    """被取消的 send/recv 任務收尾:消費例外避免 unretrieved warning;
    task 取消同時會關閉 stream() generator → 該 client queue 除名。"""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None and not isinstance(exc, WebSocketDisconnect):
        logger.warning("ws 任務收尾例外(已忽略): %r", exc)


async def _stream_to_ws(websocket: WebSocket, broadcaster: WsBroadcaster) -> None:
    """broadcast → WS 送出,並行 receive 偵測 client 斷線(review B3)。

    無推播流量時 send 側永遠掛在 queue.get,察覺不到 client 斷線 →
    per-client queue 洩漏;receive task 在斷線時 raise WebSocketDisconnect 收尾。
    收尾路徑只做同步 cancel(不 await 子任務):endpoint 本身可能被外層
    cancel scope 取消(TestClient / server shutdown),收尾中再 await 會吸收
    重投的取消訊號,讓 task 以 cancelled 終結。
    """

    async def _send() -> None:
        async for msg in broadcaster.stream():
            await websocket.send_json(msg)

    async def _recv() -> None:
        while True:
            await websocket.receive_text()  # client 訊息忽略;斷線 raise 收尾

    send_task = asyncio.ensure_future(_send())
    recv_task = asyncio.ensure_future(_recv())
    done: set[asyncio.Task[None]] = set()
    try:
        done, _pending = await asyncio.wait(
            {send_task, recv_task}, return_when=asyncio.FIRST_COMPLETED
        )
    finally:
        for t in (send_task, recv_task):
            if not t.done():
                t.cancel()
                t.add_done_callback(_consume_ws_task)
    for t in done:
        if not t.cancelled():
            exc = t.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect):
                raise exc


@router.websocket("/ws/capital")
async def ws_capital(websocket: WebSocket) -> None:
    client: CapitalClient | None = websocket.app.state.capital
    await websocket.accept()
    if client is None:
        await websocket.close()
        return
    broadcaster: WsBroadcaster = websocket.app.state.capital_ws
    await _stream_to_ws(websocket, broadcaster)


# ---- futures 行情(SC-8;吃 app.state.futures)----


@router.get("/api/futures/state")
async def futures_state(request: Request) -> dict:
    futures: FuturesEngine | None = request.app.state.futures
    if futures is None:
        raise HTTPException(status_code=503, detail={"error": "NOT_READY"})
    return futures.state()


@router.websocket("/ws/futures")
async def ws_futures(websocket: WebSocket) -> None:
    futures: FuturesEngine | None = websocket.app.state.futures
    await websocket.accept()
    if futures is None:
        await websocket.close()
        return
    broadcaster: WsBroadcaster = websocket.app.state.futures_ws
    await _stream_to_ws(websocket, broadcaster)


# ---------------------------------------------------------------------------
# 例外映射註冊(design §6 全表)
# ---------------------------------------------------------------------------

_CAPITAL_ERROR_MAP: dict[type[Exception], tuple[int, str]] = {
    CapitalDisabledError: (503, "CAPITAL_DISABLED"),
    CapitalNotReadyError: (503, "CAPITAL_NOT_READY"),
    CapitalDownError: (502, "CAPITAL_DOWN"),
}


def register_capital(app: FastAPI) -> None:
    """掛 capital/futures router + 顯式註冊群益例外映射。

    AuditWriteError(500 AUDIT_WRITE_FAILED)與 BrokerRejectedError(400)沿用
    app.py 既有 handler,不重複註冊。
    """
    app.include_router(router)

    for exc_type, (status_code, code) in _CAPITAL_ERROR_MAP.items():

        def _make_handler(sc: int, error_code: str):  # noqa: ANN202 - closure factory(app.py 同款)
            async def _handler(request: Request, exc: Exception) -> JSONResponse:
                return JSONResponse(status_code=sc, content={"detail": {"error": error_code}})

            return _handler

        app.add_exception_handler(exc_type, _make_handler(status_code, code))

    @app.exception_handler(CapitalGateBlockedError)
    async def _gate_blocked(request: Request, exc: CapitalGateBlockedError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"detail": {"error": "ORDER_BLOCKED", "reason": exc.reason}},
        )
