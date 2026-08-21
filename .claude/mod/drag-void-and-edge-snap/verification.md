# verification — mod/drag-void-and-edge-snap(R4)
## 自動化(2026-08-21 17:1x):vitest 136 files / 2488 passed(baseline 2468 → +20)| tsc 0 | eslint 0 | react-doctor No issues
## SC:SC-1 作廢帶(純函式 + 元件非零界 + 正向 commit + hover 回來源)PASS;SC-2 ≤0 守門(edgeMilli / futMarketEdgeMilli snap 後 / futCloseEstimate 自守 / lower:0 鈕鎖)PASS;
SC-3 snap 統一(TXF 未對齊 25_080 / 20_521、個股期 90_030 → 90.1、FuturesLadder:110 未對齊 20521)PASS;
SC-4 UI:拖曳 pointer 流程 headless 不可複現 → browser_unavailable(pointer drag)+ **user 過目**:側欄拖一檔到搜尋列放開應不動;平倉估價與市價鈕同檔位(盤中)。
## 白名單 W1 四參數位元不變 / W2 既有值斷言全綠 / W3 路由三閘未動 / W4 不變。抽 2 未改:StkfutLadder.test 綠;list-drag 既有 7 案綠。
## Migration 無。self_review_head = 4fdc81d6
