"""歷史段 missing 接交易日曆過濾(bug/futures-bars-gap)。

現象:週一的 days=5 窗尾是週日,`put_hist_range` 的負向快取只寫到「有證據掃過的
最後一天」(防 TC4 分頁截斷),窗尾的非交易日因此**永遠**不入 memo → 每次
`build_minute` 都對 TC4 重發一次「週日單日」1K 查詢;TC4 對無資料日不回首頁,
每次白付 10s deadline,且那個 timeout 還會汙染整體 status。

這裡鎖的是:missing 先被交易日曆過濾掉「不可能有資料的日子」,過濾後為空就
一發 fetch 都不出去。`calendar=None` 維持逐字舊行為(既有測試全部不傳)。
"""

from __future__ import annotations

import datetime as _dt

from copycat.live.stock_source import Bar, BarsStatus
from copycat.server.bars import BarsCache, BarsResult, _possible_data_days, build_minute
from copycat.trading_calendar import TradingCalendar

# 空 holidays → 週末即非交易日;2026 標成已載入,避免退化語意混進斷言。
CAL = TradingCalendar(
    holidays=frozenset(),
    extra_trading_days=frozenset(),
    years_loaded=frozenset({2026}),
)

TODAY = _dt.date(2026, 8, 24)  # 週一;days=5 → 窗 = 08-20(四)..08-24(一)
CODE = "F:TXF"


def bar(t: str, c: int = 100, v: int = 1) -> Bar:
    return {"t": t, "o": c, "h": c, "l": c, "c": c, "v": v}


class _RecordingFetcher:
    """記錄每一次呼叫;today 段回 ok + 一根,其餘一律 `([], "timeout")`。

    非 today 段固定 timeout **是真實現象的忠實替身**:TC4 對無資料日不回首頁,
    掛滿 deadline 後上游只能報 timeout(「timeout」與「真無資料」在 TC4 協議上
    不可分)。替身若回 ok,這條 bug 的 status 汙染面就測不到。
    """

    def __init__(self, today: _dt.date = TODAY) -> None:
        self.calls: list[tuple[str, str, str, str]] = []
        self._today = today.isoformat()

    async def __call__(self, code: str, tf: str, start: str, end: str) -> BarsResult:
        self.calls.append((code, tf, start, end))
        if start == self._today and end == self._today:
            return BarsResult([bar(f"{self._today} 09:01")], "ok")
        return BarsResult([], "timeout")

    @property
    def hist_calls(self) -> list[tuple[str, str, str, str]]:
        return [c for c in self.calls if c[3] != self._today]


def _seed(cache: BarsCache, session: str, days: list[str]) -> None:
    """把 `days` 逐日種進歷史 memo(每天一根)。"""
    ck = f"{CODE}:{session}"
    lo = _dt.date.fromisoformat(days[0])
    hi = _dt.date.fromisoformat(days[-1])
    cache.put_hist_range(ck, lo, hi, [bar(f"{d} 09:01") for d in days])


class TestNonTradingDayNotRefetched:
    async def test_pure_non_trading_gap_sends_no_history_fetch(self) -> None:
        """窗尾只剩週日 → 一發歷史 fetch 都不該出去(每次白付 10s deadline 的來源)。"""
        cache = BarsCache(ttl=999.0)
        # 08-22(六)有資料 = 週五夜盤尾 00:00-05:00,近全序列的常態
        _seed(cache, "allday", ["2026-08-20", "2026-08-21", "2026-08-22"])
        fetch = _RecordingFetcher()

        out, status = await build_minute(
            fetch, cache, CODE, 5, TODAY, session="allday", calendar=CAL
        )

        assert fetch.hist_calls == []
        assert [c[1:] for c in fetch.calls] == [("1", "2026-08-24", "2026-08-24")]
        assert [b["t"] for b in out] == [
            "2026-08-20 09:01",
            "2026-08-21 09:01",
            "2026-08-22 09:01",
            "2026-08-24 09:01",
        ]
        assert status == "ok"

    async def test_status_not_polluted_by_impossible_day(self) -> None:
        """(b) 整體 status = today 段的 status,不被不可能有資料的日子汙染。"""
        cache = BarsCache(ttl=999.0)
        _seed(cache, "allday", ["2026-08-20", "2026-08-21", "2026-08-22"])
        fetch = _RecordingFetcher()

        status: BarsStatus = (
            await build_minute(fetch, cache, CODE, 5, TODAY, session="allday", calendar=CAL)
        ).status

        assert status == "ok"

    async def test_real_trading_day_gap_still_fetched_with_filtered_endpoints(self) -> None:
        """(c) 對照組:missing 含真交易日照樣發 fetch,端點取**過濾後**的 min/max。"""
        cache = BarsCache(ttl=999.0)
        _seed(cache, "allday", ["2026-08-20"])
        fetch = _RecordingFetcher()

        await build_minute(fetch, cache, CODE, 5, TODAY, session="allday", calendar=CAL)

        # missing = 08-21(五) 08-22(六) 08-23(日);allday 規則保留「當日或前一日是交易日」
        # → 08-21 保留、08-22 保留(週五夜盤尾)、08-23 剔除 → 端點 08-21..08-22
        assert [c[1:] for c in fetch.hist_calls] == [("1", "2026-08-21", "2026-08-22")]

    async def test_day_session_filters_saturday_too(self) -> None:
        """day 盤別沒有夜盤尾 → 週六一併剔除(allday 下週六可有資料,兩者規則不同)。"""
        cache = BarsCache(ttl=999.0)
        _seed(cache, "day", ["2026-08-20"])
        fetch = _RecordingFetcher()

        await build_minute(fetch, cache, CODE, 5, TODAY, session="day", calendar=CAL)

        assert [c[1:] for c in fetch.hist_calls] == [("1", "2026-08-21", "2026-08-21")]

    async def test_no_calendar_keeps_old_behavior(self) -> None:
        """`calendar=None`(既有全部呼叫點)逐字舊行為:純非交易日缺口照樣發 fetch。"""
        cache = BarsCache(ttl=999.0)
        _seed(cache, "allday", ["2026-08-20", "2026-08-21", "2026-08-22"])
        fetch = _RecordingFetcher()

        out, status = await build_minute(fetch, cache, CODE, 5, TODAY, session="allday")

        assert [c[1:] for c in fetch.hist_calls] == [("1", "2026-08-23", "2026-08-23")]
        assert status == "timeout"
        assert out  # 回應內容不受影響(memo + 當日段)


def test_holiday_filtered_like_weekend_and_night_tail_kept() -> None:
    """假日與週末同權(review C3):國定假日(平日)被剔除;其前一交易日的夜盤尾日保留。

    2026-09-25(五)/ 09-28(一)設為假日:day 盤別只留 09-24(四);allday 額外留
    09-25(週四夜盤尾 00:00-05:00 落在週五),09-26/27/28 前一日皆非交易日 → 剔除。
    """
    cal = TradingCalendar(
        holidays=frozenset({_dt.date(2026, 9, 25), _dt.date(2026, 9, 28)}),
        extra_trading_days=frozenset(),
        years_loaded=frozenset({2026}),
    )
    days = [_dt.date(2026, 9, d) for d in range(24, 29)]
    assert _possible_data_days(days, "day", cal) == [_dt.date(2026, 9, 24)]
    assert _possible_data_days(days, "allday", cal) == [
        _dt.date(2026, 9, 24),
        _dt.date(2026, 9, 25),
    ]
