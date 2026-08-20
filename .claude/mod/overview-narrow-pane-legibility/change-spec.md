# change-spec:台股綜合窄容器可讀性三合一

分流判定:**已成形方案**(handoff 指名落點檔案 + 修法候選 + 驗證手法;命中 core-flow §2 條件 1+2)→ grilling 姿態,
逐題採建議解標 `[auto-default]`;規格來源為 user 撰寫的 handoff(auto.md 預核准替代條件)。無方向性抉擇(候選互換不改 SC 集合 / out of scope / 對外契約)。
規模:**M**(4 個 src 檔 + 測試;無 API / 無 migration;CandleChart 為共用 util 風險面 → review 照 M 1 輪,實作 dispatch)。

## 0. 決策(grilling 逐題)

- **D1 子項 1 修法**:(a) `unitScale` 字級補償 vs (b) CandleChart 開 `width` prop、MarketPane 傳量測寬 → 1:1。
  `[auto-default: (b) 1:1 | reason: 補償只補得了 7 處 fontSize,補不了 PRICE_TAG/TIME_TAG/X_LABEL_H/MARK_LABEL_* 這些 viewBox 單位排版常數(scale 0.2 下 hover 標籤框 11×3px、X 軸標籤帶 2.8px 高,字放大後必撞);2026-08-17 分時態已因同一理由棄補償改 1:1(paneIntradayBox),K 線態跟上 = 同一份像素語彙。蠟燭寬在 1:1 下與現況螢幕 px 相同(slot×0.7:282/120×0.7 = 1.64px vs 1400/120×0.7×0.202 = 1.65px),只有文字 / 標籤 / 線寬回原生。]`
- **D2 子項 2 修法**:窄右欄下 (a) 隱藏 金額(億)/量比 兩欄 + (b) `px-2 → px-1`,兩者**併用**。
  `[auto-default: a+b 併用、門檻 @max-[41rem] 掛在 limit-list root(自掛 @container) | reason: 以實測 612 為唯一基準:只藏兩欄(content+padding ≈ 140)→ ~472 > 431 仍捲;只縮 padding(9×8=72)→ 540 仍捲;併用(藏兩欄後剩 7 cell × 8 = 56)→ ~416 < 431,邊際僅 ~10–15px。門檻用 rem 不用 px:表格內容是 rem 字級,「塞不塞得下」隨 root 縮放(與 frontend-conventions 的 px 門檻案例相反——那裡是面板寬固定 px);41rem = 656@100% / 738@112.5%(≥1920)/ 820@125%(≥2560)。寬度模型(IndexPage 註解 容器=視窗−349,rem 部件隨 root 放大;右欄=0.4×(容器−gap)):1536 → 470(實測 475 ✓)→ 降級;1920 → 605 < 738 → 降級(本就塞不下:605−32 < 612×1.125);2560 → 844 > 820 → 九欄。藏哪兩欄沿 handoff / next-time 原案(金額 / 量比 皆仍可由篩選列輸入門檻)。]`
  [amendment 2026-08-21: review round 1 R1/R2:門檻 px→rem、重算以 612 為基準、補 FAIL 階梯]
  **D2 FAIL 階梯**(SC-2 真資料量測 scrollWidth > clientWidth 時,依序 amendment):(1) 窄態再藏「市場」欄(上市/上櫃由篩選列 checkbox 仍可控,約再省 36px);(2) 名稱欄 `max-w-[6rem] truncate`(長股名 edge 5)。
- **D3 子項 3 修法**:(a) 週期鈕收窄 vs (b) 折疊次要檔位進「更多」。
  `[auto-default: (a) 收窄:pane 自掛 @container,@max-[26.5rem] 下 Btn px-2→px-1、列 gap-1→gap-0.5 | reason: 估算 17 鈕 text-xs 在 px-1/gap-0.5 下總寬 ≈ 561px(含重疊鈕 593)→ 346px pane 1.6–1.7 行 = 2 行;折疊要新增 state + 第二層 UI、且「每個週期一鍵可達」是既有行為。門檻用 rem(鈕文字 / padding 全 rem,隨 root 放大):26.5rem = 424@100% / 477@112.5% / 530@125%。pane 寬模型((0.6×(容器−gap)−12)/2):1536 → 346 → compact;1920 → 448 < 477 → compact(估 561×1.125=631 / 448 = 1.4 → 2 行;不 compact 會 820/448=1.83 → 3 行風險);2560 → 626 > 530 不 compact(估 729×1.25=911 / 626 = 1.46 → 2 行)。收窄只在窄 pane 生效,寬 pane computed padding 不變。若真環境 2 行不成立(SC-3 FAIL)→ 回本節 amendment 改 (b)。]`
  [amendment 2026-08-21: review round 1 R9:門檻 px→rem、補 1920/2560 估算]
