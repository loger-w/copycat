"""Phase 6 截圖用 fake-source server(零 ZMQ — 夜盤紀律)。port 8899。

worktree 直跑腳本必釘 sys.path(CLAUDE.md §8)。全部行情 source 皆 fake,
只為讓 rules CRUD routes + 前端規則 UI 有真 HTTP 後端可打。
"""

from __future__ import annotations

import sys

sys.path.insert(0, r"C:\side-project\copycat\.claude\worktrees\feat-discord-watchlist")

import tempfile
from collections.abc import Callable
from pathlib import Path

import uvicorn

from copycat.live.models import SeriesInfo, Tick
from copycat.server.app import create_app
from tests.helpers.fake_sources import (
    FakeCorrSource,
    FakeFuturesSource,
    FakeIndexSource,
    FakeStockSource,
)

assert create_app.__module__.startswith("copycat"), "import 錨點檢查"

SERIES = SeriesInfo(series_id="TX4.202608", name="TX4 202608", expiry="202608", contracts=())


class FakeQuoteSource:
    def list_series(self) -> list[SeriesInfo]:
        return [SERIES]

    def fetch_backfill(self, series: SeriesInfo) -> list[Tick]:
        return []

    def subscribe(self, series: SeriesInfo, on_tick: Callable[[Tick], None]) -> None: ...

    def unsubscribe(self, series: SeriesInfo) -> None: ...

    def close(self) -> None: ...


tmp = Path(tempfile.mkdtemp(prefix="signal-rules-shot-"))
app = create_app(
    FakeQuoteSource(),
    stock_source=FakeStockSource(),
    index_source=FakeIndexSource(),
    futures_source=FakeFuturesSource(),
    corr_source=FakeCorrSource(),
    stock_watchlist_path=tmp / "watchlist.json",
)

uvicorn.run(app, host="127.0.0.1", port=8899, log_level="warning")
