"""分位數 helpers — 兩種演算法並存,**不可互換**(user 2026-07-20 拍板保留).

- round 版:idx = round(q*(n-1))(banker's rounding)— fade_anatomy / fade_cells 系。
- truncate 版:idx = int(p*n) — fade_diagnose 系。
分歧點例:n=6, p=0.5 → round 取排序後 idx 2、truncate 取 idx 3。
統一演算法會改報告數字 = 行為改動,須另開行為輪,不得在 refactor 內做。
(第四份 backtest/search._quantile 為 nearest-rank、吃已排序輸入,契約不同,不在此收斂。)
"""

from __future__ import annotations


def quantile_round(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[idx]


def quantiles_round(values: list[float]) -> dict[str, object]:
    if not values:
        return {"p25": None, "p50": None, "p75": None, "p90": None, "n": 0}
    return {
        "p25": quantile_round(values, 0.25),
        "p50": quantile_round(values, 0.50),
        "p75": quantile_round(values, 0.75),
        "p90": quantile_round(values, 0.90),
        "n": len(values),
    }


def quantile_trunc(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    idx = min(len(s) - 1, int(p * len(s)))
    return s[idx]
