"""refactor/bars-cache-daily-entry 真實環境對照側車(零 TC4 / 零 ZMQ,ops-discipline 盤中安全)。

用法:python sidecar_bars.py <repo_root> <port>
兩台各自錨定不同 repo root(主樹 master vs worktree),同一組日 K / 週 K / 月 K 請求 diff 回應。
"""

from __future__ import annotations

import sys

ROOT = sys.argv[1]
PORT = int(sys.argv[2])
sys.path.insert(0, ROOT)

import datetime as _dt
import json
import tempfile
from pathlib import Path

import uvicorn

# ⚠ 必須在 create_app 之前:壓制 CAPITAL_* / DISCORD_* / FINMIND(ops-discipline)
from copycat.server.verify import FakeTxoSource, neutralize_external_env

neutralize_external_env()

import copycat.server.bars as bars_mod
from copycat.server.app import create_app
from tests.helpers.fake_sources import (
    FakeCorrSource,
    FakeFuturesSource,
    FakeIndexSource,
    FakeStockSource,
)

loaded = Path(bars_mod.__file__).resolve()
assert str(loaded).startswith(str(Path(ROOT).resolve())), f"import 錨點錯:{loaded}"
print(f"bars.py loaded from: {loaded}", flush=True)
print(f"has _DailyEntry: {hasattr(bars_mod, '_DailyEntry')}", flush=True)


def dbar(t: str, c: int) -> dict:
    return {"t": t, "o": c, "h": c + 10, "l": c - 10, "c": c, "v": 100}


today = _dt.date.today()
days = [today - _dt.timedelta(days=n) for n in (4, 3, 2, 1, 0)]
stock = FakeStockSource()
stock.bars_result = [dbar(d.isoformat(), 1000 + i) for i, d in enumerate(days)]

tmp = Path(tempfile.mkdtemp(prefix=f"bars-sidecar-{PORT}-"))
wl_path = tmp / "watchlist.json"
wl_path.write_text(json.dumps({"codes": ["2330"], "groups": []}), encoding="utf-8")

app = create_app(
    FakeTxoSource(),
    stock_source=stock,
    index_source=FakeIndexSource(
        daily_bars=[dbar(d.isoformat(), 23_000 + i) for i, d in enumerate(days)]
    ),
    futures_source=FakeFuturesSource(),
    corr_source=FakeCorrSource(),
    stock_watchlist_path=wl_path,
)
uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
