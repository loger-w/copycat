from __future__ import annotations

import datetime as _dt

from copycat.live.stock_source import Bar
from copycat.server.bars import (
    DAILY_MAX_BARS,
    BarsCache,
    build_daily,
    build_minute,
    clamp_days,
)


def bar(t: str, c: int = 100, v: int = 1) -> Bar:
    return {"t": t, "o": c, "h": c, "l": c, "c": c, "v": v}


class _Fetcher:
    """engine.bars_range 替身:記錄每次呼叫的區間。"""

    def __init__(self, by_call: list[list[Bar]] | None = None) -> None:
        self.calls: list[tuple[str, str, str, str]] = []
        self._by_call = by_call

    async def __call__(self, code: str, tf: str, start: str, end: str) -> list[Bar]:
        self.calls.append((code, tf, start, end))
        if self._by_call is not None:
            idx = len(self.calls) - 1
            return self._by_call[idx] if idx < len(self._by_call) else []
        return []


class TestClampDays:
    def test_clamped_to_range(self) -> None:
        assert clamp_days(0) == 1
        assert clamp_days(5) == 5
        assert clamp_days(999) == 30


class TestDailyCache:
    async def test_daily_memo_hits_second_call(self) -> None:
        today = _dt.date(2026, 7, 28)
        fetch = _Fetcher([[bar("2026-07-27")]])
        cache = BarsCache()
        assert await build_daily(fetch, cache, "2330", today) == [bar("2026-07-27")]
        assert await build_daily(fetch, cache, "2330", today) == [bar("2026-07-27")]
        assert len(fetch.calls) == 1  # 第二次全走 memo

    async def test_daily_empty_not_cached(self) -> None:
        # don't-cache-empty:TC4 失敗與真無資料上游不可分,要留重試餘地
        fetch = _Fetcher([[], [bar("2026-07-27")]])
        cache = BarsCache()
        assert await build_daily(fetch, cache, "2330", _dt.date(2026, 7, 28)) == []
        assert await build_daily(fetch, cache, "2330", _dt.date(2026, 7, 28)) != []
        assert len(fetch.calls) == 2

    async def test_daily_tail_limited_to_120(self) -> None:
        many = [bar(f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}") for i in range(200)]
        fetch = _Fetcher([many])
        bars = await build_daily(fetch, BarsCache(), "2330", _dt.date(2026, 7, 28))
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
        assert first == hist + cur
        second = await build_minute(fetch, cache, "2330", 2, today)
        assert second == hist + cur
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
        out = await build_minute(fetch, cache, "2330", 2, today)  # TTL 過 → 只重抓當日
        assert len(fetch.calls) == 3
        assert out[-1]["t"] == "2026-07-28 09:02"  # SC-10:最後一根會前進

    async def test_empty_history_not_negatively_cached(self) -> None:
        """整段回空可能是 TC4 失敗 → 不可寫負向快取,否則被永久釘成空。"""
        today = _dt.date(2026, 7, 28)
        fetch = _Fetcher([[], [], [bar("2026-07-27 09:01")], []])
        cache = BarsCache(ttl=999.0)
        await build_minute(fetch, cache, "2330", 2, today)
        assert cache.hist_missing("2330", _dt.date(2026, 7, 27), _dt.date(2026, 7, 27)) != []
        out = await build_minute(fetch, cache, "2330", 2, today)
        assert out == [bar("2026-07-27 09:01")]

    async def test_days_1_skips_history_segment(self) -> None:
        today = _dt.date(2026, 7, 28)
        fetch = _Fetcher([[bar("2026-07-28 09:01")]])
        await build_minute(fetch, BarsCache(), "2330", 1, today)
        assert [c[1:] for c in fetch.calls] == [("1", "2026-07-28", "2026-07-28")]

    async def test_today_empty_not_cached(self) -> None:
        today = _dt.date(2026, 7, 28)
        fetch = _Fetcher([[], [bar("2026-07-28 09:01")]])
        cache = BarsCache(ttl=999.0)
        assert await build_minute(fetch, cache, "2330", 1, today) == []
        assert await build_minute(fetch, cache, "2330", 1, today) != []
