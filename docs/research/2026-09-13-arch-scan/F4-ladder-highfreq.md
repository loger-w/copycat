# F4 — 前端:閃電梯 / 五檔 / 逐筆等高頻更新元件

> 掃描範圍:`frontend/src/components/{stock,futures,ladder,quote,capital}/*` 的下單與報價面元件
> + `frontend/src/lib/{ladder-*,futures-ladder,flash-*,qty-quick,trade-kinds,close-order,oi-levels,fill-marks,position-summary}.ts`
> + `frontend/src/hooks/{useFlashArm,useCapital}.ts`,並往上追到觸發它們重繪的
> `hooks/useStockStream.ts` / `lib/stock-accum.ts` / `components/rail/RightRail.tsx` / `App.tsx`,
> 往後端追到 `copycat/server/stock_engine.py`(推播頻率)。
> 本報告只讀不改;所有量測皆為 Node 端微量測(標注「實測」)或原始碼推導(標注「推導」/「推測」)。

---

## 0. 一句話結論

**閃電梯本身的演算法不慢(131 列上限、純整數運算),慢的是「它每秒被整棵重建幾十次」。**
根因有二:(a) 後端 `book`(五檔)WS 訊息**零 coalesce、零內容去重**,主圖每收一則 TC4 REALTIME
就發一則;(b) 前端把整顆 `accum` 當成 `useMemo`/props 的單一 dep,任何欄位動一下,
`RightRail → PriceLadder → LadderView` 的 ~130 列 × ~7 個 DOM 節點全部重建、
ref 全部 detach/attach、780 次 `twMerge`。

而「下單按鈕反應延遲」的機制**不在 click handler 裡**(已查證:handler 同步段只有幾個
比較 + `Date.now()`,`fetch()` 在同一個 microtask 就發出去,TanStack 的 re-render 通知走
`setTimeout(0)` macrotask、排在 fetch 之後)。延遲來自**主執行緒被上面那些 render 佔滿**,
click 事件排在 long task 後面。所以「讓梯不要每則重繪」= 「讓下單鍵變快」,是同一件事。

---

## 1. 架構地圖

### 1.1 三座梯的血統

```
                    ┌──────────────────────────────────────────┐
                    │ components/ladder/ArmRow.tsx (89 行)      │  武裝列唯一畫法
                    │  ⚠ outerHTML 逐字 characterization 鎖住   │  (三梯共用)
                    └──────────────────────────────────────────┘
                                    ▲            ▲
       ┌────────────────────────────┘            └──────────────┐
       │                                                         │
┌──────┴───────────────────────────────┐          ┌──────────────┴─────────────┐
│ components/stock/LadderView.tsx (396)│          │ futures/FuturesLadder.tsx  │
│  presentation:標題列 / 武裝列 / 數量  │          │  (551) 自帶一份完整 JSX     │
│  快捷 / 檔位列 / 市價列 / 部位標記     │          │  幾何 = FUT_TICK 1 點固定   │
│  幾何 = lib/stock-tick::buildLadder   │          │  = lib/futures-ladder      │
└──────▲─────────────────▲──────────────┘          └────────────────────────────┘
       │                 │
┌──────┴───────┐  ┌──────┴─────────────┐
│ PriceLadder  │  │ StkfutLadder (376) │   container:送單 hook / 武裝 reducer /
│  (497) 現股   │  │  個股期            │   折數 / 部位口徑 / 防抖 / hint
└──────────────┘  └────────────────────┘
```

- 兩座「股票血統」的梯(現股 `PriceLadder`、個股期 `StkfutLadder`)共用 `LadderView` 做
  presentation,幾何都走 `lib/stock-tick.ts::buildLadder`(台股 tick 表,毫元整數)。
- 期貨梯 `FuturesLadder` **不共用 `LadderView`**,只共用 `ArmRow` 與 `MarketOrderButtons`,
  幾何走 `lib/futures-ladder.ts::buildFuturesLadder`(固定 1 點 = 1000 毫點)。
- 三梯的送單尾段共用 `lib/flash-send.ts::settleFlashSend`,武裝狀態機共用
  `lib/flash-arm.ts::reduceArm`(state 由 `RightRail` 的 `useFlashArm` 持有)。

### 1.2 兩種幾何 = 兩種完全不同的重繪特性(關鍵差異)

| | 現股 / 個股期(`buildLadder`) | 期貨(`buildFuturesLadder`) |
|---|---|---|
| 錨定 | **固定界**:rows = [跌停, 漲停] 全域合法 tick | **跟隨 center**:上下各 60 檔 |
| 列數 | 49–150(依價格帶,見 §2.1 實測) | 121(60+1+60),漲跌停夾界時更少 |
| center 移動時 | rows **集合不變**,只有 `isCenter` / `dimmed` 翻轉 → React key 全部命中 | rows 整窗平移 → 頭尾各換一個 key,中間 119 個命中 |
| React 重排成本 | 低(keyed diff 全命中) | 低(一進一出) |
| 但兩者共同點 | **每次 render 都重建全部列的 vdom**,因為沒有列級 memo | 同左 |

這一點很重要:**列數不多、key 也穩,所以虛擬化(react-window / TanStack Virtual)不是答案**
(見 §6「不要動的地方」)。真正要省的是「重建 vdom + commit 階段的 ref/attr 工作」。

### 1.3 資料流(現股頁,最熱的一條)

```
TC4 (ZMQ, Windows 桌面)
   │  REALTIME quote(每筆成交 + 每次簿變動各一則)
   ▼
copycat/server/stock_engine.py::_handle_quote
   ├─ tick  → _pending_ticks[] ──(call_later 0.1 s)──► WS {"type":"ticks", items:[…]}   ← 有 coalesce
   ├─ book  → 【立即】self._publish({"type":"book", …})                                  ← ✗ 零 coalesce
   └─ watchlist_quote → _dirty_watchlist ──(1 s 節流 loop)──► WS                          ← 有節流
   ▼  /ws/stock
frontend hooks/useStockStream.ts::handle
   ├─ case "ticks": 逐 item applyTick(acc, item)  → setAccum(acc)   (整則 1 次 commit)
   ├─ case "book" : {...acc, book}                → setAccum(next)  (每則 1 次 commit)  ← 熱點
   └─ case "watchlist_quote": setWatchlist(...)  (+ 條件性 setAccum)
   ▼  accum: StockAccum
App.tsx
   ├─ stockCtx = useMemo(..., [stockCode, stkfutContract, accum])   ← dep 是整顆 accum
   ▼
RightRail (memo)  ← memo 的比較 prop 就是 stockCtx,accum 一動就全破
   ▼
PriceLadder (無 memo)
   ├─ aggregateLots(orders, code, ymdWindow(new Date(),[0]), "股", fills)  ← 每 render 掃全帳戶
   ├─ positionRows(secPositionsOf(positions, code), last.p, discount)      ← 每 render
   ├─ markMap ×2                                                           ← 每 render
   ├─ useFeeDiscountField() → useSyncExternalStore(getSnapshot = localStorage.getItem)
   └─ buildLadder({center: last.p, ref, upper, lower, book})               ← 每 render 造 ~130 物件
   ▼
LadderView (無 memo,列也無 memo)
   └─ rows.map(...)  × ~130
         ├─ cn() × 6            → twMerge(clsx(...))
         ├─ ref={(el)=>{...}}   → inline 箭頭,identity 每 render 變 → commit 階段全列 detach+attach
         ├─ markTitle: 3 個暫時陣列
         └─ ~7 個 DOM 元素

同一則 accum 也同時打到:StockPage 的 StockChart(SVG)、OrderBook(10 格)、TickTape(30 列)
```

