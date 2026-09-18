# -*- coding: utf-8 -*-
"""#272 two-axis review S-01:CLAUDE.md §4 補「群益審計 jsonl 的離線讀者」這條跨檔契約。"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
MD = Path(r"C:\side-project\copycat\CLAUDE.md")
t = MD.read_text(encoding="utf-8", newline="")

ANCHOR = "  上線第一週用真數字覆核 spec 的體積估計(jsonl ~700 MB / 日、簿 parquet 60–100 MB / 日、去重後簿列數)。\n"
NEW = """- **群益審計 jsonl 多了一個 repo 外離線讀者:回看頁的「我的委託」**(2026-09-18 起,#272):產生點
  `copycat/capital/client.py::_record`(`data/audit/capital-<YYYYMMDD>.jsonl`;`ts` 秒精度、`action` ∈ order /
  cancel、`req` = `_WriteReq` 的 `dataclasses.asdict`、`blocked`、`result`)。線上讀者只有事後追溯;**離線讀者** =
  `Documents/copycat-trading-review/scripts/week0909/build_viewer_cdp.py`(repo 外,不在 git;diff 與模板副本歸檔在
  `.claude/feat/book-replay-myorders/`),它吃 `action` 的 order / cancel、`req.stock_no` / `buy_sell` / `price` /
  `qty` / `price_type`、下單 `result.seq_no`(**刪單要刪的單在 `req.seq_no`** —— 刪單 `result.seq_no` 是訊息回音),
  把「我的委託」畫在簿重播的價格階梯上。三個判準沿用不得漂:`result is None`(送出前那一列)/ `blocked` 非 null /
  `result.ok` 為 false 都**不算掛出去的單**;`price_type` 值域 = `PriceType`(`limit` / `market`),非限價不畫在格子上。
  **`ts` 是送單呼叫回來之後才蓋的章**,系統性晚於真正送出(全集 9 筆的成交回報比它早 0.08–0.95 秒,配對後把送出時刻
  收斂成不晚於成交)。漂掉的症狀:改鍵名 → 回看頁那一層**整片少畫、零錯誤訊號**(它不解析失敗,只是配不到);
  `_record` docstring 有同一段的短版。repo 內沒有測試釘得住(讀者在 repo 外),證據 =
  `.claude/feat/book-replay-myorders/evidence/invariants_272.py`(payload 不變式)與 `verify_myorders.mjs`(頁面逐格)。
"""

assert t.count(ANCHOR.replace("\n", "\r\n")) == 1
t = t.replace(
    ANCHOR.replace("\n", "\r\n"), ANCHOR.replace("\n", "\r\n") + NEW.replace("\n", "\r\n")
)
MD.write_text(t, encoding="utf-8", newline="")
b = MD.read_bytes()
print("CLAUDE.md CRLF", b.count(b"\r\n"), "LF", b.count(b"\n"))
