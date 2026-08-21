# current-state — VWAP 就地標籤 × MA 價位標疊印

來源:`docs/superpowers/specs/2026-08-22-daytime-chain-review.md` R1 P1(PR #78 出貨後 review)。

| 項 | 現況 | 目標 |
|---|---|---|
| VWAP 標籤 | `StockIntradayChart.tsx:593-607` 就地畫在 vwapLine 末點右側,anchor=start,x=min(end.x+4, w−R_AXIS_W−VWAP_LABEL_W),y=end.y,**不進任何避讓** | 不動(它是「線在哪」的就地訊號,位置即資訊) |
| MA 價位標 | `edgePriceLabels(oLines, maObstacles, edgeBounds)`,anchor=end 在 x=w−R_AXIS_W−2,向左佔 EDGE_LABEL_W=34;obstacles = 極值標記(僅當其 x 區間碰到 `maLabelLeft`)+ pegs | obstacles 多一項:VWAP 標籤 y,**僅當 VWAP 標籤 x 區間 [x, x+VWAP_LABEL_W] 碰到 maLabelLeft** |
| 症狀 | 末點貼右界(盤末 / 收盤後資料)時 VWAP 右緣 = w−R_AXIS_W,與 MA 價位標 x 區間完全重疊;y 相近即疊印(SC-4-2330-band-closeup.png 白 2387.74 壓琥珀 2380) | 兩者中心距 ≥ EDGE_LABEL_H |

Caller:`edgePriceLabels` 只有 StockIntradayChart 一處(`grep -rn edgePriceLabels frontend/src`);`maObstacles` 為元件內 local。
既有測試:`StockIntradayChart.test.tsx` SC-1(MA 標籤 y 貼線 / x / 口徑)、SC-2(VWAP 就地 / 末點貼右界內縮)、`stock-intraday-svg.pegs.test.ts`。
Backward compat:純畫面,無 API / 資料格式。
