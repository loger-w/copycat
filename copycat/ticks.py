"""tick 存檔的列形狀與讀回(spec #257)。

**列**(CONTEXT.md「tick 存檔 / 成交列 / 簿列」):盤中 server 收到的每一則個股訊息,以
`kind="trade"`(看盤引擎 `ingest` 為真的那筆成交)或 `kind="book"`(五檔任一變動)落成
一列;兩種列共用 `msg_seq`(進程內全域序號,**重啟歸零**)與 `recv_ns`(server 收到當下的
本機 `time.time_ns()`)。寫入端在 `copycat.live.tick_persist`,本模組只管形狀與讀回。

`precise_time` 在**簿列**的語意 = 「這個簿在哪筆成交之後」,**不是簿變動時刻**:達錢簿更新
訊息的 `PreciseTime` / `FilledTime` / `TradeQuantity` 都是上一筆成交的殘影(2026-09-14 實測
43,289 則零例外,skill `tc4-market-facts`)。簿列的時刻只有 `recv_ns` 是真的。

讀回:`load_day` 走 stdlib 讀 jsonl(當天還沒轉檔的檔也讀得到);parquet 讀回在 T4 接上
(pyarrow 只在 extras `[ticks]`)。
"""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass, fields
from pathlib import Path

from copycat.live.stock_models import StockTick

__all__ = ["DEPTH", "TickRow", "jsonl_path", "load_day", "taipei_ms"]

DEPTH = 5


def jsonl_path(data_dir: Path, trade_date: str) -> Path:
    """`<dir>/<YYYYMMDD>.jsonl`;`trade_date` 為 `YYYY-MM-DD`(StockTick 同尺)。"""
    return data_dir / f"{trade_date.replace('-', '')}.jsonl"


def taipei_ms(time_taipei: str) -> int:
    """台北 `HH:MM:SS.fff` → 當日毫秒(研究目錄 tick 的時間尺)。"""
    hh, mm, rest = time_taipei.split(":")
    ss, _, frac = rest.partition(".")
    return ((int(hh) * 60 + int(mm)) * 60 + int(ss)) * 1000 + int((frac + "000")[:3])


@dataclass(frozen=True, slots=True)
class TickRow:
    """一列 tick 存檔。共同欄恆有;成交專屬欄在簿列為 None。

    五檔 20 欄 = 該則訊息**解析後**的簿(`StockBook` 位移歸一、價毫元、量張),成交列的
    五檔是**成交後簿**。`bid{i}` 為 0 = 市價單佇列(真資料,原樣保留);None = 該層不存在。
    `precise_time` 為達錢原始 UTC 字串;簿列上它是上一筆成交的殘影(見模組說明)。
    """

    kind: str  # "trade" | "book"
    code: str
    trade_date: str  # 台北 YYYY-MM-DD(檔名由此決定)
    msg_seq: int  # 進程內全域序號(每一則個股 REALTIME 訊息佔一號,含被擋的);重啟歸零
    recv_ns: int  # server 收到當下的本機 time.time_ns()
    precise_time: str | None  # 達錢原始 PreciseTime;簿列 = 上一筆成交殘影,不是簿變動時刻
    trade_status: str | None  # 達錢原始 TradeStatus
    bid0: int | None = None
    bid1: int | None = None
    bid2: int | None = None
    bid3: int | None = None
    bid4: int | None = None
    bidq0: int | None = None
    bidq1: int | None = None
    bidq2: int | None = None
    bidq3: int | None = None
    bidq4: int | None = None
    ask0: int | None = None
    ask1: int | None = None
    ask2: int | None = None
    ask3: int | None = None
    ask4: int | None = None
    askq0: int | None = None
    askq1: int | None = None
    askq2: int | None = None
    askq3: int | None = None
    askq4: int | None = None
    # ---- 成交列專屬 ----
    time: str | None = None  # 台北 HH:MM:SS.fff
    ms: int | None = None  # 台北當日毫秒
    price_milli: int | None = None
    qty: int | None = None
    cum_vol: int | None = None
    flag: str | None = None  # 達錢 FlagOfBuySell 原字串("0" / "1" / "2");欄缺 None
    side: str | None = None  # engine 判定 inner / outer / neutral
    seq: int | None = None  # engine 的成交序號(StockDayState.seq)

    def to_stock_tick(self) -> StockTick:
        """成交列 → 引擎的 `StockTick`(與當時 `ingest` 的那筆相等);簿列 → ValueError。"""
        if self.kind != "trade":
            raise ValueError(f"只有成交列能轉 StockTick(kind={self.kind!r})")
        assert self.price_milli is not None and self.qty is not None
        assert self.cum_vol is not None and self.time is not None and self.side is not None
        return StockTick(
            code=self.code,
            price_milli=self.price_milli,
            qty=self.qty,
            cum_vol=self.cum_vol,
            time=self.time,
            trade_date=self.trade_date,
            side=self.side,
            is_trial=False,  # 試撮成交不進存檔母體
            bid_milli=_best_limit(self.bid0, self.bid1, self.bid2, self.bid3, self.bid4),
            ask_milli=_best_limit(self.ask0, self.ask1, self.ask2, self.ask3, self.ask4),
            flag=self.flag,
        )


def _best_limit(*levels: int | None) -> int | None:
    """同 `stock_models._best_limit_price`:第一個 > 0 的價位;全空 / 全市價佇列 → None。"""
    for price in levels:
        if price is not None and price > 0:
            return price
    return None


_FIELD_NAMES = frozenset(f.name for f in fields(TickRow))


def _row_from_dict(payload: dict) -> TickRow:
    return TickRow(**{k: v for k, v in payload.items() if k in _FIELD_NAMES})


def load_day(day: _dt.date, data_dir: Path) -> list[TickRow]:
    """讀回某日全部列(成交 + 簿),依 `(recv_ns, msg_seq)` 排序。

    排序鍵不是單看 `msg_seq`:它是進程內序號,同日重啟後歸零,單看會把重啟後的列排到
    前面;`recv_ns` 是牆鐘、跨重啟單調,同 ns 撞號再以 `msg_seq` 定序。
    檔不存在 → FileNotFoundError。
    """
    path = jsonl_path(data_dir, day.isoformat())
    if not path.exists():
        raise FileNotFoundError(path)
    rows: list[TickRow] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(_row_from_dict(json.loads(line)))
    rows.sort(key=lambda r: (r.recv_ns, r.msg_seq))
    return rows
