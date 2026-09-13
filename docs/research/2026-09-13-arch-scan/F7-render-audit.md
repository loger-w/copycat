# F7 — 前端跨切 render 稽核(主執行緒預算)

> 範圍:`C:/side-project/copycat/frontend/src` 全庫(160 source + 156 test / 75,233 LOC)
> 目標:回答「畫面為什麼會卡」,給出主執行緒預算表與分層改造建議。
> 方法:更新來源清單 → 重繪範圍表 → 反模式全庫搜尋 → React 19 特性利用度 → 預算估算。

---

## 0. 一句話結論

**這個前端的單點最大問題不是「某個元件慢」,而是「每一則 WebSocket 訊息都讓五個 tab 的整棵樹跑一次 render function」。**

這不是我的推測,是這個 repo 自己量過並寫在程式碼註解裡的事實:

```ts
// frontend/src/lib/dev-perf-guard.ts:6-9
//  React 19.2 development build 的 Component Performance Track … 對每個「props identity 變了」的
//  re-render 打一筆 `performance.measure`(含 Changed Props diff 的 detail,~1.8 KB);…
//  本 app 每則 WS 訊息都讓整棵樹 re-render → 實測 632 筆/秒 ≈ 1.1 MB/s,
//  看盤數小時後 renderer 膨脹到 10 GB 級 → Aw Snap
```

`dev-perf-guard` 修的是**症狀**(User Timing buffer 無上限),根因「每則 WS 訊息全樹重繪」原封不動。
production build 沒有那段 measure 程式碼,所以記憶體不再爆;但**render 工作量一模一樣還在**。

值得先講清楚的反向結論:**這個 codebase 的個別元件層級最佳化做得非常紮實**
(`ChartStatic` / `EnergySub` / `GroupCard` 三個 memo 邊界、模組層 `EMPTY_*` 常數 identity、
`useMemo` deps 逐條寫了為什麼、`setHover` 的 bail-out、`setDrag` 的 same-reference return、
`TickRow.n` 這種為了 React key 穩定性專門設計的後端契約)。
問題全部落在**元件之上的那一層**:狀態放在 App、沒有外部 store、沒有 React Compiler、
tab 用 `hidden` 保留 DOM 而 React 不知道它是隱藏的。
所以改造方向是**架構級的三件事**(細節見 §7),不是再多包幾層 `memo`。

---

## 1. 架構地圖

### 1.1 元件樹(含狀態持有者)

```
main.tsx
└─ StrictMode
   └─ QueryClientProvider (單一 QueryClient,無 defaultOptions)
      └─ App.tsx  ← ★ 全站狀態集中點
         │  state:  tab / visited / stockCode / product / stkfutContract / prevStockCode / stockView
         │  hooks:  useTradingCalendar
         │          useIndexStream()   ← /ws/index      ~1 則/s
         │          useBreadth()       ← /ws/breadth
         │          useCapitalStream() ← /ws/capital
         │          useSignalAlerts()  ← signal-bus(EventTarget)
         │          useStockStream()   ← /ws/stock      ★ 最高頻(見 §2)
         │          useFuturesStream() ← /ws/futures    0.1 s coalesce × N 商品
         │          useFuturesBars("TXF")               60 s 輪詢
         │          useChartToggles()  ← module store
         │
         ├─ <nav> CalendarBadges / VersionDriftBadge / IndexBar
         ├─ tabpanel txo      : hidden={tab!=="txo"}      TxoPage      ← ★ 恆掛
         ├─ tabpanel stock    : hidden={...} visited gate  StockPage   (lazy)
         ├─ tabpanel futures  : hidden={...} visited gate  FuturesPage (lazy)
         ├─ tabpanel index    : hidden={...} 恆 visited     IndexPage   (lazy) ← ★ 恆掛
         ├─ tabpanel corr     : hidden={...} visited gate  CorrPage    (lazy)
         ├─ RightRail (memo)   ← ctx = stockCtx | futuresCtx | NONE_CTX
         └─ ToastStack
```

**關鍵結構事實**:`hidden` 是 HTML 屬性,**對 React 的 reconciliation 完全無意義**。
`tab !== "stock"` 時 `StockPage` 的 render function 照跑、子樹照 diff,只是 commit 出來的 DOM
被 CSS 藏起來。`visited` 閘門只管「第一次 mount 的時機」,mount 之後永遠不 unmount
(App.tsx:117-124 的註解明說「之後 hidden 保留 DOM(§3 慣例)」)。

### 1.2 全庫 memo 邊界(只有 7 個)

```
src/components/corr/RiverCards.tsx:31          RiverCard
src/components/rail/RightRail.tsx:121          RightRail
src/components/stock/CandleChart.tsx:88        ChartStatic
src/components/stock/GroupGridView.tsx:132     GroupCard
src/components/stock/StockIntradayChart.tsx:171 ChartStatic
src/components/stock/StockIntradayChart.tsx:818 EnergySub
```

`StockPage` / `FuturesPage` / `IndexPage` / `CorrPage` / `TxoPage` / `WatchlistSidebar` /
`TickTape` / `OrderBook` / `LadderView` / `PriceLadder` / `SignalRail` / `QuoteTable` /
`PnlChart` / `LimitListSection` / `MarketPane` / `MarketChart` / `FuturesChart` /
`FuturesLadder` / `IntradayChartCore` / `CardIntradayChart` —— **全部沒有 memo**。

### 1.3 資料流(報價 → 畫面)

```
TC4 (ZMQ)
  └─ copycat/server/stock_engine.py
       ├─ _flush_ticks()        0.1 s 打包 → 一則 {"type":"ticks","items":[…]}
       ├─ _flush_watchlist_loop 1 s 一輪,**每個 dirty code 各 self._publish 一則**
       └─ _handle_quote() 尾端  code == _main → **每則 quote 立即 publish 一則 book,零節流**
                 ↓ /ws/stock(單一連線)
  useStockStream.handle(msg)
       ├─ "ticks"            → setAccum(newAccum)  + emitTicks(items) → tick-stream bus
       ├─ "book"             → setAccum({...acc, book})
       ├─ "watchlist_quote"  → setWatchlist(prev => ({...prev, [code]: q}))   ← 每碼一次
       ├─ "status"/"stkfut"  → setStatus / setStkfut
       └─ "signal"           → emitSignal(bus)
                 ↓ 全部是 App 層的 useState
  App re-render  →  五個 tabpanel 子樹全跑  →  RightRail(memo,但 ctx 含 accum)
                 ↓
  tick-stream bus(module EventTarget,繞過 props)→ useGroupLiveAccums → 50 張卡各自 applyTick
```

