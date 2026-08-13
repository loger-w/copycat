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

import functools
import json
import threading
import time
from datetime import date as _date
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient

from copycat.server import app as app_mod
from copycat.server import signal_hub as hub_mod
from copycat.server.app import create_app
from copycat.server.signal_hub import SignalHub
from copycat.signal_rules import RULE_KINDS, Rule
from tests.helpers.boot import BootedClient, wait_boot
from tests.helpers.fake_sources import FakeIndexSource
from tests.helpers.fake_txo import FakeTxoSource
from tests.server.test_stock_routes import FakeStockSource

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


def _market_event(code: str = "1101", *, at: str = "10:01:00") -> dict:
    """breadth `_diff_limit_events` 產出的事件形狀(`publish_market_events` 的入參)。"""
    return {
        "code": code,
        "kind": "market_limit_lock",
        "direction": "up",
        "time": at,
        "name": "台泥",
        "price": 30_000,
        "touch_count": 1,
    }


def _market_event_id(trade_date: str, event: dict) -> str:
    """`publish_market_events` 的決定性 id(規則段固定 `breadth`)。"""
    return (
        f"{trade_date}-breadth-{event['code']}-{event['kind']}-{event['direction']}-{event['time']}"
    )


def _publish_market(
    client: BootedClient, hub: SignalHub, events: list[dict], trade_date: str
) -> None:
    """hub 的呼叫**必須回到 event loop**:`WsBroadcaster.publish` 契約是「只能在 loop 上
    呼叫」,jsonl 也是走 asyncio.Queue 交給 worker。測試執行緒直呼會把訊息放進另一條
    執行緒看不到的佇列(而斷言只會逾時,看不出是接線錯還是時序問題)。

    `portal.call` 只吃位置參數(anyio `call(func, *args)`)而 `trade_date` 是
    keyword-only → 走 `functools.partial`;不得因 TypeError 改用跨執行緒直呼繞過。
    """
    portal = client.portal
    assert portal is not None, "portal 只在 TestClient context 內存在(lifespan 未進場?)"
    portal.call(functools.partial(hub.publish_market_events, events, trade_date=trade_date))


def _pump_receive(ws: Any, timeout: float) -> tuple[list[dict], list[BaseException]]:
    """在 daemon 執行緒上跑一次 `receive_json`,`join(timeout)` 封頂(T-5)。

    `WebSocketTestSession.receive` 是無上限的 `portal.call(...receive)` —— 接線回歸
    (訊號不再上這條 WS)的表現會是**整個 pytest 掛死**,CI 只看得到逾時被砍,而不是
    一條指名道姓的紅測試。例外收進回傳值而不是就地拋:close 分支要拿它做斷言,
    逾時分支要拿它寫進訊息(兩條路都有人讀,不是吞掉)。
    """
    box: list[dict] = []
    err: list[BaseException] = []

    def _pump() -> None:
        try:
            box.append(ws.receive_json())
        except BaseException as exc:  # noqa: BLE001 - 進 err,由呼叫端判讀
            err.append(exc)

    worker = threading.Thread(target=_pump, daemon=True)
    worker.start()
    worker.join(timeout)
    return box, err


def _recv_json(ws: Any, timeout: float = 5.0) -> dict:
    """有上限的 `receive_json`;沒收到就 AssertionError(不掛死)。"""
    box, err = _pump_receive(ws, timeout)
    if not box:
        raise AssertionError(f"WS 未在 {timeout}s 內收到訊息(例外:{err})")
    return box[0]


def _expect_close(ws: Any, timeout: float = 5.0) -> None:
    """有上限地斷言「accept 後隨即被 close」。

    close 不會在 `websocket_connect` 那一步拋 —— route 先 `accept()` 才 `close()`,
    TestClient 的 enter 只讀到 accept(既有 `/ws/breadth` 測試同款)。
    """
    box, err = _pump_receive(ws, timeout)
    assert not box, f"連線沒被 close,反而收到訊息:{box}"
    assert err and isinstance(err[0], WebSocketDisconnect), f"{timeout}s 內沒收到 close:{err}"


def _recv_until(ws: Any, kind: str, timeout: float = 5.0) -> dict:
    """收到指定 `type` 為止(同一顆 broadcaster 上可能夾雜 status / 節流 quote)。"""
    deadline = time.monotonic() + timeout
    seen: list[str] = []
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(f"{timeout}s 內未收到 type={kind} 的訊息(收到:{seen})")
        msg = _recv_json(ws, timeout=remaining)
        if msg.get("type") == kind:
            return msg
        seen.append(str(msg.get("type")))


