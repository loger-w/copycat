"""SC-3 real-env 取證側車:**真 TC4 corr / futures 引擎** + fake TXO + 外部 IO 中和。

前提(啟動前必查):prod :8721 **沒在跑**(`netstat -ano | findstr :8721` 空)— 否則同 symbol 跨
session 只推一邊,會搶走 prod 六腿推播(ops-discipline)。本輪 2026-08-17 20:2x 實查 8721/8722 皆空。
用 8721 的理由:vite proxy 寫死 8721(frontend/vite.config.ts:9),要截前端畫面只能占它;
取證完 **必 kill**,不留給 user 當 prod(branch tree 會被 merge 刪除)。

用法:.venv\\Scripts\\python .claude\\mod\\corr-nk225m-leg\\evidence\\corr_sidecar.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, r"C:\side-project\copycat")

import uvicorn

# ⚠ 必須在 create_app import 之前:壓制 CAPITAL_* / DISCORD_*(否則拿 .env 真憑證登入群益正式環境)
from copycat.server.verify import FakeTxoSource, fake_breadth_fetchers, neutralize_external_env

neutralize_external_env()

from copycat.server.app import DEFAULT_CORR, DEFAULT_FUTURES, create_app  # noqa: E402

assert create_app.__module__.startswith("copycat"), "import 錨點檢查"

DATA_DIR = Path(tempfile.mkdtemp(prefix="corr-nk225m-sidecar-"))

app = create_app(
    FakeTxoSource(),
    futures_source=DEFAULT_FUTURES,  # base 腿台指走 futures_engine(真 TC4)
    corr_source=DEFAULT_CORR,  # 六 + 一腿真 TC4 SUBQUOTE
    breadth_fetchers=fake_breadth_fetchers(),
    breadth_data_dir=DATA_DIR,
    stock_watchlist_path=DATA_DIR / "stock_watchlist.json",  # 隔離,不寫 prod data/
)

if __name__ == "__main__":
    print(f"sidecar data_dir={DATA_DIR}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=8721)
