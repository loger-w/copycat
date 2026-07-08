"""SC-5: 7 類微結構特徵正確性(每類 ≥ 1 hand-crafted case)."""

from __future__ import annotations

from copycat.backtest.fade_features import (
    _auction_mismatch,
    _bid_exhaustion,
    _intraday_basic,
    _open_eq_high_count,
    _price_vol_divergence,
    _retest_failure,
    _speed_of_decline,
    _unch_vol_spike,
    fade_trigger_features,
)
from copycat.data.models import Bar1K


def _bar(
    m: int,
    o: float,
    h: float,
    lo: float,
    c: float,
    vol: float = 100,
    up: float = 50,
    dn: float = 50,
    unch: float = 0,
) -> Bar1K:
    return Bar1K(
        m=m,
        open=o,
        high=h,
        low=lo,
        close=c,
        volume=vol,
        up_volume=up,
        down_volume=dn,
        unch_volume=unch,
    )


class TestUnchVolSpike:
    def test_single_bar(self) -> None:
        bars = [_bar(0, 50, 51, 49, 50, vol=100, unch=30)]
        result = _unch_vol_spike(bars, 0)
        val = result["unch_vol_spike_n1"]
        assert val is not None
        assert abs(val - 0.3) < 1e-9

    def test_window_average(self) -> None:
        bars = [
            _bar(0, 50, 51, 49, 50, vol=100, unch=10),
            _bar(1, 50, 51, 49, 50, vol=100, unch=50),
        ]
        result = _unch_vol_spike(bars, 1)
        val = result["unch_vol_spike_n2"]
        assert val is not None
        assert abs(val - 0.3) < 1e-9


class TestPriceVolDivergence:
    def test_divergence_detected(self) -> None:
        bars = [
            _bar(0, 50, 51.0, 49, 50, vol=300),
            _bar(1, 50, 51.5, 49, 50, vol=250),  # high up, vol down
            _bar(2, 50, 52.0, 49, 50, vol=200),  # high up, vol down
        ]
        result = _price_vol_divergence(bars, 2)
        assert result["pvd_n3_d0"] == 2 / 2  # 2 out of 2 transitions

    def test_no_divergence(self) -> None:
        bars = [
            _bar(0, 50, 51.0, 49, 50, vol=100),
            _bar(1, 50, 50.5, 49, 50, vol=200),  # high down, vol up
            _bar(2, 50, 50.0, 49, 50, vol=300),  # high down, vol up
        ]
        result = _price_vol_divergence(bars, 2)
        assert result["pvd_n3_d0"] == 0.0


class TestOpenEqHigh:
    def test_all_open_eq_high(self) -> None:
        bars = [
            _bar(0, 50.0, 50.01, 49, 49.5),  # (50.01-50)/50 = 0.0002
            _bar(1, 51.0, 51.02, 50, 50.5),  # (51.02-51)/51 ≈ 0.00039
            _bar(2, 52.0, 52.01, 51, 51.5),  # (52.01-52)/52 ≈ 0.00019
        ]
        result = _open_eq_high_count(bars, 2)
        assert result["oeh_n3_t5"] == 1.0  # all 3 within tol=0.0005

    def test_none_match(self) -> None:
        bars = [
            _bar(0, 50.0, 52.0, 49, 50),
            _bar(1, 50.0, 53.0, 49, 50),
            _bar(2, 50.0, 54.0, 49, 50),
        ]
        result = _open_eq_high_count(bars, 2)
        assert result["oeh_n3_t5"] == 0.0


class TestBidExhaustion:
    def test_consecutive_low_buying(self) -> None:
        bars = [
            _bar(0, 50, 51, 49, 50, up=80, dn=20),
            _bar(1, 50, 51, 49, 50, up=5, dn=95),  # up/(up+dn) = 0.05 < 0.20
            _bar(2, 50, 51, 49, 50, up=10, dn=90),  # 0.10 < 0.20
        ]
        result = _bid_exhaustion(bars, 2)
        assert result["bidex_t20_lb5"] == 2.0

    def test_broken_streak(self) -> None:
        bars = [
            _bar(0, 50, 51, 49, 50, up=5, dn=95),
            _bar(1, 50, 51, 49, 50, up=50, dn=50),  # 0.50 >= 0.20 breaks streak
            _bar(2, 50, 51, 49, 50, up=5, dn=95),
        ]
        result = _bid_exhaustion(bars, 2)
        assert result["bidex_t20_lb5"] == 1.0


