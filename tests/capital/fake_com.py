"""CapitalCom 假實作治具(Task 6 client 測試;之後 server route 測試重用)。

FakeCom:滿足 CapitalCom Protocol,寫入呼叫收集進 `sent` 供逐欄斷言;
RecordingCom:額外記錄啟動序列方法名(SC-1 啟動順序驗證)。
不放 test_ 前綴檔 — pytest 不收集,只當 import 治具。
"""

from __future__ import annotations

from collections.abc import Callable


class FakeCom:
    """滿足 CapitalCom Protocol 的假實作;全部呼叫成功(rc=0)。

    寫入面呼叫以 tuple 收進 `sent`;帳號清單可注入(預設含 TS 證券 + TF 期貨戶)。
    """

    def __init__(self, accounts: list[tuple[str, str]] | None = None) -> None:
        self.sent: list[tuple[object, ...]] = []
        self.accounts: list[tuple[str, str]] = (
            [("TS", "1234567890A"), ("TF", "F9999999")] if accounts is None else accounts
        )
        self.authority: int | None = None
        self.on_reply: Callable[[str], None] | None = None
        self.on_balance: Callable[[str], None] | None = None
        self.on_profit: Callable[[str], None] | None = None
        self.on_reply_disconnect: Callable[[int], None] | None = None
        self.on_open_interest: Callable[[str], None] | None = None

    def setup(
        self,
        on_reply: Callable[[str], None] | None = None,
        on_balance: Callable[[str], None] | None = None,
        on_profit: Callable[[str], None] | None = None,
        on_reply_disconnect: Callable[[int], None] | None = None,
        on_open_interest: Callable[[str], None] | None = None,
    ) -> None:
        self.on_reply = on_reply
        self.on_balance = on_balance
        self.on_profit = on_profit
        self.on_reply_disconnect = on_reply_disconnect
        self.on_open_interest = on_open_interest

    def set_authority(self, flag: int) -> int:
        self.authority = flag
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
        self.sent.append(("stock", fields))
        return "SEQ0001", 0

    def send_future_order(
        self, user_id: str, fields: dict[str, object], *, is_option: bool
    ) -> tuple[str, int]:
        self.sent.append(("future", fields, is_option))
        return "SEQF001", 0

    def cancel_order(self, user_id: str, full_account: str, seq_no: str) -> tuple[str, int]:
        self.sent.append(("cancel", full_account, seq_no))
        return "OK", 0

    def correct_price(
        self, user_id: str, full_account: str, seq_no: str, price: float
    ) -> tuple[str, int]:
        self.sent.append(("correct_price", full_account, seq_no, price))
        return "OK", 0

    def decrease_qty(
        self, user_id: str, full_account: str, seq_no: str, qty: int
    ) -> tuple[str, int]:
        self.sent.append(("decrease", full_account, seq_no, qty))
        return "OK", 0

    def get_real_balance(self, user_id: str, full_account: str) -> int:
        self.sent.append(("get_real_balance", full_account))
        return 0

    def get_profit_loss_gw(self, user_id: str, full_account: str) -> int:
        self.sent.append(("get_profit_loss_gw", full_account))
        return 0

    def get_user_accounts(self, timeout_s: float = 3.0) -> list[tuple[str, str]]:
        return list(self.accounts)

    def get_open_interest(self, user_id: str, futures_account: str) -> int:
        self.sent.append(("get_open_interest", futures_account))
        return 0

    def return_code_message(self, code: int) -> str:
        return "成功" if code == 0 else f"錯誤({code})"

    def pump(self) -> None: ...


class RecordingCom(FakeCom):
    """記錄啟動時呼叫到的 COM 方法順序,驗證啟動序列(SC-1)。"""

    def __init__(self, accounts: list[tuple[str, str]] | None = None) -> None:
        super().__init__(accounts)
        self.calls: list[str] = []
        self.connect_reply_rc = 0

    def setup(
        self,
        on_reply: Callable[[str], None] | None = None,
        on_balance: Callable[[str], None] | None = None,
        on_profit: Callable[[str], None] | None = None,
        on_reply_disconnect: Callable[[int], None] | None = None,
        on_open_interest: Callable[[str], None] | None = None,
    ) -> None:
        self.calls.append("setup")
        super().setup(on_reply, on_balance, on_profit, on_reply_disconnect, on_open_interest)

    def set_authority(self, flag: int) -> int:
        self.calls.append("set_authority")
        return super().set_authority(flag)

    def login(self, user_id: str, password: str) -> int:
        self.calls.append("login")
        return 0

    def init_order(self) -> int:
        self.calls.append("init_order")
        return 0

    def read_cert(self, user_id: str) -> int:
        self.calls.append("read_cert")
        return 0

    def connect_reply(self, user_id: str) -> int:
        self.calls.append("connect_reply")
        return self.connect_reply_rc

    def get_user_accounts(self, timeout_s: float = 3.0) -> list[tuple[str, str]]:
        self.calls.append("get_user_accounts")
        return super().get_user_accounts(timeout_s)
