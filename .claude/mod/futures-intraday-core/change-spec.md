# change-spec — 期貨頁分時圖換 IntradayChartCore(mode="futures")+ 分 K 檔位 1–10 / 15 / 30 / 60

分支 `mod/futures-intraday-core`;現況表見同目錄 `current-state.md`(行號基準 master `010330ad`)。
來源:user 2026-08-18 口頭需求(「期貨頁面的分時圖改為跟個股的分時圖一樣,就像前幾次把大盤 / 櫃買分時圖
改的那個分支;再把期貨的 K 棒調整為 1–10 分、15 分、30 分、60 分」)。
**分流判定**:已成形方案(指名元件 = 個股同款 core、指名前例 = PR #63 index-intraday-core、指名檔位表)→
grilling 姿態、無方向性抉擇 → 逐題 `[auto-default]` 推進不停等;收尾回報列全部 auto-default。

規模:**L**(≥ 5 檔:core / lib/allday / 新 adapter / FuturesChart / fut-chart-mode + 測試;跨 stock / futures
兩個元件族)→ spec review 1 輪 + accepted P0 限縮加輪。

## 0. 目標(一句話)

期貨 tab 分時圖改吃個股同一份 `IntradayChartCore`(新 mode="futures":近全三段軸注入、hover 十字 / readout 六欄 /
昨收紅綠填色 / 真 VWAP 均價線 / 高低點 / 成交量副圖 / 內外盤說明列 / VP;持倉均價與 OI 撐壓 hlines 保留),
且 K 線檔位由 1/5/15/30/60 擴為 1–10 / 15 / 30 / 60。

## 1. 成功條件(SC;UI 條皆「畫面可指認」)

| # | 條件 | 驗證方式 |
|---|---|---|
| SC-1 | 期貨分時圖 = 個股同款 core:游標移入出現**虛線十字**(垂直線落該分鐘、水平線跟滑鼠)+ 左緣價位標(整數點,不 snap 個股 tick)+ 底部「時間 / 該分鐘收盤」兩行標籤;左上 readout **六欄** `HH:MM / 價 / 漲跌% / 量 / 外 / 內`(無 hover 顯最新分鐘;時間文字為**牆上時刻**(如 `21:35`,不是軸索引);外 / 內來自 1K `uv/dv`);主線相對 `state.ref` 平盤上紅下綠 + 填色 | vitest `FuturesChart.test.tsx` 新案(`fireEvent.mouseMove` → `crosshair-v` / `crosshair-h` / `price-tag-text` / `time-tag-text` 印 `HH:MM` / readout 六欄;**hover 需 `getBoundingClientRect` stub 成 800×260,clientX 由 `minuteToX(index, 800, ALLDAY_WINDOW)` 反算才命中有 bar 的索引**,`[amendment 2026-08-18: review R7]`);截圖 `evidence/SC-1-fut-hover.png` |
| SC-2 | 近全三段軸**保留**:13:45 與 15:01 相鄰(死區不佔 x)、05:00 為軸尾;底部時間標籤 = `09:00 11:00 13:00 15:00 18:00 21:00 00:00 03:00 05:00` 九個;前一交易日 bars 被 slice 掉 | vitest(polyline points x = `minuteToX(alldayIndexOf(HHMM), 800, ALLDAY_WINDOW)`;`XAxisLabels` 九個文字);截圖同 SC-1 |
| SC-3 | 均價線(白 `stroke-ink` 1.2,值 = Σc·v/Σv 真量加權)+ 末點標籤;當日高 / 低空心環 + 價位文字(標在該分鐘;高===低只畫高);現價實心圈於序列末點(高於昨收紅 / 低綠 / 無 ref 灰);昨收虛線 `2 3`;左緣 3 格刻度(autofit:上 / 昨收 / 下)依相對昨收紅綠 | vitest testids `edge-price-vwap` / `day-high` / `day-low` / `last-dot` / `y-tick-price` 三格;截圖同 SC-1 |
| SC-4 | 成交量副圖(`aria-label="成交量"`)+ 說明列 `外盤 X · 內盤 Y · 未分類 Z · 外盤比 · (判定率) / VWAP` 兩者皆 render;toggle 列五顆:均價 / VP 可按;**CDP / MA / 成交點反灰** + title「期貨分時本輪不提供 CDP/MA/成交點」;VP 開時 `vp-bar` ≥ 1(價位別量由分鐘收盤 × 量折入,鍵 = 5 點桶心 `snapDown(c)+tick/2`,一根 bar 鎖 `priceMilli` 期望值;`[amendment 2026-08-18: review R9]`) | vitest(副圖 svg / figcaption / `toggleDefs` disabled + title / `vp-bar` 數);截圖 `evidence/SC-4-fut-toggles.png` |
| SC-5 | **hlines 保留**:持倉均價(本契約,label「均 23000 多2口」+ `<title>`)與 OI 撐 / 壓線在分時圖上照畫(testid `chart-hline`),**價位超出 y 域那一條不畫**(不 clamp);K 線態 hlines 不動 | 既有 `FuturesChart.test.tsx:316-373` 三案**只改前置一行**(`findByTestId("allday-line")` → `svg[aria-label="期貨近全時段分時走勢"]`),hlines 斷言(`均 23000 多2口` / `chart-hline` 計數 / 域外不畫)一字不動全綠;新域 ref 22,950,000、半幅 = max(650k, 550k, 229.5k)×1.1 = 715k → [22,235,000, 23,665,000]:23,000 內 / 30,000 外 / 21,000 外 → 「畫 1 條」期望不變(`[amendment 2026-08-18: review R1]`);截圖 `evidence/SC-5-fut-hlines.png`(有部位或 OI 時) |
| SC-6 | live 現價點語意保留:牆上時鐘落點 + 三道 gate(死區 / 錨定日 / 時鐘落後)→ gate 擋下時序列**不追加** live 分鐘、`last-dot` 落在末根 bar 的 x;同一錨定日通過時 `last-dot` cx = `minuteToX(當前分+1 索引)`、y = `state.p` | vitest 既有四案改為 core 語彙(`last-dot` cx / polyline 點數) |
| SC-7 | 分時圖高度吃剩餘空間(同個股頁):wrapper 量測 → `svgBox(size, 800)` → mainH:subH = 260:70;jsdom 量不到 → viewBox `0 0 800 260` / `0 0 800 70`;**K 線態不傳 height(1400×578 等比不變)** | vitest(RO mock 沿 `StockChart.test`/`MarketPane.size.test` 樣板:量到 1000×500 → 主圖 viewBox 高 = `round(vbH×260/330)`;無 RO → 800×260) |
| SC-8 | K 線檔位:模式列 = `分時 / 1分 / 2分 … 10分 / 15分 / 30分 / 60分 / 日K`(15 顆,順序如此);任一分 K 鈕 → `aggregateBars(bars, n)`(m7 → 7 分桶);localStorage 舊值 `m5` / 新值 `m7` 皆還原;`isFutChartMode("m7") === true`、`("m11") === false` | vitest `fut-chart-mode.test.ts`(逐值)+ `FuturesChart.test.tsx` 模式列案;截圖 `evidence/SC-8-fut-modes.png` |
| SC-9 | **個股頁 / 群組圖牆 / 台股綜合分時圖零變化**(mode 預設 stock;index 態逐字不變) | `StockIntradayChart*.test` / `GroupGridView*.test` / `MarketChart.test` / `MarketPane*.test` / `stock-intraday-svg.test` **不改一字**全綠;個股頁截圖前後 `evidence/SC-9-stock-{before,after}.png` |
| SC-10 | 三類 commit 分明:🟢 core mode/hlines/軸注入 + adapter + allday 純函式([red]→[green])→ 🔴 FuturesChart 換元件([red]→[green])→ 🔴 檔位擴充([red]→[green]);既有測試紅只在 🔴 `[red]` commit | `git log` 對照 §6 |

**驗證窗口**:SC-1~6 真資料 hover 需 TC4 期貨 1K(近全時段幾乎全天有;週末 / 05:00–08:45 死區顯示最後錨定日序列仍可 hover)。
真 TC4 層截圖以 prod 8721 或 `--verify` 側車為準;截不到 → `browser_unavailable` + 假資料 fixture 截圖,真 TC4 層記「待 prod 重啟 + user 過目」。

## 2. 不能破壞的既有行為白名單

- W-1 `StockIntradayChart` / `CardIntradayChart` / `MarketChart`(index 態)渲染逐字不變:新 props(`mode="futures"` / `xWindow` /
  `hourTicks` / `timeText` / `hlines`)全 optional 且預設 = 現行為(`xw = stkfut ? STKFUT_WINDOW : SPOT_WINDOW`、
  `hourTicksOf(xw)`、`hhmm`、`EMPTY_HLINES`);`useStockOverlay` 仍無條件呼叫;index 態的每個閘不改判準。
- W-2 期貨 K 線態(1–60 分 / 日K):`CandleChart` 用法(`key` / `initBars` / `hlines` / `volumeDelta`、**不傳 height**)不動;
  `useFuturesBars` 的 query key / tf 分派 / 輪詢 gate(`active`)不動;`MINUTE_INIT_BARS = 240` / `DAILY_INIT_BARS = 120` 不動。
- W-3 hlines 內容(`useMemo` 依 positions / contract / oiStrikes / oiDate / spotMilli;契約完整字串相等;`pickOiLines`)不動;
  分時 / K 線兩態同一份。
- W-4 live 點的四道判定(`liveSlotOf` 當前分 + 1 / 死區 null / `live.anchor !== anchorDateOf(last.t)` / `tail.index > live.index`)
  與「刻意不 useMemo」不動;`sliceCurrentAllday` 不動。
- W-5 空 / 壞態文案不動:isPending「載入中…」/ isError「K 線載入失敗」+ message / `meta.source === "unavailable"`
  「暫無資料(TC4 未回應)」/ 分時空序列「無分時資料」。
- W-6 模式列既有七檔的值、標籤與順序不動(只在 1 與 5 之間插 2–4、5 與 15 之間插 6–10);`initialFutChartMode` 壞值退 intraday /
  try-catch 不拋;`persistFutChartMode` 不拋。
- W-7 `FuturesPage` / App 掛法與 `FuturesChart` 對外簽名(`product / state / resolvedYm / active`)不動。
- W-8 `useChartToggles` 存檔 schema / DEFAULTS / TOGGLES_VERSION 不動(期貨分時只是多一個讀寫者)。
- W-9 `lib/allday.ts` 既有 export(`ALLDAY_SEGMENTS / ALLDAY_LEN / alldayIndexOf / ALLDAY_TICKS / anchorDateOf /
  sliceCurrentAllday`)值與簽名不動;只新增。
- W-10 core 不沾 capital / TQ(hlines / fills 由 caller 折好傳入;futures 態 `fills` 恆 `EMPTY_FILLS`)。

## 3. 設計(diff 級)

### 3.1 🟢 `components/stock/StockIntradayChart.tsx` — core 加 mode="futures" / 軸注入 / hlines(stock / index 零變化)

新增 / 修改 `CoreProps`:
```ts
/** "futures" = 期貨近全時段分時:語彙同 stock(副圖 / 說明列 / readout 六欄 / VP),但價位口徑同 index
 *  (`fmtIndexPts`,不 snap 個股 tick)、不打 /api/stock/overlay(CDP/MA/成交點反灰)、x 軸由 caller 注入。 */
mode?: "stock" | "index" | "futures";
/** x 軸窗覆寫(key 值域;預設 `stkfut ? STKFUT_WINDOW : SPOT_WINDOW`)。**必經模組層常數**(進 memo props)。 */
xWindow?: XWindow;
/** 整點刻度覆寫(預設 `hourTicksOf(xw)`);同上 identity 穩定。 */
hourTicks?: readonly HourTick[];
/** key → 時間文字(readout 首欄 / hover 底部標籤);預設 `hhmm`。**模組層函式**。 */
timeText?: (minute: number) => string;
/** 任意水平參考線(期貨:持倉均價 / OI 撐壓)。域外不畫;預設 `EMPTY_HLINES`。**必經呼叫端 useMemo**。 */
hlines?: readonly ChartHLine[];
```
行為(以 `const futures = mode === "futures"` 為唯一判別子;下列每處只在 futures / 通用注入處改,stock / index 逐行不變):
- `xw = xWindow ?? (stkfut ? STKFUT_WINDOW : SPOT_WINDOW)`;`derivedTicks = useMemo(() => hourTicksOf(xw), [xw])`(hook 不條件化),
  `hourTicks = hourTicksProp ?? derivedTicks`。
- overlay 查詢:`useStockOverlay(index || futures ? null : accum.code || null, !index && !futures && !stkfut && !isInstrumentKey(...) && (...))`;
  `overlay = index || futures ? overlayProp : ...`、`overlayFailed = index || futures ? overlayError : ...`;
  `supported = (!index && !futures) || overlaySupported`(FuturesChart 傳 `overlaySupported={false}` → CDP/MA 恆反灰)。
- toggleDefs:futures 走 **stock 分支**(五顆),但 `fills.available = !futures`;disabled title 鏈
  `index || futures ? overlayOffTitle : stkfut ? ... : ...`(FuturesChart 傳 `overlayOffTitle="期貨分時本輪不提供 CDP/MA/成交點"`)。
- 價位口徑:`pts = index || futures` → `hoverPrice = pts ? g.priceAtY(y) : snapDown(...)`、`hoverPriceText = pts ? fmtIndexPts : fmt`、
  `priceText={pts ? fmtIndexPts : fmtTickPrice}`、`tickText={pts ? fmtIndexPts : undefined}`。
- 時間文字:readout `timeText(shownMin)`、time-tag `timeText(hoverMin)`(預設 `hhmm` → stock/index 逐字同)。
- **live 佔位分鐘的量欄**(`[amendment 2026-08-18: review R4]`,`[auto-default: (b) futures 態 `shownAgg.v === 0` → readout 量 / 外 / 內 印「-」 | reason: bars 60s 輪詢、live 走牆上時鐘,最新分鐘常是尚無 1K 的佔位格,印 0 是假數字;TC4 1K 只在有成交時才有 row(v ≥ 1),v = 0 在 futures 態唯一來源就是佔位]`):stock / index 態不改(stock 的分鐘由 tick 累出必 v ≥ 1;index v = 1)。副圖該格高 0(無量可畫,誠實)。
- 副圖 / VP / side / readout 六欄 / figure 外框 / 空態框:futures **同 stock**(既有 `index` 閘不加 futures)。
  空態文字:`index ? "等待指數資料…" : futures ? "無分時資料" : "尚無成交"`(W-5 字面)。
- **hlines**(ChartStatic 新 prop `hlines = EMPTY_HLINES`;模組常數):繪於主價線之後、極值標記之前;每條
  `priceMilli` 在 `g.yDomain` 閉區間外 → 不畫(同 `overlayLines` 判定);
  `<g data-testid="chart-hline">{title && <title>}<line x1={Y_AXIS_W} x2={w−R_AXIS_W} y=g.toY(p) className={ln.className} strokeWidth=1 strokeDasharray="5 3"/>
  <text x={w−R_AXIS_W−2} y={y−3} textAnchor="end" className="fill-ink stroke-surface" strokeWidth=2 paintOrder="stroke" fontSize="0.5625rem">{label}</text></g>`
  `[auto-default: 字級 0.5625rem 與 core 右緣標籤同級(舊 0.625rem)| reason: 同圖同級標籤一律 0.5625rem,避免兩套字級]`。
  型別 `ChartHLine` 自 `@/components/stock/CandleChart` import(既有 export;無反向 import,不成環)。

新測試 `StockIntradayChart.futures.test.tsx`:readout 六欄且首欄走 `timeText`(index 3 → `"09:00"` 假函式可辨)/ 副圖 + 說明列在 /
toggle 五顆:cdp / ma / fills disabled + title、vwap / vp enabled / hover 價標整數點不 snap / `xWindow` + `hourTicks` 注入:
polyline x = `minuteToX(key, w, xw)`、XAxisLabels 印注入 label / hlines:域內畫(testid + title + label)、域外不畫 /
不打 `/api/stock/overlay` / **W-1 lock**:mode 預設下 `hourTicks` = `hourTicksOf(SPOT_WINDOW)` 標籤、time-tag 走 `hhmm`、
hlines 零(mutation:把 `pts` 判別改成 `!index` → stock 案紅)。

### 3.2 🟢 `lib/allday.ts` 新增(既有 export 不動)+ `lib/futures-accum-adapter.ts`(新)

`lib/allday.ts`:
```ts
/** 近全軸當 core 的 x 窗:key = 軸索引 0..ALLDAY_LEN−1。模組常數(進 memo props)。 */
export const ALLDAY_WINDOW: XWindow = { start: 0, end: ALLDAY_LEN - 1 };
/** `ALLDAY_TICKS` 換成 core 的 `HourTick` 形狀(minute 欄放軸索引)。 */
export const ALLDAY_HOUR_TICKS: readonly HourTick[] = ALLDAY_TICKS.map(({index, label}) => ({minute: index, label}));
/** 軸索引 → `HH:MM`(`alldayIndexOf` 的反函式);域外 / 非整數 → ""。 */
export function alldayHhmmOf(index: number): string
/** `YYYY-MM-DD HH:MM` → 軸索引;非分 K 時戳 / 死區 → null(自 FuturesChart `indexOfBar` 搬入,行為同)。 */
export function alldayIndexOfStamp(t: string): number | null
```
`lib/futures-accum-adapter.ts`:
```ts
export interface FuturesLive { index: number; p: number }
export function futuresBarsToAccum(input: {
  bars: readonly Bar[];   // 已 sliceCurrentAllday 的當前錨定日 bars(升冪)
  live: FuturesLive | null; // 已過四道 gate 的 live 點;null = 不合
  ref: number | null; name: string; code: string;
}): StockAccum
```
- `minutes`:每根 bar `index = alldayIndexOfStamp(b.t)`(null 略過)→ `{c: b.c, v: b.v, o: b.uv ?? 0, i: b.dv ?? 0,
  u: max(0, v − (uv ?? 0) − (dv ?? 0)), h: b.h, l: b.l}`(uv/dv 缺欄 → u = v,判定率 0% 誠實呈現);
  `c <= 0` 的 bar 略過(同 index adapter 的 0 收口)。**live 合入**:`live !== null` → 同索引已有 →
  `{...agg, c: p, h: max(h, p), l: min(l, p)}`;無 → `{c: p, v: 0, o: 0, i: 0, u: 0, h: p, l: p}`。
- `vwap`:Σc·v / Σv(整份 minutes,含 live 分鐘的 v;`Math.round`;Σv = 0 → null)—— 與 core `vwapLine` 末點同源同值。
- `high / low`:minutes 的 `max(h)` / `min(l)`(空 → null);live 已折進 h/l → 等值反查必命中。
- `last`:live → `{p: live.p, t: "", cum_vol: 0}`;否則末根 bar `{p: c, t: "", cum_vol: 0}`(`t / cum_vol` 無來源 → 空值佔位、core 不讀,同 index adapter;`[amendment 2026-08-18: review R8]`);空 → null
  `[auto-default: 無 live 也在序列末點畫現價圈(同個股收盤後行為)| reason: core 的現價圈語意是「線走到哪」,不是「現在有推播」;live gate 擋下時圈落在末根 bar 是正確語意]`。
- `meta`:`{name, ref, upper: null, lower: null, y_vol: null}`(±10% 漲跌停域會把期指日內線壓成平線 → 走對稱 autofit,同 index)。
- `vp`:每根 bar `key = snapDown(c) + tickOf(c) / 2`(= 5 點桶的**桶心**;`buildVpBars` 的帶界 = 與 `stepUp/stepDown` 的中點 → 帶恰為 `[k, k+5)`,與桶區間一致,不偏 2.5 點;`[amendment 2026-08-18: review R9]`)累加 `{t: v, o: uv ?? 0, i: dv ?? 0}`;`c <= 0` 略過
  `[auto-default: VP 以分鐘收盤 × 量折入、5 點檔位 | reason: 1K 沒有逐筆價量,分鐘收盤是唯一可得的價位;5 點檔位在 2 萬多點的期指上是合理粒度]`。
- 其餘:`code` / `seq: 0` / `ticks: []` / `book: null` / `noData: false` / `trial: false` / `amountMilli` = Σc·v / `volume` = Σv。
- 測試:索引映射與死區略過 / uv/dv → o/i/u(缺欄 u=v)/ live 覆寫同索引 c 與 h/l、新索引補格 v=0 / vwap 量加權 / high-low 取 h/l /
  last 三態 / meta upper-lower null / vp 5 點檔位聚合 / c<=0 略過 / 空 bars。

### 3.3 🔴 `components/futures/FuturesChart.tsx` — 換元件

- 刪 module-private `IntradayChart` / `buildIntradayGeometry` / `IntradayGeometry` / `IntradayPoint` / `toX` / `indexOfBar` /
  `INTRADAY_VB_W`(export)/ `INTRADAY_VB_H` / `Y_PAD` / `X_LABEL_H`;刪 import `ALLDAY_TICKS / alldayIndexOf(→ liveSlotOf 仍用,保留)/
  pts / fmt(hlines label 仍用,保留)/ ChartHLine(仍用)`;以 `npx eslint src` 零 unused 為準。
- 新 import:`IntradayChartCore` / `useChartToggles` / `useContainerSize` / `svgBox` / `ALLDAY_WINDOW, ALLDAY_HOUR_TICKS, alldayHhmmOf` /
  `futuresBarsToAccum`。
- live:既有 IIFE 改回 `{ liveIndex: number | null }`(四道 gate 判準逐字不動,W-4);`liveP = state?.p ?? null`。
  **gate 4 的輸入替代**(`[amendment 2026-08-18: review R3]`;`basePoints` 刪除):`tailIndex = useMemo(() => 由 slice 尾往前第一個 `alldayIndexOfStamp(b.t) !== null` 的索引,無 → null, [slice])`
  = 舊 `basePoints` 末點定義(最後一根**索引可解**的 bar,不是最後一根 bar);gate 4 改 `tailIndex !== null && tailIndex > live.index → none`;
  同索引覆寫 / 新索引 push 的分派下沉到 adapter(語意同)。新測試釘 gate 4 單獨成立:末根 bar 索引 > live 索引且錨定日相同(bars 至 D 10:00、時鐘 D 09:30)→ 主線點數 = bars 數、`last-dot` cx = 末 bar x。
- `accum = useMemo(() => futuresBarsToAccum({bars: slice, live: liveIndex === null || liveP === null ? null : {index: liveIndex, p: liveP},
  ref: state?.ref ?? null, name: state?.name ?? product, code: product}), [slice, liveIndex, liveP, state?.ref, state?.name, product])`
  (deps 全純量 / slice identity;live 落點是每 render 現算的純量,memo 命中率 = 同一分鐘同一價)。
- 尺寸:`const [sizeRef, size] = useContainerSize(); const box = svgBox(size, 800); mainH = usable ? round(vbH×260/330) : undefined; subH = usable ? vbH − mainH : undefined`;
  量測 wrapper `<div ref={sizeRef} className="flex min-h-0 flex-1 flex-col">` **恆存**包住 `body()`(loading / error / data 三態皆在內)。
- toggles:`const { toggles, set } = useChartToggles();`
- 分時分支:
  ```tsx
  if (mode === "intraday") return (
    <IntradayChartCore accum={accum} toggles={toggles} onToggle={set} variant="page" mode="futures"
      mainHeight={mainH} subHeight={subH} xWindow={ALLDAY_WINDOW} hourTicks={ALLDAY_HOUR_TICKS} timeText={alldayHhmmOf}
      hlines={hlines} overlaySupported={false} overlayOffTitle="期貨分時本輪不提供 CDP/MA/成交點" ariaLabel="期貨近全時段分時走勢" />
  );
  ```
  舊 `series.length === 0 → 無分時資料` 分支刪除(core futures 態空態同字);舊 `rounded-md border p-2` 包框刪除(core figure 已是框)。
- K 線分支逐字不動(W-2)。
- 測試該紅 → 改:`FuturesChart.test.tsx` 分時 / live 各案改 core 語彙(§3.5);hlines 三案 / 模式列 / 輪詢 / unavailable 不動。

### 3.4 🔴 `lib/fut-chart-mode.ts` — 檔位擴充

- `FutChartMode = "intraday" | "day" | \`m${1|2|...|10|15|30|60}\``(顯式 union 列舉 13 個字面值);
- `FUT_CHART_MODES` 由 `[1,2,3,4,5,6,7,8,9,10,15,30,60]` map 產生 `[\`m${n}\`, \`${n}分\`]`,首尾 `intraday / day` 不動;
  檔頭註解「檔位(1/5/15/30/60)也與個股(1–10 連續)不同」改為「1–10 連續 + 15/30/60」。
- `isFutChartMode` / `futMinutesOf` / `initialFutChartMode` / `persistFutChartMode` 不動(值域已由表推導)。
- 測試該紅 → 改:`fut-chart-mode.test.ts` 「七檔」案改 15 檔逐值;`isFutChartMode("m7")` 由 false 翻 true,另補 `"m11" / "m0"` false;
  `futMinutesOf("m7") === 7`;**「壞值」案 bad 清單的 `"m7"` 移除改 `"m11" / "m0" / "m61"`**(`[amendment 2026-08-18: review R2]`)。

### 3.5 既有測試逐案表

| 檔 | 案 | 判定 | 理由 / 改法 |
|---|---|---|---|
| `FuturesChart.test.tsx` | import `INTRADAY_VB_W` / `xOf()` helper | **該紅(🔴)** | 改 `minuteToX(index, 800, ALLDAY_WINDOW).toFixed(1)` |
| 〃 | 分時 SC-1 死區相鄰 :127 / slice :140 | **該紅** | `allday-line` → 主價線 polyline(`polyline.stroke-bull` 或 hasRef=false 時 `stroke-accent`;fixture STATE 有 ref → 取 clip 上半 `stroke-bull` 那條)points |
| 〃 | unavailable :155 | **該紅(第二斷言退化)**(`[amendment 2026-08-18: review R6]`) | 文案斷言不動;`queryByTestId("allday-line")` 刪後恆真 → 改 `querySelector('svg[aria-label="期貨近全時段分時走勢"]')` 為 null,歸 🔴 [red] |
| 〃 | 模式列 :105 / :117 | 不該紅 | 「5分」仍在;新增一案「1–10 / 15 / 30 / 60 共 15 顆、m7 寫 storage」 |
| 〃 | 輪詢 gate :164 / :177 | 不該紅 | |
| 〃 | live 四案 :195-243 | **該紅** | `allday-live` → `last-dot`:gate 擋下 → 主線點數 = bars 數且 `last-dot` cx = 末 bar x;通過 → cx = live 索引 x |
| 〃 | overlays K 線 :245-315 | 不該紅 | |
| 〃 | overlays 分時 :316-373 | **該紅(前置語彙一行)/ 斷言本體不動**(`[amendment 2026-08-18: review R1]`) | 三案 `findByTestId("allday-line")` → 以 `svg[aria-label="期貨近全時段分時走勢"]` 指認分時態;`chart-hline` / `<title>` / 域外不畫斷言逐字保留(新域判定見 SC-5) |
| `fut-chart-mode.test.ts` | 七檔 / m7 false | **該紅** | §3.4 |
| 〃 | 「壞值 / 別頁的值 → 退回 intraday(不把 'm7' 放行)」:69-74 | **該紅**(`[amendment 2026-08-18: review R2]`) | bad 清單移除 `"m7"`,改補 `"m11" / "m0" / "m61"`;案名括號改「不把 m11 這種白名單外的值放行」 |
| 〃 | futMinutesOf / 其餘 storage 案 | 不該紅 | |
| `FuturesPage.test.tsx` | 全檔 | 不該紅 | 不引用分時 svg 語彙(current-state §1.4);若因 core 多掛 hook(useChartToggles / RO)而需 stub → `test-infra-fix` |
| `App.test.tsx` 期貨 tab 案(:400-521,含 :515「期貨商品選擇寫入 localStorage」)| 全部 | 不該紅(`[amendment 2026-08-18: review R5]`) | 間接掛出 FuturesChart;core futures 態不打任何新 endpoint(`useStockOverlay` enabled=false、`useChartToggles` 只碰 localStorage、無 RO 走 800×260);[green] 後列入回歸清單 |
| `StockIntradayChart*.test` / `GroupGridView*.test` / `MarketChart.test` / `MarketPane*.test` / `stock-intraday-svg.test` / `time-labels.test` / `allday.test` | 全部 | **不該紅(SC-9 / W-1 / W-9)**,不改一字 | |

## 4. Edge cases(≥ 3)

1. `state === null`(WS 未就緒):`ref/name/p` 皆 null → `hasRef=false` 單色 accent 線、readout % 「-」;`last` 取末根 bar
   → 現價圈灰(無 ref 不判色);hlines 的 OI 以 `spotMilli=null` 走既有 `pickOiLines` 語意(不動)。
2. bars 帶 `uv/dv` 缺欄(舊後端 / DK 路徑不會進分時):`o=i=0, u=v` → 說明列判定率 0% + 警示色(誠實)。
3. 死區(13:46–15:00 / 05:01–08:45)hover:軸上沒有那些分鐘 → 只有 crosshair-h + 價標(核心既有分解退化)。
4. 週末 / 盤後看圖:slice = 最後錨定日整段 1140 分鐘;live gate 擋下(錨定日不同或死區)→ 現價圈在 05:00 末點。
5. 開盤瞬間(08:45–08:46 今日首根未回):slice 仍是前一日、live anchor 不同 → 不合入(W-4 語意保留)。
6. `live.index` 已存在(同分鐘 bar 已回):覆寫 c 並更新 h/l;高低標記可能因 live 價成為新高而移到當前分鐘。
7. bar `c <= 0`(TC4 偶發 "0"):略過,不進 minutes / vp。
8. `mode = "m7"` 於舊 build(若 prod 未重啟就切回):`isFutChartMode` 白名單退 intraday,不炸。
9. 極矮視窗:`svgBox` 地板 180px → figure 溢出交 FuturesPage `overflow-y-auto`(既有逃生口)。
11. hover 落在**無 bar 的分鐘**(夜盤薄量常見;近全軸 0.64 單位/分鐘,反演不 snap 最近):只有 crosshair-h + 價標,無十字垂直線 / readout 資料欄(core 既有分解退化,不是 bug;KR-5)。
12. live 佔位分鐘(尚無 1K)為最新分鐘:readout 量 / 外 / 內 印「-」,副圖該格高 0(R4)。
10. 兩 pane 或多 tab 共用 toggles(全站 localStorage):期貨頁關 VP → 個股頁也關(既有跨頁語意,同 index R4)。

## 5. 觀感差異(換元件的必然變化,不算破壞)

- y 域由「hi/lo × 0.3%」改為「以 ref 置中的對稱域(半幅 = max 偏離 × 1.1,≥ 1%)」:單邊行情日另一半留白;左緣 3 格刻度紅綠。
- 主線由單色 accent 改為相對昨收紅綠 + 填色;新增均價線 / 高低點 / 現價圈 / readout / 副圖 / 說明列。
- viewBox 由 1140×340 等比改為 800 × 量測高(1140 分鐘擠進 724 單位繪圖區 → 每分鐘 0.63 單位;副圖量柱 1 單位寬彼此相接,視覺近似面積圖)。
- 左緣價位帶 36 / 右緣 40 → 繪圖區寬 −76;hlines label 由 `W−4` 改到繪圖區右緣內側,字級 0.625 → 0.5625rem。
- 無 live 時現價圈仍畫在末點(舊版沒有 live 就沒有點)。
- 高低點用 1K `h/l`(tick 級極值反查必命中);VP 粒度 = 分鐘收盤 × 量。

## 6. 三類 commit 順序與 TDD tag

1. 🟢 `test(frontend): IntradayChartCore mode="futures" / 軸注入 / hlines 契約 + allday 純函式 + adapter [red]`
   → 🟢 `feat(frontend): core 加 futures 態 + xWindow/hourTicks/timeText/hlines 注入、allday 反函式、futuresBarsToAccum [green]`
2. 🔴 `test(frontend): FuturesChart 分時改吃 core 語彙(last-dot / minuteToX / 量測 box) [red]`
   → 🔴 `fix(frontend): 期貨分時圖換 IntradayChartCore(mode="futures") [green]`
3. 🔴 `test(frontend): 期貨 K 線檔位 1–10/15/30/60 [red]` → 🔴 `fix(frontend): FUT_CHART_MODES 擴為 1–10/15/30/60 [green]`
4. (若有)🔵 review fix 之純重構

可逆 = revert 三個 [green](futures 態新能力住在 🟢 那顆;stock / index 由 SC-9 鎖)。

## 7. Out of scope

- 期貨 CDP / MA 疊線(需以期貨日 K 前端算 CDP/MA5/20,涉「日盤 vs 近全時段昨日 H/L/C」口徑拍板)→ next-time。
- 期貨分時成交點(需近全軸的日期界:夜盤成交屬錨定日;`fillPoints` 現為今日 ∨ 昨日活單)→ next-time 既有條補註。
- K 線態量測高(`CandleChart height`)、CandleChart 任何改動;`FuturesPage` 版面。
- 期貨 hover 十字的五檔 / 委託連動;OI 線語意。
- 個股期(stkfut)分時的任何行為。

## 8. Backward compat / migration

無對外 API / 資料格式變更。localStorage:`FUT_CHART_MODE_KEY` 值域擴大(舊值皆合法);`CHART_TOGGLES_KEY` 多一讀寫者(schema 不動)。
無 migration;可逆見 §6。

## 9. Known risks

- KR-1 對稱域 ±1% 地板:期指平靜日(振幅 < 1%,~230 點)線的視覺振幅變小(同 index R4 KR);user 過目點。
- KR-2 每 WS tick re-render → adapter 折 1140 格 + core 幾何(memo 依 accum identity;live 同分鐘同價命中 memo,價變才重折);
  與 index R4 KR-2 同量級,可接受;verification 記 hover 掉幀目視。
- KR-3 全站共用 toggles:期貨頁 CDP/MA 反灰但 toggles.cdp 仍為 true(不影響畫面;`aria-pressed = toggles && available` 已處理)。
- KR-5 近全軸 hover 命中率:1139 索引壓進 724 單位繪圖區(渲染 ~1200px 時 ~1 索引/px),無 bar 分鐘反演回 null → 十字與資料欄退化;verification 記真環境夜盤 hover 目視;改善候選 = futures 態「±N 索引最近 snap」(動白名單,留 next-time)。
- KR-4 副圖 1140 根 1 單位寬 rect 每 tick 重建(EnergySub memo 依 bars identity → 每次 accum 重折都重建):實測 hover 是否掉幀,掉幀則
  candidate = 副圖改 path 單元素(另案)。
