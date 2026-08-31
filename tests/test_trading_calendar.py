"""交易日曆純模組(mod/trading-calendar SC-1)。

三塊契約:(1) 純判定 `is_trading_day` / `last_trading_day` 不碰 IO;
(2) `load_trading_calendar` 檔缺 = 只擋週末 + WARNING、壞檔 raise(對齊
`signals_config` 慣例);(3) 版控 `configs/trading_holidays.json` 的資料本身
(2026 平日休市 18 天)也被鎖住 —— 假日清單漂掉是零錯誤訊號的靜默故障。
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
from datetime import date, timedelta
from pathlib import Path

import pytest

from copycat.trading_calendar import (
    DEFAULT_PATH,
    WEEKEND_ONLY,
    TradingCalendar,
    _reset_year_warnings,
    load_trading_calendar,
    resolve_trade_date,
    resolve_trade_date_before,
    warn_if_year_missing,
)


@pytest.fixture(autouse=True)
def _clear_year_warnings() -> None:
    """節流狀態是 module-level,測試間必須清乾淨。"""
    _reset_year_warnings()


def _cal(
    holidays: list[str] | None = None,
    extra: list[str] | None = None,
    years: list[int] | None = None,
) -> TradingCalendar:
    return TradingCalendar(
        holidays=frozenset(date.fromisoformat(s) for s in holidays or []),
        extra_trading_days=frozenset(date.fromisoformat(s) for s in extra or []),
        years_loaded=frozenset(years or []),
    )


# --- is_trading_day ---------------------------------------------------------


def test_is_trading_day_weekday() -> None:
    assert _cal().is_trading_day(date(2026, 8, 14)) is True  # 週五


def test_is_trading_day_weekend() -> None:
    cal = _cal()
    assert cal.is_trading_day(date(2026, 8, 15)) is False  # 週六
    assert cal.is_trading_day(date(2026, 8, 16)) is False  # 週日


def test_is_trading_day_holiday_weekday() -> None:
    cal = _cal(holidays=["2026-10-09"])
    assert cal.is_trading_day(date(2026, 10, 9)) is False


def test_is_trading_day_extra_trading_day_saturday() -> None:
    """補班交易日:週六但有交易(2026 無,模組先支援)。"""
    cal = _cal(extra=["2026-08-15"])
    assert cal.is_trading_day(date(2026, 8, 15)) is True


# --- last_trading_day -------------------------------------------------------


def test_last_trading_day_returns_self_when_trading() -> None:
    assert _cal().last_trading_day(date(2026, 8, 14)) == date(2026, 8, 14)


def test_last_trading_day_sunday_walks_back_to_friday() -> None:
    assert _cal().last_trading_day(date(2026, 8, 16)) == date(2026, 8, 14)


def test_last_trading_day_across_lunar_new_year() -> None:
    """連假(02-12 四 ~ 02-22 日)任一天 → 02-11(用版控真日曆)。"""
    cal = load_trading_calendar()
    assert cal.last_trading_day(date(2026, 2, 22)) == date(2026, 2, 11)


def test_last_trading_day_monday_after_lunar_new_year_is_self() -> None:
    cal = load_trading_calendar()
    assert cal.last_trading_day(date(2026, 2, 23)) == date(2026, 2, 23)


def test_last_trading_day_raises_when_no_trading_day_within_bound() -> None:
    """全休的假日曆 = 資料錯,寧可炸也不要無窮迴圈。"""
    start = date(2026, 1, 1)
    cal = _cal(holidays=[(start - timedelta(days=i)).isoformat() for i in range(90)])
    with pytest.raises(RuntimeError):
        cal.last_trading_day(start)


# --- 版控 config 的資料本身 --------------------------------------------------


def test_real_config_shape() -> None:
    cal = load_trading_calendar()
    assert cal.years_loaded == frozenset({2026})
    assert cal.has_year(2026) is True
    assert cal.has_year(2027) is False
    assert len([d for d in cal.holidays if d.year == 2026]) == 18
    assert cal.extra_trading_days == frozenset()


def test_real_config_has_no_weekend_holidays() -> None:
    """週末本來就不開盤,清單塞週末 = 抄錯來源。"""
    cal = load_trading_calendar()
    assert [d for d in sorted(cal.holidays) if d.weekday() >= 5] == []


@pytest.mark.parametrize(
    ("day", "trading"),
    [
        (date(2026, 1, 1), False),  # 元旦
        (date(2026, 2, 16), False),  # 春節
        (date(2026, 10, 9), False),  # 國慶補假
        (date(2026, 8, 14), True),  # 平常週五
    ],
)
def test_real_config_samples(day: date, trading: bool) -> None:
    assert load_trading_calendar().is_trading_day(day) is trading


def test_default_path_points_at_versioned_config() -> None:
    assert DEFAULT_PATH.name == "trading_holidays.json"
    assert DEFAULT_PATH.exists()


# --- load:檔缺 / 壞檔 -------------------------------------------------------


def test_load_missing_file_returns_weekend_only_with_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="copycat.trading_calendar"):
        cal = load_trading_calendar(tmp_path / "nope.json")
    assert cal == WEEKEND_ONLY
    assert cal.holidays == frozenset()
    assert cal.years_loaded == frozenset()
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.WARNING


def test_weekend_only_still_blocks_weekend() -> None:
    assert WEEKEND_ONLY.is_trading_day(date(2026, 8, 15)) is False
    assert WEEKEND_ONLY.is_trading_day(date(2026, 10, 9)) is True  # 沒日曆就不多擋


def test_load_malformed_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        load_trading_calendar(path)
    assert str(path) in str(exc.value)


@pytest.mark.parametrize(
    "payload",
    [
        {"years": []},  # years 不是 dict
        {"years": {"2026": ["2026-01-01"]}},  # 年份值不是 dict
        {"years": {"twenty": {"holidays": []}}},  # 年份鍵不是數字
        {"years": {"2026": {"holidays": "2026-01-01"}}},  # holidays 不是 list
        {"years": {"2026": {"holidays": [20260101]}}},  # 元素不是字串
        {"years": {"2026": {"holidays": ["2026-13-01"]}}},  # 日期無效
        {"years": {"2026": {"holidays": [], "extra_trading_days": "x"}}},
    ],
    ids=[
        "years-list",
        "year-list",
        "year-key",
        "holidays-str",
        "elem-int",
        "bad-date",
        "extra-str",
    ],
)
def test_load_wrong_shape_raises(tmp_path: Path, payload: dict[str, object]) -> None:
    path = tmp_path / "shape.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        load_trading_calendar(path)
    assert str(path) in str(exc.value)


def test_load_conflicting_day_raises(tmp_path: Path) -> None:
    """同一天同時掛 holidays 與 extra_trading_days = 資料矛盾,不能靜默挑一邊(C4)。

    `is_trading_day` 讓 `extra_trading_days` 優先 —— 撞在一起就是「休市日被判成
    交易日」,而那是零訊號的:畫面照常、只是那天沒資料。
    """
    path = tmp_path / "conflict.json"
    path.write_text(
        json.dumps(
            {
                "years": {
                    "2026": {
                        "holidays": ["2026-01-01", "2026-10-09"],
                        "extra_trading_days": ["2026-10-09"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as exc:
        load_trading_calendar(path)
    assert "2026-10-09" in str(exc.value)
    assert str(path) in str(exc.value)


def test_load_year_mismatch_raises(tmp_path: Path) -> None:
    """年份鍵下掛別年的日期 = 抄錯 / 貼錯格(C4)。

    2027 的假日被塞進 2026 那格時 `years_loaded` 仍是 {2026} → 缺年 WARNING 照樣會叫,
    但那些日期已經默默生效了,兩個訊號互相打架。
    """
    path = tmp_path / "mismatch.json"
    path.write_text(
        json.dumps({"years": {"2026": {"holidays": ["2026-01-01", "2027-01-01"]}}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as exc:
        load_trading_calendar(path)
    assert "2027-01-01" in str(exc.value)
    assert str(path) in str(exc.value)


def test_load_missing_years_key_raises(tmp_path: Path) -> None:
    path = tmp_path / "noyears.json"
    path.write_text(json.dumps({"_updated": "2026-08-16"}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_trading_calendar(path)


# --- 缺年 WARNING 節流 ------------------------------------------------------


def test_warn_if_year_missing_throttles_per_year(caplog: pytest.LogCaptureFixture) -> None:
    cal = load_trading_calendar()
    with caplog.at_level(logging.WARNING, logger="copycat.trading_calendar"):
        warn_if_year_missing(cal, date(2027, 1, 4))
        assert len(caplog.records) == 1
        warn_if_year_missing(cal, date(2027, 6, 30))  # 同年 → 不再叫
        assert len(caplog.records) == 1
        warn_if_year_missing(cal, date(2028, 1, 3))  # 跨年 → 再叫一次
        assert len(caplog.records) == 2


def test_warn_if_year_missing_silent_when_year_loaded(caplog: pytest.LogCaptureFixture) -> None:
    cal = load_trading_calendar()
    with caplog.at_level(logging.WARNING, logger="copycat.trading_calendar"):
        warn_if_year_missing(cal, date(2026, 8, 16))
    assert caplog.records == []


# --- resolve_trade_date -----------------------------------------------------


def test_resolve_trade_date_returns_last_trading_day() -> None:
    cal = load_trading_calendar()
    assert resolve_trade_date(date(2026, 8, 16), cal) == date(2026, 8, 14)
    assert resolve_trade_date(date(2026, 8, 14), cal) == date(2026, 8, 14)


def test_resolve_trade_date_warns_on_missing_year(caplog: pytest.LogCaptureFixture) -> None:
    cal = load_trading_calendar()
    with caplog.at_level(logging.WARNING, logger="copycat.trading_calendar"):
        # 2027-01-02 = 週六 → 只擋週末回 01-01(週五);日曆缺 2027 故 WARNING
        assert resolve_trade_date(date(2027, 1, 2), cal) == date(2027, 1, 1)
    assert len(caplog.records) == 1


# --- next_trading_day(N075:夜盤所屬交易日)---------------------------------


def test_next_trading_day_returns_self_when_trading() -> None:
    assert _cal().next_trading_day(date(2026, 8, 14)) == date(2026, 8, 14)


def test_next_trading_day_saturday_walks_forward_to_monday() -> None:
    """週五 15:00 開的夜盤屬於下週一那個交易日 —— 往前走,不是往回走。"""
    assert _cal().next_trading_day(date(2026, 8, 15)) == date(2026, 8, 17)


def test_next_trading_day_across_lunar_new_year() -> None:
    cal = _cal(holidays=[f"2026-02-{d:02d}" for d in range(12, 21)])
    assert cal.next_trading_day(date(2026, 2, 12)) == date(2026, 2, 23)


def test_next_trading_day_honours_extra_trading_day() -> None:
    """補班日優先於週末規則(與 `is_trading_day` 同一條)。"""
    cal = _cal(extra=["2026-08-15"])
    assert cal.next_trading_day(date(2026, 8, 15)) == date(2026, 8, 15)


def test_next_trading_day_raises_when_calendar_is_broken() -> None:
    """保險絲與 `last_trading_day` 同一條:資料錯掉要炸,不要無窮迴圈。"""
    cal = _cal(holidays=[(date(2026, 8, 17) + timedelta(days=i)).isoformat() for i in range(90)])
    with pytest.raises(RuntimeError):
        cal.next_trading_day(date(2026, 8, 17))
def test_warn_if_year_missing_is_atomic_across_threads(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """N033(review C-3):`year in _warned_years` 與 `_warned_years.add(year)` 之間是
    check-then-act,而這支是從**多條執行緒**進來的(`resolve_trade_date` 走 to_thread
    的各條路徑 + 引擎自己的 worker)。節流因此不保證,失效樣態是 log 裡同一年重複幾行
    —— 無害但會讓「這行只該出現一次」這個判準不可用。

    治具把窗放大到 50 ms:沒有鎖時四條執行緒必然全部通過 check。
    """
    import threading
    import time

    import copycat.trading_calendar as cal_mod

    class _SlowSet(set):
        def __contains__(self, item: object) -> bool:
            # 先算答案**再**睡:睡在前面等於把答案延後到別人 add 完之後才取,
            # 治具自己就把競賽消掉了(而測試照樣綠)。
            answer = super().__contains__(item)
            time.sleep(0.05)
            return answer

    monkeypatch.setattr(cal_mod, "_warned_years", _SlowSet())
    cal = load_trading_calendar()
    with caplog.at_level(logging.WARNING, logger="copycat.trading_calendar"):
        threads = [
            threading.Thread(target=warn_if_year_missing, args=(cal, date(2031, 1, 6)))
            for _ in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
    assert len(caplog.records) == 1


class TestResolveTradeDateBefore:
    """L77 盤前冷啟動:交易日 stage 時刻前 = 前一交易日;其餘同 resolve_trade_date。"""

    def test_trading_day_before_stage_uses_previous_trading_day(self) -> None:
        cal = _cal()  # 預設只擋週末
        # 2026-08-17(一)07:30,stage 08:00 → 前一交易日 = 08-14(五)
        now = _dt.datetime(2026, 8, 17, 7, 30)
        assert resolve_trade_date_before(now, cal, _dt.time(8, 0)) == _dt.date(2026, 8, 14)

    def test_trading_day_at_or_after_stage_is_same_day(self) -> None:
        cal = _cal()
        assert resolve_trade_date_before(
            _dt.datetime(2026, 8, 17, 8, 0), cal, _dt.time(8, 0)
        ) == _dt.date(2026, 8, 17)
        assert resolve_trade_date_before(
            _dt.datetime(2026, 8, 17, 12, 0), cal, _dt.time(8, 0)
        ) == _dt.date(2026, 8, 17)

    def test_non_trading_day_ignores_stage(self) -> None:
        cal = _cal()
        # 週六不論幾點都是最近交易日(五);stage 只對「今天是交易日」有意義
        for hh in (7, 12):
            assert resolve_trade_date_before(
                _dt.datetime(2026, 8, 15, hh, 0), cal, _dt.time(8, 0)
            ) == _dt.date(2026, 8, 14)

    def test_stage_boundary_per_face(self) -> None:
        """index 面 08:30 vs stock 面 08:00:同一時刻(08:15)兩面答案不同 —— 各沿自家 stage。"""
        cal = _cal()
        now = _dt.datetime(2026, 8, 17, 8, 15)
        assert resolve_trade_date_before(now, cal, _dt.time(8, 0)) == _dt.date(2026, 8, 17)
        assert resolve_trade_date_before(now, cal, _dt.time(8, 30)) == _dt.date(2026, 8, 14)