`tick-stream.ts` 這條 module-level bus 是本專案唯一一處「繞過 React 樹傳資料」的設計,
而且註解寫得很清楚為什麼(「免得為了傳 tick 把 state 提到 App 再逐層 props 往下穿,
50 張卡的 memo 邊界會被打穿」)。**這正是應該擴大適用範圍的那個模式** —— 見 §7.2。

---

## 2. 更新來源清單(每秒觸發次數)

| # | 來源 | 檔案:行 | 頻率(開盤最忙的一秒) | setState 落點 | 是否進 App |
|---|---|---|---|---|---|
| U1 | `/ws/stock` **book**(主圖) | `stock_engine.py:1360`(publish)/ `useStockStream.ts` `case "book"` | **零節流**,TC4 每則主圖 quote 一次。熱門股開盤估 **20–60 則/s** | `setAccum` | ✅ |
| U2 | `/ws/stock` **watchlist_quote** | `stock_engine.py:1826-1831` for-loop 逐碼 `_publish` | 1 s 一輪,但**每碼一則 frame**。150 檔自選 → 一秒內 **最多 150 則**(集中在同一個 100 ms 窗) | `setWatchlist` | ✅ |
| U3 | `/ws/stock` **ticks** 打包 | `stock_engine.py:1782` `_flush_ticks`, `tick_flush_secs=0.1` | ≤ **10 則/s** | `setAccum` + bus | ✅ |
| U4 | `/ws/futures` | `futures_engine.py:173` `flush_interval_secs=0.1`,**per-product** | 3 商品全 dirty → **30 則/s** | `setState` | ✅ |
| U5 | `/ws/index` | `useIndexStream.ts` | ~**1 則/s** | 4 個 setState | ✅ |
| U6 | `/ws/corr` | `useCorrelation.ts` 每秒全量快照 | 1/s | CorrPage 內 | ❌(CorrPage) |
| U7 | `/ws/river` | `useRiver.ts` 每秒 delta | 1/s | CorrPage 內 | ❌ |
| U8 | `/ws/breadth` | `useBreadth.ts` | 低 | `setState` | ✅ |
| U9 | `/ws/capital` | `useCapital.ts:277` | 成交/委託事件驅動,爆單時可達數則/s | `invalidateQueries` → 連鎖 refetch | ✅ |
| U10 | `/ws/txo-pnl` | `useTxoSnapshot.ts` | TXO 推播 | `setData` | ❌(TxoPage 內部,但 TxoPage 恆掛) |
| U11 | signal-bus | `useSignalAlerts.ts` | 事件驅動 + toast TTL timer | `setToasts` | ✅ |
| U12 | TQ 輪詢:capital orders | `useCapital.ts:154` `refetchInterval: 10_000` | 0.1/s | query cache | ✅ |
| U13 | TQ 輪詢:positions | `useCapital.ts:190` `30_000` | 0.033/s | | ✅ |
| U14 | TQ 輪詢:group-state | `useGroupSnapshots.ts:135` `POLL_MS`(60 s) | 0.017/s | | StockPage |
| U15 | TQ 輪詢:bars / breadthRows / names / health / calendar / signalFeed | 各 hook | 合計 < 0.5/s | | 散布 |
| U16 | `useContainerSize` ResizeObserver | `useContainerSize.ts:31` | 僅版面變動;有 1px 去抖 | `setSize` | 各圖 |
| U17 | 圖表 hover `onMouseMove` | `StockIntradayChart.tsx:1328` / `CandleChart.tsx:585` / `PnlChart.tsx:26` / `RiverOverlay.tsx:88` | 滑鼠在圖上時 **~60/s**(有 bail-out,見 §4.1) | `setHover` | 圖本身 |
| U18 | 側欄拖曳 `pointermove` | `WatchlistSidebar.tsx:388` | 拖曳中 ~60/s | `setDrag`(有 same-ref 守門) | StockPage |
| U19 | 梯捲動 `onScroll` | `LadderView.tsx:236` / `FuturesLadder.tsx:460` | 捲動中 | `setFollow`(只一次) | RightRail |

### 2.1 加總(使用者停在「個股(期)」tab、群組檢視、150 檔自選、開盤第一分鐘)

進 **App 層 setState** 的來源:U1 + U2 + U3 + U4 + U5 + U8 + U9 + U11

```
U1  book              20 ~ 60 /s
U2  watchlist_quote   ≤ 150 /s   (150 檔全部有成交的極端;常態 40~80)
U3  ticks              ≤ 10 /s
U4  futures            ≤ 30 /s
U5  index                 1 /s
U8+U9+U11              ~  2 /s
                      ─────────
合計                  ≈ 100 ~ 250 次 App re-render / 秒
```

**這些不會被 React 18/19 的 automatic batching 合併。** 每一則 WebSocket frame 是瀏覽器獨立派發的
一個 task,React 只在單一 task 內批次。所以 250 則 frame = 250 次 render pass。

這與 `dev-perf-guard.ts` 註解裡的「實測 632 筆/秒」量級一致(632 是**元件**級計數,
一次 App render 會產生多筆 measure)。

---

## 3. 重繪範圍表(state 在哪裡 → 誰被拖下水)

