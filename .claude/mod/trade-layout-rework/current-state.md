# Phase 1 現況表 — 交易版面重構(閃電下單右欄 / 五檔水平 / 委託部位右欄)

分支 `mod/trade-layout-rework`,基準 `be027ca`(master;本 repo 無 remote,mainline = master)。

## Baseline 測試

| Gate | 結果 |
|---|---|
| `npm test -- --run`(frontend/) | **41 files / 287 tests PASS**(2026-07-29 10:26) |
| `pytest -q`(root) | 見 Phase 6 收錄 |

## 目前版面(讀 code 得出的實況)

### App 外殼 `frontend/src/App.tsx`

- L47 root:`mx-auto flex h-full max-w-6xl flex-col gap-4 px-4 py-5`
  → **`max-w-6xl` = 72rem 上限**,即 user 說的「被壓在中間太多」的直接成因(1920/2560 螢幕
  root font-size 放大後仍是 72rem 硬上限)。
- L48-72 nav:4 個 tab(`txo` / `stock` / `futures` / `index`)+ `IndexBar`。
- L73-102:四個 tab 各一個 `<div hidden={tab !== ...}>`;`visited` 控制首次 mount(lazy)。
- **無任何跨 tab 常駐的側欄**。`useIndexStream` / `useCapitalStream` 已常駐 App 層
  (WS 唯一連線,review B2/B4)。

### 個股頁 `frontend/src/components/stock/StockPage.tsx`(132 行)

現況結構(L34-128):

```
<div flex flex-1 gap-4>
  <WatchlistSidebar>            ← w-60 shrink-0(左)
  <main flex-1 flex-col gap-3>
    header(股名/現價/漲跌%/期現價差/總量)
    <StockIntradayChart>        ← 江波圖(SVG,固定 viewBox 800x260 + 副圖 800x70)
    <div flex flex-wrap gap-3>
      <OrderBook>               ← 五檔(min-w-56,直式 table)
      <TickTape>                ← 明細(flex-1)
      <PriceLadder>             ← 閃電梯(w-60 shrink-0,可摺疊)
    </div>
    <div flex flex-wrap gap-6 border-t>
      <CapitalOrdersList market="sec">   ← 委託
      <CapitalPositionsList market="sec"> ← 部位
    </div>
  </main>
</div>
```

- `code` state + `MAIN_CODE_KEY = "stock-main-code"` localStorage。
- `useStockStream(code)` 回 `{ accum, watchlist, status, stkfut, wsStatus }`。
- 平倉估價 `closePriceOf` = 主檔最新成交價(`pos.stock_no === code` 才有值)。

### 期貨頁 `frontend/src/components/futures/FuturesPage.tsx`(122 行)

```
<div flex flex-1 flex-col gap-3>
  header(商品切換 TXF/MXF/TMF + 現價 + resolved 合約 + ConnectionBadge)
  <div flex flex-wrap items-start gap-4>
    <FuturesLadder>             ← w-64 shrink-0 閃電梯(自帶五檔量在梯上)
    <div flex min-w-64 flex-1 flex-col gap-4>
      <CapitalOrdersList market="fut">
      <CapitalPositionsList market="fut">
    </div>
  </div>
</div>
```

- `product` state + `PRODUCT_KEY = "copycat-fut-product"`。
- 平倉估價 `futCloseEstimate`(**exported**,`FuturesPage.test.tsx` 直接測)= 漲跌停貼價。
- **無江波圖 / 無獨立五檔 / 無明細**(五檔量直接畫在閃電梯格內)。

### 五檔 `frontend/src/components/stock/OrderBook.tsx`(111 行)

- **直式 `<table>`**:賣5→賣1(反序)→ 中間成交價列(colSpan=3,含鎖漲/跌停 badge)→ 買1→買5。
- 每列 3 欄:`檔位標籤 w-8` / `價格 w-20`(button)/ `量 w-24`(含比例底色 bar)。
- 點價 → `window.dispatchEvent(CustomEvent("stock-price-click", { detail:{priceMilli, side, code} }))`
  **不送單**;唯一訂閱者 = `PriceLadder.tsx:195-206` → 該價 `scrollIntoView({block:"center"})`
  + `setFollow(false)`。
- 底色 bar 方向:賣側 `left-0` 往右長、買側 `right-0` 往左長(SC-5 慣例)。
- `bidTotal` / `askTotal` 表頭;`lockedUp` = `bids[0][0] === upper`,`lockedDown` 同理。

### 閃電梯

| | `stock/PriceLadder.tsx`(414 行) | `futures/FuturesLadder.tsx`(339 行) |
|---|---|---|
| 寬 | `w-60 shrink-0` | `w-64 shrink-0` |
| 摺疊 | 有(`OPEN_KEY="stock-ladder-open"`,收合成一顆「閃電梯」鈕) | 無 |
| 武裝 | `flash-arm` reducer 共用 | 同 |
| 額外控制 | 交易別 select(現股/融資/融券/無券) | 當沖 checkbox |
| 量單位 | 張 | 口 |
| 送單 | `useSubmitStock` | `useSubmitFuture`(`TC.F.TWF.<prod>.HOT`) |
| 我的單 | `aggregateLots(orders, code)` 本檔聚合 | `splitMyLots(orders, contract)` |
| 捲動 | `max-h-96 overflow-y-auto` + 跟隨置中 | 同 |
| 監聽 | `stock-price-click`(唯一訂閱者) | 無 |

