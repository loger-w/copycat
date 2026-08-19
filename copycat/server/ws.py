"""WS fanout 共用層:per-client 有界 queue + stream→WS 轉送(含斷線偵測)。

capital / futures / corr / river / stock / index 六路 WS 原本各抄一份同樣的
「滿了丟最舊、保最新」邏輯(B-D5)。住 capital_api 會讓 stock_engine / index_engine
逆向依賴 route 層,故獨立成檔。

`relay` 是這六路唯一的送出路徑:send-only 迴圈察覺不到 client 斷線(uvicorn 的
`connection_lost` 只把 `websocket.disconnect` 放進 receive queue,不設旗標),
必須並行 receive 才收得到 —— 沒有它就是殭屍迴圈對死 transport 連寫。

應用層心跳(`WS_HEARTBEAT_SECS` / `PING`)也住這裡:半死 TCP(連線活著但零 frame)
在瀏覽器端與「server 只是沒東西可推」完全同形,前端唯有「太久沒收到任何訊息」
這個判準可以自癒 —— 前提是 server 保證定時出聲。心跳由 `relay` **直送**,
不經 `WsBroadcaster` 的 per-client queue(不佔位、不受「滿了丟最舊」影響)。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator, Iterable, Mapping, Protocol

from fastapi import WebSocketDisconnect

logger = logging.getLogger(__name__)

#: 預設 per-client queue 上限(capital/futures/corr/river 沿用;engine 層各自傳值)
CLIENT_QUEUE_MAX = 500

#: 應用層心跳間隔(秒);`<= 0` 停用。跨檔契約:前端靜默 watchdog
#: (`frontend/src/lib/ws-reconnect.ts::WS_SILENCE_TIMEOUT_MS`)必須**大於**本值,
#: 改值要同改兩邊(CLAUDE.md §4)。
WS_HEARTBEAT_SECS: float = 10.0

#: 心跳訊息;8 條 WS 共用同一形狀(前端 helper 過濾,不進各 hook 的 onMessage)。
PING: dict[str, str] = {"type": "ping"}


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


async def relay(
    websocket: WsConnection,
    stream: AsyncGenerator[dict, None],
    *,
    heartbeat_secs: float | None = None,
) -> None:
    """stream → WS 送出,並行 receive 偵測 client 斷線(review B3)+ 定時心跳。

    無推播流量時 send 側永遠掛在 queue.get,察覺不到 client 斷線 →
    per-client queue 洩漏;receive task 在斷線時收到 `websocket.disconnect` 收尾。
    收尾路徑只做同步 cancel(不 await 子任務):endpoint 本身可能被外層
    cancel scope 取消(TestClient / server shutdown),收尾中再 await 會吸收
    重投的取消訊號,讓 task 以 cancelled 終結。

    突斷(TCP RST,無 close frame)也走同一條:uvicorn 的 `connection_lost` 只把
    disconnect 訊息放進 receive queue,send 側的 `transport.write()` 不會 raise
    (sans-io state 仍 OPEN)—— 不 receive 就永遠不知道對面已經死了。

    心跳(`_beat`):`heartbeat_secs=None` → **呼叫當下**讀模組常數 `WS_HEARTBEAT_SECS`
    (測試 monkeypatch 得到);`<= 0` 不建 task = 現況行為。每滿一個間隔送一則 `PING`,
    **定時而非補空窗**(有推播時照送);因為第一則要等滿一個間隔,route 自送的 seed /
    stream 的首則永遠排在任何 ping 之前。ping 直送 `send_json`,不經 `WsBroadcaster`
    的 per-client queue。

    `send_lock` 只序列化「單次 `await send_json`」,**不得**包住 `async for` 迴圈或
    `await queue.get()`:那會讓 `_beat` 在零流量時永遠等鎖 = 心跳靜默失效
    (正是本功能要解的那個症狀)。慢 client 的 `send_json` drain 卡住時 `_beat` 等鎖,
    ping 不會疊加。

    `_beat` 也進 `asyncio.wait(FIRST_COMPLETED)` 集合,例外分流與 `_send` 完全相同:
    死 transport 的 OSError 已由 starlette 轉成 `WebSocketDisconnect` → 吞掉收尾;
    其餘(如 uvicorn `close_sent` 後 ASGI send 的 `RuntimeError`)一律 re-raise。
    """
    secs = WS_HEARTBEAT_SECS if heartbeat_secs is None else heartbeat_secs
    send_lock = asyncio.Lock()

    async def _send() -> None:
        async for msg in stream:
            async with send_lock:
                await websocket.send_json(msg)

    async def _beat() -> None:
        while True:
            await asyncio.sleep(secs)
            async with send_lock:
                await websocket.send_json(PING)

    async def _recv() -> None:
        while True:
            message = await websocket.receive()
            # client 送來的訊息一律忽略;收到 disconnect 即結束 → FIRST_COMPLETED 收尾。
            # 用 `receive()` 不用 `receive_text()`:斷線在此是回傳值不是例外,而且
            # client 送 binary frame 不該被當成錯誤炸掉整條連線。
            if message.get("type") == "websocket.disconnect":
                return

    tasks: list[asyncio.Task[None]] = [
        asyncio.ensure_future(_send()),
        asyncio.ensure_future(_recv()),
    ]
    if secs > 0:
        tasks.append(asyncio.ensure_future(_beat()))
    done: set[asyncio.Task[None]] = set()
    try:
        done, _pending = await asyncio.wait(set(tasks), return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()
                t.add_done_callback(_consume_ws_task)
    for t in done:
        if not t.cancelled():
            exc = t.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect):
                raise exc
