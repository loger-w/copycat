# change-spec — mod/positions-pnl-display(batch3 R3:三處顯示使用者倉位與含費稅損益)

> 對照 `current-state.md`(同目錄)。分流判定:**已成形方案**(來源 prompt 指名資料流 / 落點檔 / UI 形式;
> D9(a) / D10(a) 已 user 拍板)→ grilling 姿態、決策點逐條 `[auto-default]`,不再重問拍板項。
> 規模:**L**(後端 API 加欄 + 前端 ≥ 5 檔;對外 API 純加欄無 migration)→ spec review 1 輪 + P0 限縮加輪。

## 0. 目標(一句話)

自選列 / 單檔 header / 群組卡三處,**有倉位才**顯示使用者倉位與損益;證券損益 = 含費稅 `positionEcon`
(與現股閃電梯部位列同一函式同一折數),個股期損益 = 群益 `pnl_base`(與個股期閃電梯部位列同一數字);
個股期倉位靠後端 positions 每列新附 `code`(股號)對到自選股號。

## 1. 決策點(bencium:先問;沒 user 在場走 `[auto-default]`)

| # | 決策 | 選擇 |
|---|---|---|
| AD-1 | 契約碼→股號落點 | **後端 API 邊界附欄**(來源 prompt 建議 (a)):`GET /api/capital/positions` 每列附 `code: str \| null`。**不動 `Position` dataclass**(建構點 balance/store/tests 多處,加欄要給預設值且 store 序列化面擴大);純 helper `copycat/capital/mapping.py::stock_code_of(market, stock_no) -> str \| None`:sec → `stock_no`;fut → `lookup_product(exchange_product_of(stock_no))?.code`;`exchange_product_of` raise / 查無 → `None`(不 raise,不擋整條 API)。 `[auto-default \| reason: 契約碼→產品→股號兩段反查都已在後端且有測試;前端自建對照 = 第二份真相]` |
| AD-2 | 三處折數同源 | `PriceLadder.tsx` 的 `loadDiscount` / `persistDiscount` / `DiscountState` **搬到 `frontend/src/lib/fee-discount.ts`**(🔵 純搬家,PriceLadder 改 import),另 export `readFeeDiscount(): number`(= `loadDiscount().value`)與 hook `useFeeDiscount(): number`(`useSyncExternalStore`:getSnapshot = `readFeeDiscount`,subscribe = `window` `storage` 事件 + 模組級 listener 集合,`persistDiscount` 寫入後通知 listeners)。三處消費者用 `useFeeDiscount()`;讀取收斂到 `getSnapshot`(回 primitive number,Object.is 比對穩定),外部變更靠 subscribe 通知重畫 —— 不再由元件在 render 期間直接讀 localStorage、也不另加快取層(`[amendment 2026-08-17: R16/R20]`)。PriceLadder 自己的折數 state / 輸入框行為不變(仍 `useState(loadDiscount)`),只是 persist 時多發通知 → 三處同 tick 收斂。 `[auto-default \| reason: 折數是低頻設定;useSyncExternalStore 是 React 讀外部 store 的正規解,零額外 abstraction]` |
| AD-3 | 證券損益% 分母 | `pct = pnl / (avg × \|qty\| × 1000) × 100`(成本基準;pnl 為含費稅 `positionEcon.pnl`)。多方 / 空方同一分母。 `[auto-default \| reason: 「賺賠幾 %」對使用者的直觀是本金報酬,與 pnl 同一口徑]` |
| AD-4 | 同股號多 kind(現股 + 融資 + 融券) | **自選列 / 群組卡:sec 聚合成一段**(qty = Σ 帶號 qty;**嚴格制**:任一列 pnl null → 聚合 pnl / pct 皆 null 顯示 `—`;否則 pnl = Σ pnl、cost = Σ avg×\|qty\|×1000、pct = pnl/cost;`[amendment 2026-08-17: R6 刪「只計非 null 列」矛盾語]`);聚合 qty = 0(對鎖,如 cash +3 / short −3)→ 張數印 `多3/空3張` 不印 `0張`(`[amendment 2026-08-17: R10]`);tooltip 逐 kind 列出。**單檔 header:逐 kind 一段**(空間夠,與閃電梯部位列一對一)。 `[auto-default \| reason: 240px 側欄 / 266px 卡片塞不下逐 kind;header 逐列才能「與右欄部位列並排核數字」]` |
| AD-5 | 個股期段內容 | 自選列:**逐契約**(std / mini 契約碼不同、同 code;`[amendment 2026-08-17: R9 標準與小型差 20 倍不可聚合]`):單一契約 `期 n口`(qty<0 → `期 空n口`);多契約 `期 2口/空1口`(依契約碼排序,`/` 分隔),tooltip 逐契約碼列 `CDFI6 多2口 損益 +500 / QFFI6 空1口 損益 —`;**不印 %**(期貨保證金制沒有成本基準;pnl_base 快照亦非即時),tone 依 Σ pnl_base 三態;tooltip「損益 ±元(群益名目,報告時點)」。群組卡:`期 n口 ±元`。header:逐契約一段 `期 <契約碼> 多/空 n口 · 均價 X · 損益 ±元`。 `[auto-default \| reason: 與 StkfutLadder 部位列同數字(pnl_base);不自創期貨費稅口徑(該檔註解已明講)]` |
| AD-6 | 自選列落點 | 左欄第二行**改為 flex row**(`<span class="flex min-w-0 items-baseline gap-1">`,與代號那行 :409 同構;`[amendment 2026-08-17: R5 左欄是 flex-col,直接加子項會多一行撐破 ROW_H]`)包住名稱(`min-w-0 truncate`,name 缺席時省略)+ chip(`shrink-0`);**name 缺席仍渲染該 row 只放 chip**;chip `data-testid="wl-pos-{code}"`(同一檔在多組會出現多份 → 測試用 `queryAllByTestId`;`[amendment 2026-08-17: R12]`),文字 `3張 +1.20%`(有期倉再接 ` · 期 2口`);tone = sec pct 三態(有 sec)否則 fut pnl 三態;`title` = 逐列明細。**無倉 → 不渲染該節點**(零佔位)。 `[auto-default \| reason: 右欄是價 / 漲跌% 的兩行對齊塊,塞第三個元素會破對齊;左欄第二行右緣正好貼著報價塊,符合「第二行右緣」]` |
| AD-7 | 群組卡落點 | `GroupCard` 標題列**之下**新一行 `data-testid="group-pos-{code}"`(font-mono text-[0.625rem]),內容 `現 3張 +12,345 (+1.20%)`,有期倉再接 ` · 期 2口 +500`;無倉不渲染。`GroupCard` 新增 props `positions: readonly CapitalPosition[]`(圖牆層 `useMemo(positionsByCode(positions), [positions])`,無倉 code 拿同一個 `EMPTY_POSITIONS`)+ `discount: number`(primitive)。損益在卡內以 `quote?.p` 現算(quote 本就是 memo dep)。高度評估(`[amendment 2026-08-17: R15/R24]`):卡片 `flex-col gap-1 p-2`,現況 padding 16 + 標題 ~20 + gap 4 + 圖 = 120 起跳;新行 12 + gap 4 → 有倉卡圖區比無倉卡**矮約 16px**,由 `CardIntradayChart` 的 `flex-1 min-h-0` 吸收(不溢軌、不動 `gridShape`);>16 檔 `h-56` 224px 同理。SC-4 截圖 1080p 4×4 有倉卡 + 高 600 過矮視窗即為此結論的驗收(目視圖高差可接受)。 `[auto-default \| reason: 沿 fills 的 EMPTY_* 穩定 identity 範式,memo 契約不破]` |
| AD-8 | 單檔 header 落點 | header 內、`page-quote` 之後、期現價差之前,新 `<span data-testid="page-position">`(font-mono text-xs),每段一個 `<span>`:`現股 3張 · 均價 985.2 · 損益 +12,345 (+1.20%)`;現貨態與個股期態**都**顯示該股號全部 sec 列 + 全部 fut 列(fut 列以契約碼標明)。無倉不渲染。 `[auto-default \| reason: 個股期態下右欄梯只顯示該合約,header 顯示全部才看得到「我這檔還有現股倉」]` |
| AD-9 | 缺值降級 | `avg_price` null/≤0 → 該列 pnl / pct = `—`(qty 照顯示;`DASH`);現價缺(盤前 `q.p` null)→ **僅 sec 段** pnl / pct = `—`,fut 段用 `pnl_base` 不受現價影響(`[amendment 2026-08-17: R7]`);`code` null(未知產品)→ 該 fut 列不進三處(閃電梯不受影響)。 `[auto-default]` |
| AD-10 | 百分比精度 | 沿 `fmtPct`(兩位小數,+號)—— 與側欄漲跌%同一格式;來源 prompt 的「±x.x%」視為示意。 `[auto-default \| reason: 同一列兩個 % 精度不同會像兩種數字]` |
| AD-11 | 三類歸屬 | 後端加欄屬 **🟢**(對外 API 新增欄位是新行為,不是重構;來源 prompt 標 🔵 係口語);前端 lib 搬家 🔵;三處 UI 🟢。 |

