# change-spec — 台股綜合左欄:指數分時圖換 IntradayChartCore(mode="index")+ 騰落線吃 flex

分支 `mod/index-intraday-core`;現況表見同目錄 `current-state.md`(行號基準 master `c958b141`)。
來源:`docs/superpowers/specs/2026-08-17-user-feedback-batch3-rounds.md` §2 R4;D11(a)/ D12(a)
已由 user 拍板(2026-08-17)。**分流判定**:已成形方案(prompt 指名元件、adapter 落點、佈局
改法)→ grilling 姿態、無方向性抉擇 → 逐題 `[auto-default]` 推進不停等。

規模:**L**(≥5 檔、跨 stock / index 兩個元件族)→ spec review 1 輪 + P0 限縮加輪。

## 0. 目標(一句話)

加權 / 櫃買分時圖改吃個股同一份 `IntradayChartCore`(mode="index":hover 十字 / readout /
昨收線 / 均價線 / CDP+MA 含域外掛牌 / 高低點 / 現價圈 / 紅綠填色),副圖與 VP 一律關;左欄
雙圖與騰落線改為 3:2 flex 分配,騰落線不再固定 96px。

## 1. 成功條件(SC;UI 條皆「畫面可指認」)

| # | 條件 | 驗證方式 |
|---|---|---|
| SC-1 | 加權分時圖 hover:游標移入圖區出現**虛線十字**(垂直線落在該分鐘、水平線跟滑鼠)、左緣價位標籤(不 tick-snap;口徑 `fmtIndexPts`:加權 8 字收整數點、櫃買保留小數 — `[amendment 2026-08-17: review C-2 + real-env 截圖裁字]`)、底部時間+點位標籤;左上 readout 三欄 `HH:MM / 點位 / 漲跌%`(無 hover 顯最新分鐘;點位與 % 依相對昨收紅綠) | vitest `MarketChart.test.tsx` 新案(`fireEvent.mouseMove` → `crosshair-v` / `crosshair-h` / `price-tag-text` / readout 文字);截圖 `evidence/SC-1-twse-hover.png` |
| SC-2 | 均價線 / 昨收線 / CDP+MA 與個股頁同款(MA 價位標籤 `fmt` 不 tick-snap:fixture ma5=23_018_000 印 `23018`,不是 `23020`):均價線 `stroke-ink` 1.2 + 末點就地標籤(值 = 分鐘收盤算術平均);昨收 `stroke-line` 虛線 `2 3`;CDP 域內線 + 右緣帶 `價位*`(`fmtIndexPts`,不 tick-snap);MA 名稱右緣帶 + 價位標籤;**域外 CDP/MA 在繪圖區右緣掛牌 `AH 24100↑`**(現版行為保留) | vitest(域內 / 域外 fixture 沿 `MarketChart.test.tsx` 的 `OVERLAY_IN/OUT`);截圖 `evidence/SC-2-twse-overlay.png` 與個股頁同款對照 |
| SC-3 | 當日高 / 低空心環 + 價位文字(標在該分鐘;**高 === 低(單一分鐘 / 一字)只畫日高**,core 既有規則)、現價實心圈(高於昨收紅 / 低綠 / 無昨收灰;**`series.p` null 不畫**) | vitest testids `day-high` / `day-low` / `last-dot`;截圖同 SC-1 |
| SC-4 | 櫃買圖同款,但 CDP / MA 鈕反灰 + title「櫃買無日 K 資料源」;加權 503 / 三欄全 null → 反灰 title「無日線資料」;閘關(cdp/ma 都關)後鈕恢復可按(G-2 保留);均價鈕 title「分鐘收盤均價(指數無成交量)」 | vitest(移植 `MarketChart.test.tsx:176-286` 四案);截圖 `evidence/SC-4-otc.png` |
| SC-5 | **個股頁 / 群組圖牆分時圖零變化**(mode 預設 stock) | `StockIntradayChart*.test` / `GroupGridView*.test` / `stock-intraday-svg.test` 不改一字全綠;個股頁截圖前後 `evidence/SC-5-stock-before.png` / `-after.png` 目視同款 |
| SC-6 | 佈局(兩欄態):1920×1080 與 1536×864 整頁無捲軸(主 grid `scrollHeight === clientHeight`);**騰落線 wrapper 高 ≥ 0.6 × 任一 MarketPane figure 高**;兩 pane 分時 svg 高 ≥ 96px。**單欄態(1366×768,容器 1017 < 1050)**:騰落線 wrapper 高 = 96px、`getComputedStyle` 的 `--idx-*` 變數未套用(flex 走預設值)= 改動前行為 | claude-in-chrome JS 量 `getBoundingClientRect` / `getComputedStyle` 落 `evidence/SC-6-layout-{1080p,864p,768p}.json` + 截圖 |
| SC-7 | 分時 svg 1:1:viewBox 寬 = 量到寬 px、高 = `max(96, floor(量到高 − 26) − 2)`;量不到(jsdom)→ 走 core 預設(800×260) | vitest `MarketPane.size.test.tsx` 改寫(RO mock 沿既有 `:168-188`) |
| SC-8 | 三類 commit 分明:🟢 core mode 注入([red]→[green])→ 🔴 換元件 + adapter([red]→[green])→ 🔴 佈局([red]→[green]);既有測試紅只在 🔴 `[red]` commit | `git log` 對照 §6 |

