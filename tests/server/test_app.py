from __future__ import annotations

from typing import Callable

from fastapi.testclient import TestClient

from copycat.live.models import OptionContract, SeriesInfo, Tick
from copycat.server.app import create_app

from tests.helpers.boot import BootedClient

C44000 = OptionContract(symbol="TC.O.TWF.TX4.202607.C.44000", cp="C", strike_millipts=44_000_000)
SERIES_A = SeriesInfo(
    series_id="TX4.202607", name="TX4 202607", expiry="202607", contracts=(C44000,)
)


def tick(*, price: int, qty: int, cum: int | None = None, t: int = 1) -> Tick:
    return Tick(
        symbol=C44000.symbol,
        precise_time=t,
        price_millipts=price,
        qty=qty,
        bid_millipts=price - 1_000,
        ask_millipts=price,
        cum_volume=cum,
    )


class FakeQuoteSource:
    def __init__(self, series: list[SeriesInfo] | None = None) -> None:
        self.series = [SERIES_A] if series is None else series
        self.on_tick: Callable[[Tick], None] | None = None
        self.fail_backfill_for: set[str] = set()

    def list_series(self) -> list[SeriesInfo]:
        return self.series

    def fetch_backfill(self, series: SeriesInfo) -> list[Tick]:
        if series.series_id in self.fail_backfill_for:
            raise ConnectionError("tc4 gone")
        return []

    def subscribe(self, series: SeriesInfo, on_tick: Callable[[Tick], None]) -> None:
        self.on_tick = on_tick

    def unsubscribe(self, series: SeriesInfo) -> None:
        pass

    def close(self) -> None:
        pass


def make_client(fake: FakeQuoteSource | None = None) -> tuple[TestClient, FakeQuoteSource]:
    fake = fake or FakeQuoteSource()
    app = create_app(fake, throttle_secs=0.01)
    # raise_server_exceptions=False:讓全域 exception handler 的 502 回應可被斷言
    return BootedClient(app, raise_server_exceptions=False), fake


class TestSeriesRoute:
    def test_lists_series(self) -> None:
        client, _ = make_client()
        with client:
            res = client.get("/api/txo/series")
            assert res.status_code == 200
            body = res.json()
            assert body["series"][0]["series_id"] == "TX4.202607"
            assert body["series"][0]["name"] == "TX4 202607"

    def test_no_series_is_503(self) -> None:
        client, _ = make_client(FakeQuoteSource(series=[]))
        with client:
            res = client.get("/api/txo/series")
            assert res.status_code == 503
            assert res.json()["detail"]["error"] == "NOT_READY"


class TestSelectRoute:
    def test_unknown_series_400(self) -> None:
        client, _ = make_client()
        with client:
            res = client.post("/api/txo/select", json={"series_id": "NOPE"})
            assert res.status_code == 400
            assert res.json()["detail"]["error"] == "UNKNOWN_SERIES"

    def test_select_switches_active(self) -> None:
        client, _ = make_client()
        with client:
            res = client.post("/api/txo/select", json={"series_id": "TX4.202607"})
            assert res.status_code == 200
            assert res.json()["series_id"] == "TX4.202607"

    def test_upstream_failure_maps_502(self) -> None:
        fake = FakeQuoteSource()
        client, _ = make_client(fake)
        with client:
            fake.fail_backfill_for.add("TX4.202607")
            res = client.post("/api/txo/select", json={"series_id": "TX4.202607"})
            assert res.status_code == 502
            assert res.json()["detail"]["error"] == "TC4_DOWN"


class TestSnapshotRoute:
    def test_snapshot_shape(self) -> None:
        client, _ = make_client()
        with client:
            res = client.get("/api/txo/snapshot")
            assert res.status_code == 200
            body = res.json()
            assert body["series_id"] == "TX4.202607"
            assert body["status"] == "live"
            assert body["curve"] == []


class TestWebSocket:
    def test_first_message_then_push(self) -> None:
        client, fake = make_client()
        with client:
            with client.websocket_connect("/ws/txo-pnl") as ws:
                first = ws.receive_json()
                assert first["series_id"] == "TX4.202607"
                assert fake.on_tick is not None
                fake.on_tick(tick(price=100_000, qty=2, cum=2, t=5))
                nxt = ws.receive_json()
                assert nxt["totals"]["call_net_qty"] == 2


class TestTxoContractsRoute:
    """SC-11(Task 16b):OrderPanel 全鏈選單來源 — active 序列全集,非 snapshot 成交子集。"""

    def test_contracts_empty_when_no_series(self) -> None:
        # runtime 啟動即自動 activate 首序列 → 空態要用零序列 fake 逼出
        client, _ = make_client(FakeQuoteSource(series=[]))
        with client:
            res = client.get("/api/txo/contracts")
            assert res.status_code == 200
            assert res.json() == {"contracts": []}

    def test_contracts_after_select_full_chain_no_spot(self) -> None:
        client, _ = make_client()
        with client:
            client.post("/api/txo/select", json={"series_id": "TX4.202607"})
            res = client.get("/api/txo/contracts")
            assert res.status_code == 200
            contracts = res.json()["contracts"]
            assert C44000.symbol in contracts
            assert all(s.startswith("TC.O.") for s in contracts)