### 自選 `frontend/src/components/stock/WatchlistSidebar.tsx`(327 行)

**群組功能已完整實作**(user 第 4 點需求「自選可新增群組、把個股加進群組」**現況已存在**):

- 群組 tab 列:「全部」(union,停用拖拉)+ 各群組 tab + `×` 刪群組 + `+` 新增群組(inline input)。
- 個股列 hover 出兩鈕:`⊞` 移組(展開 checkbox 面板,多群組可同時歸屬)、`×` 移除。
- 拖拉排序(僅在具體群組內,`list-drag.ts` 的 `insertIndexFromPointer` / `reorder`)。
- `activeGroup` localStorage `GROUP_KEY = "stock-wl-group"`;`DEFAULT_GROUP = "自選"`。
- 「全部」下新增 → 進「自選」群組(不存在自動建立);「全部」下移除 = 從所有群組移除。
- 寬 `w-60 shrink-0`。

### 後端契約(本次相關)

| Endpoint | 用途 | 現況 |
|---|---|---|
| `GET/PUT /api/stock/watchlist` | 群組自選(schema v2 `groups`) | 已有,含 30 檔上限(聯集計) |
| `GET /api/stock/overlay/{code}` | CDP/MA 疊線 | **只回算好的 cdp/ma5/ma20/date,不回原始 bar** |
| `GET /api/stock/state/{code}` | 個股當日快照 | 已有 |
| `WS /ws/stock` | 個股推播 | 已有 |
| `GET /api/futures/state` + `WS /ws/futures` | TXF/MXF/TMF 五檔 | 已有 |
| `/api/capital/*` + `WS /ws/capital` | 委託/部位/下單 | 已有 |

**K 線資料源**:`copycat/live/stock_source.py:274 fetch_daily_bars(code, n=25)` 回
`list[DailyBar]`(DK 優先、1K 聚合 fallback)。
**目前唯一 consumer 是 `build_overlay`,沒有任何 endpoint 把原始 bar 吐給前端** →
「江波圖可切 K 線」需要新 endpoint(🟢 新功能),不是純前端改版。

> `[amendment 2026-07-29: review P2-13 — 原寫 DailyBar 欄位為 date/open/high/low/close/volume,係事實錯誤]`
> **`DailyBar` 實際只有 4 欄:`date` / `high` / `low` / `close`**(`stock_source.py:34-41`)。
> **沒有 open、沒有 volume**;`_parse_dk_rows`(:51-70)與 `_aggregate_1k_rows`(:73-97)
> 都只解析 High/Low/Close。畫蠟燭需要的 open/volume **兩條路徑都得新做**,
> 且 DK 的 `Open` / `Volume` 欄位名**未實測**(CLAUDE.md §8 只實證 High/Low/Close)。
> 另 `_DAILY_WINDOW_DAYS = 40`(日曆日)≈ **27 個交易日**,拿不到 120 根。

**Protocol 契約**:`copycat/server/stock_engine.py:28-45 class StockSource(Protocol)` 明列
`fetch_daily_bars`;新增 source 方法必須同步擴充 Protocol 與**兩個測試 fake**
(`tests/server/test_stock_engine.py:78`、`tests/server/test_stock_routes.py:42`),
否則 pyright gate 紅。

**TC4 REQ 互斥(粒度與範圍)** `[amendment 2026-07-29 round2: review R2-8 — 原寫「_api_lock 全域鎖」係事實錯誤]`:
- `tc4.py:132 _api_lock` **不是** REQ 鎖 —— 註解明寫是「`_api`/`_session` **指標讀寫專用小鎖**」
  (讓 `_dispose` 的 check-then-clear 與 `_ensure_connected` 的指標發布原子)。
- 真正序列化 REQ 的是 **`api.lock`**(`tc4.py:214 api.lock.acquire(timeout=self._lock_timeout)`),
  粒度 = **單次 REQ 往返**(send/recv 後即 release),**不是**整段 SubHistory 收割。
- 範圍 = **per-source 實例**(每個 `TC4QuoteSource` 各自 `QuoteAPI(...)`,`tc4.py:144`)。
  故競爭者是「同一個個股 source 上的」訂閱/退訂、tick 回補、overlay 日 bar、新的 bars 抓取;
  **不跨** index / futures 引擎。

## Caller map(要動的元素,含動態用法)

