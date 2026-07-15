"""round 3 cells:gate / b 變體 / b_capped / 底倉臂格 / Q2 / 精算表 / forward 切分
(change-spec §9.3)."""

from __future__ import annotations

from copycat.backtest.fade_cells import evaluate_cells_from_universe
from copycat.backtest.fade_config import FadeBacktestConfig
from copycat.backtest.fade_simulate import FadeSample
from copycat.data.models import Bar1K

_WATCH = frozenset({"9227", "9600"})


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


def _sample(
    sid: str,
    t1: str,
    broker_ids: str = "9227",
    gap: float = 0.04,
) -> FadeSample:
    return FadeSample(
        stock_id=sid,
        date="2026-01-01",
        t1_date=t1,
        limit=50.0,  # t1_limit = 55.0
        t1_open=52.0,
        gap=gap,
        broker_ids=broker_ids,
        source="scan",
    )


def _cell_a_bars() -> list[Bar1K]:
    """拉高 53.5 → 回落 52.8(cell_a 觸發於 idx 2,結構高 53.5)→ 收低."""
    return [
        _bar(0, 52.0, 52.2, 51.8, 52.1),
        _bar(1, 52.1, 53.5, 52.0, 53.4),
        _bar(2, 53.4, 53.4, 52.7, 52.8),
        _bar(3, 52.8, 52.9, 50.9, 51.0),
        _bar(4, 51.0, 51.1, 50.5, 50.6),
    ]


_R3_CFG = FadeBacktestConfig(
    guard_limit_dist=0.01,
    disaster_arm_x=0.06,
    disaster_retrace_r=0.02,
    lock_penalty=0.03,
    struct_stop_buffers=(0.025, 0.0375),
    cell_a_inner_thresholds=(0.45,),
    cell_b_approach_dists=(0.03,),
    cell_c_rally_pcts=(0.03, 0.05),
    base_arm=True,
    forward_start="2026-07-11",
)


def _r3_result(
    main: list[tuple[FadeSample, list[Bar1K]]] | None = None,
    low: list[tuple[FadeSample, list[Bar1K]]] | None = None,
    cellb: list[tuple[FadeSample, list[Bar1K]]] | None = None,
    cfg: FadeBacktestConfig = _R3_CFG,
) -> dict[str, object]:
    return evaluate_cells_from_universe(main or [], low or [], cfg, _WATCH, cellb_universe=cellb)


def _dig(obj: object, *keys: str) -> dict[str, object]:
    for k in keys:
        assert isinstance(obj, dict)
        obj = obj[k]
    assert isinstance(obj, dict)
    return obj


def test_gate_off_keeps_round2_shape() -> None:
    cfg = FadeBacktestConfig()  # struct_stop_buffers=() → round 2 形狀
    universe = [(_sample("uc1", "2026-02-01"), _cell_a_bars())]
    result = evaluate_cells_from_universe(universe, [], cfg, _WATCH)
    cells = result["cells"]
    assert isinstance(cells, dict)
    assert "cell_a:inner_0.45" in cells  # 舊 key,無 b 後綴
    assert result.get("round3") is not True


def test_round3_variant_keys_and_budget() -> None:
    result = _r3_result(main=[(_sample("uc1", "2026-02-01"), _cell_a_bars())])
    cells = result["cells"]
    assert isinstance(cells, dict)
    # a×1 + b×1 + c×2 = 4,× b×2 = 8(SC-6 自由度預算)
    assert len(cells) == 8
    assert "cell_a:inner_0.45:b0.025" in cells
    assert "cell_b:dist_0.03:b0.0375" in cells
    assert "cell_c:rally_0.05:b0.025" in cells
    # cell_c 升正式(round 3)
    c = _dig(result, "cells", "cell_c:rally_0.05:b0.025")
    assert c["observation"] is False


def test_round3_cell_a_uses_struct_stop_from_context_high() -> None:
    # 結構高 53.5×1.025=54.8375 < guard 54.45?否:guard = 55×0.99 = 54.45 → capped!
    # 53.5×1.025 = 54.8375 ≥ 54.45 → b0.025 對此事件 capped(fixed_stop=None)
    result = _r3_result(main=[(_sample("uc1", "2026-02-01"), _cell_a_bars())])
    cell = _dig(result, "cells", "cell_a:inner_0.45:b0.025", "in_window")
    assert cell["b_capped"] == 1