**驗證窗口**:SC-1~4 的真資料 hover 需 TC4 有指數 push(盤中或 restore 過的當日序列);
窗口外用 `IndexPage` 假資料側車(fake index series)或 vitest 截圖 → 標 `browser_unavailable`
/ 假資料註記,真 TC4 層記「待 prod 重啟 + 盤中過目」。

## 2. 不能破壞的既有行為白名單

- W-1 個股頁 `StockIntradayChart` 與群組卡 `CardIntradayChart` 渲染逐字不變(mode 預設 `"stock"`;
  新 props 全 optional 且預設值 = 現行為;`useStockOverlay` 仍無條件呼叫)。
- W-2 `OverlayCard`(加權 vs 櫃買相對昨收疊線)與 K 線態(`CandleChart` + meta 列)不動;
  `PANE_FRAMES.overlay / .candle` 數值不動。
- W-3 `/api/index/*` 契約不動;`useIndexOverlay` 查詢與 gate(`intraday && TWSE && (cdp‖ma)`)不動;
  G-2「閘關不鎖鈕」語意保留。
- W-4 家數帶 / 漲跌停列表 / 右欄不動;1050px 兩欄斷點與單欄退化不動;可縮鏈(`min-h-0` 節點:
  root / 左欄 `@[1050px]:min-h-0` / pane / 量測 wrapper)不動。
- W-5 `ChartToggles` 鍵集合與 localStorage 不動;兩 pane 共用同一份 toggles 不動。
- W-6 MarketPane 標的列 / 週期列 / 重疊鈕 / storage 遷移 / coerceMode 全部不動。
- W-7 騰落線內容(net 計算 / 紅綠雙色 / 末值標)不動,只改 wrapper 高度契約。
- W-8 core 不沾 capital / TQ(index 態 `fills` 恆 `EMPTY_FILLS`,不掛新 hook)。

## 3. 設計(diff 級)

### 3.1 🟢 `components/stock/StockIntradayChart.tsx` — core 加 mode / overlay 注入(個股零變化)

(`[amendment 2026-08-17: review R5]` 原標 🔵,依三類定義「新增能力」= 🟢;個股零變化由 SC-5 白名單驗證,不由分類宣稱。)

