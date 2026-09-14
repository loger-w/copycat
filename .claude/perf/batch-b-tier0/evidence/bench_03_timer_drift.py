"""0-3 / 0-7 timer drift 60 秒連量(perf #243 / #247 的判準腳本)。

量 ProactorEventLoop 上 `asyncio.sleep(0.05)` 的 drift(實際等待 − 0.05,ms),**連量 60 秒**:
T4 §2.1 實測單獨 `timeBeginPeriod(1)` 前 3 秒 0.5 ms、之後被 Windows 11 EcoQoS 收回到 12.6 ms,
量 3 秒會讓壞實作假 PASS,所以分段印(0–3 s / 3–60 s / 全程 / 每 10 s p50)且判準看 3–60 s 與全程。

模式(`--mode`):
  base   什麼都不做(before)
  apply  呼叫 `--repo` 那份 code 的 `copycat.server.win_timer.apply_timer_1ms()`(after;prod 同一條路)
  tbp    只 timeBeginPeriod(1)(對照:應該前 3 秒好、之後退回)
`--switch <secs>`:另設 `sys.setswitchinterval`(0-7);`--cpu-threads N`:起 N 條 CPU-bound 執行緒
(解 REALTIME 電文)當背景競爭,0-7 的判準 = apply + switch 0.001 + 4 threads 下 loop p50 ≤ 4 ms。

**要以 run.ps1 同款方式起**(無視窗才會碰到 EcoQoS):
  Start-Process -FilePath <venv>\\python.exe -ArgumentList '<本檔>','--mode','apply','--repo','<root>' `
      -NoNewWindow -Wait -RedirectStandardOutput <out.json>
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import statistics
import sys
import threading
import time

DELAY = 0.05

QUOTE_RAW = (
    b"TC.S.TSE.2330:"
    + json.dumps(
        {
            "DataType": "REALTIME",
            "Quote": {
                "Symbol": "TC.S.TSE.2330",
                "TradingPrice": "1085.0000",
                "TradeQuantity": "3",
                "Bid": "1085.0000",
                "Ask": "1090.0000",
            },
        }
    ).encode()
    + b"\x00"
)


def _unit() -> int:
    s = QUOTE_RAW[:-1].decode("utf-8")
    obj = json.loads(s[s.find(":") + 1 :])
    q = obj["Quote"]
    return int(round(float(q["Ask"]) * 1000)) - int(round(float(q["Bid"]) * 1000))


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round((len(xs) - 1) * p)))]


def seg(rows: list[tuple[float, float]], lo: float, hi: float) -> dict:
    xs = [d for t, d in rows if lo <= t < hi]
    if not xs:
        return {"n": 0}
    return {
        "n": len(xs),
        "p50": round(pct(xs, 0.5), 3),
        "p90": round(pct(xs, 0.9), 3),
        "p99": round(pct(xs, 0.99), 3),
        "mean": round(statistics.fmean(xs), 3),
        "under_1ms": round(sum(1 for x in xs if x < 1.0) / len(xs), 3),
        "under_2ms": round(sum(1 for x in xs if x < 2.0) / len(xs), 3),
    }


async def _measure(secs: float) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    t_start = time.perf_counter()
    while True:
        t0 = time.perf_counter()
        await asyncio.sleep(DELAY)
        t1 = time.perf_counter()
        out.append((t0 - t_start, (t1 - t0 - DELAY) * 1000))
        if t1 - t_start >= secs:
            return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("base", "apply", "tbp"), default="base")
    ap.add_argument("--repo", default=r"C:\side-project\copycat")
    ap.add_argument("--secs", type=float, default=60.0)
    ap.add_argument("--switch", type=float, default=None)
    ap.add_argument("--cpu-threads", type=int, default=0)
    a = ap.parse_args()
    rec: dict = {"mode": a.mode, "secs": a.secs, "switch": a.switch, "cpu_threads": a.cpu_threads}
    if a.mode == "apply":
        sys.path.insert(0, a.repo)
        from copycat.server.win_timer import apply_timer_1ms

        rec["apply_ok"] = apply_timer_1ms()
    elif a.mode == "tbp":
        rec["tbp"] = ctypes.WinDLL("winmm").timeBeginPeriod(1)
    if a.switch is not None:
        sys.setswitchinterval(a.switch)
    rec["switchinterval"] = sys.getswitchinterval()

    stop = threading.Event()
    counts = [0] * a.cpu_threads

    def spin(idx: int) -> None:
        c = 0
        while not stop.is_set():
            for _ in range(500):
                _unit()
            c += 500
        counts[idx] = c

    threads = [threading.Thread(target=spin, args=(i,), daemon=True) for i in range(a.cpu_threads)]
    for t in threads:
        t.start()
    loop = asyncio.ProactorEventLoop()
    t0 = time.perf_counter()
    try:
        rows = loop.run_until_complete(_measure(a.secs))
    finally:
        wall = time.perf_counter() - t0
        loop.close()
        stop.set()
        for t in threads:
            t.join(timeout=5)
    rec["first_3s"] = seg(rows, 0, 3)
    rec["after_3s"] = seg(rows, 3, 1e9)
    rec["all"] = seg(rows, 0, 1e9)
    rec["per_10s_p50"] = [seg(rows, s, s + 10).get("p50") for s in range(0, int(a.secs), 10)]
    if a.cpu_threads:
        rec["worker_units_per_s"] = round(sum(counts) / wall, 1)
    print(json.dumps(rec, ensure_ascii=False))


if __name__ == "__main__":
    main()
