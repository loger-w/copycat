"""家數帶 API/WS 接線(market-overview R2 Task 7;design §6)— SC-3。

**禁止真打 FinMind / 禁起 TC4**:取數四元組全部注入 fake、TXO 走 `FakeTxoSource`,
整條路不碰網路也不碰 ZMQ。

`BootedClient`(design R12):啟動序列已背景化,`with TestClient(app)` 返回只代表
HTTP 面可用 —— breadth 引擎是否掛上去要等 boot 序列結束才問得準。
"""

from __future__ import annotations

import datetime as _dt
import logging
import time
from pathlib import Path
from typing import Callable

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

import copycat.server.breadth_engine as be
import copycat.server.breadth_fetch as breadth_fetch
import copycat.server.finmind_token as finmind_token
from copycat.breadth_config import BreadthConfig
from copycat.server import app as app_mod
from copycat.server.app import DEFAULT_BREADTH, BreadthFetchers, create_app
from copycat.server.breadth_fetch import BreadthFetchError
from copycat.server.mis import OtcSnap
from tests.helpers.boot import BootedClient
from tests.helpers.fake_sources import FakeIndexSource
from tests.helpers.fake_txo import FakeTxoSource

#: 快照時刻固定用**今天** 10:23:45:trade_date == today 才會 append(design R1),
#: 而 10:23:45 → 分鐘鍵 "1024" 落在域內 —— 兩者都與測試實跑時刻無關。
_TODAY = _dt.date.today()
_STAMP = f"{_TODAY.isoformat()} 10:23:45"
_KEY = "1024"

_INFO_ROWS: list[dict] = [
    {
        "date": "2026-08-01",
        "stock_id": "1101",
        "stock_name": "台泥",
        "type": "twse",
        "industry_category": "水泥工業",
    },
    {
        "date": "2026-08-01",
        "stock_id": "2330",
        "stock_name": "台積電",
        "type": "twse",
        "industry_category": "半導體業",
    },
    {
        "date": "2026-08-01",
        "stock_id": "6488",
        "stock_name": "環球晶",
        "type": "tpex",
        "industry_category": "半導體業",
    },
]

#: 手算:1101 前收 10.0 → 漲停 11.0;6488 前收 10.0 → 跌停 9.0;2330 前收 995.0 →
#: 漲停 1094.5 ≠ 1000.0 故只是上漲。
_EXPECTED_TWSE = {"limit_up": 1, "up": 1, "flat": 0, "down": 0, "limit_down": 0}
_EXPECTED_TPEX = {"limit_up": 0, "up": 0, "flat": 0, "down": 0, "limit_down": 1}


@pytest.fixture(autouse=True)
def _fixed_now(monkeypatch: pytest.MonkeyPatch) -> None:
    """引擎的牆上時鐘釘在今天 10:24(`_STAMP` 的下一分鐘)。

    引擎在 lifespan 內建構 → 這個檔案沒有 `now_fn` 注入點,只能 monkeypatch 模組層的
    `_now`。不釘的話兩件事會跟著實跑時刻飄:快照時刻超前本機時鐘 10 分鐘以上會被當
    髒 row 忽略(review P1-2)→ 早上 10:14 之前跑整批紅;窗判定(09:00–13:40)也同理。
    """
    monkeypatch.setattr(be, "_now", lambda: _dt.datetime.combine(_TODAY, _dt.time(10, 24)))


def _snapshot_rows() -> list[dict]:
    def row(sid: str, close: float, chg_price: float, chg_rate: float) -> dict:
        return {
            "date": _STAMP,
            "stock_id": sid,
            "close": close,
            "change_price": chg_price,
            "change_rate": chg_rate,
            "total_volume": 1000,
            "yesterday_volume": 500,
            "total_amount": 12_345,
        }

    return [
        row("1101", 11.0, 1.0, 10.0),
        row("2330", 1000.0, 5.0, 0.5),
        row("6488", 9.0, -1.0, -10.0),
    ]


def _ok_fetchers() -> BreadthFetchers:
    """第四槽(EOD 日線)刻意給 `None` = 連板停用(契約的一部分,R3 R20)。

    本檔驗的是 route 形狀與接線;真要在這裡餵日線,引擎的 `_DAILY_MIN_ROWS` 健檢
    會逼每個 fake 日回 25,000 列 —— 連板編排的行為面在 test_breadth_engine 已逐條覆蓋。
    """
    return (
        lambda _token: _snapshot_rows(),
        lambda _token: list(_INFO_ROWS),
        lambda _token, _today: [],
        None,
    )


