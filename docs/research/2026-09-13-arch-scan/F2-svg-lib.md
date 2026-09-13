# F2-svg-lib — 前端 SVG 繪圖計算層(純函式)架構與效能掃描

掃描日期 2026-09-13 / 對象 `C:/side-project/copycat/frontend/src/lib/*.ts` 的繪圖幾何層
與其唯一消費者(`components/stock/StockIntradayChart.tsx` / `CandleChart.tsx` /
`GroupGridView.tsx` / `components/futures/FuturesChart.tsx` / `components/corr/*` /
`components/index/MarketPane.tsx`)。

所有量測用 Node v24.13.0(V8,與 Chrome 同引擎)跑複刻版熱路徑,腳本留在
`scratchpad/arch-scan/bench-svg.mjs` 與 `bench-candle.mjs`(不碰 repo)。

---

## 0. 一句話結論

**這一層的純數學不慢,慢的是「每個圖元一個 DOM 節點」與「每 tick 從零重算整份序列」兩件事。**

- 純幾何計算:一張 271 分鐘的分時圖 `buildIntradayGeometry` **0.10 ms**;近全軸 1365 分鐘 **0.53 ms**。
  50 張卡全部重算也只有 **14.4 ms**。以「純計算」而言,這一層**不是**瓶頸,換 numpy 式的向量化工具毫無意義。
- 真正的成本在渲染側:**每張卡 ~450–470 個 SVG 節點**,50 張卡 ≈ **23,000 節點**,
  自選上限 150 檔 ≈ **70,000 節點**。這些節點在「指數疊線開著」時**每秒全部重建一次**(見 B1-01)。
- 第二個成本在 K 線鏈:個股頁分 K 模式下,每則 ticks 打包(0.1 s)會把 **5,900 根 1 分 K 整條重跑**
  聚合 + MA + 布林(實測 m5 模式 **2.07 ms/打包 = 20.7 ms/s 純 JS**),而結果只用到視窗內 ≤700 根。

