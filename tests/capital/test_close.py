"""平倉反向映射(spec §6.2 四規則)+ close 驗量 + 期貨平倉組裝(SC-5/6)。
treading-king test_capital_close.py 照搬改寫(enum → Literal 字串、
PositionCloseRequest key/market 欄、pos_kind 參數 → pos.kind)。"""

from __future__ import annotations

import pytest

from copycat.capital.close import build_close_order, build_future_close_order
from copycat.capital.models import Position, PositionCloseRequest, TradeKind


def _pos(qty: int, kind: TradeKind = "cash") -> Position:
    return Position(market="sec", stock_no="2330", qty=qty, avg_price=500.0, kind=kind)


def test_long_cash_closes_with_cash_sell() -> None:
    pos = _pos(3)
    req = PositionCloseRequest(market="sec", key="2330", price=450.0)
    order = build_close_order(pos, req)
    assert order.buy_sell == "sell"
    assert order.trade_kind == "cash"
    assert order.qty == 3  # 預設全部
    assert order.source == "panel"


def test_partial_qty_close() -> None:
    pos = _pos(5)
    req = PositionCloseRequest(market="sec", key="2330", qty=2, price=450.0)
    assert build_close_order(pos, req).qty == 2


def test_qty_over_holding_rejected() -> None:
    pos = _pos(2)
    req = PositionCloseRequest(market="sec", key="2330", qty=3, price=450.0)
    with pytest.raises(ValueError, match="超過持有"):
        build_close_order(pos, req)


def test_margin_long_closes_with_margin_sell() -> None:
    pos = _pos(1, kind="margin")
    order = build_close_order(pos, PositionCloseRequest(market="sec", key="2330", price=450.0))
    assert order.buy_sell == "sell"
    assert order.trade_kind == "margin"


def test_short_position_closes_with_short_buy() -> None:
    pos = _pos(-2, kind="short")
    order = build_close_order(pos, PositionCloseRequest(market="sec", key="2330", price=550.0))
    assert order.buy_sell == "buy"
    assert order.trade_kind == "short"
    assert order.qty == 2  # 取絕對值


def test_daytrade_short_closes_with_cash_buy() -> None:
    pos = _pos(-1, kind="daytrade_sell")
    order = build_close_order(pos, PositionCloseRequest(market="sec", key="2330", price=550.0))
    assert order.buy_sell == "buy"
    assert order.trade_kind == "cash"  # 無券空單回補=現股買進(交易所自動沖銷)


def test_no_position_rejected() -> None:
    with pytest.raises(ValueError, match="無部位可平"):
        build_close_order(_pos(0), PositionCloseRequest(market="sec", key="2330", price=450.0))


def test_kind_direction_mismatch_rejected() -> None:
    # 融券卻是多頭方向(資料矛盾)→ 不猜單種,直接拒絕
    with pytest.raises(ValueError, match="無法平倉"):
        build_close_order(
            _pos(2, kind="short"), PositionCloseRequest(market="sec", key="2330", price=450.0)
        )


def test_cash_short_direction_is_data_contradiction_and_rejected() -> None:
    """(cash, 空向)刻意**不在** _CLOSE_MAP:2026-08-28 校準後群益負現股列已在 parse 端歸
    daytrade_sell,cash 負向不再有正常來源 = 資料矛盾 → 不猜單種,與 (short, 多向) 同理拒絕。"""
    with pytest.raises(ValueError, match="無法平倉"):
        build_close_order(
            _pos(-1, kind="cash"), PositionCloseRequest(market="sec", key="2330", price=450.0)
        )


def test_zero_price_rejected() -> None:
    with pytest.raises(ValueError, match="平倉價格"):
        build_close_order(_pos(3), PositionCloseRequest(market="sec", key="2330", price=0.0))


# ---- 期貨平倉:build_future_close_order ----


def _fut_pos(qty: int, contract: str = "TXFI6") -> Position:
    return Position(market="fut", stock_no=contract, qty=qty, avg_price=23000.0)


