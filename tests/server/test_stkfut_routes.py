"""`GET /api/stock/stkfut/contracts/{code}`(stkfut-contracts SC-1)。

catalog 由 boot 時的個股 source 接線(`list_stock_futures`)—— 這條測試同時鎖「接線
有接上」:route 200 代表 app 真的把 source 的查詢能力綁進了 `app.state.stkfut_catalog`,
而不是各自 new 一個 TC4 session(那會多一條登入,且與個股訂閱那條 session 分家)。
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from copycat.server.app import create_app
from tests.helpers.boot import BootedClient
from tests.helpers.fake_sources import FakeStockSource
from tests.helpers.fake_txo import FakeTxoSource

CATALOG: dict[str, dict] = {
    "2330": {
        "name": "台積電",
        "std": {"prod": "CDF", "contracts": ["202608", "202609"]},
        "mini": {"prod": "QFF", "contracts": ["202608", "202609"]},
    },
}


def make_client(tmp_path: Path) -> tuple[TestClient, FakeStockSource]:
    fake = FakeStockSource()
    fake.stkfut_catalog = {k: dict(v) for k, v in CATALOG.items()}
    app = create_app(
        FakeTxoSource(),
        stock_source=fake,
        stock_watchlist_path=tmp_path / "watchlist.json",
        throttle_secs=0.01,
    )
    return BootedClient(app, raise_server_exceptions=False), fake


class TestContractsRoute:
    def test_returns_std_and_mini(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)
        with client:
            r = client.get("/api/stock/stkfut/contracts/2330")
        assert r.status_code == 200
        body = r.json()
        assert body["code"] == "2330"
        assert body["name"] == "台積電"
        assert body["std"] == {"prod": "CDF", "contracts": ["202608", "202609"]}
        assert body["mini"]["prod"] == "QFF"

    def test_no_futures_404(self, tmp_path: Path) -> None:
        """無期貨的股票 → 404 NO_STKFUT(前端據此不渲染下拉)。"""
        client, _ = make_client(tmp_path)
        with client:
            r = client.get("/api/stock/stkfut/contracts/9999")
        assert r.status_code == 404
        assert r.json()["detail"]["error"] == "NO_STKFUT"

    def test_bad_code_400(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)
        with client:
            r = client.get("/api/stock/stkfut/contracts/bad!")
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "BAD_CODE"

    def test_tc4_down_502(self, tmp_path: Path) -> None:
        client, fake = make_client(tmp_path)
        fake.stkfut_catalog = ConnectionError("tc4 down")
        with client:
            r = client.get("/api/stock/stkfut/contracts/2330")
        assert r.status_code == 502
        assert r.json()["detail"]["error"] == "TC4_DOWN"

    def test_engine_missing_503(self) -> None:
        """引擎未就緒優先於代號閘(既有 `/api/stock/state` 同優先序)。"""
        app = create_app(FakeTxoSource(), throttle_secs=0.01)
        with BootedClient(app, raise_server_exceptions=False) as client:
            r = client.get("/api/stock/stkfut/contracts/@@@")
        assert r.status_code == 503
        assert r.json()["detail"]["error"] == "NOT_READY"
