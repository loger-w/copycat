"""舊(v2,正式資料夾)vs 新(v3,暫存資料夾)外掛檔逐檔比對:量化 #279 審查收修改了什麼。

只讀 payload 的 `chg` / `eat`(不經 decode,新舊版本閘不同),逐則比:
- 價位變動的成交 / 撤單重分類:同一 (側別碼, 價) 的 traded 差
- 吃檔不同的成交列數、被移走 / 移入的張數
- 新版標為集合競價撮合(整則不拆)與附舊簿的則數

用法:python compare_v2_v3.py 2026-09-16 [2026-09-17 …]
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, r"C:\side-project\copycat\.claude\worktrees\fix-pr-279-review-followups")

from copycat.book_replay import parse_plugin_js  # noqa: E402

OLD = Path(r"C:\Users\USER\Documents\copycat-trading-review\viewer-cdp-book")
NEW = Path(r"C:\Users\USER\Documents\copycat-trading-review\viewer-cdp-book-279")
_WIDTH = (7, 3, 8, 3)  # 種類碼 // 2 → 每項格數(= book_replay._CHANGE_KINDS)


def level_changes(cells: list[int]) -> dict[tuple[int, int], tuple[int, int, int]]:
    """一則的 `chg` → {(側別碼, 價): (前量, 後量, 成交)},只取價位變動項。"""
    out: dict[tuple[int, int], tuple[int, int, int]] = {}
    q = 0
    while q < len(cells):
        code = cells[q]
        width = _WIDTH[code // 2]
        if code // 2 == 0:
            out[(code % 2, cells[q + 1])] = (cells[q + 2], cells[q + 3], cells[q + 5])
        q += width
    return out


def main(dates: list[str]) -> None:
    for date in dates:
        stats: Counter[str] = Counter()
        moved: Counter[str] = Counter()
        examples: list[str] = []
        for new_file in sorted((NEW / date).glob("*.js")):
            code = new_file.stem
            old_file = OLD / date / f"{code}.js"
            if not old_file.exists():
                stats["新檔沒有對應舊檔"] += 1
                continue
            a = parse_plugin_js(old_file.read_text(encoding="utf-8"))
            b = parse_plugin_js(new_file.read_text(encoding="utf-8"))
            stats["檔"] += 1
            if a["n"] != b["n"] or a["kind"] != b["kind"]:
                stats["則數或種類不同(異常)"] += 1
                continue
            stats["則"] += b["n"]
            stats["集合競價撮合則"] += len(b.get("auction", []))
            stats["附舊簿則"] += len(b.get("stale", []))
            for i, (ca, cb) in enumerate(zip(a["chg"], b["chg"], strict=True)):
                if ca == cb:
                    continue
                stats["變動不同的則"] += 1
                la, lb = level_changes(ca), level_changes(cb)
                for key in la.keys() & lb.keys():
                    delta = la[key][2] - lb[key][2]
                    if delta > 0:
                        moved["成交 → 撤單(張)"] += delta
                        stats["成交 → 撤單(項)"] += 1
                        if len(examples) < 6:
                            side = "買" if key[0] == 0 else "賣"
                            examples.append(
                                f"{code} 第{i + 1}則 {side} {key[1] / 1000:g}:"
                                f"成交 {la[key][2]} → {lb[key][2]}(前量 {la[key][0]} → 後量 {la[key][1]})"
                            )
                    elif delta < 0:
                        moved["撤單 → 成交(張)"] += -delta
                        stats["撤單 → 成交(項)"] += 1
            for k, (ea, eb) in enumerate(zip(a["eat"], b["eat"], strict=True)):
                if ea != eb:
                    stats["吃檔不同的成交列"] += 1
                    moved["吃檔張數(舊)"] += sum(ea[2::3])
                    moved["吃檔張數(新)"] += sum(eb[2::3])
        print(f"== {date} ==")
        for key, value in stats.items():
            print(f"   {key}: {value:,}")
        for key, value in moved.items():
            print(f"   {key}: {value:,}")
        for line in examples:
            print(f"   例 {line}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["2026-09-16", "2026-09-17"])
