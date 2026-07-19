"""Dev / real-env 驗證用 TradeSource(env TXO_FAKE_TRADE=1;不碰 TC4,impl-R4)。

故障注入(r2-R3,供截圖 (c)(d)):qty=98 → TouchanceDownError;qty=99 → BrokerRejectedError。
正常單 0.5 秒後經 on_report 回推 exec + fill(r2-R1:report 必須走 callback 才進 store)。
"""

from __future__ import annotations

import threading
from typing import Callable

from copycat.live.trade_models import (
    AccountInfo,
    BrokerRejectedError,
    OrderReport,
    TouchanceDownError,
    parse_execution_report,
    parse_fill_report,
)


class FakeTradeSource:
    def __init__(self) -> None:
        self._on_report: Callable[[str, OrderReport], None] | None = None
        self._seq = 0

    def accounts(self) -> list[AccountInfo]:
        return [
            AccountInfo(
                broker_id="SIM-DEV", account="9999000", account_mask="SIM-DEV-9999000", raw={}
            )
        ]

    def place_order(self, param: dict[str, str]) -> dict:
        qty = param.get("OrderQty", "")
        if qty == "98":
            raise TouchanceDownError("fake: injected touchance down (qty=98)")
        if qty == "99":
            raise BrokerRejectedError("-22", "價格的 TickSize 錯誤(fake 注入)")
        self._seq += 1
        report_id = f"FAKE{self._seq:04d}"
        base = {
            "ReportID": report_id,
            "Symbol": param.get("Symbol", ""),
            "Side": param.get("Side", ""),
            "Price": param.get("Price", ""),
            "OrderQty": qty,
        }

        def push() -> None:
            cb = self._on_report
            if cb is None:
                return
            cb("exec", parse_execution_report({**base, "OrdStatus": "4"}))
            cb("fill", parse_fill_report({**base, "OrdStatus": "F", "MatchedQty": qty}))

        threading.Timer(0.5, push).start()
        return {"Success": "OK", "FakeReportID": report_id}

    def restore_reports(self) -> list[OrderReport]:
        return []

    def restore_fills(self) -> list[OrderReport]:
        return []

    def subscribe_reports(
        self,
        on_report: Callable[[str, OrderReport], None],
        on_reconnect: Callable[[], None],
    ) -> None:
        self._on_report = on_report

    def close(self) -> None:
        return None
