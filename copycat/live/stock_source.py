"""StockQuoteSource:個股 TC4 資料源(design v4 §2.3)。

繼承 TC4QuoteSource 複用連線/REQ 全域互斥/_dispose/stale 重連機制(不動 tc4.py,
案 A:TXO 實盤路徑零風險)。覆寫:

- `_rt_window`:REALTIME 窗 = 個股當日 UTC 日盤窗(非 TXO 時段窗)。
- listener 原始分派:REALTIME → `on_message(Quote dict)`(book/meta 都要,不能只回 Tick)。
- 逐檔 subscribe/unsubscribe(refcount 池在 engine 層)+ 無推播健檢(訂閱後 N 秒
  無該檔任何推播 → `on_no_data(code)` 一次 + 退避重掛直到有推播;僅交易時段生效
  — 個股休市 snapshot 行為未實測,design R5)。
"""

from __future__ import annotations

import datetime as _dt
import logging
import threading
import time
from typing import Any, Callable, Literal, NotRequired, Sequence, TypedDict, cast

from copycat.live.stock_models import TRIAL_WINDOWS, StockTick, parse_hist_tick
from copycat.live.tc4 import (
    BARS_POLL_DEADLINE,
    HEAL_VARIANT_AFTER,
    HistoryTimeoutError,
    TC4QuoteSource,
)
from copycat.tc4common import TC4_DEFAULT_PORT, iter_qry_pages

logger = logging.getLogger(__name__)

_TRADING_START = _dt.time(8, 30)
_TRADING_END = _dt.time(13, 35)

_DAILY_WINDOW_DAYS = 40  # 日 K 抓取視窗(日曆日;25 交易日 + 假日餘裕)
#: CDP basis sweep 的 n(`signal_hub._BASIS_BARS`)。**只有它小於這個數**,而它只要
#: 最後一根已完成 bar → 1K fallback 可以走窄窗。
_DAILY_SMALL_N = 5
#: 小 n 的 1K fallback 視窗(日曆日)。20 日曆日 ≈ 12–14 個交易日,春節那種 9 天連假
#: 之後仍有 7–8 個平日 —— 對「要 5 根」綽綽有餘。
_DAILY_FALLBACK_SMALL_DAYS = 20


def _daily_fallback_window_days(n: int) -> int:
    """`fetch_daily_bars` 的 **1K fallback 段**視窗(日曆日);DK 段不吃這個。

    只有兩種輸入就寫成兩種輸出(review ST8):`n <= 5` → 20 日,其餘 → 40 日(逐字
    等於改動前)。用連續公式表達一個只有兩格的對映,讀者得自己算才知道 `n=25` 沒變。

    為什麼只縮 fallback(review SP3):條文點名的是「DK 不支援的股號**每次 overlay 都
    整窗拉 1K**」—— DK 一天一列,縮它省不到量卻多一個會漂的維度。兩段窗不同是刻意的,
    與 `fetch_bars_range_tagged`(DK 全窗、fallback 縮到 90 日)同款姿態。

    為什麼 `n=25` 不縮:`overlay.build_overlay` 的 ma20 要 20 根**已完成**日 bar,
    40 日曆日 ≈ 25–28 個交易日、遇春節只剩 ~23 根,餘裕本來就只有個位數;再縮的失效
    樣態是 ma20 靜默變 null(畫面上只是少一條線,零錯誤訊號)。
    """
    return _DAILY_FALLBACK_SMALL_DAYS if n <= _DAILY_SMALL_N else _DAILY_WINDOW_DAYS


# K 線 fallback:DK 空時改走 1K 聚合,但 1K 量級是 DK 的數百倍(180 日曆日 ≈ 4.8 萬列
# 分頁收割)→ fallback 另用較小視窗,寧可根數不足也不打爆 REQ 往返(change-spec R2-7)
_OHLC_FALLBACK_WINDOW_DAYS = 90

# 1K 分鐘域(台北,終點標記;與 fetch_day_minutes 同一把尺)
_MIN_DOMAIN_START = "0901"
_MIN_DOMAIN_END = "1330"
_MIN_CLAMP_END = "1335"

#: `fetch_day_minutes(window_variant=v)` 的窗口 end hour = `min(BASE + v, CAP)`。
#: **公開常數**:index_engine 要判「階梯用盡」才打得出與「還在爬」可分的 log,
#: 兩邊各寫一份數字就會漂(review L1-P2-2)。
WINDOW_VARIANT_END_BASE = 6
WINDOW_VARIANT_END_CAP = 23

#: 零推播健檢重掛的退避上限(秒)。比基底 watchdog 的 300s 短:個股健檢盯的是
#: 「這一檔從訂閱起就沒推播」,盤中每分鐘試一次的成本(2 個 REQ)遠低於一檔自選
#: 整場空白的代價。
_NO_DATA_HEAL_CAP = 60.0


class DailyBar(TypedDict):
    """overlay 用日 bar(毫元;date = YYYY-MM-DD)。定義在 source 層避免 live→server 逆依賴。"""

    date: str
    high: int
    low: int
    close: int


class Bar(TypedDict):
    """K 線 bar(毫元整數;`t` 日 K = YYYY-MM-DD、分 K = "YYYY-MM-DD HH:MM" 台北)。

    與 DailyBar 分開定義:後者是 overlay(實盤路徑)在用的,只有 high/low/close,
    不得為了畫蠟燭去動它(change-spec W-D2)。

    `uv` / `dv` = 內外盤量(1K row 的 UpVolume / DownVolume,futures-allday SC-8)。
    **NotRequired 且來源沒欄就不設** —— DK 路徑與沒有這兩欄的 1K 來源,bar 形狀必須
    與加這個欄位之前完全相同(前端以 `uv == null` 判定副圖隱藏)。"""

    t: str
    o: int
    h: int
    l: int  # noqa: E741 - 與前端 Bar 欄位對齊(o/h/l/c/v)
    c: int
    v: int
    uv: NotRequired[int]
    dv: NotRequired[int]


