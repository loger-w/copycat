# Phase 1 — 現況 vs 目標(個股 UI 第六輪 + 管理 Dialog bug)

分支 `mod/stock-ui-round6`,起點 master `2f8c188`。
Baseline:`npm test` **65 檔 / 828 測試全綠**(2026-07-31 11:56)。
無遠端(local-only repo),branch-lifecycle 同步節跳過,收尾走離線 `--ff-only` fallback。

⚠ slug 註記:`.claude/mod/stock-ui-round5/` 是**上一輪已 merge 完成**的殘留 artifact
(HANDOFF 記載 merged 至 master `235f70f`),與本輪無關,不要覆寫。本輪一律用 `round6`。

真實環境證據取得條件:2026-07-31 **盤中 ~12:00**,達錢 4 開啟、server 8721 有資料、
dev server 5174(本輪自起)。側欄自選含 **2327 國巨(鎖漲停 502,+9.97%)**,
是項 2/3/4 的天然實驗標的 —— 這是很難重現的取樣窗,證據優先在收盤前抓齊。

---

## 0. Caller map(grep 結果,含動態用法確認)

| 目標符號 | caller | 動態用法 |
|---|---|---|
| `trianglePoints` / `INTRADAY_MARK` / `CANDLE_MARK` / `markLabelY` / `clampLabelX` | `StockIntradayChart.tsx`、`CandleChart.tsx`、`chart-extreme.test.ts` | 無(全靜態 import) |
| `derive_side` | `copycat/live/stock_models.py` 內兩處(REALTIME / 歷史 row);`tests/live/test_stock_models.py` | 無 |
| `buildLadder` | `PriceLadder.tsx`、`stock-tick.test.ts` | 無 |
| `OrderBook` | `StockPage.tsx`、`OrderBook.test.tsx` | 無 |
| `WatchlistManagerDialog` | `WatchlistSidebar.tsx`、`WatchlistManagerDialog.test.tsx` | 無 |
| `YTick` / `yTicks` | `StockIntradayChart.tsx`、`stock-intraday-svg.test.ts` | 無 |
| `MinuteAgg.u`(灰色量) | 後端 `live/stock_state.py` → WS/REST `"u"` → `stock-accum.ts` → `stock-intraday-svg.ts` `energyBars` → `StockIntradayChart.EnergySub` | 無 |

**回測鏈路獨立性(關鍵,推翻本輪 fable 拍板時的錯誤前提)**
`derive_side` **只**存在於 `copycat/live/stock_models.py`。
回測(`backtest/fade_*.py`、`data/models.py`)用的是 TC4 **1K row** 的
`UpVolume`/`DownVolume`/`UnchVolume`(`Bar1K`),與 `derive_side` 無呼叫關係。
→ 改 `derive_side` **不影響任何回測口徑**。

---

## 1. 項 1|極值標記:三角 → 圓形 + 圖層

**現況**
- `lib/chart-extreme.ts` 匯出 `trianglePoints(x,y,dir,style,bounds)`;`ExtremeMarkStyle` 帶
  `half`(三角半寬)/ `height`(apex→底邊)/ `labelUp` / `labelDown`。
- `INTRADAY_MARK = {half:3.5, height:6, labelUp:{out:5,flip:15}, labelDown:{out:12,flip:10}}`
  `CANDLE_MARK   = {half:5,   height:8, labelUp:{out:6,flip:19}, labelDown:{out:16,flip:12}}`
- 兩個 caller 都畫 `<polygon points={trianglePoints(...)} className="fill-ink-muted stroke-surface">`。
- **圖層(user 抱怨的第二件事)**:`StockIntradayChart.ChartStatic` 內順序為
  `格線 → 平盤填色 → 疊線 → 【極值標記】 → VWAP 線 → 主價線`
  → 主價線(strokeWidth 1.6)壓在標記**之上**。實測 2327 的 `day-high` polygon
  `points="36,4 32.5,10 39.5,10"` 恰在 y 域頂端,被價線與上緣切齊處覆蓋。
- `CandleChart.tsx` 同樣的標記畫在蠟燭層之後?→ 需逐檔確認(見 change-spec)。
- 既有註解明寫「用三角不用圓點:圓點會與現價圈(r=3)、hover 收盤錨(r=2.5)混淆」
  → **本輪 user 顯式推翻**,change-spec 必須記錄推翻理由與新的防混淆手段。

**目標**:圓形標記 + 畫在主價線之上。
**對 caller 影響**:兩個 caller 同步改;`trianglePoints` 改完無 caller → 隨本次移除(已確認無動態用法)。
**backward compat**:純前端顯示,無資料契約,無 migration。

---

## 2. 項 2|內外盤副圖的灰色段

灰色 = `MinuteAgg.u` = 後端 `derive_side` 回 `"neutral"` 的量。判定三行:
`price >= ask → outer` / `price <= bid → inner` / 其餘 → `neutral`。

**盤中實測(2026-07-31 12:00,`GET /api/stock/state/<code>`)**

