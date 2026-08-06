"""Phase 6 截圖用 fake-source server(零 TC4 / 零 ZMQ — 紀律)。port 8899。

改自 `.claude/feat/signal-rules/evidence/fake_server.py`,差別:
  1. `stock_watchlist_path` 指到 tmp 檔並**預先寫入含群組的 v3 watchlist**
     (玻璃 / 石英 / 測試空群),讓群組檢視的下拉與空態都有東西可看。
  2. `SeededStockSource`:per-code 合成當日分鐘資料(`backfill`)+ 背景 REALTIME
     推播(meta:name/ref/upper/lower + 現價),讓卡片的 mini 圖畫得出紅綠面積、
     右上角有價格與漲跌幅。

worktree 直跑腳本必釘 sys.path(CLAUDE.md §8)。
"""

from __future__ import annotations

import sys

sys.path.insert(0, r"C:\side-project\copycat\.claude\worktrees\feat-discord-watchlist")

import datetime as _dt
import json
import math
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path

import uvicorn

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


# ---- 合成標的:(名稱, 參考價元, 當日漂移%)----
SEEDS: dict[str, tuple[str, float, float]] = {
    "5483": ("中美晶", 100.0, 6.5),
    "1802": ("台玻", 25.0, -3.2),
    "3481": ("群創", 12.5, 2.1),
    "2330": ("台積電", 1200.0, -1.4),
    "2317": ("鴻海", 200.0, 4.0),
}

GROUPS = [
    {"name": "玻璃", "codes": ["5483", "1802", "3481"]},
    {"name": "石英", "codes": ["2330", "2317"]},
    {"name": "測試空群", "codes": []},
]
CODES = ["5483", "1802", "3481", "2330", "2317"]

_START_MIN = 9 * 60  # 09:00
_TRIAL_MIN = 13 * 60 + 24  # 13:24(13:25 起是試撮窗,ingest 會丟)


def _now_min() -> int:
    now = _dt.datetime.now()
    return now.hour * 60 + now.minute


def _last_min() -> int:
    """合成序列的最後一分鐘:盤中= 現在,盤外= 收在 13:24。"""
    return max(_START_MIN + 30, min(_now_min(), _TRIAL_MIN))


def _price_milli(code: str, minute: int) -> int:
    """ref 出發、朝 drift 走的一條有波動的路徑;毫元、對齊 0.05 元。"""
    _name, ref, drift = SEEDS[code]
    span = max(1, _TRIAL_MIN - _START_MIN)
    prog = (minute - _START_MIN) / span
    wiggle = 0.004 * math.sin(minute / 7.0) + 0.002 * math.sin(minute / 2.3)
    price = ref * (1 + drift / 100 * prog + wiggle)
    return int(round(price * 1000 / 50)) * 50


class SeededStockSource(FakeStockSource):
    """FakeStockSource + per-code 合成回補 + 背景 REALTIME 推播(meta / 現價)。"""

    def __init__(self) -> None:
        super().__init__()
        self._cum: dict[str, int] = {c: 0 for c in CODES}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- 回補:09:00 → 現在,每分鐘一筆 --
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
        # live 推播的 cum 一定要比回補上限大,否則 apply_backfill 會把它當重疊窗丟掉
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
            "Bid1": f"{(price - 100) / 1000:.2f}",
            "BidVolume1": "20",
            "Ask": f"{price / 1000:.2f}",
            "AskVolume": "8",
            "Ask1": f"{(price + 50) / 1000:.2f}",
            "AskVolume1": "15",
            "TradingPrice": f"{price / 1000:.2f}",
            "TradeQuantity": "11",
            "TradeVolume": str(self._cum[code]),
            # PreciseTime = UTC HHMMSSffffff(12 位;parse 層 +8 轉台北)
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


tmp = Path(tempfile.mkdtemp(prefix="group-grid-shot-"))
wl_path = tmp / "watchlist.json"
wl_path.write_text(
    json.dumps({"codes": CODES, "groups": GROUPS}, ensure_ascii=False),
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

uvicorn.run(app, host="127.0.0.1", port=8899, log_level="warning")
