"""WS client 突斷(TCP RST,無 close frame)後不得對死 transport 續寫。

行為合約:uvicorn 的 `connection_lost` 只把 `websocket.disconnect` 放進 receive queue,
不設任何旗標;send-only 迴圈(`async for … await send_json`)因此永遠察覺不到斷線 →
每個 tick 都對已死的 asyncio transport 寫一次,第 6 次起 asyncio 每寫一次就 log 一則
`socket.send() raised exception.`(`LOG_THRESHOLD_FOR_CONNLOST_WRITES = 5`),而且殭屍
廣播迴圈永不退場 → 警告無限累積。

整合測試直接編碼那條鏈路(真 uvicorn + raw socket RST);`relay` 的單元測試則釘住
收尾語意(receive watcher 勝出 → send 側被取消 → stream 的 finally 走到 = queue 除名)。
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import socket
import struct
import threading
import time
from typing import AsyncGenerator, Callable

import pytest
import uvicorn

from copycat.live.models import SeriesInfo, Tick
from copycat.server.app import create_app
from copycat.server.ws import relay
from tests.helpers.fake_txo import C, FakeTxoSource

#: asyncio 對「connection lost 後仍寫入」的警告字串(stdlib selector/proactor 兩實作同字)
CONNLOST_WARNING = "socket.send() raised exception."


class _TickingSource(FakeTxoSource):
    """捕捉 EngineRuntime 的 on_tick,讓測試執行緒能持續推 tick(TC4 亦由他執行緒推)。"""

    def __init__(self) -> None:
        self.on_tick: Callable[[Tick], None] | None = None

    def subscribe(self, series: SeriesInfo, on_tick: Callable[[Tick], None]) -> None:
        self.on_tick = on_tick


def _tick(cum: int) -> Tick:
    return Tick(
        symbol=C.symbol,
        precise_time=cum,
        price_millipts=23_500_000,
        qty=1,
        bid_millipts=23_499_000,
        ask_millipts=23_500_000,
        cum_volume=cum,  # 遞增 = 聚合層去重主鍵,每筆都算新成交
    )


class _Collector(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def connlost_count(self) -> int:
        return sum(1 for r in self.records if CONNLOST_WARNING in r.getMessage())


def _ws_handshake(port: int, path: str) -> socket.socket:
    """手寫 HTTP upgrade:要的是能發 RST 的裸 socket,任何 WS client library 都會替我們
    好好地送 close frame —— 那正是本 bug 不會發生的路徑。"""
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    key = base64.b64encode(os.urandom(16)).decode()
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    )
    sock.sendall(request.encode())
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise AssertionError("握手期間連線被關閉")
        buf += chunk
    assert b" 101 " in buf.split(b"\r\n", 1)[0], buf[:200]
    return sock


def _abort(sock: socket.socket) -> None:
    """SO_LINGER=(on, 0) → close 發 RST 而非 FIN:模擬分頁被殺 / 網路斷,無 close frame。"""
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    sock.close()


class TestAbruptDisconnect:
    def test_no_write_to_dead_transport(self) -> None:
        source = _TickingSource()
        app = create_app(source, throttle_secs=0.02)
        config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", ws="auto")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()

        stop = threading.Event()

        def _pump() -> None:
            cum = 0
            while not stop.is_set():
                cum += 1
                callback = source.on_tick
                if callback is not None:
                    callback(_tick(cum))
                stop.wait(0.02)

        pump = threading.Thread(target=_pump, daemon=True)
        collector = _Collector()
        asyncio_logger = logging.getLogger("asyncio")
        asyncio_logger.addHandler(collector)
        try:
            deadline = time.monotonic() + 10
            while not server.started:
                if time.monotonic() > deadline:
                    raise AssertionError("uvicorn 未在時限內啟動")
                time.sleep(0.01)
            port = int(server.servers[0].sockets[0].getsockname()[1])

            sock = _ws_handshake(port, "/ws/txo-pnl")
            pump.start()
            sock.settimeout(5)
            assert sock.recv(4096), "連線後應收到至少一則 snapshot frame"

            _abort(sock)
            # 斷線後仍持續推 tick ≥1.5s:0.02s cadence 遠超 asyncio 的 5 次門檻,
            # 未修時必然累積警告;修好後 watcher 毫秒級收尾,殘餘寫入不到門檻。
            time.sleep(1.5)

            count = collector.connlost_count()
            assert count == 0, f"client 突斷後仍對死 transport 寫入 {count} 次(asyncio 警告)"
        finally:
            stop.set()
            if pump.is_alive():
                pump.join(timeout=5)
            asyncio_logger.removeHandler(collector)
            server.should_exit = True
            thread.join(timeout=5)


class _FakeWebSocket:
    """只實作 relay 用到的兩個方法;`receive` 由 future 控制何時「斷線」。"""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.disconnected: asyncio.Future[dict] = asyncio.Future()

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)

    async def receive(self) -> dict:
        return await self.disconnected

    def disconnect(self) -> None:
        if not self.disconnected.done():
            self.disconnected.set_result({"type": "websocket.disconnect", "code": 1006})


async def _spin(times: int = 5) -> None:
    """讓被取消的子任務跑完 finally(同步 cancel 不 await,需要 loop 再轉幾圈)。"""
    for _ in range(times):
        await asyncio.sleep(0)


class TestRelay:
    async def test_disconnect_stops_stream_and_runs_cleanup(self) -> None:
        websocket = _FakeWebSocket()
        closed = False

        async def _never_ending() -> AsyncGenerator[dict, None]:
            nonlocal closed
            try:
                while True:
                    await asyncio.sleep(3600)
                    yield {}
            finally:
                closed = True

        websocket.disconnect()  # client 已斷:relay 不該掛在永不產出的 stream 上
        await asyncio.wait_for(relay(websocket, _never_ending()), timeout=2)
        await _spin()
        assert closed, "send 側被取消後,stream 的 finally(client queue 除名)必須走到"

    async def test_forwards_messages_until_disconnect(self) -> None:
        websocket = _FakeWebSocket()
        gate = asyncio.Event()

        async def _three_then_wait() -> AsyncGenerator[dict, None]:
            for i in range(3):
                yield {"n": i}
            gate.set()
            await asyncio.sleep(3600)

        task = asyncio.ensure_future(relay(websocket, _three_then_wait()))
        await asyncio.wait_for(gate.wait(), timeout=2)
        assert websocket.sent == [{"n": 0}, {"n": 1}, {"n": 2}]
        assert not task.done(), "receive 仍 pending 時 relay 不該提前收尾"

        websocket.disconnect()
        await asyncio.wait_for(task, timeout=2)


@pytest.mark.parametrize("path", ["/ws/txo-pnl"])
def test_paths_exist(path: str) -> None:
    """route 表健檢:整合測試若因路徑打錯而握手失敗,錯誤訊息會很難讀。"""
    app = create_app(FakeTxoSource())
    assert any(getattr(r, "path", None) == path for r in app.routes)
