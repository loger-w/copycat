"""T 日進場模擬器(SC-4)— design §3 D6/D7/D9 + §4 全語意.

固定場景:prev_close=100、θ=0.08、limit=110.0、觸發 bar close=108
→ 進場 = 108 + 1 tick(0.5)= 108.5。
"""

from __future__ import annotations

import pytest

from copycat.backtest.config import BacktestConfig
from copycat.backtest.simulate import StopCombo, enumerate_stop_combos, simulate_sample
from copycat.backtest.universe import Sample
from copycat.data.models import Bar1K

CFG = BacktestConfig.default()
INTRADAY_COST = 0.001425 * 2 + 0.0015
OVERNIGHT_COST = 0.001425 * 2 + 0.003
ENTRY = 108.5


def _bar(
    m: int,
    o: float,
    h: float,
    lo: float,
    c: float,
    v: float = 10.0,
    uv: float = 5.0,
    dv: float = 5.0,
) -> Bar1K:
    return Bar1K(
        m=m,
        open=o,
        high=h,
        low=lo,
        close=c,
        volume=v,
        up_volume=uv,
        down_volume=dv,
        unch_volume=0.0,
    )


def _sample(group: str = "ctrl_lock", t1_date: str | None = "2026-03-03") -> Sample:
    return Sample(
        stock_id="1101",
        date="2026-03-02",
        group=group,
        weight=1.0,
        prev_close=100.0,
        limit_price=110.0,
        t1_date=t1_date,
    )


_TRIG = _bar(10, 106.0, 108.2, 104.0, 108.0)  # 觸發 bar(low 104 不得觸發任何停損)


def _combo(**kw: object) -> StopCombo:
    base: dict[str, object] = {
        "s1_n": None,
        "s1_phi": None,
        "s2_m": None,
        "s2_buf": None,
        "s3_x": None,
        "s4_x": None,
        "t1300": False,
    }
    base.update(kw)
    return StopCombo(**base)  # type: ignore[arg-type]


def test_enumerate_stop_combos_count() -> None:
    combos = enumerate_stop_combos(CFG)
    # (S1 16 + S2 6 + S3 4 + S4 4 + S1×S2 96)× t1300 2 = 252,固定順序
    assert len(combos) == 252
    assert combos == enumerate_stop_combos(CFG)


def test_s4_fixed_stop_pessimistic_fill() -> None:
    bars = [_TRIG, _bar(11, 107.0, 107.5, 105.0, 105.1)]
    out = simulate_sample(bars, 0, _sample(), None, _combo(s4_x=0.03), CFG, 1)
    # 停損位 108.5×0.97=105.245;low 105 穿越 → 成交 min(105.245, close 105.1)
    assert out.status == "stopped" and out.exit_m == 11
    assert out.pnl_rate is not None
    assert abs(out.pnl_rate - (105.1 / ENTRY - 1 - INTRADAY_COST)) < 1e-12


def test_gap_through_fills_at_bar_close() -> None:
    bars = [_TRIG, _bar(11, 95.0, 96.0, 90.0, 92.0)]
    out = simulate_sample(bars, 0, _sample(), None, _combo(s4_x=0.03), CFG, 1)
    assert out.status == "stopped"
    assert out.pnl_rate is not None
    assert abs(out.pnl_rate - (92.0 / ENTRY - 1 - INTRADAY_COST)) < 1e-12


def test_stop_not_evaluated_on_trigger_bar() -> None:
    # 觸發 bar low 104 遠低於停損位,但停損自下一根起評估 → 不觸發
    bars = [_TRIG, _bar(11, 108.0, 109.0, 108.0, 108.5)]
    out = simulate_sample(bars, 0, _sample("near_miss", None), None, _combo(s4_x=0.03), CFG, 1)
    assert out.status == "closeout"


def test_s2_swing_low_break() -> None:
    pre = _bar(9, 105.0, 106.0, 105.5, 105.8)
    bars = [pre, _TRIG, _bar(11, 107.0, 107.2, 103.9, 104.0)]
    # M=5:swing low = min(觸發窗尾 M 根 low)=min(105.5,104)=104;buf=0 → 破 104 才停
    out = simulate_sample(bars, 1, _sample(), None, _combo(s2_m=5, s2_buf=0.0), CFG, 1)
    # low 103.9 < 104 → 停損,成交 min(104, close 104.0) = 104.0
    assert out.status == "stopped" and out.pnl_rate is not None
    assert abs(out.pnl_rate - (104.0 / ENTRY - 1 - INTRADAY_COST)) < 1e-12


