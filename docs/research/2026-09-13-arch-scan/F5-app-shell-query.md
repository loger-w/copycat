# F5 — 前端:App shell、路由、TanStack Query 與輪詢層

分析日期 2026-09-13 · 對象 `C:/side-project/copycat/frontend/src`
範圍:`App.tsx` / `main.tsx` / 五顆 tab 的容器元件 / 22 支 hook / queryClient 設定 / 輪詢層

---

## 0. 一句話結論

**這個區塊的效能瓶頸不在 TanStack Query,也不在 bundle 大小 —— 在「WS 推播 → App 層 setState → 整棵樹重繪」這條路。**

盤中開盤後,後端每秒對**每一檔**自選股各送一則獨立的 `watchlist_quote` WS 訊息(80–150 則/s),
期貨引擎每 0.1 s 對每個 dirty 商品各送一則(最多 30 則/s)。這兩條流的 `setState` 都落在 `App.tsx`,
而 WebSocket `message` 事件各自是獨立的 macrotask —— **React 的 automatic batching 合併不了它們**。
結果是 **App 整棵樹每秒被重繪 110–180 次**,而且因為五顆 tab 用 `hidden` 保留(不是 unmount),
每一次重繪都會走過**沒在看的那幾頁**:TXO 選擇權表、台股綜合頁的兩張 pane + 漲跌停表、
自選側欄的 80 列、群組圖牆的 80 張卡。

Query 層本身寫得相當克制(函式形 `refetchInterval`、`subscribed` 退訂、`gcTime: Infinity` 有界鍵集、
per-observer 輪詢收斂到單一 provider),只有三個具體洞:全域 `refetchOnWindowFocus` 沒關、
`breadth-rows` 每 10 秒拉一份全市場、`queryClient` 完全沒有 `defaultOptions`。

---

## 1. 架構地圖

### 1.1 掛載樹(實際執行期形狀)

```
main.tsx
 └ StrictMode                       ← dev 下所有 effect / updater double-invoke
   └ QueryClientProvider  client = new QueryClient()   ← 零 defaultOptions(見 F5-04)
     └ App                          ← 全站唯一的「資料流集散地」
        ├ [hook] useTradingCalendar()      TQ  5 min(背景分頁照跑)
        ├ [hook] useIndexStream()          WS /ws/index      ~1–2 則/s   → setState ×4
        ├ [hook] useBreadth()              WS /ws/breadth    ~1 則/min   → setState
        ├ [hook] useCapitalStream()        WS /ws/capital    事件驅動 + TQ 15 s / 30 s
        ├ [hook] useSignalAlerts()         bus 訂閱          事件驅動
        ├ [hook] useStockStream(code,…)    WS /ws/stock      ★ 80–150 則/s → setState
        ├ [hook] useFuturesStream()        WS /ws/futures    ★ ≤30 則/s   → setState
        ├ [hook] useFuturesBars("TXF",…)   TQ 60 s(個股頁台指期疊線開著時)
        ├ [hook] useChartToggles()         useSyncExternalStore(localStorage 直讀)
        │
        ├ nav ─ CalendarBadges / VersionDriftBadge / IndexBar
        ├ tabpanel txo      **恆掛**    TxoPage(WS /ws/txo-pnl)
        │                                 └ MetricsBar / PnlChart / QuoteTable / OrderPanel(TQ 30 s)
        ├ tabpanel stock    visited 後恆掛  lazy StockPage
        │                                 ├ SignalRail(groupSignals,未 memo)
        │                                 ├ SignalRulesDialog(恆掛只切 open)
        │                                 ├ WatchlistSidebar(80–150 列,未 memo)
        │                                 └ main ─ GroupGridView(80 張 memo 卡)or 單檔圖
        ├ tabpanel futures  visited 後恆掛  lazy FuturesPage
        ├ tabpanel index    **恆掛**    lazy IndexPage
        │                                 ├ MarketPane ×2(各自一支 useMarketBars 60 s)
        │                                 ├ BreadthBand + AdvanceDeclineChart
        │                                 └ LimitListSection(useBreadthRows 10 s,~2800 列 payload)
        ├ tabpanel corr     visited 後恆掛  lazy CorrPage(WS /ws/corr 1/s + /ws/river 1/s)
        ├ RightRail                     memo(ctx)  ← 全站唯一有 memo 邊界的頁級元件
        └ ToastStack
```

關鍵事實:
- **`visited.index` 與 `txo` 恆為 `true`**(`App.tsx:125-131`)。台股綜合頁與選擇權頁**從開站第一秒就掛著**,
  而且永遠不卸載。切走只是 `hidden`(CSS `display:none`),React 照樣 render。
- **只有 `RightRail` 有 `memo`**。`StockPage` / `IndexPage` / `FuturesPage` / `CorrPage` / `TxoPage` 全裸。
  就算加 memo 也擋不住 —— `stream` / `breadth` / `twse` 這些 prop 每次 App render 都是新值。
- code splitting 有做(四個 `lazy`),但只切了「首訪前不載」,**首訪後就永久掛著**。

### 1.2 資料流(誰在推、推多快)

| 來源 | 節奏 | 每秒訊息數(盤中) | setState 落點 | 重繪範圍 |
|---|---|---|---|---|
| `/ws/stock` `watchlist_quote` | 後端 1 s 節流,**per-code 各一則** | **80–150** | `App`(`useStockStream`) | 整棵樹 |
| `/ws/stock` `ticks` | 後端 0.1 s 打包,一則含全部 | ≤10 | `App` + tick 匯流排 | 整棵樹 + 命中的卡 |
| `/ws/futures` | 後端 0.1 s flush,**per-product 各一則** | ≤**30** | `App`(`useFuturesStream`) | 整棵樹 |
| `/ws/index` | 每拍 ~1 s | 1–2 | `App`(`useIndexStream`) | 整棵樹 |
| `/ws/breadth` | 每分鐘一格 | ~0.02 | `App`(`useBreadth`) | 整棵樹 |
| `/ws/txo-pnl` | TXO 引擎推播 | 視行情 | `TxoPage` | TxoPage 子樹 |
| `/ws/corr` | 每秒全量快照 | 1 | `CorrPage` | CorrPage 子樹 |
| `/ws/river` | 每秒 delta | 1 | `CorrPage` | CorrPage 子樹 |
| `/ws/capital` | 成交/委託事件 | 稀疏 | 無(只 invalidate) | — |

**合計:App 這一層每秒被 setState 110–180 次。**

後端側的證據(不是推測):

```python
# copycat/server/stock_engine.py:1813-1832
async def _flush_watchlist_loop(self) -> None:
    """側欄節流:1s 合併一則(design §2.4)+ 試撮窗翻轉補推(D3)。"""
    while True:
        await asyncio.sleep(self._throttle)
        ...
        dirty, self._dirty_watchlist = self._dirty_watchlist, set()
        for code in dirty:                       # ← 每一檔各 publish 一則
            state = self._states.get(code)
            if state is None or state.last is None:
                continue
            self._publish(self._quote_payload(code))
```

「1s 合併」合併的是**同一檔在這一秒內的多筆 tick**,不是「把各檔合成一則」。
80 檔都有成交 = 80 個 WS frame。

```python
# copycat/server/futures_engine.py:8-9
- 廣播 per-product coalesce:quote 只更新 state + 標 dirty,每 `flush_interval_secs`
  (prod 0.1 s)把每個 dirty 商品各送**一則最新 payload**
```

前端側沒有任何緩衝層:

```ts
// frontend/src/lib/ws-reconnect.ts(檔頭契約)
/** 收到的是 `JSON.parse` 後的值;parse 失敗只 warn 不呼叫,`{type:"ping"}` 心跳被過濾。 */
onMessage(msg: unknown): void;
```

每一則 frame → 一次 `JSON.parse` → 一次 `handle()` → 一次 `setState` → 一次 commit。

---

## 2. 熱路徑逐條

### HP-1 `watchlist_quote` → `setWatchlist` → App 重繪 **(80–150 次/秒)**

```ts
// frontend/src/hooks/useStockStream.ts:413-425
case "watchlist_quote": {
  const q: WatchlistQuote = {
    p: (msg.p as number | null) ?? null,
    chg_pct: (msg.chg_pct as number | null) ?? null,
    ...
  };
  setWatchlist((prev) => ({ ...prev, [msg.code as string]: q }));
```

