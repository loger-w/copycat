"""簿重播引擎(spec #265 / ticket #267):tick 存檔的成交列 + 簿列照訊息序號重播成每則的五檔。

CONTEXT.md「簿重播」:與分點指紋的引擎回放(`copycat.replay`)是兩件事,不共用程式碼。
零 IO —— 讀檔(`ticks.load_day`)與寫檔在 CLI `book-replay`。

**一則** = 一列 tick 存檔(成交列或簿列),依 `msg_seq` 排;每列自帶完整五檔(成交列是成交後簿),
所以第 i 則的簿就是那一列的 20 格,不需要跨列累積。

**排序** 只看 `msg_seq`(server 收到的全域順序,因果不會反)。

**時間軸(拖曳 / 十字線 / 對齊委託)= server 收到時刻** `Frame.recv_ms`(交易日台北零點起毫秒;本機鐘被
校時往回撥時沿用前一則,不倒退)。2026-09-16 實測:達錢**即時**個股成交時刻只到整秒(37.5 萬筆次秒
全 0),一般盤中成交的收到時刻比它晚 81–1,279 ms、100–1,099 ms 各 100 ms 桶近乎均勻 = 整秒截斷加約
0.1 秒延遲 —— 收到時刻本身很穩(前提是本機鐘準;#236 時鐘偏差 WARNING 出現時軸整段跟著偏,與同一把
本機鐘的群益審計時刻仍對得齊);
反過來拿整秒的達錢時刻當軸,2426「11:02:43」一格底下就有 51 則(user 2026-09-16 拍板改軸)。

**文字標籤 = 交易所的尺**:最近一個**時鐘點**的達錢時刻,簿列讀作「該時刻之後第 N 則」(`Frame.after`)。
時鐘點 = 成交列,且 (a) 不早於目前時鐘(不倒退)、(b) 達錢時刻不晚於收到時刻超過
`CLOCK_FUTURE_TOLERANCE_MS`(收不到未來)。2026-09-16 實錄三種時刻:13:30:00.000 收盤撮合晚到
1.4–39.8 秒(真時刻,當時鐘點);7772 緩撮成交晚到 118.6 秒(真時刻,當時鐘點);1815 開機 07:31 收到前一日
14:30 的盤後成交(未來,不當時鐘點)。不當時鐘點的成交仍是一則,`after` 照數,計入 `BookReplay.anomalous_trades`。

**變動分解**(`Frame.changes`,#269):第 i 則相對同一檔第 i−1 則,以**價格**為鍵(不是檔位),只比兩則都
**看得到**的價位。看得到 = 買方價 ≥ 第五檔限價、賣方價 ≤ 第五檔限價(比買一高的價位本來就沒有買單、比賣一低的
沒有賣單);某側不滿五層 = 整側看得到;市價佇列(價 0)恆看得到。一則的項目買方在前、賣方在後,同側市價佇列在前、
其後由最優價往外;每個價位一則至多一項:
- `LevelChange`:兩則都看得到。量增加 = 掛入;量減少先扣該價位還沒扣到的成交(`traded`),剩下的算撤單。
  「還沒扣到」= 成交則附的五檔常常還沒反映這筆成交(掃單時前幾筆成交則的五檔是舊的),所以往後
  `TRADE_CARRY_MESSAGES` 則且 `TRADE_CARRY_MS` 毫秒內的同價位減量都先扣它;市價佇列的減少不看成交價
  (鎖停時成交價是漲跌停價,吃掉的是市價那一排)
- `LeftView`:追蹤中的價位被擠到第五檔之外(離開視野),離開前最後看到的量 > 0 才列
- `Reappeared`:被擠出去的價位回到看得到的範圍(重新可見),給離開時量、現在量、離開期間該價位成交量、淨掛
  (= 現在 − 離開時 + 期間成交)、離開時長;**不算掛單**,看不到的那段無法分辨一次掛進或分次堆積。三個量都是 0 不列
- `EnteredView`:從沒追蹤過的價位帶量進到看得到的範圍(首次進入五檔),不算掛單
追蹤中 = 看得到時列出過的限價,之後在看得到的範圍內歸 0 仍追蹤(離開時量就是 0)。
價位從賣方換到買方(價格穿過它)一直看得到,是賣方減量 + 買方增量,不是離開視野(user 2026-09-17 拍板;
grilling 階段把換邊當離開,算出 2426「賣 92.0 淨掛 +154」,實際賣方只新掛 16 張)。

**吃檔**(`Frame.eaten`,成交明細的「吃 賣1 −12」,#269):成交則這筆成交被哪一格的減量扣到(扣法同上),
檔位 = 成交前那一則五檔該側的第幾檔(只數限價,最優 = 1;那一則沒列出這個價位就看扣到那一則的前一則),
扣到市價佇列 = 0。到期(`TRADE_CARRY_MESSAGES` / `TRADE_CARRY_MS`)都沒扣到的量:成交價在成交前那一則該側
第五檔之外(外盤看賣方、內盤看買方)= 五檔外(`level` None);其餘看不出吃了哪一檔(開收盤集合競價、同一則
又掛進來蓋過減量)不列。同一格分幾則扣到合成一項。

**外掛檔 v2**(`encode` → `plugin_js`;每檔每日一檔,回看頁 `<script src>` 懶載入;v1 → v2 = #269 加 `chg` 與
`eat`):
全文一行 `window.__bk("<代號>|<日期>","<base64(gzip(JSON))>");`,JSON 物件鍵:

- `v`:2;`code`、`date`(YYYY-MM-DD);`n`:則數;`fields`:五檔 20 格欄序(= `BOOK_LEVEL_FIELDS`)
- `seq`:訊息序號,首項絕對值、其後逐則差值(每一項都 > 0)
- `kind`:長 n 的字串,`t` 成交 / `b` 簿
- `recv`:長 n,收到時刻(交易日台北零點起毫秒),首項絕對值、其後逐則差值(恆 ≥ 0)
- `anomalous`:達錢時刻異常、不當時鐘點的成交則號(遞增;個數 = `BookReplay.anomalous_trades`,2026-09-16
  全 80 檔共 1 個)。**其餘成交則都是時鐘點**,時刻讀它在 `trade` 的第一格(必有值、不減)。
  第 i 則的標籤時刻 = 則號 ≤ i 的最後一個時鐘點,`after` = i − 該則號;沒有這樣的點 = 首筆成交前,`after` = i + 1
- `trade`:每個成交則依序 4 格攤平 `[達錢成交時刻毫秒, 價, 張, 內外盤]`(時刻 = 存檔 `ms` 原值),內外盤為
  `"inner"` / `"outer"` / `"neutral"`;長度 = 4 × `kind` 裡 `t` 的個數,簿則不佔位。列在 `anomalous` 的成交
  時刻照原值保留、不一定是當日(1815 那則是前一日 14:30)
- `kf`:第 0、K、2K… 則的完整 20 格(K = `kf_every`,個數 = ceil(n / K))
- `d`:長 n,第 i 則相對第 i−1 則變了的格,攤平成 `[欄號, 新值, 欄號, 新值, …]`(第 −1 則視為 20 格全 null)
- `chg`:長 n,第 i 則的變動分解(= `Frame.changes`,順序照變動分解那段)攤平成一列,每項以種類碼開頭
  (種類碼 = 基本碼 + 側別碼,側別碼 買 0 / 賣 1;價 0 = 市價佇列)。第 0 則恆空:
  - 基本碼 0 價位變動 `[碼, 價, 前量, 後量, 成交]`:掛入 = 後量 − 前量(增加時),撤單 = 前量 − 後量 − 成交(減少時)
  - 基本碼 2 被擠出五檔 `[碼, 價, 離開前的量]`
  - 基本碼 4 重新可見 `[碼, 價, 離開時量, 現在量, 期間成交, 淨掛, 離開則號, 離開毫秒]`
  - 基本碼 6 首次進入五檔 `[碼, 價, 量]`
- `eat`:每個成交則一列(順序同 `trade`,長度 = 成交則數),`Frame.eaten` 攤平成 `[側別碼, 檔位, 張, …]`:
  側別碼 = 被吃的掛單在買 0 / 賣 1;檔位 = 限價第 1–5 檔、0 = 市價佇列、null = 五檔外;空列 = 看不出吃哪一檔

值:價毫元、量張的整數;null = 該層不存在;價 0 = 鎖停的市價單佇列(0 與 null 不可混)。
解碼:逐則播放 = 從前一則套 `d[i]`;跳到第 i 則 = 取 `kf[i // K]` 再套 `d[i//K*K + 1 .. i]`(`book_at`)。
兩條路在每個 keyframe 必須逐格相等 —— `decode` 對每個 keyframe 做這個自檢。
"""

