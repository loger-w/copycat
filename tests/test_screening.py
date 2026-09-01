"""盤前選股篩選純函式層測試(spec issue #173,seam 已議定)。

零 IO。輸入 = 逐日全市場 TaiwanStockPrice rows(新→舊)+ 資格 / 處置集合,
輸出 = 排序後候選名單。還原係數鏈與收盤鎖板判定皆以 `close − spread` 推導
參考前收(與 `limit_streaks` 同口徑,除權息安全)。
"""

from __future__ import annotations

import datetime as _dt

from copycat.screening import (
    AVG_LOTS_MIN,
    RET_MIN_PCT,
    RUN_TIME,
    WINDOW_DAYS,
    ScreenCandidate,
    apply_eligibility,
    expected_data_date,
    hard_candidates,
    shrink_rows,
)
from copycat.trading_calendar import WEEKEND_ONLY

D0 = _dt.date(2026, 9, 1)  # 最新交易日
D1 = _dt.date(2026, 8, 31)
D2 = _dt.date(2026, 8, 28)  # 最舊(基準日,只出 close)


def _row(sid: str, close: float, spread: float, vol_shares: float = 5_000_000) -> dict:
    """FinMind TaiwanStockPrice 的最小必要欄(真 dataset 另有 open/max/min/...)。"""
    return {"stock_id": sid, "close": close, "spread": spread, "Trading_Volume": vol_shares}


def _days(*per_day: list[dict]) -> list[tuple[_dt.date, list[dict]]]:
    """新→舊組裝(per_day[0] = D0)。"""
    dates = [D0, D1, D2]
    return [(dates[i], rows) for i, rows in enumerate(per_day)]


# ---------------------------------------------------------------------------
# hard_candidates —— 三硬條件 + universe + 排序
# ---------------------------------------------------------------------------


def test_constants_match_spec() -> None:
    assert RET_MIN_PCT == 15.0
    assert AVG_LOTS_MIN == 5000.0
    assert WINDOW_DAYS == 21


def test_pass_all_three_conditions() -> None:
    # D2 基準 100;D1 收 110 spread 10 → prev_ref 100,漲停 110_000 毫 = 收盤鎖板
    # D0 收 116 spread 6 → prev_ref 110,非鎖板。還原漲幅 = 116/100 − 1 = +16%
    days = _days(
        [_row("1234", 116.0, 6.0)],
        [_row("1234", 110.0, 10.0)],
        [_row("1234", 100.0, 0.0)],
    )
    got = hard_candidates(days)
    assert len(got) == 1
    cand = got[0]
    assert cand.code == "1234"
    assert round(cand.ret_pct, 6) == 16.0
    assert cand.avg_lots == 5000.0
    assert cand.lock_dates == (D1,)


def test_return_below_threshold_excluded() -> None:
    # 116 → 114:漲幅 +14% < 15%,即使有鎖板日與量也不收
    days = _days(
        [_row("1234", 114.0, 4.0)],
        [_row("1234", 110.0, 10.0)],  # 鎖板日
        [_row("1234", 100.0, 0.0)],
    )
    assert hard_candidates(days) == []


def test_no_close_lock_excluded() -> None:
    # 漲 +16% 但沒有任何一天收盤鎖板(108 對 prev_ref 100 的漲停 110 未到;
    # 116 對 prev_ref 108 的漲停 118.8 未到)
    days = _days(
        [_row("1234", 116.0, 8.0)],
        [_row("1234", 108.0, 8.0)],
        [_row("1234", 100.0, 0.0)],
    )
    assert hard_candidates(days) == []


def test_volume_below_threshold_excluded() -> None:
    # 均量取「基準日以外」的 20 個交易日:兩天各 4,999 張 → 不收
    days = _days(
        [_row("1234", 116.0, 6.0, vol_shares=4_999_000)],
        [_row("1234", 110.0, 10.0, vol_shares=4_999_000)],
        [_row("1234", 100.0, 0.0, vol_shares=999_999_000)],  # 基準日量不計
    )
    assert hard_candidates(days) == []


