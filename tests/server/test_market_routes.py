"""大盤 K 線 route(index-board N-5 / SC-4/5/6)。

三個分派各自向**持有該 symbol REALTIME 訂閱的那條 session** 問歷史
(CLAUDE.md §8 同 symbol 跨 session 只推一邊):
`TWSE` → index 引擎、`TXF/MXF/TMF` → futures 引擎、`OTC` → 本機合成(TC4 無此 symbol)。
"""

from __future__ import annotations

import datetime as _dt
from typing import Callable

from fastapi.testclient import TestClient

from copycat.live.models import OptionContract, SeriesInfo, Tick
from copycat.server.app import create_app
from copycat.server.mis import OtcSnap

_C = OptionContract(symbol="TC.O.TWF.TXO.202608.C.23000", cp="C", strike_millipts=23_000_000)
_SERIES = SeriesInfo(series_id="TXO.202608", name="TXO 202608", expiry="202608", contracts=(_C,))
_TODAY = f"{_dt.date.today():%Y-%m-%d}"


class FakeTxoSource:
    def list_series(self) -> list[SeriesInfo]:
        return [_SERIES]

    def fetch_backfill(self, series: SeriesInfo) -> list[Tick]:
        return []

    def subscribe(self, series: SeriesInfo, on_tick: Callable[[Tick], None]) -> None:
        return None

    def unsubscribe(self, series: SeriesInfo) -> None:
        return None

    def close(self) -> None:
        return None


def _dbar(t: str, c: int) -> dict:
    return {"t": t, "o": c, "h": c + 1000, "l": c - 1000, "c": c, "v": 10}


class FakeIndexSource:
    def __init__(self, *, tag: str = "tc4_dk") -> None:
        self.calls: list[tuple[str, str, str, str]] = []
        self._tag = tag

    def subscribe_symbol(self, code: str) -> None:
        pass

    def unsubscribe_symbol(self, code: str) -> None:
        pass

    def fetch_day_minutes(self, code: str) -> dict[str, int]:
        return {}

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        pass

    def set_trade_date(self, trade_date: str) -> None:
        pass

    def close(self) -> None:
        pass

    def fetch_bars_range_tagged(
        self, code: str, tf: str, start: str, end: str
    ) -> tuple[list[dict], str]:
        self.calls.append((code, tf, start, end))
        if tf == "1":
            return [{"t": f"{_TODAY} 09:01", "o": 1, "h": 2, "l": 0, "c": 1, "v": 3}], "tc4_1k"
        return [
            _dbar("2026-07-27", 23_000_000),
            _dbar("2026-07-28", 23_100_000),
            _dbar("2026-07-29", 23_200_000),
        ], self._tag


class NoHistoryIndexSource(FakeIndexSource):
    """沒有 `fetch_bars_range_tagged` 的來源(舊 source / TC4 不可用的替身)。"""

    fetch_bars_range_tagged = None  # type: ignore[assignment]


class FakeFuturesSource:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, str]] = []

    def subscribe_symbol(self, product: str) -> None:
        pass

    def subscribe_leaf(self, product: str, ym: str) -> None:
        pass

    def unsubscribe_symbol(self, product: str) -> None:
        pass

    def fetch_day_1k(self, product: str) -> list[tuple[int, int]]:
        return []

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        pass

    def close(self) -> None:
        pass

    def fetch_bars_range(self, product: str, tf: str, start: str, end: str) -> list[dict]:
        self.calls.append((product, tf, start, end))
        return [_dbar("2026-07-29", 23_200_000)]


def _mis() -> OtcSnap | None:
    return None


def make_client(
    *,
    index_source: FakeIndexSource | None = None,
    futures_source: FakeFuturesSource | None = None,
    mis: Callable[[], OtcSnap | None] = _mis,
) -> TestClient:
    app = create_app(
        FakeTxoSource(),
        index_source=index_source,
        index_mis_fetch=mis,
        futures_source=futures_source,
        throttle_secs=0.01,
    )
    return TestClient(app, raise_server_exceptions=False)


class TestValidation:
    def test_bad_key_400(self) -> None:
        with make_client(index_source=FakeIndexSource()) as c:
            r = c.get("/api/market/bars/2330")
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "BAD_KEY"

    def test_bad_tf_400(self) -> None:
        with make_client(index_source=FakeIndexSource()) as c:
            r = c.get("/api/market/bars/TWSE?tf=5")
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "BAD_TF"

    def test_bad_days_400(self) -> None:
        with make_client(index_source=FakeIndexSource()) as c:
            r = c.get("/api/market/bars/TWSE?tf=1&days=abc")
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "BAD_DAYS"

    def test_engine_absent_503(self) -> None:
        with make_client(index_source=None) as c:
            r = c.get("/api/market/bars/TWSE")
        assert r.status_code == 503
        assert r.json()["detail"]["error"] == "NOT_READY"


