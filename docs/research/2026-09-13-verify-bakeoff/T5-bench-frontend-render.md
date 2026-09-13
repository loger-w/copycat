# T5-bench-frontend-render —— 前端繪圖擂台(真瀏覽器實測)

- 日期:2026-09-13
- 對象:copycat 前端分時圖 / K 線 / 群組圖牆的繪製方案
- **所有數字都是真瀏覽器(headed Chrome 152)實測**,不是 jsdom、不是純 JS 微基準
- 硬紀律遵守:repo 零改動、未碰 `C:/side-project/copycat/.venv`、未起 server、未下單

---

## 0. 一句話結論

> **以「50 張卡、每 0.1 秒更新、要即時看盤」這個場景:canvas 2D(手刻)與 uPlot 並列第一,
> 兩者主執行緒佔用 ≈ 9.5–11.3 ms/拍,對比現況手刻 SVG 的 56.8 ms/拍 = 5.0–6.0 倍。
> 但因為 canvas 2D 版本畫的是**完整語彙**(VP 長條 / 面積填色 / 現價圈 / 副圖量柱 / 雙刻度),
> 而 uPlot 版本畫的**比較少**,同樣快的前提下 canvas 2D 才是該選的那一個。**
>
> 零相依的中途站:**EnergySub + VP 改單一 `<path>`**,不換繪製技術、幾何層一行不動,
> 就從 56.8 → 26.1 ms(2.2 倍),而且是 repo 自己 next-time 已經寫下的修法。

---

## 1. Setup(可重現)

### 1.1 專案與版本

拋棄式 vite + React 19 專案(**未碰 repo 的 `frontend/node_modules`**):

```
C:\Users\USER\AppData\Local\Temp\claude\C--side-project-copycat\2f320e31-68fc-4cfd-859c-b63b666e7f79\scratchpad\verify-bakeoff\T5\
```

| 套件 | 版本 |
|---|---|
| node | v24.13.0 / npm 11.6.2 |
| react / react-dom | 19.3.0 |
| vite | 6.4.3 |
| @vitejs/plugin-react | 4.7.0 |
| typescript | 5.8.3 |
| **uplot** | **1.6.32** |
| **lightweight-charts** | **5.2.1** |
| jsdom(僅做對照組) | 最新 / vitest 5.0.0 |

安裝耗時 8 秒,零失敗。`npx tsc --noEmit` 全綠、`npx vite build` 全綠。

### 1.2 執行環境(實測記錄)

```
Chrome/152.0.7977.84  (headed,非 headless)
UA: Mozilla/5.0 (Windows NT 10.0; Win64; x64) … Chrome/152.0.0.0
devicePixelRatio = 1
viewport = 1664 × 905
navigator.hardwareConcurrency = 16
閒置 rAF 間隔 p50 = 16.70 ms(→ 60 Hz 螢幕;這是 frame 指標的地板)
Chrome flags: --disable-background-timer-throttling --disable-renderer-backgrounding
              --disable-backgrounding-occluded-windows --enable-precise-memory-info
```

### 1.3 檔案清單(benchmark 腳本 + 原始輸出)

