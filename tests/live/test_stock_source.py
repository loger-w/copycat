from __future__ import annotations

import json
import logging
import threading

import pytest

from copycat.live.stock_source import StockQuoteSource, stock_symbol, stock_window
from tests.helpers.tc4_fakes import FakeApi, ok

HIST_ROW = {
    "Date": "20260721",
    "FilledTime": "10006",
    "TradeQuantity": "10",
    "TradeVolume": "10",
    "Bid": "2415",
    "Ask": "2420",
    "TradingPrice": "2415",
    "PreciseTime": "10006840000",
    "QryIndex": "1",
}


class TestSymbolAndWindow:
    def test_stock_symbol(self) -> None:
        assert stock_symbol("2330") == "TC.S.TWS.2330"

    def test_future_prefix_maps_to_twf_hot(self) -> None:
        # 期現對照加訂個股期:F:<prod> → 期貨樹 HOT(2026-07-21 real-env 實證:
        # 誤組成 TC.S.TWS.CDF.HOT 時 SUBQUOTE 照回 OK,零錯誤訊號)
        assert stock_symbol("F:CDF") == "TC.F.TWF.CDF.HOT"

    def test_stock_window_utc_day(self) -> None:
        assert stock_window("2026-07-21") == ("2026072100", "2026072106")


class TestSubscribe:
    def test_subscribe_unsub_then_sub_with_day_window(self) -> None:
        sent: list[dict] = []

        def handler(obj: dict) -> bytes:
            sent.append(obj)
            return ok()

        src = StockQuoteSource(api=FakeApi(handler), session="s1", trade_date="2026-07-21")
        src.subscribe_symbol("2330")
        assert [o["Request"] for o in sent] == ["UNSUBQUOTE", "SUBQUOTE"]
        param = sent[1]["Param"]
        assert param["Symbol"] == "TC.S.TWS.2330"
        assert param["SubDataType"] == "REALTIME"
        assert param["StartTime"] == "2026072100"
        assert param["EndTime"] == "2026072106"

    def test_subscribe_starts_listener_when_sub_port_known(self) -> None:
        # 2026-07-21 real-env 實證:漏啟 listener → 訂閱成功但永收不到推播,
        # 健檢把全部檔誤標 no_data
        src = StockQuoteSource(api=FakeApi(lambda o: ok()), session="s1", trade_date="2026-07-21")
        src._sub_port = "59999"  # 模擬真連線已知 SubPort
        src.subscribe_symbol("2330")
        assert src._listener is not None

    def test_subscribe_without_sub_port_skips_listener(self) -> None:
        # 注入測試路徑(無真連線)不得因 listener 缺 SubPort 而炸
        src = StockQuoteSource(api=FakeApi(lambda o: ok()), session="s1", trade_date="2026-07-21")
        src.subscribe_symbol("2330")
        assert src._listener is None

    def test_subscribe_failure_raises_for_rollback(self) -> None:
        def handler(obj: dict) -> bytes:
            if obj["Request"] == "SUBQUOTE":
                return (json.dumps({"Success": "Fail", "ErrMsg": "x"}) + "\0").encode()
            return ok()

        src = StockQuoteSource(api=FakeApi(handler), session="s1", trade_date="2026-07-21")
        try:
            src.subscribe_symbol("2330")
        except ConnectionError:
            pass
        else:
            raise AssertionError("subscribe 失敗必須 raise(engine refcount 回滾依賴)")


class TestBackfill:
    def test_backfill_pages_until_empty(self) -> None:
        pages = {"0": [HIST_ROW], "1": []}

        def handler(obj: dict) -> bytes:
            if obj["Request"] == "SUBQUOTE":
                return ok()
            if obj["Request"] == "GETHISDATA":
                qi = obj["Param"]["QryIndex"]
                return (
                    "TICKS:" + json.dumps({"Success": "OK", "HisData": pages.get(qi, [])}) + "\0"
                ).encode()
            return ok()

        src = StockQuoteSource(
            api=FakeApi(handler), session="s1", trade_date="2026-07-21", poll_wait_secs=0.0
        )
        ticks = src.backfill("2330")
        assert len(ticks) == 1
        assert ticks[0].code == "2330"
        assert ticks[0].price_milli == 2_415_000
        assert ticks[0].time == "09:00:06.840"


