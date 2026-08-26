# fix/breakeven-avg-source-daytrade-tax — verification

user 症狀(2026-08-26):閃電梯打平線「先樂觀更新、再跳到系統判斷的位置」;系統顯示的損益價格與群益 APP 不一樣。
user 拍板:修法 A(avg_source);今天成交進來的張數賣出稅用當沖 0.15%、過往庫存 0.3%、混合按張數分段。

## Phase 1 loop(紅先行,commit 6692ca7d)

| 指令 | 修前 | 修後(d0b058ea) |
|---|---|---|
| `npx vitest run src/lib/ladder-position.test.ts`(frontend/) | 4 紅:pnl `expected 120 to be ≤ 1`(差 120 元 = 一筆買費)、BE `120.42 < 1`(= 落地那一跳 0.12 元)、當沖 `18165 ≠ 19020`、混合 `28848 ≠ 29090` | 全綠 |
| `pytest -q tests/capital/test_store.py -k "avg_source or today_qty"` | 5 紅(`AttributeError: 'Position' object has no attribute 'avg_source'` 等) | 5 passed |

紅在 user 症狀上:120 元 / 120 毫元正是「群益均價含買費、我們再加一次」的量。

## Phase 2 真資料(prod `c430a662`,`/api/capital/positions` 2026-08-26 收盤後)

| 股 | 券商 avg_price | pnl_cost ÷ 股數 | 差 | 價 × 0.1425% × 1.8 折 |
|---|---|---|---|---|
| 4991 現股 1 張 | 469.62 | 469.50 | 0.12 | 0.1204 |
| 6715 融資 1 張 | 364.59 | 364.50 | 0.09 | 0.0935 |

群益 pnl_base 18,285 @489.5 = 20,000 − 買費 120.4 − 賣費 125.6 − 稅 0.3% 1,468.5 → 群益 APP **用 0.3%、不做當沖減半**。
舊前端公式算出 18,165(少 120 = 買費算兩次)。

## Phase 3 假說(依真資料排序;user 已拍板 A 故未停等)

1. **群益均價含買進手續費、前端當純價再加一次**(prod 兩筆部位差額 = 買費,吻合到 0.001)→ 成立,修於本輪。
2. next-time「成交到達時回查鏈在途,落地短暫覆蓋回成交前快照」→ 會是「閃回再回來」形狀,user 描述是「先樂觀再跳到系統位置」(跳一次定住),不符;未動。
3. 折數不是 1.8 → 資料反推 0.02565% = 1.8 折整,否定。
4. 現價時點不同(我們用 WS 現價、APP 用報告市價)→ 只影響 pnl 不影響打平線,且差額固定 120 與現價無關,否定。

## 自動化 gate(分支 HEAD d0b058ea)

| gate | 結果 |
|---|---|
| `pytest -q tests/capital/test_store.py` | 63 passed |
| `pytest -q`(全套) | 見下 |
| `ruff check copycat tests` | All checks passed |
| `pyright copycat/capital tests/capital` | 0 errors |
| `npx vitest run` | 151 files / 2827 passed |
| `npx tsc -b` | exit 0 |
| `npx eslint src` | exit 0 |
| `npx react-doctor@latest --scope changed --no-telemetry` | No issues found |

## Blast radius

- `positionEcon` 讀者:`PriceLadder.tsx::positionRows`、`lib/position-summary.ts::secSummary`(StockPage header / 側欄 / 群組卡經此)—— 兩處改傳 `{avgSource, todayQty}`;`StkfutLadder` 刻意不套稅費口徑,未動。
- `Position` 建構點:`balance.py`(OI / 庫存列,預設 `avg_source=None, today_qty=0`)、store 樂觀套用(`fill`)、`apply_profit_rows`(`broker`)、測試多處;序列化唯一點 `capital_api.py::capital_positions` 的 `asdict` 自動帶新欄。
- 前端 `CapitalPosition` 字面 fixture 16 檔 19 處補 `avg_source: null, today_qty: 0`(tsc 擋住漏補)。

## 反向驗證

(見下方追記)

## 真實環境

- 打平線 / 損益公式以 prod 真資料(4991 / 6715)手算對照:broker 來源 pnl 18,286 vs 群益 18,285(券商均價四捨五入到分);打平線 fill 469.50 vs broker 469.62 差 0.4 毫元(< 一檔 500 毫元)。
- **真成交過目(prod 重啟後下一筆整股成交)**:打平線在券商快照落地時不再跳格;今天買的部位損益 = 群益 APP + 稅減半差額(4991 例 +734)。
- 空方(融券 / 無券)均價語意無真樣本,沿舊式(當純價);明天 user 無券當沖實錄一併校準。

## Review round 1 收修後重跑(3554a18a)

| gate | 結果 |
|---|---|
| `pytest -q tests/capital/test_store.py` | 65 passed(新測 9 條:含跨日 fill_date、net ≤ 0) |
| `ruff check copycat tests` / `pyright copycat/capital tests/capital` | All checks passed / 0 errors |
| `npx vitest run src/lib/ladder-position.test.ts src/lib/position-summary.test.ts` | 70 passed |
| `npx tsc -b` / `npx eslint src` | exit 0 / exit 0 |
| 全套 pytest / 全套 vitest / react-doctor | 見下方追記 |

## 反向驗證(3554a18a)

`git checkout 733d772e -- copycat/capital/store.py copycat/capital/models.py frontend/src/lib/ladder-position.ts`(生產檔回修前、測試留新)
→ `pytest -k "avg_source or today_qty"` **7 failed**;`vitest ladder-position.test.ts` **8 failed**(pnl 18165≠18286、BE 差 120 毫元、當沖、混合、NaN…)
→ `git checkout HEAD -- <同三檔>` → 7 passed / 37 passed。紅 → 綠 → 紅 → 綠成立。
(`git revert --no-commit d0b058ea 3554a18a` 兩筆互撞衝突,故改用生產檔 checkout 法。)

## 真實環境對帳規則(明天)

- 與群益 APP 對損益:**只拿 `today_qty = 0` 的部位**(APP 不做當沖減半 —— 實證 = 4991 當日 10:07 買進,收盤 pnl_base 18,285 以 0.3% 反算吻合到 1 元)。
- 今天買的部位:我們 = APP + 減半差額(4991 例 +734)。
- 打平線:成交後 1–2 s 券商快照落地時不再跳格(prod 重啟後首筆整股成交過目)。
- 期貨 OI 列 `avg_source` 恆 null(產生點不標),前端 `secPositionsOf` 濾掉不進 positionEcon。
