"""把 viewer-cdp.html 內嵌的 payload 解出來存成 JSON(#273 AC4:比對舊交易日的逐筆有沒有被動到)。

用法:python payload_dump.py <viewer-cdp.html> <out.json>
"""

import base64
import gzip
import json
import re
import sys
from pathlib import Path

src = Path(sys.argv[1]).read_text(encoding="utf-8")
m = re.search(r'<script id="blob" type="text/plain">([A-Za-z0-9+/=]+)</script>', src)
assert m, "找不到 blob"
payload = json.loads(gzip.decompress(base64.b64decode(m.group(1))).decode("utf-8"))
Path(sys.argv[2]).write_text(
    json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=0), encoding="utf-8"
)
print(
    "keys",
    sorted(payload),
    "codes",
    len(payload["codes"]),
    "dates",
    len(payload["dates"]),
)
