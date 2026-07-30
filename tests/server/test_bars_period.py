"""週 / 月 K 聚合(index-board N-1)。

TC4 沒有 WK / MK DataType(官方 wrapper 只有 TICKS/1K/DK)→ 週月只能由日 K 聚合。

**桶鍵取實際日期(ISO 年-週 / 年-月),不是「每 N 根一組」** —— 連假 / 補班週的
交易日數不固定,固定根數分組會累積錯位,而且圖形看起來完全正常、沒有任何斷言會紅
(change-spec §1.2 陷阱清單第一條)。本檔的存在就是釘住這件事。
"""

from __future__ import annotations

from copycat.live.stock_source import Bar
from copycat.server.bars import aggregate_period


def bar(t: str, o: int, h: int, low: int, c: int, v: int = 1) -> Bar:
    return Bar(t=t, o=o, h=h, l=low, c=c, v=v)


class TestWeekly:
    def test_ohlcv_and_right_edge_stamp(self) -> None:
        """o = 桶內第一根 o、h = max、l = min、c = 最後一根 c、v = Σv;
        `t` 取桶內**最後一個交易日**(右端對齊,與 K 線終點標記慣例一致)。"""
        # 2026-07-27(一)~ 2026-07-31(五)= ISO 2026-W31
        bars = [
            bar("2026-07-27", 100, 110, 95, 105, 10),
            bar("2026-07-28", 105, 120, 104, 118, 20),
            bar("2026-07-29", 118, 119, 90, 92, 30),
        ]
        out = aggregate_period(bars, "W")
        assert len(out) == 1
        assert out[0] == Bar(t="2026-07-29", o=100, h=120, l=90, c=92, v=60)

    def test_holiday_week_with_three_trading_days_keeps_own_bucket(self) -> None:
        """連假週只有 3 個交易日 —— 固定根數分組(每 5 根一週)會從這裡開始永久錯位。"""
        bars = [
            # 2026-06-15(一)~ 19(五):W25,但週三放假 → 只有 4 天
            bar("2026-06-15", 10, 11, 9, 10),
            bar("2026-06-16", 10, 12, 10, 11),
            bar("2026-06-18", 11, 13, 11, 12),
            bar("2026-06-19", 12, 14, 12, 13),
            # 2026-06-22(一)~ 26(五):W26,只有 3 天
            bar("2026-06-22", 13, 15, 13, 14),
            bar("2026-06-24", 14, 16, 14, 15),
            bar("2026-06-26", 15, 17, 15, 16),
            # 2026-06-29(一)~ 07-03(五):W27
            bar("2026-06-29", 16, 18, 16, 17),
        ]
        out = aggregate_period(bars, "W")
        assert [b["t"] for b in out] == ["2026-06-19", "2026-06-26", "2026-06-29"]
        assert [b["c"] for b in out] == [13, 16, 17]

    def test_year_boundary_week_is_one_bucket(self) -> None:
        """2025-12-29(一)~ 2026-01-02(五)同屬 ISO 2026-W01 —— 用曆年+週號當鍵會拆成兩桶。"""
        bars = [
            bar("2025-12-29", 10, 11, 9, 10),
            bar("2025-12-31", 10, 12, 10, 11),
            bar("2026-01-02", 11, 13, 8, 12),
        ]
        out = aggregate_period(bars, "W")
        assert len(out) == 1
        assert out[0]["t"] == "2026-01-02"
        assert (out[0]["o"], out[0]["h"], out[0]["l"], out[0]["c"]) == (10, 13, 8, 12)

    def test_single_trading_day_week(self) -> None:
        bars = [bar("2026-02-16", 10, 11, 9, 10, 7)]
        out = aggregate_period(bars, "W")
        assert out == [Bar(t="2026-02-16", o=10, h=11, l=9, c=10, v=7)]


class TestMonthly:
    def test_month_bucket_by_calendar_month(self) -> None:
        bars = [
            bar("2026-06-29", 10, 11, 9, 10, 5),
            bar("2026-06-30", 10, 15, 10, 14, 5),
            bar("2026-07-01", 14, 16, 13, 15, 5),
            bar("2026-07-31", 15, 20, 7, 8, 5),
        ]
        out = aggregate_period(bars, "M")
        assert [b["t"] for b in out] == ["2026-06-30", "2026-07-31"]
        assert out[0] == Bar(t="2026-06-30", o=10, h=15, l=9, c=14, v=10)
        assert out[1] == Bar(t="2026-07-31", o=14, h=20, l=7, c=8, v=10)

    def test_month_end_on_non_trading_day_uses_last_actual_bar(self) -> None:
        """2026-05-31 是週日 → 該月最後一根是 05-29;`t` 不得憑空造出非交易日。"""
        bars = [bar("2026-05-28", 10, 11, 9, 10), bar("2026-05-29", 10, 12, 10, 11)]
        out = aggregate_period(bars, "M")
        assert out[0]["t"] == "2026-05-29"


class TestEdges:
    def test_empty_input(self) -> None:
        assert aggregate_period([], "W") == []
        assert aggregate_period([], "M") == []

    def test_unsorted_input_is_sorted_first(self) -> None:
        """上游已排序,但聚合結果的正確性不該依賴呼叫端(o/c 取端點,順序錯 = 值錯)。"""
        bars = [
            bar("2026-07-29", 118, 119, 90, 92),
            bar("2026-07-27", 100, 110, 95, 105),
            bar("2026-07-28", 105, 120, 104, 118),
        ]
        out = aggregate_period(bars, "W")
        assert (out[0]["o"], out[0]["c"]) == (100, 92)

    def test_minute_stamps_are_passed_through_untouched(self) -> None:
        """防呆:分 K(`t` 含 HH:MM)不該被送進來;真送進來也不得靜默算出錯誤的週 bar。"""
        bars = [bar("2026-07-29 10:30", 1, 2, 1, 2)]
        assert aggregate_period(bars, "W") == []
