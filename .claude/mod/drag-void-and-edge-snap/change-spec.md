# change-spec — 拖曳 sticky 落點作廢 + 貼漲跌停 snap 口徑統一與 ≤0 守門(mod/drag-void-and-edge-snap,R4 / B10+B11)

分流判定:已成形方案(rounds.md §R4 指名檔案與做法;預核准)。Scope:**M**(4 源檔 + 測試;B11 碰下單邊價 → 1 輪 review 不省)。

## 現況(current-state 併本檔)
- **B10** `lib/list-drag.ts::dropTargetFromPointer(p, zones, rowHeight, bounds)`:x 越界回 null;y 取最近 zone(在所有 zone 上方 → 最上 zone index 0)。
  `WatchlistSidebar.tsx:254 zonesNow()` 回 zones + bounds(aside rect);sticky 搜尋區 `:606 <div className="sticky top-0 z-10 bg-bg pb-1">` 無 ref。
  next-time 08-17 R6 節(review A-3):游標在 sticky 區放開 → 落未分組 index 0 而非作廢;2026-08-20 探針證實。
- **B11** `lib/futures-ladder.ts`:`edgeMilli(side, upper, lower)` raw 選邊(只擋 null);`futMarketEdgeMilli` = floor/ceil 到 `FUT_TICK_MILLI`(市價鈕);
  `futCloseEstimate(pos, contract, quote)` = **raw** edge / 1000(平倉閘估價)。`lib/stkfut.ts::stkfutMarketEdgeMilli` = snapDown/snapUp(股票 tick 表)+ `raw <= 0 → null`。
  RightRail.tsx:281 個股期平倉用 `futCloseEstimate(pos, futKey, meta)` → **未 snap**(且 FUT tick ≠ 股票 tick);:300 期貨平倉亦 raw。
  next-time 08-17 R1 節兩條;探針:fut 版對 0 回 0、負值放行。
- Caller:`dropTargetFromPointer` 只 WatchlistSidebar(305/311)+ list-drag.test;`futCloseEstimate` = FuturesLadder.tsx:110(期貨梯部位)/ RightRail 281(個股期)/ 300(期貨)+ FuturesPage.test.tsx:152-170(TXF 界 25_080_000 / 20_520_000 **已對齊 FUT tick** → 值斷言實際不變,next-time「該紅」判定更正為不該紅;紅測試用未對齊 fixture 另寫)。

## 拍板(auto-default)
- **D1 B10**:`dropTargetFromPointer` 加第 5 參數 `voidBelowY?: number`(sticky 區下緣 clientY);`p.y < voidBelowY` → null(在 x 檢查之後、zone 搜尋之前)。
  `zonesNow()` 回傳加 `voidBelowY`(新增 `stickyRef` 掛 :606 div,取 `getBoundingClientRect().bottom`;ref 缺 → undefined = 不作廢)。
  不動 ROW_H / bounds / zone 幾何。`[auto-default | reason: next-time 明寫做法]`
- **D2 B11 ≤0 守門**:`edgeMilli` 加 `raw <= 0 → null`(futMarketEdgeMilli / futCloseEstimate 同時受益;fut 版與 stkfut 版口徑一致)。
- **D3 B11 snap 統一**:`futCloseEstimate(pos, contract, quote, edgeOf = futMarketEdgeMilli)` —— 平倉估價改吃 snap 後邊價;
  RightRail:281 個股期傳 `edgeOf = (side, u, l) => stkfutMarketEdgeMilli(side, { upper: u, lower: l })`(股票 tick 表);
  FuturesLadder:110 / RightRail:300 期貨用預設(FUT tick)。`[auto-default: 注入 edgeOf 而非兩支函式 | reason: 「同一標的兩處邊價必須同值」—— 市價鈕與平倉各自已有 snap 函式,平倉只是改吃同一支]`
- **D4 不改下單路由**(§R4 契約);`closePriceOf` 單位仍為元。

## 成功條件
- SC-1(B10):`dropTargetFromPointer({x,y:voidBelowY−1}, zones, ROW_H, bounds, voidBelowY)` → null;`y = voidBelowY` → 照舊最近 zone;未傳 voidBelowY → 行為位元不變(既有 list-drag.test 全綠)。
  元件層:WatchlistSidebar.test 模擬拖到 sticky 區放開 → watchlist 不變(PUT 不發)。