| state | 持有者 | 更新頻率 | 重繪範圍 | 範圍是否過大 |
|---|---|---|---|---|
| `accum` | `useStockStream` → App | U1+U3 ≈ 30–70/s | **App 整棵樹**(5 個 tabpanel + RightRail,ctx 含 accum) | ★★★ 極度過大 |
| `watchlist` | `useStockStream` → App | U2 ≤ 150/s | **App 整棵樹** | ★★★ 極度過大 |
| `futuresStream.state` | `useFuturesStream` → App | U4 ≤ 30/s | **App 整棵樹**(含完全無關的 TXO / 個股 / 指數 tab) | ★★★ |
| `twse/otc/txf` | `useIndexStream` → App | 1/s | App 整棵樹 | ★★ |
| `alerts.toasts` | `useSignalAlerts` → App | 事件 + TTL | App 整棵樹 | ★★ |
| `tab` / `stockCode` / `product` | App | 使用者操作級 | App 整棵樹(合理) | — |
| `localHover` | `IntradayChartCore` | 60/s(hover 時) | 該張圖(ChartStatic memo 擋住線層) | ✔ 已處理 |
| `syncMin` | `GroupGridView` | 跨分鐘才變 | 整面圖牆(刻意,F3 功能) | ✔ |
| `drag` | `WatchlistSidebar` | pointermove(有 same-ref 守門) | 側欄 150 列 | ★ |
| `live`(群組) | `useGroupLiveAccums` | 10/s | 只有收到成交的卡換 identity(`GroupCard` memo 擋住) | ✔ 已處理 |
| `follow` / `centerRequest` | `LadderView` / `RightRail` | 低 | 梯 | ✔ |

### 3.1 一次 App render 實際跑過什麼(使用者在個股 tab)

| 子樹 | 是否跑 render function | 元素量級 | 有無 memo 護欄 |
|---|---|---|---|
| `TxoPage`(hidden) | ✅ 跑 | `QuoteTable` ~60 履約價 × 21 cell ≈ **1,300 元素** + `PnlChart` SVG + `OrderPanel` + `MetricsBar` | ❌ 完全沒有 |
| `StockPage`(顯示) | ✅ 跑 | `WatchlistSidebar` 150 列 × ~14 元素 ≈ **2,100**;`SignalRail`;`StockChart`;`TickTape` 30 列 | 只有 GroupCard / ChartStatic |
| `FuturesPage`(hidden) | ✅ 跑 | `FuturesChart` 重算 `futuresBarsToAccum`(1365 格)+ `FuturesLadder` | ChartStatic 擋住線層,**adapter 沒擋** |
| `IndexPage`(hidden,恆 visited) | ✅ 跑 | 兩個 `MarketPane` + `IntradayChartCore` ×2 + `LimitListSection` + `AdvanceDeclineChart` | ChartStatic 擋住線層 |
| `CorrPage`(hidden,若造訪過) | ✅ 跑 | `RiverPanel` + 11 腿 `RiverCard`(memo) | RiverCard memo |
| `RightRail`(memo) | ctx 變就跑 | `PriceLadder` **200 列 × ~6 元素 ≈ 1,200** + `buildLadder` 200 物件 | memo 的 dep 含 `accum` → U1/U3 必打穿 |

**粗估一次完整 App render 要建立 / diff 5,000 – 8,000 個 React element。**

---

## 4. 反模式全庫搜尋結果

### 4.1 `useEffect` 裡 setState 造成的連鎖重繪 —— ✅ 乾淨

repo 裝了 `eslint-plugin-react-you-might-not-need-an-effect`(`eslint.config.js:19`,level `warn`)。
全庫只有 **一處** `eslint-disable`:

```ts
// src/components/stock/StockPage.tsx:127
onViewChange?.(readStockView()); // eslint-disable-line react-you-might-not-need-an-effect/…
```

而且理由寫了 15 行(上提整份 view 會動 50+ 呼叫點;`notifiedRef` 守門避免 render 迴圈)。
其餘全部用官方的 **adjust-state-during-render** pattern:

- `App.tsx:150-154`(`prevStockCode`)
- `StockPage.tsx:143-147`(`prevCode`)
- `RightRail.tsx:184-196`(`prevInstrument`)
- `StockChart.tsx:~148-156`(`isFut` 收斂)
- `lib/fee-discount.ts:96`

**這一項不用改。** 它是全庫做得最好的部分。

### 4.2 行內 object / array / function 當 props —— ⚠️ 大部分已處理,但護欄是「人工紀律」

已處理的證據(模組層常數 identity):

```ts
// App.tsx:70            const NONE_CTX: RailContext = { kind: "none" };
// GroupGridView.tsx:279 const NOOP_HOVER = (): void => {};
// GroupGridView.tsx:56  const EMPTY_CODES: readonly string[] = [];
// StockIntradayChart.tsx:127-131  EMPTY_PEGS / EMPTY_IDX_LINES
// StockIntradayChart.tsx:158      EMPTY_ENERGY
// fill-marks.ts  EMPTY_FILLS / EMPTY_MARKS ; position-summary.ts EMPTY_POSITIONS
// chart-hlines.ts EMPTY_HLINES
// stock-intraday-svg.ts:38,45  SPOT_WINDOW / STKFUT_WINDOW(註解明寫「行內 {} 會打穿兩層 memo」)
```

**風險不在現況,在於沒有機械閘。** repo **沒有裝 `eslint-plugin-react-hooks`**
(`eslint.config.js` 只有 js.recommended + tseslint.recommended + you-might-not-need-an-effect),
所以 `exhaustive-deps` 與 `rules-of-hooks` 都沒有 lint 守。程式碼裡到處寫著這件事:

```ts
// StockIntradayChart.tsx:1074  「(專案 eslint 沒裝 react-hooks,exhaustive-deps 抓不到)」
// StockIntradayChart.tsx:1093  「hook 不可條件化(本 repo 沒裝 react-hooks lint,漏了不會被擋)」
// GroupGridView.tsx:~380       「hook 不可條件化(本 repo 沒裝 react-hooks lint,漏了不會被擋)」
// App.tsx:~253                 「deps 完整性**沒有 lint 守**,守門是 App.memo.test.tsx 的計次」
```

守門靠的是 `App.memo.test.tsx` 這種 render 計次測試 —— 有效,但覆蓋不到新寫的元件。

### 4.3 `useMemo` 依賴含每次都新建的物件 —— 找到 2 處實質命中

**(a) `StockChart.tsx` 的 `bars`**(檔案 `src/components/stock/StockChart.tsx`,`bars` useMemo):

```ts
const liveMinutes = liveOn && isMinute ? accum.minutes : null;
…
const bars = useMemo(() => {
  const raw = data?.bars ?? [];
  if (liveMinutes !== null) {
    return aggregateBars(mergeLiveMinuteBars(raw, liveMinutes, liveToday, nowMinute), minutesOf(mode));
  }
  …
}, [data, mode, liveMinutes, liveDay, dayOpen, liveToday, nowMinute]);
```

