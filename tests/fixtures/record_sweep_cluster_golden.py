"""掃單簇 golden fixture 產生腳本(spec #192 seam 2;一次性手跑,產物 `sweep_cluster_golden.json` 進版控)。

**參考碼逐字沿研究腳本**(`C:\\Users\\USER\\Documents\\copycat-trading-review\\scripts\\combo_events.py`
的 `find_sweeps` + 主迴圈 sweepc 段、`sweep_prefix_scan.py` 的 prefix 規則),不是 copycat 的
偵測器 —— 這樣 expected 才有 oracle 意義(線上定義漂掉時只有偵測器那邊紅)。

兩組期望:

- `expected_research`:研究定義(同毫秒群**結束**才判、群末筆 > 首價、層數 = round((群高 − 首價) ÷
  首價檔距)≥ 2、30 s 內 ≥ 2 掃、60 s 漲 ≥ 0.3%、60 s 去重)。事件掛在群末筆。
- `expected_prefix`:即時判(群內自第 2 筆起「當筆 > 首價 且 run_hi 層數 ≥ 2」即登記掃單、之後群內
  每筆重算 hi / qty 直到發訊;冷卻以 tick 時刻算)。事件掛在發訊那一筆。**線上偵測器必須與這組相等。**

已知差異(user 2026-09-07 拍板接受,研究 1,883 股票日量測多發 60 個 = 0.7%、零漏發):
發訊筆可能早於群末(`i` 較小、`price` 較低)、`levels` / `qty` / `up_pct` 為達標當下值(≤ 群結束值)。
測試另斷言 research 事件的時刻集合 ⊆ prefix 事件的時刻集合(零漏發)。

重跑方式(repo root)::

    .venv\\Scripts\\python tests\\fixtures\\record_sweep_cluster_golden.py

前置:研究 tick 檔 `…\\copycat-trading-review\\data\\ticks\\<date>\\<code>.json`(每列
`[毫秒(台北,自午夜), 價, 量, 買一, 賣一]`,毫秒與線上 `StockTick.time` 同源 TC4 PreciseTime)。
"""

from __future__ import annotations

import json
import os
from bisect import bisect_left, bisect_right
from pathlib import Path
from typing import Any

TICKS_ROOT = Path(r"C:/Users/USER/Documents/copycat-trading-review/data/ticks")
OUT = Path(__file__).with_name("sweep_cluster_golden.json")
#: 三個股票日:各含 2–5 個事件,且有「發訊早於群末 / 層數低於群結束值」的差異案例
CASES: tuple[tuple[str, str], ...] = (
    ("6715", "2026-08-17"),
    ("1727", "2026-08-05"),
    ("8103", "2026-08-19"),
)

Row = list[float]


def tick_size(p: float) -> float:
    if p < 10:
        return 0.01
    if p < 50:
        return 0.05
    if p < 100:
        return 0.1
    if p < 500:
        return 0.5
    if p < 1000:
        return 1.0
    return 5.0


def load_rows(path: Path) -> list[Row]:
    """研究 loader 同款:濾 價 / 量 ≤ 0,買一 / 賣一 None → 0。"""
    raw: list[list[float | None]] = json.loads(path.read_text(encoding="utf-8"))
    out: list[Row] = []
    for r in raw:
        ms, p, q, b, a = r
        if p and p > 0 and q and q > 0:
            out.append([float(ms or 0), float(p), float(q), float(b or 0.0), float(a or 0.0)])
    return out


def groups(rows: list[Row]) -> list[tuple[int, int]]:
    """同毫秒相鄰 tick 的 (首索引, 末索引)。"""
    out: list[tuple[int, int]] = []
    n = len(rows)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and rows[j + 1][0] == rows[i][0]:
            j += 1
        out.append((i, j))
        i = j + 1
    return out


def find_sweeps_final(
    rows: list[Row], min_levels: int = 2
) -> list[tuple[float, int, int, float, float, int, float]]:
    """研究 `find_sweeps`:回 [(sec, i_first, i_last, p0, hi, lev, qty)]。"""
    out: list[tuple[float, int, int, float, float, int, float]] = []
    for i, j in groups(rows):
        if j > i:
            p0, ask0 = rows[i][1], rows[i][4]
            hi = max(r[1] for r in rows[i : j + 1])
            if rows[j][1] > p0 and ask0 > 0 and p0 >= ask0 - 1e-9:
                lev = int(round((hi - p0) / tick_size(p0)))
                if lev >= min_levels:
                    qty = sum(r[2] for r in rows[i : j + 1])
                    out.append((rows[i][0] / 1000.0, i, j, p0, hi, lev, qty))
    return out


