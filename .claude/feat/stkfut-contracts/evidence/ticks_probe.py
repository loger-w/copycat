"""D4 spike:個股期 leaf 的 TICKS / 1K 當日歷史可得性(一次性,收工 Disconnect)。

安全窗執行(13:45–15:00 之間,日盤已收夜盤未開);只 SubHistory 不訂 REALTIME。
worktree 直跑必釘 sys.path。
"""

from __future__ import annotations

import datetime as dt
import sys

sys.path.insert(0, r"C:\side-project\copycat\.claude\worktrees\feat-discord-watchlist")

from copycat.live.tc4 import BARS_POLL_DEADLINE, TC4QuoteSource

SYM = "TC.F.TWF.CDF.202608"  # 台積電個股期近月(2026-08-19 到期,未到期)
today = dt.date.today()
start = f"{today:%Y%m%d}00"
end = f"{today:%Y%m%d}23"

src = TC4QuoteSource()
try:
    src._ensure_connected()
    for dtype in ("TICKS", "1K"):
        try:
            res = src._collect_history(SYM, dtype, start, end, BARS_POLL_DEADLINE)
            rows = res.rows
            print(f"{dtype}: rows={len(rows)}")
            for r in rows[:2]:
                print(
                    "  head:",
                    {
                        k: r.get(k)
                        for k in ("Date", "Time", "Price", "Close", "Volume", "Qty", "TradeVolume")
                    },
                )
            for r in rows[-2:]:
                print(
                    "  tail:",
                    {k: r.get(k) for k in ("Date", "Time", "Price", "Close", "Volume", "Qty")},
                )
        except Exception as e:  # 一次性 probe:任何失敗都要印出來人工判讀
            print(f"{dtype}: FAIL {type(e).__name__}: {e}")
finally:
    try:
        src.close()
    except Exception as e:
        print("close:", e)
