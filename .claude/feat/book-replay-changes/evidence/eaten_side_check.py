"""#269 review 後增量快篩:吃檔的側別與成交內外盤是否一致(外盤吃賣方、內盤吃買方)。

引擎扣成交只比價格不比側別(`_absorb`),被擠出價位的期間成交也只比價格(`_SideView.count_trade`,
買方那一側先走);理論上一致的五檔裡同一價位不會同時是買方與賣方的價位,這支用真資料數反例。
讀暫存 v2 外掛檔(copycat decode 解回),不讀 tick 存檔。

用法:python eaten_side_check.py [外掛檔資料夾]
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

WORKTREE = r"C:\side-project\copycat\.claude\worktrees\feat-book-replay-changes"
sys.path.insert(0, WORKTREE)

from copycat import book_replay as br  # noqa: E402

assert (br.__file__ or "").startswith(WORKTREE), br.__file__

root = Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\USER\Documents\copycat-trading-review\viewer-cdp-book-269")
EXPECTED = {"outer": "ask", "inner": "bid"}
for date_dir in sorted(p for p in root.iterdir() if p.is_dir()):
    counts: Counter[str] = Counter()
    examples: list[str] = []
    for f in sorted(date_dir.glob("*.js")):
        day = br.decode(br.parse_plugin_js(f.read_text(encoding="utf-8")))
        for i, frame in enumerate(day.frames):
            if frame.trade is None:
                continue
            counts["成交則"] += 1
            want = EXPECTED.get(frame.trade.side or "")
            for eat in frame.eaten:
                key = "中性" if want is None else "一致" if eat.side == want else "相反"
                counts[f"吃檔項_{key}"] += 1
                counts[f"張_{key}"] += eat.qty
                if key == "相反" and len(examples) < 8:
                    examples.append(f"{f.stem} 第 {i + 1} 則 {frame.trade} 吃檔 {frame.eaten}")
    print(date_dir.name, dict(counts))
    for line in examples:
        print("  相反例", line)
