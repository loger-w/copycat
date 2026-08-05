"""WS client 突斷(TCP RST,無 close frame)後不得對死 transport 續寫。

行為合約:uvicorn 的 `connection_lost` 只把 `websocket.disconnect` 放進 receive queue,
不設任何旗標;send-only 迴圈(`async for … await send_json`)因此永遠察覺不到斷線 →
每個 tick 都對已死的 asyncio transport 寫一次,第 6 次起 asyncio 每寫一次就 log 一則
`socket.send() raised exception.`(`LOG_THRESHOLD_FOR_CONNLOST_WRITES = 5`),而且殭屍
廣播迴圈永不退場 → 警告無限累積。

整合測試直接編碼那條鏈路(真 uvicorn + raw socket RST);`relay` 的單元測試則釘住
收尾語意(receive watcher 勝出 → send 側被取消 → stream 的 finally 走到 = queue 除名)。

同一條合約的另外兩半也在本檔:
- `TestGracefulShutdownWithLiveClient`:client **保持連線**時 server 仍要收得掉
  (上面那條測的是「client 先 RST 之後」,涵蓋不到沒斷線的情形)。
- `TestBroadcastRouteDisconnect`:六條 broadcaster 路由逐一過同一套突斷劇本 ——
  `/ws/txo-pnl` 只是七條 relay 路的其中一條,其餘六條各有自己的接線。
"""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import datetime as _dt
import json
import logging
import os
import socket
import struct
import threading
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Callable

import pytest
import uvicorn
from fastapi import FastAPI, WebSocketDisconnect

import copycat.capital.factory as capital_factory
import copycat.server.app as app_mod
from copycat.live.models import SeriesInfo, Tick
from copycat.server.app import create_app
from copycat.server.ws import WsBroadcaster, relay
from tests.helpers.boot import wait_boot
from tests.helpers.fake_sources import (
    FakeCorrSource,
    FakeFuturesSource,
    FakeIndexSource,
    FakeStockSource,
)
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


def _ws_handshake_keep_rest(port: int, path: str) -> tuple[socket.socket, bytes]:
    """手寫 HTTP upgrade:要的是能發 RST 的裸 socket,任何 WS client library 都會替我們
    好好地送 close frame —— 那正是本 bug 不會發生的路徑。

    **第二個回傳值 = header 之後那段殘留位元組**。101 回應與 server 主動送的第一則
    frame 可能落在同一個 TCP segment,握手迴圈讀到 `\\r\\n\\r\\n` 就停,超出的那段還在
    buf 裡 —— 丟掉它等於那則 frame 憑空消失,而下一次 recv 會一路等到 timeout
    (現象:「連線後收不到 snapshot」,2026-08-04 實測約每五次一次)。
    """
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
    return sock, buf.split(b"\r\n\r\n", 1)[1]


def _ws_handshake(port: int, path: str) -> socket.socket:
    """丟棄殘留的版本(既有測試沿用,行為與收斂前逐位元組相同)。

    ⚠ 丟殘留 = 上面那個 flake 仍在。修它要動既有測試的斷言,不在本輪 scope(已記
    next-time);**新測試一律用 `_ws_handshake_keep_rest`**。
    """
    sock, _rest = _ws_handshake_keep_rest(port, path)
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
            # `server.started` = HTTP 面開了,不再等於引擎就緒(啟動序列已移背景 task)
            wait_boot(app)
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


# ---------------------------------------------------------------------------
# 真 uvicorn 治具(以下新測試共用)
# ---------------------------------------------------------------------------


#: 未在 `__exit__` 的 join 期限內收掉的 server(以 label 記)。殘留的殭屍廣播迴圈會繼續
#: 往 **全域** asyncio logger 寫警告 → 其後每一條測試的 `connlost_count()` 都不再只反映
#: 自己那一路。空著才代表計數可信;非空時由消費端測試開頭直接 fail 明示,免得一次真失敗
#: 被演成連鎖數次的假失敗(review F4)。
_HUNG_SERVERS: list[str] = []