新增 `CoreProps`:
```ts
/** "index" = 指數分時(台股綜合):副圖 / VP / 成交點 / 說明列一律關,readout 三欄,
 *  疊線由 caller 注入(不打 /api/stock/overlay),右緣文字走 `fmt` 不 tick-snap。預設 "stock"。 */
mode?: "stock" | "index";
/** index 態注入的疊線;stock 態忽略(仍走內建 useStockOverlay)。 */
overlay?: StockOverlay | null;
/** 疊線查詢失敗且閘當前有效(語意同 MarketChart.overlayError) */
overlayError?: boolean;
/** 該標的是否有疊線資料源(櫃買 = false → CDP/MA 反灰、title 用 overlayOffTitle) */
overlaySupported?: boolean;      // 預設 true
overlayOffTitle?: string;        // 預設 "無日線資料"
/** svg aria-label;預設 "分時走勢圖"(index 態 caller 傳 `${name}分時走勢`) */
ariaLabel?: string;
```
行為(全部以 `const index = mode === "index"` 閘;stock 態逐行不變):
- overlay:`useStockOverlay(index ? null : accum.code || null, !index && 既有條件)`(`|| null` 是**現碼既有**(:709),保留 = W-1;`[amendment 2026-08-17: review R8 REFUTED — 現碼本就 `|| null`,spec 原句抄錯]`);
  `overlay = index ? (overlayProp ?? null) : (overlayQ.data ?? null)`;
  `cdpAvailable = index ? overlaySupported && (overlayError ? false : overlay ? overlay.cdp !== null : true) : 既有`,MA 同理。
- toggleDefs:index → 只 `[vwap(title「分鐘收盤均價(指數無成交量)」), cdp, ma]`;disabled title = index ? overlayOffTitle : 既有。
- 副圖 `<svg aria-label="成交量">` index 不 render;`subEnergy` useMemo index 回常數空結果;`vpEnabled = toggles.vp && !stkfut && !index`;`fillMarks` 既有(fills 恆空);`side = card || index ? null : sideSummary(...)` → figcaption 不出。
- readout:`fields = (card || index ? allFields.slice(0, index ? 3 : 4) : allFields).concat(fillField...)`。
- hover 價標:`hoverPrice = index ? g.priceAtY(y) : snapDown(g.priceAtY(y))`。
- 右緣 / MA 價位文字:ChartStatic 新 prop `priceText: (milli) => string`(stock `fmtTickPrice`、index `fmt`;module 函式 identity 穩定,memo 安全);**兩個落點**都改吃它:(a) `levelText(level, price, priceText)`(CDP `價位*`,:90-95);(b) `maLabels` 的 `{fmtTickPrice(l.priceMilli)}`(:455)→ `{priceText(l.priceMilli)}`。`[amendment 2026-08-17: review R1]`
- **域外掛牌**(index 限定):`pegs = index && overlay ? outOfDomainLevels(overlay, g, {cdp: toggles.cdp && cdpAvailable, ma: toggles.ma && maAvailable}) : EMPTY_PEGS`;**useMemo 位置必須在 `g` 之後、`priceLine.length === 0` 早退之前**(hook 不可條件化,同 `fillMarks` 註解;本 repo 無 react-hooks lint),deps `[index, overlay, g, toggles.cdp, toggles.ma, cdpAvailable, maAvailable]`(`[amendment 2026-08-17: review R9]`)。ChartStatic 新 prop `pegs`(預設模組常數空陣列),render 於繪圖區右緣內側(`x = w − R_AXIS_W − 2`, `textAnchor="end"`,`stroke-surface` halo,`LEVEL_FILL[level]`,`0.5625rem`,`dy="0.35em"` 置中):up 由 `MARK_LABEL_TOP` 往下 `EDGE_LABEL_H` 疊、down 由 `plotBottom − 5` 往上疊(定位純函式抽 `lib/stock-intraday-svg.ts::pegLabels(pegs, bounds)`,回 `{level, priceMilli, dir, y}[]`);文字 `${level.toUpperCase()} ${fmt(price)}↑/↓`(= 現版 `labelText` peg 字面);`data-testid="overlay-peg-{level}"`。**pegs 的 y 併入 `edgePriceLabels` 的 obstacles**(pegs 先定位、MA 價位標讓位;掛牌是 KR-1 的唯一訊號不可被推)—— 與極值標籤同一條走廊、同一組 bounds(`[amendment 2026-08-17: review R2]`)。stock 態 pegs 恆空 → 零渲染、obstacles 不變。
- 空態:`priceLine.length === 0` → 文字 index ? 「等待指數資料…」: 「尚無成交」;**index 態容器去框**(`flex min-h-0 flex-1 items-center justify-center`,無 `rounded-md border border-line bg-surface` — MarketPane 的 figure 已是框,否則盤前每個 pane 框中框;`[amendment 2026-08-17: review R11]`)。
- wrapper:index → `<div className="flex min-h-0 flex-1 flex-col select-none">`(同 card;MarketPane 的 figure 已是外框)。
- svg `aria-label={ariaLabel ?? "分時走勢圖"}`。
- import 新增:`outOfDomainLevels, type OutOfDomainLevel` from `@/lib/index-chart-svg`。

