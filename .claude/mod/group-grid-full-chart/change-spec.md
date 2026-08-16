# change-spec — 群組圖牆分時圖改單檔同款 + 點卡片只切閃電目標(R4)

分流判定:**已成形方案**(prompt 指名做法:`variant="card"`、toggle 上提 GroupGridView、
onPick 去 `selectView("single")`;D3/D4 已拍板)→ grilling 姿態,逐題 `[auto-default]`。
現況表:`current-state.md`(同目錄)。

## 0. 拍板 / auto-default 清單

| # | 決策 | 選擇 | 理由 |
|---|---|---|---|
| D3(user) | 進單檔的路徑 | 只靠檢視 pill | prompt 拍板 |
| D4(user) | 卡片圖同款程度 | 完全同款;toggle 列在圖牆頂放一份 | prompt 拍板 |
| AD-1 | 卡片圖缺的 vwap/high/low/vp 資料從哪來 | `[auto-default: 後端 light_snapshot 加 4 鍵(vwap/high/low/vp);**vp 由 StockDayState 增量維護**(`_apply` 每 tick 累加、`reset` 清空、`apply_backfill` 走 reset+重放自然重建),light_snapshot 只序列化 \| reason: 「完全同款」含 VP+POC/VWAP 標籤/高低點,而 group-state 刻意不送 ticks(頻寬);前端由 minutes 近似會畫出與單檔不同的圖 = 違反 D4。加鍵 additive,舊前端不讀新鍵、新前端 `?? null` 降級舊後端]` `[amendment 2026-08-16: review R6 — 原「請求時全掃 ticks」跑在事件迴圈,最壞 50×20k 同步迴圈會卡 WS fanout;改增量維護 O(1)/tick。review R10 — 拿掉 `last` 鍵(前端無讀者),現價由 liveP 承載]` |
| AD-2 | 後端 vp 折法與前端 `foldVp` 對齊 | `[auto-default: 同規則(剔 p<=0、分鐘窗 [540,810]、key=向下 snap 到 tick 檔、cell {t,o,i});以**共用 fixture** 鎖 parity(`tests/fixtures/vp_parity.json`:ticks + 期望直方圖;pytest 讀之斷言後端 vp;vitest 以 `node:fs` `readFileSync` 讀同檔斷言 **export 後的** `foldVp`)\| reason: 兩份折法各漂的樣態是「同一檔在單檔頁與卡片上 POC 不同」,零錯誤訊號]` `[amendment 2026-08-16: review R9 — foldVp 現為模組私有需 export;跨語言共讀 fixture 在本 repo 是新做法(breadth parity 為 pytest 單邊),tsconfig 無 resolveJsonModule 故 vitest 用 fs 讀不 import。review R14 — parity 保證範圍 = 「同一輸入折法一致」;後端改增量維護後 vp 不受 `ticks` deque(maxlen 20k)截斷影響,與前端「不截斷」同源;殘餘差異來源:(1) 單檔頁 WS 逐 tick vs 卡片 60s 快照的**時間差**(AD-9);(2) `[amendment 2026-08-17: round 2 R2-5]` >20k tick 日單檔頁 vp 折自 `/api/stock/state` 已被 deque 截斷的 ticks 而偏小(stock-accum.ts:118 既有 characterization),本輪不處理、記 next-time]` |
| AD-3 | 卡片尺度 | `[auto-default: variant="card" 以 useContainerSize 量卡片圖區 wrapper(高度由外層指派),**主副圖共用單一寬 `w` = 量到的 px 寬**(1:1);可用高 = 量到高 − `CARD_CHROME`(readout 列 22 + mb-1 4 = 26,常數收 `lib/chart-frame.ts` 與 CHART_FRAME 同檔),再按 260:70 拆(減法保證相加等於可用高;`[amendment 2026-08-17: round 2 R2-1]` 可用高先 −2 安全邊同 svgBox;**不做幾何降級**(y 刻度減量會動共用 ChartStatic 波及 W-1),小格可讀性以 SC-1 三張截圖(2×2 最好格 / 4×4 user 實機 / 4×4 1080p 模擬)驗收,1080p 4×4 若不可讀 → next-time 記「卡片變體刻度減量」並回報,不擋出貨);**量到之前不畫圖(佔位空白,同 svgBox `usable=false` 慣例)**;jsdom 走同一佔位分支 → 元件測試以「量測後」路徑用 props 直給尺寸(core 測試)或 mock RO 尺寸 \| reason: 800 寬 viewBox 掛進 250px 卡片字高縮成 3px,不可讀;1:1 讓 rem 字級與單檔頁同量級]` `[amendment 2026-08-16: review R2 — 副圖 SUB.width 一併參數化(同 w);R3 — 扣 chrome 否則溢軌打破 W-2;R12 — 首幀不畫避免 800→1:1 跳動]` |
| AD-4 | 卡片變體省略哪些 chrome | `[auto-default: 省略 toggle 鈕列(移圖牆頂)、figcaption 說明列(外/內盤/判定率/VWAP 文字)、figure 的 border/bg/p-4;**card 變體外層用 `<div>` 不用 `<figure>`**;readout 保留 4 欄(時間/價/%/量),外/內兩欄省略 \| reason: 卡片 250px 寬裝不下六欄 + 說明列;圖形語彙(線/標籤/軸/hover)全同,文字 chrome 精簡不算「不同款」]` `[amendment 2026-08-16: review R11 — 卡片外層 `<button>` 內容模型為 phrasing content,改 GroupCard 外層為 `<div role="button" tabIndex={0} aria-label aria-pressed onClick onKeyDown(Enter/Space)>`;既有 `card.tagName==="BUTTON"` 斷言為 test-infra 調整(改 role);`g.priceLine.length===0` 早退框在卡片內不出現 — 見 edge 9]` |
| AD-5 | 圖牆頂 toggle 列的可用性 | `[auto-default: 四鈕(均價/CDP/MA/量分佈)恆可按;個別卡片 overlay 不可得時該卡不畫(不反灰整列) \| reason: 可用性是 per-code 的,整列反灰要選「任一/全部」語意都會誤導]` `[amendment 2026-08-16: review R5 — `cdp` 預設 true,進群組冷 cache 會對 ≤50 檔併發 `daily_bars`(to_thread 無上限,共用 TC4 歷史通道);對策 = **`/api/stock/overlay` route 層** `asyncio.Semaphore(4)`(app 實例屬性,包住 `stock.daily_bars` 呼叫;`[amendment 2026-08-17: round 2 R2-3]` engine.daily_bars 另有 caller `signal_hub.py:662`(basis 取數),節流放引擎會拖慢訊號 basis,故只擋 overlay 路徑),SC-6 加冷 cache 進群組 overlay 總耗時量測]` |
| AD-6 | 選中態視覺 | `[auto-default: 卡片 button aria-pressed={code===active} + border-accent + ring-1 ring-accent;hover 仍 border-accent \| reason: 沿 pill 既有 aria-pressed 慣例]` |
| AD-7 | >16 檔分支(auto 列軌)的量測迴圈 | `[auto-default: 卡片固定高 h-56 (14rem);≤16 分支維持 1fr 列軌吃滿 \| reason: useContainerSize 契約要求被量元素高度由外層指派]` |
| AD-8 | 卡片 hover 是否跨卡同步 | `[auto-default: 不同步(各卡獨立) \| reason: 非 prompt 需求,out of scope]` |
| AD-9 | 卡片資料節奏 | `[auto-default: 沿現行 60s snapshot + 每秒 liveP 末點延伸(現價圈與末點同源 liveP);VWAP/VP/高低/CDP 60s 才更新 \| reason: 資料面設計(design R1/R10)不在本輪;渲染同款不等於資料流同款,change-spec 明列此差異]` |

