"""FinMind 全市場取數層(market-overview R2 Task 5;`test_oi_levels` 同款)。

真打 FinMind 一律禁止:HTTP 層以 `breadth_fetch.urlopen` monkeypatch 攔下
(conftest 另把 FINMIND_TOKEN 中和,漏 patch 也不會流出去打真 API)。
"""

from __future__ import annotations

import email.message
import io
import json
import logging
import urllib.error
import urllib.parse
from datetime import date as _date
from typing import Any

import pytest

import copycat.server.breadth_fetch as bf

_TODAY = _date(2026, 8, 5)


class FakeResp:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> FakeResp:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, *args: object) -> bytes:
        return self._body


class FakeHttp:
    """`urlopen` 替身:記錄每次請求,依序吐 responses(用完固定停在最後一項)。

    元素是 Exception 就 raise、bytes 則原樣當 body(非 JSON 路徑)、dict 走 JSON。
    """

    def __init__(self, *responses: dict | bytes | Exception) -> None:
        self._responses: list[dict | bytes | Exception] = list(responses)
        self.urls: list[str] = []
        self.headers: list[dict[str, str]] = []
        self.timeouts: list[float] = []

    def __call__(self, req: Any, timeout: float = 0.0) -> FakeResp:
        self.urls.append(req.full_url)
        self.headers.append(dict(req.headers))
        self.timeouts.append(timeout)
        item = self._responses[min(len(self.urls) - 1, len(self._responses) - 1)]
        if isinstance(item, Exception):
            raise item
        if isinstance(item, bytes):
            return FakeResp(item)
        return FakeResp(json.dumps(item).encode("utf-8"))

    @property
    def calls(self) -> int:
        return len(self.urls)

    def query(self, i: int = 0) -> dict[str, list[str]]:
        return urllib.parse.parse_qs(urllib.parse.urlsplit(self.urls[i]).query)

    def path(self, i: int = 0) -> str:
        return urllib.parse.urlsplit(self.urls[i]).path


def _payload(rows: list[dict]) -> dict:
    return {"msg": "success", "status": 200, "data": rows}


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://api.finmindtrade.com/api/v4/data",
        code,
        "err",
        email.message.Message(),
        io.BytesIO(b""),
    )


def _snapshot_rows(n: int = 1) -> list[dict]:
    return [{"stock_id": f"{2330 + i}", "close": 100.0, "change_price": 1.0} for i in range(n)]


def _info_rows(n: int) -> list[dict]:
    return [
        {"industry_category": "半導體業", "stock_id": f"{1000 + i}", "stock_name": "X", "type": "twse"}
        for i in range(n)
    ]


def _eod_rows(n: int = 2) -> list[dict]:
    return [
        {"date": "2026-08-05", "stock_id": f"{2330 + i}", "close": 100.0, "spread": 1.0}
        for i in range(n)
    ]


# ---------- URL / header / timeout 契約 ----------