class TestTwse:
    def test_daily_goes_through_index_engine_with_ix0001(self) -> None:
        """P0-1:加權歷史必須走 index 自己的 session,不是個股 session。"""
        src = FakeIndexSource()
        with make_client(index_source=src) as c:
            r = c.get("/api/market/bars/TWSE?tf=D")
        assert r.status_code == 200
        body = r.json()
        assert len(body["bars"]) == 3
        assert body["meta"]["source"] == "tc4_dk"
        assert body["meta"]["coverage_from"] == "2026-07-27"
        assert body["meta"]["coverage_to"] == "2026-07-29"
        assert [c_[0] for c_ in src.calls] == ["IX0001"]

    def test_weekly_aggregates_from_same_long_daily_fetch(self) -> None:
        """日/週/月共用同一份長窗日 K —— 第二次請求不得再打一次 TC4。"""
        src = FakeIndexSource()
        with make_client(index_source=src) as c:
            c.get("/api/market/bars/TWSE?tf=D")
            r = c.get("/api/market/bars/TWSE?tf=W")
        assert len(src.calls) == 1  # cache hit
        body = r.json()
        assert len(body["bars"]) == 1  # 三根同屬 ISO 2026-W31
        assert body["bars"][0]["t"] == "2026-07-29"
        assert body["meta"]["partial_last"] is True

    def test_source_tag_reflects_actual_branch_not_expectation(self) -> None:
        """P1-4:DK 空時 fallback 成 1K 聚合,meta 必須說實話。"""
        src = FakeIndexSource(tag="tc4_dk_1k_agg")
        with make_client(index_source=src) as c:
            r = c.get("/api/market/bars/TWSE?tf=M")
        assert r.json()["meta"]["source"] == "tc4_dk_1k_agg"

    def test_history_unavailable_is_200_with_unavailable_source(self) -> None:
        """引擎在但代理不到(TC4 掛了)→ 200 + source=unavailable,不是 4xx。"""
        src = NoHistoryIndexSource()
        with make_client(index_source=src) as c:
            r = c.get("/api/market/bars/TWSE?tf=D")
        assert r.status_code == 200
        assert r.json()["bars"] == []
        assert r.json()["meta"]["source"] == "unavailable"


class TestOtc:
    def test_daily_refuses_with_reason_not_4xx(self) -> None:
        """SC-6:櫃買無歷史來源 → 200 + refusal。4xx 會被前端 error 路徑吞成
        同一種紅色,分不出「平台不支援」與「TC4 掛了」。"""
        with make_client(index_source=FakeIndexSource()) as c:
            for tf in ("D", "W", "M"):
                r = c.get(f"/api/market/bars/OTC?tf={tf}")
                assert r.status_code == 200, tf
                assert r.json()["bars"] == []
                assert r.json()["meta"]["refusal"] == "NO_HISTORICAL_SOURCE"

    def test_minute_is_local_synth_without_volume(self) -> None:
        snaps = [
            OtcSnap(p=359_800, ref=378_090, open=0, high=0, low=0, time="101610"),
        ]
        with make_client(index_source=FakeIndexSource(), mis=lambda: snaps[0]) as c:
            r = c.get("/api/market/bars/OTC?tf=1")
        body = r.json()
        assert body["meta"]["source"] == "mis_poll_synth"
        assert body["meta"]["volume"] is False
        assert body["meta"]["refusal"] is None
        if body["bars"]:  # MIS poll 是背景 task,首拍未必趕上
            assert body["bars"][0]["t"].startswith(f"{_TODAY} ")
            assert body["meta"]["synth_since"] is not None


class TestFutures:
    def test_product_routes_to_futures_engine(self) -> None:
        fut = FakeFuturesSource()
        with make_client(index_source=FakeIndexSource(), futures_source=fut) as c:
            r = c.get("/api/market/bars/MXF?tf=D")
        assert r.status_code == 200
        assert r.json()["meta"]["source"] == "tc4_dk"
        assert [call[0] for call in fut.calls] == ["MXF"]

    def test_futures_absent_503(self) -> None:
        with make_client(index_source=FakeIndexSource(), futures_source=None) as c:
            r = c.get("/api/market/bars/TXF?tf=D")
        assert r.status_code == 503

    def test_cache_key_does_not_collide_with_twse(self) -> None:
        """`F:TXF` 與 `IX0001` 各佔一格,不得互相取到對方的 bars。"""
        src, fut = FakeIndexSource(), FakeFuturesSource()
        with make_client(index_source=src, futures_source=fut) as c:
            twse = c.get("/api/market/bars/TWSE?tf=D").json()
            txf = c.get("/api/market/bars/TXF?tf=D").json()
        assert len(twse["bars"]) == 3
        assert len(txf["bars"]) == 1
