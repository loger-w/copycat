# -*- coding: utf-8 -*-
"""從產好的回看頁抽出 payload,印每天的「我的委託」與成交配對結果(#272 驗收用)。"""
import base64
import gzip
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
PAGE = Path(r"C:\Users\USER\Documents\copycat-trading-review\viewer-cdp.html")
m = re.search(r'<script id="blob" type="text/plain">([A-Za-z0-9+/=]+)</script>', PAGE.read_text(encoding="utf-8"))
assert m, "頁面裡找不到 payload blob"
DATA = json.loads(gzip.decompress(base64.b64decode(m.group(1))).decode("utf-8"))


def tt(sec):
    s = int(sec)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


rows = []
for code, days in DATA["d"].items():
    for date, D in days.items():
        for o in D.get("mo", []):
            rows.append((date, tt(o[0]), code, "買" if o[4] > 0 else "賣", o[2], o[3], o[6], o[5], (tt(o[1]) if o[1] is not None else "—")))
rows.sort()
want = sys.argv[1] if len(sys.argv) > 1 else ""
for r in rows:
    if want and not r[0].startswith(want):
        continue
    print(f"{r[0]} {r[1]} {r[2]} {r[3]} {r[4]:>8} × {r[5]} 張 {r[7]:<4} {r[8]}  ({r[6]})")
print(f"合計 {len(rows)} 筆委託(全部日期);日期數 {len({r[0] for r in rows})}")
for date in sorted({r[0] for r in rows}):
    ds = [r for r in rows if r[0] == date]
    print(f"  {date}: {len(ds)} 筆 — " + "、".join(f"{k} {sum(1 for x in ds if x[7] == k)}" for k in ("成交", "刪單", "未配到", "未知") if any(x[7] == k for x in ds)))
