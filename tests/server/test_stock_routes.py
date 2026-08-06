from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient

from copycat.server.app import create_app
from copycat.server.signal_hub import SignalHub
from copycat.server.stock_engine import StockEngine
from copycat.stock_watchlist import save_watchlist
from tests.helpers.boot import BootedClient
from tests.helpers.fake_sources import FakeStockSource
from tests.helpers.fake_txo import FakeTxoSource


def make_client(
    tmp_path: Path, *, names_path: Path | None = None
) -> tuple[TestClient, FakeStockSource]:
    fake = FakeStockSource()
    app = create_app(
        FakeTxoSource(),
        stock_source=fake,
        stock_watchlist_path=tmp_path / "watchlist.json",
        stock_names_path=names_path,
        throttle_secs=0.01,
    )
    return BootedClient(app, raise_server_exceptions=False), fake


class _FailingStartStockSource(FakeStockSource):
    """start() 途中拋例外的 source(`set_trade_date` 是 StockEngine.start 的第一步)。"""

    def __init__(self) -> None:
        super().__init__()
        self.closed = False

    def set_trade_date(self, trade_date: str) -> None:
        raise RuntimeError("boom during start")

    def close(self) -> None:
        self.closed = True


class _ClosingStockSource(FakeStockSource):
    """start 全程正常、只記 `close()` 有沒有被呼叫。"""

    def __init__(self) -> None:
        super().__init__()
        self.closed = False

    def close(self) -> None:
        self.closed = True


class TestEngineStartFailureDegrades:
    """characterization(refactor C7 前置):引擎起停樣板的降級契約。

    `_boot` 即將把五段 try/except 收成一支,而**建構成功但 start 失敗**是最容易在
    重構中掉的分支 —— 掉了會洩漏一條已連線的 TC4 session,且畫面只會看到 503。
    """

    def test_start_exception_closes_source_and_app_still_serves_503(self, tmp_path: Path) -> None:
        fake = _FailingStartStockSource()
        app = create_app(
            FakeTxoSource(),
            stock_source=fake,
            stock_watchlist_path=tmp_path / "watchlist.json",
            throttle_secs=0.01,
        )
        client = BootedClient(app, raise_server_exceptions=False)
        with client:
            r = client.get("/api/stock/watchlist")
        assert r.status_code == 503
        assert r.json()["detail"]["error"] == "NOT_READY"
        assert fake.closed, "start 失敗必須關掉已建好的 source(否則洩漏 TC4 session)"

    def test_bad_watchlist_file_degrades_and_closes_source(self, tmp_path: Path) -> None:
        """壞自選檔 = `_start_stock` 的**第二段**失敗(source 本身完全正常)。

        `load_watchlist` 對壞檔不吞例外,而它留在 `_boot` 的 try 內是行為契約 ——
        把自選回填移到 try 外(看起來只是「起完引擎再補資料」)會讓壞檔變成
        lifespan 例外整台 server 起不來,而不是個股功能單獨降級。
        """
        (tmp_path / "watchlist.json").write_text("{not json", encoding="utf-8")
        fake = _ClosingStockSource()
        app = create_app(
            FakeTxoSource(),
            stock_source=fake,
            stock_watchlist_path=tmp_path / "watchlist.json",
            throttle_secs=0.01,
        )
        client = BootedClient(app, raise_server_exceptions=False)
        with client:
            r = client.get("/api/stock/watchlist")
        assert r.status_code == 503
        assert r.json()["detail"]["error"] == "NOT_READY"
        assert fake.closed is True, "回填失敗一樣要關掉已建好的 source"


