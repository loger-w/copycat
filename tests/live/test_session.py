"""session_key / session_window:台股期權時段窗判定(UTC 基準)。

時區事實:日盤 台北 08:45–13:45 = UTC 00:45–05:45;夜盤 台北 15:00–次日 05:00
= UTC 同日 07:00–21:00(兩時段各自完整落在單一 UTC 日)。
"""

from __future__ import annotations

import datetime
import time

from copycat.live.session import backfill_window, in_txo_session, session_key, session_window


def _utc(y: int, mo: int, d: int, h: int, mi: int = 0) -> time.struct_time:
    return time.struct_time((y, mo, d, h, mi, 0, 0, 0, 0))


class TestSessionKey:
    def test_day_session_hours(self) -> None:
        # UTC 00:00 = 台北 08:00(開盤前空窗)→ 日盤
        assert session_key(_utc(2026, 7, 20, 0)) == ("20260720", "day")
        # UTC 01:00 = 台北 09:00(日盤中)
        assert session_key(_utc(2026, 7, 20, 1)) == ("20260720", "day")
        # UTC 06:59 = 台北 14:59(日盤剛收)→ 仍顯示日盤
        assert session_key(_utc(2026, 7, 20, 6, 59)) == ("20260720", "day")

    def test_night_session_hours(self) -> None:
        # UTC 07:00 = 台北 15:00(夜盤開)
        assert session_key(_utc(2026, 7, 20, 7)) == ("20260720", "night")
        # UTC 12:00 = 台北 20:00(夜盤中)
        assert session_key(_utc(2026, 7, 20, 12)) == ("20260720", "night")
        # UTC 20:59 = 台北 04:59 次日(夜盤尾段,仍屬同一 UTC 日)
        assert session_key(_utc(2026, 7, 20, 20, 59)) == ("20260720", "night")
        # UTC 21:00–23:59 = 台北 05:00–07:59(夜盤剛收)→ 仍顯示剛收的夜盤
        assert session_key(_utc(2026, 7, 20, 21)) == ("20260720", "night")
        assert session_key(_utc(2026, 7, 20, 23)) == ("20260720", "night")

    def test_defaults_to_current_utc(self) -> None:
        ymd, kind = session_key()
        assert ymd == time.strftime("%Y%m%d", time.gmtime())
        assert kind in ("day", "night")


class TestInTxoSession:
    """TXO session 的自癒閘(台北牆鐘):日盤 08:45–13:45 / 夜盤 15:00–次日 05:00。"""

    def test_day_session(self) -> None:
        assert in_txo_session(datetime.time(8, 45)) is True
        assert in_txo_session(datetime.time(13, 45)) is True

    def test_night_session_wraps_midnight(self) -> None:
        assert in_txo_session(datetime.time(15, 0)) is True
        assert in_txo_session(datetime.time(23, 30)) is True
        assert in_txo_session(datetime.time(0, 30)) is True
        assert in_txo_session(datetime.time(5, 0)) is True

    def test_closed_gaps(self) -> None:
        # 盤外不自癒:零推播是正常的,重掛只會 churn TC4 上游
        assert in_txo_session(datetime.time(8, 44)) is False
        assert in_txo_session(datetime.time(14, 30)) is False
        assert in_txo_session(datetime.time(5, 1)) is False

    def test_defaults_to_wall_clock(self) -> None:
        assert in_txo_session() in (True, False)


def test_in_txo_session_pad() -> None:
    """`pad` 把兩段各往外撐(期貨自癒閘用 5 分寬限,避免邊界誤關自癒)。"""
    pad = datetime.timedelta(minutes=5)
    assert in_txo_session(datetime.time(8, 39), pad=pad) is False
    assert in_txo_session(datetime.time(8, 40), pad=pad) is True
    assert in_txo_session(datetime.time(13, 50), pad=pad) is True
    assert in_txo_session(datetime.time(13, 51), pad=pad) is False
    assert in_txo_session(datetime.time(14, 54), pad=pad) is False
    assert in_txo_session(datetime.time(14, 55), pad=pad) is True
    assert in_txo_session(datetime.time(23, 59), pad=pad) is True
    assert in_txo_session(datetime.time(2, 0), pad=pad) is True
    assert in_txo_session(datetime.time(5, 5), pad=pad) is True
    assert in_txo_session(datetime.time(5, 6), pad=pad) is False


class TestSessionWindow:
    def test_day_window_matches_legacy(self) -> None:
        # 日盤窗與既有寫死窗完全一致(SC-4 日盤不變)
        assert session_window(("20260720", "day")) == ("2026072000", "2026072006")

    def test_night_window_has_margin(self) -> None:
        # 夜盤窗帶裕度 06–22(UTC 06–07 = 台北 14–15、21–22 = 台北 05–06 皆無成交,
        # 不依賴 TC4 窗邊界含斥語意)
        assert session_window(("20260720", "night")) == ("2026072006", "2026072022")


class TestBackfillWindow:
    """pr-167 F-04:回補窗唯一定義 —— ident = 窗本身之後,「ident 變 ⇔ 窗變」是定義。"""

    def test_fixed_env_beats_auto(self) -> None:
        assert backfill_window("20260814", "20260901", ("20260901", "day")) == (
            "2026081400",
            "2026081406",
        )

    def test_auto_fixed_day_equals_live_day_window(self) -> None:
        # 13:45–15:00 收盤段 auto 落定為今日:固定日窗與 live 日盤窗**字面相同**,
        # 13:46 那格不再觸發冗餘全鏈重交接(修前代理值 ident 在此變了、窗沒變)
        key = ("20260901", "day")
        assert backfill_window(None, "20260901", key) == session_window(key)

    def test_no_fixed_no_auto_falls_to_live_session_window(self) -> None:
        key = ("20260901", "night")
        assert backfill_window(None, None, key) == session_window(key)
