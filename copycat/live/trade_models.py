"""下單資料模型:NEWORDER param 對映、回報 parse、帳戶遮罩/分類(零 IO 純函數)。

TC4 值域對照(spikes/TCPY/trade_sample.py + 官方下單設定頁;整合驗證清單見 design §8):
Side 1=買/2=賣;OrderType 1=市價/2=限價;TimeInForce 1=ROD/2=IOC;PositionEffect 4=自動。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Mapping, Sequence

OrderSide = Literal["buy", "sell"]
OrderKind = Literal["limit", "market"]

_MILLI = Decimal(1000)


class TouchanceDownError(Exception):
    """Touchance 端故障(連線/timeout/ErrCode -20)— 對映 502 TOUCHANCE_DOWN。"""


class BrokerRejectedError(Exception):
    """券商/交易所拒單(NEWORDER ErrCode 或回報 rejected)— 對映 400 BROKER_REJECTED。"""

    def __init__(self, err_code: str, err_msg: str = "") -> None:
        super().__init__(f"broker rejected: {err_code} {err_msg}".rstrip())
        self.err_code = err_code
        self.err_msg = err_msg


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: OrderSide
    kind: OrderKind
    qty: int
    price_millipts: int | None  # limit 必填;market None


@dataclass(frozen=True)
class AccountInfo:
    broker_id: str
    account: str
    account_mask: str
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class OrderReport:
    report_id: str
    symbol: str
    side: str
    status_raw: str
    price: str
    qty: str
    filled_qty: str
    err_code: str | None
    err_msg: str | None
    raw: Mapping[str, Any]


def price_str_from_millipts(v: int) -> str:
    """毫點 → TC4 價格字串(整數除盡去小數:15500→"15.5"、23000000→"23000")。"""
    d = Decimal(v) / _MILLI
    text = format(d.normalize(), "f")
    return text


def millipts_from_price_str(s: str) -> int:
    """點數字串 → 毫點;非法/非正值 raise ValueError(route 層轉 400 INVALID_ORDER)。"""
    try:
        d = Decimal(s.strip())
    except InvalidOperation as exc:
        raise ValueError(f"invalid price: {s!r}") from exc
    if not s.strip() or d <= 0:
        raise ValueError(f"invalid price: {s!r}")
    scaled = d * _MILLI
    if scaled != scaled.to_integral_value():
        raise ValueError(f"price finer than millipts: {s!r}")
    return int(scaled)


def to_neworder_param(req: OrderRequest, *, broker_id: str, account: str) -> dict[str, str]:
    """組 NEWORDER Param;市價單不帶 Price 鍵(design §2.1 [auto-default])。"""
    param: dict[str, str] = {
        "Symbol": req.symbol,
        "BrokerID": broker_id,
        "Account": account,
        "Side": "1" if req.side == "buy" else "2",
        "OrderQty": str(req.qty),
        "PositionEffect": "4",
    }
    if req.kind == "limit":
        if req.price_millipts is None:
            raise ValueError("limit order requires price_millipts")
        param["OrderType"] = "2"
        param["TimeInForce"] = "1"
        param["Price"] = price_str_from_millipts(req.price_millipts)
    else:
        param["OrderType"] = "1"
        param["TimeInForce"] = "2"
    return param


def parse_accounts(msg: Mapping[str, Any]) -> list[AccountInfo]:
    accounts: list[AccountInfo] = []
    for row in msg.get("Accounts") or []:
        accounts.append(
            AccountInfo(
                broker_id=str(row.get("BrokerID", "")),
                account=str(row.get("Account", "")),
                account_mask=str(row.get("AccountMask", "")),
                raw=row,
            )
        )
    return accounts


def _parse_report(row: Mapping[str, Any]) -> OrderReport:
    err_code = row.get("ErrCode")
    if err_code in (0, "0"):  # 慣例 0 = 無錯,不得標成錯誤列(值域見 design §8)
        err_code = None
    err_msg = row.get("ErrMsg")
    return OrderReport(
        report_id=str(row.get("ReportID", "")),
        symbol=str(row.get("Symbol", "")),
        side=str(row.get("Side", "")),
        status_raw=str(row.get("OrdStatus", row.get("ExecType", ""))),
        price=str(row.get("Price", row.get("AvgPrice", ""))),
        qty=str(row.get("OrderQty", "")),
        filled_qty=str(row.get("CumQty", row.get("MatchedQty", ""))),
        err_code=str(err_code) if err_code not in (None, "") else None,
        err_msg=str(err_msg) if err_msg not in (None, "") else None,
        raw=row,
    )


def parse_execution_report(row: Mapping[str, Any]) -> OrderReport:
    return _parse_report(row)


def parse_fill_report(row: Mapping[str, Any]) -> OrderReport:
    return _parse_report(row)


def mask_account(account: str) -> str:
    """只留末 4 碼;不足 4 碼全遮(§7 審計/banner 用)。"""
    if len(account) < 4:
        return "****"
    return "****" + account[-4:]


def classify_is_sim(acc: AccountInfo, patterns: Sequence[str]) -> bool:
    """broker_id 不分大小寫子字串比對;patterns 空 → False(無法分類視為正式戶)。"""
    broker = acc.broker_id.lower()
    return any(p.lower() in broker for p in patterns if p)
