"""K 線 bar 組裝與 cache(SC-7;change-spec 🟢-4 + R2-2)。

分 K 的成本控制全押在這層:前端交易時段每 60s 輪詢,若每次都重拉整段歷史,
會反覆佔用 TC4 的 REQ 往返(`tc4.py:214 api.lock`,粒度=單次 REQ、範圍=同一 source)。

兩段式:

- **歷史段**(`date < today`):per (code, date) memo(視窗外由 `prune` 剪除)。
  已完成交易日的 1K 不會再變。關鍵是 **負向快取** —— 一次區間抓取後,無資料的日曆日
  也寫空 list。窗內必有週末/假日,少了負向快取就會「永遠缺、每次重拉」,等於沒 cache
  (change-spec R2-2)。但負向快取**只寫到有證據掃過的最後一天**,TC4 分頁截斷時
  不把後面的日子誤釘成空(review P1-2)。
- **當日段**:短 TTL(預設 30s,短於前端 60s 輪詢),讓盤中最後一根會前進(SC-10)。

`tf="D"` 不走兩段式:日 K 當日內不過期,整份 per (code, today) memo 即可(D-15:
key 不含 days)。空結果一律不 cache —— TC4 失敗與真無資料在上游不可分,
don't-cache-empty 讓斷線恢復後可重試(同 `OverlayCache` 慣例)。
"""

from __future__ import annotations

import datetime as _dt
import logging
import time
from typing import Awaitable, Callable

from copycat.live.stock_source import Bar

logger = logging.getLogger(__name__)

TODAY_TTL_SECS = 30.0
DAYS_MIN = 1
DAYS_MAX = 30
DAILY_WINDOW_DAYS = 180  # 日曆日 ≈ 120 交易日(change-spec D-14)
DAILY_MAX_BARS = 120

#: engine.bars_range(code, tf, start_date, end_date) -> list[Bar]
BarsFetcher = Callable[[str, str, str, str], Awaitable[list[Bar]]]


def clamp_days(days: int) -> int:
    return max(DAYS_MIN, min(DAYS_MAX, days))


def _iter_days(start: _dt.date, end: _dt.date):
    d = start
    while d <= end:
        yield d
        d += _dt.timedelta(days=1)


