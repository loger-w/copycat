from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Callable

from copycat.live.stock_source import Bar, BarsStatus
from copycat.server.stock_engine import StockEngine


def _quote(
    code: str = "2330",
    *,
    cum: int = 1,
    price: str = "2380",
    qty: str = "1",
    date: str = "20260721",
    symbol: str | None = None,
) -> dict:
    return {
        "Symbol": symbol or f"TC.S.TWS.{code}",
        "Security": code,
        "SecurityName": "台積電",
        "TradingPrice": price,
        "TradeQuantity": qty,
        "TradeVolume": str(cum),
        "TradeDate": date,
        "FilledTime": "25751",
        "PreciseTime": "25751000000",
        "Bid": "2375",
        "Ask": "2380",
        "BidVolume": "10",
        "AskVolume": "10",
        "ReferencePrice": "2320",
        "UpperLimitPrice": "2550",
        "LowerLimitPrice": "2090",
        "YClosedPrice": "2320",
        "YTradeVolume": "100",
        "OpenTime": "90000",
        "CloseTime": "133000",
        "TradeStatus": "0",
    }


class FakeSource:
    def __init__(self) -> None:
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.trade_dates: list[str] = []
        self.backfills: list[str] = []
        self.fail_subscribe: set[str] = set()
        # 「訂閱丟非連線類例外」(壞電文 / wrapper 內部型別錯)—— `fail_subscribe` 丟的
        # ConnectionError 是引擎預期並吞掉的那條路,測不到 task 帶例外結束的情境
        self.subscribe_error: Exception | None = None
        self.subscribe_gate: threading.Event | None = None
        self.closed = False
        self.backfill_gate: threading.Event | None = None
        self.backfill_result: list = []
        # 逐碼結果(優先於 `backfill_result`)。單一 `backfill_result` 對每個 code 都回
        # 同一份 → 「job 有沒有落到**別檔**的 state」根本測不出來(兩邊都會有值,而且
        # 那些值來自各自的 job)。收件人正確性要鎖,就得讓不同 code 的回補可分辨。
        self.backfill_results: dict[str, list] = {}
        self.backfill_error: Exception | None = None
        self.on_message: Callable[[dict], None] | None = None
        self.on_no_data: Callable[[str], None] | None = None
        self.on_reconnect: Callable[[], None] | None = None
        self.on_subscribe: Callable[[str], None] | None = None

    def subscribe_symbol(self, code: str) -> None:
        if self.subscribe_error is not None:
            raise self.subscribe_error
        if code in self.fail_subscribe:
            raise ConnectionError(f"SUBQUOTE fail {code}")
        if self.subscribe_gate is not None:
            self.subscribe_gate.wait(timeout=5)
        self.subscribed.append(code)
        # 真 TC4 在 SUB 回來後幾乎立刻推第一則 REALTIME。這個 hook 讓測試能重現
        # 「報價在 set_watchlist 的 await 窗內到貨」的競態(round4 項 4 R7)。
        if self.on_subscribe is not None:
            self.on_subscribe(code)

    def unsubscribe_symbol(self, code: str) -> None:
        self.unsubscribed.append(code)

    def backfill(self, code: str) -> list:
        self.backfills.append(code)
        if self.backfill_error is not None:
            raise self.backfill_error
        if self.backfill_gate is not None:
            self.backfill_gate.wait(timeout=5)
        if code in self.backfill_results:
            return list(self.backfill_results[code])
        return list(self.backfill_result)

    def fetch_bars_range(
        self, code: str, tf: str, start_date: str, end_date: str
    ) -> tuple[list[Bar], BarsStatus]:
        """Protocol 新增方法(change-spec R2-1);既有斷言不依賴,回空即可。"""
        return [], "ok"

    def fetch_daily_bars(self, code: str, n: int = 25) -> list:
        return []

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        self.on_message = cb

    def set_on_no_data(self, cb: Callable[[str], None]) -> None:
        self.on_no_data = cb

    def set_trade_date(self, trade_date: str) -> None:
        self.trade_dates.append(trade_date)

    def close(self) -> None:
        self.closed = True


async def _drain(engine: StockEngine) -> None:
    """讓 loop 消化 call_soon_threadsafe 與背景 task。"""
    for _ in range(20):
        await asyncio.sleep(0.01)


async def _make() -> tuple[StockEngine, FakeSource]:
    src = FakeSource()
    engine = StockEngine(src, trade_date="2026-07-21", throttle_secs=0.01, checkpoint=False)
    await engine.start()
    return engine, src


class TestRefcountPool:
    async def test_two_owners_one_real_subscribe(self) -> None:
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        await engine.set_main("2330")
        assert src.subscribed.count("2330") == 1
        await engine.set_main("5483")  # 2330 仍在 watchlist,不退訂
        assert "2330" not in src.unsubscribed
        await engine.set_watchlist([])  # last owner 退 → 真退訂
        assert "2330" in src.unsubscribed
        await engine.close()

    async def test_subscribe_failure_rolls_back_refs(self) -> None:
        engine, src = await _make()
        src.fail_subscribe.add("9999")
        await engine.set_watchlist(["9999"])
        # 失敗回滾:再加一次仍會真訂(refs 未殘留)
        src.fail_subscribe.discard("9999")
        await engine.set_watchlist(["9999"])
        assert src.subscribed.count("9999") == 1
        await engine.close()

    async def test_same_codes_resubscribe_is_a_noop_for_the_source(self) -> None:
        """group-only 變更(建群 / 改名 / 移出群組)會以**相同 codes** 再呼叫一次
        `set_watchlist`(watchlist_service R9 的前提)。那條路一旦產生 UNSUB/SUB,
        盤中改個群組就會讓整份自選斷訂重訂 —— 畫面是一排「-」而且沒有任何錯誤訊號。
        """
        engine, src = await _make()
        await engine.set_watchlist(["2330", "2317"])
        subscribed = len(src.subscribed)
        unsubscribed = len(src.unsubscribed)
        assert subscribed > 0  # 基準非零:第一次真的訂到了,第二次的「不變」才有意義

        await engine.set_watchlist(["2330", "2317"])

        assert len(src.subscribed) == subscribed
        assert len(src.unsubscribed) == unsubscribed
        await engine.close()


