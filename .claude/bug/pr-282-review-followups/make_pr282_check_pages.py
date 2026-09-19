"""pr-282 收修驗證用:造一份暫用頁,驗 #1(日期晚於**最後**一個有簿日時的面板文案)。

pr-281 的 `make_pr281_check_pages.py` 砍的是**中間**那一天(09-17),驗的是「界內缺一天」那一格;
本批要的是另一格 —— `bookdays` 砍掉**最後一天**再選那一天:界取 min,`rpShouldHaveBook()` 照樣命中,
但修前的文案會說它「落在有簿的區間內(09-16–09-17)」,而 09-18 根本不在裡面(pr-282 review #1)。

不動真的 `viewer-cdp-book/`,也不覆寫 `viewer-cdp.html`(只讀它的 payload 重打包成另一個檔名),
而且**完全不刪任何東西**(沒有 rmtree)。

用法:python make_pr282_check_pages.py   # 印出頁面路徑與要選的日期
"""

import base64
import gzip
import json
import re
from pathlib import Path

ROOT = Path(r"C:\Users\USER\Documents\copycat-trading-review")
OUT_NAME = "viewer-cdp-pr282-d3max.html"

src = (ROOT / "viewer-cdp.html").read_text(encoding="utf-8")
m = re.search(r'<script id="blob" type="text/plain">([A-Za-z0-9+/=]+)</script>', src)
assert m
PRE, POST, BLOB = src[: m.start(1)], src[m.end(1) :], m.group(1)

base = json.loads(gzip.decompress(base64.b64decode(BLOB)).decode("utf-8"))
print("原 bookdays =", base["bookdays"], " bookdir =", base["bookdir"])

drop = base["bookdays"][-1]
page = dict(base)
page["bookdays"] = base["bookdays"][:-1]
assert page["bookdays"], "至少要留一天,否則會走 rpNoBookDir() 那一種"

raw = json.dumps(page, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
b64 = base64.b64encode(gzip.compress(raw, 9)).decode("ascii")
out = ROOT / OUT_NAME
out.write_text(PRE + b64 + POST, encoding="utf-8")
print("#1 頁 bookdays =", page["bookdays"], "→", out)
print(
    f"  驗:開頁後選 {drop},重播分頁應說「它不早於最早有簿的一天({page['bookdays'][0]};"
    f"目前有簿 {len(page['bookdays'])} 天,最後一天 {page['bookdays'][-1]})」,"
    "不得再說「落在有簿的區間內」"
)
