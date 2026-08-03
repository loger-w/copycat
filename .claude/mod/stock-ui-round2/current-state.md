# Phase 1|現況盤點 — stock-ui-round2

分支:`mod/stock-ui-round2`(從 `master` 開;**本 repo 無 remote**,收尾走 branch-lifecycle
離線 fallback:`git switch master` + `git merge --ff-only`)。

Baseline(2026-07-29 19:37):
- frontend `npm test -- --run` → **47 檔 / 395 測試全綠**
- backend `pytest -q` → 見 Phase 1 執行紀錄

---

## 0. 檔案地圖(個股頁相關)

| 檔案 | 角色 |
|---|---|
| `frontend/src/components/stock/StockPage.tsx` | 個股頁版面:側欄 + header + 圖表 + 下半(五檔/明細) |
| `frontend/src/components/stock/StockChart.tsx` | 圖表模式切換容器(江波圖 / 1分K / 5分K / 日K)+ 「往前」載入 |
| `frontend/src/components/stock/StockIntradayChart.tsx` | 江波圖元件(主圖 800×260 + 內外盤副圖 800×70) |
| `frontend/src/lib/stock-intraday-svg.ts` | 江波圖幾何純函數(Y 域 / 刻度 / 量 bar / 能量 bar / overlay 線) |
| `frontend/src/components/stock/CandleChart.tsx` | K 線元件(1400×320) |
| `frontend/src/lib/candle.ts` | K 線幾何 + `aggregateBars(n)` + `movingAverage(n)` |
| `frontend/src/hooks/useStockBars.ts` | `/api/stock/bars` query(`tf=D` / `tf=1&days=N`) |
| `frontend/src/hooks/useChartToggles.ts` | 江波圖 toggle(vwap / cdp / ma)+ localStorage |
| `frontend/src/components/stock/WatchlistSidebar.tsx` | 自選側欄(群組 tab + 清單 + 拖拉 + 移組) |
| `frontend/src/hooks/useStockWatchlist.ts` | watchlist GET/PUT |
| `frontend/src/hooks/useStockStream.ts` | 個股 WS(`watchlist_quote` / tick / book / status) |
| `frontend/src/components/stock/PriceLadder.tsx` | 閃電梯(武裝 / 點價送單 / 跟隨置中) |
| `frontend/src/components/rail/RightRail.tsx` | 右欄三 tab(閃電 / 委託 / 部位) |
| `frontend/src/components/capital/CapitalPositionsList.tsx` | 部位清單 + 平倉 |
| `frontend/src/index.css` | `@theme` 色票 + 全域捲軸樣式 |
| `copycat/server/stock_engine.py` | `watchlist_quote` 廣播(1s 節流) |
| `copycat/server/app.py:393` | `/api/stock/bars/{code}`(**`tf` 只收 `D` / `1`**) |
| `copycat/stock_watchlist.py` | watchlist v2 groups schema + 30 檔上限 |

---

## 1. 逐項:現況 vs 目標

### 項 1 — 捲軸樣式

| | |
|---|---|
| **現況** | `index.css:43-46` `* { scrollbar-width: thin; scrollbar-color: var(--color-ink-dim) transparent; }` |
| **來歷** | **上一輪 `mod/stock-ui-fixes` 的 SC-5 已做掉**(commit `f619237` 綠 + `6c54d27` 修選擇器 `html`→`*`),並附註解說明「標準屬性優先於 `::-webkit-scrollbar`」 |
| **判定** | **本項疑似已完成**。若 user 仍不滿意,需指認「哪一處捲軸、不滿意什麼」才有可改動點 → **Phase 2 待澄清 Q1** |
| **caller 影響** | 全站(TXO / 期貨 / 指數頁共用),改動 = 全站視覺 |

### 項 2 — 江波圖漲跌配色

| | |
|---|---|
| **現況** | 色票**已是台股紅漲綠跌**(`--color-bull #f0524f` / `--color-bear #3ba272`)。但**價格線是單色 accent 桃紅** `#e8467c`(`StockIntradayChart.tsx:129` `stroke-accent`),不隨漲跌變色 |
| **treading-king 對照** | `intraday-chart-svg.tsx:417-426`:主價線用 **clipPath 切上下兩段**,平盤上 `t.bull`、平盤下 `t.bear`;baseline 無值時 fallback 單條 `t.ink` 白線 |
| **目標** | 江波圖價格線改成 baseline(昨收 ref)上紅 / 下綠 |
| **caller 影響** | 僅 `StockIntradayChart`;`stock-intraday-svg.ts` 需輸出 clip 幾何或分段 polyline |