class TestStockNamesRoute:
    """搜尋提示列的名稱表(round4 項 1)。表是版控檔 → 降級路徑必須靠注入點才測得到。"""

    def test_returns_versioned_table(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)  # names_path=None → 用版控檔
        with client:
            body = client.get("/api/stock/names").json()
        assert body["count"] == len(body["names"])
        assert body["count"] > 1_800  # 版控檔實測 2,401
        assert {"code": "2330", "name": "台積電"} in body["names"]

    def test_missing_table_returns_empty_not_500(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path, names_path=tmp_path / "nope.json")
        with client:
            r = client.get("/api/stock/names")
        assert r.status_code == 200
        assert r.json() == {"names": [], "count": 0}

    def test_corrupt_table_returns_empty_not_500(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{oops", encoding="utf-8")
        client, _ = make_client(tmp_path, names_path=bad)
        with client:
            r = client.get("/api/stock/names")
        assert r.status_code == 200
        assert r.json() == {"names": [], "count": 0}

    def test_available_without_tc4(self, tmp_path: Path) -> None:
        """名稱表與 TC4 連線無關:達錢 4 沒開(stock engine 未就緒)也要能搜尋。"""
        app = create_app(FakeTxoSource(), throttle_secs=0.01)  # 無 stock_source
        with BootedClient(app, raise_server_exceptions=False) as client:
            assert client.get("/api/stock/names").status_code == 200


class TestWatchlistRoutes:
    """v3 shape `{codes, groups}`(stock-ui-round5 §🔴-5);舊 groups-only body 仍相容."""

    def test_get_empty_then_put_round_trip(self, tmp_path: Path) -> None:
        client, fake = make_client(tmp_path)
        with client:
            assert client.get("/api/stock/watchlist").json() == {"codes": [], "groups": []}
            groups = [
                {"name": "主力", "codes": ["2330", "5483"]},
                {"name": "觀察", "codes": ["3231"]},
            ]
            body = {"codes": ["2330", "5483", "3231"], "groups": groups}
            r = client.put("/api/stock/watchlist", json=body)
            assert r.status_code == 200
            assert r.json() == body
            assert client.get("/api/stock/watchlist").json() == body
            assert "2330" in fake.subscribed and "3231" in fake.subscribed  # 全體已訂

    def test_put_without_codes_defaults_to_union(self, tmp_path: Path) -> None:
        """舊 client 只送 groups → 存檔結果與 v2 時代逐字元相同(codes = 聯集)."""
        client, _ = make_client(tmp_path)
        with client:
            groups = [
                {"name": "主力", "codes": ["2330", "5483"]},
                {"name": "觀察", "codes": ["3231", "2330"]},
            ]
            r = client.put("/api/stock/watchlist", json={"groups": groups})
            assert r.status_code == 200
            assert r.json() == {"codes": ["2330", "5483", "3231"], "groups": groups}

    def test_ungrouped_code_enters_subscription_pool(self, tmp_path: Path) -> None:
        """SC-18 的機械守門:不屬任何群組的 code 也要進 set_watchlist."""
        client, fake = make_client(tmp_path)
        with client:
            r = client.put(
                "/api/stock/watchlist",
                json={
                    "codes": ["2330", "5483"],
                    "groups": [{"name": "主力", "codes": ["2330"]}],
                },
            )
            assert r.status_code == 200
            assert r.json()["codes"] == ["2330", "5483"]
            assert "5483" in fake.subscribed

    def test_put_bad_code_400(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)
        with client:
            body = {"groups": [{"name": "a", "codes": ["bad code"]}]}
            r = client.put("/api/stock/watchlist", json=body)
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "BAD_CODE"

    def test_put_bad_group_400(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)
        with client:
            body = {"groups": [{"name": "  ", "codes": ["2330"]}]}
            r = client.put("/api/stock/watchlist", json=body)
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "BAD_GROUP"

    def test_put_over_limit_400(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)
        with client:
            codes = [f"{1000 + i}" for i in range(31)]
            r = client.put("/api/stock/watchlist", json={"groups": [{"name": "a", "codes": codes}]})
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "WATCHLIST_FULL"

    def test_watchlist_persists_across_app_restart(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)
        with client:
            client.put(
                "/api/stock/watchlist", json={"groups": [{"name": "自選", "codes": ["2330"]}]}
            )
        client2, fake2 = make_client(tmp_path)
        with client2:
            assert client2.get("/api/stock/watchlist").json() == {
                "codes": ["2330"],
                "groups": [{"name": "自選", "codes": ["2330"]}],
            }
            assert "2330" in fake2.subscribed  # 啟動即訂回持久化清單

    def test_v1_file_restores_codes_on_startup(self, tmp_path: Path) -> None:
        """v1 檔(codes shape)重啟 → 全部落未分組,codes 仍進訂閱池(🔴 行為改)."""
        import json as _json

        (tmp_path / "watchlist.json").write_text(
            _json.dumps({"_cache_version": 1, "codes": ["2330", "5483"]}), encoding="utf-8"
        )
        client, fake = make_client(tmp_path)
        with client:
            assert client.get("/api/stock/watchlist").json() == {
                "codes": ["2330", "5483"],
                "groups": [],
            }
            assert "2330" in fake.subscribed and "5483" in fake.subscribed

    def test_v2_file_restores_union_on_startup(self, tmp_path: Path) -> None:
        """v2 檔(groups shape)重啟 → codes 由聯集補,畫面零差異(SC-17)."""
        import json as _json

        (tmp_path / "watchlist.json").write_text(
            _json.dumps(
                {"_cache_version": 2, "groups": [{"name": "主力", "codes": ["2330", "5483"]}]}
            ),
            encoding="utf-8",
        )
        client, fake = make_client(tmp_path)
        with client:
            assert client.get("/api/stock/watchlist").json() == {
                "codes": ["2330", "5483"],
                "groups": [{"name": "主力", "codes": ["2330", "5483"]}],
            }
            assert "2330" in fake.subscribed and "5483" in fake.subscribed


class TestOverlayRoute:
    """SC-4:/api/stock/overlay/{code} — 200 形狀 / BAD_CODE / TC4 down 全 null."""

    BARS = [
        {"date": f"2026-06-{d:02d}", "high": 103_000, "low": 100_000, "close": 100_000 + d * 100}
        for d in range(1, 27)
    ]

    def test_overlay_shape_200(self, tmp_path: Path) -> None:
        client, fake = make_client(tmp_path)
        fake.daily_bars_result = list(self.BARS)
        with client:
            r = client.get("/api/stock/overlay/2330")
            assert r.status_code == 200
            body = r.json()
            assert set(body) == {"cdp", "ma5", "ma20", "date"}
            assert body["date"] == "2026-06-26"
            assert set(body["cdp"]) == {"cdp", "ah", "nh", "nl", "al"}
            assert isinstance(body["ma5"], int) and isinstance(body["ma20"], int)

    def test_overlay_bad_code_400(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)
        with client:
            r = client.get("/api/stock/overlay/bad!")
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "BAD_CODE"

    def test_overlay_tc4_down_returns_all_null_200(self, tmp_path: Path) -> None:
        client, fake = make_client(tmp_path)
        fake.daily_bars_result = ConnectionError("tc4 down")
        with client:
            r = client.get("/api/stock/overlay/2330")
            assert r.status_code == 200
            assert r.json() == {"cdp": None, "ma5": None, "ma20": None, "date": None}


class TestStateRoute:
    def test_get_state_sets_main_and_returns_snapshot(self, tmp_path: Path) -> None:
        client, fake = make_client(tmp_path)
        with client:
            r = client.get("/api/stock/state/2330")
            assert r.status_code == 200
            snap = r.json()
            assert snap["code"] == "2330"
            assert snap["seq"] == 0
            assert "2330" in fake.subscribed  # main owner 已訂

    def test_get_state_bad_code_400(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)
        with client:
            r = client.get("/api/stock/state/bad!")
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "BAD_CODE"

    def test_engine_missing_beats_bad_code(self) -> None:
        """引擎未就緒 + 代號非法 → 503 不是 400(`_valid_code` 在 `_stock` 之後的優先序)。

        把代號閘做成 `Depends` 看起來更整齊,但 FastAPI 會在 handler body 之前跑它 ——
        優先序會靜默翻成 400,前端就把「達錢 4 沒開」誤顯示成「代號打錯」。
        """
        app = create_app(FakeTxoSource(), throttle_secs=0.01)  # 無 stock_source
        with BootedClient(app, raise_server_exceptions=False) as client:
            r = client.get("/api/stock/state/@@@")
        assert r.status_code == 503
        assert r.json()["detail"]["error"] == "NOT_READY"


STKFUT_CATALOG: dict[str, dict] = {
    "2330": {
        "name": "台積電",
        "std": {"prod": "CDF", "contracts": ["202608", "202609"]},
        "mini": {"prod": "QFF", "contracts": ["202609"]},
    },
    "2317": {
        "name": "鴻海",
        "std": {"prod": "DHF", "contracts": ["202608", "202609"]},
        "mini": None,
    },
}


class TestStateRouteContract:
    """`?contract=` 主圖合約切換(stkfut-contracts SC-3 / D6+D7)。

    **白名單是這組測試的核心**:regex 過得了不代表這個合約屬於這檔股票 ——
    `/api/stock/state/2330?contract=DHF:202609` 光看形狀完全合法,放行的話主圖畫的是
    鴻海期貨,而 URL、下單面、右側欄的股號全都還是 2330,畫面上沒有任何地方會不一致
    到被看出來(TC4 對不存在 / 不相干的 symbol 一律照回 `Success: OK`,連訂閱層都不會
    抗議)。所以合法性判定只能來自 catalog,不能只靠字串形。
    """

    def _client(self, tmp_path: Path) -> tuple[TestClient, FakeStockSource]:
        client, fake = make_client(tmp_path)
        fake.stkfut_catalog = {k: dict(v) for k, v in STKFUT_CATALOG.items()}
        return client, fake

    def test_valid_contract_switches_main_and_returns_instrument_key(self, tmp_path: Path) -> None:
        client, fake = self._client(tmp_path)
        with client:
            r = client.get("/api/stock/state/2330?contract=CDF:202609")
        assert r.status_code == 200
        snap = r.json()
        # code = instrument key(前端 WS 比對鍵);underlying = 股號(下單/右欄口徑)
        assert snap["code"] == "F:CDF:202609"
        assert snap["underlying"] == "2330"
        assert "F:CDF:202609" in fake.subscribed, "set_main_contract 必須真的訂到合約鍵"

    def test_mini_contract_allowed(self, tmp_path: Path) -> None:
        """小型合約也在白名單內(std / mini 兩腿都要查,只查 std 會讓小型永遠 400)。"""
        client, fake = self._client(tmp_path)
        with client:
            r = client.get("/api/stock/state/2330?contract=QFF:202609")
        assert r.status_code == 200
        assert r.json()["code"] == "F:QFF:202609"
        assert "F:QFF:202609" in fake.subscribed

    def test_no_contract_keeps_spot_behaviour(self, tmp_path: Path) -> None:
        """現貨態零行為變更;`underlying` 在現貨態 = code 自身(前端單一讀法)。"""
        client, fake = self._client(tmp_path)
        with client:
            r = client.get("/api/stock/state/2330")
        assert r.status_code == 200
        snap = r.json()
        assert snap["code"] == "2330"
        assert snap["underlying"] == "2330"
        assert "2330" in fake.subscribed

    def test_foreign_product_rejected(self, tmp_path: Path) -> None:
        """形狀合法但產品屬於別檔股票 → 400(白名單的存在理由)。"""
        client, fake = self._client(tmp_path)
        with client:
            r = client.get("/api/stock/state/2330?contract=DHF:202609")
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "BAD_CONTRACT"
        assert "F:DHF:202609" not in fake.subscribed, "被拒的合約不得留下訂閱"

    def test_unknown_month_rejected(self, tmp_path: Path) -> None:
        """產品對、月份不在清單(已到期 / 尚未掛牌)→ 400。

        放行的話會訂到不存在的 symbol,而 TC4 照回 OK → 表現為「圖是空的」。
        """
        client, fake = self._client(tmp_path)
        with client:
            r = client.get("/api/stock/state/2330?contract=CDF:202612")
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "BAD_CONTRACT"
        assert "F:CDF:202612" not in fake.subscribed

    def test_stock_without_futures_rejected(self, tmp_path: Path) -> None:
        client, _ = self._client(tmp_path)
        with client:
            r = client.get("/api/stock/state/9999?contract=CDF:202609")
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "BAD_CONTRACT"

    @pytest.mark.parametrize(
        "contract",
        [
            "CDF-202609",  # 分隔符錯
            "CDF:2026",  # 缺月
            "cdf:202609",  # 小寫
            "CDF:202613",  # 月份 13
            "CDF:202600",  # 月份 00
            "CDF:192609",  # 世紀非 20
            "C:202609",  # 產品碼過短
            "CDFFF:202609",  # 產品碼過長
            "CDF:202609:X",  # 尾贅
            "F:CDF:202609",  # 直接把 instrument key 當 contract 塞
            "",  # 空字串(前端狀態清空時最容易誤送)
        ],
    )
    def test_malformed_contract_rejected(self, tmp_path: Path, contract: str) -> None:
        """形檢在白名單之前:壞形不該打到 catalog(那是一次 TC4 查詢)。"""
        client, fake = self._client(tmp_path)
        with client:
            r = client.get("/api/stock/state/2330", params={"contract": contract})
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "BAD_CONTRACT"
        assert fake.subscribed == [], "被拒的請求不得動到訂閱池"

    def test_catalog_down_rejects_not_falls_back_to_spot(self, tmp_path: Path) -> None:
        """catalog 查不到 → 502,**不放行**。

        降級成「當作現貨處理」會讓 TC4 一斷線畫面就悄悄從期貨跳回現貨,而下拉還顯示著
        合約 —— 使用者看著的是另一個商品的價格。
        """
        client, fake = self._client(tmp_path)
        fake.stkfut_catalog = ConnectionError("tc4 down")
        with client:
            r = client.get("/api/stock/state/2330?contract=CDF:202609")
        assert r.status_code == 502
        assert r.json()["detail"]["error"] == "TC4_DOWN"
        assert fake.subscribed == []

    def test_bad_code_beats_contract_check(self, tmp_path: Path) -> None:
        """代號閘優先(既有優先序不變):壞代號 + 壞合約 → BAD_CODE。"""
        client, _ = self._client(tmp_path)
        with client:
            r = client.get("/api/stock/state/bad!?contract=nope")
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "BAD_CODE"


class TestGroupStateRoute:
    """群組檢視的唯讀 batch(group-grid SC-4)。

    **這條路存在的唯一理由就是不 set_main**:群組檢視每分鐘會對最多 30 檔各要一次
    狀態,重用 `/api/stock/state/{code}` 等於每分鐘把主圖搶走 30 次 → 主圖分時線凍結,
    而畫面上只表現為「圖不動了」,沒有任何錯誤。所以 `_main` 的斷言是本組的核心。
    """

    def _put(self, client: TestClient, codes: list[str]) -> None:
        r = client.put("/api/stock/watchlist", json={"codes": codes, "groups": []})
        assert r.status_code == 200

    def test_batch_shape_and_never_sets_main(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)
        with client:
            self._put(client, ["2330", "2317"])
            r = client.get("/api/stock/group-state", params={"codes": "2330,2317"})
            assert r.status_code == 200
            states = r.json()["states"]
            assert set(states) == {"2330", "2317"}
            # payload 形寫死:ticks 不得混進來(30 檔 × 數千筆 = 頻寬炸彈)
            assert set(states["2330"]) == {"minutes", "meta", "no_data", "backfilling"}
            assert states["2330"]["no_data"] is False
            stock = cast("StockEngine", client.app.state.stock)  # type: ignore[attr-defined]
            assert stock._main is None, "群組 batch 不得 set_main(會把主圖搶走)"

    def test_empty_codes_returns_empty_states(self, tmp_path: Path) -> None:
        """空群組 → 前端 hook 是 enabled=false 零請求;真的打到也必須是 200 空表。"""
        client, _ = make_client(tmp_path)
        with client:
            assert client.get("/api/stock/group-state").json() == {"states": {}}
            r = client.get("/api/stock/group-state", params={"codes": ""})
            assert r.status_code == 200
            assert r.json() == {"states": {}}

    def test_unknown_code_is_no_data_not_404(self, tmp_path: Path) -> None:
        """未訂閱 / 查無此檔對卡片是同一件事(「這格畫不出東西」)→ 無 404 路徑。"""
        client, _ = make_client(tmp_path)
        with client:
            states = client.get("/api/stock/group-state", params={"codes": "9999"}).json()["states"]
            assert states["9999"]["no_data"] is True
            assert states["9999"]["minutes"] == {}
            assert states["9999"]["meta"] is None

    def test_too_many_codes_400(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)
        with client:
            codes = ",".join(f"{9000 + i}" for i in range(31))  # 自選上限 30
            r = client.get("/api/stock/group-state", params={"codes": codes})
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "BAD_CODES"

    def test_bad_code_400(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)
        with client:
            r = client.get("/api/stock/group-state", params={"codes": "2330,bad!"})
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "BAD_CODE"

    def test_engine_missing_503(self) -> None:
        app = create_app(FakeTxoSource(), throttle_secs=0.01)  # 無 stock_source
        with BootedClient(app, raise_server_exceptions=False) as client:
            r = client.get("/api/stock/group-state", params={"codes": "@@@"})
        assert r.status_code == 503
        assert r.json()["detail"]["error"] == "NOT_READY"

    def test_duplicate_codes_are_deduped_before_the_count_check(self, tmp_path: Path) -> None:
        """A6-2:重複碼是**正常輸入**(同一檔可屬多群組,前端把群組成員直接拼進 csv),
        先驗數量再去重會把它判成 `BAD_CODES` —— 而整個群組頁只會顯示「載入失敗」,
        沒有任何線索指向「你有一檔重複」。去重要**保序**:卡片順序就是這個順序。
        """
        client, _ = make_client(tmp_path)
        with client:
            self._put(client, ["2330", "2317"])
            r = client.get("/api/stock/group-state", params={"codes": ",".join(["2330"] * 31)})
            assert r.status_code == 200
            assert list(r.json()["states"]) == ["2330"]
            r = client.get("/api/stock/group-state", params={"codes": "2317,2330,2317"})
            assert list(r.json()["states"]) == ["2317", "2330"]

    def test_dedup_does_not_defeat_the_limit(self, tmp_path: Path) -> None:
        """去重之後仍要驗上限:相異碼超量照樣 400(去重不是放行的後門)。"""
        client, _ = make_client(tmp_path)
        with client:
            codes = ",".join(f"{9000 + i}" for i in range(31))
            r = client.get("/api/stock/group-state", params={"codes": codes})
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "BAD_CODES"


class TestSignalHubGroupWiring:
    """接線防呆(group-grid R7):`groups_fn` / `quotes_fn` 預設 None = 靜默停用摘要。

    忘了在 `create_app` 接上去的失效樣態是「Discord 通知少了一段尾巴」—— 沒有例外、
    沒有 log、hub 單元測試全綠。只有從 booted app 這一端看才抓得到。
    """

    def test_boot_injects_groups_and_quotes(self, tmp_path: Path) -> None:
        save_watchlist(
            tmp_path / "watchlist.json",
            {"codes": ["2330", "2317"], "groups": [{"name": "半導體", "codes": ["2330", "2317"]}]},
        )
        client, _ = make_client(tmp_path)
        with client:
            hub = cast("SignalHub", client.app.state.signal_hub)  # type: ignore[attr-defined]
            assert hub is not None
            assert hub._groups == [{"name": "半導體", "codes": ["2330", "2317"]}]
            # quotes_fn 也接上了才產得出成員列(缺行情時是 `-`,但不會是空字串)
            assert hub._group_suffix({"code": "2330"}).startswith("｜同群 半導體:2317")

    def test_group_rename_without_code_change_reaches_the_hub(self, tmp_path: Path) -> None:
        """B3-a 端到端:只改群組名(codes 一模一樣)也要傳到 hub。

        這條路的 `set_watchlist` 收到的 added / removed 都是空的 —— 只要哪天有人為了
        省 UNSUB/SUB 而把 `on_watchlist` 收進「有增減才呼叫」的條件裡,摘要就會一直
        印**舊組名**,而畫面、log、hub 單元測試全部正常。
        """
        save_watchlist(
            tmp_path / "watchlist.json",
            {"codes": ["2330", "2317"], "groups": [{"name": "舊名", "codes": ["2330", "2317"]}]},
        )
        client, _ = make_client(tmp_path)
        with client:
            hub = cast("SignalHub", client.app.state.signal_hub)  # type: ignore[attr-defined]
            assert hub._groups == [{"name": "舊名", "codes": ["2330", "2317"]}]
            r = client.put(
                "/api/stock/watchlist",
                json={
                    "codes": ["2330", "2317"],
                    "groups": [{"name": "新名", "codes": ["2330", "2317"]}],
                },
            )
            assert r.status_code == 200
            assert hub._groups == [{"name": "新名", "codes": ["2330", "2317"]}]


class TestStockWs:
    def test_ws_streams_engine_messages(self, tmp_path: Path) -> None:
        client, fake = make_client(tmp_path)
        with client:
            client.get("/api/stock/state/2330")
            with client.websocket_connect("/ws/stock") as ws:
                assert fake.on_message is not None
                fake.on_message(
                    {
                        "Symbol": "TC.S.TWS.2330",
                        "Security": "2330",
                        "SecurityName": "台積電",
                        "TradingPrice": "2380",
                        "TradeQuantity": "1",
                        "TradeVolume": "1",
                        "TradeDate": "20260721",
                        "FilledTime": "25751",
                        "PreciseTime": "25751000000",
                        "Bid": "2375",
                        "Ask": "2380",
                        "BidVolume": "10",
                        "AskVolume": "10",
                        "ReferencePrice": "2320",
                        "UpperLimitPrice": "2550",
                        "LowerLimitPrice": "2090",
                        "YClosedPrice": "2320",
                        "YTradeVolume": "100",
                        "OpenTime": "90000",
                        "CloseTime": "133000",
                        "TradeStatus": "0",
                    }
                )
                got = [ws.receive_json(), ws.receive_json()]
                types = {m["type"] for m in got}
                assert {"tick", "book"} & types


class TestBarsRoute:
    """K 線 endpoint(SC-7;change-spec 🟢-6)。"""

    def _bar(self, t: str) -> dict:
        return {"t": t, "o": 100, "h": 110, "l": 90, "c": 105, "v": 7}

    def test_daily_shape_200(self, tmp_path: Path) -> None:
        client, fake = make_client(tmp_path)
        fake.bars_result = [self._bar("2026-07-27")]
        with client:
            r = client.get("/api/stock/bars/2330?tf=D")
            assert r.status_code == 200
            assert r.json() == {
                "code": "2330",
                "tf": "D",
                "bars": [{"t": "2026-07-27", "o": 100, "h": 110, "l": 90, "c": 105, "v": 7}],
                "status": "ok",
            }
            assert fake.bars_calls[0][1] == "D"

    def test_minute_shape_200(self, tmp_path: Path) -> None:
        client, fake = make_client(tmp_path)
        fake.bars_result = [self._bar("2026-07-28 09:01")]
        with client:
            r = client.get("/api/stock/bars/2330?tf=1&days=1")
            assert r.status_code == 200
            assert r.json()["tf"] == "1"
            assert fake.bars_calls[0][1] == "1"

    def test_default_tf_is_daily(self, tmp_path: Path) -> None:
        client, fake = make_client(tmp_path)
        with client:
            assert client.get("/api/stock/bars/2330").json()["tf"] == "D"

    def test_bad_code_400(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)
        with client:
            r = client.get("/api/stock/bars/bad code?tf=D")
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "BAD_CODE"

    def test_bad_tf_400(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)
        with client:
            r = client.get("/api/stock/bars/2330?tf=5m")
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "BAD_TF"

    def test_days_clamped_not_rejected(self, tmp_path: Path) -> None:
        client, fake = make_client(tmp_path)
        fake.bars_result = [self._bar("2026-07-28 09:01")]
        with client:
            assert client.get("/api/stock/bars/2330?tf=1&days=999").status_code == 200
            starts = [c[2] for c in fake.bars_calls]
            ends = [c[3] for c in fake.bars_calls]
            span = (
                _dt.date.fromisoformat(max(ends)) - _dt.date.fromisoformat(min(starts))
            ).days
            assert span <= 30

    def test_bad_days_400_not_422(self, tmp_path: Path) -> None:
        """days 轉換失敗要走專案錯誤契約,不是 FastAPI 預設 422 + list 形 detail(W-D3)。"""
        client, _ = make_client(tmp_path)
        with client:
            r = client.get("/api/stock/bars/2330?tf=1&days=abc")
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "BAD_DAYS"

    def test_daily_ignores_days_even_when_unparsable(self, tmp_path: Path) -> None:
        """tf=D 忽略 days(對齊 docstring / D-15):壞 days 不該擋下日 K(M1)。"""
        client, fake = make_client(tmp_path)
        fake.bars_result = [self._bar("2026-07-27")]
        with client:
            r = client.get("/api/stock/bars/2330?tf=D&days=abc")
            assert r.status_code == 200
            assert r.json()["tf"] == "D"
            assert r.json()["bars"]

    def test_tc4_down_returns_empty_200(self, tmp_path: Path) -> None:
        """engine 層降級空(不是 502),但 status 要說出是斷線 —— 前端才分得出
        「TC4 掛了」與「這檔真的沒資料」,兩者原本收斂成同一句「無 K 線資料」。"""
        client, fake = make_client(tmp_path)

        def boom(code: str, tf: str, start_date: str, end_date: str) -> tuple[list, str]:
            raise ConnectionError("tc4 down")

        fake.fetch_bars_range = boom  # type: ignore[method-assign]
        with client:
            r = client.get("/api/stock/bars/2330?tf=D")
            assert r.status_code == 200
            assert r.json()["bars"] == []
            assert r.json()["status"] == "disconnected"

    def test_timeout_status_reaches_response(self, tmp_path: Path) -> None:
        """N-5:source 層 deadline 用滿 → `{"status": "timeout", "bars": []}`(SC-1)。"""
        client, fake = make_client(tmp_path)
        fake.bars_result = []
        fake.bars_status = "timeout"
        with client:
            r = client.get("/api/stock/bars/2330?tf=D")
            assert r.status_code == 200
            assert r.json()["status"] == "timeout"
            assert r.json()["bars"] == []

    def test_minute_response_carries_status(self, tmp_path: Path) -> None:
        """分 K 路徑同樣要帶 status(兩段合併後的最壞值)。"""
        client, fake = make_client(tmp_path)
        fake.bars_result = []
        fake.bars_status = "timeout"
        with client:
            r = client.get("/api/stock/bars/2330?tf=1&days=1")
            assert r.json()["status"] == "timeout"
