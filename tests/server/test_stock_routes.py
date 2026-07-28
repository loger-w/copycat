from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi.testclient import TestClient

from copycat.live.models import OptionContract, SeriesInfo, Tick
from copycat.server.app import create_app

_C = OptionContract(symbol="TC.O.TWF.TXO.202608.C.23000", cp="C", strike_millipts=23_000_000)
_SERIES = SeriesInfo(series_id="TXO.202608", name="TXO 202608", expiry="202608", contracts=(_C,))


class FakeTxoSource:
    """TXO QuoteSource fake(stock 路由測試不碰 TXO,但 lifespan 需要它)。"""

    def list_series(self) -> list[SeriesInfo]:
        return [_SERIES]

    def fetch_backfill(self, series: SeriesInfo) -> list[Tick]:
        return []

    def subscribe(self, series: SeriesInfo, on_tick) -> None:
        return None

    def unsubscribe(self, series: SeriesInfo) -> None:
        return None

    def close(self) -> None:
        return None


class FakeStockSource:
    """StockSource fake:全部 no-op,記錄呼叫(routes 測試不需要真行情)。"""

    def __init__(self) -> None:
        self.subscribed: list[str] = []
        self.on_message: Callable[[dict], None] | None = None

    def subscribe_symbol(self, code: str) -> None:
        self.subscribed.append(code)

    def unsubscribe_symbol(self, code: str) -> None:
        pass

    def backfill(self, code: str) -> list:
        return []

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        self.on_message = cb

    def set_on_no_data(self, cb: Callable[[str], None]) -> None:
        pass

    def set_trade_date(self, trade_date: str) -> None:
        pass

    def close(self) -> None:
        pass


def make_client(tmp_path: Path) -> tuple[TestClient, FakeStockSource]:
    fake = FakeStockSource()
    app = create_app(
        FakeTxoSource(),
        stock_source=fake,
        stock_watchlist_path=tmp_path / "watchlist.json",
        throttle_secs=0.01,
    )
    return TestClient(app, raise_server_exceptions=False), fake


class TestWatchlistRoutes:
    """groups shape(stock-ui-upgrade SC-6);舊 codes shape 斷言隨 API 契約同輪遷移."""

    def test_get_empty_then_put_round_trip(self, tmp_path: Path) -> None:
        client, fake = make_client(tmp_path)
        with client:
            assert client.get("/api/stock/watchlist").json() == {"groups": []}
            groups = [
                {"name": "主力", "codes": ["2330", "5483"]},
                {"name": "觀察", "codes": ["3231"]},
            ]
            r = client.put("/api/stock/watchlist", json={"groups": groups})
            assert r.status_code == 200
            assert r.json() == {"groups": groups}
            assert client.get("/api/stock/watchlist").json() == {"groups": groups}
            assert "2330" in fake.subscribed and "3231" in fake.subscribed  # 聯集已訂

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
                "groups": [{"name": "自選", "codes": ["2330"]}]
            }
            assert "2330" in fake2.subscribed  # 啟動即訂回持久化清單

    def test_v1_file_restores_union_on_startup(self, tmp_path: Path) -> None:
        """R2:v1 檔(codes shape)重啟 → set_watchlist 收到遷移後聯集."""
        import json as _json

        (tmp_path / "watchlist.json").write_text(
            _json.dumps({"_cache_version": 1, "codes": ["2330", "5483"]}), encoding="utf-8"
        )
        client, fake = make_client(tmp_path)
        with client:
            assert client.get("/api/stock/watchlist").json() == {
                "groups": [{"name": "自選", "codes": ["2330", "5483"]}]
            }
            assert "2330" in fake.subscribed and "5483" in fake.subscribed


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
