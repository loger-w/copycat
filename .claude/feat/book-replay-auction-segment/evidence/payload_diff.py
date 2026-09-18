"""#273 AC4:回看頁 payload 改版前後,舊交易日的資料(尤其逐筆 `tt` 的內外盤欄)必須語意逐鍵相同。

兩邊都先經 payload_dump.py 的 json.dumps(sort_keys=True, indent=0) 正規化再 loads 回來比,所以比的是
語意相等而不是位元組相等 —— 對 AC4(內外盤判定未被更動)語意相等才是對的尺(2026-09-19 pr-281 review #5)。

用法:python payload_diff.py <before.json> <after.json>
"""

import json
import sys
from pathlib import Path

before = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
after = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))

added = sorted(set(after) - set(before))
removed = sorted(set(before) - set(after))
changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
print("新增鍵:", added)
print("刪掉的鍵:", removed)
print("值變了的鍵:", changed)
print("bookdays =", after.get("bookdays"), " bookdir =", after.get("bookdir"))

BOOK_FROM = min(after.get("bookdays") or ["9999-99-99"])
old_days = diff = 0
tick_rows = 0
for code, days in before["d"].items():
    for date, row in days.items():
        if date >= BOOK_FROM:
            continue
        old_days += 1
        new = after["d"].get(code, {}).get(date)
        tick_rows += len(row.get("tt") or [])
        if new != row:
            diff += 1
            keys = sorted(
                k for k in set(row) | set(new or {}) if (new or {}).get(k) != row.get(k)
            )
            print(f"  差異 {code} {date}:{keys}")
print(
    f"舊交易日(< {BOOK_FROM})股票日 {old_days}、逐筆列 {tick_rows:,}:不同的 {diff} 個"
)
# gate 要蓋住報告引用的那三行,不只 per-day 迴圈(2026-09-19 pr-281 review #4)。added 刻意不進
# gate —— 新增鍵是這次要的。`d` 在這裡是 catch-all:任一股票日不同就進 changed,所以「只在 after
# 出現的舊股票日」也擋得住,代價是**拿兩份天數不同的 dump 來比會紅**,而那是 AC4 不在乎的理由
# (印出來的「值變了的鍵」會有 d,人眼分得出來)。這支的用法是「同一批資料、改版前後」,不是跨期比對。
raise SystemExit(1 if (diff or removed or changed) else 0)
