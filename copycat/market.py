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


def tick_size_milli(price_milli: int) -> int:
    """毫元版 tick:`tick_size_milli(23_450) == 50`(23.45 元 → 0.05 元檔)、
    `tick_size_milli(123_450) == 500`(123.45 元落 100–500 元段 → 0.5 元檔)。

    訊號層的 rearm 門檻全走毫元整數比較,不繞道 float `tick_size`。
    """
    return _tick_milli(price_milli)


def tick_size(price: float) -> float:
    return _tick_milli(round(price * 1000)) / 1000


def limit_up_milli(prev_close_milli: int) -> int:
    """毫元版漲停:前收 ×1.1 向下貼 tick(tick 段取 candidate 所在價位段)."""
    cand = prev_close_milli * 11 // 10
    tick = _tick_milli(cand)
    return cand // tick * tick


def limit_down_milli(prev_close_milli: int) -> int:
    """毫元版跌停:前收 ×0.9 向上貼 tick。

    tick 段取 **ceil 前** 的 candidate 所在價位段(與 neigui float 版
    `_tick_size(raw)` 同語意)—— candidate 落在段上界附近時,ceil 後可能跨進
    下一段,取段一律以 ceil 前的值為準。
    """
    cand = prev_close_milli * 9 // 10
    tick = _tick_milli(cand)
    return -(-cand // tick) * tick


def limit_up_price(prev_close: float) -> float:
    """前收 ×1.1 向下貼 tick(tick 段取 candidate 所在價位段)."""
    return round(limit_up_milli(round(prev_close * 1000)) / 1000, 2)
