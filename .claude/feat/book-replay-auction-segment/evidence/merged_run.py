"""哪幾檔的集合競價段是「13:25 前就開始、一路連到收盤」(F-4 的標籤要驗的那一種)。"""

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
        for start, end in zip(
            payload["trial"][::2], payload["trial"][1::2], strict=True
        ):
            a, z = frames[start].recv_ms, frames[end].recv_ms
            if a < CLOSE_FROM_MS <= z:
                print(f"{date} {path.stem}:第 {start}–{end} 則,{hhmmss(a)}–{hhmmss(z)}")
