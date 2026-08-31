"""個股當日回補「單工 vs 批次 SubHistory vs 執行緒並行」量測(一次性 probe,收工必 close)。

背景(2026-08-28 triage /perf 開盤回補並行 步驟 ①):`stock_engine` 的回補 worker 單工,
每檔 `backfill(code)` = SubHistory → 等首頁 → 逐頁收割,實測開盤一秒一檔、40 檔要一分鐘,
user 看到群組圖牆「一檔一檔陸續跑好」。TXO 面早就用「先對全鏈 SubHistory 再 round 制收割」
(`tc4.fetch_backfill`,280 檔 10 分 → 大幅縮短)。本 probe 對同一組自選碼量三種做法:

  A. serial  :逐檔 `backfill(code)`(= 現況 worker)
  B. batch   :先對全部 `_sub_history`,再逐檔收割(= TXO 樣板)
  C. threads :ThreadPool(N) 並行 `backfill(code)`(session 鎖只包單一 REQ,poll sleep 可交錯)

每種做法記牆鐘總時間、每檔 tick 數(三者必須逐檔相等 = 正確性判準)、逾時檔。
只做 history 請求、**不 SUBQUOTE REALTIME**(不碰 prod 的 refcount key);盤後跑。

用法:.venv/Scripts/python spikes/stock_backfill_parallel_probe.py [--codes 20] [--threads 4] [--port 50774]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "spikes" / "TCPY"))

from copycat.live.stock_source import StockQuoteSource  # noqa: E402
from copycat.live.tc4 import HealPolicy, HistoryTimeoutError  # noqa: E402


def _codes(n: int) -> list[str]:
    d = json.loads((ROOT / "data" / "stock_watchlist.json").read_text(encoding="utf-8"))
    seen: list[str] = []
    for g in d.get("groups", []):
        for c in g.get("codes", []):
            if c not in seen:
                seen.append(c)
    return seen[:n]


def _one(src: StockQuoteSource, code: str) -> tuple[str, int | None, float]:
    t0 = time.monotonic()
    try:
        n = len(src.backfill(code))
    except HistoryTimeoutError:
        n = None
    return code, n, time.monotonic() - t0


def run_serial(src: StockQuoteSource, codes: list[str]) -> dict:
    t0 = time.monotonic()
    per = [_one(src, c) for c in codes]
    return {"wall": time.monotonic() - t0, "per": per}


def run_threads(src: StockQuoteSource, codes: list[str], n: int) -> dict:
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=n) as ex:
        per = list(ex.map(lambda c: _one(src, c), codes))
    return {"wall": time.monotonic() - t0, "per": per}


def run_batch(src: StockQuoteSource, codes: list[str]) -> dict:
    """先全訂再收割:直接呼叫 source 的私有 REQ helper(probe 專用,不進 prod)。"""
    from copycat.live.stock_source import stock_symbol, stock_window

    t0 = time.monotonic()
    start, end = stock_window(src._trade_date)
    for c in codes:
        src._sub_history(stock_symbol(c), start, end)
    t_sub = time.monotonic() - t0
    per = [_one(src, c) for c in codes]  # backfill 內的 SubHistory 冪等,首頁多半已備妥
    return {"wall": time.monotonic() - t0, "sub_wall": t_sub, "per": per}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", type=int, default=20)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--port", default="50774")
    ap.add_argument("--out", default=str(ROOT / "out" / "stock_backfill_parallel_probe.json"))
    args = ap.parse_args()

    codes = _codes(args.codes)
    src = StockQuoteSource(port=args.port, heal=HealPolicy(silence_secs=None, symbol_silence_secs=None))
    result: dict = {"codes": codes, "threads": args.threads}
    try:
        result["serial"] = run_serial(src, codes)
        result["batch"] = run_batch(src, codes)
        result["threads_run"] = run_threads(src, codes, args.threads)
    finally:
        src.close()  # Disconnect:一次性腳本不收工 process 不退(tc4-market-facts)

    def _summ(name: str, r: dict) -> None:
        ticks = {c: n for c, n, _ in r["per"]}
        timeouts = [c for c, n, _ in r["per"] if n is None]
        slowest = sorted(r["per"], key=lambda x: -x[2])[:3]
        print(
            f"{name:8s} wall={r['wall']:.1f}s  per-code avg={r['wall'] / len(codes):.2f}s  "
            f"timeouts={timeouts}  slowest={[(c, round(t, 2)) for c, _, t in slowest]}"
        )
        r["ticks"] = ticks

    _summ("serial", result["serial"])
    _summ("batch", result["batch"])
    _summ("threads", result["threads_run"])
    same = result["serial"]["ticks"] == result["batch"]["ticks"] == result["threads_run"]["ticks"]
    print("tick 數三者逐檔相等:", same)
    if not same:
        for c in codes:
            a, b, t = (result[k]["ticks"].get(c) for k in ("serial", "batch", "threads_run"))
            if not (a == b == t):
                print(f"  {c}: serial={a} batch={b} threads={t}")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("out:", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
