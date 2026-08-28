"""CorrelationEngine 的江波圖接線(SC-3/SC-4/SC-5):live 餵值、背景回補、delta 廣播。"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Callable

import pytest

from copycat.corr_config import CorrConfig, Leg
from copycat.live.tc4 import HistoryTimeoutError
from copycat.server import corr_engine as corr_engine_mod
from copycat.server.corr_engine import CorrelationEngine
from tests.helpers.wait import wait_until

DAY = ("20260730", "day")

CONFIG = CorrConfig(
    legs=(
        Leg("TXF", "台指", "TC.F.TWF.TXF.HOT", "futures_engine"),
        Leg("NQ", "納指", "TC.F.CME.NQ.HOT", "tc4"),
        Leg("SXF", "費半", "TC.F.TWF.SXF.HOT", "tc4"),
    ),
    base="TXF",
    windows=(60,),
    min_samples={60: 3},
    stale_secs=30.0,
)


class _FakeSource:
    def __init__(self) -> None:
        self.subscribed: list[str] = []
        self.closed = False
        self.cb: Callable[[dict], None] | None = None
        self.fetched: list[str] = []
        self.minutes: dict[str, list[tuple[int, int]]] = {}
        self.fail_1k: set[str] = set()
        #: 恆逾時(重試上界要測的那條);`timeout_1k_once` 只逾時第一發,之後正常
        self.fail_1k_timeout: set[str] = set()
        self.timeout_1k_once: set[str] = set()
        #: 掛上後**每一發** fetch 都卡在閘門上(`to_thread` 執行緒,loop 不受阻)——
        #: 用來造「一輪回補確實還在進行中」的 single-flight 互吃現場
        self.gate: threading.Event | None = None

    def subscribe_raw(self, symbol: str) -> None:
        self.subscribed.append(symbol)

    def unsubscribe_raw(self, symbol: str) -> None:
        if symbol in self.subscribed:
            self.subscribed.remove(symbol)

    def set_on_message(self, cb: Callable[[dict], None]) -> None:
        self.cb = cb

    def fetch_day_1k(self, symbol: str) -> list[tuple[int, int]]:
        self.fetched.append(symbol)
        if self.gate is not None:
            self.gate.wait()
        if symbol in self.fail_1k:
            raise ConnectionError(f"1K fail {symbol}")
        if symbol in self.fail_1k_timeout:
            raise HistoryTimeoutError(f"1K timeout {symbol}")
        if symbol in self.timeout_1k_once:
            self.timeout_1k_once.discard(symbol)
            raise HistoryTimeoutError(f"1K timeout {symbol}")
        return self.minutes.get(symbol, [])

    def close(self) -> None:
        self.closed = True


def _trade_quote(symbol: str, price_milli: int, *, precise: str = "030030000000") -> dict:
    """帶成交的 REALTIME。

    `PreciseTime` 是 **12 位 HHMMSSffffff**(微秒;`stock_models._taipei_time` 以 zfill(12) 解析)
    → "030030000000" = UTC 03:00:30 = 台北 11:00:30 → 桶 11:01 = minute 661 → 日盤 offset 136。
    位數寫短會被 zfill 從左邊補零成完全不同的時刻(本測試第一版踩過:9 位 → UTC 00:00:30)。
    """
    return {
        "Symbol": symbol,
        "SecurityName": "x",
        "TradingPrice": str(price_milli / 1000),
        "TradeQuantity": "3",
        "TradeVolume": "100",
        "TradeDate": "20260730",
        "PreciseTime": precise,
        "Bid": str((price_milli - 1000) / 1000),
        "BidVolume": "5",
        "Ask": str((price_milli + 1000) / 1000),
        "AskVolume": "5",
    }


def _foreign_trade_quote(symbol: str, price_milli: int) -> dict:
    """海外腿(CME/CBOT/SGX)實測形狀:`PreciseTime` 是 **6 位 HHMMSS**,不是台期交的 12 位。

    Phase 6 real-env finding —— 用 zfill(12) 解讀 "41256" 會得到台北 08:00:00.041 的假時刻,
    分鐘落在日盤窗外 → 該腿永遠不進點。`FilledTime` 兩段同寬,改吃它。
    """
    return {
        "Symbol": symbol,
        "SecurityName": "x",
        "TradingPrice": str(price_milli / 1000),
        "TradeQuantity": "4",
        "TradeVolume": "100",
        "TradeDate": "20260730",
        "PreciseTime": "41256",  # 6 位;zfill(12) 會解成 00:00:00.041
        "FilledTime": "41256",  # 04:12:56 UTC → 台北 12:12:56 → 桶 12:13 = 733 → offset 208
        "Bid": str((price_milli - 1000) / 1000),
        "BidVolume": "5",
        "Ask": str((price_milli + 1000) / 1000),
        "AskVolume": "5",
    }


def _book_quote(symbol: str, bid: int, ask: int) -> dict:
    return {
        "Symbol": symbol,
        "SecurityName": "x",
        "Bid": str(bid / 1000),
        "BidVolume": "5",
        "Ask": str(ask / 1000),
        "AskVolume": "5",
    }


def _futures_state(price: int | None = 40_400_000) -> dict:
    return {
        "seq": 1,
        "products": {
            "TXF": {
                "product": "TXF",
                "p": price,
                "bids": [(price - 1000, 5)] if price is not None else [],
                "asks": [(price + 1000, 5)] if price is not None else [],
            }
        },
    }


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


async def _drain() -> None:
    for _ in range(30):
        await asyncio.sleep(0.001)


def _engine(
    source: _FakeSource,
    *,
    txf_state: Callable[[], dict] = lambda: _futures_state(),
    clock: _Clock | None = None,
    river_broadcast: Callable[[dict], None] | None = None,
    futures_minutes_fetch: Callable[[str], list[tuple[int, int]]] | None = None,
    taipei_time: str = "110030",
) -> CorrelationEngine:
    return CorrelationEngine(
        lambda: source,
        config=CONFIG,
        txf_state_getter=txf_state,
        tick_secs=1.0,
        now_fn=clock or _Clock(),
        session_fn=lambda: DAY,
        river_broadcast=river_broadcast,
        futures_minutes_fetch=futures_minutes_fetch,
        taipei_time_fn=lambda: taipei_time,
    )


def _minutes(eng: CorrelationEngine, key: str) -> dict[int, int]:
    return eng.river_snapshot()["legs"][key]["minutes"]


class TestLiveFeed:
    async def test_trade_tick_becomes_minute_point(self) -> None:
        src = _FakeSource()
        eng = _engine(src)
        await eng.start()
        try:
            assert src.cb is not None
            src.cb(_trade_quote("TC.F.CME.NQ.HOT", 27_638_000))
            await _drain()
            assert _minutes(eng, "NQ") == {136: 27_638_000}  # 11:01 → offset 136
        finally:
            await eng.close()

    async def test_book_only_quote_adds_no_point_but_mid_still_works(self) -> None:
        src = _FakeSource()
        eng = _engine(src)
        await eng.start()
        try:
            assert src.cb is not None
            src.cb(_book_quote("TC.F.CME.NQ.HOT", 27_637_000, 27_639_000))
            await _drain()
            assert _minutes(eng, "NQ") == {}
            eng.tick_once()
            assert eng.state()["legs"]["NQ"]["mid"] == 27_638_000  # 既有中價行為不變
        finally:
            await eng.close()

    async def test_foreign_leg_uses_filled_time_not_precise_time(self) -> None:
        """Phase 6 real-env finding:海外腿的 PreciseTime 是 6 位 → 必須用 FilledTime 分桶。"""
        src = _FakeSource()
        eng = _engine(src)
        await eng.start()
        try:
            assert src.cb is not None
            src.cb(_foreign_trade_quote("TC.F.CME.NQ.HOT", 27_638_000))
            await _drain()
            assert _minutes(eng, "NQ") == {208: 27_638_000}  # 12:13 → offset 208
        finally:
            await eng.close()

    async def test_tc4_leg_without_filled_time_falls_back_to_local_clock(self) -> None:
        """FilledTime 缺值/壞值 → 退回本機時鐘(與台指腿同款),不是丟掉這一點。"""
        src = _FakeSource()
        eng = _engine(src, taipei_time="110030")  # → 桶 11:01 = 661 → offset 136
        await eng.start()
        try:
            assert src.cb is not None
            quote = _foreign_trade_quote("TC.F.CME.NQ.HOT", 27_638_000)
            quote["FilledTime"] = ""
            src.cb(quote)
            await _drain()
            assert _minutes(eng, "NQ") == {136: 27_638_000}
        finally:
            await eng.close()

    async def test_futures_leg_point_from_tick_with_injected_clock(self) -> None:
        src = _FakeSource()
        eng = _engine(src)
        await eng.start()
        try:
            eng.tick_once()
            assert _minutes(eng, "TXF") == {136: 40_400_000}
        finally:
            await eng.close()

    async def test_futures_leg_empty_when_upstream_has_no_data(self) -> None:
        """SC-4:既有 bug 1 發作(futures_engine 零推播)→ 台指腿空著,其餘腿照常。"""
        src = _FakeSource()
        eng = _engine(src, txf_state=lambda: {})
        await eng.start()
        try:
            assert src.cb is not None
            src.cb(_trade_quote("TC.F.CME.NQ.HOT", 27_638_000))
            await _drain()
            eng.tick_once()
            assert _minutes(eng, "TXF") == {}
            assert _minutes(eng, "NQ") == {136: 27_638_000}
            assert eng.river_snapshot()["legs"]["TXF"]["last"] is None
        finally:
            await eng.close()


class TestBackfill:
    async def test_applies_per_tc4_leg(self) -> None:
        src = _FakeSource()
        src.minutes["TC.F.CME.NQ.HOT"] = [(600, 27_600_000), (601, 27_610_000)]
        eng = _engine(src)
        await eng.start()
        try:
            await _drain()
            assert _minutes(eng, "NQ") == {75: 27_600_000, 76: 27_610_000}
        finally:
            await eng.close()

    async def test_one_leg_failure_does_not_block_others(self) -> None:
        src = _FakeSource()
        src.minutes["TC.F.CME.NQ.HOT"] = [(600, 27_600_000)]
        src.fail_1k.add("TC.F.TWF.SXF.HOT")
        eng = _engine(src)
        await eng.start()
        try:
            await _drain()
            assert _minutes(eng, "NQ") == {75: 27_600_000}
            assert _minutes(eng, "SXF") == {}
        finally:
            await eng.close()

    async def test_never_requests_base_leg_symbol(self) -> None:
        """SC-4:台指的歷史也不可從 corr session 問(多掛一把 refcount key = 多一個退訂引信)。"""
        src = _FakeSource()
        eng = _engine(src, futures_minutes_fetch=lambda p: [])
        await eng.start()
        try:
            await _drain()
            assert "TC.F.TWF.TXF.HOT" not in src.fetched
            assert "TC.F.TWF.TXF.HOT" not in src.subscribed
        finally:
            await eng.close()

    async def test_futures_leg_backfill_goes_through_injected_fetch(self) -> None:
        src = _FakeSource()
        seen: list[str] = []

        def fetch(product: str) -> list[tuple[int, int]]:
            seen.append(product)
            return [(700, 40_300_000)]

        eng = _engine(src, futures_minutes_fetch=fetch)
        await eng.start()
        try:
            await _drain()
            assert seen == ["TXF"]  # leg.key == 期貨產品碼(design §4 假設)
            assert _minutes(eng, "TXF") == {175: 40_300_000}
        finally:
            await eng.close()

    async def test_backfill_does_not_overwrite_live_minute(self) -> None:
        src = _FakeSource()
        src.minutes["TC.F.CME.NQ.HOT"] = [(661, 27_000_000)]
        eng = _engine(src)
        await eng.start()
        try:
            assert src.cb is not None
            src.cb(_trade_quote("TC.F.CME.NQ.HOT", 27_638_000))  # live 先到,桶 661
            await _drain()
            assert _minutes(eng, "NQ") == {136: 27_638_000}
        finally:
            await eng.close()


class TestBackfillTimeoutRetry:
    """bug/history-timeout-propagation:逾時的腿要排重試,不是「整天只從啟動後累積」。

    真實事故(08:23):TXF/TWN/SXF 三腿同秒逾時 → 江波圖三條線整天缺前半段,
    而 TC4 端的 1K 一直都在。
    """

    async def test_timed_out_leg_is_retried_and_only_that_leg(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(corr_engine_mod, "_BACKFILL_RETRY_SECS", 0.01)
        src = _FakeSource()
        src.minutes["TC.F.CME.NQ.HOT"] = [(600, 27_600_000)]
        src.timeout_1k_once.add("TC.F.TWF.SXF.HOT")
        src.minutes["TC.F.TWF.SXF.HOT"] = [(601, 12_000_000)]
        eng = _engine(src, futures_minutes_fetch=lambda p: [])
        await eng.start()
        try:
            # 等**終態**(分鐘進來了)而不是等固定圈數:`fetched` 是在 fetch 進場時就
            # 記的,等它到 2 只證明第二發開打,還沒證明它的結果被套用
            await wait_until(lambda: bool(_minutes(eng, "SXF")))
            # 首輪逾時 → 第二發把它補回來(次數即證據;中途狀態會隨排程時序漂,不斷言)
            assert src.fetched.count("TC.F.TWF.SXF.HOT") == 2
            assert _minutes(eng, "SXF") == {76: 12_000_000}
            # 只重補 pending 腿:成功的腿不該被再打一次(TC4 歷史通道是稀缺資源)
            assert src.fetched.count("TC.F.CME.NQ.HOT") == 1
        finally:
            await eng.close()

    async def test_retry_rounds_are_capped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """上界從 3 輪放寬到 8 輪(do-batch 第二批題 4 順帶;08-26 08:52 真事件:TSMC 腿開機三輪
        逾時全落在 08:53–08:54 的 90 秒內就放棄,整天無 seed,而 TC4 的 1K 幾分鐘後就備妥了)。
        退避改遞增(30 s 起翻倍、封頂 10 分),8 輪合計 ≈ 45 分鐘 —— 蓋過開盤 TC4 忙碌窗,
        仍然有界(真的壞掉的腿不會整天重打)。"""
        monkeypatch.setattr(corr_engine_mod, "_BACKFILL_RETRY_SECS", 0.01)
        monkeypatch.setattr(corr_engine_mod, "_BACKFILL_RETRY_MAX_SECS", 0.01)
        src = _FakeSource()
        src.fail_1k_timeout.add("TC.F.TWF.SXF.HOT")  # 永遠逾時
        eng = _engine(src, futures_minutes_fetch=lambda p: [])
        await eng.start()
        try:
            # 首輪 + 8 輪重試 = 9;沒有上界的話會一路重試到收盤
            await wait_until(lambda: src.fetched.count("TC.F.TWF.SXF.HOT") == 9)
            await asyncio.sleep(0.05)  # 退避已封頂 0.01s → 這段足夠讓第 10 發(若有)現形
            await _drain()
            assert src.fetched.count("TC.F.TWF.SXF.HOT") == 9
        finally:
            await eng.close()

    def test_retry_delay_ladder_doubles_from_30s_and_caps_at_10min(self) -> None:
        """退避階梯由三個常數推導(不另寫一份數字):30 → 60 → 120 → 240 → 480 → 600 封頂。
        第 1 輪是 30 s(與修前逐字同),之後翻倍;超過 `_BACKFILL_RETRY_MAX_SECS` 一律封頂。
        8 輪合計 2730 s ≈ 45.5 分。"""
        ladder = [corr_engine_mod._retry_delay_secs(n) for n in range(1, 9)]
        assert ladder == [30.0, 60.0, 120.0, 240.0, 480.0, 600.0, 600.0, 600.0]
        assert corr_engine_mod._BACKFILL_RETRY_MAX_ROUNDS == 8
        assert sum(ladder) == 2730.0

    async def test_close_cancels_pending_retry_task(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(corr_engine_mod, "_BACKFILL_RETRY_SECS", 5.0)
        src = _FakeSource()
        src.fail_1k_timeout.add("TC.F.TWF.SXF.HOT")
        eng = _engine(src, futures_minutes_fetch=lambda p: [])
        await eng.start()
        await wait_until(lambda: bool(eng._backfill_retry_tasks))
        tasks = list(eng._backfill_retry_tasks)
        await eng.close()
        # `cancelled()` 而非 `cancelled() or done()`:退避是 5s,close 時它必定還睡在
        # `asyncio.sleep` 上 —— `or done()` 會讓「close 根本沒去取消、task 自己跑完」
        # 也算通過,那正是這條要擋的失效
        assert all(t.cancelled() for t in tasks)

    async def test_reconnect_during_inflight_round_merges_all_legs_and_tail_refetches(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """2026-08-22 review R8 P2 + round-2 P1:reconnect 觸發的**整輪**回補撞上進行中那一輪,
        真正的丟棄點是 `_schedule_backfill` 的 inflight 早退(連 task 都不建、零 log),
        不是 `_backfill_river` 的 merge 分支。整輪要併回全部腿、由進行中那一輪的尾巴重抓;
        併回 = 新 episode(reconnect),連續失敗輪數歸零、不吃逾時重試預算。"""
        monkeypatch.setattr(corr_engine_mod, "_BACKFILL_RETRY_SECS", 0.01)
        src = _FakeSource()
        src.gate = threading.Event()  # NQ 那一發卡在閘門上 → 整輪維持 in-flight
        src.minutes["TC.F.TWF.SXF.HOT"] = [(601, 12_000_000)]
        eng = _engine(src, futures_minutes_fetch=lambda p: [])
        await eng.start()
        try:
            await wait_until(lambda: eng._backfill_inflight)
            eng._backfill_retry_round = 2  # 上一個 episode 留下的連續失敗數
            with caplog.at_level(logging.INFO):
                eng._schedule_backfill()  # = _on_reconnect_threadsafe 落到 loop 後的那一步
            assert eng._backfill_pending_legs == set(eng._legs)
            assert "single-flight" in caplog.text
            src.gate.set()
            # 尾巴接手:SXF 被重抓第二次(首輪 + 併回);輪數歸零後不因併回被 bump 到 3 放棄
            await wait_until(lambda: src.fetched.count("TC.F.TWF.SXF.HOT") >= 2)
            await _drain()
            assert eng._backfill_retry_round == 0
        finally:
            src.gate.set()
            await eng.close()

    async def test_retry_task_unexpected_error_resets_round_budget(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """2026-08-22 review R8 P2:`_backfill_retry` task 無兜底,非 ConnectionError 例外
        會以「Task exception was never retrieved」收場,`_backfill_retry_round` 卡在非零 →
        當天稍後的新 episode 拿到被削過的預算。例外要留痕(WARNING 含 traceback)且歸零。"""
        monkeypatch.setattr(corr_engine_mod, "_BACKFILL_RETRY_SECS", 0.0)
        src = _FakeSource()
        eng = _engine(src, futures_minutes_fetch=lambda p: [])
        await eng.start()
        try:
            await _drain()
            eng._backfill_retry_round = 2

            async def boom(legs: set[str] | None = None) -> None:
                raise RuntimeError("apply_backfill exploded")

            monkeypatch.setattr(eng, "_backfill_river", boom)
            with caplog.at_level(logging.WARNING):
                await eng._backfill_retry({"SXF"})  # 不得把例外往外丟
            assert eng._backfill_retry_round == 0
            assert "apply_backfill exploded" in caplog.text
        finally:
            await eng.close()

    async def test_plain_connection_error_leg_is_not_retried(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """純 `ConnectionError`(TC4 真的不通)照舊降級,**不排重試**。

        重試網是給「TC4 好得很、只是首頁還沒備妥」用的;TC4 不通時整條 session 都在
        重連,再排三輪回補只是對著斷掉的通道空打,而 `HistoryTimeoutError` 是
        `ConnectionError` 的子類 —— 兩個 except 的先後順序寫反就會靜默地把兩者合併。
        """
        monkeypatch.setattr(corr_engine_mod, "_BACKFILL_RETRY_SECS", 0.01)
        src = _FakeSource()
        src.fail_1k.add("TC.F.TWF.SXF.HOT")  # 恆 ConnectionError(非逾時)
        eng = _engine(src, futures_minutes_fetch=lambda p: [])
        await eng.start()
        try:
            await wait_until(lambda: src.fetched.count("TC.F.TWF.SXF.HOT") == 1)
            await asyncio.sleep(0.05)
            await _drain()
            assert src.fetched.count("TC.F.TWF.SXF.HOT") == 1
            assert eng._backfill_retry_tasks == set()
            assert eng._backfill_pending_legs == set()
        finally:
            await eng.close()

    async def test_giving_up_resets_the_round_for_the_next_episode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`_backfill_retry_round` 是**連續**失敗輪數 —— 放棄那一刻也要歸零。

        只在「補齊一輪」歸零的話,放棄後計數永久停在上限:當天稍後的每一次 reconnect
        回補都會在第一次逾時就直接放棄(零重試),而 log 只有一行「已重試 3 輪」讀起來
        像是真的試過。第二個 episode 是新的抖動,該有自己的完整預算。
        """
        monkeypatch.setattr(corr_engine_mod, "_BACKFILL_RETRY_SECS", 0.01)
        monkeypatch.setattr(corr_engine_mod, "_BACKFILL_RETRY_MAX_SECS", 0.01)
        src = _FakeSource()
        src.fail_1k_timeout.add("TC.F.TWF.SXF.HOT")  # 永遠逾時
        eng = _engine(src, futures_minutes_fetch=lambda p: [])
        await eng.start()
        try:
            # episode 1:首輪 + 8 輪重試 = 9,然後放棄
            await wait_until(lambda: src.fetched.count("TC.F.TWF.SXF.HOT") == 9)
            await _drain()
            assert src.fetched.count("TC.F.TWF.SXF.HOT") == 9, "上界失效"
            # episode 2:reconnect 觸發全新一輪 —— 預算沒歸零的話這裡只會有 1 發
            eng._on_reconnect_threadsafe()
            await wait_until(lambda: src.fetched.count("TC.F.TWF.SXF.HOT") == 18)
        finally:
            await eng.close()

    async def test_retry_blocked_by_single_flight_keeps_its_legs(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """single-flight 互吃:被擋掉那一發的腿要併回 pending,並留下一行 log。

        舊碼是靜默 `return` —— 重試 task 醒來時撞上 reconnect 觸發的整輪回補,它負責的
        那幾腿就這樣蒸發,全鏈零訊號(江波圖只是缺前半段)。併回 pending 之後由進行中
        那一輪的尾巴接手重排(**恰好一次**,不重複排);被擋下不算試過,所以不 bump 輪數。
        """
        src = _FakeSource()
        src.gate = threading.Event()  # NQ 那一發卡在閘門上 → 整輪維持 in-flight
        eng = _engine(src, futures_minutes_fetch=lambda p: [])
        await eng.start()
        try:
            await wait_until(lambda: eng._backfill_inflight)
            round_before = eng._backfill_retry_round
            with caplog.at_level(logging.INFO):
                await eng._backfill_river(legs={"SXF"})  # 重試醒來,撞上進行中那一輪
            assert eng._backfill_pending_legs == {"SXF"}
            assert eng._backfill_retry_round == round_before
            assert "single-flight" in caplog.text
        finally:
            src.gate.set()
            await eng.close()


class TestBackfillSessionOrdering:
    """Phase 4 自評 finding:回補任務不得把狀態機的盤別「拉回」發起時的那一場。

    情境:14:59:58 起跑的回補在 15:00:01 才回來 —— 此時 tick 已把 river 切到夜盤。
    若回補流程對狀態機重設發起時的 session,夜盤已累積的點會被清掉、窗也退回日盤,
    畫面出現一秒的錯盤別資料(下一拍才自我修正)。
    直呼私有 `_backfill_river` 是為了精確控制「回補晚於換場」的時序 —— 走 start() 無法
    穩定重現這個順序。
    """

    async def test_late_backfill_does_not_revert_session(self) -> None:
        src = _FakeSource()
        src.minutes["TC.F.CME.NQ.HOT"] = [(600, 27_600_000)]  # 日盤窗的分鐘
        sessions = [("20260730", "night")]
        eng = CorrelationEngine(
            lambda: src,
            config=CONFIG,
            txf_state_getter=lambda: _futures_state(),
            tick_secs=1.0,
            now_fn=_Clock(),
            session_fn=lambda: sessions[0],
            taipei_time_fn=lambda: "230030",  # 夜盤 23:01 → offset 481
        )
        await eng.start()
        try:
            await _drain()
            eng.tick_once()  # 夜盤點入帳
            assert _minutes(eng, "TXF") == {481: 40_400_000}

            sessions[0] = ("20260730", "day")  # 回補以「日盤」身分晚到
            await eng._backfill_river()

            snap = eng.river_snapshot()
            assert snap["session"] == "night"
            assert snap["window"] == {"start_min": 900, "end_min": 1740}
            assert _minutes(eng, "TXF") == {481: 40_400_000}  # 夜盤點沒被清掉
            assert _minutes(eng, "NQ") == {}  # 日盤回補資料不得混入夜盤
        finally:
            await eng.close()


class TestRiverBroadcast:
    async def test_one_delta_per_tick_with_monotonic_seq(self) -> None:
        src = _FakeSource()
        events: list[dict] = []
        eng = _engine(src, river_broadcast=events.append)
        await eng.start()
        try:
            eng.tick_once()
            eng.tick_once()
            assert [e["type"] for e in events] == ["river_delta", "river_delta"]
            assert [e["seq"] for e in events] == [1, 2]
            assert events[-1]["legs"]["TXF"] == {"m": 136, "p": 40_400_000}
            assert events[-1]["window"] == {"start_min": 525, "end_min": 825}
        finally:
            await eng.close()

    async def test_no_broadcast_after_close(self) -> None:
        src = _FakeSource()
        events: list[dict] = []
        eng = _engine(src, river_broadcast=events.append)
        await eng.start()
        eng.tick_once()
        await eng.close()
        n = len(events)
        assert src.cb is not None
        src.cb(_trade_quote("TC.F.CME.NQ.HOT", 27_638_000))  # close 後推播不得再進狀態
        await _drain()
        assert len(events) == n


class TestSnapshotShape:
    async def test_snapshot_carries_labels_window_and_base(self) -> None:
        src = _FakeSource()
        eng = _engine(src)
        await eng.start()
        try:
            snap = eng.river_snapshot()
            assert snap["type"] == "river"
            assert snap["base"] == "TXF"
            assert snap["session"] == "day"
            assert snap["window"] == {"start_min": 525, "end_min": 825}
            assert snap["legs"]["SXF"]["label"] == "費半"
        finally:
            await eng.close()