## 2. 成功條件(SC;UI 一律畫面可指認)

| SC | 條件 | 驗證方式 |
|---|---|---|
| SC-1 | `GET /api/capital/positions` 每列多 `code`:sec 列 = `stock_no`;fut 列 `CDFI6` → `2330`、mini `QFFI6` → `2330`(版控 `stkfut_map.json` 真表;`[amendment 2026-08-17: R2 CDF=2330 非 2002]`);未知 / 除權息調整碼(`EE1I6`,進不了 stkfut_map)→ `null`;既有欄位不變 | pytest `tests/server/test_capital_api.py::test_positions_carry_code`(sec / fut std / fut mini / fut 未知 `EE1I6` 四例,**打真 DEFAULT_PATH 不 monkeypatch**,把版控表與 helper 綁在一起)+ `tests/capital/test_mapping.py::test_stock_code_of`(含壞契約碼 → None) |
| SC-2 | 自選列:有 sec 倉的列第二行名稱右側出現 chip `3張 +1.20%`(pnl>0 bull 紅 / <0 bear 綠 / 0 ink / null ink-dim);`title` 含 `現股 3張 均價 985.2 損益 +12,345`;無倉列 **DOM 無 `wl-pos-*` 節點**;有 fut 倉的股號 chip 含 `期 2口`(std+mini 並存 → `期 2口/1口`);quote 缺 + 只有 fut 倉 → chip 仍 `期 n口` 帶 tone | vitest `WatchlistSidebar.test.tsx` 新 describe:fetch stub **加 `/api/capital/positions` 路由**(既有 `respond()` fallback 是 200 `{codes,groups}` 殼,不加 = 恆無倉 vacuous;`[amendment 2026-08-17: R4]`),先自檢 `queryAllByTestId("wl-pos-2330").length > 0` 再做無倉 `length === 0`;fixture 鎖文字 / class / title;avg_price null → `—`;std+mini;quote 缺 fut 仍顯示;截圖 `evidence/SC-2-*.png`(240px 側欄:名稱 truncate、報價塊不推移、列高仍 52) |
| SC-3 | 單檔 header:`page-position` 內每段文字 `現股 3張 · 均價 985.2 · 損益 +12,345 (+1.20%)`,數字與右欄閃電梯 `ladder-position-row` **同值**(同 `positionEcon` 同折數);fut 段 `期 CDFI6 多 2口 · 均價 X · 損益 +500` = `stkfut-position-row` 同值;無倉不渲染 | vitest `StockPage.test.tsx`(fixture 鎖文字;含 avg null 降級);截圖 `evidence/SC-3-*.png` header 與右欄並排 |
| SC-4 | 群組卡:標題列下一行 `group-pos-{code}` = `現 3張 +12,345 (+1.20%) · 期 2口 +500`;無倉卡無該節點;`GroupCard` memo 契約:quotes 換 identity 兩輪 → **有倉卡的重畫增量 == 無倉卡增量**(沿 `memo.test.tsx:167-189` fills 量法;`[amendment 2026-08-17: R3 只測無倉卡 = vacuous]`) | vitest `GroupGridView.test.tsx`(stub 加 positions 路由,既有 fallback 是 200 `{states}` 殼;先自檢 `group-pos-2330` 存在)+ `GroupGridView.memo.test.tsx` 新 case(positions 路由 + 一有倉一無倉 fixture + 增量相等 + 前置斷言有倉卡真的收到 positions);既有 memo / geometry 斷言不紅;截圖 `evidence/SC-4-*.png`(含 1080p 4×4 有倉卡 + 高 600 過矮視窗) |
| SC-5 | 折數同源:改 localStorage `copycat-fee-discount` 後三處算出的 pnl 與 PriceLadder 一致 | vitest:`lib/position-summary.test.ts` 以 `positionEcon` 直算對照;`lib/fee-discount.test.ts` 鎖 read/persist/`useFeeDiscount` 通知(含 localStorage 拋錯降級);**元件級**(`[amendment 2026-08-17: R17]`):`WatchlistSidebar.test.tsx` 與 `GroupGridView.test.tsx` 各一條先 `localStorage.setItem("copycat-fee-discount","3")` 再斷言 chip / 卡片文字 == 同 fixture 下 `positionEcon(...,3,...)` 算出的值(不寫死字串) |
| SC-6 | 真實環境:user 有真倉位時三處截圖(**驗證窗口:user 盤中 / 有倉時**;窗口外降級 = fake positions 側車截圖 + user 過目) | `evidence/` + user 過目 |