def _raising_fetchers() -> BreadthFetchers:
    """四個取數點全炸 —— SC-3 的失效注入(FinMind 整段掛掉,含 EOD 日線那一支)。"""

    def _boom(*_a: object) -> list[dict]:
        raise BreadthFetchError("fake FinMind down")

    return (_boom, _boom, _boom, _boom)


def _mis() -> OtcSnap | None:
    return None


def _make_app(
    *,
    breadth_fetchers: object | None = None,
    breadth_data_dir: Path | None = None,
    index_source: FakeIndexSource | None = None,
    stock_source: object | None = None,
    stock_watchlist_path: Path | None = None,
):
    return create_app(
        FakeTxoSource(),
        stock_source=stock_source,
        stock_watchlist_path=stock_watchlist_path,
        index_source=index_source,
        index_mis_fetch=_mis,
        breadth_fetchers=breadth_fetchers,
        breadth_data_dir=breadth_data_dir,
        throttle_secs=0.01,
    )


def _client(
    *,
    breadth_fetchers: object | None = None,
    breadth_data_dir: Path | None = None,
    index_source: FakeIndexSource | None = None,
) -> TestClient:
    app = _make_app(
        breadth_fetchers=breadth_fetchers,
        breadth_data_dir=breadth_data_dir,
        index_source=index_source,
    )
    return BootedClient(app, raise_server_exceptions=False)


def _wait_counts(client: TestClient, timeout: float = 5.0) -> dict:
    """輪詢到首輪 poll 完成(counts 非 null)。

    首圈 fetch 在 poll task 上跑(`start()` 零網路 IO,design R6)→ boot 結束不代表
    已有數字,不等就會斷言到「載入中」那一態。
    """
    deadline = time.monotonic() + timeout
    while True:
        payload = client.get("/api/market/breadth").json()
        if payload["counts"] is not None:
            return payload
        if time.monotonic() > deadline:
            raise AssertionError(f"breadth 首輪未在 {timeout}s 內完成:{payload}")
        time.sleep(0.01)


class TestBreadthRest:
    def test_engine_absent_returns_disabled_shape(self) -> None:
        """引擎缺席(未注入取數層 = FINMIND_TOKEN 未設)→ 恆 200 的 enabled=false 三態。"""
        with _client() as c:
            r = c.get("/api/market/breadth")
        assert r.status_code == 200
        assert r.json() == {
            "enabled": False,
            "trade_date": None,
            "as_of": None,
            "stale": False,
            "counts": None,
            "series": [],
        }

    def test_fake_fetchers_enabled_with_counts(self, tmp_path: Path) -> None:
        with _client(breadth_fetchers=_ok_fetchers(), breadth_data_dir=tmp_path) as c:
            body = _wait_counts(c)
        assert body["enabled"] is True
        assert body["trade_date"] == _TODAY.isoformat()
        assert body["as_of"] == "10:23:45"
        assert body["counts"] == {"twse": _EXPECTED_TWSE, "tpex": _EXPECTED_TPEX}
        assert body["series"] == [{"t": _KEY, "twse": [1, 1, 0, 0, 0], "tpex": [0, 0, 0, 0, 1]}]

    def test_before_boot_returns_loading_shape(self, tmp_path: Path) -> None:
        """create_app 期(lifespan 未進場 / boot 未完成)直打 —— `app.state.breadth` 還不存在。

        沒有 getattr 預設的話這裡是 AttributeError → 全域 handler 轉 502 TC4_DOWN,
        而那句訊息與真因(啟動窗還沒開)完全無關。**但也不能回 enabled=false**:
        breadth 排在 boot 序列最後,開站頭幾秒必然落在這個窗,回「未設定」會讓前端
        在每次重啟時閃一次「FINMIND_TOKEN 未設定」的假訊息(review P2-1)。
        """
        client = TestClient(
            _make_app(breadth_fetchers=_ok_fetchers(), breadth_data_dir=tmp_path),
            raise_server_exceptions=False,
        )
        r = client.get("/api/market/breadth")
        assert r.status_code == 200
        assert r.json() == {
            "enabled": True,
            "trade_date": None,
            "as_of": None,
            "stale": True,
            "counts": None,
            "series": [],
        }


#: `/api/market/breadth/rows` 每列的完整欄位(design §4 契約)。整組等值比對而不是
#: 逐欄 `in`:漏欄與多欄都要紅 —— 前端型別直譯這份契約,少一欄是 undefined、多一欄
#: 是無人消費的頻寬(rows payload 每 10 秒數百 KB)。
_ROW_FIELDS = {
    "stock_id",
    "name",
    "market",
    "close",
    "change_rate",
    "volume_ratio",
    "total_amount",
    "limit_up",
    "limit_down",
    # SC-5 diff 事件源前置(design §6.1):limit 旗標是判定結果還是缺值預設。
    # 前端不消費,但 rows payload 是 `rows_state()` 直通,這裡如實釘住實際契約。
    "limit_judged",
    "touched_limit_up",
    "touched_limit_down",
    "streak",
    "streak_capped",
}