`accum.minutes` 是 `applyTick` **每筆成交新建的 Map**(`stock-accum.ts`:`const minutes = new Map(acc.minutes)`),
所以每 0.1 s 一則 ticks 打包就換一次 identity → memo 必失效 → `aggregateBars` 掃 30 日 1 分 K
**≈ 5,900 根**。程式碼自己的註解承認這個量級:

```
// 成本 = 一次 aggregateBars(30 日 1 分 K ≈ 5,900 根)+ merge O(補的根數)
```

memory 記錄的 prod bench 是 **p95 6.6 ms**。10 Hz → **66 ms/s ≈ 6.6 % 主執行緒**,只為了
「最後一根 K 棒要即時」。使用者切到分 K 模式時常駐。

**(b) `FuturesChart.tsx` 的 `accum`**(`src/components/futures/FuturesChart.tsx:314`):

```ts
const accum = useMemo(
  () => futuresBarsToAccum({ bars: slice, live: …, ref: …, name: …, code: product }),
  [slice, liveIndex, liveP, state?.ref, state?.name, product],
);
```

`liveP = state?.p` 每則期貨 WS 推播(0.1 s coalesce)就變 → memo 每 0.1 s 失效 →
`futuresBarsToAccum` 重建 **1365 格 minutes Map + VP Map**
(`ALLDAY_LEN` 常數見 `stock-intraday-svg.ts:MINUTE_SNAP_RADIUS` doc:「`ALLDAY_LEN` = 1365」)。
接著 `buildIntradayGeometry` 也吃新的 `accum.minutes` → `windowedEntries` 再 **拷貝 + 排序 1365 格**。

**而這一切在使用者停在個股 tab、期貨 tab 被 `hidden` 藏起來時照跑。**

### 4.4 map 裡用 index 當 key —— 低風險,全部是固定長度集合

| 檔案:行 | 集合 | 判定 |
|---|---|---|
| `OrderBook.tsx:59,76,111` | 五檔(固定 5 列) | ✔ 安全 |
| `ChartReadout.tsx:40` | 4–6 欄固定 | ✔ |
| `QuoteTable.tsx:203` | `key={row.strike}`(實際用 strike,`i` 只拿來比 atm) | ✔ |
| `CandleChart.tsx:176,203,221,300,353` | `g.candles` / `g.volBars` —— **可變長度序列** | ⚠️ 平移縮放時整段重掛(見 §6.4) |
| `WatchlistSidebar.tsx:779` | `groups.map((g,i)` —— 檢查用 `key={g.name}`? 需確認 | ⚠️ |
| `RadioPills.tsx:63` | 固定選項 | ✔ |

`CandleChart` 那一組是唯一真正的候選問題:viewport 平移時 `g.candles` 的視窗滑動,
index key 會讓整批 `<rect>` 卸載重掛。但 `CandleChart` 外層有 `key={code}-${mode}`
而且 `ChartStatic` memo 包住,平移只在使用者拖曳時發生 —— **不在自動更新熱路徑上**,
列為 low。

反面教材(做對的):`TickTape.tsx` 用 `key={t.n}`,且為此在後端開了一條 `seq` 契約
(CLAUDE.md §4「個股 `seq` 的兩個口徑」),註解寫明「回推索引會讓整個 tbody 卸載重掛」。

### 4.5 render 期間做重計算 —— 找到 3 處在熱路徑上

**(a) `PriceLadder.tsx:257` `buildLadder` 完全沒有 `useMemo`:**

```ts
// src/components/stock/PriceLadder.tsx:257
const ladder = buildLadder({
  center: last?.p ?? null,
  ref: meta?.ref ?? null,
  upper: meta?.upper ?? null,
  lower: meta?.lower ?? null,
  book,
});
```

`buildLadder`(`lib/stock-tick.ts:120-163`)從漲停走到跌停,**每個合法 tick 一列**:

```ts
for (let p = upperBound; p >= lowerBound; p = stepDown(p)) {
  …
  rows.push({ priceMilli: p, bidQty: bidMap.get(p) ?? 0, askQty: askMap.get(p) ?? 0,
              isCenter: false, dimmed: Math.abs(p - anchor) / anchor > 0.05 });
}
```

台股 tick 表設計讓 ±10% 在各價帶都約 **200 列**。外加兩個 `new Map(book.bids/asks)`。
`PriceLadder` 住在 `RightRail`(memo)底下,而 `RightRail` 的 `ctx = stockCtx`
的 dep 是**整個 `accum`**:

```ts
// App.tsx:~262
const stockCtx = useMemo<RailContext>(() => ({ … book: accum?.book ?? null, last: accum?.last ?? null, … }),
  [stockCode, stkfutContract, accum]);
```

`accum` 每則 book / 每則 ticks 換 identity → `stockCtx` 換 → `RightRail` memo 失效 →
`buildLadder` 重跑。**U1+U3 ≈ 30–70 次/s × 200 列物件 = 6,000–14,000 物件配置/秒。**

**(b) `PriceLadder.tsx:245-254`** 同一段裡還有 `aggregateLots`(掃全帳戶當日 fills 建 seq 索引)
與 `positionRows` / `markMap`,註解自承「每 render 重算:純算術 … 量級小先不包,長大再對齊」。
散戶單日數十筆 fills,量級確實小,**但它跟著同一個 30–70 Hz 的節拍在跑**。

**(c) `StockIntradayChart.tsx:~1208`** `sideSummary(accum.minutes, xw)` 在 render body:

```ts
const side = card || index ? null : sideSummary(accum.minutes, xw);
```

`sideSummary` 走一遍最多 271 格。單檔頁每則 book / tick 一次 → 30–70 × 271 = 8k–19k 次迭代/秒。
量級不大,但它是 `useMemo` 一行就能省掉的。

### 4.6 forced reflow(layout 讀取)—— 找到 1 處在高頻 handler 裡

```ts
// src/components/stock/WatchlistSidebar.tsx:285-318  zonesNow()
const push = (key, count) => {
  const box = section.getBoundingClientRect();                    // ← 每個 section 一次
  …  listTop: isCollapsed ? box.bottom : list.getBoundingClientRect().top,   // ← 再一次
};
push(null, ungrouped.length);
for (const g of groups) push(g.name, g.codes.length);
const aside = asideRef.current?.getBoundingClientRect();          // ← +1
const voidBelowY = stickyRef.current?.getBoundingClientRect().bottom;  // ← +1
```

