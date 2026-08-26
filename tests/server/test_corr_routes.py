"""相關係數 REST / WS 端點(SC-6)。"""

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
            assert set(body["legs"]) == _LEG_KEYS
            # 配對 = 各腿 vs 台指(base 不與自己配對)
            assert set(body["pairs"]) == _PAIR_KEYS

    def test_leg_labels_are_traditional_chinese(self) -> None:
        """前端不寫死對照表 → label 必須由後端帶(SC-7)。"""
        with _client(FakeCorrSource()) as client:
            legs = client.get("/api/corr/state").json()["legs"]
            assert legs["SXF"]["label"] == "費半"
            assert legs["TWN"]["label"] == "富台"

    def test_engine_subscribes_every_tc4_leg_but_not_the_base(self) -> None:
        """SC-5:台指腿走 futures_engine,不得由本引擎重複訂閱(本引擎只訂 source=tc4 的腿)。"""
        src = FakeCorrSource()
        with _client(src) as client:
            client.get("/api/corr/state")
            assert "TC.F.TWF.TXF.HOT" not in src.subscribed
            assert "TC.F.OSE.NK225M.HOT" in src.subscribed
            # F4 四腿(台積電是**現貨** TC.S.TWS. 段,不是個股期)
            assert "TC.F.CFE.VX.HOT" in src.subscribed
            assert "TC.F.CME.CL.HOT" in src.subscribed
            assert "TC.F.CME.GC.HOT" in src.subscribed
            assert "TC.S.TWS.2330" in src.subscribed
            assert len(src.subscribed) == len(_CFG.tc4_legs())


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
