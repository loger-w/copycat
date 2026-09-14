"""0-9 `SignalDetector.evaluate_book` 每則簿更新成本(µs):無 latch(常態)vs 有 latch。

簿更新每則都跑一次(prod 股票 REALTIME 87% 是簿更新),常態下該檔沒鎖板 → latch 全 False,
理想成本 = 兩個 dict 查詢。before 版先做 `_now_fn()` / `_in_session` / `_mono` / `_clock_key`
才查 latch。
用法:python bench_09_evaluate_book.py [--repo <root>] [--iters 20000]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import time


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round((len(xs) - 1) * p)))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=r"C:\side-project\copycat")
    ap.add_argument("--iters", type=int, default=20000)
    a = ap.parse_args()
    sys.path.insert(0, a.repo)
    from copycat.live.signal_state import SignalDetector, TickContext
    from copycat.signals_config import SignalsConfig

    now = _dt.datetime(2026, 9, 15, 10, 0, 0)
    det = SignalDetector(SignalsConfig(), now_fn=lambda: now)
    enabled = frozenset({"limit_lock"})
    ctx = TickContext(
        trade_date="2026-09-15",
        upper_milli=110_000,
        lower_milli=90_000,
        ask_limit_available=True,
        bid_limit_available=True,
        bids0_is_market=False,
        asks0_is_market=False,
        best_bid_limit_milli=99_900,
        best_ask_limit_milli=100_100,
        day_volume=1000,
    )

    def bench(code: str) -> dict:
        xs: list[float] = []
        for _ in range(a.iters):
            t0 = time.perf_counter_ns()
            det.evaluate_book(code, ctx, enabled)
            xs.append((time.perf_counter_ns() - t0) / 1000)
        return {"p50": round(pct(xs, 0.5), 3), "p90": round(pct(xs, 0.9), 3)}

    no_latch = bench("2330")
    # 有 latch(鎖板中)的檔:latch=True 但 reopened 為 True → 每次會翻 latch 並發事件,
    # 這裡只量「latch 為 True」那條路徑的第一次;之後 latch 被翻回 False,同無 latch。
    det._latch[("2317", "up")] = True
    first = time.perf_counter_ns()
    det.evaluate_book("2317", ctx, enabled)
    with_latch_first_us = (time.perf_counter_ns() - first) / 1000
    print(
        json.dumps(
            {
                "repo": a.repo,
                "iters": a.iters,
                "no_latch_us": no_latch,
                "with_latch_first_call_us": round(with_latch_first_us, 2),
            },
            ensure_ascii=False,
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
