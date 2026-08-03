# Phase 1 — 現況盤點(個股 UI round 4)

分支 `mod/stock-ui-round4`(worktree `.claude/worktrees/mod-stock-ui-round4`,自 master c409cb1)。

## Baseline 測試(2026-07-30)

| 套件 | 指令 | 結果 |
|---|---|---|
| frontend | `npm test -- --run` | **744 passed / 64 files**,9.10s |
| backend | `.venv\Scripts\python -m pytest -q` | **1447 passed, 4 skipped**,40.97s |

兩者皆綠 = baseline 成立。

---

## 1. 目標項對應的現況

### 項 1 — 分時圖 / K 線圖的最高最低價

**分時圖(`frontend/src/components/stock/StockIntradayChart.tsx:230-261`)**
- 現況:`accum.high` / `accum.low`(當日 tick 級 running max/min,後端給)→ `inDomain()`
  過濾域外 → 畫**整條橫向虛線**(`strokeDasharray="4 3"`, `strokeWidth=0.8`,
  `data-testid="day-high"` / `day-low`)+ 右緣(`x = w - R_AXIS_W + 2`)價位文字
  (`data-testid="day-high-label"` / `day-low-label`)。
- 資料源:`copycat/live/stock_state.py:106-109` 逐 tick running max/min → `snapshot()`
  top-level `high`/`low`;WS tick 訊息也帶 `h`/`l`(`stock_engine.py:346` 註解)。
- **缺**:高低發生在「哪一分鐘」沒有任何資料 —— `MinuteAgg`(後端 `stock_state.py:20-26`
  與前端 `lib/stock-accum.ts:20-26`)只有 `c/v/i/o/u`,**無 per-minute high/low**。

**K 線圖(`frontend/src/components/stock/CandleChart.tsx:113-146`)**
- 現況:`windowHigh/windowLow` = 當下可視窗口 `shown` 的 `max(b.h)` / `min(b.l)`
  → 同款**整條橫向虛線**(`window-high` / `window-low`)+ 右緣 `textAnchor="end"` 文字。
- 值本身已經是「當下視野中的最高最低」= 目標行為;**要改的只是呈現(虛線)**。
- ⚠ `CandleChart` **共用給指數頁**(`components/index/MarketChart.tsx:146`)—— 這次
  呈現改動會同時作用在指數 K 線上。

**參考實作(treading-king `frontend/src/lib/intraday-chart-svg.tsx:149-166, 436-448`)**
- `todayHigh` 取 **candle.high**(分鐘聚合,含同分鐘 tick 波動)不是 close,
  同時記 `todayHighIdx`。
- 畫法:在 `(scaleX(minute), scaleY(todayHigh))` 畫 **r=2.5 小圓點** + 其上方 6px 的
  價位文字,**沒有橫線**。顏色走 `priceColor`(相對 baseline 紅綠)。

### 項 2 — 分時圖即時價位文字

`StockIntradayChart.tsx:595-610`:`last-dot`(圓點)+ `last-price`(文字,畫在圓點右上
`x+5, y-4`)。文字有機會與右緣疊線價位標(`R_AXIS_W` 帶)重疊 → 要刪文字留圓點。

### 項 3 — hover tooltip 加價位

`StockIntradayChart.tsx:661-682`:底部時間標 `time-tag`(34×13,`fill-bg-deep stroke-line`)
內含 `time-tag-text` = `hhmm(hoverMin)`。左緣另有 `price-tag`(自由量尺價位,跟滑鼠 y)。
**缺**:時間標下方沒有「該時刻股價」。該分鐘收盤價可由 `accum.minutes.get(hoverMin).c` 取得
(資訊列 `shownAgg.c` 已在用)。

### 項 4 — 自選功能

**(a) 管理 Dialog**(`WatchlistManagerDialog.tsx`)
- `<dialog>` + `showModal()`,className `w-96 max-w-[90vw]`(384px 窄長條)。
- 版面 = **上下兩段**:上「群組」(list + 改名 / 刪除 + 新增群組輸入),
  下「股票」(`wl.codes` 全體,每列 code / name / **每個群組一個 checkbox** / 移除)。
- `<dialog>` 原生 `showModal()` 本來就置中,但 `w-96` 對「左群組右股票」太窄。
- 測試:`WatchlistManagerDialog.test.tsx`(SC-13 開關 / SC-14 群組管理 / SC-14 股票管理)。

**(b) 群組折疊**(`WatchlistSidebar.tsx:426-439`)
- 只有 header 左側 `▸/▾` **按鈕**可折疊(`aria-label="展開/折疊 <name>"`),
  header 其餘區域無 onClick。未分組區塊同款(`:378-391`)。

**(c) 搜尋流程**(`WatchlistSidebar.tsx:128-140, 325-362`)
- `add()` → `commit(addCode(wl, code))` = **搜尋 Enter / 點「新增」/ 點提示列 → 立刻
  寫進自選(落未分組)**。
