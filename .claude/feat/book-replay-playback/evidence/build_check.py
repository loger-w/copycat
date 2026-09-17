"""#270 重產回看頁後的資料不變檢查:新舊 viewer-cdp.html 解出的 payload 逐位元組相同,且新頁 = 模板 + blob。

用法:python build_check.py
"""

import base64
import gzip
import re
from pathlib import Path

ROOT = Path(r"C:\Users\USER\Documents\copycat-trading-review")


def blob(path):
    text = path.read_text(encoding="utf-8")
    m = re.search(r'<script id="blob" type="text/plain">(.*?)</script>', text, re.S)
    assert m, f"{path} 沒有 blob"
    return text, m.group(1).strip()


_, b_old = blob(ROOT / "viewer-cdp.html.bak-20260917-pre270")
t_new, b_new = blob(ROOT / "viewer-cdp.html")
p_old, p_new = gzip.decompress(base64.b64decode(b_old)), gzip.decompress(base64.b64decode(b_new))
tpl = (ROOT / "scripts" / "week0909" / "viewer_cdp_template.html").read_text(encoding="utf-8")
print("payload bytes 改前", len(p_old), "改後", len(p_new), "逐位元組相同", p_old == p_new)
print("新頁 == 模板 + blob:", t_new == tpl.replace("__DATA_B64__", b_new))
raw = (ROOT / "scripts" / "week0909" / "viewer_cdp_template.html").read_bytes()
print("模板換行 CRLF", raw.count(b"\r\n"), "LF", raw.count(b"\n"))
