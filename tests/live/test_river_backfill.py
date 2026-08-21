"""1K 當日回補(SC-3/SC-4):分頁收割、首頁未備妥回空、兩個 source 的窗與 symbol。"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import pytest

from copycat.live.corr_source import CorrQuoteSource
from copycat.live.futures_source import FuturesQuoteSource
from copycat.live.river_models import all_day_utc_window
from copycat.live.tc4 import HistoryTimeoutError
from tests.helpers.tc4_fakes import FakeApi, ok


def _his(rows: list[dict]) -> bytes:
    """GETHISDATA 回應帶 "<type>:" 前綴(tc4._get_history strip_prefix 語意)。"""
    return ("1K:" + json.dumps({"Success": "OK", "HisData": rows}) + "\0").encode()


def _row(qry: int, time_utc: str, close: str, date: str | None = None) -> dict:
    """`Date` 預設 = **窗口的 UTC 日**(不是寫死的過去日期)。

    回補窗是「今天(UTC)」,而收割器現在會丟掉 `Date` 不等於窗口日的列(凍結 stub 的
    簽名)—— 治具寫死舊日期的話,鎖分頁/解析的那幾條會被 Date 閘整批丟掉而變成假紅。
    """
    return {
        "Date": date if date is not None else all_day_utc_window()[0][:8],
        "Time": time_utc,
        "Open": close,
        "High": close,
        "Low": close,
        "Close": close,
        "Volume": "10",
        "QryIndex": str(qry),
    }


PAGES = {
    "0": [_row(1, "004600", "51666"), _row(2, "004700", "51680")],
    "2": [_row(3, "004800", "51700"), _row(4, "004900", "51710")],
    "4": [],
}


def _paging_handler(sent: list[dict]) -> Any:
    def handler(obj: dict) -> bytes:
        sent.append(obj)
        if obj["Request"] != "GETHISDATA":
            return ok()
        return _his(PAGES.get(obj["Param"]["QryIndex"], []))

    return handler


class TestCorrSourceFetchDay1k:
    def test_harvests_all_pages_and_parses_minutes(self) -> None:
        sent: list[dict] = []
        src = CorrQuoteSource(api=FakeApi(_paging_handler(sent)), session="s1")

        assert src.fetch_day_1k("TC.F.CME.ES.HOT") == [
            (526, 51_666_000),
            (527, 51_680_000),
            (528, 51_700_000),
            (529, 51_710_000),
        ]

    def test_subscribes_1k_with_all_day_utc_window(self) -> None:
        sent: list[dict] = []
        src = CorrQuoteSource(api=FakeApi(_paging_handler(sent)), session="s1")
        src.fetch_day_1k("TC.F.CME.ES.HOT")

        sub = next(o for o in sent if o["Request"] == "SUBQUOTE")
        assert sub["Param"]["SubDataType"] == "1K"
        assert (sub["Param"]["StartTime"], sub["Param"]["EndTime"]) == all_day_utc_window()

    def test_empty_first_page_raises_without_blocking(self) -> None:
        """**事前標記該變的既有斷言**(舊名 `test_empty_first_page_returns_empty_without_blocking`)。

        2026-08-23 08:23 真實事故:TXF/TWN/SXF 三腿同秒逾時回空 → 引擎讀成「這幾腿今天
        沒有 1K」,整天不再回補。回空是唯一把逾時訊號丟掉的地方,所以改 raise;
        「不阻塞」那一半照舊鎖住(poll_wait=0 = 探測一次就走)。
        """

        def handler(obj: dict) -> bytes:
            return _his([]) if obj["Request"] == "GETHISDATA" else ok()

        src = CorrQuoteSource(api=FakeApi(handler), session="s1", poll_wait_secs=0)
        started = time.monotonic()

        with pytest.raises(HistoryTimeoutError):
            src.fetch_day_1k("TC.F.SGX.TWN.HOT")
        assert time.monotonic() - started < 0.5  # poll_wait=0 → 探測一次就回

    def test_ready_first_page_with_zero_harvested_rows_returns_empty(self) -> None:
        """首頁備妥(非逾時)但收割 0 列 → 回空、**不** raise。

        契約邊界:`timed_out` 是唯一「暫時取不到」的正面訊號;首頁答得出來就代表
        TC4 不忙,空就是空,不該讓引擎排重試。
        """
        calls = {"n": 0}

        def handler(obj: dict) -> bytes:
            if obj["Request"] != "GETHISDATA":
                return ok()
            calls["n"] += 1
            # 第一發 = 首頁探測(備妥);之後的收割回空頁 → iter_qry_pages 立即收斂
            return _his([_row(1, "004600", "51666")] if calls["n"] == 1 else [])

        src = CorrQuoteSource(api=FakeApi(handler), session="s1", poll_wait_secs=0)
        assert src.fetch_day_1k("TC.F.SGX.TWN.HOT") == []

    def test_rows_from_another_utc_day_are_dropped(self) -> None:
        """凍結 stub 的列帶著**別的日期**,只讀 `Time` 會把它變成今日分鐘(repro §症狀)。"""

        def handler(obj: dict) -> bytes:
            if obj["Request"] != "GETHISDATA":
                return ok()
            qi = obj["Param"]["QryIndex"]
            if qi != "0":
                return _his([])
            return _his(
                [
                    _row(1, "004600", "51666", date="20200101"),  # 窗外日 → 丟
                    _row(2, "004700", "51680"),  # 窗口日 → 留
                ]
            )

        src = CorrQuoteSource(api=FakeApi(handler), session="s1", poll_wait_secs=0)
        assert src.fetch_day_1k("TC.F.SGX.TWN.HOT") == [(527, 51_680_000)]

    def test_all_rows_dropped_warns_frozen_stub(self, caplog: pytest.LogCaptureFixture) -> None:
        """rows 非空但 minutes 全空 = 毒化訂閱簽名 —— 沿 `stock_source` 的固定字串。"""

        def handler(obj: dict) -> bytes:
            if obj["Request"] != "GETHISDATA":
                return ok()
            qi = obj["Param"]["QryIndex"]
            return _his([_row(1, "004600", "51666", date="20200101")] if qi == "0" else [])

        src = CorrQuoteSource(api=FakeApi(handler), session="s1", poll_wait_secs=0)
        with caplog.at_level(logging.WARNING):
            assert src.fetch_day_1k("TC.F.SGX.TWN.HOT") == []
        assert "疑似凍結 stub" in caplog.text


class TestFuturesSourceFetchDay1k:
    def test_product_maps_to_twf_hot_symbol(self) -> None:
        sent: list[dict] = []
        src = FuturesQuoteSource(api=FakeApi(_paging_handler(sent)), session="s1")

        minutes = src.fetch_day_1k("TXF")

        sub = next(o for o in sent if o["Request"] == "SUBQUOTE")
        assert sub["Param"]["Symbol"] == "TC.F.TWF.TXF.HOT"
        assert sub["Param"]["SubDataType"] == "1K"
        assert minutes[0] == (526, 51_666_000)
