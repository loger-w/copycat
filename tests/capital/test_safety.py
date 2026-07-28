"""safety 閘測試:None=不限(user 拍板,與 treading-king fail-closed 相反)× 期權乘數。"""

from __future__ import annotations

from copycat.capital.models import FutureOrderRequest, StockOrderRequest
from copycat.capital.safety import (
    GateResult,
    SafetyConfig,
    check_cancel,
    check_correct_price,
    check_decrease,
    check_future_order,
    check_master,
    check_stock_order,
)


def _stock(qty: int = 1, price: float = 590.0, **kw: object) -> StockOrderRequest:
    return StockOrderRequest(stock_no="2330", buy_sell="buy", price=price, qty=qty, **kw)  # type: ignore[arg-type]


def _fut(qty: int = 1, price: float = 23000.0, **kw: object) -> FutureOrderRequest:
    return FutureOrderRequest(
        tc4_symbol="TC.F.TWF.TXF.202609", buy_sell="buy", price=price, qty=qty, **kw
    )  # type: ignore[arg-type]


def _cfg(
    enabled: bool = True, max_qty: int | None = None, max_amount: float | None = None
) -> SafetyConfig:
    return SafetyConfig(order_enabled=enabled, max_qty=max_qty, max_amount=max_amount)


# ── master 總開關 ──────────────────────────────────────────────


def test_master_off_blocks_everything() -> None:
    off = _cfg(enabled=False)
    for r in (
        check_master(off),
        check_stock_order(_stock(), off),
        check_future_order(_fut(), off, multiplier=200),
        check_cancel(off),
        check_correct_price(100.0, 1, off),
        check_decrease(1, off),
    ):
        assert r.allowed is False
        assert r.reason == "order_disabled"


def test_master_on_allows() -> None:
    r = check_master(_cfg())
    assert r == GateResult(True)


def test_config_defaults_disabled_and_unlimited() -> None:
    cfg = SafetyConfig()
    assert cfg.order_enabled is False
    assert cfg.max_qty is None
    assert cfg.max_amount is None


# ── None = 不限(僅基本驗證) ─────────────────────────────────


def test_none_limits_allow_any_size() -> None:
    cfg = _cfg()  # max_qty=None, max_amount=None
    assert check_stock_order(_stock(qty=99_999, price=1000.0), cfg).allowed is True
    assert check_future_order(_fut(qty=500, price=23000.0), cfg, multiplier=200).allowed is True
    assert check_correct_price(1_000_000.0, 999, cfg).allowed is True


def test_none_limits_still_do_basic_validation() -> None:
    cfg = _cfg()
    assert check_stock_order(_stock(qty=0), cfg).allowed is False
    assert check_stock_order(_stock(price=0.0), cfg).allowed is False
    assert check_future_order(_fut(qty=-1), cfg, multiplier=200).allowed is False


# ── max_qty 邊界 ──────────────────────────────────────────────


def test_max_qty_boundary_equal_allowed_over_blocked() -> None:
    cfg = _cfg(max_qty=5)
    assert check_stock_order(_stock(qty=5), cfg).allowed is True
    r = check_stock_order(_stock(qty=6), cfg)
    assert r.allowed is False
    assert r.reason is not None and "數量" in r.reason
    assert check_future_order(_fut(qty=5), cfg, multiplier=200).allowed is True
    assert check_future_order(_fut(qty=6), cfg, multiplier=200).allowed is False


# ── max_amount × 期權乘數 ─────────────────────────────────────


def test_stock_amount_uses_1000_shares_per_lot() -> None:
    # 10 張 × 590 × 1000 = 5,900,000 > 2,000,000
    cfg = _cfg(max_amount=2_000_000.0)
    r = check_stock_order(_stock(qty=10), cfg)
    assert r.allowed is False
    assert r.reason is not None and "金額" in r.reason
    # 3 張 × 590 × 1000 = 1,770,000 ≤ 2,000,000
    assert check_stock_order(_stock(qty=3), cfg).allowed is True


