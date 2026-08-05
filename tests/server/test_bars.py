from __future__ import annotations

import datetime as _dt
import logging
from typing import cast

import pytest

from copycat.live.stock_source import Bar, BarsStatus
from copycat.server.bars import (
    DAILY_MAX_BARS,
    EMPTY_TTL_SECS,
    BarsCache,
    BarsResult,
    build_daily,
    build_minute,
    clamp_days,
    worst_status,
)


def bar(t: str, c: int = 100, v: int = 1) -> Bar:
    return {"t": t, "o": c, "h": c, "l": c, "c": c, "v": v}


class _Fetcher:
    """engine.bars_range 替身:記錄每次呼叫的區間。

    `statuses` 逐次對應 `by_call`(超出長度 → "ok"),讓「哪一段逾時」可以精確注入
    —— 三態的重點正是兩段各自的來源不同(SC-6 worst 合併)。

    型別刻意收成 `list[str]` 而非 `list[BarsStatus]`:`BarsStatus` 是 Literal,
    只在 pyright 期生效,**runtime 進來的就是裸 str**(source 是 fake / 未來可能是
    別的實作)。域外值要測得到,替身就不能先幫真實世界把它擋掉。
    """

    def __init__(
        self,
        by_call: list[list[Bar]] | None = None,
        statuses: list[str] | None = None,
    ) -> None:
        self.calls: list[tuple[str, str, str, str]] = []
        self._by_call = by_call
        self._statuses = statuses

    async def __call__(self, code: str, tf: str, start: str, end: str) -> BarsResult:
        self.calls.append((code, tf, start, end))
        idx = len(self.calls) - 1
        bars: list[Bar] = []
        if self._by_call is not None and idx < len(self._by_call):
            bars = self._by_call[idx]
        status = "ok"
        if self._statuses is not None and idx < len(self._statuses):
            status = self._statuses[idx]
        return BarsResult(bars, cast("BarsStatus", status))


class TestClampDays:
    def test_clamped_to_range(self) -> None:
        assert clamp_days(0) == 1
        assert clamp_days(5) == 5
        assert clamp_days(999) == 30


class TestWorstStatus:
    """SC-6:status = 各實際發出 fetch 的最壞值(disconnected > timeout > ok)。"""

    def test_severity_order(self) -> None:
        assert worst_status("ok", "timeout") == "timeout"
        assert worst_status("timeout", "disconnected") == "disconnected"
        assert worst_status("ok", "ok") == "ok"
        assert worst_status("disconnected", "ok", "timeout") == "disconnected"

    def test_no_args_is_ok(self) -> None:
        """一次 fetch 都沒發(兩段全 cache 命中)→ 沒有壞消息可報。"""
        assert worst_status() == "ok"


