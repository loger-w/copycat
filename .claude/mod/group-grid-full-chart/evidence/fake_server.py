"""R4 群組圖牆取證用 fake-source server(零 TC4 / 零 ZMQ — ops-discipline)。

改自 `.claude/mod/trial-pause-badge/evidence/fake_server.py`(含 neutralize_external_env),差別:
  1. 20 檔種子 + 三個群組(6 / 16 / 17 檔)→ 驗 2×2~4×4 與 >16 捲動。
  2. `fetch_daily_bars` 給 25 根合成日 bar → overlay CDP / MA 可算(卡片疊線可截圖)。
  3. 全日回補(09:00–13:30)不看時鐘 → 週末也有整段分時 + VP。
  4. port 由 argv[1] 指定(預設 8721:prod 未起時直接讓 vite proxy 打到它)。
"""

from __future__ import annotations

import sys

sys.path.insert(0, r"C:\side-project\copycat")

import datetime as _dt
import json
import math
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

import uvicorn

# ⚠ 必須在 create_app 之前(ops-discipline:漏了會拿 .env 真憑證登入群益正式環境)
from copycat.server.verify import neutralize_external_env

neutralize_external_env()

from copycat.live.models import SeriesInfo, Tick
from copycat.live.stock_models import StockTick
from copycat.server.app import create_app
from tests.helpers.fake_sources import (
    FakeCorrSource,
    FakeFuturesSource,
    FakeIndexSource,
    FakeStockSource,
)

assert create_app.__module__.startswith("copycat"), "import 錨點檢查"

SERIES = SeriesInfo(series_id="TX4.202608", name="TX4 202608", expiry="202608", contracts=())


class FakeQuoteSource:
    def list_series(self) -> list[SeriesInfo]:
        return [SERIES]

    def fetch_backfill(self, series: SeriesInfo) -> list[Tick]:
        return []

    def subscribe(self, series: SeriesInfo, on_tick: Callable[[Tick], None]) -> None: ...

    def unsubscribe(self, series: SeriesInfo) -> None: ...

    def close(self) -> None: ...


_NAMES = [
    ("2330", "台積電", 1200.0, -1.4),
    ("2317", "鴻海", 200.0, 4.0),
    ("2454", "聯發科", 1400.0, 2.2),
    ("2308", "台達電", 420.0, -0.6),
    ("2382", "廣達", 300.0, 6.5),
    ("3231", "緯創", 110.0, -3.1),
    ("2303", "聯電", 48.0, 0.8),
    ("2881", "富邦金", 92.0, 1.1),
    ("2882", "國泰金", 70.0, -0.9),
    ("2412", "中華電", 128.0, 0.2),
    ("1301", "台塑", 38.0, -2.4),
    ("1303", "南亞", 33.0, 1.7),
    ("2002", "中鋼", 21.5, 0.5),
    ("2603", "長榮", 190.0, 8.9),
    ("2609", "陽明", 68.0, -5.2),
    ("3008", "大立光", 2600.0, 1.3),
    ("2357", "華碩", 620.0, -1.8),
    ("2379", "瑞昱", 560.0, 3.6),
    ("6505", "台塑化", 45.0, -0.3),
    ("2891", "中信金", 41.0, 0.9),
]
SEEDS: dict[str, tuple[str, float, float]] = {c: (n, r, d) for c, n, r, d in _NAMES}
CODES = [c for c, *_ in _NAMES]
GROUPS = [
    {"name": "四檔", "codes": CODES[:4]},
    {"name": "六檔", "codes": CODES[:6]},
    {"name": "十六檔", "codes": CODES[:16]},
    {"name": "十七檔", "codes": CODES[:17]},
]

_START_MIN = 9 * 60
_END_MIN = 13 * 60 + 30


def _tick(price_milli: int) -> int:
    for floor, t in ((1_000_000, 5000), (500_000, 1000), (100_000, 500), (50_000, 100), (10_000, 50)):
        if price_milli >= floor:
            return t
    return 10


def _price_milli(code: str, minute: int) -> int:
    _name, ref, drift = SEEDS[code]
    span = max(1, _END_MIN - _START_MIN)
    prog = (minute - _START_MIN) / span
    seed = sum(map(ord, code))
    wiggle = 0.006 * math.sin(minute / 7.0 + seed) + 0.003 * math.sin(minute / 2.3 + seed / 3)
    price = ref * (1 + drift / 100 * prog + wiggle)
    raw = int(round(price * 1000))
    t = _tick(raw)
    return raw // t * t


