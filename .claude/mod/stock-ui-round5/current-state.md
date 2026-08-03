# Phase 1 現況表 — 個股 UI 第五輪(stock-ui-round5)

工作區:worktree `C:\side-project\copycat\.claude\worktrees\mod-stock-ui-round5`,
分支 `mod/stock-ui-round5`(base = master `f1677bc`,即 round 4 merge 後的 master)。

## Baseline(2026-07-30,round 4 merge 後在 master 上量)

| Gate | 指令 | 結果 |
|---|---|---|
| 後端測試 | `pytest -q` | **1367 passed, 1 skipped** |
| 後端 lint | `ruff check copycat tests` | All checks passed |
| 後端型別 | `pyright` | 0 errors, 0 warnings |
| 前端測試 | `npm test` | **58 files / 643 tests passed** |
| 前端型別 / lint | `npx tsc -b` / `npx eslint src` | exit 0 / exit 0 |
| Replay golden | `copycat validate --run-five … --run-four …` | **42/42 PASS** |

**worktree 陷阱(round 4 已記,本輪重踩確認)**:
- `.venv` 與 `frontend/node_modules` 與 `spikes/TCPY` 與 `out/` 全在 .gitignore → 新 worktree 沒有。
  本輪處置:python 用主 repo 的 `C:/side-project/copycat/.venv/Scripts/python`(cwd 優先,
  `import copycat` 實測解析到 worktree 自己的檔);`npm install`;`cp -r spikes/TCPY`;
  `validate` 用 `--run-five/--run-four` 指向主 repo `out/`。

## Caller map(grep 全域,含動態用法檢查)

| 目標 | caller | 動態用法 |
|---|---|---|
| `TickTape` | `StockPage.tsx:106`(`ticks={accum.ticks}`)唯一 | 無 |
| `TickRow` 型別 | `stock-accum.ts:21,50,76`(`StockAccum.ticks` / snapshot shape)+ `TickTape.tsx:3` | 無 |
| `WatchlistSidebar` | `StockPage.tsx:31`(`active`/`onSelect`/`quotes`)唯一 | 無 |
| `useStockWatchlist` / `useSaveWatchlist` | `WatchlistSidebar.tsx:52,54` 唯一 | 無 |
| `lib/list-drag` | `WatchlistSidebar.tsx:6` 唯一 | 無 |
| `load_watchlist_groups` | `app.py:188`(啟動時建訂閱池)、`app.py:445`(GET) | 無 |
| `save_watchlist_groups` | `app.py:451`(PUT) | 無 |
| `union` | `app.py:188,452`、`stock_watchlist.save_watchlist_groups` 內部(上限檢查) | 無 |
| `validate_code` | `app.py`(overlay/bars/state 路由)、`copycat/stock_names.py:32` | 無 |
| `CandleChart` | `StockChart.tsx:105` 唯一(期貨 / 指數頁各有自己的圖) | 無 |
| `StockIntradayChart` | `StockChart.tsx:89` 唯一 | 無 |
| `buildCandleGeometry` | `CandleChart.tsx:328` + 自身測試 | 無 |
| `buildIntradayGeometry` | `StockIntradayChart.tsx:353,360`(主圖 / 副圖各一)+ 自身測試 | 無 |

後端側 `copycat/stock_watchlist.py` 是自選唯一持久化路徑;PUT 成功會
`stock.set_watchlist(union(saved))` 重訂閱池 —— **訂閱池 = union,所以資料模型一改,
訂閱池的取值來源必須同步改,否則未分組的股票拿不到報價**(本輪最大的隱形接點)。

---

## 逐項:現況 vs 目標

### 項 1 — 當日高低 + 現價小圈

| | 內容 |
|---|---|
| 江波圖現況 | y 軸刻度是 **±10%…0 的固定百分比格**(`stock-intraday-svg.ts` `yTicks`),**沒有**當日最高 / 最低的線或標籤;走勢線末端**沒有**現價點(只有 hover 時該分鐘收盤的黑點 `StockIntradayChart.tsx:519`)。現價只出現在頁面 header(`StockPage.tsx:48-60`)與資訊列。 |
| K 線圖現況 | 視窗高低**已算好**但只印在底部 figcaption 文字(`CandleChart.tsx:416-417,553-564`:`高 {fmt(windowHigh)}` / `低 {fmt(windowLow)}`),圖上**沒有**對應的線或標籤。 |
| 目標 | 江波圖:當日最高 / 最低各一條水平線 + 價位標;走勢線末端一顆漲跌色小圈 + 現價標。K 線圖:視窗最高 / 最低標在圖上(**不加小圈**,user 拍板)。 |
| 資料來源 | 江波圖當日高低:`accum.minutes` 的逐分鐘收盤(`MinuteAgg.c`)—— **注意 MinuteAgg 只存收盤價 `c`,沒有分鐘內高低**,所以「當日最高」= 分鐘收盤的最大值,不是真正的當日最高成交價。真高低要另取(見下)。 |
| **真高低可得性** | `accum.ticks` 只留最近 200 筆(`stock-accum.ts:62` `TAPE_MAX`),不能當全日極值。**後端 `StockDayState` 也沒有存 day high/low**(`stock_state.py` 只有 minutes/vwap/cum_*)。→ 若要真高低,得後端加欄位;若接受「分鐘收盤極值」,純前端可算。 |
| 對 caller 影響 | 江波圖:`stock-intraday-svg.ts` 幾何 + `StockIntradayChart.tsx` DOM。K 線圖:`CandleChart.tsx` DOM(`windowHigh`/`windowLow` 已存在)。 |
| backward compat | 純加繪製元素;`toY`/`priceAtY`/`yTicks` 不動。 |

