"""capital routes/例外映射/futures 行情 REST+WS/舊 trade 路 404(SC-1..6/8/9/10/11)。

治具:tests/capital/fake_com.py 的 FakeCom 配真 CapitalClient(app lifespan 走真
start/close,COM 執行緒消化命令佇列);factory 單例以 monkeypatch _client 注入
(test_factory 同慣例)。futures 行情 fake source 直傳 create_app(futures_source=...)。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import copycat.capital.factory as factory_mod
import copycat.stkfut_map as stkfut_map
from copycat.stkfut_map import write_map
from copycat.capital.client import CapitalClient
from copycat.server.audit import AuditWriteError
from copycat.server.ws import CLIENT_QUEUE_MAX as _CLIENT_QUEUE_MAX
from copycat.server.ws import WsBroadcaster
from copycat.capital.models import Position
from copycat.capital.safety import SafetyConfig
from copycat.live.models import OptionContract, SeriesInfo, Tick
from copycat.server.app import create_app
from tests.capital.fake_com import FakeCom, RejectingCom
from tests.helpers.boot import BootedClient
from tests.helpers.fake_sources import FakeFuturesSource

C23000 = OptionContract(symbol="TC.O.TWF.TXO.202607.C.23000", cp="C", strike_millipts=23_000_000)
SERIES = SeriesInfo(series_id="TXO.202607", name="TXO 202607", expiry="202607", contracts=(C23000,))


class FakeQuoteSource:
    def list_series(self) -> list[SeriesInfo]:
        return [SERIES]

    def fetch_backfill(self, series: SeriesInfo) -> list[Tick]:
        return []

    def subscribe(self, series: SeriesInfo, on_tick: Callable[[Tick], None]) -> None:
        return None

    def unsubscribe(self, series: SeriesInfo) -> None:
        return None

    def close(self) -> None:
        return None


def _fut_quote(**over: object) -> dict:
    q: dict = {
        "Symbol": "TC.F.TWF.TXF.HOT",
        "SecurityName": "臺股期貨",
        "TradingPrice": "23500",
        "TradeQuantity": "2",
        "TradeVolume": "1000",
        "TradeDate": "20260728",
        "PreciseTime": "10000000000",
        "Bid": "23499",
        "BidVolume": "10",
        "Ask": "23500",
        "AskVolume": "12",
        "ReferencePrice": "23400",
    }
    q.update(over)
    return q


def _stock_evt_raw(seq: str, qty: str = "1000", price: str = "90.0000") -> str:
    """OnNewData 證券委託事件(N)最小治具(欄位對照 test_client 同款)。"""
    arr = [""] * 48
    arr[0], arr[1], arr[2], arr[3] = seq, "TS", "N", "N"
    arr[6], arr[8], arr[11], arr[20] = "B00R2", "3357", price, qty
    return ",".join(arr)


def _fut_evt_raw(seq: str, contract: str = "TXFI6", qty: str = "2", price: str = "23000") -> str:
    """OnNewData 期權委託事件(N;市場別 TF)最小治具(欄位對照 test_client 同款)。"""
    arr = [""] * 48
    arr[0], arr[1], arr[2], arr[3] = seq, "TF", "N", "N"
    arr[6], arr[8], arr[11], arr[20] = "BNR20", contract, price, qty
    return ",".join(arr)


def _capital_client(
    tmp_path: Path,
    *,
    com: FakeCom | None = None,
    enabled: bool = True,
    max_amount: float | None = None,
) -> tuple[CapitalClient, FakeCom]:
    com = com if com is not None else FakeCom()
    client = CapitalClient(
        com,
        user_id="u",
        password="p",
        full_account="1234567890A",
        env="test",
        safety=SafetyConfig(order_enabled=enabled, max_qty=None, max_amount=max_amount),
        audit_base=tmp_path / "audit",
    )
    return client, com


def _wait_status(
    client: CapitalClient, want: tuple[str, ...] = ("ok",), timeout: float = 3.0
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client.status in want:
            return
        time.sleep(0.005)
    raise AssertionError(f"capital status={client.status},等不到 {want}")


def _sent(com: FakeCom, kind: str) -> list[tuple[object, ...]]:
    """背景 balance 鏈也會 append com.sent — 依類別過濾,不可用索引位置斷言。"""
    return [t for t in com.sent if t[0] == kind]


def make_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    capital: CapitalClient | None = None,
    futures_source: FakeFuturesSource | None = None,
    configure: Callable[[FastAPI], None] | None = None,
) -> TestClient:
    """`configure` = 建 TestClient 前對 app 動手的鉤子(探針 route 用,見 TestErrorMapping)。"""
    monkeypatch.delenv("CAPITAL_USER_ID", raising=False)
    monkeypatch.setattr(factory_mod, "_client", capital)
    app = create_app(
        FakeQuoteSource(),
        futures_source=futures_source,
        throttle_secs=0.01,
    )
    if configure is not None:
        configure(app)
    return BootedClient(app, raise_server_exceptions=False)


_STOCK_BODY: dict[str, Any] = {"stock_no": "2330", "buy_sell": "buy", "price": 590.0, "qty": 1}
_FUTURE_BODY: dict[str, Any] = {
    "tc4_symbol": "TC.F.TWF.TXF.202609",
    "buy_sell": "buy",
    "price": 23000,
    "qty": 1,
}

_ALL_CAPITAL_ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", "/api/capital/orders", None),
    ("GET", "/api/capital/positions", None),
    ("POST", "/api/capital/order/stock", _STOCK_BODY),
    ("POST", "/api/capital/order/future", _FUTURE_BODY),
    ("POST", "/api/capital/order/cancel", {"seq_no": "00000000001", "market": "sec"}),
    (
        "POST",
        "/api/capital/order/correct-price",
        {"seq_no": "00000000001", "market": "sec", "price": 91.0},
    ),
    ("POST", "/api/capital/order/decrease", {"seq_no": "00000000001", "market": "sec", "qty": 1}),
    ("POST", "/api/capital/position/close", {"market": "sec", "key": "2330", "price": 590.0}),
]


# ---------------------------------------------------------------------------
# status(SC-10)
# ---------------------------------------------------------------------------


class TestStatus:
    def test_disabled_returns_200_not_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with make_client(monkeypatch) as client:
            res = client.get("/api/capital/status")
            assert res.status_code == 200
            assert res.json() == {"status": "disabled"}

    def test_ok_shape_with_masked_accounts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cap, _com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            body = client.get("/api/capital/status").json()
            assert body["status"] == "ok"
            assert body["env"] == "test"
            assert body["account_masked"] == "****890A"
            assert body["futures_account_masked"] == "****9999"
            assert body["order_enabled"] is True
            assert "1234567890A" not in str(body)  # 帳號本體不得外洩


# ---------------------------------------------------------------------------
# disabled:除 status 外全 503 CAPITAL_DISABLED
# ---------------------------------------------------------------------------


class TestDisabled:
    def test_all_routes_503_capital_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with make_client(monkeypatch) as client:
            for method, url, body in _ALL_CAPITAL_ROUTES:
                res = client.request(method, url, json=body)
                assert res.status_code == 503, url
                assert res.json()["detail"]["error"] == "CAPITAL_DISABLED", url


# ---------------------------------------------------------------------------
# orders / positions(SC-5/6 讀路)
# ---------------------------------------------------------------------------


class TestOrdersPositions:
    def test_empty_shapes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cap, _com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            assert client.get("/api/capital/orders").json() == {"orders": []}
            assert client.get("/api/capital/positions").json() == {"positions": []}

    def test_orders_reflect_reply(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            assert com.on_reply is not None
            com.on_reply(_stock_evt_raw("00000000001"))
            orders = client.get("/api/capital/orders").json()["orders"]
            assert len(orders) == 1
            assert orders[0]["seq_no"] == "00000000001"
            assert orders[0]["market"] == "TS"
            assert orders[0]["order_qty"] == 1  # 1000 股 → 1 張

    def test_positions_reflect_store(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cap, _com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            cap.store.set_positions([Position(market="sec", stock_no="2330", qty=2)])
            positions = client.get("/api/capital/positions").json()["positions"]
            assert [p["stock_no"] for p in positions] == ["2330"]
            assert positions[0]["market"] == "sec"

    def test_positions_carry_code(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """每列附 `code`(股號)—— 前端沒有契約碼→股號的反查,只能由後端給(SC-1)。

        個股期用**真版控對映表**(不 monkeypatch DEFAULT_PATH):這條要在期交所改碼 /
        對映表沒 refresh 時跟著紅,那正是 `code` 會靜默變 null 的情境。
        """
        cap, _com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            cap.store.set_positions(
                [
                    Position(market="sec", stock_no="2330", qty=2),
                    Position(market="fut", stock_no="CDFI6", qty=1),
                    Position(market="fut", stock_no="EE1I6", qty=1),
                ]
            )
            positions = client.get("/api/capital/positions").json()["positions"]
            assert [(p["stock_no"], p["code"]) for p in positions] == [
                ("2330", "2330"),  # sec:股號直接沿用
                ("CDFI6", "2330"),  # fut 標準:CDF → 2330
                ("EE1I6", None),  # 除權息調整碼進不了對映表 → 不猜
            ]
            # 既有欄位仍在(加欄是 additive)
            assert positions[0]["market"] == "sec"
            assert positions[0]["qty"] == 2
            assert positions[0]["kind"] == "cash"

    def test_positions_keep_both_kinds_of_same_stock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 複合鍵:同檔資+集保並存回兩列(舊 dedupe 只留張數大者,被捨棄種類平倉鍵不到)
        cap, _com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            cap.store.set_positions(
                [
                    Position(market="sec", stock_no="2330", qty=1, kind="cash"),
                    Position(market="sec", stock_no="2330", qty=3, kind="margin"),
                ]
            )
            positions = client.get("/api/capital/positions").json()["positions"]
            assert [(p["stock_no"], p["kind"], p["qty"]) for p in positions] == [
                ("2330", "cash", 1),
                ("2330", "margin", 3),
            ]


# ---------------------------------------------------------------------------
# order/stock(SC-2)
# ---------------------------------------------------------------------------


class TestOrderStock:
    def test_happy_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            res = client.post("/api/capital/order/stock", json=_STOCK_BODY)
            assert res.status_code == 200
            body = res.json()
            assert body["ok"] is True
            assert body["seq_no"] == "SEQ0001"
            stock_sent = _sent(com, "stock")
            assert len(stock_sent) == 1
            fields = stock_sent[0][1]
            assert isinstance(fields, dict)
            assert fields["bstrStockNo"] == "2330"
            assert fields["sBuySell"] == 0

    def test_gate_blocked_403_with_reason(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cap, com = _capital_client(tmp_path, enabled=False)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            res = client.post("/api/capital/order/stock", json=_STOCK_BODY)
            assert res.status_code == 403
            detail = res.json()["detail"]
            assert detail["error"] == "ORDER_BLOCKED"
            assert detail["reason"] == "order_disabled"
            assert _sent(com, "stock") == []  # 閘擋下不得觸 COM


# ---------------------------------------------------------------------------
# order/future(SC-3:HOT 解析/契約轉換/期權分流)
# ---------------------------------------------------------------------------


class TestOrderFuture:
    def test_explicit_month_converts_contract(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            res = client.post("/api/capital/order/future", json=_FUTURE_BODY)
            assert res.status_code == 200
            assert res.json()["ok"] is True
            fut_sent = _sent(com, "future")
            assert len(fut_sent) == 1
            fields = fut_sent[0][1]
            assert isinstance(fields, dict)
            assert fields["bstrStockNo"] == "TXFI6"
            assert fields["bstrFullAccount"] == "F9999999"
            assert fut_sent[0][2] is False  # TXF → SendFutureOrder 家族

    def test_option_symbol_routes_option_flow(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            body = dict(_FUTURE_BODY, tc4_symbol="TC.O.TWF.TXO.202609.C.20000", price=100)
            res = client.post("/api/capital/order/future", json=body)
            assert res.status_code == 200
            fut_sent = _sent(com, "future")
            fields = fut_sent[0][1]
            assert isinstance(fields, dict)
            assert fields["bstrStockNo"] == "TXO20000I6"
            assert fut_sent[0][2] is True  # TXO → 期權面

    def test_unknown_product_400_invalid_order(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cap, _com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            body = dict(_FUTURE_BODY, tc4_symbol="TC.F.TWF.ZZZ.202609")
            res = client.post("/api/capital/order/future", json=body)
            assert res.status_code == 400
            assert res.json()["detail"]["error"] == "INVALID_ORDER"

    def test_hot_without_engine_400(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            body = dict(_FUTURE_BODY, tc4_symbol="TC.F.TWF.TXF.HOT")
            res = client.post("/api/capital/order/future", json=body)
            assert res.status_code == 400
            assert res.json()["detail"]["error"] == "INVALID_ORDER"
            assert _sent(com, "future") == []  # 不猜月份、不送單

    def test_hot_unresolved_400(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cap, _com = _capital_client(tmp_path)
        src = FakeFuturesSource()
        with make_client(monkeypatch, capital=cap, futures_source=src) as client:
            _wait_status(cap)
            body = dict(_FUTURE_BODY, tc4_symbol="TC.F.TWF.TXF.HOT")
            res = client.post("/api/capital/order/future", json=body)
            assert res.status_code == 400
            assert res.json()["detail"]["error"] == "INVALID_ORDER"

    def test_hot_resolved_via_engine(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cap, com = _capital_client(tmp_path)
        src = FakeFuturesSource()
        with make_client(monkeypatch, capital=cap, futures_source=src) as client:
            _wait_status(cap)
            assert src.on_message is not None
            src.on_message(_fut_quote(EndDate="20260916"))  # HOT → 202609
            body = dict(_FUTURE_BODY, tc4_symbol="TC.F.TWF.TXF.HOT")
            res = client.post("/api/capital/order/future", json=body)
            assert res.status_code == 200
            fields = _sent(com, "future")[0][1]
            assert isinstance(fields, dict)
            assert fields["bstrStockNo"] == "TXFI6"


# ---------------------------------------------------------------------------
# order/future 的個股期閘(stkfut-contracts SC-6:PRODUCT_NOT_ALLOWED / BAD_TICK)
# ---------------------------------------------------------------------------


def _stkfut_map(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """個股期對映表注入(隔離版控真檔;CDF=標準 2000、QFF=小型 100、NYF=ETF 10000)。"""
    path = tmp_path / "stkfut_map.json"
    write_map(
        path,
        {
            "2330": {
                "prod": "CDF",
                "name": "台積電",
                "unit": 2000,
                "mini": {"prod": "QFF", "unit": 100},
            },
            "0050": {"prod": "NYF", "name": "元大台灣50ETF", "unit": 10000, "mini": None},
            "1312": {"prod": "EEF", "name": "國喬", "unit": 2157, "mini": None},
        },
    )
    monkeypatch.setattr(stkfut_map, "DEFAULT_PATH", path)


_STKFUT_BODY: dict[str, Any] = {
    "tc4_symbol": "TC.F.TWF.CDF.202609",
    "buy_sell": "buy",
    "price": 1180.0,
    "qty": 1,
}


class TestOrderStkfutGates:
    def test_standard_stock_future_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stkfut_map(tmp_path, monkeypatch)
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            res = client.post("/api/capital/order/future", json=_STKFUT_BODY)
            assert res.status_code == 200
            sent = _sent(com, "future")[0]
            fields = sent[1]
            assert isinstance(fields, dict)
            assert fields["bstrStockNo"] == "CDFI6"
            # 個股期是期貨:整條 route 走到 COM 時必須是 SendFutureOrder(C-1)
            assert sent[2] is False

    def test_mini_stock_future_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stkfut_map(tmp_path, monkeypatch)
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            body = dict(_STKFUT_BODY, tc4_symbol="TC.F.TWF.QFF.202609")
            assert client.post("/api/capital/order/future", json=body).status_code == 200
            assert len(_sent(com, "future")) == 1
            assert _sent(com, "future")[0][2] is False  # 小型腿同樣是期貨(C-1)

    def test_etf_future_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """ETF 期貨(契約單位 10,000 受益權單位)本輪不開放下單 —— 行情/乘數照落,
        送單層擋:名目金額是股票期貨的 5 倍,誤按一次的後果與個股期完全不同級。"""
        _stkfut_map(tmp_path, monkeypatch)
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            body = dict(_STKFUT_BODY, tc4_symbol="TC.F.TWF.NYF.202609", price=60.0)
            res = client.post("/api/capital/order/future", json=body)
            assert res.status_code == 400
            assert res.json()["detail"]["error"] == "PRODUCT_NOT_ALLOWED"
            assert _sent(com, "future") == []

    def test_non_standard_unit_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """characterization(R13):除權息調整後契約單位變 2,157 的個股期會被一併擋下。

        這是**已知的誤拒**(design Known Risks)—— 「單位必須是標準值」這道閘的
        目的是擋 ETF,而調整契約剛好落在同一側。放寬要另外拿到「哪些單位算股票期貨」
        的權威來源,不是把閘拿掉。
        """
        _stkfut_map(tmp_path, monkeypatch)
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            body = dict(_STKFUT_BODY, tc4_symbol="TC.F.TWF.EEF.202609", price=60.0)
            res = client.post("/api/capital/order/future", json=body)
            assert res.status_code == 400
            assert res.json()["detail"]["error"] == "PRODUCT_NOT_ALLOWED"
            assert _sent(com, "future") == []

    @pytest.mark.parametrize("price", [1180.5, 60.03, 9.999])
    def test_illegal_tick_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, price: float
    ) -> None:
        """個股期的升降單位 = 現股 tick 表(期交所規格同級距)。非法檔位在期交所會被
        退單,而群益端的退單訊息回到畫面上只是一句「委託失敗」。"""
        _stkfut_map(tmp_path, monkeypatch)
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            body = dict(_STKFUT_BODY, price=price)
            res = client.post("/api/capital/order/future", json=body)
            assert res.status_code == 400
            assert res.json()["detail"]["error"] == "BAD_TICK"
            assert _sent(com, "future") == []

    # 50–100 元段的檔位是 0.1 元(不是 0.05)—— 各段的合法值各取一個
    @pytest.mark.parametrize("price", [1180.0, 60.1, 9.99, 505.0])
    def test_legal_ticks_pass(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, price: float
    ) -> None:
        _stkfut_map(tmp_path, monkeypatch)
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            body = dict(_STKFUT_BODY, price=price)
            assert client.post("/api/capital/order/future", json=body).status_code == 200
            assert len(_sent(com, "future")) == 1

    def test_market_order_skips_tick_gate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """市價單的 price 欄無意義(bstrPrice="M")→ 不得拿它去驗檔位(R2-8)。"""
        _stkfut_map(tmp_path, monkeypatch)
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            body = dict(_STKFUT_BODY, price=1180.5, price_type="market", time_in_force="IOC")
            assert client.post("/api/capital/order/future", json=body).status_code == 200
            assert len(_sent(com, "future")) == 1

    # code review B4:名目金額閘的乘數 = 契約單位股數。這條沒被鎖住的話,乘數若退回
    # 1(`multiplier_of` 的 fallback 路徑)金額閘會鬆 2,000 倍 —— 而畫面上只是「單送出去
    # 了」,沒有任何訊號。標準與小型差 20 倍,兩腿各鎖一次才分得出「用錯了另一腿的單位」。
    @pytest.mark.parametrize(
        "symbol,unit",
        [("TC.F.TWF.CDF.202609", 2000), ("TC.F.TWF.QFF.202609", 100)],
    )
    def test_amount_gate_uses_the_contract_unit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, symbol: str, unit: int
    ) -> None:
        _stkfut_map(tmp_path, monkeypatch)
        price = 1180.0
        notional = price * unit  # qty=1
        # 邊界:est == 上限放行(閘是 `>` 才擋)
        cap, com = _capital_client(tmp_path, max_amount=notional)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            body = dict(_STKFUT_BODY, tc4_symbol=symbol, price=price)
            assert client.post("/api/capital/order/future", json=body).status_code == 200
            assert len(_sent(com, "future")) == 1
        # 差一元就要擋 —— 乘數若是別腿的單位,這一則會靜默通過
        cap2, com2 = _capital_client(tmp_path, max_amount=notional - 1)
        with make_client(monkeypatch, capital=cap2) as client:
            _wait_status(cap2)
            body = dict(_STKFUT_BODY, tc4_symbol=symbol, price=price)
            res = client.post("/api/capital/order/future", json=body)
            assert res.status_code == 403
            detail = res.json()["detail"]
            assert detail["error"] == "ORDER_BLOCKED"
            assert f"{notional:.0f}" in detail["reason"]
            assert _sent(com2, "future") == []

    def test_index_future_not_subject_to_stock_tick_gate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """台指期 23,000 點在股票 tick 表是「5 元檔」的合法值,但這道閘本來就只該
        套在個股期上 —— 鎖住範圍,免得日後改 tick 表誤傷指數期。"""
        _stkfut_map(tmp_path, monkeypatch)
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            body = dict(_FUTURE_BODY, price=23001)
            assert client.post("/api/capital/order/future", json=body).status_code == 200
            assert len(_sent(com, "future")) == 1


# ---------------------------------------------------------------------------
# 改價的個股期檔位閘(SC-6 同一 blast radius:送單擋得住的價,改價不可放行)
# ---------------------------------------------------------------------------


class TestCorrectPriceStkfutTickGate:
    def _seed_fut_order(self, com: FakeCom, seq: str, contract: str) -> None:
        assert com.on_reply is not None
        com.on_reply(_fut_evt_raw(seq, contract=contract))

    def test_illegal_tick_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """個股期活單改到非法檔位 → 400 BAD_TICK,不得送到群益。

        送單面有這道閘、改價面沒有的話,同一個 1180.5 送不出去卻改得進去,
        而期交所退單回到畫面上只是一句「委託失敗」(送單閘的 docstring 逐字)。
        """
        _stkfut_map(tmp_path, monkeypatch)
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            self._seed_fut_order(com, "00000000021", "CDFI6")
            res = client.post(
                "/api/capital/order/correct-price",
                json={"seq_no": "00000000021", "market": "fut", "price": 1180.5},
            )
            assert res.status_code == 400
            assert res.json()["detail"]["error"] == "BAD_TICK"
            assert _sent(com, "correct_price") == []

    def test_legal_tick_passes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _stkfut_map(tmp_path, monkeypatch)
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            self._seed_fut_order(com, "00000000021", "CDFI6")
            res = client.post(
                "/api/capital/order/correct-price",
                json={"seq_no": "00000000021", "market": "fut", "price": 1180.0},
            )
            assert res.status_code == 200
            assert len(_sent(com, "correct_price")) == 1

    def test_unknown_seq_still_passes_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """store 查無 → 放行(R3 逃生口):斷線時 store 空,刪改單仍必須送得出去。"""
        _stkfut_map(tmp_path, monkeypatch)
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            res = client.post(
                "/api/capital/order/correct-price",
                json={"seq_no": "99999999999", "market": "fut", "price": 1180.5},
            )
            assert res.status_code == 200
            assert len(_sent(com, "correct_price")) == 1

    @pytest.mark.parametrize(
        ("seq", "contract"),
        [
            ("00000000023", "NYFI6"),  # ETF 期貨(10,000 受益權單位)
            ("00000000024", "EEFI6"),  # 除權息調整後的非標準單位(2,157)
        ],
    )
    def test_non_standard_unit_not_gated(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, seq: str, contract: str
    ) -> None:
        """非標準契約單位的個股期改價不驗檔位 —— 送單面根本走不到 tick 檢查。

        送單面在 tick 檢查**之前**先擋單位(PRODUCT_NOT_ALLOWED),ETF / 調整後
        契約永遠到不了現股 tick 表;改價面照套那張表,會把制度上合法的 60.05
        擋成 400 BAD_TICK。而這種活單真的存在(可由群益 APP 下),擋掉的結果是
        既有委託改不動 —— 閘的目的是消滅退單,不是自己造一個。
        """
        _stkfut_map(tmp_path, monkeypatch)
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            self._seed_fut_order(com, seq, contract)
            res = client.post(
                "/api/capital/order/correct-price",
                json={"seq_no": seq, "market": "fut", "price": 60.05},
            )
            assert res.status_code == 200
            assert len(_sent(com, "correct_price")) == 1

    def test_index_future_not_gated(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """characterization:現股 tick 表只適用個股期,指數期權改價照放行(鎖 scope)。"""
        _stkfut_map(tmp_path, monkeypatch)
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            self._seed_fut_order(com, "00000000022", "TXFI6")
            res = client.post(
                "/api/capital/order/correct-price",
                json={"seq_no": "00000000022", "market": "fut", "price": 23000.5},
            )
            assert res.status_code == 200
            assert len(_sent(com, "correct_price")) == 1


# ---------------------------------------------------------------------------
# cancel / correct-price / decrease(SC-4:market 帳號路由)
# ---------------------------------------------------------------------------


class TestCancelCorrectDecrease:
    def test_cancel_fut_uses_futures_account(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            res = client.post(
                "/api/capital/order/cancel", json={"seq_no": "00000000009", "market": "fut"}
            )
            assert res.status_code == 200
            assert _sent(com, "cancel") == [("cancel", "F9999999", "00000000009")]

    def test_cancel_sec_uses_stock_account(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            res = client.post(
                "/api/capital/order/cancel", json={"seq_no": "00000000009", "market": "sec"}
            )
            assert res.status_code == 200
            assert _sent(com, "cancel") == [("cancel", "1234567890A", "00000000009")]

    def test_cancel_market_mismatch_403(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            assert com.on_reply is not None
            com.on_reply(_stock_evt_raw("00000000001"))  # store 記為證券單(TS)
            res = client.post(
                "/api/capital/order/cancel", json={"seq_no": "00000000001", "market": "fut"}
            )
            assert res.status_code == 403
            assert res.json()["detail"]["reason"] == "market_mismatch"

    def test_correct_price_and_decrease_200(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            res = client.post(
                "/api/capital/order/correct-price",
                json={"seq_no": "00000000001", "market": "sec", "price": 91.0},
            )
            assert res.status_code == 200
            res = client.post(
                "/api/capital/order/decrease",
                json={"seq_no": "00000000001", "market": "sec", "qty": 1},
            )
            assert res.status_code == 200
            assert _sent(com, "correct_price") == [
                ("correct_price", "1234567890A", "00000000001", "91.00")  # A6:COM 收字串
            ]
            assert _sent(com, "decrease") == [("decrease", "1234567890A", "00000000001", 1)]


# ---------------------------------------------------------------------------
# position/close(SC-6)
# ---------------------------------------------------------------------------


class TestPositionClose:
    def test_no_position_403(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cap, _com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            res = client.post(
                "/api/capital/position/close", json={"market": "sec", "key": "2330", "price": 590.0}
            )
            assert res.status_code == 403
            assert "無部位可平" in res.json()["detail"]["reason"]

    def test_sec_close_sends_reverse_order(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            cap.store.set_positions([Position(market="sec", stock_no="2330", qty=2, kind="cash")])
            res = client.post(
                "/api/capital/position/close", json={"market": "sec", "key": "2330", "price": 590.0}
            )
            assert res.status_code == 200
            assert res.json()["ok"] is True
            fields = _sent(com, "stock")[0][1]
            assert isinstance(fields, dict)
            assert fields["sBuySell"] == 1  # 現股多 → 反向賣
            assert fields["nQty"] == 2

    def test_close_body_kind_selects_row(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # body 的 kind 透傳到 client:同檔資+集保並存時精確鍵到融資列(送融資賣)
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            cap.store.set_positions(
                [
                    Position(market="sec", stock_no="2330", qty=2, kind="cash"),
                    Position(market="sec", stock_no="2330", qty=5, kind="margin"),
                ]
            )
            res = client.post(
                "/api/capital/position/close",
                json={"market": "sec", "key": "2330", "price": 590.0, "kind": "margin"},
            )
            assert res.status_code == 200
            fields = _sent(com, "stock")[0][1]
            assert isinstance(fields, dict)
            assert fields["sFlag"] == 1 and fields["nQty"] == 5  # 融資賣、融資列張數

    def test_close_without_kind_ambiguous_403(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            cap.store.set_positions(
                [
                    Position(market="sec", stock_no="2330", qty=2, kind="cash"),
                    Position(market="sec", stock_no="2330", qty=5, kind="margin"),
                ]
            )
            res = client.post(
                "/api/capital/position/close",
                json={"market": "sec", "key": "2330", "price": 590.0},
            )
            assert res.status_code == 403
            detail = res.json()["detail"]
            assert detail["error"] == "ORDER_BLOCKED"
            assert "請指定種類" in detail["reason"]
            assert _sent(com, "stock") == []  # 猜錯種類 = 送錯單種,寧可不送

    def test_close_body_rejects_unknown_kind_422(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # kind 是列舉不是自由字串:錯值該在 wire 層擋(422),不可降級成誤導的「無部位可平」
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            cap.store.set_positions([Position(market="sec", stock_no="2330", qty=2, kind="cash")])
            res = client.post(
                "/api/capital/position/close",
                json={"market": "sec", "key": "2330", "price": 590.0, "kind": "Margin"},
            )
            assert res.status_code == 422
            assert _sent(com, "stock") == []


# ---------------------------------------------------------------------------
# 群益拒單透傳 400 BROKER_REJECTED(review A2/C1/C2)
# ---------------------------------------------------------------------------


class TestBrokerRejected:
    def _assert_rejected(self, res: Any) -> None:
        assert res.status_code == 400
        detail = res.json()["detail"]
        assert detail["error"] == "BROKER_REJECTED"
        assert detail["err_code"] == "1097"
        assert "查無委託" in detail["err_msg"]

    def test_order_stock_reject_400(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cap, _com = _capital_client(tmp_path, com=RejectingCom())
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            self._assert_rejected(client.post("/api/capital/order/stock", json=_STOCK_BODY))

    def test_order_cancel_reject_400(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cap, _com = _capital_client(tmp_path, com=RejectingCom())
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            self._assert_rejected(
                client.post(
                    "/api/capital/order/cancel", json={"seq_no": "00000000001", "market": "sec"}
                )
            )

    def test_correct_price_reject_400(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cap, com = _capital_client(tmp_path, com=RejectingCom())
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            assert com.on_reply is not None
            com.on_reply(_stock_evt_raw("00000000001"))  # store 有此單(排除 R3 逃生口變因)
            self._assert_rejected(
                client.post(
                    "/api/capital/order/correct-price",
                    json={"seq_no": "00000000001", "market": "sec", "price": 91.0},
                )
            )

    def test_correct_price_unknown_seq_passthrough_400(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # C2/SC-4:改價對不存在委託 — store 查無(R3 逃生口)放行送群益,
        # 群益 1097 透傳 400 = 「可辨識錯誤」的最終語意
        cap, com = _capital_client(tmp_path, com=RejectingCom())
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            self._assert_rejected(
                client.post(
                    "/api/capital/order/correct-price",
                    json={"seq_no": "99999999999", "market": "sec", "price": 91.0},
                )
            )
            assert _sent(com, "correct_price")  # 逃生口確實放行到 COM


# ---------------------------------------------------------------------------
# 例外映射(NOT_READY / DOWN;GateBlocked/Disabled 已於上方覆蓋)
# ---------------------------------------------------------------------------


class _FailingLoginCom(FakeCom):
    def login(self, user_id: str, password: str) -> int:
        return 1


class _ExplodingCom(FakeCom):
    def send_stock_order(self, user_id: str, fields: dict[str, object]) -> tuple[str, int]:
        raise RuntimeError("COM boom")


class TestErrorMapping:
    def test_not_ready_503(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cap, _com = _capital_client(tmp_path, com=_FailingLoginCom())
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap, want=("error",))
            res = client.post("/api/capital/order/stock", json=_STOCK_BODY)
            assert res.status_code == 503
            assert res.json()["detail"]["error"] == "CAPITAL_NOT_READY"

    def test_com_exception_502_capital_down(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cap, _com = _capital_client(tmp_path, com=_ExplodingCom())
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            res = client.post("/api/capital/order/stock", json=_STOCK_BODY)
            assert res.status_code == 502
            assert res.json()["detail"]["error"] == "CAPITAL_DOWN"

    def test_audit_write_error_500_audit_write_failed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AuditWriteError → 500 AUDIT_WRITE_FAILED(WLR-1)。

        真正的 raise 點在 CapitalClient 送單前置(審計寫失敗),從 route 觸發要造 IO 故障;
        這裡受測的是 app.py 的 handler 註冊本身(本輪由 _TRADE_ERROR_MAP 迴圈改為獨立
        @app.exception_handler),故用探針 route 直接 raise 鎖住契約 —— frontend
        lib/trade-text.ts 依 AUDIT_WRITE_FAILED 這個字串顯示「單未送出」。
        """

        def _boom() -> None:
            raise AuditWriteError("boom")

        with make_client(
            monkeypatch,
            configure=lambda app: app.add_api_route("/api/_probe/audit-fail", _boom),
        ) as client:
            res = client.get("/api/_probe/audit-fail")
            assert res.status_code == 500
            assert res.json()["detail"]["error"] == "AUDIT_WRITE_FAILED"


