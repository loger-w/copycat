from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Callable

import pytest

from copycat.live.stock_source import Bar, BarsStatus, stock_symbol
from copycat.server import stock_engine as stock_engine_mod
from copycat.server.stock_engine import StockEngine


def _quote(
    code: str = "2330",
    *,
    cum: int = 1,
    price: str = "2380",
    qty: str = "1",
    date: str = "20260721",
    symbol: str | None = None,
    precise: str = "25751000000",
) -> dict:
    """`precise` = TC4 的 UTC PreciseTime(預設 02:57:51 = 台北 10:57:51,日盤正中)。

    參數化是 SC-3 需要的:試撮窗與期貨日盤窗的行為只有在**特定時刻**才分得出來
    (08:50 / 13:27 / 15:30 / 次日 01:00),寫死一個時刻就只驗得到「沒爆」。
    """
    return {
        "Symbol": symbol or f"TC.S.TWS.{code}",
        "Security": code,
        "SecurityName": "台積電",
        "TradingPrice": price,
        "TradeQuantity": qty,
        "TradeVolume": str(cum),
        "TradeDate": date,
        "FilledTime": precise.zfill(12)[:6],  # 同一時刻的 HHMMSS 形(UTC)
        "PreciseTime": precise,
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

    def symbol_of(self, key: str) -> str:
        """instrument key → TC4 symbol。**一律委派 `stock_symbol`**(R1):fake 自寫
        第二份對映時,engine 的路由表鍵與真實 symbol 會在測試裡永遠一致、在 prod
        永遠對不上 —— 而那條路的失效是「訂閱成功但零推播」。"""
        return stock_symbol(key)

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
        """R4 的另一半:跨日後「今日已回補」必須全部作廢(記帳是日別語意)。

        **setup 先餵一則當日 REALTIME 把 meta 補齊**(斷言不變):A6-5 之後「漲跌停值
        變化」對已回補過的成員也會重入列,而 meta 為 None 時**任何**一則報價都算值變
        —— 觸發 stage2 的那一則會順手排一筆合法的新日回補,`_backfilled` 就在同一輪
        drain 內被正當地重新填上,這條測試要釘的「清空」反而被那件事蓋掉。
        先讓 meta 有值(且新日報價的漲跌停與之相同)就沒有這個混淆源。
        """
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        src.on_message(_quote(cum=1))  # meta 到位;此時尚未回補過 → 不觸發重入列
        await _drain(engine)
        engine._backfill_jobs.put_nowait(("2330", engine._generation))
        await _drain(engine)
        assert "2330" in engine._backfilled
        engine.rollover_stage1("2026-07-22")
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

    async def test_stage2_survives_states_mutation_during_reset_iteration(self) -> None:
        """E-5:stage2 的 reset 迴圈要先對 `_states` 取快照。

        `_acquire` 在 executor thread 對 `_states` setdefault 新鍵(自選新增 / 重試輪 /
        stkfut 腿隨時可能發生),而 stage2 在 loop 上直接迭代 `.values()` —— 撞上就是
        RuntimeError:迴圈**之後**的每一步(記帳清空、主圖重回補、hub 的 on_rollover)
        全部不跑,而 `_pending_date` 已在迴圈**之前**清掉 → 這一天不會再有第二次 stage2。
        沒 reset 到的 state 整天 ingest=False、記帳整天沿用昨日,畫面只是「圖不動」。
        `quotes()` 的同款 hazard 已由 R16 防住,這裡是漏網的第二處。
        """
        from copycat.live.stock_state import StockDayState

        engine, src = await _make()
        await engine.set_watchlist(["2330", "5483"])
        assert src.on_message is not None
        src.on_message(_quote(cum=1))
        src.on_message(_quote(code="5483", cum=1))
        await _drain(engine)
        engine._backfill_jobs.put_nowait(("2330", engine._generation))
        engine._backfill_jobs.put_nowait(("5483", engine._generation))
        await _drain(engine)
        assert engine._backfilled == {"2330", "5483"}  # 前提:記帳確實有東西可清

        state = engine._states["2330"]  # 迭代的第一個 → 之後的每一步都在它後面
        orig_reset = state.reset

        def _mutating_reset() -> None:
            engine._states.setdefault("F:XXF", StockDayState())  # executor thread 的新訂閱
            orig_reset()

        state.reset = _mutating_reset  # type: ignore[method-assign]

        engine.rollover_stage1("2026-07-22")
        src.on_message(_quote(cum=50, date="20260722"))
        await _drain(engine)

        assert engine._backfilled == set()  # 迴圈之後的步驟確實跑完
        assert engine.snapshot("5483")["last"] is None  # 迴圈內的每個 state 都 reset 到
        assert engine.trade_date == "2026-07-22"
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


async def _make_mapped() -> tuple[StockEngine, FakeSource]:
    """顯式 stkfut 對映 + 不介入的重試迴圈:群組資料面的測試只關心 `_states` 的內容。"""
    src = FakeSource()
    engine = StockEngine(
        src,
        trade_date="2026-07-21",
        throttle_secs=60,
        checkpoint=False,
        stkfut_map=_STKFUT_MAP,
        resub_interval_secs=60,
    )
    await engine.start()
    return engine, src


class TestQuotes:
    """SC-2:同群摘要要印成員的**名稱**與漲跌幅,而名稱只有 `state.meta.name` 拿得到。"""

    async def test_quotes_returns_name_and_chg_pct(self) -> None:
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        src.on_message(_quote(cum=7, price="2400"))
        await _drain(engine)
        assert engine.quotes() == {"2330": ("台積電", 3.45)}
        await engine.close()

    async def test_quotes_excludes_futures_pseudo_keys(self) -> None:
        """`F:` 是訂閱池的期貨偽鍵,不是股號 —— 混進摘要會印出「F:CDF」這種東西。

        走 `_watchlist` 而不是 `_states` 天然排除(`_states` 兩種鍵都有)。
        """
        engine, _src = await _make_mapped()
        await engine.set_watchlist(["2330"])
        await engine.set_main("2330")  # → 加訂 F:CDF,`_states` 因此多一個偽鍵
        await _drain(engine)
        assert "F:CDF" in engine._states  # 前提:偽鍵確實在 `_states` 裡
        assert set(engine.quotes()) == {"2330"}
        await engine.close()

    async def test_quotes_name_empty_and_chg_none_without_meta(self) -> None:
        """盤前 / 冷啟動尚無 REALTIME:名稱回空字串、漲跌幅 None(摘要側各自降級顯示),
        **不得**整檔缺席 —— 缺席會讓「群組有幾檔」跟著波動。"""
        engine, _src = await _make()
        await engine.set_watchlist(["2330"])
        assert engine.quotes() == {"2330": ("", None)}
        await engine.close()

    async def test_quotes_survives_states_mutation_during_iteration(self, monkeypatch) -> None:
        """R16:名單以 local 參照取一次(該欄位以**整份重新指派**更新),且不對 `_states`
        做 dict 迭代 —— 迭代中新訂閱寫進 `_states` 會炸 RuntimeError(size changed),
        而 quotes 是在 Discord worker 呼叫的,盤中隨時可能與 `set_watchlist` 交錯。
        """
        from copycat.live.stock_state import StockDayState

        engine, _src = await _make()
        await engine.set_watchlist(["2330", "5483"])
        orig = engine._quote_payload

        def mutating(code: str) -> dict:
            engine._states[f"X{code}"] = StockDayState()  # 迭代中新訂閱建 state
            engine._watchlist = ["9999"]  # 使用者同時換了名單
            return orig(code)

        monkeypatch.setattr(engine, "_quote_payload", mutating)
        got = engine.quotes()
        assert set(got) == {"2330", "5483"}  # 一致快照:不炸、不漏鍵、不摻新名單
        await engine.close()


class TestGroupSnapshot:
    """SC-4:群組檢視的唯讀 batch。**不 set_main、不改訂閱池**(`/api/stock/state/{code}`
    會 set_main,群組每分鐘 30 次會把主圖搶走令主圖凍結 → 那條路不可重用)。"""

    async def test_payload_is_the_lightweight_three_keys_plus_backfilling(self) -> None:
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        src.on_message(_quote(cum=7, price="2380"))
        await _drain(engine)
        snap = engine.group_snapshot(["2330"])["2330"]
        assert set(snap) == {"minutes", "meta", "no_data", "backfilling"}
        # R2:ticks 是數千筆,30 檔一起送等於把 batch 端點變成頻寬炸彈
        assert "ticks" not in snap
        # 鍵名沿 `StockDayState.snapshot()` 的單一定義:直接丟 dataclass 會讓前端
        # `meta.ref` undefined → hasRef=false → 紅綠面積靜默消失
        assert snap["meta"] == {
            "name": "台積電",
            "ref": 2_320_000,
            "upper": 2_550_000,
            "lower": 2_090_000,
            "y_vol": 100,
        }
        assert snap["minutes"]["657"]["c"] == 2_380_000
        assert snap["no_data"] is False
        await engine.close()

    async def test_unknown_code_is_no_data_and_never_enqueued(self) -> None:
        """R9:`no_data` 推導式 = `code in _no_data` **或** 未訂閱。

        刻意與 `snapshot()` / `engine` 其他地方相反 —— `StockDayState.snapshot()` 根本
        沒這個鍵,而 `engine.snapshot()` 對未知 code 回 False(語意 = 「TC4 說查無此檔」)。
        群組卡片要的是「這格畫不出東西」,未訂閱與查無此檔對它是同一件事。
        未訂閱的 code 也**不得**入列回補:那等於替不在訂閱池的股票發 SubHistory。
        """
        engine, src = await _make()
        snap = engine.group_snapshot(["9999"])["9999"]
        assert snap["no_data"] is True
        assert snap["minutes"] == {}
        assert snap["meta"] is None
        assert snap["backfilling"] is False
        await _drain(engine)
        assert src.backfills == []
        await engine.close()

    async def test_never_sets_main_or_touches_the_pool(self) -> None:
        engine, src = await _make()
        await engine.set_watchlist(["2330", "5483"])
        subscribed = list(src.subscribed)
        engine.group_snapshot(["2330", "5483"])
        await _drain(engine)
        assert engine._main is None
        assert src.subscribed == subscribed
        assert src.unsubscribed == []
        await engine.close()

    async def test_enqueues_backfill_once_per_day(self) -> None:
        engine, src = await _make()
        src.backfill_gate = threading.Event()  # 未 set → worker 卡在回補中
        await engine.set_watchlist(["2330"])
        engine.group_snapshot(["2330"])
        engine.group_snapshot(["2330"])  # 在途 → 不重入列(pending dedup)
        src.backfill_gate.set()
        await _drain(engine)
        assert src.backfills.count("2330") == 1
        engine.group_snapshot(["2330"])  # 今日已回補 → 仍不重入列(backfilled dedup)
        await _drain(engine)
        assert src.backfills.count("2330") == 1
        await engine.close()

    async def test_backfilling_flag_tracks_the_in_flight_job(self) -> None:
        """卡片三態靠這個旗標分辨「回補中…」與「無資料」—— 沒有它,剛開的群組會有
        一整排看起來像壞掉的空卡。"""
        engine, src = await _make()
        src.backfill_gate = threading.Event()
        await engine.set_watchlist(["2330"])
        assert engine.group_snapshot(["2330"])["2330"]["backfilling"] is True
        src.backfill_gate.set()
        await _drain(engine)
        assert engine.group_snapshot(["2330"])["2330"]["backfilling"] is False
        await engine.close()

    async def test_backfill_reaches_a_non_main_member_end_to_end(self) -> None:
        """R1/R12 端到端:主圖是別檔時,群組成員照樣補得到當日分鐘列。"""
        engine, src = await _make()
        from copycat.live.stock_models import StockTick

        src.backfill_results = {
            "2330": [
                StockTick(code="2330", price_milli=2_400_000, qty=3, cum_vol=3,
                          time="09:01:00.000", trade_date="2026-07-21", side="outer",
                          is_trial=False)
            ]
        }
        await engine.set_watchlist(["2330"])
        await engine.set_main("5483")
        await _drain(engine)
        engine.group_snapshot(["2330"])
        await _drain(engine)
        minutes = engine.group_snapshot(["2330"])["2330"]["minutes"]
        assert minutes["541"]["c"] == 2_400_000  # 09:01 = 9*60+1
        await engine.close()

    async def test_member_reenqueued_after_reconnect(self) -> None:
        """R4 的群組側:斷線期間的缺口要補得回來。reconnect 只重入列 `_main`,
        成員全靠記帳清空後由下一次 group_snapshot 重新入列。"""
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        engine.group_snapshot(["2330"])
        await _drain(engine)
        assert src.backfills.count("2330") == 1
        assert src.on_reconnect is not None
        src.on_reconnect()
        await _drain(engine)
        engine.group_snapshot(["2330"])
        await _drain(engine)
        assert src.backfills.count("2330") == 2
        await engine.close()

    # ---- code review round 1 ----

    async def test_does_not_build_the_full_snapshot(self) -> None:
        """A1:batch 走 `light_snapshot()`,不得再建全量 `snapshot()`。

        全量那份會把當日數千筆 tick 逐筆組成 dict 再整份丟掉 —— 30 檔 × 每 60s。
        用「把該檔 state 的 `snapshot` 換成會炸的替身」鎖:讀不到 tick 這件事沒有
        任何畫面表現,只有這樣才驗得到真的沒走那條路。
        """
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        src.on_message(_quote(cum=7, price="2380"))
        await _drain(engine)

        def _boom() -> dict:
            raise AssertionError("group batch 不得建全量 snapshot(ticks 是數千筆)")

        engine._states["2330"].snapshot = _boom  # type: ignore[method-assign]
        snap = engine.group_snapshot(["2330"])["2330"]
        assert snap["minutes"]["657"]["c"] == 2_380_000
        assert snap["meta"]["name"] == "台積電"
        await engine.close()

    async def test_unknown_code_reuses_the_module_level_empty_payload(self, monkeypatch) -> None:
        """A1 的另一半:未知 / 未訂閱 code 不得為了「拿一份空 payload」而 new 一個
        狀態機(deque(maxlen=20_000) 一個都不便宜,而群組頁的空格數量沒有上界)。"""
        engine, _ = await _make()

        def _boom(*_a: object, **_k: object) -> None:
            raise AssertionError("未知 code 不得建 StockDayState")

        monkeypatch.setattr(stock_engine_mod, "StockDayState", _boom)
        snap = engine.group_snapshot(["9999"])["9999"]
        assert snap == {"minutes": {}, "meta": None, "no_data": True, "backfilling": False}
        await engine.close()

    async def test_released_member_is_no_data_and_not_enqueued(self) -> None:
        """A6-3:「已訂閱」與 `no_data` 的判準都改讀訂閱池 `_refs`。

        `_states` 是**只增不減**的(退訂只動 `_refs`)—— 拿它當判準會讓卡片對一檔
        早就退出自選的股票答「有資料」,還每 60s 替它發一次 SubHistory。
        """
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        await engine.set_watchlist([])
        assert "2330" in engine._states  # 前提:state 確實留著,判準才有得選
        assert "2330" not in engine._refs
        snap = engine.group_snapshot(["2330"])["2330"]
        await _drain(engine)
        assert snap["no_data"] is True
        assert src.backfills == []
        await engine.close()

    async def test_no_data_member_is_no_data_and_not_enqueued(self) -> None:
        """B2 + A6-4:TC4 已回「查無此檔」的**已訂閱**成員 → `no_data` 為真,且不再
        入列回補(對一檔平台說沒有的股票發 SubHistory 是純浪費,每 60s 一次)。"""
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        assert src.on_no_data is not None
        src.on_no_data("2330")
        await _drain(engine)
        snap = engine.group_snapshot(["2330"])["2330"]
        await _drain(engine)
        assert snap["no_data"] is True
        assert src.backfills == []
        await engine.close()

    async def test_limit_change_reenqueues_a_backfilled_member(self) -> None:
        """A6-5:漲跌停值變化的重入列放寬到「已回補過的成員」。

        鎖停日的回補補判(round6 項 2)靠 `meta` 的 upper/lower,而 meta 只有 REALTIME
        才寫入 —— 成員的回補常常先跑完。舊條件只認 `_main`,群組成員的鎖停側標就整天
        停在 neutral(內外盤整片灰、外盤比算不出來),而畫面上完全看不出異常。
        """
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        engine.group_snapshot(["2330"])
        await _drain(engine)
        assert src.backfills.count("2330") == 1
        assert engine._main != "2330"  # 前提:這一檔不是主圖,舊條件涵蓋不到
        assert src.on_message is not None
        src.on_message(_quote(cum=7))  # 首則 REALTIME:漲跌停 None → 有值
        await _drain(engine)
        assert src.backfills.count("2330") == 2
        await engine.close()


class TestBackfillFailureIsolation:
    """A2/A3:成員回補失敗的爆炸半徑與當日冷卻。

    群組檢視把「非主圖成員」也送進同一條單工 worker 之後,成員的一次 SubHistory 失敗
    會沿著舊碼把**全域** `tc4_status` 打成 down —— 畫面跳出「達錢 4 連線中斷」而達錢 4
    好得很;而 60s 一輪的重入列會讓失敗檔持續重試到收盤。
    """

    async def _collect(self, stream) -> list[dict]:
        got: list[dict] = []
        try:
            while True:
                got.append(await asyncio.wait_for(anext(stream), timeout=0.3))
        except (TimeoutError, asyncio.TimeoutError):
            pass
        return got

    async def test_member_failure_does_not_flip_global_tc4_status(self) -> None:
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        stream = engine.stream()
        src.backfill_error = ConnectionError("SubHistory 2330 failed")
        engine.group_snapshot(["2330"])
        await _drain(engine)
        assert engine.tc4_status == "up"
        got = await self._collect(stream)
        statuses = [m for m in got if m["type"] == "status"]
        assert statuses, "回補期間必有 status 訊息(前提)"
        assert all(m["tc4"] == "up" for m in statuses)
        # 徽章仍要收:失敗路徑不補推 backfilling=None 的話「回補中…」永遠掛著(TQ-4)
        assert statuses[-1]["backfilling"] is None
        await engine.close()

    async def test_main_failure_still_marks_tc4_down(self) -> None:
        """舊語意保留:主圖自己的回補失敗仍是「達錢 4 出事了」的最好證據 ——
        使用者當下就在看那一檔,靜默降級會讓他以為畫面是真的。"""
        engine, src = await _make()
        src.backfill_error = ConnectionError("SubHistory 2330 failed")
        await engine.set_main("2330")
        await _drain(engine)
        assert engine.tc4_status == "down"
        await engine.close()

    async def test_member_stops_being_enqueued_after_three_failures(self) -> None:
        """A2 止血:同一檔當日連 3 次失敗就不再入列。

        沒有這條的話,一檔壞碼會讓 60s 輪詢整天對 TC4 發同一個必敗請求(單工 worker
        還會被它排隊佔用),而卡片顯示的一直是「回補中…」。
        """
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        src.backfill_error = ConnectionError("SubHistory 2330 failed")
        for _ in range(5):
            engine.group_snapshot(["2330"])
            await _drain(engine)
        assert src.backfills.count("2330") == 3
        await engine.close()

    async def test_inflight_job_survives_reconnect_without_duplicate_enqueue(self) -> None:
        """A3:`_backfill_pending` 改計數,reconnect 不再清它。

        舊碼把在途集合一起清掉 → 下一次 `group_snapshot`(60s 或更快)會對**同一檔**
        再入列一次;而第一個 job 結清時 `discard` 直接把旗標翻成 False,卡片在第二個
        job 還在跑的時候就從「回補中…」跳成「無資料」。
        """
        engine, src = await _make()
        src.backfill_gate = threading.Event()  # 未 set → worker 卡在回補中
        await engine.set_watchlist(["2330"])
        engine.group_snapshot(["2330"])
        await _drain(engine)
        assert src.on_reconnect is not None
        src.on_reconnect()
        await _drain(engine)
        assert engine.group_snapshot(["2330"])["2330"]["backfilling"] is True
        src.backfill_gate.set()
        await _drain(engine)
        assert src.backfills.count("2330") == 1
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


# ---- 個股期合約主圖(stkfut-contracts SC-3;instrument key = 股號 或 F:<prod>:<ym>)----

_CONTRACT = "F:CDF:202609"
_CONTRACT_SYMBOL = "TC.F.TWF.CDF.202609"


def _fut_quote(*, cum: int = 1, price: str = "2400", **kw) -> dict:
    """月契約 leaf 的 REALTIME(`Security` 是產品碼,**不是** instrument key)。"""
    return _quote(code="CDF", symbol=_CONTRACT_SYMBOL, cum=cum, price=price, **kw)


class TestInstrumentRouting:
    """D1/R2-2:推播路由以 `Symbol` → `_symbol_to_key` 決定收件人。"""

    async def test_contract_quote_lands_on_the_contract_key(self) -> None:
        engine, src = await _make()
        await engine.set_main_contract(_CONTRACT)
        assert _CONTRACT in src.subscribed
        stream = engine.stream()
        assert src.on_message is not None
        src.on_message(_fut_quote(cum=7))
        await _drain(engine)
        got = await _collect(stream)
        tick = next(m for m in got if m["type"] == "tick")
        assert tick["code"] == _CONTRACT  # WS code = instrument key,不是 Security
        assert engine.snapshot(_CONTRACT)["last"]["cum_vol"] == 7
        await engine.close()

    async def test_security_field_does_not_decide_the_recipient(self) -> None:
        """`Security` 不是路由鍵:個股期 leaf 的該欄值域未實證(產品碼 / 股號都可能),
        拿它當鍵時「合約推播蓋掉現貨狀態」是靜默的 —— 主圖畫的是期貨價,側欄的現貨
        卻也跟著跳。"""
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        await engine.set_main_contract(_CONTRACT)
        assert src.on_message is not None
        src.on_message(_fut_quote(cum=9, price="2400") | {"Security": "2330"})
        await _drain(engine)
        assert engine.snapshot(_CONTRACT)["last"]["cum_vol"] == 9
        assert engine.snapshot("2330")["last"] is None
        await engine.close()

    async def test_bookkeeping_is_written_before_subscribe(self) -> None:
        """R2-2 先寫後訂:TC4 在 SUB 回來後毫秒級推第一則 REALTIME(§8 實證)。

        後寫的話首則必漏 —— 冷門合約整天可能只有那一則(meta / 參考價),而畫面
        只是空著。fake 在 subscribe 當下回推並**等到引擎收下才返回**(順序反了就會
        等滿 deadline 再讓斷言紅,不靠時序運氣)。
        """
        engine, src = await _make()

        def _push_on_subscribe(code: str) -> None:
            if code != _CONTRACT or src.on_message is None:
                return
            src.on_message(_fut_quote(cum=5))
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                state = engine._states.get(_CONTRACT)
                if state is not None and state.last is not None:
                    return
                time.sleep(0.005)

        src.on_subscribe = _push_on_subscribe
        await engine.set_main_contract(_CONTRACT)
        await _drain(engine)
        assert engine.snapshot(_CONTRACT)["last"]["cum_vol"] == 5
        await engine.close()

    async def test_failed_subscribe_rolls_back_the_symbol_map(self) -> None:
        """訂閱失敗要連對映一起回滾:留著的話那個 symbol 的後續推播會落到一個
        沒有 owner 的 key 上(而 `_refs` 的對帳判準看不到它)。"""
        engine, src = await _make()
        src.fail_subscribe.add(_CONTRACT)
        try:
            await engine.set_main_contract(_CONTRACT)
        except ConnectionError:
            pass
        assert _CONTRACT_SYMBOL not in engine._symbol_to_key
        await engine.close()

    async def test_unmapped_symbol_is_dropped(self) -> None:
        engine, src = await _make()
        await engine.set_main("2330")
        assert src.on_message is not None
        src.on_message(_fut_quote(cum=3))  # 從未訂閱這個合約
        await _drain(engine)
        assert engine.snapshot(_CONTRACT)["last"] is None
        assert engine.snapshot("2330")["last"] is None
        await engine.close()

    async def test_hot_leg_is_routed_by_suffix_not_by_tc_f_prefix(self) -> None:
        """`_handle_stkfut` 的判定改「endswith('.HOT')」—— 舊的 `startswith('TC.F.')`
        會把月契約 leaf 一起吃掉,主圖永遠收不到自己的推播。"""
        engine, src = await _make()
        await engine.set_main("2330")  # 對映表 2330 → CDF,加訂 HOT 腿
        stream = engine.stream()
        assert src.on_message is not None
        src.on_message(_quote(cum=1))  # 現股價 2380
        src.on_message(
            _quote(code="CDF", symbol="TC.F.TWF.CDF.HOT", price="2398", cum=100)
            | {"SecurityName": "台積電(2330)"}
        )
        await _drain(engine)
        got = await _collect(stream)
        assert any(m["type"] == "stkfut" for m in got)
        assert "F:CDF" not in {m.get("code") for m in got if m["type"] == "tick"}
        await engine.close()


class TestContractTrialWindow:
    """D2:期貨 instrument 用空試撮窗(現貨口徑不動)。"""

    async def test_contract_ingests_0850_and_1327(self) -> None:
        engine, src = await _make()
        await engine.set_main_contract(_CONTRACT)
        assert src.on_message is not None
        src.on_message(_fut_quote(cum=1, precise="005000000000"))  # 台北 08:50
        src.on_message(_fut_quote(cum=2, precise="052700000000"))  # 台北 13:27
        await _drain(engine)
        minutes = engine.snapshot(_CONTRACT)["minutes"]
        assert set(minutes) == {"530", "807"}  # 8*60+50 / 13*60+27
        await engine.close()

    async def test_spot_still_drops_the_trial_window(self) -> None:
        engine, src = await _make()
        await engine.set_main("2330")
        assert src.on_message is not None
        src.on_message(_quote(cum=1, precise="005000000000"))
        src.on_message(_quote(cum=2, precise="052700000000"))
        await _drain(engine)
        assert engine.snapshot("2330")["minutes"] == {}
        await engine.close()


class TestContractSessionGate:
    """D14b:期貨 key 的 ingest 前加日盤窗 gate(夜盤 tick 不得進當日狀態)。"""

    async def test_night_ticks_never_reach_the_contract_state(self) -> None:
        engine, src = await _make()
        await engine.set_main_contract(_CONTRACT)
        assert src.on_message is not None
        src.on_message(_fut_quote(cum=1, precise="073000000000"))  # 台北 15:30
        await _drain(engine)
        # 基準不是 0:主圖入列的**空回補**照樣 `apply_backfill` → seq 跳增 1001
        # (既有行為,與 ingest 無關)。要鎖的是「夜盤 tick 不推進序號」,所以取基準比對。
        before = engine.snapshot(_CONTRACT)["seq"]
        src.on_message(_fut_quote(cum=2, precise="170000000000"))  # 台北次日 01:00
        await _drain(engine)
        snap = engine.snapshot(_CONTRACT)
        assert snap["minutes"] == {}
        assert snap["last"] is None  # 兩則都沒進狀態機
        assert snap["seq"] == before
        await engine.close()

    async def test_daytime_edges_are_inside_the_gate(self) -> None:
        engine, src = await _make()
        await engine.set_main_contract(_CONTRACT)
        assert src.on_message is not None
        src.on_message(_fut_quote(cum=1, precise="004500000000"))  # 台北 08:45 開盤
        src.on_message(_fut_quote(cum=2, precise="054500000000"))  # 台北 13:45 收盤
        await _drain(engine)
        assert set(engine.snapshot(_CONTRACT)["minutes"]) == {"525", "825"}
        await engine.close()

    async def test_spot_is_not_gated(self) -> None:
        engine, src = await _make()
        await engine.set_main("2330")
        assert src.on_message is not None
        src.on_message(_quote(cum=1, precise="073000000000"))  # 台北 15:30(盤後零股等)
        await _drain(engine)
        assert set(engine.snapshot("2330")["minutes"]) == {"930"}
        await engine.close()

    async def test_night_quote_leaves_the_book_and_meta_untouched(self) -> None:
        """code review A1:窗外要**整則早退**,不是只丟 tick。

        只丟 tick 的話夜盤的五檔與參考價照樣蓋掉日盤收盤簿 —— 分時圖與序號都不動,
        畫面只表現為「收盤後五檔還在跳」,沒有任何錯誤訊號。
        """
        engine, src = await _make()
        await engine.set_main_contract(_CONTRACT)
        assert src.on_message is not None
        src.on_message(_fut_quote(cum=1, precise="004500000000"))  # 台北 08:45
        await _drain(engine)
        day = engine.snapshot(_CONTRACT)
        assert day["book"] == {"bids": [(2_375_000, 10)], "asks": [(2_380_000, 10)]}
        src.on_message(
            _fut_quote(cum=2, precise="073000000000")  # 台北 15:30
            | {"Bid": "2500", "BidVolume": "99", "ReferencePrice": "2500"}
        )
        await _drain(engine)
        after = engine.snapshot(_CONTRACT)
        assert after["book"] == day["book"]
        assert after["meta"] == day["meta"]

        await engine.close()

    async def test_night_book_only_update_is_dropped_by_wall_clock(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """純簿更新(qty=0 → tick=None)沒有 tick 時刻可判窗 → 退到本機時鐘。

        這是夜盤覆蓋日盤簿最主要的一條路:個股期夜盤大部分時間只有簿在動。
        """
        engine, src = await _make()
        await engine.set_main_contract(_CONTRACT)
        assert src.on_message is not None
        src.on_message(_fut_quote(cum=1, precise="004500000000"))
        await _drain(engine)
        day_book = engine.snapshot(_CONTRACT)["book"]
        monkeypatch.setattr(stock_engine_mod, "_now_taipei_hhmm", lambda: "15:30")
        src.on_message(
            _fut_quote(cum=1, qty="0") | {"Bid": "2500", "BidVolume": "99"}  # 純簿更新
        )
        await _drain(engine)
        assert engine.snapshot(_CONTRACT)["book"] == day_book
        await engine.close()

    async def test_daytime_book_only_update_still_applies(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """對照組:本機時鐘在日盤窗內時,純簿更新照舊生效(gate 不誤傷)。"""
        engine, src = await _make()
        await engine.set_main_contract(_CONTRACT)
        assert src.on_message is not None
        monkeypatch.setattr(stock_engine_mod, "_now_taipei_hhmm", lambda: "10:30")
        src.on_message(_fut_quote(cum=1, qty="0") | {"Bid": "2500", "BidVolume": "99"})
        await _drain(engine)
        assert engine.snapshot(_CONTRACT)["book"]["bids"] == [(2_500_000, 99)]
        await engine.close()


class TestRolloverIsolationForContracts:
    """D14a:期貨 tick 不**武裝** stage1(夜盤跨午夜的日期會比日盤主圖早一天到);
    但已武裝的 pending 可由**日盤**合約 tick 完成 stage2(E-3)。

    兩者的分界靠 `_in_futures_session` 的整則早退:到得了 stage2 那段的期貨 tick
    必屬日盤 08:45–13:45,其 `trade_date` 即當日,無跨午夜歧義。
    """

    async def test_contract_tick_with_a_new_date_never_rolls_the_day(self) -> None:
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        await engine.set_main_contract(_CONTRACT)
        assert src.on_message is not None
        src.on_message(_quote(cum=100))  # 現貨當日狀態
        await _drain(engine)
        # 日盤窗內、但日期是次日(夜盤契約的跨日推播)
        src.on_message(_fut_quote(cum=1, date="20260722"))
        await _drain(engine)
        assert engine.trade_date == "2026-07-21"
        assert engine._pending_date is None
        assert engine.snapshot("2330")["last"]["cum_vol"] == 100  # 現貨狀態未被 reset
        await engine.close()

    async def test_night_contract_tick_does_not_complete_a_pending_rollover(self) -> None:
        """**事前標為該變的既有斷言**(舊名 `test_contract_tick_does_not_complete_a_pending_rollover`)。

        舊契約是「任何期貨 tick 都不得完成 stage2」,那把 08:45–09:00 的期貨成交
        全丟掉(pending 期間合約 tick 落到 `state.ingest`,昨日 `_last_cum` 使它恆
        False);極端情形是自選空 + 主圖合約時永遠等不到現貨首筆 → 整天不換日。
        新契約 = **日盤**合約 tick 可完成 stage2,而這條保留其防護意圖的新表述:
        夜盤 tick 在 `_in_futures_session` 就整則早退,到不了 stage2 那段。
        """
        engine, src = await _make()
        await engine.set_main_contract(_CONTRACT)
        engine.rollover_stage1("2026-07-22")
        assert src.on_message is not None
        # 台北次日 01:00(夜盤):跨午夜的日期比日盤主圖早一天到
        src.on_message(_fut_quote(cum=1, date="20260722", precise="170000000000"))
        await _drain(engine)
        assert engine._pending_date == "2026-07-22"  # 仍等日盤首筆
        assert engine.trade_date == "2026-07-21"
        await engine.close()

    async def test_daytime_contract_tick_completes_a_pending_rollover(self) -> None:
        """E-3:pending 已武裝時,日盤合約 tick 要完成 stage2 並自己被 ingest。

        期貨日盤 08:45 開盤、現貨 09:00 才有首筆 —— 舊碼要求 `rolls_the_day`
        (非期貨鍵)才完成 stage2,那 15 分鐘的期貨成交全部落到 `state.ingest`
        而昨日 `_last_cum` 使它恆 False(不 apply 不推播),分時圖左緣整段消失
        且沒有任何錯誤訊號。
        """
        engine, src = await _make()
        await engine.set_main_contract(_CONTRACT)
        await _drain(engine)
        engine.rollover_stage1("2026-07-22")
        stream = engine.stream()
        assert src.on_message is not None
        # 台北 08:46(日盤窗內)+ 新日 trade_date
        src.on_message(_fut_quote(cum=1, date="20260722", precise="004600000000"))
        await _drain(engine)

        assert engine.trade_date == "2026-07-22"
        assert engine._pending_date is None
        assert engine.snapshot(_CONTRACT)["last"]["cum_vol"] == 1  # 觸發的那一則自己也進狀態
        got = await _collect(stream)
        assert any(m["type"] == "tick" and m["code"] == _CONTRACT for m in got)
        await engine.close()


class TestMainSlotTransfer:
    """D15 槽位轉移表:四種轉移後 `_refs` 零洩漏(逐 owner 斷言)。"""

    async def test_four_transfers_leave_no_ref_leak(self) -> None:
        engine, _src = await _make()
        # 現貨 → 期現對照腿一併掛上
        await engine.set_main("2330")
        assert engine._refs["2330"] == {"main"}
        assert engine._refs["F:CDF"] == {"stkfut:2330"}

        # 現貨 → 期貨:主圖換合約,舊現貨與它的對照腿一起收(合約態不加對照腿)
        await engine.set_main_contract(_CONTRACT)
        assert engine._refs == {_CONTRACT: {"main"}}

        # 期貨 → 期貨(換月)
        await engine.set_main_contract("F:CDF:202610")
        assert engine._refs == {"F:CDF:202610": {"main"}}

        # 期貨 → 現貨:`_release_stkfut` 對合約鍵查無對映 → 無害早退
        await engine.set_main("2317")
        assert engine._refs == {"2317": {"main"}, "F:DHF": {"stkfut:2317"}}

        # 現貨 → 現貨(既有行為)
        await engine.set_main("2330")
        assert engine._refs == {"2330": {"main"}, "F:CDF": {"stkfut:2330"}}
        await engine.close()

    async def test_contract_main_enqueues_its_own_backfill(self) -> None:
        engine, src = await _make()
        await engine.set_main_contract(_CONTRACT)
        await _drain(engine)
        assert src.backfills == [_CONTRACT]
        await engine.close()

    async def test_releasing_the_old_main_clears_its_no_data_flag(self) -> None:
        """code review A7d:主圖被**真正退訂**時要一併清 `_no_data`。

        留著的話下次切回那一檔,畫面在任何新推播之前就先掛上「無資料」,而那是上一輪
        訂閱期的答案 —— 而重新訂閱後 TC4 若這次有推,`_no_data` 也只在收到推播那一刻
        才會被清,中間那段空窗使用者看到的是假訊息。`set_watchlist` 移除檔早有同款處理。
        """
        engine, src = await _make()
        await engine.set_main("9999")  # 對映表無此碼 → 不掛期現對照腿
        assert src.on_no_data is not None
        src.on_no_data("9999")
        await _drain(engine)
        assert engine.snapshot("9999")["no_data"] is True
        await engine.set_main_contract(_CONTRACT)
        assert "9999" not in engine._refs  # 前提:真的退訂了
        assert engine.snapshot("9999")["no_data"] is False
        await engine.close()

    async def test_no_data_survives_when_the_old_main_is_still_subscribed(self) -> None:
        """還有 owner(自選)時不得清:那格旗標歸側欄,不歸主圖。

        無條件清的話,自選裡一檔查無資料的股票只要被點開再切走,側欄的「無資料」
        就此消失且不會再回來(TC4 的 no-data 回呼只在訂閱當下發一次)。
        """
        engine, src = await _make()
        await engine.set_watchlist(["9999"])
        await engine.set_main("9999")
        assert src.on_no_data is not None
        src.on_no_data("9999")
        await _drain(engine)
        await engine.set_main_contract(_CONTRACT)
        assert engine._refs["9999"] == {"watchlist"}
        assert engine.snapshot("9999")["no_data"] is True
        await engine.close()

    async def test_watchlist_owner_survives_a_contract_switch(self) -> None:
        """自選檔同時是主圖時,切去合約不得把它退訂(refcount 語意不因新槽位而破)。"""
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        await engine.set_main("2330")
        await engine.set_main_contract(_CONTRACT)
        assert engine._refs["2330"] == {"watchlist"}
        assert "2330" not in src.unsubscribed
        await engine.close()


class TestWatchlistRemovalBookkeeping:
    """E-4:自選移除的旗標清理要與 `set_main_contract` 的 A7d 同守則 ——
    **真正退訂了才**清,還有 owner 時不動。"""

    async def test_no_data_survives_removal_while_main_still_holds(self) -> None:
        """同一檔同時是主圖與自選時,自自選移除**不得**清 `_no_data`。

        TC4 的 no-data 回呼只在訂閱當下發一次 —— 被誤清之後那一檔的 snapshot 恆
        `no_data=False`,而它其實仍訂著且平台說查無此檔:「查無此檔」與「還沒推」
        在畫面上合併成同一張空卡,使用者分不出該不該換一檔看。
        鏡像路徑 `set_main_contract`(A7d)早已依此守則做對。
        """
        engine, src = await _make()
        await engine.set_watchlist(["9999"])  # 對映表無此碼 → 不掛期現對照腿
        await engine.set_main("9999")
        assert src.on_no_data is not None
        src.on_no_data("9999")
        await _drain(engine)
        assert engine.snapshot("9999")["no_data"] is True  # 前提:旗標確實掛上了

        await engine.set_watchlist([])

        assert engine._refs["9999"] == {"main"}  # 前提:主圖 owner 還在 = 沒真退訂
        assert engine.snapshot("9999")["no_data"] is True
        await engine.close()

    async def test_no_data_cleared_when_removal_is_the_last_owner(self) -> None:
        """對照組:自選是最後一個 owner → 真退訂,旗標照清(A7d 的另一半)。

        不清的話下次把它加回自選,畫面在任何新推播之前就先掛「無資料」,
        而那是上一輪訂閱期的答案。
        """
        engine, src = await _make()
        await engine.set_watchlist(["9999"])
        assert src.on_no_data is not None
        src.on_no_data("9999")
        await _drain(engine)
        assert engine.snapshot("9999")["no_data"] is True

        await engine.set_watchlist([])

        assert "9999" not in engine._refs  # 前提:真的退訂了
        assert engine.snapshot("9999")["no_data"] is False
        await engine.close()

    async def test_backfill_bookkeeping_restarts_after_a_real_unsubscribe(self) -> None:
        """E-2:`_backfilled` 是日別記帳,但**真退訂**同樣要讓它作廢。

        清空點只有 rollover stage2 與 reconnect —— 移除再加回之後(`_acquire` 的
        setdefault 用回同一個舊 state)`code not in self._backfilled` 恆假,
        `group_snapshot` 的入列 guard 永遠擋著 → 退訂期間的分鐘缺口整天補不回來,
        而 `backfilling` / `no_data` 都是 False,卡片零訊號地空著。
        """
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        engine.group_snapshot(["2330"])
        await _drain(engine)
        assert src.backfills.count("2330") == 1
        assert "2330" in engine._backfilled  # 前提:確實記過帳

        await engine.set_watchlist([])  # 真退訂(自選是唯一 owner)
        assert "2330" not in engine._refs
        await engine.set_watchlist(["2330"])  # 重新加回
        engine.group_snapshot(["2330"])
        await _drain(engine)

        assert src.backfills.count("2330") == 2
        await engine.close()

    async def test_failure_cooldown_restarts_after_a_real_unsubscribe(self) -> None:
        """`_backfill_failed` 同構:冷卻計數隨真退訂歸零。

        re-acquire 是使用者驅動(把股票加回自選)、不是重試風暴,所以「當日已失敗
        3 次」這個判斷跟著訂閱期一起作廢 —— 否則使用者移除再加回也救不了那一格。
        """
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        src.backfill_error = ConnectionError("SubHistory 2330 failed")
        for _ in range(5):
            engine.group_snapshot(["2330"])
            await _drain(engine)
        assert src.backfills.count("2330") == 3  # 前提:當日冷卻確實生效(A2)

        await engine.set_watchlist([])
        await engine.set_watchlist(["2330"])
        engine.group_snapshot(["2330"])
        await _drain(engine)

        assert src.backfills.count("2330") == 4
        await engine.close()

    async def test_backfill_bookkeeping_survives_removal_while_main_still_holds(self) -> None:
        """對照組:仍有 owner(主圖)= 沒真退訂 → 記帳**保留**,不得重補。

        無條件清會讓「移出自選」變成對 TC4 多發一次 SubHistory,而那一檔的當日
        資料根本沒斷過。
        """
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        await engine.set_main("2330")
        await _drain(engine)
        assert src.backfills.count("2330") == 1  # set_main 的入列
        assert "2330" in engine._backfilled

        await engine.set_watchlist([])

        assert engine._refs["2330"] == {"main"}  # 前提:主圖 owner 還在
        assert "2330" in engine._backfilled
        engine.group_snapshot(["2330"])
        await _drain(engine)
        assert src.backfills.count("2330") == 1
        await engine.close()


class TestDirtyWatchlistScope:
    """D16:`_dirty_watchlist` 只收自選碼 —— 合約鍵混進去會廣播 code="F:CDF:202609"
    的 `watchlist_quote`,而側欄以 code 對照自選名單,那一則對它是垃圾。"""

    async def test_contract_ticks_never_produce_watchlist_quote(self) -> None:
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        await engine.set_main_contract(_CONTRACT)
        stream = engine.stream()
        assert src.on_message is not None
        src.on_message(_fut_quote(cum=3))
        await _drain(engine)
        got = await _collect(stream)
        codes = {m["code"] for m in got if m["type"] == "watchlist_quote"}
        assert codes <= {"2330"}
        assert _CONTRACT not in engine._dirty_watchlist
        await engine.close()
