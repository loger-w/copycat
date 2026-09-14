"""0-1 冷歷史取數:首頁輪詢起點 `_POLL_BACKOFF_START` 的牆鐘成本(before / after 同一把尺)。

假 TC4:SUBQUOTE 後首頁備妥時刻依 `--ready-dist`:`exp`(預設)= 15 ms + Exp(mean 5 ms) 截到 40 ms,
對齊 C1 §4.1 的掃描(輪詢間隔 0 時首頁備妥 p50 15.5 ms、間隔 20 ms 時 p50 22.3 ms = 過半在首輪
20 ms 就備妥);`uniform` = [ready_lo, ready_hi] 均勻(悲觀:退避倍增後第二輪落在 ~61 ms)。
GETHISDATA qi=0 備妥前回空頁、備妥後回一列;其餘頁回空。每檔互異 symbol = 真冷取。
量兩條路徑:`tc4._collect_history`(stock DK)與 `river_backfill.collect_1k_minutes`(江波圖 1K)。

用法:python bench_01_history_poll.py [--repo <root>] [--n 30] [--ready-ms 15,40] [--timer-1ms]
`--repo` 指向要量的那份 code(主樹 = baseline;worktree = after)。stdlib-only。
`--timer-1ms` = 套 0-3 組態(EcoQoS 豁免 + timeBeginPeriod(1)):本 harness 由工具起、無視窗,
Windows 11 EcoQoS 約 3 秒後忽略高解析 timer,`time.sleep(0.02)` 會被拉到 ~31–47 ms,
量到的是 timer quantum 不是輪詢起點 —— 批 B 的 prod 同時有 0-3,prod-like 數字以此旗標為準。
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time

ROW = {
    "Date": "20260912",
    "Open": "100",
    "High": "101",
    "Low": "99",
    "Close": "100.5",
    "Volume": "100",
    "QryIndex": "1",
}


def timer_1ms() -> None:
    import ctypes
    import ctypes.wintypes as wt

    class PPT(ctypes.Structure):
        _fields_ = [("Version", wt.ULONG), ("ControlMask", wt.ULONG), ("StateMask", wt.ULONG)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetCurrentProcess.restype = wt.HANDLE
    k32.SetProcessInformation.restype = wt.BOOL
    k32.SetProcessInformation.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD]
    st = PPT(1, 0x1 | 0x4, 0)
    assert k32.SetProcessInformation(k32.GetCurrentProcess(), 4, ctypes.byref(st), ctypes.sizeof(st))
    assert ctypes.WinDLL("winmm").timeBeginPeriod(1) == 0


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round((len(xs) - 1) * p)))]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=r"C:\side-project\copycat")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--ready-ms", default="15,40")
    ap.add_argument("--ready-dist", choices=("exp", "uniform"), default="exp")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--timer-1ms", action="store_true")
    a = ap.parse_args()
    sys.path.insert(0, a.repo)
    random.seed(a.seed)
    if a.timer_1ms:
        timer_1ms()

    from copycat.live import river_backfill, tc4
    from copycat.live.stock_source import StockQuoteSource
    from tests.helpers.tc4_fakes import FakeApi, ok

    lo, hi = (float(x) / 1000 for x in a.ready_ms.split(","))

    def ready_after() -> float:
        if a.ready_dist == "uniform":
            return random.uniform(lo, hi)
        return min(lo + random.expovariate(1 / 0.005), hi)

    ready: dict[str, float] = {}
    polls = {"n": 0}

    def handler(obj: dict) -> bytes:
        req = obj["Request"]
        if req == "SUBQUOTE":
            ready[obj["Param"]["Symbol"]] = time.perf_counter() + ready_after()
            return ok()
        if req == "GETHISDATA":
            polls["n"] += 1
            sym = obj["Param"]["Symbol"]
            qi = obj["Param"]["QryIndex"]
            is_ready = sym in ready and time.perf_counter() >= ready[sym]
            rows = [ROW] if (is_ready and qi == "0") else []
            dtype = obj["Param"]["SubDataType"]
            return (f"{dtype}:" + json.dumps({"Success": "OK", "HisData": rows}) + "\0").encode()
        return ok()

    src = StockQuoteSource(
        api=FakeApi(handler), session="s1", trade_date="2026-09-15", poll_wait_secs=1.0
    )

    # ---- 路徑 A:tc4._collect_history(stock DK,冷取)----
    walls_a: list[float] = []
    polls_a: list[int] = []
    for i in range(a.n):
        polls["n"] = 0
        t0 = time.perf_counter()
        res = src._collect_history(f"TC.S.TWS.{9000 + i}", "DK", "20260801", "20260912")
        walls_a.append((time.perf_counter() - t0) * 1000)
        polls_a.append(polls["n"])
        assert not res.timed_out and len(res.rows) == 1, res

    # ---- 路徑 B:river_backfill.collect_1k_minutes(江波圖 1K 首頁輪詢)----
    utc_day = river_backfill.all_day_utc_window()[0][:8]
    row_1k = {"Date": utc_day, "Time": "0900", "Open": "22000", "High": "22010", "Low": "21990",
              "Close": "22005", "Volume": "10", "QryIndex": "1"}

    def sub_history(symbol: str, start: str, end: str, dtype: str) -> None:
        ready[symbol] = time.perf_counter() + ready_after()

    def get_history(symbol: str, start: str, end: str, qi: str, dtype: str) -> dict:
        polls["n"] += 1
        is_ready = symbol in ready and time.perf_counter() >= ready[symbol]
        return {"HisData": ([row_1k] if (is_ready and qi == "0") else [])}

    walls_b: list[float] = []
    polls_b: list[int] = []
    for i in range(a.n):
        polls["n"] = 0
        t0 = time.perf_counter()
        try:
            river_backfill.collect_1k_minutes(
                sub_history=sub_history,
                get_history=get_history,
                symbol=f"TC.F.TWF.FITX.{i}",
                poll_wait=1.0,
            )
        except tc4.HistoryTimeoutError:
            raise
        except Exception:
            # 假列不是合法 1K 列,收割解析炸掉不影響「首頁輪詢」這段的牆鐘量測
            pass
        walls_b.append((time.perf_counter() - t0) * 1000)
        polls_b.append(polls["n"])

    out = {
        "repo": a.repo,
        "poll_backoff_start": {
            "tc4": tc4._POLL_BACKOFF_START,
            "river_backfill": river_backfill._POLL_BACKOFF_START,
        },
        "ready_ms": a.ready_ms,
        "ready_dist": a.ready_dist,
        "timer_1ms": a.timer_1ms,
        "n": a.n,
        "tc4_collect_history_ms": {
            "p50": round(pct(walls_a, 0.5), 1),
            "p90": round(pct(walls_a, 0.9), 1),
            "max": round(max(walls_a), 1),
            "mean": round(statistics.fmean(walls_a), 1),
            "polls_mean": round(statistics.fmean(polls_a), 2),
        },
        "river_collect_1k_ms": {
            "p50": round(pct(walls_b, 0.5), 1),
            "p90": round(pct(walls_b, 0.9), 1),
            "max": round(max(walls_b), 1),
            "mean": round(statistics.fmean(walls_b), 1),
            "polls_mean": round(statistics.fmean(polls_b), 2),
        },
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
