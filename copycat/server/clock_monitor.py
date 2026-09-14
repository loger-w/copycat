"""時鐘偏差監測(#236):本機鐘 vs NTP,stdlib SNTP,只 log 不改任何判定。

盤中閘(`_in_session` 13:30 end-exclusive)、冷卻、推播窗 12:30、T+1 回填時點全走本機鐘,tick 時刻
走交易所鐘 —— 兩把尺的差就是**時鐘偏差**(本機 − NTP;負 = 本機落後)。2026-09-14 實測本機**超前**
2.6 s(17:32)→ 2.9 s(20:30),三小時漂 +0.24 s;W32Time Stopped / Manual;09-11 有 4 則 13:30:00 的 tick
穿過盤中閘(那天是落後)—— 方向會變、幅度秒級,都指向沒人校時。校時是 user 端動作(服務設
Automatic + 每小時輪詢),這裡只做「看」:每 `INTERVAL_SECS` 問一台 NTP,INFO 印 offset,超閾另印
WARNING / ERROR。閾值為常數不進 config:250 ms = 校時沒在跑,2 s = 已經會改變 gate 結果。

網路傳輸可注入(`exchange`),測試零網路;prod 由 app 用 `asyncio.to_thread` 跑同步 UDP,不佔 loop。
"""

from __future__ import annotations

import asyncio
import logging
import socket
import struct
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

logger = logging.getLogger(__name__)

NTP_HOSTS: tuple[str, ...] = ("time.google.com", "time.windows.com", "pool.ntp.org")
NTP_PORT: int = 123
INTERVAL_SECS: float = 600.0
TIMEOUT_SECS: float = 2.0
#: recv 緩衝:Winsock 對「datagram 比緩衝長」回 WSAEMSGSIZE(WinError 10040)**不截斷**,`recvfrom(48)`
#: 遇到帶認證欄(MAC)的 NTP 回應就整台恆失敗;三台公開伺服器實務上回 48,放大只是韌性,解析仍只看
#: 前 48(pr-238 review F-16)。
_RECV_BUF: int = 512
#: |offset| ≥ 此值印 WARNING:校時正常時 Windows 壓在 100 ms 內,250 ms 已是「校時沒在跑」
WARN_MS: float = 250.0
#: |offset| ≥ 此值印 ERROR:秒級偏差會改變 13:30 盤中閘 / 12:30 推播窗的事件集合
ERROR_MS: float = 2000.0
_NTP_EPOCH_OFFSET = 2_208_988_800  # 1900-01-01 → 1970-01-01 秒數
_REQUEST = b"\x1b" + 47 * b"\0"  # LI=0, VN=3, Mode=3(client)

Exchange = Callable[[str, bytes, float], tuple[float, bytes, float]]
"""(host, request, timeout_secs) → (t0, 回應 bytes(≥ 48), t3):t0 / t3 由傳輸層在**送出前 / 收到後**
當場取,DNS 解析那段不算進去(pr-238 review F-07:修前 t0 在進傳輸層之前取,冷 DNS 200 ms 全算成
去程 → offset 偏 −100 ms、RTT 膨脹 200 ms,而首發正是啟動當下最可能冷 DNS 的那一發);
拋 OSError = 這台失敗。"""


@dataclass(frozen=True)
class ClockSample:
    offset_ms: float  # 本機 − NTP;負 = 本機落後
    rtt_ms: float
    host: str


def _ntp_to_unix(secs: int, frac: int) -> float:
    return secs - _NTP_EPOCH_OFFSET + frac / 2**32


