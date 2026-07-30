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
        """**不依賴 MIS 背景 task 的時序**:直接餵引擎再打 route。

        原本寫成 `if body["bars"]:` 的條件式斷言 —— `_mis_loop` 是 `asyncio.create_task`
        起的背景任務,首拍未必趕在請求前完成,bars 空時整段斷言被跳過而測試照樣綠。
        那是本專案已經吃過虧的假綠樣態,條件式斷言不留在 repo(review P1-4)。"""
        with make_client(index_source=FakeIndexSource()) as c:
            engine = c.app.state.index  # type: ignore[attr-defined]
            engine._apply_otc(
                OtcSnap(p=359_800, ref=378_090, open=0, high=0, low=0, time="101610")
            )
            engine._apply_otc(
                OtcSnap(p=360_100, ref=378_090, open=0, high=0, low=0, time="101655")
            )
            r = c.get("/api/market/bars/OTC?tf=1")
        body = r.json()
        assert body["meta"]["source"] == "mis_poll_synth"
        assert body["meta"]["volume"] is False
        assert body["meta"]["refusal"] is None
        assert body["meta"]["synth_since"] == "10:17"
        assert len(body["bars"]) == 1
        bar = body["bars"][0]
        assert bar["t"] == f"{_TODAY} 10:17"  # 前端靠空格分辨日 K / 分 K
        assert (bar["o"], bar["h"], bar["l"], bar["c"], bar["v"]) == (
            359_800, 360_100, 359_800, 360_100, 0,
        )


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


class TestVolumeMeta:
    """`volume` 由資料判定(2026-07-30 real-env 抓到:加權 DK 的 v 全為 0)。

    指數沒有量欄位 → `_int_field` 缺值回 0 → 整條序列 v=0。標 volume=true 會讓前端
    畫一排貼底的 0 高柱,與「真的零成交」在畫面上無法區分,正是 SC-6 要避免的假造零。
    """

    def test_all_zero_volume_series_reports_volume_false(self) -> None:
        class ZeroVol(FakeIndexSource):
            def fetch_bars_range_tagged(
                self, code: str, tf: str, start: str, end: str
            ) -> tuple[list[dict], str]:
                return [{"t": "2026-07-29", "o": 1, "h": 2, "l": 0, "c": 1, "v": 0}], "tc4_dk"

        with make_client(index_source=ZeroVol()) as c:
            r = c.get("/api/market/bars/TWSE?tf=D")
        assert r.json()["meta"]["volume"] is False

    def test_series_with_volume_reports_true(self) -> None:
        fut = FakeFuturesSource()
        with make_client(index_source=FakeIndexSource(), futures_source=fut) as c:
            r = c.get("/api/market/bars/TXF?tf=D")
        assert r.json()["meta"]["volume"] is True


class TestMinutePath:
    """tf=1 是 UI 最常走的一條(17 顆週期鈕裡有 13 顆走它),原本零測試(review P1-3)。"""

    def test_twse_minute_hits_index_engine_with_tf1(self) -> None:
        src = FakeIndexSource()
        with make_client(index_source=src) as c:
            r = c.get("/api/market/bars/TWSE?tf=1&days=5")
        body = r.json()
        assert body["meta"]["source"] == "tc4_1k"
        assert body["bars"][0]["t"] == f"{_TODAY} 09:01"
        # build_minute 是兩段式:歷史段(start..昨日)+ 當日段 各發一次(W-7 語意)
        assert {(call[0], call[1]) for call in src.calls} == {("IX0001", "1")}

    def test_futures_minute_hits_futures_engine_with_tf1(self) -> None:
        fut = FakeFuturesSource()
        with make_client(index_source=FakeIndexSource(), futures_source=fut) as c:
            r = c.get("/api/market/bars/TMF?tf=1")
        assert r.json()["meta"]["source"] == "tc4_1k"
        assert {(call[0], call[1]) for call in fut.calls} == {("TMF", "1")}

    def test_days_is_clamped_to_30(self) -> None:
        src = FakeIndexSource()
        with make_client(index_source=src) as c:
            c.get("/api/market/bars/TWSE?tf=1&days=999")
        # 取最早的 start(歷史段)到今天 = 實際請求窗
        earliest = min(call[2] for call in src.calls)
        span = (_dt.date.today() - _dt.date.fromisoformat(earliest)).days + 1
        assert span == 30

    def test_empty_minute_result_reports_unavailable(self) -> None:
        class Empty(FakeIndexSource):
            def fetch_bars_range_tagged(
                self, code: str, tf: str, start: str, end: str
            ) -> tuple[list[dict], str]:
                return [], "tc4_1k"

        with make_client(index_source=Empty()) as c:
            r = c.get("/api/market/bars/TWSE?tf=1")
        assert r.status_code == 200
        assert r.json()["meta"]["source"] == "unavailable"

    def test_minute_cache_key_isolated_from_stock_session(self) -> None:
        """裸 "IX0001" 會與 /api/stock/bars/IX0001(走 **stock** session)共用同一格,
        讓 W-12「歷史從持有其 REALTIME 訂閱的 session 問」在快取層被繞過(review P1-6)。"""
        src = FakeIndexSource()
        with make_client(index_source=src) as c:
            c.get("/api/market/bars/TWSE?tf=1&days=1")
            # 個股路徑不存在(未注入 stock source)→ 503;重點是 market 端不受污染
            c.get("/api/market/bars/TWSE?tf=D")
        # 分鐘與長窗各打一次(共用同一格的話第二次會 cache hit 到錯的那份)
        assert [call[1] for call in src.calls] == ["1", "D"]


class TestPartialLast:
    """`partial_last` 由資料判定,不是 tf 的常數(review P1-1)。"""

    def _src(self, last_date: str) -> FakeIndexSource:
        class Fixed(FakeIndexSource):
            def fetch_bars_range_tagged(
                self, code: str, tf: str, start: str, end: str
            ) -> tuple[list[dict], str]:
                return [_dbar(last_date, 1_000)], "tc4_dk"

        return Fixed()

    def test_today_daily_bar_is_partial(self) -> None:
        with make_client(index_source=self._src(_TODAY)) as c:
            r = c.get("/api/market/bars/TWSE?tf=D")
        assert r.json()["meta"]["partial_last"] is True

    def test_old_daily_bar_is_not_partial(self) -> None:
        with make_client(index_source=self._src("2020-01-02")) as c:
            r = c.get("/api/market/bars/TWSE?tf=D")
        assert r.json()["meta"]["partial_last"] is False

    def test_old_week_bucket_is_not_partial(self) -> None:
        """週末查已收盤的週 K 不該恆標「未收盤」(舊實作 tf != "D" 就恆 True)。"""
        with make_client(index_source=self._src("2020-01-02")) as c:
            r = c.get("/api/market/bars/TWSE?tf=W")
        assert r.json()["meta"]["partial_last"] is False

    def test_current_week_and_month_are_partial(self) -> None:
        with make_client(index_source=self._src(_TODAY)) as c:
            assert c.get("/api/market/bars/TWSE?tf=W").json()["meta"]["partial_last"] is True
            assert c.get("/api/market/bars/TWSE?tf=M").json()["meta"]["partial_last"] is True
