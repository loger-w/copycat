"""river_models 純對映測試(SC-2:盤別窗 / 跨午夜 / 收盤 clamp / 1K 解析)。"""

from __future__ import annotations

import time

from copycat.live.river_models import (
    SESSION_WINDOWS,
    all_day_utc_window,
    close_clamp_rank,
    minute_end_from_1k,
    minute_end_from_taipei,
    minute_end_from_utc_hhmmss,
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


class TestCloseClampRank:
    """clamp 名次(B8):`push` 靠它分辨「收盤撮合那一分鐘」與「收盤後的殘留取樣」。

    只鎖 end / end+1 / end+2 / end+5 / end+6 五個邊界 —— 中間值由同一把尺(`_expand`)
    保證,多鎖只是把實作抄一遍。
    """

    def test_end_minute_is_not_clamped(self) -> None:
        assert close_clamp_rank(825, "day") == 0  # 13:45 bar 本身

    def test_close_auction_minute_is_rank_one(self) -> None:
        assert close_clamp_rank(826, "day") == 1  # 13:45:xx 的成交 → 仍要進得來

    def test_first_stale_minute_is_rank_two(self) -> None:
        assert close_clamp_rank(827, "day") == 2  # 13:46 起 = 收盤後殘留

    def test_last_clamped_minute_is_rank_five(self) -> None:
        assert close_clamp_rank(830, "day") == 5

    def test_beyond_clamp_window_is_none(self) -> None:
        assert close_clamp_rank(831, "day") is None  # 與 offset_of 同時失效


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


class TestMinuteEndFromUtcHhmmss:
    """Phase 6 real-env finding:`PreciseTime` 欄寬跨交易所段不同 → 改吃 `FilledTime`。

    CME/CBOT/SGX 的 PreciseTime 是 6 位 HHMMSS(實測 MES `"41256"`),台期交是 12 位
    HHMMSSffffff。`stock_models._taipei_time` 的 zfill(12) 對海外腿會算出恆為
    台北 08:00:00.0xx 的假時刻 → 分鐘落在窗外 → 該腿永遠不進點。
    """

    def test_six_digit_utc_becomes_taipei_bar_end(self) -> None:
        # "41256" = 04:12:56 UTC = 台北 12:12:56 → 桶 12:13 = 733
        assert minute_end_from_utc_hhmmss("41256") == 733

    def test_zero_padded_form(self) -> None:
        assert minute_end_from_utc_hhmmss("041256") == 733

    def test_midnight_utc_wraps_to_taipei_morning(self) -> None:
        # 00:30:10 UTC = 台北 08:30:10 → 桶 08:31 = 511
        assert minute_end_from_utc_hhmmss("3010") == 511

    def test_2359_taipei_rolls_to_1440(self) -> None:
        # 15:59:30 UTC = 台北 23:59:30 → 桶 1440(不是 0;夜盤 offset 才連續)
        assert minute_end_from_utc_hhmmss("155930") == 1440

    def test_bad_or_empty_is_none(self) -> None:
        assert minute_end_from_utc_hhmmss("") is None
        assert minute_end_from_utc_hhmmss("bad") is None
        assert minute_end_from_utc_hhmmss("990000") is None


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
