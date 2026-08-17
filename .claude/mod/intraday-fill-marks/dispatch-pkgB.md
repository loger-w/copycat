# Dispatch 包 B — 圖層 + caller(🟢 IntradayChartCore fills 標記 / readout / toggle 鈕 + CardIntradayChart / GroupGridView / StockChart 接線)

你是 implementer(fresh context)。repo:`C:\side-project\copycat`,分支 `mod/intraday-fill-marks`(已切好,直接在主 tree 工作,**不要**開 worktree、不要 switch 分支)。前端在 `frontend/`(npm 指令在該目錄下跑)。包 A 已完成並 commit(`lib/fill-marks.ts` 全部純函式 / `useChartToggles.fills` / `ladder-lots.ts::ymdOf`)—— **直接 import 使用,不改包 A 的檔**(若發現包 A 有 bug,回報而不是順手改)。

## 必讀(先讀再動手)
1. `C:\side-project\copycat\.claude\mod\intraday-fill-marks\change-spec.md` — 本包做 SC-3 / SC-4 / SC-5 / SC-6 / SC-7 / SC-9 與 §5 diff 表的 `StockIntradayChart.tsx` / `CardIntradayChart.tsx` / `GroupGridView.tsx` / `StockChart.tsx` 四列 + 對應測試列;白名單 §3 逐條遵守;含 `[amendment]` 段一律以 amendment 為準。
2. `C:\side-project\copycat\.claude\mod\intraday-fill-marks\current-state.md`(現況與行號;行號為 master 快照,實際以 grep 為準)
3. `frontend/src/lib/fill-marks.ts`(包 A 產物;介面與 docstring)
4. 專案 skills:`C:\side-project\copycat\.claude\skills\frontend-conventions\SKILL.md`、`C:\side-project\copycat\.claude\skills\frontend-testing\SKILL.md`
5. 既有樣板:`frontend/src/components/stock/StockIntradayChart.tsx`(ChartStatic memo 契約、極值標記渲染 :375-421、toggleDefs、readout `allFields`)、`CardIntradayChart.tsx`、`GroupGridView.tsx`(GroupCard memo、GRID_TOGGLES)、`StockChart.tsx`、`StkfutLadder.tsx:113-121`(契約碼 key 選擇範式)、測試樣板 `GroupGridView.geometry.test.tsx:20-23`(vi.mock importOriginal 計次)、`GroupGridView.test.tsx:84-100`(fetch 路由 stub)。

## 本包範圍(只動這些檔)
- `frontend/src/components/stock/StockIntradayChart.tsx`:`CoreProps.fills?: readonly FillPoint[]`(預設 `EMPTY_FILLS`)+ page 薄殼 `Props` 透傳;`fillMarks` useMemo(位置:`g` 之後、`priceLine.length === 0` 早退**之前**);`ChartStatic` 新 prop `fillMarks: readonly FillMark[]`,於 ChartStatic **最末一組** `<g data-testid="fills-layer" pointerEvents="none">`(恆 render)畫 `<polygon data-testid="fill-{B|S}-{minute}" key=同字串 points={fillTrianglePoints(x,y,side)} className={cn(side==="B"?"fill-bull":"fill-bear","stroke-surface")} strokeWidth={FILL_MARK.halo} paintOrder="stroke">`;`toggleDefs` 加 `{key:"fills", label:"成交點", available:true}`(型別 union 加 `"fills"`);readout `fillField`(**page 限定**、`toggles.fills` 閘、`fillsAtMinute(fills, shownMin)` 非空才追加,tone 單側 bull/bear 雙側 undefined,value = `fillLabel(pts, fmt)`)→ `fields = (card ? allFields.slice(0,4) : allFields).concat(fillField ? [fillField] : [])`。註解說明 memo identity 約束(沿檔內既有語氣)。
- `frontend/src/components/stock/CardIntradayChart.tsx`:Props 加 `fills: readonly FillPoint[]`,透傳 core。
- `frontend/src/components/stock/GroupGridView.tsx`:圖牆層(**`groups.length === 0` 早退之前**)`const orders = useCapitalOrders().data?.orders;` `const today = ymdOf(new Date());` `const fillsMap = useMemo(() => fillsByCode(orders, fillDates(today), "股"), [orders, today]);`;`GroupCard` memo props 加 `fills: readonly FillPoint[]`,傳 `fillsMap.get(code) ?? EMPTY_FILLS`;`GRID_TOGGLES` 加 `{key:"fills", label:"成交點"}`(型別 union 加 `"fills"`)。
- `frontend/src/components/stock/StockChart.tsx`:`const orders = useCapitalOrders().data?.orders;` `const today = ymdOf(new Date());` `const key = isFut ? stkfutFillKey(contract.prod, contract.ym) : code;` `const fills = useMemo(() => fillPoints(orders, key, fillDates(today), isFut ? undefined : "股"), [orders, key, today, isFut]);` 傳 `<StockIntradayChart … fills={fills}>`。
- 測試(新 / 改;每條對應 SC 驗證方式欄):`StockIntradayChart.test.tsx`(SC-3 兩點 testid / class / 頂點座標反算 / 窗外 0 / 域外 0 / document 順序;SC-4 hover 成交欄 / 無成交分鐘無欄 / toggle 關無欄;SC-5 按「成交點」→ aria-pressed false + 0 polygon + 無成交欄;SC-9 `vi.mock("@/lib/fill-marks", async (importOriginal) => ({...actual, fillTrianglePoints: vi.fn(actual.fillTrianglePoints)}))` delegate 計次,fixture ≥2 窗內域內點,先斷言 calls === 筆數再連發 3 mousemove 不變)、`StockIntradayChart.variant.test.tsx`(**該紅** `:117` 4→5;新案 card 有 fills 時 readout 仍 4 欄且不含「成交」、card 零 button 不變)、`GroupGridView.test.tsx`(`:559` 五鈕逐名加「成交點」;SC-6 新案:fetch 路由 `/api/capital/orders` 回一筆 2330 當日成交 → 2330 卡 `polygon[data-testid^="fill-"]` 數 1、2317 卡 0)、`GroupGridView.toggle.test.tsx`(SC-5:預種 fills:false → 兩卡 polygon 0;按「成交點」→ 兩卡同時 >0;fetch 路由需回 orders fixture)、`StockChart.test.tsx`(SC-7 三案:現貨態只畫 2330;`contract={prod:"CDF",ym:"202608"}` 只畫 CDFH6;零股 unit "股" 現貨態不畫;fetch 路由 `/api/capital/orders`)。
- **不動**:後端 `copycat/`;`lib/ladder-lots.ts` / `lib/fill-marks.ts` / `hooks/useChartToggles.ts`;`PriceLadder` / `StkfutLadder` / `FuturesLadder` / `FuturesChart`。

