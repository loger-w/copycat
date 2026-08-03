# Phase 1 現況表 — 個股頁 5 項修改(stock-ui-fixes)

蒐證日期:2026-07-29 16:30–16:45(盤後,TC4 常駐開啟,vite dev :5174 + backend :8721 執行中)

## 0. Baseline

| 項目 | 指令 | 結果 |
|---|---|---|
| 後端測試 | `.venv\Scripts\python -m pytest -q` | **1188 passed**, 1 warning, 41.78s |
| 前端測試 | `npm test`(frontend/) | **382 passed / 47 files**, 7.37s |

Working tree 乾淨,分支 `mod/stock-ui-fixes` 自 `master`(6c5f56c)開出。
**無 git remote**(`git remote -v` 空、`git fetch` 失敗)→ branch-lifecycle 開工節同步步驟跳過;
本 repo 主線是 `master`(無 `main` 分支)。

---

## 1. 五檔版式(item 1:參照 treading-king)

### 現況

`frontend/src/components/quote/DepthBar.tsx`(160 行)—— **水平 10 格版式**:

```
[量/價列標] 買5 買4 買3 買2 買1 │ 成交價+% │ 賣1 賣2 賣3 賣4 賣5 [量/價列標]
             每格:量(上) / 價(中) / 垂直量 bar(下,高度 = qty/maxVol)
上緣:委買總量(左,紅) ────────── 委賣總量(右,綠)
中央格:成交價 + 漲跌% + 鎖漲停 / 鎖跌停 badge
```

- 檔位不足補「—」不塌陷;`onPriceClick` 未給時 Cell 渲染成 `div` 而非 `button`(避免假 affordance)。
- 個股側 `OrderBook.tsx` 只做接線:點價 → `stock-price-click` CustomEvent → RightRail 切閃電 tab + ladder 置中。

### 參照對象:treading-king `frontend/src/components/QuoteBook.tsx`(107 行)

**垂直雙欄版式**:

```
標題列:委買賣 五檔   [鎖漲停 badge] [鎖跌停 badge]        [· 更新失敗]
總量列:1085 張(大字,紅,左)          3576 張(大字,綠,右)
grid-cols-2 gap-8:
  左欄(買)5 列              右欄(賣)5 列
  [量 張]      [價]          [價]      [量 張]
  ← 水平量 bar 靠右貼齊       水平量 bar 靠左貼齊 →
  (bar = absolute inset-y-0,width = size/maxQty,z-index 在文字下)
  每列 border-b border-line、cursor-pointer、hover:bg-bg-card/40
  price === 0 顯示「市價」(鎖停對手檔);size === 0 顯示「—」
```

差異軸:**排列方向(水平 → 垂直雙欄)/ 量 bar 方向(垂直柱 → 水平列背景)/ 總量呈現(小字列 → 大字)/ 單位(無 → 張)/ 千分位(無 → toLocaleString)**。

### Caller map(grep `DepthBar`,含測試)

| 檔案 | 用法 | 影響 |
|---|---|---|
| `components/stock/OrderBook.tsx:24` | `<DepthBar ... onPriceClick>` | 個股五檔(本輪目標) |
| `components/futures/FuturesPage.tsx:78` | `<DepthBar ...>`(**無 onPriceClick**) | 期貨頁五檔(**非本輪目標**,user 說「先專務在個股上」) |
| `components/quote/DepthBar.test.tsx` | 直接測 DepthBar | 動版式即紅 |
| `components/stock/OrderBook.test.tsx` | 106 行,測點價事件 + 渲染 | 版式斷言部分會紅 |
| `components/futures/FuturesPage.test.tsx:139` | 「渲染水平五檔(與個股共用 DepthBar)」 | **共用元件一改即紅** |

動態用法:無(無字串拼接 / reflection / dynamic import 指向 DepthBar)。
`data-testid="depth-vol-bar"` 是唯一測試側耦合點。

> ⚠ **方向性抉擇**:DepthBar 是個股 / 期貨共用。改它 = 期貨頁版式同時變 → 撞「先專務在個股上」。
> 見 change-spec Q1。

---

## 2. K 線無資料(item 2)

### 症狀(實測)

個股頁選 2317、K 線模式(日K)→ 圖表區顯示「**無 K 線資料**」(截圖 `stock-before.png`)。

### 根因(已定位,證據確鑿)

**執行中的 backend(:8721, pid 3328)是舊版 build,根本沒有 `/api/stock/bars/{code}` 這條 route。**

證據 —— `GET http://127.0.0.1:8721/openapi.json` 的 paths 全列:

```
/api/capital/*(9 條)、/api/futures/state、/api/index/state、
/api/stock/overlay/{code}、/api/stock/state/{code}、/api/stock/watchlist、
/api/trade/*(3 條)、/api/txo/*(4 條)
```

→ **`/api/stock/bars/{code}` 不在其中**;直接打該 URL 回 **HTTP 404**。

前端鏈路吻合:`useStockBars.fetchBars` 對 `!res.ok` 丟 `HTTP_404` → TanStack Query `isError`
→ `StockChart.tsx:83-86` 渲染「無 K 線資料」。

