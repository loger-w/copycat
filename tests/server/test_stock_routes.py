from __future__ import annotations

import datetime as _dt
import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient

from copycat.live.stock_models import StockTick
from copycat.live.tc4 import HistoryTimeoutError
from copycat.server import app as app_module
from copycat.server.app import create_app
from copycat.server.signal_hub import SignalHub
from copycat.server.stock_engine import StockEngine
from copycat.stock_watchlist import WATCHLIST_LIMIT, save_watchlist
from tests.helpers.boot import BootedClient
from tests.helpers.fake_sources import FakeStockSource
from tests.helpers.fake_txo import FakeTxoSource

#: VP 折法的跨語言 parity fixture(前端 `src/lib/vp-parity.test.ts` 讀同一個檔)
VP_PARITY_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "vp_parity.json"


def make_client(
    tmp_path: Path, *, names_path: Path | None = None
) -> tuple[TestClient, FakeStockSource]:
    fake = FakeStockSource()
    app = create_app(
        FakeTxoSource(),
        stock_source=fake,
        stock_watchlist_path=tmp_path / "watchlist.json",
        stock_names_path=names_path,
        throttle_secs=0.01,
    )
    return BootedClient(app, raise_server_exceptions=False), fake


class _FailingStartStockSource(FakeStockSource):
    """start() 途中拋例外的 source(`set_trade_date` 是 StockEngine.start 的第一步)。"""

    def __init__(self) -> None:
        super().__init__()
        self.closed = False

    def set_trade_date(self, trade_date: str) -> None:
        raise RuntimeError("boom during start")

    def close(self) -> None:
        self.closed = True


class _ClosingStockSource(FakeStockSource):
    """start 全程正常、只記 `close()` 有沒有被呼叫。"""

    def __init__(self) -> None:
        super().__init__()
        self.closed = False

    def close(self) -> None:
        self.closed = True


class TestEngineStartFailureDegrades:
    """characterization(refactor C7 前置):引擎起停樣板的降級契約。

    `_boot` 即將把五段 try/except 收成一支,而**建構成功但 start 失敗**是最容易在
    重構中掉的分支 —— 掉了會洩漏一條已連線的 TC4 session,且畫面只會看到 503。
    """

    def test_start_exception_closes_source_and_app_still_serves_503(self, tmp_path: Path) -> None:
        fake = _FailingStartStockSource()
        app = create_app(
            FakeTxoSource(),
            stock_source=fake,
            stock_watchlist_path=tmp_path / "watchlist.json",
            throttle_secs=0.01,
        )
        client = BootedClient(app, raise_server_exceptions=False)
        with client:
            r = client.get("/api/stock/watchlist")
        assert r.status_code == 503
        assert r.json()["detail"]["error"] == "NOT_READY"
        assert fake.closed, "start 失敗必須關掉已建好的 source(否則洩漏 TC4 session)"

    def test_bad_watchlist_file_degrades_and_closes_source(self, tmp_path: Path) -> None:
        """壞自選檔 = `_start_stock` 的**第二段**失敗(source 本身完全正常)。

        `load_watchlist` 對壞檔不吞例外,而它留在 `_boot` 的 try 內是行為契約 ——
        把自選回填移到 try 外(看起來只是「起完引擎再補資料」)會讓壞檔變成
        lifespan 例外整台 server 起不來,而不是個股功能單獨降級。
        """
        (tmp_path / "watchlist.json").write_text("{not json", encoding="utf-8")
        fake = _ClosingStockSource()
        app = create_app(
            FakeTxoSource(),
            stock_source=fake,
            stock_watchlist_path=tmp_path / "watchlist.json",
            throttle_secs=0.01,
        )
        client = BootedClient(app, raise_server_exceptions=False)
        with client:
            r = client.get("/api/stock/watchlist")
        assert r.status_code == 503
        assert r.json()["detail"]["error"] == "NOT_READY"
        assert fake.closed is True, "回填失敗一樣要關掉已建好的 source"