def clusters_final(
    rows: list[Row],
    sweeps: list[tuple[float, int, int, float, float, int, float]],
    *,
    window: float = 30,
    min_sweeps: int = 2,
    up_pct: float = 0.3,
    up_window: float = 60,
    dedup: float = 60,
) -> list[dict[str, Any]]:
    """研究 sweepc 段:n30 / up60 / 60 s 去重;事件掛在群末筆。"""
    sec = [r[0] / 1000.0 for r in rows]
    sw_secs = [s[0] for s in sweeps]
    out: list[dict[str, Any]] = []
    last = -1e9
    for s, _i0, i1, _p0, p1, lev, qs in sweeps:
        n30 = bisect_right(sw_secs, s) - bisect_left(sw_secs, s - window)
        j60 = bisect_right(sec, s - up_window) - 1
        up60 = (p1 / rows[j60][1] - 1) * 100 if j60 >= 0 else 0.0
        if n30 >= min_sweeps and up60 >= up_pct and s - last >= dedup:
            last = s
            out.append(
                dict(
                    i=i1,
                    ms=int(rows[i1][0]),
                    price=rows[i1][1],
                    n30=n30,
                    levels=lev,
                    qty=qs,
                    up_pct=up60,
                )
            )
    return out


def clusters_prefix(
    rows: list[Row],
    *,
    min_levels: int = 2,
    window: float = 30,
    min_sweeps: int = 2,
    up_pct: float = 0.3,
    up_window: float = 60,
    dedup: float = 60,
) -> list[dict[str, Any]]:
    """即時判(線上偵測器語意):掃單達標當筆即登記 s;之後群內每筆重算(hi / qty 隨前綴長大)
    直到發訊;冷卻 = 發訊後 dedup 秒內不發(以 tick 時刻當時鐘)。事件掛在發訊那一筆。"""
    sec = [r[0] / 1000.0 for r in rows]
    out: list[dict[str, Any]] = []
    sw_secs: list[float] = []  # 已登記的掃單時刻(升冪)
    last = -1e9
    for i, j in groups(rows):
        if j == i:
            continue
        p0, ask0 = rows[i][1], rows[i][4]
        if not (ask0 > 0 and p0 >= ask0 - 1e-9):
            continue
        s = rows[i][0] / 1000.0
        run_hi = p0
        qty = rows[i][2]
        qualified = False
        fired = False
        for k in range(i + 1, j + 1):
            run_hi = max(run_hi, rows[k][1])
            qty += rows[k][2]
            lev = int(round((run_hi - p0) / tick_size(p0)))
            if not qualified:
                if rows[k][1] > p0 and lev >= min_levels:
                    qualified = True
                    sw_secs.append(s)
                else:
                    continue
            if fired:
                continue
            n30 = bisect_right(sw_secs, s) - bisect_left(sw_secs, s - window)
            j60 = bisect_right(sec, s - up_window) - 1
            up60 = (run_hi / rows[j60][1] - 1) * 100 if j60 >= 0 else 0.0
            if n30 >= min_sweeps and up60 >= up_pct and s - last >= dedup:
                last = s
                fired = True
                out.append(
                    dict(
                        i=k,
                        ms=int(rows[k][0]),
                        price=rows[k][1],
                        n30=n30,
                        levels=lev,
                        qty=qty,
                        up_pct=up60,
                    )
                )
    return out


def build() -> None:
    cases: list[dict[str, Any]] = []
    for code, date in CASES:
        rows = load_rows(TICKS_ROOT / date / f"{code}.json")
        cases.append(
            {
                "code": code,
                "date": date,
                "ticks": [[int(r[0]), r[1], r[2], r[3], r[4]] for r in rows],
                "expected_prefix": clusters_prefix(rows),
                "expected_research": clusters_final(rows, find_sweeps_final(rows)),
            }
        )
    payload = {
        "_note": (
            "掃單簇 golden fixture(spec #192 seam 2):ticks 逐列 [毫秒(台北,自午夜), 價, 量, 買一, 賣一]"
            "(研究 data/ticks 原始列,已濾 價/量 ≤ 0、None → 0)。expected_research = 研究定義(combo_events."
            "find_sweeps + sweepc:同毫秒群結束才判、群末筆 > 首價、60 s 去重);expected_prefix = 即時判(群內首次"
            "達標即登記、群內每筆重算直到發訊、冷卻以 tick 時刻算),線上偵測器必須與 expected_prefix 集合相等。"
            "已知差異 = 發訊筆可能早於群末(i 較小)、levels / qty / up_pct 為達標當下值;研究 1,883 股票日量測"
            "多發 60 個(0.7%)、零漏發。產生腳本 = tests/fixtures/record_sweep_cluster_golden.py。"
        ),
        "params": {
            "cluster_window_secs": 30,
            "min_sweeps": 2,
            "min_levels": 2,
            "up_pct": 0.3,
            "up_window_secs": 60,
            "cooldown_secs": 60,
        },
        "cases": cases,
    }
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    print(f"wrote {OUT} ({os.path.getsize(OUT)} bytes)")


if __name__ == "__main__":
    build()
