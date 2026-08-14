"""活體 probe:模仿 index_engine._subscribe_and_backfill 對 IX0001 的 1K 回補。

蒐證用(fix/index-line-vanish):dump 原始 rows 的 Time/Close、domain 過濾統計,
裁決「heal fetch 快速返回但 minutes 空」的成因。收工必 close()(KeepAlive §0a)。
"""

import logging
import sys

sys.path.insert(0, r"C:\side-project\copycat")
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
)

from copycat.live.stock_source import StockQuoteSource, stock_window, _taipei_minute_key

TRADE_DATE = "2026-08-14"
SYM = "TC.S.TWS.IX0001"

src = StockQuoteSource(trade_date=TRADE_DATE)
try:
    src.subscribe_symbol("IX0001")
    print("REALTIME resub OK", flush=True)
    start, end = stock_window(TRADE_DATE)
    print("window:", start, end, flush=True)
    res = src._collect_history(SYM, "1K", start, end)
    rows = res.rows
    print("timed_out:", res.timed_out, "rows:", len(rows), flush=True)
    for r in rows[:5]:
        print(
            "HEAD",
            {k: r.get(k) for k in ("Date", "Time", "Close", "Volume", "QryIndex")},
        )
    for r in rows[-5:]:
        print("TAIL", {k: r.get(k) for k in ("Date", "Time", "Close", "QryIndex")})
    minutes = {}
    dropped: list[str] = []
    skipped = 0
    for r in rows:
        try:
            key = _taipei_minute_key(str(r["Time"]))
            value = round(float(r["Close"]) * 1000)
        except (KeyError, ValueError):
            skipped += 1
            continue
        if key is None:
            dropped.append(str(r.get("Time")))
            continue
        minutes[key] = value
    print(
        "parsed:",
        len(minutes),
        "min:",
        min(minutes) if minutes else None,
        "max:",
        max(minutes) if minutes else None,
        "skipped:",
        skipped,
    )
    print("domain-dropped:", len(dropped), "sample:", dropped[:10])
finally:
    src.close()
    print("closed", flush=True)
