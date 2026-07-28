"""mapping 測試:STOCKORDER/FUTUREORDER 逐欄 + TC4 → 期交所契約碼轉換(SC-2/3)。

證券逐欄案例移植 treading-king tests/test_capital_mapping.py(enum → Literal 改寫)。
FUTUREORDER 用欄依 Task 0 spike 定案(docs/research/2026-07-28-skcom-typelib.md)。
"""

from __future__ import annotations

import pytest

from copycat.capital.mapping import (
    exchange_product_of,
    multiplier_of,
    product_of,
    to_exchange_symbol,
    to_futureorder_fields,
    to_stockorder_fields,
)
from copycat.capital.models import (
    BuySell,
    FutureOrderRequest,
    PriceType,
    StockOrderRequest,
    TimeInForce,
    TradeKind,
)


def _stock(
    buy_sell: BuySell = "buy",
    price: float = 590.0,
    price_type: PriceType = "limit",
    time_in_force: TimeInForce = "ROD",
    trade_kind: TradeKind = "cash",
) -> StockOrderRequest:
    return StockOrderRequest(
        stock_no="2330",
        buy_sell=buy_sell,
        price=price,
        qty=1,
        price_type=price_type,
        time_in_force=time_in_force,
        trade_kind=trade_kind,
    )


def _fut(
    tc4_symbol: str = "TC.F.TWF.TXF.202609",
    buy_sell: BuySell = "buy",
    price: float = 23000.0,
    qty: int = 2,
    price_type: PriceType = "limit",
    time_in_force: TimeInForce = "ROD",
    day_trade: bool = False,
) -> FutureOrderRequest:
    return FutureOrderRequest(
        tc4_symbol=tc4_symbol,
        buy_sell=buy_sell,
        price=price,
        qty=qty,
        price_type=price_type,
        time_in_force=time_in_force,
        day_trade=day_trade,
    )


# ── STOCKORDER 逐欄(treading-king 案例移植)────────────────────


def test_stock_buy_limit_rod_cash_maps_to_capital_enums() -> None:
    f = to_stockorder_fields(_stock(), full_account="1234567890A")
    assert f["bstrStockNo"] == "2330"
    assert f["bstrFullAccount"] == "1234567890A"
    assert f["sBuySell"] == 0  # 買=0
    assert f["nSpecialTradeType"] == 2  # 限價=2
    assert f["nTradeType"] == 0  # ROD=0
    assert f["sFlag"] == 0  # 現股=0
    assert f["bstrPrice"] == "590.00"  # 價格字串,兩位小數
    assert f["nQty"] == 1
    assert f["sPeriod"] == 0  # 盤中
    assert f["sPrime"] == 0  # 上市櫃


def test_stock_sell_market_fok_short_maps() -> None:
    f = to_stockorder_fields(
        _stock(
            buy_sell="sell",
            price_type="market",
            time_in_force="FOK",
            trade_kind="short",
        ),
        full_account="1234567890A",
    )
    assert f["sBuySell"] == 1  # 賣=1
    assert f["nSpecialTradeType"] == 1  # 市價=1
    assert f["nTradeType"] == 2  # FOK=2
    assert f["sFlag"] == 2  # 融券=2


def test_stock_margin_maps_to_one() -> None:
    f = to_stockorder_fields(_stock(trade_kind="margin"), full_account="x")
    assert f["sFlag"] == 1  # 融資=1


def test_stock_daytrade_sell_maps_to_three() -> None:
    f = to_stockorder_fields(_stock(buy_sell="sell", trade_kind="daytrade_sell"), full_account="x")
    assert f["sFlag"] == 3  # 無券=3


# ── FUTUREORDER 逐欄(spike 定案欄位)──────────────────────────


def test_future_limit_full_fields() -> None:
    f = to_futureorder_fields(_fut(), "F0123456789", contract="TXFI6")
    assert f == {
        "bstrFullAccount": "F0123456789",
        "bstrStockNo": "TXFI6",
        "bstrPrice": "23000",  # 整數價去小數
        "sTradeType": 0,  # ROD=0
        "sBuySell": 0,  # 買=0
        "sDayTrade": 0,
        "sNewClose": 2,  # 預設自動
        "nQty": 2,
    }


def test_future_limit_decimal_price_keeps_fraction() -> None:
    f = to_futureorder_fields(_fut(price=96.5), "acc", contract="TXO20000I6")
    assert f["bstrPrice"] == "96.5"  # 有小數保留,無 float 尾差


def test_future_sell_ioc_fok_tradetype() -> None:
    f = to_futureorder_fields(_fut(buy_sell="sell", time_in_force="IOC"), "acc", contract="TXFI6")
    assert f["sBuySell"] == 1
    assert f["sTradeType"] == 1  # IOC=1
    f2 = to_futureorder_fields(_fut(time_in_force="FOK"), "acc", contract="TXFI6")
    assert f2["sTradeType"] == 2  # FOK=2


def test_future_market_forces_ioc_and_m_literal() -> None:
    f = to_futureorder_fields(
        _fut(price_type="market", time_in_force="ROD"), "acc", contract="TXFI6"
    )
    assert f["bstrPrice"] == "M"  # 市價 literal(spike 定案 M,未實測)
    assert f["sTradeType"] == 1  # 市價 ROD(不可市價掛整天)→ 升 IOC


