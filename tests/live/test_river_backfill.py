"""1K 當日回補(SC-3/SC-4):分頁收割、首頁未備妥回空、兩個 source 的窗與 symbol。"""

from __future__ import annotations

import json
import time
from typing import Any

from copycat.live.corr_source import CorrQuoteSource
from copycat.live.futures_source import FuturesQuoteSource
from copycat.live.river_models import all_day_utc_window
from tests.helpers.tc4_fakes import FakeApi, ok


def _his(rows: list[dict]) -> bytes:
    """GETHISDATA 回應帶 "<type>:" 前綴(tc4._get_history strip_prefix 語意)。"""
    return ("1K:" + json.dumps({"Success": "OK", "HisData": rows}) + "\0").encode()


def _row(qry: int, time_utc: str, close: str) -> dict:
    return {
        "Date": "20260730",
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

    def test_empty_first_page_returns_empty_without_blocking(self) -> None:
        def handler(obj: dict) -> bytes:
            return _his([]) if obj["Request"] == "GETHISDATA" else ok()

        src = CorrQuoteSource(api=FakeApi(handler), session="s1", poll_wait_secs=0)
        started = time.monotonic()

        assert src.fetch_day_1k("TC.F.SGX.TWN.HOT") == []
        assert time.monotonic() - started < 0.5  # poll_wait=0 → 探測一次就回


class TestFuturesSourceFetchDay1k:
    def test_product_maps_to_twf_hot_symbol(self) -> None:
        sent: list[dict] = []
        src = FuturesQuoteSource(api=FakeApi(_paging_handler(sent)), session="s1")

        minutes = src.fetch_day_1k("TXF")

        sub = next(o for o in sent if o["Request"] == "SUBQUOTE")
        assert sub["Param"]["Symbol"] == "TC.F.TWF.TXF.HOT"
        assert sub["Param"]["SubDataType"] == "1K"
        assert minutes[0] == (526, 51_666_000)
