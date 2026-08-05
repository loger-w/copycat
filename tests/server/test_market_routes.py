"""大盤 K 線 route(index-board N-5 / SC-4/5/6)。

三個分派各自向**持有該 symbol REALTIME 訂閱的那條 session** 問歷史
(CLAUDE.md §8 同 symbol 跨 session 只推一邊):
`TWSE` → index 引擎、`TXF/MXF/TMF` → futures 引擎、`OTC` → 本機合成(TC4 無此 symbol)。
"""

from __future__ import annotations

import datetime as _dt
from typing import Callable

from fastapi.testclient import TestClient

from copycat.server.app import create_app
from copycat.server.mis import OtcSnap
from tests.helpers.boot import BootedClient
from tests.helpers.fake_sources import FakeFuturesSource, FakeIndexSource
from tests.helpers.fake_sources import dbar as _dbar
from tests.helpers.fake_txo import FakeTxoSource

_TODAY = f"{_dt.date.today():%Y-%m-%d}"


def _this_week_days(n: int) -> list[str]:
    """當前 ISO 週的週一起算 `n` 天(必同屬一個 ISO 週,`n <= 7`)。

    週 K 的 `partial_last` 比的是「最後一根的 ISO 週 == today 的 ISO 週」,
    寫死日期的 fixture 一過那週就恆 False —— 測試會因為日曆而紅,與被測行為無關。
    """
    monday = _dt.date.today() - _dt.timedelta(days=_dt.date.today().weekday())
    return [(monday + _dt.timedelta(days=i)).isoformat() for i in range(n)]


class NoHistoryIndexSource(FakeIndexSource):
    """沒有 `fetch_bars_range_tagged` 的來源(舊 source / TC4 不可用的替身)。"""

    fetch_bars_range_tagged = None  # type: ignore[assignment]


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
    return BootedClient(app, raise_server_exceptions=False)


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
        """日/週/月共用同一份長窗日 K —— 第二次請求不得再打一次 TC4。

        fixture 取**當前 ISO 週**的週一~週三(見 `_this_week_days`):三根必同桶,
        且最後一根與 today 同 ISO 週 → `partial_last` 恆 True,哪一天跑都成立
        (含週日 —— ISO 的週日仍屬同一週)。
        """
        mon, tue, wed = _this_week_days(3)
        src = FakeIndexSource(daily_bars=[_dbar(d, 23_000_000) for d in (mon, tue, wed)])
        with make_client(index_source=src) as c:
            c.get("/api/market/bars/TWSE?tf=D")
            r = c.get("/api/market/bars/TWSE?tf=W")
        assert len(src.calls) == 1  # cache hit
        body = r.json()
        assert len(body["bars"]) == 1  # 三根同屬當前 ISO 週
        assert body["bars"][0]["t"] == wed  # 桶以最後一根標記
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
            engine._apply_otc(OtcSnap(p=359_800, ref=378_090, open=0, high=0, low=0, time="101610"))
            engine._apply_otc(OtcSnap(p=360_100, ref=378_090, open=0, high=0, low=0, time="101655"))
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
            359_800,
            360_100,
            359_800,
            360_100,
            0,
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


