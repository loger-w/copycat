"""0-4 CorrState:每秒一次 `push()` + `correlations()` 的成本(11 腿 × 窗 (60,300,1800))。

形狀取自 configs/correlation.json(base TXF + 10 腿;SXF / VX 稀疏,25% 有值)。
價格 = 合成隨機漫步(共同因子 + 個別噪音,σ=8e-5/秒;T2 §1 同款)。先灌 warm 秒填滿最長窗,
再量 `measure` 秒;`--drift` 另對照「全窗整批 statistics.correlation 重算」的 max|Δr|
(after 版的漂移證據;before 版兩者同式,Δr 恆 0)。stdlib-only。

用法:python bench_04_corr_state.py [--repo <root>] [--warm 1900] [--measure 300] [--drift]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
import time

LEGS = ["TXF", "TWN", "YM", "ES", "NQ", "SXF", "NK225M", "VX", "CL", "GC", "TSMC"]
BASE = "TXF"
SPARSE = {"SXF", "VX"}
WINDOWS = (60, 300, 1800)


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round((len(xs) - 1) * p)))]


class Walk:
    def __init__(self, seed: int) -> None:
        self.r = random.Random(seed)
        self.px = {k: 20_000_000 + i * 1_000_000 for i, k in enumerate(LEGS)}

    def step(self) -> dict[str, int | None]:
        common = self.r.gauss(0, 8e-5)
        out: dict[str, int | None] = {}
        for k in LEGS:
            self.px[k] = int(round(self.px[k] * math.exp(common * 0.6 + self.r.gauss(0, 8e-5))))
            if k in SPARSE and self.r.random() > 0.25:
                out[k] = None
            else:
                out[k] = self.px[k]
        return out


def reference_corr(
    series: dict[str, list[tuple[float, int | None]]], now: float, leg: str
) -> dict[str, float | int | None]:
    """整批重算參考:與 before 版 CorrState 同一套定義(相鄰秒、兩腿皆有值、不跨洞)。"""
    base = series[BASE]
    other = dict(series[leg])
    pairs: list[tuple[float, float, float]] = []
    prev: tuple[float, int | None, int | None] | None = None
    for ts, b in base:
        o = other.get(ts)
        if (
            prev is not None
            and prev[1] is not None
            and prev[2] is not None
            and b is not None
            and o is not None
            and abs((ts - prev[0]) - 1.0) <= 0.5
        ):
            pairs.append((ts, math.log(b / prev[1]), math.log(o / prev[2])))
        prev = (ts, b, o)
    row: dict[str, float | int | None] = {}
    for w in WINDOWS:
        xs = [rb for ts, rb, _ in pairs if ts >= now - w]
        ys = [rl for ts, _, rl in pairs if ts >= now - w]
        row[f"n{w}"] = len(xs)
        if len(xs) < max({60: 30, 300: 100, 1800: 300}[w], 2):
            row[f"w{w}"] = None
        else:
            try:
                row[f"w{w}"] = statistics.correlation(xs, ys)
            except statistics.StatisticsError:
                row[f"w{w}"] = None
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=r"C:\side-project\copycat")
    ap.add_argument("--warm", type=int, default=1900)
    ap.add_argument("--measure", type=int, default=300)
    ap.add_argument("--drift", action="store_true")
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()
    sys.path.insert(0, a.repo)
    from copycat.live.corr_state import CorrState

    state = CorrState(LEGS, BASE, windows=WINDOWS)
    walk = Walk(a.seed)
    session = ("20260915", "day")
    ts = 0.0
    # 參考用中價序列(自行逐出到最長窗 + 與 before 版 _evict 同語意:ts < now - 1800 丟)
    ref_series: dict[str, list[tuple[float, int | None]]] = {k: [] for k in LEGS}

    def feed() -> None:
        nonlocal ts
        ts += 1.0
        mids = walk.step()
        state.push(ts, mids, session)
        if a.drift:
            for k in LEGS:
                ref_series[k].append((ts, mids[k]))
                cutoff = ts - 1800
                while ref_series[k] and ref_series[k][0][0] < cutoff:
                    ref_series[k].pop(0)

    for _ in range(a.warm):
        feed()

    push_ms: list[float] = []
    corr_ms: list[float] = []
    max_dr = 0.0
    n_mismatch = 0
    for _ in range(a.measure):
        ts_next = ts + 1.0
        mids = walk.step()
        t0 = time.perf_counter()
        state.push(ts_next, mids, session)
        push_ms.append((time.perf_counter() - t0) * 1000)
        ts = ts_next
        t0 = time.perf_counter()
        out = state.correlations(ts)
        corr_ms.append((time.perf_counter() - t0) * 1000)
        if a.drift:
            for k in LEGS:
                ref_series[k].append((ts, mids[k]))
                cutoff = ts - 1800
                while ref_series[k] and ref_series[k][0][0] < cutoff:
                    ref_series[k].pop(0)
            for leg in LEGS:
                if leg == BASE:
                    continue
                ref = reference_corr(ref_series, ts, leg)
                got = out[leg]
                for w in WINDOWS:
                    if got[f"n{w}"] != ref[f"n{w}"]:
                        n_mismatch += 1
                    gv, rv = got[f"w{w}"], ref[f"w{w}"]
                    if gv is None or rv is None:
                        if (gv is None) != (rv is None):
                            n_mismatch += 1
                        continue
                    max_dr = max(max_dr, abs(float(gv) - float(rv)))

    out_json = {
        "repo": a.repo,
        "legs": len(LEGS),
        "windows": WINDOWS,
        "warm": a.warm,
        "measure": a.measure,
        "push_ms": {"p50": round(pct(push_ms, 0.5), 4), "p90": round(pct(push_ms, 0.9), 4)},
        "correlations_ms": {
            "p50": round(pct(corr_ms, 0.5), 4),
            "p90": round(pct(corr_ms, 0.9), 4),
            "max": round(max(corr_ms), 4),
        },
        "per_second_total_ms_p50": round(pct(push_ms, 0.5) + pct(corr_ms, 0.5), 4),
    }
    if a.drift:
        out_json["drift"] = {"n_mismatch": n_mismatch, "max_abs_dr": max_dr}
    print(json.dumps(out_json, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