每則訊息:
1. 建一個新的 `WatchlistQuote` 物件(9 欄);
2. `{ ...prev, [code]: q }` —— **整份 80–150 鍵的物件淺複製**;
3. `setState` → App re-render。

單秒成本:80 次淺複製 × 80 鍵 = **6,400 次屬性複製**,外加 80 個新物件、80 次完整 render pass。

`useStockStream` 掛在 App 層是刻意的(D-3:右欄要跟著當前 tab 的標的),
而且 `App.tsx:170-177` 的註解已經**預先承認了這個代價**:

```
// 取捨(review phase5 P2-3):…且 watchlist_quote 的 setState 現在落在 App 層 → 每秒一批側欄報價會重繪整棵樹。
// 判定可接受:…(b) App 層本來就會因 useIndexStream 每則指數推播重繪,不是新增的重繪類別。
// 若日後量測到掉幀,先做的是讓 useStockStream 吃 `enabled` 參數
```

這個判定在「每秒一批」的前提下是對的 —— 但實際是**每秒 80–150 批**,
與 `useIndexStream` 的 1–2 次/秒差了兩個數量級。這不是同一個重繪類別。

### HP-2 `futures` WS → App 重繪 **(≤30 次/秒)**

```ts
// frontend/src/hooks/useFuturesStream.ts:96-100
const out = applyFuturesMsg(cur, msg);
if (out.next !== cur) {
  stateRef.current = out.next;
  setState(out.next);          // ← App 重繪
}
```

`App.tsx:248-251` 的註解已經點名這條流是「全站最重的 render」的打穿者,
並用兩腿 `useMemo` 把 `railCtx` 護住了 —— 但護的只有 `RightRail` 一個節點。
`futuresStream.state` 換 identity → `futProd` 換 → App render → **其餘四頁全部重繪**。

停在個股頁時,期貨 10 Hz × 3 商品的每一則,都在重畫自選側欄、圖牆、台股綜合頁與 TXO 表。

### HP-3 App 重繪 → `WatchlistSidebar` 80–150 列全重算 **(跟著 HP-1/HP-2,110–180 次/秒)**

`WatchlistSidebar` 沒有 memo,也沒有任何 row 級別的記憶化。每次 render:

```ts
// frontend/src/components/stock/WatchlistSidebar.tsx:449-461(每一列)
function stockRow(code: string, group: string | null): React.ReactElement {
  const q = quotes[code];
  const name = nameOf.get(code);
  const limit = limitState(q?.p ?? null, q?.upper ?? null, q?.lower ?? null);
  const posRows = posMap.get(code);
  const sec = posRows === undefined ? null : secSummary(posRows, q?.p ?? null, discount);
  const fut = posRows === undefined ? null : futSummary(posRows);
```

`secSummary` 是含手續費/稅的損益現算。每列還有 **6 次 `cn()`** 呼叫
(`cn = twMerge(clsx(...))`,`lib/utils.ts:4-6`)。

```ts
// frontend/src/lib/utils.ts
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
```

單秒成本:150 render × 80 列 × 6 = **72,000 次 twMerge 呼叫/秒**。
`tailwind-merge` 有 LRU cache(預設 500 筆)所以多數是 cache hit,
但 hit 也要先 `clsx` 拼字串 + Map 查詢 —— 不是零成本,而且這裡根本沒有 class 衝突要解。

另外每個群組標題各跑一次 `groupAvgPct(g.codes, quotes)`(`:802`,註解寫「不值得 memo」——
那是在「每秒 render 一次」的前提下算的)。

### HP-4 App 重繪 → 隱藏的 `IndexPage` 全樹重算 **(110–180 次/秒,而且沒人在看)**

`visited.index` 恆 true(`App.tsx:126`),所以只要開過站,IndexPage 就在樹上。
每次 App render 都會走:

- `MarketPane` ×2:各自的 `useContainerSize` / `RadioPills`(標的 3 顆 + 週期 17 顆 = 40 顆 pill,
  每顆一次 `pillClass()` → 一次 `cn()`)
- `BreadthBand` + `AdvanceDeclineChart`(SVG)
- `LimitListSection` → `LimitListBody` → `entries.map(...)`,漲跌停列常態 30–300 列,
  每列 **19 個 `cn()` 位點之中的多數**

`entries` 本身有 `useMemo([data, filter])` 護住(`LimitListSection.tsx:325-328`),
但 `.map()` 產生 React element 這一段沒有,每次 render 都重跑。

### HP-5 App 重繪 → 隱藏的 `TxoPage` 全樹重算

`App.tsx:341` `<TxoPage />` 在 `hidden={tab !== "txo"}` 的 div 裡 —— **無條件 render**。
`snapshot` 非 null 時會走 `MetricsBar` / `PnlChart`(SVG)/ `QuoteTable`(T 字報價,
`rows` 有 memo 但 `rows.map` 沒有)/ `OrderPanel`(還帶一支 30 秒的 `txo-contracts` 輪詢)。

### HP-6 `useSyncExternalStore` 的 localStorage 直讀 **(每次 render × 每個消費端)**

```ts
// frontend/src/hooks/useChartToggles.ts:110-118
function getSnapshot(): ChartToggles {
  const raw = readLocal(CHART_TOGGLES_KEY);     // ← localStorage.getItem,同步
  if (cachedRaw === undefined || raw !== cachedRaw) {
    cached = load();
    cachedRaw = readLocal(CHART_TOGGLES_KEY);   // ← 再一次
  }
  return cached;
}
```

```ts
// frontend/src/lib/fee-discount.ts:41-43, 67-69
export function readFeeDiscount(): number {
  return loadDiscount().value;                  // ← readLocal + clampDiscount 解析
}
export function useFeeDiscount(): number {
  return useSyncExternalStore(subscribe, readFeeDiscount, () => FEE_DISCOUNT_DEFAULT);
}
```

`useChartToggles` 有 8 個非測試消費端、`useFeeDiscount` 有 4 個。
`useSyncExternalStore` 在每次 render **以及** commit 後的一致性檢查各呼叫一次 `getSnapshot`
→ 每個消費端每次 render 至少 2 次 `localStorage.getItem`。
150 render/s × 12 個消費端 × 2 ≈ **3,600 次同步 getItem/秒**。
單次 ~1–3 µs,合計 ~4–11 ms/s —— 不是主因,但屬於「純白燒」的那一類。

### HP-7 `groupSignals` 每 render 重跑

```tsx
// frontend/src/components/stock/SignalRail.tsx:174
{groupSignals(signals).map((group) => {
```

`signals` 上限 200(`mergeSignals` 的 `cap = 200`),`groupSignals` 是 O(n) 但會**配置最多 200 個
group 物件 + 200 個 items 陣列**。150 render/s → 每秒 30,000 個短命物件,純 GC 壓力。
沒有 `useMemo`。

### HP-8 `GroupGridView` 的 memo 邊界(這裡做對了,列出來當對照)

`GroupCard` 有 `memo`,而且父層很用心地把 14 個 prop 全部做成穩定 identity
(`EMPTY_FILLS` / `EMPTY_POSITIONS` / `NOOP_HOVER` / `pick` 用 latest-ref + `useCallback`)。
所以 150 次父層 render 只會做 150 × 80 × 14 ≈ **168,000 次 prop 淺比較**,
而不是 12,000 次卡片重繪。這是全檔最好的一段工程 —— 但它也說明了問題的形狀:
**大家在補 memo 補到極致,而根因是上游每秒 render 150 次。**

---

## 3. Query / 輪詢層全表

### 3.1 `refetchInterval` / `staleTime` / `gcTime` 逐支

