"""SC-3: 大盤特徵(MTX)日線 + 盤中 1K 正確性."""

from __future__ import annotations

from copycat.backtest.market_features import (
    compute_mkt_daily_features_full,
    compute_mkt_intraday_features,
)
from copycat.data.models import Bar1K


def _bar(m: int, o: float, h: float, lo: float, c: float, up: float = 50, dn: float = 50) -> Bar1K:
    return Bar1K(
        m=m,
        open=o,
        high=h,
        low=lo,
        close=c,
        volume=up + dn,
        up_volume=up,
        down_volume=dn,
        unch_volume=0,
    )


class TestMktDaily:
    def test_ret_and_range_pos(self) -> None:
        rows = [
            {"date": "2026-01-02", "open": 20000, "high": 20200, "low": 19800, "close": 20100},
            {"date": "2026-01-03", "open": 20100, "high": 20300, "low": 19900, "close": 20000},
        ]
        result = compute_mkt_daily_features_full(rows, "2026-01-03")
        assert result["mkt_t_ret"] is not None
        assert abs(result["mkt_t_ret"] - (20000 / 20100 - 1)) < 1e-9
        assert result["mkt_t_range_pos"] is not None
        assert abs(result["mkt_t_range_pos"] - (20000 - 19900) / (20300 - 19900)) < 1e-9

    def test_range_pos_from_low(self) -> None:
        rows = [
            {"date": "2026-01-02", "open": 20000, "high": 20200, "low": 19800, "close": 20100},
            {"date": "2026-01-03", "open": 20100, "high": 20300, "low": 19900, "close": 19900},
        ]
        result = compute_mkt_daily_features_full(rows, "2026-01-03")
        assert result["mkt_t_range_pos"] is not None
        assert abs(result["mkt_t_range_pos"] - 0.0) < 1e-9

    def test_missing_date(self) -> None:
        rows = [{"date": "2026-01-02", "open": 20000, "high": 20200, "low": 19800, "close": 20100}]
        result = compute_mkt_daily_features_full(rows, "2026-01-05")
        assert result["mkt_t_ret"] is None

    def test_5day_ret(self) -> None:
        rows = [
            {
                "date": f"2026-01-{2 + i:02d}",
                "open": 100,
                "high": 110,
                "low": 90,
                "close": 100 + i * 2,
            }
            for i in range(6)
        ]
        result = compute_mkt_daily_features_full(rows, "2026-01-07")
        assert result["mkt_t5_ret"] is not None
        assert abs(result["mkt_t5_ret"] - (110 / 100 - 1)) < 1e-9


class TestMktIntraday:
    def test_basic(self) -> None:
        bars = [
            _bar(0, 20000, 20100, 19950, 20050, up=80, dn=20),
            _bar(1, 20050, 20150, 20000, 20100, up=60, dn=40),
            _bar(2, 20100, 20200, 20050, 20080, up=40, dn=60),
        ]
        result = compute_mkt_intraday_features(bars, trigger_m=2)
        assert result["mkt_t1_ret_to_trigger"] is not None
        assert abs(result["mkt_t1_ret_to_trigger"] - (20080 / 20000 - 1)) < 1e-9
        assert result["mkt_t1_from_high"] is not None
        assert abs(result["mkt_t1_from_high"] - (1 - 20080 / 20200)) < 1e-9
        assert result["mkt_t1_range_pos"] is not None
        rng = 20200 - 19950
        assert abs(result["mkt_t1_range_pos"] - (20080 - 19950) / rng) < 1e-9

    def test_inner_ratio(self) -> None:
        bars = [
            _bar(0, 100, 101, 99, 100, up=80, dn=20),
            _bar(1, 100, 101, 99, 100, up=30, dn=70),
            _bar(2, 100, 101, 99, 100, up=20, dn=80),
            _bar(3, 100, 101, 99, 100, up=10, dn=90),
            _bar(4, 100, 101, 99, 100, up=15, dn=85),
            _bar(5, 100, 101, 99, 100, up=25, dn=75),
        ]
        result = compute_mkt_intraday_features(bars, trigger_m=5)
        assert result["mkt_t1_inner"] is not None
        up_5 = 30 + 20 + 10 + 15 + 25  # last 5 bars (idx 1-5)
        dn_5 = 70 + 80 + 90 + 85 + 75
        expected = dn_5 / (up_5 + dn_5)
        assert abs(result["mkt_t1_inner"] - expected) < 1e-9

    def test_empty_bars(self) -> None:
        result = compute_mkt_intraday_features([], trigger_m=5)
        assert result["mkt_t1_ret_to_trigger"] is None

    def test_trigger_before_first_bar(self) -> None:
        bars = [_bar(5, 100, 101, 99, 100)]
        result = compute_mkt_intraday_features(bars, trigger_m=3)
        assert result["mkt_t1_ret_to_trigger"] is None
