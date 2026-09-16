"""決定性:兩次 CLI 產出逐位元組比對(檔名集合、sha256、殘留 .tmp)。"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

a, b = Path(sys.argv[1]), Path(sys.argv[2])
names_a = sorted(p.name for p in a.iterdir())
names_b = sorted(p.name for p in b.iterdir())
print(
    f"A {len(names_a)} 檔、B {len(names_b)} 檔,檔名集合{'相同' if names_a == names_b else '不同'}"
)
print("非 .js 檔:", [n for n in names_a + names_b if not n.endswith(".js")])
diff = [
    n for n in names_a if n in names_b and (a / n).read_bytes() != (b / n).read_bytes()
]
print(f"位元組不同的檔:{diff}")
digest = hashlib.sha256()
for n in names_a:
    digest.update(n.encode())
    digest.update(hashlib.sha256((a / n).read_bytes()).digest())
print(f"A 目錄彙總 sha256(檔名 + 各檔 sha256 依序)= {digest.hexdigest()}")
total = sum((a / n).stat().st_size for n in names_a)
print(f"A 總位元組 {total:,}")
