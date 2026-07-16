"""round 4 cfg 驅動停利:check_flush_exit / PivotState / check_higher_low_exit(change-spec §5.2)."""

from __future__ import annotations

from copycat.backtest.fade_config import FadeBacktestConfig
from copycat.backtest.fade_tp import PivotState, check_flush_exit, check_higher_low_exit
from copycat.data.models import Bar1K


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


_FLUSH_CFG = FadeBacktestConfig(
    tp_flush_z=3.0, tp_flush_lookback=3, tp_flush_recovery=0.5, tp_flush_min_profit=0.005
)


class TestFlushExit:
    def _post_bars(self) -> list[Bar1K]:
        return [
            _bar(1, 52.0, 52.2, 51.8, 52.0, vol=100),
            _bar(2, 52.0, 52.1, 51.6, 51.8, vol=100),
            _bar(3, 51.8, 51.9, 51.5, 51.6, vol=100),
        ]

    def test_triggers_on_volume_spike_new_low_with_recovery(self) -> None:
        post = self._post_bars()
        # 量爆 5 倍 + 創新低 51.0 + 長下影收回 60%((51.6-51.0)/(52.0-51.0)=0.6)
        flush = _bar(4, 51.6, 52.0, 51.0, 51.6, vol=500)
        post.append(flush)
        fill = check_flush_exit(_FLUSH_CFG, flush, 51.0, post, profit=0.02)
        assert fill == flush.close

    def test_no_trigger_without_volume_spike(self) -> None:
        post = self._post_bars()
        flush = _bar(4, 51.6, 52.0, 51.0, 51.6, vol=150)
        post.append(flush)
        assert check_flush_exit(_FLUSH_CFG, flush, 51.0, post, profit=0.02) is None

    def test_no_trigger_when_not_new_low(self) -> None:
        post = self._post_bars()
        flush = _bar(4, 51.6, 52.0, 51.55, 51.8, vol=500)
        post.append(flush)
        # 進場後最低 51.4 未被觸及
        assert check_flush_exit(_FLUSH_CFG, flush, 51.4, post, profit=0.02) is None

    def test_min_profit_gate(self) -> None:
        post = self._post_bars()
        flush = _bar(4, 51.6, 52.0, 51.0, 51.6, vol=500)
        post.append(flush)
        assert check_flush_exit(_FLUSH_CFG, flush, 51.0, post, profit=0.001) is None

    def test_recovery_gate(self) -> None:
        post = self._post_bars()
        # 收在低點附近(收回 10%)= 還在殺,不是殺完
        flush = _bar(4, 51.6, 52.0, 51.0, 51.1, vol=500)
        post.append(flush)
        assert check_flush_exit(_FLUSH_CFG, flush, 51.0, post, profit=0.02) is None

    def test_disabled_when_cfg_off(self) -> None:
        post = self._post_bars()
        flush = _bar(4, 51.6, 52.0, 51.0, 51.6, vol=500)
        post.append(flush)
        assert check_flush_exit(FadeBacktestConfig(), flush, 51.0, post, profit=0.02) is None


class TestPivotState:
    def test_pivot_confirmed_one_bar_later(self) -> None:
        st = PivotState()
        st.update(_bar(1, 52.0, 52.5, 51.8, 52.0))
        st.update(_bar(2, 52.0, 52.2, 51.0, 51.2))  # 候選 pivot low
        assert st.pivot_lows == []  # 尚未確認(無 lookahead)
        st.update(_bar(3, 51.2, 51.8, 51.4, 51.6))
        assert st.pivot_lows == [51.0]

    def test_pivot_high_strict(self) -> None:
        st = PivotState()
        st.update(_bar(1, 52.0, 52.0, 51.8, 52.0))
        st.update(_bar(2, 52.0, 52.5, 51.9, 52.3))  # 候選 pivot high
        st.update(_bar(3, 52.3, 52.1, 51.7, 51.9))
        assert st.pivot_highs == [52.5]

    def test_flat_lows_no_pivot(self) -> None:
        st = PivotState()
        st.update(_bar(1, 52.0, 52.5, 51.5, 52.0))
        st.update(_bar(2, 52.0, 52.2, 51.5, 51.8))  # 平底,非嚴格低
        st.update(_bar(3, 51.8, 52.0, 51.9, 52.0))
        assert st.pivot_lows == []


_HL_CFG = FadeBacktestConfig(tp_hl_k=2, tp_hl_min_profit=0.005)


def _state_with(lows: list[float], highs: list[float]) -> PivotState:
    st = PivotState()
    st.pivot_lows = list(lows)
    st.pivot_highs = list(highs)
    return st


class TestHigherLowExit:
    def test_triggers_on_higher_lows_and_highs(self) -> None:
        st = _state_with([51.0, 51.0, 51.4], [52.0, 52.3, 52.6])
        bar = _bar(30, 51.5, 51.8, 51.4, 51.6)
        fill = check_higher_low_exit(st, bar, profit=0.02, cfg=_HL_CFG)
        assert fill == bar.close

    def test_equal_low_counts_as_held(self) -> None:
        # 相等 low 視為未破(≥)
        st = _state_with([51.0, 51.0, 51.0], [52.0, 52.3, 52.6])
        bar = _bar(30, 51.5, 51.8, 51.4, 51.6)
        assert check_higher_low_exit(st, bar, profit=0.02, cfg=_HL_CFG) == bar.close

    def test_no_trigger_when_lows_break(self) -> None:
        st = _state_with([51.0, 51.4, 50.8], [52.0, 52.3, 52.6])
        bar = _bar(30, 51.5, 51.8, 51.4, 51.6)
        assert check_higher_low_exit(st, bar, profit=0.02, cfg=_HL_CFG) is None

    def test_no_trigger_when_highs_not_increasing(self) -> None:
        st = _state_with([51.0, 51.2, 51.4], [52.0, 52.0, 52.0])
        bar = _bar(30, 51.5, 51.8, 51.4, 51.6)
        assert check_higher_low_exit(st, bar, profit=0.02, cfg=_HL_CFG) is None

    def test_insufficient_pivots(self) -> None:
        st = _state_with([51.0, 51.2], [52.0, 52.3])
        bar = _bar(30, 51.5, 51.8, 51.4, 51.6)
        assert check_higher_low_exit(st, bar, profit=0.02, cfg=_HL_CFG) is None

    def test_min_profit_gate(self) -> None:
        st = _state_with([51.0, 51.2, 51.4], [52.0, 52.3, 52.6])
        bar = _bar(30, 51.5, 51.8, 51.4, 51.6)
        assert check_higher_low_exit(st, bar, profit=0.001, cfg=_HL_CFG) is None

    def test_disabled_when_cfg_off(self) -> None:
        st = _state_with([51.0, 51.2, 51.4], [52.0, 52.3, 52.6])
        bar = _bar(30, 51.5, 51.8, 51.4, 51.6)
        assert check_higher_low_exit(st, bar, profit=0.02, cfg=FadeBacktestConfig()) is None
