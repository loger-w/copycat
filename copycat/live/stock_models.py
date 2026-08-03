"""個股 REALTIME / 歷史 TICKS 對映層(欄位事實:docs/research/2026-07-21-stock-spot-quote-order-probe.md)。

- 位移命名歸一:`Bid`=最佳(L0)、`Bid1`=第二檔(L1)…(TC4 REALTIME 慣例,07-18 期權同款)。
- 時間:TC4 的 FilledTime/PreciseTime 為 UTC,parse 層即 +8 轉台北;OpenTime/CloseTime
  實測為交易所當地時間(90000 = 09:00 台北),不轉。
- 試撮:只以時間窗判定([08:30,09:00) / [13:25,13:30),端點不含);TradeStatus != "0"
  值域未實測,僅 warning 觀測不丟棄(design v4 r2-F5)。
"""

from __future__ import annotations

import datetime as _dt
import logging
from dataclasses import dataclass, replace

from copycat.tc4common import to_milli_units

logger = logging.getLogger(__name__)

_DEPTH = 5
_TAIPEI_OFFSET = _dt.timedelta(hours=8)
# 試撮窗(台北,端點不含右界;09:00:00 起=開盤撮合、13:30:00 起=收盤撮合,皆真成交)
_TRIAL_WINDOWS = (("08:30:00.000", "09:00:00.000"), ("13:25:00.000", "13:30:00.000"))


#: 十進位字串 → 毫元整數(元 × 1000);空/無效 → None。
#: 與 `live.models.to_millipts` 同一個運算(單位名不同)→ 實作在 tc4common,此處留具名別名。
to_milli = to_milli_units


def _to_int(raw: str) -> int | None:
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None


@dataclass(frozen=True)
class StockTick:
    code: str
    price_milli: int
    qty: int
    cum_vol: int
    time: str  # 台北 HH:MM:SS.fff(parse 層已 +8)
    trade_date: str  # 台北 YYYY-MM-DD
    side: str  # "outer" | "inner" | "neutral"(成交當下對照 Bid/Ask)
    buy_sell_flag: int | None
    is_trial: bool
    # 成交當下的最佳買賣價(= derive_side 的輸入,round5 明細欄位)。
    # 有 default 是必要的:既有建構點(tests/live/test_stock_state.py、
    # tests/server/test_stock_engine.py)以關鍵字建構且不會帶新欄位。
    bid_milli: int | None = None
    ask_milli: int | None = None


@dataclass(frozen=True)
class StockBook:
    bids: list[tuple[int, int]]  # [(價毫元, 張數)] L0..L4;空側 = []
    asks: list[tuple[int, int]]


@dataclass(frozen=True)
class StockMeta:
    name: str
    ref_milli: int | None  # 參考價(除權息已反映,design:不自算前收)
    upper_milli: int | None
    lower_milli: int | None
    y_close_milli: int | None
    y_volume: int | None
    open_time: str  # HH:MM:SS(交易所當地時間)
    close_time: str


def _hhmmss(raw: str) -> str:
    s = raw.zfill(6)
    return f"{s[:2]}:{s[2:4]}:{s[4:6]}"


def _taipei_time(precise_utc: str, date_utc: str) -> tuple[str, str]:
    """(PreciseTime, Date/TradeDate) UTC → (台北 HH:MM:SS.fff, 台北 YYYY-MM-DD)。"""
    s = precise_utc.zfill(12)
    hh, mm, ss, frac = int(s[:2]), int(s[2:4]), int(s[4:6]), s[6:9]
    base = _dt.datetime.strptime(date_utc, "%Y%m%d")
    local = base + _dt.timedelta(hours=hh, minutes=mm, seconds=ss) + _TAIPEI_OFFSET
    return f"{local:%H:%M:%S}.{frac}", f"{local:%Y-%m-%d}"


def is_trial_window(time_taipei: str) -> bool:
    """台北 HH:MM:SS.fff 是否落在試撮窗(端點不含右界、含左界)。"""
    return any(lo <= time_taipei < hi for lo, hi in _TRIAL_WINDOWS)


def derive_side(price_milli: int, bid_milli: int | None, ask_milli: int | None) -> str:
    if ask_milli is not None and price_milli >= ask_milli:
        return "outer"
    if bid_milli is not None and price_milli <= bid_milli:
        return "inner"
    return "neutral"


