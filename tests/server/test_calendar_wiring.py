"""交易日曆在 app 層的佈線(mod/trading-calendar SC-2 / SC-6 / SC-7 / SC-13)。

四件事各自的失效樣態都是「畫面一片空而零錯誤訊號」,所以逐條釘住:

- **SC-2**:週六 / 假日冷啟動時 stock / index / hub / breadth 各自拿到哪一天
  (`TXO_BACKFILL_DATE` 對前三者最高優先、breadth 一律純日曆 —— KR-5)。
- **SC-6**:`GET /api/calendar` 是「這台今天在看哪一天」的唯一可視管道(含日曆是否載到)。
- **SC-7**:boot 後的 DK 雙向交叉檢查 —— 日曆過期 / 臨時休市各一句 WARNING,而**正常
  交易日盤前不得誤報**(這條偽陽性鎖是整組最重要的一條:每天早上都會走到)。
- **SC-13**:overlay 的基準日跟著顯示中的交易日走(cache 鍵同源)。

牆鐘取樣一律 monkeypatch `app_mod._today` / `_now` 這**兩個模組層函式**(app 內唯一的
兩個取樣點);`TXO_BACKFILL_DATE` 由 autouse fixture 清掉 —— 開發機 shell 留著它會讓
整檔斷言隨環境飄。
"""

from __future__ import annotations

import datetime as _dt
import logging
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from copycat.server import app as app_mod
from copycat.server.app import BreadthFetchers, create_app
from copycat.trading_calendar import TradingCalendar, load_trading_calendar
from tests.helpers.boot import BootedClient
from tests.helpers.fake_sources import FakeIndexSource, FakeStockSource, dbar
from tests.helpers.fake_txo import FakeTxoSource

#: 2026-08-15 = 週六;前一交易日 = 08-14(週五)。連假 / 國定假日的推導由
#: `tests/test_trading_calendar.py` 覆蓋,這裡只驗「app 有沒有把它接上去」。
SAT = _dt.date(2026, 8, 15)
FRI = _dt.date(2026, 8, 14)
FRI_ISO = "2026-08-14"

#: 個股 overlay 的日 K 治具:08-11 ~ 08-14(≥5 根才有 ma5,20 根以下 ma20 為 null)。
_DAILY = [
    {"date": f"2026-08-{d:02d}", "high": 103_000, "low": 100_000, "close": 100_000 + d * 100}
    for d in range(11, 15)
]


@pytest.fixture(autouse=True)
def _no_backfill_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TXO_BACKFILL_DATE", raising=False)


def _freeze(
    monkeypatch: pytest.MonkeyPatch, today: _dt.date, *, at: _dt.time = _dt.time(9, 30)
) -> None:
    """牆鐘的兩個取樣點一起釘 —— `_now` 只釘一半的話 SC-7 的 14:00 門檻會隨實跑時刻飄。"""
    monkeypatch.setattr(app_mod, "_today", lambda: today)
    monkeypatch.setattr(app_mod, "_now", lambda: _dt.datetime.combine(today, at))


class RecordingStockSource(FakeStockSource):
    """記錄 `set_trade_date` 與日 K 取數次數。

    共用 fake 的兩支都是靜默 no-op —— 而「trade_date 有沒有真的傳到 source 日窗」正是
    本輪要驗的那件事(engine 屬性對了但 source 沒收到 = 回補仍打錯日,畫面照樣空)。
    """

    def __init__(self) -> None:
        super().__init__()
        self.trade_dates: list[str] = []
        self.daily_calls = 0

    def set_trade_date(self, trade_date: str) -> None:
        self.trade_dates.append(trade_date)

    def fetch_daily_bars(self, code: str, n: int = 25) -> list:
        self.daily_calls += 1
        return super().fetch_daily_bars(code, n)