### 1.4 逐筆匯流排(群組卡片,與梯同一則訊息)

`useStockStream` 的 `case "ticks"` 尾端 `emitTicks(items)` 把**整則原序**丟給
`lib/tick-stream.ts` 匯流排,`useGroupLiveAccums` 在那頭替 50 張卡各自 `applyTick`
(詳見 F5 區塊)。本報告只提醒一件事:**`applyTick` 的每筆成本(§3.5 實測 41 µs)
在群組檢視下會乘以「命中的卡片數」**,所以那一支的最佳化收益不只在單檔頁。

---

## 2. 熱路徑逐條(附量級)

### 2.1 P0 — `LadderView` 檔位列 map(每則 book / 每則 ticks)

**位置**:`frontend/src/components/stock/LadderView.tsx:256-376`

```tsx
{rows.map((r) => {
  const buyLot = buyLots?.get(r.priceMilli);
  ...
  const markTitle = [ ... ].filter((s) => s !== null).join("、");
  return (
    <div key={r.priceMilli} data-price={r.priceMilli} title={...}
      ref={(el) => {                                   // ← 每 render 新 identity
        if (el) rowRefs.current.set(r.priceMilli, el);
        else rowRefs.current.delete(r.priceMilli);
        if (r.isCenter && el) centerRef.current = el;
      }}
      className={cn("relative grid h-6 grid-cols-[1fr_64px_1fr] …", r.isCenter && "bg-bg-deep",
        r.dimmed ? "border-line/20" : "border-line/50")}>
```

**列數(實測,以 `buildLadder` 原始算式在 Node 重跑)**:

| 參考價 | 列數 | | 參考價 | 列數 |
|---|---|---|---|---|
| 9.9 元 | 127 | | 105 元 | 87 |
| 15 元 | 61 | | 180 元 | 73 |
| 25 元 | 101 | | 330 元 | 133 |
| 49.9 元 | **150** | | 520 元 | 137 |
| 52 元 | 137 | | 990 元 | 127 |
| 99 元 | 127 | | 1200 元 | 49 |

→ 典型 100–150 列,最壞 150(49.9 元附近)。每列最少 7 個 DOM 元素(row div、買側 div、
買鈕、價格 span、賣側 div、賣鈕 + 可選的 be/avg 標記 span 與紅方格 button)。
**每次 render ≈ 900–1050 個 React element 重建 + 同量的 props diff。**

**每則變幾列?**(這是題目問的核心)
- `book` 訊息:五檔最多變 10 列的 `bidQty`/`askQty`(通常只變 1–4 列)。
- `ticks` 訊息:`last.p` 變 → `isCenter` 從 A 列搬到 B 列(2 列),`dimmed` 邊界動 0–2 列。
- 合計**真正變的列 ≈ 1–12 列 / 130 列 ≈ 1–9%**。
- React 實際重繪:**130 列全部**(沒有列級 memo)。

**成本實測**(Node,tailwind-merge LRU 已 warm):

```
cn x 780 per render (130 列 × 6 次), 1000 renders: 101.5 ms  →  101.5 µs/render
```

`cn` 只是其中一項。加上 130 次 `Map.get` ×3、130 個 markTitle 的 3 個暫存陣列、
~1000 個 `createElement`、以及 commit 階段 130 × 2 次 ref 回呼 —— 推導總計
**每則 render 的 JS 側 ≈ 1–3 ms**(Chrome、prod build;需以 §7 的量測計畫驗證),
再加上瀏覽器的 style recalc / layout(130 列 grid,無 `contain`)。

---

### 2.2 P0 — `book` 訊息的發送頻率(後端,但決定前端負載)

**位置**:`copycat/server/stock_engine.py:1359-1360`

```python
        if code == self._main:
            self._publish({"type": "book", "code": code, "bids": book.bids, "asks": book.asks})
```

- **無條件**:`parse_stock_realtime` 恆回一個 `StockBook`(`stock_models.py:197`),
  所以**每一則主圖 REALTIME quote 都會產生一則 book WS 訊息**,不論簿內容有沒有變。
- 對比同一函式裡的另外兩條:
  - tick 走 `_pending_ticks` + `call_later(self._tick_flush_secs)`(0.1 s 打包,`stock_engine.py:1340-1342`);
  - `watchlist_quote` 走 `_dirty_watchlist` + `await asyncio.sleep(self._throttle)`(≈1 s,`stock_engine.py:1816-1827`)。
  - **只有 book 沒有任何節流**。
- 註解甚至明寫過這個教訓(`stock_engine.py:1223`):「寫成無條件 discard + publish 會變成
  每 tick 廣播,直接打穿 1s 節流(W-17)」—— 那一條講的是 `watchlist_quote`,book 這條漏了。

**後果**:#180 花力氣把逐筆打包成 0.1 s 一則(「50 檔開盤每秒數百筆 → ≤ 10 則/s」),
但**同一批 quote 仍然逐則發 book**,前端的 `setAccum` 次數因此回到 tick 級。
0.1 s 打包省下的是「訊息數 + 逐筆 vdom」,沒省到「React commit 次數」。

**量級**:未實測(見 §8 open question 1)。推導上界 = 主圖那一檔的 TC4 REALTIME 推播率;
熱門股開盤數十 Hz 是合理範圍。

---

### 2.3 P1 — `stockCtx` 的 `useMemo` dep = 整顆 `accum`

**位置**:`frontend/src/App.tsx:256-270`

```tsx
const stockCtx = useMemo<RailContext>(
  () => ({ kind: "stock", code: stockCode, contract: stkfutContract,
           name: accum?.meta?.name ?? "", book: accum?.book ?? null,
           last: accum?.last ?? null, meta: accum?.meta ?? null }),
  [stockCode, stkfutContract, accum],          // ← 整顆 accum
);
```

`RightRail` 是 `memo()`(`RightRail.tsx:121`),但它唯一的 prop 就是 `stockCtx`。
`accum` 在 `ticks` / `book` / `watchlist_quote`(no_data / trial 翻轉)任一路徑都換 identity,
所以 memo 每次都破。

