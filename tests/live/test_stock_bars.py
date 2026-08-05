from __future__ import annotations

import json
from typing import Any

from copycat.live.futures_source import FUTURES_ALLDAY_DOMAIN
from copycat.live.stock_source import StockQuoteSource, aggregate_1k_to_daily, parse_1k_bars
from tests.helpers.tc4_fakes import FakeApi, ok


def _src(handler: Any) -> StockQuoteSource:
    return StockQuoteSource(
        api=FakeApi(handler), session="s1", trade_date="2026-07-28", poll_wait_secs=0.0
    )


def _pager(pages_by_type: dict[str, dict[str, list[dict]]], sent: list[dict] | None = None):
    """SubDataType → {QryIndex: rows} 的 GETHISDATA 分頁替身。"""

    def handler(obj: dict) -> bytes:
        if sent is not None:
            sent.append(obj)
        if obj["Request"] == "GETHISDATA":
            dtype = obj["Param"]["SubDataType"]
            qi = obj["Param"]["QryIndex"]
            rows = pages_by_type.get(dtype, {}).get(qi, [])
            return (f"{dtype}:" + json.dumps({"Success": "OK", "HisData": rows}) + "\0").encode()
        return ok()

    return handler


def dk(date: str, o: str, h: str, low: str, c: str, v: str = "100", qi: str = "1") -> dict:
    return {"Date": date, "Open": o, "High": h, "Low": low, "Close": c, "Volume": v, "QryIndex": qi}


def k1(date: str, time: str, o: str, h: str, low: str, c: str, v: str = "5", qi: str = "1") -> dict:
    return {
        "Date": date,
        "Time": time,
        "Open": o,
        "High": h,
        "Low": low,
        "Close": c,
        "Volume": v,
        "QryIndex": qi,
    }


class TestFetchBarsRangeDaily:
    def test_dk_parsed_to_ohlcv(self) -> None:
        pages = {"DK": {"0": [dk("20260724", "100", "101.5", "99", "100.5", "1200")], "1": []}}
        src = _src(_pager(pages))
        assert src.fetch_bars_range("2330", "D", "2026-07-01", "2026-07-28") == (
            [{"t": "2026-07-24", "o": 100_000, "h": 101_500, "l": 99_000, "c": 100_500, "v": 1200}],
            "ok",
        )

    def test_missing_open_falls_back_to_close_and_missing_volume_is_zero(self) -> None:
        # DK 的 Open / Volume 欄位名未實測(CLAUDE.md §8 只實證 High/Low/Close)
        row = {"Date": "20260724", "High": "101", "Low": "99", "Close": "100", "QryIndex": "1"}
        src = _src(_pager({"DK": {"0": [row], "1": []}}))
        bars, status = src.fetch_bars_range("2330", "D", "2026-07-01", "2026-07-28")
        assert bars == [
            {"t": "2026-07-24", "o": 100_000, "h": 101_000, "l": 99_000, "c": 100_000, "v": 0}
        ]
        assert status == "ok"

    def test_dk_empty_falls_back_to_1k_aggregation(self) -> None:
        pages = {
            "DK": {"0": []},
            "1K": {
                "0": [
                    k1("20260724", "10000", "100", "101", "100", "100.5", "10", "1"),
                    k1("20260724", "10100", "100.5", "102", "99", "101", "5", "2"),
                ],
                "2": [],
            },
        }
        src = _src(_pager(pages))
        # status 不在這條的意圖內:DK 首頁空 = 等滿(poll_wait=0)預算 → 必然 timeout,
        # 那條語意由 TestBarsStatus 專門鎖。這裡只驗 fallback 真的聚出了 bar。
        bars, _ = src.fetch_bars_range("2330", "D", "2026-07-01", "2026-07-28")
        assert bars == [
            {"t": "2026-07-24", "o": 100_000, "h": 102_000, "l": 99_000, "c": 101_000, "v": 15}
        ]

    def test_sorted_ascending(self) -> None:
        pages = {
            "DK": {
                "0": [
                    dk("20260727", "1", "1", "1", "1", "1", "1"),
                    dk("20260724", "2", "2", "2", "2", "2", "2"),
                ],
                "2": [],
            }
        }
        src = _src(_pager(pages))
        bars, _ = src.fetch_bars_range("2330", "D", "2026-07-01", "2026-07-28")
        assert [b["t"] for b in bars] == ["2026-07-24", "2026-07-27"]


