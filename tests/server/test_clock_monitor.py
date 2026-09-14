"""時鐘偏差監測(#236):假 SNTP 回應 bytes 進、offset 出;閾值三案;三台全失敗案;監測 loop。

期望值來自獨立的手算(不是照 code 重算):伺服器兩個時戳都比本機**快 2.6 s**、往返 6 ms →
offset = −2600 ms、RTT = 6 ms(本機落後為負);2026-09-14 對 time.google.com 的實測是反向的
+2627 ms(17:32)→ +2861 ms(20:30),本機**超前**且三小時漂 +0.24 s,量級相同、符號相反。
"""

from __future__ import annotations

import asyncio
import logging
import struct
from pathlib import Path

import pytest

from copycat.server import clock_monitor as cm
from copycat.server.clock_monitor import (
    ERROR_MS,
    WARN_MS,
    ClockSample,
    level_for,
    log_sample,
    parse_offset,
    probe,
    run_clock_monitor,
    sntp_query,
)

_NTP_EPOCH = 2_208_988_800


def _ts(unix: float) -> bytes:
    secs = int(unix) + _NTP_EPOCH
    frac = int((unix - int(unix)) * 2**32)
    return struct.pack("!II", secs, frac)


def _response(t1: float, t2: float) -> bytes:
    """48-byte SNTP 回應:只填 receive(32–40)與 transmit(40–48)兩個時戳。"""
    return b"\x24" + b"\0" * 31 + _ts(t1) + _ts(t2)


class TestParseOffset:
    def test_server_ahead_by_2600ms(self) -> None:
        t0 = 1_800_000_000.000
        t3 = t0 + 0.006  # 往返 6 ms
        # 伺服器鐘快 2.6 s:收到 = t0 + 2.6 + 單程 3 ms;送出 = 再過 0 ms
        t1 = t0 + 2.6 + 0.003
        t2 = t1
        offset_s, rtt_s = parse_offset(_response(t1, t2), t0, t3)
        assert offset_s == pytest.approx(-2.6, abs=1e-6)  # 本機落後 = 負
        assert rtt_s == pytest.approx(0.006, abs=1e-6)

    def test_local_ahead_is_positive(self) -> None:
        t0 = 1_800_000_000.0
        t3 = t0 + 0.010
        t1 = t2 = t0 - 0.5 + 0.005  # 伺服器慢 0.5 s
        offset_s, _rtt = parse_offset(_response(t1, t2), t0, t3)
        assert offset_s == pytest.approx(0.5, abs=1e-6)

    def test_short_or_kod_response_raises_oserror(self) -> None:
        with pytest.raises(OSError):
            parse_offset(b"\0" * 40, 0.0, 0.0)
        with pytest.raises(OSError):
            parse_offset(b"\0" * 48, 0.0, 0.0)  # transmit = 0


class TestLevels:
    @pytest.mark.parametrize(
        ("offset_ms", "level"),
        [
            (0.0, logging.INFO),
            (249.0, logging.INFO),
            (-249.0, logging.INFO),
            (WARN_MS, logging.WARNING),
            (-1999.0, logging.WARNING),
            (ERROR_MS, logging.ERROR),
            (-2624.0, logging.ERROR),
        ],
    )
    def test_thresholds(self, offset_ms: float, level: int) -> None:
        assert level_for(offset_ms) == level


class TestProbeFallback:
    def test_first_host_fails_second_wins(self) -> None:
        calls: list[str] = []

        def query(host: str) -> ClockSample:
            calls.append(host)
            if host == "a":
                raise OSError("timeout")
            return ClockSample(offset_ms=-10.0, rtt_ms=5.0, host=host)

        s = probe(("a", "b", "c"), query=query)
        assert s is not None and s.host == "b"
        assert calls == ["a", "b"]  # 第一台成功即停

    def test_all_fail_returns_none(self) -> None:
        def query(host: str) -> ClockSample:
            raise OSError("timeout")

        assert probe(("a", "b"), query=query) is None