**具體損失**:`applyTick` 一定重建 `last`(`stock-accum.ts:applyTick` 的
`last: { p: msg.p, t: msg.t, cum_vol: … }`),即使成交價與上一筆**完全相同**。
鎖板 / 盤整時「同價連續成交」極常見 —— 這些 tick 對閃電梯的畫面是完全 no-op,
但每一筆都讓 130 列重畫一遍。

修法:`stockCtx` 的 deps 改成三個更細的來源 —— `accum?.book`(identity 只在 book 訊息換)、
`accum?.last?.p`(primitive)、`accum?.meta`(identity 只在 meta 訊息換)。
`last` 物件若下游只用 `p`,把它降成 `lastMilli: number | null` 更乾脆
(⚠ `RightRail.positionsContent` 的 `closePriceOf` 也讀 `last.p`,`StkfutLadder`/`PriceLadder`
的 `last === null` 判定是「估價缺 → 市價鈕鎖」的安全閘,改形狀要一起改,見 §5 約束)。

---

### 2.4 P1 — 列的 inline `ref` 回呼:commit 階段對 130 列全做 detach + attach

**位置**:`LadderView.tsx:277-281`

React 對 **identity 改變的 callback ref** 的處理是「以 `null` 呼叫舊的、以元素呼叫新的」。
inline 箭頭每 render 都是新 identity,所以:

- 每次 render 的 **commit 階段**(= 阻塞、不可中斷的那一段)固定付出
  `130 × 2` 次函式呼叫 + `130` 次 `Map.delete` + `130` 次 `Map.set`;
- 而 `rowRefs` 這張 Map 的**唯一用途**是 `centerRequest` effect 的
  `rowRefs.current.get(centerRequest.priceMilli)`(`LadderView.tsx:151`),
  而那是「使用者點五檔」才發生的低頻事件。

**這整張 Map 可以消掉**:列高是固定的 `h-6`(Tailwind = 1.5rem = **24 px**),
列的 index 在 `rows` 陣列裡直接可得 → 置中改成
`container.scrollTop = idx * 24 - container.clientHeight / 2`,
`centerRequest` 改成先 `rows.findIndex(r => r.priceMilli === req.priceMilli)`。

順帶解掉下一條。

---

### 2.5 P1 — 跟隨置中的 `scrollIntoView`:每次 center 價變就強制 layout

**位置**:`LadderView.tsx:158-165`(期貨梯同款 `FuturesLadder.tsx:329-336`)

```tsx
useEffect(() => {
  if (!follow || centerPrice === null) return;
  progScroll.current = true;
  centerRef.current?.scrollIntoView({ block: "center" });
  requestAnimationFrame(() => { progScroll.current = false; });
}, [follow, centerPrice]);
```

`scrollIntoView` 要先量到目標元素相對 scroll 容器的位置 → **強制同步 layout**
(130 列 grid + 每列 3 欄 + 絕對定位標記)。這發生在 passive effect 裡,也就是 paint 之後,
會造成一次額外的 layout→paint 循環。

deps 已經很省(只在 `centerPrice` **值**變才跑,`rows` identity 每 tick 變不觸發 —— 那是
既有的 R5 修正,做得對)。但快速跳動的標的一秒可以換好幾次 center 價。

改成 §2.4 的 `scrollTop` 算術後:純寫入、零 layout read、O(1)。

---

### 2.6 P2 — `applyTick` 每筆複製三份容器

**位置**:`frontend/src/lib/stock-accum.ts::applyTick`

```ts
const minutes = new Map(acc.minutes);          // 盤中最多 ~271 筆(09:00–13:30)
...
const ticks = [...acc.ticks, {...}].slice(-TAPE_MAX);   // 200 → 201 → 200,兩次陣列配置
...
const vp = new Map(acc.vp);                    // 當日成交過的檔位數;低價股可近千
foldVp(vp, msg.t, msg.p, msg.q, msg.side);
```

原始碼註解自己承認了量級:「有漲跌停時域是 [lower, upper](± 10%),autofit 的低價股
(tick 0.01 元)可以近千檔。仍遠小於每秒 tick 數的量級,Map 淺拷在這個尺度上不是熱點。」

**實測**(Node,minutes 270 / vp 600 / ticks 200):

```
applyTick-like: 41.21 µs/tick
```

問題不在單筆,在**「一則打包呼叫 N 次」**:`useStockStream.ts:385` 是
`for (const item of items) { … acc = applyTick(acc, item); }`。
開盤一則 0.1 s 打包裡含 20–50 筆很常見 → **0.8–2 ms / 打包**,全部花在複製上,
而最終只有一份 accum 會被 `setAccum`。

修法:bundle 內用可變 draft(`minutes` / `vp` / `ticks` 各複製**一次**,逐筆就地寫),
最後產一個新的 `StockAccum` 物件。對外語意不變(identity 仍每則換一次)。
⚠ 每筆的 `seq` 連續判定 / `isSeededDuplicate` 必須逐筆照跑(CLAUDE.md §4 的兩道閘)。

---

### 2.7 P2 — `PriceLadder` render body 的三段未 memo 計算

**位置**:`PriceLadder.tsx:245-263`

```tsx
const lots = aggregateLots(ordersData?.orders, code, ymdWindow(new Date(), [0]), "股", fills);
...
const posRows = positionRows(secPositionsOf(positionsData?.positions, code), last?.p ?? null, discount.value);
const beMarks = markMap(posRows, (r) => r.beTick);
const avgMarks = markMap(posRows, (r) => r.avgTick);
...
const ladder = buildLadder({ center: last?.p ?? null, ref: meta?.ref ?? null, … });
```

- `aggregateLots`(`lib/ladder-lots.ts:107-165`)先 `groupUsableFillsBySeq` 掃**全帳戶**當日 fills
  建 Map,再掃**全帳戶**當日 orders。散戶一日數十至數百筆。**它完全不吃 `last` / `book`**
  → 可以完整 `useMemo([ordersData, fills, code])`,一毛都不用每 tick 付。
  原始碼註解寫「量級小先不包,長大再對齊」—— 現在就是「長大」的時候。
- `ymdWindow(new Date(), [0])` 每 render 建一個 `Date` + 一個 `Set`。
- `positionRows` 吃 `last?.p`,必須跟著動,但它是個位數列 × 幾十次浮點運算,便宜。
- `buildLadder` 每 render 造 ~130 個新物件 + 2 個 Map;這是必要的(要餵新的 bidQty),
  但如果做了列級 memo,它產出的物件 identity 反而會變成 memo 的破口 → 列級 memo
  必須傳 primitive props,不能傳 `LadderRow` 物件。

---

### 2.8 P2 — `TickTape` 的 `useMemo` 永遠 miss

**位置**:`components/stock/TickTape.tsx:33-37`

```tsx
const [limit, setLimit] = useState(PAGE);          // PAGE = 30
const newestFirst = useMemo(() => [...ticks].reverse(), [ticks]);
const rows = newestFirst.slice(0, limit);
```