def test_future_market_fok_keeps_fok() -> None:
    # review A9:市價單僅 ROD 升 IOC;使用者明示 FOK(全成或全撤)不可被靜默降成 IOC
    f = to_futureorder_fields(
        _fut(price_type="market", time_in_force="FOK"), "acc", contract="TXFI6"
    )
    assert f["bstrPrice"] == "M"
    assert f["sTradeType"] == 2  # FOK 保留


def test_future_new_close_override() -> None:
    f = to_futureorder_fields(_fut(), "acc", contract="TXFI6", new_close=1)
    assert f["sNewClose"] == 1  # 平倉單由 close.py 傳 1


def test_future_day_trade_flag() -> None:
    f = to_futureorder_fields(_fut(day_trade=True), "acc", contract="TXFI6")
    assert f["sDayTrade"] == 1


# ── to_exchange_symbol:月碼表 ─────────────────────────────────


@pytest.mark.parametrize(
    ("month", "code"),
    [
        (1, "A"),
        (2, "B"),
        (3, "C"),
        (4, "D"),
        (5, "E"),
        (6, "F"),
        (7, "G"),
        (8, "H"),
        (9, "I"),
        (10, "J"),
        (11, "K"),
        (12, "L"),
    ],
)
def test_futures_month_codes(month: int, code: str) -> None:
    assert to_exchange_symbol(f"TC.F.TWF.TXF.2026{month:02d}") == f"TXF{code}6"


@pytest.mark.parametrize(("ym", "code"), [("202603", "C6"), ("202609", "I6"), ("202612", "L6")])
def test_option_call_month_codes(ym: str, code: str) -> None:
    assert to_exchange_symbol(f"TC.O.TWF.TXO.{ym}.C.19500") == f"TXO19500{code}"


@pytest.mark.parametrize(("ym", "code"), [("202601", "M6"), ("202609", "U6"), ("202612", "X6")])
def test_option_put_month_codes(ym: str, code: str) -> None:
    assert to_exchange_symbol(f"TC.O.TWF.TXO.{ym}.P.20000") == f"TXO20000{code}"


def test_year_code_is_last_digit() -> None:
    assert to_exchange_symbol("TC.F.TWF.TXF.202712") == "TXFL7"


def test_option_strike_string_kept_verbatim() -> None:
    assert to_exchange_symbol("TC.O.TWF.TXO.202609.C.20000") == "TXO20000I6"


def test_weekly_option_product_same_rule() -> None:
    assert to_exchange_symbol("TC.O.TWF.TX5.202607.C.23000") == "TX523000G6"


# ── to_exchange_symbol:HOT 與解析失敗 ─────────────────────────


def test_hot_with_resolved_ym() -> None:
    assert to_exchange_symbol("TC.F.TWF.TXF.HOT", resolved_ym="202609") == "TXFI6"


def test_hot_without_resolved_ym_raises() -> None:
    with pytest.raises(ValueError):
        to_exchange_symbol("TC.F.TWF.TXF.HOT")


@pytest.mark.parametrize(
    "symbol",
    [
        "TC.S.TWS.2330",  # 個股非期權
        "TXF202609",  # 非 TC4 格式
        "TC.F.TWF.TXF.202613",  # 月份越界
        "TC.O.TWF.TXO.2026W1.C.20000",  # 週選 token 非 YYYYMM(spike 未定)
        "",
    ],
)
def test_unparseable_symbol_raises(symbol: str) -> None:
    with pytest.raises(ValueError):
        to_exchange_symbol(symbol)


# ── multiplier_of / exchange_product_of / product_of ──────────


@pytest.mark.parametrize(
    ("product", "mult"),
    [("TXF", 200), ("MXF", 50), ("TMF", 10), ("TXO", 50)],
)
def test_multiplier_of_base_products(product: str, mult: int) -> None:
    assert multiplier_of(product) == mult


@pytest.mark.parametrize(
    "product",
    ["TX1", "TX2", "TX3", "TX4", "TX5", "TXY", "TXZ", "MX1", "MX2", "MX3", "MX4", "MX5"],
)
def test_multiplier_of_weekly_family_is_50(product: str) -> None:
    assert multiplier_of(product) == 50


def test_multiplier_of_unknown_raises() -> None:
    with pytest.raises(ValueError):
        multiplier_of("ZZZ")


@pytest.mark.parametrize(
    ("contract", "product"),
    [("TXFI6", "TXF"), ("MXFL5", "MXF"), ("TMFA6", "TMF"), ("TXO20000I6", "TXO")],
)
def test_exchange_product_of(contract: str, product: str) -> None:
    assert exchange_product_of(contract) == product


@pytest.mark.parametrize(
    ("contract", "product"),
    [("TX422000T6", "TX4"), ("MXFI6", "MXF"), ("TXO20000I6", "TXO"), ("MX523000G6", "MX5")],
)
def test_exchange_product_of_known_prefix_wins(contract: str, product: str) -> None:
    # 週選契約(TX422000T6)的「去尾 2 碼取字母段」啟發式會截成 "TX" →
    # 乘數反查 ValueError → fallback 1,金額閘鬆 50 倍(review A1)
    assert exchange_product_of(contract) == product


def test_product_of_takes_fourth_segment() -> None:
    assert product_of("TC.F.TWF.TXF.HOT") == "TXF"
    assert product_of("TC.F.TWF.MXF.202609") == "MXF"
    assert product_of("TC.O.TWF.TXO.202609.C.20000") == "TXO"


def test_product_of_bad_symbol_raises() -> None:
    with pytest.raises(ValueError):
        product_of("TC.S.TWS.2330")  # 個股段非期權
    with pytest.raises(ValueError):
        product_of("not-a-symbol")