被 `onHandleDown` 註冊的 `pointermove`(`WatchlistSidebar.tsx:388`)**每則呼叫一次**。
以 12 個群組計:12 × 2 + 2 = **26 次 `getBoundingClientRect()` / pointermove**,
拖曳時 ~60 Hz → **1,560 次 layout 讀取/秒**。而同一時間背景還有 U1/U2 在 commit DOM,
所以每一次讀取都可能觸發 forced synchronous layout。

這是**拖曳期間**才有的成本(使用者操作級,不是常駐),但拖曳正是最需要跟手的動作。
註解承認「**每次 pointermove 重算** —— 只在 pointerdown 算一次的話,側欄捲動或錯誤文案出現消失
都會讓 rect 失效」—— 理由成立,但可以改成 `pointerdown` 算一次 + `scroll`/`ResizeObserver`
失效重算,不必每 frame 全量。

其餘 `getBoundingClientRect` 呼叫點全部在**單次事件**內讀一次(`e.currentTarget.getBoundingClientRect()`),
屬於 `mousemove` 的標準寫法,量級是 1 次/事件,可接受:

```
StockIntradayChart.tsx:1328   onMove → 1 次
PnlChart.tsx:26               handleMouseMove → 1 次
RiverOverlay.tsx:88           handleMouseMove → 1 次
useCandleHover.ts:25          → 1 次
useCandleViewport.ts:57,78    wheel / drag → 1 次
```

### 4.7 inline ref callback —— 找到 2 處在大列表上

```ts
// src/components/stock/LadderView.tsx(rows.map 內)
ref={(el) => {
  if (el) rowRefs.current.set(r.priceMilli, el);
  else rowRefs.current.delete(r.priceMilli);
  if (r.isCenter && el) centerRef.current = el;
}}
```

React 對 **identity 改變的 callback ref** 會在每次 commit 先用 `null` 呼叫舊的、再用 element
呼叫新的。inline arrow 每次 render 都是新 identity → **200 列 × 2 次呼叫 = 400 次 ref 呼叫
+ 400 次 Map 寫入 / 刪除,每次 PriceLadder render**。以 30–70 Hz 計 = **12,000–28,000 次/秒**。

同型:
```ts
// WatchlistSidebar.tsx  <section ref={(el) => { if (el) sectionRefs.current.set(null, el); else … }}>
```
(群組數量級小,影響小。)

React 19 支援 ref cleanup 函式,但**沒有解決 identity 問題** —— 解法是把 callback 提出去
`useCallback` 化(需要 per-row 穩定 callback,通常做法是把 row 抽成 memo 子元件並用
`data-price` 屬性 + 父層 `querySelector`,或用 `useCallback` 工廠 + Map 快取)。

### 4.8 其他

- **Intl 快取:✅ 已做**。`lib/format.ts:1-2` 兩個 module 級 `Intl.NumberFormat` 單例。
  殘留三處直接 `toLocaleString`:`OrderBook.tsx:30`、`pnl-format.ts:13`、`OrderPanel.tsx:302`。
  `OrderBook.tsx:30` 在五檔每格都跑(10 格 × 30–70 Hz = 700/s),`toLocaleString` 每次會走
  一次 ICU locale 解析 —— 小,但是「一天能改」的零風險項。
- **`localStorage` 在 render 期讀取**:`readLocal` 都在 `useState` initializer 或事件裡,✔。
- **`new Date()` 在 render body**:`StockChart.tsx`(`now` / `today`)、`GroupGridView.tsx`(`today`)、
  `PriceLadder.tsx`(`ymdWindow(new Date(), [0])`)、`FuturesChart.tsx`(`liveSlotOf(new Date(), …)`)。
  都是刻意的(memo deps 表達不了「現在幾點」),成本可忽略。

---

## 5. React 19 特性利用度 —— 幾乎全部沒用

| 特性 | 現況 | 機會 |
|---|---|---|
| **React Compiler** | ❌ **沒裝**。`package.json` devDependencies 無 `babel-plugin-react-compiler`;`vite.config.ts` 的 `react()` 沒有 babel 設定 | ★★★ 最高 CP 值。全庫手工 memo 紀律(§4.2 的十幾個 `EMPTY_*` 常數、`useMemo` deps 逐條註解)正是 compiler 自動做的事 |
| `useSyncExternalStore` | ❌ 零使用(全庫 grep 無命中)。自製 store 有 3 份:`tick-stream.ts`(EventTarget)、`signal-bus.ts`、`useChartToggles`(module store)、`fee-discount.ts` | ★★★ 這是把 `accum`/`watchlist` 移出 App 的標準工具 |
| `useDeferredValue` | ❌ 零使用 | ★★ 圖牆 / 側欄可延後 |
| `startTransition` | ❌ 零使用 | ★★ 切 tab、切群組、換股 |
| `<Activity>`(React 19.2) | ❌ 零使用。tab 用 `hidden` + 常駐 mount 手刻 | ★★★ **這正是 `<Activity mode="hidden">` 設計來解的問題**:保留 state 與 DOM,但**跳過 render** |
| `use()` | ❌ | — |
| `<Suspense>` | ✔ 有(lazy tab) | — |
| `memo` | 7 處 | — |
| `StrictMode` | ✔ 有(`main.tsx`) | prod build 無成本;dev 下 double-invoke 讓量測失真,量測時要注意 |

---

## 6. 主執行緒預算估算

### 6.1 開盤最忙的一秒(使用者停在個股 tab / 群組檢視 / 150 檔自選)

```
事件數
  book                 ~40  則/s   (熱門股;零節流,上限取決於 TC4)
  watchlist_quote      ~80  則/s   (150 檔中約半數有成交)
  ticks 打包            ~10  則/s
  futures              ~30  則/s
  index                  1  則/s
  其他                   ~2  則/s
  ───────────────────────────────
  App re-render        ~163 次/s   ← 平均每 6.1 ms 一次
```

### 6.2 單次 App render 的工作量拆解(估算,標記為估算)

