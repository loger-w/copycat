"""兩個文字檔的 unified diff(CRLF 正規化成 LF 再比),寫成 UTF-8 LF;印增刪行數。

用法:python diff_text.py <舊檔> <新檔> <輸出 diff> [<舊檔標籤> <新檔標籤>]
"""

from __future__ import annotations

import difflib
import sys
from pathlib import Path

old_path, new_path, out_path = (Path(a) for a in sys.argv[1:4])
old_label = sys.argv[4] if len(sys.argv) > 4 else old_path.name
new_label = sys.argv[5] if len(sys.argv) > 5 else new_path.name


def lines(path: Path) -> list[str]:
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n").splitlines(keepends=True)


text = "".join(difflib.unified_diff(lines(old_path), lines(new_path), old_label, new_label))
out_path.write_text(text, encoding="utf-8", newline="\n")
body = text.splitlines()
added = sum(1 for line in body if line.startswith("+") and not line.startswith("+++"))
removed = sum(1 for line in body if line.startswith("-") and not line.startswith("---"))
print(f"{out_path.name}:+{added} / −{removed}")