## 3. 不能破壞的既有行為白名單(reviewer / 自評 finder 對照用)

- W-1 閃電梯部位列(`PriceLadder` `ladder-position-row` / `StkfutLadder` `stkfut-position-row`)文字、數字、順序、折數框行為**逐字不變**(`PriceLadder.test.tsx` 全綠、只改 import)。
- W-2 自選列既有欄位:代號 / 名稱 / (緩) / 價 / 漲跌% / 亮燈整塊底色 / 參考價灰字 / 無資料 / 拖曳握把與落點幾何(`ROW_H=52` 不變、chip 不增列高)/ 群組平均漲幅 badge / 上限 50 文案 —— `WatchlistSidebar.test.tsx` + `.dropcollapsed.test.tsx` 既有斷言零改動。
- W-3 群組卡:`QuoteCell` 三態 / 卡片三態(回補中 / 無資料 / 尚無成交)/ 選中框 / toggle 列 / 成交點 / `GroupCard` memo(既有 `GroupGridView.memo.test.tsx` 不紅)/ 檔數矩陣 —— 既有四檔測試零改動。
- W-4 單檔 header 既有元素順序與文案(名稱 / 代號 / (緩)/ 合約 select / 價 / % / 亮燈 / 無資料 / 回補中 / 期現價差 / 加入自選)不變。
- W-5 `useCapitalPositions` 的 queryKey / `refetchInterval: 15_000` / `retry: 1` / WS invalidate 設定值不變(新 observer 不改 query 設定;TanStack v5 refetchInterval 是 per-observer 計時器,同 15s 窗內掛載錯開可能多打 —— 上界以側車 log 量測 15s 窗內 `/api/capital/positions` 次數記入 verification;`[amendment 2026-08-17: R14]`)。
- W-6 `/api/capital/positions` 既有欄位名與值不變;capital 未啟用仍 `CapitalDisabledError` 路徑。
- W-7 無倉位時三處**不新增任何可見內容**:無 `wl-pos-*` / `group-pos-*` / `page-position` 節點;自選列第二行的 flex wrapper 屬版面重構(所有列一致),不影響列高與既有斷言(`[amendment 2026-08-17: R22]`)。
- W-8 `positionEcon` / `secPositionsOf` / `clampDiscount` 簽章與行為不變(`ladder-position.test.ts` 不動)。

