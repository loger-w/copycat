"""群益委託/部位記憶體快取(執行緒安全)。COM 事件回呼更新它;REST 讀它。

邏輯照搬 treading-king backend/services/capital_store.py(pydantic → dataclass:
model_copy → dataclasses.replace)。

委託聚合:key = 13 碼委託序號(KeyNo)。同標的不同單絕不合併;
合併的只有同一張單自己的 委託/成交/刪改 事件。
重啟後靠 SKReplyLib_ConnectByID 的當日 backlog 重播重建,無需持久化。

注意:聚合**非冪等** — 同一筆回報事件只能 apply 一次(目前唯一來源
ConnectByID 啟動重播 + 即時推送,天然唯一)。未來若加回報斷線重連,
重播前必須先 clear(),否則成交量會重複累計。
"""

from __future__ import annotations

import dataclasses
import logging
import threading
from dataclasses import dataclass

from copycat.capital.balance import ProfitRow
from copycat.capital.models import Market, OrderRecord, Position, PositionKind
from copycat.capital.reply import ReplyRecord

logger = logging.getLogger(__name__)

_SEC_LOT_MARKETS = {"TS", "TA", "TP"}  # 整股:股 → 張(÷1000)
_FUT_MARKETS = {"TF", "TO", "OF", "OO"}  # 口

# 狀態只進不退(防 backlog 重播亂序降級)
_RANK = {
    "預約中": 1,
    "委託成功": 1,
    "改價": 1,
    "改量": 1,
    "改價改量": 1,
    "部分成交": 2,
    "全部成交": 3,
    "已刪單": 3,
    "失敗": 3,
    "逾時": 3,
    "退單": 3,
}

# 刪/改事件(C/U/P/B)帶 OrderErr 時,失敗的是「該次動作」,原委託仍掛在市場上;
# 標整張單終態會讓活單從面板消失(刪/改鈕跟著沒了)。N/D/S 帶 err 才是單本身的問題。
_ACTION_TYPES = {"C", "U", "P", "B"}


@dataclass
class _Agg:
    seq_no: str
    stock_no: str | None = None
    market: str | None = None
    buy_sell: str | None = None
    flag_label: str | None = None
    book_no: str | None = None
    status_raw: str | None = None
    status_label: str | None = None
    price: float | None = None
    order_qty: int = 0  # 原始單位(股/口)
    filled_qty: int = 0
    fill_value: float = 0.0  # Σ(成交價×量),算均價用
    date: str | None = None  # 委託建立日 YYYYMMDD
    time: str | None = None
    pre_order: bool = False
    error_msg: str | None = None
    raw: str = ""


class CapitalStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._orders: dict[str, _Agg] = {}
        self._order_seq: list[str] = []  # 到達順序
        # 本 app 送出的價格別:seq → (price_type, 候選日 YYYYMMDD 們)。與 _Agg 分開放,
        # 因為它不是回報事件的產物 —— 送單結果與 N 回報的到達序不保證(COM 執行緒 vs
        # async),掛在 _Agg 上會在「結果先回」時無處可放。`clear()` 不清(見該方法註)。
        # 候選日 = 本機日曆日(+ 夜盤時的所屬交易日),見 `note_price_type`(N075)。
        self._price_types: dict[str, tuple[str, tuple[str, ...]]] = {}
        # 鍵 = (stock_no, kind):同檔資+集保並存各佔一列,兩種類都平倉鍵得到
        self._positions: dict[tuple[str, str], Position] = {}

    def _set_status(self, a: _Agg, label: str) -> None:
        if _RANK.get(label, 0) >= _RANK.get(a.status_label or "", 0):
            a.status_label = label

    def _refresh_fill_status(self, a: _Agg) -> None:
        """成交滿不滿由量推導;量變動(N 補量/D 成交/U/B 改量)就重算。
        order_qty 未知(=0,N 還沒到)時不得斷言「全部成交」— 終態進 _RANK 就退不回來,
        部分成交的活單會被鎖死在面板上不可刪改。"""
        if a.filled_qty <= 0:
            return
        if a.order_qty > 0 and a.filled_qty >= a.order_qty:
            self._set_status(a, "全部成交")
        else:
            self._set_status(a, "部分成交")

    def apply_reply(self, rec: ReplyRecord) -> None:
        if not rec.seq_no:
            return
        with self._lock:
            a = self._orders.get(rec.seq_no)
            if a is None:
                a = _Agg(seq_no=rec.seq_no)
                self._orders[rec.seq_no] = a
                self._order_seq.append(rec.seq_no)

            # 共通欄位:有值就更新
            for f in ("stock_no", "market", "buy_sell", "flag_label", "book_no", "date"):
                v = getattr(rec, f)
                if v:
                    setattr(a, f, v)
            if rec.pre_order:
                a.pre_order = True
            if rec.time:
                a.time = rec.time
            a.status_raw = rec.status_raw
            a.raw = rec.raw

            t = rec.status_raw
            if rec.order_err in ("Y", "T"):
                a.error_msg = rec.error_msg or a.error_msg
                if t not in _ACTION_TYPES:
                    self._set_status(a, "失敗" if rec.order_err == "Y" else "逾時")
            elif t == "N":
                a.order_qty = rec.qty or a.order_qty
                if rec.price is not None:
                    a.price = rec.price
                self._set_status(a, "預約中" if rec.pre_order else "委託成功")
                self._refresh_fill_status(a)  # 亂序:D 先到時,N 補上量後重算滿不滿
            elif t == "D":
                # 成交無價(解析失敗)整筆不採計:量與均價分子綁定,
                # 少算成交 → remaining_shares 高估 → 改價金額閘更嚴,是安全方向。
                if rec.price is not None:
                    a.filled_qty += rec.qty
                    a.fill_value += rec.price * rec.qty
                self._refresh_fill_status(a)
            elif t == "C":
                # C 的 qty=原委託剩量,order/filled 不動
                self._set_status(a, "已刪單")
            elif t == "U":
                a.order_qty = (
                    rec.after_qty if rec.after_qty is not None else max(a.order_qty - rec.qty, 0)
                )
                self._set_status(a, "改量")
                self._refresh_fill_status(a)  # 減到 ≤ 已成交量 = 等同全部成交
            elif t == "P":
                if rec.price is not None:
                    a.price = rec.price
                self._set_status(a, "改價")
            elif t == "B":
                if rec.price is not None:
                    a.price = rec.price
                if rec.after_qty is not None:
                    a.order_qty = rec.after_qty
                self._set_status(a, "改價改量")
                self._refresh_fill_status(a)
            elif t == "S":
                self._set_status(a, "退單")

    def note_price_type(
        self, seq_no: str, price_type: str, date: str, *, trade_date: str | None = None
    ) -> None:
        """記下本 app 送出的價格別(送單成功且拿到 seq 時呼叫)。
        `date` = 送出當日 YYYYMMDD:server 長跑跨日、券商 seq 若重用,
        沒有日期界就會把今日的限價單標成昨日那張的「市價」(review R7)。

        `trade_date`(N075)= 送出時刻**所屬的交易日**(`client._trade_ymd`)。夜盤 23:50
        送出的單,本機日曆日是今天、交易日是明天,而群益回報的 `_Agg.date` 到底是哪一種
        語意**未實證**(review r1 IMPL-5)—— 所以兩個都記,任一相符即帶出:

        - 這是舊行為(只比 `date`)的**超集**,不會因為改動而讓現在還標得出來的單失標;
        - 新增的候選是**唯一**一個有語意根據的日子(該筆委託所屬的交易日),不是
          「±1 天」那種任意放寬 —— 往回多接受一天正是 seq 重用誤標的方向,
          而 fail-safe 方向(只會缺標籤、不會誤標)不可變鬆。

        同鎖內順手 prune 掉**候選集合與本次不相交**的舊項(review r1 IMPL-7 + N075):
        它們早已因日期不符而不會帶出,留著只是讓 dict 隨 server 長跑單調成長。
        判準從「日期不等」改成「集合不相交」是必要的 —— 否則夜盤那筆(0824/0825)會被
        隔天日盤第一張單(0825/0825)順手清掉,標籤在同一個交易日內就沒了。"""
        days = (date,) if trade_date is None or trade_date == date else (date, trade_date)
        with self._lock:
            stale = [
                s for s, (_pt, d) in self._price_types.items() if not set(d) & set(days)
            ]
            for s in stale:
                del self._price_types[s]
            self._price_types[seq_no] = (price_type, days)

    def forget_price_type(self, seq_no: str) -> None:
        """作廢某筆的價格別記憶(改價成功時呼叫)。
        市價單被改成限價後標籤還在 = 唯一一條會**誤標**的路徑(其餘失效方向都只是少標)。"""
        with self._lock:
            self._price_types.pop(seq_no, None)

    def _price_type_of(self, a: _Agg) -> str | None:
        """委託日落在記錄的候選日(本機日 / 交易日)之一才帶出;委託日缺(None)
        無從比對 → 不帶,不猜。回報的日界語意(夜盤 / 預約單)未實證 —
        見 `note_price_type`。"""
        noted = self._price_types.get(a.seq_no)
        if noted is None or a.date is None:
            return None
        return noted[0] if a.date in noted[1] else None

    def _to_record(self, a: _Agg) -> OrderRecord:
        if a.market in _SEC_LOT_MARKETS or a.market is None:
            div, unit = 1000, "張"
        elif a.market in _FUT_MARKETS:
            div, unit = 1, "口"
        else:  # TL/TC 零股
            div, unit = 1, "股"
        avg = (a.fill_value / a.filled_qty) if a.filled_qty > 0 else None
        return OrderRecord(
            seq_no=a.seq_no,
            stock_no=a.stock_no,
            market=a.market,
            buy_sell=a.buy_sell,
            flag_label=a.flag_label,
            book_no=a.book_no,
            status_raw=a.status_raw,
            status_label=a.status_label,
            price=a.price,
            avg_fill_price=round(avg, 4) if avg is not None else None,
            order_qty=a.order_qty // div,
            filled_qty=a.filled_qty // div,
            unit=unit,
            date=a.date,
            time=a.time,
            pre_order=a.pre_order,
            error_msg=a.error_msg,
            actionable=_RANK.get(a.status_label or "", 0) in (1, 2),
            price_type=self._price_type_of(a),
            raw=a.raw,
        )

    def orders(self) -> list[OrderRecord]:
        """日期+時間倒序(昨日預約單不浮頂、有新回報的單浮頂);同秒以到達序新者在前。"""
        with self._lock:
            arrival = {s: i for i, s in enumerate(self._order_seq)}
            aggs = sorted(
                self._orders.values(),
                key=lambda a: (a.date or "", a.time or "", arrival[a.seq_no]),
                reverse=True,
            )
            return [self._to_record(a) for a in aggs]

    def remaining_shares(self, seq_no: str) -> int | None:
        """改價金額閘用:未成交量(原始單位,股/口)。查無此單回 None。
        終態單(已刪/全成/失敗/逾時/退單)回 0:死單沒有未成交量可改,
        否則已刪單的 order-filled 差額會讓改價閘對死單放行、留給券商兜底。"""
        with self._lock:
            a = self._orders.get(seq_no)
            if a is None:
                return None
            if _RANK.get(a.status_label or "", 0) >= 3:
                return 0
            return max(a.order_qty - a.filled_qty, 0)

    def market_of(self, seq_no: str) -> str | None:
        """寫入鏈市場閘用:該單市場別。查無此單或缺值回 None(寬鬆放行,與顯示端同慣例)。"""
        with self._lock:
            a = self._orders.get(seq_no)
            return a.market if a else None

    def clear(self) -> None:
        """清空委託聚合(部位不動)。回報重連重播前必須呼叫,否則成交量重複累計。

        `_price_types` **不清**:它是送單意圖不是回報事件,重播不會重建它 ——
        清掉等於本 app 送出的市價單在重連後全體失標。"""
        with self._lock:
            self._orders.clear()
            self._order_seq.clear()

    def set_positions(self, positions: list[Position]) -> None:
        """全量替換。同 (股號, 種類) 重複列 = 後到者勝並留 warning:
        複合鍵下重複鍵是上游異常訊號(對照 merge_fut_positions 的淨額合併 warning),
        靜默 last-wins 會讓丟掉的張數無跡可尋 — 但不在此做去重補償,寧可讓訊號浮出來。"""
        with self._lock:
            old = self._positions
            new: dict[tuple[str, str], Position] = {}
            for p in positions:
                key = (p.stock_no, p.kind)
                prev = old.get(key)
                # 損益查詢回來前沿用既有均價/損益基底(鍵已含 kind,天然只沿用同種類 —
                # 資/券成本基礎不同,異種類是另一列不是同一列的續命)
                if p.avg_price is None and prev is not None:
                    p.avg_price = prev.avg_price
                    p.pnl_base = prev.pnl_base
                    p.pnl_base_price = prev.pnl_base_price
                    p.pnl_cost = prev.pnl_cost
                dup = new.get(key)
                if dup is not None:
                    logger.warning(
                        "同 (股號, 種類) 重複列 %s/%s: %+d + %+d — 後到者勝(上游回報異常)",
                        p.stock_no,
                        p.kind,
                        dup.qty,
                        p.qty,
                    )
                new[key] = p
            self._positions = new

    def apply_profit_rows(self, rows: list[ProfitRow]) -> None:
        """損益試算回填(均價+含費稅息損益基底);查無 (股號, 種類) 忽略
        (部位清單以即時庫存為權威);kind=None(未知標籤)整列略過 —
        寧缺均價,不可把不明成本基礎套到任一種類上。
        用 dataclasses.replace 發布新物件而非就地變更:positions() 回傳的是物件參考,
        route 在鎖外 asdict,就地改會撕裂讀(新 pnl 配舊基準價)。"""
        with self._lock:
            for r in rows:
                if r.kind is None:
                    continue
                key = (r.stock_no, r.kind)
                p = self._positions.get(key)
                if p is not None:
                    self._positions[key] = dataclasses.replace(
                        p,
                        avg_price=r.avg_price,
                        pnl_base=r.pnl,
                        pnl_base_price=r.price,
                        pnl_cost=r.cost,
                    )

    def positions(self) -> list[Position]:
        with self._lock:
            return list(self._positions.values())

    def position_for(
        self, stock_no: str, kind: PositionKind | None = None, *, market: Market | None = None
    ) -> Position | None:
        """平倉查找。kind 有值 = 精確鍵;kind=None = 同股號恰一列才回傳,
        多列(同檔資+集保並存)回 None — 平倉種類猜錯會送錯單種,寧可讓 caller 阻擋。

        market 收斂唯一匹配的掃描母體:證券股號與期交所契約碼是兩套獨立代碼,
        「不會撞字串」是隱形不變量不是保證(個股期契約碼隨期交所異動);不帶 market
        時一個巧合的同名列就會讓另一邊誤判成歧義 → fut 平倉靜默「無部位可平」。"""
        with self._lock:
            if kind is not None:
                p = self._positions.get((stock_no, kind))
                return p if p is not None and (market is None or p.market == market) else None
            hits = [
                p
                for (no, _kind), p in self._positions.items()
                if no == stock_no and (market is None or p.market == market)
            ]
            return hits[0] if len(hits) == 1 else None
