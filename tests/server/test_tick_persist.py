"""S1 盤中 tick 存檔(spec #257):餵達錢訊息、看 jsonl。

沿 `test_stock_engine` 的 fake source + engine 鷹架;只斷言檔案內容與 `load_day` 讀回,
不碰 handle / 緩衝 / 私有計數器。
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import pytest

from copycat.live.stock_models import StockTick
from copycat.live.stock_state import StockDayState
from copycat.live.tick_persist import TickPersist
from copycat.server.stock_engine import StockEngine
from copycat.ticks import TickRow, load_day
from copycat.ticks_config import TicksConfig
from tests.helpers.wait import wait_until
from tests.server.test_stock_engine import FakeSource, _drain, _quote

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
