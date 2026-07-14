"""劇本格子:三 cell 觸發邊界 / UC 池過濾 / 基準線 / 四等分 / D5(SC-4)."""

from __future__ import annotations

from copycat.backtest.fade_cells import (
    evaluate_cells_from_universe,
    find_cell_a_entry,
    find_cell_b_entry,
    find_cell_c_entry,
)
from copycat.backtest.fade_config import FadeBacktestConfig
from copycat.backtest.fade_simulate import FadeSample
from copycat.data.models import Bar1K

_LIMIT = 55.0  # sample.limit=50 → t1_limit=55


def _bar(m: int, o: float, h: float, lo: float, c: float, up: float = 30, dn: float = 70) -> Bar1K:
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


def _sample(sid: str, t1: str, broker_ids: str = "9227", source: str = "scan") -> FadeSample:
    return FadeSample(
        stock_id=sid,
        date="2026-01-01",
        t1_date=t1,
        limit=50.0,
        t1_open=52.0,
        gap=0.04,
        broker_ids=broker_ids,
        source=source,
    )


_CFG = FadeBacktestConfig()
_WATCH = frozenset({"9227", "9600"})


def _cell_a_bars() -> list[Bar1K]:
    """拉高(53.5 ≥ 52×1.01)→ 回落(52.8 ≤ 53.5×0.992)、headroom 4.2%、內盤比 0.7."""
    return [
        _bar(0, 52.0, 52.2, 51.8, 52.1),
        _bar(1, 52.1, 53.5, 52.0, 53.4),
        _bar(2, 53.4, 53.4, 52.7, 52.8),
        _bar(3, 52.8, 52.9, 50.9, 51.0),
    ]


def test_cell_a_triggers_on_pullback_with_inner_gate() -> None:
    assert find_cell_a_entry(_cell_a_bars(), _LIMIT, 0.45, _CFG) == 2


def test_cell_a_requires_min_rally() -> None:
    bars = [
        _bar(0, 52.0, 52.2, 51.8, 52.1),
        _bar(1, 52.1, 52.4, 51.9, 51.9),  # 高點 52.4 < 52×1.01=52.52 → 沒拉
        _bar(2, 51.9, 52.0, 51.0, 51.1),
    ]
    assert find_cell_a_entry(bars, _LIMIT, 0.45, _CFG) is None


def test_cell_a_requires_inner_ratio() -> None:
    bars = [
        _bar(0, 52.0, 52.2, 51.8, 52.1, up=90, dn=10),
        _bar(1, 52.1, 53.5, 52.0, 53.4, up=90, dn=10),
        _bar(2, 53.4, 53.4, 52.7, 52.8, up=90, dn=10),  # 內盤比 0.1 < 0.45
        _bar(3, 52.8, 52.9, 50.9, 51.0, up=90, dn=10),
    ]
    assert find_cell_a_entry(bars, _LIMIT, 0.45, _CFG) is None


def test_cell_a_window_cutoff() -> None:
    bars = [
        _bar(0, 52.0, 52.2, 51.8, 52.1),
        _bar(61, 52.1, 53.5, 52.0, 53.4),  # 窗外(> cell_a_window_m=60)
        _bar(62, 53.4, 53.4, 52.7, 52.8),
    ]
    assert find_cell_a_entry(bars, _LIMIT, 0.45, _CFG) is None


def test_cell_a_headroom_gate() -> None:
    bars = [  # 回落後收 53.4 → headroom (55−53.4)/53.4 = 3.0% < 4% → 不進
        _bar(0, 52.0, 52.2, 51.8, 52.1),
        _bar(1, 52.1, 54.0, 52.0, 53.9),
        _bar(2, 53.9, 53.9, 53.3, 53.4),
        _bar(3, 53.4, 53.5, 52.9, 53.0),
    ]
    assert find_cell_a_entry(bars, _LIMIT, 0.45, _CFG) is None


def test_cell_b_triggers_after_approach_failure() -> None:
    bars = [  # dist 0.02 → level 53.9;逼近高 54.0;失敗確認 ≤ 54×0.99=53.46
        _bar(0, 52.0, 52.5, 51.8, 52.2),
        _bar(1, 52.2, 54.0, 52.1, 53.8),  # 逼近(不進場)
        _bar(2, 53.8, 53.5, 53.0, 53.2),  # 收 53.2 ≤ 53.46 → 進場
        _bar(3, 53.2, 53.3, 51.9, 52.0),
    ]
    found = find_cell_b_entry(bars, _LIMIT, 0.02, _CFG)
    assert found is not None
    idx, approach_high = found
    assert idx == 2
    assert abs(approach_high - 54.0) < 1e-9


