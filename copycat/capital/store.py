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
import time
from collections.abc import Callable
from dataclasses import dataclass

from copycat.capital.mapping import contract_from_fill, is_option_contract
from copycat.capital.models import AvgSource, Market, OrderRecord, Position, PositionKind, TradeKind
from copycat.capital.reply import ReplyRecord

logger = logging.getLogger(__name__)

_SEC_LOT_MARKETS = {"TS", "TA", "TP"}  # 整股:股 → 張(÷1000)
_FUT_MARKETS = {"TF", "TO", "OF", "OO"}  # 口

# 成交樂觀套用(F5)的證券種類對映:回報 idx6 資券別 → 部位種類。**只列確定的**:「無券」
# (無券當沖賣)的部位狀態與回補單種待首筆實錄校準(balance.py 負股數同一條),不在表內
# = 不套(回查鏈仍會補),寧缺勿錯。零股不在此表 —— 零股市場(TL/TC)整個不套。
_FILL_KIND: dict[str, PositionKind] = {
    "現股": "cash",
    "拍賣現股": "cash",
    "融資": "margin",
    "代資": "margin",
    "融券": "short",
    "代券": "short",
}

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
    applied_qty: int = 0  # 已樂觀套進部位的成交量(張 / 口;F5 部分成交只套增量)
    applied_shares: int = 0  # 已被套用消化的成交量(股 / 口;證券 = 已套張數 × 1000),算增量均價用
    applied_value: float = 0.0  # 已被套用消化的價金(以增量均價計),殘量(不足 1 張)留給下一張
    date: str | None = None  # 回報**最新事件日** YYYYMMDD(apply_reply 有值就覆寫;不是委託建立日)
    fill_date: str | None = None  # 最後一筆成交**到達**的本機日 YYYYMMDD(today_qty 只算今天的)
    time: str | None = None
    pre_order: bool = False
    error_msg: str | None = None
    raw: str = ""


def _local_yyyymmdd() -> str:
    return time.strftime("%Y%m%d")