## 測試 fixture 提示
- `CapitalOrder` 全欄位型別在 `frontend/src/types.ts:68-91`;`date` 用 `ymdOf(new Date())` 動態算(測試不可寫死日期);`time` 用 `"09:01:30"`(minute 541)等落在 fixture accum 分鐘上;`avg_fill_price` 是**元**(2380.0 → 毫元 2_380_000);`filled_qty` 現股是**張**;`unit` "張" / "股" / "口"。
- 既有 `StockIntradayChart.test.tsx` 的 fetch stub 不分 URL 回 overlay —— SC-3/4/5/9 直接以 `fills` prop 注入,不需 fetch 路由(白名單 W-7)。
- 量法一律 per-card / per-container `querySelectorAll('polygon[data-testid^="fill-"]')` 計數,不用 document 級 `getByTestId`(圖牆兩卡同分鐘會撞)。

## TDD 與 commit 規則(鐵則,逐條照做)
- 每個 SC:先寫紅測試 commit → 再實作到綠 commit;可把介面耦合的 SC 合成一組(如 SC-3+SC-4+SC-5 同一 [red] / [green] 對;SC-6、SC-7、SC-9 各自一對),但**一個 `[red]` 只配一個 `[green]`**。
- commit subject(tag 在 subject):紅 `🟢 test(frontend): add failing test for SC-3/4/5 [red]`;綠 `🟢 feat(frontend): implement SC-3/4/5 [green]`,body 註 `red→green for <red-sha>`。事前標記該紅的 `variant.test.tsx:117` 更新併入對應 `[red]` commit。三類 emoji 不混 commit;本包無 🔴 / 🔵。
- **禁止**:`.skip`、砍測試、改非事前標記的 assertion、mock 掉真依賴(SC-9 的 delegate 計次除外)、`try/catch` 吞錯、條件式 hook。
- 既有測試若紅且不在該紅清單 → 停下不改 assertion,回報。
- 觸及範圍 gate(包尾必跑,在 `frontend/`):`npx vitest run src/components/stock src/components/index src/lib src/hooks` + `npx tsc -b` + `npx eslint src/components/stock` 全綠才回報。**不跑全套 npm test**(main session 波尾親跑)。

## 回報格式(純文字)
1. 逐檔改了什麼(1 行/檔)
2. `git log --format="%h %s" master..HEAD` 全文(自檢 tag 規則)
3. gate 指令與各自 exit code / 測試數字
4. 未決或偏離 spec 之處(若無寫「無」)
