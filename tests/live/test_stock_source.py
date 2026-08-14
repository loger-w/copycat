from __future__ import annotations

import json
import logging
import threading
from typing import Callable

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

    def test_contract_key_maps_to_month_leaf(self) -> None:
        # SC-3:三段形 `F:<prod>:<ym>` = 使用者選定的月契約(HOT 兩段形是期現對照腿)
        assert stock_symbol("F:CDF:202609") == "TC.F.TWF.CDF.202609"

    def test_symbol_of_is_the_same_single_definition(self) -> None:
        """R2-2:engine 的 `_symbol_to_key` 只能經 `symbol_of` 取 symbol。

        engine 自組第二份對映的失效樣態是「兩邊各自演化」—— 路由表的鍵與真正送出去的
        SUBQUOTE symbol 不同字,推播因此永遠 map miss(而 TC4 對訂閱照回 OK)。
        """
        src = StockQuoteSource(api=FakeApi(lambda o: ok()), session="s1", trade_date="2026-07-21")
        for key in ("2330", "F:CDF", "F:CDF:202609"):
            assert src.symbol_of(key) == stock_symbol(key)

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


def _k1_pager(
    pages: dict[str, list[dict]], sent: list[dict] | None = None
) -> Callable[[dict], bytes]:
    """1K GETHISDATA 分頁替身(QryIndex → rows;其餘請求回 OK)。"""

    def handler(obj: dict) -> bytes:
        if sent is not None:
            sent.append(obj)
        if obj["Request"] == "GETHISDATA":
            qi = obj["Param"]["QryIndex"]
            body = json.dumps({"Success": "OK", "HisData": pages.get(qi, [])})
            return ("1K:" + body + "\0").encode()
        return ok()

    return handler


def _minutes_src(handler: Callable[[dict], bytes]) -> StockQuoteSource:
    return StockQuoteSource(
        api=FakeApi(handler), session="s1", trade_date="2026-07-28", poll_wait_secs=0.0
    )


class TestFetchDayMinutesWindowVariant:
    """SC-4:window variant = 逃出「毒化 history 訂閱」的維度(repro 實證:換窗口字串
    或換 session 才逃得掉,重送 SubHistory 逃不掉)。start 不變,只推 end hour。"""

    def _end_time_for(self, variant: int) -> list[str]:
        sent: list[dict] = []
        src = _minutes_src(_k1_pager({}, sent))
        src.fetch_day_minutes("IX0001", window_variant=variant)
        hist = [o for o in sent if o["Request"] in ("SUBQUOTE", "GETHISDATA")]
        assert [o["Param"]["StartTime"] for o in hist] == ["2026072800"] * len(hist)
        return [o["Param"]["EndTime"] for o in hist]

    def test_variant_zero_keeps_the_current_window(self) -> None:
        assert self._end_time_for(0) == ["2026072806", "2026072806"]

    def test_variant_extends_end_hour(self) -> None:
        assert self._end_time_for(1) == ["2026072807", "2026072807"]

    def test_variant_capped_at_23(self) -> None:
        assert self._end_time_for(20) == ["2026072823", "2026072823"]


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