class TestFetchBarsRangeMinute:
    def test_utc_to_taipei_end_stamp(self) -> None:
        # 1K Time 為 UTC 終點標記;01:01 UTC = 09:01 台北(當日第一根)
        pages = {"1K": {"0": [k1("20260728", "10100", "100", "101", "99", "100.5", "7")], "1": []}}
        src = _src(_pager(pages))
        assert src.fetch_bars_range("2330", "1", "2026-07-28", "2026-07-28") == (
            [
                {
                    "t": "2026-07-28 09:01",
                    "o": 100_000,
                    "h": 101_000,
                    "l": 99_000,
                    "c": 100_500,
                    "v": 7,
                }
            ],
            "ok",
        )

    def test_close_correction_clamped_and_merged(self) -> None:
        # fetch_day_minutes 回 dict 靠 key 覆寫;Bar 是 list → 必須顯式合併(review R2-6)
        rows = [
            k1("20260728", "53000", "100", "100", "100", "100", "1", "1"),  # 13:30
            k1("20260728", "53100", "101", "103", "99", "102", "2", "2"),  # 13:31 → clamp 13:30
            k1("20260728", "53500", "102", "104", "98", "103", "3", "3"),  # 13:35 → clamp 13:30
        ]
        src = _src(_pager({"1K": {"0": rows, "3": []}}))
        bars, _ = src.fetch_bars_range("2330", "1", "2026-07-28", "2026-07-28")
        assert bars == [
            {"t": "2026-07-28 13:30", "o": 100_000, "h": 104_000, "l": 98_000, "c": 103_000, "v": 6}
        ]

    def test_out_of_domain_dropped(self) -> None:
        rows = [
            k1("20260728", "5000", "1", "1", "1", "1", "1", "1"),  # 00:50 UTC → 08:50 台北,域外
            k1("20260728", "10100", "100", "101", "99", "100.5", "7", "2"),
            k1("20260728", "54000", "1", "1", "1", "1", "1", "3"),  # 13:40 台北,域外
        ]
        src = _src(_pager({"1K": {"0": rows, "3": []}}))
        bars, _ = src.fetch_bars_range("2330", "1", "2026-07-28", "2026-07-28")
        assert [b["t"] for b in bars] == ["2026-07-28 09:01"]

    def test_cross_day_separate_bars(self) -> None:
        rows = [
            k1("20260727", "10100", "1", "1", "1", "1", "1", "1"),
            k1("20260728", "10100", "2", "2", "2", "2", "2", "2"),
        ]
        src = _src(_pager({"1K": {"0": rows, "2": []}}))
        bars, _ = src.fetch_bars_range("2330", "1", "2026-07-27", "2026-07-28")
        assert [b["t"] for b in bars] == ["2026-07-27 09:01", "2026-07-28 09:01"]

    def test_empty_returns_empty(self) -> None:
        """poll_wait=0 探測一次即回 = 等滿(零)預算 → timeout,不是「確認無資料」。"""
        src = _src(_pager({"1K": {"0": []}}))
        assert src.fetch_bars_range("2330", "1", "2026-07-28", "2026-07-28") == ([], "timeout")


class TestFetchBarsRangeErrors:
    def test_tc4_failure_normalized_to_connection_error(self) -> None:
        import zmq

        def handler(obj: dict) -> bytes:
            raise zmq.ZMQError()

        src = _src(handler)
        try:
            src.fetch_bars_range("2330", "D", "2026-07-01", "2026-07-28")
        except ConnectionError:
            pass
        else:
            raise AssertionError("TC4 通訊失敗必須正規化為 ConnectionError")

    def test_legacy_fetch_daily_bars_untouched(self) -> None:
        # W-D2:overlay 是實盤路徑,新 K 線走新函式,舊路徑零風險
        pages = {"DK": {"0": [dk("20260724", "100", "101.5", "99", "100.5")], "1": []}}
        src = _src(_pager(pages))
        assert src.fetch_daily_bars("2330") == [
            {"date": "2026-07-24", "high": 101_500, "low": 99_000, "close": 100_500}
        ]


