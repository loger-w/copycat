# -*- coding: utf-8 -*-
"""#272 payload 不變式(two-axis review round-1 C1 / C2 的釘子):
`mo` 每一列的結束時刻不得早於送出時刻;欄數 / 種類 / price_type / 委託序號值域固定;
「成交」那一列的結束時刻必須逐字等於「你的成交」清單裡同價同買賣的某一筆(兩邊同一把尺)。
非 0 離開碼 = 不變式破了。"""
import base64
import gzip
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
PAGE = Path(r"C:\Users\USER\Documents\copycat-trading-review\viewer-cdp.html")
m = re.search(r'<script id="blob" type="text/plain">([A-Za-z0-9+/=]+)</script>', PAGE.read_text(encoding="utf-8"))
assert m, "頁面裡找不到 payload blob"
DATA = json.loads(gzip.decompress(base64.b64decode(m.group(1))).decode("utf-8"))

KINDS = {"成交", "刪單", "未配到", "未知"}
bad_order, bad_kind, bad_shape, bad_fill = [], [], [], []
kinds: Counter[str] = Counter()
n = 0
for code, days in DATA["d"].items():
    for date, D in days.items():
        fills = {(round(f[0], 1), round(f[1] * 1000), f[3]) for f in D["f"]}
        for o in D.get("mo", []):
            n += 1
            if len(o) != 8:
                bad_shape.append((date, code, o))
                continue
            t0, t1, px, qty, side, kind, ptype, seq = o
            kinds[kind] += 1
            if t1 is not None and t1 < t0:
                bad_order.append((date, code, o))
            if kind not in KINDS or ptype not in {"limit", "market"} or not isinstance(seq, str):
                bad_kind.append((date, code, o))
            if kind == "成交" and (round(t1, 1), round(px * 1000), side) not in fills:
                bad_fill.append((date, code, o))

print(f"mo 共 {n} 列;種類 {dict(kinds)}")
print(f"結束早於送出 {len(bad_order)} 列(要 0)")
print(f"欄數不符 {len(bad_shape)} 列 / 值域不符 {len(bad_kind)} 列(都要 0)")
print(f"成交列的結束時刻對不上成交清單 {len(bad_fill)} 列(要 0)")
for lab, rows in (("結束早於送出", bad_order), ("欄數", bad_shape), ("值域", bad_kind), ("成交尺", bad_fill)):
    for r in rows[:5]:
        print("  ", lab, r)
sys.exit(1 if (bad_order or bad_shape or bad_kind or bad_fill) else 0)
