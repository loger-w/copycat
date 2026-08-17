"""SC-6 回放:1 分 K 重建 tick 餵真 SignalDetector,比 CDP 事件數(舊 cfg vs 新 cfg)。

用法(repo root):`.venv/Scripts/python .claude/mod/signal-denoise/replay_cdp.py`
資料:evidence/bars-20260817.json(GET /api/stock/bars/{code}?tf=1&days=1 + overlay 快照)。
tick 路徑近似:o → 較近的極值 → 另一極值 → c,每 15 秒一筆;是近似值,只比相對減量。
"""

from __future__ import annotations

import datetime as _dt
import json
import sys
from collections import Counter
from dataclasses import fields, replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from copycat.live.signal_state import SignalDetector, TickContext  # noqa: E402
from copycat.live.stock_models import StockTick  # noqa: E402
from copycat.signals_config import SignalsConfig  # noqa: E402

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / "evidence" / "bars-20260817.json").read_text(encoding="utf-8"))
TRADE_DATE = DATA["trade_date"]
CDP_ONLY = frozenset({"cdp_cross"})
UNCHANGED = ("2408", "3006", "3037", "8064")


def _path(bars: list[list]) -> list[tuple[_dt.datetime, int]]:
    out: list[tuple[_dt.datetime, int]] = []
    y, m, d = (int(x) for x in TRADE_DATE.split("-"))
    for t, o, h, l, c in bars:
        hh, mm = int(t[:2]), int(t[3:5])
        base = _dt.datetime(y, m, d, hh, mm) - _dt.timedelta(minutes=1)
        seq = [o] + ([h, l] if abs(h - o) <= abs(l - o) else [l, h]) + [c]
        for i, p in enumerate(seq):
            out.append((base + _dt.timedelta(seconds=15 * i), p))
    return out


def _cfg(**over: float) -> SignalsConfig:
    known = {f.name for f in fields(SignalsConfig)}
    return replace(SignalsConfig(), **{k: v for k, v in over.items() if k in known})


def run(cfg: SignalsConfig, code: str, entry: dict) -> int:
    clock = {"now": _dt.datetime(2000, 1, 1)}
    det = SignalDetector(cfg, now_fn=lambda: clock["now"])
    det.set_basis(code, entry["cdp"])
    ctx = TickContext(
        trade_date=TRADE_DATE, upper_milli=None, lower_milli=None,
        ask_limit_available=True, bid_limit_available=True, bids0_is_market=False,
        asks0_is_market=False, best_bid_limit_milli=None, best_ask_limit_milli=None,
        day_volume=0,
    )
    n = 0
    for when, price in _path(entry["bars"]):
        clock["now"] = when
        tick = StockTick(code=code, price_milli=price, qty=1, cum_vol=1,
                         time=f"{when:%H:%M:%S}.000", trade_date=TRADE_DATE,
                         side="neutral", is_trial=False)
        n += len(det.evaluate(code, tick, ctx, CDP_ONLY))
    return n


def main() -> int:
    variants = {
        "baseline(dwell 0)": _cfg(cdp_rearm_dwell_secs=0.0),
        "new(dwell 300)": _cfg(cdp_rearm_dwell_secs=300.0),
    }
    totals: Counter[str] = Counter()
    per: dict[str, dict[str, int]] = {k: {} for k in variants}
    for code, entry in sorted(DATA["codes"].items()):
        if not entry.get("cdp") or not entry.get("bars"):
            continue
        for name, cfg in variants.items():
            n = run(cfg, code, entry)
            totals[name] += n
            per[name][code] = n
    jsonl = HERE.parents[2] / "data" / "signals" / f"{TRADE_DATE.replace('-', '')}.jsonl"
    actual = None
    if jsonl.exists():  # 旁證:真 tick 下 hub 實際落檔的 CDP 則數(近似路徑 vs 真 tick 的落差)
        actual = sum(
            1 for line in jsonl.read_text(encoding="utf-8").splitlines()
            if line.strip() and json.loads(line).get("kind") == "cdp_cross"
        )
    print(f"actual jsonl cdp_cross ({jsonl.name}): {actual}")
    base, new = totals["baseline(dwell 0)"], totals["new(dwell 300)"]
    cut = (base - new) / base * 100 if base else 0.0
    print(f"CDP events  baseline={base}  new={new}  reduction={cut:.1f}%")
    print("code  base  new")
    for code in sorted(per["baseline(dwell 0)"], key=lambda c: -per["baseline(dwell 0)"][c]):
        print(f"{code}  {per['baseline(dwell 0)'][code]:4d}  {per['new(dwell 300)'][code]:4d}")
    ok_cut = cut >= 25
    ok_same = all(per["baseline(dwell 0)"].get(c) == per["new(dwell 300)"].get(c) for c in UNCHANGED)
    print(f"SC-6 reduction>=25%: {'PASS' if ok_cut else 'FAIL'};"
          f" unchanged {UNCHANGED}: {'PASS' if ok_same else 'FAIL'}")
    return 0 if ok_cut and ok_same else 1


if __name__ == "__main__":
    raise SystemExit(main())