新測試 `StockIntradayChart.index.test.tsx`(mode 單元):三欄 readout / 無副圖 svg / 無 VP、成交點鈕 /
CDP 域外掛牌 testid 與字面 / **peg 與 `edge-price-ma5` y 差 ≥ EDGE_LABEL_H(MA 讓位)** / MA 價位 `fmt` 不 snap /
`overlaySupported=false` 反灰 title / 空態文字與無框 / aria-label / stock 預設下 pegs 零、readout 六欄、
副圖仍在(W-1 lock,mutation:把 `index` 閘改反 → 紅)。

### 3.2 🟢 `lib/index-accum-adapter.ts`(新)+ `.test.ts`

```ts
export function indexSeriesToAccum(series: IndexSeries, code: string, name: string): StockAccum
```
- `minutes`:`Object.entries(series.minutes)` → HHMM → 分鐘數(非四位數字 / 分鐘 ≥ 60 略過)→ **只收 `SPOT_WINDOW` 內(import `SPOT_WINDOW`,不另抄 X_START/END)** — vwap / high / low 與幾何 `windowedEntries` 同一把尺,窗外鍵(落檔舊格式 / 未來 1430)不會讓均價末點標籤與線位置脫節或日高標記缺席(`[amendment 2026-08-17: review R6]`)→ `Map<min, {c: v, v: 1, i: 0, o: 0, u: 0, h: v, l: v}>`(**v=1** 讓 `buildIntradayGeometry.vwapLine` 退化為分鐘收盤算術平均 = 現版 avgLine;h/l = c 讓高低等值反查一定命中);Map 依分鐘升冪。
- `vwap`:分鐘收盤算術平均(`Math.round`;空 → null)—— 與均價線末點同源。
- `high / low`:**分鐘收盤的 max / min**(不是 `series.high/low`)—— 等值反查才必命中;`[auto-default: 用分鐘收盤極值 | reason: series.high/low 是 tick 極值,分鐘收盤鮮少等於它,標記會靜默缺席;figcaption Quote 仍顯示 tick 高低,兩者差異 ≤ 分鐘內振幅,spec 註記]`。空 → null。
- `last`:`series.p !== null ? {p: series.p, t: "", cum_vol: 0} : null`。
- `meta`:`{name, ref: series.ref, upper: null, lower: null, y_vol: null}`(upper/lower null → 幾何走對稱 autofit,見 §5 觀感差異)。
- 其餘:`code`、`seq: 0`、`ticks: []`、`vp: new Map()`、`book: null`、`noData: false`、`trial: false`、`amountMilli: 0`、`volume: 0`。
- 測試:HHMM→分鐘、v=1、h/l=c、vwap 算術平均、high/low 取自收盤、非法鍵略過、**窗外鍵(1430)不進 minutes 也不影響 vwap/high**、ref null 透傳、p null → last null、空 minutes。

### 3.3 🔴 `components/index/MarketChart.tsx` — 換元件 + adapter + `lib/pane-frame.ts` + `MarketPane.tsx`

- 刪 module-private `IntradayChart`、`SIZE`、`toX`、`fmt`、`labelText`、`labelKey`、`labelBounds`、`IntradayProps`;刪 import
  `buildIndexGeometry / outOfDomainLevels / RightEdgeLabel / rightEdgeLabels / X_END_MIN / X_START_MIN`(index-chart-svg)、
  `svgFontRem`(pane-frame)、`LEVEL_FILL / LEVEL_STROKE / overlayLines`(stock-intraday-svg)、`pts`、`HOUR_TICKS`;
  以 `npx eslint src` 零 unused 為準(`[amendment 2026-08-17: review R7]`)。