def test_s1_stall_stop_and_outer_condition() -> None:
    # φ off(-1):N=2 根未創高 → 第 2 根 close 出場
    bars = [
        _TRIG,
        _bar(11, 108.0, 108.0, 107.5, 107.8),
        _bar(12, 107.8, 107.9, 107.0, 107.2),
    ]
    out = simulate_sample(bars, 0, _sample(), None, _combo(s1_n=2, s1_phi=-1.0), CFG, 1)
    assert out.status == "stopped" and out.exit_m == 12
    assert out.pnl_rate is not None
    assert abs(out.pnl_rate - (107.2 / ENTRY - 1 - INTRADAY_COST)) < 1e-12
    # φ=0.55 且外盤比高(買壓仍在)→ 不觸發
    strong = [
        _TRIG,
        _bar(11, 108.0, 108.0, 107.5, 107.8, uv=9.0, dv=1.0),
        _bar(12, 107.8, 107.9, 107.0, 107.2, uv=9.0, dv=1.0),
    ]
    out2 = simulate_sample(
        strong, 0, _sample("near_miss", None), None, _combo(s1_n=2, s1_phi=0.55), CFG, 1
    )
    assert out2.status == "closeout"


def test_s3_trail_stop() -> None:
    bars = [
        _TRIG,
        _bar(11, 109.0, 109.5, 109.0, 109.4),  # run_high → 109.5
        _bar(12, 109.0, 109.4, 106.0, 106.2),  # level = 109.5×0.98 = 107.31,low 穿越
    ]
    out = simulate_sample(bars, 0, _sample(), None, _combo(s3_x=0.02), CFG, 1)
    assert out.status == "stopped" and out.exit_m == 12
    assert out.pnl_rate is not None
    assert abs(out.pnl_rate - (106.2 / ENTRY - 1 - INTRADAY_COST)) < 1e-12


def test_lock_freeze_no_s1_and_hold_e1() -> None:
    # 鎖死 bar(low=limit)期間 S1 不評估、計時不累計;收盤仍鎖 → hold_e1
    locked = [_TRIG] + [_bar(11 + i, 110.0, 110.0, 110.0, 110.0) for i in range(5)]
    out = simulate_sample(locked, 0, _sample(), 112.0, _combo(s1_n=2, s1_phi=-1.0), CFG, 1)
    assert out.status == "hold_e1"
    assert out.pnl_rate is not None
    assert abs(out.pnl_rate - (112.0 / ENTRY - 1 - OVERNIGHT_COST)) < 1e-12


def test_lock_freeze_then_reopen_resumes_stops() -> None:
    # 鎖 3 根 → 打開後未創高 2 根 → S1 於打開後第 2 根觸發(鎖死根不累計)
    bars = (
        [_TRIG]
        + [_bar(11 + i, 110.0, 110.0, 110.0, 110.0) for i in range(3)]
        + [_bar(14, 109.5, 109.5, 108.8, 109.0), _bar(15, 109.0, 109.2, 108.5, 108.6)]
    )
    out = simulate_sample(bars, 0, _sample(), None, _combo(s1_n=2, s1_phi=-1.0), CFG, 1)
    assert out.status == "stopped" and out.exit_m == 15


def test_outer_window_excludes_locked_bars() -> None:
    # 鎖死根外盤比極高;解鎖後兩根外盤比 0 → 窗若含鎖死根就不會 < φ
    bars = (
        [_TRIG]
        + [_bar(11 + i, 110.0, 110.0, 110.0, 110.0, uv=100.0, dv=0.0) for i in range(3)]
        + [
            _bar(14, 109.5, 109.5, 108.8, 109.0, uv=0.0, dv=10.0),
            _bar(15, 109.0, 109.2, 108.5, 108.6, uv=0.0, dv=10.0),
        ]
    )
    out = simulate_sample(bars, 0, _sample(), None, _combo(s1_n=2, s1_phi=0.55), CFG, 1)
    assert out.status == "stopped" and out.exit_m == 15


def test_same_bar_stop_beats_hold() -> None:
    # 末 bar low 破停損、close 收回貼 limit → 悲觀:停損出場,不進 E1
    bars = [_TRIG, _bar(11, 109.0, 110.0, 104.0, 110.0)]
    out = simulate_sample(bars, 0, _sample(), 112.0, _combo(s4_x=0.03), CFG, 1)
    assert out.status == "stopped"


