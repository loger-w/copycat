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
# 群益即時庫存段的三種**原始**種類代碼(OnRealBalanceReport [1] T集保 / C融資 / L融券)解析中繼 ——
# 只給 balance._KIND / _PNL_KIND / _PNL_KIND_CODE / ProfitRow.kind 用。部位對外值域(store 鍵、wire
# `PositionCloseBody.kind` / `PositionCloseRequest.kind`、`position_for` 查找)是 TradeKind:2026-08-30 起
# 現股 T 列負股數與成交回報「無券」都會產生 daytrade_sell 列,部位面板點得到平倉、前端也會送這個 kind
#(pr-152 review F-01;修前這裡寫「不進 wire」,已成假述)。
PositionKind = Literal["cash", "margin", "short"]
#: Position.avg_price 的語意來源:broker = 群益損益試算「平均買進成本」(**含買進手續費**;
#: 2026-08-26 prod 實證 4991 成交 469.50 → 均價 469.62,差 = 價 × 0.1425% × 折數);
#: fill = 成交回報樂觀套用的**純成交價**。前端打平線 / 損益依來源決定要不要再加買費 ——
#: 兩邊算同一條線,券商快照落地才不會跳格(fix/breakeven-avg-source-daytrade-tax)。
AvgSource = Literal["broker", "fill"]


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
    # sec 庫存種類(同檔資+集保並存時的第二把鍵);
    # None = 舊 body:同檔唯一列才成立,多列一律阻擋不猜。fut 忽略此欄。
    # 值域 TradeKind(2026-08-30 起含 daytrade_sell:無券空單可平倉,_CLOSE_MAP 回補 = 現股買)。
    kind: TradeKind | None = None


@dataclass(frozen=True)
class OrderResult:
    ok: bool
    code: int
    message: str
    seq_no: str | None


@dataclass
class FillRecord:
    """逐筆成交(D 事件)一列(成交點精確版,L76)。與 OrderRecord 同尺:qty 已換算
    顯示單位(整股撮合以張為單位,除得盡;除不盡的異常量退回原始股數 + unit="股",
    不靜默捨小數);`price` 是**這一筆**的成交價,不是委託均價。`date` = 成交**到達**
    本機日(同 `_Agg.fill_date` 口徑);`time` = 該筆回報事件時刻。store 的保留窗 =
    到達日今天 ∨ 錨定交易日同當前(pr-167 F-02:期貨夜盤跨午夜 / 隔週末仍同軸)。

    已知殘餘限制:重播蓋日(跨錨定日重連時 `store.clear()` 後重播昨日 D 事件會以
    到達日重建)目前**不可達** —— `clear()` 零 prod caller(ConnectByID 只在開機
    重播,屆時 store 是新的);若未來加回報斷線重連,重播列的 `date` 語意要重審。"""

    seq_no: str
    stock_no: str | None
    buy_sell: str  # "B"/"S"
    flag_label: str | None
    price: float
    qty: int
    unit: str  # 張/口/股
    date: str
    time: str | None


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
    date: str | None = None  # 回報 idx23 YYYYMMDD,每筆回報覆寫;跨日事件是否變值未實證(排序/前端跨日顯示用)
    time: str | None = None  # 最新事件 HH:MM:SS
    pre_order: bool = False
    error_msg: str | None = None
    actionable: bool = False  # 活單可刪/改。store 由 _RANK 算,前端不要自己抄狀態表
    # 價格別:**本 app 送出才知道**(群益回報無此欄)→ APP 下單 / 跨日的單恆 None。
    # store 由送單結果記憶(note_price_type),回報事件不會產生它。
    price_type: str | None = None
    raw: str = ""  # 最新事件原始字串(debug)


@dataclass
class Position:
    market: str  # sec/fut(TC4 側 Market Literal;store 寫入時決定)
    stock_no: str  # sec=股號;fut=期交所契約碼
    qty: int  # 張/口(空方為負)
    name: str = ""
    avg_price: float | None = None  # 損益試算[10]平均買進成本(OnRealBalanceReport 無此欄)
    # 部位種類:值域 TradeKind。daytrade_sell = 無券當沖空單(2026-08-30 校準:群益現股 T 列負股數 /
    # 成交回報「無券」兩條產生路徑,_CLOSE_MAP 回補 = 現股買進)。fut 列恆 "cash"(OI 不帶種類)。
    kind: TradeKind = "cash"
    pnl_base: float | None = None  # 損益試算[9]含費稅息淨損益(報告市價時點)— 前端平移基底
    pnl_base_price: float | None = None  # 損益試算[5]報告市價(平移基準)
    pnl_cost: float | None = None  # 損益試算[12]成交價金(% 分母,同報告[21]口徑)
    avg_source: AvgSource | None = None  # avg_price 的語意來源;avg_price None 時恆 None
    # 今天成交淨進來的張數(同 (股號, 種類);buy − sell,clamp 到 [0, |qty|];fut 恆 0)。
    # 前端現股當沖賣出稅減半(0.15%)只套這一段,其餘張數 0.3%。來源 = 委託聚合(群益
    # ConnectByID 只重播當日 backlog,所以聚合裡的成交都是今天的)。
    today_qty: int = 0
