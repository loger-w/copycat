"""收盤集合競價段裡單格堆到最多張的是哪一檔哪一格(#273 docstring 的數字要自己量過)。"""

import datetime as dt

import pyarrow.parquet as pq

TP = dt.timezone(dt.timedelta(hours=8))
COLS = (
    ["code", "recv_ns", "trade_status"]
    + [f"bidq{i}" for i in range(5)]
    + [f"askq{i}" for i in range(5)]
)
for day in ("20260916", "20260917", "20260918"):
    t = pq.read_table(
        f"C:/side-project/copycat/data/ticks/{day}-book.parquet", columns=COLS
    ).to_pydict()
    best = (0, None, None, None)
    for i, ts in enumerate(t["trade_status"]):
        if ts != "1":
            continue
        tm = dt.datetime.fromtimestamp(t["recv_ns"][i] / 1e9, TP)
        if (tm.hour, tm.minute) < (13, 25):
            continue
        for side in ("bidq", "askq"):
            for lv in range(5):
                q = t[f"{side}{lv}"][i]
                if q and q > best[0]:
                    best = (q, t["code"][i], f"{side}{lv}", tm.strftime("%H:%M:%S"))
    print(day, "收盤集合競價段單格最大量:", best)