- **D4 pane 自掛 `@container` 的副作用**:pane 內 CandleChart / IntradayChartCore / ChartReadout 無任何 `@[…]` 變體(grep 已查),最近容器改變不影響;`@[1050px]:min-h-0` 教訓在 pane 上已是無條件 `min-h-0`,不受影響。[amendment 2026-08-21: review round 1 R10] `@container` = `container-type: inline-size`(含 layout/style containment、成為 stacking context 與 absolute/fixed 子孫的 containing block):已 grep 確認 pane 子樹(MarketPane/MarketChart/CandleChart/StockIntradayChart/ChartReadout)與 limit-list 子樹**無 absolute / fixed 定位子孫**;唯一 `sticky th` 的捲動祖先是 `limit-list-scroll`(在新容器之內,不受影響);pane 所在 grid 軌 `minmax(0,1fr)`、limit-list 為 flex item 寬由父指派 → inline-size containment 不改軌算。
- **D5 `PANE_FRAMES.candle` 去留**:`[auto-default: 刪除 candle 格,PANE_FRAMES 只剩 overlay;新增 paneCandleBox(size)(chrome 100 / inset 34,1:1,地板 96 / −2 同 paneIntradayBox) | reason: 與 2026-08-17 分時態退出該表同理 —— 留一格沒人讀的反解參數,下一個人會以為兩條路都在。]`
- **D6 MarketChart `height` prop**:`[auto-default: 改名為 `candleBox?: {width; height}`(px 1:1),與 `intradayBox` 同型;不再有 viewBox 單位 prop | reason: 單一 caller(MarketPane)同 PR 改;同名異義(height 從 viewBox 變 px)比改名更危險。]`
- **D7 順路債**:K 線態 y-tick duplicate key(資料全 0)→ **out of scope**(與可讀性無關、另屬 ChartStatic 共用碼);`EDGE_LABEL_H` → out of scope(1:1 後 K 線態不再牽涉)。

## 1. 成功條件(SC)

量測環境:`npm run dev` + 同源 iframe host `frontend/public/__viewport_host.html?w=1536&h=864`(臨時檔,收尾刪);host 內以 script 讀 DOM 幾何渲染成 `<pre>`,截圖 / `get_page_text` 讀數。對照組 2560×1440。

- **SC-1(K 線態可讀)**:1536×864 兩欄態,左 pane 切「日K」,CandleChart svg `viewBox` 寬 = svg `clientWidth`(誤差 ≤ 1),y 刻度 `<text>` 的 `getComputedStyle(..).fontSize === '10px'`(root 100%;1920 為 11.25px)且**相鄰兩條 y 刻度 text 的 rect 不重疊**;另回報 svg clientHeight 前後(edge 9)。[amendment 2026-08-21: review round 1 R5]畫面可指認:左 pane K 線圖左緣價位刻度(如 `24000`)、底部日期(`08/20`)肉眼可讀,與右 pane 分時圖字級同級。
  驗證:iframe host 量測 + 截圖 `evidence/SC-1-*.png`;單元測試 `MarketPane.size.test`「K 線態 → 1:1 box」。
