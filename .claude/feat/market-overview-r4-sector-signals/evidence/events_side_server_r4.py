"""R4 事件鏈取證 server:fake TXO + fake Stock(hub 得以 boot)+ verify fake breadth(FLIP)。

verify 模式本身沒有 stock engine → hub 恆 None → 廣度事件在 `--verify` 上到不了
(Phase 6 實測發現;design §8 的「verify 取證通道」漏了這一層)。本腳本補上
FakeStockSource 讓 SignalHub boot,廣度事件全鏈(diff → hub → jsonl/WS → 前端)
即可在盤後取證。

- signals jsonl 落隔離目錄(data_dir 跟著 stock_watchlist_path 走)— 零汙染真 data/
- breadth 落檔隔離 data/market-events-r4/
- port 8721(vite proxy 直通;prod 未跑時使用)
- 需 env VERIFY_BREADTH_FLIP=1(1101 依牆鐘 11 分週期鎖↔開)
"""

import logging
import pathlib
import sys
import tempfile

import uvicorn

REPO = pathlib.Path(r"C:\side-project\copycat")
sys.path.insert(0, str(REPO))

from copycat.server.app import create_app  # noqa: E402
from copycat.server.verify import (  # noqa: E402
    FakeTxoSource,
    fake_breadth_fetchers,
    neutralize_external_env,
)

sys.path.insert(0, str(REPO / "tests"))
from helpers.fake_sources import FakeStockSource  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

neutralize_external_env()

iso = pathlib.Path(tempfile.mkdtemp(prefix="r4-events-"))
print(f"isolated data dir: {iso}", flush=True)

app = create_app(
    FakeTxoSource(),
    stock_source=FakeStockSource(),
    stock_watchlist_path=iso / "stock_watchlist.json",  # jsonl 跟著落 iso/signals/
    breadth_fetchers=fake_breadth_fetchers(),
    breadth_data_dir=REPO / "data" / "market-events-r4",
)

uvicorn.run(app, host="127.0.0.1", port=8721)
