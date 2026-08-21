# change-spec — 個股分時圖 CDP 右緣標籤避讓(mod/cdp-edge-label-avoid,R1 / B2)

分流判定:**已成形方案**(rounds.md §R1 指名檔案 + 修法候選 a/b/c;規格來自 user 拍板文件 → 預核准,
grilling 逐題採建議解標 `[auto-default]`)。Scope:**M**(lib + 元件 2 源檔 + 測試)。
現況見 `current-state.md`。

## 拍板(auto-default)

- **D1 修法取 (a) 1D 避讓推廣,不做 (b) 近價合併**
  `[auto-default: (a) | reason: (b) 會改標籤文字(「2365*/2360*」併一顆),違反 §R1 行為契約「標籤文字與價位不變、只動 y」;(a) 只動 y]`
- **D2 (c) 兩份演算法合一:stock 側抽共用核心,index 側 `rightEdgeLabels` 不借用、不動**
  `[auto-default: 抽 stock-intraday-svg 內部共用 layout 核心;index-chart-svg.ts 不碰 | reason: rightEdgeLabels 無 production caller(R10 C3 將刪),借用等於復活死碼;兩份核心邏輯相同,stock 側抽核心後「不各長一套」已達成,且 R10 刪碼時不會撞到本輪]`
- **D3 走廊 A 與走廊 B 不互避**
  `[auto-default: 帶內標籤(A)只避自己 | reason: A 在 x ≥ w−38(anchor start)、B 在 x ≤ w−42(anchor end),水平不相交;互避只會讓 MA 值無故位移(白名單 W2)]`
- **D4 最小間距沿 `EDGE_LABEL_H`(10px 中心距)、裝不下時依既有規則截斷 / 丟棄**
  `[auto-default: 不另設常數 | reason: 同一條走廊語意(字高 9px + 1px);既有 capacity / 殘餘丟棄規則已被 review 過]`
- **D5 帶內文字渲染座標維持「baseline = 中心 + 3」**(`y={lab.y + 3}`,不加 `dy`)
  `[auto-default | reason: 不相疊時像素零變(現行 `l.y + 3`),走廊 A 現無測試鎖 y,避免順手改渲染方式]`
  `[amendment 2026-08-21: spec review R9]` +3 是走廊 A 的既有近似(走廊 B 用 `dy=0.35em` ≈ 3.15px);核心輸出仍是**中心**,
  本輪刻意不改渲染方式以保像素零變,後續勿當 bug 順手改。
- **D6 核心是純函式,且走廊 A 不截斷不丟棄** `[amendment 2026-08-21: spec review R1/R2]`
  `[auto-default: 核心第一步 items.map(i => ({...i})),輸入陣列與元素一律不改;bandLabels 以參數 dropOverflow=false 走核心 ——
  不做 capacity 截斷、不做殘餘 <EDGE_LABEL_H 丟棄、界退化(top > bottom)時回傳「y = 線 y」原樣;edgePriceLabels 維持
  dropOverflow=true(W1 位元不變) | reason: oLines 是 useMemo 陣列且被 <line y1> 同讀,就地改寫會把線體一起推走並汙染 memo;
  走廊 A 現行無條件全印,§R1 契約「文字與價位不變」→ 價位訊息不得靜默消失(cardSvgBox 無高度地板,4×4 圖牆 mainH≈80 時
  capacity 6 < 7 可達),裝不下時寧可疊在界邊]`
- **D7 走廊 A 用自己的界 `bandBounds = { top: PAD_Y, bottom: plotBottom − PAD_Y }`** `[amendment 2026-08-21: spec review R3]`
  `[auto-default | reason: 這正是線 y 的值域(g.yDomain 映射範圍),任何不相疊的線標籤 y 都不會被 clamp 位移(Edge case 3 才成立);
  帶內沒有極值文字 / 掛牌,不必對齊 MARK_LABEL_TOP]`

## 成功條件

- **SC-1 帶內標籤互不相疊(幾何)**:`[amendment 2026-08-21: R12]` **在 bounds 非退化且 n ≤ capacity
  (= floor((bottom−top)/EDGE_LABEL_H)+1)時**,`oLines` 任意組合經新佈局函式後,輸出兩兩 `|Δy| ≥ EDGE_LABEL_H`,
  且 y 排序與輸入線 y 排序一致(上下次序不互換);退化 / 超容兩態另立:輸出顆數 = 輸入顆數、y 單調(允許相等)、
  線體不動、位移上限仍成立。**輸出順序 = 輸入順序**(`[amendment: R15]` 理由 = 拆節點後 DOM 次序穩定、測試逐條對位;
  配色 / key 以 level 為鍵,非配色需求)。
  `[amendment 2026-08-21: R7]` §R1 原句的 11 顆裡 VWAP / 昨收 / 現價(走廊 B/C,x ≤ w−42 anchor=end)與帶內(x = w−R_AXIS_W+2,
  全檔僅 L408 一處,anchor=start)**水平不相交**,故不入 fixture;帶內 7 顆歸零即 9 對歸零。
  `[amendment 2026-08-21: R8]` 位移上限:每顆 `|label.y − line.y| ≤ (n−1) × EDGE_LABEL_H`(n = 帶內顆數),並作為測試斷言;
  已知核心是「下推 + 底部回推」而非對稱展開,cluster 整體偏下 —— 接受(改對稱展開要動核心,威脅 W1)。
  `[amendment 2026-08-21: R1]` 純函式 lock:`structuredClone` 輸入後呼叫,輸入逐位元不變。
  驗證:`lib/stock-intraday-svg.test.ts` 新 describe,fixture = 2330 08-20 型平靜日(CDP 五值 +
  MA5/MA20 七條擠 36px:y ∈ {100,106,112,118,124,130,136})→ 相疊對數 0;另測單顆 / 空集合 / 界退化原樣 /
  容量不足全印(不截斷;`[amendment: R13]` `edgePriceLabels` dropOverflow=true 的截斷案由 W1 既有測試覆蓋、不重寫)。
