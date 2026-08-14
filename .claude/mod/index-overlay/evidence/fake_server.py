"""index-overlay real-env 取證側車(零 TC4 / 零 ZMQ — ops-discipline)。port 8721(prod 未跑)。

改自 `.claude/mod/trial-pause-badge/evidence/fake_server.py`。用途:
  1. `GET /api/index/overlay` happy / 今日 partial 剔除(SC-5 HTTP 層)。
  2. 前端截圖:加權/櫃買分時 + 均價線 + CDP/MA 疊線(域內線與域外掛牌混合)+ 昨收標籤
     (SC-1/2/3/4/6)。
治具設計:昨日 H/L/C = 24350/24050/24300 → cdp 24250(域內)/ nh 24450(域內)/
ah 24550(域外↑)/ nl 24150(域外↓)/ al 23950(域外↓);日線 ramp 使 ma5 域內、
ma20 域外↓。今日分時 24240..24440(ref 24300)。
"""

from __future__ import annotations

import sys

sys.path.insert(0, r"C:\side-project\copycat")

import datetime as _dt
import json
import math
import tempfile
import threading
import time as _time
from pathlib import Path

import uvicorn

# ⚠ 必須在 create_app 使用之前(ops-discipline:漏了會拿 .env 真憑證)
from copycat.server.verify import neutralize_external_env

neutralize_external_env()

from copycat.server.app import create_app
from copycat.server.mis import OtcSnap
from tests.helpers.fake_sources import (
    FakeCorrSource,
    FakeFuturesSource,
    FakeIndexSource,
    FakeStockSource,
)

assert create_app.__module__.startswith("copycat"), "import 錨點檢查"

REF = 24_300_000  # 加權昨收(毫點)
TODAY = _dt.date.today()


def _weekdays_back(n: int) -> list[_dt.date]:
    """昨日往回 n 個平日(升冪)。"""
    out: list[_dt.date] = []
    d = TODAY - _dt.timedelta(days=1)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= _dt.timedelta(days=1)
    return list(reversed(out))


def _daily_bars() -> list[dict]:
    days = _weekdays_back(25)
    bars: list[dict] = []
    for i, d in enumerate(days):
        c = 23_600_000 + int((24_300_000 - 23_600_000) * i / (len(days) - 1))
        bars.append({"t": f"{d:%Y-%m-%d}", "o": c, "h": c + 60_000, "l": c - 60_000, "c": c, "v": 10})
    # 昨日(最後一根完成 bar)覆寫成 CDP 治具值
    bars[-1] = {
        "t": bars[-1]["t"], "o": 24_250_000, "h": 24_350_000, "l": 24_050_000,
        "c": 24_300_000, "v": 10,
    }
    # 今日 partial(build_overlay 必須剔除;值刻意怪異,混入即肉眼可見)
    bars.append({"t": f"{TODAY:%Y-%m-%d}", "o": 99_000_000, "h": 99_900_000, "l": 98_000_000, "c": 99_500_000, "v": 1})
    return bars


def _twse_minutes() -> dict[str, int]:
    """0901..1330;24240..24440 帶波動。"""
    out: dict[str, int] = {}
    start, end = 9 * 60, 13 * 60 + 30
    span = end - start
    for m in range(start + 1, end + 1):
        prog = (m - start) / span
        p = REF + int(
            60_000 * prog
            + 80_000 * math.sin(prog * math.pi * 1.3)
            + 12_000 * math.sin(m / 5.0)
        )
        p = max(24_240_000, min(24_440_000, p))
        out[f"{m // 60:02d}{m % 60:02d}"] = p
    return out


TWSE_MIN = _twse_minutes()
TWSE_LAST = TWSE_MIN[max(TWSE_MIN)]

# ---- OTC:mis_fetch 逐呼叫吐下一分鐘(側車把 engine._poll 調小加速灌入)----

OTC_REF = 240_000
_otc_steps: list[OtcSnap] = []
_hi, _lo = OTC_REF, OTC_REF
for m in range(9 * 60, 13 * 60 + 31):
    prog = (m - 9 * 60) / (4.5 * 60)
    p = OTC_REF + int(3_000 * math.sin(prog * math.pi * 1.7) + 1_500 * prog + 600 * math.sin(m / 3.0))
    _hi, _lo = max(_hi, p), min(_lo, p)
    _otc_steps.append(
        OtcSnap(p=p, ref=OTC_REF, open=_otc_steps[0]["p"] if _otc_steps else p, high=_hi, low=_lo,
                time=f"{m // 60:02d}{m % 60:02d}30")
    )

_otc_lock = threading.Lock()
_otc_i = 0


def fake_mis_fetch() -> OtcSnap | None:
    global _otc_i
    with _otc_lock:
        snap = _otc_steps[min(_otc_i, len(_otc_steps) - 1)]
        _otc_i += 1
        return snap


# ---- TWSE 推播(ref/high/low/現價;歷史分鐘由 fetch_day_minutes 回補)----

index_src = FakeIndexSource(day_minutes=TWSE_MIN, tag="tc4_dk", daily_bars=_daily_bars())


def _push_loop() -> None:
    while True:
        _time.sleep(1.0)
        cb = index_src.on_message
        if cb is None:
            continue
        now_utc = _dt.datetime.now(_dt.timezone.utc)
        try:
            cb({
                "Security": "IX0001",
                "TradingPrice": f"{TWSE_LAST / 1000:.2f}",
                "ReferencePrice": f"{REF / 1000:.2f}",
                "HighPrice": "24440.00",
                "LowPrice": "24240.00",
                "FilledTime": f"{now_utc:%H%M%S}",
            })
        except Exception:  # noqa: BLE001 — fake 推播失敗不該弄倒 server
            pass


threading.Thread(target=_push_loop, daemon=True).start()

tmp = Path(tempfile.mkdtemp(prefix="index-overlay-evidence-"))
wl_path = tmp / "watchlist.json"
wl_path.write_text(json.dumps({"codes": [], "groups": []}, ensure_ascii=False), encoding="utf-8")
print(f"isolated dir: {tmp}", flush=True)

app = create_app(
    stock_source=FakeStockSource(),
    index_source=index_src,
    futures_source=FakeFuturesSource(),
    corr_source=FakeCorrSource(),
    index_mis_fetch=fake_mis_fetch,
    stock_watchlist_path=wl_path,
)


def _accelerate_mis() -> None:
    """等 index engine 起來後把 MIS poll 間隔調小,快速灌完 OTC 全日分鐘後恢復。"""
    while getattr(app.state, "index", None) is None:
        _time.sleep(0.2)
    app.state.index._poll = 0.02  # noqa: SLF001 — 側車取證專用
    while _otc_i < len(_otc_steps):
        _time.sleep(0.5)
    app.state.index._poll = 5.0
    print("OTC minutes seeded", flush=True)


threading.Thread(target=_accelerate_mis, daemon=True).start()

uvicorn.run(app, host="127.0.0.1", port=8721, log_level="warning")