from __future__ import annotations

import base64
import bisect
import datetime as _dt
import gzip
import json
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from dataclasses import fields as dataclass_fields  # `fields` 會跟 payload 的 fields 鍵混淆
from operator import attrgetter
from typing import Any, TypedDict

from copycat.ticks import BOOK_FIELDS, DEPTH, TickRow

__all__ = [
    "BOOK_LEVEL_FIELDS",
    "CLOCK_FUTURE_TOLERANCE_MS",
    "FORMAT_VERSION",
    "KEYFRAME_EVERY",
    "TRADE_CARRY_MESSAGES",
    "TRADE_CARRY_MS",
    "BookChange",
    "BookReplay",
    "Eaten",
    "EnteredView",
    "Frame",
    "LeftView",
    "LevelChange",
    "PluginFormatError",
    "PluginPayload",
    "Reappeared",
    "Trade",
    "book_at",
    "decode",
    "encode",
    "parse_plugin_js",
    "plugin_js",
    "replay_books",
]

_TAIPEI = _dt.timezone(_dt.timedelta(hours=8))

#: 外掛檔呼叫的全域函式(回看頁定義;逐筆外掛檔是 `window.__tk`,兩者分開)
_PLUGIN_CALLBACK = "window.__bk"
_PLUGIN_LINE = re.compile(
    re.escape(_PLUGIN_CALLBACK) + r'\("(?P<key>[^"\\]*)","(?P<blob>[A-Za-z0-9+/=]*)"\);'
)

#: 外掛檔格式版本;改格式 = +1(回看頁依它選解碼規則)
FORMAT_VERSION = 2

#: 每幾則放一個完整五檔(keyframe);回看頁跳到任一則最多套這麼多則 delta
KEYFRAME_EVERY = 256

#: 成交的達錢時刻最多能比 server 收到時刻「晚」多少還算真成交。正常是早 ~0.6 秒;本機鐘落後
#: (#236 時鐘偏差,實務秒級)會讓它看起來晚幾秒。超過 = 不可能收得到的未來時刻,例如開機時
#: 收到前一日的盤後成交(2026-09-16 1815:07:31 收到、蓋 14:30),不讓它當時鐘點(文字標籤的時刻)。
CLOCK_FUTURE_TOLERANCE_MS = 60_000

#: 成交則附的五檔還沒反映這筆成交時,後面幾則內的同價位減量仍先算成交:往後至多這麼多則、且收到時刻
#: 至多晚這麼多毫秒(兩條都要成立)。2026-09-16 全日 80 檔:成交量 88.1% 在同一則就看得到減量,2.4% 是掃單
#: (前幾筆成交則的五檔還是舊的)晚 1–8 則才減、晚的毫秒 p50 1 / p99 46 / 最大 599;只扣同一則會把這些
#: 被買走 / 賣掉的量寫成撤單(user 2026-09-17 拍板算成交)。
TRADE_CARRY_MESSAGES = 8
TRADE_CARRY_MS = 1_000

#: 一則五檔的 20 格欄序(= tick 存檔欄名):買價 0–4、買量 0–4、賣價 0–4、賣量 0–4。
#: 價為毫元、量為張;None = 該層不存在;價 0 = 鎖停時的市價單佇列(真資料,原樣保留)。
BOOK_LEVEL_FIELDS: tuple[str, ...] = BOOK_FIELDS[BOOK_FIELDS.index("bid0") :]
assert len(BOOK_LEVEL_FIELDS) == 4 * DEPTH

_book_of: Callable[[TickRow], tuple[int | None, ...]] = attrgetter(*BOOK_LEVEL_FIELDS)


#: 一則的種類 ↔ 外掛檔 `kind` 字元(兩個方向同一張表)
_KIND_CODE: dict[str, str] = {"trade": "t", "book": "b"}
_KIND_NAME: dict[str, str] = {code: name for name, code in _KIND_CODE.items()}


class PluginFormatError(ValueError):
    """外掛檔解不回原樣:不是外掛檔、版本不認得、檔頭與內容不符、逐則的值不合模組說明,或 delta 與
    keyframe 對不上(`decode` 逐條列出它檢查什麼)。"""


@dataclass(frozen=True, slots=True)
class Trade:
    """成交則上的那一筆成交(tick 存檔成交列原值)。"""

    # 達錢成交時刻(台北 HH:MM:SS.fff 換毫秒,存檔原值;即時個股只到整秒;異常成交可能不是當日)
    ms: int | None
    price_milli: int | None
    qty: int | None  # 張
    side: str | None  # "inner" | "outer" | "neutral"(看盤引擎當時的判定)