## 4. Backward compat / migration

- API 純加欄(additive);舊前端忽略;無版本 bump、無 cache、無 migration → 可逆 = revert commit。
- localStorage key `copycat-fee-discount` 語意不變(只是讀者變多)。

## 5. Out of scope

- 個股期含費稅口徑(期交稅 / 每口手續費)—— 沿用 `pnl_base`。
- 群組標題列 avgPct 混入倉位。
- 群組卡個股期**委託**成交點(契約碼→股號反查已有 `code` 可用,但屬 R2 精確版留尾)。
- 跨瀏覽器分頁的折數同步不做保證(`storage` 事件有掛但不驗收);PriceLadder 折數輸入框仍是元件內 state,不改為受控於外部 store(`[amendment 2026-08-17: R19]`)。
- 期貨 tab(FuturesLadder / FuturesChart)不動。

## 6. Edge cases(≥ 3)

1. `avg_price` null(OnRealBalanceReport 尚未被損益試算回填)→ 三處 pnl / pct `—`,qty 仍顯示。
2. 現價缺(盤前 `quotes[code].p` null、`accum.last` null)→ **sec 段** pnl `—`;fut 段 pnl_base 照顯示;群組卡 quote undefined 同。
3. 同股號 cash + short 兩列(qty 3 / −2)→ 側欄聚合 `1張`(帶號和)、pnl 和;header 兩段。3b. cash +3 / short −3 對鎖 → `多3/空3張`。3c. 同 code std `CDFI6` 2 口 + mini `QFFI6` −1 口 → 側欄 `期 2口/空1口`,tooltip 逐契約。
4. fut 列 `code` null(未知產品 / 對照檔缺)→ 三處不顯示;閃電梯照舊。
5. `qty === 0` 列(理論不出現)→ 過濾掉。
6. capital 未啟用 / positions 查詢失敗 → `data` undefined → 三處等同無倉。
7. 折數 localStorage 拋錯 → `FEE_DISCOUNT_DEFAULT`(沿 loadDiscount 既有 try/catch)。