class TestSntpQueryWithInjectedExchange:
    def test_uses_exchange_and_reports_host(self) -> None:
        seen: list[tuple[str, int, float]] = []

        def exchange(host: str, request: bytes, timeout: float) -> bytes:
            seen.append((host, len(request), timeout))
            import time

            now = time.time()
            return _response(now + 1.0, now + 1.0)  # 伺服器快 1 s

        s = sntp_query("x.example", timeout=1.5, exchange=exchange)
        assert seen == [("x.example", 48, 1.5)]
        assert s.host == "x.example"
        assert s.offset_ms == pytest.approx(-1000.0, abs=50.0)


class TestLogLines:
    def test_info_only_when_within_warn(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO, logger=cm.__name__)
        log_sample(ClockSample(offset_ms=-42.4, rtt_ms=6.4, host="time.google.com"))
        lines = [(r.levelno, r.getMessage()) for r in caplog.records]
        assert lines == [(logging.INFO, "時鐘偏差:-42 ms(time.google.com,RTT 6 ms)")]

    def test_error_line_names_direction_and_threshold(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO, logger=cm.__name__)
        log_sample(ClockSample(offset_ms=-2624.5, rtt_ms=66.0, host="time.windows.com"))
        levels = [r.levelno for r in caplog.records]
        assert levels == [logging.INFO, logging.ERROR]
        msg = caplog.records[1].getMessage()
        assert msg.startswith("時鐘偏差 2624 ms 超過 2000 ms:本機鐘落後")
        assert "校時服務可能沒在跑" in msg

    def test_warning_line_for_ahead(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO, logger=cm.__name__)
        log_sample(ClockSample(offset_ms=300.0, rtt_ms=6.0, host="h"))
        assert caplog.records[1].levelno == logging.WARNING
        assert "超過 250 ms:本機鐘超前" in caplog.records[1].getMessage()

    def test_all_hosts_failed_is_one_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO, logger=cm.__name__)
        log_sample(None)
        assert [
            (r.levelno, r.getMessage().startswith("時鐘偏差量測失敗")) for r in caplog.records
        ] == [(logging.WARNING, True)]


class TestMonitorLoop:
    async def test_probes_immediately_then_every_interval_and_feeds_sink(self) -> None:
        samples = [ClockSample(-2600.0, 6.0, "a"), None, ClockSample(-10.0, 6.0, "b")]
        got: list[ClockSample | None] = []

        def probe_fn() -> ClockSample | None:
            return samples[min(len(got), len(samples) - 1)]

        task = asyncio.create_task(run_clock_monitor(probe_fn, interval_secs=0.01, sink=got.append))
        for _ in range(200):
            if len(got) >= 3:
                break
            await asyncio.sleep(0.005)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert got[:3] == samples

    async def test_probe_exception_does_not_kill_loop(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING, logger=cm.__name__)
        n = {"calls": 0}

        def probe_fn() -> ClockSample | None:
            n["calls"] += 1
            if n["calls"] == 1:
                raise RuntimeError("dns 炸了")
            return ClockSample(-1.0, 1.0, "h")

        got: list[ClockSample | None] = []
        task = asyncio.create_task(run_clock_monitor(probe_fn, interval_secs=0.01, sink=got.append))
        for _ in range(200):
            if len(got) >= 2:
                break
            await asyncio.sleep(0.005)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert got[0] is None and got[1] is not None
        assert any("時鐘偏差量測例外" in r.getMessage() for r in caplog.records)


def test_thresholds_documented_in_claude_md() -> None:
    """閾值是契約的一半(另一半是 user 校時動作):CLAUDE.md 寫的數字要與常數同值。"""
    text = (Path(__file__).resolve().parents[2] / "CLAUDE.md").read_text(encoding="utf-8")
    assert f"{int(WARN_MS)} ms WARNING" in text and f"{int(ERROR_MS / 1000)} s ERROR" in text