因此改造方向是:**幾何層(lib/*.ts)基本保留,渲染層(components 的 JSX)換成 Canvas 2D**,
外加三處把「全序列重算」改成「增量 / 視窗限定」。圖表庫(uPlot / lightweight-charts)的
評估見 §6 —— 結論是**不建議整套換**,因為本專案的價值全在那些跨檔契約與幾何規則裡,
圖表庫吃不下它們,只會把 921 行幾何搬成 1200 行 adapter。

---

## 1. 架構地圖

### 1.1 分層

```
資料層  lib/stock-accum.ts        StockAccum{minutes: Map<分鐘, MinuteAgg>, vp: Map<價位, VpCell>, ticks, meta, high/low}
        lib/index-accum-adapter   加權/櫃買 minutes(Record<"HHMM", 毫點>)→ 同形
        lib/futures-accum-adapter 期貨 1K + live → 近全軸索引當 key 的同形 accum
              │
              ▼
幾何層  lib/stock-intraday-svg.ts (921)   buildIntradayGeometry / buildEnergyBars / overlayLines /
        │                                 bandLabels / edgePriceLabels / pegLabels / layoutEdgeLabels /
        │                                 yieldToObstacles* / labelWidth / vwapLabelBox / sideSummary
        ├ lib/volume-profile.ts (114)     buildVpBars(價位別成交量水平長條)
        ├ lib/index-overlay-lines.ts(107) buildIndexOverlayLines(加權/櫃買/台指期疊到個股價格軸)
        ├ lib/txf-overlay-series.ts(111)  期貨 1K → 同形 IndexSeries(分鐘鍵 −1)
        ├ lib/index-chart-svg.ts (117)    buildOverlayGeometry(指數 pane 的相對 % 雙線) / outOfDomainLevels
        ├ lib/river-chart-svg.ts (219)    江波圖並排 / 重疊幾何 + spreadLabelYs + timeTicks
        ├ lib/candle.ts (354)             aggregateBars / movingAverage / buildCandleGeometry / hlineYOf
        ├ lib/bollinger.ts (47)           bollinger / bandSeries
        ├ lib/live-last-bar.ts (133)      mergeLiveMinuteBars / mergeLiveDailyBar(即時末根)
        ├ lib/futures-overlay.ts (75)     期貨 CDP/MA(與後端 overlay.py 同式,golden fixture 釘住)
        └ lib/allday.ts (246)             近全軸段表 / 索引 ↔ HHMM / 錨定日 / sliceCurrentAllday
              │
              ▼
版面層  lib/chart-frame.ts / pane-frame.ts    量測 px → viewBox(1:1 或反解)
        lib/chart-extreme.ts / chart-hlines   極值標記 style + 翻面規則 / 水平線型別
        lib/chart-crosshair.ts                螢幕座標 → viewBox 座標、標籤夾制、區間相交
        lib/time-labels.ts                    整點刻度
        lib/svg-points.ts (4 行)              pts():`x.toFixed(1),y.toFixed(1)` join
              │
              ▼
渲染層  StockIntradayChart.tsx(1724)    ChartStatic(memo) / EnergySub(memo) / XAxisLabels / hover 層
        CandleChart.tsx(699)            CandleChartStatic(memo)
        GroupGridView.tsx(482)          GroupCard(memo) × N
        FuturesChart / MarketPane / RiverCards / RiverOverlay / AdvanceDeclineChart
```

### 1.2 設計特徵(讀 code 看得出來的)

1. **零圖表庫、零 canvas、零 worker**。`package.json` runtime dependencies 只有
   `react / react-dom / @tanstack/react-query / clsx / tailwind-merge` 五個。
   全庫搜 `canvas` / `new Worker` / `OffscreenCanvas` 只有兩處 `requestAnimationFrame`
   (`FuturesLadder.tsx:333`、`LadderView.tsx:162`,與繪圖無關)。
2. **幾何全部是純函式**,零 React 依賴,元件只負責掛 DOM。每個檔頭都有大量「為什麼這樣寫」的
   註解,且**大多數是為了避免靜默錯誤**(座標對不齊、標籤疊字、域外 clamp 變假陳述),
   不是為了效能。這是這套 code 真正的資產。
3. **memo 紀律已經做過一輪**:`ChartStatic` / `EnergySub` / `GroupCard` 都是 `memo`,
   props 一律要求「純量或模組層常數 identity」,檔內有 10 處以上註解專門警告
   「行內 `[]` / `{}` / 箭頭函式會打穿 memo」。`EMPTY_HLINES` / `EMPTY_PEGS` /
   `EMPTY_IDX_LINES` / `EMPTY_ENERGY` / `EMPTY_FILLS` / `EMPTY_POSITIONS` /
   `NOOP_HOVER` / `SPOT_WINDOW` / `STKFUT_WINDOW` / `ALLDAY_WINDOW` 全是為此存在的模組層常數。
4. 已有三處上一輪的效能修法,**不要回頭動**:
   - `hasWindowedMinutes`(stock-intraday-svg.ts:303)取代 `windowedEntries(...).length > 0`,第一格命中即退出;
   - `buildEnergyBars`(:335)讓副圖不再整份跑 `buildIntradayGeometry`;
   - `sortedIndexRows`(index-overlay-lines.ts:57)以 `WeakMap<IndexSeries, Row[]>` 讓 50 張卡共用一次排序;
   - `sideSummary` 在 card / index 變體直接不算(StockIntradayChart.tsx:1207)。

---

## 2. 資料流(一則成交到畫面)

```
後端 WS  {"type":"ticks","items":[{code,t,p,q,side,...,seq}]}      ← 0.1 s 打包(CLAUDE.md §4)
   │
   ├─ 單檔頁 useStockStream → applyTick → 新 StockAccum(minutes 新 Map、vp 新 Map)
   │      └→ StockIntradayChart: g=useMemo[accum.minutes,…] 失效 → buildIntradayGeometry 重算
   │             → vpBars / fillMarks / subEnergy / idxLines 五個 memo 一起失效(dep 含 g 或 minutes)
   │             → ChartStatic props 換 → 整個靜態圖層 React reconcile(~190 節點)
   │             → EnergySub props 換 → 271(近全軸 1140)個 <rect> 全部 reconcile
   │      └→ StockChart(K 線): liveMinutes=accum.minutes 換 → bars=useMemo 失效
   │             → mergeLiveMinuteBars(5900 根拷貝) → aggregateBars(5900 根)
   │             → CandleChart: movingAverage×2(5900)+ bollinger(5900)+ buildCandleGeometry(700)
   │             → CandleChartStatic: 700 蠟燭 ×(line+rect+g)+ 700 volBar ≈ 2,100 節點 reconcile
   │
   └─ 圖牆 useGroupLiveAccums → per-code seq 檢查 → 只有收到成交的 code 換 accum identity
          └→ GroupCard memo:只有那幾張卡重繪(T4 #185 的設計,做得很好)

後端 WS  index push(加權 / 櫃買 / 台指期)                          ← ~1 s
   │
   └─ App useIndexStream → toSeries 每則新物件 → indexSeries 新 identity
          └→ GroupGridView 傳給**每一張**卡(toggle 開時)
                 → GroupCard memo 全體比不過 → 50 張卡全部重繪
                       → 每卡 idxLines 重算(3 線 × 271 點)+ ChartStatic 整層重建
                       ≈ 23,000 SVG 節點 / 秒                       ← 見 B1-01

滑鼠 mousemove
   └─ setHover → IntradayChartCore re-render(g / vpBars / idxLines 命中 memo 不重算)
          → ChartStatic memo 擋住 → 只重建 hover 層 + XAxisLabels(≤ 15 節點)  ← 這條已經很好
```

---

## 3. 熱路徑逐條(含量測)

| # | 路徑 | 頻率 | 每次工作量 | 實測 |
|---|---|---|---|---|
| H1 | `buildIntradayGeometry`(現貨窗 271 分鐘,800×260) | 每則 ticks 打包(0.1 s)/該檔 | entries 拷貝+sort、4 趟 map(priceLine/vwapLine/energyBars/Set)、areaPolygon 3.2 KB 字串、2 次 `find` 全掃 | **0.101 ms** |
| H2 | `buildIntradayGeometry`(近全軸 1365) | 期貨頁每則 WS(已 coalesce ≤10/s) | 同上 ×5 倍資料 | **0.530 ms** |
| H3 | `pts()` 271 點 | 每 tick × **4 次**(priceLine 被呼叫 2 次 + vwap + idx 線) | 271×2 次 `toFixed(1)` + join,產 3,227 字元 | **0.046 ms** |
| H4 | `pts()` 1365 點 | 同上 | 產 16,258 字元 | **0.254 ms** |
| H5 | `windowedEntries` 271 / 1365 | 每次 H1/H2 內含,另 `buildEnergyBars` 再一次 | `[...entries()].filter().sort()` | **0.012 / 0.064 ms** |
| H6 | 一張卡完整幾何 + 4 條 pts | 每 tick / 該卡 | H1+H3×4 | **0.287 ms** |
| H7 | 50 張卡同時重算(= 指數 push 時的實況) | **每 ~1 s**(指數 toggle 開時) | H6 × 50 | **14.4 ms** 純 JS |
| H8 | 150 張卡(自選上限) | 同上 | H6 × 150 | **43.1 ms** 純 JS |
| H9 | `aggregateBars(6100 根, n=5)` | 每則 ticks 打包(0.1 s),個股頁分 K | 每根 2 次 `slice`+`Number`、1 個 template-literal key、每桶 1 次 `stampOf` | **1.539 ms** |
| H10 | `aggregateBars(6100, n=1)` | 同上(m1 模式) | 純 `[...bars]` | 0.004 ms |
| H11 | `movingAverage(6100,5)+(6100,20)` | 同上 | 2 個 6100 陣列配置 | **0.150 ms** |
| H12 | `bollinger(6100, 20)` | 同上(布林 toggle 開) | O(n×20×2) ≈ 244,000 次浮點 + 5,880 個物件 | **0.318 ms** |
| H13 | `bollinger(700, 20)`(= 只算視窗) | 對照組 | | 0.036 ms(**8.8×** 更快) |
| H14 | `buildCandleGeometry(700)` | 同上 | 700×(6 次 toY + 2 物件) | **0.049 ms** |
| H15 | K 線鏈合計(m5 模式) | 每 0.1 s | H9+H11+H12+H14+merge | **2.07 ms → 20.7 ms/s** |
| H16 | `buildVpBars`(~100 價位) | 每 tick / 該卡 | 域過濾、`Math.max(...spread)`、POC 掃、每根 2 次 `stepUp/stepDown`(各線性掃 6 列 TICK_TABLE)、最後 sort | 未單測,估 0.02 ms |
| H17 | `buildIndexOverlayLines` | 每 tick(dep 含 `g`)+ 每指數 push × 每卡 | 3 線 × 271 點 × (窗判 + 乘除 + toY + push) | 估 0.03 ms/卡 |
| H18 | hover `g.minuteOf(x)` | 每 mousemove(~60/s) | 1 次除法 + Set.has + ≤3 次 snap | < 0.001 ms(**不是問題**) |
| H19 | `layoutEdgeLabels` / `bandLabels` / `pegLabels` / `yieldToObstacles` | 每次 ChartStatic render | n ≤ 9,兩趟 sweep | < 0.01 ms(**不是問題**) |
| H20 | `sliceCurrentAllday`(5,700 根) | bars 換(60 s)/ holidaySet 換 | 每根 `anchorClassOf` 2 次 slice + Number,memo map 命中 | 低頻,**不是問題** |

### 3.1 SVG DOM 節點統計(逐項推導)

一張個股分時圖(`variant="card"` 與 `"page"` 圖形語彙相同),VP 開、CDP+MA 開:

| 圖層 | 節點式 | 節點數 |
|---|---|---|
| `defs` + 2 clipPath + 2 rect | 固定 | 5 |
| 平盤虛線 | 1 line | 1 |
| 整點格線 `hourTicks.map` | 5 line | 5 |
| y 刻度 `g.yTicks.map` | 11 × (g + line + text) + 2 lamp rect | 35 |
| **量分佈 `vpBars.map`** | g + N rect(N = 域內有成交的合法檔位;300 元股 ±10% / tick 0.5 → 上限 120) | **~40–120** |
| 平盤填色 | 2 polygon | 2 |
| 疊線 `oLines.map` | 7 × (g + line) | 14 |
| 帶內標籤 `bandLabels` | 7 text | 7 |
| VWAP 線 | 1 polyline | 1 |
| 主價線 | 2 polyline(clip 上下半) | 2 |
| 指數疊線 `idxLines.map` | 3 × (g + polyline + text) | 9 |
| 極值標記 `markLabels` | 2 × (g + circle + text) | 6 |
| MA 價位標 / 掛牌 / VWAP 標 / POC 標 | text | ~6 |
| 成交點 `fillMarks` | g + M polygon | 1 + M |
| `XAxisLabels` | 5 text | 5 |
| **`EnergySub`** | line + 2 text + **271 rect**(近全軸 **≤1140**) | **274 / 1143** |
| hover 層(僅 hover 時) | ~12 | 12 |
| **合計** | | **~410–500 / 卡**(近全軸 ~1,300) |

- 圖牆 50 張卡 → **20,500–25,000 節點**
- 自選上限 150 檔 → **61,500–75,000 節點**
- 其中 **`EnergySub` 一層就佔 55–66%**(271/450)。

K 線圖(`CandleChart`,`MAX_VISIBLE = 700`):

| 圖層 | 節點數 |
|---|---|
| `g.candles.map` | 700 × (g + line + rect) = **2,100** |
| `g.volBars.map`(或內外盤雙柱 → ×2) | **700**(雙柱 700 g + 1400 rect = 2,100) |
| y 刻度 5 × (g+line+text) | 15 |
| BB 3 節點 + MA 2 polyline + 標記/hlines | ~15 |
| **合計** | **~2,830(內外盤雙柱態 ~4,230)** |

---

## 4. Findings

> 嚴重度以「在熱路徑上 × 量級」排序。所有 `location` 為 `檔案:行號`。

### B1-01 [critical / render] 指數疊線開啟時,整面圖牆每秒全量重建 ~23,000 SVG 節點

**location** `frontend/src/components/stock/GroupGridView.tsx:462` + `hooks/useIndexStream.ts:164` + `components/stock/StockIntradayChart.tsx:1170-1183`

```tsx
// GroupGridView.tsx:462
indexSeries={toggles.idxTwse || toggles.idxOtc || toggles.idxTxf ? indexSeries : null}
```
```ts
// useIndexStream.ts:164 —— 每則 WS 訊息造新 IndexSeries 物件
if (msg.twse) commitRef(twseRef, setTwse, toSeries(msg.twse, twseRef.current));
```

`toSeries` 每則(index engine ~1 s 一拍)回**新物件** → `indexSeries` 新 identity →
`GroupCard` 的 `memo` 淺比對對**每一張卡**都失敗 → 50 張卡全部 re-render →
每卡 `idxLines` useMemo(dep `idxTwseSeries` 換了)重算 → `ChartStatic` 的 `idxLines` prop 換 →
**ChartStatic 整層重建**(不只是指數線那三條)。

GroupGridView.tsx:52-54 的註解已經承認了這件事(「序列每秒換 identity,關著也傳的話整牆卡
(上限 150)每秒全部重畫,memo 形同虛設」)—— 但解法只做到「關著時傳 null」,**開著時就是每秒全畫**。

**影響**:純 JS 14.4 ms/s(50 卡)/ 43.1 ms/s(150 卡),再加上 React reconcile 20,000+ 個
SVG 節點與瀏覽器的 style recalc。這是圖牆掛整天時最大的單一固定開銷,且**只在使用者按下
「加權 / 櫃買 / 台指期」三顆鈕之一時才發生**(平時 T4 #185 的 per-code accum identity 讓它很安靜)。

**fix**:把指數序列從 props 鏈上拿掉,改成**外部 store + `useSyncExternalStore`**,由一個
`<IndexOverlayLayer>` 子元件自己訂閱並自己算 `idxLines`。`ChartStatic` 不再吃 `idxLines` prop
(它本來就是獨立的一組 `<g data-testid="index-line-*">` 節點,拆得乾淨)。
這樣指數 push 只重建每卡 3 條 polyline + 3 個 text(50 卡 = 300 節點),而不是 23,000。

**risk**:動到 `CLAUDE.md §4` 沒有登記的東西,但會動到 `StockIntradayChart.indexlines.test.tsx`
(14 處 `index-line-*` 斷言)與 `GroupGridView.memo.test.tsx`。z-order 契約要保住:
指數線必須畫在主價線之後、極值標記之前(StockIntradayChart.tsx:547-548 註解)——
拆成獨立子元件時**位置不可移**,SVG 沒有 z-index。

**effort** M

---

### B1-02 [critical / render] `EnergySub` 每張卡 271 個 `<rect>`(近全軸 1140),每 tick 全部重建

**location** `frontend/src/components/stock/StockIntradayChart.tsx:882-892`

```tsx
{bars.map((b) => (
  <rect key={`e-${b.x}`} data-testid="energy-bar"
        x={b.x - bw / 2} y={h - b.h} width={bw} height={b.h} className="fill-ink-muted" />
))}
```

檔案自己的註解(:812-817)已經量過:「memo 擋得住 hover,但擋不住報價 —— 每則 tick 讓
`accum.minutes` 換 identity → `subEnergy` 重算 → 本層 1140 個 rect 全部重建;jsdom 量到滿窗一輪
~15 ms」,並已把「改單一 `<path>`(節點數 1140 → 1)」寫進 `docs/next-time.md:733`(停放中)。

**影響**:50 張卡 × 271 = **13,550 個 rect**,佔整面圖牆節點數的 55–66%。

**fix**:改成單一 `<path d="M x0 y0 V h ..." >`。量柱是等寬矩形,可用
`M (x-bw/2) h L (x+bw/2) h L (x+bw/2) (h-bh) L (x-bw/2) (h-bh) Z` 串接,或更省的
`strokeWidth={bw}` + 一條 `M x h V (h-bh)` 的 path(柱寬用 stroke 寬表示,節點 271 → 1,
字串長度也比 271 個 rect 的屬性總量小一個量級)。

**risk**:`energy-bar` 有 4 處測試斷言(2 檔)要改成 path `d` 的斷言。
**絕對不可**用「當日總量當 memo key」的捷徑 —— next-time 明確記載:1K 回補可以在總量不變下
改寫某一分鐘的量,那種 memo key 會讓副圖靜默停在舊值(用錯誤換效能)。

**effort** S

---

### B1-03 [high / render, architecture] SVG「每圖元一節點」模型 = 節點爆炸的根因

**location** 全域;最重的三處:`StockIntradayChart.tsx:882`(energy rect)、
`StockIntradayChart.tsx:451-464`(vp rect)、`CandleChart.tsx:221-240`(candle g+line+rect)

```tsx
// CandleChart.tsx:221 —— 700 根 × 3 節點
{g.candles.map((c, i) => (
  <g key={`c-${i}`}>
    <line x1={c.cx} x2={c.cx} y1={c.wickTop} y2={c.wickBottom} className={BODY_CLASS[c.dir]} strokeWidth={1} />
    <rect data-testid="candle-body" x={c.x} y={c.bodyTop} width={c.w} height={c.bodyH} className={BODY_CLASS[c.dir]} />
  </g>
))}
```

**影響**:見 §3.1。圖牆 20,500–25,000 節點 / K 線 2,830–4,230 節點。
每個節點在 React 側有一個 fiber、在瀏覽器側有一個 SVG element + 一份 computed style。
這是「整天掛著」時記憶體與 style recalc 的主要來源,也是 `npm run dev` 的 props-diff
開銷讓 user 必須改用 `npm run preview` 的根因之一(CLAUDE.md §1 表註)。

**fix(不換技術棧的版本)**:把三個「每 bar 一節點」的層各收成 1–3 個 `<path>`:
- energy bars → 1 path(見 B1-02)
- vp bars → 1 path(水平長條,`M Y_AXIS_W y h w v h Z` 串接)
- candles → 4 path(up body / down body / up wick / down wick;`dir` 只有三種,class 可分組)

節點數:圖牆 450/卡 → **~130/卡**(50 卡 23,000 → 6,500);K 線 2,830 → **~40**。

**fix(換技術棧的版本)**:Canvas 2D,見 §6。

**risk**:`candle-body`(7 處)/ `vol-bar`(15 處)/ `energy-bar`(4 處)/ `vp-bar`(14 處)
共 **40 處測試斷言**要改寫成 path `d` 比對。這是真實成本但可控(改成「d 字串含 N 段」的斷言)。
z-order 由文件順序決定的既有紀律**不變**(path 仍在原位)。

**effort** M(三層各一次)

---

### B1-04 [high / algorithmic] 個股頁分 K:每 0.1 s 把 5,900 根 1 分 K 從零重算一遍

**location** `frontend/src/components/stock/StockChart.tsx:196-203` + `components/stock/CandleChart.tsx:475-497`

```tsx
// StockChart.tsx:196 —— liveMinutes = accum.minutes,每則 ticks 打包換 identity
const bars = useMemo(() => {
  const raw = data?.bars ?? [];
  if (liveMinutes !== null) {
    return aggregateBars(mergeLiveMinuteBars(raw, liveMinutes, liveToday, nowMinute), minutesOf(mode));
  }
  ...
}, [data, mode, liveMinutes, liveDay, dayOpen, liveToday, nowMinute]);
```
```tsx
// CandleChart.tsx:475 —— bars identity 一換,MA / BB 全序列重算
const { shown, g, ma5, ma20, bbUpper, bbLower } = useMemo(() => {
  const m5 = movingAverage(bars, 5).slice(start, start + viewport.count);
  const m20 = movingAverage(bars, 20).slice(start, start + viewport.count);
  const bb = showBb ? bollinger(bars, 20).slice(start, start + viewport.count) : [];
  ...
}, [bars, viewport, showBb, dimW, dimH]);
```

`StockChart.tsx:161` 的註解自己算過:「成本 = 一次 `aggregateBars`(30 日 1 分 K ≈ 5,900 根)+
merge O(補的根數)」—— 但漏算了下游的 `movingAverage ×2` + `bollinger` 也一起失效。

**實測**(6,100 根,m5 模式):
```
mergeLiveMinuteBars   0.017 ms
aggregateBars n=5     1.539 ms   ← 最大單項
movingAverage ×2      0.150 ms
bollinger(全序列)     0.318 ms   ← 只用 700 根卻算 5,900 根
buildCandleGeometry   0.049 ms
────────────────────────────
合計                  2.07 ms / 打包 → 20.7 ms/s
```
再加 2,100–4,230 個節點的 React reconcile。**盤中開著個股頁 K 線分頁 = 每秒穩定燒掉 3–5% 的一顆核心**。

**fix**(三刀,由淺到深):
1. **把正式段與 live 尾巴拆開**:`aggregateBars(raw, n)` 只依 `data` memo(60 s 才換一次),
   live 尾巴另外 `aggregateBars(mergeLiveMinuteBars([], liveMinutes, ...), n)` 再接上去。
   每 0.1 s 只處理尾巴的 ≤271 根 → 1.539 ms → **~0.07 ms**。
   ⚠ 桶界要對齊:live 段的第一個桶可能與正式段最後一個桶同 key,要合併(`aggregateBars`
   的桶邏輯已經處理「同 key 合併」,把正式末桶與 live 首桶再過一次即可)。
2. **MA / BB 只算視窗需要的區間**:`bars.slice(Math.max(0, start - 19), start + count)`
   再算,左緣一樣不斷頭。`bollinger` 0.318 → **0.036 ms**(實測 8.8×)。
3. **`movingAverage` 已是 O(n) 滑動窗**(candle.ts:114-123),不必改演算法,只要縮輸入。

**risk**:`bollinger` 的「中軌用 `Math.floor(mean)` 要與 `movingAverage` 逐根相等」
(bollinger.ts:3-5)必須保住 —— 縮輸入不影響,但**不可**順手改成 Σx²−(Σx)²/n 的一趟法
(檔頭明記:毫元平方後量級 1e11,低波動盤整段會有災難性抵銷)。
`CandleChart.test.tsx` 有 `bb-upper` / `ma-5` 斷言(6 處)。

**effort** M

---

### B1-05 [high / allocation] `aggregateBars` 每根 bar 配置 3 個字串

**location** `frontend/src/lib/candle.ts:70-89`

```ts
for (const b of bars) {
  const { date, minute } = splitStamp(b.t);         // ← 2 次 slice + 2 次 Number
  ...
  const key = `${bucketDate} ${bucketEnd}`;         // ← template literal,每根一個新字串
  if (key !== curKey) {
    cur = { t: stampOf(bucketDate, bucketEnd), ... } // ← padStart ×2 + template,每桶一個
```

`splitStamp`(candle.ts:27-36)每根做 `t.slice(0,sp)` + `t.slice(sp+1)` + 再兩次 `slice(0,2)`/`slice(3,5)`
= **每根 4 個 substring**。6,100 根 → **24,400 個字串配置 + 6,100 個 key 字串**,每 0.1 s 一輪。
這正是 H9 的 1.539 ms 的主要去處(n=1 的純拷貝只要 0.004 ms,差 **385 倍**)。

**fix**:
- `key` 改數值:桶界本來就是 `(日曆日序號 × 1440) + bucketEnd`,用 number 比較,省 6,100 個字串;
- `splitStamp` 改 `charCodeAt` 手解分鐘(不配置 substring),只在真的需要日期字串時 slice;
- 更好:讓 `Bar` 在**進入前端時就帶一個 `m: number`(絕對分鐘)欄位**(後端加欄或 adapter 一次性算),
  之後所有 `splitStamp` / `stampOf` / `alldayIndexOfStamp` / `txf-overlay-series.splitStamp` 都省掉。
  目前**同一個時戳解析在四個檔案各寫一份**:`candle.ts:27`、`txf-overlay-series.ts:46`、
  `allday.ts:197 anchorClassOf`、`allday.ts:181 alldayIndexOfStamp`。

**risk**:`stampOf` 的輸出格式是**跨檔契約的一半**(`live-last-bar.ts` 的
「accum 起點分 +1、上限 13:30」測試以 `"YYYY-MM-DD HH:MM"` 字面比對,9 條測試釘住);
`t` 欄位本身是 wire 契約,**只能加欄不能改欄**。跨日正規化(candle.ts:84-87 的 `while bucketEnd >= DAY_MIN`
+ `shiftDate`)改成數值鍵時要保住「23:56–23:59 與次日 00:00 合併」的行為(SC-2)。

**effort** M

---

### B1-06 [high / allocation] 同一條 `priceLine` 的 `pts()` 在一次 render 內被呼叫兩次

**location** `frontend/src/components/stock/StockIntradayChart.tsx:529-546`

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

`hasRef` 為真(常態)時同一份點串被格式化**兩次**:271 點 = 2 × 0.046 ms + 2 × 3,227 字元;
近全軸 1365 點 = 2 × 0.254 ms + 2 × 16,258 字元。每 tick、每張卡。
50 卡 → 每秒多配置 **~320 KB** 的短命字串(GC 壓力)。

**fix**:`ChartStatic` 函式體頂端 `const linePts = pts(g.priceLine);` 用兩次。**三行改動**。
同理 `CandleChart.tsx:148/154/162` 的 `pts(bbUpperLine)` 被用在 polygon 與 polyline 兩處
(148 那個是 `[...bbUpperLine, ...reverse(bbLowerLine)]`,是另一份,不重複)。

**risk**:零。像素逐點相同(同一函式同一輸入)。

**effort** S

---

### B1-07 [medium / allocation] `buildIntradayGeometry` 每次重建 `haveMinutes` Set,而來源本來就是 Map

**location** `frontend/src/lib/stock-intraday-svg.ts:451`

```ts
const haveMinutes = new Set(entries.map(([k]) => k));
const minuteOf = (xPx: number): number | null => {
  ...
  if (haveMinutes.has(m)) return m;
```

`entries` 來自 `input.minutes`(一個 `Map<number, MinuteAgg>`),而 `Map.has()` 同樣是 O(1)。
這裡多配置一個 271(近全軸 **1365**)元素的中介陣列 **和** 一個同大小的 Set,
**只為了 hover 時的一次 `has` 查詢**——而 hover 在大多數 render(每 tick)根本沒發生。

**fix**:閉包捕 `input.minutes`,判定寫成 `m >= xw.start && m <= xw.end && input.minutes.has(m)`。
省一個 map + 一個 Set 的配置。

**risk**:語意等價需要確認一件事 —— `windowedEntries` 只留窗內的 key,所以 `haveMinutes`
天然只含窗內 key;改用 `minutes.has` 必須自己補窗界判定(上面的寫法已補)。
`stock-intraday-svg.test.ts` 有 `minuteOf` 的 round-trip 測試會守住。

**effort** S

---

### B1-08 [medium / allocation] 幾何無條件產出 `areaPolygon` / `vwapLine` / `energyBars`,toggle 關著也照算

**location** `frontend/src/lib/stock-intraday-svg.ts:406-418`(vwapLine)、`:481-488`(areaPolygon)、`:418`(energyBars)

```ts
const areaPolygon =
  hasRef && priceLine.length > 0
    ? [ `${priceLine[0]!.x.toFixed(1)},${refY.toFixed(1)}`,
        ...priceLine.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`),
        `${priceLine[priceLine.length - 1]!.x.toFixed(1)},${refY.toFixed(1)}` ].join(" ")
    : "";
```

`areaPolygon` 每 tick 產一個 3,250 字元(近全軸 16 KB)的字串 —— 而它只在 `g.hasRef` 為真時
被兩個 `<polygon>` 用(那兩個用的是同一個字串 reference,這半邊沒問題)。
`vwapLine` 在 `toggles.vwap` 關時完全不畫(:521),但幾何照算 271 個點物件 + toY。
`energyBars` 在主圖的 `g` 裡算了一份、`buildEnergyBars` 又算一份 —— **主圖那一份沒有任何讀者**
(`IntradayGeometry.energyBars` 欄位存在,但元件走的是 `subEnergy`;`grep` 全庫只有型別定義與測試用它)。

**fix**:
- `energyBars` / `maxTotal` 從 `buildIntradayGeometry` 的回傳裡拿掉(改由 `buildEnergyBars` 獨佔),
  或至少改成 lazy getter。省一趟 271/1365 的 map。
- `areaPolygon` 與 `vwapLine` 改成 `GeometryOpts` 控制(預設全開 = 零行為改變),
  呼叫端依 `hasRef` / `toggles.vwap` 傳。
- 或更乾脆:B1-13 的 canvas 路線一走,`areaPolygon` 這個字串整個消失。

**risk**:`IntradayGeometry` 是本層的公開介面,拿掉欄位會讓
`stock-intraday-svg.test.ts` / `StockIntradayChart.*.test.tsx` 的 `energyBars` 斷言紅
(這是好事:機械擋住)。`vwapLine` 的 running VWAP 近似(檔頭:Σ close×vol / Σ vol)
是唯一定義處,關掉時不可改算法只能跳過。

**effort** S

---

### B1-09 [medium / algorithmic] 座標轉換每個點都重算 scale

**location** `frontend/src/lib/stock-intraday-svg.ts:79-81`、`:395-402`

```ts
export function minuteToX(minute: number, width: number, xw: XWindow = SPOT_WINDOW): number {
  return Y_AXIS_W + ((minute - xw.start) / (xw.end - xw.start)) * plotWidth(width);
}
export function plotWidth(width: number): number {
  return Math.max(1, width - Y_AXIS_W - R_AXIS_W);   // ← 每次呼叫都重算
}
```

`buildIntradayGeometry` 內 `toX` 被呼叫 **3n 次**(priceLine / vwapLine / energyBars 各一趟),
每次含一次 `Math.max` + 兩次減法 + 一次除法 + 一次乘法。n=1365 → **4,095 次**。
`toY`(:395)同樣每點兩次除法。`minuteToX` 另外在元件端 `hourTicks.map`(:381,×2)、
`XAxisLabels`(:786)、`timeTagX`(:1323)、`buildIndexOverlayLines`(:100,每點)再被呼叫。

**fix**:在 `buildIntradayGeometry` 頂端一次算好
```ts
const pw = plotWidth(size.width);
const kx = pw / (xw.end - xw.start);
const toX = (m: number) => Y_AXIS_W + (m - xw.start) * kx;
const ky = flat ? 0 : plotH / ySpan;
const toY = (p: number) => flat ? PAD_Y + plotH / 2 : PAD_Y + (yTop - p) * ky;
```
⚠ **浮點結果會變**(`(a/b)*c` vs `a*(c/b)`),而 `pts()` 是 `toFixed(1)` → 大多數點不變,
但邊界點可能差 0.1。`stock-intraday-svg.test.ts` 有逐值斷言,要逐條確認。
**若不想冒這個險**,只把 `plotWidth(width)` 的結果提出來當常數即可(純減法,結果逐位元相同)。

**risk**:見上。跨檔契約 `minuteToX` 是「幾何與元件共用這一份」(:76-78 註解)——
**不可**在元件端另寫一份快取版,否則正是那條註解要防的漂移。

**effort** S

---

### B1-10 [medium / render] `CandleChart` 的蠟燭層 700 根 × 3 節點,且 K 線每 0.1 s 重建

**location** `frontend/src/components/stock/CandleChart.tsx:221-240`、`:203-213`

見 B1-03 的 code 引用。與分時圖的差別:K 線的 `MAX_VISIBLE = 700`(candle-viewport.ts:14),
而 `viewport` 每次 `bars.length` 變(每 0.1 s,因為 live 末根)會走 `onTotalChange` → 新 Viewport 物件
→ `useMemo[bars, viewport, ...]` 失效 → `g` 重算 → `CandleChartStatic` 全層重建。

**影響**:2,100(蠟燭)+ 700–2,100(量柱)= **2,830–4,230 節點,每 0.1 s**。
比分時圖單卡重 6–9 倍,只是只有一張。

**fix**:蠟燭收成 4 個 path(up/down/flat body 各一 + wick 各一,`dir` 三值)。
量柱同理。節點 2,830 → **~40**。
另外 `onTotalChange`(candle-viewport.ts:69)在 `wasAtRight` 且 count 不變時應回**同一個物件**
(現在無條件 `clampViewport` 回新物件)→ 加一行 identity 保留就能讓 `useMemo` 在
「只有末根值變、根數沒變」時不重算。

**risk**:`candle-body`(7 處)/ `vol-bar`(15 處)/ `vol-delta-outer`/`inner` 測試斷言。
`onTotalChange` 的 identity 改動要確認 `useCandleViewport` 的 render 期調整 pattern 不受影響。

**effort** M

---

### B1-11 [medium / algorithmic] `bollinger` 對全序列算,結果只用視窗 700 根

**location** `frontend/src/lib/bollinger.ts:19-42` + `components/stock/CandleChart.tsx:483`

```ts
for (let i = 0; i < bars.length; i += 1) {
  if (i < n - 1) { out.push(null); continue; }
  let sum = 0;
  for (let j = i - n + 1; j <= i; j += 1) sum += bars[j]!.c;      // ← 20 次
  const mean = sum / n;
  let sq = 0;
  for (let j = i - n + 1; j <= i; j += 1) { const d = bars[j]!.c - mean; sq += d * d; }  // ← 又 20 次
  ...
}
```
```tsx
const bb = showBb ? bollinger(bars, 20).slice(start, start + viewport.count) : [];
```

O(n × 40) = 5,900 × 40 = **236,000 次運算 + 5,880 個 Band 物件**,`slice` 後丟掉 88%。
實測 0.318 ms vs 只算視窗的 0.036 ms。

**fix**:`bollinger(bars.slice(Math.max(0, start - 19), start + count), 20)`,
前 19 根是為了讓視窗第一根不斷頭。CandleChart.tsx:478-479 的註解已經寫明這個要求
(「MA / BB 以完整序列計算後再裁切,左緣才不會斷頭」)—— 但「完整序列」其實只需要
「視窗 + 前 n−1 根」。

**risk**:`movingAverage` 同理(但它是 O(n) 滑動窗,省的少)。
不可改成一趟法(bollinger.ts:6-7 的數值穩定性理由)。

**effort** S

---

### B1-12 [medium / allocation] `buildVpBars` 每 tick 重排 + 每根兩次 tick 表線性掃

**location** `frontend/src/lib/volume-profile.ts:55`、`:95-96`、`:112`

```ts
const maxTotal = Math.max(1, ...inDomain.map(([, c]) => c.t));   // ← spread + 中介陣列
...
const topMilli = (priceMilli + stepUp(priceMilli)) / 2;          // ← tickOf 線性掃 6 列
const bottomMilli = (priceMilli + stepDown(priceMilli)) / 2;     // ← 再一次
...
bars.sort((a, b) => b.priceMilli - a.priceMilli);                // ← 每 tick 重排 ~100 根
```

`vpBars` 的 useMemo dep 是 `[accum.vp, g, vpEnabled, w]`,而 `accum.vp` 每 tick 是新 Map、
`g` 每 tick 是新物件 → **每 tick 全部重算**。但實際上**價位帶的幾何(y / h)只依賴 `g.yDomain`**,
一整天幾乎不變(有漲跌停時域是 `[lower, upper]`,**恆定**);變的只有 `w`(量的比例)。

**fix**:把 `buildVpBars` 拆成兩半:
- `buildVpSlots(yDomain, toY, priceLevels)` → y / h(以 `yDomain` + 價位集合為 key,幾乎不變);
- 每 tick 只算 `w = (cell.t / maxTotal) * maxW` 與 `poc`。
另外 `maxTotal` 改迴圈(省中介陣列與 spread),`tickOf` 改查表(TICK_TABLE 只有 6 列,
可以改成 `priceMilli >= 1_000_000 ? 5000 : ...` 的三元鏈,或預先把整個域的 step 算成陣列)。
`sort` 可省:`inDomain` 的來源 Map 若改成有序結構就不必每次排。

**risk**:POC 判定的 tie-break(「tie 取較高價位」,volume-profile.ts:62-65)是**決定性契約**
(不決定性會讓 highlight 在畫面上跳動);拆成兩半時 POC 必須留在「每 tick 算」那一半。
`vp-bar` 有 14 處測試斷言。後端 `StockDayState._vp` 折的是同一份規則
(stock-accum.ts:177-178:`foldVp` export 是給後端 parity fixture 用的)—— 改的是**呈現**不是**折法**,不碰那條契約。

**effort** M

---

### B1-13 [medium / architecture] 渲染層改 Canvas 2D 的評估

**location** 整個 `components/*/…Chart.tsx` 的 JSX 部分(幾何層 `lib/*.ts` **不動**)

這套 code 的分層剛好非常適合換渲染後端:

| 已經在幾何層、canvas 不必重寫 | 檔案 |
|---|---|
| 座標映射 `toY` / `priceAtY` / `minuteToX` / `minuteOf` | stock-intraday-svg.ts |
| y 域決策(漲跌停 / autofit / 退化 flat) | stock-intraday-svg.ts:368-401 |
| 刻度 snap 與去重 | stock-intraday-svg.ts:420-449 / candle.ts:300-329 |
| 標籤避讓(1D sweep、obstacles、走廊 A/B) | stock-intraday-svg.ts:614-921 |
| **命中測試(hover)** `minuteOf` / `indexOf` / `toSvgPoint` | stock-intraday-svg.ts:452 / candle.ts:331 / chart-crosshair.ts:35 |
| 極值標記翻面 / 夾制 | chart-extreme.ts |
| 量測 → viewBox 換算 | chart-frame.ts / pane-frame.ts |

**也就是說「失去 hover 要自己算命中測試」這個 canvas 的標準代價,在這個 codebase 是零成本 ——
`chart-crosshair.ts` + `g.minuteOf` + `g.indexOf` 早就在自己算了。**

**收益**:
- 節點數 450/卡 → **1**(一個 `<canvas>`);50 卡 23,000 → **50**。
- 不再產 `pts()` 字串(每 tick 每卡省 3–16 KB × 4 次)。
- 重繪成本從「React reconcile N 個 fiber + 瀏覽器 style recalc N 個 element」
  降成「一次 `clearRect` + N 次 `lineTo`」,量級差 10–50×。
- `devicePixelRatio` 縮放後畫質與 SVG 相同。

**代價 / 風險**(誠實清單):
1. **測試**:`data-testid` 斷言約 **300 處 / 20 個測試檔**(`fill-` 115、`edge-price` 58、
   `day-high` 31、`vol-bar` 15、`y-tick-price` 15、`vp-bar` 14、`index-line` 14、
   `day-low` 14、`chart-hline` 12、`candle-body` 7、`energy-bar` 4、`bb-upper`/`ma-5` 6)。
   canvas 後這些**全部失效**,jsdom 沒有 canvas 實作(要 `vitest` 裝 `canvas` 或 mock context)。
   **這是最大的單一成本,也是最該先談清楚的一條**。
   緩解:把「畫什麼」抽成一個 display list(`{kind:"rect"|"line"|"text", ...}[]` 純陣列),
   測試斷言改對 display list 而不是 DOM —— **純函式測試,比現在的 RTL 斷言更快更穩**,
   而且 canvas renderer 只是 display list 的一個消費者(SVG renderer 可以留著給測試用)。
2. **CSS 語彙全失**:`className="stroke-bull"` / `fill-bull/55` / Tailwind token / dark mode
   都要換成從 CSS custom property 讀色(`getComputedStyle(root).getPropertyValue("--color-bull")`)
   並在主題切換時重繪。`river-colors.ts` 的「調色盤色數 ≥ 腿數」契約(CLAUDE.md §4)
   要改成從 token 讀而不是 class 字面 —— 那條契約的測試
   (`test_river_palette_covers_every_leg` 以**原始碼字面**鎖住)要同步改。
3. **`paintOrder="stroke"` 的 halo**:全庫大量使用(極值文字 / MA 標籤 / POC / 成交點)。
   canvas 對應是 `ctx.strokeText` 再 `ctx.fillText`,可等價。
4. **`clipPath` 的雙色價線**(平盤上紅下綠,StockIntradayChart.tsx:360-373 + 527-543):
   canvas 用 `ctx.save(); ctx.rect(...); ctx.clip();` 等價,且省掉 `useId` 的
   「«r0» 拼進 url(#…) 解析失敗會靜默不繪製」那個坑(:356-359 註解)。
5. **`<title>` tooltip**(chart-hlines 的證據文字):canvas 沒有,要自己做 hover tooltip。
   目前只有 `chart-hline` 一處用。
6. **a11y**:`role="img" aria-label` 仍可掛在 canvas 上;但 SVG 內的 text 目前也不是可選取的,
   實際損失很小。
7. **無障礙 / 列印 / 截圖**:驗證截圖走 `docs/specs/<feature>/screenshots/`(CLAUDE.md §6),
   canvas 一樣截得到。

**建議**:**分兩期**。
第一期(低風險、收益已達八成):B1-02 / B1-03 的「三層收 path」+ B1-01 + B1-06。
節點數 23,000 → 6,500,不動任何測試語彙以外的東西。
第二期(若第一期後仍不夠):抽 display list + canvas renderer,同時把 300 處 DOM 斷言
遷成 display list 斷言。**不要跳過第一期直接做第二期** —— 第一期的量測結果會決定第二期值不值得。

**effort** 第一期 M / 第二期 XL

---

### B1-14 [low / algorithmic] `windowedEntries` 每次拷貝 + 排序,而來源已近乎有序

**location** `frontend/src/lib/stock-intraday-svg.ts:288-292`

```ts
function windowedEntries(minutes: Map<number, MinuteAgg>, xw: XWindow): [number, MinuteAgg][] {
  return [...minutes.entries()]
    .filter(([k]) => k >= xw.start && k <= xw.end)
    .sort(([a], [b]) => a - b);
}
```

三趟:spread 建陣列(271/1365 個 `[k,v]` tuple 物件)、filter 建第二個陣列、sort。
實測 0.012 ms(271)/ 0.064 ms(1365)。而 `accum.minutes` 的插入序來自
「後端 Record 的 key 順序」+「tick 依時間到達」→ **實務上已經是升冪**,sort 幾乎是白做
(但不能拿掉 —— 回補落地時順序無保證)。

同一份工作在一次 render 內做 **兩次**:`buildIntradayGeometry`(:349)與
`buildEnergyBars → energyFrom`(:340)各一次。

**fix**:`accum` 層維護一份已排序的 `readonly [number, MinuteAgg][]`(插入時二分插入,
或標記 dirty 只在需要時排一次),幾何層只做窗切片(二分找端點 + `subarray` 語意)。
或最小改動:`buildIntradayGeometry` 把 `entries` 順便回傳,`buildEnergyBars` 接受它。

**risk**:`windowedEntries` 的窗語意是四處共用的尺(`sideSummary` / `hasWindowedMinutes` /
`foldVp` 的 `X_START_MIN`/`X_END_MIN`),改資料結構時四處都要走同一份。

**effort** M

---

### B1-15 [low / allocation] `Math.max(1, ...arr.map(...))` 的 spread + 中介陣列

**location** `stock-intraday-svg.ts:322`、`:382-383`、`volume-profile.ts:55`、`river-chart-svg.ts:108-109`、`index-chart-svg.ts:105-106`、`pnl-svg.tsx:19-20,26`

```ts
const maxTotal = Math.max(1, ...entries.map(([, m]) => m.o + m.i + m.u));   // :322
const hi = Math.max(ref, ...prices, ...(foldExtremes && dayHigh !== null ? [dayHigh] : []));  // :382
```

每次多配置一個 n 元素陣列並把它整個 spread 成函式參數。n=1365 時是 1,365 個堆疊參數
(V8 安全上限約 64K,不會炸,但 spread 路徑比迴圈慢)。`index-chart-svg.ts:105` 的
`Math.min(0, ...all)` 的 `all` 是**兩條線的所有點**(~540 個)。

**fix**:改單趟迴圈求 max/min。`stock-intraday-svg.ts:322` 的 `entries.map` 可以直接併進
`energyFrom` 的 `bars` 那一趟(目前掃兩遍)。

**risk**:零(純算術等價;`Math.max()` 空參數回 `-Infinity`,迴圈版要保留 `Math.max(1, …)` 的地板)。

**effort** S

---

### B1-16 [low / algorithmic] 極值等值反查每 tick 兩次全掃

**location** `frontend/src/lib/stock-intraday-svg.ts:494-504`

```ts
const markFor = (target, pick) => {
  ...
  const hit = entries.find(([, m]) => (pick === "h" ? m.h : m.l) === target);
  ...
};
const highMark = markFor(dayHigh, "h");
const lowMark = dayLow !== null && dayLow === dayHigh ? null : markFor(dayLow, "l");
```

兩次 O(n) 線性掃(最壞 2×1365)。可與 `priceLine` 那一趟合併(同一個迴圈內順便比對 h/l)。
成本小(~0.005 ms),但「免費」。

**risk**:「等值反查」的語意(反查落空一律回 null 不退而求其次,:490-493)必須保住。

**effort** S

---

### B1-17 [low / algorithmic] `buildIndexOverlayLines` 每卡逐點重算,無法跨卡共用

**location** `frontend/src/lib/index-overlay-lines.ts:87-105`

```ts
for (const { minute, p } of sortedIndexRows(s)) {
  if (minute < xw.start || minute > xw.end) continue;
  const priceMilli = (stockRefMilli * p) / ref;
  if (priceMilli < yBottom || priceMilli > yTop) continue;
  pts.push({ x: minuteToX(minute, width, xw), y: g.toY(priceMilli) });
  lastP = p;
}
```

`sortedIndexRows` 已用 WeakMap 跨卡共用排序結果(F-06 的修法,做得對),但**映射本身是 per-card**
(y 依個股自己的 `ref` 與 `yDomain`),數學上無法共用。50 卡 × 3 線 × 271 點 = **40,650 次**
乘除 + toY + push,每次指數 push(~1 s)+ 每次該卡 tick。

**可以共用的只有 x**:`minuteToX(minute, width, xw)` 對所有卡片**完全相同**(同一個 `w`、同一個 `xw`),
卻被算了 40,650 次。

**fix**:把 x 序列以 `(series, w, xw)` 為鍵快取(第二層 WeakMap / Map),per-card 只算 y。
省掉三分之一的工作。

**risk**:`w` 在圖牆上所有卡相同(`cardSvgBox` 同一個容器寬)但不保證 —— 快取鍵要含 `w`。

**effort** S

---

### B1-18 [low / observability] 這一層完全沒有效能探針

**location** 全區塊

沒有 `performance.mark` / `PerformanceObserver` / 任何 render 計次。
唯一的量測紀錄是註解裡的一次性 jsdom 數字(StockIntradayChart.tsx:812-817 的 N047)。
CLAUDE.md §1 的表提到 `dev-perf-guard` 與 React Component Performance Track,
但那是 dev build 的側面觀察,不是這一層的量化。

**fix**:在 `buildIntradayGeometry` / `buildCandleGeometry` / `aggregateBars` 三個入口
加一個可由 `localStorage` 開關的 `perfCount` 計數器(呼叫次數 + 累計 ms),
`/api/health` 式的 debug 面板印出來。**不加 `performance.mark`**(它本身有成本且會污染 trace)。
見 §8 量測方法。

**effort** S

---

## 5. 逐題回答(任務指定的七個重點問題)

### Q1. 一張分時圖重繪跑多少次運算?

現貨窗 271 分鐘,一次 `buildIntradayGeometry`:
- `windowedEntries`:271 次 filter 比較 + 271 個 tuple 配置 + sort(~271×log271 ≈ 2,200 次比較)
- `prices` map+filter:542 次
- `priceLine` map:271 × (1 次 toX〔含 `Math.max`+2 減+1 除+1 乘〕+ 1 次 toY〔2 減 1 除 1 乘 1 加〕+ 1 物件)
- `vwapLine`:271 × (2 乘 2 加 1 除 1 round + toX + toY + 1 物件)
- `energyFrom`:271 × (2 加) + max spread + 271 × (toX + 1 除 1 乘 + 1 物件)
- `haveMinutes`:271 個 tuple + 271 個 Set entry
- `yTicks`:11 × (snapDown〔tickOf 線性掃 6 列〕+ toY)
- `areaPolygon`:**273 × 2 = 546 次 `toFixed(1)`** + 273 個字串 + join → 3,227 字元
- 兩次 `entries.find` 全掃:最壞 542 次比較

**總計約 2,700 次浮點運算 + ~1,400 個短命物件 + ~550 次字串格式化 = 0.101 ms**。

再加渲染端 `pts(g.priceLine)` × 2 = **1,084 次 `toFixed(1)`** + 2 個 3.2 KB 字串 + `pts(vwapLine)` 542 次。

**所以字串格式化(`toFixed(1)`)佔了這張圖總運算次數的約 40%**,是這一層最大的單項成本。
近全軸(1365)時比例更高:`pts()` 0.254 ms vs 幾何 0.53 ms。

### Q2. 字串串接產生 SVG path 是主要成本嗎?

**是主要成本之一,但不是唯一。** 具體:
- 一條 271 點 polyline 的 `points` 字串 = **3,227 字元**;1365 點 = **16,258 字元**。
- `areaPolygon` 同級(3,250 / 16,3xx 字元)。
- 每次重繪**整條重建**(`pts()` 是 `map().join()`,無增量)。
- 而且 `priceLine` 被格式化 **2 次**(B1-06)。
- 一張卡每 tick 產 ~13 KB 短命字串;50 卡 ~650 KB/tick;指數 push 時 650 KB/s 的 GC 壓力。

**但**:`toFixed(1)` 在 V8 已經相當快(0.046 ms / 542 次 ≈ 85 ns/次),
純字串成本佔一張圖總重繪時間約 30–45%。**節點數(B1-03)的影響比字串大** ——
字串只是 JS 側,節點是 JS + React fiber + 瀏覽器 style/layout/paint 三重。

換 canvas 後這一項**歸零**(`ctx.lineTo(x, y)` 吃 number,不經字串)。

### Q3. 有沒有 memoize?依賴陣列對不對?

**有,而且做得比一般專案好很多。** 逐一檢查:

| memo | deps | 判定 |
|---|---|---|
| `g = buildIntradayGeometry`(:1066) | `[accum.minutes, accum.meta, accum.high, accum.low, w, mainH, xw, snapRadius]` | ✅ 正確且完整(註解明記漏 `mainH` / `xw` 的靜默症狀) |
| `fillMarks`(:1086) | `[fills, g, w, xw, toggles.fills]` | ✅ |
| `subEnergy`(:1094) | `[index, accum.minutes, w, subH, xw]` | ✅ 刻意不含 `meta`(量的幾何不依賴它) |
| `vpBars`(:1110) | `[accum.vp, g, vpEnabled, w]` | ✅ 但見 B1-12(dep 太粗) |
| `oLines`(:1129) | `[overlay, g, toggles.cdp, toggles.ma, cdpAvailable, maAvailable]` | ✅ |
| `pegs`(:1144) | 同上 + `index` | ✅ |
| `idxLines`(:1170) | 九個純量/物件,逐個攤平(不傳整個 `indexSeries` 物件) | ✅ 攤平得很細心 |
| `bars`(StockChart:196) | `[data, mode, liveMinutes, liveDay, dayOpen, liveToday, nowMinute]` | ✅ 正確,但 `liveMinutes` 每 0.1 s 換 → 見 B1-04 |
| `{shown,g,ma5,...}`(CandleChart:475) | `[bars, viewport, showBb, dimW, dimH]` | ✅ 正確,但輸入太大 → 見 B1-04/B1-11 |
| `ma5Line`/`ma20Line`/`bbUpperLine`/`bbLowerLine`(:499-508) | `[ma5, g]` 等 | ✅ |
| `highMark`/`lowMark`(:530-538) | — | ✅(註解 W-3 明記 identity 要求) |

**物件/陣列 identity 的處理是這個 codebase 的強項**:12 個以上模組層空常數
(`EMPTY_HLINES` / `EMPTY_PEGS` / `EMPTY_IDX_LINES` / `EMPTY_ENERGY` / `EMPTY_FILLS` /
`EMPTY_MARKS` / `EMPTY_POSITIONS` / `EMPTY_CODES` / `EMPTY_LINE` / `NOOP_HOVER` /
`SPOT_WINDOW` / `STKFUT_WINDOW` / `ALLDAY_WINDOW`)+ 每個 memo prop 的 doc 都寫明
「必經 useMemo 或模組層常數」。`GroupGridView` 的 `pick = useCallback(latest-ref)` 也是對的。

**唯一真正打穿 memo 的**是 B1-01(`indexSeries` 每秒換 identity 且沒有隔離層)。

**deps 對不對?** 全部對。**問題不在 deps 錯,在「資料真的變了」** —— 每 tick `accum.minutes`
確實是新 Map、確實該重算。要省的是**重算的範圍**(增量)而不是重算的觸發。

### Q4. 座標轉換是不是每個點都重算 scale?

**是。** 見 B1-09。`minuteToX` 每次呼叫重算 `plotWidth(width)`(`Math.max` + 2 減),
`toY` 每次重算 `(yTop - p) / ySpan`(除法沒有提出來)。
n=1365 時 `toX` 被呼叫 4,095 次、`toY` 約 2,730 次 + 刻度/疊線/hover。
影響約佔幾何時間的 15–20%,不是主因但可以省。

`candle.ts` 的 `toY`(:254)同樣每點重算 `(hi - priceMilli) / span * usable`。

`river-chart-svg.ts:88` 的 `toX` 每次呼叫 `span(window)`(含一次 `Math.max`)—— 同病。

### Q5. 產生了多少 SVG DOM 節點?

見 §3.1 的逐項推導。摘要:
- **分時圖一張卡 ~410–500 節點**(其中 `EnergySub` 271 個 rect 佔 55–66%,VP 40–120 個 rect 佔 10–25%)
- **圖牆 50 張卡 ≈ 20,500–25,000 節點**
- **自選上限 150 檔 ≈ 61,500–75,000 節點**
- **K 線圖一張 ~2,830 節點**(內外盤雙柱態 ~4,230)
- 期貨近全軸分時圖一張 **~1,300 節點**(EnergySub 1,140)

任務假設的「600 節點 × 50 卡 = 30,000」與實測推導的 20,500–25,000 同一個量級,**假設成立**。

### Q6. 改 Canvas 2D / WebGL 的評估

見 B1-13 完整評估。**要點**:
- 工作量:**幾何層一行不改**(座標映射 / 命中測試 / 標籤避讓 / y 域決策全部可直接沿用),
  只重寫 `components/*/…Chart.tsx` 裡的 JSX → `ctx` 呼叫。
  `StockIntradayChart.tsx` 的 ChartStatic(~410 行 JSX)→ 約 250 行 canvas draw;
  `CandleChart.tsx` 的 Static(~180 行)→ 約 100 行。
- 收益:節點 23,000 → 50;`pts()` 字串成本歸零;重繪從 React reconcile 變成 `clearRect + path`。
- **「hover 要自己算命中測試」這個代價在這裡是零** —— `chart-crosshair.ts` / `g.minuteOf` /
  `g.indexOf` / `g.priceAtY` 早就在自己算了,SVG 的事件只是拿來取 `clientX/clientY`。
- 真正的代價是 **~300 處 DOM testid 斷言**(20 個測試檔)與 **Tailwind class 語彙全失**。
- **WebGL 不建議**:資料量(271–1365 點 × 50 圖)遠低於 WebGL 的門檻,
  WebGL 的固定開銷(context、shader、文字渲染地獄)在這個規模是純負擔。

### Q7. 圖表庫選項評估(針對既有契約)

| 庫 | 技術 | 對本專案的判定 |
|---|---|---|
| **lightweight-charts**(TradingView) | canvas,~45 KB | **不建議整套換**。它的 API 是「給我 bars,我畫」——而本專案的價值全在「y 域恰為 [跌停,漲停] 不留邊」「極值等值反查落空就不畫」「域外疊線改右緣掛牌」「走廊 A/B 雙軌標籤避讓」「VP 帶以成交價置中且端點取相鄰合法檔位中點」這些**規則**上。它的 priceScale 不支援「域恰為 [lower, upper]」、series 不支援 VP 水平長條、標籤避讓完全沒有。硬套的結果是把 921 行幾何搬成 1,200 行 adapter 再加一堆 `createPriceLine` hack。**唯一值得考慮的用法**:只拿它畫 `CandleChart`(K 線 + 量 + MA/BB 是它的原生強項),分時圖維持自繪。但那會讓 `chart-extreme.ts` / `chart-hlines.ts` 的「兩張圖共用同一套規則」契約破掉(那支檔頭明記:兩張圖各寫一份會讓規則各自漂移)。 |
| **uPlot** | canvas,~40 KB | **有條件推薦當 renderer**。它最接近「只負責畫,不管語意」:`series` 吃 `[xs, ys1, ys2…]` 的平行陣列,scale 可完全自訂(`scales.y.range` 可以直接給 `[lower, upper]`),`hooks.draw` 可以插入任意自繪(VP 長條 / 極值標記 / 標籤避讓全部可以在 hook 裡用本專案既有的幾何函式畫)。缺點:它自帶 x/y 軸與 legend(要關掉或客製)、它的 `cursor` 命中測試與本專案的 `minuteOf`(含 snapRadius)語意不同(要關掉走自己的)。**等於「用它的 canvas 管線 + 自己的全部語意」——那與 B1-13 的自寫 canvas 差別不大,多的是 40 KB 與一層 API 學習成本。** 判定:**除非需要它的縮放/平移體驗,否則自寫 canvas 更省**。 |
| **visx** | **SVG** | **不建議**。它是 D3 的 React 封裝,輸出仍是每圖元一個 SVG 節點 —— **完全不解決本區塊最大的問題(B1-03 節點爆炸)**,只是把手寫的 `<rect>` 換成 `<Bar>`。 |
| **ECharts** | canvas | **不建議**。1 MB+ 的 bundle(現在整個 app 的 runtime deps 只有 5 個套件)、option-model 驅動(所有幾何規則要翻譯成 option,而很多翻譯不出來)、且它自帶的 tooltip/legend/theme 與 Tailwind token 體系衝突。遷移成本最高、契約風險最大。 |
| **自寫 Canvas 2D** | canvas,0 KB | **推薦(第二期)**。見 B1-13。 |

**契約遷移成本逐條**(不論選哪個庫都要面對):

| 契約(CLAUDE.md §4) | 影響 | 處置 |
|---|---|---|
| 期貨 CDP/MA 前後端同式 + `tests/fixtures/overlay_parity.json` | `futures-overlay.ts` 是**計算**不是渲染 → **不受影響** | 不動 |
| 台指期疊線分鐘鍵 = 1K 終點標記 −1 分 | `txf-overlay-series.ts` 是計算 → 不受影響 | 不動 |
| 個股頁即時末根分鐘鍵 = accum 起點分 +1、上限 13:30 | `live-last-bar.ts` 是計算 → 不受影響 | 不動 |
| 日 K 定稿界 14:00 前後端 parity | `StockChart.tsx` 的閘 → 不受影響 | 不動 |
| 江波圖調色盤色數 ≥ 腿數(`river-colors.ts` 三組 class + `--color-river-N` token) | **受影響**:canvas 讀不到 Tailwind class,要改讀 CSS custom property | `test_river_palette_covers_every_leg` 以原始碼字面鎖住,要同步改成鎖 token |
| `pts()` 一律 `toFixed(1)`(svg-points.ts:1「各圖精度須一致」) | **消失**:canvas 不經字串 | `stock-intraday-svg.test.ts` 的 `areaPolygon` 字面斷言要改 |
| viewBox 1:1 像素語彙(`cardSvgBox` / `paneIntradayBox` / `paneCandleBox` / `svgBox`) | **受影響**:canvas 要 `width = px * dpr` + `ctx.scale(dpr, dpr)` | 好消息:1:1 語彙讓這件事**最簡單**(等比縮放的 `paneUnitScale` 路徑只剩 OverlayCard 一個讀者) |
| `EnergySub` 不可用「總量當資料版本」做 memo key | 仍然成立 | 不動 |
| z-order 由文件順序決定(多處註解) | canvas 也是「畫的順序 = 疊的順序」,**語意完全一致** | 反而更直觀 |

---

## 6. 工具選型建議(彙總)

### 建議導入

| 工具 / 手法 | 用在哪 | 為什麼 | 代價 |
|---|---|---|---|
| **單一 `<path>` 取代 N 個 `<rect>`/`<line>`** | `EnergySub` / `vp-bars` / `candles` / `volBars` | 零依賴、節點數降一個量級、測試改動可控(40 處) | 測試斷言改寫;path `d` 的可讀性差 |
| **外部 store + `useSyncExternalStore`** | `indexSeries` 下沉(B1-01) | React 18+ 內建,零依賴;把「每秒全牆重繪」變成「每秒 300 節點」 | 需要一個小 store(~40 行);`indexlines` 測試改 |
| **display list 中介層** | 幾何層與渲染層之間 | 讓 SVG / canvas 兩種 renderer 共存,測試對 display list 斷言(純函式、比 RTL 快 10×) | 多一層抽象;要一次性遷 ~300 處斷言 |
| **Canvas 2D renderer**(自寫) | 第二期,見 B1-13 | 節點 23,000 → 50 | 見 B1-13 代價清單 |

### 有條件導入

| 工具 | 條件 |
|---|---|
| **uPlot** | 只有在「需要它的縮放/平移/游標體驗」時才值得那 40 KB 與 API 學習;否則自寫 canvas 更省。要用的話,只用它的 `hooks.draw`,語意全部走本專案既有幾何函式。 |
| **OffscreenCanvas + Worker** | 圖牆 150 檔且 canvas 化之後仍卡才考慮。50 張 OffscreenCanvas transferControlToOffscreen 到一個 worker,主執行緒只送 accum diff。Windows + Chrome 支援良好。**現在做是過早最佳化**。 |
| **`react-window` / 虛擬化** | 圖牆超過 16 檔時走 `h-56` + `overflow-y-auto`(GroupGridView.tsx:474),**畫面外的卡仍然全部 render + 收 tick**。150 檔時畫面上最多看得到 ~12 張。虛擬化能直接砍 90% 的工作 —— 但要先確認「使用者是不是真的會捲」;若他只看 ≤16 檔,這是純負擔。 |

### 不建議

| 工具 | 原因 |
|---|---|
| **visx** | 仍是 SVG,不解決節點爆炸 |
| **ECharts** | bundle 1 MB+、option-model 吃不下本專案的幾何規則、與 Tailwind token 衝突 |
| **lightweight-charts(整套)** | 見 §5 Q7;會破掉「兩張圖共用同一套規則」的既有契約 |
| **WebGL / regl / PixiJS** | 資料量遠低於門檻,固定開銷與文字渲染成本是純負擔 |
| **d3-scale / d3-shape** | 本專案的 scale 已經是 8 行純函式且帶了 y 域決策邏輯;引入 d3 只會多一層而不會更快 |

---

## 7. 不要動的地方

1. **`chart-crosshair.ts`(43 行)/ `chart-frame.ts`(100)/ `pane-frame.ts`(173)/
   `time-labels.ts`(31)/ `spot-session.ts`(14)/ `timeframe.ts`(73)/ `candle-viewport.ts`(73)**
   —— 全部是常數與 O(1) 換算,在熱路徑上的成本是零。這些檔的註解密度極高(每個數字都有出處),
   動它們的期望收益是 0、風險是版面契約漂移。
2. **`pnl-svg.tsx`** —— TXO payoff 曲線,隨部位變(低頻)。`interpCurve` 的 O(n) 線性搜尋
   與 `xDomain` 被算兩次都是真的,但每分鐘跑不到一次。**過度工程,不要動**。
3. **`bollinger.ts` 的直算法** —— 檔頭明記「不用 Σx²−(Σx)²/n 的一趟法:毫元價位平方後量級
   1e11,一趟法在低波動盤整段會有災難性抵銷」。**為了效能改成一趟法 = 用正確性換速度**。
   要快就縮輸入(B1-11),不要改算法。
4. **標籤避讓全家**(`layoutEdgeLabels` / `yieldToObstacles*` / `pegLabels` / `bandLabels` /
   `edgePriceLabels` / `labelWidth` / `spansOverlap` / `vwapLabelBox`)—— n ≤ 9,
   兩趟 sweep,總成本 < 0.01 ms。而這些函式的每一行都在修一個「畫得出來但位置錯」的靜默 bug,
   註解裡記著實測到 0.15px 的細節。**碰它們只會把已經修好的疊字 bug 放回來**。
5. **已經做過的三個優化**:`hasWindowedMinutes` 早退、`buildEnergyBars` 拆分、
   `sortedIndexRows` 的 WeakMap、`sideSummary` 在 card 變體跳過。**不要為了「統一」把它們收回去**。
6. **`memo` prop 的「必經模組層常數」紀律與那 12 個空常數** —— 看起來冗贅,
   實際上是唯一擋住「每秒全牆重繪」的東西。
7. **`allday.ts` 的段表推導**(`ALLDAY_SEGMENTS` → `ALLDAY_LEN` / `ALLDAY_GAP` / `ALLDAY_TICKS`
   / `ALLDAY_WINDOW` / `ALLDAY_HOUR_TICKS` 全部由段表 derive)—— 模組載入時算一次,零熱路徑成本,
   且「offset 由前段累加,段長改動自動傳導」正是防止 1139 → 1365 那種漂移的機制。
8. **`river-chart-svg.ts`** —— 江波圖 11 腿 × 窗內分鐘,但只在相關係數頁;
   `spreadLabelYs` / `timeTicks` / `offsetAtX` 都是 O(n) 小量。**頻率不夠高,不值得動**。

---

## 8. 量測方法(要證明這裡快或慢,該怎麼量)

### 8.1 離線微基準(已做,可重跑)

```powershell
node "C:\Users\USER\AppData\Local\Temp\claude\C--side-project-copycat\2f320e31-68fc-4cfd-859c-b63b666e7f79\scratchpad\arch-scan\bench-svg.mjs"
node "C:\Users\USER\AppData\Local\Temp\claude\C--side-project-copycat\2f320e31-68fc-4cfd-859c-b63b666e7f79\scratchpad\arch-scan\bench-candle.mjs"
```
兩支都是**複刻**版(不 import repo)。要量真實版,把 lib 檔用 `tsx` / `esbuild-register` 直接 import 即可。

### 8.2 真實瀏覽器 profile(最重要的一步,目前完全沒做過)

**前提**:`npm run build && npm run preview`(port 4173),**不要用 `npm run dev`** ——
dev build 的 props-diff 開銷會污染數字(CLAUDE.md §1 表已明記)。

用 chrome-devtools MCP:
```
performance_start_trace(reload=false, autoStop=false)
  → 切到群組檢視、開 60 s(先關指數 toggle 量 baseline,再開三顆量對照)
performance_stop_trace()
performance_analyze_insight(...)
```
**要看的三個數字**:
1. **Scripting 佔比**:baseline vs 指數 toggle 開啟後的差(預期 +14 ms/s @50 卡);
2. **Recalculate Style / Layout 的節點數**:DevTools 的 "Elements affected";
3. **Long tasks(>50 ms)計數**:09-03 的實測紀錄是「trace 93 s,>50ms = 0」(memory
   `group-grid-ticks-shipped`),那是**逐筆打包**那一輪的判準 —— 這次要在**指數 toggle 開啟**
   的條件下重跑,因為那個判準當時沒覆蓋 B1-01。

### 8.3 節點數直接量(五秒可得,最便宜的證據)

在 preview 的 console:
```js
document.querySelectorAll('svg *').length            // 全頁 SVG 節點總數
document.querySelectorAll('[data-testid="energy-bar"]').length   // 量柱
document.querySelectorAll('[data-testid="vp-bar"]').length       // VP
document.querySelectorAll('[data-testid="candle-body"]').length  // 蠟燭
```
在群組檢視(50 檔)跑一次,驗證 §3.1 的推導(預期 20,000–25,000)。
**這一條應該先做** —— 它是 B1-01/02/03 三條 finding 的共同前提。

### 8.4 React 重繪計次(驗證 B1-01)

不裝 profiler,用最便宜的方法:在 `GroupCard` 內加一行
```ts
if (localStorage.getItem("perf") === "1") console.count(`GroupCard ${code}`);
```
開 60 s 後看 console:若 50 個 code 各 ~60 次 → B1-01 成立(每秒一次全牆);
若只有幾個 code 有計數 → memo 有擋住,B1-01 不成立(需重新檢查 `indexSeries` 的傳遞路徑)。
**這是 B1-01 唯一需要的證據,做完再決定要不要改。**

### 8.5 改動後的對照判準

每一條 finding 的驗收:
- B1-01:8.4 的計次從「50×60」降到「只有收到 tick 的卡」;
  8.2 的 Scripting 在指數 toggle 開/關之間的差 < 2 ms/s。
- B1-02/03:8.3 的 `svg *` 總數從 ~23,000 降到 ~6,500。
- B1-04/05/11:8.1 的 `bench-candle.mjs` 從 2.07 ms 降到 < 0.3 ms;
  真實環境用 4.4 的計次法在 `CandleChart` 內計 `useMemo` 執行次數。
- B1-06:`pts` 呼叫次數減半(在 `svg-points.ts` 加臨時計數器)。
- **回歸閘**:`npm test`(vitest,3,069 條)+ `npx tsc -b` + `npx eslint src` +
  `npx react-doctor@latest --scope changed --no-telemetry` 全綠(CLAUDE.md §1)。
  **像素回歸**:改幾何前後各截一張同一檔同一時刻的圖對照(B1-09 的浮點順序改動必做這一步)。

---

## 9. 開放問題

1. **使用者實際開幾張卡、開不開指數疊線?** B1-01 的嚴重度完全取決於這個。
   若平常只開 ≤12 檔且不開指數疊線,B1-01 從 critical 降到 low。
2. **`npm run preview` 常駐時的真實 CPU 佔用是多少?** 完全沒有紀錄。
   在量之前,B1-04(20.7 ms/s)是「算出來的」不是「觀察到的」。
3. **300 處 DOM testid 斷言要不要遷成 display list 斷言?** 這是 canvas 路線的守門條件,
   是**決策**不是事實 —— 要 user 拍板。
4. **圖牆超過 16 檔時,使用者會不會真的往下捲?** 決定虛擬化值不值得。
5. **K 線的 `MAX_VISIBLE = 700` 是不是還需要?** 它是「viewBox 寬 1400 ÷ 700 = 2px/根」
   的保護(candle-viewport.ts:5-6)。canvas 化之後這個上限可以放寬 —— 但那是功能決策。
6. **`IntradayGeometry.energyBars` 真的沒有讀者嗎?** 我 grep 到的只有型別定義與測試;
   拿掉前要確認 `MarketPane` / `FuturesChart` / `RiverPanel` 沒有間接用到。
7. **浮點順序改動(B1-09)可接受嗎?** `pts()` 是 `toFixed(1)`,大多數點不變,
   但 `stock-intraday-svg.test.ts` 有逐值斷言 —— 要先跑一次看紅幾條再決定做不做。
