# change-spec — 個股(期)分時圖疊「當日成交點」近似版(mod/intraday-fill-marks)

> 現況表:`.claude/mod/intraday-fill-marks/current-state.md`(reviewer 先讀)。
> 來源:`docs/superpowers/specs/2026-08-17-user-feedback-batch3-rounds.md` §2 R2;拍板 D7(近似版)/ D8(樣式)。
> 分流判定:**已成形方案**(prompt 指名資料源 / 落點檔案 / UI 形式;決策點 D7/D8 已由 user 拍板)→ grilling 姿態、規格來自 user 拍板文件 = 預核准;餘下實作選擇逐條標 `[auto-default]`,無方向性抉擇(SC 集合 / out of scope / 對外契約皆不受選項互換影響)。
> 規模:L(≥5 檔;純前端、無 API / 無 migration)→ spec review 1 輪 + P0 限縮加輪;實作 dispatch(opus)。

## 0. 目標(一句)

單檔頁(現貨 / 個股期)與群組圖牆的分時主圖上,把使用者**當日有成交的委託**畫成 ▲(買)/ ▼(賣)標記於(最新事件分鐘, 均價);hover 該分鐘 readout 顯示「成交 買 n@價」;新 toggle `fills`(預設開)可關;**後端零改動**。

## 1. 近似版限制(明寫,user 已拍板 D7)

- 一張委託 = 一點,座標取 `avg_fill_price`(均價)× `time`(**最新事件時間**,非首筆成交時間)。分批成交多筆會被壓成同一點;若尾段事件是刪單(部分成交後刪),點落在刪單時刻。
- 精確版(後端保留逐筆 D 事件 + `GET /api/capital/fills`)→ **記 next-time**(收尾時寫入 `docs/next-time.md`)。
- 群組卡**只標現股**委託(契約碼→股號反查留給精確版);單檔頁個股期態以**選定契約碼**比對。

## 2. 成功條件(SC gate:每條附驗證方式)

