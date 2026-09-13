# F3 — 前端:圖表元件與重繪行為(架構掃描報告)

掃描對象:`C:/side-project/copycat/frontend/src` 的全部圖表元件 + 其幾何 lib + 相關 hook。
方法:**整檔讀完**指定的 17 個檔案 + 其依賴的 lib(`stock-intraday-svg.ts` 921 / `candle.ts` /
`volume-profile.ts` / `futures-accum-adapter.ts` / `stock-accum.ts` / `live-last-bar.ts` /
`index-overlay-lines.ts` / `river-chart-svg` 呼叫端 / `tick-stream.ts` / `chart-frame.ts`),
再用 **esbuild bundle 真實模組 + node 微基準**量出每個熱函式的 ms/op(見 §6,指令可重跑)。

> 一句話結論:這個前端的**演算法層已經被優化過很多輪**(memo 邊界、模組層空常數、WeakMap 快取、
> 去重 windowedEntries、adapter 折法),真正的剩餘瓶頸**不在算式**,而在
> **(a) 每 0.1 s 把「整條序列」當成新資料重折重繪**、
> **(b) hover / 同步十字線把 mousemove 級事件打進 React 的 state 與 50 張卡的 props**、
> **(c) SVG 節點數量級(單張期貨分時圖 ~2,500 個節點、圖牆 ~20,000 個節點)全部走 React reconciler**。
> 換演算法工具(numpy 之於後端的等價物)在這裡收益很小;**把繪圖與游標脫離 React、把節點數降一到兩個
> 數量級**才是量級改變。

---

## 1. 架構地圖與資料流

### 1.1 元件樹(只畫圖表相關)

```
App.tsx  ← 五條串流全掛在這裡(useStockStream / useIndexStream / useFuturesStream /
          useBreadth / useCapitalStream)→ App 的 re-render 頻率 = 五條流的「聯集」
 ├─ StockPage
 │   ├─ StockChart(模式切換容器:江波圖 / 1–10 分K / 日K)
 │   │   ├─ StockIntradayChart → IntradayChartCore(variant="page", mode="stock")
 │   │   │     ├─ <ChartStatic>   memo  ← 線 / 填色 / 刻度 / VP / 疊線 / 極值 / 成交點
 │   │   │     ├─ <XAxisLabels>   非 memo(刻意:要看 hover 位置決定遮蔽)
 │   │   │     ├─ hover 十字線層(直接在 svg 內,非 memo)
 │   │   │     └─ <EnergySub>     memo  ← 成交量副圖(**每分鐘一個 <rect>**)
 │   │   └─ CandleChart(K 線)
 │   │         ├─ <ChartStatic>   memo  ← 蠟燭 / 量柱 / MA / BB / hline
 │   │         ├─ <XAxisLabels>   非 memo
 │   │         └─ hover 十字線層
 │   └─ GroupGridView(圖牆,上限 150 檔、常態 ~50)
 │         └─ <GroupCard> memo × N
 │               └─ CardIntradayChart → IntradayChartCore(variant="card")   ← 與單檔頁同一份碼
 ├─ FuturesPage → FuturesChart
 │     ├─ IntradayChartCore(mode="futures", 近全軸 1365 格)
 │     └─ CandleChart
 ├─ IndexPage → MarketPane → MarketChart
 │     ├─ IntradayChartCore(mode="index")
 │     ├─ CandleChart
 │     └─ AdvanceDeclineChart(騰落線,自繪 svg,無 memo)
 ├─ CorrPage → RiverPanel → { RiverCards(memo per leg) | RiverOverlay(無 memo) }
 └─ PnlChart(TXO 到期損益曲線,無 memo)
```

**只有 6 個 `memo` 元件**(`grep -rn "= memo("`):`StockIntradayChart.ChartStatic`、
`StockIntradayChart.EnergySub`、`CandleChart.ChartStatic`、`GroupGridView.GroupCard`、
`RiverCards.RiverCard`、`RightRail`。`IntradayChartCore` 本身**不是 memo**。

### 1.2 資料流(誰在什麼頻率讓誰重繪)

| 來源 | 節奏 | 打到哪 |
|---|---|---|
| `/ws/stock` `ticks` 打包 | **每 0.1 s 一則**(後端 `tick_flush_secs`;CLAUDE.md §4) | `useStockStream` → `applyTick` → 新 `StockAccum` → App → StockPage → StockChart → **整張分時圖 / K 線重算**;同一則同時經 `tick-stream` 匯流排 → `useGroupLiveAccums` → **收到成交的卡**換 accum |
| `/ws/stock` `watchlist_quote` | **每 1 s** | App state → StockPage → GroupGridView 整層 re-render(GroupCard memo 擋掉沒變的卡) |
| `/ws/futures` | **coalesce 後 ≤10/s** | `useFuturesStream` → App re-render(**即使人在個股頁**)→ FuturesChart 全鏈重折 |
| `/ws/index` | ~1/s | `useIndexStream` → App → `indexOverlay` 物件 → 疊線開著時打到圖牆每一張卡 |
| `/ws/river` delta | 1/s | `useRiver` → RiverPanel → RiverCards / RiverOverlay |
| TQ 輪詢 `group-state` | 60 s | `useGroupSnapshots` → `seeded` 整份換 → **整牆 50 卡同幀重播種 + 重算幾何** |
| 使用者 mousemove | **60–144/s** | hover setState → IntradayChartCore / CandleChart / RiverOverlay / PnlChart 整個 re-render;圖牆另加「同步十字線」→ **整牆 50 卡** |
| 使用者滾輪 / 拖曳(K 線) | 每步一次,拖曳時 = mousemove 頻率 | `useCandleViewport` setViewport → CandleChart 主 useMemo 失效 → **MA/BB 全序列重算** |

### 1.3 幾何層的形狀

- **分時圖**:`StockAccum.minutes: Map<分鐘鍵, MinuteAgg>` →
  `buildIntradayGeometry(minutes, meta, high, low)` 回一整包(priceLine / vwapLine / yTicks /
  areaPolygon / highMark / lowMark / **energyBars** / toY / priceAtY / minuteOf)。
  副圖另走 `buildEnergyBars`,VP 走 `buildVpBars`,疊線走 `overlayLines`,指數疊線走
  `buildIndexOverlayLines`(WeakMap 快取排序結果,已優化)。
- **K 線**:`Bar[]` → `movingAverage` / `bollinger` 全序列 → `slice(viewport)` →
  `buildCandleGeometry(shown)`。
- **期貨分時**:`Bar[](1K)` → `futuresBarsToAccum`(折成 `StockAccum`,key = 近全軸索引 0–1365)
  → 走與個股完全相同的 `buildIntradayGeometry`。
- 三條路的共同點:**輸入是不可變物件,任何一格變動 = 整份重折**。這在 0.1 s 節奏下就是
  「每秒 10 次全序列重算」。

---

## 2. 熱路徑逐條(含實測 ms/op)

微基準環境:Node 24.13.0,Windows 11,esbuild bundle 真實模組(非重寫近似)。
**這些數字只含 JS 計算,不含 React reconcile 與瀏覽器繪製**,後兩者在真瀏覽器通常是 JS 的 2–5 倍。

```
--- 分時圖幾何(單張圖 / 單次 re-render)---
buildIntradayGeometry 271 分鐘(現貨窗)        0.1388 ms/op
buildIntradayGeometry 1140 格(期貨近全軸)      0.6025 ms/op
buildEnergyBars 271                          0.0283 ms/op
buildEnergyBars 1140                         0.0975 ms/op
buildVpBars 400 檔位                          0.0166 ms/op
sideSummary 271                              0.0028 ms/op
pts(priceLine 271)                           0.0506 ms/op
pts(priceLine 1140)                          0.2431 ms/op
windowedEntries 271(copy+filter+sort)        0.0229 ms/op
windowedEntries 1140                         0.1099 ms/op
energyFrom 271(geometry 內那份,零讀者)        0.0107 ms/op
energyFrom 1140(geometry 內那份,零讀者)       0.0697 ms/op

--- 逐筆 accum ---
applyTick(minutes 271 + vp 400 + tape 200)   0.0306 ms/op

--- K 線 ---
movingAverage(5900, 5)                       0.0845 ms/op
movingAverage(5900, 20)                      0.0886 ms/op
bollinger(5900, 20)                          0.4314 ms/op
aggregateBars(5900, n=5)                     2.1506 ms/op   ← 字串時戳解析是主因
aggregateBars(5900, n=1)                     0.0057 ms/op
buildCandleGeometry(240 根 + BB)              0.0221 ms/op
buildCandleGeometry(700 根 = MAX_VISIBLE)     0.0594 ms/op
CandleChart 主 useMemo 全套(MA×2+BB 全序列)    0.5465 ms/op

--- 即時末根路徑 ---
mergeLiveMinuteBars(5900 正式 + 240 分鐘)      0.0113 ms/op
merge + aggregateBars(n=5) 一整趟             1.3328 ms/op
merge + aggregateBars(n=1) 一整趟             0.0113 ms/op

--- 期貨 adapter ---
futuresBarsToAccum(1365 bars)                0.8820 ms/op
```