def relabel_locked_side(
    tick: StockTick, upper_milli: int | None, lower_milli: int | None
) -> StockTick:
    """鎖漲跌停且對手側整個不可得時,補回 `derive_side` 判不出來的那一邊。

    **為什麼需要這個**:歷史 TICKS row 只有單一 `Bid`/`Ask` 欄(不像 REALTIME 有五檔可以
    往下找第一個限價檔),鎖停日那一欄就是市價佇列的 `0`,`_best_limit_price` 無從施力
    → 整天的回補 tick 全判 neutral。而 `apply_backfill` 會先 `reset()` 再用回補資料重放,
    所以 live 期間判好的值每次切檔都被洗掉 —— 2026-07-31 實測 2327 切檔後
    `cum_outer = cum_inner = 0` 回到原點。

    **為什麼可以補**:這不是猜測,是漲跌停制度下的恆等式。鎖漲停時漲停價之上沒有更高價可掛,
    主動買方只能排隊,**唯一**能促成成交的是主動賣方 → 內盤;鎖跌停對稱 → 外盤。

    五道閘一律不套用(寧可留 neutral 也不冒充):
    - 已判定的 tick(只補 neutral)
    - 成交價不在漲停 / 跌停價上
    - 漲跌停不可得
    - **對手側拿得到** —— 有 ask 還判不出來是另一回事(價差內成交),
      不可用鎖停規則蓋過去
    - **同側也要不可得**(Phase 5 review P2):`ask is None` 不等於「鎖住了」。
      「首次攻上漲停、把賣方掛單一次吃光」的那一筆,成交後簿的 ask 側同樣是空的,
      但它實際是**主動買**(outer)—— 只看 ask 空會把它反向標成 inner,而偏誤方向固定
      (系統性低估攻擊方),恰好打到本輪要修對的外盤比。真鎖停時歷史 row 的 Bid 是市價
      佇列的 0(`parse_hist_tick` 已歸零成 None),首攻那一筆的 Bid 通常有值 → 兩者可分。
    """
    if tick.side != "neutral":
        return tick
    locked = tick.bid_milli is None and tick.ask_milli is None
    if not locked:
        return tick
    if upper_milli is not None and tick.price_milli == upper_milli:
        return replace(tick, side="inner")
    if lower_milli is not None and tick.price_milli == lower_milli:
        return replace(tick, side="outer")
    return tick


def _best_limit_price(levels: list[tuple[int, int]]) -> int | None:
    """簿的最佳**限價**檔位;全是市價佇列 / 空簿 → None。

    鎖漲跌停時 TC4 會在第一檔推「市價單佇列」,價格欄是 `0`。**`0` 不是價格** ——
    它的語意是「這些委託沒有限價」。拿它當 `derive_side` 的 bid/ask 兩側都會壞:

    - 鎖漲停(`bids[0] = (0, N)`、ask 側空):`price <= 0` 恆假 → 每筆成交判 neutral。
      2026-07-31 盤中實測 2327 國巨全日 5450 張成交,`cum_outer = cum_inner = 0`,
      內外盤副圖整片灰、外盤比分母 0 算不出來。
    - 鎖跌停(`asks[0] = (0, N)`、bid 側空):`price >= 0` **恆真** → 一律判 outer。
      方向碰巧對(鎖跌停的成交確為主動買),但 bid 側判定被整條短路。

    **只影響餵給 `derive_side` 的取值,不影響 `book` 本身** —— 簿要原樣保留 0 檔位,
    五檔與閃電梯得把它顯示成「市價」。所以這裡是獨立的挑選函式,
    不是把過濾塞進 `_parse_levels`。
    """
    for price, _vol in levels:
        if price > 0:
            return price
    return None


def _parse_levels(msg: dict, price_key: str, vol_key: str) -> list[tuple[int, int]]:
    """位移命名歸一:`Bid`/`BidVolume`=L0、`Bid1`/`BidVolume1`=L1…;空價位跳過。

    ⚠ 這裡的「空」只指 `price is None`(欄位不存在 / 空字串)。價格 `0` 是**市價單佇列**,
    是真實資料要保留(見 `_best_limit_price`);過濾它是消費端的事,不是解析端的事。
    """
    levels: list[tuple[int, int]] = []
    for i in range(_DEPTH):
        suffix = "" if i == 0 else str(i)
        price = to_milli(msg.get(price_key + suffix, ""))
        vol = _to_int(msg.get(vol_key + suffix, ""))
        if price is None:
            continue
        levels.append((price, vol or 0))
    return levels


