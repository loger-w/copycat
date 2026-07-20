"""Round 5 投票制進場(prereg 2026-07-17 §2,凍結)——三票計分器。

每分鐘三票(0=反向 / 1=中性 / 2=同向),總分 ≥ S 的第一分鐘進場:
- 內盤比(開盤累計至 t):>hi → 2、<lo → 0、其間 → 1(量零 → 1)。
- 流向反轉(N/ρ,與 fade_entry_anatomy 同定義):翻轉已確認 → 2、
  攻擊段 armed 未翻(拉抬進行中)→ 0、全日尚無攻擊段 → 1。
- 位階(AH/NH,caller 先過適用性 = 線 ≥ T+1 開盤):當日高曾觸線 ±eps → 2、
  已越過所有適用線 +eps 以上 → 0(優先)、其餘 → 1(無適用線 → 1)。
全部只用開盤至 t 的資訊,無 lookahead;參數凍結不搜索。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Literal

from copycat.data.models import Bar1K

_SIGNALS = ("inner", "flow", "level")

SignalName = Literal["inner", "flow", "level"]


@dataclass(frozen=True, slots=True)
class VoteParams:
    s_threshold: int
    m_min: int  # bar m 索引下限(6 = 09:07 起,對齊 m7 臂)
    flow_n: int
    flow_rho: float
    flow_confirm: int
    inner_lo: float
    inner_hi: float
    level_eps: float
    flow_seg_gain: float


def iter_flow_flip(
    bars: list[Bar1K],
    *,
    n: int,
    rho: float,
    confirm: int,
    seg_gain: float,
    require_attack: bool = True,
) -> Iterator[tuple[int, Bar1K, bool, bool]]:
    """流向反轉 per-bar 狀態機(fade_vote 投票票 / fade_entry_anatomy._first_flip
    單一實作):逐 bar 產出 (index, bar, armed, flipped),armed / flipped 皆 sticky。

    攻擊段 = 連續 ≥n 根外盤 > 內盤且段內累計漲幅 ≥ seg_gain(基準 = 段前一根 close,
    段自首根起算用首根 open)→ armed。翻轉 = armed 後連續 confirm 根內盤 > 外盤 × rho。
    require_attack=False = 無前置對照(armed 自始成立,首根不計翻轉;rho ≥ 1 時與舊
    _first_flip 逐 bar 等價,rho < 1 的翻轉判定收斂本結構 — 凍結網格皆 ≥ 1 不受影響)。"""
    armed = not require_attack
    flipped = False
    flip_run = 0
    run_start: int | None = None
    for i, b in enumerate(bars):
        if b.up_volume > b.down_volume:
            if run_start is None:
                run_start = i
            run_len = i - run_start + 1
            base = bars[run_start].open if run_start == 0 else bars[run_start - 1].close
            if run_len >= n and base > 0 and (b.close / base - 1.0) >= seg_gain:
                armed = True
            flip_run = 0
        else:
            run_start = None
            if armed and not flipped and not (not require_attack and i == 0):
                if b.down_volume > b.up_volume * rho:
                    flip_run += 1
                    if flip_run >= confirm:
                        flipped = True
                else:
                    flip_run = 0
        yield i, b, armed, flipped


def _iter_votes(
    bars: list[Bar1K], level_values: tuple[float, ...], p: VoteParams
) -> Iterator[tuple[int, Bar1K, int, int, int]]:
    """逐 bar 產出 (index, bar, inner, flow, level) 三票;flow 狀態機 = iter_flow_flip。"""
    cum_up = 0.0
    cum_dn = 0.0
    running_high = 0.0
    touched = False
    for i, b, armed, flipped in iter_flow_flip(
        bars, n=p.flow_n, rho=p.flow_rho, confirm=p.flow_confirm, seg_gain=p.flow_seg_gain
    ):
        cum_up += b.up_volume
        cum_dn += b.down_volume
        # --- 三票 ---
        total_v = cum_up + cum_dn
        if total_v <= 0:
            inner = 1
        else:
            ratio = cum_dn / total_v
            inner = 2 if ratio > p.inner_hi else 0 if ratio < p.inner_lo else 1
        flow = 2 if flipped else 0 if armed else 1
        if not level_values:
            level = 1
        else:
            running_high = max(running_high, b.high)
            if any(abs(b.high - v) / v <= p.level_eps for v in level_values):
                touched = True
            if all(running_high > v * (1.0 + p.level_eps) for v in level_values):
                level = 0  # 突破優先(壓力位失效)
            elif touched:
                level = 2
            else:
                level = 1
        yield i, b, inner, flow, level


def find_vote_entry(
    bars: list[Bar1K], level_values: tuple[float, ...], p: VoteParams
) -> int | None:
    """總分 ≥ S 且 bar.m ≥ m_min 的第一根 → entry index;無 → None。"""
    for i, b, inner, flow, level in _iter_votes(bars, level_values, p):
        if b.m >= p.m_min and inner + flow + level >= p.s_threshold:
            return i
    return None


def find_signal_entry(
    bars: list[Bar1K],
    level_values: tuple[float, ...],
    p: VoteParams,
    signal: SignalName,
) -> int | None:
    """消融用單訊號進場:該票 = 2 且 bar.m ≥ m_min 的第一根。"""
    pos = _SIGNALS.index(signal)
    for i, b, *votes in _iter_votes(bars, level_values, p):
        if b.m >= p.m_min and votes[pos] == 2:
            return i
    return None


def find_inner15_entry(bars: list[Bar1K], phi: float) -> int | None:
    """inner15 臂(round 4 候選 (a)):前 15 分鐘(m<15)累計內盤比 > φ →
    進場於首根 m ≥ 15(gate 窗完整後才進,無 lookahead)。"""
    cum_up = 0.0
    cum_dn = 0.0
    entry_idx: int | None = None
    for i, b in enumerate(bars):
        if b.m < 15:
            cum_up += b.up_volume
            cum_dn += b.down_volume
        elif entry_idx is None:
            entry_idx = i
            break
    total = cum_up + cum_dn
    if entry_idx is None or total <= 0:
        return None
    return entry_idx if (cum_dn / total) > phi else None
