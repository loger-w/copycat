# verification — mod/cdp-edge-label-avoid(R1)

## 自動化(frontend/,2026-08-21 13:2x)
| step | command | exit | 結果 |
|---|---|---|---|
| vitest | npm test -- --run | 0 | 134 files / 2382 passed(baseline 2358 → +24 新測試) |
| tsc | npx tsc -b | 0 | OK |
| eslint | npx eslint src | 0 | OK |
| react-doctor | npx react-doctor@latest --scope changed --no-telemetry | 0 | No issues found |

## SC 對照
- SC-1 幾何:lib describe bandLabels(擁擠七條 / 交錯 / 全同 y / 界退化原樣 / 超容全印 / 界外 / 位移上限 / 純函式 lock)PASS。
- SC-2 文字不變:MarketChart.test `*` 集合 + StockIntradayChart.test 新 describe 文字集合 PASS。
- SC-3 線體不動:line y1 = g.toY(price),相鄰 6px 而文字 ≥ 10px PASS。
- SC-4 畫面:headless chrome 1600×900(claude-in-chrome 未連線、devtools profile 被他 session 鎖)→
  docs/specs/mod-cdp-edge-label-avoid/screenshots/ 六張:2330 單檔帶內 2395*/2385*/MA5/2370*/2360*/MA20/2345* 逐顆錯開;
  光通圖牆 2455 卡六顆錯開且全印;指數面板 MA5/45291*/44868*/44577* 錯開。**待 user 過目。**

## 白名單
W1 edgePriceLabels 位元不變(既有 96 案不動 + reviewer fuzz 50000 組 0 mismatch)/ W2 pegs.test + 極值避讓測試綠 /
W3 文字、顏色、x、fontSize 不變(測試鎖)/ W4 線體 y 域不動(MarketChart SC-7 綠)/ W5 index 態同段 JSX(MarketChart 21 案綠)/
W6 memo 未打穿(bandBounds 為區域變數)/ W7 拆節點無測試依賴父子結構。
抽 2 個未改功能:MA 值標籤極值避讓(StockIntradayChart.test 1395-1470)綠;futures 態 W-1 lock(futures.test)綠。

## Migration:無。self_review_head = c5d7b9be
