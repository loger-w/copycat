"""啟動窗(HTTP 已開、引擎還在起)的行為合約(mod/startup-http-window)。

lifespan 的 `yield` 之前只做「便宜且必要」的三件事(build 身分 / banner / 建 runtime),
整段引擎啟動序列改跑在背景 task —— uvicorn 因此在亞秒級開始 serve,而不是等 TXO 全鏈
回補跑完(prod 分鐘級)。窗內的對外形狀 = 既有「引擎降級」形狀(503 NOT_READY /
WS close),不是新狀態。

這一組釘住四件事:窗真的開著、關機中斷 boot 不洩漏、runtime 起不來只降級 txo 面、
序列本體拋例外要留下痕跡(背景化把它從 fail-loud 變 fail-silent)。
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import copycat.server.app as app_mod
from copycat.live.models import SeriesInfo
from copycat.server.app import create_app
from tests.helpers.boot import wait_boot
from tests.helpers.fake_sources import (
    FakeCorrSource,
    FakeFuturesSource,
    FakeIndexSource,
    FakeStockSource,
)
from tests.helpers.fake_txo import SERIES, FakeTxoSource

#: fake 的阻塞上限。測試一律自己放行,這只是「忘了放行」時不要把整套測試掛死的保險。
_GATE_CAP = 15.0


class BlockingTxoSource(FakeTxoSource):
    """`list_series` 卡在 gate 上 —— 那是 `runtime.start` 的第一個 to_thread,也就是
    prod 啟動最貴的那一段(TXO 全鏈回補)在測試裡的替身。

    `entered` 是同步點:沒有它,測試無從分辨「boot 卡在這裡」與「boot 一行都還沒跑」
    (`create_task` 只是排程)或「boot 早就跑完了」—— 後兩者會讓中斷路徑一次都沒執行
    而測試照樣綠。
    """

    def __init__(self) -> None:
        self.gate = threading.Event()
        self.entered = threading.Event()
        self.closed = False

    def list_series(self) -> list[SeriesInfo]:
        self.entered.set()
        self.gate.wait(_GATE_CAP)
        return [SERIES]

    def close(self) -> None:
        self.closed = True


class BlockingBackfillTxoSource(FakeTxoSource):
    """`fetch_backfill` 卡在 gate 上 —— 交接協定裡真正貴的那一段(prod 全鏈分鐘級)。

    `list_series` 照常回,所以窗內 `/api/txo/series` 已經看得到序列 → 前端按得下去,
    而初始交接還沒完 —— select 與 boot 中的交接並發共用 `_buffer` 的那個窗。
    """

    def __init__(self) -> None:
        self.gate = threading.Event()
        self.entered = threading.Event()

    def fetch_backfill(self, series: SeriesInfo) -> list:
        self.entered.set()
        self.gate.wait(_GATE_CAP)
        return []


class FailingTxoSource(FakeTxoSource):
    """`list_series` 直接拋 —— runtime start 的執行期失敗(D2)。"""

    def __init__(self) -> None:
        self.closed = False

    def list_series(self) -> list[SeriesInfo]:
        raise RuntimeError("TC4 沒開")

    def close(self) -> None:
        self.closed = True


class BlockingSubscribeStockSource(FakeStockSource):
    """`subscribe_symbol` 卡在 gate 上 —— 自選回填(`_start_stock` 的第二段)會走到它,
    而那一步是 `asyncio.to_thread`,loop 仍能收下 cancel。

    卡在 `set_trade_date` 反而不行:那一步同步跑在 loop 上,整條 loop 都會停住,
    cancel 根本送不進去(boot 會在 gate 放行後照常跑完,中斷路徑一次都沒執行)。
    """

    def __init__(self) -> None:
        super().__init__()
        self.gate = threading.Event()
        self.entered = threading.Event()
        self.closed = False

    def subscribe_symbol(self, code: str) -> None:
        self.entered.set()
        self.gate.wait(_GATE_CAP)
        super().subscribe_symbol(code)

    def close(self) -> None:
        self.closed = True


def _watchlist(tmp_path: Path, codes: list[str]) -> Path:
    path = tmp_path / "watchlist.json"
    path.write_text(
        '{"codes": %s, "groups": []}' % str(codes).replace("'", '"'), encoding="utf-8"
    )
    return path


class TestBootWindowIsOpen:
    def test_lifespan_yields_before_boot_completes(self, tmp_path: Path) -> None:
        """窗開著:boot 還卡在 TXO 那段時,HTTP 面必須已經在服務。

        裸 `TestClient`(刻意不用 `BootedClient`)—— 這條要驗的正是「不等就緒也進得去」。

        **stock source 必須注入**:不注入的話 `/api/stock/watchlist` 恆 503(engine 從頭
        到尾都是 None),那個 503 反映的是「沒 source」不是「還在窗內」—— 斷言看起來
        對、實際上不鑑別。注入之後才有 503 → 200 的翻轉可比。
        """
        fake = BlockingTxoSource()
        app = create_app(
            fake,
            stock_source=FakeStockSource(),
            stock_watchlist_path=_watchlist(tmp_path, []),
            throttle_secs=0.01,
        )
        client = TestClient(app, raise_server_exceptions=False)
        t0 = time.monotonic()
        with client:
            entered_secs = time.monotonic() - t0
            assert entered_secs < 2.0, (
                f"進 context 花了 {entered_secs:.1f}s:lifespan 仍在等引擎起完"
            )
            assert fake.entered.wait(5), "boot 沒真的跑到 list_series,窗態斷言不算數"

            assert app.state.boot_done is False
            assert client.get("/api/health").status_code == 200, "build 身分在窗內必須答得出來"
            assert client.get("/api/txo/series").status_code == 503
            # stock 排在 TXO runtime 之後 → 窗內尚未輪到,與注入的 source 無關
            assert client.get("/api/stock/watchlist").status_code == 503

            # **exit 之前必須放行**:阻塞點跑在 loop 的預設 executor,`__exit__` 會
            # `shutdown_default_executor()` join 它(3.13 上限 300s),之後才放行 = 卡死
            fake.gate.set()
            wait_boot(app)
            assert app.state.boot_done is True
            assert app.state.boot_error is None
            assert client.get("/api/txo/snapshot").status_code == 200
            # 翻轉對照:同一條 route 在窗外變 200 → 上面那個 503 確實只出自「窗內」
            assert client.get("/api/stock/watchlist").status_code == 200


class TestShutdownDuringBoot:
    def test_shutdown_during_boot_closes_started(self) -> None:
        """關機中斷 boot 不得洩漏已建好的 source(SC-3)。"""
        fake = BlockingTxoSource()
        app = create_app(fake, throttle_secs=0.01)
        with TestClient(app, raise_server_exceptions=False):
            assert fake.entered.wait(5), "boot 沒卡在 list_series,中斷路徑不會被執行"
            # 放行必須落在 `__exit__` 阻塞期間 → 只能由別的執行緒定時放(見上一條註解)
            threading.Timer(0.2, fake.gate.set).start()

        assert fake.closed is True, "runtime.close 恆做(source 必須關掉)"
        # 鑑別證據:cancel 路徑不設 boot_done。少了它,「Timer 先放行 → boot 正常跑完
        # → 走正常反序 close」也會讓 fake.closed 成立,中斷路徑一次都沒驗到
        assert app.state.boot_done is False, "關機中的 server 不得宣告就緒"
        assert app.state.stock is None
        # index / corr 的 None 斷言已刪:這個 app 根本沒注入那兩個 source,值與 cancel
        # 無關(恆 None),留著只會讓人以為中斷路徑多驗了兩件事

    def test_boot_cancel_closes_inflight_engine(self, tmp_path: Path) -> None:
        """中斷點落在某個引擎的 `_boot` 內時,已建好的物件也要關掉。

        `_boot` 的 `except Exception` 接不到 `CancelledError` —— 少了那條分支,這裡
        洩漏的是一條已連線的 TC4 session,而畫面上只看得到 503。
        """
        fake = BlockingSubscribeStockSource()
        app = create_app(
            FakeTxoSource(),
            stock_source=fake,
            stock_watchlist_path=_watchlist(tmp_path, ["2330"]),
            throttle_secs=0.01,
        )
        with TestClient(app, raise_server_exceptions=False):
            assert fake.entered.wait(5), "boot 沒卡在 stock 的自選回填上"
            threading.Timer(0.2, fake.gate.set).start()

        assert fake.closed is True, "cancel 時已建好的 stock source 必須關掉"
        # 鑑別:引擎從未掛上 app.state → 這個 close 只可能出自 `_boot` 的 cancel 分支,
        # 不可能是 lifespan finally 的正常反序(那條讀的是 record,而 record 沒被寫)
        assert app.state.stock is None


class TestRuntimeStartFailureDegrades:
    def test_runtime_start_failure_degrades_not_crash(self, tmp_path: Path) -> None:
        """TXO runtime 起不來只降級 txo 面,其餘引擎照起(D2,🔴 行為改動)。

        現況是 lifespan 例外 → server 整台起不來:達錢 4 沒開的早上,個股 / 指數 /
        群益全部跟著陪葬。
        """
        fake = FailingTxoSource()
        stock = FakeStockSource()
        app = create_app(
            fake,
            stock_source=stock,
            stock_watchlist_path=_watchlist(tmp_path, []),
            throttle_secs=0.01,
        )
        with TestClient(app, raise_server_exceptions=False) as client:
            wait_boot(app)
            # 受控降級 ≠ 序列中止:error 必須是 null,否則 `wait_boot` 的 loud 語意
            # 會被這條常見狀況灌成雜訊
            assert app.state.boot_error is None
            assert client.get("/api/txo/series").status_code == 503
            assert client.get("/api/stock/watchlist").status_code == 200


class TestSelectDuringHandover:
    def test_select_during_handover_returns_503(self) -> None:
        """交接進行中的 select 回 503 HANDOVER_BUSY,交接完成後同請求 200(SC-4)。

        窗開了之後這條才變得可達:`runtime.start` 已填 `_series` → `/api/txo/series`
        回得出清單 → 前端按得下去,而初始交接還在跑。`activate` 沒有重入 guard 時,
        第二個交接會與第一個共用 `_buffer`(engine.py 的 F1 註解警告的正是這件事)。
        """
        fake = BlockingBackfillTxoSource()
        app = create_app(fake, throttle_secs=0.01)
        client = TestClient(app, raise_server_exceptions=False)
        with client:
            assert fake.entered.wait(5), "初始交接沒卡在回補上,並發窗不存在"
            assert client.get("/api/txo/series").status_code == 200, (
                "序列還沒列出的話,前端根本按不下 select —— 這條測的窗不成立"
            )
            r = client.post("/api/txo/select", json={"series_id": SERIES.series_id})
            assert r.status_code == 503
            assert r.json()["detail"]["error"] == "HANDOVER_BUSY"

            # **不用 Timer**:測試執行緒在兩次 POST 之間是自由的,預先 arm 反而會在慢
            # 機器上讓第一次 POST 晚於放行 → 拿 200 假紅(Timer 協定只適用「放行時機
            # 必須落在 __exit__ 阻塞期間」的那兩條)
            fake.gate.set()
            wait_boot(app)
            again = client.post("/api/txo/select", json={"series_id": SERIES.series_id})
            assert again.status_code == 200, "交接完成後同一個請求必須成功"


class TestReadyProbe:
    """`/api/ready` = 就緒的唯一對外管道(D4)。

    刻意**不動 `/api/health`**:它的 docstring 明文「不含引擎健康度」,build 身分要在
    引擎全壞時也答得出來 —— 混進就緒狀態會讓「這台是哪一版」在最需要它的時候失效。
    """

    def test_ready_flips_false_to_true(self) -> None:
        fake = BlockingTxoSource()
        app = create_app(fake, throttle_secs=0.01)
        client = TestClient(app, raise_server_exceptions=False)
        with client:
            assert fake.entered.wait(5), "boot 沒真的在跑,窗內 false 不算數"
            assert client.get("/api/ready").json() == {"ready": False, "error": None}

            fake.gate.set()  # 放行必須在 exit 之前(見 TestBootWindowIsOpen 的註解)
            wait_boot(app)
            assert client.get("/api/ready").json() == {"ready": True, "error": None}

    def test_ready_reports_boot_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """序列未走完即中止:ready 仍是 true(序列結束了),但 error 必須有值。

        兩欄合起來才分得出「正常起完」與「起到一半炸了」—— 只有 ready 的話,最壞的
        失效樣態(後續引擎全部靜默不啟動)在 probe 上看起來一切正常。
        """

        def _boom(*_a: object, **_k: object) -> object:
            raise RuntimeError("watchlist service 建構炸了")

        monkeypatch.setattr(app_mod, "WatchlistService", _boom)
        app = create_app(
            FakeTxoSource(),
            stock_source=FakeStockSource(),
            stock_watchlist_path=_watchlist(tmp_path, []),
            throttle_secs=0.01,
        )
        with TestClient(app, raise_server_exceptions=False) as client:
            wait_boot(app, allow_error=True)
            body = client.get("/api/ready").json()
            assert body["ready"] is True
            assert body["error"] is not None
            assert "watchlist service 建構炸了" in body["error"]


class TestBootSequenceException:
    def test_boot_sequence_exception_surfaces_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`_boot` 傘**外**的一步拋(此處 `WatchlistService` 建構)必須留下痕跡。

        背景化之前這種例外會炸掉 lifespan(fail-loud);背景化之後沒有頂層 catch 的話,
        後續引擎全部靜默不啟動而 server 看起來一切正常 —— 最壞的失效樣態。
        """

        def _boom(*_a: object, **_k: object) -> object:
            raise RuntimeError("watchlist service 建構炸了")

        monkeypatch.setattr(app_mod, "WatchlistService", _boom)
        app = create_app(
            FakeTxoSource(),
            stock_source=FakeStockSource(),
            stock_watchlist_path=_watchlist(tmp_path, []),
            throttle_secs=0.01,
        )
        with TestClient(app, raise_server_exceptions=False) as client:
            wait_boot(app, allow_error=True)
            assert app.state.boot_done is True, "序列結束(雖不完整)仍算結束"
            assert app.state.boot_error is not None
            assert "watchlist service 建構炸了" in app.state.boot_error
            # 後續引擎未啟動 = 既有降級形狀
            assert client.get("/api/index/state").status_code == 503


