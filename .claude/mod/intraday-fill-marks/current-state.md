# current-state — 個股(期)分時圖「當日成交點」近似版(R2)

> 快照:master `0c0322ad`(2026-08-17),分支 `mod/intraday-fill-marks`。
> 來源 prompt:`docs/superpowers/specs/2026-08-17-user-feedback-batch3-rounds.md` §2 R2;
> D7(近似版:每張委託一點)/ D8(▲/▼、同分鐘同向合併、readout 加欄、toggle `fills` 預設開)已拍板。

## 1. 資料面(後端零改動)

| 項 | 現況 | 檔:行 |
|---|---|---|
| 委託記錄型別 | `CapitalOrder{seq_no, stock_no, buy_sell("B"/"S"/null), price, avg_fill_price, order_qty, filled_qty, unit, date(YYYYMMDD), time(HH:MM:SS 最新事件), actionable, price_type,…}` | `frontend/src/types.ts:68-91` |
| 取得 hook | `useCapitalOrders()` → TQ `["capital-orders"]`,`refetchInterval 30_000`、`retry 1`;WS `capital_order` 事件 → `scheduleInvalidate` 200ms debounce → 成交後 ≤1s 更新。**無 `enabled` 參數**;多處掛載共享同一 query(PriceLadder/StkfutLadder/FuturesLadder/CapitalOrdersList 已各掛一份) | `hooks/useCapital.ts:119-141,157-163` |
| 當日窗 | `ymdWindow(now, offsets)` → `Set<YYYYMMDD>`;現股梯傳 `[0]`,期貨/個股期梯傳 `[-1,0,1]`(理由:`date` 是委託建立日、夜盤跨午夜語意未實證) | `lib/ladder-lots.ts:33-41` |
| 比對鍵 | 現股 `stock_no` = 股號;個股期 `stock_no` = 期交所契約碼(`futExchangeContract(prod, ym)` 如 `CDFH6`,對非 YYYYMM 會 throw → caller try/catch 落 null) | `lib/ladder-lots.ts:43-56`;`lib/futures-ladder.ts:88-95`;`StkfutLadder.tsx:113-121` |
| 零股排除 | 現股梯 `excludeUnit="股"` 整筆排除(`unit==="股"` 實涵蓋零股 ∪ 未知 market) | `lib/ladder-lots.ts:56-64` |
| 聚合語意 | `aggregateLots` 分側、以 `price`(委託價)聚合;**不吃 `avg_fill_price` / `time`**,本輪不動它 | `lib/ladder-lots.ts:66-87` |
| 個股期交易時段 | 主圖 x 窗 `STKFUT_WINDOW` = 08:45–13:45(日盤);個股期有無夜盤**未實證**(`StkfutLadder.tsx:123` 註解稱有、梯因此取 ±1 日窗)— 本輪不以此為依據 [amendment 2026-08-17: R6] | `StockIntradayChart.tsx:650`;`StkfutLadder.tsx:123-125` |

## 2. 圖層面