`ticks` 的 identity 在**每一筆成交**都換(`applyTick` 重建陣列),所以這個 `useMemo`
**在盤中 100% miss**,註解寫的「不必跟著每次 render 重付」只在 hover / 展開這種純 UI
state 變動時成立。實際付出的是「200 筆複製 + 200 筆反轉」,而顯示只要最後 `limit`(預設 30)筆。

改法一行:`ticks.slice(-limit).reverse()` → O(30) 而非 O(400)。

另外 `TickTape` 沒有 `memo`,而它的父 `StockPage` 在**每則 book** 都重繪
(`StockPage.tsx:519-523` 直接吃 `accum.ticks`)→ 30 列 × 5 個 `cn` = 150 次 twMerge/則,
而 book 訊息根本沒改 `ticks`。`memo(TickTape)` + `ticks` identity 未變即整支跳過,是零風險的一刀。

**做對的地方**:key 用 `t.n`(後端 seq 指派),丟頭時倖存列 key 不變 —— 這正是 N120 修過的,
不要改回索引(CLAUDE.md §4 的「個股 seq 兩口徑」契約)。

---

### 2.9 P3 — `cn()` = `twMerge(clsx(...))` 出現在每一列

`lib/utils.ts`:

```ts
export function cn(...inputs: ClassValue[]): string { return twMerge(clsx(inputs)); }
```

`tailwind-merge` 的工作是「解析 class 字串、找出同組衝突、後者勝」。它有 LRU 快取
(預設 500 筆),而梯上的 class 組合只有 4–6 種,所以**快取命中率接近 100%**,
實測 780 次只要 101 µs —— 並不是災難,但它是**純粹的浪費**:這些 class 是
開發期就知道的固定字串,執行期不可能有衝突。

熱路徑上的建議:模組層預先算好 4–6 個常數字串(`ROW_BASE_DIMMED` / `ROW_BASE_NORMAL` /
`ROW_CENTER` …),用字串串接或 `clsx` 選一個,把 `twMerge` 留給低頻元件。
(做了列級 memo 之後這條會自然消失大半,優先序因此壓在 memo 之後。)

---

### 2.10 P3 — `useFeeDiscount` 的 `getSnapshot` 每 render 讀 localStorage

`lib/fee-discount.ts:67`:

```ts
export function useFeeDiscount(): number {
  return useSyncExternalStore(subscribe, readFeeDiscount, () => FEE_DISCOUNT_DEFAULT);
}
export function readFeeDiscount(): number { return loadDiscount().value; }
export function loadDiscount(): DiscountState {
  const raw = readLocal(FEE_DISCOUNT_KEY);          // ← window.localStorage.getItem
  const value = clampDiscount(raw ?? "") ?? FEE_DISCOUNT_DEFAULT;
  return { raw: String(value), value };
}
```

`useSyncExternalStore` 會在 **render 期間**與 **passive effect 的 tearing check** 各呼叫一次
`getSnapshot`。消費者有 4 個(`PriceLadder` / `GroupGridView` / `StockPage` / `WatchlistSidebar`),
所以每一則 book 訊息 ≈ 8 次 `localStorage.getItem` + 8 次 `Number.parseFloat` + 8 次 `String()`。

`lib/storage.ts` 的註解甚至已經寫了「讀取端住在 render 路徑上,一秒可以被呼叫幾十次」。

修法:模組層快取一個 `let cached: number | null`,`persistDiscount` 與 `storage` 事件時
清掉 —— `getSnapshot` 變成讀一個 number。零行為變更(值域與通知路徑都不動)。

---

### 2.11 P3 — 期貨梯 `buildFuturesLadder` 的 `unshift`

`lib/futures-ladder.ts:193-195`:

```ts
for (let p = c + FUT_TICK_MILLI, i = 0; i < half && p <= upper; i++, p += FUT_TICK_MILLI) {
  prices.unshift(p);          // ← O(n) 搬移 × 60 次 = ~1800 次元素搬移
}
```

`half = 60` → 約 1800 次搬移,10 Hz 下 18k/s。絕對值很小(µs 級),但改成
「往後 push 再 `reverse()`」或「先算陣列長度再倒填」是零風險的免費修正。

---

### 2.12 P3 — `showHint` 造成兩次全梯重繪

`PriceLadder.tsx:265-270`:送單成功 → `setHint(text)` → 130 列重繪;
3 秒後 `setTimeout` → `setHint(null)` → 再 130 列重繪。
hint 只是武裝列底下一行 `<p>`。做了列級 memo 之後成本降到可忽略;
沒做之前,它剛好落在「使用者剛按下送單鍵」的那一刻 —— 也就是最不該卡的時刻。

---

### 2.13 已經夠快的部分(反向 finding,詳見 §6)

- `OrderBook`(273 行):**最多 10 個格子**,`limitOnly` / `bestLimit` / `marketQty` 各掃 ≤5 筆。
  每則 book 的計算量 ≈ 30 次基本運算。不要動。
- `DepthBar`(151 行,期貨頁):同上,10 格。不要動。
- `capital/CapitalOrdersList` / `CapitalPositionsList` / `CapitalConfirmDialog`:
  只在右欄「委託 / 部位」tab 掛載(`RightRail` 條件 render),資料源是 15 s / 30 s 輪詢
  + WS 事件經 200 ms trailing debounce invalidate(`useCapital.ts:120-143`)。
  完全不在 tick 路徑上。不要動。
- `QuoteTable`(226 行,TXO T 字表):資料源 `useTxoSnapshot` 的 `/ws/txo-pnl`,
  後端 `server/engine.py:70` `throttle_secs=1.0`,且「版本有變**且內容有變**才 yield」。
  1 Hz、~50–100 列。有小瑕疵(`sideColumns("put")` 每格 `[...QUOTE_COLUMNS].reverse()`,
  每 render ~100 個暫存陣列)但 1 Hz 下無感。優先序最低。
- `lib/oi-levels.ts` / `lib/close-order.ts` / `lib/trade-kinds.ts`:日級 / 事件級,不在熱路徑。
- `lib/flash-arm.ts` reducer / `lib/flash-send.ts`:純狀態機與 promise 尾段,零效能成本,
  但**安全語意極重**(不對稱守門、連 3 敗斷路器)。碰都不要碰。

---

## 3. 題目的六個問題 — 逐題直答

### Q1. 閃電梯有幾列?每 tick 幾列變?React 重繪幾列?

- 現股 / 個股期:**49–150 列**(實測表見 §2.1),典型 100–140。
- 期貨:**121 列**(60+1+60),漲跌停夾界時較少。
- 每則 `book` 真正變值的列:**1–10**(五檔深度上限)。
- 每則 `ticks` 真正變值的列:**2**(`isCenter` 搬家)+ 0–2(`dimmed` 邊界)。
- React 重繪:**全部 130 列**。理想值 1–12 列,**目前是 10–100 倍的浪費**。

### Q2. `TickTape` 列數上限?prepend 是 O(n) 複製 + 全表 re-key 嗎?

