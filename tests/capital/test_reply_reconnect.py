"""回報線斷線後自動重連(fix/capital-reply-reconnect;prod 2026-09-15 05:50 實錄)。

實錄:05:50:57 `Capital Solace reply disconnect (code=3033)` → 1.4 s 後探針 `IsConnectedByID=0(上一值 1)`
→ 到 08:14:30 user 重啟前**零** `Solace reply connection` 事件、探針值停在 0、status 燈仍 ok。同一分鐘
Discord / TC4 各自重連回來,回報線沒有任何路徑再呼 `connect_reply`。期望(user 2026-09-15 拍板「做」):
斷線(Solace 事件或探針翻 0 任一)→ degraded → 退避後 `store.clear()` + `connect_reply()`(ConnectByID 會重播
當日 backlog,不清就成交雙計;12:32 重啟實錄重播 17 筆)→ 探針回 1 / Solace connection code 0 → ok。
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from copycat.capital.client import CapitalClient
from copycat.capital.safety import SafetyConfig
from tests.capital.fake_com import RecordingCom


def _client(com: RecordingCom, tmp_path: Path) -> CapitalClient:
    client = CapitalClient(
        com,
        user_id="u",
        password="p",
        full_account="1234567890A",
        env="test",
        safety=SafetyConfig(order_enabled=True, max_qty=5, max_amount=None),
        audit_base=tmp_path / "audit",
    )
    assert client._init_com() is True  # 走真啟動序列:sink 回呼才會接到 client
    assert client.status == "ok"
    client._balance_last_ts = float("inf")  # 60 s 輪詢不混進 calls
    return client


def _fill_evt_raw(seq: str = "S1", qty: str = "1000", price: str = "90.0000") -> str:
    arr = [""] * 48
    arr[0], arr[1], arr[2], arr[3] = seq, "TS", "D", "N"
    arr[6], arr[8], arr[11], arr[20] = "B00R2", "3357", price, qty
    return ",".join(arr)


class _ReplayingCom(RecordingCom):
    """ConnectByID 語意:連上就把當日 backlog 重播一輪(store.py 檔頭;12:32 重啟實錄 17 筆)。"""

    def __init__(self) -> None:
        super().__init__()
        self.backlog: list[str] = []

    def connect_reply(self, user_id: str) -> int:
        rc = super().connect_reply(user_id)
        if rc == 0 and self.on_reply is not None:
            for row in self.backlog:
                self.on_reply(row)
        return rc


def _new_calls(com: RecordingCom, before: list[str]) -> list[str]:
    return com.calls[len(before) :]


def test_solace_disconnect_then_probe_zero_degrades_reconnects_and_recovers(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """05:50 場景逐字重播:事件斷線 → 探針 0 → 退避到期重連 → 探針 1 → ok。"""
    caplog.set_level(logging.INFO, logger="copycat.capital.client")
    com = RecordingCom()
    com.reply_connected_seq = [1, 0, 1]
    client = _client(com, tmp_path)
    client._reply_probe_next = 0.0
    client._pump_once()  # 探針首值 1
    assert client.status_view()["reply_connected"] == 1
    before = list(com.calls)

    assert com.on_reply_disconnect is not None
    com.on_reply_disconnect(3033)  # 05:50:57 Solace disconnect(sink 轉給 client)
    assert client.status == "degraded"

    client._reply_probe_next = 0.0
    client._pump_once()  # 05:50:59 探針翻 0
    assert client.status_view()["reply_connected"] == 0
    assert client.status == "degraded"

    # 修前:這裡之後永遠沒人再呼 connect_reply(prod 05:50 → 08:14 全程)。
    client._reply_reconnect_next = 0.0  # 退避到期
    client._pump_once()
    assert _new_calls(com, before) == ["connect_reply"], (
        f"斷線後退避到期必須重連回報線;實際 COM 呼叫:{_new_calls(com, before)}"
    )

    client._reply_probe_next = 0.0
    client._pump_once()  # 探針回 1
    assert client.status_view()["reply_connected"] == 1
    assert client.status == "ok"
    assert client.last_error is None or "回報" in client.last_error


def test_probe_zero_alone_degrades_and_reconnects(tmp_path: Path) -> None:
    """兩對事件都沒響、只有探針翻 0(next-time 第二條路):同樣翻 degraded + 重連。"""
    com = RecordingCom()
    com.reply_connected_seq = [1, 0, 0, 1]
    client = _client(com, tmp_path)
    client._reply_probe_next = 0.0
    client._pump_once()  # 1
    before = list(com.calls)

    client._reply_probe_next = 0.0
    client._pump_once()  # 0
    assert client.status == "degraded"

    client._reply_reconnect_next = 0.0
    client._pump_once()
    assert "connect_reply" in _new_calls(com, before)

    client._reply_probe_next = 0.0
    client._pump_once()  # 0:還沒回來,留在 degraded
    assert client.status == "degraded"
    client._reply_probe_next = 0.0
    client._pump_once()  # 1
    assert client.status == "ok"


def test_reconnect_clears_store_before_backlog_replay(tmp_path: Path) -> None:
    """R7:ConnectByID 重播當日 backlog,重連前不 clear 就成交雙計。"""
    com = _ReplayingCom()
    com.reply_connected_seq = [1, 0, 1]
    client = _client(com, tmp_path)
    assert com.on_reply is not None
    fill = _fill_evt_raw(seq="S1")
    com.on_reply(fill)  # 斷線前的成交
    com.backlog = [fill]  # 重連後群益會再送一次
    assert len(client.store.fills()) == 1

    client._reply_probe_next = 0.0
    client._pump_once()  # 1
    assert com.on_reply_disconnect is not None
    com.on_reply_disconnect(3033)
    before = list(com.calls)
    client._reply_reconnect_next = 0.0
    client._pump_once()  # 重連 → 重播
    assert "connect_reply" in com.calls[len(before) :]  # 先確定真的重連了,守門才有意義
    assert len(client.store.fills()) == 1, "重播前未 clear → 同一筆成交雙計"


def test_reconnect_failure_backs_off_and_stays_degraded(tmp_path: Path) -> None:
    """connect_reply 失敗:留在 degraded、每個退避窗只試一次(不在幫浦圈每 50 ms 狂打 COM)。"""
    com = RecordingCom()
    com.reply_connected_seq = [1, 0]
    client = _client(com, tmp_path)
    client._reply_probe_next = 0.0
    client._pump_once()
    before = list(com.calls)
    assert com.on_reply_disconnect is not None
    com.on_reply_disconnect(3033)

    com.connect_reply_rc = 3001
    client._reply_reconnect_next = 0.0
    client._pump_once()
    client._pump_once()  # 同一退避窗內不再試
    client._pump_once()
    assert _new_calls(com, before).count("connect_reply") == 1
    assert client.status == "degraded"

    client._reply_reconnect_next = 0.0
    client._pump_once()
    assert _new_calls(com, before).count("connect_reply") == 2
    assert client.status == "degraded"

