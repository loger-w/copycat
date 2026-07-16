"""round 4 cells 評估路徑:分流 gate / m7 臂 / fallback / 消融 / 精算擴充(change-spec §5.4)."""

from __future__ import annotations

import dataclasses

from copycat.backtest.fade_cells import (
    _simulate_r3_trades,
    _stats_block,
    _tp_actuarial_block,
    _TradeRec,
    evaluate_cells_from_universe,
)
from copycat.backtest.fade_config import FadeBacktestConfig
from copycat.backtest.fade_simulate import FadeSample
from copycat.data.models import Bar1K
from copycat.market import tick_size

_WATCH = frozenset({"9227"})


def _bar(m: int, o: float, h: float, lo: float, c: float, vol: float = 100) -> Bar1K:
    return Bar1K(
        m=m,
        open=o,
        high=h,
        low=lo,
        close=c,
        volume=vol,
        up_volume=30,
        down_volume=70,
        unch_volume=0,
    )


def _sample(t1_date: str = "2026-03-02") -> FadeSample:
    return FadeSample(
        stock_id="2330",
        date="2026-03-01",
        t1_date=t1_date,
        limit=50.0,  # t1_limit = 55.0
        t1_open=52.0,
        gap=0.04,
        broker_ids="9227",
    )


def _flat_day(n: int = 30) -> list[Bar1K]:
    return [_bar(m, 52.0, 52.1, 51.8, 52.0) for m in range(n)]


_R4_CFG = FadeBacktestConfig(
    struct_stop_buffers=(0.025,),
    guard_limit_dist=0.01,
    disaster_arm_x=0.06,
    disaster_retrace_r=0.02,
    base_arm=True,
    inner_flip_phi_grid=(0.45,),
    tp_flush_z=3.0,
    tp_flush_lookback=3,
    tp_flush_recovery=0.5,
    tp_flush_min_profit=0.005,
    tp_hl_k=2,
    tp_hl_min_profit=0.005,
)


class TestM7Arm:
    def test_m7_arm_enters_at_baseline_idx(self) -> None:
        cfg = FadeBacktestConfig()
        uni = [(_sample(), _flat_day())]
        trades, _ = _simulate_r3_trades(uni, "m7_arm", 0.0, 0.025, cfg, 1, _WATCH)
        assert len(trades) == 1
        t = trades[0]
        # 進場 = m6 bar close − 1 tick(entry_price 由引擎回傳)
        entry = 52.0 - tick_size(52.0)
        assert t.entry_price is not None
        assert abs(t.entry_price - entry) < 1e-9

    def test_closeout_hold_pnl_equals_pnl(self) -> None:
        cfg = FadeBacktestConfig()
        uni = [(_sample(), _flat_day())]
        trades, _ = _simulate_r3_trades(uni, "m7_arm", 0.0, 0.025, cfg, 1, _WATCH)
        t = trades[0]
        # closeout 交易:抱到收盤 = 實際出場 → hold_pnl == pnl
        assert t.hold_pnl is not None
        assert abs(t.hold_pnl - t.pnl) < 1e-9
        assert t.mfe is not None


class TestDispatchGate:
    def test_round4_gate_takes_priority(self) -> None:
        uni = [(_sample(), _flat_day())]
        result = evaluate_cells_from_universe(uni, [], _R4_CFG, _WATCH, cellb_universe=uni)
        assert result.get("round4") is True

    def test_round3_config_still_routes_round3(self) -> None:
        cfg = FadeBacktestConfig(
            struct_stop_buffers=(0.025, 0.0375),
            guard_limit_dist=0.01,
            disaster_arm_x=0.06,
            disaster_retrace_r=0.02,
            base_arm=True,
        )
        uni = [(_sample(), _flat_day())]
        result = evaluate_cells_from_universe(uni, [], cfg, _WATCH, cellb_universe=uni)
        assert result.get("round3") is True
        assert "round4" not in result


class TestFallbacks:
    def test_fallback1_empty_phi_grid_runs_with_none(self) -> None:
        cfg = dataclasses.replace(_R4_CFG, inner_flip_phi_grid=())
        uni = [(_sample(), _flat_day())]
        result = evaluate_cells_from_universe(uni, [], cfg, _WATCH, cellb_universe=uni)
        fallbacks = result.get("fallbacks")
        assert isinstance(fallbacks, dict)
        assert fallbacks["inner_flip_demoted"] is True
        ablation = result.get("ablation")
        assert isinstance(ablation, dict)
        assert "stop_inner_only" not in ablation

    def test_fallback2_no_hl_skips_hl_ablation(self) -> None:
        cfg = dataclasses.replace(_R4_CFG, tp_hl_k=None, tp_hl_min_profit=None)
        uni = [(_sample(), _flat_day())]
        result = evaluate_cells_from_universe(uni, [], cfg, _WATCH, cellb_universe=uni)
        fallbacks = result.get("fallbacks")
        assert isinstance(fallbacks, dict)
        assert fallbacks["tp_hl_demoted"] is True
        ablation = result.get("ablation")
        assert isinstance(ablation, dict)
        assert "hl_only" not in ablation

    def test_full_config_has_all_ablations(self) -> None:
        uni = [(_sample(), _flat_day())]
        result = evaluate_cells_from_universe(uni, [], _R4_CFG, _WATCH, cellb_universe=uni)
        ablation = result.get("ablation")
        assert isinstance(ablation, dict)
        assert set(ablation) == {
            "tp_off",
            "flush_only",
            "hl_only",
            "stop_inner_only",
            "stop_struct_only",
        }


class TestStatsAndActuarial:
    def test_stats_block_profit_factor(self) -> None:
        trades = [(0.02, "2026-03-02"), (0.01, "2026-03-03"), (-0.01, "2026-03-04")]
        from datetime import date

        stats = _stats_block(trades, date(2026, 3, 1), 10.0, 4)
        assert stats["avg_win"] == 0.015
        assert stats["avg_loss"] == -0.01
        assert isinstance(stats["profit_factor"], float)
        assert abs(stats["profit_factor"] - 3.0) < 1e-9

    def test_tp_actuarial_saved(self) -> None:
        trades = [
            _TradeRec(
                pnl=0.02,
                day="2026-03-02",
                exit_reason="tp_flush",
                locked_close=False,
                gap=0.04,
                hits=1,
                mfe=0.03,
                hold_pnl=0.01,
            ),
            _TradeRec(
                pnl=0.01,
                day="2026-03-03",
                exit_reason="tp_flush",
                locked_close=True,
                gap=0.04,
                hits=1,
                mfe=0.02,
                hold_pnl=None,  # 收盤鎖死日,排除 saved
            ),
            _TradeRec(
                pnl=0.005,
                day="2026-03-04",
                exit_reason=None,
                locked_close=False,
                gap=0.04,
                hits=1,
                mfe=0.01,
                hold_pnl=0.005,
            ),
        ]
        blk = _tp_actuarial_block(trades)
        flush = blk["tp_flush"]
        assert isinstance(flush, dict)
        assert flush["n"] == 2
        assert flush["saved_mean"] == 0.01  # (0.02−0.01);鎖死日排除
        assert flush["saved_excluded_lock"] == 1
        hl = blk["tp_hl"]
        assert isinstance(hl, dict)
        assert hl["n"] == 0
