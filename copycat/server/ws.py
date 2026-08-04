"""WS fanout 共用層:per-client 有界 queue + stream→WS 轉送(含斷線偵測)。

capital / futures / corr / river / stock / index 六路 WS 原本各抄一份同樣的
「滿了丟最舊、保最新」邏輯(B-D5)。住 capital_api 會讓 stock_engine / index_engine
逆向依賴 route 層,故獨立成檔。

`relay` 是這六路唯一的送出路徑:send-only 迴圈察覺不到 client 斷線(uvicorn 的
`connection_lost` 只把 `websocket.disconnect` 放進 receive queue,不設旗標),
必須並行 receive 才收得到 —— 沒有它就是殭屍迴圈對死 transport 連寫。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator, Iterable, Mapping, Protocol

from fastapi import WebSocketDisconnect

logger = logging.getLogger(__name__)

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


class WsConnection(Protocol):
    """`relay` 用到的 WebSocket 面。

    用 Protocol 不用 `fastapi.WebSocket` 具體型別:relay 的合約只是「送 JSON + 收訊息」,
    測試注入 fake 才能不起真 server(engine 層 QuoteSource / StockSource 同款)。
    """

    async def send_json(self, data: Any) -> None: ...

    async def receive(self) -> Mapping[str, Any]: ...


def _consume_ws_task(task: asyncio.Task[None]) -> None:
    """被取消的 send/recv 任務收尾:消費例外避免 unretrieved warning;
    task 取消同時會關閉 stream() generator → 該 client queue 除名。"""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None and not isinstance(exc, WebSocketDisconnect):
        logger.warning("ws 任務收尾例外(已忽略): %r", exc)


async def relay(websocket: WsConnection, stream: AsyncGenerator[dict, None]) -> None:
    """stream → WS 送出,並行 receive 偵測 client 斷線(review B3)。

    無推播流量時 send 側永遠掛在 queue.get,察覺不到 client 斷線 →
    per-client queue 洩漏;receive task 在斷線時收到 `websocket.disconnect` 收尾。
    收尾路徑只做同步 cancel(不 await 子任務):endpoint 本身可能被外層
    cancel scope 取消(TestClient / server shutdown),收尾中再 await 會吸收
    重投的取消訊號,讓 task 以 cancelled 終結。

    突斷(TCP RST,無 close frame)也走同一條:uvicorn 的 `connection_lost` 只把
    disconnect 訊息放進 receive queue,send 側的 `transport.write()` 不會 raise
    (sans-io state 仍 OPEN)—— 不 receive 就永遠不知道對面已經死了。
    """

    async def _send() -> None:
        async for msg in stream:
            await websocket.send_json(msg)

    async def _recv() -> None:
        while True:
            message = await websocket.receive()
            # client 送來的訊息一律忽略;收到 disconnect 即結束 → FIRST_COMPLETED 收尾。
            # 用 `receive()` 不用 `receive_text()`:斷線在此是回傳值不是例外,而且
            # client 送 binary frame 不該被當成錯誤炸掉整條連線。
            if message.get("type") == "websocket.disconnect":
                return

    send_task = asyncio.ensure_future(_send())
    recv_task = asyncio.ensure_future(_recv())
    done: set[asyncio.Task[None]] = set()
    try:
        done, _pending = await asyncio.wait(
            {send_task, recv_task}, return_when=asyncio.FIRST_COMPLETED
        )
    finally:
        for t in (send_task, recv_task):
            if not t.done():
                t.cancel()
                t.add_done_callback(_consume_ws_task)
    for t in done:
        if not t.cancelled():
            exc = t.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect):
                raise exc
