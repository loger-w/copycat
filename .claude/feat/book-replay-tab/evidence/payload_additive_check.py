"""#268 追加驗證:新回看頁 payload 扣掉「非群組(簿重播)」的新增後,與改前備份逐位元組相同(55 檔資料與研究統計未動)。"""

import base64
import gzip
import json
from pathlib import Path

ROOT = Path(r"C:\Users\USER\Documents\copycat-trading-review")


def payload(name):
    html = (ROOT / name).read_text(encoding="utf-8")
    mark = '<script id="blob" type="text/plain">'
    s = html.index(mark) + len(mark)
    return json.loads(gzip.decompress(base64.b64decode(html[s : html.index("</script>", s)])))


old, new = payload("viewer-cdp.html.bak-20260917"), payload("viewer-cdp.html")
eg = new["extra_group"]
extras = set(new["groups"][eg])
print("非群組", eg, len(extras), "檔:", sorted(extras))
print("population", new["population"], "舊 codes", len(old["codes"]))
stripped = dict(new)
stripped.pop("extra_group")
stripped.pop("population")
stripped["codes"] = [c for c in new["codes"] if c["c"] not in extras]
stripped["names"] = {k: v for k, v in new["names"].items() if k not in extras}
stripped["groups"] = {k: v for k, v in new["groups"].items() if k != eg}
stripped["daysum"] = {k: v for k, v in new["daysum"].items() if k not in extras}
stripped["d"] = {k: v for k, v in new["d"].items() if k not in extras}
dump = lambda x: json.dumps(x, ensure_ascii=False, separators=(",", ":"))  # noqa: E731
print("扣掉新增後與舊 payload 相同:", dump(stripped) == dump(old))
for k in old:
    if dump(stripped[k]) != dump(old[k]):
        print("  不同的鍵:", k)
days = {c: sorted(new["d"][c]) for c in extras}
print("非群組日子:", {d for v in days.values() for d in v})
sample = new["d"]["2305"]["2026-09-16"]
print(
    "2305 9/16:",
    {k: sample[k] for k in ("pc", "lim", "o", "c", "hi", "lo", "op", "cdp")},
    "1 分 K",
    len(sample["b"]),
    "根,成交標記",
    len(sample["f"]),
    "訊號",
    len(sample["s"]),
)
partial = {c: new["d"][c]["2026-09-16"].get("partial") for c in extras}
print("逐筆不完整:", {c: v for c, v in partial.items() if v})
print(
    "6147 頁頭:", {k: new["d"]["6147"]["2026-09-16"][k] for k in ("o", "hi", "lo", "c", "rg", "op")}
)
