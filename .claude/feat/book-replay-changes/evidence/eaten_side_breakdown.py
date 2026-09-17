"""#269 增量快篩:吃檔側別與內外盤相反的項目分類(eaten_side_check.py 的後續)。

分類(依序判定,先中先算):
- market_queue:吃的是市價佇列(檔位 0)—— 鎖停時市價排隊被成交,內外盤旗標看的是成交價對應哪一側
- both_sides:同一筆成交的吃檔兩側都有 —— 集合競價 / 暫緩撮合的撮合一次吃兩側
- auction_time:成交時刻 < 09:00:30 或 ≥ 13:25:00(開收盤集合競價)
- after_cleared:同檔當日出現過五檔全空(暫緩撮合)之後的成交
- other:以上皆非(連續交易中單側相反)—— 印例子與前後幾則五檔
用法:python eaten_side_breakdown.py [外掛檔資料夾]
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

WORKTREE = r"C:\side-project\copycat\.claude\worktrees\feat-book-replay-changes"
sys.path.insert(0, WORKTREE)

from copycat import book_replay as br  # noqa: E402

root = Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\USER\Documents\copycat-trading-review\viewer-cdp-book-269")
EXPECTED = {"outer": "ask", "inner": "bid"}
OPEN_END, CLOSE_START = 9 * 3600_000 + 30_000, 13 * 3600_000 + 25 * 60_000


def hms(ms: int | None) -> str:
    if ms is None:
        return "—"
    s = ms // 1000
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


for date_dir in sorted(p for p in root.iterdir() if p.is_dir()):
    lots: Counter[str] = Counter()
    items: Counter[str] = Counter()
    codes: Counter[str] = Counter()
    shown = 0
    for f in sorted(date_dir.glob("*.js")):
        day = br.decode(br.parse_plugin_js(f.read_text(encoding="utf-8")))
        seen_cleared = False
        for i, frame in enumerate(day.frames):
            if all(v is None for v in frame.book):
                seen_cleared = True
            trade = frame.trade
            if trade is None or not frame.eaten:
                continue
            want = EXPECTED.get(trade.side or "")
            if want is None:
                continue
            sides = {eat.side for eat in frame.eaten}
            for eat in frame.eaten:
                if eat.side == want:
                    continue
                if eat.level == 0:
                    key = "market_queue"
                elif len(sides) > 1:
                    key = "both_sides"
                elif trade.ms is not None and (trade.ms < OPEN_END or trade.ms >= CLOSE_START):
                    key = "auction_time"
                elif seen_cleared:
                    key = "after_cleared"
                else:
                    key = "other"
                lots[key] += eat.qty
                items[key] += 1
                if key == "other":
                    codes[f.stem] += eat.qty
                    if shown < 6:
                        shown += 1
                        print(f"  other {f.stem} 第 {i + 1} 則 {hms(trade.ms)} {trade} 吃檔 {frame.eaten}")
                        for j in range(max(0, i - 3), min(len(day.frames), i + 3)):
                            g = day.frames[j]
                            print(
                                f"      第 {j + 1} 則 {g.kind} 收到 {g.recv_ms} 成交 {g.trade}"
                                f" 買 {g.book[0:10]} 賣 {g.book[10:20]}"
                            )
                            print(f"        變動 {g.changes}")
    print(date_dir.name, "張", dict(lots), "項", dict(items))
    print("  other 前幾檔", codes.most_common(8))