## 7. Diff 級章節(逐檔;🔴 行為 / 🟢 新功能 / 🔵 重構;順序 🔵 → 🔴 → 🟢)

### 🔵 前端搬家(行為不變)
- `frontend/src/lib/fee-discount.ts`(新):`DiscountState`、`loadDiscount()`、`persistDiscount()`、`readFeeDiscount()`(從 `PriceLadder.tsx:134-167` 原樣搬出;`FEE_DISCOUNT_KEY` / `FEE_DISCOUNT_DEFAULT` / `clampDiscount` 沿既有 import)。
- `frontend/src/lib/trade-kinds.ts`(新):`TRADE_KINDS` + **`TradeKind` 型別**(`PriceLadder.tsx:46`)+ `kindLabel()`(從 `PriceLadder.tsx:40-46` + `:51-55` 搬出;**line 49 的 local `const DASH` 不在此範圍**,改為 `import { DASH } from "@/lib/pnl-format"`,仍屬 🔵 W-1 逐字不變;`[amendment 2026-08-17: R21]`);`PriceLadder.tsx` 改 import 並 **一律 `export { TRADE_KINDS } from "@/lib/trade-kinds"` + `export type { TradeKind }`** —— caller `RightRail.tsx:7`(`import { PriceLadder, type TradeKind }`)與 `PriceLadder.test.tsx:6` 零改動(`[amendment 2026-08-17: R1 P0 TradeKind 外部 caller 漏盤]`)。
- `frontend/src/lib/pnl-format.ts`(新):`DASH` / `pnlText` / `pnlTone`(從 `LadderView.tsx:52-63` 搬出);`LadderView.tsx` 改 import 並 re-export 三者(既有 caller PriceLadder / StkfutLadder / 測試零改動;`[amendment 2026-08-17: R8 顯示規則單一定義]`)。
- `frontend/src/lib/fee-discount.ts` 另含 `useFeeDiscount()`(AD-2;hook 屬新功能但與搬家同檔 —— 搬家 commit 只搬,hook 進 🟢 lib commit)。
- 既有測試:`PriceLadder.test.tsx` / `LadderView.test.tsx` / `StkfutLadder.test.tsx` 不該紅;新測試 `lib/fee-discount.test.ts`(read 預設 / 合法值 / 壞值 / localStorage 拋錯 / useFeeDiscount 收到 persist 通知)。