def _wait_signal(client: BootedClient, signal_id: str, timeout: float = 5.0) -> dict:
    """輪詢 today 直到該 id 出現(jsonl 落檔由 worker 非同步完成,不可一次性立即斷言)。"""
    deadline = time.monotonic() + timeout
    while True:
        r = client.get("/api/stock/signals/today")
        assert r.status_code == 200
        rows = r.json()["signals"]
        for row in rows:
            if row.get("id") == signal_id:
                return row
        if time.monotonic() > deadline:
            raise AssertionError(f"{signal_id} 未在 {timeout}s 內出現在 today:{rows}")
        time.sleep(0.01)


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

    def test_no_stock_still_builds_hub(self, tmp_path: Path) -> None:
        """SC-1(🔴 XR-3):TC4 不在 → hub 照建照啟,落點仍是 `wl_path.parent`。

        舊行為是「stock 缺席 → hub None」,而 hub 是廣度事件鏈的唯一出口 ——
        達錢 4 沒開的早上,全市場鎖板事件整天不產生而畫面與「今天沒有漲停」同形。
        `watchlist_service` 仍 None(它真的依賴 engine 的訂閱池,不在解耦範圍)。
        """
        app, _ = make_app(tmp_path, with_stock=False)
        with BootedClient(app, raise_server_exceptions=False):
            assert app.state.signal_hub is not None
            assert app.state.watchlist_service is None
            assert (tmp_path / _RULES_FILE).exists(), "規則檔要落在注入的 data 根"


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
                client.get("/api/stock/signals/rules"),
                client.post("/api/stock/signals/rules", json=_rule_body("limit_lock", "新")),
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


class TestSignalsTodayMarketParam:
    """`?market=exclude` 後端過濾(R4 design §7 / R2-7)。

    SignalRail 那個消費端只要自選訊號,而全市場鎖板事件在漲停潮日可以是數百則 ——
    整包下載後 client 丟棄會讓 cap 200 在過濾**之前**發生,自選訊號被擠光。
    """

    def _seed(self, app: FastAPI, tmp_path: Path) -> tuple[dict, dict]:
        trade_date = app.state.stock.trade_date
        own = _signal_row(trade_date)
        market = {
            **_signal_row(trade_date),
            "id": f"{trade_date}-breadth-1101-market_limit_lock-up-10:01:00",
            "kind": "market_limit_lock",
            "code": "1101",
            "name": "台泥",
            "direction": "up",
            "levels": [],
        }
        path = tmp_path / "signals" / f"{trade_date.replace('-', '')}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in (own, market)),
            encoding="utf-8",
        )
        return own, market

    def test_default_includes_market_rows(self, tmp_path: Path) -> None:
        """預設(不帶參數)= include —— 既有呼叫端零改動,行為逐字不變。"""
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            own, market = self._seed(app, tmp_path)
            body = client.get("/api/stock/signals/today").json()
        assert body == {"signals": [own, market]}

    def test_explicit_include_matches_default(self, tmp_path: Path) -> None:
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            own, market = self._seed(app, tmp_path)
            body = client.get("/api/stock/signals/today", params={"market": "include"}).json()
        assert body == {"signals": [own, market]}

    def test_exclude_drops_market_kinds(self, tmp_path: Path) -> None:
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            own, _market = self._seed(app, tmp_path)
            body = client.get("/api/stock/signals/today", params={"market": "exclude"}).json()
        assert body == {"signals": [own]}

    def test_unknown_value_falls_back_to_include(self, tmp_path: Path) -> None:
        """未知值 = include(T-5):這個參數是效能取捨,不是安全閘。

        擋成 400 的話,舊 client(或打錯字的手測)只會白掉一整條自癒 baseline ——
        而 baseline 空掉的表現是「重連後訊號欄突然少了一段」,沒有錯誤訊號。
        """
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            own, market = self._seed(app, tmp_path)
            r = client.get("/api/stock/signals/today", params={"market": "whatever"})
        assert r.status_code == 200
        assert r.json() == {"signals": [own, market]}

    def test_bad_kind_rows_survive_exclude(self, tmp_path: Path) -> None:
        """`kind` 不是字串 / 整個缺鍵的列:過濾要**留著**它們且不得 500(T-5)。

        jsonl 是檔案,`kind` 的型別無人保證(壞行只擋到 JSON 層)。`str.startswith`
        對 int 會 AttributeError → 整條端點 502,而肇因只是一列髒資料;而「留著」是
        因為它已經不是可辨識的廣度事件 —— 這條路徑的預設是 include。
        """
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            trade_date = app.state.stock.trade_date
            numeric = {**_signal_row(trade_date), "id": "bad-1", "kind": 123}
            missing = {k: v for k, v in _signal_row(trade_date).items() if k != "kind"}
            missing["id"] = "bad-2"
            path = tmp_path / "signals" / f"{trade_date.replace('-', '')}.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in (numeric, missing)),
                encoding="utf-8",
            )
            r = client.get("/api/stock/signals/today", params={"market": "exclude"})
        assert r.status_code == 200
        assert [row["id"] for row in r.json()["signals"]] == ["bad-1", "bad-2"]


