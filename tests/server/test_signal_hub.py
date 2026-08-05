"""SignalHub 接線層行為合約(design §4 / §7;SC-1 整合層 / SC-5 / SC-7 / SC-12 後端半)。

detector 本身的判定邏輯在 `tests/live/test_signal_state.py`,這裡只釘接線:
payload 逐鍵契約、membership gate、fanout(WS / jsonl / Discord)、基準 worker、
enabled 持久化。時鐘一律注入,daily_bars / publish / notify_fallback 全用 fake。
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
import time
from dataclasses import replace
from pathlib import Path

import pytest

from copycat.live.stock_models import StockBook, StockMeta, StockTick
from copycat.live.stock_source import DailyBar
from copycat.live.stock_state import StockDayState
from copycat.server import signal_hub as hub_mod
from copycat.server.signal_hub import SignalHub
from copycat.signals_config import SignalsConfig

_DATE = "2026-08-04"
_NEXT = "2026-08-05"
_THIRD = "2026-08-06"
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
}


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


class _Harness:
    def __init__(
        self,
        tmp_path: Path,
        clock: _Clock,
        bars: _FakeBars | None = None,
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
            assert msg["id"] == "2026-08-04-2330-cdp_cross-nh-10:00:00.123"

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
            assert h.published[0]["id"] == "2026-08-04-2330-limit_lock-up-10:00:00.123"
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
            h.hub._detector.drop_code = dropped.append  # type: ignore[method-assign]

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
    async def test_disabled_kind_emits_nothing_and_persists(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """SC-12 後端半:關掉的 kind 不產事件,開關跨重啟保留。"""
        h = _Harness(tmp_path, clock)
        await h.hub.start()
        try:
            assert h.hub.enabled() == {
                "cdp_cross": True,
                "surge_crash": True,
                "vol_burst": True,
                "limit_lock": True,
            }
            await h.hub.set_enabled({"cdp_cross": False})
            h.hub.on_watchlist(["2330"])
            await h.settle()
            h.cross_nh(_state())
            await h.settle()
            assert h.published == []

            h.lock_up(_state(upper=110_000, locked_up=True), code="2317")
            h.hub.on_watchlist(["2330", "2317"])
            await h.settle()
            h.lock_up(_state(upper=110_000, locked_up=True), code="2317")
            await h.settle()
            assert [m["kind"] for m in h.published] == ["limit_lock"]
        finally:
            await h.hub.close()

        again = _Harness(tmp_path, clock)
        assert again.hub.enabled()["cdp_cross"] is False
        assert again.hub.enabled()["limit_lock"] is True

    async def test_concurrent_set_enabled_lands_memory_state_on_disk(
        self, tmp_path: Path, clock: _Clock
    ) -> None:
        """CC-7:read-modify-write 與落檔沒有共同臨界區 → 慢的那次寫入覆蓋在後。

        記憶體是對的、磁碟停在舊值,重啟後開關「自己跳回去」而當下零錯誤訊號。
        """
        h = _Harness(tmp_path, clock)
        real = h.hub._write_enabled

        def slow_stale_write(flags: dict[str, bool]) -> None:
            # 舊快照(vol_burst 還是 True 的那次)刻意寫得慢 → 無 lock 時它最後落地
            if flags["vol_burst"]:
                time.sleep(0.05)
            real(flags)

        h.hub._write_enabled = slow_stale_write  # type: ignore[method-assign]

        await asyncio.gather(
            h.hub.set_enabled({"cdp_cross": False}),
            h.hub.set_enabled({"vol_burst": False}),
        )

        expected = {
            "cdp_cross": False,
            "surge_crash": True,
            "vol_burst": False,
            "limit_lock": True,
        }
        assert h.hub.enabled() == expected
        on_disk = json.loads((tmp_path / "signals_enabled.json").read_text(encoding="utf-8"))
        assert on_disk == expected, "磁碟停在舊快照 = 重啟後開關自己跳回去"

    async def test_set_enabled_rejects_unknown_key(self, tmp_path: Path, clock: _Clock) -> None:
        h = _Harness(tmp_path, clock)
        with pytest.raises(ValueError):
            await h.hub.set_enabled({"nope": True})
        with pytest.raises(ValueError):
            await h.hub.set_enabled({"cdp_cross": "yes"})  # type: ignore[dict-item]


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
            # stage1:盤前預抓次日基準(多一根 08-04 日 K → nh 由 80_000 變 95_000)
            h.bars.bars = [_BAR_A, _BAR_B]
            h.hub.on_rollover_pending(_NEXT)
            await h.settle()
            assert h.published == []  # 暫存不生效

            h.date = _NEXT
            clock.now = _dt.datetime(2026, 8, 5, 10, 0, 0)
            h.hub.on_rollover()
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

            state2 = _state()
            h.hub.on_tick("2330", _tick(124_000, trade_date=_THIRD), state2)
            h.hub.on_tick("2330", _tick(125_500, cum=2, trade_date=_THIRD), state2)
            await h.settle()
            assert [m["levels"] for m in h.published] == [["nh"]], "沿用了昨天的 CDP 基準"
            assert h.published[0]["price"] == 125_500
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