### 項 3 — 平盤與漲跌之間顏色區塊

| | |
|---|---|
| **現況** | **無**填色,只有一條線 |
| **treading-king 對照** | `intraday-chart-svg.tsx:289-317`:一個封閉 polygon(`起點baselineY → 走勢各點 → 終點baselineY`),用兩個 clipPath(above/below baseline)分別以 `bull` / `bear` `fillOpacity 0.15` 塗色 |
| **目標** | 照抄同一手法 |
| **caller 影響** | 同項 2 |

### 項 4 — 均線 / 漲跌線配色

| | |
|---|---|
| **現況** | VWAP(均價)線 = `stroke-profit` 琥珀金 `#d9a441`;MA5 = `--color-ma5` 黃 `#f0b429`;MA20 = `--color-ma20` 紫 `#b794f4`;價格線 = accent 桃紅 |
| **目標(字面)** | 「均線用白色的,漲用紅色的,跌用綠色的線」 |
| **歧義** | 「均線」= **VWAP 均價線** 還是 **MA5/MA20**?兩者都叫均線。「漲紅跌綠的線」= 價格線(與項 2 同一件事) → **Phase 2 待澄清 Q2** |
| **caller 影響** | `index.css` 色票改動會擴散到 K 線的 MA(`CandleChart.tsx:118/128`)與 treading-king 無關的其他頁 |

### 項 5 — 預設開啟 CDP

| | |
|---|---|
| **現況** | `useChartToggles.ts:11` `DEFAULTS = { vwap: true, cdp: false, ma: false }` |
| **目標** | `cdp: true` |
| **backward compat** | localStorage key `copycat-chart-toggles` 已存的使用者**不受影響**(`load()` 是 `{...DEFAULTS, ...saved}`,saved 的 `cdp:false` 會蓋掉新預設)。本機開發者若要看到效果需清 key 或該 key 尚未寫入 |
| **caller 影響** | `StockIntradayChart` 唯一 consumer |

### 項 6 — 江波圖 Y 區間與刻度

| | |
|---|---|
| **現況(區間)** | `stock-intraday-svg.ts:92-96`:有漲跌停時 `yTop = upper×1.02` / `yBottom = lower×0.98`(**多留 2% 邊)**;無漲跌停走對稱 autofit |
| **現況(刻度)** | 同檔 `142-147`:`[lower, midLow, ref, midHigh, upper]` **5 條** — 即 -10% / -5% / 0 / +5% / +10%,這就是 user 說的「以 5 為分隔」 |
| **目標** | 區間 = 漲停/跌停;左側刻度 = `0, ±2%, ±4%, ±6%, ±8%, ±10%` **11 條** |
| **風險** | `upper×1.02` 的 2% 邊若拿掉,漲停日價格線會**貼齊圖框頂端**(現況刻意留邊)。刻度 11 條在 260px 高度下間距 ~26px,字級 0.625rem 尚可 |
| **caller 影響** | `buildIntradayGeometry` 同時被主圖與副圖(SUB 800×70)呼叫;`overlayLines` 依 `yDomain` 過濾越界線 → 域縮小會讓更多 CDP/MA 線被隱藏 |

### 項 7 — 兩個成交量

| | |
|---|---|
| **現況** | 江波圖同時畫兩塊:(a) **主圖底部量 bar**(`StockIntradayChart.tsx:97-106`,佔主圖高 1/4,依分鐘漲跌著色);(b) **內外盤能量副圖**(`:271-278`,獨立 800×70 svg,外盤紅 / 內盤綠 雙色並排) |
| **目標** | 二選一 |
| **價值判斷** | (b) 內外盤能量是**本專案核心訊號**(CLAUDE.md §0a:每分鐘內外盤張數是 FinMind 拿不到、非留在 copycat 不可的理由);(a) 是傳統看盤軟體的量能。**砍哪個是方向性抉擇** → **Phase 2 待澄清 Q3** |
| **caller 影響** | `IntradayGeometry.volumeBars` / `.energyBars` 其中一個變成 dead code |

### 項 8 — K 線縮放 / MA / 布林 / 分K 選項 / 與江波圖同尺寸