class TestBackfillGuard:
    async def test_backfill_lands_on_its_own_state_after_main_switch(self) -> None:
        """**事前標記該變的既有斷言**(design v3 R12 / PLAN R1/R2)。

        舊名 `test_stale_backfill_not_applied_after_main_switch` 釘的是「回補中切走主圖 →
        結果丟棄」,那條語意把 job 的收件人綁在 `_main` 上。群組檢視要替**非主圖成員**補
        當日分鐘資料,同一條單工 worker 會收到不屬於主圖的 job —— 綁 `_main` 等於那些 job
        全部靜默丟棄(零錯誤訊號,卡片只是一直空著)。

        新契約 = **job 自帶 code,落地到它自己的 state**;generation 作廢照舊
        (`test_rollover_generation_voids_inflight_backfill` 不動 —— 那條鎖的是跨日,
        與收件人無關)。
        """
        engine, src = await _make()
        src.backfill_gate = threading.Event()
        from copycat.live.stock_models import StockTick

        # 逐碼結果:B 的回補回空,所以「B 有 tick」只可能是 A 的 job 串了檔
        src.backfill_results = {
            "2330": [
                StockTick(code="2330", price_milli=2_380_000, qty=5, cum_vol=5,
                          time="09:01:00.000", trade_date="2026-07-21", side="outer",
                          is_trial=False)
            ]
        }
        await engine.set_main("2330")
        await engine.set_main("5483")  # A 回補中切 B
        src.backfill_gate.set()
        await _drain(engine)
        ticks = engine.snapshot("2330")["ticks"]
        assert len(ticks) == 1  # A 的結果落到 A 自己的 state
        assert ticks[0]["p"] == 2_380_000
        # 且**不會**串到 B:收件人是 job 自帶的 code,不是「當下主圖」
        assert engine.snapshot("5483")["ticks"] == []
        await engine.close()

    async def test_non_main_job_backfills_end_to_end(self) -> None:
        """R1 端到端:主圖是別檔時,非主圖成員的 job 仍要跑完並產出當日分鐘列。

        (群組成員的入列點在 T1 後半的 `group_snapshot`;這裡直接入列 job,鎖的是
        worker 這一段與收件人無關。)
        """
        engine, src = await _make()
        from copycat.live.stock_models import StockTick

        src.backfill_result = [
            StockTick(code="2330", price_milli=2_400_000, qty=3, cum_vol=3,
                      time="09:01:00.000", trade_date="2026-07-21", side="outer",
                      is_trial=False)
        ]
        await engine.set_watchlist(["2330"])
        await engine.set_main("5483")
        await _drain(engine)
        engine._backfill_jobs.put_nowait(("2330", engine._generation))
        await _drain(engine)
        minutes = engine.snapshot("2330")["minutes"]
        assert minutes["541"]["c"] == 2_400_000  # 09:01 = 9*60+1
        assert "2330" in engine._backfilled  # 套用成功才進帳
        await engine.close()

    async def test_reconnect_clears_backfill_bookkeeping(self) -> None:
        """R4:reconnect **不** bump generation(實碼事實)。

        兩個記帳 set 沒被顯式清掉的話,「今日已回補」會一路留到收盤 —— 斷線那段的缺口
        整天補不回來,而 tick 流恢復後畫面看起來完全正常。主圖以外的成員尤其嚴重:
        reconnect 只重入列 `_main` 一檔,其餘全靠這次清空才有機會再被 `group_snapshot`
        入列。
        """
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        engine._backfill_jobs.put_nowait(("2330", engine._generation))
        await _drain(engine)
        assert "2330" in engine._backfilled  # 前提:確實記過帳,否則這條測不到東西
        assert src.on_reconnect is not None
        src.on_reconnect()
        await _drain(engine)
        assert "2330" not in engine._backfilled
        assert "2330" not in engine._backfill_pending
        await engine.close()

    async def test_rollover_stage2_clears_backfill_bookkeeping(self) -> None:
        """R4 的另一半:跨日後「今日已回補」必須全部作廢(記帳是日別語意)。"""
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        engine._backfill_jobs.put_nowait(("2330", engine._generation))
        await _drain(engine)
        assert "2330" in engine._backfilled
        engine.rollover_stage1("2026-07-22")
        assert src.on_message is not None
        src.on_message(_quote(cum=50, date="20260722"))  # 首筆新日 tick → stage2
        await _drain(engine)
        assert "2330" not in engine._backfilled
        assert "2330" not in engine._backfill_pending
        await engine.close()

    async def test_rollover_generation_voids_inflight_backfill(self) -> None:
        engine, src = await _make()
        src.backfill_gate = threading.Event()
        from copycat.live.stock_models import StockTick

        src.backfill_result = [
            StockTick(code="2330", price_milli=2_380_000, qty=12000, cum_vol=12000,
                      time="09:01:00.000", trade_date="2026-07-21", side="outer",
                      is_trial=False)
        ]
        await engine.set_main("2330")
        engine.rollover_stage1("2026-07-22")
        src.backfill_gate.set()
        await _drain(engine)
        # 舊日回補不得落地墊高 cum → 新日 cum=50 tick 必須可 ingest
        assert src.on_message is not None
        src.on_message(_quote(cum=50, date="20260722"))
        await _drain(engine)
        snap = engine.snapshot("2330")
        assert snap["last"] is not None
        assert snap["last"]["cum_vol"] == 50
        await engine.close()


class TestRollover:
    async def test_holiday_stage1_without_new_day_tick_keeps_state(self) -> None:
        engine, src = await _make()
        await engine.set_main("2330")
        assert src.on_message is not None
        src.on_message(_quote(cum=100))
        await _drain(engine)
        engine.rollover_stage1("2026-07-26")  # 假日:之後永無新日推播
        await _drain(engine)
        assert engine.snapshot("2330")["last"]["cum_vol"] == 100  # 不清空
        assert "2026-07-26" in src.trade_dates  # 但日窗已換(重掛)
        await engine.close()

    async def test_stage2_first_new_day_tick_resets_and_ingests(self) -> None:
        engine, src = await _make()
        await engine.set_main("2330")
        assert src.on_message is not None
        src.on_message(_quote(cum=12000))
        await _drain(engine)
        engine.rollover_stage1("2026-07-22")
        src.on_message(_quote(cum=50, date="20260722"))
        await _drain(engine)
        snap = engine.snapshot("2330")
        assert snap["last"]["cum_vol"] == 50  # reset 後首筆被 ingest,不被 stale-drop
        # 「reset 後首筆 ingest 且判到側」的唯一證明(M3 前為 snap["cum_outer"];
        # 該欄位退出 wire 後改讀 minutes 的同源聚合,行為鎖不變)
        assert snap["minutes"]["657"]["o"] == 1
        await engine.close()


