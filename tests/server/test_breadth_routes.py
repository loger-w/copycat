"""家數帶 API/WS 接線(market-overview R2 Task 7;design §6)— SC-3。

**禁止真打 FinMind / 禁起 TC4**:取數三元組全部注入 fake、TXO 走 `FakeTxoSource`,
整條路不碰網路也不碰 ZMQ。

`BootedClient`(design R12):啟動序列已背景化,`with TestClient(app)` 返回只代表
HTTP 面可用 —— breadth 引擎是否掛上去要等 boot 序列結束才問得準。
"""

from __future__ import annotations

import datetime as _dt
import time
from pathlib import Path
from typing import Callable

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

import copycat.server.breadth_engine as be
from copycat.server.app import create_app
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
    髒 row 忽略(review P1-2)→ 早上 10:14 之前跑整批紅;窗判定(08:55–13:40)也同理。
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


def _ok_fetchers() -> tuple[
    Callable[[str], list[dict]],
    Callable[[str], list[dict]],
    Callable[[str, _dt.date], list[dict]],
]:
    return (
        lambda _token: _snapshot_rows(),
        lambda _token: list(_INFO_ROWS),
        lambda _token, _today: [],
    )


def _raising_fetchers() -> tuple[
    Callable[[str], list[dict]],
    Callable[[str], list[dict]],
    Callable[[str, _dt.date], list[dict]],
]:
    """三個取數點全炸 —— SC-3 的失效注入(FinMind 整段掛掉)。"""

    def _boom(*_a: object) -> list[dict]:
        raise BreadthFetchError("fake FinMind down")

    return (_boom, _boom, _boom)


def _mis() -> OtcSnap | None:
    return None


def _make_app(
    *,
    breadth_fetchers: object | None = None,
    breadth_data_dir: Path | None = None,
    index_source: FakeIndexSource | None = None,
):
    return create_app(
        FakeTxoSource(),
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
