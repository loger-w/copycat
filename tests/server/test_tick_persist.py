"""S1 盤中 tick 存檔(spec #257):餵達錢訊息、看 jsonl。

沿 `test_stock_engine` 的 fake source + engine 鷹架;只斷言檔案內容與 `load_day` 讀回,
不碰 handle / 緩衝 / 私有計數器。
"""

from __future__ import annotations

import datetime as _dt
import io
import json
import logging
import re
import time
from pathlib import Path
from typing import Callable, TextIO

import pytest

from copycat.live.stock_models import StockTick
from copycat.live.stock_state import StockDayState
from copycat.live.tick_persist import TickPersist
from copycat.server.app import create_app
from copycat.server.stock_engine import StockEngine
from copycat.ticks import TickRow, load_day
from copycat.ticks_config import TicksConfig
from tests.helpers.boot import BootedClient
from tests.helpers.fake_sources import FakeStockSource
from tests.helpers.fake_txo import FakeTxoSource
from tests.helpers.wait import wait_until
from tests.server.test_stock_engine import FakeSource, _drain, _quote
from tests.server.test_stock_routes import TICK_MSG

#: 試撮窗內的 UTC PreciseTime(台北 08:50:00 = UTC 00:50:00)
_TRIAL_PRECISE = "5000000000"
_DAY = _dt.date(2026, 7, 21)


async def _make(
    tmp_path: Path, *, flush_secs: float = 0.05, trade_date: str = "2026-07-21"
) -> tuple[StockEngine, FakeSource]:
    src = FakeSource()
    persist = TickPersist(TicksConfig(dir=str(tmp_path), flush_secs=flush_secs))
    engine = StockEngine(
        src, trade_date=trade_date, throttle_secs=0.01, checkpoint=False, tick_persist=persist
    )
    await engine.start()
    await engine.set_main("2330")
    assert src.on_message is not None
    return engine, src


