"""盤後把當日 tick jsonl 壓成兩個 parquet(spec #257 T4)。

入口 `compact_day`(CLI `ticks-compact` 與測試 S2 共用):讀 jsonl → 依 `kind` 分流 → 成交以
`(code, cum_vol)` 去重保首見(同日重啟後達錢重送最後一筆)→ 壞 JSON 行跳過計數 → 兩個
parquet(zstd;成交 `<YYYYMMDD>.parquet`、簿 `<YYYYMMDD>-book.parquet`,皆依
`(code, msg_seq)` 排序 —— 同檔連續區塊;`msg_seq` 同日重啟自檔尾接續,不需牆鐘)→
**讀回列數 = 去重後列數才刪 jsonl**(寫一半的檔不得把原始資料帶走)。

pyarrow 只在 extras `[ticks]`,本模組只在函式內 import;server 進程永遠不 import 這裡
(T5 以子程序呼叫 CLI)。
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from copycat.ticks import BOOK_FIELDS, TRADE_FIELDS, book_parquet_path, jsonl_path, parquet_path

__all__ = [
    "CompactFailed",
    "CompactRefused",
    "CompactResult",
    "compact_day",
    "format_compact_line",
]

logger = logging.getLogger(__name__)


class CompactRefused(Exception):
    """前置不成立(jsonl 不存在 / 非交易日):零檔案、CLI exit 2。"""


class CompactFailed(Exception):
    """轉檔中途失敗(讀回列數對不上):jsonl 保留、壞 parquet 刪除、CLI exit 1。"""


@dataclass(frozen=True, slots=True)
class CompactResult:
    jsonl_rows: int  # 含壞行
    trades: int  # 去重後成交列(= 成交 parquet 列數)
    books: int  # 簿列(= 簿 parquet 列數)
    dups: int  # (code, cum_vol) 重複而丟掉的成交列
    bad_lines: int  # JSON 解不開 / 形狀不對的行
    secs: float
    mbytes: float  # 兩個 parquet 合計


def format_compact_line(day: _dt.date, r: CompactResult) -> str:
    """每日一行的字面 = 盤後判準(CLAUDE.md §4;`grep "tick 轉檔"`,壞行應為 0)。"""
    return (
        f"tick 轉檔 {day.isoformat()}:jsonl {r.jsonl_rows} 列 → 成交 {r.trades} 列 + 簿 {r.books} 列"
        f"(去重 {r.dups}、壞行 {r.bad_lines}),耗時 {r.secs:.1f} 秒,{r.mbytes:.1f} MB"
    )


def _parquet_rows(path: Path) -> int:
    """讀回列數(metadata,不載整表)。測試以 monkeypatch 注入「對不上」。"""
    import pyarrow.parquet as pq

    return pq.read_metadata(path).num_rows


def _sort_key(row: dict[str, Any]) -> tuple[str, int]:
    """spec 的 `(code, msg_seq)`:寫入端同日重啟自檔尾接續 `msg_seq`,不需要牆鐘救援。"""
    return (row["code"], row["msg_seq"])


def _well_formed(row: object) -> bool:
    """形狀閘:是物件、`kind` 在值域、排序鍵與去重鍵齊全;其餘欄缺就是 parquet 的 null。"""
    if not isinstance(row, dict) or row.get("kind") not in ("trade", "book"):
        return False
    needed = ("code", "recv_ns", "msg_seq") + (("cum_vol",) if row["kind"] == "trade" else ())
    return all(k in row for k in needed)


def compact_day(
    day: _dt.date, data_dir: Path, *, is_trading_day: Callable[[_dt.date], bool]
) -> CompactResult:
    """一天的 jsonl → 兩個 parquet;成功才刪 jsonl。例外語意見 `CompactRefused` / `CompactFailed`。"""
    src = jsonl_path(data_dir, day.isoformat())
    if not is_trading_day(day):
        raise CompactRefused(f"{day} 是非交易日")
    if not src.exists():
        raise CompactRefused(f"jsonl 不存在:{src}")
    existing = parquet_path(data_dir, day.isoformat())
    if existing.exists():
        # round-1 Spec F-01:已轉檔的日再轉 = 用殘餘 jsonl(常是盤後重啟預開的空檔)蓋掉真 parquet,
        # 「列數核對」對空對空無效。要重轉先刪 parquet —— 訊息要講清楚。
        raise CompactRefused(f"parquet 已在({existing.name}),已轉檔;要重轉先刪 parquet")
    started = time.monotonic()
    trades: list[dict[str, Any]] = []
    books: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    total = dups = bad = 0
    with src.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            if not _well_formed(row):
                bad += 1
                continue
            if row["kind"] == "trade":
                key = (row["code"], row["cum_vol"])
                if key in seen:
                    dups += 1
                    continue
                seen.add(key)
                trades.append(row)
            else:
                books.append(row)
    trades.sort(key=_sort_key)
    books.sort(key=_sort_key)

    trade_out = parquet_path(data_dir, day.isoformat())
    book_out = book_parquet_path(data_dir, day.isoformat())
    # 簿檔**先**落地、成交檔最後(pr-263 F-02):CLI / 排程 / loader 三處都以「成交 parquet 存在」當
    # 已轉檔判準,它必須等於「兩檔都寫完」—— 被 kill 在兩次 replace 之間才不會卡成「已轉檔但簿列
    # 永遠讀不到」
    _write_parquet(book_out, books, BOOK_FIELDS)
    _write_parquet(trade_out, trades, TRADE_FIELDS)
    got = (_parquet_rows(trade_out), _parquet_rows(book_out))
    if got != (len(trades), len(books)):
        _rollback(trade_out, book_out)
        raise CompactFailed(
            f"讀回列數對不上(成交 {got[0]} / 簿 {got[1]},預期 {len(trades)} / {len(books)}),jsonl 保留"
        )
    mbytes = (trade_out.stat().st_size + book_out.stat().st_size) / 1_000_000
    try:
        src.unlink()
    except OSError as exc:
        # pr-263 F-03:Windows 上 jsonl 被別的 process 開著(server 未 seal 就手動重跑)會在這一步
        # PermissionError;parquet 已落地的話之後每次重跑都撞「parquet 已在」exit 2 —— 回滾成可重入
        _rollback(trade_out, book_out)
        raise CompactFailed(
            f"刪 jsonl 失敗({exc}),parquet 已回滾、jsonl 保留;server 跑著請等 13:45 排程"
        ) from exc
    return CompactResult(
        jsonl_rows=total,
        trades=len(trades),
        books=len(books),
        dups=dups,
        bad_lines=bad,
        secs=time.monotonic() - started,
        mbytes=mbytes,
    )


def _rollback(*paths: Path) -> None:
    """失敗收尾:兩個 parquet 與殘留 `.tmp` 都拿掉,讓狀態回到「只有 jsonl」可重入。"""
    for p in paths:
        p.unlink(missing_ok=True)
        p.with_suffix(p.suffix + ".tmp").unlink(missing_ok=True)


def _write_parquet(path: Path, rows: list[dict[str, Any]], fields: tuple[str, ...]) -> None:
    """欄序固定、schema 明寫(空表也有型別);先寫 `.tmp` 再 rename,不留半成品當正式檔。"""
    import pyarrow as pa
    import pyarrow.parquet as pq

    schema = pa.schema([(name, _arrow_type(name)) for name in fields])
    columns = {name: [row.get(name) for row in rows] for name in fields}
    table = pa.Table.from_pydict(columns, schema=schema)
    tmp = path.with_suffix(path.suffix + ".tmp")
    pq.write_table(table, tmp, compression="zstd")
    os.replace(tmp, path)


_STRING_FIELDS = frozenset(
    {"kind", "code", "trade_date", "precise_time", "trade_status", "time", "flag", "side"}
)
_INT64_FIELDS = frozenset({"msg_seq", "recv_ns", "ms", "cum_vol", "seq"})


def _arrow_type(name: str) -> Any:
    import pyarrow as pa

    if name in _STRING_FIELDS:
        return pa.string()
    if name in _INT64_FIELDS:
        return pa.int64()
    return pa.int32()  # 五檔價(毫元)/ 量(張)/ price_milli / qty
