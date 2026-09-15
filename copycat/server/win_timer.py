"""Windows timer 解析度 1 ms + EcoQoS 豁免(perf #243;server 啟動最前呼叫一次)。

**兩行缺一不可**(T4 §2.1 實測):單獨 `timeBeginPeriod(1)` 在 Windows 11 約 3 秒後被 Power
Throttling(EcoQoS)收回,`asyncio.sleep` drift 退回 12.6 ms;先
`SetProcessInformation(ProcessPowerThrottling, IGNORE_TIMER_RESOLUTION)` 豁免才全程穩在 ~0.56 ms。
八種替代配方(`NtSetTimerResolution` 直呼、HIGH_PRIORITY_CLASS、常駐 high-resolution waitable timer
…)全部無效。

收益要誠實拆(T4 §2.2):timer 驅動步驟(逐筆打包 `call_later(0.1)`、五檔 flush、`_consume` 輪詢、
退避 `asyncio.sleep`)的尾巴從 ~14 ms 壓到 ~1.5 ms —— **盤外約 12 ms、盤中密集推播時約 2–3 ms**
(推播本身會把 loop 敲醒);`queue.get(timeout=)` 一族(群益 `_cmd_q`)不受益,下單路徑不在範圍。
0-7 `sys.setswitchinterval(0.001)` 的收益也掛在這上面:GIL 交棒等的是 condvar timeout,同吃
timer quantum,不豁免時 1 ms 與 5 ms 都被夾成 15.6 ms(批 B 本機實量 58 ms 零差異)。

ctypes 地雷(T4):`GetCurrentProcess()` 的偽 handle −1 不設 `restype` 會被截成 32-bit,
`SetProcessInformation` **靜默回 False** —— 兩個回傳值都檢查,失敗印 WARNING(含 GetLastError /
MMRESULT)不炸啟動;成功印 INFO 一行(盤後 `grep "timer 1 ms"` 是真環境判準)。
真判準走 `.claude/perf/batch-b-tier0/evidence/bench_03_timer_drift.py` 60 秒連量(量 3 秒會假 PASS)。
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable

logger = logging.getLogger(__name__)

__all__ = ["apply_timer_1ms"]

#: PROCESS_INFORMATION_CLASS.ProcessPowerThrottling(processthreadsapi.h)
_PROCESS_POWER_THROTTLING = 4
_PROCESS_POWER_THROTTLING_CURRENT_VERSION = 1
_PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1
_PROCESS_POWER_THROTTLING_IGNORE_TIMER_RESOLUTION = 0x4
#: winmm timeBeginPeriod 成功值(TIMERR_NOERROR)
_TIMERR_NOERROR = 0


def _qos_exempt() -> tuple[bool, int]:
    """`SetProcessInformation(ProcessPowerThrottling, ControlMask=EXECUTION_SPEED|IGNORE_TIMER_RESOLUTION,
    StateMask=0)`:ControlMask 列出要「由我們決定」的項目、StateMask=0 = 兩項都關(不節流、不忽略
    timer 請求)。回 (成功與否, GetLastError)。"""
    import ctypes
    import ctypes.wintypes as wt

    class _PowerThrottlingState(ctypes.Structure):
        _fields_ = [("Version", wt.ULONG), ("ControlMask", wt.ULONG), ("StateMask", wt.ULONG)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetCurrentProcess.restype = wt.HANDLE
    k32.SetProcessInformation.restype = wt.BOOL
    k32.SetProcessInformation.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD]
    state = _PowerThrottlingState(
        _PROCESS_POWER_THROTTLING_CURRENT_VERSION,
        _PROCESS_POWER_THROTTLING_EXECUTION_SPEED
        | _PROCESS_POWER_THROTTLING_IGNORE_TIMER_RESOLUTION,
        0,
    )
    ok = bool(
        k32.SetProcessInformation(
            k32.GetCurrentProcess(),
            _PROCESS_POWER_THROTTLING,
            ctypes.byref(state),
            ctypes.sizeof(state),
        )
    )
    return ok, (0 if ok else ctypes.get_last_error())


def _time_begin_period() -> int:
    """`winmm.timeBeginPeriod(1)`;回 MMRESULT(0 = TIMERR_NOERROR)。程序結束時 OS 自動歸還,不另
    `timeEndPeriod`(server 常駐,整個生命週期都要 1 ms)。"""
    import ctypes

    winmm = ctypes.WinDLL("winmm")
    winmm.timeBeginPeriod.restype = ctypes.c_uint
    winmm.timeBeginPeriod.argtypes = [ctypes.c_uint]
    return int(winmm.timeBeginPeriod(1))


def apply_timer_1ms(
    *,
    qos_fn: Callable[[], tuple[bool, int]] = _qos_exempt,
    tbp_fn: Callable[[], int] = _time_begin_period,
    platform: str = sys.platform,
) -> bool:
    """先豁免 EcoQoS、再要 1 ms timer;回「兩步都成功」。非 Windows no-op(回 False,INFO 一行)。

    豁免失敗仍照要 timer(無害,而且前 3 秒還是好的),但 WARNING 講清楚後果:約 3 秒後會被收回,
    盤後 drift 判準會退回 12 ms。任一失敗都不拋 —— 這是效能項不是正確性項,server 照起。
    """
    if platform != "win32":
        logger.info("timer 1 ms:非 Windows(%s),不套用", platform)
        return False
    try:
        qos_ok, err = qos_fn()
    except (OSError, AttributeError) as exc:
        # DLL 載不到 / 匯出不存在(pr-251 review F-06):與回傳 False 同歸「失敗」,不讓效能項炸掉啟動
        logger.warning("EcoQoS 豁免呼叫失敗(%s: %s):視同未豁免", type(exc).__name__, exc)
        qos_ok, err = False, -1
    if not qos_ok:
        logger.warning(
            "EcoQoS 豁免失敗(SetProcessInformation ProcessPowerThrottling 回 False,GetLastError=%d):"
            "timeBeginPeriod(1) 仍會要,但 Windows 11 約 3 秒後收回,timer drift 退回 ~12 ms",
            err,
        )
    try:
        mm = tbp_fn()
    except (OSError, AttributeError) as exc:
        logger.warning("timeBeginPeriod 呼叫失敗(%s: %s):視同未套用", type(exc).__name__, exc)
        mm = -1
    if mm != _TIMERR_NOERROR:
        logger.warning("timeBeginPeriod(1) 失敗(MMRESULT=%d):timer 解析度維持系統預設 15.6 ms", mm)
    ok = qos_ok and mm == _TIMERR_NOERROR
    if ok:
        logger.info("timer 1 ms 已套用(EcoQoS 豁免 + timeBeginPeriod)")
    return ok