def parse_offset(response: bytes, t0: float, t3: float) -> tuple[float, float]:
    """SNTP 四時戳:t0 送出、t1 伺服器收到(bytes 32–40)、t2 伺服器送出(40–48)、t3 收到。
    回 (offset_s, rtt_s);offset = ((t1 − t0) + (t2 − t3)) / 2 = 伺服器 − 本機 的負號 → 這裡回本機 − 伺服器。"""
    if len(response) < 48:
        raise OSError(f"SNTP 回應長度 {len(response)} < 48")
    t1 = _ntp_to_unix(*struct.unpack("!II", response[32:40]))
    t2 = _ntp_to_unix(*struct.unpack("!II", response[40:48]))
    if t2 <= 0:
        raise OSError("SNTP 回應 transmit timestamp 為 0(Kiss-o'-Death?)")
    server_minus_local = ((t1 - t0) + (t2 - t3)) / 2
    rtt = (t3 - t0) - (t2 - t1)
    return -server_minus_local, rtt


def _udp_exchange(host: str, request: bytes, timeout: float) -> tuple[float, bytes, float]:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.connect((host, NTP_PORT))  # DNS 在這一步;t0 在它之後才取
        t0 = time.time()
        sock.send(request)
        data = sock.recv(_RECV_BUF)
        t3 = time.time()
    return t0, data, t3


def sntp_query(host: str, *, timeout: float = TIMEOUT_SECS, exchange: Exchange = _udp_exchange) -> ClockSample:
    """問一台;失敗拋 OSError(含 timeout)。"""
    t0, data, t3 = exchange(host, _REQUEST, timeout)
    offset_s, rtt_s = parse_offset(data, t0, t3)
    return ClockSample(offset_ms=offset_s * 1000, rtt_ms=rtt_s * 1000, host=host)


def probe(
    hosts: Sequence[str] = NTP_HOSTS,
    *,
    query: Callable[[str], ClockSample] = sntp_query,
) -> ClockSample | None:
    """依序問,第一台成功即回;全失敗回 None(呼叫端印一行 WARNING,不重試到下一輪)。"""
    for host in hosts:
        try:
            return query(host)
        except OSError as e:
            logger.debug("時鐘偏差:%s 失敗(%r),換下一台", host, e)
    return None


def level_for(offset_ms: float) -> int:
    """|offset| 對應的告警等級:< WARN_MS → INFO(只印量測行);≥ WARN_MS WARNING;≥ ERROR_MS ERROR。"""
    mag = abs(offset_ms)
    if mag >= ERROR_MS:
        return logging.ERROR
    if mag >= WARN_MS:
        return logging.WARNING
    return logging.INFO


def log_sample(sample: ClockSample | None) -> None:
    if sample is None:
        logger.warning("時鐘偏差量測失敗:%s 全部無回應(下一輪再試)", "、".join(NTP_HOSTS))
        return
    logger.info(
        "時鐘偏差:%+.0f ms(%s,RTT %.0f ms)", sample.offset_ms, sample.host, sample.rtt_ms
    )
    level = level_for(sample.offset_ms)
    if level > logging.INFO:
        direction = "落後" if sample.offset_ms < 0 else "超前"
        threshold = ERROR_MS if level == logging.ERROR else WARN_MS
        logger.log(
            level,
            "時鐘偏差 %.0f ms 超過 %.0f ms:本機鐘%s,校時服務可能沒在跑(W32Time 設 Automatic + w32tm /resync)",
            abs(sample.offset_ms),
            threshold,
            direction,
        )


async def run_clock_monitor(
    probe_fn: Callable[[], ClockSample | None] = probe,
    *,
    interval_secs: float = INTERVAL_SECS,
    sink: Callable[[ClockSample | None], None] | None = None,
) -> None:
    """啟動立即量一次,之後每 `interval_secs`;同步 UDP 走 `to_thread` 不佔 loop。
    `sink` 收每次結果(app.state 用);例外走 WARNING 不殺 task(它只是一則提示)。"""
    while True:
        try:
            sample = await asyncio.to_thread(probe_fn)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — 提示型 task,單輪例外不得殺掉整條監測
            logger.warning("時鐘偏差量測例外(略過本輪):%r", e)
            sample = None
        log_sample(sample)
        if sink is not None:
            sink(sample)
        await asyncio.sleep(interval_secs)
