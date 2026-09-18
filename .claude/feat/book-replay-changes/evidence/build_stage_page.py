"""#269 測試頁:工作模板 + 現用 viewer-cdp.html 裡的資料 blob → viewer-cdp.269.html(外掛檔讀 viewer-cdp-book-269)。

另一個 session 同時在補 09-17 回看頁(user 2026-09-17 拍板「先在旁邊做完,最後一次切換」),所以開發期間
不碰現用的模板、viewer-cdp.html 與 viewer-cdp-book;build_viewer_cdp.py 的最後一步就是「模板的
__DATA_B64__ 換成 blob」(本腳本先驗現用頁 = 現用模板 + blob 再照做,只多把外掛檔資料夾換成暫存那份)。

用法:python build_stage_page.py <工作模板路徑>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REVIEW = Path(r"C:\Users\USER\Documents\copycat-trading-review")
LIVE_PAGE = REVIEW / "viewer-cdp.html"
LIVE_TEMPLATE = REVIEW / "scripts" / "week0909" / "viewer_cdp_template.html"
STAGE_PAGE = REVIEW / "viewer-cdp.269.html"
BOOKDIR_LINE = b'const BOOKDIR = DATA.bookdir || "viewer-cdp-book";'
STAGE_BOOKDIR_LINE = b'const BOOKDIR = DATA.bookdir || "viewer-cdp-book-269";'
RESULT = Path(__file__).parent / "result_build_stage_page.txt"


def main() -> None:
    work_template = Path(sys.argv[1]).read_bytes()
    live = LIVE_PAGE.read_bytes()
    m = re.search(rb'<script id="blob" type="text/plain">(.*?)</script>', live, re.S)
    assert m, "現用頁找不到資料 blob"
    blob = m.group(1).strip()
    live_template = LIVE_TEMPLATE.read_bytes()
    rebuilt_live = live_template.replace(b"__DATA_B64__", blob)
    check = f"現用頁 == 現用模板 + blob: {rebuilt_live == live}"
    print(check)
    RESULT.write_text(check + "\n", encoding="utf-8")
    if rebuilt_live != live:
        # pr-279 review F-23:原本只印 True/False、False 也照樣往下寫測試頁;
        # 現用頁可能被另一個 session 重建過(blob 對不上目前的模板),先停下來確認,不能悄悄用錯資料。
        sys.exit(
            "停:現用頁不是現用模板 + blob,先確認另一個 session 的狀態(現用頁可能被重建過,需要重新複製舊頁)"
        )
    assert work_template.count(b"__DATA_B64__") == 1
    assert work_template.count(BOOKDIR_LINE) == 1
    page = work_template.replace(b"__DATA_B64__", blob).replace(BOOKDIR_LINE, STAGE_BOOKDIR_LINE)
    STAGE_PAGE.write_bytes(page)
    crlf, lf = page.count(b"\r\n"), page.count(b"\n")
    print(f"寫出 {STAGE_PAGE}({len(page) / 1e6:.2f} MB;CRLF {crlf} / LF {lf})")


if __name__ == "__main__":
    main()
