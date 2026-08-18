"""相關係數引擎的行情源:泛化任意 TC4 symbol 訂閱(SC-5;design §5.5)。

與 `futures_source.FuturesQuoteSource` 的兩點關鍵差異:

1. **不限交易所段**:`futures_source.futures_symbol` 寫死 `TC.F.TWF.` 前綴,
   本引擎要訂 SGX / CBOT / CME 三段,故改吃完整 symbol 字串(由設定檔給)。
2. **訂閱窗覆寫為全天窗**:基底 `TC4QuoteSource._rt_window` 用
   `session_window(session_key())` —— 那是**台指期**盤別窗(日盤 UTC 00–06 /
   夜盤 UTC 06–22)。海外腿時段不同(美股現貨 UTC 13:30–20:00),在台指日盤窗訂
   CME 會落在窗外。且 TC4 對訂閱一律回 `Success: OK`(CLAUDE.md §8),窗不匹配的
   失效樣態是「訂閱成功但零推播」,沒有錯誤訊號 —— 靠 log 抓不到,只能靠設計避開。

全天窗 `({ymd}00, {ymd}23)` 即 Phase 0 probe 實測有效者(2026-07-29 23:09 六腿全推播)。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from copycat.live.river_backfill import collect_1k_minutes
from copycat.live.tc4 import TC4QuoteSource
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
        heal_silence_secs: float | None = 120.0,
        heal_symbol_silence_secs: float | None = 240.0,
    ) -> None:
        # 門檻放寬一倍:海外腿(SGX/CBOT/CME)時段錯開、成交稀疏,台指門檻會把
        # 「這條腿現在本來就沒人交易」誤判成零推播。不設盤別閘 —— 全天窗本就跨時段。
        super().__init__(
            port,
            api=api,
            session=session,
            poll_wait_secs=poll_wait_secs,
            heal_silence_secs=heal_silence_secs,
            heal_symbol_silence_secs=heal_symbol_silence_secs,
        )
        self._on_message: Callable[[dict], None] | None = None

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        self._on_message = cb

    # ---- 訂閱窗覆寫(本類別存在的主要理由)----

    def _rt_window(self, symbol: str) -> tuple[str, str]:
        return all_day_window()

    # ---- 泛化 symbol 訂閱(UNSUB→SUB 冪等;失敗 raise 供引擎降級)----

    def subscribe_raw(self, symbol: str) -> None:
        self._ensure_connected()
        if self._sub_port is not None:
            # 真連線才有 SubPort;漏啟 listener = 訂閱成功但永收不到推播(07-21 實證)
            self._start_listener()
        self._resub(symbol)

    def unsubscribe_raw(self, symbol: str) -> None:
        self._unsub(symbol)

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
        msg = self._realtime_msg(raw)
        if msg is None:
            return
        if self._on_message is not None:
            self._on_message(msg.get("Quote", {}))