### HP-1 期貨 tab 分時圖:每 0.1 s 全鏈重折(**最重的單一路徑**)
`FuturesChart` 每則 WS(≤10/s)re-render → `liveP = state.p` 改變 →
`accum` useMemo 失效 → `futuresBarsToAccum(1365)` **0.88 ms** →
`accum.minutes` 新 identity → core 的 `g` useMemo 失效 → `buildIntradayGeometry(1140)` **0.60 ms** →
`subEnergy` 失效 **0.10 ms** → `vpBars` 失效 → `ChartStatic` memo 被打穿 →
`pts(priceLine)` **×2**(`hasRef` 分支呼叫兩次)**0.49 ms** + `pts(vwapLine)` →
**JS 合計 ≈ 2.1 ms/次 × 10 次/s ≈ 21 ms/s**,外加 **~2,500 個 SVG 節點**(1140 個 energy `<rect>`
+ 1140 點 polyline × 3 條 + vp + 刻度 + 標籤)每次全部走 React diff。

### HP-2 個股頁分 K 模式 + 即時末根:每 0.1 s 重聚合全序列
`StockChart.bars` useMemo 的 dep `liveMinutes = accum.minutes` 每則 ticks 打包換 identity →
`mergeLiveMinuteBars`(0.011 ms,便宜)→ **`aggregateBars(5900, n≥2)` 1.33 ms** →
新 `bars` array → `CandleChart` 主 useMemo 失效 → **MA×2 + BB 全序列 0.55 ms** →
`buildCandleGeometry` → `ChartStatic` 重建 **240 根蠟燭 × 3 節點 ≈ 720 個 SVG 節點**。
**JS 合計 ≈ 1.9 ms × 10/s ≈ 19 ms/s**。1 分 K(n=1)只有 0.011 ms —— 成本幾乎全在
`aggregateBars` 的 `splitStamp` 字串解析 + 每根一個 template-literal key。

### HP-3 群組圖牆逐筆:每 0.1 s × 有成交的卡數
每則打包 → `useGroupLiveAccums` 對每個有成交的 code 跑 `applyTick`(0.031 ms,內含
Map 271 淺拷 + Map(vp) 400 淺拷 + tape 200 spread+slice)→ 該卡換 identity → `GroupCard` memo
放行 → `IntradayChartCore` 全跑:`buildIntradayGeometry(271)` 0.139 + `buildEnergyBars` 0.028 +
`buildVpBars` 0.017 + `pts×2` 0.10 ≈ **0.31 ms/卡**,外加 **~500 個 SVG 節點**/卡。
開盤時 50 檔幾乎每則打包都有一半以上在動 → **25 卡 × 0.31 ≈ 7.8 ms JS + ~12,000 節點 diff,每 0.1 s**。
既有註記(`EnergySub` doc,N047)在 jsdom 量到滿窗一輪 ~15 ms,與這裡對得上。

### HP-4 hover / 同步十字線:mousemove 級(60–144/s)
- 單檔頁:`onMove` → `getBoundingClientRect()`(**強制 layout**)→ `setHover` →
  `IntradayChartCore` 整個 body 重跑(8 個 useMemo 逐一比 deps)+ `XAxisLabels` 重建 +
  hover 十字線層(~8 個節點)重建 + `ChartReadout` 重建。`ChartStatic` / `EnergySub` 的 memo 擋住重頭戲。
- **圖牆(預設 `syncHover: true`)**:被 hover 的那張卡每跨一分鐘就 `onHoverMinute(min)` →
  `GroupGridView.setSyncMin` → **整牆 50 張卡的 `syncHoverMin` prop 全部換值 → 50 個 GroupCard memo
  全部失效 → 50 次 core 重跑 + 50 份十字線 DOM 變更**。
  而卡片寬 ~250px、繪圖區 ~174px、現貨窗 271 分鐘 → **1 分鐘 ≈ 0.64 px**:滑鼠移動 1px 就跨分鐘,
  「只在分鐘變化時回報」這道節流**在卡片尺寸下幾乎不生效**。
- K 線拖曳:`window` 的 mousemove → `setViewport` → 主 useMemo 失效 → **MA/BB 全序列重算 0.55 ms
  每一步**(拖曳時 60–144 步/秒 → 33–79 ms/s,且是連續的長任務)。

### HP-5 圖牆 60 s 重播種尖峰
`useGroupSnapshots` 60 s 回一份新快照 → `seeded` 整份重建 → 50 張卡 accum 全換 →
**同一幀內 50 × 0.31 ms ≈ 15 ms JS + ~25,000 節點 diff**,是可觀測的掉幀點(一次性長任務)。

### HP-6 江波圖重疊模式 hover
`RiverOverlay.readout` 每 mousemove 對每腿做 `g.lines.find(...)` + `line.pts.find(p => p.offset === cursor)`
= **O(腿數 × 點數) = 11 × 840 ≈ 9,200 次線性比較**,再 × 60–144 mousemove/s。

---

## 3. Findings(逐條含證據)

編號 `F3-xx`;嚴重度以「在熱路徑上 × 量級」排序。

---

### F3-01 [critical] 圖牆同步十字線把 mousemove 放大成 50 張卡的 re-render
**位置**:`components/stock/GroupGridView.tsx:310, 464-465`;`components/stock/StockIntradayChart.tsx:1041-1055, 1327-1335`

```tsx
// GroupGridView.tsx:310
const [syncMin, setSyncMin] = useState<number | null>(null);
...
// GroupGridView.tsx:464-465  ← 同一個值傳給每一張卡
syncHoverMin={toggles.syncHover ? syncMin : null}
onHoverMinute={toggles.syncHover ? setSyncMin : NOOP_HOVER}
```
```tsx
// StockIntradayChart.tsx:1327-1335
function onMove(e: React.MouseEvent<SVGSVGElement>): void {
  const rect = e.currentTarget.getBoundingClientRect();
  const { x, y } = toSvgPoint(e, rect, { width: w, height: mainH });
  const min = g.minuteOf(x);
  const ry = Math.round(y);
  setHover((p) => (p !== null && p.min === min && p.y === ry ? p : { min, y: ry }));
  emitHoverMinute(min);   // ← 只在分鐘變化時外報
}
```
`useChartToggles.DEFAULTS` 的 `syncHover: true`(`hooks/useChartToggles.ts:60`)。

**影響**:`emitHoverMinute` 的節流條件是「分鐘變了才報」,但卡片繪圖區只有 ~174px 對應 271 分鐘
(`plotWidth = width − Y_AXIS_W(36) − R_AXIS_W(40)`),**1 分鐘 ≈ 0.64 px** → 幾乎每個 mousemove
都跨分鐘。於是 `setSyncMin` 以 60–144 Hz 觸發,`syncHoverMin` 是**傳給每一張卡的同一個 prop**,
50 張 `GroupCard` 的 memo 一次全破。每次:50 × (core body 重跑 + hover 層 DOM 變更)。
粗估 1–2.5 ms/次 × 120 Hz = **120–300 ms/s 主執行緒**,是使用者「在圖牆上移動滑鼠時很鈍」的直接來源。
`ChartStatic` 的 memo 在這條路徑上**沒有幫助**(它擋的是重繪,擋不住 50 次元件函式呼叫與 50 份十字線 DOM)。

**修法**:
1. 把 `syncMin` 從 GroupGridView 的 `useState` 改成**模組層 external store**(沿用本專案已有的
   `lib/tick-stream.ts` EventTarget 模式,零新相依),卡片內以 `useSyncExternalStore` 訂閱 →
   只有「需要畫十字線」的卡重繪,而不是整牆。
