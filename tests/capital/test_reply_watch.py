"""回報線主動問(#235 辨識階段):幫浦圈每 `REPLY_PROBE_SECS` 問一次 `IsConnectedByID`,
值變化才印一行,結果進 `status_view()`;**status 燈不動、不重連**(語意未實證,誤判會在盤中
亮假黃字)。這是「真掉線時 status 恆 ok」這個 blast radius 的保底,不依賴任何 SKCOM 事件會不會響。
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from copycat.capital.client import CapitalClient
from copycat.capital.safety import SafetyConfig
from tests.capital.fake_com import FakeCom


def _client(com: FakeCom, tmp_path: Path) -> CapitalClient:
    client = CapitalClient(
        com,
        user_id="u",
        password="p",
        full_account="1234567890A",
        env="test",
        safety=SafetyConfig(order_enabled=True, max_qty=5, max_amount=None),
        audit_base=tmp_path / "audit",
    )
    client._status = "ok"
    client._balance_last_ts = float("inf")  # 不讓 60 s 輪詢混進來
    return client


def _probe_lines(caplog: pytest.LogCaptureFixture) -> list[tuple[int, str]]:
    return [
        (r.levelno, r.getMessage())
        for r in caplog.records
        if r.name == "copycat.capital.client" and "回報線" in r.getMessage()
    ]


def test_probe_is_throttled_and_logs_only_on_change(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="copycat.capital.client")
    com = FakeCom()
    com.reply_connected_seq = [1, 1, 0, 1]
    client = _client(com, tmp_path)
    assert client.status_view()["reply_connected"] is None  # 尚未問過

    client._pump_once()  # 首圈就問
    assert com.reply_connected_calls == 1
    assert client.status_view()["reply_connected"] == 1
    assert _probe_lines(caplog) == [(logging.INFO, "群益回報線 IsConnectedByID=1(上一值 None)")]

    client._pump_once()  # 節流:同一窗內不再問
    assert com.reply_connected_calls == 1

    client._reply_probe_next = 0.0  # 到期
    client._pump_once()
    assert com.reply_connected_calls == 2
    assert len(_probe_lines(caplog)) == 1  # 值沒變 → 不印

    client._reply_probe_next = 0.0
    client._pump_once()  # → 0
    assert client.status_view()["reply_connected"] == 0
    assert _probe_lines(caplog)[-1] == (logging.WARNING, "群益回報線 IsConnectedByID=0(上一值 1)")
    assert client.status == "ok"  # 辨識階段不翻 degraded(白名單)

    client._reply_probe_next = 0.0
    client._pump_once()  # → 1
    assert _probe_lines(caplog)[-1] == (logging.INFO, "群益回報線 IsConnectedByID=1(上一值 0)")
    assert client.status_view()["reply_connected"] == 1


def test_probe_skipped_when_not_logged_in(tmp_path: Path) -> None:
    """status 在 ok / degraded 之外(starting / error)不問:登入前問是無意義的 COM 呼叫。"""
    com = FakeCom()
    client = _client(com, tmp_path)
    client._status = "error"
    client._pump_once()
    assert com.reply_connected_calls == 0
    assert client.status_view()["reply_connected"] is None
