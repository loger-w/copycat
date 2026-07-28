"""capital com 層:SKCOM.dll 載入決策 + 事件 sink 純邏輯 + Protocol 合約(SC-1)。

真實 COM 載入需要群益元件與 Windows COM apartment,不進 CI(treading-king 慣例);
這裡只測「決定怎麼載」「事件轉發/防炸/留痕」「OnAccount 帳號列解析」等純邏輯,
以及 CapitalCom Protocol 可被 stub/fake 滿足(Task 6 FakeCom 前哨)。
"""

from __future__ import annotations

import logging
import os
import sys
import types
from collections.abc import Callable

from copycat.capital.com import (
    CapitalCom,
    SkcomCapitalCom,
    _OrderEvents,
    _parse_account_row,
    _ReplyEvents,
    _resolve_skcom_load,
)

# ---------------------------------------------------------------------------
# _resolve_skcom_load(treading-king 案例移植)
# ---------------------------------------------------------------------------


def test_resolve_no_dir_keeps_bare_name() -> None:
    """沒設 dll_dir → 裸檔名 + 不加搜尋路徑(靠 PATH/CWD 找)。"""
    assert _resolve_skcom_load(None) == (None, "SKCOM.dll")


def test_resolve_blank_dir_keeps_bare_name() -> None:
    """空字串 / 純空白都視為沒設,不可組出 '\\SKCOM.dll' 這種爛路徑。"""
    assert _resolve_skcom_load("") == (None, "SKCOM.dll")
    assert _resolve_skcom_load("   ") == (None, "SKCOM.dll")


def test_resolve_with_dir_uses_absolute_path() -> None:
    """有設 dll_dir → 回該資料夾(要加進 DLL 搜尋路徑)+ 絕對路徑給 GetModule。"""
    d = r"C:\CapitalAPI\x64"
    assert _resolve_skcom_load(d) == (d, os.path.join(d, "SKCOM.dll"))


# ---------------------------------------------------------------------------
# setup():sink / advise 連線必須存 instance 屬性防 GC(treading-king 根因防呆移植)
# ---------------------------------------------------------------------------


def test_setup_retains_event_refs(monkeypatch) -> None:
    """setup() 必須存住 reply/order 兩組事件 sink + GetEvents 連線。

    丟掉會被 CPython refcount GC → comtypes Unadvise → 登入即回
    SK_WARNING_REGISTER_REPLYLIB_ONREPLYMESSAGE_FIRST / 庫存事件永遠收不到。
    這裡 mock 掉 comtypes 層(sys.modules 注入),驗證 setup() 有把兩者存到 self。
    """
    captured: list[tuple[object, object, object]] = []

    def fake_get_events(source: object, sink: object) -> object:
        conn = types.SimpleNamespace(tag=f"advise-{len(captured)}")
        captured.append((source, sink, conn))
        return conn

    client = types.ModuleType("comtypes.client")
    setattr(client, "GetModule", lambda *a, **k: None)
    setattr(
        client,
        "CreateObject",
        lambda coclass, interface=None: types.SimpleNamespace(coclass=coclass),
    )
    setattr(client, "GetEvents", fake_get_events)

    comtypes_mod = types.ModuleType("comtypes")
    gen = types.ModuleType("comtypes.gen")
    skcomlib = types.ModuleType("comtypes.gen.SKCOMLib")
    for nm in (
        "SKCenterLib",
        "ISKCenterLib",
        "SKOrderLib",
        "ISKOrderLib",
        "SKReplyLib",
        "ISKReplyLib",
    ):
        setattr(skcomlib, nm, nm)
    setattr(comtypes_mod, "client", client)
    setattr(comtypes_mod, "gen", gen)
    setattr(gen, "SKCOMLib", skcomlib)

    monkeypatch.setitem(sys.modules, "comtypes", comtypes_mod)
    monkeypatch.setitem(sys.modules, "comtypes.client", client)
    monkeypatch.setitem(sys.modules, "comtypes.gen", gen)
    monkeypatch.setitem(sys.modules, "comtypes.gen.SKCOMLib", skcomlib)

    com = SkcomCapitalCom()
    com.setup()

    assert com._sk is skcomlib
    by_sink = {id(sink): (source, sink, conn) for source, sink, conn in captured}
    assert len(captured) == 2  # reply + order 兩條 advise
    _, reply_sink, reply_conn = by_sink[id(com._reply_sink)]
    assert com._reply_conn is reply_conn
    assert reply_sink is not None
    _, order_sink, order_conn = by_sink[id(com._order_sink)]
    assert com._order_conn is order_conn
    assert order_sink is not None


# ---------------------------------------------------------------------------
# 事件 sink:轉發 / 例外防炸 / 留痕(treading-king 移植 + open_interest 新增)
# ---------------------------------------------------------------------------