def test_t1300_exit_sparse_and_afternoon() -> None:
    sample = _sample("near_miss", None)
    # sparse:13:00(239)缺 bar → 第一根 m≥239(=245)close 出場
    bars = [_TRIG, _bar(200, 108.0, 109.0, 107.9, 108.8), _bar(245, 108.5, 108.6, 108.0, 108.2)]
    out = simulate_sample(bars, 0, sample, None, _combo(t1300=True), CFG, 1)
    assert out.status == "time_1300" and out.exit_m == 245
    assert out.pnl_rate is not None
    assert abs(out.pnl_rate - (108.2 / ENTRY - 1 - INTRADAY_COST)) < 1e-12
    # 午後觸發:on 臂 → 不進場;off 臂 → 收盤全出
    pm_trig = _bar(240, 106.0, 108.2, 105.9, 108.0)
    pm_bars = [pm_trig, _bar(250, 108.0, 108.5, 107.8, 108.0)]
    on = simulate_sample(pm_bars, 0, sample, None, _combo(t1300=True), CFG, 1)
    assert on.status == "excluded_afternoon"
    off = simulate_sample(pm_bars, 0, sample, None, _combo(t1300=False), CFG, 1)
    assert off.status == "closeout"
    assert off.pnl_rate is not None
    assert abs(off.pnl_rate - (108.0 / ENTRY - 1 - INTRADAY_COST)) < 1e-12


def test_t1300_locked_checkpoint_passes() -> None:
    # 13:00 檢查點時鎖死 → 不出場;收盤仍鎖 → hold_e1
    bars = [_TRIG] + [_bar(239 + i, 110.0, 110.0, 110.0, 110.0) for i in range(3)]
    out = simulate_sample(bars, 0, _sample(), 112.0, _combo(t1300=True), CFG, 1)
    assert out.status == "hold_e1"


def test_unfillable_and_lastbar() -> None:
    # 觸發 bar close 已在 limit → entry cap = limit;其後無更低成交 → unfillable
    trig_at_limit = _bar(10, 109.0, 110.0, 108.9, 110.0)
    bars = [trig_at_limit, _bar(11, 110.0, 110.0, 110.0, 110.0)]
    out = simulate_sample(bars, 0, _sample(), 112.0, _combo(), CFG, 1)
    assert out.status == "excluded_unfillable"
    # 末 bar 觸發 → 剔除
    out2 = simulate_sample([_TRIG], 0, _sample(), None, _combo(), CFG, 1)
    assert out2.status == "excluded_lastbar"


def test_lock_conflict_and_t1_missing() -> None:
    # ctrl_lock 但收盤沒鎖 → 矛盾剔除
    bars = [_TRIG, _bar(11, 108.0, 108.5, 107.0, 107.5)]
    out = simulate_sample(bars, 0, _sample("ctrl_lock"), None, _combo(), CFG, 1)
    assert out.status == "excluded_lock_conflict"
    # 鎖住留倉但 t1_open 缺 → 剔除
    locked = [_TRIG, _bar(11, 110.0, 110.0, 110.0, 110.0)]
    out2 = simulate_sample(locked, 0, _sample(), None, _combo(), CFG, 1)
    assert out2.status == "excluded_t1_missing"


def test_near_miss_closeout_and_slippage_stress() -> None:
    bars = [_TRIG, _bar(11, 108.0, 108.5, 107.5, 108.0)]
    base = simulate_sample(bars, 0, _sample("near_miss", None), None, _combo(), CFG, 1)
    stress = simulate_sample(bars, 0, _sample("near_miss", None), None, _combo(), CFG, 2)
    assert base.status == "closeout" and stress.status == "closeout"
    assert base.pnl_rate is not None and stress.pnl_rate is not None
    assert stress.pnl_rate < base.pnl_rate  # +2 tick 進場更貴
    assert abs(base.pnl_rate - (108.0 / 108.5 - 1 - INTRADAY_COST)) < 1e-12
    assert abs(stress.pnl_rate - (108.0 / 109.0 - 1 - INTRADAY_COST)) < 1e-12


def test_data_break_after_trigger_excluded() -> None:
    with pytest.raises(ValueError):
        simulate_sample([], 0, _sample(), None, _combo(), CFG, 1)