class CapitalStore:
    def __init__(self, *, today: Callable[[], str] | None = None) -> None:
        # 「今天」的來源可注入(測試跨日);prod = 本機日曆日。證券無夜盤,00:00 切日即交易日切日。
        self._today = today or _local_yyyymmdd
        self._lock = threading.Lock()
        self._orders: dict[str, _Agg] = {}
        self._order_seq: list[str] = []  # 到達順序
        # 本 app 送出的價格別:seq → (price_type, 候選日 YYYYMMDD 們)。與 _Agg 分開放,
        # 因為它不是回報事件的產物 —— 送單結果與 N 回報的到達序不保證(COM 執行緒 vs
        # async),掛在 _Agg 上會在「結果先回」時無處可放。`clear()` 不清(見該方法註)。
        # 候選日 = 本機日曆日(+ 夜盤時的所屬交易日),見 `note_price_type`(N075)。
        #: seq → (價格別, 候選日, 綁定的 stock_no, 綁定的 B/S);後兩者 None = 該路徑沒有可綁的值
        self._price_types: dict[str, tuple[str, tuple[str, ...], str | None, str | None]] = {}
        # 鍵 = (stock_no, kind):同檔資+集保並存各佔一列,兩種類都平倉鍵得到
        self._positions: dict[tuple[str, str], Position] = {}
        # 委託序號 → 回報 idx33 YYYYMM(期貨樂觀套用組契約碼用;F5)
        self._contract_ym: dict[str, str] = {}
        # 樂觀套用只在「券商快照已落地一次」之後才開(PR #111 review F-02):開機時 _positions
        # 是空的,ConnectByID 的當日 backlog 重播若照套,昨日庫存 10 張今日賣 3 張的檔會變成
        # qty=-3 的幻影空單、可按平倉。每次 set_positions 落地後把所有委託標成「已套用到目前」,
        # 之後只套快照之後的成交;clear()(重連重播前)把旗標關回去。
        self._positions_seeded = False

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

    def apply_reply(self, rec: ReplyRecord) -> bool:
        """回報事件 → 委託聚合;成交(D)另樂觀套進部位。回傳「部位有沒有變」
        (caller 據此推 `capital_position`;其他事件恆 False)。"""
        if not rec.seq_no:
            return False
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
            if rec.contract_ym is not None:
                self._contract_ym[rec.seq_no] = rec.contract_ym
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
                    a.fill_date = self._today()
                self._refresh_fill_status(a)
                # 快照未落地(開機 / 重連重播中)只累計不套 —— 見 __init__ 的 _positions_seeded 註解
                return self._apply_fill_locked(a) if self._positions_seeded else False
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
            return False

    def _today_net_lots_locked(self, stock_no: str, kind: TradeKind) -> int:
        """今天同 (股號, 種類) 的成交淨張數(buy − sell,整張)。「今天」看成交**到達日**
        `fill_date`,不看 idx23(它是最新事件日不是成交日:昨日建立今日成交 / 刪單的單 `date`
        都已是今日,分不出哪些成交量是今天進來的),也不能假設聚合
        只有當日 —— prod 8721 跨日長跑、`_orders` 沒有 caller 會清(review 2026-08-26 P1),
        隔夜庫存若被算成今天進來的,前端稅減半 = 少收稅、打平線偏低,零錯誤訊號。"""
        today = self._today()
        net = 0
        for a in self._orders.values():
            if a.stock_no != stock_no or a.market not in _SEC_LOT_MARKETS or a.filled_qty <= 0:
                continue
            if a.fill_date != today:
                continue
            if _FILL_KIND.get(a.flag_label or "") != kind:
                continue
            lots = a.filled_qty // 1000
            net += lots if a.buy_sell == "B" else -lots
        return net

    def _with_today_qty_locked(self, p: Position) -> Position:
        """today_qty 重算:多方取淨買進、空方取淨賣出,clamp 到 [0, |qty|];fut 恆 0。"""
        if p.market != "sec" or p.qty == 0:
            today = 0
        else:
            net = self._today_net_lots_locked(p.stock_no, p.kind)
            today = max(0, min(abs(p.qty), net if p.qty > 0 else -net))
        return p if p.today_qty == today else dataclasses.replace(p, today_qty=today)

    def _apply_fill_locked(self, a: _Agg) -> bool:
        """成交樂觀套用(F5):成交回報帶價 / 量 / 方向 / 種類,不必等券商三段回查鏈
        (0.5 s debounce + 庫存 → 損益 → 期貨部位串行)才讓部位出現。回查鏈照跑、落地時
        `set_positions` 全量覆蓋 —— 真相仍是券商,這裡只是先到。

        規則(寧缺勿錯,任一環節不確定就不套、回傳 False):
        - 只套「這張單」尚未套過的增量(`applied_qty`):部分成交 500 + 500 股 → 湊滿 1 張才套 1。
        - 證券:整股市場 + 種類對得到 `_FILL_KIND`;張數 = 累計成交股 // 1000。
        - 期貨:純期貨(選擇權不套);契約碼由回報組(`contract_from_fill`)。
        - 買 +、賣 −(融券空單本來就是負張,與 `parse_balance_line` 同號)。
        - 均價:新倉 = 這張單成交均價;同向加碼且舊均價已知 = 加權;減碼(同號)不動;舊均價未知留 None;
          反向翻倉(換號,不論幅度)= 這張單均價。損益基底(`pnl_*`)一律清 None —— 舊快照對新張數是假的。
        - avg_source:新倉 / 翻倉 = "fill"(純成交價);加碼沿用舊來源(broker 含費均價與純價加權,
          誤差只在新增那幾張的買費、鏈落地即消);減碼沿用;均價 None 時 None。today_qty 每次重算。
        - 只在 `_positions_seeded`(券商快照落地過)之後套;重播 / 開機前的成交只累計。
        - 歸零 → 移除該列。
        """
        if a.buy_sell not in ("B", "S") or a.filled_qty <= 0 or not a.stock_no:
            return False
        market: Market
        kind: PositionKind
        if a.market in _SEC_LOT_MARKETS:
            k = _FILL_KIND.get(a.flag_label or "")
            if k is None:
                logger.info("成交種類 %r 不在樂觀套用表,等回查鏈: %s", a.flag_label, a.stock_no)
                return False
            market, kind, key_no = "sec", k, a.stock_no
            total = a.filled_qty // 1000
        elif a.market in _FUT_MARKETS:
            contract = contract_from_fill(a.stock_no, self._contract_ym.get(a.seq_no))
            if contract is None or is_option_contract(contract):
                return False
            market, kind, key_no = "fut", "cash", contract
            total = a.filled_qty
        else:
            return False
        delta = total - a.applied_qty
        if delta <= 0:
            return False
        # 增量均價 = 尚未被消化的成交量的均價(不是整張單的累計均價 —— 第二次套用時把第一批
        # 的價格再算進去,加碼均價會被拉回舊價)。**只消化整張的量**(review Spec c):1500 股
        # 套 1 張時只吃 1000 股的價金,殘 500 股留給下一張與後續成交一起算 —— 全吃掉的話那 500
        # 股的價金憑空消失,下一張均價偏移。unit = 一張 / 一口對應的原始量。
        unit = 1000 if market == "sec" else 1
        fill_avg = (a.fill_value - a.applied_value) / (a.filled_qty - a.applied_shares)
        a.applied_qty = total
        a.applied_shares += delta * unit
        a.applied_value += fill_avg * delta * unit
        signed = delta if a.buy_sell == "B" else -delta
        key = (key_no, kind)
        prev = self._positions.get(key)
        if prev is None:
            self._positions[key] = self._with_today_qty_locked(
                Position(
                    market=market,
                    stock_no=key_no,
                    qty=signed,
                    avg_price=fill_avg,
                    kind=kind,
                    avg_source="fill",
                )
            )
            return True
        new_qty = prev.qty + signed
        if new_qty == 0:
            del self._positions[key]
            return True
        source: AvgSource | None = prev.avg_source
        if prev.qty == 0 or (prev.qty > 0) == (signed > 0):
            avg = (
                (prev.avg_price * abs(prev.qty) + fill_avg * abs(signed)) / abs(new_qty)
                if prev.avg_price is not None and prev.avg_price > 0
                else None
            )
        elif (new_qty > 0) == (prev.qty > 0):
            # 同號 = 減碼(幅度不重要),均價不動
            avg = prev.avg_price
        else:
            # 換號 = 反手翻倉:+3 口賣 5 口 → -2 口,均價是這張單的(review F-03:舊寫法用幅度判,
            # |new| < |prev| 的翻倉會沿用舊方向均價)
            avg = fill_avg
            source = "fill"
        if avg is None:
            source = None
        self._positions[key] = self._with_today_qty_locked(
            dataclasses.replace(
                prev,
                qty=new_qty,
                avg_price=avg,
                avg_source=source,
                pnl_base=None,
                pnl_base_price=None,
                pnl_cost=None,
            )
        )
        return True

    def note_price_type(
        self,
        seq_no: str,
        price_type: str,
        date: str,
        *,
        trade_date: str | None = None,
        stock_no: str | None = None,
        buy_sell: str | None = None,
    ) -> None:
        """記下本 app 送出的價格別(送單成功且拿到 seq 時呼叫)。
        `date` = 送出當日 YYYYMMDD:server 長跑跨日、券商 seq 若重用,
        沒有日期界就會把今日的限價單標成昨日那張的「市價」(review R7)。

        `trade_date`(N075)= 送出時刻**所屬的交易日**(`client._trade_ymd`)。夜盤 23:50
        送出的單,本機日曆日是今天、交易日是明天,而群益回報的 `_Agg.date` 到底是哪一種
        日界語意**未實證**(review r1 IMPL-5)—— 所以兩個都記,任一相符即帶出:

        - 這是舊行為(只比 `date`)的**超集**,不會因為改動而讓現在還標得出來的單失標;
        - 新增的候選是**唯一**一個有語意根據的日子(該筆委託所屬的交易日),不是
          「±1 天」那種任意放寬 —— 往回多接受一天正是 seq 重用誤標的方向,
          而 fail-safe 方向(只會缺標籤、不會誤標)不可變鬆。

        同鎖內順手 prune 掉**候選集合與本次不相交**的舊項(review r1 IMPL-7 + N075):
        它們早已因日期不符而不會帶出,留著只是讓 dict 隨 server 長跑單調成長。
        判準從「日期不等」改成「集合不相交」是必要的 —— 否則夜盤那筆(0824/0825)會被
        隔天日盤第一張單(0825/0825)順手清掉,標籤在同一個交易日內就沒了。

        另一個前提要說清楚:`_Agg.date` 是**最新事件日**,不是委託建立日(`apply_reply` 有值就
        覆寫;tc4-market-facts 群益節)。日盤單只記 (0824,),隔日再有事件(成交 / 刪單)把 `date`
        推成 0825 → 出候選集 → 標籤消失 = 只缺標籤,fail-safe 方向仍成立;夜盤單 (0824, 0825)
        被隔日事件推日期仍在集合內,標籤照帶。語意錯位沒有把誤標窗拉寬(review §2.4 Standards 1)。

        `stock_no` / `buy_sell`(review R6 ST1)= 這張單的標的與方向("B"/"S"),帶出時
        回報的同名欄位要**等值**才算同一張單。多開的那個交易日候選正是 seq 重用的誤標窗
        (群益 seq 是日曆日重置還是交易日重置**未實證**):夜盤 0824 23:50 的市價單記
        (0824, 0825),隔日 0825 日盤若他處(群益 APP)下了同 seq 的限價單,只比日期會把它
        標成市價。綁標的 + 方向後,同 seq 撞到**不同標的或方向**的單就不帶出;**同檔同方向**撞同 seq
        的窗仍在,所以現況是「大幅縮窗、非零誤標」,不是「只缺標籤、不誤標」;期貨路徑
        (`client.submit_future_order` 只綁方向,stock_no=None)的窗更寬 —— 同方向撞同 seq 即誤標。
        08-25 review N075 的候選處置 = 送單時刻 ± 窗或 seq 單調性檢查;**08-28 user 拍板:程式不封洞**
        —— 窗只在夜盤送市價單時存在(日盤單只有一個候選日),先由夜盤遠價市價單實驗(user 親做)
        定案回報日界 + 群益 seq 重置口徑:兩者同口徑 → 改成只記單一候選日就關窗;不同口徑
        (日界走交易日、seq 走日曆日)才需要送單時刻 ± 窗那類補丁。現況在
        `tests/capital/test_store.py::test_price_type_binding_rejects_same_seq_different_order` s3 案
        釘住 —— 同一組輸入,store 分不出「同一張」與「另一張」,那就是窗。
        `None` = 該路徑沒有可綁的值(期貨單的 `tc4_symbol` 與回報契約碼不同域 → 只綁方向;
        平倉沒有方向 → 只綁 key),不參與比對。"""
        days = (date,) if trade_date is None or trade_date == date else (date, trade_date)
        with self._lock:
            stale = [
                s for s, (_pt, d, _sn, _bs) in self._price_types.items() if not set(d) & set(days)
            ]
            for s in stale:
                del self._price_types[s]
            self._price_types[seq_no] = (price_type, days, stock_no, buy_sell)

    def forget_price_type(self, seq_no: str) -> None:
        """作廢某筆的價格別記憶(改價成功時呼叫)。
        市價單被改成限價後標籤還在 = 唯一一條會**誤標**的路徑(其餘失效方向都只是少標)。"""
        with self._lock:
            self._price_types.pop(seq_no, None)

    def _price_type_of(self, a: _Agg) -> str | None:
        """回報 `date`(最新事件日)落在記錄的候選日(本機日 / 交易日)之一才帶出;
        日期缺(None)無從比對 → 不帶,不猜。回報的日界語意(夜盤 / 預約單)未實證 —
        見 `note_price_type`。"""
        noted = self._price_types.get(a.seq_no)
        if noted is None or a.date is None:
            return None
        price_type, days, stock_no, buy_sell = noted
        if a.date not in days:
            return None
        # 綁定欄位有值就必須等值(review R6 ST1):同 seq 撞到不同標的 / 方向的單 → 不帶出
        if stock_no is not None and a.stock_no is not None and a.stock_no != stock_no:
            return None
        if buy_sell is not None and a.buy_sell is not None and a.buy_sell != buy_sell:
            return None
        return price_type

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
            self._contract_ym.clear()
            # 重播會把當日成交再送一輪:關掉樂觀套用直到下一次快照落地(review F-02)
            self._positions_seeded = False

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
                    p.avg_source = prev.avg_source
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
                new[key] = self._with_today_qty_locked(p)
            self._positions = new
            # 快照涵蓋到此刻的所有成交:把每張單標成「已套用到目前」,之後只套快照之後的增量
            # (同一筆成交既在快照裡又再樂觀套一次 = 重複計)。
            for a in self._orders.values():
                unit = 1000 if a.market in _SEC_LOT_MARKETS else 1
                a.applied_qty = a.filled_qty // unit
                a.applied_shares = a.applied_qty * unit
                a.applied_value = a.fill_value * (a.applied_shares / a.filled_qty) if a.filled_qty else 0.0
            self._positions_seeded = True

    def positions(self) -> list[Position]:
        """回傳的是物件**參考**(route 在鎖外 asdict):已發布的 Position 不可就地變更,
        要改就 dataclasses.replace 發布新物件(`_apply_fill_locked` 的寫法),否則撕裂讀
        (新 pnl 配舊基準價)。損益回填(client._on_profit_complete)改的是尚未發布的
        pending 列,不在此限。`set_positions` 的 carry-over 也是就地寫,寫的是尚未發布的新一輪列;
        唯一例外是 `_finalize_positions(self._stale_fut_positions())` 那條路傳回**已發布**的 fut 物件,
        此時 `p is prev`、五行皆自我賦值才沒撕裂 —— 改那五行(補別的欄 / 換來源)前先確認這條仍成立
        (pr-119 F-06)。"""
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