class TestLegacyEnabledRouteGone:
    """SC-4:四鍵開關家族退役 —— 規則自帶 `enabled`,兩套開關並存會互相蓋掉。

    hub **就緒**下仍是 404(不是 503):503 代表「暫時不可用、待會再試」,前端會
    留著舊 UI 等它回來;退役的東西要回 404 才說得清楚「這條路沒了」。
    """

    def test_legacy_enabled_route_gone(self, tmp_path: Path) -> None:
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            assert app.state.signal_hub is not None  # hub 就緒 → 404 不是降級造成的

            responses = [
                client.get("/api/stock/signals/enabled"),
                client.put("/api/stock/signals/enabled", json={"enabled": {"vol_burst": False}}),
            ]

        assert [r.status_code for r in responses] == [404, 404]


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
            # 合法的線名(review B9):填 "zz" 時 `_normalize_levels` 在「不是五線之一」
            # 就先拒了,鎖不到「非 cdp 規則必須空 levels」這條規則本身
            pytest.param({"cdp_levels": ["ah"]}, id="非 cdp 規則帶線"),
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

    @pytest.mark.parametrize("missing", ["name", "kind", "cooldown_secs", "params", "cdp_levels"])
    def test_missing_field_400(self, tmp_path: Path, missing: str) -> None:
        """缺欄同樣走 400 INVALID_RULE(review B8)。

        `RuleBody` 每個欄位都給 None 預設就是為了這條:宣告成必填時 pydantic 會回
        422 + list 形 detail,前端只解 `detail.error` → 畫面上是「儲存失敗」而不是
        「規則設定不合法」,而且完全看不出是缺了哪一種輸入。
        """
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            before = _rules(client)
            body = _rule_body("surge_crash", "新")
            del body[missing]

            r = client.post("/api/stock/signals/rules", json=body)

            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "INVALID_RULE"
            assert _rules(client) == before

    def test_non_string_id_in_body_400(self, tmp_path: Path) -> None:
        """body 的 id 型別不符也要 400(review A6(1)):`RuleBody.id` 宣告成 `str | None`
        時,`{"id": 123}` 會在 pydantic 那層變成 422 + list 形 detail。"""
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            rule_id = _rules(client)[0]["id"]

            r = client.put(
                f"/api/stock/signals/rules/{rule_id}",
                json=_rule_body("limit_lock", "X", id=123),
            )

            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "INVALID_RULE"

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