| 項目 | 元素 / 迭代量 | 估時 |
|---|---|---|
| `TxoPage` 子樹(hidden) | ~2,000 元素 | ~1.2 ms |
| `StockPage` 骨架 + `WatchlistSidebar` 150 列 | ~2,100 元素 + 150× (`secSummary`+`futSummary`+`limitState`) | ~1.5 ms |
| `FuturesPage`(hidden) | `futuresBarsToAccum` 1365 格 ×2 Map + geometry 1365 格排序 **(只在 futures WS 那 30 次)** | ~2.0 ms(命中時) |
| `IndexPage`(hidden) | 2× `IntradayChartCore`,ChartStatic memo 擋住線層 | ~0.6 ms |
| `RightRail` → `PriceLadder` | `buildLadder` 200 物件 + 200 列 JSX + **400 次 ref 呼叫** | ~1.5 ms |
| `StockChart` → `IntradayChartCore` | geometry memo 命中時只跑 readout / toggleDefs / sideSummary(271 格) | ~0.4 ms |
| 群組圖牆 50 張卡 | `GroupCard` memo,只有收到成交那幾張重畫 | ~0.3 ms |
| React reconcile + commit | 5,000–8,000 元素 | ~1.5 ms |
| **合計(估算)** | | **≈ 5–9 ms / render** |

### 6.3 結論:預算超支

```
163 次/s × 6 ms  ≈  978 ms  /  1000 ms  主執行緒
```

**開盤那一分鐘,主執行緒基本上是滿的。** 16.7 ms/frame 的預算裡,連續兩三則 WS 訊息就吃光。
可觀察症狀應該是:

1. 開盤 09:00–09:05 滑鼠 hover 十字線明顯遲滯、跟不上游標
2. 側欄拖曳掉格(§4.6 的 1,560 次/s layout 讀取疊上去)
3. 閃電梯點價的視覺回饋延遲(但點價本身走 event handler,**不會漏單**)
4. 切 tab 有可見卡頓
5. dev build 下更嚴重(StrictMode double-invoke + Component Performance Track)

**這也解釋了 CLAUDE.md §1 那條「看盤日常一律用 `npm run preview` 不用 `npm run dev`」的紀律**
—— 那是在繞過同一個根因。

### 6.4 誠實的不確定性

- **book 的實際頻率沒有量過**。後端 `stock_engine.py:1360` 確實零節流,但 TC4 對單一 symbol
  的 REALTIME 推播頻率我沒有實測數字。40/s 是估計,可能是 5/s 也可能是 100/s。
  **這是全篇最該先量的一個數字**(見 §9 M1)。
- 每次 render 的 5–9 ms 是從元素量推的估算,不是量測。實機可能因 React 19 的
  bailout 路徑而更快。
- `watchlist_quote` 在一個 asyncio loop iteration 內連續 `_publish`,瀏覽器**可能**把多個
  frame 合成一個 `message` 事件批次嗎? **不會** —— WebSocket 每個 frame 派發一個 MessageEvent。
  但作業系統 / 瀏覽器的 IO 執行緒可能在同一個 task 內連續派發多個 —— 這一點需要用
  DevTools Performance 的 Event 標記實測確認(§9 M2)。

---

## 7. 分層改造建議

### 7.1 Tier 0 —— 一天內能做完、零架構風險(合計預期省 30–50 % 主執行緒)

| # | 改動 | 檔案:行 | 預期 |
|---|---|---|---|
| T0-1 | **裝 React Compiler** | `package.json` + `vite.config.ts` 的 `react({ babel: { plugins: [["babel-plugin-react-compiler", {}]] } })` | 自動 memo 化所有元件與 hook 回傳值,等於把全庫 §4.2 的手工紀律機械化。**先跑一次 `npx react-compiler-healthcheck` 看相容率** |
| T0-2 | **後端把 `book` 併進既有的 0.1 s coalesce** | `copycat/server/stock_engine.py:1360` —— 改成標 dirty,由 `_flush_ticks` 同一支 timer 帶出(或另開一支 `_flush_book`) | 40/s → 10/s,**直接砍掉 ~25 % 的 App render**。⚠ 契約影響見 §8 |
| T0-3 | **後端把 `watchlist_quote` 一秒一批打包成一則** | `stock_engine.py:1826-1831` 的 for-loop 改成組一則 `{"type":"watchlist_quotes","items":[…]}` | 80/s → 1/s,**砍掉 ~50 % 的 App render**。⚠ 這是新 wire 契約,見 §8 |
| T0-4 | `PriceLadder` 的 `buildLadder` 包 `useMemo` | `PriceLadder.tsx:257`,deps `[last?.p, meta?.ref, meta?.upper, meta?.lower, book]` | book 沒變的 render 省掉 200 物件 |
| T0-5 | `LadderView` 的 row ref 改穩定 callback | `LadderView.tsx` rows.map 內的 inline `ref` | 省 400 次 ref 呼叫 / render |
| T0-6 | `sideSummary` 包 `useMemo` | `StockIntradayChart.tsx:~1208` | 省 271 格迭代 |
| T0-7 | `zonesNow()` 快取 + 失效 | `WatchlistSidebar.tsx:285` | 拖曳期省 1,500 次/s layout 讀取 |
| T0-8 | `OrderBook.tsx:30` 的 `toLocaleString` 改走 `lib/format` 的 `nf` 單例 | `OrderBook.tsx:30` | 微小但零風險 |
| T0-9 | **裝 `eslint-plugin-react-hooks`** | `eslint.config.js` | 不是效能改動,是**把現有的人工紀律機械化**(§4.2 的四處註解都在喊這件事) |

T0-2 / T0-3 是本篇 **CP 值最高的兩條**:改的是後端 4 行,砍掉的是前端 75 % 的 render 次數。

### 7.2 Tier 1 —— 一到兩週、架構級但可漸進

