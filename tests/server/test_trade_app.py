"""SC-11(capital-order):TC4 TradeRuntime 停用 — /api/trade/* 一律 503,舊 source 不啟動。

原本此檔測 preview/submit/錯誤映射的 HTTP 流(經 TradeRuntime);lifespan 停用後
routes 保留但 state.trade 恆 None → 全部 503 TRADE_NOT_READY。TradeRuntime 本身的
gate/preview/submit 邏輯仍由 tests/server/test_trade_gates.py 直測覆蓋(trade.py 不退役)。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient

from copycat.live.models import OptionContract, SeriesInfo, Tick
from copycat.live.trade_models import AccountInfo, OrderReport
from copycat.server.app import create_app

C23000 = OptionContract(symbol="TC.O.TWF.TXO.202607.C.23000", cp="C", strike_millipts=23_000_000)
SERIES = SeriesInfo(series_id="TXO.202607", name="TXO 202607", expiry="202607", contracts=(C23000,))


class FakeQuoteSource:
    def __init__(self) -> None:
        self.closed = False

    def list_series(self) -> list[SeriesInfo]:
        return [SERIES]

    def fetch_backfill(self, series: SeriesInfo) -> list[Tick]:
        return []

    def subscribe(self, series: SeriesInfo, on_tick: Callable[[Tick], None]) -> None:
        return None

    def unsubscribe(self, series: SeriesInfo) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class FakeTrade:
    """舊 TC4 trade source 治具:任何方法被呼叫都記進 calls(SC-11 斷言不得啟動)。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def accounts(self) -> list[AccountInfo]:
        self.calls.append("accounts")
        return []

    def place_order(self, param: dict[str, str]) -> dict:
        self.calls.append("place_order")
        return {"Success": "OK"}

    def restore_reports(self) -> list[OrderReport]:
        self.calls.append("restore_reports")
        return []

    def restore_fills(self) -> list[OrderReport]:
        self.calls.append("restore_fills")
        return []

    def subscribe_reports(self, on_report: Any, on_reconnect: Any) -> None:
        self.calls.append("subscribe_reports")

    def close(self) -> None:
        self.calls.append("close")


def make_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    trade: FakeTrade | None,
    quote: FakeQuoteSource | None = None,
) -> TestClient:
    monkeypatch.setenv("TXO_AUDIT_DIR", str(tmp_path / "audit"))
    monkeypatch.delenv("DQ4_LIVE", raising=False)
    return TestClient(
        create_app(
            quote if quote is not None else FakeQuoteSource(),
            trade_source=trade,
            throttle_secs=0.01,
        ),
        raise_server_exceptions=False,
    )


_PREVIEW_BODY = {
    "symbol": C23000.symbol,
    "side": "buy",
    "kind": "limit",
    "qty": 1,
    "price": "15.5",
}

_TRADE_ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", "/api/trade/account", None),
    ("POST", "/api/trade/preview", _PREVIEW_BODY),
    ("POST", "/api/trade/orders", {"preview_id": "x"}),
    ("GET", "/api/trade/orders", None),
]


class TestTradeRoutesDisabled:
    def test_all_routes_503_even_with_source(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SC-11:即使傳入 trade_source,lifespan 不再啟動 TradeRuntime → 一律 503。"""
        with make_client(tmp_path, monkeypatch, FakeTrade()) as client:
            client.post("/api/txo/select", json={"series_id": SERIES.series_id})
            for method, url, body in _TRADE_ROUTES:
                res = client.request(method, url, json=body)
                assert res.status_code == 503, url
                assert res.json()["detail"]["error"] == "TRADE_NOT_READY", url

    def test_no_trade_source_is_not_ready(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with make_client(tmp_path, monkeypatch, None) as client:
            for method, url, body in _TRADE_ROUTES:
                res = client.request(method, url, json=body)
                assert res.status_code == 503, url
                assert res.json()["detail"]["error"] == "TRADE_NOT_READY", url

    def test_trade_source_never_started(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """舊 source 完全不被觸碰(不啟動也不 close — 從未開啟過)。"""
        trade = FakeTrade()
        with make_client(tmp_path, monkeypatch, trade):
            pass
        assert trade.calls == []

    def test_quote_unaffected_and_closed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """trade 停用不得波及看盤;關機仍正常清理 quote runtime。"""
        quote = FakeQuoteSource()
        with make_client(tmp_path, monkeypatch, FakeTrade(), quote=quote) as client:
            client.post("/api/txo/select", json={"series_id": SERIES.series_id})
            assert client.get("/api/txo/snapshot").status_code == 200
        assert quote.closed is True
