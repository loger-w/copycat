"""server 測試的 hub 落點隔離(XR-3 SC-8)。

SignalHub 解耦後**恆建**(不再需要 stock engine 在場),而它的 `data_dir` 是
`wl_path.parent` —— 沒有顯式傳 `stock_watchlist_path` 的 app 測試會落在
`WATCHLIST_DEFAULT_PATH.parent` = repo 真 `data/`,在那裡生成 `signal_rules.json`;
`test_breadth_routes` 那一系列更會經 attach 把 fake 鎖板事件寫進 prod 的
`data/signals/*.jsonl` —— 而那份 jsonl 是 breadth 對帳的 seed(`market_event_state`),
被灌假事件之後 prod 的真鎖板事件會被判成「已發布」而**靜默不發**。

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