class _OrderedCloseTxoSource(FakeTxoSource):
    """close 時記一筆順序戳(TC4 session 的 UNSUB + Disconnect 在這一步)。"""

    def __init__(self, order: list[str]) -> None:
        self._order = order

    def close(self) -> None:
        self._order.append("txo")


class _OrderedCloseStockSource(FakeStockSource):
    def __init__(self, order: list[str]) -> None:
        super().__init__()
        self._order = order

    def close(self) -> None:
        self._order.append("stock")


class _FakeCapital:
    """CapitalClient 的最小替身:`close()` 是同步的 COM 執行緒 join(prod ≤5 s)。"""

    def __init__(self, order: list[str]) -> None:
        self._order = order

    def set_broadcast(self, cb: object) -> None:
        pass

    def start(self, loop: object) -> None:
        pass

    def close(self) -> None:
        self._order.append("capital")


def test_capital_com_teardown_runs_after_the_tc4_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """N049:關機時 TC4 的 UNSUB + `Disconnect()` 必須排在**群益 COM 執行緒 join 之前**。

    09:00:49 那次事故的形狀:uvicorn 已開始 graceful shutdown,但 lifespan 還沒跑到
    sources 的 `close()` 就被 `run.ps1` 的 `taskkill /T /F` 收掉 —— TC4 那頭直到 60 s
    後 `ExecuteCheckPingTime` reap 才 `RemoveLoginInfo`,而 reap 會把那條殭屍 session
    獨持的 key 歸零、連帶把 symbol 的上游 feed 帶走(新 server 開頭 ~60 s 零推播)。

    `capital.close()` 是同步 join(prod ≤5 s),排在 TC4 前面等於在關機預算最前面挖掉
    一塊。它與 index / stock / runtime 之間**沒有依賴**(corr→futures、signals→stock
    那兩條才有),所以這裡刻意違反「一律照建立的反序收」——理由就是這條時間預算。
    """
    order: list[str] = []
    monkeypatch.setattr(
        app_mod.capital_factory, "get_capital", lambda: _FakeCapital(order)
    )
    app = create_app(
        source=_OrderedCloseTxoSource(order),
        stock_source=_OrderedCloseStockSource(order),
        stock_watchlist_path=tmp_path / "stock_watchlist.json",
    )
    with TestClient(app):
        wait_boot(app)
    assert order.index("capital") > order.index("stock"), "群益 COM join 擋在 stock 前面"
    assert order.index("capital") > order.index("txo"), "群益 COM join 擋在 TXO runtime 前面"