class TestSignalRoutesWithoutStock:
    """🔴 XR-3:TC4 沒開時訊號面**全可用**(舊行為是全 503)。

    503 從此只剩一種語意:hub 自身降級(壞規則檔 / start 炸)—— 那兩條由
    `test_bad_rules_file_degrades` / `test_hub_start_failure_isolates_signals_only` 守。

    這一組守的是:規則 CRUD 是純檔案操作、廣度事件鏈是純 FinMind,兩者與達錢 4
    一點關係都沒有,卻曾因為 hub 綁 stock engine 而一起消失。
    """

    def test_rule_crud_available_without_stock(self, tmp_path: Path) -> None:
        """SC-3:GET 200(預設規則)/ POST 201 / PUT 200 / DELETE 204,today 200。"""
        app, _ = make_app(tmp_path, with_stock=False)
        with BootedClient(app, raise_server_exceptions=False) as client:
            assert [r["kind"] for r in _rules(client)] == list(RULE_KINDS)

            created = client.post("/api/stock/signals/rules", json=_rule_body("limit_lock", "新"))
            assert created.status_code == 201
            rid = created.json()["id"]

            put = client.put(
                f"/api/stock/signals/rules/{rid}", json=_rule_body("limit_lock", "改名了")
            )
            assert put.status_code == 200
            assert put.json()["name"] == "改名了"

            assert client.delete(f"/api/stock/signals/rules/{rid}").status_code == 204
            assert rid not in [r["id"] for r in _rules(client)]

            today = client.get("/api/stock/signals/today")
            assert today.status_code == 200
            assert today.json() == {"signals": []}

    def test_market_events_reach_today_on_wall_clock_date(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SC-2:廣度事件鏈(REST)照活,`trade_date` 走牆鐘 fallback。

        `TXO_BACKFILL_DATE` 顯式清掉:它是 fallback 的優先來源(edge §7.1),
        開發機 shell 留著它會讓這條斷言隨環境飄。
        """
        monkeypatch.delenv("TXO_BACKFILL_DATE", raising=False)
        app, _ = make_app(tmp_path, with_stock=False)
        with BootedClient(app, raise_server_exceptions=False) as client:
            assert client.get("/api/stock/signals/today").json() == {"signals": []}
            hub = app.state.signal_hub
            assert hub is not None
            today = f"{_date.today():%Y-%m-%d}"
            assert hub._trade_date_fn() == today, "無 engine 時日別來源 = 牆鐘"

            event = _market_event()
            _publish_market(client, hub, [event], today)
            row = _wait_signal(client, _market_event_id(today, event))

        assert row["kind"] == "market_limit_lock"
        assert row["code"] == "1101"
        assert row["trade_date"] == today

    def test_ws_stock_stays_open_and_carries_market_events(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SC-4:`/ws/stock` 不再立即 close;首則是 tc4=down 的 status seed(review P1-2)。

        沒有那則 seed 的話,前端「連線異常」提示靠 `status.tc4 === "down" ||
        wsStatus === "closed"` 觸發,而 `status` 初值是 `{tc4: "up"}` —— 掛著的空流
        會讓 TC4-off 完全無提示(比舊的立即 close 更糟)。
        """
        monkeypatch.delenv("TXO_BACKFILL_DATE", raising=False)
        app, _ = make_app(tmp_path, with_stock=False)
        with BootedClient(app, raise_server_exceptions=False) as client:
            hub = app.state.signal_hub
            assert hub is not None
            today = f"{_date.today():%Y-%m-%d}"
            with client.websocket_connect("/ws/stock") as ws:
                assert _recv_json(ws) == {
                    "type": "status",
                    "tc4": "down",
                    "backfilling": None,
                }

                event = _market_event()
                _publish_market(client, hub, [event], today)
                msg = _recv_json(ws)

        assert msg["type"] == "signal"
        assert msg["kind"] == "market_limit_lock"
        assert msg["id"] == _market_event_id(today, event)

    def test_basis_falls_back_to_empty_daily_bars(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """T5:無 engine → `daily_bars` stub 恆回 `[]` = 「資料面就是沒有」。

        hub 既有路徑因此逐檔一次「CDP 停用」warning + cache 落 `(日別, None)`,
        **不重試**(重試留給例外路徑 X-2b)—— 自選 50 檔不會變成重試風暴。
        """
        monkeypatch.delenv("TXO_BACKFILL_DATE", raising=False)
        (tmp_path / "watchlist.json").write_text(
            json.dumps({"_cache_version": 3, "codes": ["2330"], "groups": []}),
            encoding="utf-8",
        )
        app, _ = make_app(tmp_path, with_stock=False)
        with BootedClient(app, raise_server_exceptions=False):
            hub = app.state.signal_hub
            assert hub is not None
            assert hub._watch == {"2330"}, "membership 種子不得因為 engine 缺席而漏掉"
            today = f"{_date.today():%Y-%m-%d}"
            deadline = time.monotonic() + 5.0
            while "2330" not in hub._basis_cache:
                if time.monotonic() > deadline:
                    raise AssertionError(f"basis 未在 5s 內落定:{hub._basis_cache}")
                time.sleep(0.01)
            assert hub._basis_cache["2330"] == (today, None)
            assert hub._basis_retries == {}, "資料面回空不得排重試"

    def test_trade_date_is_evaluated_per_call(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """T-2:牆鐘 fallback 必須**每次呼叫求值**,且 `TXO_BACKFILL_DATE` 優先。

        「= 今天」那條斷言對 boot 時算一次的靜態字串同樣成立 → 鑑別點只能落在
        **boot 之後**才改 env:靜態實作會固定在 boot 當下的值。失效樣態是長跑跨日後
        `_distribute` 的日別尺與 jsonl 檔名都停在昨天 —— 今天的事件寫進昨天的檔,
        today 端點空白,完全靜默。
        """
        monkeypatch.delenv("TXO_BACKFILL_DATE", raising=False)
        app, _ = make_app(tmp_path, with_stock=False)
        with BootedClient(app, raise_server_exceptions=False):
            hub = app.state.signal_hub
            assert hub is not None

            monkeypatch.setenv("TXO_BACKFILL_DATE", "2026-01-02")
            assert hub._trade_date_fn() == "2026-01-02", "boot 後改 env 要立刻反映(非靜態快照)"

            monkeypatch.delenv("TXO_BACKFILL_DATE")
            assert hub._trade_date_fn() == f"{_date.today():%Y-%m-%d}", "env 撤掉要回牆鐘"

    def test_bot_built_with_none_service(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """T6:bot 照建(service=None → `/watch` 回 fallback 文案),不隨 stock 一起消失。"""
        seen: list[tuple[object, object]] = []

        def _spy(service: object, hub: object) -> None:
            seen.append((service, hub))
            return None

        monkeypatch.setattr(app_mod, "create_bot", _spy)
        app, _ = make_app(tmp_path, with_stock=False)
        with BootedClient(app, raise_server_exceptions=False):
            assert seen == [(None, app.state.signal_hub)]


class TestWsStockSharedBroadcaster:
    """T-1:engine **在場**時 hub 與 `/ws/stock` 必須共用同一顆 broadcaster。

    `_make_stock` 漏傳 `ws=stock_ws` 的話 engine 會自建一顆,而 hub 照樣 publish 到
    app 層那顆 —— 整套測試仍然全綠(hub 建得起來;TC4-off 那組走的正好就是 app 層
    那顆),壞掉的偏偏是 prod 主用例:達錢 4 開著時訊號全部不上 WS,畫面只是
    「今天都沒跳訊號」,零錯誤訊號。
    """

    def test_hub_signal_reaches_ws_when_engine_present(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """行為版:同一條連線先收 engine 的自選 seed,再收 hub 發的訊號。

        先斷言 seed 是關鍵鑑別:它證明這條連線走的是 **engine 的 stream**(無 engine
        分支的首則是 status),所以之後收到訊號只可能出自「兩者同一顆」。
        """
        monkeypatch.delenv("TXO_BACKFILL_DATE", raising=False)
        (tmp_path / "watchlist.json").write_text(
            json.dumps({"_cache_version": 3, "codes": ["2330"], "groups": []}),
            encoding="utf-8",
        )
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            hub = app.state.signal_hub
            assert hub is not None
            trade_date = app.state.stock.trade_date
            with client.websocket_connect("/ws/stock") as ws:
                assert _recv_json(ws)["type"] == "watchlist_quote", "engine 在場 → 首則是自選 seed"

                event = _market_event()
                _publish_market(client, hub, [event], trade_date)
                msg = _recv_until(ws, "signal")

        assert msg["kind"] == "market_limit_lock"
        assert msg["id"] == _market_event_id(trade_date, event)

    def test_engine_ws_is_the_app_level_broadcaster(self, tmp_path: Path) -> None:
        """最小版:上一條紅掉時直接指出壞在哪一根線(注入 vs. hub 那端)。"""
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False):
            assert app.state.stock._ws is app.state.stock_ws


class _BlockingIndexSource(FakeIndexSource):
    """`subscribe_symbol` 卡在 gate 上 —— boot 序列停在 **signals 之後、boot_done 之前**。

    `_subscribe_and_backfill` 走 `to_thread`,所以卡的是背景 boot task 而不是測試執行緒。
    """

    def __init__(self) -> None:
        super().__init__()
        self.gate = threading.Event()
        self.entered = threading.Event()

    def subscribe_symbol(self, code: str) -> None:
        self.entered.set()
        self.gate.wait(15.0)  # 測試一律自己放行;上限只是「忘了放行」時不掛死整套測試
        super().subscribe_symbol(code)


class TestWsStockCloseBranches:
    """T-3/W-4:`/ws/stock` 仍會 close 的兩條分支(XR-3 只放寬了第三種情形)。

    這兩條沒鎖的話,`not state.boot_done or state.signal_hub is None` 被改窄成只剩
    前半、後半、或整段拿掉都不會紅 —— 留下的是永遠無流量的殭屍連線,而前端的
    「連線異常」提示正是靠 `wsStatus === "closed"`。
    """

    def test_closes_when_hub_also_none(self, tmp_path: Path) -> None:
        """(a) stock 缺席 **且** hub 降級(壞規則檔)→ 這條通道沒有任何生產者。"""
        (tmp_path / _RULES_FILE).write_text("{壞掉的 json", encoding="utf-8")
        app, _ = make_app(tmp_path, with_stock=False)
        with BootedClient(app, raise_server_exceptions=False) as client:
            assert app.state.signal_hub is None, "壞規則檔 → hub 降級(這條測試的前提)"
            with client.websocket_connect("/ws/stock") as ws:
                _expect_close(ws)

    def test_closes_inside_boot_window(self, tmp_path: Path) -> None:
        """(b) boot 未完成 → close(早連的 client 錯過 seed,重連自癒比空流好)。

        不能用 `BootedClient`:它的語意就是「等到窗關上」,窗內路徑一次都不會執行。
        窗**必須卡在 signals 之後**:更早卡住(runtime 的 `list_series`)時 hub 也還
        是 None,close 由 `signal_hub is None` 那半邊接住 —— 拿掉 `boot_done` 照樣綠
        (實測過的假紅測試)。
        """
        index = _BlockingIndexSource()
        app = create_app(
            FakeTxoSource(),
            index_source=index,
            stock_watchlist_path=tmp_path / "watchlist.json",
            throttle_secs=0.01,
        )
        with TestClient(app, raise_server_exceptions=False) as client:
            assert index.entered.wait(5), "boot 沒卡在 index 訂閱 → 窗沒開在鑑別點上"
            assert app.state.signal_hub is not None, "窗要落在 signals 之後,否則驗不到 boot_done"
            assert app.state.boot_done is False

            with client.websocket_connect("/ws/stock") as ws:
                _expect_close(ws)

            index.gate.set()
            wait_boot(app)
            # 翻轉對照:窗外同一條連線活著 → 上面那個 close 確實只出自「窗內」,
            # 而不是這個 app 的 `/ws/stock` 根本連不上
            with client.websocket_connect("/ws/stock") as ws:
                assert _recv_json(ws)["type"] == "status"


class TestConftestWatchlistIsolation:
    """T-4:`tests/server/conftest.py` 的落點隔離 fixture 自身要有鎖。

    它是 SC-8 唯一的擋牆(hub 恆建之後,沒傳 `stock_watchlist_path` 的 19 個站點全會
    把 `signal_rules.json` / fake 鎖板事件寫進 repo 真 `data/`),而 fixture 壞掉是
    **靜默**的:所有測試照樣綠,只有 prod 的對帳 seed 被汙染。
    """

    def test_hub_data_dir_isolated_without_explicit_path(self, tmp_path: Path) -> None:
        app = create_app(
            FakeTxoSource(),
            stock_source=FakeStockSource(),
            throttle_secs=0.01,
        )  # 刻意不傳 stock_watchlist_path → 落點由 conftest 的 autouse fixture 決定
        with BootedClient(app, raise_server_exceptions=False):
            hub = app.state.signal_hub
            assert hub is not None
            assert hub._data_dir == tmp_path, "落點必須在 tmp_path,不得是 repo 的 data/"


def _spy(engine: object) -> tuple[list[list[str]], list[dict]]:
    """記錄 `set_watchlist` 呼叫與 `_publish` 訊息(WatchlistService 的兩個副作用出口)。"""
    calls: list[list[str]] = []
    published: list[dict] = []
    orig_set = engine.set_watchlist  # type: ignore[attr-defined]
    orig_publish = engine._publish  # type: ignore[attr-defined]

    async def spy_set(codes: list[str], *, seq: int | None = None) -> None:
        calls.append(list(codes))
        await orig_set(codes, seq=seq)

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
