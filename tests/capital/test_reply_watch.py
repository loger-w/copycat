"""回報線主動問(#235):幫浦圈每 `REPLY_PROBE_SECS` 問一次 `IsConnectedByID`,值變化才印一行,
結果進 `status_view()`。fix/capital-reply-reconnect 起 0 / 1 也驅動狀態機(0 → degraded + 排退避重連、
1 → ok);重連本身**不在同一圈**發生(退避未到期),狀態機全貌見 test_reply_reconnect。這是「真掉線時
status 恆 ok」這個 blast radius 的保底,不依賴任何 SKCOM 事件會不會響(2026-09-15 05:50 實錄兩者都響了)。
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from copycat.capital.client import CapitalClient
from copycat.capital.safety import SafetyConfig
from tests.capital.fake_com import FakeCom, RecordingCom


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
    """只取值序列那一行(「群益回報線 IsConnectedByID=n」);同 logger 的耗時 WARNING「IsConnectedByID 耗時 … ms」
    沒有 `=`,cost > 50 ms(GC / 防毒停頓)時不會混進來讓 `==` 斷言紅在錯的方向(review F-11);狀態機的
    「斷線(探針 IsConnectedByID=0)→ degraded」那行含同一子字串,靠前綴「群益回報線 」隔開。"""
    return [
        (r.levelno, r.getMessage())
        for r in caplog.records
        if r.name == "copycat.capital.client" and "群益回報線 IsConnectedByID=" in r.getMessage()
    ]


def test_probe_is_throttled_and_logs_only_on_change(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="copycat.capital.client")
    com = RecordingCom()  # `calls` 記 COM 方法名:要能斷「翻 0 那一圈」connect_reply 沒被叫
    com.reply_connected_seq = [1, 1, 0, 1]
    client = _client(com, tmp_path)
    calls_before = list(com.calls)
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
    # 值翻 0 → degraded,重連只排程不立刻打:同一圈 COM 上沒有任何啟動序列方法被叫
    # (connect_reply / login / init_order …),退避到期才由 `_maybe_reconnect_reply` 出手
    # (test_reply_reconnect)。只斷 status 證不到後半(pr-238 review F-02)。
    assert client.status == "degraded"
    assert com.calls == calls_before, (
        f"值翻 0 同一圈不得有任何 COM 啟動序列呼叫:{com.calls[len(calls_before) :]}"
    )

    client._reply_probe_next = 0.0
    client._pump_once()  # → 1:探針自己救回 ok
    assert _probe_lines(caplog)[-1] == (logging.INFO, "群益回報線 IsConnectedByID=1(上一值 0)")
    assert client.status_view()["reply_connected"] == 1
    assert client.status == "ok"


def test_probe_skipped_when_not_logged_in(tmp_path: Path) -> None:
    """status 在 ok / degraded 之外(starting / error)不問:登入前問是無意義的 COM 呼叫。"""
    com = FakeCom()
    client = _client(com, tmp_path)
    client._status = "error"
    client._pump_once()
    assert com.reply_connected_calls == 0
    assert client.status_view()["reply_connected"] is None


def test_probe_value_two_is_neutral(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """pr-review 253 F-05:`IsConnectedByID` 值 2(23:59:56 實錄首值 = 連線中)**不動狀態、不排重連**——
    只有 0 / 1 驅動狀態機。守門寫成 `!= 1` 的話,開機首值 2 那一刻健康的回報線會被判斷線 →
    `store.clear()` + ConnectByID 迴圈 + degraded 假黃字(正是 #235 刻意避開的事)。值照進 `status_view`。"""
    caplog.set_level(logging.INFO, logger="copycat.capital.client")
    com = RecordingCom()
    com.reply_connected_seq = [1, 2, 2, 1]
    client = _client(com, tmp_path)
    calls_before = list(com.calls)
    for expected in (1, 2, 2, 1):
        client._reply_probe_next = 0.0
        client._pump_once()
        assert client.status_view()["reply_connected"] == expected
        assert client.status == "ok"
        assert client._reply_link.next_due is None
    assert com.calls == calls_before
    assert [lvl for lvl, _ in _probe_lines(caplog)] == [logging.INFO, logging.WARNING, logging.INFO]
