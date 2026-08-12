"""R4 側車 server(R3 樣板升五元組):fake TXO + 真 FinMind 五支 fetcher(含 chain)。

- 本輪在主 tree 開發(無 worktree),不需 sys.path 前置
- 真 token 以閉包綁進 fetcher(顯式注入路徑會拿 dummy token)
- neutralize_external_env() 壓制群益 / Discord
- 落檔隔離 data/market-sidecar-r4/(不碰 prod data/market/)
- port 8723(prod 8721 / verify 8722 錯開);全程零 TC4 / ZMQ
- 驗證面:/api/market/sector(rotation)/ /api/market/sector/members /
  /api/stock/signals/today(廣度事件,盤中 09:01+ 才有)
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

DATA_DIR = pathlib.Path(r"C:\side-project\copycat\data\market-sidecar-r4")


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
    # XR-3 後 SignalHub 恆建(不再需要 stock engine)→ 它的落點 = 自選檔所在目錄。
    # 不隔離的話這台側車會把真廣度事件寫進 prod 的 `data/signals/*.jsonl`,而那份是
    # breadth 對帳的 seed:被灌事件之後 prod 的真鎖板事件會被判成「已發布」而靜默不發。
    stock_watchlist_path=DATA_DIR / "stock_watchlist.json",
)

import os  # noqa: E402

uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("SIDECAR_PORT", "8723")))