def test_reply_on_reply_message_suppresses_popup() -> None:
    """群益慣例:OnReplyMessage 回 -1 抑制彈窗。"""
    assert _ReplyEvents().OnReplyMessage("u", "msg") == -1


def test_reply_events_forwards_and_swallows() -> None:
    got: list[str] = []
    sink = _ReplyEvents(on_reply=got.append)
    sink.OnNewData("u", "TS,1234,...")
    assert got == ["TS,1234,..."]

    def boom(_: str) -> None:
        raise RuntimeError("handler boom")

    _ReplyEvents(on_reply=boom).OnNewData("u", "x")  # 例外不可炸 COM 事件迴圈
    _ReplyEvents().OnNewData("u", "x")  # 無回呼 noop


def test_reply_events_disconnect_notifies_and_swallows() -> None:
    """OnDisconnect 要轉給 client 降級(comtypes 對未實作事件靜默忽略,
    不掛 handler 就完全偵測不到斷線);回呼例外不可炸 COM 事件迴圈。"""
    got: list[int] = []
    sink = _ReplyEvents(on_disconnect=got.append)
    sink.OnDisconnect("u", 3002)
    assert got == [3002]

    def boom(_: int) -> None:
        raise RuntimeError("boom")

    _ReplyEvents(on_disconnect=boom).OnDisconnect("u", 1)
    _ReplyEvents().OnDisconnect("u", 1)


def test_order_events_balance_and_profit_forward_and_swallow() -> None:
    got: list[str] = []
    _OrderEvents(on_balance=got.append).OnRealBalanceReport("TS,1234567,2330,...")
    _OrderEvents(on_profit=got.append).OnProfitLossGWReport("000,查詢成功")
    assert got == ["TS,1234567,2330,...", "000,查詢成功"]

    def boom(_: str) -> None:
        raise RuntimeError("boom")

    _OrderEvents(on_balance=boom).OnRealBalanceReport("x")
    _OrderEvents(on_profit=boom).OnProfitLossGWReport("x")
    _OrderEvents().OnRealBalanceReport("x")
    _OrderEvents().OnProfitLossGWReport("x")


def test_order_events_open_interest_forwards_and_swallows() -> None:
    """OnOpenInterest(期貨部位資料列)轉給 on_open_interest;例外不可炸 COM 迴圈。"""
    got: list[str] = []
    _OrderEvents(on_open_interest=got.append).OnOpenInterest("TF,F0212345678,TXFH6,...")
    assert got == ["TF,F0212345678,TXFH6,..."]

    def boom(_: str) -> None:
        raise RuntimeError("boom")

    _OrderEvents(on_open_interest=boom).OnOpenInterest("x")
    _OrderEvents().OnOpenInterest("x")


def test_order_events_open_interest_status_is_noop_safe() -> None:
    """OnOpenInterestGWStatus 只留 log,不可拋(COM 事件迴圈)。"""
    _OrderEvents().OnOpenInterestGWStatus(0, "")
    _OrderEvents().OnOpenInterestGWStatus(2003, "查詢失敗")


def test_event_sink_exceptions_leave_log_trail(caplog) -> None:
    """回呼例外=一筆回報/庫存/損益/部位事件被丟棄:不炸 COM 迴圈是對的,
    但必須留痕(含原始字串),否則面板跟市場脫節後完全無法追查為什麼漏。"""

    def boom(_: str) -> None:
        raise RuntimeError("handler boom")

    with caplog.at_level(logging.ERROR, logger="copycat.capital.com"):
        _ReplyEvents(on_reply=boom).OnNewData("u", "data-x")
        _OrderEvents(on_balance=boom).OnRealBalanceReport("bal-x")
        _OrderEvents(on_profit=boom).OnProfitLossGWReport("pnl-x")
        _OrderEvents(on_open_interest=boom).OnOpenInterest("oi-x")
    errs = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errs) == 4
    for token in ("data-x", "bal-x", "pnl-x", "oi-x"):
        assert any(token in r.getMessage() for r in errs), token


# ---------------------------------------------------------------------------
# OnAccount 收集 + 帳號列解析(get_user_accounts,review R6)
# ---------------------------------------------------------------------------


def test_order_events_on_account_collects_raw_rows() -> None:
    sink = _OrderEvents()
    sink.OnAccount("u", "TS,F02,7,1234567,A123456789,測試")
    sink.OnAccount("u", "TF,F02,7,7654321,A123456789,測試")
    assert sink.accounts == [
        "TS,F02,7,1234567,A123456789,測試",
        "TF,F02,7,7654321,A123456789,測試",
    ]


def test_parse_account_row_stock_and_future() -> None:
    """market 取欄 0 前 2 碼上大寫;full_account = parts[1]+parts[3](欄序 prod 實測後校正)。"""
    assert _parse_account_row("TS,F02,7,1234567,A123456789,測試") == ("TS", "F021234567")
    assert _parse_account_row("tf,F02,7,7654321,A123456789,測試") == ("TF", "F027654321")