- 顯示上限:`PAGE = 30`,按「載入更多」每次 +30;資料上限 `TAPE_MAX = 200`(`stock-accum.ts`)。
- **不是 prepend**:`applyTick` 是 **append + `slice(-200)`**(環形丟頭),
  顯示端再 `[...ticks].reverse()`。
- **不是全表 re-key**:key 用 `TickRow.n`(後端 `seq` 指派),丟頭時倖存列的 key 不變 ——
  這是 N120 已經修過的坑(舊版用尾端回推索引,滿 200 後每筆整個 tbody 重掛)。
  **這一塊做對了,不要動 key 的語意**(CLAUDE.md §4「個股 `seq` 的兩個口徑」)。
- 仍有的浪費:每筆做 200 筆複製 + 反轉但只用 30 筆(§2.8);以及整支沒有 `memo`,
  被 book 訊息帶著空轉。

### Q3. 每列是不是獨立 memo 元件?props 是原始值還是物件?

- **三座梯都沒有列級元件**,列是直接寫在 `rows.map()` 裡的 inline JSX。
- 目前 `LadderView` 從 props 收到的是**物件**:`rows: LadderRow[]`、
  `buyLots/sellLots: Map<number, LadderLot>`、`beMarks/avgMarks: Map<number, string[]>`,
  且這些 Map / 陣列**每 render 都是新 identity**(`aggregateLots` / `markMap` / `buildLadder`
  都在 render body 重算)。
- 所以就算現在直接 `memo(LadderView)` 也**一點用都沒有** —— 要先把資料流改成
  「列級 primitive props」才有意義。

### Q4. 閃爍動畫(flash)怎麼實作?setTimeout + setState?CSS?

**完全沒有閃爍動畫。** 全 repo 的 `animate-` / `@keyframes` / `animation` grep 只命中
`transition-colors`(確認彈窗、委託列、OrderPanel 的 hover),梯上零筆。
(注意:本專案的「flash」指的是**閃電梯 = 一鍵下單**,不是視覺閃爍;
`flash-arm.ts` / `flash-send.ts` / `useFlashArm.ts` 全是武裝狀態機。)

唯一的計時器驅動 state 是 `hint`(`HINT_MS = 3000` 的 `setTimeout` → `setHint(null)`),
它會造成兩次全梯重繪(§2.12)。

**這是一個功能缺口而不是效能問題**:量化看盤台通常要「價格 / 量變動時該格閃一下」。
若要加,**務必**用 CSS animation + 由 DOM 直接改 class(`el.classList.add('flash')` +
`animationend` 移除),或用 CSS 變數驅動,**不要**用 `setState` + `setTimeout` ——
那會把 130 列的重繪頻率再乘上閃爍次數。

### Q5. 下單按鈕的反應延遲:click → fetch 之間做了什麼?

**同步段極短,已查證,不要為此加優化。** 逐行:

`PriceLadder.tsx:272-311` `clickPrice`:
1. `touchIdle()` → `clearTimeout` + `setTimeout`(`useFlashArm.ts:47-51`,**不含 setState**);
2. `KIND_TRAITS[tradeKind].buyLocked` 查表;
3. `arm.state.armed` 布林;
4. `Date.now()` + 一次字串比較(500 ms 同格防抖);
5. `submitStock.mutateAsync({...})` → `useCapital.ts:102-114` `fetchJson`
   → `JSON.stringify(body)` → `fetch(url, init)`。

**TanStack 的 re-render 不會擋在 fetch 前面**(查證 `node_modules/@tanstack/query-core`):
- `mutation.js:94` `#dispatch({type:"pending"})` → 觀察者通知走 `notifyManager.schedule`;
- `notifyManager.js:3` `defaultScheduler = systemSetTimeoutZero` → 通知是 **macrotask**;
- 而 `mutation.js:102/115` 的 `await onMutate` / `await retryer.start()` 是 **microtask**,
  因此 `fetch()` 在同一輪 microtask 就送出,**排在 React re-render 之前**。

**所以真正的延遲來源是主執行緒佔用**:如果 click 落在一段 20–50 ms 的
「book 訊息 → 130 列重繪 + StockChart SVG 重建」long task 中間,瀏覽器要等那段跑完
才能派送 click 事件。**§2.1–§2.5 的每一條都是在修這個。**

附帶兩個真實的小風險(不是延遲,是體驗):
- 送單後 `showHint` 兩次全梯重繪(§2.12),剛好在最敏感的那一刻;
- `useCapitalMutation` 的 `onSuccess` 會 `invalidateQueries(["capital-orders"])` +
  `["capital-positions"]` → 兩發 HTTP + 兩輪 `aggregateLots` / `positionRows` 重算 + 重繪。
  這是正確的(送出去就要看到掛單),但在沒有列級 memo 之前它是全梯重繪。

### Q6. 五檔位移歸一的前端計算量?

`OrderBook.tsx:143-168` / `DepthBar.tsx:75-84`,每則 book:

```ts
const b = (book?.bids ?? []).slice(0, DEPTH);        // DEPTH = 5
const limitB = limitOnly(b);                          // filter ≤5
const maxQty = Math.max(1, ...limitB.map(([, v]) => v), ...limitA.map(([, v]) => v));
const bidTotal = limitB.reduce((s, [, v]) => s + v, 0);
const marketBid = marketQty(b);                       // reduce ≤5
```

**≈ 30 次基本運算 + 6 個小陣列配置,每則 book 一次。完全不是問題。**
量 bar 的寬度用 inline `style={{width: \`${...}%\`}}` —— 每則產生新 style 物件,
但只有 10 個格子。

⚠ 這裡有**口徑契約**(不是效能):`limitOnly` / `bestLimit` / `marketQty` 三支被
`OrderBook` 與 `DepthBar` 共用,「一律只算限價量」是 2026-07-31 user 拍板,
兩邊漂移的症狀是「同一檔在兩頁的總量不同」且零錯誤訊號。**任何最佳化都不准碰這三支。**

---

## 4. 改造建議(依「收益 / 風險」排序)

### 階段 A — 先砍觸發次數(收益最大、風險最低)

**A1. 後端 `book` 加 coalesce + 內容去重**
`stock_engine.py:1359` 改成沿用既有的 `_tick_flush_timer` 樣板:標 dirty → `call_later(0.05~0.1)`
flush 一次最新簿;flush 前比對 `(bids, asks)` tuple 與上次送出值,相同即不送。
- 直接把「130 列重繪」從 tick 級壓到 ≤ 10–20 Hz,且靜市時歸零。
- **不動任何 CLAUDE.md §4 契約**:WS 訊息型別 `{"type":"book", code, bids, asks}` 逐字不變,
  前端 `case "book"` 一行不改。
- ⚠ **五檔延遲是 user 敏感點**:`futures_engine.py:183-184` 的註解白紙黑字寫
  「五檔盤中要即時 → 週期取 0.1 s(1 s 會讓閃電梯五檔慢一秒)」。
  所以窗只能開到 50–100 ms,**要 user 拍板**,不能自己定。

