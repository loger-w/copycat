"""Phase 3 T+1 開盤訊號:T1Tracker(路徑分類與研究 t1_day_features 對齊).

無 lookahead 修正:auction_tell 分母用 adv20(09:00:06 可知),
研究版 ÷全日量 只在 finalize 出現、僅供 golden 對照(spec §4c)。
"""
from __future__ import annotations

from dataclasses import dataclass

from copycat.data.models import Bar1K, fmt_min
from copycat.engine.lock_quality import LockQualitySignals
from copycat.strategy_config import StrategyConfig

_GAP_LABELS = ("<0%", "0-1%", "1-3%", "3-7%", "7-9.5%", "漲停開")


@dataclass(frozen=True, slots=True)
class EventContext:
    stock_id: str
    date: str          # T 日
    t1_date: str
    limit: float       # T 日漲停收盤價
    adv20_lots: float | None   # 截至 T 日的 20 日均量(張)
    one_price: bool | None     # T 日一價到底(日線 high==low)
    board_streak: int          # T 日連板數
    lock: LockQualitySignals | None


@dataclass(frozen=True, slots=True)
class T1OpenSignals:
    open_px: float
    gap: float
    gap_bucket: str
    auction_lots: float
    auction_share_adv20: float | None
    auction_tell: str
    auction_share_dayvol: float   # 研究版(收盤定稿,golden 對照用)
    inner15: float | None
    high_idx: int
    high_time: str
    high_vs_open: float
    close_vs_open: float
    touched_limit: bool
    path: str


def _gap_bucket(cfg: StrategyConfig, gap: float) -> str:
    for label, cut in zip(_GAP_LABELS, cfg.gap_buckets):
        if gap < cut:
            return label
    return _GAP_LABELS[-1]


def _auction_tell(cfg: StrategyConfig, share: float | None) -> str:
    if share is None:
        return "n/a"
    lo, hi = cfg.auction_buckets
    if share < lo:
        return "<3%"
    if share < hi:
        return "3-8%"
    return ">=8%"


class T1Tracker:
    def __init__(self, config: StrategyConfig, ctx: EventContext) -> None:
        self._cfg = config
        self._ctx = ctx
        self._t1_limit = ctx.limit * config.t1_limit_mult
        self._bars: list[Bar1K] = []
        self._high = float("-inf")
        self._high_pos = -1

    def feed(self, bar: Bar1K) -> None:
        if self._bars and bar.m <= self._bars[-1].m:
            raise ValueError(f"bar 時間未遞增: m={bar.m} (last={self._bars[-1].m})")
        self._bars.append(bar)
        if bar.high > self._high:
            self._high = bar.high
            self._high_pos = len(self._bars) - 1

    @property
    def gap(self) -> float | None:
        if not self._bars:
            return None
        return self._bars[0].open / self._ctx.limit - 1

    @property
    def auction_tell(self) -> str | None:
        if not self._bars:
            return None
        return _auction_tell(self._cfg, self._auction_share_adv20())

    def _auction_share_adv20(self) -> float | None:
        adv = self._ctx.adv20_lots
        if adv is None or adv <= 0 or not self._bars:
            return None
        return self._bars[0].volume / adv

    def finalize(self, again: bool) -> T1OpenSignals | None:
        cfg = self._cfg
        bars = self._bars
        if not bars:
            return None
        day_vol = sum(b.volume for b in bars)
        if day_vol <= 0:
            return None
        open_px = bars[0].open
        if open_px <= 0:
            return None
        close_px = bars[-1].close
        high = self._high
        high_m = bars[self._high_pos].m
        w15 = [b for b in bars if b.m < cfg.inner_window]
        up15 = sum(b.up_volume for b in w15)
        dn15 = sum(b.down_volume for b in w15)
        inner15 = dn15 / (up15 + dn15) if up15 + dn15 > 0 else None
        touched = high >= self._t1_limit - cfg.limit_eps
        if again:
            path = "再鎖"
        elif touched:
            path = "觸停回落"
        elif (high >= open_px * (1 + cfg.pull_high_min) and close_px < open_px
              and high_m <= cfg.pull_high_max_idx):
            path = "拉高出貨"
        elif high <= open_px * 1.01 and close_px < open_px:
            path = "開盤直倒"
        elif open_px < self._ctx.limit and close_px > open_px:
            path = "低開反拉"
        elif close_px < open_px:
            path = "陰跌"
        else:
            path = "強勢收高"
        gap = open_px / self._ctx.limit - 1
        return T1OpenSignals(
            open_px=open_px,
            gap=gap,
            gap_bucket=_gap_bucket(cfg, gap),
            auction_lots=bars[0].volume,
            auction_share_adv20=self._auction_share_adv20(),
            auction_tell=_auction_tell(cfg, self._auction_share_adv20()),
            auction_share_dayvol=bars[0].volume / day_vol,
            inner15=inner15,
            high_idx=high_m,
            high_time=fmt_min(high_m),
            high_vs_open=high / open_px - 1,
            close_vs_open=close_px / open_px - 1,
            touched_limit=touched,
            path=path,
        )
