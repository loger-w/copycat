"""突變體迴圈(pr-275 review 收修):改壞 → 跑議定 seam 測試 → 記憶體寫回還原 → sleep 避同秒 pyc。

用法(worktree 根):python mutants.py <組名> [<組名> …];組定義在 GROUPS。
每顆突變體可改多處(對稱突變),每處的 old 字串必須恰好出現一次。
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path.cwd()
PY = "C:/side-project/copycat/.venv/Scripts/python"
SRC = "copycat/book_replay.py"

Site = tuple[str, str, str]  # (相對路徑, old, new)

GROUPS: dict[str, list[tuple[str, list[Site]]]] = {
    # F-04 / F-05:釘住既有行為
    "pin": [
        ("tol-3000", [(SRC, "CLOCK_FUTURE_TOLERANCE_MS = 60_000", "CLOCK_FUTURE_TOLERANCE_MS = 3_000")]),
        ("tol-60001", [(SRC, "CLOCK_FUTURE_TOLERANCE_MS = 60_000", "CLOCK_FUTURE_TOLERANCE_MS = 60_001")]),
        (
            "tol-strict-lt",
            [
                (
                    SRC,
                    "<= row.recv_ns // 1_000_000 + CLOCK_FUTURE_TOLERANCE_MS",
                    "< row.recv_ns // 1_000_000 + CLOCK_FUTURE_TOLERANCE_MS",
                )
            ],
        ),
        ("gzip-mtime", [(SRC, "compresslevel=9, mtime=0)", "compresslevel=9, mtime=12345)")]),
    ],
    # F-01 / F-02 / F-03 / F-07:格式字面、解碼特例、時刻異常清單檢查
    "format": [
        (
            "decode-first-clock-index",
            [(SRC, "    clock_index = -1\n    state: list", "    clock_index = 0\n    state: list")],
        ),
        (
            "kind-code-swap",
            [(SRC, '{"trade": "t", "book": "b"}', '{"trade": "b", "book": "t"}')],
        ),
        (
            "trade-cells-reversed-symmetric",
            [
                (
                    SRC,
                    "tuple(f.name for f in dataclass_fields(Trade))",
                    "tuple(reversed([f.name for f in dataclass_fields(Trade)]))",
                ),
                (SRC, "Trade(*next(trades))", "Trade(**dict(zip(_TRADE_CELLS, next(trades))))"),
            ],
        ),
        (
            "anomalous-trade-inverted",
            [(SRC, 'return self.kind == "trade" and self.after != 0', 'return self.kind == "trade" and self.after == 0')],
        ),
        (
            "anomalous-trade-drops-kind",
            [(SRC, 'return self.kind == "trade" and self.after != 0', "return self.after != 0")],
        ),
        (
            "header-anomalous-not-increasing",
            [(SRC, "if not (prev_index < index < n and", "if not (-1 < index < n and")],
        ),
        (
            "header-anomalous-upper-bound",
            [(SRC, "if not (prev_index < index < n and", "if not (prev_index < index and")],
        ),
        (
            "header-anomalous-on-trade",
            [
                (
                    SRC,
                    'index < n and kinds[index] == _KIND_CODE["trade"]):',
                    "index < n):",
                )
            ],
        ),
        ("decode-rewind-check", [(SRC, "elif clock is not None and trade.ms < clock:", "elif False:")]),
        ("decode-ms-none-check", [(SRC, "elif trade.ms is None:", "elif False:")]),
    ],
    # F-08:逐則的值與 book_at 範圍
    "values": [
        ("header-kf-every-lt1", [(SRC, "    if every < 1:", "    if every < 0:")]),
        ("encode-kf-every", [(SRC, "if keyframe_every < 1:", "if keyframe_every < 0:")]),
        ("delta-odd", [(SRC, "if len(delta) % 2:", "if False:")]),
        ("delta-field-lower", [(SRC, "if not 0 <= field < len(state):", "if not field < len(state):")]),
        ("delta-field-upper", [(SRC, "if not 0 <= field < len(state):", "if not 0 <= field:")]),
        ("seq-strict", [(SRC, "if seq_step <= 0:", "if seq_step < 0:")]),
        ("side-domain", [(SRC, "if trade.side not in _SIDES:", "if False:")]),
        ("book-at-lower", [(SRC, "if not 0 <= index < n:", "if not index < n:")]),
        ("book-at-upper", [(SRC, "if not 0 <= index < n:", "if not 0 <= index:")]),
    ],
}


def run_tests() -> tuple[int, str]:
    proc = subprocess.run(
        [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_book_replay.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    tail = [line for line in proc.stdout.splitlines() if line.strip()][-1:]
    return proc.returncode, tail[0] if tail else proc.stderr[-200:]


def run_mutant(name: str, sites: list[Site]) -> bool:
    originals: dict[Path, bytes] = {}
    try:
        for rel, old, new in sites:
            path = ROOT / rel
            originals.setdefault(path, path.read_bytes())
            text = path.read_text(encoding="utf-8")
            count = text.count(old)
            assert count == 1, f"{name}: {old!r} 出現 {count} 次"
            path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="")
        time.sleep(1.1)
        rc, summary = run_tests()
    finally:
        for path, data in originals.items():
            path.write_bytes(data)
        time.sleep(1.1)
    print(f"{name}: {'KILLED' if rc != 0 else 'SURVIVED'} ({summary})")
    return rc != 0


def main(groups: list[str]) -> int:
    rc, summary = run_tests()
    print(f"baseline: rc={rc} {summary}")
    if rc != 0:
        return 1
    survived = 0
    for group in groups:
        print(f"== {group}")
        for name, sites in GROUPS[group]:
            survived += not run_mutant(name, sites)
    rc, summary = run_tests()
    print(f"restored: rc={rc} {summary};survived={survived}")
    return 1 if survived or rc != 0 else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