- **SC-2(漲跌停表不捲)**:1536×864 下 `[data-testid=limit-list-scroll]` 的 `scrollWidth ≤ clientWidth`(用真 FinMind 資料或 verify fake 皆可,以 prod 後端 8721 的實資料為準);金額(億)/ 量比 的 th `getComputedStyle(th).display === 'none'`、代號 th `!== 'none'`、任一 td `paddingLeft === '4px'`;狀態徽章完整可見。**1920×1080** 同上(右欄 ≈ 605 → 七欄、不捲)。2560 下九欄 th display 皆非 none、`paddingLeft === '10px'`(px-2 @125%)。[amendment 2026-08-21: review round 1 R1/R8]
  驗證:iframe host 量測兩個寬度 + 截圖 `evidence/SC-2-*.png`;單元測試鎖 class(`@max-[41rem]:hidden` 於兩欄 th/td、`@container` 於 root)—— class 鎖只防漏寫,CSS 層由 host computed style 斷言把關(`@max-[…]:` 為本專案首用)。
- **SC-3(週期列 ≤ 2 行)**:1536×864 下兩 pane 的週期列容器 `getBoundingClientRect().height ≤ 48px`(2 行 × 22 + gap 2 = 46;3 行 ≥ 70)。畫面可指認:「分時 … 月K」17 顆鈕佔兩行,圖高較前多 ≥ 20px。**1920×1080** 兩 pane 同樣 ≤ 48px(pane ≈ 448 → compact);2560 下 Btn `getComputedStyle(btn_日K).paddingLeft === '10px'`(px-2 @125%,不 compact)且週期列高 ≤ 2 行(≤ 60px @125%)。1536 下 `paddingLeft === '4px'`。[amendment 2026-08-21: review round 1 R7/R8/R9]
  驗證:iframe host 量測 + 截圖 `evidence/SC-3-*.png`;單元測試鎖 pane root `@container` + Btn `@max-[26.5rem]:px-1`。
- **SC-4(回歸鎖:個股頁 / 期貨頁 CandleChart 零差異)**:`CandleChart` 未傳 `width` 時 svg viewBox 為 `0 0 1400 <h>`、7 處 fontSize 仍 `0.625rem`、`PRICE_TAG/TIME_TAG` 不變;StockChart / FuturesChart 不動。
  驗證:`CandleChart.test.tsx` 新增「預設 width 1400」lock;既有 StockChart / FuturesChart 測試全綠;截圖個股頁 K 線一張 `evidence/SC-4-stock-candle.png` 對照(viewBox 字串由 host 讀出);另補台股綜合 pane「5分」態截圖 `evidence/SC-4-pane-m5.png`(240 根,edge 10 未成實心)。[amendment 2026-08-21: review round 1 R4]
- **SC-5(自動化 gate)**:`npm test` / `npx tsc -b` / `npx eslint src` / `npx react-doctor@latest --scope changed --no-telemetry` 全 PASS,落 `verification.md`。

## 2. 不能破壞的既有行為白名單

- W-1 個股頁(StockChart)與期貨 tab(FuturesChart)的 CandleChart:viewBox `0 0 1400 H`、字級、hover 標籤、拖曳 / 滾輪、hlines、volumeDelta 全部逐值不變。
- W-2 MarketPane 分時態 1:1 box(`paneIntradayBox`)、重疊態 `PANE_FRAMES.overlay` 反解 + `unitScale` 字級補償:不變。
- W-3 MarketPane 量不到(jsdom / 無 ResizeObserver)→ K 線態 CandleChart 走自身預設 1400×578(W-10 fallback 精神)。
- W-4 K 線態 chrome 契約:`MarketChart` meta 列 `h-4 truncate`、CandleChart figure chrome 80 + meta 20 = 100 的高度算式(改寫進 `paneCandleBox`,數值不變)。
- W-5 漲跌停表:九欄順序與文案(**右欄 ≥ 41rem** 時;1920 右欄 ≈ 605px 亦降級為七欄,是預期 [amendment 2026-08-21: review round 1 R1])、th 各自 sticky + inset shadow、名稱 / 連板 / 徽章 nowrap、篩選 / 排序 / 空態文案 / localStorage 還原全部不變;金額 / 量比**資料與篩選邏輯**不變,只是窄容器不顯示該兩欄。
- W-6 週期列:17 個 MARKET_MODES 全部保留、順序不變、disabled 規則(櫃買日/週/月)不變、重疊鈕條件不變;寬 pane(≥ 26.5rem)Btn **computed** `padding-inline` 仍 8px、列 gap 仍 4px(class 會多一個條件式 token,是預期)。[amendment 2026-08-21: review round 1 R7]
- W-7 pane root 無條件 `min-h-0`、figure `min-h-48` 地板、IndexPage 的 `@[1050px]` 兩欄斷點與 6:5 flex 變數:不變。
- W-8 CandleChart 蠟燭 / 量柱的螢幕像素寬度在台股綜合 pane 下、**根數 ≤ ~197(日 K 初始 120 根)時**等價(1.64 vs 1.65px);> 197 根時 `max(1, …)` 地板使柱寬 0.83 → 1px,為既知可接受差異(edge 10)。[amendment 2026-08-21: review round 1 R4]