| 項 | 現況 | 檔:行 |
|---|---|---|
| 共用渲染核心 | `IntradayChartCore({accum, toggles, onToggle?, variant:"page"/"card", width?, mainHeight?, subHeight?, stkfut?})`;`StockIntradayChart` = page 薄殼(:1066-1079);`CardIntradayChart` = card 薄殼(自量尺寸、`accumFromGroupSnapshot` useMemo) | `StockIntradayChart.tsx:604-644`;`CardIntradayChart.tsx:26-53` |
| 靜態圖層 memo | `ChartStatic = memo(...)` props 全純量或 useMemo 穩定 identity(`g/w/h/refMilli/showVwap/vwapMilli/oLines/vpBars/clipAbove/clipBelow/plotBottom/xw/hourTicks`);註解明言行內字面值 / 新 identity 會打穿 memo | `StockIntradayChart.tsx:111-146` |
| 極值標記範式 | `markLabels` 由 `g.highMark/g.lowMark`(`ExtremeMark{x,y,priceMilli}`)算;畫在主價線之後;`markCenterX(mark.x, INTRADAY_MARK, {min:0,max:w})` 夾制、`markTone` 判色、`paintOrder="stroke"` + `stroke-surface` halo;`INTRADAY_MARK.dot = {radius 2.5, halo 1}` | `StockIntradayChart.tsx:150-162, 375-421`;`lib/chart-extreme.ts:53-57` |
| 時間→x | `minuteKey("HH:MM:SS")` → 分鐘序號;`minuteToX(minute, w, xw)`;窗外分鐘由呼叫端自行過濾(幾何 `priceLine` 只含窗內) | `lib/stock-accum.ts:102-104`;`lib/stock-intraday-svg.ts:79-81` |
| 價→y | `g.toY(priceMilli)`(`IntradayGeometry.toY`,overlay 線共用) | `lib/stock-intraday-svg.ts:122-140, 484` |
| hover / readout | `hover{min,y}` state;`hoverMin` → `accum.minutes.get`;`allFields`(六欄:時間/價/%/量/外/內)→ card `slice(0,4)`;`ChartReadout({fields, hovering})`(key = label 或 `f-i`) | `StockIntradayChart.tsx:739-787`;`components/chart/ChartReadout.tsx` |
| toggle 鈕列 | `toggleDefs: {key:"vwap"/"cdp"/"ma"/"vp", label, available}[]`;card 變體不畫 button;stkfut 態 cdp/ma/vp 反灰 | `StockIntradayChart.tsx:809-846` |
| 圖牆 toggle | `GRID_TOGGLES` 四鈕(label 與單檔頁逐字相同)在 `GroupGridView`;`useChartToggles` 只在圖牆層一份,`toggles`(不含 `set`)傳進 `GroupCard`(memo) → `CardIntradayChart` | `GroupGridView.tsx:207-219, 107-125` |
| GroupCard memo 契約 | `quotes` 每秒換 identity → 父層每秒 render;GroupCard 為 memo,props 必須穩定(`onPick` latest-ref、`toggles` 圖牆一份、`snap` TQ cache) | `GroupGridView.tsx:107-125, 226-235` |
| toggles schema | `ChartToggles{vwap,cdp,ma,bb,vp}`;`DEFAULTS`;`TOGGLES_VERSION=2`;規則:**新鍵免 bump**(`{...DEFAULTS,...saved}` 自然補上),bump 只在既有鍵預設改變 | `hooks/useChartToggles.ts:5-13, 17-31, 32` |
| ChartToggles 其他讀者 | `App.tsx` / `IndexPage.tsx` / `LimitListSection.tsx` / `MarketChart.tsx` / `MarketPane.tsx` / `CandleChart.tsx` / `PriceLadder.tsx` / `lib/constants.ts` — 源碼只讀個別鍵,加鍵不影響;**測試整包 literal 四處**(`MarketChart.test.tsx:40` / `MarketPane.test.tsx:40` / `MarketPane.size.test.tsx:73` / `StockIntradayChart.variant.test.tsx:49`)加必填鍵會 tsc 紅(`tsconfig.app.json` include src 含 test)[amendment 2026-08-17: R1] | grep `ChartToggles = {` |
| 單檔頁 caller | `StockPage.tsx:366 <StockChart accum code contract>` → `StockChart.tsx:157 <StockIntradayChart accum mainHeight subHeight stkfut={isFut}>`;`StockChart` 持有 `contract {prod, ym} | null` | `StockChart.tsx:42-61, 157` |
| 期貨 tab | `FuturesChart.tsx` 另一套幾何 — **不在本輪** | — |

## 3. 測試面(現況)

- `StockIntradayChart.test.tsx`:`vi.stubGlobal("fetch", 回 overlayResponse)`(不分 URL)、`getBoundingClientRect` 800×260 mock;`wrap()` 內含 QueryClientProvider。
- `StockIntradayChart.variant.test.tsx:69,117`:card 變體 `button` 數 = 0;page 變體 toggle `button` 數 = **4** → 加 `fills` 鈕會變 5(該紅)。`:91` card readout 4 欄(非成交分鐘不變)。
- `GroupGridView.test.tsx:559-566`:「pill 列右側有均價 / CDP / MA / 量分佈 四鈕」逐鈕查存在(不數總數,加鈕不紅);`:578` 卡片 button 數 0(不變)。
- `GroupGridView.toggle.test.tsx` / `.memo.test.tsx`:QueryClientProvider 有;fetch stub 依 URL 路由(需看新 URL `/api/capital/orders` 落到哪個分支)。
- `useChartToggles.test.ts:19 DEFAULTS` 整包 + `:143-150` 整包 `toEqual` → 加 `fills` 鍵**該紅**(schema 擴充,事前標記)。
- `StockChart.test.tsx:60-72` 只數模式鈕(regex 過濾),加 toggle 鈕不紅。
- baseline:`npm test -- --run` 執行中(見 verification.md 補記)。

## 4. 現況 vs 目標

| 面向 | 現況 | 目標 |
|---|---|---|
| 行為 | 分時圖無使用者成交資訊 | 主圖疊 ▲(買 bull)/▼(賣 bear)於(成交分鐘, 均價);同分鐘同向合併;hover/readout 加「成交」欄;toggle `fills` 預設開;page + card 同畫 |
| signature | `IntradayChartCore` 無成交入口 | 新增 `fills?: readonly FillPoint[]`(幾何無關資料,穩定 identity 傳入);`StockIntradayChart` / `CardIntradayChart` 透傳 |
| 資料流 | orders 只進三座梯 | `StockChart`(page)/ `GroupGridView`(wall)各掛一份 `useCapitalOrders` → `lib/fill-marks.ts` 純函式折成 FillPoint → 傳入 core |
| caller 影響 | — | `StockPage` 不改;`GroupCard` memo props 多一個 `fills`(穩定 identity);`GRID_TOGGLES` + `toggleDefs` 各加一鈕 |
| backward compat | toggles 存檔 v2 五鍵 | 加鍵免 bump(既有規則);舊存檔自動補 `fills:true`;無 API / 資料格式變更 |
| migration | 無 | 無 |