class SeededStockSource(FakeStockSource):
    def __init__(self) -> None:
        super().__init__()
        self._cum: dict[str, int] = {c: 0 for c in CODES}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def fetch_daily_bars(self, code: str, n: int = 25) -> list:
        if code not in SEEDS:
            return []
        _name, ref, _d = SEEDS[code]
        today = _dt.date.today()
        bars = []
        for i in range(n, 0, -1):
            d = today - _dt.timedelta(days=i)
            k = 1 + 0.02 * math.sin(i / 3.0)
            close = int(ref * 1000 * k) // 10 * 10
            bars.append({"date": f"{d:%Y-%m-%d}", "high": int(close * 1.012), "low": int(close * 0.988), "close": close})
        return bars

    def backfill(self, code: str) -> list[StockTick]:
        if code not in SEEDS:
            return []
        today = f"{_dt.date.today():%Y-%m-%d}"
        ticks: list[StockTick] = []
        cum = 0
        for minute in range(_START_MIN, _END_MIN + 1):
            for sub in (5, 35):
                price = _price_milli(code, minute) + (0 if sub == 5 else _tick(_price_milli(code, minute)) * ((minute % 3) - 1))
                qty = 5 + (minute * 7 + sub) % 60
                cum += qty
                ticks.append(
                    StockTick(
                        code=code,
                        price_milli=price,
                        qty=qty,
                        cum_vol=cum,
                        time=f"{minute // 60:02d}:{minute % 60:02d}:{sub:02d}.000",
                        trade_date=today,
                        side="outer" if (minute + sub) % 3 else "inner",
                        is_trial=False,
                        bid_milli=price - 50,
                        ask_milli=price,
                    )
                )
        self._cum[code] = max(self._cum[code], cum)
        return ticks

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        super().set_on_message(cb)
        if self._thread is None:
            self._thread = threading.Thread(target=self._push_loop, daemon=True)
            self._thread.start()

    def _realtime(self, code: str) -> dict:
        name, ref, _drift = SEEDS[code]
        base = _price_milli(code, _END_MIN)
        # 每次推播價位 ±1 tick 抖動:讓前端 liveP 真的每 2s 變一次(SC-6e 量測要走到 accum 重算路徑)
        price = base + _tick(base) * ((int(_dt.datetime.now().timestamp()) // 2) % 3 - 1)
        self._cum[code] += 11
        now_utc = _dt.datetime.now(_dt.timezone.utc)
        return {
            "Symbol": f"TC.S.TWS.{code}",
            "Security": code,
            "SecurityName": name,
            "ReferencePrice": f"{ref:.2f}",
            "UpperLimitPrice": f"{ref * 1.1:.2f}",
            "LowerLimitPrice": f"{ref * 0.9:.2f}",
            "YClosedPrice": f"{ref:.2f}",
            "YTradeVolume": "12345",
            "OpenTime": "90000",
            "CloseTime": "133000",
            "TradeStatus": "0",
            "Bid": f"{(price - 50) / 1000:.2f}",
            "BidVolume": "12",
            "Ask": f"{price / 1000:.2f}",
            "AskVolume": "8",
            "TradingPrice": f"{price / 1000:.2f}",
            "TradeQuantity": "11",
            "TradeVolume": str(self._cum[code]),
            "PreciseTime": f"{now_utc:%H%M%S}000000",
            "TradeDate": f"{now_utc:%Y%m%d}",
        }

    def _push_loop(self) -> None:
        while not self._stop.wait(2.0):
            cb = self.on_message
            if cb is None:
                continue
            for code in list(self.subscribed):
                if code in SEEDS:
                    try:
                        cb(self._realtime(code))
                    except Exception:  # noqa: BLE001 — fake 推播失敗不該弄倒 server
                        pass

    def close(self) -> None:
        self._stop.set()


tmp = Path(tempfile.mkdtemp(prefix="r4-grid-evidence-"))
wl_path = tmp / "watchlist.json"
wl_path.write_text(
    json.dumps({"version": 2, "codes": CODES, "groups": GROUPS}, ensure_ascii=False),
    encoding="utf-8",
)
print(f"watchlist: {wl_path}", flush=True)

app = create_app(
    FakeQuoteSource(),
    stock_source=SeededStockSource(),
    index_source=FakeIndexSource(),
    futures_source=FakeFuturesSource(),
    corr_source=FakeCorrSource(),
    stock_watchlist_path=wl_path,
)

port = int(sys.argv[1]) if len(sys.argv) > 1 else 8721
uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
