"""pr-282 #6 驗收:把 make_pr281_check_pages.py 原始碼裡那道閘直接抓出來跑真值表。

不碰任何真目錄(只 exec 那兩行),證明護欄在「常數被改成真資料夾名」時真的擋在 rmtree 之前。
two-axis Std-5 之後那道閘不是 assert 而是 `if …: raise SystemExit(…)`(assert 在 `python -O`
下會整行消失,而它守的是「別刪到真資料夾」),所以這裡抓的是 if + raise 兩行。
"""

import pathlib
import re
import sys

p = pathlib.Path(sys.argv[1])
lines = p.read_text(encoding="utf-8").splitlines()
i = next(n for n, line in enumerate(lines) if line.startswith("if TMP_BOOKDIR =="))
gate = "\n".join(lines[i : i + 2])
real = re.search(r'TMP_BOOKDIR = "([^"]+)"', "\n".join(lines)).group(1)  # type: ignore[union-attr]
print("原始碼那道閘 :")
for line in lines[i : i + 2]:
    print("   " + line)
print("閘的下一行   :", lines[i + 2])
print("腳本現值     :", real)
for v in (real, "viewer-cdp-book", "viewer-cdp-book-pr282", "viewer-cdp-bookpr281", ""):
    try:
        exec(gate, {"TMP_BOOKDIR": v})  # noqa: S102
        r = "PASS(往下走到 rmtree)"
    except SystemExit as e:
        r = f"SystemExit -> 擋住({e})"
    print(f"  TMP_BOOKDIR={v!r:26} {r}")
