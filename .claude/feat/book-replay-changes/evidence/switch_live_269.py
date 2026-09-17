"""#269 一次切換(另一個 session 收工、user 確認後才跑):暫存驗完的模板與 v2 外掛檔換進回看頁正式位置。

步驟(任一步失敗即停,已做的備份保留):
1. 現用模板雜湊 = 開工時記下的(evidence/base_hashes_before_269.txt 第一行);不同 = 有人改過模板 → 停,要先合併
2. 備份:模板 → viewer_cdp_template.html.bak-20260917-pre269;現用頁 → viewer-cdp.html.bak-20260917-pre269
   (已存在就停,不覆蓋既有備份;外掛檔資料夾已於 15:0x 備份成 viewer-cdp-book.bak-20260917-pre269)
3. 工作模板(evidence/viewer_cdp_template.269.html,CRLF)換進 scripts/week0909/viewer_cdp_template.html
4. viewer-cdp-book-269/<日>/*.js 逐檔複製蓋掉 viewer-cdp-book/<日>/(09-16、09-17),複製後逐檔比雜湊
5. 跑 build_viewer_cdp.py 重建 viewer-cdp.html,確認新頁 = 新模板 + blob

用法:python switch_live_269.py [--dry-run]
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

REVIEW = Path(r"C:\Users\USER\Documents\copycat-trading-review")
SCRIPTS = REVIEW / "scripts" / "week0909"
TEMPLATE = SCRIPTS / "viewer_cdp_template.html"
PAGE = REVIEW / "viewer-cdp.html"
BOOK, STAGE_BOOK = REVIEW / "viewer-cdp-book", REVIEW / "viewer-cdp-book-269"
EVIDENCE = Path(__file__).parent
WORK_TEMPLATE = EVIDENCE / "viewer_cdp_template.269.html"
DATES = ["2026-09-16", "2026-09-17"]
DRY = "--dry-run" in sys.argv


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def step(msg: str) -> None:
    print(("[dry-run] " if DRY else "") + msg, flush=True)


def main() -> int:
    base = (EVIDENCE / "base_hashes_before_269.txt").read_text(encoding="utf-8").split()[0]
    now = sha(TEMPLATE)
    if now != base:
        step(f"停:現用模板雜湊 {now[:12]} ≠ 開工時 {base[:12]},有人改過模板,要先合併")
        return 1
    step(f"1. 現用模板未變({now[:12]})")
    backups = [(TEMPLATE, SCRIPTS / "viewer_cdp_template.html.bak-20260917-pre269"), (PAGE, REVIEW / "viewer-cdp.html.bak-20260917-pre269")]
    for src, dst in backups:
        if dst.exists():
            step(f"停:備份 {dst.name} 已存在,不覆蓋")
            return 1
    for src, dst in backups:
        step(f"2. 備份 {src.name} → {dst.name}")
        if not DRY:
            shutil.copy2(src, dst)
    work = WORK_TEMPLATE.read_bytes()
    assert b"\r\n" in work and work.count(b"__DATA_B64__") == 1
    step(f"3. 模板換成 #269 版({len(work)} bytes,CRLF)")
    if not DRY:
        TEMPLATE.write_bytes(work)
    for date in DATES:
        files = sorted((STAGE_BOOK / date).glob("*.js"))
        step(f"4. {date}:{len(files)} 檔 v2 外掛檔蓋進 {BOOK.name}/{date}")
        if not DRY:
            (BOOK / date).mkdir(exist_ok=True)
            for f in files:
                shutil.copyfile(f, BOOK / date / f.name)
            bad = [f.name for f in files if sha(f) != sha(BOOK / date / f.name)]
            if bad:
                step(f"停:複製後雜湊不符 {bad[:5]}")
                return 1
    step("5. 重建 viewer-cdp.html")
    if not DRY:
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_viewer_cdp.py")], cwd=SCRIPTS, capture_output=True, text=True, encoding="utf-8")
        print(r.stdout.strip(), r.stderr.strip()[-800:])
        if r.returncode:
            return r.returncode
        blob = re.search(rb'<script id="blob" type="text/plain">(.*?)</script>', PAGE.read_bytes(), re.S)
        assert blob
        step(f"   新頁 == 新模板 + blob:{TEMPLATE.read_bytes().replace(b'__DATA_B64__', blob.group(1).strip()) == PAGE.read_bytes()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
