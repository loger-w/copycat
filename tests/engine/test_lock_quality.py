from __future__ import annotations

import pytest

from copycat.data.models import Bar1K
from copycat.engine.lock_quality import LockTracker
from copycat.strategy_config import StrategyConfig

LIMIT = 11.0
CFG = StrategyConfig.default()


def bar(
    m: int, close: float, *, high: float | None = None, open_: float | None = None, v: float = 100.0
) -> Bar1K:
    o = open_ if open_ is not None else close
    h = high if high is not None else max(o, close)
    return Bar1K(
        m=m,
        open=o,
        high=h,
        low=min(o, close),
        close=close,
        volume=v,
        up_volume=v,
        down_volume=0.0,
        unch_volume=0.0,
    )


def run(bars: list[Bar1K]) -> LockTracker:
    t = LockTracker(CFG, LIMIT)
    for b in bars:
        t.feed(b)
    return t


def test_open_lock_strong() -> None:
    # 開盤第一根就鎖到收盤;鎖後量 = 全日量 → strong
    bars = [bar(0, LIMIT, v=100.0)] + [bar(m, LIMIT, v=100.0) for m in range(1, 6)]
    sig = run(bars).finalize()
    assert sig is not None
    assert sig.lock_idx == 0 and sig.lock_time_bucket == "<09:05"
    assert sig.n_reopens == 0
    assert sig.violent_pull is False and sig.prelock10_gain is None  # 窗內無 bar
    assert sig.vol_after_lock_share == 1.0 and sig.queue_bucket == ">=40%"
    assert sig.tier == "strong"


def test_reopen_then_relock() -> None:
    # 鎖(m2)→打開(m3)→回鎖(m4)到收盤:final lock = m4、n_reopens = 1
    bars = [
        bar(0, 10.5),
        bar(1, 10.8),
        bar(2, LIMIT),
        bar(3, 10.9, high=LIMIT),
        bar(4, LIMIT),
        bar(5, LIMIT),
    ]
    sig = run(bars).finalize()
    assert sig is not None
    assert sig.first_touch_idx == 2 and sig.lock_idx == 4 and sig.n_reopens == 1


def test_violent_pull_weak() -> None:
    # m0-m9 在 10.3,m10 拉到漲停鎖死:prelock 窗 [0,10) px0=10.3 → gain 6.8% ≥ 6%
    bars = [bar(m, 10.3) for m in range(10)] + [bar(m, LIMIT, open_=10.3) for m in (10, 11, 12)]
    sig = run(bars).finalize()
    assert sig is not None
    assert sig.violent_pull is True
    assert sig.prelock10_gain == pytest.approx(LIMIT / 10.3 - 1)
    assert sig.tier == "weak"


def test_tail_lock_weak() -> None:
    bars = [bar(m, 10.5) for m in range(239)] + [bar(m, LIMIT) for m in range(239, 245)]
    sig = run(bars).finalize()
    assert sig is not None
    assert sig.lock_time_bucket == "13:00+" and sig.tier == "weak"


def test_vol_after_lock_share_includes_lock_bar() -> None:
    # 鎖後量計法含 final lock bar:(440+60)/1000 = 0.5
    bars = [bar(0, 10.6, v=500.0), bar(1, LIMIT, open_=10.6, v=440.0)] + [
        bar(m, LIMIT, v=10.0) for m in range(2, 8)
    ]
    sig = run(bars).finalize()
    assert sig is not None
    assert sig.lock_idx == 1
    assert sig.vol_after_lock_share == pytest.approx(0.5)


def test_dead_lock_weak_strict() -> None:
    bars = [bar(0, 10.6, v=900.0), bar(1, LIMIT, open_=10.6, v=50.0)] + [
        bar(m, LIMIT, v=10.0) for m in range(2, 7)
    ]
    sig = run(bars).finalize()
    assert sig is not None
    assert sig.queue_bucket == "<15%" and sig.tier == "weak"


def test_never_touch_returns_none() -> None:
    assert run([bar(m, 10.0) for m in range(5)]).finalize() is None


def test_close_not_at_limit_returns_none() -> None:
    # 觸停但收盤掉下來(未鎖收盤)→ 與研究一致回 None
    bars = [bar(0, 10.0), bar(1, LIMIT), bar(2, 10.8, high=LIMIT)]
    assert run(bars).finalize() is None


def test_feed_non_increasing_raises() -> None:
    t = LockTracker(CFG, LIMIT)
    t.feed(bar(5, 10.0))
    with pytest.raises(ValueError):
        t.feed(bar(5, 10.1))


def test_no_lookahead_immutability() -> None:
    # 餵到 t 查詢的 first_touch/n_reopens,繼續餵資料後不得改變(SC-8)
    t = LockTracker(CFG, LIMIT)
    t.feed(bar(0, 10.5))
    t.feed(bar(1, LIMIT))
    ft, nr = t.first_touch_idx, t.n_reopens
    t.feed(bar(2, 10.9, high=LIMIT))  # 打開
    t.feed(bar(3, LIMIT))  # 回鎖
    assert t.first_touch_idx == ft == 1
    assert nr == 0 and t.n_reopens == 1  # 歷史查詢值不變;新值單調前進
