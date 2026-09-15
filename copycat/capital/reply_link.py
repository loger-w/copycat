"""回報線重連的純狀態機(零 IO、零時鐘讀取):退避表、排程去重、出手計數、恢復歸零、探針值分類。

IO 全留在 `CapitalClient`(`ConnectByID` / `store.clear()` / log / status 燈 / 幫浦圈節奏);這裡只回答
「該不該、等多久、這個探針值算什麼」。輸入一律由呼叫端把 `time.monotonic()` 傳進來,所以退避表、去重、
值域三態可以用純函式表驗(pr-review 253 F-10 抽出;client 端行為由 `tests/capital/test_reply_reconnect.py`
逐案 characterization 釘住,抽出前後零行為差)。

狀態機只認兩件事:`next_due`(下次 ConnectByID 到期,None = 未排)與 `attempts`(已出手次數,決定退避格)。
degraded / ok 那顆狀態燈**不在這裡** —— 它還要看開機 / error 等其他來源,留在 client。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: 回報線重連退避(秒):斷線後等第 0 格才第一次出手,之後每出手一次(不論 rc)等下一格,超出取最後一格
#: → 等待序列 5, 10, 20, 40, 60, 60, …。首格 5 s:2026-09-15 05:50 實錄裡 Discord 與 TC4 都在兩分鐘內
#: 自己回來,網路抖一下就立刻打 ConnectByID 只會在 SKCOM 還沒收拾好時再吃一次 3033;上限 60 s 與
#: balance 定時輪詢同節奏,回報線死一整夜也只是每分鐘一行 WARNING。
REPLY_RECONNECT_BACKOFF_SECS: tuple[float, ...] = (5.0, 10.0, 20.0, 40.0, 60.0)

ProbeVerdict = Literal["down", "up"]


def reconnect_delay(attempts_done: int) -> float:
    """已出手 `attempts_done` 次之後要等多久再打 ConnectByID(0 = 剛斷線、還沒出手)。"""
    idx = min(attempts_done, len(REPLY_RECONNECT_BACKOFF_SECS) - 1)
    return REPLY_RECONNECT_BACKOFF_SECS[idx]


def classify_probe(value: int) -> ProbeVerdict | None:
    """`IsConnectedByID` 原始 int 的三態:0 = 斷(`down`)、1 = 連(`up`)、其他(2026-09-15 23:59:56
    實錄首值 2 = 連線中)不動狀態(None)。守門寫成 `!= 1` 會把開機首值 2 判成斷線 →
    `store.clear()` + ConnectByID 迴圈 + degraded 假黃字(pr-review 253 F-05)。"""
    if value == 0:
        return "down"
    if value == 1:
        return "up"
    return None


@dataclass
class ReplyLink:
    """回報線重連排程。只在 COM 執行緒碰(與 client 的其他狀態同一條)。"""

    #: 下次 ConnectByID 到期(monotonic);None = 未排。與 client 同檔 `_balance_due` / `_pending_deadline`
    #: 同款哨兵語意。
    next_due: float | None = None
    #: 已出手次數(決定下一格退避;恢復 ok 時歸零)。
    attempts: int = 0

    def schedule(self, now: float) -> float | None:
        """排下一次 ConnectByID。已排(`next_due` 非 None)回 None —— 事件與探針都會叫進來,同一次斷線只排一次;
        新排回等待秒數(呼叫端拿去 log)。"""
        if self.next_due is not None:
            return None
        delay = reconnect_delay(self.attempts)
        self.next_due = now + delay
        return delay

    def due(self, now: float) -> bool:
        """退避到期(已排且 now ≥ next_due)。"""
        return self.next_due is not None and now >= self.next_due

    def begin_attempt(self, now: float) -> tuple[int, float]:
        """出手一次:計數 +1、排下一格。回 (第 n 次, 下一格秒數)。不論這次 rc 為何,下一格都已排好 ——
        rc=0 但線沒回來、rc≠0 都在同一條路上再試。"""
        self.attempts += 1
        delay = reconnect_delay(self.attempts)
        self.next_due = now + delay
        return self.attempts, delay

    def recovered(self) -> int:
        """回報線回來:清排程、計數歸零。回這一次斷線總共出手幾次(log 用)。"""
        attempts = self.attempts
        self.next_due = None
        self.attempts = 0
        return attempts
