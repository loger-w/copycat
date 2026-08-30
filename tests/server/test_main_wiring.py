"""`python -m copycat.server` 的正式啟動佈線(SC-3):四個 source 一律顯式 DEFAULT_*。

`__main__.py` 原本零測試覆蓋,而漏傳任一 sentinel 的失效樣態是「對應面板整段空白且
零錯誤訊號」(corr/river 尤其:引擎沒建起來與行情沒推播在畫面上長得一模一樣)。
故這裡直接斷言傳給 `create_app` 的 kwargs 集合本身,不只斷言個別鍵存在。

--verify 模式(chore server-launch-wrapper)同檔上鎖:fake source、env 壓制有跑、
port 錯開、不落 log 檔 —— 漏任一項的失效樣態都是「盤中驗證悄悄變成第二台真 server」。

交易日曆(mod/trading-calendar SC-8)同理只在 prod 傳:verify 的 fake 資料綁牆鐘
today,傳真日曆會讓 verify server 在假日整片空 —— 而 prod 漏傳的失效樣態正是本輪
要根治的那一個(假日冷啟動全空圖、零錯誤訊號)。
"""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import pytest
import uvicorn

import copycat.server.__main__ as main_mod
from copycat.server import shutdown_budget
from copycat.server.app import (
    DEFAULT_BREADTH,
    DEFAULT_CORR,
    DEFAULT_FUTURES,
    DEFAULT_INDEX,
    DEFAULT_STOCK,
)
from copycat.server.verify import FAIL_ENV_KEY, FakeTxoSource
from copycat.trading_calendar import TradingCalendar
from tests.helpers.boot import BootedClient


class _Capture:
    def __init__(self) -> None:
        self.create_args: tuple[Any, ...] | None = None
        self.create_kwargs: dict[str, Any] | None = None
        self.run_kwargs: dict[str, Any] | None = None
        self.neutralized = False
        self.prod_log_calls = 0

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _fake_create_app(*args: Any, **kwargs: Any) -> object:
            self.create_args = args
            self.create_kwargs = kwargs
            return object()

        def _fake_run(*_a: Any, **kwargs: Any) -> None:
            self.run_kwargs = kwargs

        monkeypatch.setattr(main_mod, "create_app", _fake_create_app)
        monkeypatch.setattr(uvicorn, "run", _fake_run)
        # 佈線測試不得真的動 sys.stdout/stderr 或寫 logs/(prod 路徑才有,計數驗證)
        monkeypatch.setattr(main_mod, "_setup_prod_log", lambda: self._count_prod_log())
        monkeypatch.setattr(
            main_mod, "neutralize_external_env", lambda: setattr(self, "neutralized", True)
        )
        # 開發機 shell 可能 export 著 TXO_SERVER_PORT(正式設定 key),port 斷言要隔離
        # (review T-5;test_verify_port_env_override 自己 setenv 不受影響)
        monkeypatch.delenv("TXO_SERVER_PORT", raising=False)
        # 失效注入 key 同理隔離:operator 的 shell 留著它會讓 data_dir 斷言隨環境飄
        monkeypatch.delenv(FAIL_ENV_KEY, raising=False)

    def _count_prod_log(self) -> None:
        self.prod_log_calls += 1
        return None


