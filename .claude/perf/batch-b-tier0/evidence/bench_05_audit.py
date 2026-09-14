"""0-5 `append_audit` 單次成本(µs):per-append mkdir 在鎖內 vs 搬到啟動。

同一顆 SSD 的暫存目錄、同一條 record(群益送單審計列形狀)、N 次 append 取 p50 / p90 / p99。
用法:python bench_05_audit.py [--repo <root>] [--n 3000]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import tempfile
import time
from pathlib import Path

REC = {
    "ts": "2026-09-15T09:00:00+08:00",
    "env": "prod",
    "action": "order",
    "req": {
        "stock_no": "6949",
        "buy_sell": "sell",
        "price": 58.8,
        "qty": 1,
        "price_type": "limit",
        "time_in_force": "ROD",
        "trade_kind": "margin",
        "source": "flash-locked",
    },
    "blocked": None,
    "result": None,
}


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round((len(xs) - 1) * p)))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=r"C:\side-project\copycat")
    ap.add_argument("--n", type=int, default=3000)
    a = ap.parse_args()
    sys.path.insert(0, a.repo)
    from copycat.server import audit

    when = _dt.date(2026, 9, 15)
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "audit"
        prepare = getattr(audit, "ensure_audit_dir", None)
        if prepare is not None:
            prepare(base)  # after 版:啟動時建一次
        xs: list[float] = []
        for _ in range(a.n):
            t0 = time.perf_counter_ns()
            audit.append_audit(base, REC, when=when, prefix="capital")
            xs.append((time.perf_counter_ns() - t0) / 1000)
        lines = sum(
            1 for _ in open(audit.audit_path(base, when, prefix="capital"), encoding="utf-8")
        )
    print(
        json.dumps(
            {
                "repo": a.repo,
                "has_ensure_audit_dir": prepare is not None,
                "n": a.n,
                "lines_written": lines,
                "append_us": {
                    "p50": round(pct(xs, 0.5), 1),
                    "p90": round(pct(xs, 0.9), 1),
                    "p99": round(pct(xs, 0.99), 1),
                },
            },
            ensure_ascii=False,
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
