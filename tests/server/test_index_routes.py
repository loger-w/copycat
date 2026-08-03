"""index routes 測試 — index-board SC-4 接線."""

from __future__ import annotations

from typing import Callable

from fastapi.testclient import TestClient

from copycat.server.app import create_app
from copycat.server.mis import OtcSnap
from tests.helpers.fake_txo import FakeTxoSource


class FakeIndexSource:
    def __init__(self) -> None:
        self.subscribed: list[str] = []
        self.closed = False
        self.on_message: Callable[[dict], None] | None = None

    def subscribe_symbol(self, code: str) -> None:
        self.subscribed.append(code)

    def unsubscribe_symbol(self, code: str) -> None:
        pass

    def fetch_day_minutes(self, code: str) -> dict[str, int]:
        return {"0901": 43_000_000}

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        self.on_message = cb

    def set_trade_date(self, trade_date: str) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def _mis() -> OtcSnap | None:
    return OtcSnap(p=359_800, ref=378_090, open=373_420, high=373_420, low=358_430, time="101610")


def make_client(index_source: FakeIndexSource | None) -> tuple[TestClient, FakeIndexSource | None]:
    app = create_app(
        FakeTxoSource(),
        index_source=index_source,
        index_mis_fetch=_mis,
        throttle_secs=0.01,
    )
    return TestClient(app, raise_server_exceptions=False), index_source


class TestIndexState:
    def test_state_shape_200(self) -> None:
        client, fake = make_client(FakeIndexSource())
        with client:
            r = client.get("/api/index/state")
            assert r.status_code == 200
            body = r.json()
            assert set(body) == {"trade_date", "twse", "otc", "txf"}
            assert body["twse"]["minutes"] == {"0901": 43_000_000}
            assert body["txf"] is None  # TXO runtime 無現貨 tick → None
        assert fake is not None and fake.closed is True  # lifespan finally close(IR6)

    def test_engine_absent_503(self) -> None:
        client, _ = make_client(None)
        with client:
            r = client.get("/api/index/state")
            assert r.status_code == 503
            assert r.json()["detail"]["error"] == "NOT_READY"

    def test_ws_streams_index_payload(self) -> None:
        client, fake = make_client(FakeIndexSource())
        with client:
            assert fake is not None and fake.on_message is not None
            with client.websocket_connect("/ws/index") as ws:
                fake.on_message(
                    {
                        "Security": "IX0001",
                        "TradingPrice": "42039.92",
                        "ReferencePrice": "43634.19",
                        "HighPrice": "43221.93",
                        "LowPrice": "41815.78",
                        "FilledTime": "13015",
                    }
                )
                msg = ws.receive_json()
                assert msg["type"] == "index"
                assert msg["twse"]["p"] == 42_039_920