class BarsCache:
    def __init__(self, ttl: float = TODAY_TTL_SECS, clock: Callable[[], float] = time.monotonic):
        self._hist: dict[tuple[str, str], list[Bar]] = {}
        self._today: dict[tuple[str, str], tuple[float, list[Bar]]] = {}
        self._daily: dict[tuple[str, str], list[Bar]] = {}
        self._ttl = ttl
        self._clock = clock

    # ---- 歷史段(永久 memo,含負向快取)----

    def hist_missing(self, code: str, start: _dt.date, end: _dt.date) -> list[_dt.date]:
        return [d for d in _iter_days(start, end) if (code, d.isoformat()) not in self._hist]

    def put_hist_range(self, code: str, start: _dt.date, end: _dt.date, bars: list[Bar]) -> None:
        """把一次區間抓取的結果攤進 per-day memo;沒資料的日子寫空 list(負向快取)。

        **負向快取只寫到「有證據掃過」的最後一天**:TC4 分頁可能提早截斷
        (`tc4common.iter_qry_pages` 遇 QryIndex 停滯即靜默結束,不區分收完與異常中斷),
        若無條件把整段寫空,截斷後缺的日子會被永久釘成空、只能重啟 server 才恢復
        (review P1-2)。已有非空值的日子也不被空值覆寫。"""
        by_date: dict[str, list[Bar]] = {}
        for b in bars:
            by_date.setdefault(b["t"][:10], []).append(b)
        last_seen = max(by_date) if by_date else None
        for d in _iter_days(start, end):
            key = d.isoformat()
            got = by_date.get(key)
            if got:
                self._hist[(code, key)] = got
            elif last_seen is not None and key <= last_seen:
                self._hist.setdefault((code, key), [])

    def hist_range(self, code: str, start: _dt.date, end: _dt.date) -> list[Bar]:
        out: list[Bar] = []
        for d in _iter_days(start, end):
            out.extend(self._hist.get((code, d.isoformat()), []))
        return out

    # ---- 當日段(短 TTL)----

    def today_get(self, code: str, today: str) -> list[Bar] | None:
        # key 含日期:只用 code 的話,server 跨午夜後的 TTL 窗內會把昨日 bars 當今日回,
        # 而歷史段此時已含昨日 → 同一回應出現重複 t(review P2-9)
        entry = self._today.get((code, today))
        if entry is None or self._clock() - entry[0] >= self._ttl:
            return None
        return entry[1]

    def today_put(self, code: str, today: str, bars: list[Bar]) -> None:
        if not bars:
            return  # don't-cache-empty
        self._today[(code, today)] = (self._clock(), bars)

    def prune(self, today: _dt.date) -> None:
        """剪掉視窗外條目。三個 dict 都無 evict,長跑 server 的成長主要來自**日期維度**
        (股號受 watchlist 30 檔上限約束,日期不受)—— review P2-5。"""
        floor = (today - _dt.timedelta(days=DAYS_MAX * 2)).isoformat()
        for key in [k for k in self._hist if k[1] < floor]:
            del self._hist[key]
        today_iso = today.isoformat()
        for key in [k for k in self._daily if k[1] != today_iso]:
            del self._daily[key]
        for key in [k for k in self._today if k[1] != today_iso]:
            del self._today[key]

    # ---- 日 K(per (code, today) memo)----

    def daily_get(self, code: str, today: str) -> list[Bar] | None:
        return self._daily.get((code, today))

    def daily_put(self, code: str, today: str, bars: list[Bar]) -> None:
        if not bars:
            return  # don't-cache-empty
        self._daily[(code, today)] = bars


async def build_daily(
    fetch: BarsFetcher, cache: BarsCache, code: str, today: _dt.date
) -> list[Bar]:
    cache.prune(today)
    cached = cache.daily_get(code, today.isoformat())
    if cached is not None:
        return cached
    start = today - _dt.timedelta(days=DAILY_WINDOW_DAYS)
    bars = (await fetch(code, "D", start.isoformat(), today.isoformat()))[-DAILY_MAX_BARS:]
    cache.daily_put(code, today.isoformat(), bars)
    return bars


async def build_minute(
    fetch: BarsFetcher, cache: BarsCache, code: str, days: int, today: _dt.date
) -> list[Bar]:
    """近 `days` 個日曆日的 1 分 bar(歷史 memo + 當日 TTL 拼接)。"""
    cache.prune(today)
    start = today - _dt.timedelta(days=clamp_days(days) - 1)
    yesterday = today - _dt.timedelta(days=1)

    out: list[Bar] = []
    if start <= yesterday:
        missing = cache.hist_missing(code, start, yesterday)
        if missing:
            # 只補缺口區間(端點取 min/max;中間已 memo 的日子重抓無害,省下逐日 REQ)
            lo, hi = missing[0], missing[-1]
            fetched = await fetch(code, "1", lo.isoformat(), hi.isoformat())
            if fetched:
                cache.put_hist_range(code, lo, hi, fetched)
            else:
                # 全空:可能是 TC4 失敗,不寫負向快取(否則整段被永久釘成空)
                logger.info("bars %s: 歷史段 %s..%s 回空,不入 memo", code, lo, hi)
        out.extend(cache.hist_range(code, start, yesterday))

    today_bars = cache.today_get(code, today.isoformat())
    if today_bars is None:
        today_bars = await fetch(code, "1", today.isoformat(), today.isoformat())
        cache.today_put(code, today.isoformat(), today_bars)
    out.extend(today_bars)
    return out
