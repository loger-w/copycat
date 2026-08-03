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
