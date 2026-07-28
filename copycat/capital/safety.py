"""下單安全閘 —— 純函式,所有寫入(下單/改/刪/減/平倉)送群益前必過。

邏輯對照 treading-king backend/services/capital_safety.py,關鍵差異(user 拍板):
上限 `max_qty`/`max_amount` 為 `None` = 不限(跳過該閘),與 treading-king 的
fail-closed(未設=拒單)相反;設了數值照擋。期權名目 = price × qty × multiplier(review R8)。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from copycat.capital.models import FutureOrderRequest, StockOrderRequest


@dataclass(frozen=True)
class SafetyConfig:
    order_enabled: bool = False
    max_qty: int | None = None  # None = 不限(單筆張/口)
    max_amount: float | None = None  # None = 不限(單筆名目金額)


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    reason: str | None = None


def _master(cfg: SafetyConfig) -> GateResult | None:
    if not cfg.order_enabled:
        return GateResult(False, "order_disabled")
    return None


def check_master(cfg: SafetyConfig) -> GateResult:
    """只驗下單總開關 — 任何寫入的第一道閘,先於其他檢查,稽核 blocked 才反映真正原因。"""
    return _master(cfg) or GateResult(True)


def _bad_price(price: float) -> GateResult | None:
    # NaN 對任何比較都是 False,會無聲穿過 <=0 與金額上限兩道閘,必須明確擋。
    # market 單的 price 是閘用估價(review R1),同樣必須 > 0 且有限。
    if not math.isfinite(price) or price <= 0:
        return GateResult(False, "價格必須大於 0")
    return None


def _check_qty_amount(price: float, qty: int, cfg: SafetyConfig, *, multiplier: int) -> GateResult:
    if qty <= 0:
        return GateResult(False, "數量必須大於 0")
    if cfg.max_qty is not None and qty > cfg.max_qty:
        return GateResult(False, f"數量 {qty} 超過上限 {cfg.max_qty}")
    if cfg.max_amount is not None:
        est = price * qty * multiplier
        if est > cfg.max_amount:
            return GateResult(False, f"預估金額 {est:.0f} 超過上限 {cfg.max_amount:.0f}")
    return GateResult(True)


def check_stock_order(req: StockOrderRequest, cfg: SafetyConfig) -> GateResult:
    blocked = _master(cfg) or _bad_price(req.price)
    if blocked:
        return blocked
    # 無券=現股當沖先賣;「無券+買進」不是合法組合(回補=現股買進,交易所自動沖銷)
    if req.trade_kind == "daytrade_sell" and req.buy_sell == "buy":
        return GateResult(False, "daytrade_sell 不可買進")
    return _check_qty_amount(req.price, req.qty, cfg, multiplier=1000)


def check_future_order(req: FutureOrderRequest, cfg: SafetyConfig, *, multiplier: int) -> GateResult:
    """期貨/選擇權閘:名目 = price × qty × multiplier;market 單 price 為閘用估價,同式。"""
    blocked = _master(cfg) or _bad_price(req.price)
    if blocked:
        return blocked
    return _check_qty_amount(req.price, req.qty, cfg, multiplier=multiplier)


def check_cancel(cfg: SafetyConfig) -> GateResult:
    """刪單只降風險:僅過總開關。"""
    return check_master(cfg)


def check_correct_price(
    new_price: float, remaining: int | None, cfg: SafetyConfig, *, multiplier: int = 1000
) -> GateResult:
    """改價改變曝險:總開關 + 新價 × 未成交量 × 乘數過金額閘。

    remaining=None 表查無剩量(store 沒該筆):數量/金額閘跳過,只驗 new_price > 0。
    """
    blocked = _master(cfg) or _bad_price(new_price)
    if blocked:
        return blocked
    if remaining is None:
        return GateResult(True)
    if remaining <= 0:
        # 已全成交/已刪單 remaining=0:est=0 恆過金額閘,安全層須自己擋,不留給券商兜底
        return GateResult(False, "無未成交數量可改價")
    if cfg.max_amount is not None:
        est = new_price * remaining * multiplier
        if est > cfg.max_amount:
            return GateResult(False, f"預估金額 {est:.0f} 超過上限 {cfg.max_amount:.0f}")
    return GateResult(True)


def check_decrease(qty: int, cfg: SafetyConfig) -> GateResult:
    """減量只降風險:總開關 + 量 > 0。"""
    blocked = _master(cfg)
    if blocked:
        return blocked
    if qty <= 0:
        return GateResult(False, "減量必須大於 0")
    return GateResult(True)
