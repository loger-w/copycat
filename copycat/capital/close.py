"""平倉反向單組裝 — 純函式。

證券:部位種類 → 回補單(treading-king spec §6.2 固定映射):
現股多→現股賣;融資多→融資賣;融券空→融券買;無券空→現股買(交易所自動沖銷)。
邏輯照搬 treading-king backend/services/capital_close.py(pos_kind 參數 → pos.kind、
req.stock_no → req.key)。

期貨/選擇權:build_future_close_order 為本專案新增(design amendment:test 沙盒
市價 literal 不可送 → 限價貼漲跌停 + IOC,不走市價)。
"""

from __future__ import annotations

from copycat.capital.models import (
    BuySell,
    FutureOrderRequest,
    Position,
    PositionCloseRequest,
    StockOrderRequest,
    TradeKind,
)

# (部位種類, 是否多頭) → (回補方向, 回補交易種類)
_CLOSE_MAP: dict[tuple[str, bool], tuple[BuySell, TradeKind]] = {
    ("cash", True): ("sell", "cash"),
    ("margin", True): ("sell", "margin"),
    ("short", False): ("buy", "short"),
    ("daytrade_sell", False): ("buy", "cash"),
}


def build_close_order(pos: Position, req: PositionCloseRequest) -> StockOrderRequest:
    holding = abs(pos.qty)
    if holding == 0:
        raise ValueError(f"{req.key} 無部位可平")
    lots = req.qty if req.qty is not None else holding
    if lots <= 0:
        raise ValueError("平倉數量必須大於 0")
    if lots > holding:
        raise ValueError(f"平倉 {lots} 張超過持有 {holding} 張")
    key = (pos.kind, pos.qty > 0)
    if key not in _CLOSE_MAP:
        raise ValueError(f"部位種類 {pos.kind} 與方向不符,無法平倉")
    side, kind = _CLOSE_MAP[key]
    if req.price <= 0:
        raise ValueError("缺平倉價格(市價單也需帶閘用估價)")
    return StockOrderRequest(
        stock_no=req.key,
        buy_sell=side,
        price=req.price,
        qty=lots,
        price_type=req.price_type,
        trade_kind=kind,
        source=req.source,
    )


def build_future_close_order(pos: Position, req: PositionCloseRequest) -> FutureOrderRequest:
    """期權部位 → 反向平倉單(限價貼漲跌停 + IOC 固定;design amendment)。

    反向:pos.qty>0(買方)→ sell;pos.qty<0(賣方)→ buy。
    req.price = 閘用估價(漲跌停貼價,caller 帶入);不走市價 literal(test 沙盒不可用)。
    ⚠ 回傳的 `tc4_symbol` 欄在平倉路徑存的是**期交所契約碼**(= pos.stock_no)而非
    TC4 symbol — caller 直接當 contract 用,並經 to_futureorder_fields(..., new_close=1)
    覆寫倉別=平倉。
    """
    holding = abs(pos.qty)
    if holding == 0:
        raise ValueError(f"{pos.stock_no} 無部位可平")
    lots = req.qty if req.qty is not None else holding
    if lots <= 0:
        raise ValueError("平倉數量必須大於 0")
    if lots > holding:
        raise ValueError(f"平倉 {lots} 口超過持有 {holding} 口")
    if req.price <= 0:
        raise ValueError("缺平倉價格(閘用估價=漲跌停貼價)")
    side: BuySell = "sell" if pos.qty > 0 else "buy"
    return FutureOrderRequest(
        tc4_symbol=pos.stock_no,  # 期交所契約碼(平倉路徑語意,見 docstring)
        buy_sell=side,
        price=req.price,
        qty=lots,
        price_type="limit",
        time_in_force="IOC",
        source=req.source,
    )
