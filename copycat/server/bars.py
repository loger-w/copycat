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

`tf="D"` 不走兩段式,整份 per (code, today) memo(D-15:key 不含 days),但有一道
**定稿界**(`DAILY_FINAL_TIME`,bug/futures-daily-cache-night):界前寫入的快照(今日
bar 仍在進行)過界即作廢一次,界後寫入視為定稿、釘到跨日 prune。作廢後 refetch 拿空手
(TC4 關/忙)→ 墊背回舊快照(`daily_stale`)—— 沒消息不可蓋掉舊消息。

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
from typing import Awaitable, Callable, NamedTuple, cast

from copycat.live.stock_source import Bar, BarsStatus
from copycat.trading_calendar import TradingCalendar

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

#: 午夜緩衝窗的**結束時刻**(台北牆鐘)。這段期間內不把 `yesterday` 寫進永久 memo。
#: 10 分鐘 = 「TC4 把上一個台北日的尾根寫進 1K 分頁」的寬限;比它更長只是多付幾次
#: 歷史段往返(而且午夜本來就沒什麼人在看盤),更短則救不到真正晚寫的那幾根(TZ-2)。
MIDNIGHT_BUFFER_END = _dt.time(0, 10)

#: 日 K 快照的**定稿界**(台北牆鐘;bug/futures-daily-cache-night)。界前寫入的 `_daily`
#: memo(今日 bar 仍在進行)過界即作廢一次;界後寫入視為定稿。少了這道界,早上首抓的
#: 部分 bar 釘到午夜 —— 期貨 15:00 錨定日翻頁後,前端 `futures-overlay` 要前一交易日的
#: **完整** D bar 當 CDP/MA 基準,15:01–24:00 拿到的全是早上那截,圖照樣畫得出來、
#: 零錯誤訊號。取 14:00:晚於全部日盤收盤(現貨 13:30/13:33、期貨日盤 13:45)留 TC4
#: 把定稿寫進 DK 的寬限(寫入時點未實測,界後寫入即永久 → 寬限要給足),早於 15:00
#: 夜盤開盤 / 錨定翻頁(消費者最早需要點 15:01)。成本:成功路徑上界 = 每 code 每天
#: 多一次 DK 取數;refetch 失敗窗(TC4 關/忙)的重試由**下一個請求**驅動(cache 無背景
#: refresher),節奏上限 = 每 `EMPTY_TTL_SECS` 至多一次 —— 且墊背回的是**非空**快照,
#: 前端三條空態自癒(retryEmpty / barsPollInterval / index overlay 輪詢)都不會被觸發,
#: 掛著的分頁到午夜才會再問(實務上 = F5 才重試;期間讀者拿 `daily_stale` 墊背,
#: 不是空白 —— pr-165-review #3 改口徑,行為不變)。
#: 另一個 14:00 讀者:app.py `_calendar_crosscheck`(語意 = 今日 IX0001 DK **存在**了沒、
#: boot 只跑一次)—— 與本界(**定稿**了沒)不同問題,刻意分家不共用常數;改任一值前
#: 先看對方(pr-165-review #1)。
DAILY_FINAL_TIME = _dt.time(14, 0)


def _now_time() -> _dt.time:
    """本機牆鐘時刻(server 跑在台北)。**獨立成 module 級函式 = 測試唯一的凍結點**
    —— 內嵌 `datetime.now()` 的話這條競態就只能靠真的跑到半夜才驗得到。"""
    return _dt.datetime.now().time()


class BarsResult(NamedTuple):
    """bars + 空結果的原因(`BarsStatus`)。

    **刻意做成 NamedTuple 而不是裸 tuple**:與 `TaggedBars` 同構(`BarsStatus` 是
    `str` 的 Literal 子型別),裸 tuple 下把帶 status 的 fetcher 誤傳給 `build_period`
    型別合法,結果是大盤 meta 的「來源」欄靜默變成 `"ok"` —— 一個沒人會第一眼認出
    是 bug 的字(spec R5)。
    """

    bars: list[Bar]
    status: BarsStatus


