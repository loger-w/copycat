"""R4 真環境探針:各 WS 端點的握手結果 + 首則訊息 + ping 間隔。"""
import asyncio, json, sys, time
import websockets
from websockets.exceptions import InvalidStatus

async def probe(url: str, wait: float) -> str:
    t0 = time.monotonic()
    try:
        async with websockets.connect(url, open_timeout=5) as ws:
            msgs = []
            try:
                while time.monotonic() - t0 < wait:
                    raw = await asyncio.wait_for(ws.recv(), timeout=wait)
                    m = json.loads(raw)
                    msgs.append((round(time.monotonic() - t0, 2), m.get("type") or m.get("event") or "snapshot", list(m)[:4]))
            except (asyncio.TimeoutError, websockets.ConnectionClosed) as exc:
                msgs.append((round(time.monotonic() - t0, 2), f"end:{type(exc).__name__}", []))
            return f"ACCEPTED  {url}\n    " + "\n    ".join(f"t={t:>6}s {kind:<10} keys={keys}" for t, kind, keys in msgs)
    except InvalidStatus as exc:
        return f"REJECTED  {url}  HTTP {exc.response.status_code}  (t={time.monotonic()-t0:.2f}s)"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR     {url}  {type(exc).__name__}: {exc}"

async def main() -> None:
    port = sys.argv[1]
    wait = float(sys.argv[2])
    paths = sys.argv[3:]
    for p in paths:
        print(await probe(f"ws://127.0.0.1:{port}{p}", wait), flush=True)

asyncio.run(main())
