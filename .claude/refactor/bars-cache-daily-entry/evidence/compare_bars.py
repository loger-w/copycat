"""兩台側車(master vs worktree)同請求回應 diff。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

A, B = "http://127.0.0.1:8731", "http://127.0.0.1:8732"
PATHS = [
    "/api/stock/bars/2330?tf=D",
    "/api/stock/bars/2330?tf=D",  # 第二發:memo hit
    "/api/stock/bars/IX0001?tf=D",
    "/api/market/bars/TWSE?tf=D",
    "/api/market/bars/TWSE?tf=D",  # memo hit,tag 由 cache 還原
    "/api/market/bars/TWSE?tf=W",
    "/api/market/bars/TWSE?tf=M",
    "/api/stock/bars/9999?tf=D",  # 未知碼(fake 一樣回資料;驗鍵隔離)
]


def get(base: str, path: str) -> tuple[int, object]:
    try:
        with urllib.request.urlopen(base + path, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


all_ok = True
for p in PATHS:
    sa, ba = get(A, p)
    sb, bb = get(B, p)
    same = (sa, ba) == (sb, bb)
    all_ok &= same
    extra = ""
    if isinstance(ba, dict):
        meta = ba.get("meta", {})
        extra = f" bars={len(ba.get('bars', []))} meta={json.dumps(meta, ensure_ascii=False)}"
    print(f"{'SAME' if same else 'DIFF'} {sa}/{sb} {p}{extra}")
    if not same:
        print("  A:", json.dumps(ba, ensure_ascii=False)[:400])
        print("  B:", json.dumps(bb, ensure_ascii=False)[:400])
print("RESULT:", "ALL SAME" if all_ok else "MISMATCH")
