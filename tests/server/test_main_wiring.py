"""`python -m copycat.server` 的正式啟動佈線(SC-3):四個 source 一律顯式 DEFAULT_*。

`__main__.py` 原本零測試覆蓋,而漏傳任一 sentinel 的失效樣態是「對應面板整段空白且
零錯誤訊號」(corr/river 尤其:引擎沒建起來與行情沒推播在畫面上長得一模一樣)。
故這裡直接斷言傳給 `create_app` 的 kwargs 集合本身,不只斷言個別鍵存在。
"""

from __future__ import annotations

from typing import Any

import pytest
import uvicorn

import copycat.server.__main__ as main_mod
from copycat.server.app import DEFAULT_CORR, DEFAULT_FUTURES, DEFAULT_INDEX, DEFAULT_STOCK


def test_main_passes_explicit_default_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def _fake_create_app(*args: Any, **kwargs: Any) -> object:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(main_mod, "create_app", _fake_create_app)
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: None)

    main_mod.main()

    assert captured["args"] == ()
    assert captured["kwargs"] == {
        "stock_source": DEFAULT_STOCK,
        "index_source": DEFAULT_INDEX,
        "futures_source": DEFAULT_FUTURES,
        "corr_source": DEFAULT_CORR,
    }
    # 明寫:trade 路已除役,sentinel 借用語意不得復活
    assert "trade_source" not in captured["kwargs"]
