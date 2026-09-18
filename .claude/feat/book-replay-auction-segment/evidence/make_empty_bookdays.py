"""F-3 驗證用:把回看頁的 payload 改成 bookdays = [](= 產生頁時一個外掛檔都沒掃到),另存一份暫用頁。

不動真的 viewer-cdp-book/ 資料夾,也不覆寫 viewer-cdp.html。
"""

import base64
import gzip
import json
import re
from pathlib import Path

ROOT = Path(r"C:\Users\USER\Documents\copycat-trading-review")
src = (ROOT / "viewer-cdp.html").read_text(encoding="utf-8")
m = re.search(r'<script id="blob" type="text/plain">([A-Za-z0-9+/=]+)</script>', src)
assert m
payload = json.loads(gzip.decompress(base64.b64decode(m.group(1))).decode("utf-8"))
print("before bookdays =", payload["bookdays"])
payload["bookdays"] = []
raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
b64 = base64.b64encode(gzip.compress(raw, 9)).decode("ascii")
out = ROOT / "viewer-cdp-empty-bookdays-273.html"
out.write_text(src[: m.start(1)] + b64 + src[m.end(1) :], encoding="utf-8")
print("wrote", out)
