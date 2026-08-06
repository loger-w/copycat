"""個股期合約發現(stkfut-contracts SC-1):Fut2 catalog parser + list_stock_futures。

fixture = `tests/fixtures/catalog_fut2_sample.json`,自 `spikes/catalog_dump/
catalog_Fut2.json`(2026-06-30 真 dump)裁 —— 保留兩支 `Node`(`StockFutures` 真合約 /
`StockFutures(F2)` 價差)、HOT 節點(無 SYMBOL)、除權息調整契約(EE1)與 ETF(0050),
即 parser 四種反例各一。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import pytest

from copycat.live.tc4 import TC4QuoteSource, parse_stkfut_catalog

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "catalog_fut2_sample.json"


def _res() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class TestParseStkfutCatalog:
    def test_std_and_mini_split_by_product(self) -> None:
        """2330 = 標準 CDF + 小型 QFF;月份取四段形的 YYYYMM(裸產品節點不入列)。"""
        entry = parse_stkfut_catalog(_res())["2330"]
        assert entry["name"] == "台積電"
        assert entry["std"] == {
            "prod": "CDF",
            "contracts": ["202607", "202608", "202609", "202612", "202703"],
        }
        assert entry["mini"] == {
            "prod": "QFF",
            "contracts": ["202607", "202608", "202609", "202612", "202703"],
        }

    def test_spread_branch_excluded(self) -> None:
        """`StockFutures(F2)`(價差)整支排除 —— 只留它時輸出必須是空的。

        價差節點名與真合約**逐字同名**(「台積電(2330)」),差別只在無 `SYMBOL` 欄與
        六段跨月 Contracts;誤收會讓下拉多出「202607.CDF.202608」這種選項,
        訂閱後零推播而毫無錯誤訊號。
        """
        res = _res()
        branches = res["Instruments"]["Node"]
        res["Instruments"]["Node"] = [b for b in branches if b["ENG"] == "StockFutures(F2)"]
        assert parse_stkfut_catalog(res) == {}

    def test_hot_node_without_symbol_ignored(self) -> None:
        """HOT(熱門月)節點無 `SYMBOL` 欄但 Contracts 是合法四段形 → 不得產生條目。"""
        parsed = parse_stkfut_catalog(_res())
        assert set(parsed) == {"0050", "1312", "2330"}
        for entry in parsed.values():
            assert entry["std"]["prod"] != "HOT"

    def test_adjusted_contract_not_taken_as_std(self) -> None:
        """除權息調整契約(國喬1 = EE1)不得蓋掉原始 EEF,且不算小型。"""
        entry = parse_stkfut_catalog(_res())["1312"]
        assert entry["std"]["prod"] == "EEF"
        assert entry["mini"] is None

    def test_etf_pair_included(self) -> None:
        """ETF 期貨照收(行情/顯示可用;下單層另有閘,SC-6)。"""
        entry = parse_stkfut_catalog(_res())["0050"]
        assert entry["std"]["prod"] == "NYF"
        assert entry["mini"]["prod"] == "SRF"

    def test_month_shapes_are_six_digit_only(self) -> None:
        parsed = parse_stkfut_catalog(_res())
        for entry in parsed.values():
            for leg in (entry["std"], entry["mini"]):
                if leg is None:
                    continue
                assert all(len(ym) == 6 and ym.isdigit() for ym in leg["contracts"])


class _CatalogSocket:
    def __init__(self, res: dict) -> None:
        self.requests: list[dict] = []
        self._res = res

    def send_string(self, payload: str) -> None:
        self.requests.append(json.loads(payload))

    def recv(self) -> bytes:
        return json.dumps(self._res).encode() + b"\x00"


class _CatalogApi:
    def __init__(self, res: dict) -> None:
        self.lock = threading.Lock()
        self.socket = _CatalogSocket(res)


class TestListStockFutures:
    def test_queries_fut2_type_and_parses(self) -> None:
        api = _CatalogApi(_res())
        src = TC4QuoteSource(port="0", api=api, session="sess-1")
        result = src.list_stock_futures()
        assert api.socket.requests[0]["Request"] == "QUERYALLINSTRUMENT"
        assert api.socket.requests[0]["Type"] == "Fut2"
        assert result["2330"]["std"]["prod"] == "CDF"

    def test_failed_reply_raises_connection_error(self) -> None:
        api = _CatalogApi({"Success": "Fail", "ErrMsg": "boom"})
        src = TC4QuoteSource(port="0", api=api, session="sess-1")
        with pytest.raises(ConnectionError):
            src.list_stock_futures()


def test_fixture_keeps_both_branches() -> None:
    """fixture 的形狀本身是被測前提(價差反例在不在):裁錯了要在這裡紅,不是在別處綠。"""
    res: dict[str, Any] = _res()
    assert [b["ENG"] for b in res["Instruments"]["Node"]] == [
        "StockFutures",
        "StockFutures(F2)",
    ]