class TestBarsStatus:
    """N-1:三態 status 的源頭 —— deadline 用滿 vs 首頁備妥但無 bar。

    TC4 協定上「真無資料」沒有正面訊號(GETHISDATA 空頁不分未備妥/無資料),
    唯一能誠實說出口的區分是「有沒有等滿預算」,所以逾時路徑必須帶得出來。
    """

    def test_minute_with_data_is_ok(self) -> None:
        pages = {"1K": {"0": [k1("20260728", "10100", "100", "101", "99", "100.5", "7")], "1": []}}
        bars, status = _src(_pager(pages)).fetch_bars_range("2330", "1", "2026-07-28", "2026-07-28")
        assert bars
        assert status == "ok"

    def test_minute_timeout_reports_timeout(self) -> None:
        src = _src(_pager({"1K": {}}))
        assert src.fetch_bars_range("2330", "1", "2026-07-28", "2026-07-28") == ([], "timeout")

    def test_daily_with_dk_data_is_ok(self) -> None:
        pages = {"DK": {"0": [dk("20260724", "100", "101.5", "99", "100.5")], "1": []}}
        bars, status = _src(_pager(pages)).fetch_bars_range("2330", "D", "2026-07-01", "2026-07-28")
        assert bars
        assert status == "ok"

    def test_dk_timeout_with_fallback_data_still_reports_timeout(self) -> None:
        """SC-6 worst:1K fallback 補到了 bar,但 DK 那一趟等滿了預算 —— 兩段取最壞。

        bars 非空照樣回 bars(前端只在空時分態),status 誠實說有一段沒等到。
        """
        pages = {
            "DK": {},  # 首頁永遠空 → 等滿預算
            "1K": {
                "0": [k1("20260724", "10000", "100", "101", "100", "100.5", "10", "1")],
                "1": [],
            },
        }
        bars, status = _src(_pager(pages)).fetch_bars_range("2330", "D", "2026-07-01", "2026-07-28")
        assert bars == [
            {"t": "2026-07-24", "o": 100_000, "h": 101_000, "l": 100_000, "c": 100_500, "v": 10}
        ]
        assert status == "timeout"

    def test_tagged_returns_three_tuple(self) -> None:
        """tagged 版是 index_engine 走的那條:tag 與 status 兩件事都要在。"""
        pages = {"DK": {"0": [dk("20260724", "100", "101.5", "99", "100.5")], "1": []}}
        assert _src(_pager(pages)).fetch_bars_range_tagged("2330", "D", "2026-07-01", "2026-07-28")[
            1:
        ] == ("tc4_dk", "ok")


#: **真常數本尊**,不是同值副本(review TC-1):自己抄一份的話,`futures_source` 那邊
#: 把段界改壞(例如夜盤收盤 0500 寫成 0400)這裡照樣全綠 —— 這批段域測試就完全失去
#: 鎖定力,而失效樣態是「圖照畫、只是少了一段時間」,沒有任何錯誤訊號。
_ALLDAY = FUTURES_ALLDAY_DOMAIN
_DAY_ONLY = ("0846", "1345", "1350")


def _k1v(date: str, time: str, c: str, v: str = "1", qi: str = "1", **extra: str) -> dict:
    """1K row 治具(o/h/l 全等於 c;`extra` 供 UpVolume / DownVolume 等選配欄)。"""
    row = k1(date, time, c, c, c, c, v, qi)
    row.update(extra)
    return row


