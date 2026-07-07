"""台股市場規則:tick 表與漲停價(全程毫元整數運算,避免二進位殘差)."""

from __future__ import annotations

# (上限毫元, tick 毫元);超過末段 → 5 元
_ZONES: tuple[tuple[int, int], ...] = (
    (10_000, 10),
    (50_000, 50),
    (100_000, 100),
    (500_000, 500),
    (1_000_000, 1_000),
)


def _tick_milli(price_milli: int) -> int:
    for upper, tick in _ZONES:
        if price_milli < upper:
            return tick
    return 5_000


def tick_size(price: float) -> float:
    return _tick_milli(round(price * 1000)) / 1000


def limit_up_price(prev_close: float) -> float:
    """前收 ×1.1 向下貼 tick(tick 段取 candidate 所在價位段)."""
    cand = round(prev_close * 1000) * 11 // 10
    tick = _tick_milli(cand)
    return round(cand // tick * tick / 1000, 2)
