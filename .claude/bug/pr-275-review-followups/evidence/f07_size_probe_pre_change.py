"""F-07 / F-08 事實探針(唯讀):09-16 tick 存檔逐檔重播,量 clock 去重能省多少、查真資料的 seq / side / ms 值域。

**只能對改格式前的碼跑**(讀 payload["clock"];本分支 F-07 之後該鍵已改名 anomalous)。2026-09-16 在 master
1c964d51 的主 tree 跑過一次(主 tree venv,import copycat 經 editable .pth 解析到主 tree;132 s),輸出抄錄於 f07_size_probe_pre_change.out.txt,
用來給 user 拍板 F-07。改格式後的等價量測 = size_old_vs_new.py(從新檔還原舊格式,總位元組數與本探針相同)。
"""

from __future__ import annotations

import collections
import json
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from copycat.book_replay import encode, plugin_js, replay_books
from copycat.ticks import _row_from_dict

DATA = Path("C:/side-project/copycat/data/ticks")
t0 = time.monotonic()
trade_t = pq.read_table(DATA / "20260916.parquet")
book_t = pq.read_table(DATA / "20260916-book.parquet")
print(
    f"read tables: trade {trade_t.num_rows} rows, book {book_t.num_rows} rows, {time.monotonic() - t0:.1f}s"
)

# ---- F-08 值域事實 ----
side_counts = collections.Counter(trade_t.column("side").to_pylist())
print("trade side values:", dict(side_counts))
for col in ("ms", "price_milli", "qty", "time"):
    print(f"trade null {col}:", trade_t.column(col).null_count)
all_seq = pa.concat_arrays(
    [
        trade_t.column("msg_seq").combine_chunks(),
        book_t.column("msg_seq").combine_chunks(),
    ]
)
print("msg_seq total", len(all_seq), "distinct", len(pc.unique(all_seq)))

# ---- F-07 大小 ----
codes = sorted(set(trade_t.column("code").to_pylist()) | set(book_t.column("code").to_pylist()))
tot = collections.Counter()
for code in codes:
    rows = [
        _row_from_dict(r)
        for t in (trade_t, book_t)
        for r in t.filter(pc.equal(t.column("code"), code)).to_pylist()
    ]
    day = replay_books(rows)[code]
    payload = encode(day)
    cur = len(plugin_js(payload))
    idx = payload["clock"][::2]
    kinds = payload["kind"]
    idx_set = set(idx)
    anom = [i for i, k in enumerate(kinds) if k == "t" and i not in idx_set]
    a1 = dict(payload)
    a1["clock"] = idx
    a2 = {k: (anom if k == "clock" else v) for k, v in payload.items()}
    no_clock = {k: v for k, v in payload.items() if k != "clock"}
    raw_clock = len(json.dumps(payload["clock"], separators=(",", ":")))
    tot["files"] += 1
    tot["frames"] += payload["n"]
    tot["trades"] += kinds.count("t")
    tot["clock_points"] += len(idx)
    tot["anom"] += len(anom)
    tot["cur"] += cur
    tot["a1_indices_only"] += len(plugin_js(a1))  # type: ignore[arg-type]
    tot["a2_anom_only"] += len(plugin_js(a2))  # type: ignore[arg-type]
    tot["no_clock"] += len(plugin_js(no_clock))  # type: ignore[arg-type]
    tot["raw_clock_json"] += raw_clock
    del rows, day, payload, a1, a2, no_clock

print(dict(tot))
for key in ("cur", "a1_indices_only", "a2_anom_only", "no_clock"):
    print(f"{key:>16}: {tot[key] / 1e6:6.2f} MB ({tot[key] / tot['cur'] * 100:5.1f}%)")
print(f"elapsed {time.monotonic() - t0:.1f}s")