class TestStockNamesRoute:
    """搜尋提示列的名稱表(round4 項 1)。表是版控檔 → 降級路徑必須靠注入點才測得到。"""

    def test_returns_versioned_table(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)  # names_path=None → 用版控檔
        with client:
            body = client.get("/api/stock/names").json()
        assert body["count"] == len(body["names"])
        assert body["count"] > 1_800  # 版控檔實測 2,401
        assert {"code": "2330", "name": "台積電"} in body["names"]

    def test_missing_table_returns_empty_not_500(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path, names_path=tmp_path / "nope.json")
        with client:
            r = client.get("/api/stock/names")
        assert r.status_code == 200
        assert r.json() == {"names": [], "count": 0}

    def test_corrupt_table_returns_empty_not_500(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{oops", encoding="utf-8")
        client, _ = make_client(tmp_path, names_path=bad)
        with client:
            r = client.get("/api/stock/names")
        assert r.status_code == 200
        assert r.json() == {"names": [], "count": 0}

    def test_available_without_tc4(self, tmp_path: Path) -> None:
        """名稱表與 TC4 連線無關:達錢 4 沒開(stock engine 未就緒)也要能搜尋。"""
        app = create_app(FakeTxoSource(), throttle_secs=0.01)  # 無 stock_source
        with BootedClient(app, raise_server_exceptions=False) as client:
            assert client.get("/api/stock/names").status_code == 200


class TestWatchlistRoutes:
    """v3 shape `{codes, groups}`(stock-ui-round5 §🔴-5);舊 groups-only body 仍相容."""

    def test_get_empty_then_put_round_trip(self, tmp_path: Path) -> None:
        client, fake = make_client(tmp_path)
        with client:
            assert client.get("/api/stock/watchlist").json() == {"codes": [], "groups": []}
            groups = [
                {"name": "主力", "codes": ["2330", "5483"]},
                {"name": "觀察", "codes": ["3231"]},
            ]
            body = {"codes": ["2330", "5483", "3231"], "groups": groups}
            r = client.put("/api/stock/watchlist", json=body)
            assert r.status_code == 200
            assert r.json() == body
            assert client.get("/api/stock/watchlist").json() == body
            assert "2330" in fake.subscribed and "3231" in fake.subscribed  # 全體已訂

    def test_put_without_codes_defaults_to_union(self, tmp_path: Path) -> None:
        """舊 client 只送 groups → 存檔結果與 v2 時代逐字元相同(codes = 聯集)."""
        client, _ = make_client(tmp_path)
        with client:
            groups = [
                {"name": "主力", "codes": ["2330", "5483"]},
                {"name": "觀察", "codes": ["3231", "2330"]},
            ]
            r = client.put("/api/stock/watchlist", json={"groups": groups})
            assert r.status_code == 200
            assert r.json() == {"codes": ["2330", "5483", "3231"], "groups": groups}

    def test_ungrouped_code_enters_subscription_pool(self, tmp_path: Path) -> None:
        """SC-18 的機械守門:不屬任何群組的 code 也要進 set_watchlist."""
        client, fake = make_client(tmp_path)
        with client:
            r = client.put(
                "/api/stock/watchlist",
                json={
                    "codes": ["2330", "5483"],
                    "groups": [{"name": "主力", "codes": ["2330"]}],
                },
            )
            assert r.status_code == 200
            assert r.json()["codes"] == ["2330", "5483"]
            assert "5483" in fake.subscribed

    def test_put_bad_code_400(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)
        with client:
            body = {"groups": [{"name": "a", "codes": ["bad code"]}]}
            r = client.put("/api/stock/watchlist", json=body)
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "BAD_CODE"

    def test_put_bad_group_400(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)
        with client:
            body = {"groups": [{"name": "  ", "codes": ["2330"]}]}
            r = client.put("/api/stock/watchlist", json=body)
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "BAD_GROUP"

    def test_put_at_limit_ok(self, tmp_path: Path) -> None:
        """字面 50 與 test_put_over_limit_400 的字面 51 成對釘死邊界 = 50。

        兩支都引常數的話,上限值本身就沒有任何測試錨點(改常數兩支自動跟著綠)。
        """
        client, _ = make_client(tmp_path)
        with client:
            codes = [f"{1000 + i}" for i in range(150)]
            r = client.put("/api/stock/watchlist", json={"groups": [{"name": "a", "codes": codes}]})
            assert r.status_code == 200
            assert r.json()["codes"] == codes

    def test_put_over_limit_400(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)
        with client:
            # 字面 151:與 test_put_at_limit_ok 的字面 150 成對釘死邊界 150/151
            codes = [f"{1000 + i}" for i in range(151)]
            r = client.put("/api/stock/watchlist", json={"groups": [{"name": "a", "codes": codes}]})
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "WATCHLIST_FULL"

    def test_watchlist_persists_across_app_restart(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)
        with client:
            client.put(
                "/api/stock/watchlist", json={"groups": [{"name": "自選", "codes": ["2330"]}]}
            )
        client2, fake2 = make_client(tmp_path)
        with client2:
            assert client2.get("/api/stock/watchlist").json() == {
                "codes": ["2330"],
                "groups": [{"name": "自選", "codes": ["2330"]}],
            }
            assert "2330" in fake2.subscribed  # 啟動即訂回持久化清單

    def test_v1_file_restores_codes_on_startup(self, tmp_path: Path) -> None:
        """v1 檔(codes shape)重啟 → 全部落未分組,codes 仍進訂閱池(🔴 行為改)."""
        import json as _json

        (tmp_path / "watchlist.json").write_text(
            _json.dumps({"_cache_version": 1, "codes": ["2330", "5483"]}), encoding="utf-8"
        )
        client, fake = make_client(tmp_path)
        with client:
            assert client.get("/api/stock/watchlist").json() == {
                "codes": ["2330", "5483"],
                "groups": [],
            }
            assert "2330" in fake.subscribed and "5483" in fake.subscribed

    def test_v2_file_restores_union_on_startup(self, tmp_path: Path) -> None:
        """v2 檔(groups shape)重啟 → codes 由聯集補,畫面零差異(SC-17)."""
        import json as _json

        (tmp_path / "watchlist.json").write_text(
            _json.dumps(
                {"_cache_version": 2, "groups": [{"name": "主力", "codes": ["2330", "5483"]}]}
            ),
            encoding="utf-8",
        )
        client, fake = make_client(tmp_path)
        with client:
            assert client.get("/api/stock/watchlist").json() == {
                "codes": ["2330", "5483"],
                "groups": [{"name": "主力", "codes": ["2330", "5483"]}],
            }
            assert "2330" in fake.subscribed and "5483" in fake.subscribed


class TestOverlayRoute:
    """SC-4:/api/stock/overlay/{code} — 200 形狀 / BAD_CODE / TC4 down 全 null."""

    BARS = [
        {"date": f"2026-06-{d:02d}", "high": 103_000, "low": 100_000, "close": 100_000 + d * 100}
        for d in range(1, 27)
    ]

    def test_overlay_shape_200(self, tmp_path: Path) -> None:
        client, fake = make_client(tmp_path)
        fake.daily_bars_result = list(self.BARS)
        with client:
            r = client.get("/api/stock/overlay/2330")
            assert r.status_code == 200
            body = r.json()
            assert set(body) == {"cdp", "ma5", "ma20", "date"}
            assert body["date"] == "2026-06-26"
            assert set(body["cdp"]) == {"cdp", "ah", "nh", "nl", "al"}
            assert isinstance(body["ma5"], int) and isinstance(body["ma20"], int)

    def test_overlay_bad_code_400(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)
        with client:
            r = client.get("/api/stock/overlay/bad!")
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "BAD_CODE"

    def test_overlay_tc4_down_returns_all_null_200(self, tmp_path: Path) -> None:
        client, fake = make_client(tmp_path)
        fake.daily_bars_result = ConnectionError("tc4 down")
        with client:
            r = client.get("/api/stock/overlay/2330")
            assert r.status_code == 200
            assert r.json() == {"cdp": None, "ma5": None, "ma20": None, "date": None}

    def test_overlay_history_timeout_degrades_like_asyncio_timeout(self, tmp_path: Path) -> None:
        """`daily_bars` 現在會把 TC4 首頁逾時往外拋(hub 靠它排重試)。

        route 這一端的語意與既有 `OVERLAY_FETCH_TIMEOUT_S` 逾時完全相同 —— 200 + 全 null
        + 不寫 cache。沒有這條分支的話,`ConnectionError` 的降級接不到子類以外的任何
        地方,疊線會變成 500/502。
        """
        client, fake = make_client(tmp_path)
        fake.daily_bars_result = HistoryTimeoutError("first page not ready")
        with client:
            r = client.get("/api/stock/overlay/2330")
            assert r.status_code == 200
            assert r.json() == {"cdp": None, "ma5": None, "ma20": None, "date": None}


class _GatedDailyBarsSource(FakeStockSource):
    """`fetch_daily_bars` 記併發峰值,且**等到本批到齊 `cap` 個才放行**。

    純 `sleep` + 計數在慢機器上會退化成「剛好沒重疊」的假綠(峰值 1 也算通過)。
    等待條件讓上限變成可觀察的終態:有節流時恰好 4 個同時卡在門內,沒節流時 8 個
    一起進來(峰值 8)。`timeout` 是不讓測試在真的壞掉時吊死,不是正常路徑。
    """

    def __init__(self, cap: int = 4) -> None:
        super().__init__()
        self._cap = cap
        self._cond = threading.Condition()
        self.in_flight = 0
        self.peak = 0

    def fetch_daily_bars(self, code: str, n: int = 25) -> list:
        with self._cond:
            self.in_flight += 1
            self.peak = max(self.peak, self.in_flight)
            self._cond.notify_all()
            self._cond.wait_for(lambda: self.in_flight >= self._cap, timeout=10.0)
        try:
            time.sleep(0.01)  # 讓下一批有機會與本批重疊(峰值才量得出來)
            return []
        finally:
            with self._cond:
                self.in_flight -= 1
                self._cond.notify_all()


class TestOverlayConcurrencyGate:
    """AD-5 amendment(review R5):`cdp` 預設開,進群組會對 ≤50 檔同時打 overlay,
    而 `daily_bars` 走 `to_thread` 無上限、共用同一條 TC4 歷史通道。

    節流刻意放在 **route 層**而不是 `engine.daily_bars`:後者另有 `signal_hub` 的
    basis 取數在用,擋在引擎會連訊號的 basis 一起拖慢(round 2 R2-3)。
    """

    def test_daily_bars_in_flight_capped_at_four(self, tmp_path: Path) -> None:
        source = _GatedDailyBarsSource()
        app = create_app(
            FakeTxoSource(),
            stock_source=source,
            stock_watchlist_path=tmp_path / "watchlist.json",
            throttle_secs=0.01,
        )
        codes = [str(9000 + i) for i in range(8)]  # 相異碼:cache 不得吃掉併發
        results: dict[str, int] = {}
        with BootedClient(app, raise_server_exceptions=False) as client:

            def _hit(code: str) -> None:
                results[code] = client.get(f"/api/stock/overlay/{code}").status_code

            threads = [threading.Thread(target=_hit, args=(c,)) for c in codes]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=15)
        assert list(results.values()) == [200] * 8
        # 上界是契約(節流拿掉 → 峰值 8),下界只求「真的有重疊」—— 慢機器上第 4 個
        # 執行緒可能等到 `wait_for` 逾時才進門,此時峰值 2~3 而節流仍然是對的。
        # `peak == 4` 的精確斷言把「機器慢」誤報成「節流壞了」(review B5)。
        assert source.peak <= 4, f"overlay 併發上限應為 4,實測峰值 {source.peak}"
        assert source.peak >= 2, f"完全沒重疊 = 沒量到併發,這條測試 vacuous(峰值 {source.peak})"


class _SlowDailyBarsSource(FakeStockSource):
    """`fetch_daily_bars` 對 `slow` 內的股號睡 `delay` 秒(其餘照常回 bar)。

    模擬 TC4 「查無此檔」:不是快速失敗,而是把 deadline 睡好睡滿。
    """

    def __init__(self, slow: set[str], delay: float = 1.0) -> None:
        super().__init__()
        self.slow = slow
        self._delay = delay
        self.daily_calls: list[str] = []

    def fetch_daily_bars(self, code: str, n: int = 25) -> list:
        self.daily_calls.append(code)
        if code in self.slow:
            time.sleep(self._delay)
        return list(TestOverlayRoute.BARS)


class TestOverlayFetchTimeout:
    """review B2:`overlay_sem` 名額沒有時間上界 → head-of-line。

    TC4 對查無此檔的股號會把 deadline 睡滿(30s×2),而空結果依 overlay.py 規則
    不進 cache → 每次請求都重付一次。四檔這種股號就能把 Semaphore(4) 佔滿,
    整個端點凍住;畫面上只是「疊線一直沒出來」,零錯誤訊號。
    """

    def test_slow_code_times_out_all_null_and_frees_slot(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(app_module, "OVERLAY_FETCH_TIMEOUT_S", 0.2)
        source = _SlowDailyBarsSource({"2330"})
        app = create_app(
            FakeTxoSource(),
            stock_source=source,
            stock_watchlist_path=tmp_path / "watchlist.json",
            throttle_secs=0.01,
        )
        with BootedClient(app, raise_server_exceptions=False) as client:
            r = client.get("/api/stock/overlay/2330")
            assert r.status_code == 200
            assert r.json() == {"cdp": None, "ma5": None, "ma20": None, "date": None}

            # 名額已放掉:後面排隊的股號照常取得(head-of-line 的反面)
            other = client.get("/api/stock/overlay/2317")
            assert other.status_code == 200
            assert other.json()["cdp"] is not None

            # 逾時**不寫 cache**(沿 overlay.py 空結果不 cache):同一檔恢復後
            # 再打一次要真的重新取數,而不是今天再也拿不到疊線
            source.slow.discard("2330")
            again = client.get("/api/stock/overlay/2330")
            assert again.status_code == 200
            assert again.json()["cdp"] is not None
        assert source.daily_calls.count("2330") == 2, "逾時那次若被 cache 住,第二次就不會取數"


class TestStateRoute:
    def test_get_state_sets_main_and_returns_snapshot(self, tmp_path: Path) -> None:
        client, fake = make_client(tmp_path)
        with client:
            r = client.get("/api/stock/state/2330")
            assert r.status_code == 200
            snap = r.json()
            assert snap["code"] == "2330"
            assert snap["seq"] == 0
            # SC-3:REST snapshot 帶 additive `trial`(單檔頁 header 的種子;側欄吃
            # `watchlist_quote`,只加一邊會有一個消費端拿不到)
            assert "trial" in snap
            assert isinstance(snap["trial"], bool)
            assert "2330" in fake.subscribed  # main owner 已訂

    def test_get_state_bad_code_400(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)
        with client:
            r = client.get("/api/stock/state/bad!")
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "BAD_CODE"

    def test_engine_missing_beats_bad_code(self) -> None:
        """引擎未就緒 + 代號非法 → 503 不是 400(`_valid_code` 在 `_stock` 之後的優先序)。

        把代號閘做成 `Depends` 看起來更整齊,但 FastAPI 會在 handler body 之前跑它 ——
        優先序會靜默翻成 400,前端就把「達錢 4 沒開」誤顯示成「代號打錯」。
        """
        app = create_app(FakeTxoSource(), throttle_secs=0.01)  # 無 stock_source
        with BootedClient(app, raise_server_exceptions=False) as client:
            r = client.get("/api/stock/state/@@@")
        assert r.status_code == 503
        assert r.json()["detail"]["error"] == "NOT_READY"


#: 餵一則成交進 engine(讓 tape 非空;欄位比照 TestStockWs 的真 TC4 payload)。
#: **刻意不帶 Upper/LowerLimitPrice**:漲跌停值變(None → 有值)是 engine 的回補入列點
#: 之一,而回補是原子重建 —— 帶了就會在餵完 tick 之後非同步把 tape 清掉。
TICK_MSG: dict[str, str] = {
    "Symbol": "TC.S.TWS.2330",
    "Security": "2330",
    "SecurityName": "台積電",
    "TradingPrice": "2380",
    "TradeQuantity": "1",
    "TradeVolume": "1",
    "TradeDate": "20260721",
    "FilledTime": "25751",
    "PreciseTime": "25751000000",
    "Bid": "2375",
    "Ask": "2380",
    "BidVolume": "10",
    "AskVolume": "10",
    "ReferencePrice": "2320",
    "YClosedPrice": "2320",
    "YTradeVolume": "100",
    "OpenTime": "90000",
    "CloseTime": "133000",
    "TradeStatus": "0",
}


class TestStateRouteTape:
    """`?tape=0` 省略逐筆明細(B15)。

    群組檢視點卡片的**唯一目的**是換右欄閃電梯的標的(檢視停在群組),而群組檢視裡
    沒有主圖 / 明細 —— 那趟卻照樣拖回整份 tape(M0 盤中實測 0.5–1.5 MB/檔,50 檔輪點
    20–70 MB)。`set_main` 仍要打(W-4:訂閱與回補靠它),省的只有 payload。
    """

    def _wait(self, client: TestClient, pred: Callable[[StockEngine], bool], why: str) -> None:
        stock = cast("StockEngine", client.app.state.stock)  # type: ignore[attr-defined]
        for _ in range(300):
            if pred(stock):
                return
            time.sleep(0.01)
        raise AssertionError(why)

    def _quiet_state_with_one_tick(self, client: TestClient, fake: FakeStockSource) -> None:
        """把 2330 帶到「tape 有一筆、且不會再有回補落地」的穩定點。

        `apply_backfill` 是**原子重建**(seq +1001、ticks 整份換掉),落在餵 tick 與
        兩次 GET 之間就會把全量那份的 tape 清空 —— 對照退化成「兩邊都空」的假綠。
        所以:(a) 先等 `set_main` 那趟回補落地才餵;(b) 餵的那則**不帶漲跌停**,
        否則 meta 值變(None → 有值)會再排一趟非同步回補(engine 既有行為)。
        """
        assert fake.on_message is not None
        client.get("/api/stock/state/2330")  # set_main → 唯一一趟回補
        self._wait(client, lambda s: "2330" in s._backfilled, "set_main 的回補沒落地")
        fake.on_message(dict(TICK_MSG))
        self._wait(
            client,
            lambda s: (st := s._states.get("2330")) is not None and len(st.ticks) == 1,
            "餵進去的成交沒進 tape",
        )

    def test_tape_0_omits_ticks_and_leaves_every_other_key_intact(self, tmp_path: Path) -> None:
        client, fake = make_client(tmp_path)
        with client:
            self._quiet_state_with_one_tick(client, fake)
            full = client.get("/api/stock/state/2330").json()
            light = client.get("/api/stock/state/2330?tape=0").json()
        assert full["ticks"], "基準 tape 是空的 → 兩邊都空,測不出東西"
        assert light["ticks"] == []
        assert light["tape_omitted"] is True
        assert "tape_omitted" not in full, "全量路徑多一個鍵 = 契約漂移(W3 位元不變)"
        assert {k: v for k, v in light.items() if k != "tape_omitted"} == full | {"ticks": []}

    def test_tape_0_still_sets_main(self, tmp_path: Path) -> None:
        """W-4:省 payload 不等於省 set_main —— 漏掉的話點卡片就換不了訂閱標的,
        而畫面上只表現為右欄「沒有資料」,沒有任何錯誤。"""
        client, fake = make_client(tmp_path)
        with client:
            r = client.get("/api/stock/state/2317?tape=0")
        assert r.status_code == 200
        assert "2317" in fake.subscribed

    def test_unknown_tape_value_falls_back_to_full(self, tmp_path: Path) -> None:
        """`tape` 收字串不收 int(D3'):`?tape=abc` 走全量,不產生 422 ——
        422 的 detail 是 list 形,不符全站 `{"detail": {"error": code}}` 契約。"""
        client, fake = make_client(tmp_path)
        with client:
            self._quiet_state_with_one_tick(client, fake)
            r = client.get("/api/stock/state/2330?tape=abc")
        assert r.status_code == 200
        assert r.json()["ticks"], "非 0 一律全量"
        assert "tape_omitted" not in r.json()


STKFUT_CATALOG: dict[str, dict] = {
    "2330": {
        "name": "台積電",
        "std": {"prod": "CDF", "contracts": ["202608", "202609"]},
        "mini": {"prod": "QFF", "contracts": ["202609"]},
    },
    "2317": {
        "name": "鴻海",
        "std": {"prod": "DHF", "contracts": ["202608", "202609"]},
        "mini": None,
    },
}


class TestStateRouteContract:
    """`?contract=` 主圖合約切換(stkfut-contracts SC-3 / D6+D7)。

    **白名單是這組測試的核心**:regex 過得了不代表這個合約屬於這檔股票 ——
    `/api/stock/state/2330?contract=DHF:202609` 光看形狀完全合法,放行的話主圖畫的是
    鴻海期貨,而 URL、下單面、右側欄的股號全都還是 2330,畫面上沒有任何地方會不一致
    到被看出來(TC4 對不存在 / 不相干的 symbol 一律照回 `Success: OK`,連訂閱層都不會
    抗議)。所以合法性判定只能來自 catalog,不能只靠字串形。
    """

    def _client(self, tmp_path: Path) -> tuple[TestClient, FakeStockSource]:
        client, fake = make_client(tmp_path)
        fake.stkfut_catalog = {k: dict(v) for k, v in STKFUT_CATALOG.items()}
        return client, fake

    def test_valid_contract_switches_main_and_returns_instrument_key(self, tmp_path: Path) -> None:
        client, fake = self._client(tmp_path)
        with client:
            r = client.get("/api/stock/state/2330?contract=CDF:202609")
        assert r.status_code == 200
        snap = r.json()
        # code = instrument key(前端 WS 比對鍵);underlying = 股號(下單/右欄口徑)
        assert snap["code"] == "F:CDF:202609"
        assert snap["underlying"] == "2330"
        assert "F:CDF:202609" in fake.subscribed, "set_main_contract 必須真的訂到合約鍵"

    def test_mini_contract_allowed(self, tmp_path: Path) -> None:
        """小型合約也在白名單內(std / mini 兩腿都要查,只查 std 會讓小型永遠 400)。"""
        client, fake = self._client(tmp_path)
        with client:
            r = client.get("/api/stock/state/2330?contract=QFF:202609")
        assert r.status_code == 200
        assert r.json()["code"] == "F:QFF:202609"
        assert "F:QFF:202609" in fake.subscribed

    def test_no_contract_keeps_spot_behaviour(self, tmp_path: Path) -> None:
        """現貨態零行為變更;`underlying` 在現貨態 = code 自身(前端單一讀法)。"""
        client, fake = self._client(tmp_path)
        with client:
            r = client.get("/api/stock/state/2330")
        assert r.status_code == 200
        snap = r.json()
        assert snap["code"] == "2330"
        assert snap["underlying"] == "2330"
        assert "2330" in fake.subscribed

    def test_foreign_product_rejected(self, tmp_path: Path) -> None:
        """形狀合法但產品屬於別檔股票 → 400(白名單的存在理由)。"""
        client, fake = self._client(tmp_path)
        with client:
            r = client.get("/api/stock/state/2330?contract=DHF:202609")
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "BAD_CONTRACT"
        assert "F:DHF:202609" not in fake.subscribed, "被拒的合約不得留下訂閱"

    def test_unknown_month_rejected(self, tmp_path: Path) -> None:
        """產品對、月份不在清單(已到期 / 尚未掛牌)→ 400。

        放行的話會訂到不存在的 symbol,而 TC4 照回 OK → 表現為「圖是空的」。
        """
        client, fake = self._client(tmp_path)
        with client:
            r = client.get("/api/stock/state/2330?contract=CDF:202612")
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "BAD_CONTRACT"
        assert "F:CDF:202612" not in fake.subscribed

    def test_stock_without_futures_rejected(self, tmp_path: Path) -> None:
        client, _ = self._client(tmp_path)
        with client:
            r = client.get("/api/stock/state/9999?contract=CDF:202609")
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "BAD_CONTRACT"

    @pytest.mark.parametrize(
        "contract",
        [
            "CDF-202609",  # 分隔符錯
            "CDF:2026",  # 缺月
            "cdf:202609",  # 小寫
            "CDF:202613",  # 月份 13
            "CDF:202600",  # 月份 00
            "CDF:192609",  # 世紀非 20
            "C:202609",  # 產品碼過短
            "CDFFF:202609",  # 產品碼過長
            "CDF:202609:X",  # 尾贅
            "F:CDF:202609",  # 直接把 instrument key 當 contract 塞
            "",  # 空字串(前端狀態清空時最容易誤送)
        ],
    )
    def test_malformed_contract_rejected(self, tmp_path: Path, contract: str) -> None:
        """形檢在白名單之前:壞形不該打到 catalog(那是一次 TC4 查詢)。"""
        client, fake = self._client(tmp_path)
        with client:
            r = client.get("/api/stock/state/2330", params={"contract": contract})
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "BAD_CONTRACT"
        assert fake.subscribed == [], "被拒的請求不得動到訂閱池"

    def test_catalog_down_rejects_not_falls_back_to_spot(self, tmp_path: Path) -> None:
        """catalog 查不到 → 502,**不放行**。

        降級成「當作現貨處理」會讓 TC4 一斷線畫面就悄悄從期貨跳回現貨,而下拉還顯示著
        合約 —— 使用者看著的是另一個商品的價格。
        """
        client, fake = self._client(tmp_path)
        fake.stkfut_catalog = ConnectionError("tc4 down")
        with client:
            r = client.get("/api/stock/state/2330?contract=CDF:202609")
        assert r.status_code == 502
        assert r.json()["detail"]["error"] == "TC4_DOWN"
        assert fake.subscribed == []

    def test_bad_code_beats_contract_check(self, tmp_path: Path) -> None:
        """代號閘優先(既有優先序不變):壞代號 + 壞合約 → BAD_CODE。"""
        client, _ = self._client(tmp_path)
        with client:
            r = client.get("/api/stock/state/bad!?contract=nope")
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "BAD_CODE"


class TestGroupStateRoute:
    """群組檢視的唯讀 batch(group-grid SC-4)。

    **這條路存在的唯一理由就是不 set_main**:群組檢視每分鐘會對最多 50 檔各要一次
    狀態,重用 `/api/stock/state/{code}` 等於每分鐘把主圖搶走 50 次 → 主圖分時線凍結,
    而畫面上只表現為「圖不動了」,沒有任何錯誤。所以 `_main` 的斷言是本組的核心。
    """

    def _put(self, client: TestClient, codes: list[str]) -> None:
        r = client.put("/api/stock/watchlist", json={"codes": codes, "groups": []})
        assert r.status_code == 200

    def test_batch_shape_and_never_sets_main(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)
        with client:
            self._put(client, ["2330", "2317"])
            r = client.get("/api/stock/group-state", params={"codes": "2330,2317"})
            assert r.status_code == 200
            states = r.json()["states"]
            assert set(states) == {"2330", "2317"}
            # payload 形寫死:ticks 不得混進來(50 檔 × 數千筆 = 頻寬炸彈),但
            # light_snapshot 的四個加鍵(vwap/high/low/vp)必須到得了前端 —— 卡片圖
            # 的 VWAP 白線 / 日高低圈 / VP 條全靠它們(🔴 group-grid-full-chart SC-5)
            assert set(states["2330"]) == {
                "minutes",
                "meta",
                "vwap",
                "high",
                "low",
                "vp",
                "no_data",
                "backfilling",
            }
            assert states["2330"]["no_data"] is False
            stock = cast("StockEngine", client.app.state.stock)  # type: ignore[attr-defined]
            assert stock._main is None, "群組 batch 不得 set_main(會把主圖搶走)"

    def test_empty_codes_returns_empty_states(self, tmp_path: Path) -> None:
        """空群組 → 前端 hook 是 enabled=false 零請求;真的打到也必須是 200 空表。"""
        client, _ = make_client(tmp_path)
        with client:
            assert client.get("/api/stock/group-state").json() == {"states": {}}
            r = client.get("/api/stock/group-state", params={"codes": ""})
            assert r.status_code == 200
            assert r.json() == {"states": {}}

    def test_unknown_code_is_no_data_not_404(self, tmp_path: Path) -> None:
        """未訂閱 / 查無此檔對卡片是同一件事(「這格畫不出東西」)→ 無 404 路徑。"""
        client, _ = make_client(tmp_path)
        with client:
            states = client.get("/api/stock/group-state", params={"codes": "9999"}).json()["states"]
            assert states["9999"]["no_data"] is True
            assert states["9999"]["minutes"] == {}
            assert states["9999"]["meta"] is None
            # 空卡的四個加鍵一律是「不可得」而不是漏鍵:前端 `?? null` 對漏鍵與 null
            # 同解,但少一個鍵時契約測試與型別都看不出來(同 meta 的理由)
            assert states["9999"]["vwap"] is None
            assert states["9999"]["high"] is None
            assert states["9999"]["low"] is None
            assert states["9999"]["vp"] == {}

    def test_vp_reaches_the_wire_matching_the_shared_parity_fixture(self, tmp_path: Path) -> None:
        """端到端 parity(SC-5):同一份 ticks 進狀態機 → 端點吐出的 `vp` 必須逐鍵等於
        手算的 `expected`,而前端 `src/lib/vp-parity.test.ts` 對同一個檔各自斷言。

        兩份折法各漂各的樣態是「同一檔在單檔頁與卡片上 POC 不同」——兩個數字都畫得出
        來、都看起來對,沒有任何錯誤訊號。JSON 鍵是字串:序列化這一段也在 parity 內。
        """
        fixture = json.loads(VP_PARITY_PATH.read_text(encoding="utf-8"))
        client, _ = make_client(tmp_path)
        with client:
            self._put(client, ["2330"])
            stock = cast("StockEngine", client.app.state.stock)  # type: ignore[attr-defined]
            state = stock._states["2330"]
            for i, row in enumerate(fixture["ticks"]):
                state.ingest(
                    StockTick(
                        code="2330",
                        price_milli=row["p"],
                        qty=row["q"],
                        cum_vol=i + 1,
                        time=row["t"],
                        trade_date="2026-07-21",
                        side=row["side"],
                        is_trial=False,
                    )
                )
            states = client.get("/api/stock/group-state", params={"codes": "2330"}).json()["states"]
        assert states["2330"]["vp"] == fixture["expected"]

    def test_group_state_at_limit_ok(self, tmp_path: Path) -> None:
        """字面 150 相異碼 → 200(與 test_too_many_codes_400 的字面 151 成對釘死邊界)。"""
        client, _ = make_client(tmp_path)
        with client:
            codes = ",".join(f"{9000 + i}" for i in range(150))
            r = client.get("/api/stock/group-state", params={"codes": codes})
            assert r.status_code == 200
            assert len(r.json()["states"]) == 150

    def test_too_many_codes_400(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)
        with client:
            codes = ",".join(f"{9000 + i}" for i in range(151))  # 自選上限 150(與 at-limit 成對)
            r = client.get("/api/stock/group-state", params={"codes": codes})
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "BAD_CODES"

    def test_bad_code_400(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)
        with client:
            r = client.get("/api/stock/group-state", params={"codes": "2330,bad!"})
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "BAD_CODE"

    def test_engine_missing_503(self) -> None:
        app = create_app(FakeTxoSource(), throttle_secs=0.01)  # 無 stock_source
        with BootedClient(app, raise_server_exceptions=False) as client:
            r = client.get("/api/stock/group-state", params={"codes": "@@@"})
        assert r.status_code == 503
        assert r.json()["detail"]["error"] == "NOT_READY"

    def test_duplicate_codes_are_deduped_before_the_count_check(self, tmp_path: Path) -> None:
        """A6-2:重複碼是**正常輸入**(同一檔可屬多群組,前端把群組成員直接拼進 csv),
        先驗數量再去重會把它判成 `BAD_CODES` —— 而整個群組頁只會顯示「載入失敗」,
        沒有任何線索指向「你有一檔重複」。去重要**保序**:卡片順序就是這個順序。
        """
        client, _ = make_client(tmp_path)
        with client:
            self._put(client, ["2330", "2317"])
            # 重複數必須 > 上限,否則失去鑑別力(考點是「去重先於驗數」的順序)
            dup = ",".join(["2330"] * (WATCHLIST_LIMIT + 1))
            r = client.get("/api/stock/group-state", params={"codes": dup})
            assert r.status_code == 200
            assert list(r.json()["states"]) == ["2330"]
            r = client.get("/api/stock/group-state", params={"codes": "2317,2330,2317"})
            assert list(r.json()["states"]) == ["2317", "2330"]

    def test_dedup_does_not_defeat_the_limit(self, tmp_path: Path) -> None:
        """去重之後仍要驗上限:相異碼超量照樣 400(去重不是放行的後門)。"""
        client, _ = make_client(tmp_path)
        with client:
            codes = ",".join(f"{9000 + i}" for i in range(WATCHLIST_LIMIT + 1))
            r = client.get("/api/stock/group-state", params={"codes": codes})
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "BAD_CODES"


class TestSignalHubGroupWiring:
    """接線防呆(group-grid R7):`groups_fn` / `quotes_fn` 預設 None = 靜默停用摘要。

    忘了在 `create_app` 接上去的失效樣態是「Discord 通知少了一段尾巴」—— 沒有例外、
    沒有 log、hub 單元測試全綠。只有從 booted app 這一端看才抓得到。
    """

    def test_boot_injects_groups_and_quotes(self, tmp_path: Path) -> None:
        save_watchlist(
            tmp_path / "watchlist.json",
            {"codes": ["2330", "2317"], "groups": [{"name": "半導體", "codes": ["2330", "2317"]}]},
        )
        client, _ = make_client(tmp_path)
        with client:
            hub = cast("SignalHub", client.app.state.signal_hub)  # type: ignore[attr-defined]
            assert hub is not None
            assert hub._groups == [{"name": "半導體", "codes": ["2330", "2317"]}]
            # quotes_fn 也接上了才產得出成員列(缺行情時是 `-`,但不會是空字串)
            assert hub._group_suffix({"code": "2330"}).startswith("｜同群 半導體:2317")

    def test_group_rename_without_code_change_reaches_the_hub(self, tmp_path: Path) -> None:
        """B3-a 端到端:只改群組名(codes 一模一樣)也要傳到 hub。

        這條路的 `set_watchlist` 收到的 added / removed 都是空的 —— 只要哪天有人為了
        省 UNSUB/SUB 而把 `on_watchlist` 收進「有增減才呼叫」的條件裡,摘要就會一直
        印**舊組名**,而畫面、log、hub 單元測試全部正常。
        """
        save_watchlist(
            tmp_path / "watchlist.json",
            {"codes": ["2330", "2317"], "groups": [{"name": "舊名", "codes": ["2330", "2317"]}]},
        )
        client, _ = make_client(tmp_path)
        with client:
            hub = cast("SignalHub", client.app.state.signal_hub)  # type: ignore[attr-defined]
            assert hub._groups == [{"name": "舊名", "codes": ["2330", "2317"]}]
            r = client.put(
                "/api/stock/watchlist",
                json={
                    "codes": ["2330", "2317"],
                    "groups": [{"name": "新名", "codes": ["2330", "2317"]}],
                },
            )
            assert r.status_code == 200
            assert hub._groups == [{"name": "新名", "codes": ["2330", "2317"]}]


class TestStockWs:
    def test_ws_streams_engine_messages(self, tmp_path: Path) -> None:
        client, fake = make_client(tmp_path)
        with client:
            client.get("/api/stock/state/2330")
            with client.websocket_connect("/ws/stock") as ws:
                assert fake.on_message is not None
                fake.on_message(
                    {
                        "Symbol": "TC.S.TWS.2330",
                        "Security": "2330",
                        "SecurityName": "台積電",
                        "TradingPrice": "2380",
                        "TradeQuantity": "1",
                        "TradeVolume": "1",
                        "TradeDate": "20260721",
                        "FilledTime": "25751",
                        "PreciseTime": "25751000000",
                        "Bid": "2375",
                        "Ask": "2380",
                        "BidVolume": "10",
                        "AskVolume": "10",
                        "ReferencePrice": "2320",
                        "UpperLimitPrice": "2550",
                        "LowerLimitPrice": "2090",
                        "YClosedPrice": "2320",
                        "YTradeVolume": "100",
                        "OpenTime": "90000",
                        "CloseTime": "133000",
                        "TradeStatus": "0",
                    }
                )
                got = [ws.receive_json(), ws.receive_json()]
                types = {m["type"] for m in got}
                assert {"tick", "book"} & types


class TestBarsRoute:
    """K 線 endpoint(SC-7;change-spec 🟢-6)。"""

    def _bar(self, t: str) -> dict:
        return {"t": t, "o": 100, "h": 110, "l": 90, "c": 105, "v": 7}

    def test_daily_shape_200(self, tmp_path: Path) -> None:
        client, fake = make_client(tmp_path)
        fake.bars_result = [self._bar("2026-07-27")]
        with client:
            r = client.get("/api/stock/bars/2330?tf=D")
            assert r.status_code == 200
            assert r.json() == {
                "code": "2330",
                "tf": "D",
                "bars": [{"t": "2026-07-27", "o": 100, "h": 110, "l": 90, "c": 105, "v": 7}],
                "status": "ok",
            }
            assert fake.bars_calls[0][1] == "D"

    def test_minute_shape_200(self, tmp_path: Path) -> None:
        client, fake = make_client(tmp_path)
        fake.bars_result = [self._bar("2026-07-28 09:01")]
        with client:
            r = client.get("/api/stock/bars/2330?tf=1&days=1")
            assert r.status_code == 200
            assert r.json()["tf"] == "1"
            assert fake.bars_calls[0][1] == "1"

    def test_default_tf_is_daily(self, tmp_path: Path) -> None:
        client, fake = make_client(tmp_path)
        with client:
            assert client.get("/api/stock/bars/2330").json()["tf"] == "D"

    def test_bad_code_400(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)
        with client:
            r = client.get("/api/stock/bars/bad code?tf=D")
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "BAD_CODE"

    def test_bad_tf_400(self, tmp_path: Path) -> None:
        client, _ = make_client(tmp_path)
        with client:
            r = client.get("/api/stock/bars/2330?tf=5m")
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "BAD_TF"

    def test_days_clamped_not_rejected(self, tmp_path: Path) -> None:
        client, fake = make_client(tmp_path)
        fake.bars_result = [self._bar("2026-07-28 09:01")]
        with client:
            assert client.get("/api/stock/bars/2330?tf=1&days=999").status_code == 200
            starts = [c[2] for c in fake.bars_calls]
            ends = [c[3] for c in fake.bars_calls]
            span = (
                _dt.date.fromisoformat(max(ends)) - _dt.date.fromisoformat(min(starts))
            ).days
            assert span <= 30

    def test_bad_days_400_not_422(self, tmp_path: Path) -> None:
        """days 轉換失敗要走專案錯誤契約,不是 FastAPI 預設 422 + list 形 detail(W-D3)。"""
        client, _ = make_client(tmp_path)
        with client:
            r = client.get("/api/stock/bars/2330?tf=1&days=abc")
            assert r.status_code == 400
            assert r.json()["detail"]["error"] == "BAD_DAYS"

    def test_daily_ignores_days_even_when_unparsable(self, tmp_path: Path) -> None:
        """tf=D 忽略 days(對齊 docstring / D-15):壞 days 不該擋下日 K(M1)。"""
        client, fake = make_client(tmp_path)
        fake.bars_result = [self._bar("2026-07-27")]
        with client:
            r = client.get("/api/stock/bars/2330?tf=D&days=abc")
            assert r.status_code == 200
            assert r.json()["tf"] == "D"
            assert r.json()["bars"]

    def test_tc4_down_returns_empty_200(self, tmp_path: Path) -> None:
        """engine 層降級空(不是 502),但 status 要說出是斷線 —— 前端才分得出
        「TC4 掛了」與「這檔真的沒資料」,兩者原本收斂成同一句「無 K 線資料」。"""
        client, fake = make_client(tmp_path)

        def boom(code: str, tf: str, start_date: str, end_date: str) -> tuple[list, str]:
            raise ConnectionError("tc4 down")

        fake.fetch_bars_range = boom  # type: ignore[method-assign]
        with client:
            r = client.get("/api/stock/bars/2330?tf=D")
            assert r.status_code == 200
            assert r.json()["bars"] == []
            assert r.json()["status"] == "disconnected"

    def test_timeout_status_reaches_response(self, tmp_path: Path) -> None:
        """N-5:source 層 deadline 用滿 → `{"status": "timeout", "bars": []}`(SC-1)。"""
        client, fake = make_client(tmp_path)
        fake.bars_result = []
        fake.bars_status = "timeout"
        with client:
            r = client.get("/api/stock/bars/2330?tf=D")
            assert r.status_code == 200
            assert r.json()["status"] == "timeout"
            assert r.json()["bars"] == []

    def test_minute_response_carries_status(self, tmp_path: Path) -> None:
        """分 K 路徑同樣要帶 status(兩段合併後的最壞值)。"""
        client, fake = make_client(tmp_path)
        fake.bars_result = []
        fake.bars_status = "timeout"
        with client:
            r = client.get("/api/stock/bars/2330?tf=1&days=1")
            assert r.json()["status"] == "timeout"
