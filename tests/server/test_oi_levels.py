"""FinMind TXO OI 撐壓 service + endpoint(futures-allday SC-11;PLAN 後端 §7)。

真打 FinMind 一律禁止:HTTP 層以 `oi_levels.urlopen` monkeypatch 攔下(notify 同款),
route 層則把 service 換掉。列資料形狀取自 design §2 的 2026-08-05 實打樣本。
"""

from __future__ import annotations

import asyncio
import email.message
import io
import json
import logging
import time
import urllib.error
import urllib.parse
from datetime import date as _date
from datetime import timedelta
from pathlib import Path
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

#: 真實作的 restore point。**module import 期取**:conftest 的 autouse fixture 會在
#: 每條測試前把它換成 `lambda: {}`(FinMind 憑證中和),那之後就抓不到本尊了。
_REAL_DOTENV_VALUES = oi._dotenv_values


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
    """module 級快取跨測試殘留 = 下一條測試看到的是上一條的答案。

    `_dotenv_cache` 一併重置(review TC-5):它是**解析一次就黏住**的 module 級狀態,
    conftest 已把它設 None,這裡再顯式一次讓本檔的 .env 案例彼此不互相汙染
    (前一條測到的檔案內容會直接變成後一條的答案)。
    """
    monkeypatch.setattr(oi, "_cache", oi.OiLevelsCache())
    monkeypatch.setattr(oi, "_dotenv_cache", None)


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


class TestSingleFlight:
    """單飛鎖:同鍵並發只讓一條真的去打 FinMind(review TC-6)。

    鎖若失效,失效樣態不是紅色而是**配額被乘上並發數** —— 前端一次重新整理就可能同時
    發多發(query invalidate + 換 tab 重掛),而回應內容完全一樣,沒有任何跡象。
    """

    async def test_concurrent_same_key_makes_one_round_trip(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class SlowHttp(FakeHttp):
            """第一發在 worker thread 內卡住一下 —— 讓其餘 4 發**必定**在它回來之前
            進場(否則鎖有沒有生效會取決於執行緒排程的運氣)。"""

            def __call__(self, req: Any, timeout: float = 0.0) -> FakeResp:
                time.sleep(0.05)
                return super().__call__(req, timeout)

        http = SlowHttp(_payload([_row(strike=24000.0, cp="call", open_interest=5)]))
        monkeypatch.setattr(oi, "urlopen", http)

        got = await asyncio.gather(
            *(oi.fetch_oi_levels(_YM, token="tok", today=_TODAY) for _ in range(5))
        )

        assert http.calls == 1  # 5 發同鍵 → 1 次 HTTP 往返
        assert all(g == got[0] for g in got)
        assert got[0]["strikes"] == [{"strike": 24000, "call_oi": 5, "put_oi": 0}]


class TestFreshnessLog:
    """成功路徑的觀測(review LF-3):截斷 / 上游停更會讓 latest 靜默退化成舊日期。"""

    @staticmethod
    def _fetch_with_date(monkeypatch: pytest.MonkeyPatch, date: str) -> None:
        monkeypatch.setattr(
            oi,
            "urlopen",
            FakeHttp(_payload([_row(date=date, strike=24000.0, cp="call", open_interest=7)])),
        )

    async def test_fresh_latest_logs_info_only(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        self._fetch_with_date(monkeypatch, (_TODAY - timedelta(days=1)).isoformat())
        with caplog.at_level(logging.INFO, logger=oi.__name__):
            await oi.fetch_oi_levels(_YM, token="tok", today=_TODAY)
        records = [r for r in caplog.records if "oi-levels" in r.message]
        assert [r.levelno for r in records] == [logging.INFO]
        assert "1 rows" in records[0].getMessage()
        assert "1 strikes" in records[0].getMessage()

    async def test_threshold_day_is_still_info(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """邊界含在內(`> STALE_WARN_DAYS` 才吵):連假剛好落在門檻上不該每天報警。

        門檻**值**本身是可調參數,刻意不用字面量釘死;這裡鎖的是比較的方向與含端。
        """
        self._fetch_with_date(
            monkeypatch, (_TODAY - timedelta(days=oi.STALE_WARN_DAYS)).isoformat()
        )
        with caplog.at_level(logging.INFO, logger=oi.__name__):
            await oi.fetch_oi_levels(_YM, token="tok", today=_TODAY)
        assert [r.levelno for r in caplog.records if "oi-levels" in r.message] == [logging.INFO]

    async def test_stale_latest_warns_but_still_returns(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """> STALE_WARN_DAYS:升 warning,但資料照樣回(舊撐壓仍有用,只是要有人知道)。"""
        stale = (_TODAY - timedelta(days=oi.STALE_WARN_DAYS + 1)).isoformat()
        self._fetch_with_date(monkeypatch, stale)
        with caplog.at_level(logging.INFO, logger=oi.__name__):
            got = await oi.fetch_oi_levels(_YM, token="tok", today=_TODAY)
        records = [r for r in caplog.records if "oi-levels" in r.message]
        assert [r.levelno for r in records] == [logging.WARNING]
        assert got["date"] == stale
        assert got["strikes"] == [{"strike": 24000, "call_oi": 7, "put_oi": 0}]


class TestResolveToken:
    """token 解析三條語意(review TC-5)。server 不載 dotenv:
    `FINMIND_TOKEN in os.environ` 即用(含空字串 = 未設,可壓制 .env)→ 否則 repo root .env。

    conftest 的 autouse fixture 已把 `_dotenv_values` 中和成 `lambda: {}`,要驗 .env
    行為的案例自行推回真實作(同 tests/capital/test_factory.py 的 `_REAL_DOTENV_VALUES`)。
    """

    def test_env_value_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FINMIND_TOKEN", "  tok-env  ")
        assert oi.resolve_token() == "tok-env"  # 兩端空白剝掉

    def test_empty_env_suppresses_dotenv(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """`set FINMIND_TOKEN=` 是明確的「這台不要打 FinMind」,不得被檔案值復活。"""
        monkeypatch.setattr(oi, "_dotenv_values", _REAL_DOTENV_VALUES)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("FINMIND_TOKEN=tok-file\n", encoding="utf-8")
        monkeypatch.setenv("FINMIND_TOKEN", "")
        assert oi.resolve_token() is None

    def test_dotenv_fallback_reads_bom_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """utf-8-sig:Windows 存的 .env 帶 BOM 會讓**首 key** 靜默失效(CLAUDE.md §8
        真踩過)→ 治具刻意把 FINMIND_TOKEN 放第一行。"""
        monkeypatch.setattr(oi, "_dotenv_values", _REAL_DOTENV_VALUES)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("FINMIND_TOKEN=tok-file\nOTHER=x\n", encoding="utf-8-sig")
        monkeypatch.delenv("FINMIND_TOKEN", raising=False)
        assert oi.resolve_token() == "tok-file"


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
