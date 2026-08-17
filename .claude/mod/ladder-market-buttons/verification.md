# verification — mod/ladder-market-buttons(2026-08-17)

分支 HEAD(自動化 gate 對象):`5dacee8f`(master `8cc9f524` 起 13 commits)。

## 1. 自動化 gate(全綠;第 2 輪 = fix 波後全套)

| gate | 指令 | 結果 | exit |
|---|---|---|---|
| pytest | `.venv\Scripts\python -m pytest -q` | **2648 passed**(baseline 2638;+10 = store 6 / client 4) | 0 |
| ruff | `.venv\Scripts\python -m ruff check copycat tests` | All checks passed | 0 |
| pyright | `.venv\Scripts\python -m pyright` | 0 errors / 0 warnings | 0 |
| validate | `.venv\Scripts\python -m copycat validate` | 42/42 PASS | 0 |
| vitest | `npm test`(frontend/) | **120 files / 2027 passed**(baseline 119 / 1971;+56) | 0 |
| tsc | `npx tsc -b` | 無輸出 | 0 |
| eslint | `npx eslint src` | 無輸出 | 0 |
| react-doctor | `npx react-doctor@latest --scope changed --no-telemetry` | 4 warnings 全存量(`only-export-components` CapitalOrdersList:18 / LadderView:54,60 / PriceLadder:40 均為 master 已存在的 export);**新增 finding = 0**;`no-giant-component` 中途觸發已以 PositionBar 抽出壓回 | 0 |
| build | `npm run build` | ✓ built | 0 |

## 2. 真實環境(側車 = 真 `create_app` + `CapitalClient(FakeCom)` + fake sources,零 TC4 / ZMQ / 群益;`evidence/sidecar_server.py`,port 8721 因 prod 未起;已停)

驗證窗口註記:本輪 SC-12 分兩層 —— (a) 自動化 + 側車可在任何時段驗;(b) D4 現股安全首單 **需 user 盤中執行**(見 §4)。

| SC | 證據 | 結果 |
|---|---|---|
| SC-1 梯頂鈕列 | `evidence/SC-1_stock-ladder-market-buttons-unarmed.png`:2330 現股梯,武裝列之下、價格列之上「市價買」(bull 外框)「市價賣」(bear 外框)並排;DOM 查證 `ladder-market-buttons` 的 previousSibling = 武裝列、nextSibling = `overflow-y-auto` scroll 容器(捲動不動) | PASS |
| SC-2 現股市價買送單 | `evidence/SC-2_stock-armed-market-buy-sent-hint.png` hint「已送 2330 市價買 × 1」;`evidence/SC-2_audit_order_enabled_fakecom.jsonl` + `_fake/sent`:FakeCom 收到 `nSpecialTradeType=1`(市價)/ `nTradeType=0`(ROD)/ `bstrPrice=1190.00`(=梯面最近成交價)/ qty 1;audit `price_type:"market"`, `source:"flash"` | PASS |
| SC-5 未武裝 hint | JS 點擊後讀 DOM:hint = 「未武裝 — 市價不送單」,零請求(audit 無新行) | PASS |
| SC-6 估價 / 界缺鎖鈕 | `evidence/SC-6_futures-no-bounds-buttons-locked.png`:期貨梯 fake 推播無 upper/lower → 「無資料」+ 兩顆鈕灰;武裝後仍灰(JS 讀 disabled=true);現股 3042(無資料)兩顆灰 | PASS |
| SC-7 無券鎖買 | `evidence/SC-7_stock-daytrade-sell-buy-locked.png`:交易別切「無券」→ 市價買灰、市價賣可用(JS: buyDisabled true / sellDisabled false) | PASS |
| SC-8 title | 三態文案由 vitest 逐字鎖(`flash-send.test.ts` marketButtonState);瀏覽器 extension 對 title 屬性遮罩無法直讀 | PASS(vitest) |
| SC-10 委託列表標籤 | `evidence/SC-10_orders-list-market-tag.png`:委託 tab 「2330 買 **市價** 1190 0/1 張 委託成功」;`evidence/SC-10_orders_api.json` `price_type:"market"`(store 由送單結果 SEQ0001 記憶 + 注入 N 回報後帶出);標的名欄仍可辨識 | PASS |
| SC-12(a) 總開關擋單 | `evidence/SC-12a_stock-armed-market-buy-403-hint.png` hint「安全閘拒絕(order_disabled)」;`evidence/SC-12a_audit_order_disabled.jsonl`:三筆(現股 market/ROD、個股期 limit/IOC/1320、期貨 limit/IOC/21060)皆 403 ORDER_BLOCKED,audit blocked 行帶完整 payload | PASS |
| SC-3 / SC-4 個股期 / 期貨 payload | 側車無個股期契約 / 期貨 fake 無界 → UI 端到端未走;由 vitest 逐欄鎖(snapUp/snapDown 邊價、floor/ceil FUT tick、limit+IOC、day_trade、source)+ 側車 curl 直打 route 驗 gate 接受該形狀(SC-12a 的第 2/3 筆) | PASS(vitest + route) |
| SC-9 防抖 | vitest(連按 / 交錯 / 換標的後仍送)三梯 | PASS(vitest) |
| 白名單抽 2 個未改功能 | 點價限價路徑(fixture 既有測試零改綠;側車 UI 點價格格照常送 limit ROD 由 audit 形狀可辨)/ 跟隨置中 + 市價佇列列(既有測試零改) | PASS |

## 3. 白名單逐條(code review r1 白名單 lens 逐條 verdict:W1–W10 全「保留」;`code-review-round-1.json`)

## 4. 留給 user 的真實環境節(本輪不算 Done 的部分,顯式標明)
- **SC-12(b) D4 現股市價安全首單**:prod 重啟含本分支後,盤中挑低價股 1 張(有庫存賣或買)按「市價買 / 市價賣」→ 群益 APP 核對成交型別為市價 + 委託列表出現「市價」標籤 → 截圖回填此節。現股 `nSpecialTradeType=1 + bstrPrice=估價 + ROD` 端到端**仍未實測**(R-F)。
- 個股期 / 期貨市價鈕(limit@邊價 + IOC)prod 首發同樣待 user(遠價 IOC 無對手即刻取消,可作零成交驗收)。
- 夜盤 TXO 市價單的委託列表標籤(KL-4 日界語意)待盤中觀察。
