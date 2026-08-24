"""headless Chrome(visible 分頁、timer 不節流)下量 N035 閒置零誤重連 + N038 stall 後 jitter。"""
import asyncio, json, sys, time, urllib.request, threading
import websockets

DEVTOOLS = "http://127.0.0.1:9333"
PATCH = r"""(() => {
  const Orig = window.WebSocket; window.__wsLog = []; window.__wsT0 = Date.now();
  const stamp = () => new Date().toISOString().slice(11, 23);
  function Patched(url, protocols) {
    const ws = protocols === undefined ? new Orig(url) : new Orig(url, protocols);
    const path = String(url).replace(/^ws:\/\/[^/]+/, "");
    window.__wsLog.push({ t: stamp(), ev: "new", path });
    ws.addEventListener("open", () => window.__wsLog.push({ t: stamp(), ev: "open", path }));
    ws.addEventListener("close", () => window.__wsLog.push({ t: stamp(), ev: "close", path }));
    return ws;
  }
  Patched.prototype = Orig.prototype; Object.assign(Patched, { CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3 });
  window.WebSocket = Patched;
  const ow = console.warn; window.__warnLog = [];
  console.warn = (...a) => { window.__warnLog.push({ t: stamp(), msg: String(a[0]) }); ow.apply(console, a); };
  return "patched " + stamp() + " visibility=" + document.visibilityState;
})()"""
DUMP = "JSON.stringify({now:new Date().toISOString().slice(11,23), visibility: document.visibilityState, ws: window.__wsLog, warns: window.__warnLog})"

def stall(secs: int) -> None:
    req = urllib.request.Request(f"http://127.0.0.1:8899/_fake/stall?secs={secs}", method="POST")
    urllib.request.urlopen(req, timeout=secs + 30).read()

async def main() -> None:
    idle_s, stall_s, after_s = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    pages = json.loads(urllib.request.urlopen(DEVTOOLS + "/json").read())
    page = next(p for p in pages if p["type"] == "page")
    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=None) as cdp:
        mid = 0
        async def ev(expr: str) -> str:
            nonlocal mid
            mid += 1
            await cdp.send(json.dumps({"id": mid, "method": "Runtime.evaluate", "params": {"expression": expr, "returnByValue": True}}))
            while True:
                m = json.loads(await cdp.recv())
                if m.get("id") == mid:
                    return m["result"]["result"].get("value")
        print("url:", page["url"], "|", await ev(PATCH), flush=True)
        await asyncio.sleep(idle_s)
        print("IDLE", await ev(DUMP), flush=True)
        t = threading.Thread(target=stall, args=(stall_s,), daemon=True)
        print(f"STALL start {time.strftime('%H:%M:%S')} secs={stall_s}", flush=True)
        t.start()
        await asyncio.sleep(stall_s + after_s)
        print("AFTER", await ev(DUMP), flush=True)

asyncio.run(main())
