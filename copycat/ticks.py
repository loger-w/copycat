"""tick 存檔的列形狀與讀回(spec #257)。

**列**(CONTEXT.md「tick 存檔 / 成交列 / 簿列」):盤中 server 收到的每一則個股訊息,以
`kind="trade"`(看盤引擎 `ingest` 為真的那筆成交)或 `kind="book"`(五檔任一變動)落成
一列;兩種列共用 `msg_seq`(進程內全域序號,**同日重啟自檔尾接續、不歸零**,排序只看它)與
`recv_ns`(server 收到當下的本機 `time.time_ns()`,牆鐘、校時回撥可能倒退,**不當排序鍵**)。
寫入端在 `copycat.live.tick_persist`,本模組只管形狀與讀回。

`precise_time` 在**簿列**的語意 = 「這個簿在哪筆成交之後」,**不是簿變動時刻**:達錢簿更新
訊息的 `PreciseTime` / `FilledTime` / `TradeQuantity` 都是上一筆成交的殘影(2026-09-14 實測
43,289 則零例外,skill `tc4-market-facts`)。簿列的時刻只有 `recv_ns` 是真的。

讀回:`load_day` 走 stdlib 讀 jsonl(當天還沒轉檔的檔也讀得到);parquet 讀回在 T4 接上
(pyarrow 只在 extras `[ticks]`)。
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
from dataclasses import dataclass, fields
from pathlib import Path

from copycat.live.stock_models import StockTick

logger = logging.getLogger(__name__)

__all__ = [
    "BOOK_FIELDS",
    "DEPTH",
    "TRADE_FIELDS",
    "TickRow",
    "book_parquet_path",
    "jsonl_path",
    "load_day",
    "parquet_path",
    "taipei_ms",
]

DEPTH = 5


def jsonl_path(data_dir: Path, trade_date: str) -> Path:
    """`<dir>/<YYYYMMDD>.jsonl`;`trade_date` 為 `YYYY-MM-DD`(StockTick 同尺)。"""
    return data_dir / f"{trade_date.replace('-', '')}.jsonl"


def parquet_path(data_dir: Path, trade_date: str) -> Path:
    """成交 parquet `<dir>/<YYYYMMDD>.parquet`(永久保留)。"""
    return data_dir / f"{trade_date.replace('-', '')}.parquet"


def book_parquet_path(data_dir: Path, trade_date: str) -> Path:
    """簿 parquet `<dir>/<YYYYMMDD>-book.parquet`(保留 `book_keep_days` 個交易日)。"""
    return data_dir / f"{trade_date.replace('-', '')}-book.parquet"


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
    msg_seq: int  # 進程內全域序號(每則進引擎路由的現貨訊息佔一號,含被擋的);同日重啟自檔尾接續
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


#: `TickRow` 欄序 = parquet 欄序;成交檔全欄、簿檔只有共同欄(到 `askq4` 為止)。
TRADE_FIELDS: tuple[str, ...] = tuple(f.name for f in fields(TickRow))
BOOK_FIELDS: tuple[str, ...] = TRADE_FIELDS[: TRADE_FIELDS.index("time")]
_FIELD_NAMES = frozenset(TRADE_FIELDS)


def _row_from_dict(payload: dict) -> TickRow:
    return TickRow(**{k: v for k, v in payload.items() if k in _FIELD_NAMES})


def load_day(day: _dt.date, data_dir: Path) -> list[TickRow]:
    """讀回某日全部列(成交 + 簿),依 `msg_seq` 排序 = 當天完整訊息流。

    parquet 優先(成交檔在就讀 parquet,簿檔可能已過保留期而不在 → 只有成交列),沒有才讀
    jsonl(當天還沒轉檔)。jsonl 走 stdlib;parquet 需 pyarrow(extras `[ticks]`,未裝 →
    ImportError 帶安裝說明)。排序只看 `msg_seq`(寫入端同日重啟自檔尾接續,不歸零);
    **不用 `recv_ns`** —— 它是牆鐘,校時回撥會把跨段列交錯(round-1 Spec F-03)。
    兩種檔都不存在 → FileNotFoundError。
    """
    date = day.isoformat()
    trade_pq = parquet_path(data_dir, date)
    if trade_pq.exists():
        rows = _read_parquet(trade_pq)
        book_pq = book_parquet_path(data_dir, date)
        if book_pq.exists():
            rows.extend(_read_parquet(book_pq))
    else:
        path = jsonl_path(data_dir, date)
        if not path.exists():
            raise FileNotFoundError(path)
        rows = []
        bad = 0
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                # 與 `ticks_compact.compact_day` 同口徑(pr-263 F-07):當機留下的半行 / 壞行跳過
                # 計數,不讓一行壞資料把整天讀回炸掉
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    bad += 1
                    continue
                if not isinstance(payload, dict) or payload.get("kind") not in ("trade", "book"):
                    bad += 1
                    continue
                rows.append(_row_from_dict(payload))
        if bad:
            logger.warning("load_day %s:jsonl 壞行 %d 行已跳過(%s)", date, bad, path.name)
    rows.sort(key=lambda r: r.msg_seq)
    return rows


def _read_parquet(path: Path) -> list[TickRow]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise ImportError(
            f"讀 {path.name} 需要 pyarrow:pip install -e .[ticks](當天未轉檔的 jsonl 不需要)"
        ) from exc
    table = pq.read_table(path)
    return [_row_from_dict(r) for r in table.to_pylist()]