class TestStreamAndStatus:
    async def test_stream_receives_tick_and_book(self) -> None:
        engine, src = await _make()
        await engine.set_main("2330")
        stream = engine.stream()
        assert src.on_message is not None
        src.on_message(_quote(cum=1))
        await _drain(engine)
        got: list[dict] = []
        try:
            while True:
                got.append(await asyncio.wait_for(anext(stream), timeout=0.3))
        except (TimeoutError, asyncio.TimeoutError):
            pass
        types = {m["type"] for m in got}
        assert "tick" in types
        assert "book" in types
        tick_msg = next(m for m in got if m["type"] == "tick")
        assert tick_msg["code"] == "2330"
        assert tick_msg["p"] == 2_380_000
        assert tick_msg["seq"] == 1
        # round5:明細要買賣價、江波圖當日高低線要能盤中更新。
        # h/l 掛 tick 而不另立 meta 訊息型別 —— engine 只發 tick/book/watchlist_quote 三種,
        # 而當日高低本來就只在成交時才會變,與 tick 同步天然正確。
        assert tick_msg["b"] == 2_375_000
        assert tick_msg["a"] == 2_380_000
        assert tick_msg["h"] == 2_380_000
        assert tick_msg["l"] == 2_380_000
        await engine.close()

    async def test_tick_high_low_track_new_extreme(self) -> None:
        engine, src = await _make()
        await engine.set_main("2330")
        await _drain(engine)
        stream = engine.stream()
        assert src.on_message is not None
        src.on_message(_quote(cum=1, price="2380"))
        src.on_message(_quote(cum=2, price="2410"))
        await _drain(engine)
        got: list[dict] = []
        try:
            while True:
                got.append(await asyncio.wait_for(anext(stream), timeout=0.3))
        except (TimeoutError, asyncio.TimeoutError):
            pass
        ticks = [m for m in got if m["type"] == "tick"]
        assert ticks[-1]["h"] == 2_410_000  # 新高跟著推
        assert ticks[-1]["l"] == 2_380_000
        await engine.close()

    async def test_reconnect_pushes_status_and_reenqueues_main_backfill(self) -> None:
        engine, src = await _make()
        await engine.set_main("2330")
        await _drain(engine)
        before = src.backfills.count("2330")
        stream = engine.stream()
        assert src.on_reconnect is not None
        src.on_reconnect()
        await _drain(engine)
        assert src.backfills.count("2330") > before  # 自癒重回補
        got: list[dict] = []
        try:
            while True:
                got.append(await asyncio.wait_for(anext(stream), timeout=0.3))
        except (TimeoutError, asyncio.TimeoutError):
            pass
        assert any(m["type"] == "status" for m in got)
        await engine.close()

    async def test_no_data_flag_published(self) -> None:
        engine, src = await _make()
        await engine.set_watchlist(["9998"])
        assert src.on_no_data is not None
        stream = engine.stream()
        src.on_no_data("9998")
        await _drain(engine)
        got: list[dict] = []
        try:
            while True:
                got.append(await asyncio.wait_for(anext(stream), timeout=0.3))
        except (TimeoutError, asyncio.TimeoutError):
            pass
        assert any(m["type"] == "watchlist_quote" and m["no_data"] for m in got)
        await engine.close()


class TestSnapshotShape:
    """M3:REST snapshot 只送有消費者的欄位。"""

    async def test_snapshot_omits_dead_wire_fields(self) -> None:
        """tc4 / backfilling 的畫面來源是 WS status 訊息(仍是活碼),snapshot 這三個
        欄位前端零讀取;stkfut_prod 更是每次 snapshot 白算一次 map 查找。"""
        engine, _ = await _make()
        await engine.set_main("2330")
        await _drain(engine)
        snap = engine.snapshot("2330")
        assert "tc4" not in snap
        assert "backfilling" not in snap
        assert "stkfut_prod" not in snap
        assert snap["code"] == "2330"  # 仍在的欄位不受波及
        assert snap["no_data"] is False
        await engine.close()

    async def test_status_message_still_carries_tc4_and_backfilling(self) -> None:
        """同名活碼護欄:WS status 訊息是畫面「回補中…」與連線徽章的唯一來源。"""
        engine, src = await _make()
        stream = engine.stream()
        assert src.on_reconnect is not None
        src.on_reconnect()
        await _drain(engine)
        got: list[dict] = []
        try:
            while True:
                got.append(await asyncio.wait_for(anext(stream), timeout=0.3))
        except (TimeoutError, asyncio.TimeoutError):
            pass
        status = next(m for m in got if m["type"] == "status")
        assert status["tc4"] == "up"
        assert status["backfilling"] is None
        await engine.close()