def test_cell_b_no_approach_no_entry() -> None:
    bars = [
        _bar(0, 52.0, 52.5, 51.8, 52.2),
        _bar(1, 52.2, 53.0, 52.0, 52.5),  # 高 53.0 < 53.9
        _bar(2, 52.5, 52.6, 51.9, 52.0),
    ]
    assert find_cell_b_entry(bars, _LIMIT, 0.02, _CFG) is None


def test_cell_c_triggers_on_rally_then_pullback() -> None:
    bars = [  # 低開 49;反拉 50.6 ≥ 49×1.03=50.47;回落 ≤ 50.6×0.992=50.195
        _bar(0, 49.0, 49.2, 48.8, 49.1),
        _bar(1, 49.1, 50.6, 49.0, 50.5),
        _bar(2, 50.5, 50.5, 50.0, 50.1),  # 收 50.1 ≤ 50.195 → 進場
        _bar(3, 50.1, 50.2, 48.9, 49.0),
    ]
    assert find_cell_c_entry(bars, 0.03, _CFG) == 2


def test_evaluate_filters_to_uc_pool_only() -> None:
    universe = [
        (_sample("uc1", "2026-02-01"), _cell_a_bars()),
        (_sample("x1", "2026-02-01", broker_ids=""), _cell_a_bars()),  # 非 UC → 不進
    ]
    result = evaluate_cells_from_universe(universe, [], _CFG, _WATCH)
    assert result["n_uc_main"] == 1
    cells = result["cells"]
    assert isinstance(cells, dict)
    a_key = "cell_a:inner_0.45"
    base = cells[a_key]["base"]
    assert base["n"] == 1  # 只有 UC 樣本成交


def test_evaluate_variant_count_and_observation_flag() -> None:
    result = evaluate_cells_from_universe([], [], _CFG, _WATCH)
    cells = result["cells"]
    assert isinstance(cells, dict)
    assert len(cells) == 6  # a×2 + b×2 + c×2(pre-registration 預算)
    for key, c in cells.items():
        assert isinstance(c, dict)
        if key.startswith("cell_c"):
            assert c["observation"] is True
            assert c["d5"]["applicable"] is False
        else:
            assert c["observation"] is False
            assert "passed" in c["d5"]
    assert set(result["baselines"].keys()) == {"main", "low"}


def test_d5_pass_and_fail_by_config_thresholds() -> None:
    universe = [
        (_sample("a1", "2026-01-10"), _cell_a_bars()),
        (_sample("a2", "2026-03-10"), _cell_a_bars()),
        (_sample("a3", "2026-03-11"), _cell_a_bars()),
    ]
    loose = FadeBacktestConfig(
        cells_eval_segments=2, d5_min_n=2, d5_min_positive_segments=1, d5_min_ev=0.001
    )
    result = evaluate_cells_from_universe(universe, [], loose, _WATCH)
    d5 = result["cells"]["cell_a:inner_0.45"]["d5"]
    assert d5["passed"] is True

    strict = FadeBacktestConfig(
        cells_eval_segments=2, d5_min_n=99, d5_min_positive_segments=1, d5_min_ev=0.001
    )
    result2 = evaluate_cells_from_universe(universe, [], strict, _WATCH)
    d5b = result2["cells"]["cell_a:inner_0.45"]["d5"]
    assert d5b["passed"] is False
    assert d5b["criteria"]["n_ge_min"] is False


def test_segments_split_by_calendar() -> None:
    universe = [
        (_sample("a1", "2026-01-10"), _cell_a_bars()),  # 前半
        (_sample("a2", "2026-06-10"), _cell_a_bars()),  # 後半
    ]
    cfg = FadeBacktestConfig(cells_eval_segments=2)
    result = evaluate_cells_from_universe(universe, [], cfg, _WATCH)
    base = result["cells"]["cell_a:inner_0.45"]["base"]
    segs = base["segments"]
    assert [s["n"] for s in segs] == [1, 1]  # 等日曆切分,各落一段
