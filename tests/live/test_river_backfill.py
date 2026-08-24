"""1K 當日回補(SC-3/SC-4):分頁收割、首頁未備妥回空、兩個 source 的窗與 symbol。"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import pytest

from copycat.live import river_backfill as river_backfill_mod
from copycat.live.corr_source import CorrQuoteSource
from copycat.live.futures_source import FuturesQuoteSource
from copycat.live.tc4 import HistoryTimeoutError
from tests.helpers.tc4_fakes import FakeApi, ok

#: **凍結**的回補窗(TQ-5):治具與實作若共用 `all_day_utc_window()`,Date 閘就是拿
#: 自己的答案跟自己比 —— 把閘改成 `row["Date"] != all_day_utc_window()[0][:8]` 之外的
#: 任何等價式(甚至整條拆掉再用同一個函式重算)都照樣綠。窗釘死 + Date 寫死字面值,
#: 比對的兩端才真的獨立。
_WINDOW = ("2026073000", "2026073023")
_UTC_DAY = "20260730"


@pytest.fixture(autouse=True)
def _frozen_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """收割器看到的窗一律 `_WINDOW`(牆鐘無關 → 跨午夜跑測試也不會漂)。"""
    monkeypatch.setattr(river_backfill_mod, "all_day_utc_window", lambda: _WINDOW)


def _his(rows: list[dict]) -> bytes:
    """GETHISDATA 回應帶 "<type>:" 前綴(tc4._get_history strip_prefix 語意)。"""
    return ("1K:" + json.dumps({"Success": "OK", "HisData": rows}) + "\0").encode()


def _row(qry: int, time_utc: str, close: str, date: str | None = None) -> dict:
    """`Date` 預設 = 窗口日的**字面值**(`_UTC_DAY`),不從實作那邊算回來。"""
    return {
        "Date": date if date is not None else _UTC_DAY,
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
        assert (sub["Param"]["StartTime"], sub["Param"]["EndTime"]) == _WINDOW

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

    def test_all_rows_dropped_raises_history_timeout(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """rows 非空但 minutes 全空 = 毒化訂閱簽名 —— 沿 `stock_source` 的固定字串。

        **該變**(N092,舊契約是「warning + 回空」):「首頁非空即 break」的 ready-check
        擋不住凍結 stub,break 出來的是一列假資料而 `timed_out` 為 False → 呼叫端讀成
        「這條腿今天沒有 1K」整天不再回補。凍結 stub 的語意是「現在取不到,不是沒有」
        = `HistoryTimeoutError`,corr 的逾時重補階梯因此接得到手。
        """

        def handler(obj: dict) -> bytes:
            if obj["Request"] != "GETHISDATA":
                return ok()
            qi = obj["Param"]["QryIndex"]
            return _his([_row(1, "004600", "51666", date="20200101")] if qi == "0" else [])

        src = CorrQuoteSource(api=FakeApi(handler), session="s1", poll_wait_secs=0)
        with caplog.at_level(logging.WARNING), pytest.raises(HistoryTimeoutError) as excinfo:
            src.fetch_day_1k("TC.F.SGX.TWN.HOT")
        # 判準搬到例外訊息(review ST6:同一件事不印兩次 —— 呼叫端
        # `corr_engine._fetch_leg_minutes` 自己會記一行帶處置的 warning)
        assert "疑似凍結 stub" in str(excinfo.value)
        assert "疑似凍結 stub" not in caplog.text

    def test_unparsable_rows_do_not_claim_frozen_stub(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """全數列都**解析不了**(欄位缺漏 / 格式)≠ 凍結 stub。

        「rows 非空但 minutes 全空」對兩件事都成立,但處置差很遠:凍結 stub 要換窗口
        逃逸,欄位壞掉要看 TC4 是不是換了欄名。混報的代價是那句固定字串失去診斷力
        —— 它是這條路上唯一的 grep 判準。
        """

        def handler(obj: dict) -> bytes:
            if obj["Request"] != "GETHISDATA":
                return ok()
            qi = obj["Param"]["QryIndex"]
            row = _row(1, "004600", "51666")
            del row["Close"]  # Date 是窗口日、Time 正常,只有 Close 缺 → skipped
            return _his([row] if qi == "0" else [])

        src = CorrQuoteSource(api=FakeApi(handler), session="s1", poll_wait_secs=0)
        with caplog.at_level(logging.WARNING):
            assert src.fetch_day_1k("TC.F.SGX.TWN.HOT") == []
        assert "疑似凍結 stub" not in caplog.text

    def test_late_utc_row_of_the_window_day_is_kept(self) -> None:
        """UTC 16:30 = **台北次日 00:30**,但 `Date` 仍是窗口日 → 保留。

        Date 閘刻意是**純 UTC 比對**(窗本身就是 UTC 全天窗)。哪天有人「順手補上」
        台北換算,夜盤跨午夜那一段的每一列都會被判成隔天而整批丟掉 —— 江波圖夜盤
        後半段整段消失,而全鏈只有一行「丟棄 N 列」。
        """

        def handler(obj: dict) -> bytes:
            if obj["Request"] != "GETHISDATA":
                return ok()
            qi = obj["Param"]["QryIndex"]
            return _his([_row(1, "163000", "51680")] if qi == "0" else [])

        src = CorrQuoteSource(api=FakeApi(handler), session="s1", poll_wait_secs=0)
        # (16+8)%24 = 0 → 台北 00:30 → minute_end 30
        assert src.fetch_day_1k("TC.F.SGX.TWN.HOT") == [(30, 51_680_000)]

    def test_rows_without_date_still_reach_the_chart(self) -> None:
        """缺 `Date` 的列不被 Date 閘丟掉 —— 丟資料比放過凍結 stub 更壞(整條線消失)。"""

        def handler(obj: dict) -> bytes:
            if obj["Request"] != "GETHISDATA":
                return ok()
            qi = obj["Param"]["QryIndex"]
            row = _row(1, "004700", "51680")
            del row["Date"]
            return _his([row] if qi == "0" else [])

        src = CorrQuoteSource(api=FakeApi(handler), session="s1", poll_wait_secs=0)
        assert src.fetch_day_1k("TC.F.SGX.TWN.HOT") == [(527, 51_680_000)]


class TestFuturesSourceFetchDay1k:
    def test_product_maps_to_twf_hot_symbol(self) -> None:
        sent: list[dict] = []
        src = FuturesQuoteSource(api=FakeApi(_paging_handler(sent)), session="s1")

        minutes = src.fetch_day_1k("TXF")

        sub = next(o for o in sent if o["Request"] == "SUBQUOTE")
        assert sub["Param"]["Symbol"] == "TC.F.TWF.TXF.HOT"
        assert sub["Param"]["SubDataType"] == "1K"
        assert minutes[0] == (526, 51_666_000)