#: 外掛檔 `trade` 內外盤格的值域(= `StockTick.side`)
_SIDES: frozenset[str] = frozenset({"inner", "outer", "neutral"})


#: 外掛檔 `trade` 每筆成交的格序 = `Trade` 欄序(encode 取值與 decode 建構同一個來源)
_TRADE_CELLS: tuple[str, ...] = tuple(f.name for f in dataclass_fields(Trade))
_trade_cells: Callable[[Trade], tuple[int | str | None, ...]] = attrgetter(*_TRADE_CELLS)

#: 五檔兩側,序號 = 外掛檔變動項目的側別碼(買 0 / 賣 1)
_BOOK_SIDES: tuple[str, str] = ("bid", "ask")


@dataclass(frozen=True, slots=True)
class LevelChange:
    """兩則都看得到的同一價位,量從 `before` 變 `after`(張;價 0 = 市價佇列)。

    量增加 = 掛入;量減少先算成交 `traded`,剩下的算撤單。
    """

    side: str  # "bid" | "ask"
    price_milli: int
    before: int
    after: int
    traded: int  # 這次減少裡算成交的張數(量增加時恆 0)

    @property
    def added(self) -> int:
        return max(0, self.after - self.before)

    @property
    def cancelled(self) -> int:
        return max(0, self.before - self.after - self.traded)


@dataclass(frozen=True, slots=True)
class LeftView:
    """價位被擠到第五檔之外(離開視野),離開前最後看到 `qty` 張(> 0;0 張離開不列)。"""

    side: str  # "bid" | "ask"
    price_milli: int
    qty: int


@dataclass(frozen=True, slots=True)
class Reappeared:
    """被擠出五檔的價位回到看得到的範圍(重新可見),不產生掛單。

    看不到的那段**無法分辨是一次掛進或分次堆積**,只給離開時量、現在量、期間該價位成交量與淨掛。
    """

    side: str  # "bid" | "ask"
    price_milli: int
    left_qty: int  # 離開前最後看到的量(看得到時已先變 0 就是 0)
    now_qty: int  # 回來這一則的量(沒掛 = 0)
    traded_away: int  # 離開期間(含離開與回來那兩則)在這個價位的成交量
    left_index: int  # 離開那一則的則號
    away_ms: int  # 離開時長(收到時刻)

    @property
    def net_placed(self) -> int:
        """期間淨掛值 = 現在量 − 離開時量 + 期間成交量。"""
        return self.now_qty - self.left_qty + self.traded_away


@dataclass(frozen=True, slots=True)
class EnteredView:
    """從沒追蹤過的價位帶量進到看得到的範圍(首次進入五檔),不算掛單。"""

    side: str  # "bid" | "ask"
    price_milli: int
    qty: int


#: 一則裡的一項變動(`Frame.changes`)
BookChange = LevelChange | LeftView | Reappeared | EnteredView


@dataclass(frozen=True, slots=True)
class Eaten:
    """成交吃到的掛單(成交明細的吃檔欄,見模組說明「吃檔」)。"""

    side: str  # 被吃的掛單在哪一側:"bid" | "ask"
    level: int | None  # 成交前那一則五檔的第幾檔:限價 1–5(只數限價)、0 = 市價佇列、None = 五檔外
    qty: int


@dataclass(frozen=True, slots=True)
class Frame:
    """重播的一則 = 一列 tick 存檔當下的五檔 + 它在兩把時間尺上的位置(見模組說明)。"""

    msg_seq: int
    kind: str  # "trade" | "book"
    book: tuple[int | None, ...]  # 20 格,欄序見 BOOK_LEVEL_FIELDS
    clock_ms: int | None  # 最近一個時鐘點的達錢時刻(台北當日毫秒);None = 首筆成交前
    after: int  # 距該時鐘點第幾則(時鐘點本身 0;首筆成交前自第 1 則數起)
    recv_ms: int  # 時間軸位置 = server 收到時刻(交易日台北零點起毫秒);本機鐘回撥時沿用前一則
    trade: Trade | None  # 成交則的那筆成交;簿則 None
    changes: tuple[BookChange, ...]  # 相對同一檔上一則變了什麼(見模組說明「變動分解」);第一則恆空
    eaten: tuple[Eaten, ...]  # 成交則吃到的掛單(見模組說明「吃檔」);簿則與看不出吃哪一檔時恆空

    @property
    def anomalous_trade(self) -> bool:
        """成交則、卻沒當成時鐘點 = 達錢時刻異常(時鐘點本身 `after` = 0)。"""
        return self.kind == "trade" and self.after != 0


@dataclass(frozen=True, slots=True)
class BookReplay:
    """一檔一日的簿重播:`frames` 依訊息序號遞增。"""

    code: str
    trade_date: str
    frames: tuple[Frame, ...]

    @property
    def anomalous_trades(self) -> int:
        """達錢時刻異常、沒當成時鐘點的成交則數(晚於收到時刻超過容差,或早於目前時鐘)。"""
        return sum(frame.anomalous_trade for frame in self.frames)


class PluginPayload(TypedDict):
    """外掛檔 v2 的 JSON 物件;各鍵的意義見模組說明「外掛檔 v2」。"""

    v: int
    code: str
    date: str
    n: int
    fields: list[str]
    kf_every: int
    seq: list[int]
    kind: str
    anomalous: list[int]
    recv: list[int]
    trade: list[int | str | None]
    kf: list[list[int | None]]
    d: list[list[int | None]]
    chg: list[list[int]]
    eat: list[list[int | None]]


def replay_books(rows: Iterable[TickRow]) -> dict[str, BookReplay]:
    """一天的 tick 存檔列(任意順序、多檔交錯)→ 每檔的簿重播,鍵 = 代號。

    一次只重播一個交易日:混到別天的列 → ValueError(兩把時間尺都以交易日台北零點換算,混日算不出對的時刻)。
    """
    by_code: dict[str, list[TickRow]] = defaultdict(list)
    trade_date: str | None = None
    for row in rows:
        if trade_date is None:
            trade_date = row.trade_date
        elif row.trade_date != trade_date:
            raise ValueError(
                f"一次只重播一個交易日:{trade_date} 與 {row.trade_date} 混在一起"
                f"({row.code} msg_seq={row.msg_seq})"
            )
        by_code[row.code].append(row)
    out: dict[str, BookReplay] = {}
    for code, code_rows in by_code.items():
        code_rows.sort(key=attrgetter("msg_seq"))
        out[code] = BookReplay(code, code_rows[0].trade_date, _frames(code_rows))
    return out