class _GatedCloseStockSource(FakeStockSource):
    """`close()` 卡在 gate 上 —— TC4 半死時那條 session 的 UNSUB / LOGOUT 撞 RCVTIMEO
    (10 s)的替身。`entered` 是同步點:放行必須落在「它真的卡住之後」,否則別的 lane
    在它進門前就收完,並行與序列在 order 上長得一樣。"""

    def __init__(self, order: list[str]) -> None:
        super().__init__()
        self._order = order
        self.gate = threading.Event()
        self.entered = threading.Event()

    def close(self) -> None:
        self._order.append("stock:enter")
        self.entered.set()
        self.gate.wait(_GATE_CAP)
        self._order.append("stock:exit")


class _OrderedCloseIndexSource(FakeIndexSource):
    def __init__(self, order: list[str]) -> None:
        super().__init__()
        self._order = order

    def close(self) -> None:
        self._order.append("index")


class _OrderedCloseFuturesSource(FakeFuturesSource):
    def __init__(self, order: list[str]) -> None:
        super().__init__()
        self._order = order

    def close(self) -> None:
        self._order.append("futures")


class _OrderedCloseCorrSource(FakeCorrSource):
    def __init__(self, order: list[str]) -> None:
        super().__init__()
        self._order = order

    def close(self) -> None:
        self._order.append("corr")