- Props:新增 `intradayBox?: { width: number; height: number }`(**px,1:1**,intraday 限定;未給 = 量不到 → core 走
  800×260 預設);`height?` **維持** candle 專用(viewBox 單位透傳,JSDoc 註明「intraday 不讀」);**移除 `unitScale`**
  (唯一讀者是自繪 intraday;K 線態本就不吃 — KR-3)。同一 prop 不帶兩種單位(`[amendment 2026-08-17: review R12]`)。
- intraday 分支:
  ```tsx
  const accum = useMemo(() => series === null ? null : indexSeriesToAccum(series, `IX:${marketKey}`, name), [series, marketKey, name]);
  if (mode === "intraday") {
    if (accum === null) return <p ...>等待指數資料…</p>;   // series null(既有句)
    return <IntradayChartCore accum={accum} toggles={toggles} onToggle={onToggle} variant="page" mode="index"
      width={intradayBox?.width} mainHeight={intradayBox?.height} overlay={overlayQ.data ?? null}
      overlayError={overlayGate && overlayQ.isError} overlaySupported={marketKey === "TWSE"}
      overlayOffTitle={marketKey === "TWSE" ? "無日線資料" : "櫃買無日 K 資料源"} ariaLabel={`${name}分時走勢`} />;
  }
  ```
- `lib/pane-frame.ts`:`PANE_FRAMES` 移除 `intraday`(型別收成 `"overlay" | "candle"`);新增
  ```ts
  /** 分時態 1:1 box(同 cardSvgBox 精神):chrome = core 頂列 26(h-[1.375rem] 22 + mb-1 4),−2 抗抖,地板 96 */
  export const INTRADAY_CHROME_Y = 26;
  export function paneIntradayBox(size: Size): { width: number; height: number; usable: boolean }
  ```
  `usable=false`(量不到)→ MarketPane 傳 `undefined` 讓 core 走 800×260 預設(= jsdom / 舊瀏覽器 fallback)。
- `MarketPane.tsx`:分時且非重疊 → `box = paneIntradayBox(size)`,`<MarketChart intradayBox={box.usable ? box : undefined} />`;
  `frame` / `svgHeight` / `unitScale` **只在** `overlayPair !== null || mode !== "intraday"` 分支計算(overlay → PANE_FRAMES.overlay、
  candle → PANE_FRAMES.candle),intraday 態不再算無人讀的 candle 值(`[amendment 2026-08-17: review R12]`);不再傳
  `unitScale` 給 MarketChart(OverlayCard 續用)。figure `min-h-48` 不變(chrome 62 未變:core 頂列 26 = 舊 toggle 列 26)。
- 測試該紅 → 改:`MarketChart.test.tsx`(SC-3 疊線 / toggle 列 / G-2 / 昨收標籤 / y 域 / a11y / 均價線 /
  height prop 各 describe 改為 core 語彙:`y-tick-price` 三格、`overlay-peg-*`、readout、`stroke-ink` 均價
  polyline、viewBox = `${width} ${height}` 或預設 800×260;`aria-label` 沿 `{name}分時走勢`);
  `MarketPane.size.test.tsx:137-166`(三態 → 兩態 + `paneIntradayBox` 算式)、`:168-188`(分時 svg 高 =
  box.height、寬 = box.width;無 RO → 800×260)、`:224-255`(字級補償只驗 overlay 態)。
  `MarketPane.test.tsx:318-431` 逐案跑,只改真的紅的。

### 3.4 🔴 佈局 `IndexPage.tsx` + `AdvanceDeclineChart.tsx`(`[amendment 2026-08-17: review R3/R10]` 條件化到兩欄態)

**為什麼不能直接寫 `@[1050px]:flex-[3]`**:雙圖 grid / 家數帶 section / 騰落線 wrapper 的最近 `@container`
祖先是**左欄**(它為了 640px 雙圖斷點自己是 container),兩欄態左欄僅 630–930px → 掛在它們身上的
`@[1050px]:` 永不成立(frontend-conventions「巢狀 container」陷阱,pane 層 min-h-0 同一教訓)。
能量到 root 的只有左欄本身 → 由左欄以 `@[1050px]:` 設 CSS 變數,子節點讀變數;**變數預設值 = 改動前的
字面行為**,單欄態由建構保證不變(W-4)。

