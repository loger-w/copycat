# F6 — 前端:其餘 lib、型別、build 設定與 bundle

分析對象:`frontend/src/lib/*`(F2/F4 未涵蓋的 28 支)、`frontend/src/types.ts`、
`frontend/vite.config.ts` / `sha-plugin.ts` / `tsconfig*.json` / `eslint.config.js` /
`index.html` / `src/index.css`,以及 build 產物與量測。

所有量測在 2026-09-13 於本機(Windows 11、Node 22 系、`frontend/` 目錄)實跑,
**沒有改動 repo 任何檔案** —— build 產物一律輸出到 scratchpad 的 `distprobe` /
`distmap`,`frontend/dist/` 未被覆蓋。

---

## 0. 一句話結論

**這個區塊本身幾乎沒有「慢在 CPU」的東西 —— 真正的效能問題有兩條,而且都不在
lib 的演算法裡,在「怎麼把畫面送到瀏覽器」這一層:**

1. `run.ps1`(一鍵啟動)跑的是 **`npm run dev`**,與 CLAUDE.md §1「看盤日常一律
   `npm run build` + `npm run preview`」相反 —— 預設路徑上整天看盤跑的是 React
   **development build**。
2. 不論 dev 或 preview,**所有 `/api` 與 `/ws` 都繞一個 Node 行程**(vite proxy),
   開盤時每秒數百則 tick frame 要多經一次 Node 的 `ws` 解幀 / 重打包 / event loop 排程。

除此之外:bundle 386 KB(gzip 123 KB)、CSS 39 KB(gzip 7.9 KB)、`tsc -b --force` 8.4 s、
`vite build` 2.16 s —— 以一個只服務 localhost 單一 Chrome 的看盤終端來說,**這些數字全部
不是問題,不要為了它們做工**。lib 內的純函式絕大多數是 O(小 n) 的字串/日期運算,
換 numpy 級工具在前端沒有對應物,也沒有必要。

---

## 1. 架構地圖

### 1.1 build / serve 拓樸(現況)

```
                       ┌──────────────────────────────────────────┐
 Chrome (localhost)    │  vite dev :5173  或  vite preview :4173  │
        │  HTTP/WS     │  ── Node 行程 ──                          │
        └──────────────►  server.proxy:                            │
                       │    /api  → http://127.0.0.1:8721          │
                       │    /ws   → ws://127.0.0.1:8721 (ws:true)  │
                       └───────────────┬──────────────────────────┘
                                       │ (再一跳)
                                ┌──────▼───────────────┐
                                │ uvicorn / FastAPI    │
                                │ :8721                │
                                └──────────────────────┘
```

- `vite.config.ts:19-24` 只宣告了 `server.proxy`;vite 的 preview 設定是
  `proxy: preview?.proxy ?? server.proxy`(`node_modules/vite/dist/node/chunks/dep-Dm0c1Wj2.js:48365`
  實際核過),所以 **`npm run preview` 也走同一組 proxy**,Node 行程不會因為切 prod build 而消失。
- 後端**沒有**任何 `StaticFiles` / `FileResponse` 掛載(`grep StaticFiles copycat/server/*.py` 零命中),
  所以 dist 目前只能靠 vite preview 服務 —— Node 行程是**目前架構下的必要元件**,不是可有可無的開發工具。
- `run.ps1:142-143`:
  ```
  Write-Host '[run] frontend -> vite dev(實際網址看下方 vite 輸出)'
  $frontend = Start-Process -FilePath $npm -ArgumentList 'run', 'dev' `
  ```
  一鍵啟動 = dev。要照 CLAUDE.md 的「看盤日常」得手動另跑 build + preview。

### 1.2 lib 分層

`src/lib/` 這 28 支(F6 範圍)可以分成五類,**沒有一支是「計算密集」的**:

| 類別 | 檔案 | 性質 |
|---|---|---|
| 顯示格式化 | `format.ts` `pnl-format.ts` `trade-text.ts` | 純字串;Intl 已在 module 層 hoist |
| 瀏覽器邊界 | `storage.ts` `fetch-timeout.ts` `api-error.ts` `dev-perf-guard.ts` | 唯一出口封裝,never-raise |
| 值域 / 契約鏡像 | `constants.ts` `signal-params.ts` `close-order.ts` `fut-chart-mode.ts` `stkfut.ts` `types.ts` | **跨語言契約的前端半邊**(§5) |
| 時間 / 日曆政策 | `trading-calendar.ts` `trading-hours.ts` `day-bars-rollover.ts` `settlement.ts` | 被 TanStack Query 的 `refetchInterval` / `staleTime` callback 每 render 求值 |
| 純模型 | `signal-model.ts` `watchlist-model.ts` `watchlist-avg.ts` `list-drag.ts` `stock-search.ts` `index-source-health.ts` `fee-discount.ts` `stock-view.ts` `tablist-keys.ts` `commit-ref.ts` `version-drift.ts` `utils.ts` `commit-ref.ts` | 小 n 的陣列/字串處理 |

`trading-calendar.ts` 有一顆**模組級可變狀態** `holidaySet`(L17),寫入點唯一
(`setHolidays`,由 `useTradingCalendar` 取數成功後呼叫),讀取點是三支純函式 —— 這是
刻意設計(檔頭 L3-8 寫明理由:`refetchInterval` callback 拿不到 hook)。**不要改成 context**,
會把 5 個 hook 的整條 refetch 鏈都改成吃 props。

### 1.3 bundle 拓樸(實測)

`npx vite build --outDir <scratchpad>/distprobe`(2026-09-13,vite 6.4.3):

```
index.html                        0.76 kB │ gzip:   0.46 kB
assets/index-D7-RUPTK.css        39.32 kB │ gzip:   7.93 kB
assets/svg-points-*.js            0.10 kB
assets/chart-frame-*.js           0.61 kB
assets/CorrPage-*.js             13.75 kB │ gzip:   4.99 kB
assets/FuturesPage-*.js          14.19 kB │ gzip:   5.66 kB
assets/IndexPage-*.js            26.47 kB │ gzip:   8.90 kB
assets/CandleChart-*.js          40.95 kB │ gzip:  14.67 kB
assets/StockPage-*.js            73.83 kB │ gzip:  22.41 kB
assets/index-*.js               386.44 kB │ gzip: 123.51 kB   ← 主 chunk
✓ built in 2.16s
```

切分來源 = `src/App.tsx:39-42` 的四個 `React.lazy`(StockPage / FuturesPage / IndexPage /
CorrPage)+ 圖表的動態 import(CandleChart / chart-frame / svg-points)。**`vite.config.ts`
沒有 `build.rollupOptions.manualChunks`** —— 目前的切分全部是 lazy 邊界自然產生的。

主 chunk 386 KB 的組成(用 sourcemap mappings 把 minified byte 逐段歸戶,實測):

| 歸戶 | minified bytes | 佔主 chunk |
|---|---|---|
| `react-dom/cjs/react-dom-client.production.js` | 177,129 | 46% |
| **`tailwind-merge/dist/bundle-mjs.mjs`** | **27,463** | **7.2%** |
| `@tanstack/query-core`(queryObserver + query + queryClient …) | ~28,000 | 7.3% |
| `react/cjs/react.production.js` | 7,626 | 2.0% |
| `scheduler` | ~3,000 | 0.8% |
| 其餘全是 `src/`(FuturesLadder 8.2 KB / App 6.8 KB / LadderView 6.1 KB / stock-intraday-svg 5.7 KB / PriceLadder 5.4 KB / OrderPanel 5.0 KB …) | ~130,000 | 34% |

**`import * as` 零命中**(`grep -rn "import \* as" src` 全庫 0),沒有 tree-shaking 失效的
namespace import。node_modules 只有 7 個套件進 bundle:react-dom / tailwind-merge /
@tanstack/query-core / react / scheduler / @tanstack/react-query / clsx。

### 1.4 CSS(Tailwind v4)

- 產物 39,318 bytes / gzip 7,932 bytes,約 667 條規則。
- `src/index.css` 只有 75 行:`@import "tailwindcss"` + 一個 `@theme`(24 顆語意色 token
  含 11 顆江波圖腿色 + 2 組字型)+ 三條全域規則(`html/body/#root` 高度、`*` 捲軸配色、`body` 底色)。
