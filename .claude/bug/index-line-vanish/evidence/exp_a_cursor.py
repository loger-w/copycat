"""實驗 A:同 session 消耗完分頁 cursor 後,重送同窗口 SubHistory,GETHISDATA("0") 回什麼?

裁決「heal 重抓同窗口拿不到東西」是否僅需 cursor 消耗即可重現(不需 boot 空窗態)。
"""

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
START, END = "2026081400", "2026081406"

src = StockQuoteSource(trade_date="2026-08-14")
try:
    src._ensure_connected()

    def page(qry_index: str) -> list[dict]:
        return src._get_history(SYM, START, END, qry_index, "1K").get("HisData", [])

    # 1) SUBQUOTE + 全量收割(消耗 cursor 到空頁)
    src._sub_history(SYM, START, END, "1K")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if page("0"):
            break
        time.sleep(0.5)
    rows = []
    for p in iter_qry_pages(page):
        rows.extend(p)
    print(
        f"[1] 首抓 rows={len(rows)} last_qry={rows[-1]['QryIndex'] if rows else None}",
        flush=True,
    )

    # 2) 立即再問 GETHISDATA("0")(不重送 SubHistory)
    p0 = page("0")
    print(
        f"[2] 不重送、直接 GETHISDATA(0) → {len(p0)} rows;首列={p0[0] if p0 else None}",
        flush=True,
    )

    # 3) 重送同窗口 SubHistory 後再問 "0"(= heal 的 _collect_history 行為)
    src._sub_history(SYM, START, END, "1K")
    got = None
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        p0b = page("0")
        if p0b:
            got = p0b
            break
        time.sleep(0.5)
    if got is None:
        print("[3] 重送後 GETHISDATA(0):30s 內恆空(= timeout 路徑)", flush=True)
    else:
        print(f"[3] 重送後 GETHISDATA(0) → {len(got)} rows;首列={got[0]}", flush=True)

    # 4) 從上次 cursor 續抓(報告 §7 增量模式對照)
    last = rows[-1]["QryIndex"] if rows else "0"
    inc = page(str(last))
    print(
        f"[4] 從 QryIndex={last} 續抓 → {len(inc)} rows;首列={inc[0] if inc else None}",
        flush=True,
    )
finally:
    src.close()
    print("closed", flush=True)
