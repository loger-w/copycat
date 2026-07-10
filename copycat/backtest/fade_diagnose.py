"""逼近漲停診斷(SC-7):P(鎖|逼近 d%)與回落深度,量能 × 時段分桶.

回答 guard 設計的核心經驗問題:T+1 逼近漲停的事件裡多少真鎖、多少嘎空回落,
回落後有多少肉。純統計、不涉及任何規則選擇(R5 診斷限定)。
"""

from __future__ import annotations

import logging

from copycat.backtest.fade_config import FadeBacktestConfig
from copycat.backtest.fade_simulate import FadeSample
from copycat.data.models import Bar1K
from copycat.market import limit_up_price

logger = logging.getLogger(__name__)

_EARLY_M = 59  # < 10:00
_HEAVY_VOL_RATIO = 2.0  # 逼近 bar 量 / 前 20bar 均量


def _quantile(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    idx = min(len(s) - 1, int(p * len(s)))
    return s[idx]


def _classify_approach(
    bars: list[Bar1K], limit: float, level: float, eps: float
) -> dict[str, object] | None:
    """回傳逼近事件分類;未逼近 → None."""
    approach_i: int | None = None
    for i, b in enumerate(bars):
        if b.high >= level:
            approach_i = i
            break
    if approach_i is None:
        return None
    ended_locked = bars[-1].low >= limit - eps
    after = bars[approach_i:]
    min_low_after = min(b.low for b in after)
    reversal_depth = max(0.0, (level - min_low_after) / level)

    prior = bars[max(0, approach_i - 20) : approach_i]
    avg_vol = sum(b.volume for b in prior) / len(prior) if prior else 0.0
    vol_ratio = bars[approach_i].volume / avg_vol if avg_vol > 0 else None
    return {
        "ended_locked": ended_locked,
        "reversal_depth": None if ended_locked else reversal_depth,
        "early": bars[approach_i].m < _EARLY_M,
        "heavy": (vol_ratio is not None and vol_ratio >= _HEAVY_VOL_RATIO),
        "vol_known": vol_ratio is not None,
    }


def _bucket_stats(events: list[dict[str, object]]) -> dict[str, float | int | None]:
    n = len(events)
    locked = sum(1 for e in events if e["ended_locked"])
    depths = [e["reversal_depth"] for e in events if e["reversal_depth"] is not None]
    depths_f = [d for d in depths if isinstance(d, float)]
    return {
        "n": n,
        "p_lock": (locked / n) if n else None,
        "p_reverse": ((n - locked) / n) if n else None,
        "reversal_depth_med": _quantile(depths_f, 0.5),
        "reversal_depth_p25": _quantile(depths_f, 0.25),
        "reversal_depth_p75": _quantile(depths_f, 0.75),
    }


def diagnose_limit_approach(
    samples_bars: list[tuple[FadeSample, list[Bar1K]]],
    cfg: FadeBacktestConfig,
) -> dict[str, object]:
    """全 universe 逼近漲停統計,per guard dist × (量能 × 時段) 分桶."""
    out: dict[str, object] = {"n_samples": len(samples_bars)}
    per_dist: dict[str, object] = {}
    for dist in cfg.guard_dist_grid:
        events: list[dict[str, object]] = []
        for sample, bars in samples_bars:
            if not bars:
                continue
            t1_limit = limit_up_price(sample.limit)
            level = t1_limit * (1.0 - dist)
            ev = _classify_approach(bars, t1_limit, level, cfg.limit_eps)
            if ev is not None:
                events.append(ev)
        buckets = {
            "early_heavy": [e for e in events if e["early"] and e["heavy"]],
            "early_light": [e for e in events if e["early"] and not e["heavy"] and e["vol_known"]],
            "late_heavy": [e for e in events if not e["early"] and e["heavy"]],
            "late_light": [
                e for e in events if not e["early"] and not e["heavy"] and e["vol_known"]
            ],
        }
        per_dist[f"{dist}"] = {
            "overall": _bucket_stats(events),
            "buckets": {k: _bucket_stats(v) for k, v in buckets.items()},
        }
    out["per_dist"] = per_dist
    return out
