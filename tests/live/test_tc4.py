from __future__ import annotations

from typing import Any

from copycat.live.tc4 import TC4QuoteSource, build_rt_request, group_series

SYMS = [
    "TC.O.TWF.TX4.202607.C.44550",
    "TC.O.TWF.TX4.202607.P.44550",
    "TC.O.TWF.TX4.202607.C.44600",
    "TC.O.TWF.TX5.202607.C.44550",
    "TC.O.TWF.TXO.202608.C.44550",
    "TC.O.TWF.TXO.202608.P.44000",
    "TC.F.TWF.FITX.HOT",  # 非期權,應被忽略
    "TC.O.TWF.TXO.202608",  # 產品層節點,非葉子
]


class TestGroupSeries:
    def test_groups_leaf_symbols_by_prod_expiry(self) -> None:
        series = group_series(SYMS)
        ids = [s.series_id for s in series]
        assert ids == ["TX4.202607", "TX5.202607", "TXO.202608"]
        tx4 = series[0]
        assert len(tx4.contracts) == 3
        assert tx4.contracts[0].strike_millipts == 44_550_000
        assert tx4.name == "TX4 202607"

    def test_nearest_expiry_sorts_first(self) -> None:
        series = group_series(["TC.O.TWF.TXO.202612.C.44000", "TC.O.TWF.TXO.202608.C.44000"])
        assert [s.series_id for s in series] == ["TXO.202608", "TXO.202612"]


class TestBuildRtRequest:
    def test_subquote_carries_time_window(self) -> None:
        obj = build_rt_request("SUBQUOTE", "sess-1", "TC.F.TWF.FITX.HOT", "20260718")
        assert obj == {
            "Request": "SUBQUOTE",
            "SessionKey": "sess-1",
            "Param": {
                "Symbol": "TC.F.TWF.FITX.HOT",
                "SubDataType": "REALTIME",
                "StartTime": "2026071800",
                "EndTime": "2026071806",
            },
        }


class FakeApi:
    """最小 QuoteAPI 替身:GetHistory 分頁 + 呼叫記錄。"""

    def __init__(self, pages: dict[str, list[list[dict]]]) -> None:
        self.pages = pages
        self.sub_history_calls: list[str] = []
        self.disconnected = False

    def SubHistory(self, session: str, sym: str, dtype: str, start: str, end: str) -> None:  # noqa: N802
        self.sub_history_calls.append(sym)

    def GetHistory(  # noqa: N802
        self, session: str, sym: str, dtype: str, start: str, end: str, qry_index: str
    ) -> dict[str, Any]:
        # 真 TC4 語意:回傳 QryIndex 大於游標的下一批(耗盡 → 空頁)
        rows = [r for page in self.pages.get(sym, []) for r in page]
        idx = int(qry_index) if qry_index.isdigit() else 0
        remaining = [r for r in rows if int(r["QryIndex"]) > idx]
        return {"HisData": remaining[:100]}

    def Disconnect(self) -> None:  # noqa: N802
        self.disconnected = True


def hist_row(i: int, *, price: str = "100", qty: str = "1") -> dict:
    return {
        "TradingPrice": price,
        "TradeQuantity": qty,
        "Bid": "99",
        "Ask": "100",
        "PreciseTime": str(10000000000 + i),
        "QryIndex": str(i),
    }


class TestFetchBackfill:
    def test_paged_history_parsed_and_flattened(self) -> None:
        sym = "TC.O.TWF.TX4.202607.C.44550"
        pages = {
            sym: [[hist_row(i) for i in range(1, 101)], [hist_row(i) for i in range(101, 121)]]
        }
        src = TC4QuoteSource(port="0", api=FakeApi(pages), session="sess-1", poll_wait_secs=0.0)
        series = group_series([sym])[0]
        ticks = src.fetch_backfill(series)
        assert len(ticks) == 120
        assert ticks[0].symbol == sym
        assert ticks[0].price_millipts == 100_000
