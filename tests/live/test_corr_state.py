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


    def test_longest_window_boundary_matches_mid_series_eviction(self) -> None:
        """perf #244 守門(T2 §9 意外 1):最長窗的 off-by-one 只在這裡發生。

        中價序列以 `ts < now − 1800` 逐出 → 現存樣本 1801 個 → 配對報酬 **1800** 筆(不是 1801);
        60 窗那條(上一案)量不到這個邊界,因為 60 窗的中價沒被逐出。斷 n 完全相等 + r 對照
        獨立 Pearson(容差 1e-9 抓得到差一筆的 1e-3)。
        """
        state = CorrState(["TXF", "NQ"], "TXF", windows=(1800,), min_samples={1800: 300})
        base = _walk(4, 3601)
        leg = _walk(8, 3601)

        ts = _feed(state, base, leg)
        out = state.correlations(ts)["NQ"]

        expected = _pearson(_returns(base[-1801:]), _returns(leg[-1801:]))
        assert out["n1800"] == 1800
        assert out["w1800"] is not None
        assert abs(out["w1800"] - expected) < 1e-9

    def test_short_windows_keep_w_plus_one_returns(self) -> None:
        """短窗(未撞到中價逐出)的舊語意 = `ts >= now − w` → w+1 筆報酬;增量版必須同數。"""
        state = CorrState(["TXF", "NQ"], "TXF", windows=(60, 300, 1800))
        ts = _feed(state, _walk(4, 2000), _walk(8, 2000))
        out = state.correlations(ts)["NQ"]
        assert (out["n60"], out["n300"], out["n1800"]) == (61, 301, 1800)

    def test_full_day_parity_with_batch_reference(self) -> None:
        """perf #244 全日對照:同一串 16,200 次 push(11 腿、SXF / VX 25% 有值、洞 + 相鄰判定
        全部走真實路徑),每 100 筆與檔內**整批**參考(自行逐出的中價序列 → 重掃配對 →
        `_pearson`)比:`n{w}` 全部 `==`(不用容差,差一筆一定抓到),r 的 max|Δr| 釘在實測值
        上一級(2026-09-15 本機實測 3.0e-14,見 assert 旁註解)。
        """
        import random

        legs = ["TXF", "TWN", "YM", "ES", "NQ", "SXF", "NK225M", "VX", "CL", "GC", "TSMC"]
        sparse = {"SXF", "VX"}
        windows = (60, 300, 1800)
        min_n = {60: 30, 300: 100, 1800: 300}
        state = CorrState(legs, "TXF", windows=windows, min_samples=min_n)
        rng = random.Random(244)
        px = {k: 20_000_000 + i * 1_000_000 for i, k in enumerate(legs)}
        series: dict[str, list[tuple[float, int | None]]] = {k: [] for k in legs}

        def reference(now: float, leg: str) -> dict[str, float | int | None]:
            base = series["TXF"]
            other = dict(series[leg])
            pairs: list[tuple[float, float, float]] = []
            prev: tuple[float, int | None, int | None] | None = None
            for t, b in base:
                o = other.get(t)
                if (
                    prev is not None
                    and prev[1] is not None
                    and prev[2] is not None
                    and b is not None
                    and o is not None
                    and abs((t - prev[0]) - 1.0) <= 0.5
                ):
                    pairs.append((t, math.log(b / prev[1]), math.log(o / prev[2])))
                prev = (t, b, o)
            row: dict[str, float | int | None] = {}
            for w in windows:
                xs = [rb for t, rb, _ in pairs if t >= now - w]
                ys = [rl for t, _, rl in pairs if t >= now - w]
                row[f"n{w}"] = len(xs)
                row[f"w{w}"] = _pearson(xs, ys) if len(xs) >= max(min_n[w], 2) else None
            return row

        max_dr = 0.0
        checks = 0
        ts = 0.0
        for i in range(16_200):
            ts += 1.0
            common = rng.gauss(0, 8e-5)
            mids: dict[str, int | None] = {}
            for k in legs:
                px[k] = int(round(px[k] * math.exp(common * 0.6 + rng.gauss(0, 8e-5))))
                mids[k] = None if (k in sparse and rng.random() > 0.25) else px[k]
            state.push(ts, mids, DAY)
            for k in legs:
                series[k].append((ts, mids[k]))
                while series[k] and series[k][0][0] < ts - 1800:
                    series[k].pop(0)
            if i % 100 != 99 and i < 16_150:
                continue
            got = state.correlations(ts)
            for leg in legs[1:]:
                ref = reference(ts, leg)
                for w in windows:
                    assert got[leg][f"n{w}"] == ref[f"n{w}"], (i, leg, w)
                    gv, rv = got[leg][f"w{w}"], ref[f"w{w}"]
                    assert (gv is None) == (rv is None), (i, leg, w)
                    if gv is not None and rv is not None:
                        max_dr = max(max_dr, abs(float(gv) - float(rv)))
                        checks += 1
        assert checks > 1000
        assert max_dr < 1e-9  # 實測 2026-09-15:見 commit 訊息;閉式公式 vs 定義式 Pearson 同量級 1e-15

    def test_constant_window_after_movement_returns_none(self) -> None:
        """running sums 加減後的殘差不得把「整窗零波動」算成一個亂數 r。

        先走 100 秒隨機漫步(sums 非零),再 61 秒完全不動 → 60 窗內報酬全 0 → w60 None;
        300 窗仍含前段波動 → 有值。
        """
        state = CorrState(["TXF", "NQ"], "TXF", windows=(60, 300), min_samples={60: 30, 300: 100})
        base = _walk(4, 101)
        leg = _walk(8, 101)
        base = base + [base[-1]] * 62
        leg = leg + [leg[-1]] * 62
        ts = _feed(state, base, leg)
        out = state.correlations(ts)["NQ"]
        assert out["n60"] == 61 and out["w60"] is None
        assert out["w300"] is not None and math.isfinite(out["w300"])


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


class TestWindowsDiffer:
    def test_full_windows_yield_different_values(self) -> None:
        """SC-3 驗證方式逐字對照:各窗滿窗後值互不相等。"""
        state = CorrState(
            ["TXF", "NQ"], "TXF", windows=(60, 300), min_samples={60: 30, 300: 100}
        )
        base = _walk(61, 301)
        leg = _walk(67, 301)

        ts = _feed(state, base, leg)
        out = state.correlations(ts)["NQ"]

        assert out["w60"] is not None
        assert out["w300"] is not None
        assert out["w60"] != out["w300"]
