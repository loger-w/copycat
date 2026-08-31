"""FastAPI app:route 只 raise 不 catch;error contract {"detail": {"error": code}}(§2)。"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import date as _date
from datetime import datetime as _datetime
from datetime import time as _clock_time
from datetime import timedelta as _timedelta
from pathlib import Path
from typing import AsyncGenerator, Awaitable, Callable, Final, TypeVar, cast

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from copycat.live.trade_models import BrokerRejectedError
from copycat.breadth_config import BreadthConfig, load_breadth_config
from copycat.capital import factory as capital_factory
from copycat.capital.client import CapitalClient
from copycat.server import build_info, breadth_fetch, finmind_token
from copycat.server.audit import AuditWriteError
from copycat.corr_config import CorrConfig, load_config as load_corr_config
from copycat.server.breadth_engine import (
    BreadthEngine,
    DailyPricesFetch,
    DispositionFetch,
    SnapshotFetch,
    StockInfoFetch,
)
from copycat.server.capital_api import register_capital
from copycat.server.oi_levels import register_oi
from copycat.server.ws import WsBroadcaster, relay
from copycat.server.corr_engine import CorrelationEngine, CorrSource
from copycat.server.engine import EngineRuntime, HandoverBusyError, QuoteSource
from copycat.server.futures_engine import FuturesEngine, FuturesSource
from copycat.server.index_engine import IndexEngine, IndexSource
from copycat.live.stock_source import Bar, BarsStatus, DailyBar
from copycat.live.tc4 import HistoryTimeoutError
from copycat.server.mis import OtcSnap, fetch_otc_snapshot
from copycat.server.bars import (
    BarsCache,
    BarsResult,
    TaggedBars,
    build_daily,
    build_minute,
    build_period,
    clamp_days,
    is_partial_last,
)
from copycat.notify import notify_discord
from copycat.server.discord_bot import Bot, create_bot
from copycat.server.overlay import OverlayCache, build_overlay
from copycat.server.shutdown_budget import SLOW_CLOSE_WARN_SECS
from copycat.server.signal_hub import SignalHub
from copycat.server.stkfut_catalog import StkfutCatalog
from copycat.server.stock_engine import (
    _CLIENT_QUEUE_MAX,
    WATCHLIST_BOOT_SEQ,
    StockEngine,
    StockSource,
)
from copycat.server.watchlist_service import WatchlistService
from copycat.signal_rules import Rule, RuleError
from copycat.signals_config import load_signals_config
from copycat.stock_watchlist import (
    WATCHLIST_LIMIT,
    Group,
    WatchlistError,
    load_watchlist,
    union,
    validate_code,
)
from copycat.stock_watchlist import DEFAULT_PATH as WATCHLIST_DEFAULT_PATH
from copycat.stock_names import DEFAULT_PATH as NAMES_DEFAULT_PATH
from copycat.stock_names import load_names as load_stock_names
from copycat.stkfut_map import lookup_product
from copycat.tc4common import TC4_DEFAULT_PORT
from copycat.live.session import session_key
from copycat.trading_calendar import (
    TradingCalendar,
    resolve_trade_date,
    resolve_trade_date_before,
)

logger = logging.getLogger(__name__)

#: 期指鍵(近全盤別 `session=allday` 專屬 —— 加權 / 櫃買沒有夜盤)。
FUTURES_MARKET_KEYS = ("TXF", "MXF", "TMF")

#: 大盤頁支援的標的鍵。值域小且固定 → 白名單比 regex 好:非法鍵一律 400 BAD_KEY,
#: 不讓打錯的字串一路走到 TC4 才回空(那會被誤讀成「沒資料」)。
MARKET_KEYS = ("TWSE", "OTC") + FUTURES_MARKET_KEYS

#: `?session=` 的值域。
MARKET_SESSIONS = ("day", "allday")

#: lifespan 關機各段的**輸出序**(彙總行用;不是執行序 —— 執行序見 lifespan finally 的註解:
#: 前三段序列、中間四條 TC4 lane 並行、capital 最後)。
_SHUTDOWN_SEGMENTS: Final = ("breadth", "signals", "corr", "futures", "index", "stock", "txo", "capital")

#: `/api/stock/overlay/{code}` 單檔取數的時間上界(group-grid review B2)。
#: TC4 對「查無此檔」不是快速失敗 —— `fetch_daily_bars` 內部兩段 deadline 各
#: `BARS_POLL_DEADLINE` = **10s**(bug/history-timeout-propagation 起兩段皆顯式帶;
#: 原本是預設的 `poll_wait*30` ≈ 30s × 2 = 最壞 60s)→ 現在最壞 **20s**。空結果依
#: `overlay.py` 規則不進 cache,於是每次請求都重付一次。配上 route 層 `Semaphore(4)`,
#: 四檔這種股號就足以把整個端點凍住(head-of-line):進群組時 50 張卡的 CDP/MA 全排在
#: 後面,而畫面上只是「疊線一直沒出來」,零錯誤訊號。
#: 15s > 正常取數(實測 <1s)一個數量級,又短於 source 的最壞 20s —— 也就是說
#: `asyncio.wait_for` 幾乎恆先到期,route 那條 `except (TimeoutError,
#: HistoryTimeoutError)` 的**後半是 defensive**:要兩段各自明顯快於 7.5s 卻雙雙逾時
#: 才走得到(兩者的降級完全相同,所以合在同一條分支;少了它會變成 500)。
#: 這個數字若日後被調到 > 20s,那條分支就從 defensive 變成主要路徑 —— 仍然是對的,
#: 不必跟著改。
OVERLAY_FETCH_TIMEOUT_S = 15.0

#: `/api/stock/state/{code}?contract=` 的形檢:`<prod>:<YYYYMM>`(stkfut-contracts D7)。
#: 只是第一道 —— 「這個合約屬不屬於這檔股票」必須另外查 catalog 白名單。
_CONTRACT_RE = re.compile(r"^[A-Z0-9]{2,4}:20\d{2}(0[1-9]|1[0-2])$")


def _with_unit(leg: dict | None) -> dict | None:
    """合約腿 + 契約單位股數(code review B2/B3)。查無對映 → `unit: None`。

    前端的 ETF 前置閘原本以「股號開頭為 0」推,那是這份資料**今天**的性質而不是契約
    規格;權威判準(`capital_api._stkfut_gates`)吃的是單位。單位隨清單一起送出,兩邊
    從此同一個判準,而查無時給 `None` 讓前端明確落回 fallback —— 塞 0 會被讀成
    「非股票單位」→ 誤擋一檔本來可以下單的標的,而後端那道真閘根本沒被觸發過。
    """
    if leg is None:
        return None
    found = lookup_product(leg["prod"])
    return {**leg, "unit": None if found is None else found.get("unit")}


def _market_payload(
    key: str,
    tf: str,
    bars: list[Bar],
    *,
    source: str,
    volume: bool | None = None,
    partial_last: bool = False,
    refusal: str | None = None,
    synth_since: str | None = None,
    status: BarsStatus | None = None,
) -> dict:
    """大盤 K 線回應(index-board N-5)。

    `meta` 不是裝飾:前端固定把它渲染成一行「來源 · 涵蓋期間」,讓「壞了 vs 沒資料」
    看畫面就能答(/adhd 三個 frame 收斂到的同一點)。`source` 必須是**實際走到的分支**,
    不能是預期值 —— DK 空時 fallback 成 1K 聚合而 meta 仍標 tc4_dk,等於在最可能出事的
    那條路上說謊(review P1-4)。

    `status`(N104)與 `source` 是**兩把不同的尺**,同為 str 但不可互換:`source` 答
    「這份 bar 從哪來」,`status` 答「這一趟取數的結果」(ok / timeout / disconnected)。

    **`None` = 這條路徑還沒有三態訊號 → `meta` 裡連這一格都不給**(review SP4)。
    硬寫 `"ok"` 是謊報:index proxy miss 時 payload 會變成 `source:"unavailable"` +
    `status:"ok"`,而後者的意思正好是「問到了、就是沒有」。缺欄是誠實的「不知道」,
    前端的 `?? "ok"` 也已經吃得下 undefined。
    """
    # volume 未指定時**由資料判定**:指數(IX0001)的 DK/1K 沒有量欄位,`_int_field`
    # 缺值回 0 → 整條序列 v=0。標 volume=true 會讓前端畫一排貼底的 0 高柱,與「真的
    # 零成交」在畫面上無法區分 —— 正是 SC-6 要避免的假造零(2026-07-30 real-env 抓到)。
    has_volume = volume if volume is not None else any(b["v"] > 0 for b in bars)
    meta: dict = {
        "source": source,
        "coverage_from": bars[0]["t"][:10] if bars else None,
        "coverage_to": bars[-1]["t"][:10] if bars else None,
        "partial_last": partial_last,
        "volume": has_volume,
        "refusal": refusal,
        "synth_since": synth_since,
    }
    if status is not None:
        meta["status"] = status
    return {"key": key, "tf": tf, "bars": bars, "meta": meta}


# sentinel:__main__ 顯式傳入才建真 source(測試不傳 → None → 零連線)
DEFAULT_STOCK: Final = object()  # __main__ 傳入才建真 StockQuoteSource
DEFAULT_INDEX: Final = object()  # 同語意(index-board IR9)
DEFAULT_FUTURES: Final = object()  # 同語意(capital-order SC-8)
DEFAULT_CORR: Final = object()  # 同語意(realtime-correlation SC-6)
DEFAULT_BREADTH: Final = object()  # 同語意(market-overview R2 SC-3;→ 真 FinMind 取數層)

#: breadth 引擎的注入點四元組(snapshot / stock_info / disposition / daily_prices)。
#: 第四槽 `None` = 連板數停用(rows 端點照常、`streak` 恆 null)—— 停用是契約的一部分,
#: 不用 cast 掩蓋(R3 design R20)。長度固定 4。
BreadthFetchers = tuple[
    SnapshotFetch,
    StockInfoFetch,
    DispositionFetch,
    DailyPricesFetch | None,
]


class SelectBody(BaseModel):
    series_id: str


class GroupBody(BaseModel):
    name: str
    codes: list[str]


class GroupsBody(BaseModel):
    groups: list[GroupBody]
    codes: list[str] | None = None  # v3 自選全體;缺省 → union(groups)(舊 client 相容)


class RuleBody(BaseModel):
    """訊號規則的**形狀**層;語意(值域 / 唯一名 / levels / kind)單一定義在 `normalize_rule`。

    每個欄位都宣告成 `object` 且給 None 預設,兩個理由都是為了守住錯誤契約:
    宣告成 `bool`/`int` 會讓 pydantic 把 "yes"/"3" 寬鬆轉型、把打錯的值靜默收下;
    宣告成必填則缺欄回 422 + list 形 detail,不符全站 `{"detail": {"error": code}}`
    ——缺欄要走 400 INVALID_RULE(signal-rules R10)。
    """

    #: id 同樣是 `object`(review A6(1)):宣告成 `str | None` 時,`{"id": 123}` 會在
    #: pydantic 那層變成 422 + list 形 detail —— 破的正是這個 class 存在的理由。
    #: 用 object 收下來後由 PUT 自己比對(型別不符 → `!=` 成立 → 400 INVALID_RULE);
    #: POST 不看(id 由 hub 配)。
    id: object = None
    name: object = None
    kind: object = None
    enabled: object = None
    notify_discord: object = None
    cooldown_secs: object = None
    params: object = None
    cdp_levels: object = None

    def payload(self) -> dict:
        """送進 hub 的規則欄位(去掉 id — 那由 route 的 path / hub 決定)。"""
        return self.model_dump(exclude={"id"})


def _tc4_port() -> str:
    return os.environ.get("TC4_PORT", TC4_DEFAULT_PORT)


_BootT = TypeVar("_BootT")


async def _boot(
    name: str,
    fail_msg: str,
    make: Callable[[], _BootT | None],
    start: Callable[[_BootT], Awaitable[None]],
    close: Callable[[_BootT], Awaitable[None]],
) -> _BootT | None:
    """引擎起停樣板(B-D7):任一引擎起不來都只讓自己停用,不波及其他引擎。

    兩段式而非單一 `build`:**`make` 與 `start` 都必須在同一個 try 內**,而 except
    分支要拿得到已建好的物件才關得掉 —— 「建構成功但 start 失敗」若沒 close,會洩漏
    一條已連線的 TC4 session,畫面只看得到 503。

    - `make` 回 `None` = sentinel 解析結果為「不啟動」→ 整段跳過,**不記失敗 log**。
    - `start` 語意 = 「帶到就緒的全部工作」,不只 `o.start()`:stock 的自選回填也在內
      (`load_watchlist` 對壞檔不吞例外,現況正是由這個 except 接住)。
    - 序列跑在背景 task,關機會 cancel 它 → **`CancelledError` 要單獨接**(`except
      Exception` 接不到):已建好的物件不關就是一條洩漏的 TC4 session。close 內部多為
      `asyncio.to_thread`,執行緒派出去後不受 cancel 影響,會自然跑完。
    """
    obj: _BootT | None = None
    try:
        obj = make()
        if obj is None:
            return None
        await start(obj)
        return obj
    except asyncio.CancelledError:
        if obj is not None:
            # best-effort:二次 cancel 會讓這個 await 就地拋,log 後把原本的
            # CancelledError 交還關機路徑(shield 救不了 —— 孤兒 close task 一樣沒人 await)
            try:
                await close(obj)
            except asyncio.CancelledError:
                # 預期路徑(二次 cancel 打斷 close),不是錯誤 → 不吐 ERROR traceback,
                # 分法與 lifespan finally 的 CancelledError / Exception 兩分一致
                logger.info("%s close 被二次 cancel 中斷(關機續行)", name)
            except Exception:
                logger.exception("%s close 失敗(關機中斷 boot,忽略)", name)
        raise
    except Exception:
        logger.exception("%s", fail_msg)
        if obj is not None:
            try:
                await close(obj)
            except Exception:
                logger.exception("%s close 失敗(忽略)", name)
        return None


@dataclass
class _Booted:
    """boot 序列實際掛上去的引擎 —— 關機反序 close 的唯一來源。

    `_boot_all` 與 lifespan 的 finally 不再共用同一組 local(序列本身要能獨立於
    lifespan 的執行點推進),record 就是兩者之間那條界線:finally 只關「record 裡
    有值的」,None = 沒起來或還沒輪到,跳過。

    `signals_close` 存 callable 而非只存 hub:signals 的收攤要先關 bot、再從 engine
    摘掛點、最後才關 hub(`_close_signals` 的 closure),那個順序不能在 finally 重寫。
    """

    stock: StockEngine | None = None
    signals: SignalHub | None = None
    signals_close: Callable[[SignalHub], Awaitable[None]] | None = None
    index: IndexEngine | None = None
    capital: CapitalClient | None = None
    futures: FuturesEngine | None = None
    corr: CorrelationEngine | None = None
    breadth: BreadthEngine | None = None
    #: SC-7 的背景交叉檢查(不是引擎,但關機一樣要 cancel —— 沒人 await 的 task
    #: 會在 loop 關閉時留下「Task was destroyed but it is pending」)
    crosscheck_task: asyncio.Task[None] | None = None


def _heal_gate(
    calendar: TradingCalendar | None, clock_gate: Callable[[], bool]
) -> Callable[[], bool]:
    """自癒閘 = 牆鐘時段 **AND 那一場有開盤**;`calendar=None` 逐字等於改動前的純牆鐘。

    純牆鐘的失效樣態:週末 / 國定假日整天閘都成立 → 每 5s 巡檢一次、對 TC4 上游
    送 UNSUB+SUB,而那些 symbol 在休市日本來就不會有推播 → 退避爬到 300s 之後仍
    整天不停。我方全鏈零訊號(自癒 log 本來就是 warning 級的日常),只有 TC4 那頭
    的 QuoteZMQService log 看得出來。

    日期取樣走 `_session_date()`(**場別起始日**,不是牆鐘今天):夜盤跨午夜,凌晨
    那幾小時屬前一日開的那一場。用 `_today()` 的話兩頭都錯 —— 週六 00:00–05:00
    查到週六 → 該救不救;週一 01:00 查到週一 → 空 churn(週日沒有夜盤,而凌晨的
    clock_gate 為真)。stock / index 的 clock_gate 凌晨恆 False,不受這一改影響。
    """
    if calendar is None:
        return clock_gate
    return lambda: calendar.is_trading_day(_session_date()) and clock_gate()


def _txo_auto_backfill_date(calendar: TradingCalendar | None) -> Callable[[], str | None]:
    """TXO 回補窗的自動日期(L77;env `TXO_BACKFILL_DATE` 未設時的 fallback)。

    回 None = 那一場活著(場別起始日是交易日 AND 牆鐘在盤中)→ live session 窗。
    回 YYYYMMDD = 休市段(休市日整天 / 交易日盤前 08:45 前 / 13:45–15:00 收盤段)→
    最近「日盤已經開過」的交易日固定日盤窗 —— 盤前冷啟動 TXO 面維持前一交易日資料,
    開盤時 runtime 的 window identity 變化觸發 rollover 切回 live 窗(D3:TXO 開盤 stage)。
    無日曆 = 恆 None = 改動前行為(休市要看 TXO 仍靠手動 env)。
    """
    if calendar is None:
        return lambda: None
    from copycat.live import session as session_mod

    def resolve() -> str | None:
        now = _now()
        if calendar.is_trading_day(_session_date()) and session_mod.in_txo_session(now.time()):
            return None
        d = now.date()
        if calendar.is_trading_day(d) and now.time() < _clock_time(8, 45):
            d -= _timedelta(days=1)  # 交易日盤前:今天日盤還沒開,資料在前一交易日
        return resolve_trade_date(d, calendar).strftime("%Y%m%d")

    return resolve


def _default_source(calendar: TradingCalendar | None = None) -> QuoteSource:
    from copycat.live import session as session_mod
    # 延遲 import:測試不觸 pyzmq/TC4
    from copycat.live.tc4 import TXO_HEAL, TC4QuoteSource

    return TC4QuoteSource(
        port=_tc4_port(),
        backfill_date=os.environ.get("TXO_BACKFILL_DATE"),
        # 盤前 / 休市自動日(L77);env 有值時 TC4QuoteSource 內 env 恆優先
        auto_backfill_date=_txo_auto_backfill_date(calendar),
        # REALTIME 零推播自癒(fix/tc4-realtime-refcount-kill):TXO 是唯一直接用基底類的
        # session,基底預設全關 → 這裡顯式開 R1(60s 全場靜默 → 整批重掛)、R2 關(277 檔
        # 深價外契約本就靜默),閘 = 日盤/夜盤牆鐘 AND 交易日。
        heal=replace(TXO_HEAL, active=_heal_gate(calendar, session_mod.in_txo_session)),
    )


def _default_stock_source(calendar: TradingCalendar | None = None) -> StockSource:
    from copycat.live import stock_source as stock_mod  # 延遲 import:測試不觸 pyzmq

    # 個股走既有的 `in_trading_hours` 注入點(健檢與自癒同一把閘),不另開參數
    return stock_mod.StockQuoteSource(
        port=_tc4_port(),
        in_trading_hours=_heal_gate(calendar, stock_mod.in_stock_heal_window_now),
    )


def _default_index_source(calendar: TradingCalendar | None = None) -> IndexSource:
    from copycat.live import stock_source as stock_mod  # 獨立 session(指數專用)

    # 指數拿**自己的**牆鐘(13:25 收盤試撮起指數不更新,看門狗誤判 19 發 / 日),不與個股共用
    # 13:35 那把:個股在 13:25–13:30 仍有簿更新推播,一起關掉是零收益純代價(pr-126 F-01)。
    # 注入參數仍是 `in_trading_hours`(健檢與自癒同一把),只換牆鐘不動簽名。
    return stock_mod.StockQuoteSource(
        port=_tc4_port(),
        in_trading_hours=_heal_gate(calendar, stock_mod.in_index_heal_window_now),
    )


def _default_futures_source(calendar: TradingCalendar | None = None) -> FuturesSource:
    from copycat.live import futures_source as futures_mod  # 延遲 import:測試不觸 pyzmq

    # 閘 = 交易日曆 AND 盤別(日夜盤各寬 5 分)。原本是 always:假日整天、以及日盤收後
    # 13:45–15:00 與夜盤收後 05:00–08:45 兩段都在對 TC4 空 churn UNSUB+SUB
    return futures_mod.FuturesQuoteSource(
        port=_tc4_port(),
        heal=replace(
            futures_mod.FUTURES_HEAL,
            active=_heal_gate(calendar, futures_mod.in_futures_session_now),
        ),
    )


def _default_corr_source(
    calendar: TradingCalendar | None = None, *, config: CorrConfig
) -> CorrSource:
    from copycat.live import futures_source as futures_mod  # 延遲 import:測試不觸 pyzmq
    from copycat.live import stock_source as stock_mod
    from copycat.live.corr_source import CORR_HEAL, CorrQuoteSource, segment_leg_gate

    # **逐腿**閘(N051),不是 session 級:corr 這條 session 上同時掛著台期交段、台股現貨段
    # 與 SGX/CME/CBOT/CFE/OSE 段的腿,時段各不相同。session 級的閘全開時,台期交段的國外
    # 指數腿(SXF/UDF/SPF/UNF,與台指同時段同結算)在自己的休市段整晚每 240s 一發
    # UNSUB+SUB(2026-08-21 M0:SXF 三小時 8 發);全關則會把在自己盤中的海外腿一起
    # 關掉(台灣連假 SGX / CME 照開)。日曆也只 AND 在有閘的那兩段,理由同上。
    #
    # 現貨腿(F4 台積電)吃**個股** session 那把 `in_stock_heal_window_now`,不是期貨那把:
    # 現貨 13:30 收盤且無夜盤,套期貨閘 = 整個夜盤都在對一條收盤了的腿空 churn。
    #
    # 稀疏腿(SXF 費半,事實見 tc4-market-facts)豁免 R2:旗標來自設定檔 `sparse`,與時段閘
    # 正交 —— 它仍留在 R1 母體。只看 `tc4_legs()`:base 腿不由本 source 訂閱,標了也沒有 R2 可豁免
    # (load_config 會對這種誤標印 WARNING)。`config` **必填**(pr-120 F-04):source 的稀疏腿集合與
    # engine 的腿組必須吃同一份(lifespan 只讀一次再分兩處),不留 fallback 讓「各讀各的」在結構上合法;
    # keyword-only 讓 `calendar` 的預設值與四個兄弟工廠同形。
    return CorrQuoteSource(
        port=_tc4_port(),
        heal=replace(
            CORR_HEAL,
            symbol_active=segment_leg_gate(
                taifex=_heal_gate(calendar, futures_mod.in_futures_session_now),
                tws=_heal_gate(calendar, stock_mod.in_stock_heal_window_now),
            ),
            sparse_symbols=frozenset(leg.symbol for leg in config.tc4_legs() if leg.sparse),
        ),
    )


def _session_date() -> _date:
    """現在這一刻所屬**場別的起始日**(夜盤跨午夜歸前一日),**不是 TAIFEX 交易日**。

    06:00 切換:夜盤 05:00 收盤 + 自癒閘的 5 分寬放都在門檻內,日盤 08:45 尚未開。

    **判準(不是清單)**:凡是在答「資料屬於哪個交易日」的一律用 `_today()`(含
    `_calendar_crosscheck`);只有在答「現在是誰的場」時才用本函式,而目前唯一這樣問的
    是 `_heal_gate`。原本這裡列的是逐個呼叫點,新增一處就漏一處(`_calendar_crosscheck`
    正是這樣漏掉的),改記判準。

    **近似誤差**:夜盤存在與否其實取決於**次一營業日**(封關夜那類:起始日是交易日
    但隔天休市 → 當晚無夜盤,閘仍為真 → 空 churn)。方向安全(不會該救不救),頻率
    也低,故不引入「下一交易日」判定。
    """
    now = _now()
    d = now.date()
    return d - _timedelta(days=1) if now.hour < 6 else d


def _today() -> _date:
    """牆鐘今天 —— 日曆**交易日**推導的唯一取樣點(mod/trading-calendar Q9);
    場別起始日另見 `_session_date`。

    涵蓋範圍逐條:`trade_date` 推導(`_resolve_trade_date`)、overlay 基準日、
    `/api/calendar.today`。散在各處的 `date.today()` 讓「跨午夜那一瞬用了兩個不同的
    日子」無法被測試釘住,也讓假日冷啟動的整條推導沒有注入點。

    **例外(刻意保留)**:`/api/stock/bars` 與 `/api/market/bars` 依 W3 仍直呼
    `_date.today()` —— K 線的日期邏輯本輪不動,把它們一起收進來就是改 W3 白名單內的
    行為。要動 K 線日期時再一起搬,不要以為這裡已經涵蓋了。
    """
    return _date.today()


def _now() -> _datetime:
    """牆鐘現在(SC-7 交叉檢查的 14:00 門檻);同 `_today` 的單一取樣點理由。"""
    return _datetime.now()


def create_app(
    source: QuoteSource | None = None,
    *,
    stock_source: StockSource | object | None = None,
    index_source: IndexSource | object | None = None,
    futures_source: FuturesSource | object | None = None,
    corr_source: CorrSource | object | None = None,
    breadth_fetchers: BreadthFetchers | object | None = None,
    breadth_data_dir: Path | None = None,
    breadth_config: BreadthConfig | None = None,
    index_mis_fetch: Callable[[], OtcSnap | None] = fetch_otc_snapshot,
    stock_watchlist_path: Path | None = None,
    stock_names_path: Path | None = None,
    trading_calendar: TradingCalendar | None = None,
    throttle_secs: float = 1.0,
    queue_maxsize: int = 10_000,
) -> FastAPI:
    """`trading_calendar=None`(預設)= 無日曆 = 牆鐘,逐字等於改動前的行為。

    prod 由 `__main__` 顯式傳 `load_trading_calendar()`(對齊 DEFAULT_STOCK /
    DEFAULT_BREADTH 的「prod 顯式、測試預設關」慣例):39 個既有測試呼叫點以
    `date.today()` 對照,預設載真日曆會讓整批測試在週末全紅。
    """
    wl_path = stock_watchlist_path if stock_watchlist_path is not None else WATCHLIST_DEFAULT_PATH
    # 名稱表是版控檔(必然存在)→ 沒有注入點的話「表不可用」這條降級路徑無法測
    names_path = stock_names_path if stock_names_path is not None else NAMES_DEFAULT_PATH
    overlay_cache = OverlayCache()  # per-app 實例(impl-spec R9:module-level 跨測試汙染)
    # overlay 的 TC4 歷史取數節流(group-grid AD-5 amendment R5)。群組檢視的 `cdp`
    # 預設是開的 → 一進群組就對最多 50 檔同時打 `/api/stock/overlay`,而
    # `daily_bars` 走 `to_thread` 沒有上限、50 條請求共用同一條 TC4 歷史通道。
    # 擋在 **route 層**而不是 `engine.daily_bars`:後者另有 `signal_hub` 的 basis
    # 取數在用(signal_hub.py:662),節流下沉到引擎會連訊號的 basis 一起拖慢。
    overlay_sem = asyncio.Semaphore(4)
    bars_cache = BarsCache()  # 同上;K 線兩段式 cache(server/bars.py)
    capital_ws = WsBroadcaster()  # capital/futures WS fanout(lifespan 綁 publish)
    # 個股 WS 匯流排住 app 層而非 engine 內(XR-3):`/ws/stock` 同時載自選 quote
    # (engine 產)與訊號(hub 產),而 hub 恆建、與達錢 4 在否無關 —— 綁在 engine
    # 身上時 TC4 沒開就整條通道死掉。上限沿用 engine 的 `_CLIENT_QUEUE_MAX`(私名共用:
    # 兩份上限值必然漂移,而 ws.py 的公開 `CLIENT_QUEUE_MAX` 是另一個值)。
    stock_ws = WsBroadcaster(maxsize=_CLIENT_QUEUE_MAX)
    futures_ws = WsBroadcaster()
    corr_ws = WsBroadcaster()
    river_ws = WsBroadcaster()  # 江波圖每秒 delta(全量走 REST/WS 首則;index-river-chart SC-5)

    def _resolve_trade_date(before: _clock_time | None = None) -> str:
        """引擎 / overlay / hub fallback 共用的「今天在看哪一天」(Q9)。

        **每次呼叫求值**:boot 時算一次的靜態字串會在長跑跨日後停在昨日,而 hub 的
        `_distribute` 日別尺、jsonl 檔名與 `today_signals` 讀取集全都以它為準 ——
        壞掉的樣態是「今天的訊號寫進昨天的檔」,完全靜默。

        `TXO_BACKFILL_DATE` **最高優先**(W2:手動回補是 ops 通道,日曆不得蓋掉它);
        其次走日曆的最近交易日;無日曆 = 牆鐘 = 改動前行為。日曆推導一律經
        `resolve_trade_date` —— 缺當年的 WARNING 節流入口就在那裡,自己呼
        `last_trading_day` 會靜默跳過提醒。
        """
        env = os.environ.get("TXO_BACKFILL_DATE")
        if env:
            return env
        if trading_calendar is None:
            return _today().isoformat()
        if before is not None:
            # L77 盤前冷啟動:交易日 stage 時刻前 = 前一交易日(各面沿自家 stage:
            # stock 08:00 / index 08:30),之後由各引擎既有 rollover 機制換今日。
            # 只有兩個 boot 時刻的 ctor 呼叫帶 before;hub / overlay 等逐次求值的
            # caller 不帶 = 語意逐字不變。
            return resolve_trade_date_before(_now(), trading_calendar, before).isoformat()
        return resolve_trade_date(_today(), trading_calendar).isoformat()

    async def _calendar_crosscheck(index: IndexEngine) -> None:
        """日曆 vs 實際 DK 的雙向交叉檢查(SC-7)—— 靜態 config 唯一的體檢管道。

        兩個方向對應兩種故障:DK 比日曆新 = 日曆把真交易日標成了假日(KR-1,當天
        index 不換日);最近交易日沒有 DK = 臨時休市(颱風假,靜態 config 預知不了,
        KR-3)→ 提示改設 `TXO_BACKFILL_DATE`。

        期望日刻意**不含今天**(除非今天非交易日或已過 14:00):交易日盤中今天的 DK
        本來就還不存在,拿今天當期望會讓每天早上重啟都誤報一次 —— 天天亮的 WARNING
        等於沒有 WARNING。

        probe 直呼 `index.bars_range` 不經 `bars_cache`:boot 當下的結果灌進共用格會
        污染 `/api/market/bars` 與 index overlay。整段自吞例外只 log:它是一則提示,
        不是 index 的啟動條件(`_boot` 的傘不得因它把 index 收掉)。
        """
        cal = trading_calendar
        if cal is None:
            return
        try:
            today = _today()
            bars, _tag = await index.bars_range(
                "D", (today - _timedelta(days=14)).isoformat(), today.isoformat()
            )
            if not bars:
                logger.info("交易日曆交叉檢查:IX0001 無日 K 可比對(TC4 不可用?),略過")
                return
            last = _date.fromisoformat(bars[-1]["t"][:10])
            latest_trading = cal.last_trading_day(today)
            if last > latest_trading:
                logger.warning(
                    "交易日曆可能過期:IX0001 DK 有 %s 但日曆判非交易日,"
                    "請更新 configs/trading_holidays.json",
                    last,
                )
                return
            # 14:00 與 bars.DAILY_FINAL_TIME 字面同值、語意不同:這把問「今日 IX0001 DK
            # **存在**了沒」,那把問「**定稿**了沒」—— 刻意不共用常數;改任一值前先看對方
            # (pr-165-review #1)
            if not cal.is_trading_day(today) or _now().time() >= _clock_time(14, 0):
                expected = latest_trading
            else:
                expected = cal.last_trading_day(today - _timedelta(days=1))
            if last < expected:
                logger.warning(
                    "最近交易日 %s 無 IX0001 DK 資料(臨時休市?請設 TXO_BACKFILL_DATE "
                    "或更新交易日曆)",
                    expected,
                )
        except asyncio.CancelledError:
            raise  # 關機中斷:不得被下面的傘吃掉(那會讓 close 路徑以為它正常結束)
        except Exception as e:
            logger.warning("交易日曆交叉檢查失敗(略過):%r", e)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        # 最先做:引擎起不來時 banner 也要印得出來(「這台是哪一版」是排查的第一個問題)
        app.state.build = build_info.capture()
        logger.info("%s", app.state.build.banner())
        runtime = EngineRuntime(
            source if source is not None else _default_source(trading_calendar),
            throttle_secs=throttle_secs,
            queue_maxsize=queue_maxsize,
            # 固定日回補模式(休市日)停用時段切換偵測:跨界重跑只會重拿同一份
            # 指定日資料(spec R5)
            session_rollover=os.environ.get("TXO_BACKFILL_DATE") is None,
            # 窗 identity 併入自動日(L77):盤前固定日 → 開盤 live 窗(08:45)也要
            # 觸發交接,否則前一交易日的種子會與開盤後 live tick 混同一份 agg
            window_ident_fn=(
                (lambda auto=_txo_auto_backfill_date(trading_calendar): (session_key(), auto()))
                if os.environ.get("TXO_BACKFILL_DATE") is None and trading_calendar is not None
                else None
            ),
        )
        # 未 started 的 runtime 照樣掛上去:route 對它的 None 沒有 guard,但「已建構
        # 未 started」本來就走既有 NOT_READY / 空鏈語意(current-state §4),不需新分支
        app.state.runtime = runtime
        # 其餘九個先掛 None:窗內的對外形狀 = 既有「引擎降級」形狀(503 / WS close /
        # breadth 的 enabled=false 三態)
        app.state.stock = None
        app.state.stkfut_catalog = None
        app.state.watchlist_service = None
        app.state.signal_hub = None
        app.state.discord_bot = None
        app.state.index = None
        app.state.capital = None
        app.state.futures = None
        app.state.corr = None
        app.state.breadth = None
        app.state.calendar_crosscheck = None  # SC-7 背景 task(有日曆時才建)
        # 兩者必須同點初始化:少了 boot_error,正常路徑的 /api/ready 直取屬性會
        # AttributeError → 被全域 handler 轉成 502
        app.state.boot_done = False
        app.state.boot_error = None
        booted = _Booted()

        async def _boot_all() -> None:
            """引擎啟動序列(背景 task)。**順序即依賴**(current-state §2),不可重排、
            不可並行:watchlist_service 先於 signals、signals **可獨立於 stock**(XR-3;
            但 stock 在場時要在它之後才接得上掛點)、index 綁 runtime.spot、capital 先
            set_broadcast 再 start、corr 後於 futures。

            每完成一段就同時寫 `app.state.X` 與 `booted.X` —— 前者給 route,後者給
            關機反序 close(兩者必須成對,漏寫 record 的引擎關機時不會被關掉)。
            """
            started = time.monotonic()
            try:
                try:
                    await runtime.start()
                except Exception:
                    # 🔴 D2:原本這裡的例外會炸掉 lifespan → 達錢 4 沒開的早上,個股 /
                    # 指數 / 群益全部陪葬。改成只降級 txo 面(部分失敗時 `_series` 可能
                    # 已填、self-heal 鏈仍會嘗試,所以不宣稱「恆 NOT_READY」)
                    logger.exception("TXO runtime 啟動失敗,txo 面降級(其餘引擎照起)")

                await _boot_engines()
            except asyncio.CancelledError:
                raise  # 關機中斷:不設 boot_done(關機中的 server 不得宣告就緒)
            except Exception as exc:
                # `_boot` 的傘只罩得住六段引擎;WatchlistService 建構、app.state 指派等
                # 落在傘外 —— 沒有這層,序列半路崩掉會是「後續引擎全部靜默不啟動而
                # /api/ready 照樣 true」,最壞的失效樣態
                logger.exception("boot 序列非預期中止,後續引擎未啟動")
                app.state.boot_error = repr(exc)
            # 走到這裡 = 序列結束(可能不完整,由 boot_error 表述);cancel 天然跳過
            app.state.boot_done = True
            logger.info("boot 序列結束(%.1fs)", time.monotonic() - started)

        async def _boot_engines() -> None:
            """六段引擎的實際啟動序列(`_boot_all` 只管完成/中止語意與 done 標記)。"""

            # 合約發現(SC-1)的接線點:`list_stock_futures` **不在** `StockSource`
            # Protocol 內(個股訂閱面用不到,加進去等於逼所有 fake 實作)→ 由這裡以
            # getattr 取。source 沒這能力時 catalog 留 None,route 回 503 —— 不假裝查得到。
            stkfut_source: object | None = None

            # stock engine:與 TXO runtime 並存;失敗不得波及 quote(同 trade 邊界慣例)
            def _make_stock() -> StockEngine | None:
                nonlocal stkfut_source
                resolved_stock = (
                    _default_stock_source(trading_calendar)
                    if stock_source is DEFAULT_STOCK
                    else stock_source
                )
                if resolved_stock is None:
                    return None
                stkfut_source = resolved_stock
                backfill_date = os.environ.get("TXO_BACKFILL_DATE")
                return StockEngine(
                    cast(StockSource, resolved_stock),
                    trade_date=_resolve_trade_date(before=_clock_time(8, 0)),
                    throttle_secs=throttle_secs,
                    checkpoint=backfill_date is None,
                    ws=stock_ws,  # 與 SignalHub 共用同一顆(XR-3)
                    # 無日曆 → None = engine 預設的 `weekday() < 5`(W9 逐字不變)
                    is_trading_day=(
                        trading_calendar.is_trading_day if trading_calendar is not None else None
                    ),
                    # 處置名單 late-bound(L75):breadth 在 boot 序列較晚才建,取用時
                    # 才讀 app.state;breadth 停用(無 token)→ 空集合 = 全部照標(緩)
                    disposition_codes=lambda: (
                        b.disposition_codes()
                        if (b := getattr(app.state, "breadth", None)) is not None
                        else frozenset()
                    ),
                )

            async def _start_stock(o: StockEngine) -> None:
                await o.start()
                # 自選回填屬於「帶到就緒」的一部分:load_watchlist 對壞檔不吞例外,
                # 現況正是由 _boot 的 except 接住(留在 try 內是行為契約)
                persisted = load_watchlist(wl_path)["codes"]
                if persisted:
                    # 顯式帶 boot 哨兵(N112):`WatchlistService` 的取號自 1 起,哨兵
                    # 恆為最舊 → 就算未來有人把 restore 挪到 service 之後,使用者剛
                    # 存的那一份也不會被還原蓋掉(舊碼的 `seq=None` 是無條件全套)。
                    await o.set_watchlist(persisted, seq=WATCHLIST_BOOT_SEQ)

            stock = await _boot(
                "stock",
                "stock engine 初始化非預期失敗,個股功能停用(quote 不受影響)",
                _make_stock,
                _start_stock,
                lambda o: o.close(),
            )
            app.state.stock = stock
            booted.stock = stock
            # 合約查詢與個股訂閱共用同一條 session:QUERYALLINSTRUMENT 是 REQ 不是訂閱,
            # 不會多掛 TC4 refcount key(那才是零推播的引信),但多開一條 TC4 登入沒有理由
            fetch = getattr(stkfut_source, "list_stock_futures", None)
            if stock is not None and callable(fetch):
                app.state.stkfut_catalog = StkfutCatalog(cast(Callable[[], dict], fetch))

            # 自選複合操作(design §6):落檔 + 訂閱池 + 廣播三件事的單一定義,前端 PUT 與
            # Discord `/watch` 共用同一把 lock。**必須先於 signals `_boot`**(impl-review R3):
            # 它是 `_start_signals` closure 的自由變數,順序反了會是 NameError,而 `_boot` 的
            # except 會把它吞成「訊號功能靜默停用」—— 從畫面上只看得到「今天都沒訊號」。
            service = WatchlistService(wl_path, stock) if stock is not None else None
            app.state.watchlist_service = service

            # 訊號引擎(design §4.5):整段套 `_boot` 隔離 —— discord 登入失敗 / 壞自選檔
            # 只讓訊號停用,不波及其他引擎。bot 由 start 建立、close 收攤(成對)。
            bot: Bot | None = None

            def _make_signals() -> SignalHub | None:
                """**不看 stock 在否**(XR-3):規則 CRUD 是純檔案操作、today 端點與
                `/ws/stock` 的匯流排都住在 app 層,三者都不該隨達錢 4 一起消失。
                engine 缺席時三個注入退到替代供應(bus 已在 app 層、日別走牆鐘、
                日 K 空清單),hub 本身零改動。
                """
                engine = stock
                cfg = load_signals_config()
                if engine is None:
                    # `None` = 沒有日 K 來源(N110):hub 的 `request_basis` 整批早退,
                    # 一行 INFO 交代「CDP 全域停用」。改動前是塞一個恆回空清單的替身,
                    # 那讓 hub 逐檔印「無已完成日 K,CDP 停用」(自選 50 檔 = 50 行),
                    # 還得為它把 `basis_gap_secs` 歸零(假取數也會回 True 讓 worker 付
                    # 0.2s/檔)—— 兩個症狀同一個根因,一起消失。
                    daily_bars: Callable[[str, int], Awaitable[list[DailyBar]]] | None = None
                    trade_date_fn: Callable[[], str] = _resolve_trade_date
                    # 同群摘要的價格面沒有來源 → None(hub 既有容忍:摘要空字串)
                    quotes_fn: Callable[[], dict[str, tuple[str, float | None]]] | None = None
                else:
                    daily_bars = engine.daily_bars
                    # 日別語意由 engine 單一持有(兩段式 rollover 期間 stage2 才前進)
                    trade_date_fn = lambda: engine.trade_date  # noqa: E731
                    quotes_fn = engine.quotes
                return SignalHub(
                    cfg,
                    # app 層的匯流排(engine 在場時它就是 engine 自己那顆)
                    publish=stock_ws.publish,
                    daily_bars=daily_bars,
                    notify_fallback=notify_discord,
                    # 自選檔所在目錄 = 本專案的 data 根(`data/stock_watchlist.json`)→
                    # jsonl 與開關檔天然跟著它走,測試注入自選路徑即整組落在 tmp_path
                    data_dir=wl_path.parent,
                    trade_date_fn=trade_date_fn,
                    # 同群摘要(group-grid SC-1/2)。groups 只在 `on_watchlist` 讀檔
                    # (自選變更時),quotes 在 Discord worker 讀 engine 現值 —— 兩者
                    # 都輕同步,不進熱路徑。漏接的失效樣態是「通知少一段尾巴」而已,
                    # 所以由 booted app 的接線測試把關。
                    groups_fn=lambda: load_watchlist(wl_path)["groups"],
                    quotes_fn=quotes_fn,
                )

            async def _start_signals(hub: SignalHub) -> None:
                nonlocal bot
                await hub.start()
                # membership 種子:沒有這一步,開機後所有 tick 都被 hub 的 membership gate 擋掉
                hub.on_watchlist(load_watchlist(wl_path)["codes"])
                bot = create_bot(service, hub)  # token 未設 / extras 未裝 → None(SC-8 降級)
                if bot is not None:
                    bot.start_bg()
                    hub.attach_discord(bot.send_signal)
                # **必須是最後一行**(CC-2):attach 之後這個 hub 就在 engine 熱路徑上了,
                # 而 `_boot` 的 except 只會把它 close 掉、不會從 engine 摘下來 —— 提早 attach
                # 再讓後面任何一步拋,留下的是「WS 有訊號、jsonl 與 today 全空」的殭屍。
                # 這道 guard 現在是 load-bearing(XR-3):hub 不再需要 stock 才建得起來,
                # 所以 stock 缺席是常態路徑,不是「不可能發生、只為 narrowing」的殘留。
                if stock is not None:
                    stock.attach_signal_hub(hub)

            async def _close_signals(hub: SignalHub) -> None:
                # try/finally(CC-1):bot.close 拋(token 失效)不得讓 hub 的 worker 洩漏、
                # 也不得跳過關機盡力落檔
                try:
                    if bot is not None:
                        await bot.close()
                finally:
                    if stock is not None:
                        stock.detach_signal_hub()  # 先摘掛點:hub 收攤後熱路徑不得再打到它
                    await hub.close()

            signals = await _boot(
                "signals",
                "訊號引擎啟動失敗,訊號功能停用(其餘不受影響)",
                _make_signals,
                _start_signals,
                _close_signals,
            )
            app.state.signal_hub = signals
            booted.signals = signals
            booted.signals_close = _close_signals
            # 啟動失敗時 `_boot` 已呼叫 `_close_signals`(bot 也收了)→ 不對外暴露死掉的 bot
            app.state.discord_bot = bot if signals is not None else None

            # index engine:失敗不得波及其他引擎(同 trade/stock 邊界慣例)
            def _make_index() -> IndexEngine | None:
                resolved_index = (
                    _default_index_source(trading_calendar)
                    if index_source is DEFAULT_INDEX
                    else index_source
                )
                if resolved_index is None:
                    return None
                backfill_date = os.environ.get("TXO_BACKFILL_DATE")
                return IndexEngine(
                    cast(IndexSource, resolved_index),
                    # TXO runtime 現貨轉供(design IR1);runtime 掛掉時恆 None
                    txf_getter=runtime.spot_millipts,
                    mis_fetch=index_mis_fetch,
                    trade_date=_resolve_trade_date(before=_clock_time(8, 30)),
                    rollover=backfill_date is None,
                    throttle_secs=throttle_secs,
                    # 無日曆 → None = engine 預設的「純日曆日」(W9 逐字不變)
                    is_trading_day=(
                        trading_calendar.is_trading_day if trading_calendar is not None else None
                    ),
                )

            async def _start_index(o: IndexEngine) -> None:
                await o.start()
                if trading_calendar is not None:
                    # **背景跑、不 await**(SC-7):probe 要打一次 TC4 歷史(秒級),
                    # 擋在序列上會把 capital / futures / corr / breadth 整串往後推,
                    # 而它產出的只是一則 log。
                    booted.crosscheck_task = asyncio.create_task(_calendar_crosscheck(o))
                    # 另掛 app.state:唯一能問「檢查跑完了沒」的地方(測試的同步點)
                    app.state.calendar_crosscheck = booted.crosscheck_task

            index = await _boot(
                "index",
                "index engine 初始化非預期失敗,指數功能停用(其餘不受影響)",
                _make_index,
                _start_index,
                lambda o: o.close(),
            )
            app.state.index = index
            booted.index = index

            # capital(群益下單;capital-order design §13):factory 未設定 → None = disabled;
            # 啟動失敗 catch → None 降級,server 照起(stock/index 同慣例)
            async def _start_capital(c: CapitalClient) -> None:
                loop = asyncio.get_running_loop()

                def _capital_broadcast(payload: dict[str, object]) -> None:
                    # COM 執行緒 → loop threadsafe 排入 WS fanout(publish 只能在 loop 上跑)
                    loop.call_soon_threadsafe(capital_ws.publish, payload)

                c.set_broadcast(_capital_broadcast)  # 先掛再 start:啟動狀態事件不漏
                c.start(loop)

            capital = await _boot(
                "capital",
                "capital 初始化非預期失敗,群益功能停用(其餘不受影響)",
                capital_factory.get_capital,
                _start_capital,
                lambda c: asyncio.to_thread(c.close),  # COM 執行緒 join 是同步的
            )
            app.state.capital = capital
            booted.capital = capital

            # futures 行情引擎(SC-8):__main__ 顯式傳 DEFAULT_FUTURES 即建真 source;
            # 測試未傳(None)零連線;source 實例亦可
            def _make_futures() -> FuturesEngine | None:
                if futures_source is DEFAULT_FUTURES:
                    resolved_futures: FuturesSource | None = _default_futures_source(trading_calendar)
                else:
                    resolved_futures = cast("FuturesSource | None", futures_source)
                if resolved_futures is None:
                    return None
                fut_src = resolved_futures
                # 刻意不傳 flush_interval_secs:prod 吃預設 0.1 s(D2e)——
                # 五檔盤中要即時,1 s 週期會讓閃電梯五檔慢一秒
                return FuturesEngine(lambda: fut_src, broadcast=futures_ws.publish)

            futures = await _boot(
                "futures",
                "futures engine 初始化非預期失敗,期貨行情停用(其餘不受影響)",
                _make_futures,
                lambda o: o.start(),
                lambda o: o.close(),
            )
            app.state.futures = futures
            booted.futures = futures

            # 相關係數引擎(realtime-correlation SC-6):必須在 futures 之後建 —— base 腿
            # (台指)直接讀 futures.state(),不自行訂閱 TXF.HOT(同 symbol 跨 session 只推
            # 一邊,CLAUDE.md §8)。futures 掛掉時 getter 回空 dict,base 腿 None、配對全 None。
            def _make_corr() -> CorrelationEngine | None:
                # __main__ 顯式傳 DEFAULT_CORR 即建真 source(測試未傳 → None → 零連線)
                corr_cfg = load_corr_config()  # source(稀疏腿)與引擎(腿組)同一份,只讀一次
                if corr_source is DEFAULT_CORR:
                    resolved_corr: CorrSource | None = _default_corr_source(
                        trading_calendar, config=corr_cfg
                    )
                else:
                    resolved_corr = cast("CorrSource | None", corr_source)
                if resolved_corr is None:
                    return None
                corr_src = resolved_corr
                futures_engine = futures
                return CorrelationEngine(
                    lambda: corr_src,
                    config=corr_cfg,
                    txf_state_getter=(
                        lambda: futures_engine.state() if futures_engine is not None else {}
                    ),
                    broadcast=corr_ws.publish,
                    river_broadcast=river_ws.publish,
                    # 台指腿的 1K 必須從持有 TXF 訂閱的 futures session 問(CLAUDE.md §8)
                    futures_minutes_fetch=(
                        lambda product: (
                            futures_engine.fetch_day_1k(product)
                            if futures_engine is not None
                            else []
                        )
                    ),
                )

            corr = await _boot(
                "corr",
                "corr engine 初始化非預期失敗,相關係數停用(其餘不受影響)",
                _make_corr,
                lambda o: o.start(),
                lambda o: o.close(),
            )
            app.state.corr = corr
            booted.corr = corr

            # 家數帶 / 騰落線(market-overview R2 SC-3):**排序列最後** —— 它完全不碰
            # TC4/ZMQ,前面每一段都不依賴它,而 FinMind 是唯一一條會在啟動當下就慢的
            # 上游。放前面等於讓一個外部 HTTP 服務決定 TC4 系何時就緒。
            def _make_breadth() -> BreadthEngine | None:
                if breadth_fetchers is None:
                    return None
                if breadth_fetchers is DEFAULT_BREADTH:
                    token = finmind_token.resolve_token()
                    if token is None:
                        # 未設 token 是合法配置(不是失敗)→ info 不是 exception
                        logger.info("FINMIND_TOKEN 未設定,家數帶停用")
                        return None
                    fetchers: BreadthFetchers = (
                        breadth_fetch.fetch_snapshot,
                        breadth_fetch.fetch_stock_info,
                        breadth_fetch.fetch_disposition,
                        breadth_fetch.fetch_daily_prices,
                    )
                else:
                    # 顯式注入的四元組**跳過 token 閘**:fake 取數層根本不看 token,
                    # 而 verify server / 測試環境本來就沒有(有閘就恆停用 → 驗不到)
                    token = "fake-token"
                    injected = cast("tuple[object, ...]", breadth_fetchers)
                    if len(injected) != 4:
                        # 光讓解包自己拋 ValueError 不夠:`_boot` 的傘罩會把它收成
                        # 「breadth 停用」,與「FINMIND_TOKEN 未設」在畫面上同形 ——
                        # repo 外的側車樣板漏改第四槽時,症狀會是家數面板整段悄悄
                        # 消失而查不到原因,所以先留下講清楚長度的那行
                        # (出處 = impl-spec review R8「arity 防呆」;design §3.3a v3
                        # 未載,實作期補強 —— design 的 R8 是另一件事:排序優先序)
                        logger.error(
                            "breadth 取數元組長度 %d,預期 4(呼叫端未更新)", len(injected)
                        )
                        raise ValueError("breadth_fetchers 必須是四元組")
                    fetchers = cast("BreadthFetchers", breadth_fetchers)
                (
                    snapshot_fetch,
                    stock_info_fetch,
                    disposition_fetch,
                    daily_fetch,
                ) = fetchers
                cal = trading_calendar

                def _breadth_today() -> _date:
                    """**純日曆、不吃 env**(Q9 / KR-5):`TXO_BACKFILL_DATE` 是 TXO 回補
                    的 ops 通道,breadth 現行本就不讀它,本輪不擴張它的語意。
                    無日曆時 = 牆鐘 = 引擎預設語意。
                    """
                    return _today() if cal is None else resolve_trade_date(_today(), cal)

                return BreadthEngine(
                    token=token,
                    # None → configs/breadth.json(prod 唯一路徑);顯式注入只服務
                    # --verify 的放寬窗(盤後也要跑得出第二輪,review C-2)
                    config=(
                        breadth_config if breadth_config is not None else load_breadth_config()
                    ),
                    snapshot_fetch=snapshot_fetch,
                    stock_info_fetch=stock_info_fetch,
                    disposition_fetch=disposition_fetch,
                    daily_fetch=daily_fetch,
                    data_dir=breadth_data_dir,  # None → repo root data/market
                    today_fn=_breadth_today,
                    is_trading_day=None if cal is None else cal.is_trading_day,
                )

            breadth = await _boot(
                "breadth",
                "breadth engine 初始化非預期失敗,家數帶停用(其餘不受影響)",
                _make_breadth,
                lambda o: o.start(),
                lambda o: o.close(),
            )
            app.state.breadth = breadth
            booted.breadth = breadth

            # 序列尾段:合約目錄預熱一次(A3)。放在**最後**而不是接線當下 —— 它是
            # 秒級查詢,插在引擎序列中間會把後面每一段都往後推(capital 登入、corr
            # 訂閱都吃啟動時序)。留在 boot task 內而不另起 detached task:關機取消與
            # 例外收斂在這裡已經有人管,多一條背景 task 就多一個要 cancel 的地方。
            if app.state.stkfut_catalog is not None:
                await app.state.stkfut_catalog.prewarm()

        boot_task = asyncio.create_task(_boot_all())
        try:
            yield
        finally:
            if not boot_task.done():
                boot_task.cancel()
            try:
                await boot_task
            except asyncio.CancelledError:
                # 同一個 CancelledError 有兩種來源,指向的問題完全不同:
                # `boot_task.cancelled()` True = 上面那行 cancel 生效(預期關機路徑);
                # False = **lifespan 自己**被外部 cancel(uvicorn graceful timeout 等),
                # `await` 就地拋、boot task 還在跑 —— 下面的反序 close 也可能被下一次
                # cancel 打斷。續行語意兩者相同,只有 log 要分得開。
                if boot_task.cancelled():
                    logger.info("boot 序列被關機中斷(已建物件由 _boot 的 cancel 分支收掉)")
                else:
                    logger.warning("關機路徑自身被 cancel,反序 close 可能不完整")
            except BaseException:
                # **絕不能讓它跳過下面的反序 close**:裸 await 會把 boot task 的例外
                # 就地重拋 → 六段 close + runtime.close 全部不執行,TC4 session /
                # COM 執行緒 / hub worker 一次全洩漏(同白名單「各自 try/except 續行」)
                logger.exception("boot task 以例外結束(關機續行)")
            # 關機反序:crosscheck → breadth → signals(序列)→ **TC4 session 並行 lane**
            # (corr → futures 串鏈 ‖ index ‖ stock ‖ runtime)→ **capital 最後**(N049)。
            # 順序即依賴:corr 讀 futures.state(),必須排在 futures 之前收;signals 段的
            # `_close_signals` 會呼 `stock.detach_signal_hub()`,也必須排在 stock 之前收
            # (stock engine 還活著才解得掉掛點)。其餘各段無此類依賴。
            #
            # TC4 那幾段為什麼並行(review A1 / #105 §2.6 S1):每條 session 的 `close()`
            # 在 TC4 半死時各自最壞 `tc4.close_worst_secs()`(等在途 Connect 的鎖 + 一發
            # REQ 撞 RCVTIMEO + dispose 等 api.lock ≈ 32 s),序列排下去一條卡住、後面**健康**
            # 的 session 連 UNSUB 都輪不到就被 run.ps1 硬殺 —— 健康的也被還原成殭屍。並行
            # 之後硬殺只落在真的卡住的那一條;上界 = lane 深度 × 單條(`shutdown_budget`)。
            # capital 是「照建立反序收」的**唯一**例外,理由是關機時間預算不是依賴。
            #
            # 每段計時(review A1「console 印哪段吃掉時間」):run.ps1 超時訊息指向的就是
            # 收尾那一行彙總。`_close_segment` 同時是「各自 try/except 續行」的唯一定義點 ——
            # 改動前 runtime.close() 是裸 await,拋了就跳過 capital 的 COM join。
            timings: dict[str, float] = {}
            shutdown_t0 = time.monotonic()

            async def _close_segment(name: str, close: Callable[[], Awaitable[None]]) -> None:
                # 進場先印:卡住被 run.ps1 硬殺時,完成後才印的 WARNING / 彙總行一行都不會有,
                # 事後只能由「誰有開始沒結束」指認那一段(review SP3)
                logger.info("關機 %s 段開始", name)
                t0 = time.monotonic()
                try:
                    await close()
                except Exception:
                    logger.exception("%s close 失敗(關機續行)", name)
                finally:
                    elapsed = time.monotonic() - t0
                    timings[name] = elapsed
                    if elapsed > SLOW_CLOSE_WARN_SECS:
                        logger.warning(
                            "關機 %s 段耗時 %.1fs(> %.0fs):在途 Connect 持鎖或 TC4 REQ 逾時,"
                            "細節看該 source 的「TC4 quote close」行",
                            name,
                            elapsed,
                            SLOW_CLOSE_WARN_SECS,
                        )

            if booted.crosscheck_task is not None:
                # 引擎之前先收:它只讀 index 的歷史,關機時沒有任何理由讓它跑完
                booted.crosscheck_task.cancel()
                try:
                    await booted.crosscheck_task
                except asyncio.CancelledError:
                    logger.info("交易日曆交叉檢查已取消(關機)")
                except BaseException:
                    # 與上面 boot_task 同一個不變式:任何逃出來的 BaseException
                    # (含 SystemExit / KeyboardInterrupt)都會跳過下面整串反序
                    # close → TC4 session / COM 執行緒 / hub worker 一次全洩漏。
                    # 這條旁支是「只讀 index 歷史的 log 任務」,更沒有資格擋關機。
                    logger.exception("交易日曆交叉檢查以例外結束(關機續行)")
            if booted.breadth is not None:
                await _close_segment("breadth", booted.breadth.close)
            if booted.signals is not None and booted.signals_close is not None:
                signals, signals_close = booted.signals, booted.signals_close
                # bot 先於 hub(hub 的 sender 指向 bot)—— 順序封在 `_close_signals` 內
                await _close_segment("signals", lambda: signals_close(signals))

            async def _corr_then_futures() -> None:
                if booted.corr is not None:
                    await _close_segment("corr", booted.corr.close)
                if booted.futures is not None:
                    await _close_segment("futures", booted.futures.close)

            lanes: list[Awaitable[None]] = [_corr_then_futures()]
            if booted.index is not None:
                lanes.append(_close_segment("index", booted.index.close))
            if booted.stock is not None:
                lanes.append(_close_segment("stock", booted.stock.close))
            lanes.append(_close_segment("txo", runtime.close))
            # `_close_segment` 只吞 Exception:lane 內唯一逃得出來的是 CancelledError(lifespan
            # 自身被二次 cancel),gather 就地重拋、其餘 lane 續跑到底 —— 與改動前「反序 close
            # 可能不完整」同一種結局,只是 log 會多幾行
            await asyncio.gather(*lanes)
            # **capital 刻意排在 TC4 全部收完之後**(N049,唯一違反「照建立反序收」的一段):
            # `capital.close()` 是同步的 COM 執行緒 join(`COM_JOIN_TIMEOUT_SECS`),而 TC4 那
            # 幾條 session 的 UNSUB + LOGOUT + `Disconnect()` 是關機路徑上真正有**時間預算**的一段
            # —— 沒跑到就是一條殭屍 session,TC4 要 ~60 s 後 `ExecuteCheckPingTime` reap 才
            # `RemoveLoginInfo`,而 reap 會把它獨持的 key 歸零、連帶把 symbol 的上游 feed 帶走
            # (下一台 server 開頭 ~60 s 零推播,2026-08-18 實證)。capital 與 index / stock /
            # runtime 之間沒有依賴(有依賴的是 corr→futures 與 signals→stock 那兩條),重排安全。
            if booted.capital is not None:
                capital = booted.capital
                await _close_segment("capital", lambda: asyncio.to_thread(capital.close))
            # 固定段序輸出(並行 lane 下 `timings` 的插入序是完成序,每次不同 —— review ST4)
            logger.info(
                "關機收尾 %.2fs:%s",
                time.monotonic() - shutdown_t0,
                " / ".join(
                    f"{name} {timings[name]:.2f}s"
                    for name in _SHUTDOWN_SEGMENTS
                    if name in timings
                ),
            )

    app = FastAPI(lifespan=lifespan)
    origin = os.environ.get("FRONTEND_ORIGIN")
    if origin:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[origin],
            allow_methods=["*"],
            allow_headers=["*"],
        )

    app.state.capital_ws = capital_ws
    app.state.stock_ws = stock_ws
    app.state.futures_ws = futures_ws
    app.state.corr_ws = corr_ws
    app.state.river_ws = river_ws
    register_capital(app)  # capital/futures routes + 例外映射(capital-order design §6)
    register_oi(app)  # /api/futures/oi-levels(FinMind OI 撐壓;futures-allday SC-11)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error on %s", request.url.path, exc_info=exc)
        return JSONResponse(status_code=502, content={"detail": {"error": "TC4_DOWN"}})

    @app.get("/api/health")
    async def health(request: Request) -> dict:
        """執行中 server 的建置身分 —— 「這台是不是舊版」的唯一可視管道。

        用法:`git log <git_sha>..HEAD -- copycat/` 有輸出 = 後端 code 比跑著的新,該重啟。
        刻意不含引擎健康度:那是另一個問題,混進來會讓這條在引擎壞掉時也答不出版本。
        """
        return request.app.state.build.as_dict()

    @app.get("/api/ready")
    async def ready(request: Request) -> dict:
        """readiness probe:`ready` = boot 序列已結束(啟動窗已關)。

        **不是**「所有引擎都健康」—— 個別引擎的好壞由各 route 的 503 表述,那是另一個
        問題(混進來會讓這條在任一引擎降級時就恆 false,失去「窗關了沒」的用途)。
        `error` 非 null = 序列未走完即中止(傘外一步拋例外),後續引擎根本沒啟動。

        `getattr` 帶 default:lifespan 之外(單元測試直接打 app)也要答得出來。
        """
        state = request.app.state
        return {
            "ready": bool(getattr(state, "boot_done", False)),
            "error": getattr(state, "boot_error", None),
        }

    @app.get("/api/calendar")
    async def calendar() -> dict:
        """交易日曆狀態(SC-6)—— 「這台今天在看哪一天、日曆載到了沒」的唯一可視管道。

        欄位語意(**兩個日期刻意分開**):
        - `trade_date` = **stock / index / signals hub 實際採用**的日別
          (`TXO_BACKFILL_DATE` 有值時就是它)。
        - `calendar_trade_date` = 純日曆推導(不看 env)= **breadth 一律採用**的日別。
          env 模式下兩者會不一致(KR-5),合成一個欄位就沒有任何管道分辨得出來。
        - `years_loaded` 不含當年 = 日曆過期(此後只擋週末),要更新
          `configs/trading_holidays.json`。
        - `extra_trading_days` = 補班交易日(週末仍開盤),升冪;`holidays` 的鏡像欄。

        **不依賴任何引擎**:純 config 推導,boot 窗內(引擎還在起)也答得出來 —— 前端
        開站第一件事就是問它,拿 503 會讓假日集合整天不進前端(E7)。
        """
        today = _today()
        cal = trading_calendar
        return {
            "today": today.isoformat(),
            "trade_date": _resolve_trade_date(),
            "calendar_trade_date": (
                today.isoformat() if cal is None else resolve_trade_date(today, cal).isoformat()
            ),
            "backfill_env": os.environ.get("TXO_BACKFILL_DATE"),
            "holidays": sorted(d.isoformat() for d in cal.holidays) if cal is not None else [],
            # N090:補班交易日(週末仍開盤)。前端的週末守門要分得出「普通週末」與
            # 「這個週六本來就該開盤」,而那份資料只有後端有 —— 少了它,補班日設了卻
            # 沒生效的那次,畫面上與一般週末完全同形。
            "extra_trading_days": (
                sorted(d.isoformat() for d in cal.extra_trading_days) if cal is not None else []
            ),
            "years_loaded": sorted(cal.years_loaded) if cal is not None else [],
            "calendar_loaded": cal is not None,
        }

    def _runtime(request: Request) -> EngineRuntime:
        return request.app.state.runtime

    @app.get("/api/txo/series")
    async def list_series(request: Request) -> dict:
        runtime = _runtime(request)
        series = runtime.list_series()
        if not series:
            raise HTTPException(status_code=503, detail={"error": "NOT_READY"})
        return {
            "series": [
                {"series_id": s.series_id, "name": s.name, "expiry": s.expiry} for s in series
            ]
        }

    @app.post("/api/txo/select")
    async def select_series(request: Request, body: SelectBody) -> dict:
        runtime = _runtime(request)
        try:
            await runtime.activate(body.series_id)
        except KeyError:
            raise HTTPException(status_code=400, detail={"error": "UNKNOWN_SERIES"}) from None
        except HandoverBusyError:
            # 「現在忙,等一下再按」—— 與 NOT_READY(重試也一樣)刻意分開
            raise HTTPException(status_code=503, detail={"error": "HANDOVER_BUSY"}) from None
        return runtime.latest_snapshot()

    @app.get("/api/txo/contracts")
    async def txo_contracts(request: Request) -> dict:
        """Active 序列全鏈合約(OrderPanel 選單;snapshot.contracts 僅成交子集)。"""
        runtime = _runtime(request)
        symbols = sorted(s for s in runtime.orderable_symbols() if s.startswith("TC.O."))
        return {"contracts": symbols}

    @app.get("/api/txo/snapshot")
    async def snapshot(request: Request) -> dict:
        runtime = _runtime(request)
        snap = runtime.latest_snapshot()
        if snap["series_id"] is None:
            raise HTTPException(status_code=503, detail={"error": "NOT_READY"})
        return snap

    @app.websocket("/ws/txo-pnl")
    async def ws_txo_pnl(websocket: WebSocket) -> None:
        runtime: EngineRuntime = websocket.app.state.runtime
        await websocket.accept()
        try:
            # seed 必須是「已送出的那一個 dict 物件」:再叫一次 latest_snapshot 的話,
            # 兩次之間發生的變動會被 generator 當成「跟首則一樣」吃掉
            snap = runtime.latest_snapshot()
            await websocket.send_json(snap)
            await relay(websocket, runtime.snapshots(seed=snap))
        except WebSocketDisconnect:
            return

    # ---- stock(個股看盤;design v4 §2.5)----

    @app.exception_handler(WatchlistError)
    async def _watchlist_error(request: Request, exc: WatchlistError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": {"error": str(exc)}})

    @app.exception_handler(RuleError)
    async def _rule_error(request: Request, exc: RuleError) -> JSONResponse:
        """`RuleError` 的值域只有兩碼(signal_rules R10):找不到 → 404,其餘 → 400。

        未知碼收斂成 400 而非 500:新增碼忘了在這裡對照時,前端至少拿得到 `detail.error`
        原文,而不是被全域 handler 轉成 502 TC4_DOWN(那條訊息與真因完全無關)。
        """
        code = str(exc)
        status = 404 if code == "RULE_NOT_FOUND" else 400
        return JSONResponse(status_code=status, content={"detail": {"error": code}})

    def _stock(request: Request) -> StockEngine:
        stock: StockEngine | None = request.app.state.stock
        if stock is None:
            raise HTTPException(status_code=503, detail={"error": "NOT_READY"})
        return stock

    def _watchlist_service(request: Request) -> WatchlistService:
        _stock(request)  # 引擎未就緒的 503 優先(既有 PUT 行為)
        service: WatchlistService | None = request.app.state.watchlist_service
        if service is None:
            raise HTTPException(status_code=503, detail={"error": "NOT_READY"})
        return service

    def _signals(request: Request) -> SignalHub:
        """訊號 route 的共同閘(design §7)。**只看 hub**(XR-3):hub 解耦後 503 只剩
        一種語意 —— 訊號層自身降級(壞規則檔 / start 失敗)。

        舊碼在此先過 `_stock()`,達錢 4 沒開時規則 CRUD(純檔案操作)與 today 端點
        一起 503,而兩者都與 TC4 無關。
        """
        hub: SignalHub | None = request.app.state.signal_hub
        if hub is None:
            raise HTTPException(status_code=503, detail={"error": "NOT_READY"})
        return hub

    def _valid_code(code: str) -> None:
        """個股代號閘。**必須在 `_stock(request)` 之後呼叫** —— 「引擎沒起來 + 代號非法」
        現況回 503 不是 400,那個優先序是既有行為(做成 Depends 會被 FastAPI 提前跑)。"""
        if not validate_code(code):
            raise HTTPException(status_code=400, detail={"error": "BAD_CODE"})

    @app.get("/api/stock/names")
    async def stock_names() -> dict:
        """全市場代號↔名稱(搜尋提示列用)。**刻意不過 `_stock()` 閘** —— 名稱表與 TC4
        連線無關,達錢 4 沒開時也該能搜尋。表不存在 / 壞檔 → 空陣列(不 500)。"""
        names = load_stock_names(names_path)
        return {
            "names": [{"code": code, "name": name} for code, name in names.items()],
            "count": len(names),
        }

    @app.get("/api/stock/watchlist")
    async def stock_watchlist_get(request: Request) -> dict:
        _stock(request)
        wl = load_watchlist(wl_path)
        return {"codes": wl["codes"], "groups": wl["groups"]}

    @app.put("/api/stock/watchlist")
    async def stock_watchlist_put(request: Request, body: GroupsBody) -> dict:
        """整份取代。**改走 `WatchlistService`**(design §6):落檔 + 訂閱池 + 廣播三件事
        與 Discord `/watch` 共用同一把 lock,兩邊同時改自選不再互相覆蓋。

        對外形狀不變,但**同內容 PUT 現在是 no-op**(🔴):舊碼照樣跑一輪 `set_watchlist`
        對整份名單 UNSUB/SUB,盤中存個檔就讓所有自選股斷訂一次。
        """
        service = _watchlist_service(request)
        groups: list[Group] = [{"name": g.name, "codes": g.codes} for g in body.groups]
        codes = body.codes if body.codes is not None else union(groups)
        saved = await service.apply({"codes": codes, "groups": groups})  # 400 由 handler
        return {"codes": saved["codes"], "groups": saved["groups"]}

    @app.get("/api/stock/overlay/{code}")
    async def stock_overlay(request: Request, code: str) -> dict:
        stock = _stock(request)
        _valid_code(code)
        # 基準日 = **顯示中的交易日**(SC-13),不是牆鐘:假日看的是最近交易日那張圖,
        # 疊線基準卻用今天的話,週六會把週五的 bar 當成「今日 partial」整根剔掉。
        # cache 鍵同源(日別沒變就不該重算);交易日 env 未設時逐字等於牆鐘。
        today = _resolve_trade_date()
        cached = overlay_cache.get(code, today)
        if cached is not None:
            return cached  # cache 命中不進 semaphore(沒有 TC4 取數就沒有要節流的東西)
        async with overlay_sem:
            try:
                bars = await asyncio.wait_for(
                    stock.daily_bars(code), timeout=OVERLAY_FETCH_TIMEOUT_S
                )
            except (TimeoutError, HistoryTimeoutError):
                # 兩種逾時同一條路(plan review P0-2):`asyncio.wait_for` 的整體逾時、
                # 與 TC4 歷史首頁未備妥(`daily_bars` 現在會往外拋)在使用者那一端是
                # 同一件事 —— 「這一檔現在取不到」。少了後者這半,`ConnectionError`
                # 的降級接不到它,疊線會變成 500。
                # 逾時 = 「這一檔現在取不到」,與 TC4 離線同一種降級:全 null + 200。
                # **不寫 cache**(沿 overlay.py 空結果不 cache):快取一則空值等於
                # 這檔今天再也拿不到疊線。放掉的是 semaphore 名額 —— `to_thread` 的
                # 工作執行緒中斷不了,但後面排隊的股號不必陪它一起等(head-of-line)。
                logger.warning(
                    "stock_overlay %s: daily_bars 逾時 %.0fs,疊線降級全 null",
                    code,
                    OVERLAY_FETCH_TIMEOUT_S,
                )
                return build_overlay([], today)
        result = build_overlay(bars, today)
        overlay_cache.put(code, today, result)  # 空結果不 cache(overlay.py 規則)
        return result

    @app.get("/api/stock/bars/{code}")
    async def stock_bars(request: Request, code: str, tf: str = "D", days: str = "5") -> dict:
        """K 線 bar(SC-7)。tf=D 忽略 days(D-15:忽略的參數不該進 cache/query key)。"""
        stock = _stock(request)
        _valid_code(code)
        if tf not in ("D", "1"):
            raise HTTPException(status_code=400, detail={"error": "BAD_TF"})
        # today = 本機日界(= 台北,部署綁本機;同 overlay 的 design R6/R13)
        today = _date.today()
        if tf == "D":
            # days 在日線路徑完全不參與(不進 cache/query key,D-15)→ 連驗都不驗:
            # 對忽略的參數回 400 會讓「多帶一個沒用的 query」變成擋下日 K 的理由(M1)
            bars, status = await build_daily(stock.bars_range, bars_cache, code, today)
        else:
            # days 自行解析:交給 FastAPI 轉 int 時,轉換失敗回的是 422 + list 形 detail,
            # 不符全站 {"detail": {"error": "<code>"}} 契約(W-D3;review P2-6)
            try:
                days_n = int(days)
            except ValueError:
                raise HTTPException(status_code=400, detail={"error": "BAD_DAYS"}) from None
            # calendar:歷史段的 missing 濾掉不可能有資料的日子(bug/futures-bars-gap)。
            # 這條沒帶 session → build_minute 預設 "day",個股本來就只有日盤,規則相符。
            bars, status = await build_minute(
                stock.bars_range,
                bars_cache,
                code,
                clamp_days(days_n),
                today,
                calendar=trading_calendar,
            )
        # status:空的三種來源(逾時 / 真無資料 / 斷線)原本在前端收斂成同一句
        # 「無 K 線資料」。加欄位 = 向後相容(舊前端忽略,新前端對缺欄位 default "ok")
        return {"code": code, "tf": tf, "bars": bars, "status": status}

    # ---- stock signals(stock-signals design §7)----

    @app.get("/api/stock/signals/today")
    async def stock_signals_today(request: Request) -> dict:
        """當日訊號歷史(SC-7):讀 hub 的 jsonl,壞行跳過。

        前端 reconnect 後拿它當 baseline 自癒 —— WS 斷線期間丟掉的訊號由這裡補回。

        `trade_date`(引擎日別)/ `today`(牆鐘日)是 additive 兩欄(D3'):前端拿它
        判標題該印「今日訊號」還是「MM-DD 訊號」。日期只能由**這裡**給 —— 瀏覽器
        時鐘與後端日別可以差一天(假日開站掛的是上一交易日的訊號),各算各的必錯。

        **無查參**:未宣告的查參 FastAPI 一律忽略,舊 bundle 打 `?market=exclude`
        照樣 200(前後端部署順序無關)。
        """
        # 讀整份當日 jsonl 是同步 IO,訊號多的日子會卡住 event loop(8 條 WS 一起頓)
        # → 丟 worker thread;_signals 的 503 判定留在 loop 內(handoff R5)。
        # to_thread 走 loop 預設 executor,與 daily_bars / capital close 同池且工作
        # 執行緒不可中斷 —— TC4 半死的殭屍執行緒堆積時這條會跟著排隊(review C-1);
        # today 若變慢先查同池鄰居,別急著懷疑 jsonl。
        hub = _signals(request)
        # 兩個日期是純屬性(no IO)→ 留在 loop 上讀;只有 jsonl 那段丟 worker thread。
        # **先取樣再 await**(review C-1):讀檔那段可長,橫跨 rollover stage2 時「訊號
        # 的日別」與「回傳的日期」必然錯位一拍 —— 方向由取樣順序決定。先取樣 = 最壞
        # 情況回舊日期配舊訊號(前端印「MM-DD 訊號」,兩邊一致);後取樣 = 新日期配舊
        # 訊號,前端據此印「今日訊號」而列的內容是昨天的,零錯誤訊號。
        trade_date, today = hub.trade_date, hub.today
        return {
            "signals": await asyncio.to_thread(hub.today_signals),
            "trade_date": trade_date,
            "today": today,
        }

    # ---- 訊號規則 CRUD(signal-rules design「SC-4/6 routes」)----

    async def _save_rule(hub: SignalHub, body: RuleBody, rule_id: str | None) -> Rule:
        """POST / PUT 的共同落點。**OSError 必須在這裡轉 500**:全域 handler 會把它
        收成 502 TC4_DOWN,而落檔失敗跟達錢 4 一點關係都沒有(排查會被帶到反方向)。
        """
        try:
            return await hub.upsert_rule(body.payload(), rule_id=rule_id)
        except OSError:
            logger.exception("訊號規則落檔失敗(記憶體未變更):%s", rule_id)
            raise HTTPException(status_code=500, detail={"error": "RULE_SAVE_FAILED"}) from None

    @app.get("/api/stock/signals/rules")
    async def stock_signals_rules(request: Request) -> dict:
        return {"rules": _signals(request).rules()}

    @app.post("/api/stock/signals/rules", status_code=201)
    async def stock_signals_rules_post(request: Request, body: RuleBody) -> Rule:
        """新增。body 的 `id` 一律忽略 —— id 由 hub 的單調計數配(R12),客戶端指定
        會讓已存 jsonl 的舊 id 被重用,前端去重就把新規則的訊號吃掉。"""
        return await _save_rule(_signals(request), body, None)

    @app.put("/api/stock/signals/rules/{rule_id}")
    async def stock_signals_rules_put(request: Request, rule_id: str, body: RuleBody) -> Rule:
        """編輯。**path 的 id 為準**;body 帶了不一致的 id → 400(R6):兩者不一致時
        猜哪一個都可能改到使用者沒看著的那條規則。"""
        hub = _signals(request)
        if body.id is not None and body.id != rule_id:
            raise HTTPException(status_code=400, detail={"error": "INVALID_RULE"})
        return await _save_rule(hub, body, rule_id)

    @app.delete("/api/stock/signals/rules/{rule_id}", status_code=204)
    async def stock_signals_rules_delete(request: Request, rule_id: str) -> Response:
        hub = _signals(request)
        try:
            await hub.delete_rule(rule_id)
        except OSError:
            logger.exception("訊號規則落檔失敗(記憶體未變更):%s", rule_id)
            raise HTTPException(status_code=500, detail={"error": "RULE_SAVE_FAILED"}) from None
        return Response(status_code=204)

    async def _resolve_contract(request: Request, code: str, contract: str) -> str:
        """`<prod>:<ym>` → instrument key `F:<prod>:<ym>`;不合法一律 400 BAD_CONTRACT。

        **形檢在白名單之前**:白名單那一步在冷 cache 時是一次真的 TC4
        `QUERYALLINSTRUMENT`(實測秒級),隨手打錯的字串不該換來一次重查詢。
        """
        if _CONTRACT_RE.fullmatch(contract) is None:
            raise HTTPException(status_code=400, detail={"error": "BAD_CONTRACT"})
        prod, _sep, ym = contract.partition(":")
        catalog: StkfutCatalog | None = request.app.state.stkfut_catalog
        if catalog is None:
            # source 沒有合約查詢能力 = 這條路無從驗證。放行等於讓白名單形同虛設,
            # 所以擋下並回 NOT_READY(同 contracts route 對 catalog 缺席的判法)
            raise HTTPException(status_code=503, detail={"error": "NOT_READY"})
        # 查詢失敗**不 catch** → 全域 handler 502 TC4_DOWN(不降級成現貨:悄悄換商品)
        if not await catalog.contains(code, prod, ym):
            raise HTTPException(status_code=400, detail={"error": "BAD_CONTRACT"})
        return f"F:{prod}:{ym}"

    @app.get("/api/stock/stkfut/contracts/{code}")
    async def stock_stkfut_contracts(request: Request, code: str) -> dict:
        """個股期合約清單(SC-1):404 = 這檔沒有期貨(前端據此不渲染下拉)。

        TC4 查詢失敗**不 catch** —— 全域 handler 的 502 TC4_DOWN 正是這條路要的語意,
        而降級成空清單會讓「達錢 4 斷線」看起來像「這檔沒期貨」。
        """
        _stock(request)
        _valid_code(code)
        catalog: StkfutCatalog | None = request.app.state.stkfut_catalog
        if catalog is None:
            raise HTTPException(status_code=503, detail={"error": "NOT_READY"})
        entry = await catalog.get(code)
        if entry is None:
            raise HTTPException(status_code=404, detail={"error": "NO_STKFUT"})
        return {
            "code": code,
            "name": entry["name"],
            "std": _with_unit(entry["std"]),
            "mini": _with_unit(entry.get("mini")),
        }

    @app.get("/api/stock/state/{code}")
    async def stock_state(
        request: Request, code: str, contract: str | None = None, tape: str = "1"
    ) -> dict:
        """主圖狀態;`?contract=<prod>:<ym>` 切成該股的個股期合約(stkfut-contracts D6/D7)。

        **合約合法性只能來自 catalog,不能只驗字串形**:`?contract=DHF:202609` 打到
        2330 上,形狀完全合法而畫的是鴻海期貨 —— URL、下單面、右側欄全都還寫著 2330,
        而 TC4 對不相干的 symbol 一律照回 `Success: OK`,訂閱層不會有任何抗議。所以
        白名單查不到就 400,catalog 本身查不到(TC4 斷)就讓 502 冒出去,**都不降級成
        現貨** —— 悄悄跳回現貨等於在使用者不知情下換了商品。

        `code` 回 instrument key(前端 WS 比對鍵)、`underlying` 回股號:兩者在現貨態
        相同,期貨態才分岔,前端因此有單一讀法(不必自己從 key 反推股號)。
        """
        stock = _stock(request)
        _valid_code(code)  # 代號閘優先(既有優先序)
        key = code
        if contract is not None:
            key = await _resolve_contract(request, code, contract)
        await stock.set_main_contract(key)  # 含回補觸發(design §2.5)
        # `?tape=0` = 呼叫端沒有逐筆明細讀者(群組檢視點卡片只為換右欄標的)→ 省掉
        # 整份 tape。**`set_main_contract` 照打**(W-4):省的只有 payload,訂閱與回補
        # 都還要靠它,漏掉的話點卡片換不了標的而畫面上只是「右欄沒資料」。
        #
        # 型別收 `str` 不收 `int`(D3'):`?tape=abc` 走全量比 422 好 —— 422 的 detail
        # 是 list 形,不符全站 `{"detail": {"error": code}}` 契約。
        omit_tape = tape == "0"
        snap = stock.snapshot(key, tape=not omit_tape)
        snap["underlying"] = code
        if omit_tape:
            # 旗標只在省略時出現(全量路徑位元不變,W3);診斷 / 測試用,前端不依賴 ——
            # 空 tape 與「今天真的還沒成交」在畫面上同義,沒有這個鍵就分不出來。
            snap["tape_omitted"] = True
        return snap

    @app.get("/api/stock/group-state")
    async def stock_group_state(request: Request, codes: str = "") -> dict:
        """群組檢視的唯讀 batch(group-grid SC-4)。

        **刻意不重用 `/api/stock/state/{code}`**:那條路會 `set_main`,群組檢視每分鐘
        對最多 50 檔各要一次狀態 = 每分鐘把主圖搶走 50 次,主圖分時線就此凍結,而畫面
        上只表現為「圖不動了」沒有任何錯誤訊號。

        逗號分隔的 codes 自行解析(不用 `list[str]` query):FastAPI 的重複參數形對
        50 個 code 會長到難以閱讀,而轉換失敗回的是 422 + list 形 detail,不符全站
        `{"detail": {"error": code}}` 契約。

        **無 404 路徑**:未知 / 未訂閱 code → `no_data: true` 空 minutes。卡片要答的是
        「這格畫不畫得出東西」,對它來說兩者是同一件事;整批中一顆 404 反而會讓整個
        batch 沒得顯示。
        """
        stock = _stock(request)
        # **先去重(保序)再驗數量**:重複碼是正常輸入 —— 同一檔可屬多個群組,而前端
        # 把成員直接拼進 csv。反過來(先驗後去重)會把一份合法請求判成 `BAD_CODES`,
        # 而畫面只顯示「載入失敗」,沒有任何線索指向「有一檔重複」。保序是因為卡片
        # 就照這個順序排;`dict.fromkeys` 是首見序去重的既有寫法(同自選聯集)。
        wanted = list(dict.fromkeys(c for c in codes.split(",") if c))
        # 數量驗證仍在逐碼驗證之前:超量時逐碼驗只是白做工,而且錯誤碼會變成
        # BAD_CODE 誤導排查方向
        if len(wanted) > WATCHLIST_LIMIT:
            raise HTTPException(status_code=400, detail={"error": "BAD_CODES"})
        for code in wanted:
            _valid_code(code)
        return {"states": stock.group_snapshot(wanted)}

    # ---- index(指數看盤;index-board SC-4)----

    def _index(request: Request) -> IndexEngine:
        index: IndexEngine | None = request.app.state.index
        if index is None:
            raise HTTPException(status_code=503, detail={"error": "NOT_READY"})
        return index

    @app.get("/api/index/state")
    async def index_state(request: Request) -> dict:
        return _index(request).state()

    @app.get("/api/index/overlay")
    async def index_overlay(request: Request) -> dict:
        """加權的 CDP / 日均線(index-overlay SC-5);形狀同 `/api/stock/overlay/{code}`。

        日 K 走 **`build_period`**(鍵自動成 `IX0001|L`)= 與 `/api/market/bars/TWSE?tf=D`
        真共用同一格,同日兩端點合計至多兩次 DK 取數(自 `DAILY_FINAL_TIME` 起:界前
        一次、界後定稿一次;pr-165-review #6)。**不得改走 `build_daily` 的裸
        `IX0001`** —— 那格是 `/api/stock/bars/IX0001`(**stock** session)的,共用它就
        重開了 `|M` / `|L` 後綴當初堵住的跨 session 汙染洞(W-12 / W-14)。

        另**不經 `overlay_cache`**(那是個股 overlay 專屬):日 bar 已在 `bars_cache`,
        `build_overlay` 是常數時間,再疊一層只是多一份會漂的狀態。

        bars 空(TC4 不可用)→ `build_overlay` 自然回全 null + 200:CDP/MA 是可降級的
        疊線,把它做成 5xx 會讓前端整張圖跟著紅。引擎缺席才是 503(`_index` 既有閘)。
        """
        index = _index(request)

        async def tagged(_c: str, tf_: str, s: str, e: str) -> TaggedBars:
            return TaggedBars(*await index.bars_range(tf_, s, e))

        # bars 抓取仍走**牆鐘**(W3:K 線的日期邏輯本輪不動 —— 多抓一天不會少資料);
        # 疊線基準日則走顯示中的交易日(SC-13),與個股 overlay 同源。
        today = _today()
        bars, _tag = await build_period(tagged, bars_cache, "IX0001", today, "D")
        daily: list[DailyBar] = [
            {"date": b["t"][:10], "high": b["h"], "low": b["l"], "close": b["c"]} for b in bars
        ]
        return build_overlay(daily, _resolve_trade_date())

    # ---- market(大盤 K 線;index-board SC-4/5/6)----

    @app.get("/api/market/bars/{key}")
    async def market_bars(
        request: Request, key: str, tf: str = "D", days: str = "30", session: str = "day"
    ) -> dict:
        """大盤頁 K 線(index-board N-5)。

        **拒繪走 200 + `meta.refusal`,不用 4xx**:4xx 會被 TanStack Query 的 error 路徑
        吞成同一種紅色,分不出「平台不支援」與「TC4 掛了」—— 而那正是本輪要讓使用者
        五秒內答出來的問題。400/503 只留給「請求本身錯」與「引擎沒起來」。

        分派 = 每個 symbol 都向**持有它 REALTIME 訂閱的那條 session** 問歷史
        (別條 session 問 = 對同一 symbol 多掛一把 TC4 refcount key,歸零時退訂整個 symbol;
        見 `.claude/skills/tc4-market-facts/SKILL.md`):
        `TWSE` → index 引擎、`TXF/MXF/TMF` → futures 引擎、`OTC` → 本機合成(無 TC4 來源)。

        `session`(`day` 預設 / `allday` 近全,futures-allday SC-3)只對期指 tf=1 有意義:
        非法值或非期指鍵帶 `allday` 一律 400 —— 靜默當 day 處理的話,前端會以為自己拿到
        的是近全序列(而畫面上「加權沒有夜盤」與「參數沒生效」長得一模一樣)。
        `tf != "1"` 則忽略 session(日/週/月 K 無盤別維度,D-15:忽略的參數不進 cache 鍵)。
        """
        if key not in MARKET_KEYS:
            raise HTTPException(status_code=400, detail={"error": "BAD_KEY"})
        if tf not in ("1", "D", "W", "M"):
            raise HTTPException(status_code=400, detail={"error": "BAD_TF"})
        if session not in MARKET_SESSIONS or (
            session == "allday" and key not in FUTURES_MARKET_KEYS
        ):
            raise HTTPException(status_code=400, detail={"error": "INVALID_SESSION"})
        try:
            days_n = clamp_days(int(days))
        except ValueError:
            raise HTTPException(status_code=400, detail={"error": "BAD_DAYS"}) from None
        today = _date.today()
        eff_session = session if tf == "1" else "day"

        if key == "OTC":
            index = _index(request)
            if tf != "1":
                # 櫃買指數不在 TC4 symbol 樹(CLAUDE.md §8 掃盡確認)→ 沒有任何歷史來源。
                # 給空陣列 + 明確理由,不拿當日合成假裝成日/週/月 K。
                return _market_payload(key, tf, [], source="none", refusal="NO_HISTORICAL_SOURCE")
            bars, since = index.otc_bars()
            return _market_payload(
                key,
                tf,
                bars,
                source="mis_poll_synth",
                volume=False,
                synth_since=since,
                partial_last=is_partial_last(bars, tf, today),
            )

        # 兩個閉包的第二元素語意不同(source tag vs 三態 status)且同為 str ——
        # 名字必須隔開,否則接錯的表現是 meta.source 靜默變成 "ok"(spec R5)
        if key == "TWSE":
            index = _index(request)

            async def tagged_source(_c: str, tf_: str, s: str, e: str) -> TaggedBars:
                return TaggedBars(*await index.bars_range(tf_, s, e))

            async def plain_with_status(_c: str, tf_: str, s: str, e: str) -> BarsResult:
                # `build_minute` 的 cache 型別要求一個 status,而加權路徑沒有真訊號可帶
                # (`index.bars_range` 回的是 (bars, tag))→ 這裡給 "ok" 只是**餵給 cache**,
                # **不會**進 payload:下面 tf=="1" 分支對非期指鍵不傳 status(SP4)。
                return BarsResult((await tagged_source(_c, tf_, s, e)).bars, "ok")
        else:
            futures: FuturesEngine | None = request.app.state.futures
            if futures is None:
                raise HTTPException(status_code=503, detail={"error": "NOT_READY"})

            async def tagged_source(_c: str, tf_: str, s: str, e: str) -> TaggedBars:
                # 期指沒有 DK→1K 的 fallback 分支,tag 恆定;回空 = 借不到(engine 已 log)
                got, _status = await futures.bars_range(key, tf_, s, e, session=eff_session)
                return TaggedBars(got, "tc4_dk" if got else "unavailable")

            async def plain_with_status(_c: str, tf_: str, s: str, e: str) -> BarsResult:
                # 期指分 K 是**唯一**有三態訊號的路徑(N104):engine 已把
                # HistoryTimeoutError / ConnectionError 分成 timeout / disconnected。
                # engine 回裸 tuple(ST3:不反向 import server 層型別),`BarsResult`
                # 在這裡才組 —— 它是 cache/route 這一側的搬運型別。
                return BarsResult(*await futures.bars_range(key, tf_, s, e, session=eff_session))

        # 分鐘路徑的 cache code 加 |M 後綴:裸 "IX0001" 會與 /api/stock/bars/IX0001
        # (走 **stock** session)共用 `_hist` / `_today` / `_empty` 同一格 —— 那會讓
        # W-12「歷史一律從持有其 REALTIME 訂閱的 session 問」在快取層被繞過(review P1-6)。
        # 長窗路徑的 |L 後綴同理(review P2-1)。期指的 F: 前綴含冒號,本來就撞不到。
        code = ("IX0001|M" if tf == "1" else "IX0001") if key == "TWSE" else f"F:{key}"
        if tf == "1":
            # 第二元素**不再丟棄**(N104):`build_minute` 早就把兩段取最壞算好了,
            # 丟掉它等於在 payload 裡把「TC4 忙」與「真沒這段 K 線」講成同一句話。
            bars, status = await build_minute(
                plain_with_status,
                bars_cache,
                code,
                days_n,
                today,
                session=eff_session,
                calendar=trading_calendar,
            )
            return _market_payload(
                key,
                tf,
                bars,
                source="tc4_1k" if bars else "unavailable",
                partial_last=is_partial_last(bars, tf, today),
                # **只有期指鍵給 status**(SP4):TWSE / OTC 的來源層沒有三態訊號,
                # 給一個恆 "ok" 等於在 proxy miss 時說「問到了、就是沒有」
                status=status if key in FUTURES_MARKET_KEYS else None,
            )
        # 日 / 週 / 月 K 走 `build_period`,它回的是 `TaggedBars` 沒有 status 欄 →
        # 不給這一格(未三態化)。要一起做得動 `bars.py` 的 cache 型別(白名單 §0.2-1)。
        bars, tag = await build_period(tagged_source, bars_cache, code, today, tf)
        return _market_payload(
            key, tf, bars, source=tag, partial_last=is_partial_last(bars, tf, today)
        )

    # ---- market breadth(家數帶 / 騰落線;market-overview R2 §6)----

    def _breadth(request_or_ws: Request | WebSocket) -> BreadthEngine | None:
        """`getattr` 帶預設:lifespan 進場前(create_app 期直打 / 單元測試)`state.breadth`
        還不存在,直取屬性會是 AttributeError → 全域 handler 轉 502 TC4_DOWN,而那句
        訊息與真因(啟動窗還沒開)完全無關。"""
        breadth: BreadthEngine | None = getattr(request_or_ws.app.state, "breadth", None)
        return breadth

    def _breadth_booted(request_or_ws: Request | WebSocket) -> bool:
        """boot 序列是否已跑完(`getattr` 預設:lifespan 進場前這個旗標也還不存在)。"""
        return bool(getattr(request_or_ws.app.state, "boot_done", False))

    @app.get("/api/market/breadth")
    async def market_breadth(request: Request) -> dict:
        """**恆 200 三態**(design §6),不用 503:引擎缺席(FINMIND_TOKEN 未設)是合法
        配置而非故障,而前端要把「未設定」「載入中」「有數字」講成三句不同的話 ——
        503 會被 TanStack 的 error 路徑吞成同一種紅色,三者從此不可分辨。

        引擎缺席**又分兩態**(review P2-1):boot 未完成 = 載入中(enabled=true /
        counts=null),boot 完成仍是 None 才是「未設定」。breadth 排在 boot 序列最後,
        開站頭幾秒必然落在前者 —— 混講成「未設定」等於每次重啟都閃一次假訊息。
        """
        breadth = _breadth(request)
        if breadth is None:
            loading = not _breadth_booted(request)
            return {
                "enabled": loading,
                "trade_date": None,
                "as_of": None,
                "stale": loading,
                "counts": None,
                "series": [],
            }
        return breadth.state()

    @app.get("/api/market/breadth/rows")
    async def market_breadth_rows(request: Request) -> dict:
        """全量逐檔(漲跌停列表的原料;R3 SC-1)—— 三態判式與 `/api/market/breadth` 同款。

        刻意**不進 WS**:~2800 列 × 13 欄只有列表展開時才有人看,每 10 秒推給所有連線
        是純浪費(brainstorm Q2)。連板算術全在 `rows_state()`(單一真相),前端零日期推理。

        前端的「載入中 vs 暫無資料」判別子是 `as_of`(首輪成功前恆 null),不是 `stale`
        —— 冷啟動 degraded 下 `stale` 恆 True,拿它判載入中會兩態顛倒(design R18)。
        """
        breadth = _breadth(request)
        if breadth is None:
            loading = not _breadth_booted(request)
            return {
                "enabled": loading,
                "trade_date": None,
                "as_of": None,
                "stale": loading,
                "streaks_ready": False,
                "rows": [],
            }
        return breadth.rows_state()

    @app.websocket("/ws/breadth")
    async def ws_breadth(websocket: WebSocket) -> None:
        breadth = _breadth(websocket)
        if breadth is None:
            # 載入中 / 未設定都在 accept **之前**拒握手(R4 N036;starlette 在 CONNECTING 態送
            # close = uvicorn 回 403):browser 端 onopen 不觸發、走「從未 open」退避。
            # 載入中語意由 REST `/api/market/breadth` 承擔(loading → enabled/stale),不再送
            # 「載入中 scalar」再關。
            await websocket.close()
            return
        await websocket.accept()
        try:
            # 首則 seed(當前 scalar 快照)已封在 `engine.stream()` 內 —— 不在這裡另送,
            # 否則盤中連線會收到兩則相同的全量(前端 upsert 看不出差別,更難查)
            await relay(websocket, breadth.stream())
        except WebSocketDisconnect:
            return

    @app.get("/api/corr/state")
    async def corr_state(request: Request) -> dict:
        corr: CorrelationEngine | None = request.app.state.corr
        if corr is None:
            raise HTTPException(status_code=503, detail={"error": "CORR_NOT_READY"})
        return corr.state()

    @app.websocket("/ws/corr")
    async def ws_corr(websocket: WebSocket) -> None:
        corr: CorrelationEngine | None = websocket.app.state.corr
        if corr is None:
            await websocket.close()  # reject-before-accept(R4 N036)
            return
        await websocket.accept()
        try:
            # 先送當前快照:client 不必等到下一個 tick 才有畫面
            await websocket.send_json(corr.state())
            await relay(websocket, corr_ws.stream())
        except WebSocketDisconnect:
            return

    # ---- river(江波圖;index-river-chart SC-5)----

    @app.get("/api/river/state")
    async def river_state(request: Request) -> dict:
        corr: CorrelationEngine | None = request.app.state.corr
        if corr is None:
            raise HTTPException(status_code=503, detail={"error": "RIVER_NOT_READY"})
        return corr.river_snapshot()

    @app.websocket("/ws/river")
    async def ws_river(websocket: WebSocket) -> None:
        corr: CorrelationEngine | None = websocket.app.state.corr
        if corr is None:
            await websocket.close()  # reject-before-accept(R4 N036)
            return
        await websocket.accept()
        try:
            # 首則送全量 snapshot;之後每秒只送當前分鐘的 delta(全量每秒推 = 每分鐘數 MB)
            await websocket.send_json(corr.river_snapshot())
            await relay(websocket, river_ws.stream())
        except WebSocketDisconnect:
            return

    @app.websocket("/ws/index")
    async def ws_index(websocket: WebSocket) -> None:
        index: IndexEngine | None = websocket.app.state.index
        if index is None:
            await websocket.close()  # reject-before-accept(R4 N036)
            return
        await websocket.accept()
        try:
            await relay(websocket, index.stream())
        except WebSocketDisconnect:
            return

    @app.websocket("/ws/stock")
    async def ws_stock(websocket: WebSocket) -> None:
        """個股 WS。engine 缺席時**不再立即 close**(XR-3):同一條通道也載 hub 的
        訊號,而 hub 的匯流排住在 app 層,與達錢 4 在否無關。

        兩種 stock 缺席改在 accept **之前**拒握手(R4 N036 reject-before-accept):
        - boot 未完成 —— 早連的 client 會錯過 engine 起來後的自選 seed,
          「拒 → 前端重連 → 拿 seed」的自癒比掛著一條空流好;
        - hub 亦 None(壞規則檔 / hub start 炸)—— 這條通道確實沒有任何生產者,
          留著就是永遠無流量的殭屍連線,而前端的提示靠 `wsStatus === "closed"`。
        """
        # 三個旗標(stock / boot_done / signal_hub)在 accept **之前**同一個同步區塊讀:
        # accept 是 await,跨它讀取會拿到分屬兩個時點的快照。搬到 accept 前仍是單一時點;
        # 殘餘 race = 讀到 stock=None & boot_done=False 後 boot 恰好完成 → 這代被拒,client
        # 退避重連即拿到 seed。stock=None & boot_done=True 是終態(XR-3:TC4 從未起要重啟
        # server),不會被 accept 之後的變化推翻。
        state = websocket.app.state
        stock: StockEngine | None = state.stock
        if stock is None:
            if not state.boot_done or state.signal_hub is None:
                await websocket.close()
                return
            await websocket.accept()
            try:
                # 首則 status seed:前端的「連線異常」提示靠 `status.tc4 === "down"`,
                # 而 `status` 初值是 `{tc4: "up"}` —— 沒有這則,掛著的空流會讓 TC4-off
                # 完全無提示(比舊的立即 close 更糟)。形狀與 engine 發的 status 一致。
                # 無 quote seed:沒有 engine 就沒有現值可種。
                await relay(
                    websocket,
                    stock_ws.stream(
                        # engine=False 是「真分態」的唯一訊號源(N109 / L78):engine 發的
                        # status 一律 engine=True,前端據此分「等自癒」與「去重啟伺服器」。
                        seed=[{"type": "status", "tc4": "down", "backfilling": None, "engine": False}]
                    ),
                )
            except WebSocketDisconnect:
                return
            return
        await websocket.accept()
        try:
            await relay(websocket, stock.stream())
        except WebSocketDisconnect:
            return

    # ---- capital 沿用的例外映射(capital_api.py:7,270 明文依賴這兩個 handler) ----
    # 舊 TC4 trade 路連同 _TRADE_ERROR_MAP 已整段除役;下列兩者由群益下單路徑 raise,
    # 刪掉會讓退單/審計失敗被全域 handler 吞成 502 TC4_DOWN(靜默破壞錯誤契約)。

    @app.exception_handler(AuditWriteError)
    async def _audit_write_failed(request: Request, exc: AuditWriteError) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": {"error": "AUDIT_WRITE_FAILED"}})

    @app.exception_handler(BrokerRejectedError)
    async def _broker_rejected(request: Request, exc: BrokerRejectedError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={
                "detail": {
                    "error": "BROKER_REJECTED",
                    "err_code": exc.err_code,
                    "err_msg": exc.err_msg,
                }
            },
        )

    return app