class TestWatchlistQuoteSeed:
    """round4 項 4:側欄開頁 / 盤後全是 `-` 的根因 —— quote 只有 tick 驅動的生產點,
    新 client 連上時沒有任何歷史訊息可收。修在 stream() 接點(開頁與重連天然自癒),
    與 ws_corr / ws_river「連線先送快照」的既成慣例一致。"""

    async def _collect(self, stream) -> list[dict]:
        got: list[dict] = []
        try:
            while True:
                got.append(await asyncio.wait_for(anext(stream), timeout=0.3))
        except (TimeoutError, asyncio.TimeoutError):
            pass
        return got

    async def test_stream_seeds_current_watchlist_quotes(self) -> None:
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        src.on_message(_quote(cum=7, price="2400"))
        await _drain(engine)
        # 新 client 在成交之後才連上 → 沒有種子的話這一則永遠收不到
        got = await self._collect(engine.stream())
        seeds = [m for m in got if m["type"] == "watchlist_quote" and m["code"] == "2330"]
        assert seeds, "連線時必須先送一輪 watchlist quote 種子"
        assert seeds[0]["p"] == 2_400_000
        assert seeds[0]["vol"] == 7
        assert seeds[0]["no_data"] is False
        # p 與 ref **互斥**:有成交時 ref 必為 None,否則消費端分不出「今天的價」與
        # 「昨天的基準」(round4 項 4 / review F9;原本只驗了反方向)
        assert seeds[0]["ref"] is None
        await engine.close()

    async def test_seed_uses_ref_field_never_p_when_no_trade(self) -> None:
        """盤前 / 盤後尚無成交:參考價走**獨立欄位**,絕不塞進 p ——
        塞進 p 會讓新舊 client 都把昨收讀成今價(資料誠實紅線)。"""
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        # 只有報價沒有成交(TradeVolume 0 → 無 tick,但 meta 會更新)
        quote = _quote(cum=0, qty="0")
        src.on_message(quote)
        await _drain(engine)
        got = await self._collect(engine.stream())
        seed = next(m for m in got if m["type"] == "watchlist_quote" and m["code"] == "2330")
        assert seed["p"] is None
        assert seed["chg_pct"] is None
        assert seed["ref"] == 2_320_000
        await engine.close()

    async def test_seed_absent_when_watchlist_empty(self) -> None:
        engine, _src = await _make()
        got = await self._collect(engine.stream())
        assert [m for m in got if m["type"] == "watchlist_quote"] == []
        await engine.close()

    async def test_set_watchlist_broadcasts_seed_for_added_codes(self) -> None:
        engine, _src = await _make()
        stream = engine.stream()
        await engine.set_watchlist(["2330"])
        await _drain(engine)
        got = await self._collect(stream)
        assert any(m["type"] == "watchlist_quote" and m["code"] == "2330" for m in got)
        await engine.close()

    async def test_meta_arriving_during_subscribe_still_pushes(self) -> None:
        """`_watchlist` 若在 acquire 的 await 窗之後才指派,這一則會被 gate 擋掉:
        TC4 在 SUB 後幾乎立刻推第一則 REALTIME,而每個 `await to_thread` 都讓出 loop
        → 第一檔的報價會在名單還沒指派時就進 `_handle_quote`;盤後沒有後續 tick、
        flush 只推 dirty → 該檔卡在 `-` 直到重整。"""
        engine, src = await _make()
        stream = engine.stream()

        def _on_sub(code: str) -> None:
            # 訂閱第二檔時,第一檔(_states 已建好)的報價到貨 —— 此刻 _watchlist 是否
            # 已指派,決定 meta 轉態補推會不會被擋掉
            if code == "5483":
                assert src.on_message is not None
                src.on_message(_quote(cum=0, qty="0"))

        src.on_subscribe = _on_sub
        await engine.set_watchlist(["2330", "5483"])
        await _drain(engine)
        got = await self._collect(stream)
        quotes = [m for m in got if m["type"] == "watchlist_quote" and m["code"] == "2330"]
        assert quotes, "meta 在訂閱 await 窗內到貨時仍要推播"
        assert quotes[-1]["ref"] == 2_320_000
        await engine.close()

    async def test_no_data_recovery_pushes_once_not_every_tick(self) -> None:
        """`no_data` 復原要補推,但**命中才推** —— 寫成無條件 publish 會變成每 tick 廣播,
        直接打穿 1s 節流(W-17)。"""
        # throttle 拉大到 60s:排除 1s flush loop 的貢獻,讓斷言只看轉態補推
        src = FakeSource()
        engine = StockEngine(src, trade_date="2026-07-21", throttle_secs=60, checkpoint=False)
        await engine.start()
        await engine.set_watchlist(["2330"])
        assert src.on_no_data is not None and src.on_message is not None
        src.on_no_data("2330")
        await _drain(engine)
        stream = engine.stream()
        src.on_message(_quote(cum=1))
        src.on_message(_quote(cum=2))
        src.on_message(_quote(cum=3))
        await _drain(engine)
        got = await self._collect(stream)
        # 首則是連線種子,復原補推只該有一則(不是三則)
        recoveries = [
            m
            for m in got[1:]
            if m["type"] == "watchlist_quote" and m["code"] == "2330" and not m["no_data"]
        ]
        assert len(recoveries) == 1
        assert recoveries[0]["p"] == 2_380_000  # 補推在 ingest 之後 → 帶新價不是空值
        await engine.close()

    async def test_seed_carries_limit_prices(self) -> None:
        """側欄漲跌停亮燈需要 upper/lower —— **不可用 chg_pct ≈ ±10% 猜**
        (ETF ±20%、無漲跌幅商品都會誤判;next-time 2026-07-31 條)。"""
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        src.on_message(_quote(cum=7, price="2400"))
        await _drain(engine)
        got = await self._collect(engine.stream())
        seed = next(m for m in got if m["type"] == "watchlist_quote" and m["code"] == "2330")
        assert seed["upper"] == 2_550_000
        assert seed["lower"] == 2_090_000

    async def test_no_data_message_carries_ref_key(self) -> None:
        """所有 watchlist_quote 產出點共用同一份 payload builder,形狀不得分歧。"""
        engine, src = await _make()
        await engine.set_watchlist(["9998"])
        assert src.on_no_data is not None
        stream = engine.stream()
        src.on_no_data("9998")
        await _drain(engine)
        got = await self._collect(stream)
        msg = next(m for m in got if m["type"] == "watchlist_quote" and m["no_data"])
        assert "ref" in msg

    async def test_no_data_message_clears_value_fields(self) -> None:
        """「無資料」時所有值欄位一律 None(round4 之前的既有契約,review F7)。
        讓 p 沿用最後已知值的話,訊息會變成「no_data=True 卻夾帶成交價」——
        現行側欄先判 no_data 所以畫面不會錯,但那是巧合式的保護。"""
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None and src.on_no_data is not None
        src.on_message(_quote(cum=5, price="2400"))  # 先有成交價
        await _drain(engine)
        stream = engine.stream()
        src.on_no_data("2330")
        await _drain(engine)
        got = await self._collect(stream)
        msg = next(m for m in got if m["type"] == "watchlist_quote" and m["no_data"])
        assert msg["p"] is None
        assert msg["chg_pct"] is None
        assert msg["vol"] is None
        assert msg["ref"] is None
        assert msg["upper"] is None
        assert msg["lower"] is None
        await engine.close()


