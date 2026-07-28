from __future__ import annotations

from copycat.live.futures_models import (
    PRODUCTS,
    parse_futures_realtime,
    product_from_symbol,
    resolve_contract_ym,
)


def _quote(**over: object) -> dict:
    q: dict = {
        "Symbol": "TC.F.TWF.TXF.HOT",
        "Security": "FITX",
        "SecurityName": "臺股期貨",
        "TradingPrice": "23500",
        "TradeQuantity": "2",
        "TradeVolume": "1000",
        "TradeDate": "20260728",
        "PreciseTime": "10000000000",
        "Bid": "23499",
        "Bid1": "23498",
        "BidVolume": "10",
        "BidVolume1": "20",
        "Ask": "23500",
        "Ask1": "23501",
        "AskVolume": "12",
        "AskVolume1": "22",
        "ReferencePrice": "23400",
        "UpperLimitPrice": "25740",
        "LowerLimitPrice": "21060",
    }
    q.update(over)
    return q


class TestProducts:
    def test_three_products(self) -> None:
        assert PRODUCTS == ("TXF", "MXF", "TMF")


class TestProductFromSymbol:
    def test_hot_form(self) -> None:
        assert product_from_symbol("TC.F.TWF.TXF.HOT") == "TXF"

    def test_ym_form(self) -> None:
        # 推播 symbol 可能已是實際月份形(TC4 是否展開 HOT 未定,兩形都要認得)
        assert product_from_symbol("TC.F.TWF.MXF.202609") == "MXF"

    def test_non_futures_none(self) -> None:
        assert product_from_symbol("TC.S.TWS.2330") is None
        assert product_from_symbol("") is None


class TestResolveContractYm:
    """HOT → 實際契約月份 YYYYMM(純函式;解析不到 None = 送單層拒單,不猜月份)。"""

    def test_symbol_ym_form_direct(self) -> None:
        assert resolve_contract_ym({"Symbol": "TC.F.TWF.TXF.202609"}) == "202609"

    def test_hot_symbol_falls_back_to_end_date(self) -> None:
        # TXO REALTIME 實測有 EndDate(到期日;期貨結算日落在契約月)
        payload = {"Symbol": "TC.F.TWF.TXF.HOT", "EndDate": "20260916"}
        assert resolve_contract_ym(payload) == "202609"

    def test_security_name_embedded_ym(self) -> None:
        payload = {"Symbol": "TC.F.TWF.TXF.HOT", "SecurityName": "臺股期貨2026/09"}
        assert resolve_contract_ym(payload) == "202609"

    def test_security_embedded_ym(self) -> None:
        payload = {"Symbol": "TC.F.TWF.TXF.HOT", "Security": "TXF202610"}
        assert resolve_contract_ym(payload) == "202610"

    def test_symbol_wins_over_end_date(self) -> None:
        payload = {"Symbol": "TC.F.TWF.TXF.202609", "EndDate": "20261021"}
        assert resolve_contract_ym(payload) == "202609"

    def test_no_candidates_none(self) -> None:
        payload = {"Symbol": "TC.F.TWF.TXF.HOT", "Security": "FITX", "SecurityName": "臺股期貨"}
        assert resolve_contract_ym(payload) is None

    def test_invalid_month_rejected(self) -> None:
        assert resolve_contract_ym({"Symbol": "TC.F.TWF.TXF.202613"}) is None
        assert resolve_contract_ym({"Symbol": "TC.F.TWF.TXF.HOT", "EndDate": "20261301"}) is None

    def test_empty_payload_none(self) -> None:
        assert resolve_contract_ym({}) is None


class TestParseReuse:
    """期貨 REALTIME 欄位與個股同構 → 直接重用 stock_models 對映(五檔位移歸一同款)。"""

    def test_book_offset_normalized_and_millipt(self) -> None:
        tick, book, meta = parse_futures_realtime(_quote())
        assert book.bids == [(23_499_000, 10), (23_498_000, 20)]
        assert book.asks == [(23_500_000, 12), (23_501_000, 22)]
        assert meta.ref_milli == 23_400_000
        assert meta.upper_milli == 25_740_000
        assert meta.lower_milli == 21_060_000
        assert tick is not None
        assert tick.price_milli == 23_500_000
        assert tick.qty == 2
        assert tick.cum_vol == 1000
        assert tick.time == "09:00:00.000"  # PreciseTime UTC +8
        assert tick.trade_date == "2026-07-28"

    def test_book_only_update_has_no_tick(self) -> None:
        tick, book, _meta = parse_futures_realtime(_quote(TradingPrice="", TradeQuantity=""))
        assert tick is None
        assert book.bids  # 純簿更新仍要有五檔
