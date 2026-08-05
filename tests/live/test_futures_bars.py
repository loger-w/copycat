"""期指 K 線歷史(index-board N-2)。

**為什麼一定要從 futures session 發**:`TC.F.TWF.<prod>.HOT` 的 REALTIME 訂閱在這條
session 手上,TC4 同 symbol 跨 session 只推一邊(CLAUDE.md §8)—— 從別的 session 問
同一檔有把推播搶走的風險。`river_backfill` 檔頭記的是同一件事。
"""

from __future__ import annotations

import json

from copycat.live.futures_source import FuturesQuoteSource
from tests.helpers.tc4_fakes import FakeApi


def _dk_row(date: str, o: str, h: str, low: str, c: str, v: str = "100", qi: str = "1") -> dict:
    return {"Date": date, "Open": o, "High": h, "Low": low, "Close": c, "Volume": v, "QryIndex": qi}


def _k1_row(
    date: str, time: str, o: str, h: str, low: str, c: str, v: str = "5", qi: str = "1"
) -> dict:
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


def _source(rows: list[dict], sent: list[dict] | None = None) -> FuturesQuoteSource:
    """GETHISDATA 分頁替身:QryIndex="0" 回整批,之後空(iter_qry_pages 收斂)。

    回應帶 `<SubDataType>:` 前綴 —— tc4 的 `_session_req(strip_prefix=True)` 會剝掉它
    (同 tests/live/test_stock_bars.py 的 `_pager`)。
    """

    def handler(obj: dict) -> bytes:
        if sent is not None:
            sent.append(obj)
        if obj["Request"] == "GETHISDATA":
            dtype = obj["Param"]["SubDataType"]
            qi = obj["Param"]["QryIndex"]
            served = rows if qi == "0" else []
            body = json.dumps({"Success": "OK", "HisData": served})
            return (f"{dtype}:" + body + "\0").encode()
        return (json.dumps({"Success": "OK"}) + "\0").encode()

    return FuturesQuoteSource(api=FakeApi(handler), session="s1", poll_wait_secs=0.0)


class TestFetchBarsRange:
    def test_daily_uses_dk_and_futures_symbol(self) -> None:
        sent: list[dict] = []
        src = _source([_dk_row("20260729", "23000", "23200", "22900", "23100")], sent)
        bars = src.fetch_bars_range("TXF", "D", "2026-07-01", "2026-07-30")
        assert bars == [
            {
                "t": "2026-07-29",
                "o": 23_000_000,
                "h": 23_200_000,
                "l": 22_900_000,
                "c": 23_100_000,
                "v": 100,
            }
        ]
        hist = [o for o in sent if o["Request"] in ("SUBQUOTE", "GETHISDATA")]
        assert all(o["Param"]["Symbol"] == "TC.F.TWF.TXF.HOT" for o in hist)
        assert all(o["Param"]["SubDataType"] == "DK" for o in hist)
        # 全日窗:期貨日盤 08:45 起、夜盤跨午夜,套個股的 00–06 UTC 窗會切掉一大半
        assert hist[0]["Param"]["StartTime"] == "2026070100"
        assert hist[0]["Param"]["EndTime"] == "2026073023"

    def test_product_routing(self) -> None:
        sent: list[dict] = []
        src = _source([], sent)
        src.fetch_bars_range("MXF", "D", "2026-07-30", "2026-07-30")
        assert sent[0]["Param"]["Symbol"] == "TC.F.TWF.MXF.HOT"

    def test_minute_uses_1k_and_futures_session_domain(self) -> None:
        """期貨日盤 08:45–13:45(台北)。個股域 0901–1330 會把開盤前 15 分與
        13:31–13:45 全丟掉 —— 台指期的 08:45 開盤跳空是看盤重點,不可默默消失。"""
        rows = [
            _k1_row("20260730", "004600", "23000", "23010", "22990", "23005"),  # 台北 08:46
            _k1_row("20260730", "010100", "23005", "23020", "23000", "23015"),  # 09:01
            _k1_row("20260730", "054500", "23100", "23110", "23090", "23105"),  # 13:45
            _k1_row("20260730", "150000", "23200", "23210", "23190", "23205"),  # 23:00 夜盤
        ]
        src = _source(rows)
        bars = src.fetch_bars_range("TXF", "1", "2026-07-30", "2026-07-30")
        assert [b["t"] for b in bars] == [
            "2026-07-30 08:46",
            "2026-07-30 09:01",
            "2026-07-30 13:45",
        ]

    def test_empty_first_page_returns_empty(self) -> None:
        src = _source([])
        assert src.fetch_bars_range("TXF", "1", "2026-07-30", "2026-07-30") == []