#: K 線空結果的原因三態。**沒有「確定無資料」這一態** —— TC4 的 GETHISDATA 空頁
#: 不區分「未備妥」與「無資料」(tc4.py 檔頭),所以:
#:
#: - `"timeout"` = 等滿 deadline 仍未備妥(慢 **或** 查無此檔,協定上不可分)。
#: - `"ok"` = 首頁備妥、收割跑完(結果仍可能是空,例如 bar 全落在域外)。
#: - `"disconnected"` = TC4 通訊失敗(ConnectionError),由 server 層降級時標。
#:
#: 文案因此必須用進行式不下結論(change-spec §1 語意錨點)。
BarsStatus = Literal["ok", "timeout", "disconnected"]


def _milli(raw: str) -> int:
    return round(float(raw) * 1000)


def _iso_date(ymd: str) -> str:
    return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}"


def _parse_dk_rows(rows: list[dict]) -> list[DailyBar]:
    bars: list[DailyBar] = []
    skipped = 0
    for r in rows:
        try:
            bars.append(
                DailyBar(
                    date=_iso_date(str(r["Date"])),
                    high=_milli(r["High"]),
                    low=_milli(r["Low"]),
                    close=_milli(r["Close"]),
                )
            )
        except (KeyError, ValueError):
            skipped += 1
    if skipped:
        # DK 欄位格式未實測(design Known Risk 1):略過計數是唯一診斷訊號
        logger.warning("DK rows 解析略過 %d/%d 列(欄位缺漏/格式)", skipped, len(rows))
    bars.sort(key=lambda b: b["date"])
    return bars


def _aggregate_1k_rows(rows: list[dict]) -> list[DailyBar]:
    """1K rows → 日 bar(per Date:high=max、low=min、close=最後一根 close,依 Time 序)。"""
    by_date: dict[str, list[tuple[str, int, int, int]]] = {}
    skipped = 0
    for r in rows:
        try:
            item = (str(r["Time"]), _milli(r["High"]), _milli(r["Low"]), _milli(r["Close"]))
        except (KeyError, ValueError):
            skipped += 1
            continue
        by_date.setdefault(str(r["Date"]), []).append(item)
    if skipped:
        logger.warning("1K rows 解析略過 %d/%d 列(欄位缺漏/格式)", skipped, len(rows))
    bars: list[DailyBar] = []
    for ymd in sorted(by_date):
        items = sorted(by_date[ymd], key=lambda x: x[0])
        bars.append(
            DailyBar(
                date=_iso_date(ymd),
                high=max(h for _, h, _lo, _c in items),
                low=min(lo for _, _h, lo, _c in items),
                close=items[-1][3],
            )
        )
    return bars


def _int_field(row: dict, *names: str) -> int:
    """量欄位名未實測(DK 尤其)→ 依序試,全缺回 0(缺量不該讓整根 bar 掉)。"""
    for name in names:
        raw = row.get(name)
        if raw is None or raw == "":
            continue
        try:
            return int(float(raw))
        except ValueError:
            continue
    return 0


def parse_dk_bars(rows: list[dict]) -> list[Bar]:
    """DK rows → 日 Bar。缺 Open → 用 Close(欄位名未實測,CLAUDE.md §8 只實證 H/L/C)。"""
    bars: list[Bar] = []
    skipped = 0
    for r in rows:
        try:
            close = _milli(r["Close"])
            bars.append(
                Bar(
                    t=_iso_date(str(r["Date"])),
                    o=_milli(r["Open"]) if r.get("Open") else close,
                    h=_milli(r["High"]),
                    l=_milli(r["Low"]),
                    c=close,
                    v=_int_field(r, "Volume", "TotalVolume", "Vol"),
                )
            )
        except (KeyError, ValueError):
            skipped += 1
    if skipped:
        logger.warning("DK bars 解析略過 %d/%d 列(欄位缺漏/格式)", skipped, len(rows))
    bars.sort(key=lambda b: b["t"])
    return bars


def _taipei_minute_key(
    raw_time: str,
    domain_start: str = _MIN_DOMAIN_START,
    domain_end: str = _MIN_DOMAIN_END,
    clamp_end: str = _MIN_CLAMP_END,
) -> str | None:
    """1K Time(UTC HHMMSS)→ 台北 HHMM 終點標記;域外回 None。

    `domain_end`+1 ~ `clamp_end` clamp 為 `domain_end`(收盤補正),與 `fetch_day_minutes` 同規則。

    **域是可換的尺**(index-board R-3 修正):預設值是**個股**日盤 09:00–13:30;
    台指期日盤是 08:45–13:45,套個股的尺會丟掉 08:46–09:00(開盤跳空是看盤重點)、
    把 13:31–13:35 的成交錯併進 13:30 那根、再丟掉 13:36–13:45 —— 圖畫得出來、
    根數也合理,沒有任何 assertion 會紅。"""
    raw = raw_time.zfill(6)
    hh = (int(raw[:2]) + 8) % 24
    key = f"{hh:02d}{raw[2:4]}"
    if domain_end < key <= clamp_end:
        key = domain_end
    if not (domain_start <= key <= domain_end):
        return None
    return key


