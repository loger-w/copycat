"""Phase B 停損/停利對決 + 臂間對決 + 報告 整合測試."""

from __future__ import annotations

from copycat.backtest.fade_config import (
    FadeBacktestConfig,
    FadeStopCombo,
    FadeTakeProfitCombo,
)
from copycat.backtest.fade_optimize import optimize_rule_stops, optimize_rule_tp
from copycat.backtest.fade_simulate import FadeSample
from copycat.data.models import Bar1K

_CFG = FadeBacktestConfig(split_date="2026-01-10")


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


def _combo(**kw: object) -> FadeStopCombo:
    defaults: dict[str, object] = {
        "s1_n": None,
        "s1_phi": None,
        "s2_m": None,
        "s2_buf": None,
        "s3_x": None,
        "s4_x": None,
        "s5_x": None,
        "t1300": False,
    }
    defaults.update(kw)
    return FadeStopCombo(**defaults)  # type: ignore[arg-type]


_SAMPLE_TRAIN = FadeSample(
    stock_id="2330",
    date="2026-01-05",
    t1_date="2026-01-06",
    limit=50.0,
    t1_open=52.0,
    gap=0.04,
    broker_ids="",
)
_SAMPLE_TEST = FadeSample(
    stock_id="2330",
    date="2026-01-15",
    t1_date="2026-01-16",
    limit=50.0,
    t1_open=52.0,
    gap=0.04,
    broker_ids="",
)

_BARS_PROFITABLE = [
    _bar(0, 52.0, 52.5, 51.5, 52.0),
    _bar(1, 52.0, 52.0, 50.0, 50.5),
    _bar(2, 50.5, 51.0, 49.5, 49.8),
]
_BARS_LOSING = [
    _bar(0, 52.0, 52.5, 51.5, 52.0),
    _bar(1, 52.0, 54.0, 51.5, 53.5),
    _bar(2, 53.5, 55.0, 53.0, 54.5),
]


class TestOptimizeRuleStops:
    def test_basic(self) -> None:
        combos = [_combo(), _combo(s4_x=0.01)]
        tradeable = [
            (_SAMPLE_TRAIN, _BARS_PROFITABLE, 0),
            (_SAMPLE_TRAIN, _BARS_PROFITABLE, 0),
        ]
        feats: list[dict[str, float | None]] = [{"x": 1.0}, {"x": 1.0}]
        dates = ["2026-01-06", "2026-01-07"]
        rules: list[dict[str, object]] = [
            {"conditions": [{"feature": "x", "threshold": 0.5, "op": ">="}]},
        ]
        optimize_rule_stops(tradeable, rules, combos, feats, dates, _CFG)
        assert rules[0].get("best_stop") is not None
        assert rules[0].get("best_stop_params") is not None

    def test_empty_rules(self) -> None:
        rules: list[dict[str, object]] = []
        optimize_rule_stops([], rules, [], [], [], _CFG)
        assert rules == []


