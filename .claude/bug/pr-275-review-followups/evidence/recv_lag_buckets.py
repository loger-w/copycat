"""F-10:一般盤中成交(排除 81 筆離群)recv − 達錢時刻的 100 ms 桶分布。"""

from __future__ import annotations

import collections

import pyarrow.parquet as pq

t = pq.read_table(
    "C:/side-project/copycat/data/ticks/20260916.parquet", columns=["ms", "recv_ns"]
)
ms = t["ms"].to_pylist()
recv = t["recv_ns"].to_pylist()
buckets: collections.Counter[int] = collections.Counter()
for m, r in zip(ms, recv, strict=True):
    lag = (r // 1_000_000 + 8 * 3_600_000) % 86_400_000 - m
    if m == 48_600_000 or lag < 0 or lag > 5_000:
        continue
    buckets[lag // 100 * 100] += 1
total = sum(buckets.values())
for start in sorted(buckets):
    print(
        f"{start:>5}–{start + 99:>5} ms: {buckets[start]:>7} ({buckets[start] / total * 100:4.1f}%)"
    )
print("total", total)
