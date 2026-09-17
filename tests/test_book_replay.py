"""簿重播引擎(spec #265 / ticket #267)—— 唯一測試 seam = `copycat.book_replay` 公開介面。

餵 `TickRow` 序列,斷言吐出的每則五檔、兩把時間尺(收到時刻軸 / 文字標籤時刻)、成交欄位,以及外掛檔編碼的 round-trip。
不對內部狀態開測試孔;預期值一律寫死字面(五檔版位由本檔 `_tuple` 依公開文件的欄序獨立排出)。
"""

from __future__ import annotations

import base64
import datetime as _dt
import gzip
import json
from collections.abc import Callable
from typing import Any

import pytest

from copycat.book_replay import (
    BookReplay,
    Eaten,
    EnteredView,
    LeftView,
    LevelChange,
    PluginFormatError,
    Reappeared,
    Trade,
    book_at,
    decode,
    encode,
    parse_plugin_js,
    plugin_js,
    replay_books,
)
from copycat.ticks import TickRow

_DATE = "2026-09-16"
_TPE = _dt.timezone(_dt.timedelta(hours=8))

Level = tuple[int, int]  # (價 毫元, 量 張)


def _ns(hms: str) -> int:
    """台北 2026-09-16 `HH:MM:SS.fff` → epoch 奈秒(`recv_ns` 的尺)。"""
    at = _dt.datetime.strptime(f"{_DATE} {hms}", "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=_TPE)
    return round(at.timestamp() * 1000) * 1_000_000


def _ms(hms: str) -> int:
    """台北 `HH:MM:SS.fff` → 當日毫秒(`TickRow.ms` 的尺)。"""
    hh, mm, rest = hms.split(":")
    ss, _, frac = rest.partition(".")
    return ((int(hh) * 60 + int(mm)) * 60 + int(ss)) * 1000 + int(frac)


def _plus_ms(hms: str, ms: int) -> str:
    """台北 `HH:MM:SS.fff` 往後 `ms` 毫秒(同一天)。"""
    total = _ms(hms) + ms
    return f"{total // 3_600_000:02d}:{total // 60_000 % 60:02d}:{total // 1000 % 60:02d}.{total % 1000:03d}"


def _side_fields(prefix: str, levels: list[Level]) -> dict[str, int | None]:
    out: dict[str, int | None] = {}
    for i in range(5):
        price, qty = levels[i] if i < len(levels) else (None, None)
        out[f"{prefix}{i}"] = price
        out[f"{prefix}q{i}"] = qty
    return out


def _row(
    kind: str,
    code: str,
    msg_seq: int,
    *,
    recv: str,
    time: str | None = None,
    bid: list[Level] | None = None,
    ask: list[Level] | None = None,
    trade_date: str = _DATE,
    price: int = 100_000,
    qty: int = 1,
    side: str = "outer",
) -> TickRow:
    fields: dict[str, Any] = {
        "kind": kind,
        "code": code,
        "trade_date": trade_date,
        "msg_seq": msg_seq,
        "recv_ns": _ns(recv),
        "precise_time": "10003000000",
        "trade_status": "0",
        **_side_fields("bid", bid or []),
        **_side_fields("ask", ask or []),
    }
    if kind == "trade":
        assert time is not None
        fields |= {
            "time": time,
            "ms": _ms(time),
            "price_milli": price,
            "qty": qty,
            "cum_vol": msg_seq,
            "flag": "2",
            "side": side,
            "seq": msg_seq,
        }
    return TickRow(**fields)


def _tuple(
    bid: list[Level] | None = None, ask: list[Level] | None = None
) -> tuple[int | None, ...]:
    """五檔 20 格的公開欄序:買價 0–4、買量 0–4、賣價 0–4、賣量 0–4;缺層 None。"""

    def side(levels: list[Level]) -> tuple[list[int | None], list[int | None]]:
        prices: list[int | None] = [p for p, _ in levels] + [None] * (5 - len(levels))
        qtys: list[int | None] = [q for _, q in levels] + [None] * (5 - len(levels))
        return prices, qtys

    bp, bq = side(bid or [])
    ap, aq = side(ask or [])
    return tuple(bp + bq + ap + aq)


class TestBookReplayOrdering:
    def test_groups_by_code_and_orders_each_code_by_msg_seq(self) -> None:
        rows = [
            _row("book", "2426", 30, recv="09:00:01.000", bid=[(98_900, 5)], ask=[(99_000, 7)]),
            _row(
                "trade",
                "3441",
                10,
                recv="09:00:00.600",
                time="09:00:00.000",
                bid=[(180_500, 2)],
                ask=[(181_000, 9)],
            ),
            _row(
                "trade",
                "2426",
                20,
                recv="09:00:00.700",
                time="09:00:00.100",
                bid=[(98_900, 3)],
                ask=[(99_000, 7)],
            ),
            _row("book", "2426", 25, recv="09:00:00.800", bid=[(98_900, 4)], ask=[(99_000, 7)]),
        ]

        result = replay_books(rows)

        assert sorted(result) == ["2426", "3441"]
        day = result["2426"]
        assert (day.code, day.trade_date) == ("2426", "2026-09-16")
        assert [f.msg_seq for f in day.frames] == [20, 25, 30]
        assert [f.kind for f in day.frames] == ["trade", "book", "book"]
        assert [f.book for f in day.frames] == [
            _tuple(bid=[(98_900, 3)], ask=[(99_000, 7)]),
            _tuple(bid=[(98_900, 4)], ask=[(99_000, 7)]),
            _tuple(bid=[(98_900, 5)], ask=[(99_000, 7)]),
        ]
        assert [f.msg_seq for f in result["3441"].frames] == [10]
        assert result["3441"].frames[0].book == _tuple(bid=[(180_500, 2)], ask=[(181_000, 9)])

    def test_one_call_covers_one_trading_day(self) -> None:
        rows = [
            _row("book", "2426", 1, recv="09:00:00.050", bid=[(98_900, 1)]),
            _row(
                "book", "2426", 2, recv="09:00:00.090", bid=[(98_900, 2)], trade_date="2026-09-15"
            ),
        ]

        with pytest.raises(ValueError, match="2026-09-15"):
            replay_books(rows)


class TestClock:
    def test_book_rows_read_as_nth_message_after_the_latest_trade(self) -> None:
        rows = [
            _row("book", "2426", 1, recv="09:00:00.050", bid=[(98_900, 1)]),
            _row("book", "2426", 2, recv="09:00:00.090", bid=[(98_900, 2)]),
            _row("trade", "2426", 3, recv="09:00:00.614", time="09:00:00.000", bid=[(98_900, 2)]),
            _row("book", "2426", 4, recv="09:00:00.700", bid=[(98_900, 3)]),
            _row("book", "2426", 5, recv="09:00:00.720", bid=[(98_900, 4)]),
            _row("trade", "2426", 6, recv="09:00:01.300", time="09:00:00.700", bid=[(98_900, 4)]),
            # 同一達錢時刻的第二筆成交也是時鐘點:其後的簿列從它起算
            _row("trade", "2426", 7, recv="09:00:01.310", time="09:00:00.700", bid=[(98_900, 3)]),
            _row("book", "2426", 8, recv="09:00:01.400", bid=[(98_900, 5)]),
        ]

        frames = replay_books(rows)["2426"].frames

        assert [(f.clock_ms, f.after) for f in frames] == [
            (None, 1),  # 首筆成交前:沒有達錢時刻可掛,只數第幾則
            (None, 2),
            (32_400_000, 0),  # 09:00:00.000 成交
            (32_400_000, 1),
            (32_400_000, 2),
            (32_400_700, 0),  # 09:00:00.700
            (32_400_700, 0),
            (32_400_700, 1),
        ]

    def test_a_trade_stamped_hours_after_it_was_received_never_becomes_the_clock(self) -> None:
        """2026-09-16 實錄:1815 在 07:31:22 開機收到前一日 14:30 的盤後成交(寫進當日檔)。
        讓它當時鐘 → 整段開盤簿列的標籤掛在 14:30 之後,09:00:03 那筆再把標籤時刻拉回去。"""
        rows = [
            _row(
                "trade", "1815", 157, recv="07:31:22.730", time="14:30:00.000", bid=[(114_500, 282)]
            ),
            _row("book", "1815", 28_300, recv="09:00:00.100", bid=[(115_000, 205)]),
            _row(
                "trade",
                "1815",
                28_368,
                recv="09:00:03.872",
                time="09:00:03.000",
                bid=[(115_000, 205)],
            ),
            _row("book", "1815", 28_380, recv="09:00:03.890", bid=[(115_000, 206)]),
        ]

        day = replay_books(rows)["1815"]
        frames = day.frames

        assert [(f.clock_ms, f.after) for f in frames] == [
            (None, 1),
            (None, 2),
            (32_403_000, 0),
            (32_403_000, 1),
        ]
        # 它仍是重播的一則(server 看到的就是它),只是不當時鐘點
        assert [f.kind for f in frames] == ["trade", "book", "trade", "book"]
        assert frames[0].book == _tuple(bid=[(114_500, 282)])
        assert day.anomalous_trades == 1

    def test_late_closing_auction_trade_advances_but_an_earlier_stamp_never_rewinds(self) -> None:
        rows = [
            _row("trade", "2426", 1, recv="13:25:00.100", time="13:24:59.500", bid=[(99_100, 3)]),
            _row("book", "2426", 2, recv="13:27:00.000", bid=[(99_100, 900)]),
            # 收盤撮合:達錢時刻 13:30:00.000、server 晚 39.8 秒才收到 —— 真時刻,照推進
            _row("trade", "2426", 3, recv="13:30:39.787", time="13:30:00.000", bid=[(99_100, 31)]),
            # 蓋章早於目前時鐘的成交:標籤時刻不倒退,它算「13:30:00.000 之後第 1 則」
            _row("trade", "2426", 4, recv="13:30:40.000", time="13:29:59.000", bid=[(99_100, 30)]),
            _row("book", "2426", 5, recv="13:30:41.000", bid=[(99_100, 29)]),
        ]

        day = replay_books(rows)["2426"]

        assert [(f.clock_ms, f.after) for f in day.frames] == [
            (48_299_500, 0),
            (48_299_500, 1),
            (48_600_000, 0),
            (48_600_000, 1),
            (48_600_000, 2),
        ]
        assert day.anomalous_trades == 1  # 晚到的收盤撮合不算異常,蓋章倒退的那筆算

    def test_a_few_seconds_of_local_clock_lag_is_not_an_anomaly(self) -> None:
        """本機鐘落後(#236 時鐘偏差)會讓達錢時刻看起來比收到時刻晚幾秒 —— 那是真成交。"""
        rows = [
            _row("trade", "2426", 1, recv="10:00:00.500", time="10:00:03.000", bid=[(99_000, 1)]),
            _row("book", "2426", 2, recv="10:00:00.600", bid=[(99_000, 2)]),
        ]

        frames = replay_books(rows)["2426"].frames

        assert [(f.clock_ms, f.after) for f in frames] == [(36_003_000, 0), (36_003_000, 1)]

    @pytest.mark.parametrize(
        ("stamp", "label", "anomalous"),
        [
            ("10:01:00.500", (36_060_500, 0), 0),  # 晚恰 60.000 秒:還算真成交
            ("10:01:00.501", (None, 1), 1),  # 晚 60.001 秒:收不到的未來
        ],
        ids=["60.000s-late-is-a-clock-point", "60.001s-late-is-not"],
    )
    def test_the_future_tolerance_is_sixty_seconds_inclusive(
        self, stamp: str, label: tuple[int | None, int], anomalous: int
    ) -> None:
        """容差是閉區間的 60 秒。被收窄到秒級時,本機鐘偏(#236)那天整天的標籤會退回「首筆成交前第 N 則」。"""
        rows = [_row("trade", "2426", 1, recv="10:00:00.500", time=stamp, bid=[(99_000, 1)])]

        day = replay_books(rows)["2426"]

        assert [(f.clock_ms, f.after) for f in day.frames] == [label]
        assert day.anomalous_trades == anomalous


class TestRecvAxis:
    def test_every_message_sits_on_a_never_rewinding_server_receive_time_axis(self) -> None:
        """user 2026-09-16 拍板:回看頁拖時間軸 / 十字線 / 對齊委託用 server 收到時刻 —— 達錢即時
        成交時刻只到整秒(2426「11:02:43」一個標籤底下就有 51 則),收到時刻只晚約 0.1 秒。"""
        rows = [
            _row("book", "2426", 1, recv="11:02:43.227", bid=[(99_100, 24)]),
            _row("book", "2426", 2, recv="11:02:43.910", bid=[(99_100, 187)]),
            # 校時把本機鐘往回撥:這一則收到時刻早於前一則 —— 沿用前一則,時間軸不倒退
            _row("book", "2426", 3, recv="11:02:43.610", bid=[(99_100, 186)]),
            _row("trade", "2426", 4, recv="11:02:45.669", time="11:02:45.000", bid=[(99_100, 183)]),
        ]

        frames = replay_books(rows)["2426"].frames

        assert [f.recv_ms for f in frames] == [39_763_227, 39_763_910, 39_763_910, 39_765_669]


class TestTrades:
    def test_trade_messages_carry_the_print_and_book_messages_do_not(self) -> None:
        """user 2026-09-16 拍板:成交則帶成交時刻 / 價 / 張數 / 內外盤。回看頁的「現價」直接讀它 ——
        鎖漲停時買一是價 0 的市價佇列、賣方全空,從五檔推不出現價。"""
        rows = [
            _row(
                "trade",
                "3441",
                1,
                recv="09:03:32.300",
                time="09:03:32.000",
                price=181_000,
                qty=1,
                side="inner",
                bid=[(181_000, 1)],
            ),
            _row("book", "3441", 2, recv="09:03:32.400", bid=[(181_000, 2)]),
            _row(
                "trade",
                "3441",
                3,
                recv="09:09:01.200",
                time="09:09:01.000",
                price=186_000,
                qty=744,
                side="outer",
                bid=[(0, 3_334), (186_000, 181)],
            ),
        ]

        frames = replay_books(rows)["3441"].frames

        assert [f.trade for f in frames] == [
            Trade(ms=32_612_000, price_milli=181_000, qty=1, side="inner"),
            None,
            Trade(ms=32_941_000, price_milli=186_000, qty=744, side="outer"),
        ]


class TestChanges:
    """#269 變動分解:每一則相對同一檔上一則,以價格為鍵、只比兩則都看得到的價位,拆成掛入 / 撤單 / 成交。"""

    def test_more_lots_at_a_price_both_books_show_read_as_placed(self) -> None:
        """#269 驗收「買 99.1 由 24 → 187,+163 掛單」(2426 2026-09-16 11:02:44.025 那一則的形狀)。"""
        ask = [(99_600, 2), (99_700, 422), (99_800, 4_059)]
        rows = [
            _row(
                "book",
                "2426",
                1,
                recv="11:02:43.978",
                bid=[(99_500, 1), (99_400, 10), (99_300, 9), (99_200, 41), (99_100, 24)],
                ask=ask,
            ),
            _row(
                "book",
                "2426",
                2,
                recv="11:02:44.025",
                bid=[(99_500, 1), (99_400, 10), (99_300, 9), (99_200, 41), (99_100, 187)],
                ask=ask,
            ),
        ]

        frames = replay_books(rows)["2426"].frames

        assert frames[0].changes == ()  # 當日第一則沒有前一份簿可比
        assert frames[1].changes == (
            LevelChange(side="bid", price_milli=99_100, before=24, after=187, traded=0),
        )
        change = frames[1].changes[0]
        assert isinstance(change, LevelChange)
        assert (change.added, change.cancelled) == (163, 0)

    def test_fewer_lots_count_the_trade_at_that_price_first_and_the_rest_as_cancelled(
        self,
    ) -> None:
        """#269 驗收:量減少時先扣掉該價位在該則的成交量,剩下的才算撤單(2426 11:02:43.936 賣 99.6 的形狀)。"""
        bid = [(99_500, 1)]
        ask_tail = [(99_700, 422), (99_800, 4_059)]
        rows = [
            _row("book", "2426", 1, recv="11:02:43.935", bid=bid, ask=[(99_600, 22), *ask_tail]),
            _row(
                "trade",
                "2426",
                2,
                recv="11:02:43.936",
                time="11:02:43.000",
                price=99_600,
                qty=4,
                side="outer",
                bid=bid,
                ask=[(99_600, 12), *ask_tail],
            ),
            _row("book", "2426", 3, recv="11:02:43.978", bid=bid, ask=[(99_600, 2), *ask_tail]),
        ]

        frames = replay_books(rows)["2426"].frames

        assert frames[1].changes == (LevelChange("ask", 99_600, before=22, after=12, traded=4),)
        # 那 4 張已在上一則扣過,這一則的 10 張全是撤單
        assert frames[2].changes == (LevelChange("ask", 99_600, before=12, after=2, traded=0),)
        assert [c.cancelled for f in frames for c in f.changes if isinstance(c, LevelChange)] == [
            6,
            10,
        ]

    def test_a_sweep_whose_book_catches_up_messages_later_still_reads_as_traded(self) -> None:
        """2026-09-16 實錄 2489 10:04:31 連吃 8 個價位:前幾則成交附的五檔都還是舊的,最後一則才一次歸 0。
        只扣同一則的成交會把被買走的量寫成撤單(09-16 全日 2.4% 成交量;user 09-17 拍板算成交)。"""
        bid = [(38_900, 23)]
        before = [(38_950, 7), (39_000, 44), (39_050, 45), (39_100, 53)]
        rows = [
            _row("book", "2489", 1, recv="10:04:30.208", bid=bid, ask=before),
            *(
                _row(
                    "trade",
                    "2489",
                    2 + k,
                    recv=f"10:04:31.{208 + k:03d}",
                    time="10:04:31.000",
                    price=price,
                    qty=qty,
                    side="outer",
                    bid=bid,
                    ask=before,  # 五檔還沒反映這筆成交
                )
                for k, (price, qty) in enumerate(before[:3])
            ),
            _row("book", "2489", 5, recv="10:04:31.212", bid=bid, ask=[(39_100, 53)]),
        ]

        frames = replay_books(rows)["2489"].frames

        assert [f.changes for f in frames[1:4]] == [(), (), ()]
        assert frames[4].changes == (
            LevelChange("ask", 38_950, before=7, after=0, traded=7),
            LevelChange("ask", 39_000, before=44, after=0, traded=44),
            LevelChange("ask", 39_050, before=45, after=0, traded=45),
        )

    @pytest.mark.parametrize(
        ("later", "late_ms", "traded"),
        [(8, 800, 10), (9, 800, 0), (2, 1_000, 10), (2, 1_001, 0)],
        ids=["8-messages-later", "9-messages-later", "1000ms-later", "1001ms-later"],
    )
    def test_a_trade_waits_for_its_book_at_most_eight_messages_and_one_second(
        self, later: int, late_ms: int, traded: int
    ) -> None:
        """成交則後面第 `later` 則、`late_ms` 毫秒才減量:8 則與 1 秒內(含)算成交,超過就算撤單。"""
        rows = [
            _row("book", "2489", 1, recv="10:04:30.000", bid=[(38_900, 1)], ask=[(39_000, 10)]),
            _row(
                "trade",
                "2489",
                2,
                recv="10:04:31.000",
                time="10:04:31.000",
                price=39_000,
                qty=10,
                side="outer",
                bid=[(38_900, 1)],
                ask=[(39_000, 10)],
            ),
            # 中間的簿則只動買方,賣方 39.0 還掛著 10 張
            *(
                _row(
                    "book",
                    "2489",
                    2 + k,
                    recv=f"10:04:31.{k:03d}",
                    bid=[(38_900, 1 + k)],
                    ask=[(39_000, 10)],
                )
                for k in range(1, later)
            ),
            _row(
                "book",
                "2489",
                2 + later,
                recv=_plus_ms("10:04:31.000", late_ms),
                bid=[(38_900, later)],
                ask=[],
            ),
        ]

        frames = replay_books(rows)["2489"].frames

        assert frames[-1].changes == (
            LevelChange("ask", 39_000, before=10, after=0, traded=traded),
        )

    def test_a_locked_limit_up_queue_that_shrinks_on_a_trade_reads_as_traded(self) -> None:
        """2026-09-16 實錄 2426 鎖漲停後(11:02:50.868 起):有人賣 5 張、4 張,成交價 99.8,減少的是買方市價排隊
        那一排;成交價與「市價」價位(價 0)對不上也先算成交(09-16 全日 3.0% 成交量;user 09-17 拍板)。"""
        rows = [
            _row(
                "book", "2426", 1, recv="11:02:50.868", bid=[(0, 6_763), (99_800, 480), (99_500, 7)]
            ),
            _row(
                "trade",
                "2426",
                2,
                recv="11:02:50.869",
                time="11:02:50.000",
                price=99_800,
                qty=5,
                side="outer",
                bid=[(0, 6_758), (99_800, 480), (99_500, 7)],
            ),
            _row(
                "trade",
                "2426",
                3,
                recv="11:02:50.869",
                time="11:02:50.000",
                price=99_800,
                qty=4,
                side="outer",
                bid=[(0, 6_754), (99_800, 480), (99_500, 7)],
            ),
            _row(
                "book", "2426", 4, recv="11:02:50.869", bid=[(0, 6_754), (99_800, 478), (99_500, 7)]
            ),
        ]

        frames = replay_books(rows)["2426"].frames

        assert [f.changes for f in frames[1:]] == [
            (LevelChange("bid", 0, before=6_763, after=6_758, traded=5),),
            (LevelChange("bid", 0, before=6_758, after=6_754, traded=4),),
            (LevelChange("bid", 99_800, before=480, after=478, traded=0),),  # 成交都已扣完
        ]


def _at(frame_changes: tuple[object, ...], price: int) -> list[object]:
    """一則變動裡某價位的項目(測試只斷言它關心的價位,其餘價位的變動另有測試)。"""
    return [c for c in frame_changes if getattr(c, "price_milli", None) == price]


class TestView:
    """#269 視野:買方看得到 = 第五檔限價以上、賣方 = 第五檔限價以下,某側不滿五檔 = 整側看得到。
    價位被擠到第五檔之外 = 離開;回到看得到的範圍 = 重新可見,**不**產生掛單(user 2026-09-17 拍板)。"""

    def test_a_fifth_level_pushed_out_and_back_is_never_counted_as_placed(self) -> None:
        """spec 實測回歸:2305 於 2026-09-16 09:07:46–47,46.95 一張單掛了又被賣掉,第五檔 46.7(113 張)
        被擠出去又回來;逐價位直接比會出現「買 46.7 由 0 → 112 張」好幾次(同一筆墊單被數好幾次,零錯誤訊號)。"""
        ask = [(47_000, 139), (47_050, 9), (47_100, 22), (47_150, 11), (47_200, 50)]
        rest = [(46_900, 149), (46_850, 63), (46_800, 97), (46_750, 22)]
        rows = [
            _row("book", "2305", 1, recv="09:07:46.376", bid=[*rest, (46_700, 113)], ask=ask),
            _row("book", "2305", 2, recv="09:07:46.423", bid=[(46_950, 11), *rest], ask=ask),
            _row(
                "trade",
                "2305",
                3,
                recv="09:07:47.365",
                time="09:07:47.000",
                price=46_950,
                qty=11,
                side="inner",
                bid=[*rest, (46_700, 112)],
                ask=ask,
            ),
            _row("book", "2305", 4, recv="09:07:47.410", bid=[(46_950, 1), *rest], ask=ask),
            _row(
                "trade",
                "2305",
                5,
                recv="09:07:47.454",
                time="09:07:47.000",
                price=46_950,
                qty=1,
                side="inner",
                bid=[*rest, (46_700, 112)],
                ask=ask,
            ),
        ]

        frames = replay_books(rows)["2305"].frames

        assert [f.changes for f in frames] == [
            (),
            (
                LevelChange("bid", 46_950, before=0, after=11, traded=0),
                LeftView("bid", 46_700, qty=113),
            ),
            (
                LevelChange("bid", 46_950, before=11, after=0, traded=11),
                Reappeared(
                    "bid",
                    46_700,
                    left_qty=113,
                    now_qty=112,
                    traded_away=0,
                    left_index=1,
                    away_ms=942,
                ),
            ),
            (
                LevelChange("bid", 46_950, before=0, after=1, traded=0),
                LeftView("bid", 46_700, qty=112),
            ),
            (
                LevelChange("bid", 46_950, before=1, after=0, traded=1),
                Reappeared(
                    "bid",
                    46_700,
                    left_qty=112,
                    now_qty=112,
                    traded_away=0,
                    left_index=3,
                    away_ms=44,
                ),
            ),
        ]
        assert [c.net_placed for f in frames for c in f.changes if isinstance(c, Reappeared)] == [
            -1,
            0,
        ]

    def test_a_price_that_changes_sides_stays_in_view_and_reads_as_traded_then_placed(self) -> None:
        """2426 於 2026-09-16 09:00:32–09:03:43 的 92.0:賣方 11 張被一筆 11 張外盤吃光 → 價格漲上去,92.0 當了
        3 分鐘買方價位(期間 149 張成交全是內盤)→ 價格跌回來,賣方新掛 16 張。grilling 當時把「換到買方」當成
        賣方看不到,算出「賣 92.0 離開 11 → 回來 16、期間成交 149、淨掛 +154」—— 賣方真正新掛的只有 16 張
        (user 2026-09-17 拍板照實際經過算,驗收樣本改用 2426 買 98.0)。"""
        bid_low = [(91_700, 1), (91_600, 18), (91_500, 15), (91_400, 12), (91_300, 17)]
        ask_start = [(92_000, 11), (92_100, 30), (92_200, 2), (92_300, 5), (92_400, 5)]
        ask_after = [(92_100, 11), (92_200, 2), (92_300, 5), (92_400, 5), (92_500, 4)]
        rows = [
            _row("book", "2426", 1, recv="09:00:32.987", bid=bid_low, ask=ask_start),
            _row(
                "trade",
                "2426",
                2,
                recv="09:00:33.058",
                time="09:00:32.000",
                price=92_000,
                qty=11,
                side="outer",
                bid=bid_low,
                ask=ask_start,  # 五檔還沒反映這筆成交
            ),
            _row(
                "trade",
                "2426",
                3,
                recv="09:00:33.058",
                time="09:00:32.000",
                price=92_100,
                qty=19,
                side="outer",
                bid=bid_low,
                ask=ask_after,
            ),
            _row(
                "book",
                "2426",
                4,
                recv="09:00:34.783",
                bid=[(92_000, 1), (91_900, 6), (91_800, 6), (91_700, 24), (91_600, 29)],
                ask=ask_after,
            ),
            _row(
                "trade",
                "2426",
                5,
                recv="09:00:34.789",
                time="09:00:34.000",
                price=92_000,
                qty=1,
                side="inner",
                bid=[(91_900, 6), (91_800, 4), (91_700, 24), (91_600, 29), (91_500, 34)],
                ask=ask_after,
            ),
            _row(
                "book",
                "2426",
                6,
                recv="09:03:43.761",
                bid=[(91_900, 26), (91_800, 35), (91_700, 32), (91_600, 20), (91_500, 58)],
                ask=[(92_000, 16), (92_100, 8), (92_200, 16), (92_300, 44), (92_400, 53)],
            ),
        ]

        frames = replay_books(rows)["2426"].frames

        assert [_at(f.changes, 92_000) for f in frames] == [
            [],
            [],
            [LevelChange("ask", 92_000, before=11, after=0, traded=11)],
            [LevelChange("bid", 92_000, before=0, after=1, traded=0)],
            [LevelChange("bid", 92_000, before=1, after=0, traded=1)],
            [LevelChange("ask", 92_000, before=0, after=16, traded=0)],
        ]

    def test_back_in_view_reports_left_and_now_lots_and_the_net_placed_while_away(self) -> None:
        """#269 驗收樣本(user 2026-09-17 改定):2426 於 2026-09-16 09:46:00 有人在 98.5 掛 2 張買單,原本
        第五檔的買 98.0(39 張)被擠出去;09:48:35 那 2 張被賣掉,98.0 回到第五檔已是 120 張 ——
        離開時 39 → 現在 120、期間成交 0、淨掛 +81、離開 2 分 35 秒。"""
        ask_a = [(98_700, 78), (98_800, 199), (98_900, 125), (99_000, 639), (99_100, 66)]
        ask_b = [(98_600, 25), (98_700, 84), (98_800, 17), (98_900, 12), (99_000, 69)]
        rows = [
            _row(
                "book",
                "2426",
                1,
                recv="09:46:00.356",
                bid=[(98_400, 22), (98_300, 40), (98_200, 65), (98_100, 81), (98_000, 39)],
                ask=ask_a,
            ),
            _row(
                "book",
                "2426",
                2,
                recv="09:46:00.358",
                bid=[(98_500, 2), (98_400, 22), (98_300, 40), (98_200, 65), (98_100, 81)],
                ask=ask_a,
            ),
            _row(
                "book",
                "2426",
                3,
                recv="09:48:34.890",
                bid=[(98_500, 52), (98_400, 11), (98_300, 28), (98_200, 31), (98_100, 30)],
                ask=ask_b,
            ),
            _row(
                "trade",
                "2426",
                4,
                recv="09:48:35.264",
                time="09:48:35.000",
                price=98_500,
                qty=50,
                side="inner",
                bid=[(98_500, 2), (98_400, 11), (98_300, 28), (98_200, 31), (98_100, 30)],
                ask=ask_b,
            ),
            _row(
                "trade",
                "2426",
                5,
                recv="09:48:35.269",
                time="09:48:35.000",
                price=98_500,
                qty=2,
                side="inner",
                bid=[(98_400, 11), (98_300, 28), (98_200, 31), (98_100, 30), (98_000, 120)],
                ask=ask_b,
            ),
        ]

        frames = replay_books(rows)["2426"].frames

        assert [_at(f.changes, 98_000) for f in frames] == [
            [],
            [LeftView("bid", 98_000, qty=39)],
            [],
            [],
            [
                Reappeared(
                    "bid",
                    98_000,
                    left_qty=39,
                    now_qty=120,
                    traded_away=0,
                    left_index=1,
                    away_ms=154_911,  # 2 分 35 秒
                )
            ],
        ]
        (back,) = _at(frames[4].changes, 98_000)
        assert isinstance(back, Reappeared)
        assert back.net_placed == 81

    def test_lots_traded_while_out_of_view_are_added_back_into_the_net_placed(self) -> None:
        """2489 於 2026-09-16:10:04:20 賣 39.2(80 張)被擠出五檔;10:04:31 一筆掃單連吃 8 個價位把它吃光,
        最後一則五檔才更新 —— 回到看得到的範圍時 0 張、離開期間成交 80 → 淨掛 0(被吃掉,不是撤掉)。"""
        rows = _sweep_2489_rows()

        frames = replay_books(rows)["2489"].frames

        assert [_at(f.changes, 39_200) for f in frames] == [
            [],
            [LeftView("ask", 39_200, qty=80)],
            *([[]] * 8),
            [
                Reappeared(
                    "ask",
                    39_200,
                    left_qty=80,
                    now_qty=0,
                    traded_away=80,
                    left_index=1,
                    away_ms=11_056,
                )
            ],
        ]
        (back,) = _at(frames[10].changes, 39_200)
        assert isinstance(back, Reappeared)
        assert back.net_placed == 0

    def test_a_price_seen_for_the_first_time_enters_view_without_counting_as_placed(self) -> None:
        """之前從沒看過的價位帶量進到看得到的範圍(賣方第五檔外的單露出來)= 首次進入五檔,不算掛單。"""
        bid = [(99_900, 3)]
        rows = [
            _row(
                "book",
                "3441",
                1,
                recv="10:00:00.000",
                bid=bid,
                ask=[(100_000, 5), (100_500, 5), (101_000, 5), (101_500, 5), (102_000, 5)],
            ),
            _row(
                "trade",
                "3441",
                2,
                recv="10:00:00.500",
                time="10:00:00.000",
                price=100_000,
                qty=5,
                side="outer",
                bid=bid,
                ask=[(100_500, 5), (101_000, 5), (101_500, 5), (102_000, 5), (102_500, 30)],
            ),
        ]

        frames = replay_books(rows)["3441"].frames

        assert frames[1].changes == (
            LevelChange("ask", 100_000, before=5, after=0, traded=5),
            EnteredView("ask", 102_500, qty=30),
        )

    def test_a_price_that_emptied_before_it_left_comes_back_from_zero(self) -> None:
        """追蹤中的價位在看得到時變 0、再被擠出去:離開不列(0 張沒東西可列);回來仍 0 張且期間沒成交也不列;
        回來時有量 = 重新可見「離開時 0 → 現在 n」,淨掛 = n。"""
        full = [(50_500, 5), (50_400, 5), (50_300, 5)]
        pushed = [(50_700, 1), (50_600, 1), *full]
        rows = [
            _row("book", "2344", 1, recv="10:00:00.000", bid=[*full, (50_200, 5), (50_100, 5)]),
            _row("book", "2344", 2, recv="10:00:01.000", bid=[*full, (50_100, 5), (50_000, 5)]),
            _row("book", "2344", 3, recv="10:00:02.000", bid=pushed),
            _row("book", "2344", 4, recv="10:00:03.000", bid=[*full, (50_100, 5), (50_000, 5)]),
            _row("book", "2344", 5, recv="10:00:04.000", bid=pushed),
            _row("book", "2344", 6, recv="10:00:05.000", bid=[*full, (50_200, 20), (50_100, 5)]),
        ]

        frames = replay_books(rows)["2344"].frames

        assert [_at(f.changes, 50_200) for f in frames] == [
            [],
            [LevelChange("bid", 50_200, before=5, after=0, traded=0)],
            [],  # 0 張被擠出去:不列
            [],  # 回來仍 0 張、期間沒成交:不列
            [],
            [
                Reappeared(
                    "bid",
                    50_200,
                    left_qty=0,
                    now_qty=20,
                    traded_away=0,
                    left_index=4,
                    away_ms=1_000,
                )
            ],
        ]


def _cleared_2305_rows() -> list[TickRow]:
    """2305 於 2026-09-16 09:04:56:成交 46.05 × 81 → 09:04:56.102 五檔全空(清空)→ 09:05:01.174 下一份五檔。"""
    bid = [(46_000, 88), (45_950, 40), (45_900, 11), (45_850, 42), (45_800, 21)]
    ask_before = [(46_050, 81), (46_100, 14), (46_150, 17), (46_200, 77), (46_250, 17)]
    ask_traded = [(46_100, 14), (46_150, 17), (46_200, 77), (46_250, 17), (46_300, 49)]
    return [
        _row("book", "2305", 1, recv="09:04:56.096", bid=bid, ask=ask_before),
        _row(
            "trade",
            "2305",
            2,
            recv="09:04:56.097",
            time="09:04:55.000",
            price=46_050,
            qty=81,
            side="outer",
            bid=bid,
            ask=ask_traded,
        ),
        _row("book", "2305", 3, recv="09:04:56.102", bid=[], ask=[]),
        _row(
            "book",
            "2305",
            4,
            recv="09:05:01.174",
            bid=[(46_000, 12), (45_950, 38), (45_900, 29), (45_850, 36), (45_800, 22)],
            ask=[(46_050, 10), (46_100, 12), (46_150, 27), (46_200, 66), (46_250, 17)],
        ),
    ]


class TestClearedBook:
    """達錢在暫緩撮合開始那一刻送一則買賣兩側全空的五檔,之後改每 5 秒才更新(2026-09-16 10 檔 15 則)。
    那一則是清空,不是所有人同時撤單:不拆變動,下一則跟全空之前最後一份五檔比(user 2026-09-17 拍板)。"""

    def test_a_fully_empty_book_is_skipped_and_the_next_book_compares_with_the_last_real_one(
        self,
    ) -> None:
        """2305 於 2026-09-16 09:04:56.102 五檔全空,下一則 09:05:01.174。"""
        frames = replay_books(_cleared_2305_rows())["2305"].frames

        assert frames[2].book == (None,) * 20
        assert frames[2].changes == ()
        assert frames[3].changes == (
            LevelChange("bid", 46_000, before=88, after=12, traded=0),
            LevelChange("bid", 45_950, before=40, after=38, traded=0),
            LevelChange("bid", 45_900, before=11, after=29, traded=0),
            LevelChange("bid", 45_850, before=42, after=36, traded=0),
            LevelChange("bid", 45_800, before=21, after=22, traded=0),
            LevelChange("ask", 46_050, before=0, after=10, traded=0),
            LevelChange("ask", 46_100, before=14, after=12, traded=0),
            LevelChange("ask", 46_150, before=17, after=27, traded=0),
            LevelChange("ask", 46_200, before=77, after=66, traded=0),
            LeftView("ask", 46_300, qty=49),
        )

    def test_a_trade_right_after_the_empty_book_reads_its_level_from_the_last_real_book(
        self,
    ) -> None:
        """全空之後第一筆成交:檔位看全空之前最後一份五檔(否則一律變成五檔外)。"""
        ask = [(46_050, 10)]
        rows = [
            _row(
                "book",
                "2305",
                1,
                recv="09:04:56.096",
                bid=[(46_000, 88), (45_950, 40), (45_900, 11), (45_850, 42), (45_800, 21)],
                ask=ask,
            ),
            _row("book", "2305", 2, recv="09:04:56.102", bid=[], ask=[]),
            _row(
                "trade",
                "2305",
                3,
                recv="09:05:01.174",
                time="09:05:01.000",
                price=46_000,
                qty=12,
                side="inner",
                bid=[(45_950, 40), (45_900, 11), (45_850, 42), (45_800, 21), (45_750, 5)],
                ask=ask,
            ),
        ]

        frames = replay_books(rows)["2305"].frames

        assert frames[2].eaten == (Eaten("bid", level=1, qty=12),)
        assert frames[2].changes == (
            LevelChange("bid", 46_000, before=88, after=0, traded=12),
            EnteredView("bid", 45_750, qty=5),
        )

    def test_the_plugin_file_keeps_the_cleared_book_and_refuses_changes_written_on_it(
        self,
    ) -> None:
        """回看頁跟 decode 同一套規則:清空那一則沒有變動,下一則的前量是清空之前那一份。"""
        day = replay_books(_cleared_2305_rows())["2305"]
        wire = _wire(day, keyframe_every=2)

        assert decode(wire) == day

        wire["chg"][2] = [7, 46_300, 49]  # 清空那一則寫一項「賣 46.3 首次進入五檔 49 張」
        with pytest.raises(PluginFormatError, match="五檔全空"):
            decode(wire)


class TestEaten:
    """#269 成交明細的吃檔欄:這筆成交吃到成交前那一則五檔的第幾檔、幾張(例「吃 賣1 −12」)。"""

    def test_each_trade_of_a_sweep_names_the_level_it_ate_in_the_book_before_the_sweep(
        self,
    ) -> None:
        """一筆連吃好幾檔(掃單)在這欄現形:2489 10:04:31 吃 賣1 −7、賣2 −44、賣3 −45、賣4 −53、賣5 −21;
        39.2 以上在成交前看不到 → 五檔外;簿則沒有吃檔。"""
        frames = replay_books(_sweep_2489_rows())["2489"].frames

        assert [f.eaten for f in frames] == [
            (),
            (),
            (),
            (Eaten("ask", level=1, qty=7),),
            (Eaten("ask", level=2, qty=44),),
            (Eaten("ask", level=3, qty=45),),
            (Eaten("ask", level=4, qty=53),),
            (Eaten("ask", level=5, qty=21),),
            (Eaten("ask", level=None, qty=80),),
            (Eaten("ask", level=None, qty=34),),
            (Eaten("ask", level=None, qty=56),),
        ]

    def test_a_trade_into_a_locked_limit_up_eats_the_market_queue(self) -> None:
        """2426 11:02:50 鎖漲停後有人賣 5 張:成交價 99.8,吃的是買方市價排隊(level 0),不是限價 99.8 那一檔。"""
        bid = [(0, 6_763), (99_800, 480), (99_500, 7)]
        rows = [
            _row("book", "2426", 1, recv="11:02:50.868", bid=bid),
            _row(
                "trade",
                "2426",
                2,
                recv="11:02:50.869",
                time="11:02:50.000",
                price=99_800,
                qty=5,
                side="outer",
                bid=[(0, 6_758), (99_800, 480), (99_500, 7)],
            ),
        ]

        frames = replay_books(rows)["2426"].frames

        assert frames[1].eaten == (Eaten("bid", level=0, qty=5),)

    def test_levels_count_limit_prices_only_and_a_trade_hidden_by_new_orders_eats_nothing(
        self,
    ) -> None:
        """檔位只數限價(有市價排隊時限價最優仍是 買1);量不減反增(同一則又掛進來)看不出吃了哪一檔 → 不列。"""
        rows = [
            _row(
                "book", "3441", 1, recv="09:00:18.000", bid=[(0, 50), (170_000, 59), (169_500, 78)]
            ),
            _row(
                "trade",
                "3441",
                2,
                recv="09:00:18.740",
                time="09:00:18.000",
                price=169_500,
                qty=8,
                side="inner",
                bid=[(0, 50), (170_000, 59), (169_500, 70)],
            ),
            _row(
                "trade",
                "3441",
                3,
                recv="09:00:18.800",
                time="09:00:18.000",
                price=170_000,
                qty=647,
                side="inner",
                bid=[(0, 50), (170_000, 120), (169_500, 70)],
            ),
        ]

        frames = replay_books(rows)["3441"].frames

        assert [f.eaten for f in frames] == [(), (Eaten("bid", level=2, qty=8),), ()]

    def test_a_trade_counted_while_its_price_was_out_of_view_is_not_taken_again(self) -> None:
        """review round 1 P-01(6209 於 2026-09-16 09:04:10 的形狀):買 78.8 被擠出五檔後,一筆 61 張成交落在
        它身上、同一則 78.8 回到五檔 → 這 61 張算進期間成交,就不能在兩則後 78.8 減 6 張時再扣一次;那 6 張
        是它自己那筆 6 張成交吃的(修前:61 張那筆吃檔變「買1 −6、買五檔外 −55」,6 張那筆變「—」)。"""
        ask = [(79_400, 5)]
        ask_after = [(78_900, 2), (79_000, 27)]
        rows = [
            _row(
                "book",
                "6209",
                1,
                recv="09:02:45.300",
                bid=[(79_200, 3), (79_100, 3), (79_000, 3), (78_900, 3), (78_800, 5)],
                ask=ask,
            ),
            _row(
                "book",
                "6209",
                2,
                recv="09:02:45.318",
                bid=[(79_300, 1), (79_200, 3), (79_100, 3), (79_000, 3), (78_900, 3)],
                ask=ask,
            ),
            _row(
                "trade",
                "6209",
                3,
                recv="09:04:10.204",
                time="09:04:10.000",
                price=78_800,
                qty=61,
                side="inner",
                bid=[(78_800, 6), (78_700, 2), (78_600, 4), (78_500, 6), (78_400, 5)],
                ask=ask_after,
            ),
            _row(
                "book",
                "6209",
                4,
                recv="09:04:10.247",
                bid=[(78_800, 6), (78_700, 2), (78_600, 4), (78_500, 5), (78_400, 5)],
                ask=ask_after,
            ),
            _row(
                "trade",
                "6209",
                5,
                recv="09:04:10.250",
                time="09:04:10.000",
                price=78_800,
                qty=6,
                side="inner",
                bid=[(78_700, 2), (78_600, 4), (78_500, 5), (78_400, 5), (78_300, 6)],
                ask=ask_after,
            ),
        ]

        frames = replay_books(rows)["6209"].frames

        assert _at(frames[2].changes, 78_800) == [
            Reappeared(
                "bid",
                78_800,
                left_qty=5,
                now_qty=6,
                traded_away=61,
                left_index=1,
                away_ms=84_886,
            )
        ]
        assert _at(frames[4].changes, 78_800) == [
            LevelChange("bid", 78_800, before=6, after=0, traded=6)
        ]
        assert [f.eaten for f in frames] == [
            (),
            (),
            (Eaten("bid", level=None, qty=61),),  # 成交當下 78.8 在五檔外
            (),
            (Eaten("bid", level=1, qty=6),),
        ]


def _sweep_2489_rows() -> list[TickRow]:
    """2489 於 2026-09-16 10:04:20–10:04:31(11 則):賣 39.2(80 張)被擠出五檔 → 10:04:31 一筆掃單連吃
    8 個價位(38.95 × 7 … 39.3 × 56),前 7 則成交附的五檔都還是舊的,最後一則才一次更新。"""
    bid_a = [(38_900, 13), (38_850, 11), (38_800, 18), (38_750, 41), (38_700, 24)]
    bid_b = [(38_900, 23), (38_850, 12), (38_800, 18), (38_750, 36), (38_700, 28)]
    ask_b = [(38_950, 7), (39_000, 44), (39_050, 45), (39_100, 53), (39_150, 21)]
    sweep = [
        (38_950, 7, ".208"),
        (39_000, 44, ".208"),
        (39_050, 45, ".209"),
        (39_100, 53, ".210"),
        (39_150, 21, ".211"),
        (39_200, 80, ".211"),
        (39_250, 34, ".211"),
    ]
    return [
        _row(
            "book",
            "2489",
            1,
            recv="10:04:20.107",
            bid=bid_a,
            ask=[(39_000, 38), (39_050, 44), (39_100, 53), (39_150, 20), (39_200, 80)],
        ),
        _row(
            "book",
            "2489",
            2,
            recv="10:04:20.156",
            bid=bid_a,
            ask=[(38_950, 4), (39_000, 38), (39_050, 44), (39_100, 53), (39_150, 20)],
        ),
        _row("book", "2489", 3, recv="10:04:30.208", bid=bid_b, ask=ask_b),
        *(
            _row(
                "trade",
                "2489",
                4 + k,
                recv=f"10:04:31{ms}",
                time="10:04:31.000",
                price=price,
                qty=qty,
                side="outer",
                bid=bid_b,
                ask=ask_b,  # 掃單途中五檔都還是舊的
            )
            for k, (price, qty, ms) in enumerate(sweep)
        ),
        _row(
            "trade",
            "2489",
            11,
            recv="10:04:31.212",
            time="10:04:31.000",
            price=39_300,
            qty=56,
            side="outer",
            bid=[(39_300, 60), (38_900, 23), (38_850, 12), (38_800, 18), (38_750, 36)],
            ask=[(39_350, 28), (39_400, 45), (39_450, 22), (39_500, 118), (39_550, 98)],
        ),
    ]


def _lock_limit_up_rows() -> list[TickRow]:
    """2426 漲停前後的形狀(2026-09-16 實測當日 2,776 則賣方全空):掛單變厚 → 鎖漲停(買一 = 價 0
    的市價佇列、賣方全空)→ 兩邊全空一則 → 打開回到正常。8 則,跨 keyframe 間隔 3 的兩個邊界。"""
    return [
        _row(
            "trade",
            "2426",
            101,
            recv="11:02:40.614",
            time="11:02:40.000",
            bid=[(99_000, 24), (98_900, 50)],
            ask=[(99_100, 12), (99_200, 8)],
        ),
        _row(
            "book",
            "2426",
            102,
            recv="11:02:43.100",
            bid=[(99_000, 187), (98_900, 50)],
            ask=[(99_100, 12), (99_200, 8)],
        ),
        _row(
            "book",
            "2426",
            103,
            recv="11:02:45.000",
            bid=[(99_000, 184), (98_900, 50)],
            ask=[(99_100, 3), (99_200, 8)],
        ),
        _row(
            "trade",
            "2426",
            104,
            recv="11:02:50.614",
            time="11:02:50.000",
            bid=[(0, 3_300), (99_100, 5_000), (99_000, 184)],
            ask=[],
        ),
        _row(
            "book",
            "2426",
            105,
            recv="11:02:51.000",
            bid=[(0, 3_310), (99_100, 5_000), (99_000, 184)],
            ask=[],
        ),
        _row("book", "2426", 106, recv="11:02:52.000", bid=[], ask=[]),
        _row("book", "2426", 107, recv="11:02:53.000", bid=[(0, 3_310), (99_100, 5_020)], ask=[]),
        _row(
            "trade",
            "2426",
            108,
            recv="11:05:00.614",
            time="11:05:00.000",
            bid=[(99_000, 40)],
            ask=[(99_100, 2_000)],
        ),
    ]


def _golden_rows() -> list[TickRow]:
    """外掛檔字面測試用的 4 則(2026-09-16 1815 的形狀):開機收到前一日盤後成交(時刻異常)→ 首筆成交前的
    簿列 → 鎖漲停的成交(買一 = 價 0 的市價佇列、賣方全空)→ 蓋章早於標籤時刻的成交(時刻異常)。
    每筆成交的時刻 / 價 / 張 / 內外盤取彼此不同的值,格序錯位才看得出來。"""
    return [
        _row(
            "trade",
            "1815",
            157,
            recv="07:31:22.730",
            time="14:30:00.000",
            price=114_500,
            qty=2,
            side="inner",
            bid=[(114_500, 282)],
            ask=[(115_000, 40)],
        ),
        _row(
            "book", "1815", 28_300, recv="09:00:00.100", bid=[(115_000, 205)], ask=[(115_500, 12)]
        ),
        _row(
            "trade",
            "1815",
            28_368,
            recv="09:00:03.872",
            time="09:00:03.000",
            price=115_500,
            qty=7,
            side="outer",
            bid=[(0, 1_300), (115_500, 800)],
        ),
        _row(
            "trade",
            "1815",
            28_380,
            recv="09:00:04.000",
            time="09:00:02.000",
            price=115_500,
            qty=1,
            side="neutral",
            bid=[(0, 1_299), (115_500, 800)],
        ),
    ]


def _wire(day: BookReplay, *, keyframe_every: int) -> Any:
    """編碼後走一趟 JSON 往返 = 外掛檔裡實際存的樣子(0 / null 必須分得開);竄改案直接改它。"""
    return json.loads(json.dumps(encode(day, keyframe_every=keyframe_every)))


class TestPluginEncoding:
    def test_round_trip_reproduces_every_frame_across_keyframe_boundaries(self) -> None:
        day = replay_books(_lock_limit_up_rows())["2426"]
        assert day.frames[3].book == _tuple(bid=[(0, 3_300), (99_100, 5_000), (99_000, 184)])
        assert day.frames[5].book == (None,) * 20

        wire = _wire(day, keyframe_every=3)

        assert decode(wire) == day

    def test_payload_layout_matches_the_documented_v2_literal(self) -> None:
        """外掛檔永久保留,回看頁 JS 照模組說明「外掛檔 v2」逐鍵讀。編碼與解碼一起漂的時候 round-trip 照綠,
        只有寫死的字面抓得到(pr-275 review F-01)。v1 → v2(#269)加 `chg`。"""
        day = replay_books(_golden_rows())["1815"]

        payload = encode(day, keyframe_every=2)

        assert payload == {
            "v": 2,
            "code": "1815",
            "date": "2026-09-16",
            "n": 4,
            "fields": [
                *("bid0", "bid1", "bid2", "bid3", "bid4"),
                *("bidq0", "bidq1", "bidq2", "bidq3", "bidq4"),
                *("ask0", "ask1", "ask2", "ask3", "ask4"),
                *("askq0", "askq1", "askq2", "askq3", "askq4"),
            ],
            "kf_every": 2,
            "seq": [157, 28_143, 68, 12],
            "kind": "tbtt",
            # 時刻異常、不當時鐘點的成交則號;其餘成交則都是時鐘點,標籤時刻讀 trade 裡那筆的第一格
            "anomalous": [0, 3],
            "recv": [27_082_730, 5_317_370, 3_772, 128],
            "trade": [
                *(52_200_000, 114_500, 2, "inner"),  # 前一日 14:30 的盤後成交,07:31 開機收到
                *(32_403_000, 115_500, 7, "outer"),
                *(32_402_000, 115_500, 1, "neutral"),  # 09:00:02 早於標籤時刻 09:00:03
            ],
            "kf": [
                [114_500, None, None, None, None, 282, None, None, None, None]
                + [115_000, None, None, None, None, 40, None, None, None, None],
                [0, 115_500, None, None, None, 1_300, 800, None, None, None] + [None] * 10,
            ],
            "d": [
                [0, 114_500, 5, 282, 10, 115_000, 15, 40],
                [0, 115_000, 5, 205, 10, 115_500, 15, 12],
                [0, 0, 1, 115_500, 5, 1_300, 6, 800, 10, None, 15, None],
                [5, 1_299],
            ],
            # 每則的變動,每項 [側別碼(買 0 / 賣 1), 價, 前量, 後量, 成交];同側市價佇列在前、再由最優價往外
            "chg": [
                [],
                [0, 115_000, 0, 205, 0]
                + [0, 114_500, 282, 0, 0]
                + [1, 115_000, 40, 0, 0]
                + [1, 115_500, 0, 12, 0],
                [0, 0, 0, 1_300, 0]
                + [0, 115_500, 0, 800, 0]
                + [0, 115_000, 205, 0, 0]
                + [1, 115_500, 12, 0, 7],  # 同則 115.5 × 7 成交先扣,其餘 5 張撤單
                [0, 0, 1_300, 1_299, 1],  # 市價佇列減少不看成交價:同則 115.5 × 1 先扣
            ],
            # 每筆成交一列 [側別碼, 檔位(限價 1–5、市價佇列 0、五檔外 null), 張, …]
            "eat": [
                [],  # 開機收到的前一日成交:之前沒有簿,看不出吃哪一檔
                [1, 1, 7],  # 吃 賣1 −7
                [0, 0, 1],  # 吃 市價買 −1
            ],
        }

    def test_round_trip_keeps_labels_before_the_first_clock_point_and_on_anomalous_trades(
        self,
    ) -> None:
        """解碼的兩條特例:首筆成交前(沒有標籤時刻,從第 1 則數起)與時刻異常的成交(pr-275 review F-02)。"""
        day = replay_books(_golden_rows())["1815"]
        assert [(f.clock_ms, f.after) for f in day.frames] == [
            (None, 1),
            (None, 2),
            (32_403_000, 0),
            (32_403_000, 1),
        ]
        assert day.anomalous_trades == 2

        wire = _wire(day, keyframe_every=2)

        assert decode(wire) == day

    @pytest.mark.parametrize("keyframe_every", [1, 3, 256])
    def test_jumping_to_any_message_from_its_keyframe_matches_the_book_replay(
        self, keyframe_every: int
    ) -> None:
        """回看頁拖時間軸的解碼規則:取該則之前最近的 keyframe,再套到該則為止的 delta。"""
        day = replay_books(_lock_limit_up_rows())["2426"]
        wire = _wire(day, keyframe_every=keyframe_every)

        assert [book_at(wire, i) for i in range(len(day.frames))] == [f.book for f in day.frames]

    def test_plugin_file_is_one_script_line_carrying_gzip_base64_json(self) -> None:
        """沿用 viewer-cdp-ticks 的外掛檔形態:`<script src>` 懶載入,file:// 直接可讀。"""
        day = replay_books(_lock_limit_up_rows())["2426"]
        payload = encode(day)

        text = plugin_js(payload)

        head, tail = 'window.__bk("2426|2026-09-16","', '");'
        assert text.startswith(head)
        assert text.endswith(tail)
        assert "\n" not in text
        # 瀏覽器那條路:atob → DecompressionStream("gzip") → JSON.parse
        blob = base64.b64decode(text[len(head) : -len(tail)], validate=True)
        # gzip 檔頭第 4–7 byte = MTIME,釘 0 才會「同資料重產逐位元組相同」(不比整段:zlib 版本不同壓出來會變)
        assert blob[4:8] == b"\x00\x00\x00\x00"
        assert decode(json.loads(gzip.decompress(blob))) == day
        assert parse_plugin_js(text) == payload

    def test_decode_refuses_deltas_that_disagree_with_a_later_keyframe(self) -> None:
        """回看頁「播放」走 delta、「跳轉」走 keyframe;兩條路對不上 = 同一刻看到兩份簿,不得放行。"""
        day = replay_books(_lock_limit_up_rows())["2426"]
        wire = _wire(day, keyframe_every=3)
        wire["d"][1] = wire["d"][1] + [19, 777]  # 第 1 則多蓋賣量 4 = 777,第 3 則 keyframe 仍是空

        with pytest.raises(PluginFormatError, match="keyframe"):
            decode(wire)

    @pytest.mark.parametrize(
        ("tamper", "message"),
        [
            (lambda w: w.update(v=99), "版本 99"),
            (lambda w: w.update(n=7), "n=7"),
            (lambda w: w["fields"].reverse(), "欄序"),
            (lambda w: w["kf"].pop(), "keyframe 個數"),
            (lambda w: w["recv"].pop(), "recv"),
            (lambda w: w["trade"].pop(), "trade 長度"),
            (lambda w: w.update(kind=w["kind"].replace("b", "x", 1)), "kind"),
            (lambda w: w.pop("trade"), "缺鍵"),
            (lambda w: w.update(kf_every=0), "kf_every"),
        ],
        ids=[
            "unknown-version",
            "message-count",
            "field-order",
            "missing-keyframe",
            "recv-length",
            "trade-length",
            "kind-char",
            "missing-key",
            "keyframe-interval-zero",
        ],
    )
    def test_decode_refuses_a_header_the_viewer_cannot_trust(
        self, tamper: Callable[[dict[str, Any]], object], message: str
    ) -> None:
        """外掛檔永久保留:一年後讀它的人只能靠檔頭自述,下列檔頭與內容對不上的情形都拒絕。"""
        wire = _wire(replay_books(_lock_limit_up_rows())["2426"], keyframe_every=3)
        tamper(wire)

        with pytest.raises(PluginFormatError, match=message):
            decode(wire)

    @pytest.mark.parametrize(
        ("tamper", "message"),
        [
            (lambda w: w["recv"].__setitem__(1, -5), "倒退"),
            # 第 7 則在最後一個 keyframe(第 6 則)之後:壞 delta 沒有 keyframe 能對出來
            (lambda w: w["d"][7].append(5), "delta 長度"),
            (lambda w: w["d"][7].extend([20, 555]), "欄號"),
            (lambda w: w["d"][7].extend([-1, 555]), "欄號"),  # 負欄號會默默寫進賣量 4
            (lambda w: w["seq"].__setitem__(2, 0), "訊息序號"),
            (lambda w: w["trade"].__setitem__(3, "weird"), "內外盤"),  # 第 0 則成交
        ],
        ids=[
            "recv-rewind",
            "delta-odd-length",
            "delta-field-20",
            "delta-negative-field",
            "seq-not-increasing",
            "side-outside-domain",
        ],
    )
    def test_decode_refuses_messages_that_break_the_documented_values(
        self, tamper: Callable[[dict[str, Any]], object], message: str
    ) -> None:
        """逐則的值不合模組說明(收到時刻不倒退、delta 成對、欄號 0–19、訊息序號遞增、內外盤三值)就拒絕 ——
        不讓它變成 IndexError,或更糟,默默解出另一份簿(pr-275 review F-08)。"""
        wire = _wire(replay_books(_lock_limit_up_rows())["2426"], keyframe_every=3)
        tamper(wire)

        with pytest.raises(PluginFormatError, match=message):
            decode(wire)

    def test_encode_refuses_a_keyframe_interval_below_one(self) -> None:
        day = replay_books(_lock_limit_up_rows())["2426"]

        with pytest.raises(ValueError, match="keyframe_every"):
            encode(day, keyframe_every=0)

    @pytest.mark.parametrize("index", [8, -1], ids=["index-equals-n", "negative-index"])
    def test_book_at_refuses_an_index_outside_the_messages(self, index: int) -> None:
        """8 則的檔:`book_at(8)` 修前回第 7 則、`book_at(-1)` 回最後一個 keyframe —— 回看頁照抄這條規則會帶歪。"""
        wire = _wire(replay_books(_lock_limit_up_rows())["2426"], keyframe_every=3)

        with pytest.raises(IndexError, match="沒有第"):
            book_at(wire, index)

    @pytest.mark.parametrize(
        ("tamper", "message"),
        [
            (lambda w: w.update(anomalous=[3, 0]), "時刻異常成交則號"),
            (lambda w: w.update(anomalous=[-1, 0, 3]), "時刻異常成交則號"),
            (lambda w: w.update(anomalous=[0, 3, 4]), "時刻異常成交則號"),  # n = 4
            (lambda w: w.update(anomalous=[0, 1, 3]), "時刻異常成交則號"),  # 第 1 則是簿則
            # 漏列第 3 則:09:00:02 變時鐘點,標籤時刻從 09:00:03 倒退
            (lambda w: w.update(anomalous=[0]), "早於標籤時刻"),
            # 漏列第 0 則:前一日 14:30 變時鐘點,第 2 則的 09:00:03 倒退
            (lambda w: w.update(anomalous=[3]), "早於標籤時刻"),
            (lambda w: w["trade"].__setitem__(4, None), "沒有達錢時刻"),  # 第 2 則的時刻
        ],
        ids=[
            "not-increasing",
            "negative-index",
            "index-equals-n",
            "on-book-message",
            "missed-rewinding-trade",
            "missed-future-trade",
            "clock-trade-without-time",
        ],
    )
    def test_decode_refuses_an_anomalous_trade_list_that_contradicts_the_trades(
        self, tamper: Callable[[dict[str, Any]], object], message: str
    ) -> None:
        """時鐘點不直接存:沒列在 `anomalous` 的成交就是時鐘點,時刻讀它自己的成交時刻。清單與成交對不上 =
        標籤時刻會倒退或掛在簿則上,拒絕(pr-275 review F-03 / F-07)。"""
        wire = _wire(replay_books(_golden_rows())["1815"], keyframe_every=2)
        tamper(wire)

        with pytest.raises(PluginFormatError, match=message):
            decode(wire)

    def test_round_trip_keeps_changes_and_eaten_levels(self) -> None:
        """變動分解四種項目與吃檔(含五檔外)都解得回來(2489 掃單樣本:掛入 / 成交 / 被擠出 / 重新可見 / 首次進入)。"""
        day = replay_books(_sweep_2489_rows())["2489"]

        wire = _wire(day, keyframe_every=4)

        assert decode(wire) == day

    @pytest.mark.parametrize(
        ("tamper", "message"),
        [
            (lambda w: w["chg"][1].__setitem__(0, 8), "種類碼"),
            (lambda w: w["chg"][1].pop(), "格數不足"),
            # 第 1 則「賣 38.95 由 0 → 4」:前量 / 後量改掉就跟前後兩則的五檔對不上
            (lambda w: w["chg"][1].__setitem__(2, 1), "前量"),
            (lambda w: w["chg"][1].__setitem__(3, 5), "後量"),
            # 第 1 則多一項「買 38.9 由 13 → 13」:兩則五檔都是 13,但沒有變的價位不該列
            (lambda w: w["chg"][1].extend([0, 38_900, 13, 13, 0]), "沒有變"),
            # 第 10 則「賣 38.95 由 7 → 0,成交 7」改成成交 8:比減少的量還多
            (lambda w: w["chg"][10].__setitem__(12, 8), "成交"),
            # 第 1 則「賣 39.2 被擠出五檔 80 張」改 81:與前一則五檔不符
            (lambda w: w["chg"][1].__setitem__(7, 81), "離開前"),
            # 第 10 則「賣 39.2 重新可見」[碼, 價, 離開 80, 現在 0, 期間成交 80, 淨掛 0, 離開則號 1, 11056 ms]:
            # 現在量改 3 連同淨掛改 3(算式自洽)→ 仍與這一則五檔 0 張不符;其餘各改一格
            (lambda w: w["chg"][10].__setitem__(slice(36, 39), [3, 80, 3]), "現在量"),
            (lambda w: w["chg"][10].__setitem__(38, 5), "淨掛"),
            (lambda w: w["chg"][10].__setitem__(39, 10), "離開則號"),
            (lambda w: w["chg"][10].__setitem__(40, 11_000), "離開時長"),
            # 第 10 則「賣 39.35 首次進入五檔 28 張」改 29
            (lambda w: w["chg"][10].__setitem__(43, 29), "首次進入"),
            (lambda w: w["chg"][0].extend([6, 38_900, 13]), "第 0 則"),
            (lambda w: w["eat"].pop(), "eat 長度"),
            (lambda w: w["eat"][0].__setitem__(1, 7), "吃檔"),
            (lambda w: w["eat"][0].append(1), "吃檔"),
            # 第 3 則成交 38.95 × 7,吃檔寫成 8 張
            (lambda w: w["eat"][0].__setitem__(2, 8), "超過成交"),
        ],
        ids=[
            "unknown-change-kind",
            "truncated-change",
            "level-before",
            "level-after",
            "level-unchanged",
            "traded-over-decrease",
            "left-qty",
            "reappeared-now",
            "reappeared-net",
            "reappeared-left-index",
            "reappeared-away-ms",
            "entered-qty",
            "changes-on-first-message",
            "eat-length",
            "eat-level-out-of-range",
            "eat-cells-not-triples",
            "eat-over-trade-qty",
        ],
    )
    def test_decode_refuses_changes_or_eaten_levels_that_contradict_the_books(
        self, tamper: Callable[[dict[str, Any]], object], message: str
    ) -> None:
        """回看頁把變動清單與階梯並排顯示:清單與前後兩則五檔對不上 = 同一刻講兩件事,不得放行。"""
        wire = _wire(replay_books(_sweep_2489_rows())["2489"], keyframe_every=4)
        tamper(wire)

        with pytest.raises(PluginFormatError, match=message):
            decode(wire)

    def test_parse_refuses_text_that_is_not_a_book_replay_plugin_line(self) -> None:
        """逐筆外掛檔(`window.__tk`)跟簿重播外掛檔同形,放錯資料夾也要認得出來。"""
        with pytest.raises(PluginFormatError, match="window.__bk"):
            parse_plugin_js('window.__tk("2426|2026-09-16","H4sIAAAAAAAAA4uOBQApu0wNAgAAAA==");')

    def test_parse_refuses_a_call_key_that_disagrees_with_the_content(self) -> None:
        """回看頁以呼叫鍵「代號|日期」配對懶載入的請求;鍵與內容不符 = 畫面掛到別檔別日的簿。"""
        text = plugin_js(encode(replay_books(_lock_limit_up_rows())["2426"]))

        with pytest.raises(PluginFormatError, match="呼叫鍵"):
            parse_plugin_js(text.replace('"2426|2026-09-16"', '"2427|2026-09-16"', 1))
