"""盤中個股 tick 存檔的寫入端(spec #257;列形狀與讀回在 `copycat.ticks`)。

由 stock engine 在 `_handle_quote` 尾端對**每一則現貨訊息**呼叫 `observe` 一次:訊息序號
`msg_seq` 每則 +1(被試撮 / 重複擋掉的也佔號,照序號合起來才是完整訊息流);`ingest` 為真
的那筆寫成交列,其餘餵五檔給簿列去重。寫入 = 直接在看盤 loop 上 `write` 進 64 KB 緩衝
handle、不 fsync、每 `flush_secs` 一次 `flush`(只是 write syscall;bakeoff T3 b5 / b6:單筆
0.5 µs、70 萬次無 > 1 ms)。handle 在 `start` 與換日 `open_day` 預先開好,開檔那 9 ms 不落在
盤中第一筆。

檔名由**每一列**的 `trade_date` 決定(同日重啟 `"a"` 續寫、跨日自然分檔);同時最多握兩天
的 handle(rollover stage1 到新日首筆之間兩日訊息會交錯),`open_day` 時關掉其他日。

**存檔永遠不影響看盤**:開檔 / 寫入 / flush 任一拋 OSError → WARNING 一次、**該日停寫**
(計數器保留、`msg_seq` 照走),換日重新武裝;絕不 raise 進訊息處理路徑。`enabled=false`
→ 零檔案、零 handle、零 timer(引擎照呼叫,全部 no-op)。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from pathlib import Path
from typing import Callable, TextIO

from copycat.live.stock_models import StockBook, StockTick
from copycat.ticks import DEPTH, jsonl_path, taipei_ms
from copycat.ticks_config import TicksConfig

__all__ = ["STATS_FMT", "TickPersist"]

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_BUFFER_BYTES = 64 * 1024

#: 每日一行的字面 = 盤後判準(CLAUDE.md §4 契約;`grep "tick 存檔" logs/server-*.log`,寫入失敗
#: 應為 0)。換日 stage2 印舊日、關機印當日、13:45 轉檔前再印一次(T5);同日多行取最後。
STATS_FMT = "tick 存檔 %s:成交 %d / 簿 %d / 重複簿略過 %d / flush %d / 寫入失敗 %d"


def _open_append(path: Path) -> TextIO:
    return open(path, "a", buffering=_BUFFER_BYTES, encoding="utf-8", newline="\n")  # noqa: SIM115


def _put_levels(out: dict, levels: list[tuple[int, int]], price_key: str, qty_key: str) -> None:
    """五檔 20 欄:先五層價再五層量;不存在的層 None(價 0 = 市價佇列,原樣保留)。"""
    for i in range(DEPTH):
        out[f"{price_key}{i}"] = levels[i][0] if i < len(levels) else None
    for i in range(DEPTH):
        out[f"{qty_key}{i}"] = levels[i][1] if i < len(levels) else None


class TickPersist:
    def __init__(
        self,
        config: TicksConfig,
        *,
        base_dir: Path = _REPO_ROOT,
        opener: Callable[[Path], TextIO] = _open_append,
    ) -> None:
        """`opener` 是測試注入壞 handle(OSError)的唯一入口;prod 用預設的 append 開檔。"""
        self._cfg = config
        self._enabled = config.enabled
        d = Path(config.dir)
        self._dir = d if d.is_absolute() else base_dir / d
        self._opener = opener
        self._files: dict[str, TextIO] = {}  # trade_date → 開著的 handle(最多兩天)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._flush_timer: asyncio.TimerHandle | None = None
        self._closed = False
        self._msg_seq = 0
        # 當日停寫:某日開檔 / 寫入 / flush 拋 OSError 後記在這裡,該日之後的列全部略過
        # (只 WARNING 一次);換日 `open_day` 開的是別的日期,自然重新武裝。
        self._failed_days: set[str] = set()
        # 簿列去重基準:code → 該檔**上一列存下的簿**(五檔 20 個數;成交列自帶的五檔也算)。
        # 「達錢重推一模一樣的簿」與「成交後緊接同一個簿」都不佔列,只進 `dup_books`。
        self._basis: dict[str, tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]]] = {}
        self._day: str | None = None  # 計數器所屬日(`open_day` 換日時歸零)
        self.trades = 0
        self.books = 0
        self.dup_books = 0
        self.flushes = 0
        self.write_failures = 0

    @property
    def dir(self) -> Path:
        return self._dir

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ---- 生命週期 ----

    def start(self, loop: asyncio.AbstractEventLoop, trade_date: str) -> None:
        """預開當日 handle + 武裝定時 flush;engine.start 呼叫。"""
        if not self._enabled:
            return
        self._loop = loop
        self.open_day(trade_date)
        self._arm_flush()

    def open_day(self, trade_date: str) -> None:
        """預開 `trade_date` 的 handle(換日 stage2 呼叫),其他日的 handle flush + 關;
        計數器歸零(呼叫端先 `log_stats` 舊日)。"""
        if not self._enabled or self._closed:
            return
        for day in [d for d in self._files if d != trade_date]:
            self._close_file(day)
        if self._day != trade_date:
            self._day = trade_date
            self.trades = self.books = self.dup_books = self.flushes = self.write_failures = 0
        self._file_for(trade_date)

    def flush(self) -> None:
        """把緩衝寫進 OS(write syscall,不 fsync)。"""
        for day, fh in list(self._files.items()):
            try:
                fh.flush()
            except OSError as exc:
                self._fail(day, "flush", exc)
        self.flushes += 1

    def log_stats(self, day: str) -> None:
        """印當日那一行(字面 `STATS_FMT`);零筆也印,判準是「那行存在」。"""
        if not self._enabled:
            return
        logger.info(
            STATS_FMT,
            day,
            self.trades,
            self.books,
            self.dup_books,
            self.flushes,
            self.write_failures,
        )

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
        if not self._enabled or self._closed:
            return
        self._msg_seq += 1
        key = (tuple(book.bids), tuple(book.asks))
        if tick is None:
            if self._basis.get(code) == key:
                self.dup_books += 1
                return
            self._basis[code] = key
            row = self._common(code, trade_date, quote, book, recv_ns, kind="book")
            if self._write(trade_date, row):
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
        if self._write(tick.trade_date, row):
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

    def _write(self, trade_date: str, row: dict) -> bool:
        """一列進緩衝;該日已停寫 → False(不計數);OSError → 記失敗、該日停寫、False。"""
        if trade_date in self._failed_days:
            return False
        try:
            self._file_for(trade_date).write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError as exc:
            self._fail(trade_date, "寫入", exc)
            return False
        return True

    def _file_for(self, trade_date: str) -> TextIO:
        """該日 handle,沒有就開(`open_day` 預開;停寫日不會走到這裡)。可能拋 OSError。"""
        fh = self._files.get(trade_date)
        if fh is None:
            self._dir.mkdir(parents=True, exist_ok=True)
            fh = self._opener(jsonl_path(self._dir, trade_date))
            self._files[trade_date] = fh
        return fh

    def _fail(self, trade_date: str, stage: str, exc: OSError) -> None:
        """OSError 的唯一處置:WARNING 一次、該日停寫、丟掉該日 handle。已停寫的日不再記。"""
        if trade_date in self._failed_days:
            return
        self._failed_days.add(trade_date)
        self.write_failures += 1
        fh = self._files.pop(trade_date, None)
        if fh is not None:
            # 已在失敗處置裡:這個 handle 要丟掉,關不掉也沒有第二步可做(壞的 handle 本來就
            # 關不掉),原因由下面那行 WARNING 帶出;`suppress` 明說「此處刻意不處理」
            with contextlib.suppress(OSError):
                fh.close()
        logger.warning(
            "tick 存檔 %s 停寫(%s 失敗:%s)—— 看盤不受影響,換日自動重試",
            trade_date.replace("-", ""),
            stage,
            exc,
        )

    def _close_file(self, trade_date: str) -> None:
        fh = self._files.pop(trade_date)
        try:
            fh.close()  # close 隱含 flush
        except OSError as exc:
            self._fail(trade_date, "關檔", exc)

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
