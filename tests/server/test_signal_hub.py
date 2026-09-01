"""SignalHub 接線層行為合約(design §4 / §7;SC-1 整合層 / SC-5 / SC-7 / SC-12 後端半)。

detector 本身的判定邏輯在 `tests/live/test_signal_state.py`,這裡只釘接線:
payload 逐鍵契約、membership gate、fanout(WS / jsonl / Discord)、基準 worker、
規則引擎(per-rule detector / basis cache / CRUD 熱重載)。時鐘一律注入,
daily_bars / publish / notify_fallback 全用 fake。
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from copycat.live.stock_models import StockBook, StockMeta, StockTick
from copycat.live.stock_source import DailyBar
from copycat.live.stock_state import StockDayState
from copycat.live.tc4 import HistoryTimeoutError
from copycat.server import signal_hub as hub_mod
from copycat.server.signal_hub import SignalHub, format_signal_group_text, format_signal_text
from copycat.signal_rules import CDP_LEVELS, MAX_RULES, RuleError, load_rules
from copycat.signals_config import SignalsConfig
from copycat.stock_watchlist import Group

_DATE = "2026-08-04"
_NEXT = "2026-08-05"
_THIRD = "2026-08-06"
_RULES_FILE = "signal_rules.json"
# design §7 的 WS 訊號契約鍵集合(jsonl row 為本集合 + trade_date)
_SIGNAL_KEYS = {
    "type",
    "id",
    "kind",
    "code",
    "name",
    "price",
    "time",
    "levels",
    "direction",
    "pct",
    "touch_count",
    "rule_id",
    "rule_name",
}

_RULE_PARAMS: dict[str, dict[str, float]] = {
    "cdp_cross": {"rearm_ticks": 5, "rearm_dwell_secs": 300},
    "surge_crash": {"pct": 2.0, "window_secs": 300},
    "surge_pullback": {"surge_pct": 2.0, "window_secs": 300, "pct": 1.0},
    "vol_burst": {
        "ratio": 3,
        "window_secs": 300,
        "min_elapsed_min": 15,
        "min_window_lots": 100,
        "min_day_lots": 500,
    },
    "limit_lock": {},
}


def _rule(kind: str, rid: str, **over: Any) -> dict[str, Any]:
    """規則樣板(參數 = SignalsConfig 預設,行為與遷移種子一致);over 覆寫任一欄。"""
    rule: dict[str, Any] = {
        "id": rid,
        "name": f"{kind}-{rid}",
        "kind": kind,
        "enabled": True,
        "notify_discord": True,
        "cooldown_secs": 600,
        "params": dict(_RULE_PARAMS[kind]),
        "cdp_levels": list(CDP_LEVELS) if kind == "cdp_cross" else [],
    }
    rule.update(over)
    return rule


def _write_rules(tmp_path: Path, rules: list[dict[str, Any]]) -> None:
    """預寫規則檔:hub 建構時就走 load 而非遷移(注入受測規則集合的唯一入口)。

    寫**當前版本 v3**:寫舊版會觸發遷移鏈 append surge_pullback 種子卡,
    「注入的集合 = 受測的集合」這個前提就破了(遷移行為由 test_signal_rules 專測)。
    """
    (tmp_path / _RULES_FILE).write_text(
        json.dumps({"_cache_version": 3, "rules": rules}, ensure_ascii=False), encoding="utf-8"
    )


class _Clock:
    def __init__(self, start: _dt.datetime | None = None) -> None:
        self.now = start if start is not None else _dt.datetime(2026, 8, 4, 10, 0, 0)

    def __call__(self) -> _dt.datetime:
        return self.now

    def advance(self, secs: float) -> None:
        self.now += _dt.timedelta(seconds=secs)


def _bar(date: str, high: int, low: int, close: int) -> DailyBar:
    return DailyBar(date=date, high=high, low=low, close=close)


# compute_cdp(80_000, 70_000, 75_000) → cdp 75_000 / ah 85_000 / nh 80_000 / nl 70_000 / al 65_000
_BAR_A = _bar("2026-08-01", 80_000, 70_000, 75_000)
# compute_cdp(95_000, 85_000, 90_000) → cdp 90_000 / ah 100_000 / nh 95_000 / nl 85_000 / al 80_000
_BAR_B = _bar("2026-08-04", 95_000, 85_000, 90_000)
# compute_cdp(125_000, 115_000, 120_000) → cdp 120_000 / nh 125_000(與 _BAR_B 的線完全不重疊)
_BAR_C = _bar("2026-08-05", 125_000, 115_000, 120_000)


def _tick(
    price: int,
    *,
    code: str = "2330",
    qty: int = 1,
    cum: int = 1,
    time: str = "10:00:00.123",
    trade_date: str = _DATE,
) -> StockTick:
    return StockTick(
        code=code,
        price_milli=price,
        qty=qty,
        cum_vol=cum,
        time=time,
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


class _FakeBars:
    """engine.daily_bars 的替身;`bars` 可中途換掉以模擬換日新增一根。"""

    def __init__(
        self,
        bars: list[DailyBar] | None = None,
        *,
        error: bool = False,
        error_exc: Exception | None = None,
    ) -> None:
        self.bars = list(bars or [])
        self.error = error or error_exc is not None
        #: 拋哪一型由呼叫端指定 —— `HistoryTimeoutError`(逾時)與其餘例外在 hub 的
        #: **處置相同**,差別只在 log 等級與有沒有 traceback,分不出型別就測不到那件事
        self.error_exc = error_exc
        self.calls: list[tuple[str, int]] = []

    async def __call__(self, code: str, n: int = 25) -> list[DailyBar]:
        self.calls.append((code, n))
        if self.error:
            raise self.error_exc if self.error_exc is not None else ConnectionError("TC4 不可用")
        return list(self.bars)


class _GatedBars(_FakeBars):
    """掛上 `gate` 後**下一次**呼叫會卡在閘門上 —— 用來造「in-flight job 跨過換日」。

    基準 worker 是序列的,唯一能讓一則舊 job 在 promote **之後**才 settle 的方法,
    就是把它卡在日 K 那個 await 上。
    """

    def __init__(self, bars: list[DailyBar] | None = None) -> None:
        super().__init__(bars)
        self.gate: asyncio.Event | None = None
        self.entered = asyncio.Event()

    async def __call__(self, code: str, n: int = 25) -> list[DailyBar]:
        gate = self.gate
        if gate is not None:
            self.gate = None
            self.entered.set()
            await gate.wait()
        return await super().__call__(code, n)


class _FlakyBars(_FakeBars):
    """前 `fail_times` 次拋例外(連線 / 傳輸層抖動),之後正常回 bars。

    X-2b 的分流前提:同一個 code 的同一天,失敗與成功可以在幾十秒內先後發生 ——
    `_FakeBars(error=True)` 的「永遠失敗」測不到這件事。
    """

    def __init__(self, bars: list[DailyBar] | None = None, *, fail_times: int = 1) -> None:
        super().__init__(bars)
        self.fail_times = fail_times

    async def __call__(self, code: str, n: int = 25) -> list[DailyBar]:
        if len(self.calls) < self.fail_times:
            self.calls.append((code, n))
            raise ConnectionError("TC4 連線抖動")
        return await super().__call__(code, n)


def _boom_cdp(*_args: int) -> dict[str, int]:
    raise RuntimeError("compute_cdp 壞了")


class _Watch:
    """`groups_fn` / `quotes_fn` 的替身(SC-1/2):內容可換、可設成拋例外。

    生產端兩者分別是「讀自選檔」與「讀 engine 現值」—— 都可能在盤中失敗,而摘要
    是通知的**裝飾**,失敗絕不能連帶把訊號本身打掉,所以兩條失敗路徑都要有替身。
    """

    def __init__(
        self,
        groups: list[Group] | None = None,
        quotes: dict[str, tuple[str, float | None]] | None = None,
    ) -> None:
        self.groups: list[Group] = list(groups or [])
        self.quotes: dict[str, tuple[str, float | None]] = dict(quotes or {})
        self.groups_error = False
        self.quotes_error = False

    def groups_fn(self) -> list[Group]:
        if self.groups_error:
            raise RuntimeError("自選檔讀取失敗")
        return list(self.groups)

    def quotes_fn(self) -> dict[str, tuple[str, float | None]]:
        if self.quotes_error:
            raise RuntimeError("engine quotes 壞了")
        return dict(self.quotes)


#: `_Harness(daily_bars=...)` 的「未傳」哨兵(None 是合法且有意義的值)
_UNSET: object = object()


class _Harness:
    def __init__(
        self,
        tmp_path: Path,
        clock: _Clock,
        bars: _FakeBars | None = None,
        wl: _Watch | None = None,
        daily_bars: object = _UNSET,
        **over: float | int,
    ) -> None:
        self.published: list[dict] = []
        self.fallback: list[str] = []
        self.bot: list[str] = []
        self.bot_fails = False
        #: bot 未 ready(channel 還沒取到)→ `send_signal` 回 False。這是**生產預設態**
        #: (token 未設 / 頻道未設 / 剛啟動),不是例外路徑。
        self.bot_ready = True
        #: webhook 未設 URL 時 `notify_discord` 回 False(never-raise)
        self.notify_ok = True
        self.date = _DATE
        self.data_dir = tmp_path
        self.bars = bars if bars is not None else _FakeBars([_BAR_A])
        cfg = replace(SignalsConfig(), basis_gap_secs=0.0, **over)  # type: ignore[arg-type]
        self.hub = SignalHub(
            cfg,
            publish=self.published.append,
            # `daily_bars=None` 是**顯式的「沒有日 K 來源」**(N110),與「不傳 = 用
            # `self.bars`」是兩件事 → 用 sentinel 分,不能拿 None 當「未傳」
            daily_bars=self.bars if daily_bars is _UNSET else daily_bars,  # type: ignore[arg-type]
            notify_fallback=self._notify,
            data_dir=tmp_path,
            trade_date_fn=lambda: self.date,
            now_fn=clock,
            # 預設 None = 未注入(既有測試的摘要恆為空字串,行為零改動)
            groups_fn=wl.groups_fn if wl is not None else None,
            quotes_fn=wl.quotes_fn if wl is not None else None,
        )

    def _notify(self, text: str) -> bool:
        self.fallback.append(text)
        return self.notify_ok

    async def _send(self, text: str) -> bool:
        if self.bot_fails:
            raise RuntimeError("discord bot 斷線")
        if not self.bot_ready:
            return False
        self.bot.append(text)
        return True

    def attach_bot(self) -> None:
        self.hub.attach_discord(self._send)

    async def settle(self) -> None:
        await asyncio.wait_for(self.hub._basis_jobs.join(), 2)
        await asyncio.wait_for(self.hub._jsonl_queue.join(), 2)
        await asyncio.wait_for(self.hub._discord_queue.join(), 2)

    def rule_id(self, kind: str) -> str:
        return next(r["id"] for r in self.hub.rules() if r["kind"] == kind)

    def rule_name(self, kind: str) -> str:
        return next(r["name"] for r in self.hub.rules() if r["kind"] == kind)

    def rows(self, date: str = _DATE) -> list[dict]:
        path = self.data_dir / "signals" / f"{date.replace('-', '')}.jsonl"
        if not path.exists():
            return []
        return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]

    def cross_nh(self, state: StockDayState, code: str = "2330") -> None:
        """走 CDP nh(80_000)由下而上穿越:首 tick 只初始化,第二筆觸發。"""
        self.hub.on_tick(code, _tick(79_000, code=code), state)
        self.hub.on_tick(code, _tick(80_500, code=code, cum=2), state)

    def lock_up(self, state: StockDayState, code: str = "2330") -> None:
        self.hub.on_tick(code, _tick(109_000, code=code), state)
        self.hub.on_tick(code, _tick(110_000, code=code, cum=2), state)


def _drain(queue: asyncio.Queue[dict]) -> list[dict]:
    rows: list[dict] = []
    while not queue.empty():
        rows.append(queue.get_nowait())
    return rows


def _seed_jsonl(tmp_path: Path, date: str, rows: list[dict[str, Any]]) -> None:
    """直接鋪當日 jsonl(模擬「上一個 process 留下的檔」)。"""
    path = tmp_path / "signals" / f"{date.replace('-', '')}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )


def _merge_rules() -> list[dict[str, Any]]:
    """SC-4 的最小「同 tick 兩事件」組合:兩條 CDP 規則各訂一條線,一筆 tick 同時穿過兩條。

    用兩條**不同線**的規則(而非同線兩規則)是為了讓兩段 kind 文案不同 —— 去重
    邏輯若寫成「無條件砍成一段」,同線版本會綠而這版會紅。
    """
    return [
        _rule("cdp_cross", "r-1-000", name="NH 規則", cdp_levels=["nh"]),
        _rule("cdp_cross", "r-1-001", name="AH 規則", cdp_levels=["ah"]),
    ]


def _cross_both(h: _Harness, code: str = "2330", time: str = "10:00:00") -> None:
    """一筆 tick 同時穿過 nh(80.00)與 ah(85.00):兩條規則同一 (code, time) 各發一則。"""
    state = _state()
    h.hub.on_tick(code, _tick(79_000, code=code, time=f"{time}.100"), state)
    h.hub.on_tick(code, _tick(86_000, code=code, cum=2, time=f"{time}.123"), state)


def _long_rows(n: int = 2, pad: int = 1200) -> list[dict[str, Any]]:
    """同 (code, time) 的多則,規則名刻意很長 → 合併文本必然超過 1900 字元(edge 8)。

    規則名沒有長度上限,而 bot / webhook 兩層都沒有截斷 —— 不分批就是整則被 Discord
    退回(缺角靜默)。`pad=1200` 讓單則約 1.2k 字:兩則必然分成兩批,一則必然不分。
    """
    return [
        {
            "id": f"sig-{i}",
            "kind": "vol_burst",
            "code": "2330",
            "name": "台積電",
            "price": 100_000,
            "time": "10:00:00",
            "pct": 3.0 + i,  # 每則 kind 文案不同 → 去重不得把它們併掉
            "rule_name": f"規則{i}" + "長" * pad,
        }
        for i in range(n)
    ]


def _tight_rows() -> list[dict[str, Any]]:
    """貼著上限的治具(T-3):配 `_TIGHT_SUFFIX` 時合併文本 2 則 = 1282 字、
    3 則 = **1900 字**(= 上限)、4 則 = 2518 字。

    3 則落在 (1884, 1900] 這個窄帶裡 —— 正是「不預留批尾 ` (i/N)` 就會切出超標批」
    的唯一區間。少了 `_BATCH_TAG_RESERVE`,貪婪切批會把 3 則收成一批,加上批尾 6 字
    就是 1906 字(Discord 2000 硬上限之下、本專案 1900 之上)。
    """
    return [
        {
            "id": f"sig-{i}",
            "kind": "vol_burst",
            "code": "2330",
            "name": "台積電",
            "price": 100_000,
            "time": "10:00:00",
            "pct": 3.0 + i,  # kind 文案逐則不同 → 去重不得把它們併掉
            "rule_name": f"規{i}" + "長" * 606,
        }
        for i in range(4)
    ]


#: `_tight_rows` 的長度計算把摘要一起算進去(`_split_batches` 也是)
_TIGHT_SUFFIX = "｜同群 半導體:2317鴻海 +0.8%"


def _cache(h: _Harness, code: str = "2330") -> tuple[str, int | None]:
    """hub 的 basis cache 摘要 → (基準日, nh 線價);cdp 不可得時 nh 為 None。"""
    basis_date, cdp = h.hub._basis_cache[code]
    return basis_date, None if cdp is None else cdp["nh"]


async def _wait_rows(h: _Harness, n: int, timeout: float = 2.0) -> None:
    """等 jsonl 落到 n 筆(不碰私有佇列 —— 這裡驗的正是「哪條路徑卡不住哪條」)。"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if len(h.rows()) >= n:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"jsonl 只落了 {len(h.rows())} 筆,等不到 {n} 筆")


