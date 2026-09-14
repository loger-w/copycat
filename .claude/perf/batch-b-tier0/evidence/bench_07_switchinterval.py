"""0-7 `sys.setswitchinterval`:K 條 CPU-bound 執行緒在跑時,event loop `asyncio.sleep(0.005)` 的 drift。

沿 T4 `t4_bench_switch.py` 同法(worker = 解一則 REALTIME 電文),但只掃 {0.005(預設), 0.001},
且**兩種 timer 組態各跑一次**:prod-like(不動 timer 解析度)與 T4 表的組態(EcoQoS 豁免 +
timeBeginPeriod(1),即 0-3;prod 尚未做)。這支不 import copycat —— 它量的是直譯器旗標,
before / after 的差別只在 prod 進程有沒有呼叫 `setswitchinterval`;此處以參數化重現兩值。
用法:python bench_07_switchinterval.py [--threads 4] [--rounds 2]
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import ctypes.wintypes as wt
import json
import statistics
import sys
import threading
import time

winmm = ctypes.WinDLL("winmm")
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.GetCurrentProcess.restype = wt.HANDLE
k32.SetProcessInformation.restype = wt.BOOL
k32.SetProcessInformation.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD]


class PPT(ctypes.Structure):
    _fields_ = [("Version", wt.ULONG), ("ControlMask", wt.ULONG), ("StateMask", wt.ULONG)]


def timer_1ms() -> None:
    st = PPT(1, 0x1 | 0x4, 0)
    k32.SetProcessInformation(k32.GetCurrentProcess(), 4, ctypes.byref(st), ctypes.sizeof(st))
    winmm.timeBeginPeriod(1)


QUOTE = {
    "Symbol": "TC.S.TSE.2330",
    "TradingPrice": "1085.0000",
    "TradeQuantity": "3",
    "Bid": "1085.0000",
    "Ask": "1090.0000",
    "High": "1095.0000",
    "Low": "1075.0000",
    "FilledTime": "133012",
}
RAW = b"TC.S.TSE.2330:" + json.dumps({"DataType": "REALTIME", "Quote": QUOTE}).encode() + b"\x00"


def unit(raw: bytes = RAW) -> int:
    s = raw[:-1].decode("utf-8")
    i = s.find(":")
    obj = json.loads(s[i + 1 :])
    q = obj["Quote"]
    return int(round(float(q["Ask"]) * 1000)) - int(round(float(q["Bid"]) * 1000))


def pct(s: list[float], p: float) -> float:
    return s[min(len(s) - 1, int(round((len(s) - 1) * p)))]


def measure(k: int, iv: float) -> dict:
    sys.setswitchinterval(iv)
    stop = threading.Event()
    counts = [0] * k

    def spin(idx: int) -> None:
        c = 0
        while not stop.is_set():
            for _ in range(500):
                unit()
            c += 500
        counts[idx] = c

    ths = [threading.Thread(target=spin, args=(i,), daemon=True) for i in range(k)]
    for t in ths:
        t.start()

    async def go() -> list[float]:
        xs = []
        for _ in range(400):
            t0 = time.perf_counter()
            await asyncio.sleep(0.005)
            xs.append((time.perf_counter() - t0 - 0.005) * 1000)
        return xs

    loop = asyncio.ProactorEventLoop()
    t0 = time.perf_counter()
    try:
        xs = sorted(loop.run_until_complete(go()))
    finally:
        wall = time.perf_counter() - t0
        loop.close()
        stop.set()
        for t in ths:
            t.join(timeout=5)
    return {
        "cpu_threads": k,
        "switchinterval": iv,
        "loop_p50_ms": round(pct(xs, 0.5), 3),
        "loop_p90_ms": round(pct(xs, 0.9), 3),
        "loop_p99_ms": round(pct(xs, 0.99), 3),
        "loop_mean_ms": round(statistics.fmean(xs), 3),
        "worker_units_per_s": round(sum(counts) / wall, 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument(
        "--timer-1ms", action="store_true", help="套 0-3 組態(EcoQoS 豁免 + timeBeginPeriod)"
    )
    a = ap.parse_args()
    if a.timer_1ms:
        timer_1ms()
    rows = []
    for _ in range(a.rounds):
        for iv in (0.005, 0.001):
            rows.append(measure(a.threads, iv))
    print(
        json.dumps(
            {
                "python": sys.version.split()[0],
                "timer_1ms": a.timer_1ms,
                "rows": rows,
            },
            ensure_ascii=False,
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
