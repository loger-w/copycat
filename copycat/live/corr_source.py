"""相關係數引擎的行情源:泛化任意 TC4 symbol 訂閱(SC-5;design §5.5)。

與 `futures_source.FuturesQuoteSource` 的兩點關鍵差異:

1. **不限交易所段**:`futures_source.futures_symbol` 寫死 `TC.F.TWF.` 前綴,
   本引擎要訂 SGX / CBOT / CME 三段,故改吃完整 symbol 字串(由設定檔給)。
2. **訂閱窗覆寫為全天窗**:基底 `TC4QuoteSource._rt_window` 用
   `session_window(session_key())` —— 那是**台指期**盤別窗(日盤 UTC 00–06 /
   夜盤 UTC 06–22)。海外腿時段不同(美股現貨 UTC 13:30–20:00),在台指日盤窗訂
   CME 會落在窗外。且 TC4 對訂閱一律回 `Success: OK`(CLAUDE.md §8),窗不匹配的
   失效樣態是「訂閱成功但零推播」,沒有錯誤訊號 —— 靠 log 抓不到,只能靠設計避開。

全天窗 `({ymd}00, {ymd}23)` 即 Phase 0 probe 實測有效者(2026-07-29 23:09 各腿全推播)。
"""

from __future__ import annotations

import datetime as _dt
import logging
import time
from typing import Any, Callable

from copycat.live.river_backfill import collect_1k_minutes
from copycat.live.stock_source import stock_window
from copycat.live.tc4 import TC4QuoteSource, always_symbol_active
from copycat.tc4common import TC4_DEFAULT_PORT

logger = logging.getLogger(__name__)

__all__ = [
    "TAIFEX_PREFIX",
    "TWS_PREFIX",
    "CorrQuoteSource",
    "all_day_window",
    "segment_leg_gate",
]

#: 台期交段前綴。同段的國外指數期貨(SXF 費半 / UDF 道瓊 / SPF 標普 / UNF 那斯達克)
#: 與台指**同時段同結算**(tc4-market-facts「海外商品」節)—— 它們的休市段就是台指的
#: 休市段,可以直接沿用期貨盤別閘。SGX / CME / CBOT / CFE / OSE 段各有自己的時段(且在
#: 台灣連假照開),沒有實測事實之前一律不閘。
TAIFEX_PREFIX = "TC.F.TWF."

#: 台股現貨段前綴(2026-08-26 F4 台積電腿)。現貨 09:00–13:30 收盤、**無夜盤**,與台期交
#: (收 13:45、夜盤到次日 05:00)不是同一把尺 —— 沿用台期交閘會讓整個夜盤都在對一條收盤了
#: 的腿發 UNSUB+SUB。故現貨段自己一把,吃個股 session 既有的那把牆鐘。
TWS_PREFIX = "TC.S.TWS."


def segment_leg_gate(
    *, taifex: Callable[[], bool], tws: Callable[[], bool]
) -> Callable[[str], bool]:
    """逐腿自癒閘(N051 + F4):依 symbol **前綴**分派時段閘,未列的段恆 True。

    corr 是唯一一條 session 上掛著**時段各不相同**的腿的:session 級的 `heal_active`
    只有「全開」或「全關」兩種答案 —— 全開時台期交國外指數腿在自己的休市段整晚落進
    R2「從未推播」母體(2026-08-21 M0:SXF 3 小時 8 發 UNSUB+SUB),全關則等於把在
    自己盤中的海外腿一起關掉(台灣連假時 SGX / CME 照開)。

    - `TC.F.TWF.` → `taifex`(台期交日夜盤,prod 帶交易日曆 AND `in_futures_session_now`)
    - `TC.S.TWS.` → `tws`(台股現貨日盤,prod 帶交易日曆 AND `in_stock_heal_window_now`)
    - 其餘(SGX / CME / CBOT / CFE / OSE)→ 恆 True

    **不做「猜海外時段」**:CME/SGX/CFE/OSE 的時段本專案沒有實測事實(OSE 只有 skill 記的
    OpenTime/CloseTime 一組),猜錯的失效樣態是「該救的腿整場不救」—— 比多幾發 churn
    嚴重得多。要收那半邊的前提是先拿 `QUERYINSTRUMENTINFO` 的 OpenCloseTime 落成事實。
    現貨段之所以敢閘,是因為台股日盤時段是本專案已經在用的既有事實,不是猜的。
    """

    def _gate(symbol: str) -> bool:
        if symbol.startswith(TAIFEX_PREFIX):
            return taifex()
        if symbol.startswith(TWS_PREFIX):
            return tws()
        return True

    return _gate


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
        heal_symbol_active: Callable[[str], bool] = always_symbol_active,
        heal_sparse_symbols: frozenset[str] = frozenset(),
    ) -> None:
        # 門檻放寬一倍:海外腿(SGX/CBOT/CME)時段錯開、成交稀疏,台指門檻會把
        # 「這條腿現在本來就沒人交易」誤判成零推播。不設 **session 級**盤別閘 ——
        # 全天窗本就跨時段,而各腿的時段各不相同(閘一開一關都會錯一半)。逐腿的閘
        # 由 `heal_symbol_active` 帶(prod 走 `segment_leg_gate`,見 `app._default_corr_source`)。
        super().__init__(
            port,
            api=api,
            session=session,
            poll_wait_secs=poll_wait_secs,
            heal_silence_secs=heal_silence_secs,
            heal_symbol_silence_secs=heal_symbol_silence_secs,
            heal_symbol_active=heal_symbol_active,
            heal_sparse_symbols=heal_sparse_symbols,
        )
        self._on_message: Callable[[dict], None] | None = None

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        self._on_message = cb

    # ---- 訂閱窗覆寫(本類別存在的主要理由)----

    def _rt_window(self, symbol: str) -> tuple[str, str]:
        # TWS 現貨腿(台積電)**必須**與個股引擎同一把訂閱窗(PR #111 review F-01):TC4 refcount
        # 以 symbol|DataType|Start|End 為 key、但上游 feed 以 symbol 為單位 —— 兩引擎各持一把不同
        # key 時,任一把歸零(自選移除 2330 / rollover / corr 收工)上游就退訂整個 symbol,另一邊
        # 靜默零推播只能等自癒(tc4-market-facts (b))。同一把 key 兩邊各持一份,count 2→1 永不歸零。
        # 日期用本機當日(與 stock_source 無日曆時的預設同式);非交易日兩邊可能不同日 → 兩把 key,
        # 但非交易日本來就沒推播,無害。
        if symbol.startswith(TWS_PREFIX):
            return stock_window(f"{_dt.date.today():%Y-%m-%d}")
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
        """當日 1K → [(台北 minute_end, close 毫點)]。

        **首頁在預算內未備妥 → `HistoryTimeoutError`**(bug/history-timeout-propagation;
        舊契約是「回空」)。回空是唯一把「暫時取不到」這個訊號丟掉的地方 —— 引擎會讀成
        「這條腿今天沒有 1K」而整天不再回補(2026-08-23 08:23 三腿同秒逾時的真實事故)。
        **首頁備妥但收割 0 列仍回 `[]`**:TC4 答得出首頁就代表它不忙,空就是空。
        `HistoryTimeoutError` 是 `ConnectionError` 子類 → 只寫 `except ConnectionError`
        的呼叫端行為不變(逐腿降級);要重試的 `corr_engine` 自己寫在它**之前**。
        """
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
