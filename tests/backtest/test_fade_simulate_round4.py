"""round 4 模擬器:inner_flip 停損 / TP 決策樹(flush+hl)/ mfe_rate+entry_price
(change-spec §5.3;新參數/欄位預設 = round 3 行為 bit-for-bit)."""

from __future__ import annotations

import dataclasses

import pytest

from copycat.backtest.fade_config import FadeBacktestConfig, FadeStopCombo
from copycat.backtest.fade_simulate import FadeSample, simulate_fade_sample
from copycat.data.models import Bar1K
from copycat.market import tick_size

_SAMPLE = FadeSample(
    stock_id="2330",
    date="2026-01-05",
    t1_date="2026-01-06",
    limit=50.0,  # t1_limit = 55.0
    t1_open=52.0,
    gap=0.04,
    broker_ids="",
)

_NONE_COMBO = FadeStopCombo(
    s1_n=None, s1_phi=None, s2_m=None, s2_buf=None, s3_x=None, s4_x=None, s5_x=None, t1300=False
)

_COST = 0.001425 * 2 + 0.0015


def _bar(
    m: int,
    o: float,
    h: float,
    lo: float,
    c: float,
    vol: float = 100,
    up: float = 50,
    dn: float = 50,
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
        unch_volume=0,
    )


def _flat_bars(m_from: int, m_to: int, up: float = 30, dn: float = 70) -> list[Bar1K]:
    return [_bar(m, 52.0, 52.1, 51.9, 52.0, up=up, dn=dn) for m in range(m_from, m_to + 1)]


# --- inner_flip 停損 ---


class TestInnerFlip:
    def test_triggers_when_ratio_flips_below_phi(self) -> None:
        cfg = FadeBacktestConfig()
        # trig(m0)up/dn=50/50;m1-14 賣壓在(dn 70%);m15 大買盤翻轉
        bars = [_bar(0, 52.0, 52.2, 51.8, 52.0)]
        bars += _flat_bars(1, 14)
        bars.append(_bar(15, 52.0, 52.1, 51.9, 52.0, vol=2000, up=2000, dn=0))
        bars.append(_bar(16, 52.0, 52.1, 51.5, 51.6))
        r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1, inner_flip_phi=0.45)
        assert r.status == "guard_exit"
        assert r.exit_reason == "inner_flip"
        assert r.exit_m == 15
        entry = 52.0 - tick_size(52.0)
        assert r.pnl_rate is not None
        assert abs(r.pnl_rate - (1.0 - 52.0 / entry - _COST)) < 1e-9

    def test_min_bars_gate_blocks_early_flip(self) -> None:
        cfg = FadeBacktestConfig()  # inner_flip_min_bars=15
        bars = [_bar(0, 52.0, 52.2, 51.8, 52.0)]
        bars += _flat_bars(1, 9)
        bars.append(_bar(10, 52.0, 52.1, 51.9, 52.0, vol=2000, up=2000, dn=0))
        bars.append(_bar(11, 52.0, 52.1, 51.5, 51.6))
        r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1, inner_flip_phi=0.45)
        assert r.status == "closeout"

    def test_no_trigger_when_sell_pressure_holds(self) -> None:
        cfg = FadeBacktestConfig()
        bars = [_bar(0, 52.0, 52.2, 51.8, 52.0)]
        bars += _flat_bars(1, 20)  # dn 70% 全程 → 比例 ~0.7 > 0.45
        r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1, inner_flip_phi=0.45)
        assert r.status == "closeout"

    def test_phi_none_equals_legacy(self) -> None:
        cfg = FadeBacktestConfig()
        bars = [_bar(0, 52.0, 52.2, 51.8, 52.0)]
        bars += _flat_bars(1, 14)
        bars.append(_bar(15, 52.0, 52.1, 51.9, 52.0, vol=2000, up=2000, dn=0))
        bars.append(_bar(16, 52.0, 52.1, 51.5, 51.6))
        legacy = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1)
        explicit = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1, inner_flip_phi=None)
        assert legacy == explicit
        assert legacy.status == "closeout"

    def test_fill_not_stressed(self) -> None:
        base = FadeBacktestConfig()
        stress = FadeBacktestConfig(stress_guard_fill_high=True)
        bars = [_bar(0, 52.0, 52.2, 51.8, 52.0)]
        bars += _flat_bars(1, 14)
        # 觸發 bar 帶長上影(high 53.0):stress 下 inner_flip 成交仍 = close
        bars.append(_bar(15, 52.0, 53.0, 51.9, 52.0, vol=2000, up=2000, dn=0))
        bars.append(_bar(16, 52.0, 52.1, 51.5, 51.6))
        r_base = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, base, 1, inner_flip_phi=0.45)
        r_stress = simulate_fade_sample(
            bars, 0, _SAMPLE, _NONE_COMBO, stress, 1, inner_flip_phi=0.45
        )
        assert r_base.pnl_rate == r_stress.pnl_rate

    def test_hardline_wins_same_bar(self) -> None:
        cfg = FadeBacktestConfig(guard_limit_dist=0.01)  # 硬線 = 54.45
        bars = [_bar(0, 52.0, 52.2, 51.8, 52.0)]
        bars += _flat_bars(1, 14)
        bars.append(_bar(15, 52.0, 54.6, 51.9, 52.0, vol=2000, up=2000, dn=0))
        bars.append(_bar(16, 52.0, 52.1, 51.5, 51.6))
        r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1, inner_flip_phi=0.45)
        assert r.status == "guard_exit"
        assert r.exit_reason == "hardline"  # worst = 54.45 > close 52.0


