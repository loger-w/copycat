from __future__ import annotations

import datetime as _dt
from pathlib import Path

from fastapi.testclient import TestClient

from copycat.server.app import create_app
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
    return TestClient(app, raise_server_exceptions=False), fake


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
        client = TestClient(app, raise_server_exceptions=False)
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
        client = TestClient(app, raise_server_exceptions=False)
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
        with TestClient(app, raise_server_exceptions=False) as client:
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
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get("/api/stock/state/@@@")
        assert r.status_code == 503
        assert r.json()["detail"]["error"] == "NOT_READY"


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