2. 事件端加 **rAF 節流**:`onMove` 只記 ref,`requestAnimationFrame` 內才 commit(把 144 Hz 收成 ≤60 Hz)。
3. 更進一步:十字線改成**不經 React** —— core 內用 `useRef` 拿到一個常駐的 `<g>`,直接設
   `line.setAttribute("x1", …)`。十字線是純視覺游標,沒有任何跨檔契約。

**風險**:`StockIntradayChart.synchover.test.tsx` 與 `GroupGridView.memo.test.tsx` 會需要改判準
(memo 計次測試正是釘這件事的)。不觸及任何 CLAUDE.md §4 契約。**Effort: M**

---

### F3-02 [critical] 每次 mousemove 都呼叫 `getBoundingClientRect()`(強制同步 layout)
**位置**:`StockIntradayChart.tsx:1328`、`hooks/useCandleHover.ts:25`、`components/corr/RiverOverlay.tsx:88`、`components/PnlChart.tsx:26`、`hooks/useCandleViewport.ts:57, 77`

```ts
// useCandleHover.ts:24-26
function onMove(e: React.MouseEvent<SVGSVGElement>): void {
  const rect = e.currentTarget.getBoundingClientRect();   // ← forced reflow
  const { x, y } = toSvgPoint(e, rect, { width: dimW, height: dimH });
```

**影響**:`getBoundingClientRect()` 會強制瀏覽器 flush pending layout。在這個 app 上一幀
**永遠有 pending DOM 變更**(報價 10 Hz、圖牆 50 張卡),所以每個 mousemove 都付一次完整 layout。
圖牆有 ~20,000 個 SVG 節點時單次 layout 可達數 ms。這是最典型、最容易被忽略的卡頓源,
而且**在任何測試裡都看不出來**(jsdom 的 `getBoundingClientRect` 回傳全 0,零成本)。

**修法**:`mouseenter` 時量一次 rect 存 ref,`mousemove` 讀 ref;以 `ResizeObserver`(元件已有)
與 `scroll` / `resize` 讓它失效。或直接用 `e.nativeEvent.offsetX / offsetY`(相對 target 的
內容座標,SVG 上可用),完全免 rect。

**風險**:jsdom 測試對 rect 的假設要跟著改(目前測試靠 `toSvgPoint` 的 0 rect 退化行為)。
無跨檔契約。**Effort: S**

---

### F3-03 [high] `EnergySub` 用「每分鐘一個 `<rect>`」畫量柱:1140 / 271 個節點每 0.1 s 重建
**位置**:`StockIntradayChart.tsx:818-895`(尤其 882-892)

```tsx
{bars.map((b) => (
  <rect key={`e-${b.x}`} data-testid="energy-bar"
    x={b.x - bw / 2} y={h - b.h} width={bw} height={b.h} className="fill-ink-muted" />
))}
```
元件自己的 doc 已經寫了(N047,2026-08-24):
> `memo` 擋得住 hover,但擋不住報價 —— 每則 tick 讓 `accum.minutes` 換 identity → `subEnergy` 重算 →
> 本層 1140 個 rect 全部重建。jsdom 量到滿窗一輪 ~15 ms … **真正安全的是 EnergySub 改單一 `<path>`
> (節點數 1140 → 1),留 next-time。**

**影響**:期貨分時 1140 個、個股 271 個、圖牆 50 卡 × 271 ≈ 13,550 個 `<rect>` 常駐 DOM。
每次 accum 變動,對應那張圖的整層 rect 走 React diff + DOM 屬性寫入。
這是「節點數量級」問題,不是算式問題 —— 換再快的計算庫都救不了。

**修法**:量柱改成**單一 `<path>`**,`d` 由 bars 組成(每根 `M x,y h w v h z`,或用
`stroke-width = bw` 的直線串)。節點 1140 → 1,diff 成本 → 一個字串比較。
同法可套用到 `vpBars`(水平長條,`volume-profile.ts` 輸出最多數百根)。

**風險**:`data-testid="energy-bar"` 的計數型測試(`StockIntradayChart.test.tsx`、
`GroupGridView.geometry.test.tsx`)會全紅,需改成量 path 的 `d` 或改判準。
**另一個既有缺陷順帶修掉**:現在的 `key={`e-${b.x}`}` 用**浮點 x** 當 key —— 容器寬一變(resize /
圖牆換檔數)所有 key 全換 → 整層重掛;退化寬度下兩根 x 相同還會 key 衝突。`EnergyBar` 型別
(`stock-intraday-svg.ts:97-102`)只有 `{x, h}`,**沒有 minute 欄位**,所以連「用穩定 key」都做不到。
**Effort: M**

---

### F3-04 [high] `pts(g.priceLine)` 在同一次 render 內被呼叫兩次(整條線字串化兩遍)
**位置**:`StockIntradayChart.tsx:527-546(`pts` 於 530 / 537 / 545)`

