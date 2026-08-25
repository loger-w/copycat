"""真 uvicorn + 真 lifespan 的關機 lane 量測(mod/shutdown-budget SC-1)。

零 TC4 / 零 ZMQ / 零群益:fake source(`neutralize_external_env` 先於 create_app),
port 0 隨機、自選檔落 scratchpad 隔離目錄(ops-discipline:非 prod create_app 必傳
`stock_watchlist_path`)。

形狀:stock close 睡 `SLOW`、index close 睡 `SLOW`、txo 即時。序列版收尾 ≥ 2 × SLOW,
並行 lane 版 ≈ SLOW。輸出「關機收尾」彙總行與 `should_exit` → thread join 的牆鐘。

用法(worktree 內直跑腳本必須把 repo root 插到 sys.path[0],否則 import 到主 tree 的 code):
    .venv\\Scripts\\python .claude/mod/shutdown-budget/evidence/shutdown_lanes_probe.py
"""

from __future__ import annotations

import logging
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT))

from copycat.server.verify import neutralize_external_env  # noqa: E402

neutralize_external_env()

import uvicorn  # noqa: E402

from copycat.server.app import create_app  # noqa: E402
from copycat.server.shutdown_budget import WS_DRAIN_SECS  # noqa: E402
from tests.helpers.fake_sources import FakeIndexSource, FakeStockSource  # noqa: E402
from tests.helpers.fake_txo import FakeTxoSource  # noqa: E402

SLOW = 2.0


class _SleepyStock(FakeStockSource):
    def close(self) -> None:
        print(f"[probe] stock close enter t={time.monotonic() - T0:.2f}s", flush=True)
        time.sleep(SLOW)
        print(f"[probe] stock close exit  t={time.monotonic() - T0:.2f}s", flush=True)


class _SleepyIndex(FakeIndexSource):
    def close(self) -> None:
        print(f"[probe] index close enter t={time.monotonic() - T0:.2f}s", flush=True)
        time.sleep(SLOW)
        print(f"[probe] index close exit  t={time.monotonic() - T0:.2f}s", flush=True)


class _InstantTxo(FakeTxoSource):
    def close(self) -> None:
        print(f"[probe] txo close t={time.monotonic() - T0:.2f}s", flush=True)


T0 = time.monotonic()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    data_dir = Path(tempfile.mkdtemp(prefix="copycat-shutdown-probe-"))
    app = create_app(
        source=_InstantTxo(),
        stock_source=_SleepyStock(),
        index_source=_SleepyIndex(),
        stock_watchlist_path=data_dir / "stock_watchlist.json",
        throttle_secs=0.01,
    )
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=0,
        log_level="info",
        timeout_graceful_shutdown=WS_DRAIN_SECS,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="uvicorn", daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "uvicorn 沒起來"
    port = server.servers[0].sockets[0].getsockname()[1]
    for _ in range(200):
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ready", timeout=2) as resp:
            if b'"ready":true' in resp.read().replace(b" ", b""):
                break
        time.sleep(0.05)
    else:
        raise AssertionError("boot 沒就緒")
    print(f"[probe] ready on :{port}; sending should_exit", flush=True)
    global T0
    T0 = time.monotonic()
    server.should_exit = True
    thread.join(timeout=60)
    wall = time.monotonic() - T0
    print(
        f"[probe] shutdown wall = {wall:.2f}s (SLOW={SLOW}s; 序列版 >= {2 * SLOW:.1f}s, 並行版 ≈ {SLOW:.1f}s)"
    )
    print(f"[probe] thread alive after join = {thread.is_alive()}")
    ok = not thread.is_alive() and wall < 2 * SLOW
    print(f"[probe] RESULT = {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
