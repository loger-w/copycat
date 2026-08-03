# Phase 7 — 回頭核 goal(txo-tquote-cursor)

2026-07-18,HEAD efb17e4。brainstorm.md 重讀後逐 SC 核對;所有驗證指令本 phase 內 fresh 重跑(含設計精修後)。

| SC | 實作檔案:行號 | 自動化測試 + pass count | real-env 證據路徑 | regression 抽樣對象 |
|---|---|---|---|---|
| SC-1 snapshot per-contract 明細 | copycat/live/aggregate.py:34-41(_PosState outer/inner)、79-92(_ingest 分量)、105-126(_contract_rows)、reset warning:52-58 | tests/live/test_aggregate.py::TestContractsDetail 4 tests + test_replay_golden 1 test,pytest 全套 509 passed;既有 aggregate 測試 assertion 零改動仍綠;regen.py old-keys diff=NONE | 真 TC4 回補(22,935 ticks/190 檔)snapshot 程式化驗證:contracts 存在、逐列不變量成立、舊欄位 shape 不變(real-env-verification-round-1.json SC-1) | 既有 snapshot 消費者:MetricsBar/PnlChart 渲染照常(SC-4 截圖) |
| SC-2 T 字表 | frontend/src/lib/tquote.ts:1-66、frontend/src/components/QuoteTable.tsx:1-160、types.ts ContractRow | tquote.test.ts 10 tests + QuoteTable.test.tsx 5 tests(vitest 42 passed 全套) | evidence/SC-2_tquote-table.png(ATM 區雙側資料 + 單側 — 空態) | 表格外既有版面(header/footer)未變(SC-4 截圖) |
| SC-3 游標試算 | frontend/src/lib/pnl-svg.tsx:30-55(invertX/interpCurve,xDomain 同源)、frontend/src/components/PnlChart.tsx:19-23,42-51,142-166 | pnl-svg.test.ts +4 tests(互逆/邊界 null/插值手算)+ PnlChart.test.tsx +3 tests(hover/stale 重算/範圍外)(vitest 42 passed) | evidence/SC-3_cursor-readout.png + 真實 DOM edge 驗證(pad 外不顯示/mouseout 清除,round JSON SC-3 edge1/edge2) | PnlChart 既有 BEP 標記/分區渲染測試綠 + 截圖可見 |
| SC-4 同頁整合 | frontend/src/App.tsx:1-10,31-36 | (版面無單元測試 — 驗證方式即截圖,brainstorm 所定) | evidence/SC-4_layout.png(全頁:指標卡→曲線→表格,互不遮擋) | footer tick 計數/更新時間照常(同截圖) |
| SC-5 全 gate 綠 | — | pytest 509 / ruff 0 / pyright 0 / validate 42/42 / tsc 0 / vitest 42 / eslint 0 / build exit 0(全部本 phase fresh 重跑,exit code 逐一檢查) | — | 全 repo 既有測試(509 backend + 42 frontend)即 regression 面 |

無 N/A、無「應該可以」。唯一非本次可完成項:ATM 分隔線的**盤中**視覺確認(週六 spot=None 依 DR-8 不畫,行為正確;單元測試已鎖,2026-07-20 盤中順帶看)— 非 SC 缺口,記 Known Limitation。

結論:SC-1~SC-5 全數通過,無回退。
