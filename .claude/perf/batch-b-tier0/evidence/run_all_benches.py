"""一鍵重跑全部 before / after harness,輸出落 evidence/out_{before,after}_<n>.json(0-3 / 0-7 的 60 秒
連量另走 bench_03_timer_drift.py + Start-Process,見該檔 docstring)。

用法:python run_all_benches.py --before <主樹 root> --after <worktree root>
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
RUNS: list[tuple[str, str, list[str]]] = [
    ("01", "bench_01_history_poll.py", ["--n", "60", "--timer-1ms"]),
    ("02", "bench_02_eval_volume.py", []),
    ("04", "bench_04_corr_state.py", ["--drift"]),
    ("05", "bench_05_audit.py", []),
    ("06", "bench_06_asdict.py", []),
    ("09", "bench_09_evaluate_book.py", []),
    ("11", "check_11_river_wire.py", []),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    a = ap.parse_args()
    env = {**os.environ, "PYTHONUTF8": "1"}
    for tag, script, extra in RUNS:
        for side, repo in (("before", a.before), ("after", a.after)):
            out = HERE / f"out_{side}_{tag}.json"
            with open(out, "w", encoding="utf-8") as fh:
                subprocess.run(
                    [sys.executable, str(HERE / script), "--repo", repo, *extra],
                    stdout=fh,
                    stderr=subprocess.STDOUT,
                    env=env,
                    check=True,
                )
            print(f"{side}_{tag} -> {out.name}")


if __name__ == "__main__":
    main()