class TestFetchDailyBars:
    """SC-4 overlay 資料源:DK 優先、1K 聚合 fallback、SubDataType 欄位釘死(impl-spec R3)."""

    @staticmethod
    def _dk_row(date: str, h: str, lo: str, c: str) -> dict:
        return {"Date": date, "High": h, "Low": lo, "Close": c, "QryIndex": "1"}

    def test_dk_path_parses_and_asserts_subdatatype(self) -> None:
        sent: list[dict] = []
        pages = {
            "0": [
                self._dk_row("20260724", "101.5", "99", "100.5"),
                self._dk_row("20260727", "103", "100", "102"),
            ],
            "1": [],
        }

        def handler(obj: dict) -> bytes:
            sent.append(obj)
            if obj["Request"] == "GETHISDATA":
                qi = obj["Param"]["QryIndex"]
                return (
                    "DK:" + json.dumps({"Success": "OK", "HisData": pages.get(qi, [])}) + "\0"
                ).encode()
            return ok()

        src = StockQuoteSource(
            api=FakeApi(handler), session="s1", trade_date="2026-07-28", poll_wait_secs=0.0
        )
        bars = src.fetch_daily_bars("2330")
        assert bars == [
            {"date": "2026-07-24", "high": 101_500, "low": 99_000, "close": 100_500},
            {"date": "2026-07-27", "high": 103_000, "low": 100_000, "close": 102_000},
        ]
        dk_reqs = [o for o in sent if o["Param"].get("SubDataType") == "DK"]
        assert {o["Request"] for o in dk_reqs} == {"SUBQUOTE", "GETHISDATA"}

    def test_dk_empty_falls_back_to_1k_aggregation(self) -> None:
        sent: list[dict] = []
        k1_pages = {
            "0": [
                {
                    "Date": "20260724",
                    "Time": "10000",
                    "Open": "100",
                    "High": "101",
                    "Low": "100",
                    "Close": "100.5",
                    "Volume": "10",
                    "QryIndex": "1",
                },
                {
                    "Date": "20260724",
                    "Time": "10100",
                    "Open": "100.5",
                    "High": "102",
                    "Low": "99",
                    "Close": "101",
                    "Volume": "5",
                    "QryIndex": "2",
                },
                {
                    "Date": "20260727",
                    "Time": "10000",
                    "Open": "101",
                    "High": "103",
                    "Low": "101",
                    "Close": "102",
                    "Volume": "8",
                    "QryIndex": "3",
                },
            ],
            "3": [],
        }

        def handler(obj: dict) -> bytes:
            sent.append(obj)
            if obj["Request"] == "GETHISDATA":
                dtype = obj["Param"]["SubDataType"]
                if dtype == "DK":
                    return ("DK:" + json.dumps({"Success": "OK", "HisData": []}) + "\0").encode()
                qi = obj["Param"]["QryIndex"]
                return (
                    "1K:" + json.dumps({"Success": "OK", "HisData": k1_pages.get(qi, [])}) + "\0"
                ).encode()
            return ok()

        src = StockQuoteSource(
            api=FakeApi(handler), session="s1", trade_date="2026-07-28", poll_wait_secs=0.0
        )
        bars = src.fetch_daily_bars("2330")
        assert bars == [
            {"date": "2026-07-24", "high": 102_000, "low": 99_000, "close": 101_000},
            {"date": "2026-07-27", "high": 103_000, "low": 101_000, "close": 102_000},
        ]
        assert any(o["Param"].get("SubDataType") == "1K" for o in sent)

    def test_tail_limited_to_n(self) -> None:
        rows = [self._dk_row(f"202607{d:02d}", "10", "9", "9.5") for d in range(1, 28)]
        for i, r in enumerate(rows):
            r["QryIndex"] = str(i + 1)
        pages = {"0": rows, str(len(rows)): []}

        def handler(obj: dict) -> bytes:
            if obj["Request"] == "GETHISDATA":
                qi = obj["Param"]["QryIndex"]
                return (
                    "DK:" + json.dumps({"Success": "OK", "HisData": pages.get(qi, [])}) + "\0"
                ).encode()
            return ok()

        src = StockQuoteSource(
            api=FakeApi(handler), session="s1", trade_date="2026-07-28", poll_wait_secs=0.0
        )
        bars = src.fetch_daily_bars("2330", n=25)
        assert len(bars) == 25
        assert bars[0]["date"] == "2026-07-03"  # 27 根裁尾取最後 25

    def test_zmq_error_normalized_to_connection_error(self) -> None:
        import zmq

        def handler(obj: dict) -> bytes:
            raise zmq.ZMQError()

        src = StockQuoteSource(
            api=FakeApi(handler), session="s1", trade_date="2026-07-28", poll_wait_secs=0.0
        )
        try:
            src.fetch_daily_bars("2330")
        except ConnectionError:
            pass
        else:
            raise AssertionError("TC4 通訊失敗必須正規化為 ConnectionError(design R10)")


