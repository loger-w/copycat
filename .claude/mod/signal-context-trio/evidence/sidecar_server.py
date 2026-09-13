"""#224 三件顯示層小改的取證側車(零 TC4 / 零 ZMQ — ops-discipline;含 neutralize_external_env)。

改自 `.claude/mod/group-grid-full-chart/evidence/fake_server.py`,差別:
  1. `sys.path` 錨在 **worktree**(ops-discipline 三險:worktree 直跑腳本會 import 主 tree 的 code)。
  2. 三檔劇本(推播執行緒在訂閱齊之後自動跑一次,之後只保持 idle):
     - 2330:日 K 前 5 日 +11% → CDP 列閘**過** → 09:21 穿越 NH 發 cdp_cross;09:31 暖機 30 筆 + 一筆大單
       (10 張,外盤、價升)→ 09:33 兩個同毫秒群 → 掃單簇 `detail.big_lots_120s = 1`;2330 在「盤前篩選」
       群 → S 政策列頂層 `big_lots_120s = 1`。
     - 2317:日 K 五根同收盤(+0%)→ 列閘**不過** → 同樣的 NH 穿越**零** cdp_cross,log INFO「CDP 列閘」。
     - 2454:09:30–09:39 每分鐘 10 張同價迴盪 → 09:40 離帶(+1%)40 張 = 4× 均量 → `vol_breakout` up。
  3. 偵測器 09:00–13:30 牆鐘閘放寬成全天(夜間取證;tick 時刻仍是劇本寫死的 09:2x–09:4x)。
  4. `logging.basicConfig(INFO)`:列閘那一行是 INFO,uvicorn 的 warning 等級看不到。
  5. port 由 argv[1] 指定(預設 8730;prod 8721 跑著不碰)。

跑法(worktree root)::

    C:/side-project/copycat/.venv/Scripts/python .claude/mod/signal-context-trio/evidence/sidecar_server.py 8730
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # <worktree>/.claude/mod/<slug>/evidence → <worktree>
sys.path.insert(0, str(ROOT))

import datetime as _dt
import json
import logging
import tempfile
import threading
import time
from collections.abc import Callable

import uvicorn

# ⚠ 必須在 create_app 之前(ops-discipline:漏了會拿 .env 真憑證登入群益正式環境)
from copycat.server.verify import neutralize_external_env

neutralize_external_env()

import copycat.live.signal_state as _signal_state
from copycat.live.models import SeriesInfo, Tick
from copycat.server.app import create_app
from tests.helpers.fake_sources import (
    FakeCorrSource,
    FakeFuturesSource,
    FakeIndexSource,
    FakeStockSource,
)

assert create_app.__module__.startswith("copycat"), "import 錨點檢查"
assert Path(create_app.__code__.co_filename).resolve().is_relative_to(ROOT), (
    "import 到主 tree 的 code 了(worktree 三險)"
)

# 夜間取證:偵測器牆鐘閘放寬成全天(tick 時刻仍照劇本 09:2x–09:4x)
_signal_state._SESSION_START = _dt.time(0, 0)
_signal_state._SESSION_END = _dt.time(23, 59, 59)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

SERIES = SeriesInfo(series_id="TX4.202608", name="TX4 202608", expiry="202608", contracts=())


class FakeQuoteSource:
    def list_series(self) -> list[SeriesInfo]:
        return [SERIES]

    def fetch_backfill(self, series: SeriesInfo) -> list[Tick]:
        return []

    def subscribe(self, series: SeriesInfo, on_tick: Callable[[Tick], None]) -> None: ...

    def unsubscribe(self, series: SeriesInfo) -> None: ...

    def close(self) -> None: ...


TODAY = _dt.date.today()
TRADE_DATE = f"{TODAY:%Y%m%d}"
NAMES = {"2330": ("台積電", 50_000), "2317": ("鴻海", 50_000), "2454": ("聯發科", 100_000)}
CODES = list(NAMES)
GROUPS = [
    {"name": "盤前篩選", "codes": ["2330"]},
    {"name": "測試群", "codes": ["2317", "2454"]},
]


def _tp(hhmmss_fff: str) -> tuple[str, str]:
    """台北 `HH:MM:SS.fff` → (PreciseTime UTC 12 碼, TradeDate UTC)。parse 層 +8 還原。"""
    local = _dt.datetime.combine(TODAY, _dt.time.fromisoformat(hhmmss_fff))
    utc = local - _dt.timedelta(hours=8)
    return f"{utc:%H%M%S}{utc.microsecond // 1000:03d}000", f"{utc:%Y%m%d}"


def _daily(code: str) -> list[dict]:
    """25 根已完成日 K(日期恆早於今天)。2330 / 2454 前 5 日上漲過閘;2317 五根同收盤不過。"""
    bars: list[dict] = []
    for i in range(25, 0, -1):
        d = TODAY - _dt.timedelta(days=i)
        if code == "2330":
            close = 45_000 + max(0, 6 - i) * 1_000  # 倒數第六根 45.00 → 最後一根 50.00(+11.1%)
        elif code == "2454":
            close = 95_000 + max(0, 6 - i) * 1_000  # 95.00 → 100.00(+5.26%)
        else:
            close = 50_000  # 2317:整段 50.00(+0%)
        bars.append({"date": f"{d:%Y-%m-%d}", "high": close + 500, "low": close - 500, "close": close})
    return bars


class ScriptedStockSource(FakeStockSource):
    def __init__(self) -> None:
        super().__init__()
        self._cum: dict[str, int] = {c: 0 for c in CODES}
        self._thread: threading.Thread | None = None
        self.done = threading.Event()

    def fetch_daily_bars(self, code: str, n: int = 25) -> list:
        return _daily(code)[-n:] if code in NAMES else []

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        super().set_on_message(cb)
        if self._thread is None:
            self._thread = threading.Thread(target=self._script, daemon=True)
            self._thread.start()

    def _quote(self, code: str, time_tp: str, price: int, qty: int, ask: int | None) -> dict:
        name, ref = NAMES[code]
        self._cum[code] += qty
        precise, date = _tp(time_tp)
        tick = 100 if price < 100_000 else 500
        return {
            "Symbol": f"TC.S.TWS.{code}",
            "Security": code,
            "SecurityName": name,
            "ReferencePrice": f"{ref / 1000:.2f}",
            "UpperLimitPrice": f"{ref * 1.1 / 1000:.2f}",
            "LowerLimitPrice": f"{ref * 0.9 / 1000:.2f}",
            "YClosedPrice": f"{ref / 1000:.2f}",
            "YTradeVolume": "12345",
            "OpenTime": "90000",
            "CloseTime": "133000",
            "TradeStatus": "0",
            "Bid": f"{(price - tick) / 1000:.2f}",
            "BidVolume": "12",
            "Ask": f"{(ask if ask is not None else price + tick) / 1000:.2f}",
            "AskVolume": "8",
            "TradingPrice": f"{price / 1000:.2f}",
            "TradeQuantity": str(qty),
            "TradeVolume": str(self._cum[code]),
            "PreciseTime": precise,
            "TradeDate": date,
        }

    def _push(self, code: str, time_tp: str, price: int, qty: int = 1, ask: int | None = None) -> None:
        cb = self.on_message
        assert cb is not None
        cb(self._quote(code, time_tp, price, qty, ask))
        time.sleep(0.02)

    def _script(self) -> None:
        while not all(c in self.subscribed for c in CODES):
            time.sleep(0.2)
        time.sleep(2.0)  # boot 收尾 + 首輪基準
        log = logging.getLogger("sidecar")
        log.info("劇本開始:phase0 換日暖機")
        for code, p in (("2330", 50_300), ("2317", 50_300), ("2454", 100_000)):
            self._push(code, "09:20:00.000", p, 1, ask=p + 100)
        time.sleep(4.0)  # 換日 → 基準重抓(3 檔 × 0.2 s gap)
        log.info("phase1:CDP NH 穿越(2330 過閘 / 2317 不過閘)")
        self._push("2330", "09:21:00.000", 50_600, 1, ask=50_600)
        self._push("2317", "09:21:00.000", 50_600, 1, ask=50_600)
        log.info("phase2:2454 迴盪十分鐘後放量離帶")
        for i in range(10):
            self._push("2454", f"09:{30 + i:02d}:00.000", 100_000, 10, ask=100_000)
        self._push("2454", "09:40:00.000", 101_000, 40, ask=101_000)
        log.info("phase3:2330 暖機 30 筆 + 大單 + 掃單簇")
        for i in range(30):
            ms = i * 100
            self._push("2330", f"09:31:{ms // 1000:02d}.{ms % 1000:03d}", 50_600, 1, ask=50_600)
        self._push("2330", "09:31:40.000", 50_700, 10, ask=50_700)
        self._push("2330", "09:32:00.000", 50_700, 1, ask=50_700)
        for p in (50_700, 50_800, 50_900):
            self._push("2330", "09:33:10.100", p, 1, ask=50_700)
        for p in (50_900, 51_000, 51_100):
            self._push("2330", "09:33:30.500", p, 2, ask=50_900)
        log.info("劇本結束")
        self.done.set()


tmp = Path(tempfile.mkdtemp(prefix="signal-trio-evidence-"))
wl_path = tmp / "watchlist.json"
wl_path.write_text(
    json.dumps({"version": 2, "codes": CODES, "groups": GROUPS}, ensure_ascii=False),
    encoding="utf-8",
)
print(f"data dir: {tmp}", flush=True)

source = ScriptedStockSource()
app = create_app(
    FakeQuoteSource(),
    stock_source=source,
    index_source=FakeIndexSource(),
    futures_source=FakeFuturesSource(),
    corr_source=FakeCorrSource(),
    stock_watchlist_path=wl_path,
)

port = int(sys.argv[1]) if len(sys.argv) > 1 else 8730
uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
