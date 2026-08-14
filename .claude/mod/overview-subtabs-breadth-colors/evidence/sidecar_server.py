"""overview-subtabs 側車 server(抄 R4 五元組樣板,僅改隔離目錄與預設 port)。

- 用途:Phase 6 UI 截圖(SC-1 家數字色 / SC-2 subtab)— 盤後 prod 未跑,佔 8721
  讓 vite proxy(寫死 8721)直通;截圖完即關,不留駐。
- 真 token 以閉包綁進 fetcher(顯式注入路徑會拿 dummy token)
- neutralize_external_env() 壓制群益 / Discord(ops-discipline:起真 create_app 必核)
- 落檔隔離 data/market-sidecar-overview-subtabs/(不碰 prod data/market/ 與 data/signals/)
- 全程零 TC4 / ZMQ
"""

import datetime as dt
import logging
import pathlib

import uvicorn

from copycat.server import breadth_fetch
from copycat.server.app import create_app
from copycat.server.verify import FakeTxoSource, neutralize_external_env

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

env = pathlib.Path(r"C:\side-project\copycat\.env").read_text(encoding="utf-8-sig")
TOKEN = [ln.split("=", 1)[1].strip() for ln in env.splitlines() if ln.startswith("FINMIND_TOKEN")][
    0
]

neutralize_external_env()

DATA_DIR = pathlib.Path(r"C:\side-project\copycat\data\market-sidecar-overview-subtabs")


def _snapshot(_token: str) -> list[dict]:
    return breadth_fetch.fetch_snapshot(TOKEN)


def _stock_info(_token: str) -> list[dict]:
    return breadth_fetch.fetch_stock_info(TOKEN)


def _disposition(_token: str, today: dt.date) -> list[dict]:
    return breadth_fetch.fetch_disposition(TOKEN, today)


def _daily(_token: str, day: dt.date) -> list[dict]:
    return breadth_fetch.fetch_daily_prices(TOKEN, day)


def _chain(_token: str) -> list[dict]:
    return breadth_fetch.fetch_industry_chain(TOKEN)


app = create_app(
    FakeTxoSource(),
    breadth_fetchers=(_snapshot, _stock_info, _disposition, _daily, _chain),
    breadth_data_dir=DATA_DIR,
    # SignalHub 恆建 → 落點必隔離,否則側車把事件寫進 prod data/signals/*.jsonl,
    # prod 真鎖板事件會被對帳判「已發布」而靜默不發(XR-3 C-1/W-1)。
    stock_watchlist_path=DATA_DIR / "stock_watchlist.json",
)

import os  # noqa: E402

uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("SIDECAR_PORT", "8721")))
