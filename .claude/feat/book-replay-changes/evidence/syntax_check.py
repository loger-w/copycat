"""#269:抽出回看頁的程式 <script>(資料 blob 除外)→ node --check。用法:python syntax_check.py <頁面>"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

page = Path(sys.argv[1]).read_text(encoding="utf-8")
scripts = [
    m.group(2)
    for m in re.finditer(r"<script(\s[^>]*)?>(.*?)</script>", page, re.S)
    if 'type="text/plain"' not in (m.group(1) or "")
]
print("script blocks", len(scripts))
if not scripts:
    # pr-279 review F-33:regex 抽不到任何 script(頁面結構或屬性寫法改了)時迴圈不會跑,
    # 原本會直接照印 SYNTAX-OK、exit 0 —— 這其實是「什麼都沒檢查到」,不是「檢查過都對」。
    sys.exit(
        "找不到程式 script 區塊(頁面結構或 <script> 屬性寫法可能改了,檢查上面的 regex 是否要跟著調)"
    )
with tempfile.TemporaryDirectory() as tmp:
    for n, body in enumerate(scripts):
        js = Path(tmp) / f"s{n}.js"
        js.write_text(body, encoding="utf-8")
        r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
        print(f"block {n}: node --check exit={r.returncode}", r.stderr.strip()[:500])
        if r.returncode:
            sys.exit(1)
print("SYNTAX-OK")