## 3. Edge cases

1. pane 量測首幀 0×0 / jsdom → `paneCandleBox` usable=false → `candleBox` undefined → CandleChart 預設 1400×578(W-3)。
2. pane 極窄(`size.width ≤ 34` = insetX,svgW ≤ 0)→ usable=false 同上,不傳 0 寬(svg 不報錯純粹消失)。測試邊界值用 34 / 30。[amendment 2026-08-21: review round 1 R6:130 無出處]
3. 容器極矮 → 高地板 96(同 paneIntradayBox)。
4. 1:1 後 hover 價位 / 時間標籤框(56×16 / 48×14 px)在 282px 寬圖上約佔 20% 寬 —— 可接受(與分時態右緣標籤同級);`clampTagX` 仍夾在 viewBox 內。
5. 漲跌停表窄態遇 6 字以上股名(如「元大台灣50」):名稱 nowrap 可能再撐出捲軸 → SC-2 以真資料量測;若出現,amendment 加 `max-w` + truncate 於名稱欄(不在本輪預設 scope)。
6. 右欄寬恰在 650px 邊界抖動(視窗拖拉)→ 欄位顯隱切換無 state、純 CSS,無閃爍風險。
7. 週期列窄態含「重疊」鈕(18 顆)→ 估算 593px / 350 = 1.7 行仍 2 行;SC-3 量測以左 pane(加權,有重疊鈕)為準。
8. 切模式(分時 ↔ 日K)時 CandleChart 以 `key` 重掛,viewport 重置 —— 既有行為,不變。
9. [amendment 2026-08-21: review round 1 R5] 1:1 的必然代價:`X_LABEL_H 14` / `PAD_Y 6` 從 viewBox 單位變真 px(現況 282×113 下只值 2.8 / 1.2px)→ 價格繪圖區約 84px → 65px(−22%);`Y_TICKS = 5` 不隨高調整 → 刻度間距 ≈ 13px、字 10px 幾乎相接。與 SC-3 週期列省下的 ≥ 20px 圖高對沖後淨值由量測回報(SC-1 附 svg clientHeight 前後)。SC-1 因此加「相鄰 y 刻度不重疊」判定。
10. [amendment 2026-08-21: review round 1 R4] 根數 > ~197(分 K initBars 240、滾輪縮小)時 `lib/candle.ts` 的 `w = min(max(1, slot×0.7), slot)` 地板在 1:1 下以真 px 咬住:柱寬 0.83px → 1px、柱距 0.35 → 0.18px,既知可接受差異(見 W-8);SC-4 補 5分 態截圖確認未成一片實心。
11. [amendment 2026-08-21: code review A1] **單欄態**(IndexPage 容器 < 1050px,視窗 ≈ 1024–1399)兩門檻同樣生效:limit-list = 容器全寬、pane = (容器 − 12)/2。實測 1200×800:limit-list root 852px → 九欄不捲;pane 421px → compact、週期列 46px(2 行);K 線 1:1 353×96。視窗 < 1024 走 mobile 分支,本頁不掛載。
12. [amendment 2026-08-21: 真環境實測] **事實更正(code review B1)**:copycat 前端**無** root font-size media query(root 恆 16px,三檔實測),D2/D3 rationale 中「@112.5% / @125%」的換算不成立 —— rem 門檻今日等於 px(41rem = 656px / 26.5rem = 424px),保留 rem 的理由改為「內容為 rem 字級,門檻以 rem 表達使『塞不塞得下』對 root 縮放不變」。實測:1920 右欄 627 → 七欄(恰好 585 = 585 不捲)、pane 466 → **不** compact 但週期列 48px = 2 行;2560 右欄 883 → 九欄 padL 8px、pane 658 → 2 行。SC-1/2/3 中 11.25px / 10px padL 的期望值一律讀作 10px / 8px。
13. [amendment 2026-08-21: 真環境實測] **地板 96 在 1536×864 被吃到**:pane 圖區 wrapper 扣 chrome 100 後 < 96 → viewBox 高取地板 96,但 CandleChart 的 svg 是 flex item 被壓到 81px → 實際縮放 0.84(文字 computed 10px、渲染 ≈ 8.4px;改前為 0.20 / 3.0px)。y 刻度 bounding rect 相疊 1.1px(ascent/descent 盒),3× 放大截圖可見字形分離(`evidence/SC-1-1536-candle-crop3x.png`);figcaption 折兩行與 K 線區偏矮為**既有現象**(handoff 改前截圖同樣可見),根因是 K 線態雙層 figure chrome(100 vs 分時 26)在 864 高度下無空間,**不在本案 scope**,列 next-time 候選。1920×1080 / 2560×1440 / 1200×800 皆未吃地板(226 / 451 / 96=96)。

