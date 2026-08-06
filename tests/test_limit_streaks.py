"""SC-2 純函式層測試:連板數(compute_day_limitups / compute_prev_streaks)。

零 IO。單日漲停判定與 `market_breadth` 同口徑(毫元精確等值),但前收來源不同:
snapshot 走 `close − change_price`,EOD 走 `close − spread`(除權息安全,neigui
`DailyIndex.ref_prev_close` 同源)。
"""

from __future__ import annotations

from copycat.limit_streaks import (
    STREAK_WINDOW_DAYS,
    compute_day_limitups,
    compute_prev_streaks,
)

# ---------------------------------------------------------------------------
# compute_day_limitups —— 單日 TaiwanStockPrice rows → 收盤漲停代號集合
# ---------------------------------------------------------------------------


def _row(sid: str, close: float, spread: float) -> dict:
    """FinMind TaiwanStockPrice 的最小必要欄(真 dataset 另有 open/max/min/...)。"""
    return {"stock_id": sid, "close": close, "spread": spread}


def test_compute_day_limitups_derives_prev_close_from_spread() -> None:
    # prev = 55.0 − 5.0 = 50.0 元 = 50_000 毫;cand = 55_000 落 50–100 元段
    # (tick 100 毫)→ 漲停 55_000 毫 = 55.0 元
    assert compute_day_limitups([_row("1234", 55.0, 5.0)]) == {"1234"}


def test_compute_day_limitups_spread_is_the_only_prev_close_source() -> None:
    """同一個 close 換 spread 即改判 —— 釘死前收確實由 spread 推導(除權息日的
    「前一日 close」與參考前收不同,拿錯來源會整批誤判)。"""
    # prev = 55.0 − 4.0 = 51.0 → 漲停 = 51_000*11//10 = 56_100 毫 ≠ 55_000
    assert compute_day_limitups([_row("1234", 55.0, 4.0)]) == set()


def test_compute_day_limitups_exact_milli_no_tolerance() -> None:
    # 54.9 = 一個整 tick(100 毫)之下;54.95 = 半 tick 之下 —— 皆非漲停
    assert compute_day_limitups([_row("1234", 54.9, 4.9)]) == set()
    assert compute_day_limitups([_row("1234", 54.95, 4.95)]) == set()


def test_compute_day_limitups_keeps_only_four_digit_ordinary_stocks() -> None:
    """權證 / ETF / 指數 row 即使價格恰好落在公式漲停價也不得入集合。"""
    rows = [
        _row("0050", 55.0, 5.0),  # ETF
        _row("00679B", 55.0, 5.0),  # ETF(6 位,00 前綴優先)
        _row("030171", 55.0, 5.0),  # 權證
        _row("001", 55.0, 5.0),  # 指數 row
        _row("1234", 55.0, 5.0),  # 普通股
    ]
    assert compute_day_limitups(rows) == {"1234"}


def test_compute_day_limitups_skips_unusable_rows() -> None:
    rows: list[dict] = [
        _row("1111", 5.0, 5.0),  # prev_close = 0 → 不判
        _row("2222", 5.0, 6.0),  # prev_close < 0 → 不判
        {"stock_id": "3333", "spread": 5.0},  # 缺 close
        {"stock_id": "4444", "close": 55.0},  # 缺 spread
        {"stock_id": "5555", "close": "N/A", "spread": 5.0},  # 非數值
        {"close": 55.0, "spread": 5.0},  # 缺 stock_id
    ]
    assert compute_day_limitups(rows) == set()


def test_compute_day_limitups_empty_input() -> None:
    assert compute_day_limitups([]) == set()


# ---------------------------------------------------------------------------
# compute_prev_streaks —— 新 → 舊 的日集合列表 → 連續漲停日數
# ---------------------------------------------------------------------------


def test_streak_window_days_is_ten() -> None:
    assert STREAK_WINDOW_DAYS == 10


def test_compute_prev_streaks_counts_consecutive_days_from_newest() -> None:
    # day_sets[0] = 最近可得交易日;A 連 3 日、B 只連最近 2 日
    day_sets = [{"A", "B"}, {"A", "B"}, {"A"}]
    assert compute_prev_streaks(day_sets) == {"A": 3, "B": 2}


def test_compute_prev_streaks_break_stops_counting() -> None:
    """中間一日沒漲停 → streak 停在中斷之前,更舊的漲停不得接回去。"""
    assert compute_prev_streaks([{"A"}, set(), {"A"}]) == {"A": 1}


def test_compute_prev_streaks_only_counts_stocks_in_the_newest_day() -> None:
    """最近日沒漲停的檔(含窗內才上市而缺 row 的檔)完全不入結果 —— 只含 streak ≥ 1。"""
    assert compute_prev_streaks([{"A"}, {"A", "C"}]) == {"A": 2}


def test_compute_prev_streaks_caps_at_window_length() -> None:
    """streak 上限 = 收到的交易日數(呼叫端據此標 `streak_capped`)。"""
    day_sets = [{"A"} for _ in range(STREAK_WINDOW_DAYS)]
    assert compute_prev_streaks(day_sets) == {"A": STREAK_WINDOW_DAYS}


def test_compute_prev_streaks_empty_inputs() -> None:
    assert compute_prev_streaks([]) == {}
    assert compute_prev_streaks([set()]) == {}