| | |
|---|---|
| **現況(縮放)** | **無縮放**。`CandleChart` 只畫最後 `maxBars` 根(日K 120 / m1 700 / m5 400),要看更早要按「往前」把 `days` 加 5(上限 30) |
| **現況(MA)** | `showMa={mode === "day"}` — **只有日K 顯示 MA5/MA20**,分K 不顯示 |
| **現況(布林)** | **無** |
| **現況(分K)** | 只有 1分 / 5分 兩個按鈕;5分由前端 `aggregateBars(data, 5)` 聚合。`aggregateBars(n)` 本身**已支援任意 n**(`candle.ts:37`) |
| **現況(尺寸)** | K 線 `DIMS = 1400×320`;江波圖主圖 `800×260` + 副圖 `800×70`(合計 330 高、寬 800)。兩者 viewBox 不同、`className="w-full"` 撐滿容器 → **實際渲染寬相同、高不同** |
| **backend 限制** | `app.py:399` **`tf` 只接受 `"D"` / `"1"`**,`tf=3` 會 400 `BAD_TF`。→ 2~10 分 K **全部走前端 `aggregateBars`**,backend 不需改(`tf=1` 取原料) |
| **目標** | 滾輪縮放 + 平移;5MA/20MA + 布林通道(20MA ± 2σ);分K 1~10;兩圖同高 |
| **風險** | 「不需要再點往前就能看 30 日」= 預設 `days=30`。1 分 K × 30 日 ≈ **8,000 根**,現況 `MINUTE_MAX_BARS.m1 = 700` 是為了避免蠟燭壓到 <2px 而設的上限 → 縮放機制必須取代這個常數,否則「載了但看不到」 |
| **caller 影響** | `CandleChart` 被 `StockChart` 唯一呼叫;`buildCandleGeometry` 需接受可視窗口(start/end index) |

### 項 9 — 閃電下單「跟隨置中會隨價位中心變動」

| | |
|---|---|
| **現況** | `PriceLadder.tsx:239-246`:`follow === true` 時,**`centerPrice`(= 現價所在列)一變就 `scrollIntoView({block:"center"})`** — 這已經是「跟著價位中心捲動」。另 `:336-341` 手動捲動會自動關掉 follow;`:220-226` 五檔點價 → 該價置中並關 follow |
| **歧義** | 本句讀起來像是**描述現況**而非要求改動。可能的真實訴求:(a) 現況壞了(捲不動 / 捲錯);(b) 希望**中心錨點固定在容器正中**而非 `block:"center"` 的瀏覽器行為;(c) 希望 follow 關掉後仍有「回到現價」按鈕 → **Phase 2 待澄清 Q4** |
| **caller 影響** | `PriceLadder` 內部;`RightRail` 持有 `centerRequest` |

### 項 10 — 兩圖都顯示 x/y 軸虛線

| | |
|---|---|
| **現況(江波圖)** | **已有雙軸**(`StockIntradayChart.tsx:239-256`):垂直線在 hover 分鐘、水平線在**該分鐘收盤價** `g.toY(hoverAgg.c)`(**不是滑鼠 y**) |
| **現況(K 線)** | **只有垂直線**(`CandleChart.tsx:216-227`),無水平線 |
| **目標** | 兩圖都有 x/y 虛線 |
| **與項 11 綁定** | 水平線要跟「滑鼠 y」還是「bar 收盤價」,取決於項 11 的設計結論 |

### 項 11 — 滑鼠位置價位 + 資訊小視窗(要求用 fable 5 設計)

| | |
|---|---|
| **現況(江波圖)** | hover tooltip 是 **SVG 內浮動小方框**(`:257-266`,122×34,跟著 x 位移、y 固定 10),顯示「時間 · 收盤 / 漲跌% · 量」。左側無滑鼠價位標籤 |
| **現況(K 線)** | tooltip 是 **圖下方的 `<figcaption>` 橫排**(`:229-247`),顯示「時間 / 開高低收 / 量」。無 y 軸標籤 |
| **目標** | 十字虛線跟隨滑鼠;左緣顯示滑鼠所在**價位**;股票資訊小視窗重新設計得更好用 |
| **決策方式** | user 指定 **fable 5 思考設計** → Phase 2 前先 dispatch fable 產設計方案,結論併入拍板 |

### 項 12 — 自選側欄重做