### 🟢 後端加欄
- `copycat/capital/mapping.py`:新 `stock_code_of(market: str, stock_no: str) -> str | None`(sec 直回;fut:`exchange_product_of` 包 try/except ValueError → None;`lookup_product` None → None;命中回 `code`)。
- `copycat/server/capital_api.py:218-221`:`{**asdict(p), "code": stock_code_of(p.market, p.stock_no)}`。
- 測試(紅先行):`tests/capital/test_mapping.py::test_stock_code_of`(sec / fut 命中(用 tmp map monkeypatch `DEFAULT_PATH` 或 `path`)/ fut 未知 / 壞契約碼);`tests/server/test_capital_api.py::test_positions_carry_code`。既有 positions 測試不該紅(不整包比對)。
- `frontend/src/types.ts` `CapitalPosition` 加 `code: string | null`(**必填**,漏塞會被 tsc 抓)。該紅(型別,補 `code: null`)的 10 個 fixture factory(`[amendment 2026-08-17: R13]`):`lib/close-order.test.ts:6`、`lib/ladder-position.test.ts:14`、`components/stock/PriceLadder.test.tsx:95`、`components/stock/StkfutLadder.test.tsx:97`、`components/rail/RightRail.test.tsx:74`、`components/capital/CapitalPositionsList.test.tsx:14` 與 `:29`、`components/futures/FuturesLadder.test.tsx:89`、`components/futures/FuturesPage.test.tsx:53`、`components/futures/FuturesChart.test.tsx:43`(`lib/futures-ladder.ts:97` 結構子集不受影響)。

### 🟢 前端 lib(純函式,紅先行)
- `frontend/src/lib/position-summary.ts`(新):
  - `positionsByCode(positions?: CapitalPosition[]): Map<string, CapitalPosition[]>`(qty≠0;key = sec→stock_no / fut→code(null 跳過)),`EMPTY_POSITIONS: readonly CapitalPosition[]`。
  - `secSummary(rows, lastMilli, discount)` → `{ qty, pnl: number|null, pct: number|null, kinds: {label, qty, avg, pnl, pct}[] }`(AD-3 / AD-4)。
  - `futSummary(rows)` → `{ qty, pnl: number|null, rows: {contract, qty, avg, pnl}[] }`(AD-5)。
  - `chipText(sec, fut)` / `chipTitle(...)` / `cardText(...)`(格式單一定義處;用 `lib/pnl-format.ts` 的 `DASH/pnlText/pnlTone` + `fmtPct`,**不自建第二份**;`[amendment 2026-08-17: R8]`)。
  - 測試 `lib/position-summary.test.ts`:與 `positionEcon` 直算對照(SC-5)、聚合、null 降級、code null 跳過。
- 三態 tone 判準 = `pnlTone`(單一定義)。

