"""實驗 B(黃金重現):重演 prod boot 的「空窗 SubHistory 毒化」→ heal 重抓失效。

序列(全部台北時間,對 UTC05 窗 = 13:00-14:00):
1. 立即(窗仍空):subscribe_symbol(REALTIME) + SubHistory(1K, 05-06 窗)+ 輪詢 30s
   到 timeout(= prod boot 08:00 的行為)。session 保持存活。
2. 13:01 起每 60s 重演 heal(subscribe_symbol 重掛 + _collect_history 同窗口),
   dump 原始結果(rows 數 / 首列原文)。跑 6 輪或連兩輪拿到資料即停。
3. 對照 C1:同 session、不同窗口(00-06)fetch → 應含 13:0x 根。
   對照 C2:全新 session、同窗口(05-06)fetch。
4. close 全部(KeepAlive §0a)。
"""

import datetime as dt
import logging
import sys
import time

sys.path.insert(0, r"C:\side-project\copycat")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
)

from copycat.live.stock_source import StockQuoteSource
from copycat.tc4common import iter_qry_pages

SYM = "TC.S.TWS.IX0001"
W_START, W_END = "2026081405", "2026081406"  # UTC05 窗 = 台北 13:00-14:00


def log(msg: str) -> None:
    print(f"[{dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def collect(
    src: StockQuoteSource, start: str, end: str, budget: float = 30.0
) -> list[dict]:
    """_collect_history 等價(SubHistory → 輪詢首頁 → 收割),回原始 rows。"""
    src._sub_history(SYM, start, end, "1K")

    def page(qry_index: str) -> list[dict]:
        return src._get_history(SYM, start, end, qry_index, "1K").get("HisData", [])

    deadline = time.monotonic() + budget
    while time.monotonic() < deadline:
        if page("0"):
            break
        time.sleep(0.5)
    else:
        return []
    rows: list[dict] = []
    for p in iter_qry_pages(page):
        rows.extend(p)
    return rows


def summarize(rows: list[dict]) -> str:
    if not rows:
        return "EMPTY"
    head = {k: rows[0].get(k) for k in ("Date", "Time", "Close", "QryIndex")}
    tail = {k: rows[-1].get(k) for k in ("Date", "Time", "Close", "QryIndex")}
    return f"{len(rows)} rows head={head} tail={tail}"


s2 = StockQuoteSource(trade_date="2026-08-14")
try:
    # --- 1) 空窗毒化(= boot) ---
    s2.subscribe_symbol("IX0001")
    log("S2 REALTIME 訂閱完成;開始空窗 SubHistory(05-06)輪詢 30s")
    rows = collect(s2, W_START, W_END, budget=30.0)
    log(f"boot 重演結果:{summarize(rows)}(預期 EMPTY = timeout 靜默回空)")

    # --- 2) 等到 13:01,逐分鐘重演 heal ---
    target = dt.datetime.now().replace(hour=13, minute=1, second=10, microsecond=0)
    wait = (target - dt.datetime.now()).total_seconds()
    if wait > 0:
        log(f"等待 {wait:.0f}s 至 13:01:10(窗內首根 1301 應已生成)")
        time.sleep(wait)

    got_data_rounds = 0
    for rnd in range(1, 7):
        s2.subscribe_symbol("IX0001")  # heal 的重掛 REALTIME
        rows = collect(s2, W_START, W_END, budget=30.0)
        log(f"heal 重演 #{rnd}:{summarize(rows)}")
        if rows:
            got_data_rounds += 1
            if got_data_rounds >= 2:
                break
        else:
            got_data_rounds = 0
        time.sleep(60)

    # --- 3) 對照 ---
    rows_c1 = collect(s2, "2026081400", "2026081406", budget=30.0)
    log(f"對照 C1(同 session、換窗口 00-06):{summarize(rows_c1)}")

    s3 = StockQuoteSource(trade_date="2026-08-14")
    try:
        rows_c2 = collect(s3, W_START, W_END, budget=30.0)
        log(f"對照 C2(新 session、同窗口 05-06):{summarize(rows_c2)}")
    finally:
        s3.close()
finally:
    s2.close()
    log("closed")
