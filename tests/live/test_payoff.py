from __future__ import annotations

from copycat.live.models import OptionContract
from copycat.live.payoff import (
    PositionRow,
    build_grid,
    curve_points,
    extremes,
    find_beps,
    interp_pnl,
    intrinsic_millipts,
)

C43000 = OptionContract(symbol="TC.O.TWF.TX4.202607.C.43000", cp="C", strike_millipts=43_000_000)
P42000 = OptionContract(symbol="TC.O.TWF.TX4.202607.P.42000", cp="P", strike_millipts=42_000_000)

# 手算小例:sell 1 C43000 @100pt、buy 2 P42000 @30pt
ROWS = [
    PositionRow(contract=C43000, net_qty=-1, net_cost_millipts=-100_000),
    PositionRow(contract=P42000, net_qty=2, net_cost_millipts=60_000),
]


class TestIntrinsic:
    def test_call_itm(self) -> None:
        assert intrinsic_millipts("C", 43_000_000, 44_000_000) == 1_000_000

    def test_call_otm_is_zero(self) -> None:
        assert intrinsic_millipts("C", 43_000_000, 42_000_000) == 0

    def test_put_itm(self) -> None:
        assert intrinsic_millipts("P", 42_000_000, 41_000_000) == 1_000_000

    def test_put_otm_is_zero(self) -> None:
        assert intrinsic_millipts("P", 42_000_000, 43_000_000) == 0


class TestBuildGrid:
    def test_strikes_union_extended_one_step(self) -> None:
        grid = build_grid([43_000_000, 42_000_000, 43_000_000])
        assert grid == [41_000_000, 42_000_000, 43_000_000, 44_000_000]

    def test_empty_is_empty(self) -> None:
        assert build_grid([]) == []


class TestCurvePoints:
    def test_hand_computed_grid_values(self) -> None:
        grid = build_grid([c.strike_millipts for c in (C43000, P42000)])
        curve = curve_points(ROWS, grid)
        assert curve == [
            (41_000_000, 102_000.0),
            (42_000_000, 2_000.0),
            (43_000_000, 2_000.0),
            (44_000_000, -48_000.0),
        ]

    def test_no_rows_is_empty(self) -> None:
        assert curve_points([], [41_000_000]) == [(41_000_000, 0.0)]


class TestFindBeps:
    def test_single_crossing_interpolated(self) -> None:
        grid = build_grid([c.strike_millipts for c in (C43000, P42000)])
        curve = curve_points(ROWS, grid)
        assert find_beps(curve) == [43040.0]

    def test_no_crossing(self) -> None:
        assert find_beps([(41_000_000, 5_000.0), (42_000_000, 3_000.0)]) == []


class TestExtremes:
    def test_max_profit_and_loss(self) -> None:
        grid = build_grid([c.strike_millipts for c in (C43000, P42000)])
        curve = curve_points(ROWS, grid)
        max_profit, max_loss = extremes(curve)
        assert max_profit == (41000.0, 102_000.0)
        assert max_loss == (44000.0, -48_000.0)


class TestInterpPnl:
    def test_midpoint_interpolation(self) -> None:
        grid = build_grid([c.strike_millipts for c in (C43000, P42000)])
        curve = curve_points(ROWS, grid)
        assert interp_pnl(curve, 43_500_000) == -23_000.0

    def test_out_of_range_is_none(self) -> None:
        curve = [(42_000_000, 1_000.0), (43_000_000, 2_000.0)]
        assert interp_pnl(curve, 41_000_000) is None
