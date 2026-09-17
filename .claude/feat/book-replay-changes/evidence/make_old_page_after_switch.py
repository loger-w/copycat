"""#269 切換後回歸用的舊頁:切換時備份的 viewer-cdp.html.bak-20260917-pre269 → viewer-cdp.pre269.html,
外掛檔改讀備份資料夾 viewer-cdp-book.bak-20260917-pre269(切換後 viewer-cdp-book 已是 v2,舊頁只認 v1,不改會載不進簿檔,
回歸的重播部分就不是在比畫面而是在比錯誤訊息)。

用法:python make_old_page_after_switch.py
"""

from __future__ import annotations

from pathlib import Path

REVIEW = Path(r"C:\Users\USER\Documents\copycat-trading-review")
BACKUP_PAGE = REVIEW / "viewer-cdp.html.bak-20260917-pre269"
BACKUP_BOOK = "viewer-cdp-book.bak-20260917-pre269"
OLD_PAGE = REVIEW / "viewer-cdp.pre269.html"
BOOKDIR_LINE = b'const BOOKDIR = DATA.bookdir || "viewer-cdp-book";'


def main() -> None:
    page = BACKUP_PAGE.read_bytes()
    assert page.count(BOOKDIR_LINE) == 1, "備份頁找不到 BOOKDIR 那一行"
    assert (REVIEW / BACKUP_BOOK / "2026-09-16").is_dir() and (
        REVIEW / BACKUP_BOOK / "2026-09-17"
    ).is_dir()
    OLD_PAGE.write_bytes(
        page.replace(
            BOOKDIR_LINE, f'const BOOKDIR = DATA.bookdir || "{BACKUP_BOOK}";'.encode("ascii")
        )
    )
    print(f"寫出 {OLD_PAGE}(外掛檔讀 {BACKUP_BOOK};{len(page) / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
