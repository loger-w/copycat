"""期貨 REALTIME 對映(capital-order SC-8;design §10)。

期貨 REALTIME 欄位與個股同構(TradingPrice/TradeQuantity/累積 TradeVolume/五檔位移
命名 `Bid`=最佳;stkfut 推播已在 stock_engine 走同一組欄位)→ 對映直接重用
stock_models.parse_stock_realtime,本模組只加期貨特有部分:

- `product_from_symbol`:推播 Symbol → 產品碼(TXF/MXF/TMF 路由;Security 欄是舊命名
  FITX 不可靠,2026-07-20 實測)。
- `resolve_contract_ym`:HOT 訂閱推播 → 實際契約月份 YYYYMM(HOT 換碼送單用;解析不到
  一律 None = 送單層拒單,不猜月份 — design §5 edge case 4)。

註:parse_stock_realtime 的 is_trial 以個股試撮窗計,期貨無試撮 → 引擎層忽略該旗標。
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from copycat.live.stock_models import StockBook, StockMeta, StockTick, parse_stock_realtime

__all__ = [
    "PRODUCTS",
    "StockBook",
    "StockMeta",
    "StockTick",
    "parse_futures_realtime",
    "product_from_symbol",
    "resolve_contract_ym",
]

PRODUCTS: tuple[str, ...] = ("TXF", "MXF", "TMF")

# 期貨 REALTIME 對映 = 個股同款(別名,單一實作)
parse_futures_realtime = parse_stock_realtime

_SYMBOL_RE = re.compile(r"^TC\.F\.TWF\.(?P<prod>[A-Z0-9]+)\.(?P<tail>[A-Z0-9]+)$")
_YM_RE = re.compile(r"^(20\d{2})(0[1-9]|1[0-2])$")
_YMD_RE = re.compile(r"^(20\d{2})(0[1-9]|1[0-2])\d{2}$")
# 內嵌形:202609 / 2026/09 / 2026-09
_EMBEDDED_YM_RE = re.compile(r"(20\d{2})[/\-]?(0[1-9]|1[0-2])")


def product_from_symbol(symbol: str) -> str | None:
    """推播 Symbol → 產品碼;HOT 形與實際月份形都認得,非期貨樹 → None。"""
    m = _SYMBOL_RE.match(symbol)
    return m.group("prod") if m is not None else None


def resolve_contract_ym(payload: Mapping[str, object]) -> str | None:
    """HOT 推播 → 實際契約月份 YYYYMM;解析不到 None(不猜月份)。

    候選序(design §10:解析源依實測,先信最結構化的欄位):
    1. Symbol 已是 TC.F.TWF.<prod>.<YYYYMM> 形 → 直取。
    2. EndDate(YYYYMMDD 到期日;TXO REALTIME 實測有此欄,期貨結算日落在契約月)。
    3. SecurityName / Security 內嵌 YYYYMM(202609、2026/09、2026-09 形)。
    """
    sym = str(payload.get("Symbol", ""))
    m = _SYMBOL_RE.match(sym)
    if m is not None and _YM_RE.match(m.group("tail")) is not None:
        return m.group("tail")
    end_date = _YMD_RE.match(str(payload.get("EndDate", "")))
    if end_date is not None:
        return end_date.group(1) + end_date.group(2)
    for field in ("SecurityName", "Security"):
        embedded = _EMBEDDED_YM_RE.search(str(payload.get(field, "")))
        if embedded is not None:
            return embedded.group(1) + embedded.group(2)
    return None
