"""pr-281 收修驗證用:造兩份暫用頁,驗 review #9(D3)與 #10。

不動真的 `viewer-cdp-book/`,也不覆寫 `viewer-cdp.html`(沿 make_empty_bookdays.py 的作法)。

1. `viewer-cdp-pr281-d3.html`:`bookdays` 拿掉 2026-09-17(落在 min–max 之間卻沒掃到)
   → 09-17 應印第三種文案「應該有五檔簿,但這一頁沒掃到」;09-15(在 min 之前)仍印原本
   「達錢歷史 TICKS 不含五檔」;09-16 / 09-18 照常可播。
2. `viewer-cdp-pr281-badtrial.html`:`bookdir` 改指暫用資料夾,裡面放一支把 `trial` 改成
   **物件**的外掛檔 → 應印「簿重播檔解不開」,而不是靜默退化成「沒有段」(修前 undefined % 2
   = NaN 會過關)。同資料夾另放一支**沒動過**的當對照組。

用法:python make_pr281_check_pages.py   # 印出兩份頁面路徑與對照用的代號
"""

import base64
import gzip
import json
import re
import shutil
from pathlib import Path

ROOT = Path(r"C:\Users\USER\Documents\copycat-trading-review")
DROP_DAY = "2026-09-17"
BAD_DAY = "2026-09-16"
BAD_CODE = "1303"  # trial 被改成物件的那一支
OK_CODE = "1312"  # 同一天的對照組,不動
TMP_BOOKDIR = "viewer-cdp-book-pr281"

src = (ROOT / "viewer-cdp.html").read_text(encoding="utf-8")
m = re.search(r'<script id="blob" type="text/plain">([A-Za-z0-9+/=]+)</script>', src)
assert m
PRE, POST, BLOB = src[: m.start(1)], src[m.end(1) :], m.group(1)


def repack(payload: dict, out_name: str) -> Path:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    b64 = base64.b64encode(gzip.compress(raw, 9)).decode("ascii")
    out = ROOT / out_name
    out.write_text(PRE + b64 + POST, encoding="utf-8")
    return out


base = json.loads(gzip.decompress(base64.b64decode(BLOB)).decode("utf-8"))
print("原 bookdays =", base["bookdays"], " bookdir =", base["bookdir"])

# --- (1) D3:界內缺一天 ---
d3 = dict(base)
d3["bookdays"] = [d for d in base["bookdays"] if d != DROP_DAY]
print("D3 頁 bookdays =", d3["bookdays"], "→", repack(d3, "viewer-cdp-pr281-d3.html"))

# --- (2) #10:trial 不是陣列 ---
tmp = ROOT / TMP_BOOKDIR / BAD_DAY
# docstring 承諾「不動真的 viewer-cdp-book/」,而下面是整棵 rmtree —— 這是 .claude/** 證據腳本裡
# 唯一一處破壞性呼叫,沒有同款前例可以背書,所以把那句承諾釘成機器可驗的(pr-282 review #6)
assert TMP_BOOKDIR != "viewer-cdp-book" and TMP_BOOKDIR.endswith("-pr281"), TMP_BOOKDIR
if tmp.parent.exists():
    shutil.rmtree(tmp.parent)
tmp.mkdir(parents=True)
shutil.copy(ROOT / "viewer-cdp-book" / BAD_DAY / f"{OK_CODE}.js", tmp / f"{OK_CODE}.js")

js = (ROOT / "viewer-cdp-book" / BAD_DAY / f"{BAD_CODE}.js").read_text(encoding="utf-8")
head = re.match(r'^window\.__bk\("([^"]+)","([^"]+)"\);\s*$', js)
assert head
payload = json.loads(gzip.decompress(base64.b64decode(head.group(2))))
print(f"  {BAD_CODE} 原 trial = {payload['trial']}")
payload["trial"] = {"0": 0}  # 物件:修前 undefined % 2 = NaN(falsy)→ 靜默當成沒有段
blob = base64.b64encode(
    gzip.compress(json.dumps(payload, separators=(",", ":")).encode(), 9)
).decode()
(tmp / f"{BAD_CODE}.js").write_text(f'window.__bk("{head.group(1)}","{blob}");\n', encoding="utf-8")

bad = dict(base)
bad["bookdir"] = TMP_BOOKDIR
bad["bookdays"] = [BAD_DAY]
print("#10 頁 bookdir =", bad["bookdir"], "→", repack(bad, "viewer-cdp-pr281-badtrial.html"))
print(f"  驗:{BAD_DAY} {BAD_CODE} 應「解不開」、{OK_CODE} 應照常有橘色帶")
