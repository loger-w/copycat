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
from copycat.server import signal_hub as hub_mod
from copycat.server.signal_hub import SignalHub, format_signal_text
from copycat.signal_rules import CDP_LEVELS, MAX_RULES, RULE_KINDS, RuleError, load_rules
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
    """預寫規則檔:hub 建構時就走 load 而非遷移(注入受測規則集合的唯一入口)。"""
    (tmp_path / _RULES_FILE).write_text(
        json.dumps({"_cache_version": 1, "rules": rules}, ensure_ascii=False), encoding="utf-8"
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

    def __init__(self, bars: list[DailyBar] | None = None, *, error: bool = False) -> None:
        self.bars = list(bars or [])
        self.error = error
        self.calls: list[tuple[str, int]] = []

    async def __call__(self, code: str, n: int = 25) -> list[DailyBar]:
        self.calls.append((code, n))
        if self.error:
            raise ConnectionError("TC4 不可用")
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


class _Harness:
    def __init__(
        self,
        tmp_path: Path,
        clock: _Clock,
        bars: _FakeBars | None = None,
        wl: _Watch | None = None,
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
            daily_bars=self.bars,
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


def _market_event(**over: Any) -> dict[str, Any]:
    """breadth diff 交給 hub 的事件形狀(design §6.4 → §7)。"""
    event: dict[str, Any] = {
        "kind": "market_limit_lock",
        "code": "2330",
        "name": "台積電",
        "price": 100_000,
        "time": "10:00:00",
        "direction": "up",
        "touch_count": 1,
    }
    event.update(over)
    return event


def _seed_jsonl(tmp_path: Path, date: str, rows: list[dict[str, Any]]) -> None:
    """直接鋪當日 jsonl(模擬「上一個 process 留下的檔」)。"""
    path = tmp_path / "signals" / f"{date.replace('-', '')}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )


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
        """
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            h.hub.on_watchlist(["2330"])
            await h.settle()

            monkeypatch.setattr(hub_mod, "compute_cdp", _boom_cdp)
            h.hub.on_rollover_pending(_NEXT)
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
        """邊界 2:同 kind 兩規則同 tick → 兩則事件,id 因 rule 段不撞。"""
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
            assert len(h.bot) == 2
        finally:
            await h.hub.close()

    async def test_upsert_preserves_other_rules_state(self, tmp_path: Path, clock: _Clock) -> None:
        """邊界 3:被編輯那顆 detector 重建歸零,其他顆的 cooldown 原樣保留。

        兩條規則都把冷卻設到一天:第一次穿越後兩顆都被自己的冷卻壓著;編輯 A 之後
        只有 A 能再發。順帶釘 `_seed_slot` —— 新 detector 沒被餵基準的話這裡零事件。
        """
        rules = [
            _rule("cdp_cross", "r-1-000", cooldown_secs=86_400, params={"rearm_ticks": 0}),
            _rule("cdp_cross", "r-1-001", cooldown_secs=86_400, params={"rearm_ticks": 0}),
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
        assert [r["kind"] for r in rules] == list(RULE_KINDS)
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


class TestMarketEvents:
    """SC-6:全市場廣度事件的入口(design §7)。

    這條路徑與規則引擎**完全平行** —— 不經 slots、不經 detector、硬性不進 Discord。
    breadth 是純 FinMind 來源,它的日別由呼叫端傳入(TC4 engine 的 trade_date 會在
    空自選 / 零推播時靜默停在昨日,綁上去等於整批事件落錯檔且無錯誤訊號)。
    """

    async def test_publishes_ws_and_jsonl_but_never_discord(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """(a) 兩則 → WS 兩則(id 文法 + 鍵集合)、jsonl 佇列 2、Discord 佇列 0。"""
        h = _Harness(tmp_path, clock)  # 刻意不 start:兩條佇列的內容留在原地可直接數
        h.attach_bot()
        h.hub.publish_market_events(
            [
                _market_event(),
                _market_event(
                    kind="market_limit_open",
                    code="2317",
                    name="鴻海",
                    price=50_000,
                    time="10:01:00",
                    direction="down",
                    touch_count=2,
                ),
            ],
            trade_date=_DATE,
        )

        assert len(h.published) == 2
        first = h.published[0]
        # 無 rule_id / rule_name:這條路徑沒有規則(前端型別 optional)
        assert set(first) == _SIGNAL_KEYS - {"rule_id", "rule_name"}
        assert first["type"] == "signal"
        assert first["id"] == "2026-08-04-breadth-2330-market_limit_lock-up-10:00:00"
        assert first["kind"] == "market_limit_lock"
        assert first["code"] == "2330"
        assert first["name"] == "台積電"
        assert first["price"] == 100_000
        assert first["time"] == "10:00:00"
        assert first["levels"] == []
        assert first["direction"] == "up"
        assert first["pct"] is None
        assert first["touch_count"] == 1
        assert h.published[1]["id"] == "2026-08-04-breadth-2317-market_limit_open-down-10:01:00"
        assert h.published[1]["touch_count"] == 2

        assert h.hub._discord_queue.qsize() == 0  # 硬性不進 Discord(不是靠規則開關)
        rows = _drain(h.hub._jsonl_queue)
        assert [r["code"] for r in rows] == ["2330", "2317"]
        assert [r["trade_date"] for r in rows] == [_DATE, _DATE]
        assert set(rows[0]) == (_SIGNAL_KEYS - {"rule_id", "rule_name"}) | {"trade_date"}

    async def test_closing_drops_events(self, tmp_path: Path, clock: _Clock) -> None:
        """(b) 關機已開始 → 整批丟棄(再收件也不會被寫出去)。"""
        h = _Harness(tmp_path, clock)
        await h.hub.close()
        h.hub.publish_market_events([_market_event()], trade_date=_DATE)
        assert h.published == []
        assert h.hub._jsonl_queue.qsize() == 0
        assert h.rows() == []

    async def test_trade_date_mismatch_warns_once_and_uses_given_date(
        self, tmp_path: Path, clock: _Clock, caplog: pytest.LogCaptureFixture
    ) -> None:
        """(c) 傳入日別與 `_trade_date_fn()` 不符 → warning **每日別一次**,仍落傳入值檔。

        engine 的 trade_date 可能靜默停在昨日,所以不符不是「錯誤」而是「要看得見」;
        每則都記則會在一輪數百則的廣度事件下把 log 洗掉,反而更看不見。
        """
        h = _Harness(tmp_path, clock)  # trade_date_fn() = 2026-08-04
        with caplog.at_level(logging.WARNING, logger="copycat.server.signal_hub"):
            h.hub.publish_market_events(
                [_market_event(), _market_event(code="2317", time="10:01:00")],
                trade_date=_NEXT,
            )
            assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1
            h.hub.publish_market_events(
                [_market_event(code="2454", time="10:02:00")], trade_date=_NEXT
            )
            assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1

        await h.hub.close()  # 盡力落檔
        assert h.rows(_DATE) == []
        assert [r["code"] for r in h.rows(_NEXT)] == ["2330", "2317", "2454"]

    async def test_publish_exception_does_not_escape_and_later_events_still_sent(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """(g) never-raise:WS 那則炸掉只丟 WS,**jsonl 照收**(review S-4/C-5)。

        呼叫端是 breadth `_poll_loop`;這裡往外拋等於整條家數輪停擺,而家數面板
        與廣度事件是兩件事,不該被彼此的失敗綁死。

        jsonl 是歷史真相源**也是重啟後對帳 seed 的來源**:WS 拋一次就連 jsonl 一起
        丟的話,那則事件從此不存在 —— 重啟後 seed 讀不到它,對帳會把已經發生過的
        鎖板當成新的再發一次(或反過來永遠對不回來)。所以入列先行、兩者各自 try。
        """
        h = _Harness(tmp_path, clock)
        sent: list[dict] = []

        def _flaky(msg: dict) -> None:
            if msg["code"] == "2330":
                raise RuntimeError("ws 壞了")
            sent.append(msg)

        h.hub._publish = _flaky  # type: ignore[assignment]
        h.hub.publish_market_events(
            [_market_event(), _market_event(code="2317", time="10:01:00")], trade_date=_DATE
        )

        assert [m["code"] for m in sent] == ["2317"]
        assert [r["code"] for r in _drain(h.hub._jsonl_queue)] == ["2330", "2317"]


class TestMarketEventState:
    async def test_replays_lock_then_open_to_false_with_counts(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """(d) engine seed 的唯一來源:檔內順序後者勝 → lock→open 得 False。

        非 market 的 kind 一律不進(`limit_lock` 是自選股那條路,名字只差前綴)。
        """
        h = _Harness(tmp_path, clock)
        h.hub.on_watchlist(["2330"])
        h.lock_up(_state(upper=110_000, locked_up=True))  # 自選股 limit_lock:不得混入
        h.hub.publish_market_events([_market_event()], trade_date=_DATE)
        h.hub.publish_market_events(
            [_market_event(kind="market_limit_open", time="10:05:00")], trade_date=_DATE
        )
        await h.hub.close()
        assert len(h.rows()) == 3

        fresh = _Harness(tmp_path, clock)  # 重啟後的 engine seed
        emitted, counts = fresh.hub.market_event_state(_DATE)
        assert emitted == {("2330", "up"): False}
        assert counts == {
            ("2330", "market_limit_lock", "up"): 1,
            ("2330", "market_limit_open", "up"): 1,
        }

    async def test_missing_file_returns_empty_pair(self, tmp_path: Path, clock: _Clock) -> None:
        """檔缺 → 空 seed(視同全 False):開盤即鎖的檔在首輪就發 lock。"""
        h = _Harness(tmp_path, clock)
        assert h.hub.market_event_state("2026-01-01") == ({}, {})


class TestTodaySignalsUnion:
    async def test_reads_union_of_engine_date_and_wall_clock_date(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """(e) 兩日別檔聯集:**日期字串升冪**(舊日在前)+ 以 id 去重保檔內順序。

        stock engine 的 trade_date 只在當日首 tick 前進 —— 空自選 / 零推播時它停在
        昨日,而廣度事件寫的是牆鐘日檔;只讀其中一邊,今天的事件會整批從端點消失。
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


class TestMarketKindText:
    """(f) `_kind_text` 的 market 兩案 × 兩方向 —— 前端 `kindLabel` 與此對齊。"""

    def test_market_limit_lock_up(self) -> None:
        assert hub_mod._kind_text({"kind": "market_limit_lock", "direction": "up"}) == "全市場鎖漲停"

    def test_market_limit_lock_down(self) -> None:
        assert (
            hub_mod._kind_text({"kind": "market_limit_lock", "direction": "down"}) == "全市場鎖跌停"
        )

    def test_market_limit_open_up(self) -> None:
        assert (
            hub_mod._kind_text({"kind": "market_limit_open", "direction": "up"}) == "全市場漲停打開"
        )

    def test_market_limit_open_down(self) -> None:
        assert (
            hub_mod._kind_text({"kind": "market_limit_open", "direction": "down"})
            == "全市場跌停打開"
        )