| # | hook | queryKey | refetchInterval | staleTime | gcTime | retry | 掛載條件 |
|---|---|---|---|---|---|---|---|
| 1 | `useBreadthRows` | `["breadth-rows"]` | **10 s**(`active` 才排;盤外 = 距 09:01 ms) | 預設 0 | 預設 5 min | 1 | IndexPage 恆掛 |
| 2 | `useCapitalStatus` | `["capital-status"]` | **10 s**(無條件) | 0 | 5 min | 1 | OrderPanel / 各梯 |
| 3 | `useCapitalStream` positions provider | `["capital-positions"]` | **15 s** | 0 | 5 min | 1 | App 恆掛 |
| 4 | `useCapitalOrders` | `["capital-orders"]` | **30 s**(無條件) | 0 | 5 min | 1 | 委託 tab |
| 5 | `useCapitalStream` fills provider | `["capital-fills"]` | **30 s** | 0 | 5 min | 1 | App 恆掛 |
| 6 | `useTxoContracts`(OrderPanel) | `["txo-contracts"]` | **30 s**(無條件) | 0 | 5 min | 1 | TxoPage 恆掛 |
| 7 | `useStockBars` 分 K | `["stock-bars",code,"1",30]` | 60 s / 盤外距開點 / 空非 ok 20 s | 0 | 5 min | 1 | 個股 K 線模式 |
| 8 | `useStockBars` 日 K | `["stock-bars",code,"D"]` | 界政策(午夜 / 14:00)+ 失敗 60 s | `dayBarsStaleTime` | 5 min | 1 | 同上 |
| 9 | `useMarketBars` 分 K ×2 pane | `["market-bars",key,"1",30]` | 60 s(`active`) | 0 | 5 min | 1 | IndexPage 恆掛 |
| 10 | `useMarketBars` D/W/M ×2 | `["market-bars",key,tf]` | 界政策(**不吃 `active`**,刻意) | `dayBarsStaleTime` | 5 min | 1 | 同上 |
| 11 | `useFuturesBars` 分 K | `["futures-bars",key,"1",5,"allday"]` | 60 s | 0 | **Infinity** | 1 | `subscribed: active` |
| 12 | `useFuturesBars` 日 K | `["futures-bars",key,"D"]` | 界政策 | `dayBarsStaleTime` | **Infinity** | 1 | 同上 |
| 13 | `useGroupSnapshots` | `["stock-group-state",csv]` | 60 s(盤外距開點) | **55 s** | 5 min | **false** | 群組檢視 |
| 14 | `useServerBuild` | `["server-build"]` | **60 s** | 5 s | 5 min | false | VersionDriftBadge(App 恆掛) |
| 15 | `useBuildDrift` | `["build-drift",beSha]` | **60 s** | 5 s | 5 min | false | **dev only**(每發跑一次 git 子行程) |
| 16 | `useSignalFeed` | `["stock-signals-today"]` | **5 min** | 0 | 5 min | 1 | 個股頁 |
| 17 | `useTradingCalendar` | `["calendar"]` | **5 min**,`refetchIntervalInBackground: true` | **Infinity** | 5 min | 1 | App 恆掛 |
| 18 | `useStockNames` | `["stock-names"]` | 僅無 data 時 3 s,上限 20 輪 | **Infinity** | **Infinity** | 1 | 側欄 |
| 19 | `useIndexOverlay` | `["index-overlay",date]` | 僅 error / 三欄全 null 時 60 s | **Infinity** | 5 min | 1 | 分時疊線 |
| 20 | `useStockOverlay` | `["stock-overlay",code,date]` | 無 | **Infinity** | 5 min | 1 | 個股分時 |
| 21 | `useOiLevels` | `["oi-levels"]` | 無 | **1 h** | 5 min | 1 | 期貨圖 |
| 22 | `useStkfutContracts` | `["stkfut-contracts",code]` | 無 | **10 min** | 5 min | 1 | 個股頁 header |
| 23 | `useStockWatchlist` | `["stock-watchlist"]` | 無 | 0 | 5 min | 1 | 側欄 / 圖牆 |
| 24 | `useSignalRules` | `["signal-rules"]` | 無 | 0 | 5 min | 1 | 個股頁 |
| 25 | `useSeries` | `["txo-series"]` | 無 | 0 | 5 min | 1 | TxoPage |
| 26 | `useCapitalFills` / `useCapitalPositions`(讀取端) | 同 3/5 | **false**(N068 刻意) | — | — | 1 | 多處 |

### 3.2 每分鐘總請求數與頻寬(盤中,一個分頁,個股 tab + index 恆掛)

| 項 | req/min | 單次 payload | bytes/min |
|---|---|---|---|
| `breadth-rows` | 6 | **~2,800 列 × 13 欄 ≈ 400–600 KB** | **~2.4–3.6 MB** |
| `capital-status` | 6 | < 1 KB | ~5 KB |
| `capital-positions` | 4 | 數 KB | ~15 KB |
| `capital-orders` | 2 | 數 KB | ~10 KB |
| `capital-fills` | 2 | 數 KB | ~10 KB |
| `txo-contracts` | 2 | ~10 KB | ~20 KB |
| `stock-bars` 分 K | 1 | 30 日 × ~270 根 ≈ 8,000 根 ≈ 300 KB | ~300 KB |
| `market-bars` 分 K ×2 | 2 | 同量級 | ~600 KB |
| `futures-bars` 分 K | 1 | 5 日 × 1,140 ≈ 5,700 根 ≈ 200 KB | ~200 KB |
| `stock-group-state` | 1 | 80 檔 × (minutes + vp) ≈ 200–400 KB | ~300 KB |
| `/api/health` | 1 | < 1 KB | ~1 KB |
| `/__build/sha`(dev) | 1 | < 1 KB(但後端跑 git 子行程) | ~1 KB |
| `signals/today` | 0.2 | 視訊號數 | ~20 KB |
| `/api/calendar` | 0.2 | < 5 KB | ~1 KB |
| **合計** | **≈ 29 req/min** | | **≈ 4–5 MB/min** |

**`breadth-rows` 一支就吃掉 60–75% 的總頻寬**,而前端 `statusOf()` 會把其中約 90% 的列直接丟掉。

WS 另計:8 條連線,盤中 110–180 則/s ≈ 每則 200–600 bytes → **~1.5–4 MB/min**。
其中 `watchlist_quote` 佔絕大多數,且每則的 JSON 外殼(`{"type":"watchlist_quote","code":"2330",…}`)
本身就是重複開銷 —— 合併成一則陣列可以省掉 80 份 `"type"` 鍵。

### 3.3 `queryClient` 全域設定

```ts
// frontend/src/main.tsx:16
const queryClient = new QueryClient();
```

**完全沒有 `defaultOptions`。** 所以生效的是 TanStack v5 出廠預設:

| 選項 | 預設值 | 對本專案的意義 |
|---|---|---|
| `refetchOnWindowFocus` | **`true`** | 每次從別的視窗切回瀏覽器 → **所有 stale 的 query 同時重抓**。而 `staleTime` 預設 0,除了上表 17–22 那幾支之外全部恆 stale。一次 alt-tab = `breadth-rows`(500 KB)+ 三支 bars(打 TC4 `SubHistory`,搶 `api.lock`)+ group-state + 全部 capital 同時發。 |
| `refetchOnReconnect` | `true` | 同上,網路抖一下就是一次齊發 |
| `refetchOnMount` | `true` | 配合 `staleTime: 0` → tab 切換讓 lazy 頁首次掛載時齊發 |
| `staleTime` | `0` | 見上 |
| `gcTime` | `5 min` | `useFuturesBars` 已針對這條覆寫成 `Infinity`(bug/futures-tab-reactivate-refetch);其餘未覆寫的在退訂 5 分鐘後被回收,切回要重抓 |
| `retry` | `3` + 指數退避 | 幾乎每支 hook 都手動覆寫成 1 或 false —— 26 支裡 20 支寫了 `retry`。這是「預設錯了所以每個呼叫點各修一次」的典型樣態 |
| `structuralSharing` | `true` | 對 `breadth-rows` 是每 10 秒對 2,800 個物件 × 13 欄做 `replaceEqualDeep`(~36,000 次比較);好處是「內容沒變就不重繪」。**對 `useGroupSnapshots` 無效** —— 它回的是 `Map`,`replaceEqualDeep` 只處理 plain object / array,遇到 Map 直接回新值 |
| `notifyOnChangeProps` | 未設 = tracked props | ✅ v5 預設就是最佳解,不必動 |

---

## 4. Findings

> 嚴重度以「在這台看盤機上、盤中、真實使用」為準。
> `on_hot_path` = 是否每秒執行 ≥ 10 次。

---

### F5-01 `watchlist_quote` per-code 推播讓 App 整棵樹每秒重繪 80–150 次 — **critical**

**位置**:`copycat/server/stock_engine.py:1827-1832`(產生點)+ `frontend/src/hooks/useStockStream.ts:425`(消費點)

