"""劇本格子:三 cell 觸發邊界 / UC 池過濾 / 基準線 / 四等分 / D5(SC-4)."""

from __future__ import annotations

import logging

import pytest

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


def _dig(obj: object, *keys: str) -> dict[str, object]:
    for k in keys:
        assert isinstance(obj, dict)
        obj = obj[k]
    assert isinstance(obj, dict)
    return obj


def _cell_a_bars() -> list[Bar1K]:
    """拉高(53.5 ≥ 52×1.01)→ 回落(52.8 ≤ 53.5×0.992)、headroom 4.2%、內盤比 0.7."""
    return [
        _bar(0, 52.0, 52.2, 51.8, 52.1),
        _bar(1, 52.1, 53.5, 52.0, 53.4),
        _bar(2, 53.4, 53.4, 52.7, 52.8),
        _bar(3, 52.8, 52.9, 50.9, 51.0),
    ]


def test_cell_a_triggers_on_pullback_with_inner_gate() -> None:
    found = find_cell_a_entry(_cell_a_bars(), _LIMIT, 0.45, _CFG)
    assert found is not None
    idx, struct_high = found
    assert idx == 2
    assert abs(struct_high - 53.5) < 1e-9  # 進場前盤中高點(round 3 結構高)


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
    found = find_cell_c_entry(bars, 0.03, _CFG)
    assert found is not None
    idx, struct_high = found
    assert idx == 2
    assert abs(struct_high - 50.6) < 1e-9  # 反拉高點(round 3 結構高)


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
    baselines = result["baselines"]
    assert isinstance(baselines, dict)
    assert set(baselines.keys()) == {"main", "low"}


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
    d5 = _dig(result, "cells", "cell_a:inner_0.45", "d5")
    assert d5["passed"] is True

    strict = FadeBacktestConfig(
        cells_eval_segments=2, d5_min_n=99, d5_min_positive_segments=1, d5_min_ev=0.001
    )
    result2 = evaluate_cells_from_universe(universe, [], strict, _WATCH)
    d5b = _dig(result2, "cells", "cell_a:inner_0.45", "d5")
    assert d5b["passed"] is False
    crit = d5b["criteria"]
    assert isinstance(crit, dict)
    assert crit["n_ge_min"] is False


def _round5_cfg(**overrides: object) -> FadeBacktestConfig:
    base: dict[str, object] = {
        "struct_stop_buffers": (0.025,),
        "guard_limit_dist": 0.01,
        "disaster_arm_x": 0.06,
        "disaster_retrace_r": 0.02,
        "vote_s_grid": (5, 4),
        "vote_m_min_grid": (0, 14),
        "vote_flow_confirm_grid": (1, 2),
        "vote_flow_n": 5,
        "vote_flow_rho": 1.5,
        "vote_flow_seg_gain": 0.01,
        "vote_inner_lo": 0.45,
        "vote_inner_hi": 0.55,
        "vote_level_eps": 0.005,
        "inner15_arm": True,
        "inner15_phi": 0.55,
        "base_arm": True,
        "cells_eval_segments": 2,
    }
    base.update(overrides)
    return FadeBacktestConfig(**base)  # type: ignore[arg-type]


def _round5_bars() -> list[Bar1K]:
    """內盤比 0.7(2)+ 無攻擊段(1)+ 高點觸線 52.2(2)= 5;inner15 gate 亦過."""
    return [_bar(m, 52.0, 52.2, 51.8, 51.9, up=30, dn=70) for m in range(30)]


def test_round5_vote_path_structure() -> None:
    cfg = _round5_cfg()
    universe = [
        (_sample("uc1", "2026-02-01"), _round5_bars()),
        (_sample("uc2", "2026-05-01"), _round5_bars()),
        (_sample("x1", "2026-02-01", broker_ids=""), _round5_bars()),  # 非 UC
    ]
    levels = {("uc1", "2026-01-01"): (52.2,), ("uc2", "2026-01-01"): (52.2,)}
    result = evaluate_cells_from_universe(universe, [], cfg, _WATCH, levels_map=levels)
    assert result["round5"] is True
    assert result["n_uc_main"] == 2
    arms = result["arms"]
    assert isinstance(arms, dict)
    vote = arms["vote_S5:m0:c1"]
    assert isinstance(vote, dict)
    base = _dig(vote, "in_window", "base")
    assert base["n"] == 2  # 兩筆 UC 全數進場(總分 5)
    assert "cluster_z" in vote
    inner15 = arms["inner15"]
    assert isinstance(inner15, dict)
    assert _dig(inner15, "in_window", "base")["n"] == 2
    budget = result["sample_budget"]
    assert isinstance(budget, dict)
    assert budget["S5"] == 2
    assert budget["S6"] == 0  # flow 中性 1 分,湊不到 6
    assert budget["inner15"] == 2
    abl = result["ablation"]
    assert isinstance(abl, dict)
    assert set(abl) == {"inner_only", "flow_only", "level_only"}
    sens = result["sensitivity"]
    assert isinstance(sens, dict)
    assert {"S4", "c2", "m14", "disaster_off"} <= set(sens)


