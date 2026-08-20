# 測試覆蓋盤點(refactor/memo-boundaries)

> baseline:master `294f604a`,vitest 2323 全綠(R4 輪驗過)。本輪動到的每個檔案的
> 行為覆蓋如下;memo 是行為保持性改動,行為合約由既有測試守,render-skip 性質由
> 新增 `.memo.test.tsx` 計次測試鎖(慣例樣板 = `GroupGridView.memo.test.tsx`)。

| 檔案 | 既有測試 | 覆蓋面 | 缺口與處置 |
|---|---|---|---|
| `App.tsx`(railCtx / RightRail 掛點) | `App.test.tsx` + `App.corr-tab.test.tsx` | tab 切換、路由 stub、右欄跟隨 | 無 railCtx identity 測試 → 新增 memo 計次測試(harness 層) |
| `components/rail/RightRail.tsx` | `RightRail.test.tsx`(60) | ctx 切換行為、rerender 行為 | 無 render-skip 計次 → 新增 `RightRail.memo.test.tsx` |
| `components/index/MarketPane.tsx` | `MarketPane.test.tsx`(37)+ `.size.test.tsx`(20) | 行為 + 尺寸 | 無 memo 覆蓋 → OverlayCard 幾何 useMemo 的計次測試 |
| `hooks/useChartToggles.ts` | 經 MarketPane / GroupGridView 測試間接 | toggle 行為 | `set` identity 無測試 → 計次測試附帶鎖 |
| `components/corr/RiverCards.tsx` / `RiverOverlay.tsx` / `RiverPanel.tsx` | `RiverPanel.test.tsx`(14,間接) | 渲染行為 | 無 per-card 計次 → 新增 memo 計次測試 |
| `components/stock/LadderView.tsx` / `PriceLadder.tsx` | 8 / 91 tests | 行為極完整 | **本輪不動**(見 plan「範圍決策」) |
| `components/stock/GroupGridView.tsx` | 63 + memo 6 + geometry 3 + toggle 4 | 含 render-skip 計次 | 已達標,不動 |

結論:行為面覆蓋足夠(無需 characterization 補寫);新增的全是「render-skip 性質」
計次測試(🟢 獨立 commit,mutation 抽驗 = 拔掉 memo/useMemo → 紅)。
