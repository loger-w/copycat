"""Phase 2 鎖板品質:LockTracker(鎖死定義與 neigui extract_features.py 對齊)."""

from __future__ import annotations

from dataclasses import dataclass

from copycat.data.models import Bar1K, fmt_min
from copycat.strategy_config import StrategyConfig

_LOCK_BUCKET_LABELS = ("<09:05", "09:05-10:00", "10:00-12:00", "12:00-13:00", "13:00+")


@dataclass(frozen=True, slots=True)
class LockQualitySignals:
    first_touch_idx: int
    first_touch_time: str
    lock_idx: int  # final lock 起點 bar 的分鐘索引
    lock_time: str
    lock_time_bucket: str
    n_reopens: int
    violent_pull: bool
    prelock10_gain: float | None
    vol_after_lock_share: float
    queue_bucket: str
    day_volume: float
    tier: str


def _lock_bucket(cfg: StrategyConfig, lock_idx: int) -> str:
    for label, cut in zip(_LOCK_BUCKET_LABELS, cfg.lock_time_buckets):
        if lock_idx < cut:
            return label
    return _LOCK_BUCKET_LABELS[-1]


def _queue_bucket(cfg: StrategyConfig, share: float) -> str:
    if share >= cfg.queue_strong_min:
        return ">=40%"
    if share < cfg.queue_dead_max:
        return "<15%"
    return "15-40%"


def _tier(cfg: StrategyConfig, lock_idx: int, violent: bool, share: float, n_reopens: int) -> str:
    if (
        lock_idx >= cfg.tail_lock_min_idx
        or violent
        or share < cfg.queue_dead_max
        or n_reopens >= cfg.open_count_weak
    ):
        return "weak"
    if (
        lock_idx < cfg.early_lock_max_idx
        and not violent
        and share >= cfg.queue_strong_min
        and n_reopens <= cfg.open_count_strong_max
    ):
        return "strong"
    return "neutral"


class LockTracker:
    """逐 bar 餵入;first_touch / n_reopens 盤中可查且不回改;finalize 收盤定稿."""

    def __init__(self, config: StrategyConfig, limit: float) -> None:
        self._cfg = config
        self._limit = limit
        self._bars: list[Bar1K] = []
        self._first_touch: int | None = None  # bars list 內的位置(非分鐘索引)
        self._n_reopens = 0
        self._in_limit = False
        self._run_start: int | None = None  # 當前連續 at_limit 段起點(list 位置)

    def _at_limit(self, b: Bar1K) -> bool:
        return b.close >= self._limit - self._cfg.limit_eps

    def feed(self, bar: Bar1K) -> None:
        if self._bars and bar.m <= self._bars[-1].m:
            raise ValueError(f"bar 時間未遞增: m={bar.m} (last={self._bars[-1].m})")
        self._bars.append(bar)
        i = len(self._bars) - 1
        touched = bar.high >= self._limit - self._cfg.limit_eps
        if self._first_touch is None and touched:
            self._first_touch = i
        if self._at_limit(bar):
            if not self._in_limit:
                self._in_limit = True
                self._run_start = i
        elif self._in_limit:
            self._in_limit = False
            self._run_start = None
            if self._first_touch is not None:
                self._n_reopens += 1

    @property
    def first_touch_idx(self) -> int | None:
        return self._bars[self._first_touch].m if self._first_touch is not None else None

    @property
    def n_reopens(self) -> int:
        return self._n_reopens

    def current_lock_start(self) -> int | None:
        return self._bars[self._run_start].m if self._run_start is not None else None

    def finalize(self) -> LockQualitySignals | None:
        cfg = self._cfg
        if self._first_touch is None or not self._in_limit or self._run_start is None:
            return None  # 全日未觸停,或收盤不在漲停(與研究定義一致)
        day_vol = sum(b.volume for b in self._bars)
        if day_vol <= 0:
            return None
        lock_pos = self._run_start
        lock_m = self._bars[lock_pos].m
        after_share = sum(b.volume for b in self._bars[lock_pos:]) / day_vol
        window = [b for b in self._bars[:lock_pos] if b.m >= lock_m - cfg.violent_pull_window]
        gain = self._limit / window[0].open - 1 if window and window[0].open > 0 else None
        violent = gain is not None and gain >= cfg.violent_pull_min_gain
        return LockQualitySignals(
            first_touch_idx=self._bars[self._first_touch].m,
            first_touch_time=fmt_min(self._bars[self._first_touch].m),
            lock_idx=lock_m,
            lock_time=fmt_min(lock_m),
            lock_time_bucket=_lock_bucket(cfg, lock_m),
            n_reopens=self._n_reopens,
            violent_pull=violent,
            prelock10_gain=gain,
            vol_after_lock_share=after_share,
            queue_bucket=_queue_bucket(cfg, after_share),
            day_volume=day_vol,
            tier=_tier(cfg, lock_m, violent, after_share, self._n_reopens),
        )
