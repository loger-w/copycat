"""`GET /api/stock/stkfut/contracts/{code}`(stkfut-contracts SC-1)。

catalog 由 boot 時的個股 source 接線(`list_stock_futures`)—— 這條測試同時鎖「接線
有接上」:route 200 代表 app 真的把 source 的查詢能力綁進了 `app.state.stkfut_catalog`,
而不是各自 new 一個 TC4 session(那會多一條登入,且與個股訂閱那條 session 分家)。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import copycat.stkfut_map as stkfut_map
from copycat.server.app import create_app
from copycat.stkfut_map import write_map
from tests.helpers.boot import BootedClient
from tests.helpers.fake_sources import FakeStockSource
from tests.helpers.fake_txo import FakeTxoSource

CATALOG: dict[str, dict] = {
    "2330": {
        "name": "台積電",
        "std": {"prod": "CDF", "contracts": ["202608", "202609"]},
        "mini": {"prod": "QFF", "contracts": ["202608", "202609"]},
    },
    # 對映表查無的產品碼(新上市 / 對映檔過期)—— unit 必須是 null 而不是猜一個值
    "1101": {
        "name": "台泥",
        "std": {"prod": "ZZF", "contracts": ["202609"]},
        "mini": None,
    },
}


def _stkfut_map(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """契約單位對映(隔離版控真檔):CDF=標準 2000、QFF=小型 100。"""
    path = tmp_path / "stkfut_map.json"
    write_map(
        path,
        {
            "2330": {
                "prod": "CDF",
                "name": "台積電",
                "unit": 2000,
                "mini": {"prod": "QFF", "unit": 100},
            }
        },
    )
    monkeypatch.setattr(stkfut_map, "DEFAULT_PATH", path)


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


class TestContractUnits:
    """code review B2/B3:payload 逐腿帶契約單位。

    前端的 ETF 前置閘原本以「股號開頭為 0」推 —— 那是這份資料**今天**的性質,不是
    契約規格。權威判準(後端 `_stkfut_gates`)吃的是單位,前端拿不到就只能猜,而猜錯
    的方向是「放行一張必被拒的真錢單」。單位隨清單一起送出,兩邊從此同一個判準。
    """

    def test_std_and_mini_carry_their_contract_unit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stkfut_map(tmp_path, monkeypatch)
        client, _ = make_client(tmp_path)
        with client:
            body = client.get("/api/stock/stkfut/contracts/2330").json()
        assert body["std"]["unit"] == 2000
        assert body["mini"]["unit"] == 100
        # 既有欄位不得因此改形(前端 contracts 清單仍逐字讀這兩個鍵)
        assert body["std"]["prod"] == "CDF"
        assert body["std"]["contracts"] == ["202608", "202609"]

    def test_unknown_product_unit_is_null_not_guessed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """對映表查無 → null。塞 0 或省略欄位都會讓前端把它讀成「非股票單位」→
        誤擋一檔本來可以下單的標的(而後端那道真閘根本沒被觸發)。"""
        _stkfut_map(tmp_path, monkeypatch)
        client, _ = make_client(tmp_path)
        with client:
            body = client.get("/api/stock/stkfut/contracts/1101").json()
        assert body["std"]["unit"] is None
        assert body["mini"] is None


class TestCatalogPrewarm:
    """code review A3:boot 尾段預熱一次,冷查詢移出盤中熱路徑。

    冷 cache 的第一次 `QUERYALLINSTRUMENT(Fut2)` 是秒級(Opt 實測 1.93s)且**持鎖**
    —— 開盤瞬間第一個開下拉的請求要等它,而那正是最不能等的時刻。
    """

    def test_boot_loads_the_catalog_once_before_any_request(self, tmp_path: Path) -> None:
        client, fake = make_client(tmp_path)
        with client:
            assert fake.stkfut_calls == 1  # 尚未打任何 route
            assert client.get("/api/stock/stkfut/contracts/2330").status_code == 200
            assert fake.stkfut_calls == 1  # 當日 cache 命中,不再問 TC4

    def test_prewarm_failure_does_not_abort_boot(self, tmp_path: Path) -> None:
        """TC4 沒開的早上照樣要開得起來:預熱失敗只降級成「第一次請求時再查」。"""
        fake = FakeStockSource()
        fake.stkfut_catalog = ConnectionError("tc4 down")
        app = create_app(
            FakeTxoSource(),
            stock_source=fake,
            stock_watchlist_path=tmp_path / "watchlist.json",
            throttle_secs=0.01,
        )
        with BootedClient(app, raise_server_exceptions=False) as client:
            assert app.state.boot_error is None
            assert client.get("/api/stock/stkfut/contracts/2330").status_code == 502
