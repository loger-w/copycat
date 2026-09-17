"""#268 對照:Python decode 當標準答案,產出隨機時刻的階梯期望值,給頁面比對。"""

import bisect
import json
import random
import sys
from pathlib import Path

from copycat.book_replay import BOOK_LEVEL_FIELDS as F
from copycat.book_replay import decode, parse_plugin_js

D = Path(r"C:\Users\USER\Documents\copycat-trading-review\viewer-cdp-book\2026-09-16")
OUT = Path(sys.argv[1])
rng = random.Random(268)
codes = ["2426", "1815", "3441", "8064", "2344", "6770"]


def hms(ms):
    s = ms // 1000
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


out = []
for c in codes:
    r = decode(parse_plugin_js((D / f"{c}.js").read_text(encoding="utf-8")))
    fr = r.frames
    recv = [f.recv_ms for f in fr]
    ts = [recv[0], recv[-1]] + [rng.randint(recv[0], recv[-1]) for _ in range(28)]
    ts += [f.recv_ms for f in fr if f.anomalous_trade]
    for t in ts:
        i = bisect.bisect_right(recv, t) - 1
        f = fr[i]
        b = dict(zip(F, f.book))
        buy = {str(b[f"bid{l}"]): b[f"bidq{l}"] for l in range(5) if b[f"bid{l}"]}
        sell = {str(b[f"ask{l}"]): b[f"askq{l}"] for l in range(5) if b[f"ask{l}"]}
        mkt = sum(b[f"bid{l}"] == 0 for l in range(5)) + sum(
            b[f"ask{l}"] == 0 for l in range(5)
        )
        px = next(
            (
                g.trade.price_milli
                for g in reversed(fr[: i + 1])
                if g.trade and g.trade.price_milli
            ),
            None,
        )
        if f.clock_ms is None:
            lab = f"首筆成交前第 {f.after} 則"
        else:
            lab = f"成交 {hms(f.clock_ms)}" + (
                "" if f.after == 0 else f" 之後第 {f.after} 則"
            )
        out.append(dict(c=c, t=t, i=i, lab=lab, buy=buy, sell=sell, mkt=mkt, px=px))
OUT.write_text(
    json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
)
print(
    len(out),
    "with market queue:",
    sum(o["mkt"] > 0 for o in out),
    "1815 anomalous label:",
    [o for o in out if o["c"] == "1815"][-1]["lab"],
)