| # | 改動 | 做法 | 預期 |
|---|---|---|---|
| T1-1 | **`<Activity mode="hidden">` 包住非當前 tab** | `App.tsx` 的五個 tabpanel:`<Activity mode={tab==="stock"?"visible":"hidden"}>` 取代 `hidden={…}`。React 會保留 state 與 DOM 但**降低優先權 / 跳過更新** | 砍掉 TxoPage / IndexPage / FuturesPage / CorrPage 四個子樹的常駐 render ≈ **40 % 工作量**。⚠ 需確認 React 版本(19.2+)與 `<Activity>` 的穩定度;過渡方案見 T1-2 |
| T1-2 | (T1-1 的保守替代)**把每個 tabpanel 包 `memo`,props 只傳該 tab 真正要的東西** | `export default memo(StockPage)` 等;App 的 props 全部 `useMemo` 化 | 同上,但要人工維護 props identity;`<Activity>` 可用時直接跳過這一步 |
| T1-3 | **把 `accum` / `watchlist` 移出 App,改 module store + `useSyncExternalStore`** | 沿 `lib/tick-stream.ts` 既有模式:`lib/quote-store.ts` 持有 accum/watchlist,`useStockStream` 只負責寫入;讀者各自 `useSyncExternalStore(subscribe, () => store.get(code))`。**side bar 每列自己訂閱自己那一檔** | 報價更新只重繪「真的用到那一檔的那幾個節點」。這是整份稽核最根本的修法 —— 它讓 §3 的重繪範圍表從「整棵樹」變成「一格」 |
| T1-4 | `WatchlistSidebar` 每列抽成 `memo` 子元件 + 各自訂閱 store | 配合 T1-3 | 150 列 → 只有價變的那幾列重繪 |
| T1-5 | `FuturesChart` 的 `futuresBarsToAccum` 改增量更新 | 現在是每次全量重建 1365 格 Map;live 點只改一格,可以 `new Map(base)` + set 一格,或把 base map 用 `useMemo([slice])` 分離、live 那格另外疊 | 省掉隱藏 tab 每 0.1 s 的 1365 格重建。**T1-1 做了以後這條的急迫性大降** |
| T1-6 | `StockChart` 的 live-last-bar 改增量 | 現在 `aggregateBars(5900 根)` 每 0.1 s 一次(p95 6.6 ms)。可以把「正式段的聚合」`useMemo([data, mode])`,只對尾端補的幾根做聚合再 concat | 省 6.6 % 主執行緒 |
| T1-7 | `startTransition` 包住切 tab / 切群組 / 換股 | `App.tsx` `setTab` / `StockPage` `selectGroup` / `setStockCode` | 切換不阻塞輸入回饋 |

### 7.3 Tier 2 —— 只有在 T0+T1 做完仍不夠時才考慮

| # | 改動 | 取捨 |
|---|---|---|
| T2-1 | **虛擬化長列表**(`@tanstack/react-virtual`) | 目標:`WatchlistSidebar` 150 列、`PriceLadder` 200 列、`QuoteTable` 60×21。代價:多一個相依(但 TanStack 系已在用,心智負擔低)、`scrollIntoView` 置中邏輯要重寫(`LadderView.tsx:155-168` 的 follow 機制)、a11y 與既有測試(`data-testid` 全量查詢)會紅一片。**PriceLadder 的置中跟隨與虛擬化衝突最大,建議最後做** |
| T2-2 | **分時圖改 Canvas** | 目前手刻 SVG(`stock-intraday-svg.ts` 921 LOC + `StockIntradayChart.tsx` 1724 LOC)。單張圖的 SVG 節點數:priceLine polyline 1 + vwapLine 1 + 271 energy bar `<rect>` + ~200 VP bar + 11 yTick + 標籤 ≈ **500 節點**。圖牆 50 張 = **25,000 SVG 節點**。Canvas 可以把這一層完全移出 DOM。代價:**極大** —— hover 命中、a11y(`role="img"` + `aria-label`)、jsdom 測試(156 個測試檔大量靠 `data-testid` 查 SVG 節點)、`ChartStatic` memo 邊界全部作廢。**目前 memo 已經擋住這一層,不建議動** |
| T2-3 | **Web Worker 做 geometry** | 把 `buildIntradayGeometry` / `futuresBarsToAccum` / `aggregateBars` 移進 worker,回傳 typed array。代價:序列化成本可能吃掉收益(271 格的 geometry 序列化 > 計算本身);只有 T2-2 的 canvas + `OffscreenCanvas` 才真的划算 |
| T2-4 | 換 SVG 圖表庫 | **不建議**。現有手刻 SVG 幾何有大量台股領域知識(tick 表 snap、漲跌停域、判定率門檻、CDP 避讓佈局、近全軸 1365 格),沒有任何現成庫接得住 |

---

## 8. 跨檔契約影響(CLAUDE.md §4)

任何我在 §7 提的改動,只要動到 wire,都必須點名契約:

| 我的建議 | 觸及的契約 | 兩邊要怎麼同動 |
|---|---|---|
| **T0-2**(book 併進 coalesce) | 無既有 §4 契約直接涵蓋 book 節奏,但**會改變 `snapshot.seq` 與 book 的相對時序**。CLAUDE.md §4「快照與打包的 seq 對齊 = 同一個 race 的兩道閘」的推理前提是「book 即時、ticks 打包」;book 也進打包後,`useStockStream` 的 `pendingBookRef`(F-2 交錯緩衝)語意要重新確認 | 後端 `stock_engine._flush_ticks` 若改成同時帶 book,前端 `case "ticks"` 要多解一格;或另開 `_flush_book` 保持訊息型別不變(**推薦後者,零前端契約變動**) |
| **T0-3**(watchlist_quote 打包) | 這是**新增一個 wire 型別**。沿 CLAUDE.md §4「個股逐筆 = `ticks` 打包訊息,單筆 `tick` 型別已退役」的既有前例:item 欄位逐字同名、無 `type`,前端 `default` 分支對舊型別靜默丟棄 | 後端 `stock_engine._flush_watchlist_loop` 組一則 `{"type":"watchlist_quotes","items":[…]}`;前端 `useStockStream` 加 `case "watchlist_quotes"` 一次 `setWatchlist(prev => ({...prev, ...batch}))`。**必須前後端同版部署**(同 §4「政策列形狀」那條的紀律)。舊 `watchlist_quote` 單則路徑要保留一段時間(`_handle_no_data` / trial 翻轉補推是逐碼直發的,見 `stock_engine.py:1798` `_trial_flip_targets`) |
| **T1-3**(accum/watchlist 移出 App) | 不動 wire,但動 `StockStreamState` 這個前端內部介面 —— `StockPage` / `RightRail` / `GroupGridView` 全部吃它 | 純前端重構,`npm test` 的 156 個測試檔是主要成本 |
| **T1-5 / T1-6**(增量化) | `mergeLiveMinuteBars` 觸及 CLAUDE.md §4「個股頁即時末根的分鐘鍵 = accum 起點分 +1、上限 13:30」;`futuresBarsToAccum` 觸及「台指期疊線的分鐘鍵 = 期指 1K 終點標記 −1 分」 | **兩條都是純函式內部的算式,增量化不改算式就不動契約**;但 `lib/live-last-bar.test.ts` 案 1/2/9 與 `lib/txf-overlay-series.test.ts` 是守門,改完必須全綠 |
| **T0-1**(React Compiler) | 不動任何契約,但會改變 `useMemo` / `memo` 的實際行為 | 現有的 render 計次測試(`App.memo.test.tsx`、`WatchlistSidebar.dragrender.test.tsx`)是最好的安全網 —— compiler 只會讓計次**變少**,變多就是 bug |
| **T2-1**(虛擬化) | `WATCHLIST_LIMIT = 150` 那條契約的「效能預算註解」(CLAUDE.md §4 第二類讀者)會整段失效 | 虛擬化後上限可以放寬,那幾處「以檔數 × 單價推理」的註解要重寫 |