def _taipei_dt_key(
    date_iso: str, raw_time: str, segments: Sequence[tuple[str, str, str]]
) -> tuple[str, str] | None:
    """(1K row 的 UTC 日期, UTC HHMMSS) → (台北 YYYY-MM-DD, HHMM 終點標記);域外回 None。

    多段域專用。**完整 datetime 轉換**而不是 `_taipei_minute_key` 的「只加小時 % 24」
    捷徑:夜盤跨午夜,UTC 16:00 之後的列屬台北**次日**,只加小時會把日期留在前一天
    (畫面上是每天凌晨五小時的 bar 全被塞回前一日,零錯誤訊號)。

    **不加 1 分鐘** —— 1K 的 `Time` 本身已是 bar 終點標記(`river_models` 實證),
    加 1 會讓整條序列晚一分(日盤首根 0846 變 0847)。

    段判定逐段試,`end`+1 ~ `clamp_end` clamp 為 `end`(收盤補正,與單段同規則);
    clamp 不動日期 —— 05:03 clamp 成 05:00 仍是同一個台北日。
    """
    try:
        utc = _dt.datetime.strptime(f"{date_iso} {raw_time.zfill(6)}", "%Y-%m-%d %H%M%S")
    except ValueError:
        return None
    taipei = utc + _dt.timedelta(hours=8)
    hhmm = f"{taipei:%H%M}"
    for start, end, clamp_end in segments:
        key = end if end < hhmm <= clamp_end else hhmm
        if start <= key <= end:
            return f"{taipei:%Y-%m-%d}", key
    return None


def _merge_into(bar: Bar, k: _RawK) -> None:
    """同 t 的後續列併入(o 保留第一根、c 取最後一根)。

    吃 `_RawK` 而不是拆開的純量:uv/dv 是選配欄,拆參數就得再多兩個 `| None`,
    而「有沒有那兩欄」的判斷會散到呼叫點(R10)。
    """
    bar["h"] = max(bar["h"], k["h"])
    bar["l"] = min(bar["l"], k["l"])
    bar["c"] = k["c"]
    bar["v"] += k["v"]
    if "uv" in k and "dv" in k:
        bar["uv"] = bar.get("uv", 0) + k["uv"]
        bar["dv"] = bar.get("dv", 0) + k["dv"]


class _RawK(TypedDict):
    date: str  # YYYY-MM-DD
    time: str  # 原始 UTC HHMMSS(排序用)
    o: int
    h: int
    l: int  # noqa: E741
    c: int
    v: int
    uv: NotRequired[int]
    dv: NotRequired[int]


def _delta_vol(row: dict) -> tuple[int, int] | None:
    """1K row 的內外盤量 (UpVolume, DownVolume);**兩欄皆缺 → None**。

    缺欄回 None 而不是 (0, 0):`Bar.uv/dv` 是 NotRequired,沒有來源就不該長出欄位
    —— 否則個股與 DK 路徑的 bar 形狀跟著改變,而 0 與「沒這個資料」在畫面上不可分。
    """
    up, down = row.get("UpVolume"), row.get("DownVolume")
    if up in (None, "") and down in (None, ""):
        return None
    return _int_field(row, "UpVolume"), _int_field(row, "DownVolume")


def _parse_1k_rows(rows: list[dict]) -> list[_RawK]:
    """1K rows → 中性列(不套分鐘域過濾;分鐘域是 x 軸語意,日聚合不該吃)。"""
    out: list[_RawK] = []
    skipped = 0
    for r in rows:
        try:
            close = _milli(r["Close"])
            k = _RawK(
                date=_iso_date(str(r["Date"])),
                time=str(r["Time"]).zfill(6),
                o=_milli(r["Open"]) if r.get("Open") else close,
                h=_milli(r["High"]),
                l=_milli(r["Low"]),
                c=close,
                v=_int_field(r, "Volume", "TotalVolume", "Vol"),
            )
            delta = _delta_vol(r)
            if delta is not None:
                k["uv"], k["dv"] = delta
            out.append(k)
        except (KeyError, ValueError):
            skipped += 1
    if skipped:
        logger.warning("1K bars 解析略過 %d/%d 列(欄位缺漏/格式)", skipped, len(rows))
    out.sort(key=lambda k: (k["date"], k["time"]))
    return out


def _fold(bars: dict[str, Bar], order: list[str], t: str, k: _RawK) -> None:
    existing = bars.get(t)
    if existing is None:
        bar = Bar(t=t, o=k["o"], h=k["h"], l=k["l"], c=k["c"], v=k["v"])
        if "uv" in k and "dv" in k:
            bar["uv"] = k["uv"]
            bar["dv"] = k["dv"]
        bars[t] = bar
        order.append(t)
    else:
        _merge_into(existing, k)