def _rows(tmp_path: Path, day: str = "20260721") -> list[dict]:
    text = (tmp_path / f"{day}.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line]


class _TickRecorder:
    """SignalSink 的最小實作:只記 engine `ingest` 為真的 tick(存檔母體的獨立來源)。"""

    def __init__(self) -> None:
        self.ticks: list[StockTick] = []

    def on_tick(self, code: str, tick: StockTick, state: StockDayState) -> None:
        self.ticks.append(tick)

    def on_book(self, code: str, state: StockDayState) -> None:
        pass

    def on_rollover_pending(self, new_date: str) -> None:
        pass

    def on_rollover(self) -> None:
        pass

    def on_watchlist(self, codes: list[str]) -> None:
        pass


class TestTradeRow:
    async def test_three_messages_write_exactly_one_trade_row(self, tmp_path: Path) -> None:
        """tracer bullet:成交 / 試撮成交 / 同累積量重複 → jsonl 剛好一列,欄位全集逐字。"""
        engine, src = await _make(tmp_path)
        assert src.on_message is not None
        src.on_message(_quote(cum=1))
        src.on_message(_quote(cum=2, precise=_TRIAL_PRECISE))  # 試撮:ingest False
        src.on_message(_quote(cum=1))  # 重複累積量:ingest False
        await _drain(engine)
        await engine.close()

        rows = _rows(tmp_path)
        assert len(rows) == 1
        row = rows[0]
        recv_ns = row.pop("recv_ns")
        assert isinstance(recv_ns, int) and recv_ns > 1_700_000_000_000_000_000
        assert row == {
            "kind": "trade",
            "code": "2330",
            "trade_date": "2026-07-21",
            "msg_seq": 1,
            "precise_time": "25751000000",
            "trade_status": "0",
            "bid0": 2_375_000,
            "bid1": None,
            "bid2": None,
            "bid3": None,
            "bid4": None,
            "bidq0": 10,
            "bidq1": None,
            "bidq2": None,
            "bidq3": None,
            "bidq4": None,
            "ask0": 2_380_000,
            "ask1": None,
            "ask2": None,
            "ask3": None,
            "ask4": None,
            "askq0": 10,
            "askq1": None,
            "askq2": None,
            "askq3": None,
            "askq4": None,
            "time": "10:57:51.000",
            "ms": 39_471_000,  # 10:57:51.000 台北當日毫秒
            "price_milli": 2_380_000,
            "qty": 1,
            "cum_vol": 1,
            "flag": None,
            "side": "outer",  # 2380 ≥ ask 2380
            "seq": 1,
        }

    async def test_msg_seq_counts_every_message_and_recv_ns_is_monotonic(
        self, tmp_path: Path
    ) -> None:
        """被擋的訊息(試撮 / 重複)也各佔一號:第四則成交的 `msg_seq` = 4。"""
        engine, src = await _make(tmp_path)
        assert src.on_message is not None
        src.on_message(_quote(cum=1))
        src.on_message(_quote(cum=2, precise=_TRIAL_PRECISE))
        src.on_message(_quote(cum=1))
        src.on_message(_quote(cum=2) | {"FlagOfBuySell": "1"})
        await _drain(engine)
        await engine.close()

        rows = _rows(tmp_path)
        assert [r["msg_seq"] for r in rows] == [1, 4]
        assert rows[0]["recv_ns"] <= rows[1]["recv_ns"]
        assert rows[1]["flag"] == "1" and rows[1]["side"] == "inner"
        assert rows[1]["seq"] == 2

    async def test_five_levels_are_stored_after_trade(self, tmp_path: Path) -> None:
        engine, src = await _make(tmp_path)
        assert src.on_message is not None
        src.on_message(
            _quote(cum=1)
            | {"Bid1": "2370", "BidVolume1": "20", "Ask1": "2385", "AskVolume1": "7", "Ask2": "0"}
        )
        await _drain(engine)
        await engine.close()
        (row,) = _rows(tmp_path)
        assert (row["bid1"], row["bidq1"]) == (2_370_000, 20)
        assert (row["ask1"], row["askq1"]) == (2_385_000, 7)
        assert (row["ask2"], row["askq2"]) == (0, 0)  # 市價佇列 0 是真資料,原樣保留


class TestFileNaming:
    async def test_rows_land_in_the_file_of_their_own_trade_date(self, tmp_path: Path) -> None:
        engine, src = await _make(tmp_path)
        assert src.on_message is not None
        src.on_message(_quote(cum=1))
        await _drain(engine)
        engine.rollover_stage1("2026-07-22")
        src.on_message(_quote(cum=5, date="20260722"))
        await _drain(engine)
        await engine.close()

        assert [r["trade_date"] for r in _rows(tmp_path, "20260721")] == ["2026-07-21"]
        assert [r["trade_date"] for r in _rows(tmp_path, "20260722")] == ["2026-07-22"]

    async def test_same_day_restart_appends_instead_of_overwriting(self, tmp_path: Path) -> None:
        engine, src = await _make(tmp_path)
        assert src.on_message is not None
        src.on_message(_quote(cum=1))
        await _drain(engine)
        await engine.close()

        engine2, src2 = await _make(tmp_path)  # 同日重建 engine = 重啟
        assert src2.on_message is not None
        src2.on_message(_quote(cum=7))
        await _drain(engine2)
        await engine2.close()

        rows = _rows(tmp_path)
        assert [r["cum_vol"] for r in rows] == [1, 7]
        assert [r["msg_seq"] for r in rows] == [1, 1]  # 進程內序號,重啟歸零


class TestFlush:
    async def test_rows_become_readable_after_flush_interval_without_close(
        self, tmp_path: Path
    ) -> None:
        engine, src = await _make(tmp_path, flush_secs=0.05)
        assert src.on_message is not None
        src.on_message(_quote(cum=1))
        await wait_until(
            lambda: (tmp_path / "20260721.jsonl").exists() and len(_rows(tmp_path)) == 1
        )
        src.on_message(_quote(cum=2))
        await wait_until(lambda: len(_rows(tmp_path)) == 2)
        await engine.close()


class TestLoadDay:
    async def test_load_day_rows_round_trip_to_the_engine_stock_tick(self, tmp_path: Path) -> None:
        engine, src = await _make(tmp_path)
        recorder = _TickRecorder()
        engine.attach_signal_hub(recorder)
        assert src.on_message is not None
        src.on_message(_quote(cum=1) | {"Bid1": "2370", "BidVolume1": "20"})
        src.on_message(_quote(cum=3, price="2385", qty="2") | {"FlagOfBuySell": "2"})
        await _drain(engine)
        await engine.close()

        rows = load_day(_DAY, tmp_path)
        assert [type(r) for r in rows] == [TickRow, TickRow]
        assert [r.kind for r in rows] == ["trade", "trade"]
        assert [r.to_stock_tick() for r in rows] == recorder.ticks
        assert rows[1].msg_seq == 2 and rows[1].bidq0 == 10

    def test_load_day_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_day(_DAY, tmp_path)


_BOOK3 = {  # 三層買、一層賣的基準簿
    "Bid1": "2370",
    "BidVolume1": "20",
    "Bid2": "2365",
    "BidVolume2": "30",
}


class TestBookRow:
    async def test_book_row_only_when_any_of_twenty_numbers_changes(self, tmp_path: Path) -> None:
        """成交、簿變(第三檔量改)、簿不變(逐字重推)、只買一變 → 三列(成交 + 兩簿),重複簿計數 1。"""
        src = FakeSource()
        persist = TickPersist(TicksConfig(dir=str(tmp_path), flush_secs=0.05))
        engine = StockEngine(
            src, trade_date="2026-07-21", throttle_secs=0.01, checkpoint=False, tick_persist=persist
        )
        await engine.start()
        await engine.set_main("2330")
        assert src.on_message is not None
        src.on_message(_quote(cum=1) | _BOOK3)  # 成交(五檔成基準)
        src.on_message(_quote(cum=1) | _BOOK3 | {"BidVolume2": "31"})  # 第三檔量改 → 簿列
        src.on_message(_quote(cum=1) | _BOOK3 | {"BidVolume2": "31"})  # 逐字重推 → 不寫、計數
        src.on_message(_quote(cum=1, bid="2376") | _BOOK3 | {"BidVolume2": "31"})  # 買一變 → 簿列
        await _drain(engine)
        await engine.close()

        rows = _rows(tmp_path)
        assert [(r["kind"], r["msg_seq"]) for r in rows] == [("trade", 1), ("book", 2), ("book", 4)]
        assert persist.dup_books == 1
        book = rows[1]
        assert book["bidq2"] == 31 and book["bid0"] == 2_375_000
        assert book["precise_time"] == "25751000000"  # 殘影照存(語意 = 在哪筆成交之後)
        assert book["trade_date"] == "2026-07-21"
        assert "price_milli" not in book and "time" not in book  # 簿列沒有成交專屬欄
        assert rows[2]["bid0"] == 2_376_000

    async def test_trade_row_updates_the_basis_so_identical_book_after_trade_is_skipped(
        self, tmp_path: Path
    ) -> None:
        engine, src = await _make(tmp_path)
        assert src.on_message is not None
        src.on_message(_quote(cum=1) | _BOOK3)
        src.on_message(_quote(cum=1) | _BOOK3)  # 成交後緊接相同五檔 → 不寫
        src.on_message(_quote(cum=2) | _BOOK3)  # 再成交,五檔沒變 → 只有成交列
        await _drain(engine)
        await engine.close()
        assert [r["kind"] for r in _rows(tmp_path)] == ["trade", "trade"]

    async def test_basis_is_per_code(self, tmp_path: Path) -> None:
        engine, src = await _make(tmp_path)
        await engine.set_watchlist(["2330", "2317"])
        assert src.on_message is not None
        src.on_message(_quote("2330", cum=1, bid="2375"))
        src.on_message(_quote("2317", cum=1, bid="100", ask="101"))
        src.on_message(_quote("2330", cum=1, bid="2375"))  # 2330 沒變 → 不寫
        src.on_message(_quote("2317", cum=1, bid="100", ask="101"))  # 2317 沒變 → 不寫
        src.on_message(_quote("2317", cum=1, bid="99", ask="101"))  # 2317 變 → 簿列
        await _drain(engine)
        await engine.close()
        assert [(r["code"], r["kind"]) for r in _rows(tmp_path)] == [
            ("2330", "trade"),
            ("2317", "trade"),
            ("2317", "book"),
        ]

    async def test_load_day_returns_both_kinds_and_the_row_before_a_trade_is_the_pre_trade_book(
        self, tmp_path: Path
    ) -> None:
        engine, src = await _make(tmp_path)
        assert src.on_message is not None
        src.on_message(_quote(cum=1))
        src.on_message(_quote(cum=1, bid="2376"))  # 簿變 = 下一筆成交前的簿
        src.on_message(_quote(cum=2, bid="2377"))  # 成交後簿又變
        await _drain(engine)
        await engine.close()

        rows = load_day(_DAY, tmp_path)
        assert [(r.kind, r.msg_seq) for r in rows] == [("trade", 1), ("book", 2), ("trade", 3)]
        assert rows[1].bid0 == 2_376_000 and rows[2].bid0 == 2_377_000
        assert rows[1].price_milli is None and rows[1].time is None
        with pytest.raises(ValueError):
            rows[1].to_stock_tick()


class _FailingFile(io.StringIO):
    """寫入即 OSError 的 handle(硬碟滿 / 權限)。"""

    def write(self, s: str) -> int:
        raise OSError(28, "No space left on device")


def _opener_failing_on(days: set[str]) -> Callable[[Path], TextIO]:
    """指定日期的檔給壞 handle,其餘走真檔。"""

    def _open(path: Path) -> TextIO:
        if path.stem in days:
            return _FailingFile()
        return open(path, "a", buffering=64 * 1024, encoding="utf-8", newline="\n")

    return _open


def _stat_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    """每日那一行(字面 `tick 存檔 <YYYY-MM-DD>:…`);停寫 WARNING 另有前綴,不混入。"""
    return [
        r.getMessage()
        for r in caplog.records
        if re.match(r"^tick 存檔 \d{4}-\d{2}-\d{2}:", r.getMessage())
    ]


class TestResilience:
    _LOGGER = "copycat.live.tick_persist"

    async def test_write_error_warns_once_stops_for_the_day_and_never_touches_the_engine(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        src = FakeSource()
        persist = TickPersist(
            TicksConfig(dir=str(tmp_path), flush_secs=3600.0),
            opener=_opener_failing_on({"20260721"}),
        )
        engine = StockEngine(
            src, trade_date="2026-07-21", throttle_secs=0.01, checkpoint=False, tick_persist=persist
        )
        recorder = _TickRecorder()
        engine.attach_signal_hub(recorder)
        await engine.start()
        await engine.set_main("2330")
        assert src.on_message is not None
        with caplog.at_level(logging.INFO, logger=self._LOGGER):
            src.on_message(_quote(cum=1))
            src.on_message(_quote(cum=2))
            src.on_message(_quote(cum=2, bid="2376"))  # 簿變
            await _drain(engine)
            warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
            assert len(warnings) == 1 and "20260721" in warnings[0].getMessage()
            assert len(recorder.ticks) == 2  # 訊號層照常
            assert len(engine.snapshot("2330")["ticks"]) == 2  # 看盤成交明細照常
            await engine.close()
        assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1
        assert not (tmp_path / "20260721.jsonl").exists()
        assert _stat_lines(caplog) == [
            "tick 存檔 2026-07-21:成交 0 / 簿 0 / 重複簿略過 0 / flush 0 / 寫入失敗 1"
        ]

    async def test_next_day_re_arms_after_a_failed_day(self, tmp_path: Path) -> None:
        src = FakeSource()
        persist = TickPersist(
            TicksConfig(dir=str(tmp_path), flush_secs=0.05),
            opener=_opener_failing_on({"20260721"}),
        )
        engine = StockEngine(
            src, trade_date="2026-07-21", throttle_secs=0.01, checkpoint=False, tick_persist=persist
        )
        await engine.start()
        await engine.set_main("2330")
        assert src.on_message is not None
        src.on_message(_quote(cum=1))  # 當日停寫
        await _drain(engine)
        engine.rollover_stage1("2026-07-22")
        src.on_message(_quote(cum=5, date="20260722"))
        await _drain(engine)
        await engine.close()
        assert not (tmp_path / "20260721.jsonl").exists()
        assert [r["cum_vol"] for r in _rows(tmp_path, "20260722")] == [5]

    async def test_disabled_writes_nothing_and_creates_no_dir(self, tmp_path: Path) -> None:
        src = FakeSource()
        persist = TickPersist(TicksConfig(enabled=False, dir=str(tmp_path / "ticks")))
        engine = StockEngine(
            src, trade_date="2026-07-21", throttle_secs=0.01, checkpoint=False, tick_persist=persist
        )
        await engine.start()
        await engine.set_main("2330")
        assert src.on_message is not None
        src.on_message(_quote(cum=1))
        await _drain(engine)
        await engine.close()
        assert not (tmp_path / "ticks").exists()

    async def test_close_flushes_rows_that_never_hit_the_flush_interval(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        engine, src = await _make(tmp_path, flush_secs=3600.0)
        assert src.on_message is not None
        src.on_message(_quote(cum=1) | _BOOK3)
        src.on_message(_quote(cum=1) | _BOOK3)  # 重複簿
        src.on_message(_quote(cum=1) | _BOOK3 | {"BidVolume2": "31"})  # 簿列
        await _drain(engine)
        assert not (tmp_path / "20260721.jsonl").read_text(encoding="utf-8")  # 還在緩衝
        with caplog.at_level(logging.INFO, logger=self._LOGGER):
            await engine.close()
        assert [r["kind"] for r in _rows(tmp_path)] == ["trade", "book"]
        assert _stat_lines(caplog) == [
            "tick 存檔 2026-07-21:成交 1 / 簿 1 / 重複簿略過 1 / flush 0 / 寫入失敗 0"
        ]

    async def test_stage2_prints_old_day_then_counts_restart_for_the_new_day(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        engine, src = await _make(tmp_path, flush_secs=0.05)
        assert src.on_message is not None
        with caplog.at_level(logging.INFO, logger=self._LOGGER):
            src.on_message(_quote(cum=1))
            await wait_until(lambda: len(_rows(tmp_path)) == 1)  # 至少 flush 一次
            engine.rollover_stage1("2026-07-22")
            src.on_message(_quote(cum=5, date="20260722"))
            src.on_message(_quote(cum=5, date="20260722", bid="2376"))
            await _drain(engine)
            lines = _stat_lines(caplog)
            assert len(lines) == 1
            assert re.fullmatch(
                r"tick 存檔 2026-07-21:成交 1 / 簿 0 / 重複簿略過 0 / flush [1-9]\d* / 寫入失敗 0",
                lines[0],
            )
            await engine.close()
        lines = _stat_lines(caplog)
        assert len(lines) == 2
        assert re.fullmatch(
            r"tick 存檔 2026-07-22:成交 1 / 簿 1 / 重複簿略過 0 / flush \d+ / 寫入失敗 0", lines[1]
        )


class TestAppWiring:
    """`create_app(ticks_config=…)` 真的到 engine:漏傳的失效樣態是整條存檔靜默不起。"""

    @staticmethod
    def _boot(tmp_path: Path, cfg: TicksConfig) -> tuple[BootedClient, FakeStockSource]:
        fake = FakeStockSource()
        app = create_app(
            FakeTxoSource(),
            stock_source=fake,
            stock_watchlist_path=tmp_path / "watchlist.json",
            ticks_config=cfg,
            throttle_secs=0.01,
        )
        return BootedClient(app, raise_server_exceptions=False), fake

    def test_enabled_config_writes_the_trade_row_under_the_configured_dir(
        self, tmp_path: Path
    ) -> None:
        client, fake = self._boot(
            tmp_path, TicksConfig(dir=str(tmp_path / "ticks"), flush_secs=3600.0)
        )
        with client:
            client.get("/api/stock/state/2330")  # set_main → 訂閱
            assert fake.on_message is not None
            fake.on_message(dict(TICK_MSG))
            engine = client.app.state.stock  # type: ignore[attr-defined]
            _wait_sync(lambda: len(engine.snapshot("2330")["ticks"]) == 1)
        rows = _rows(tmp_path / "ticks")  # lifespan 關機 flush 後才讀得到
        assert [(r["kind"], r["code"], r["cum_vol"]) for r in rows] == [("trade", "2330", 1)]

    def test_disabled_config_creates_nothing(self, tmp_path: Path) -> None:
        client, fake = self._boot(tmp_path, TicksConfig(enabled=False, dir=str(tmp_path / "ticks")))
        with client:
            client.get("/api/stock/state/2330")
            assert fake.on_message is not None
            fake.on_message(dict(TICK_MSG))
            engine = client.app.state.stock  # type: ignore[attr-defined]
            _wait_sync(lambda: len(engine.snapshot("2330")["ticks"]) == 1)
        assert not (tmp_path / "ticks").exists()


def _wait_sync(pred: Callable[[], bool], timeout: float = 2.0) -> None:
    """TestClient 的同步世界:loop 在別的 thread,輪詢 `pred` 直到成立。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return
        time.sleep(0.005)
    raise AssertionError(f"條件未在 {timeout}s 內成立")