| # | 成功條件(畫面可指認) | 驗證方式 |
|---|---|---|
| SC-1 | 純函式 `lib/fill-marks.ts`(零 React)[amendment 2026-08-17: R2/R5/R8/R9/R10/R12]:<br>• `FillPoint = {minute, priceMilli, side:"B"\|"S", qty}`;`EMPTY_FILLS: readonly FillPoint[] = []`(module 常數)。<br>• `FillDates = { today: string; yesterday: string }`;`fillDates(todayYmd: string): FillDates`(解析 YYYYMMDD 減一日,純函式)。<br>• `fillPoints(orders: CapitalOrder[] \| undefined, key: string \| null, dates: FillDates, excludeUnit?: string): readonly FillPoint[]`:**`key === null` → 直接回 `EMPTY_FILLS`**(同 `aggregateLots` guard)[amendment 2026-08-17 r2: R2-5];過濾 = `stock_no===key` ∧ `filled_qty>0` ∧ `avg_fill_price!==null` ∧ `time!==null` ∧ (`date===dates.today` **∨** (`actionable` ∧ `date===dates.yesterday`))[amendment 2026-08-17 r2: R2-4 — 活單只認**昨日建立**的(涵蓋盤後預約單今日成交);更早的 actionable 幽靈單、以及昨日建立昨日成交今日仍 actionable 的單(理論上收盤即終態,殘餘風險明列)不再無界計入] ∧ `buy_sell∈{B,S}` ∧(`excludeUnit` 命中則整筆跳過);逐筆 `priceMilli = Math.round(avg_fill_price*1000)`(元→毫元);`minute = minuteKey(time)`;**同分鐘同向合併**:qty 加總、price = 量加權平均後 `Math.round`(毫元整數);輸出依 minute 升冪(同分鐘 B 先 S 後);**零筆回 `EMPTY_FILLS`(同一 identity)**。<br>• `fillsByCode(orders, dates: FillDates, excludeUnit?) → Map<string, readonly FillPoint[]>`(圖牆用,同規則按 `stock_no` 分組;零筆的 code 不入 map)。<br>• `stkfutFillKey(prod: string, ym: string): string \| null`(包 `futExchangeContract` try/catch,throw → null)。<br>• `FILL_MARK = { halfW: 3.5, height: 6, halo: 1 }`;`clampFillX(x, w, style=FILL_MARK)` = `min(max(x, halfW+halo/2), w-(halfW+halo/2))`;`fillTrianglePoints(cx, tipY, side, style)` → SVG points 字串:B = 尖端 (cx,tipY) 體在下 `(cx-halfW,tipY+height) (cx+halfW,tipY+height)`;S = 尖端 (cx,tipY) 體在上。<br>• `projectFills(fills, geo: {toY, yDomain:[lo,hi]}, w, xw): readonly FillMark[]`(`FillMark = FillPoint & {x, y}`):`minute` 不在 `[xw.start, xw.end]` **或** `priceMilli < lo \|\| priceMilli > hi`(域外,同 overlay / 極值既有規則)→ 不畫;`x = clampFillX(minuteToX(minute,w,xw), w)`、`y = toY(priceMilli)`(尖端 y **不夾**:域頂賣點三角體最多被裁 ~2px,明示接受);零筆回 module 常數 `EMPTY_MARKS`。<br>• `fillsAtMinute(fills, minute) → readonly FillPoint[]`;`fillLabel(points, fmt) → string`(SC-4 文案)。 | vitest `lib/fill-marks.test.ts`:過濾各一案(含「昨日 date + actionable + filled → 計入」「昨日 date + 非活單 → 排除」「前日 date + actionable → 排除」「key null → identity === EMPTY_FILLS」)、`fillDates` 跨月 / 跨年案、元→毫元換算案、合併加權案(100000@2 + 101000@1 → 100333 qty 3)、跨分鐘不合併案、排序案、零筆 identity === EMPTY_FILLS 案、`fillsByCode` 分組案、`stkfutFillKey` 合法 / 非法 ym 案、`clampFillX` 兩端案、`fillTrianglePoints` B/S 頂點案、`projectFills` 窗外 / 域外 / 正常三案、`fillsAtMinute` 案、`fillLabel` 單側 / 雙側案 |
| SC-2 | `useChartToggles`:`ChartToggles` 加 `fills: boolean`,`DEFAULTS.fills = true`,**`TOGGLES_VERSION` 不 bump**;舊存檔(v2 五鍵)load 後 `fills===true`;`set("fills", false)` 落檔含 `fills:false` | vitest `useChartToggles.test.ts`:新增「舊存檔缺 fills → true 且 v 仍 2」「set fills false 落檔」;既有整包比對兩處(`:19 DEFAULTS`、`:143-150`)**該紅** → 補 `fills: true` |
| SC-3 | 單檔頁主圖:每個 FillMark 畫一個實心三角 `<polygon data-testid="fill-{B\|S}-{minute}">`(key 同字串);買 = ▲ `fill-bull`、賣 = ▼ `fill-bear`;尖端 (x,y) 由 `projectFills` 供給(SC-1);`stroke-surface` halo `strokeWidth=FILL_MARK.halo` `paintOrder="stroke"`;**渲染位置 = `ChartStatic` 內最末一組 `<g data-testid="fills-layer" pointerEvents="none">`(恆 render,空集合時內容為空;testid 刻意不與 `fill-` 前綴共用)[amendment 2026-08-17 r2: R2-1]**(在極值標記 / MA 價位標 / VWAP 標籤 / POC 標籤之後 = ChartStatic 內最上層;現價圈與 hover 層在 ChartStatic 之外仍在其上,接受)[amendment 2026-08-17: R11];`fills` 空或 `toggles.fills=false` → 零 polygon | vitest `StockIntradayChart.test.tsx`:注入 `fills` prop 兩點(B@541、S@542)→ 兩個 testid 存在、class 含 bull/bear、polygon 第一頂點 y ≈ `toY(price)`(同 fixture 反算)、x ≈ minuteToX;窗外分鐘案 0 個;域外價案 0 個;document 順序:`fills-layer` 群組在 `day-high` 與 MA 價位標之後 [amendment: R10/R11] |
| SC-4 | readout(**page 變體限定**):shown 分鐘(hover 或最新分鐘)有 FillPoint 且 `toggles.fills` 開時,欄位列**尾端追加** `{label:"成交", value}`:單側 `買 2@2380` / `賣 1@2385`(tone bull / bear),雙側 `買 2@2380 賣 1@2385`(tone 無);價格文字 = 既有 `fmt(priceMilli)`;無成交分鐘 / toggle 關 → 不追加(六欄不變)。**card 變體不追加**(246px 寬 readout `overflow-hidden`,追加必被裁 = 靜默失敗;標記本身已承載資訊,與 card 砍外/內欄同理)[amendment 2026-08-17: R7/R9][amendment 2026-08-17 cr1: A-2 — readout 與三角同一把尺(欄位吃 `fillMarks` 而非 `fills`),域外/窗外/toggle 關皆不追加] | vitest:page hover 至 541 → readout 含「成交」與「買 2@2380」;hover 無成交分鐘 → 無「成交」;toggle 關 → 無「成交」;`variant.test`:card 有 fills 時 readout 仍 4 欄且不含「成交」 |
| SC-5 | toggle:page 鈕列多一顆「成交點」(`key:"fills"`,available 恆 true、含 stkfut 態);關 → polygon 全消失、readout「成交」欄不追加;圖牆 `GRID_TOGGLES` 多同名一顆「成交點」;card 內仍零 button | vitest:`variant.test.tsx:117` page button 數 4→**5(該紅)**;新案「按成交點 → aria-pressed false 且 0 polygon 且 readout 無成交」;`GroupGridView.test.tsx:559` 五鈕逐名查存在(加「成交點」);toggle test 加「預種 fills:false → 兩卡 per-card `querySelectorAll('polygon[data-testid^="fill-"]')` 皆 0;按鈕 → 同時 >0」(**量法一律 per-card 以 `polygon[data-testid^="fill-"]` 計數,不用 document 級 getByTestId;`fills-layer` 群組不入計數**)[amendment r2: R2-1][amendment 2026-08-17: R13] |
| SC-6 | 群組卡(現股):`GroupGridView` 於圖牆層 `const orders = useCapitalOrders().data?.orders;` `today = ymdOf(new Date())`;`fillsMap = useMemo(() => fillsByCode(orders, fillDates(today), "股"), [orders, today])`,每卡傳 `fills={fillsMap.get(code) ?? EMPTY_FILLS}`(identity 穩定);`GroupCard` memo 契約不破:quotes 每秒換 identity 時,無成交的卡 render 次數與現況相同 [amendment 2026-08-17: R12] | vitest `GroupGridView.memo.test.tsx` 既有 render 計數案**不該紅**;新案(`GroupGridView.test.tsx`):fetch 路由 `/api/capital/orders` 回一筆 2330 成交 → 2330 卡 per-card `polygon[data-testid^="fill-"]` 數 1、2317 卡 0 [amendment r2: R2-1] |
| SC-7 | 單檔頁 key 選擇(`StockChart`):`const orders = useCapitalOrders().data?.orders;` 現貨態 key = 股號、`excludeUnit="股"`;個股期態 key = `stkfutFillKey(contract.prod, contract.ym)`(null → 零標記)、不排除 unit;`today = ymdOf(new Date())`;`fills = useMemo(() => fillPoints(orders, key, fillDates(today), isFut ? undefined : "股"), [orders, key, today, isFut])`(**deps 不放 `contract` 物件**);傳 `<StockIntradayChart fills=…>` [amendment 2026-08-17: R3/R12] | vitest `StockChart.test.tsx`:fetch 路由 orders fixture 含 `{stock_no:"2330"}` 與 `{stock_no:"CDFH6"}`;現貨態只畫 2330 那點;`contract={prod:"CDF",ym:"202608"}` 只畫 CDFH6 那點;零股 fixture(unit "股")現貨態不畫 |
| SC-8 | 真實環境(側車 fake capital + 種子行情):單檔頁 2330 注入 B 2張@某價(10:05)、S 1張(10:40)→ 截圖可指認 ▲ 紅 / ▼ 綠貼在價線上、hover 10:05 readout「成交 買 2@…」;關「成交點」→ 消失;圖牆 2330 卡同步出現;個股期頁選定契約注入 CDF 契約碼成交 → 標到 | 側車 `evidence/sidecar_server.py`(抄 R1 樣板 + `/_fake/fill` D 回報注入)+ vite dev + claude-in-chrome 截圖 `evidence/SC-8-*.png`;**驗證窗口**:不受盤中限制(fake source);**盤中真成交截圖 = user 過目層**(自動化綠燈不算 Done 的那一段) |
| SC-9 | memo 閘 [amendment 2026-08-17: R3]:`ChartStatic` 新增 `fillMarks` prop 後,hover mousemove 連發**不**重建靜態層;`fills` 零筆時 identity 恆 `EMPTY_FILLS`、`fillMarks` 恆 `EMPTY_MARKS` | vitest `StockIntradayChart.test.tsx`:`vi.mock("@/lib/fill-marks", async (importOriginal) => { const actual = …; return { ...actual, fillTrianglePoints: vi.fn(actual.fillTrianglePoints) }; })` —— **delegate 原實作只加計次**(同檔 SC-3 頂點斷言得以共存,樣板 `GroupGridView.geometry.test.tsx:20-23`);fixture 帶 **≥ 2 個窗內且域內** FillPoint;先斷言掛載後 `mock.calls.length === fills 筆數(≥2)`,再連發 3 個 mousemove → 計數不變;反向保險(spec 註記,不寫成測試):把 `fillMarks` 改成行內字面值該案必紅;`fill-marks.test.ts` 鎖零筆 identity [amendment 2026-08-17 r2: R2-2/R2-3] |

