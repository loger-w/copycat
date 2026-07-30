from __future__ import annotations

import asyncio
import logging
import threading
from typing import Callable

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
        self.subscribe_gate: threading.Event | None = None
        self.backfill_gate: threading.Event | None = None
        self.backfill_result: list = []
        self.backfill_error: Exception | None = None
        self.on_message: Callable[[dict], None] | None = None
        self.on_no_data: Callable[[str], None] | None = None
        self.on_reconnect: Callable[[], None] | None = None
        self.on_subscribe: Callable[[str], None] | None = None

    def subscribe_symbol(self, code: str) -> None:
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
        return list(self.backfill_result)

    def fetch_bars_range(
        self, code: str, tf: str, start_date: str, end_date: str
    ) -> list:
        """Protocol 新增方法(change-spec R2-1);既有斷言不依賴,回空即可。"""
        return []

    def fetch_daily_bars(self, code: str, n: int = 25) -> list:
        return []

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        self.on_message = cb

    def set_on_no_data(self, cb: Callable[[str], None]) -> None:
        self.on_no_data = cb

    def set_trade_date(self, trade_date: str) -> None:
        self.trade_dates.append(trade_date)

    def close(self) -> None:
        pass


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


class TestBackfillGuard:
    async def test_stale_backfill_not_applied_after_main_switch(self) -> None:
        engine, src = await _make()
        src.backfill_gate = threading.Event()
        from copycat.live.stock_models import StockTick

        src.backfill_result = [
            StockTick(code="2330", price_milli=2_380_000, qty=5, cum_vol=5,
                      time="09:01:00.000", trade_date="2026-07-21", side="outer",
                      buy_sell_flag=None, is_trial=False)
        ]
        await engine.set_main("2330")
        await engine.set_main("5483")  # A 回補中切 B
        src.backfill_gate.set()
        await _drain(engine)
        assert engine.snapshot("2330")["ticks"] == []  # A 結果不落地
        await engine.close()

    async def test_rollover_generation_voids_inflight_backfill(self) -> None:
        engine, src = await _make()
        src.backfill_gate = threading.Event()
        from copycat.live.stock_models import StockTick

        src.backfill_result = [
            StockTick(code="2330", price_milli=2_380_000, qty=12000, cum_vol=12000,
                      time="09:01:00.000", trade_date="2026-07-21", side="outer",
                      buy_sell_flag=None, is_trial=False)
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
        assert snap["cum_outer"] == 1
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


class TestReviewFixes:
    """Phase 4 round 1 accepted P1 的 regression lock(CR2~CR5)。"""

    async def test_worker_survives_unexpected_backfill_error(self) -> None:
        # CR4:非 ConnectionError 例外不得殺死 worker
        engine, src = await _make()
        src.backfill_error = ValueError("truncated payload")
        await engine.set_main("2330")
        await _drain(engine)
        src.backfill_error = None
        await engine.set_main("5483")
        await _drain(engine)
        assert "5483" in src.backfills  # worker 仍活著
        assert engine.snapshot("5483")["backfilling"] is None  # 清乾淨

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
