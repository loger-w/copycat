"""SC-2 characterization gate:θ=8.0 重算特徵 vs neigui trigger_features.csv.

交集抽 50(seed 固定)× 18 欄對照(dtr_t1 除外 — Phase A 無當沖資料源,known difference)。
需本機真資料(data/ 匯入完成 + neigui 種子 CSV);缺 → skip。
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

import pytest

from copycat.backtest.config import BacktestConfig
from copycat.backtest.features import avg20_t1, find_trigger, static_features, trigger_features
from copycat.data.daily import DailyIndex
from copycat.data.store import read_bars

_DATA = Path("data")
_NEIGUI_CSV = Path("C:/side-project/neigui/backend/data/research/five-tigers/trigger_features.csv")
_FLOAT_COLS = [
    "trig_min",
    "gap_open",
    "auction_lots",
    "auction_vol_ratio",
    "climb_rate",
    "burst3",
    "up_min_frac",
    "max_pullback",
    "cumvol_ratio",
    "max_minvol_x",
    "wash_bars",
    "outer_ratio",
    "touches_back",
    "amt_t1_m",
    "ret5",
    "ret20",
    "prev_close",
]


def _rel_close(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


@pytest.mark.skipif(
    not (_DATA / "events" / "near_miss.csv").exists() or not _NEIGUI_CSV.exists(),
    reason="需本機種子資料(data/ 匯入 + neigui trigger_features.csv)",
)
def test_characterization_50_samples_vs_neigui() -> None:
    cfg = BacktestConfig.default()
    daily = DailyIndex.load(_DATA)
    with _NEIGUI_CSV.open("r", encoding="utf-8-sig") as fh:
        golden = {(r["stock_id"], r["date"]): r for r in csv.DictReader(fh)}

    # 交集 = golden 中我方也有 1K 與足夠日線者;deterministic 抽 50
    keys = sorted(golden)
    picked = random.Random(42).sample(keys, 200)  # 多抽,前 50 個可比樣本為準
    compared = 0
    mismatches: list[str] = []
    for sid, date in picked:
        if compared >= 50:
            break
        bars = read_bars(_DATA, sid, date)
        prev_close = daily.ref_prev_close(sid, date)
        avg20 = avg20_t1(daily, sid, date)
        stat = static_features(daily, sid, date)
        if not bars or prev_close is None or avg20 is None or stat is None:
            continue
        trig = find_trigger(bars, prev_close, 0.08, cfg.float_eps)
        if trig is None:
            continue
        ours = trigger_features(
            bars,
            trig,
            prev_close,
            0.08,
            avg20,
            stat,
            tb_upper=cfg.touchback_upper,
            tb_lower=cfg.touchback_lower,
        )
        g = golden[(sid, date)]
        compared += 1
        for col in _FLOAT_COLS:
            gv_raw = g[col]
            ov = ours[col]
            if gv_raw == "" and ov is None:
                continue
            if gv_raw == "" or ov is None:
                mismatches.append(f"{sid} {date} {col}: golden={gv_raw!r} ours={ov!r}")
                continue
            if not _rel_close(float(gv_raw), ov):
                mismatches.append(f"{sid} {date} {col}: golden={gv_raw} ours={ov}")
        # prev_limitup 單向比對(2026-07-10 scan-events 之後):limitup_all 已補全
        # neigui 漏收的真實收盤漲停(1569/2025-08-01、2478/2026-06-16、2340/2026-04-20
        # 皆實證 close == limit_up_price(ref_prev_close),golden=False 是漏收)。
        # 公式錨點仍保留:golden=True 而我們 False = 真偏差。
        g_pl = g["prev_limitup"] == "True"
        if g_pl and ours["prev_limitup"] != 1.0:
            mismatches.append(
                f"{sid} {date} prev_limitup: golden={g_pl} ours={ours['prev_limitup']}"
            )

    assert compared == 50, f"可比樣本不足 50(僅 {compared})"
    assert not mismatches, "characterization 偏差:\n" + "\n".join(mismatches[:20])
