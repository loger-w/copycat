"""FinMind TXO OI 撐壓 service + endpoint(futures-allday SC-11;PLAN 後端 §7)。

真打 FinMind 一律禁止:HTTP 層以 `oi_levels.urlopen` monkeypatch 攔下(notify 同款),
route 層則把 service 換掉。列資料形狀取自 design §2 的 2026-08-05 實打樣本。
"""

from __future__ import annotations

import email.message
import io
import json
import urllib.error
import urllib.parse
from datetime import date as _date
from typing import Any

import pytest
from fastapi.testclient import TestClient

import copycat.server.oi_levels as oi
from copycat.server.app import create_app
from tests.helpers.boot import BootedClient
from tests.helpers.fake_sources import FakeFuturesSource
from tests.helpers.fake_txo import FakeTxoSource

_TODAY = _date(2026, 8, 5)
_YM = "202608"
_EMPTY = {"date": None, "contract": None, "strikes": []}


def _row(
    *,
    date: str = "2026-08-04",
    contract: str = _YM,
    strike: float,
    cp: str,
    open_interest: int,
    session: str = "position",
) -> dict[str, Any]:
    """design §2 真樣本欄位形狀(欄位一個不少 —— 少了就驗不到解析只挑該挑的欄)。"""
    return {
        "date": date,
        "option_id": "TXO",
        "contract_date": contract,
        "strike_price": strike,
        "call_put": cp,
        "open": 0.0,
        "max": 0.0,
        "min": 0.0,
        "close": 0.0,
        "volume": 0,
        "settlement_price": 0.0,
        "open_interest": open_interest,
        "trading_session": session,
    }


class FakeResp:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> FakeResp:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, *args: object) -> bytes:
        return self._body


