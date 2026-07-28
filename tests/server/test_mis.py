"""MIS 櫃買快照 fetch/解析測試 — index-board SC-4."""

from __future__ import annotations

import io
import json
import urllib.error
from typing import Any

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
