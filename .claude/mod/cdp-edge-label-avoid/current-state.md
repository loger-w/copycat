# current-state — 個股分時圖右緣標籤(R1 / B2)

來源:`docs/superpowers/specs/2026-08-21-daytime-chain-rounds.md` §R1(user 拍板文件 → 預核准)。
證據:`docs/specs/next-time-mcp-verification-2026-08-20/screenshots/102-cdp-label-cluster-2330.jpg`
(2330 平靜日右緣 11 顆標籤擠 36px 縱距、9 對兩兩相疊)。

## 右緣文字的三條走廊(StockIntradayChart.tsx `ChartStatic`)

| 走廊 | x / anchor | 內容 | 現行 y | 避讓 |
|---|---|---|---|---|
| A 右緣帶(`R_AXIS_W`=40 內) | `w − R_AXIS_W + 2`,start | `oLines` 每條一顆:CDP 五線印 `價位*`、MA5/MA20 印名稱(`levelText`) | **`l.y + 3`(baseline,直接取線 y)** | **無**(StockIntradayChart.tsx:395-416) |
| B 繪圖區內側右緣 | `w − R_AXIS_W − 2`,end | MA5/MA20 **價位值**(`edge-price-*`)、域外掛牌(index 態 `overlay-peg-*`)、極值標記文字(clamp 後可能伸入) | `edgePriceLabels(oLines, maObstacles, edgeBounds)` | 1D 三段式 + obstacles(極值文字/圓/掛牌) |
| C 就地 | VWAP 末點右側、POC 尖端右側 | `edge-price-vwap` / `vp-poc-label` | 線末點 y | 無(x 有 clamp) |

截圖中相疊的 cluster 是 **走廊 A 的 7 顆**(5 CDP* + MA5 + MA20 名稱)彼此互疊,再加走廊 B 的
MA 值 / 極值文字與它們**水平上不相交**(A 在帶內 x ≥ w−38,B 在帶外 x ≤ w−42,anchor 相背)。
→ 本輪只需讓走廊 A 內部互不相疊;A 與 B 不需互避(x 不交)。

## 既有演算法

- `lib/stock-intraday-svg.ts::edgePriceLabels(oLines, obstacles, bounds)`(L601-663):
  過濾 `ma5|ma20` → 依 y 排序 → capacity 截斷 → 由上而下推開(含 obstacle 往下讓)→
  由下而上回推(obstacle 往上讓)→ clamp + 殘餘 `<EDGE_LABEL_H` 丟棄。單位 = 視覺中心,`EDGE_LABEL_H = 10`。
- `lib/stock-intraday-svg.ts::pegLabels`(L566-598):兩側各自堆疊,不推。
- `lib/index-chart-svg.ts::rightEdgeLabels`(L154-231):fixed 昨收錨 + movable(oLines + pegs)
  三段式(同精神)。**無 production caller**(next-time 08-17 index-core R4 節已列死碼;R10 C3 要刪)。
  兩份演算法核心相同(排序 / capacity / 下推 / 回推 / clamp 丟棄),差在 (1) 輸入型別,(2) fixed
  是否也出現在輸出(index 側昨收在輸出、stock 側 obstacles 不在輸出)。

## Caller map

- `edgePriceLabels`:唯一 caller `StockIntradayChart.tsx:253`(ChartStatic)。測試
  `lib/stock-intraday-svg.test.ts:964-1095`(describe `edgePriceLabels(SC-1/SC-3)`)、
  `lib/stock-intraday-svg.pegs.test.ts`(掛牌 obstacles 不退化)、
  `StockIntradayChart.test.tsx:1308/1425/1464`(MA 值 y 與極值避讓)、
  `StockIntradayChart.index.test.tsx:144`(掛牌 vs MA)。
- 走廊 A 文字:`StockIntradayChart.tsx:395-416`(`oLines.map`,`<g key="o-<level>">` 內 line + text)。
  讀者測試:`MarketChart.test.tsx:158-166`(只讀 textContent 以 `*` 結尾集合,不讀 y);
  `StockIntradayChart.test.tsx:1274`(MA 值不含 `*`)。**無測試鎖定走廊 A 的 y**。
- `IntradayChartCore` 直接消費者:StockChart(經 StockIntradayChart)/ CardIntradayChart / MarketChart / FuturesChart;
  間接:GroupGridView → CardIntradayChart、MarketPane → MarketChart(皆經同一 ChartStatic;index 態 oLines 走同一段 JSX;
  futures 態 `overlaySupported=false` → oLines 恆空)。AdvanceDeclineChart 自繪 SVG,不經 core(更正 2026-08-21 R6)。

## 現況 vs 目標

| 面向 | 現況 | 目標 |
|---|---|---|
| 走廊 A y | 直接 = 線 y,密集 CDP 整組疊字 | 同 `edgePriceLabels` 的 1D 三段式避讓(無 obstacles),兩兩中心距 ≥ `EDGE_LABEL_H` |
| 文字 / 價位 / 顏色 / x | — | **不變**(只動 y) |
| 線體 y | 線仍畫在真價位 | 不變(標籤可離線,線不離) |
| signature | `edgePriceLabels` 過濾寫死 ma5/ma20 | 抽共用 layout 核心,`edgePriceLabels` 行為位元不變(🔵);新增帶標籤佈局入口(🟢) |
| backward compat | 無對外 API、無持久化 | 無 migration |
| index 側 `rightEdgeLabels` | 死碼 | 不借用、不復活(R10 C3 刪;本輪不動該檔) |