def test_baseline_day_volume_not_counted() -> None:
    """反向釘死:基準日灌天量也救不了(上一測試的對照組)。"""
    days = _days(
        [_row("1234", 116.0, 6.0, vol_shares=5_000_000)],
        [_row("1234", 110.0, 10.0, vol_shares=5_000_000)],
        [_row("1234", 100.0, 0.0, vol_shares=0.0)],  # 基準日 0 量,不影響
    )
    assert len(hard_candidates(days)) == 1


def test_adjustment_chain_neutralizes_ex_dividend() -> None:
    # D1 除息 10 元:prev_ref = 94.5 − 4.5 = 90 ≠ 前日 close 100 → 係數鏈吸收。
    # D0 收 103.5 spread 9 → prev_ref 94.5,漲停 = 94_500*11//10=103_950 貼 500 毫
    # tick = 103_500 = 收盤鎖板。還原漲幅 = 94.5/90 × 103.5/94.5 − 1 = +15.0%
    # (naive 103.5/100 = +3.5% 會漏掉 —— 這正是要還原的理由)
    days = _days(
        [_row("1234", 103.5, 9.0)],
        [_row("1234", 94.5, 4.5)],
        [_row("1234", 100.0, 0.0)],
    )
    got = hard_candidates(days)
    assert len(got) == 1
    assert round(got[0].ret_pct, 6) == 15.0
    assert got[0].lock_dates == (D0,)


def test_missing_day_excluded() -> None:
    """窗內缺日(新上市 / 停牌)不判。"""
    days = _days(
        [_row("1234", 116.0, 6.0)],
        [],  # D1 無此檔
        [_row("1234", 100.0, 0.0)],
    )
    assert hard_candidates(days) == []


def test_unusable_transition_row_excluded() -> None:
    """轉換日 spread 缺 / prev_ref <= 0 → 係數鏈斷,整檔不判。"""
    days = _days(
        [_row("1234", 116.0, 6.0)],
        [{"stock_id": "1234", "close": 110.0, "Trading_Volume": 5_000_000}],  # 無 spread
        [_row("1234", 100.0, 0.0)],
    )
    assert hard_candidates(days) == []
    days2 = _days(
        [_row("5678", 116.0, 6.0)],
        [_row("5678", 5.0, 5.0)],  # prev_ref = 0
        [_row("5678", 100.0, 0.0)],
    )
    assert hard_candidates(days2) == []


def test_universe_keeps_only_four_digit_ordinary_stocks() -> None:
    """ETF / 權證 / 指數 row 即使三條件全過也不得入榜。"""

    def trio(sid: str) -> list[list[dict]]:
        return [
            [_row(sid, 116.0, 6.0)],
            [_row(sid, 110.0, 10.0)],
            [_row(sid, 100.0, 0.0)],
        ]

    per_day: list[list[dict]] = [[], [], []]
    for sid in ("0050", "00679B", "030171", "001", "1234"):
        for i, rows in enumerate(trio(sid)):
            per_day[i].extend(rows)
    got = hard_candidates(_days(*per_day))
    assert [c.code for c in got] == ["1234"]


def test_sorting_recent_lock_first_then_return() -> None:
    # A/B 最近鎖板皆 D0:B 漲幅高 → B 前;C 漲幅最高但鎖板日較舊 → 殿後
    def stock(
        sid: str, d0_close: float, d0_spread: float, d1_close: float, d1_spread: float
    ) -> list[list[dict]]:
        return [
            [_row(sid, d0_close, d0_spread)],
            [_row(sid, d1_close, d1_spread)],
            [_row(sid, 100.0, 0.0)],
        ]

    per_day: list[list[dict]] = [[], [], []]
    # 1111: 100 → 105 → 115.5(D0 鎖板;prev_ref 105 漲停 115_500)= +15.5%
    # 2222: 100 → 110(D1 鎖板)→ 121(D0 也鎖板;prev_ref 110 漲停 121_000)= +21%
    # 3333: 100 → 110(D1 鎖板)→ 126.5(非鎖板)= +26.5%,最近鎖板日較舊
    for rows3 in (
        stock("1111", 115.5, 10.5, 105.0, 5.0),
        stock("2222", 121.0, 11.0, 110.0, 10.0),
        stock("3333", 126.5, 16.5, 110.0, 10.0),
    ):
        for i, rows in enumerate(rows3):
            per_day[i].extend(rows)
    got = hard_candidates(_days(*per_day))
    # 2222:D0 鎖板 +21%;1111:D0 鎖板 +15.5%;3333:最近鎖板 D1 → 殿後
    assert [c.code for c in got] == ["2222", "1111", "3333"]
    assert got[0].lock_dates[0] == D0
    assert got[2].lock_dates[0] == D1


