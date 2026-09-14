"""`win_timer.apply_timer_1ms`(perf #243):EcoQoS 豁免 + timeBeginPeriod(1) 兩行缺一不可,回傳值都要查。

T4 §2.1:單獨 `timeBeginPeriod(1)` 在 Windows 11 約 3 秒後被 Power Throttling 收回(12.6 ms);
先 `SetProcessInformation(ProcessPowerThrottling, IGNORE_TIMER_RESOLUTION)` 才穩在 0.556 ms。
ctypes 呼叫沒設 restype / argtypes 時 `SetProcessInformation` 會**靜默回 False**,所以這裡的
契約是「兩個回傳值都檢查、失敗一律印 WARNING(含錯誤碼)不炸啟動、成功印 INFO 一行」。
真判準(timer drift 60 秒 p50 < 1 ms)走 `.claude/perf/batch-b-tier0/evidence/bench_03_timer_drift.py`。
"""

from __future__ import annotations

import logging
import sys

import pytest

from copycat.server import win_timer


def test_both_ok_logs_info_and_returns_true(caplog: pytest.LogCaptureFixture) -> None:
    calls: list[str] = []

    def qos() -> tuple[bool, int]:
        calls.append("qos")
        return True, 0

    def tbp() -> int:
        calls.append("tbp")
        return 0

    with caplog.at_level(logging.INFO, logger="copycat.server.win_timer"):
        ok = win_timer.apply_timer_1ms(qos_fn=qos, tbp_fn=tbp, platform="win32")

    assert ok is True
    assert calls == ["qos", "tbp"]  # 順序:先豁免再要 1 ms(反過來前三秒會假 PASS)
    assert [r.levelname for r in caplog.records] == ["INFO"]
    assert "timer 1 ms 已套用" in caplog.records[0].getMessage()


def test_qos_failure_warns_with_error_code_and_still_requests_timer(
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[str] = []

    def qos() -> tuple[bool, int]:
        calls.append("qos")
        return False, 87  # ERROR_INVALID_PARAMETER

    def tbp() -> int:
        calls.append("tbp")
        return 0

    with caplog.at_level(logging.INFO, logger="copycat.server.win_timer"):
        ok = win_timer.apply_timer_1ms(qos_fn=qos, tbp_fn=tbp, platform="win32")

    assert ok is False
    assert calls == ["qos", "tbp"]
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    msg = warnings[0].getMessage()
    assert "EcoQoS 豁免失敗" in msg and "87" in msg
    assert "3 秒" in msg  # 講清楚後果:timeBeginPeriod 會被收回


def test_tbp_failure_warns(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="copycat.server.win_timer"):
        ok = win_timer.apply_timer_1ms(
            qos_fn=lambda: (True, 0), tbp_fn=lambda: 97, platform="win32"
        )  # TIMERR_NOCANDO

    assert ok is False
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1 and "timeBeginPeriod(1) 失敗" in warnings[0].getMessage()
    assert "97" in warnings[0].getMessage()


def test_non_windows_is_a_noop(caplog: pytest.LogCaptureFixture) -> None:
    def boom() -> tuple[bool, int]:
        raise AssertionError("非 Windows 不得碰 Win32 API")

    with caplog.at_level(logging.INFO, logger="copycat.server.win_timer"):
        ok = win_timer.apply_timer_1ms(qos_fn=boom, tbp_fn=lambda: 0, platform="linux")

    assert ok is False
    assert [r.levelname for r in caplog.records] == ["INFO"]


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 API smoke,只在 Windows 跑")
def test_default_fns_are_the_win32_wrappers() -> None:
    """預設走真 ctypes 包裝(不是 stub);在 Windows 上實際呼叫一次應該成功 —— 這是本機
    (Windows 11)的 smoke,也是 T4「沒設 restype 靜默回 False」那顆地雷的守門。
    佈線測試(test_main_wiring)刻意用替身,這裡是唯一真呼叫的地方:timeBeginPeriod 用完立刻
    timeEndPeriod 歸還,不讓 pytest 進程剩下的時間帶著 1 ms timer(EcoQoS 豁免無需歸還)。"""
    import ctypes

    ok, err = win_timer._qos_exempt()
    assert ok is True, f"SetProcessInformation 回 False,GetLastError={err}"
    try:
        assert win_timer._time_begin_period() == 0
    finally:
        ctypes.WinDLL("winmm").timeEndPeriod(1)
