"""離線對照(issue #174):鼎元 2426 2026-09-01 真 1K 餵 surge_pullback 狀態機。

bar `t` 是終點標記;每根依 o→h/l(依漲跌序)→c 展成 4 筆 tick,時鐘取 bar 終點。
兩顆 detector = 種子兩張卡(5 分鐘 +2% 武裝,回檔 1% / 2%)。
可重跑:輸入 `bars_2426.json` 同目錄入版控;repo root 由本檔位置推導
(pr-177 review F-12 —— 初版硬編一個收尾即刪的 worktree 絕對路徑)。
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from dataclasses import replace
from pathlib import Path

# parents: [0]=evidence [1]=surge-pullback-signal [2]=feat [3]=.claude [4]=repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from copycat.live.signal_state import SignalDetector, TickContext  # noqa: E402
from copycat.live.stock_models import StockTick  # noqa: E402
from copycat.signals_config import SignalsConfig  # noqa: E402

bars = json.loads((Path(__file__).parent / "bars_2426.json").read_text(encoding="utf-8-sig"))[
    "bars"
]
day = [b for b in bars if b["t"].startswith("2026-09-01")]
print(f"2026-09-01 bars: {len(day)}")

CTX = TickContext(
    trade_date="2026-09-01",
    upper_milli=None,
    lower_milli=None,
    ask_limit_available=True,
    bid_limit_available=True,
    bids0_is_market=False,
    asks0_is_market=False,
    best_bid_limit_milli=None,
    best_ask_limit_milli=None,
    day_volume=0,
)
ENABLED = frozenset({"surge_pullback"})


class Clock:
    def __init__(self) -> None:
        self.now = dt.datetime(2026, 9, 1, 9, 0, 0)

    def __call__(self) -> dt.datetime:
        return self.now


def run(pct: float) -> list[str]:
    clock = Clock()
    cfg = replace(SignalsConfig(), surge_pct=2.0, surge_window_secs=300.0, pullback_pct=pct)
    det = SignalDetector(cfg, now_fn=clock)
    out: list[str] = []
    for bar in day:
        end = dt.datetime.strptime(bar["t"], "%Y-%m-%d %H:%M")
        prices = [bar["o"]]
        prices += [bar["h"], bar["l"]] if bar["c"] < bar["o"] else [bar["l"], bar["h"]]
        prices.append(bar["c"])
        for i, price in enumerate(prices):
            clock.now = end - dt.timedelta(seconds=45 - i * 15)
            tick = StockTick(
                code="2426",
                price_milli=price,
                qty=1,
                cum_vol=0,
                time=f"{clock.now:%H:%M:%S}.000",
                trade_date="2026-09-01",
                side="neutral",
                is_trial=False,
            )
            for ev in det.evaluate("2426", tick, CTX, ENABLED):
                out.append(
                    f"{ev.time} {ev.kind} price={ev.price_milli / 1000:.1f} 回檔 {ev.pct:.2f}%"
                )
    return out


for pct in (1.0, 2.0):
    events = run(pct)
    print(f"\n== 回檔 {pct}% 卡:{len(events)} 則 ==")
    for line in events:
        print(" ", line)
