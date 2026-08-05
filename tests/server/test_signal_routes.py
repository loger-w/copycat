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

from copycat.server import app as app_mod
from copycat.server import signal_hub as hub_mod
from copycat.server.app import create_app
from copycat.server.signal_hub import SignalHub
from copycat.signal_rules import RULE_KINDS, Rule
from tests.helpers.boot import BootedClient
from tests.helpers.fake_txo import FakeTxoSource
from tests.server.test_stock_routes import FakeStockSource

_ALL_ON = {"cdp_cross": True, "surge_crash": True, "vol_burst": True, "limit_lock": True}
_RULES_FILE = "signal_rules.json"

_RULE_PARAMS: dict[str, dict[str, float]] = {
    "cdp_cross": {"rearm_ticks": 5},
    "surge_crash": {"pct": 2.0, "window_secs": 300},
    "vol_burst": {
        "ratio": 3,
        "window_secs": 300,
        "min_elapsed_min": 15,
        "min_window_lots": 100,
        "min_day_lots": 500,
    },
    "limit_lock": {},
}


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


def _rule_body(kind: str, name: str, /, **over: object) -> dict:
    """合法 RuleBody(參數取 SignalsConfig 預設值域內的值);`over` 覆寫任一欄以造非法輸入。

    `kind` / `name` 宣告成 positional-only:`over` 要能覆寫這兩欄(非法 kind / 撞名案例),
    同名關鍵字否則會撞成 TypeError。
    """
    body: dict = {
        "name": name,
        "kind": kind,
        "enabled": True,
        "notify_discord": True,
        "cooldown_secs": 600,
        "params": dict(_RULE_PARAMS[kind]),
        "cdp_levels": ["ah", "nh"] if kind == "cdp_cross" else [],
    }
    body.update(over)
    return body


def _rules(client: BootedClient) -> list[Rule]:
    r = client.get("/api/stock/signals/rules")
    assert r.status_code == 200
    return r.json()["rules"]


