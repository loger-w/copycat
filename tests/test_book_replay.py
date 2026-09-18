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
    BookChange,
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
    seconds, milli = divmod(_ms(hms) + ms, 1000)
    minutes, sec = divmod(seconds, 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}:{sec:02d}.{milli:03d}"


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
    status: str | None = "0",
) -> TickRow:
    fields: dict[str, Any] = {
        "kind": kind,
        "code": code,
        "trade_date": trade_date,
        "msg_seq": msg_seq,
        "recv_ns": _ns(recv),
        "precise_time": "10003000000",
        "trade_status": status,
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


def _at(frame_changes: tuple[BookChange, ...], price: int) -> list[BookChange]:
    """一則變動裡某價位的項目(測試只斷言它關心的價位,其餘價位的變動另有測試)。

    型別寫 `BookChange`(公開型別)而不是 `object` + `getattr`:四種變動都有 `price_milli`,
    欄位改名時 pyright 當場紅(#279 審查 F-14)。
    """
    return [c for c in frame_changes if c.price_milli == price]


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

    def test_a_trade_on_the_cleared_message_still_counts_into_an_away_price(self) -> None:
        """清空那一則本身是成交則(合成樣本):不比簿,但成交照樣算進被擠出價位的期間成交。

        買 46.7 被擠出五檔 → 清空那一則成交 46.7 × 3 → 46.7 回到五檔:那 3 張要進「期間成交」,
        淨掛才不會少算(清空分支漏了這一步 = 重新可見寫成「期間成交 0、淨掛 0」,零錯誤訊號;#279 審查 F-10)。
        """
        five = [(46_900, 10), (46_850, 10), (46_800, 10), (46_750, 10)]
        rows = [
            _row("book", "2305", 1, recv="09:04:56.000", bid=[*five, (46_700, 5)]),
            _row("book", "2305", 2, recv="09:04:56.100", bid=[(46_950, 3), *five]),
            _row(
                "trade",
                "2305",
                3,
                recv="09:04:56.200",
                time="09:04:56.000",
                price=46_700,
                qty=3,
                side="inner",
                bid=[],
                ask=[],
            ),
            _row("book", "2305", 4, recv="09:04:56.300", bid=[*five, (46_700, 5)]),
        ]

        frames = replay_books(rows)["2305"].frames

        assert frames[2].book == (None,) * 20
        assert frames[2].changes == ()
        assert frames[2].eaten == (Eaten("bid", level=None, qty=3),)  # 成交當下 46.7 在五檔外
        assert _at(frames[3].changes, 46_700) == [
            Reappeared(
                "bid",
                46_700,
                left_qty=5,
                now_qty=5,
                traded_away=3,
                left_index=1,
                away_ms=200,
            )
        ]

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


def _halt_auction_rows() -> list[TickRow]:
    """暫緩撮合形狀(2305 於 2026-09-16 09:12 實錄縮寫):試撮五檔(達錢 `TradeStatus=1`,每 5 秒一份)
    → 撮合那一筆 772 張(五檔上只看得到 23 張)→ 撮後的下一筆成交與簿則。"""
    trial_bid = [(49_200, 7), (49_150, 3), (49_100, 23)]
    trial_ask = [(49_250, 161), (49_300, 481)]
    after_bid = [(49_050, 40), (49_000, 12)]
    return [
        _row("book", "9101", 1, recv="09:12:16.920", bid=trial_bid, ask=trial_ask, status="1"),
        _row(
            "trade",
            "9101",
            2,
            recv="09:12:21.572",
            time="09:12:21.000",
            price=49_100,
            qty=772,
            side="inner",
            bid=after_bid,
            ask=[(49_100, 72), (49_150, 37), (49_250, 228)],
        ),
        _row(
            "trade",
            "9101",
            3,
            recv="09:12:21.587",
            time="09:12:21.000",
            price=49_100,
            qty=16,
            side="outer",
            bid=after_bid,
            ask=[(49_100, 56), (49_150, 37), (49_250, 228)],
        ),
        _row(
            "book",
            "9101",
            4,
            recv="09:12:21.600",
            bid=after_bid,
            ask=[(49_100, 50), (49_150, 37), (49_250, 228)],
        ),
    ]


class TestAuctionMatch:
    """集合競價撮出來的那一筆(開盤 / 暫緩撮合結束 / 收盤 / 處置股分盤撮合):試撮期間達錢揭示的五檔
    是「撮完剩下的」,撮掉的單子從來沒顯示過 —— 這一筆的減量永遠比不到,不留著扣後面的量,吃檔留空
    (user 2026-09-18 拍板)。撮合那一則也不拆變動(跟試撮五檔比不出意義),撮後的五檔當新基準。"""

    def test_the_auction_message_is_not_broken_down_and_claims_no_later_decrease(self) -> None:
        """撮合那一則:不拆、吃檔空;之後同價位的減量各自歸位,沒成交的算撤單。"""
        frames = replay_books(_halt_auction_rows())["9101"].frames

        assert frames[1].auction is True
        assert frames[1].changes == ()
        assert frames[1].eaten == ()
        assert frames[2].eaten == (Eaten("ask", level=1, qty=16),)
        assert frames[2].changes == (
            LevelChange("ask", 49_100, before=72, after=56, traded=16),
        )
        assert frames[3].changes == (
            LevelChange("ask", 49_100, before=56, after=50, traded=0),
        )
        assert [frame.auction for frame in frames] == [False, True, False, False]

    def test_the_first_message_of_the_day_being_a_trade_claims_no_later_decrease(self) -> None:
        """開盤集合競價那筆常常是當天第一則(五檔已是成交後,沒有前一份可比):5314 於 2026-09-17
        09:00:12 鎖跌停開盤 11,090 張,之後兩則同價位減量其實是撤單(下一筆成交在第 20 則)。"""
        rows = [
            _row(
                "trade",
                "5314",
                1,
                recv="09:00:12.632",
                time="09:00:12.000",
                price=27_750,
                qty=11_090,
                side="outer",
                bid=[],
                ask=[(27_750, 22_536), (27_800, 350)],
            ),
            _row(
                "book", "5314", 2, recv="09:00:12.659", bid=[], ask=[(27_750, 22_426), (27_800, 350)]
            ),
            _row(
                "book", "5314", 3, recv="09:00:12.664", bid=[], ask=[(27_750, 22_406), (27_800, 350)]
            ),
        ]

        frames = replay_books(rows)["5314"].frames

        assert frames[0].eaten == ()
        assert frames[0].auction is False  # 當日第一份五檔(沒有前一份可比),不是集合競價標記
        assert frames[1].changes == (
            LevelChange("ask", 27_750, before=22_536, after=22_426, traded=0),
        )
        assert frames[2].changes == (
            LevelChange("ask", 27_750, before=22_426, after=22_406, traded=0),
        )

    def test_a_future_stamped_trade_brings_a_stale_book_that_is_not_the_first_of_the_day(
        self,
    ) -> None:
        """1815 每天開機(07:31)收到前一日 14:30 的盤後成交,附的是前一天的五檔:不當當日第一份
        (否則 09:00 開盤那則跟它比,拆出幾千張假撤單),它自己的成交也不留著扣。"""
        yesterday = [(114_000, 1_967), (113_500, 500)]
        opening = [(114_000, 172), (113_500, 480)]
        rows = [
            _row(
                "trade",
                "1815",
                1,
                recv="07:31:22.730",
                time="14:30:00.000",
                price=114_500,
                qty=67,
                side="inner",
                bid=yesterday,
                ask=[(115_500, 68)],
            ),
            _row(
                "trade",
                "1815",
                2,
                recv="09:00:03.872",
                time="09:00:03.000",
                price=115_500,
                qty=426,
                side="outer",
                bid=opening,
                ask=[(115_500, 68), (117_500, 27)],
            ),
            _row(
                "book",
                "1815",
                3,
                recv="09:00:03.904",
                bid=opening,
                ask=[(115_500, 60), (117_500, 27)],
            ),
        ]

        frames = replay_books(rows)["1815"].frames

        assert (frames[0].changes, frames[0].eaten) == ((), ())
        assert (frames[1].changes, frames[1].eaten) == ((), ())  # 當日第一份五檔在這一則才成立
        assert frames[2].changes == (
            LevelChange("ask", 115_500, before=68, after=60, traded=0),
        )

    def test_two_trades_waiting_at_one_price_credit_the_older_one_first(self) -> None:
        """同價位兩筆待扣、減量不夠分時扣舊的那筆(#279 審查 F-09:這個順序原本沒有測試;
        user 2026-09-18 拍板維持由舊到新)。"""
        rows = [
            _row("book", "9201", 1, recv="10:00:00.000", bid=[(99_000, 1)], ask=[(100_000, 25)]),
            _row(
                "trade",
                "9201",
                2,
                recv="10:00:00.100",
                time="10:00:00.000",
                price=100_000,
                qty=5,
                side="outer",
                bid=[(99_000, 1)],
                ask=[(100_000, 25)],
            ),
            _row(
                "trade",
                "9201",
                3,
                recv="10:00:00.200",
                time="10:00:00.000",
                price=100_000,
                qty=3,
                side="outer",
                bid=[(99_000, 1)],
                ask=[(100_000, 22)],
            ),
        ]

        frames = replay_books(rows)["9201"].frames

        assert frames[1].eaten == (Eaten("ask", level=1, qty=3),)
        assert frames[2].eaten == ()

    def test_one_trade_eating_the_same_level_in_two_goes_reports_one_item(self) -> None:
        """同一格分幾則扣到合成一項 —— 中間夾著別格也要合(#279 審查 F-04)。"""
        bid = [(90_000, 3)]
        rows = [
            _row("book", "9202", 1, recv="10:00:00.000", bid=bid, ask=[(0, 500), (90_100, 20)]),
            _row(
                "trade",
                "9202",
                2,
                recv="10:00:00.100",
                time="10:00:00.000",
                price=90_100,
                qty=10,
                side="outer",
                bid=bid,
                ask=[(0, 500), (90_100, 20)],
            ),
            _row("book", "9202", 3, recv="10:00:00.200", bid=bid, ask=[(0, 500), (90_100, 16)]),
            _row("book", "9202", 4, recv="10:00:00.300", bid=bid, ask=[(0, 497), (90_100, 16)]),
            _row("book", "9202", 5, recv="10:00:00.400", bid=bid, ask=[(0, 497), (90_100, 13)]),
        ]

        frames = replay_books(rows)["9202"].frames

        assert frames[1].eaten == (Eaten("ask", level=1, qty=7), Eaten("ask", level=0, qty=3))

    def test_the_plugin_file_marks_the_auction_message_and_refuses_a_list_that_disagrees(
        self,
    ) -> None:
        """外掛檔:`auction` 只列集合競價撮合那些成交則(遞增);回看頁靠它印「集合競價撮合」。"""
        day = replay_books(_halt_auction_rows())["9101"]
        wire = _wire(day, keyframe_every=2)

        assert wire["auction"] == [1]
        assert decode(wire) == day

        wire["auction"] = [0]  # 第 0 則是簿則,不可能是集合競價撮合
        with pytest.raises(PluginFormatError, match="集合競價撮合則號 0 不合法"):
            decode(wire)

    def test_the_plugin_file_refuses_eaten_levels_on_messages_that_never_waited(self) -> None:
        """集合競價撮合與附舊簿的成交都不進待扣 → 永遠扣不到任何一格,`eat` 那一列必須是空的。"""
        auction_wire = _wire(replay_books(_halt_auction_rows())["9101"], keyframe_every=2)
        auction_wire["eat"][0] = [1, 1, 5]  # 第 1 則(撮合那筆)寫「吃 賣1 −5」
        with pytest.raises(PluginFormatError, match="集合競價撮合不進待扣,不該有吃檔"):
            decode(auction_wire)

        stale_wire = _wire(replay_books(_golden_rows())["1815"], keyframe_every=2)
        stale_wire["eat"][0] = [1, 1, 1]  # 第 0 則(開機收到的前一日成交)寫「吃 賣1 −1」
        with pytest.raises(PluginFormatError, match="附舊簿的成交不進待扣,不該有吃檔"):
            decode(stale_wire)


def _closing_auction_rows() -> list[TickRow]:
    """收盤集合競價形狀(2026-09-16 實錄縮寫):13:24 盤中 → 13:25 起整段試撮(達錢 `TradeStatus=1`)
    → 13:30 撮出收盤那一筆(狀態已回 0)→ 撮後再一則簿。"""
    live_bid, live_ask = [(50_000, 12), (49_950, 30)], [(50_050, 8), (50_100, 44)]
    trial_ask: list[Level] = [(50_050, 40)]  # 試撮那三則的賣方不動,買方一路堆
    return [
        _row("book", "9102", 1, recv="13:24:58.100", bid=live_bid, ask=live_ask),
        _row(
            "book",
            "9102",
            2,
            recv="13:25:03.400",
            bid=[(50_000, 900)],
            ask=trial_ask,
            status="1",
        ),
        _row(
            "book",
            "9102",
            3,
            recv="13:27:10.200",
            bid=[(50_000, 2_400)],
            ask=trial_ask,
            status="1",
        ),
        _row(
            "book",
            "9102",
            4,
            recv="13:29:58.700",
            bid=[(50_000, 3_300)],
            ask=trial_ask,
            status="1",
        ),
        _row(
            "trade",
            "9102",
            5,
            recv="13:30:12.900",
            time="13:30:00.000",
            price=50_050,
            qty=3_300,
            side="outer",
            bid=[(50_000, 5)],
            ask=[(50_050, 40)],
        ),
        _row("book", "9102", 6, recv="13:30:13.050", bid=[(50_000, 5)], ask=[(50_050, 40)]),
    ]


class TestAuctionSegment:
    """集合競價段(ticket #273):達錢 `TradeStatus` 標「試撮中」的那些則。收盤 13:25–13:30、處置股
    整天的分盤撮合、盤中暫緩撮合都是這一段 —— 那段揭示的五檔是「撮完剩下的」,委託堆積是集合競價的
    結果而不是盤中墊單,所以要在回看頁上分隔標註,#271 的厚檔事件也要整段排除。"""

    def test_the_trial_messages_of_the_closing_auction_are_the_segment(self) -> None:
        """13:25 起的試撮簿列在段內;13:24 的盤中簿與撮出收盤那一筆(狀態已回 0)都不在。"""
        frames = replay_books(_closing_auction_rows())["9102"].frames

        assert [frame.trial for frame in frames] == [False, True, True, True, False, False]
        assert frames[4].auction is True

    def test_a_late_delayed_match_trade_carries_the_trial_flag_itself(self) -> None:
        """暫緩撮合撮出來的成交自己也可能還帶著試撮狀態:旗標讀那一則自己的 `TradeStatus`,不分成交則簿則。

        成交那一列取自 7772 於 2026-09-16 的實錄(11:40:29 成交、11:42:27 才收到,狀態仍是試撮);
        **前面那一則試撮簿是構造的** —— 實錄裡那筆是當天第一則(全天只有 3 則訊息,`kind="ttb"`、
        `trial=[0,0,2,2]`、`auction=[]`),沒有前一則可比。補上前一則才問得出下面這件事。

        排成「試撮簿 → 試撮成交」之後,這一列**同時**滿足兩個判準(`trial` 讀自己的狀態、`auction`
        讀前一則是不是試撮簿)—— 兩個旗標**不互斥**,這是 `book_replay` 模組說明「段的界」那段的反例
        守門(2026-09-18 pr-281 review #1)。暫緩撮合期間每分鐘約 10 則試撮簿,延遲成交夾在中間到達
        就是這個形狀;7772 只是因為全天 3 則訊息才沒撞上。
        """
        rows = [
            _row(
                "book",
                "7772",
                1,
                recv="11:42:20.000",
                bid=[(131_500, 4)],
                ask=[(132_000, 9)],
                status="1",
            ),
            _row(
                "trade",
                "7772",
                2,
                recv="11:42:27.594",
                time="11:40:29.000",
                price=132_000,
                qty=1,
                side="outer",
                bid=[(131_500, 4)],
                ask=[(132_000, 8)],
                status="1",
            ),
        ]

        frames = replay_books(rows)["7772"].frames

        assert [frame.trial for frame in frames] == [True, True]
        assert frames[1].auction is True  # 兩個判準獨立,同一則可以都成立

    def test_an_intraday_halt_auction_is_the_same_segment(self) -> None:
        """盤中暫緩撮合與收盤同一套:試撮那幾則在段內,撮合那一筆不在。"""
        frames = replay_books(_halt_auction_rows())["9101"].frames

        assert [frame.trial for frame in frames] == [True, False, False, False]

    def test_the_plugin_file_carries_the_segment_as_increasing_message_ranges(self) -> None:
        """外掛檔 v4:`trial` = 攤平的 `[起, 迄]` 則號閉區間(遞增、相鄰的併成一段)。"""
        day = replay_books(_closing_auction_rows())["9102"]
        wire = _wire(day, keyframe_every=2)

        assert wire["trial"] == [1, 3]
        assert decode(wire) == day

    @pytest.mark.parametrize(
        ("ranges", "why"),
        [
            ([1], "格數"),
            ([3, 1], "起迄"),
            ([1, 3, 3, 4], "遞增"),
            ([1, 3, 4, 5], "遞增"),  # 相鄰兩段沒併成一段
            ([1, 9], "落在則號"),
            ([-1, 1], "落在則號"),
        ],
    )
    def test_decode_refuses_segment_ranges_the_viewer_cannot_draw(
        self, ranges: list[int], why: str
    ) -> None:
        wire = _wire(replay_books(_closing_auction_rows())["9102"], keyframe_every=2)
        wire["trial"] = ranges
        with pytest.raises(PluginFormatError, match=why):
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

    def test_a_price_first_listed_on_the_trade_message_reads_its_level_from_that_message(
        self,
    ) -> None:
        """吃檔退路(模組說明「吃檔」):成交前那一則沒列出這個價位,就看扣到那一則的前一則。

        成交價 100.5 在成交前那一則(只有賣 100.0)看不到,是成交自己附的五檔才第一次列出來、下一則才減量。
        沒有這條退路,看得到的賣 2 會被標成「五檔外」(#279 審查 F-08:正式檔每天約四十列走這條)。
        """
        rows = [
            _row("book", "2489", 1, recv="10:10:00.000", ask=[(100_000, 5)]),
            _row(
                "trade",
                "2489",
                2,
                recv="10:10:00.100",
                time="10:10:00.000",
                price=100_500,
                qty=3,
                side="outer",
                ask=[(100_000, 5), (100_500, 10)],
            ),
            _row("book", "2489", 3, recv="10:10:00.200", ask=[(100_000, 5), (100_500, 7)]),
        ]

        frames = replay_books(rows)["2489"].frames

        assert frames[1].changes == (LevelChange("ask", 100_500, before=0, after=10, traded=0),)
        assert frames[2].changes == (LevelChange("ask", 100_500, before=10, after=7, traded=3),)
        # 賣 2 = 扣到那一則(第 2 則)的前一則(第 1 則,成交自己附的五檔)裡 100.5 的檔位
        assert [f.eaten for f in frames] == [(), (Eaten("ask", level=2, qty=3),), ()]

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

    def test_a_locked_limit_down_counts_ask_levels_without_the_market_queue(self) -> None:
        """鎖跌停 = 賣方市價佇列(價 0)+ 跌停價,是上一條鎖漲停的鏡像(合成樣本)。

        檔位只數限價,所以吃跌停價那一檔是「賣 1」不是「賣 2」—— 這條規則原本只有買方樣本,而買方
        由高到低排、價 0 恆在最後,把 0 算進去檔位也不會變;要賣方(0 排最前)才分得出來(#279 審查 F-07)。
        同一則的變動,賣方市價佇列那項也排在賣方最前。
        """
        ask = [(0, 500), (90_100, 20)]
        rows = [
            _row("book", "5314", 1, recv="09:30:00.000", ask=ask),
            _row(
                "trade",
                "5314",
                2,
                recv="09:30:00.100",
                time="09:30:00.000",
                price=90_100,
                qty=4,
                side="outer",
                ask=[(0, 500), (90_100, 16)],
            ),
            _row(
                "trade",
                "5314",
                3,
                recv="09:30:00.200",
                time="09:30:00.000",
                price=90_100,
                qty=6,
                side="outer",
                ask=[(0, 494), (90_100, 14)],
            ),
        ]

        frames = replay_books(rows)["5314"].frames

        assert frames[1].changes == (LevelChange("ask", 90_100, before=20, after=16, traded=4),)
        assert frames[2].changes == (
            LevelChange("ask", 0, before=500, after=494, traded=6),  # 市價佇列排在賣方最前
            LevelChange("ask", 90_100, before=16, after=14, traded=0),
        )
        assert [f.eaten for f in frames] == [
            (),
            (Eaten("ask", level=1, qty=4),),  # 跌停價是賣 1:市價佇列不佔號
            (Eaten("ask", level=0, qty=6),),  # 減的是市價那一排,不看成交價
        ]

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

    def test_a_first_message_trade_never_borrows_a_later_book_to_claim_five_levels_away(
        self,
    ) -> None:
        """當日第一份五檔那一則的成交:自己的減量已經在這份簿裡,不進待扣,吃檔恆空。

        前後兩道閘:成交不進待扣(第 0 則還沒有視野可比),以及到期時 `record_unabsorbed` 不碰第 0 則 ——
        後面那道沒了,「成交前那一則」會取到 `_books[-1]`(**最後**一份簿),在這個樣本裡把成交價 105.0
        標成「賣五檔外 −2」。兩道各自拿掉都看不出差別(前一道另有 TestAuctionMatch 兩條釘著),
        兩道都拿掉這一條才紅(#279 審查 F-10)。
        """
        rows = [
            _row(
                "trade",
                "3450",
                1,
                recv="09:30:00.000",
                time="09:30:00.000",
                price=105_000,
                qty=2,
                side="outer",
                ask=[(100_000, 4)],
            ),
            # 1.1 秒後(超過 TRADE_CARRY_MS)那筆成交到期;這一則賣五檔到 101.0,看不到 105.0
            _row(
                "book",
                "3450",
                2,
                recv="09:30:01.100",
                ask=[(100_000, 2), (100_250, 1), (100_500, 1), (100_750, 1), (101_000, 1)],
            ),
        ]

        frames = replay_books(rows)["3450"].frames

        assert frames[1].changes == (
            LevelChange("ask", 100_000, before=4, after=2, traded=0),  # 首則那筆不在待扣 → 撤單
            LevelChange("ask", 100_250, before=0, after=1, traded=0),
            LevelChange("ask", 100_500, before=0, after=1, traded=0),
            LevelChange("ask", 100_750, before=0, after=1, traded=0),
            LevelChange("ask", 101_000, before=0, after=1, traded=0),
        )
        assert [f.eaten for f in frames] == [(), ()]

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

    def test_payload_layout_matches_the_documented_v4_literal(self) -> None:
        """外掛檔永久保留,回看頁 JS 照模組說明「外掛檔 v4」逐鍵讀。編碼與解碼一起漂的時候 round-trip 照綠,
        只有寫死的字面抓得到(pr-275 review F-01)。v1 → v2(#269)加 `chg` 與 `eat`;
        v2 → v3(#279 審查收修)加 `auction` 與 `stale`;v3 → v4(#273)加 `trial`。第 0 則(開機收到的
        前一日成交)附的是前一日的簿 → 列在 `stale`、不當當日第一份五檔,所以第 1 則才是第一份(變動為空)。"""
        day = replay_books(_golden_rows())["1815"]

        payload = encode(day, keyframe_every=2)

        assert payload == {
            "v": 4,
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
            "auction": [],  # 集合競價撮合(前一則是試撮五檔)的成交則號;這四則都不是
            "stale": [0],  # 附舊簿(時刻在未來的異常成交)的成交則號 ⊆ anomalous:不比、也不當基準
            "trial": [],  # 集合競價段(試撮中)的 [起, 迄] 則號閉區間;這四則都在正常盤
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
            # 每則的變動;價位變動 [種類碼(買 0 / 賣 1), 價, 前量, 後量, 掛入, 成交, 撤單];
            # 同側市價佇列在前、再由最優價往外
            "chg": [
                [],  # 開機收到的前一日成交:附的是舊簿,不比
                [],  # 當日第一份五檔(前一則附舊簿,不當基準)
                [0, 0, 0, 1_300, 1_300, 0, 0]
                + [0, 115_500, 0, 800, 800, 0, 0]
                + [0, 115_000, 205, 0, 0, 0, 205]
                + [1, 115_500, 12, 0, 0, 7, 5],  # 同則 115.5 × 7 成交先扣,其餘 5 張撤單
                [0, 0, 1_300, 1_299, 0, 1, 0],  # 市價佇列減少不看成交價:同則 115.5 × 1 先扣
            ],
            # 每筆成交一列 [側別碼, 檔位(限價 1–5、市價佇列 0、五檔外 null), 張, …]
            "eat": [
                [],  # 開機收到的前一日成交:之前沒有簿,看不出吃哪一檔
                [1, 1, 7],  # 吃 賣1 −7
                [0, 0, 1],  # 吃 市價買 −1
            ],
        }

    def test_every_change_kind_and_eaten_level_matches_the_documented_v2_literal(self) -> None:
        """`chg` 八種種類碼、`eat` 各種檔位的字面(review round 1 S-02):encode / decode 一起把兩種碼對調時
        round-trip 照綠,回看頁卻會印反。2489 掃單樣本出賣方 1 / 3 / 5 / 7 與吃檔 1–5、五檔外;另一段合成的
        買方序列出 0 / 2 / 4 / 6 與吃市價排隊(0)。"""
        sweep = encode(replay_books(_sweep_2489_rows())["2489"], keyframe_every=4)

        assert sweep["chg"][1] == [1, 38_950, 0, 4, 4, 0, 0] + [3, 39_200, 80]
        assert sweep["chg"][10] == (
            [0, 39_300, 0, 60, 60, 0, 0]
            + [2, 38_700, 28]
            + [1, 38_950, 7, 0, 0, 7, 0]
            + [1, 39_000, 44, 0, 0, 44, 0]
            + [1, 39_050, 45, 0, 0, 45, 0]
            + [1, 39_100, 53, 0, 0, 53, 0]
            + [1, 39_150, 21, 0, 0, 21, 0]
            + [5, 39_200, 80, 0, 80, 0, 1, 11_056]
            + [7, 39_350, 28]
            + [7, 39_400, 45]
            + [7, 39_450, 22]
            + [7, 39_500, 118]
            + [7, 39_550, 98]
        )
        assert sweep["eat"] == [
            [1, 1, 7],
            [1, 2, 44],
            [1, 3, 45],
            [1, 4, 53],
            [1, 5, 21],
            [1, None, 80],
            [1, None, 34],
            [1, None, 56],
        ]

        five = [(50_500, 5), (50_400, 5), (50_300, 5), (50_200, 5)]
        rows = [
            _row("book", "3450", 1, recv="10:00:00.000", bid=[*five, (50_100, 5)]),
            _row("book", "3450", 2, recv="10:00:01.000", bid=[(50_600, 1), *five]),
            _row(
                "trade",
                "3450",
                3,
                recv="10:00:02.000",
                time="10:00:02.000",
                price=50_600,
                qty=1,
                side="inner",
                bid=[*five, (50_100, 5)],
            ),
            _row("book", "3450", 4, recv="10:00:03.000", bid=[*five, (50_000, 9)]),
            _row("book", "3450", 5, recv="10:00:04.000", bid=[(0, 100), *five]),
            _row(
                "trade",
                "3450",
                6,
                recv="10:00:05.000",
                time="10:00:05.000",
                price=50_500,
                qty=3,
                side="inner",
                bid=[(0, 97), *five],
            ),
        ]
        bids = encode(replay_books(rows)["3450"])

        assert bids["chg"] == [
            [],
            [0, 50_600, 0, 1, 1, 0, 0] + [2, 50_100, 5],
            [0, 50_600, 1, 0, 0, 1, 0] + [4, 50_100, 5, 5, 0, 0, 1, 1_000],
            [0, 50_100, 5, 0, 0, 0, 5] + [6, 50_000, 9],
            [0, 0, 0, 100, 100, 0, 0] + [2, 50_000, 9],
            [0, 0, 100, 97, 0, 3, 0],
        ]
        assert bids["eat"] == [[0, 1, 1], [0, 0, 3]]

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
            # `chg` 也在檔頭那條長度檢查裡:少了它,壞檔會變成 decode 迴圈 `zip(strict=True)` 的
            # 裸 ValueError,而 CLI 只接 PluginFormatError → 吐 traceback(#279 審查 F-11)。
            # 這一案就是釘住它必須是 PluginFormatError:pytest.raises 不收 ValueError 的父類別命中
            (lambda w: w["chg"].pop(), "chg 長度"),
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
            "chg-length",
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
            # 漏列第 0 則:前一日 14:30 變時鐘點 —— v3 起「附舊簿的則號 ⊆ 時刻異常」在檔頭就擋下
            (lambda w: w.update(anomalous=[3]), "不在時刻異常清單裡"),
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
            (lambda w: w["chg"][1].__setitem__(0, 8), "變動種類碼 8 不認得"),
            (lambda w: w["chg"][1].pop(), "變動項目格數不足"),
            # 竄改的格位一律寫「格位:值」。第 1 則「賣 38.95 由 0 → 4,+4 掛單」
            # [0 碼 1, 1 價 38950, 2 前量 0, 3 後量 4, 4 掛入 4, 5 成交 0, 6 撤單 0]:
            # 前量 / 後量連同掛入改成算式自洽的值 → 仍跟前後兩則的五檔對不上;掛入單獨改 → 算式不符
            (
                lambda w: w["chg"][1].__setitem__(slice(2, 5), [1, 4, 3]),
                "前量 1 與前一則五檔 0 不符",
            ),
            (
                lambda w: w["chg"][1].__setitem__(slice(2, 5), [0, 5, 5]),
                "後量 5 與這一則五檔 4 不符",
            ),
            (lambda w: w["chg"][1].__setitem__(4, 3), "掛入 3 / 撤單 0 不合算式"),
            # 第 1 則多一項「買 38.9 由 13 → 13」:兩則五檔都是 13,但沒有變的價位不該列
            (lambda w: w["chg"][1].extend([0, 38_900, 13, 13, 0, 0, 0]), "沒有變不該列"),
            # 第 10 則「賣 38.95 由 7 → 0,−7 成交」
            # [10 碼 1, 11 價 38950, 12 前量 7, 13 後量 0, 14 掛入 0, 15 成交 7, 16 撤單 0]:
            # 成交改 8(撤單照算式仍 0)→ 比減少的量還多;撤單單獨改 → 算式不符
            (lambda w: w["chg"][10].__setitem__(15, 8), "成交 8 張不在 0 到減少的量之間"),
            (lambda w: w["chg"][10].__setitem__(16, 1), "掛入 0 / 撤單 1 不合算式"),
            # 第 1 則「賣 39.2 被擠出五檔」[7 碼 3, 8 價 39200, 9 離開前的量 80]:改 81 與前一則五檔不符。
            # 整項改成「賣 39.16 被擠出五檔 0 張」(39.16 同樣是前一則看得到、這一則看不到,但前一則沒有量)
            # 才單獨試得到「0 張離開不列」那半個條件(#279 審查 F-11)
            (lambda w: w["chg"][1].__setitem__(9, 81), "離開前的量 81 與前一則五檔 80 不符"),
            (
                lambda w: w["chg"][1].__setitem__(slice(7, 10), [3, 39_160, 0]),
                "離開前的量 0 與前一則五檔 0 不符",
            ),
            # 第 10 則「賣 39.2 重新可見」[45 碼 5, 46 價 39200, 47 離開時量 80, 48 現在量 0,
            # 49 期間成交 80, 50 淨掛 0, 51 離開則號 1, 52 離開毫秒 11056]:現在量改 3 連同淨掛改 3
            # (算式自洽)→ 仍與這一則五檔 0 張不符;三個量一起歸 0(算式也自洽)→ 不該列;其餘各改一格
            (
                lambda w: w["chg"][10].__setitem__(slice(48, 51), [3, 80, 3]),
                "現在量 3 與這一則五檔 0 不符",
            ),
            (
                lambda w: w["chg"][10].__setitem__(slice(47, 51), [0, 0, 0, 0]),
                "重新可見三個量都是 0",
            ),
            (lambda w: w["chg"][10].__setitem__(50, 5), "淨掛 5 不等於"),
            (lambda w: w["chg"][10].__setitem__(51, 10), "離開則號 10 不在這一則之前"),
            (lambda w: w["chg"][10].__setitem__(52, 11_000), "離開時長 11000 ms"),
            # 第 10 則「賣 39.35 首次進入五檔」[53 碼 7, 54 價 39350, 55 量 28]:改 29 與這一則五檔不符。
            # 同上,整項改成「賣 39.36 首次進入五檔 0 張」才單獨試得到「0 張進入不列」(#279 審查 F-11)
            (
                lambda w: w["chg"][10].__setitem__(55, 29),
                "首次進入五檔的量 29 與這一則五檔 28 不符",
            ),
            (
                lambda w: w["chg"][10].__setitem__(slice(53, 56), [7, 39_360, 0]),
                "首次進入五檔的量 0 與這一則五檔 0 不符",
            ),
            (lambda w: w["chg"][0].extend([6, 38_900, 13]), "不該有變動"),
            (lambda w: w["eat"].pop(), "eat 長度"),
            # 第 3 則「吃 賣1 −7」[0 側別碼 1, 1 檔位 1, 2 張 7]:檔位、側別碼、張數三格各自出界,
            # 同一道檢查擋下(側別碼與張數兩案 = #279 審查 F-11)
            (lambda w: w["eat"][0].__setitem__(1, 7), "側別碼 0 / 1、檔位 0–5 或 null、張數 > 0"),
            (lambda w: w["eat"][0].__setitem__(0, 2), "側別碼 0 / 1、檔位 0–5 或 null、張數 > 0"),
            (lambda w: w["eat"][0].__setitem__(2, 0), "側別碼 0 / 1、檔位 0–5 或 null、張數 > 0"),
            (lambda w: w["eat"][0].append(1), "吃檔格數 4 不是 3 的倍數"),
            # 第 3 則成交 38.95 × 7,吃檔寫成 8 張
            (lambda w: w["eat"][0].__setitem__(2, 8), "吃檔共 8 張,超過成交 7 張"),
        ],
        ids=[
            "unknown-change-kind",
            "truncated-change",
            "level-before",
            "level-after",
            "level-added-arithmetic",
            "level-unchanged",
            "traded-over-decrease",
            "level-cancelled-arithmetic",
            "left-qty",
            "left-qty-zero",
            "reappeared-now",
            "reappeared-all-zero",
            "reappeared-net",
            "reappeared-left-index",
            "reappeared-away-ms",
            "entered-qty",
            "entered-qty-zero",
            "changes-on-first-message",
            "eat-length",
            "eat-level-out-of-range",
            "eat-side-code-out-of-range",
            "eat-qty-not-positive",
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

    @pytest.mark.parametrize(
        ("tamper", "message"),
        [
            # 第 1 則「賣 39.20 被擠出五檔 80 張」改寫成「賣 39.20 撤單 80 張」:量都對得上五檔,
            # 只有「這一則已經看不到 39.20」看得出來
            (
                lambda w: w["chg"].__setitem__(
                    1, [1, 38_950, 0, 4, 4, 0, 0] + [1, 39_200, 80, 0, 0, 0, 80]
                ),
                "價位變動要兩則都看得到",
            ),
            # 刪掉「賣 38.95 0 → 4」:兩則都看得到、量變了卻沒列
            (lambda w: w["chg"].__setitem__(1, [3, 39_200, 80]), "卻沒列出價位變動"),
            # 兩項對調:回看頁照收,整組順序與階梯對不起來
            (
                lambda w: w["chg"].__setitem__(
                    1, [3, 39_200, 80] + [1, 38_950, 0, 4, 4, 0, 0]
                ),
                "變動排序不合",
            ),
            # 同一個價位列兩項(把被擠出改成同價位的重新可見)
            (
                lambda w: w["chg"].__setitem__(
                    1, [1, 38_950, 0, 4, 4, 0, 0] + [1, 38_950, 0, 4, 4, 0, 0]
                ),
                "同一個價位列了兩項",
            ),
        ],
        ids=["kind-vs-view", "missing-level-change", "out-of-order", "duplicate-price"],
    )
    def test_decode_refuses_changes_whose_kind_completeness_or_order_disagrees(
        self, tamper: Callable[[dict[str, Any]], object], message: str
    ) -> None:
        """逐項的量對得上五檔還不夠:種類要與看得到的範圍相符、該列的不能漏、順序要跟階梯一致 ——
        修前這四種竄改 decode 都照收(#279 審查 F-03)。"""
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
