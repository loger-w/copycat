"""個股當日狀態機(零 IO;design v4 §2.2)。

- 去重主鍵 = 當日累積量 cum_vol(≤ 已見最大值即丟,TXO handover 同款)。
- 試撮 tick 在 dedup 前丟棄且不觸碰 `_last_cum`(試撮期 TradeVolume 為模擬值)。
- apply_backfill = 原子重建 + seq 跳增(前端跳號規則觸發全量 refetch,design §4)。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from copycat.live.stock_models import StockBook, StockMeta, StockTick

_TICKS_MAXLEN = 20_000  # 熱門股單日 6.2k 實測、漲停攻防股更高(design r1-F8)
_BACKFILL_SEQ_MARGIN = 1_000  # seq 跳增下限,確保前端必偵測到跳號


@dataclass
class MinuteAgg:
    close_milli: int = 0
    volume: int = 0
    inner: int = 0
    outer: int = 0
    unch: int = 0


@dataclass
class StockDayState:
    seq: int = 0
    minutes: dict[int, MinuteAgg] = field(default_factory=dict)
    ticks: deque[StockTick] = field(default_factory=lambda: deque(maxlen=_TICKS_MAXLEN))
    book: StockBook | None = None
    meta: StockMeta | None = None
    cum_inner: int = 0
    cum_outer: int = 0
    vwap_milli: int | None = None
    _last_cum: int = -1
    _amount_milli: int = 0  # Σ(價毫元 × 量),VWAP 分子
    _volume: int = 0

    @property
    def last(self) -> StockTick | None:
        return self.ticks[-1] if self.ticks else None

    def reset(self) -> None:
        self.seq = 0
        self.minutes = {}
        self.ticks = deque(maxlen=_TICKS_MAXLEN)
        self.cum_inner = 0
        self.cum_outer = 0
        self.vwap_milli = None
        self._last_cum = -1
        self._amount_milli = 0
        self._volume = 0
        # book/meta 保留 — 盤外顯示昨收靜態值依賴 meta(design §2.4 rollover 階段一不清)

    def ingest(self, tick: StockTick) -> bool:
        """True = 收下(通過試撮/去重);False = 丟棄。"""
        if tick.is_trial:
            return False  # dedup 前短路,不觸 _last_cum
        if tick.cum_vol <= self._last_cum:
            return False
        self._last_cum = tick.cum_vol
        self._apply(tick)
        self.seq += 1
        return True

    def apply_backfill(self, ticks: list[StockTick]) -> None:
        """原子重建 + merge:回補列為基底,回補期間已 ingest 的 live tick
        (cum > 回補上限)為倖存者接續重放 — 空回補即全數倖存,不洗掉 live 狀態。
        seq 一次跳增(前端跳號規則觸發全量 refetch,design §4)。"""
        old_seq = self.seq
        backfill_max = max((t.cum_vol for t in ticks), default=-1)
        survivors = [t for t in self.ticks if t.cum_vol > backfill_max]
        self.reset()
        for tick in ticks:
            if tick.is_trial:
                continue
            if tick.cum_vol > self._last_cum:
                self._last_cum = tick.cum_vol
            self._apply(tick)
        for tick in survivors:
            if tick.cum_vol > self._last_cum:
                self._last_cum = tick.cum_vol
                self._apply(tick)
        self.seq = old_seq + max(len(ticks), 1) + _BACKFILL_SEQ_MARGIN

    def update_book(self, book: StockBook) -> None:
        self.book = book

    def update_meta(self, meta: StockMeta) -> None:
        self.meta = meta

    def _apply(self, tick: StockTick) -> None:
        self.ticks.append(tick)
        self._amount_milli += tick.price_milli * tick.qty
        self._volume += tick.qty
        if self._volume:
            self.vwap_milli = round(self._amount_milli / self._volume)
        minute_key = int(tick.time[:2]) * 60 + int(tick.time[3:5])
        agg = self.minutes.setdefault(minute_key, MinuteAgg())
        agg.close_milli = tick.price_milli
        agg.volume += tick.qty
        if tick.side == "outer":
            agg.outer += tick.qty
            self.cum_outer += tick.qty
        elif tick.side == "inner":
            agg.inner += tick.qty
            self.cum_inner += tick.qty
        else:
            agg.unch += tick.qty

    def snapshot(self) -> dict:
        """REST 全量(design §4:snapshot 為前端累算基底)。"""
        last = self.last
        return {
            "seq": self.seq,
            "last": {"p": last.price_milli, "t": last.time, "cum_vol": last.cum_vol}
            if last
            else None,
            "vwap": self.vwap_milli,
            "cum_inner": self.cum_inner,
            "cum_outer": self.cum_outer,
            "minutes": {
                str(k): {
                    "c": m.close_milli,
                    "v": m.volume,
                    "i": m.inner,
                    "o": m.outer,
                    "u": m.unch,
                }
                for k, m in sorted(self.minutes.items())
            },
            "ticks": [
                {"t": t.time, "p": t.price_milli, "q": t.qty, "side": t.side} for t in self.ticks
            ],
            "book": {"bids": self.book.bids, "asks": self.book.asks} if self.book else None,
            "meta": {
                "name": self.meta.name,
                "ref": self.meta.ref_milli,
                "upper": self.meta.upper_milli,
                "lower": self.meta.lower_milli,
                "y_close": self.meta.y_close_milli,
                "y_vol": self.meta.y_volume,
            }
            if self.meta
            else None,
        }