- 左欄 `IndexPage.tsx:131`:加
  `@[1050px]:[--idx-chart-flex:3_1_0%] @[1050px]:[--idx-adl-flex:2_1_0%] @[1050px]:[--idx-adl-wrap-flex:1_1_0%] @[1050px]:[--idx-adl-min:10rem]`。
- 雙圖 grid `:140`:`flex-1` → `[flex:var(--idx-chart-flex,1_1_0%)]`(預設 = `flex-1` 的展開值);`min-h-80` 不變。
- section `:168`:`flex shrink-0 flex-col gap-2` → `flex min-h-0 flex-col gap-2 [flex:var(--idx-adl-flex,0_0_auto)]`
  (預設 = `shrink-0` 的展開值 `0 0 auto`;`min-h-0` 無條件安全:單欄態 flex 不縮,min-height 不作用)。
- `AdvanceDeclineChart.tsx:76` 根:`flex flex-col gap-1` → `flex min-h-0 flex-1 flex-col gap-1`(單欄態在 auto 高
  section 內 flex-1 無自由空間 = 內容高;兩欄態填滿 section);`:82` wrapper:`flex h-24 shrink-0 items-center
  justify-center` → `flex h-24 items-center justify-center [flex:var(--idx-adl-wrap-flex,0_0_auto)]
  [min-height:var(--idx-adl-min,auto)]`(單欄態 = `h-24 shrink-0` 逐值等價;兩欄態 basis 0% 覆寫 height、
  `min-height` 10rem = 160px 地板,仍是外層 flex 指派高 — useContainerSize 契約 2)。
- 變數命名前綴 `--idx-`(整頁唯一;只在 IndexPage 子樹使用,jsdom 鎖 class 字串,真值由 SC-6 `getComputedStyle` 驗)。
- 比例 `[auto-default: 雙圖 6 : 騰落線段 5 | reason: 原案 3:2 實測 1080p 騰落線/figure 0.47、864p 溢出 18px 出捲軸(家數帶兩列 + 標題 ≈ 150px 固定 chrome 吃掉比例);6:5 實測 1080p 0.653 / 864p 0.638 皆不捲,是滿足 SC-6 的最小調整;等分 0.84 會讓單線圖比兩張指數圖還高]` `[amendment 2026-08-17: Phase 6 real-env,689c0a6a]`。
- 推導(1080p,主 grid 高 ≈ 900):BasisRow 28 + gap 12×2 = 52 → 848 × 3/5 = 509(grid)/ 339(section);
  figure ≈ 509 − 28 − 28 − 24 = 429;section 內家數帶 ≈ 60 + gap 8 → 騰落線 ≈ 271 → 271/429 = 0.63 ✓。
  864p(主 grid ≈ 690):638 → 383 / 255;figure ≈ 303;騰落線 ≈ 187 → 0.62 ✓;svg 高 = 303−62−28 = 213 ≥ 96 ✓。
  1366×768:容器 1017 < 1050 → 單欄態,變數不套用,騰落線 96px、grid 內容決定高(= 改動前)。
  **實測值以 SC-6 evidence 為準**,若 < 0.6 調變數比(不是改 SC)。
- 測試該紅 → 改:見 §3.5 逐案表。

### 3.5 既有測試逐案表(`[amendment 2026-08-17: review R4]`)

