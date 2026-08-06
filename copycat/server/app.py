"""FastAPI app:route 只 raise 不 catch;error contract {"detail": {"error": code}}(§2)。"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date as _date
from pathlib import Path
from typing import AsyncGenerator, Awaitable, Callable, Final, TypeVar, cast

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from copycat.live.trade_models import BrokerRejectedError
from copycat.breadth_config import load_breadth_config
from copycat.capital import factory as capital_factory
from copycat.capital.client import CapitalClient
from copycat.server import build_info, breadth_fetch, finmind_token
from copycat.server.audit import AuditWriteError
from copycat.corr_config import load_config as load_corr_config
from copycat.server.breadth_engine import (
    BreadthEngine,
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
from copycat.live.stock_source import Bar
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
from copycat.server.signal_hub import SignalHub
from copycat.server.stkfut_catalog import StkfutCatalog
from copycat.server.stock_engine import StockEngine, StockSource
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
from copycat.tc4common import TC4_DEFAULT_PORT

logger = logging.getLogger(__name__)

#: 期指鍵(近全盤別 `session=allday` 專屬 —— 加權 / 櫃買沒有夜盤)。
FUTURES_MARKET_KEYS = ("TXF", "MXF", "TMF")

#: 大盤頁支援的標的鍵。值域小且固定 → 白名單比 regex 好:非法鍵一律 400 BAD_KEY,
#: 不讓打錯的字串一路走到 TC4 才回空(那會被誤讀成「沒資料」)。
MARKET_KEYS = ("TWSE", "OTC") + FUTURES_MARKET_KEYS

#: `?session=` 的值域。
MARKET_SESSIONS = ("day", "allday")


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
) -> dict:
    """大盤 K 線回應(index-board N-5)。

    `meta` 不是裝飾:前端固定把它渲染成一行「來源 · 涵蓋期間」,讓「壞了 vs 沒資料」
    看畫面就能答(/adhd 三個 frame 收斂到的同一點)。`source` 必須是**實際走到的分支**,
    不能是預期值 —— DK 空時 fallback 成 1K 聚合而 meta 仍標 tc4_dk,等於在最可能出事的
    那條路上說謊(review P1-4)。
    """
    # volume 未指定時**由資料判定**:指數(IX0001)的 DK/1K 沒有量欄位,`_int_field`
    # 缺值回 0 → 整條序列 v=0。標 volume=true 會讓前端畫一排貼底的 0 高柱,與「真的
    # 零成交」在畫面上無法區分 —— 正是 SC-6 要避免的假造零(2026-07-30 real-env 抓到)。
    has_volume = volume if volume is not None else any(b["v"] > 0 for b in bars)
    return {
        "key": key,
        "tf": tf,
        "bars": bars,
        "meta": {
            "source": source,
            "coverage_from": bars[0]["t"][:10] if bars else None,
            "coverage_to": bars[-1]["t"][:10] if bars else None,
            "partial_last": partial_last,
            "volume": has_volume,
            "refusal": refusal,
            "synth_since": synth_since,
        },
    }


# sentinel:__main__ 顯式傳入才建真 source(測試不傳 → None → 零連線)
DEFAULT_STOCK: Final = object()  # __main__ 傳入才建真 StockQuoteSource
DEFAULT_INDEX: Final = object()  # 同語意(index-board IR9)
DEFAULT_FUTURES: Final = object()  # 同語意(capital-order SC-8)
DEFAULT_CORR: Final = object()  # 同語意(realtime-correlation SC-6)
DEFAULT_BREADTH: Final = object()  # 同語意(market-overview R2 SC-3;→ 真 FinMind 取數層)

#: breadth 引擎的注入點三元組(snapshot / stock_info / disposition)。
BreadthFetchers = tuple[SnapshotFetch, StockInfoFetch, DispositionFetch]


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


def _default_source() -> QuoteSource:
    from copycat.live.tc4 import TC4QuoteSource  # 延遲 import:測試不觸 pyzmq/TC4

    return TC4QuoteSource(
        port=_tc4_port(),
        backfill_date=os.environ.get("TXO_BACKFILL_DATE"),
    )


def _default_stock_source() -> StockSource:
    from copycat.live.stock_source import StockQuoteSource  # 延遲 import:測試不觸 pyzmq

    return StockQuoteSource(port=_tc4_port())


def _default_index_source() -> IndexSource:
    from copycat.live.stock_source import StockQuoteSource  # 獨立 session(指數專用)

    return StockQuoteSource(port=_tc4_port())


def _default_futures_source() -> FuturesSource:
    from copycat.live.futures_source import FuturesQuoteSource  # 延遲 import:測試不觸 pyzmq

    return FuturesQuoteSource(port=_tc4_port())


def _default_corr_source() -> CorrSource:
    from copycat.live.corr_source import CorrQuoteSource  # 延遲 import:測試不觸 pyzmq

    return CorrQuoteSource(port=_tc4_port())


def create_app(
    source: QuoteSource | None = None,
    *,
    stock_source: StockSource | object | None = None,
    index_source: IndexSource | object | None = None,
    futures_source: FuturesSource | object | None = None,
    corr_source: CorrSource | object | None = None,
    breadth_fetchers: BreadthFetchers | object | None = None,
    breadth_data_dir: Path | None = None,
    index_mis_fetch: Callable[[], OtcSnap | None] = fetch_otc_snapshot,
    stock_watchlist_path: Path | None = None,
    stock_names_path: Path | None = None,
    throttle_secs: float = 1.0,
    queue_maxsize: int = 10_000,
) -> FastAPI:
    wl_path = stock_watchlist_path if stock_watchlist_path is not None else WATCHLIST_DEFAULT_PATH
    # 名稱表是版控檔(必然存在)→ 沒有注入點的話「表不可用」這條降級路徑無法測
    names_path = stock_names_path if stock_names_path is not None else NAMES_DEFAULT_PATH
    overlay_cache = OverlayCache()  # per-app 實例(impl-spec R9:module-level 跨測試汙染)
    bars_cache = BarsCache()  # 同上;K 線兩段式 cache(server/bars.py)
    capital_ws = WsBroadcaster()  # capital/futures WS fanout(lifespan 綁 publish)
    futures_ws = WsBroadcaster()
    corr_ws = WsBroadcaster()
    river_ws = WsBroadcaster()  # 江波圖每秒 delta(全量走 REST/WS 首則;index-river-chart SC-5)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        # 最先做:引擎起不來時 banner 也要印得出來(「這台是哪一版」是排查的第一個問題)
        app.state.build = build_info.capture()
        logger.info("%s", app.state.build.banner())
        runtime = EngineRuntime(
            source if source is not None else _default_source(),
            throttle_secs=throttle_secs,
            queue_maxsize=queue_maxsize,
            # 固定日回補模式(休市日)停用時段切換偵測:跨界重跑只會重拿同一份
            # 指定日資料(spec R5)
            session_rollover=os.environ.get("TXO_BACKFILL_DATE") is None,
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
        # 兩者必須同點初始化:少了 boot_error,正常路徑的 /api/ready 直取屬性會
        # AttributeError → 被全域 handler 轉成 502
        app.state.boot_done = False
        app.state.boot_error = None
        booted = _Booted()

        async def _boot_all() -> None:
            """引擎啟動序列(背景 task)。**順序即依賴**(current-state §2),不可重排、
            不可並行:watchlist_service 先於 signals、signals 需 stock、index 綁
            runtime.spot、capital 先 set_broadcast 再 start、corr 後於 futures。

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
                    _default_stock_source() if stock_source is DEFAULT_STOCK else stock_source
                )
                if resolved_stock is None:
                    return None
                stkfut_source = resolved_stock
                import datetime as _dt

                backfill_date = os.environ.get("TXO_BACKFILL_DATE")
                return StockEngine(
                    cast(StockSource, resolved_stock),
                    trade_date=backfill_date or f"{_dt.date.today():%Y-%m-%d}",
                    throttle_secs=throttle_secs,
                    checkpoint=backfill_date is None,
                )

            async def _start_stock(o: StockEngine) -> None:
                await o.start()
                # 自選回填屬於「帶到就緒」的一部分:load_watchlist 對壞檔不吞例外,
                # 現況正是由 _boot 的 except 接住(留在 try 內是行為契約)
                persisted = load_watchlist(wl_path)["codes"]
                if persisted:
                    await o.set_watchlist(persisted)

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
            # 不會有「同 symbol 跨 session 只推一邊」的問題,但多開一條 TC4 登入沒有理由
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
                if stock is None:
                    return None
                engine = stock
                return SignalHub(
                    load_signals_config(),
                    publish=engine._publish,
                    daily_bars=engine.daily_bars,
                    notify_fallback=notify_discord,
                    # 自選檔所在目錄 = 本專案的 data 根(`data/stock_watchlist.json`)→
                    # jsonl 與開關檔天然跟著它走,測試注入自選路徑即整組落在 tmp_path
                    data_dir=wl_path.parent,
                    # 日別語意由 engine 單一持有(兩段式 rollover 期間 stage2 才前進)
                    trade_date_fn=lambda: engine.trade_date,
                    # 同群摘要(group-grid SC-1/2)。groups 只在 `on_watchlist` 讀檔
                    # (自選變更時),quotes 在 Discord worker 讀 engine 現值 —— 兩者
                    # 都輕同步,不進熱路徑。漏接的失效樣態是「通知少一段尾巴」而已,
                    # 所以由 booted app 的接線測試把關。
                    groups_fn=lambda: load_watchlist(wl_path)["groups"],
                    quotes_fn=engine.quotes,
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
                if stock is not None:  # `_make_signals` 已保證;narrowing 用
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
                    _default_index_source() if index_source is DEFAULT_INDEX else index_source
                )
                if resolved_index is None:
                    return None
                import datetime as _dt

                backfill_date = os.environ.get("TXO_BACKFILL_DATE")
                return IndexEngine(
                    cast(IndexSource, resolved_index),
                    # TXO runtime 現貨轉供(design IR1);runtime 掛掉時恆 None
                    txf_getter=runtime.spot_millipts,
                    mis_fetch=index_mis_fetch,
                    trade_date=backfill_date or f"{_dt.date.today():%Y-%m-%d}",
                    rollover=backfill_date is None,
                    throttle_secs=throttle_secs,
                )

            index = await _boot(
                "index",
                "index engine 初始化非預期失敗,指數功能停用(其餘不受影響)",
                _make_index,
                lambda o: o.start(),
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
                    resolved_futures: FuturesSource | None = _default_futures_source()
                else:
                    resolved_futures = cast("FuturesSource | None", futures_source)
                if resolved_futures is None:
                    return None
                fut_src = resolved_futures
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
                if corr_source is DEFAULT_CORR:
                    resolved_corr: CorrSource | None = _default_corr_source()
                else:
                    resolved_corr = cast("CorrSource | None", corr_source)
                if resolved_corr is None:
                    return None
                corr_src = resolved_corr
                futures_engine = futures
                return CorrelationEngine(
                    lambda: corr_src,
                    config=load_corr_config(),
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
                    )
                else:
                    # 顯式注入的三元組**跳過 token 閘**:fake 取數層根本不看 token,
                    # 而 verify server / 測試環境本來就沒有(有閘就恆停用 → 驗不到)
                    token = "fake-token"
                    fetchers = cast("BreadthFetchers", breadth_fetchers)
                snapshot_fetch, stock_info_fetch, disposition_fetch = fetchers
                return BreadthEngine(
                    token=token,
                    config=load_breadth_config(),
                    snapshot_fetch=snapshot_fetch,
                    stock_info_fetch=stock_info_fetch,
                    disposition_fetch=disposition_fetch,
                    data_dir=breadth_data_dir,  # None → repo root data/market
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
            # 關機反序:breadth → signals → corr → futures → capital → index → stock →
            # runtime(corr 依賴 futures.state(),必須先收;signals 在 breadth 之後 ——
            # fanout worker 還活著時對已收攤的 stock engine publish 會炸在關機路徑上)
            if booted.breadth is not None:
                try:
                    await booted.breadth.close()
                except Exception:
                    logger.exception("breadth close 失敗(關機續行)")
            if booted.signals is not None and booted.signals_close is not None:
                try:
                    # bot 先於 hub(hub 的 sender 指向 bot)—— 順序封在 `_close_signals` 內
                    await booted.signals_close(booted.signals)
                except Exception:
                    logger.exception("signals close 失敗(關機續行)")
            if booted.corr is not None:
                try:
                    await booted.corr.close()
                except Exception:
                    logger.exception("corr close 失敗(關機續行)")
            if booted.futures is not None:
                try:
                    await booted.futures.close()
                except Exception:
                    logger.exception("futures close 失敗(關機續行)")
            if booted.capital is not None:
                try:
                    await asyncio.to_thread(booted.capital.close)  # join COM 執行緒(≤5s)
                except Exception:
                    logger.exception("capital close 失敗(關機續行)")
            if booted.index is not None:
                try:
                    await booted.index.close()
                except Exception:
                    logger.exception("index close 失敗(關機續行)")
            if booted.stock is not None:
                try:
                    await booted.stock.close()
                except Exception:
                    logger.exception("stock close 失敗(關機續行)")
            await runtime.close()

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
            await websocket.send_json(runtime.latest_snapshot())
            await relay(websocket, runtime.snapshots())
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
        """訊號 route 的共同閘(design §7):先 `_stock()` 再 hub —— 兩者皆 503 NOT_READY,
        但順序決定「達錢 4 沒開」與「訊號層單獨降級」在 log 上的可分辨性。"""
        _stock(request)
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
        # today = 本機日界(= 台北,部署綁本機;design R6/R13);backfill 模式亦以本機為準
        today = f"{_date.today():%Y-%m-%d}"
        cached = overlay_cache.get(code, today)
        if cached is not None:
            return cached
        result = build_overlay(await stock.daily_bars(code), today)
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
            bars, status = await build_minute(
                stock.bars_range, bars_cache, code, clamp_days(days_n), today
            )
        # status:空的三種來源(逾時 / 真無資料 / 斷線)原本在前端收斂成同一句
        # 「無 K 線資料」。加欄位 = 向後相容(舊前端忽略,新前端對缺欄位 default "ok")
        return {"code": code, "tf": tf, "bars": bars, "status": status}

    # ---- stock signals(stock-signals design §7)----

    @app.get("/api/stock/signals/today")
    async def stock_signals_today(request: Request) -> dict:
        """當日訊號歷史(SC-7):讀 hub 的 jsonl,壞行跳過。

        前端 reconnect 後拿它當 baseline 自癒 —— WS 斷線期間丟掉的訊號由這裡補回。
        """
        return {"signals": _signals(request).today_signals()}

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
        return {"code": code, **entry}

    @app.get("/api/stock/state/{code}")
    async def stock_state(request: Request, code: str) -> dict:
        stock = _stock(request)
        _valid_code(code)
        await stock.set_main(code)  # 含回補觸發(design §2.5)
        return stock.snapshot(code)

    @app.get("/api/stock/group-state")
    async def stock_group_state(request: Request, codes: str = "") -> dict:
        """群組檢視的唯讀 batch(group-grid SC-4)。

        **刻意不重用 `/api/stock/state/{code}`**:那條路會 `set_main`,群組檢視每分鐘
        對最多 30 檔各要一次狀態 = 每分鐘把主圖搶走 30 次,主圖分時線就此凍結,而畫面
        上只表現為「圖不動了」沒有任何錯誤訊號。

        逗號分隔的 codes 自行解析(不用 `list[str]` query):FastAPI 的重複參數形對
        30 個 code 會長到難以閱讀,而轉換失敗回的是 422 + list 形 detail,不符全站
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
        (CLAUDE.md §8 同 symbol 跨 session 只推一邊):
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

        if key == "TWSE":
            index = _index(request)

            async def tagged_source(_c: str, tf_: str, s: str, e: str) -> TaggedBars:
                return TaggedBars(*await index.bars_range(tf_, s, e))
        else:
            futures: FuturesEngine | None = request.app.state.futures
            if futures is None:
                raise HTTPException(status_code=503, detail={"error": "NOT_READY"})

            async def tagged_source(_c: str, tf_: str, s: str, e: str) -> TaggedBars:
                # 期指沒有 DK→1K 的 fallback 分支,tag 恆定;回空 = 借不到(engine 已 log)
                got = await futures.bars_range(key, tf_, s, e, session=eff_session)
                return TaggedBars(got, "tc4_dk" if got else "unavailable")

        # 兩個閉包的第二元素語意不同(source tag vs 三態 status)且同為 str ——
        # 名字必須隔開,否則接錯的表現是 meta.source 靜默變成 "ok"(spec R5)
        async def plain_with_status(c: str, tf_: str, s: str, e: str) -> BarsResult:
            # 大盤路徑本輪不做三態(out of scope):固定 "ok",空態仍由 source tag 表述
            return BarsResult((await tagged_source(c, tf_, s, e)).bars, "ok")

        # 分鐘路徑的 cache code 加 |M 後綴:裸 "IX0001" 會與 /api/stock/bars/IX0001
        # (走 **stock** session)共用 `_hist` / `_today` / `_empty` 同一格 —— 那會讓
        # W-12「歷史一律從持有其 REALTIME 訂閱的 session 問」在快取層被繞過(review P1-6)。
        # 長窗路徑的 |L 後綴同理(review P2-1)。期指的 F: 前綴含冒號,本來就撞不到。
        code = ("IX0001|M" if tf == "1" else "IX0001") if key == "TWSE" else f"F:{key}"
        if tf == "1":
            bars, _ = await build_minute(
                plain_with_status, bars_cache, code, days_n, today, session=eff_session
            )
            return _market_payload(
                key,
                tf,
                bars,
                source="tc4_1k" if bars else "unavailable",
                partial_last=is_partial_last(bars, tf, today),
            )
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

    @app.websocket("/ws/breadth")
    async def ws_breadth(websocket: WebSocket) -> None:
        breadth = _breadth(websocket)
        await websocket.accept()
        if breadth is None:
            if not _breadth_booted(websocket):
                # 載入中:先送一則載入中 scalar 再關,client 退避重連時 boot 已完成
                # → 屆時拿到的是真狀態或「未設定」,不會與後者同形(review P2-1)
                await websocket.send_json(
                    {
                        "type": "breadth",
                        "trade_date": None,
                        "as_of": None,
                        "stale": True,
                        "counts": None,
                        "last_minute": None,
                    }
                )
            await websocket.close()
            return
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
        await websocket.accept()
        if corr is None:
            await websocket.close()
            return
        try:
            # 先送當前快照:client 不必等到下一個 tick 才有畫面
            await websocket.send_json(corr.state())
            await relay(websocket, corr_ws.stream())
        except WebSocketDisconnect:
            return

    # ---- river(六腿江波圖;index-river-chart SC-5)----

    @app.get("/api/river/state")
    async def river_state(request: Request) -> dict:
        corr: CorrelationEngine | None = request.app.state.corr
        if corr is None:
            raise HTTPException(status_code=503, detail={"error": "RIVER_NOT_READY"})
        return corr.river_snapshot()

    @app.websocket("/ws/river")
    async def ws_river(websocket: WebSocket) -> None:
        corr: CorrelationEngine | None = websocket.app.state.corr
        await websocket.accept()
        if corr is None:
            await websocket.close()
            return
        try:
            # 首則送全量 snapshot;之後每秒只送當前分鐘的 delta(全量每秒推 = 每分鐘數 MB)
            await websocket.send_json(corr.river_snapshot())
            await relay(websocket, river_ws.stream())
        except WebSocketDisconnect:
            return

    @app.websocket("/ws/index")
    async def ws_index(websocket: WebSocket) -> None:
        index: IndexEngine | None = websocket.app.state.index
        await websocket.accept()
        if index is None:
            await websocket.close()
            return
        try:
            await relay(websocket, index.stream())
        except WebSocketDisconnect:
            return

    @app.websocket("/ws/stock")
    async def ws_stock(websocket: WebSocket) -> None:
        stock: StockEngine | None = websocket.app.state.stock
        await websocket.accept()
        if stock is None:
            await websocket.close()
            return
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
