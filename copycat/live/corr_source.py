"""相關係數引擎的行情源:泛化任意 TC4 symbol 訂閱(SC-5;design §5.5)。

與 `futures_source.FuturesQuoteSource` 的兩點關鍵差異:

1. **不限交易所段**:`futures_source.futures_symbol` 寫死 `TC.F.TWF.` 前綴,
   本引擎要訂 SGX / CBOT / CME 三段,故改吃完整 symbol 字串(由設定檔給)。
2. **訂閱窗覆寫為全天窗**:基底 `TC4QuoteSource._rt_request` 用
   `session_window(session_key())` —— 那是**台指期**盤別窗(日盤 UTC 00–06 /
   夜盤 UTC 06–22)。海外腿時段不同(美股現貨 UTC 13:30–20:00),在台指日盤窗訂
   CME 會落在窗外。且 TC4 對訂閱一律回 `Success: OK`(CLAUDE.md §8),窗不匹配的
   失效樣態是「訂閱成功但零推播」,沒有錯誤訊號 —— 靠 log 抓不到,只能靠設計避開。

全天窗 `({ymd}00, {ymd}23)` 即 Phase 0 probe 實測有效者(2026-07-29 23:09 六腿全推播)。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from copycat.live.river_backfill import collect_1k_minutes
from copycat.live.tc4 import TC4QuoteSource, build_rt_request
from copycat.tc4common import TC4_DEFAULT_PORT

logger = logging.getLogger(__name__)

__all__ = ["CorrQuoteSource", "all_day_window"]


def all_day_window() -> tuple[str, str]:
    """當日 UTC 全天窗;不隨台指盤別變動(design §5.5)。"""
    ymd = time.strftime("%Y%m%d", time.gmtime())
    return (f"{ymd}00", f"{ymd}23")


class CorrQuoteSource(TC4QuoteSource):
    def __init__(
        self,
        port: str = TC4_DEFAULT_PORT,
        *,
        api: Any | None = None,
        session: str | None = None,
        poll_wait_secs: float = 1.0,
    ) -> None:
        super().__init__(port, api=api, session=session, poll_wait_secs=poll_wait_secs)
        self._on_message: Callable[[dict], None] | None = None

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        self._on_message = cb

    # ---- 訂閱窗覆寫(本類別存在的主要理由)----

    def _rt_request(self, request: str, symbol: str) -> dict:
        window = all_day_window()
        return self._session_req(lambda session: build_rt_request(request, session, symbol, window))

    # ---- 泛化 symbol 訂閱(UNSUB→SUB 冪等;失敗 raise 供引擎降級)----

    def subscribe_raw(self, symbol: str) -> None:
        self._ensure_connected()
        if self._sub_port is not None:
            # 真連線才有 SubPort;漏啟 listener = 訂閱成功但永收不到推播(07-21 實證)
            self._start_listener()
        self._rt_request("UNSUBQUOTE", symbol)
        r = self._rt_request("SUBQUOTE", symbol)
        if r.get("Success") != "OK":
            raise ConnectionError(f"SUBQUOTE fail {symbol}: {r.get('ErrMsg')}")
        self._subscribed.add(symbol)

    def unsubscribe_raw(self, symbol: str) -> None:
        if symbol in self._subscribed:
            self._rt_request("UNSUBQUOTE", symbol)
            self._subscribed.discard(symbol)

    # ---- 江波圖當日回補(index-river-chart SC-3)----

    def fetch_day_1k(self, symbol: str) -> list[tuple[int, int]]:
        """當日 1K → [(台北 minute_end, close 毫點)];首頁未備妥回空(引擎逐腿降級)。"""
        self._ensure_connected()
        return collect_1k_minutes(
            sub_history=self._sub_history,
            get_history=self._get_history,
            symbol=symbol,
            poll_wait=self._poll_wait,
        )

    # ---- listener:原始 Quote dict 分派(同 futures_source 手法)----

    def handle_raw(self, raw: str) -> None:
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
                # generation-following:重連換 SubPort 必須跟隨(07-20 盤中實證)
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
