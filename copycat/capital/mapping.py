"""群益送單欄位映射 + TC4 → 期交所契約碼轉換(純函式;唯一的 IO = 個股期乘數 fallback)。

`multiplier_of` 對非指數期權產品會問 `stkfut_map.lookup_product` —— 那份版控對映檔
以 process 級索引 cache 讀,首呼一次 JSON 讀檔,之後純記憶體(檔頭原本的「零 IO」
約定隨 stkfut-contracts SC-2 更新為此)。


STOCKORDER 映射照搬 treading-king backend/services/capital_mapping.py(enum → Literal);
FUTUREORDER 用欄依 Task 0 spike 定案(docs/research/2026-07-28-skcom-typelib.md):
bstrFullAccount / bstrStockNo(=期交所契約碼)/ bstrPrice / sTradeType / sBuySell /
sDayTrade / sNewClose / nQty,餘欄不設。期交所市價單僅允許 IOC/FOK,mapping 層對
market+ROD 升 IOC(FOK 保留,review A9)+ bstrPrice="M"(test 沙盒未開通,literal
未實測;design §5 R4)。
月碼:期貨/Call 1-12 → A..L、Put 1-12 → M..X;年末碼 = 西元年最後一位。
"""

from __future__ import annotations

import re
from decimal import Decimal

from copycat.stkfut_map import lookup_product
from copycat.capital.models import (
    BuySell,
    FutureOrderRequest,
    PriceType,
    StockOrderRequest,
    TimeInForce,
    TradeKind,
)

# 元/點(safety 名目金額閘用;review R8)
MULTIPLIERS: dict[str, int] = {"TXF": 200, "MXF": 50, "TMF": 10, "TXO": 50}

# 週選家族(TAIEX 週選 TX1-TX5/TXY/TXZ、小台週選 MX1-MX5)同乘數 50(review R2)
_WEEKLY_50: frozenset[str] = frozenset(
    {"TX1", "TX2", "TX3", "TX4", "TX5", "TXY", "TXZ", "MX1", "MX2", "MX3", "MX4", "MX5"}
)

# 已知產品碼(乘數表 ∪ 週選家族),長者優先 — 契約碼反查最長前綴比對用(review A1)
_KNOWN_PRODUCTS: tuple[str, ...] = tuple(
    sorted(set(MULTIPLIERS) | _WEEKLY_50, key=len, reverse=True)
)

_BUYSELL: dict[BuySell, int] = {"buy": 0, "sell": 1}
_SPECIAL: dict[PriceType, int] = {"market": 1, "limit": 2}
_TIF: dict[TimeInForce, int] = {"ROD": 0, "IOC": 1, "FOK": 2}
_FLAG: dict[TradeKind, int] = {"cash": 0, "margin": 1, "short": 2, "daytrade_sell": 3}

_FUT_RE = re.compile(r"^TC\.F\.TWF\.(?P<prod>[A-Z0-9]+)\.(?P<ym>\d{6}|HOT)$")
# 段名對齊 live/models._OPTION_LEAF_RE;expiry 收斂到可轉月碼的 YYYYMM|HOT
# (週選特殊 token 格式 spike 未定,解析不到一律 ValueError → 400 INVALID_ORDER)
_OPT_RE = re.compile(
    r"^TC\.O\.TWF\.(?P<prod>[A-Z0-9]+)\.(?P<expiry>\d{6}|HOT)\.(?P<cp>[CP])\.(?P<strike>\d+)$"
)
_YM_RE = re.compile(r"^\d{6}$")


def multiplier_of(product: str) -> int:
    """product → 元/點乘數;未知 raise ValueError(route 層轉 400 INVALID_ORDER)。

    指數期權查內建表;查無再問個股期對映表(`stkfut_map.lookup_product`)——
    個股期的「乘數」= 契約單位股數(標準 2,000 / 小型 100),名目金額 = 價 × 股數。
    查得到但單位缺 / ≤0(含對映檔版本不符 → 空表)一律 ValueError:乘數是名目
    金額閘的分母,寧可拒單也不能用一個猜的數字放行。
    """
    if product in MULTIPLIERS:
        return MULTIPLIERS[product]
    if product in _WEEKLY_50:
        return 50
    stkfut = lookup_product(product)
    if stkfut is not None and isinstance(stkfut.get("unit"), int) and stkfut["unit"] > 0:
        return stkfut["unit"]
    raise ValueError(f"unknown product multiplier: {product!r}")


def product_of(tc4_symbol: str) -> str:
    """TC4 期權 symbol 第 4 段 = product(multiplier_of lookup 用)。"""
    parts = tc4_symbol.split(".")
    if len(parts) < 5 or parts[0] != "TC" or parts[1] not in ("F", "O"):
        raise ValueError(f"not a TC4 futures/options symbol: {tc4_symbol!r}")
    return parts[3]


