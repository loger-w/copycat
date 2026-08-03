"""WS fanout 共用層:per-client 有界 queue。

capital / futures / corr / river / stock / index 六路 WS 原本各抄一份同樣的
「滿了丟最舊、保最新」邏輯(B-D5)。住 capital_api 會讓 stock_engine / index_engine
逆向依賴 route 層,故獨立成檔。
"""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator, Iterable

#: 預設 per-client queue 上限(capital/futures/corr/river 沿用;engine 層各自傳值)
CLIENT_QUEUE_MAX = 500


class WsBroadcaster:
    """per-client 有界 queue fanout;`publish` 必須在 event loop 上呼叫。"""

    def __init__(self, maxsize: int = CLIENT_QUEUE_MAX) -> None:
        self._maxsize = maxsize
        self._clients: set[asyncio.Queue[dict]] = set()

    def publish(self, msg: dict) -> None:
        for queue in self._clients:
            try:
                queue.put_nowait(msg)
            except asyncio.QueueFull:
                # 慢連線丟最舊、保最新(行情/回報都是最新有意義)
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(msg)
                except asyncio.QueueFull:
                    pass

    def stream(self, seed: Iterable[dict] = ()) -> AsyncGenerator[dict, None]:
        """新 client 的訊息流;`seed` 逐則在**呼叫當下同步**入該 client 的佇列。

        種子**不可借用 `publish`**(那會打到所有 client);同步區間無 await,
        對 event loop 原子,不會與其它推播交錯。
        """
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=self._maxsize)
        self._clients.add(queue)
        for msg in seed:
            try:
                queue.put_nowait(msg)
            except asyncio.QueueFull:  # pragma: no cover - 種子數遠小於 queue 上限
                break

        async def _gen() -> AsyncGenerator[dict, None]:
            try:
                while True:
                    yield await queue.get()
            finally:
                self._clients.discard(queue)

        return _gen()