class TestSessionParam:
    """SC-3:`?session=allday` 三層貫通 + 值域驗證(futures-allday §1.4)。"""

    def test_allday_forwarded_to_source_and_returns_night_bars(self) -> None:
        fut = FakeFuturesSource(today=_TODAY)
        with make_client(index_source=FakeIndexSource(), futures_source=fut) as c:
            r = c.get("/api/market/bars/TXF?tf=1&days=2&session=allday")
        assert r.status_code == 200
        assert set(fut.sessions) == {"allday"}
        assert [b["t"] for b in r.json()["bars"]] == [f"{_TODAY} 09:01", f"{_TODAY} 15:01"]

    def test_default_session_is_day(self) -> None:
        """無 session 參數 = 既有行為(既有 caller / 大盤 tab 零影響)。"""
        fut = FakeFuturesSource(today=_TODAY)
        with make_client(index_source=FakeIndexSource(), futures_source=fut) as c:
            r = c.get("/api/market/bars/TXF?tf=1&days=2")
        assert set(fut.sessions) == {"day"}
        assert [b["t"] for b in r.json()["bars"]] == [f"{_TODAY} 09:01"]

    def test_session_isolated_in_cache_across_requests(self) -> None:
        """先 day 後 allday(同一個 client / 同一份 cache):近全那次必須真的拿到夜盤根。"""
        fut = FakeFuturesSource(today=_TODAY)
        with make_client(index_source=FakeIndexSource(), futures_source=fut) as c:
            c.get("/api/market/bars/TXF?tf=1&days=2")
            r = c.get("/api/market/bars/TXF?tf=1&days=2&session=allday")
        assert [b["t"] for b in r.json()["bars"]] == [f"{_TODAY} 09:01", f"{_TODAY} 15:01"]

    def test_allday_on_non_futures_key_is_400(self) -> None:
        """近全段是期指專屬:加權 / 櫃買沒有夜盤,靜默當 day 處理會讓前端以為有。"""
        with make_client(index_source=FakeIndexSource(), futures_source=FakeFuturesSource()) as c:
            r = c.get("/api/market/bars/TWSE?tf=1&session=allday")
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "INVALID_SESSION"

    def test_unknown_session_value_is_400(self) -> None:
        with make_client(index_source=FakeIndexSource(), futures_source=FakeFuturesSource()) as c:
            r = c.get("/api/market/bars/TXF?tf=1&session=xxx")
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "INVALID_SESSION"

    def test_daily_ignores_session(self) -> None:
        """tf=D 無 session 維度(D-15):不轉給 source、也不進 cache 鍵。"""
        fut = FakeFuturesSource(today=_TODAY)
        with make_client(index_source=FakeIndexSource(), futures_source=fut) as c:
            r = c.get("/api/market/bars/TXF?tf=D&session=allday")
        assert r.status_code == 200
        assert set(fut.sessions) == {"day"}


class TestVolumeMeta:
    """`volume` 由資料判定(2026-07-30 real-env 抓到:加權 DK 的 v 全為 0)。

    指數沒有量欄位 → `_int_field` 缺值回 0 → 整條序列 v=0。標 volume=true 會讓前端
    畫一排貼底的 0 高柱,與「真的零成交」在畫面上無法區分,正是 SC-6 要避免的假造零。
    """

    def test_all_zero_volume_series_reports_volume_false(self) -> None:
        class ZeroVol(FakeIndexSource):
            def fetch_bars_range_tagged(
                self, code: str, tf: str, start: str, end: str
            ) -> tuple[list[dict], str, str]:
                return [{"t": "2026-07-29", "o": 1, "h": 2, "l": 0, "c": 1, "v": 0}], "tc4_dk", "ok"

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
        # `today=_TODAY`:下面那條斷言比的是 import 期算出的 `_TODAY`,治具若在呼叫期
        # 自己重算,跨午夜跑就會兩邊不同日 → 與被測行為無關的假紅
        src = FakeIndexSource(today=_TODAY)
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
            ) -> tuple[list[dict], str, str]:
                return [], "tc4_1k", "ok"

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
            ) -> tuple[list[dict], str, str]:
                return [_dbar(last_date, 1_000)], "tc4_dk", "ok"

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


class TestMarketPayloadUnaffectedByBarsStatus:
    """N-6:個股 bars 的三態 status **不得**滲進 market payload(白名單 6)。

    `meta.source` 是資料源標籤(tc4_dk / tc4_1k / unavailable …),與 status 同構
    (都是 str)—— 誤把帶 status 的 fetcher 接進 `build_period` 會讓它靜默變成 "ok",
    畫面上就是「來源:ok」這種沒人會第一眼認出是 bug 的字(R5 的誤接守門)。
    """

    def test_market_payload_has_no_status_field(self) -> None:
        with make_client(index_source=FakeIndexSource(), futures_source=FakeFuturesSource()) as c:
            for path in ("/api/market/bars/TWSE?tf=D", "/api/market/bars/TWSE?tf=1&days=1"):
                body = c.get(path).json()
                assert "status" not in body
                assert "status" not in body["meta"]

    def test_meta_source_is_never_a_status_word(self) -> None:
        with make_client(index_source=FakeIndexSource(), futures_source=FakeFuturesSource()) as c:
            for path in (
                "/api/market/bars/TWSE?tf=D",
                "/api/market/bars/TWSE?tf=W",
                "/api/market/bars/TWSE?tf=1&days=1",
                "/api/market/bars/TXF?tf=D",
            ):
                source = c.get(path).json()["meta"]["source"]
                assert source not in ("ok", "timeout", "disconnected"), path
