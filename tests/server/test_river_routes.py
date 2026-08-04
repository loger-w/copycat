"""江波圖 REST / WS 端點(SC-5)。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from copycat.server.app import create_app
from tests.helpers.fake_sources import FakeCorrSource
from tests.helpers.fake_txo import FakeTxoSource


def _client(corr_source: object | None) -> TestClient:
    app = create_app(FakeTxoSource(), corr_source=corr_source, throttle_secs=0.01)
    return TestClient(app, raise_server_exceptions=False)


class TestRiverStateRoute:
    def test_returns_503_with_error_code_when_engine_disabled(self) -> None:
        with _client(None) as client:
            r = client.get("/api/river/state")
            assert r.status_code == 503
            assert r.json()["detail"]["error"] == "RIVER_NOT_READY"

    def test_returns_window_and_six_legs(self) -> None:
        with _client(FakeCorrSource()) as client:
            r = client.get("/api/river/state")

            assert r.status_code == 200
            body = r.json()
            assert body["type"] == "river"
            assert body["base"] == "TXF"
            assert set(body["legs"]) == {"TXF", "TWN", "YM", "ES", "NQ", "SXF"}
            assert set(body["window"]) == {"start_min", "end_min"}
            assert body["session"] in ("day", "night")

    def test_leg_labels_come_from_backend(self) -> None:
        with _client(FakeCorrSource()) as client:
            legs = client.get("/api/river/state").json()["legs"]
            assert legs["SXF"]["label"] == "費半"
            assert legs["TWN"]["label"] == "富台"

    def test_minutes_keys_are_json_strings(self) -> None:
        """JSON 物件鍵恆為字串 → 前端幾何層必須 Number(k)(design review P2-2)。"""
        with _client(FakeCorrSource()) as client:
            legs = client.get("/api/river/state").json()["legs"]
            assert all(isinstance(k, str) for k in legs["ES"]["minutes"])

    def test_backfill_never_requests_the_base_leg_symbol(self) -> None:
        """SC-4:台指的 1K 不可從 corr session 問。"""
        src = FakeCorrSource()
        with _client(src) as client:
            client.get("/api/river/state")
            assert "TC.F.TWF.TXF.HOT" not in src.fetched


class TestRiverWebSocket:
    def test_first_frame_is_full_snapshot(self) -> None:
        with _client(FakeCorrSource()) as client:
            with client.websocket_connect("/ws/river") as ws:
                first = ws.receive_json()

                assert first["type"] == "river"
                assert "legs" in first
                assert "window" in first

    def test_closes_when_engine_disabled(self) -> None:
        with _client(None) as client:
            with client.websocket_connect("/ws/river") as ws:
                try:
                    ws.receive_json()
                    raise AssertionError("引擎停用時不應收到訊息")
                except Exception as exc:  # WebSocketDisconnect
                    assert "AssertionError" not in type(exc).__name__


class TestExistingCorrRouteUnaffected:
    def test_corr_state_still_returns_pairs(self) -> None:
        """SC-10:既有相關係數端點零退化。"""
        with _client(FakeCorrSource()) as client:
            body = client.get("/api/corr/state").json()
            assert body["type"] == "corr"
            assert set(body["pairs"]) == {"TWN", "YM", "ES", "NQ", "SXF"}
