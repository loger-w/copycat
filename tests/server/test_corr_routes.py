"""相關係數 REST / WS 端點(SC-6)。"""

from __future__ import annotations

from typing import Callable

from fastapi.testclient import TestClient

from copycat.live.models import OptionContract, SeriesInfo, Tick
from copycat.server.app import create_app

_C = OptionContract(symbol="TC.O.TWF.TXO.202608.C.23000", cp="C", strike_millipts=23_000_000)
_SERIES = SeriesInfo(series_id="TXO.202608", name="TXO 202608", expiry="202608", contracts=(_C,))


class FakeTxoSource:
    """lifespan 需要的 TXO source;corr 路由測試不碰它。"""

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


class FakeCorrSource:
    def __init__(self) -> None:
        self.subscribed: list[str] = []
        self.cb: Callable[[dict], None] | None = None

    def subscribe_raw(self, symbol: str) -> None:
        self.subscribed.append(symbol)

    def unsubscribe_raw(self, symbol: str) -> None:
        if symbol in self.subscribed:
            self.subscribed.remove(symbol)

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        self.cb = cb

    def close(self) -> None:
        return None


def _client(corr_source: object | None) -> TestClient:
    app = create_app(FakeTxoSource(), corr_source=corr_source, throttle_secs=0.01)
    return TestClient(app, raise_server_exceptions=False)


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
            assert set(body["legs"]) == {"TXF", "TWN", "YM", "ES", "NQ", "SXF"}
            # 配對 = 各腿 vs 台指(base 不與自己配對)
            assert set(body["pairs"]) == {"TWN", "YM", "ES", "NQ", "SXF"}

    def test_leg_labels_are_traditional_chinese(self) -> None:
        """前端不寫死對照表 → label 必須由後端帶(SC-7)。"""
        with _client(FakeCorrSource()) as client:
            legs = client.get("/api/corr/state").json()["legs"]
            assert legs["SXF"]["label"] == "費半"
            assert legs["TWN"]["label"] == "富台"

    def test_engine_subscribes_five_tc4_legs_not_the_base(self) -> None:
        """SC-5:台指腿走 futures_engine,不得由本引擎重複訂閱。"""
        src = FakeCorrSource()
        with _client(src) as client:
            client.get("/api/corr/state")
            assert "TC.F.TWF.TXF.HOT" not in src.subscribed
            assert len(src.subscribed) == 5


class TestCorrWebSocket:
    def test_first_frame_is_current_state(self) -> None:
        with _client(FakeCorrSource()) as client:
            with client.websocket_connect("/ws/corr") as ws:
                first = ws.receive_json()

                assert first["type"] == "corr"
                assert first["base"] == "TXF"
                assert "pairs" in first

    def test_closes_when_engine_disabled(self) -> None:
        with _client(None) as client:
            with client.websocket_connect("/ws/corr") as ws:
                # 引擎停用 → server 直接關閉,不得空等
                try:
                    ws.receive_json()
                    raise AssertionError("引擎停用時不應收到訊息")
                except Exception as exc:  # WebSocketDisconnect
                    assert "AssertionError" not in type(exc).__name__
