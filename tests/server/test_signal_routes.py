"""訊號 route 與 lifespan 組裝(design §4.5 / §7 — SC-7 / SC-8 / SC-11 / SC-12 後端半)。

hub / detector 自身的行為在 `test_signal_hub.py` 與 `tests/live/test_signal_state.py`,
這裡只釘 **app 層**:

- lifespan 有沒有真的把 hub 掛上去(「靜默降級成沒有訊號」是這一層最可能的失效樣態,
  而且從 API 看起來只是「今天沒訊號」);
- 三條 route 的契約(200 形狀、400 錯誤碼、hub 缺席時的 503);
- `PUT /api/stock/watchlist` 改走 `WatchlistService` 之後的行為(同內容零副作用 🔴)。

`FakeStockSource` 沿用 `test_stock_routes`(tests/replay 同款跨檔 import):StockSource 是
Protocol,fake 複製一份就會在下次 Protocol 加方法時漂移成兩份不同的假引擎。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from copycat.server import app as app_mod
from copycat.server.app import create_app
from tests.helpers.fake_txo import FakeTxoSource
from tests.server.test_stock_routes import FakeStockSource

_ALL_ON = {"cdp_cross": True, "surge_crash": True, "vol_burst": True, "limit_lock": True}


def make_app(tmp_path: Path, *, with_stock: bool = True) -> tuple[FastAPI, FakeStockSource]:
    fake = FakeStockSource()
    app = create_app(
        FakeTxoSource(),
        stock_source=fake if with_stock else None,
        stock_watchlist_path=tmp_path / "watchlist.json",
        throttle_secs=0.01,
    )
    return app, fake


def _signal_row(trade_date: str) -> dict:
    return {
        "type": "signal",
        "id": f"{trade_date}-2330-cdp_cross-ah-10:00:00.123",
        "kind": "cdp_cross",
        "code": "2330",
        "name": "台積電",
        "price": 123_450,
        "time": "10:00:00",
        "levels": ["ah"],
        "direction": "from_below",
        "pct": None,
        "touch_count": 1,
        "trade_date": trade_date,
    }


class TestLifespanWiring:
    """hub 掛不上去的失效樣態是「今天都沒訊號」,沒有任何錯誤訊號 → 這條測試是唯一守門。"""

    def test_signal_hub_service_attached_when_stock_ready(self, tmp_path: Path) -> None:
        app, _ = make_app(tmp_path)
        with TestClient(app, raise_server_exceptions=False):
            assert app.state.signal_hub is not None
            assert app.state.watchlist_service is not None
            # engine 側也要真的接上(只建 hub 不 attach = 一則訊號都不會產生)
            assert app.state.stock._signal_hub is app.state.signal_hub

    def test_discord_bot_none_without_token(self, tmp_path: Path) -> None:
        """conftest 中和 `DISCORD_BOT_TOKEN` → `create_bot` 回 None = SC-8 降級路徑。"""
        app, _ = make_app(tmp_path)
        with TestClient(app, raise_server_exceptions=False):
            assert app.state.discord_bot is None
            assert app.state.signal_hub is not None  # bot 缺席不得連帶關掉訊號

    def test_boot_seeds_hub_watchlist(self, tmp_path: Path) -> None:
        """啟動時 hub 的 membership 要吃到持久化自選(否則開機後第一輪 tick 全被 gate 掉)。"""
        (tmp_path / "watchlist.json").write_text(
            json.dumps({"_cache_version": 3, "codes": ["2330"], "groups": []}),
            encoding="utf-8",
        )
        app, _ = make_app(tmp_path)
        with TestClient(app, raise_server_exceptions=False):
            assert app.state.signal_hub._watch == {"2330"}

    def test_no_stock_leaves_hub_none(self, tmp_path: Path) -> None:
        app, _ = make_app(tmp_path, with_stock=False)
        with TestClient(app, raise_server_exceptions=False):
            assert app.state.signal_hub is None
            assert app.state.watchlist_service is None


class _ExplodingBot:
    """close 會拋的假 bot(真實對應:token 失效 → discord.py 在收攤路徑上拋)。"""

    def __init__(self) -> None:
        self.closed = False

    def start_bg(self) -> None:
        return None

    async def send_signal(self, text: str) -> bool:
        return True

    async def close(self) -> None:
        self.closed = True
        raise RuntimeError("discord close 炸了")


class TestSignalsShutdownIsolation:
    """關機/啟動失敗路徑的隔離(CC-1 / CC-2)—— 失效樣態全是靜默的。"""

    def test_bot_close_failure_still_closes_hub(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CC-1:bot.close 拋不得讓 hub.close 整段跳過(worker 洩漏 + 關機落檔不跑)。"""
        bot = _ExplodingBot()
        monkeypatch.setattr(app_mod, "create_bot", lambda service, hub: bot)
        app, _ = make_app(tmp_path)
        with TestClient(app, raise_server_exceptions=False):
            hub = app.state.signal_hub
            assert hub is not None
        assert bot.closed is True
        assert hub._tasks == [], "hub 的 worker 沒被收掉 = 洩漏一整天"

    def test_start_failure_leaves_no_zombie_hub_on_engine(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CC-2:`_start_signals` 中途炸掉 → engine 不得留著已收攤的 hub 在熱路徑上。

        殭屍 hub 的樣態:WS 照樣有訊號、jsonl 與 `signals/today` 全空(worker 已死)。
        """

        def _boom(service: object, hub: object) -> object:
            raise RuntimeError("bot 建構炸了")

        monkeypatch.setattr(app_mod, "create_bot", _boom)
        app, _ = make_app(tmp_path)
        with TestClient(app, raise_server_exceptions=False):
            assert app.state.signal_hub is None
            assert app.state.discord_bot is None
            assert app.state.stock is not None  # 其他引擎不受波及
            assert app.state.stock._signal_hub is None

    def test_shutdown_detaches_hub_from_engine(self, tmp_path: Path) -> None:
        """CC-2 後半:收攤後掛點要摘掉,關機序列後半不得再打到已收的 hub。"""
        app, _ = make_app(tmp_path)
        with TestClient(app, raise_server_exceptions=False):
            assert app.state.stock._signal_hub is app.state.signal_hub
        assert app.state.stock._signal_hub is None


class TestSignalsTodayRoute:
    def test_empty_when_no_jsonl(self, tmp_path: Path) -> None:
        app, _ = make_app(tmp_path)
        with TestClient(app, raise_server_exceptions=False) as client:
            assert client.get("/api/stock/signals/today").json() == {"signals": []}

    def test_returns_jsonl_rows(self, tmp_path: Path) -> None:
        app, _ = make_app(tmp_path)
        with TestClient(app, raise_server_exceptions=False) as client:
            trade_date = app.state.stock.trade_date  # 引擎當前日別 = hub 的 jsonl 檔名
            row = _signal_row(trade_date)
            path = tmp_path / "signals" / f"{trade_date.replace('-', '')}.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
            assert client.get("/api/stock/signals/today").json() == {"signals": [row]}


class TestSignalsEnabledRoute:
    def test_default_all_on(self, tmp_path: Path) -> None:
        app, _ = make_app(tmp_path)
        with TestClient(app, raise_server_exceptions=False) as client:
            assert client.get("/api/stock/signals/enabled").json() == {"enabled": _ALL_ON}

    def test_put_round_trip(self, tmp_path: Path) -> None:
        app, _ = make_app(tmp_path)
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.put("/api/stock/signals/enabled", json={"enabled": {"vol_burst": False}})
            assert r.status_code == 200
            assert r.json() == {"enabled": {**_ALL_ON, "vol_burst": False}}
            # 回傳的是新狀態,GET 必須同值(部分更新不得把其他三鍵清掉)
            assert client.get("/api/stock/signals/enabled").json() == {
                "enabled": {**_ALL_ON, "vol_burst": False}
            }

    def test_persists_across_restart(self, tmp_path: Path) -> None:
        """SC-12:開關是持久化狀態,重啟 server 不得回到全開。"""
        app, _ = make_app(tmp_path)
        with TestClient(app, raise_server_exceptions=False) as client:
            client.put("/api/stock/signals/enabled", json={"enabled": {"cdp_cross": False}})
        app2, _ = make_app(tmp_path)
        with TestClient(app2, raise_server_exceptions=False) as client2:
            assert client2.get("/api/stock/signals/enabled").json() == {
                "enabled": {**_ALL_ON, "cdp_cross": False}
            }

    def test_unknown_key_400(self, tmp_path: Path) -> None:
        app, _ = make_app(tmp_path)
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.put("/api/stock/signals/enabled", json={"enabled": {"nope": True}})
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "INVALID_SIGNALS_ENABLED"
            assert client.get("/api/stock/signals/enabled").json() == {"enabled": _ALL_ON}

    def test_non_bool_value_400_not_coerced(self, tmp_path: Path) -> None:
        """值的驗證必須落在 hub(400 契約),不能讓 pydantic 把 "yes" 寬鬆轉成 True。"""
        app, _ = make_app(tmp_path)
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.put("/api/stock/signals/enabled", json={"enabled": {"vol_burst": "yes"}})
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "INVALID_SIGNALS_ENABLED"
            assert client.get("/api/stock/signals/enabled").json() == {"enabled": _ALL_ON}


class TestSignalRoutesNotReady:
    """hub 缺席(stock engine 未就緒)→ 三條全 503 NOT_READY,不是 500 也不是空回應。"""

    def test_all_three_return_503(self, tmp_path: Path) -> None:
        app, _ = make_app(tmp_path, with_stock=False)
        with TestClient(app, raise_server_exceptions=False) as client:
            responses = [
                client.get("/api/stock/signals/today"),
                client.get("/api/stock/signals/enabled"),
                client.put("/api/stock/signals/enabled", json={"enabled": {"vol_burst": False}}),
            ]
        for r in responses:
            assert r.status_code == 503
            assert r.json()["detail"]["error"] == "NOT_READY"


def _spy(engine: object) -> tuple[list[list[str]], list[dict]]:
    """記錄 `set_watchlist` 呼叫與 `_publish` 訊息(WatchlistService 的兩個副作用出口)。"""
    calls: list[list[str]] = []
    published: list[dict] = []
    orig_set = engine.set_watchlist  # type: ignore[attr-defined]
    orig_publish = engine._publish  # type: ignore[attr-defined]

    async def spy_set(codes: list[str]) -> None:
        calls.append(list(codes))
        await orig_set(codes)

    def spy_publish(msg: dict) -> None:
        published.append(msg)
        orig_publish(msg)

    engine.set_watchlist = spy_set  # type: ignore[method-assign, attr-defined]
    engine._publish = spy_publish  # type: ignore[method-assign, attr-defined]
    return calls, published


class TestWatchlistPutGoesThroughService:
    BODY = {"codes": ["2330"], "groups": [{"name": "主力", "codes": ["2330"]}]}

    def test_change_broadcasts_watchlist_changed(self, tmp_path: Path) -> None:
        """SC-11 後端半:改自選要廣播,前端才能自動 refetch(不必靠使用者重整)。"""
        app, _ = make_app(tmp_path)
        with TestClient(app, raise_server_exceptions=False) as client:
            calls, published = _spy(app.state.stock)
            r = client.put("/api/stock/watchlist", json=self.BODY)
            assert r.status_code == 200
            assert r.json() == self.BODY
            assert calls == [["2330"]]
            assert {"type": "watchlist_changed"} in published

    def test_identical_put_is_noop(self, tmp_path: Path) -> None:
        """🔴 行為改動:同內容 PUT 從「全量 UNSUB/SUB」變 no-op,回傳形狀不變。

        舊碼每次存檔都讓所有自選股斷訂一次,盤中畫面就是一排「-」。
        """
        app, _ = make_app(tmp_path)
        with TestClient(app, raise_server_exceptions=False) as client:
            calls, published = _spy(app.state.stock)
            r1 = client.put("/api/stock/watchlist", json=self.BODY)
            r2 = client.put("/api/stock/watchlist", json=self.BODY)
            assert r1.json() == r2.json() == self.BODY
            assert calls == [["2330"]], "第二次不得再跑 set_watchlist"
            assert [m for m in published if m.get("type") == "watchlist_changed"] == [
                {"type": "watchlist_changed"}
            ]

    def test_bad_code_still_400(self, tmp_path: Path) -> None:
        """改走 service 之後,WatchlistError → 400 的既有契約不得改變。"""
        app, _ = make_app(tmp_path)
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.put(
                "/api/stock/watchlist", json={"groups": [{"name": "a", "codes": ["bad code"]}]}
            )
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "BAD_CODE"
