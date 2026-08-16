"""個股當日狀態機(零 IO;design v4 §2.2)。

- 去重主鍵 = 當日累積量 cum_vol(≤ 已見最大值即丟,TXO handover 同款)。
- 試撮 tick 在 dedup 前丟棄且不觸碰 `_last_cum`(試撮期 TradeVolume 為模擬值)。
- apply_backfill = 原子重建 + seq 跳增(前端跳號規則觸發全量 refetch,design §4)。
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field

from copycat.live.stock_models import StockBook, StockMeta, StockTick, relabel_locked_side
from copycat.market import snap_down_milli

logger = logging.getLogger(__name__)

_TICKS_MAXLEN = 20_000  # 熱門股單日 6.2k 實測、漲停攻防股更高(design r1-F8)
_BACKFILL_SEQ_MARGIN = 1_000  # seq 跳增下限,確保前端必偵測到跳號
#: VP 的分鐘窗 = 前端分時圖幾何的 x 窗(`stock-intraday-svg.ts` 的 X_START_MIN /
#: X_END_MIN,含端點)。窗外的盤前試撮與 13:31 收盤撮合不進 VP —— 否則卡片 VP 的
#: 總張與說明列的外/內/未分類三數對不起來,而兩個數字都「看起來對」。
_VP_START_MIN = 9 * 60  # 09:00
_VP_END_MIN = 13 * 60 + 30  # 13:30


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
    #: 價位別成交量直方圖(VP):key = `snap_down_milli` 後的檔位,value = [總張, 外, 內]。
    #: **逐 tick 增量維護,不在請求時掃 `ticks`**(change-spec AD-1 amendment R6):
    #: 群組 batch 對最多 50 檔各要一次,請求時全掃最壞是 50 × 20k 的同步迴圈跑在事件
    #: 迴圈上 → WS fanout 被卡住,而畫面上只表現為「圖偶爾頓一下」。
    #: 附帶好處是不受 `ticks` deque 的 20k 截斷影響(前端折的是不截斷的全量)。
    _vp: dict[int, list[int]] = field(default_factory=dict)

    @property
    def last(self) -> StockTick | None:
        return self.ticks[-1] if self.ticks else None

    def reset(self) -> None:
        self.seq = 0
        self.minutes = {}
        self.ticks = deque(maxlen=_TICKS_MAXLEN)
        self.vwap_milli = None
        # 高低是當日衍生狀態,與 vwap 同批清;book/meta 才是盤外要保留的靜態值
        self.high_milli = None
        self.low_milli = None
        self._last_cum = -1
        self._amount_milli = 0
        self._volume = 0
        # VP 與 vwap / 高低同批清:`apply_backfill` 走 reset + 重放,漏了這行回補量會
        # 疊在 live 期間的量上變兩倍,而畫面上只是 VP 條變長,沒有任何錯誤訊號
        self._vp = {}
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
        # cum_outer = cum_inner = 0 回到原點)。meta 是 reset() 刻意保留的靜態值。
        #
        # ⚠ **meta 與回補 tick 不同源**(Phase 5 review P1):`set_main` 訂閱後立刻把回補
        # 入列,而 meta 只有收到 REALTIME 才寫入 —— server 冷啟動後第一次開一檔鎖停股時
        # 回補可能先跑完,補判整段跳過而且**沒有任何重跑點**。所以這裡缺 meta 不能靜默:
        # 出聲讓它可被發現,並由 `stock_engine` 在漲跌停值變化時重新入列回補。
        # survivors(回補期間已 ingest 的 live tick)不套補判是刻意的:它們走的是
        # REALTIME 路徑,`_best_limit_price` 有五檔可退,已經判得出來。
        if self.meta is not None:
            up, lo = self.meta.upper_milli, self.meta.lower_milli
            ticks = [relabel_locked_side(t, up, lo) for t in ticks]
        elif any(t.side == "neutral" for t in ticks):
            logger.warning(
                "apply_backfill: meta 未到,%d 筆回補 tick 的鎖停補判跳過(等 meta 到齊後重跑)",
                sum(1 for t in ticks if t.side == "neutral"),
            )
        old_seq = self.seq
        backfill_max = max((t.cum_vol for t in ticks), default=-1)
        survivors = [t for t in self.ticks if t.cum_vol > backfill_max]
        self.reset()
        # ⚠ 兩個迴圈的去重**不對稱,且是刻意保留的現況**:回補列一律 `_apply`(cum 比對
        # 只推進 `_last_cum`),survivors 則 cum 沒推進就整筆跳過。回補是 TC4 的權威重放
        # (同 cum 的連續成交是真資料,丟了會少張數);survivors 是與回補重疊窗的 live 尾巴,
        # 寧可漏也不可重複計。對齊兩者會改張數/內外盤累積值 → 屬行為改動,記 next-time。
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
        # 全日累積內外盤不另存欄位:Σ(minutes.o/i) 同源且恆等,兩份並存只是多一個
        # 會不同步的地方(M3 移除 wire 欄位後 prod 端已零讀者)
        if tick.side == "outer":
            agg.outer += tick.qty
        elif tick.side == "inner":
            agg.inner += tick.qty
        else:
            agg.unch += tick.qty
        self._fold_vp(tick, minute_key)

    def _fold_vp(self, tick: StockTick, minute_key: int) -> None:
        """把一筆成交折進 VP。**規則逐條對齊前端 `stock-accum.ts::foldVp`**
        (parity 由 `tests/fixtures/vp_parity.json` 兩側各自斷言鎖住):

        - `price_milli <= 0` 剔除:鎖漲跌停時 TC4 在簿的第一檔推市價佇列,價格欄是 `0`。
          `snap_down_milli(0)` 是合法運算,不剔就憑空長出一個 0 元檔位。
        - 分鐘窗 `[09:00, 13:30]`(含端點)= 前端幾何的 x 窗,窗外不計。
        - key 走 `snap_down_milli`(單一定義,不在這裡再寫一次 tick 表)。
        - cell `[總張, 外盤張, 內盤張]`:`neutral`(開盤集合競價無 Bid/Ask 可比)
          只進總張 —— 與 `MinuteAgg.unch` 同語意,故總張 ≠ 外 + 內。
        """
        if tick.price_milli <= 0:
            return
        if not (_VP_START_MIN <= minute_key <= _VP_END_MIN):
            return
        cell = self._vp.setdefault(snap_down_milli(tick.price_milli), [0, 0, 0])
        cell[0] += tick.qty
        if tick.side == "outer":
            cell[1] += tick.qty
        elif tick.side == "inner":
            cell[2] += tick.qty

    def _minutes_payload(self) -> dict[str, dict]:
        """分鐘序列的 wire 形。**鍵名的單一定義** —— 全量 snapshot 與群組 batch 共用。

        兩邊各寫一份的漂移樣態是其中一邊的 `h`/`l` 留在 undefined,而分時圖的極值
        等值反查(`minute.h == accum.high`)對它恆為 false → 當日高低標記靜默消失。
        """
        return {
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
        }

    def _meta_payload(self) -> dict | None:
        """靜態盤別資料的 wire 形(同上,單一定義)。

        缺 meta 回 `None` **不是漏鍵**:前端 `raw.meta ?? null` 對兩者同解,但少一個
        鍵時 response 形的契約測試與型別檢查都看不出來。
        """
        if self.meta is None:
            return None
        return {
            "name": self.meta.name,
            "ref": self.meta.ref_milli,
            "upper": self.meta.upper_milli,
            "lower": self.meta.lower_milli,
            "y_vol": self.meta.y_volume,
        }

    def light_snapshot(self) -> dict:
        """群組 batch 專用的輕量 payload(code review A1)。

        `group_snapshot` 對最多 50 檔、每 60s 各要一次;走全量 `snapshot()` 等於把
        當日數千筆 tick 逐筆組成 dict 之後整份丟掉,而卡片只畫得到這幾鍵。

        `vwap` / `high` / `low` / `vp` 是「卡片圖與單檔頁完全同款」的必要輸入
        (change-spec AD-1):`ticks` 仍然不送(頻寬),而由 minutes 在前端近似出一份
        VWAP / VP,畫面上會與單檔頁的同一檔對不上,且兩個數字都「看起來對」。
        `vp` 是 tick 的**聚合**(O(當日成交過的檔位數)),與 tick 筆數脫鉤。
        """
        return {
            "minutes": self._minutes_payload(),
            "meta": self._meta_payload(),
            # 與 `snapshot()` 同口徑(同一份欄位,不另算):兩邊岔開的樣態是卡片的
            # VWAP 線與單檔頁差一截,而兩條線都畫得出來
            "vwap": self.vwap_milli,
            "high": self.high_milli,
            "low": self.low_milli,
            # JSON 物件的鍵只能是字串;前端 `useGroupSnapshots` 轉回 number key 的 Map
            "vp": {str(price): list(cell) for price, cell in sorted(self._vp.items())},
        }

    def snapshot(self) -> dict:
        """REST 全量(design §4:snapshot 為前端累算基底)。"""
        last = self.last
        return {
            "seq": self.seq,
            "last": {"p": last.price_milli, "t": last.time, "cum_vol": last.cum_vol}
            if last
            else None,
            "vwap": self.vwap_milli,
            # vwap 的**分母**(additive,M4)。前端要做增量 VWAP 就得先還原分子
            # (vwap × 分母),而分母是這裡的 `_volume` = 去重剔試撮後的 Σqty ——
            # **不是** `last.cum_vol`(TC4 的當日累積量)。兩者在有 tick 被去重
            # 或試撮丟棄時就會岔開,拿錯的那個當分母不會報錯,只會讓 VWAP 靜默
            # 偏移到下一次全量 refetch 為止。
            # 欄名帶 `vwap_` 前綴不可省(FC-2):WS `watchlist_quote` 的 `vol` 就是
            # 上面那個 `cum_vol`,叫同一個名字等於把「兩個口徑不可互換」這件事
            # 藏起來,而前端同時握著兩份訊息。
            "vwap_vol": self._volume,
            # 高低與 vwap 同層(top-level)不進 meta:meta 是 TC4 來的靜態盤別資料
            # (名稱 / 參考價 / 漲跌停),而高低是由成交推導的當日狀態。放這裡之後
            # meta 為 None(只跑過回補、未收 REALTIME)時高低照樣有值。
            "high": self.high_milli,
            "low": self.low_milli,
            "minutes": self._minutes_payload(),
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
            "meta": self._meta_payload(),
        }