class TestContractKeySubscription:
    """SC-3:三段形合約鍵沿現貨那條路(只換 symbol + 空試撮窗)。"""

    @staticmethod
    def _src(handler, **kw) -> StockQuoteSource:
        return StockQuoteSource(api=FakeApi(handler), session="s1", trade_date="2026-07-21", **kw)

    def test_subscribe_uses_the_month_leaf_symbol(self) -> None:
        sent: list[dict] = []

        def handler(obj: dict) -> bytes:
            sent.append(obj)
            return ok()

        self._src(handler).subscribe_symbol("F:CDF:202609")
        sub = next(o for o in sent if o["Request"] == "SUBQUOTE")
        assert sub["Param"]["Symbol"] == "TC.F.TWF.CDF.202609"
        # 窗沿個股日盤窗(UTC 00–06 涵蓋期貨日盤 08:45–13:45,design SC-3 刻意選擇)
        assert sub["Param"]["StartTime"] == "2026072100"
        assert sub["Param"]["EndTime"] == "2026072106"

    def test_backfill_uses_the_leaf_symbol_and_no_trial_window(self) -> None:
        """回補走既有 TICKS 路徑(D4);08:50 的成交對期貨**不是**試撮。

        沿用個股試撮窗的話,`StockDayState.ingest` 會在 dedup 前把 08:45–09:00 全部
        短路 —— 切一次檔(`apply_backfill` 先 reset 再重放)開盤那段就永久消失。
        """
        sent: list[dict] = []
        row = {
            "Date": "20260721",
            "FilledTime": "005000",
            "TradeQuantity": "3",
            "TradeVolume": "3",
            "TradingPrice": "2400",
            "PreciseTime": "005000000000",
            "QryIndex": "1",
        }
        pages = {"0": [row], "1": []}

        def handler(obj: dict) -> bytes:
            sent.append(obj)
            if obj["Request"] == "GETHISDATA":
                qi = obj["Param"]["QryIndex"]
                return (
                    "TICKS:" + json.dumps({"Success": "OK", "HisData": pages.get(qi, [])}) + "\0"
                ).encode()
            return ok()

        ticks = self._src(handler, poll_wait_secs=0.0).backfill("F:CDF:202609")
        assert {o["Param"]["Symbol"] for o in sent} == {"TC.F.TWF.CDF.202609"}
        assert len(ticks) == 1
        assert ticks[0].time == "08:50:00.000"
        assert ticks[0].is_trial is False

    def test_spot_backfill_still_marks_the_trial_window(self) -> None:
        row = {
            "Date": "20260721",
            "FilledTime": "005000",
            "TradeQuantity": "3",
            "TradeVolume": "3",
            "TradingPrice": "2400",
            "PreciseTime": "005000000000",
            "QryIndex": "1",
        }
        pages = {"0": [row], "1": []}

        def handler(obj: dict) -> bytes:
            if obj["Request"] == "GETHISDATA":
                qi = obj["Param"]["QryIndex"]
                return (
                    "TICKS:" + json.dumps({"Success": "OK", "HisData": pages.get(qi, [])}) + "\0"
                ).encode()
            return ok()

        ticks = self._src(handler, poll_wait_secs=0.0).backfill("2330")
        assert ticks[0].is_trial is True


class TestHealthCheckKeyedBySymbol:
    """D8/R2-3:`_seen` 以 **symbol** 記;timer 只掛現貨與三段形合約鍵。"""

    @staticmethod
    def _src(**kw) -> StockQuoteSource:
        return StockQuoteSource(
            api=FakeApi(lambda o: ok()),
            session="s1",
            trade_date="2026-07-21",
            in_trading_hours=lambda: True,
            **kw,
        )

    @staticmethod
    def _push(src: StockQuoteSource, symbol: str, security: str) -> None:
        src.handle_raw(
            "REALTIME:"
            + json.dumps(
                {"DataType": "REALTIME", "Quote": {"Symbol": symbol, "Security": security}}
            )
        )

    def test_contract_key_with_no_push_is_flagged_with_the_key(self) -> None:
        src = self._src(no_data_secs=0.01)
        flagged: list[str] = []
        src.set_on_no_data(flagged.append)
        src.subscribe_symbol("F:CDF:202609")
        threading.Event().wait(0.1)
        assert flagged == ["F:CDF:202609"]  # 回呼傳 key(engine 的 `_no_data` 以 key 記)

    def test_contract_push_cancels_its_own_health_check(self) -> None:
        src = self._src(no_data_secs=0.05)
        flagged: list[str] = []
        src.set_on_no_data(flagged.append)
        src.subscribe_symbol("F:CDF:202609")
        # 個股期推播的 `Security` 是產品碼 / 股號(未實證),以 Security 為鍵時
        # 這一則對不上 "F:CDF:202609" → 健檢誤判 no_data
        self._push(src, "TC.F.TWF.CDF.202609", "CDF")
        threading.Event().wait(0.15)
        assert flagged == []

    def test_contract_push_does_not_cancel_the_spot_health_check(self) -> None:
        """同一個 `Security` 可能同時出現在現貨與合約推播上 —— 以 Security 為鍵時,
        期貨那一則會把現貨的健檢一起消掉(現貨真的零推播也不再有訊號)。"""
        src = self._src(no_data_secs=0.01)
        flagged: list[str] = []
        src.set_on_no_data(flagged.append)
        src.subscribe_symbol("2330")
        self._push(src, "TC.F.TWF.CDF.202609", "2330")
        threading.Event().wait(0.1)
        assert flagged == ["2330"]

    def test_hot_leg_has_no_health_check(self) -> None:
        """兩段形 HOT 腿維持現行排除(R2-3):放開會讓 `_handle_no_data` 廣播
        code="F:CDF" 的 watchlist_quote,與 D16(只收自選碼)直接打架。"""
        src = self._src(no_data_secs=0.01)
        flagged: list[str] = []
        src.set_on_no_data(flagged.append)
        src.subscribe_symbol("F:CDF")
        threading.Event().wait(0.1)
        assert flagged == []
