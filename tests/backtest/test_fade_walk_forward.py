"""SC-5:walk-forward 去汙染 — fold 切分、val 選擇不碰 test、OOS 串接、分層(SC-6)."""

from __future__ import annotations

from copycat.backtest.fade_config import FadeBacktestConfig
from copycat.backtest.fade_optimize import _fold_test_indices
from copycat.backtest.fade_pipeline import _add_months, _run_walk_forward
from copycat.backtest.fade_simulate import FadeSample
from copycat.data.models import Bar1K


def test_add_months() -> None:
    assert _add_months("2026-01-01", 2) == "2026-03-01"
    assert _add_months("2026-11-01", 2) == "2027-01-01"
    assert _add_months("2026-07-01", 6) == "2027-01-01"


def test_fold_test_indices_double_bounded() -> None:
    dates = ["2026-01-05", "2026-02-28", "2026-03-01", "2026-04-30", "2026-05-01"]
    mask = (1 << 5) - 1  # 全命中
    assert _fold_test_indices(mask, dates, "2026-03-01", "2026-05-01") == [2, 3]


def _bar(m: int, o: float, h: float, lo: float, c: float) -> Bar1K:
    return Bar1K(
        m=m,
        open=o,
        high=h,
        low=lo,
        close=c,
        volume=100,
        up_volume=50,
        down_volume=50,
        unch_volume=0,
    )


def _mk_sample(i: int, t1: str, winner: bool, source: str) -> tuple[FadeSample, list[Bar1K], int]:
    sample = FadeSample(
        stock_id=f"S{i:04d}",
        date=t1,  # date 欄在 wf 不參與切分,簡化
        t1_date=t1,
        limit=50.0,
        t1_open=52.0,
        gap=0.04,
        broker_ids="",
        source=source,
    )
    if winner:  # 空方賺:走跌
        bars = [_bar(0, 52.0, 52.5, 51.5, 52.0), _bar(1, 52.0, 52.0, 48.5, 49.0)]
    else:  # 空方虧:走漲(不觸漲停 55)
        bars = [_bar(0, 52.0, 52.5, 51.5, 52.0), _bar(1, 52.0, 54.5, 52.0, 54.4)]
    return sample, bars, 0


def _build_dataset() -> tuple[
    list[tuple[FadeSample, list[Bar1K], int]],
    list[dict[str, float | None]],
    list[float],
    list[str],
]:
    """f1=1 在 train/val 賺、test 虧;f2=1 相反。val 端選擇必挑 f1 → OOS 必為負。"""
    tradeable: list[tuple[FadeSample, list[Bar1K], int]] = []
    feats: list[dict[str, float | None]] = []
    pnls: list[float] = []
    dates: list[str] = []
    i = 0

    def _add(t1: str, f1: float, winner: bool, source: str = "control") -> None:
        nonlocal i
        s = _mk_sample(i, t1, winner, source)
        tradeable.append(s)
        feats.append({"f1": f1, "f2": 1.0 - f1})
        pnls.append(0.05 if winner else -0.05)  # default-combo pnl 近似值(選擇用)
        dates.append(t1)
        i += 1

    # core:2026-01(f1 賺 × 20、f2 虧 × 20)+ 2026-02(同構 × 各 10)
    for d in range(1, 21):
        _add(f"2026-01-{d:02d}", 1.0, True)
        _add(f"2026-01-{d:02d}", 0.0, False)
    for d in range(1, 11):
        _add(f"2026-02-{d:02d}", 1.0, True)
        _add(f"2026-02-{d:02d}", 0.0, False)
    # val 尾段:2026-03(f1 賺 × 10、f2 虧 × 10)
    for d in range(1, 11):
        _add(f"2026-03-{d:02d}", 1.0, True)
        _add(f"2026-03-{d:02d}", 0.0, False)
    # fold test(2026-04 起):f1 全虧(tiger)、f2 全賺(control)— 若選擇碰 test 會挑 f2
    for d in range(1, 11):
        _add(f"2026-04-{d:02d}", 1.0, False, source="tiger_csv")
        _add(f"2026-04-{d:02d}", 0.0, True, source="control")
    return tradeable, feats, pnls, dates


_WF_CFG = FadeBacktestConfig(
    wf_test_starts=("2026-04-01",),
    wf_test_months=2,
    wf_val_frac=0.25,
    ga_seeds=(),  # 只用 exhaustive_scan,測試求快且確定性
    support_raw_min=10,
    support_weighted_min=10.0,
    quantile_probs=(0.5,),
)


def test_selection_ignores_test_and_oos_is_honest() -> None:
    tradeable, feats, pnls, dates = _build_dataset()
    wf = _run_walk_forward(tradeable, feats, pnls, dates, _WF_CFG)
    assert wf["n_folds"] == 1
    folds = wf["folds"]
    assert isinstance(folds, list)
    conds = folds[0]["conditions"]
    # val 端選擇必挑 f1 規則(test 端 f2 更賺,但選擇不得碰 test)
    assert any(c["feature"] == "f1" and c["op"] == ">=" for c in conds)
    oos = wf["oos"]
    assert isinstance(oos, dict)
    assert oos["n"] == 10  # 只有 f1 匹配的 test 樣本
    exp = oos["expectancy"]
    assert isinstance(exp, float) and exp < 0  # 誠實的負 OOS,證明無 test 洩漏


def test_oos_no_cross_fold_duplication() -> None:
    tradeable, feats, pnls, dates = _build_dataset()
    cfg = FadeBacktestConfig(
        wf_test_starts=("2026-04-01", "2026-06-01"),  # 第二 fold test 無資料
        wf_test_months=2,
        wf_val_frac=0.25,
        ga_seeds=(),
        support_raw_min=10,
        support_weighted_min=10.0,
        quantile_probs=(0.5,),
    )
    wf = _run_walk_forward(tradeable, feats, pnls, dates, cfg)
    trades = wf["oos_trades"]
    assert isinstance(trades, list)
    keys = [(t["stock_id"], t["date"]) for t in trades]
    assert len(keys) == len(set(keys))  # R12:無跨 fold 重複


def test_oos_by_source_split() -> None:
    tradeable, feats, pnls, dates = _build_dataset()
    wf = _run_walk_forward(tradeable, feats, pnls, dates, _WF_CFG)
    by_source = wf["oos_by_source"]
    assert isinstance(by_source, dict)
    assert "tiger_csv" in by_source  # f1 test 樣本全標 tiger
    assert by_source["tiger_csv"]["n"] == 10


def test_guard_sensitivity_is_diagnostic_only() -> None:
    tradeable, feats, pnls, dates = _build_dataset()
    wf = _run_walk_forward(tradeable, feats, pnls, dates, _WF_CFG)
    sens = wf["guard_sensitivity"]
    assert isinstance(sens, dict)
    assert set(sens) == {"0.02", "0.03", "0.04"}
