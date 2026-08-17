# verification — mod/positions-pnl-display(2026-08-17)

HEAD `77810ab3`(master `cdaee027` + 18 commits)。

## 1. 自動化 gate(全在 HEAD 上跑)

| gate | 指令 | 結果 | exit |
|---|---|---|---|
| pytest 全套 | `.venv\Scripts\python -m pytest -q` | 2650 passed, 1 warning (146.8s) | 0 |
| ruff | `.venv\Scripts\python -m ruff check copycat tests` | All checks passed! | 0 |
| pyright | `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings | 0 |
| validate | `.venv\Scripts\python -m copycat validate` | 42/42 PASS | 0 |
| vitest 全套 | `npx vitest run`(frontend/) | 123 files / 2152 passed(baseline 121 / 2100) | 0 |
| tsc | `npx tsc -b` | 無輸出 | 0 |
| eslint | `npx eslint src` | 無輸出 | 0 |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry` | 1 warning `only-export-components GroupGridView.tsx (gridShape)`—master 已存在的存量 export(implementer 以 `git show master:` 核過),**零新增** | PASS |

## 2. 真實環境(側車 8721 + vite 5173;`evidence/sidecar_server.py` + `positions-fixture.json`)

fixture:2330 cash 3@1180 / short −1@1210 / fut CDFI6 +2@1185 pnl_base 3000 / fut QFFI6 −1@1190 pnl_base −250;2317 cash 5 avg null;2454 short −2@1450;fut EE1I6 +1(未知碼)。

| SC | 證據 | 結果 |
|---|---|---|
| SC-1 | `curl /api/capital/positions` → `sec 2330→2330 / fut CDFI6→2330 / fut QFFI6→2330 / fut EE1I6→None`(既有欄位仍在) | PASS |
| SC-2 | `evidence/SC-2-sidebar-chips.png`:2330 `2張 +0.26% · 期 2口/空1口`(bull)、2317 `5張 —`(ink-dim)、2454 `空2張 +0.95%`、2308 無 chip;DOM:全部 `wl-row-*` 高 52px;`wl-row-2308` innerText 與改前同(⋮⋮/2308/台達電/418/-0.48%);chip title 逐 kind + 逐契約全文 | PASS |
| SC-3 | `evidence/SC-3-header-segments.png` + `SC-3-ladder-position-bar.png`;**同瞬 DOM 對照**(JS 一次讀):header `現股 … 損益 -12,436 (-0.35%)` / `融券 … +24,789 (+2.05%)` == ladder-position-row `-12,436` / `+24,789`(quote 1180);fut 段 `期 CDFI6 多 2口 · 均價 1185 · 損益 +3,000` / `期 QFFI6 空 1口 · … -250`;**期貨態**(合約 CDF:202608,主圖 1180、側欄 2330 = 1190):現股段 `+17,466 (+0.49%)` = positionEcon@1190,不隨主圖合約價變(review C-1 反證)→ `evidence/SC-3-header-contract-state.png` | PASS |
| SC-4 | `evidence/SC-4-grid-4cards.jpg` / `SC-4-card-pos-line.png`:2330 卡 `現 2張 +32,252 (+0.68%) · 期 2口/空1口 +2,750`、2317 `現 5張 —`、2454 `現 空2張 +7,497`、2308 無節點;4×4 十六檔 `SC-4-grid-4x4-with-positions.jpg`:有倉卡圖區略矮、不溢軌;四卡高一致 561px | PASS(過矮視窗 600 高:resize_window 對截圖 viewport 無效,改以 4×4 圖牆(卡片 ~180px 高)目視代替) |
| SC-5 | lib 測試(positionEcon 直算對照)+ 元件級 discount=3 兩處(vitest 綠);真機:header 與 ladder 同折數同瞬同值(上列) | PASS |
| SC-6 | **user 有真倉位盤中截圖**——窗口外降級:本節 fake positions 側車截圖 + user 過目 | 待 user |
| W-5 | 群組檢視(側欄 + 圖牆 + 閃電梯三個 observer 掛載)PerformanceObserver 38s:`/api/capital/positions` 3 次(319610 / 334619 / 350616 ms,間隔 15.0s)→ **同 15s 窗恰 1 請求**(觀察者同 tick 掛載,TQ 去重) | PASS |
| 抽 2 未改功能 | 群組卡點選只換閃電目標(點 2330 卡 → 右欄仍 2330,檢視停留群組)✓;無倉列 DOM / 列高不變 ✓ | PASS |

## 3. 白名單逐條

W-1 ladder 部位列文字不變(`PriceLadder.test.tsx` 零改動全綠;真機 `現股 3張 @1180 -12,436 打平 1185`)✓ / W-2 既有欄位 + ROW_H 52 + 既有測試零改動 ✓ / W-3 memo lock(mutation 實證 posMap 拿掉即紅)+ 既有 memo/geometry/toggle 零改動 ✓ / W-4 header 既有元素順序不變(截圖)✓ / W-5 實測 ✓ / W-6 API 既有欄位不變(pytest 既有三案綠)✓ / W-7 無倉列 / 卡 / header 無新節點 ✓ / W-8 `ladder-position.test.ts` 只補 fixture `code: null` ✓。

## 4. Migration 可逆
純加欄 + 純前端;revert 即回復,無資料格式 / cache 版本變動。

## 5. 未完成 / 待 user
- SC-6 真倉位盤中截圖(user 在場)。
- 畫面過目點:自選列 2330 chip 較長時股名被 truncate 到看不見(240px 側欄,見 SC-2 截圖)—— 是 AD-6 拍定的取捨,user 若要改可縮 chip(去 ` · 期 …` 進 tooltip)。
