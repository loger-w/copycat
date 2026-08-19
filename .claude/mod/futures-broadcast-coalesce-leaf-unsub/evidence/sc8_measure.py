"""SC-8 量測:/ws/futures 20 s 窗 per-product 則數 / seq gap / bytes;GET state seq 對照。"""
from __future__ import annotations
import asyncio, json, sys, time, urllib.request
from collections import Counter
import websockets

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8721
WINDOW = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0

async def main() -> None:
    health = json.load(urllib.request.urlopen(f"http://localhost:{PORT}/api/health"))
    print("health:", health.get("git_sha"))
    n = 0; nbytes = 0; per = Counter(); gaps = 0; last_seq = None; first_seq = None
    t0 = time.monotonic(); gap_ms: list[float] = []; last_t = t0
    async with websockets.connect(f"ws://localhost:{PORT}/ws/futures", max_size=None) as ws:
        while time.monotonic() - t0 < WINDOW:
            try:
                raw = await asyncio.wait_for(ws.recv(), WINDOW - (time.monotonic() - t0))
            except asyncio.TimeoutError:
                break
            now = time.monotonic(); gap_ms.append((now - last_t) * 1000); last_t = now
            m = json.loads(raw); n += 1; nbytes += len(raw); per[m.get("product")] += 1
            s = m.get("seq")
            if first_seq is None: first_seq = s
            if last_seq is not None and s != last_seq + 1: gaps += 1
            last_seq = s
        state = json.load(urllib.request.urlopen(f"http://localhost:{PORT}/api/futures/state"))
        st = ws.state.name if hasattr(ws, "state") else "?"
    print(f"msgs in {WINDOW:.0f}s = {n}  bytes={nbytes}  KB/s={nbytes/WINDOW/1024:.2f}  per-product={dict(per)}")
    print(f"seq first={first_seq} last={last_seq} gaps={gaps}; GET state seq={state.get('seq')} (>= last ws seq: {state.get('seq') is not None and last_seq is not None and state['seq'] >= last_seq})")
    if gap_ms[1:]:
        g = sorted(gap_ms[1:]); print(f"inter-msg gap ms: min={g[0]:.1f} p50={g[len(g)//2]:.1f} max={g[-1]:.1f}")
    print(f"ws state at end = {st}")

asyncio.run(main())
