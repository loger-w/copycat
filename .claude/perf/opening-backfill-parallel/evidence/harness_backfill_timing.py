"""開盤回補 timing harness(確定性、零 TC4):真 StockEngine + 真 StockQuoteSource + FakeApi。

FakeApi 模擬 TC4 歷史通道的實測形狀(08-28 probe):
  - SUBQUOTE TICKS 送出後 `--ready-ms` 才有首頁(probe:批次 20 檔 3.3 s ≈ 0.17 s/檔 → 取 0.2 s)
  - 每則 REQ 在 api.lock 內睡 `--req-ms`(localhost REQ ~ms 級)
  - GETHISDATA 首頁備妥前回 [],備妥後回 1 列 + 空尾頁

量:`set_watchlist(N 檔)` → 觸發入列 → 全部進 `_backfilled` 的牆鐘秒數。
用法(**在 worktree 根目錄執行**,sys.path 釘 cwd 避免 venv .pth 把 import 拉回主 tree):
  .venv/Scripts/python <this file> --codes 40 [--ready-ms 200] [--req-ms 3] [--trigger group|watchlist]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.getcwd())

from copycat.live.stock_source import StockQuoteSource  # noqa: E402
from copycat.server.stock_engine import StockEngine  # noqa: E402

TRADE_DATE = "2026-07-21"
HIST_ROW = {
    "Date": "20260721",
    "FilledTime": "10006",
    "TradeQuantity": "10",
    "TradeVolume": "10",
    "Bid": "2415",
    "Ask": "2420",
    "TradingPrice": "2415",
    "PreciseTime": "10006840000",
    "QryIndex": "1",
}


def _first_tick(code: str) -> dict:
    """一則當日日盤成交 REALTIME(形狀同 tests/server/test_stock_engine.py::_quote;
    PreciseTime 02:57:51 UTC = 台北 10:57:51,非試撮窗)。"""
    return {
        "Symbol": f"TC.S.TWS.{code}",
        "Security": code,
        "SecurityName": "x",
        "TradingPrice": "2380",
        "TradeQuantity": "1",
        "TradeVolume": "1",
        "TradeDate": "20260721",
        "FilledTime": "025751",
        "PreciseTime": "25751000000",
        "Bid": "2375",
        "Ask": "2380",
        "BidVolume": "10",
        "AskVolume": "10",
        "ReferencePrice": "2320",
        "UpperLimitPrice": "2550",
        "LowerLimitPrice": "2090",
        "YClosedPrice": "2320",
        "YTradeVolume": "100",
        "OpenTime": "90000",
        "CloseTime": "133000",
        "TradeStatus": "0",
    }


class JsonSocket:
    def __init__(self, handler) -> None:  # noqa: ANN001
        self._handler = handler
        self._resp = b""

    def send_string(self, payload: str) -> None:
        self._resp = self._handler(json.loads(payload))

    def recv(self) -> bytes:
        return self._resp


class FakeApi:
    def __init__(self, handler) -> None:  # noqa: ANN001
        self.socket = JsonSocket(handler)
        self.lock = threading.Lock()

    def Disconnect(self) -> None:  # noqa: N802
        pass


def _ok(extra: dict | None = None, prefix: str = "") -> bytes:
    return (prefix + json.dumps({"Success": "OK", **(extra or {})}) + "\0").encode()


class Tc4Sim:
    def __init__(self, ready_ms: float, req_ms: float) -> None:
        self.ready_at: dict[str, float] = {}
        self.ready_s = ready_ms / 1000
        self.req_s = req_ms / 1000
        self.reqs = 0
        self.gethis_empty = 0

    def handle(self, obj: dict) -> bytes:
        self.reqs += 1
        if self.req_s:
            time.sleep(self.req_s)
        req = obj.get("Request")
        param = obj.get("Param", {})
        if req == "SUBQUOTE" and param.get("SubDataType") == "TICKS":
            sym = param["Symbol"]
            self.ready_at.setdefault(sym, time.monotonic() + self.ready_s)
            return _ok()
        if req == "GETHISDATA":
            sym = param["Symbol"]
            at = self.ready_at.get(sym)
            if at is None or time.monotonic() < at:
                self.gethis_empty += 1
                return _ok({"HisData": []}, "TICKS:")
            qi = param["QryIndex"]
            rows = [HIST_ROW] if qi == "0" else []
            return _ok({"HisData": rows}, "TICKS:")
        return _ok()


async def run(
    n: int, ready_ms: float, req_ms: float, trigger: str, tick_gap_ms: float = 10.0
) -> dict:
    sim = Tc4Sim(ready_ms, req_ms)
    src = StockQuoteSource(
        api=FakeApi(sim.handle),
        session="s1",
        trade_date=TRADE_DATE,
        heal_silence_secs=None,
        heal_symbol_silence_secs=None,
        in_trading_hours=lambda: False,  # 不排健檢 timer
    )
    engine = StockEngine(src, trade_date=TRADE_DATE, throttle_secs=60, checkpoint=False)
    await engine.start()
    codes = [f"{1000 + i}" for i in range(n)]
    t0 = time.monotonic()
    await engine.set_watchlist(codes)
    t_sub = time.monotonic() - t0
    if trigger == "group":
        engine.group_snapshot(codes)  # 現況:群組檢視 60 s 輪詢的入列點
    elif trigger == "ticks":
        # S2 路徑:模擬 09:00 開盤,每檔首筆成交 tick 相隔 tick_gap_ms 從 source thread 到達
        def _burst() -> None:
            for c in codes:
                engine._on_raw_threadsafe(_first_tick(c))
                time.sleep(tick_gap_ms / 1000)

        threading.Thread(target=_burst, daemon=True).start()
    t1 = time.monotonic()
    deadline = t1 + max(5.0, n * 1.5 + 5)
    while time.monotonic() < deadline:
        if all(c in engine._backfilled for c in codes):
            break
        await asyncio.sleep(0.02)
    done = time.monotonic()
    out = {
        "codes": n,
        "ready_ms": ready_ms,
        "req_ms": req_ms,
        "trigger": trigger,
        "subscribe_wall_s": round(t_sub, 3),
        "backfill_wall_s": round(done - t1, 3),
        "backfilled": sum(c in engine._backfilled for c in codes),
        "reqs": sim.reqs,
        "gethis_empty_polls": sim.gethis_empty,
    }
    await engine.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", type=int, default=40)
    ap.add_argument("--ready-ms", type=float, default=200)
    ap.add_argument("--req-ms", type=float, default=3)
    ap.add_argument("--trigger", choices=["group", "ticks", "watchlist"], default="group")
    ap.add_argument("--tick-gap-ms", type=float, default=10.0, help="ticks 模式:相鄰檔首筆間隔")
    a = ap.parse_args()
    res = asyncio.run(run(a.codes, a.ready_ms, a.req_ms, a.trigger, a.tick_gap_ms))
    print(json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
