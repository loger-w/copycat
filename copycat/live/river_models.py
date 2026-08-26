"""江波圖的純對映層(design v2 §1/§4;零 IO、只依賴 stdlib)。

**分鐘鍵一律「終點標記」**(bar end),與 TC4 1K 的 `Time` 語意一致:

- 1K row 的 `Time`(UTC HHMMSS)**已是 bar 終點**(2026-07-30 probe:CME 首列 `Time=100`
  = UTC 00:01 的 bar 覆蓋 00:00–00:01;UDF 首列 `004600` = 台北 08:46,而日盤 08:45 開盤)
  → 換台北只 +8 小時,**不加 1**。
- live 推播的成交時刻是瞬時點 → 桶 = `floor(分) + 1`,與 1K 對齊(同 `index_engine.minute_key`
  / `stock_source._taipei_minute_key` 的 floor+1 手法)。

窗以「台北 minute-of-day」表示,夜盤跨午夜以 +1440 展開,故上界可 > 1440。收盤補正 clamp
(`end < m <= end+5` → `end`)沿用既有兩處 1331–1335 → 1330 的慣例 —— 少了它,日盤
13:45:xx / 夜盤 05:00:xx 的成交會整段被丟掉(design review P0-1)。

`all_day_utc_window` 與 `corr_source.all_day_window` 三行重複是刻意的:那條是 REALTIME
訂閱窗(已上線且有測試),本條是回補窗;放這裡讓 `futures_source` 不必逆依賴相關係數模組
(design review P1-2)。
"""

from __future__ import annotations

import logging
import time
from typing import NamedTuple

logger = logging.getLogger(__name__)

__all__ = [
    "SESSION_WINDOWS",
    "Parsed1k",
    "all_day_utc_window",
    "close_clamp_rank",
    "minute_end_from_1k",
    "minute_end_from_taipei",
    "minute_end_from_utc_hhmmss",
    "offset_of",
    "parse_1k_minutes",
    "window_bounds",
]

#: 台北 minute-of-day 窗:start = x 軸原點(該分鐘的 bar 屬開盤前,不收)、end = 上界
SESSION_WINDOWS: dict[str, tuple[int, int]] = {
    "day": (525, 825),  # 08:45 – 13:45
    "night": (900, 1740),  # 15:00 – 次日 05:00
}

_DAY_MINUTES = 1440
#: 收盤補正寬度(分):與既有 1331–1335 → 1330 同寬
_CLOSE_CLAMP = 5


def window_bounds(kind: str) -> tuple[int, int]:
    """盤別 → (start_min, end_min);未知盤別回日盤窗(never-raise:引擎不因盤別字串倒)。"""
    return SESSION_WINDOWS.get(kind, SESSION_WINDOWS["day"])


def _expand(minute_end: int, kind: str) -> tuple[int, int, int]:
    """跨午夜展開後的 `(m, start, end)` —— `offset_of` 與 `close_clamp_rank` 的同一把尺。

    兩者若各自展開,clamp 判定與分桶會在夜盤跨午夜那一段悄悄錯開(00:30 這種分鐘一邊
    是 30、一邊是 1470)。
    """
    start, end = window_bounds(kind)
    m = minute_end + _DAY_MINUTES if minute_end < start else minute_end
    return m, start, end


def offset_of(minute_end: int, kind: str) -> int | None:
    """台北 minute-of-day(終點標記)→ 窗內 offset(1..N);窗外 None。

    跨午夜:小於窗首的分鐘先 +1440 展開(夜盤 00:30 排在 23:00 之後)。
    收盤補正:`end < m <= end + 5` 併入 `end`。
    """
    m, start, end = _expand(minute_end, kind)
    if m > end:
        if m > end + _CLOSE_CLAMP:
            return None
        m = end
    offset = m - start
    return offset if offset >= 1 else None


