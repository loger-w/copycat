# change-spec — VWAP 就地標籤併進 MA 價位標避讓

分流判定:已成形(review 指名檔案與修法候選)→ grilling 一題:「VWAP 讓位還是 MA 讓位?」
[auto-default: MA 讓位 | reason: VWAP 是就地標籤,位置 = 「線末點在哪」是資訊;MA 價位標是線的冗餘數值(線照畫),
與極值標記同一套「不可動圖元進 obstacles」口徑,不另長一套]。級別 S(單元件檔 + 測試)→ spec review 0 輪。

## SC
- SC-1(畫面可指認):末點貼右界且 MA 開、ma5 價位與 VWAP 相近時,琥珀色 MA5 數字與白色 VWAP 數字**上下錯開**
  (中心距 ≥ EDGE_LABEL_H=10px),VWAP 仍在線末點 y。驗證:`StockIntradayChart.test.tsx` 新案「VWAP 標籤 x 區間碰到 MA 走廊 → MA 讓位、VWAP 不動」;
  截圖 docs/specs/mod-vwap-label-avoid/screenshots/(headless,資料面用 fixture)或 `browser_unavailable` + user 過目。
- SC-2:VWAP 末點在畫面中段(x 區間不碰 maLabelLeft)時 MA 標籤 y 不位移(既有「標籤 y 貼著對應的 MA 線」案 + 新反向案)。

## 不能破壞的既有行為白名單
1. VWAP 標籤 x/y/anchor/class 不變(SC-2 三案 `StockIntradayChart.test.tsx:1191-1260`)。
2. MA 標籤 x = w−R_AXIS_W−2、口徑 fmtTickPrice、toggle 關無標籤(SC-1 五案 :1263-1327)。
3. 極值標記 / pegs 的 obstacle 行為不變(`maObstacles` 既有兩項原樣)。
4. 走廊 A `bandLabels` 與 `pegs.test` 全部不動。

## Out of scope
- VWAP 與 CDP 帶內標籤(走廊 A)的關係:x 不相交(VWAP 右界 ≤ w−R_AXIS_W < 走廊 A 起點)。
- 超容 clamp 全堆界邊(next-time 已記)。

## Diff
- 🟢 `StockIntradayChart.test.tsx`:新增兩案(撞 → MA 讓位;不撞 → 不動)[red]。
- 🔴 `StockIntradayChart.tsx`:`vwapLabel` 算式上移到 `maObstacles` 之前;`maObstacles` 追加
  `vwapLabel && vwapLabelX + VWAP_LABEL_W > maLabelLeft ? [vwapLabel.y] : []`(x 與渲染同一算式,抽 `vwapLabelX`)。
- 既有測試:全部不該紅。
