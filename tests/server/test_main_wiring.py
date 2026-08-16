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

from pathlib import Path
from typing import Any

import pytest
import uvicorn

import copycat.server.__main__ as main_mod
from copycat.server.app import (
    DEFAULT_BREADTH,
    DEFAULT_CORR,
    DEFAULT_FUTURES,
    DEFAULT_INDEX,
    DEFAULT_STOCK,
)
from copycat.server.verify import FAIL_ENV_KEY, FakeTxoSource
from copycat.trading_calendar import TradingCalendar


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