## 1. 成功條件(SC)

| SC | 內容(畫面可指認) | 驗證方式 |
|---|---|---|
| SC-1 | 圖牆每張卡片是單檔同款分時圖:左緣價位刻度 + 漲跌停亮燈、右緣 CDP `*` 標 / MA 名、繪圖區內側右緣 MA 價位、VWAP 白線 + 末點價位標、左側 VP 水平條 + accent POC 與價位字、日高/日低空心圈 + 價位、現價實心圈、底部整點時間標、下方量能副圖;hover 出十字線 + 左價標 + 底部時間/價標,頂列 readout 四欄跟著游標 | vitest:`GroupGridView.test.tsx` 掛真元件查 `edge-price-vwap`/`vp-bar`/`day-high`/`last-dot`/`y-tick-price`/`energy-bar` testid;截圖三張 `evidence/SC-1-2x2.jpg`(最好格)/ `SC-1-4x4.jpg`(user 實機視窗)/ `SC-1-4x4-1080p.jpg`(1080p 模擬)+ user 過目;4×4 判準 = 刻度文字不互疊、時間標可讀 |
| SC-2 | 圖牆頂(群組 pill 列右側)有一列四鈕「均價 / CDP / MA / 量分佈」,按下任一鈕 → 圖牆**全部**卡片同步顯示/隱藏該層;重整後狀態保留;單檔頁切 toggle 後切到群組檢視 → 圖牆狀態一致(同一 localStorage key) | vitest:GroupGridView 測「按量分佈 → 每卡 `vp-bar` 群組出現/消失」+「localStorage 種 `{vp:false}` → 掛載後無 vp-bar」;截圖 `evidence/SC-2-toggle-row.png` |
| SC-3 | 點卡片:檢視**仍停在「群組」**(pill 群組 aria-pressed=true、`選擇群組` 群組列仍在、無 header/五檔/明細),被點卡片出現 accent 選中框(aria-pressed=true,其他卡 false),右欄閃電梯標的變成該股號,主圖訂閱換檔(打 `/api/stock/state/<code>`) | vitest:`StockPage.test.tsx:691-701` 改寫為「點卡片 → onSelect + 檢視仍群組」;`GroupGridView.test.tsx` 加 `active` 選中態;`App.test.tsx` 加全鏈「群組檢視點卡片 → fetch `/api/stock/state/2317` + 主檔 localStorage=2317 + 群組列仍在」;截圖 `evidence/SC-3-card-selected.png` |
| SC-4 | 單檔頁分時圖**逐像素行為不變**:props 簽名相容(`accum/mainHeight/subHeight/stkfut`),toggle 四鈕仍在頂列、說明列仍在、hover 全同 | vitest 既有 `StockIntradayChart*.test.tsx` 全綠不改 assertion;🔵 commit 前後單檔頁截圖對照 `evidence/SC-4-single-before.png` / `SC-4-single-after.png` |
| SC-5 | `GET /api/stock/group-state` **回應**每檔多 `vwap`/`high`/`low`/`vp` 四鍵(`vp` = `{ "<priceMilli>": [t, o, i] }` 緊湊陣列);`vp` 與前端 `foldVp` 對同一份 tick fixture 折出**同一直方圖** | pytest:`tests/live/test_stock_state.py` light_snapshot 四鍵 + 增量維護(ingest / reset / apply_backfill 重建)+ parity fixture;**`tests/server/` 端點層契約測試鎖 group-state 回應含四鍵**(review R1);vitest:`stock-accum.test.ts` 以 fs 讀同 fixture 斷言 `foldVp`;curl 實測 `/api/stock/group-state?codes=<自選>` 含新鍵 |
| SC-6 | 量化(全部記 verification.md):(a) payload:**未壓縮** bytes(`curl -s -o NUL -w '%{size_download}'`,無 GZipMiddleware 不量 gzip),以現有最大群組實測 + 換算 50 檔上界 ≤ 1.5 MB;超標降級 = vp 改 t-only(`[t]`)並記錄;(b) overlay 請求數 = 卡片數(每 code 每日一次;**5 分鐘內**切回群組檢視 0 新請求 — TQ gcTime 5 min);(c) 冷 cache 進群組(cdp 開)overlay 全部回齊的總耗時(DevTools network waterfall,Semaphore(4)下);(d) 渲染:vitest spy `buildIntradayGeometry` 次數 — 掛 4 卡後 hover 一張卡 mousemove 3 次,幾何重算次數 0(useMemo 護欄);(e) `[amendment 2026-08-17: round 2 R2-2]` 每秒 liveP 路徑:fake server 16 卡、2s 推播下 DevTools Performance 錄 10s,主執行緒 scripting+rendering 佔比 < 30% 且無連續 >50ms long task;超標對策 = CardIntradayChart 對 liveP 做 5s 量化(`Math.floor(Date.now()/5000)` 入 useMemo deps 降頻),記錄採用與否 | 記數字;超標處置寫在同列 |
| SC-7 | 既有矩陣佈局不變:2×2~4×4 佔滿中區不捲動、>16 四欄外層捲動且卡片不溢軌(固定高)、群組 pill + `STOCK_GROUP_KEY` 記憶 | vitest 既有 `GroupGridView.test.tsx` gridShape / pill 測試不改;截圖 `evidence/SC-7-4x4.png` + `SC-7-17cards.png` 目視無溢出 |