### 🟢 三處 UI(紅先行)
- `WatchlistSidebar.tsx`:掛 `useCapitalPositions()`;`posMap = useMemo(positionsByCode, [positions])`;`const discount = useFeeDiscount()`(`[amendment 2026-08-17: R18]`);`stockRow` 內取 `posMap.get(code)` → chip(AD-6)。測試新增 describe「倉位 chip」(fetch stub 接 `/api/capital/positions`)。
- `StockPage.tsx`:掛 `useCapitalPositions()` + `useFeeDiscount()`;header 內 `page-position`(AD-8)。測試新增(fetch stub 接 positions)。
- `GroupGridView.tsx`:圖牆層 `useCapitalPositions()` + `posMap` useMemo + `const discount = useFeeDiscount()`(讀一次、primitive 傳給 GroupCard);`GroupCard` 新 props(AD-7);測試新增 + memo test 不紅。
- 既有測試 fetch stub 事實(`[amendment 2026-08-17: R4]`):`GroupGridView.test.tsx:132-135` / `GroupGridView.memo.test.tsx:112-116` fallback = 200 `{states:{}}`;`WatchlistSidebar.test.tsx:37-39 respond()` fallback = 200 `{codes,groups}`;`StockPage.test.tsx` fallback = 404。三者對 positions 都得到「無 `positions` 陣列」→ 無倉 → 既有斷言不紅(W-7);**新寫的倉位測試三份 stub 必加 `/api/capital/positions` 路由 + 先自檢有倉節點存在**。

### 既有測試逐一
| 測試 | 該紅? |
|---|---|
| `PriceLadder.test.tsx` | 不該紅(只換 import) |
| `WatchlistSidebar*.test.tsx` / `GroupGridView*.test.tsx` / `StockPage.test.tsx` 既有 case | 不該紅(無倉 fixture) |
| `tests/server/test_capital_api.py` positions 三例 | 不該紅(不整包相等) |
| `tests/capital/test_mapping.py` 既有 | 不該紅 |
| 上列 10 個 `CapitalPosition` fixture factory(tsc) | **該紅(型別)**:補 `code: null`,行為斷言不動 |
| `LadderView.test.tsx` / `StkfutLadder.test.tsx` / `RightRail.test.tsx` | 不該紅(re-export 保住 import 路徑) |

## 8. 風險註記
- R-1 `useFeeDiscount` 的 getSnapshot 每次 render / 通知讀一次 localStorage(側欄一次、圖牆一次、header 一次;primitive number Object.is 穩定),量級可忽略(`[amendment 2026-08-17: R18]`)。
- R-2 個股期 `pnl_base` 是報告時點快照,三處與梯同數字但都不即時 —— tooltip 標「群益名目」。
- R-3 `code` 反查依賴 `stkfut_map.json` 版控檔;新上市個股期未 refresh、**以及除權息調整後商品代號第三碼由 F 改數字(EE1 / CD1 形,`_parse_rows` 只組 XXF 形,進不了對映)** → 該列 `code` null 不顯示(閃電梯不受影響;`[amendment 2026-08-17: R11]`)。tooltip 不另提示;記 next-time。
- R-4 `useFeeDiscount` 若 doctor 出新 finding(hook 規則)→ 退路:圖牆 / 側欄層一次 `useState(readFeeDiscount)` + `storage` 事件(`[amendment 2026-08-17: R16]`)。

## 9. Verification 計畫
- 自動化:`pytest -q`(全)+ `ruff` + `pyright` + `copycat validate`;`npm test` + `tsc -b` + `eslint` + `react-doctor --scope changed`。
- 真實環境:側車 server(`ops-discipline` capital 側車樣板:fake positions fixture 含 sec 兩 kind + fut 一列 + avg null 一列)→ claude-in-chrome 截圖 SC-2/3/4;抽 2 個未改功能(自選拖曳 / 群組卡點選只換閃電目標);**側車 log 量 15s 窗內 `/api/capital/positions` 請求數**記入 verification(W-5;`[amendment 2026-08-17: R23]`)。

---
`self_review_head: 77810ab3`(2026-08-17;自評 round-1 2 lens + fix 波 5 commits 主 session 快篩;fix 後增量無新 dispatch)
