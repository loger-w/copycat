"""MIS 櫃買快照 fetch/解析測試 — index-board SC-4."""

from __future__ import annotations

import io
import json
import logging
import urllib.error
from typing import Any

import pytest

import copycat.server.mis as mis
from copycat.server.mis import fetch_otc_snapshot

# 2026-07-28 盤中實測樣本(節錄)
SAMPLE = {
    "msgArray": [
        {
            "c": "o00",
            "n": "櫃買指數",
            "z": "359.80",
            "y": "378.09",
            "o": "373.42",
            "h": "373.42",
            "l": "358.43",
            "t": "10:16:10",
            "ex": "otc",
        }
    ],
    "rtcode": "0000",
    "rtmessage": "OK",
}


def _fake_fetcher(payload: dict) -> Any:
    def fetcher(req: Any, timeout: float = 0.0) -> io.BytesIO:
        return io.BytesIO(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    return fetcher


class TestFetchOtcSnapshot:
    def test_parses_millipts(self) -> None:
        snap = fetch_otc_snapshot(fetcher=_fake_fetcher(SAMPLE))
        assert snap == {
            "p": 359_800,
            "ref": 378_090,
            "open": 373_420,
            "high": 373_420,
            "low": 358_430,
            "time": "101610",
        }

    def test_no_trade_value_returns_none(self) -> None:
        payload = {**SAMPLE, "msgArray": [{**SAMPLE["msgArray"][0], "z": "-"}]}
        assert fetch_otc_snapshot(fetcher=_fake_fetcher(payload)) is None

    def test_bad_rtcode_returns_none(self) -> None:
        assert fetch_otc_snapshot(fetcher=_fake_fetcher({**SAMPLE, "rtcode": "9999"})) is None

    def test_dash_field_value_error_swallowed(self) -> None:
        """o/h/l/y 任一欄 '-' → float 炸 ValueError → None 不外溢(design R8)."""
        payload = {**SAMPLE, "msgArray": [{**SAMPLE["msgArray"][0], "o": "-"}]}
        assert fetch_otc_snapshot(fetcher=_fake_fetcher(payload)) is None

    def test_empty_msg_array_returns_none(self) -> None:
        assert fetch_otc_snapshot(fetcher=_fake_fetcher({**SAMPLE, "msgArray": []})) is None

    def test_network_error_returns_none(self) -> None:
        def boom(req: Any, timeout: float = 0.0) -> io.BytesIO:
            raise urllib.error.URLError("down")

        assert fetch_otc_snapshot(fetcher=boom) is None

    def test_timeout_error_returns_none(self) -> None:
        def boom(req: Any, timeout: float = 0.0) -> io.BytesIO:
            raise TimeoutError("ssl read timeout")

        assert fetch_otc_snapshot(fetcher=boom) is None


def _boom(req: Any, timeout: float = 0.0) -> io.BytesIO:
    raise TimeoutError("read timed out")


class TestFailureLogEscalation:
    """偶發 timeout 降噪:單次失敗 debug,連續 _WARN_AFTER 次起才 warning,成功歸零."""

    @pytest.fixture(autouse=True)
    def _reset_streak(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(mis, "_fail_streak", 0, raising=False)

    def _fail_levels(self, caplog: pytest.LogCaptureFixture) -> list[int]:
        return [
            r.levelno for r in caplog.records if "快照失敗" in r.getMessage()
        ]

    def test_single_failure_logs_debug_not_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG, logger="copycat.server.mis"):
            fetch_otc_snapshot(fetcher=_boom)
        assert self._fail_levels(caplog) == [logging.DEBUG]

    def test_consecutive_failures_escalate_to_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG, logger="copycat.server.mis"):
            for _ in range(4):
                fetch_otc_snapshot(fetcher=_boom)
        assert self._fail_levels(caplog) == [
            logging.DEBUG,
            logging.DEBUG,
            logging.WARNING,
            logging.WARNING,
        ]

    def test_success_resets_streak(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.DEBUG, logger="copycat.server.mis"):
            fetch_otc_snapshot(fetcher=_boom)
            fetch_otc_snapshot(fetcher=_boom)
            fetch_otc_snapshot(fetcher=_fake_fetcher(SAMPLE))
            fetch_otc_snapshot(fetcher=_boom)
        assert self._fail_levels(caplog) == [
            logging.DEBUG,
            logging.DEBUG,
            logging.DEBUG,
        ]
