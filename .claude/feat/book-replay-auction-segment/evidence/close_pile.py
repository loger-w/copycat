"""集合競價**段內**單格堆到最多張的是哪一檔哪一格(#273 模組說明的數字要自己量過)。

2026-09-19 pr-281 review #7 收修:原版有兩個窄化 —— gate 在 `(tm.hour, tm.minute) >= (13, 25)`、
且只讀 `<日>-book.parquet`。但它撐的那句話說的是「**段內**」,而段照 #273 的定義含處置股整天的
分盤撮合、盤中暫緩撮合,也含帶試撮狀態的**成交**列。兩個窄化都只在量測端,宣稱端沒有。

這版把兩個窄化都拿掉(只依 `trade_status == "1"` 判段,成交 parquet 一起掃)。**數字沒有變**
(09-16 47,033 / 09-17 27,806 / 09-18 29,675),但 09-18 的裕度只有 375 張 —— 13:25 前的段內最大
是 29,300,全段最大 29,675。所以連「13:25 前的段內最大」一起印出來留底,下次有人想再窄化時看得到。

用法:python close_pile.py            # 09-16 / 09-17 / 09-18
      python close_pile.py 20260916  # 指定日
"""

import datetime as dt
import sys
from typing import NamedTuple

import pyarrow.compute as pc
import pyarrow.parquet as pq

TP = dt.timezone(dt.timedelta(hours=8))
TRIAL_STATUS = "1"  # copycat.book_replay._TRIAL_STATUS
CLOSE_FROM = (13, 25)
TICKS = "C:/side-project/copycat/data/ticks"
# (檔名後綴, 這一份是什麼):成交列也可能帶試撮狀態(7772),不能只掃簿
SOURCES = (("", "成交"), ("-book", "簿"))
COLS = (
    ["code", "recv_ns", "trade_status"]
    + [f"bidq{i}" for i in range(5)]
    + [f"askq{i}" for i in range(5)]
)


class Peak(NamedTuple):
    """段內最大的那一格。歸檔的 .txt 直接印它,所以欄位名要自述(pr-281 two-axis Std-1)。"""

    qty: int
    code: str | None
    cell: str | None  # bidq0 = 買一、askq0 = 賣一,以此類推
    at: str | None  # 收到時刻 HH:MM:SS
    row_kind: str | None  # 成交 / 簿


def scan(day: str) -> None:
    best = before_close = Peak(0, None, None, None, None)
    rows = 0
    for suffix, row_kind in SOURCES:
        table = pq.read_table(f"{TICKS}/{day}{suffix}.parquet", columns=COLS)
        trial = table.filter(pc.equal(table["trade_status"], TRIAL_STATUS)).to_pydict()
        rows += len(trial["code"])
        for i, ns in enumerate(trial["recv_ns"]):
            tm = dt.datetime.fromtimestamp(ns / 1e9, TP)
            for side in ("bidq", "askq"):
                for lv in range(5):
                    q = trial[f"{side}{lv}"][i]
                    if not q:
                        continue
                    hit = Peak(q, trial["code"][i], f"{side}{lv}", tm.strftime("%H:%M:%S"), row_kind)
                    if q > best.qty:
                        best = hit
                    if (tm.hour, tm.minute) < CLOSE_FROM and q > before_close.qty:
                        before_close = hit
    print(f"{day} 段內列 {rows:,}(成交 + 簿)")
    print(f"   全段單格最大量:{best}")
    print(f"   其中 13:25 前的最大:{before_close}")


for arg in sys.argv[1:] or ["20260916", "20260917", "20260918"]:
    scan(arg)
