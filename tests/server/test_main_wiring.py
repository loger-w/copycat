"""`python -m copycat.server` 的正式啟動佈線(SC-3):四個 source 一律顯式 DEFAULT_*。

`__main__.py` 原本零測試覆蓋,而漏傳任一 sentinel 的失效樣態是「對應面板整段空白且
零錯誤訊號」(corr/river 尤其:引擎沒建起來與行情沒推播在畫面上長得一模一樣)。
故這裡直接斷言傳給 `create_app` 的 kwargs 集合本身,不只斷言個別鍵存在。

--verify 模式(chore server-launch-wrapper)同檔上鎖:fake source、env 壓制有跑、
port 錯開、不落 log 檔 —— 漏任一項的失效樣態都是「盤中驗證悄悄變成第二台真 server」。
"""

from __future__ import annotations

from typing import Any

import pytest
import uvicorn

import copycat.server.__main__ as main_mod
from copycat.server.app import DEFAULT_CORR, DEFAULT_FUTURES, DEFAULT_INDEX, DEFAULT_STOCK
from copycat.server.verify import FakeTxoSource


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

    def _count_prod_log(self) -> None:
        self.prod_log_calls += 1
        return None


def test_main_passes_explicit_default_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    cap = _Capture()
    cap.install(monkeypatch)

    main_mod.main([])

    assert cap.create_args == ()
    assert cap.create_kwargs == {
        "stock_source": DEFAULT_STOCK,
        "index_source": DEFAULT_INDEX,
        "futures_source": DEFAULT_FUTURES,
        "corr_source": DEFAULT_CORR,
    }
    # 明寫:trade 路已除役,sentinel 借用語意不得復活
    assert cap.create_kwargs is not None and "trade_source" not in cap.create_kwargs
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
    assert cap.create_kwargs == {}
    # env 壓制必須有跑、log 不落檔、port 與 prod 錯開
    assert cap.neutralized is True
    assert cap.prod_log_calls == 0
    assert cap.run_kwargs is not None and cap.run_kwargs["port"] == 8722


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