## 4. Out of scope

- 折疊式週期列(D3 (b))、y-tick duplicate key、`EDGE_LABEL_H` 縮放、名稱欄 truncate、StockChart / FuturesChart 任何字級調整、2560 下 K 線字級「再放大」的主觀偏好(1:1 後 = 原生 rem,不另調)。

## 5. Diff 級計畫(逐檔;🔴 行為 / 🟢 新功能 / 🔵 重構)

順序:**🟢 先、🔴 後**([amendment 2026-08-21: review round 1 R3]:🟢 是 CandleChart 純擴充 optional prop、預設 = 現況零差異,🔴 的 MarketChart / MarketPane 依賴該 prop,反序會產出不可編譯的中間 commit)。本案沒有純 🔵 項。

### `frontend/src/lib/pane-frame.ts` 🔴
- 刪 `PANE_FRAMES.candle`(型別縮成 `Record<"overlay", PaneFrame>`),文件註解改寫(candle 退出原因同 intraday)。
- 新增 `CANDLE_CHROME_Y = 100`、`CANDLE_INSET_X = 34`(export,測試 import 不硬寫)與 `paneCandleBox(size): IntradayBox`(型別可改名 `PaneBox` 共用;`width = round(size.width − 34)`、`height = max(96, floor(size.height − 100) − 2)`、任一邊 ≤ 0 或 svgW ≤ 0 → usable false)。
- 既有測試該紅:`MarketPane.size.test.tsx:146`「candle:vbW 是 CandleChart 的 1400」、`:154` candle 地板、`:161` candle undefined、`:223`「K 線態 → 用 candle frame 1400」→ 改寫成 `paneCandleBox` 語意(先改紅 → 再改實作綠)。
- 新測試:`paneCandleBox` 算式 / 地板 / usable false 三條。

### `frontend/src/components/stock/CandleChart.tsx` 🟢(新 prop,預設 = 現況)
- `Props` 加 `width?: number`(文件:viewBox 寬,px 1:1 時由 caller 傳量測寬;未傳 1400 = 既有所有 caller 零差異)。`const dimW = width ?? DIMS.width;`。
- `ChartStatic` 內 `DIMS.height * 0.85` fallback 保留(只在 volBars 空時用,非本案)。
- [amendment 2026-08-21: review round 1 R11] `hooks/useCandleViewport.ts:65–68` 註解「當前 dimW 是模組常數」改寫為「dimW 現為 prop(台股綜合 pane 1:1),deps 帶它不再只是形式」(純註解,同 🟢 commit)。
- 新測試:`CandleChart.test.tsx`「未傳 width → viewBox 0 0 1400 578(lock)」「傳 width=282 height=113 → viewBox 0 0 282 113,y 刻度 fontSize 仍 0.625rem」。