class TestSpeedOfDecline:
    def test_decline_rate(self) -> None:
        bars = [
            _bar(0, 55, 56, 54, 55),
            _bar(1, 55, 55, 54, 54),
            _bar(2, 54, 54, 53, 53),
        ]
        result = _speed_of_decline(bars, 2)
        expected = (55 - 53) / 55 / 2  # n=2: (bars[-3].close - bars[-1].close) / bars[-3].close / 2
        assert result["decline_speed_n2"] is not None
        assert abs(result["decline_speed_n2"] - expected) < 1e-9


class TestRetestFailure:
    def test_retest_detected(self) -> None:
        bars = [
            _bar(0, 50, 55, 49, 54),  # peak = 55
            _bar(1, 54, 54.9, 53, 53.5),  # retest: 54.9 >= 55*(1-0.003)=54.835, < 55
            _bar(2, 53.5, 54, 52, 52.5),
        ]
        result = _retest_failure(bars, 2)
        assert result["retest_fail_nr30"] == 1.0
        assert result["retest_depth_nr30"] is not None
        assert abs(result["retest_depth_nr30"] - (55 - 54.9) / 55) < 1e-9

    def test_no_retest(self) -> None:
        bars = [
            _bar(0, 50, 55, 49, 54),
            _bar(1, 54, 54, 53, 53.5),  # 54 < 55*0.997=54.835 → not near enough
            _bar(2, 53.5, 53, 52, 52.5),
        ]
        result = _retest_failure(bars, 2)
        assert result["retest_fail_nr30"] == 0.0


class TestAuctionMismatch:
    def test_mismatch_ratio(self) -> None:
        bars = [
            _bar(0, 50, 51, 49, 50, vol=500),  # auction
            _bar(1, 50, 51, 49, 50, vol=100),
            _bar(2, 50, 51, 49, 50, vol=100),
        ]
        result = _auction_mismatch(bars, 2)
        assert result["auc_mismatch_n2"] is not None
        assert abs(result["auc_mismatch_n2"] - 5.0) < 1e-9

    def test_balanced(self) -> None:
        bars = [
            _bar(0, 50, 51, 49, 50, vol=100),
            _bar(1, 50, 51, 49, 50, vol=100),
            _bar(2, 50, 51, 49, 50, vol=100),
        ]
        result = _auction_mismatch(bars, 2)
        assert result["auc_mismatch_n2"] is not None
        assert abs(result["auc_mismatch_n2"] - 1.0) < 1e-9


class TestIntradayBasic:
    def test_consecutive_red(self) -> None:
        bars = [
            _bar(0, 50, 51, 49, 50.5),  # green
            _bar(1, 50, 51, 49, 49.5),  # red
            _bar(2, 50, 51, 49, 49.0),  # red
            _bar(3, 50, 51, 49, 48.5),  # red (trigger)
        ]
        result = _intraday_basic(bars, 3)
        assert result["consecutive_red"] == 2.0  # bars before trig: bar 1 and 2 are red

    def test_time_since_high(self) -> None:
        bars = [
            _bar(0, 50, 55, 49, 54),  # rolling high = 55 at idx 0
            _bar(1, 54, 54, 53, 53),
            _bar(2, 53, 53, 52, 52),  # trigger
        ]
        result = _intraday_basic(bars, 2)
        assert result["time_since_high"] == 2.0


class TestFadeTriggerFeaturesIntegration:
    def test_returns_all_feature_groups(self) -> None:
        bars = [_bar(i, 50, 52, 49, 50 + i * 0.1, vol=100, up=60, dn=40, unch=5) for i in range(20)]
        result = fade_trigger_features(
            bars,
            trig_idx=19,
            lock_features={"lock_time_min": 10.0, "opens_count": 2.0},
            t1_features={"gap_pct": 0.04},
            static_features={"ret5": 0.05},
            mkt_daily={"mkt_t_ret": 0.01},
            mkt_intraday={"mkt_t1_ret_to_trigger": 0.005},
        )
        assert "unch_vol_spike_n1" in result
        assert "pvd_n3_d0" in result
        assert "oeh_n3_t5" in result
        assert "bidex_t20_lb5" in result
        assert "decline_speed_n2" in result
        assert "retest_fail_nr30" in result
        assert "auc_mismatch_n2" in result
        assert result["lock_time_min"] == 10.0
        assert result["gap_pct"] == 0.04
        assert result["ret5"] == 0.05
        assert result["mkt_t_ret"] == 0.01
        assert result["mkt_t1_ret_to_trigger"] == 0.005
        assert len(result) > 200
