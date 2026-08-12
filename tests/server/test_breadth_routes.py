"""家數帶 API/WS 接線(market-overview R2 Task 7;design §6)— SC-3。

R4 併入:類股輪動兩條 route(§5)、取數五元組、廣度事件的 hub attach/detach 接線(§8)。

**禁止真打 FinMind / 禁起 TC4**:取數五元組全部注入 fake、TXO 走 `FakeTxoSource`,
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
from copycat.server.breadth_fetch import CHAIN_MIN_ROWS, BreadthFetchError
from copycat.server.mis import OtcSnap
from tests.helpers.boot import BootedClient
from tests.helpers.fake_sources import FakeIndexSource
from tests.helpers.fake_txo import FakeTxoSource
from tests.server.test_stock_routes import FakeStockSource

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


#: 產業鏈對照(R4):1101 獨佔水泥;2330 / 6488 同屬半導體的兩個子產業。
#: 手算 rotation —— 水泥 avg = 10.0;半導體 avg = (0.5 + (-10.0)) / 2 = -4.75 → 水泥在前。
_CHAIN_ROWS: list[dict] = [
    {"date": "2026-08-01", "stock_id": "1101", "industry": "水泥", "sub_industry": "水泥製造"},
    {"date": "2026-08-01", "stock_id": "2330", "industry": "半導體", "sub_industry": "晶圓代工"},
    {"date": "2026-08-01", "stock_id": "6488", "industry": "半導體", "sub_industry": "矽晶圓"},
]

#: 過 `CHAIN_MIN_ROWS`(部分截斷健檢)的墊列。代號取 9000 段 = **不在 universe**,
#: `_group_stats` 回 None → 那些產業天然不進 rotation,手算對照一格不動。
_CHAIN_PAD: list[dict] = [
    {
        "date": "2026-08-01",
        "stock_id": f"{9000 + i}",
        "industry": "墊檔",
        "sub_industry": "墊檔",
    }
    for i in range(CHAIN_MIN_ROWS - len(_CHAIN_ROWS))
]


def _ok_fetchers(*, chain: bool = False) -> BreadthFetchers:
    """第四槽(EOD 日線)刻意給 `None` = 連板停用(契約的一部分,R3 R20)。

    本檔驗的是 route 形狀與接線;真要在這裡餵日線,引擎的 `_DAILY_MIN_ROWS` 健檢
    會逼每個 fake 日回 25,000 列 —— 連板編排的行為面在 test_breadth_engine 已逐條覆蓋。

    第五槽(產業鏈)預設同樣 `None` = 類股輪動停用(R4;`rotation` 恆 null)——
    要驗 rotation 有值的那條路才傳 `chain=True`。
    """
    return (
        lambda _token: _snapshot_rows(),
        lambda _token: list(_INFO_ROWS),
        lambda _token, _today: [],
        None,
        (lambda _token: [*_CHAIN_ROWS, *_CHAIN_PAD]) if chain else None,
    )


def _raising_fetchers() -> BreadthFetchers:
    """五個取數點全炸 —— SC-3 的失效注入(FinMind 整段掛掉,含 EOD 日線與產業鏈那兩支)。"""

    def _boom(*_a: object) -> list[dict]:
        raise BreadthFetchError("fake FinMind down")

    return (_boom, _boom, _boom, _boom, _boom)


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


def _wait_rotation(client: TestClient, timeout: float = 5.0) -> dict:
    """輪詢到 rotation 有值。

    chain 刷新是**獨立 task**(design §4.3)—— 家數首輪完成不代表 chain 已換表,
    等 counts 就斷言 rotation 會偶發紅(競態)。
    """
    deadline = time.monotonic() + timeout
    while True:
        payload = client.get("/api/market/sector").json()
        if payload["rotation"] is not None:
            return payload
        if time.monotonic() > deadline:
            raise AssertionError(f"rotation 未在 {timeout}s 內就緒:{payload}")
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
    def test_four_tuple_is_rejected_with_explicit_log(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """舊四元組(repo 外的側車樣板漏改第五槽)必須**炸而且說清楚**。

        出處 = impl-spec review R8「arity 防呆」;design §3.3a v3 未載,實作期補強
        (design 自己的 R8 是另一件事:漲跌停列表的排序優先序)。

        `_boot` 的傘罩會把任何例外收成「breadth 停用」,與「FINMIND_TOKEN 未設」在
        畫面上同形 —— 沒有這行 error log 的話,漏改一個呼叫端的症狀是家數面板悄悄
        整段消失,查不到原因。
        """
        def _f(*_a: object) -> list[dict]:
            return []

        app = _make_app(breadth_fetchers=(_f, _f, _f, _f), breadth_data_dir=tmp_path)
        with caplog.at_level(logging.ERROR):
            with BootedClient(app, raise_server_exceptions=False) as c:
                assert app.state.breadth is None
                assert c.get("/api/market/breadth/rows").json()["enabled"] is False
        assert any("預期 5" in rec.getMessage() for rec in caplog.records)


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

    def test_engine_absent_closes(self) -> None:
        with _client() as c:
            with c.websocket_connect("/ws/breadth") as ws:
                # 引擎停用 → accept 後即關(`/ws/index` 同處置),不得讓 client 空等
                with pytest.raises(WebSocketDisconnect):
                    ws.receive_json()

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

    def test_before_boot_sends_loading_frame_then_closes(self, tmp_path: Path) -> None:
        """boot 未完成:先送一則載入中 scalar 再關(client 自行退避重連,屆時 boot 已完成)
        —— 與 REST 同語意,不與「未設定」同形(review P2-1)。"""
        client = TestClient(
            _make_app(breadth_fetchers=_ok_fetchers(), breadth_data_dir=tmp_path),
            raise_server_exceptions=False,
        )
        with client.websocket_connect("/ws/breadth") as ws:
            first = ws.receive_json()
            assert first["type"] == "breadth"
            assert first["counts"] is None
            assert first["stale"] is True
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()


class TestProdWiring:
    """`DEFAULT_BREADTH` sentinel → 真取數五元組(prod 唯一走的那條路;review TC-1)。

    五個 `breadth_fetch.*` 一律先 monkeypatch 成會拋的替身:引擎 start 後首圈就會打,
    不換掉等於讓測試真打 FinMind。身分比對(`is`)而非「有五個 callable」——
    元組調序是這條接線最可能的錯誤,而它的失效樣態是家數恆為 0(取數層互換後
    snapshot 拿到對照表格式),沒有任何錯誤訊號。
    """

    @pytest.fixture
    def fetchers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> tuple[Callable, Callable, Callable, Callable, Callable]:
        def _make(name: str) -> Callable[..., list[dict]]:
            def _f(*_a: object) -> list[dict]:
                raise BreadthFetchError(f"{name} 不得真打")

            return _f

        quint = (
            _make("snapshot"),
            _make("stock_info"),
            _make("disposition"),
            _make("daily_prices"),
            _make("industry_chain"),
        )
        monkeypatch.setattr(breadth_fetch, "fetch_snapshot", quint[0])
        monkeypatch.setattr(breadth_fetch, "fetch_stock_info", quint[1])
        monkeypatch.setattr(breadth_fetch, "fetch_disposition", quint[2])
        monkeypatch.setattr(breadth_fetch, "fetch_daily_prices", quint[3])
        monkeypatch.setattr(breadth_fetch, "fetch_industry_chain", quint[4])
        return quint

    def test_default_sentinel_wires_real_fetchers_in_order(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        fetchers: tuple[Callable, Callable, Callable, Callable, Callable],
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
            # 第五支漏接 = 類股面板整天「資料未就緒」,同樣零錯誤訊號(R4)
            assert engine._chain_fetch is fetchers[4]

    def test_default_sentinel_disabled_without_token(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        fetchers: tuple[Callable, Callable, Callable, Callable, Callable],
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


class TestSectorRest:
    """`GET /api/market/sector` 三態(R4 design §5)—— 判式與 `/api/market/breadth` 同款。"""

    def test_engine_absent_returns_disabled_shape(self) -> None:
        with _client() as c:
            r = c.get("/api/market/sector")
        assert r.status_code == 200
        assert r.json() == {
            "enabled": False,
            "trade_date": None,
            "as_of": None,
            "stale": False,
            "rotation": None,
        }

    def test_before_boot_returns_loading_shape(self, tmp_path: Path) -> None:
        """boot 未完成 → 載入中(enabled=true / stale=true),不得與「未設定」同形。"""
        client = TestClient(
            _make_app(breadth_fetchers=_ok_fetchers(chain=True), breadth_data_dir=tmp_path),
            raise_server_exceptions=False,
        )
        r = client.get("/api/market/sector")
        assert r.status_code == 200
        assert r.json() == {
            "enabled": True,
            "trade_date": None,
            "as_of": None,
            "stale": True,
            "rotation": None,
        }

    def test_booted_without_chain_returns_null_rotation(self, tmp_path: Path) -> None:
        """boot 完成、chain 未就緒 → **200 且 rotation=null**(不是 503,也不是空清單)。

        空 `industries` 會被前端讀成「今天所有產業都沒成員」;null 才是「還沒有資料」。
        """
        with _client(breadth_fetchers=_ok_fetchers(), breadth_data_dir=tmp_path) as c:
            _wait_counts(c)
            body = c.get("/api/market/sector").json()
        assert body["enabled"] is True
        assert body["trade_date"] == _TODAY.isoformat()
        assert body["as_of"] == "10:23:45"
        assert body["rotation"] is None

    def test_rotation_payload_carries_engine_computation(self, tmp_path: Path) -> None:
        with _client(breadth_fetchers=_ok_fetchers(chain=True), breadth_data_dir=tmp_path) as c:
            body = _wait_rotation(c)

        assert set(body) == {"enabled", "trade_date", "as_of", "stale", "rotation"}
        assert body["trade_date"] == _TODAY.isoformat()
        assert body["as_of"] == "10:23:45"
        industries = body["rotation"]["industries"]
        # avg desc:水泥 10.0 > 半導體 -4.75
        assert [i["name"] for i in industries] == ["水泥", "半導體"]
        assert industries[0]["members"] == 1
        assert industries[0]["avg_change_rate"] == pytest.approx(10.0)
        assert industries[0]["vol_ratio"] == pytest.approx(2.0)  # 1000 / 500
        assert industries[1]["members"] == 2
        assert industries[1]["avg_change_rate"] == pytest.approx(-4.75)
        assert [s["name"] for s in industries[1]["subs"]] == ["晶圓代工", "矽晶圓"]


class TestSectorMembers:
    """`GET /api/market/sector/members` 三語意(design §5 / R10)。"""

    def test_missing_industry_is_422(self, tmp_path: Path) -> None:
        """`industry` **缺席** = 呼叫端寫錯 → FastAPI required query 的 422。

        與「查無此產業」的 404 刻意分開:前者是程式 bug、後者是資料還沒到。
        """
        with _client(breadth_fetchers=_ok_fetchers(chain=True), breadth_data_dir=tmp_path) as c:
            _wait_rotation(c)
            r = c.get("/api/market/sector/members")
        assert r.status_code == 422

    def test_blank_industry_is_404(self, tmp_path: Path) -> None:
        """空字串 industry → 404(chain_map 沒有 "" 桶:缺 sub 的列整列丟)。"""
        with _client(breadth_fetchers=_ok_fetchers(chain=True), breadth_data_dir=tmp_path) as c:
            _wait_rotation(c)
            r = c.get("/api/market/sector/members", params={"industry": ""})
        assert r.status_code == 404
        assert r.json()["detail"]["error"] == "SECTOR_NOT_FOUND"

    def test_unknown_industry_is_404(self, tmp_path: Path) -> None:
        with _client(breadth_fetchers=_ok_fetchers(chain=True), breadth_data_dir=tmp_path) as c:
            _wait_rotation(c)
            r = c.get("/api/market/sector/members", params={"industry": "不存在的產業"})
        assert r.status_code == 404
        assert r.json()["detail"]["error"] == "SECTOR_NOT_FOUND"

    def test_unknown_sub_is_404(self, tmp_path: Path) -> None:
        with _client(breadth_fetchers=_ok_fetchers(chain=True), breadth_data_dir=tmp_path) as c:
            _wait_rotation(c)
            r = c.get(
                "/api/market/sector/members", params={"industry": "半導體", "sub": "不存在的子業"}
            )
        assert r.status_code == 404
        assert r.json()["detail"]["error"] == "SECTOR_NOT_FOUND"

    def test_known_industry_returns_members(self, tmp_path: Path) -> None:
        with _client(breadth_fetchers=_ok_fetchers(chain=True), breadth_data_dir=tmp_path) as c:
            _wait_rotation(c)
            r = c.get("/api/market/sector/members", params={"industry": "半導體"})
        assert r.status_code == 200
        body = r.json()
        assert body["industry"] == "半導體"
        assert body["sub_industry"] is None
        # change_rate desc:2330(+0.5)在 6488(-10.0)之前
        assert [m["stock_id"] for m in body["members"]] == ["2330", "6488"]
        assert body["members"][0]["name"] == "台積電"
        assert body["members"][0]["vol_ratio"] == pytest.approx(2.0)

    def test_blank_sub_is_treated_as_unspecified(self, tmp_path: Path) -> None:
        """`sub=`(空字串)**當未指定** —— 前端不帶 sub 時送空字串是最容易寫出的形狀,
        當成「子產業名為空」查就會回 404,而畫面上與「這個產業沒有成員」同形。"""
        with _client(breadth_fetchers=_ok_fetchers(chain=True), breadth_data_dir=tmp_path) as c:
            _wait_rotation(c)
            r = c.get("/api/market/sector/members", params={"industry": "半導體", "sub": ""})
        assert r.status_code == 200
        body = r.json()
        assert body["sub_industry"] is None
        assert [m["stock_id"] for m in body["members"]] == ["2330", "6488"]

    def test_sub_narrows_members(self, tmp_path: Path) -> None:
        with _client(breadth_fetchers=_ok_fetchers(chain=True), breadth_data_dir=tmp_path) as c:
            _wait_rotation(c)
            r = c.get(
                "/api/market/sector/members", params={"industry": "半導體", "sub": "矽晶圓"}
            )
        assert r.status_code == 200
        body = r.json()
        assert body["sub_industry"] == "矽晶圓"
        assert [m["stock_id"] for m in body["members"]] == ["6488"]

    def test_engine_absent_is_404(self) -> None:
        """引擎缺席 → 同一個錯誤碼(沒有引擎就沒有任何產業;不是 503)。"""
        with _client() as c:
            r = c.get("/api/market/sector/members", params={"industry": "半導體"})
        assert r.status_code == 404
        assert r.json()["detail"]["error"] == "SECTOR_NOT_FOUND"


class TestSignalHubWiring:
    """廣度事件入匯流排的接線(design §8)。

    漏 attach 的失效樣態 = 全市場鎖板事件整天不產生(`_diff_limit_events` 對 hub None
    早退,連狀態機都不推進)—— 畫面上與「今天沒有漲停」完全同形,沒有錯誤訊號。
    漏 detach 則相反:關機序 breadth 先收,close 之後才摘掛點的話,收攤中的那一輪
    會對還沒 close 的 hub 發事件(或反過來對已 close 的 hub 發)。
    """

    def _app(self, tmp_path: Path):
        return _make_app(
            breadth_fetchers=_ok_fetchers(),
            breadth_data_dir=tmp_path,
            stock_source=FakeStockSource(),
            stock_watchlist_path=tmp_path / "watchlist.json",
        )

    def test_hub_attached_after_breadth_boot(self, tmp_path: Path) -> None:
        app = self._app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False):
            assert app.state.signal_hub is not None
            assert app.state.breadth is not None
            assert app.state.breadth._signal_hub is app.state.signal_hub

    def test_stock_absent_still_attaches_hub(self, tmp_path: Path) -> None:
        """SC-6(🔴 XR-3):stock 引擎缺席**不再**讓 hub 消失 → breadth 照掛。

        舊行為(hub 綁 stock)下,達錢 4 沒開的早上這條掛載條件不成立 → 全市場鎖板
        事件整天不產生,而畫面上與「今天沒有漲停」完全同形。廣度鏈是純 FinMind,
        與 TC4 在否無關,這條就是那個不變式的錨點。
        """
        app = _make_app(breadth_fetchers=_ok_fetchers(), breadth_data_dir=tmp_path)
        with BootedClient(app, raise_server_exceptions=False):
            assert app.state.stock is None
            assert app.state.signal_hub is not None
            assert app.state.breadth is not None
            assert app.state.breadth._signal_hub is app.state.signal_hub

    def test_detach_happens_before_close(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict[str, object] = {}
        app = self._app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False):
            engine = app.state.breadth
            assert engine is not None
            orig_close = engine.close

            async def _spy_close() -> None:
                seen["hub"] = engine._signal_hub
                await orig_close()

            monkeypatch.setattr(engine, "close", _spy_close)

        assert "hub" in seen, "關機序沒有呼叫 breadth.close()"
        assert seen["hub"] is None, "detach 必須在 close 之前"