- 沒有「先預覽再決定加哪一組」的路徑。
- 主圖選檔靠 `onSelect(code)` → `App.tsx:168` `setStockCode`;
  `/api/stock/state/{code}` 內含 `set_main` → **非自選股也能被訂閱與看盤**(預覽可行)。

**(d) 自選列的名稱 / 價位 / 漲幅**(`WatchlistSidebar.tsx:218-260`)
- 列只印 `code`(`w-14 font-mono text-sm`)+ 價 + 漲幅;**沒有名稱欄**
  (`useStockNames()` 已在本檔取用,只餵搜尋提示列)。
- 價 / 漲幅來源 = `quotes[code]`(WS `watchlist_quote`)。
  後端 `stock_engine.py:437-460` `_flush_watchlist_loop`:**只推 `_dirty_watchlist`
  (= 有新 tick 的檔)**,且 `state.last is None` 直接 `continue`。
  → **開頁 / 盤後完全沒有種子推播,側欄全 `-`**。
  已知問題,`docs/next-time.md` 2026-07-21 條目:
  「盤後重載側欄顯示 "-" 而非昨收靜態值(需 snapshot 種子側欄)」。

### 項 5 — 字體大小

自選列:`code` `text-sm`(0.875rem)、價 `text-sm`、漲幅 `text-xs`(0.75rem)。
`StockPage` header 已是 `text-lg`。

### 項 6 — 分時圖左緣價位帶

`lib/stock-intraday-svg.ts:36` `Y_AXIS_W = 46`(註解說「取 46 = 元件的 `PRICE_TAG.w`」)。
`StockIntradayChart.tsx:179-187` 價位文字 `x={2}`(**靠最左**)、`fontSize="0.625rem"`、
`y={clamp(t.y - 2, 8, h-16)}`(baseline 在格線上方 2px = **不置中對齊**)。
→ 三個症狀:離走勢圖遠(帶寬 46 且文字靠左)、與格線沒對齊(baseline 偏移)、字偏大。
`PRICE_TAG.w = Y_AXIS_W` 綁死(`StockIntradayChart.tsx:33`),縮帶寬會連帶縮 hover 價位標。

---

## 2. Caller map(含動態用法)

| 目標 | Caller | 影響 |
|---|---|---|
| `StockIntradayChart` | `StockChart.tsx:89`(唯一) + 自身 test | 低 |
| `CandleChart` | `StockChart.tsx:105`、**`components/index/MarketChart.tsx:146`** + 自身 test | **跨頁**:指數 K 線同步變 |
| `WatchlistSidebar` | `StockPage.tsx:31`(唯一) + 自身 test | 低 |
| `WatchlistManagerDialog` | `WatchlistSidebar.tsx:470`(唯一) + 自身 test | 低 |
| `Y_AXIS_W` / `R_AXIS_W` | `stock-intraday-svg.ts` 內部 (`minuteToX`/`plotWidth`/`minuteOf`)、`StockIntradayChart.tsx`(9 處)、`StockIntradayChart.test.tsx`(x1/x2/寬度斷言 6 處) | 常數改值 → 測試斷言隨動(測試已用符號不用字面 46,除 `:274` 註解) |
| 前端 `MinuteAgg` | `stock-accum.ts`(fromSnapshot/applyTick)、`stock-intraday-svg.ts:121`、`stock-intraday-svg.test.ts:16` | 加欄位為 additive |
| 後端 `MinuteAgg` | `stock_state.py` 內部唯一(`_apply` / `snapshot`) | 加欄位為 additive |
| snapshot `minutes` 契約 | 前端 `fromSnapshot`;`tests/live/test_stock_state.py:80` | additive 相容 |
| `watchlist_quote` WS 型別 | 前端 `useStockStream.ts:148-157`;後端 `stock_engine.py:293`(no_data)/ `:454`(正常) | 加種子推播 = 同型別多發幾則,無契約改動 |
| 動態用法掃描 | `grep -rn "stock/state\|watchlist_quote\|day-high\|last-price\|window-high"` 已掃;**無** template string / reflection 拼接元件名或 testid | — |

## 3. 既有實作意圖(為什麼現在長這樣)

- **虛線高低線**(round5 SC-1):當初刻意用 `4 3 / 0.8` 與 y 軸格線 `2 3 / 0.5` 區分,
  且**域外不畫**(無漲跌停時 y 域由分鐘收盤極值決定,裝不下逐筆極值)。
  → 改成「點 + 標」後,域外規則仍要保留(逐筆高低可能超出分鐘收盤域)。
- **`Y_AXIS_W = 46`**:round4 項 3 讓出左緣帶避免價位文字壓在走勢線上;46 是為了讓
  hover 價位標(`PRICE_TAG.w`)整格塞進帶內。
- **`_flush_watchlist_loop` 只推 dirty**:1s 節流合併(design §2.4),避免每 tick 廣播。
- **`addCode` 立刻 PUT**:round5 §🟢-7 的 v3 schema,`codes` = 訂閱池 —— 加進自選 = 訂閱。
- **`commit()` 零 PUT 早退**:內容相同的 PUT 會讓後端重設整個訂閱池(TC4 全量 UNSUB/SUB)。