class TestParse1kMultiSegmentDomain:
    """SC-3:夜盤多段域 —— 段序列 + 完整 UTC→台北 datetime 轉換。

    夜盤跨午夜,`_taipei_minute_key` 的「只加小時 % 24」捷徑會把台北次日的列留在
    前一天(UTC 16:00 之後全體受害),所以序列路徑改走完整 datetime 轉換。
    **不加 1 分鐘**:1K 的 `Time` 本身已是 bar 終點標記。
    """

    def _stamps(self, *rows: dict) -> list[str]:
        return [b["t"] for b in parse_1k_bars(list(rows), _ALLDAY)]

    def test_day_open_first_bar_kept(self) -> None:
        # UTC 00:46 = 台北 08:46 = 日盤首根終點標記(08:45 開盤)
        assert self._stamps(_k1v("20260730", "004600", "23000")) == ["2026-07-30 08:46"]

    def test_before_day_open_dropped(self) -> None:
        """UTC 00:45(台北 08:45)落在日盤段起點之前 → 丟(與既有單段域同語意,R9)。"""
        assert self._stamps(_k1v("20260730", "004500", "23000")) == []

    def test_night_session_first_bar_is_1501(self) -> None:
        # 夜盤 15:00 開盤 → 首根終點標記 15:01(UTC 07:01)
        assert self._stamps(_k1v("20260730", "070100", "23100")) == ["2026-07-30 15:01"]

    def test_utc_1559_stays_on_same_taipei_day(self) -> None:
        """23:59 不進位、不加 1 —— 加 1 會變 24:00 這種不存在的時刻。"""
        assert self._stamps(_k1v("20260730", "155900", "23100")) == ["2026-07-30 23:59"]

    def test_utc_1600_rolls_into_next_taipei_day(self) -> None:
        """台北日期由 datetime 轉換得出:UTC 16:00 = 台北**次日** 00:00。"""
        assert self._stamps(_k1v("20260730", "160000", "23100")) == ["2026-07-31 00:00"]

    def test_night_close_and_clamp_and_out_of_domain(self) -> None:
        assert self._stamps(_k1v("20260730", "205900", "1")) == ["2026-07-31 04:59"]
        # 05:01–05:05 clamp 進 05:00(收盤補正);05:10 已在 clamp 窗外 → 丟
        assert self._stamps(_k1v("20260730", "210300", "1")) == ["2026-07-31 05:00"]
        assert self._stamps(_k1v("20260730", "211000", "1")) == []

    def test_clamped_rows_merge_into_one_bar(self) -> None:
        bars = parse_1k_bars(
            [
                _k1v("20260730", "210000", "100", v="2", qi="1"),  # 台北次日 05:00
                _k1v("20260730", "210300", "103", v="3", qi="2"),  # clamp → 05:00
            ],
            _ALLDAY,
        )
        assert bars == [
            {
                "t": "2026-07-31 05:00",
                "o": 100_000,
                "h": 103_000,
                "l": 100_000,
                "c": 103_000,
                "v": 5,
            }
        ]

    def test_segments_ordered_chronologically(self) -> None:
        rows = [
            _k1v("20260730", "004600", "1", qi="1"),  # 08:46
            _k1v("20260730", "070100", "2", qi="2"),  # 15:01
            _k1v("20260730", "160000", "3", qi="3"),  # 次日 00:00
        ]
        assert self._stamps(*rows) == [
            "2026-07-30 08:46",
            "2026-07-30 15:01",
            "2026-07-31 00:00",
        ]

    def test_single_tuple_domain_keeps_legacy_path(self) -> None:
        """三元素 str tuple 也是 Sequence —— 判別法必須是 `isinstance(domain[0], str)`。

        單段路徑行為零變化:夜盤列照舊落在域外被丟。
        """
        rows = [_k1v("20260730", "004600", "1", qi="1"), _k1v("20260730", "070100", "2", qi="2")]
        assert [b["t"] for b in parse_1k_bars(rows, _DAY_ONLY)] == ["2026-07-30 08:46"]


class TestDeltaVolumeFields:
    """SC-8 後端半:1K row 的 UpVolume / DownVolume(內外盤量)貫通到 Bar。

    `uv` / `dv` 是 `NotRequired` —— **來源沒有那兩欄就不得長出欄位**,否則個股既有
    路徑與 DK 路徑的 bar 形狀一起改變(既有測試以完整 dict 相等把這件事釘住)。
    """

    def test_absent_fields_leave_bar_shape_unchanged(self) -> None:
        bars = parse_1k_bars([_k1v("20260728", "10100", "100", v="7")])
        assert bars == [
            {
                "t": "2026-07-28 09:01",
                "o": 100_000,
                "h": 100_000,
                "l": 100_000,
                "c": 100_000,
                "v": 7,
            }
        ]

    def test_delta_volume_accumulated_within_same_minute(self) -> None:
        rows = [
            _k1v("20260728", "53000", "100", v="4", qi="1", UpVolume="3", DownVolume="1"),
            _k1v("20260728", "53100", "101", v="6", qi="2", UpVolume="2", DownVolume="4"),
        ]
        bars = parse_1k_bars(rows)  # 13:31 clamp 進 13:30 → 同一根
        assert len(bars) == 1
        assert (bars[0].get("uv"), bars[0].get("dv"), bars[0]["v"]) == (5, 5, 10)

    def test_missing_one_side_counts_as_zero(self) -> None:
        bars = parse_1k_bars([_k1v("20260728", "10100", "100", UpVolume="9")])
        assert (bars[0].get("uv"), bars[0].get("dv")) == (9, 0)

    def test_multi_segment_path_also_carries_delta_volume(self) -> None:
        bars = parse_1k_bars(
            [_k1v("20260730", "070100", "100", v="5", UpVolume="4", DownVolume="1")], _ALLDAY
        )
        assert (bars[0]["t"], bars[0].get("uv"), bars[0].get("dv")) == ("2026-07-30 15:01", 4, 1)

    def test_daily_aggregation_sums_delta_volume(self) -> None:
        rows = [
            _k1v("20260728", "10100", "100", v="4", qi="1", UpVolume="3", DownVolume="1"),
            _k1v("20260728", "10200", "102", v="6", qi="2", UpVolume="2", DownVolume="4"),
        ]
        bars = aggregate_1k_to_daily(rows)
        assert len(bars) == 1
        assert (bars[0].get("uv"), bars[0].get("dv"), bars[0]["v"]) == (5, 5, 10)

    def test_daily_aggregation_without_fields_unchanged(self) -> None:
        bars = aggregate_1k_to_daily([_k1v("20260728", "10100", "100", v="4")])
        assert bars == [
            {"t": "2026-07-28", "o": 100_000, "h": 100_000, "l": 100_000, "c": 100_000, "v": 4}
        ]