---

## 9. 量測方法(先量再改)

| # | 要證明什麼 | 怎麼量 |
|---|---|---|
| **M1** | **book 訊息的真實頻率**(全篇最關鍵的未知數) | 開盤時在 DevTools Console 跑:<br>`let n=0; const ws=[...performance.getEntriesByType('resource')]; ` 不行 —— WS frame 不進 resource timing。<br>改法 (a):DevTools → Network → 該 `/ws/stock` 連線 → Messages 分頁,直接數 10 秒內 `"type":"book"` 的則數。<br>改法 (b):在 `ws-reconnect.ts` 的 `onmessage` 加一個 **dev-only** 計數器,每 5 s `console.table` 各 type 的則數。**這是最省事的,而且順便量到 U2/U3/U4** |
| **M2** | 多則 WS frame 是否被 React 批次 | DevTools Performance 錄 5 秒開盤 → 看 `Event: message` task 與 `commit` 的一對一關係。若 N 個 message 對應 N 個 commit,就是沒批次 |
| **M3** | 單次 App render 的真實耗時 | production build(`npm run build && npm run preview`)+ DevTools Performance,錄 10 秒,看 **Main 軌的 Long Task 數量**與 `Scripting` 佔比。目標:Long Task(>50 ms)應為 0 |
| **M4** | 哪些元件在燒時間 | dev build + React DevTools Profiler 的 **Ranked** 檢視,錄 3 秒。⚠ dev build 有 StrictMode double-invoke,絕對數字失真,**只看排名不看絕對值** |
| **M5** | 隱藏 tab 到底跑不跑 | 在 `TxoPage` / `IndexPage` / `FuturesChart` 的 render body 各加一行 dev-only `console.count`,停在個股 tab 觀察 10 秒。**這一條 5 分鐘就能做完,而且直接證實或推翻本篇最大的 finding** |
| **M6** | `aggregateBars` 的實機成本 | `StockChart` 的 `bars` useMemo 內包 `performance.now()` 差值,dev-only,切到 5 分 K 觀察 p50/p95。memory 有一筆「prod bench p95 6.6 ms」可對照 |
| **M7** | ref churn 的成本 | `LadderView` 改穩定 ref 前後各錄一次 Performance,比 `Recalculate Style` + `Scripting` |
| **M8** | 改造後的驗收 | 開盤 09:00–09:05 錄一次 Performance:<br>① Long Task 數 = 0<br>② 主執行緒 idle > 50 %<br>③ 滑鼠在分時圖上畫圈,十字線與游標的視覺延遲 < 1 frame |

**建議順序:M5(5 分鐘,定調)→ M1(定量最大未知)→ M3(建立 baseline)→ 做 T0-2/T0-3 → M3 再測。**

---

## 10. 不要動的地方

| 區塊 | 為什麼不要動 |
|---|---|
| **`ChartStatic` / `EnergySub` / `GroupCard` 三個 memo 邊界與它們周圍的 `EMPTY_*` 模組常數** | 已經是正確解,而且註解寫清楚了失效樣態。React Compiler 裝上去之後這些可以**逐步**移除,但不要在裝之前手動拆 |
| **`stock-intraday-svg.ts` 的幾何演算法** | 271 格的迴圈不是瓶頸,而裡面全是台股領域知識(tick 表 snap、漲跌停域、判定率 75 % 門檻、CDP 避讓佈局)。換圖表庫會直接損失這些 |
| **`useEffect` 紀律 / adjust-state-during-render pattern** | §4.1,全庫最乾淨的部分 |
| **`TickRow.n` 這條 key 契約** | CLAUDE.md §4 的「seq 兩口徑」是為了 React key 穩定性專門設計的後端契約,拆了就回到「tbody 整片重掛」 |
| **`tick-stream.ts` 的 module bus** | 這是唯一做對的解耦,應該**擴大**而不是收回 |
| **`setHover` 的 bail-out / `setDrag` 的 same-reference return** | `StockIntradayChart.tsx:1333`、`WatchlistSidebar.tsx:~360`,都有機械閘測試守著 |
| **`dev-perf-guard.ts`** | 它修的是症狀,但症狀是真的、修法是對的。根因修好之後也不必拆(dev-only,零 prod 成本) |
| **`useContainerSize` 的 1px 去抖 + 0×0 保留舊值** | 兩個都是踩過坑寫出來的 |
| **`aggregateLots` / `positionRows` 的「不包 memo」決定** | `PriceLadder.tsx:244` 註解說「量級小先不包,長大再對齊」—— 判斷正確,散戶單日數十筆 fills。**但如果 T1-3 沒做,它跟著 30–70 Hz 跑,那時再回來看** |
| **手刻 SVG 改 Canvas** | §7.3 T2-2:代價遠大於收益,memo 已經擋住那一層 |

---

## 11. 附:最該先做的三件事(如果只有一天)

1. **M5**(5 分鐘)—— 在四個隱藏 tab 的 render body 加 `console.count`,證實「隱藏 tab 照跑」。
2. **T0-3**(後端 ~10 行)—— `watchlist_quote` 一秒一批打包。這一條單獨就砍掉約一半的 App render。
3. **T0-1**(設定檔 2 行 + healthcheck)—— 裝 React Compiler。

這三件做完再量 M3,再決定要不要進 Tier 1。