- **SC-2 文字與價位不變**:輸出每顆 `level` / `priceMilli` 與輸入一一對應,元件層 `*` 集合與 MA 名稱不變。
  驗證:既有 `MarketChart.test.tsx:158`(`*` 集合)+ `StockIntradayChart.test.tsx:1274` 不動且綠;
  新元件測試:七條擁擠 fixture 下帶內 `<text>` 節點數 = 7、文字集合不變、相鄰 y 差 ≥ 10。
- **SC-3 線體不動**:帶內 `<line y1>` 仍 = 線真 y(標籤離線、線不離)。驗證:同上元件測試比對 line y1 vs text y。
- **SC-4 畫面可指認(UI)**:2330 個股頁開 CDP+MA,右緣帶內 `2xxx*` 五顆與 MA5/MA20 字樣上下錯開、
  無疊印。驗證:claude-in-chrome 截圖 `docs/specs/mod-cdp-edge-label-avoid/screenshots/`(盤後資料亦可)+ user 過目。
  `[amendment 2026-08-21: R5]` 增列兩張:群組圖牆(最小卡片,CDP 開)、指數面板(MarketChart,CDP 開)。
  `[amendment: R11]` 圖牆卡片判準與 D6 一致:帶內七顆**全印**(節點數 7、文字集合不變)、y 單調不互換、capacity < n 時
  允許界邊貼齊(mainH≈80 → 可用高 58px < 60px,七顆必疊,不以「不疊」驗收);「不疊」只在容量足夠的尺寸(單檔頁 / 指數面板)驗。

## 不能破壞的既有行為白名單

- W1 `edgePriceLabels` 對 MA 值標籤的既有輸出**逐位元不變**(`stock-intraday-svg.test.ts:964-1095` 全綠,不改 assertion)。
- W2 MA 值標籤對極值文字 / 圓 / 掛牌的避讓不退化(`stock-intraday-svg.pegs.test.ts`、`StockIntradayChart.test.tsx:1308/1425/1464`、`StockIntradayChart.index.test.tsx:144`)。
- W3 帶內標籤文字口徑不變:CDP `priceText(milli)*`、MA 名稱大寫;顏色 `LEVEL_FILL`、x、fontSize 不變。
- W4 疊線線體 x1/x2/y/虛線樣式不變;y 域不受影響(`MarketChart.test.tsx` SC-7)。
- W5 index 態的 oLines 走同一段 JSX,行為一致(無 mode 分支;MarketChart fixture 佐證)。`[amendment 2026-08-21: R5]`
  futures 態 `overlaySupported=false` → oLines 恆空,本輪無行為面。
- W7 `<line>` 與 `<text>` 從同一 `<g key="o-…">` 拆成兩組節點:全庫無測試依賴該父子結構(reviewer 掃 parentElement /
  closest / querySelectorAll("g") 確認),實作可拆;但線體 `<g>` key 保留。`[amendment 2026-08-21: R4]`
- W6 `ChartStatic` memo 不被打穿(新計算在 ChartStatic 內、不新增 props / 行內常數)。

## Backward compat / migration
無對外 API、無持久化、無 props 變更 → 無 migration。

## Out of scope
- 近價合併顯示(D1)、index 側 `rightEdgeLabels` 重用或刪除(R10 C3)、`EDGE_LABEL_H` 隨 unitScale 縮放(next-time 08-17 條)、走廊 C(VWAP/POC)就地標籤。
- 極值文字與帶內標籤的互避(x 不交,D3)。

## Edge cases
1. 七條全同 y(CDP 五值相等的極端 + MA 同價)→ 由上而下展開,中心距 10,超出界者回推,裝不下者截斷。
2. 界退化(top > bottom,超矮圖)→ 帶內標籤回傳 y = 線 y 原樣(D6;**與 `edgePriceLabels` 不同**,線體照畫)。
3. 只有 MA 開、CDP 關(oLines 僅 2 條)→ 結果與現行相同(不相疊時 y 不動)。
4. oLines 空 → 空陣列,無 `<g>`。
5. 容量不足(mainH 很矮、7 顆 > capacity)→ 帶內**全印**、允許疊在界邊(D6);`edgePriceLabels` 仍截斷。

## Diff 級章節

