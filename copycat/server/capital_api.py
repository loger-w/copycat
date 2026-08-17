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

import dataclasses
import logging
from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from copycat.capital.client import CapitalClient
from copycat.capital.mapping import (
    exchange_product_of,
    multiplier_of,
    product_of,
    stock_code_of,
    to_exchange_symbol,
)
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
    PositionKind,
    StockOrderRequest,
)
from copycat.market import tick_size_milli
from copycat.server.futures_engine import FuturesEngine
from copycat.stkfut_map import lookup_product
from copycat.server.ws import WsBroadcaster, relay

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
    # sec 庫存種類;未帶 = 同檔唯一列才成立。列舉不是自由字串:錯值在 wire 層 422,
    # 否則會降級成誤導的 403「無部位可平」(查不到是因為拼錯,不是因為沒庫存)
    kind: PositionKind | None = None


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


#: 期交所股票期貨規格:標準 2,000 股 / 小型 100 股。ETF 期貨(10,000 受益權單位)與
#: 除權息調整後的非標準單位(如 2,157)本輪一律不開放下單(design SC-6 / Known Risks)。
_STOCK_FUTURE_UNITS: dict[str, int] = {"std": 2000, "mini": 100}


def _require_legal_tick(price: float, *, context: str) -> None:
    """個股期限價檔位閘:非現股 tick 表合法檔位 → 400 `BAD_TICK`。

    送單(`_stkfut_gates`)與改價 route 共用的**單一定義** —— 兩處各寫一份規則,
    漂移後的失效樣態是「送不出去的價改得進去」(或反過來),而兩邊都不會有錯誤訊號。
    """
    price_milli = round(price * 1000)
    if price_milli <= 0 or price_milli % tick_size_milli(price_milli) != 0:
        logger.info("%s 非法檔位:@%s", context, price)
        raise HTTPException(status_code=400, detail={"error": "BAD_TICK"})


def _is_tickable_stkfut(stkfut: dict) -> bool:
    """該個股期是否為標準/小型腿(= 唯一適用現股 tick 表的一群)。

    送單面與改價面共用的**單一判準**:送單面以此擋單(不開放的產品),改價面以此
    決定驗不驗檔位 —— 兩處各寫一份的話,失效樣態是「送單面根本走不到 tick 檢查的
    產品,改價面卻拿現股表擋它」(ETF 期貨 60.05 是 ETF 制度上的合法檔位)。
    """
    return stkfut.get("unit") == _STOCK_FUTURE_UNITS.get(str(stkfut.get("kind")))


def _stkfut_gates(product: str, req: FutureOrderRequest) -> None:
    """個股期送單的兩道閘(stkfut-contracts SC-6);非個股期產品直接放行。

    - 非股票契約單位 → `PRODUCT_NOT_ALLOWED`
    - limit 單價格非現股 tick 表合法檔位 → `BAD_TICK`(**market 單跳過**:
      `bstrPrice="M"`,body 的 price 欄不參與送單,拿它驗檔位會擋掉合法的市價單)
    """
    stkfut = lookup_product(product)
    if stkfut is None:
        return
    if not _is_tickable_stkfut(stkfut):
        logger.info("order/future 產品未開放:%s unit=%s", product, stkfut.get("unit"))
        raise HTTPException(status_code=400, detail={"error": "PRODUCT_NOT_ALLOWED"})
    if req.price_type != "limit":
        return
    _require_legal_tick(req.price, context=f"order/future {product}")


def _correct_price_tick_gate(client: CapitalClient, seq_no: str, price: float) -> None:
    """改價的個股期檔位閘:契約碼由 seq_no 反查 store(`_fut_multiplier` 同一條路)。

    - store 查無該委託 → 放行(review R3 逃生口:斷線 store 空時仍要能刪改單);
    - 契約碼推不出產品、或產品不是個股期 → 放行(指數期權不適用現股 tick 表);
    - 個股期但非標準/小型腿(ETF 期貨、除權息調整後的非標準單位)→ **放行**:
      現股 tick 表不適用,而這種活單可由群益 APP 下,改不動比擋掉更糟。

    scope = 僅驗「會被送單面放行的標準/小型個股期」,判準與送單面共用
    `_is_tickable_stkfut`(送單面不合 → PRODUCT_NOT_ALLOWED;改價面不合 → 放行)。
    """
    rec = next((o for o in client.store.orders() if o.seq_no == seq_no), None)
    if rec is None or not rec.stock_no:
        return
    try:
        product = exchange_product_of(rec.stock_no)
    except ValueError:
        logger.info(
            "correct-price 契約碼推不出產品(seq=%s, contract=%r)→ 不驗檔位", seq_no, rec.stock_no
        )
        return
    stkfut = lookup_product(product)
    if stkfut is None or not _is_tickable_stkfut(stkfut):
        return
    _require_legal_tick(price, context=f"correct-price {product}")


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
    """部位列表;每列附衍生欄 `code`(股號)。

    `code` 附在 API 邊界而不是進 `Position` dataclass:建構點散在 balance / store /
    測試多處,加欄要嘛給預設值(於是「沒反查」與「反查不到」同形)、要嘛連 store
    序列化面一起擴。衍生欄留在邊界,唯一讀者是前端。
    """
    client = _capital(request)
    return {
        "positions": [
            {**dataclasses.asdict(p), "code": stock_code_of(p.market, p.stock_no)}
            for p in client.store.positions()
        ]
    }


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
        # 個股期兩道閘先於乘數:兩者都會 400,但錯誤碼分得開才指得到真因
        # (INVALID_ORDER 對使用者只是「不知道為什麼不能送」)
        _stkfut_gates(product, req)
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
    if body.market == "fut":
        _correct_price_tick_gate(client, body.seq_no, body.price)
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
        kind=body.kind,
    )
    return dataclasses.asdict(await client.close_position(req))


@router.websocket("/ws/capital")
async def ws_capital(websocket: WebSocket) -> None:
    client: CapitalClient | None = websocket.app.state.capital
    await websocket.accept()
    if client is None:
        await websocket.close()
        return
    broadcaster: WsBroadcaster = websocket.app.state.capital_ws
    await relay(websocket, broadcaster.stream())


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
    await relay(websocket, broadcaster.stream())


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
