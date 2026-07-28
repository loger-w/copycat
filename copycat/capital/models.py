"""群益下單資料模型:request dataclass(frozen)+ 委託/庫存記錄 + 例外類(零 IO)。

欄位對照 treading-king backend/services/capital_models.py(pydantic → stdlib dataclass),
OrderRecord/Position 為 mutable(store 就地更新聚合狀態)並加 market 欄。
值域/映射細節見 docs/research/2026-07-28-skcom-typelib.md 與 PLAN Task 1。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BuySell = Literal["buy", "sell"]
PriceType = Literal["limit", "market"]
TimeInForce = Literal["ROD", "IOC", "FOK"]
TradeKind = Literal["cash", "margin", "short", "daytrade_sell"]
Market = Literal["sec", "fut"]


class CapitalDisabledError(Exception):
    """群益下單未啟用(factory 回 None / order_enabled off)— 對映 503 CAPITAL_DISABLED。"""


class CapitalNotReadyError(Exception):
    """COM 執行緒尚未就緒(登入/回報連線未完成)— 對映 503 CAPITAL_NOT_READY。"""


class CapitalGateBlockedError(Exception):
    """安全閘擋下寫入動作 — 對映 403 ORDER_BLOCKED(detail 帶 reason)。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class CapitalDownError(Exception):
    """群益端故障(COM 例外/timeout/執行緒死亡)— 對映 502 CAPITAL_DOWN。"""


@dataclass(frozen=True)
class StockOrderRequest:
    stock_no: str
    buy_sell: BuySell
    price: float
    qty: int  # 張
    price_type: PriceType = "limit"
    time_in_force: TimeInForce = "ROD"
    trade_kind: TradeKind = "cash"
    source: str = "panel"  # 稽核分流:panel/flash


@dataclass(frozen=True)
class FutureOrderRequest:
    tc4_symbol: str
    buy_sell: BuySell
    price: float
    qty: int  # 口
    price_type: PriceType = "limit"
    time_in_force: TimeInForce = "ROD"
    day_trade: bool = False
    source: str = "panel"


@dataclass(frozen=True)
class CancelOrderRequest:
    seq_no: str
    market: Market


@dataclass(frozen=True)
class CorrectPriceRequest:
    seq_no: str
    market: Market
    price: float


@dataclass(frozen=True)
class DecreaseQtyRequest:
    seq_no: str
    market: Market
    qty: int


@dataclass(frozen=True)
class PositionCloseRequest:
    market: Market
    key: str  # sec=股號;fut=期交所契約碼
    price: float  # market=閘用估價(前端帶);limit=委託價
    qty: int | None = None  # None=全部
    price_type: PriceType = "market"
    source: str = "panel"


@dataclass(frozen=True)
class OrderResult:
    ok: bool
    code: int
    message: str
    seq_no: str | None


@dataclass
class OrderRecord:
    """委託清單一列 = 一張單的聚合狀態(key=13碼委託序號)。qty 已換算顯示單位。"""

    seq_no: str
    stock_no: str | None = None
    name: str = ""  # route enrich 填,store 不管
    market: str | None = None
    buy_sell: str | None = None  # "B"/"S"
    flag_label: str | None = None  # 現股/融資/融券…
    book_no: str | None = None
    status_raw: str | None = None  # 最新事件 Type
    status_label: str | None = None  # 預約中/委託成功/部分成交/全部成交/已刪單/失敗/逾時/退單
    price: float | None = None  # 委託價(P/B 更新)
    avg_fill_price: float | None = None
    order_qty: int = 0  # 顯示單位(張/股/口)
    filled_qty: int = 0
    unit: str = "張"
    date: str | None = None  # 委託建立日 YYYYMMDD(排序/前端跨日顯示用)
    time: str | None = None  # 最新事件 HH:MM:SS
    pre_order: bool = False
    error_msg: str | None = None
    actionable: bool = False  # 活單可刪/改。store 由 _RANK 算,前端不要自己抄狀態表
    raw: str = ""  # 最新事件原始字串(debug)


@dataclass
class Position:
    market: str  # sec/fut(TC4 側 Market Literal;store 寫入時決定)
    stock_no: str  # sec=股號;fut=期交所契約碼
    qty: int  # 張/口(空方為負)
    name: str = ""
    avg_price: float | None = None  # 損益試算[10]平均買進成本(OnRealBalanceReport 無此欄)
    kind: str = "cash"  # cash(T集保)/margin(C融資)/short(L融券) — 平倉反向映射用
    pnl_base: float | None = None  # 損益試算[9]含費稅息淨損益(報告市價時點)— 前端平移基底
    pnl_base_price: float | None = None  # 損益試算[5]報告市價(平移基準)
    pnl_cost: float | None = None  # 損益試算[12]成交價金(% 分母,同報告[21]口徑)