class DayKeyedIndexSource(FakeIndexSource):
    """`fetch_day_minutes` 依**最後一次 `set_trade_date`** 回不同資料。

    共用 fake 恆回同一份 → 「日窗切對了沒」驗不出來(trade_date 標成假日、回補仍回
    週五資料的假綠)。這裡讓 08-14 那份才有分鐘,冷啟動後分時非空 = 日窗真的對上。
    """

    def __init__(self, by_date: dict[str, dict[str, int]]) -> None:
        super().__init__()
        self._by_date = {k: dict(v) for k, v in by_date.items()}

    def fetch_day_minutes(self, code: str, *, window_variant: int = 0) -> dict[str, int]:
        super().fetch_day_minutes(code, window_variant=window_variant)  # 計數 / variant 記錄
        current = self.trade_dates[-1] if self.trade_dates else ""
        return dict(self._by_date.get(current, {}))


class RaisingHistoryIndexSource(FakeIndexSource):
    """日 K 取數拋非 ConnectionError —— SC-7 的「交叉檢查自己炸掉」路徑。

    ConnectionError 會被 `IndexEngine.bars_range` 收成空清單(那是另一條:bars 空),
    要驗自吞傘就必須是它接不住的例外。
    """

    def fetch_bars_range_tagged(
        self, code: str, tf: str, start: str, end: str
    ) -> tuple[list[dict], str, str]:
        raise RuntimeError("history boom")


class _CrosscheckBomb(BaseException):
    """刻意不是 `Exception` 子類 —— 只有這種例外能同時穿過 `_calendar_crosscheck`
    自吞的傘與關機路徑的 `except Exception`,正是 C2 要釘的那一格。"""


class BaseExcHistoryIndexSource(FakeIndexSource):
    """日 K probe 拋 BaseException:交叉檢查 task 以例外結束 → 走關機的 await。"""

    def fetch_bars_range_tagged(
        self, code: str, tf: str, start: str, end: str
    ) -> tuple[list[dict], str, str]:
        raise _CrosscheckBomb("crosscheck boom")


def _empty_fetchers() -> BreadthFetchers:
    """家數帶取數四元組:全空(本檔只驗 today_fn 佈線,不驗家數算術)。"""
    return (
        lambda _token: [],
        lambda _token: [],
        lambda _token, _today: [],
        None,
    )


def _app(
    tmp_path: Path,
    *,
    cal: TradingCalendar | None = None,
    stock: object | None = None,
    index: object | None = None,
    breadth: object | None = None,
) -> FastAPI:
    return create_app(
        FakeTxoSource(),
        stock_source=stock,
        index_source=index,
        index_mis_fetch=lambda: None,
        breadth_fetchers=breadth,
        breadth_data_dir=tmp_path / "market",
        # 非 prod create_app 一律隔離自選檔路徑(XR-3 紀律:hub 恆建,落點跟著它走)
        stock_watchlist_path=tmp_path / "watchlist.json",
        trading_calendar=cal,
        throttle_secs=0.01,
    )


def _client(app: FastAPI) -> TestClient:
    return BootedClient(app, raise_server_exceptions=False)


def _wait_crosscheck(app: FastAPI, timeout: float = 5.0) -> None:
    """等到 SC-7 的背景交叉檢查結束。

    它刻意**不擋 boot 鏈**(probe 要打 TC4 歷史)→ `boot_done` 不代表它跑完,不等的話
    「無 WARNING」那幾條會變成「還沒跑到」的假綠。
    """
    deadline = time.monotonic() + timeout
    while True:
        task = getattr(app.state, "calendar_crosscheck", None)
        if task is not None and task.done():
            return
        if time.monotonic() > deadline:
            raise AssertionError(f"交叉檢查未在 {timeout}s 內結束:{task}")
        time.sleep(0.01)


def _app_warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == "copycat.server.app" and r.levelno >= logging.WARNING
    ]


