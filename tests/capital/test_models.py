"""SC-2/3/4/6:capital models — frozen 合約 / 預設值 / asdict JSON 化 / 例外類。"""

from __future__ import annotations

import dataclasses
import json
import re
from typing import get_args

import pytest

from copycat.capital.models import (
    AvgSource,
    CancelOrderRequest,
    CapitalDisabledError,
    CapitalDownError,
    CapitalGateBlockedError,
    CapitalNotReadyError,
    CorrectPriceRequest,
    DecreaseQtyRequest,
    FutureOrderRequest,
    OrderRecord,
    OrderResult,
    Position,
    PositionCloseRequest,
    StockOrderRequest,
    TradeKind,
)
from tests.helpers.frontend_source import read_frontend_source


def stock_req(**kw: object) -> StockOrderRequest:
    base: dict = {"stock_no": "2330", "buy_sell": "buy", "price": 1000.0, "qty": 1}
    base.update(kw)
    return StockOrderRequest(**base)


def future_req(**kw: object) -> FutureOrderRequest:
    base: dict = {
        "tc4_symbol": "TC.F.TWF.TXF.202609",
        "buy_sell": "buy",
        "price": 23000.0,
        "qty": 2,
    }
    base.update(kw)
    return FutureOrderRequest(**base)


class TestFrozen:
    def test_stock_order_request_immutable(self) -> None:
        req = stock_req()
        with pytest.raises(dataclasses.FrozenInstanceError):
            req.price = 999.0  # type: ignore[misc]

    def test_future_order_request_immutable(self) -> None:
        req = future_req()
        with pytest.raises(dataclasses.FrozenInstanceError):
            req.qty = 99  # type: ignore[misc]

    def test_control_requests_immutable(self) -> None:
        cancel = CancelOrderRequest(seq_no="1234567890123", market="sec")
        correct = CorrectPriceRequest(seq_no="1234567890123", market="fut", price=23100.0)
        decrease = DecreaseQtyRequest(seq_no="1234567890123", market="sec", qty=1)
        close = PositionCloseRequest(market="fut", key="TXFI6", price=23000.0)
        result = OrderResult(ok=True, code=0, message="", seq_no="1234567890123")
        for obj in (cancel, correct, decrease, close, result):
            with pytest.raises(dataclasses.FrozenInstanceError):
                obj.seq_no = "x"  # type: ignore[misc]


class TestDefaults:
    def test_stock_order_request_defaults(self) -> None:
        req = stock_req()
        assert req.price_type == "limit"
        assert req.time_in_force == "ROD"
        assert req.trade_kind == "cash"
        assert req.source == "panel"

    def test_future_order_request_defaults(self) -> None:
        req = future_req()
        assert req.price_type == "limit"
        assert req.time_in_force == "ROD"
        assert req.day_trade is False
        assert req.source == "panel"

    def test_position_close_request_defaults(self) -> None:
        req = PositionCloseRequest(market="sec", key="2330", price=1000.0)
        assert req.qty is None
        assert req.price_type == "market"
        assert req.source == "panel"


class TestMutableRecords:
    def test_order_record_updates_in_place(self) -> None:
        rec = OrderRecord(seq_no="1234567890123")
        rec.filled_qty = 2
        rec.status_label = "部分成交"
        assert rec.filled_qty == 2
        assert rec.status_label == "部分成交"
        assert rec.market is None
        assert rec.order_qty == 0
        assert rec.unit == "張"
        assert rec.pre_order is False
        assert rec.actionable is False

    def test_position_updates_in_place(self) -> None:
        pos = Position(market="sec", stock_no="2330", qty=3)
        pos.qty = 1
        pos.avg_price = 995.0
        assert pos.qty == 1
        assert pos.avg_price == 995.0
        assert pos.name == ""
        assert pos.kind == "cash"
        assert pos.pnl_base is None
        assert pos.pnl_base_price is None
        assert pos.pnl_cost is None


class TestAsdictJson:
    def test_all_models_asdict_json_serializable(self) -> None:
        objs: list[object] = [
            stock_req(),
            future_req(day_trade=True),
            CancelOrderRequest(seq_no="1234567890123", market="sec"),
            CorrectPriceRequest(seq_no="1234567890123", market="fut", price=23100.0),
            DecreaseQtyRequest(seq_no="1234567890123", market="sec", qty=1),
            PositionCloseRequest(market="fut", key="TXFI6", price=23000.0, qty=2),
            OrderResult(ok=False, code=1097, message="帳號未開通", seq_no=None),
            OrderRecord(seq_no="1234567890123", market="TS", price=1000.0),
            Position(market="fut", stock_no="TXFI6", qty=-1, avg_price=23000.0),
        ]
        for obj in objs:
            payload = json.dumps(dataclasses.asdict(obj))  # type: ignore[call-overload]
            assert isinstance(payload, str)


class TestExceptions:
    def test_exception_hierarchy(self) -> None:
        for exc_type in (
            CapitalDisabledError,
            CapitalNotReadyError,
            CapitalGateBlockedError,
            CapitalDownError,
        ):
            assert issubclass(exc_type, Exception)

    def test_gate_blocked_carries_reason(self) -> None:
        exc = CapitalGateBlockedError("no_futures_account")
        assert exc.reason == "no_futures_account"
        assert "no_futures_account" in str(exc)


def test_avg_source_parity_with_frontend() -> None:
    """跨語言契約(CLAUDE.md §4 avg_source):後端 `AvgSource` Literal 是產生點,前端 `types.ts::AVG_SOURCES`
    是執行期白名單(`AvgSource` 型別由它推導)。後端先加值而前端沒跟 → 白名單把新值歸 null → **靜默**退回
    修前口徑(損益少一筆買費、打平線跳格),零錯誤訊號 —— 比 #118 的 NaN 更難看到(pr-129 F-05)。
    同 `test_river_palette_covers_every_leg` 姿態:後端測試直接讀前端原始碼字面鎖兩邊集合相等。"""
    text = read_frontend_source("types.ts")
    m = re.search(r"export const AVG_SOURCES = \[([^\]]*)\] as const;", text)
    assert m, "types.ts 找不到 `export const AVG_SOURCES = [...] as const;` 字面"
    frontend = re.findall(r'"([^"]+)"', m.group(1))
    backend = list(get_args(AvgSource))
    assert len(frontend) == len(set(frontend)), frontend
    assert set(frontend) == set(backend), (frontend, backend)


def test_position_kind_subset_of_trade_kind() -> None:
    """跨語言契約(CLAUDE.md §4 證券部位 kind 的 daytrade_sell 值):前端 `types.ts::PositionKind`(平倉 body 送得出的
    種類 = `close-order.ts::KIND_TEXT` 鍵集)必須是後端 `TradeKind`(`PositionCloseBody.kind` 值域)的**子集** ——
    後端單邊拿掉一值 → 前端照送 → 真錢空單平倉 422,兩側各自的字面測試全綠(pr-152 review F-13)。
    子集不相等:TradeKind 同時是下單交易別值域,日後加值不該逼前端跟。"""
    text = read_frontend_source("types.ts")
    m = re.search(r"export type PositionKind = ([^;]+);", text)
    assert m, "types.ts 找不到 `export type PositionKind = ...;` 字面"
    frontend = re.findall(r'"([^"]+)"', m.group(1))
    backend = set(get_args(TradeKind))
    assert frontend and len(frontend) == len(set(frontend)), frontend
    assert set(frontend) <= backend, (frontend, sorted(backend))
