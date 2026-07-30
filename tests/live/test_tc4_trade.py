"""SC-2:TC4TradeSource — disposable 連線模型 / ErrCode 分流 / 回報分派 / 分頁防呆。"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

import pytest
import zmq

from copycat.live.tc4_trade import TC4TradeSource
from copycat.live.trade_models import BrokerRejectedError, TouchanceDownError
from tests.conftest import requires_tcpy


class FakeSocket:
    """REQ socket 替身:依 Request 類型回 scripted 回應;可注入 zmq.Again 與 recv side-effect。"""

    def __init__(self, responses: dict[str, list[dict] | dict]) -> None:
        self.responses = responses
        self.sent: list[dict] = []
        self.raise_again_on: set[str] = set()
        self.on_recv: Callable[[], None] | None = None

    def send_string(self, text: str) -> None:
        self.sent.append(json.loads(text))

    def recv(self) -> bytes:
        if self.on_recv is not None:
            self.on_recv()
        req = self.sent[-1]["Request"]
        if req in self.raise_again_on:
            raise zmq.Again()
        resp = self.responses[req]
        if isinstance(resp, list):
            resp = resp.pop(0)
        return json.dumps(resp).encode() + b"\x00"


class FakeTradeApi:
    def __init__(self, responses: dict[str, list[dict] | dict]) -> None:
        self.lock = threading.Lock()
        self.socket = FakeSocket(responses)
        self.disconnects = 0
        self.m_objZMQKeepAlive = None

    def Disconnect(self) -> None:  # noqa: N802 - TCPY wrapper 命名
        self.disconnects += 1


def make_source(
    responses: dict[str, list[dict] | dict] | None = None, **kw: Any
) -> tuple[TC4TradeSource, FakeTradeApi]:
    api = FakeTradeApi(responses or {})
    src = TC4TradeSource(
        port="0", api=api, session="sess-1", sub_port="9001", lock_timeout_secs=0.05, **kw
    )
    return src, api


ACCOUNTS_RESP = {
    "Success": "OK",
    "Accounts": [{"BrokerID": "SIM", "Account": "9999000", "AccountMask": "SIM-9999000"}],
}


class TestReqPath:
    def test_accounts_parses(self) -> None:
        src, api = make_source({"ACCOUNTS": ACCOUNTS_RESP})
        accounts = src.accounts()
        assert [a.broker_id for a in accounts] == ["SIM"]
        assert api.socket.sent[-1]["Request"] == "ACCOUNTS"

    def test_timeout_disposes_and_lock_reusable(self) -> None:
        src, api = make_source({"ACCOUNTS": ACCOUNTS_RESP})
        api.socket.raise_again_on.add("ACCOUNTS")
        with pytest.raises(TouchanceDownError):
            src.accounts()
        assert api.lock.acquire(timeout=0.1) is True  # R2-1:timeout 後 lock 未毒化
        api.lock.release()
        assert api.disconnects == 1  # disposable:連線已作廢
        assert src.connected is False

    def test_lock_held_elsewhere_is_touchance_down(self) -> None:
        src, api = make_source({"ACCOUNTS": ACCOUNTS_RESP})
        api.lock.acquire()  # 模擬 wrapper 殘留路徑毒化(R3-2)
        try:
            with pytest.raises(TouchanceDownError):
                src.accounts()
        finally:
            api.lock.release()

    def test_dispose_only_once(self) -> None:
        src, api = make_source({"ACCOUNTS": ACCOUNTS_RESP})
        api.socket.raise_again_on.add("ACCOUNTS")
        with pytest.raises(TouchanceDownError):
            src.accounts()
        with pytest.raises(TouchanceDownError):
            src.accounts()  # _api 已 None,注入模式下不重連 → 直接 down
        assert api.disconnects == 1  # 不 double-Disconnect(R3-5)


class TestPlaceOrder:
    def test_success_returns_raw(self) -> None:
        src, _ = make_source({"NEWORDER": {"Success": "OK", "OrderID": "X1"}})
        assert src.place_order({"Symbol": "S"})["OrderID"] == "X1"

    def test_errcode_minus_20_is_touchance_down(self) -> None:
        src, _ = make_source({"NEWORDER": {"Success": "FAIL", "ErrCode": "-20"}})
        with pytest.raises(TouchanceDownError):
            src.place_order({"Symbol": "S"})

    def test_errcode_minus_20_disposes_request_api_not_current(self) -> None:
        """-20 dispose 的對象必須是本次請求用的 api;若期間已換新連線不得誤殺(review A3)。"""
        src, api = make_source({"NEWORDER": {"Success": "FAIL", "ErrCode": "-20"}})
        replacement = FakeTradeApi({})

        def swap() -> None:
            src._api = replacement  # 模擬:回覆抵達前另一條路徑已 dispose + lazy reconnect

        api.socket.on_recv = swap
        with pytest.raises(TouchanceDownError):
            src.place_order({"Symbol": "S"})
        assert replacement.disconnects == 0  # 新連線不得被誤殺
        assert src.connected is True  # replacement 仍在役

    def test_other_errcode_is_broker_rejected(self) -> None:
        src, _ = make_source(
            {"NEWORDER": {"Success": "FAIL", "ErrCode": "-13", "ErrMsg": "no permission"}}
        )
        with pytest.raises(BrokerRejectedError) as ei:
            src.place_order({"Symbol": "S"})
        assert ei.value.err_code == "-13"


class TestRestorePagination:
    def test_pages_until_stall(self) -> None:
        page1 = {
            "Reply": "RESTOREREPORT",
            "Orders": [
                {"ReportID": "R1", "QryIndex": "10"},
                {"ReportID": "R2", "QryIndex": "20"},
            ],
        }
        page2 = {"Reply": "RESTOREREPORT", "Orders": [{"ReportID": "R3", "QryIndex": "20"}]}
        src, api = make_source({"RESTOREREPORT": [page1, page2]})
        reports = src.restore_reports()
        assert [r.report_id for r in reports] == ["R1", "R2", "R3"]
        # 停滯(QryIndex 同值)→ break,不再送第三次
        assert sum(1 for s in api.socket.sent if s["Request"] == "RESTOREREPORT") == 2

    def test_empty_first_page(self) -> None:
        src, _ = make_source({"RESTOREREPORT": {"Reply": "RESTOREREPORT", "Orders": []}})
        assert src.restore_reports() == []

    def test_restore_fills(self) -> None:
        src, _ = make_source(
            {
                "RESTOREFILLREPORT": {
                    "Reply": "RESTOREFILLREPORT",
                    "Orders": [{"ReportID": "F1", "QryIndex": ""}],
                }
            }
        )
        assert [r.report_id for r in src.restore_fills()] == ["F1"]


class TestSubMessageDispatch:
    def collect(self) -> tuple[list[tuple[str, str]], Callable[[str, Any], None]]:
        got: list[tuple[str, str]] = []

        def on_report(kind: str, report: Any) -> None:
            got.append((kind, report.report_id))

        return got, on_report

    def test_execution_and_fill_dispatch(self) -> None:
        src, _ = make_source()
        got, on_report = self.collect()
        src.set_report_callback_for_test(on_report)
        src.handle_sub_message({"DataType": "EXECUTIONREPORT", "Report": {"ReportID": "E1"}})
        src.handle_sub_message({"DataType": "FILLEDREPORT", "Report": {"ReportID": "F1"}})
        src.handle_sub_message({"DataType": "ACCOUNTS", "Accounts": []})  # Phase 1 忽略
        assert got == [("exec", "E1"), ("fill", "F1")]

    def test_ping_sends_pong(self) -> None:
        src, api = make_source({"PONG": {"Success": "OK"}})
        src.handle_sub_message({"DataType": "PING"})
        assert api.socket.sent[-1]["Request"] == "PONG"

    def test_ping_ignored_when_disposed(self) -> None:
        src, api = make_source({"ACCOUNTS": ACCOUNTS_RESP})
        api.socket.raise_again_on.add("ACCOUNTS")
        with pytest.raises(TouchanceDownError):
            src.accounts()
        src.handle_sub_message({"DataType": "PING"})  # R4-5:不觸發 reconnect、不 raise
        assert all(s["Request"] != "PONG" for s in api.socket.sent)

    def test_pong_failure_does_not_dispose(self) -> None:
        src, api = make_source({"PONG": {"Success": "OK"}})
        api.socket.raise_again_on.add("PONG")
        src.handle_sub_message({"DataType": "PING"})  # 失敗僅 debug log(R4-5)
        assert src.connected is True
        assert api.disconnects == 0


class FakeSubSocket:
    def __init__(self, target: str) -> None:
        self.target = target
        self.closed = False

    def recv(self) -> bytes:
        raise zmq.Again()

    def close(self, linger: int = 0) -> None:
        self.closed = True


class TestListenerGeneration:
    def test_generation_change_rebuilds_sub_and_fires_on_reconnect(self) -> None:
        src, _ = make_source()
        built: list[FakeSubSocket] = []

        def make_sub(sub_port: str) -> FakeSubSocket:
            sock = FakeSubSocket(sub_port)
            built.append(sock)
            return sock

        reconnects = threading.Event()
        src.set_sub_socket_factory_for_test(make_sub)
        src.subscribe_reports(lambda kind, r: None, reconnects.set)
        try:
            deadline = time.monotonic() + 2.0
            while not built and time.monotonic() < deadline:
                time.sleep(0.01)
            assert built and built[0].target == "9001"
            src.set_conn_info_for_test(("sess-2", "9002", 2))  # 模擬 lazy reconnect 換 SubPort
            assert reconnects.wait(timeout=2.0) is True  # R3-1:generation 驅動重建
            deadline = time.monotonic() + 2.0
            while len(built) < 2 and time.monotonic() < deadline:
                time.sleep(0.01)
            assert built[-1].target == "9002"
            assert built[0].closed is True
        finally:
            src.close()


class TestClose:
    def test_close_disconnects(self) -> None:
        src, api = make_source()
        src.close()
        assert api.disconnects == 1  # §0a:不 Disconnect process 不退出


@requires_tcpy
class TestFailedConnectGcSafety:
    def test_failed_connect_gc_does_not_block_process(self) -> None:
        """F-1(2026-07-20 盤中驗證):Connect 失敗被丟棄的 api,GC 回收 zmq Context 不得卡死。

        盤中實證:trade port 不通時,被棄 TradeAPI 的 Context.__del__ → term() 因 pending
        LOGIN + 預設 LINGER=-1 無限期阻塞 event loop,server 永不 bind(py-spy stack 見
        docs/research/2026-07-20-txo-live-verification.md F-1)。子行程重現:逾時 = 卡死。
        """
        script = (
            "import gc\n"
            "from copycat.live.tc4_trade import TC4TradeSource\n"
            "from copycat.live.trade_models import TouchanceDownError\n"
            "src = TC4TradeSource(port='1')\n"  # 無 listener 的 port:LOGIN 永遠 pending
            "try:\n"
            "    src._ensure_connected()\n"
            "except TouchanceDownError:\n"
            "    pass\n"
            "gc.collect()\n"
            "print('GC_OK', flush=True)\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(Path(__file__).resolve().parent.parent.parent),
        )
        assert "GC_OK" in proc.stdout
