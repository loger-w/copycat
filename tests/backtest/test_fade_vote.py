"""Round 5 投票制進場(fade_vote):三票計分 / 單訊號消融 / inner15 臂。

配分表凍結出處:docs/superpowers/specs/2026-07-17-fade-round5-prereg-draft.md §2。
"""

from __future__ import annotations

from copycat.backtest.fade_vote import (
    VoteParams,
    find_inner15_entry,
    find_signal_entry,
    find_vote_entry,
)
from copycat.data.models import Bar1K


def _bar(
    m: int,
    o: float,
    h: float,
    lo: float,
    c: float,
    up: float = 30,
    dn: float = 70,
) -> Bar1K:
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


def _params(s: int = 5, m_min: int = 0, confirm: int = 1) -> VoteParams:
    return VoteParams(
        s_threshold=s,
        m_min=m_min,
        flow_n=5,
        flow_rho=1.5,
        flow_confirm=confirm,
        inner_lo=0.45,
        inner_hi=0.55,
        level_eps=0.005,
        flow_seg_gain=0.01,
    )


class TestVoteEntry:
    def test_inner2_flow1_level2_reaches_5(self) -> None:
        # 內盤比 0.7(2)+ 無攻擊段(1)+ 高點觸線 52.0(2)= 5 → S=5 進場
        bars = [_bar(m, 52.0, 52.0, 51.8, 51.9, up=30, dn=70) for m in range(10)]
        idx = find_vote_entry(bars, (52.0,), _params(s=5, m_min=3))
        assert idx is not None
        assert bars[idx].m == 3  # m_min 前不進場

    def test_attack_in_progress_blocks(self) -> None:
        # 攻擊段 armed 未翻(flow=0):內盤比即使翻正也湊不到 5
        bars = []
        price = 52.0
        for m in range(8):  # 連續外盤 + 漲 >1% → armed
            new_p = round(price * 1.004, 2)
            bars.append(_bar(m, price, new_p, price, new_p, up=80, dn=20))
            price = new_p
        # 攻擊後盤整(up>dn 維持,未翻轉;累計內盤比低 → inner=0)
        bars += [_bar(m, price, price, price - 0.05, price, up=60, dn=40) for m in range(8, 15)]
        idx = find_vote_entry(bars, (price * 2,), _params(s=5, m_min=0))
        assert idx is None

    def test_flip_after_attack_unlocks(self) -> None:
        # 攻擊 → 翻轉(flow=2)+ 翻轉後內盤比累積 + 觸線 → 進場
        bars = []
        price = 52.0
        for m in range(6):
            new_p = round(price * 1.004, 2)
            bars.append(_bar(m, price, new_p, price, new_p, up=80, dn=20))
            price = new_p
        # 大量內盤翻轉(dn 遠大於 up×1.5)拉高累計內盤比 → inner 過 0.55
        bars += [
            _bar(m, price, price, price - 0.3, price - 0.2, up=20, dn=900) for m in range(6, 10)
        ]
        # 觸線:攻擊高點 ≈ 53.26,線設 53.3(|53.26−53.3|/53.3 ≈ 0.08% ≤ 0.5%)
        idx = find_vote_entry(bars, (53.3,), _params(s=5, m_min=0))
        assert idx is not None

    def test_level_breakout_scores_zero(self) -> None:
        # 高點越過唯一適用線 +0.5% 以上 → level=0;內盤 2 + flow 1 = 3 < 4
        bars = [_bar(0, 52.0, 53.0, 51.9, 52.0, up=30, dn=70)]
        bars += [_bar(m, 52.0, 52.1, 51.8, 51.9, up=30, dn=70) for m in range(1, 10)]
        idx = find_vote_entry(bars, (52.5,), _params(s=4, m_min=0))  # 53.0 > 52.5×1.005
        assert idx is None

    def test_no_levels_is_neutral(self) -> None:
        # 無適用線 → level=1;內盤 2 + flow 1 + level 1 = 4 → S=4 過
        bars = [_bar(m, 52.0, 52.1, 51.8, 51.9, up=30, dn=70) for m in range(10)]
        assert find_vote_entry(bars, (), _params(s=4, m_min=0)) is not None
        assert find_vote_entry(bars, (), _params(s=5, m_min=0)) is None


class TestSignalEntry:
    def test_inner_only(self) -> None:
        bars = [_bar(m, 52.0, 52.1, 51.8, 51.9, up=30, dn=70) for m in range(10)]
        assert find_signal_entry(bars, (), _params(m_min=2), "inner") is not None
        bars_low = [_bar(m, 52.0, 52.1, 51.8, 51.9, up=70, dn=30) for m in range(10)]
        assert find_signal_entry(bars_low, (), _params(m_min=2), "inner") is None

    def test_level_only(self) -> None:
        bars = [_bar(m, 52.0, 52.0, 51.8, 51.9) for m in range(10)]
        assert find_signal_entry(bars, (52.0,), _params(m_min=0), "level") is not None
        assert find_signal_entry(bars, (60.0,), _params(m_min=0), "level") is None


class TestFlowConsistencyWithAnatomy:
    """fade_vote flow 票與 fade_entry_anatomy._first_flip 必須同定義
    (收尾 review:雙實作無共用,以本測試釘住等價性防漂移)。"""

    def _fixtures(self) -> list[list[Bar1K]]:
        # 攻擊 → 翻轉
        f1 = []
        price = 52.0
        for m in range(6):
            new_p = round(price * 1.004, 2)
            f1.append(_bar(m, price, new_p, price, new_p, up=80, dn=20))
            price = new_p
        f1 += [_bar(m, price, price, price - 0.3, price - 0.2, up=20, dn=900) for m in range(6, 10)]
        # 全日內盤、無攻擊段
        f2 = [_bar(m, 52.0, 52.1, 51.9, 52.0, up=20, dn=80) for m in range(20)]
        # 攻擊後盤整、未翻轉
        f3 = []
        price = 52.0
        for m in range(8):
            new_p = round(price * 1.004, 2)
            f3.append(_bar(m, price, new_p, price, new_p, up=80, dn=20))
            price = new_p
        f3 += [_bar(m, price, price, price - 0.05, price, up=60, dn=40) for m in range(8, 15)]
        return [f1, f2, f3]

    def test_flow_entry_equals_anatomy_first_flip(self) -> None:
        from copycat.backtest.fade_entry_anatomy import _first_flip

        for confirm in (1, 2):
            for bars in self._fixtures():
                expected = _first_flip(bars, 1.5, confirm, require_attack=True, n=5)
                got = find_signal_entry(bars, (), _params(m_min=0, confirm=confirm), "flow")
                assert got == expected


class TestInner15:
    def test_gate_and_entry_bar(self) -> None:
        # 前 15 分內盤比 0.7 > 0.55 → 進場於首根 m ≥ 15
        bars = [_bar(m, 52.0, 52.1, 51.8, 51.9, up=30, dn=70) for m in range(20)]
        idx = find_inner15_entry(bars, 0.55)
        assert idx is not None
        assert bars[idx].m == 15

    def test_gate_fail(self) -> None:
        bars = [_bar(m, 52.0, 52.1, 51.8, 51.9, up=70, dn=30) for m in range(20)]
        assert find_inner15_entry(bars, 0.55) is None

    def test_no_tail_no_entry(self) -> None:
        bars = [_bar(m, 52.0, 52.1, 51.8, 51.9, up=30, dn=70) for m in range(10)]
        assert find_inner15_entry(bars, 0.55) is None
