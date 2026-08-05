# phase7-verification:ladder-position-pnl

2026-08-05,HEAD a2dbb95。重讀 brainstorm.md 逐 SC 核對。

| SC-N | 實作檔案:行號 | 自動化測試名 + pass count | real-env 證據路徑 | regression 抽樣對象 |
|---|---|---|---|---|
| SC-1 部位條(卡片底部,空手零痕跡) | PriceLadder.tsx(ladder-position-bar section,卡片 root 末子) | PriceLadder.test.tsx 部位條 describe(文字/空手/DOM 順序 LP-3),45 支全綠 | evidence/SC-1_SC-4_SC-5_ladder-position-full.jpg(現股+融券兩列可指認)+ user 過目待 | 既有閃電梯 24 支原測試(活單聚合/武裝/點價)零變紅 |
| SC-2 未實現損益口徑 | lib/ladder-position.ts(positionEcon) | ladder-position.test.ts 手算例(+3284 / +3138 / −6864)+ LP-6 rerender(+3,284→+5,278),28 支全綠 | live 驗算:last=66.9 → +1,330 / +1,614 逐位吻合;last 跳動 pnl 即時重算(round-1 JSON SC-2) | 部位 tab CapitalPositionsList 不動(pnl_base 原樣) |
| SC-3 打平價(多空,short 含借券費) | lib/ladder-position.ts(BE 公式 + snapBreakEven) | 手算例 100.352→snapUp 100_500 / 99.569→snapDown 99_500 | live:66.2326→66.3、67.707→67.7 與畫面一致 | snapUp/snapDown 既有 stock-tick 測試 |
| SC-4 梯內標記(be warn / avg ma20,pointer-events-none,不受 dimmed) | PriceLadder.tsx(標記 render + Map;row title) | 標記落列/title/LP-2 pointer-events/dimmed 不淡化/IS-3 域外不畫,全綠 | evidence/SC-4_SC-5_rail-after-re1-fix.png(66.3/67.7 amber、66/68 紫,四標記可見)+ DOM 查證 rowTitles 4 筆 | dimmed characterization(opacity 移欄兩段式) |
| SC-5 折數設定(localStorage,CALC-1 invalid 樣態) | PriceLadder.tsx(標題列 input)+ constants.ts(FEE_DISCOUNT_KEY) | 改值重算/字面 key 斷言/非法不寫入/空手可設/aria-invalid,全綠 | live:改 10 折 → ls='10'、pnl/BE 重算驗算相符;RE-1 截字已修並複驗(round-1 JSON) | 張數 input 值不受折數影響(IS-8 斷言) |
| SC-6 多 kind 逐列 | lib secPositionsOf + 部位條逐列 | 多 kind 兩列測試綠 | live:現股 + 融券並列(截圖) | — |
| SC-7 缺值降級 | lib(qty=0/avg≤0/last≤0 歸一)+ 部位條 `—` | avg null / last null 打平照畫 / CALC-2 qty=0 / D14 lastMilli=0,全綠 | fake 通道難重現缺值態,依 design 以測試證據為準(round-1 JSON SC-7) | — |

- 驗證窗口:SC-1/4 的「真持倉」畫面屬盤中 + 群益登入情境,降級策略(brainstorm 明訂)= fake positions 截圖 + user 過目 — 已執行,user 過目為最終關卡。
- 無 FAIL 條目,無回退;rollbacks 空。