**A2. `App.tsx` 的 `stockCtx` deps 細化**
`[stockCode, stkfutContract, accum]` → `[stockCode, stkfutContract, accum?.book, accum?.last?.p, accum?.meta, accum?.meta?.name]`。
- 同價連續成交、`vp` / `minutes` / `ticks` 的變動不再打到右欄。
- ⚠ `App.memo.test.tsx` 有「計次 + 內容斷言」的守門(App.tsx:253 註解),要一起更新;
  漏欄位的症狀是「右欄掛著舊五檔 / 舊成交價」,**真錢面板**,必須有測試釘住。

**A3. `memo(TickTape)` + `ticks.slice(-limit).reverse()`**
兩行改動,book 訊息不再帶動逐筆表。

### 階段 B — 列級 memo(收益次大,要小心 props 形狀)

**B1. 抽出 `LadderRow = memo(function LadderRow(props))`,props 全 primitive**

```
priceMilli, priceText(預先格式化), bidQty, askQty, isCenter, dimmed,
buyLotText: string | null, buyLotCancelable: boolean,
sellLotText: string | null, sellLotCancelable: boolean,
beMark: boolean, avgMark: boolean, markTitle: string | undefined,
onClickPrice(穩定), onCancelBuy/onCancelSell(穩定,傳 priceMilli 回去查)
```

要點:
- `onClickPrice` / `onCancelLot` 必須 `useCallback` 且**不依賴每 render 變的閉包變數**
  (`tradeKind` / `qtyState` / `arm.state` 要走 ref 讀最新值,否則 callback identity 一變 memo 全破)。
  ⚠ 這一段牽動送單語意:`qtyState.qty` 目前是 render 期間讀的,改 ref 讀要確定
  「按了快捷 3 張之後點價送 3 張」的時序不變(`PriceLadder.test.tsx` 1631 行有大量相關斷言)。
- `fmt(r.priceMilli)` 在同一列裡被呼叫 **3 次**(row title 兩處 aria-label + 價格欄),
  應在 `buildLadder` 階段就把 `priceText` 算好放進 `LadderRow`(題目問的
  「把數字格式化預先算好」)。價格文字只在列集合變(= 換股 / 換界)時才變,
  可以整份快取。
- 預期效果:每則只重跑 1–12 個列函式,其餘 118 列連函式都不進。

**B2. 列的 class 改模組層常數**
配合 B1,把 6 次 `cn()` 換成「4 個預算好的常數 × 三元式」。實測省 ~100 µs/render,
但更重要的是省掉 780 次函式呼叫與字串配置的 GC 壓力。

**B3. 期貨梯同一套**
`FuturesLadder.tsx:465-530` 的 inline 列抽成同款 memo 列(它的 props 已經幾乎都是 primitive,
只有 `mySeqNos: string[]` 要換成 `seqKey: string` + 回查)。

### 階段 C — 繞過 React 的視覺更新(要不要做取決於 A/B 後的量測)

**C1. `content-visibility` — 零相依、純 CSS、先做這個**
梯的 scroll 視窗一次只看得到 ~25 列,其餘 105 列仍然全額 layout + paint。
在列上加 `content-visibility: auto; contain-intrinsic-size: 24px;`
(Tailwind v4 可用 arbitrary property `[content-visibility:auto]`)。
- 瀏覽器會跳過畫面外列的 layout / paint,**React 那邊一行不改**。
- 這是本區塊 CP 值最高的單行改動。需真 Chrome 量測確認不會造成捲動抖動。

**C2. CSS 變數驅動量的更新(只在 A/B 都做完仍不夠時)**
五檔的量(`bidQty` / `askQty`)是唯一每則都變的東西。可以讓 React 只負責列的骨架,
量的更新走 `rowEl.style.setProperty('--bid', qty)` + CSS `content: counter(...)`
或直接 `textContent` 寫入。
- **這是逃逸艙口,不是預設方案**:它把「畫面上的數字」搬出 React 的真相源之外,
  與本 repo「零 ErrorBoundary、靜默失效最可怕」的整體取向相衝。
  A+B+C1 之後若 long task 仍 > 16 ms 再考慮。

**C3. 加價格閃爍(新功能)**
若要做:CSS `@keyframes` + `el.classList.add()`,在 B1 的 memo 列裡用
`useLayoutEffect` 比對前後值觸發,**不要**用 `setState`。

### 階段 D — 資料層

**D1. `applyTick` 改 bundle draft**(§2.6),省 N 倍的 Map 複製。
**D2. `aggregateLots` / `ymdWindow` 進 `useMemo([ordersData, fills, code])`**(§2.7)。
**D3. `fee-discount` 的 `getSnapshot` 改模組層快取**(§2.10)。
**D4. `rowRefs` + `scrollIntoView` → index 算術**(§2.4 / §2.5)。

---

## 5. 這一區塊碰得到的硬約束(CLAUDE.md §4 與等價物)

