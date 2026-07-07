from __future__ import annotations

import pytest

from copycat.data.models import Bar1K
from copycat.engine.t1_open import EventContext, T1OpenSignals, T1Tracker
from copycat.strategy_config import StrategyConfig

CFG = StrategyConfig.default()
LIMIT_T = 100.0  # T 日漲停收盤


def ctx(adv20: float | None = 1000.0, t1_open_px: float | None = None,
        auction_lots_tick: float | None = None) -> EventContext:
    return EventContext(stock_id="1104", date="2025-09-10", t1_date="2025-09-11",
                        limit=LIMIT_T, adv20_lots=adv20, one_price=False,
                        board_streak=1, lock=None, t1_open_px=t1_open_px,
                        auction_lots_tick=auction_lots_tick)


def bar(m: int, close: float, *, open_: float | None = None, high: float | None = None,
        v: float = 10.0, uv: float | None = None, dv: float | None = None) -> Bar1K:
    o = open_ if open_ is not None else close
    h = high if high is not None else max(o, close)
    u = uv if uv is not None else v
    d = dv if dv is not None else 0.0
    return Bar1K(m=m, open=o, high=h, low=min(o, close), close=close,
                 volume=v, up_volume=u, down_volume=d, unch_volume=0.0)


def run(bars: list[Bar1K], again: bool = False,
        adv20: float | None = 1000.0) -> T1OpenSignals | None:
    t = T1Tracker(CFG, ctx(adv20))
    for b in bars:
        t.feed(b)
    return t.finalize(again)


def _bucket(bars: list[Bar1K]) -> str:
    sig = run(bars)
    assert sig is not None
    return sig.gap_bucket


def test_gap_buckets() -> None:
    # 開 103 → gap 3% → "3-7%"
    sig = run([bar(0, 103.0, v=100.0), bar(1, 104.0)])
    assert sig is not None
    assert sig.gap == pytest.approx(0.03) and sig.gap_bucket == "3-7%"
    assert _bucket([bar(0, 99.0)]) == "<0%"
    assert _bucket([bar(0, 100.5)]) == "0-1%"
    assert _bucket([bar(0, 108.0)]) == "7-9.5%"
    assert _bucket([bar(0, 110.0)]) == "漲停開"


def test_auction_tell_uses_adv20() -> None:
    # 首根量 100 張 / adv20 1000 張 = 10% → ">=8%"
    sig = run([bar(0, 103.0, v=100.0), bar(1, 104.0, v=50.0)])
    assert sig is not None
    assert sig.auction_lots == 100.0
    assert sig.auction_share_adv20 == pytest.approx(0.10)
    assert sig.auction_tell == ">=8%"
    assert sig.auction_share_dayvol == pytest.approx(100.0 / 150.0)  # 研究版(收盤定稿)


def test_auction_tell_without_adv20_is_na() -> None:
    sig = run([bar(0, 103.0)], adv20=None)
    assert sig is not None and sig.auction_tell == "n/a" and sig.auction_share_adv20 is None


def test_inner15_window() -> None:
    # 前 15 分鐘:內盤 60 / (40+60) = 60%;m=20 的 bar 不計入
    bars = [bar(0, 103.0, v=100.0, uv=40.0, dv=60.0), bar(20, 104.0, v=50.0, uv=50.0, dv=0.0)]
    sig = run(bars)
    assert sig is not None and sig.inner15 == pytest.approx(0.60)


def test_path_pull_high_dump() -> None:
    # 開 103 → 8 分鐘拉到 106(+2.9% ≥2%)→ 收 101(< 開)→ 拉高出貨
    bars = [bar(0, 103.0), bar(8, 106.0), bar(200, 101.0)]
    sig = run(bars)
    assert sig is not None
    assert sig.path == "拉高出貨" and sig.high_idx == 8 and sig.high_time == "09:09"


def test_path_touched_and_again() -> None:
    bars = [bar(0, 109.5), bar(1, 108.0, high=110.0)]
    sig = run(bars)
    assert sig is not None and sig.touched_limit is True and sig.path == "觸停回落"
    sig2 = run(bars, again=True)
    assert sig2 is not None and sig2.path == "再鎖"


def test_path_low_open_rebound() -> None:
    bars = [bar(0, 98.0), bar(30, 101.0)]
    sig = run(bars)
    assert sig is not None and sig.path == "低開反拉"


def test_intraday_query_immutable() -> None:
    # 首根餵入後 gap / auction_tell 即可查,之後不變(SC-8)
    t = T1Tracker(CFG, ctx())
    t.feed(bar(0, 103.0, v=100.0))
    g, tell = t.gap, t.auction_tell
    t.feed(bar(1, 108.0, v=500.0))
    assert t.gap == g and t.auction_tell == tell


def test_empty_returns_none() -> None:
    t = T1Tracker(CFG, ctx())
    assert t.finalize(False) is None


def test_feed_non_increasing_raises() -> None:
    t = T1Tracker(CFG, ctx())
    t.feed(bar(3, 103.0))
    with pytest.raises(ValueError):
        t.feed(bar(2, 104.0))


def test_t1_open_px_override_wins_gap() -> None:
    # 日線 open(權威競價價)與 1K 首根 open 不同時,gap 以日線為準
    t = T1Tracker(CFG, ctx(t1_open_px=99.5))
    t.feed(bar(0, 103.0, v=100.0))
    assert t.gap == pytest.approx(-0.005)
    sig = t.finalize(False)
    assert sig is not None
    assert sig.open_px == 99.5 and sig.gap_bucket == "<0%"


def test_auction_lots_tick_override() -> None:
    # tick 競價量(純 09:00:06 那筆)優先於 1K 首根 volume
    sig = run_with_ctx([bar(0, 103.0, v=100.0), bar(1, 104.0, v=60.0)],
                       ctx(auction_lots_tick=20.0))
    assert sig is not None
    assert sig.auction_lots == 20.0
    assert sig.auction_share_adv20 == pytest.approx(0.02)
    assert sig.auction_tell == "<3%"
    assert sig.auction_share_dayvol == pytest.approx(20.0 / 160.0)


def run_with_ctx(bars: list[Bar1K], context: EventContext) -> T1OpenSignals | None:
    t = T1Tracker(CFG, context)
    for b in bars:
        t.feed(b)
    return t.finalize(False)