class TestDailyCache:
    async def test_daily_memo_hits_second_call(self) -> None:
        today = _dt.date(2026, 7, 28)
        fetch = _Fetcher([[bar("2026-07-27")]])
        cache = BarsCache()
        assert (await build_daily(fetch, cache, "2330", today)).bars == [bar("2026-07-27")]
        assert (await build_daily(fetch, cache, "2330", today)).bars == [bar("2026-07-27")]
        assert len(fetch.calls) == 1  # 第二次全走 memo

    async def test_daily_empty_not_cached(self) -> None:
        """don't-cache-empty:TC4 失敗與真無資料上游不可分,要留重試餘地。

        round3:空結果改由短 TTL 負向快取擋一下(收斂重複的首頁 deadline 空等),
        過了 EMPTY_TTL_SECS 必須恢復重抓 —— 「可恢復」性質不變,只是延後幾秒(W-15)。
        """
        clock = {"t": 0.0}
        fetch = _Fetcher([[], [bar("2026-07-27")]])
        cache = BarsCache(clock=lambda: clock["t"])
        assert (await build_daily(fetch, cache, "2330", _dt.date(2026, 7, 28))).bars == []
        clock["t"] = EMPTY_TTL_SECS + 1.0
        assert (await build_daily(fetch, cache, "2330", _dt.date(2026, 7, 28))).bars != []
        assert len(fetch.calls) == 2

    async def test_daily_tail_limited_to_120(self) -> None:
        many = [bar(f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}") for i in range(200)]
        fetch = _Fetcher([many])
        bars, _ = await build_daily(fetch, BarsCache(), "2330", _dt.date(2026, 7, 28))
        assert len(bars) == DAILY_MAX_BARS

    async def test_daily_window_is_180_calendar_days(self) -> None:
        # D-14:tf=D 專屬視窗,不共用 overlay 的 _DAILY_WINDOW_DAYS=40(≈27 交易日)
        today = _dt.date(2026, 7, 28)
        fetch = _Fetcher([[bar("2026-07-27")]])
        await build_daily(fetch, BarsCache(), "2330", today)
        _, tf, start, end = fetch.calls[0]
        assert tf == "D"
        assert end == "2026-07-28"
        assert (today - _dt.date.fromisoformat(start)).days == 180


class TestMinuteTwoTier:
    async def test_history_memoized_today_refetched(self) -> None:
        today = _dt.date(2026, 7, 28)
        hist = [bar("2026-07-27 09:01")]
        cur = [bar("2026-07-28 09:01")]
        fetch = _Fetcher([hist, cur, cur])
        cache = BarsCache(ttl=0.0)  # 當日段每次都過期
        first = await build_minute(fetch, cache, "2330", 2, today)
        assert first.bars == hist + cur
        second = await build_minute(fetch, cache, "2330", 2, today)
        assert second.bars == hist + cur
        # 3 次呼叫 = 歷史 1 次 + 當日 2 次(歷史沒有重抓)
        assert len(fetch.calls) == 3
        assert [c[1:] for c in fetch.calls] == [
            ("1", "2026-07-27", "2026-07-27"),
            ("1", "2026-07-28", "2026-07-28"),
            ("1", "2026-07-28", "2026-07-28"),
        ]

    async def test_holiday_negative_cache_prevents_refetch(self) -> None:
        """窗內含週末 → 該日永遠無資料。少了負向快取就會每次重拉整段歷史(R2-2)。"""
        today = _dt.date(2026, 7, 28)  # 週二
        # 近 5 日 = 07-24(五) 07-25(六) 07-26(日) 07-27(一) 07-28(二)
        hist = [bar("2026-07-24 09:01"), bar("2026-07-27 09:01")]
        fetch = _Fetcher([hist, [], []])
        cache = BarsCache(ttl=999.0)
        await build_minute(fetch, cache, "2330", 5, today)
        hist_calls = len([c for c in fetch.calls if c[3] != today.isoformat()])
        await build_minute(fetch, cache, "2330", 5, today)
        assert len([c for c in fetch.calls if c[3] != today.isoformat()]) == hist_calls
        # 週末兩天被寫成空 list = 負向快取命中,不再算「缺」
        assert cache.hist_missing("2330", _dt.date(2026, 7, 24), _dt.date(2026, 7, 27)) == []

    async def test_today_ttl_expiry_refetches_only_today(self) -> None:
        today = _dt.date(2026, 7, 28)
        clock = {"t": 0.0}
        cache = BarsCache(ttl=30.0, clock=lambda: clock["t"])
        cur1 = [bar("2026-07-28 09:01")]
        cur2 = [bar("2026-07-28 09:01"), bar("2026-07-28 09:02")]
        fetch = _Fetcher([[bar("2026-07-27 09:01")], cur1, cur2])
        await build_minute(fetch, cache, "2330", 2, today)
        clock["t"] = 10.0
        await build_minute(fetch, cache, "2330", 2, today)  # TTL 內 → 不重抓
        assert len(fetch.calls) == 2
        clock["t"] = 40.0
        out, _ = await build_minute(fetch, cache, "2330", 2, today)  # TTL 過 → 只重抓當日
        assert len(fetch.calls) == 3
        assert out[-1]["t"] == "2026-07-28 09:02"  # SC-10:最後一根會前進

    async def test_empty_history_not_negatively_cached(self) -> None:
        """整段回空可能是 TC4 失敗 → 不可寫**永久**負向快取,否則被釘成空。

        round3:全空結果現在會被短 TTL(EMPTY_TTL_SECS)擋一下以收斂重複空等,
        但過了 TTL 必須恢復重抓 —— W-15 的「可恢復」性質不變,只是延後幾秒。
        """
        today = _dt.date(2026, 7, 28)
        clock = {"t": 0.0}
        fetch = _Fetcher([[], [], [bar("2026-07-27 09:01")], []])
        cache = BarsCache(ttl=999.0, clock=lambda: clock["t"])
        await build_minute(fetch, cache, "2330", 2, today)
        assert cache.hist_missing("2330", _dt.date(2026, 7, 27), _dt.date(2026, 7, 27)) != []
        clock["t"] = EMPTY_TTL_SECS + 1.0
        out, _ = await build_minute(fetch, cache, "2330", 2, today)
        assert out == [bar("2026-07-27 09:01")]

    async def test_days_1_skips_history_segment(self) -> None:
        today = _dt.date(2026, 7, 28)
        fetch = _Fetcher([[bar("2026-07-28 09:01")]])
        await build_minute(fetch, BarsCache(), "2330", 1, today)
        assert [c[1:] for c in fetch.calls] == [("1", "2026-07-28", "2026-07-28")]

    async def test_today_empty_not_cached(self) -> None:
        """當日段回空同樣只被短 TTL 擋,過了就重抓(W-15)。"""
        today = _dt.date(2026, 7, 28)
        clock = {"t": 0.0}
        fetch = _Fetcher([[], [bar("2026-07-28 09:01")]])
        cache = BarsCache(ttl=999.0, clock=lambda: clock["t"])
        assert (await build_minute(fetch, cache, "2330", 1, today)).bars == []
        clock["t"] = EMPTY_TTL_SECS + 1.0
        assert (await build_minute(fetch, cache, "2330", 1, today)).bars != []


class TestPhase5Hardening:
    async def test_truncated_fetch_does_not_pin_later_days_empty(self) -> None:
        """TC4 分頁提早截斷 → 後面的日子不可寫負向快取,否則永久釘成空(review P1-2)。"""
        today = _dt.date(2026, 7, 28)
        # 請求 07-24..07-27,但只回到 07-25 就截斷
        truncated = [bar("2026-07-24 09:01"), bar("2026-07-25 09:01")]
        full = truncated + [bar("2026-07-26 09:01"), bar("2026-07-27 09:01")]
        fetch = _Fetcher([truncated, [], full, []])
        cache = BarsCache(ttl=999.0)
        await build_minute(fetch, cache, "2330", 5, today)
        # 07-26 / 07-27 仍算「缺」→ 下次會重抓
        assert cache.hist_missing("2330", _dt.date(2026, 7, 26), _dt.date(2026, 7, 27)) == [
            _dt.date(2026, 7, 26),
            _dt.date(2026, 7, 27),
        ]
        out, _ = await build_minute(fetch, cache, "2330", 5, today)
        assert [b["t"] for b in out] == [b["t"] for b in full]

    async def test_existing_bars_not_overwritten_by_empty(self) -> None:
        cache = BarsCache()
        d = _dt.date(2026, 7, 24)
        cache.put_hist_range("2330", d, d, [bar("2026-07-24 09:01")])
        cache.put_hist_range("2330", d, d, [])  # second pass returns nothing
        assert cache.hist_range("2330", d, d) == [bar("2026-07-24 09:01")]

    async def test_today_cache_keyed_by_date_survives_midnight(self) -> None:
        """跨午夜:昨日的當日段不可在 TTL 窗內被當成今日資料回(review P2-9)。"""
        cache = BarsCache(ttl=999.0)
        cache.today_put("2330", "2026-07-28", [bar("2026-07-28 13:30")], "ok")
        assert cache.today_get("2330", "2026-07-28") == ([bar("2026-07-28 13:30")], "ok")
        assert cache.today_get("2330", "2026-07-29") is None

    async def test_prune_drops_out_of_window_entries(self) -> None:
        cache = BarsCache()
        old = _dt.date(2026, 1, 1)
        cache.put_hist_range("2330", old, old, [bar("2026-01-01 09:01")])
        cache.daily_put("2330", "2026-01-01", [bar("2026-01-01")])
        cache.today_put("2330", "2026-01-01", [bar("2026-01-01 09:01")], "ok")
        cache.prune(_dt.date(2026, 7, 28))
        assert cache.hist_range("2330", old, old) == []
        assert cache.daily_get("2330", "2026-01-01") is None
        assert cache.today_get("2330", "2026-01-01") is None


class TestEmptyNegativeCache:
    """round3 T-8(項 9):TC4 查無該檔時每次請求都重付 60s 的空等。

    實測(2026-07-29,server :8721 + TC4 在線):9999 的 ?tf=1&days=30 兩次都是
    60.1s —— 歷史段與當日段各等滿 30s deadline,且完全沒有快取。
    """

    async def test_empty_result_short_ttl_blocks_refetch(self) -> None:
        today = _dt.date(2026, 7, 28)
        clock = {"t": 0.0}
        fetch = _Fetcher([[], []])
        cache = BarsCache(ttl=999.0, clock=lambda: clock["t"])
        assert (await build_minute(fetch, cache, "9999", 2, today)).bars == []
        calls = len(fetch.calls)
        clock["t"] = EMPTY_TTL_SECS - 1.0
        assert (await build_minute(fetch, cache, "9999", 2, today)).bars == []
        assert len(fetch.calls) == calls  # TTL 內完全不打 TC4

    async def test_empty_ttl_expiry_recovers(self) -> None:
        """W-15:負向標記必須會過期,否則等於把「可恢復」改成永久釘死。"""
        today = _dt.date(2026, 7, 28)
        clock = {"t": 0.0}
        fetch = _Fetcher([[], [], [bar("2026-07-27 09:01")], [bar("2026-07-28 09:01")]])
        cache = BarsCache(ttl=999.0, clock=lambda: clock["t"])
        assert (await build_minute(fetch, cache, "9999", 2, today)).bars == []
        clock["t"] = EMPTY_TTL_SECS + 1.0
        assert (await build_minute(fetch, cache, "9999", 2, today)).bars != []

    async def test_empty_key_includes_days(self) -> None:
        """key 含 days:days=1 的空結果不可把 days=30 一併釘住(review R15)。"""
        today = _dt.date(2026, 7, 28)
        cache = BarsCache(ttl=999.0)
        fetch = _Fetcher([[], [bar("2026-07-27 09:01")], [bar("2026-07-28 09:01")]])
        assert (await build_minute(fetch, cache, "2330", 1, today)).bars == []
        calls = len(fetch.calls)
        await build_minute(fetch, cache, "2330", 30, today)
        assert len(fetch.calls) > calls

    async def test_daily_empty_also_short_ttl_cached(self) -> None:
        today = _dt.date(2026, 7, 28)
        clock = {"t": 0.0}
        fetch = _Fetcher([[], []])
        cache = BarsCache(ttl=999.0, clock=lambda: clock["t"])
        assert (await build_daily(fetch, cache, "9999", today)).bars == []
        calls = len(fetch.calls)
        clock["t"] = EMPTY_TTL_SECS - 1.0
        assert (await build_daily(fetch, cache, "9999", today)).bars == []
        assert len(fetch.calls) == calls

    async def test_today_empty_with_nonempty_history_still_short_cached(self) -> None:
        """歷史有資料但今日零成交:合併後的 out 非空 → 不會觸發 empty_mark,
        於是當日段每次請求都重付一次 TC4 首頁等待(self-review B2)。
        當日段自己也要有短 TTL 負向快取。"""
        today = _dt.date(2026, 7, 28)
        clock = {"t": 0.0}
        hist = [bar("2026-07-27 09:01")]
        fetch = _Fetcher([hist, [], []])
        cache = BarsCache(ttl=999.0, clock=lambda: clock["t"])
        assert (await build_minute(fetch, cache, "2317", 2, today)).bars == hist
        calls = len(fetch.calls)
        clock["t"] = EMPTY_TTL_SECS - 1.0
        assert (await build_minute(fetch, cache, "2317", 2, today)).bars == hist
        assert len(fetch.calls) == calls  # 當日段不再重打

    async def test_today_empty_short_ttl_expires(self) -> None:
        """短 TTL 過期後當日段必須重抓 —— 該股開始成交時要看得到(W-15 同理)。"""
        today = _dt.date(2026, 7, 28)
        clock = {"t": 0.0}
        hist = [bar("2026-07-27 09:01")]
        cur = [bar("2026-07-28 09:01")]
        fetch = _Fetcher([hist, [], cur])
        cache = BarsCache(ttl=999.0, clock=lambda: clock["t"])
        assert (await build_minute(fetch, cache, "2317", 2, today)).bars == hist
        clock["t"] = EMPTY_TTL_SECS + 1.0
        assert (await build_minute(fetch, cache, "2317", 2, today)).bars == hist + cur

    async def test_prune_evicts_expired_today_entries(self) -> None:
        """`today_put` 開始存空 entry 後,同日內過期的 entry 也要能回收。

        prune 原本對 `_today` 只做「日期 != 今日就刪」。空結果不進 cache 的時代,
        股號維度實質被「真的有今日資料的股號」約束(prune docstring 據此判定成長受控);
        改成空也存之後,任何通過 validate_code 的字串被請求一次就會留一筆到跨日
        (self-review round2 P2)。
        """
        clock = {"t": 0.0}
        today = _dt.date(2026, 7, 28)
        cache = BarsCache(ttl=999.0, clock=lambda: clock["t"])
        cache.today_put("9999", today.isoformat(), [], "ok")  # 空 → 吃 EMPTY_TTL_SECS
        cache.today_put("2330", today.isoformat(), [bar("2026-07-28 09:01")], "ok")  # 非空 → ttl
        clock["t"] = EMPTY_TTL_SECS + 1.0
        cache.prune(today)
        # 空 entry 已過期 → 回收;非空 entry 的 ttl=999 還沒到 → 留著
        assert cache.today_get("9999", today.isoformat()) is None
        assert cache.today_get("2330", today.isoformat()) is not None
        assert cache.today_entry_count() == 1

    async def test_prune_drops_only_expired_empty_marks(self) -> None:
        """prune 在每次 build_* 開頭都會跑 —— 無條件清空等於負向快取從未生效。

        順帶覆蓋 SC-5:標記存的是**原因**,prune 過一輪也不得被洗成 ok。
        """
        clock = {"t": 0.0}
        cache = BarsCache(ttl=999.0, clock=lambda: clock["t"])
        cache.empty_mark("2330", "1", 30, "timeout")
        cache.prune(_dt.date(2026, 7, 28))
        assert cache.empty_status("2330", "1", 30) == "timeout"  # 未過期 → 留著,原因保真
        clock["t"] = EMPTY_TTL_SECS + 1.0
        cache.prune(_dt.date(2026, 7, 28))
        assert cache.empty_status("2330", "1", 30) is None  # 過期 → 被 prune 丟掉


class TestStatusFlow:
    """N-3:status 沿 build_* 流出,兩段以 worst 合併(SC-6)。"""

    async def test_daily_status_flows_through(self) -> None:
        today = _dt.date(2026, 7, 28)
        fetch = _Fetcher([[]], ["timeout"])
        assert await build_daily(fetch, BarsCache(), "2330", today) == ([], "timeout")

    async def test_daily_ok_status_when_data(self) -> None:
        today = _dt.date(2026, 7, 28)
        fetch = _Fetcher([[bar("2026-07-27")]])
        assert await build_daily(fetch, BarsCache(), "2330", today) == ([bar("2026-07-27")], "ok")

    async def test_daily_memo_hit_reports_ok(self) -> None:
        """已有資料的 memo 命中 = 沒發 fetch,沒有壞消息可報。"""
        today = _dt.date(2026, 7, 28)
        fetch = _Fetcher([[bar("2026-07-27")]], ["timeout"])
        cache = BarsCache()
        # 第一次:有資料但那一趟 timeout(DK 逾時→1K fallback 有料的樣態)
        assert (await build_daily(fetch, cache, "2330", today)).status == "timeout"
        # 第二次全走 memo → 不再重播上一次的壞消息
        assert (await build_daily(fetch, cache, "2330", today)) == ([bar("2026-07-27")], "ok")
        assert len(fetch.calls) == 1

    async def test_minute_worst_of_two_segments(self) -> None:
        """歷史段 ok + 當日段 timeout → timeout(bars 非空也照回 status)。"""
        today = _dt.date(2026, 7, 28)
        hist = [bar("2026-07-27 09:01")]
        fetch = _Fetcher([hist, []], ["ok", "timeout"])
        out, status = await build_minute(fetch, BarsCache(ttl=999.0), "2330", 2, today)
        assert out == hist
        assert status == "timeout"

    async def test_minute_disconnected_beats_timeout(self) -> None:
        today = _dt.date(2026, 7, 28)
        fetch = _Fetcher([[], []], ["timeout", "disconnected"])
        assert (await build_minute(fetch, BarsCache(ttl=999.0), "2330", 2, today)) == (
            [],
            "disconnected",
        )

    async def test_minute_all_ok_stays_ok(self) -> None:
        today = _dt.date(2026, 7, 28)
        fetch = _Fetcher([[], []])
        assert (await build_minute(fetch, BarsCache(ttl=999.0), "2330", 2, today)).status == "ok"

    async def test_minute_history_memo_hit_counts_as_ok(self) -> None:
        """歷史段全 memo 命中(未 fetch)→ 不貢獻 status;當日段 ok → 整體 ok。"""
        today = _dt.date(2026, 7, 28)
        hist = [bar("2026-07-27 09:01")]
        cur = [bar("2026-07-28 09:01")]
        fetch = _Fetcher([hist, cur, cur], ["timeout", "ok", "ok"])
        cache = BarsCache(ttl=0.0)  # 當日段每次都過期 → 只有歷史段吃 memo
        assert (await build_minute(fetch, cache, "2330", 2, today)).status == "timeout"
        assert (await build_minute(fetch, cache, "2330", 2, today)).status == "ok"

    async def test_today_cache_hit_preserves_status(self) -> None:
        """R4:`_today` 存 status —— days 維度不同時 `_empty` 未命中,
        當日段的空若被視為 ok,timeout 就被洗白(SC-5)。"""
        today = _dt.date(2026, 7, 28)
        clock = {"t": 0.0}
        hist = [bar("2026-07-27 09:01")]
        # call0=days1 當日段 timeout;call1=days30 歷史段 ok(當日段走 cache)
        fetch = _Fetcher([[], hist], ["timeout", "ok"])
        cache = BarsCache(ttl=999.0, clock=lambda: clock["t"])
        assert (await build_minute(fetch, cache, "2330", 1, today)) == ([], "timeout")
        out, status = await build_minute(fetch, cache, "2330", 30, today)
        assert out == hist
        assert status == "timeout"  # 當日段那份 timeout 沒被洗白


class TestEmptyMarkStatusFidelity:
    """N-4 / SC-5:負向快取回的是**存入時的 status**,不得洗白成 ok。"""

    async def test_minute_empty_mark_replays_timeout(self) -> None:
        today = _dt.date(2026, 7, 28)
        clock = {"t": 0.0}
        fetch = _Fetcher([[], []], ["ok", "timeout"])
        cache = BarsCache(ttl=999.0, clock=lambda: clock["t"])
        assert (await build_minute(fetch, cache, "9999", 2, today)) == ([], "timeout")
        calls = len(fetch.calls)
        clock["t"] = EMPTY_TTL_SECS - 1.0
        assert (await build_minute(fetch, cache, "9999", 2, today)) == ([], "timeout")
        assert len(fetch.calls) == calls  # TTL 內不打 TC4,但原因照樣說得出來

    async def test_daily_empty_mark_replays_disconnected(self) -> None:
        today = _dt.date(2026, 7, 28)
        clock = {"t": 0.0}
        fetch = _Fetcher([[], []], ["disconnected", "ok"])
        cache = BarsCache(ttl=999.0, clock=lambda: clock["t"])
        assert (await build_daily(fetch, cache, "9999", today)) == ([], "disconnected")
        clock["t"] = EMPTY_TTL_SECS - 1.0
        assert (await build_daily(fetch, cache, "9999", today)) == ([], "disconnected")

    async def test_expired_mark_refetches_and_updates_status(self) -> None:
        """過期後恢復重抓,新的 status 取代舊的(不是永遠停在第一次的原因)。"""
        today = _dt.date(2026, 7, 28)
        clock = {"t": 0.0}
        fetch = _Fetcher([[], []], ["timeout", "ok"])
        cache = BarsCache(ttl=999.0, clock=lambda: clock["t"])
        assert (await build_daily(fetch, cache, "9999", today)).status == "timeout"
        clock["t"] = EMPTY_TTL_SECS + 1.0
        assert (await build_daily(fetch, cache, "9999", today)) == ([], "ok")
        assert len(fetch.calls) == 2


class TestUnknownStatusCoerced:
    """域外 status 字串的收斂點(review F2 / WL-COV-3)。

    `BarsStatus` 是 Literal —— **只在 pyright 期生效**,runtime 攔不住任何東西。
    注入面是實在的:`FakeStockSource.bars_status` 是裸 str,未來換 source 實作
    或欄位打錯字同理。而兩條 build_* 對未知值的反應原本剛好相反:
    `build_minute` 走 `worst_status` 的嚴格查表 → KeyError → 整條 route 500;
    `build_daily` 不經它 → 未知值原封寫進 `_empty` 再塞進 response,前端拿到一個
    不在白名單裡的字。前者太吵、後者太安靜,兩種都不對。

    裁定:一律收斂成 `"ok"` + warning log —— **與前端 `fetchBars` 的白名單正規化
    同語意**(未知 → ok)。不用 `"timeout"`:那會讓一個打錯字的欄位在畫面上長出
    「等待 TC4 回應中…」並每 20s 重試,把設定錯誤偽裝成基礎設施問題。
    """

    async def test_build_daily_coerces_unknown_status(self, caplog: pytest.LogCaptureFixture) -> None:
        today = _dt.date(2026, 7, 28)
        fetch = _Fetcher([[]], ["weird"])
        with caplog.at_level(logging.WARNING, logger="copycat.server.bars"):
            assert await build_daily(fetch, BarsCache(), "2330", today) == ([], "ok")
        assert any("weird" in r.message % r.args for r in caplog.records)

    async def test_build_minute_coerces_unknown_status(self, caplog: pytest.LogCaptureFixture) -> None:
        """原本這條會 KeyError → 500(`worst_status` 直接查表)。"""
        today = _dt.date(2026, 7, 28)
        fetch = _Fetcher([[], []], ["weird", "bogus"])
        with caplog.at_level(logging.WARNING, logger="copycat.server.bars"):
            assert await build_minute(fetch, BarsCache(ttl=999.0), "2330", 2, today) == ([], "ok")
        assert any("weird" in r.message % r.args for r in caplog.records)

    async def test_unknown_status_not_persisted_into_empty_mark(self) -> None:
        """域外值不得繞過收斂點滲進負向快取 —— 15s 內的重播會把它再送出去一次。"""
        today = _dt.date(2026, 7, 28)
        clock = {"t": 0.0}
        cache = BarsCache(ttl=999.0, clock=lambda: clock["t"])
        await build_daily(_Fetcher([[]], ["weird"]), cache, "9999", today)
        assert cache.empty_status("9999", "D", 0) == "ok"

    async def test_unknown_status_not_persisted_into_today_cache(self) -> None:
        today = _dt.date(2026, 7, 28)
        cache = BarsCache(ttl=999.0)
        await build_minute(_Fetcher([[], []], ["ok", "weird"]), cache, "2330", 2, today)
        entry = cache.today_get("2330", today.isoformat())
        assert entry is not None
        assert entry[1] == "ok"

    async def test_known_statuses_untouched(self) -> None:
        """收斂點不得把三態本身也一起壓平。"""
        today = _dt.date(2026, 7, 28)
        fetch = _Fetcher([[], []], ["timeout", "disconnected"])
        assert (await build_minute(fetch, BarsCache(ttl=999.0), "2330", 2, today)) == (
            [],
            "disconnected",
        )