class _RunningServer:
    """真 uvicorn(port 0)+ 背景執行緒;離開 context 時 graceful shutdown 並 join。

    `thread` 在 `__exit__` 之後仍可查 `is_alive()` —— 「關得掉」的斷言刻意留在 context
    **外面**做,主體失敗時不跑,免得把原始失敗訊息蓋掉(同上面那條既有測試的理由)。

    `graceful_timeout` 預設 **None(= uvicorn 預設的無上限)**:那正是
    `TestGracefulShutdownWithLiveClient` 要驗的行為,設了上限等於讓被測的 bug
    在期限到時被 uvicorn 強制收尾 → 那條測試對回歸失去敏感度。只有「關機不是題目、
    但殘留會污染別人」的用法(六路突斷)才顯式給上限。
    """

    def __init__(
        self,
        app: FastAPI,
        *,
        join_timeout: float = 10.0,
        graceful_timeout: int | None = None,
        label: str = "",
    ) -> None:
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=0,
            log_level="warning",
            ws="auto",
            timeout_graceful_shutdown=graceful_timeout,
        )
        self.app = app  # `wait_boot` 用:HTTP 開了 ≠ 引擎就緒(啟動序列在背景 task)
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.port = 0
        self.hung = False
        self._join_timeout = join_timeout
        self._label = label

    def __enter__(self) -> _RunningServer:
        self.thread.start()
        deadline = time.monotonic() + 15
        while not self.server.started:
            if not self.thread.is_alive():
                raise AssertionError("uvicorn 執行緒在啟動途中就結束了(lifespan 炸了?)")
            if time.monotonic() > deadline:
                self.server.should_exit = True
                raise AssertionError("uvicorn 未在時限內啟動")
            time.sleep(0.01)
        try:
            wait_boot(self.app)  # 六路推播鏈的正向對照需要引擎真的起完
        except BaseException:
            # `__enter__` 拋 = `with` 主體不執行 = `__exit__` **永不執行**:server 沒被
            # should_exit 收掉,殭屍廣播迴圈也不會進 `_HUNG_SERVERS` → 其後每條測試的
            # connlost 計數都被污染卻看不出來(歸還路徑同 `BootedClient.__enter__`)
            self.__exit__()
            raise
        self.port = int(self.server.servers[0].sockets[0].getsockname()[1])
        return self

    def __exit__(self, *_exc: object) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=self._join_timeout)
        if self.thread.is_alive():
            self.hung = True
            _HUNG_SERVERS.append(self._label or "<unlabelled>")


def _drain_frames(sock: socket.socket, *, want: int, timeout: float) -> int:
    """收滿 `want` 批(或到 deadline)為止,回實際收到的批數。

    **deadline 迴圈而非固定時間窗**:固定窗(「收 0.5 秒然後數」)在全套負載下會因為
    排程抖動間歇少收 → 假紅,既有 `test_no_write_to_dead_transport` 正是這樣 flake 的。
    累積到目標就走、沒到才等滿,慢只會慢不會錯。
    """
    deadline = time.monotonic() + timeout
    batches = 0
    while batches < want:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        sock.settimeout(min(0.5, remaining))
        try:
            chunk = sock.recv(4096)
        except TimeoutError:
            continue
        assert chunk, "server 提前關閉了連線"
        batches += 1
    return batches


class TestGracefulShutdownWithLiveClient:
    def test_shutdown_completes_while_client_stays_connected(self) -> None:
        """client **不斷線**時 server 也要收得掉(2026-08-04 relay 回歸)。

        未修時 send-only 迴圈掛在 `queue.get` 上永不返回,uvicorn 關機送的 close frame
        只會進 receive queue 沒人收 —— `Server.shutdown()` 等連線收尾等到天荒地老
        (`timeout_graceful_shutdown` 預設 None = 無上限)。上面那條既有測試在 client
        已 RST 之後才驗關機,涵蓋不到這一半。

        `/ws/txo-pnl` 且**不推任何 tick**:accept 後直送一則 snapshot 證明連線活著,
        接著 relay 就停在 `queue.get` 上 —— 正是要驗的那個狀態。
        """
        app = create_app(FakeTxoSource(), throttle_secs=0.02)
        with _RunningServer(app, label="graceful-shutdown") as srv:
            sock, rest = _ws_handshake_keep_rest(srv.port, "/ws/txo-pnl")
            sock.settimeout(5)
            assert rest or sock.recv(4096), "連線後應收到至少一則 snapshot frame(證明連線活著)"

            started = time.monotonic()
            srv.server.should_exit = True
            srv.thread.join(timeout=10)
            elapsed = time.monotonic() - started
            # **判決點在 `sock.close()` 之前**:context 的 `__exit__` 會再 join 一次,而
            # client 一旦關掉,未修的 send-only 迴圈也會因為 transport 死掉而收尾 ——
            # 拿 `__exit__` 之後的 `is_alive()` 當判準,實際驗到的是「允許 client 先斷」,
            # 與本測試宣稱的場景(client 保持連線)不符(review F1)。
            alive_while_connected = srv.thread.is_alive()
            sock.close()

        assert not alive_while_connected, (
            f"client 仍連著時 uvicorn 收不掉:{elapsed:.1f}s 後執行緒仍活著"
            "(WS 迴圈掛在 queue.get 上,察覺不到關機)"
        )