def _frames(rows: list[TickRow]) -> tuple[Frame, ...]:
    parts: list[tuple[int, str, tuple[int | None, ...], int | None, int, int, Trade | None]] = []
    all_changes: list[tuple[BookChange, ...]] = []
    ledger = _EatLedger()
    clock: int | None = None
    clock_index = -1
    day_start_ms = _taipei_day_start_epoch_ms(rows[0].trade_date)
    recv_ms = rows[0].recv_ns // 1_000_000 - day_start_ms
    views: tuple[_SideView, _SideView] | None = None
    unmatched: list[_UnmatchedTrade] = []
    for i, row in enumerate(rows):
        if _is_clock_point(row, clock, day_start_ms):
            assert row.ms is not None
            clock, clock_index = row.ms, i
        recv_ms = max(recv_ms, row.recv_ns // 1_000_000 - day_start_ms)
        trade = Trade(row.ms, row.price_milli, row.qty, row.side) if row.kind == "trade" else None
        book = _book_of(row)
        ledger.add_book(book)
        traded_price = traded_qty = None
        if trade is not None and trade.price_milli is not None and trade.qty:
            traded_price, traded_qty = trade.price_milli, trade.qty
            unmatched.append(_UnmatchedTrade(traded_price, traded_qty, i, recv_ms, trade.side))
        live: list[_UnmatchedTrade] = []
        for pending in unmatched:
            if not pending.qty:
                continue
            if (
                i - pending.index <= TRADE_CARRY_MESSAGES
                and recv_ms - pending.recv_ms <= TRADE_CARRY_MS
            ):
                live.append(pending)
            else:
                ledger.unabsorbed(pending)
        unmatched = live
        if views is None:
            views = (_SideView(0, book), _SideView(1, book))
            changes: tuple[BookChange, ...] = ()
        else:
            step = (i, recv_ms, traded_price, traded_qty, unmatched, ledger)
            changes = (*views[0].step(book, *step), *views[1].step(book, *step))
        parts.append((row.msg_seq, row.kind, book, clock, i - clock_index, recv_ms, trade))
        all_changes.append(changes)
    for pending in unmatched:
        ledger.unabsorbed(pending)
    return tuple(
        Frame(*part, changes, ledger.eaten(i))
        for i, (part, changes) in enumerate(zip(parts, all_changes, strict=True))
    )


@dataclass(slots=True)
class _UnmatchedTrade:
    """還沒在五檔看到對應減量的成交(剩 `qty` 張);`TRADE_CARRY_MESSAGES` 則且 `TRADE_CARRY_MS` 內有效。"""

    price_milli: int
    qty: int
    index: int  # 成交則則號
    recv_ms: int
    side: str | None  # 內外盤("inner" | "outer" | "neutral");到期沒扣到時判斷五檔外用


def _absorb(
    unmatched: list[_UnmatchedTrade], price: int | None, decrease: int
) -> list[tuple[_UnmatchedTrade, int]]:
    """量減少 `decrease` 張先扣還沒扣到的成交(由舊到新、就地扣減),回傳 [(成交, 扣了幾張)]。

    `price` None = 市價佇列:不看成交價(鎖停時成交價是漲跌停價,吃掉的卻是市價那一排,
    2026-09-16 2426 11:02:50 實錄)。
    """
    takes: list[tuple[_UnmatchedTrade, int]] = []
    remaining = decrease
    for trade in unmatched:
        if remaining <= 0:
            break
        if trade.qty and (price is None or trade.price_milli == price):
            take = min(remaining, trade.qty)
            trade.qty -= take
            remaining -= take
            takes.append((trade, take))
    return takes


class _EatLedger:
    """每筆成交吃到哪一檔(見模組說明「吃檔」)。成交則附的五檔可能晚幾則才反映,所以等扣到或到期才記。"""

    def __init__(self) -> None:
        self._books: list[tuple[int | None, ...]] = []
        self._eaten: dict[int, list[Eaten]] = {}

    def add_book(self, book: tuple[int | None, ...]) -> None:
        self._books.append(book)

    def absorbed(
        self, trade: _UnmatchedTrade, side: int, price: int | None, qty: int, index: int
    ) -> None:
        """第 `index` 則某側 `price`(None = 市價佇列)的減量扣了這筆成交 `qty` 張。

        檔位看成交前那一則;那一則沒列出這個價位就看扣到的那一則的前一則 —— 扣得到 = 那一則有量,一定列著。
        """
        if price is None:
            level = 0
        else:
            before = _level_of(self._books[trade.index - 1], side, price) if trade.index else None
            level = before if before is not None else _level_of(self._books[index - 1], side, price)
        self._add(trade.index, Eaten(_BOOK_SIDES[side], level, qty))

    def unabsorbed(self, trade: _UnmatchedTrade) -> None:
        """到期都沒扣到的量:成交價在成交前那一則該側第五檔之外 = 五檔外;其餘看不出吃了哪一檔,不記。"""
        side = {"inner": 0, "outer": 1}.get(trade.side or "")
        if not trade.qty or side is None or trade.index == 0:
            return
        _listed, _queue, bound = _side_levels(self._books[trade.index - 1], side)
        price = trade.price_milli
        if bound is not None and (price > bound if side else price < bound):
            self._add(trade.index, Eaten(_BOOK_SIDES[side], None, trade.qty))

    def eaten(self, index: int) -> tuple[Eaten, ...]:
        return tuple(self._eaten.get(index, ()))

    def _add(self, index: int, eat: Eaten) -> None:
        eats = self._eaten.setdefault(index, [])
        if eats and (eats[-1].side, eats[-1].level) == (eat.side, eat.level):
            eats[-1] = Eaten(eat.side, eat.level, eats[-1].qty + eat.qty)
        else:
            eats.append(eat)


def _level_of(book: tuple[int | None, ...], side: int, price: int) -> int | None:
    """`price` 是這份簿該側限價的第幾檔(最優 = 1,市價佇列不佔號);沒列出 → None。"""
    base = 2 * DEPTH * side
    limits = sorted((p for level in range(DEPTH) if (p := book[base + level])), reverse=side == 0)
    return limits.index(price) + 1 if price in limits else None


@dataclass(slots=True)
class _Away:
    """被擠出五檔的價位:離開前最後看到的量、離開那一則、之後在這個價位的成交累計。"""

    qty: int
    index: int
    recv_ms: int
    traded: int = 0


class _SideView:
    """一側的視野(見模組說明「變動分解」):邊界、追蹤中的價位、被擠出去的價位。

    追蹤中 = 看得到時列出過的限價,記最後已知量(之後在看得到的範圍內歸 0 仍追蹤);市價佇列恆看得到、另記。
    """

    def __init__(self, side: int, book: tuple[int | None, ...]) -> None:
        self._side = side
        self._name = _BOOK_SIDES[side]
        self._listed, self._queue, self._bound = _side_levels(book, side)
        self._tracked: dict[int, int] = dict(self._listed)
        self._tracked_prices: list[int] = sorted(self._tracked)
        self._away: dict[int, _Away] = {}
        self._away_prices: list[int] = []

    def _covers(self, bound: int | None, price: int) -> bool:
        """看得到:買方價 ≥ 第五檔限價、賣方價 ≤ 第五檔限價;bound None(不滿五層)= 整側看得到。"""
        if bound is None:
            return True
        return price >= bound if self._side == 0 else price <= bound

    def _track(self, price: int, qty: int) -> None:
        if price not in self._tracked:
            bisect.insort(self._tracked_prices, price)
        self._tracked[price] = qty

    def step(
        self,
        book: tuple[int | None, ...],
        index: int,
        recv_ms: int,
        traded_price: int | None,
        traded_qty: int | None,
        unmatched: list[_UnmatchedTrade],
        ledger: _EatLedger,
    ) -> list[BookChange]:
        """這一則相對上一則,這一側變了什麼(同側市價佇列在前,其後由最優價往外)。"""
        listed, queue, bound = _side_levels(book, self._side)
        prev_listed, prev_queue, prev_bound = self._listed, self._queue, self._bound
        self._listed, self._queue, self._bound = listed, queue, bound
        out: list[BookChange] = []
        if queue != prev_queue:
            traded = self._traded(unmatched, None, prev_queue - queue, index, ledger)
            out.append(LevelChange(self._name, 0, prev_queue, queue, traded))
        for price in prev_listed.keys() | listed.keys():
            if not (self._covers(prev_bound, price) and self._covers(bound, price)):
                continue  # 只在一則看得到:離開 / 回來 / 首次進入,下面處理
            before, after = prev_listed.get(price, 0), listed.get(price, 0)
            if after or price in self._tracked:
                self._track(price, after)
            if before != after:
                traded = self._traded(unmatched, price, before - after, index, ledger)
                out.append(LevelChange(self._name, price, before, after, traded))
        for price in self._leaving(prev_bound, bound):
            qty = self._tracked.pop(price)
            self._away[price] = _Away(qty, index, recv_ms)
            bisect.insort(self._away_prices, price)
            if qty:
                out.append(LeftView(self._name, price, qty))
        if traded_qty and traded_price in self._away:
            self._away[traded_price].traded += traded_qty
        for price in self._returning(prev_bound, bound):
            away = self._away.pop(price)
            now = listed.get(price, 0)
            self._track(price, now)
            if away.qty or now or away.traded:
                out.append(
                    Reappeared(
                        self._name,
                        price,
                        away.qty,
                        now,
                        away.traded,
                        away.index,
                        recv_ms - away.recv_ms,
                    )
                )
        for price, qty in listed.items():
            if not self._covers(prev_bound, price) and price not in self._tracked:
                self._track(price, qty)
                if qty:
                    out.append(EnteredView(self._name, price, qty))
        direction = -1 if self._side == 0 else 1
        out.sort(key=lambda change: (change.price_milli != 0, direction * change.price_milli))
        return out

    def _traded(
        self,
        unmatched: list[_UnmatchedTrade],
        price: int | None,
        decrease: int,
        index: int,
        ledger: _EatLedger,
    ) -> int:
        """減量先扣成交並記到吃檔帳上,回傳算成交的張數。"""
        traded = 0
        for trade, take in _absorb(unmatched, price, decrease):
            ledger.absorbed(trade, self._side, price, take, index)
            traded += take
        return traded

    def _leaving(self, prev_bound: int | None, bound: int | None) -> list[int]:
        """邊界收窄時被擠出去的追蹤中價位(從追蹤清單移除,回傳由小到大)。"""
        prices = self._tracked_prices
        if bound is None or (prev_bound is not None and bound == prev_bound):
            return []
        if self._side == 0:
            if prev_bound is not None and bound < prev_bound:
                return []
            cut = bisect.bisect_left(prices, bound)
            leaving, self._tracked_prices = prices[:cut], prices[cut:]
        else:
            if prev_bound is not None and bound > prev_bound:
                return []
            cut = bisect.bisect_right(prices, bound)
            leaving, self._tracked_prices = prices[cut:], prices[:cut]
        return leaving

    def _returning(self, prev_bound: int | None, bound: int | None) -> list[int]:
        """邊界放寬時回到看得到範圍的被擠出價位(從被擠出清單移除,回傳由小到大)。"""
        prices = self._away_prices
        if prev_bound is None or (bound is not None and bound == prev_bound):
            return []
        if self._side == 0:
            if bound is not None and bound > prev_bound:
                return []
            cut = 0 if bound is None else bisect.bisect_left(prices, bound)
            returning, self._away_prices = prices[cut:], prices[:cut]
        else:
            if bound is not None and bound < prev_bound:
                return []
            cut = len(prices) if bound is None else bisect.bisect_right(prices, bound)
            returning, self._away_prices = prices[:cut], prices[cut:]
        return returning


def _side_levels(book: Sequence[int | None], side: int) -> tuple[dict[int, int], int, int | None]:
    """一側五檔 → (限價 {價: 量}、市價佇列量(沒有 = 0)、看得到的邊界)。

    邊界:五層都有價時 = 最遠那一檔限價(買方最低 / 賣方最高),之外看不到;不滿五層 = None(整側看得到)。
    有價沒量當 0。
    """
    base = 2 * DEPTH * side
    listed: dict[int, int] = {}
    queue = 0
    levels = 0
    for level in range(DEPTH):
        price = book[base + level]
        if price is None:
            continue
        levels += 1
        qty = book[base + DEPTH + level] or 0
        if price == 0:
            queue = qty
        else:
            listed[price] = qty
    if levels < DEPTH or not listed:
        return listed, queue, None
    return listed, queue, (min(listed) if side == 0 else max(listed))


def _is_clock_point(row: TickRow, clock: int | None, day_start_ms: int) -> bool:
    """成交列當時鐘點(文字標籤時刻)的條件:有達錢時刻、不早於目前時鐘、不晚於收到時刻超過容差。"""
    if row.kind != "trade" or row.ms is None:
        return False
    if clock is not None and row.ms < clock:
        return False  # 標籤時刻不倒退
    return day_start_ms + row.ms <= row.recv_ns // 1_000_000 + CLOCK_FUTURE_TOLERANCE_MS


def _taipei_day_start_epoch_ms(trade_date: str) -> int:
    start = _dt.datetime.fromisoformat(trade_date).replace(tzinfo=_TAIPEI)
    return int(start.timestamp()) * 1000


def encode(code_day: BookReplay, *, keyframe_every: int = KEYFRAME_EVERY) -> PluginPayload:
    """一檔一日的簿重播 → 外掛檔 payload(可直接 JSON 化)。格式見模組說明「外掛檔 v2」。"""
    if keyframe_every < 1:
        raise ValueError(f"keyframe_every 須 ≥ 1(收到 {keyframe_every})")
    seq: list[int] = []
    kinds: list[str] = []
    anomalous: list[int] = []
    recv: list[int] = []
    trades: list[int | str | None] = []
    keyframes: list[list[int | None]] = []
    deltas: list[list[int | None]] = []
    changes: list[list[int]] = []
    eaten: list[list[int | None]] = []
    state: list[int | None] = [None] * len(BOOK_LEVEL_FIELDS)
    prev_seq = prev_recv = 0
    for i, frame in enumerate(code_day.frames):
        seq.append(frame.msg_seq - prev_seq)
        prev_seq = frame.msg_seq
        recv.append(frame.recv_ms - prev_recv)
        prev_recv = frame.recv_ms
        kinds.append(_KIND_CODE[frame.kind])
        if frame.kind == "trade":
            assert frame.trade is not None, (
                f"{code_day.code} msg_seq={frame.msg_seq} 成交則沒帶成交"
            )
            trades += _trade_cells(frame.trade)
            eaten.append(_encode_eaten(frame.eaten))
            if frame.anomalous_trade:
                anomalous.append(i)
        delta: list[int | None] = []
        for field, value in enumerate(frame.book):
            if value != state[field]:
                delta += [field, value]
        deltas.append(delta)
        changes.append(_encode_changes(frame.changes))
        state = list(frame.book)
        if i % keyframe_every == 0:
            keyframes.append(list(frame.book))
    return {
        "v": FORMAT_VERSION,
        "code": code_day.code,
        "date": code_day.trade_date,
        "n": len(code_day.frames),
        "fields": list(BOOK_LEVEL_FIELDS),
        "kf_every": keyframe_every,
        "seq": seq,
        "kind": "".join(kinds),
        "anomalous": anomalous,
        "recv": recv,
        "trade": trades,
        "kf": keyframes,
        "d": deltas,
        "chg": changes,
        "eat": eaten,
    }


def _encode_eaten(eaten: tuple[Eaten, ...]) -> list[int | None]:
    """一筆成交的吃檔 → `eat` 的一列 `[側別碼, 檔位, 張, …]`(檔位 null = 五檔外)。"""
    out: list[int | None] = []
    for eat in eaten:
        out += [_BOOK_SIDES.index(eat.side), eat.level, eat.qty]
    return out


def _decode_eaten(cells: Sequence[Any], code: str, index: int) -> tuple[Eaten, ...]:
    """`eat` 的一列 → 吃檔(`_encode_eaten` 的反函數);格數不是 3 的倍數、側別碼 / 檔位 / 張數不合 →
    PluginFormatError。"""
    if len(cells) % 3:
        raise PluginFormatError(f"{code} 第 {index} 則:吃檔格數 {len(cells)} 不是 3 的倍數")
    out: list[Eaten] = []
    for k in range(0, len(cells), 3):
        side, level, qty = cells[k : k + 3]
        if side not in (0, 1) or not (level is None or 0 <= level <= DEPTH) or qty <= 0:
            raise PluginFormatError(
                f"{code} 第 {index} 則:吃檔 {[side, level, qty]} 不合(側別碼 0 / 1、檔位 0–5 或 null、張數 > 0)"
            )
        out.append(Eaten(_BOOK_SIDES[side], level, qty))
    return tuple(out)


#: 外掛檔 `chg` 每項佔幾格(含開頭的種類碼);種類碼 = 2 × 這張表的序號 + 側別碼(買 0 / 賣 1)
_CHANGE_WIDTHS: tuple[int, ...] = (
    5,  # 0 / 1 價位變動:[碼, 價, 前量, 後量, 成交]
    3,  # 2 / 3 被擠出五檔:[碼, 價, 離開前的量]
    8,  # 4 / 5 重新可見:[碼, 價, 離開時量, 現在量, 期間成交, 淨掛, 離開則號, 離開毫秒]
    3,  # 6 / 7 首次進入五檔:[碼, 價, 量]
)


def _encode_changes(changes: tuple[BookChange, ...]) -> list[int]:
    """一則的變動 → `chg` 的一列(格式見模組說明「外掛檔 v2」)。"""
    out: list[int] = []
    for change in changes:
        side = _BOOK_SIDES.index(change.side)
        match change:
            case LevelChange():
                out += [side, change.price_milli, change.before, change.after, change.traded]
            case LeftView():
                out += [2 + side, change.price_milli, change.qty]
            case Reappeared():
                out += [
                    4 + side,
                    change.price_milli,
                    change.left_qty,
                    change.now_qty,
                    change.traded_away,
                    change.net_placed,
                    change.left_index,
                    change.away_ms,
                ]
            case EnteredView():
                out += [6 + side, change.price_milli, change.qty]
    return out


def _decode_changes(cells: Sequence[Any], code: str, index: int) -> tuple[BookChange, ...]:
    """`chg` 的一列 → 這一則的變動(`_encode_changes` 的反函數)。

    種類碼不認得、最後一項格數不足 → PluginFormatError。
    """
    out: list[BookChange] = []
    k = 0
    while k < len(cells):
        kind = cells[k]
        if not isinstance(kind, int) or not 0 <= kind < 2 * len(_CHANGE_WIDTHS):
            raise PluginFormatError(f"{code} 第 {index} 則:變動種類碼 {kind!r} 不認得")
        width = _CHANGE_WIDTHS[kind // 2]
        item = cells[k + 1 : k + width]
        if len(item) != width - 1:
            raise PluginFormatError(f"{code} 第 {index} 則:變動項目格數不足(種類碼 {kind})")
        side = _BOOK_SIDES[kind % 2]
        match kind // 2:
            case 0:
                out.append(LevelChange(side, *item))
            case 1:
                out.append(LeftView(side, *item))
            case 2:
                price, left_qty, now_qty, traded_away, net, left_index, away_ms = item
                if net != now_qty - left_qty + traded_away:
                    raise PluginFormatError(
                        f"{code} 第 {index} 則 {side} {price}:淨掛 {net} 不等於"
                        f" 現在 {now_qty} − 離開時 {left_qty} + 期間成交 {traded_away}"
                    )
                out.append(
                    Reappeared(side, price, left_qty, now_qty, traded_away, left_index, away_ms)
                )
            case _:
                out.append(EnteredView(side, *item))
        k += width
    return tuple(out)


def plugin_js(payload: PluginPayload) -> str:
    """payload → 外掛檔全文:一行 `window.__bk("<代號>|<日期>","<base64(gzip(JSON))>");`。

    gzip `mtime=0`:同一份資料重產出逐位元組相同的檔(重跑 CLI 不製造無意義差異)。
    """
    raw = json.dumps(payload, separators=(",", ":")).encode("ascii")
    blob = base64.b64encode(gzip.compress(raw, compresslevel=9, mtime=0)).decode("ascii")
    key = json.dumps(f"{payload['code']}|{payload['date']}")
    return f'{_PLUGIN_CALLBACK}({key},"{blob}");'


def parse_plugin_js(text: str) -> PluginPayload:
    """外掛檔全文 → payload(`plugin_js` 的反函數)。不是一行 `window.__bk(...)` → PluginFormatError。"""
    match = _PLUGIN_LINE.fullmatch(text.strip())
    if match is None:
        raise PluginFormatError(f"不是簿重播外掛檔(找不到 {_PLUGIN_CALLBACK}(...) 一行)")
    payload: PluginPayload = json.loads(
        gzip.decompress(base64.b64decode(match["blob"], validate=True))
    )
    expected_key = f"{payload.get('code')}|{payload.get('date')}"
    if match["key"] != expected_key:
        # 回看頁以呼叫鍵配對懶載入的請求:鍵與內容不符 = 畫面掛到別檔別日的簿
        raise PluginFormatError(f"外掛檔呼叫鍵 {match['key']!r} 與內容 {expected_key!r} 不符")
    return payload


def book_at(payload: PluginPayload, index: int) -> tuple[int | None, ...]:
    """第 `index` 則的五檔,走回看頁跳轉的規則:該則之前最近的 keyframe + 其後到該則的 delta。

    `index` 不在 0..n−1 → IndexError:不照 list 容許負數 —— 負數或 n 在這條規則下會默默回到別則的簿。
    本身只驗 `index` 範圍與途經的 delta;檔頭(版本、kf_every、各陣列長度)的檢查在 `decode`,先解過一次再跳轉。
    """
    code, n, every = payload["code"], payload["n"], payload["kf_every"]
    if not 0 <= index < n:
        raise IndexError(f"{code} 沒有第 {index} 則(共 {n} 則)")
    base = (index // every) * every
    state = list(payload["kf"][index // every])
    for i, delta in enumerate(payload["d"][base + 1 : index + 1], start=base + 1):
        _apply_delta(state, delta, code, i)
    return tuple(state)


def _apply_delta(state: list[int | None], delta: Sequence[Any], code: str, index: int) -> None:
    """第 `index` 則的 `[欄號, 新值, 欄號, 新值, …]` 套到 20 格上(欄號與值混在同一串,所以收 Any)。

    不成對、欄號不在 0–19 → PluginFormatError(負欄號照 list 規則會默默寫進別格)。
    """
    if len(delta) % 2:
        raise PluginFormatError(f"{code} 第 {index} 則:delta 長度 {len(delta)} 不是偶數")
    for k in range(0, len(delta), 2):
        field = delta[k]
        if not 0 <= field < len(state):
            raise PluginFormatError(
                f"{code} 第 {index} 則:delta 欄號 {field!r} 不在 0–{len(state) - 1}"
            )
        state[field] = delta[k + 1]


def decode(payload: PluginPayload) -> BookReplay:
    """外掛檔 payload → 簿重播(`encode` 的反函數;回看頁解碼規則的 Python 版)。

    反函數對 `replay_books` 產出的簿重播成立;成交的內外盤不在三值(型別上 `Trade.side` 允許 None)時
    `encode` 照寫、這裡拒收 —— CLI 落檔前的解回自檢會擋下,不落檔。

    自檢,不合格一律 PluginFormatError:
    - 檔頭與內容的形狀(`_check_header`:版本、鍵、欄序、各陣列長度、kf_every ≥ 1、kind 字元、
      anomalous 則號遞增且落在成交則)
    - 逐則:訊息序號遞增、收到時刻不倒退、delta 成對且欄號 0–19、內外盤是三值之一;時鐘點成交(沒列在
      `anomalous` 的成交)有達錢時刻且不早於目前的標籤時刻
    - 每個 keyframe 位置,逐則套 delta 的結果與 keyframe 逐格相等 —— 回看頁「播放」走 delta、「跳轉」走
      keyframe,兩條路對不上 = 同一刻兩份簿
    值的型別(例如該是整數的地方放了字串)不在檢查範圍。
    """
    _check_header(payload)
    code, every, keyframes = payload["code"], payload["kf_every"], payload["kf"]
    trades = iter(zip(*[iter(payload["trade"])] * len(_TRADE_CELLS), strict=True))
    eat_rows = iter(payload["eat"])
    anomalous = iter(payload["anomalous"])
    next_anomalous = next(anomalous, None)
    clock: int | None = None
    clock_index = -1
    state: list[int | None] = [None] * len(BOOK_LEVEL_FIELDS)
    prev_state: list[int | None] | None = None
    recv_at: list[int] = []
    frames: list[Frame] = []
    msg_seq = recv_ms = 0
    for i, (seq_step, kind, recv_step, delta, change_cells) in enumerate(
        zip(
            payload["seq"],
            payload["kind"],
            payload["recv"],
            payload["d"],
            payload["chg"],
            strict=True,
        )
    ):
        if seq_step <= 0:
            raise PluginFormatError(f"{code} 第 {i} 則:訊息序號沒有遞增(差值 {seq_step})")
        if recv_step < 0:
            raise PluginFormatError(f"{code} 第 {i} 則:收到時刻倒退 {recv_step} ms")
        msg_seq += seq_step
        recv_ms += recv_step
        recv_at.append(recv_ms)
        _apply_delta(state, delta, code, i)
        if i % every == 0 and state != keyframes[i // every]:
            raise PluginFormatError(
                f"{code} 第 {i} 則:delta 累積結果與 keyframe 不符"
                f"({state} ≠ {keyframes[i // every]})"
            )
        kind_name = _KIND_NAME[kind]
        trade = Trade(*next(trades)) if kind_name == "trade" else None
        if trade is not None:
            if trade.side not in _SIDES:
                raise PluginFormatError(
                    f"{code} 第 {i} 則:內外盤 {trade.side!r} 不是 {' / '.join(sorted(_SIDES))}"
                )
            if i == next_anomalous:
                next_anomalous = next(anomalous, None)
            elif trade.ms is None:
                raise PluginFormatError(f"{code} 第 {i} 則:成交沒列為時刻異常,卻沒有達錢時刻")
            elif clock is not None and trade.ms < clock:
                raise PluginFormatError(
                    f"{code} 第 {i} 則:成交沒列為時刻異常,達錢時刻 {trade.ms} 早於標籤時刻 {clock}"
                )
            else:
                clock, clock_index = trade.ms, i
        changes = _decode_changes(change_cells, code, i)
        if prev_state is None:
            if changes:
                raise PluginFormatError(f"{code} 第 0 則:當日第一則沒有前一則可比,不該有變動")
        else:
            _check_changes(changes, prev_state, state, recv_at, code, i)
        prev_state = list(state)
        eaten = _decode_eaten(next(eat_rows), code, i) if trade is not None else ()
        if trade is not None and sum(eat.qty for eat in eaten) > (trade.qty or 0):
            raise PluginFormatError(
                f"{code} 第 {i} 則:吃檔共 {sum(eat.qty for eat in eaten)} 張,超過成交 {trade.qty} 張"
            )
        frames.append(
            Frame(
                msg_seq,
                kind_name,
                tuple(state),
                clock,
                i - clock_index,
                recv_ms,
                trade,
                changes,
                eaten,
            )
        )
    return BookReplay(code, payload["date"], tuple(frames))


def _check_changes(
    changes: tuple[BookChange, ...],
    prev_book: Sequence[int | None],
    book: Sequence[int | None],
    recv_at: list[int],
    code: str,
    index: int,
) -> None:
    """第 `index` 則的變動與前後兩則五檔一致(回看頁把變動清單與階梯並排顯示,對不上 = 同一刻講兩件事)。"""
    for change in changes:
        side = _BOOK_SIDES.index(change.side)
        price = change.price_milli
        where = f"{code} 第 {index} 則 {change.side} {price}"
        before_book, after_book = _qty_at(prev_book, side, price), _qty_at(book, side, price)
        match change:
            case LevelChange():
                if change.before == change.after:
                    raise PluginFormatError(
                        f"{where}:價位變動前後都是 {change.before} 張,沒有變不該列"
                    )
                if change.before != before_book:
                    raise PluginFormatError(
                        f"{where}:前量 {change.before} 與前一則五檔 {before_book} 不符"
                    )
                if change.after != after_book:
                    raise PluginFormatError(
                        f"{where}:後量 {change.after} 與這一則五檔 {after_book} 不符"
                    )
                if not 0 <= change.traded <= max(0, change.before - change.after):
                    raise PluginFormatError(f"{where}:成交 {change.traded} 張不在 0 到減少的量之間")
            case LeftView():
                if change.qty <= 0 or change.qty != before_book:
                    raise PluginFormatError(
                        f"{where}:離開前的量 {change.qty} 與前一則五檔 {before_book} 不符(須 > 0)"
                    )
            case Reappeared():
                if change.now_qty != after_book:
                    raise PluginFormatError(
                        f"{where}:現在量 {change.now_qty} 與這一則五檔 {after_book} 不符"
                    )
                if not 0 <= change.left_index < index:
                    raise PluginFormatError(f"{where}:離開則號 {change.left_index} 不在這一則之前")
                away_ms = recv_at[index] - recv_at[change.left_index]
                if change.away_ms != away_ms:
                    raise PluginFormatError(
                        f"{where}:離開時長 {change.away_ms} ms 與收到時刻差 {away_ms} ms 不符"
                    )
                if not (change.left_qty or change.now_qty or change.traded_away):
                    raise PluginFormatError(f"{where}:重新可見三個量都是 0,不該列")
            case EnteredView():
                if change.qty <= 0 or change.qty != after_book:
                    raise PluginFormatError(
                        f"{where}:首次進入五檔的量 {change.qty} 與這一則五檔 {after_book} 不符(須 > 0)"
                    )


def _qty_at(book: Sequence[int | None], side: int, price: int) -> int:
    """這份簿該側 `price` 的量(價 0 = 市價佇列);沒列出 = 0。"""
    listed, queue, _bound = _side_levels(book, side)
    return queue if price == 0 else listed.get(price, 0)


def _check_header(payload: PluginPayload) -> None:
    """檔頭與內容的形狀一致(逐則的檢查在 `decode` 迴圈裡)。"""
    if payload.get("v") != FORMAT_VERSION:
        raise PluginFormatError(f"外掛檔版本 {payload.get('v')!r} 不認得(本版解 {FORMAT_VERSION})")
    missing = set(PluginPayload.__required_keys__) - set(payload)
    if missing:
        raise PluginFormatError(f"外掛檔缺鍵:{sorted(missing)}")
    code, n, every, kinds = payload["code"], payload["n"], payload["kf_every"], payload["kind"]
    if list(payload["fields"]) != list(BOOK_LEVEL_FIELDS):
        raise PluginFormatError(f"{code} 五檔欄序與本版不同:{payload['fields']}")
    lengths = tuple(len(payload[key]) for key in ("seq", "kind", "recv", "d", "chg"))
    if lengths != (n, n, n, n, n):
        raise PluginFormatError(
            f"{code} 檔頭 n={n} 與 seq / kind / recv / d / chg 長度 {lengths} 不符"
        )
    if every < 1:
        raise PluginFormatError(f"{code} kf_every={every!r} 不合法:須 ≥ 1")
    if len(payload["kf"]) != -(-n // every):
        raise PluginFormatError(
            f"{code} keyframe 個數 {len(payload['kf'])} 不符(n={n}、每 {every} 則一個)"
        )
    if not set(kinds) <= _KIND_NAME.keys():
        raise PluginFormatError(f"{code} kind 有不認得的字元:{set(kinds) - _KIND_NAME.keys()}")
    width, trade_count = len(_TRADE_CELLS), kinds.count(_KIND_CODE["trade"])
    if len(payload["trade"]) != width * trade_count:
        raise PluginFormatError(
            f"{code} trade 長度 {len(payload['trade'])} 不是成交則數 × {width}({trade_count} 則)"
        )
    if len(payload["eat"]) != trade_count:
        raise PluginFormatError(
            f"{code} eat 長度 {len(payload['eat'])} 不是成交則數({trade_count} 則)"
        )
    prev_index = -1
    for index in payload["anomalous"]:
        if not (prev_index < index < n and kinds[index] == _KIND_CODE["trade"]):
            raise PluginFormatError(
                f"{code} 時刻異常成交則號 {index} 不合法:則號須遞增且落在成交則"
            )
        prev_index = index