def test_future_long_closes_with_ioc_limit_sell() -> None:
    req = PositionCloseRequest(market="fut", key="TXFI6", price=22000.0)
    order = build_future_close_order(_fut_pos(2), req)
    assert order.buy_sell == "sell"
    assert order.qty == 2  # 預設全部
    # design amendment:test 沙盒市價 literal 不可用 → 限價貼漲跌停 + IOC 固定
    assert order.price_type == "limit"
    assert order.time_in_force == "IOC"
    assert order.price == 22000.0  # 閘用估價=漲跌停貼價(caller 帶入)
    assert order.tc4_symbol == "TXFI6"  # 平倉路徑此欄存期交所碼,caller 直接當 contract 用
    assert order.source == "panel"


def test_future_short_closes_with_buy() -> None:
    req = PositionCloseRequest(market="fut", key="TXO20000I6", price=130.0)
    order = build_future_close_order(_fut_pos(-1, contract="TXO20000I6"), req)
    assert order.buy_sell == "buy"
    assert order.qty == 1
    assert order.tc4_symbol == "TXO20000I6"


def test_future_partial_qty_close() -> None:
    req = PositionCloseRequest(market="fut", key="TXFI6", qty=1, price=22000.0)
    assert build_future_close_order(_fut_pos(3), req).qty == 1


def test_future_qty_over_holding_rejected() -> None:
    req = PositionCloseRequest(market="fut", key="TXFI6", qty=3, price=22000.0)
    with pytest.raises(ValueError, match="超過持有"):
        build_future_close_order(_fut_pos(2), req)


def test_future_no_position_rejected() -> None:
    req = PositionCloseRequest(market="fut", key="TXFI6", price=22000.0)
    with pytest.raises(ValueError, match="無部位可平"):
        build_future_close_order(_fut_pos(0), req)


def test_future_zero_or_negative_qty_rejected() -> None:
    req = PositionCloseRequest(market="fut", key="TXFI6", qty=0, price=22000.0)
    with pytest.raises(ValueError, match="大於 0"):
        build_future_close_order(_fut_pos(2), req)


def test_future_zero_price_rejected() -> None:
    req = PositionCloseRequest(market="fut", key="TXFI6", price=0.0)
    with pytest.raises(ValueError, match="平倉價格"):
        build_future_close_order(_fut_pos(2), req)


def test_future_source_propagated() -> None:
    req = PositionCloseRequest(market="fut", key="TXFI6", price=22000.0, source="flash")
    assert build_future_close_order(_fut_pos(1), req).source == "flash"


def test_close_kind_label_parity_with_frontend() -> None:
    """跨語言契約(CLAUDE.md §4 證券部位 kind 的 daytrade_sell 值):前端 `close-order.ts::CLOSE_KIND`(確認窗
    「反向單 … (現股)」的回補交易別)鏡像後端 `_CLOSE_MAP` 的回補單種 —— 後端改回補單種而前端沒跟,確認窗會
    謊報實送交易別、兩側各自測試全綠(pr-152 review 收修 Standards F-01)。逐 kind 比:前端 kind → kind,
    後端 (kind, 多空) → (方向, 單種),同 kind 所有方向的單種必須等於前端值。"""
    import re

    from copycat.capital.close import _CLOSE_MAP
    from tests.helpers.frontend_source import read_frontend_source

    text = read_frontend_source("lib/close-order.ts")
    m = re.search(r"const CLOSE_KIND: Record<PositionKind, PositionKind> = \{([^}]*)\};", text)
    assert m, "close-order.ts 找不到 `const CLOSE_KIND: Record<PositionKind, PositionKind> = {...};` 字面"
    frontend = dict(re.findall(r'(\w+): "(\w+)"', m.group(1)))
    backend = {kind: {v[1] for (k, _), v in _CLOSE_MAP.items() if k == kind} for kind in {k for k, _ in _CLOSE_MAP}}
    assert set(frontend) == set(backend), (frontend, backend)
    for kind, close_kind in frontend.items():
        assert backend[kind] == {close_kind}, (kind, close_kind, backend[kind])