# ---------------------------------------------------------------------------
# 六條 broadcaster 路由的突斷覆蓋
# ---------------------------------------------------------------------------


class _FakeCapital:
    """`app.state.capital` 的最小替身:只需要 lifespan 的三個接點 + broadcast 掛點。

    真 `CapitalClient` + `FakeCom` 也走得通,但那條路要起 COM 執行緒與命令佇列,
    對「WS 突斷」這件事是純噪音。`set_broadcast` 收到的 callback 就是 app.py 包好的
    `loop.call_soon_threadsafe(capital_ws.publish, …)` —— 從 COM 執行緒邊界往下的
    production 路徑一段沒少。
    """

    def __init__(self) -> None:
        self.broadcast: Callable[[dict[str, object]], None] | None = None

    def set_broadcast(self, cb: Callable[[dict[str, object]], None]) -> None:
        self.broadcast = cb

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        return None

    def close(self) -> None:
        return None


def _futures_quote(n: int) -> dict:
    """TXF HOT REALTIME(欄位對照 test_capital_api `_fut_quote`)。

    刻意不帶月份訊號(Symbol 尾是 HOT、無 EndDate、名稱無數字)→ `resolve_contract_ym`
    回 None → 不觸發 leaf fallback 的計時器,測試只留突斷這一條變因。
    """
    return {
        "Symbol": "TC.F.TWF.TXF.HOT",
        "SecurityName": "臺股期貨",
        "TradingPrice": str(23_500 + n % 7),
        "TradeQuantity": "2",
        "TradeVolume": str(1_000 + n),
        "TradeDate": "20260728",
        "PreciseTime": "020000000000",
        "Bid": "23499",
        "BidVolume": "10",
        "Ask": "23500",
        "AskVolume": "12",
        "ReferencePrice": "23400",
    }


def _index_quote(n: int) -> dict:
    """加權 IX0001 REALTIME;價每則不同 → `_dirty` 必被設起(否則廣播迴圈跳過)。"""
    return {
        "Security": "IX0001",
        "TradingPrice": f"{42_039.92 + n:.2f}",
        "ReferencePrice": "43634.19",
        "HighPrice": "43221.93",
        "LowPrice": "41815.78",
        "FilledTime": "013015",
    }


_STOCK_CODE = "2330"


def _stock_quote(n: int) -> dict:
    """個股 REALTIME。

    - `TradeDate` = 本機今日 + `PreciseTime` UTC 02:00(= 台北 10:00):既避開試撮窗
      (13:25–13:30 會被 `ingest` 短路),也讓 `tick.trade_date` 等於 engine 的
      `trade_date` —— 大一天就會踩 rollover 快路徑,那是另一個測試的題目。
    - `TradeVolume` 遞增 = 去重主鍵,每則都算新成交 → 進 `_dirty_watchlist`,
      由 1s(此處 0.02s)flush 迴圈廣播 `watchlist_quote`。
    """
    return {
        "Symbol": f"TC.S.TWS.{_STOCK_CODE}",
        "Security": _STOCK_CODE,
        "SecurityName": "台積電",
        "TradingPrice": "1000.0000",
        "TradeQuantity": "1",
        "TradeVolume": str(1_000 + n),
        "TradeDate": f"{_dt.date.today():%Y%m%d}",
        "PreciseTime": "020000000000",
        "ReferencePrice": "1000.0000",
        "UpperLimitPrice": "1100.0000",
        "LowerLimitPrice": "900.0000",
        "Bid": "999.0000",
        "BidVolume": "5",
        "Ask": "1000.0000",
        "AskVolume": "5",
    }


def _build_futures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[FastAPI, Any]:
    fake = FakeFuturesSource()
    return create_app(FakeTxoSource(), futures_source=fake, throttle_secs=0.02), fake


