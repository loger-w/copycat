"""[perf #241 重啟後判準;原檔 = 2026-09-13 verify-bakeoff C1-B4 scratchpad 腳本,逐字複製]
C1-B4:prod 真實熱路徑實測 —— `/api/stock/overlay/{code}` 的 DK 取數排在 api.lock 後面值多少。

**零新 session、零新 refcount**:全部走跑著的 server 自己的 stock session,
與前端進群組時做的事逐字相同(GET /api/stock/overlay/<code>)。

量三件事:
  1. 冷取(cache miss)單發延遲 = 一次 SubHistory(DK) + GETHISDATA 收割 的真實成本
  2. 並發灌入 N 檔(= 進群組)時的 p50/p95/max —— 這是使用者真正感受到的
  3. 熱取(cache hit)當基線,把 HTTP/loop 的固定成本扣掉

用法:<venv>\Scripts\python.exe bench_04_prod_overlay.py [並發檔數]
"""
from __future__ import annotations

import json
import statistics as st
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "http://127.0.0.1:8721"
BURST = int(sys.argv[1]) if len(sys.argv) > 1 else 30


def get(path: str, timeout: float = 40.0):
    t0 = time.perf_counter()
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        body = r.read()
    return time.perf_counter() - t0, json.loads(body)


def pctl(xs, p):
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def main() -> None:
    _, wl = get("/api/stock/watchlist")
    codes = wl["codes"]
    print(f"自選 {len(codes)} 檔;trade_date = {get('/api/calendar')[1]['trade_date']}")

    # ---- 1. 序列冷取:前 10 檔 ----
    print("\n== 1. 序列取 overlay(第一輪,可能冷可能熱)==")
    seq = []
    for c in codes[:10]:
        dt, body = get(f"/api/stock/overlay/{c}")
        seq.append(dt)
        print(f"  {c}: {dt*1000:8.1f} ms  cdp={'有' if body.get('cdp') else '無'}")
    print(f"  p50 {pctl(seq,0.5)*1000:.1f} ms  max {max(seq)*1000:.1f} ms")

    # ---- 2. 熱取基線(同一批,現在必在 cache)----
    print("\n== 2. 同一批再取一次(cache hit 基線 = HTTP + loop 固定成本)==")
    hot = []
    for c in codes[:10]:
        dt, _ = get(f"/api/stock/overlay/{c}")
        hot.append(dt)
    print(f"  p50 {pctl(hot,0.5)*1000:.3f} ms  max {max(hot)*1000:.3f} ms")

    # ---- 3. 並發灌入(= 進群組)----
    burst_codes = codes[10:10 + BURST]
    print(f"\n== 3. 並發灌入 {len(burst_codes)} 檔(= 進群組;route 有 Semaphore(4))==")
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(burst_codes)) as ex:
        res = list(ex.map(lambda c: get(f"/api/stock/overlay/{c}")[0], burst_codes))
    wall = time.perf_counter() - t0
    print(f"  牆鐘 {wall:.2f} s  每檔 p50 {pctl(res,0.5)*1000:.0f} ms  "
          f"p95 {pctl(res,0.95)*1000:.0f} ms  max {max(res)*1000:.0f} ms")
    print(f"  → 有效吞吐 {len(burst_codes)/wall:.1f} 檔/s;"
          f"外推 150 檔 ≈ {150/(len(burst_codes)/wall):.1f} s")

    # ---- 4. 同時間的互動請求:一發 /api/stock/bars 排在哪裡 ----
    print(f"\n== 4. 灌入進行中,使用者點開一檔 K 線(/api/stock/bars)的延遲 ==")
    burst2 = codes[10 + BURST:10 + BURST + 20] or codes[:20]
    victim = codes[-1]
    lat_box = []

    def interactive():
        time.sleep(0.35)
        dt, _ = get(f"/api/stock/bars/{victim}?tf=D&days=5")
        lat_box.append(dt)

    with ThreadPoolExecutor(max_workers=len(burst2) + 1) as ex:
        f_i = ex.submit(interactive)
        fs = [ex.submit(lambda c: get(f"/api/stock/overlay/{c}")[0], c) for c in burst2]
        f_i.result()
        for f in fs:
            f.result()
    if lat_box:
        print(f"  背景 {len(burst2)} 檔灌入中,互動 K 線請求 = {lat_box[0]*1000:.0f} ms")
    dt_idle, _ = get(f"/api/stock/bars/{victim}?tf=D&days=5")
    print(f"  閒置時同一發                   = {dt_idle*1000:.0f} ms")


if __name__ == "__main__":
    main()