| 目標 | Caller / 依賴 | 種類 |
|---|---|---|
| `App.tsx` root `max-w-6xl` | 無其他 caller;`App.test.tsx` 不斷言寬度 | CSS |
| `StockPage` | `App.tsx:15` lazy default import;`StockPage.test.tsx` 具名 import | 靜態 |
| `FuturesPage` | `App.tsx:16` lazy default import;`FuturesPage.test.tsx` 具名 import + **`futCloseEstimate` 具名 export 被測試直接呼叫** | 靜態 |
| `OrderBook` | 僅 `StockPage.tsx:89`;`OrderBook.test.tsx` | 靜態 |
| `PriceLadder` | 僅 `StockPage.tsx:101`;`PriceLadder.test.tsx` | 靜態 |
| `FuturesLadder` | 僅 `FuturesPage.tsx:102`;`FuturesLadder.test.tsx` | 靜態 |
| `WatchlistSidebar` | 僅 `StockPage.tsx:36`;`WatchlistSidebar.test.tsx` | 靜態 |
| `CapitalOrdersList` / `CapitalPositionsList` | `StockPage`(sec)+ `FuturesPage`(fut);各自 test | 靜態 |
| **`"stock-price-click"` CustomEvent** | 發:`OrderBook.tsx:21`;收:`PriceLadder.tsx:204`。**字串型動態耦合**,grep 全庫僅此兩處 + `OrderBook.test.tsx` / `PriceLadder.test.tsx` | **動態** |
| localStorage key(字串常數) | `copycat-tab` / `stock-main-code` / `stock-ladder-open` / `stock-wl-group` / `copycat-fut-product` / `chart-toggles`(useChartToggles) | **動態(persist 契約)** |
| `useStockStream(code)` | 僅 `StockPage` | 靜態 |
| `useFuturesStream()` | 僅 `FuturesPage` | 靜態 |
| `useCapitalStream()` | 僅 `App.tsx:39`(唯一 WS,review B2) | 靜態 |

grep 驗證指令:
`grep -rn "stock-price-click\|max-w-6xl\|localStorage" frontend/src`(已跑,結果如上表)。

## 現況 vs 目標(user 需求逐條)

| # | user 需求 | 現況 | 目標 | 對 caller 影響 | backward compat |
|---|---|---|---|---|---|
| 1 | 閃電下單放最右邊獨立一排 | `PriceLadder` 在個股頁中段第三欄;`FuturesLadder` 在期貨頁左側 | 移到全站最右欄 | StockPage / FuturesPage 版面重組 | localStorage `stock-ladder-open` 語意可能改變 |
| 2 | 五檔改水平 | `OrderBook` 直式 table(賣5↓賣1 / 成交 / 買1↓買5) | 水平佈局 | 僅 StockPage;`OrderBook.test.tsx` 需改(🔴) | 點價 CustomEvent 契約要保留 |
| 3 | 委託 + 部位放最右邊 | 個股頁底部 / 期貨頁右側,**各 tab 一份** | 右欄 3 tab(閃電/五檔?/委託/部位) | 兩頁都拆走 | `market` prop 來源改變 |
| 4 | 自選可新增群組並加入個股 | **已實作**(群組 tab + ⊞ 移組 + 拖拉) | 待確認是否另有缺口 | — | — |
| 5 | 中間:上江波圖(可切 K 線)、下左五檔、下右明細 | 江波圖有;**K 線圖不存在**;五檔/明細/閃電梯三欄並排 | 需新 K 線圖 + 後端 bar endpoint | 🟢 新功能,跨前後端 | 新增 endpoint 無破壞 |
| 6 | 充分利用網頁空間 | `max-w-6xl` 硬上限 | 放寬 | 全站所有 tab 都受影響 | TXO/指數頁版面也會變寬 |
| 7 | 右欄固定,切期貨時不動 | 右側內容目前綁在各 tab 內 | 提升到 App 層常駐 | **重大結構改動**,方向性待拍板 | — |

## 已知風險/待釐清(Phase 2 要拍板)

- **R1「右邊區塊不會動」的語意**:是「右欄提升到 App 層、內容永遠跟個股走」,還是「右欄位置固定、
  內容隨當前 tab 的標的切換」?兩者對閃電下單的送單標的判定完全不同(誤送 = 真錢)。
- **R2 K 線圖範圍**:日 K only,還是含分 K?需不需要互動(crosshair / 縮放)?後端 `fetch_daily_bars`
  只回 25 根,n 可調但 DK 支援度「未實測」(CLAUDE.md §0 記載)。
- **R3 右欄若要顯示五檔**:user 描述「最右邊固定閃電下單、使用者的委買委賣、倉位 然後用一個區塊
  三個 tab 控制」——「使用者的委買委賣」可能指**使用者自己的掛單**(= 委託單)而非市場五檔。
  與「中間下面左邊是委買賣」(市場五檔)是兩個不同東西,需釐清。
- **R4 期貨頁沒有江波圖/明細/獨立五檔**:若右欄提升到 App 層,期貨頁中間剩什麼?
- **R5 `max-w-6xl` 放寬會同時改到 TXO 與指數頁**,那兩頁的 SVG 是固定 viewBox(`w-full` 自適應),
  但 `QuoteTable` / `PnlChart` 的視覺密度會變 — 是否接受?