def _build_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[FastAPI, Any]:
    fake = FakeIndexSource()
    app = create_app(
        FakeTxoSource(),
        index_source=fake,
        index_mis_fetch=lambda: None,
        throttle_secs=0.02,
    )
    return app, fake


def _build_corr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[FastAPI, Any]:
    fake = FakeCorrSource()
    return create_app(FakeTxoSource(), corr_source=fake, throttle_secs=0.02), fake


def _build_stock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[FastAPI, Any]:
    # 自選預先落檔:lifespan 會回填成訂閱池,`_handle_quote` 才有 state 收 tick
    wl = tmp_path / "watchlist.json"
    wl.write_text(json.dumps({"codes": [_STOCK_CODE], "groups": []}), encoding="utf-8")
    # 訊號層的 fallback 通知走真 `notify_discord` —— 開發機 shell / repo root .env 有
    # webhook 時測試會真的發訊息出去(conftest 只中和了 CAPITAL_* 與 DISCORD_BOT_TOKEN)
    monkeypatch.setattr(app_mod, "notify_discord", lambda *_a, **_k: False)
    fake = FakeStockSource()
    app = create_app(
        FakeTxoSource(),
        stock_source=fake,
        stock_watchlist_path=wl,
        throttle_secs=0.02,
    )
    return app, fake