class FakeHttp:
    """`urlopen` 替身:記錄每次請求,依序吐 responses(用完固定停在最後一項)。

    元素是 Exception 就 raise —— retry / 402 不 retry 兩條路徑都靠這個表達。
    """

    def __init__(self, *responses: dict | Exception) -> None:
        self._responses: list[dict | Exception] = list(responses)
        self.urls: list[str] = []
        self.headers: list[dict[str, str]] = []

    def __call__(self, req: Any, timeout: float = 0.0) -> FakeResp:
        self.urls.append(req.full_url)
        self.headers.append(dict(req.headers))
        item = self._responses[min(len(self.urls) - 1, len(self._responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return FakeResp(item)

    @property
    def calls(self) -> int:
        return len(self.urls)

    def query(self, i: int = 0) -> dict[str, list[str]]:
        return urllib.parse.parse_qs(urllib.parse.urlsplit(self.urls[i]).query)


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


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """module 級快取跨測試殘留 = 下一條測試看到的是上一條的答案。"""
    monkeypatch.setattr(oi, "_cache", oi.OiLevelsCache())


# ---------- service:口徑與 pivot ----------


class TestFetchOiLevels:
    async def test_pivot_normal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """max(date) 那日 + 月契約 + position 列 → per-strike 升冪;缺對邊填 0。"""
        rows = [
            _row(strike=24000.0, cp="call", open_interest=1234),
            _row(strike=24000.0, cp="put", open_interest=999),
            _row(strike=23000.0, cp="call", open_interest=111),
            _row(date="2026-07-31", strike=24000.0, cp="call", open_interest=5),
        ]
        http = FakeHttp(_payload(rows))
        monkeypatch.setattr(oi, "urlopen", http)

        got = await oi.fetch_oi_levels(_YM, token="tok", today=_TODAY)

        assert got == {
            "date": "2026-08-04",
            "contract": _YM,
            "strikes": [
                {"strike": 23000, "call_oi": 111, "put_oi": 0},
                {"strike": 24000, "call_oi": 1234, "put_oi": 999},
            ],
        }

    async def test_range_query_and_bearer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """單次 range 查詢 today−10..today(D15:一次往返涵蓋連假)+ Bearer header。"""
        http = FakeHttp(_payload([_row(strike=24000.0, cp="call", open_interest=1)]))
        monkeypatch.setattr(oi, "urlopen", http)

        await oi.fetch_oi_levels(_YM, token="tok", today=_TODAY)

        q = http.query()
        assert q["dataset"] == ["TaiwanOptionDaily"]
        assert q["data_id"] == ["TXO"]
        assert q["start_date"] == ["2026-07-26"]
        assert q["end_date"] == ["2026-08-05"]
        assert http.headers[0]["Authorization"] == "Bearer tok"

    async def test_after_market_rows_filtered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OI 只在 position 列(after_market 的 OI 恆 0)→ 只有 after_market 即無資料。"""
        rows = [
            _row(strike=24000.0, cp="call", open_interest=777, session="after_market"),
            _row(strike=24000.0, cp="put", open_interest=666, session="after_market"),
        ]
        monkeypatch.setattr(oi, "urlopen", FakeHttp(_payload(rows)))

        assert await oi.fetch_oi_levels(_YM, token="tok", today=_TODAY) == _EMPTY

    async def test_after_market_not_mixed_into_position(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """同 strike 兩種 session 並存時,after_market 的 0 不可蓋掉 position 的真值。"""
        rows = [
            _row(strike=24000.0, cp="call", open_interest=1234),
            _row(strike=24000.0, cp="call", open_interest=0, session="after_market"),
        ]
        monkeypatch.setattr(oi, "urlopen", FakeHttp(_payload(rows)))

        got = await oi.fetch_oi_levels(_YM, token="tok", today=_TODAY)
        assert got["strikes"] == [{"strike": 24000, "call_oi": 1234, "put_oi": 0}]

    async def test_weekly_and_other_month_filtered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """contract_date 精確等值 → 週選 W / F 序列與他月自然排除。"""
        rows = [
            _row(contract="202608W1", strike=24500.0, cp="call", open_interest=888),
            _row(contract="202608W2", strike=24500.0, cp="put", open_interest=888),
            _row(contract="202608F1", strike=24500.0, cp="call", open_interest=888),
            _row(contract="202609", strike=26000.0, cp="call", open_interest=42),
        ]
        monkeypatch.setattr(oi, "urlopen", FakeHttp(_payload(rows)))

        assert await oi.fetch_oi_levels(_YM, token="tok", today=_TODAY) == _EMPTY

    async def test_token_missing_returns_empty_without_http(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        http = FakeHttp(_payload([]))
        monkeypatch.setattr(oi, "urlopen", http)

        assert await oi.fetch_oi_levels(_YM, token=None, today=_TODAY) == _EMPTY
        assert http.calls == 0

    async def test_402_not_retried_and_negative_cached(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """配額用盡:不 retry(重打只會燒更多)、負向快取讓第二次呼叫零往返。"""
        http = FakeHttp(_http_error(402))
        monkeypatch.setattr(oi, "urlopen", http)

        assert await oi.fetch_oi_levels(_YM, token="tok", today=_TODAY) == _EMPTY
        assert http.calls == 1
        assert await oi.fetch_oi_levels(_YM, token="tok", today=_TODAY) == _EMPTY
        assert http.calls == 1

    async def test_negative_cache_expires(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """負向快取不可永久 —— FinMind 恢復後要自癒。"""
        http = FakeHttp(
            _http_error(402), _payload([_row(strike=24000.0, cp="call", open_interest=7)])
        )
        monkeypatch.setattr(oi, "urlopen", http)
        clock = [1000.0]
        monkeypatch.setattr(oi, "_now", lambda: clock[0])

        assert await oi.fetch_oi_levels(_YM, token="tok", today=_TODAY) == _EMPTY
        clock[0] += oi.NEGATIVE_TTL_SECS + 1
        got = await oi.fetch_oi_levels(_YM, token="tok", today=_TODAY)

        assert http.calls == 2
        assert got["strikes"] == [{"strike": 24000, "call_oi": 7, "put_oi": 0}]

    async def test_positive_cache_hit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        http = FakeHttp(_payload([_row(strike=24000.0, cp="call", open_interest=1234)]))
        monkeypatch.setattr(oi, "urlopen", http)

        first = await oi.fetch_oi_levels(_YM, token="tok", today=_TODAY)
        second = await oi.fetch_oi_levels(_YM, token="tok", today=_TODAY)

        assert first == second
        assert http.calls == 1

    async def test_cache_key_includes_contract_and_day(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """換月 / 跨日各自換鍵 —— 共用一格會讓次月拿到本月的撐壓。"""
        http = FakeHttp(_payload([_row(strike=24000.0, cp="call", open_interest=1)]))
        monkeypatch.setattr(oi, "urlopen", http)

        await oi.fetch_oi_levels(_YM, token="tok", today=_TODAY)
        await oi.fetch_oi_levels("202609", token="tok", today=_TODAY)
        await oi.fetch_oi_levels(_YM, token="tok", today=_date(2026, 8, 6))

        assert http.calls == 3

    async def test_timeout_is_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SSL read timeout 以 TimeoutError 拋、不包在 URLError(CLAUDE.md §8)。"""
        http = FakeHttp(
            TimeoutError("read timed out"),
            _payload([_row(strike=24000.0, cp="call", open_interest=7)]),
        )
        monkeypatch.setattr(oi, "urlopen", http)

        got = await oi.fetch_oi_levels(_YM, token="tok", today=_TODAY)

        assert http.calls == 2
        assert got["strikes"] == [{"strike": 24000, "call_oi": 7, "put_oi": 0}]


# ---------- route:降級一律 200 空 shape(SC-11) ----------


class StubFutures:
    """只提供 route 用得到的那一格(resolved_contract);其餘引擎行為與本測試無關。"""

    def __init__(self, ym: str | None) -> None:
        self._ym = ym
        self.asked: list[str] = []

    def resolved_contract(self, product: str) -> str | None:
        self.asked.append(product)
        return self._ym


def _client(*, futures_source: FakeFuturesSource | None = None) -> TestClient:
    app = create_app(FakeTxoSource(), futures_source=futures_source, throttle_secs=0.01)
    return BootedClient(app, raise_server_exceptions=False)


class TestOiRoute:
    def test_resolved_contract_returns_strikes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[str, str | None]] = []

        async def fake_fetch(ym: str, *, token: str | None, today: _date) -> dict:
            calls.append((ym, token))
            return {
                "date": "2026-08-04",
                "contract": ym,
                "strikes": [{"strike": 24000, "call_oi": 1234, "put_oi": 999}],
            }

        monkeypatch.setattr(oi, "fetch_oi_levels", fake_fetch)
        monkeypatch.setattr(oi, "resolve_token", lambda: "tok")
        stub = StubFutures(_YM)
        with _client(futures_source=FakeFuturesSource()) as c:
            c.app.state.futures = stub  # type: ignore[union-attr]
            r = c.get("/api/futures/oi-levels")

        assert r.status_code == 200
        assert r.json() == {
            "date": "2026-08-04",
            "contract": _YM,
            "strikes": [{"strike": 24000, "call_oi": 1234, "put_oi": 999}],
        }
        assert calls == [(_YM, "tok")]
        assert stub.asked == ["TXF"]

    def test_unresolved_contract_returns_empty_shape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """契約未解析 → 200 空 shape(不是 503:前端把 OI 線當可有可無的疊圖)。"""

        async def boom(ym: str, *, token: str | None, today: _date) -> dict:
            raise AssertionError("契約未解析時不該打 FinMind")

        monkeypatch.setattr(oi, "fetch_oi_levels", boom)
        with _client(futures_source=FakeFuturesSource()) as c:
            c.app.state.futures = StubFutures(None)  # type: ignore[union-attr]
            r = c.get("/api/futures/oi-levels")

        assert r.status_code == 200
        assert r.json() == _EMPTY

    def test_futures_engine_absent_returns_empty_shape(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """引擎沒起來(state.futures is None)照樣 200 空 shape。"""

        async def boom(ym: str, *, token: str | None, today: _date) -> dict:
            raise AssertionError("引擎缺席時不該打 FinMind")

        monkeypatch.setattr(oi, "fetch_oi_levels", boom)
        with _client() as c:
            assert c.app.state.futures is None  # type: ignore[union-attr]
            r = c.get("/api/futures/oi-levels")

        assert r.status_code == 200
        assert r.json() == _EMPTY