async def _wait_calls(bars: _FakeBars, n: int, timeout: float = 2.0) -> None:
    """等 daily_bars 被打到第 n 次 —— 重試是**延遲入列**的,不在 `settle()` 的射程內
    (job 已 `task_done`,佇列是空的,`join()` 立刻返回)。"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if len(bars.calls) >= n:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"daily_bars 只被打了 {len(bars.calls)} 次,等不到 {n} 次")


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


class TestPayloadContract:
    async def test_ws_and_jsonl_key_contract(self, tmp_path: Path, clock: _Clock) -> None:
        h = _Harness(tmp_path, clock)
        h.attach_bot()
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            h.cross_nh(_state())
            await h.settle()

            assert len(h.published) == 1
            msg = h.published[0]
            assert set(msg) == _SIGNAL_KEYS
            assert msg["type"] == "signal"
            assert msg["kind"] == "cdp_cross"
            assert msg["code"] == "2330"
            assert msg["name"] == "台積電"
            assert msg["price"] == 80_500
            assert msg["time"] == "10:00:00"
            assert msg["levels"] == ["nh"]
            assert msg["direction"] == "from_below"
            assert msg["pct"] is None
            assert msg["touch_count"] == 1
            # id 帶 rule 段(SC-2):同 kind 多規則同 tick 的兩則事件不得撞 id
            rid = h.rule_id("cdp_cross")
            assert msg["rule_id"] == rid
            assert msg["rule_name"] == h.rule_name("cdp_cross")
            assert msg["id"] == f"2026-08-04-{rid}-2330-cdp_cross-nh-10:00:00.123"

            rows = h.rows()
            assert len(rows) == 1
            assert set(rows[0]) == _SIGNAL_KEYS | {"trade_date"}
            assert rows[0]["trade_date"] == _DATE
            assert rows[0]["id"] == msg["id"]
            assert len(h.bot) == 1
            assert h.fallback == []
        finally:
            await h.hub.close()

    async def test_name_empty_when_meta_missing(self, tmp_path: Path, clock: _Clock) -> None:
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            h.cross_nh(_state(name=None))
            await h.settle()
            assert h.published[0]["name"] == ""
        finally:
            await h.hub.close()

    async def test_limit_lock_id_uses_direction(self, tmp_path: Path, clock: _Clock) -> None:
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            h.lock_up(_state(upper=110_000, locked_up=True))
            await h.settle()
            assert h.published[0]["kind"] == "limit_lock"
            rid = h.rule_id("limit_lock")
            assert h.published[0]["id"] == f"2026-08-04-{rid}-2330-limit_lock-up-10:00:00.123"
        finally:
            await h.hub.close()


class TestMembership:
    async def test_non_watchlist_code_emits_nothing(self, tmp_path: Path, clock: _Clock) -> None:
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            h.lock_up(_state(upper=110_000, locked_up=True), code="2317")
            h.hub.on_book("2317", _state(upper=110_000))
            await h.settle()
            assert h.published == []
            assert h.rows() == []
        finally:
            await h.hub.close()

    async def test_contract_instrument_key_emits_nothing(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """code review B7:個股期合約主圖的推播不得產出訊號 —— 即使它的標的股在自選裡。

        engine 的訊號掛點是**逐 instrument key** 的(`_handle_quote` 不分現貨 / 合約),
        擋在這裡的只有 membership gate。合約鍵永遠不可能進 `_watch`(自選存的是股號),
        所以這條是結構不變量;把它釘住是因為破壞它的改動長得很無害 —— 有人把合約鍵
        「正規化」回標的股號,訊號就會拿期貨價去比現貨的 CDP 線,而畫面上只是多了
        幾則看起來很合理的假訊號。
        """
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            h.lock_up(_state(upper=110_000, locked_up=True), code="F:CDF:202609")
            h.hub.on_book("F:CDF:202609", _state(upper=110_000))
            await h.settle()
            assert h.published == []
            assert h.rows() == []
            # 對照組:同一組 tick 走股號就會發 —— 沒有這一半,上面全綠也可能是治具壞了
            h.lock_up(_state(upper=110_000, locked_up=True))
            await h.settle()
            assert [p["code"] for p in h.published] == ["2330"]
        finally:
            await h.hub.close()

    async def test_removed_code_dropped_and_added_code_gets_basis(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            assert [c for c, _n in h.bars.calls] == ["2330"]
            h.hub.on_watchlist(["2330", "2317"])  # 差集:只抓新增的那檔
            await h.settle()
            assert [c for c, _n in h.bars.calls] == ["2330", "2317"]

            h.cross_nh(_state())  # 2330 有基準 → 先建立 prev 狀態並觸發一次
            await h.settle()
            assert len(h.published) == 1
            h.hub.on_watchlist(["2317"])  # 2330 被移除 → drop_code + 不再評估
            h.hub.on_tick("2330", _tick(90_000, cum=3), _state())
            await h.settle()
            assert len(h.published) == 1
        finally:
            await h.hub.close()


    async def test_same_codes_again_drops_nothing_and_refetches_no_basis(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """group-only 變更(建群 / 改名 / 移出群組)會以**相同 codes** 再走一次
        `set_watchlist` → hub 也收到同一份名單(watchlist_service R9 的另一半前提)。

        差集若失守,盤中改個群組就會把每檔的 CDP 基準 drop 掉再重抓 —— 那條路要打 TC4
        日 K,重抓期間 CDP 訊號整段停用,而畫面與 log 都不會有任何異狀。
        """
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330", "2317"])
            await h.settle()
            fetched = [c for c, _n in h.bars.calls]
            assert fetched == ["2317", "2330"]  # 基準非零:第一次真的抓了(request_basis 排序)

            dropped: list[str] = []
            for slot in h.hub._slots.values():  # 逐 slot:drop 已是每顆 detector 各做一次
                slot.detector.drop_code = dropped.append  # type: ignore[method-assign]

            h.hub.on_watchlist(["2317", "2330"])  # 同集合(順序不同)
            await h.settle()

            assert dropped == []
            assert [c for c, _n in h.bars.calls] == fetched  # 零重抓
        finally:
            await h.hub.close()


class TestBackfillIsolation:
    async def test_apply_backfill_replay_does_not_reach_hub(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """SC-5:hub 沒有任何回補入口,state 自行重放不會再產訊號。"""
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            state = _state()
            h.cross_nh(state)
            await h.settle()
            assert len(h.published) == 1

            state.apply_backfill([_tick(79_000), _tick(80_500, cum=2)])
            await h.settle()
            assert len(h.published) == 1
            assert len(h.rows()) == 1
        finally:
            await h.hub.close()


class TestHistoryAndId:
    async def test_jsonl_survives_restart_with_stable_id(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """SC-7:id 是決定性鍵 → 重啟後重發同一事件 id 相同(前端據此去重)。"""
        first = _Harness(tmp_path, clock)
        await first.hub.start()
        try:
            first.hub.on_watchlist(["2330"])
            await first.settle()
            first.cross_nh(_state())
            await first.settle()
        finally:
            await first.hub.close()

        second = _Harness(tmp_path, clock)
        await second.hub.start()
        try:
            second.hub.on_watchlist(["2330"])
            await second.settle()
            second.cross_nh(_state())
            await second.settle()
            rows = second.rows()
            assert len(rows) == 2
            assert rows[0]["id"] == rows[1]["id"]
            assert second.hub.today_signals() == rows
        finally:
            await second.hub.close()

    async def test_restart_new_signal_id_does_not_collide_with_old(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """SC-7 amendment 的另一半:上一條釘的是「同一事件 → 同 id」(去重要的);
        這條釘反命題 —— 重啟後的**新**事件不得撞上重啟前任一則的 id。

        撞到的話前端會把新訊號當重複丟掉,而畫面上只是「這則沒出現」。
        """
        first = _Harness(tmp_path, clock)
        await first.hub.start()
        try:
            first.hub.on_watchlist(["2330"])
            await first.settle()
            first.cross_nh(_state())
            await first.settle()
            before = {m["id"] for m in first.published}
            assert before
        finally:
            await first.hub.close()

        clock.now = _dt.datetime(2026, 8, 4, 10, 30, 0)
        second = _Harness(tmp_path, clock)
        await second.hub.start()
        try:
            second.hub.on_watchlist(["2330"])
            await second.settle()
            state = _state()  # 重啟後另一次穿越(同一條線、不同時刻與方向)
            second.hub.on_tick("2330", _tick(81_000, time="10:30:00.500"), state)
            second.hub.on_tick("2330", _tick(79_500, cum=2, time="10:30:01.100"), state)
            await second.settle()

            after = {m["id"] for m in second.published}
            assert after
            assert not (after & before)
            assert len({r["id"] for r in second.rows()}) == 2
        finally:
            await second.hub.close()

    async def test_today_signals_skips_broken_lines(self, tmp_path: Path, clock: _Clock) -> None:
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            h.cross_nh(_state())
            await h.settle()
            path = tmp_path / "signals" / "20260804.jsonl"
            with path.open("a", encoding="utf-8") as fh:
                fh.write("{壞行\n")
            assert len(h.hub.today_signals()) == 1
        finally:
            await h.hub.close()

    async def test_truncated_multibyte_tail_keeps_good_rows(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """半寫入的最後一行切在中文序列中間 → 好行全保留,兩條消費路都不得拋。

        `read_text(encoding="utf-8")` 對這種截斷丟的是 `UnicodeDecodeError`(ValueError
        系),不在 `except OSError` 內 —— 整個當日檔一起消失,而 today 端點 / 前端自癒
        兩條路會同時整天壞著(review round-2 HR-1)。
        """
        path = tmp_path / "signals" / f"{_DATE.replace('-', '')}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        good = {
            "id": "a",
            "kind": "limit_lock",
            "code": "2330",
            "name": "台積電",
            "direction": "up",
            "trade_date": _DATE,
        }
        good_bytes = json.dumps(good, ensure_ascii=False).encode("utf-8")
        tail = json.dumps({"id": "b", "code": "2317", "name": "鴻海"}, ensure_ascii=False)
        tail_bytes = tail.encode("utf-8")
        # 切在「鴻」的第 2 個 byte:UTF-8 續位元組單獨解不出來(半寫入的真實樣態)
        cut = tail_bytes[: tail_bytes.index("鴻".encode("utf-8")) + 1]
        path.write_bytes(good_bytes + b"\n" + cut)

        h = _Harness(tmp_path, clock)
        assert h.hub.read_signals(_DATE) == [good]
        assert h.hub.today_signals() == [good]


class TestEnabled:
    async def test_disabled_rule_emits_nothing_and_persists(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """SC-2:停用的單位是**規則**,停用態隨規則檔跨重啟保留;其他規則照發。

        事前標記的契約改寫(design R8「既有測試遷移」表):原
        `test_disabled_kind_emits_nothing_and_persists` 釘的是 `set_enabled` 四鍵開關,
        該家族已不參與評估(評估只讀 slots),本輪整組退役。
        """
        _write_rules(tmp_path, [_rule("cdp_cross", "r-1-000"), _rule("limit_lock", "r-1-001")])
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            await h.hub.upsert_rule(_rule("cdp_cross", "r-1-000", enabled=False), rule_id="r-1-000")
            h.hub.on_watchlist(["2330", "2317"])
            await h.settle()
            h.cross_nh(_state())
            await h.settle()
            assert h.published == []

            h.lock_up(_state(upper=110_000, locked_up=True), code="2317")
            await h.settle()
            assert [m["kind"] for m in h.published] == ["limit_lock"]
        finally:
            await h.hub.close()

        again = _Harness(tmp_path, clock)
        by_id = {r["id"]: r["enabled"] for r in again.hub.rules()}
        assert by_id == {"r-1-000": False, "r-1-001": True}


class TestDiscordFanout:
    async def test_throttle_blocks_only_discord(self, tmp_path: Path, clock: _Clock) -> None:
        """節流上限 30/分:第 31 則不送 Discord,但 WS 與 jsonl 完整(design §4.3)。"""
        h = _Harness(tmp_path, clock)
        h.attach_bot()
        await h.hub.start()
        try:
            codes = [f"{9000 + i}" for i in range(31)]
            h.hub.on_watchlist(codes)
            await h.settle()
            for code in codes:
                h.lock_up(_state(upper=110_000, locked_up=True), code=code)
            await h.settle()
            assert len(h.published) == 31
            assert len(h.rows()) == 31
            assert len(h.bot) == 30
            assert h.fallback == []
        finally:
            await h.hub.close()

    async def test_bot_failure_falls_back_to_webhook(self, tmp_path: Path, clock: _Clock) -> None:
        h = _Harness(tmp_path, clock)
        h.attach_bot()
        h.bot_fails = True
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            h.cross_nh(_state())
            await h.settle()
            assert h.bot == []
            assert len(h.fallback) == 1
            assert "2330" in h.fallback[0]
            assert len(h.rows()) == 1
        finally:
            await h.hub.close()

    async def test_bot_not_ready_returns_false_and_falls_back(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """TQ-1:bot 沒 ready 的真實樣態是 `send_signal` **回 False**,不是丟例外。

        頻道未設 / on_ready 還沒跑完 = 生產預設態,這條降級路徑必須有覆蓋。
        """
        h = _Harness(tmp_path, clock)
        h.attach_bot()
        h.bot_ready = False
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            h.cross_nh(_state())
            await h.settle()

            assert h.bot == []
            assert len(h.fallback) == 1
            assert "2330" in h.fallback[0]
            assert len(h.rows()) == 1
            assert len(h.published) == 1
        finally:
            await h.hub.close()

    async def test_webhook_returning_false_is_not_an_error_path(
        self, tmp_path: Path, clock: _Clock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """TQ-1:兩層皆未送出(webhook URL 未設 → notify 回 False)。

        「沒送出去」是可接受的降級,不是例外 —— worker 不得記 ERROR、jsonl 與 WS 照常。
        """
        h = _Harness(tmp_path, clock)
        h.notify_ok = False
        await h.hub.start()
        try:
            with caplog.at_level(logging.ERROR, logger="copycat.server.signal_hub"):
                h.hub.on_watchlist(["2330"])
                await h.settle()
                h.cross_nh(_state())
                await h.settle()

            assert len(h.fallback) == 1
            assert len(h.rows()) == 1
            assert len(h.published) == 1
            assert [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR] == []
        finally:
            await h.hub.close()

    async def test_no_bot_attached_uses_webhook(self, tmp_path: Path, clock: _Clock) -> None:
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            h.cross_nh(_state())
            await h.settle()
            assert len(h.fallback) == 1
        finally:
            await h.hub.close()

    async def test_slow_discord_does_not_starve_jsonl(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """CC-5:jsonl 是歷史真相源,不得被 Discord 這條「可丟」的路徑卡住。

        單一 worker 把 jsonl→Discord 序列化,Discord 一卡住整條佇列就停;WS 已經送出去
        的訊號進不了 jsonl,而重連 refetch 讀的正是 jsonl —— 缺角靜默且不可回復。
        """
        gate = asyncio.Event()

        async def _stuck(text: str) -> bool:
            await gate.wait()
            return True

        h = _Harness(tmp_path, clock)
        h.hub.attach_discord(_stuck)
        await h.hub.start()
        try:
            codes = [f"{9000 + i}" for i in range(3)]
            h.hub.on_watchlist(codes)
            await asyncio.wait_for(h.hub._basis_jobs.join(), 2)
            for code in codes:
                h.lock_up(_state(upper=110_000, locked_up=True), code=code)

            await _wait_rows(h, 3)
            assert len(h.published) == 3
        finally:
            gate.set()
            await h.hub.close()

    async def test_queue_full_drops_oldest(
        self, tmp_path: Path, clock: _Clock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """滿載策略(design R14):丟最舊 + dropped 計數,熱路徑不反壓。"""
        monkeypatch.setattr(hub_mod, "JSONL_QUEUE_MAXSIZE", 2)
        monkeypatch.setattr(hub_mod, "DISCORD_QUEUE_MAXSIZE", 2)
        h = _Harness(tmp_path, clock)  # 刻意不 start:worker 不消化,佇列必滿
        codes = [f"{9000 + i}" for i in range(5)]
        h.hub.on_watchlist(codes)
        for code in codes:
            h.lock_up(_state(upper=110_000, locked_up=True), code=code)
        assert len(h.published) == 5  # WS 不受佇列影響
        assert h.hub.dropped_jsonl == 3
        assert h.hub.dropped_discord == 3
        # TQ-2:只數 qsize 分不出「丟最舊」與「丟最新」—— 留下的必須是最新兩則
        assert [r["code"] for r in _drain(h.hub._jsonl_queue)] == ["9003", "9004"]
        assert [r["code"] for r in _drain(h.hub._discord_queue)] == ["9003", "9004"]

    async def test_close_flushes_pending_jsonl_and_abandons_discord(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """TQ-3:關機盡力落檔 —— jsonl 是真相源要寫完,Discord 這時不再送。"""
        h = _Harness(tmp_path, clock)  # 刻意不 start:兩則都還躺在佇列裡
        h.attach_bot()
        h.hub.on_watchlist(["2330", "2317"])
        h.lock_up(_state(upper=110_000, locked_up=True), code="2330")
        h.lock_up(_state(upper=110_000, locked_up=True), code="2317")
        assert h.rows() == []

        await h.hub.close()

        assert [r["code"] for r in h.rows()] == ["2330", "2317"]
        assert h.bot == []
        assert h.fallback == []

    async def test_jsonl_write_failure_does_not_kill_worker(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """TQ-4:落檔炸掉(磁碟滿 / 權限)只該丟掉那一筆,worker 死掉 = 之後整天無聲。"""
        h = _Harness(tmp_path, clock)
        real = h.hub._append_jsonl
        seen: list[dict] = []

        def flaky(row: dict) -> None:
            seen.append(row)
            if len(seen) == 1:
                raise OSError("磁碟滿了")
            real(row)

        h.hub._append_jsonl = flaky  # type: ignore[method-assign]
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330", "2317"])
            await h.settle()

            h.lock_up(_state(upper=110_000, locked_up=True), code="2330")
            await h.settle()  # 不得往外拋
            assert h.rows() == []

            h.lock_up(_state(upper=110_000, locked_up=True), code="2317")
            await h.settle()
            assert [r["code"] for r in h.rows()] == ["2317"]  # worker 還活著
        finally:
            await h.hub.close()


class TestDiscordMerge:
    """SC-4:同 code、同 time 且在 Discord 佇列中**相鄰**的多 row → 一則訊息。

    合併只發生在**送出端**:WS / jsonl / id 逐 row 不變(W6)—— emit 端合併會改 id,
    重連 refetch jsonl 就會出現合併前後兩份不同 id 的重複列。
    """

    async def test_same_tick_two_events_send_once(self, tmp_path: Path, clock: _Clock) -> None:
        """同一 tick 兩則 → sender 只被打一次,文案含兩段 kind + 兩個規則名 + 同群摘要。"""
        _write_rules(tmp_path, _merge_rules())
        wl = _Watch(
            groups=[{"name": "半導體", "codes": ["2330", "2317"]}],
            quotes={"2330": ("台積電", 1.5), "2317": ("鴻海", 0.8)},
        )
        h = _Harness(tmp_path, clock, wl=wl)
        h.attach_bot()
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330", "2317"])
            await h.settle()
            _cross_both(h)
            await h.settle()

            assert len(h.published) == 2  # W6:WS 逐 row
            assert len(h.rows()) == 2  # W6:jsonl 逐 row
            assert h.bot == [
                "🔔 突破 CDP NH(壓力・第1次)・突破 CDP AH(壓力・第1次)"
                "｜台積電 2330｜86.00｜10:00:00｜NH 規則・AH 規則"
                "｜同群 半導體:2317鴻海 +0.8%"
            ]
        finally:
            await h.hub.close()

    async def test_different_tick_not_merged_and_order_kept(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """同 tick A(兩則)+ 不同 tick B(一則)混排 → 2 則、順序不變。

        B 是被存進 pending 那一則:`settle()`(= `_discord_queue.join()`)返回時它必須
        **已送出** —— 送出前就 `task_done` 的話 join 會提早返回,關機與測試屏障同時失真。
        """
        _write_rules(tmp_path, _merge_rules())
        h = _Harness(tmp_path, clock)
        h.attach_bot()
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330", "2317"])
            await h.settle()

            _cross_both(h)  # 2330:同一 tick 兩則
            state = _state()  # 2317:另一個 tick,只穿 nh → 一則
            h.hub.on_tick("2317", _tick(79_000, code="2317", time="10:00:05.100"), state)
            h.hub.on_tick("2317", _tick(80_500, code="2317", cum=2, time="10:00:06.000"), state)
            await h.settle()

            assert len(h.published) == 3
            assert len(h.bot) == 2
            assert "2330" in h.bot[0] and "NH 規則・AH 規則" in h.bot[0]
            assert h.bot[1] == "🔔 突破 CDP NH(壓力・第1次)｜台積電 2317｜80.50｜10:00:06｜NH 規則"
        finally:
            await h.hub.close()

    async def test_same_code_different_second_not_merged(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """T-1:同 code、**不同秒**的兩筆 tick 各發一則 —— 合併粒度是 (code, time)。

        既有「不合併」測試用的是兩個不同 code,把 `_same_tick` 的 time 比對整條拿掉
        也照樣綠;而錯合併的代價是第二筆的價位與時刻被第一筆蓋掉(同一檔連續兩次
        穿越在 Discord 上只剩一則,且印的是舊價)。
        """
        _write_rules(tmp_path, _merge_rules())
        h = _Harness(tmp_path, clock)
        h.attach_bot()
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()

            state = _state()
            h.hub.on_tick("2330", _tick(79_000, time="10:00:00.100"), state)
            h.hub.on_tick("2330", _tick(80_500, cum=2, time="10:00:01.000"), state)  # 穿 nh
            h.hub.on_tick("2330", _tick(86_000, cum=3, time="10:00:02.000"), state)  # 穿 ah
            await h.settle()

            assert h.bot == [
                "🔔 突破 CDP NH(壓力・第1次)｜台積電 2330｜80.50｜10:00:01｜NH 規則",
                "🔔 突破 CDP AH(壓力・第1次)｜台積電 2330｜86.00｜10:00:02｜AH 規則",
            ]
        finally:
            await h.hub.close()

    async def test_three_pending_rounds_keep_worker_alive(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """連續三輪含 pending 的混排:每輪都把下一組的頭一則存進 pending。

        記帳錯一格就會 `task_done() called too many times`(ValueError)→ worker 當場
        死掉,之後整天 Discord 無聲而 WS/jsonl 都正常(最難查的那種靜默)。
        `close()` 會把 worker 的例外 re-raise,ValueError 在這裡逃不掉。
        """
        _write_rules(tmp_path, _merge_rules())
        h = _Harness(tmp_path, clock)
        h.attach_bot()
        await h.hub.start()
        try:
            codes = ["2330", "2317", "2454", "1101"]
            h.hub.on_watchlist(codes)
            await h.settle()

            for code in codes[:3]:  # 三組,每組同 tick 兩則(六則一次入列)
                _cross_both(h, code=code)
            await h.settle()
            assert len(h.published) == 6
            assert len(h.bot) == 3
            assert all("NH 規則・AH 規則" in text for text in h.bot)
            assert [text.split("｜")[1].split(" ")[1] for text in h.bot] == codes[:3]

            _cross_both(h, code="1101")  # worker 還活著:之後再發一組仍送出
            await h.settle()
            assert len(h.bot) == 4
        finally:
            await h.hub.close()

    async def test_oversized_merge_splits_into_batches(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """edge 8:合併文本 > 1900 字元 → 依 row 分批,批尾標 `(i/N)`,**不截斷**。"""
        h = _Harness(tmp_path, clock)
        h.attach_bot()
        rows = _long_rows()
        assert len(format_signal_group_text(rows)) > 1900  # 前提:治具真的造出超長文本

        await h.hub._send_discord(rows)

        assert len(h.bot) == 2
        assert h.bot[0].endswith(" (1/2)")
        assert h.bot[1].endswith(" (2/2)")
        assert all(len(text) <= 1900 for text in h.bot)
        assert rows[0]["rule_name"] in h.bot[0]
        assert rows[1]["rule_name"] in h.bot[1]  # 第二則沒有被截掉

    def test_split_batches_leave_room_for_tag(self) -> None:
        """T-3:每批「文本 + 摘要 + 批尾 ` (i/N)`」都要 ≤ 1900 —— 批數要切完才知道,
        所以 `_split_batches` 得先扣掉 `_BATCH_TAG_RESERVE` 再切。

        不預留的失效樣態:某一批剛好落在 (1884, 1900] 就會被 Discord 退回,而
        `test_oversized_merge_splits_into_batches` 的治具離上限太遠,永遠測不到。
        """
        rows = _tight_rows()
        suffix = _TIGHT_SUFFIX
        assert len(format_signal_group_text(rows)) + len(suffix) > 1900  # 前提:真的要分批
        # 前提:三則剛好貼在上限上 —— 沒有預留就會被貪婪收成一批
        assert len(format_signal_group_text(rows[:3])) + len(suffix) == 1900

        batches = hub_mod._split_batches(rows, suffix)

        total = len(batches)
        assert total > 1
        assert [row for batch in batches for row in batch] == rows  # 不漏不重不換序
        for index, batch in enumerate(batches, 1):
            text = f"{format_signal_group_text(batch)}{suffix} ({index}/{total})"
            assert len(text) <= 1900, f"第 {index}/{total} 批 {len(text)} 字超標"

    async def test_merged_message_counts_as_one_throttle_unit(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """T-4(SC-4「節流計 1 則」):同 tick 三則合併只吃掉一格額度。

        逐 row 計一次的話,`discord_per_min=1` 下第一組就只送得出第一則(或整組被
        擋),而合併的用意正是「一次穿多線不該把當分鐘的額度用光」。第二組(不同
        tick)被擋下則釘住額度**確實只有一格** —— 少了它,把節流整條拿掉也會綠。
        """
        _write_rules(
            tmp_path,
            [
                _rule("cdp_cross", "r-1-000", name="NL 規則", cdp_levels=["nl"]),
                _rule("cdp_cross", "r-1-001", name="CDP 規則", cdp_levels=["cdp"]),
                _rule("cdp_cross", "r-1-002", name="NH 規則", cdp_levels=["nh"]),
            ],
        )
        h = _Harness(tmp_path, clock, discord_per_min=1)
        h.attach_bot()
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330", "2317"])
            await h.settle()

            state = _state()  # 一筆 tick 同時穿 nl(70)/ cdp(75)/ nh(80)→ 三條規則各一則
            h.hub.on_tick("2330", _tick(69_000, time="10:00:00.100"), state)
            h.hub.on_tick("2330", _tick(86_000, cum=2, time="10:00:00.123"), state)
            h.hub.on_tick("2317", _tick(79_000, code="2317", time="10:00:05.100"), state)
            h.hub.on_tick("2317", _tick(80_500, code="2317", cum=2, time="10:00:06.000"), state)
            await h.settle()

            assert len(h.published) == 4  # W6:WS 逐 row,不受節流影響
            assert len(h.bot) == 1  # 合併那則送出,第二組(2317)被擋 → 額度確實只有一格
            assert "NL 規則・CDP 規則・NH 規則" in h.bot[0]
        finally:
            await h.hub.close()

    async def test_blocked_batch_is_logged_with_id(
        self, tmp_path: Path, clock: _Clock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """各批各計一次節流 → 後續批可能被擋下:缺角必須在 log 可見(帶 rows[0] 的 id)。"""
        h = _Harness(tmp_path, clock, discord_per_min=1)
        h.attach_bot()
        rows = _long_rows()

        with caplog.at_level(logging.WARNING, logger="copycat.server.signal_hub"):
            await h.hub._send_discord(rows)

        assert len(h.bot) == 1
        assert h.bot[0].endswith(" (1/2)")
        assert "sig-0" in caplog.text
        assert "1 批被節流擋下" in caplog.text

    async def test_single_row_text_unchanged(self, tmp_path: Path, clock: _Clock) -> None:
        """單則(含超長單則)照現行路徑走:不分批、不加 `(i/N)`、文案逐字不變。"""
        h = _Harness(tmp_path, clock)
        h.attach_bot()
        rows = _long_rows(n=1, pad=2000)

        await h.hub._send_discord(rows)

        assert h.bot == [format_signal_text(rows[0])]

    async def test_blocked_merged_message_is_logged_with_id(
        self, tmp_path: Path, clock: _Clock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """review C-5:未分批的合併訊息被節流擋下 = 一次吞掉整組 N 則。

        `_allow_discord` 自己那句 log 只說「本則」—— 合併之後「一則」已經不等於
        「一筆訊號」,缺角有多大、是哪一組,只有這裡記得下來(分批路徑早就有記)。
        """
        h = _Harness(tmp_path, clock, discord_per_min=1)
        h.attach_bot()
        rows = _long_rows(n=2, pad=0)  # 短文本 → 不分批,走「一則送出」那條路
        assert len(format_signal_group_text(rows)) <= 1900

        await h.hub._send_discord([rows[0]])  # 用掉這一分鐘唯一的額度
        with caplog.at_level(logging.WARNING, logger="copycat.server.signal_hub"):
            await h.hub._send_discord(rows)

        assert len(h.bot) == 1  # 合併那則整組被擋下
        assert "節流擋下合併 2 則" in caplog.text
        assert "sig-0" in caplog.text

    async def test_close_accounts_for_pending_row(
        self, tmp_path: Path, clock: _Clock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """review C-3:單槽 pending 那一則已經 `get()` 出來、還沒 `task_done()`。

        關機時 worker 被取消 → 它既沒送出也沒記帳:`_discord_queue.join()` 的計數
        永遠掛著一格,關機屏障(與測試的 `settle()`)從此吊死,而丟掉的是哪一則
        全無痕跡。
        """
        h = _Harness(tmp_path, clock)
        h.hub._discord_queue.put_nowait(_long_rows(n=1, pad=0)[0])
        h.hub._discord_pending = h.hub._discord_queue.get_nowait()  # 模擬 worker 的單槽

        with caplog.at_level(logging.INFO, logger="copycat.server.signal_hub"):
            await h.hub.close()

        assert h.hub._discord_pending is None
        await asyncio.wait_for(h.hub._discord_queue.join(), 1)
        assert "sig-0" in caplog.text


class TestNoDailyBarsSource:
    """N110:`daily_bars=None` = **配置上就沒有日 K 來源**(app 層無 stock engine)。

    改動前那條路是塞一個恆回空清單的替身,hub 把「配置上沒有」讀成「這一檔資料面
    沒有」—— 自選 50 檔就是 50 行「無已完成日 K,CDP 停用」WARNING,外加逐檔一格
    basis job(以及一個為了它而存在的 `basis_gap_secs=0` hack)。
    """

    async def test_request_basis_is_a_noop_without_source(
        self, tmp_path: Path, clock: _Clock, caplog: pytest.LogCaptureFixture
    ) -> None:
        h = _Harness(tmp_path, clock, bars=None, daily_bars=None)
        await h.hub.start()
        try:
            with caplog.at_level(logging.INFO):
                h.hub.on_watchlist(["2330", "2317", "2454"])
                await h.settle()
            assert h.hub._basis_cache == {}
            assert "CDP 停用" not in caplog.text
            assert caplog.text.count("CDP 基準:無日 K 來源") == 1
        finally:
            await h.hub.close()

    async def test_ticks_still_flow_without_a_daily_bars_source(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """CDP 停用不等於訊號鏈停用:非 CDP 規則照常發(XR-3 的既有語意不得回退)。"""
        h = _Harness(tmp_path, clock, bars=None, daily_bars=None)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            h.cross_nh(_state())
            await h.settle()
            assert [m["kind"] for m in h.published] == []  # CDP 無基準 → 不發
            assert h.hub.today_signals() == []
        finally:
            await h.hub.close()


class TestBasisWorker:
    async def test_staged_prefetch_swaps_in_on_rollover(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            assert _cache(h) == (_DATE, 80_000)  # 基準快照歸 hub 持有(SC-3)
            # stage1:盤前預抓次日基準(多一根 08-04 日 K → nh 由 80_000 變 95_000)
            h.bars.bars = [_BAR_A, _BAR_B]
            h.hub.on_rollover_pending(_NEXT)
            await h.settle()
            assert h.published == []  # 暫存不生效
            assert h.hub._staged_date == _NEXT
            assert h.hub._staged_cache["2330"] is not None
            assert h.hub._staged_cache["2330"]["nh"] == 95_000
            assert _cache(h) == (_DATE, 80_000)  # 當日快照未被暫存區汙染

            h.date = _NEXT
            clock.now = _dt.datetime(2026, 8, 5, 10, 0, 0)
            h.hub.on_rollover()
            assert _cache(h) == (_NEXT, 95_000)  # promote:整批換日別
            assert h.hub._staged_cache == {} and h.hub._staged_date is None
            state = _state()
            h.hub.on_tick("2330", _tick(94_000, trade_date=_NEXT), state)
            h.hub.on_tick("2330", _tick(95_500, cum=2, trade_date=_NEXT), state)
            await h.settle()
            assert [m["levels"] for m in h.published] == [["nh"]]
            assert h.published[0]["price"] == 95_500
        finally:
            await h.hub.close()

    async def test_rollover_without_prefetch_refetches(self, tmp_path: Path, clock: _Clock) -> None:
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            assert len(h.bars.calls) == 1

            h.bars.bars = [_BAR_A, _BAR_B]
            h.date = _NEXT
            clock.now = _dt.datetime(2026, 8, 5, 10, 0, 0)
            h.hub.on_rollover()  # stage1 沒跑過 → swap 失敗 → 清空重抓
            await h.settle()
            assert len(h.bars.calls) == 2
            assert _cache(h) == (_NEXT, 95_000)

            state = _state()
            h.hub.on_tick("2330", _tick(94_000, trade_date=_NEXT), state)
            h.hub.on_tick("2330", _tick(95_500, cum=2, trade_date=_NEXT), state)
            await h.settle()
            assert [m["levels"] for m in h.published] == [["nh"]]
        finally:
            await h.hub.close()

    async def test_staged_basis_never_reused_across_days(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """MFS-2 + CC-4:stage1/stage2 同步連發(快路徑)兩輪,第二輪不得沿用第一輪基準。

        劇本:`on_rollover_pending` 才剛把 job 排進佇列,`on_rollover` 就在同一輪 event
        loop 到了 → 暫存區還是空的 → swap 失敗走重抓(可接受,只是多抓一次)。**但**
        worker 隨後才把 stage1 的結果填進暫存區,那份就這樣留到下一輪換日 —— 下一次
        swap 會回 True 並把**舊日**基準當成當日基準用一整天,而且完全沒有錯誤訊號。
        """
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()

            # 第一輪換日:pending 與 rollover 之間沒有讓 worker 跑的機會
            h.bars.bars = [_BAR_A, _BAR_B]
            h.hub.on_rollover_pending(_NEXT)
            h.date = _NEXT
            clock.now = _dt.datetime(2026, 8, 5, 10, 0, 0)
            h.hub.on_rollover()
            await h.settle()  # 此刻 worker 才消化 stage1 的 job → 暫存區被填上 08-05 基準
            assert _cache(h) == (_NEXT, 95_000)

            state = _state()
            h.hub.on_tick("2330", _tick(94_000, trade_date=_NEXT), state)
            h.hub.on_tick("2330", _tick(95_500, cum=2, trade_date=_NEXT), state)
            await h.settle()
            assert [m["levels"] for m in h.published] == [["nh"]]  # _BAR_B 的 nh = 95_000
            h.published.clear()

            # 第二輪換日:同樣的快路徑。基準必須換成 _BAR_C 的(nh = 125_000)
            h.bars.bars = [_BAR_A, _BAR_B, _BAR_C]
            h.hub.on_rollover_pending(_THIRD)
            h.date = _THIRD
            clock.now = _dt.datetime(2026, 8, 6, 10, 0, 0)
            h.hub.on_rollover()
            await h.settle()
            assert _cache(h) == (_THIRD, 125_000), "hub 快照沿用了昨天的基準日"

            state2 = _state()
            h.hub.on_tick("2330", _tick(124_000, trade_date=_THIRD), state2)
            h.hub.on_tick("2330", _tick(125_500, cum=2, trade_date=_THIRD), state2)
            await h.settle()
            assert [m["levels"] for m in h.published] == [["nh"]], "沿用了昨天的 CDP 基準"
            assert h.published[0]["price"] == 125_500
        finally:
            await h.hub.close()

    async def test_staged_job_crash_keeps_today_basis(
        self, tmp_path: Path, clock: _Clock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A1:stage1(**次日**)的 job 崩掉,不得動到當日正在用的基準。

        worker 的 outer except 繞過 cache 直摸 detector 時,一則盤前預抓的例外會把
        今天剩下的 CDP 全部停掉;cache 還寫著正確值 → 之後任何 `_distribute` 都不會
        自癒,而畫面只顯示「這條規則今天都沒發」,零錯誤訊號。

        **落點契約不變,時點改了(X-2b)**:worker 級例外現在先走有限重試,超限
        (第 3 次)才落暫存區 —— 故等到 daily_bars 被打滿 4 次(當日 1 + staged 3)。
        """
        h = _Harness(tmp_path, clock, basis_retry_delay_secs=0.0)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()

            monkeypatch.setattr(hub_mod, "compute_cdp", _boom_cdp)
            h.hub.on_rollover_pending(_NEXT)
            await _wait_calls(h.bars, 4)
            await h.settle()

            assert _cache(h) == (_DATE, 80_000)  # 當日快照未被暫存區的例外動到
            # 崩掉的 staged job 落點必須是暫存區(日別符),不是當日 detector
            assert h.hub._staged_cache["2330"] is None
            h.cross_nh(_state())
            await h.settle()
            assert [m["levels"] for m in h.published] == [["nh"]], "當日 CDP 被次日的例外停掉了"
        finally:
            await h.hub.close()

    async def test_stale_job_crash_does_not_clobber_promoted_basis(
        self, tmp_path: Path, clock: _Clock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A1:換日前排下的當日 job 在 promote **之後**才崩,不得洗掉剛換上的基準。

        成功路徑早有日別尺(R18),例外路徑沒有 —— 同一個劇本只要 worker 這一則
        剛好炸掉,結果就從「丟棄」變成「整天沒有 CDP」。
        """
        gated = _GatedBars([_BAR_A])
        h = _Harness(tmp_path, clock, gated)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            gated.bars = [_BAR_A, _BAR_B]
            h.hub.on_rollover_pending(_NEXT)
            await h.settle()  # 暫存區備妥次日基準

            gate = asyncio.Event()
            gated.gate = gate
            # 換日前排下的當日 job(自選異動 / server 剛啟動),此刻卡在日 K 上
            h.hub.request_basis(["2330"])
            await asyncio.wait_for(gated.entered.wait(), 2)
            monkeypatch.setattr(hub_mod, "compute_cdp", _boom_cdp)

            h.date = _NEXT
            clock.now = _dt.datetime(2026, 8, 5, 10, 0, 0)
            h.hub.on_rollover()
            assert _cache(h) == (_NEXT, 95_000)

            gate.set()  # 舊 job 這時才崩
            await h.settle()

            assert _cache(h) == (_NEXT, 95_000), "過期 job 的例外洗掉了剛 promote 的快照"
            state = _state()
            h.hub.on_tick("2330", _tick(94_000, trade_date=_NEXT), state)
            h.hub.on_tick("2330", _tick(95_500, cum=2, trade_date=_NEXT), state)
            await h.settle()
            assert [m["levels"] for m in h.published] == [["nh"]], "當日基準被過期的例外洗掉"
        finally:
            await h.hub.close()

    async def test_stale_job_result_does_not_overwrite_promoted_basis(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """B3:同劇本但舊 job **成功**收工 —— 舊日別的結果一樣不得覆蓋 promote 的快照。

        成功路徑的日別尺(R18)現在改在 `_daily_bars` 之前也判一次,這條是它的迴歸鎖:
        判斷提前之後,「排隊時還新鮮、收工時已過期」這一格仍必須丟棄。
        """
        gated = _GatedBars([_BAR_A])
        h = _Harness(tmp_path, clock, gated)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            gated.bars = [_BAR_A, _BAR_B]
            h.hub.on_rollover_pending(_NEXT)
            await h.settle()

            gate = asyncio.Event()
            gated.gate = gate
            h.hub.request_basis(["2330"])
            await asyncio.wait_for(gated.entered.wait(), 2)

            h.date = _NEXT
            clock.now = _dt.datetime(2026, 8, 5, 10, 0, 0)
            h.hub.on_rollover()
            gated.bars = [_BAR_A]  # 舊 job 拿到的是舊資料(nh = 80_000)
            gate.set()
            await h.settle()

            assert _cache(h) == (_NEXT, 95_000), "過期 job 的結果覆蓋了 promote 的快照"
        finally:
            await h.hub.close()

    async def test_code_added_between_stages_gets_next_day_basis(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """A2:stage1 之後才加進自選的檔,也要進暫存區 —— 否則 promote 時它整批不在。

        失效樣態:那一檔隔天一整天沒有 CDP 基準(當日 job 會被日別尺丟棄),
        而畫面只會顯示「這檔今天沒發 CDP」。
        """
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            h.bars.bars = [_BAR_A, _BAR_B]
            h.hub.on_rollover_pending(_NEXT)
            await h.settle()

            h.hub.on_watchlist(["2330", "2317"])  # 盤前(stage1 之後)才加的自選
            await h.settle()
            assert h.hub._staged_cache.get("2317") is not None, "新加的檔沒有進暫存區"

            h.date = _NEXT
            clock.now = _dt.datetime(2026, 8, 5, 10, 0, 0)
            h.hub.on_rollover()
            assert _cache(h, "2317") == (_NEXT, 95_000)
        finally:
            await h.hub.close()

    async def test_promote_refetches_codes_missing_from_staged(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """A2:promote 之後要對「自選有、快照沒有」的差集補抓。

        stage1 排的 job 還沒 settle 換日就到了(快路徑)時,那些檔不在暫存區,
        promote 整批換上去等於把它們的基準**刪掉**,而且不會自癒。
        """
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            h.bars.bars = [_BAR_A, _BAR_B]
            h.hub.on_rollover_pending(_NEXT)
            await h.settle()

            h.hub.on_watchlist(["2330", "2317"])  # job 還在佇列裡,換日就到了
            h.date = _NEXT
            clock.now = _dt.datetime(2026, 8, 5, 10, 0, 0)
            h.hub.on_rollover()
            await h.settle()

            assert _cache(h, "2317") == (_NEXT, 95_000), "promote 漏掉的檔整天沒有基準"
        finally:
            await h.hub.close()

    async def test_daily_bars_failure_disables_cdp_only(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        h = _Harness(tmp_path, clock, _FakeBars([_BAR_A], error=True))
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            h.cross_nh(_state())
            await h.settle()
            assert h.published == []  # 基準 None → CDP 跳過

            h.lock_up(_state(upper=110_000, locked_up=True), code="2317")
            h.hub.on_watchlist(["2330", "2317"])
            await h.settle()
            h.lock_up(_state(upper=110_000, locked_up=True), code="2317")
            await h.settle()
            assert [m["kind"] for m in h.published] == ["limit_lock"]  # 其他 kind 照常
        finally:
            await h.hub.close()

    async def test_no_completed_bar_leaves_basis_none(self, tmp_path: Path, clock: _Clock) -> None:
        """只有今日 partial bar → 無「date < basis_date」的已完成 bar,CDP 停用不炸。"""
        h = _Harness(tmp_path, clock, _FakeBars([_bar(_DATE, 95_000, 85_000, 90_000)]))
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            h.cross_nh(_state())
            await h.settle()
            assert h.published == []
        finally:
            await h.hub.close()


class TestBasisRetry:
    """X-2b:例外(連線 / 傳輸層,暫時性)有限重試;資料面的空 bars 不重試。

    落 None 是**整天**的決定(當日不再重抓),而 basis sweep 逐檔間隔只有 0.2s ——
    一次連線抖動可以在數秒內把十幾檔的 CDP 停掉一整天,而畫面只是「規則沒發」。
    """

    async def test_transient_failure_retried_until_success(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        bars = _FlakyBars([_BAR_A], fail_times=1)
        h = _Harness(tmp_path, clock, bars, basis_retry_delay_secs=0.0)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await _wait_calls(bars, 2)
            await h.settle()
            assert _cache(h) == (_DATE, 80_000), "第一次失敗就把當天的 CDP 定死了"
            h.cross_nh(_state())
            await h.settle()
            assert [m["levels"] for m in h.published] == [["nh"]]
        finally:
            await h.hub.close()

    async def test_retry_capped_then_basis_none(self, tmp_path: Path, clock: _Clock) -> None:
        """連續失敗 = 不是抖動:重試上限後落 None 定格,不得無限重打 TC4。"""
        bars = _FakeBars([_BAR_A], error=True)
        h = _Harness(tmp_path, clock, bars, basis_retry_delay_secs=0.0)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await _wait_calls(bars, 3)
            await h.settle()
            assert _cache(h) == (_DATE, None)
            await asyncio.sleep(0.05)
            assert len(bars.calls) == 3, "重試沒有上限"
        finally:
            await h.hub.close()

    async def test_history_timeout_warns_without_traceback_and_still_retries(
        self, tmp_path: Path, clock: _Clock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """逾時走 `logger.warning`(無 traceback),**處置與其他例外完全相同**。

        `logger.exception` 對它零資訊量:堆疊每次都是同一條 `to_thread` → raise。
        盤前 basis sweep 逐檔 0.2s,TC4 忙窗一來就是幾十份 traceback,把真正該看的
        例外(型別錯 / 解析爆)整段沖掉 —— 而那正是 traceback 唯一有用的場合。
        """
        bars = _FakeBars([_BAR_A], error_exc=HistoryTimeoutError("first page not ready"))
        h = _Harness(tmp_path, clock, bars, basis_retry_delay_secs=0.0)
        await h.hub.start()
        try:
            with caplog.at_level(logging.WARNING):
                h.hub.on_watchlist(["2330"])
                await _wait_calls(bars, 3)
                await h.settle()
            assert len(bars.calls) == 3, "逾時的重試預算必須與其他例外相同"
            assert _cache(h) == (_DATE, None)
            assert "Traceback" not in caplog.text
            assert "逾時" in caplog.text
        finally:
            await h.hub.close()

    async def test_other_exception_keeps_the_traceback(
        self, tmp_path: Path, clock: _Clock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """逾時之外的例外照舊 `logger.exception` —— 逾時那條分支不得把整個 except 降級。"""
        bars = _FakeBars([_BAR_A], error_exc=ValueError("wrapper 內部型別錯"))
        h = _Harness(tmp_path, clock, bars, basis_retry_delay_secs=0.0)
        await h.hub.start()
        try:
            with caplog.at_level(logging.WARNING):
                h.hub.on_watchlist(["2330"])
                await _wait_calls(bars, 3)
                await h.settle()
            assert "Traceback" in caplog.text
        finally:
            await h.hub.close()

    async def test_empty_bars_not_retried(self, tmp_path: Path, clock: _Clock) -> None:
        """新上市無歷史日 K = 資料面的答案,重抓一百次也一樣 —— 不重試。"""
        bars = _FakeBars([])
        h = _Harness(tmp_path, clock, bars, basis_retry_delay_secs=0.0)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            assert _cache(h) == (_DATE, None)
            await asyncio.sleep(0.05)
            assert len(bars.calls) == 1, "空 bars 也重試 = 白打 TC4"
        finally:
            await h.hub.close()

    async def test_stale_retry_job_discarded_after_rollover(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """重試 job 帶原 basis_date 走同一條佇列 → 跨日後由 `_stale` 丟棄,不打 TC4。"""
        bars = _FakeBars([_BAR_A], error=True)
        h = _Harness(tmp_path, clock, bars, basis_retry_delay_secs=0.1)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await _wait_calls(bars, 1)
            await h.settle()
            h.date = _NEXT  # 重試還沒入列就換日了
            await asyncio.sleep(0.25)
            await h.settle()
            assert len(bars.calls) == 1, "過期的重試 job 仍去打了 TC4"
        finally:
            await h.hub.close()

    async def test_reschedule_cancels_orphaned_timer(self, tmp_path: Path, clock: _Clock) -> None:
        """同鍵兩筆 job 先後失敗(rollover 差集補抓 race 的形)→ 第二次排程必須取消
        第一支 timer。孤兒 timer 照樣醒來:重試預算被雙倍燒掉、TC4 被多打一次,而且
        它 pop 掉 dict 條目後,close() 再也看不到真正在途的那支。"""
        bars = _FakeBars([_BAR_A], error=True)
        h = _Harness(tmp_path, clock, bars, basis_retry_delay_secs=0.15)
        await h.hub.start()
        try:
            h.hub.request_basis(["2330"])
            h.hub.request_basis(["2330"])  # 同鍵第二筆:重試在途時又排了新 job
            await _wait_calls(bars, 2)
            await asyncio.sleep(0.4)  # 讓在途 timer 全數到期
            await h.settle()
            # 兩筆初始 + 一次重試(tries 已達上限)= 3;孤兒 timer 也醒的話會是 4
            assert len(bars.calls) == 3, "孤兒 timer 也醒來重打了 TC4"
        finally:
            await h.hub.close()

    async def test_drop_code_cancels_pending_retry(self, tmp_path: Path, clock: _Clock) -> None:
        """移出自選後在途重試必須取消:醒來的重試不只白打 TC4,`_basis_failed` 還會把
        `_drop_code` 刻意清掉的 cache 條目寫回去(復活成 (date, None))。"""
        bars = _FakeBars([_BAR_A], error=True)
        h = _Harness(tmp_path, clock, bars, basis_retry_delay_secs=0.1)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await _wait_calls(bars, 1)
            h.hub.on_watchlist([])  # 重試在途時移出
            await asyncio.sleep(0.3)
            await h.settle()
            assert len(bars.calls) == 1, "移出自選後重試仍去打了 TC4"
            assert "2330" not in h.hub._basis_cache, "被清掉的 cache 條目又被重試復活"
        finally:
            await h.hub.close()

    async def test_rollover_prunes_pending_handles_and_staged_counters(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """換日清舊要一次清齊:舊日別與 staged 的在途 timer 取消(醒來也只會被 `_stale`
        丟掉,白走一趟換日最忙窗的佇列);staged 計數不得帶進新的一天 —— `_staged_date`
        此刻歸 None,那些鍵再也不會被讀到,留著就是 `on_rollover` 自己要防的慢性洩漏。"""
        bars = _FakeBars([_BAR_A], error=True)
        h = _Harness(tmp_path, clock, bars, basis_retry_delay_secs=5.0)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await _wait_calls(bars, 1)  # 當日 job 失敗 → 非 staged timer 在途
            h.hub.on_rollover_pending(_NEXT)
            await _wait_calls(bars, 2)  # staged job 失敗 → staged timer 在途
            await h.settle()
            h.date = _NEXT
            h.hub.on_rollover()
            assert h.hub._retry_handles == {}, "舊日別 / staged 的在途 timer 未取消"
            assert h.hub._basis_retries == {}, "staged 計數被帶進了新的一天"
        finally:
            await h.hub.close()


class TestBookPath:
    async def test_book_open_after_lock(self, tmp_path: Path, clock: _Clock) -> None:
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            h.lock_up(_state(upper=110_000, locked_up=True))
            await h.settle()
            assert [m["kind"] for m in h.published] == ["limit_lock"]

            clock.advance(700)  # 讓 limit_open 自己的冷卻桶無關,單純推進時鐘
            h.hub.on_book("2330", _state(upper=110_000))  # ask 限價檔重現 → 打開
            await h.settle()
            assert [m["kind"] for m in h.published] == ["limit_lock", "limit_open"]
            assert h.published[1]["price"] == 110_000
            assert h.published[1]["time"] == "10:11:40"
        finally:
            await h.hub.close()

    async def test_on_tick_exception_is_swallowed(self, tmp_path: Path, clock: _Clock) -> None:
        """publish 炸掉不得汙染 engine 主路徑(design §4.1)。"""

        def _boom(_msg: dict) -> None:
            raise RuntimeError("ws 壞了")

        h = _Harness(tmp_path, clock)
        h.hub._publish = _boom  # type: ignore[assignment]
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            h.cross_nh(_state())  # 不得往外拋
            await h.settle()
        finally:
            await h.hub.close()


class TestRuleEngine:
    """SC-2/3/5:每條規則一顆 detector;design「邊界」逐 edge。"""

    async def test_zero_rules_no_events(self, tmp_path: Path, clock: _Clock) -> None:
        """邊界 1:規則 0 條 → 評估迴圈零次,不炸也不發。"""
        _write_rules(tmp_path, [])
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            assert h.hub.rules() == []
            h.hub.on_watchlist(["2330"])
            await h.settle()
            h.cross_nh(_state())
            h.hub.on_book("2330", _state(upper=110_000))
            await h.settle()
            assert h.published == []
            assert h.rows() == []
        finally:
            await h.hub.close()

    async def test_empty_rules_file_not_remigrated(self, tmp_path: Path, clock: _Clock) -> None:
        """邊界 1 的另一半:空陣列 ≠ 缺檔 —— 刪光規則後重啟不得復活四條預設。"""
        _write_rules(tmp_path, [])
        assert _Harness(tmp_path, clock).hub.rules() == []
        assert _Harness(tmp_path, clock).hub.rules() == []
        assert load_rules(tmp_path / _RULES_FILE) == []

    async def test_two_rules_same_kind_both_fire(self, tmp_path: Path, clock: _Clock) -> None:
        """邊界 2:同 kind 兩規則同 tick → 兩則事件,id 因 rule 段不撞。

        Discord 那一則是**事前標為該變**的斷言(SC-4):同 (code, time) 相鄰兩 row 現在
        合成一則,kind 文案相同 → 去重成一段,兩條規則名以「・」串接。WS / jsonl 仍逐 row。
        """
        _write_rules(tmp_path, [_rule("cdp_cross", "r-1-000"), _rule("cdp_cross", "r-1-001")])
        h = _Harness(tmp_path, clock)
        h.attach_bot()
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            h.cross_nh(_state())
            await h.settle()
            assert [m["rule_id"] for m in h.published] == ["r-1-000", "r-1-001"]
            assert len({m["id"] for m in h.published}) == 2
            assert len(h.rows()) == 2
            assert h.bot == [
                "🔔 突破 CDP NH(壓力・第1次)｜台積電 2330｜80.50｜10:00:00"
                "｜cdp_cross-r-1-000・cdp_cross-r-1-001"
            ]
        finally:
            await h.hub.close()

    async def test_upsert_preserves_other_rules_state(self, tmp_path: Path, clock: _Clock) -> None:
        """邊界 3:被編輯那顆 detector 重建歸零,其他顆的 cooldown 原樣保留。

        兩條規則都把冷卻設到一天:第一次穿越後兩顆都被自己的冷卻壓著;編輯 A 之後
        只有 A 能再發。順帶釘 `_seed_slot` —— 新 detector 沒被餵基準的話這裡零事件。
        """
        rules = [
            # dwell 0 = W3 舊語意(離線即解除),與本測試原本的 rearm_ticks 0 意圖一致;
            # 這個 dict 之後直接餵進 upsert_rule,params 必須是完整的精確鍵集合。
            _rule(
                "cdp_cross",
                "r-1-000",
                cooldown_secs=86_400,
                params={"rearm_ticks": 0, "rearm_dwell_secs": 0},
            ),
            _rule(
                "cdp_cross",
                "r-1-001",
                cooldown_secs=86_400,
                params={"rearm_ticks": 0, "rearm_dwell_secs": 0},
            ),
        ]
        _write_rules(tmp_path, rules)
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            h.cross_nh(_state())
            await h.settle()
            assert [m["rule_id"] for m in h.published] == ["r-1-000", "r-1-001"]
            h.published.clear()

            await h.hub.upsert_rule({**rules[0], "name": "改過的 A"}, rule_id="r-1-000")

            state = _state()
            h.hub.on_tick("2330", _tick(79_000, cum=3), state)  # 新 detector:首 tick 只初始化
            h.hub.on_tick("2330", _tick(80_500, cum=4), state)
            await h.settle()
            assert [m["rule_id"] for m in h.published] == ["r-1-000"]
            assert h.published[0]["rule_name"] == "改過的 A"
            assert h.published[0]["touch_count"] == 1  # 歸零(B 那顆若被波及會是 2)
        finally:
            await h.hub.close()

    async def test_cdp_levels_subset(self, tmp_path: Path, clock: _Clock) -> None:
        """邊界 4:規則只訂 AH → hub 只餵那條線,detector 認不得 nh 就不會發。"""
        _write_rules(tmp_path, [_rule("cdp_cross", "r-1-000", cdp_levels=["ah"])])
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            assert h.hub._slots["r-1-000"].detector._basis["2330"] == {"ah": 85_000}

            h.cross_nh(_state())
            await h.settle()
            assert h.published == []

            state = _state()
            h.hub.on_tick("2330", _tick(84_000, cum=3), state)
            h.hub.on_tick("2330", _tick(85_500, cum=4), state)
            await h.settle()
            assert [m["levels"] for m in h.published] == [["ah"]]
        finally:
            await h.hub.close()

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({**_rule("cdp_cross", "x"), "kind": "nope"}, id="kind"),
            pytest.param(_rule("cdp_cross", "x", name="   "), id="blank-name"),
            pytest.param(_rule("cdp_cross", "x", name="cdp_cross-r-1-000"), id="dup-name"),
            pytest.param(_rule("cdp_cross", "x", cooldown_secs=5), id="cooldown-low"),
            pytest.param(_rule("cdp_cross", "x", cdp_levels=[]), id="levels-empty"),
            pytest.param(_rule("cdp_cross", "x", cdp_levels=["zz"]), id="levels-unknown"),
            pytest.param(_rule("cdp_cross", "x", params={"rearm_ticks": 999}), id="param-range"),
            pytest.param(
                _rule("cdp_cross", "x", params={"rearm_ticks": 5, "bogus": 1}), id="param-extra"
            ),
            pytest.param(_rule("surge_crash", "x", params={"pct": 2.0}), id="param-missing"),
            pytest.param(_rule("limit_lock", "x", cdp_levels=["ah"]), id="levels-on-non-cdp"),
        ],
    )
    async def test_invalid_payload_rejected_and_state_untouched(
        self, tmp_path: Path, clock: _Clock, payload: dict[str, Any]
    ) -> None:
        """邊界 6:語意驗證單一定義在 normalize_rule;拒收時記憶體與磁碟都不得動。"""
        _write_rules(tmp_path, [_rule("cdp_cross", "r-1-000")])
        h = _Harness(tmp_path, clock)
        before = h.hub.rules()
        with pytest.raises(RuleError, match="INVALID_RULE"):
            await h.hub.upsert_rule(payload)
        assert h.hub.rules() == before
        assert load_rules(tmp_path / _RULES_FILE) == before

    async def test_limit_rule_latch_isolated(self, tmp_path: Path, clock: _Clock) -> None:
        """邊界 7:latch 在各自 detector 內閉合 —— 兩條鎖板規則各發一對 lock/open。"""
        _write_rules(tmp_path, [_rule("limit_lock", "r-1-000"), _rule("limit_lock", "r-1-001")])
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            h.lock_up(_state(upper=110_000, locked_up=True))
            await h.settle()
            assert [(m["rule_id"], m["kind"]) for m in h.published] == [
                ("r-1-000", "limit_lock"),
                ("r-1-001", "limit_lock"),
            ]
            h.hub.on_book("2330", _state(upper=110_000))
            await h.settle()
            assert [(m["rule_id"], m["kind"]) for m in h.published][2:] == [
                ("r-1-000", "limit_open"),
                ("r-1-001", "limit_open"),
            ]
        finally:
            await h.hub.close()

    async def test_migration_defaults(self, tmp_path: Path, clock: _Clock) -> None:
        """邊界 8:缺規則檔 + 缺 legacy 檔 → 每 kind 一條、全開,並立刻落檔。"""
        h = _Harness(tmp_path, clock)
        rules = h.hub.rules()
        # surge_pullback 種子是兩張卡(1% / 2%,spec #174)
        assert [r["kind"] for r in rules] == [
            "cdp_cross",
            "surge_crash",
            "surge_pullback",
            "surge_pullback",
            "vol_burst",
            "limit_lock",
        ]
        assert all(r["enabled"] for r in rules)
        assert all(r["notify_discord"] for r in rules)
        assert load_rules(tmp_path / _RULES_FILE) == rules

    async def test_migration_reads_legacy_flags(self, tmp_path: Path, clock: _Clock) -> None:
        """SC-4:舊 `signals_enabled.json` 的關閉態要跟著遷移過來(缺鍵 = fail-open)。"""
        (tmp_path / "signals_enabled.json").write_text(
            json.dumps({"vol_burst": False}), encoding="utf-8"
        )
        h = _Harness(tmp_path, clock)
        assert {r["kind"]: r["enabled"] for r in h.hub.rules()} == {
            "cdp_cross": True,
            "surge_crash": True,
            "surge_pullback": True,  # 晚於開關檔時代 → 恆走缺鍵 fail-open
            "vol_burst": False,
            "limit_lock": True,
        }

    async def test_bad_rules_file_raises_on_construct(self, tmp_path: Path, clock: _Clock) -> None:
        """R9:壞規則檔在建構時就往外拋(app 的 `_boot` 傘接手 → hub None + 503)。

        靜默套預設會在盤中無預警改變推播行為,所以這裡要的正是「大聲」。
        """
        (tmp_path / _RULES_FILE).write_text("{壞檔", encoding="utf-8")
        with pytest.raises(RuleError, match="INVALID_RULE"):
            _Harness(tmp_path, clock)

    async def test_watchlist_removal_stops_all_rules(self, tmp_path: Path, clock: _Clock) -> None:
        """SC-5:移出自選 → 逐 slot drop + basis / staged 雙 cache 都不得留下該檔。"""
        _write_rules(tmp_path, [_rule("cdp_cross", "r-1-000"), _rule("cdp_cross", "r-1-001")])
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            h.hub.on_rollover_pending(_NEXT)  # 讓暫存區也有這檔
            await h.settle()
            h.cross_nh(_state())
            await h.settle()
            assert len(h.published) == 2
            assert "2330" in h.hub._basis_cache
            assert "2330" in h.hub._staged_cache

            h.hub.on_watchlist([])
            assert "2330" not in h.hub._basis_cache
            assert "2330" not in h.hub._staged_cache
            assert all("2330" not in s.detector._basis for s in h.hub._slots.values())

            h.cross_nh(_state())
            await h.settle()
            assert len(h.published) == 2  # 兩顆都停發
        finally:
            await h.hub.close()

    async def test_one_rule_exception_does_not_stop_others(
        self, tmp_path: Path, clock: _Clock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """R1:per-rule try/except —— 一條規則炸掉只跳過它自己,其餘照評。"""
        _write_rules(tmp_path, [_rule("cdp_cross", "r-1-000"), _rule("cdp_cross", "r-1-001")])
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()

            def _boom(*_args: Any, **_kwargs: Any) -> list:
                raise RuntimeError("這條規則壞了")

            h.hub._slots["r-1-000"].detector.evaluate = _boom  # type: ignore[method-assign]
            with caplog.at_level(logging.ERROR, logger="copycat.server.signal_hub"):
                h.cross_nh(_state())
                await h.settle()

            assert [m["rule_id"] for m in h.published] == ["r-1-001"]
            assert "cdp_cross-r-1-000" in caplog.text  # log 要指得出是哪條規則
        finally:
            await h.hub.close()

    async def test_notify_discord_false_skips_discord_only(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """SC-2:`notify_discord` 只擋 Discord,WS 與 jsonl 這條真相源照走。"""
        _write_rules(
            tmp_path,
            [
                _rule("cdp_cross", "r-1-000", name="要通知"),
                _rule("cdp_cross", "r-1-001", name="不通知", notify_discord=False),
            ],
        )
        h = _Harness(tmp_path, clock)
        h.attach_bot()
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            h.cross_nh(_state())
            await h.settle()
            assert len(h.published) == 2
            assert len(h.rows()) == 2
            assert h.bot == [h.bot[0]] and h.bot[0].endswith("｜要通知")
        finally:
            await h.hub.close()


class TestDiscordText:
    def _row(self, **over: Any) -> dict[str, Any]:
        row: dict[str, Any] = {
            "kind": "vol_burst",
            "code": "2330",
            "name": "台積電",
            "price": 100_000,
            "time": "10:00:00",
            "pct": 3.2,
        }
        row.update(over)
        return row

    def test_rule_name_appended(self) -> None:
        """R14b:同 kind 多規則在 Discord 要分得出是哪一條發的。"""
        assert format_signal_text(self._row(rule_name="爆量-緊")).endswith("｜爆量-緊")

    def test_legacy_row_without_rule_name(self) -> None:
        """升級當日的舊 jsonl row 沒有 rule_name → 不得留下空的分隔符。"""
        assert format_signal_text(self._row()).endswith("10:00:00")

    def test_group_text_dedups_rule_name_across_kinds(self) -> None:
        """SC-4(T-2):同一條規則同一 tick 觸發兩種 kind → kind 兩段、規則名只印一次。

        kind 文案去重有專測(`_merge_rules` 刻意用兩條不同線),規則名去重沒有:
        「爆拉…・爆量…｜當沖組・當沖組」在 Discord 上是純噪音,而任何測試都不會紅。
        """
        rows = [
            self._row(kind="surge", pct=2.5, rule_name="當沖組"),
            self._row(kind="vol_burst", pct=3.0, rule_name="當沖組"),
        ]
        text = format_signal_group_text(rows)
        assert "爆拉 +2.50%・爆量 3.0 倍" in text  # kind 不同 → 兩段都在
        assert text.count("當沖組") == 1

    def test_group_text_of_single_row_is_verbatim(self) -> None:
        """SC-4:單則走合併版仍**逐字**等於單則版 —— 絕大多數訊號走的正是這條路。"""
        assert format_signal_group_text([self._row(rule_name="爆量-緊")]) == format_signal_text(
            self._row(rule_name="爆量-緊")
        )
        assert format_signal_group_text([self._row()]) == format_signal_text(self._row())


class TestGroupSuffix:
    """同群摘要(group-grid SC-1/2)。

    摘要在 **Discord worker** 組(離熱路徑),所以 quotes 取的是「發送當下」的快照 ——
    這裡逐項釘格式與降級,因為它的失效樣態全是靜默的:排序反了只是「看起來怪」、
    例外沒接住則整則通知消失(而 WS/jsonl 有,對照時最容易被當成 Discord 掛了)。
    """

    async def test_end_to_end_text_appends_summary(self, tmp_path: Path, clock: _Clock) -> None:
        """逐字:`format_signal_text` 之後接摘要,WS/jsonl payload 零改。"""
        wl = _Watch(
            groups=[{"name": "半導體", "codes": ["2330", "2454", "2317"]}],
            quotes={"2330": ("台積電", 1.5), "2454": ("聯發科", -3.2), "2317": ("鴻海", 0.8)},
        )
        h = _Harness(tmp_path, clock, wl=wl)
        h.attach_bot()
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330", "2454", "2317"])
            await h.settle()
            h.cross_nh(_state())
            await h.settle()

            assert len(h.bot) == 1
            assert h.bot[0].endswith("｜同群 半導體:2454聯發科 -3.2%、2317鴻海 +0.8%")
            assert h.bot[0].startswith(format_signal_text(h.published[0]))
            # WS / jsonl 零改動:摘要是 Discord 專屬
            assert set(h.published[0]) == _SIGNAL_KEYS
            assert all("同群" not in json.dumps(r, ensure_ascii=False) for r in h.rows())
        finally:
            await h.hub.close()

    async def test_fallback_webhook_gets_same_summary(self, tmp_path: Path, clock: _Clock) -> None:
        """bot 未 ready 走 webhook —— 兩層是同一段文字(design §4.3)。"""
        wl = _Watch(
            groups=[{"name": "半導體", "codes": ["2330", "2317"]}],
            quotes={"2330": ("台積電", 1.5), "2317": ("鴻海", 0.8)},
        )
        h = _Harness(tmp_path, clock, wl=wl)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330", "2317"])
            await h.settle()
            h.cross_nh(_state())
            await h.settle()
            # B3-b:`fallback == [fallback[0]]` 讀起來像在比內容,實際只釘了「長度 1」
            # 而且空 list 會炸 IndexError 而不是失敗訊息 —— 意圖直接寫出來
            assert len(h.fallback) == 1
            assert h.fallback[0].endswith("｜同群 半導體:2317鴻海 +0.8%")
        finally:
            await h.hub.close()

    async def test_not_injected_means_no_summary(self, tmp_path: Path, clock: _Clock) -> None:
        """兩 fn 未注入(預設 None)→ 摘要停用,文字與規則化之前逐字相同。"""
        h = _Harness(tmp_path, clock)
        h.attach_bot()
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            h.cross_nh(_state())
            await h.settle()
            assert h.bot[0] == format_signal_text(h.published[0])
        finally:
            await h.hub.close()

    def _suffix(self, tmp_path: Path, clock: _Clock, wl: _Watch, code: str = "2330") -> str:
        h = _Harness(tmp_path, clock, wl=wl)
        h.hub.on_watchlist(sorted({c for g in wl.groups for c in g["codes"]} | {code}))
        return h.hub._group_suffix({"code": code})

    def test_edge1_first_group_containing_code_wins(self, tmp_path: Path, clock: _Clock) -> None:
        """edge 1:一檔可屬多群組 → 取**群組序**第一個含它的(不是最大的、不是最後的)。"""
        wl = _Watch(
            groups=[
                {"name": "A", "codes": ["2330", "2317"]},
                {"name": "B", "codes": ["2330", "2454"]},
            ],
            quotes={"2330": ("台積電", 1.0), "2317": ("鴻海", 2.0), "2454": ("聯發科", 3.0)},
        )
        assert self._suffix(tmp_path, clock, wl) == "｜同群 A:2317鴻海 +2.0%"

    def test_edge2_solo_group_has_no_summary(self, tmp_path: Path, clock: _Clock) -> None:
        """edge 2:群組只有觸發者自己 → 無「其他成員」→ 不附(不留空的分隔符)。"""
        wl = _Watch(
            groups=[{"name": "獨", "codes": ["2330"]}],
            quotes={"2330": ("台積電", 1.0)},
        )
        assert self._suffix(tmp_path, clock, wl) == ""

    def test_edge4_ungrouped_code_has_no_summary(self, tmp_path: Path, clock: _Clock) -> None:
        """edge 4:自選內但不屬任何群組(未分組是衍生桶不是群組)→ 不附。"""
        wl = _Watch(
            groups=[{"name": "A", "codes": ["2317", "2454"]}],
            quotes={"2330": ("台積電", 1.0), "2317": ("鴻海", 2.0), "2454": ("聯發科", 3.0)},
        )
        assert self._suffix(tmp_path, clock, wl) == ""

    def test_edge3_over_five_takes_top4_and_total_tail(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """edge 3:成員總數(含觸發者)> 5 → |漲跌幅| 前 4 + 尾綴總數(N = **總數**)。"""
        wl = _Watch(
            groups=[{"name": "A", "codes": ["2330", "2317", "2454", "3008", "2308", "1301"]}],
            quotes={
                "2330": ("台積電", 0.5),
                "2317": ("鴻海", 1.0),
                "2454": ("聯發科", -4.0),
                "3008": ("大立光", 3.0),
                "2308": ("台達電", -2.0),
                "1301": ("台塑", 5.0),
            },
        )
        assert self._suffix(tmp_path, clock, wl) == (
            "｜同群 A:1301台塑 +5.0%、2454聯發科 -4.0%、3008大立光 +3.0%、2308台達電 -2.0%、…共 6 檔"
        )

    def test_exactly_five_shows_all_four_without_tail(self, tmp_path: Path, clock: _Clock) -> None:
        """邊界另一側:總數 5(其他 4 檔)剛好全印 → **不得**出現「…共 5 檔」。"""
        wl = _Watch(
            groups=[{"name": "A", "codes": ["2330", "2317", "2454", "3008", "2308"]}],
            quotes={
                "2330": ("台積電", 0.5),
                "2317": ("鴻海", 1.0),
                "2454": ("聯發科", 2.0),
                "3008": ("大立光", 3.0),
                "2308": ("台達電", 4.0),
            },
        )
        assert self._suffix(tmp_path, clock, wl) == (
            "｜同群 A:2308台達電 +4.0%、3008大立光 +3.0%、2454聯發科 +2.0%、2317鴻海 +1.0%"
        )

    def test_edge7_missing_quote_shows_dash_and_sorts_last(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """edge 7:quotes 讀不到(未訂閱瞬間)→ `-`,且排在有行情的之後。

        名稱同時缺 → 只印代碼:硬拼一個空字串會留下 `2317 ` 這種尾隨空白。
        """
        wl = _Watch(
            groups=[{"name": "A", "codes": ["2330", "2317", "2454"]}],
            quotes={"2330": ("台積電", 1.0), "2454": ("聯發科", 0.1)},
        )
        assert self._suffix(tmp_path, clock, wl) == "｜同群 A:2454聯發科 +0.1%、2317 -"

    def test_explicit_none_chg_sorts_last(self, tmp_path: Path, clock: _Clock) -> None:
        """有 meta 但無行情(chg None)也一樣排最後 —— 排序鍵第一位是「有沒有值」。"""
        wl = _Watch(
            groups=[{"name": "A", "codes": ["2330", "2317", "2454"]}],
            quotes={"2330": ("台積電", 1.0), "2317": ("鴻海", None), "2454": ("聯發科", 0.1)},
        )
        assert self._suffix(tmp_path, clock, wl) == "｜同群 A:2454聯發科 +0.1%、2317鴻海 -"

    def test_groups_follow_watchlist_changes(self, tmp_path: Path, clock: _Clock) -> None:
        """SC-2:群組結構改了(建群 / 改名 / 移成員)→ 下一則摘要跟著變。"""
        wl = _Watch(
            groups=[{"name": "舊", "codes": ["2330", "2317"]}],
            quotes={"2330": ("台積電", 1.0), "2317": ("鴻海", 2.0), "2454": ("聯發科", 3.0)},
        )
        h = _Harness(tmp_path, clock, wl=wl)
        h.hub.on_watchlist(["2330", "2317"])
        assert h.hub._group_suffix({"code": "2330"}) == "｜同群 舊:2317鴻海 +2.0%"

        wl.groups = [{"name": "新", "codes": ["2330", "2454"]}]
        h.hub.on_watchlist(["2330", "2454"])
        assert h.hub._group_suffix({"code": "2330"}) == "｜同群 新:2454聯發科 +3.0%"

    def test_groups_fn_failure_keeps_previous_groups(
        self, tmp_path: Path, clock: _Clock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """自選檔讀取失敗 → 保舊值 + log。

        清空才是危險的那一邊:membership 更新照走,但摘要會**永久**消失一整天,
        而畫面上完全看不出來(Discord 只是少了一段尾巴)。
        """
        wl = _Watch(
            groups=[{"name": "A", "codes": ["2330", "2317"]}],
            quotes={"2330": ("台積電", 1.0), "2317": ("鴻海", 2.0)},
        )
        h = _Harness(tmp_path, clock, wl=wl)
        h.hub.on_watchlist(["2330", "2317"])
        wl.groups_error = True
        with caplog.at_level(logging.WARNING, logger="copycat.server.signal_hub"):
            h.hub.on_watchlist(["2330", "2317", "2454"])
        assert h.hub._watch == {"2330", "2317", "2454"}  # membership 照更新
        assert h.hub._group_suffix({"code": "2330"}) == "｜同群 A:2317鴻海 +2.0%"
        assert caplog.text != ""

    async def test_quotes_failure_degrades_to_empty_suffix_not_lost_signal(
        self, tmp_path: Path, clock: _Clock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """摘要組裝任何例外 → 空字串 + log,訊號本身照送(摘要是裝飾不是內容)。"""
        wl = _Watch(
            groups=[{"name": "A", "codes": ["2330", "2317"]}],
            quotes={"2330": ("台積電", 1.0), "2317": ("鴻海", 2.0)},
        )
        wl.quotes_error = True
        h = _Harness(tmp_path, clock, wl=wl)
        h.attach_bot()
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330", "2317"])
            await h.settle()
            with caplog.at_level(logging.ERROR, logger="copycat.server.signal_hub"):
                h.cross_nh(_state())
                await h.settle()
            assert h.bot == [format_signal_text(h.published[0])]
            assert len(h.rows()) == 1
            assert caplog.text != ""
        finally:
            await h.hub.close()

    async def test_notify_gate_still_blocks_discord_only(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """摘要接上去之後,`notify_discord=False` 仍然只擋 Discord(gate 未被繞過)。"""
        _write_rules(
            tmp_path,
            [
                _rule("cdp_cross", "r-1-000", name="要通知"),
                _rule("cdp_cross", "r-1-001", name="不通知", notify_discord=False),
            ],
        )
        wl = _Watch(
            groups=[{"name": "A", "codes": ["2330", "2317"]}],
            quotes={"2330": ("台積電", 1.0), "2317": ("鴻海", 2.0)},
        )
        h = _Harness(tmp_path, clock, wl=wl)
        h.attach_bot()
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330", "2317"])
            await h.settle()
            h.cross_nh(_state())
            await h.settle()
            assert len(h.published) == 2
            assert len(h.rows()) == 2
            assert h.bot == [
                "🔔 突破 CDP NH(壓力・第1次)｜台積電 2330｜80.50｜10:00:00｜要通知"
                "｜同群 A:2317鴻海 +2.0%"
            ]
        finally:
            await h.hub.close()


class TestRulesCrud:
    async def test_create_assigns_new_id_persists_and_is_live(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        _write_rules(tmp_path, [_rule("limit_lock", "r-1-000")])
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            created = await h.hub.upsert_rule(_rule("cdp_cross", "客戶端亂填的", name="新 CDP"))
            assert created["id"] not in {"客戶端亂填的", "r-1-000"}
            assert [r["id"] for r in h.hub.rules()] == ["r-1-000", created["id"]]
            assert load_rules(tmp_path / _RULES_FILE) == h.hub.rules()

            h.cross_nh(_state())  # 熱重載:新規則立刻生效(基準由 _seed_slot 補上)
            await h.settle()
            assert [m["rule_id"] for m in h.published] == [created["id"]]
        finally:
            await h.hub.close()

    async def test_ids_not_recycled_after_delete(self, tmp_path: Path, clock: _Clock) -> None:
        """R12:id 走單調計數 —— 刪掉再新增不得撞上已存 jsonl 的舊 id。"""
        h = _Harness(tmp_path, clock)
        first = await h.hub.upsert_rule(_rule("limit_lock", "x", name="A"))
        await h.hub.delete_rule(first["id"])
        second = await h.hub.upsert_rule(_rule("limit_lock", "x", name="B"))
        assert second["id"] != first["id"]

    async def test_put_edits_in_place_and_hot_reloads(self, tmp_path: Path, clock: _Clock) -> None:
        _write_rules(tmp_path, [_rule("cdp_cross", "r-1-000"), _rule("limit_lock", "r-1-001")])
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            await h.hub.upsert_rule(
                _rule("cdp_cross", "r-1-000", cdp_levels=["ah"]), rule_id="r-1-000"
            )
            assert [r["id"] for r in h.hub.rules()] == ["r-1-000", "r-1-001"]  # 位置不變
            assert h.hub._slots["r-1-000"].detector._basis["2330"] == {"ah": 85_000}

            h.cross_nh(_state())  # nh 已不在規則的線集合
            await h.settle()
            assert h.published == []
        finally:
            await h.hub.close()

    async def test_put_unknown_id_raises_not_found(self, tmp_path: Path, clock: _Clock) -> None:
        h = _Harness(tmp_path, clock)
        with pytest.raises(RuleError, match="RULE_NOT_FOUND"):
            await h.hub.upsert_rule(_rule("limit_lock", "nope", name="X"), rule_id="nope")

    async def test_delete_unknown_id_raises_not_found(self, tmp_path: Path, clock: _Clock) -> None:
        h = _Harness(tmp_path, clock)
        with pytest.raises(RuleError, match="RULE_NOT_FOUND"):
            await h.hub.delete_rule("nope")

    async def test_delete_removes_slot_and_persists(self, tmp_path: Path, clock: _Clock) -> None:
        _write_rules(tmp_path, [_rule("cdp_cross", "r-1-000"), _rule("limit_lock", "r-1-001")])
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()
            await h.hub.delete_rule("r-1-000")
            assert [r["id"] for r in h.hub.rules()] == ["r-1-001"]
            assert load_rules(tmp_path / _RULES_FILE) == h.hub.rules()

            h.cross_nh(_state())
            await h.settle()
            assert h.published == []
        finally:
            await h.hub.close()

    async def test_max_rules_enforced_on_create_only(self, tmp_path: Path, clock: _Clock) -> None:
        """R11:上限只擋新增 —— 編輯既有規則不得因為「已經滿了」而被拒。"""
        _write_rules(
            tmp_path,
            [_rule("limit_lock", f"r-1-{i:03d}", name=f"n{i}") for i in range(MAX_RULES)],
        )
        h = _Harness(tmp_path, clock)
        with pytest.raises(RuleError, match="INVALID_RULE"):
            await h.hub.upsert_rule(_rule("limit_lock", "x", name="第 31 條"))
        assert len(h.hub.rules()) == MAX_RULES

        edited = await h.hub.upsert_rule(
            _rule("limit_lock", "r-1-000", name="n0 改"), rule_id="r-1-000"
        )
        assert edited["name"] == "n0 改"

    async def test_save_failure_leaves_memory_untouched(
        self, tmp_path: Path, clock: _Clock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R12/R21:記憶體不得先於落檔更新 —— 否則畫面有、重啟後就沒了。"""
        _write_rules(tmp_path, [_rule("cdp_cross", "r-1-000")])
        h = _Harness(tmp_path, clock)
        before = h.hub.rules()

        def _boom(path: Path, rules: list) -> None:
            raise OSError("磁碟滿了")

        monkeypatch.setattr(hub_mod, "save_rules", _boom)
        with pytest.raises(OSError):
            await h.hub.upsert_rule(_rule("limit_lock", "x", name="新"))
        assert h.hub.rules() == before
        with pytest.raises(OSError):
            await h.hub.delete_rule("r-1-000")
        assert h.hub.rules() == before

    async def test_rules_returns_copies(self, tmp_path: Path, clock: _Clock) -> None:
        """外部改到回傳值不得反噬 slot(熱路徑讀的就是那份 rule)。"""
        h = _Harness(tmp_path, clock)
        snapshot = h.hub.rules()
        snapshot[0]["name"] = "亂改"
        snapshot[0]["cdp_levels"].append("zz")
        assert h.hub.rules()[0]["name"] != "亂改"
        assert "zz" not in h.hub.rules()[0]["cdp_levels"]


class TestTodaySignalsUnion:
    async def test_reads_union_of_engine_date_and_wall_clock_date(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """(e) 兩日別檔聯集:**日期字串升冪**(舊日在前)+ 以 id 去重保檔內順序。

        寫檔的日別有兩個來源(XR-3):engine 在場走 engine 的 trade_date,engine 缺席
        走牆鐘。而 engine 的 trade_date 只在當日首 tick 前進 —— 空自選 / 零推播時它
        停在昨日,於是同一天內兩種來源可能落在不同的檔;只讀其中一邊,另一邊寫的
        訊號會整批從端點消失。
        """
        _seed_jsonl(
            tmp_path,
            _DATE,
            [
                {"id": "a", "code": "1101", "trade_date": _DATE},
                {"id": "dup", "code": "2330", "trade_date": _DATE},
            ],
        )
        _seed_jsonl(
            tmp_path,
            _NEXT,
            [
                {"id": "dup", "code": "2330", "trade_date": _NEXT},
                {"id": "b", "code": "2317", "trade_date": _NEXT},
            ],
        )
        h = _Harness(tmp_path, clock)
        h.date = _DATE  # engine 停在昨日
        clock.now = _dt.datetime(2026, 8, 5, 10, 0, 0)  # 牆鐘已是今天

        rows = h.hub.today_signals()
        assert [r["id"] for r in rows] == ["a", "dup", "b"]
        assert rows[1]["trade_date"] == _DATE  # 去重保「先出現的那一份」

    async def test_same_date_reads_single_file_verbatim(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """(e) 回歸:兩 fn 同日 → 只讀一次檔、輸出**逐字**同既有行為(含重複 id)。

        既有契約(SC-7)是「重啟後同一事件同 id」,當日檔裡本來就會有同 id 兩列,
        端點必須原樣回傳;聯集分支若無條件套去重,就會把那一列吃掉。
        """
        _seed_jsonl(
            tmp_path,
            _DATE,
            [{"id": "same", "code": "2330"}, {"id": "same", "code": "2330"}],
        )
        h = _Harness(tmp_path, clock)  # trade_date_fn() 與牆鐘同為 2026-08-04
        reads: list[str] = []
        real = h.hub.read_signals

        def _counted(trade_date: str) -> list[dict]:
            reads.append(trade_date)
            return real(trade_date)

        h.hub.read_signals = _counted  # type: ignore[method-assign]
        rows = h.hub.today_signals()
        assert reads == [_DATE]
        assert rows == [{"id": "same", "code": "2330"}, {"id": "same", "code": "2330"}]
