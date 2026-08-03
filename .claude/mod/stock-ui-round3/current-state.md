# stock-ui-round3 — Phase 1 現況表

分支:`mod/stock-ui-round3`(自 `3e891f1`,與 `master` 同 sha)
Baseline:`npm test` 51 檔 / 482 tests 全綠、`npx tsc -b` 0、`npx eslint src` 0(2026-07-29 23:46)

---

## 0. Caller map(要動的模組 → 誰吃它)

| 目標 | caller | 動態用法 |
|---|---|---|
| `lib/stock-intraday-svg.ts::buildIntradayGeometry` | `StockIntradayChart.tsx:254`(MAIN)、`:259`(SUB) | 無;`stock-intraday-svg.test.ts` 直呼 |
| `lib/stock-intraday-svg.ts::overlayLines` | `StockIntradayChart.tsx:275` | 無 |
| `IntradayGeometry.yTicks[].pct` | `StockIntradayChart.tsx:122-131`(右緣 % 文字) | 無 |
| `IntradayGeometry.energyBars` | `StockIntradayChart.tsx:503`(`EnergySub`) | 無 |
| `OverlayLine.label` | `StockIntradayChart.tsx:154`(React key)、`:161`(MA20 判色)、`:167`(文字) | **`key={`o-${l.label}`}` 與 `l.label === "MA20"` 為字串耦合** |
| `lib/candle.ts::buildCandleGeometry` | `CandleChart.tsx:310` | `candle.test.ts` 直呼 |
| `CandleGeometry.yTicks` | `CandleChart.tsx:100-114` | 無。`IndexPage.tsx:78` 的 `g.yTicks` 來自 **`index-chart-svg.ts` 另一支**,不受影響 |
| `StockPage.tsx` 版面 | `App.tsx:159` | 無 |
| `WatchlistSidebar` | `StockPage.tsx:31` | 無 |
| `RightRail` | `App.tsx:189`(**全 tab 常駐**,不只個股頁) | 無 |
| `server/bars.py::build_minute` | `app.py:428` | 無;`tests/test_bars*.py` 直呼 |
| `live/stock_source.py::_collect_history` | 同檔 `fetch_day_minutes` / `fetch_bars_range` / `fetch_daily_bars` | 無 |

---

## 1. 逐項現況 vs 目標

### 項 1 江波圖右緣 % 數
- **現況**:兩處。(a) 靜態 y 刻度右緣 %,`StockIntradayChart.tsx:122-132`,值來自 `YTick.pct`;
  (b) hover 右緣 `pct-tag`,`:450-474`,值來自 `hoverPrice` 對 `ref` 換算。
- **目標**:右緣不顯示 %。**(b) 去留待拍板**。
- **對 caller 影響**:`YTick.pct` 若移除欄位 → `stock-intraday-svg.test.ts` 有斷言(該紅)。
- **Backward compat**:純前端顯示,無對外契約。

### 項 2 CDP 用顏色區分 + 右緣顯示價位(不顯示 AH/NH)
- **現況**:`stock-intraday-svg.ts:229-234` push 五條線,label 字面為 `"AH"/"NH"/"CDP"/"NL"/"AL"`;
  `StockIntradayChart.tsx:160-162` 五條 CDP 線**同色** `stroke-ink-dim`,右緣文字直接印 label。
- **treading-king 參考**(`frontend/src/lib/intraday-chart-svg.tsx:201-210` + `lib/tick.ts`):
  label 文字 = `` `${formatTickPrice(v)}*` ``,五條**同一個 accent 色** `#e85a4f`;
  「接近整數價位邏輯」= `roundToNearestTick()` snap 到最近合法台股 tick +
  `formatTickPrice()` 依 tick 級距決定小數位(tick≥1 → 0 位、≥0.1 → 1 位、否則 2 位)。
