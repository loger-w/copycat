"""SC-1 真環境量測:連 ws://127.0.0.1:<port>/ws/txo-pnl(零推播流),記每則 `{"type":"ping"}` 到達間隔。

用法:python sc1_measure.py [port] [n_pings]
期望:連續 n 則 ping 間隔 10.0 ± 0.5 s。
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

import websockets


async def main(port: int, n: int) -> None:
    uri = f"ws://127.0.0.1:{port}/ws/txo-pnl"
    async with websockets.connect(uri) as ws:
        t_open = time.monotonic()
        last: float | None = None
        got = 0
        while got < n:
            raw = await asyncio.wait_for(ws.recv(), timeout=60)
            now = time.monotonic()
            msg = json.loads(raw)
            if isinstance(msg, dict) and msg.get("type") == "ping":
                got += 1
                gap = None if last is None else now - last
                print(f"ping #{got} t+{now - t_open:6.2f}s gap={'-' if gap is None else f'{gap:.2f}s'}", flush=True)
                last = now
            else:
                keys = sorted(msg.keys())[:4] if isinstance(msg, dict) else type(msg).__name__
                print(f"data   t+{now - t_open:6.2f}s keys={keys}", flush=True)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    asyncio.run(main(port, n))
