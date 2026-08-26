"""江波圖 REST / WS 端點(SC-5)。"""

from __future__ import annotations

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from copycat.corr_config import CONFIG_PATH, load_config
from copycat.server.app import create_app
from tests.helpers.boot import BootedClient
from tests.helpers.fake_sources import FakeCorrSource
from tests.helpers.fake_txo import FakeTxoSource


# 腿集合來自 repo configs/correlation.json(F-20:逐字契約只鎖在 tests/test_corr_config.py::
# _EXPECTED_LEGS;這裡鎖的是 route 有把設定檔那組原封不動吐出來、配對 = 各腿 vs base)
_CFG = load_config(CONFIG_PATH)
_LEG_KEYS = {leg.key for leg in _CFG.legs}
_PAIR_KEYS = _LEG_KEYS - {_CFG.base}


def _client(corr_source: object | None) -> TestClient:
    app = create_app(FakeTxoSource(), corr_source=corr_source, throttle_secs=0.01)
    return BootedClient(app, raise_server_exceptions=False)


class TestRiverStateRoute:
    def test_returns_503_with_error_code_when_engine_disabled(self) -> None:
        with _client(None) as client:
            r = client.get("/api/river/state")
            assert r.status_code == 503
            assert r.json()["detail"]["error"] == "RIVER_NOT_READY"

    def test_returns_window_and_every_leg(self) -> None:
        """腿集合 = repo `configs/correlation.json`(2026-08-26 F4 起十一腿)。"""
        with _client(FakeCorrSource()) as client:
            r = client.get("/api/river/state")

            assert r.status_code == 200
            body = r.json()
            assert body["type"] == "river"
            assert body["base"] == "TXF"
            assert set(body["legs"]) == _LEG_KEYS
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

    def test_rejects_handshake_when_engine_disabled(self) -> None:
        # R4 N036(由「accept 後即關」翻轉):引擎停用 → 握手前就 close,進場即拋,不得空等
        with _client(None) as client:
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/ws/river"):
                    raise AssertionError("引擎停用時握手不該成功")


class TestExistingCorrRouteUnaffected:
    def test_corr_state_still_returns_pairs(self) -> None:
        """SC-10:既有相關係數端點零退化。"""
        with _client(FakeCorrSource()) as client:
            body = client.get("/api/corr/state").json()
            assert body["type"] == "corr"
            assert set(body["pairs"]) == _PAIR_KEYS