### `frontend/src/lib/stock-intraday-svg.ts`
- 🔵 抽 `layoutEdgeLabels<T extends { y: number }>(items: readonly T[], obstacles, bounds, opts: { dropOverflow: boolean }): T[]`
  (**先 `map(i => ({...i}))` 複製**;排序(穩定)/ capacity / 下推 / 回推 / clamp,`dropOverflow=true` 時 capacity 截斷 +
  殘餘丟棄 + 界退化回 `[]`,內容逐行搬自 `edgePriceLabels`);`edgePriceLabels` = 過濾 ma5/ma20 → 核心(dropOverflow=true)。
  既有測試全部不動、全綠(🔵 commit 的證據)。
- 🟢 新 export `bandLabels(oLines, bounds): OverlayLine[]`(核心 dropOverflow=false,無 obstacles,所有 level 都收;
  **輸出依輸入順序**:`[amendment: R14]` 還原機制 = `bandLabels` 先包 `{ ...line, _i: idx }` 餵核心(spread 複製保留 `_i`),
  回傳後 `sort((a,b) => a._i − b._i)` 再剝欄 —— 不改核心簽名,W1 不受影響;界退化回 y 原樣;回傳新物件)。
- 既有測試:全部「不該紅」。新測試:`describe("bandLabels(R1 SC-1)")` ≥ 6 案(擁擠七條 / 單顆 / 空 / 界退化原樣 /
  容量不足全印 / 純函式 lock / 位移上限 / 順序保持)。
- commit 順序 `[amendment 2026-08-21: R10]`:🔵 抽核心 → 🟢 `bandLabels` + lib 測試(測試即 caller,message 標明下一顆元件接手)
  → 🔴 元件換資料源;三顆同一 PR 同一 merge,不留跨 PR 死碼窗口。

### `frontend/src/components/stock/StockIntradayChart.tsx`
- 🔴 走廊 A 的 `oLines.map` 拆成:線體仍由 `oLines` 畫(`<g key="o-…">` 保留);文字改由
  `bandLabels(oLines, bandBounds)` 畫(`y={lab.y + 3}`,其餘屬性不變;`bandBounds = { top: PAD_Y, bottom: plotBottom − PAD_Y }`,D7)。
- 既有測試:全部「不該紅」(無測試鎖帶內 y)。新測試:`StockIntradayChart.test.tsx` 擁擠 fixture
  → 帶內文字相鄰 y 差 ≥ 10、line y1 不動、文字集合不變(先紅後綠)。

### 既有測試逐檔盤點 `[amendment 2026-08-21: R4]`
| 檔案 | 案子 | 判定 | 理由 |
|---|---|---|---|
| `lib/stock-intraday-svg.test.ts:964-1095` | edgePriceLabels 全部 | 不該紅 | W1 位元不變 |
| `lib/stock-intraday-svg.pegs.test.ts` | 全部 | 不該紅 | W2 |
| `StockIntradayChart.test.tsx` 1274/1308/1395/1425/1464 | MA 值 / 極值避讓 | 不該紅 | 走廊 B 不動 |
| `StockIntradayChart.index.test.tsx:144` | 掛牌 vs MA | 不該紅 | 走廊 B 不動 |
| `StockIntradayChart.variant.test.tsx` | card 變體 | 不該紅 | 只讀結構 / 尺寸,不讀帶內 y |
| `StockIntradayChart.futures.test.tsx` | futures 態 W-1 lock | 不該紅 | oLines 恆空 |
| `GroupGridView.test.tsx` | 圖牆 svg 結構 | 不該紅 | 不讀帶內文字 y |
| `MarketChart.test.tsx:158-198, SC-7` | `*` 集合 / 掛牌 / y 域 | 不該紅 | 文字不變、y 域不動 |
任一條紅 = 打到不該動的,回 spec。

### 測試檔
- `lib/stock-intraday-svg.test.ts`(🟢 新 describe)、`components/stock/StockIntradayChart.test.tsx`(🔴 紅先行)。

## Known Risks
- 帶內標籤被推離線後,密集區使用者需靠顏色對應線(與 MA 值標籤既有行為一致);cluster 整體偏下(R8,位移 ≤ (n−1)×10px)。
- 矮卡片(圖牆)七顆全印可能疊在界邊(D6 取捨:寧疊不丟)。

## Spec review 處置(round 1,`change-spec-review-round-1.json`)
R1 accepted→D6 / R2 accepted→D6 / R3 accepted→D7 / R4 accepted→盤點表+W7 / R5 accepted→SC-4 增兩張+W5 改寫 /
R6 accepted→current-state caller map 更正 / R7 accepted→SC-1 註 / R8 accepted→SC-1 位移上限 / R9 accepted→D5 註 / R10 accepted→commit 順序。
有 accepted P0 → 限縮加輪 1 次(只審 amendment 段)。
Round 2(`change-spec-review-round-2.json`):R11 accepted→SC-4 圖牆判準改全印 / R12 accepted→SC-1 加前提 / R13 accepted→措辭 /
R14 accepted→`_i` 還原機制 / R15 accepted→理由改寫。無 P0,收斂。
