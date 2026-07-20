"""tick / 合約資料模型與 TC4 訊息對映(欄位事實:docs/research/2026-07-18-txo-chain-probe.md)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

MULTIPLIER = 50  # TXO 每點 NTD

# TXF 現貨 symbol(zmq-free 常數;tc4.py re-export — server 端 import 不拉 pyzmq,review C1)
SPOT_SYMBOL = "TC.F.TWF.TXF.HOT"  # 台指期在 TC4 symbol 樹的產品碼是 TXF(FITX 不存在,07-20 實證)

_OPTION_LEAF_RE = re.compile(
    r"^TC\.O\.TWF\.(?P<prod>[A-Z0-9]+)\.(?P<expiry>[0-9A-Z/]+)\.(?P<cp>[CP])\.(?P<strike>\d+)$"
)


def to_millipts(raw: str) -> int | None:
    """十進位字串 → 毫點整數(點 × 1000);空/無效 → None。"""
    if not raw:
        return None
    try:
        return int(Decimal(raw) * 1000)
    except InvalidOperation:
        return None


@dataclass(frozen=True)
class OptionContract:
    symbol: str
    cp: str  # "C" | "P"
    strike_millipts: int


@dataclass(frozen=True)
class Tick:
    symbol: str
    precise_time: int  # HHMMSS + 微秒串接整數,僅供排序
    price_millipts: int
    qty: int
    bid_millipts: int | None
    ask_millipts: int | None
    cum_volume: int | None  # 當日累積量;歷史 TICKS 無此欄(None)
    seq: int = 0  # 歷史 QryIndex(同 precise_time 時的次序鍵)


@dataclass(frozen=True)
class SeriesInfo:
    series_id: str
    name: str
    expiry: str
    contracts: tuple[OptionContract, ...]


def _to_int(raw: str) -> int | None:
    try:
        return int(raw)
    except ValueError:
        return None


def parse_history_tick(symbol: str, raw: dict) -> Tick | None:
    """歷史 TICKS row → Tick;缺 price/qty/PreciseTime → None。cum_volume 恆 None(spike 實測)。"""
    price = to_millipts(raw.get("TradingPrice", ""))
    qty = _to_int(raw.get("TradeQuantity", ""))
    ptime = _to_int(raw.get("PreciseTime", ""))
    if price is None or qty is None or qty <= 0 or ptime is None:
        return None
    seq = _to_int(raw.get("QryIndex", "")) or 0
    return Tick(
        symbol=symbol,
        precise_time=ptime,
        price_millipts=price,
        qty=qty,
        bid_millipts=to_millipts(raw.get("Bid", "")),
        ask_millipts=to_millipts(raw.get("Ask", "")),
        cum_volume=None,
        seq=seq,
    )


def parse_realtime(raw: dict) -> Tick | None:
    """REALTIME Quote dict → Tick(DR-4 隔離層);無成交(qty 空/0)→ None。

    例外:TC.F.*(現價源)只取 price,qty 可為 0 — 休市 snapshot 無成交量
    仍要能更新現價線(Phase 6 實測)。
    """
    symbol = raw.get("Symbol", "")
    price = to_millipts(raw.get("TradingPrice", ""))
    qty = _to_int(raw.get("TradeQuantity", ""))
    ptime = _to_int(raw.get("PreciseTime", ""))
    if not symbol or price is None or ptime is None:
        return None
    if qty is None or qty <= 0:
        if not symbol.startswith("TC.F."):
            return None
        qty = 0
    return Tick(
        symbol=symbol,
        precise_time=ptime,
        price_millipts=price,
        qty=qty,
        bid_millipts=to_millipts(raw.get("Bid", "")),
        ask_millipts=to_millipts(raw.get("Ask", "")),
        cum_volume=_to_int(raw.get("TradeVolume", "")),
    )


def parse_option_symbol(symbol: str) -> tuple[str, str, str, int] | None:
    """TC.O.TWF.<prod>.<expiry>.<C|P>.<strike> → (prod, expiry, cp, strike_pts)。"""
    m = _OPTION_LEAF_RE.match(symbol)
    if m is None:
        return None
    return m.group("prod"), m.group("expiry"), m.group("cp"), int(m.group("strike"))
