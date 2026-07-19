"""SC-6/7:/api/trade/* 契約、錯誤碼 HTTP 對映、與 quote 路徑隔離。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient

from copycat.live.models import OptionContract, SeriesInfo, Tick
from copycat.live.trade_models import (
    AccountInfo,
    BrokerRejectedError,
    OrderReport,
    TouchanceDownError,
)
from copycat.server.app import create_app

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


class FakeTrade:
    def __init__(self) -> None:
        self.account_list = [
            AccountInfo(broker_id="SIM", account="9999000", account_mask="SIM-9999000", raw={})
        ]
        self.place_error: Exception | None = None
        self.place_calls: list[dict[str, str]] = []

    def accounts(self) -> list[AccountInfo]:
        return self.account_list

    def place_order(self, param: dict[str, str]) -> dict:
        self.place_calls.append(param)
        if self.place_error is not None:
            raise self.place_error
        return {"Success": "OK"}

    def restore_reports(self) -> list[OrderReport]:
        return []

    def restore_fills(self) -> list[OrderReport]:
        return []

    def subscribe_reports(self, on_report: Any, on_reconnect: Any) -> None:
        return None

    def close(self) -> None:
        return None


def make_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    trade: FakeTrade | None,
) -> TestClient:
    monkeypatch.setenv("TXO_AUDIT_DIR", str(tmp_path / "audit"))
    monkeypatch.delenv("DQ4_LIVE", raising=False)
    return TestClient(
        create_app(FakeQuoteSource(), trade_source=trade, throttle_secs=0.01),
        raise_server_exceptions=False,
    )


def do_preview(client: TestClient, **overrides: Any) -> Any:
    body: dict[str, Any] = {
        "symbol": C23000.symbol,
        "side": "buy",
        "kind": "limit",
        "qty": 1,
        "price": "15.5",
    }
    body.update(overrides)
    return client.post("/api/trade/preview", json=body)


class TestAccountRoute:
    def test_account_with_orderable_symbols(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with make_client(tmp_path, monkeypatch, FakeTrade()) as client:
            client.post("/api/txo/select", json={"series_id": SERIES.series_id})
            res = client.get("/api/trade/account")
            assert res.status_code == 200
            body = res.json()
            assert body["mode"] == "sim"
            assert body["status"] == "ready"
            assert C23000.symbol in body["orderable_symbols"]
            assert "TC.F.TWF.FITX.HOT" in body["orderable_symbols"]

    def test_no_trade_source_is_not_ready(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with make_client(tmp_path, monkeypatch, None) as client:
            preview_body = {
                "symbol": C23000.symbol,
                "side": "buy",
                "kind": "limit",
                "qty": 1,
                "price": "15.5",
            }
            for method, url, body in [
                ("GET", "/api/trade/account", None),
                ("POST", "/api/trade/preview", preview_body),
                ("POST", "/api/trade/orders", {"preview_id": "x"}),
                ("GET", "/api/trade/orders", None),
            ]:
                res = client.request(method, url, json=body)
                assert res.status_code == 503, url
                assert res.json()["detail"]["error"] == "TRADE_NOT_READY"


class TestPreviewSubmit:
    def test_happy_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        trade = FakeTrade()
        with make_client(tmp_path, monkeypatch, trade) as client:
            client.post("/api/txo/select", json={"series_id": SERIES.series_id})
            pv = do_preview(client)
            assert pv.status_code == 200
            preview_id = pv.json()["preview_id"]
            res = client.post("/api/trade/orders", json={"preview_id": preview_id})
            assert res.status_code == 200
            assert trade.place_calls[0]["Price"] == "15.5"

    def test_submit_without_preview(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        with make_client(tmp_path, monkeypatch, FakeTrade()) as client:
            res = client.post("/api/trade/orders", json={"preview_id": "ghost"})
            assert res.status_code == 400
            assert res.json()["detail"]["error"] == "CONFIRM_REQUIRED"

    def test_invalid_price(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        with make_client(tmp_path, monkeypatch, FakeTrade()) as client:
            client.post("/api/txo/select", json={"series_id": SERIES.series_id})
            res = do_preview(client, price="abc")
            assert res.status_code == 400
            assert res.json()["detail"]["error"] == "INVALID_ORDER"

    def test_limit_without_price(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        with make_client(tmp_path, monkeypatch, FakeTrade()) as client:
            client.post("/api/txo/select", json={"series_id": SERIES.series_id})
            res = do_preview(client, price=None)
            assert res.status_code == 400
            assert res.json()["detail"]["error"] == "INVALID_ORDER"

    def test_symbol_not_allowed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        with make_client(tmp_path, monkeypatch, FakeTrade()) as client:
            client.post("/api/txo/select", json={"series_id": SERIES.series_id})
            res = do_preview(client, symbol="TC.O.TWF.TXO.209912.C.1")
            assert res.status_code == 400
            assert res.json()["detail"]["error"] == "SYMBOL_NOT_ALLOWED"


class TestErrorMapping:
    def test_broker_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        trade = FakeTrade()
        trade.place_error = BrokerRejectedError("-22", "tick size")
        with make_client(tmp_path, monkeypatch, trade) as client:
            client.post("/api/txo/select", json={"series_id": SERIES.series_id})
            preview_id = do_preview(client).json()["preview_id"]
            res = client.post("/api/trade/orders", json={"preview_id": preview_id})
            assert res.status_code == 400
            detail = res.json()["detail"]
            assert detail["error"] == "BROKER_REJECTED"
            assert detail["err_code"] == "-22"

    def test_touchance_down_and_quote_unaffected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        trade = FakeTrade()
        trade.place_error = TouchanceDownError("down")
        with make_client(tmp_path, monkeypatch, trade) as client:
            client.post("/api/txo/select", json={"series_id": SERIES.series_id})
            preview_id = do_preview(client).json()["preview_id"]
            res = client.post("/api/trade/orders", json={"preview_id": preview_id})
            assert res.status_code == 502
            assert res.json()["detail"]["error"] == "TOUCHANCE_DOWN"
            assert client.get("/api/txo/snapshot").status_code == 200  # 隔離:看盤不受影響

    def test_live_blocked(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        trade = FakeTrade()
        trade.account_list = [
            AccountInfo(broker_id="F999", account="1234567", account_mask="F999-1234567", raw={})
        ]
        with make_client(tmp_path, monkeypatch, trade) as client:
            client.post("/api/txo/select", json={"series_id": SERIES.series_id})
            res = do_preview(client)
            assert res.status_code == 403
            assert res.json()["detail"]["error"] == "LIVE_DISABLED"


class TestOrdersRoute:
    def test_orders_view_shape(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        with make_client(tmp_path, monkeypatch, FakeTrade()) as client:
            res = client.get("/api/trade/orders")
            assert res.status_code == 200
            body = res.json()
            assert body["orders"] == []
            assert body["fills"] == []
            assert body["degraded"] is False
            assert body["audit_degraded"] is False
