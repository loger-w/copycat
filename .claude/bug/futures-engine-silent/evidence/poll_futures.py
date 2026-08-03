"""Trial poller: /api/futures/state + /api/corr/state 每 10s 一筆,記 seq 與各品 p。"""
import json, sys, time, urllib.request

label = sys.argv[1]
rounds = int(sys.argv[2])
out = open(f"{label}_poll.txt", "w", encoding="utf-8")


def get(path):
    with urllib.request.urlopen(f"http://127.0.0.1:8721{path}", timeout=8) as r:
        return json.load(r)


for i in range(rounds):
    stamp = time.strftime("%H:%M:%S")
    try:
        f = get("/api/futures/state")
        prods = " ".join(
            f"{p}:p={s['p']},t={s['t']}" for p, s in sorted(f["products"].items())
        )
        line = f"{stamp} futures seq={f['seq']} {prods}"
    except Exception as exc:  # noqa: BLE001 - 觀測腳本,任何失敗都要記下來繼續
        line = f"{stamp} futures ERROR {type(exc).__name__}: {exc}"
    try:
        c = get("/api/corr/state")
        base = c["legs"].get(c["base"], {})
        line += f" || corr seq={c['seq']} base_mid={base.get('mid')} stale={base.get('stale')}"
    except Exception as exc:  # noqa: BLE001
        line += f" || corr ERROR {type(exc).__name__}: {exc}"
    print(line, file=out, flush=True)
    time.sleep(10)
out.close()
