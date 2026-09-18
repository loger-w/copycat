"""#269 量化:播放時中間欄會不會漏則(review S-04)。

照回看頁 rpTick:每幀(60 fps,16.7 ms)把時間軸推進 16.7 ms × 速度,取收到時刻 ≤ t 的最後一則重畫。
整天播完,數有幾則從沒出現在任何一幀的中間欄(= 播放時看不到,只能逐則步進)。兩種中間欄:
- 固定窗 N:列到這一則為止最近 N 則(只看則號)
- 跨則補齊 cap C:列「上次畫到的下一則 → 這一則」全部(至少 12 則,至多 C 則;要記上次畫到哪一則)
v2 暫存外掛檔的 recv 就是頁面用的時間軸。

用法:python playback_window_coverage.py <日期> [代號,…] [外掛檔資料夾]
"""

from __future__ import annotations

import bisect
import sys
from pathlib import Path

WORKTREE = str(Path(__file__).resolve().parents[4])
sys.path.insert(0, WORKTREE)

from copycat import book_replay as br  # noqa: E402

date = sys.argv[1]
BOOKDIR = Path(
    sys.argv[3]
    if len(sys.argv) > 3
    else r"C:\Users\USER\Documents\copycat-trading-review\viewer-cdp-book"
)
codes = (
    sys.argv[2].split(",")
    if len(sys.argv) > 2
    else sorted(p.stem for p in (BOOKDIR / date).glob("*.js"))
)
if not codes:
    # pr-279 review F-24:資料夾/日期給錯時 codes 是空的,totals 全部停在初值,
    # 最後 missed / n 會除以零 —— 先在這裡擋下來,講清楚是哪個資料夾找不到檔。
    sys.exit(f"停:{BOOKDIR / date} 底下沒有 .js 外掛檔,檢查資料夾與日期(用法見檔頭 docstring)")
FRAME_MS = 1000 / 60
SPEEDS = (1, 2, 5, 10)
VARIANTS = [("固定窗", 12), ("固定窗", 30), ("固定窗", 60), ("跨則補齊", 60), ("跨則補齊", 200)]

totals = {
    (v, s): [0, 0, "", 0.0, 0] for v in VARIANTS for s in SPEEDS
}  # missed, n, worst code, worst rate, max span
for code in codes:
    payload = br.parse_plugin_js((BOOKDIR / date / f"{code}.js").read_text(encoding="utf-8"))
    recv, acc = [], 0
    for step in payload["recv"]:
        acc += step
        recv.append(acc)
    n = len(recv)
    for speed in SPEEDS:
        draws = []
        t, prev = recv[0], -1
        while True:
            i = bisect.bisect_right(recv, t) - 1
            if i != prev:
                draws.append(i)
                prev = i
            if t >= recv[-1]:
                break
            t = min(recv[-1], t + FRAME_MS * speed)
        for kind, size in VARIANTS:
            covered = bytearray(n)
            last = -1
            span_max = 0
            for i in draws:
                if kind == "固定窗":
                    lo = max(0, i - size + 1)
                else:
                    span = i - last
                    span_max = max(span_max, span)
                    lo = max(0, i - max(12, min(span, size)) + 1)
                covered[lo : i + 1] = b"\x01" * (i + 1 - lo)
                last = i
            missed = n - sum(covered)
            tot = totals[((kind, size), speed)]
            tot[0] += missed
            tot[1] += n
            if n and missed / n > tot[3]:
                tot[2], tot[3] = code, missed / n
            tot[4] = max(tot[4], span_max)
for (variant, speed), (missed, n, worst, rate, span) in totals.items():
    extra = f",單幀最多跨 {span:,} 則" if variant[0] == "跨則補齊" else ""
    print(
        f"{date} {variant[0]} {variant[1]:>3} {speed:>2}x:漏 {missed:>7,} / {n:,} = {missed / n * 100:6.3f}%(最多 {worst} {rate * 100:5.2f}%){extra}"
    )
