"""R3 側車 server(R2 樣板改四元組):fake TXO + 真 FinMind 四支 fetcher。

- worktree code 優先(sys.path.insert 教訓)
- 真 token 以閉包綁進 fetcher(顯式注入路徑會拿 dummy token)
- neutralize_external_env() 壓制群益 / Discord
- 落檔隔離 data/market-sidecar-r3/(不碰 prod data/market/)
- port 8723(prod 8721 / verify 8722 皆錯開);全程零 TC4 / ZMQ
"""

import sys

WT = r"C:\side-project\copycat\.claude\worktrees\market-overview-r3-limit-list"
sys.path.insert(0, WT)

import datetime as dt
import logging
import pathlib

import uvicorn

from copycat.server import breadth_fetch
from copycat.server.app import create_app
from copycat.server.verify import FakeTxoSource, neutralize_external_env

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
)

env = pathlib.Path(r"C:\side-project\copycat\.env").read_text(encoding="utf-8-sig")
TOKEN = [
    ln.split("=", 1)[1].strip()
    for ln in env.splitlines()
    if ln.startswith("FINMIND_TOKEN")
][0]

neutralize_external_env()

DATA_DIR = pathlib.Path(r"C:\side-project\copycat\data\market-sidecar-r3")


def _snapshot(_token: str) -> list[dict]:
    return breadth_fetch.fetch_snapshot(TOKEN)


def _stock_info(_token: str) -> list[dict]:
    return breadth_fetch.fetch_stock_info(TOKEN)


def _disposition(_token: str, today: dt.date) -> list[dict]:
    return breadth_fetch.fetch_disposition(TOKEN, today)


def _daily(_token: str, day: dt.date) -> list[dict]:
    return breadth_fetch.fetch_daily_prices(TOKEN, day)


app = create_app(
    FakeTxoSource(),
    breadth_fetchers=(_snapshot, _stock_info, _disposition, _daily),
    breadth_data_dir=DATA_DIR,
)

uvicorn.run(app, host="127.0.0.1", port=8723)