def parse_1k_bars(
    rows: list[dict],
    domain: tuple[str, str, str] | Sequence[tuple[str, str, str]] | None = None,
) -> list[Bar]:
    """1K rows → 分鐘 Bar(台北終點標記;域外丟棄)。

    clamp 後同 t 會有多列(個股 13:31–13:35 全標 1330)→ **必須合併**:`fetch_day_minutes`
    回 dict 靠 key 覆寫躲掉了這件事,list 不會(change-spec R2-6)。

    `domain`:
    - `None` = 個股日盤(既有行為);單段 `(start, end, clamp_end)` = 既有路徑零改動
      (期貨日盤傳 `FUTURES_MINUTE_DOMAIN`)。
    - **段序列**(期指近全 `FUTURES_ALLDAY_DOMAIN`)= 新路徑,走完整 UTC→台北 datetime
      轉換以跨午夜(`_taipei_dt_key`)。

    判別法寫死 `isinstance(domain[0], str)`:三元素 str tuple **本身也是 Sequence**,
    用 `isinstance(domain, Sequence)` 兩種都會命中,單段會被當成三個段解讀。"""
    by_key: dict[str, Bar] = {}
    order: list[str] = []
    if domain is not None and not isinstance(domain[0], str):
        segments = tuple(cast("Sequence[tuple[str, str, str]]", domain))
        for k in _parse_1k_rows(rows):
            got = _taipei_dt_key(k["date"], k["time"], segments)
            if got is None:
                continue
            date_s, key = got
            _fold(by_key, order, f"{date_s} {key[:2]}:{key[2:]}", k)
        return [by_key[t] for t in order]
    d = (
        cast("tuple[str, str, str]", domain)
        if domain is not None
        else (_MIN_DOMAIN_START, _MIN_DOMAIN_END, _MIN_CLAMP_END)
    )
    for k in _parse_1k_rows(rows):
        key = _taipei_minute_key(k["time"], d[0], d[1], d[2])
        if key is None:
            continue
        _fold(by_key, order, f"{k['date']} {key[:2]}:{key[2:]}", k)
    return [by_key[t] for t in order]


def aggregate_1k_to_daily(rows: list[dict]) -> list[Bar]:
    """1K rows → 日 Bar(DK 不支援時的 fallback;o = 當日第一根 open、v / uv / dv = 加總)。

    **不套分鐘域過濾** —— 域(0901–1330)是江波圖 x 軸語意,套進日聚合會把域外列
    (如試撮/開盤前後)的量與極值靜默丟掉,與既有 `_aggregate_1k_rows` 行為也不一致。"""
    by_date: dict[str, Bar] = {}
    order: list[str] = []
    for k in _parse_1k_rows(rows):
        _fold(by_date, order, k["date"], k)
    return [by_date[d] for d in order]


def stock_symbol(key: str) -> str:
    """instrument key → TC4 symbol(**唯一定義**;engine 經 `symbol_of` 取用)。

    - 股號 → `TC.S.TWS.<code>`:上市/上櫃都掛 TWS 段(2026-07-21 spike:5483 上櫃推播成功)
    - `F:<prod>`(兩段形)→ `TC.F.TWF.<prod>.HOT`:期現對照腿
    - `F:<prod>:<ym>`(三段形)→ `TC.F.TWF.<prod>.<ym>`:使用者選定的月契約主圖

    誤走股票段時 SUBQUOTE 照回 OK 零錯誤訊號(2026-07-21 real-env 實證),前綴分流
    是唯一防線;同理 engine 不得自組第二份對映(R2-2)。"""
    if key.startswith("F:"):
        prod, _sep, ym = key[2:].partition(":")
        return f"TC.F.TWF.{prod}.{ym or 'HOT'}"
    return f"TC.S.TWS.{key}"


def is_futures_key(key: str) -> bool:
    """instrument key 是否為個股期(兩段形對照腿或三段形合約)。"""
    return key.startswith("F:")


def is_contract_key(key: str) -> bool:
    """三段形合約鍵(`F:<prod>:<ym>`)= 可當主圖的 instrument;HOT 對照腿不算。"""
    return key.startswith("F:") and ":" in key[2:]


def trial_windows_for(key: str) -> tuple[tuple[str, str], ...]:
    """instrument key → 試撮窗(個股期空窗,D2)。

    **單一定義**:engine(REALTIME)與 source(回補)必須同一把尺 —— 分岔時 live
    收得到 08:50 的成交、回補把它丟掉,而 `apply_backfill` 先 reset 再重放,每切一次
    檔那段就消失一次。"""
    return () if is_futures_key(key) else TRIAL_WINDOWS


def stock_window(trade_date: str) -> tuple[str, str]:
    """台北交易日 YYYY-MM-DD → 日盤 UTC 窗。

    窗以**小時**為粒度(`YYYYMMDDHH`),實際回 UTC 00–06 = 台北 08:00–14:00 ——
    比日盤 09:00–13:30 兩端各寬一些,涵蓋試撮與收盤補正,不是精準到分的 01–05:30。"""
    day = trade_date.replace("-", "")
    return f"{day}00", f"{day}06"


def in_trading_hours_now(now: _dt.time | None = None) -> bool:
    """台股現貨盤中(08:30 試撮起 – 13:35 收盤補正止)。

    個股 / 指數 session 的健檢與自癒共用這一把;2026-08-26 F4 起 corr 的台積電現貨腿
    也吃它(`corr_source.segment_leg_gate` 的 `tws` 那半邊)—— 現貨時段只有一張表,
    第二張表的失效樣態是兩邊悄悄漂開,而畫面上兩邊都「看起來對」。

    `now` 只給測試注入(簽名比照 `futures_source.in_futures_session_now`);預設 None
    = 讀牆鐘,逐字等於改動前。
    """
    t = _dt.datetime.now().time() if now is None else now
    return _TRADING_START <= t <= _TRADING_END