# ---------------------------------------------------------------------------
# 舊 trade 路已除役 → 404(remove-tc4-trade-path SC-2)
# ---------------------------------------------------------------------------


_REMOVED_TRADE_ROUTES: list[tuple[str, str]] = [
    ("GET", "/api/trade/account"),
    ("POST", "/api/trade/preview"),
    ("POST", "/api/trade/orders"),
    ("GET", "/api/trade/orders"),
]


class TestTradeRoutesRemoved:
    @pytest.mark.parametrize(("method", "url"), _REMOVED_TRADE_ROUTES)
    def test_trade_route_404_route_gone(
        self, method: str, url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # route 不存在時 404 先於 body 驗證,故 POST 帶空 json 也不會變 422
        with make_client(monkeypatch) as client:
            res = client.request(method, url, json={})
            assert res.status_code == 404, f"{method} {url}"

    def test_known_route_not_404_anchors_the_above(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """對照錨:同一個 app 上已知存在的 route 非 404,證明上面四條 404 是
        「這幾條沒了」而不是「app 根本沒建起來 / client 全打不到」。"""
        with make_client(monkeypatch) as client:
            assert client.get("/api/capital/status").status_code != 404


# ---------------------------------------------------------------------------
# futures 行情 REST + WS(SC-8)
# ---------------------------------------------------------------------------


class TestFuturesState:
    def test_state_200_with_products(self, monkeypatch: pytest.MonkeyPatch) -> None:
        src = FakeFuturesSource()
        with make_client(monkeypatch, futures_source=src) as client:
            res = client.get("/api/futures/state")
            assert res.status_code == 200
            body = res.json()
            assert set(body["products"]) == {"TXF", "MXF", "TMF"}
            assert body["seq"] == 0
            assert src.subscribed == ["TXF", "MXF", "TMF"]
        assert src.closed is True  # lifespan finally close

    def test_engine_absent_503(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with make_client(monkeypatch) as client:
            res = client.get("/api/futures/state")
            assert res.status_code == 503
            assert res.json()["detail"]["error"] == "NOT_READY"


class TestWsBroadcasterBackpressure:
    async def test_overflow_drops_oldest_keeps_newest(self) -> None:
        # review C8:慢連線灌超量 → 丟最舊、保最新(行情/回報都是最新有意義)
        b = WsBroadcaster()
        gen = b.stream()
        try:
            for i in range(_CLIENT_QUEUE_MAX + 5):
                b.publish({"i": i})
            got = [await gen.__anext__() for _ in range(_CLIENT_QUEUE_MAX)]
            assert got[0] == {"i": 5}  # 最舊 0..4 被丟
            assert got[-1] == {"i": _CLIENT_QUEUE_MAX + 4}  # 收尾端 = 最新
        finally:
            await gen.aclose()

    async def test_custom_maxsize_applies_to_client_queue(self) -> None:
        """`maxsize` 參數必須真的傳到 per-client queue(engine 層各自傳值,B-D5)。

        參數若被忽略(queue 一律吃模組常數 500),5 則全進得去 → 讀到的是**最舊** 3 則;
        真的生效才會丟舊保新。上面兩條都用預設值,測不出這個差別。
        """
        b = WsBroadcaster(maxsize=3)
        gen = b.stream()
        try:
            for i in range(5):
                b.publish({"i": i})
            got = [await gen.__anext__() for _ in range(3)]
            assert got == [{"i": 2}, {"i": 3}, {"i": 4}]
        finally:
            await gen.aclose()

    async def test_slow_client_does_not_affect_fast_client(self) -> None:
        b = WsBroadcaster()
        slow = b.stream()
        fast = b.stream()
        try:
            for i in range(_CLIENT_QUEUE_MAX + 3):
                b.publish({"i": i})
            assert await fast.__anext__() == {"i": 3}  # 各自獨立 queue,各自丟舊
            assert await slow.__anext__() == {"i": 3}
        finally:
            await slow.aclose()
            await fast.aclose()


class TestWebSockets:
    def test_ws_futures_streams_quote(self, monkeypatch: pytest.MonkeyPatch) -> None:
        src = FakeFuturesSource()
        with make_client(monkeypatch, futures_source=src) as client:
            assert src.on_message is not None
            with client.websocket_connect("/ws/futures") as ws:
                src.on_message(_fut_quote())
                msg = ws.receive_json()
                assert msg["type"] == "futures"
                assert msg["product"] == "TXF"
                assert msg["state"]["p"] == 23_500_000

    def test_ws_capital_streams_order_event(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cap, com = _capital_client(tmp_path)
        with make_client(monkeypatch, capital=cap) as client:
            _wait_status(cap)
            assert com.on_reply is not None
            with client.websocket_connect("/ws/capital") as ws:
                com.on_reply(_stock_evt_raw("00000000001"))
                # 背景 balance 鏈可能先推 capital_position/capital_status,輪詢至目標事件
                for _ in range(10):
                    msg = ws.receive_json()
                    if msg.get("event") == "capital_order":
                        break
                else:
                    raise AssertionError("等不到 capital_order 事件")
                assert msg["data"]["seq_no"] == "00000000001"