def test_round5_no_levels_blocks_s5() -> None:
    # 無位階線(level=1)→ 總分 4 < S=5 → 主臂 0 筆;S4 敏感度有成交
    cfg = _round5_cfg()
    universe = [(_sample("uc1", "2026-02-01"), _round5_bars())]
    result = evaluate_cells_from_universe(universe, [], cfg, _WATCH, levels_map={})
    arms = result["arms"]
    assert isinstance(arms, dict)
    assert _dig(arms["vote_S5:m0:c1"], "in_window", "base")["n"] == 0
    sens = result["sensitivity"]
    assert isinstance(sens, dict)
    assert _dig(sens["S4"], "in_window", "base")["n"] == 1


def test_round5_empty_levels_map_warns(caplog: pytest.LogCaptureFixture) -> None:
    # 直呼忘傳 levels_map → 位階票全釘中性 1 分,必須有警告(run_cells 會自建故不受影響)
    cfg = _round5_cfg()
    universe = [(_sample("uc1", "2026-02-01"), _round5_bars())]
    with caplog.at_level(logging.WARNING, logger="copycat.backtest.fade_cells"):
        evaluate_cells_from_universe(universe, [], cfg, _WATCH, levels_map={})
    assert any("levels_map" in m for m in caplog.messages)


def test_round5_populated_levels_map_no_warning(caplog: pytest.LogCaptureFixture) -> None:
    cfg = _round5_cfg()
    universe = [(_sample("uc1", "2026-02-01"), _round5_bars())]
    levels = {("uc1", "2026-01-01"): (52.2,)}
    with caplog.at_level(logging.WARNING, logger="copycat.backtest.fade_cells"):
        evaluate_cells_from_universe(universe, [], cfg, _WATCH, levels_map=levels)
    assert not any("levels_map" in m for m in caplog.messages)


def test_round5_validate_fail_fast() -> None:
    # 收尾 review:缺量尺 b / round4 欄位同設,必須在 config 層就擋(不等宇宙載入)
    from copycat.backtest.fade_config import validate_round5_fields

    try:
        validate_round5_fields(_round5_cfg(struct_stop_buffers=()))
    except ValueError as e:
        assert "struct_stop_buffers" in str(e)
    else:
        raise AssertionError("缺 struct_stop_buffers 應在 validate 層 raise")
    try:
        validate_round5_fields(_round5_cfg(inner_flip_phi_grid=(0.45,)))
    except ValueError as e:
        assert "不得同時啟用" in str(e)
    else:
        raise AssertionError("round 4/5 欄位同設應在 validate 層 raise")


def test_round5_and_round4_fields_mutually_exclusive() -> None:
    cfg = _round5_cfg(inner_flip_phi_grid=(0.45,))
    try:
        evaluate_cells_from_universe([], [], cfg, _WATCH, levels_map={})
    except ValueError as e:
        assert "不得同時啟用" in str(e)
    else:
        raise AssertionError("round 4/5 欄位同設應 raise")


def test_segments_split_by_calendar() -> None:
    universe = [
        (_sample("a1", "2026-01-10"), _cell_a_bars()),  # 前半
        (_sample("a2", "2026-06-10"), _cell_a_bars()),  # 後半
    ]
    cfg = FadeBacktestConfig(cells_eval_segments=2)
    result = evaluate_cells_from_universe(universe, [], cfg, _WATCH)
    base = _dig(result, "cells", "cell_a:inner_0.45", "base")
    segs = base["segments"]
    assert isinstance(segs, list)
    assert [s["n"] for s in segs] == [1, 1]  # 等日曆切分,各落一段