### 項 2 — 交易量對不到 K 線圖十字軸

| | 內容 |
|---|---|
| 幾何量測(本輪讀 code) | `buildCandleGeometry`(`candle.ts:197-217`)裡蠟燭與量 bar **共用同一組 `x` 與 `w`**(`x = i*slot + (slot-w)/2`);十字線畫在 `hoverCandle.cx = x + w/2` = slot 中心。→ **x 對齊在數學上成立**。 |
| 垂直線長度 | `crosshair-v` `y2={plotBottom}`,`plotBottom = dimH − X_LABEL_H`(元件 `:29` 的 14);量 bar 基線 `bottom = size.height − X_LABEL_H`(`candle.ts:128` 的 14,同值)。→ **線的下端恰好等於量 bar 基線,有穿進量區**。 |
| 縮放映射 | `svgBox`(`chart-frame.ts:46-58`)反解 viewBox 高使 viewBox 比例貼合渲染框 → 無 letterbox;`toSvgPoint` 分軸換算(`chart-crosshair.ts:35-43`)。→ 這條路徑也看不出偏移。 |
| **結論** | **靜態讀 code 找不到根因;與 user 指認的症狀矛盾。** 需要現場證據才能定位。 |
| 蒐證阻塞 | chrome-devtools MCP 的 profile 被並行 session 佔住(`browser is already running`);claude-in-chrome 擴充功能未連線。→ **本輪無法自行開瀏覽器量測**。 |
| 已備妥的環境 | 後端 8721 有一個**舊 build** 在跑(`/api/stock/names` 回 404 = round 4 之前的版本),但 `tc4: "up"` 且 `/api/stock/bars/2330?tf=D` 回真日 K;vite dev server 已起在 **5180**(proxy → 8721)。→ 一旦瀏覽器可用即可直接複現。 |
| 待 user 補 | 截圖 或 精確操作步驟(哪個模式 / 滑鼠在哪 / 什麼跟什麼對不上) |

### 項 3 — 明細欄位與配色

| | 內容 |
|---|---|
| 現況欄位 | `TickTape.tsx:33-57`:**時間 / 成交價 / 單量** 三欄。 |
| 現況配色 | **成交價**依內外盤上色(`outer→text-bull` / `inner→text-bear` / 其他 `text-ink-dim`);單量恆 `text-ink`。 |
| 目標 | 五欄 **時間 / 買價 / 賣價 / 成交 / 量**;三個價格欄依**漲跌**上色;量依**內外盤**上色(內盤綠 `text-bear`、外盤紅 `text-bull`)。 |
| **買賣價可得性** | 前端 `TickRow`(`stock-accum.ts:21-26`)只有 `{t,p,q,side}`,**沒有 bid/ask**。後端 `StockTick`(`stock_models.py:42-52`)同樣沒有 —— 但 **parse 當下拿得到**:`stock_models.py:148`(REALTIME)與 `:173`(歷史 TICKS)都已算出 `bid0`/`ask0` 餵給 `derive_side`,只是沒留存。 |
| 需要動的接點 | `StockTick` 加欄位 → `StockDayState.snapshot()` 的 `ticks` payload(`stock_state.py:136`)→ WS tick 推播 payload(`stock_engine.py:341-349`)→ 前端 `StockTickMsg` / `TickRow` / `applyTick` → `TickTape`。**跨檔契約改動**(REST snapshot + WS 訊息同時加欄位)。 |
| 漲跌基準 | `meta.ref`(參考價)。`TickTape` 目前**沒有拿到 meta** → props 要加。 |
| backward compat | 新欄位 additive;舊 snapshot / 舊訊息缺欄位 → 前端當 `null` 顯示 `-`。 |