| | |
|---|---|
| **現況(群組)** | tab 列 = 「全部」(union,停用拖拉)+ 使用者自建群組 + `+` 新增。**沒有恆存的預設群組** —— 在「全部」下新增股號時才會 lazily 建立名為「自選」的群組(`WatchlistSidebar.tsx:79-88`) |
| **現況(列內容)** | 單列 44px:`⋮⋮ 拖把 / 代號(font-mono) / 價位 + 漲跌%(同一水平列,baseline 對齊) / ⊞ 移組 / × 移除`。**沒有股票名稱** |
| **🔴 對外契約缺口** | `WatchlistQuote`(`useStockStream.ts:13-18`)只有 `p / chg_pct / vol / no_data`,**沒有 `name`**。後端 `stock_engine.py:448-457` 的 `watchlist_quote` 廣播也沒發 name(`_handle_no_data:295-304` 同)。→ **要顯示名稱必須改 WS 訊息 shape(跨檔契約,CLAUDE.md §4)** |
| **名稱來源** | `StockDayState.meta` 有 name(主檔 header `StockPage.tsx:46` 用的是 `accum.meta.name`),側欄各檔的 state 也在 `engine._states` 裡 → 後端拿得到,只是沒發 |
| **目標** | 恆存預設群組 + 使用者自建;列改雙行(上:價位 / 下:漲跌幅)+ 代號 + 名稱;漲跌停紅/綠燈 |
| **歧義** | 「預設群組」是否**取代**現有的「全部」union tab?兩者並存還是二擇一 → **Phase 2 待澄清 Q5** |
| **backward compat** | `stock_watchlist.py` 已是 v2 groups + v1 讀時遷移;**新增恆存預設群組不需再改 schema**(空清單時前端補一個「自選」即可)。若改 schema 需再走一次 migration |
| **已知既有 bug** | `docs/next-time.md:93`:「全部」群組顯示「尚無自選」但主檔有資料 —— 既有行為,根因未查,**不在本輪 scope 除非 user 要求** |

### 項 13 — 閃電梯顯示部位 / 未實現損益 / 打平價位

| | |
|---|---|
| **現況** | 部位在**右欄「部位」tab**(`CapitalPositionsList`),閃電 tab 看不到。`CapitalPosition` 已有 `qty / avg_price / pnl_base / pnl_base_price / pnl_cost / kind` |
| **現況(平倉估價)** | `RightRail.tsx:170-177`:個股用 `last.p / 1000` 當閘用估價 |
| **目標** | 閃電梯內直接顯示「本檔部位 + 未實現損益 + 打平價位」 |
| **🔴 打平價位的定義未定** | 純均價打平(`avg_price`)vs **含交易成本**(買進手續費 + 賣出手續費 + 證交稅 0.3%,當沖減半)。含成本才是「真正打平」,但需要**手續費折數**這個設定值 —— 群益 API 不保證回傳,等於要新增一個 env / config → **Phase 2 待澄清 Q6** |
| **caller 影響** | `PriceLadder` 需吃 `useCapitalPositions`;`pnl_base` 語意需確認(`copycat/capital/balance.py`) |

---

## 2. 既有行為白名單(候選 — Phase 2 定案)

改動不得破壞:

1. **閃電梯武裝紀律**:換股 / 斷線 / idle 5 分 / Esc / 連 3 次失敗 / 離開畫面(unmount)全部自動解除;
   未武裝點價不送單。`RightRail` 的閃電 tab **必須維持條件 render 不可改 `hidden`**(D-13)。
2. **同格 500ms 防抖**、五檔點價只置中不送單。
3. 江波圖 `minuteOf` 對無資料 bucket 回 `null`(不 snap 最近)。
4. 江波圖 / K 線的 `ChartStatic` memo 邊界(hover 每次 mousemove 不得重建靜態層)。
5. `useStockBars` 的 `tf=D` query key 不含 days(D-15);非交易時段不得週期輪詢(週末 gate)。
6. K 線失敗態與「無資料」態必須分得開(SC-3,顯示錯誤碼)。
7. watchlist 30 檔上限以**跨群組聯集**計;`BAD_CODE` / `BAD_GROUP` / `WATCHLIST_FULL` 錯誤碼契約。
8. `StockPage` 下半列 `min-h-56` 地板 + `StockChart` 的 `shrink-0`(W-17 溢出防護)。
9. 全站捲軸樣式(項 1 若改動,TXO / 期貨 / 指數頁不得回退成瀏覽器預設白底)。
10. `select-none` 防拖曳反白(兩張圖)。

---

## 3. 規模判定

**L 級**:13 項橫跨 3 個元件族(圖表 / 側欄 / 閃電梯)+ 1 處後端 WS 契約(項 12 name)
+ 1 處可能的新設定(項 13 費率)。含 2 個純設計題(項 11)與 4 個待澄清歧義。
