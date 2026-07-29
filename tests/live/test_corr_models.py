"""corr_models 純函數:中價與對數報酬(SC-2)。"""

from __future__ import annotations

import math

from copycat.live.corr_models import log_return, mid_from_book


class TestMidFromBook:
    def test_both_sides_present_returns_midpoint(self) -> None:
        bids = [(40399000, 5), (40398000, 3)]
        asks = [(40401000, 4), (40402000, 2)]
        assert mid_from_book(bids, asks) == 40400000

    def test_uses_best_level_only_not_deeper_levels(self) -> None:
        # L1 以下不得影響中價 —— 只取 L0
        bids = [(100_000, 1), (1, 999)]
        asks = [(102_000, 1), (999_999, 999)]
        assert mid_from_book(bids, asks) == 101_000

    def test_odd_sum_floors(self) -> None:
        # 毫點整數運算:奇數和取整除(誤差 0.5 毫點,遠小於實際波動)
        assert mid_from_book([(1001, 1)], [(1002, 1)]) == 1001

    def test_empty_bid_side_returns_none(self) -> None:
        assert mid_from_book([], [(40401000, 4)]) is None

    def test_empty_ask_side_returns_none(self) -> None:
        assert mid_from_book([(40399000, 5)], []) is None

    def test_both_empty_returns_none(self) -> None:
        assert mid_from_book([], []) is None


class TestLogReturn:
    def test_computes_log_ratio(self) -> None:
        got = log_return(100_000, 101_000)
        assert got is not None
        assert math.isclose(got, math.log(1.01), rel_tol=1e-12)

    def test_identical_prices_return_zero(self) -> None:
        assert log_return(40_400_000, 40_400_000) == 0.0

    def test_zero_prev_returns_none(self) -> None:
        assert log_return(0, 100) is None

    def test_zero_cur_returns_none(self) -> None:
        assert log_return(100, 0) is None

    def test_negative_returns_none(self) -> None:
        assert log_return(-100, 100) is None
