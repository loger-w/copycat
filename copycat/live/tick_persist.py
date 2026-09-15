"""盤中個股 tick 存檔的寫入端(spec #257;列形狀與讀回在 `copycat.ticks`)。

由 stock engine 在 `_handle_quote` **真正尾端**(五檔廣播與訊號 `on_book` 之後,pr-263 F-19)對
**每一則進到引擎路由的現貨訊息**(symbol 有對映、state 存在;池外推播早退不算)呼叫 `observe`
一次:訊息序號 `msg_seq` 每則 +1(被試撮 / 重複擋掉的也佔號,照序號合起來才是完整訊息流;
**同日重啟自檔尾接續**,不歸零);`ingest` 為真的那筆寫成交列,其餘餵五檔給簿列去重。
**簿列只在 09:00 開盤後才寫**(`BOOK_OPEN_TIME`,pr-263 F-04 user 拍板):盤前 08:00 重掛訂閱
到 08:30 試撮那批簿快照不存(計 `books_preopen`),也就不會落在前一交易日、被前一日的 seal
靜默丟掉。寫入 = 直接在看盤 loop 上 `write` 進 64 KB 緩衝 handle、不 fsync、每 `flush_secs`
一次 `flush`(只是 write syscall;bakeoff T3 b5 / b6:單筆 0.5 µs、70 萬次無 > 1 ms)。handle 在
`start` 與換日 `open_day` 預先開好,開檔那 9 ms 不落在盤中第一筆。

檔名由**每一列**的 `trade_date` 決定(同日重啟 `"a"` 續寫、跨日自然分檔);同時最多握兩天
的 handle(rollover stage1 到新日首筆之間兩日訊息會交錯),`open_day` 時關掉其他日。
**該日 parquet 已在 = 已轉檔**:不再開 jsonl(否則盤後重啟的空 jsonl 會讓補跑把真 parquet
蓋成空表,round-1 Spec F-01),該日的列當遲到殘影丟。

**存檔永遠不影響看盤**:開檔 / 寫入 / flush 任一拋 OSError → WARNING 一次、**該日停寫**
(計數器保留、`msg_seq` 照走),換日重新武裝;絕不 raise 進訊息處理路徑(含 `start` 與
`open_day` 的預開,round-1 Spec F-02;檔尾壞 utf-8 也只當「尾列壞」,pr-263 F-09)。
`enabled=false` → 零檔案、零 handle、零 timer。
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime as _dt
import json
import logging
import os
from pathlib import Path
from typing import Callable, TextIO

from copycat.live.stock_models import StockBook, StockTick
from copycat.ticks import BOOK_FIELDS, DEPTH, jsonl_path, parquet_path, taipei_ms
from copycat.ticks_config import TicksConfig, resolve_ticks_dir

__all__ = ["BOOK_OPEN_TIME", "STATS_FMT", "TickPersist", "tail_msg_seq"]

logger = logging.getLogger(__name__)

_BUFFER_BYTES = 64 * 1024
#: 重啟接續 `msg_seq` 時讀檔尾的量:一列 < 1 KB,64 KB 內必有完整尾列(除非檔案更短)
_TAIL_BYTES = 64 * 1024

#: 簿列的開盤閘(台北牆鐘):此刻之前的簿更新不存。成交列不受此閘(09:00 前只有試撮成交,
#: `ingest` 本就不收)。
BOOK_OPEN_TIME = _dt.time(9, 0)

#: 每日一行的字面 = 盤後判準(CLAUDE.md §4 契約;`grep "tick 存檔" logs/server-*.log`,寫入失敗
#: 應為 0)。換日 stage2 印舊日、關機印當日、13:45 轉檔前再印一次(T5);同日多行取最後。
STATS_FMT = "tick 存檔 %s:成交 %d / 簿 %d / 重複簿略過 %d / flush %d / 寫入失敗 %d"
#: 封住後仍到達而丟棄的列數,> 0 才另印一行(不動 `STATS_FMT` 字面;pr-263 F-04)
_SEALED_FMT = "tick 存檔 %s 封住後丟棄 %d 列(該日已轉檔;09:00 後的遲到列)"

#: 五檔 20 欄的鍵名,與 `TickRow` 同源(`BOOK_FIELDS` 尾段),熱路徑不再每則 f-string 現組
#: (pr-263 F-22)
_LEVEL_KEYS = BOOK_FIELDS[BOOK_FIELDS.index("bid0") :]
_BID_KEYS = _LEVEL_KEYS[0:DEPTH]
_BIDQ_KEYS = _LEVEL_KEYS[DEPTH : 2 * DEPTH]
_ASK_KEYS = _LEVEL_KEYS[2 * DEPTH : 3 * DEPTH]
_ASKQ_KEYS = _LEVEL_KEYS[3 * DEPTH : 4 * DEPTH]
assert _BID_KEYS == ("bid0", "bid1", "bid2", "bid3", "bid4") and _ASKQ_KEYS[-1] == "askq4"


def _open_append(path: Path) -> TextIO:
    return open(path, "a", buffering=_BUFFER_BYTES, encoding="utf-8", newline="\n")  # noqa: SIM115


def tail_msg_seq(path: Path) -> int:
    """既有 jsonl 最後一列**完整**列的 `msg_seq`(重啟接續用);檔不在 / 空 / 尾列壞 → 0。

    只讀最後 `_TAIL_BYTES`。上一個 process 當機留下的半行(檔尾不是換行)不算完整列,
    由呼叫端先補一個換行把它隔開,再從最後一列完整列接號 —— 半行裡的號碼不可信。
    壞 utf-8(`UnicodeDecodeError` 是 ValueError、不是 JSONDecodeError)同樣算尾列壞。
    """
    try:
        size = path.stat().st_size
    except OSError:
        return 0
    if size == 0:
        return 0
    with path.open("rb") as fh:
        fh.seek(max(0, size - _TAIL_BYTES))
        chunk = fh.read()
    complete = chunk if chunk.endswith(b"\n") else chunk[: chunk.rfind(b"\n") + 1]
    for line in reversed(complete.splitlines()):
        if not line.strip():
            continue
        try:
            seq = json.loads(line).get("msg_seq")
        except (ValueError, AttributeError):
            continue
        return int(seq) if isinstance(seq, int) else 0
    return 0


def _put_levels(
    out: dict, levels: list[tuple[int, int]], price_keys: tuple[str, ...], qty_keys: tuple[str, ...]
) -> None:
    """五檔 20 欄:先五層價再五層量;不存在的層 None(價 0 = 市價佇列,原樣保留)。"""
    n = len(levels)
    for i, key in enumerate(price_keys):
        out[key] = levels[i][0] if i < n else None
    for i, key in enumerate(qty_keys):
        out[key] = levels[i][1] if i < n else None


class TickPersist:
    def __init__(
        self,
        config: TicksConfig,
        *,
        opener: Callable[[Path], TextIO] = _open_append,
        now_fn: Callable[[], _dt.datetime] = _dt.datetime.now,
    ) -> None:
        """`opener` 是測試注入壞 handle(OSError)的唯一入口;`now_fn` 是簿列開盤閘的牆鐘。"""
        self._cfg = config
        self._enabled = config.enabled
        self._dir = resolve_ticks_dir(config)
        self._opener = opener
        self._now_fn = now_fn
        self._files: dict[str, TextIO] = {}  # trade_date → 開著的 handle(最多兩天)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._flush_timer: asyncio.TimerHandle | None = None
        self._closed = False
        self._msg_seq = 0
        # 當日停寫:某日開檔 / 寫入 / flush 拋 OSError 後記在這裡,該日之後的列全部略過
        # (只 WARNING 一次);換日 `open_day` 開的是別的日期,自然重新武裝。
        self._failed_days: set[str] = set()
        # 已轉檔封住的日(`seal_day` / parquet 已在):該日的列不再寫,只計數;每個封住日
        # WARNING 首筆一次(`_sealed_warned`)
        self._sealed_days: set[str] = set()
        self._sealed_warned: set[str] = set()
        # 簿列去重基準:code → 該檔**上一列存下的簿**(五檔 20 個數;成交列自帶的五檔也算)。
        # 「達錢重推一模一樣的簿」與「成交後緊接同一個簿」都不佔列,只進 `dup_books`。
        self._basis: dict[str, tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]]] = {}
        self._day: str | None = None  # 計數器所屬日(`open_day` 換日時歸零)
        self.trades = 0
        self.books = 0
        self.dup_books = 0
        self.flushes = 0
        self.write_failures = 0
        self.sealed_dropped = 0
        self.books_preopen = 0  # 09:00 前略過的簿更新(不寫、不動去重基準)

    @property
    def dir(self) -> Path:
        return self._dir

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def current_day(self) -> str | None:
        """計數器所屬的交易日(`open_day` 設);排程只對這一天印 `log_stats`(pr-263 F-05)。"""
        return self._day

    # ---- 生命週期 ----

    def start(self, loop: asyncio.AbstractEventLoop, trade_date: str) -> None:
        """預開當日 handle + 武裝定時 flush;engine.start 呼叫。不 raise(預開失敗 = 當日停寫)。"""
        if not self._enabled:
            return
        self._loop = loop
        self.open_day(trade_date)
        self._arm_flush()

    def open_day(self, trade_date: str) -> None:
        """預開 `trade_date` 的 handle(換日 stage2 呼叫),其他日的 handle flush + 關;
        計數器歸零(呼叫端先 `log_stats` 舊日)。該日 parquet 已在 → 不開,封住。不 raise。"""
        if not self._enabled or self._closed:
            return
        for day in [d for d in self._files if d != trade_date]:
            self._close_file(day)
        if self._day != trade_date:
            self._day = trade_date
            self.trades = self.books = self.dup_books = self.flushes = self.write_failures = 0
            self.sealed_dropped = self.books_preopen = 0
        if trade_date in self._failed_days or trade_date in self._sealed_days:
            return
        if parquet_path(self._dir, trade_date).exists():
            self._sealed_days.add(trade_date)
            logger.info("tick 存檔 %s 已有 parquet(已轉檔),本日不再開 jsonl", trade_date)
            return
        try:
            self._file_for(trade_date)
        except (OSError, ValueError) as exc:
            self._fail(trade_date, "開檔", exc)

    def seal_day(self, trade_date: str) -> None:
        """轉檔前放掉該日 handle(flush + 關)並封住:之後該日的列一律丟(計 `sealed_dropped`、
        該日首筆 WARNING 一次、`log_stats` 時 > 0 另印一行)。Windows 開著的檔刪不掉,子程序的
        「列數核對後刪 jsonl」會直接失敗;封住而不是重開,是因為重開會在 parquet 旁邊留下一份
        殘餘 jsonl,loader 永遠不讀它。09:00 前的簿更新本就不寫(`BOOK_OPEN_TIME`),所以封住後
        會丟的只有 13:45 之後(13:30 收盤)達錢的遲到殘影,以及「engine 整天沒換日」那種尾端情形
        —— 後者靠那一行丟棄計數看得到。"""
        if not self._enabled or self._closed:
            return
        if trade_date in self._files:
            self._close_file(trade_date)
        self._sealed_days.add(trade_date)

    def flush(self) -> None:
        """把緩衝寫進 OS(write syscall,不 fsync)。"""
        for day, fh in list(self._files.items()):
            try:
                fh.flush()
            except OSError as exc:
                self._fail(day, "flush", exc)
        self.flushes += 1

    def log_stats(self, day: str) -> None:
        """印當日那一行(字面 `STATS_FMT`);零筆也印,判準是「那行存在」。封住後丟棄 > 0 另印一行。

        `day` 是呼叫端的標籤(engine 傳 `_trade_date`、排程傳 `current_day`),計數器是自上次
        `open_day` 起的累計 —— 換日邊界遲到的舊日列會計進新日(round-1 F-04 知情接受:
        判準只看「行存在、寫入失敗 0」,不對帳列數)。
        """
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
        if self.sealed_dropped:
            logger.info(_SEALED_FMT, day, self.sealed_dropped)

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
            if self._now_fn().time() < BOOK_OPEN_TIME:
                self.books_preopen += 1  # 開盤前不存、不動基準(09:00 第一則簿必寫)
                return
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
        _put_levels(row, book.bids, _BID_KEYS, _BIDQ_KEYS)
        _put_levels(row, book.asks, _ASK_KEYS, _ASKQ_KEYS)
        return row

    # ---- 內部 ----

    def _write(self, trade_date: str, row: dict) -> bool:
        """一列進緩衝;該日已停寫 / 已封住 → False(不計數);OSError → 記失敗、該日停寫、False。"""
        if trade_date in self._failed_days:
            return False
        if trade_date in self._sealed_days:
            if trade_date not in self._sealed_warned:
                self._sealed_warned.add(trade_date)
                logger.warning("tick 存檔 %s 已轉檔封住,之後到達的列丟棄", trade_date)
            self.sealed_dropped += 1
            return False
        try:
            self._file_for(trade_date).write(json.dumps(row, ensure_ascii=False) + "\n")
        except (OSError, ValueError) as exc:
            self._fail(trade_date, "寫入", exc)
            return False
        return True

    def _file_for(self, trade_date: str) -> TextIO:
        """該日 handle,沒有就開(`open_day` 預開;停寫 / 封住日不會走到這裡)。可能拋 OSError。

        開既有檔時先接 `msg_seq`(檔尾最後一列完整列 +1 起跳),檔尾若是當機留下的半行先補
        一個換行把它隔開 —— 新列黏在半行後面 = 一行壞資料吃掉一列好資料。
        """
        fh = self._files.get(trade_date)
        if fh is None:
            self._dir.mkdir(parents=True, exist_ok=True)
            path = jsonl_path(self._dir, trade_date)
            self._msg_seq = max(self._msg_seq, tail_msg_seq(path))
            fh = self._opener(path)
            if _ends_without_newline(path):
                fh.write("\n")
            self._files[trade_date] = fh
        return fh

    def _fail(self, trade_date: str, stage: str, exc: Exception) -> None:
        """失敗的唯一處置:WARNING 一次、該日停寫、丟掉該日 handle。已停寫的日不再記。"""
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
            trade_date,
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


def _ends_without_newline(path: Path) -> bool:
    """既有非空檔的最後一個 byte 不是換行 = 上次當機留下半行。檔不在 / 空 → False。"""
    try:
        size = os.path.getsize(path)
        if size == 0:
            return False
        with open(path, "rb") as fh:
            fh.seek(size - 1)
            return fh.read(1) != b"\n"
    except OSError:
        return False


def _raw_str(value: object) -> str | None:
    """達錢原始欄位照存:欄缺 / null → None,其餘 `str()`(達錢哪天送 int 也不丟)。"""
    return None if value is None else str(value)
