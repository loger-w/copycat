"""FuturesQuoteSource:TXF/MXF/TMF HOT REALTIME 資料源(capital-order design §10)。

繼承 TC4QuoteSource 複用連線/REQ 全域互斥/_dispose/stale 重連(同 stock_source 案 A:
不動 tc4.py)。REALTIME 窗沿用基底 session 窗 — 期貨與 TXO 同時段(日盤 08:45–13:45 /
夜盤 15:00–05:00,live/session 時區事實),不需個股日盤窗覆寫。

listener 覆寫為原始 Quote dict 分派(book/meta 都要,不能只回 Tick;同 stock_source
手法)。ZMQ session 第 4 條:TXO quote + stock + index + futures(design §13)。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from copycat.live.futures_models import PRODUCTS
from copycat.live.tc4 import TC4QuoteSource

logger = logging.getLogger(__name__)


def futures_symbol(product: str) -> str:
    """產品碼 → TC4 期貨樹熱門月 symbol(台指期產品碼 = TXF,非 FITX;07-20 實證)。"""
    return f"TC.F.TWF.{product}.HOT"


class FuturesQuoteSource(TC4QuoteSource):
    def __init__(
        self,
        port: str = "50774",
        *,
        api: Any | None = None,
        session: str | None = None,
        poll_wait_secs: float = 1.0,
    ) -> None:
        super().__init__(port, api=api, session=session, poll_wait_secs=poll_wait_secs)
        self._on_message: Callable[[dict], None] | None = None

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        self._on_message = cb

    # ---- 逐品訂閱(UNSUB→SUB 冪等;失敗 raise 供 engine 降級)----

    def subscribe_symbol(self, product: str) -> None:
        self._ensure_connected()
        if self._sub_port is not None:
            # 真連線才有 SubPort;漏啟 listener = 訂閱成功但永收不到推播(07-21 實證)
            self._start_listener()
        sym = futures_symbol(product)
        self._rt_request("UNSUBQUOTE", sym)
        r = self._rt_request("SUBQUOTE", sym)
        if r.get("Success") != "OK":
            raise ConnectionError(f"SUBQUOTE fail {sym}: {r.get('ErrMsg')}")
        self._subscribed.add(sym)

    def unsubscribe_symbol(self, product: str) -> None:
        sym = futures_symbol(product)
        if sym in self._subscribed:
            self._rt_request("UNSUBQUOTE", sym)
            self._subscribed.discard(sym)

    def subscribe_leaf(self, product: str, ym: str) -> None:
        """補訂實際月份 leaf 契約(TC.F.TWF.<p>.<YYYYMM>)。

        HOT 與 TXO runtime 的 spot 訂閱同 symbol 時,TC4 只推一邊(2026-07-28 盤中實證,
        同 process 四 session);leaf 字串不同即無衝突。冪等同 subscribe_symbol。"""
        self._ensure_connected()
        if self._sub_port is not None:
            self._start_listener()
        sym = f"TC.F.TWF.{product}.{ym}"
        self._rt_request("UNSUBQUOTE", sym)
        r = self._rt_request("SUBQUOTE", sym)
        if r.get("Success") != "OK":
            raise ConnectionError(f"SUBQUOTE fail {sym}: {r.get('ErrMsg')}")
        self._subscribed.add(sym)

    def subscribe_all(self) -> None:
        for product in PRODUCTS:
            self.subscribe_symbol(product)

    # ---- listener:原始分派(覆寫 TXO 的 Tick 解析路徑;同 stock_source)----

    def handle_raw(self, raw: str) -> None:
        """SUB socket 一則原始電文 → REALTIME Quote dict 分派(listener 與測試共用)。"""
        idx = raw.find(":")
        if idx < 0:
            return
        try:
            msg = json.loads(raw[idx + 1 :])
        except json.JSONDecodeError:
            return
        if msg.get("DataType") != "REALTIME":
            return
        if self._on_message is not None:
            self._on_message(msg.get("Quote", {}))

    def _listen_loop(self) -> None:
        import zmq

        ctx = zmq.Context()
        sock: Any | None = None
        bound_port: str | None = None
        while not self._stop.is_set():
            if sock is None or self._sub_port != bound_port:
                # generation-following:重連換 SubPort 必須跟隨(07-20 盤中實證,同 tc4.py)
                if sock is not None:
                    sock.close(linger=0)
                sock = ctx.socket(zmq.SUB)
                sock.connect(f"tcp://127.0.0.1:{self._sub_port}")
                sock.setsockopt_string(zmq.SUBSCRIBE, "")
                sock.setsockopt(zmq.RCVTIMEO, 1_000)
                bound_port = self._sub_port
            try:
                raw = (sock.recv()[:-1]).decode("utf-8")
            except zmq.ZMQError:
                self._check_stale()
                continue
            self._last_msg = time.monotonic()
            self.handle_raw(raw)
        if sock is not None:
            sock.close(linger=0)
        ctx.term()
