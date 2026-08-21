"""tick / 合約資料模型與 TC4 訊息對映(欄位事實:docs/research/2026-07-18-txo-chain-probe.md)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from copycat.tc4common import to_milli_units

MULTIPLIER = 50  # TXO 每點 NTD

# TXF 現貨 symbol(zmq-free 常數;tc4.py re-export — server 端 import 不拉 pyzmq,review C1)
SPOT_SYMBOL = "TC.F.TWF.TXF.HOT"  # 台指期在 TC4 symbol 樹的產品碼是 TXF(FITX 不存在,07-20 實證)
#: 現價源判定前綴 = **台指期產品樹**,含 HOT 與月份 leaf(`TC.F.TWF.TXF.202609`)。
#:
#: **不可放寬成 `"TC.F."`**:TXO runtime 的 ZMQ SUB 訂 `""`,會收到同 process 其他引擎訂的
#: 所有期貨推播 —— 個股期(`TC.F.TWF.DHF.HOT`)、海外腿(`TC.F.CME.YM.HOT` 等)、
#: 費半、小台微台。整棵樹前綴會讓它們輪流覆寫現價,右上角台指與 TXO 綜合損益的
#: `spot_pnl` 一起亂跳(2026-07-29 盤中實測個股期 232.5 顯示成台指)。
#:
#: 留 leaf 而非只認 `SPOT_SYMBOL` 完全相等:`futures_engine` 在 HOT 零推播時會補訂月份
#: leaf(refcount 被別把 key 帶走後的復活路徑 —— leaf 是不同 symbol,天然是新 key;見
#: `.claude/skills/tc4-market-facts/SKILL.md`),那是同一標的同一價位,
#: 也是該情境下唯一的現價來源。
SPOT_PREFIX = "TC.F.TWF.TXF."

_OPTION_LEAF_RE = re.compile(
    r"^TC\.O\.TWF\.(?P<prod>[A-Z0-9]+)\.(?P<expiry>[0-9A-Z/]+)\.(?P<cp>[CP])\.(?P<strike>\d+)$"
)


#: 十進位字串 → 毫點整數(點 × 1000);空/無效 → None。
#: 與 `live.stock_models.to_milli` 同一個運算(單位名不同)→ 實作在 tc4common,此處留具名別名。
to_millipts = to_milli_units


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

    例外:台指期(`SPOT_PREFIX`,現價源)只取 price,qty 可為 0 — 休市 snapshot
    無成交量仍要能更新現價線(Phase 6 實測)。**這個例外只給台指期**:放寬到整棵
    `TC.F.*` 會讓個股期 / 海外腿的零量 snapshot 也流進 `ChainAggregator.route`。
    """
    symbol = raw.get("Symbol", "")
    price = to_millipts(raw.get("TradingPrice", ""))
    qty = _to_int(raw.get("TradeQuantity", ""))
    ptime = _to_int(raw.get("PreciseTime", ""))
    if not symbol or price is None or ptime is None:
        return None
    if qty is None or qty <= 0:
        if not symbol.startswith(SPOT_PREFIX):
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