def test_round3_forward_split() -> None:
    main = [
        (_sample("uc1", "2026-02-01"), _cell_a_bars()),
        (_sample("uc2", "2026-07-13"), _cell_a_bars()),  # forward
    ]
    result = _r3_result(main=main)
    cell = _dig(result, "cells", "cell_a:inner_0.45:b0.025")
    in_w = _dig(cell, "in_window", "base")
    fwd = _dig(cell, "forward", "base")
    assert in_w["n"] == 1
    assert fwd["n"] == 1


def test_base_arm_grid_assignment_by_hits_and_gap() -> None:
    main = [
        (_sample("uc1", "2026-02-01", broker_ids="9227", gap=0.02), _cell_a_bars()),
        (_sample("uc2", "2026-02-02", broker_ids="9227|9600", gap=0.04), _cell_a_bars()),
        (_sample("uc3", "2026-02-03", broker_ids="9227", gap=0.06), _cell_a_bars()),
    ]
    result = _r3_result(main=main)
    grid = _dig(result, "base_arm", "b0.025", "grid")
    assert _dig(grid, "1:gap_0.01_0.03")["n"] == 1
    assert _dig(grid, "2plus:gap_0.03_0.055")["n"] == 1
    assert _dig(grid, "1:gap_0.055_0.075")["n"] == 1


def test_base_arm_q2_primary_on_b1_only() -> None:
    main = [(_sample("uc1", "2026-02-01"), _cell_a_bars())]
    result = _r3_result(main=main)
    q2_b1 = _dig(result, "base_arm", "b0.025", "q2")
    q2_b2 = _dig(result, "base_arm", "b0.0375", "q2")
    assert q2_b1["primary"] is True
    assert q2_b2["primary"] is False
    assert "z" in q2_b1 and "p" in q2_b1 and "pass" in q2_b1


def test_actuarial_table_attribution() -> None:
    # cell_a 事件:b0.025 capped → 硬線 guard 生效;bar3 高 52.9 < 54.45 → 不觸發
    # → closeout(無強制出場)→ 精算表 exit_reason 全 0
    result = _r3_result(main=[(_sample("uc1", "2026-02-01"), _cell_a_bars())])
    act = _dig(result, "cells", "cell_a:inner_0.45:b0.025", "in_window", "actuarial")
    assert isinstance(act, dict)
    total_forced = sum(
        v["n"] for v in act.values() if isinstance(v, dict) and isinstance(v.get("n"), int)
    )
    assert total_forced == 0


def test_cellb_universe_separate() -> None:
    # cell_b 宇宙獨立傳入:main 空、cellb 有觸發事件 → cell_b 仍有樣本
    bars = [  # dist 0.03 → level 53.35;衝 54.0 → bar2 高 53.3 < 53.35 且收 53.2 ≤ 53.46 → 進場 idx 2
        _bar(0, 52.0, 52.5, 51.8, 52.2),
        _bar(1, 52.2, 54.0, 52.1, 53.8),
        _bar(2, 53.3, 53.3, 53.0, 53.2),
        _bar(3, 53.2, 53.3, 51.9, 52.0),
    ]
    result = _r3_result(main=[], cellb=[(_sample("uc1", "2026-02-01", gap=0.08), bars)])
    cell = _dig(result, "cells", "cell_b:dist_0.03:b0.025", "in_window", "base")
    assert cell["n"] == 1


def test_round3_report_sections(tmp_path) -> None:
    from pathlib import Path

    from copycat.backtest.fade_cells import write_cells_report

    result = _r3_result(main=[(_sample("uc1", "2026-02-01"), _cell_a_bars())])
    path = Path(tmp_path) / "r3.md"
    write_cells_report(result, _R3_CFG, "2026-07-15", path)
    text = path.read_text(encoding="utf-8")
    assert "Q2" in text
    assert "精算" in text
    assert "forward 樣本 0,僅候選" in text  # fixture 無 forward 樣本
    assert "b_capped" in text or "封頂" in text


def test_round2_path_ignores_cellb_universe_param() -> None:
    cfg = FadeBacktestConfig()
    universe = [(_sample("uc1", "2026-02-01"), _cell_a_bars())]
    r_no = evaluate_cells_from_universe(universe, [], cfg, _WATCH)
    r_with = evaluate_cells_from_universe(universe, [], cfg, _WATCH, cellb_universe=universe)
    assert r_no == r_with