- **copycat 對應件**:`lib/stock-tick.ts` 已有 `tickOf` / `snapDown` / `snapUp`(毫元整數),
  **缺 `snapNearest` 與「依 tick 決定小數位」的 formatter**(現行 `fmt()` 一律去尾 0 到 2 位)。
- **目標**:右緣印價位(snap 合法 tick + tick 級距小數位),五條線用顏色互相區分。**配色待拍板**。
- **對 caller 影響**:`OverlayLine.label` 語意由「名稱」變「價位」→ `key={`o-${l.label}`}` 與
  `l.label === "MA20"` 兩處字串耦合會壞,必須改成獨立欄位(`kind` / `level`)。

### 項 3 左緣只顯示 ±2/4/6/8%、漲跌停、平盤
- **現況**:`stock-intraday-svg.ts:25` `TICK_PCTS = [10,8,6,4,2,0,-2,-4,-6,-8,-10]`,
  ±10 取 `upper`/`lower` 原值、0 取 `ref`、其餘 `snapDown(ref×(1+pct/100))`;域外刻度跳過、
  重複價去重(`:159-173`)。**已與需求逐項相符**。
- **無 upper/lower 的 fallback 分支**(`:174-177`)只給 3 條(yTop / ref / yBottom)。
- **目標**:待釐清(見 change-spec 提問)。

### 項 4 漲跌停虛線
- **現況**:`StockIntradayChart.tsx:92-97`,`g.upperY` / `g.lowerY` 兩條 dashed(bull/bear)。
- **目標**:刪除。域已恰為 `[lower, upper]`(round2 SC-4),兩條線本就貼齊上下緣。
- **對 caller 影響**:`IntradayGeometry.upperY/lowerY` 將無 consumer(是否一併移除欄位待定)。

### 項 5 側欄 border
- **現況**:`WatchlistSidebar.tsx:163` `aside` 無 border;`RightRail.tsx:189` `aside` 無 border。
  兩者與中間僅靠 `gap-4`(`StockPage.tsx:30` / `App.tsx:149`)分隔。
- **目標**:自選加右 border、右欄加左 border。
- **注意**:RightRail 常駐**全部 tab**,border 會同時出現在 TXO / 期貨 / 指數頁。

### 項 6 中間不要滾動條 + 五檔/明細對齊底部
- **現況**(`StockPage.tsx:32/79-104`):`<main>` 帶 `overflow-y-auto`;圖表容器
  `StockChart.tsx:53` 是 `shrink-0`(高度由 viewBox 比例 × 容器寬決定,**不隨可用高度縮**);
  下半列 `min-h-56 flex-1`,五檔 `self-start`(自然高)、明細 `h-full`。
- **既有設計意圖**(檔內註解 + `docs/next-time.md`):`min-h-56` 是高度地板,空間不足時
  **刻意**讓 `<main>` 長出捲軸當逃生口(避免 flex-basis 0 把明細壓成 0 高整塊消失)。
  next-time 實測:1440×800 江波圖模式下下半列 226px vs 地板 224px,**只剩 2px 餘裕**。
- **目標**:不出捲軸、五檔與明細貼底。
- **技術阻塞**:要讓圖表吃「剩餘高度」必須讓 viewBox 高度隨可用像素變 —— 專案
  `frontend-conventions` 提到的 `useContainerSize` **本 repo 尚未存在**(grep 零命中),
  需新建 hook 或改用不失真的降級版式。**做法待拍板**。

### 項 7 江波圖時間黃色
- **現況**:X 軸靜態時間標籤 `StockIntradayChart.tsx:211` `fill-ink-dim`;
  hover 時間標文字 `:490` `fill-ink`。
- **目標**:黃色。theme 已有 `--color-ma5: #f0b429`(MA5 黃);未有專屬時間色 token。

### 項 8 江波圖交易量刻度
- **現況**:`EnergySub`(`:223-240`)只畫 bar,無任何軸標;歸一分母 `maxSide`
  (`stock-intraday-svg.ts:147`)為區域變數,**未進 `IntradayGeometry`**。