def _build_capital(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[FastAPI, Any]:
    fake = _FakeCapital()
    monkeypatch.setattr(capital_factory, "get_capital", lambda: fake)
    return create_app(FakeTxoSource(), throttle_secs=0.02), fake


def _pump_source(build: Callable[[int], dict]) -> Callable[[FastAPI, Any, int], None]:
    """source callback 直推:engine 的 `_on_*_threadsafe` 自己做 loop 轉發,
    測試執行緒可以直接呼叫(TC4 真實情況也是他執行緒推進來)。"""

    def _pump(app: FastAPI, ctx: Any, n: int) -> None:
        cb = ctx.on_message
        if cb is not None:
            cb(build(n))

    return _pump


def _pump_corr(app: FastAPI, ctx: Any, n: int) -> None:
    """corr / river 的廣播只出自每秒的 `tick_once`,而 `tick_secs` 不經 `create_app`
    暴露 —— 1 Hz 推不出足以觸發 asyncio 門檻(連寫 5 次才 log)的密度,斷線後零警告
    會變成 vacuous 綠。故直接以 threadsafe 方式敲 `tick_once`:從那裡往下
    (state → broadcast → WsBroadcaster → relay)仍是完整的 production 路徑。

    讀 `_loop` private:engine 沒有公開的 loop 取用面,而測試執行緒要進 loop 只有這條。
    """
    engine = app.state.corr
    if engine is None:
        return
    loop = engine._loop
    if loop is not None:
        loop.call_soon_threadsafe(engine.tick_once)


def _pump_capital(app: FastAPI, ctx: Any, n: int) -> None:
    cb = ctx.broadcast
    if cb is not None:
        cb({"type": "status", "n": n})


@dataclasses.dataclass(frozen=True)
class _WsCase:
    path: str
    build: Callable[[Path, pytest.MonkeyPatch], tuple[FastAPI, Any]]
    pump: Callable[[FastAPI, Any, int], None]
    #: route 在 relay **之外**、accept 後直送一則快照(app.py 的 `/ws/corr`、`/ws/river`;
    #: 其餘四路 accept 後就直接進 relay)。True 時測試先把那則單獨收乾,之後數到的批數
    #: 才全部出自 relay 迴圈本身。
    pre_relay_snapshot: bool = False


#: `create_app` 的 futures/corr/index/stock source 預設 None = 該引擎不建 → 每一路都要
#: 顯式注入對應的 fake,否則 route 會走「引擎缺席」分支直接關連線(vacuous 綠)。
_WS_CASES = [
    _WsCase("/ws/futures", _build_futures, _pump_source(_futures_quote)),
    _WsCase("/ws/index", _build_index, _pump_source(_index_quote)),
    _WsCase("/ws/stock", _build_stock, _pump_source(_stock_quote)),
    _WsCase("/ws/corr", _build_corr, _pump_corr, pre_relay_snapshot=True),
    _WsCase("/ws/river", _build_corr, _pump_corr, pre_relay_snapshot=True),
    _WsCase("/ws/capital", _build_capital, _pump_capital),
]


class TestBroadcastRouteDisconnect:
    """`/ws/txo-pnl` 之外的六條 relay 路,逐條過同一套劇本。

    劇本 = 正向對照(收到足量 frame,證明推播鏈真的在跑)→ RST 突斷 → 繼續推 1.5s
    → asyncio 零 `socket.send() raised exception.` → server 收得掉。缺了正向對照那段,
    「斷線後零警告」在上游靜默斷掉時會 vacuous 綠(根本沒寫過,自然沒有警告)。

    正向對照有兩截,缺一不可:
    - **斷線前**:`_drain_frames` 數到門檻。有 pre-relay 快照的兩路先把那則單獨收乾,
      門檻才只數 relay 迴圈的產出(`_drain_frames` 數的是 recv 回傳次數 —— 快照長大到
      被 TCP 拆成數段時,四批可能全出自那一則,review F3)。
    - **斷線後**:pump 執行緒必須真的還在推。它若靜默死掉,`count == 0` 同樣是
      vacuous 綠 —— 對稱於斷線前那道保護(review F2)。
    """

    @pytest.mark.parametrize("case", _WS_CASES, ids=[c.path for c in _WS_CASES])
    def test_no_write_to_dead_transport(
        self, case: _WsCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 前一路的 server 沒收乾淨時,它的殭屍迴圈仍在往全域 asyncio logger 寫警告 ——
        # 本路的計數會混到別人的帳(review F4)。明示 fail 而不是讓它變成一串假失敗。
        if _HUNG_SERVERS:
            pytest.fail(f"前一路 server 未關乾淨({_HUNG_SERVERS}),本路計數不可信")

        app, ctx = case.build(tmp_path, monkeypatch)
        stop = threading.Event()
        collector = _Collector()
        asyncio_logger = logging.getLogger("asyncio")
        pumped = 0

        # `graceful_timeout`:關機不是這條的題目(下面那句 `is_alive` 只是順帶的契約),
        # 而殘留會污染其後每一路 → 給上限讓殘留有界。
        with _RunningServer(app, graceful_timeout=5, label=case.path) as srv:

            def _pump() -> None:
                nonlocal pumped
                n = 0
                while not stop.is_set():
                    n += 1
                    case.pump(app, ctx, n)
                    pumped += 1
                    stop.wait(0.02)

            pump = threading.Thread(target=_pump, daemon=True)
            asyncio_logger.addHandler(collector)
            try:
                sock, rest = _ws_handshake_keep_rest(srv.port, case.path)
                if case.pre_relay_snapshot:
                    # pump 還沒起 → 線上只可能有 accept 後直送的那一則,單獨收乾
                    if not rest:
                        assert _drain_frames(sock, want=1, timeout=15) == 1, (
                            f"{case.path}:連線後沒收到 relay 之外的快照"
                        )
                    pump.start()
                    want = 3
                    batches = _drain_frames(sock, want=want, timeout=15)
                else:
                    pump.start()
                    # 握手殘留裡的那批也算(否則同 segment 到達時會白白少數一批)
                    seen = 1 if rest else 0
                    want = 4
                    batches = seen + _drain_frames(sock, want=want - seen, timeout=15)
                assert batches >= want, (
                    f"{case.path} 斷線前只收到 {batches} 批 frame(門檻 {want}):推播鏈沒動,"
                    "本測試無法證明修復(relay 根本沒送過幾次)"
                )

                pumped_at_abort = pumped
                _abort(sock)
                # 0.02s cadence × 1.5s ≈ 75 次寫入,遠超 asyncio 的 5 次門檻:
                # 未修時必然累積警告,修好後 watcher 毫秒級收尾。
                time.sleep(1.5)

                assert pump.is_alive(), (
                    f"{case.path}:pump 執行緒在斷線後就死了 —— 沒人推,零警告不算證據"
                )
                pumped_after = pumped - pumped_at_abort
                assert pumped_after >= 20, (
                    f"{case.path}:斷線後只推了 {pumped_after} 次(遠低於 asyncio 的 5 次門檻的"
                    "安全倍數),零警告不算證據"
                )

                count = collector.connlost_count()
                assert count == 0, (
                    f"{case.path}:client 突斷後仍對死 transport 寫入 {count} 次(asyncio 警告)"
                )
            finally:
                stop.set()
                if pump.is_alive():
                    pump.join(timeout=5)
                asyncio_logger.removeHandler(collector)

        assert not srv.thread.is_alive(), (
            f"{case.path}:uvicorn 未能 graceful shutdown(WS 迴圈仍掛著)"
        )


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