class TestReviewFixes:
    """Phase 4 round 1 accepted P1 的 regression lock(CR2~CR5)。"""

    async def test_worker_survives_unexpected_backfill_error(self) -> None:
        # CR4:非 ConnectionError 例外不得殺死 worker
        engine, src = await _make()
        stream = engine.stream()
        src.backfill_error = ValueError("truncated payload")
        await engine.set_main("2330")
        await _drain(engine)
        # 使用者看得到的那一半:畫面「回補中…」的唯一來源是 WS status 訊息(M3 之後
        # snapshot 不再帶),例外路徑沒補推 backfilling=None 的話,徽章永遠掛著而內部態
        # 早就清了(TQ-4)。斷言必須落在**第二次回補之前** —— 後面那次成功回補自己也會
        # 推一則 None,收到最後才驗會變成無論例外路徑推不推都綠。
        got: list[dict] = []
        try:
            while True:
                got.append(await asyncio.wait_for(anext(stream), timeout=0.3))
        except (TimeoutError, asyncio.TimeoutError):
            pass
        statuses = [m for m in got if m["type"] == "status"]
        assert statuses, "回補期間必有 status 訊息"
        assert statuses[-1]["backfilling"] is None
        src.backfill_error = None
        await engine.set_main("5483")
        await _drain(engine)
        assert "5483" in src.backfills  # worker 仍活著
        # backfilling 已退出 REST snapshot(M3),改讀 engine 內部態 —— 鎖的行為
        # (例外後 `_backfilling` 不會永久卡住)不變
        assert engine._backfilling is None  # 清乾淨
        await engine.close()

    async def test_weekend_makeup_day_fast_path_rollover(self) -> None:
        # CR5:無 checkpoint(週六補市)下,新日 tick 直接觸發兩段式
        engine, src = await _make()
        await engine.set_main("2330")
        assert src.on_message is not None
        src.on_message(_quote(cum=12000))
        await _drain(engine)
        src.on_message(_quote(cum=50, date="20260722"))
        await _drain(engine)
        snap = engine.snapshot("2330")
        assert snap["last"] is not None
        assert snap["last"]["cum_vol"] == 50  # 不被 stale-drop
        assert "2026-07-22" in src.trade_dates  # stage1 快路徑跑過(換日窗)

    async def test_rollover_stage1_does_not_block_event_loop(self) -> None:
        # CR3:重掛阻塞時 stage1 呼叫必須立即返回(sync 呼叫會在此 deadlock)
        engine, src = await _make()
        await engine.set_main("2330")
        await _drain(engine)
        src.subscribe_gate = threading.Event()  # 未 set → subscribe 阻塞
        t0 = asyncio.get_running_loop().time()
        engine.rollover_stage1("2026-07-22")  # 同步重掛會在此吃掉 subscribe 阻塞時間
        assert asyncio.get_running_loop().time() - t0 < 0.5  # 必須立即返回
        assert "2026-07-22" in src.trade_dates  # 同步部分已生效
        src.subscribe_gate.set()
        await _drain(engine)
        assert src.subscribed.count("2330") >= 2  # 背景重掛完成

    async def test_close_cancels_pending_resubscribe_task(self) -> None:
        """M2:關機要取消 in-flight 的重掛 task(否則 loop 收掉時它還掛著)。

        pending 的製造刻意用 `_pool_lock` 而非 `subscribe_gate`:後者會讓 task 已經
        進到 `to_thread` 的阻塞裡,cancel 等不回來 → 測試自己死鎖。卡在
        `async with self._pool_lock` 時取消才乾淨。
        """
        engine, _ = await _make()
        await engine.set_main("2330")
        await _drain(engine)
        await engine._pool_lock.acquire()
        n_before = len(engine._tasks)
        engine.rollover_stage1("2026-07-22")
        # 從 `_tasks` 取而不是 `asyncio.all_tasks()` 差集:差集抓到的是「這一刻多出來的
        # 任何 task」,重掛 task 有沒有進 `_tasks`(唯一持有點 = 唯一取消點,漏掛就會
        # 被中途 GC)完全沒被鎖住 —— 這樣取才順帶把那條行為變成顯式斷言(TQ-3)
        assert len(engine._tasks) == n_before + 1
        resub = engine._tasks[-1]
        await asyncio.sleep(0.05)  # 讓它跑到 pool_lock 卡住
        assert not resub.done()
        await engine.close()
        assert resub.cancelled()
        engine._pool_lock.release()

    async def test_close_completes_even_if_a_task_died_with_exception(self) -> None:
        """TQ-1 + FC-1:背景 task 帶非 Cancelled 例外結束時,close() 仍要跑完並關掉 source。

        `for task: await task` 只吞 `CancelledError` → 已死 task 的例外在那一行**重拋**,
        close 就地中斷:後面的 task 不再被 await、`self._source.close()` 永不執行
        (ZMQ session 洩漏),而關機路徑上沒有人會再呼叫第二次。重掛 task 是最現實的
        來源 —— `_resubscribe_all` 只吞 ConnectionError,壞電文那類例外一路穿出去。
        """
        engine, src = await _make()
        await engine.set_main("2330")
        await _drain(engine)
        src.subscribe_error = ValueError("wrapper 內部型別錯")
        engine.rollover_stage1("2026-07-22")
        await _drain(engine)
        assert any(
            t.done() and not t.cancelled() and t.exception() is not None for t in engine._tasks
        ), "前提:確實有 task 帶例外結束(否則這條測不到東西)"
        await asyncio.wait_for(engine.close(), timeout=2)
        assert src.closed is True, "source 必須被關掉"

    async def test_concurrent_watchlist_removal_keeps_main_subscribed(self) -> None:
        # CR2:並發「移出自選 + 設為主圖」不得把主圖檔退訂 / 弄丟 refs
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        await asyncio.gather(engine.set_main("2330"), engine.set_watchlist([]))
        await _drain(engine)
        assert "2330" not in src.unsubscribed  # main owner 仍持有
        # refs 未損毀:再次移除 main(切走)才真退訂
        await engine.set_main("2317")
        assert "2330" in src.unsubscribed
        await engine.close()


class TestBarsRangeStatus:
    """N-2:TC4 斷線在 engine 層被吞成空,前端只看得到「無 K 線資料」。

    降級空的行為照舊(K 線可降級,不 raise),但**原因要跟著空一起送出去**
    —— 那正是使用者五秒內要答出「壞了 vs 沒資料」的唯一依據。
    """

    async def test_connection_error_reports_disconnected(self) -> None:
        engine, src = await _make()

        def boom(
            code: str, tf: str, start_date: str, end_date: str
        ) -> tuple[list[Bar], BarsStatus]:
            raise ConnectionError("tc4 down")

        src.fetch_bars_range = boom  # type: ignore[method-assign]
        assert await engine.bars_range("2330", "D", "2026-01-01", "2026-07-28") == (
            [],
            "disconnected",
        )
        await engine.close()

    async def test_source_status_passed_through(self) -> None:
        engine, src = await _make()

        def slow(
            code: str, tf: str, start_date: str, end_date: str
        ) -> tuple[list[Bar], BarsStatus]:
            return [], "timeout"

        src.fetch_bars_range = slow  # type: ignore[method-assign]
        assert await engine.bars_range("2330", "1", "2026-07-28", "2026-07-28") == ([], "timeout")
        await engine.close()