class TestFetchDayMinutes:
    """index-board SC-4:當日 1K → {HHMM(台北,終點標記): close 毫點};域 0901-1330。"""

    @staticmethod
    def _row(time_utc: str, close: str, qi: str) -> dict:
        return {"Date": "20260728", "Time": time_utc, "Close": close, "QryIndex": qi}

    def test_utc_plus8_domain_and_clamp(self) -> None:
        rows = [
            self._row("10100", "100.5", "1"),  # 01:01 UTC → 0901
            self._row("53000", "101", "2"),  # 13:30 → inclusive 保留
            self._row("53300", "102", "3"),  # 13:33 → clamp 1330 覆寫
            self._row("60000", "103", "4"),  # 14:00 → >1335 丟棄
            self._row("3000", "99", "5"),  # 08:30 → <0901 丟棄
        ]
        pages = {"0": rows, "5": []}

        def handler(obj: dict) -> bytes:
            if obj["Request"] == "GETHISDATA":
                qi = obj["Param"]["QryIndex"]
                return (
                    "1K:" + json.dumps({"Success": "OK", "HisData": pages.get(qi, [])}) + "\0"
                ).encode()
            return ok()

        src = StockQuoteSource(
            api=FakeApi(handler), session="s1", trade_date="2026-07-28", poll_wait_secs=0.0
        )
        minutes = src.fetch_day_minutes("IX0001")
        assert minutes == {"0901": 100_500, "1330": 102_000}

    def test_bad_rows_skipped(self) -> None:
        rows = [self._row("10100", "100", "1"), {"Date": "20260728", "QryIndex": "2"}]
        pages = {"0": rows, "2": []}

        def handler(obj: dict) -> bytes:
            if obj["Request"] == "GETHISDATA":
                qi = obj["Param"]["QryIndex"]
                return (
                    "1K:" + json.dumps({"Success": "OK", "HisData": pages.get(qi, [])}) + "\0"
                ).encode()
            return ok()

        src = StockQuoteSource(
            api=FakeApi(handler), session="s1", trade_date="2026-07-28", poll_wait_secs=0.0
        )
        assert src.fetch_day_minutes("IX0001") == {"0901": 100_000}

    def test_bad_time_value_skipped_not_raised(self) -> None:
        """Time 非數字 → 只計入 skipped(不得因共用 _taipei_minute_key 而外漏 ValueError)。

        ⚠ **這條測不到 skipped 路徑**(2026-08-03 收尾 review TC-4 實測):`"bad"` 經
        `zfill(6)` 變成 `"000bad"`,前兩碼是 `"00"` → `int()` 不炸 → 走的是**域外靜默**
        丟棄(key `"080b"` 不在 0901–1330)。名稱與 docstring 描述的路徑實際沒被走到。
        真正踩到 skipped 的輸入見下一條 `test_unparsable_time_counted_as_skipped`。
        """
        rows = [self._row("10100", "100", "1"), self._row("bad", "100", "2")]
        pages = {"0": rows, "2": []}

        def handler(obj: dict) -> bytes:
            if obj["Request"] == "GETHISDATA":
                qi = obj["Param"]["QryIndex"]
                return (
                    "1K:" + json.dumps({"Success": "OK", "HisData": pages.get(qi, [])}) + "\0"
                ).encode()
            return ok()

        src = StockQuoteSource(
            api=FakeApi(handler), session="s1", trade_date="2026-07-28", poll_wait_secs=0.0
        )
        assert src.fetch_day_minutes("IX0001") == {"0901": 100_000}

    def test_unparsable_time_counted_as_skipped(self, caplog: pytest.LogCaptureFixture) -> None:
        """真正解析不了的 Time → 計入 skipped 並發 warning;域外列不計。

        回傳值分不出「壞列」與「域外列」—— 兩者都只是沒進 dict。skipped 計數的 warning
        是唯一的診斷訊號(壞列代表資料源格式有異、域外列是正常的日內過濾),兩者混為
        一談會讓「TC4 換欄位格式」這種事完全靜默。
        """
        rows = [
            self._row("10100", "100", "1"),
            self._row("xx0100", "100", "2"),  # 前兩碼非數字 → int() 炸 → skipped
            self._row("60000", "103", "3"),  # 14:00 台北,域外 → 靜默丟棄,不計 skipped
        ]
        pages = {"0": rows, "3": []}

        def handler(obj: dict) -> bytes:
            if obj["Request"] == "GETHISDATA":
                qi = obj["Param"]["QryIndex"]
                return (
                    "1K:" + json.dumps({"Success": "OK", "HisData": pages.get(qi, [])}) + "\0"
                ).encode()
            return ok()

        src = StockQuoteSource(
            api=FakeApi(handler), session="s1", trade_date="2026-07-28", poll_wait_secs=0.0
        )
        with caplog.at_level(logging.WARNING, logger="copycat.live.stock_source"):
            assert src.fetch_day_minutes("IX0001") == {"0901": 100_000}
        assert "1K minutes 解析略過 1/3 列" in caplog.text  # 3 列中恰 1 列壞,域外那列不算

    def test_zmq_error_normalized(self) -> None:
        import zmq

        def handler(obj: dict) -> bytes:
            raise zmq.ZMQError()

        src = StockQuoteSource(
            api=FakeApi(handler), session="s1", trade_date="2026-07-28", poll_wait_secs=0.0
        )
        try:
            src.fetch_day_minutes("IX0001")
        except ConnectionError:
            pass
        else:
            raise AssertionError("必須正規化為 ConnectionError")