def test_future_amount_uses_multiplier_txf200() -> None:
    # PLAN 例:23000 × 2 口 × 200 = 9.2M ≤ 10M → allowed
    cfg = _cfg(max_amount=10_000_000.0)
    assert check_future_order(_fut(qty=2, price=23000.0), cfg, multiplier=200).allowed is True
    # 23000 × 3 口 × 200 = 13.8M > 10M → blocked
    r = check_future_order(_fut(qty=3, price=23000.0), cfg, multiplier=200)
    assert r.allowed is False
    assert r.reason is not None and "金額" in r.reason
    # 同名目換小乘數(MXF 50):23000 × 3 × 50 = 3.45M ≤ 10M
    assert check_future_order(_fut(qty=3, price=23000.0), cfg, multiplier=50).allowed is True


def test_future_market_order_estimate_price_gated() -> None:
    # market 單 price 為閘用估價(R1):同式計算,且估價必須 > 0
    cfg = _cfg(max_amount=10_000_000.0)
    req = _fut(qty=3, price=23000.0, price_type="market")
    assert check_future_order(req, cfg, multiplier=200).allowed is False
    bad = _fut(qty=1, price=0.0, price_type="market")
    assert check_future_order(bad, _cfg(), multiplier=200).allowed is False


# ── 無券 + 買進 ───────────────────────────────────────────────


def test_daytrade_sell_buy_blocked() -> None:
    req = StockOrderRequest(
        stock_no="2330", buy_sell="buy", price=100.0, qty=1, trade_kind="daytrade_sell"
    )
    r = check_stock_order(req, _cfg())
    assert r.allowed is False
    assert r.reason == "daytrade_sell 不可買進"


def test_daytrade_sell_sell_allowed() -> None:
    req = StockOrderRequest(
        stock_no="2330", buy_sell="sell", price=100.0, qty=1, trade_kind="daytrade_sell"
    )
    assert check_stock_order(req, _cfg()).allowed is True


# ── qty / price 非法 ──────────────────────────────────────────


def test_nonpositive_qty_blocked() -> None:
    assert check_stock_order(_stock(qty=0), _cfg()).allowed is False
    assert check_stock_order(_stock(qty=-3), _cfg()).allowed is False
    assert check_future_order(_fut(qty=0), _cfg(), multiplier=200).allowed is False


def test_nonpositive_and_nonfinite_price_blocked() -> None:
    nan, inf = float("nan"), float("inf")
    for price in (0.0, -5.0, nan, inf):
        assert check_stock_order(_stock(price=price), _cfg()).allowed is False
        assert check_future_order(_fut(price=price), _cfg(), multiplier=200).allowed is False
        assert check_correct_price(price, 1, _cfg()).allowed is False


# ── check_correct_price ───────────────────────────────────────


def test_correct_price_amount_gate_with_multiplier() -> None:
    cfg = _cfg(max_amount=100_000.0)
    # 股票預設 multiplier=1000:200 × 1 張 × 1000 = 200,000 > 100,000
    r = check_correct_price(200.0, 1, cfg)
    assert r.allowed is False
    assert r.reason is not None and "金額" in r.reason
    assert check_correct_price(90.0, 1, cfg).allowed is True
    # 期貨乘數覆寫:400 × 1 口 × 200 = 80,000 ≤ 100,000
    assert check_correct_price(400.0, 1, cfg, multiplier=200).allowed is True
    assert check_correct_price(600.0, 1, cfg, multiplier=200).allowed is False


def test_correct_price_remaining_none_skips_qty_and_amount() -> None:
    # None = 查無剩量:金額/數量閘跳過,只驗 new_price > 0
    cfg = _cfg(max_amount=1.0)
    assert check_correct_price(999_999.0, None, cfg).allowed is True
    assert check_correct_price(0.0, None, cfg).allowed is False
    assert check_correct_price(float("nan"), None, cfg).allowed is False
    # master 閘仍先行
    assert check_correct_price(100.0, None, _cfg(enabled=False)).allowed is False


def test_correct_price_zero_remaining_blocked() -> None:
    r = check_correct_price(100.0, 0, _cfg())
    assert r.allowed is False
    assert r.reason is not None and "未成交" in r.reason


# ── cancel / decrease ─────────────────────────────────────────


def test_cancel_only_needs_master() -> None:
    assert check_cancel(_cfg()).allowed is True


def test_decrease_needs_positive_qty() -> None:
    assert check_decrease(1, _cfg()).allowed is True
    assert check_decrease(0, _cfg()).allowed is False
    assert check_decrease(-2, _cfg()).allowed is False
