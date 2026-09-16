"""F-08 新檢查會不會誤擋真資料(唯讀):兩個 parquet 的 msg_seq 是否全不重複、最小值;成交內外盤值域;成交欄 null 數。"""

from __future__ import annotations

import collections
import sys

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

data = sys.argv[1] if len(sys.argv) > 1 else "C:/side-project/copycat/data/ticks"
trade = pq.read_table(
    f"{data}/20260916.parquet", columns=["msg_seq", "side", "ms", "price_milli", "qty", "time"]
)
book = pq.read_table(f"{data}/20260916-book.parquet", columns=["msg_seq"])
seq = pa.concat_arrays([trade["msg_seq"].combine_chunks(), book["msg_seq"].combine_chunks()])
print(f"msg_seq 則數 {len(seq)}、相異 {len(pc.unique(seq))}、最小 {pc.min(seq).as_py()}")  # type: ignore[attr-defined]
print("成交內外盤:", dict(collections.Counter(trade["side"].to_pylist())))
print(
    "成交欄 null:", {c: trade[c].null_count for c in ("ms", "price_milli", "qty", "time", "side")}
)
