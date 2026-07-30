"""river_models 純對映測試(SC-2:盤別窗 / 跨午夜 / 收盤 clamp / 1K 解析)。"""

from __future__ import annotations

import time

from copycat.live.river_models import (
    SESSION_WINDOWS,
    all_day_utc_window,
    minute_end_from_1k,
    minute_end_from_taipei,
    offset_of,
    parse_1k_minutes,
    window_bounds,
)


class TestWindowBounds:
    def test_day_window_is_0845_to_1345(self) -> None:
        assert window_bounds("day") == (525, 825)

    def test_night_window_expands_past_midnight(self) -> None:
        assert window_bounds("night") == (900, 1740)

    def test_unknown_kind_falls_back_to_day(self) -> None:
        assert window_bounds("weird") == SESSION_WINDOWS["day"]


class TestOffsetOfDay:
    def test_first_bar_is_offset_one(self) -> None:
        assert offset_of(526, "day") == 1  # 08:46 bar

    def test_last_bar_is_offset_300(self) -> None:
        assert offset_of(825, "day") == 300  # 13:45 bar

    def test_pre_open_bar_dropped(self) -> None:
        assert offset_of(525, "day") is None  # 08:45 bar = 08:44–08:45 開盤前

    def test_close_correction_clamps_five_minutes(self) -> None:
        # 13:45:xx 的成交桶 = 13:46;不 clamp 就整段丟掉(design review P0-1)
        assert offset_of(826, "day") == 300
        assert offset_of(830, "day") == 300

    def test_beyond_clamp_window_dropped(self) -> None:
        assert offset_of(831, "day") is None


class TestOffsetOfNight:
    def test_first_bar_is_offset_one(self) -> None:
        assert offset_of(901, "night") == 1  # 15:01

    def test_midnight_sorts_after_evening(self) -> None:
        # 23:00 = 1380 → 480;00:30 = 30(minute-of-day)→ +1440 → 1470 → 570
        assert offset_of(1380, "night") == 480
        assert offset_of(1470, "night") == 570
        assert offset_of(30, "night") == 570

    def test_last_bar_is_offset_840(self) -> None:
        assert offset_of(1740, "night") == 840  # 05:00
        assert offset_of(300, "night") == 840  # 同一分鐘的另一種表述

    def test_close_correction_and_beyond(self) -> None:
        assert offset_of(1745, "night") == 840
        assert offset_of(1746, "night") is None


class TestMinuteEndFromTaipei:
    def test_tick_bucketed_to_bar_end(self) -> None:
        assert minute_end_from_taipei("08:45:30.500") == 526

    def test_compact_format(self) -> None:
        assert minute_end_from_taipei("134459") == 825

    def test_2359_rolls_to_1440_not_zero(self) -> None:
        # floor+1 讓 23:59 的桶 = 1440(不是 0)—— 夜盤 offset 才連續
        assert minute_end_from_taipei("23:59:01.000") == 1440

    def test_bad_format_is_none(self) -> None:
        assert minute_end_from_taipei("bad") is None
        assert minute_end_from_taipei("") is None


class TestMinuteEndFrom1k:
    def test_utc_time_shifted_without_plus_one(self) -> None:
        # TC4 1K 的 Time 已是 bar 終點(probe 實證:UDF 首列 004600 = 台北 08:46)
        assert minute_end_from_1k({"Date": "20260730", "Time": "004600"}) == 526

    def test_short_time_zero_padded(self) -> None:
        # MES 首列 Time="100" = UTC 00:01 → 台北 08:01
        assert minute_end_from_1k({"Date": "20260730", "Time": "100"}) == 481

    def test_missing_time_is_none(self) -> None:
        assert minute_end_from_1k({"Date": "20260730"}) is None


class TestParse1kMinutes:
    def test_parses_probe_rows_and_skips_broken(self) -> None:
        rows = [
            {"Date": "20260730", "Time": "004600", "Close": "51666", "Volume": "0"},
            {"Date": "20260730", "Time": "004700", "Volume": "3"},  # 缺 Close → 略過
            {"Date": "20260730", "Time": "013500", "Close": "51900", "Volume": "0"},
        ]
        assert parse_1k_minutes(rows) == [(526, 51_666_000), (575, 51_900_000)]

    def test_empty_rows(self) -> None:
        assert parse_1k_minutes([]) == []


class TestAllDayUtcWindow:
    def test_window_is_whole_utc_day(self) -> None:
        assert all_day_utc_window(time.gmtime(0)) == ("1970010100", "1970010123")
