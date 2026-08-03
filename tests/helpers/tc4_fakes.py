"""TC4 source 測試共用的 ZMQ socket / api 替身。

`TC4QuoteSource` 家族(stock / futures / corr)全部走「`api.socket.send_string(JSON)` →
`api.socket.recv()` 取回應」這條路,測試因此都要同一組替身:handler 吃解好的 dict、
回一則位元組電文。六個測試檔各抄一份逐字相同的定義,wrapper 介面一變就要六處同步。

`tests/live/test_tc4.py` 與 `tests/data/test_backfill_tc4.py` 的 FakeApi 是**不同的東西**
(前者自帶分頁狀態機、後者對應 `_fetch_1k` 的另一種介面),刻意不收進來。
"""

from __future__ import annotations

import json
import threading
from typing import Any


class JsonSocket:
    """socket 替身:send 的 JSON 電文交 handler 分派,recv 回其回應。"""

    def __init__(self, handler: Any) -> None:
        self._handler = handler
        self._resp = b""

    def send_string(self, payload: str) -> None:
        self._resp = self._handler(json.loads(payload))

    def recv(self) -> bytes:
        return self._resp


class FakeApi:
    def __init__(self, handler: Any) -> None:
        self.socket = JsonSocket(handler)
        self.lock = threading.Lock()

    def Disconnect(self) -> None:  # noqa: N802 - wrapper 介面
        pass


def ok(payload: dict | None = None) -> bytes:
    """TC4 的成功回應電文(NUL 結尾)。"""
    return (json.dumps({"Success": "OK", **(payload or {})}) + "\0").encode()