- **目標**:副圖顯示量刻度。需把 `maxSide` 出口化。

### 項 9 分 K 顯示慢 — **已實測**
量測環境:2026-07-29 23:5x,server :8721 常駐、TC4 在線、`/api/stock/bars/<code>?tf=1&days=30`

| 情境 | 耗時 | 說明 |
|---|---|---|
| 暖 cache(2330 / 1101 二訪) | 0.004–0.026s | 歷史段永久 memo + 當日段 30s TTL |
| 冷載入且有資料(1101 / 2603 / 3037) | **2.12–2.13s** | 三檔幾乎相同 → 由固定等待主導,非資料量 |
| 冷載入且**無資料**(9999) | **60.1s**,回 `{"bars":[]}` | 兩訪皆 60.1s → **完全沒有快取** |

- **根因**:`live/stock_source.py:382` `_collect_history` 的首頁 poll deadline =
  `max(poll_wait*30, 1.0)` = **30 秒**,且輪間 `time.sleep(poll_wait)` 固定 **1.0 秒**。
  `server/bars.py::build_minute` 對「歷史段」與「當日段」各發一次 fetch →
  無資料時 30s × 2 = 60s。
- **放大因子**:(a) `bars.py:101 today_put` / `:124 daily_put` 的 don't-cache-empty +
  `:158-160` 歷史段全空不寫負向快取 → 無資料標的**每次請求都重付 60s**;
  (b) `useStockBars.ts:73` `retry: 1` → 前端還會再打一次;
  (c) `docs/next-time.md` 已記「K 線 endpoint 未做 inflight dedup」。
- **未涵蓋的推測**:「有些股票」是否即「今日無成交 / TC4 無該檔 1K」尚待 user 指認
  (今日有資料的冷載入只有 2.1s,不像是 user 說的「很慢」)。
- **常態冷載入的 0.9s 浪費**:首輪 poll 必定落空時固定睡滿 1.0s。

### 項 10 K 線 y 刻度非法價位
- **現況**:`lib/candle.ts:222-225` `priceMilli = round(lo + span×i/(Y_TICKS−1))` **等分**,
  不 snap 合法 tick;`CandleChart.tsx:111` 用 `fmt()` 印出(最多 2 位小數去尾 0)。
- **既有紀錄**:`docs/next-time.md` 2026-07-29 條目已列此問題(「日 K 左緣會出現 2547.32」),
  當輪刻意未動。
- **目標**:刻度 snap 到該價位帶合法 tick + 依 tick 級距決定小數位;去重。
- **對 caller 影響**:`candle.test.ts:147-155` 只斷言「落在 [low, high] 內」→ 不該紅;
  若刻度數因去重變動,`:96` 等長度斷言需檢查。

---

## 2. 既有測試 baseline

| 檔 | 與本輪相關的斷言 |
|---|---|
| `lib/stock-intraday-svg.test.ts`(294 行) | yTicks 的 pct、11 刻度、overlayLines 的 label 字面 |
| `lib/candle.test.ts`(258 行) | yTicks 區間、長度、priceAtY |
| `components/stock/StockIntradayChart.test.tsx` | 右緣 %、疊線 label、crosshair tag |
| `components/stock/CandleChart.test.tsx` | y 刻度文字 |
| `components/stock/StockPage.test.tsx` | 下半列 `stock-lower-row` 結構 |
| `tests/test_bars.py`(後端) | `build_minute` 歷史/當日段拼接、負向快取 |

---

## 3. Backward compat / migration

- 全為前端顯示 + 後端 cache/timeout 調參,**無資料格式、無 API 契約、無 localStorage schema 變動**。
- 唯一跨檔契約面:`/api/stock/bars` 的 response shape 不變(項 9 只動時間與快取策略)。
- 無 migration 需求。