class TestBreadthRowsRest:
    """`GET /api/market/breadth/rows` 三態 + 契約(R3 SC-1)。

    與 `/api/market/breadth` 同款恆 200 三態(未設定 / 載入中 / 有引擎),理由相同:
    503 會被 TanStack 的 error 路徑吞成同一種紅色。
    """

    def test_engine_absent_returns_disabled_shape(self) -> None:
        with _client() as c:
            r = c.get("/api/market/breadth/rows")
        assert r.status_code == 200
        assert r.json() == {
            "enabled": False,
            "trade_date": None,
            "as_of": None,
            "stale": False,
            "streaks_ready": False,
            "rows": [],
        }

    def test_before_boot_returns_loading_shape(self, tmp_path: Path) -> None:
        """boot 未完成 → 載入中(enabled=true / stale=true),不得與「未設定」同形。"""
        client = TestClient(
            _make_app(breadth_fetchers=_ok_fetchers(), breadth_data_dir=tmp_path),
            raise_server_exceptions=False,
        )
        r = client.get("/api/market/breadth/rows")
        assert r.status_code == 200
        assert r.json() == {
            "enabled": True,
            "trade_date": None,
            "as_of": None,
            "stale": True,
            "streaks_ready": False,
            "rows": [],
        }

    def test_rows_payload_matches_contract(self, tmp_path: Path) -> None:
        with _client(breadth_fetchers=_ok_fetchers(), breadth_data_dir=tmp_path) as c:
            _wait_counts(c)
            body = c.get("/api/market/breadth/rows").json()

        assert set(body) == {"enabled", "trade_date", "as_of", "stale", "streaks_ready", "rows"}
        assert body["enabled"] is True
        assert body["trade_date"] == _TODAY.isoformat()
        assert body["as_of"] == "10:23:45"
        assert body["streaks_ready"] is False  # daily_fetch=None → 連板停用
        by_id = {r["stock_id"]: r for r in body["rows"]}
        assert set(by_id) == {"1101", "2330", "6488"}
        assert set(by_id["1101"]) == _ROW_FIELDS
        assert by_id["1101"]["limit_up"] is True
        assert by_id["1101"]["streak"] is None  # 未就緒 → null(不是 0,更不是 1)
        assert by_id["1101"]["streak_capped"] is False

    def test_rows_carry_engine_streak_merge(self, tmp_path: Path) -> None:
        """route 必須回 `rows_state()` 的**算術結果**,不是自己拼一份 rows。

        直接種引擎的 streak 成果(昨日止 2 板)→ 今日盤中的漲停列要是 3。
        route 若改回 `{"rows": engine.rows}` 之類的直通,這裡就會紅。
        """
        app = _make_app(breadth_fetchers=_ok_fetchers(), breadth_data_dir=tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as c:
            _wait_counts(c)
            engine = app.state.breadth
            assert engine is not None
            engine._streaks = {"1101": 2}
            engine._streaks_day = _TODAY.isoformat()
            engine._streaks_end = (_TODAY - _dt.timedelta(days=1)).isoformat()
            engine._streaks_span = 10
            body = c.get("/api/market/breadth/rows").json()

        assert body["streaks_ready"] is True
        by_id = {r["stock_id"]: r for r in body["rows"]}
        assert by_id["1101"]["streak"] == 3
        assert by_id["1101"]["streak_capped"] is False
        assert by_id["2330"]["streak"] is None  # 非漲停列恆 null


class TestFetchersArity:
    """非四元組的注入必須**炸而且說清楚**(兩側都驗:少一槽 / 多一槽)。

    出處 = impl-spec review R8「arity 防呆」;design §3.3a v3 未載,實作期補強
    (design 自己的 R8 是另一件事:漲跌停列表的排序優先序)。

    `_boot` 的傘罩會把任何例外收成「breadth 停用」,與「FINMIND_TOKEN 未設」在
    畫面上同形 —— 沒有這行 error log 的話,漏改一個呼叫端的症狀是家數面板悄悄
    整段消失,查不到原因。
    """

    def _assert_rejected(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture, fetchers: tuple
    ) -> None:
        app = _make_app(breadth_fetchers=fetchers, breadth_data_dir=tmp_path)
        with caplog.at_level(logging.ERROR):
            with BootedClient(app, raise_server_exceptions=False) as c:
                assert app.state.breadth is None
                assert c.get("/api/market/breadth/rows").json()["enabled"] is False
        assert any("預期 4" in rec.getMessage() for rec in caplog.records)

    def test_three_tuple_is_rejected_with_explicit_log(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        def _f(*_a: object) -> list[dict]:
            return []

        self._assert_rejected(tmp_path, caplog, (_f, _f, _f))

    def test_five_tuple_is_rejected_with_explicit_log(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """舊五元組(repo 外的側車樣板還帶著已刪的 industry_chain 槽)同樣要炸。"""

        def _f(*_a: object) -> list[dict]:
            return []

        self._assert_rejected(tmp_path, caplog, (_f, _f, _f, _f, _f))


class TestBreadthWebSocket:
    def test_first_frame_is_scalar_seed(self, tmp_path: Path) -> None:
        with _client(breadth_fetchers=_ok_fetchers(), breadth_data_dir=tmp_path) as c:
            _wait_counts(c)
            with c.websocket_connect("/ws/breadth") as ws:
                first = ws.receive_json()
        assert first["type"] == "breadth"
        assert set(first) == {"type", "trade_date", "as_of", "stale", "counts", "last_minute"}
        assert first["trade_date"] == _TODAY.isoformat()
        assert first["counts"] == {"twse": _EXPECTED_TWSE, "tpex": _EXPECTED_TPEX}

    def test_engine_absent_rejects_handshake(self) -> None:
        # R4 N036(由「accept 後即關」翻轉):引擎停用 → 握手前就 close(uvicorn 回 403),
        # TestClient 在進場那一步就拋;browser 端 onopen 不觸發、走「從未 open」退避。
        with _client() as c:
            with pytest.raises(WebSocketDisconnect):
                with c.websocket_connect("/ws/breadth"):
                    raise AssertionError("引擎停用時握手不該成功")

    def test_second_frame_carries_last_minute(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """route 層的第二則(= 下一輪 poll 的增量)必須帶 `last_minute`(review TC-4)。

        首則是 `stream()` 內建的 seed,增量路徑要再等一輪才走得到 —— 只驗首則的話,
        `payload(last_minute)` 沒接上去也照樣綠(前端的分鐘格全靠這個欄位)。
        poll 間隔由 `load_breadth_config` 注入點壓到 0.05s(engine 無 config 參數)。
        """
        monkeypatch.setattr(app_mod, "load_breadth_config", lambda: BreadthConfig(poll_secs=0.05))
        with _client(breadth_fetchers=_ok_fetchers(), breadth_data_dir=tmp_path) as c:
            _wait_counts(c)
            with c.websocket_connect("/ws/breadth") as ws:
                ws.receive_json()  # seed
                second = ws.receive_json()

        assert second["type"] == "breadth"
        assert second["last_minute"] == {"t": _KEY, "twse": [1, 1, 0, 0, 0], "tpex": [0, 0, 0, 0, 1]}

    def test_before_boot_rejects_handshake(self, tmp_path: Path) -> None:
        """boot 未完成:握手前就拒(R4 N036,由「先送載入中 scalar 再關」翻轉)。

        載入中語意由 REST `/api/market/breadth` 承擔(前端對該 WS frame 的處理與 REST 同形,
        無獨立讀者);client 退避重連時 boot 已完成。
        """
        client = TestClient(
            _make_app(breadth_fetchers=_ok_fetchers(), breadth_data_dir=tmp_path),
            raise_server_exceptions=False,
        )
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/breadth"):
                raise AssertionError("boot 未完成時握手不該成功")


class TestProdWiring:
    """`DEFAULT_BREADTH` sentinel → 真取數四元組(prod 唯一走的那條路;review TC-1)。

    四個 `breadth_fetch.*` 一律先 monkeypatch 成會拋的替身:引擎 start 後首圈就會打,
    不換掉等於讓測試真打 FinMind。身分比對(`is`)而非「有四個 callable」——
    元組調序是這條接線最可能的錯誤,而它的失效樣態是家數恆為 0(取數層互換後
    snapshot 拿到對照表格式),沒有任何錯誤訊號。
    """

    @pytest.fixture
    def fetchers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> tuple[Callable, Callable, Callable, Callable]:
        def _make(name: str) -> Callable[..., list[dict]]:
            def _f(*_a: object) -> list[dict]:
                raise BreadthFetchError(f"{name} 不得真打")

            return _f

        quad = (
            _make("snapshot"),
            _make("stock_info"),
            _make("disposition"),
            _make("daily_prices"),
        )
        monkeypatch.setattr(breadth_fetch, "fetch_snapshot", quad[0])
        monkeypatch.setattr(breadth_fetch, "fetch_stock_info", quad[1])
        monkeypatch.setattr(breadth_fetch, "fetch_disposition", quad[2])
        monkeypatch.setattr(breadth_fetch, "fetch_daily_prices", quad[3])
        return quad

    def test_default_sentinel_wires_real_fetchers_in_order(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        fetchers: tuple[Callable, Callable, Callable, Callable],
    ) -> None:
        monkeypatch.setattr(finmind_token, "resolve_token", lambda: "tok")
        app = _make_app(breadth_fetchers=DEFAULT_BREADTH, breadth_data_dir=tmp_path)

        with BootedClient(app, raise_server_exceptions=False):
            engine = app.state.breadth
            assert engine is not None
            assert engine._token == "tok"
            assert engine._snapshot_fetch is fetchers[0]
            assert engine._stock_info_fetch is fetchers[1]
            assert engine._disposition_fetch is fetchers[2]
            # 第四支漏接的失效樣態 = 連板欄整天 null(prod 沒有任何錯誤訊號)
            assert engine._daily_fetch is fetchers[3]

    def test_default_sentinel_disabled_without_token(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        fetchers: tuple[Callable, Callable, Callable, Callable],
    ) -> None:
        """FINMIND_TOKEN 未設 = 合法配置(不是失敗)→ 引擎不建、REST 回「未設定」。"""
        monkeypatch.setattr(finmind_token, "resolve_token", lambda: None)
        app = _make_app(breadth_fetchers=DEFAULT_BREADTH, breadth_data_dir=tmp_path)

        with BootedClient(app, raise_server_exceptions=False) as c:
            assert app.state.breadth is None
            assert c.get("/api/market/breadth").json()["enabled"] is False


class TestFailureIsolation:
    def test_breadth_fetch_failure_does_not_affect_index(self, tmp_path: Path) -> None:
        """SC-3:FinMind 整段掛掉只讓家數面板 stale,TC4 系(index)零波及。"""
        with _client(
            breadth_fetchers=_raising_fetchers(),
            breadth_data_dir=tmp_path,
            index_source=FakeIndexSource(day_minutes={"0901": 43_000_000}),
        ) as c:
            index = c.get("/api/index/state")
            breadth = c.get("/api/market/breadth")

        assert index.status_code == 200
        assert index.json()["twse"]["minutes"] == {"0901": 43_000_000}
        # 引擎在(enabled=true)但沒有數字,且以 stale 誠實表述 —— 不是 5xx
        assert breadth.status_code == 200
        body = breadth.json()
        assert body["enabled"] is True
        assert body["counts"] is None
        assert body["stale"] is True

    def test_lifespan_closes_breadth_engine(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """關機反序第一段:lifespan 離場必須 `await breadth.close()`。

        失效樣態安靜且長命:漏 close 的引擎其 poll task 不會停,測試 process 裡是每
        10s 一輪對 FinMind 的真實請求(prod 則是舊 server 的殘留 task 與新 server 搶
        配額、搶同一份 `breadth-<date>.json`)—— 而所有 route 斷言照樣綠。

        `close` 包原件後照呼:只加旗標,不改關機語意(收攤本身仍要真的發生)。
        """
        app = _make_app(breadth_fetchers=_ok_fetchers(), breadth_data_dir=tmp_path)
        closed: list[bool] = []
        with BootedClient(app, raise_server_exceptions=False):
            engine = app.state.breadth
            assert engine is not None, "注入取數層後引擎必存在(否則測到的是停用態)"
            inner = engine.close

            async def _close() -> None:
                closed.append(True)
                await inner()

            monkeypatch.setattr(engine, "close", _close)
        assert closed == [True]


class TestSectorRemoved:
    """`/api/market/sector*` 已隨類股強弱 subtab 一併刪除(2026-08-16 R1)→ 404。

    留這兩支不是為了「驗 FastAPI 會回 404」,而是釘住**對外 API 已消失**這件事:
    route 若被誰復活(例如 revert 半套),舊前端的死碼會跟著復活而沒人發現。
    """

    def test_sector_state_is_404(self, tmp_path: Path) -> None:
        with _client(breadth_fetchers=_ok_fetchers(), breadth_data_dir=tmp_path) as c:
            assert c.get("/api/market/sector").status_code == 404

    def test_sector_members_is_404(self, tmp_path: Path) -> None:
        with _client(breadth_fetchers=_ok_fetchers(), breadth_data_dir=tmp_path) as c:
            r = c.get("/api/market/sector/members", params={"industry": "半導體"})
        assert r.status_code == 404
