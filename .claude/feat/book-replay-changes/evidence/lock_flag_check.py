"""#269 沉澱前核對:鎖停時達錢內外盤旗標的分布(寫 tc4-market-facts 前先數,不憑例子下「恆」)。

前一則五檔(跳過全空的則)= 賣方全空且買方第一檔是市價佇列(價 0)→ 鎖漲停;買方全空且賣方第一檔是市價佇列 → 鎖跌停。
數這兩種狀態下每筆成交的內外盤旗標。五檔 20 格欄序 = BOOK_LEVEL_FIELDS(買價 5、買量 5、賣價 5、賣量 5)。

用法:python lock_flag_check.py [外掛檔資料夾]
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

WORKTREE = str(Path(__file__).resolve().parents[4])
sys.path.insert(0, WORKTREE)

from copycat import book_replay as br  # noqa: E402

assert (br.__file__ or "").startswith(WORKTREE), br.__file__
assert br.BOOK_LEVEL_FIELDS[0] == "bid0" and br.BOOK_LEVEL_FIELDS[10] == "ask0", br.BOOK_LEVEL_FIELDS
root = Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\USER\Documents\copycat-trading-review\viewer-cdp-book")
for date_dir in sorted(p for p in root.iterdir() if p.is_dir()):
    flags: Counter[tuple[str, str]] = Counter()
    lots: Counter[tuple[str, str]] = Counter()
    examples: list[str] = []
    for f in sorted(date_dir.glob("*.js")):
        day = br.decode(br.parse_plugin_js(f.read_text(encoding="utf-8")))
        prev: tuple[int | None, ...] | None = None
        for i, frame in enumerate(day.frames):
            book = frame.book
            trade = frame.trade
            if trade is not None and prev is not None:
                bids, asks = prev[0:10], prev[10:20]
                state = (
                    "鎖漲停" if all(v is None for v in asks) and prev[0] == 0
                    else "鎖跌停" if all(v is None for v in bids) and prev[10] == 0
                    else None
                )
                if state is not None:
                    flags[(state, trade.side or "None")] += 1
                    lots[(state, trade.side or "None")] += trade.qty or 0
                    if state == "鎖漲停" and trade.side != "outer" and len(examples) < 5:
                        examples.append(f"{f.stem} 第 {i + 1} 則 {trade} 前一簿 買 {bids} 賣 {asks}")
            if any(v is not None for v in book):
                prev = book
    print(date_dir.name, "筆", dict(flags), "張", dict(lots))
    for line in examples:
        print("  鎖漲停非外盤例", line)
