from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import re
import threading
import time
from types import SimpleNamespace
from typing import Callable

import pytest

from copycat.live.stock_source import Bar, BarsStatus, stock_symbol
from copycat.live.tc4 import HistoryTimeoutError
from copycat.server import stock_engine as stock_engine_mod
from copycat.server.stock_engine import StockEngine
from tests.helpers.wait import wait_until


def _quote(
    code: str = "2330",
    *,
    cum: int = 1,
    price: str = "2380",
    qty: str = "1",
    date: str = "20260721",
    symbol: str | None = None,
    precise: str = "25751000000",
    status: str = "0",
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
        "TradeStatus": status,
    }


class FakeSource:
    def __init__(self) -> None:
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.trade_dates: list[str] = []
        self.backfills: list[str] = []
        self.prepares: list[list[str]] = []
        self.prepare_error: Exception | None = None
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
        # 逐次結果:pop(0) 取一個,取完退回 `backfill_error`(重試路徑要能表達
        # 「第一發逾時、第二發成功」,單一 `backfill_error` 只表達得出恆錯)
        self.backfill_errors: list[Exception | None] = []
        self.daily_bars_error: Exception | None = None
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

    def prepare_backfill(self, codes: list[str]) -> None:
        """S1-b:worker 出隊時整批先 SubHistory。只記批次(順序 + 成員)。"""
        self.prepares.append(list(codes))
        if self.prepare_error is not None:
            raise self.prepare_error

    def backfill(self, code: str) -> list:
        self.backfills.append(code)
        if self.backfill_errors:
            err = self.backfill_errors.pop(0)
            if err is not None:
                raise err
        elif self.backfill_error is not None:
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
        if self.daily_bars_error is not None:
            raise self.daily_bars_error
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


def _tick_items(got: list[dict]) -> list[dict]:
    """`ticks` 打包訊息攤平成 item 列(mod/group-grid-ticks)。

    逐筆成交自此只走 0.1 s 打包(`{"type":"ticks","items":[…]}`),不再有單筆 `tick` 型別;
    既有斷言只關心「哪些成交、什麼欄位、什麼 seq」,攤平後逐字不動。
    """
    return [item for m in got if m["type"] == "ticks" for item in m["items"]]


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

    async def test_set_main_back_to_backfilled_code_does_not_reenqueue(self) -> None:
        """set_main 切回「今日已回補、仍有 owner」的檔不重排回補(next-time L69:
        08-31 實測 2455 一天 75 次重複回補全來自來回切主圖,每次 = SubHistory +
        全量收割)。斷線缺口的保險由 reconnect 清 `_backfilled` 承接,不靠切主圖
        順便重補;no_data / 冷卻不在此擋(group_snapshot docstring 那把尺)。"""
        engine, src = await _make()
        await engine.set_watchlist(["2330"])  # 切走後仍有 owner,記帳不清
        await engine.set_main("2330")
        await _drain(engine)
        assert src.backfills.count("2330") == 1
        await engine.set_main("5483")
        await _drain(engine)
        await engine.set_main("2330")  # 切回:今日已回補 → 不重排
        await _drain(engine)
        assert src.backfills.count("2330") == 1
        await engine.close()

    async def test_set_main_back_to_inflight_code_does_not_reenqueue(self) -> None:
        """set_main 切回「回補在途」的檔不重複入列(與 `_backfill_wanted` 的在途
        dedup 同尺;worker 出隊不查 `_backfilled`,重複 job 一定會多打一次 TC4)。"""
        engine, src = await _make()
        src.backfill_gate = threading.Event()
        await engine.set_watchlist(["2330"])
        await engine.set_main("2330")  # job1 在途(gate 未開)
        await engine.set_main("5483")
        await engine.set_main("2330")  # 在途 → 不重排
        src.backfill_gate.set()
        await _drain(engine)
        assert src.backfills.count("2330") == 1
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

        S2(首筆當日成交 tick 入列)之後,觸發 stage2 的那一則**本身**就會替新一天排一筆
        回補 —— 用 `backfill_gate` 把它卡在在途,「清空」的斷言才看得到;放行後重新進帳
        的是新一天的記帳,不是舊的沒清。
        """
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        src.on_message(_quote(cum=1))  # 首筆當日成交 → S2 入列一次(meta 同時到位)
        await _drain(engine)
        assert src.backfills == ["2330"]
        assert "2330" in engine._backfilled
        engine.rollover_stage1("2026-07-22")
        src.backfill_gate = threading.Event()  # 新一天那筆卡在在途
        src.on_message(_quote(cum=50, date="20260722"))  # 首筆新日 tick → stage2
        await _drain(engine)
        assert "2330" not in engine._backfilled  # 舊記帳清掉
        assert engine._backfill_pending == {"2330": 1}  # 新一天的 job 在途(S2)
        src.backfill_gate.set()
        await _drain(engine)
        assert src.backfills == ["2330", "2330"]
        assert "2330" in engine._backfilled  # 新一天的記帳
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
        src.backfill_gate = threading.Event()  # S2:新日首筆會排 2330 的新一天 job,先卡住
        src.on_message(_quote(cum=50, date="20260722"))
        await _drain(engine)

        assert engine._backfilled == set()  # 迴圈之後的步驟確實跑完
        assert engine._backfill_pending == {"2330": 1}  # 新一天的 job 在途(不是舊帳沒清)
        assert engine.snapshot("5483")["last"] is None  # 迴圈內的每個 state 都 reset 到
        assert engine.trade_date == "2026-07-22"
        src.backfill_gate.set()
        await _drain(engine)
        await engine.close()


class TestStreamAndStatus:
    async def test_stream_receives_tick_and_book(self) -> None:
        engine, src = await _make()
        # 主圖入列的**空回補**照樣 `apply_backfill` → seq 跳增 1001(stock_state
        # `_BACKFILL_SEQ_MARGIN`)。它跑在 worker thread 上,與下面那則 tick 誰先落地
        # 沒有定序:回補先到時首則 tick 的 seq 是 1002 不是 1(08-26 全套三輪一紅、單跑
        # 恆綠的那條 flake)。卡住回補,讓 tick 必然是第一個事件;斷言不動。
        src.backfill_gate = threading.Event()
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
        assert "ticks" in types
        assert "book" in types
        tick_msg = _tick_items(got)[0]
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
        src.backfill_gate.set()
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
        ticks = _tick_items(got)
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
        # **該變**(review SP1):換窗(`set_trade_date`)從 stage1 的同步段下沉到重掛
        # 的背景 to_thread —— N052 之後它含一批同步 UNSUBQUOTE,留在 loop 上就是
        # 「立即返回」這條不變式自己被打破。這裡改驗「背景段跑完之後才生效」,
        # 而順序(換窗 → 重掛)另由 `TestRolloverStageOneOffLoop` 釘住。
        assert "2026-07-22" not in src.trade_dates  # 同步段不再碰 source
        src.subscribe_gate.set()
        await _drain(engine)
        assert "2026-07-22" in src.trade_dates  # 背景段已換窗
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


class TestDailyBarsTimeout:
    """bug/history-timeout-propagation:逾時 ≠ 資料面沒有。

    `daily_bars` 回空時 SignalHub 讀成「無已完成日 K,CDP 停用」且**永不重試**
    (app.py 的分工:空清單 = 資料面沒有;拋例外 = 暫時性 → X-2b 有限重試)。
    """

    async def test_history_timeout_propagates(self) -> None:
        engine, src = await _make()
        src.daily_bars_error = HistoryTimeoutError("first page not ready")
        with pytest.raises(HistoryTimeoutError):
            await engine.daily_bars("2330")
        await engine.close()

    async def test_plain_connection_error_still_degrades_to_empty(self) -> None:
        engine, src = await _make()
        src.daily_bars_error = ConnectionError("tc4 down")
        assert await engine.daily_bars("2330") == []
        await engine.close()


class TestHistoryTimeoutIsConnectionError:
    """`HistoryTimeoutError` 的**子類契約** —— 整個修法就架在這一條上(repro §修法)。

    六處 caller 的上游已經有 `except ConnectionError` 的降級 / 重試網,做成子類才能
    「一行不改自動接手」;基底哪天被改成 `Exception`,那些路徑會從降級變成把例外往上
    炸,而它們多半是背景 task —— 炸掉只留一行 log,畫面靜靜地空著。
    """

    def test_is_a_connection_error_subclass(self) -> None:
        assert issubclass(HistoryTimeoutError, ConnectionError)

    async def test_caller_that_only_catches_connection_error_still_degrades(self) -> None:
        """`bars_range` 是**不分辨逾時**的那種 caller(只寫 `except ConnectionError`):
        逾時對它必須仍是「降級回空 + disconnected」,不是往外拋。"""
        engine, src = await _make()

        def boom(*_args: object, **_kwargs: object) -> tuple[list[Bar], BarsStatus]:
            raise HistoryTimeoutError("first page not ready")

        src.fetch_bars_range = boom  # type: ignore[method-assign]
        assert await engine.bars_range("2330", "1", "2026-07-28", "2026-07-28") == (
            [],
            "disconnected",
        )
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


# 恆失敗的自選檔:重試輪的**可觀察計數器**。用牆鐘 sleep 換輪數在 Windows 上是假的
# (timer 解析度 15.6ms,`sleep(0.05)` 對 interval=0.01 實際只跑 ~3 輪),否定斷言的
# 強度會比註解寫的低一半以上(review W-4)。
_SENTINEL = "8888"


async def _wait_rounds(src: _RetrySource, rounds: int, timeout: float = 2.0) -> None:
    """等重試迴圈確實跑滿 `rounds` 輪(以哨兵檔被重試的次數計)。"""
    base = src.attempts.count(_SENTINEL)
    await wait_until(lambda: src.attempts.count(_SENTINEL) >= base + rounds, timeout=timeout)


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
        await wait_until(lambda: "9999" in src.subscribed)
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
        await wait_until(lambda: "2330" in engine._failed_resubs)
        src.fail_subscribe.discard("2330")
        await wait_until(lambda: "2330" not in engine._failed_resubs)
        assert src.subscribed.count("2330") >= 2  # 重掛真的發出去了
        await engine.close()

    async def test_failed_resub_pruned_when_code_unsubscribed(self) -> None:
        engine, src = await _make_retry()
        src.fail_subscribe.add(_SENTINEL)
        await engine.set_watchlist([_SENTINEL])  # 輪數哨兵(段 2 恆失敗)
        await engine.set_main("2330")
        src.fail_subscribe.add("2330")
        engine.rollover_stage1("2026-07-22")
        await wait_until(lambda: "2330" in engine._failed_resubs)
        await engine.set_main("5483")  # 2330 last owner 退 → 已不在 _refs
        await wait_until(lambda: not engine._failed_resubs)
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
        await wait_until(lambda: "9999" in src.subscribed)
        await engine.close()

    async def test_head_of_line_failure_does_not_starve_failed_resubs(self) -> None:
        """C-1 的段 3 對稱情境(pending_resubs 是 sorted,順序同樣固定)。"""
        engine, src = await _make_retry()
        await engine.set_watchlist(["9997", "9998"])  # 先真訂上 → owner 在 _refs
        src.fail_subscribe.update({"9997", "9998"})
        engine.rollover_stage1("2026-07-22")  # 全量重掛兩檔皆失敗
        await wait_until(lambda: engine._failed_resubs == {"9997", "9998"})
        src.fail_subscribe.discard("9998")  # 只修 sorted 順序在後的那檔
        await wait_until(lambda: "9998" not in engine._failed_resubs)
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
        await wait_until(lambda: src.attempts.count("2330") >= 2)  # 重掛已進到慢失敗窗
        async with engine._pool_lock:
            await asyncio.sleep(0.4)  # 慢失敗早已結束;合併必須還卡在鎖外
            assert engine._failed_resubs == set()
        await wait_until(lambda: "2330" in engine._failed_resubs)  # 放鎖後才進帳
        await engine.close()

    async def test_close_stops_retry_loop(self) -> None:
        """W-2:關機後重試不再新排(仿 corr test_close_stops_retry_loop)。"""
        engine, src = await _make_retry()
        src.fail_subscribe.add("9999")
        await engine.set_watchlist(["9999"])
        await wait_until(lambda: src.attempts.count("9999") > 4)  # 迴圈確實在跑
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
        await wait_until(lambda: "F:CDF" in src.subscribed)
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
    會 set_main,群組每分鐘 50 次會把主圖搶走令主圖凍結 → 那條路不可重用)。"""

    async def test_payload_is_the_lightweight_three_keys_plus_backfilling(self) -> None:
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        src.on_message(_quote(cum=7, price="2380"))
        await _drain(engine)
        snap = engine.group_snapshot(["2330"])["2330"]
        # 🔴 group-grid-full-chart:卡片改畫「完全同款」的分時圖 → light_snapshot 的
        # 四個加鍵(vwap/high/low/vp)必須原封轉發。鍵名單一定義在 `light_snapshot()`,
        # 這裡只 `{**light, ...}` 展開 —— 逐鍵手抄的漂移樣態是後端補了鍵、卡片卻收不到
        assert set(snap) == {
            "minutes",
            "meta",
            "vwap",
            "high",
            "low",
            "vp",
            "no_data",
            "backfilling",
        }
        # R2:ticks 是數千筆,50 檔一起送等於把 batch 端點變成頻寬炸彈
        assert "ticks" not in snap
        assert snap["vwap"] == 2_380_000
        assert snap["vp"] == {"2380000": [1, 1, 0]}
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

        全量那份會把當日數千筆 tick 逐筆組成 dict 再整份丟掉 —— 50 檔 × 每 60s。
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
        # 空 payload 的加鍵一律「不可得」而不是漏鍵(`_EMPTY_LIGHT` 由 light_snapshot()
        # 自己產,鍵集合跟著它走 —— 手抄一份字面 dict 就是下一個會漂的地方)
        assert snap == {
            "minutes": {},
            "meta": None,
            "vwap": None,
            "high": None,
            "low": None,
            "vp": {},
            "no_data": True,
            "backfilling": False,
        }
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