| 檔 | 案 | 判定 | 理由 / 改法 |
|---|---|---|---|
| `MarketChart.test.tsx` | 全檔 intraday 案(疊線 SC-3 ×3 / toggle 列 ×4 / G-2 ×1 / 昨收 ×2 / y 域 ×1 / a11y ×1 / 均價線 ×1 / height intraday ×1) | **該紅(🔴)**,重寫為 core 語彙 | 右緣文字 → `y-tick-price` 三格 + `overlay-peg-*` + `edge-price-ma*`;aria-label 沿 `{name}分時走勢`;均價 polyline `stroke-ink`;height 案 → `intradayBox` 1:1 / 未給 800×260;candle 兩案(:375-395)不動 |
| `MarketPane.size.test.tsx` | `paneSvgHeight 三態` :137-166 | **該紅** | intraday 列移除;新增 `paneIntradayBox` 算式(430×300 → 430×272;地板 96;量不到 usable=false) |
| 〃 | `量測 → 圖高` :168-188 | **該紅** | 分時 svg viewBox = `0 0 430 272`;無 RO → `0 0 800 260` |
| 〃 | `依模式選 frame(TD-7)` :190-219 | 不該紅 | overlay / candle 走原 frame;註記:`PANE_FRAMES.intraday` 移除後「分時選對 box」的覆蓋 = :168-188 那支 |
| 〃 | `字級補償(WL-3)` :224-255 | **該紅** | 分時 1:1 後不補償;改為驗 overlay 態 `OverlayCard` 字級仍補償(`指數重疊走勢` svg 首個 text) |
| 〃 | `可縮鏈` :256-270 | 不該紅 | `root.querySelector("figure")` 仍是 pane figure(core index 態外層是 div) |
| `MarketPane.test.tsx` | 全檔 30 案 | 不該紅(29 案);**1 案 test-infra-fix**(`[amendment 2026-08-17: 實作發現]` 標的列案 `getByText("42039.92")` 因 readout 也印最新分鐘點位而撞兩元素 → 收斂到 `within(figcaption)`,語意不放寬,同檔昨收先例) | grep 只查了 svg 語彙,漏「數值字面撞名」類 |
| `AdvanceDeclineChart.test.tsx` | :225 量得到 640×96 → vb 96 | 不該紅 | 量測不變 |
| 〃 | :231 無 RO → 150 | 不該紅 | |
| 〃 | :237-247 wrapper 契約 | **:238 `h-24` 不該紅(保留)/ :242 `shrink-0` 該紅(改為 `[flex:var(--idx-adl-wrap-flex,0_0_auto)]` + `[min-height:var(--idx-adl-min,auto)]`)/ :245-246 `h-full` `w-full` 不該紅** | 案名改「wrapper 預設 h-24 不縮,兩欄態由 --idx-* 變數接管」 |
| `IndexPage.test.tsx` | y3 :322-332 | 不該紅(只 assert `grid-cols-1 / @[640px] / min-h-80 / not min-h-0`,不 assert `flex-1`) | 新增 y5:左欄帶四個 `@[1050px]:[--idx-` 前綴、grid 含 `[flex:var(--idx-chart-flex`、section 含 `[flex:var(--idx-adl-flex` 且不含 `shrink-0` |
| 〃 | y4 :337-347 | 不該紅 | |
| `StockChart.test.tsx`(11 處 `分時走勢圖`)、`StockIntradayChart.test.tsx` / `.variant.test.tsx`、`GroupGridView*.test.tsx`、`stock-intraday-svg.test.ts`、`chart-frame*.test.ts`、`index-chart-svg.test.ts`、`App.test.tsx` | 全部 | **不該紅(SC-5 / W-1)**,不改一字 | |

## 4. Edge cases(≥3)

1. `series.ref === null`(開盤前 / 後端缺昨收):`hasRef=false` → 單色 accent 線、無填色、readout % 「-」、
   yTicks 以首筆收盤置中;現版是虛線昨收畫在 avg 上 → 行為變(同個股語意),記 §5。
2. `minutes` 空但 series 非 null:core 空態「等待指數資料…」(現版畫空軸)。
3. 極矮容器:`paneIntradayBox` 地板 96px → figure 溢出交給主 grid overflow(既有逃生口)。
4. 加權 overlay 200 但三欄 null(TC4 沒開)→ CDP/MA 反灰「無日線資料」;60s 輪詢恢復後鈕自動亮(useIndexOverlay 不動)。
5. CDP 全部域外(平靜日對稱域 ±1%)→ 只掛牌不畫線;掛牌堆疊上限受 `EDGE_LABEL_H` 與 plot 高限制,矮圖溢出者被
   clamp 到界內可能疊印(**接受**:與現版 `rightEdgeLabels` 同級的既有債,見 next-time:104-107)。
6. 兩 pane 同選加權:兩份 core 各自 hover、共用 toggles → 兩圖 CDP 同開同關(現版同)。
7. 櫃買 pane 切到 K 線再切回分時:core 重掛,`useContainerSize` wrapper 恆存 → 尺寸即時。
8. 開盤第一分鐘 / 單一分鐘鍵:高 === 低 → 只畫日高標記(core 既有規則,不是 bug);`series.p` null → 無現價圈。
9. 單欄態(<1050px 容器):`--idx-*` 未設 → 三處 flex 走預設值 = 改動前 class 的展開值,騰落線 96px。