驗證窗口:SC-1/2/3 截圖需 server 有 minutes 資料 — 非交易日 R3 已讓 trade_date 落最近交易日,
盤外可用最近交易日資料截圖;若 prod 8721 記憶體無資料(未回補),降級 = 側車 `--verify`
假資料 server(ops-discipline)截圖 + 標註「盤中待 user 過目」。

## 2. 不能破壞的既有行為白名單(W)

- W-1 單檔頁分時圖一切不變(SC-4):props、toggle 鈕位置與反灰語意、readout 六欄、說明列、hover、`useStockOverlay` 兩道閘(`!stkfut && !isInstrumentKey`)、期貨態 x 窗與 VP/overlay 全停。
- W-2 矩陣佈局(PR #50):`gridShape` 靜態字面值、`minmax(8rem,1fr)`、`content-start`、>16 捲動;群組 pill 切換與 `STOCK_GROUP_KEY` 記憶;`選擇群組` aria-label 契約(StockPage.test 四處靠它)。
- W-3 群組檢視不渲染五檔 / 明細 / header(`StockPage.test.tsx:662-671`)。
- W-4 右欄 ladder 三梯互斥掛載;`onSelect` 仍觸發主圖訂閱換檔(`useStockStream` → `/api/stock/state/{code}` set_main)。
- W-5 `GroupCard` memo + `pickRef` 穩定化(memo.test 鎖 quotes 每秒換不重畫別張);`useGroupSnapshots` 不 set_main、60s、盤外停、`retry:false`;卡片三態(回補中 / 無資料 / 常態)語意與優先序。
- W-6 `extendMinutes` 三道限制(窗外不延伸 / liveP≤0 不延伸 / 只覆寫 c、不污染 TQ cache)行為原樣搬家。
- W-7 `useChartToggles` localStorage key / schema(`{vwap,cdp,ma,bb,vp}`)不變;`set()` 重讀合併語意不變。
- W-8 `/api/stock/group-state` 既有四鍵(minutes/meta/no_data/backfilling)語意與 no_data 推導式不變;不 set_main、不改訂閱池、回補入列四道 guard 不變。
- W-9 `/api/stock/state/{code}` 全量 snapshot 不變(ticks 仍在,vp 仍由前端折)。
- W-10 IndexPage / MarketPane 的 toggles 上提樣板不受影響(不動 useChartToggles 的 API)。

## 3. Backward compat / migration

- 後端 group-state 加鍵:additive;新前端對舊後端 `vwap/high/low/vp` 缺 → `null`/空 Map 降級(卡片畫線與面積,不畫 VWAP 標/VP/高低)。無 cache 版本要 bump(group-state 不落檔)。
- 前端無資料格式遷移;localStorage 無新 key(toggle 沿 `CHART_TOGGLES_KEY`,群組沿 `STOCK_GROUP_KEY`)。
- 可逆:revert 兩側 commit 即回復;無持久化副作用。

## 4. Out of scope

- 卡片 hover 跨卡同步(AD-8);卡片資料改 WS 逐 tick(AD-9);同步率 badge(next-time 既有);
  MiniIntradayChart 的 ±10% 域 → autofit 議題(next-time 2026-08-06)隨本輪換元件自然消滅
  (單檔同域),收尾時在 next-time 勾銷;外/內盤分色 VP;圖牆頂 toggle 列的 per-code 反灰。

## 5. Edge cases

1. 群組成員 `no_data` / `backfilling` 且 minutes 空 → 卡片仍走既有「無資料 / 回補中…」佔位,不掛圖(W-5)。
2. 舊後端(無新鍵)→ 卡片退化為線 + 面積 + 軸,VP toggle 開著也無 bar(`vp` 空 Map)。
3. `liveP` 有值但 minutes 空(盤前只有參考價)→ `extendMinutes` 窗外不延伸;窗內延伸成單點 → 幾何 `priceLine.length===1`,現價圈畫在該點(單檔頁同行為)。 `[amendment 2026-08-17: 包 C 實作]` edge 9 的判準以**未延伸**的 snapshot 分鐘為準 → 09:00 後首個 60s 快照到達前、liveP 已有值的窄窗,卡片顯示「尚無成交」而非單點圖(單點圖資訊量趨零;避免 GroupCard 重跑一次 extendMinutes)。edge 9 優先於本條。
4. 卡片 code 的 overlay 404/500 → 該卡 `cdpAvailable=false` 不畫,其他卡不受影響;圖牆頂鈕不反灰(AD-5)。
5. 群組 >16 檔 → 卡片固定高(AD-7),量測值恆定,不觸 ResizeObserver loop。
6. `active` 不在當前群組 → 無卡片選中(全 aria-pressed=false)。
7. 主 tab hidden(RO 回 0×0)→ `useContainerSize` 保留舊值(既有行為),切回不跳尺寸。
8. 兩張卡同 code(不同群組不會同時掛;同群組內 codes 唯一 by watchlist 模型)→ 不特處理;svg clip id 走 `useId` 天然唯一。
9. `[amendment 2026-08-16: review R11]` 已訂閱、非 noData、非 backfilling 但**窗內無分鐘**(`[amendment 2026-08-17: round 2 R2-6]` 判準 = 新 export `hasWindowedMinutes(minutes, SPOT_WINDOW)`(stock-intraday-svg.ts 包 windowedEntries),不是 `minutes.size===0` —— 盤前只有 08:59 / 盤後 13:31+ 的窗外分鐘同樣 priceLine 空)→ GroupCard **自佔位「尚無成交」**(同既有佔位樣式),不掛圖 —— 不進 StockIntradayChart 的早退框(那塊帶 border/bg 會在卡片內變框中框)。
10. `[amendment 2026-08-16: review R10]` `liveP` null/≤0 → `accum.last` 退回 minutes 最後一格 close(`{p: c, t: hhmm, cum_vol: 0}`);minutes 也空 → null(不會走到,edge 9 已擋)。

## 6. Diff 級章節(逐檔;三類標記)

### 🔵 A. StockIntradayChart variant 化(行為不變)
- `frontend/src/components/stock/StockIntradayChart.tsx`
  - 抽出受控核心 `IntradayChartCore`(同檔 export)接 `toggles: ChartToggles`、
    `onToggle?(key, v)`、`variant: "page" | "card"`、`width?`(預設 800,**主副圖共用**,
    取代 `MAIN.width`/`SUB.width` 兩個常數的讀點;review R2)、`mainHeight?`、`subHeight?`、
    `stkfut`、`accum`;既有 `StockIntradayChart(props)` 保持簽名,內部 `useChartToggles()`
    後轉呼叫 core with `variant="page"`。
  - `variant="card"`:不 render toggle 鈕列;外層 `<div>`(非 figure)且無 border/bg/p-4;
    不 render figcaption;readout 只給前 4 欄。**`variant="page"` 輸出 DOM 與現況逐節點相同**。
  - `MAIN.width`/`SUB.width` 硬編處全部改吃 `w`(`barW`/`minuteToX` 已參數化;:958-959 註解
    「兩常數碰巧相等」改述為「同一變數」)。
  - 測試:既有 `StockIntradayChart*.test.tsx` 全部**不該紅**;新增 `StockIntradayChart.variant.test.tsx`
    鎖「card 變體無 toggle 鈕 / 無 figcaption / readout 4 欄 / 外層非 figure / 主副 svg viewBox
    寬相等且 = width prop;page 變體有 toggle + figcaption + figure」。
- `frontend/src/lib/stock-accum.ts`:`export` 既有 `foldVp`(review R9);新增
  `export function accumFromGroupSnapshot(code, snap, liveP)` → `StockAccum`
  (minutes=extendMinutes(snap.minutes, liveP)、last = liveP>0 ? {p:liveP,t:hhmm(now),cum_vol:0}
  : minutes 最後一格 close(edge 10)、vwap/high/low/vp 由 snap(缺 → null / 空 Map)、
  ticks=[]、book=null、seq=0、trial=false、amountMilli=0、volume=0、noData=snap.noData)
  — 純函式,先寫紅測(含缺鍵降級 + last 兩分支)。
  `extendMinutes` 由 MiniIntradayChart 搬到 `lib/stock-accum.ts`,測試從
  `MiniIntradayChart.test.tsx` 搬到 `stock-accum.test.ts`(assertion 不變)。
- `frontend/src/lib/chart-frame.ts`:加 `CARD_CHROME = { readoutRow: 26 }`(review R3)+
  `cardSvgBox(size) → {width, mainH, subH, usable}`(可用高 = h − 26,260:70 減法拆;
  w<=0/h<=26 → usable=false)+ 單元測試。

### 🟢 B. 後端 light_snapshot 加鍵 + parity fixture
- `copycat/market.py`:新增 `snap_down_milli(price_milli)` = floor 到 `tick_size_milli` 檔。
- `copycat/live/stock_state.py`:`StockDayState` 加 `_vp: dict[int, list[int]]`(key=snap 檔位,
  value `[t,o,i]`),`_apply` 內累加(剔 `price_milli<=0`、分鐘窗 540..810 — 與前端 `foldVp`
  同規;分鐘由 `tick.time` "HH:MM:SS" 取)、`reset` 清空(`apply_backfill` 走 reset+重放自然重建);
  `light_snapshot()` 加 `vwap`/`high`/`low`(同 `snapshot()` 口徑)+ `vp`(`{str(price): [t,o,i]}`)。
  `_EMPTY_LIGHT`(`stock_engine.py:49`)**由 `light_snapshot()` 衍生、自動涵蓋新鍵,不得改寫成
  字面 dict**(review R13);只需測空狀態 vp=={}、其餘 None。
- `copycat/server/stock_engine.py::group_snapshot`(:618-623):out 改 `{**light, "no_data": …,
  "backfilling": …}`(review R1,鍵名單一定義);`daily_bars` **不動**(round 2 R2-3)。
- `copycat/server/app.py` `/api/stock/overlay/{code}` route:`overlay_sem = asyncio.Semaphore(4)`(create_app 內建,與 overlay_cache 同層)包住 `stock.daily_bars(code)`;測試 = fake source 計 in-flight 峰值 ≤ 4(8 個併發 request)。
- `tests/fixtures/vp_parity.json`:`{"ticks":[{t,p,q,side}...], "expected":{"<price>":[t,o,i]}}`
  含:窗外 tick(08:59 / 13:31)、p=0 市價、跨 tick 段價位(99.9/100/1005 元)、inner/outer/
  neutral side、同價多筆累加。
- `tests/live/test_stock_state.py`:紅測 light_snapshot 四鍵 + vp 增量(ingest 累加 / reset 清 /
  apply_backfill 重建後與重放一致)+ parity(讀 fixture 逐筆 ingest 後 `light_snapshot()["vp"]`
  === expected);`tests/test_market.py` `snap_down_milli` 邊界(1_000_000 → 1_000_000;
  999_999 → 999_000;23_456 → 23_450;9_990 → 9_990)。
- `tests/server/test_stock_group_state.py`(或既有 group-state 測試檔):端點回應每檔含四鍵、
  既有四鍵不變;overlay route semaphore 上限測試(8 個併發 request,fake source `fetch_daily_bars` 內計 in-flight 峰值 ≤ 4)。
- `frontend/src/lib/stock-accum.test.ts`:`node:fs` `readFileSync(path.resolve(__dirname,
  "../../../tests/fixtures/vp_parity.json"))` 斷言 `foldVp` 逐筆折後 Map === expected(值比較
  `{t,o,i}` ↔ `[t,o,i]`)。
- `frontend/src/hooks/useGroupSnapshots.ts`:`GroupSnapshot` 加 `vwap/high/low: number|null`、
  `vp: Map<number, VpCell>`(由 `{price:[t,o,i]}` 轉;缺鍵 → null / 空 Map);測試補欄位解析。

### 🔴 C. 圖牆換元件 + 點卡片不跳單檔
- `frontend/src/components/stock/GroupGridView.tsx`
  - Props 加 `active: string | null`;上提 `useChartToggles()`,pill 列右側 render toggle 四鈕
    (`aria-pressed`,label 同單檔;`data-testid="grid-toggle-<key>"`)。
  - `GroupCard` 加 `active: boolean`、`toggles`(**不傳 `set`**:toggle 鈕在圖牆頂,卡片
    只讀;`useChartToggles.set` 每 render 新 identity,傳進 memo 卡片會打穿 memo);
    core 的 `onToggle` 在 card 變體為 optional / 不用;
    `aria-pressed={active}`;**外層改 `<div role="button" tabIndex={0} aria-label … onClick
    onKeyDown(Enter/Space → onPick)>`**(review R11;既有 `tagName==='BUTTON'` 斷言改
    role,test-infra);class 加選中框;圖區:`minutes.size===0` → 佔位「尚無成交」(edge 9),
    否則 `<CardIntradayChart code snap liveP toggles />`
    (新檔 `CardIntradayChart.tsx`:`useContainerSize` 量恆存 wrapper(`flex-1 min-h-0`)→
    `cardSvgBox(size)`;`!usable` → 空佔位不畫;**`const accum = useMemo(() =>
    accumFromGroupSnapshot(code, snap, liveP), [code, snap, liveP])`(review R4,禁止就地建)**
    → `<IntradayChartCore variant="card" width=w mainHeight=mainH subHeight=subH accum toggles />`)。
  - 卡片內 svg hover 事件 → 點擊仍冒泡到 role=button 容器(onPick),hover 不觸 click。
    **注意** 卡片內不得有 button(toggle 鈕不在卡內)。
  - >16 分支卡片 `h-56`;≤16 維持 `min-h-0`(列軌指派)。
  - 既有測試:`GroupGridView.test.tsx` describe「GroupGridView 現價延伸接線(review B1)」
    selector `mini-price` → 改以 `polyline` points 數量計(不動單檔 DOM;契約「liveP 有值 →
    多一點」不變;jsdom 無 RO → 測試需 mock `useContainerSize` 回固定尺寸或 stub RO,寫法由
    implementer 定);`GroupGridView.memo.test.tsx` mock 目標換成
    `@/components/stock/CardIntradayChart`(計次語意不變)。
  - 新測試(先紅):`active` 選中態 aria-pressed;toggle 列四鈕存在 + 按下 → 各卡同步(SC-2);
    localStorage 預載 toggle 生效。
- `frontend/src/components/stock/StockPage.tsx:218-222`:`onPick={onSelect}`(去 selectView);
  `active={code}` 傳入。既有測試「點卡片 → onSelect 該股 + 自動切回單檔檢視」(:691-701,review R8 更正)**該紅** → 改寫為「點卡片 → onSelect(2317) + 檢視仍
  群組(`選擇群組` 仍在、`stock-lower-row` 仍 null)」(先改測試紅 → 再改實作綠)。
- `frontend/src/App.test.tsx`:新增全鏈「stock tab 群組檢視點 group-card-2317 → fetch
  `/api/stock/state/2317` + `copycat-stock-main-code`=2317 + `選擇群組` 仍在」(套 R3 SC-5 樣板)。
- 刪 `MiniIntradayChart.tsx` + `MiniIntradayChart.test.tsx`(extendMinutes 測試已搬 A);
  grep 確認零殘留引用。

### 🟢 D. 選中態視覺 + toggle 列樣式(UI 打磨)
- 併入 C 的實作 commit 分開:選中框 class / toggle 列 layout(`frontend-design` +
  `bencium-controlled-ux-designer` 載入後定 class;不引入新色 token)。

### 測試清單總表
- 該紅(🔴 預告):`StockPage.test.tsx:691-701`「點卡片 → onSelect 該股 + 自動切回單檔檢視」;`[amendment 2026-08-17: round 2 R2-4]` `tests/live/test_stock_state.py:334 test_light_snapshot_is_exactly_minutes_and_meta`(改鎖六鍵集合 `{minutes,meta,vwap,high,low,vp}`)、`:351 test_light_snapshot_without_meta_is_none_not_missing`(空態 `vp=={}`、vwap/high/low None、meta None);`:340 test_light_and_full_snapshot_share_one_key_mapping` 擴到 vwap/high/low 與 `snapshot()` 逐鍵相同(不紅,擴)。
- 不該紅:其餘全部(含 `StockIntradayChart*.test.tsx`、`GroupGridView.test.tsx` gridShape/pill/三態、`useChartToggles.test.ts`)。
- selector/mock 目標調整(test-infra,行為契約不變):`GroupGridView.test.tsx` describe「現價延伸接線(review B1)」與「點卡片切主檔」(tagName→role)、`GroupGridView.memo.test.tsx:21`。
- 搬家(assertion 不變):`MiniIntradayChart.test.tsx` 的 extendMinutes 部分 → lib test;幾何補償部分隨元件刪除。
- 新增:variant test、accumFromGroupSnapshot、cardSvgBox、GroupSnapshot 解析、GroupGridView active/toggle/edge 9、hover 不重算幾何(SC-6d)、App 全鏈、後端 light_snapshot 四鍵 + vp 增量 + parity + snap_down_milli + group-state 端點契約 + daily_bars semaphore。

## 7. 執行約束(沿前輪)
- `GroupCard` memo / `pickRef` 不打破(PR #27 review A6-1);矩陣 class 靜態字面值(PR #50)。
- `useContainerSize` 呼叫端契約兩條(恆存 wrapper / 高度由外層指派)。
- 前端 `frontend-conventions` / `frontend-testing` skill 先讀;後端 `backend-conventions`。
- 三類 commit 順序 🔵 A → 🔴 C → 🟢 B → 🟢 D(/mod 🔵→🔴→🟢;C 在 B 前落地時
  `accumFromGroupSnapshot` 走「缺鍵降級」路徑 = 舊後端相容路徑,本身就是要測的分支);
  [red]/[green] 配對。

## 8. Review changelog

- `[amendment 2026-08-17: code review round 1 A-2 / A-p2-6]` 實作階段另有三處既有 assertion 隨本輪必改而未在上表預告,補記:(1) `GroupGridView.test.tsx` describe「高度均分 class」— mini 圖 220×76 非等比縮放模型消滅(卡片改 1:1),`non-scaling-stroke` 與 `mini-ref` 契約自然失效,改鎖 viewBox 寬 = 量到寬 + wrapper class(test-infra);(2) `tests/server/test_stock_engine.py:1214`(group_snapshot 鍵集合)與 `:1370`(`_EMPTY_LIGHT` 全等)、`tests/server/test_stock_routes.py:495/563/597`(group-state 鍵集合)— 與 test_stock_state 兩條同性質的 exact-set 鎖,依同法擴鍵。
- round 2 限縮輪(`change-spec-review-round-2.json`):P1×4 / P2×2 全 accepted(R2-1 部分:不做幾何降級,改三張截圖驗收);無 P0 → 進實作。
- round 1(`change-spec-review-round-1.json`):P0×1 / P1×6 / P2×7,全部 accepted;修復段落 = AD-1/2/3/4/5、SC-3/5/6/7、edge 9/10、§6 A/B/C、測試清單總表(均標 `[amendment 2026-08-16]` 或本節指出)。

## 9. self_review_head

`self_review_head: dc70b1d9`(code review round 1 + fix 波收斂後 HEAD;fix 波 commit 由 main agent 逐條快篩:tag / diff 目視 / gate exit code)。
