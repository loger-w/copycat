"""SC-4 量測:/ws/txo-pnl 20 s 窗訊息數 / bytes,首則 series_id、連線存活、反向 GET 對照。"""
from __future__ import annotations
import asyncio, json, sys, time, urllib.request
import websockets

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8721
WINDOW = 20.0
EXCL = {"generated_at"}

def strip(d: dict) -> dict:
    out = {k: v for k, v in d.items() if k not in EXCL}
    t = dict(out.get("totals") or {})
    t.pop("dropped_foreign_ticks", None); t.pop("queue_dropped", None)
    out["totals"] = t
    return out

async def main() -> None:
    health = json.load(urllib.request.urlopen(f"http://localhost:{PORT}/api/health"))
    print("health:", health.get("git_sha"), health.get("status"))
    msgs: list[tuple[float, int, dict]] = []
    t0 = time.monotonic()
    async with websockets.connect(f"ws://localhost:{PORT}/ws/txo-pnl", max_size=None) as ws:
        first = json.loads(await asyncio.wait_for(ws.recv(), 5))
        msgs.append((0.0, len(json.dumps(first)), first))
        while time.monotonic() - t0 < WINDOW:
            try:
                raw = await asyncio.wait_for(ws.recv(), WINDOW - (time.monotonic() - t0))
            except asyncio.TimeoutError:
                break
            msgs.append((time.monotonic() - t0, len(raw), json.loads(raw)))
        still_open = ws.state.name if hasattr(ws, "state") else "?"
        get = json.load(urllib.request.urlopen(f"http://localhost:{PORT}/api/txo/snapshot"))
    total = sum(n for _, n, _ in msgs)
    print(f"first series_id={first.get('series_id')} status={first.get('status')} ticks={first.get('totals',{}).get('ticks')}")
    print(f"msgs in {WINDOW:.0f}s = {len(msgs)} (incl first)  bytes={total}  KB/s={total/WINDOW/1024:.2f}")
    for t, n, m in msgs[1:8]:
        print(f"  +{t:5.1f}s {n} B ticks={m.get('totals',{}).get('ticks')} gen={m.get('generated_at')}")
    dup = sum(1 for a, b in zip(msgs, msgs[1:]) if strip(a[2]) == strip(b[2]))
    print(f"consecutive identical (excl generated_at/dropped_foreign/queue_dropped) = {dup}")
    print(f"ws state at end = {still_open}")
    same = strip(get) == strip(msgs[-1][2])
    print(f"GET /api/txo/snapshot == last ws msg (excl set): {same}; "
          f"dropped_foreign first={first.get('totals',{}).get('dropped_foreign_ticks')} get={get.get('totals',{}).get('dropped_foreign_ticks')}")

asyncio.run(main())
