"""7 臂竭盡點觸發定義(design.md v2 §3)— T+1 盤中進場訊號.

每臂回傳觸發 bar index(第一根滿足條件的 bar),None = 時間窗內未觸發。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from copycat.data.models import Bar1K


def find_trigger_pullback(bars: list[Bar1K], x_pct: float, max_m: int) -> int | None:
    rolling_high = 0.0
    for i, b in enumerate(bars):
        if b.m > max_m:
            return None
        rolling_high = max(rolling_high, b.high)
        if rolling_high > 0 and (1.0 - b.close / rolling_high) >= x_pct:
            return i
    return None


def find_trigger_inner_flip(
    bars: list[Bar1K],
    n_window: int,
    y_threshold: float,
    max_m: int,
) -> int | None:
    for i, b in enumerate(bars):
        if b.m > max_m:
            return None
        if i < n_window - 1:
            continue
        window = bars[i - n_window + 1 : i + 1]
        up = sum(w.up_volume for w in window)
        dn = sum(w.down_volume for w in window)
        total = up + dn
        if total > 0 and dn / total > y_threshold:
            return i
    return None


def find_trigger_pin_bar(
    bars: list[Bar1K],
    w_threshold: float,
    near_pct: float,
    max_m: int,
) -> int | None:
    rolling_high = 0.0
    for i, b in enumerate(bars):
        if b.m > max_m:
            return None
        rolling_high = max(rolling_high, b.high)
        if b.high <= b.low:
            continue
        near_high = b.high >= rolling_high * (1.0 - near_pct)
        upper_wick = (b.high - max(b.open, b.close)) / (b.high - b.low)
        if near_high and upper_wick >= w_threshold:
            return i
    return None


def find_trigger_vol_exhaust(
    bars: list[Bar1K],
    z_ratio: float,
    near_pct: float,
    max_m: int,
) -> int | None:
    rolling_high = 0.0
    cum_vol = 0.0
    for i, b in enumerate(bars):
        if b.m > max_m:
            return None
        rolling_high = max(rolling_high, b.high)
        if i == 0:
            cum_vol += b.volume
            continue
        avg_vol = cum_vol / i
        cum_vol += b.volume
        if avg_vol <= 0:
            continue
        near_high = b.high >= rolling_high * (1.0 - near_pct)
        if near_high and b.volume / avg_vol < z_ratio:
            return i
    return None


def find_trigger_delta_flip(bars: list[Bar1K], max_m: int) -> int | None:
    cum_delta = 0.0
    for i, b in enumerate(bars):
        if b.m > max_m:
            return None
        prev_delta = cum_delta
        cum_delta += b.up_volume - b.down_volume
        if i > 0 and prev_delta > 0 and cum_delta <= 0:
            return i
    return None


def find_trigger_vwap_break(bars: list[Bar1K], max_m: int) -> int | None:
    cum_pv = 0.0
    cum_v = 0.0
    prev_above = True
    for i, b in enumerate(bars):
        if b.m > max_m:
            return None
        cum_pv += b.close * b.volume
        cum_v += b.volume
        if cum_v <= 0:
            continue
        vwap = cum_pv / cum_v
        above = b.close >= vwap
        if i > 0 and prev_above and not above:
            return i
        prev_above = above
    return None


def find_trigger_fixed_time(bars: list[Bar1K], target_m: int) -> int | None:
    for i, b in enumerate(bars):
        if b.m == target_m:
            return i
        if b.m > target_m:
            return None
    return None


@dataclass(frozen=True)
class ArmParamSet:
    name: str
    values: dict[str, float | int]

    @property
    def param_id(self) -> str:
        parts = [f"{k}={v}" for k, v in sorted(self.values.items())]
        return "|".join(parts)


@dataclass(frozen=True)
class ArmSpec:
    name: str
    find_fn: Callable[..., int | None]
    param_grid: list[ArmParamSet]
    anchor_params: list[ArmParamSet]


def _build_pullback_arm() -> ArmSpec:
    grid_x = [
        0.001,
        0.002,
        0.003,
        0.004,
        0.005,
        0.006,
        0.007,
        0.008,
        0.009,
        0.010,
        0.012,
        0.015,
        0.020,
        0.025,
        0.030,
    ]
    grid = [ArmParamSet("pullback", {"x_pct": x}) for x in grid_x]
    anchors = [ArmParamSet("pullback", {"x_pct": x}) for x in [0.003, 0.008, 0.015]]
    return ArmSpec("pullback", find_trigger_pullback, grid, anchors)


def _build_inner_flip_arm() -> ArmSpec:
    ns = [2, 3, 4, 5, 6, 8, 10]
    ys = [0.45, 0.48, 0.50, 0.52, 0.55, 0.58, 0.60, 0.65, 0.70]
    grid = [ArmParamSet("inner_flip", {"n_window": n, "y_threshold": y}) for n in ns for y in ys]
    anchors = [
        ArmParamSet("inner_flip", {"n_window": 3, "y_threshold": 0.50}),
        ArmParamSet("inner_flip", {"n_window": 5, "y_threshold": 0.55}),
        ArmParamSet("inner_flip", {"n_window": 8, "y_threshold": 0.60}),
    ]
    return ArmSpec("inner_flip", find_trigger_inner_flip, grid, anchors)


def _build_pin_bar_arm() -> ArmSpec:
    ws = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]
    nears = [0.003, 0.005, 0.010]
    grid = [ArmParamSet("pin_bar", {"w_threshold": w, "near_pct": n}) for w in ws for n in nears]
    anchors = [
        ArmParamSet("pin_bar", {"w_threshold": 0.40, "near_pct": 0.005}),
        ArmParamSet("pin_bar", {"w_threshold": 0.60, "near_pct": 0.005}),
        ArmParamSet("pin_bar", {"w_threshold": 0.70, "near_pct": 0.003}),
    ]
    return ArmSpec("pin_bar", find_trigger_pin_bar, grid, anchors)


def _build_vol_exhaust_arm() -> ArmSpec:
    zs = [0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]
    nears = [0.003, 0.005, 0.010]
    grid = [ArmParamSet("vol_exhaust", {"z_ratio": z, "near_pct": n}) for z in zs for n in nears]
    anchors = [
        ArmParamSet("vol_exhaust", {"z_ratio": 0.30, "near_pct": 0.005}),
        ArmParamSet("vol_exhaust", {"z_ratio": 0.50, "near_pct": 0.005}),
        ArmParamSet("vol_exhaust", {"z_ratio": 0.70, "near_pct": 0.005}),
    ]
    return ArmSpec("vol_exhaust", find_trigger_vol_exhaust, grid, anchors)


def _build_delta_flip_arm() -> ArmSpec:
    ps = ArmParamSet("delta_flip", {})
    return ArmSpec("delta_flip", find_trigger_delta_flip, [ps], [ps])


def _build_vwap_break_arm() -> ArmSpec:
    ps = ArmParamSet("vwap_break", {})
    return ArmSpec("vwap_break", find_trigger_vwap_break, [ps], [ps])


def _build_fixed_time_arm() -> ArmSpec:
    ms = list(range(1, 30))
    grid = [ArmParamSet("fixed_time", {"target_m": m}) for m in ms]
    anchors = [
        ArmParamSet("fixed_time", {"target_m": 4}),
        ArmParamSet("fixed_time", {"target_m": 7}),
        ArmParamSet("fixed_time", {"target_m": 14}),
    ]
    return ArmSpec("fixed_time", find_trigger_fixed_time, grid, anchors)


ALL_ARMS: list[ArmSpec] = [
    _build_pullback_arm(),
    _build_inner_flip_arm(),
    _build_pin_bar_arm(),
    _build_vol_exhaust_arm(),
    _build_delta_flip_arm(),
    _build_vwap_break_arm(),
    _build_fixed_time_arm(),
]


def dispatch_trigger(
    arm: ArmSpec, bars: list[Bar1K], params: ArmParamSet, max_m: int
) -> int | None:
    kwargs = dict(params.values)
    if arm.name == "fixed_time":
        return arm.find_fn(bars, kwargs["target_m"])
    kwargs["max_m"] = max_m
    return arm.find_fn(bars, **kwargs)