```tsx
{g.hasRef ? (
  <>
    <polyline points={pts(g.priceLine)} ... clipPath={`url(#${clipAbove})`} />
    <polyline points={pts(g.priceLine)} ... clipPath={`url(#${clipBelow})`} />
  </>
) : (
  <polyline points={pts(g.priceLine)} ... />
)}
```
`pts` 本身(`lib/svg-points.ts:2-4`)是 `line.map(p => \`${p.x.toFixed(1)},${p.y.toFixed(1)}\`).join(" ")`
—— 每點兩次 `toFixed`(慢路徑)+ 一次字串配置。

**影響**:實測 `pts(1140)` = **0.243 ms**,呼叫兩次 = 0.49 ms;`pts(271)` = 0.051 ms × 2。
在期貨 10 Hz 路徑上這一條就佔了 JS 的 **~23%**,而兩次算出來的**是完全相同的字串**。
(`areaPolygon` 已經在幾何層預算好了,正是同一個道理沒做完。)

**修法**:`const priceD = pts(g.priceLine)` 提到分支之外;更進一步把 `priceLine` 的字串化下沉進
`buildIntradayGeometry`(與 `areaPolygon` 並列),幾何 memo 命中時連字串都不用重建。
`vwapLine` 同理。

**風險**:零(純內部)。**Effort: S**

---

### F3-05 [high] `CandleChart` 把「全序列 MA/BB」算在 viewport 的 deps 裡 → 每個拖曳步重算 5900 根
**位置**:`components/stock/CandleChart.tsx:475-497`

```tsx
const { shown, g, ma5, ma20, bbUpper, bbLower } = useMemo(() => {
  const start = viewport.start;
  const shownBars = bars.slice(start, start + viewport.count);
  const m5 = movingAverage(bars, 5).slice(start, start + viewport.count);     // 全序列
  const m20 = movingAverage(bars, 20).slice(start, start + viewport.count);   // 全序列
  const bb = showBb ? bollinger(bars, 20).slice(start, start + viewport.count) : [];  // 全序列
  ...
}, [bars, viewport, showBb, dimW, dimH]);   // ← viewport 在 deps 內
```
`bollinger`(`lib/bollinger.ts:19-43`)是 **O(n × 20) 的雙重迴圈**(每根重新掃 20 根算 mean 再掃 20 根算 sd),
不是滑動窗:5900 根 = **0.43 ms**。

**影響**:`useCandleViewport.onDragStart` 的 `move` handler 掛在 `window` 的 mousemove
(`hooks/useCandleViewport.ts:86-92`),拖曳中每個事件都 `setViewport` → 這個 memo 失效 →
**MA×2 + BB 全序列重算 0.55 ms/步**;滾輪縮放同理。60–144 Hz 下 = 33–79 ms/s 的連續長任務,
正是「拖 K 線會頓」的成因。而 `viewport` 只該影響**切片**,不該影響全序列指標。

**修法**:拆成兩層 memo ——
```tsx
const full = useMemo(() => ({
  ma5: movingAverage(bars, 5), ma20: movingAverage(bars, 20),
  bb: showBb ? bollinger(bars, 20) : [],
}), [bars, showBb]);                                  // 只隨資料變
const { shown, g, ma5, ma20, bbUpper, bbLower } = useMemo(() => { /* 只做 slice + geometry */ },
  [full, viewport, dimW, dimH]);
```
另把 `bollinger` 改成**單趟滑動窗**(維持 `sum` 與 `sumSq`,O(n)):0.43 ms → ~0.05 ms。
⚠ 滑動窗的浮點累積誤差與現行「每窗重算」不逐位元相同,而 BB 的 `Math.round(mean ± k·sd)`
會放大這個差異 → **要先跑 `lib/candle.test.ts` / `bollinger` 相關測試確認**,若釘了精確值就改用
「Welford / 分塊重置」或乾脆只做 memo 拆層(收益已有 90%)。

**風險**:`CandleChart.test.tsx`(714 行)有大量幾何斷言;拆 memo 是純結構改動,行為零變化。
不觸及 CLAUDE.md 的 overlay parity fixture(那是 `futures-overlay.ts` / `server/overlay.py`,不同檔)。
**Effort: S(拆 memo)/ M(含 bollinger 改滑動窗)**

---

### F3-06 [high] 分 K 即時末根:每 0.1 s 對 5900 根跑一次 `aggregateBars`(字串時戳解析)
**位置**:`components/stock/StockChart.tsx:196-203`;`lib/candle.ts:65-110`

```tsx
const bars = useMemo(() => {
  const raw = data?.bars ?? [];
  if (liveMinutes !== null) {
    return aggregateBars(mergeLiveMinuteBars(raw, liveMinutes, liveToday, nowMinute), minutesOf(mode));
  }
  ...
}, [data, mode, liveMinutes, liveDay, dayOpen, liveToday, nowMinute]);
//   ↑ liveMinutes = accum.minutes,每則 0.1 s ticks 打包換 identity
```
`aggregateBars` 內每根 bar 做:`splitStamp`(indexOf + 兩次 slice + 兩次 `Number`)、
`` const key = `${bucketDate} ${bucketEnd}` ``(每根一個新字串)、`stampOf`(padStart ×2)。
實測 **5900 根 n=5 → 2.15 ms**(n=1 只有 0.006 ms,因為走 `[...bars]` 捷徑)。

**影響**:`merge + aggregate` 一整趟 **1.33 ms × 10/s = 13 ms/s**,再串到 F3-05 的
CandleChart 主 memo(0.55 ms)→ **分 K 模式常開時,光是圖表這一路就吃掉 ~19 ms/s 的 JS**,
且每 0.1 s 產生一個全新的 5900 元素陣列(GC 壓力)。
元件註解已經預估了「成本 = 一次 aggregateBars ≈ 5,900 根」,但**沒有把下游 CandleChart 的
全序列 MA/BB 重算算進去**。

**修法**(不動任何契約,分鐘鍵語意全保留):
1. **正式段聚合結果快取**:`data.bars` 只在 60 s 輪詢時變,把
   `aggregateBars(raw, n)` 拆成 `useMemo([data, mode])`;即時末根只影響**最後一個桶**,
   改成「聚合好的正式段 + 最後一桶就地重算」——O(補的根數) 而非 O(5900)。
2. `splitStamp` 的結果可在 `Bar` 上快取(WeakMap<Bar, {date, minute}>,沿用
   `index-overlay-lines.ts::SORTED_ROWS` 已在用的模式),或請後端多送一個 `minute` 數值欄
   (⚠ 那是跨檔契約,要改兩邊,不建議這一輪做)。
3. `key` 用 `bucketDate` 的字串 + `bucketEnd` 數字組合比較,避免每根配置 template literal。

**風險**:`lib/live-last-bar.ts` 的「accum 起點分 +1、上限 13:30」是 CLAUDE.md §4 白紙黑字的契約
(`live-last-bar.test.ts` 案 1/2/9 釘住),**只改聚合的分工不改分鐘鍵**即可。
`aggregateBars` 的跨午夜正規化(SC-2)與 uv/dv「缺欄 vs 0」語意必須逐字保留。**Effort: M**

---

### F3-07 [high] 期貨分時:`futuresBarsToAccum` 每次價變重折 1365 根(且與幾何重複排序)
**位置**:`components/futures/FuturesChart.tsx:316-327`;`lib/futures-accum-adapter.ts:52-172`

```tsx
const accum = useMemo(() => futuresBarsToAccum({
  bars: slice, live: ..., ref: state?.ref ?? null, ... }),
  [slice, liveIndex, liveP, state?.ref, state?.name, product]);
//                     ↑ liveP = WS 現價,每則推播都可能變
```
adapter 內:建 `rows` Map(1365)、建 `vp` Map、Σ/高低迴圈、插橋掃描、
最後 `[...rows.entries()].sort(...)` **再建一個 Map**。實測 **0.88 ms**。
接著 `buildIntradayGeometry` 的 `windowedEntries` **又做一次 `[...entries].filter().sort()`**
(1140 格 = 0.11 ms)—— 同一份資料在一次 render 內排序兩遍。

**影響**:期貨 tab 常開時 ≈ 10 Hz × 0.88 ms = 8.8 ms/s,單只為了「最後一格的收盤價換了一個數字」。
adapter 的 doc 說「價變才重折 1140 格」—— 是的,而盤中價幾乎每則都在變。

**修法**:
- adapter 改成**兩段**:`barsToRows(bars)` 以 `slice` 為 dep(60 s 才變,附帶排序結果);
  `applyLive(rows, live)` 只動一格,回一個「共用 base + 覆蓋層」的輕量結構。
- adapter 已經排好序了 → 讓它輸出的 `minutes` 帶一個「已排序且已在窗內」的旗標 / 或直接輸出
  `entries` 陣列,讓 `buildIntradayGeometry` 收 `entries` 而不是 Map(見 F3-08)。

**風險**:`futuresBarsToAccum` 的插橋、Σ/高低「在插橋之前算完」(pr-133 F-11)、live 佔位格
`v = 0` 三條語意必須逐字保留 —— 它們各自對應一個真實 bug 的修法。
`FuturesChart.test.tsx`(1128 行)會是主要守門。**Effort: M**

---

### F3-08 [medium] `buildIntradayGeometry` 內的 `energyFrom` 是死碼(零讀者),且 `windowedEntries` 一次 render 做兩遍
**位置**:`lib/stock-intraday-svg.ts:418, 516-517`;`StockIntradayChart.tsx:1094-1097`

```ts
// stock-intraday-svg.ts:418  ← 算完塞進回傳物件
const { bars: energyBars, maxTotal } = energyFrom(entries, size, xw);
...
return { ..., energyBars, maxTotal, ... };
```
```bash
$ grep -rn "energyBars" --include=*.ts --include=*.tsx . | grep -v "\.test\."
./lib/stock-intraday-svg.ts:136   # interface 宣告
./lib/stock-intraday-svg.ts:418   # 計算
./lib/stock-intraday-svg.ts:516   # 回傳
# 零個消費端
```
元件端另外走 `buildEnergyBars`(`StockIntradayChart.tsx:1094`,註解已寫明「原本整份跑一次
`buildIntradayGeometry`(L-1)」)—— 當初把副圖抽出去時**忘了把幾何裡那一份拿掉**。

**影響**:實測死碼成本 271 格 **0.011 ms**、1140 格 **0.070 ms**(佔幾何總成本 8% / 12%);
另加 `buildEnergyBars` 自己那次 `windowedEntries`(0.023 / 0.110 ms)。
在圖牆(50 卡 × 10 Hz)= 白燒 ~5.5 ms/s;期貨 tab = 白燒 ~1.8 ms/s。

**修法**:
1. 從 `IntradayGeometry` 拿掉 `energyBars` / `maxTotal` 兩個欄位與第 418 行的呼叫(TS 會指出所有讀者 = 0)。
2. 把 `windowedEntries` 的結果做成可共用的輸入:`buildIntradayGeometry` 與 `buildEnergyBars` 都改收
   `entries`,由元件端一個 `useMemo([accum.minutes, xw])` 算一次餵兩邊。

**風險**:`stock-intraday-svg.test.ts`(1598 行)若有斷言 `g.energyBars` 會紅 —— 那正是要確認的。
**Effort: S**

---

### F3-09 [medium] `IntradayChartCore` 不是 `memo`,期貨 / 大盤頁每則 WS 都完整重跑它
**位置**:`StockIntradayChart.tsx:978`(`export function IntradayChartCore(...)`)、
呼叫端 `FuturesChart.tsx:392`、`MarketChart.tsx:94`、`CardIntradayChart.tsx:56`

**影響**:圖牆那條路有 `GroupCard` 的 memo 在上面擋著,但**期貨頁與台股綜合頁沒有任何 memo 邊界** ——
`FuturesChart` / `MarketChart` 因 WS 重繪時,core 的 8 個 `useMemo` 全部要逐一比 deps、
`toggleDefs` 陣列每次重建(內含 5–8 個新物件)、`allFields` / `fields` 每次重建、
`XAxisLabels` 重建。單次幾十 µs,10 Hz 下不是主因,但它讓 F3-07 的 memo 失效直接一路貫穿到底。

**修法**:`export const IntradayChartCore = memo(function IntradayChartCore(...))`。
前置條件是 caller 的 props identity 要穩(`hlines` / `fills` / `xWindow` / `hourTicks` /
`timeText` 目前**都已經**是 useMemo 或模組層常數 —— 元件的 prop doc 逐條寫明了這個要求,
所以這層 memo 幾乎是免費的)。
同時把 `toggleDefs` 收進 `useMemo`。

**風險**:低。若哪個 caller 漏了 identity 穩定性,症狀是 memo 失效(= 現狀),不是錯畫面。
**Effort: S**

---

### F3-10 [medium] `useChartToggles.getSnapshot` 每次 render 同步讀 `localStorage`
**位置**:`hooks/useChartToggles.ts:110-118, 136-140`

```ts
function getSnapshot(): ChartToggles {
  const raw = readLocal(CHART_TOGGLES_KEY);       // ← 每次呼叫都打 localStorage
  if (cachedRaw === undefined || raw !== cachedRaw) { cached = load(); ... }
  return cached;
}
export function useChartToggles() {
  const toggles = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
```
**影響**:`useSyncExternalStore` 每次 render **至少呼叫一次** `getSnapshot`(並發模式下為了 tearing 檢查
可能更多)。`localStorage.getItem` 是同步的 main-thread 儲存 I/O(典型 1–10 µs,但在 Windows +
大 origin 資料時可到數十 µs,且不可被 JIT 消除)。呼叫端有 `App`、`StockChart`、`GroupGridView`、
`FuturesChart`、`MarketPane` —— 每則 0.1 s 推播就是 5+ 次。

**修法**:真相源仍留 localStorage,但**只在寫入時 / `storage` 事件時更新快取**,`getSnapshot` 直接回
模組層變數。現行寫法是為了「兩個分頁各自 set 時不互相覆蓋」—— 那件事已經由 `setToggle` 內的
`{...load(), [key]: value}` 保證了,`getSnapshot` 不必再讀一次。

**風險**:`useChartToggles.test.ts` 有「外部清空存檔 → 重載」的案子會需要改成監聽 `storage` 事件。
**Effort: S**

---

### F3-11 [medium] `CandleChart` 的視窗高低每次 render(含每次 mousemove)重算,還用 spread 呼叫 `Math.max`
**位置**:`components/stock/CandleChart.tsx:522-538`

```tsx
const windowHigh = shown.length > 0 ? Math.max(...shown.map((b) => b.h)) : 0;
const windowLow  = shown.length > 0 ? Math.min(...shown.map((b) => b.l)) : 0;
...
const highMark = useMemo<WindowMark | null>(() => {
  const cx = g.candles[shown.findIndex((b) => b.h === windowHigh)]?.cx;   // 再掃一遍
  ...
}, [shown, g, windowHigh, highText]);
```
**影響**:`shown` 最多 700 根(`MAX_VISIBLE`)。每次 mousemove 都:2 次 `map` 配置新陣列(1400 個元素)
+ 2 次 700 引數的 spread 呼叫。`Math.max(...arr)` 對大陣列是已知的 footgun(**超過 ~65k 會直接
RangeError**;700 只是慢,但 spread 本身要把陣列展成呼叫堆疊上的引數)。
兩個 `useMemo` 的 dep 含 `windowHigh` / `windowLow`,而那兩個值每 render 都重算 —— 值相同所以 memo
仍命中,但前置的 `map` + spread 成本無法避免。

**修法**:把 `windowHigh` / `windowLow` / `highText` / `lowText` / `highMark` / `lowMark` 收進
**同一個** `useMemo([shown, g])`,內部用單趟 for 迴圈同時求 max/min **與其索引**(現在還多跑了兩次
`findIndex`)。

**風險**:「取最早出現的那一根」的語意(`findIndex` 的第一個命中)必須保留 —— 單趟迴圈用
嚴格大於 / 嚴格小於即可。**Effort: S**

---

### F3-12 [medium] `RiverOverlay` 的讀值列是 mousemove 上的 O(腿 × 點) 線性搜尋
**位置**:`components/corr/RiverOverlay.tsx:99-106`

```tsx
const readout = cursor === null ? null : entries.map((e) => {
  const line = g.lines.find((l) => l.key === e.key);          // O(腿)
  const hit  = line?.pts.find((p) => p.offset === cursor);    // O(點) = 最多 840
  return { key: e.key, label: e.label, colorIndex: e.colorIndex, hit };
});
```
**影響**:11 腿 × 840 點 ≈ 9,200 次比較 / mousemove × 60–144 Hz ≈ **0.5–1.3 M 次/s**。
外加每次 mousemove 整個 `<svg>` 的 children(刻度 group + 11 條 polyline + 標籤)全部重建 vdom
(`points` 字串有 memo 保護所以 DOM 不動,但 vdom 物件照配置)。

**修法**:在既有的幾何 `useMemo` 內順手建 `Map<key, Map<offset, pt>>`,讀值列變成 O(腿) 的 `get`;
`g.lines.find` 改成同一個 memo 裡建好的 `Map<key, line>`。
再把 svg 的靜態部分(刻度 + 11 條線 + 0% 基準)抽成 `memo` 子元件(對齊 `ChartStatic` 的既有慣例),
只留十字線與讀值列在外層。

**風險**:零(純內部)。**Effort: S**

---

### F3-13 [medium] 圖牆 60 s 重播種是同幀 50 卡全換的長任務
**位置**:`hooks/useGroupLiveAccums.ts:58-69`;`components/stock/GroupGridView.tsx:320-323`

```ts
const seeded = useMemo<AccumMap>(() => {
  ...
  for (const code of csv.split(",")) { out[code] = accumFromGroupSnapshot(code, snap, ...); }
  return out;
}, [snapshots, csv]);      // ← snapshots 每 60 s 整份換 identity
```
**影響**:一次 `useGroupSnapshots` 輪詢回來 → 50 個 accum 全部換 identity → 50 張 `GroupCard`
memo 全破 → 同一幀 **50 × 0.31 ms ≈ 15 ms JS + ~25,000 個 SVG 節點 diff**。
這是每分鐘一次、肉眼可感的掉幀點(也是 `hasWindowedMinutes` 那條「別建整份陣列」優化的同一個戰場)。

**修法**:
1. 用 `startTransition` 包住重播種的 commit(React 19 可用),讓它可被使用者輸入打斷。
2. 更根本的:`accumFromGroupSnapshot` 回傳前先與現有 accum 逐欄比較,**內容相同就沿用舊物件**
   (沒有新成交的檔在 60 s 內內容多半不變)—— 直接讓 memo 擋掉大半。
3. 配合 `IntersectionObserver`:捲動區外(>16 檔時常有)的卡不重算幾何。

**風險**:`useGroupLiveAccums` 的「live 層以 `base === seeded` 判作廢」語意不可破 —— 若改成沿用舊物件,
要確保 `seeded` 的 identity 規則仍然成立(建議只在 per-code 層沿用,`seeded` 物件本身照換)。
**Effort: M**

---

### F3-14 [medium] `applyTick` 每筆成交淺拷兩個 Map + 一個陣列(~1,500 元素)
**位置**:`lib/stock-accum.ts:425-470`

```ts
const minutes = new Map(acc.minutes);          // 最多 271 筆
...
const ticks = [...acc.ticks, {...}].slice(-TAPE_MAX);   // 200 → 配置兩個陣列
const vp = new Map(acc.vp);                    // 最多數百~千筆
foldVp(vp, msg.t, msg.p, msg.q, msg.side);
```
實測 **0.031 ms/筆**。CLAUDE.md §4 記載開盤 50 檔每秒數百筆 → **0.3–0.9 ms/s 純配置**,
再乘上 GC 壓力(每筆產生 ~1,500 個元素的新結構)。

**影響**:單看不大,但它是「每一筆成交」的固定稅,而且與 F3-03/F3-13 疊加。
註解自己也承認「Map 淺拷在這個尺度上不是熱點」—— 以目前的量級(≤10 則打包/s)成立,
若未來要提高推播頻率(真・逐筆、不打包)就會變成熱點。

**修法**(**現階段建議不做,列為量級升級時的備案**):
- 一則打包內同一檔的多筆先合併再拷一次(現在是 `applyTick` 逐筆呼叫,一則打包內同一檔拷 N 次)。
  → 這一條**現在就值得做**:`useGroupLiveAccums` 的迴圈已經是 per-item,改成 per-code 批次套用即可。
- 長期:`ticks` 改 ring buffer(固定 200 的 typed 結構),`minutes` 改 typed array 索引
  (分鐘鍵本來就是連續整數 540–810 / 0–1365,**天生適合 `Int32Array` / `Float64Array`**)。

**風險**:`seq` 的兩個口徑(CLAUDE.md §4「snapshot.seq = ticks 尾筆序號;tick.seq 每收下一筆 +1」)
與 `isSeededDuplicate` 的三分支判定不可動 —— 批次套用要逐筆走完 seq 檢查,只是**最後才拷一次**。
**Effort: M**

---

### F3-15 [low] `ChartStatic` 的 memo 是「全有或全無」:末點變一格 = 整層重建
**位置**:`StockIntradayChart.tsx:171-765`

`ChartStatic` 收 13 個 prop,其中 `g` 每則 tick 都換 identity(價線末點多一格 / 末格收盤變了)。
於是「靜態圖層」這個名字在**報價路徑上是不成立的** —— 它只擋得住 hover。
內含的 `markLabels` / `pegList` / `hlineLabels` / `maObstacles` / `maLabels` / `bandLabels`
避讓運算(第 280–351 行)每次全跑,而這些東西一分鐘內幾乎不會變。

**修法**(與 F3-03 同一個方向):把圖層拆成
**「今天到上一分鐘」的真・靜態層(memo dep = 分鐘數)** + **「當前分鐘 + 現價圈」的 live 層**。
`live-last-bar.ts` 已經在資料層做了這個切分(正式末根 vs 即時末根),**渲染層照做即可**:
polyline 拆成「已定稿的 N−1 段」+「最後一段」,前者的 `points` 字串只在跨分鐘時重建。

**風險**:SVG 沒有 z-index,圖層順序完全由文件順序決定(元件內多處註解反覆強調)—— 拆層時
**必須保持節點的文件順序**,否則會出現「三角被 halo 吃掉」「極值標記被價線壓過」這類
畫得出來但零錯誤訊號的回歸。這是本區塊風險最高的一項改動。**Effort: L**

---

### F3-16 [low] `useContainerSize`:每張卡一個 ResizeObserver,無 rAF 合併
**位置**:`hooks/useContainerSize.ts:27-50`

已有 **1px 去抖**(第 42–46 行)與 **0×0 忽略**(第 38 行),品質不錯。剩下兩點:
1. 圖牆有 **50 個獨立 ResizeObserver**(每張 `CardIntradayChart` 一個),視窗 resize 時同幀
   50 次 `setSize` → 50 次 re-render + 50 次幾何重算(React 18+ 的 automatic batching 會把
   setState 合併成一次 commit,但**每張卡的幾何 memo 還是各自失效**)。
2. 回呼內直接 `setSize`,沒有 rAF 合併 → 拖視窗邊緣時每幀多次。

**修法**:單一模組層 ResizeObserver + `Map<Element, callback>` 分派(瀏覽器對「一個 RO 觀察 N 個
元素」的最佳化遠好於 N 個 RO);回呼統一在 rAF 內 flush。

**風險**:低。呼叫端契約(恆存 wrapper / 高度由外層指派)不變。**Effort: S**

---

### F3-17 [low] `useRiver` 每秒 clone 每腿的 `minutes` 物件並用 spread 求 max
**位置**:`hooks/useRiver.ts:32-40, 51-63`

```ts
function lastOf(minutes: Record<string, number>) {
  const offsets = Object.keys(minutes).map(Number);     // 最多 840 個字串 → 840 個數字
  const last_minute = Math.max(...offsets);             // 840 引數 spread
  ...
}
function applyDelta(prev, msg) {
  ... const minutes = { ...leg.minutes, [String(point.m)]: point.p };   // clone 840 鍵
      legs[key] = { ...leg, minutes, ...lastOf(minutes) };
}
```
**影響**:11 腿 × (840 clone + 840 keys + 840 Number + spread) 每秒一次 ≈ 3 萬次操作/s。
不致命,但完全可以 O(1):delta 帶的 `point.m` 本身就是新的最大 offset(單調遞增),
`last_minute = Math.max(prev.last_minute ?? -1, point.m)` 即可。

**修法**:`applyDelta` 直接用 `point.m` / `point.p` 更新 `last` / `last_minute`,不呼叫 `lastOf`
(`lastOf` 只在 `mergeLeg`(REST union)那條路留著)。

**風險**:低 —— 但要確認「delta 的 m 一定 ≥ 已有 offset」這個前提。從 `useRiver` 的 doc
(「各腿當前分鐘寫入」)看成立,建議保留 `Math.max` 防禦。**Effort: S**

---

### F3-18 [low] `RiverPanel.hasAnyPoint` 每 render 對每腿做 `Object.keys`
**位置**:`components/corr/RiverPanel.tsx:76`

```tsx
const hasAnyPoint = order.some((key) => Object.keys(state.legs[key]?.minutes ?? {}).length > 0);
```
11 腿 × 最多 840 鍵 = 每秒(delta 節奏)配置 ~9,000 個字串,只為了問「有沒有東西」。
**修法**:改用 `leg.last_minute !== null`(欄位已經在,`lastOf` 算好的),或
`for (const _ in obj) return true`。**Effort: S**

---

### F3-19 [low] `EnergySub` 的 React key 用浮點 x(resize 即全層重掛)
**位置**:`StockIntradayChart.tsx:884`(`key={`e-${b.x}`}`)、型別 `stock-intraday-svg.ts:97-102`

`EnergyBar = { x: number; h: number }` —— **沒有 minute 欄位**,所以 key 只能用 x,而
`x = minuteToX(minute, width, xw)` 依賴容器寬。容器寬一變(視窗 resize、圖牆檔數變動改列高)
→ 所有 key 換新 → **整層 1140 / 271 個 rect 卸載重掛**(不是更新屬性)。
另外浮點字串化在退化寬度下可能撞 key。

**修法**:`EnergyBar` 加 `minute` 欄位,key 用 minute。(若做了 F3-03 的單 `<path>`,這條自然消失。)
**Effort: S**

---

### F3-20 [low] `hasWindowedMinutes` 之外,`GroupCard` 每次 render 都重算 `secSummary` / `futSummary`
**位置**:`components/stock/GroupGridView.tsx:195-196`

```tsx
const sec = secSummary(positions, quote?.p ?? null, discount);
const fut = futSummary(positions);
```
無 memo,但 `GroupCard` 本身是 memo 且這兩支是 O(該檔部位數)(通常 0–2 筆)→ **可忽略,不建議動**。
列在這裡是為了說明「已經檢查過、判定不動」。

---

## 4. 工具與套件選型建議(含取捨)

現況:`frontend/package.json` 的 runtime dependencies 只有 5 個
(react / react-dom / @tanstack/react-query / clsx / tailwind-merge),**零圖表庫、零虛擬化、
零狀態管理、零 worker、零 canvas**。所有圖表 100% 手刻 SVG。
這個選擇在**正確性**上非常成功(CDP 標籤避讓、VP 桶界、極值等值反查、域外不畫……這些語意
沒有任何現成圖表庫能表達),代價全部落在**節點數與 React 重繪**上。

| 工具 | 用在哪 | 解決什麼 / 預期收益 | 代價 | 判定 |
|---|---|---|---|---|
| **(零相依)SVG `<path>` 合併** | `EnergySub`、`buildVpBars` 的長條、candle 量柱 | 節點數 1140 → 1;圖牆 DOM 從 ~20,000 降到 ~2,000。**這是本區塊 CP 值最高的一項** | 測試判準要改(testid 計數 → `d` 字串);沒有新相依 | **建議導入(先做)** |
| **(零相依)ref + 直接 DOM 操作畫十字線** | 四個元件的 hover 層 | mousemove 完全脫離 React;配合 F3-02 免 rect,hover 成本降一個數量級 | 與 RTL 測試的互動方式要改;要自己管清理 | **建議導入** |
| **(零相依)rAF 節流 + external store** | `syncHover`、`useContainerSize` | F3-01 的 50 卡放大效應消除 | 沿用既有 `tick-stream.ts` 的 EventTarget 模式,零新相依 | **建議導入** |
| **`uPlot`**(~45 KB, canvas) | 群組圖牆的 50 張**小圖** | canvas 一張圖 = 1 個 DOM 節點;50 張小圖的繪製成本可降 10–30 倍;內建 hover / 多序列 | 需要用 plugin hooks 重寫 VP / 成交點三角 / 極值標記 / CDP 標籤避讓;小圖上這些語彙本來就砍了一半(card variant 已無說明列、無成交欄),移植面比單檔頁小得多 | **有條件導入**:只換圖牆卡片,單檔頁維持 SVG(兩套繪製 = 「同一檔在卡片與單檔頁是兩張不一樣的圖」的風險,正是 `CardIntradayChart` doc 明確反對的 —— 需 user 拍板) |
| **`lightweight-charts`**(TradingView, ~180 KB, canvas) | 取代 `CandleChart` | 內建縮放 / 平移 / 十字線 / MA / 多 pane,效能一個數量級,拖曳不掉幀 | **自訂 overlay 能力有限**:hline label 避讓、視窗高低標記、內外盤雙柱、`volumeDelta` 這些都要靠 primitives 重寫;體積是目前整包的數倍 | **不建議(這一輪)**:K 線的效能問題(F3-05/F3-06)用拆 memo 就能解 90%,不值得引入這個量級的相依 |
| **`d3-scale` / `d3-shape`** | 取代手刻 `toY` / `priceAtY` / `pts` | 無 —— 本專案的縮放是整數毫元 + 明確域分支,d3 只會多一層抽象 | 相依 + 與現有「單一定義」紀律衝突 | **不建議** |
| **Web Worker / OffscreenCanvas** | 幾何計算 | 幾何單次成本 0.14–0.88 ms,**postMessage 的結構化複製成本比計算本身還高**(要傳 1140 個點物件) | 大幅架構複雜度 | **不建議** |
| **`react-window` / `@tanstack/virtual`** | 圖牆 >16 檔的捲動區 | 只渲染可視卡片 | 圖牆的版面是「檔數決定矩陣」(`gridShape`),虛擬化會破壞「同一群組每次打開版面相同」這個明確設計意圖 | **不建議**;改用 `IntersectionObserver` **暫停**不可見卡的幾何重算(保留 DOM),收益接近、破壞為零 |
| **`zustand`**(~1.2 KB) | `syncHover` / `quotes` / `toggles` 的細粒度訂閱 | 讓「多消費者高頻值」不必穿 props(F3-01 的根因) | 新相依;但本專案已有 `tick-stream.ts` + `useChartToggles` 兩個手刻 external store,模式已在 | **不建議新增相依**:沿用既有 EventTarget + `useSyncExternalStore` 模式即可,與 stdlib-only 哲學一致 |
| **`useDeferredValue` / `startTransition`**(React 19 內建) | 圖牆 60 s 重播種(F3-13)、圖牆非 hover 卡的更新 | 讓長任務可被輸入打斷 | ⚠ **交易系統要慎用**:延遲 commit = 畫面上的價格晚一拍。**只用在「非即時語意」的路徑**(重播種、指數疊線),**絕不可用在主圖末點 / 現價圈 / 閃電梯** | **有條件導入(限 F3-13)** |
| **`performance.mark` / `PerformanceObserver` longtask** | 量測基建 | 讓「快不快」變成數字而不是感覺 | 幾行程式 | **建議導入**(見 §6) |

**總體選型結論**:這個前端**不需要換掉 React,也不需要引入圖表庫**才能快。
按 CP 值排序的路線是
**① SVG 節點合併(F3-03)→ ② hover 脫離 React + 免 rect(F3-01/F3-02)→ ③ memo 拆層(F3-05/F3-06/F3-07)
→ ④ 死碼與重複計算(F3-04/F3-08)**。
這四步預估把主執行緒的圖表開銷降到現在的 **1/5 到 1/10**,而且**不動任何跨檔契約**。
只有在做完這四步還不夠(例如未來要把推播從 0.1 s 打包改成真・逐筆、或圖牆要到 150 檔)時,
才值得評估 canvas(uPlot)這條路。

---

## 5. 不要動的地方

1. **`buildIntradayGeometry` 的語意分支**:`norm()` 的「0 = 不可得」收口、`hasRef` 與首筆 fallback 的
   分權、極值的**等值反查**(`entries.find(m => m.h === target)`)、域外不畫、`flat` 退化域特判。
   每一條都對應一個真實 bug 的修法(註解裡有實測樣本)。**為了速度砍掉任何一條都是用正確性換效能。**
2. **`index-overlay-lines.ts::SORTED_ROWS` 的 WeakMap 快取**(第 66–76 行):已經是本檔最佳解
   (per-series 排序一次、50 張卡共用、隨舊物件 GC)。這是正確的模式,應該**往外複製**而不是改它。
3. **`useContainerSize` 的 1px 去抖與 0×0 忽略**:兩條都是修過的真 bug(RO 回饋迴圈、hidden tab 量到 0)。
4. **`useChartToggles` 的 module store 架構**(`useSyncExternalStore` + 單一 localStorage 真相源):
   架構對的,只有 `getSnapshot` 的同步讀需要改(F3-10)。
5. **`AdvanceDeclineChart` / `PnlChart` / `RiverCards`**:更新頻率 1/s ~ 5/s、節點數 < 100,
   `RiverCard` 已有 per-leg memo。加 memo / 換 canvas 都是過度工程。**明確建議不動。**
6. **`XAxisLabels` 刻意不進 memo**:兩個元件的 doc 都解釋了原因(要看 hover 位置決定遮蔽),
   且只有 ≤6 個 text 節點。這是**正確的取捨**,不要「順手補 memo」。
7. **`sideSummary` 只在 page variant 算**(`StockIntradayChart.tsx:1207`,`card || index` 時為 null):
   已經做過這個優化(review B4),0.003 ms,不用再碰。
8. **所有「模組層空常數」**(`EMPTY_PEGS` / `EMPTY_IDX_LINES` / `EMPTY_MARKS` / `EMPTY_FILLS` /
   `EMPTY_POSITIONS` / `NOOP_HOVER` / `EMPTY_ENERGY` / `EMPTY_LINE` / `EMPTY_HLINES`):
   這些是 memo 邊界成立的前提,`StockIntradayChart.memo.test.tsx` 專門釘住其中一條。**只能加不能減。**
9. **SVG 的文件順序 = 圖層順序**:元件內至少 6 處註解在強調(極值標記必須在主價線之後、
   成交點必須是最後一組、VP 必須在填色之前……)。任何拆層 / 合併 path 的重構都必須保持順序。

---

## 6. 量測方法(怎麼證明快了或慢了)

### 6.1 純 JS 微基準(可重跑,已驗證)
我用的方式是 **esbuild 打包真實模組後用 node 跑**,不重寫近似碼:

```bash
cd C:/side-project/copycat/frontend
node_modules/.bin/esbuild <bench.ts> --bundle --platform=node --format=cjs \
  --alias:@=./src --outfile=<bench.cjs>
node <bench.cjs>
```
腳本在 `…/scratchpad/bench/{bench,bench2,bench3}.ts`。
這是**回歸基準**:任何一項改動後重跑,數字要往下走。
⚠ 限制:量不到 React reconcile 與瀏覽器繪製,而那兩者通常是 JS 的 2–5 倍。

### 6.2 真環境 trace(必要,不可略)
專案慣例(CLAUDE.md §1):**看盤日常一律 `npm run build` + `npm run preview`(port 4173)**,
不要用 `npm run dev` 量效能(dev build 有 props-diff 開銷)。

三個必錄場景,各 20 s Performance trace:
1. **圖牆 50 檔盤中靜置**(不動滑鼠)→ 量「報價驅動」的基線:Scripting / Rendering / Painting 佔比,
   longtask 數量。目標:無 > 50 ms 的 task。
2. **圖牆 50 檔,滑鼠在一張卡上持續掃過**(F3-01 的直接證據)→ 現況預期會看到一片
   連續的 `GroupCard` render 火焰。改完後這一片應該消失。
3. **個股頁切 5 分 K,盤中靜置 20 s**(F3-05/F3-06)→ 看 `aggregateBars` / `bollinger` 的自身時間。
4. **期貨 tab 分時靜置 20 s**(F3-07)→ 看 `futuresBarsToAccum` + `buildIntradayGeometry`。

工具:本機已裝 `chrome-devtools-mcp`(`performance_start_trace` / `performance_stop_trace` /
`performance_analyze_insight`),可直接在 4173 上錄;或用 React DevTools Profiler 的
「Ranked」視圖直接看哪個元件吃掉最多 commit 時間。

### 6.3 常駐探針(建議加,幾行)
```ts
// main.tsx 或一支 lib/perf.ts
new PerformanceObserver((l) => {
  for (const e of l.getEntries()) if (e.duration > 50) console.warn("longtask", e.duration, e);
}).observe({ entryTypes: ["longtask"] });
```
以及在 `buildIntradayGeometry` / `aggregateBars` 外層包 `performance.measure`
(只在 `import.meta.env.DEV` 或一個 query flag 下開啟,不進 prod 熱路徑)。

### 6.4 節點數(最直觀的指標)
```js
// DevTools console,開著圖牆時
document.querySelectorAll("svg *").length
```
現況預期 ~20,000(50 卡 × ~400)。做完 F3-03 後應降到 ~2,000–4,000。
這個數字比任何 profile 都好解釋,也最適合當驗收判準。

### 6.5 既有測試作為守門
- `App.memo.test.tsx` / `GroupGridView.memo.test.tsx` / `StockIntradayChart.memo.test.tsx` /
  `RiverPanel.memo.test.tsx` 是本專案**已經在用的 memo 計次測試**(用 `vi.mock` 換計次替身)。
  任何 memo 邊界改動都要先看這四支,並依同一模式為新邊界補一條 —— 因為 memo 失效
  **在畫面上完全看不出來**,只有計次測試抓得到。
- 完成前 gate(專案覆寫):`npm test` + `npx tsc -b` + `npx eslint src` +
  `npx react-doctor@latest --scope changed --no-telemetry`(在 `frontend/`)。

---

## 7. 硬約束速查(改造時必須同時處理的跨檔契約)

以下皆引用 CLAUDE.md §4,**本區塊的任何改動若碰到,必須點名並兩邊同動**:

| 契約 | 這一區塊的哪個改動會碰到 | 同動點 |
|---|---|---|
| **個股 `seq` 兩個口徑**(snapshot.seq = ticks 尾筆;tick.seq 每筆 +1) | F3-14 的 `applyTick` 批次化 | `copycat/live/stock_state.py::ingest/snapshot` ↔ `lib/stock-accum.ts::fromSnapshot/applyTick`;症狀 = 成交明細 tbody 靜默整片重掛 |
| **`ticks` 打包 wire 形狀**(`{type:"ticks", items:[…]}`) | F3-14 | `server/stock_engine.py::_flush_ticks` ↔ `useStockStream` `case "ticks"` + `useGroupLiveAccums` |
| **個股頁即時末根分鐘鍵 = accum 起點分 +1、上限 13:30** | F3-06 的聚合改寫 | `lib/live-last-bar.ts::mergeLiveMinuteBars`(前端唯一產生點);`live-last-bar.test.ts` 案 1/2/9 |
| **台指期疊線分鐘鍵 = 1K 終點標記 −1 分** | 若動 `txf-overlay-series` / `index-overlay-lines` | `lib/txf-overlay-series.ts`;`futures_source.py` 分鐘域 |
| **日 K 定稿界 `DAILY_FINAL_TIME` 14:00 前後端同值** | F3-06 若動 `StockChart.dailyFinal` | `server/bars.py::DAILY_FINAL_TIME` ↔ `lib/day-bars-rollover.ts`;`test_daily_final_time_parity_with_frontend` 釘等值 |
| **期貨 CDP/MA 前後端同式 + golden fixture** | 不要碰 `lib/futures-overlay.ts` | `tests/fixtures/overlay_parity.json` 兩邊各一條 |
| **江波圖調色盤色數 ≥ 腿數** | F3-12 若改 River 的線層結構 | `configs/correlation.json` ↔ `components/corr/river-colors.ts` ↔ `index.css` `--color-river-N` |
| **`/ws/stock` 入站 `view` 訊息** | F3-13 若改圖牆成員的訂閱 / 虛擬化 | `lib/tick-stream.ts::setTickView` ↔ `server/app.py::ws_stock` ↔ `stock_engine.set_view`;若做 IntersectionObserver 暫停,**不要**順手改 view 集合(後端據此決定推不推該檔的逐筆) |
| **自選上限 150 的效能預算註解** | F3-03/F3-13 改完後「檔數 × 單價」的最壞值會變 | `stock_watchlist.py::WATCHLIST_LIMIT` 的第二類讀者(stock_engine / watchlist_service / stock_state / GroupGridView 的預算註解)要重算 |
| **「盤前篩選」群組名前後端同字面** | 無(只要不動群組解析) | — |

---

## 8. 建議的執行順序(每批可獨立出貨、獨立驗收)

| 批次 | 內容 | 預期收益 | 驗收判準 |
|---|---|---|---|
| **B1(S)** | F3-04(pts 重複)、F3-08(死碼 + 重複 windowedEntries)、F3-11(窗高低單趟)、F3-18(Object.keys)、F3-17(River O(1) last) | 純算式,**零行為改變**;期貨路徑 JS −25%,圖牆 −10% | 微基準數字下降;`pytest`/`vitest` 全綠(純重構不該有任何測試需要改) |
| **B2(S–M)** | F3-02(免 rect)+ F3-01(syncHover external store + rAF) | **hover 卡頓消失**,圖牆滑鼠移動 −90% re-render | 場景 2 的 trace:`GroupCard` render 從一片變零星;`GroupGridView.memo.test.tsx` 補一條「hover 不打穿 memo」 |
| **B3(M)** | F3-03(EnergySub → 單 path;順帶 F3-19 key) | DOM 節點 20,000 → ~4,000 | `document.querySelectorAll("svg *").length`;testid 計數測試改判準 |
| **B4(S–M)** | F3-05(CandleChart memo 拆層)+ F3-06(正式段聚合快取) | 分 K 常開 JS −85%;K 線拖曳不掉幀 | 場景 3/4 trace;`CandleChart.test.tsx` 全綠 |
| **B5(M)** | F3-07(期貨 adapter 兩段化)+ F3-09(core memo)+ F3-10(toggles 快取) | 期貨 tab JS −60% | 場景 4 trace |
| **B6(M)** | F3-13(圖牆重播種:per-code 沿用 + IntersectionObserver)+ F3-16(單一 RO) | 每分鐘的掉幀點消失 | 場景 1 trace 無 > 50 ms longtask |
| **B7(L,選配)** | F3-15(ChartStatic 靜態/live 分層)、或評估 uPlot 換圖牆卡片 | 再降一個數量級 | 需 user 先拍板(圖層順序風險 / 兩套繪製風險) |

---

## 9. 未決問題(需要 user 回答或需要真環境量測才知道)

1. **真瀏覽器下 React reconcile 佔比多少?** 我的微基準只量 JS 計算。所有「節點數」類 finding
   (F3-03/F3-15)的實際收益,要先錄一次場景 1/2 的 trace 才能定量。**這是第一件該做的事。**
2. **使用者實際盤中常開哪個畫面?** 若 90% 時間停在圖牆 → 優先 B2/B3;若停在期貨 tab → 優先 B5;
   若常用 5 分 K → 優先 B4。目前無使用資料。
3. **圖牆常態檔數是多少?** 上限 150、`gridShape` 在 >16 檔時走捲動。若常態就是 ~60 檔
   (盤前篩選群組),F3-13 的 IntersectionObserver 收益會遠大於估計。
4. **`syncHover` 預設開是刻意的嗎?**(`useChartToggles.ts:59-60` 標 auto-default,非 user 逐項拍板)
   若 user 其實不常用,關掉預設就是零成本解掉 F3-01 的一大半 —— 但那是治標。
5. **圖牆卡片可否接受與單檔頁「不是同一份渲染碼」?** 這是 uPlot / canvas 路線的前提,
   而 `CardIntradayChart` 的 doc 明確反對(「同一檔股票在卡片與單檔頁上是兩張不一樣的圖」)。
   **需 user 拍板**,在 B1–B6 做完之前不必問。
6. **未來會不會把逐筆從「0.1 s 打包」改成真・逐筆?** 若會,F3-14(applyTick 的 Map 淺拷)
   會從 low 升成 critical,`minutes` / `ticks` 的 typed-array 化就值得做。
7. **`bollinger` 的測試有沒有釘精確值?** 決定 F3-05 能不能改成單趟滑動窗(浮點不逐位元相同)。
   `lib/bollinger` 沒有獨立測試檔,斷言散在 `CandleChart.test.tsx` —— 需要逐條看過才能定。
