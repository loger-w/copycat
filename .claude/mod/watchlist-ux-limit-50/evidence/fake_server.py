"""SC-1/3/4 real-env 取證用 fake-source server(零 TC4 / 零 ZMQ — ops-discipline)。

改自 `.claude/mod/trial-pause-badge/evidence/fake_server.py`,差別:
  1. port 8721(prod 已停、盤外;vite proxy 寫死 8721,免改 vite.config)—— 取證完必殺。
  2. 種子自選 6 檔 + 2 群組(觀察/航運)+ 未分組 2 檔:驗群組標題列視覺(SC-3)與
     全部展開/收合(SC-4)。
  3. SC-1 邊界 curl(PUT 50/51、group-state 50/51)後以種子 PUT 還原。
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

# ⚠ 必須在 create_app 之前:壓制 CAPITAL_* / DISCORD_* / FINMIND(auto-verify 紀律
# 2026-08-06;凡起真 create_app 的腳本開頭沒有 neutralize = 不合格)。
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


SEEDS: dict[str, tuple[str, float, float]] = {
    "2330": ("台積電", 1200.0, -1.4),
    "2317": ("鴻海", 200.0, 4.0),
    "2454": ("聯發科", 1400.0, 2.1),
    "2603": ("長榮", 210.0, -2.8),
    "2609": ("陽明", 72.0, 9.6),
    "3231": ("緯創", 110.0, 0.6),
}
CODES = list(SEEDS)
WATCHLIST = {
    "codes": CODES,
    "groups": [
        {"name": "觀察", "codes": ["2330", "2454"]},
        {"name": "航運", "codes": ["2603", "2609"]},
    ],
}

_START_MIN = 9 * 60
_TRIAL_MIN = 13 * 60 + 24


def _now_min() -> int:
    now = _dt.datetime.now()
    return now.hour * 60 + now.minute


def _last_min() -> int:
    return max(_START_MIN + 30, min(_now_min(), _TRIAL_MIN))


def _price_milli(code: str, minute: int) -> int:
    _name, ref, drift = SEEDS[code]
    span = max(1, _TRIAL_MIN - _START_MIN)
    prog = (minute - _START_MIN) / span
    wiggle = 0.004 * math.sin(minute / 7.0) + 0.002 * math.sin(minute / 2.3)
    price = ref * (1 + drift / 100 * prog + wiggle)
    return int(round(price * 1000 / 50)) * 50


class SeededStockSource(FakeStockSource):
    def __init__(self) -> None:
        super().__init__()
        self._cum: dict[str, int] = {c: 0 for c in CODES}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def backfill(self, code: str) -> list[StockTick]:
        if code not in SEEDS:
            return []
        today = f"{_dt.date.today():%Y-%m-%d}"
        ticks: list[StockTick] = []
        cum = 0
        end = _last_min()
        for minute in range(_START_MIN, end + 1):
            price = _price_milli(code, minute)
            qty = 30 + (minute * 7) % 120
            cum += qty
            ticks.append(
                StockTick(
                    code=code,
                    price_milli=price,
                    qty=qty,
                    cum_vol=cum,
                    time=f"{minute // 60:02d}:{minute % 60:02d}:30.000",
                    trade_date=today,
                    side="outer" if minute % 3 else "inner",
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
        minute = _last_min()
        price = _price_milli(code, minute)
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
            for code in self.subscribed:
                if code in SEEDS:
                    try:
                        cb(self._realtime(code))
                    except Exception:  # noqa: BLE001 — fake 推播失敗不該弄倒 server
                        pass

    def close(self) -> None:
        self._stop.set()


tmp = Path(tempfile.mkdtemp(prefix="wl-limit50-evidence-"))
wl_path = tmp / "watchlist.json"
wl_path.write_text(json.dumps(WATCHLIST, ensure_ascii=False), encoding="utf-8")
print(f"watchlist: {wl_path}", flush=True)

app = create_app(
    FakeQuoteSource(),
    stock_source=SeededStockSource(),
    index_source=FakeIndexSource(),
    futures_source=FakeFuturesSource(),
    corr_source=FakeCorrSource(),
    stock_watchlist_path=wl_path,
)

uvicorn.run(app, host="127.0.0.1", port=8721, log_level="warning")