def test_main_passes_explicit_default_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    cap = _Capture()
    cap.install(monkeypatch)

    main_mod.main([])

    assert cap.create_args == ()
    assert cap.create_kwargs is not None
    # 日曆是實例(不是 sentinel)→ 先抽出來單獨驗型別,其餘仍逐鍵鎖死整份 dict
    calendar = cap.create_kwargs.get("trading_calendar")
    assert isinstance(calendar, TradingCalendar), "prod 必須顯式載入交易日曆"
    assert {k: v for k, v in cap.create_kwargs.items() if k != "trading_calendar"} == {
        "stock_source": DEFAULT_STOCK,
        "index_source": DEFAULT_INDEX,
        "futures_source": DEFAULT_FUTURES,
        "corr_source": DEFAULT_CORR,
        # 家數帶(market-overview R2):prod 必須顯式 DEFAULT_BREADTH,漏傳 = 整條
        # FinMind 管線靜默不啟動而面板只寫「FinMind 未設定」(與真的沒設同形)
        "breadth_fetchers": DEFAULT_BREADTH,
    }
    # 明寫:trade 路已除役,sentinel 借用語意不得復活
    assert cap.create_kwargs is not None and "trade_source" not in cap.create_kwargs
    # 放寬窗只屬於 verify:prod 一律吃 configs/breadth.json(review C-2 的零改動要求)
    assert "breadth_config" not in cap.create_kwargs
    # prod:log 落檔有掛、env 壓制不得跑(真 server 要吃真憑證)、port canonical
    assert cap.prod_log_calls == 1
    assert cap.neutralized is False
    assert cap.run_kwargs is not None and cap.run_kwargs["port"] == 8721
    # 關機預算同源(A1):uvicorn 先等 WS 收攤才進 lifespan,那段要有上限,否則 run.ps1
    # 的 graceful 窗再怎麼算都可能整段被 WS drain 吃掉、lifespan 一步都輪不到
    assert cap.run_kwargs["timeout_graceful_shutdown"] == shutdown_budget.WS_DRAIN_SECS


def test_main_argv_defaults_to_sys_argv_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    """main() 無參數 = 讀 sys.argv(pytest 自己的 argv 不含 --verify → prod 路)。"""
    cap = _Capture()
    cap.install(monkeypatch)
    monkeypatch.setattr(main_mod.sys, "argv", ["copycat.server"])

    main_mod.main()

    assert cap.create_kwargs is not None and "stock_source" in cap.create_kwargs
    assert cap.neutralized is False


def test_verify_mode_fake_source_and_neutralize(monkeypatch: pytest.MonkeyPatch) -> None:
    cap = _Capture()
    cap.install(monkeypatch)

    main_mod.main(["--verify"])

    # fake source 單一位置參數;其餘 source 全部不傳(= None = 引擎不啟動、零 ZMQ)
    assert cap.create_args is not None and len(cap.create_args) == 1
    assert isinstance(cap.create_args[0], FakeTxoSource)
    # breadth 是唯一的例外:走 fake 四元組(不打真 FinMind)+ 獨立落檔目錄
    # ——共用 prod 的 data/market/ 會讓 fake 快照有機會蓋掉當日真序列
    assert cap.create_kwargs is not None and set(cap.create_kwargs) == {
        "breadth_fetchers",
        "breadth_data_dir",
        "breadth_config",
        "stock_watchlist_path",
    }
    assert len(cap.create_kwargs["breadth_fetchers"]) == 4
    assert cap.create_kwargs["breadth_data_dir"] == main_mod.VERIFY_DATA_DIR
    # SignalHub 解耦後(XR-3)verify server 也會建真 hub,而它的落點 = 自選檔所在目錄。
    # 不隔離的話 verify 進程會把 fake 訊號寫進 prod 的 `data/signals/*.jsonl` ——
    # 那份是 today 端點的歷史真相源(前端斷線自癒的 baseline),prod 畫面上會多出
    # 從未發生過的訊號列(review P0-3)。與 breadth_data_dir 同一條隔離原則。
    assert (
        cap.create_kwargs["stock_watchlist_path"]
        == main_mod.VERIFY_DATA_DIR / "stock_watchlist.json"
    )
    # 放寬窗(review C-2):prod 預設窗 09:00–13:40 之外 `_poll_loop` 只跑首圈 ——
    # 失效注入 / 家數序列第二格都要「第二輪之後」才看得到,而 verify server
    # 幾乎都在盤後跑,窗照抄 prod 等於整條取證路徑只剩一格
    config = cap.create_kwargs["breadth_config"]
    assert (config.window_start, config.window_end) == ("00:00", "23:59")
    # env 壓制必須有跑、log 不落檔、port 與 prod 錯開
    assert cap.neutralized is True
    assert cap.prod_log_calls == 0
    assert cap.run_kwargs is not None and cap.run_kwargs["port"] == 8722
    assert cap.run_kwargs["timeout_graceful_shutdown"] == shutdown_budget.WS_DRAIN_SECS