class TestRawDispatch:
    def test_realtime_quote_dispatched(self) -> None:
        src = StockQuoteSource(api=FakeApi(lambda o: ok()), session="s1", trade_date="2026-07-21")
        got: list[dict] = []
        src.set_on_message(got.append)
        raw = "REALTIME:" + json.dumps(
            {"DataType": "REALTIME", "Quote": {"Symbol": "TC.S.TWS.2330", "Security": "2330"}}
        )
        src.handle_raw(raw)
        assert got == [{"Symbol": "TC.S.TWS.2330", "Security": "2330"}]

    def test_ping_ignored(self) -> None:
        src = StockQuoteSource(api=FakeApi(lambda o: ok()), session="s1", trade_date="2026-07-21")
        got: list[dict] = []
        src.set_on_message(got.append)
        src.handle_raw("PING:" + json.dumps({"DataType": "PING"}))
        assert got == []


class TestNoDataHealthCheck:
    def test_no_push_within_deadline_flags_no_data(self) -> None:
        src = StockQuoteSource(
            api=FakeApi(lambda o: ok()),
            session="s1",
            trade_date="2026-07-21",
            no_data_secs=0.01,
            in_trading_hours=lambda: True,
        )
        flagged: list[str] = []
        src.set_on_no_data(flagged.append)
        src.subscribe_symbol("2330")
        threading.Event().wait(0.1)
        assert flagged == ["2330"]

    def test_push_cancels_health_check(self) -> None:
        src = StockQuoteSource(
            api=FakeApi(lambda o: ok()),
            session="s1",
            trade_date="2026-07-21",
            no_data_secs=0.05,
            in_trading_hours=lambda: True,
        )
        flagged: list[str] = []
        src.set_on_no_data(flagged.append)
        src.subscribe_symbol("2330")
        src.handle_raw(
            "REALTIME:"
            + json.dumps(
                {"DataType": "REALTIME", "Quote": {"Symbol": "TC.S.TWS.2330", "Security": "2330"}}
            )
        )
        threading.Event().wait(0.1)
        assert flagged == []

    def test_health_check_disabled_outside_trading_hours(self) -> None:
        src = StockQuoteSource(
            api=FakeApi(lambda o: ok()),
            session="s1",
            trade_date="2026-07-21",
            no_data_secs=0.01,
            in_trading_hours=lambda: False,
        )
        flagged: list[str] = []
        src.set_on_no_data(flagged.append)
        src.subscribe_symbol("2330")
        threading.Event().wait(0.1)
        assert flagged == []