這與 `docs/next-time.md`(2026-07-29 trade-layout-rework 條)已記的事實一致:
「本輪出貨時 8721 已被舊版 server 佔用且盤中,不自行重啟搶 TC4 推播」——
K 線 endpoint **從實作完成到現在從未在真實環境跑過**。

### 尚未排除的第二層風險(必須重啟後才驗得到)

重啟 server 後 K 線仍可能空,因為下列全是**未實測假定**:

| 假定 | 出處 | 若不成立的後果 |
|---|---|---|
| DK rows 的 `Open` / `Volume` 欄位名 | `stock_source.py:124,137`;CLAUDE.md §8 只實證 H/L/C | bar 缺 o/v(防禦解析:缺 Open → 用 Close、缺量 → 0),不致全空 |
| DK 對「股票 + 180 日曆日區間」可用 | CLAUDE.md §8 只實證 2330 抓 25 根 | DK 回空 → 走 1K 聚合 fallback(視窗縮短) |
| `_collect_history` 首頁 poll ≈30s 內收得完 | `stock_source.py:379` | 逾時回空 → 仍顯示「無 K 線資料」 |

→ **驗證前置:必須用當前 code 重啟 :8721**(現在 16:45 已收盤,無盤中推播可搶)。

### Caller map(K 線鏈路)

`StockChart.tsx` → `useStockBars.ts` → `GET /api/stock/bars/{code}` → `app.py:393 stock_bars`
→ `server/bars.py build_daily` / `build_minute` → `stock_engine.bars_range`
→ `live/stock_source.fetch_bars_range`(DK 優先 → 1K 聚合 fallback)。
`lib/candle.ts` 只做幾何,不碰資料。

---

## 3. 圖表拖曳選字(item 3)

### 現況

`StockIntradayChart.tsx`(江波圖)與 `CandleChart.tsx`(K 線)的 `<figure>` / `<svg>`
**沒有任何 `select-none` / `user-select`**。兩張圖的 SVG 內含大量 `<text>`:

| 元件 | `<text>` 來源 |
|---|---|
| StockIntradayChart | x 軸時間標籤(5)、y 軸左價位 + 右 %、疊線 label(CDP/MA)、hover tooltip 兩行 |
| CandleChart | y 軸價位刻度、x 軸時間標籤(至多 6)、(tooltip 在 `<figcaption>`,HTML 非 SVG) |

Chrome 對 SVG `<text>` 預設可選取 → 在圖上按住拖曳(使用者的自然「拉一段來看」手勢)會反白選字。
`figcaption` / 圖下方的累積內外盤文字也一併被選取。

全 repo grep `select-none` 只有一處:`WatchlistSidebar.tsx:259`(拖拉把手 `⋮⋮`)。

### Caller map

兩個元件各自獨立,無共用 wrapper。`StockChart.tsx` 是它們的唯一父層(依 mode 二選一)。
期貨頁 / 指數頁 / TXO 頁的圖(`PnlChart`、`IndexPage`)**不在本輪 scope**(user 說先專務個股)。

---

## 4 + 5. 捲軸樣式與捲動範圍(item 4 / item 5)

> **判讀**:全 repo 無任何 resize / splitter / draggable 面板機制(grep `draggable` /
> `onDragStart` / `cursor-col-resize` / `resize` 全空,只有 WatchlistSidebar 的清單重排把手)。
> 「拖曳條」= **捲軸(scrollbar)**;「元素能拖曳」= 該元素有捲軸可拖。
> 使用者列的三個(明細 / 閃電下單 / 自選股票清單)= 現存的三個**內層**捲動容器,完全對得上。
> ⚠ 此判讀需 user 確認,見 change-spec Q2。

### 現況:捲軸樣式(item 4)

`frontend/src/index.css` 全檔 36 行,`@theme` 只定義色票 + 字型,**沒有任何 scrollbar 樣式**
(無 `::-webkit-scrollbar`、無 `scrollbar-color` / `scrollbar-width`)。

→ 所有捲動容器都用 **Chrome 預設亮色捲軸**(白底 / 淺灰 slider),在 `--color-bg: #0a0e14`
的暗色盤面上非常突兀。截圖 `stock-intraday-before.png` 中三條白色捲軸清晰可見
(x≈1590 主區、x≈1578 明細、x≈1895 閃電梯)。

### 現況:捲動容器盤點(item 5)

全 repo `overflow-*` 共 11 處:

| # | 檔案:行 | 容器 | 個股頁? | user 期望 |
|---|---|---|---|---|
| 1 | `stock/StockPage.tsx:32` | `<main>` **個股頁最外圍** | ✅ | **不該捲** ← 本輪目標 |
| 2 | `stock/TickTape.tsx:26` | 明細(`max-h-80`) | ✅ | 該捲 ✔ 保留 |
| 3 | `stock/PriceLadder.tsx:337` | 閃電梯價格列 | ✅(右欄) | 該捲 ✔ 保留 |
| 4 | `stock/WatchlistSidebar.tsx:241` | 自選清單 `<ul>` | ✅ | 該捲 ✔ 保留 |
| 5 | `rail/RightRail.tsx:209` | 委託 tab | ✅(右欄) | user 未提(非閃電 tab) |
| 6 | `rail/RightRail.tsx:211` | 部位 tab | ✅(右欄) | user 未提 |
| 7 | `App.tsx:199` | TxoPage 根 | ❌ TXO 頁 | 非本輪 scope |
| 8 | `futures/FuturesPage.tsx:36` | 期貨頁根 | ❌ 期貨頁 | 非本輪 scope |
| 9 | `futures/FuturesPage.tsx:38` | `overflow-hidden`(商品鈕圓角裁切) | ❌ | 無關 |
| 10 | `futures/FuturesLadder.tsx:294` | 期貨閃電梯 | ❌ | 非本輪 scope |
| 11 | `QuoteTable.tsx:193` | TXO 報價表橫捲 | ❌ | 非本輪 scope |

### 實測:哪些真的在捲(1920×1080,2317,盤後)

`document.querySelectorAll("*")` 掃 computed `overflow-y` + `scrollHeight > clientHeight`:

| 模式 | 實際出現捲軸的容器 |
|---|---|
| 日K(K 線空) | 明細(788/318)、閃電梯(2280/860) —— **`<main>` 不捲** |
| 江波圖 | **`<main>` 1012/1002**(溢出 10px,✅ 重現 item 5)、明細(788/318)、閃電梯(2280/860) |

`document.documentElement.scrollHeight === clientHeight === 1080` → body 層不捲(`#root` 有
`height:100%`,App root `h-full` 未溢出)。**所以「最外圍」指的是 StockPage 的 `<main>`**,不是 body。

江波圖比日K高 10px 的來源:江波圖 = 主圖 SVG(viewBox 800×260,`w-full` → 高度隨寬度)
+ 副圖 SVG(800×70)+ toggle 列 + figcaption;日K = 單張 SVG(1400×320,寬高比更扁)。

→ **窗高一縮 / 五檔改成更高的垂直版式(item 1),`<main>` 溢出會擴大**。
兩件事有耦合:item 1 與 item 5 必須一起設計版面高度分配。見 change-spec Q3。

### Caller map(捲軸樣式)

`index.css` 是全域唯一樣式入口(`main.tsx` import),沒有其他 CSS 檔。
在此加 `::-webkit-scrollbar` 規則 = **全站生效**,會同時影響 TXO / 期貨 / 指數頁的捲軸
(判定為**期望效果**:統一視覺;但屬 scope 外溢,需在 spec 標明)。

---

## 6. 現況 vs 目標 總表

| # | 現況 | 目標 | signature 變動 | Caller 影響 | Backward compat |
|---|---|---|---|---|---|
| 1 | DepthBar 水平 10 格,個股 / 期貨共用 | 個股改 treading-king 垂直雙欄 | 待 Q1 定 | FuturesPage(共用)+ 3 份測試 | 無持久化資料,純視覺 |
| 2 | 舊 server 無 bars route → 404 → 「無 K 線資料」 | 重啟後 K 線出資料 | 無(code 已存在) | 無 | 無 |
| 3 | 圖表 SVG text 可選取,拖曳反白 | 拖曳不選字 | 無(加 class) | 無 | 無 |
| 4 | 預設亮色捲軸 | 暗色主題捲軸 | 無(全域 CSS) | **全站捲軸**(TXO/期貨/指數一併) | 無 |
| 5 | `<main>` 江波圖時溢出 10px 產生捲軸 | `<main>` 恆不捲,只留內層三個 | 版面高度分配需重排 | 個股頁版面 | 無 |

## 7. 不能破壞的既有行為(Phase 2 白名單草稿,待 spec 定案)

1. 五檔點價 → `stock-price-click` CustomEvent → 右欄切閃電 tab + ladder 置中(`OrderBook.tsx:17`、`RightRail.tsx:82-99`)
2. 五檔**不送單**(design §11:誤觸面大);期貨側無 `onPriceClick` 時不得渲染成可聚焦 button
3. 鎖漲停 / 鎖跌停 badge 判定(`b[0][0] === upper` / `a[0][0] === lower`)
4. 檔位不足時不塌陷(補位)
5. 期貨頁五檔可用(不論 Q1 選哪條路)
6. 閃電梯手動捲動暫停跟隨(`PriceLadder.tsx:339 onScroll`)—— 改捲軸樣式不得影響 scroll 事件
7. 明細「載入更多」分頁鈕(`TickTape.tsx:53`)
8. 自選清單拖拉重排把手(`WatchlistSidebar.tsx:259`,已有 `select-none`)
9. 圖表 hover 十字 + tooltip(江波圖 `onMouseMove`、K 線 `onMouseMove`)—— 禁選字不得擋掉 hover
10. 江波圖 CDP / MA / 均價 toggle 與反灰可用性判定
11. K 線模式切換 + `copycat-chart-mode` localStorage 持久化、分 K「往前」載入天數
