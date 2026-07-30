from __future__ import annotations

import json
import threading
from typing import Any

from copycat.live.stock_source import StockQuoteSource


class _JsonSocket:
    def __init__(self, handler: Any) -> None:
        self._handler = handler
        self._resp = b""

    def send_string(self, payload: str) -> None:
        self._resp = self._handler(json.loads(payload))

    def recv(self) -> bytes:
        return self._resp


class _FakeApi:
    def __init__(self, handler: Any) -> None:
        self.socket = _JsonSocket(handler)
        self.lock = threading.Lock()

    def Disconnect(self) -> None:  # noqa: N802 - wrapper 介面
        pass


def _ok(payload: dict | None = None) -> bytes:
    return (json.dumps({"Success": "OK", **(payload or {})}) + "\0").encode()


def _src(handler: Any) -> StockQuoteSource:
    return StockQuoteSource(
        api=_FakeApi(handler), session="s1", trade_date="2026-07-28", poll_wait_secs=0.0
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
        return _ok()

    return handler


def dk(date: str, o: str, h: str, low: str, c: str, v: str = "100", qi: str = "1") -> dict:
    return {"Date": date, "Open": o, "High": h, "Low": low, "Close": c, "Volume": v, "QryIndex": qi}


def k1(date: str, time: str, o: str, h: str, low: str, c: str, v: str = "5", qi: str = "1") -> dict:
    return {
        "Date": date, "Time": time, "Open": o, "High": h, "Low": low,
        "Close": c, "Volume": v, "QryIndex": qi,
    }


class TestFetchBarsRangeDaily:
    def test_dk_parsed_to_ohlcv(self) -> None:
        pages = {"DK": {"0": [dk("20260724", "100", "101.5", "99", "100.5", "1200")], "1": []}}
        src = _src(_pager(pages))
        assert src.fetch_bars_range("2330", "D", "2026-07-01", "2026-07-28") == [
            {"t": "2026-07-24", "o": 100_000, "h": 101_500, "l": 99_000, "c": 100_500, "v": 1200}
        ]

    def test_missing_open_falls_back_to_close_and_missing_volume_is_zero(self) -> None:
        # DK 的 Open / Volume 欄位名未實測(CLAUDE.md §8 只實證 High/Low/Close)
        row = {"Date": "20260724", "High": "101", "Low": "99", "Close": "100", "QryIndex": "1"}
        src = _src(_pager({"DK": {"0": [row], "1": []}}))
        bars = src.fetch_bars_range("2330", "D", "2026-07-01", "2026-07-28")
        assert bars == [{"t": "2026-07-24", "o": 100_000, "h": 101_000, "l": 99_000, "c": 100_000, "v": 0}]

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
        assert src.fetch_bars_range("2330", "D", "2026-07-01", "2026-07-28") == [
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
        bars = src.fetch_bars_range("2330", "D", "2026-07-01", "2026-07-28")
        assert [b["t"] for b in bars] == ["2026-07-24", "2026-07-27"]


class TestFetchBarsRangeMinute:
    def test_utc_to_taipei_end_stamp(self) -> None:
        # 1K Time 為 UTC 終點標記;01:01 UTC = 09:01 台北(當日第一根)
        pages = {"1K": {"0": [k1("20260728", "10100", "100", "101", "99", "100.5", "7")], "1": []}}
        src = _src(_pager(pages))
        assert src.fetch_bars_range("2330", "1", "2026-07-28", "2026-07-28") == [
            {"t": "2026-07-28 09:01", "o": 100_000, "h": 101_000, "l": 99_000, "c": 100_500, "v": 7}
        ]

    def test_close_correction_clamped_and_merged(self) -> None:
        # fetch_day_minutes 回 dict 靠 key 覆寫;Bar 是 list → 必須顯式合併(review R2-6)
        rows = [
            k1("20260728", "53000", "100", "100", "100", "100", "1", "1"),  # 13:30
            k1("20260728", "53100", "101", "103", "99", "102", "2", "2"),  # 13:31 → clamp 13:30
            k1("20260728", "53500", "102", "104", "98", "103", "3", "3"),  # 13:35 → clamp 13:30
        ]
        src = _src(_pager({"1K": {"0": rows, "3": []}}))
        bars = src.fetch_bars_range("2330", "1", "2026-07-28", "2026-07-28")
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
        bars = src.fetch_bars_range("2330", "1", "2026-07-28", "2026-07-28")
        assert [b["t"] for b in bars] == ["2026-07-28 09:01"]

    def test_cross_day_separate_bars(self) -> None:
        rows = [
            k1("20260727", "10100", "1", "1", "1", "1", "1", "1"),
            k1("20260728", "10100", "2", "2", "2", "2", "2", "2"),
        ]
        src = _src(_pager({"1K": {"0": rows, "2": []}}))
        bars = src.fetch_bars_range("2330", "1", "2026-07-27", "2026-07-28")
        assert [b["t"] for b in bars] == ["2026-07-27 09:01", "2026-07-28 09:01"]

    def test_empty_returns_empty(self) -> None:
        src = _src(_pager({"1K": {"0": []}}))
        assert src.fetch_bars_range("2330", "1", "2026-07-28", "2026-07-28") == []


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
        assert src.fetch_bars_range("2330", "1", "2026-07-24", "2026-07-24") == []
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
            api=_FakeApi(_pager({"1K": {}})),
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
            api=_FakeApi(_pager({"DK": {}, "1K": {}})),
            session="s1",
            trade_date="2026-07-28",
            poll_wait_secs=1.0,
        )
        out, slept = self._run_with_fake_clock(src, "2330", "D", "2026-07-24", "2026-07-24")
        assert out == []
        # DK 一輪 + 1K fallback 一輪,兩輪都受 10s 約束
        assert sum(slept) <= 20.0
