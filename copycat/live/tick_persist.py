"""盤中個股 tick 存檔的寫入端(spec #257;列形狀與讀回在 `copycat.ticks`)。

由 stock engine 在 `_handle_quote` 尾端對**每一則現貨訊息**呼叫 `observe` 一次:訊息序號
`msg_seq` 每則 +1(被試撮 / 重複擋掉的也佔號,照序號合起來才是完整訊息流);`ingest` 為真
的那筆寫成交列。寫入 = 直接在看盤 loop 上 `write` 進 64 KB 緩衝 handle、不 fsync、每
`flush_secs` 一次 `flush`(只是 write syscall;bakeoff T3 b5 / b6:單筆 0.5 µs、70 萬次無
> 1 ms)。handle 在 `start` 與換日 `open_day` 預先開好,開檔那 9 ms 不落在盤中第一筆。

檔名由**每一列**的 `trade_date` 決定(同日重啟 `"a"` 續寫、跨日自然分檔);同時最多握兩天
的 handle(rollover stage1 到新日首筆之間兩日訊息會交錯),`open_day` 時關掉其他日。
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TextIO

from copycat.live.stock_models import StockBook, StockTick
from copycat.ticks import DEPTH, jsonl_path, taipei_ms
from copycat.ticks_config import TicksConfig

__all__ = ["TickPersist"]

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_BUFFER_BYTES = 64 * 1024


def _put_levels(out: dict, levels: list[tuple[int, int]], price_key: str, qty_key: str) -> None:
    """五檔 20 欄:先五層價再五層量;不存在的層 None(價 0 = 市價佇列,原樣保留)。"""
    for i in range(DEPTH):
        out[f"{price_key}{i}"] = levels[i][0] if i < len(levels) else None
    for i in range(DEPTH):
        out[f"{qty_key}{i}"] = levels[i][1] if i < len(levels) else None


class TickPersist:
    def __init__(self, config: TicksConfig, *, base_dir: Path = _REPO_ROOT) -> None:
        self._cfg = config
        d = Path(config.dir)
        self._dir = d if d.is_absolute() else base_dir / d
        self._files: dict[str, TextIO] = {}  # trade_date → 開著的 handle(最多兩天)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._flush_timer: asyncio.TimerHandle | None = None
        self._closed = False
        self._msg_seq = 0
        # 簿列去重基準:code → 該檔**上一列存下的簿**(五檔 20 個數;成交列自帶的五檔也算)。
        # 「達錢重推一模一樣的簿」與「成交後緊接同一個簿」都不佔列,只進 `dup_books`。
        self._basis: dict[str, tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]]] = {}
        self.trades = 0
        self.books = 0
        self.dup_books = 0
        self.flushes = 0

    @property
    def dir(self) -> Path:
        return self._dir

    # ---- 生命週期 ----

    def start(self, loop: asyncio.AbstractEventLoop, trade_date: str) -> None:
        """預開當日 handle + 武裝定時 flush;engine.start 呼叫。"""
        self._loop = loop
        self.open_day(trade_date)
        self._arm_flush()

    def open_day(self, trade_date: str) -> None:
        """預開 `trade_date` 的 handle(換日 stage2 呼叫),其他日的 handle flush + 關。"""
        if self._closed:
            return
        for day in [d for d in self._files if d != trade_date]:
            self._close_file(day)
        self._file_for(trade_date)

    def flush(self) -> None:
        """把緩衝寫進 OS(write syscall,不 fsync)。"""
        for fh in self._files.values():
            fh.flush()
        self.flushes += 1

    def close(self) -> None:
        """flush + 關全部 handle;之後 `observe` 為 no-op。engine.close 呼叫。"""
        if self._closed:
            return
        self._closed = True
        if self._flush_timer is not None:
            self._flush_timer.cancel()
            self._flush_timer = None
        for day in list(self._files):
            self._close_file(day)

    # ---- 熱路徑 ----

    def observe(
        self,
        *,
        code: str,
        quote: dict,
        book: StockBook,
        tick: StockTick | None,
        engine_seq: int,
        trade_date: str,
        recv_ns: int,
    ) -> None:
        """每一則現貨 REALTIME 訊息呼叫一次;`tick` 只在 engine `ingest` 為真時非 None。

        `trade_date` = engine 當前交易日,給**簿列**用(簿更新訊息沒有可信的日期欄);
        成交列用 `tick.trade_date`。區分成交 / 簿更新只看 `tick`(= 累積量有沒有前進),
        不看 `TradeQuantity` —— 那是上一筆成交的殘影。
        """
        if self._closed:
            return
        self._msg_seq += 1
        key = (tuple(book.bids), tuple(book.asks))
        if tick is None:
            if self._basis.get(code) == key:
                self.dup_books += 1
                return
            self._basis[code] = key
            row = self._common(code, trade_date, quote, book, recv_ns, kind="book")
            self._file_for(trade_date).write(json.dumps(row, ensure_ascii=False) + "\n")
            self.books += 1
            return
        self._basis[code] = key  # 成交列自帶的五檔也是「上一列存下的簿」
        row = self._common(code, tick.trade_date, quote, book, recv_ns, kind="trade")
        row["time"] = tick.time
        row["ms"] = taipei_ms(tick.time)
        row["price_milli"] = tick.price_milli
        row["qty"] = tick.qty
        row["cum_vol"] = tick.cum_vol
        row["flag"] = tick.flag
        row["side"] = tick.side
        row["seq"] = engine_seq
        self._file_for(tick.trade_date).write(json.dumps(row, ensure_ascii=False) + "\n")
        self.trades += 1

    def _common(
        self, code: str, trade_date: str, quote: dict, book: StockBook, recv_ns: int, *, kind: str
    ) -> dict:
        """兩種列的共同欄(順序 = `TickRow` 欄序):身分 + 時刻 + 達錢原始字串 + 五檔 20 欄。"""
        row: dict = {
            "kind": kind,
            "code": code,
            "trade_date": trade_date,
            "msg_seq": self._msg_seq,
            "recv_ns": recv_ns,
            "precise_time": _raw_str(quote.get("PreciseTime")),
            "trade_status": _raw_str(quote.get("TradeStatus")),
        }
        _put_levels(row, book.bids, "bid", "bidq")
        _put_levels(row, book.asks, "ask", "askq")
        return row

    # ---- 內部 ----

    def _file_for(self, trade_date: str) -> TextIO:
        fh = self._files.get(trade_date)
        if fh is None:
            self._dir.mkdir(parents=True, exist_ok=True)
            fh = open(  # noqa: SIM115 — 長駐 handle,關檔在 close / open_day
                jsonl_path(self._dir, trade_date),
                "a",
                buffering=_BUFFER_BYTES,
                encoding="utf-8",
                newline="\n",
            )
            self._files[trade_date] = fh
        return fh

    def _close_file(self, trade_date: str) -> None:
        fh = self._files.pop(trade_date)
        fh.close()  # close 隱含 flush

    def _arm_flush(self) -> None:
        if self._loop is None or self._closed:
            return
        self._flush_timer = self._loop.call_later(self._cfg.flush_secs, self._on_flush_timer)

    def _on_flush_timer(self) -> None:
        self._flush_timer = None
        if self._closed:
            return
        self.flush()
        self._arm_flush()


def _raw_str(value: object) -> str | None:
    """達錢原始欄位照存:欄缺 / null → None,其餘 `str()`(達錢哪天送 int 也不丟)。"""
    return None if value is None else str(value)
