# F1-stream-hotpath —— 前端即時資料流熱路徑(WS → state → render)架構掃描

分析對象:`C:/side-project/copycat/frontend/src`
掃描日期:2026-09-13 / 分支 master(caca1d30)
方法:指定檔案整檔閱讀 + 後端產生點對照 + **實機微量測**(esbuild 直接 bundle repo 原始碼跑 node,
未改動 repo 任何檔案;bench 檔在 scratchpad)。

---

## 0. 一句話結論

> **這一條路徑的瓶頸不在「算得慢」,而在「每一則 WS 訊息都把整棵 React 樹推一次」。**
> `applyTick`(19 µs)與 `buildIntradayGeometry`(126 µs)本身都不算慢;
> 慢的是**它們被觸發的次數 = WS 訊息則數**,而後端目前把側欄報價拆成 **每檔一則**
> (滿自選 150 檔 = **150 則/秒**),外加期貨 per-product 0.1 s flush(~30 則/秒)。
> App 是五條流的共同持有者且**沒有 memo 邊界保護**,所以這 ~190 則/秒每一則都會
> 重跑 `App` → `StockPage` → `WatchlistSidebar`(150 列)+ `GroupGridView`(150 張卡的 memo 比對)。
>
> 要改造成「量化交易等級」的前端,**第一優先是把 React state 從 tick 通道上拿掉**
> (外部 store + `useSyncExternalStore` 細粒度訂閱 + rAF 合流),
> **第二優先是把後端的 per-item 廣播改成 per-window 打包**(逐筆已經做了,側欄報價與期貨還沒)。
> 換數值套件(numpy 之於前端 = typed array / wasm)在這一區**不是重點**,別浪費在那裡。

---

## 1. 架構地圖

### 1.1 連線層

8 條 WebSocket,全部走同一支骨架 `lib/ws-reconnect.ts::connectWithRetry`:

| hook | endpoint | 掛載點 | 後端節奏 |
|---|---|---|---|
| `useStockStream` | `/ws/stock` | **App(恆掛,deps `[]`)** | `ticks` 0.1 s 打包 / `book` 逐則 / `watchlist_quote` **1 s × 每檔一則** / `status` / `signal` |
| `useFuturesStream` | `/ws/futures` | **App(恆掛)** | per-product coalesce **0.1 s,每商品一則** |
| `useIndexStream` | `/ws/index` | **App(恆掛)** | 1 s throttle |
| `useBreadth` | `/ws/breadth` | App(恆掛) | 低頻 |
| `useCapitalStream` | `/ws/capital` | App(恆掛) | 事件驅動 |
| `useTxoSnapshot` | `/ws/txo-pnl` | App(TxoPage 恆掛) | 全量快照 |
| `useCorrelation` | `/ws/corr` | CorrPage | — |
| `useRiver` | `/ws/river` | CorrPage | — |

`connectWithRetry` 每條連線一個 `setInterval(tick, 5000)` watchdog(`ws-reconnect.ts:188`),
`onmessage` 只寫 `lastMsgAt` 時間戳(`:202`)—— 這一點設計正確,**逐筆洪流下零 timer churn**,
不是問題。

### 1.2 資料流(個股逐筆,最熱的一條)

```
後端 stock_engine._handle_quote
  └ _pending_ticks.append(...)             每筆成交
  └ call_later(0.1, _flush_ticks)          首筆到貨才排
        └ _publish({"type":"ticks","items":[...]})   一則 = 一個 0.1 s 窗
              └ WsBroadcaster.publish → per-client asyncio.Queue(maxsize 1000)
                    └ relay → ws.send_json                     ← 一則 = 一個 WS frame
瀏覽器
  ws.onmessage  (ws-reconnect.ts:201)
     JSON.parse
     → useStockStream.handle   case "ticks"  (useStockStream.ts:356-394)
         ├ seqsByCode(items)                       ← Map<string,Set<number>> 每則重建
         ├ for item of items:
         │     item.code === 主圖?  applyTick(acc, item)   ← **每 item 一次全量 immutable 複製**
         ├ setAccum(acc)                            ← 整則只 commit 一次 ✅
         └ emitTicks(items)  → tick-stream EventTarget
                └ useGroupLiveAccums 的唯一訂閱者 (useGroupLiveAccums.ts:144)
                      ├ seqsByCode(items)           ← **同一份 items 第二次建**
                      ├ per-code applyTick          ← 每 item 一次全量 immutable 複製
                      └ overlay(next) → setLive     ← 整則只 commit 一次 ✅
```