def close_clamp_rank(minute_end: int, kind: str) -> int | None:
    """收盤補正的「第幾分鐘」:非 clamp 0、`end+1` → 1、…、`end+5` → 5;超出 clamp 窗 None。

    `offset_of` 把 `end+1..end+5` 全部併進 `end` 格,少了名次就分不出「13:45:xx 的收盤
    撮合」(桶 = end+1,必須寫得進來)與「13:46 之後的殘留取樣」(蓋掉真收盤)。
    判定由 `RiverState.push` 使用;`offset_of` 的輸出不受影響。

    **`minute_end` 只收 live 慣例(floor+1)的分鐘鍵** —— `minute_end_from_taipei` /
    `minute_end_from_utc_hhmmss` 那一路,**不收** `minute_end_from_1k`(1K 的 `Time`
    已是終點標記,不加 1)。同一個牆鐘分鐘在兩種慣例下差 1,名次跟著整排位移一格:
    13:46 那一分鐘的成交在 1K 鍵下算出 rank 1(= 收盤撮合,放行),守門就漏掉第一個
    殘留分鐘 —— 而它正是最常見的那一個。這條慣例目前只靠呼叫點成立(`RiverState.push`
    吃的是 live 鍵;回補走 `apply_backfill`,只填空缺、根本不查名次)。
    """
    m, _start, end = _expand(minute_end, kind)
    if m <= end:
        return 0
    if m > end + _CLOSE_CLAMP:
        return None
    return m - end


def _hh_mm(hh_raw: str, mm_raw: str) -> tuple[int, int] | None:
    try:
        hh, mm = int(hh_raw), int(mm_raw)
    except ValueError:
        return None
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None
    return hh, mm


def minute_end_from_taipei(hhmmss: str) -> int | None:
    """台北時刻("HH:MM:SS.fff" 或 "HHMMSS")→ floor(分)+1 的 minute-of-day;壞格式 None。

    23:59:xx → 1440(不是 0):夜盤 offset 靠這個才連續。
    """
    raw = str(hhmmss).strip()
    if not raw:
        return None
    if ":" in raw:
        parts = raw.split(":")
        if len(parts) < 2:
            return None
        parsed = _hh_mm(parts[0], parts[1])
    else:
        padded = raw.zfill(6)
        parsed = _hh_mm(padded[:2], padded[2:4])
    if parsed is None:
        return None
    hh, mm = parsed
    return hh * 60 + mm + 1


def minute_end_from_utc_hhmmss(raw: str) -> int | None:
    """UTC `HHMMSS`(TC4 `FilledTime`)→ floor(分)+1 的台北 minute-of-day;壞格式 None。

    **為什麼不用 `PreciseTime`**(2026-07-30 real-env 實證):該欄的寬度跨交易所段不同 ——
    台期交是 `HHMMSSffffff`(微秒),CME/CBOT/SGX 是 `HHMMSS`(實測 MES 為 `"41256"`)。
    `stock_models._taipei_time` 的 `zfill(12)` 對後者會算出恆為台北 08:00:00.0xx 的假時刻,
    分鐘落在盤別窗外 → 該腿永遠不進點(相關係數只用五檔中價,所以沒被這個問題咬到)。
    `FilledTime` 兩段同寬。`index_engine` 對 IX0001 **不能**靠它:指數 quote 的 `FilledTime` /
    `PreciseTime` 恆 `'0'`(2026-08-26 probe),那邊**時間欄位全零**時退回台北牆鐘(比本函式的
    「壞格式 None → corr 退回本機時鐘」窄:非全零的壞格式在 index 仍靜默不寫分鐘)。
    """
    text = str(raw).strip()
    if not text:
        return None
    padded = text.zfill(6)
    parsed = _hh_mm(padded[:2], padded[2:4])
    if parsed is None:
        return None
    hh, mm = parsed
    return ((hh + 8) % 24) * 60 + mm + 1


def minute_end_from_1k(row: dict) -> int | None:
    """1K row 的 UTC `Time` → 台北 minute-of-day(**不加 1**,TC4 已是終點標記)。"""
    raw = str(row.get("Time", "") or "")
    if not raw:
        return None
    padded = raw.zfill(6)
    parsed = _hh_mm(padded[:2], padded[2:4])
    if parsed is None:
        return None
    hh, mm = parsed
    return ((hh + 8) % 24) * 60 + mm