| 契約 | 在本區塊的位置 | 動到時要同動什麼 |
|---|---|---|
| **`ArmRow` outerHTML 逐字 characterization** | `components/ladder/ArmRow.characterization.test.tsx:110/134`(兩梯 outerHTML 字面量) | 任何 class / 元素順序 / `aria-pressed` 的改動都會紅。武裝列**不要**做效能改動 —— 它一 render 只有 2 顆鈕,毫無收益。 |
| **`OrderRecord.unit` / `FillRecord.unit` 字面值(張/口/股)** | `lib/ladder-lots.ts` 的 `excludeUnit === "股"`(現股梯排零股)、`groupUsableFillsBySeq` 同鍵 | 產生點是後端 `capital/store.py::_lot_unit`;另一讀者是後端 `capital_api.py::_fill_code`(`unit == "口"` 當期貨判準)。memo 化不碰值,但**不准順手改字面值**。 |
| **個股 `seq` 的兩個口徑** | `lib/stock-accum.ts::applyTick`(`n: msg.seq`)/ `fromSnapshot`(由尾回推)/ `TickTape` 的 `key={t.n}` | `applyTick` 改 bundle draft 時,每筆的 `n` 指派與丟頭語意必須逐字保住;`TickTape` 的 key 不准改回索引。 |
| **`ticks` 打包契約(#180)+ 快照/打包 seq 對齊兩道閘** | `useStockStream.ts` `case "ticks"` 的 `isSeededDuplicate` / `seq === acc.seq + 1` / `emitTicks(items)` 整則原序 | bundle draft 化時逐筆判定不可合併;`emitTicks` 必須拿到**原始 items 陣列**(含主圖那一檔)。 |
| **`/api/stock/state/{code}?tape=0` + `tape_omitted`** | `TickTape` 的 `loading={accum.tapeOmitted}` 空態分流 | `memo(TickTape)` 不影響,但 props 形狀改動要保住 `tapeOmitted` 這條線。 |
| **WS 心跳 10 s / 前端 30 s 靜默 watchdog** | 若在前端對 `book` 做 coalesce,必須在 `lib/ws-reconnect.ts` 的 helper **之後**做(helper 已過濾 ping 且負責 watchdog) | 在 helper 之前 buffer 會讓 watchdog 看不到訊息 → 每 35 s 誤重連(症狀:uvicorn access log 每半分鐘 8 條握手)。 |
| **`avg_source` / `today_qty` 語意** | `PriceLadder.positionRows` → `lib/ladder-position.ts::positionEcon` | `positionRows` 做 memo 時 deps 必須含 `positionsData`、`discount.value`、`last?.p`;漏 `discount` 的症狀是「改了折數打平線不動」。 |
| **`PositionKind` ⊆ `TradeKind` + `KIND_TRAITS` `Record` 交集型別** | `lib/trade-kinds.ts` | 不要為了省 `kindTraits(kind)` 的 `Object.hasOwn` 而改成直接索引 —— 那是原型鏈污染的守門(pr-166 F-03)。 |
| **前端 `WATCHLIST_LIMIT = 150` 的效能預算註解** | `stock_engine` / `watchlist_service` / `GroupGridView` 各處以「檔數 × 單價」推理 | 本區塊的 memo 化會改變那些最壞值的推導,改完要回去更新那些註解的判準(CLAUDE.md §4 明記)。 |
| **`MarketOrderButtons` 三態全由 `marketButtonState` 算** | `lib/flash-send.ts` | 不准把 disabled 判定搬進元件做「省一次呼叫」—— 那是安全規則的單一定義處。 |
| **`settleFlashSend` 的兩參數 `then`(不是 `.then().catch()`)** | `lib/flash-send.ts:32-52` | 任何「順手重構」都不准改成鏈式 —— 會讓一次成功的送單同時算 send_ok 與 send_fail。 |
| **Windows / 本機同台** | 後端與前端同一台 Windows 11 跑 | 前端的 CPU 與後端 Python GIL 搶同一顆機器;前端省下來的 main thread 時間,後端 event loop 直接受益。這是做前端最佳化的額外理由。 |

---

## 6. 不要動的地方(明確清單)

1. **`OrderBook.tsx` / `DepthBar.tsx` 的歸一計算** —— 10 個格子、30 次運算。
   `limitOnly` / `bestLimit` / `marketQty` 是口徑契約,改了會靜默失真(2327 鎖停實證)。
2. **不要上虛擬化(react-window / @tanstack/react-virtual)** —— 列數 49–150、key 已穩、
   高度固定,虛擬化能省的只有「畫面外列的 layout/paint」,而那件事
   `content-visibility: auto` 一行 CSS 就做到,且不破壞跟隨置中、`centerRequest` 捲動、
   點價座標穩定性,以及 3877 行既有梯測試。虛擬化在這裡是明確的過度工程。
3. **`clickPrice` / `marketOrder` 的同步段** —— 已查證 click→fetch 無阻塞(§Q5)。
   不要加 optimistic UI、不要把送單搬 Web Worker(`fetch` 本來就是非阻塞的)、
   不要為了「快」而拿掉 500 ms 防抖或武裝檢查。
4. **`ArmRow` 的 DOM** —— outerHTML 字面測試鎖死,且只有 2 顆鈕。
5. **`lib/flash-arm.ts` / `lib/flash-send.ts`** —— 純安全語意,零效能成本。
6. **`capital/*.tsx` 三支 list** —— 只在非閃電 tab 掛載,15/30 s 輪詢 + 200 ms debounce。
7. **`lib/oi-levels.ts` / `lib/close-order.ts` / `lib/position-summary.ts`** —— 日級 / 事件級。
8. **`TickTape` 的 `key={t.n}`** —— N120 修過的坑,改回索引會讓 tbody 每筆整片重掛。
9. **`QuoteTable`** —— 1 Hz + 後端內容去重,有小瑕疵但不值得動(若真要動,
   只改 `sideColumns` 的兩個常數陣列預先算好即可,一行)。
10. **不要引入狀態管理庫** —— repo 已有兩處正確的 `useSyncExternalStore` + module store
    先例(`fee-discount` / `useCapital` 的 wsStatus)。問題不是缺工具,是 `accum`
    這顆大物件被當成單一 dep。

---

## 7. 量測方法(證明快 / 慢的具體做法)

### 7.1 前置:一定要用 prod build
```
cd frontend && npm run build && npm run preview     # port 4173
```
CLAUDE.md 已明記:dev build 的 props-diff 開銷會污染量測,整天掛著一律用 preview。
**任何效能數字若是在 `npm run dev` 量的,一律作廢。**

### 7.2 先回答最重要的未知:`book` 到底多快
兩條路任選(推薦後端,不動前端):
- 後端:`stock_engine._publish` 加 per-type 計數器,`/api/health` 多回
  `{"ws_msgs": {"ticks": n, "book": m, "watchlist_quote": k}}`,開盤 09:00–09:05 取兩次差值。
- 前端:`useStockStream.handle` 入口 dev-only 計數,每 5 s `console.log`。

判準:若 `book` 的每秒則數 > `ticks` 的 3 倍,A1 的收益就已經確立。

### 7.3 主執行緒佔用(這是「不能塞住」的前端判準)
用已裝的 chrome-devtools MCP:
1. `performance_start_trace` → 停在個股頁 + 右欄閃電 tab,選一檔開盤的熱門股;
2. 錄 60 s 跨 09:00;
3. `performance_stop_trace` → 看
   - **Long Tasks(> 50 ms)數量**(目標:0,這是 #187 已用過的判準)
   - Main thread 佔用率(目標:< 30%)
   - Scripting / Rendering / Painting 三段比例
   - Recalculate Style 與 Layout 的觸發次數(對照 `scrollIntoView` 的強制 layout)
4. 常駐監測:在 `main.tsx` 加 dev-only
   `new PerformanceObserver(l => l.getEntries().forEach(e => console.warn('longtask', e.duration))).observe({entryTypes:['longtask']})`。

### 7.4 元件級歸因
React DevTools Profiler 錄 10 s,看 `PriceLadder` / `LadderView` / `TickTape` / `StockChart`
的 **render 次數**與 **self time**。改前 / 改後各一份,附進 PR。

### 7.5 下單延遲的直接量測(端到端)
```ts
// clickPrice 第一行
performance.mark("order:click");
// useCapital.fetchJson 的 fetch 之前
performance.mark("order:fetch");
performance.measure("order:click→fetch", "order:click", "order:fetch");
```
搭配 DevTools Network 的 request start timestamp,量「按下去到請求出門」。
**判準:p95 < 5 ms**(目前推測已經達標,這一條是用來證明「不要動送單路徑」的)。
真正要盯的是同一份 trace 裡「click 事件的 Input Delay」——那才是使用者感受到的延遲。

### 7.6 微量測(本報告用的兩支,可重跑)
放在 `frontend/` 底下臨時跑(用完即刪,不進版控):
- `cn` × 780 / render:`twMerge(clsx(...))` 六種組合 × 130 列 × 1000 輪 → 101.5 ms(101.5 µs/render)。
- `applyTick` 的三次複製(minutes 270 / vp 600 / ticks 200)× 200k → 41.21 µs/tick。

---

## 8. Open questions(需要 user 回答或需要開盤取證)

1. **`book` 訊息的真實到達頻率**。整份分析的量級依賴它。未量測(不啟 server 是本次紀律)。
2. **五檔可以容忍多少延遲?** `futures_engine.py:183-184` 的註解顯示 user 對「五檔慢一秒」
   有明確不滿。A1 的 coalesce 窗(50 ms / 100 ms)是 user 拍板事項,不是我能定的。
3. **實際盯的價格帶** → 決定梯列數落在 49 還是 150。低價股(< 50 元)是最壞情況。
4. **是否要加價格 / 量的閃爍視覺回饋**(目前完全沒有)。這是新功能不是效能,
   但它會改變「列級 memo 要傳什麼 props」的設計,應該在階段 B 之前決定。
5. **是否評估 React Compiler**(`babel-plugin-react-compiler`)。它能一次解掉列級 memo 與
   callback identity 兩件事,但本 repo 有多處「render 期間調整 state」的官方 pattern
   (`RightRail.tsx:178-186`、`fee-discount.ts:95-99`)與大量 ref 寫入,
   導入前必須先跑 `react-compiler-healthcheck` 看違規數。
6. **`last` 物件能不能降成 `lastMilli: number`**?牽動 `RightRail.positionsContent` 的
   `closePriceOf` 與三梯的「估價缺 → 鎖市價鈕」安全閘。
7. **群組檢視開著時,右欄閃電梯的重繪與 50 張卡的重繪疊加後的總 long task**
   —— 需要與 F5 區塊合併量測(同一份 trace)。

---

## 9. 工具選型建議與取捨

| 工具 | 用在哪 | 解決什麼 / 預期收益 | 代價 | 判定 |
|---|---|---|---|---|
| **`content-visibility: auto` + `contain-intrinsic-size`**(純 CSS) | `LadderView` / `FuturesLadder` 的列 | 跳過畫面外 ~105 列的 layout / paint;零 JS、零相依、零契約 | 需真 Chrome 驗證捲動不抖;Firefox 支援較晚(本專案只跑 Chrome) | **建議導入(最先做)** |
| **`React.memo` 列元件 + `useCallback`**(React 內建) | `LadderView` / `FuturesLadder` | 每則只重跑 1–12 列而非 130;最大單項收益 | 要把 props 全改 primitive、callback 要走 ref 讀最新 qty/tradeKind;`PriceLadder.test.tsx` 1631 行要跟 | **建議導入** |
| **後端 book coalesce**(stdlib `call_later`,沿用既有 `_tick_flush_timer` 樣板) | `stock_engine.py:1359` | 觸發次數直接砍;不新增任何相依,符合 stdlib-only | 五檔延遲 50–100 ms,**要 user 拍板** | **建議導入(需拍板)** |
| **`babel-plugin-react-compiler`** | 全 frontend | 自動 memo + 自動穩定 callback,一次解掉 B1/B2 的手工活 | React 19 + Vite 6 可用但仍在演進;repo 大量 render 期間 setState / ref 寫入需 healthcheck;會讓「哪裡有 memo」變隱性,與本 repo「註解寫清楚每個決策」的文化相衝 | **有條件導入**(先跑 healthcheck,再由 user 決定) |
| **`@tanstack/react-virtual` / `react-window`** | 梯列 | 虛擬化 | 130 列不值得;破壞跟隨置中 / `centerRequest` / 點價座標 / 既有測試 | **不建議** |
| **zustand / jotai / valtio** | accum 狀態拆分 | selector 訂閱 | repo 已有正確的 `useSyncExternalStore` 手刻先例;真正的問題是 `useMemo` 的 dep 粒度,換庫不會自己解決 | **不建議** |
| **`use-sync-external-store/with-selector`**(React 官方 shim,已在 React 生態內) | 若要把 `accum` 拆成 book / last / tape / vp 四個 slice store | 讓梯只訂 book+last、逐筆只訂 tape、圖只訂 minutes+vp —— 這是「從根本解決」的版本 | 大改 `useStockStream`;#180 / #187 的 seq 兩道閘要重新驗;工程量 XL | **有條件導入**(A/B/C1 都做完仍不夠時的下一步) |
| **移除熱路徑上的 `tailwind-merge`**(保留相依,只是不在梯上呼叫) | `LadderView` / `FuturesLadder` / `TickTape` | 省 780 次/render 的字串解析 | 失去「後寫的 class 勝」保護,要人工確認沒有衝突 class | **建議導入(隨 B1 一起)** |
| **`PerformanceObserver('longtask')` 常駐 dev 監測** | `main.tsx`(dev-only) | 把「不能塞住」變成可觀測的判準,而不是感覺 | 幾行 code;prod build 要排除 | **建議導入** |
| **chrome-devtools MCP performance trace** | 驗收 | 已裝;#187 已有「93 s 內 >50 ms = 0」的先例判準 | 需開盤取證 | **建議導入(當驗收 gate)** |

---

## 10. 附:建議的改動順序與預期

| 順序 | 改動 | 工程量 | 預期效果 | 風險 |
|---|---|---|---|---|
| 1 | C1 `content-visibility`(CSS 一行 × 2 梯) | S | layout/paint 側 -60~80% | 低(視覺驗證) |
| 2 | A3 `memo(TickTape)` + `slice(-limit)` | S | 逐筆表不再被 book 帶動 | 低 |
| 3 | D3 fee-discount 快照快取 | S | 每則省 8 次 localStorage | 低 |
| 4 | D4 `rowRefs` → index 算術 + `scrollTop` | S | commit 階段 -260 次 ref 操作;消掉強制 layout | 中(置中行為要逐項驗:跟隨 / 手動捲暫停 / `centerRequest`) |
| 5 | A2 `stockCtx` deps 細化 | S | 同價連續成交不重繪右欄 | 中(`App.memo.test.tsx` 要更新) |
| 6 | D2 `aggregateLots` useMemo | S | 每則省一次全帳戶掃描 | 低 |
| 7 | D1 `applyTick` bundle draft | M | 開盤一則打包 -N 倍複製 | 中(seq 兩道閘要逐筆保住) |
| 8 | B1+B2 列級 memo + class 常數 | L | **每則只重跑 1–12 列**,主要收益 | 中高(callback identity / qty 時序 / 1631 行測試) |
| 9 | A1 後端 book coalesce | M | 觸發次數直接砍 | 中(需 user 拍板延遲) |
| 10 | B3 期貨梯同套 | M | 10 Hz × 121 列同樣受益 | 中 |
| (待定) | C2 CSS 變數 / DOM 直寫、C3 閃爍動畫、React Compiler、accum store 拆分 | L–XL | 視 1–10 之後的量測 | 高 |
