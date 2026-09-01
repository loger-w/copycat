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

import asyncio
import datetime as _dt
import json
import threading
import time
from datetime import date as _date
from pathlib import Path
from typing import Any, Callable

import pytest
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient

import copycat.notify as notify_mod
from copycat.live import signal_state
from copycat.live.stock_models import StockBook, StockMeta, StockTick
from copycat.live.stock_state import StockDayState
from copycat.server import app as app_mod
from copycat.server import signal_hub as hub_mod
from copycat.server import ws as ws_mod
from copycat.server.app import create_app
from copycat.server.signal_hub import SignalHub
from copycat.signal_rules import Rule
from tests.helpers.boot import BootedClient, wait_boot
from tests.helpers.fake_sources import FakeIndexSource
from tests.helpers.fake_txo import FakeTxoSource
from tests.server.test_stock_routes import FakeStockSource

_RULES_FILE = "signal_rules.json"

#: 缺檔遷移的種子 kind 序:surge_pullback 兩張卡(1% / 2%,spec #174)
_SEEDED_KINDS = [
    "cdp_cross",
    "surge_crash",
    "surge_pullback",
    "surge_pullback",
    "vol_burst",
    "limit_lock",
]

_RULE_PARAMS: dict[str, dict[str, float]] = {
    "cdp_cross": {"rearm_ticks": 5, "rearm_dwell_secs": 300},
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


#: `test_signal_hub.py` 同名 helper 的**自帶副本**(tests/ 無 `__init__.py`,跨檔
#: import 那兩個私有 helper 會讓 pyright 紅)。值刻意與該檔 `_Harness.lock_up` 逐字
#: 對齊:鎖漲停的複合簽名 = 成交價 == `ctx.upper_milli` **且** ask 側無限價檔。
def _tick(
    price: int,
    *,
    code: str = "2330",
    cum: int = 1,
    trade_date: str,
) -> StockTick:
    return StockTick(
        code=code,
        price_milli=price,
        qty=1,
        cum_vol=cum,
        time="10:00:00.123",
        trade_date=trade_date,
        side="neutral",
        is_trial=False,
    )


def _state(
    *,
    name: str | None = "台積電",
    upper: int = 200_000,
    lower: int = 50_000,
    locked_up: bool = False,
) -> StockDayState:
    st = StockDayState()
    if name is not None:
        st.update_meta(
            StockMeta(
                name=name,
                ref_milli=100_000,
                upper_milli=upper,
                lower_milli=lower,
                y_close_milli=None,
                y_volume=None,
                open_time="09:00:00",
                close_time="13:30:00",
            )
        )
    if locked_up:
        # 真鎖漲停簽名:ask 側無限價檔 + bids[0] 是市價佇列的 0(CLAUDE.md §8)
        st.update_book(StockBook(bids=[(0, 800)], asks=[]))
    else:
        st.update_book(StockBook(bids=[(99_000, 5)], asks=[(101_000, 5)]))
    return st


def _emit_rule_signal(
    client: BootedClient,
    hub: SignalHub,
    monkeypatch: pytest.MonkeyPatch,
    *,
    trade_date: str,
) -> None:
    """把一則**規則訊號**(`limit_lock`)灌進 hub —— XR-3 三條測試的共用載具。

    hub 的呼叫**必須回到 event loop**:`WsBroadcaster.publish` 契約是「只能在 loop 上
    呼叫」,jsonl 也是走 asyncio.Queue 交給 worker。測試執行緒直呼會把訊息放進另一條
    執行緒看不到的佇列(而斷言只會逾時,看不出是接線錯還是時序問題)。

    三個前置缺一不可:

    1. **`code` 必須在 `hub._watch`** —— `on_tick` 首行就 gate 掉非自選(呼叫端負責
       種 watchlist 並先斷言)。
    2. **盤別閘**:`SignalDetector._in_session` 是 09:00–13:30(end-exclusive),而
       `create_app` 沒有 `now_fn` 注入點 → 只能 monkeypatch `signal_state` 的模組層
       常數。用 `time.min`/`time.max` 而不是 `23:59`:後者會在最後一分鐘偶發紅。
    3. **Discord 出口中和**:規則訊號依 `rule["notify_discord"]`(預設 True)入 Discord
       佇列,而 webhook 走 `notify` 的 `.env` fallback —— conftest 沒罩那條路(本機
       `.env` 目前無 `DISCORD_WEBHOOK_URL`,但不得依賴)。

    兩筆 tick:首筆只初始化 detector 的 `_prev`,第二筆成交在漲停價才產生事件。
    """
    monkeypatch.setattr(signal_state, "_SESSION_START", _dt.time.min)
    monkeypatch.setattr(signal_state, "_SESSION_END", _dt.time.max)
    monkeypatch.setattr(notify_mod, "_URL_RESOLVED", True)
    monkeypatch.setattr(notify_mod, "_WEBHOOK_URL", None)

    portal = client.portal
    assert portal is not None, "portal 只在 TestClient context 內存在(lifespan 未進場?)"
    state = _state(upper=110_000, locked_up=True)
    portal.call(hub.on_tick, "2330", _tick(109_000, trade_date=trade_date), state)
    portal.call(hub.on_tick, "2330", _tick(110_000, cum=2, trade_date=trade_date), state)


def _seed_watchlist(tmp_path: Path) -> None:
    """`on_tick` 載具的前置:2330 必須在自選裡,否則 hub 首行就早退。"""
    (tmp_path / "watchlist.json").write_text(
        json.dumps({"_cache_version": 3, "codes": ["2330"], "groups": []}),
        encoding="utf-8",
    )


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


def _wait_signal(
    client: BootedClient, match: Callable[[dict], bool], timeout: float = 5.0
) -> dict:
    """輪詢 today 直到符合 `match` 的列出現(jsonl 落檔由 worker 非同步完成)。

    predicate 而非 id:規則訊號的 id 含 `rule_id`(執行期生成),釘 id 等於把測試綁在
    規則檔的產生順序上 —— 那與這幾條要守的行為(訊號到得了 today / WS)無關。
    """
    deadline = time.monotonic() + timeout
    while True:
        r = client.get("/api/stock/signals/today")
        assert r.status_code == 200
        rows = r.json()["signals"]
        for row in rows:
            if match(row):
                return row
        if time.monotonic() > deadline:
            raise AssertionError(f"符合條件的訊號未在 {timeout}s 內出現在 today:{rows}")
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

        舊行為是「stock 缺席 → hub None」,而 hub 是規則 CRUD 與 today 端點的唯一
        出口 —— 達錢 4 沒開的早上這兩條路一起 503,而它們都是純檔案操作。
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
            assert client.get("/api/stock/signals/today").json()["signals"] == []

    def test_carries_trade_date_and_today(self, tmp_path: Path) -> None:
        """D3'/AR6:標題用的日期由回傳體自帶 —— 前端不看瀏覽器時鐘也不多打 /api/calendar。

        `trade_date` = hub 的引擎日別、`today` = hub 牆鐘日(與 `today_signals()` 取
        聯集的那顆時鐘同源,AR7)。缺欄的失效樣態是前端永遠印「今日訊號」:假日開站
        掛的是上一交易日的訊號,畫面上零提示 —— 所以在這裡把兩欄的來源釘死。

        **日期取 2019 年**(review TQ-4):原本用的是撰寫當日附近的日期,而
        `_now_fn` / `_trade_date_fn` 若哪天被繞過(route 改讀真牆鐘),期望值恰好等於
        真牆鐘的那幾天測試會靜默假綠。2019-03-01(五)/ 03-04(一)永遠不會等於執行
        當下的牆鐘。

        **形狀全等**(review TQ-8):`set(body)` 而不是逐鍵 in —— 多一個欄位(例如把
        內部狀態順手掛上去)在逐鍵斷言下是沉默的,而回傳體是跨檔契約。
        """
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            hub = app.state.signal_hub
            assert hub is not None
            hub._trade_date_fn = lambda: "2019-03-01"  # 引擎日別
            hub._now_fn = lambda: _dt.datetime(2019, 3, 4, 9, 30, 0)  # 牆鐘
            body = client.get("/api/stock/signals/today").json()
        assert body["trade_date"] == "2019-03-01"
        assert body["today"] == "2019-03-04"
        assert set(body) == {"signals", "trade_date", "today"}

    def test_dates_are_sampled_before_the_await(self, tmp_path: Path) -> None:
        """review C-1:兩個日期必須在 `await to_thread(today_signals)` **之前**取樣。

        取樣點在 await 之後時,jsonl 讀取那段(worker thread,可長)橫跨 rollover
        stage2 的話,回傳體會是「舊日的訊號 + 新日的日期」—— 前端拿它比對得出
        `trade_date == today` → 標題印「今日訊號」,而列的內容其實是昨天的。錯位不可
        避免(兩件事本來就不是原子的),但方向要選得對:先取樣 = 最壞情況印出舊日期,
        使用者看到的是「MM-DD 訊號」配那一天的列,兩邊一致且說得通。

        探針:`today_signals` 執行中把 hub 的兩顆時鐘推到新日別(= 讀檔期間發生
        rollover)。取樣在 await 後的實作會回新日別。
        """
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            hub = app.state.signal_hub
            assert hub is not None
            hub._trade_date_fn = lambda: "2019-03-01"
            hub._now_fn = lambda: _dt.datetime(2019, 3, 1, 13, 40, 0)

            def _rolls_over_while_reading() -> list[dict]:
                hub._trade_date_fn = lambda: "2019-03-04"
                hub._now_fn = lambda: _dt.datetime(2019, 3, 4, 9, 0, 0)
                return []

            hub.today_signals = _rolls_over_while_reading  # type: ignore[method-assign]
            body = client.get("/api/stock/signals/today").json()
            # 前提自檢:探針真的改到了 hub(沒改到的話下面兩條會假綠)
            assert hub.trade_date == "2019-03-04"
        assert body["trade_date"] == "2019-03-01"
        assert body["today"] == "2019-03-01"

    def test_returns_jsonl_rows(self, tmp_path: Path) -> None:
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            trade_date = app.state.stock.trade_date  # 引擎當前日別 = hub 的 jsonl 檔名
            row = _signal_row(trade_date)
            path = tmp_path / "signals" / f"{trade_date.replace('-', '')}.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
            assert client.get("/api/stock/signals/today").json()["signals"] == [row]

    def test_reads_jsonl_off_event_loop(self, tmp_path: Path) -> None:
        """handoff R5:同步讀整份 jsonl 會卡住 event loop(8 條 WS 推播/心跳一起頓),
        且前端每次 WS 重連自癒都打這條,恰在連線抖動時雪上加霜 —— route 必須把
        讀取丟到 worker thread。probe:to_thread 內 `asyncio.get_running_loop()` 必 raise。

        涵蓋面(review T-1):證的是「不在 loop 執行緒」;若改寫成同步 `def` route
        (anyio worker pool)也會綠 —— 那個寫法同樣不卡 loop,可接受。"""
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            hub = app.state.signal_hub
            assert hub is not None
            probe: dict[str, bool] = {}

            def _probing_today() -> list[dict]:
                try:
                    asyncio.get_running_loop()
                    probe["in_event_loop"] = True
                except RuntimeError:
                    probe["in_event_loop"] = False
                return []

            hub.today_signals = _probing_today  # type: ignore[method-assign]
            assert client.get("/api/stock/signals/today").json()["signals"] == []
        # dict 全等:probe 空(route 沒呼叫 today_signals)與 True(跑在 loop 上)
        # 兩種回歸都要印出實際值,不能壓成無訊息的 KeyError(review TC-1/T-1)
        assert probe == {"in_event_loop": False}, f"today_signals 未被呼叫或跑在 loop 上:{probe}"

    def test_unexpected_error_propagates_as_502(self, tmp_path: Path) -> None:
        """Edge case 3(review TC-2):to_thread 內的非預期例外要原樣傳回 await 處、
        落全域 handler 收 502 TC4_DOWN —— 不得被靜默降級成 200 + 空清單(那會讓
        前端自癒 baseline 整天顯示「今天沒訊號」,零錯誤訊號)。"""
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            hub = app.state.signal_hub
            assert hub is not None

            def _boom() -> list[dict]:
                raise RuntimeError("jsonl exploded")

            hub.today_signals = _boom  # type: ignore[method-assign]
            r = client.get("/api/stock/signals/today")
        assert r.status_code == 502
        assert r.json()["detail"]["error"] == "TC4_DOWN"

    def test_legacy_market_query_param_is_ignored(self, tmp_path: Path) -> None:
        """舊 bundle 打 `?market=exclude` 照樣 200 且結果與裸 URL 全等(spec §3)。

        market 分族刪掉後,瀏覽器裡還開著舊分頁的 client 會繼續帶那個查參自癒;route
        若哪天宣告了 `market` 查參(或加 pattern 驗證),舊 bundle 會在斷線後拿到 422
        —— 前端的 baseline 自癒整條靜默失效,而 WS 仍活著,畫面上看不出任何異常。
        """
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            trade_date = app.state.stock.trade_date
            row = _signal_row(trade_date)
            path = tmp_path / "signals" / f"{trade_date.replace('-', '')}.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
            bare = client.get("/api/stock/signals/today")
            legacy = client.get("/api/stock/signals/today", params={"market": "exclude"})
        assert legacy.status_code == 200
        assert legacy.json() == bare.json()
        assert bare.json()["signals"] == [row]


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
            assert [r["kind"] for r in rules] == _SEEDED_KINDS
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

    def test_cdp_body_missing_rearm_dwell_secs_400(self, tmp_path: Path) -> None:
        """W9 R15:精確鍵集合對新鍵一樣嚴 —— server 更新後未重新整理的舊分頁送 cdp 規則
        會缺 `rearm_dwell_secs`,預期降級成 INVALID_RULE(重新整理即恢復)。

        這裡不是可容忍的寬鬆點:放行等於使用者以為調得動駐留秒數,實際套的是 detector 預設。
        """
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            before = _rules(client)

            r = client.post(
                "/api/stock/signals/rules",
                json=_rule_body("cdp_cross", "舊分頁送的", params={"rearm_ticks": 5}),
            )

            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "INVALID_RULE"
            assert _rules(client) == before

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

    這一組守的是:規則 CRUD 是純檔案操作、today / `/ws/stock` 的匯流排住在 app 層,
    三者與達錢 4 一點關係都沒有,卻曾因為 hub 綁 stock engine 而一起消失。
    """

    def test_rule_crud_available_without_stock(self, tmp_path: Path) -> None:
        """SC-3:GET 200(預設規則)/ POST 201 / PUT 200 / DELETE 204,today 200。"""
        app, _ = make_app(tmp_path, with_stock=False)
        with BootedClient(app, raise_server_exceptions=False) as client:
            assert [r["kind"] for r in _rules(client)] == _SEEDED_KINDS

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
            assert today.json()["signals"] == []

    def test_rule_signal_reaches_today_on_wall_clock_date(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SC-2:訊號鏈(REST)照活,`trade_date` 走牆鐘 fallback。

        `TXO_BACKFILL_DATE` 顯式清掉:它是 fallback 的優先來源(edge §7.1),
        開發機 shell 留著它會讓這條斷言隨環境飄。
        """
        monkeypatch.delenv("TXO_BACKFILL_DATE", raising=False)
        _seed_watchlist(tmp_path)
        app, _ = make_app(tmp_path, with_stock=False)
        with BootedClient(app, raise_server_exceptions=False) as client:
            assert client.get("/api/stock/signals/today").json()["signals"] == []
            hub = app.state.signal_hub
            assert hub is not None
            assert hub._watch == {"2330"}, "membership 種子不得因為 engine 缺席而漏掉"
            today = f"{_date.today():%Y-%m-%d}"
            assert hub._trade_date_fn() == today, "無 engine 時日別來源 = 牆鐘"

            _emit_rule_signal(client, hub, monkeypatch, trade_date=today)
            row = _wait_signal(
                client, lambda r: r.get("kind") == "limit_lock" and r.get("code") == "2330"
            )

        assert row["trade_date"] == today

    def test_ws_stock_stays_open_and_carries_rule_signals(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SC-4:`/ws/stock` 不再立即 close;首則是 tc4=down 的 status seed(review P1-2)。

        沒有那則 seed 的話,前端「連線異常」提示靠 `status.tc4 === "down" ||
        wsStatus === "closed"` 觸發,而 `status` 初值是 `{tc4: "up"}` —— 掛著的空流
        會讓 TC4-off 完全無提示(比舊的立即 close 更糟)。
        """
        monkeypatch.delenv("TXO_BACKFILL_DATE", raising=False)
        _seed_watchlist(tmp_path)
        app, _ = make_app(tmp_path, with_stock=False)
        with BootedClient(app, raise_server_exceptions=False) as client:
            hub = app.state.signal_hub
            assert hub is not None
            assert hub._watch == {"2330"}
            today = f"{_date.today():%Y-%m-%d}"
            with client.websocket_connect("/ws/stock") as ws:
                assert _recv_json(ws) == {
                    "type": "status",
                    "tc4": "down",
                    "backfilling": None,
                    # L78 分態:無 engine 的 seed 標 engine=False(engine 發的 status 恆 True),
                    # 前端據此分「等待自動重連」與「需重啟伺服器」兩句(N109 真分態)
                    "engine": False,
                }

                _emit_rule_signal(client, hub, monkeypatch, trade_date=today)
                msg = _recv_until(ws, "signal")

        assert msg["kind"] == "limit_lock"
        assert msg["code"] == "2330"

    def test_ws_stock_hub_only_stream_gets_ping(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """W13:TC4 down 的 hub-only 空流是「恆無推播」那條 —— 心跳最有價值處。

        沒有心跳時這條連線與「半死」在前端完全不可分辨。首則仍是 status seed(W2)。
        """
        monkeypatch.setattr(ws_mod, "WS_HEARTBEAT_SECS", 0.05)
        monkeypatch.delenv("TXO_BACKFILL_DATE", raising=False)
        _seed_watchlist(tmp_path)
        app, _ = make_app(tmp_path, with_stock=False)
        with BootedClient(app, raise_server_exceptions=False) as client:
            with client.websocket_connect("/ws/stock") as ws:
                assert _recv_json(ws) == {
                    "type": "status",
                    "tc4": "down",
                    "backfilling": None,
                    # L78 分態:無 engine 的 seed 標 engine=False(engine 發的 status 恆 True),
                    # 前端據此分「等待自動重連」與「需重啟伺服器」兩句(N109 真分態)
                    "engine": False,
                }
                assert _recv_until(ws, "ping") == {"type": "ping"}

    def test_basis_is_disabled_without_a_daily_bars_source(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """T5(N020 後改口徑):無 engine → `daily_bars=None` = **配置上沒有日 K 來源**。

        改動前是塞一個恆回 `[]` 的替身,讓 hub 把配置態讀成「這一檔資料面就是沒有」——
        自選 50 檔 = 50 行「CDP 停用」WARNING + 50 格 job。現在 `request_basis` 整批
        早退:cache 一格都不落,membership 種子照舊(訊號鏈其餘部分不受影響),
        也仍然**不重試**(重試留給例外路徑 X-2b)。
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
            # 佇列本身就是判準:早退後它恆空,不必空轉等 worker「做錯事」。
            # `qsize()==0` 對「還沒排」與「排了又做完」同形 → 再看 cache / 重試記帳,
            # 三者一起才把「整批沒排進去」釘死(review ST2:原本 2.0 s 輪詢)。
            assert hub._basis_jobs.qsize() == 0
            deadline = time.monotonic() + 0.2
            while time.monotonic() < deadline:
                if hub._basis_cache:
                    raise AssertionError(f"無日 K 來源時不得落 basis:{hub._basis_cache}")
                time.sleep(0.02)
            assert hub._basis_retries == {}, "沒排過 job 就不該有重試記帳"

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
        _seed_watchlist(tmp_path)
        app, _ = make_app(tmp_path)
        with BootedClient(app, raise_server_exceptions=False) as client:
            hub = app.state.signal_hub
            assert hub is not None
            assert hub._watch == {"2330"}
            trade_date = app.state.stock.trade_date
            with client.websocket_connect("/ws/stock") as ws:
                assert _recv_json(ws)["type"] == "watchlist_quote", "engine 在場 → 首則是自選 seed"

                _emit_rule_signal(client, hub, monkeypatch, trade_date=trade_date)
                msg = _recv_until(ws, "signal")

        assert msg["kind"] == "limit_lock"
        assert msg["code"] == "2330"

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
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/ws/stock"):
                    raise AssertionError("hub 亦缺席時握手不該成功")

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

            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/ws/stock"):
                    raise AssertionError("boot 窗內握手不該成功")

            index.gate.set()
            wait_boot(app)
            # 翻轉對照:窗外同一條連線活著 → 上面那個 close 確實只出自「窗內」,
            # 而不是這個 app 的 `/ws/stock` 根本連不上
            with client.websocket_connect("/ws/stock") as ws:
                assert _recv_json(ws)["type"] == "status"


class TestConftestWatchlistIsolation:
    """T-4:root `tests/conftest.py` 的落點隔離 fixture 自身要有鎖。

    它是 SC-8 唯一的擋牆(hub 恆建之後,沒傳 `stock_watchlist_path` 的 19 個站點全會
    把 `signal_rules.json` / fake 訊號寫進 repo 真 `data/`),而 fixture 壞掉是
    **靜默**的:所有測試照樣綠,只有 prod 的 today 端點多出從未發生過的訊號列。

    fixture 原住 `tests/server/conftest.py`,2026-08-20 因 pytest 9.1.1 的參數順序
    bug(子目錄 conftest autouse 在「server 檔、根檔、server 檔」交錯參數下對最後
    一個 server 檔靜默失效)上移 root conftest —— 本測試當時就是那個必然紅的受害者。
    """

    def test_hub_data_dir_isolated_without_explicit_path(self, tmp_path: Path) -> None:
        app = create_app(
            FakeTxoSource(),
            stock_source=FakeStockSource(),
            throttle_secs=0.01,
        )  # 刻意不傳 stock_watchlist_path → 落點由 root conftest 的 autouse fixture 決定
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