# --- TP 決策樹:出量殺 ---

_FLUSH_CFG = FadeBacktestConfig(
    tp_flush_z=3.0, tp_flush_lookback=3, tp_flush_recovery=0.5, tp_flush_min_profit=0.005
)


class TestTpFlushInCore:
    def _bars(self) -> list[Bar1K]:
        return [
            _bar(0, 52.0, 52.2, 51.8, 52.0),
            _bar(1, 52.0, 52.1, 51.7, 51.9),
            _bar(2, 51.9, 52.0, 51.6, 51.8),
            _bar(3, 51.8, 51.9, 51.5, 51.7),
            # 量爆 5x + 進場後新低 50.0 + 收回 (51.0-50.0)/(51.5-50.0)=0.667
            _bar(4, 51.7, 51.5, 50.0, 51.0, vol=500),
            _bar(5, 51.0, 51.2, 50.8, 51.1),
        ]

    def test_flush_exit(self) -> None:
        r = simulate_fade_sample(self._bars(), 0, _SAMPLE, _NONE_COMBO, _FLUSH_CFG, 1)
        assert r.status == "target_hit"
        assert r.exit_reason == "tp_flush"
        assert r.exit_m == 4
        entry = 52.0 - tick_size(52.0)
        assert r.pnl_rate is not None
        assert abs(r.pnl_rate - (1.0 - 51.0 / entry - _COST)) < 1e-9

    def test_tp_off_equals_legacy(self) -> None:
        r_off = simulate_fade_sample(self._bars(), 0, _SAMPLE, _NONE_COMBO, FadeBacktestConfig(), 1)
        assert r_off.status == "closeout"
        assert r_off.exit_reason is None

    def test_stop_beats_tp_same_bar(self) -> None:
        cfg = dataclasses.replace(_FLUSH_CFG, guard_limit_dist=0.01)
        bars = self._bars()
        # flush bar 同時衝破硬線 54.45 → worst = 硬線,歸因 hardline
        bars[4] = _bar(4, 51.7, 54.6, 50.0, 51.0, vol=500)
        r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1)
        assert r.status == "guard_exit"
        assert r.exit_reason == "hardline"


# --- TP 決策樹:墊高竭盡(含凍結 bar 參與 pivot)---

_HL_CFG = FadeBacktestConfig(tp_hl_k=1, tp_hl_min_profit=0.005)