**打包→單次 commit 這一段是對的**(#180/#185 的設計),問題在 `applyTick` 是 per-item 的
immutable 全量複製,一則含 N 筆就丟掉 N−1 份中間物。

### 1.3 render 扇出

```
App (五條流的 setState 都落在這裡)
├ nav / IndexBar / CalendarBadges / VersionDriftBadge
├ TxoPage                     ← 恆掛(hidden),每次 App render 都跑
├ StockPage (lazy, 非 memo)   ← 每次 App render 都跑
│   ├ WatchlistSidebar (867 LOC, **非 memo**)   → 150 列
│   ├ GroupGridView (**非 memo**)                → 150 × <GroupCard memo>
│   │      └ GroupCard(memo)→ CardIntradayChart → IntradayChartCore
│   │             ├ buildIntradayGeometry  (useMemo, deps accum.minutes…)
│   │             ├ ChartStatic(memo)      ~130 節點
│   │             └ EnergySub(memo)        **最多 270 個 <rect>**
│   ├ StockChart → IntradayChartCore(主圖,同上但 900×420)
│   ├ OrderBook / TickTape(最多 200 列)
├ FuturesPage (**全樹無 memo**) → FuturesLadder(數百列)
├ IndexPage / CorrPage
└ RightRail(memo,ctx = stockCtx / futuresCtx)
      └ PriceLadder(~120–400 列閃電梯)
```

**關鍵事實:`App` 本身沒有任何上游 memo 邊界。** 五條流的任一則訊息 → `App` 重新執行整個
函式本體 + 重建整棵 element tree(`TxoPage`、`StockPage`、`FuturesPage`、`IndexPage` 全部,
因為 tab 是 `hidden` 保留而不是 unmount)。memo 只擋得住 `RightRail`、`GroupCard`、
`ChartStatic`、`EnergySub` 這四層以下。

---

## 2. 熱路徑逐條(含實測)

### 量測方法
把 repo 原始碼以 esbuild bundle 成 ESM 後在 node v24(V8,與 Chrome 同引擎)跑,
資料規模取「全日 271 分鐘 × 40 筆/分 ≈ 10,840 筆成交」的合成 accum。
輸出:

```
accum: minutes=271  vp=124  ticks=200
buildIntradayGeometry 主圖 900x420 (271 分鐘): 126.27 µs
buildIntradayGeometry 卡片 220x80  (271 分鐘): 116.46 µs
buildIntradayGeometry 卡片          (30 分鐘):  12.68 µs
buildEnergyBars 主圖:                            19.53 µs
sideSummary 主圖(每 render 未 memo):             2.46 µs
buildVpBars 主圖(vp 124 檔位):                  11.02 µs
applyTick 滿載(真實 applyTick):                 18.92 µs
```

補充合成 bench(只複刻配置形狀,vp 放大到 900 檔位 = 低價股 autofit 的實際上界):

```
滿載(271 分鐘 / 900 檔位 / 200 tape): 38.8 µs/tick
群組卡片(271 / 900 / 0 tape):        44.4 µs/tick
早盤(60 / 100 / 0 tape):              6.6 µs/tick
```

### HP-1 `applyTick`(`lib/stock-accum.ts:425-469`)—— 每 tick,全市場 ~數百次/秒

```ts
export function applyTick(acc: StockAccum, msg: StockTickItem): StockAccum {
  const minutes = new Map(acc.minutes);        // ← 複製最多 271 entries
  ...
  const ticks = [
    ...acc.ticks,
    { ... n: msg.seq },
  ].slice(-TAPE_MAX);                          // ← 200 元素陣列複製兩次(spread + slice)
  const vp = new Map(acc.vp);                  // ← 複製 124~900 entries
  foldVp(vp, msg.t, msg.p, msg.q, msg.side);
  return { ...acc, seq, last: {...}, vwap, minutes, ticks, vp, ... };
}
```

- 頻率:主圖 = 該檔成交率(2330 開盤可達 20–50 筆/秒);群組檢視 = **檢視集合全部檔的成交率總和**
  (150 檔的族群,開盤瞬間數百到上千筆/秒是常態)。
- 實測 18.9 µs(vp 124)/ 38.8 µs(vp 900)。500 tick/s → 9.5–22 ms/s;
  2000 tick/s(開盤爆量)→ 38–88 ms/s,**單靠這一支就吃掉 4–9% 主執行緒**,
  而且是純配置 → GC 壓力(每 tick 產生 1 個 Map(271)+1 個 Map(900)+2 個 Array(200)+1 個物件)。
- **浪費點**:一則 0.1 s 打包內同檔有 N 筆時,產生 N 份完整 accum,只有第 N 份會被讀。

### HP-2 `seqsByCode`(`lib/stock-accum.ts:391-402`)—— 每則打包 **×2**

`useStockStream.ts:369` 建一次,`useGroupLiveAccums.ts:148` 對**同一份 items** 再建一次。
一則 300 筆的打包 = 600 次 Set.add + 兩個 Map。10 則/秒 → 6000 次/秒。量級小,但是純重複。

### HP-3 `buildIntradayGeometry`(`lib/stock-intraday-svg.ts:343-522`)—— 每個「這一窗有成交的」圖表,每 0.1 s

deps 是 `accum.minutes`(`StockIntradayChart.tsx:1077`),而 `applyTick` **每 tick 換一個新 Map**
→ 該檔只要有成交,幾何就整份重算。內容:

- `windowedEntries`:`[...minutes.entries()]` 複製 + `.filter` + `.sort`(271 筆)
- `prices = entries.map(...).filter(...)`
- `priceLine = entries.map(...)`(271 點)
- `vwapLine` 迴圈(271 點,再建 271 個物件)
- `energyFrom`:`Math.max(1, ...entries.map(...))`(**spread 271 個引數進 Math.max**)+ 271 bars
- `haveMinutes = new Set(entries.map(...))`
- `areaPolygon`:273 次 `toFixed(1)` + `join(" ")`(字串)
- `markFor` × 2:`entries.find(...)` 線性掃

實測 **126 µs(主圖)/ 116 µs(卡片)**。注意卡片只有 220×80 卻幾乎一樣貴 —— 成本在
**分鐘數**不在畫布尺寸,所以「卡片圖比較小所以比較便宜」的直覺是錯的。

### HP-4 `EnergySub` 的 270 個 `<rect>`(`StockIntradayChart.tsx:818, 882`)

```tsx
{bars.map((b) => (
  <rect key={...} x={...} y={...} width={...} height={b.h} ... />
))}
```
檔頭自承:「真正安全的是 EnergySub 改單一 `<path>`(節點數 1140 → 1),留 next-time」
(`:817`)。個股態是 271 根,期貨近全時段是 1140 根。
只要 `accum.minutes` 換 identity 就整批重建 → **每張有成交的卡每 0.1 s 重建 271 個 SVG 節點**。

### HP-5 `watchlist_quote` per-code 廣播 → App 全樹重繪(**最嚴重**)

後端 `copycat/server/stock_engine.py:1827-1832`:
```python
dirty, self._dirty_watchlist = self._dirty_watchlist, set()
for code in dirty:
    state = self._states.get(code)
    if state is None or state.last is None:
        continue
    self._publish(self._quote_payload(code))   # ← 每檔一則,一則一個 WS frame
```
`_throttle = 1.0`(`:248`),自選上限 150(CLAUDE.md §4「自選上限常數多邊同值」)。
盤中活躍時段 dirty 幾乎 = 全部 → **150 則/秒**。

前端 `hooks/useStockStream.ts:425`:
```ts
setWatchlist((prev) => ({ ...prev, [msg.code as string]: q }));
```
每則複製一個 150 鍵物件,並讓 `watchlist` 換 identity → `App` 重繪 →
`StockPage` 重繪 → `WatchlistSidebar`(150 列,**非 memo**)+ `GroupGridView`(**非 memo**,
重建 150 個 `<GroupCard>` element 做 memo 比對)。

**量級**:150 則/秒 × (150 鍵物件複製 + 150 列 + 150 卡 element 建立 + 150 次 memo 比對)
≈ 每秒 6.75 萬次 element 建立 / 屬性複製,**而畫面上只有 150 個數字在變**。

### HP-6 `futures` per-product 0.1 s flush → App 全樹重繪

`copycat/server/futures_engine.py:669-687` 對每個 dirty product 各 `_broadcast(...)` 一則。
3 商品(TXF/MXF/TMF)× 10 Hz = **30 則/秒**,每則:
```ts
// useFuturesStream.ts:33
next: { seq: msg.seq, products: { ...prev.products, [msg.product]: msg.state } }
```
→ `setState` → App 全樹重繪 **30 次/秒**,即使使用者停在個股 tab。
App 註解已經意識到右欄的部分(`App.tsx:246-252` 拆 `futuresCtx` / `stockCtx`),
但**擋不住 App 自己那一輪**。

### HP-7 `stockCtx` 的 deps 過寬 → 閃電梯每 tick 重繪

`App.tsx:256-270`:
```ts
const stockCtx = useMemo<RailContext>(() => ({ ..., book: accum?.book ?? null, last: accum?.last ?? null, ... }),
  [stockCode, stkfutContract, accum]);   // ← 整個 accum
```
`accum` 每則 ticks 打包換 identity(即使 `book` 沒變),→ `RightRail` 的 memo 每 0.1 s 被打穿
→ `PriceLadder` 重繪(閃電梯 rows 是 `[lower, upper]` 全域合法 tick:600 元股 ≈ 120 列,
10 元股 ≈ 200 列,低價股 tick 0.01 可近千列 —— `lib/stock-tick.ts:144` 的 `for (let p = upperBound; p >= lowerBound; p = stepDown(p))`)。
`accum.last` 也是**每 tick 新物件**(`stock-accum.ts:458`),所以連改成 `accum?.book, accum?.last`
也救不到,得降到 primitive(`accum?.last?.p`)。

### HP-8 `merged` 的 150 鍵 spread(`useGroupLiveAccums.ts:78-81, 103-107`)

```ts
const merged = useMemo(() => (live.base === seeded ? { ...seeded, ...live.map } : seeded), [seeded, live]);
...
mergedRef.current = { ...mergedRef.current, ...next };
setLive((prev) => ({ base: seededRef.current, map: prev.base === seededRef.current ? { ...prev.map, ...next } : { ...next } }));
```
每則打包做 3 次 150 鍵 object spread。10 則/秒 → 4500 次屬性複製/秒。量級不大,
但它同時讓 `merged` 換 identity → `GroupGridView` 重繪 → 150 個 element 重建。

### HP-9 未 memo 的 per-render 計算(小)

- `StockIntradayChart.tsx:1207` `sideSummary(accum.minutes, xw)` —— 2.46 µs,每 render 一次。
  hover mousemove 也會跑。小,但每一張卡都有一份。
- `GroupGridView.tsx:354` `ymdOf(new Date())` 每 render 一次(刻意,見註解)。
- `App.tsx:117` `purgeOrphanKeys()` 在 module 層,只跑一次 —— 沒問題。

---

## 3. 「一則 WS 訊息觸發幾次 re-render」逐條回答

| 訊息 | 頻率 | setState 次數 | React commit | 實際重繪範圍 |
|---|---|---|---|---|
| `ticks`(打包) | 10/s | 1(`setAccum`)+ 1(`setLive`,經 bus) | 1–2 | App 全樹 + 該窗有成交的每一張卡的圖 |
| `book` | 逐則(活躍股數次/秒) | 1(`setAccum`) | 1 | App 全樹 + 閃電梯 + OrderBook |
| `watchlist_quote` | **150/s** | 1(`setWatchlist`)(+ 主圖檔另 1) | 1 | **App 全樹 + 側欄 150 列 + 圖牆 150 卡比對** |
| `futures` | **30/s** | 1(`setState`) | 1 | App 全樹(+ 期貨 tab 時右欄閃電梯) |
| `index` | ~1–2/s | 3–4 個 `commitRef`(同一 callback,批次合併) | 1 | App 全樹 |
| `signal` | 事件 | bus → `useSignalAlerts` | 1 | App 全樹 |
| `status` | 低頻 | 1 | 1 | App 全樹 |

**合計盤中穩態約 190–200 次 App 全樹重繪/秒。**

### React 19 automatic batching 在 WS callback 裡有沒有生效?

**同一則訊息內的多個 setState:會合併**(React 18 起 automatic batching 涵蓋所有 context,
含 native event handler / promise / timeout)。所以 `case "ticks"` 裡的 `setAccum` 與
bus 扇出的 `setLive` 落在同一個 `message` event → 合併成一次 commit。

**跨訊息:不保證。** 每個 WS frame 是獨立 task;React 的 default lane 透過 Scheduler
(MessageChannel macrotask)排程,**若多則 frame 在 scheduler callback 跑之前連續到達,
會合併;若瀏覽器在兩則 frame 之間插入 scheduler task,就各自 commit 一次**。
瀏覽器 task source 的交錯順序不是規範保證的 → **這一點只能量測不能推論**。
本報告的 190/s 是「最壞且合理」的上界;實測值需要用 React Profiler 的 commit 計數確認(見 §7)。

**這正是要改掉的原因**:效能不該取決於瀏覽器 task 交錯的運氣。
用 rAF 主動合流之後,commit 次數變成**確定的 ≤ 60/s**。

---

## 4. `tick-stream.ts` 的扇出真相(題目假設需要修正)

題目問「50 張卡各訂閱一次 → 一則訊息扇出 50 次 callback」。
**實際不是這樣,而且現況是對的**:

`lib/tick-stream.ts:55` 的 `subscribeTicks` 在整個 repo 只有**一個訂閱者**
(`useGroupLiveAccums.ts:144`,由 `GroupGridView` 掛一份)。
卡片不自己訂閱 —— 圖牆層一份 hook 算完整份 `AccumMap` 再往下傳,
`GroupCard` 以 `memo` 擋住沒動的卡(`GroupGridView.tsx:132`)。
`EventTarget` 每則打包只 dispatch 一次 `CustomEvent`。

**所以 pub/sub 本身不是問題,不要動它。**
要動的是「訂閱者收到之後仍然走 React state」這一段(見 §6 的 R1)。

---

## 5. 60 s 群組輪詢 × WS 逐筆的互動

`useGroupSnapshots.ts:119-137` 每 60 s 打一次 `/api/stock/group-state?codes=...`(150 檔 batch)。
落地 → `snapshots` 換 identity → `useGroupLiveAccums` 的 `seeded` useMemo 重算
(150 次 `accumFromGroupSnapshot`,每次含 `extendMinutes` 的 `new Map(minutes)`)→
`live.base !== seeded` → 整層 live 作廢 → `merged = seeded` → **整牆 150 張卡全部重畫**。

- 頻率:60 s 一次。**這不是效能問題**(每分鐘一次 150 × ~120 µs ≈ 18 ms 的尖峰,可接受)。
- 但它有一個**正確性尾巴**:重播種丟掉 live 層之後,下一則打包靠 `isSeededDuplicate`
  (`stock-accum.ts:417`)接住重複。這段已經在 pr-187/188 review 收過,現況正確。
- **值得記的一點**:重播種造成的整牆重畫尖峰,與下面 R1 的改造互斥 ——
  如果 accum 搬到外部 store,重播種也只需要 diff 出「真的變了的檔」再通知,尖峰自然消失。

---

## 6. Findings(改造建議,依影響排序)

> 每條都標:熱路徑?量級?會不會動到 CLAUDE.md §4 的跨檔契約?

---

### F1-01 【critical】`watchlist_quote` 每檔一則 → App 全樹 150 次/秒重繪

**位置**:`copycat/server/stock_engine.py:1827-1832`(產生點) + `frontend/src/hooks/useStockStream.ts:413-464`(讀者)

**證據**:見 §2 HP-5。

**影響**:盤中穩態 150 次/秒的 App 全樹重繪,每次重建 `WatchlistSidebar` 150 列 +
`GroupGridView` 150 個 `GroupCard` element(即使 memo 攔下,element 建立與 props 比對仍要跑)。
**這是這一區最大的一筆浪費,而且完全可以消掉** —— 資料本來就是 1 s 節流合併過的,
只是「合併」停在後端資料層、沒有延伸到 wire 層。

**改法(兩段,可分開做)**:
1. 後端把迴圈收成一則打包 —— 沿用 `ticks` 打包已經證明過的形狀:
   ```python
   items = [self._quote_payload(c) for c in dirty if ...]
   if items:
       self._publish({"type": "watchlist_quotes", "items": items})
   ```
2. 前端 `case "watchlist_quotes"` 一次 `setWatchlist` 套用整批:
   ```ts
   setWatchlist((prev) => { const next = { ...prev }; for (const q of items) next[q.code] = toQuote(q); return next; });
   ```
   **舊 `watchlist_quote` 分支必須保留**(`_handle_no_data` / trial 翻轉補推是單則路徑,
   `stock_engine.py:1355`、`:1802`),不是取代是新增。

**風險 / 契約**:
- 這是**新增一個 wire 訊息型別**,屬 CLAUDE.md §4 的跨檔契約新增(additive):
  後端加、前端加 `case`,舊前端遇到新型別走 `default: return` 靜默丟棄 →
  **部署必須前後端同版**(與 §4「政策列形狀」那條的部署紀律同一條:畫面「版本落差」膠囊亮起先 build)。
- 失效樣態:前端忘了加 case → 側欄整排停在 `-`,零錯誤訊號。要加 parity 測試
  (後端 `test_stock_engine.py` 斷言打包形狀;前端 `useStockStream.test.ts` 斷言一則多檔)。
- 不動 `WATCHLIST_LIMIT` 契約、不動 `seq` 兩口徑契約。

**effort**:M

---

### F1-02 【critical】App 是五條流的共同 setState 落點,且沒有 memo 邊界

**位置**:`frontend/src/App.tsx:154-183`

**證據**:
```ts
const { twse, otc, txf, tradeDate, wsStatus: indexWs } = useIndexStream();
const breadth = useBreadth();
useCapitalStream();
const alerts = useSignalAlerts();
const stockStream = useStockStream(...);
const futuresStream = useFuturesStream();
```
`App.tsx:172-177` 的註解已經自承這件事並判定「可接受」:
> 「且 watchlist_quote 的 setState 現在落在 App 層 → 每秒一批側欄報價會重繪整棵樹。
> 判定可接受:…(b) App 層本來就會因 useIndexStream 每則指數推播重繪,不是新增的重繪類別。
> **若日後量測到掉幀**,先做的是讓 useStockStream 吃 `enabled` 參數」

**「日後」就是現在**:當初的估算是「每秒一批」,實際是「每秒 150 則」。
前提錯了,結論要重算。

**影響**:190–200 次/秒的 App 全樹 element 重建。含 `TxoPage`(恆掛)、
`StockPage`、`FuturesPage`、`IndexPage` 四棵 hidden 但仍 render 的子樹。

**改法**:把「高頻純量」從 React state 移到外部 store,元件以 selector 訂閱。
本 repo **已有四處 `useSyncExternalStore` 先例**(`hooks/useCapital.ts:81`、
`hooks/useChartToggles.ts:137`、`hooks/useSignalSound.ts:43`、`lib/fee-discount.ts:68`),
所以這不是引進新範式,是把既有範式用到熱路徑上。

最小可行版本(不換套件、不加相依):
```ts
// lib/quote-store.ts  —— module 級,不進 React
let quotes: Record<string, WatchlistQuote> = {};
const subs = new Map<string, Set<() => void>>();   // per-code 訂閱
let version = 0;
export function applyQuotes(items: WireQuote[]): void { /* 就地寫 + 只通知變動的 code */ }
export function useQuote(code: string): WatchlistQuote | undefined {
  return useSyncExternalStore(
    (cb) => subscribeCode(code, cb),
    () => quotes[code],
  );
}
```
`WatchlistRow` / `GroupCard` 各自 `useQuote(code)` → **一檔報價變只重繪那一列 / 那一張卡**,
App 完全不動。

**風險 / 契約**:
- 不動任何 §4 契約(純前端內部結構)。
- 最大的風險是「兩份真相」:必須讓 store 成為**唯一**持有者,
  `useStockStream` 回傳的 `watchlist` 欄位要一起退役,否則就是 §4 那種「兩邊各漂各的」失效樣態。
- 既有測試 `App.memo.test.tsx`(計次 + 內容斷言)是這次改造的護欄,要沿用並加嚴。

**effort**:L

---

### F1-03 【high】`applyTick` per-item 全量複製 → 一則打包丟掉 N−1 份中間物

**位置**:`frontend/src/lib/stock-accum.ts:425-469`;呼叫點
`hooks/useStockStream.ts:385`、`hooks/useGroupLiveAccums.ts:163`、`:123`

**證據**:見 §2 HP-1,實測 18.9–38.8 µs/tick。

**改法**:加一支 `applyTicks(acc, items)`(**保留 `applyTick` 供既有測試與單筆路徑**),
內部只複製一次 `minutes` / `vp` / `ticks`,再就地折 N 筆:
```ts
export function applyTicks(acc: StockAccum, items: readonly StockTickItem[]): StockAccum {
  if (items.length === 0) return acc;
  if (items.length === 1) return applyTick(acc, items[0]!);      // 單筆走原路,語意逐字不變
  const minutes = new Map(acc.minutes);
  const vp = new Map(acc.vp);
  const ticks = acc.ticks.slice(Math.max(0, acc.ticks.length + items.length - TAPE_MAX));
  ... // 迴圈就地寫 minutes / vp / ticks,最後一次性組出新 accum
}
```
一則含 30 筆 → 複製成本從 30× 降到 1×,**節省 ~97%**。

**風險 / 契約**:
- `seq` / `n`(React key)語意必須逐字不變 —— CLAUDE.md §4「個股 `seq` 的兩個口徑」。
  尤其 `ticks` 的 `n = msg.seq` 與 `fromSnapshot` 的回推必須落在同一把尺上。
- `vwap` 的 rounding 順序:現況每筆都 `Math.round(amountMilli / volume)`,
  批次版只在最後 round 一次 → **中間值不同但終值相同**(`amountMilli` / `volume` 都是整數累加)。
  這點要寫成 characterization 測試釘住,否則是「兩個數字都看起來對」的靜默漂移。
- `MinuteAgg.h/l` 的 `unknown` 分支(`:432`)在批次內要逐筆重判,不能提到迴圈外。
- 呼叫端的跳號 / pending 分岔邏輯不可合併 —— 只有「連續的一段」才能批次套用。

**effort**:M

---

### F1-04 【high】幾何 / SVG 每 0.1 s 全量重建,沒有「這一格才變」的增量路徑

**位置**:`frontend/src/components/stock/StockIntradayChart.tsx:1066-1078`(geometry useMemo)、
`:882`(270 個 `<rect>`)、`lib/stock-intraday-svg.ts:343`

**證據**:實測 116–126 µs/次;`StockIntradayChart.tsx:817` 的檔頭註解已自承
「真正安全的是 EnergySub 改單一 `<path>`(節點數 1140 → 1),留 next-time」。

**量級**:150 檔族群全在檢視集合內時,0.1 s 窗內幾乎每一檔都有成交 →
**1500 次幾何重建/秒 × 116 µs ≈ 174 ms/s**,再加 1500 次卡片 subtree 的 React 協調
(每卡 ~400 個 SVG 節點)。**這已經超過單一主執行緒的預算**,開盤瞬間會直接掉幀。

**改法(三段,由便宜到貴)**:
1. **EnergySub 改單一 `<path>`**(已在 next-time):270 個 `<rect>` → 1 個 `d` 字串。
   同理 `vpBars`(124 rect)。這一段是純渲染層,零語意風險,**先做這個**。
2. **幾何增量化**:`buildIntradayGeometry` 的 `entries`/`priceLine`/`vwapLine`/`energyBars`
   對「只有最後一分鐘變了」的情況是可增量的。實作方式是讓 accum 帶一個
   `lastChangedMinute`,幾何 memo 用「上一份幾何 + 變動分鐘」走快路徑。
   `windowedEntries` 的 `sort` 也可以省掉 —— `minutes` 的 key 天然單調(除了回補),
   維護一個已排序的 `number[]` 就不必每次 271 筆排序。
3. **rAF 合流**(見 F1-05):把「每 0.1 s 一次」壓成「每幀最多一次」,
   在 100 ms 窗小於一幀時無效,但在 burst(多則堆積)時有效。

**風險 / 契約**:
- **`overlay_parity.json` / `sweep_cluster_golden.json` 那一類 golden fixture 不碰**
  (幾何不在 §4 契約內,CDP/MA 的前後端同式是另一支 `lib/futures-overlay.ts`)。
- 幾何的**輸出值**必須逐字不變 —— `stock-intraday-svg` 有大量「等值反查」邏輯
  (`markFor` 的 `m.h === target`,`:497`),增量化時如果浮點/整數路徑變了,
  症狀是**標記靜默消失**。既有 `StockIntradayChart.test.tsx`(2304 LOC)是護欄。
- `areaPolygon` 的 `toFixed(1)` 精度與 `lib/svg-points.ts::pts()` 必須一致(`:480` 明記)。

**effort**:L(第 1 段是 S)

---

### F1-05 【high】沒有 rAF 節流:render 次數由 WS 到貨節奏決定,不由畫面刷新率決定

**位置**:整條路徑;最直接的插入點是 `hooks/useStockStream.ts:388-391` 與
`hooks/useGroupLiveAccums.ts:165`

**證據**:
```ts
if (touched && acc !== null) {
  accumRef.current = acc;
  setAccum(acc);          // ← 每則打包直接 commit
}
```
沒有任何 `requestAnimationFrame` / `startTransition` / 手動合流
(全 repo 只有 `FuturesLadder.tsx:333` 與 `LadderView.tsx:162` 兩處 rAF,都是捲動定位用)。

**影響**:後端節奏(0.1 s 打包 / 1 s 報價 / 0.1 s 期貨)直接變成 React commit 節奏。
Burst 時(TC4 補推、回補落地、重連後對齊)多則訊息連續到達,**每則各 commit 一次**,
而畫面根本來不及顯示。

**改法**:在 store 寫入與 React 通知之間插一層 rAF 合流:
```ts
let dirty = false;
function notify(): void {
  if (dirty) return;
  dirty = true;
  requestAnimationFrame(() => { dirty = false; flushSubscribers(); });
}
```
配合 F1-02 的外部 store,commit 次數變成**確定的 ≤ 60/s 且與後端節奏解耦**。

**風險**:
- **閃電梯(真錢那一側)不可以延遲**。`PriceLadder` / `OrderBook` 的更新如果被 rAF 押後
  最多 16 ms,理論上可接受(人眼與滑鼠反應都遠大於此),但這是 user 要拍板的事,
  不可由實作者自行決定 —— 列入停等問題。
- 測試層:既有 hook 測試大量用 `act()` 同步斷言,rAF 會讓它們全部要改成 `await` 一幀。
  這是**最大的隱性成本**(156 個前端測試檔),要先評估影響面。

**effort**:L

---

### F1-06 【high】群組卡片維護一份永遠不會被顯示的 200 筆 `ticks` 陣列

**位置**:`lib/stock-accum.ts:445-449`(產生)+ `lib/stock-accum.ts:375`(`accumFromGroupSnapshot` 給 `ticks: []`)

**證據**:群組卡片的 accum 由 `accumFromGroupSnapshot` 播種(`ticks: []`),
之後每筆 tick 由 `applyTick` **append 並 slice 到 200**。
但 `CardIntradayChart` → `IntradayChartCore` **從不讀 `accum.ticks`** ——
逐筆明細 `TickTape` 只掛在單檔頁(`StockPage.tsx:521`)。

**影響**:150 張卡 × 每 tick 2 次 200 元素陣列複製 = **純浪費**。
以 500 tick/s 估:500 × 400 = 20 萬次元素複製/秒,零畫面價值。

**改法**:`applyTick` / `applyTicks` 加一個 `keepTape: boolean` 參數(群組路徑傳 false),
或更乾淨:讓 `StockAccum.ticks` 在群組 accum 恆為同一個凍結空陣列。

**風險**:
- `ticks` 為空時 `TickTape` 的空態文案分支會被觸發 —— 但群組卡片不渲染 TickTape,無影響。
- `tapeOmitted` 旗標的語意(CLAUDE.md §4「`tape=0` 字面值 + `tape_omitted`」)**不受影響**:
  那是後端省略的宣告,這裡是前端不維護,兩件事。**但別把兩者混用**
  —— 把群組 accum 的 `tapeOmitted` 改成 true 會讓未來若有人在卡片上加明細時印錯的空態文案。

**effort**:S

---

### F1-07 【high】期貨 per-product 0.1 s flush 讓 App 每秒重繪 30 次(且與畫面無關)

**位置**:`copycat/server/futures_engine.py:669-687`(產生)+ `frontend/src/hooks/useFuturesStream.ts:26-36, 96-100`

**證據**:見 §2 HP-6。`App.tsx:246-252` 的註解已經處理了右欄那一半
(拆 `futuresCtx` / `stockCtx`),但 App 本身那一輪擋不住。

**改法**:
- 後端把 `_flush` 的迴圈收成一則 `{"type":"futures","seq":n,"products":{...}}`(同 F1-01 的形狀),
  **或**
- 前端把 `futuresStream.state` 搬進外部 store(F1-02 的同一套機制),App 不持有。

後者風險小很多(不動 wire),優先。

**風險 / 契約**:
- 動 wire 的話 `seq` 語意要重新定義(現況 `seq` 是**廣播游標**不是內容版本,
  `futures_engine.py:335` 明記)—— `applyFuturesMsg` 的 `msg.seq !== prev.seq + 1` 判跳號
  邏輯會跟著變。這條**不建議動 wire**,走前端 store 就好。

**effort**:M

---

### F1-08 【medium】`stockCtx` / `futuresCtx` 的 deps 過寬,打穿 `RightRail` memo

**位置**:`frontend/src/App.tsx:256-276`

**證據**:見 §2 HP-7。`deps: [stockCode, stkfutContract, accum]`,而 `accum` 每 tick 換 identity。

**改法**:降到 primitive + 真正會變的物件:
```ts
const bookRef = accum?.book ?? null;          // 只在 book 訊息變
const lastP = accum?.last?.p ?? null;         // primitive
const lastT = accum?.last?.t ?? null;
const metaRef = accum?.meta ?? null;
const stockCtx = useMemo(() => ({ kind: "stock", code: stockCode, contract: stkfutContract,
  name: metaRef?.name ?? "", book: bookRef, last: lastP === null ? null : { p: lastP, t: lastT ?? "", cum_vol: 0 }, meta: metaRef }),
  [stockCode, stkfutContract, metaRef, bookRef, lastP, lastT]);
```
**但 `last.cum_vol` 如果有讀者就不能這樣偽造** —— 要先 grep `RightRail` 底下對 `ctx.last` 的用法。

**風險**:
- `App.tsx:253-255` 明記「deps 完整性**沒有 lint 守**,守門是 `App.memo.test.tsx` 的計次 + 內容斷言」。
  改 deps 一定要同時加 case:「book 沒變、只有 tick 變 → RightRail 不重繪」。
- 失效樣態:右欄掛著舊五檔 / 舊成交價(真錢面板),畫面零訊號。**這是高風險改動**,
  必須有紅先行測試。

**effort**:S

---

### F1-09 【medium】`seqsByCode` 對同一份 items 建兩次

**位置**:`hooks/useStockStream.ts:369` 與 `hooks/useGroupLiveAccums.ts:148`

**改法**:`emitTicks(items, seqs)` 把已算好的 Map 一起傳過去。
或更好:後端在打包時直接帶 per-code 的 seq 範圍(但那是動 wire,不划算)。

**風險**:`tick-stream.ts` 的 `emitTicks` 簽名改 → 測試 `useStockStream.test.ts`「ticks 打包」節要跟。
語意不變(同一份資料換個傳法)。

**effort**:S

---

### F1-10 【medium】`WatchlistSidebar` / `GroupGridView` / `StockPage` / `FuturesPage` 皆非 memo

**位置**:`components/stock/WatchlistSidebar.tsx`(867 LOC)、`components/stock/GroupGridView.tsx:296`、
`components/stock/StockPage.tsx`、`components/futures/FuturesPage.tsx`

**證據**:全 repo 只有 6 個 `memo(`:`RiverCards`、`RightRail`、`CandleChart::ChartStatic`、
`GroupCard`、`StockIntradayChart::ChartStatic`、`StockIntradayChart::EnergySub`。

**影響**:App 的每一輪都穿透到這四棵樹的 render 函式本體。
`FuturesPage` 尤其嚴重:它底下的 `FuturesLadder` 有數百列且無 memo,
而使用者停在個股 tab 時它仍然 `hidden` 掛著、仍然每輪 render。

**改法**:
- 短期:對這四個加 `memo` + 把 props 收成穩定 identity。
- 但**這是治標**:props 裡有 `quotes`(每秒換 150 次 identity)、`stream`(每 tick 換)
  的話 memo 一樣穿透。**真正的解是 F1-02**(store + selector),memo 才有意義。

**風險**:加 memo 本身零行為風險,但要小心 `StockPage` 的 `onViewChange` 等 inline handler
會打穿 memo(`GroupGridView.tsx:332-341` 已用 latest-ref 處理過同款問題,可沿用該 pattern)。

**effort**:M

---

### F1-11 【medium】hidden tab 的整棵子樹仍然參與每一輪 render

**位置**:`App.tsx:334-438`(四個 `hidden={tab !== ...}` 的 tabpanel)

**證據**:`hidden` 是 CSS 層的隱藏,React 照樣 render + 協調整棵子樹。
`TxoPage`(`App.tsx:341`)甚至沒有 `visited` 閘門,恆掛。

**改法**:
- 對「非當前 tab」的 panel 內容包一層 `{tab === id ? <Page/> : null}` 會 unmount(丟狀態,不行);
- 正解是讓每個 Page 自己 memo 且 props 在非當前 tab 時 identity 凍結
  (現況 `active={tab === "futures"}` 已經是這個思路的一半 —— 它擋輪詢,但沒擋 render)。
- 或用 `<Activity mode="hidden">`(React 19.2+ 的 Offscreen 正式版)—— **需要確認本專案的
  React 19 版本是否已含**(package.json 是 `^19.0.0`,實際裝的版本要查 lock)。

**effort**:M

---

### F1-12 【low】`merged` / `mergedRef` 的 150 鍵三重 spread

**位置**:`hooks/useGroupLiveAccums.ts:78-81, 103-107`

見 §2 HP-8。量級小(4500 次屬性複製/秒),但在 F1-02 的 store 改造裡會自然消失
(store 就地寫、per-code 通知,不需要重建整張 map)。**不值得單獨做。**

**effort**:S(但建議併入 F1-02)

---

### F1-13 【low】`sideSummary` 每 render 未 memo

**位置**:`components/stock/StockIntradayChart.tsx:1207`

實測 2.46 µs。150 張卡 × 每 render → 0.37 ms/輪。小,但 hover 時每個 mousemove 也跑。
**併入 F1-04 一起處理即可,不單獨做。**

---

### F1-14 【low】`Math.max(1, ...entries.map(...))` 的 spread(271 個引數)

**位置**:`lib/stock-intraday-svg.ts:322`
```ts
const maxTotal = Math.max(1, ...entries.map(([, m]) => m.o + m.i + m.u));
```
以及 `:382-383`:
```ts
const hi = Math.max(ref, ...prices, ...(...));
const lo = Math.min(ref, ...prices, ...(...));
```
271 個引數的 spread 在 V8 上會走慢路徑(超過內聯上限),且 `prices` 陣列被建了又丟。
改成迴圈掃描。**已含在 F1-04 的量測裡(126 µs),不是獨立的一筆。**

---

## 7. 量測方法(要證明快 / 慢,怎麼量)

### 7.1 「一則訊息幾次 commit」—— React Profiler commit 計數

prod build 下 Profiler 被剝掉,所以量測要用 **`npm run dev` + React DevTools Profiler**,
但 dev build 本身有 props-diff 開銷(CLAUDE.md §1 已記)。做法:

```
1. frontend/ 起 `npm run dev`
2. Chrome DevTools → Performance → 錄 10 秒盤中
3. 看 "Timings" 軌:React 的 commit 標記數 ÷ 秒數 = 實際 commit 率
4. 同時用 chrome-devtools MCP 的 performance_start_trace / performance_analyze_insight
```
**判準**:改造前預期 150–200 commit/s;改造後應 ≤ 60/s(rAF 上限)。

### 7.2 「哪一支函式吃掉主執行緒」—— 已有可重複的離線 bench

本次用的腳本在 scratchpad,可以留成常設工具:
```bash
cd C:/side-project/copycat/frontend
./node_modules/.bin/esbuild <bench>.ts --bundle --platform=node --format=esm \
  --alias:@=./src --outfile=<out>.mjs && node <out>.mjs
```
**這是這個 codebase 最有價值的量測基建** —— 不需要起 server、不需要 TC4、
不改 repo,就能對純函式(`applyTick` / `buildIntradayGeometry` / `buildVpBars` /
`buildLadder`)做 before/after 對照。建議固化成 `frontend/bench/`(但這屬於本次 scope 外)。

### 7.3 「WS 到貨節奏」—— 不靠猜

```
# 後端側:看實際一秒幾則
grep -c '"type": "watchlist_quote"' <ws 錄製>
# 或在 relay 加臨時計數(不建議動 prod)
```
更安全:瀏覽器 DevTools → Network → WS → Messages,選 10 秒區間數則數。
**這是 F1-01 的 150 則/秒這個數字唯一該被驗證的地方**(我從 code 推導出來,
實際 dirty 集合大小取決於當下有多少檔在成交,盤後會遠低於 150)。

### 7.4 「圖牆到底掉不掉幀」—— 已有先例

memory 記錄 09-03 的 #187 真環境驗證做過「trace 93 s >50ms=0」。
沿用同一套:Performance trace + long task 統計。
**判準**:開盤 09:00–09:05、150 檔群組檢視、long task(>50 ms)為 0。

### 7.5 記憶體 / GC

`applyTick` 是配置大戶。用 DevTools → Memory → Allocation instrumentation on timeline,
錄 30 秒,看 Map / Array 的配置速率。改造後應下降一個量級。

---

## 8. 工具選型建議與取捨

| 候選 | 用在哪 | 解決什麼 | 代價 | 結論 |
|---|---|---|---|---|
| **`useSyncExternalStore` + 自寫 module store** | `lib/quote-store.ts` / `lib/accum-store.ts` 新檔 | F1-02 / F1-12 的根;per-code 訂閱,App 完全退出熱路徑 | 零新相依;**repo 已有四處先例**;要重寫 hook 契約與相關測試 | **建議導入**(第一優先) |
| **`requestAnimationFrame` 合流** | store 的 notify 層 | F1-05;commit 率與後端節奏解耦 | 零相依;**測試要全面改成 await 一幀**(156 個測試檔的影響面要先評);閃電梯延遲 ≤16 ms 要 user 拍板 | **有條件導入**(先評測試影響 + 拍板) |
| **React Compiler(`babel-plugin-react-compiler`)** | `vite.config.ts` 的 `@vitejs/plugin-react` | 自動 memo;本 repo 有大量「**必經呼叫端 useMemo**」的人工契約(`StockIntradayChart.tsx:197/209/216/234/239` 等),正是 compiler 要消滅的那類 | devDep 一個;需要 code 符合 Rules of React —— 本 repo 有多處刻意的 render 期 ref 寫入(`useStockStream.ts:180/182/198`,已被 doctor 標 needs-human),**compiler 可能會拒編或行為改變** | **有條件導入**:先在 `frontend/` 跑 `react-compiler-healthcheck` 看違規數,再決定。收益大但風險實在 |
| **`@preact/signals-react`** | 取代 store | 細粒度到「一個數字一個訂閱」 | 新 runtime 相依 + 它要 patch React 內部(`signals-react-transform`);與 React 19 / TanStack Query 的相容性要驗;**與本 repo「零 runtime 相依除 4 個」的取向衝突** | **不建議**:`useSyncExternalStore` 已經能拿到 90% 的收益且零相依 |
| **`zustand` / `valtio`** | 同上 | 現成 store + selector | 一個小相依(~1 KB);API 熟悉度高 | **有條件**:如果自寫 store 的樣板變多再引。目前 store 需求很窄(per-code selector + rAF notify),自寫 ~80 行就夠,**先不引** |
| **Web Worker 做 accum** | `applyTick` / `buildIntradayGeometry` 搬進 worker | 把 20–170 ms/s 的計算移出主執行緒 | 每幀要把幾何結果 postMessage 回來(structured clone 271 點 × 150 卡 = 反而更貴);**除非改用 SharedArrayBuffer + typed array,否則序列化成本吃掉收益** | **不建議**(除非走下一列) |
| **typed array 幾何 + `SharedArrayBuffer`** | `minutes` / `vp` 改成 `Float64Array` / `Int32Array` 環形緩衝,worker 直接寫,主執行緒直接讀 | 徹底消滅 immutable 複製與序列化;這才是「量化等級」的做法 | **需要 COOP/COEP header**(vite dev + preview 都要設);`StockAccum` 是 §4 契約的消費端形狀,改型別影響面極大(`stock-accum.ts` 477 LOC + 全部幾何 + 156 個測試檔) | **不建議現在做**。列為「F1-02~F1-05 做完後仍不夠快」才啟動的第二階段 |
| **Canvas / OffscreenCanvas 取代 SVG** | `EnergySub`(270 rect)、`vpBars`(124 rect)、priceLine | 節點數 400 → 0,協調成本歸零 | 失去 SVG 的 hover 命中測試(現況 `minuteOf` 是純數學反演,其實**不依賴 DOM 命中**,所以可行性比想像高);失去 CSS class 主題(`stroke-accent` 等 Tailwind token 要改成讀 CSS 變數);測試從 DOM 斷言改成 canvas mock(**156 個測試檔裡 `StockIntradayChart.test.tsx` 2304 LOC 幾乎全是 DOM 斷言**) | **有條件導入**:先做 F1-04 第 1 段(rect → 單一 `<path>`),量測後若仍不夠再考慮 canvas。**測試改寫成本是主要阻力** |
| **虛擬化(`@tanstack/react-virtual`)** | `WatchlistSidebar` 150 列 / `PriceLadder` 120–400 列 / `TickTape` 200 列 / `FuturesLadder` 數百列 | 只渲染可視區的 ~20 列 | 一個小相依(TanStack 家族,已有 react-query);閃電梯**必須能捲到任意價位**,虛擬化與「固定界錨定」(`stock-tick.ts:120` buildLadder 的 design v2 R5)相容,但捲動定位邏輯(`LadderView.tsx:162` 的 rAF scrollIntoView)要改 | **建議導入**,但**在 F1-02 之後**:先讓這些列不要每秒重繪 150 次,再談少渲染幾列 |
| **binary wire(msgpack / protobuf)** | 取代 JSON | 降 parse 成本 | 兩邊都要引 codec;後端 stdlib-only 哲學要破例 | **不建議**:實測 parse 不是瓶頸(小物件 × 200/s),**打包(F1-01/F1-07)才是**。先打包,量測後若 parse 仍上榜再說 |
| **`ws` 訊息 worker parse** | WS 在 worker 裡收 + parse | 主執行緒不做 parse | 同 Worker 的序列化問題 | **不建議** |

---

## 9. 不要動的地方(反向結論)

1. **`lib/tick-stream.ts` 的 EventTarget pub/sub —— 不要動。**
   只有一個訂閱者,一則打包 dispatch 一次。題目假設的「50 張卡各訂閱一次 → 扇出 50 次」
   **在這個 codebase 不成立**。改成別的 bus 只是換個寫法,零收益。

2. **`lib/ws-reconnect.ts` 的退避 / watchdog / 心跳過濾 —— 不要動。**
   `onmessage` 只寫時間戳(`:202`),單一 `setInterval` 巡檢(`:188`),
   檔頭明記「個股 tick 洪流下零 timer churn」。這是正確的設計。
   `WS_SILENCE_TIMEOUT_MS` 是 §4 心跳契約的一半,動它要同動後端 `WS_HEARTBEAT_SECS`。

3. **0.1 s tick 打包本身(#180)—— 不要動。**
   後端 flush 與前端「整則只 commit 一次」都已經做對了。
   問題不在打包,在打包**之後**的 per-item `applyTick` 與 App 層 setState。

4. **`seq` 跳號 / `isSeededDuplicate` / pending buffer 的時序保護 —— 不要碰。**
   `stock-accum.ts:404-423` 的 docstring 記了整套推導,pr-187/188 review 收過兩輪。
   任何效能改造都必須**原封保留**這一段(CLAUDE.md §4「快照與打包的 seq 對齊 = 同一個 race 的兩道閘」)。

5. **60 s 群組輪詢 —— 不要改頻率。**
   每分鐘一次 18 ms 尖峰,佔比 0.03%。`groupPollInterval`(`useGroupSnapshots.ts:111`)
   的盤外「距開點 ms」寫法是 next-time L71 的收修,不要退回 `false`。

6. **`accumFromGroupSnapshot` 的「缺鍵一律降級成不可得」紀律 —— 不要為了省計算而近似。**
   `stock-accum.ts:330-343` 的 docstring 講得很清楚:前端自己折一份 VWAP/VP 出來
   會與單檔頁對不上,而兩個數字都看起來對。效能改造不得越過這條線。

7. **`fromSnapshot` 的 VP fold 走全量 ticks(`:243-247`)—— 不要改成只折 200 筆。**
   那是每次 refetch 一次(不在熱路徑),而截斷會讓 POC 錯。

8. **後端 `WsBroadcaster` 的「滿了丟最舊保最新」政策 —— 不要動。**
   `ws.py:65-90`。前端有 seq 跳號自癒,政策正確。
   丟包可觀測性(`dropped` / `window_dropped`)是 #182 加的,保留。

---

## 10. 硬約束(CLAUDE.md §4 跨檔契約 × 本區改動)

本區任何改動會踩到的契約,逐條點名:

| 契約 | 本區哪個改動會碰 | 兩邊要怎麼同動 |
|---|---|---|
| **個股 `seq` 的兩個口徑**(`snapshot.seq` = ticks 尾筆 / `tick.seq` 每筆 +1) | F1-03 `applyTicks` 批次版的 `n` 指派 | 產生點仍是後端 `stock_state.py::ingest`/`snapshot()`;前端 `fromSnapshot` 回推與 `applyTicks` 取 `msg.seq` 必須落在同一把尺。漂掉 = tbody 靜默整片重掛 |
| **快照與打包的 seq 對齊(兩道閘)** | F1-03 / F1-05(rAF 押後會改變「重複在播種前還是播種後被消化」) | 後端 `_flush_ticks()` 先於快照、前端 `isSeededDuplicate` 兩半都要在。**rAF 押後前端這半的時機,要重新推導 race**,不能只靠現有測試 |
| **`ticks` 打包契約**(`{type:"ticks",items:[{code,t,p,q,side,b,a,h,l,seq}]}`) | F1-09(`emitTicks` 帶 seqs)不動 wire;F1-01 新增 `watchlist_quotes` 是**另一個**型別 | 新增型別 = additive,但舊前端 `default: return` 靜默丟棄 → **部署必須前後端同版** |
| **`/ws/stock` 入站 `view` 訊息** | 不動。但 F1-02 若把 store 搬走,`getTickView()` / `subscribeTickView` 的 onopen 重送邏輯必須原樣保留 | 前端忘了 onopen 重送 → 圖牆只剩 60 s 輪詢、逐筆靜默消失 |
| **WS 心跳契約**(`WS_HEARTBEAT_SECS` 10 s ↔ `WS_SILENCE_TIMEOUT_MS` 30 s) | 不動(明列於 §9) | — |
| **`tape=0` 字面值 + `tape_omitted`** | F1-06 的「群組不維護 ticks」**不可以**改用 `tapeOmitted` 表達 | 兩件事:一個是後端省略的宣告,一個是前端不維護 |
| **自選上限常數多邊同值(150)** | F1-01 的打包大小、F1-02 的 store 容量都以它為預算 | 註解裡以「上限表述」引用(2026-09-02 已改寫),改值時最壞值跟著變,量測判準要重算 |
| **「盤前篩選」群組名前後端同字面** | F1-02 的 store 若要按群組分片訂閱會碰到 | 過濾鍵仍走 `lib/constants.ts::SCREEN_GROUP_NAME` |
| **訊號列 `notify` 欄 / 政策列形狀** | 不碰(訊號是低頻路徑) | — |
| **個股頁即時末根分鐘鍵 = accum 起點分 +1、上限 13:30** | F1-03 的 `minuteKey` 語意不可變 | `lib/live-last-bar.ts` 是另一個讀者,accum 的 `minutes` key 語意改了它就整條右移一格 |
| **日 K 定稿界 14:00 前後端同值** | 不碰 | — |

---

## 11. 建議的執行順序(給後續 /perf 或 /refactor 用)

```
批 1(低風險、可獨立量測、S–M):
  F1-06  群組 accum 不維護 ticks               [S]  → applyTick 成本降 ~30%
  F1-09  seqsByCode 只算一次                    [S]
  F1-04 第 1 段  EnergySub/vpBars → 單一 <path> [S]  → 每卡 SVG 節點 400 → ~130
  F1-14  Math.max spread → 迴圈                 [S]  (併入上一條一起量)
  → 量測點:離線 bench(§7.2)before/after;圖牆 trace long task

批 2(最大收益,L):
  F1-01  watchlist_quotes 打包(前後端同版部署)  [M]  → App 重繪 150/s → 1/s
  F1-07  期貨 state 搬外部 store                 [M]  → App 重繪 30/s → 0
  F1-02  quote/accum 外部 store + per-code 訂閱  [L]  → App 徹底退出熱路徑
  F1-10  四個大元件加 memo(F1-02 之後才有意義)  [M]
  → 量測點:React commit 計數(§7.1),目標 190/s → <10/s

批 3(需 user 拍板 / 影響測試面):
  F1-05  rAF 合流                               [L]  ← 閃電梯延遲要拍板 + 156 測試檔影響面
  F1-03  applyTicks 批次                        [M]  ← vwap rounding 順序要 characterization
  F1-08  stockCtx deps 收窄                     [S]  ← 高風險(真錢面板),要紅先行
  F1-04 第 2 段  幾何增量化                      [L]  ← 等值反查的精度風險

批 4(前三批做完仍不夠快才啟動):
  虛擬化(側欄 / 閃電梯 / TickTape)
  React Compiler(先 healthcheck)
  Canvas 取代 SVG
  typed array + SharedArrayBuffer + Worker
```

---

## 12. 待回答的問題(查不出來 / 需 user 拍板 / 需真環境量測)

1. **盤中實際的 `watchlist_quote` 則數**是多少?150 是「dirty = 全部自選」的上界,
   實際取決於同時有成交的檔數。要用 DevTools Network WS 面板量 10 秒。
2. **閃電梯(真錢)可不可以接受 rAF 的 ≤16 ms 延遲?** 這是 user 拍板題,不是實作題。
3. **rAF 合流對 156 個前端測試檔的影響面**有多大?要先跑一次「把 notify 包 rAF」的 spike
   看有多少測試轉紅,再決定 F1-05 的 effort。
4. **裝的 React 到底是 19.x 的哪一版?** `package.json` 是 `^19.0.0`,
   `<Activity>` 要 19.2+;要查 `package-lock.json`。
5. **React Compiler healthcheck 的違規數**:本 repo 有多處刻意的 render 期 ref 寫入
   (`useStockStream.ts:180/182/198` — 2026-08-11 doctor triage 已列 needs-human),
   compiler 會不會拒編要實測。
6. **`RightRail` 底下對 `ctx.last.cum_vol` / `ctx.last.t` 有沒有讀者?**
   F1-08 的收窄要先確認,否則會偽造欄位。
7. **群組檢視 150 檔時,一個 0.1 s 窗內實際有幾檔有成交?**
   決定 F1-04 的 174 ms/s 估算是不是真的(我是用「幾乎全部」估的上界)。
   要用後端 `_pending_ticks` 的長度分布量。
8. **prod build(`npm run preview`,4173)下的實際 commit 率**:
   dev build 有 props-diff 開銷(CLAUDE.md §1 已記),量測要在 prod build 做,
   但 prod build 沒有 Profiler → 要用 `performance.measure` 自建探針(可掛在 `dev-perf-guard` 的既有基建上)。