class StockQuoteSource(TC4QuoteSource):
    def __init__(
        self,
        port: str = TC4_DEFAULT_PORT,
        *,
        api: Any | None = None,
        session: str | None = None,
        trade_date: str | None = None,
        poll_wait_secs: float = 1.0,
        no_data_secs: float = 10.0,
        in_trading_hours: Callable[[], bool] = in_trading_hours_now,
        heal_silence_secs: float | None = 30.0,
        heal_symbol_silence_secs: float | None = 60.0,
        heal_poll_secs: float = 5.0,
    ) -> None:
        # 自癒閘沿用既有的盤中判定:個股盤外沒有推播是正常的,churn 沒有意義
        super().__init__(
            port,
            api=api,
            session=session,
            poll_wait_secs=poll_wait_secs,
            heal_silence_secs=heal_silence_secs,
            heal_symbol_silence_secs=heal_symbol_silence_secs,
            heal_active=in_trading_hours,
            heal_poll_secs=heal_poll_secs,
        )
        self._trade_date = trade_date or f"{_dt.date.today():%Y-%m-%d}"
        self._no_data_secs = no_data_secs
        self._in_trading_hours = in_trading_hours
        self._on_message: Callable[[dict], None] | None = None
        self._on_no_data: Callable[[str], None] | None = None
        # 已收過推播的 **symbol**(健檢用;D8)。**不可用 `Security`** —— 個股期 leaf 的
        # 該欄值域未實證(產品碼 / 股號都可能),同一個值會同時出現在現貨與合約推播上,
        # 以它為鍵時合約的推播會把現貨的健檢一起消掉(現貨真的零推播也不再有訊號)。
        self._seen: set[str] = set()
        self._seen_lock = threading.Lock()
        #: R3 專屬的重掛記帳(**不與 watchdog 共用**:共用時個股的 10/20/40/60s 退避
        #: 會被 watchdog 的 300s 階梯推走)。兩邊只共用 `_window_variant` —— 那是
        #: 「這把 key 現在是哪一把」的事實,不是節奏。
        self._no_data_attempts: dict[str, int] = {}
        self._no_data_next: dict[str, float] = {}
        #: code → 待觸發的健檢 timer(**per-code 單一把**)。重複訂閱(rollover /
        #: 退訂後再訂)不換掉舊的話會疊出多條鏈:同一檔被通報多次、重掛頻率成倍,
        #: 而每條鏈都只是「照設計在跑」,沒有任何錯誤訊號。
        self._no_data_timers: dict[str, threading.Timer] = {}
        self._timer_lock = threading.Lock()

    # ---- 設定 ----

    def symbol_of(self, key: str) -> str:
        """instrument key → TC4 symbol(`StockSource` Protocol;engine 路由表的鍵來源)。"""
        return stock_symbol(key)

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        self._on_message = cb

    def set_on_no_data(self, cb: Callable[[str], None]) -> None:
        self._on_no_data = cb

    def set_trade_date(self, trade_date: str) -> None:
        """rollover 階段一:換日窗(重掛訂閱由呼叫端執行)。

        自癒的 variant / attempts / 退避一併清掉:那些是「**昨天**那把 key 救不回來」
        的事實,帶進新的一天等於一開盤就訂到一把沒人知道的窗、第一次靜默就換窗。

        **換窗前先對舊窗逐 symbol UNSUBQUOTE**(N052):stage 2 的 `_resub` 送的
        UNSUB 已經是**新日期窗**,前一交易日那把 key 的 count 就永遠停在 >0 —— 它
        留在 session 上直到 session 死,而死的那一刻(taskkill / crash 後 ~60s 被 TC4
        `ExecuteCheckPingTime` reap)歸零,上游 feed 以 symbol 為單位:歸零就把整個
        symbol 的推播帶走,連別條 session 剛掛好的活 key 一起殺(tc4-market-facts
        「重啟後 ~60s 訂閱成功但零推播」的素材)。
        """
        if trade_date != self._trade_date:
            self._unsub_stale_window()
        self._trade_date = trade_date
        self._window_variant.clear()
        self._heal_attempts.clear()
        self._heal_next.clear()
        self._no_data_attempts.clear()
        self._no_data_next.clear()

    def _unsub_stale_window(self) -> None:
        """對**當下**的窗(含 variant)逐 symbol 發 UNSUBQUOTE;`_subscribed` 不動。

        `_subscribed` 是 stage 2 全量重掛的名單,清掉就沒人重訂了。舊窗 key 歸零會讓
        上游退訂該 symbol —— 這正是要的:stage 2 的新窗 SUB 走 0→1 觸發 `ReqSubQuote`
        把 feed 重新掛上(同 `_heal_resub(bump_variant=True)` 已在跑的「先退舊窗再換窗」
        形狀)。

        **不得拋**:呼叫端是 rollover stage1 與 `index_engine.start()`(後者在連線
        **之前**就呼叫),best-effort 清窗把它們炸掉是新的失效。第一發失敗即停 ——
        失敗多半是連線已死,其餘 symbol 也會失敗(同 `close()` 的收斂)。
        """
        for sym in sorted(self._subscribed):
            try:
                self._rt_request("UNSUBQUOTE", sym)
            # OSError 涵蓋 ConnectionError(`_req` 的收斂型別);**zmq.ZMQError 不是 OSError
            # 子類**(08-25 review 親驗 issubclass=False)—— 但 `_rt_request` 路徑的 Connect /
            # send / recv 都已收斂成 ConnectionError,鎖外裸拋只剩 setsockopt(新 context 不拋),
            # 今天不可達,屬 latent;ValueError 涵蓋壞電文的 json.JSONDecodeError
            except (OSError, ValueError) as exc:
                logger.warning("換日清舊窗 UNSUBQUOTE 失敗(略過其餘):%s: %s", sym, exc)
                return

    # ---- 覆寫:REALTIME 窗 = 個股當日日盤窗 ----

    def _rt_window(self, symbol: str) -> tuple[str, str]:
        return stock_window(self._trade_date)

    # ---- 逐檔訂閱 ----

    def subscribe_symbol(self, code: str) -> None:
        """UNSUB→SUB 冪等重掛;失敗 raise(engine refcount 回滾依賴,design §2.4)。"""
        self._ensure_connected()
        if self._sub_port is not None:
            # 真連線才有 SubPort;漏啟 = 訂閱成功但永收不到推播(2026-07-21 real-env 實證)
            self._start_listener()
        symbol = stock_symbol(code)
        self._resub(symbol)
        with self._seen_lock:
            self._seen.discard(symbol)
        # 健檢只掛現貨與**三段形合約鍵**(R2-3):兩段形 HOT 對照腿放開的話,
        # `_handle_no_data` 會廣播 code="F:CDF" 的 watchlist_quote,與 D16(只收自選碼)
        # 直接打架 —— 側欄會多出一格對不上任何自選項目的卡片。
        if (not is_futures_key(code) or is_contract_key(code)) and self._in_trading_hours():
            self._no_data_attempts.pop(symbol, None)  # 新一輪訂閱 = 新的退避階梯
            self._arm_health_check(code, self._no_data_secs, attempt=1)

    def _arm_health_check(self, code: str, delay: float, *, attempt: int) -> None:
        """排下一發健檢,並**換掉**這個 code 上待觸發的那一把(疊鏈是 C-4 的根因)。"""
        timer = threading.Timer(delay, self._health_check, args=(code, attempt))
        timer.daemon = True
        with self._timer_lock:
            old = self._no_data_timers.get(code)
            if old is not None:
                old.cancel()
            if self._stop.is_set():  # 收工中不再排(close 已經清過一輪)
                return
            self._no_data_timers[code] = timer
        timer.start()

    def unsubscribe_symbol(self, code: str) -> None:
        self._unsub(stock_symbol(code))

    def close(self) -> None:
        """收工:先關閘再取消所有待觸發的健檢,最後走基底的退訂 / Disconnect。

        timer 不收的話,process 收工後最長還會有一發健檢對已死的連線送 REQ ——
        `_stop` 早退是第二道防線,兩道都要(timer 已在飛的那一瞬間只有 `_stop` 擋得住)。
        """
        self._stop.set()
        with self._timer_lock:
            for timer in self._no_data_timers.values():
                timer.cancel()
            self._no_data_timers.clear()
        super().close()

    def _health_check(self, code: str, attempt: int = 1) -> None:
        """零推播 → 通報(僅第一次)+ 重掛,並以退避排下一輪(R3)。

        回呼一律傳 **key**(engine 的 `_no_data` 以 key 記);`_seen` 比對用 symbol。

        通報之外還要**重掛**:被 TC4 上游退訂的 key 再送幾次 SUBQUOTE 也不會回來,
        只有讓自己那把 key 走一次 0→1(或換一把新窗 key)才觸發 `ReqSubQuote`
        —— 09:00 那台 server 從 boot 起就 `no_data` 正是這個形狀(repro.md 觸發鏈 4)。

        退避 10 → 20 → 40 → 60s(封頂),記在 **R3 自己的** `_no_data_attempts` /
        `_no_data_next`(與 watchdog 分帳,理由見宣告處),持續到收到推播或被退訂;
        **盤外連重掛都不做**(個股收盤後零推播是正常的,churn 到隔天早上沒有意義;
        通報仍照舊發 —— 那是 engine 的狀態,不是對 TC4 的動作)。
        """
        if self._stop.is_set():  # 收工後仍在飛的那一發
            return
        symbol = stock_symbol(code)
        with self._seen_lock:
            seen = symbol in self._seen
        if seen or symbol not in self._subscribed:
            return
        if attempt == 1 and self._on_no_data is not None:
            self._on_no_data(code)
        if not self._in_trading_hours():
            return
        attempts = self._no_data_attempts.get(symbol, 0) + 1
        self._no_data_attempts[symbol] = attempts
        delay = min(self._no_data_secs * 2 ** (attempts - 1), _NO_DATA_HEAL_CAP)
        self._no_data_next[symbol] = time.monotonic() + delay
        bump = attempts >= HEAL_VARIANT_AFTER
        logger.warning(
            "個股零推播健檢:%s 重掛(attempt %d, window_variant=%d)",
            symbol,
            attempts,
            self._next_variant(symbol, bump=bump),
        )
        self._heal_resub(symbol, bump_variant=bump)
        self._arm_health_check(code, delay, attempt=attempt + 1)

    # ---- 回補(收割分頁;跨 symbol 序列化由 engine worker queue 統籌)----

    def backfill(self, code: str) -> list[StockTick]:
        """當日 tick 回補;**首頁等滿預算仍未備妥 → `HistoryTimeoutError`**。

        回空的話 worker 會把它當成功套用(`_backfilled` 進帳)→ 當日不再重排,
        分時圖整天空著而零錯誤訊號。逾時與「今天真的沒有成交」在 TC4 協定上只有
        「有沒有等滿」這一個區分訊號(同 `_collect_history` 的 `timed_out`)。
        """
        self._ensure_connected()
        sym = stock_symbol(code)
        start, end = stock_window(self._trade_date)
        self._sub_history(sym, start, end)
        rows: list[dict] = []
        budget = max(self._poll_wait * 30, 1.0)
        deadline = time.monotonic() + budget
        while True:
            first = self._get_history(sym, start, end, "0")
            if first.get("HisData"):
                break
            remaining = deadline - time.monotonic()
            # `poll_wait <= 0` = 測試組態,語意 = **不等待**(探測一次就走,沿
            # `river_backfill.collect_1k_minutes` 的同名慣例)。少了這道早退,`budget`
            # 的 1.0s 地板會被拿去空轉幾十萬次 GETHISDATA —— 每條測試付一秒,而真實
            # 組態(poll_wait > 0)完全看不到。
            if self._poll_wait <= 0 or remaining <= 0:
                raise HistoryTimeoutError(f"backfill {sym}:{budget:.1f}s 內首頁未備妥")
            time.sleep(min(self._poll_wait, remaining))

        def _page(qry_index: str) -> list[dict]:
            return self._get_history(sym, start, end, qry_index).get("HisData", [])

        for page in iter_qry_pages(_page):
            rows.extend(page)
        windows = trial_windows_for(code)  # 個股期空窗(D2);現貨照舊
        ticks = [
            t for r in rows if (t := parse_hist_tick(code, r, trial_windows=windows)) is not None
        ]
        if rows and not ticks:
            # N092:這條 ready-check 同樣是「首頁非空即 break」,凍結 stub(窗內無資料時
            # 建立的 history 訂閱回一列 Time = 訂閱建立時刻的假列)會讓它 break 出來卻
            # 一筆都解不出 —— 呼叫端看到的與「當日真無成交」一模一樣,全鏈零 log。
            #
            # **只記 log、不升成例外**:`parse_hist_tick` 的試撮窗過濾會製造同一個形狀的
            # **合法**空(08:30–09:00 盤前回補、13:25–13:30 試撮段),升成
            # `HistoryTimeoutError` 會讓那條路被 worker 無限重排。要真三態化得先把
            # 「試撮濾掉」與「解析不出」分流(見 verification.md 留尾)。
            logger.warning("stock backfill %s:%d 列全數解析失敗(疑似凍結 stub)", code, len(rows))
        logger.info("stock backfill %s: %d ticks", code, len(ticks))
        return ticks

    # ---- 日 K(overlay 資料源;SC-4)----
    #
    # `_collect_history` 已上提到基底 `TC4QuoteSource`(index-board R-3):futures_source
    # 的 K 線路徑要用同一份收割/退避/deadline 邏輯,各寫一份必然漂移。

    def fetch_day_minutes(self, code: str, *, window_variant: int = 0) -> dict[str, int]:
        """當日 1K → {HHMM(台北,bar 終點標記): close 毫點}(index-board SC-4)。

        1K Time 為 UTC 終點標記(實測 09:01 起);域 0901–1330 inclusive,
        1331–1335 clamp "1330"(收盤補正),其餘丟棄(design F5/IR4)。

        **「rows 非空但 minutes 全空」= 毒化訂閱的簽名**(fix/index-line-vanish A′):
        TC4 對「窗內當下無資料時建立的 history 訂閱」回的是凍結 stub 列(2026-08-14
        實驗 B),它的 Time 落在日內域外(boot stub ≈ 台北 08:30)→ 被域外靜默丟棄後
        呼叫端只看得到一個空 dict,與「TC4 真沒這天的資料」無從分辨、全鏈零 log
        (index 分時自癒因此全日空轉)。固定字串供 grep:`疑似凍結 stub`。

        `window_variant` = **逃出毒化 history 訂閱**的唯一便宜維度:TC4 的 history
        訂閱一旦在「窗內無資料」時建立就進 stub 態,重送 SubHistory 逃不掉,實證逃得掉
        的只有換窗口字串或換 session(2026-08-14 repro)。窗口 key 是
        (session, symbol, ktype, start, end) → end hour 每 +1 就是一個全新訂閱。
        start 不動、只推 end(`min(BASE + variant, CAP)`);`variant=0` 與原行為完全相同。"""
        self._ensure_connected()
        sym = stock_symbol(code)
        start, end = stock_window(self._trade_date)
        if window_variant > 0:
            hour = min(WINDOW_VARIANT_END_BASE + window_variant, WINDOW_VARIANT_END_CAP)
            end = f"{start[:8]}{hour:02d}"
        rows = self._collect_history(sym, "1K", start, end).rows
        minutes: dict[str, int] = {}
        skipped = 0
        for r in rows:
            try:
                key = _taipei_minute_key(str(r["Time"]))
                value = round(float(r["Close"]) * 1000)
            except (KeyError, ValueError):
                skipped += 1
                continue
            if key is None:  # 域外靜默丟棄(不計入 skipped)
                continue
            minutes[key] = value
        if skipped:
            logger.warning("1K minutes 解析略過 %d/%d 列", skipped, len(rows))
        if rows and not minutes:
            logger.warning("1K minutes:%d 列全數域外(疑似凍結 stub)", len(rows))
        return minutes

    def fetch_bars_range(
        self, code: str, tf: str, start_date: str, end_date: str
    ) -> tuple[list[Bar], BarsStatus]:
        """K 線 bar + 空結果的原因(`tf` = "D" 日 K / "1" 分 K;start/end 含端點)。

        range 型而非 days 型:server 層要把「歷史段(永久 memo)」與「當日段(短 TTL)」
        分開取,才不會每次輪詢都重拉整段歷史(change-spec R2-1/R2-2)。

        `tf="D"` 走 DK,空則 fallback 1K 聚合 —— fallback 視窗另行縮到
        `_OHLC_FALLBACK_WINDOW_DAYS`,避免 4.5× 量級放大(R2-7)。"""
        bars, _tag, status = self.fetch_bars_range_tagged(code, tf, start_date, end_date)
        return bars, status

    def fetch_bars_range_tagged(
        self, code: str, tf: str, start_date: str, end_date: str
    ) -> tuple[list[Bar], str, BarsStatus]:
        """同 `fetch_bars_range`,另回**實際走到的資料源標籤**。

        大盤頁的 meta 行要誠實說出這一份 bar 從哪來(index-board review P1-4):
        `tf="D"` 在 DK 空時會 fallback 成 90 日窗的 1K 聚合,若 meta 仍標 `tc4_dk`,
        「壞了 vs 沒資料看畫面即可答」的設計主軸剛好在最可能出事的那條路上失效。

        `source_tag ∈ {"tc4_1k", "tc4_dk", "tc4_dk_1k_agg"}`;`status` 見 `BarsStatus`。
        """
        self._ensure_connected()
        sym = stock_symbol(code)
        start = f"{start_date.replace('-', '')}00"
        end = f"{end_date.replace('-', '')}23"
        if tf == "1":
            rows, timed_out = self._collect_history(sym, "1K", start, end, BARS_POLL_DEADLINE)
            return parse_1k_bars(rows), "tc4_1k", ("timeout" if timed_out else "ok")

        dk_rows, dk_timed_out = self._collect_history(sym, "DK", start, end, BARS_POLL_DEADLINE)
        bars = parse_dk_bars(dk_rows)
        if bars:
            return bars, "tc4_dk", "ok"
        fb_start = max(
            _dt.date.fromisoformat(start_date),
            _dt.date.fromisoformat(end_date) - _dt.timedelta(days=_OHLC_FALLBACK_WINDOW_DAYS),
        )
        logger.info("bars %s: DK 空,fallback 1K 聚合(視窗縮至 %s..%s)", code, fb_start, end_date)
        # fallback 也要傳短 budget:漏傳的話 tf=D 無資料標的變成 10 + 30 = 40s
        fb_rows, fb_timed_out = self._collect_history(
            sym, "1K", f"{fb_start:%Y%m%d}00", end, BARS_POLL_DEADLINE
        )
        # 兩段取最壞:fallback 補到了 bar 但 DK 那趟等滿了預算 → 仍是 timeout。
        # 「有資料就一律 ok」會把「DK 沒回應」這件事在有 fallback 的日子裡靜默掉。
        status: BarsStatus = "timeout" if (dk_timed_out or fb_timed_out) else "ok"
        return aggregate_1k_to_daily(fb_rows), "tc4_dk_1k_agg", status

    def fetch_daily_bars(self, code: str, n: int = 25) -> list[DailyBar]:
        """近 n 根日 bar(DK 優先;DK 空/不支援 → 1K 聚合 fallback,股票 1K 一年已實證)。

        含今日 partial bar 也照回 — 「已完成 bar」剔除在 overlay 層(design R1)。

        **DK 逾時仍走 fallback、fallback 首頁未備妥才 raise**(plan review P0-1 + N019):
        fallback 是「DK 不支援這檔」與「DK 現在忙」共用的那條路,DK 逾時就直接放棄等於
        把還可能有貨的 1K 也一起丟了;反過來,fallback 也逾時卻回空,SignalHub 會讀成
        「無已完成日 K,CDP 停用」而且**永不重試**(空清單 = 資料面沒有;例外 = 暫時性
        → X-2b 有限重試)。

        判準**只看 `fb_timed_out`**(N019;原本是 `dk_timed_out and fb_timed_out`):
        AND 的另一半只在「DK 首頁非空、但整批解析不出 bar」時為 False,而那是**解析面**
        的失敗,不是「資料面就是沒有」—— 拿它當「不必重試」的理由是把兩件事混為一談。
        1K 首頁有沒有等滿是 TC4 協定側**唯一**的暫時性訊號,它為真就該往外拋。

        兩段都顯式帶 `BARS_POLL_DEADLINE`:預設是 `poll_wait*30` ≈ 30s **兩段** = 最壞
        60s,hub 的重試會把 executor 佔滿,而畫面只是疊線遲遲不來(P2-13)。

        **DK 段窗逐字 40 日;只有 1K fallback 段隨 `n` 縮**(N024,見
        `_daily_fallback_window_days`)。
        """
        self._ensure_connected()
        sym = stock_symbol(code)
        end_d = _dt.date.today()
        start_d = end_d - _dt.timedelta(days=_DAILY_WINDOW_DAYS)
        start, end = f"{start_d:%Y%m%d}00", f"{end_d:%Y%m%d}23"
        dk_rows, _dk_timed_out = self._collect_history(sym, "DK", start, end, BARS_POLL_DEADLINE)
        bars = _parse_dk_rows(dk_rows)
        if not bars:
            fb_start_d = end_d - _dt.timedelta(days=_daily_fallback_window_days(n))
            fb_start = f"{fb_start_d:%Y%m%d}00"
            logger.info("daily bars %s: DK 空,fallback 1K 聚合(視窗 %s..)", code, fb_start_d)
            fb_rows, fb_timed_out = self._collect_history(
                sym, "1K", fb_start, end, BARS_POLL_DEADLINE
            )
            if fb_timed_out:
                raise HistoryTimeoutError(f"daily bars {sym}:1K fallback 首頁未備妥")
            bars = _aggregate_1k_rows(fb_rows)
        return bars[-n:]

    # ---- listener:原始分派(覆寫 TXO 的 Tick 解析路徑)----

    def handle_raw(self, raw: str) -> None:
        """SUB socket 一則原始電文 → REALTIME Quote dict 分派(listener 與測試共用)。"""
        msg = self._realtime_msg(raw)
        if msg is None:
            return
        quote = msg.get("Quote", {})
        symbol = str(quote.get("Symbol", ""))
        if symbol:
            with self._seen_lock:
                self._seen.add(symbol)  # 健檢以 symbol 為鍵(D8;理由見 `_seen` 宣告處)
        if self._on_message is not None:
            self._on_message(quote)
