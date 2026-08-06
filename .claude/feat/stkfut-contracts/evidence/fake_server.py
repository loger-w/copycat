"""Phase 6 截圖用 fake-source server(零 TC4 / 零 ZMQ — 紀律)。port 8899。

改自 `.claude/feat/group-grid/evidence/fake_server.py`,差別:
  1. `SeededStockSource.list_stock_futures()` 回 2330 的個股期目錄(標準 CDF / 小型 QFF),
     讓 `/api/stock/stkfut/contracts/2330` 有東西可回、header 的合約下拉畫得出來。
  2. instrument key 泛化:`F:<prod>:<ym>` 也有合成回補(08:45–13:45,個股期日盤窗)
     與 REALTIME 推播(SecurityName「台積電期08」/ 五檔 / ref / 漲跌停)。
  3. 推播時刻**合成在盤別窗內**(不是本機時鐘):engine 的 `_in_futures_session`
     對窗外的期貨推播是整則早退,盤後跑截圖時 meta 會整個拿不到。

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
from copycat.market import tick_size_milli
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


# ---- 合成現貨標的:(名稱, 參考價元, 當日漂移%)----
SEEDS: dict[str, tuple[str, float, float]] = {
    "2330": ("台積電", 1200.0, -1.4),
    "2317": ("鴻海", 200.0, 4.0),
    "5483": ("中美晶", 100.0, 6.5),
}

CODES = ["2330", "2317", "5483"]

# ---- 個股期目錄(SC-1 的 fetch 回形;route 會另以 stkfut_map 併上 unit)----
STKFUT_CATALOG: dict[str, dict] = {
    "2330": {
        "name": "台積電",
        "std": {"prod": "CDF", "unit": 2000, "contracts": ["202608", "202609", "202612"]},
        "mini": {"prod": "QFF", "unit": 100, "contracts": ["202608", "202609"]},
    },
}

#: 產品碼 → (標的股號, 顯示前綴)。合成推播的 SecurityName 用它組「台積電期08」。
PROD_INFO: dict[str, tuple[str, str]] = {
    "CDF": ("2330", "台積電期"),
    "QFF": ("2330", "台積電小期"),
}

_SPOT_START = 9 * 60  # 09:00
_SPOT_END = 13 * 60 + 24  # 13:24(13:25 起是試撮窗,ingest 會丟)
_FUT_START = 8 * 60 + 45  # 08:45(個股期日盤開盤)
_FUT_END = 13 * 60 + 45  # 13:45(個股期日盤收盤)


def is_fut(key: str) -> bool:
    return key.startswith("F:")


def window_of(key: str) -> tuple[int, int]:
    return (_FUT_START, _FUT_END) if is_fut(key) else (_SPOT_START, _SPOT_END)


def seed_of(key: str) -> tuple[str, float, float] | None:
    """instrument key → (顯示名, 參考價元, 漂移%);未知 key → None。"""
    if not is_fut(key):
        return SEEDS.get(key)
    prod, _sep, ym = key[2:].partition(":")
    if not ym or prod not in PROD_INFO:
        return None
    under, prefix = PROD_INFO[prod]
    spot = SEEDS.get(under)
    if spot is None:
        return None
    _name, ref, drift = spot
    # 各月合約的參考價逐月墊高一點(近月貼現貨、遠月正價差),看得出「換月換了資料」
    # 幅度刻意拉開:合約簿與現貨簿的價位若數值相同,截圖上「這是合約的五檔」就不可指認
    bump = {"202608": 1.02, "202609": 1.05, "202612": 1.09}.get(ym, 1.0)
    return f"{prefix}{ym[4:]}", round(ref * bump, 1), drift + 0.6


def _now_min() -> int:
    now = _dt.datetime.now()
    return now.hour * 60 + now.minute


def last_min_of(key: str) -> int:
    """合成序列的最後一分鐘:盤中= 現在,盤外= 收在該 instrument 的窗尾。"""
    start, end = window_of(key)
    return max(start + 30, min(_now_min(), end))


def _price_milli(key: str, minute: int) -> int:
    """ref 出發、朝 drift 走的一條有波動的路徑;毫元、貼該價位段的現股 tick。"""
    seed = seed_of(key)
    assert seed is not None
    _name, ref, drift = seed
    start, end = window_of(key)
    span = max(1, end - start)
    prog = (minute - start) / span
    wiggle = 0.004 * math.sin(minute / 7.0) + 0.002 * math.sin(minute / 2.3)
    raw = int(round(ref * (1 + drift / 100 * prog + wiggle) * 1000))
    tick = tick_size_milli(raw)
    return raw // tick * tick


class SeededStockSource(FakeStockSource):
    """FakeStockSource + per-instrument 合成回補 + 背景 REALTIME 推播(meta / 五檔 / 現價)。"""

    def __init__(self) -> None:
        super().__init__()
        self.stkfut_catalog = STKFUT_CATALOG
        self._cum: dict[str, int] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- 回補:窗首 → 現在(盤外收在窗尾),每分鐘一筆 --
    def backfill(self, code: str) -> list[StockTick]:
        if seed_of(code) is None:
            return []
        today = f"{_dt.date.today():%Y-%m-%d}"
        start, _end = window_of(code)
        ticks: list[StockTick] = []
        cum = 0
        for minute in range(start, last_min_of(code) + 1):
            price = _price_milli(code, minute)
            qty = 30 + (minute * 7) % 120
            cum += qty
            tick = tick_size_milli(price)
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
                    bid_milli=price - tick,
                    ask_milli=price,
                )
            )
        # live 推播的 cum 一定要比回補上限大,否則 apply_backfill 會把它當重疊窗丟掉
        self._cum[code] = max(self._cum.get(code, 0), cum)
        return ticks

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        super().set_on_message(cb)
        if self._thread is None:
            self._thread = threading.Thread(target=self._push_loop, daemon=True)
            self._thread.start()

    def _realtime(self, key: str) -> dict:
        seed = seed_of(key)
        assert seed is not None
        name, ref, _drift = seed
        minute = last_min_of(key)
        price = _price_milli(key, minute)
        tick = tick_size_milli(price)
        self._cum[key] = self._cum.get(key, 0) + 11
        # 推播時刻**合成在盤別窗內**(UTC = 台北 − 8h):盤後跑截圖時用本機時鐘的話,
        # 期貨推播會被 engine 的 `_in_futures_session` 整則早退(meta 全拿不到)。
        utc_min = (minute - 8 * 60) % (24 * 60)
        precise = f"{utc_min // 60:02d}{utc_min % 60:02d}45000000"
        today_utc = _dt.datetime.now(_dt.timezone.utc)

        def px(n: int) -> str:
            return f"{(price + n * tick) / 1000:.2f}"

        return {
            "Symbol": (
                f"TC.F.TWF.{key[2:].replace(':', '.')}" if is_fut(key) else f"TC.S.TWS.{key}"
            ),
            "Security": key,
            "SecurityName": name,
            "ReferencePrice": f"{ref:.2f}",
            "UpperLimitPrice": f"{ref * 1.1:.2f}",
            "LowerLimitPrice": f"{ref * 0.9:.2f}",
            "YClosedPrice": f"{ref:.2f}",
            "YTradeVolume": "12345",
            "OpenTime": "084500" if is_fut(key) else "90000",
            "CloseTime": "134500" if is_fut(key) else "133000",
            "TradeStatus": "0",
            "Bid": px(-1),
            "BidVolume": "12",
            "Bid1": px(-2),
            "BidVolume1": "20",
            "Bid2": px(-3),
            "BidVolume2": "31",
            "Bid3": px(-4),
            "BidVolume3": "9",
            "Bid4": px(-5),
            "BidVolume4": "44",
            "Ask": px(0),
            "AskVolume": "8",
            "Ask1": px(1),
            "AskVolume1": "15",
            "Ask2": px(2),
            "AskVolume2": "22",
            "Ask3": px(3),
            "AskVolume3": "6",
            "Ask4": px(4),
            "AskVolume4": "37",
            "TradingPrice": f"{price / 1000:.2f}",
            "TradeQuantity": "11",
            "TradeVolume": str(self._cum[key]),
            # PreciseTime = UTC HHMMSSffffff(12 位;parse 層 +8 轉台北)
            "PreciseTime": precise,
            "TradeDate": f"{today_utc:%Y%m%d}",
        }

    def _push_loop(self) -> None:
        while not self._stop.wait(2.0):
            cb = self.on_message
            if cb is None:
                continue
            for key in list(dict.fromkeys(self.subscribed)):
                if seed_of(key) is None:
                    continue
                try:
                    cb(self._realtime(key))
                except Exception:  # noqa: BLE001 — fake 推播失敗不該弄倒 server
                    pass

    def close(self) -> None:
        self._stop.set()


tmp = Path(tempfile.mkdtemp(prefix="stkfut-shot-"))
wl_path = tmp / "watchlist.json"
wl_path.write_text(
    json.dumps({"codes": CODES, "groups": []}, ensure_ascii=False),
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