class TestAlldaySession:
    """SC-3:`session="allday"` 的近全段(日盤 + 夜盤兩半)。

    台北日 D 的凌晨段(00:00–05:00)落在 **UTC 日 D−1 的 16:00–21:00** —— 窗不前移就
    整段抓不到,而失效樣態是「圖照畫、只是每天凌晨五小時憑空消失」,沒有任何錯誤訊號。
    """

    @staticmethod
    def _window(sent: list[dict]) -> tuple[str, str]:
        hist = [o for o in sent if o["Request"] in ("SUBQUOTE", "GETHISDATA")]
        return hist[0]["Param"]["StartTime"], hist[0]["Param"]["EndTime"]

    def test_window_start_shifts_back_one_day(self) -> None:
        sent: list[dict] = []
        src = _source([], sent)
        src.fetch_bars_range("TXF", "1", "2026-07-30", "2026-07-30", session="allday")
        assert self._window(sent) == ("2026072916", "2026073023")

    def test_window_shift_crosses_month(self) -> None:
        sent: list[dict] = []
        src = _source([], sent)
        src.fetch_bars_range("TXF", "1", "2026-08-01", "2026-08-03", session="allday")
        assert self._window(sent) == ("2026073116", "2026080323")

    def test_window_shift_crosses_year(self) -> None:
        sent: list[dict] = []
        src = _source([], sent)
        src.fetch_bars_range("TXF", "1", "2026-01-01", "2026-01-01", session="allday")
        assert self._window(sent) == ("2025123116", "2026010123")

    def test_day_session_window_unchanged(self) -> None:
        """預設 session(day)的窗與行為零改動 —— 既有 caller 全不受影響。"""
        sent: list[dict] = []
        src = _source([], sent)
        src.fetch_bars_range("TXF", "1", "2026-07-30", "2026-07-30")
        assert self._window(sent) == ("2026073000", "2026073023")

    def test_daily_ignores_session(self) -> None:
        """tf="D" 無 session 維度:窗與 SubDataType 都不因 allday 而變。"""
        sent: list[dict] = []
        src = _source([], sent)
        src.fetch_bars_range("TXF", "D", "2026-07-30", "2026-07-30", session="allday")
        assert self._window(sent) == ("2026073000", "2026073023")
        assert sent[0]["Param"]["SubDataType"] == "DK"

    def test_allday_bars_span_both_sessions_and_filter_out_of_range_taipei_days(self) -> None:
        rows = [
            # 台北 2026-07-29 15:01(UTC 07:01)—— **這列其實在取數窗外**(窗起點是
            # UTC 20260729 16:00),不是「前移窗多收到的」。留著是 filter 的防禦樣本:
            # 真正被多收的是最後一列那種高端次日凌晨(TZ-1 更正)
            _k1_row("20260729", "070100", "23000", "23000", "23000", "23000", "1", "1"),
            # 台北 2026-07-30 00:00(UTC 16:00,= 窗起點)—— 正是前移窗要救回來的那段
            _k1_row("20260729", "160000", "23010", "23010", "23010", "23010", "1", "2"),
            _k1_row("20260730", "004600", "23020", "23020", "23020", "23020", "1", "3"),  # 08:46
            _k1_row("20260730", "070100", "23030", "23030", "23030", "23030", "1", "4"),  # 15:01
            # 台北 2026-07-31 00:00 —— end_date 之後,同樣被 filter 丟棄
            _k1_row("20260730", "160000", "23040", "23040", "23040", "23040", "1", "5"),
        ]
        src = _source(rows)
        bars = src.fetch_bars_range("TXF", "1", "2026-07-30", "2026-07-30", session="allday")
        assert [b["t"] for b in bars] == [
            "2026-07-30 00:00",
            "2026-07-30 08:46",
            "2026-07-30 15:01",
        ]

    #: (UTC 日期, UTC HHMMSS, 期望的台北終點標記 / None = 域外丟棄)。
    #: 每一列各鎖住 `FUTURES_ALLDAY_DOMAIN` 的一個段界元素(review TC-1):把任一元素
    #: 改壞(日盤收盤 1345→1340、clamp 1350→1345、夜盤前半 end 2359→2300、後半
    #: start 0000→0100、收盤 0500→0400、clamp 0505→0500)都必有一列翻紅。
    _BOUNDS: tuple[tuple[str, str, str | None], ...] = (
        ("20260730", "054500", "2026-07-30 13:45"),  # 日盤收盤那根(段 end)
        ("20260730", "054700", "2026-07-30 13:45"),  # 收盤補正 clamp 窗內 → 併回 13:45
        ("20260730", "055500", None),  # 13:55 已在 clamp 窗外 → 丟
        ("20260730", "155900", "2026-07-30 23:59"),  # 夜盤前半 end(跨午夜前最後一根)
        ("20260729", "210000", "2026-07-30 05:00"),  # 夜盤後半收盤(UTC 前一日)
        ("20260729", "210300", "2026-07-30 05:00"),  # 05:03 clamp → 05:00
        ("20260729", "211000", None),  # 05:10 已在 clamp 窗外 → 丟
    )

    def test_allday_segment_boundaries(self) -> None:
        """段界逐點走**真的 `fetch_bars_range`**(不是直接餵 parse_1k_bars):
        窗前移 → 收割 → parse → 台北日期 filter 整條鏈都在斷言範圍內。"""
        for date, time, expect in self._BOUNDS:
            src = _source([_k1_row(date, time, "23000", "23000", "23000", "23000", "1", "1")])
            bars = src.fetch_bars_range("TXF", "1", "2026-07-30", "2026-07-30", session="allday")
            assert [b["t"] for b in bars] == ([] if expect is None else [expect]), (date, time)

    def test_day_close_clamped_rows_merge_into_one_bar(self) -> None:
        """13:45 與 13:47 是同一根 —— clamp 後同 t 必須合併(不是兩根 13:45)。"""
        rows = [
            _k1_row("20260730", "054500", "23100", "23100", "23100", "23100", "2", "1"),
            _k1_row("20260730", "054700", "23110", "23110", "23110", "23110", "3", "2"),
        ]
        bars = _source(rows).fetch_bars_range(
            "TXF", "1", "2026-07-30", "2026-07-30", session="allday"
        )
        assert bars == [
            {
                "t": "2026-07-30 13:45",
                "o": 23_100_000,
                "h": 23_110_000,
                "l": 23_100_000,
                "c": 23_110_000,
                "v": 5,
            }
        ]

    def test_day_session_drops_night_rows(self) -> None:
        """同一批 rows 在 day session 下只剩日盤段(既有語意)。"""
        rows = [
            _k1_row("20260730", "004600", "23020", "23020", "23020", "23020", "1", "1"),
            _k1_row("20260730", "070100", "23030", "23030", "23030", "23030", "1", "2"),
        ]
        src = _source(rows)
        bars = src.fetch_bars_range("TXF", "1", "2026-07-30", "2026-07-30")
        assert [b["t"] for b in bars] == ["2026-07-30 08:46"]