def test_short_window_returns_empty() -> None:
    assert hard_candidates([]) == []
    assert hard_candidates([(D0, [_row("1234", 116.0, 6.0)])]) == []


# ---------------------------------------------------------------------------
# apply_eligibility —— 當沖資格 + 處置股過濾(保序)
# ---------------------------------------------------------------------------


def _cand(code: str) -> ScreenCandidate:
    return ScreenCandidate(code=code, ret_pct=20.0, avg_lots=9000.0, lock_dates=(D0,))


def test_apply_eligibility_filters_and_preserves_order() -> None:
    cands = [_cand("1111"), _cand("2222"), _cand("3333"), _cand("4444")]
    got = apply_eligibility(
        cands,
        daytrade_ok={"1111", "3333", "4444"},  # 2222 非當沖標的
        disposed={"4444"},  # 4444 處置中
    )
    assert [c.code for c in got] == ["1111", "3333"]


# ---------------------------------------------------------------------------
# expected_data_date —— 排程 / 補跑判定
# ---------------------------------------------------------------------------


def test_expected_data_date_flips_at_run_time_on_trading_day() -> None:
    assert RUN_TIME == _dt.time(21, 0)
    # 2026-08-31 = 週一(交易日):21:00 起 = 當日,之前 = 前一交易日(週五 08-28)
    assert expected_data_date(_dt.datetime(2026, 8, 31, 21, 0), WEEKEND_ONLY) == _dt.date(
        2026, 8, 31
    )
    assert expected_data_date(_dt.datetime(2026, 8, 31, 20, 59), WEEKEND_ONLY) == _dt.date(
        2026, 8, 28
    )


def test_expected_data_date_non_trading_day_ignores_clock() -> None:
    # 週六深夜也不會指到週六 —— 非交易日整天 = 前一交易日(週五)
    assert expected_data_date(_dt.datetime(2026, 8, 29, 23, 0), WEEKEND_ONLY) == _dt.date(
        2026, 8, 28
    )
    assert expected_data_date(_dt.datetime(2026, 8, 30, 8, 0), WEEKEND_ONLY) == _dt.date(
        2026, 8, 28
    )


# ---------------------------------------------------------------------------
# shrink_rows —— 記憶體縮列(對 hard_candidates 結果不變)
# ---------------------------------------------------------------------------


def test_shrink_rows_drops_non_universe_and_extra_fields() -> None:
    rows = [
        {**_row("1234", 116.0, 6.0), "open": 1.0, "max": 2.0, "Trading_money": 3.0},
        _row("0050", 116.0, 6.0),  # ETF
        _row("030171", 116.0, 6.0),  # 權證
    ]
    got = shrink_rows(rows)
    assert [r["stock_id"] for r in got] == ["1234"]
    assert set(got[0]) == {"stock_id", "close", "spread", "Trading_Volume"}


def test_shrink_rows_preserves_hard_candidates_result() -> None:
    per_day = [
        [_row("1234", 116.0, 6.0), _row("0050", 116.0, 6.0)],
        [_row("1234", 110.0, 10.0), _row("0050", 110.0, 10.0)],
        [_row("1234", 100.0, 0.0), _row("0050", 100.0, 0.0)],
    ]
    raw = hard_candidates(_days(*per_day))
    shrunk = hard_candidates(_days(*[shrink_rows(rows) for rows in per_day]))
    assert shrunk == raw
    assert [c.code for c in shrunk] == ["1234"]