| 股票 | bid0 | ask0 | 外盤 | 內盤 | neutral | neutral 佔比 |
|---|---|---|---|---|---|---|
| 2330 台積電 | 2395.0 | 2400.0 | 1122 | 949 | 0 | **0%** |
| 2317 鴻海 | 248.5 | 249.0 | 31271 | 17107 | 9404 | 16.3% |
| 6207 雷科 +7.95% | 93.6 | 93.7 | 1018 | 736 | 1618 | 48% |
| 4989 榮科 +9.41% | 55.7 | 55.8 | 61 | 35 | 93 | 49.2% |
| **2327 國巨 鎖漲停** | **0** | 無 | **0** | **0** | 5450 | **100%** |

### 成因 A — 鎖漲停時判定完全失效(硬缺陷,本輪修)

鎖漲停時 TC4 推的簿:`bids = [(0, 15966), (502000, 9385), (501000, 41), …]`、`asks = []`。
`bids[0]` 的價格欄 `0` 是**市價買單佇列**,不是價格。
`parse_stock_realtime` 取 `bid0 = book.bids[0][0]` → `0`;`ask0 = None`(asks 空)。
`derive_side(502000, 0, None)`:ask 為 None 跳過 outer;`502000 <= 0` 為假 → `neutral`。
→ 全日每筆成交判 neutral,`cum_outer = cum_inner = 0`,外盤比分母 0 → 顯示 `-`。

`_parse_levels` 只跳過 `price is None`;`to_milli("0")` 回 `0` 不是 `None`,故 0 檔位被保留。

**對稱風險(推理,今日無實例)**:鎖跌停時 `asks[0]` 會是 `(0, N)` → `ask0 = 0`
→ `price >= 0` **恆真** → 全部判 outer。結果方向碰巧對(鎖跌停成交確為主動買),
但機制是壞的,且「恆真」意味著 bid 側判定被完全短路。

### 成因 B — 價差內成交(時序假影,本輪**不動判定規則**)

4989 的 tape 逐筆拆解:neutral **100%** 屬 `bid < 成交價 < ask`。
- `p=55700 b=55600 a=55800` → neutral
- `p=55700 b=55700 a=55800` → inner

同一個價格,只因為該則 REALTIME 帶的五檔已是**成交後**的簿,就落到不同類。
這是量測時序假影,不是市場結構。修它要換一整套演算法(tick rule),本輪不做。

### 呈現層現況
- 灰段 `<rect className="fill-ink-dim">` 堆在紅(外)綠(內)之上,**無圖例、無文字說明**。
- `figcaption` 只印「累積外盤 X · 內盤 Y · 外盤比 Z%」,對 neutral 隻字不提。
- 外盤比分母 = (外+內),**排除 neutral** 且未揭露。
- 副圖頂端量刻度分母 = 全日最大**總量**(外+內+未分類),round5 E 刻意決策,**不可回退**。

**目標**(user 拍板「修鎖停根因 + 呼應層」)
1. 後端:`derive_side` 的輸入 `bid0`/`ask0` 跳過 `price <= 0` 的市價單偽檔位。
2. 前端:灰段改斜線紋理、`figcaption` 補「未分類 N」與「判定率 W%」,判定率低於門檻時外盤比降對比。

**對 caller 影響**:`book.bids`/`book.asks` **原樣保留 0 檔位**(項 4 要顯示「市價」),
只有餵給 `derive_side` 的 `bid0`/`ask0` 改取「第一個 price > 0 的檔位」。
**backward compat**:WS/REST payload shape 不變(`u` 仍在,值會變小)。
live 狀態不持久化,重啟即重建,無 migration。回測不受影響(見 §0)。

---

## 3. 項 3|漲跌停亮燈(價格 / %數 位置)

**現況**
- `StockPage` header:`{fmt(last.p)}` + `{chg}%`,只有文字色。
- `OrderBook` 標題列 `data-testid="depth-last"` 的成交價 + chg%,只有文字色。
- `OrderBook` 已有「鎖漲停 / 鎖跌停」badge,判定
  `lockedUp = upper !== null && b[0]?.[0] === upper`。
  **實測 2327 沒有顯示 badge** —— `b[0][0] === 0 ≠ 502000`,判定被市價偽檔位打穿(與項 4 同根因)。
- `WatchlistSidebar` 每列有價 + chg%,但 `WatchlistQuote`(`hooks/useStockStream.ts:14-22`)
  **無 `upper`/`lower`** → 前端無從判定漲跌停。

**目標**:成交價 === upper → 該價格 / %數區塊紅底白字;=== lower → 綠底白字。順帶修好 badge 判定。
**對 caller 影響**:`OrderBook` 已收 `upper`/`lower` props;`StockPage` 已有 `meta`。無 signature 變更。
**backward compat**:`upper`/`lower` 為 null(舊後端 / 無漲跌幅商品)→ 不亮燈,退回現況。
**out of scope**:側欄亮燈(需動後端 WS `watchlist_quote` payload)。