class TestStkfut:
    async def test_stkfut_subscribed_with_future_prefix(self) -> None:
        engine, src = await _make()
        await engine.set_main("2330")
        assert "F:CDF" in src.subscribed  # 期貨鍵,不是股號鍵(real-env 修正)
        await engine.set_main("2317")  # 換主圖 → 舊 stkfut 退訂
        assert "F:CDF" in src.unsubscribed
        await engine.close()

    async def test_stkfut_quote_published_with_basis(self) -> None:
        engine, src = await _make()
        await engine.set_main("2330")  # 對映表有 2330 → 加訂 CDF
        assert src.on_message is not None
        src.on_message(_quote(cum=1))  # 現股價 2380
        await _drain(engine)
        stream = engine.stream()
        src.on_message(_quote(
            code="CDF", symbol="TC.F.TWF.CDF.HOT", price="2398", cum=100,
        ) | {"SecurityName": "台積電(2330)"})
        await _drain(engine)
        got: list[dict] = []
        try:
            while True:
                got.append(await asyncio.wait_for(anext(stream), timeout=0.3))
        except (TimeoutError, asyncio.TimeoutError):
            pass
        fut = next(m for m in got if m["type"] == "stkfut")
        assert fut["code"] == "2330"
        assert fut["p"] == 2_398_000
        assert fut["basis"] == 18_000
        await engine.close()

    async def test_security_name_mismatch_warns(self, caplog) -> None:
        engine, src = await _make()
        await engine.set_main("2330")
        assert src.on_message is not None
        with caplog.at_level(logging.WARNING):
            src.on_message(_quote(
                code="CDF", symbol="TC.F.TWF.CDF.HOT", price="2398", cum=100,
            ) | {"SecurityName": "聯發科(2454)"})
            await _drain(engine)
        assert any("stkfut" in r.message for r in caplog.records)
        await engine.close()


class FakeHub:
    """SignalSink stub:只記錄呼叫序列(順序本身是被鎖的行為)。"""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def on_tick(self, code: str, tick, state) -> None:
        self.calls.append(("tick", code, tick.cum_vol))

    def on_book(self, code: str, state) -> None:
        self.calls.append(("book", code))

    def on_rollover_pending(self, new_date: str) -> None:
        self.calls.append(("pending", new_date))

    def on_rollover(self) -> None:
        self.calls.append(("rollover",))

    def on_watchlist(self, codes: list[str]) -> None:
        self.calls.append(("watchlist", list(codes)))

    def kinds(self, kind: str) -> list[tuple]:
        return [c for c in self.calls if c[0] == kind]


class _RetrySource(FakeSource):
    """記錄每次 `subscribe_symbol` 呼叫(含失敗)—— `subscribed` 只記成功,
    測不到「重試了幾次」也測不到「已移除的檔還在被重試」。"""

    def __init__(self, fail_delay: float = 0.0) -> None:
        super().__init__()
        self.attempts: list[str] = []
        self._fail_delay = fail_delay

    def subscribe_symbol(self, code: str) -> None:
        self.attempts.append(code)
        if self._fail_delay and code in self.fail_subscribe:
            # TC4 斷線時單檔 SUBQUOTE 要等 `_REQ_TIMEOUT_MS`(10s)才失敗 —— 慢失敗
            # 才是鎖飢餓的真實形狀,瞬間 raise 測不到持鎖時間
            time.sleep(self._fail_delay)
        super().subscribe_symbol(code)


# 顯式對映表:不吃磁碟上的 `stkfut_map.json`(內容會隨期交所頁面重抓而變)
_STKFUT_MAP = {"2330": {"prod": "CDF", "name": "台積電"}}


async def _make_retry(
    interval: float = 0.01, source: _RetrySource | None = None
) -> tuple[StockEngine, _RetrySource]:
    src = source if source is not None else _RetrySource()
    engine = StockEngine(
        src,
        trade_date="2026-07-21",
        throttle_secs=60,  # 排除 1s flush 對 watchlist_quote 計數的貢獻
        checkpoint=False,
        stkfut_map=_STKFUT_MAP,
        resub_interval_secs=interval,
    )
    await engine.start()
    return engine, src


