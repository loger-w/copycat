"""fix/dk-frozen-snapshot 真環境驗證:本 repo 的 FuturesQuoteSource 直連 TC4,
同參數兩刷夾行情 —— 修前第二刷 = 凍結快照,修後(_next_dk_start,原名
_dk_start_variant、收修改名)= 前進值。

自己的 session;base 窗 start=today−30d / end=明日(≠ prod 的 −1825d/today),不訂 REALTIME。
原始實跑(2026-09-01 16:52,PASS)在出貨用的臨時 worktree 上執行;路徑已改為由檔案
位置回推 repo root(pr-171-review F-10:舊寫法硬綁已刪除的 worktree,重跑必炸)。
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from copycat.live.futures_source import FuturesQuoteSource  # noqa: E402


def main() -> int:
    today = dt.date.today()
    start = (today - dt.timedelta(days=30)).isoformat()
    end = (today + dt.timedelta(days=1)).isoformat()
    src = FuturesQuoteSource()
    try:
        b1 = src.fetch_bars_range("TXF", "D", start, end)
        print(f"fetch1 {time.strftime('%H:%M:%S')} last={json.dumps(b1[-1])}", flush=True)
        assert b1[0]["t"] >= start, f"頭部越界:{b1[0]['t']} < {start}"
        print("sleep 150s 等行情前進 …", flush=True)
        time.sleep(150)
        b2 = src.fetch_bars_range("TXF", "D", start, end)
        print(f"fetch2 {time.strftime('%H:%M:%S')} last={json.dumps(b2[-1])}", flush=True)
        assert b2[0]["t"] >= start, f"頭部越界:{b2[0]['t']} < {start}"
        assert b2[-1] != b1[-1], "FAIL:第二刷仍是凍結快照(末根逐字節同)"
        print("PASS:同參數第二刷取到前進值(variant 逃逸在真 TC4 生效)+ 頭部過濾成立")
    finally:
        src.close()
        print("closed", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
