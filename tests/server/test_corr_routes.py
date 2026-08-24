"""相關係數 REST / WS 端點(SC-6)。"""

from __future__ import annotations

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from copycat.server.app import create_app
from tests.helpers.boot import BootedClient
from tests.helpers.fake_sources import FakeCorrSource
from tests.helpers.fake_txo import FakeTxoSource


def _client(corr_source: object | None) -> TestClient:
    app = create_app(FakeTxoSource(), corr_source=corr_source, throttle_secs=0.01)
    return BootedClient(app, raise_server_exceptions=False)


class TestCorrStateRoute:
    def test_returns_503_with_error_code_when_engine_disabled(self) -> None:
        with _client(None) as client:
            r = client.get("/api/corr/state")
            assert r.status_code == 503
            assert r.json()["detail"]["error"] == "CORR_NOT_READY"

    def test_returns_payload_when_engine_running(self) -> None:
        with _client(FakeCorrSource()) as client:
            r = client.get("/api/corr/state")

            assert r.status_code == 200
            body = r.json()
            assert body["base"] == "TXF"
            assert body["type"] == "corr"
            # 腿集合 = repo configs/correlation.json(2026-08-17 起七腿含小日經 NK225M)
            assert set(body["legs"]) == {"TXF", "TWN", "YM", "ES", "NQ", "SXF", "NK225M"}
            # 配對 = 各腿 vs 台指(base 不與自己配對)
            assert set(body["pairs"]) == {"TWN", "YM", "ES", "NQ", "SXF", "NK225M"}

    def test_leg_labels_are_traditional_chinese(self) -> None:
        """前端不寫死對照表 → label 必須由後端帶(SC-7)。"""
        with _client(FakeCorrSource()) as client:
            legs = client.get("/api/corr/state").json()["legs"]
            assert legs["SXF"]["label"] == "費半"
            assert legs["TWN"]["label"] == "富台"

    def test_engine_subscribes_six_tc4_legs_not_the_base(self) -> None:
        """SC-5:台指腿走 futures_engine,不得由本引擎重複訂閱(七腿 → 本引擎訂六)。"""
        src = FakeCorrSource()
        with _client(src) as client:
            client.get("/api/corr/state")
            assert "TC.F.TWF.TXF.HOT" not in src.subscribed
            assert "TC.F.OSE.NK225M.HOT" in src.subscribed
            assert len(src.subscribed) == 6


class TestCorrWebSocket:
    def test_first_frame_is_current_state(self) -> None:
        with _client(FakeCorrSource()) as client:
            with client.websocket_connect("/ws/corr") as ws:
                first = ws.receive_json()

                assert first["type"] == "corr"
                assert first["base"] == "TXF"
                assert "pairs" in first

    def test_rejects_handshake_when_engine_disabled(self) -> None:
        # R4 N036(由「accept 後即關」翻轉):引擎停用 → 握手前就 close,進場即拋,不得空等
        with _client(None) as client:
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/ws/corr"):
                    raise AssertionError("引擎停用時握手不該成功")
