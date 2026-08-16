"""server 測試的 hub 落點隔離(XR-3 SC-8)。

SignalHub 解耦後**恆建**(不再需要 stock engine 在場),而它的 `data_dir` 是
`wl_path.parent` —— 沒有顯式傳 `stock_watchlist_path` 的 app 測試會落在
`WATCHLIST_DEFAULT_PATH.parent` = repo 真 `data/`,在那裡生成 `signal_rules.json`,
訊號測試更會把 fake 訊號寫進 prod 的 `data/signals/*.jsonl` —— 而那份 jsonl 是
`/api/stock/signals/today` 的歷史真相源(前端斷線自癒的 baseline),被灌假訊號之後
prod 畫面上會多出從未發生過的訊號列,且隔日才自癒。

逐站點補傳 `stock_watchlist_path` 會散在 19 處且未來新測試靜默回歸,故在 conftest 層
一次隔離:`WATCHLIST_DEFAULT_PATH` 是 `app.py` 的模組級名、`create_app` 在 call time
才讀(`wl_path = ... else WATCHLIST_DEFAULT_PATH`),monkeypatch 得到;顯式傳路徑的
測試不受影響。沿 `tests/conftest.py` 既有「外部 IO 同型隔離」的 autouse 慣例。
"""

from __future__ import annotations

from pathlib import Path

import pytest

import copycat.server.app as _app_mod


@pytest.fixture(autouse=True)
def _isolate_watchlist_default_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_app_mod, "WATCHLIST_DEFAULT_PATH", tmp_path / "stock_watchlist.json")