class TaggedBars(NamedTuple):
    """bars + 實際走到的資料源標籤(大盤 meta 用;與 `BarsResult` 刻意不可互換)。"""

    bars: list[Bar]
    tag: str


#: 嚴重度:壞消息不可被好消息蓋掉,所以合併一律取 max。
_STATUS_SEVERITY: dict[BarsStatus, int] = {"ok": 0, "timeout": 1, "disconnected": 2}


def worst_status(*statuses: BarsStatus) -> BarsStatus:
    """SC-6:多段結果的 status = 最壞值(disconnected > timeout > ok)。

    一個引數都沒有(兩段全 cache 命中、一次 fetch 都沒發)→ `"ok"`:沒發請求就
    沒有壞消息可報,把它算成上一輪的原因等於讓過期的診斷永遠黏著。
    """
    worst: BarsStatus = "ok"
    for s in statuses:
        if _STATUS_SEVERITY[s] > _STATUS_SEVERITY[worst]:
            worst = s
    return worst


def _coerce_status(status: str) -> BarsStatus:
    """fetcher 回來的 status 的唯一收斂點(review F2 / WL-COV-3)。

    `BarsStatus` 是 Literal —— **只在 pyright 期生效**,runtime 什麼都攔不住,
    而注入面是實在的(fake source 的欄位是裸 str,真實 source 也可能打錯字)。
    少了這道收斂,`worst_status` 的嚴格查表會 KeyError 把整條 route 打成 500,
    而 `build_daily` 那條不經它、會把未知值原封送進前端。

    未知 → `"ok"` + warning:**與前端 `fetchBars` 的白名單正規化同語意**,
    兩端對稱才不會出現「後端說 timeout、前端當 ok」這種零訊號的矛盾態。
    不用 `"timeout"` —— 那會讓一個打錯字的欄位在畫面上長出「等待 TC4 回應中…」
    並每 20s 重試,把設定錯誤偽裝成基礎設施問題。
    """
    if status in _STATUS_SEVERITY:
        return cast("BarsStatus", status)
    logger.warning("bars: 未知的 status %r,收斂為 ok", status)
    return "ok"


#: engine.bars_range(code, tf, start_date, end_date) -> BarsResult
BarsFetcher = Callable[[str, str, str, str], Awaitable[BarsResult]]


def clamp_days(days: int) -> int:
    return max(DAYS_MIN, min(DAYS_MAX, days))


def _iter_days(start: _dt.date, end: _dt.date):
    d = start
    while d <= end:
        yield d
        d += _dt.timedelta(days=1)


def _possible_data_days(
    days: list[_dt.date], session: str, calendar: TradingCalendar | None
) -> list[_dt.date]:
    """把「不可能有資料的日子」從 missing 清單濾掉(bug/futures-bars-gap)。

    為什麼需要:`put_hist_range` 的負向快取**只寫到有證據掃過的最後一天**(防 TC4
    分頁截斷把後面的日子永久釘成空,review P1-2 —— 那條取捨不動)。代價是窗尾的
    非交易日永遠不入 memo:週一的 days=5 窗尾是週日,allday 序列裡週六因為有週五
    夜盤尾而有資料、週日真的沒有 → 週日**永久 missing**,每次 build_minute 都對
    TC4 重發一次「週日單日」1K 查詢。TC4 對無資料日不回首頁,每次白付 10s deadline
    (2026-08-24 全日 log:28 次歷史段 timeout,範圍全部是 08-23(日)),而且那個
    timeout 還會經 `worst_status` 汙染整體 status。前端切商品時的表現就是圖空白 10s。

    盤別規則不同:
    - `day`:只有交易日當天有 08:45-13:45 的日盤。
    - `allday`:再加上「前一日是交易日」—— 夜盤跨午夜到 05:00,週五夜盤的尾巴落在
      週六。所以 allday 下的週六可以有資料,週日不行。

    `calendar is None` → 不過濾(逐字舊行為)。日曆缺年時 `is_trading_day` 退化成
    只擋週末,永不多擋 —— 最壞是回到本修之前的行為。
    """
    if calendar is None:
        return days
    if session == "allday":
        return [
            d
            for d in days
            if calendar.is_trading_day(d) or calendar.is_trading_day(d - _dt.timedelta(days=1))
        ]
    return [d for d in days if calendar.is_trading_day(d)]


