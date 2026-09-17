"""#268 橫條基準(user 2026-09-17 拍板):收到時刻 13:25 前、價 > 0 的最大單格量;對照頁面說明列印出的值。"""

import sys
from pathlib import Path

from copycat.book_replay import BOOK_LEVEL_FIELDS as F
from copycat.book_replay import decode, parse_plugin_js

D = Path(r"C:\Users\USER\Documents\copycat-trading-review\viewer-cdp-book\2026-09-16")
END = 13 * 3600_000 + 25 * 60_000
for code in sys.argv[1:]:
    r = decode(parse_plugin_js((D / f"{code}.js").read_text(encoding="utf-8")))
    before = day = 0
    for fr in r.frames:
        b = dict(zip(F, fr.book))
        for side, qty in (("bid", "bidq"), ("ask", "askq")):
            for level in range(5):
                q = b[f"{qty}{level}"]
                if (b[f"{side}{level}"] or 0) > 0 and q is not None:
                    day = max(day, q)
                    if fr.recv_ms < END:
                        before = max(before, q)
    print(code, "13:25 前", before or day, "全天", day)