class TestEngineTradeDate:
    """SC-2:引擎冷啟動拿到的日別。"""

    def test_stock_and_index_use_last_trading_day_on_saturday(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _freeze(monkeypatch, SAT)
        stock = RecordingStockSource()
        index = DayKeyedIndexSource({FRI_ISO: {"0901": 43_000_000}})
        app = _app(tmp_path, cal=load_trading_calendar(), stock=stock, index=index)
        with _client(app) as c:
            assert app.state.stock is not None
            assert app.state.stock.trade_date == FRI_ISO
            # engine 屬性對了但 source 日窗沒切 = 回補照樣打週六(畫面空、零錯誤訊號)
            assert stock.trade_dates == [FRI_ISO]
            body = c.get("/api/index/state").json()
            assert body["trade_date"] == FRI_ISO
            assert body["twse"]["minutes"] == {"0901": 43_000_000}, "日窗切對才拿得到週五那份"

    def test_backfill_env_beats_calendar_for_stock_and_index(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """W2:手動 `TXO_BACKFILL_DATE` 仍是最高優先(日曆不得蓋掉 ops 通道)。"""
        _freeze(monkeypatch, SAT)
        monkeypatch.setenv("TXO_BACKFILL_DATE", "2026-08-10")
        stock = RecordingStockSource()
        index = DayKeyedIndexSource({"2026-08-10": {"0902": 1}})
        app = _app(tmp_path, cal=load_trading_calendar(), stock=stock, index=index)
        with _client(app) as c:
            assert app.state.stock is not None
            assert app.state.stock.trade_date == "2026-08-10"
            assert stock.trade_dates == ["2026-08-10"]
            assert c.get("/api/index/state").json()["trade_date"] == "2026-08-10"

    def test_hub_fallback_uses_calendar_without_stock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """stock 缺席時 hub 的日別 fallback(jsonl 檔名 / today 端點的尺)也吃日曆。"""
        _freeze(monkeypatch, SAT)
        app = _app(tmp_path, cal=load_trading_calendar())
        with _client(app):
            hub = app.state.signal_hub
            assert hub is not None
            assert hub._trade_date_fn() == FRI_ISO
            # 每次呼叫求值(非 boot 當下快照):env 後設也要立刻反映
            monkeypatch.setenv("TXO_BACKFILL_DATE", "2026-08-10")
            assert hub._trade_date_fn() == "2026-08-10"

    def test_breadth_today_fn_is_last_trading_day_and_ignores_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """KR-5:breadth 一律純日曆 —— env 是 TXO 回補通道,不擴張到 FinMind 面。"""
        _freeze(monkeypatch, SAT)
        monkeypatch.setenv("TXO_BACKFILL_DATE", "2026-08-10")
        app = _app(tmp_path, cal=load_trading_calendar(), breadth=_empty_fetchers())
        with _client(app):
            breadth = app.state.breadth
            assert breadth is not None
            assert breadth._today_fn() == FRI


class TestCalendarRoute:
    """SC-6:`GET /api/calendar`。"""

    def test_payload_with_calendar_on_saturday(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _freeze(monkeypatch, SAT)
        app = _app(tmp_path, cal=load_trading_calendar())
        with _client(app) as c:
            body = c.get("/api/calendar").json()
        assert set(body) == {
            "today",
            "trade_date",
            "calendar_trade_date",
            "backfill_env",
            "holidays",
            "years_loaded",
            "calendar_loaded",
        }
        assert body["today"] == "2026-08-15"
        assert body["trade_date"] == FRI_ISO
        assert body["calendar_trade_date"] == FRI_ISO
        assert body["backfill_env"] is None
        assert body["calendar_loaded"] is True
        assert body["years_loaded"] == [2026]
        assert len(body["holidays"]) == 18
        assert "2026-10-09" in body["holidays"]

    def test_env_shifts_trade_date_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`trade_date` = 引擎實際採用;`calendar_trade_date` = 純日曆(breadth 那份)。

        兩者分開才看得出 KR-5 的日別不一致 —— 合成一個欄位就沒有任何管道分辨。
        """
        _freeze(monkeypatch, SAT)
        monkeypatch.setenv("TXO_BACKFILL_DATE", "2026-08-10")
        app = _app(tmp_path, cal=load_trading_calendar())
        with _client(app) as c:
            body = c.get("/api/calendar").json()
        assert body["trade_date"] == "2026-08-10"
        assert body["calendar_trade_date"] == FRI_ISO
        assert body["backfill_env"] == "2026-08-10"

    def test_without_calendar_degrades_to_wall_clock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """W6:預設(測試 / 未注入)= 牆鐘,且看得出來日曆沒載到。"""
        _freeze(monkeypatch, SAT)
        app = _app(tmp_path)
        with _client(app) as c:
            body = c.get("/api/calendar").json()
        assert body["calendar_loaded"] is False
        assert body["holidays"] == [] and body["years_loaded"] == []
        assert body["today"] == "2026-08-15"
        assert body["trade_date"] == "2026-08-15"
        assert body["calendar_trade_date"] == "2026-08-15"

    def test_health_payload_unchanged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """W7:日曆是新端點的事,`/api/health` 的「只答建置身分」契約不得被沾到。"""
        _freeze(monkeypatch, SAT)
        app = _app(tmp_path, cal=load_trading_calendar())
        with _client(app) as c:
            body = c.get("/api/health").json()
        assert set(body) == set(app.state.build.as_dict())
        assert "trade_date" not in body and "holidays" not in body


class TestCrosscheck:
    """SC-7:boot 後的 DK 雙向交叉檢查(背景 task,自吞例外)。"""

    def test_dk_newer_than_calendar_warns_stale_calendar(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """日曆把真交易日標成假日 → DK 比日曆新 → 「可能過期」(KR-1 的唯一提示)。"""
        caplog.set_level(logging.INFO)
        _freeze(monkeypatch, FRI)
        wrong = TradingCalendar(
            holidays=frozenset({FRI}),
            extra_trading_days=frozenset(),
            years_loaded=frozenset({2026}),
        )
        index = FakeIndexSource(daily_bars=[dbar("2026-08-13", 1), dbar(FRI_ISO, 2)])
        app = _app(tmp_path, cal=wrong, index=index)
        with _client(app):
            _wait_crosscheck(app)
            warnings = _app_warnings(caplog)
        assert any("可能過期" in w and FRI_ISO in w for w in warnings), warnings

    def test_dk_older_than_expected_warns_unscheduled_close(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """最近交易日沒有 DK → 臨時休市(颱風假)提示改設 env / 更新日曆(KR-3)。"""
        caplog.set_level(logging.INFO)
        _freeze(monkeypatch, SAT)
        index = FakeIndexSource(daily_bars=[dbar("2026-08-11", 1), dbar("2026-08-12", 2)])
        app = _app(tmp_path, cal=load_trading_calendar(), index=index)
        with _client(app):
            _wait_crosscheck(app)
            warnings = _app_warnings(caplog)
        assert any("臨時休市" in w and FRI_ISO in w for w in warnings), warnings

    def test_probe_failure_never_takes_index_down(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """probe 拋 → 只留一句「略過」,index 照樣掛著(它只是一則 log,不是啟動條件)。"""
        caplog.set_level(logging.INFO)
        _freeze(monkeypatch, SAT)
        app = _app(tmp_path, cal=load_trading_calendar(), index=RaisingHistoryIndexSource())
        with _client(app) as c:
            _wait_crosscheck(app)
            assert app.state.index is not None
            assert c.get("/api/index/state").status_code == 200
            warnings = _app_warnings(caplog)
        assert any("交叉檢查失敗" in w for w in warnings), warnings
        assert not any("可能過期" in w or "臨時休市" in w for w in warnings), warnings

    def test_trading_day_pre_open_does_not_warn(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """偽陽性鎖:交易日盤前(今天的 DK 本來就還不存在)一句都不能報。

        期望日若用「含今天」的最近交易日,每天早上重啟都會誤報一次臨時休市 ——
        那種天天亮的 WARNING 三天內就會被當雜訊,真的臨時休市時反而看不見。
        """
        caplog.set_level(logging.INFO)
        _freeze(monkeypatch, FRI, at=_dt.time(8, 0))
        index = FakeIndexSource(daily_bars=[dbar("2026-08-12", 1), dbar("2026-08-13", 2)])
        app = _app(tmp_path, cal=load_trading_calendar(), index=index)
        with _client(app):
            _wait_crosscheck(app)
            warnings = _app_warnings(caplog)
        assert not any("可能過期" in w or "臨時休市" in w for w in warnings), warnings

    def test_crosscheck_base_exception_still_closes_engines(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """C2:交叉檢查以 BaseException 結束時,關機仍走完反序 close。

        它在反序 close 的**最前面** await —— 例外從那裡逃出去就等於六段 close 全部
        不執行(TC4 session / COM 執行緒 / hub worker 一次全洩漏),與 `boot_task`
        上面那段是同一個不變式。觀察點取 breadth `_task`(close 後歸 None)。
        """
        _freeze(monkeypatch, SAT)
        app = _app(
            tmp_path,
            cal=load_trading_calendar(),
            index=BaseExcHistoryIndexSource(),
            breadth=_empty_fetchers(),
        )
        with _client(app):
            _wait_crosscheck(app)
            assert app.state.breadth is not None
            assert app.state.breadth._task is not None
        assert app.state.breadth._task is None, "crosscheck 的例外把反序 close 整串跳過了"


class TestOverlayBasis:
    """SC-13:overlay 基準日 = 顯示中的交易日(cache 鍵同源)。"""

    def test_stock_overlay_basis_and_cache_key_follow_trade_date(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """週六看的是週五那天的圖 → 基準 = 08-14 之前最後一根已完成 bar = 08-13。

        cache 鍵的鑑別點在**第二發時把牆鐘推到週日**:鍵若還是牆鐘,08-16 ≠ 08-15 會
        重算(日別沒變卻多打一次 TC4,且與圖上疊線的基準脫鉤)。
        """
        _freeze(monkeypatch, SAT)
        stock = RecordingStockSource()
        stock.daily_bars_result = list(_DAILY)
        app = _app(tmp_path, cal=load_trading_calendar(), stock=stock)
        with _client(app) as c:
            body = c.get("/api/stock/overlay/2330").json()
            assert body["date"] == "2026-08-13"
            assert stock.daily_calls == 1
            _freeze(monkeypatch, _dt.date(2026, 8, 16))  # 週日:日曆推導仍是 08-14
            assert c.get("/api/stock/overlay/2330").json() == body
            assert stock.daily_calls == 1, "同一交易日第二發應命中 overlay cache"

    def test_index_overlay_basis_follows_trade_date(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _freeze(monkeypatch, SAT)
        index = FakeIndexSource(
            daily_bars=[dbar(f"2026-08-{d:02d}", 23_000_000 + d) for d in range(11, 15)]
        )
        app = _app(tmp_path, cal=load_trading_calendar(), index=index)
        with _client(app) as c:
            assert c.get("/api/index/overlay").json()["date"] == "2026-08-13"

    def test_env_day_shifts_overlay_basis(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """env 模式下 overlay 與 stock/index 日別同源(刻意對齊,SC-13)。"""
        _freeze(monkeypatch, SAT)
        monkeypatch.setenv("TXO_BACKFILL_DATE", "2026-08-13")
        stock = RecordingStockSource()
        stock.daily_bars_result = list(_DAILY)
        app = _app(tmp_path, cal=load_trading_calendar(), stock=stock)
        with _client(app) as c:
            assert c.get("/api/stock/overlay/2330").json()["date"] == "2026-08-12"

    def test_no_calendar_weekday_unchanged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """W6/SC-13:未注入日曆的交易日逐字不變(基準 = 牆鐘今天之前最後一根)。"""
        _freeze(monkeypatch, FRI)
        stock = RecordingStockSource()
        stock.daily_bars_result = list(_DAILY)
        app = _app(tmp_path, stock=stock)
        with _client(app) as c:
            assert c.get("/api/stock/overlay/2330").json()["date"] == "2026-08-13"
