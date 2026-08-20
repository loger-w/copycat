# current-state:台股綜合窄容器可讀性三合一(/mod)

來源:`docs/superpowers/specs/2026-08-21-b1-overview-narrow-pane-handoff.md`(實測數字為 2026-08-20 MCP 機械量測)。
分支 `mod/overview-narrow-pane-legibility`,自 master `8434bdf1`(B3 #76 之後)開。

## 1. 現況(code 事實)

### 1a. K 線態(子項 1)

- `frontend/src/components/stock/CandleChart.tsx`
  - `DIMS = { width: 1400, height: 578 }` 模組常數;`dimW = DIMS.width` **無 prop 可改**,`dimH = height ?? 578`。
  - svg `viewBox="0 0 ${dimW} ${dimH}"` + `className="w-full"` → 整份等比縮放到容器寬。
  - 字級字面值 `fontSize="0.625rem"` **7 處**:y 刻度、「無量資料」、視窗高低標(2 via map)、hline 標籤、X 軸時間標、hover 價位標、hover 時間標。
  - viewBox 單位的排版常數:`PRICE_TAG {56,16}`、`TIME_TAG {48,14}`、`MARK_LABEL_TOP 11`、`MARK_LABEL_PAD_X 20`、`lib/candle.ts::X_LABEL_H 14`、`clampLabelX(…, cx±15)`。這些**不是字級**,字級補償(候選 a)補不到 —— 與 2026-08-17 分時態棄補償改 1:1 的理由相同(`pane-frame.ts::paneIntradayBox` 註解)。
  - hover / viewport 兩 hook 以 `dimW`/`dimH` 參數化(`toSvgPoint(e, rect, {width: dimW, height: dimH})`、拖曳 `scale = dimW / rect.width`)→ viewBox 寬改變數不需動 hook。
  - `buildCandleGeometry(bars, {width, height})` 已吃寬度參數;`slot = width / bars.length`。
- Caller(共 3,grep `<CandleChart`):
  | caller | 傳 height? | 容器寬(典型) | 本案影響 |
  |---|---|---|---|
  | `stock/StockChart.tsx:205` | 量測(viewBox 單位) | 個股頁主圖 ≥ 700px | **零差異(硬約束)** |
  | `futures/FuturesChart.tsx:270` | 量測 | 期貨 tab 主圖 | 零差異 |
  | `index/MarketChart.tsx:142` | `height`(MarketPane 反解,viewBox 單位) | 台股綜合 pane svg 282–420px | **改** |
- `frontend/src/components/index/MarketChart.tsx`:K 線態 `<CandleChart key bars initBars showBb onToggleBb showVolume height />`;`height` 文件明寫「viewBox 單位」「未給透傳 undefined 用 578」。
- `frontend/src/components/index/MarketPane.tsx`:`frame = PANE_FRAMES.candle`(chromeY 100 / insetX 34 / vbW 1400)→ `svgHeight = paneSvgHeight(size, frame)`(反解成 viewBox 單位)→ `<MarketChart height={svgHeight} intradayBox={…}>`。`unitScale` 只剩 `OverlayCard` 讀。
- `frontend/src/lib/pane-frame.ts`:`PANE_FRAMES` 兩格(overlay 640 / candle 1400)、`paneSvgHeight`、`paneUnitScale`、`svgFontRem`、`paneIntradayBox`(1:1 樣板,chrome 26)。
- 實測:1536×864 兩欄態加權 pane CandleChart 實渲染 282×113px、scale 0.202、文字 3.0px。2560 寬(user 實機)pane svg ≈ 700px → scale 0.5 → 文字 ≈ 6px(root 125% 後),也偏小但目前視為可接受(對照組:不得退化)。

### 1b. 漲跌停表(子項 2)

- `frontend/src/components/index/LimitListSection.tsx`:9 欄 `<table className="w-full border-collapse text-sm">`,th/td 全 `px-2 py-1`;th `whitespace-nowrap`(防折行撐高表頭)、名稱/連板/徽章 `whitespace-nowrap`(防列高撐開)。捲動容器 `limit-list-scroll` = `min-h-0 flex-1 overflow-auto`。
- 容器結構(`IndexPage.tsx:113–203`):root `@container` → 右欄框 `flex flex-col rounded-md border … @[1050px]:min-h-0`(**非** `@container`,其 `@[1050px]` 量 root 寬,正確)→ `LimitListSection` root `div[data-testid=limit-list]`。**右欄內任何 `@[…]` 變體目前量到的是頁 root 寬**,要依右欄寬降級必須在右欄框或 `limit-list` 上自掛 `@container`。
- 實測:1536×864 scroller clientWidth 431px、表 scrollWidth 612px → 恆捲軸,金額(億)/量比/狀態尾段藏在捲軸後。1920 右欄 ≈ 740px、2560 ≈ 1000px 無此問題。
- 測試 `LimitListSection.test.tsx` 鎖:表頭九欄文字與順序、九欄各自 sticky + inset shadow、徽章/名稱/連板 nowrap、各欄 testid 內容。

### 1c. 週期列(子項 3)

- `MarketPane.tsx` 週期列:`<div className="flex flex-wrap items-center gap-1">` 內 `MARKET_MODES.map(Btn)` + 條件「重疊」鈕。`MARKET_MODES`(`lib/timeframe.ts`)**17 個**:分時 / 1–10分 / 30 / 60 / 90分 / 日K / 週K / 月K。
- `Btn`:`rounded border px-2 py-0.5 text-xs`,單鈕高 22px。
- pane root `section.flex min-h-0 min-w-0 flex-col gap-3`,**非** `@container`;最近容器 = 左欄(`IndexPage.tsx:141` 的 `@container`,兩欄態 630–930px)。
- 實測:~350px pane 週期列折 3 行、總高 74px,兩 pane 皆命中,吃掉 ~50px 圖高。
- `MarketPane.size.test.tsx` 鎖 figure `min-h-48` 地板(算式 192 − chrome 62 …,註解提到「週期列折行上限」是 IndexPage `min-h-80` 地板算式的一部分,非測試字面)。

## 2. 現況 vs 目標

| 面向 | 現況 | 目標 |
|---|---|---|
| CandleChart viewBox 寬 | 模組常數 1400,所有 caller 同 | 新 optional prop `width`(預設 1400);**只有 MarketChart 傳**量測 px 寬 → 1:1(同分時態 `paneIntradayBox` 精神) |
| MarketChart `height` 語意 | viewBox 單位(反解 ×1400/svgW) | K 線態改收 px 1:1 box(寬高皆 px),與 `intradayBox` 同型;不再反解 |
| pane-frame | `PANE_FRAMES.candle.vbW = 1400` 參與反解 | 新 `paneCandleBox(size)`(chrome 100 / inset 34,1:1);`PANE_FRAMES.candle` 是否保留見 change-spec |
| K 線字級(窄 pane) | 3.0px @ 282px | = 字面 0.625rem × root(≈ 10px @1536;≈ 12.5px @2560) |
| 漲跌停表 @ 431px | scrollWidth 612 > clientWidth 431 | 窄右欄下 `scrollWidth ≤ clientWidth`(欄數降級 + padding 收窄);寬右欄九欄不變 |
| 週期列 @ ~350px | 3 行 74px | ≤ 2 行;寬 pane 外觀不變 |
| 個股頁 / 期貨 tab CandleChart | — | **viewBox / 字級 / 幾何零變**(回歸鎖) |

## 3. Backward compat / migration

- 純前端、無 API、無 localStorage schema 變動 → **無 migration**。
- `CandleChart` 新 prop optional + 預設 = 現值 → 其他 caller 零差異。
- `MarketChart.height`(viewBox 單位)→ 改型為 px box:**單一 caller(MarketPane)**,同 PR 內一起改;`MarketChart.test.tsx:498/503` 的 `"0 0 1400 300"` / `"0 0 1400 578"` 斷言、`MarketPane.size.test.tsx:146–148, 223–236` 的 candle 反解斷言為**預告該紅**的既有測試(🔴)。

## 4. 相關債(handoff「不強制入 scope」)

- next-time 91:`EDGE_LABEL_H` 未隨 unitScale 縮放 —— 僅影響 `rightEdgeLabels`(個股分時共用契約),本案 K 線態改 1:1 後與此無關;**不入 scope**。
- MarketPane K 線態 y-tick duplicate key(全 0)—— 來自 `ChartStatic` `key={`yt-${t.priceMilli}`}` 在資料全 0 時重複;順路可收,列 out of scope 候選由 spec 拍板。
- next-time:`INTRADAY_CHROME_Y` export 無外部讀者,測試硬寫 26/272 —— 本案若新增 `CANDLE_CHROME_Y` 類常數,新測試一律 import 不硬寫。
