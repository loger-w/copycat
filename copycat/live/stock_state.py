"""個股當日狀態機(零 IO;design v4 §2.2)。

- 去重主鍵 = 當日累積量 cum_vol(≤ 已見最大值即丟,TXO handover 同款)。
- 試撮 tick 在 dedup 前丟棄且不觸碰 `_last_cum`(試撮期 TradeVolume 為模擬值)。
- apply_backfill = 原子重建 + seq 跳增(前端跳號規則觸發全量 refetch,design §4)。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from copycat.live.stock_models import StockBook, StockMeta, StockTick, relabel_locked_side

_TICKS_MAXLEN = 20_000  # 熱門股單日 6.2k 實測、漲停攻防股更高(design r1-F8)
_BACKFILL_SEQ_MARGIN = 1_000  # seq 跳增下限,確保前端必偵測到跳號


@dataclass
class MinuteAgg:
    close_milli: int = 0
    volume: int = 0
    inner: int = 0
    outer: int = 0
    unch: int = 0
    # 分鐘內高低(round4 項 1)。分時圖要把當日高低標在「摸到的那一分鐘」上,而
    # top-level high/low 只有值沒有時間歸屬 —— 前端靠 `minute.h == accum.high` 等值反查
    # 定位,那條等式由 `_apply` 同源維護建構保證(day high = max(minute highs))。
    # **預設必須是 None 不是 0**:`min(0, price)` 會把最低價永久卡在 0,而且是靜默錯值。
    high_milli: int | None = None
    low_milli: int | None = None


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
    # 當日最高 / 最低成交價(round5 項 1)。刻意由本狀態機逐 tick 維護而不取 TC4 的
    # HighPrice/LowPrice —— 個股 REALTIME 帶不帶那兩個欄位沒有實證(2026-07-21 probe
    # 的 33 個欄位樣本裡沒有),而這裡握有當日全部 tick(含 apply_backfill 重放),
    # running max/min 是建構保證正確且天然單調。
    high_milli: int | None = None
    low_milli: int | None = None
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
        # 高低是當日衍生狀態,與 vwap 同批清;book/meta 才是盤外要保留的靜態值
        self.high_milli = None
        self.low_milli = None
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
        # 鎖停日的回補補判(round6 項 2)。歷史 TICKS row 只有單一 Bid/Ask 欄,鎖停時那欄
        # 就是市價佇列的 0 → `derive_side` 整天判 neutral;而本方法會先 reset() 再用回補
        # 重放,live 期間判好的值每次切檔都被洗掉(2026-07-31 實測 2327 切檔後
        # cum_outer = cum_inner = 0 回到原點)。meta 是 reset() 刻意保留的靜態值,
        # 補判的依據就在手上 —— 見 `relabel_locked_side` 的四道閘。
        if self.meta is not None:
            up, lo = self.meta.upper_milli, self.meta.lower_milli
            ticks = [relabel_locked_side(t, up, lo) for t in ticks]
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
        if self.high_milli is None or tick.price_milli > self.high_milli:
            self.high_milli = tick.price_milli
        if self.low_milli is None or tick.price_milli < self.low_milli:
            self.low_milli = tick.price_milli
        self._amount_milli += tick.price_milli * tick.qty
        self._volume += tick.qty
        if self._volume:
            self.vwap_milli = round(self._amount_milli / self._volume)
        minute_key = int(tick.time[:2]) * 60 + int(tick.time[3:5])
        agg = self.minutes.setdefault(minute_key, MinuteAgg())
        agg.close_milli = tick.price_milli
        # 與 top-level high/low 同一批維護 → day high == max(minute highs) 由建構保證
        agg.high_milli = (
            tick.price_milli if agg.high_milli is None else max(agg.high_milli, tick.price_milli)
        )
        agg.low_milli = (
            tick.price_milli if agg.low_milli is None else min(agg.low_milli, tick.price_milli)
        )
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
            # 高低與 vwap 同層(top-level)不進 meta:meta 是 TC4 來的靜態盤別資料
            # (名稱 / 參考價 / 漲跌停),而高低是由成交推導的當日狀態。放這裡之後
            # meta 為 None(只跑過回補、未收 REALTIME)時高低照樣有值。
            "high": self.high_milli,
            "low": self.low_milli,
            "cum_inner": self.cum_inner,
            "cum_outer": self.cum_outer,
            "minutes": {
                str(k): {
                    "c": m.close_milli,
                    "v": m.volume,
                    "i": m.inner,
                    "o": m.outer,
                    "u": m.unch,
                    # additive(round4 項 1):舊前端忽略未知 key;新前端缺 key 時填 null
                    # 而不是拿 c 頂替 —— 頂替會讓等值反查命中錯的分鐘 = 靜默標錯位置
                    "h": m.high_milli,
                    "l": m.low_milli,
                }
                for k, m in sorted(self.minutes.items())
            },
            "ticks": [
                {
                    "t": t.time,
                    "p": t.price_milli,
                    "q": t.qty,
                    "side": t.side,
                    "b": t.bid_milli,
                    "a": t.ask_milli,
                }
                for t in self.ticks
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
