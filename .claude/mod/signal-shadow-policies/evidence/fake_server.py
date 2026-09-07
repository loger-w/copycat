"""spec #192 盤後可驗取證用 fake-source 側車 server(零 TC4 / 零 ZMQ — ops-discipline)。port 8899。

改自 `.claude/mod/trial-pause-badge/evidence/fake_server.py`,差別:
  1. sys.path 錨點**自我定位**到本檔所在的 repo root(review F-05:worktree 收掉後寫死路徑會炸),import 檢查
     斷言 create_app 來自同一棵樹。
  2. 用途 = (a) `GET /api/stock/signals/rules` 在**舊版 v1 規則檔**(複製自 prod `data/signal_rules.json`,
     落在 tmp 隔離目錄,不碰 prod)上多出「掃單簇」且 CDP 穿越 / 爆量通知關;(b) 啟動 log 有
     「T+1/T+2 回填」起動一行;(c) 前端規則視窗截圖(vite preview 以 evidence/vite.sidecar.config.ts proxy 到 8899)。
  3. 自選檔含「記憶體」群組 + 「盤前篩選」群組(政策族群解析的形狀)。

跑法(任一棵樹的 root):`PYTHONUTF8=1 .venv python .claude/mod/signal-shadow-policies/evidence/fake_server.py`
"""

from __future__ import annotations

import sys
from pathlib import Path

# 本檔在 <repo>/.claude/mod/signal-shadow-policies/evidence/ → parents[4] = repo root(深度已實跑驗證)
_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT))

import json
import logging
import shutil
import tempfile
from collections.abc import Callable

import uvicorn

# ⚠ 必須在 create_app 之前:壓制 CAPITAL_* / DISCORD_* / FINMIND(漏了會拿 .env 真憑證登入群益正式環境)
from copycat.server.verify import neutralize_external_env

neutralize_external_env()

from copycat.live.models import SeriesInfo, Tick
from copycat.server.app import create_app
from tests.helpers.fake_sources import (
    FakeCorrSource,
    FakeFuturesSource,
    FakeIndexSource,
    FakeStockSource,
)

assert create_app.__module__.startswith("copycat"), "import 錨點檢查"
assert Path(sys.modules["copycat.server.app"].__file__ or "").resolve().is_relative_to(_REPO_ROOT), (
    "create_app 必須來自本檔所在的那棵樹(venv 是 editable 主 tree,sys.path[0] 要先蓋過它)"
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

SERIES = SeriesInfo(series_id="TX4.202609", name="TX4 202609", expiry="202609", contracts=())


class FakeQuoteSource:
    def list_series(self) -> list[SeriesInfo]:
        return [SERIES]

    def fetch_backfill(self, series: SeriesInfo) -> list[Tick]:
        return []

    def subscribe(self, series: SeriesInfo, on_tick: Callable[[Tick], None]) -> None: ...

    def unsubscribe(self, series: SeriesInfo) -> None: ...

    def close(self) -> None: ...


tmp = Path(tempfile.mkdtemp(prefix="signal-shadow-evidence-"))
wl_path = tmp / "watchlist.json"
wl_path.write_text(
    json.dumps(
        {
            "codes": ["2330", "2344", "2408", "6715"],
            "groups": [
                {"name": "記憶體", "codes": ["2330", "2344", "2408"]},
                {"name": "盤前篩選", "codes": ["6715"]},
            ],
        },
        ensure_ascii=False,
    ),
    encoding="utf-8",
)
# 舊版(v1)規則檔 = prod 檔的副本(唯讀複製到隔離目錄;hub 載入走 v1→v2→v3→v4 遷移鏈,不回寫)
shutil.copy(r"C:\side-project\copycat\data\signal_rules.json", tmp / "signal_rules.json")
print(f"data dir: {tmp}", flush=True)

app = create_app(
    FakeQuoteSource(),
    stock_source=FakeStockSource(),
    index_source=FakeIndexSource(),
    futures_source=FakeFuturesSource(),
    corr_source=FakeCorrSource(),
    stock_watchlist_path=wl_path,
)

uvicorn.run(app, host="127.0.0.1", port=8899, log_level="info")