- arbitrary value 用量:整個 `src/**/*.tsx` 共 606 處 `x-[…]` 形態的 token,去重後 **227 個**,
  其中相當比例其實是 JS 陣列索引(`instances[0]` / `rows[0]` / `bids[0]`)被我的正則誤收,
  真正的 Tailwind arbitrary class 是 `text-[0.625rem]`(18)、`h-[1.375rem]`(12)、`z-[1]`(8)、
  `max-[26.5rem]`(7)這一類固定字面。**沒有任何一處是 template literal 動態產生的**
  (`grep 'cn(`'` 與 `grep '\[\${'` 皆零命中)。
- 結論:**CSS 沒有膨脹問題,不需要瘦身。** 7.9 KB gzip 對一個 25+ 元件的暗色交易終端是很小的數字。

### 1.5 型別 / lint / 測試設定

- `tsconfig.app.json`:`strict` + `noUncheckedIndexedAccess` + `noUnusedLocals` +
  `noUnusedParameters` + `noFallthroughCasesInSwitch`,`skipLibCheck: true`,
  `moduleResolution: bundler`,`noEmit: true`。設定本身很嚴格也很現代,**沒有改進空間**。
- `tsc -b --force` 實測 **8.437 s**(全量);增量(有 `tsconfig.app.tsbuildinfo`)會更短。
- `eslint.config.js` 只掛三組規則:`js.configs.recommended`、`tseslint.configs.recommended`、
  `react-you-might-not-need-an-effect`。**沒有 `eslint-plugin-react-hooks`**(package.json
  devDependencies 也沒有),所以 `rules-of-hooks` 與 `exhaustive-deps` 完全沒在跑。
- `vite.config.ts` 的 `test.environment` 是 `"node"`,99 個測試檔各自用
  `// @vitest-environment jsdom` 檔頭覆寫。`npx vitest run` 實測:
  ```
  Test Files 156 passed | Tests 3069 passed
  Duration 48.18s (transform 26.24s, collect 125.73s, tests 240.41s, environment 212.83s, prepare 30.97s)
  ```
  **`environment` 累計 212.83 s** —— 建 jsdom 是這條迴圈裡最貴的單項(累計比實際跑測試的
  240 s 只差一點,而它完全是固定成本)。

---

## 2. 資料流(與 F6 相關的三條)

### 2.1 偏好設定流(localStorage)

```
constants.ts(key 唯一宣告,22 把 key + ORPHAN_STORAGE_KEYS)
      │
      ▼
storage.ts(readLocal / writeLocal / removeLocal / readLocalJson;唯一 try/catch 出口)
      │
      ├─ App.tsx / MarketPane / RightRail / StockChart / WatchlistSidebar /
      │  RiverPanel / LimitListSection / useChartToggles …(74 個呼叫點)
      │
      └─ fee-discount.ts ── useSyncExternalStore ── 4 個元件(見 §3 熱路徑 HP-2)
```

### 2.2 日曆 / 時段流(進 TanStack Query 政策)

```
/api/calendar ──► useTradingCalendar ──► trading-calendar.setHolidays()(模組級集合)
                                                   │
                                         isTradingDay / isWeekendIso / nextTradingDayIso
                                                   │
                               trading-hours.ts:inTradingHours / inFuturesTradingHours /
                               inFuturesAllDayHours / msUntil*Open / offHoursInterval
                                                   │
                     ┌─────────────────────────────┴──────────────────────────────┐
       day-bars-rollover.dayBarsStaleTime / dayBarsRefetchInterval          各 hook 自己的 POLL_MS
                     │
        useFuturesBars / useMarketBars / useStockBars(日 K)、useBreadthRows、useIndexOverlay
                     │
        ★ TanStack Query 的 useBaseQuery 每 render 都 observer.setOptions(...)
          → 這些 callback **每 render 求值一次**(day-bars-rollover.ts L66-73 已自行寫明)
```

### 2.3 訊號流(顯示層)

```
WS /ws/stock ─► useSignalFeed ─► mergeSignals(baseline, live, cap=200)  [useMemo 有]
                                          │
                                          ▼
                             SignalRail.tsx:174  groupSignals(signals)   [無 useMemo]
                                          │  每組再呼叫
                                          ├─ groupKindLabels  → arrivalOrder → [...items].reverse()
                                          ├─ groupRuleNames   → arrivalOrder → [...items].reverse()
                                          ├─ groupPolicyTags  → arrivalOrder → [...items].reverse()
                                          └─ groupPolicies    → arrivalOrder → [...items].reverse()
```

---

## 3. 熱路徑逐條

> 頻率口徑:個股頁的逐筆打包 flush 是 **0.1 s**(`stock_engine._flush_ticks`,CLAUDE.md §4),
> 所以 StockPage 子樹在開盤時的 commit 節奏約 **10 次/秒**;閃電梯 / 五檔另有各自節奏。

### HP-1 `utils.cn()` → `twMerge(clsx(...))`
- 位置:`src/lib/utils.ts:4-6`;全庫 **152 個呼叫點 / 40 個檔案**。
- 密度最高的:`LimitListSection.tsx`(19)、`QuoteTable.tsx`(10)、`WatchlistSidebar.tsx`(9)、
  `LadderView.tsx`(9)、`StockIntradayChart.tsx`(8)、`SignalRail.tsx`(7)、`OrderBook.tsx`(7)。
- 每次 render 每個帶條件 class 的節點各一次;閃電梯一梯數十列 × 每列數個 → 單次 commit 數百次。
- **實測成本**(Node 22,本機):
  ```
  clsx only               0.048 us/call
  twMerge(clsx) cache hit 0.168 us/call
  twMerge cache MISS      3.851 us/call      ← 23×
  ```
- cache hit 時完全不是問題(500 次呼叫 = 0.08 ms)。風險在 **tailwind-merge 預設 LRU
  `cacheSize: 500`**:本 app 有 407 個 distinct 靜態 `className="…"` 字面,加上 `cn()` 的
  條件組合(同一個 base + 有/無 `text-bull`/`text-bear`/`opacity-50` …)很容易把 distinct
  輸入推過 500 → 在盤中不同顏色狀態輪替時開始 thrash。

### HP-2 `fee-discount.useFeeDiscount()` 的 getSnapshot
- 位置:`src/lib/fee-discount.ts:41-43, 67-69`
  ```ts
  export function readFeeDiscount(): number {
    return loadDiscount().value;      // ← 每次都 readLocal + clampDiscount + String() + 物件配置
  }
  export function useFeeDiscount(): number {
    return useSyncExternalStore(subscribe, readFeeDiscount, () => FEE_DISCOUNT_DEFAULT);
  }
  ```
  `loadDiscount()`(L21-25)做的是:`readLocal(FEE_DISCOUNT_KEY)` →
  `window.localStorage.getItem`(**同步 IO**)→ `clampDiscount` 的 `Number.parseFloat` →
  `String(value)` → 配置 `{ raw, value }` 物件 → 呼叫端只取 `.value`,其餘全部丟掉。
- 消費者 4 個,而且都是個股頁的常駐元件:
  `StockPage.tsx:167`、`WatchlistSidebar.tsx:207`、`GroupGridView.tsx:362`、
  `PriceLadder.tsx:230`(經 `useFeeDiscountField`)。
- React 對每個訂閱元件,每次 render 至少呼叫一次 getSnapshot,commit 階段的
  `checkIfSnapshotChanged` 還會再呼叫一次 → **每秒約 4 × 2 × 10 = 80 次同步 localStorage 讀 +
  80 次物件配置**。
- 量級誠實話:Chrome 暖快取的 `getItem` 大約 0.1–1 µs,80 次/秒 ≈ 0.01–0.08 ms/s,
  **在 CPU 上根本不痛**。真正的問題是 (a) 它是 render path 上的同步 IO,在 storage
  被政策鎖 / 私密視窗的路徑上會走 try/catch 拋接,(b) 每秒 80 個丟棄物件進 minor GC。
  嚴重度 medium 而非 high,修法卻只有三行。

### HP-3 `trading-hours` / `trading-calendar` 在 refetchInterval callback
- `day-bars-rollover.ts:66-73` 檔內已寫明:「react-query 的 `useBaseQuery` 每 render 都
  `observer.setOptions(...)`,`QueryObserver.setOptions` 見回值一變就 clear + 重排計時器」。
- 盤中路徑:`inTradingHours(now)` → `isTradingDay(d)` → `isoLocalDate(d)`
  (`trading-calendar.ts:31-36`:3 個 `String()` + 2 個 `padStart` + 1 個模板字串 = 每呼叫 6 個字串配置)。
  5 條輪詢鏈 × 10 render/s = 300 個小字串/秒。**可忽略**。
- 盤外路徑:`msUntilNextOpen`(`trading-hours.ts:31-44`)最多掃 14 個日曆日,每日 `new Date(now)`
  + `isTradingDay` + 每個開點一個 `new Date(day)`。週末最壞掃 3 天 ≈ 10 個 Date。
  **也可忽略**(而且 `offHoursInterval` 已做秒級量化,避免計時器每 render 重排 —— 這一段
  設計是對的,別動)。

### HP-4 `signal-model` 的四支 group* + `SignalRail` 無 memo
- `SignalRail.tsx:174` 在 JSX 內直接 `groupSignals(signals).map(...)`;該檔 **`grep memo` 零命中**。
- 每組再呼叫 `groupKindLabels` / `groupRuleNames` / `groupPolicyTags` / `groupPolicies`,
  四支各自經 `arrivalOrder`(`signal-model.ts:237`)做 `[...group.items].reverse()`。
- 上界:`mergeSignals` 的 `cap = 200` → 最壞 200 組 × 4 個複本陣列 = 800 個陣列 / render。
  10 render/s → 8,000 個小陣列/秒。純 JS 成本仍是 µs 級,但 **同時產生 200 個 `<li>` 的 vdom**
  才是真花費(那一半屬 F4 的 render 議題)。
- 修法極便宜:`groupSignals` 外包一層 `useMemo([signals])`,`arrivalOrder` 改成一次算完傳給四支。

### HP-5 `index-source-health.otcSourceDead`
- `src/lib/index-source-health.ts:32-34`:
  ```ts
  if (otc.p !== null || Object.keys(otc.minutes).length > 0) return false;
  return Object.keys(twse.minutes).length >= OTC_DEAD_MIN_TWSE_MINUTES;
  ```
  `minutes` 是分鐘格 map,盤中最多 ~270 鍵 → 每次呼叫配置一個 270 元素的字串陣列,
  而實際只要知道「是不是空」/「有沒有 ≥2 個」。
- 呼叫點 `MarketPane.tsx:379`,每 render 一次;大盤頁是 1 s 級推播 → **約 1–2 次/秒**。
  量級小,但寫法是白配置(改 `for (const _ in obj) { …; break }` 或計數上限即可)。

### HP-6 `stock-search.searchStocks`
- `src/lib/stock-search.ts:30-32`:
  ```ts
  for (const row of table) {
    if (row.code.toUpperCase().startsWith(upper)) byCode.push(row);
    else if (row.name.includes(trimmed)) byName.push(row);
  }
  ```
- 表大小實測註記為 **2,401 檔**(檔頭 L3)。每個字元按鍵掃全表,且每列做一次
  `row.code.toUpperCase()` → **每按一鍵配置 2,401 個字串**。
- 頻率 = 人打字(~10 次/秒上限),單次約 0.3–1 ms。**不是熱路徑**,但改成預先大寫的
  索引表是零風險的一行事。

### HP-7(非熱路徑但值得記) `watchlist-model.isSameWatchlist`
- `src/lib/watchlist-model.ts:27-29` 用 `JSON.stringify(a) === JSON.stringify(b)` 做深比。
- 自選上限已從 50 升到 **150**(`constants.ts:102`),加上群組結構,單次 stringify ~ 幾 KB。
- 呼叫點只在拖拉 commit / PUT 前的零寫早退,**每次使用者動作一次**,不在 tick 路徑上。
  **不要改** —— 這裡的正確性(避免送出內容相同的 PUT → 後端全量 TC4 UNSUB/SUB)遠比
  微秒重要,而 JSON.stringify 是最不容易寫錯的深比。

---

## 4. Findings

### F6-01 [critical · architecture] `run.ps1` 一鍵啟動走 `npm run dev`,與 CLAUDE.md §1 的看盤日常相反

**位置**:`run.ps1:142-143`

```powershell
Write-Host '[run] frontend -> vite dev(實際網址看下方 vite 輸出)' -ForegroundColor Green
$frontend = Start-Process -FilePath $npm -ArgumentList 'run', 'dev' `
```

**CLAUDE.md §1 的表格白紙黑字寫**:

> **看盤日常(prod build)** | `npm run build` 後 `npm run preview`(port 4173)…
> 整天掛著一律用本列,`npm run dev` 只做開發(2026-08-20)

但唯一的啟動腳本跑的是 dev。

**影響(熱路徑,每 tick)**:
- React 19 **development build**:每個 props identity 變了的 re-render 都走
  `logComponentRender` 打一筆 `performance.measure` + Changed Props diff。
  `lib/dev-perf-guard.ts` 的檔頭(L4-7)實測寫明 **632 筆/秒 ≈ 1.1 MB/s**。
  dev-perf-guard 只解決「buffer 無上限 → renderer 膨脹到 10 GB → Aw Snap」的**記憶體**面,
  **props diff 本身的 CPU 開銷它一點都沒省**(檔頭也是這樣寫的,CLAUDE.md §1 亦然)。
- 無 minify、無 dead-code elimination;約 **231 個模組各一支 HTTP request**(build 輸出
  「231 modules transformed」);HMR client 常駐一條額外 WS。
- StrictMode 在 dev 下雙呼叫 render / effect(`main.tsx:19`),每次 commit 的 JS 成本乘 2。

**修法**:
1. `run.ps1` 改成 `npm run build; npm run preview`(或加一個 `-Dev` 開關,預設 prod)。
2. 或至少讓啟動時印一行醒目的「現在是 dev build,整天看盤請用 preview」。

**風險**:改 `run.ps1` 會動到 §4「關機預算三方同源」契約的**同一個檔**
(`run.ps1` 啟動時 `python -c` 讀 `shutdown_budget.run_grace_secs()`,
`tests/server/test_shutdown_budget.py` 有 run.ps1 字面 parity 與 **UTF-8 BOM** 斷言)。
編輯時必須保留 BOM,且不可動到 graceSecs 那一段的字面。

**Effort**:S

---

### F6-02 [high · blocking-io / architecture] 所有 `/api` 與 `/ws` 都多繞一個 Node 行程

**位置**:`frontend/vite.config.ts:17-24`

```ts
const BACKEND = "http://127.0.0.1:8721";
...
  server: {
    proxy: {
      "/api": BACKEND,
      "/ws": { target: BACKEND, ws: true },
    },
  },
```

**證據鏈**:
- vite 的 preview 設定 `proxy: preview2?.proxy ?? server.proxy`
  (`node_modules/vite/dist/node/chunks/dep-Dm0c1Wj2.js:48365`)→ **`npm run preview`
  也走同一組 proxy**,切 prod build 不會讓 Node 退出資料路徑。
- 後端零 `StaticFiles` 掛載(`grep -rn "StaticFiles\|mount(" copycat/server/*.py` 零命中),
  dist 目前**只能**靠 vite preview 服務。
- 前端有 6–8 條常駐 WS(`types.ts:12` 的註解寫明「8 支 WS hook 共用的連線狀態」),
  個股逐筆打包節奏 0.1 s、期貨 0.1 s coalesce、加權 1 s、corr… 開盤時合計每秒數百則 frame。

**影響**:每一則 tick frame 要經 `uvicorn → Node ws 解幀 → Node 重打包 → Chrome`。
多一次記憶體複製、一次 Node event loop 排程、一次 GC 壓力,而且 Node 那一圈與
`vite preview` 的靜態檔服務共用同一條單執行緒 event loop。對「要用來下實單、速度要夠快」
的系統,這是**整個前端區塊裡最貴的單一架構決定**,而且它不是為了任何功能存在 ——
它只是「dev server 順手也當了 prod server」。

**修法(建議 A,推薦)**:後端掛 `StaticFiles` 服務 `frontend/dist`,瀏覽器直接開 `http://127.0.0.1:8721/`。
- Node 完全退出 runtime;`/api`、`/ws` 變同源,連 CORS 都不必。
- `run.ps1` 只剩 backend 一個行程要收(順帶簡化 §4 關機預算的 taskkill 樹)。
- 代價:每次改前端要 `npm run build`(CLAUDE.md 本來就要求了);dev 時仍走 vite dev + proxy。

**修法(建議 B)**:瀏覽器直接連 `http://127.0.0.1:8721`,dist 另外用任何靜態伺服器服務,
靠既有的 `FRONTEND_ORIGIN` CORS(`copycat/server/app.py:1267-1270`)放行。
— 比 A 差,因為 WS 跨 origin 還是要處理,且多一個行程。

**契約**:`vite.config.ts` 的 `BACKEND` port 8721 與 `run.ps1:29 $port = 8721`、
後端 `TXO_SERVER_PORT` 三處同值(run.ps1 L26 註解點名「要改必須兩邊一起改」)。
建議 A 不改 port,只是讓 dist 多一個服務者,契約不動。

**Effort**:M(後端 ~15 行 + run.ps1 調整 + 一次真環境驗證)

---

### F6-03 [medium · bundle / allocation] `tailwind-merge` 佔主 chunk 7.2%,且 LRU cache 只有 500

**位置**:`src/lib/utils.ts:1-6`

```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
```

**證據**:
- sourcemap 歸戶:`tailwind-merge/dist/bundle-mjs.mjs` = **27,463 minified bytes**,
  是主 chunk 裡僅次於 react-dom 的第二大依賴(原始碼 105,606 bytes)。
- 實測(§3 HP-1):cache hit 0.168 µs / cache **miss 3.851 µs** / 純 clsx 0.048 µs。
- 全庫 152 個 `cn()` 呼叫點,407 個 distinct 靜態 className 字面。

**twMerge 存在的理由是「合併外部傳進來的 className,解衝突」。** 本專案的元件幾乎不對外
開放 className prop(全部是自家頁面),`cn()` 實際上大多只是在做條件串接 —— 那正是 clsx 的工作。

**修法(擇一或併用)**:
1. **最小改動**:`cn` 改成用 `extendTailwindMerge({ cacheSize: 4000 })` 建的實例,
   確保永不 thrash。一行,零行為改變。
2. **最大收益**:熱路徑元件(閃電梯 `LadderView` / `PriceLadder` / `FuturesLadder`、
   五檔 `OrderBook` / `DepthBar`、`SignalRail`、`GroupGridView`、`QuoteTable`)把
   `cn` 換成直接 `clsx` —— 這些地方的 class 全是自家寫死的、彼此不衝突,twMerge 的
   衝突解析純屬白工。3.5× 提速 + 讓 tailwind-merge 有機會只留在冷路徑。
3. **極端**:全庫拿掉 tailwind-merge,`cn = clsx`。省 27 KB minified,但要人工核過
   152 個呼叫點確認沒有真的靠 twMerge 解衝突的地方 —— **不建議一次做**。

**風險**:選項 2/3 會改變「後面的 class 覆蓋前面的同族 class」這個語意。
必須逐點核:凡是 `cn(base, cond && "px-4")` 而 base 已有 `px-2` 的,拿掉 twMerge 後
兩條都會進 DOM,結果由 CSS 順序決定。`npx tsc -b` 與 vitest 都抓不到,只有畫面看得出來。

**Effort**:S(選項 1)/ M(選項 2)

---

### F6-04 [medium · blocking-io] `useFeeDiscount` 的 getSnapshot 每次 render 同步讀 localStorage

**位置**:`src/lib/fee-discount.ts:21-25, 41-43, 67-69`

```ts
export function loadDiscount(): DiscountState {
  const raw = readLocal(FEE_DISCOUNT_KEY);
  const value = clampDiscount(raw ?? "") ?? FEE_DISCOUNT_DEFAULT;
  return { raw: String(value), value };          // ← 只有 .value 被用
}
export function readFeeDiscount(): number {
  return loadDiscount().value;
}
export function useFeeDiscount(): number {
  return useSyncExternalStore(subscribe, readFeeDiscount, () => FEE_DISCOUNT_DEFAULT);
}
```

檔內註解(L61-62)自己寫了「getSnapshot 回的是 primitive number,React 以 Object.is 比對 ——
**每次 render 讀一次 localStorage 不會造成迴圈**」。不造成迴圈是對的,但那句話把
「不會壞」與「不花錢」混為一談了。

**頻率**:4 個常駐元件(`StockPage:167` / `WatchlistSidebar:207` / `GroupGridView:362` /
`PriceLadder:230`)× 每 render ≥2 次 getSnapshot × ~10 render/s = **~80 次/秒同步
localStorage.getItem + 80 個丟棄物件**。

**影響**:CPU 上約 0.01–0.08 ms/s(推測值,依 Chrome 的 localStorage 暖快取行為);
真正的問題是「render path 上的同步 IO」這個形狀本身 —— 這也正是 `storage.ts` 檔頭
(L4-9)自己點名的風險面。

**修法**:模組層快取一個 `let cached: number | null = null`,
`readFeeDiscount()` 命中就回;`persistDiscount()` 與 `storage` 事件時設 `cached = null`。
三行,行為完全等價(`persistDiscount` 本來就已經在通知所有訂閱者了)。

**風險**:低。`subscribe`(L47-54)已同時掛 module listener 與 `window.addEventListener("storage")`,
兩條失效路徑都覆蓋得到。測試在 `fee-discount.test.ts`。

**Effort**:S

---

### F6-05 [medium · allocation] `signal-model` 的 `arrivalOrder` 被四支函式各複製一次,且 `SignalRail` 無 memo

**位置**:`src/lib/signal-model.ts:237-239` + `src/components/stock/SignalRail.tsx:174-188`

```ts
// signal-model.ts
function arrivalOrder(group: SignalGroup): SignalMsg[] {
  return [...group.items].reverse();
}
// groupKindLabels / groupRuleNames / groupPolicyTags / groupPolicies 各呼叫一次
```

```tsx
// SignalRail.tsx:174 —— 檔內 grep memo 零命中
{groupSignals(signals).map((group) => {
  const segments = groupKindLabels(group);
  const ruleNames = groupRuleNames(group);
  ...
  const tags = groupPolicyTags(group);
  const policies = groupPolicies(group);
```

**頻率**:SignalRail 是 StockPage 的子元件、無 `React.memo` → 隨主樹每次 commit 重繪
(開盤 ~10 次/秒)。`mergeSignals` 的 `cap = 200`(`signal-model.ts:171`)是上界。

**影響**:最壞 200 組 × 4 個複本 = 800 個陣列 / render,~8,000 陣列/秒。純 JS 時間仍在
µs 級,**真正的花費是 200 個 `<li>` 的 vdom 重建**(那一半是 F4 的題)。列入這裡是因為
lib 的介面設計(四支各自 `arrivalOrder`)直接製造了這個放大係數。

**修法**:
1. `SignalRail` 外包 `const groups = useMemo(() => groupSignals(signals), [signals])`。
2. `signal-model` 開一支 `groupView(group)` 一次算完四樣東西(共用一份 `arrivalOrder` 結果)。
3. `SignalRail` 的 `<li>` 抽成 `memo` 子元件,key 已經是穩定的 `group.key`
   (檔內 L185-189 已經為了 key 穩定性做過設計)。

**風險**:`groupKindLabels` / `groupRuleNames` / `groupPolicyTags` / `groupPolicies`
的「到達序」口徑是 §4 契約點名的東西(與 Discord `rows[0]` 同口徑)。合併成一支時
**四者的順序語意必須逐字保持**,`signal-model.test.ts` 的「政策組」節與
`useSignalAlerts.test.tsx` 會抓到順序改變。

**Effort**:S

---

### F6-06 [medium · tooling] 測試迴圈 48 s,其中 jsdom environment 累計 212 s

**位置**:`frontend/vite.config.ts:25-28`

```ts
  test: {
    environment: "node",
    include: ["src/**/*.test.{ts,tsx}"],
  },
```

99 個測試檔各自靠 `// @vitest-environment jsdom` 檔頭覆寫(`grep -rln "vitest-environment jsdom" src` = 99)。

**實測**:
```
Duration 48.18s (transform 26.24s, collect 125.73s, tests 240.41s, environment 212.83s, prepare 30.97s)
```

`environment 212.83s` 是各 worker 累計的「建 DOM 環境」時間 —— 幾乎與實際跑測試的時間同級,
而它 100% 是固定成本。

**修法**:
1. 換 `happy-dom`(`environment: "happy-dom"` + `environmentMatchGlobs` 或維持檔頭覆寫)。
   happy-dom 的建立成本通常是 jsdom 的 1/3–1/5。
2. 或設 `test.pool: "threads"` + `poolOptions.threads.isolate: false`,讓同一 worker 重用環境
   —— 但 `trading-calendar.ts` 有**模組級可變狀態** `holidaySet`,關掉 isolation 會讓
   `clearHolidays()`(L26-28,註解明說「模組級狀態會跨 it / 跨 describe 外溢」)的責任
   從「每檔一份新模組」變成「測試自己要清乾淨」—— **這條要先盤過才能開**。

**風險**:happy-dom 與 jsdom 的 API 覆蓋不完全一致(`getBoundingClientRect`、
`ResizeObserver`、SVG 相關)。本專案有 `useContainerSize`、大量 SVG 元件與
`frontend-testing` skill 記錄的 Radix Tabs jsdom 不可靠問題 —— **要一次跑全量 3069 條確認**,
不是換完就算。屬於 dev-loop 改善,對 prod runtime 零影響。

**Effort**:M

---

### F6-07 [medium · correctness-risk] ESLint 沒有 `eslint-plugin-react-hooks`

**位置**:`frontend/eslint.config.js:10-20`

```js
extends: [js.configs.recommended, ...tseslint.configs.recommended],
...
plugins: { "react-you-might-not-need-an-effect": reactYouMightNotNeedAnEffect },
rules: { "react-you-might-not-need-an-effect/you-might-not-need-an-effect": "warn" },
```

`package.json` 的 devDependencies 也沒有 `eslint-plugin-react-hooks`。

**為什麼這在效能區塊值得記**:本專案大量使用「deps `[]` 的常駐閉包 + ref 同步」這個 pattern
(`lib/commit-ref.ts` 整支就是為此存在,檔頭 L2-6 寫明「常駐 WS hook 的 handler 是 deps `[]`
的閉包,讀不到最新 state → merge 基底改由 ref 取」)。這個 pattern 的兩種失效方向都沒有靜態守門:
- **漏 dep** → stale closure → 資料靜默錯(`commit-ref` 就是為了堵其中一種);
- **多餘 dep** → effect 反覆 cleanup/setup → **WS 重連 / 重訂閱風暴**,這是純效能問題。

`exhaustive-deps` 是唯一能機械抓到後者的工具。專案已經有兩支 hook 的效能問題
(記憶中 `refetchInterval: false` 同病五 hook、`setOptions` 每 render 重排計時器)
都屬同一族。

**修法**:裝 `eslint-plugin-react-hooks`,`rules-of-hooks: error` + `exhaustive-deps: warn`
(先 warn,因為既有程式碼刻意用 deps `[]`,會一次噴出大量存量 —— 依 CLAUDE.md 的
react-doctor 慣例「只有新增 finding 算 FAIL,存量不擋」同款處置)。

**風險**:存量 finding 可能上百條,不可一次全改(鐵則 B scope 紀律)。

**Effort**:S(裝 + 設 warn)/ L(清存量,不建議現在做)

---

### F6-08 [low · bundle] 沒有 `build.target`,預設向下相容到 Safari 16

**位置**:`frontend/vite.config.ts`(整支沒有 `build` 區塊)

Vite 6 的 `build.target` 預設 `'baseline-widely-available'`(≈ chrome107 / firefox104 /
safari16 / edge107)。實測產物含 `??` 但不含 `?.` —— 有一部分語法被降級了。

**在這個專案**:唯一的客戶端是同一台機器上的 Chrome,永遠是最新版。
`target: 'esnext'` 可以省掉所有 downlevel helper 與語法重寫。

**收益誠實話**:大概省個位數 KB 與微不足道的 parse 時間。**這不是效能修復,是清理。**
單獨做不值得,和 F6-09 一起改一行即可。

**Effort**:S

---

### F6-09 [low · bundle] 沒有 `manualChunks`、沒有 bundle 分析工具、沒有 size budget

**位置**:`frontend/vite.config.ts`

- 主 chunk 386 KB 裡有 177 KB 的 react-dom —— 它永遠不變,卻和每次都變的 App code 綁在同一個
  content-hash 檔名裡。每次 `npm run build` 使用者都要重載 386 KB。
- 在 localhost 上這是 **~3 ms 的磁碟讀**,完全不痛。真正的價值只有一個:
  **`npm run build` 後開頁的那一下**(CLAUDE.md §4 的「版本落差膠囊亮起先 npm run build」流程)。
- devDependencies 裡沒有任何 bundle 分析工具;本次分析是我手寫 sourcemap VLQ 解碼做的。

**修法(低優先)**:
```ts
build: {
  target: "esnext",
  rollupOptions: {
    output: { manualChunks: { vendor: ["react", "react-dom", "scheduler"] } },
  },
},
```
+ devDep 加 `rollup-plugin-visualizer`(只在 `--mode analyze` 掛)。

**Effort**:S

---

### F6-10 [low · blocking-io] `index.html` 從 Google Fonts CDN 載 render-blocking stylesheet

**位置**:`frontend/index.html:7-13`

```html
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans+TC:wght@400;500;700&display=swap" rel="stylesheet" />
```

**影響**:一個要下實單的本機終端,開頁時要等兩次 DNS + 兩次 TLS + 一次
render-blocking stylesheet 才首次繪製。`display=swap` 保證文字不會 FOIT,但 CSSOM 仍
阻塞 first paint。外網不通 / DNS 慢時,開頁會多等到瀏覽器放棄為止。

**修法**:自架字型。**但有個大坑必須先量**:`IBM Plex Sans TC` 是 CJK 字型,
Google Fonts 用 `unicode-range` 切成上百個小 woff2 只按需載;天真地自架一顆完整
TC woff2 可能是 **數 MB**,比現況差很多。正確做法是用 `subset-font` / `glyphhanger`
對實際用到的字元集(繁中盤面詞彙 + 數字 + 英文代號)做 subset,通常能壓到 100–300 KB。

**Effort**:M(要做 subset 與驗證缺字)

---

### F6-11 [low · allocation] `otcSourceDead` 每次呼叫兩次 `Object.keys()` 全表配置

**位置**:`src/lib/index-source-health.ts:32-34`(程式碼見 §3 HP-5)

`minutes` 盤中最多 ~270 鍵,只為判斷「空不空」/「有沒有 ≥2 個」。呼叫點
`MarketPane.tsx:379`,約 1–2 次/秒。

**修法**:
```ts
function atLeast(obj: Record<string, number>, n: number): boolean {
  let c = 0;
  for (const _ in obj) if (++c >= n) return true;
  return false;
}
```
**Effort**:S

---

### F6-12 [low · allocation] `searchStocks` 每按一鍵配置 2,401 個大寫字串

**位置**:`src/lib/stock-search.ts:30-32`(程式碼見 §3 HP-6)

**修法**:呼叫端(`WatchlistSidebar:195` / `WatchlistManagerDialog:170`)把 `names`
用 `useMemo` 預處理成 `{ code, codeUpper, name }[]`,或在 lib 內存一顆
`WeakMap<readonly StockName[], string[]>` 的大寫索引。

**風險**:`searchStocks` 的排序與去重語意(代碼前綴優先、各段內代碼升序)有測試釘住,
改的只是大寫來源。**Effort**:S

---

### F6-13 [medium · observability / quant-gap] 前端完全沒有效能量測探針

**證據**:
- `lib/dev-perf-guard.ts` 是全庫唯一碰 Performance API 的檔,而它的工作是**清掉** measure,
  不是產生量測(而且 `import.meta.env.DEV` 才裝,`main.tsx:11-14`)。
- `grep -rn "performance.mark\|performance.measure" src` 除了 dev-perf-guard 之外零命中。
- 沒有任何「WS 訊息到達 → 畫面更新」的端到端延遲量測;沒有 frame budget 監測;
  `ws.py::WsBroadcaster.dropped` 的丟包統計只在**後端**,前端拿不到對應的「我來不及畫」指標。

**為什麼這是 quant 系統的硬缺口**:要把系統改造成「下實單、速度夠快」,第一件事是
**能證明它快**。現在無法回答:開盤最忙的那一秒,從後端 `_flush_ticks` 發出到閃電梯
DOM 更新是幾毫秒?掉了幾幀?

**修法建議**:
1. 加一支 `lib/perf-probe.ts`(prod 也裝,可用 localStorage 開關):
   - 在 WS `onmessage` 打 `performance.mark`,在該批 commit 的 `useEffect` 收尾打 measure;
   - 用 `requestAnimationFrame` 差值做 long-frame 計數(> 50 ms 算掉幀),每 60 s 印一次
     p50/p95/max —— 與後端「佇列滿」的 60 s 節流 WARNING 同款節奏,對帳方便。
2. 或直接用 Chrome DevTools 的 `performance_start_trace`(本 repo 已有
   `chrome-devtools-mcp` skill,CLAUDE.md 記憶裡也有「trace 93 s >50ms=0」這種判準前例),
   走既有的盤中取證流程,不必自建。

**Effort**:M

---

### F6-14 [low · architecture] 沒有 Web Worker 邊界的設定

**證據**:`grep -rn "new Worker\|?worker" src` 零命中;`vite.config.ts` 沒有 `worker` 區塊。

所有 accum 合併、SVG path 生成、指標計算都在主執行緒,與 React commit 搶同一條 timeline。
這是 F2/F4 的核心題,但**設定面的門檻在我這裡**:Vite 原生支援 `import W from './x?worker'`,
若要走 module worker 還要設 `worker.format: 'es'`。真要搬計算到 worker,
`vite.config.ts` 要先長出 `worker` 區塊,而且 `types.ts` 的 wire 型別要能在兩邊共用
(現在 `types.ts:1` 有 `import type { HandoverProgress } from "@/components/ConnectionBadge"`
—— **型別檔反向依賴元件檔**,搬進 worker 時這條會把元件模組拖進去)。

**Effort**:L(真做的話)/ S(只把 `types.ts` 的反向依賴斬掉,先鋪路)

---

### F6-15 [low · bundle] `types.ts` 反向依賴元件檔

**位置**:`src/types.ts:1`

```ts
import type { HandoverProgress } from "@/components/ConnectionBadge";
```

純 `import type`,編譯後會被抹掉,**runtime 零成本**。但它讓「wire 型別」這一層在
模組圖上依賴 UI 層,任何要把 `types.ts` 拿去別處共用(worker / 另一個 bundle /
後端 codegen)的動作都會撞到。

**修法**:`HandoverProgress` 搬到 `types.ts`,`ConnectionBadge` 反過來 import。
**Effort**:S

---

## 5. 硬約束 —— 這個區塊裡的跨檔契約

**本區塊的檔案有 7 支被後端 pytest 直接讀原始碼字面。** 這是改造時最容易踩到的地雷:
搬檔、改常數寫法、甚至只是 formatter 重排,都可能讓後端 parity 測試紅或(更糟)
靜默失準。

唯一入口是 `tests/helpers/frontend_source.py::read_frontend_source(rel)`
(讀 `frontend/src/<rel>`,檔不存在直接 raise),讀者:

| 後端測試 | 讀的前端檔 | 釘住什麼 |
|---|---|---|
| `tests/server/test_bars.py:992` | `lib/day-bars-rollover.ts` | `DAILY_FINAL_TIME = [14, 0]` **等值** |
| `tests/server/test_screen_engine.py:39` | `lib/constants.ts` | `SCREEN_GROUP_NAME = "盤前篩選"` |
| `tests/test_stock_watchlist.py:271` | `lib/constants.ts` | `WATCHLIST_LIMIT = 150` |
| `tests/capital/test_close.py:161` | `lib/close-order.ts` | `CLOSE_KIND` ↔ 後端 `_CLOSE_MAP` 回補單種 |
| `tests/capital/test_models.py:158,172` | `types.ts` | `AVG_SOURCES = ["broker","fill"]` ⊆ `get_args(AvgSource)`;`PositionKind ⊆ TradeKind` |
| `tests/test_corr_config.py:269,272` | `components/corr/river-colors.ts` + **`index.css`** | 江波圖調色盤色數 ≥ 腿數(11) |

**連 `src/index.css` 都被後端測試讀**(`tests/test_corr_config.py:272`,對
`--color-river-N` token)。所以 §1.4 說的「CSS 不需要瘦身」除了「沒必要」之外,
還有第二個理由:**動它會動到契約**。

另外三組不經 `read_frontend_source` 但同樣是硬約束(CLAUDE.md §4 點名):
- `lib/signal-params.ts` 的 `PARAM_FIELDS` / `COOLDOWN_MIN/MAX` ↔ 後端 `signal_rules.PARAM_SPECS`,
  共用 golden fixture `tests/fixtures/signal_param_specs.json`,兩邊各一條 parity 測試。
- `lib/signal-model.ts` 的 `SignalKind` / `PolicyTag` / `kindLabel` 文案 ↔ 後端 `_kind_text`
  **逐字對齊**(「掃單簇 +0.00%」零也帶正號)。
- `vite.config.ts:7` 的 `BACKEND` port 8721 ↔ `run.ps1:29 $port` ↔ 後端 `TXO_SERVER_PORT`
  (run.ps1 L26 註解點名三邊同動)。

**改造規則**:
1. 上表 7 支檔案**不可搬目錄、不可改檔名**。要拆模組就在原檔留 re-export。
2. 那幾顆常數**不可改寫法**(`[14, 0]` 不要變成 `[14,0]` 或 `{hh:14,mm:0}`,
   `150` 不要變成 `1.5e2`)—— 後端讀的是字面。
3. 動這些檔之前先跑一次後端 `pytest -q tests/server/test_bars.py tests/server/test_screen_engine.py
   tests/test_stock_watchlist.py tests/capital tests/test_corr_config.py`,確認 baseline 綠。

---

## 6. 工具選型建議與取捨

### 6.1 建議導入

| 工具 | 用在哪 | 解決什麼 | 代價 | 判斷 |
|---|---|---|---|---|
| FastAPI `StaticFiles`(**不是前端工具**) | `copycat/server/app.py` | F6-02:把 Node 從資料路徑拿掉 | 後端多一個 mount;每次改前端要 build | **強烈建議** |
| `extendTailwindMerge({cacheSize})` 或改用純 `clsx` | `lib/utils.ts` | F6-03:cache thrash 23× | 選項 2/3 要人工核 class 衝突 | **建議** |
| `eslint-plugin-react-hooks` | `eslint.config.js` | F6-07:effect 重訂閱風暴的唯一靜態守門 | 存量 warning 多 | **建議(先 warn)** |
| `happy-dom` | `vite.config.ts` test | F6-06:212 s 的環境建立成本 | API 覆蓋差異,要全量驗 | **有條件導入**(先在分支跑全量) |
| `rollup-plugin-visualizer` | devDep + `--mode analyze` | 讓 bundle 可持續觀測 | 零 runtime 成本 | **建議** |
| 自寫 `lib/perf-probe.ts` | 新檔 | F6-13:前端沒有任何量測 | ~80 行 | **建議** |

### 6.2 不建議(過度工程 / 收益為零)

| 工具 | 為什麼不 |
|---|---|
| **rolldown-vite** | `vite build` 實測 **2.16 s**。rolldown 的賣點是把分鐘級 build 壓到秒級 —— 這裡沒有可壓的東西。beta 階段換核心 bundler,為的是省 1.5 秒。**明確不要。**(`node_modules/@rolldown/pluginutils` 只是 `@vitejs/plugin-react` 的 transitive dep,不代表專案用了 rolldown) |
| **`@vitejs/plugin-react-swc`** | 同上。build 2.16 s、231 modules。SWC 只影響 transform 階段,收益 < 1 s。dev HMR 或許快一點,但 F6-01 的結論是**看盤根本不該用 dev**。 |
| **Turbopack / Rspack / esbuild 直跑** | 同上,而且會失去 vite 的 plugin 生態(`@tailwindcss/vite`、`sha-plugin`)。 |
| **`orjson` 的前端對應物(如 `fast-json-parse`)** | 瀏覽器的 `JSON.parse` 是 C++ 實作,沒有更快的 JS 替代品。WS payload 的解析成本在 F2 那邊量,不是換 library 能解的。 |
| **CSS 瘦身 / PurgeCSS** | Tailwind v4 本來就只產生用到的 class;7.9 KB gzip;而且 `index.css` 被後端測試讀(§5)。 |
| **拆更多 lazy chunk** | localhost 載入,chunk 數量對使用者零感知;拆多了反而多一輪 module graph 解析。 |
| **HTTP/2 / Brotli / CDN** | 同一台機器,loopback。 |

### 6.3 與 bundle 相關的「圖表庫」選型參考(主體在 F4,這裡只給 size 數字)

若 F4 決定把手刻 SVG 換成 canvas:
- **uPlot**:~47 KB min / ~16 KB gzip。最小、最快,但 API 原始,要自己做 crosshair / 標記。
  以本專案「一張圖幾百個點、要 10 fps 更新」的需求,uPlot 是甜蜜點。
- **lightweight-charts**(TradingView):~200 KB min。K 線 / 疊線開箱即用,但 bundle 翻倍,
  而且它的 API 模型(series / priceScale)與本專案既有的「毫元整數 + 台股 tick 表」
  口徑要接一層 adapter。
- 兩者都會讓主 chunk 或 CandleChart chunk 明顯變大,但**在 localhost 這不構成理由**
  —— 選型應該只看「主執行緒每幀花多少 ms」,不看 KB。

---

## 7. 這裡不要動

1. **`lib/format.ts`** —— `Intl.NumberFormat` 已經在 module 層 hoist(L1-2),這是正確寫法。
2. **`lib/pnl-format.ts:13` 與 `components/stock/OrderBook.tsx:30` 的 `toLocaleString("en-US")`**
   —— 看起來像「每次都建 formatter」,**實際不是**。實測(Node 22 / V8):
   ```
   cached nf.format()              0.398 us/call
   (n).toLocaleString("en-US")     0.277 us/call     ← 比 hoist 的還快
   new Intl.NumberFormat().format  20.147 us/call    ← 這才是慢的寫法
   ```
   V8 對 `Number.prototype.toLocaleString` 有 per-locale 的內部快取。**全庫 grep
   `new Intl.` 只有 format.ts 那兩行 module 層,零個在函式內** —— 這條慣例是乾淨的,不用改。
3. **`lib/storage.ts`** —— 4 個獨立 warn 旗標 + per-key parse 旗標 + 空字串走「無資料」而非
   `JSON.parse("")`,每一條都有註解寫明理由,而且是全庫 45 處裸 localStorage 收斂的成果。
   要改的是**呼叫頻率**(F6-04),不是這一層。
4. **`lib/day-bars-rollover.ts`** —— 90 行註解推導出的兩道界 + 秒級量化 + `retryEmpty` 分流,
   其中「回值秒級量化避免 TQ 每 render 重排計時器」正是效能修正本身。而且 `DAILY_FINAL_TIME`
   是後端測試直讀的字面(§5)。**整支不要碰。**
5. **`lib/trading-calendar.ts` 的模組級 `holidaySet`** —— 檔頭 L3-8 寫明它不是偷懶,是因為
   消費端是 5 個 `refetchInterval` callback(零參數、非 React 情境)。改成 context 會把整條鏈翻掉。
6. **`lib/watchlist-model.ts::isSameWatchlist` 的 `JSON.stringify` 深比** —— 每次使用者動作
   一次,不在 tick 路徑;它擋的是「內容相同的 PUT → 後端全量 TC4 UNSUB/SUB」,
   正確性價值遠大於微秒。
7. **`lib/dev-perf-guard.ts`** —— 它本身就是一個效能修復,而且只在 DEV 裝
   (`main.tsx:11-14`),用 PerformanceObserver 不用 setInterval(避開背景分頁 timer throttling)、
   用回呼增量累加不用 `getEntriesByType` 全掃(review C-1 已經處理過)。零改動空間。
8. **`lib/fetch-timeout.ts`** —— body 也在 timeout 內、手寫 AbortController 不依賴
   `AbortSignal.any`、`aborted.catch(() => {})` 避免 unhandled rejection。每個決定都有理由,
   而且它是「TQ query 永久凍結」這個 bug 的修復本體。
9. **CSS / Tailwind 設定** —— 39 KB / 7.9 KB gzip,227 個 arbitrary token 全是靜態字面,
   零 template literal。而且 `index.css` 被後端測試讀。
10. **tsconfig** —— `strict` + `noUncheckedIndexedAccess` + `noUnused*` 已經是上限。
    `tsc -b --force` 8.4 s 對 160 個檔 / 75k LOC 是正常值。

---

## 8. 量測方法(可重複)

所有指令在 `C:\side-project\copycat\frontend`,**全部輸出到 scratchpad,不碰 `dist/`**。

### 8.1 bundle 大小
```bash
npx vite build --outDir "<SCRATCH>/distprobe" --emptyOutDir
```
讀 vite 自己印的 `gzip:` 欄。

### 8.2 bundle 逐模組歸戶(minified bytes)
```bash
npx vite build --sourcemap --outDir "<SCRATCH>/distmap" --emptyOutDir
```
然後解 sourcemap 的 `mappings`(VLQ),把每個 generated segment 到下一個 segment 的
column 距離歸給它的 `sources[i]`。本次用的腳本在報告產出時是 inline node -e;
若要常態化,改用 `rollup-plugin-visualizer`(`--mode analyze` 專用)。

**注意**:`sourcesContent` 的長度是**原始碼**長度,會嚴重高估(tailwind-merge 原始碼
105 KB、minified 只有 27 KB)。一定要走 mappings 歸戶。

### 8.3 型別檢查
```bash
npx tsc -b --force        # 全量,實測 8.437 s
npx tsc -b                # 增量(吃 tsconfig.app.tsbuildinfo)
```

### 8.4 測試迴圈
```bash
npx vitest run --reporter=dot
```
看尾巴的 `Duration … (transform / collect / tests / environment / prepare)` 分項。
`environment` 是 jsdom 建立成本(本次 212.83 s 累計)。

### 8.5 `cn()` / Intl micro-benchmark
```bash
node --input-type=module -e "
import {twMerge} from 'tailwind-merge'; import clsx from 'clsx';
const cn=(...a)=>twMerge(clsx(a));
// 先 warm 50k 次,再計時 200k 次;另測 cache-miss(每次唯一 class)
"
```
本次數據:clsx 0.048 µs / twMerge hit 0.168 µs / twMerge miss 3.851 µs /
`toLocaleString("en-US")` 0.277 µs / hoisted `nf.format` 0.398 µs /
`new Intl.NumberFormat().format` 20.147 µs。

### 8.6 要證明 F6-01 / F6-02(這兩條值得真環境量)
1. **dev vs preview 對照**:開盤時分別用 `npm run dev`(:5173)與 `npm run preview`(:4173)
   各開一次個股頁 + 群組圖牆,用 Chrome DevTools Performance 錄 60 s,比對:
   - Scripting 總時間
   - long frame(> 50 ms)次數 —— CLAUDE.md 記憶裡已有「trace 93 s >50ms=0」的前例判準
   - renderer 記憶體成長斜率
2. **Node proxy 開銷**:在 preview 跑的同時看 Task Manager 的 node.exe CPU%;
   或先手動把 dist 用 `python -m http.server` 之外的方式直連 8721 開一次
   (需要後端先掛 StaticFiles),比對同一段時間的 node.exe CPU 與 WS 訊息到達間隔抖動。
3. **判準建議**:preview 相對 dev 的 Scripting 時間應降 ≥ 40%;
   拿掉 Node proxy 後 node.exe 在盤中應該完全不在 CPU 榜上。

---

## 9. Open questions(需要 user 回答或需要真環境才知道)

1. **`run.ps1` 走 dev 是刻意的還是漏改?** CLAUDE.md §1 說得很明白要用 preview,
   但唯一的啟動腳本是 dev。如果 user 平常其實是手動開 preview,那 F6-01 降為
   「腳本與文件不一致」的文件問題;如果 user 都是按 `run.ps1`,那它是本區塊最大的效能發現。
2. **後端掛 StaticFiles 服務 dist 有沒有被否決過?** 這牽涉 `run.ps1` 的兩行程結構與
   §4 關機預算的 taskkill 樹。如果之前有過拍板(例如「要留 vite 的 HMR 當熱修通道」),
   F6-02 的修法要換成建議 B。
3. **`cn()` 的 tailwind-merge 有沒有實際靠它解過 class 衝突?** 需要 grep 152 個呼叫點
   逐一核;我只確認了「沒有動態 arbitrary class」。這決定 F6-03 能不能做到選項 3。
4. **前端到底掉不掉幀?** 目前零量測(F6-13)。開盤時 50 張群組卡 + 閃電梯 + 訊號 rail
   同時跑,主執行緒有沒有超過 16.7 ms 的 frame —— 沒有這個數字,所有「這裡慢」的
   判斷都只是推測。建議先做 F6-13 的探針,再決定 F2/F4 的改造深度。
5. **happy-dom 能不能通過全量 3069 條?** 本專案有 `useContainerSize`、大量 SVG、
   `frontend-testing` skill 記錄的 Radix Tabs jsdom 不可靠案例 —— 換 DOM 實作的風險
   要跑過才知道,不能紙上決定。
6. **字型自架的 subset 範圍?** 需要先掃出整個 app 實際用到的繁中字元集(含後端送來的
   股票名稱 2,401 檔的所有字)才能估 woff2 大小。這可能是幾千個字,subset 後仍不小。