class TestLifespanWiring:
    """hub 掛不上去的失效樣態是「今天都沒訊號」,沒有任何錯誤訊號 → 這條測試是唯一守門。"""

    def test_signal_hub_service_attached_when_stock_ready(self, tmp_path: Path) -> None:
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False):
            assert app.state.signal_hub is not None
            assert app.state.watchlist_service is not None
            # engine 側也要真的接上(只建 hub 不 attach = 一則訊號都不會產生)
            assert app.state.stock._signal_hub is app.state.signal_hub

    def test_discord_bot_none_without_token(self, tmp_path: Path) -> None:
        """conftest 中和 `DISCORD_BOT_TOKEN` → `create_bot` 回 None = SC-8 降級路徑。"""
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False):
            assert app.state.discord_bot is None
            assert app.state.signal_hub is not None  # bot 缺席不得連帶關掉訊號

    def test_boot_seeds_hub_watchlist(self, tmp_path: Path) -> None:
        """啟動時 hub 的 membership 要吃到持久化自選(否則開機後第一輪 tick 全被 gate 掉)。"""
        (tmp_path / "watchlist.json").write_text(
            json.dumps({"_cache_version": 3, "codes": ["2330"], "groups": []}),
            encoding="utf-8",
        )
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False):
            assert app.state.signal_hub._watch == {"2330"}

    def test_no_stock_leaves_hub_none(self, tmp_path: Path) -> None:
        app, _ = make_app(tmp_path, with_stock=False)
        with BootedClient(app, raise_server_exceptions=False):
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
        with BootedClient(app, raise_server_exceptions=False):
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
        with BootedClient(app, raise_server_exceptions=False):
            assert app.state.signal_hub is None
            assert app.state.discord_bot is None
            assert app.state.stock is not None  # 其他引擎不受波及
            assert app.state.stock._signal_hub is None

    def test_hub_start_failure_isolates_signals_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TQ-7:訊號整段套 `_boot` 隔離 —— hub 起不來只讓訊號停用,其他引擎照常。

        沒有這條的話,`_boot` 的邊界被改窄(或搬到 try 外)會讓整個 server 起不來,
        而現有測試全部是「一切正常」的路徑,抓不到。
        """

        async def _boom(self: SignalHub) -> None:
            raise RuntimeError("hub start 炸了")

        monkeypatch.setattr(SignalHub, "start", _boom)
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            assert app.state.signal_hub is None
            assert app.state.discord_bot is None  # bot state 不得殘留
            assert app.state.stock is not None  # 其他引擎不受波及
            assert app.state.stock._signal_hub is None
            assert client.get("/api/stock/watchlist").status_code == 200

            for r in (
                client.get("/api/stock/signals/today"),
                client.get("/api/stock/signals/enabled"),
                client.put("/api/stock/signals/enabled", json={"enabled": {"vol_burst": False}}),
            ):
                assert r.status_code == 503
                assert r.json()["detail"]["error"] == "NOT_READY"

    def test_shutdown_detaches_hub_from_engine(self, tmp_path: Path) -> None:
        """CC-2 後半:收攤後掛點要摘掉,關機序列後半不得再打到已收的 hub。"""
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False):
            assert app.state.stock._signal_hub is app.state.signal_hub
        assert app.state.stock._signal_hub is None


class TestSignalsTodayRoute:
    def test_empty_when_no_jsonl(self, tmp_path: Path) -> None:
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            assert client.get("/api/stock/signals/today").json() == {"signals": []}

    def test_returns_jsonl_rows(self, tmp_path: Path) -> None:
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            trade_date = app.state.stock.trade_date  # 引擎當前日別 = hub 的 jsonl 檔名
            row = _signal_row(trade_date)
            path = tmp_path / "signals" / f"{trade_date.replace('-', '')}.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
            assert client.get("/api/stock/signals/today").json() == {"signals": [row]}


class TestSignalsEnabledRoute:
    def test_default_all_on(self, tmp_path: Path) -> None:
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            assert client.get("/api/stock/signals/enabled").json() == {"enabled": _ALL_ON}

    def test_put_round_trip(self, tmp_path: Path) -> None:
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
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
        with BootedClient(app, raise_server_exceptions=False) as client:
            client.put("/api/stock/signals/enabled", json={"enabled": {"cdp_cross": False}})
        app2, _ = make_app(tmp_path)
        with BootedClient(app2, raise_server_exceptions=False) as client2:
            assert client2.get("/api/stock/signals/enabled").json() == {
                "enabled": {**_ALL_ON, "cdp_cross": False}
            }

    def test_unknown_key_400(self, tmp_path: Path) -> None:
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            r = client.put("/api/stock/signals/enabled", json={"enabled": {"nope": True}})
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "INVALID_SIGNALS_ENABLED"
            assert client.get("/api/stock/signals/enabled").json() == {"enabled": _ALL_ON}

    def test_non_bool_value_400_not_coerced(self, tmp_path: Path) -> None:
        """值的驗證必須落在 hub(400 契約),不能讓 pydantic 把 "yes" 寬鬆轉成 True。"""
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            r = client.put("/api/stock/signals/enabled", json={"enabled": {"vol_burst": "yes"}})
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "INVALID_SIGNALS_ENABLED"
            assert client.get("/api/stock/signals/enabled").json() == {"enabled": _ALL_ON}


class TestSignalRulesRoutes:
    """SC-4/6:規則 CRUD 是訊號設定的唯一入口 —— 這層壞掉 = 只能手改檔案 + 重啟 server。

    hub 自身的 CRUD 語意在 `test_signal_hub.py`;這裡只釘 **app 層**:狀態碼、
    `detail.error` 契約、PUT 的 path id 語意,以及「改完不必重啟」(熱重載)。
    """

    def test_get_returns_migrated_defaults(self, tmp_path: Path) -> None:
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            rules = _rules(client)
            assert [r["kind"] for r in rules] == list(RULE_KINDS)
            assert rules == app.state.signal_hub.rules()

    def test_post_creates_201_and_hot_reloads(self, tmp_path: Path) -> None:
        """201 + 新規則立刻出現在 hub —— 熱重載沒接上的話畫面有、盤中行為沒變。"""
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            body = _rule_body("cdp_cross", "我的 CDP", id="客戶端亂填的")
            r = client.post("/api/stock/signals/rules", json=body)

            assert r.status_code == 201
            created = r.json()
            assert created["id"] not in ("", "客戶端亂填的")  # id 由 hub 配,不是客戶端說了算
            assert created["name"] == "我的 CDP"
            assert created["cdp_levels"] == ["ah", "nh"]
            assert [r["id"] for r in app.state.signal_hub.rules()][-1] == created["id"]
            assert _rules(client)[-1] == created

    def test_put_edits_in_place_and_hot_reloads(self, tmp_path: Path) -> None:
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            before = _rules(client)
            rid = before[0]["id"]

            r = client.put(
                f"/api/stock/signals/rules/{rid}",
                json=_rule_body("cdp_cross", "改過的 CDP", enabled=False, cdp_levels=["ah"]),
            )

            assert r.status_code == 200
            assert r.json()["id"] == rid  # path id 為準
            live = {x["id"]: x for x in app.state.signal_hub.rules()}
            assert live[rid]["name"] == "改過的 CDP"
            assert live[rid]["enabled"] is False
            assert live[rid]["cdp_levels"] == ["ah"]
            assert list(live) == [x["id"] for x in before], "編輯不得改變規則順序"

    def test_delete_204_and_removed(self, tmp_path: Path) -> None:
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            rid = _rules(client)[0]["id"]

            r = client.delete(f"/api/stock/signals/rules/{rid}")

            assert r.status_code == 204
            assert r.content == b""
            live = [x["id"] for x in app.state.signal_hub.rules()]
            assert rid not in live
            assert [x["id"] for x in _rules(client)] == live

    def test_put_body_id_mismatch_400(self, tmp_path: Path) -> None:
        """R6:body 帶的 id 與 path 不一致 → 400,不得靜默改到 path 那條。"""
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            before = _rules(client)
            rid, other = before[0]["id"], before[1]["id"]

            r = client.put(
                f"/api/stock/signals/rules/{rid}",
                json=_rule_body("cdp_cross", "改名了", id=other),
            )

            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "INVALID_RULE"
            assert _rules(client) == before

    @pytest.mark.parametrize(
        "over",
        [
            pytest.param({"name": "   "}, id="空白名稱"),
            pytest.param({"name": "CDP 穿越"}, id="撞既有規則名"),
            pytest.param({"kind": "nope"}, id="不認得的 kind"),
            pytest.param({"cooldown_secs": 10}, id="cooldown 低於下限"),
            pytest.param({"enabled": "yes"}, id="非 bool 的 enabled 不得被寬鬆轉型"),
            pytest.param({"params": {}}, id="params 缺鍵"),
            pytest.param({"params": {"pct": 2.0, "window_secs": 300, "x": 1}}, id="params 多鍵"),
            pytest.param({"params": {"pct": 999.0, "window_secs": 300}}, id="params 違域"),
            pytest.param({"cdp_levels": ["zz"]}, id="非 cdp 規則帶線"),
        ],
    )
    def test_invalid_body_400(self, tmp_path: Path, over: dict) -> None:
        """非法輸入一律 400 INVALID_RULE(不是 422,前端只解 detail.error)。"""
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            before = _rules(client)

            r = client.post("/api/stock/signals/rules", json=_rule_body("surge_crash", "新", **over))

            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "INVALID_RULE"
            assert _rules(client) == before, "被拒的請求不得留下半套狀態"

    def test_unknown_id_404(self, tmp_path: Path) -> None:
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            put = client.put(
                "/api/stock/signals/rules/r-nope", json=_rule_body("limit_lock", "X", id="r-nope")
            )
            delete = client.delete("/api/stock/signals/rules/r-nope")

            for r in (put, delete):
                assert r.status_code == 404
                assert r.json()["detail"]["error"] == "RULE_NOT_FOUND"

    def test_save_failure_500(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """R21:落檔失敗要當面回 500,不得回 200 讓畫面顯示一條重啟後就消失的規則。"""
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            before = _rules(client)

            def _boom(path: Path, rules: list) -> None:
                raise OSError("磁碟滿了")

            monkeypatch.setattr(hub_mod, "save_rules", _boom)
            responses = [
                client.post("/api/stock/signals/rules", json=_rule_body("limit_lock", "新")),
                client.put(
                    f"/api/stock/signals/rules/{before[0]['id']}",
                    json=_rule_body("cdp_cross", "改名"),
                ),
                client.delete(f"/api/stock/signals/rules/{before[0]['id']}"),
            ]

            for r in responses:
                assert r.status_code == 500
                assert r.json()["detail"]["error"] == "RULE_SAVE_FAILED"
            monkeypatch.undo()
            assert _rules(client) == before

    def test_bad_rules_file_degrades(self, tmp_path: Path) -> None:
        """邊界 5 / R9:壞規則檔 = hub 整個不啟動(靜默套預設會在盤中改變推播行為)。

        失效樣態不是 500 也不是空清單,而是四條 rules route 全 503 NOT_READY;
        其他引擎照常。
        """
        (tmp_path / _RULES_FILE).write_text("{壞掉的 json", encoding="utf-8")
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            assert app.state.signal_hub is None
            assert app.state.stock is not None  # 訊號層單獨降級,不波及個股引擎

            responses = [
                client.get("/api/stock/signals/rules"),
                client.post("/api/stock/signals/rules", json=_rule_body("limit_lock", "新")),
                client.put("/api/stock/signals/rules/r-1-000", json=_rule_body("limit_lock", "新")),
                client.delete("/api/stock/signals/rules/r-1-000"),
            ]

        for r in responses:
            assert r.status_code == 503
            assert r.json()["detail"]["error"] == "NOT_READY"


class TestSignalRoutesNotReady:
    """hub 缺席(stock engine 未就緒)→ 三條全 503 NOT_READY,不是 500 也不是空回應。"""

    def test_all_three_return_503(self, tmp_path: Path) -> None:
        app, _ = make_app(tmp_path, with_stock=False)
        with BootedClient(app, raise_server_exceptions=False) as client:
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
        with BootedClient(app, raise_server_exceptions=False) as client:
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
        with BootedClient(app, raise_server_exceptions=False) as client:
            calls, published = _spy(app.state.stock)
            r1 = client.put("/api/stock/watchlist", json=self.BODY)
            r2 = client.put("/api/stock/watchlist", json=self.BODY)
            assert r1.json() == r2.json() == self.BODY
            assert calls == [["2330"]], "第二次不得再跑 set_watchlist"
            assert [m for m in published if m.get("type") == "watchlist_changed"] == [
                {"type": "watchlist_changed"}
            ]

    def test_broken_watchlist_file_still_accepts_put(self, tmp_path: Path) -> None:
        """MFS-3:自選檔壞掉(半寫入 / 手改壞)時,存一份合法名單必須是 200 + 檔被修正。"""
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            (tmp_path / "watchlist.json").write_text("{壞掉的 json", encoding="utf-8")

            r = client.put("/api/stock/watchlist", json=self.BODY)

            assert r.status_code == 200
            assert r.json() == self.BODY
            saved = json.loads((tmp_path / "watchlist.json").read_text(encoding="utf-8"))
            assert saved["codes"] == ["2330"]

    def test_bad_code_still_400(self, tmp_path: Path) -> None:
        """改走 service 之後,WatchlistError → 400 的既有契約不得改變。"""
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            r = client.put(
                "/api/stock/watchlist", json={"groups": [{"name": "a", "codes": ["bad code"]}]}
            )
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "BAD_CODE"
