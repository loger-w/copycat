# -*- coding: utf-8 -*-
"""#272 標準答案:用 copycat.book_replay.decode 讀外掛檔,對指定 (代號, 日期, 收到時刻) 算出
那一則的則號、五檔量,再把「我的委託 / 成交」(回看頁 payload 的 mo / f)照頁面規則算成每格該出現的
「委 n」/「成 n」。頁面的 DOM 要與這份逐格相符。

用法: python -X utf8 rp272_expected.py <out.json>  (情境寫在 CASES)
"""
import base64
import gzip
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, r"C:\side-project\copycat")
from copycat.book_replay import decode, parse_plugin_js  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
REVIEW = Path(r"C:\Users\USER\Documents\copycat-trading-review")
BOOK = REVIEW / "viewer-cdp-book"

blob = re.search(r'<script id="blob" type="text/plain">([A-Za-z0-9+/=]+)</script>', (REVIEW / "viewer-cdp.html").read_text(encoding="utf-8"))
assert blob
DATA = json.loads(gzip.decompress(base64.b64decode(blob.group(1))).decode("utf-8"))

# (代號, 日期, 收到時刻 hh:mm:ss.mmm 或 None = 用第 n 則) — 涵蓋掛著 / 刪掉 / 成交後 / 未知 / 市價
CASES = [
    ("3441", "2026-09-16", "09:03:32.500", "掛買 181.0 之後、成交之前"),
    ("3441", "2026-09-16", "09:03:34.000", "成交之後(委託該消失、成交該出現)"),
    ("3441", "2026-09-16", "09:04:42.000", "驗收:181 那一格當時的量"),
    ("3441", "2026-09-16", "09:06:00.000", "賣 181.5 掛著(09:05:52 送出、09:06:48 刪單)"),
    ("3441", "2026-09-16", "09:07:00.000", "賣 181.5 已刪單(該消失)"),
    ("3441", "2026-09-16", "09:09:30.000", "鎖漲停之後"),
    ("2426", "2026-09-16", "10:45:45.000", "同價兩筆各自成交"),
    ("2426", "2026-09-18", "10:30:00.000", "當日成交還沒補 → 委?"),
    ("6179", "2026-09-18", "12:00:00.000", "市價單不畫、限價單畫"),
    ("3026", "2026-09-16", "12:35:00.000", "同檔一買一賣都成交"),
]


def ms_of(t: str) -> int:
    h, m, rest = t.split(":")
    s, frac = rest.split(".")
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(frac)


def tick_milli(p: int) -> int:
    return 10 if p < 10000 else 50 if p < 50000 else 100 if p < 100000 else 500 if p < 500000 else 1000 if p < 1000000 else 5000


def fmt_px(p: int) -> str:
    tk = tick_milli(p)
    return f"{p / 1000:.{0 if tk >= 1000 else 1 if tk >= 100 else 2}f}"


out = []
for code, date, at, why in CASES:
    payload = parse_plugin_js((BOOK / date / f"{code}.js").read_text(encoding="utf-8"))
    R = decode(payload)
    recv = [f.recv_ms for f in R.frames]
    t = ms_of(at)
    i = 0 if t < recv[0] else max(k for k in range(len(recv)) if recv[k] <= t)
    now = recv[i]
    book = R.frames[i].book
    buy = {book[j]: book[5 + j] for j in range(5) if book[j] not in (None, 0)}  # 欄序 = BOOK_LEVEL_FIELDS
    sell = {book[10 + j]: book[15 + j] for j in range(5) if book[10 + j] not in (None, 0)}
    D = DATA["d"][code][date]
    me: dict[str, dict[str, int]] = {}
    for o in D.get("mo", []):
        if o[6] != "limit":
            continue
        t0, t1 = round(o[0] * 1000), (None if o[1] is None else round(o[1] * 1000))
        if t0 > now or (t1 is not None and t1 <= now):
            continue
        k = f"{'buy' if o[4] > 0 else 'sell'}@{round(o[2] * 1000)}"
        v = me.setdefault(k, {"ord": 0, "unk": 0, "fill": 0})
        v["ord"] += o[3]
        v["unk"] += 1 if o[5] == "未知" else 0
    for f in D["f"]:
        if round(f[0] * 1000) > now:
            continue
        k = f"{'buy' if f[3] > 0 else 'sell'}@{round(f[1] * 1000)}"
        me.setdefault(k, {"ord": 0, "unk": 0, "fill": 0})["fill"] += f[2]
    fill_idx = sorted({(0 if round(f[0] * 1000) < recv[0] else max(k for k in range(len(recv)) if recv[k] <= round(f[0] * 1000))) for f in D["f"]})
    out.append(dict(code=code, date=date, at=at, why=why, i=i, recv=now, fill_idx=fill_idx, fill_recv=[recv[k] for k in fill_idx],
                    buy={fmt_px(p): q for p, q in buy.items()}, sell={fmt_px(p): q for p, q in sell.items()},
                    me={k: v for k, v in sorted(me.items())},
                    mkt=sum(1 for o in D.get("mo", []) if o[6] != "limit")))
    print(f"{code} {date} {at} 第 {i + 1} 則  {why}")
    print(f"   我的格子: {out[-1]['me']}  市價單 {out[-1]['mkt']} 筆")

Path(sys.argv[1] if len(sys.argv) > 1 else "rp272_expected.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
