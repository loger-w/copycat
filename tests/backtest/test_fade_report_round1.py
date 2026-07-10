"""round 1 報告章節:方法論(成本/風控/wf)、分層、guard 敏感度、診斷、附錄."""

from __future__ import annotations

from pathlib import Path

from copycat.backtest.fade_config import FadeBacktestConfig
from copycat.backtest.fade_report import write_fade_report

_WF_RESULT: dict[str, object] = {
    "arm": "vwap_break",
    "param": {},
    "n_triggered": 100,
    "lock_events": 3,
    "rules": [],
    "wf": {
        "folds": [],
        "oos": {"expectancy": 0.02, "p_win": 0.7, "payoff": 1.5, "mdd": 0.05, "n": 20},
        "oos_by_source": {
            "tiger_csv": {"expectancy": 0.03, "p_win": 0.8, "payoff": 1.8, "mdd": 0.03, "n": 8},
            "control": {"expectancy": 0.01, "p_win": 0.6, "payoff": 1.2, "mdd": 0.05, "n": 12},
        },
        "oos_stress": {"expectancy": 0.018, "n": 20},
        "guard_sensitivity": {"0.02": {"expectancy": 0.015, "n": 19}},
        "fold_positive": 3,
        "n_folds": 4,
        "mean_val_exp": 0.04,
        "tp_choices": "tp1|tp2",
        "t1300_choices": "True|True",
    },
}

_CROSS = [
    {
        "rank": 1, "arm": "vwap_break", "param": {}, "test_exp": 0.02, "stress_exp": 0.018,
        "p_win": 0.7, "payoff": 1.5, "mdd": 0.05, "lock_pct": 0.03, "stress_passed": True,
        "best_stop": "True|True", "best_tp": "tp1|tp2", "n_test": 20,
        "fold_positive": 3, "n_folds": 4, "appendix": False,
    },
    {
        "rank": 2, "arm": "pin_bar", "param": {}, "test_exp": 0.01, "stress_exp": 0.005,
        "p_win": 0.6, "payoff": 1.1, "mdd": 0.08, "lock_pct": 0.05, "stress_passed": True,
        "best_stop": "True", "best_tp": "tp4", "n_test": 6,
        "fold_positive": 1, "n_folds": 2, "appendix": True,
    },
]

_DIAGNOSE: dict[str, object] = {
    "n_samples": 100,
    "per_dist": {
        "0.03": {
            "overall": {
                "n": 40, "p_lock": 0.3, "p_reverse": 0.7,
                "reversal_depth_med": 0.04, "reversal_depth_p25": 0.02, "reversal_depth_p75": 0.07,
            },
            "buckets": {},
        }
    },
}


def _write(tmp_path: Path) -> str:
    cfg = FadeBacktestConfig(
        fee_discount=0.84,
        guard_limit_dist=0.03,
        disaster_x=0.04,
        lock_penalty=0.03,
        wf_test_starts=("2026-01-01", "2026-03-01"),
        universe_daytrade_filter=True,
    )
    path = write_fade_report(
        [_WF_RESULT],
        cfg,
        "2026-07-10",
        tmp_path,
        cross_arm_table=_CROSS,
        diagnose=_DIAGNOSE,
        universe_counts={"included": 90, "excluded_no_daytrade": 5},
    )
    return path.read_text(encoding="utf-8")


def test_methodology_reflects_config(tmp_path: Path) -> None:
    text = _write(tmp_path)
    assert "0.1956%" in text  # 1.6 折成本
    assert "防鎖 guard" in text
    assert "walk-forward" in text
    assert "**生效**" in text  # 當沖過濾標注(R7)
    assert "excluded_no_daytrade=5" in text


def test_wf_sections_render(tmp_path: Path) -> None:
    text = _write(tmp_path)
    assert "## 臂間對決(walk-forward OOS)" in text
    assert "多重比較 caveat" in text
    assert "## Walk-forward 分層(tiger vs control)" in text
    assert "tiger_csv" in text
    assert "## Guard 敏感度" in text
    assert "## 逼近漲停診斷" in text


def test_appendix_split_by_min_n(tmp_path: Path) -> None:
    text = _write(tmp_path)
    assert "附錄:n_test < 15" in text
    main_section = text.split("### 附錄")[0]
    assert "pin_bar" not in main_section  # n=6 不入主表
    assert "pin_bar" in text