class TestRequestShape:
    def test_snapshot_has_no_query_and_bearer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """snapshot 是專屬 endpoint(非 /data),**無 query 參數**;Bearer 帶 token。"""
        http = FakeHttp(_payload(_snapshot_rows()))
        monkeypatch.setattr(bf, "urlopen", http)

        rows = bf.fetch_snapshot("tok")

        assert rows == _snapshot_rows()
        assert http.calls == 1
        assert http.path() == "/api/v4/taiwan_stock_tick_snapshot"
        assert http.query() == {}
        assert http.headers[0]["Authorization"] == "Bearer tok"
        assert http.timeouts[0] == 30.0

    def test_stock_info_dataset_query(self, monkeypatch: pytest.MonkeyPatch) -> None:
        http = FakeHttp(_payload(_info_rows(3000)))
        monkeypatch.setattr(bf, "urlopen", http)

        bf.fetch_stock_info("tok")

        assert http.path() == "/api/v4/data"
        assert http.query() == {"dataset": ["TaiwanStockInfo"]}
        assert http.headers[0]["Authorization"] == "Bearer tok"

    def test_daily_prices_single_day_query_and_long_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """單日全市場 EOD:start_date == end_date == 該日、無 data_id;**timeout 60s**。

        回應是 MB 級(全市場 ~3 萬列含權證),秒級輪詢用的 30s 會在正常日就逾時 ——
        而逾時的表現是 streak 整輪失敗、連板欄整天 null(design §3.3a R10)。
        """
        http = FakeHttp(_payload(_eod_rows()))
        monkeypatch.setattr(bf, "urlopen", http)

        rows = bf.fetch_daily_prices("tok", _TODAY)

        assert rows == _eod_rows()
        assert http.calls == 1
        assert http.path() == "/api/v4/data"
        assert http.query() == {
            "dataset": ["TaiwanStockPrice"],
            "start_date": ["2026-08-05"],
            "end_date": ["2026-08-05"],
        }
        assert http.headers[0]["Authorization"] == "Bearer tok"
        assert http.timeouts[0] == 60.0

    def test_other_fetchers_keep_default_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`timeout` 是 keyword-only 且**只有 EOD 帶 60**;秒級輪詢的三支維持 30s。"""
        http = FakeHttp(_payload(_snapshot_rows()))
        monkeypatch.setattr(bf, "urlopen", http)

        bf.fetch_snapshot("tok")
        bf.fetch_disposition("tok", _TODAY)

        assert http.timeouts == [30.0, 30.0]

    def test_daily_prices_402_marks_quota_and_does_not_retry(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """錯誤分類沿 `_get_rows`:402 → quota=True 不重試(引擎據此走長退避)。"""
        http = FakeHttp(_http_error(402))
        monkeypatch.setattr(bf, "urlopen", http)

        with pytest.raises(bf.BreadthFetchError) as exc:
            bf.fetch_daily_prices("tok", _TODAY)

        assert exc.value.quota is True
        assert http.calls == 1

    def test_daily_prices_empty_day_returns_empty_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """假日 = 合法的空 `data` 陣列(不是錯誤);「空 = 假日候選」的判定在引擎。"""
        http = FakeHttp(_payload([]))
        monkeypatch.setattr(bf, "urlopen", http)

        assert bf.fetch_daily_prices("tok", _TODAY) == []

    def test_disposition_range_query_param_names(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """參數名必為 start_date / end_date(oi_levels / neigui 同款;PLAN R6)。"""
        http = FakeHttp(_payload([]))
        monkeypatch.setattr(bf, "urlopen", http)

        bf.fetch_disposition("tok", _TODAY)

        q = http.query()
        assert q["dataset"] == ["TaiwanStockDispositionSecuritiesPeriod"]
        assert q["start_date"] == ["2026-06-06"]  # today − 60 日曆日
        assert q["end_date"] == ["2026-08-05"]
        assert set(q) == {"dataset", "start_date", "end_date"}
        assert http.headers[0]["Authorization"] == "Bearer tok"


# ---------- 錯誤分類 ----------


class TestErrorClassification:
    def test_402_marks_quota_and_does_not_retry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """配額用盡:重打只會燒更多且必然同樣失敗 → 一次就放棄,quota=True。"""
        http = FakeHttp(_http_error(402))
        monkeypatch.setattr(bf, "urlopen", http)

        with pytest.raises(bf.BreadthFetchError) as exc:
            bf.fetch_snapshot("tok")

        assert exc.value.quota is True
        assert http.calls == 1

    def test_timeout_retries_once_then_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SSL read timeout 以 TimeoutError 拋出,不包在 URLError(CLAUDE.md §8)。"""
        http = FakeHttp(TimeoutError("read timed out"), _payload(_snapshot_rows(2)))
        monkeypatch.setattr(bf, "urlopen", http)

        rows = bf.fetch_snapshot("tok")

        assert len(rows) == 2
        assert http.calls == 2

    def test_incomplete_read_retries_once_then_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """回應斷流的 `http.client.IncompleteRead` **不是 OSError 子類**,漏接會炸穿
        重試直接殺掉 caller(2026-09-02 盤前篩選 CLI 真環境實錄 —— MB 級全市場回應
        被截斷,4.5MB 讀到一半斷線)。"""
        import http.client as _hc

        http = FakeHttp(_hc.IncompleteRead(b"x" * 10, 20), _payload(_snapshot_rows(2)))
        monkeypatch.setattr(bf, "urlopen", http)

        rows = bf.fetch_snapshot("tok")

        assert len(rows) == 2
        assert http.calls == 2

    def test_non_json_retries_once_then_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """配額燒乾時 FinMind 會回非 JSON 內容 —— 與連線失敗同樣可重試。"""
        http = FakeHttp(b"<html>oops</html>", _payload(_snapshot_rows()))
        monkeypatch.setattr(bf, "urlopen", http)

        assert bf.fetch_snapshot("tok") == _snapshot_rows()
        assert http.calls == 2

    def test_both_attempts_fail_raises_without_quota(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        http = FakeHttp(urllib.error.URLError("down"))
        monkeypatch.setattr(bf, "urlopen", http)

        with pytest.raises(bf.BreadthFetchError) as exc:
            bf.fetch_disposition("tok", _TODAY)

        assert exc.value.quota is False
        assert http.calls == 2

    def test_http_error_other_than_402_retries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        http = FakeHttp(_http_error(500), _payload(_info_rows(3000)))
        monkeypatch.setattr(bf, "urlopen", http)

        assert len(bf.fetch_stock_info("tok")) == 3000
        assert http.calls == 2

    def test_missing_data_array_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        http = FakeHttp({"msg": "no data", "status": 200})
        monkeypatch.setattr(bf, "urlopen", http)

        with pytest.raises(bf.BreadthFetchError) as exc:
            bf.fetch_snapshot("tok")

        assert exc.value.quota is False


# ---------- row 數觀測 ----------


class TestStockInfoRowCountLog:
    def test_normal_row_count_logs_info(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(bf, "urlopen", FakeHttp(_payload(_info_rows(4300))))
        with caplog.at_level(logging.INFO, logger=bf.__name__):
            bf.fetch_stock_info("tok")

        recs = [r for r in caplog.records if "4300" in r.getMessage()]
        assert recs and all(r.levelno == logging.INFO for r in recs)

    def test_short_row_count_logs_warning(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """上游分頁截斷會讓 TaiwanStockInfo 悄悄少一半 —— 少了就沒有人知道(升 warning)。"""
        monkeypatch.setattr(bf, "urlopen", FakeHttp(_payload(_info_rows(2999))))
        with caplog.at_level(logging.INFO, logger=bf.__name__):
            bf.fetch_stock_info("tok")

        recs = [r for r in caplog.records if "2999" in r.getMessage()]
        assert recs and any(r.levelno == logging.WARNING for r in recs)
