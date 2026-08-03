"""Bug 1 重現嘗試:反覆冷啟動 server,記錄 futures 三品是否有推播。

每輪:hard kill(模擬「TC4 session 殘留」候選條件)→ 等 → 起 server → 觀察 90s
→ 記 futures 各品 p 與 log 中的 subscribe 失敗/leaf fallback 告警。
結束時 server 保持執行(user 需要)。
"""

import json
import subprocess
import time
import urllib.request
from pathlib import Path

REPO = Path(r"C:\side-project\copycat")
PY = REPO / ".venv" / "Scripts" / "python.exe"
HERE = Path(__file__).resolve().parent
TRIALS = 4
OBSERVE_SECS = 90

report = open(HERE / "restart_trials.txt", "w", encoding="utf-8")


def log(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, file=report, flush=True)


def kill_server() -> None:
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
         "Where-Object { $_.CommandLine -like '*copycat.server*' } | "
         "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
        capture_output=True,
    )


def futures_state():
    with urllib.request.urlopen("http://127.0.0.1:8721/api/futures/state", timeout=8) as r:
        return json.load(r)


for trial in range(1, TRIALS + 1):
    log(f"===== trial {trial} =====")
    kill_server()
    time.sleep(10)
    logpath = HERE / f"trial{trial + 1}_restart.log"
    fh = open(logpath, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        [str(PY), "-m", "copycat.server"], cwd=str(REPO), stdout=fh, stderr=subprocess.STDOUT
    )
    log(f"started pid={proc.pid} log={logpath.name}")
    deadline = time.time() + OBSERVE_SECS
    last = None
    while time.time() < deadline:
        time.sleep(10)
        try:
            last = futures_state()
        except Exception as exc:  # noqa: BLE001 - 觀測腳本
            log(f"  poll error {type(exc).__name__}")
            continue
        silent = sorted(p for p, s in last["products"].items() if s["p"] is None)
        log(f"  seq={last['seq']} silent={silent or 'none'}")
        if not silent and last["seq"] > 0:
            break
    if last is not None:
        silent = sorted(p for p, s in last["products"].items() if s["p"] is None)
        log(f"  RESULT trial {trial}: seq={last['seq']} silent={silent or 'none'}")
    fh.flush()
    text = logpath.read_text(encoding="utf-8", errors="replace")
    for needle in ("subscribe", "failed", "leaf", "stale", "reconnect"):
        hits = [ln for ln in text.splitlines() if needle in ln.lower()]
        for h in hits:
            log(f"  log[{needle}]: {h.strip()[:160]}")

log("done — server left running")
report.close()