### `frontend/src/components/index/MarketChart.tsx` 🔴
- Props:刪 `height?: number`,加 `candleBox?: { width: number; height: number }`(px 1:1,K 線態限定;未給 → CandleChart 預設)。K 線態 `<CandleChart width={candleBox?.width} height={candleBox?.height} …>`。
- [amendment 2026-08-21: review round 1 R11] 註解 `MarketChart.tsx:151–153`(meta 列 h-4 契約)改指 `pane-frame.ts::CANDLE_CHROME_Y`;`MarketChart.test.tsx:483–485` 同段註解同步改(不算該紅)。
- 既有測試該紅:`MarketChart.test.tsx:498`(`height={300}` → `0 0 1400 300`)改為 `candleBox={{width: 430, height: 300}}` → `0 0 430 300`;`:503` 未傳 → `0 0 1400 578` 不變(W-3)。

### `frontend/src/components/index/MarketPane.tsx` 🔴 + 🔴(週期列)
- K 線態:`frame` 三態改為 `overlayPair !== null ? PANE_FRAMES.overlay : null`;`svgHeight` 只給 OverlayCard;新增 `candleBox = useMemo(paneCandleBox …)`(同 intradayBox 的 memo 形狀,deps `[paneCandle, size.width, size.height]`);`<MarketChart candleBox={candleBox} intradayBox={intradayBox}>`。
- 週期列:pane root `section` class 加 `@container`;週期列 div `gap-1` → `gap-1 @max-[26.5rem]:gap-0.5`;`Btn` 加 optional `compact?: boolean`(或直接在 Btn class 內寫 `@max-[26.5rem]:px-1` —— Btn 也用於標的列,標的列同縮無害;`[auto-default: 直接寫在 Btn class,不加 prop | reason: 標的列 3–6 顆鈕同縮只省空間不改行數,少一個 prop]`)。
- 既有測試該紅:`MarketPane.size.test.tsx:223–236`(K 線 viewBox 1400)。不該紅:`MarketPane.test.tsx`(行為)、`MarketPane.memo.test.tsx`。
- 新測試:`MarketPane.size.test`「K 線態 → 1:1 candleBox(viewBox `0 0 ${430−34} ${expected}`)」「量不到 → 1400×578」;`MarketPane.test`「pane root 含 @container;週期鈕 class 含 @max-[26.5rem]:px-1;週期列含 @max-[26.5rem]:gap-0.5」。

### `frontend/src/components/index/LimitListSection.tsx` 🔴
- root `div[data-testid=limit-list]` class 加 `@container`。
- `TH` 與 td 的 `px-2` → `px-2 @max-[41rem]:px-1`(抽常數 `CELL_X`)。
- 金額(億)/量比 的 th 與 td 加 `@max-[41rem]:hidden`(th 仍 sticky;`hidden` = display:none 在 table-cell 上合法)。
- 既有測試不該紅:「表頭九欄文字與順序」(jsdom 不套 CSS,九欄 DOM 仍在)、sticky / nowrap 各條。
- 新測試:「root 帶 @container;金額 / 量比 th+td 帶 @max-[41rem]:hidden;其餘七欄不帶;cell 帶 @max-[41rem]:px-1」。

### 測試檔異動總表
| 檔 | 該紅(🔴 預告) | 新增 |
|---|---|---|
| `MarketPane.size.test.tsx` | L146–161 candle 反解三條、L223–236 K 線 1400 | paneCandleBox ×3、1:1 candleBox、fallback |
| `MarketChart.test.tsx` | L498 | — |
| `CandleChart.test.tsx` | 無 | 預設 1400 lock、width prop |
| `MarketPane.test.tsx` | 無 | @container / compact class |
| `LimitListSection.test.tsx` | 無 | @container / hidden / px-1 class |

## 6. 執行約束(承 handoff)
- 不動 prod server(純前端);驗證走 `npm run dev`(port 5173)proxy 到 prod 8721 取真資料。
- 收尾刪 `frontend/public/__viewport_host.html`;vite dev 以 port → PID 收。
- 先讀 `frontend-conventions`(container query / 字級)與 `frontend-testing`(已讀)。
- M 級 → 實作 dispatch(顯式 `opus`)。

## 7. self_review_head

- code review round 1:`code-review-round-1.json`(P0 0 / P1 2 / P2 6;accepted 7、rejected_with_reason 1)。fix 波 commits `7288f742`(lock,mutation-verified)+ `dd5710c7`(註解)。
- `self_review_head = dd5710c7`(收尾增量 review 的基準;其後只有 artifact commit)。
