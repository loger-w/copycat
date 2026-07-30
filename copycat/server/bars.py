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
key 不含 days)。

**空結果的處理(round3 修訂)**:TC4 失敗與真無資料在上游不可分,所以空結果**不可
永久 cache** —— 否則斷線恢復後的重試路徑被釘死。但完全不 cache 也不行:TC4 查無該檔
時每次請求都要重付一次首頁等待 deadline(實測 60.1s,每次都一樣)。折衷 = **短 TTL
負向快取 `EMPTY_TTL_SECS`(15s < 前端 60s 輪詢)**,分兩層:

- `_empty`(code, tf, days):整份結果為空時標記,擋掉 15 秒內的重複請求。
- `today_put` / `today_get`:當日段自己的空也存,吃同一個短 TTL。這層是必要的 ——
  歷史有資料但今日零成交的冷門股,合併後的結果非空、永遠不會觸發上面那個標記。

`daily_put` 維持 don't-cache-empty(空由 `_empty` 那層負責)。
"""

from __future__ import annotations

import datetime as _dt
import logging
import time
from typing import Awaitable, Callable

from copycat.live.stock_source import Bar

logger = logging.getLogger(__name__)

TODAY_TTL_SECS = 30.0
#: 空結果的負向快取存活時間。**刻意短**:TC4 失敗與真無資料在上游不可分(見檔頭),
#: 永久快取會把斷線恢復後的重試路徑釘死。15s < 前端 60s 輪詢 → 交易時段內自動自癒,
#: 同時把「TC4 查無該檔 → 每次請求重付 60s 空等」收斂掉(round3 項 9)。
EMPTY_TTL_SECS = 15.0
DAYS_MIN = 1
DAYS_MAX = 30
DAILY_WINDOW_DAYS = 180  # 日曆日 ≈ 120 交易日(change-spec D-14)
DAILY_MAX_BARS = 120
#: 大盤頁日/週/月 K 共用的長窗(index-board N-1)。5 年 ≈ 1,220 根日 K,一次抓完後
#: 日 K / 週 K / 月 K 都由這一份衍生 —— 週月各自再打一次 TC4 是純粹的重工,而且
#: 三份窗長不同會讓「同一天的日 K 與週 K 對不起來」這種難查的不一致有機可乘。
DAILY_LONG_WINDOW_DAYS = 1825
DAILY_LONG_MAX_BARS = 1500  # 不截斷 5 年(留餘裕);上限只為防呆

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
        #: (code, tf, days) -> 寫入時刻。days 必須進 key —— 少了它,days=1 的空結果
        #: 會把 days=30 的請求一併釘住(spec review R15)。tf="D" 一律傳 days=0。
        self._empty: dict[tuple[str, str, int], float] = {}
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

    # ---- 空結果負向快取(短 TTL)----

    def empty_fresh(self, code: str, tf: str, days: int) -> bool:
        ts = self._empty.get((code, tf, days))
        return ts is not None and self._clock() - ts < EMPTY_TTL_SECS

    def empty_mark(self, code: str, tf: str, days: int) -> None:
        self._empty[(code, tf, days)] = self._clock()

    def empty_clear(self, code: str, tf: str, days: int) -> None:
        self._empty.pop((code, tf, days), None)

    # ---- 當日段(短 TTL)----

    def _today_ttl(self, bars: list[Bar]) -> float:
        """空結果吃更短的 TTL(見 `today_put`)。`today_get` 與 `prune` 共用同一條規則
        —— 各寫一份必然漂移。"""
        return self._ttl if bars else min(self._ttl, EMPTY_TTL_SECS)

    def today_get(self, code: str, today: str) -> list[Bar] | None:
        # key 含日期:只用 code 的話,server 跨午夜後的 TTL 窗內會把昨日 bars 當今日回,
        # 而歷史段此時已含昨日 → 同一回應出現重複 t(review P2-9)
        entry = self._today.get((code, today))
        if entry is None:
            return None
        if self._clock() - entry[0] >= self._today_ttl(entry[1]):
            return None
        return entry[1]

    def today_entry_count(self) -> int:
        """`_today` 的條目數(成長觀測用;prune 的 TTL evict 測試需要)。"""
        return len(self._today)

    def today_put(self, code: str, today: str, bars: list[Bar]) -> None:
        """空結果也存,但吃更短的 TTL(`EMPTY_TTL_SECS`)。

        原本空結果一律不存(don't-cache-empty)。問題是**歷史有資料但今日零成交**的
        股票(冷門股常態):`build_minute` 合併後的 `out` 因為歷史段非空而永不觸發
        `empty_mark`,當日段自己又不存空 → 每次請求都要重付一次 TC4 首頁等待
        (self-review B2)。短 TTL 兩邊都顧:15 秒內的重複請求免費,過期即重抓,
        該股一開始成交就看得到。"""
        self._today[(code, today)] = (self._clock(), bars)

    def prune(self, today: _dt.date) -> None:
        """剪掉視窗外與已過期的條目。

        `_hist` / `_daily` 的成長來自**日期維度**(股號受 watchlist 30 檔上限約束)
        —— review P2-5。`_today` 從 round3 起會存空 entry,股號維度不再被「真的有今日
        資料的股號」約束(任何通過 `validate_code` 的字串請求一次就留一筆),所以
        除了日期還要按 TTL evict —— 否則同日內累積到跨日才歸零(self-review round2 P2)。
        """
        floor = (today - _dt.timedelta(days=DAYS_MAX * 2)).isoformat()
        for key in [k for k in self._hist if k[1] < floor]:
            del self._hist[key]
        today_iso = today.isoformat()
        for key in [k for k in self._daily if k[1] != today_iso]:
            del self._daily[key]
        now = self._clock()
        for key in [
            k
            for k, e in self._today.items()
            if k[1] != today_iso or now - e[0] >= self._today_ttl(e[1])
        ]:
            del self._today[key]
        # 只丟已過期的:prune 每次 build_* 開頭都會跑,無條件 clear 等於負向快取從未生效
        for key in [k for k, ts in self._empty.items() if now - ts >= EMPTY_TTL_SECS]:
            del self._empty[key]

    # ---- 日 K(per (code, today) memo)----

    def daily_get(self, code: str, today: str) -> list[Bar] | None:
        return self._daily.get((code, today))

    def daily_put(self, code: str, today: str, bars: list[Bar]) -> None:
        if not bars:
            return  # don't-cache-empty
        self._daily[(code, today)] = bars


async def build_daily(
    fetch: BarsFetcher,
    cache: BarsCache,
    code: str,
    today: _dt.date,
    *,
    window_days: int = DAILY_WINDOW_DAYS,
    max_bars: int = DAILY_MAX_BARS,
    cache_key: str | None = None,
) -> list[Bar]:
    """日 K(per (cache_key, today) memo)。

    `cache_key` 讓同一個 `code` 的不同窗長各自佔一個快取格 —— 大盤頁的長窗日 K
    與個股頁的 180 日窗共用 `code` 會互相覆寫,取到誰全看誰先到(index-board N-1)。
    預設 `None` = 沿用 `code`,既有呼叫端行為完全不變。
    """
    key = cache_key if cache_key is not None else code
    cache.prune(today)
    cached = cache.daily_get(key, today.isoformat())
    if cached is not None:
        return cached
    # 短 TTL 負向快取:上一次剛確認過沒資料,不必再等一輪 TC4 首頁 deadline
    if cache.empty_fresh(key, "D", 0):
        return []
    start = today - _dt.timedelta(days=window_days)
    bars = (await fetch(code, "D", start.isoformat(), today.isoformat()))[-max_bars:]
    cache.daily_put(key, today.isoformat(), bars)
    if bars:
        cache.empty_clear(key, "D", 0)
    else:
        cache.empty_mark(key, "D", 0)
    return bars


def _period_key(stamp: str, period: str) -> str | None:
    """日 bar 的 `t`(YYYY-MM-DD)→ 桶鍵;非日 bar / 壞日期 → None(丟棄,不猜)。

    **W 用 ISO 年-週**:2025-12-29 ~ 2026-01-02 同屬 ISO 2026-W01,用曆年 + 週號
    當鍵會把跨年那一週拆成兩桶。
    """
    if len(stamp) != 10:  # 分 K 的 `t` 是 "YYYY-MM-DD HH:MM"
        return None
    try:
        d = _dt.date.fromisoformat(stamp)
    except ValueError:
        return None
    if period == "M":
        return stamp[:7]
    iso = d.isocalendar()
    return f"{iso[0]:04d}-W{iso[1]:02d}"


def aggregate_period(bars: list[Bar], period: str) -> list[Bar]:
    """日 Bar → 週("W")/ 月("M") Bar。

    **桶鍵取實際日期**(ISO 年-週 / 年-月),不是「每 N 根一組」—— 連假 / 補班週的
    交易日數不固定,固定根數分組會累積錯位,而且圖形看起來完全正常、沒有任何斷言
    會紅(change-spec §1.2)。

    o = 桶內第一根 o、h = max、l = min、c = 最後一根 c、v = Σv;
    `t` 取桶內**最後一個實際交易日**(右端對齊;不憑空造出非交易日的月底日期)。
    """
    out: list[Bar] = []
    cur_key: str | None = None
    for b in sorted(bars, key=lambda x: x["t"]):
        key = _period_key(b["t"], period)
        if key is None:
            continue
        if key != cur_key:
            out.append(Bar(t=b["t"], o=b["o"], h=b["h"], l=b["l"], c=b["c"], v=b["v"]))
            cur_key = key
            continue
        agg = out[-1]
        agg["t"] = b["t"]
        agg["h"] = max(agg["h"], b["h"])
        agg["l"] = min(agg["l"], b["l"])
        agg["c"] = b["c"]
        agg["v"] += b["v"]
    return out


async def build_period(
    fetch: BarsFetcher, cache: BarsCache, code: str, today: _dt.date, period: str
) -> list[Bar]:
    """大盤頁的日 / 週 / 月 K —— 三者共用同一份長窗日 K(見 `DAILY_LONG_WINDOW_DAYS`)。

    `period`:`"D"` 原樣回、`"W"` / `"M"` 走 `aggregate_period`。
    """
    daily = await build_daily(
        fetch,
        cache,
        code,
        today,
        window_days=DAILY_LONG_WINDOW_DAYS,
        max_bars=DAILY_LONG_MAX_BARS,
        cache_key=f"{code}|L",
    )
    if period == "D":
        return daily
    return aggregate_period(daily, period)


async def build_minute(
    fetch: BarsFetcher, cache: BarsCache, code: str, days: int, today: _dt.date
) -> list[Bar]:
    """近 `days` 個日曆日的 1 分 bar(歷史 memo + 當日 TTL 拼接)。"""
    cache.prune(today)
    if cache.empty_fresh(code, "1", days):
        return []
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
    # 兩段都空 = 這檔在 TC4 查不到(或 TC4 正忙)。標記 15 秒,期間的重複請求直接回空,
    # 不再各付一次首頁 deadline。過期即自動重試(W-15)。
    if out:
        cache.empty_clear(code, "1", days)
    else:
        cache.empty_mark(code, "1", days)
    return out
