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
with tempfile.TemporaryDirectory() as tmp:
    for n, body in enumerate(scripts):
        js = Path(tmp) / f"s{n}.js"
        js.write_text(body, encoding="utf-8")
        r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
        print(f"block {n}: node --check exit={r.returncode}", r.stderr.strip()[:500])
        if r.returncode:
            sys.exit(1)
print("SYNTAX-OK")