- SC-2(B11 守門):`futMarketEdgeMilli("buy", 0, …)` / 負值 → null;`futCloseEstimate` 對 upper 0 → null;FuturesLadder `estimateMissing` 隨之為 true(鈕鎖)。
- SC-3(B11 snap):`futCloseEstimate(pos{qty:-1}, "TXFI6", {upper: 25_080_400})` → 25_080(floor);`{qty:2}` `lower: 20_520_600` → 20_521(ceil);
  個股期:RightRail 傳入 edgeOf 後,meta upper 1_234_567 的空單平倉估價 === `stkfutMarketEdgeMilli("buy", meta)/1000`(同值 lock,元件測試或 RightRail.test)。
- SC-4 UI:側欄拖一檔到搜尋列放開 → 清單不動(截圖前後同)+ user 過目;平倉鍵估價顯示與市價鈕同檔位(user 盤中過目)。

## 白名單
- W1 `dropTargetFromPointer` 四參數呼叫行為位元不變(list-drag.test 全綠不改);拖曳 Escape / 側欄外放開作廢 / 四條 applyDrop 路徑不變。
- W2 `futMarketEdgeMilli` 對合法正值輸出不變;`stkfutMarketEdgeMilli` 不動;FuturesPage.test.tsx:152-170 既有值斷言不改(fixture 已對齊)。
- W3 下單 payload / 路由 / 三閘不變;`closePriceOf === null` → 平倉鍵 disabled 語意不變。
- W4 FuturesLadder 市價鈕 `estimateMissing` 對 null 的語意不變。

## Out of scope
真市價 "M"、委託列表市價標籤日界、B6 期貨 CDP。

## Edge cases
1. sticky ref 未掛(測試或初始 render)→ voidBelowY undefined → 舊行為。2. upper 為負(資料壞)→ null 鎖鈕。3. 個股期 meta null → null(既有)。4. 拖曳中側欄捲動 → voidBelowY 每 move 重算(zonesNow 已每次重算)。

## Diff 級
- 🔴 `lib/list-drag.ts` + `list-drag.test.ts`(新案先紅;舊案不動)→ `WatchlistSidebar.tsx`(stickyRef + zonesNow)+ WatchlistSidebar.test 新案。
- 🔴 `lib/futures-ladder.ts`(edgeMilli 守門 + futCloseEstimate edgeOf)+ FuturesPage.test / futures-ladder 測試新案先紅;`RightRail.tsx:281` 傳 edgeOf + 測試。
- 既有測試全部不該紅。

---
## Spec review round 1 amendments(`change-spec-review-round-1.json`,8 條全 accepted;無 P0 → 不加輪)
- **不該紅清單補齊(R1)**:RightRail.test.tsx:458-468(STKFUT meta.lower 90_000 → tick 100 對齊,snapUp 不變「90」)、:593-600(FUT lower 18_846_000 對齊 1000)、
  FuturesLadder.test.tsx:560-614(25_080_000 / 20_520_000 對齊)、:700-710(lower null 鎖鈕)、FuturesPage.test:152-170。任一紅 = 改壞。
- **SC-3 個股期 lock 改元件層未對齊 fixture(R2)**:RightRail.test 新案 STKFUT_CTX 變體 `lower: 90_030` → 彈窗 / 估價顯示 `90.1`(snapUp;未接 edgeOf 會是 90.03)。
- **測試面做法(R3)**:sticky div 加 `data-testid="wl-sticky"`;`stubRects()` 預設**不**納入(box(0,0) → voidBelowY 0 → 不作廢,既有 7 條拖曳測試位元不變);
  作廢新案在 it 內 local override 為 [0,20],y=10 放開 → 零 PUT(未修會 PUT 到主力 index 0,可區分)。
- **R4**:改 `edgeMilli` docstring(≤0 = 缺值哨符非價)+ futures-ladder.test 該 describe 加 0 / 負值 → null 兩案(先紅)。
- **R5**:`futCloseEstimate` 回傳前補 `edge === null || edge <= 0 → null`(不依賴注入者);SC-2 補「注入不守門 edgeOf 仍 null」。
- **R6 語意界定**:作廢帶 = (−∞, sticky.bottom),含建議清單展開時的延伸與側欄上方區域(皆遮蓋或不在側欄內,刻意);`<` 不改 `<=`。Edge case 補兩條。
- **R7**:move 命中作廢帶 → `to` 設回 `from`(高亮回來源組);SC-1 加 hover 態斷言(drag.to === from)。
- R8:caller 補 `FuturesPage.tsx:20` re-export(optional 參數相容,無需改)。
