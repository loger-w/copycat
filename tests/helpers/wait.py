"""測試用的條件式等待(deadline 輪詢),取代 `await asyncio.sleep(N)` 換圈數。

**為什麼不用固定 sleep**:Windows timer 解析度 15.6 ms —— `sleep(0.15)` 名目「約 5 拍」
實際可能一拍都沒轉。正向斷言會間歇假紅,而否定型斷言(「沒多打一次」)更糟:迴圈根本
沒跑也會綠,是永久性的假綠。條件式等待兩邊都對,慢只會慢不會錯,失敗訊息也說得出等的
是什麼。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable


async def wait_until(pred: Callable[[], bool], timeout: float = 2.0) -> None:
    """輪詢 `pred()` 直到成立;逾時 raise `AssertionError`。

    時鐘取 `loop.time()`(單調鐘,與 `asyncio.sleep` 同一把):被測物若用 `monkeypatch`
    改過牆鐘,這裡的 deadline 不會跟著漂。
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if pred():
            return
        await asyncio.sleep(0.005)
    raise AssertionError(f"條件未在 {timeout}s 內成立")
