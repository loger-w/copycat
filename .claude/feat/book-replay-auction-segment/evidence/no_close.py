"""哪幾檔沒有收盤集合競價段(#273 驗證的誠實註腳)。"""

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, r"C:\side-project\copycat\.claude\worktrees\mod-auction-segment-273")

from copycat.book_replay import decode, parse_plugin_js  # noqa: E402

BOOK = Path(r"C:\Users\USER\Documents\copycat-trading-review\viewer-cdp-book")
CLOSE_FROM_MS = (13 * 3600 + 25 * 60) * 1000


def hhmmss(ms: int) -> str:
    return str(dt.timedelta(milliseconds=ms))[:12]


for date in sys.argv[1:]:
    for path in sorted(BOOK.joinpath(date).glob("*.js")):
        payload = parse_plugin_js(path.read_text(encoding="utf-8"))
        frames = decode(payload).frames
        ends = payload["trial"][1::2]
        if any(frames[e].recv_ms >= CLOSE_FROM_MS for e in ends):
            continue
        print(
            f"{date} {path.stem}:{len(frames)} 則,"
            f"收到時刻 {hhmmss(frames[0].recv_ms)}–{hhmmss(frames[-1].recv_ms)},段 {len(ends)}"
        )
