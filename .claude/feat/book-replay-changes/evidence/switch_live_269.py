"""#269 一次切換(另一個 session 收工、user 確認後才跑):暫存驗完的模板與 v2 外掛檔換進回看頁正式位置。

步驟(任一步失敗即停,已做的備份保留):
1. 現用模板雜湊 = 開工時記下的(evidence/base_hashes_before_269.txt 第一行);不同 = 有人改過模板 → 停,要先合併
2. 確認外掛檔備份 viewer-cdp-book.bak-20260917-pre269 存在,且逐檔雜湊等於目前正式 viewer-cdp-book(v1)
   (pr-279 review F-31:原本沒檢查備份存不存在、跟正式是不是同一份,只靠 docstring 說「已備份」)
3. 備份:模板 → viewer_cdp_template.html.bak-20260917-pre269;現用頁 → viewer-cdp.html.bak-20260917-pre269
   (已存在就停,不覆蓋既有備份)
4. viewer-cdp-book-269/<日>/*.js 逐檔複製蓋進 viewer-cdp-book/<日>/(09-16、09-17),複製後逐檔比雜湊,
   並比對兩個資料夾的檔名集合相等(先蓋外掛檔、模板還沒換 —— pr-279 review F-31:原本先換模板(舊步驟 3)
   才蓋外掛檔(舊步驟 4),中途失敗會留下「模板 v2、外掛檔一半 v2」的混雜狀態;改成先蓋外掛檔驗完再換模板)
5. 工作模板(evidence/viewer_cdp_template.269.html,CRLF)換進 scripts/week0909/viewer_cdp_template.html
6. 跑 build_viewer_cdp.py 重建 viewer-cdp.html,確認新頁 = 新模板 + blob
   (pr-279 review F-30:原本這個比對只印出來、之後一律 return 0,且前面的 assert 在 `python -O` 下會被拿掉;
   verification.md 曾把 exit 0 當切換證據之一,但結束碼其實不代表新頁正確 —— 改成比對不相等就非 0 結束)

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
BOOK_BACKUP = REVIEW / "viewer-cdp-book.bak-20260917-pre269"
EVIDENCE = Path(__file__).parent
WORK_TEMPLATE = EVIDENCE / "viewer_cdp_template.269.html"
DATES = ["2026-09-16", "2026-09-17"]
DRY = "--dry-run" in sys.argv


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def step(msg: str) -> None:
    print(("[dry-run] " if DRY else "") + msg, flush=True)


def fail(msg: str) -> int:
    step("停:" + msg)
    return 1


def main() -> int:
    base = (EVIDENCE / "base_hashes_before_269.txt").read_text(encoding="utf-8").split()[0]
    now = sha(TEMPLATE)
    if now != base:
        return fail(f"現用模板雜湊 {now[:12]} ≠ 開工時 {base[:12]},有人改過模板,要先合併")
    step(f"1. 現用模板未變({now[:12]})")

    if not BOOK_BACKUP.exists():
        return fail(f"外掛檔備份 {BOOK_BACKUP} 不存在,先備份正式 viewer-cdp-book 再重跑")
    for date in DATES:
        backup_files = sorted(p.name for p in (BOOK_BACKUP / date).glob("*.js"))
        live_files = sorted(p.name for p in (BOOK / date).glob("*.js"))
        if backup_files != live_files:
            return fail(
                f"備份 {date} 檔名集合與正式不同(備份 {len(backup_files)} / 正式 {len(live_files)}),備份可能不完整"
            )
        bad = [name for name in backup_files if sha(BOOK_BACKUP / date / name) != sha(BOOK / date / name)]
        if bad:
            return fail(f"備份 {date} 與正式雜湊不符 {bad[:5]},備份可能不是目前的 v1")
    step("2. 外掛檔備份存在且與正式 v1 逐檔雜湊相同")

    backups = [
        (TEMPLATE, SCRIPTS / "viewer_cdp_template.html.bak-20260917-pre269"),
        (PAGE, REVIEW / "viewer-cdp.html.bak-20260917-pre269"),
    ]
    for _src, dst in backups:
        if dst.exists():
            return fail(f"備份 {dst.name} 已存在,不覆蓋")
    for src, dst in backups:
        step(f"3. 備份 {src.name} → {dst.name}")
        if not DRY:
            shutil.copy2(src, dst)

    for date in DATES:
        files = sorted((STAGE_BOOK / date).glob("*.js"))
        step(f"4. {date}:{len(files)} 檔 v2 外掛檔蓋進 {BOOK.name}/{date}")
        if not DRY:
            (BOOK / date).mkdir(exist_ok=True)
            for f in files:
                shutil.copyfile(f, BOOK / date / f.name)
            bad = [f.name for f in files if sha(f) != sha(BOOK / date / f.name)]
            if bad:
                return fail(f"{date} 複製後雜湊不符 {bad[:5]}")
            stage_names = {f.name for f in files}
            live_names = {p.name for p in (BOOK / date).glob("*.js")}
            if stage_names != live_names:
                extra = sorted(live_names - stage_names)
                missing = sorted(stage_names - live_names)
                return fail(
                    f"{date} 複製後檔名集合不同(正式多出 {extra[:5]}、缺 {missing[:5]}),"
                    "暫存與正式的檔案清單對不上"
                )

    work = WORK_TEMPLATE.read_bytes()
    if b"\r\n" not in work or work.count(b"__DATA_B64__") != 1:
        return fail("工作模板格式不對(缺 CRLF 或 __DATA_B64__ 標記數不是 1)")
    step(f"5. 模板換成 #269 版({len(work)} bytes,CRLF)")
    if not DRY:
        TEMPLATE.write_bytes(work)

    step("6. 重建 viewer-cdp.html")
    if not DRY:
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "build_viewer_cdp.py")],
            cwd=SCRIPTS,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        print(r.stdout.strip(), r.stderr.strip()[-800:])
        if r.returncode:
            return r.returncode
        blob = re.search(rb'<script id="blob" type="text/plain">(.*?)</script>', PAGE.read_bytes(), re.S)
        if not blob:
            return fail("新頁找不到資料 blob")
        matches = TEMPLATE.read_bytes().replace(b"__DATA_B64__", blob.group(1).strip()) == PAGE.read_bytes()
        step(f"   新頁 == 新模板 + blob:{matches}")
        if not matches:
            return fail("新頁不是新模板 + blob,重建結果不對")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
