"""overlay(CDP/MA)純計算與 cache 測試 — SC-4."""

from __future__ import annotations

from copycat.live.stock_source import DailyBar
from copycat.server.overlay import OverlayCache, build_overlay, compute_cdp, compute_ma


def _bar(date: str, h: int, lo: int, c: int) -> DailyBar:
    return {"date": date, "high": h, "low": lo, "close": c}


class TestComputeCdp:
    def test_formula(self) -> None:
        # h=103000 l=100000 c=102000 → cdp=(103000+100000+204000)/4=101750
        cdp = compute_cdp(103_000, 100_000, 102_000)
        assert cdp == {
            "cdp": 101_750,
            "ah": 104_750,  # cdp + (h-l)
            "nh": 103_500,  # 2cdp - l
            "nl": 100_500,  # 2cdp - h
            "al": 98_750,  # cdp - (h-l)
        }

    def test_tie_rounds_half_up(self) -> None:
        # h+l+2c = 10 → 10/4 = 2.5;round-half-up → 3(impl-spec R1:(x+2)//4)
        assert compute_cdp(4, 2, 2)["cdp"] == 3


class TestComputeMa:
    def test_ma_last_n(self) -> None:
        closes = [100, 200, 300, 400, 500, 600]
        assert compute_ma(closes, 5) == 400  # (200+...+600)/5

    def test_insufficient_returns_none(self) -> None:
        assert compute_ma([100, 200], 5) is None


class TestBuildOverlay:
    BARS = [_bar(f"2026-07-{d:02d}", 103_000, 100_000, 100_000 + d * 100) for d in range(1, 27)]

    def test_partial_bar_of_today_excluded(self) -> None:
        bars = [*self.BARS, _bar("2026-07-28", 999_000, 1_000, 500_000)]
        result = build_overlay(bars, today="2026-07-28")
        assert result["date"] == "2026-07-26"
        assert result["cdp"] is not None
        assert result["cdp"]["cdp"] == compute_cdp(103_000, 100_000, 102_600)["cdp"]

    def test_empty_after_exclusion_all_null(self) -> None:
        result = build_overlay([_bar("2026-07-28", 1, 1, 1)], today="2026-07-28")
        assert result == {"cdp": None, "ma5": None, "ma20": None, "date": None}

    def test_ma_values(self) -> None:
        result = build_overlay(self.BARS, today="2026-07-28")
        closes = [b["close"] for b in self.BARS]
        assert result["ma5"] == sum(closes[-5:]) // 5
        assert result["ma20"] == sum(closes[-20:]) // 20

    def test_insufficient_ma20_null_but_cdp_present(self) -> None:
        result = build_overlay(self.BARS[:6], today="2026-07-28")
        assert result["cdp"] is not None
        assert result["ma5"] is not None
        assert result["ma20"] is None


class TestOverlayCache:
    def test_caches_non_empty(self) -> None:
        cache = OverlayCache()
        value = {"cdp": {"cdp": 1}, "ma5": 1, "ma20": 1, "date": "2026-07-25"}
        cache.put("2330", "2026-07-28", value)
        assert cache.get("2330", "2026-07-28") == value

    def test_does_not_cache_all_null(self) -> None:
        cache = OverlayCache()
        cache.put("2330", "2026-07-28", {"cdp": None, "ma5": None, "ma20": None, "date": None})
        assert cache.get("2330", "2026-07-28") is None

    def test_key_includes_date(self) -> None:
        cache = OverlayCache()
        value = {"cdp": {"cdp": 1}, "ma5": 1, "ma20": 1, "date": "2026-07-25"}
        cache.put("2330", "2026-07-25", value)
        assert cache.get("2330", "2026-07-28") is None