def test_parse_account_row_defensive_skip() -> None:
    """欄位不足 / 空列 → None(略過),不可 IndexError 炸掉收集迴圈。"""
    assert _parse_account_row("TS,F02,7") is None
    assert _parse_account_row("") is None
    assert _parse_account_row(",,,") is None  # 市場別空 → 略過


def test_get_user_accounts_pumps_and_parses(monkeypatch) -> None:
    """get_user_accounts:清空舊列 → GetUserAccount → pump 迴圈收 OnAccount → 解析。
    畸形列略過,不炸整批。"""
    com = SkcomCapitalCom()
    sink = _OrderEvents()
    sink.accounts.append("stale-row-from-previous-call")
    com._order_sink = sink
    com._order = types.SimpleNamespace(GetUserAccount=lambda: 0)

    fired = {"n": 0}

    def fake_pump() -> None:
        if fired["n"] == 0:
            sink.OnAccount("u", "TS,F02,7,1234567,A123456789,測試")
            sink.OnAccount("u", "TF,F02,7,7654321,A123456789,測試")
            sink.OnAccount("u", "bad-row")
        fired["n"] += 1

    monkeypatch.setattr(com, "pump", fake_pump)
    rows = com.get_user_accounts(timeout_s=0.12)
    assert rows == [("TS", "F021234567"), ("TF", "F027654321")]
    assert fired["n"] >= 1


# ---------------------------------------------------------------------------
# Protocol 合約完整性(SC-1):stub 靜態指派給 pyright 驗、方法面 runtime 核對
# ---------------------------------------------------------------------------


class _StubCom:
    """最小 CapitalCom 實作:證明 Protocol 簽名可被 fake 滿足(Task 6 FakeCom 前哨)。"""

    def setup(
        self,
        on_reply: Callable[[str], None] | None = None,
        on_balance: Callable[[str], None] | None = None,
        on_profit: Callable[[str], None] | None = None,
        on_reply_disconnect: Callable[[int], None] | None = None,
        on_open_interest: Callable[[str], None] | None = None,
    ) -> None:
        return None

    def set_authority(self, flag: int) -> int:
        return 0

    def login(self, user_id: str, password: str) -> int:
        return 0

    def init_order(self) -> int:
        return 0

    def read_cert(self, user_id: str) -> int:
        return 0

    def connect_reply(self, user_id: str) -> int:
        return 0

    def send_stock_order(self, user_id: str, fields: dict[str, object]) -> tuple[str, int]:
        return "", 0

    def send_future_order(
        self, user_id: str, fields: dict[str, object], *, is_option: bool
    ) -> tuple[str, int]:
        return "", 0

    def cancel_order(self, user_id: str, full_account: str, seq_no: str) -> tuple[str, int]:
        return "", 0

    def correct_price(
        self, user_id: str, full_account: str, seq_no: str, price_str: str
    ) -> tuple[str, int]:
        return "", 0

    def decrease_qty(
        self, user_id: str, full_account: str, seq_no: str, qty: int
    ) -> tuple[str, int]:
        return "", 0

    def get_real_balance(self, user_id: str, full_account: str) -> int:
        return 0

    def get_profit_loss_gw(self, user_id: str, full_account: str) -> int:
        return 0

    def get_user_accounts(self, timeout_s: float = 3.0) -> list[tuple[str, str]]:
        return []

    def get_open_interest(self, user_id: str, futures_account: str) -> int:
        return 0

    def return_code_message(self, code: int) -> str:
        return ""

    def pump(self) -> None:
        return None


# pyright 靜態驗證:_StubCom 結構上滿足 CapitalCom(簽名不合會在此行報錯)
_PROTOCOL_CHECK: CapitalCom = _StubCom()


def test_protocol_methods_complete_on_stub_and_real_impl() -> None:
    """Protocol 全方法在 stub 與 SkcomCapitalCom 上都存在且 callable(方法面完整性)。"""
    proto_methods = [n for n in dir(CapitalCom) if not n.startswith("_")]
    for required in (
        "setup",
        "send_stock_order",
        "send_future_order",
        "cancel_order",
        "correct_price",
        "decrease_qty",
        "get_user_accounts",
        "get_open_interest",
        "get_real_balance",
        "get_profit_loss_gw",
        "return_code_message",
        "pump",
    ):
        assert required in proto_methods, required
    for name in proto_methods:
        assert callable(getattr(_StubCom, name, None)), f"stub 缺 {name}"
        assert callable(getattr(SkcomCapitalCom, name, None)), f"SkcomCapitalCom 缺 {name}"
    assert isinstance(_PROTOCOL_CHECK, _StubCom)