---

## 4. 項 4|五檔與閃電梯的 `0` → 「市價」

**現況**
- `OrderBook.BookSide` 直接 `fmt(priceMilli)`;`priceMilli = 0` → 畫面顯示 `0`
  (實測 2327 買1 = `0`,量 15966)。`aria-label` 也是 `買1 0`。
- 該列仍是可點 `<button>`;點了 `emitPriceClick(0,…)` → `PriceLadder` 查無 `rowRefs.get(0)` → **靜默無反應**。
- `buildLadder` 的 `bidMap`/`askMap` 以價格為 key,rows 只涵蓋 `[lowerBound, upperBound]`,
  **`0` 不在其中 → 市價單的量在閃電梯完全不出現**(不是顯示成 0,是根本沒有那一列)。
- `lockedUp` / `lockedDown` 判定被 0 檔位打穿(見項 3)。

**目標**
- 五檔:`price <= 0` 檔位的價格欄顯示「市價」(含 aria-label),該列不可點。
- 閃電梯:`buildLadder` 另回傳 `marketBidQty` / `marketAskQty`(price ≤ 0 檔位的量合計);
  `PriceLadder` 在階梯**最上方**加「市價」列顯示市價買量、**最下方**加「市價」列顯示市價賣量,
  僅該側有量時渲染,不可點價、不可送單。
  位置語意:市價買單優先於任何限價買單 → 價格軸最上;市價賣單優先於任何限價賣單 → 最下。

**對 caller 影響**:`buildLadder` 回傳型別由 `LadderRow[]` 改為物件
→ **唯一 caller 是 `PriceLadder.tsx`**,測試 `stock-tick.test.ts` 同步改。
**backward compat**:`LadderRow[]` 是前端內部純函數,非對外契約。無 migration。

---

## 5. 項 5|分時圖左緣價位軸的漲停 / 跌停刻度亮燈

**現況**
- `buildIntradayGeometry` 產 `yTicks: {y, priceMilli}[]`,由上而下 +10/+8/…/0/…/−8/−10%。
  端點取 `upper` / `lower` **原值**、中央取 `ref` 原值,其餘 snap 到合法 tick。
- `ChartStatic` 畫 `<text data-testid="y-tick-price">`,className 由 `tickTone()` 決定
  (高於平盤紅 / 低於綠 / 平盤白 / 無 ref 灰)。**無背景**。
- 實測 2327:最上 `502`(fill-bull)、最下 `411`(fill-bear)、中央 `456.5`(fill-ink);
  `meta.upper = 502000` / `lower = 411000` / `ref = 456500` — 端點確為漲跌停價。

**目標**:最上(= upper)刻度紅底白字、最下(= lower)刻度綠底白字。**恆亮**,與今日是否真漲跌停無關。
**對 caller 影響**:`YTick` 加選填 `kind?: "upper" | "lower"`;消費者只有 `StockIntradayChart.tsx`。
**backward compat**:additive 欄位;無 upper/lower 的 fallback 分支不標 kind → 不亮燈。

---

## 6. Bug|管理 Dialog 卡在畫面上

**現況 / 重現(已機械重現,非推測)**

`f46cc29` 把 `<dialog>` 的 className 由
`"w-96 max-w-[90vw] rounded border …"`(**無 display utility**)
改為 `"m-auto flex h-[min(30rem,80vh)] w-[min(56rem,92vw)] flex-col overflow-hidden …"`。

UA stylesheet 的 `dialog:not([open]) { display: none }` 屬**瀏覽器層**,
Tailwind 的 `.flex { display:flex }` 屬 **author 層** → author 勝
→ 關閉的 dialog 照樣 `display:flex`。

真瀏覽器實測(dev server 5174,2026-07-31 12:0x):
```
aria-label      : 管理群組與股票
hasOpenAttr     : false
open (property) : false
computed display: flex        ← 應為 none
visibility      : visible
rect            : 896 × 480 @ (352, 62)
```
截圖 `.claude/bug/watchlist-dialog-stuck/before-dialog-stuck.png`:
896×480 的空黑盒子壓在圖表正上方,與 user 描述一致。
內容因 `{open ? … : null}` 未渲染 → 是**空盒子**,更難被理解成「Dialog 開著」。

**根因層級**:CSS 串接層,不是 React 狀態層。
`open` prop 與 `showModal()/close()` 的 effect 邏輯**完全正確**(`hasOpenAttr:false` 證明 `el.close()` 有跑到)。

**為何 828 個測試全綠**:jsdom 26 的 `HTMLDialogElement` 是空 class,且測試環境**不載入 Tailwind CSS**
→ `display` 永遠測不到。既有測試斷言的是「內容有無渲染」,不是「可不可見」。

**目標**:關閉時不佔版面。
**對 caller 影響**:`WatchlistSidebar.tsx` 為唯一 caller,props 不變。
**backward compat**:無。
