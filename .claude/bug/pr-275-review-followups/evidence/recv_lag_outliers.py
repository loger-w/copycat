"""F-09 / F-10:排除 81 筆離群(收盤撮合 13:30:00.000、負值、> 5 s 非收盤)後的一般盤中成交統計。"""

from __future__ import annotations

import pyarrow.parquet as pq

t = pq.read_table(
    "C:/side-project/copycat/data/ticks/20260916.parquet",
    columns=["code", "ms", "recv_ns", "time", "trade_status"],
)
c = {k: t[k].to_pylist() for k in t.column_names}
lags = [
    ((c["recv_ns"][i] // 1_000_000 + 8 * 3_600_000) % 86_400_000 - c["ms"][i], i)
    for i in range(t.num_rows)
]


def pct(values: list[int], p: float) -> int:
    k = max(0, min(len(values) - 1, round(p / 100 * len(values) + 0.5) - 1))
    return values[k]


every = sorted(lag for lag, _ in lags)
print(
    "all n",
    len(every),
    "min",
    every[0],
    "max",
    every[-1],
    "p50/p90/p99",
    pct(every, 50),
    pct(every, 90),
    pct(every, 99),
)
closing = sorted(lag for lag, i in lags if c["ms"][i] == 48_600_000)
neg = [(lag, c["code"][i], c["time"][i]) for lag, i in lags if lag < 0]
big = [
    (lag, c["code"][i], c["time"][i], c["trade_status"][i])
    for lag, i in lags
    if lag > 5_000 and c["ms"][i] != 48_600_000
]
print(
    "closing n",
    len(closing),
    "min",
    closing[0],
    "max",
    closing[-1],
    ">5s",
    sum(1 for x in closing if x > 5000),
)
print("negative", neg)
print(">5s non-closing", big)
out_ids = {i for lag, i in lags if c["ms"][i] == 48_600_000 or lag < 0 or lag > 5_000}
normal = sorted(lag for lag, i in lags if i not in out_ids)
print(
    "normal n",
    len(normal),
    "excluded",
    len(out_ids),
    "min",
    normal[0],
    "max",
    normal[-1],
    "p50/p90/p99",
    pct(normal, 50),
    pct(normal, 90),
    pct(normal, 99),
)
print(
    "7772 trades",
    sum(1 for x in c["code"] if x == "7772"),
    "status values",
    sorted(set(c["trade_status"])),
)
print("normal > 1137:", sum(1 for x in normal if x > 1137), "top5", normal[-5:])