def test_verify_fail_injection_keeps_default_dir_and_clears_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`VERIFY_BREADTH_FAIL=1` → **落檔目錄不變**(`VERIFY_DATA_DIR`),且不清任何檔。

    專用 fail 目錄的唯一存在理由是「chain 快取檔跨 run 持久會吸收掉注入」,而 chain
    整條鏈已於 2026-08-16 刪除 —— 剩下的四支取數點沒有任何跨 run 落檔會吸收注入,
    分兩個目錄只會讓 verify 的家數序列在兩個目錄之間跳。落點隔離(不寫 prod)由
    `VERIFY_DATA_DIR` 本身保證,那條紀律不變。
    """
    cap = _Capture()
    cap.install(monkeypatch)
    leftover = tmp_path / "leftover.json"
    leftover.write_text("{}", encoding="utf-8")
    monkeypatch.setenv(FAIL_ENV_KEY, "1")

    main_mod.main(["--verify"])

    assert cap.create_kwargs is not None
    assert cap.create_kwargs["breadth_data_dir"] == main_mod.VERIFY_DATA_DIR
    # hub 落點跟著同一個目錄:只鎖 breadth_data_dir 的話,失效注入變體會把真 hub 的
    # jsonl 寫回 prod `data/signals/`(review P0-3)—— 那條隔離在本變體上也要成立
    assert (
        cap.create_kwargs["stock_watchlist_path"]
        == main_mod.VERIFY_DATA_DIR / "stock_watchlist.json"
    )
    assert leftover.exists()  # 開機清檔的行為已隨 chain 一併移除


def test_verify_without_fail_env_keeps_default_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """未注入失效 → 照舊用 `market-verify`(隔離目錄只服務注入那條路)。"""
    cap = _Capture()
    cap.install(monkeypatch)
    monkeypatch.delenv(FAIL_ENV_KEY, raising=False)

    main_mod.main(["--verify"])

    assert cap.create_kwargs is not None
    assert cap.create_kwargs["breadth_data_dir"] == main_mod.VERIFY_DATA_DIR


def test_verify_port_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    cap = _Capture()
    cap.install(monkeypatch)
    monkeypatch.setenv("TXO_SERVER_PORT", "9123")

    main_mod.main(["--verify"])

    assert cap.run_kwargs is not None and cap.run_kwargs["port"] == 9123


def test_unknown_arg_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    cap = _Capture()
    cap.install(monkeypatch)

    with pytest.raises(SystemExit):
        main_mod.main(["--verfy"])  # typo 不得靜默當 prod 起真連線

    assert cap.create_args is None and cap.create_kwargs is None
    # 順序合約:驗參數在落檔之前 —— 打錯字不得先換掉整個 process 的 stdio(review T-6)
    assert cap.prod_log_calls == 0


def test_verify_refuses_canonical_port(monkeypatch: pytest.MonkeyPatch) -> None:
    """run.ps1 會在 operator 的 shell 留下 TXO_SERVER_PORT=8721;verify server 佔住
    canonical port 的失效樣態是 vite proxy 打到整片 fake 而零錯誤訊號(review R-5)。"""
    cap = _Capture()
    cap.install(monkeypatch)
    monkeypatch.setenv("TXO_SERVER_PORT", "8721")

    with pytest.raises(SystemExit):
        main_mod.main(["--verify"])

    assert cap.create_args is None and cap.run_kwargs is None


def test_default_txo_source_wires_realtime_heal(monkeypatch: pytest.MonkeyPatch) -> None:
    """TXO 是唯一直接用基底 `TC4QuoteSource` 的 session,基底自癒預設全關 →
    `_default_source` 必須顯式開 R1(60s)+ 日/夜盤閘,否則 09:01 那種 reap 殺 key
    的事故 TXO 面永遠救不回(fix/tc4-realtime-refcount-kill)。"""
    import copycat.live.tc4 as tc4_mod
    from copycat.server import app as app_mod

    seen = _capture(monkeypatch, tc4_mod, "TC4QuoteSource")

    app_mod._default_source()

    assert seen["kwargs"]["heal"].silence_secs == tc4_mod.TXO_HEAL_SILENCE_SECS == 60.0
    assert seen["kwargs"]["heal"].symbol_silence_secs is None, "TXO R2 必須維持關(深價外契約 churn)"
    # 無日曆 = 逐字等於改動前的純牆鐘閘
    assert seen["kwargs"]["heal"].active is _session_mod().in_txo_session


# ---- C-5:自癒閘 AND 交易日曆(純牆鐘 → 假日整天 churn TC4 上游)----

_FRIDAY = date(2026, 8, 14)
_SATURDAY = date(2026, 8, 15)
_SUNDAY = date(2026, 8, 16)
_MONDAY = date(2026, 8, 17)
_TUESDAY = date(2026, 8, 18)
#: 假日表空 → 週末由 weekday() 擋、平日全開;閘的組合律用這一把就驗得完
_CAL = TradingCalendar(frozenset(), frozenset(), frozenset({2026}))
#: 週二(08-18)為國定假日的日曆:驗「跨午夜歸前一日」查的是假日表不只是 weekday
_CAL_TUE_HOLIDAY = TradingCalendar(frozenset({_TUESDAY}), frozenset(), frozenset({2026}))


def _at(d: date, hh: int, mm: int = 0, ss: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hh, mm, ss)


def _session_mod() -> Any:
    import copycat.live.session as session_mod

    return session_mod


def _capture(monkeypatch: pytest.MonkeyPatch, module: Any, name: str) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    class _CaptureSource:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            seen["args"] = args
            seen["kwargs"] = kwargs

    monkeypatch.setattr(module, name, _CaptureSource)
    return seen


@pytest.mark.parametrize("clock", [True, False])
def test_txo_heal_gate_ands_the_calendar(monkeypatch: pytest.MonkeyPatch, clock: bool) -> None:
    import copycat.live.tc4 as tc4_mod
    from copycat.server import app as app_mod

    seen = _capture(monkeypatch, tc4_mod, "TC4QuoteSource")
    monkeypatch.setattr(_session_mod(), "in_txo_session", lambda: clock)

    app_mod._default_source(_CAL)
    gate = seen["kwargs"]["heal"].active

    monkeypatch.setattr(app_mod, "_now", lambda: _at(_SATURDAY, 10))
    assert gate() is False, "非交易日不得自癒(整天每 5s 對 TC4 送 UNSUB+SUB)"
    monkeypatch.setattr(app_mod, "_now", lambda: _at(_TUESDAY, 10))
    assert gate() is clock, "交易日仍要 AND 牆鐘時段閘"


@pytest.mark.parametrize("clock", [True, False])
@pytest.mark.parametrize(
    ("factory", "clock_fn"),
    [
        ("_default_stock_source", "in_stock_heal_window_now"),  # 個股:13:35(試撮期仍有簿更新推播)
        ("_default_index_source", "in_index_heal_window_now"),  # 指數:13:25(試撮起指數不更新)
    ],
)
def test_stock_and_index_heal_gate_ands_the_calendar(
    monkeypatch: pytest.MonkeyPatch, factory: str, clock_fn: str, clock: bool
) -> None:
    """個股 / 指數的閘都走既有的 `in_trading_hours` 參數(健檢與自癒同一把),但牆鐘那半邊
    **各拿各的**(pr-126 F-01 per-consumer):只量了 IX0001 就一起關 13:25,個股會失去收盤集合
    競價期間 R1 / R2 / 健檢三條救援路。"""
    import copycat.live.stock_source as stock_mod
    from copycat.server import app as app_mod

    seen = _capture(monkeypatch, stock_mod, "StockQuoteSource")
    monkeypatch.setattr(stock_mod, clock_fn, lambda: clock)

    getattr(app_mod, factory)(_CAL)
    gate = seen["kwargs"]["in_trading_hours"]

    monkeypatch.setattr(app_mod, "_now", lambda: _at(_SATURDAY, 10))
    assert gate() is False
    monkeypatch.setattr(app_mod, "_now", lambda: _at(_TUESDAY, 10))
    assert gate() is clock, "交易日仍要 AND 盤中時段(盤外不得 churn)"


def test_stock_and_index_heal_gates_are_two_different_clocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """兩把牆鐘互不牽動:index 那把關著時個股那把仍開(13:25–13:35 正是這個形狀),反之亦然。
    失效樣態 = 有人把 index source 接回 `in_stock_heal_window_now`(或個股接到 index 那把),
    測試只 monkeypatch 其中一把就看不出來 —— 所以兩把同時各設相反值。"""
    import copycat.live.stock_source as stock_mod
    from copycat.server import app as app_mod

    seen = _capture(monkeypatch, stock_mod, "StockQuoteSource")
    monkeypatch.setattr(app_mod, "_now", lambda: _at(_TUESDAY, 10))

    monkeypatch.setattr(stock_mod, "in_stock_heal_window_now", lambda: True)
    monkeypatch.setattr(stock_mod, "in_index_heal_window_now", lambda: False)
    app_mod._default_stock_source(_CAL)
    assert seen["kwargs"]["in_trading_hours"]() is True
    app_mod._default_index_source(_CAL)
    assert seen["kwargs"]["in_trading_hours"]() is False

    monkeypatch.setattr(stock_mod, "in_stock_heal_window_now", lambda: False)
    monkeypatch.setattr(stock_mod, "in_index_heal_window_now", lambda: True)
    app_mod._default_stock_source(_CAL)
    assert seen["kwargs"]["in_trading_hours"]() is False
    app_mod._default_index_source(_CAL)
    assert seen["kwargs"]["in_trading_hours"]() is True


@pytest.mark.parametrize("clock", [True, False])
def test_futures_heal_gate_ands_the_calendar(monkeypatch: pytest.MonkeyPatch, clock: bool) -> None:
    """期貨閘 = 交易日曆 AND 盤別(原本是 always → 13:45–15:00 / 05:00–08:45 整段空 churn)。"""
    import copycat.live.futures_source as futures_mod
    from copycat.server import app as app_mod

    seen = _capture(monkeypatch, futures_mod, "FuturesQuoteSource")
    monkeypatch.setattr(futures_mod, "in_futures_session_now", lambda: clock)

    app_mod._default_futures_source(_CAL)
    gate = seen["kwargs"]["heal"].active

    monkeypatch.setattr(app_mod, "_now", lambda: _at(_SATURDAY, 10))
    assert gate() is False, "非交易日不得自癒"
    monkeypatch.setattr(app_mod, "_now", lambda: _at(_TUESDAY, 10))
    assert gate() is clock, "交易日仍要 AND 盤別(盤外不得 churn)"


class TestHealGateAcrossMidnight:
    """B9:凌晨(hour < 6)屬前一日那一場 —— 閘要查**場別起始日**,不是牆鐘今天。

    改動前用 `_today()`:週六 01:00 查週六 → False(週五夜盤該救不救);
    週一 01:00 查週一 → True 但週一凌晨根本沒夜盤(週日無場)→ 整段空 churn。
    """

    def test_saturday_predawn_belongs_to_friday_session(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from copycat.server import app as app_mod

        monkeypatch.setattr(app_mod, "_now", lambda: _at(_SATURDAY, 1))
        assert app_mod._heal_gate(_CAL, lambda: True)() is True

    def test_monday_predawn_belongs_to_sunday_and_is_closed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from copycat.server import app as app_mod

        monkeypatch.setattr(app_mod, "_now", lambda: _at(_MONDAY, 1))
        assert app_mod._heal_gate(_CAL, lambda: True)() is False

    def test_predawn_after_a_holiday_evening_is_closed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 週三 01:00 → 場別起始日 = 週二;週二放假 → 前一晚沒有夜盤
        from copycat.server import app as app_mod

        monkeypatch.setattr(app_mod, "_now", lambda: _at(date(2026, 8, 19), 1))
        assert app_mod._heal_gate(_CAL_TUE_HOLIDAY, lambda: True)() is False

    @pytest.mark.parametrize(
        ("when", "expected", "why"),
        [
            (_at(_FRIDAY, 23, 0), True, "週五夜盤進行中(場別起始日 = 週五,交易日)"),
            (_at(_SATURDAY, 23, 0), False, "週六晚上沒有夜盤(場別起始日 = 週六)"),
            (_at(_SUNDAY, 1, 0), False, "週日凌晨 = 週六那一場"),
            (_at(_MONDAY, 8, 50), True, "週一日盤開盤後(場別起始日 = 週一)"),
        ],
    )
    def test_cross_midnight_table(
        self, monkeypatch: pytest.MonkeyPatch, when: datetime, expected: bool, why: str
    ) -> None:
        """N015:跨午夜表補四格 —— 兩個週末邊界 + 一個夜盤中 + 一個日盤開盤。

        現存三格(週六 01:00 / 週一 01:00 / 假日隔日凌晨)**全部落在 `hour == 1`**,
        對門檻的另一半零覆蓋:把 `hour < 6` 寫成 `hour < 24`(= 恆歸前一日)三格照樣
        全綠,而週一 08:50 會退成週日 → 開盤後該救不救,零錯誤訊號。
        """
        from copycat.server import app as app_mod

        monkeypatch.setattr(app_mod, "_now", lambda: when)
        assert app_mod._heal_gate(_CAL, lambda: True)() is expected, why

    def test_session_date_switches_at_six(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """門檻對稱案:05:59 仍屬前一場、06:00 起算當日(不經 AND,直接看取樣)。"""
        from copycat.server import app as app_mod

        monkeypatch.setattr(app_mod, "_now", lambda: _at(_SATURDAY, 5, 59))
        assert app_mod._session_date() == _FRIDAY
        monkeypatch.setattr(app_mod, "_now", lambda: _at(_SATURDAY, 6, 0))
        assert app_mod._session_date() == _SATURDAY


class TestHealGateThresholdCoversSessionClose:
    """不變式:`hour < 6` 的門檻 ⊇ 夜盤收盤 + 各自的寬放(閘不會先於牆鐘關掉)。

    clock 用真函式但**顯式傳入同一時刻** —— prod 有兩個獨立取樣點(`app._now` 與
    `session.datetime.now()`),測試裡只能人工對齊,不能假裝它們是同一個。
    """

    def test_futures_pad_five_minutes_still_inside_previous_session_date(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import copycat.live.futures_source as futures_mod
        from copycat.server import app as app_mod

        monkeypatch.setattr(app_mod, "_now", lambda: _at(_SATURDAY, 5, 5))
        gate = app_mod._heal_gate(_CAL, lambda: futures_mod.in_futures_session_now(time(5, 5)))
        assert gate() is True, "05:05 仍在期貨寬放內,且屬週五那一場"

    def test_futures_gate_closes_by_the_clock_not_by_the_date(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import copycat.live.futures_source as futures_mod
        from copycat.server import app as app_mod

        monkeypatch.setattr(app_mod, "_now", lambda: _at(_SATURDAY, 5, 6))
        # 拆腿:先釘死日期腿為**真**,False 才只能來自牆鐘腿。少了這兩條,`_session_date`
        # 若退化成牆鐘今天(週六、非交易日),日期腿也是 False —— 整案照樣綠,
        # 而「閘由誰關掉」正是本案唯一要鎖的東西。
        assert app_mod._session_date() == _FRIDAY
        assert _CAL.is_trading_day(app_mod._session_date()) is True
        gate = app_mod._heal_gate(_CAL, lambda: futures_mod.in_futures_session_now(time(5, 6)))
        assert gate() is False, "寬放外由牆鐘閘關掉(日期仍是週五交易日)"

    def test_txo_gate_closes_right_after_five(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from copycat.server import app as app_mod

        session_mod = _session_mod()
        monkeypatch.setattr(app_mod, "_now", lambda: _at(_SATURDAY, 5, 0))
        assert app_mod._heal_gate(_CAL, lambda: session_mod.in_txo_session(time(5, 0)))() is True
        monkeypatch.setattr(app_mod, "_now", lambda: _at(_SATURDAY, 5, 0, 30))
        assert (
            app_mod._heal_gate(_CAL, lambda: session_mod.in_txo_session(time(5, 0, 30)))() is False
        )


def test_corr_source_keeps_the_always_on_session_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """海外腿(SGX/CBOT/CME)在台灣假日照開 → corr 的 **session 級**閘不接日曆
    (接了等於整天不自癒)。逐腿的閘走 `heal.symbol_active`,見下一條。"""
    import copycat.live.corr_source as corr_mod
    from copycat.corr_config import DEFAULT_CONFIG
    from copycat.server import app as app_mod

    seen = _capture(monkeypatch, corr_mod, "CorrQuoteSource")

    app_mod._default_corr_source(config=DEFAULT_CONFIG)

    from copycat.live.tc4 import always_active

    assert seen["kwargs"]["heal"].active is always_active  # session 級閘維持預設全開


def test_corr_sparse_legs_come_from_the_config_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """稀疏腿豁免(R2)由設定檔 `sparse` 帶到 watchdog;與時段閘正交(SXF 兩邊都掛:
    休市段由閘擋、日盤由 sparse 擋)。config **必填**(pr-120 F-04):source 的稀疏腿集合與 engine
    的腿組要吃同一份,由型別守 —— 傳 repo 設定檔則 SXF 必在。"""
    import copycat.live.corr_source as corr_mod
    from copycat.corr_config import DEFAULT_CONFIG, CorrConfig, Leg, load_config
    from copycat.server import app as app_mod

    seen = _capture(monkeypatch, corr_mod, "CorrQuoteSource")
    app_mod._default_corr_source(config=load_config())
    assert seen["kwargs"]["heal"].sparse_symbols == frozenset(
        {"TC.F.TWF.SXF.HOT", "TC.F.CFE.VX.HOT"}
    )  # 08-28 VX 加 sparse(事前標該變)

    seen = _capture(monkeypatch, corr_mod, "CorrQuoteSource")
    no_sparse = CorrConfig(
        legs=tuple(Leg(leg.key, leg.label, leg.symbol, leg.source) for leg in DEFAULT_CONFIG.legs),
        base=DEFAULT_CONFIG.base,
    )
    app_mod._default_corr_source(_CAL, config=no_sparse)
    assert seen["kwargs"]["heal"].sparse_symbols == frozenset()


@pytest.mark.parametrize("clock", [True, False])
def test_corr_leg_gate_only_applies_to_the_taifex_segment(
    monkeypatch: pytest.MonkeyPatch, clock: bool
) -> None:
    """N051:台期交段的腿(SXF/UDF/SPF/UNF,與台指同時段同結算)吃「交易日曆 AND
    盤別」;SGX / CME / CBOT / OSE 段恆 True(時段未實測,猜錯 = 該救的腿整場不救)。"""
    import copycat.live.corr_source as corr_mod
    import copycat.live.futures_source as futures_mod
    from copycat.corr_config import DEFAULT_CONFIG
    from copycat.server import app as app_mod

    seen = _capture(monkeypatch, corr_mod, "CorrQuoteSource")
    monkeypatch.setattr(futures_mod, "in_futures_session_now", lambda: clock)

    app_mod._default_corr_source(_CAL, config=DEFAULT_CONFIG)
    gate = seen["kwargs"]["heal"].symbol_active

    monkeypatch.setattr(app_mod, "_now", lambda: _at(_SATURDAY, 10))
    assert gate("TC.F.TWF.SXF.HOT") is False, "非交易日的台期交腿不得 churn"
    assert gate("TC.F.CME.NQ.HOT") is True, "海外段在台灣假日照開,不得被日曆關掉"
    monkeypatch.setattr(app_mod, "_now", lambda: _at(_TUESDAY, 10))
    assert gate("TC.F.TWF.SXF.HOT") is clock, "交易日仍要 AND 盤別"
    assert gate("TC.F.SGX.TWN.HOT") is True


@pytest.mark.parametrize("clock", [True, False])
def test_corr_tws_leg_gate_ands_the_calendar_with_the_stock_session(
    monkeypatch: pytest.MonkeyPatch, clock: bool
) -> None:
    """F4:台積電現貨腿 `TC.S.TWS.2330` 吃「交易日曆 AND **個股日盤**」。

    沿用個股 session 那把 `in_stock_heal_window_now`(不另立第二張時段表)。不接閘的失效
    樣態是整個夜盤每 240 s 一發 UNSUB+SUB —— 現貨 13:30 就收盤了,那些重掛救不到任何
    推播,只是把 TC4 上游的 refcount 反覆掀一遍。
    """
    import copycat.live.corr_source as corr_mod
    import copycat.live.futures_source as futures_mod
    import copycat.live.stock_source as stock_mod
    from copycat.corr_config import DEFAULT_CONFIG
    from copycat.server import app as app_mod

    seen = _capture(monkeypatch, corr_mod, "CorrQuoteSource")
    monkeypatch.setattr(stock_mod, "in_stock_heal_window_now", lambda: clock)
    # 台期交那把恆開 → 證明兩把閘各走各的,不是共用同一個 callable
    monkeypatch.setattr(futures_mod, "in_futures_session_now", lambda: True)

    app_mod._default_corr_source(_CAL, config=DEFAULT_CONFIG)
    gate = seen["kwargs"]["heal"].symbol_active

    monkeypatch.setattr(app_mod, "_now", lambda: _at(_SATURDAY, 10))
    assert gate("TC.S.TWS.2330") is False, "非交易日的現貨腿不得 churn"
    monkeypatch.setattr(app_mod, "_now", lambda: _at(_TUESDAY, 10))
    assert gate("TC.S.TWS.2330") is clock, "交易日仍要 AND 個股日盤時段"
    assert gate("TC.F.TWF.SXF.HOT") is True, "台期交腿不受個股閘影響"
    assert gate("TC.F.CME.CL.HOT") is True, "海外段仍恆 True"


def test_create_app_passes_the_calendar_into_every_default_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """接線點在 `create_app` 內:factory 收得到日曆才有意義,漏傳的失效樣態是
    「假日照樣 churn」—— 只有 TC4 那頭的 log 看得出來,我方零訊號。"""
    from copycat.server import app as app_mod

    seen: dict[str, Any] = {}

    def _txo(calendar: Any = None) -> Any:
        seen["txo"] = calendar
        return FakeTxoSource()

    def _none(key: str) -> Any:
        def _factory(calendar: Any = None) -> Any:
            seen[key] = calendar
            return None  # 引擎不建 → 不碰 ZMQ

        return _factory

    monkeypatch.setattr(app_mod, "_default_source", _txo)
    monkeypatch.setattr(app_mod, "_default_stock_source", _none("stock"))
    monkeypatch.setattr(app_mod, "_default_index_source", _none("index"))
    monkeypatch.setattr(app_mod, "_default_futures_source", _none("futures"))

    app = app_mod.create_app(
        stock_source=DEFAULT_STOCK,
        index_source=DEFAULT_INDEX,
        futures_source=DEFAULT_FUTURES,
        stock_watchlist_path=tmp_path / "stock_watchlist.json",
        trading_calendar=_CAL,
    )
    with BootedClient(app):
        pass

    assert seen == {"txo": _CAL, "stock": _CAL, "index": _CAL, "futures": _CAL}