**證據**:

```python
# stock_engine.py:1827-1832
dirty, self._dirty_watchlist = self._dirty_watchlist, set()
for code in dirty:
    state = self._states.get(code)
    if state is None or state.last is None:
        continue
    self._publish(self._quote_payload(code))     # ← 每檔一則獨立 WS frame
```

```ts
// useStockStream.ts:425
setWatchlist((prev) => ({ ...prev, [msg.code as string]: q }));
```

**影響**:自選 80 檔(`data/stock_watchlist.json` 實測 80 codes / 12 groups;上限 150),
開盤後多數檔每秒都有成交 → 每秒 80–150 個獨立 `message` 事件。
WebSocket message 各自是獨立 macrotask,React 的 automatic batching **跨 task 不生效**,
所以是 80–150 次獨立的 render + commit。每次 render 走完 App 底下**全部五頁**(含 hidden)。
盤中 CPU 幾乎全被這條路吃掉;下單當下的閃電梯點擊延遲直接受它拖累。

**改法**(兩段,後端那半是根治):

1. **後端合併成一則**(比照 #180 `ticks` 打包的既有先例):
   ```python
   # _flush_watchlist_loop 尾段
   items = [self._quote_payload(code) for code in dirty if ...]
   if items:
       self._publish({"type": "watchlist_quotes", "items": items})
   ```
   80 則 → 1 則,App render 從 80–150/s 降到 1/s。**訊息數降兩個數量級。**

2. **前端把 `watchlist` 搬出 React state**,改成 module-level store + `useSyncExternalStore`
   的 per-code selector(`subscribeQuote(code)` / `getQuote(code)`)。
   側欄的一列、圖牆的一張卡各自訂閱自己那一檔 —— 一檔動只重繪一列,而不是整棵樹。
   同一個 pattern 在本 repo 已有現成範例:`lib/tick-stream.ts`(EventTarget 匯流排)
   與 `hooks/useCapital.ts:59-82`(`useSyncExternalStore` 的 wsStatus store)。

**契約影響**:
- 新增 WS 訊息型別 `watchlist_quotes` = **新增跨檔契約**,要比照 CLAUDE.md §4「個股逐筆 = `ticks` 打包訊息」
  那一條寫進 §4,並在 `tests/server/test_stock_engine.py` + `useStockStream.test.ts` 兩側各釘一條。
- 舊訊息型別 `watchlist_quote` 建議**保留一個版本**(前端 `default` 分支對未知型別靜默丟棄 ——
  單邊部署會讓側欄整片變 `-`,零錯誤訊號)。退役時機比照 #180 的做法,兩邊同版部署。
- `_quote_payload` 是 CLAUDE.md 已記的「唯一 payload builder(N101)」,**不要動它的產出形狀**,
  只改外面那層信封。

**risk**:中。行為等價(逐檔 payload 逐字不變),但改的是 WS wire format。
須同時驗:`trial` 翻轉補推路徑(`:1819-1826`)也走 `_publish`,要一併進打包或明確排除。

**effort**:M(後端 ~20 行 + 前端 ~40 行 + 兩側測試)

---

### F5-02 `hidden` 保留 DOM 讓「沒在看的四頁」跟著每一次重繪 — **critical**

**位置**:`frontend/src/App.tsx:334-438`

**證據**:

```tsx
// App.tsx:334-342 —— TXO 恆掛,無條件 render
<div role="tabpanel" id={panelId("txo")} hidden={tab !== "txo"} …>
  <TxoPage />
</div>
// App.tsx:125-131 —— index / txo 恆 visited
const [visited, setVisited] = useState<Record<Tab, boolean>>({
  index: true,
  txo: true,
  ...
});
```

`hidden` 是 CSS `display:none` —— **React 照樣 render 整棵子樹、照樣跑 effect、照樣建 element**。
所以 F5-01 的 150 次/秒重繪,每一次都會走過:
TXO 的 `MetricsBar` + `PnlChart`(SVG) + `QuoteTable` + `OrderPanel`,
台股綜合的 `MarketPane`×2(40 顆 pill)+ `AdvanceDeclineChart`(SVG) + `LimitListSection`(30–300 列)。

CLAUDE.md / 各元件註解已經替**輪詢**這一半做了補救(`active` gate 到處都是),
但**渲染**這一半完全沒有 gate。

**改法**:`react@19.2.7` 已安裝且 **`React.Activity` 可用**(實測 `typeof React.Activity === "symbol"`,
`@types/react` 有 `ActivityProps` 定義)。把五個 tabpanel 換成:

```tsx
<Activity mode={tab === "stock" ? "visible" : "hidden"}>
  <StockPage … />
</Activity>
```

`mode="hidden"` 的語意正是本專案要的:**保留 state 與 DOM,但以最低優先權渲染、並卸載 effect**。

**⚠ 必須逐頁評估「effect 卸載」的後果 —— 這是這條建議唯一的真風險**:
- `CorrPage` 的兩條 WS(`/ws/corr`、`/ws/river`)在 effect 裡建立 → hidden 會斷線。
  現行設計明文要求「首訪後常駐」(`CorrPage.tsx:6-8`),**不可直接套用**。
- `IndexPage` 沒有自建 WS(`useBreadth` 在 App 層),可以套。
- `TxoPage` 的 `useTxoSnapshot` WS 在頁內 → 會斷。TXO 損益是累積量,斷線重連會重取全量快照,
  需確認 `/ws/txo-pnl` 首則是否為全量(看起來是,`onMessage: (msg) => setData(msg as Snapshot)` 整份覆蓋)。
- `FuturesPage` 資料在 App 層,可以套。

**保守的替代路徑**(不動 React 行為語意):先做 F5-01 + F5-03,
讓 App 的 render 頻率從 150/s 降到 ~2/s —— 那時「hidden 頁跟著重繪」的成本自然降兩個數量級,
`Activity` 就變成「錦上添花」而不是「非做不可」。**建議順序是這樣,不是反過來。**

**契約影響**:無跨檔契約;但 `aria-controls` 的 dangling 註解(`App.tsx:304-306`)要重寫,
`Activity` 下 panel 恆存在,dangling 問題反而消失。

**risk**:高(若貿然對 CorrPage / TxoPage 套用)/ 低(只對 IndexPage / FuturesPage 套用)

**effort**:S(改法本身)/ M(含逐頁 effect 影響盤點與真環境驗證)

---

### F5-03 `futures` WS 0.1 s × 3 商品讓 App 每秒重繪 30 次 — **high**

**位置**:`frontend/src/hooks/useFuturesStream.ts:96-100`;產生點 `copycat/server/futures_engine.py:172-184`

**證據**:

```python
# futures_engine.py:172-184
flush_interval_secs: float = 0.1,
...
# 五檔盤中要即時 → 週期取 0.1 s(1 s 會讓閃電梯五檔慢一秒)
```

```ts
// App.tsx:248-251(既有註解已點名問題)
// 期貨 10 Hz tick 因此每秒把右欄閃電梯 subtree(全站最重的 render)重畫 10 次 ——
// 而使用者停在個股 / 指數 / TXO 頁時,期貨腿與右欄顯示的東西毫無關係。
```

現行的 `futuresCtx` / `stockCtx` 兩腿 `useMemo` 只護住了 `RightRail`。
`setState` 本身仍然發生在 App,**其餘四頁照樣重繪**。

**影響**:0.1 s × 3 商品 = 30 則/s。單獨看不致命,但它與 F5-01 疊加,而且**盤後夜盤時段
F5-01 停了、這條還在跑** —— 夜盤掛著看盤的分頁整晚每秒重繪 30 次。

**改法**:把 `futuresStream` 從 App 的 `useState` 搬到 module store:

```ts
// hooks/useFuturesStream.ts —— 保留 WS 建立在 App 層(單一連線),
// 但 state 改走 useSyncExternalStore + per-product selector
export function useFuturesProduct(product: string): FuturesProductState | null
export function useFuturesWsStatus(): WsStatus
```

`RightRail`(期貨態)、`FuturesPage`、`IndexPage` 的 `PaneFutState` 各自訂閱自己要的那一顆。
App 本身不再持有,也就不再因期貨推播重繪。

`hooks/useCapital.ts:59-82` 已有同款 module store 的現成寫法可以照抄。

**契約影響**:無 wire 契約;但 `FuturesPage` / `IndexPage` 的 `futures` / `state` prop 會從
「App 下傳」變成「自己訂閱」,動到既有測試的 stub 方式(`frontend-testing` skill 有記 spyOn pattern)。

**risk**:中(動 4 個呼叫點的 props 介面,既有測試要跟)

**effort**:M

---

### F5-04 `new QueryClient()` 零 defaultOptions:`refetchOnWindowFocus` 開著 = 每次切回瀏覽器打一次齊發 — **high**

**位置**:`frontend/src/main.tsx:16`

**證據**:

```ts
const queryClient = new QueryClient();
```

全庫 grep `defaultOptions` 只在測試工具裡出現一次:

```ts
// frontend/src/test-utils.tsx:16
const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
```

**影響**:v5 預設 `refetchOnWindowFocus: true` + `staleTime: 0`。
看盤機的日常是「Chrome ↔ 達錢 4 ↔ Excel」來回切 —— **每一次切回 Chrome**:
- `breadth-rows` 重抓(~500 KB,後端 rebuild 2,800 個 dict)
- `stock-bars` / `market-bars`×2 / `futures-bars` 的分 K 重抓 → **當日段每發都真走 TC4 `SubHistory`,
  與 REALTIME 搶同一把 `api.lock`**(`useMarketBars.ts:66-69` 的註解自己講了這件事)
- `stock-group-state`(80 檔 batch)
- 四支 capital + `txo-contracts` + `signals/today`

全部在同一個 tick 內發出。這正是 `docs/` 裡「切回 tab 那一趟 14 s 才回」那類症狀的候選成因之一
(`useFuturesBars.ts:38-42` 記了 08-28 實測 14 s)。

而且 `retry: 3` 這個預設**被 26 支 hook 裡的 20 支各自覆寫了一次** —— 這是預設值錯了的鐵證。

**改法**:

```ts
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // 看盤機 alt-tab 是常態,而所有真的需要新鮮度的 query 都有自己的 refetchInterval
      refetchOnWindowFocus: false,
      // 失敗的常態是「TC4 沒開 / 後端沒起」,退避三輪只是延後降級
      retry: 1,
      // 沒有任何 query 是「秒級必須新鮮且沒有 interval」的
      staleTime: 5_000,
    },
  },
});
```

**⚠ 關窗焦點重抓有既有讀者**,不可一刀切:
- `useStockNames.ts:34-36` 明文寫「停止後的復原後門 = 分頁 visibilitychange」——
  那條走的是 focusManager,關掉 `refetchOnWindowFocus` 會拿掉它唯一的復原路徑。
  → 該 hook 要顯式 `refetchOnWindowFocus: true` 覆寫回來。
- `useBreadthRows.ts:38-41` / `useMarketBars.ts:101-103` 都寫了「`active=false` 只停 interval,
  非退訂 —— **回前景仍會 `refetchOnWindowFocus`**」。這是刻意設計的自癒路徑,
  關掉之後「切回 tab 拿到新料」的行為會變 —— 但 `useFuturesBars` 已經改用 `subscribed` 做到
  「切回立即重抓」而不依賴 focus,可以比照。

**契約影響**:無跨檔契約。但這是**行為改動(🔴)**,要獨立 commit 且逐支確認自癒路徑。

**risk**:中(自癒路徑是本專案累積教訓的核心,不能靜默拿掉)

**effort**:S(改法)/ M(含逐支覆核)

---

### F5-05 `/api/market/breadth/rows` 送全市場 2,800 列,前端丟掉 ~90% — **high**

**位置**:`copycat/server/breadth_engine.py:300-324`(產生)+ `frontend/src/components/index/LimitListSection.tsx:205-215`(丟棄)

**證據**:

```python
# breadth_engine.py:301-316
rows_out: list[dict] = []
for row in self.rows:                      # ← 全市場每一檔
    streak: int | None = None
    ...
    rows_out.append({**row, "streak": streak, "streak_capped": capped})   # ← 每檔一份 dict 複製
return { ..., "rows": rows_out }
```

```ts
// LimitListSection.tsx:205-215 —— 前端第一件事就是把非漲跌停的列全部丟掉
function buildEntries(rows: BreadthRow[], filter: LimitListFilter): Entry[] {
  for (const row of rows) {
    const status = statusOf(row);
    if (status === null) continue;         // ← ~90% 的列在這裡被丟
```

```ts
// statusOf:只有這三種列有用
if (row.limit_up) return "limit_up";
if (row.limit_down) return "limit_down";
if (row.touched_limit_up || row.touched_limit_down) return "touched";
return null;
```

**影響**:每 10 秒(IndexPage active 時)~500 KB 的 JSON 在 localhost 上來回,
後端每次重建 2,800 個 dict,前端每次 `JSON.parse` + `structuralSharing` 對 36,000 個欄位做 deep compare,
然後把 2,500 列直接丟掉。一個交易日 4.5 小時 × 6 req/min ≈ **1,620 次請求 / ~800 MB**。

**改法**:後端在 `rows_state()` 裡就濾掉 `statusOf == null` 的列,payload 從 2,800 → 30–300 列。
前端 `buildEntries` 的 `statusOf` 守門保留(防禦性,且舊後端相容)。

**⚠ 兩個欄位的語意會變**:
- `pool`(`LimitListSection.tsx:331-337`)= 「篩選前的狀態池」,濾後恰好等於 `rows.length` —— 語意不變,反而更誠實。
- `data.rows.length === 0` 目前被當成「暫無資料(延遲)」(`:365`)。濾後「今天真的沒有漲跌停」也會是 0,
  兩態就撞在一起了。**必須同時把那句判定改走 `as_of === null`**(該檔 `:355-360` 已經寫明
  「空狀態判別子是 `as_of` 不是 `stale`」,這裡是同一個道理的第二次),
  或後端另加一個 `scanned: int` 欄位(全市場掃描檔數)當「有沒有資料」的 sentinel。

**契約影響**:`/api/market/breadth/rows` 的 payload 語意改動 = 跨檔契約。
`rows` 從「全市場」變成「有漲跌停狀態的列」。要在 CLAUDE.md §4 加一條,
並在 `tests/server/test_breadth_engine.py` + `LimitListSection.test.tsx` 兩側釘住。

**risk**:中(空態文案分岔是真的會靜默壞掉的那種)

**effort**:M

---

### F5-06 `cn()` = `twMerge(clsx())` 用在每秒數萬次的列渲染上 — **medium**

**位置**:`frontend/src/lib/utils.ts:4-6`;熱點呼叫端 `WatchlistSidebar.tsx`(9 處,多數在 row 內)、
`LimitListSection.tsx`(19 處)、`GroupGridView.tsx`(6 處)

**證據**:

```ts
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
```

**影響**:`tailwind-merge` 的工作是「解 class 衝突」,設計目標是元件接受外部 `className` 覆寫。
本專案的 row 渲染器**沒有外部覆寫**,class 集合是固定的條件分支 —— twMerge 純粹白跑。
150 render/s × 80 列 × 6 次 ≈ 72,000 次/秒。twMerge 有 LRU(預設 500),
所以多數是 cache hit,但 hit 也要:`clsx` 拼字串(配置)→ 字串當 key 查 Map。

**注意這條是「量測後再改」而不是「一定要改」**:cache hit path 大約 0.5–2 µs,
72,000 次 ≈ 36–144 ms/s,佔用可觀但**不是主因**。F5-01 做完之後這個數字自動降到 ~500 次/秒,
就不值得動了。

**改法**(若量測確認):熱路徑的固定 class 集合改用三元運算直接串字串或 `clsx` 單獨使用:
```ts
import { clsx } from "clsx";
// row 內部沒有衝突要解 → clsx 就夠
className={clsx("group flex items-center …", active === code && "bg-bg-deep")}
```
`cn` 留給真的接受外部 `className` 的元件(`RadioPills` 的 `pillClass`)。

**risk**:低(但要確認每個改動點確實沒有 class 衝突 —— 有衝突時 clsx 的結果是「後者未必贏」,
Tailwind 的勝負由 CSS 產出順序決定,症狀是樣式靜默走錯)

**effort**:S(但 34 個呼叫點要逐一看,實際是 M)

---

### F5-07 頁級元件全裸無 memo,且 props 每 render 換 identity — **medium**

**位置**:`frontend/src/App.tsx:354-436`

**證據**:全庫 `memo(` 在頁級元件只有一處:

```
components/rail/RightRail.tsx:121  export const RightRail = memo(function RightRail({ ctx }) {
components/stock/GroupGridView.tsx:132  const GroupCard = memo(function GroupCard({ …
```

`StockPage` / `IndexPage` / `FuturesPage` / `CorrPage` / `TxoPage` 全部沒有。
而且就算加上去也不會生效:

```tsx
// App.tsx:354-362
<StockPage
  code={stockCode}
  stream={stockStream}          // ← useStockStream 每次 render 回新物件字面量
  ...
/>
```

```ts
// useStockStream.ts:561 —— 每次 render 都是新物件
return { accum, watchlist, status, stkfut, wsStatus };
```

`IndexPage` 的 `twse` / `otc` / `breadth` 同理(每秒真的會變)。

**影響**:記憶化的「天花板」被封死 —— 現在就算有人想加 memo 也擋不住任何東西,
所以整個架構只剩「靠葉節點 memo 硬擋」一條路(`GroupCard` 的 14 個 prop 全部手工穩定化就是這個後果)。

**改法**:與 F5-01/F5-03 是同一件事的兩面。資料搬到 external store 之後,
頁級元件的 props 自然就只剩 `code` / `product` / `active` 這些 primitive,
memo 才有意義。**單獨加 memo 沒有價值,不要分開做。**

**risk**:低

**effort**:S(併在 F5-01/F5-03 裡做)

---

### F5-08 `useSyncExternalStore` 的 `getSnapshot` 每次 render 同步讀 localStorage — **medium**

**位置**:`frontend/src/hooks/useChartToggles.ts:110-118`、`frontend/src/lib/fee-discount.ts:41-43`、
`frontend/src/hooks/useSignalSound.ts:20-22`

**證據**:

```ts
// useChartToggles.ts:110-118
function getSnapshot(): ChartToggles {
  const raw = readLocal(CHART_TOGGLES_KEY);       // ← getItem #1
  if (cachedRaw === undefined || raw !== cachedRaw) {
    cached = load();                              // ← JSON.parse + 物件展開
    cachedRaw = readLocal(CHART_TOGGLES_KEY);     // ← getItem #2
  }
  return cached;
}
```

```ts
// fee-discount.ts:41-43 —— 連快取都沒有,每次都 readLocal + clampDiscount 解析
export function readFeeDiscount(): number {
  return loadDiscount().value;
}
```

消費端:`useChartToggles` 8 個非測試檔、`useFeeDiscount` 4 個。
`useSyncExternalStore` 每次 render 呼叫 `getSnapshot` 一次,commit 後的一致性檢查再一次。

**影響**:150 render/s × ~12 消費端 × 2 ≈ 3,600 次 `localStorage.getItem`/秒。
`localStorage` 在 Chrome 是同步 API(記憶體內有快取,但仍走 binding + 字串配置)。
`readFeeDiscount` 還額外每次跑一次 `clampDiscount` 字串解析。

**改法**:`getSnapshot` 改成純讀 module 變數(O(1),零 IO),
把 localStorage 讀取移到 **subscribe 時 + `storage` 事件時 + 自己 `set` 時**。
`fee-discount.ts` 已經有 `listeners` 集合與 `storage` 事件監聽(`:47-54`),
只要把 `readFeeDiscount` 改成回快取值、在 `persistDiscount` 與 `storage` handler 裡更新快取即可。

**⚠ 已知反對理由**(`useSignalSound.ts:8-10` 明文):「每次直讀」是為了讓測試 `beforeEach` 清 storage 後
不殘留上一個 it 的狀態。→ 改法要配一支 `resetForTest()`(`lib/tick-stream.ts:60-61` 已有同款先例
`resetTickStream()`),不要為了測試方便在 prod 熱路徑上付這個錢。

**risk**:低(但 `useChartToggles` 的「跨分頁不同步是刻意的」語意要保留,見該檔 `:103-104`)

**effort**:S

---

### F5-09 `groupSignals(signals)` 未 memo,每 render 配置最多 400 個物件 — **medium**

**位置**:`frontend/src/components/stock/SignalRail.tsx:174`

**證據**:

```tsx
{groupSignals(signals).map((group) => {
```

```ts
// lib/signal-model.ts:209-232 —— 每次呼叫新建 groups 陣列 + 每組一個 items 陣列
export function groupSignals(signals: SignalMsg[]): SignalGroup[] {
  const groups: SignalGroup[] = [];
  for (const sig of signals) { ... groups.push({ key, code, name, time, price, items: [sig] }); }
```

`signals` 上限 200(`mergeSignals` 的 `cap = 200`)。

**影響**:150 render/s × 最多 200 group 物件 + 200 個陣列 = **每秒 60,000 個短命物件**。
純 GC 壓力,不改變畫面。組內還會再跑 `groupKindLabels` / `groupPolicyTags`(各自 `[...items].reverse()`)。

**改法**:`const groups = useMemo(() => groupSignals(signals), [signals]);`
`signals` 來自 `useSignalFeed` 的 `useMemo([baseline, live])`,identity 穩定 → memo 命中率接近 100%。

**risk**:極低

**effort**:S(一行)

---

### F5-10 `LimitListSection` / `WatchlistSidebar` / `QuoteTable` 無虛擬化 — **medium**

**位置**:`LimitListSection.tsx:460`(`entries.map`)、`WatchlistSidebar.tsx:769/815`、`QuoteTable.tsx:203`

**影響**:
- 漲跌停列表常態 30–300 列(全市場鎖停日可到 400+),每列 9 個 `<td>`;
- 自選側欄 80–150 列,每列 ~15 個節點;
- TXO T 字報價視序列深度。

單次 render 的 DOM diff 成本在 150 Hz 下被放大 150 倍。

**改法**:`@tanstack/react-virtual`(與既有 `@tanstack/react-query` 同一家,~4 KB gz,
headless 不帶樣式,不影響 Tailwind 版面)。

**⚠ 自選側欄有硬約束**:`ROW_H = 52` 這個常數同時是**拖曳落點幾何的分母**
(`WatchlistSidebar.tsx:39-45` 明文:「與畫面上的實際列高一旦漂移,拖曳愈往下插入位置愈偏,
而症狀是『放開後插到別的位置』= 靜默改資料、零錯誤訊號」)。
虛擬化之後 `zonesNow()` 的 `getBoundingClientRect` 量到的是虛擬容器而不是真實列,
`dropTargetFromPointer` 的整套幾何要重寫。**側欄不建議虛擬化 —— 收益(150 列)不值這個風險。**

只對 `LimitListSection` 做(它沒有拖曳,而且列數最多)。

**risk**:低(LimitListSection)/ 高(WatchlistSidebar,不做)

**effort**:M

---

### F5-11 `/__build/sha` 每 60 秒跑一次 git 子行程(dev) — **low**

**位置**:`frontend/src/hooks/useServerBuild.ts:71-82`

```ts
const q = useQuery({
  queryKey: ["build-drift", beSha],
  queryFn: () => getJson(`/__build/sha?since=${encodeURIComponent(beSha ?? "")}`),
  refetchInterval: HEALTH_POLL_MS,   // 60 s
  enabled: dev && beSha !== null,
});
```

middleware 端跑 `git log <since>..HEAD -- copycat/`(`:4-5` 註解)。
`dev` only,而 CLAUDE.md §1 已明訂「看盤日常 = `npm run preview`(prod build)」,
所以真實看盤不吃這條。**不是問題,列出來是為了記帳完整。**

---

### F5-12 `useCapitalStatus` / `useCapitalOrders` / `useTxoContracts` 無條件輪詢 — **low**

**位置**:`useCapital.ts:150-157`、`:186-193`、`OrderPanel.tsx:27-38`

三支都沒有 `active` gate:
- `capital-status` 10 s —— 掛在 OrderPanel(TxoPage 恆掛)與各梯;
- `capital-orders` 30 s —— 委託 tab 開著才掛,OK;
- `txo-contracts` 30 s —— **TxoPage 恆掛 → 恆輪詢**,而 TXO 頁多數時間沒人在看。

payload 都很小(合計 ~35 KB/min),所以是 low。
但 `capital-status` 每 10 秒會碰到群益 COM 執行緒(`capital/client.py` 的 COM 專屬執行緒),
那條路的成本不在前端 —— 留給 F3 區塊判斷。

**改法**:F5-02 的 `Activity` 一旦落地,hidden 頁的 effect 卸載會自動解決這一條。

---

### F5-13 `structuralSharing` 對 `useGroupSnapshots` 是無效的(記帳用) — **low**

**位置**:`hooks/useGroupSnapshots.ts:80-104`

`fetchGroupState` 回的是 `Record<string, GroupSnapshot>`,其中 `minutes` 與 `vp` 都是 `Map`。
TanStack 的 `replaceEqualDeep` 只對 plain object / array 遞迴,遇到 `Map` 直接回新值。
所以每 60 秒的 batch 落地時,**所有 80 個 code 的 snapshot 都換 identity**
→ `useGroupLiveAccums` 的 `seeded` useMemo 失效 → 整牆 80 張卡重播種 + 重繪。

這是**刻意且正確的**(註解 `:8` 明寫「60 s 輪詢的新快照到 → 全體重播種」),
列出來只是要說明:那一下的 60 秒週期性卡頓有明確來源,不是玄學。

---

## 5. 工具選型建議與取捨

| 工具 | 用在哪 | 解什麼 | 代價 | 建議 |
|---|---|---|---|---|
| **`React.Activity`(已內建,19.2.7)** | `App.tsx` 五個 tabpanel | hidden 頁不以正常優先權渲染、effect 卸載 | **零新相依**;但 effect 卸載會斷 CorrPage / TxoPage 的 WS,需逐頁盤點 | **有條件導入** —— 先做 F5-01/F5-03 降頻,再對 IndexPage / FuturesPage 套用,CorrPage / TxoPage 另案評估 |
| **module store + `useSyncExternalStore`(React 內建)** | `watchlist` / `futuresStream` | per-code / per-product 訂閱,把「整棵樹重繪」變成「一列重繪」 | 零新相依;repo 內已有兩個現成範例(`useCapital.ts` wsStatus、`tick-stream.ts` 匯流排);測試要改 stub 方式 | **建議導入**(F5-01 / F5-03 的核心) |
| **`useDeferredValue`(React 內建)** | 圖牆 / 漲跌停表 | 把低優先的大列表渲染讓給互動 | 零相依;但只在 concurrent render 有效,對「每秒 150 次 setState」治標不治本 | **不建議先做** —— 先降頻率,降完之後大概率不需要 |
| **`@tanstack/react-virtual`** | `LimitListSection` | 300+ 列只渲染可視的 ~20 列 | ~4 KB gz,headless,與既有 TQ 同家;**不可用在 WatchlistSidebar**(拖曳幾何依賴真實列 rect) | **有條件導入**(只 LimitListSection) |
| **`zustand` / `jotai` / `valtio`** | 取代上面的 module store | 現成的 selector + 訂閱 | 多一個相依;而 `useSyncExternalStore` 用內建 API 已經夠,repo 內也已有兩份範例 | **不建議** —— 這裡沒有跨元件複雜狀態圖,只有「一份 map,多個 per-key 訂閱者」 |
| **`react-window`** | 同 react-virtual | | 生態較舊、與 Tailwind 版面整合較差 | **不建議**(選 react-virtual) |
| **Web Worker(JSON.parse / 幾何)** | `breadth-rows` 解析 | 把 500 KB parse 移出主執行緒 | `postMessage` 結構化複製的成本可能超過 parse 本身;而 F5-05 把 payload 砍 90% 之後根本不需要 | **不建議** —— 先砍 payload |
| **Canvas / OffscreenCanvas 取代 SVG** | 圖牆 80 張卡 / 分時圖 | | 是 **F4 區塊(圖表渲染)** 的題目,不在本區塊 | 交給 F4 |
| **`tailwind-merge` 移除 / 局部化** | `lib/utils.ts` 的 `cn` | 熱路徑白燒 | 34 個呼叫點要逐一確認無 class 衝突;衝突時失效是靜默的 | **有條件導入** —— F5-01 做完後量測,超過 5% CPU 才動 |
| **`vite-plugin-compression` / 分包調校** | bundle | | 見下節「不要動」 | **不建議** |

---

## 6. 不要動的地方

### 6.1 Bundle 大小 / code splitting —— 已經夠好,而且場景不需要

實測(`frontend/dist/assets`,2026-09-09 build):

```
index-DZK_0mps.js       raw 386,444  gz 123,081
StockPage-DyBg-bXs.js   raw  73,834  gz  22,370
CandleChart-DDVyv99b.js raw  40,947  gz  14,623
IndexPage-CEkpl5Uz.js   raw  26,466  gz   8,887
FuturesPage-C-TFz8TV.js raw  14,194  gz   5,674
CorrPage-Du2YCEoh.js    raw  13,749  gz   4,999
index-D7-RUPTK.css      raw  39,318  gz   7,908
                                     ── 合計 gz ≈ 188 KB
```

這是一個**跑在 localhost、一天開一次、開著就整天不關**的看盤工具。
首屏 gz 123 KB 從 127.0.0.1 載入 = 個位數毫秒。四個 `lazy` 已經把重元件切開了。
**再花力氣做 tree-shaking / manualChunks / 預載策略是純粹的過度工程。**

### 6.2 `GroupCard` 的 14 個 prop 穩定化 —— 這是全檔最好的工程

`GroupGridView.tsx:132-179` + `:453-477` 的 `EMPTY_FILLS` / `EMPTY_POSITIONS` / `NOOP_HOVER` /
latest-ref `pick` / `indexSeries` 條件傳 null —— 每一條都有註解說明失效樣態。
F5-01 做完之後這些仍然有價值(60 秒 batch 落地那一下還是會整牆重繪)。**不要拆。**

### 6.3 日 K 新鮮度政策(`lib/day-bars-rollover.ts`)

三支 hook 共用、與後端 `DAILY_FINAL_TIME` 有 golden fixture parity(CLAUDE.md §4「日 K 定稿界前後端同值」)。
`msUntilDayRollover` / `dayBarsRefetchInterval` 的每一個分支都對應一個實際踩過的坑。
**這裡沒有效能問題(一天最多兩發),碰它只會壞事。**

### 6.4 `useWatchlistCommit` 的 module 層串行佇列

`hooks/useWatchlistCommit.ts` 整支是為了「後端 PUT 全量取代且無樂觀鎖」這個硬約束寫的。
頻率是使用者操作級(一天幾十次),零效能問題。**不要因為「看起來複雜」就重構。**

### 6.5 `notifyOnChangeProps`

TanStack v5 預設就是 tracked props(自動追蹤你解構了哪些欄位)。
現有程式碼全部走解構(`const { data, isError } = useX()`),已經是最佳解。**不要顯式設定。**

### 6.6 `useCapital` 的 N068 per-observer 輪詢收斂

`useCapitalPositions` / `useCapitalFills` 讀取端 `refetchInterval: false`、
節奏收斂到 `useCapitalStream`(App 層掛一次)。這正是本報告在別處建議的 pattern,
已經做對了。**不要動。**

---

## 7. 量測方法

### 7.1 先證明 F5-01(這是整份報告的地基,不可跳過)

**(a) 數 WS 訊息**:盤中開 DevTools → Network → WS → `/ws/stock` → Messages,
篩 `watchlist_quote`,看一秒內幾則。
**判準:若 > 20 則/秒,F5-01 成立。**

**(b) 數 React commit**:React DevTools Profiler → 錄 10 秒 →
看 commit 數與「Ranked」裡 `App` 的自身時間。
或不裝 extension,用一行 patch 在 `App` 函式體頂端加:
```ts
if (import.meta.env.DEV) { (globalThis as any).__appRenders = ((globalThis as any).__appRenders ?? 0) + 1; }
```
Console 每秒讀一次差值。**判準:> 30 次/秒 = 問題成立。**

**(c) 純瀏覽器量測(不改 code)**:Chrome DevTools → Performance → 錄 10 秒盤中 →
看 Main thread 的 `Task` 密度與 Scripting 佔比。
**判準:Scripting > 40% 且長任務(> 50 ms)頻繁出現。**

### 7.2 量 F5-04(window focus 齊發)

DevTools → Network → 清空 → 切到別的視窗 3 秒 → 切回 Chrome → 看那一瞬間發了幾發。
**判準:切回瞬間 ≥ 8 個請求同時發出,且其中含 `bars` 系列 = 成立。**
同時看後端 `logs/server-*.log` 的 uvicorn access log 時間戳是否叢聚。

### 7.3 量 F5-05(breadth-rows payload)

```bash
curl -s -o /dev/null -w "%{size_download} bytes / %{time_total}s\n" \
  http://127.0.0.1:8721/api/market/breadth/rows
# 再數有狀態的列
curl -s http://127.0.0.1:8721/api/market/breadth/rows | python -c "
import json,sys
d=json.load(sys.stdin); rows=d['rows']
hit=[r for r in rows if r['limit_up'] or r['limit_down'] or r['touched_limit_up'] or r['touched_limit_down']]
print(f'total={len(rows)} useful={len(hit)} waste={100*(1-len(hit)/max(len(rows),1)):.1f}%')
"
```
**判準:`waste > 80%` = F5-05 成立。**

### 7.4 量 F5-06(twMerge)

不要用猜的。DevTools Performance → 錄盤中 10 秒 → Bottom-Up → 搜 `twMerge` / `tailwind-merge`。
**判準:self time > 5% 才值得動;F5-01 修完後重測,大概率會掉到 < 1%。**

### 7.5 量 F5-08(localStorage)

```js
// Console 貼一次,跑 10 秒後看數字
let n = 0; const g = Storage.prototype.getItem;
Storage.prototype.getItem = function (...a) { n++; return g.apply(this, a); };
setTimeout(() => { console.log("getItem/10s =", n); Storage.prototype.getItem = g; }, 10_000);
```
**判準:> 10,000 次/10 秒 = 成立。**

### 7.6 回歸判準(改完之後)

一次改動後要同時滿足:
1. `App` render 次數 ≤ 5 次/秒(盤中);
2. Performance 錄製 60 秒內長任務(> 50 ms)數量 = 0;
3. 閃電梯點價 → 確認窗出現的延遲 < 50 ms(用 Performance 的 Interaction track 量 INP);
4. 既有 gate 全綠:`npm test` + `npx tsc -b` + `npx eslint src` + `npx react-doctor@latest --scope changed --no-telemetry`;
5. 真環境:盤中 `grep '佇列滿' logs/server-*.log` 仍為 0(WS 打包不得讓後端 queue 爆);
6. 側欄 / 圖牆 / 右欄三處的價格在同一秒顯示同一個值(合併打包不得產生分岔)。

---

## 8. 建議的施作順序

| 序 | 項目 | 理由 |
|---|---|---|
| 0 | 跑 §7.1 / §7.2 / §7.3 三個量測,留基線數字 | 鐵則 D:沒有量測不准改 |
| 1 | **F5-09**(一行 `useMemo`)+ **F5-08**(getSnapshot 去 IO) | 零風險、零契約,先拿掉純白燒 |
| 2 | **F5-04**(queryClient defaultOptions,逐支覆核自癒路徑) | 獨立 🔴 commit;立刻解掉 alt-tab 齊發 |
| 3 | **F5-01**(watchlist_quote 打包 + external store) | 根治;訊息數降兩個數量級 |
| 4 | **F5-03**(futures external store)+ **F5-07**(頁級 memo) | 與 3 同一個 pattern,一起做 |
| 5 | 重跑 §7.1 量測 —— 若 App render 已 ≤ 5/s,**F5-02 / F5-06 / F5-10 全部重新評估是否還需要** | 避免過度工程 |
| 6 | **F5-05**(breadth-rows 後端濾列) | 獨立於前端,可並行;但空態文案分岔要小心 |
| 7 | 視 5 的結果決定 **F5-02**(Activity)/ **F5-10**(虛擬化) | |

---

## 9. 硬約束清單(改動時必須同時處理的跨檔契約)

引用自 CLAUDE.md §4,不重述全文:

1. **「個股逐筆 = `ticks` 打包訊息,單筆 `tick` 型別已退役」** —— F5-01 的新 `watchlist_quotes`
   要比照這一條的形狀寫進 §4(產生點 / 讀者 / 漂掉的症狀 / 釘住的測試),並沿用同樣的
   「舊 dist 對未知型別靜默丟棄 → 部署一律前後端同版」教訓。
2. **「`/ws/stock` 入站 `view` 訊息」** —— 同一條 WS,F5-01 不得動到 `view` 的出站路徑
   (`useStockStream.ts:520-522` 的 `sendView`,onopen 必重送)。
3. **「WS 心跳契約」`WS_HEARTBEAT_SECS` 10 s ↔ `WS_SILENCE_TIMEOUT_MS` 30 s** ——
   合併打包後若某秒零 dirty 就不發訊息,心跳仍由 `ws.py` relay 直送,不受影響;
   但**不可**把心跳併進打包(併了就是把 watchdog 的判準綁到行情上)。
4. **「訊號列 `notify` 欄」/「政策列形狀」** —— F5-09 的 memo 不動語意,但 `signals` 的
   identity 若改變會影響 `useSignalAlerts` 的合併窗,不要順手改 `mergeSignals`。
5. **「日 K 定稿界前後端同值」`DAILY_FINAL_TIME`** —— F5-04 改 `staleTime` 預設時,
   `dayBarsStaleTime` 是顯式覆寫,不受全域預設影響;但要確認 `refetchOnWindowFocus: false`
   不會拿掉「14:01 那一發」的補救路徑(它走 `refetchInterval`,不走 focus,安全)。
6. **`WATCHLIST_LIMIT = 150` 的效能預算註解** —— CLAUDE.md 明記「第二類讀者 = 以『檔數 × 單價』
   推理的效能預算註解(stock_engine / watchlist_service / stock_state / GroupGridView 各處)」。
   F5-01 會改變「單價」,**這些註解的最壞值要跟著重算**。
7. **`ROW_H = 52` 是拖曳落點幾何的分母** —— F5-10 的虛擬化不得套用在 `WatchlistSidebar`。
8. **Windows / localhost 限制** —— 後端是 Windows 桌面 app + ZMQ localhost,
   所有「降低請求數」的收益主要在 **CPU 與 TC4 `api.lock` 競爭**,不在網路頻寬。
   F5-04 / F5-05 的真正價值是少搶 `api.lock`,不是省 MB。

---

## 10. 待確認 / 需要 user 回答

1. **盤中 `watchlist_quote` 的實際頻率**:我從 `_flush_watchlist_loop` 的 per-code publish
   推導出 80–150 則/s,但「一秒內有幾檔真的有成交」要開盤實測(§7.1(a))。
   冷門股多的組合可能只有 20–30 則/s,那 F5-01 的嚴重度要降一級。
2. **是否接受改 WS wire format**:F5-01 的根治半段要新增訊息型別,
   代價是一次「前後端同版部署」(CLAUDE.md 已記過 #187 的 dist 舊 build 事故)。
   若不接受,只做前端 external store 那一半也能拿到「重繪範圍縮小」的收益,
   但拿不到「render 次數降低」—— 效果大約是總收益的 40%。
3. **`CorrPage` / `TxoPage` 的 WS 是否可以在 hidden 時斷線**:
   這決定 F5-02 能不能全面套 `Activity`。需要確認 `/ws/corr` 與 `/ws/txo-pnl` 重連後
   首則是否為完整全量(corr 看起來是「每秒推全量快照」= 安全;txo 的 `setData(msg as Snapshot)`
   整份覆蓋 = 看起來也安全,但 `totals.ticks` 這類累積量的語意要確認)。
4. **`breadth-rows` 濾列後,「暫無資料(延遲)」的新判準**:
   走 `as_of === null`,還是後端加 `scanned` 欄位?這是 user 決策(影響畫面文案語意)。
5. **是否要為了效能引入新相依**:專案 runtime 前端相依只有 5 個(react / react-dom / TQ / clsx / tailwind-merge),
   這個克制是刻意的。`@tanstack/react-virtual`(F5-10)是唯一一個我認為值得的,但它也只解 low/medium 問題。
6. **INP 目標值**:「下實單的系統,速度夠快夠順暢」需要一個數字。
   建議定 **閃電梯點價 → 確認窗出現 < 50 ms(p95)**,以此反推允許的 render 預算。
   沒有這個數字,F5-06 / F5-10 這類「要不要做」的題目沒有判準。