class TestCollectHistoryWaiting:
    """round3 T-9(項 9):首頁 poll 的等待策略。

    實測(2026-07-29):TC4 查無該檔資料時 `?tf=1&days=30` 要 60.1s —— `_collect_history`
    的 deadline 寫死 `poll_wait*30` = 30s,而 `build_minute` 歷史段 + 當日段各發一次。
    有資料的冷載入也固定 2.13s,因為首輪 poll 必定落空後就睡滿 1.0s。
    """

    @staticmethod
    def _run_with_fake_clock(src: StockQuoteSource, *args: Any) -> tuple[Any, list[float]]:
        """sleep 不真睡,改推進假的 monotonic —— 否則測試會照 budget 真等 10 秒。"""
        import copycat.live.stock_source as mod

        slept: list[float] = []
        now = {"t": 0.0}
        real_sleep, real_mono = mod.time.sleep, mod.time.monotonic

        def fake_sleep(secs: float) -> None:
            slept.append(secs)
            now["t"] += secs

        mod.time.sleep = fake_sleep  # type: ignore[assignment]
        mod.time.monotonic = lambda: now["t"]  # type: ignore[assignment]
        try:
            return src.fetch_bars_range(*args), slept
        finally:
            mod.time.sleep = real_sleep  # type: ignore[assignment]
            mod.time.monotonic = real_mono  # type: ignore[assignment]

    def test_poll_wait_zero_probes_once(self) -> None:
        """poll_wait=0(測試組態)不重試 —— 否則就是在 budget 內全速空轉打 fake API。"""
        sent: list[dict] = []
        src = _src(_pager({"1K": {}}, sent))
        assert src.fetch_bars_range("2330", "1", "2026-07-24", "2026-07-24") == ([], "timeout")
        probes = [o for o in sent if o["Request"] == "GETHISDATA"]
        assert len(probes) == 1

    def test_bars_deadline_shorter_than_default(self) -> None:
        """bars 路徑用獨立的短 budget;其他 caller(overlay 日 K)維持 30s 舊值。

        常數隨 `_collect_history` 一起上提到基底 `tc4`(index-board R-3),斷言意圖不變。"""
        from copycat.live.tc4 import BARS_POLL_DEADLINE

        assert BARS_POLL_DEADLINE <= 10.0

    def test_backoff_starts_well_below_poll_wait(self) -> None:
        """首輪落空後不再睡滿 poll_wait,改退避輪詢(2.13s → 目標 ≤1.6s)。"""
        src = StockQuoteSource(
            api=FakeApi(_pager({"1K": {}})),
            session="s1",
            trade_date="2026-07-28",
            poll_wait_secs=1.0,
        )
        _, slept = self._run_with_fake_clock(src, "2330", "1", "2026-07-24", "2026-07-24")
        assert slept, "應該有等待"
        assert slept[0] <= 0.15
        assert max(slept) <= 1.0  # 退避上限 = 原 poll_wait
        assert sum(slept) <= 10.0  # 不超過 bars 專屬 budget

    def test_fallback_1k_also_uses_short_deadline(self) -> None:
        """tf=D 的 DK→1K fallback 也要傳短 budget,否則無資料標的仍是 10+30=40s。"""
        src = StockQuoteSource(
            api=FakeApi(_pager({"DK": {}, "1K": {}})),
            session="s1",
            trade_date="2026-07-28",
            poll_wait_secs=1.0,
        )
        out, slept = self._run_with_fake_clock(src, "2330", "D", "2026-07-24", "2026-07-24")
        assert out == ([], "timeout")
        # DK 一輪 + 1K fallback 一輪,兩輪都受 10s 約束
        assert sum(slept) <= 20.0