class Parsed1k(NamedTuple):
    """`parse_1k_minutes` 的回傳:分鐘序列 + 兩種「沒留下來」的**分帳**。

    呼叫端要分得出「列解析不了」(`skipped`,欄位缺漏 / 格式)與「列被 Date 閘丟掉」
    (`dropped`)—— 只有後者是凍結 stub 的簽名。合成一個數字的話,`rows` 非空而
    `minutes` 全空這件事就同時對兩種完全不同的故障成立,那句固定字串也就失去診斷力。
    """

    minutes: list[tuple[int, int]]
    skipped: int
    dropped: int


def parse_1k_minutes(rows: list[dict], utc_day: str | None = None) -> Parsed1k:
    """1K rows → [(minute_end, close 毫點)],保持原始列序。

    壞列略過並計數 warning(沿用 `stock_source` 慣例:靜默丟列會讓回補缺口無從診斷)。
    同一分鐘可能出現多列(收盤 clamp 區)→ 不在這裡去重,由 `RiverState` 的 dict 寫入收斂。

    `utc_day`(`"YYYYMMDD"`,= 回補窗的起點日)給定時,`Date` 存在且不等於它的列一律丟棄。
    **這裡的比對是純 UTC,刻意不做台北換算**:回補窗本身就是 `all_day_utc_window()` 產的
    UTC 全天窗(兩個盤別各自完整落在單一 UTC 日),兩邊用同一把尺才不會在夜盤跨午夜那
    一段自己跟自己錯開。丟的是**凍結 stub**:TC4 對「窗內當下無資料時建立的 history
    訂閱」回的是別日的殘留列,而 `minute_end_from_1k` 只讀 `Time` → 那些列會變成今日分鐘
    餵進江波圖,畫出一條來自別天的線且零錯誤訊號(`Date` 缺值的列照舊保留:真實 1K 恆有
    此欄,缺值只可能是治具/新欄位,不該連帶丟資料 —— 但**閘對它形同不存在**,所以缺值
    要留一行 warning:TC4 哪天換了欄名,「閘還在跑」與「閘被繞過」在畫面上完全一樣)。
    """
    out: list[tuple[int, int]] = []
    skipped = 0
    dropped = 0
    missing_date = 0
    for row in rows:
        if utc_day is not None:
            raw_date = str(row.get("Date", "") or "")
            if not raw_date:
                missing_date += 1
            elif raw_date != utc_day:
                dropped += 1
                continue
        minute = minute_end_from_1k(row)
        if minute is None:
            skipped += 1
            continue
        try:
            close = round(float(row["Close"]) * 1000)
        except (KeyError, TypeError, ValueError):
            skipped += 1
            continue
        out.append((minute, close))
    if skipped:
        logger.warning("1K rows 解析略過 %d/%d 列(欄位缺漏/格式)", skipped, len(rows))
    if dropped:
        logger.warning("1K rows 丟棄 %d/%d 列(Date ≠ 窗口日 %s)", dropped, len(rows), utc_day)
    if missing_date:
        # 整批**一行**(不是每列一行):換欄名那天 rows 是整頁上千列,逐列印等於把
        # 這則診斷自己洗掉
        logger.warning("1K rows 缺 Date 欄,Date 閘失效(%d/%d 列)", missing_date, len(rows))
    return Parsed1k(out, skipped, dropped)


def all_day_utc_window(now: time.struct_time | None = None) -> tuple[str, str]:
    """回補用當日 UTC 全天窗 ("YYYYMMDD00", "YYYYMMDD23")。

    兩個盤別各自完整落在單一 UTC 日(`live/session.py` 時區事實:日盤 UTC 00:45–05:45、
    夜盤 UTC 07:00–21:00)→ 全天窗即涵蓋,不需跨日拼接。
    """
    t = time.gmtime() if now is None else now
    ymd = time.strftime("%Y%m%d", t)
    return (f"{ymd}00", f"{ymd}23")