class TestOptimizeRuleTp:
    def test_basic(self) -> None:
        tradeable = [
            (_SAMPLE_TRAIN, _BARS_PROFITABLE, 0),
            (_SAMPLE_TEST, _BARS_PROFITABLE, 0),
        ]
        feats: list[dict[str, float | None]] = [{"x": 1.0}, {"x": 1.0}]
        dates = ["2026-01-06", "2026-01-16"]
        rules: list[dict[str, object]] = [
            {
                "conditions": [{"feature": "x", "threshold": 0.5, "op": ">="}],
                "best_stop": _combo().combo_id,
                "best_stop_params": {
                    "s1_n": None,
                    "s1_phi": None,
                    "s2_m": None,
                    "s2_buf": None,
                    "s3_x": None,
                    "s4_x": None,
                    "s5_x": None,
                    "t1300": False,
                },
            },
        ]
        tp_combos = [
            FadeTakeProfitCombo(None, ()),
            FadeTakeProfitCombo("s5", (("s5_x", 0.02),)),
        ]
        optimize_rule_tp(tradeable, rules, tp_combos, feats, dates, _CFG)
        assert rules[0].get("best_tp") is not None
        assert "best_test_expectancy" in rules[0]
        assert "stress_passed" in rules[0]
        assert "stress_expectancy" in rules[0]

    def test_s5_stripped(self) -> None:
        tradeable = [
            (_SAMPLE_TRAIN, _BARS_PROFITABLE, 0),
            (_SAMPLE_TEST, _BARS_PROFITABLE, 0),
        ]
        feats: list[dict[str, float | None]] = [{"x": 1.0}, {"x": 1.0}]
        dates = ["2026-01-06", "2026-01-16"]
        rules: list[dict[str, object]] = [
            {
                "conditions": [{"feature": "x", "threshold": 0.5, "op": ">="}],
                "best_stop": "with_s5",
                "best_stop_params": {
                    "s1_n": None,
                    "s1_phi": None,
                    "s2_m": None,
                    "s2_buf": None,
                    "s3_x": None,
                    "s4_x": None,
                    "s5_x": 0.02,
                    "t1300": False,
                },
            },
        ]
        tp_combos = [FadeTakeProfitCombo(None, ())]
        optimize_rule_tp(tradeable, rules, tp_combos, feats, dates, _CFG)
        assert rules[0].get("best_tp") is not None

    def test_stress_flip(self) -> None:
        tradeable = [
            (_SAMPLE_TRAIN, _BARS_PROFITABLE, 0),
            (_SAMPLE_TEST, _BARS_LOSING, 0),
        ]
        feats: list[dict[str, float | None]] = [{"x": 1.0}, {"x": 1.0}]
        dates = ["2026-01-06", "2026-01-16"]
        rules: list[dict[str, object]] = [
            {
                "conditions": [{"feature": "x", "threshold": 0.5, "op": ">="}],
                "best_stop": _combo().combo_id,
                "best_stop_params": {
                    "s1_n": None,
                    "s1_phi": None,
                    "s2_m": None,
                    "s2_buf": None,
                    "s3_x": None,
                    "s4_x": None,
                    "s5_x": None,
                    "t1300": False,
                },
            },
        ]
        tp_combos = [FadeTakeProfitCombo(None, ())]
        optimize_rule_tp(tradeable, rules, tp_combos, feats, dates, _CFG)
        assert rules[0].get("best_test_expectancy") is not None
        exp = rules[0]["best_test_expectancy"]
        assert isinstance(exp, float)
        assert exp < 0

    def test_empty_rules(self) -> None:
        rules: list[dict[str, object]] = []
        optimize_rule_tp([], rules, [], [], [], _CFG)
        assert rules == []

    def test_no_best_stop(self) -> None:
        rules: list[dict[str, object]] = [
            {
                "conditions": [{"feature": "x", "threshold": 0.5, "op": ">="}],
                "best_stop": None,
                "best_stop_params": None,
            },
        ]
        optimize_rule_tp([], rules, [], [], [], _CFG)
        assert rules[0]["stress_passed"] is False
        assert rules[0]["best_tp"] is None


class TestBuildCrossArmTable:
    def test_ranking(self) -> None:
        from copycat.backtest.fade_optimize import build_cross_arm_table

        results: list[dict[str, object]] = [
            {
                "arm": "pullback",
                "param": {"x_pct": 0.003},
                "rules": [
                    {
                        "best_test_expectancy": 0.005,
                        "stress_expectancy": 0.003,
                        "best_test_p_win": 0.6,
                        "best_test_payoff": 1.5,
                        "best_test_mdd": 0.02,
                        "best_lock_pct": 0.1,
                        "stress_passed": True,
                        "best_stop": "s1",
                        "best_tp": "tp1",
                        "best_test_n": 30,
                    },
                ],
            },
            {
                "arm": "inner_flip",
                "param": {"n_window": 5},
                "rules": [
                    {
                        "best_test_expectancy": 0.008,
                        "stress_expectancy": 0.005,
                        "best_test_p_win": 0.65,
                        "best_test_payoff": 1.8,
                        "best_test_mdd": 0.03,
                        "best_lock_pct": 0.05,
                        "stress_passed": True,
                        "best_stop": "s2",
                        "best_tp": "tp2",
                        "best_test_n": 25,
                    },
                ],
            },
            {
                "arm": "delta_flip",
                "param": {},
                "rules": [
                    {
                        "best_test_expectancy": 0.003,
                        "stress_expectancy": -0.001,
                        "best_test_p_win": 0.55,
                        "best_test_payoff": 1.2,
                        "best_test_mdd": 0.04,
                        "best_lock_pct": 0.15,
                        "stress_passed": False,
                        "best_stop": "s3",
                        "best_tp": "tp3",
                        "best_test_n": 20,
                    },
                ],
            },
        ]
        table = build_cross_arm_table(results)
        assert len(table) == 3
        assert table[0]["arm"] == "inner_flip"
        assert table[0]["rank"] == 1
        assert table[1]["arm"] == "pullback"
        assert table[2]["arm"] == "delta_flip"

    def test_empty_arm(self) -> None:
        from copycat.backtest.fade_optimize import build_cross_arm_table

        results: list[dict[str, object]] = [
            {"arm": "pullback", "param": {}, "rules": []},
            {
                "arm": "inner_flip",
                "param": {},
                "rules": [
                    {
                        "best_test_expectancy": 0.005,
                        "stress_expectancy": 0.003,
                        "best_test_p_win": 0.6,
                        "best_test_payoff": 1.5,
                        "best_test_mdd": 0.02,
                        "best_lock_pct": 0.1,
                        "stress_passed": True,
                        "best_stop": "s1",
                        "best_tp": "tp1",
                        "best_test_n": 30,
                    },
                ],
            },
        ]
        table = build_cross_arm_table(results)
        assert len(table) == 1
        assert table[0]["arm"] == "inner_flip"
