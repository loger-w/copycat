"""CorrState 純狀態機:滾動相關、三窗門檻、盤別重置、報酬不跨洞(SC-1/3/4)。

參考值一律用本檔內手寫的 Pearson 公式計算,**不呼叫 statistics.correlation** ——
用實作所依賴的同一個函式當參考等於自證,測不出報酬提取與配對邏輯的錯誤。
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from copycat.live.corr_state import CorrState

DAY = ("20260730", "day")
NIGHT = ("20260730", "night")


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    """獨立參考實作(定義式,非 statistics.correlation)。"""
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    return cov / math.sqrt(vx * vy)


def _returns(prices: Sequence[int]) -> list[float]:
    return [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices))]


def _walk(seed: int, n: int, start: int = 40_000_000) -> list[int]:
    """確定性的偽隨機價格序列(不用 random,測試須可重現)。"""
    out = [start]
    state = seed
    for _ in range(n - 1):
        state = (state * 1103515245 + 12345) % 2147483648
        out.append(out[-1] + (state % 2001) - 1000)
    return out


def _feed(
    state: CorrState,
    base_prices: Sequence[int | None],
    leg_prices: Sequence[int | None],
    *,
    session: tuple[str, str] = NIGHT,
    start_ts: float = 1000.0,
) -> float:
    """逐秒 push;回傳最後一筆 ts。"""
    ts = start_ts
    for i, (b, lg) in enumerate(zip(base_prices, leg_prices)):
        ts = start_ts + i
        state.push(ts, {"TXF": b, "NQ": lg}, session)
    return ts


class TestCorrelationCorrectness:
    def test_matches_independent_pearson_reference(self) -> None:
        base = _walk(7, 61)
        leg = _walk(99, 61)
        state = CorrState(["TXF", "NQ"], "TXF", min_samples={60: 30, 300: 100, 1800: 300})

        ts = _feed(state, base, leg)
        got = state.correlations(ts)["NQ"]["w60"]

        expected = _pearson(_returns(base), _returns(leg))
        assert got is not None
        assert abs(got - expected) < 1e-9

    def test_identical_series_gives_perfect_correlation(self) -> None:
        base = _walk(3, 61)
        state = CorrState(["TXF", "NQ"], "TXF", min_samples={60: 30, 300: 100, 1800: 300})

        ts = _feed(state, base, list(base))

        got = state.correlations(ts)["NQ"]["w60"]
        assert got is not None
        assert math.isclose(got, 1.0, abs_tol=1e-9)

    def test_constant_series_returns_none_not_nan(self) -> None:
        """標準差為 0 → 分母為零。必須回 None,不可 NaN 或拋(edge case 1)。"""
        base = _walk(5, 61)
        flat = [40_000_000] * 61
        state = CorrState(["TXF", "NQ"], "TXF", min_samples={60: 30, 300: 100, 1800: 300})

        ts = _feed(state, base, flat)

        assert state.correlations(ts)["NQ"]["w60"] is None

    def test_base_leg_absent_from_pairs(self) -> None:
        state = CorrState(["TXF", "NQ"], "TXF")
        ts = _feed(state, _walk(1, 61), _walk(2, 61))
        assert "TXF" not in state.correlations(ts)


class TestWindowThresholds:
    def test_short_window_ready_while_longer_windows_still_none(self) -> None:
        """SC-3:第 61 秒 60s 窗有值(60 筆報酬 > 30),300s/1800s 未達門檻。"""
        state = CorrState(["TXF", "NQ"], "TXF")
        ts = _feed(state, _walk(11, 61), _walk(22, 61))

        out = state.correlations(ts)["NQ"]

        assert out["w60"] is not None
        assert out["w300"] is None
        assert out["w1800"] is None
        assert out["n300"] == 60

    def test_below_threshold_returns_none(self) -> None:
        state = CorrState(["TXF", "NQ"], "TXF")
        ts = _feed(state, _walk(1, 20), _walk(2, 20))

        out = state.correlations(ts)["NQ"]

        assert out["w60"] is None
        assert out["n60"] == 19

    def test_window_evicts_samples_older_than_window_length(self) -> None:
        """60s 窗只看最近 60 秒 —— 更早的樣本不得參與。"""
        state = CorrState(["TXF", "NQ"], "TXF", windows=(60,), min_samples={60: 30})
        base = _walk(4, 121)
        leg = _walk(8, 121)

        ts = _feed(state, base, leg)
        got = state.correlations(ts)["NQ"]["w60"]

        # 期望值只由最後 61 個價格點(= 60 筆報酬)構成
        expected = _pearson(_returns(base[-61:]), _returns(leg[-61:]))
        assert got is not None
        assert abs(got - expected) < 1e-9


class TestSessionReset:
    def test_session_change_clears_all_series(self) -> None:
        """SC-4:盤別切換清窗。日盤累積的樣本不得延續到夜盤。"""
        state = CorrState(["TXF", "NQ"], "TXF")
        _feed(state, _walk(1, 61), _walk(2, 61), session=DAY)

        assert state.correlations(1060.0)["NQ"]["w60"] is not None

        state.push(1061.0, {"TXF": 40_000_000, "NQ": 20_000_000}, NIGHT)

        out = state.correlations(1061.0)["NQ"]
        assert out["n60"] == 0
        assert out["w60"] is None

    def test_same_session_does_not_clear(self) -> None:
        state = CorrState(["TXF", "NQ"], "TXF")
        ts = _feed(state, _walk(1, 61), _walk(2, 61), session=NIGHT)
        assert state.correlations(ts)["NQ"]["n60"] == 60

    def test_date_rollover_clears_even_within_same_session_kind(self) -> None:
        """跨日:session key 含 UTC 日期,同為 night 但換日也要清(edge case 3)。"""
        state = CorrState(["TXF", "NQ"], "TXF")
        _feed(state, _walk(1, 61), _walk(2, 61), session=("20260730", "night"))

        state.push(1061.0, {"TXF": 40_000_000, "NQ": 20_000_000}, ("20260731", "night"))

        assert state.correlations(1061.0)["NQ"]["n60"] == 0


class TestNoGapBridging:
    def test_missing_value_does_not_bridge_returns(self) -> None:
        """design review P0-2:缺值處不得跨接產生報酬。

        61 個時點、第 30 點該腿為 None → 少掉「進洞」與「出洞」兩筆報酬,
        n 應為 58 而非 59(跨接)或 60(當作沒缺)。
        """
        base = _walk(13, 61)
        leg: list[int | None] = list(_walk(17, 61))
        leg[30] = None
        state = CorrState(["TXF", "NQ"], "TXF", min_samples={60: 1, 300: 1, 1800: 1})

        ts = _feed(state, base, leg)

        assert state.correlations(ts)["NQ"]["n60"] == 58

    def test_base_missing_also_drops_pair(self) -> None:
        base: list[int | None] = list(_walk(13, 61))
        base[10] = None
        state = CorrState(["TXF", "NQ"], "TXF", min_samples={60: 1, 300: 1, 1800: 1})

        ts = _feed(state, base, _walk(17, 61))

        assert state.correlations(ts)["NQ"]["n60"] == 58

    def test_time_gap_does_not_bridge_returns(self) -> None:
        """漏拍(ts 不連續)同樣不得跨接 —— 該筆報酬涵蓋 2 秒,與其餘尺度不一致。"""
        state = CorrState(["TXF", "NQ"], "TXF", min_samples={60: 1, 300: 1, 1800: 1})
        base = _walk(21, 61)
        leg = _walk(23, 61)

        ts = 1000.0
        for i in range(61):
            # 第 40 筆之後跳一秒(模擬 event loop 漏拍)
            ts = 1000.0 + i + (1.0 if i >= 40 else 0.0)
            state.push(ts, {"TXF": base[i], "NQ": leg[i]}, NIGHT)

        assert state.correlations(ts)["NQ"]["n60"] == 59

    def test_values_after_gap_still_counted(self) -> None:
        """洞之後的樣本要照常累積,不能整段作廢。"""
        base = _walk(31, 21)
        leg: list[int | None] = list(_walk(37, 21))
        leg[5] = None
        state = CorrState(["TXF", "NQ"], "TXF", min_samples={60: 1, 300: 1, 1800: 1})

        ts = _feed(state, base, leg)

        # 20 筆潛在報酬 - 2(進洞/出洞)= 18
        assert state.correlations(ts)["NQ"]["n60"] == 18


class TestMultipleLegs:
    def test_legs_are_independent(self) -> None:
        """單腿缺值不得影響其他腿(edge case 5)。"""
        state = CorrState(["TXF", "NQ", "SXF"], "TXF", min_samples={60: 1, 300: 1, 1800: 1})
        base = _walk(41, 31)
        nq = _walk(43, 31)
        sxf: list[int | None] = list(_walk(47, 31))
        sxf[10] = None

        ts = 1000.0
        for i in range(31):
            ts = 1000.0 + i
            state.push(ts, {"TXF": base[i], "NQ": nq[i], "SXF": sxf[i]}, NIGHT)

        out = state.correlations(ts)
        assert out["NQ"]["n60"] == 30
        assert out["SXF"]["n60"] == 28