## 5. 觀感差異(換元件的必然變化,不算破壞)

- y 域由「hi×1.003 / lo×0.997 緊貼」改為「以昨收置中的對稱域(半幅 = max 偏離 ×1.1,≥1%)」:單邊行情日
  另一半留白、線的振幅視覺上變小;換來的是「離昨收多遠」一眼可讀 + 與個股頁一致。截圖前後對照
  落 `evidence/SC-2-domain-before-after.md`。
- 左緣新增價位帶(Y_AXIS_W 36px)與右緣帶(R_AXIS_W 40px),繪圖區寬 −76px。
- 均價線值標籤(末點)新增;昨收標籤由右緣文字改為左緣刻度中格 + 昨收虛線。
- 高低點文字用分鐘收盤極值,可能與 figcaption 的 tick 高低差 ≤ 分鐘內振幅。
- 1:1 像素:字級不再隨 pane 寬縮放(取代 unitScale 補償),與群組卡片同法。
- 左緣 y 刻度三格依相對昨收上紅下綠(`tickTone`)+ 三條水平格線(`y-grid`);現版是灰字無格線。

## 6. 三類 commit 順序與 TDD tag(`[amendment 2026-08-17: review R5]`)

1. 🟢 `test(frontend): IntradayChartCore mode="index" 契約 [red]`(`StockIntradayChart.index.test.tsx`)
   → 🟢 `feat(frontend): core 加 mode / overlay 注入 + pegs(個股零變化) [green]`
2. 🔴 `test(frontend): MarketChart / MarketPane.size 改吃 core 語彙 + adapter 測試 [red]`
   → 🔴 `fix(frontend): 指數分時圖換 IntradayChartCore(adapter、1:1 box、unitScale 退場) [green]`
3. 🔴 `test(frontend): 騰落線 / 左欄 flex 變數契約 [red]` → 🔴 `fix(frontend): 兩欄態左欄 3:2、騰落線吃剩餘高 [green]`
4. (若有)🔵 review fix 之純重構

可逆 = revert 兩個 🔴 [green] + 🟢 [green](index 態新行為住在 🟢 那顆)。

## 7. Out of scope

- 量能副圖 / IX0001 量 probe(D11 拍板不做)。
- `lib/index-chart-svg.ts` 的 `buildIndexGeometry` / `rightEdgeLabels` 死碼清理與其測試 → next-time。
- 個股 core `EDGE_LABEL_H` / K 線態窄 pane 字級債(next-time:72-80)不修;verification 標註是否惡化。
- OverlayCard 換 core(它是兩序列相對 % 疊線,不同語意)。
- 高低點改用 tick 極值(需後端 per-minute 高低)。

## 8. Backward compat / migration

無對外 API、storage、資料格式變更;`MarketChart` 單一 caller 同步改;無 migration。可逆見 §6。

## 9. Known risks

- KR-3 兩欄態較矮視窗(容器 ≥ 1050px 但主 grid 高 < ~800px):section 分到的高 < 家數帶 + 騰落線 10rem 地板 → 主 grid 出捲軸(既有逃生口語意;code review C-3)。1080p / 864p 實測不捲;若 user 常用尺寸命中,候選 = 降 `--idx-adl-min` 或 section `flex: 5 1 auto`。

- KR-1 對稱域讓 CDP 常態域外 → 掛牌是唯一訊號;若 user 覺得看不到線,候選是 index 態域改「含 overlay 值」
  (需 core 幾何加參數,另案)。
- KR-2 兩 pane 各 271 分鐘 × 每 tick 重折 adapter(useMemo 依 series identity;useIndexStream 每 tick 新物件)
  → 每 tick 兩次 O(271) 折疊,與 CardIntradayChart 同量級,可接受。

---
self_review_head: c326dee0(code review round 1:P1×3 accepted 已修 / P2 行為級 1 入 KR-3;post-fix 全量 gate 見 verification.md)