def exchange_product_of(contract: str) -> str:
    """期交所契約碼 → product("TXFI6"→"TXF";fut 改價乘數反查用,review R7)。

    先對已知產品碼(MULTIPLIERS ∪ 週選家族)做最長前綴比對 —— 週選契約
    (如 "TX422000T6")用啟發式會截成 "TX" → 乘數反查失敗 fallback 1,
    金額閘鬆 50 倍(review A1)。比對不到才走啟發式:去尾 2 碼(月碼+年碼)
    後即產品碼;選擇權碼(如 "TXO20000I6")含履約價 → 取開頭連續英文字母段。
    """
    for prod in _KNOWN_PRODUCTS:
        if contract.startswith(prod):
            return prod
    body = contract[:-2]
    if body and body.isalpha():
        return body
    m = re.match(r"^[A-Z]+", contract)
    if m is None:
        raise ValueError(f"cannot derive product from contract: {contract!r}")
    return m.group(0)


def _month_year_codes(ym: str, *, put: bool = False) -> str:
    """YYYYMM → 月碼 + 年末碼(期貨/Call A..L、Put M..X)。"""
    year, month = int(ym[:4]), int(ym[4:6])
    if not 1 <= month <= 12:
        raise ValueError(f"month out of range: {ym!r}")
    base = "M" if put else "A"
    return chr(ord(base) + month - 1) + str(year % 10)


def _resolve_ym(ym: str, resolved_ym: str | None, tc4_symbol: str) -> str:
    if ym != "HOT":
        return ym
    if resolved_ym is None:
        raise ValueError(f"HOT month requires resolved_ym: {tc4_symbol!r}")
    if _YM_RE.match(resolved_ym) is None:
        raise ValueError(f"resolved_ym must be YYYYMM: {resolved_ym!r}")
    return resolved_ym


def to_exchange_symbol(tc4_symbol: str, *, resolved_ym: str | None = None) -> str:
    """TC4 symbol → 期交所契約碼(確定性轉換;解析不到 raise ValueError)。

    期貨 "TC.F.TWF.TXF.202609" → "TXFI6";月份欄 "HOT" 需帶 resolved_ym。
    選擇權 "TC.O.TWF.TXO.202609.C.20000" → "TXO20000I6"(履約價字串原樣)。
    """
    m = _FUT_RE.match(tc4_symbol)
    if m is not None:
        ym = _resolve_ym(m.group("ym"), resolved_ym, tc4_symbol)
        return m.group("prod") + _month_year_codes(ym)
    m = _OPT_RE.match(tc4_symbol)
    if m is not None:
        ym = _resolve_ym(m.group("expiry"), resolved_ym, tc4_symbol)
        return m.group("prod") + m.group("strike") + _month_year_codes(ym, put=m.group("cp") == "P")
    raise ValueError(f"cannot parse TC4 symbol: {tc4_symbol!r}")


def future_price_str(price: float) -> str:
    """期貨限價 → 數字字串:整數價去小數("23000")、有小數保留("96.5")。

    Decimal(str(price)) 避免 float 尾差(同 live/trade_models.price_str_from_millipts 手法)。
    送單與改價(review A6)共用 — 期貨端價格字串格式單一出口。
    """
    return format(Decimal(str(price)).normalize(), "f")


def to_stockorder_fields(req: StockOrderRequest, full_account: str) -> dict[str, object]:
    """StockOrderRequest → STOCKORDER 欄位 dict(treading-king 同款逐欄)。"""
    return {
        "bstrFullAccount": full_account,
        "bstrStockNo": req.stock_no,
        "sBuySell": _BUYSELL[req.buy_sell],
        "bstrPrice": f"{req.price:.2f}",
        "nQty": req.qty,
        "nSpecialTradeType": _SPECIAL[req.price_type],
        "nTradeType": _TIF[req.time_in_force],
        "sFlag": _FLAG[req.trade_kind],
        "sPeriod": 0,  # 盤中(僅盤中整股)
        "sPrime": 0,  # 上市櫃
    }


def to_futureorder_fields(
    req: FutureOrderRequest,
    futures_account: str,
    *,
    contract: str,
    new_close: int = 2,
) -> dict[str, object]:
    """FutureOrderRequest → FUTUREORDER 欄位 dict(期貨/選擇權共用,spike 定案用欄)。

    contract = 已解析期交所碼(HOT 由呼叫端先經 resolved_contract → to_exchange_symbol)。
    market → bstrPrice="M" + sTradeType 強制 IOC(ROD 靜默升級,message 註記由 client 組)。
    sNewClose 預設 2(自動);平倉單由 close.py 傳 new_close=1(review R1)。
    """
    if req.price_type == "market":
        price_str = "M"
        # 期交所市價不允許 ROD(掛整天)→ 升 IOC;FOK(全成或全撤)是使用者
        # 明示意圖,不可靜默降級(review A9)
        trade_type = _TIF["IOC"] if req.time_in_force == "ROD" else _TIF[req.time_in_force]
    else:
        price_str = future_price_str(req.price)
        trade_type = _TIF[req.time_in_force]
    return {
        "bstrFullAccount": futures_account,
        "bstrStockNo": contract,
        "bstrPrice": price_str,
        "sTradeType": trade_type,
        "sBuySell": _BUYSELL[req.buy_sell],
        "sDayTrade": int(req.day_trade),
        "sNewClose": new_close,
        "nQty": req.qty,
    }