class _RaisingCloseTxoSource(FakeTxoSource):
    def __init__(self, order: list[str]) -> None:
        self._order = order

    def close(self) -> None:
        self._order.append("txo:raise")
        raise RuntimeError("TXO source close 炸了")


class TestShutdownLanes:
    """A1(review #105 §2.6 S1):TC4 session 的 close 走**並行 lane**,不再序列。

    序列版的失效樣態:一條 session 卡在 REQ timeout(10 s)上,排在它後面的健康 session
    連 UNSUB 都輪不到就被 run.ps1 硬殺 —— 健康的也被還原成殭屍(下一台開頭 ~60 s
    零推播)。並行之後硬殺只落在真的卡住的那一條。
    """

    def test_stuck_stock_close_does_not_delay_the_txo_and_index_sessions(
        self, tmp_path: Path
    ) -> None:
        order: list[str] = []
        stock = _GatedCloseStockSource(order)
        app = create_app(
            source=_OrderedCloseTxoSource(order),
            stock_source=stock,
            index_source=_OrderedCloseIndexSource(order),
            stock_watchlist_path=tmp_path / "stock_watchlist.json",
            throttle_secs=0.01,
        )

        def _release() -> None:
            # 放行必須落在 `__exit__` 阻塞期間(同檔 TestShutdownDuringBoot 的協定),且
            # 要在 stock 真的卡住**之後**再給其他 lane 一段時間 —— 序列版在這段時間內
            # 什麼都不會發生,並行版的 txo / index 早就收完了
            assert stock.entered.wait(_GATE_CAP), "stock close 沒進門"
            time.sleep(0.3)
            stock.gate.set()

        releaser = threading.Thread(target=_release, daemon=True)
        with TestClient(app):
            wait_boot(app)
            releaser.start()
        releaser.join(_GATE_CAP)

        assert "stock:exit" in order, "stock close 沒跑完(gate 沒放行?)"
        assert order.index("txo") < order.index("stock:exit"), (
            f"TXO session 排在卡住的 stock 後面等(序列 close):{order}"
        )
        assert order.index("index") < order.index("stock:exit"), (
            f"index session 排在卡住的 stock 後面等:{order}"
        )

    def test_lane_depth_matches_the_real_shutdown_shape(self, tmp_path: Path) -> None:
        """`shutdown_budget.TC4_LANE_DEPTH` 不能只是自證的 `== 2`(review SP4):五條 session
        全部卡住時,**同時進場**的條數 = 5 − depth + 1(串鏈裡只有頭一條進得來)。第三個引擎
        被串進 corr lane、或串鏈被拆掉,這裡都會紅。"""
        from copycat.server.shutdown_budget import TC4_LANE_DEPTH

        gates = {name: threading.Event() for name in ("corr", "futures", "index", "stock", "txo")}
        entered = {name: threading.Event() for name in gates}

        def _block(name: str) -> None:
            entered[name].set()
            gates[name].wait(_GATE_CAP)

        class _Txo(FakeTxoSource):
            def close(self) -> None:
                _block("txo")

        class _Stock(FakeStockSource):
            def close(self) -> None:
                _block("stock")

        class _Index(FakeIndexSource):
            def close(self) -> None:
                _block("index")

        class _Futures(FakeFuturesSource):
            def close(self) -> None:
                _block("futures")

        class _Corr(FakeCorrSource):
            def close(self) -> None:
                _block("corr")

        app = create_app(
            source=_Txo(),
            stock_source=_Stock(),
            index_source=_Index(),
            futures_source=_Futures(),
            corr_source=_Corr(),
            stock_watchlist_path=tmp_path / "stock_watchlist.json",
            throttle_secs=0.01,
        )
        seen: dict[str, object] = {}

        def _observe() -> None:
            # 只等四條 lane 頭;對 futures 也 wait 的話會吃滿 _GATE_CAP,那時 corr 的 gate 同樣
            # 到期放行,futures 就真的進場了 —— 首版正是這樣假紅
            heads = [n for n in gates if n != "futures" and entered[n].wait(_GATE_CAP)]
            seen["heads"] = len(heads)
            time.sleep(0.2)  # 給 futures「不該進場」一段可被證偽的時間
            seen["futures_before_corr_released"] = entered["futures"].is_set()
            gates["corr"].set()
            seen["futures_after_corr_released"] = entered["futures"].wait(_GATE_CAP)
            for name in gates:
                gates[name].set()

        observer = threading.Thread(target=_observe, daemon=True)
        with TestClient(app):
            wait_boot(app)
            observer.start()
        observer.join(_GATE_CAP)

        sessions = len(gates)
        assert seen["heads"] == sessions - TC4_LANE_DEPTH + 1, seen
        assert seen["futures_before_corr_released"] is False, "futures 沒等 corr 就進場(串鏈被拆)"
        assert seen["futures_after_corr_released"] is True, "corr 放行後 futures 沒進場"

    def test_corr_still_closes_before_futures(self, tmp_path: Path) -> None:
        """並行 lane 內唯一保留的串鏈:corr 讀 `futures.state()`,必須先於 futures 收
        (app.py 既有不變式;並行化不得把它拆掉)。"""
        order: list[str] = []
        app = create_app(
            FakeTxoSource(),
            futures_source=_OrderedCloseFuturesSource(order),
            corr_source=_OrderedCloseCorrSource(order),
            stock_watchlist_path=tmp_path / "stock_watchlist.json",
            throttle_secs=0.01,
        )
        with TestClient(app):
            wait_boot(app)
        assert order.index("corr") < order.index("futures"), order

    def test_txo_close_failure_does_not_skip_capital(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """`runtime.close()` 原本是反序 close 裡**唯一裸 await** 的一段:拋了就跳過 capital
        (COM 執行緒不 join)。lifespan 註解宣稱的「各自 try/except 續行」白名單本來就該
        涵蓋它。"""
        order: list[str] = []
        monkeypatch.setattr(app_mod.capital_factory, "get_capital", lambda: _FakeCapital(order))
        app = create_app(
            source=_RaisingCloseTxoSource(order),
            stock_watchlist_path=tmp_path / "stock_watchlist.json",
            throttle_secs=0.01,
        )
        # 改動前 lifespan 把 TXO close 的例外整個拋出來 —— 這條要紅的正是那件事,
        # 所以例外本身不是斷言對象(capital 有沒有收才是)
        with contextlib.suppress(Exception):
            with TestClient(app, raise_server_exceptions=False):
                wait_boot(app)
        assert "txo:raise" in order
        assert "capital" in order, "TXO close 拋例外讓 capital 的 COM join 被跳過"

    def test_shutdown_summary_names_every_segment(
        self, caplog: pytest.LogCaptureFixture, tmp_path: Path
    ) -> None:
        """「console 印哪段吃掉時間」(review A1):收尾一行彙總各段耗時。run.ps1 超時
        訊息指的就是這一行 —— 少了它,「15 s 內未結束」永遠零指向。"""
        order: list[str] = []
        app = create_app(
            source=_OrderedCloseTxoSource(order),
            stock_source=_OrderedCloseStockSource(order),
            stock_watchlist_path=tmp_path / "stock_watchlist.json",
            throttle_secs=0.01,
        )
        with caplog.at_level(logging.INFO, logger="copycat.server.app"):
            with TestClient(app):
                wait_boot(app)
        summaries = [r.getMessage() for r in caplog.records if "關機收尾" in r.getMessage()]
        assert len(summaries) == 1, summaries
        for segment in ("stock", "txo"):
            assert segment in summaries[0], f"彙總行漏了 {segment} 段:{summaries[0]}"