class BarsCache:
    def __init__(self, ttl: float = TODAY_TTL_SECS, clock: Callable[[], float] = time.monotonic):
        self._hist: dict[tuple[str, str], list[Bar]] = {}
        #: (code, today) -> (寫入時刻, bars, 寫入時的 status)。**status 要存**:
        #: `_empty` 的 key 含 days 而這層不含,days=1 的當日段 timeout 寫入後,15s 內
        #: days=30 的請求會 `empty_status` 未命中、`today_get` 命中那份源自 timeout 的
        #: 空 —— 若視為 ok 就把 timeout 洗白了(spec R4;違反 SC-5)。
        self._today: dict[tuple[str, str], tuple[float, list[Bar], BarsStatus]] = {}
        self._daily: dict[tuple[str, str], list[Bar]] = {}
        #: 與 `_daily` 同鍵的資料源標籤(大盤 meta 用)。分開存而不塞進值:
        #: `_daily` 的值型別是 `list[Bar]`,個股路徑四個呼叫點都吃它
        self._daily_tag: dict[tuple[str, str], str] = {}
        #: (code, tf, days) -> (寫入時刻, 空的原因)。days 必須進 key —— 少了它,
        #: days=1 的空結果會把 days=30 的請求一併釘住(spec review R15)。
        #: tf="D" 一律傳 days=0。**原因要存**:15s 內的重複請求若一律回 ok,
        #: 「還在等 TC4」就被快取洗成「這檔沒資料」(SC-5)。
        self._empty: dict[tuple[str, str, int], tuple[float, BarsStatus]] = {}
        #: 定稿界(`DAILY_FINAL_TIME`)**之前**寫入的 `_daily` 鍵:過界後 `daily_get`
        #: 視為過期(entry 本體保留,`daily_stale` 當墊背)。用集合不改 `_daily` 值型別
        #: —— 與 `_daily_tag` 分開存的同一條理由(個股路徑呼叫點都吃 `list[Bar]`)。
        #: 注意:本 class 從此有**兩把鐘** —— 注入的 `clock`(monotonic,TTL 用)與
        #: module 級 `_now_time()`(牆鐘,定稿界用;測試凍結點與午夜緩衝同一支)。
        self._daily_pre_final: set[tuple[str, str]] = set()
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

    def empty_status(self, code: str, tf: str, days: int) -> BarsStatus | None:
        """未過期的空標記 → 存入時的 status;無標記 / 已過期 → None。

        回 status 而不是 bool:呼叫端要能把「為什麼空」原封不動送出去(SC-5)。
        """
        entry = self._empty.get((code, tf, days))
        if entry is None or self._clock() - entry[0] >= EMPTY_TTL_SECS:
            return None
        return entry[1]

    def empty_mark(self, code: str, tf: str, days: int, status: BarsStatus) -> None:
        self._empty[(code, tf, days)] = (self._clock(), status)

    def empty_clear(self, code: str, tf: str, days: int) -> None:
        self._empty.pop((code, tf, days), None)

    # ---- 當日段(短 TTL)----

    def _today_ttl(self, bars: list[Bar]) -> float:
        """空結果吃更短的 TTL(見 `today_put`)。`today_get` 與 `prune` 共用同一條規則
        —— 各寫一份必然漂移。"""
        return self._ttl if bars else min(self._ttl, EMPTY_TTL_SECS)

    def today_get(self, code: str, today: str) -> tuple[list[Bar], BarsStatus] | None:
        # key 含日期:只用 code 的話,server 跨午夜後的 TTL 窗內會把昨日 bars 當今日回,
        # 而歷史段此時已含昨日 → 同一回應出現重複 t(review P2-9)
        entry = self._today.get((code, today))
        if entry is None:
            return None
        if self._clock() - entry[0] >= self._today_ttl(entry[1]):
            return None
        return entry[1], entry[2]

    def today_entry_count(self) -> int:
        """`_today` 的條目數(成長觀測用;prune 的 TTL evict 測試需要)。"""
        return len(self._today)

    def today_put(self, code: str, today: str, bars: list[Bar], status: BarsStatus) -> None:
        """空結果也存,但吃更短的 TTL(`EMPTY_TTL_SECS`)。

        原本空結果一律不存(don't-cache-empty)。問題是**歷史有資料但今日零成交**的
        股票(冷門股常態):`build_minute` 合併後的 `out` 因為歷史段非空而永不觸發
        `empty_mark`,當日段自己又不存空 → 每次請求都要重付一次 TC4 首頁等待
        (self-review B2)。短 TTL 兩邊都顧:15 秒內的重複請求免費,過期即重抓,
        該股一開始成交就看得到。

        `status` 一併存下(見 `_today` 註解):TTL 窗內的命中要能還原「為什麼空」。"""
        self._today[(code, today)] = (self._clock(), bars, status)

    def prune(self, today: _dt.date) -> None:
        """剪掉視窗外與已過期的條目。

        `_hist` / `_daily` 的成長來自**日期維度**(股號受 watchlist 50 檔上限約束)
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
        for key in [k for k in self._daily_tag if k[1] != today_iso]:
            del self._daily_tag[key]
        self._daily_pre_final = {k for k in self._daily_pre_final if k[1] == today_iso}
        now = self._clock()
        for key in [
            k
            for k, e in self._today.items()
            if k[1] != today_iso or now - e[0] >= self._today_ttl(e[1])
        ]:
            del self._today[key]
        # 只丟已過期的:prune 每次 build_* 開頭都會跑,無條件 clear 等於負向快取從未生效
        for key in [k for k, e in self._empty.items() if now - e[0] >= EMPTY_TTL_SECS]:
            del self._empty[key]

    # ---- 日 K(per (code, today) memo + 定稿界)----

    def daily_get(self, code: str, today: str) -> list[Bar] | None:
        entry = self._daily.get((code, today))
        if entry is None:
            return None
        if (code, today) in self._daily_pre_final and _now_time() >= DAILY_FINAL_TIME:
            return None  # 界前快照過界即過期;entry 留給 `daily_stale` 墊背
        return entry

    def daily_stale(self, code: str, today: str) -> list[Bar] | None:
        """過不過期都回 —— 過期後 refetch 拿空手(TC4 關/忙)時的墊背。

        沒有這條的話,定稿界會把「盤後 TC4 關著」(已知常態)從「顯示早上快照」
        惡化成「整片空白到午夜」。呼叫端只在 fetch 失敗路徑用它,status/tag 照實帶。
        """
        return self._daily.get((code, today))

    def daily_put(self, code: str, today: str, bars: list[Bar]) -> None:
        if not bars:
            return  # don't-cache-empty
        self._daily[(code, today)] = bars
        # 界前寫入 → 記下「今日 bar 可能還在進行」;界後寫入 → 定稿(含覆寫舊標記)
        if _now_time() < DAILY_FINAL_TIME:
            self._daily_pre_final.add((code, today))
        else:
            self._daily_pre_final.discard((code, today))

    # ---- 資料源標籤(大盤 meta;cache hit 也要還原正確 tag)----

    def daily_tag_get(self, code: str, today: str) -> str | None:
        return self._daily_tag.get((code, today))

    def daily_tag_put(self, code: str, today: str, tag: str) -> None:
        self._daily_tag[(code, today)] = tag


async def build_daily(
    fetch: BarsFetcher, cache: BarsCache, code: str, today: _dt.date
) -> BarsResult:
    cache.prune(today)
    cached = cache.daily_get(code, today.isoformat())
    if cached is not None:
        # memo 命中 = 這一輪沒發 fetch,沒有壞消息可報(worst_status() 的同一條理由)
        return BarsResult(cached, "ok")
    # 短 TTL 負向快取:上一次剛確認過沒資料,不必再等一輪 TC4 首頁 deadline。
    # 回的是**存入時的原因**,不是 ok —— 洗白等於讓「還在等」在 15s 內變成「沒資料」。
    marked = cache.empty_status(code, "D", 0)
    if marked is not None:
        return _daily_stale_or_empty(cache, code, today.isoformat(), marked)
    start = today - _dt.timedelta(days=DAILY_WINDOW_DAYS)
    fetched, raw_status = await fetch(code, "D", start.isoformat(), today.isoformat())
    status = _coerce_status(raw_status)
    bars = fetched[-DAILY_MAX_BARS:]
    cache.daily_put(code, today.isoformat(), bars)
    if bars:
        cache.empty_clear(code, "D", 0)
        return BarsResult(bars, status)
    cache.empty_mark(code, "D", 0, status)
    return _daily_stale_or_empty(cache, code, today.isoformat(), status)


def _daily_stale_or_empty(cache: BarsCache, code: str, day: str, status: BarsStatus) -> BarsResult:
    """定稿界作廢後 refetch 拿空手(或 15s 負向窗內)的墊背:有舊快照回舊快照,
    status 照實帶(標記的原因 / fetch 實際結果,不洗白)。與 `_period_stale_or_empty`
    同一條政策 —— 各寫一份必然漂移(`_today_ttl` 的同一條理由)。

    INFO 固定字串(pr-165-review #2):墊背回應與新鮮取數在 payload 上不可分,少這行
    log 就無法區分「定稿到手」與「一直吃墊背」。負向窗內的重複請求也各印一行 ——
    日 K 請求本就稀疏(前端到午夜才再問、overlay 拿到非空也不輪詢),不另做去重。"""
    stale = cache.daily_stale(code, day)
    if stale is not None:
        logger.info("bars %s: 日 K refetch 空手(%s),墊背舊快照 %s 根", code, status, len(stale))
        return BarsResult(stale, status)
    return BarsResult([], status)


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
    if period != "W":
        return None  # 防呆:未知 period 不得被靜默當成週(呼叫端應只傳 W / M)
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


#: `engine.bars_range_tagged(code, tf, start, end) -> TaggedBars`
TaggedBarsFetcher = Callable[[str, str, str, str], Awaitable[TaggedBars]]


def is_partial_last(bars: list[Bar], tf: str, today: _dt.date) -> bool:
    """最後一根是否仍在進行中(尚未收盤)。

    **由資料判定,不是 tf 的常數**:盤中的日 K / 分 K 最後一根就是今天 / 當下那分鐘,
    週末查的週 K 最後一桶其實已收盤 —— 用 `tf != "D"` 這種常數兩個方向都會誤導,
    而「meta 不說謊」正是本輪的設計主軸(review P1-1)。

    **與 `DAILY_FINAL_TIME` 是兩個口徑**(pr-165-review #5):過界後 tf=D 的末根雖已
    定稿,本函式仍回 True(日曆日判準)—— 大盤頁 14:00–24:00 的「最後一根未收盤」字樣
    因此失真。非定稿界引入(冷啟動 13:45 後首問同樣誤標),D 分支要不要吃界見
    docs/next-time.md 08-31 pr-165-review 留尾節(期貨側不吃本欄,不受影響)。
    """
    if not bars:
        return False
    last = bars[-1]["t"][:10]
    today_iso = today.isoformat()
    if tf in ("1", "D"):
        return last == today_iso
    if tf == "M":
        return last[:7] == today_iso[:7]
    if tf == "W":
        return _dt.date.fromisoformat(last).isocalendar()[:2] == today.isocalendar()[:2]
    return False


async def build_period(
    fetch: TaggedBarsFetcher, cache: BarsCache, code: str, today: _dt.date, period: str
) -> TaggedBars:
    """大盤頁的日 / 週 / 月 K —— 三者共用同一份長窗日 K(見 `DAILY_LONG_WINDOW_DAYS`)。

    `period`:`"D"` 原樣回、`"W"` / `"M"` 走 `aggregate_period`。回 `(bars, source_tag)`。

    **獨立實作而不借 `build_daily`**(review P2-1):快取鍵一律 `f"{code}|L"`,
    `_daily` / `_daily_tag` / `_empty` 三處都用它 —— 只隔開 `_daily` 而讓 `_empty`
    共用 `code`,會讓 180 日窗的一次空結果在 15 秒內把長窗請求也擋掉(反之亦然),
    診斷時看到的是「日K 有、週K 空」這種難以歸因的狀態。`build_daily` 則維持原簽名,
    個股路徑零風險。
    """
    key = f"{code}|L"
    day = today.isoformat()
    cache.prune(today)
    cached = cache.daily_get(key, day)
    if cached is not None:
        # tag 缺失回 unavailable 而非猜一個漂亮值 —— 猜值就是在最需要誠實的
        # 那條路上說謊(review P1-4 的同一條理由)
        tag = cache.daily_tag_get(key, day) or "unavailable"
        return TaggedBars(_shaped(cached, period), tag)
    if cache.empty_status(key, "D", 0) is not None:
        return _period_stale_or_empty(cache, key, day, period)
    start = today - _dt.timedelta(days=DAILY_LONG_WINDOW_DAYS)
    daily, tag = await fetch(code, "D", start.isoformat(), day)
    daily = daily[-DAILY_LONG_MAX_BARS:]
    cache.daily_put(key, day, daily)
    if daily:
        cache.daily_tag_put(key, day, tag)
        cache.empty_clear(key, "D", 0)
        return TaggedBars(_shaped(daily, period), tag)
    # 大盤路徑的空態表述走自己的 source tag(`unavailable`),不吃三態 status ——
    # 存 "ok" = 現況等價,只是讓 `_empty` 的值型別一致(本輪 out of scope)
    cache.empty_mark(key, "D", 0, "ok")
    return _period_stale_or_empty(cache, key, day, period)


def _shaped(bars: list[Bar], period: str) -> list[Bar]:
    """長窗日 K → 請求的 period 形狀(`"D"` 原樣、W/M 聚合)。"""
    return bars if period == "D" else aggregate_period(bars, period)


def _period_stale_or_empty(cache: BarsCache, key: str, day: str, period: str) -> TaggedBars:
    """定稿界作廢後 refetch 拿空手(或 15s 負向窗內)的墊背:有舊快照回舊快照 + 舊 tag,
    否則維持原本的空態表述。INFO 的理由見 `_daily_stale_or_empty`(pr-165-review #2)。"""
    stale = cache.daily_stale(key, day)
    if stale is None:
        return TaggedBars([], "unavailable")
    tag = cache.daily_tag_get(key, day) or "unavailable"
    # 與 _daily_stale_or_empty 同形(前綴/欄序:鍵、括號、根數)—— 括號欄這邊放來源 tag
    # (period 路徑無 status 欄);grep 錨點統一「墊背舊快照」(review S-1)
    logger.info("bars %s: 日 K refetch 空手(%s),墊背舊快照 %s 根", key, tag, len(stale))
    return TaggedBars(_shaped(stale, period), tag)


async def build_minute(
    fetch: BarsFetcher,
    cache: BarsCache,
    code: str,
    days: int,
    today: _dt.date,
    *,
    session: str = "day",
    calendar: TradingCalendar | None = None,
) -> BarsResult:
    """近 `days` 個日曆日的 1 分 bar(歷史 memo + 當日 TTL 拼接)。

    status = 兩段的 worst(SC-6)。**未實際 fetch 且無存檔 status 的段不貢獻**
    (歷史 memo 命中)—— 已經拿到的資料不是壞消息,把它算成上一輪的原因會讓
    過期的診斷永遠黏著。

    `session`(`day` / `allday`,futures-allday §1.4):同一個 code 的兩種盤別是
    **不同的序列**(近全多了夜盤那 14 小時),所以三處 cache(歷史 memo / 當日 /
    負向)的鍵一律用複合字串 `f"{code}:{session}"` —— 共用一格的話,日盤模式先跑一輪
    之後,近全模式在 TTL 內拿到的是日盤那份 bars,畫面上是「切到近全還是只有日盤」,
    兩邊都 200、都非空、零錯誤訊號。day 也帶後綴(單一格式;in-memory 無相容問題)。

    **複合鍵只在 cache 查表處組出,`fetch` 的第一個引數維持原 `code`**(R8):
    覆寫掉會讓 source 拿 "F:TXF:allday" 去問 TC4,回來是空 —— 與 timeout 不可分。

    `tf="D"` 的兩條(`build_daily` / `build_period`)不帶 session:日 K 無盤別維度,
    忽略的參數不進 cache 鍵(D-15)。

    `calendar`(選配):歷史段的 missing 先過濾掉「不可能有資料的日子」(見
    `_possible_data_days`)。`None` = 不過濾 = 逐字舊行為。

    **午夜緩衝**(`MIDNIGHT_BUFFER_END`,TZ-2):台北 00:00–00:10 內不把 `yesterday`
    寫進永久 memo —— 見下方註解。回應內容不受影響,只有「要不要記住」被延後。
    """
    cache.prune(today)
    ck = f"{code}:{session}"
    marked = cache.empty_status(ck, "1", days)
    if marked is not None:
        return BarsResult([], marked)
    start = today - _dt.timedelta(days=clamp_days(days) - 1)
    yesterday = today - _dt.timedelta(days=1)

    statuses: list[BarsStatus] = []
    out: list[Bar] = []
    deferred: list[Bar] = []
    if start <= yesterday:
        # 過濾「不可能有資料的日子」(見 `_possible_data_days`):過濾後為空 → 這一段
        # 一發 fetch 都不出去,statuses 也不收它 —— 沒發請求就沒有壞消息可報。
        missing = _possible_data_days(cache.hist_missing(ck, start, yesterday), session, calendar)
        if missing:
            # 只補缺口區間(端點取 min/max;中間已 memo 的日子重抓無害,省下逐日 REQ)
            lo, hi = missing[0], missing[-1]
            fetched, hist_status = await fetch(code, "1", lo.isoformat(), hi.isoformat())
            statuses.append(_coerce_status(hist_status))
            if fetched:
                hold = hi == yesterday and _now_time() < MIDNIGHT_BUFFER_END
                # 午夜緩衝(TZ-2):台北剛過午夜時 `yesterday` 仍屬當前交易日(夜盤到
                # 05:00 才收),TC4 不保證此刻已把 23:5x 尾根寫進 1K 分頁。歷史 memo 是
                # **永久**的 —— 這一刻寫下去,那幾根就永遠缺(重啟 server 才會消失),
                # 而畫面上只是「昨晚最後幾分鐘不見了」,零錯誤訊號。
                # 只延後**永久化**:fetch 到的照樣併進本輪回應(下面的 `deferred`)。
                put_hi = yesterday - _dt.timedelta(days=1) if hold else hi
                if lo <= put_hi:
                    cache.put_hist_range(ck, lo, put_hi, fetched)
                if hold:
                    deferred = [b for b in fetched if b["t"][:10] == yesterday.isoformat()]
            else:
                # 全空:可能是 TC4 失敗,不寫負向快取(否則整段被永久釘成空)
                logger.info("bars %s: 歷史段 %s..%s 回空,不入 memo", ck, lo, hi)
        out.extend(cache.hist_range(ck, start, yesterday))
        # yesterday 是歷史段的最後一天 → 接在 memo 之後仍是時序遞增
        out.extend(deferred)

    entry = cache.today_get(ck, today.isoformat())
    if entry is None:
        today_bars, raw_today_status = await fetch(code, "1", today.isoformat(), today.isoformat())
        # 收斂在寫入 cache **之前**:域外值一旦進了 `_today`,15s 內的重播會把它
        # 再送出去一次,收斂點就白做了
        today_status = _coerce_status(raw_today_status)
        cache.today_put(ck, today.isoformat(), today_bars, today_status)
    else:
        # cache 命中也要把存入時的 status 帶回來:`_empty` 的 key 含 days 而這層不含,
        # 少了它 days 一換就把 timeout 洗白(R4)
        today_bars, today_status = entry
    statuses.append(today_status)
    out.extend(today_bars)
    status = worst_status(*statuses)
    # 兩段都空 = 這檔在 TC4 查不到(或 TC4 正忙)。標記 15 秒,期間的重複請求直接回空,
    # 不再各付一次首頁 deadline。過期即自動重試(W-15)。
    if out:
        cache.empty_clear(ck, "1", days)
    else:
        cache.empty_mark(ck, "1", days, status)
    return BarsResult(out, status)
