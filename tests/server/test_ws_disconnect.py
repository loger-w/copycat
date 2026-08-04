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
from fastapi import WebSocketDisconnect

from copycat.live.models import SeriesInfo, Tick
from copycat.server.app import create_app
from copycat.server.ws import WsBroadcaster, relay
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
            sock.settimeout(5)
            # 初始 snapshot 在 relay 之外(accept 後直送)→ 先單獨收掉,不讓它充當
            # 下面「relay 迴圈在跑」的證據
            assert sock.recv(4096), "連線後應收到至少一則 snapshot frame"

            # 正向對照:tick → snapshot → relay send 這條鏈必須真的在跑。少了它,
            # 上游任一環靜默斷掉(fake 沒被訂閱 / 版本沒 bump / 節流卡住)時,
            # 「斷線後零警告」會 vacuous 綠 —— 沒寫過任何一次自然不會有警告。
            pump.start()
            batches = 0
            sock.settimeout(0.5)
            window_end = time.monotonic() + 0.5
            while time.monotonic() < window_end:
                try:
                    chunk = sock.recv(65536)
                except TimeoutError:
                    break
                assert chunk, "斷線前 server 就關了連線"
                batches += 1
            assert batches >= 3, (
                f"斷線前只收到 {batches} 批 frame:上游 tick 流沒動,"
                "本測試無法證明修復(relay 根本沒送過幾次)"
            )

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

        # 契約的另一半:殭屍迴圈退場後 uvicorn 才收得掉。刻意放在 finally **之外** ——
        # 主體失敗時不跑,免得這條把原始失敗訊息蓋掉。
        assert not thread.is_alive(), "uvicorn 未能 graceful shutdown(WS 迴圈仍掛著)"


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


class _RaisingWebSocket(_FakeWebSocket):
    """send 側炸掉的 WS;用來釘住 relay 的例外分流(吞 WebSocketDisconnect、其餘 re-raise)。"""

    def __init__(self, exc: BaseException) -> None:
        super().__init__()
        self._exc = exc

    async def send_json(self, data: dict) -> None:
        raise self._exc


async def _one_message() -> AsyncGenerator[dict, None]:
    """產一則後掛住:讓 send 側必然呼叫一次 send_json,再由該次呼叫決定結局。"""
    yield {"n": 0}
    await asyncio.sleep(3600)


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

    async def test_broadcaster_client_is_deregistered(self) -> None:
        """與真 `WsBroadcaster` 組合:斷線後該 client 的 queue 必須從 fanout 名單除名。

        直接讀 `_clients` private:除名是 `stream()` 的 finally 這條收尾路徑的**唯一**
        外部可觀測結果(公開面沒有「還有幾個 client」的查詢),不讀它就只能測到
        「relay 有返回」而測不到洩漏有沒有真的修掉。
        """
        websocket = _FakeWebSocket()
        broadcaster = WsBroadcaster()
        stream = broadcaster.stream()
        assert len(broadcaster._clients) == 1

        websocket.disconnect()
        await asyncio.wait_for(relay(websocket, stream), timeout=2)
        await _spin()
        assert broadcaster._clients == set(), "斷線後 per-client queue 仍掛在 fanout 名單上"

    async def test_send_error_propagates(self) -> None:
        websocket = _RaisingWebSocket(RuntimeError("送出炸了"))
        with pytest.raises(RuntimeError, match="送出炸了"):
            await asyncio.wait_for(relay(websocket, _one_message()), timeout=2)

    async def test_send_disconnect_is_swallowed(self) -> None:
        """capital_api / app.py 的 endpoint 直接 await relay,斷線不該冒成 500。"""
        websocket = _RaisingWebSocket(WebSocketDisconnect(code=1006))
        await asyncio.wait_for(relay(websocket, _one_message()), timeout=2)
