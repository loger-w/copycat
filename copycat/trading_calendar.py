"""台股交易日曆(mod/trading-calendar SC-1)— 純判定 + 版控假日表。

為什麼要這支:引擎原本用「牆鐘今天」當 trade_date,週末 / 國定假日冷啟動會去要一份
不存在的當日資料 → 空圖。這裡把「哪天有開盤」收斂成單一事實來源
(`configs/trading_holidays.json`,TWSE 官方 JSON 手動維護),讓各引擎共用同一份判定。

三個刻意的設計選擇:

1. **只列平日休市**:週末本來就由 `weekday()` 擋掉,清單再塞週末只會讓維護時對不上
   官方表。`extra_trading_days` 反向存在 —— 補班交易日(週末有開盤)是唯一需要覆寫
   週末規則的情形(2026 無,欄位先備著,模組零成本支援)。
2. **檔缺 = 只擋週末 + WARNING,不是錯誤**:日曆漂掉最壞是退回改動前的行為(假日被
   當交易日),絕不能因為少一個 config 就讓整個 server 起不來。壞檔(JSON 壞 / 形狀
   錯)則 raise —— 那是打錯字,靜默套預設會讓人以為日曆生效了(對齊 `signals_config`)。
3. **缺當年只 WARNING 不猜**:2027 官方表未公布時自動外推假日等於編資料,寧可只擋
   週末(永不多擋一天)並在 log 提醒更新 config。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

__all__ = [
    "DEFAULT_PATH",
    "WEEKEND_ONLY",
    "TradingCalendar",
    "load_trading_calendar",
    "resolve_trade_date",
    "warn_if_year_missing",
]

logger = logging.getLogger(__name__)

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "configs" / "trading_holidays.json"

# 往回找最近交易日的步數上限。實務最長連假 ~11 天,60 天純粹是「資料錯掉時要炸,
# 不要無窮迴圈」的保險絲。
_LOOKBACK_LIMIT_DAYS = 60


@dataclass(frozen=True, slots=True)
class TradingCalendar:
    """不可變的假日集合;所有方法零 IO(load 之後就只是純函式)。"""

    holidays: frozenset[date]
    extra_trading_days: frozenset[date]
    years_loaded: frozenset[int]

    def is_trading_day(self, d: date) -> bool:
        """補班日優先於週末規則,其餘 = 平日且不在假日表。"""
        return d in self.extra_trading_days or (d.weekday() < 5 and d not in self.holidays)

    def last_trading_day(self, d: date) -> date:
        """含 d 本身往回找最近交易日;超過保險絲仍找不到 = 日曆資料錯,raise。"""
        cur = d
        for _ in range(_LOOKBACK_LIMIT_DAYS):
            if self.is_trading_day(cur):
                return cur
            cur -= timedelta(days=1)
        raise RuntimeError(f"往回 {_LOOKBACK_LIMIT_DAYS} 天仍找不到交易日(起點 {d}),交易日曆資料有誤")

    def has_year(self, y: int) -> bool:
        """該年有沒有載到假日資料 —— 沒有代表此後只擋週末。"""
        return y in self.years_loaded


# 沒有日曆時的退化版本:只擋週末,永不多擋(等於改動前的行為)。
WEEKEND_ONLY = TradingCalendar(frozenset(), frozenset(), frozenset())

# 缺年 WARNING 的節流狀態:長跑 server 跨年時要再提醒一次,所以是「每個年份一次」
# 而不是「整個 process 一次」。
_warned_years: set[int] = set()


def _reset_year_warnings() -> None:
    """測試用:清掉節流狀態(module-level 狀態會跨測試殘留)。"""
    _warned_years.clear()


def _parse_days(raw: object, *, path: Path, year_key: str, field: str) -> set[date]:
    if not isinstance(raw, list):
        raise ValueError(
            f"交易日曆設定檔 {path} 形狀錯:years.{year_key}.{field} 應為 list,"
            f"實得 {type(raw).__name__}"
        )
    days: set[date] = set()
    for item in raw:
        if not isinstance(item, str):
            raise ValueError(
                f"交易日曆設定檔 {path} 形狀錯:years.{year_key}.{field} 元素應為 ISO 日期字串,"
                f"實得 {item!r}"
            )
        try:
            days.add(date.fromisoformat(item))
        except ValueError as exc:
            raise ValueError(
                f"交易日曆設定檔 {path} 日期無效:years.{year_key}.{field} 的 {item!r}"
            ) from exc
    return days


def load_trading_calendar(path: Path = DEFAULT_PATH) -> TradingCalendar:
    """讀假日表;檔缺 → WARNING + 只擋週末;JSON 壞 / 形狀錯 → ValueError(訊息帶路徑)。"""
    if not path.exists():
        logger.warning("交易日曆設定檔不存在(%s),只擋週末;國定假日將被當成交易日", path)
        return WEEKEND_ONLY

    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"交易日曆設定檔 {path} 不是合法 JSON:{exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"交易日曆設定檔 {path} 形狀錯:最外層應為物件")

    years_raw = raw.get("years")
    if not isinstance(years_raw, dict):
        raise ValueError(f"交易日曆設定檔 {path} 形狀錯:缺 years 物件")

    holidays: set[date] = set()
    extra: set[date] = set()
    years_loaded: set[int] = set()
    for year_key, entry in years_raw.items():
        if not isinstance(year_key, str) or not year_key.isdigit():
            raise ValueError(f"交易日曆設定檔 {path} 形狀錯:years 的鍵 {year_key!r} 不是年份")
        if not isinstance(entry, dict):
            raise ValueError(
                f"交易日曆設定檔 {path} 形狀錯:years.{year_key} 應為物件,"
                f"實得 {type(entry).__name__}"
            )
        holidays |= _parse_days(
            entry.get("holidays", []), path=path, year_key=year_key, field="holidays"
        )
        extra |= _parse_days(
            entry.get("extra_trading_days", []),
            path=path,
            year_key=year_key,
            field="extra_trading_days",
        )
        years_loaded.add(int(year_key))

    return TradingCalendar(
        holidays=frozenset(holidays),
        extra_trading_days=frozenset(extra),
        years_loaded=frozenset(years_loaded),
    )


def warn_if_year_missing(cal: TradingCalendar, today: date) -> None:
    """缺當年資料時提醒更新 config;同一年只叫一次(長跑 server 跨年會再叫)。"""
    year = today.year
    if cal.has_year(year) or year in _warned_years:
        return
    _warned_years.add(year)
    logger.warning(
        "交易日曆缺 %d 年資料,只擋週末;請更新 configs/trading_holidays.json",
        year,
    )


def resolve_trade_date(today: date, cal: TradingCalendar) -> date:
    """引擎要用的交易日 = 含今天往回的最近交易日(順手做缺年提醒)。"""
    warn_if_year_missing(cal, today)
    return cal.last_trading_day(today)
