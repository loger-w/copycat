"""ChainAggregator:零 IO 聚合狀態機(內外盤累積 → 損益曲線 snapshot)。design.md §2。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from copycat.live.models import SPOT_PREFIX, OptionContract, SeriesInfo, Tick
from copycat.live.payoff import (
    PositionRow,
    build_grid,
    curve_points,
    extremes,
    find_beps,
    interp_pnl,
)

logger = logging.getLogger(__name__)

_SPOT_PREFIX = SPOT_PREFIX  # 台指期產品樹(含月份 leaf);單一定義在 models.py


@dataclass
class Totals:
    ticks: int = 0
    unclassified_ticks: int = 0
    unclassified_qty: int = 0
    overlap_risk_ticks: int = 0
    dropped_foreign_ticks: int = 0


@dataclass
class _PosState:
    net_qty: int = 0
    net_cost_millipts: int = 0
    volume: int = 0
    outer_qty: int = 0
    inner_qty: int = 0
    last_price_millipts: int | None = None


class ChainAggregator:
    """單一 active 序列的逐檔累積;台指期(`SPOT_PREFIX`)只更新 spot(DR-9 分流)。

    其餘期貨(個股期 / 海外腿 / 費半 / 小台微台)一律走 foreign 丟棄計數 —— 它們會
    出現在這條流上是因為 TXO runtime 的 ZMQ SUB 訂 `""`,收得到同 process 其他引擎的
    訂閱推播,不是本序列的資料。"""

    def __init__(self, contracts: Iterable[OptionContract]) -> None:
        self._contracts: dict[str, OptionContract] = {}
        self._pos: dict[str, _PosState] = {}
        self._last_cum: dict[str, int] = {}
        self.totals = Totals()
        self.spot_millipts: int | None = None
        self.reset(contracts)

    def reset(self, contracts: Iterable[OptionContract]) -> None:
        """DR-3:清空全部 per-symbol 狀態並替換合約集合(select 切換時呼叫)。"""
        self._contracts = {c.symbol: c for c in contracts}
        for c in self._contracts.values():
            # DR-5/CR-2:非整數點履約價於載入時警告一次,不在 snapshot 廣播路徑洗版
            if c.strike_millipts % 1000 != 0:
                logger.warning("non-integer strike_millipts=%d (%s)", c.strike_millipts, c.symbol)
        self._pos = {}
        self._last_cum = {}
        self.totals = Totals()
        # spot 獨立於序列(DR-13),reset 不清

    def route(self, tick: Tick) -> None:
        if tick.symbol.startswith(_SPOT_PREFIX):
            self.spot_millipts = tick.price_millipts
            return
        if tick.symbol not in self._contracts:
            self.totals.dropped_foreign_ticks += 1
            return
        self._ingest(tick)

    def _ingest(self, tick: Tick) -> None:
        if tick.cum_volume is not None:
            last = self._last_cum.get(tick.symbol)
            if last is not None and tick.cum_volume <= last:
                return  # stale-drop(重複推播 / 重連重放 / 回補重疊)
            self._last_cum[tick.symbol] = tick.cum_volume
        self.totals.ticks += 1
        pos = self._pos.setdefault(tick.symbol, _PosState())
        pos.volume += tick.qty
        # 成交價與內外盤分類無關 → 放三分支之前(未分類 tick 也是成交,一樣更新);
        # stale-drop 已在上面早退,被丟的重複/重放 tick 不會蓋掉現價。
        pos.last_price_millipts = tick.price_millipts
        if tick.ask_millipts is not None and tick.price_millipts >= tick.ask_millipts:
            pos.net_qty += tick.qty
            pos.net_cost_millipts += tick.qty * tick.price_millipts
            pos.outer_qty += tick.qty
        elif tick.bid_millipts is not None and tick.price_millipts <= tick.bid_millipts:
            pos.net_qty -= tick.qty
            pos.net_cost_millipts -= tick.qty * tick.price_millipts
            pos.inner_qty += tick.qty
        else:
            self.totals.unclassified_ticks += 1
            self.totals.unclassified_qty += tick.qty

    def ingest_backfill(self, ticks: list[Tick]) -> dict[str, int]:
        """回補灌入:按 (symbol, precise_time, seq) 排序;重建 cum(Σqty)寫 _last_cum。

        回傳 rebuilt cum(交接協定 step 3;design.md §2.3 混合去重制)。
        """
        rebuilt: dict[str, int] = {}
        for tick in sorted(ticks, key=lambda t: (t.symbol, t.precise_time, t.seq)):
            if tick.symbol.startswith(_SPOT_PREFIX) or tick.symbol not in self._contracts:
                continue
            self._ingest(tick)
            rebuilt[tick.symbol] = rebuilt.get(tick.symbol, 0) + tick.qty
        for symbol, cum in rebuilt.items():
            self._last_cum[symbol] = max(cum, self._last_cum.get(symbol, 0))
        return rebuilt

    def last_cum(self, symbol: str) -> int | None:
        return self._last_cum.get(symbol)

    def _contract_rows(self) -> list[dict]:
        """SC-1 per-contract 明細:strike 升冪、同 strike C 在前(deterministic)。"""
        rows: list[dict] = []
        for sym, st in self._pos.items():
            contract = self._contracts[sym]
            rows.append(
                {
                    "symbol": sym,
                    "cp": contract.cp,
                    "strike": contract.strike_millipts // 1000,
                    "net_qty": st.net_qty,
                    "volume": st.volume,
                    "outer_qty": st.outer_qty,
                    "inner_qty": st.inner_qty,
                    # 點(對齊 spot.price 慣例);row 只在 _ingest 建 → 實務上恆非 None
                    "last_price": (
                        st.last_price_millipts / 1000
                        if st.last_price_millipts is not None
                        else None
                    ),
                }
            )
        rows.sort(key=lambda r: (r["strike"], r["cp"]))
        return rows

    def snapshot(
        self,
        *,
        series: SeriesInfo,
        status: str,
        accumulated_from: str,
        generated_at: str = "",
        queue_dropped: int = 0,
    ) -> dict:
        rows = [
            PositionRow(
                contract=self._contracts[sym],
                net_qty=st.net_qty,
                net_cost_millipts=st.net_cost_millipts,
            )
            for sym, st in self._pos.items()
        ]
        active_rows = [r for r in rows if r.net_qty != 0 or r.net_cost_millipts != 0]
        curve: list[tuple[int, float]] = []
        if active_rows:
            grid = build_grid([r.contract.strike_millipts for r in active_rows])
            curve = curve_points(active_rows, grid)
        beps = find_beps(curve) if curve else []
        max_profit: dict | None = None
        max_loss: dict | None = None
        if curve:
            (px, py), (lx, ly) = extremes(curve)
            max_profit = {"x": px, "y": py}
            max_loss = {"x": lx, "y": ly}
        spot_pnl: float | None = None
        if curve and self.spot_millipts is not None:
            spot_pnl = interp_pnl(curve, self.spot_millipts)
        call_net = 0
        put_net = 0
        for r in rows:
            if r.contract.cp == "C":
                call_net += r.net_qty
            elif r.contract.cp == "P":
                put_net += r.net_qty
        return {
            "series_id": series.series_id,
            "series_name": series.name,
            "status": status,
            "accumulated_from": accumulated_from,
            "generated_at": generated_at,
            "spot": {
                "symbol": "TXF",
                "price": self.spot_millipts / 1000 if self.spot_millipts is not None else None,
            },
            "curve": [(k, pnl) for k, pnl in curve],
            "beps": beps,
            "max_profit": max_profit,
            "max_loss": max_loss,
            "spot_pnl": spot_pnl,
            "contracts": self._contract_rows(),
            "totals": {
                "call_net_qty": call_net,
                "put_net_qty": put_net,
                "contracts_active": len(active_rows),
                "ticks": self.totals.ticks,
                "unclassified_ticks": self.totals.unclassified_ticks,
                "unclassified_qty": self.totals.unclassified_qty,
                "overlap_risk_ticks": self.totals.overlap_risk_ticks,
                "dropped_foreign_ticks": self.totals.dropped_foreign_ticks,
                "queue_dropped": queue_dropped,
            },
        }