## 3. 不能破壞的既有行為白名單(W)

- W-1 後端零改動(`copycat/` 不動;`tests/capital/*`、`tests/server/test_capital_api.py` 不動)。
- W-2 `lib/ladder-lots.ts::aggregateLots` / `ymdWindow` 語意與三梯掛單 / 已成交徽章(PR #46)不變(允許只**新增**輸出 helper,見 §5)。
- W-3 既有 overlay(VWAP / CDP / MA / VP / POC / 高低點 / 現價圈)幾何與 toggle 值不變;`TOGGLES_VERSION` 不 bump(舊存檔 bb/cdp/vp 選擇不被重置)。
- W-4 `ChartStatic` memo:新增 prop 必為穩定 identity(useMemo / module 常數);hover mousemove 不觸發 ChartStatic 重建 —— **既有測試無此機械閘(只有註解)**,本輪以 SC-9 新測試補上 [amendment 2026-08-17: R3]。
- W-5 `GroupCard` memo:quotes 每秒換 identity 不讓無成交卡重畫(`GroupGridView.memo.test` 不紅);card 內零 button(`variant.test:69`、`GroupGridView.test:578`)。
- W-6 readout 既有欄位(page 六欄 / card 四欄)順序、文案、tone 不變;「成交」欄只在有成交的 shown 分鐘**尾端追加**(**page 變體限定;card 恆四欄**,見 SC-4 / R7)[amendment r2: R2-6]。
- W-7 `IntradayChartCore` 不新增 capital / TQ 依賴(`fills` 由 caller 傳入);既有 `StockIntradayChart.test` 的 fetch stub(不分 URL 回 overlay)不需改路由即全綠。
- W-8 stkfut 態既有反灰(cdp/ma/vp)不變;期貨 tab `FuturesChart` 不動。
- W-9 `useCapitalOrders` 契約(30s + WS invalidate)不動;不新增 `enabled` 參數。

## 4. `[auto-default]` 決策(可逆實作選擇,非方向性)

- AD-1 資料流 = **caller 掛 hook + 純函式 → `fills` prop 傳入 core**(非 core 內掛 hook)| reason: 白名單 W-4/W-5「穩定 identity 傳入」+ W-7 core 不沾 capital;既有測試 fetch stub 免改。
- AD-2 日期條件 = `date === 今日` **∨**(`actionable` ∧ `date === 昨日`)(page 現貨 / 個股期 / card 皆同;`dates` 由 `fillDates(ymdOf(new Date()))` 供給)[amendment 2026-08-17: R5/R6;r2: R2-4 收窄活單為昨日建立] | reason: 主圖 x 窗只有日盤(現貨 09:00–13:30 / 個股期 08:45–13:45),夜盤分鐘本來就畫不出來,故不需 ±1 窗;±1 反會把昨日日盤成交畫上今日圖(假陳述);活單只認昨日建立(盤後預約單今日成交 → 梯有徽章、圖也要有點);**不**照搬梯的「活單無界恆計」—— 圖有時間軸,`CapitalStore` 跨日不清時更早的 actionable 幽靈單會在今日圖上畫出假成交,代價高於梯的多一格徽章。殘餘風險:昨日建立、昨日部分成交、今日仍 actionable(理論上收盤即終態)的單會被畫上,接受並明列。個股期有無夜盤**未實證、不作為依據**(`StkfutLadder.tsx:123` 註解稱有)。[amendment 2026-08-17 cr1: A-3 — `date` 為**最新事件日**(`CapitalStore.apply_reply` 每筆回報有值即覆寫),非建立日;殘餘風險改述:前半條即已收到「盤後預約單今日成交」,後半條真正收的是「最後回報停在昨日、今日仍 actionable」的單(其成交發生於昨日,會以昨日均價 × 昨日分鐘畫在今日圖上)]
- AD-3 現股(page 現貨態 + card)`excludeUnit="股"`;個股期不排除 | reason: 與現股梯同口徑(張梯混零股量級差千倍),「我的單」在梯與圖上一致。
- AD-4 合併價 = 量加權平均 | reason: 同分鐘同向兩筆 100@2、101@1 標在 100 或 101 都是假陳述,加權是唯一不偏的一點。
- AD-5 toggle label「成交點」;stkfut 態亦可用 | reason: 成交點不依賴外部資料(orders 手上就有),沒有反灰理由。
- AD-6 三角幾何 `FILL_MARK = { halfW: 3.5, height: 6, halo: 1 }`(由 `INTRADAY_MARK.dot.radius 2.5` 推:外緣半徑 3 → 高 6、半寬 3.5);尖端在成交價 y,買體在下 / 賣體在上;x 夾制走 fill-marks 自帶 `clampFillX`(不複用 `markCenterX`,型別不相容)[amendment 2026-08-17: R8];尖端 y 不夾(R10) | reason: prompt「尺寸沿 INTRADAY_MARK」;尖端指價位是 D8 原文。
- AD-7 readout「成交」欄文案 `買 n@價` / `賣 n@價`,雙側以單一空格連接;不帶單位 | reason: readout 既有欄位皆無單位;D8 原文即此格式。
- AD-8 孤兒分鐘(FillPoint 分鐘在 `accum.minutes` 無格,如尾段事件為刪單而該分鐘無成交、或 card snapshot 缺格):標記照畫(x/y 只需 minute/price),readout 只在 shownAgg 存在時才有機會追加(既有 readout 契約:無 agg 顯示 `-`) | reason: 標記語意不依賴分鐘成交;readout 契約不為孤兒案改。
- AD-9 `today` 字串由 caller 每 render 算(`ymdOf(new Date())`,新增於 `ladder-lots.ts` 並讓 `ymdWindow` 改用同一 helper — 🔵;`ymdOf` 補 2 案(補零 / 跨月末),`ymdWindow` 既有案 `ladder-lots.test.ts:175` 接住輸出逐字不變)[amendment 2026-08-17: R12] | reason: 跨午夜開著頁面時 useMemo deps 以字串比對自然失效重算;`ymdWindow` 內部日期格式化與新 helper 同源不重抄。
- AD-10 `EMPTY_FILLS: readonly FillPoint[] = []` module 常數(fill-marks.ts 匯出);core 的 `fills` 預設值即它 | reason: 無成交時 identity 穩定,memo 不打穿。

## 5. Diff 級章節(逐檔;三類標記)

| 檔 | 類 | 動什麼 |
|---|---|---|
| `frontend/src/lib/ladder-lots.ts` | 🔵 | 新增 `export function ymdOf(d: Date): string`(YYYYMMDD);`ymdWindow` 改呼叫它(輸出不變) |
| `frontend/src/lib/fill-marks.ts`(新) | 🟢 | SC-1 全部匯出:`FillPoint` / `FillMark` / `FillDates` / `fillDates` / `FILL_MARK` / `EMPTY_FILLS` / `EMPTY_MARKS` / `fillPoints` / `fillsByCode` / `stkfutFillKey` / `clampFillX` / `fillTrianglePoints` / `projectFills` / `fillsAtMinute` / `fillLabel`(純函式,零 React)[amendment: R9/R12] |
| `frontend/src/hooks/useChartToggles.ts` | 🟢 | `ChartToggles.fills`;`DEFAULTS.fills = true`;註解說明免 bump 理由沿 vp 條 |
| `frontend/src/components/stock/StockIntradayChart.tsx` | 🟢 | `CoreProps.fills?: readonly FillPoint[]`(預設 `EMPTY_FILLS`)+ `Props`(page 薄殼)透傳;`fillMarks = useMemo(() => (toggles.fills ? projectFills(fills, g, w, xw) : EMPTY_MARKS), [fills, g, w, xw, toggles.fills])`;`ChartStatic` 新 prop `fillMarks: readonly FillMark[]`,於 ChartStatic **最末一組** `<g data-testid="fills-layer" pointerEvents="none">`(恆 render)渲染 polygon;**`fillMarks` useMemo 必置於 `g` 之後、`priceLine.length === 0` 早退之前(hook 不可條件化;repo 無 react-hooks lint)[amendment r2: R2-8]**;`toggleDefs` 加 `{key:"fills", label:"成交點", available:true}`;readout:`fillField = !card && toggles.fills && shownMin !== null ? (pts = fillsAtMinute(fills, shownMin); pts.length ? {label:"成交", value: fillLabel(pts, fmt), tone} : null) : null`,`fields = (card ? allFields.slice(0,4) : allFields).concat(fillField ? [fillField] : [])` [amendment: R7/R9/R11] |
| `frontend/src/components/stock/CardIntradayChart.tsx` | 🟢 | Props 加 `fills: readonly FillPoint[]`,透傳 core |
| `frontend/src/components/stock/GroupGridView.tsx` | 🟢 | 圖牆層(**置於 `groups.length === 0` 早退之前**,hook 不可條件化 [amendment r2: R2-8])`const orders = useCapitalOrders().data?.orders;` `today = ymdOf(new Date())`;`fillsMap = useMemo(() => fillsByCode(orders, fillDates(today), "股"), [orders, today])`;`GroupCard` props 加 `fills`(memo;`fillsMap.get(code) ?? EMPTY_FILLS`);`GRID_TOGGLES` 加 `fills` [amendment: R12] |
| `frontend/src/components/stock/StockChart.tsx` | 🟢 | `const orders = useCapitalOrders().data?.orders;` `const today = ymdOf(new Date());` `const key = isFut ? stkfutFillKey(contract.prod, contract.ym) : code;` `fills = useMemo(() => fillPoints(orders, key, fillDates(today), isFut ? undefined : "股"), [orders, key, today, isFut])`;傳 `<StockIntradayChart fills=…>` [amendment: R12;r2: R2-4 fillDates] |
| **測試(新 / 改)** | | |
| `lib/fill-marks.test.ts`(新) | 🟢 [red→green] | SC-1 全案 |
| `hooks/useChartToggles.test.ts` | 🟢 | SC-2 新案;**該紅**:`:19 DEFAULTS` 加 `fills: true`、`:143-150` 整包加 `fills: true` |
| `components/index/MarketChart.test.tsx:40` / `MarketPane.test.tsx:40` / `MarketPane.size.test.tsx:73` / `StockIntradayChart.variant.test.tsx:49` | 🟢 | **該紅(tsc,非 vitest)**:`const TOGGLES: ChartToggles = {…}` 整包 literal 缺 `fills` → TS2739;各補 `fills: true`(schema 擴充事前標記)[amendment 2026-08-17: R1] |
| `lib/ladder-lots.test.ts` | 🔵 | 新增 `ymdOf` 2 案(補零 / 跨月末);`:175` `ymdWindow` 既有案**不該紅**(輸出逐字不變)[amendment: R12] |
| `components/stock/GroupGridView.geometry.test.tsx` | — | **不該紅**:`buildIntradayGeometry` 計次不受 `fills` prop 影響(fills 走獨立 useMemo);其 fetch stub 對 `/api/capital/orders` 回 `{states:{}}` → `data.orders` undefined → `fillsByCode(undefined)` 空 map → 每卡 `EMPTY_FILLS` [amendment: R4] |
| `components/stock/StockChart.futconverge.test.tsx` | — | **不該紅(無條件)**:`:105/:126` 斷言是 `renders.filter((v) => v === false)).toEqual([])` 存在性判定,與紀錄格數無關;新增 query 的 settle re-render 不會讓它紅 [amendment: R4;r2: R2-7 刪逃逸口] |
| `PriceLadder.test.tsx` / `StkfutLadder.test.tsx` / `FuturesLadder.test.tsx` | — | **不該紅**:`aggregateLots` / `ymdWindow` 輸出不變 [amendment: R4] |
| `components/stock/StockIntradayChart.test.tsx` | 🟢 [red→green] | SC-3 / SC-4 / SC-5(page 關閉案);memo 案不該紅 |
| `components/stock/StockIntradayChart.variant.test.tsx` | 🟢 | **該紅**:`:117` 4→5;新案 card readout 成交欄 |
| `components/stock/GroupGridView.test.tsx` | 🟢 | `:559` 加「成交點」鈕查存在(不該紅,只擴充) |
| `components/stock/GroupGridView.toggle.test.tsx` | 🟢 [red→green] | SC-5 圖牆 fills 案(fetch 路由需加 `/api/capital/orders`) |
| `components/stock/GroupGridView.memo.test.tsx` | — | 既有計數案**不該紅**(fetch stub 對 orders URL 回 `{states:{}}` → `orders` undefined → EMPTY);SC-6 新案另寫於 `GroupGridView.test.tsx`(路由 orders fixture) |
| `components/stock/StockChart.test.tsx` | 🟢 [red→green] | SC-7 三案 |
| `components/stock/CardIntradayChart` | — | 無獨立測試檔;由 GroupGridView 測試涵蓋 |

**該紅清單(事前標記,鐵則 E 合法通道)**:`useChartToggles.test.ts:19,143-150`(schema 加鍵)、`StockIntradayChart.variant.test.tsx:117`(4→5 鈕)、tsc 層四檔 `ChartToggles` 整包 literal(`MarketChart.test.tsx:40` / `MarketPane.test.tsx:40` / `MarketPane.size.test.tsx:73` / `StockIntradayChart.variant.test.tsx:49`)[amendment 2026-08-17: R1]。其餘既有測試皆**不該紅**;紅了 = 打到白名單,回 spec。
順序:🔵(`ymdOf`)→ 🟢(fill-marks + toggles + core + callers,依 TDD red→green 拆 commit)。無 🔴。

## 6. Edge cases(≥3)

1. 同分鐘同向兩筆(avg 100.0 元@2 + 101.0 元@1 → 毫元 100000@2 + 101000@1)→ 一點 qty 3、priceMilli = round(100333.33) = 100333;readout「買 3@100.33」(`fmt(100333)`)[amendment: R2]。
2. 同分鐘買賣各一 → 兩個 polygon(▲▼ 同 x 不同 y);readout 雙側文案。
3. `time` 落在窗外(現股 13:30 後盤後零股 14:30、或期貨態 08:44 前)→ 不畫、readout 不追加。
4. `avg_fill_price === null` 但 `filled_qty > 0`(回報欄位缺)→ 跳過。
5. 個股期 `futExchangeContract` throw(合約 ym 非法)→ key null → 零標記、不白屏。
6. capital 未設定 / `/api/capital/orders` 500 → `orders` undefined → 零標記,圖照畫(TQ error 不冒泡)。
7. 跨午夜開著頁面 → 下一 render `today` 變 → 昨日成交點消失。
8. 委託 `unit==="股"` 現股 → 不畫;個股期單位「口」照畫。
9. `filled_qty>0` 且 `actionable`(部分成交活單)→ 照畫(既成事實)。
10. 昨日建立、今日成交中的預約單(`date` = 昨日、`actionable` true、`filled_qty>0`)→ 照畫;昨日的終態單 → 不畫;**前日(或更早)建立仍 actionable** → 不畫;昨日建立昨日成交今日仍 actionable → 會畫(殘餘風險,理論上收盤即終態)[amendment: R5;r2: R2-4][amendment 2026-08-17 cr1: A-3 — `date` 為最新事件日,非建立日;本條「建立」一律讀作「最新事件」。另一殘餘風險:昨日部分成交、今日刪單的單 `date` 變今日,會以(今日刪單分鐘 × 昨日均價)畫上今日圖 —— 日期界躲不掉,唯一乾淨解 = 精確版逐筆 D 事件]。
11. `priceMilli` 落在 `g.yDomain` 外(autofit 域 / card 較窄域)→ 不畫(同 overlay / 極值規則)[amendment: R10]。
12. 圖牆兩卡同分鐘各有成交 → 各卡各自 polygon;測試以 per-card 計數 [amendment: R13]。

## 7. Out of scope

- 精確版(後端逐筆 D 事件 / `GET /api/capital/fills`)→ next-time。
- 期貨 tab `FuturesChart` 成交點 → next-time。
- 群組卡個股期委託(契約碼→股號反查)→ 精確版一併。
- 三梯掛單 / 已成交徽章任何變更;`useCapitalOrders` 契約變更。
- 群益 APP 下的單的 `price_type`(恆 null)不影響本輪(不看 price_type)。

## 8. Backward compat / migration

- toggles 存檔加鍵免 bump(既有規則),舊存檔自動補 `fills:true`;可逆(移除鍵即回舊 schema,`{...DEFAULTS,...saved}` 多鍵不炸)。
- 無 API / 資料格式 / localStorage key 變更;無 migration。

## 9. 執行約束(沿前輪指示)

- UI 一致性優先:只用既有 token(`fill-bull` / `fill-bear` / `stroke-surface`),不新增色票 / 動效;字級與既有 readout 同。
- 白名單 W-4/W-5 的 memo 契約以既有 memo 測試為機械閘;新 prop 一律 useMemo / module 常數。
- 收尾:next-time 追加精確版 + FuturesChart 兩條;memory `user-feedback-batch-2026-08-17` 勾 R2;batch3 spec §0 個2 標已出貨。
