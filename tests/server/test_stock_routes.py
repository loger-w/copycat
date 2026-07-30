from __future__ import annotations

import datetime as _dt
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
        self.daily_bars_result: list[dict] | Exception = []
        self.bars_calls: list[tuple[str, str, str, str]] = []
        self.bars_result: list[dict] = []

    def fetch_bars_range(
        self, code: str, tf: str, start_date: str, end_date: str
    ) -> list:
        """Protocol 新增方法(change-spec R2-1)。"""
        self.bars_calls.append((code, tf, start_date, end_date))
        return self.bars_result

    def fetch_daily_bars(self, code: str, n: int = 25) -> list:
        if isinstance(self.daily_bars_result, Exception):
            raise self.daily_bars_result
        return self.daily_bars_result

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

    def test_tc4_down_returns_empty_200(self, tmp_path: Path) -> None:
        """engine 層降級空(不是 502)—— 前端顯示「無 K 線資料」而非炸掉。"""
        client, fake = make_client(tmp_path)

        def boom(code: str, tf: str, start_date: str, end_date: str) -> list:
            raise ConnectionError("tc4 down")

        fake.fetch_bars_range = boom  # type: ignore[method-assign]
        with client:
            r = client.get("/api/stock/bars/2330?tf=D")
            assert r.status_code == 200
            assert r.json()["bars"] == []