### 項 4 — 自選側欄改版

| | 內容 |
|---|---|
| 現況(round 4) | 每個群組一個 `<section>`(`WatchlistSidebar.tsx:268-426`),標題列有 `▾`(折疊)/ 名稱 / 檔數 / `+`(該組新增,展開該組專屬搜尋框)/ `×`(刪群組);每列有 `⋮⋮` 拖拉握把 / `⊞`(展開 checkbox 面板改所屬群組,W-1 一檔多組)/ `×`(從該組移除);底部「+ 群組」;**零群組時**才出現 fallback 搜尋框。**沒有頂部全域搜尋框、沒有未分組概念**。 |
| 現況資料模型 | 後端 v2 `{"groups":[{"name","codes"}]}`(`stock_watchlist.py`);**每檔股票必屬至少一組**,不屬任何組就不存在。上限 30 以跨組聯集計。v1 `{"codes":[…]}` 讀時遷移成單一「自選」組。 |
| 目標(user 拍板) | ① 頂部**恆存**搜尋框(打代碼或名稱出提示列);② Enter / 點提示列 → 股票**持久化進「未分組」層**(重載還在);③ 未分組每列旁 `+` → 群組清單 → 點一個即移進該組(沒有群組時 `+` 停用);④ 未分組也能**拖曳**進群組;⑤ 群組區在下方依序疊,點群組名可折疊 / 展開;⑥ 一顆按鈕開 **Dialog** 統一管理群組與股票,**取代側欄的 `⊞` 面板**。 |
| **資料模型缺口** | v2 沒有地方存「不屬任何群組的股票」。→ 必須改 schema(見 change-spec 的 v3 設計)。 |
| 訂閱池接點 | `app.py:188`/`:452` 用 `union(groups)` 當訂閱池 —— 未分組的股票若不進 union 就**拿不到任何報價**(側欄顯示 `-`)。 |
| 對 caller 影響 | `StockPage.tsx:31` 的三個 props(`active`/`onSelect`/`quotes`)語意與型別**不變**;`useStockWatchlist` 回傳型別改;後端 GET/PUT body shape 加欄位。 |

---

## 讀懂現有實作意圖(不可無意識推翻的設計理由)

1. **`ChartStatic` / `EnergySub` 必 `memo`,尺寸 props 必純量**(`StockIntradayChart.tsx:96`、
   `CandleChart.tsx:93`)—— hover 每次 mousemove 都 re-render 父層,物件 props 的新 identity
   會打穿 memo,重建最多 700 根蠟燭 / 540 個 rect。**項 1 要加的線與圈若放進 memo 層,
   其 props 也必須是純量**。
2. **`minuteOf` 不 snap 最近分鐘**(`stock-intraday-svg.ts`)——無成交的分鐘回 `null`,
   hover 空白處不亂指。項 1 的現價圈是「最後一筆有成交的分鐘」,不可退化成 snap。
3. **hover 存 viewBox 座標不存 index**(`CandleChart.tsx:296-301`)—— 縮放後 index 會指到別根。
4. **MA / BB 以完整序列算完再裁切**(`CandleChart.tsx:318-334`)—— 左緣不斷頭且 y 域不被
   視窗外極值撐開。項 1 的 K 線視窗高低必須取**裁切後的 `shown`**,與現行 `windowHigh/Low` 同源。
5. **`x = i*slot + (slot−w)/2` 蠟燭與量 bar 共用**(`candle.ts:197-217`)—— 兩者對齊是
   建構保證不是巧合。項 2 若真要動 x,兩邊必須一起動。
6. **`useChartToggles` 每 instance 一份 + `set()` 重讀 localStorage 當 merge 基底**
   (`useChartToggles.ts:30-38`)—— 避免兩個持有者互相回滾。
7. **`removeGroup` 只在 mutation 成功才收斂衍生狀態**(`WatchlistSidebar.tsx:119-137`)——
   失敗時 cache 未動,UI 不該先跳。改 Dialog 後這條紀律要跟著搬過去。
8. **落點高亮只能用不改盒模型的樣式**(`WatchlistSidebar.tsx:278-281` 的 `border-accent`)——
   插入佔位元素會撐開版面讓 `getBoundingClientRect` 失效,拖曳落錯組 = 靜默改資料。
9. **拖曳 zone 每次 `pointermove` 重算**(`:150-171`)—— 只在 pointerdown 算一次的話,
   捲動或錯誤文案出現消失都會讓 rect 失效。
10. **`ROW_H = 44` 是 `dropTargetFromPointer` 的插入位置分母**,與列的 `h-11`(44px)
    綁定 —— 改列高必須同步改常數,否則跨組拖曳的落點 index 會偏。