def _hl_bars(locked_mid: bool) -> list[Bar1K]:
    """墊高結構:凍結 bar(m7)是 L2 pivot low 的唯一右確認鄰;
    沒餵它的話 m8 低點(50.4)會讓 L2 永不確認 → 不觸發."""
    bars = [
        _bar(0, 52.0, 52.2, 51.8, 52.0),
        _bar(1, 51.9, 52.6, 51.5, 51.7),
        _bar(2, 51.7, 51.9, 50.8, 51.0),
        _bar(3, 51.0, 51.2, 50.5, 50.9),  # L1 候選 50.5
        _bar(4, 50.9, 51.1, 50.7, 50.9),  # 確認 L1=50.5(m4 更新時)
        _bar(5, 50.9, 53.2, 50.8, 53.0),  # H1 候選 53.2
        _bar(6, 53.0, 53.1, 50.6, 50.8),  # 確認 H1=53.2;L2 候選 50.6
    ]
    if locked_mid:
        # 鎖死凍結 bar:是 L2 的唯一右確認鄰(50.6 < 55.0),其 high 55.1 之後
        # 在 m8 更新時成為 H2
        bars.append(_bar(7, 55.0, 55.1, 55.0, 55.0))
    else:
        # 對照:一般 bar 右確認 L2(50.6 < 50.9),其 high 53.4 在 m8 更新時成為 H2
        bars.append(_bar(7, 51.0, 53.4, 50.9, 51.2))
    bars.append(_bar(8, 52.0, 52.2, 50.4, 51.0))  # 觸發檢查點(50.4 破 L2 候選)
    bars.append(_bar(9, 51.0, 51.1, 50.8, 50.9))
    return bars


class TestTpHigherLowInCore:
    def test_hl_exit_with_locked_bar_feeding_pivots(self) -> None:
        r = simulate_fade_sample(_hl_bars(locked_mid=True), 0, _SAMPLE, _NONE_COMBO, _HL_CFG, 1)
        assert r.status == "target_hit"
        assert r.exit_reason == "tp_hl"
        assert r.exit_m == 8
        assert r.lock_flag is True  # 中途碰過鎖死

    def test_hl_exit_normal_path(self) -> None:
        r = simulate_fade_sample(_hl_bars(locked_mid=False), 0, _SAMPLE, _NONE_COMBO, _HL_CFG, 1)
        assert r.status == "target_hit"
        assert r.exit_reason == "tp_hl"
        assert r.exit_m == 8

    def test_flush_beats_hl_same_bar(self) -> None:
        cfg = dataclasses.replace(
            _HL_CFG,
            tp_flush_z=3.0,
            tp_flush_lookback=3,
            tp_flush_recovery=0.5,
            tp_flush_min_profit=0.005,
        )
        bars = _hl_bars(locked_mid=False)
        # m8 同時滿足 flush(量爆 + 新低 50.4 + 收回 (51.4-50.4)/(52.2-50.4)=0.556)
        bars[8] = _bar(8, 52.0, 52.2, 50.4, 51.4, vol=500)
        r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1)
        assert r.status == "target_hit"
        assert r.exit_reason == "tp_flush"


# --- mfe_rate / entry_price ---


class TestMfeAndEntry:
    def test_closeout_sets_mfe_and_entry(self) -> None:
        cfg = FadeBacktestConfig()
        bars = [
            _bar(0, 52.0, 52.2, 51.8, 52.0),
            _bar(1, 52.0, 52.1, 50.5, 51.0),
            _bar(2, 51.0, 51.5, 50.9, 51.2),
        ]
        r = simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1)
        entry = 52.0 - tick_size(52.0)
        assert r.entry_price == entry
        assert r.mfe_rate is not None
        assert abs(r.mfe_rate - (1.0 - 50.5 / entry)) < 1e-9  # 毛,不扣成本

    def test_excluded_has_none_fields(self) -> None:
        cfg = FadeBacktestConfig()
        bars = [
            _bar(239, 52.0, 52.2, 51.8, 52.0),
            _bar(240, 52.0, 52.1, 51.9, 52.0),
        ]
        combo = dataclasses.replace(_NONE_COMBO, t1300=True)
        r = simulate_fade_sample(bars, 0, _SAMPLE, combo, cfg, 1)
        assert r.status == "excluded_afternoon"
        assert r.mfe_rate is None
        assert r.entry_price is None


# --- config 不變式(replace 繞過 load 驗證)---


def test_partial_tp_flush_fields_rejected_by_engine() -> None:
    cfg = dataclasses.replace(FadeBacktestConfig(), tp_flush_z=3.0)
    bars = [_bar(0, 52.0, 52.2, 51.8, 52.0), _bar(1, 52.0, 52.1, 51.9, 52.0)]
    with pytest.raises(ValueError, match="同設"):
        simulate_fade_sample(bars, 0, _SAMPLE, _NONE_COMBO, cfg, 1)