| 用途 | 絕對路徑 |
|---|---|
| 資料形狀產生器(毫元整數、分鐘聚合、VP、K 線) | `…\T5\src\data.ts` |
| 幾何層(逐條對照 repo `stock-intraday-svg.ts` / `volume-profile.ts` 移植) | `…\T5\src\geom.ts` |
| SVG renderer(現況 rect 版 / 單一 path 版 / 降採樣版 / 只畫副圖版) | `…\T5\src\svg.tsx` |
| canvas 2D renderer(全語彙 + 只畫副圖) | `…\T5\src\canvas.ts` |
| uPlot / lightweight-charts wrapper | `…\T5\src\libs.ts` |
| 測試頁 harness(`window.__bench`) | `…\T5\src\main.tsx`、`…\T5\index.html` |
| **自寫 CDP client + devtools.timeline self-time 桶化** | `…\T5\cdp.mjs` |
| 擂台 runner | `…\T5\run.mjs` |
| 記憶體 runner(GC 後量 heap) | `…\T5\memrun.mjs` |
| bundle 體積探針 | `…\T5\sizeprobe.mjs` |
| jsdom 對照組(同一份元件碼) | `…\T5\src\jsdom-bench.tsx` |
| **原始輸出 run2(完整 38 場)** | `…\T5\results-run2.json` |
| **原始輸出 run3(重複性確認)** | `…\T5\results-run3.json` |
| **原始輸出 run1(早期,8 欄版面)** | `…\T5\results-run1.json` |
| **記憶體原始輸出** | `…\T5\results-mem.json` |
| 兩輪平均(headline 用) | `…\T5\consolidated.txt` |
| **每場視覺健檢截圖(38 張 PNG)** | `…\T5\shots\` |

### 1.4 真實資料形狀(取自 repo)

| 形狀 | 來源 | 本擂台用值 |
|---|---|---|
| 分時圖現貨窗 | `stock-intraday-svg.ts::SPOT_WINDOW`(09:00–13:30) | **271 格** |
| 分時圖近全軸窗 | 期貨分時全日 | **1140 格** |
| 卡片尺寸 | `_MISSED-143.md` 查核值(卡片 ~246 寬) | **246 × 250**,`plotWidth = 246−36−40 = 170` |
| 卡片量柱寬 | `barW = max(1, 170/270 − 0.4)` | **clamp 成 1px、間距 0.63px** ← 上一輪指出的退化重疊,本擂台**逐字複現** |
| K 線 | `candle-viewport.ts::MAX_VISIBLE` | **700 根** |
| 日 K | `useStockBars.ts::MINUTE_DAYS`/長歷史 | **5900 根** |
| 圖牆 | `GroupGridView` 常態 | **50 張卡** |
| 每筆 tick 造新 Map | `stock-accum.ts:427 new Map(acc.minutes)` | **逐字複現**(這正是 EnergySub memo 被打穿的來源) |
| 主副高度比 | `chart-frame.ts::MAIN_RATIO_NUM/DEN = 260/330` | 逐字複現 |

視覺健檢:`shots\C-wall50-svg-rect.png` 與 `shots\C-wall50-canvas.png` / `C-wall50-svg-path.png`
三者畫面**逐格對得上**(走勢線 / VWAP / VP 長條 / 面積填色 / 現價圈 / 11 條價位刻度 /
整點時間標籤 / 副圖量柱 + 雙量刻度),證明對決的是同一張圖,不是拿少畫的比多畫的。

---

## 2. 量測方法:Scripting / Rendering / Painting 怎麼分開的

上一輪的教訓是「所有前端數字都是純 JS 微基準,分不出三段,而排序恰恰取決於後兩者」。
本輪的做法:

1. **自寫 CDP client**(`cdp.mjs`,零相依,用 Node 24 內建 `WebSocket` / `fetch`),
   對真 Chrome 下 `Tracing.start`,categories =
   `devtools.timeline` + `disabled-by-default-devtools.timeline` +
   `disabled-by-default-devtools.timeline.frame` + `blink.user_timing` + `__metadata`。
2. 收 `Tracing.dataCollected` 的原始 trace events,**按 thread 建父子堆疊算 self-time**
   (`dur` 扣掉直接子事件的 `dur`),避免父子重複計 —— 這就是 DevTools Performance panel
   Summary 那個圓餅的算法。
3. 事件名 → 桶:
   - **Scripting**:`FunctionCall` / `EvaluateScript` / `TimerFire` / `FireAnimationFrame` /
     `RunMicrotasks` / `EventDispatch` / 所有 `V8.GC*` / `BlinkGC*`
   - **Rendering**:`Layout` / `UpdateLayoutTree`(= Recalculate Style)/ `PrePaint` /
     `UpdateLayerTree` / `HitTest` / `Layerize` / `InvalidateLayout`
   - **Painting**:`Paint` / `PaintImage` / `RasterTask` / `Commit` / `CompositeLayers` / `UpdateLayer`
   - 其餘落 `other`(主要是 `RunTask` 的殘量)
4. 只取 `CrRendererMain` 這條 thread 當主指標;`Compositor` / `TileWorker` 另外算成 raster。
5. 同時保留**頁內同步量測**當交叉驗證:
   `script` = `flushSync(setState)` 或同步繪圖呼叫的牆鐘;
   `layout` = 緊接著一次 `getBoundingClientRect()` 強制 flush 的牆鐘。

**這兩把尺互相驗證**:canvas 模式頁內 `script` p50 = 6.6 ms、trace 的 main scripting = 8.4 ms
(差值是同步路徑外的 GC / rAF);uPlot 模式頁內 0.9 ms 但 trace 7.7 ms ——
**uPlot 把重繪延到 rAF**,所以頁內同步尺看不到它,只有 trace 尺量得到。
→ **本報告的排名一律用 trace 的「main thread 每拍總量」,頁內同步尺只當佐證。**

每場:`setup` → 暖機 6 拍(不計)→ trace 中跑 **40 拍、每拍間隔 100 ms**(= 題目的 0.1 s 場景)。
run2 / run3 兩輪獨立重跑,**headline 場景兩輪差異 < 6%**。

---

## 3. 對決 1 + 2 + 3 —— 圖牆 50 卡 × 271 格,每 0.1 秒全部更新最後一根

這是題目指定的主場景。表中 `main/拍` = CrRendererMain 每一拍的 self-time 總和(run2/run3 平均)。

| 方案 | DOM 節點 | Scripting | Rendering | Painting | other | **main/拍** | raster/拍 | 倍數 vs 現況 |
|---|---|---|---|---|---|---|---|---|
| **svg-rect(現況)** | **18,645** | 34.31 | 17.03 | 5.74 | 1.30 | **56.83 ms** | 1.87 | 1.00× |
| svg-downsample(量柱降到 170) | 13,595 | 28.28 | 13.25 | 5.71 | 1.05 | **46.72 ms** | 1.59 | 1.22× |
| **svg-path(量柱 + VP 併單一 `<path>`)** | **3,009** | 20.09 | 3.46 | 1.67 | 1.06 | **26.08 ms** | 0.75 | **2.18×** |
| lightweight-charts(整份 setData) | 1,209 | 25.28 | 0.87 | 3.72 | 1.24 | **30.44 ms** | 1.33 | 1.87× |
| lightweight-charts(官方增量 `update()`) | 1,209 | 14.42 | 0.93 | 4.95 | 1.19 | **20.67 ms** | 1.26 | 2.75× |
| **canvas 2D(手刻,全語彙)** | **209** | 8.43 | 0.21 | 0.13 | 2.27 | **11.27 ms** | 0.50 | **5.04×** |
| **uPlot** | 809 | 7.71 | 0.25 | 0.14 | 1.44 | **9.48 ms** | 0.54 | **5.99×** |

頁內同步尺(佐證,p50 / p95,單位 ms):

| 方案 | script p50 | script p95 | layout p50 | 到下一幀 p50 |
|---|---|---|---|---|
| svg-rect(現況) | 30.6 | **41.7** | 11.7 | 53.5 |
| svg-downsample | 24.8 | 39.0 | 9.2 | 44.6 |
| svg-path | 17.5 | 23.1 | 2.3 | 25.1 |
| lwc(setData) | 8.8 | 11.7 | 0 | 28.2 |
| lwc(update) | 1.0 | 1.5 | 0 | 18.9 |
| canvas 2D | 6.6 | 9.4 | 0 | 13.1 |
| uPlot | 0.9 | 1.2 | 0 | 10.7 |

### 讀法(重要)

1. **現況已經吃掉 57% 的 0.1 s 預算**,p95 的純 scripting 就 41.7 ms,再加 rendering
   17 ms —— 開盤那種「50 檔一半以上都在動」的拍次,**一拍就是一個掉幀**。
   「到下一幀」53.5 ms ÷ 16.7 ms = 主執行緒吃掉 3 個 vsync。
2. **Rendering 是 SVG 專屬的稅**:svg-rect 17.03 ms(= `UpdateLayoutTree` 重算 18,645 個
   SVG 元素的樣式 + `Layout`),canvas / uPlot / lwc 只有 0.2–0.9 ms。
   **這一段在上一輪的純 JS 微基準裡完全看不見** —— 它佔現況總成本的 30%。
3. **Painting 不是瓶頸**,連 SVG 都只有 5.7 ms。所以「換 canvas 會贏在 painting」是錯的直覺:
   **canvas 贏在把 Rendering 歸零、把 Scripting 砍 4 倍**。
4. **uPlot 的頁內 script 0.9 ms 是假象** —— 它把重繪延到 rAF。trace 尺揭穿之後,
   uPlot(9.48)與手刻 canvas(11.27)差距只有 19%,而且 **uPlot 那 19% 是靠少畫東西換的**
   (見 §8 保真度)。

---

## 4. 對決 4 —— EnergySub 的退化:降採樣 vs path 化 vs canvas

把副圖那一層單獨拉出來(50 卡 × 271 根量柱,卡片 246 寬 → 繪圖區 170px、量柱 clamp 成 1px、
間距 0.63px,**完全是上一輪指認的退化重疊繪製**)。

| 方案 | 節點數 | Scripting | Rendering | Painting | **main/拍** | 降幅 | 保真度 |
|---|---|---|---|---|---|---|---|
| **271 根 `<rect>`(現況)** | 13,959 | 26.97 | 13.73 | 3.55 | **44.99 ms** | — | 基準 |
| **降採樣到 170 根 `<rect>`** | 8,909 | 19.10 | 9.28 | 2.32 | **31.20 ms** | −31% | **失真**(桶內取 max) |
| **單一 `<path>`(271 根形狀不變)** | 459 | 11.82 | 2.22 | 0.59 | **14.42 ms** | **−68%** | **逐像素相同** |
| **canvas 2D** | 209 | 5.54 | 0.16 | 0.10 | **6.84 ms** | **−85%** | 逐像素相同 |

### 這一格是本輪最重要的反直覺結果

**降採樣是最差的一條路**:它砍掉 37% 的節點,只換到 31% 的成本,**卻要付出資料失真的代價**
(桶內取 max 之後,「這一分鐘的量」不再是這一分鐘的量;而 repo 的副圖刻度值
`maxTotal` 是資訊列「量」的對照物,失真等於讓兩處對不上)。

原因很清楚:**成本不在「畫 1px 的矩形」,在「React 對 N 個元素做 reconcile + N 次 DOM 屬性寫入
+ Blink 對 N 個元素重算樣式」**。N 從 271 降到 170 只是同一條線性曲線上往左挪一格;
path 化是把 N 降到 1,才改變了量級。

→ **「降採樣到 170 格」這條建議應該撤回。** 要留 SVG 就 path 化,要更快就 canvas。

---

## 5. 對決:不同更新密度(同 50 卡)

真實盤中不會每一拍 50 檔全動。三種密度:

| 方案 | 50/50 動 | 25/50 動 | 2/50 動 |
|---|---|---|---|
| svg-rect(現況) | 56.83 | 29.30 | **5.10** |
| svg-downsample | 46.72 | 21.66 | —— |
| svg-path | 26.08 | 12.52 | 3.22 |
| lwc(update) | 20.67 | 10.45 | 2.12 |
| canvas 2D | 11.27 | 5.04 | 1.27 |
| uPlot | 9.48 | 5.85 | 1.21 |

**冷門時段(2/50 動)連現況都只要 5.1 ms** —— 而且注意它的組成:scripting 只有 1.66 ms,
**rendering 卻有 2.16 ms**。18,645 個節點光是「存在」就讓每一次樣式重算都要走一遍樹。
這正是「節點數是常駐稅,不是只有更新時才付」的證據。

---

## 6. 對決:單檔頁 271 格 / 期貨分時 1140 格(單張大圖)

| 方案 | A:1 張 × 271(1100 寬) | B:1 張 × 1140(1100 寬) |
|---|---|---|
| svg-rect(現況) | **1.52 ms**(節點 386) | **8.35 ms**(節點 1,319) |
| svg-path | 1.29 ms(節點 69) | **2.83 ms**(節點 97) |
| canvas 2D | 1.32 ms(節點 13) | 1.20 ms(節點 13) |
| uPlot | 0.85 ms(節點 25) | 1.21 ms(節點 25) |
| lwc(setData) | 1.74 ms | 2.82 ms |
| lwc(update) | 1.28 ms | 1.60 ms |

**單檔頁(271)現況完全沒有問題**:1.52 ms/拍,換任何東西都只省不到 1 ms。
**repo 的 N047「量測後留原樣」對單檔頁是正確判斷。**

**期貨分時(1140)現況 8.35 ms/拍**,其中 rendering 2.23 ms。還在預算內,
但 path 化就掉到 2.83 ms(2.9 倍),且 path 化的節點數 1,319 → 97。

---

## 7. jsdom vs 真瀏覽器 —— 上一輪教訓的正面回答

**完全同一份元件碼**,只換 DOM 實作(`src/jsdom-bench.tsx`,vitest environment=jsdom)。
比的是同一把尺:`flushSync(setState)` 的同步牆鐘 p50。

| 場景 | jsdom p50 | 真 Chrome p50(同步尺) | **jsdom / Chrome** |
|---|---|---|---|
| 1 張 × 271 svg-rect | 5.51 ms | 0.6 ms | **9.2×** |
| **1 張 × 1140 svg-rect** | **13.09 ms** | **4.0 ms** | **3.3×** |
| 1 張 × 1140 svg-path | 1.54 ms | 1.6 ms | **0.96×(一樣快)** |
| 50 卡 × 271 svg-rect | 207.8 ms | 30.6 ms | **6.8×** |
| 50 卡 × 271 svg-path | 46.2 ms | 17.5 ms | **2.6×** |

首繪:jsdom 50 卡 mount 367.9 ms vs 真 Chrome 74.7–77.8 ms(4.8×)。

### 結論(三條,都推翻或修正了既有記載)

1. **repo `StockIntradayChart.tsx` N047 註解的「jsdom 量到滿窗一輪 ~15 ms」複現成功**
   —— 我量到 13.09 ms,同一個形狀(1140 根 rect、一張圖)。
2. **但註解接著寫的「真瀏覽器的 diff 快一個量級」是高估的:實測只快 3.3 倍,不是 10 倍。**
   真瀏覽器該場景的同步成本是 4.0 ms,trace 主執行緒總量 8.35 ms。
3. **更關鍵:N047 的那句安慰從來沒涵蓋圖牆。** 同一層在 50 卡下,
   真瀏覽器要 26.97 ms scripting + 13.73 ms rendering = **44.99 ms/拍**。
   「不值得為它換寫法」在單檔頁成立,在圖牆**不成立**。
4. **jsdom 的倍率不是常數**:節點多時 6.8–9.2 倍,path 化之後降到 0.96–2.6 倍。
   → **jsdom 會系統性高估「節點數多」那一邊的成本**,用它當繪製方案的選型依據會做出
   「往減節點方向過度樂觀」的判斷。但方向本身沒判錯 —— 排序是一致的。

---

## 8. 保真度(公平性查核)—— 誰畫了什麼

| 語彙 | svg-rect / svg-path | canvas 2D | uPlot | lightweight-charts |
|---|---|---|---|---|
| 走勢線(271/1140 點) | ✔ | ✔ | ✔ | ✔ |
| VWAP 線 | ✔ | ✔ | ✔ | ✔ |
| 平盤面積填色 | ✔ | ✔ | ✔(近似) | 需 AreaSeries 另做 |
| **VP 價位別成交量長條(~52 根)** | ✔ | ✔ | ✘ **沒畫** | ✘ 需 primitive |
| 11 條價位刻度 + 價位文字 | ✔ | ✔ | ✔(軸刻度,格式不同) | ✔ |
| 整點格線 + 時間標籤 | ✔ | ✔ | ✔ | ✔ |
| 現價圈 | ✔ | ✔ | ✘ | 內建 lastValue |
| **副圖量柱(獨立 pane)+ 雙量刻度** | ✔ | ✔ | △ 疊在主圖區、非獨立 pane | ✔(第二 priceScale) |
| 高低標記 / CDP-MA 標籤避讓 / 成交點三角 | 現況有,本擂台三方都未畫 | | | |

→ **uPlot 的 9.48 ms 是「畫得比別人少」換來的**;canvas 2D 的 11.27 ms 是**全語彙**。
兩者差 1.8 ms/拍(19%),而補上 VP + 現價圈 + 獨立 pane 之後 uPlot 只會更貴。
**這就是「uPlot 帳面第一但實務該選 canvas」的理由。**

截圖佐證:`shots\C-wall50-canvas.png`(全語彙)vs `shots\C-wall50-uplot.png`(無 VP、無現價圈、
量柱疊在主圖區)。

---

## 9. K 線對決(700 根 / 5900 根,首繪)

沒有做「每 0.1 s 更新」—— K 線在 repo 是換檔 / 拖曳時重建,不是 tick 級。

| n | 方案 | mount scripting | mount layout | DOM 節點 |
|---|---|---|---|---|
| 700 | 手刻 SVG(每根 1 rect + 1 line) | 3.1–3.5 ms | 1.9–2.1 ms | **1,411** |
| 700 | lightweight-charts | 1.7–1.9 ms | 0.1–0.2 ms | **31**(7 個 canvas) |
| **5900** | 手刻 SVG | **19.6–23.2 ms** | **15.2–16.9 ms** | **11,811** |
| **5900** | lightweight-charts | **3.0–4.8 ms** | 0.2–0.3 ms | **31** |

- **700 根:手刻 SVG 5.0–5.6 ms 首繪,完全可接受。** 不必換。
- **5900 根:手刻 SVG 35–40 ms 首繪(scripting + layout)** —— 切到長歷史日 K 會**明顯卡一下**;
  lightweight-charts 3.2–5.1 ms,**快 7–11 倍**。
- 但 repo 的 `candle-viewport.ts::MAX_VISIBLE = 700` 本來就把可視上限壓在 700,
  5900 根只有在「一次全畫」時才會發生。**現況架構下 5900 這一格不成立。**

---

## 10. 記憶體與節點數(GC 後,`Runtime.getHeapUsage`)

50 卡 × 271 格,跑 20 拍後強制 GC 四輪再量:

| 方案 | JS heap | Δ vs 空頁面 | DOM 節點 | 其中 SVG 元素 | canvas 數 |
|---|---|---|---|---|---|
| (空頁面基準) | 1.14 MB | — | 3 | 0 | 0 |
| **svg-rect(現況)** | 16.70 MB | **+15.56 MB** | **18,811** | 18,552 | 0 |
| svg-downsample | 13.34 MB | +12.20 MB | 13,761 | 13,502 | 0 |
| **svg-path** | 9.95 MB | +8.81 MB | **3,009** | 2,750 | 0 |
| **canvas 2D** | **3.43 MB** | **+2.29 MB** | **209** | 0 | 50 |
| uPlot | 5.57 MB | +4.43 MB | 809 | 0 | 50 |
| lightweight-charts | **18.30 MB** | **+17.16 MB** | 1,209 | 0 | **350**(每圖 7 個) |

**注意**:`Runtime.getHeapUsage` 只量 V8 heap。SVG 那 18,552 個元素在 Blink 的 C++ 端
(RenderObject / ComputedStyle)還有一份**沒被計進來**的成本 —— 所以 svg-rect 的
+15.56 MB 是**下限**。canvas 的 GPU texture 同理未計。

lightweight-charts 每張圖開 **7 個 canvas**(50 圖 = 350 個)是這一輪最意外的發現之一,
也解釋了它為何 painting 4.95 ms/拍(每拍要 commit 多層 texture)而 canvas 2D 只有 0.13 ms。

---

## 11. Bundle 體積

| 項目 | raw | gzip |
|---|---|---|
| uPlot(`uPlot.iife.min.js`) | 51,081 B | **22,093 B** |
| uPlot CSS | 1,857 B | 762 B |
| lightweight-charts(`production.mjs`) | 189,213 B | **60,575 B** |
| lightweight-charts(standalone) | 197,922 B | 62,340 B |
| **實際打包 delta(同一 baseline 對照)** | | |
| + uPlot | | **+27.8 KB gzip** |
| + lightweight-charts | | **+62.6 KB gzip** |
| canvas 2D / SVG path 化 | 0 | **0**(零新相依) |

repo `frontend/package.json` 目前 dependencies 只有 5 個、無圖表庫。
加 lightweight-charts ≈ 把前端相依體積抬一個檔次;加 uPlot 相對溫和。
**canvas 2D 與 path 化都是 0 KB。**

---

## 12. 遷移成本評估(對照 CLAUDE.md §4 的跨檔契約)

### 12.1 完全不受影響的契約(三個方案都安全)

這些是**幾何 / 資料層**的契約,不在繪製層:

- **CDP/MA 前後端同式**(`server/overlay.py` ↔ `lib/futures-overlay.ts`,
  golden fixture `tests/fixtures/overlay_parity.json` 兩邊各一條 parity 測試)
  → 只要**繼續由 `futures-overlay.ts` / `overlayLines()` 算完再餵給 renderer**,
  換誰畫都不碰這條。**絕不可改用圖表庫內建 indicator** —— 那才是打破契約。
- **台指期疊線分鐘鍵 = 1K 終點標記 −1 分**(`txf-overlay-series.ts`)
- **個股頁即時末根分鐘鍵 = accum 起點分 +1、上限 13:30**(`live-last-bar.ts`)
- **日 K 定稿界 14:00 前後端同值**(`bars.py::DAILY_FINAL_TIME` ↔ `day-bars-rollover.ts`)
- **江波圖調色盤 ≥ 腿數**(`test_river_palette_covers_every_leg` 鎖 `river-colors.ts` 字面)
  → 江波圖在 `components/corr/` 自成一棵樹,**改分時圖 / K 線碰不到它**
  (上一輪的 Q2 把這條套錯對象,此處更正)。

### 12.2 會動到的東西(按方案排)

| 方案 | 要改什麼 | 測試衝擊 | 風險 |
|---|---|---|---|
| **A. EnergySub + VP 改單一 `<path>`**(零相依) | `StockIntradayChart.tsx` 的 `EnergySub`(818–895)與 `vpBars.map`(451)兩處;新增 `energyPath()` / `vpPath()` 兩個純函式到 `stock-intraday-svg.ts` / `volume-profile.ts` | `data-testid="energy-bar"` / `"vp-bar"` / `"vol-tick-*"` 共 **19 處引用、6 個測試檔**(`StockIntradayChart.test.tsx` 12、`.futures.test.tsx` 3、`GroupGridView.test.tsx` / `.toggle.test.tsx` / `.variant.test.tsx` / `FuturesChart.test.tsx` 各 1)要從「數元素個數」改成「斷言 `d` 字串」 | **低**。幾何層零改動、視覺逐像素相同(截圖對照過)。順帶修掉 F3-19(key 用浮點 x、resize 整層重掛) |
| **B. 卡片變體改 canvas 2D**(零相依) | 新增一個 `CardCanvasChart.tsx`(~120 行,已在 `src/canvas.ts` 有可用原型);`CardIntradayChart` 改走它;hover 十字線改直接畫在 canvas 上或疊一層小 SVG | 圖牆相關的 RTL 測試**整批要改寫**(canvas 沒有可查詢的元素);要新增 pixel / 幾何層測試補回覆蓋 | **中**。最大的風險是 `CardIntradayChart` doc 明文反對的「同一檔在卡片與單檔頁是兩張不一樣的圖」—— **必須 user 拍板**。緩解:兩邊共用同一份 `buildIntradayGeometry` 輸出,差別只在「誰把幾何畫出來」,可寫一條測試比對兩邊幾何輸入相同 |
| **C. 圖牆換 uPlot** | 同 B 的測試衝擊,外加:VP / 現價圈 / 獨立量柱 pane 要用 plugin hooks 補回來 | 同 B | **中高**,而且補完保真度之後**未必比 B 快**(§8)。**不建議** |
| **D. K 線換 lightweight-charts** | `CandleChart.tsx` 全改;hline label 避讓 / 視窗高低標記 / BB / MA 全要用 primitives 重寫;**紅漲綠跌必須顯式設** `upColor/downColor`(庫預設是歐美綠漲紅跌,看錯 = 下錯單);Apache-2.0 需 `attributionLogo` 署名 | 大 | **高** vs 收益:700 根首繪只省 3.5 ms。**不建議(這一輪)** |

### 12.3 三條硬紀律(換任何繪製技術都適用)

1. **紅漲綠跌必須顯式設定** —— 這是後果最嚴重的一條(看錯漲跌方向 = 下錯單)。
   `CandleChart.tsx:35-39` 的 `BODY_CLASS` 目前用 Tailwind class 承載台股慣例;
   改 canvas 之後顏色變成 `fillStyle` 字串,**要有一條測試鎖住這兩個字面值**。
2. **CDP / MA / VWAP 一律自算再餵**,絕不用庫內建 indicator(`overlay_parity.json` 契約)。
3. **改繪製層不可順手改幾何層** —— 兩者混在同一個 commit 裡,parity 測試紅了會分不出是哪一邊。

---

## 13. 建議(收斂成三步)

| 步序 | 動作 | 實測收益(50 卡 @ 0.1 s) | 代價 | 判定 |
|---|---|---|---|---|
| **第一步** | **EnergySub + VP 改單一 `<path>`** | 56.83 → **26.08 ms**(**2.18×**);節點 18,645 → 3,009;heap −6.75 MB;期貨分時 8.35 → 2.83 ms | 19 處測試斷言改寫;零新相依;零視覺變化 | **建議導入(先做)** |
| **第二步** | **群組卡片變體改 canvas 2D**(單檔頁維持 SVG) | 26.08 → **11.27 ms**(再 2.31×;對現況 **5.04×**);節點 → 209;heap → 3.43 MB | 圖牆 RTL 測試改寫;「兩套繪製」要 user 拍板 | **有條件導入(需 user 拍板)** |
| **第三步** | uPlot / lightweight-charts | uPlot 9.48 ms(但保真度不足);lwc 20.67 ms 且 heap 最高、350 canvas | +27.8 / +62.6 KB gzip;plugin 重寫;紅綠色 + parity 三條紀律 | **不建議** |

### 為什麼第一步就足以脫離危險區

現況 p95 scripting 41.7 ms + rendering 17 ms,在 0.1 s 的預算裡已經沒有餘裕給
「同步十字線打穿 50 張卡的 memo」(F3-01)這類放大效應。
path 化之後 p95 scripting 23.1 ms、rendering 3.5 ms,**rendering 這條 SVG 專屬稅基本消失**,
餘裕一下子出來。第二步才是「量化等級」的那一級(11.27 ms = 預算的 11%)。

---

## 14. 意外 / 反直覺的結果

1. **降採樣是騙局。** 271→170 根量柱只省 31% 成本,卻要付資料失真。
   成本在「元素個數 × (React reconcile + DOM 寫 + 樣式重算)」這條線性項上,
   降採樣只是沿線滑一格,path 化才換量級。**上一輪「降採樣到 170 格」的建議應撤回。**
2. **Painting 從頭到尾都不是瓶頸**,連最糟的 SVG 也只有 5.7 ms/拍。
   真正的兩座山是 **Scripting(34.3 ms)** 和 **Rendering / 樣式重算(17.0 ms)**。
   「換 canvas 因為 canvas 畫得快」是錯的因果;正確說法是**「換 canvas 因為它把 18,645 個
   需要重算樣式的節點變成 50 個」**。
3. **repo 自己的 N047 註解「真瀏覽器快一個量級」高估了 3 倍**(實測 3.3×,不是 10×),
   但它的結論(單檔頁不值得改)反而是對的 —— 對的理由不是「瀏覽器快」,是「單檔頁只有 1 張圖」。
4. **uPlot 的頁內同步量測會騙人**:0.9 ms 是因為它把重繪延到 rAF。
   只用 `performance.now()` 包 `setData` 會得到「uPlot 比 canvas 快 7 倍」的假結論;
   trace 尺一照,差距只有 19%,而且是靠少畫 VP 換的。
5. **lightweight-charts 每張圖開 7 個 canvas**(50 圖 = 350 個),
   JS heap 17.2 MB(全場最高、比 SVG 還高),painting 4.95 ms/拍(比手刻 canvas 高 38 倍)。
   **「50 張小圖不要開 50 個庫實例」這條上一輪的警告,實測完全成立。**
6. **節點數是常駐稅**:2/50 卡在動的冷門時段,現況 scripting 只有 1.66 ms,
   **rendering 卻要 2.16 ms** —— 18,645 個節點光是「存在」就讓每次樣式重算都走一遍樹。
7. **「卡片是否全部可視」幾乎不影響總量**(C 56.83 vs E 58.12 ms)。
   因為 React reconcile + 樣式重算對捲出畫面的卡照樣發生,只有 painting 省了一點。
   → **虛擬捲動(只渲染可視卡)的收益遠低於直覺**,除非連 React 樹都不掛。

---

## 15. 侷限與什麼情況下結論會反轉

1. **本機單一組態**:Chrome 152 / DPR 1 / 60 Hz / 16 核。DPR 2(4K 筆電)下 canvas 的
   raster 成本會 ×4,SVG 的 scripting / rendering 不變 → **canvas 的優勢會縮小**(但不會反轉,
   因為 painting 目前只佔 canvas 總量的 1%)。**未量。**
2. **未量 hover / 同步十字線**:F3-01 指出圖牆 `syncHover` 預設開、卡片寬下「只在分鐘變化時回報」
   近乎 no-op,每次 mousemove 打穿 50 張卡的 memo。本擂台只量「報價驅動的更新」。
   若 hover 成本與更新成本同量級,排序不變但絕對值要加倍。**未量。**
3. **uPlot / lwc 版本未做到保真度對等**(§8),它們的數字是**樂觀下限**。
   canvas 2D 版本則是保真度對等的,數字可直接採信。
4. **記憶體只量 V8 heap**,SVG 的 Blink C++ 端與 canvas 的 GPU texture 都未計。
   SVG 那一欄是下限。
5. **「到下一幀」指標不可靠**:我等兩個 rAF,理論下限應是 16.7 ms,但量到 6.9–13.5 ms
   的場次不少 —— Chrome 在無 damage 時的 BeginFrame 排程會提早發。
   **只把它當「有沒有掉幀」的相對訊號,不要拿絕對值做預算。**
6. **未量真實 WS 流的抖動**:本擂台每拍固定 100 ms,真實 `_flush_ticks` 是 0.1 s 打包
   但一拍內動幾檔是隨機的。C / C2 / C3 三種密度已經把範圍夾出來。
7. **未在 repo 內真的改任何一行** —— 上面的遷移成本是**讀碼 + 數測試引用**得出的估計,
   不是實作過的。`data-testid` 的 19 處引用是 grep 實數,其餘是推估。
