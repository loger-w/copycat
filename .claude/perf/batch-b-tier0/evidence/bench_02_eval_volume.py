"""0-2 `_eval_volume` 窗和:SignalDetector.evaluate 每 tick 成本 vs 300 s 窗內筆數。

先以 rate 筆/秒灌滿 300 s 窗(窗長穩定在 rate × 300 筆),再量之後 `measure` 筆的每 tick
牆鐘(µs)。`enabled` 只開 vol_burst 隔離該 kind(**committed 數字是這個母體,不是 prod 每 tick evaluate 總成本**);
`--all` 開 `KIND_SWITCH` 全部 kind 看整體。
時鐘注入 10:00 起(開盤 60 分鐘後,過 vol_min_elapsed_min 閘)。

用法:python bench_02_eval_volume.py [--repo <root>] [--rates 1,10,33] [--measure 2000]
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


class _Clock:
    def __init__(self) -> None:
        self.now = _dt.datetime(2026, 9, 15, 10, 0, 0)

    def __call__(self) -> _dt.datetime:
        return self.now

    def advance(self, secs: float) -> None:
        self.now += _dt.timedelta(seconds=secs)


def run(repo: str, rate: int, measure: int, enabled: frozenset[str]) -> dict:
    from copycat.live.signal_state import SignalDetector, TickContext
    from copycat.live.stock_models import StockTick
    from copycat.signals_config import SignalsConfig

    clock = _Clock()
    det = SignalDetector(SignalsConfig(), now_fn=clock)
    step = 1.0 / rate
    cum = 0
    price = 100_000

    def tick(i: int) -> StockTick:
        return StockTick(
            code="2330",
            price_milli=price + (i % 7) * 100,
            qty=1 + (i % 3),
            cum_vol=cum,
            time="10:00:00.123",
            trade_date="2026-09-15",
            side="neutral",
            is_trial=False,
        )

    def ctx() -> TickContext:
        return TickContext(
            trade_date="2026-09-15",
            upper_milli=110_000,
            lower_milli=90_000,
            ask_limit_available=True,
            bid_limit_available=True,
            bids0_is_market=False,
            asks0_is_market=False,
            best_bid_limit_milli=99_900,
            best_ask_limit_milli=100_100,
            day_volume=cum,
        )

    warm = rate * 300 + 5
    for i in range(warm):
        cum += 1 + (i % 3)
        det.evaluate("2330", tick(i), ctx(), enabled)
        clock.advance(step)
    xs: list[float] = []
    for i in range(warm, warm + measure):
        cum += 1 + (i % 3)
        t = tick(i)
        c = ctx()
        t0 = time.perf_counter_ns()
        det.evaluate("2330", t, c, enabled)
        xs.append((time.perf_counter_ns() - t0) / 1000)
        clock.advance(step)
    window_len = len(det._window["2330"])
    return {
        "rate_per_s": rate,
        "window_len": window_len,
        "enabled": sorted(enabled),
        "per_tick_us": {
            "p50": round(pct(xs, 0.5), 2),
            "p90": round(pct(xs, 0.9), 2),
            "p99": round(pct(xs, 0.99), 2),
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=r"C:\side-project\copycat")
    ap.add_argument("--rates", default="1,10,33")
    ap.add_argument("--measure", type=int, default=2000)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    sys.path.insert(0, a.repo)
    kinds = frozenset({"vol_burst"})
    if a.all:
        from copycat.live.signal_state import KIND_SWITCH  # 全集(pr-251 review F-19:字面寫死漏了兩種 kind)

        kinds = frozenset(KIND_SWITCH.values())
    rows = [run(a.repo, int(r), a.measure, kinds) for r in a.rates.split(",")]
    print(json.dumps({"repo": a.repo, "rows": rows}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
