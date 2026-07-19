"""SC-1:下單資料模型 — param 對映 / 價格轉換 / 回報 parse / 遮罩 / sim 分類。"""

from __future__ import annotations

import pytest

from copycat.live.trade_models import (
    AccountInfo,
    BrokerRejectedError,
    OrderRequest,
    TouchanceDownError,
    classify_is_sim,
    mask_account,
    millipts_from_price_str,
    parse_accounts,
    parse_execution_report,
    parse_fill_report,
    price_str_from_millipts,
    to_neworder_param,
)


def req(**kw: object) -> OrderRequest:
    base: dict = {
        "symbol": "TC.O.TWF.TXO.202607.C.23000",
        "side": "buy",
        "kind": "limit",
        "qty": 2,
        "price_millipts": 15500,
    }
    base.update(kw)
    return OrderRequest(**base)


class TestToNewOrderParam:
    def test_limit_buy_maps_rod_limit_with_price(self) -> None:
        param = to_neworder_param(req(), broker_id="SIM", account="9999000")
        assert param["Symbol"] == "TC.O.TWF.TXO.202607.C.23000"
        assert param["BrokerID"] == "SIM"
        assert param["Account"] == "9999000"
        assert param["Side"] == "1"
        assert param["OrderType"] == "2"
        assert param["TimeInForce"] == "1"
        assert param["Price"] == "15.5"
        assert param["OrderQty"] == "2"
        assert param["PositionEffect"] == "4"

    def test_limit_sell_side_2(self) -> None:
        param = to_neworder_param(req(side="sell"), broker_id="B", account="A")
        assert param["Side"] == "2"

    def test_market_is_ioc_without_price_key(self) -> None:
        param = to_neworder_param(
            req(kind="market", price_millipts=None), broker_id="B", account="A"
        )
        assert param["OrderType"] == "1"
        assert param["TimeInForce"] == "2"
        assert "Price" not in param

    def test_limit_without_price_raises(self) -> None:
        with pytest.raises(ValueError):
            to_neworder_param(req(price_millipts=None), broker_id="B", account="A")


class TestPriceConversion:
    @pytest.mark.parametrize(
        ("millipts", "expected"),
        [(15500, "15.5"), (23_000_000, "23000"), (500, "0.5"), (100, "0.1"), (1000, "1")],
    )
    def test_price_str_from_millipts(self, millipts: int, expected: str) -> None:
        assert price_str_from_millipts(millipts) == expected

    @pytest.mark.parametrize(
        ("text", "expected"),
        [("15.5", 15500), ("23000", 23_000_000), ("0.5", 500), ("1", 1000)],
    )
    def test_millipts_from_price_str(self, text: str, expected: int) -> None:
        assert millipts_from_price_str(text) == expected

    @pytest.mark.parametrize("text", ["abc", "", "-5", "1.2.3", " "])
    def test_invalid_price_str_raises(self, text: str) -> None:
        with pytest.raises(ValueError):
            millipts_from_price_str(text)

    def test_roundtrip(self) -> None:
        assert millipts_from_price_str(price_str_from_millipts(15500)) == 15500


class TestParsers:
    def test_parse_accounts(self) -> None:
        msg = {
            "Accounts": [
                {"BrokerID": "SIM", "Account": "9999000", "AccountMask": "SIM-9999000"},
            ]
        }
        accounts = parse_accounts(msg)
        assert len(accounts) == 1
        acc = accounts[0]
        assert acc.broker_id == "SIM"
        assert acc.account == "9999000"
        assert acc.account_mask == "SIM-9999000"
        assert acc.raw["BrokerID"] == "SIM"

    def test_parse_accounts_missing_fields_defaults_empty(self) -> None:
        accounts = parse_accounts({"Accounts": [{}]})
        assert accounts[0].broker_id == ""
        assert accounts[0].account == ""

    def test_parse_execution_report_full(self) -> None:
        r = {
            "ReportID": "4094755221B",
            "Symbol": "TC.F.TWF.FITX.HOT",
            "Side": "1",
            "OrdStatus": "4",
            "Price": "23000",
            "OrderQty": "1",
            "CumQty": "0",
            "ErrCode": "-22",
            "ErrMsg": "tick size",
        }
        rep = parse_execution_report(r)
        assert rep.report_id == "4094755221B"
        assert rep.status_raw == "4"
        assert rep.err_code == "-22"
        assert rep.err_msg == "tick size"
        assert rep.raw is r

    def test_parse_execution_report_missing_fields(self) -> None:
        rep = parse_execution_report({"ReportID": "X"})
        assert rep.report_id == "X"
        assert rep.symbol == ""
        assert rep.err_code is None
        assert rep.err_msg is None

    def test_parse_fill_report(self) -> None:
        rep = parse_fill_report({"ReportID": "F1", "Symbol": "S", "MatchedPrice": "15.5"})
        assert rep.report_id == "F1"
        assert rep.raw["MatchedPrice"] == "15.5"


class TestMaskAccount:
    def test_masks_all_but_last_4(self) -> None:
        assert mask_account("12345678") == "****5678"

    def test_short_account_fully_masked(self) -> None:
        assert mask_account("123") == "****"

    def test_empty(self) -> None:
        assert mask_account("") == "****"


def acc(broker_id: str) -> AccountInfo:
    return AccountInfo(broker_id=broker_id, account="1", account_mask="m", raw={})


class TestClassifyIsSim:
    def test_case_insensitive_substring(self) -> None:
        assert classify_is_sim(acc("TCSimulate"), ["sim"]) is True
        assert classify_is_sim(acc("SIM-DEV"), ["sim"]) is True

    def test_no_match_is_live(self) -> None:
        assert classify_is_sim(acc("F999"), ["sim"]) is False

    def test_empty_patterns_never_sim(self) -> None:
        assert classify_is_sim(acc("SIM"), []) is False


class TestErrors:
    def test_broker_rejected_carries_code(self) -> None:
        e = BrokerRejectedError("-22", "tick size")
        assert e.err_code == "-22"
        assert e.err_msg == "tick size"

    def test_touchance_down_is_exception(self) -> None:
        assert issubclass(TouchanceDownError, Exception)