# ---- 回補(backfill)主題索引(next-time 08-31:六 class 散在 3800 行檔,先聚在一起)----
# TestBackfillGuard(檔頭:design v3 R12 事前標記該變的斷言)→ 本節 TestBackfillTimeoutRetry /
# TestFirstTickEnqueuesBackfill / TestBackfillBatchPrepare / TestBackfillFailureIsolation →
# TestWatchlistRemovalBookkeeping(自選移除時 `_backfilled` / `_tick_armed` 記帳清理;#154 把
# `_tick_armed` 兩條鏡射測試補在那裡)。整併原則:同一個記帳集合的邊界測試放同一 class,不動斷言。


class TestBackfillTimeoutRetry:
    """回補逾時的處置與 TC4 斷線不同:不打 `tc4 down`、不計失敗、有界重排。"""

    async def test_timeout_reenqueues_without_touching_tc4_status(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(stock_engine_mod, "_BACKFILL_TIMEOUT_RETRY_SECS", 0.01)
        engine, src = await _make()
        from copycat.live.stock_models import StockTick

        src.backfill_errors = [HistoryTimeoutError("first page not ready")]
        src.backfill_result = [
            StockTick(code="2330", price_milli=2_400_000, qty=3, cum_vol=3,
                      time="09:01:00.000", trade_date="2026-07-21", side="outer",
                      is_trial=False)
        ]
        await engine.set_main("2330")
        await wait_until(lambda: src.backfills.count("2330") >= 1)
        # 主圖逾時**不得**打成 tc4 down(達錢 4 好得很,只是這一檔首頁還沒備妥)
        assert engine.tc4_status != "down"
        assert engine._backfill_failed.get("2330", 0) == 0
        # 等**終態**(分鐘套用進去了)而不是等固定圈數 —— `backfills` 是進場時記的
        await wait_until(lambda: "541" in engine.snapshot("2330")["minutes"])
        assert src.backfills.count("2330") == 2  # 重排且第二發成功
        assert engine.snapshot("2330")["minutes"]["541"]["c"] == 2_400_000
        await engine.close()

    async def test_retry_is_bounded_then_gives_up(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(stock_engine_mod, "_BACKFILL_TIMEOUT_RETRY_SECS", 0.01)
        engine, src = await _make()
        src.backfill_error = HistoryTimeoutError("first page not ready")
        with caplog.at_level(logging.WARNING):
            await engine.set_main("2330")
            await wait_until(lambda: src.backfills.count("2330") == 3)
            await asyncio.sleep(0.05)  # 退避已是 0.01s → 這段足夠讓第 4 發(若有)現形
            await _drain(engine)
        # 首發 + 2 次重試 = 3 次;沒有上界的話這裡會一路長下去
        assert src.backfills.count("2330") == 3
        assert engine.tc4_status != "down"
        assert "放棄" in caplog.text
        await engine.close()

    async def test_release_cancels_pending_timeout_retry_and_clears_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """2026-08-22 review R8 P2:退訂 / 主圖切走必須取消該 code 在途的逾時重排 timer、
        清掉逾時記帳。留著的話 (a) 孤兒 timer 醒來對已 release 的 code 發 SubHistory、成功後
        `_backfilled.add` 把剛清掉的記帳寫回(原註解「秒級殘留窗」變成 15s+ 且可發生兩次);
        (b) 重新訂閱時重試預算已被吃掉,與「訂閱期為界」的記帳語意相反。"""
        monkeypatch.setattr(stock_engine_mod, "_BACKFILL_TIMEOUT_RETRY_SECS", 5.0)
        engine, src = await _make()
        src.backfill_error = HistoryTimeoutError("first page not ready")
        await engine.set_main("2330")
        await wait_until(lambda: "2330" in engine._backfill_timeout_handles)
        assert engine._backfill_timeouts.get("2330") == 1
        handle = engine._backfill_timeout_handles["2330"]
        await engine.set_main("2317")  # 2330 無其他 owner → 真退訂
        assert "2330" not in engine._backfill_timeout_handles
        assert handle.cancelled()
        assert "2330" not in engine._backfill_timeouts
        # 自選路徑:主圖 + 自選共同持有 → 主圖切走**不**釋放(記帳歸還在的 owner),
        # 移出自選才真退訂 → 此時才取消
        await engine.set_main("2330")
        await engine.set_watchlist(["2330"])
        await wait_until(lambda: "2330" in engine._backfill_timeout_handles)
        handle = engine._backfill_timeout_handles["2330"]
        await engine.set_main("2317")
        assert "2330" in engine._backfill_timeout_handles and not handle.cancelled()
        await engine.set_watchlist([])
        assert "2330" not in engine._backfill_timeout_handles
        assert handle.cancelled()
        assert "2330" not in engine._backfill_timeouts
        await engine.close()

    async def test_timeout_after_release_does_not_rearm_or_bookkeep(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """2026-08-22 review round-2 P2:release 時已在佇列 / 正跑的 job 之後逾時,worker 不得
        替一支**已無 owner** 的 code 記逾時帳、武裝新 timer(15s 後再打 TC4 → 再逾時 → 終局
        `_backfilled.add` 把 release 清掉的記帳寫回)。判準 = `_refs`(訂閱池唯一真相)。"""
        import threading

        monkeypatch.setattr(stock_engine_mod, "_BACKFILL_TIMEOUT_RETRY_SECS", 5.0)
        engine, src = await _make()
        gate = threading.Event()

        def slow_backfill(code: str) -> list[object]:
            gate.wait(2.0)
            raise HistoryTimeoutError("first page not ready")

        monkeypatch.setattr(src, "backfill", slow_backfill)
        await engine.set_main("2330")
        await wait_until(lambda: engine._backfilling == "2330")  # job 正跑著
        await engine.set_main("2317")  # 2330 真退訂
        gate.set()
        await wait_until(lambda: engine._backfilling != "2330")
        await _drain(engine)
        assert "2330" not in engine._backfill_timeout_handles
        assert "2330" not in engine._backfill_timeouts
        assert "2330" not in engine._backfilled
        await engine.close()

    async def test_give_up_stops_group_snapshot_from_reenqueueing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """放棄 = **當日不再入列**(與舊行為同),而 `group_snapshot` 也是入列點之一。

        逾時記帳(`_backfill_timeouts`)與失敗記帳分帳的代價:`group_snapshot` 那條
        60s 輪詢的四道 guard 一條都看不到它。放棄後不進 `_backfilled` 的話,輪詢會
        每 60s 把同一檔重新推回 worker —— 重試上界形同虛設,而 TC4 的歷史通道是全站
        共用的稀缺資源(整個群組檢視都排在後面)。
        """
        monkeypatch.setattr(stock_engine_mod, "_BACKFILL_TIMEOUT_RETRY_SECS", 0.01)
        engine, src = await _make()
        src.backfill_error = HistoryTimeoutError("first page not ready")
        await engine.set_watchlist(["2330"])  # 進訂閱池(group_snapshot 的第一道 guard)
        expected = 1 + stock_engine_mod._BACKFILL_TIMEOUT_MAX_RETRIES
        for _ in range(6):
            engine.group_snapshot(["2330"])
            await asyncio.sleep(0.03)
            await _drain(engine)
        assert src.backfills.count("2330") == expected
        await engine.close()

    async def test_close_cancels_the_pending_timeout_reenqueue(self) -> None:
        """`loop.call_later` 的 handle 必須有取消點:關機後醒來的那一發會對已關閉的
        engine 入列(`_backfill_pending` 起帳、job 進佇列而 worker 已死),測試環境下
        則是 loop 已關而 callback 還在排程表上。"""
        engine, src = await _make()
        src.backfill_error = HistoryTimeoutError("first page not ready")
        await engine.set_main("2330")
        await wait_until(lambda: bool(engine._backfill_timeout_handles))
        handles = list(engine._backfill_timeout_handles.values())
        await engine.close()
        assert handles and all(h.cancelled() for h in handles)
        assert not engine._backfill_timeout_handles

    async def test_rollover_cancels_the_pending_timeout_reenqueue(self) -> None:
        """換日 = 日別記帳重來(`_backfill_timeouts` 已在 stage2 清空)。留著昨天排的
        那一發 handle,它醒來時會用**新一天**的 generation 重新入列一筆沒有人要的 job,
        而 stage2 自己已經替主圖排過一筆了。"""
        engine, src = await _make()
        src.backfill_error = HistoryTimeoutError("first page not ready")
        await engine.set_main("2330")
        await wait_until(lambda: bool(engine._backfill_timeout_handles))
        handles = list(engine._backfill_timeout_handles.values())
        engine.rollover_stage1("2026-07-22")
        assert src.on_message is not None
        src.on_message(_quote(cum=50, date="20260722"))  # 首筆新日 tick → stage2
        await _drain(engine)
        assert all(h.cancelled() for h in handles)
        await engine.close()

    async def test_rollover_clears_the_timeout_ledger(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`_backfill_timeouts` 是**日別**記帳:換日後那一檔要重新有完整的重試預算。

        不清的話計數永久停在上限 —— 昨天忙窗逾時放棄的檔,今天第一次逾時就直接放棄
        (零重試),而它的分時圖整天空著、log 只有一行「已重試 2 次」讀起來像真的試過。
        """
        monkeypatch.setattr(stock_engine_mod, "_BACKFILL_TIMEOUT_RETRY_SECS", 0.01)
        engine, src = await _make()
        src.backfill_error = HistoryTimeoutError("first page not ready")
        await engine.set_main("2330")
        await wait_until(lambda: src.backfills.count("2330") == 3)  # 首發 + 2 重試 → 放棄
        before = src.backfills.count("2330")
        engine.rollover_stage1("2026-07-22")
        assert src.on_message is not None
        src.on_message(_quote(cum=50, date="20260722"))  # 首筆新日 tick → stage2
        # 記帳沒清的話 stage2 排的那一發會**當場**放棄(+1 就到頂),等不到 +3
        await wait_until(lambda: src.backfills.count("2330") >= before + 3)
        await engine.close()


class TestFirstTickEnqueuesBackfill:
    """perf/opening-backfill-parallel S2(🔴):自選成員**首筆當日成交 tick** 即入列回補。

    舊入列點全是需求驅動(set_main / 群組檢視 60 s 輪詢 / rollover 主圖 / reconnect 主圖 /
    漲跌停值變),08-28 開盤 09:00→09:02 零回補,直到 user 打開群組檢視。改「訂閱當下
    入列」不行:08:14 開站對 TC4 建當日 TICKS 歷史訂閱只會 30 s 逾時 ×3 再「放棄」
    (08-28 主圖 6207 實錄),40 檔就是 20 分鐘的必敗 REQ;首筆成交才是「TC4 有東西可補」
    的正面訊號,薄股沒成交就不會去卡住單工 worker。
    """

    async def test_first_day_tick_of_a_watchlist_member_enqueues_once(self) -> None:
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        await _drain(engine)
        assert src.backfills == []  # 訂閱本身不入列(前提)
        assert src.on_message is not None
        src.on_message(_quote(cum=1))
        await _drain(engine)
        assert src.backfills == ["2330"]
        src.on_message(_quote(cum=2))  # 第二筆:今日已回補 → 不重入列
        await _drain(engine)
        assert src.backfills == ["2330"]
        await engine.close()

    async def test_book_only_update_does_not_enqueue(self) -> None:
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        src.on_message(_quote(cum=0, qty="0"))  # 純簿更新,無成交
        # 先錨「那則報價真的被處理過」(meta 落地),否定斷言才不是永久假綠(pr-153 F-09)
        await wait_until(lambda: engine._states["2330"].meta is not None)
        assert src.backfills == []
        await engine.close()

    async def test_trial_window_tick_does_not_enqueue(self) -> None:
        """08:30–09:00 試撮成交帶 `is_trial=True`(`parse_stock_realtime` 標旗標、**不丟棄**),
        由 `_handle_quote` 的 `not tick.is_trial` 擋下入列:盤前對 TC4 發當日 TICKS 歷史只會
        逾時(無資料),入列等於替每一檔排 30 s 的必敗等待。"""
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        src.on_message(_quote(cum=1, precise="003500000000"))  # UTC 00:35 = 台北 08:35
        await wait_until(lambda: engine._states["2330"].meta is not None)  # 報價確實處理過
        assert src.backfills == []
        await engine.close()

    async def test_fires_at_most_once_per_subscription_period(self) -> None:
        """review F-2:tick 節拍是次秒級,不是 group_snapshot 的 60 s。逾時 settle 後
        下一筆 tick 若立刻重排,15 s 退避與 2 次上限會在毫秒內燒完 → 「放棄」→ 該檔
        當日不再回補。首筆只點火一次,之後的重試交原本的 timer / 60 s 輪詢。"""
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        src.backfill_errors = [HistoryTimeoutError("首頁未備妥")]
        src.on_message(_quote(cum=1))
        await _drain(engine)
        assert src.backfills == ["2330"]
        assert "2330" in engine._backfill_timeout_handles  # 15 s timer 已武裝
        src.on_message(_quote(cum=2))  # 逾時 settle 後的下一筆:不重排
        src.on_message(_quote(cum=3))
        await _drain(engine)
        assert src.backfills == ["2330"]
        assert engine._backfill_timeouts == {"2330": 1}  # 重試預算沒被 tick 燒掉
        await engine.close()

    async def test_reconnect_rearms_the_first_tick_trigger(self) -> None:
        """reconnect 清 `_backfilled` 之後,成員靠重連後的首筆成交再補一次(斷線缺口)。"""
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        src.on_message(_quote(cum=1))
        await _drain(engine)
        assert src.backfills == ["2330"]
        assert src.on_reconnect is not None
        src.on_reconnect()  # 走真回呼路徑(threadsafe → loop),與檔內其餘 reconnect 測試同款
        src.on_message(_quote(cum=2))
        await _drain(engine)
        assert src.backfills == ["2330", "2330"]
        await engine.close()

    async def test_member_connection_error_rearms_the_first_tick_trigger(self) -> None:
        """pr-153 F-01:成員回補走 ConnectionError 分支後要能靠下一筆成交再點火。

        那條路只 `_backfill_failed += 1`、不設 `_backfilled`、也不武裝 timer;點火權若在
        `_backfill_wanted` 之前就用掉,開盤 TC4 抖一下 → 40 檔各 fails=1,tick 通道整天不再
        點火,又退回等群組檢視 60 s 輪詢。預算由 `_BACKFILL_MAX_FAILS` 封口:每次重排都先付
        一次真失敗 REQ,第 3 次失敗後 `_backfill_wanted` 自然擋下 —— 不會重演 F-2 的毫秒燒盡。
        """
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        src.backfill_errors = [ConnectionError("x"), ConnectionError("x"), ConnectionError("x")]
        for cum in (1, 2, 3, 4):
            src.on_message(_quote(cum=cum))
            await _drain(engine)
        # 三次失敗各由一筆成交點火,第 4 筆被冷卻擋下
        assert src.backfills == ["2330", "2330", "2330"]
        assert engine._backfill_failed == {"2330": 3}
        assert engine.tc4_status == "up"  # 成員失敗不打全站 status
        await engine.close()

    async def test_member_unexpected_error_rearms_the_first_tick_trigger(self) -> None:
        """F-01 的另一半(review round 1 F-D):`except Exception`(壞電文 JSONDecodeError 等)
        同樣不設 `_backfilled`、不武裝 timer、只 `_backfill_failed += 1` —— 點火權要一樣還回,
        否則收割端一則壞電文就讓該檔當日 tick 通道死掉。"""
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        src.backfill_errors = [RuntimeError("bad payload")]
        src.on_message(_quote(cum=1))
        await _drain(engine)
        assert src.backfills == ["2330"]
        src.on_message(_quote(cum=2))
        await _drain(engine)
        assert src.backfills == ["2330", "2330"]  # 下一筆成交再點火一次
        assert engine.tc4_status == "up"
        await engine.close()

    async def test_main_is_left_to_its_own_enqueue_points(self) -> None:
        """review F-3:主圖失敗會把全站 tc4_status 打 down;主圖已有 set_main / rollover /
        reconnect 三個入列點,tick 這條不再多排一次。"""
        engine, src = await _make()
        src.backfill_error = ConnectionError("SubHistory fail")
        await engine.set_main("2330")
        await _drain(engine)
        assert src.backfills == ["2330"]
        assert engine.tc4_status == "down"
        engine.tc4_status = "up"
        assert src.on_message is not None
        src.on_message(_quote(cum=1))  # 主圖首筆:漲跌停 None→有值那條會排(既有 A6-5)
        await _drain(engine)
        assert src.backfills == ["2330", "2330"]  # 只有 set_main + A6-5 那兩排,tick 路徑沒插手
        assert engine._tick_armed == set()  # 主圖永不武裝(pr-153 F-03:浮動基準量不到這件事)
        engine.tc4_status = "up"
        src.on_message(_quote(cum=2))  # 之後的 tick:不再由 tick 路徑排
        await _drain(engine)
        assert src.backfills == ["2330", "2330"]
        assert engine.tc4_status == "up"
        await engine.close()

    async def test_in_flight_job_is_not_doubled(self) -> None:
        """在途 dedup 與 `group_snapshot` 同一把尺(`_backfill_wanted`)。用成員不用主圖:
        主圖的首則 REALTIME 本來就會經「漲跌停 None → 有值」再排一次(既有設計,A6-5)。"""
        engine, src = await _make()
        src.backfill_gate = threading.Event()
        await engine.set_watchlist(["2330"])
        engine.group_snapshot(["2330"])  # 群組檢視已入列(在途,卡在 gate)
        await _drain(engine)
        assert src.on_message is not None
        src.on_message(_quote(cum=1))
        src.backfill_gate.set()
        await _drain(engine)
        assert src.backfills == ["2330"]
        await engine.close()


class TestBackfillBatchPrepare:
    """perf/opening-backfill-parallel S1-b:worker 出隊時把佇列裡**整批**先交給 source
    `prepare_backfill`(= 對全部先 SubHistory,TXO `fetch_backfill` 樣板),再逐檔收割。

    單工逐檔「Sub → 等首頁 → 收」讓每檔各付一次 TC4 備資料的等待;先全訂讓 TC4 平行備,
    輪到第 2 檔起首頁多半已備妥(probe 08-28:20 檔 serial 23.3 s → 批次 3.3 s)。
    """

    async def test_worker_prepares_the_whole_queued_batch_before_harvesting(self) -> None:
        engine, src = await _make()
        codes = ["2330", "2317", "2454", "3008"]
        await engine.set_watchlist(codes)
        src.backfill_gate = threading.Event()  # 把第一檔卡在收割中,趁機驗「整批早已 Sub 完」
        engine.group_snapshot(codes)  # 四筆同時入列(群組檢視的入列點)
        await wait_until(lambda: src.backfills == ["2330"])  # 第一檔正在收割
        assert src.prepares == [codes], src.prepares  # …整批在第一檔收割前就 Sub 完(pr-153 F-02)
        src.backfill_gate.set()
        await _drain(engine)
        assert src.backfills == codes  # 收割順序 = 入列順序(單工語意不變)
        assert src.prepares == [codes]
        await engine.close()

    async def test_single_job_is_not_prepared_separately(self) -> None:
        """單筆 job 不多發一次 SubHistory:backfill 自己就會 Sub,多發一次是純代價。"""
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        engine.group_snapshot(["2330"])
        await _drain(engine)
        assert src.backfills == ["2330"]
        assert src.prepares == []
        await engine.close()

    async def test_prepare_failure_does_not_kill_the_worker(self) -> None:
        """review F-1/H1:prepare 逸出例外 = 整條 worker 靜默死亡、當日回補全失效。
        prepare 只是預熱,失敗交逐檔 `backfill` 自己去撞(那條路的處置齊全)。"""
        engine, src = await _make()
        codes = ["2330", "2317", "2454"]
        await engine.set_watchlist(codes)
        src.prepare_error = ConnectionError("TC4 quote not connected")
        engine.group_snapshot(codes)
        await _drain(engine)
        assert src.prepares == [codes]
        assert src.backfills == codes  # worker 活著,逐檔照跑
        assert engine._backfill_pending == {}
        src.prepare_error = RuntimeError("壞電文")  # 非連線類同樣不得殺死 worker(CR4)
        engine._backfilled.clear()
        engine.group_snapshot(codes)
        await _drain(engine)
        assert src.backfills == codes * 2
        await engine.close()

    async def test_batch_is_deduplicated_before_prepare(self) -> None:
        """review J2:同批同 code 只 Sub 一次。

        批次要有**兩個**不同 code 才觀測得到去重(單 code 批次塌成 1 → 走「單筆不 prepare」,
        測到的不是去重;pr-153 F-07)。重複 job 自 fix/backfill-enqueue-trio(L69)起
        改由唯一接點 `_enqueue_backfill` 直造 —— set_main 已有已回補 / 在途 guard,
        但漲跌停值變 / 逾時重排 timer 等入列點仍可能與 group_snapshot 併發出同 code job。
        """
        engine, src = await _make()
        src.backfill_gate = threading.Event()
        await engine.set_watchlist(["2330", "2317", "2454"])
        engine.group_snapshot(["2330"])
        await _drain(engine)  # 2330 卡在 gate
        engine.group_snapshot(["2317"])
        engine._enqueue_backfill("2317")  # 與 group_snapshot 併發的第二筆同 code job
        engine.group_snapshot(["2454"])
        src.backfill_gate.set()
        await _drain(engine)
        # 去重壞掉會是 [["2317","2317","2454"]]
        assert src.prepares == [["2317", "2454"]], src.prepares
        assert src.backfills == ["2330", "2317", "2317", "2454"]  # 批次組成:兩筆 2317 job 都存在
        await engine.close()

    async def test_stale_generation_jobs_are_settled_and_not_prepared(self) -> None:
        """出隊整批裡的過期 job(rollover 換代)照舊丟棄結清,不進 prepare 批次。"""
        engine, src = await _make()
        src.backfill_gate = threading.Event()  # 讓 worker 卡在第一筆,後面的排在佇列裡
        await engine.set_watchlist(["2330", "2317", "2454"])
        engine.group_snapshot(["2330"])
        await _drain(engine)  # worker 取走 2330,卡在 gate
        engine.group_snapshot(["2317", "2454"])
        engine._generation += 1  # 佇列裡那兩筆過期
        src.backfill_gate.set()
        await _drain(engine)
        assert src.backfills == ["2330"]
        assert src.prepares == []
        assert engine._backfill_pending == {}
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
        await wait_until(lambda: len(src.attempts) > len(codes))  # 重試迴圈確實已在跑
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
        await wait_until(lambda: "2330" in engine._failed_resubs)
        src.fail_subscribe.difference_update({"2330", "F:CDF"})  # 9999 仍恆失敗
        await wait_until(
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


class TestWatchlistSeq:
    """X-3:`seq` = last-writer-wins 的定序尺。

    service 把訂閱移到鎖外之後,兩個並發 commit 可能以任意順序抵達 engine。舊名單
    後到時若照套,訂閱池 / hub membership / 種子廣播會**一起**退回上一版,而畫面上
    只是「剛加的股票又不見了」,沒有任何錯誤訊號。
    """

    async def test_stale_seq_is_skipped_entirely(self) -> None:
        engine, src = await _make()
        hub = FakeHub()
        engine.attach_signal_hub(hub)
        await engine.set_watchlist(["2330"], seq=2)
        subscribed = list(src.subscribed)

        await engine.set_watchlist(["5483"], seq=1)  # 舊名單後到

        assert src.subscribed == subscribed, "舊 seq 用舊名單蓋掉了訂閱池"
        assert src.unsubscribed == [], "舊 seq 把新名單的檔退訂了"
        assert hub.kinds("watchlist") == [("watchlist", ["2330"])]
        await engine.close()

    async def test_newer_seq_applies(self) -> None:
        engine, src = await _make()
        await engine.set_watchlist(["2330"], seq=1)

        await engine.set_watchlist(["5483"], seq=2)

        assert "5483" in src.subscribed
        assert "2330" in src.unsubscribed
        await engine.close()

    async def test_seq_none_does_not_participate(self) -> None:
        """既有 caller / boot 還原不帶 seq → 不參與定序,照舊全套。"""
        engine, src = await _make()
        await engine.set_watchlist(["2330"], seq=5)

        await engine.set_watchlist(["5483"])

        assert "5483" in src.subscribed
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
        tick = _tick_items(got)[0]
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
        assert "F:CDF" not in {item["code"] for item in _tick_items(got)}
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

        **這則 tick 的 `trade_date` 恰為 pending 的 2026-07-22**(UTC 2026-07-21 17:00
        = 台北 07-22 01:00),stage2 的日期條件因此成立 —— 唯一擋住它的防線就是
        `_in_futures_session` 的整則早退。刻意不寫 `date="20260722"`:那會讓
        `_taipei_time` 推成台北 07-23,日期條件先斷,session gate 根本沒被執行到
        (測試照樣綠,但驗的是別條路)。
        """
        engine, src = await _make()
        await engine.set_main_contract(_CONTRACT)
        engine.rollover_stage1("2026-07-22")
        assert src.on_message is not None
        # 台北次日 01:00(夜盤):跨午夜的日期比日盤主圖早一天到
        src.on_message(_fut_quote(cum=1, precise="170000000000"))
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
        assert any(item["code"] == _CONTRACT for item in _tick_items(got))
        await engine.close()

    async def test_daytime_contract_tick_stage2_resets_the_spot_pool(self) -> None:
        """E-3 放行邊界的**另一半**:合約 tick 完成的 stage2 一樣是全池 reset。

        `_rollover_stage2` 對 `_states` 全部 `reset()` —— 觸發者是誰不影響作用範圍。
        E-3 把觸發資格放寬到日盤合約鍵之後,「合約的 tick 會清掉現貨的當日狀態」
        就成了新的既定行為,且時點從現貨首筆(09:00)提前到期貨開盤(08:45)。
        這是**要的**行為(昨日狀態不該留到新的一天),但它是一條跨 instrument 的
        副作用,寫成合約才不會在下一輪被當成 bug「修掉」。

        同時鎖住 reset 之後現貨側仍然健康:昨日 `_last_cum` 已歸 -1,新日的現貨
        tick 進得來 —— 沒歸零的話 `ingest` 對整個新交易日恆 False(不 apply 不
        推播),而畫面只是空著。
        """
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        await engine.set_main_contract(_CONTRACT)
        assert src.on_message is not None
        src.on_message(_quote(cum=100))  # 昨日(2026-07-21)的現貨狀態
        await _drain(engine)
        assert engine.snapshot("2330")["last"]["cum_vol"] == 100  # 前提:狀態確實有值

        engine.rollover_stage1("2026-07-22")
        # 台北 08:46:期貨日盤已開、現貨要 09:00 才有首筆
        src.on_message(_fut_quote(cum=1, date="20260722", precise="004600000000"))
        await _drain(engine)

        assert engine.trade_date == "2026-07-22"
        assert engine.snapshot("2330")["last"] is None  # 現貨池被 reset
        assert engine.snapshot("2330")["seq"] == 0

        # 新日的現貨首筆(cum 比昨日的 100 小)照樣收得下
        src.on_message(_quote(cum=3, date="20260722"))
        await _drain(engine)
        assert engine.snapshot("2330")["last"]["cum_vol"] == 3
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

    async def test_first_tick_trigger_rearms_after_a_real_unsubscribe(self) -> None:
        """`_tick_armed` 同構(pr-153 F-04):點火記帳隨真退訂作廢。

        不作廢的失效樣態:移除再加回之後首筆成交不再點火,只剩群組檢視 60 s 輪詢救得回來;
        使用者沒開群組檢視就是當日整段缺口,`backfilling` / `no_data` 全 False 零訊號。
        """
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        src.on_message(_quote(cum=1))
        await _drain(engine)
        assert src.backfills.count("2330") == 1
        assert "2330" in engine._tick_armed  # 前提:確實點過火

        await engine.set_watchlist([])  # 真退訂(自選是唯一 owner)
        assert "2330" not in engine._refs
        await engine.set_watchlist(["2330"])  # 重新加回
        src.on_message(_quote(cum=2))
        await _drain(engine)

        assert src.backfills.count("2330") == 2
        await engine.close()

    async def test_first_tick_trigger_rearms_after_a_main_slot_release(self) -> None:
        """F-04 鏡像:真退訂發生在 `set_main` 舊主圖 release 那一份清點時同樣要作廢。

        走「先當成員點火 → 升主圖 → 自選移除(主圖仍持有,不清)→ 主圖切走(真退訂)」:
        只有這條路能讓一個**點過火**的 code 經由主圖槽位真退訂。
        """
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        src.on_message(_quote(cum=1))
        await _drain(engine)
        assert "2330" in engine._tick_armed
        await engine.set_main("2330")
        await engine.set_watchlist([])  # 主圖仍持有 → 不是真退訂
        assert "2330" in engine._refs
        await engine.set_main("5483")  # 主圖切走 → 2330 真退訂(set_main 舊主圖 release 清點)
        await _drain(engine)
        assert "2330" not in engine._refs

        await engine.set_watchlist(["2330"])  # 以成員身分加回(不走 group_snapshot,不入列)
        assert src.backfills.count("2330") == 1  # 前提:首筆點火 1;set_main 已回補不重排(L69)
        src.on_message(_quote(cum=2))
        await _drain(engine)
        assert src.backfills.count("2330") == 2  # 第二次 = 加回後的首筆成交再點火
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

    async def test_backfill_bookkeeping_restarts_after_a_main_slot_release(self) -> None:
        """E-2 的**鏡像路徑**:退訂發生在 `set_main_contract` 的 A7d 區塊時同樣要作廢。

        既有三條全走 `set_watchlist` 的 removed 迴圈,主圖槽位那一份清點沒有任何
        測試蓋到 —— 而「主圖是唯一 owner 的現貨檔,使用者切去合約再切回來」是
        stkfut-contracts 出貨後最日常的一條路(SC-3 的選月切換),不是邊角。

        失效樣態同 E-2:切走那段時間的分鐘缺口整天補不回來,`group_snapshot` 的
        `code not in self._backfilled` 恆假地擋著,而 `backfilling` / `no_data`
        都是 False,卡片零訊號地空著。

        re-acquire 刻意走**自選**而不是切回主圖:`set_main_contract` 尾端對未回補
        檔仍會入列(pr-164 後有去重 guard,但清點沒跑時記帳還在、切回主圖照樣不排;
        清點跑了則兩條路都會排)—— 走自選 + 群組輪詢才對清點與否有鑑別力。
        """
        engine, src = await _make()
        await engine.set_main("2330")
        await _drain(engine)
        assert src.backfills.count("2330") == 1  # 前提:set_main 的入列跑完了
        assert "2330" in engine._backfilled  # 前提:確實記過帳

        await engine.set_main_contract(_CONTRACT)  # 主圖是唯一 owner → 真退訂

        assert "2330" not in engine._refs  # 前提:真的退訂了(不是還有別的 owner)
        assert "2330" not in engine._backfilled
        assert "2330" in src.unsubscribed

        # 重新訂閱 → 回補機會重新開始(入列點走群組輪詢;set_main 有去重 guard,
        # 不拿它當證據,見 docstring)
        await engine.set_watchlist(["2330"])
        engine.group_snapshot(["2330"])
        await _drain(engine)

        assert src.backfills.count("2330") == 2
        assert "2330" in engine._backfilled
        await engine.close()


    async def test_set_main_reenqueues_after_timeout_gave_up(self) -> None:
        """pr-164 F-01:逾時放棄檔記在 `_backfill_gave_up`(當日不再**自動**入列),
        但使用者顯式切主圖必須叫得動 —— 修前借 `_backfilled` 當冷卻,放棄檔連切
        主圖也不重排,唯一救援只剩漲跌停值變那一次。"""
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        engine._backfill_gave_up.add("2330")  # 逾時重試打滿後的放棄記帳
        engine._backfill_timeouts["2330"] = 3
        engine.group_snapshot(["2330"])  # 自動入列路:被放棄冷卻擋住
        await _drain(engine)
        assert src.backfills.count("2330") == 0
        await engine.set_main("2330")  # 顯式切主圖:照樣入列
        await _drain(engine)
        assert src.backfills.count("2330") == 1
        assert "2330" not in engine._backfill_gave_up  # 套用成功 → 冷卻解除
        await engine.close()

    async def test_set_main_enqueues_even_when_no_data_or_fail_cooldown(self) -> None:
        """pr-164 F-04:「no_data / 失敗冷卻**不**下沉到 set_main」是刻意決定
        (`group_snapshot` docstring:被冷卻擋掉會變成主圖整天補不回來)。
        把 set_main 的 guard 順手收斂成 `_backfill_wanted` 看起來像純重構,
        mutation 實證全套照綠 —— 這兩條就是那個紅燈。"""
        engine, src = await _make()
        engine._backfill_failed["2330"] = 99  # 真失敗冷卻打滿
        await engine.set_main("2330")
        await _drain(engine)
        assert src.backfills.count("2330") == 1
        engine._no_data.add("2455")
        await engine.set_main("2455")
        await _drain(engine)
        assert src.backfills.count("2455") == 1
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


# ---- 試撮/緩撮標示(mod/trial-pause-badge 第一段:時間窗版)----

_OBSERVE_PREFIX = "trade-status-observe"


#: `_make_with_clock` 的預設引擎牆鐘(`now_fn`)。2026-07-21 = 週二,與 `trade_date` 同日。
#: 固定住是為了讓日曆判準能寫成「入參 == 這一天」—— 見下方 `is_trading_day` 的理由。
_ENGINE_NOW = _dt.datetime(2026, 7, 21, 9, 0)


async def _make_with_clock(
    monkeypatch: pytest.MonkeyPatch,
    clock: str,
    *,
    throttle: float = 0.01,
    trading_day: bool = True,
    now_fn: Callable[[], _dt.datetime] | None = None,
    disposition: set[str] | None = None,
) -> tuple[StockEngine, FakeSource]:
    """假時鐘**先注入再 `start()`**(D3 amendment R3)。

    `_trial_on` 在 `start()` 內以現貨窗現算播種 —— 晚注入的話第一輪 flush 會看到
    「真實時鐘 → 假時鐘」的假翻轉並補推一輪,否定型斷言(固定時鐘不補推)就永遠假綠。
    注入的是**模組屬性**而非 engine 方法:`_now_taipei_time` 是模組級函式(同
    `_now_taipei_hhmm` 慣例),per-code 的 `_trial_now` 走它。

    `is_trading_day` 顯式注入(test-infra-fix,D4'):試撮旗標接日曆之後,不注入的
    engine 會落到預設 `weekday() < 5` → 整組窗內測試在週末跑就集體轉紅(而它們要測的
    是**窗**,不是日曆)。`trading_day=False` 則是 SC-3 的反向案共用入口。

    **判準吃入參而不是 `lambda _d: trading_day`**(review TQ-5):忽略引數的 stub 讓
    「engine 把哪個日期送進日曆」完全無鎖 —— 把 `self._now_fn().date()` 換成
    `date.today()`、`+1 天`、甚至寫死一個常數,整組測試照樣全綠,而 prod 的失效樣態
    (拿錯的日期去問日曆)正是這一類。改成與 `now_fn` 的日期比對後,兩個方向都咬:
    正例只在日期正確時 True、反例只在日期正確時 False。
    """
    monkeypatch.setattr(stock_engine_mod, "_now_taipei_time", lambda: clock)
    now = now_fn if now_fn is not None else (lambda: _ENGINE_NOW)
    src = FakeSource()
    engine = StockEngine(
        src,
        trade_date="2026-07-21",
        throttle_secs=throttle,
        checkpoint=False,
        is_trading_day=(
            (lambda d: d == now().date()) if trading_day else (lambda d: d != now().date())
        ),
        now_fn=now,
        disposition_codes=(lambda: disposition) if disposition is not None else None,
    )
    await engine.start()
    return engine, src


def _tap(stream) -> tuple[list[dict], asyncio.Task[None]]:
    """背景消費一條 `stream()`,回 (累積清單, task)。

    **不可對同一個 stream 連呼兩次 `_collect`**:那個 helper 靠 `wait_for` 逾時收尾,
    逾時會取消掛在 `anext` 上的 await → async generator 隨之收攤,第二次 `anext` 直接
    `StopAsyncIteration`。窗翻轉要比對「翻轉前 / 翻轉後」兩個階段,得是同一條 stream
    (換一條會重收一輪連線種子,分不出哪一則是補推)。
    """
    got: list[dict] = []

    async def _run() -> None:
        async for msg in stream:
            got.append(msg)

    return got, asyncio.create_task(_run())


async def _untap(task: asyncio.Task[None]) -> None:
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def _observed(caplog: pytest.LogCaptureFixture, level: int) -> list[str]:
    """`trade-status-observe` 前綴的紀錄(R10:蒐證對帳以固定前綴為準)。

    比對前綴而不是「有沒有 WARNING」:parse 層 :215 的值域外 warning 是**同事件的
    另一則**(它管值域、engine 管轉態時序),兩者混在一起數會讓 (c)(e)(f) 那三條
    否定斷言在 parse 那則存在時就紅,而它是該留的。
    """
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno == level and r.getMessage().startswith(_OBSERVE_PREFIX)
    ]


class TestTrialFlag:
    """SC-3:`watchlist_quote` 與 REST snapshot 的 additive `trial: bool`(D1/D2)。

    現算而不落 `StockDayState`:試撮期 TC4 不推成交 tick(實測),tick 路徑萃取不到
    「進窗」事件 —— 掛在狀態機上的話那個旗標永遠不會被翻起來。
    """

    async def test_quote_payload_trial_in_window(self, monkeypatch: pytest.MonkeyPatch) -> None:
        engine, _src = await _make_with_clock(monkeypatch, "08:50:00.000")
        await engine.set_watchlist(["2330"])
        got = await _collect(engine.stream())
        seed = next(m for m in got if m["type"] == "watchlist_quote" and m["code"] == "2330")
        assert seed["trial"] is True
        await engine.close()

    async def test_quote_payload_trial_false_out_of_window(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine, _src = await _make_with_clock(monkeypatch, "10:00:00.000")
        await engine.set_watchlist(["2330"])
        got = await _collect(engine.stream())
        seed = next(m for m in got if m["type"] == "watchlist_quote" and m["code"] == "2330")
        assert seed["trial"] is False
        await engine.close()

    async def test_quote_payload_trial_false_for_futures_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """期貨鍵空窗 → 恆 False(D2),前端因此不必做 per-instrument 判斷。

        走 `_quote_payload` 直呼:合約鍵**永遠不會**產生 `watchlist_quote`(D16),
        公開路徑上沒有第二個觀測點,而這條契約正是前端「不判 instrument」的前提。
        """
        engine, _src = await _make_with_clock(monkeypatch, "08:50:00.000")
        assert engine._quote_payload(_CONTRACT)["trial"] is False
        assert engine._quote_payload("2330")["trial"] is True  # 對照:同一時刻現貨為 True
        await engine.close()

    async def test_snapshot_has_trial(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """附加點在 **engine.snapshot()**(同 `no_data` 慣例),不是 `StockDayState`。"""
        engine, _src = await _make_with_clock(monkeypatch, "13:27:00.000")
        assert engine.snapshot("2330")["trial"] is True
        assert engine.snapshot(_CONTRACT)["trial"] is False
        await engine.close()

    async def test_snapshot_trial_false_out_of_window(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine, _src = await _make_with_clock(monkeypatch, "13:30:00.000")  # 右界不含
        assert engine.snapshot("2330")["trial"] is False
        await engine.close()

    async def test_trade_status_pause_marks_trial_out_of_window(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """L75 第二段:盤中(窗外)TradeStatus==1 = 延緩撮合中 → trial True(per-code)。

        2026-08-28 蒐證:開盤段 11 檔 episode ≈2 min、TWSE「延緩撮合」形狀;窗判只涵蓋
        08:30–09:00 / 13:25–13:30,盤中暴漲暴跌觸發的延緩第一段整段不亮。"""
        engine, src = await _make_with_clock(monkeypatch, "10:30:00.000")
        await engine.set_main("2330")
        assert src.on_message is not None
        src.on_message(_quote(cum=1, status="1"))
        await _drain(engine)
        assert engine.snapshot("2330")["trial"] is True
        assert engine._quote_payload("2330")["trial"] is True
        await engine.close()

    async def test_trade_status_flip_pushes_watchlist_quote_without_tick(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """pr-167 F-01:延緩撮合的定義就是期間沒有成交 tick —— tick 驅動的 dirty 路徑
        整段 episode 不會替這檔發 quote(探針實證 _publish 捕獲 0 則)。TradeStatus
        轉態且改變 `_trial_now` 答案時必須主動補推一則 trial=True 的 watchlist_quote,
        否則「(緩)/(處置)」在單檔頁與側欄整段 episode 都不亮(L75 招牌交付項死路徑)。"""
        engine, src = await _make_with_clock(monkeypatch, "10:30:00.000")
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        src.on_message(_quote(cum=1, status="0"))
        await _drain(engine)
        got, task = _tap(engine.stream())
        await _drain(engine)
        got.clear()  # 丟掉連線種子與 tick 補推,只看轉態那一則
        src.on_message(_quote(cum=1, qty="0", status="1"))  # 純簿更新:延緩期間沒有成交 tick
        await _drain(engine)
        flips = [m for m in got if m["type"] == "watchlist_quote" and m["code"] == "2330"]
        assert flips, "TradeStatus 0→1 必須推播(dirty 路徑不會替無成交檔發 quote)"
        assert flips[-1]["trial"] is True
        src.on_message(_quote(cum=1, qty="0", status="0"))  # 恢復(1→0)同樣要熄得掉
        await _drain(engine)
        flips = [m for m in got if m["type"] == "watchlist_quote" and m["code"] == "2330"]
        assert flips[-1]["trial"] is False
        await _untap(task)
        await engine.close()

    async def test_trade_status_recovery_clears_pause(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """恢復推播(1→0,= 延緩後集合撮合那筆)→ trial 熄。"""
        engine, src = await _make_with_clock(monkeypatch, "10:30:00.000")
        await engine.set_main("2330")
        assert src.on_message is not None
        src.on_message(_quote(cum=1, status="1"))
        src.on_message(_quote(cum=2, status="0"))
        await _drain(engine)
        assert engine.snapshot("2330")["trial"] is False
        await engine.close()

    async def test_trade_status_pause_not_honored_after_close(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TradeStatus 只隨 REALTIME 更新:收盤後沒有恢復推播,最後一則若是 1 會把旗標
        掛整晚 —— 盤中 09:00–13:30 之外不採信 per-code 值(窗判那條照走)。"""
        engine, src = await _make_with_clock(monkeypatch, "10:30:00.000")
        await engine.set_main("2330")
        assert src.on_message is not None
        src.on_message(_quote(cum=1, status="1"))
        await _drain(engine)
        import copycat.server.stock_engine as stock_engine_mod

        monkeypatch.setattr(stock_engine_mod, "_now_taipei_time", lambda: "14:10:00.000")
        assert engine.snapshot("2330")["trial"] is False
        await engine.close()

    async def test_disposition_flag_surfaces_on_snapshot_and_quote(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """L75(處置):breadth 處置名單注入 → snapshot / quote payload 帶 disposition,
        前端據此把 trial 的標籤從「(緩)」改「(處置)」(分盤撮合不是暴漲暴跌延緩)。
        未注入(breadth 停用)→ 恆 False = 全部照標(緩)= 降級即現行為。"""
        engine, _src = await _make_with_clock(monkeypatch, "10:30:00.000", disposition={"2330"})
        assert engine.snapshot("2330")["disposition"] is True
        assert engine._quote_payload("2330")["disposition"] is True
        assert engine.snapshot("2317")["disposition"] is False
        assert engine.snapshot(_CONTRACT)["disposition"] is False  # 期貨鍵恆 False
        off, _src2 = await _make_with_clock(monkeypatch, "10:30:00.000")
        assert off.snapshot("2330")["disposition"] is False
        await engine.close()
        await off.close()

    async def test_trial_false_on_non_trading_day(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SC-3(D4'):日曆說今天不開盤 → 窗內也不標(緩)。

        只看窗不看日曆的話,週末 / 國定假日開著的站在 08:30–09:00 會讓全自選一起亮
        「(緩)」—— 那是完全沒有撮合的時段,畫面上是純噪音,還跟後端「非交易日不輪詢」
        的事實直接打架。日曆來源 = engine 既有的 `is_trading_day` 注入(單一來源)。
        """
        engine, _src = await _make_with_clock(monkeypatch, "08:50:00.000", trading_day=False)
        assert engine.snapshot("2330")["trial"] is False  # 對照:同一時鐘交易日為 True
        assert engine._quote_payload("2330")["trial"] is False
        await engine.close()

    async def test_start_seeds_trial_flag_from_calendar_and_window(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """[lock] TQ-3:`start()` 的**播種點**本身要有鎖(D3 amendment R3 的另一半)。

        `throttle=5.0` → flush loop 這一輪絕不會轉到,`_trial_on` 只可能來自 `start()`
        內的現算播種。播種若漏掉日曆(只算窗),休市日的窗內冷啟動會播成 True,而下一輪
        flush 算出 False = 一次**假翻轉**,替全自選補推一輪「(緩)熄掉」的 quote ——
        那天根本沒有撮合,畫面上的兩次轉態全是憑空的,且與真翻轉在 log 上無從分辨。

        既有測試只看得到播種的下游(補推 / payload),把 `start()` 那行改成
        `_spot_trial_window_now()` 或直接刪掉照樣全綠。
        """
        on, _src_on = await _make_with_clock(monkeypatch, "08:50:00.000", throttle=5.0)
        assert on._trial_on is True  # 窗內 + 交易日
        await on.close()
        off, _src_off = await _make_with_clock(
            monkeypatch, "08:50:00.000", throttle=5.0, trading_day=False
        )
        assert off._trial_on is False  # 同一時鐘、同一窗,只差日曆
        await off.close()

    def test_default_is_trading_day_is_weekday_lt_5(self) -> None:
        """[lock] TQ-9(W9):不注入 `is_trading_day` 時的預設判準逐字不變。

        「engine 直接建構的既有 caller 行為不得有一絲變化」這條白名單目前只有 checkpoint
        路徑間接鎖著;預設改成 `lambda _d: True`(或反過來恆 False)在那條測試以外全綠,
        而失效樣態是**測試 / 非 prod 入口**的日曆判定整個翻面。

        不 `start()`:測的是建構期的預設值,起 task 只是多一組要收的資源。
        """
        engine = StockEngine(FakeSource(), trade_date="2026-07-21", checkpoint=False)
        assert engine._is_trading_day(_dt.date(2026, 8, 21)) is True  # 週五
        assert engine._is_trading_day(_dt.date(2026, 8, 22)) is False  # 週六


class TestTrialWindowFlipPush:
    """SC-4:窗邊界翻轉 → 自選各碼 + 現貨主圖碼各補推一則帶新 `trial` 的 quote(D3)。

    掛既有 1s flush loop(不加新 task);**繞過 `state.last is None` 的 skip** ——
    盤前無成交正是要標「(緩)」的時刻,而那條 skip 讓那些檔永遠不進補推路徑。
    """

    async def test_flush_loop_pushes_on_window_flip(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        now = {"t": "08:29:59.000"}
        monkeypatch.setattr(stock_engine_mod, "_now_taipei_time", lambda: now["t"])
        src = FakeSource()
        engine = StockEngine(
            src,
            trade_date="2026-07-21",
            throttle_secs=0.01,
            checkpoint=False,
            # 判準吃入參(review TQ-5):與下方 `test_no_flip_push_on_non_trading_day`
            # 成對 —— 忽略引數的 stub 讓「engine 拿哪個日期去問日曆」完全無鎖。
            is_trading_day=lambda d: d == _ENGINE_NOW.date(),
            now_fn=lambda: _ENGINE_NOW,
        )
        await engine.start()
        await engine.set_watchlist(["2330"])
        await engine.set_main("5483")  # 現貨主圖且**不在自選** + 全程零成交(last is None)
        got, tap = _tap(engine.stream())

        # 假時鐘固定 → 窗 bool 恆定 → 不得補推(否則等於打穿 1s 節流)
        await _drain(engine)
        before = [m for m in got if m["type"] == "watchlist_quote"]
        assert [m["code"] for m in before] == ["2330"], "只該有連線種子那一則"
        assert before[0]["trial"] is False
        mark = len(got)

        now["t"] = "08:30:00.000"  # 進窗
        await _drain(engine)
        after = [m for m in got[mark:] if m["type"] == "watchlist_quote"]

        by_code: dict[str, list[dict]] = {}
        for m in after:
            by_code.setdefault(m["code"], []).append(m)
        assert set(by_code) == {"2330", "5483"}, "自選碼與現貨主圖碼都要收到"
        assert len(by_code["2330"]) == 1  # 一天四次邊界事件,各一則
        assert len(by_code["5483"]) == 1
        assert all(m["trial"] is True for m in after)
        assert engine._states["5483"].last is None  # 前提:這一檔走的是被 skip 的那條路
        await _untap(tap)
        await engine.close()

    async def test_main_in_watchlist_is_pushed_once_on_flip(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """IC-6(1):同一檔既是自選又是現貨主圖 → 補推**一則**(`_trial_flip_targets` 去重)。

        兩則的失效是靜默的:側欄收到重複 quote 不會報錯,只是節流語意開始漂
        (「一天四次邊界事件、每檔各一則」這條上界失守),而去重原本無測試鎖。
        """
        now = {"t": "08:29:59.000"}
        monkeypatch.setattr(stock_engine_mod, "_now_taipei_time", lambda: now["t"])
        src = FakeSource()
        engine = StockEngine(
            src,
            trade_date="2026-07-21",
            throttle_secs=0.01,
            checkpoint=False,
            is_trading_day=lambda _d: True,  # test-infra-fix(D4')
        )
        await engine.start()
        await engine.set_watchlist(["2330"])
        await engine.set_main("2330")  # 第二個 owner:自選 + 主圖
        got, tap = _tap(engine.stream())
        await _drain(engine)
        mark = len(got)

        now["t"] = "08:30:00.000"
        await _drain(engine)
        after = [m for m in got[mark:] if m["type"] == "watchlist_quote"]
        assert [m["code"] for m in after] == ["2330"]
        assert after[0]["trial"] is True
        await _untap(tap)
        await engine.close()

    async def test_futures_main_is_not_pushed_on_flip(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """期貨主圖鍵不推:`trial` 恆 False,推出去是一則側欄對不上任何項目的訊息。"""
        now = {"t": "08:29:59.000"}
        monkeypatch.setattr(stock_engine_mod, "_now_taipei_time", lambda: now["t"])
        src = FakeSource()
        engine = StockEngine(
            src,
            trade_date="2026-07-21",
            throttle_secs=0.01,
            checkpoint=False,
            is_trading_day=lambda _d: True,  # test-infra-fix(D4')
        )
        await engine.start()
        await engine.set_main_contract(_CONTRACT)
        got, tap = _tap(engine.stream())
        await _drain(engine)  # 排空種子與回補 status
        mark = len(got)

        now["t"] = "08:30:00.000"
        await _drain(engine)
        assert [m for m in got[mark:] if m["type"] == "watchlist_quote"] == []
        await _untap(tap)
        await engine.close()

    async def test_no_flip_push_on_non_trading_day(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SC-3(D4'):非交易日跨過窗邊界 → 一則都不補推(旗標恆 False = 根本沒有翻轉)。

        翻轉偵測若只看窗,休市日的 08:30 / 09:00 / 13:25 / 13:30 各會替全自選 + 現貨
        主圖補推一輪 quote —— 那是打穿節流的空推,且畫面上的「(緩)」會在沒有撮合的
        日子亮起又熄掉。
        """
        now = {"t": "08:29:59.000"}
        monkeypatch.setattr(stock_engine_mod, "_now_taipei_time", lambda: now["t"])
        src = FakeSource()
        engine = StockEngine(
            src,
            trade_date="2026-07-21",
            throttle_secs=0.01,
            checkpoint=False,
            # 反例同樣吃入參(review TQ-5):`!=` 讓「engine 送錯日期」翻成 True →
            # 補推真的發生 → 這條紅。恆 False 的 stub 對錯誤日期是沉默的。
            is_trading_day=lambda d: d != _ENGINE_NOW.date(),
            now_fn=lambda: _ENGINE_NOW,
        )
        await engine.start()
        await engine.set_watchlist(["2330"])
        await engine.set_main("5483")
        got, tap = _tap(engine.stream())
        await _drain(engine)
        mark = len(got)

        now["t"] = "08:30:00.000"  # 「進窗」但今天休市
        await _drain(engine)
        assert [m for m in got[mark:] if m["type"] == "watchlist_quote"] == []
        await _untap(tap)
        await engine.close()


class TestTradeStatusObserve:
    """SC-5:engine 層 per-code TradeStatus 轉態觀測 log(D6)= 第二段的蒐證通道。

    「盤中延緩撮合」期間 TradeStatus 的值域 / 起訖 / 恢復**未實測**(2026-07-21 只測到
    13:25–13:30 的 `TradeStatus=1` 簿更新),本輪不據此判定任何狀態,只留可 grep 的紀錄。
    分層理由:窗內轉態是已知常態,全 INFO 會淹沒蒐證訊號;窗外事件即是要抓的 evidence。
    """

    async def test_out_of_window_transition_warns(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """(a) 窗外 "0"→"2" → WARNING 含固定前綴 + code + 兩值。"""
        engine, src = await _make_with_clock(monkeypatch, "10:00:00.000")
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        with caplog.at_level(logging.DEBUG, logger="copycat.server.stock_engine"):
            src.on_message(_quote(cum=1))  # 首見 "0" → 只播種
            await _drain(engine)
            src.on_message(_quote(cum=2) | {"TradeStatus": "2"})
            await _drain(engine)
        warns = _observed(caplog, logging.WARNING)
        assert len(warns) == 1
        assert "code=2330" in warns[0]
        assert "0->2" in warns[0]
        assert "trial_window=False" in warns[0]
        await engine.close()

    async def test_recovery_to_zero_pairs_the_episode(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """(b) 恢復 "2"→"0" 再一則 WARNING(起訖成對 → 蒐證看得出持續多久)。"""
        engine, src = await _make_with_clock(monkeypatch, "10:00:00.000")
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        with caplog.at_level(logging.DEBUG, logger="copycat.server.stock_engine"):
            src.on_message(_quote(cum=1))
            src.on_message(_quote(cum=2) | {"TradeStatus": "2"})
            await _drain(engine)
            src.on_message(_quote(cum=3))  # 回 "0"
            await _drain(engine)
        warns = _observed(caplog, logging.WARNING)
        assert len(warns) == 2
        assert "2->0" in warns[1]
        # episode 已歸 False:下一次回 "0" 不得再記(否則每則常態推播都成對噴)
        with caplog.at_level(logging.DEBUG, logger="copycat.server.stock_engine"):
            src.on_message(_quote(cum=4) | {"TradeStatus": "1"})  # 窗外 "0"→"1" 也是異常
            src.on_message(_quote(cum=5))
            await _drain(engine)
        assert len(_observed(caplog, logging.WARNING)) == 4  # 起 + 訖 各再一則
        await engine.close()

    async def test_in_window_transition_is_debug_only(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """(c) 窗內 "0"→"1" = 已知常態 → DEBUG,不得進 WARNING。"""
        engine, src = await _make_with_clock(monkeypatch, "08:50:00.000")
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        with caplog.at_level(logging.DEBUG, logger="copycat.server.stock_engine"):
            src.on_message(_quote(cum=1))
            src.on_message(_quote(cum=2) | {"TradeStatus": "1"})
            await _drain(engine)
        assert _observed(caplog, logging.WARNING) == []
        debugs = _observed(caplog, logging.DEBUG)
        assert len(debugs) == 1
        assert "0->1" in debugs[0]
        assert "trial_window=True" in debugs[0]
        await engine.close()

    async def test_same_value_is_never_logged_twice(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """(d) 同值連續推播不重複記(每則 REALTIME 都記 = 蒐證檔被灌爆)。"""
        engine, src = await _make_with_clock(monkeypatch, "10:00:00.000")
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        with caplog.at_level(logging.DEBUG, logger="copycat.server.stock_engine"):
            src.on_message(_quote(cum=1))
            src.on_message(_quote(cum=2) | {"TradeStatus": "2"})
            src.on_message(_quote(cum=3) | {"TradeStatus": "2"})
            src.on_message(_quote(cum=4) | {"TradeStatus": "2"})
            await _drain(engine)
        assert len(_observed(caplog, logging.WARNING)) == 1
        assert _observed(caplog, logging.DEBUG) == []
        await engine.close()

    async def test_observe_window_is_pure_window_on_non_trading_day(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """[lock] TQ-6:休市日窗內轉態 —— observe 仍記 `trial_window=True` 的 DEBUG,
        而同一時刻 payload 的 `trial` 是 **False**。

        兩者刻意不同源(D4' / `_observe_window_now` docstring):payload 那顆要接日曆
        (休市日不該亮「(緩)」),觀測這顆是**純窗**(把日曆 AND 進來,休市日的窗內
        事件會被整段降級成「窗外」→ 全部升 WARNING,蒐證檔被自己的分級淹掉)。

        這條契約原本只寫在 docstring 裡:把 `_observe_window_now()` 改成
        `self._spot_trial_now()` 全組測試照綠(其餘 case 的日曆恆為交易日,兩者同值)。
        一個 assert 同時釘住兩邊的值,兩者被合併成同一顆時鐘就必紅。
        """
        engine, src = await _make_with_clock(monkeypatch, "08:50:00.000", trading_day=False)
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        with caplog.at_level(logging.DEBUG, logger="copycat.server.stock_engine"):
            src.on_message(_quote(cum=1))  # 首見 "0" → 只播種
            src.on_message(_quote(cum=2) | {"TradeStatus": "1"})
            await _drain(engine)
        assert _observed(caplog, logging.WARNING) == []
        debugs = _observed(caplog, logging.DEBUG)
        assert len(debugs) == 1
        assert "0->1" in debugs[0]
        assert "trial_window=True" in debugs[0]  # 純窗:休市日照樣 True
        assert engine._quote_payload("2330")["trial"] is False  # 對照:wire 上不亮
        await engine.close()

    async def test_observe_skips_futures_key(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """(e) 期貨鍵零觀測(R1):空窗讓 `is_trial_window` 恆 False,任何轉態都會
        誤落「窗外」分支 → 個股期整天噴假的蒐證 WARNING,把真訊號淹掉。"""
        engine, src = await _make_with_clock(monkeypatch, "10:00:00.000")
        await engine.set_main_contract(_CONTRACT)
        assert src.on_message is not None
        with caplog.at_level(logging.DEBUG, logger="copycat.server.stock_engine"):
            src.on_message(_fut_quote(cum=1))
            src.on_message(_fut_quote(cum=2) | {"TradeStatus": "2"})
            await _drain(engine)
        assert _observed(caplog, logging.WARNING) == []
        assert _observed(caplog, logging.DEBUG) == []
        assert engine._trade_status == {}  # 連前值都不播種
        await engine.close()

    async def test_first_seen_only_seeds_when_zero_or_in_window(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """(f) [IC-1 改寫,原「首見一律零記錄」assertion 已由 spec SC-5(f) 宣告該變]
        首見 "0"(任何時刻)與首見非 "0" **且在觀測窗內** → 零記錄僅播種。

        窗內那半條是對 IC-1 建議的收窄:冷啟動落在 13:25–13:30 時 255 檔齊帶 "1"
        (2026-07-21 實測那五分鐘的常態值),齊噴等於把蒐證檔灌爆。
        """
        engine, src = await _make_with_clock(monkeypatch, "08:50:00.000")
        await engine.set_watchlist(["2330", "5483"])
        assert src.on_message is not None
        with caplog.at_level(logging.DEBUG, logger="copycat.server.stock_engine"):
            src.on_message(_quote(cum=1) | {"TradeStatus": "1"})  # 首見非 "0" 但窗內
            src.on_message(_quote(code="5483", cum=1))  # 首見 "0"
            await _drain(engine)
        assert _observed(caplog, logging.WARNING) == []
        assert _observed(caplog, logging.DEBUG) == []
        assert engine._trade_status["2330"] == ("1", False)
        assert engine._trade_status["5483"] == ("0", False)
        await engine.close()

    async def test_first_seen_non_zero_out_of_window_warns(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """(f) [IC-1] 首見非 "0" 且觀測窗外 → 一則 WARNING 帶 `first_seen=1` + episode 武裝。

        這是**最可能的取樣路徑**:盤中暴漲暴跌觸發延緩撮合之後使用者才把那一檔加進
        自選(或才開頁),訂閱當下第一則就已經是非 "0" —— 舊規則的「首見一律播種」
        會讓整段 episode(起 + 訖)完全靜默,而蒐證看起來只是「那天沒抓到樣本」。
        """
        engine, src = await _make_with_clock(monkeypatch, "10:00:00.000")
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        with caplog.at_level(logging.DEBUG, logger="copycat.server.stock_engine"):
            src.on_message(_quote(cum=1) | {"TradeStatus": "2"})
            await _drain(engine)
        warns = _observed(caplog, logging.WARNING)
        assert len(warns) == 1
        assert "code=2330" in warns[0]
        assert "first_seen=1" in warns[0]  # 與正常轉態可辨(前值不明,不能假裝是 "0"→"2")
        assert "trial_window=False" in warns[0]
        assert engine._trade_status["2330"] == ("2", True)  # episode 武裝 → 恢復要記
        with caplog.at_level(logging.DEBUG, logger="copycat.server.stock_engine"):
            src.on_message(_quote(cum=2))  # 回 "0"
            await _drain(engine)
        warns = _observed(caplog, logging.WARNING)
        assert len(warns) == 2  # 起訖成對 → 蒐證看得出持續多久
        assert "2->0" in warns[1]
        await engine.close()

    async def test_missing_qty_field_logs_dash(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """IC-6(2):`TradeQuantity` 缺欄 → `qty=-`(與真的 `qty=0` 可辨)。

        純簿更新(延緩撮合期間最常見的推播形)缺 qty,印空字串會讓蒐證檔出現
        `qty=` 這種讀不出是「沒有這一欄」還是「零成交」的紀錄。
        """
        engine, src = await _make_with_clock(monkeypatch, "10:00:00.000")
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        book_only = _quote(cum=1) | {"TradeStatus": "2"}
        book_only.pop("TradeQuantity")
        with caplog.at_level(logging.DEBUG, logger="copycat.server.stock_engine"):
            src.on_message(book_only)
            await _drain(engine)
        warns = _observed(caplog, logging.WARNING)
        assert len(warns) == 1
        assert "qty=-" in warns[0]
        await engine.close()

    async def test_observe_window_has_two_second_grace(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """D6-1:觀測分級走**觀測專用窗**(TRIAL_WINDOWS 兩端各放寬 2s)。

        本機時鐘與 TC4 時戳的秒級偏移會把 13:25:00 進窗的 0→1 判成「窗外非 0」→
        每檔每日最多一對假 WARNING(進窗一則、出窗一則)淹沒真訊號。
        寬限**只影響觀測分級**:payload 的 `trial` 窗判仍是原窗(L75 起另有 per-code
        TradeStatus 分支,由本測試尾兩行分開鎖),否則畫面的「(緩)」會早亮晚熄。
        """
        engine, src = await _make_with_clock(monkeypatch, "13:24:59.000")
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        with caplog.at_level(logging.DEBUG, logger="copycat.server.stock_engine"):
            src.on_message(_quote(cum=1))  # 首見 "0"
            src.on_message(_quote(cum=2) | {"TradeStatus": "1"})
            await _drain(engine)
        assert _observed(caplog, logging.WARNING) == []
        debugs = _observed(caplog, logging.DEBUG)
        assert len(debugs) == 1
        assert "trial_window=True" in debugs[0]  # 觀測窗的答案
        # 事前標為該變(L75 第二段):TradeStatus==1 當下 wire trial=True 是新語意
        # (per-code 延緩撮合偵測,不再只看窗)。原鎖「觀測 ±2s 寬限不得漏進 wire 窗判」
        # 改由下面兩行承接:恢復 "0" 之後、13:25 窗前的同一時刻,wire 仍是 False。
        assert engine._quote_payload("2330")["trial"] is True
        src.on_message(_quote(cum=3))  # TradeStatus 恢復 "0"
        await _drain(engine)
        assert engine._quote_payload("2330")["trial"] is False  # wire 契約不吃寬限
        await engine.close()

    async def test_rollover_stage1_clears_trade_status(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """(g) [IC-5] 清空掛 **stage1**:episode 是日內語意。

        只掛 stage2 的話 08:00(checkpoint 武裝)~09:00(新日首筆)整段沿用昨日
        episode 旗標 → 今天第一則帶 "0" 的推播被判成「恢復」,記一則帶**今日時戳**、
        對照**昨日起點**的 WARNING,而它讀起來完全像真事件。
        """
        engine, src = await _make_with_clock(monkeypatch, "10:00:00.000")
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        src.on_message(_quote(cum=1))  # 首見 "0" → 播種
        src.on_message(_quote(cum=2) | {"TradeStatus": "2"})  # 窗外轉態 → episode 武裝
        await _drain(engine)
        assert engine._trade_status["2330"] == ("2", True)  # 前提:有東西可清

        engine.rollover_stage1("2026-07-22")
        assert engine._trade_status == {}

        # `caplog.records` 累積整個 test(`at_level` 只調級別不清空)→ 上面那則武裝用的
        # WARNING 會混進來,而本 case 的斷言是**否定型**(零 WARNING)。
        caplog.clear()
        with caplog.at_level(logging.DEBUG, logger="copycat.server.stock_engine"):
            src.on_message(_quote(cum=3))  # 仍昨日日期 → stage2 未跑;帶 "0"
            await _drain(engine)
        assert engine.trade_date == "2026-07-21"  # 前提:stage2 確實還沒跑
        assert engine._pending_date == "2026-07-22"
        assert _observed(caplog, logging.WARNING) == []  # 不得有假「恢復」
        assert engine._trade_status["2330"] == ("0", False)  # 新日重新播種
        await engine.close()

    async def test_rollover_stage2_clears_trade_status(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """stage2 的清空保留 = 快路徑雙保險(S4 + IC-5)。

        [IC-1/IC-5 附帶:本 case 的前值播種改走「首見 "0" → 轉態」兩則,因為首見非 "0"
        窗外現在會自己記一則;stage1 已先清,所以 stage2 前要重新播種才有東西可清。]

        觀測落點在 stage2 **之前**(期貨夜盤早退之後),所以觸發 stage2 的那一則自己
        仍以舊前值判斷;清空的效果落在**它之後**的每一則:新日重新播種。
        """
        engine, src = await _make_with_clock(monkeypatch, "10:00:00.000")
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        engine.rollover_stage1("2026-07-22")
        src.on_message(_quote(cum=1))  # stage1 後 / stage2 前:重新播種
        await _drain(engine)
        assert engine._trade_status["2330"] == ("0", False)  # 前提:stage2 有東西可清

        src.on_message(_quote(cum=1, date="20260722"))  # 新日首筆 → stage2
        await _drain(engine)
        assert engine.trade_date == "2026-07-22"  # 前提:stage2 真的跑了
        assert engine._trade_status == {}  # 前值不得跨過 stage2

        with caplog.at_level(logging.DEBUG, logger="copycat.server.stock_engine"):
            src.on_message(_quote(cum=2, date="20260722"))
            await _drain(engine)
        # 清空後這一則是新日的「首見 "0"」→ 只播種,不記
        assert engine._trade_status["2330"] == ("0", False)
        assert _observed(caplog, logging.WARNING) == []
        assert _observed(caplog, logging.DEBUG) == []
        await engine.close()

    async def test_trade_status_popped_when_watchlist_drops_last_owner(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """IC-6(3):**真退訂**才清 `_trade_status`(對齊 `_backfilled` 的清帳紀律)。

        不清的話重新訂閱時拿「上一段訂閱期的前值」跟新的第一則比對 = 一則跨訂閱期的
        假轉態;episode 旗標還武裝著時更會生出一則沒有起點的假「恢復」。
        """
        engine, src = await _make_with_clock(monkeypatch, "10:00:00.000")
        await engine.set_watchlist(["2330"])
        assert src.on_message is not None
        src.on_message(_quote(cum=1))
        await _drain(engine)
        assert "2330" in engine._trade_status
        await engine.set_watchlist([])  # last owner 退 → 真退訂
        assert "2330" not in engine._trade_status
        await engine.close()

    async def test_trade_status_kept_while_another_owner_remains(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """還有 owner 時**不清**(同 `_no_data` / `_backfilled` 的條件):訂閱還在,
        前值就還是有效的比較基準 —— 清掉等於白丟一次轉態(下一則變成「首見」)。
        主圖槽位轉移那一處(`set_main_contract`)的真退訂同樣要清。
        """
        engine, src = await _make_with_clock(monkeypatch, "10:00:00.000")
        await engine.set_watchlist(["2330"])
        await engine.set_main("2330")  # 第二個 owner
        assert src.on_message is not None
        src.on_message(_quote(cum=1))
        await _drain(engine)
        await engine.set_watchlist([])  # 仍是主圖 → 不是真退訂
        assert "2330" in engine._trade_status
        await engine.set_main("5483")  # 最後一個 owner 退 → 真退訂
        assert "2330" not in engine._trade_status
        await engine.close()


class TestObserveClockContract:
    """SC-5(h) [IC-2]:`_now_taipei_time` 的**真實實作**(其餘 case 全 monkeypatch 掉它)。

    沒有這兩條的話,把格式簡化成 `HH:MM` 全部測試照綠 —— 而 `is_trial_window` 做的是
    字串比對,`"08:30" < "08:30:00.000"` 恆真 → 進窗那一刻判窗外,badge 永不亮。
    """

    def test_now_taipei_time_format(self) -> None:
        assert re.fullmatch(r"\d{2}:\d{2}:\d{2}\.\d{3}", stock_engine_mod._now_taipei_time())

    @pytest.mark.parametrize(
        "wall,expected",
        [
            (_dt.datetime(2026, 8, 13, 8, 29, 59, 999_000), False),  # 左界前 1ms
            (_dt.datetime(2026, 8, 13, 8, 30, 0, 0), True),  # 左界含
            (_dt.datetime(2026, 8, 13, 8, 59, 59, 999_000), True),
            (_dt.datetime(2026, 8, 13, 9, 0, 0, 0), False),  # 右界不含
            (_dt.datetime(2026, 8, 13, 13, 27, 30, 500_000), True),
        ],
    )
    def test_frozen_clock_decides_window_through_real_format(
        self, monkeypatch: pytest.MonkeyPatch, wall: _dt.datetime, expected: bool
    ) -> None:
        """凍結 `datetime.now` 而不是替掉 `_now_taipei_time`:要跑的正是格式化那一步。

        替的是 **engine 模組的 `_dt` 綁定**(不是 `datetime` 模組本身的屬性):後者是
        全域突變,會連帶影響同一輪跑的其他測試。
        """
        monkeypatch.setattr(
            stock_engine_mod,
            "_dt",
            SimpleNamespace(datetime=SimpleNamespace(now=lambda: wall), timedelta=_dt.timedelta),
        )
        assert stock_engine_mod._spot_trial_window_now() is expected

    def test_observe_windows_widen_trial_windows_by_two_seconds(self) -> None:
        """D6-1 的推導式落地值(改 `TRIAL_WINDOWS` 時這條會提醒觀測窗要跟著動)。"""
        assert stock_engine_mod._OBSERVE_WINDOWS == (
            ("08:29:58.000", "09:00:02.000"),
            ("13:24:58.000", "13:30:02.000"),
        )


class _TickClock:
    """凍結時鐘 + **迴圈拍數計數器**(`now_fn` 注入點)。

    否定型斷言(「不 stage1」)需要一個可觀察的計數器來確定迴圈真的轉過幾拍:
    在 Windows 上 `await asyncio.sleep(0.1)` 對 interval=0.01 實際只跑 ~3 拍
    (timer 解析度 15.6ms,同 `_wait_rounds` 的 W-4 理由),用牆鐘換拍數的話
    「沒 stage1」有可能只是因為迴圈根本沒轉。
    """

    def __init__(self, wall: _dt.datetime) -> None:
        self.wall = wall
        self.ticks = 0

    def __call__(self) -> _dt.datetime:
        self.ticks += 1
        return self.wall


class TestCheckpointTradingDay:
    """SC-4:checkpoint 的「候選交易日」判定改吃注入的 `is_trading_day`。

    現行是 `now.weekday() < 5` —— 國定假日(平日)08:00 照樣 stage1,把 source 日窗切到
    假日,而 stage2 永遠等不到新日首筆(假日無推播)→ 狀態不清、但其後任何回補都走
    假日窗回空,畫面只是空著沒有任何錯誤訊號。
    """

    async def _armed(
        self,
        wall: _dt.datetime,
        *,
        is_trading_day: Callable[[_dt.date], bool] | None = None,
    ) -> tuple[StockEngine, FakeSource, _TickClock]:
        """起一個 checkpoint 開著的 engine,等迴圈確實轉過 3 拍後回傳現況。"""
        clock = _TickClock(wall)
        src = FakeSource()
        extra = {} if is_trading_day is None else {"is_trading_day": is_trading_day}
        engine = StockEngine(
            src,
            trade_date="2026-08-12",
            throttle_secs=0.01,
            checkpoint=True,
            now_fn=clock,
            **extra,  # type: ignore[arg-type]
        )
        engine._checkpoint_secs = 0.01  # type: ignore[attr-defined]
        await engine.start()
        await wait_until(lambda: clock.ticks >= 3)
        return engine, src, clock

    async def test_non_trading_weekday_does_not_arm_stage1(self) -> None:
        """平日但日曆說非交易日(國定假日)→ 不 stage1、不動 source 日窗。"""
        engine, src, _ = await self._armed(
            _dt.datetime(2026, 8, 13, 9, 0), is_trading_day=lambda _d: False
        )
        try:
            assert engine._pending_date is None
            assert src.trade_dates == ["2026-08-12"]  # 只有 start() 同步那次
        finally:
            await engine.close()

    async def test_trading_day_arms_stage1(self) -> None:
        """同一個時鐘、日曆說是交易日 → 照舊 stage1(否定型斷言的對照組)。"""
        engine, src, _ = await self._armed(
            _dt.datetime(2026, 8, 13, 9, 0), is_trading_day=lambda _d: True
        )
        try:
            # **該變**(review SP1):`_pending_date` 仍在 stage1 的同步段設定,但換窗
            # (`set_trade_date`,N052 之後含一批同步 UNSUBQUOTE)已下沉到重掛的背景
            # to_thread —— 等前者再讀後者是一條真的會偶發紅的競賽(全量跑時真的踩到)。
            # 等待條件改成直接等那個副作用本身。
            await wait_until(lambda: src.trade_dates == ["2026-08-12", "2026-08-13"])
            assert engine._pending_date == "2026-08-13"
        finally:
            await engine.close()

    async def test_default_keeps_weekday_semantic(self) -> None:
        """W9:不注入 `is_trading_day` 時逐字保留現行 `weekday() < 5`(週六不 stage1)。"""
        engine, src, _ = await self._armed(_dt.datetime(2026, 8, 15, 9, 0))
        try:
            assert engine._pending_date is None
            assert src.trade_dates == ["2026-08-12"]
        finally:
            await engine.close()


class _PerCodeGateSource(FakeSource):
    """逐碼閘門的 source:`gates[code]` 未 set 前 `subscribe_symbol` 卡住。

    單一 `subscribe_gate` 表達不出「第一檔已放行、第二檔還卡著」這個形狀 —— 而
    N111 要鎖的正是「第二個寫入者在**檔與檔之間**進得來」。
    """

    def __init__(self) -> None:
        super().__init__()
        self.gates: dict[str, threading.Event] = {}
        self.entered: dict[str, threading.Event] = {}

    def _gate(self, code: str) -> threading.Event:
        return self.gates.setdefault(code, threading.Event())

    def _entered(self, code: str) -> threading.Event:
        return self.entered.setdefault(code, threading.Event())

    def subscribe_symbol(self, code: str) -> None:
        self._entered(code).set()
        assert self._gate(code).wait(timeout=5), f"gate {code} 沒放行"
        super().subscribe_symbol(code)


class TestWatchlistPoolLockGranularity:
    """N111:`set_watchlist` 整段逐檔 `to_thread(_acquire)` 迴圈都在 `_pool_lock` 內
    —— TC4 故障時單檔 SUBQUOTE 要等 `_REQ_TIMEOUT_MS`(10 s)才失敗,第二個寫入者
    (PUT / Discord `/watch` 的 `_settle`、切主圖)得等**整段**迴圈走完,Discord 的
    interaction token(3 s)必逾時。修法方向 = 同檔 `_retry_round` 的逐項取鎖。
    """

    async def test_second_writer_gets_in_between_codes(self) -> None:
        src = _PerCodeGateSource()
        engine = StockEngine(src, trade_date="2026-07-21", throttle_secs=0.01, checkpoint=False)
        await engine.start()
        src._gate("9999").set()  # 第二個寫入者要訂的主圖放行(2330 / 5483 先卡住)
        first = asyncio.create_task(engine.set_watchlist(["2330", "5483"], seq=1))
        try:
            await asyncio.to_thread(src._entered("2330").wait, 5)  # 第一檔的 SUB 在途中
            second = asyncio.create_task(engine.set_main("9999"))  # 第二個寫入者排進鎖
            await asyncio.sleep(0)
            src._gate("2330").set()  # 第一檔完成 → 迴圈釋放鎖 → 第二個寫入者進得來
            await asyncio.wait_for(second, timeout=2.0)
            assert engine._main == "9999"
            assert not first.done(), "第一個寫入者這時應仍卡在第二檔"
        finally:
            src._gate("5483").set()
            await asyncio.wait_for(first, timeout=5.0)
            await engine.close()

    async def test_watchlist_is_assigned_before_any_subscribe(self) -> None:
        """「名單先指派再訂閱」(round4 項 4)的不變式在逐項取鎖之後仍成立 ——
        沒有它,SUB 回來後那第一則 REALTIME 會落在 `code not in _watchlist` 的窗內,
        被 `_handle_quote` 的 meta 轉態補推擋掉,盤後就卡在 `-` 直到重整。"""
        src = _PerCodeGateSource()
        engine = StockEngine(src, trade_date="2026-07-21", throttle_secs=0.01, checkpoint=False)
        await engine.start()
        task = asyncio.create_task(engine.set_watchlist(["2330"], seq=1))
        try:
            await asyncio.to_thread(src._entered("2330").wait, 5)
            assert engine._watchlist == ["2330"]
        finally:
            src._gate("2330").set()
            await asyncio.wait_for(task, timeout=5.0)
            await engine.close()

    async def test_stale_call_abandons_the_rest_of_its_loop(self) -> None:
        """逐項取鎖打開了一條新的窗:**較舊**的那一發可能在較新的名單套用之後才跑完
        剩下的檔 —— 照跑就是把名單退回上一版(`seq` 防的正是這個,只是舊碼靠整段
        持鎖天然不可能發生)。"""
        src = _PerCodeGateSource()
        engine = StockEngine(src, trade_date="2026-07-21", throttle_secs=0.01, checkpoint=False)
        await engine.start()
        src._gate("2330").set()
        task = asyncio.create_task(engine.set_watchlist(["2330", "5483"], seq=1))
        try:
            await asyncio.to_thread(src._entered("5483").wait, 5)
            src._gate("5483").set()
            await asyncio.wait_for(engine.set_watchlist(["2330"], seq=2), timeout=2.0)
            await asyncio.wait_for(task, timeout=5.0)
            assert engine._watchlist == ["2330"], "舊名單覆寫了新名單"
        finally:
            await engine.close()


class TestWatchlistBootSentinel:
    """N112:`seq=None` 的豁免分支唯一的生產 caller 是 app boot 還原,而它的安全前提
    (「service 在 restore 之後才建構 + routes 前置 503」)沒有在任何地方被斷言;
    Protocol 的預設 `None` 又讓未來的 caller 漏帶 keyword 時零訊號。
    收法 = boot 顯式帶 sentinel(恆為最舊),不變式從口頭約定變成結構性的。
    """

    async def test_boot_sentinel_applies_on_a_fresh_engine(self) -> None:
        engine, _src = await _make()
        await engine.set_watchlist(["2330"], seq=stock_engine_mod.WATCHLIST_BOOT_SEQ)
        assert engine._watchlist == ["2330"]
        await engine.close()

    async def test_boot_sentinel_never_clobbers_a_newer_list(self) -> None:
        """PUT 先到、boot 還原後到(未來若有人把 restore 挪到 service 之後)——
        舊碼的 `seq=None` 是無條件全套,會把使用者剛存的名單退回上一版。"""
        engine, _src = await _make()
        await engine.set_watchlist(["2317"], seq=1)
        await engine.set_watchlist(["2330"], seq=stock_engine_mod.WATCHLIST_BOOT_SEQ)
        assert engine._watchlist == ["2317"]
        await engine.close()

    def test_boot_sentinel_is_the_oldest_possible_seq(self) -> None:
        """service 取號自 1 起(`WatchlistService`)—— sentinel 必須嚴格小於它。"""
        assert stock_engine_mod.WATCHLIST_BOOT_SEQ < 1
class _IdentSource(FakeSource):
    """記錄 `set_trade_date` 是在**哪一條執行緒**上被呼叫的(SP1 的唯一判準)。"""

    def __init__(self) -> None:
        super().__init__()
        self.trade_date_idents: list[int] = []

    def set_trade_date(self, trade_date: str) -> None:
        self.trade_date_idents.append(threading.get_ident())
        super().set_trade_date(trade_date)


class TestWatchlistSupersededRelease:
    """review ST1 / SP3:`removed` 由 `self._watchlist` 算,但**較舊**那一發已經把它
    覆寫過 —— 舊發在 added 迴圈被 `_superseded` 提前 return 時整段跳過 removed 迴圈,
    它還沒退的檔既不在新發的 `removed`(新發算的時候名單已經是舊發那份)、也不在任何
    名單裡 → `"watchlist"` ref 永久佔著訂閱位,而畫面上那一檔早就不見了,零訊號。
    """

    async def test_superseded_call_leaves_no_orphan_watchlist_ref(self) -> None:
        src = _PerCodeGateSource()
        engine = StockEngine(
            src, trade_date="2026-07-21", throttle_secs=0.01, checkpoint=False
        )
        await engine.start()
        for code in ("2330", "5483", "6669"):
            src._gate(code).set()
        await engine.set_watchlist(["2330", "5483", "6669"], seq=1)
        older = asyncio.create_task(engine.set_watchlist(["2330", "9999"], seq=2))
        try:
            await asyncio.to_thread(
                src._entered("9999").wait, 5
            )  # 舊發卡在新增檔的 SUB
            newer = asyncio.create_task(engine.set_watchlist(["2330"], seq=3))
            await asyncio.sleep(0)
            src._gate("9999").set()  # 放行 → 舊發釋鎖 → 新發進場並整份套完
            await asyncio.wait_for(newer, timeout=5.0)
            await asyncio.wait_for(older, timeout=5.0)
            assert "watchlist" not in engine._refs.get("5483", set()), "退訂洩漏:5483"
            assert "watchlist" not in engine._refs.get("6669", set()), "退訂洩漏:6669"
            assert engine._watchlist == ["2330"]
        finally:
            await engine.close()

    async def test_removed_is_computed_from_refs_not_from_the_list(self) -> None:
        """直接鎖判準本身:`_refs` 裡持著 `"watchlist"` ref 卻不在最新名單的檔一律要退,
        不管 `self._watchlist` 當下長什麼樣(它可能已被別發覆寫)。"""
        engine, src = await _make()
        await engine.set_watchlist(["2330", "5483"], seq=1)
        engine._watchlist = ["2330", "5483", "6669"]  # 模擬被別發覆寫過的名單
        await engine.set_watchlist(["2330"], seq=2)
        assert "watchlist" not in engine._refs.get("5483", set())
        assert "5483" in src.unsubscribed
        await engine.close()


class TestRolloverStageOneOffLoop:
    """review SP1:換日的舊窗批次 UNSUB 是同步 ZMQ REQ,而 `rollover_stage1` 跑在
    event loop 上 —— TC4 半死時 50 檔各等 `_REQ_TIMEOUT_MS`(10 s)= 整條 loop 停擺
    幾分鐘(WS 心跳、廣播、route 全卡)。同檔 `_resubscribe_all` 的 docstring 早就寫了
    「ZMQ REQ 全程 to_thread,不佔 event loop」,這條是同一個不變式的漏網。
    """

    async def test_source_date_switch_does_not_run_on_the_loop_thread(self) -> None:
        src = _IdentSource()
        engine = StockEngine(
            src, trade_date="2026-07-21", throttle_secs=0.01, checkpoint=False
        )
        await engine.start()
        loop_ident = threading.get_ident()
        src.trade_date_idents.clear()
        try:
            engine.rollover_stage1("2026-07-22")
            await wait_until(lambda: src.trade_dates[-1:] == ["2026-07-22"])
            assert src.trade_date_idents[-1] != loop_ident, (
                "換日的 ZMQ REQ 跑在 event loop 上"
            )
        finally:
            await engine.close()

    async def test_stale_window_unsub_happens_before_the_new_window_resub(self) -> None:
        """順序是這條修法的整個重點:舊窗歸零 → 新窗 SUB 走 0→1 才會觸發上游
        `ReqSubQuote`。反過來的話舊窗那把 key 仍 >0,新窗只是多一把,feed 沒被重掛。"""
        src = _IdentSource()
        engine = StockEngine(
            src, trade_date="2026-07-21", throttle_secs=0.01, checkpoint=False
        )
        await engine.start()
        await engine.set_watchlist(["2330"], seq=1)
        order: list[str] = []
        src.set_trade_date = lambda d: order.append("set_trade_date")  # type: ignore[method-assign]
        src.on_subscribe = lambda code: order.append(f"subscribe:{code}")
        try:
            engine.rollover_stage1("2026-07-22")
            await wait_until(lambda: order[-1:] == ["subscribe:2330"])
            assert order == ["set_trade_date", "subscribe:2330"]
        finally:
            await engine.close()


# ---- ticks 打包 + 收件人集合(mod/group-grid-ticks T1,#180)----


def _bundles(got: list[dict]) -> list[dict]:
    return [m for m in got if m["type"] == "ticks"]


class TestTickBundle:
    """逐筆改 0.1 s 打包:一則 `ticks` 含「主圖 ∪ 各連線登記的檢視集合」的全部成交,
    逐筆不合併、逐筆不少;收件人集合與訂閱池正交(群組成員本來就在自選池全天訂著)。"""

    async def test_watchlist_member_is_not_bundled_until_a_view_registers_it(self) -> None:
        engine, src = await _make()
        await engine.set_watchlist(["2330", "2317"])
        # 卡住回補(主圖 set_main 的空回補 + 成員首筆 tick 的 S2 入列都會 `apply_backfill`
        # 把 seq 跳 +1001):這裡要的是可讀的 1 / 2 / 3。
        src.backfill_gate = threading.Event()
        await engine.set_main("2330")
        await _drain(engine)
        assert src.on_message is not None
        # 每個階段各開一條 stream:`_collect` 逾時時 `wait_for` 取消 `anext` 會把該
        # generator 關掉(queue 除名),同一條不能收第二輪。
        stream = engine.stream()
        src.on_message(_quote(code="2317", cum=1))
        await _drain(engine)
        assert [it["code"] for it in _tick_items(await _collect(stream))] == []

        token = object()
        engine.set_view(token, ["2317"])
        stream = engine.stream()
        src.on_message(_quote(code="2317", cum=2))
        await _drain(engine)
        items = _tick_items(await _collect(stream))
        assert [(it["code"], it["seq"]) for it in items] == [("2317", 2)]

        engine.clear_view(token)
        stream = engine.stream()
        src.on_message(_quote(code="2317", cum=3))
        await _drain(engine)
        assert _tick_items(await _collect(stream)) == []
        src.backfill_gate.set()
        await engine.close()

    async def test_main_and_view_codes_share_one_bundle_with_per_code_seq(self) -> None:
        engine, src = await _make()
        await engine.set_watchlist(["2330", "2317"])
        # 卡住主圖的空回補:`apply_backfill` 會把 seq 跳到 1002(同 TestStreamAndStatus 的
        # flake 教訓),這裡要的是「兩檔各自從 1 起算」的可讀斷言。
        src.backfill_gate = threading.Event()
        await engine.set_main("2330")
        await _drain(engine)
        engine.set_view(object(), ["2317"])
        stream = engine.stream()
        assert src.on_message is not None
        # 同步連發(無 await)= 同一個 flush 窗
        src.on_message(_quote(code="2330", cum=1, price="2380"))
        src.on_message(_quote(code="2317", cum=1, price="100"))
        src.on_message(_quote(code="2330", cum=2, price="2385"))
        src.on_message(_quote(code="2317", cum=2, price="101"))
        await _drain(engine)
        got = await _collect(stream)
        bundles = _bundles(got)
        assert len(bundles) == 1
        items = bundles[0]["items"]
        assert [(it["code"], it["seq"]) for it in items] == [
            ("2330", 1),
            ("2317", 1),
            ("2330", 2),
            ("2317", 2),
        ]
        # item 欄位與舊單筆 tick 逐字相同(少 `type`)
        assert set(items[0]) == {"code", "t", "p", "q", "side", "b", "a", "h", "l", "seq"}
        # 單筆 `tick` 型別退役
        assert not any(m["type"] == "tick" for m in got)
        src.backfill_gate.set()
        await engine.close()

    async def test_set_view_does_not_touch_the_subscription_pool(self) -> None:
        engine, src = await _make()
        await engine.set_watchlist(["2330"])
        await _drain(engine)
        before = (list(src.subscribed), list(src.unsubscribed))
        token = object()
        engine.set_view(token, ["2330", "9999"])  # 9999 不在池:登記無害
        engine.clear_view(token)
        await _drain(engine)
        assert (list(src.subscribed), list(src.unsubscribed)) == before
        await engine.close()

    async def test_pressure_50_codes_20_ticks_each_land_in_few_bundles_seq_contiguous(self) -> None:
        """50 檔 × 20 筆同窗灌入(開盤瞬間的形狀):打包則數遠小於成交數、逐檔 seq 連續。"""
        codes = [str(1001 + i) for i in range(50)]
        engine, src = await _make()
        await engine.set_watchlist(codes)
        await _drain(engine)
        engine.set_view(object(), codes)
        stream = engine.stream()
        assert src.on_message is not None
        for cum in range(1, 21):
            for code in codes:
                src.on_message(_quote(code=code, cum=cum, price=str(100 + cum)))
        await _drain(engine)
        got = await _collect(stream)
        bundles = _bundles(got)
        items = _tick_items(got)
        assert len(items) == 1000
        assert len(bundles) <= 3
        by_code: dict[str, list[int]] = {}
        for it in items:
            by_code.setdefault(it["code"], []).append(it["seq"])
        assert set(by_code) == set(codes)
        assert all(seqs == list(range(1, 21)) for seqs in by_code.values())
        await engine.close()
