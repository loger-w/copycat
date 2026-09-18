"""#273 AC4:回看頁 payload 改版前後,舊交易日的資料(尤其逐筆 `tt` 的內外盤欄)必須逐位元組相同。

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
old_days = tot = diff = 0
tick_rows = 0
for code, days in before["d"].items():
    for date, row in days.items():
        if date >= BOOK_FROM:
            continue
        old_days += 1
        new = after["d"].get(code, {}).get(date)
        tot += 1
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
raise SystemExit(1 if diff else 0)