def parse_stock_realtime(msg: dict) -> tuple[StockTick | None, StockBook, StockMeta]:
    """一則個股 REALTIME 拆 (tick, book, meta);無成交(qty 空/0)→ tick=None(純簿更新)。"""
    book = StockBook(
        bids=_parse_levels(msg, "Bid", "BidVolume"),
        asks=_parse_levels(msg, "Ask", "AskVolume"),
    )
    meta = StockMeta(
        name=str(msg.get("SecurityName", "")),
        ref_milli=to_milli(msg.get("ReferencePrice", "")),
        upper_milli=to_milli(msg.get("UpperLimitPrice", "")),
        lower_milli=to_milli(msg.get("LowerLimitPrice", "")),
        y_close_milli=to_milli(msg.get("YClosedPrice", "")),
        y_volume=_to_int(msg.get("YTradeVolume", "")),
        open_time=_hhmmss(str(msg.get("OpenTime", ""))),
        close_time=_hhmmss(str(msg.get("CloseTime", ""))),
    )
    status = str(msg.get("TradeStatus", "0") or "0")
    # 已知值域(2026-07-21 盤中實測):0=正常;1=試撮期狀態(13:25-13:30 簿更新,213 筆)。
    # 其餘值僅觀測不丟棄(丟棄的失效模式 = 處置股整檔靜默消失,design r2-F5)
    if status not in ("0", "1"):
        logger.warning("TradeStatus=%s on %s(值域外,僅觀測不丟棄)", status, msg.get("Symbol", ""))
    price = to_milli(msg.get("TradingPrice", ""))
    qty = _to_int(msg.get("TradeQuantity", ""))
    if price is None or qty is None or qty <= 0:
        return None, book, meta
    time_tp, date_tp = _taipei_time(str(msg.get("PreciseTime", "")), str(msg.get("TradeDate", "")))
    bid0 = _best_limit_price(book.bids)
    ask0 = _best_limit_price(book.asks)
    tick = StockTick(
        code=str(msg.get("Security", "")),
        price_milli=price,
        qty=qty,
        cum_vol=_to_int(msg.get("TradeVolume", "")) or 0,
        time=time_tp,
        trade_date=date_tp,
        side=derive_side(price, bid0, ask0),
        buy_sell_flag=_to_int(msg.get("FlagOfBuySell", "")),
        is_trial=is_trial_window(time_tp),
        bid_milli=bid0,
        ask_milli=ask0,
    )
    return tick, book, meta


def parse_hist_tick(code: str, row: dict) -> StockTick | None:
    """歷史/當日回補 TICKS row → StockTick;缺 price/qty/PreciseTime → None。"""
    price = to_milli(row.get("TradingPrice", ""))
    qty = _to_int(row.get("TradeQuantity", ""))
    if price is None or qty is None or qty <= 0:
        return None
    precise = str(row.get("PreciseTime", ""))
    date = str(row.get("Date", ""))
    if not precise or not date:
        return None
    time_tp, date_tp = _taipei_time(precise, date)
    # 歷史 row 只有單一 Bid/Ask 欄,沒有「往下找第一個限價檔」的餘地 ——
    # 0(市價單佇列)一律歸零成 None,誠實地讓 derive_side 判不出來,
    # 而不是留一個假價位把判定短路(同 `_best_limit_price` 的理由)。
    bid = to_milli(row.get("Bid", "")) or None
    ask = to_milli(row.get("Ask", "")) or None
    tick = StockTick(
        code=code,
        price_milli=price,
        qty=qty,
        cum_vol=_to_int(row.get("TradeVolume", "")) or 0,
        time=time_tp,
        trade_date=date_tp,
        side=derive_side(price, bid, ask),
        buy_sell_flag=None,
        is_trial=is_trial_window(time_tp),
        bid_milli=bid,
        ask_milli=ask,
    )
    return tick