async def _wait_until(pred: Callable[[], bool], timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if pred():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("條件逾時未成立")


# 恆失敗的自選檔:重試輪的**可觀察計數器**。用牆鐘 sleep 換輪數在 Windows 上是假的
# (timer 解析度 15.6ms,`sleep(0.05)` 對 interval=0.01 實際只跑 ~3 輪),否定斷言的
# 強度會比註解寫的低一半以上(review W-4)。
_SENTINEL = "8888"


async def _wait_rounds(src: _RetrySource, rounds: int, timeout: float = 2.0) -> None:
    """等重試迴圈確實跑滿 `rounds` 輪(以哨兵檔被重試的次數計)。"""
    base = src.attempts.count(_SENTINEL)
    await _wait_until(lambda: src.attempts.count(_SENTINEL) >= base + rounds, timeout=timeout)


async def _collect(stream) -> list[dict]:
    got: list[dict] = []
    try:
        while True:
            got.append(await asyncio.wait_for(anext(stream), timeout=0.3))
    except (TimeoutError, asyncio.TimeoutError):
        pass
    return got


class TestWatchlistRetry:
    """自選訂閱失敗的背景重試(mod/subscribe-retry-recovery SC-2)。

    `_acquire` 真訂失敗回滾出 `_refs` → rollover 的 `_resubscribe_all` 接不到、
    flush 無 state 可推 → 該檔畫面永遠 `-`,唯一復原是使用者自己重送同一份名單。
    """

    async def test_failed_code_retried_and_seeded(self) -> None:
        engine, src = await _make_retry()
        stream = engine.stream()  # 名單仍空 → 無種子,之後收到的都是新產出
        src.fail_subscribe.add("9999")
        await engine.set_watchlist(["9999"])
        assert "9999" not in src.subscribed
        src.fail_subscribe.discard("9999")
        await _wait_until(lambda: "9999" in src.subscribed)
        await _drain(engine)
        got = await _collect(stream)
        quotes = [m for m in got if m["type"] == "watchlist_quote" and m["code"] == "9999"]
        # 一則來自 set_watchlist 的 added 種子,一則來自重試成功(對齊 added 種子語意);
        # 沒有後者的話這一檔在盤後完全沒有生產點
        assert len(quotes) == 2
        assert "watchlist" in engine._refs["9999"]
        await engine.close()

    async def test_removed_code_is_not_retried(self) -> None:
        engine, src = await _make_retry()
        src.fail_subscribe.update({"9999", _SENTINEL})
        await engine.set_watchlist(["9999", _SENTINEL])
        await engine.set_watchlist([_SENTINEL])  # 使用者移除 9999 → 判準應自然失效
        n = src.attempts.count("9999")
        await _wait_rounds(src, 5)
        assert src.attempts.count("9999") == n
        assert "9999" not in src.subscribed
        await engine.close()

    async def test_manual_resend_repair_does_not_double_subscribe(self) -> None:
        # 白名單 4:回滾語意不變 —— 現況唯一的手動復原路(重送同名單)仍要能修,
        # 且修好之後重試輪不得再真訂一次
        engine, src = await _make_retry()
        src.fail_subscribe.update({"9999", _SENTINEL})
        await engine.set_watchlist(["9999", _SENTINEL])
        src.fail_subscribe.discard("9999")
        await engine.set_watchlist(["9999", _SENTINEL])  # 重送 → added 以 refs 實況為準
        await _wait_rounds(src, 5)
        assert src.subscribed.count("9999") == 1
        await engine.close()

    async def test_all_success_never_resubscribes(self) -> None:
        """SC-4(stock 側實鎖):判準寫錯最典型的失效 = 每輪重複真訂。"""
        engine, src = await _make_retry()
        src.fail_subscribe.add(_SENTINEL)  # 只為了數輪數,順帶證明壞檔不牽連好檔
        await engine.set_watchlist(["2330", "5483", _SENTINEL])
        await engine.set_main("2330")
        await _wait_rounds(src, 5)
        for code in ("2330", "5483", "F:CDF"):
            assert src.subscribed.count(code) == 1, code
        await engine.close()

    async def test_rollover_resubscribe_failure_retried_then_pruned(self) -> None:
        """P1-1:`_resubscribe_all` 的失敗不動 `_refs` → 只看 owner 的對帳判準接不到。"""
        engine, src = await _make_retry()
        await engine.set_main("2330")
        src.fail_subscribe.add("2330")
        engine.rollover_stage1("2026-07-22")
        await _wait_until(lambda: "2330" in engine._failed_resubs)
        src.fail_subscribe.discard("2330")
        await _wait_until(lambda: "2330" not in engine._failed_resubs)
        assert src.subscribed.count("2330") >= 2  # 重掛真的發出去了
        await engine.close()

    async def test_failed_resub_pruned_when_code_unsubscribed(self) -> None:
        engine, src = await _make_retry()
        src.fail_subscribe.add(_SENTINEL)
        await engine.set_watchlist([_SENTINEL])  # 輪數哨兵(段 2 恆失敗)
        await engine.set_main("2330")
        src.fail_subscribe.add("2330")
        engine.rollover_stage1("2026-07-22")
        await _wait_until(lambda: "2330" in engine._failed_resubs)
        await engine.set_main("5483")  # 2330 last owner 退 → 已不在 _refs
        await _wait_until(lambda: not engine._failed_resubs)
        n = src.attempts.count("2330")
        await _wait_rounds(src, 5)
        assert src.attempts.count("2330") == n  # 已退訂的檔不再被重試
        await engine.close()

    async def test_head_of_line_failure_does_not_starve_same_section(self) -> None:
        """C-1:段內迭代順序固定 + 首個 ConnectionError break = 排最前的恆失敗檔
        永久餓死同段後面所有檔(段級 break 只解跨段餓死,段內的原封不動)。"""
        engine, src = await _make_retry()
        src.fail_subscribe.update({"9998", "9999"})
        await engine.set_watchlist(["9998", "9999"])  # 9998 排在前面且恆失敗
        src.fail_subscribe.discard("9999")  # 只修好排在後面的那檔
        await _wait_until(lambda: "9999" in src.subscribed)
        await engine.close()

    async def test_head_of_line_failure_does_not_starve_failed_resubs(self) -> None:
        """C-1 的段 3 對稱情境(pending_resubs 是 sorted,順序同樣固定)。"""
        engine, src = await _make_retry()
        await engine.set_watchlist(["9997", "9998"])  # 先真訂上 → owner 在 _refs
        src.fail_subscribe.update({"9997", "9998"})
        engine.rollover_stage1("2026-07-22")  # 全量重掛兩檔皆失敗
        await _wait_until(lambda: engine._failed_resubs == {"9997", "9998"})
        src.fail_subscribe.discard("9998")  # 只修 sorted 順序在後的那檔
        await _wait_until(lambda: "9998" not in engine._failed_resubs)
        await engine.close()

    async def test_failed_resub_merge_waits_for_pool_lock(self) -> None:
        """C-2:`_failed_resubs` 一律鎖內存取。

        合併若不持鎖,會在段 3 的 `await` 窗內插進來 → 隨後那句成功 discard 把它抹掉,
        該檔從此不再重掛。失效樣態:rollover 後那一檔整天零推播,而 log 只有換日當下
        一行 warning。
        """
        src = _RetrySource(fail_delay=0.3)
        engine, src = await _make_retry(interval=10.0, source=src)  # 重試迴圈不介入
        await engine.set_main("2330")
        src.fail_subscribe.add("2330")
        engine.rollover_stage1("2026-07-22")
        await _wait_until(lambda: src.attempts.count("2330") >= 2)  # 重掛已進到慢失敗窗
        async with engine._pool_lock:
            await asyncio.sleep(0.4)  # 慢失敗早已結束;合併必須還卡在鎖外
            assert engine._failed_resubs == set()
        await _wait_until(lambda: "2330" in engine._failed_resubs)  # 放鎖後才進帳
        await engine.close()

    async def test_close_stops_retry_loop(self) -> None:
        """W-2:關機後重試不再新排(仿 corr test_close_stops_retry_loop)。"""
        engine, src = await _make_retry()
        src.fail_subscribe.add("9999")
        await engine.set_watchlist(["9999"])
        await _wait_until(lambda: src.attempts.count("9999") > 4)  # 迴圈確實在跑
        await engine.close()
        n = len(src.attempts)
        # close 後沒有哨兵可數(整條迴圈就是被停掉的那個東西),誠實記帳:0.2s 遠超 interval
        await asyncio.sleep(0.2)
        assert len(src.attempts) <= n + 1  # 至多一個 in-flight thread,不再新排


class TestStkfutRetry:
    """個股期腿訂閱失敗的背景重試(SC-3)。

    `_acquire_stkfut` 只在 `set_main` 呼叫,而 `set_main` 開頭 `old == code → return`
    → 同檔重掛被擋,現況唯一復原是切走再切回。
    """

    async def test_failed_leg_retried_until_success(self) -> None:
        engine, src = await _make_retry()
        src.fail_subscribe.add("F:CDF")
        await engine.set_main("2330")
        assert "F:CDF" not in src.subscribed
        src.fail_subscribe.discard("F:CDF")
        await _wait_until(lambda: "F:CDF" in src.subscribed)
        assert engine._refs["F:CDF"] == {"stkfut:2330"}
        await engine.close()

    async def test_main_switched_away_stops_retry_without_leaking_owner(self) -> None:
        engine, src = await _make_retry()
        src.fail_subscribe.update({"F:CDF", _SENTINEL})
        await engine.set_watchlist([_SENTINEL])  # 輪數哨兵
        await engine.set_main("2330")
        await engine.set_main("5483")  # 對映表無此檔 → 不該再為 2330 掛腿
        src.fail_subscribe.discard("F:CDF")
        await _wait_rounds(src, 5)
        assert "F:CDF" not in src.subscribed
        assert all("stkfut:2330" not in owners for owners in engine._refs.values())
        await engine.close()


class TestRetryLoopStarvation:
    async def test_slow_failing_subscribes_do_not_block_set_main(self) -> None:
        """P0-1:TC4 斷線時單檔 SUBQUOTE 要 10s 才失敗,整輪一鎖會讓 `_pool_lock`
        佔用率趨近 100% → set_main / PUT watchlist 卡死。持鎖上界必須與 N 檔無關。"""
        src = _RetrySource(fail_delay=0.05)
        engine, _ = await _make_retry(source=src)
        codes = [str(9000 + i) for i in range(12)]
        src.fail_subscribe.update(codes)
        await engine.set_watchlist(codes)
        await _wait_until(lambda: len(src.attempts) > len(codes))  # 重試迴圈確實已在跑
        t0 = asyncio.get_running_loop().time()
        await engine.set_main("2330")
        elapsed = asyncio.get_running_loop().time() - t0
        # 整輪一鎖 = 12 × 0.05 = 0.6s;段級早停 = 至多一次失敗 subscribe 的持鎖
        assert elapsed < 0.3, elapsed
        await engine.close()

    async def test_permanently_failing_code_does_not_starve_other_sections(self) -> None:
        """P1-3:`tc4._resub` 對單一壞碼可穩定 raise(與連線健康無關),round 級早停
        會讓一檔壞碼永久餓死 failed_resubs 與 stkfut 兩段。"""
        engine, src = await _make_retry()
        src.fail_subscribe.update({"9999", "F:CDF"})
        await engine.set_watchlist(["9999"])  # 段 2 恆失敗
        await engine.set_main("2330")  # 段 4 的 stkfut 腿失敗
        src.fail_subscribe.add("2330")
        engine.rollover_stage1("2026-07-22")  # 段 3 的 failed_resubs
        await _wait_until(lambda: "2330" in engine._failed_resubs)
        src.fail_subscribe.difference_update({"2330", "F:CDF"})  # 9999 仍恆失敗
        await _wait_until(
            lambda: "F:CDF" in src.subscribed and "2330" not in engine._failed_resubs
        )
        assert "9999" not in src.subscribed  # 前提:段 2 確實每輪都在失敗
        await engine.close()


class TestSignalHubHooks:
    """SC-5 / SC-6:訊號掛點只長在 live 路徑上,回補重放與換日 pending 期間不得誤觸。"""

    async def test_live_tick_notifies_hub_including_non_main_watchlist_code(self) -> None:
        # 掛點不限主圖:自選檔即使沒開主圖也要評估(membership gate 在 hub 內)
        engine, src = await _make()
        hub = FakeHub()
        engine.attach_signal_hub(hub)
        await engine.set_watchlist(["2330"])
        assert engine._main != "2330"
        assert src.on_message is not None
        src.on_message(_quote(cum=1))
        await _drain(engine)
        assert hub.kinds("tick") == [("tick", "2330", 1)]
        assert hub.kinds("book") == [("book", "2330")]
        await engine.close()

    async def test_backfill_replay_never_reaches_hub(self) -> None:
        """SC-5:`apply_backfill` 路徑零接觸 —— 回補是重放歷史,發訊號等於對著
        已成過去的價位重新示警。結構隔離(掛點只在 `_handle_quote`)+ 本測試鎖死。"""
        engine, src = await _make()
        hub = FakeHub()
        engine.attach_signal_hub(hub)
        from copycat.live.stock_models import StockTick

        src.backfill_result = [
            StockTick(code="2330", price_milli=2_380_000, qty=5, cum_vol=5,
                      time="09:01:00.000", trade_date="2026-07-21", side="outer",
                      is_trial=False),
            StockTick(code="2330", price_milli=2_400_000, qty=3, cum_vol=8,
                      time="09:02:00.000", trade_date="2026-07-21", side="outer",
                      is_trial=False),
        ]
        await engine.set_main("2330")
        await _drain(engine)
        # 前提:回補確實跑完並落地(否則這條測不到東西)
        assert len(engine.snapshot("2330")["ticks"]) == 2
        assert hub.calls == []
        await engine.close()

    async def test_trial_quote_skips_on_tick_but_still_on_book(self) -> None:
        """SC-6 後半:試撮期(13:25–13:30)`ingest` 回 False → 不評估成交路;
        但簿仍在更新(鎖板打開的簿路要抓得到),`on_book` 照常。"""
        engine, src = await _make()
        hub = FakeHub()
        engine.attach_signal_hub(hub)
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        # PreciseTime 05:26:00 UTC → 台北 13:26:00 = 試撮窗
        src.on_message(_quote(cum=1) | {"PreciseTime": "52600000000", "FilledTime": "52600"})
        await _drain(engine)
        assert hub.kinds("tick") == []
        assert hub.kinds("book") == [("book", "2330")]
        await engine.close()

    async def test_on_book_skipped_while_rollover_pending(self) -> None:
        """stage1 已觸發、stage2 未完成時跳過簿路:否則跨日後第一則簿更新會拿今日簿
        對照昨日 latch 誤發 `limit_open`(design R2-2)。"""
        engine, src = await _make()
        hub = FakeHub()
        engine.attach_signal_hub(hub)
        await engine.set_watchlist(["2330"])
        engine.rollover_stage1("2026-07-22")
        assert src.on_message is not None
        src.on_message(_quote(cum=1))  # 仍是舊日 tick → 不進 stage2,pending 未解
        await _drain(engine)
        assert hub.kinds("book") == []
        await engine.close()

    async def test_rollover_two_stages_notify_in_order(self) -> None:
        engine, src = await _make()
        hub = FakeHub()
        engine.attach_signal_hub(hub)
        await engine.set_main("2330")
        assert src.on_message is not None
        src.on_message(_quote(cum=12000))
        await _drain(engine)
        engine.rollover_stage1("2026-07-22")
        src.on_message(_quote(cum=50, date="20260722"))
        await _drain(engine)
        stages = [c for c in hub.calls if c[0] in ("pending", "rollover")]
        assert stages == [("pending", "2026-07-22"), ("rollover",)]
        # stage2 之後 pending 解除 → 簿路恢復;hub 的 trade_date_fn 讀得到新日
        assert engine.trade_date == "2026-07-22"
        assert hub.kinds("book")[-1] == ("book", "2330")
        await engine.close()

    async def test_set_watchlist_notifies_hub(self) -> None:
        engine, _src = await _make()
        hub = FakeHub()
        engine.attach_signal_hub(hub)
        await engine.set_watchlist(["2330", "5483"])
        await engine.set_watchlist(["5483"])
        assert hub.kinds("watchlist") == [
            ("watchlist", ["2330", "5483"]),
            ("watchlist", ["5483"]),
        ]
        await engine.close()
