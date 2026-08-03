# Phase 1 現況表 — 個股 UI 第四輪(stock-ui-round4)

工作區:worktree `C:\side-project\copycat\.claude\worktrees\mod-stock-ui-round4`,分支 `mod/stock-ui-round4`(base = master `cb9b43b`)。

## Baseline(2026-07-30)

| Gate | 指令 | 結果 |
|---|---|---|
| 後端測試 | `.venv\Scripts\python -m pytest -q` | **1267 passed, 1 skipped**(全綠) |
| 前端測試 | `npm test`(frontend/) | **56 files / 533 tests passed** |

**worktree 陷阱(記一筆)**:`spikes/TCPY/`(TC4 官方 wrapper)在 .gitignore 內 → 新 worktree 沒有它,
`tests/live/test_tc4.py::…dead_port…` 與 `test_tc4_trade.py::…gc…` 兩支會以
`ModuleNotFoundError: No module named 'tcoreapi_mq'` 紅。從主 repo `cp -r spikes/TCPY` 進 worktree 即恢復
(路徑 git-ignored,不進 diff)。**不是 code regression**。

## Caller map(grep 全域,含動態用法檢查)

| 目標 | caller | 動態用法 |
|---|---|---|
| `WatchlistSidebar` | `StockPage.tsx:31` 唯一 | 無(無字串拼接 / 反射式元件名) |
| `StockIntradayChart` | `StockChart.tsx:89` 唯一 | 無 |
| `CandleChart` | `StockChart.tsx:105` 唯一(**期貨 / 指數頁不用它** — 各有 `futures-ladder` / `index-chart-svg`) | 無 |
| `buildIntradayGeometry` | `StockIntradayChart.tsx:319,326`(主圖 + 副圖各一次)+ 自身測試 | 無 |
| `SUB_TOP_PAD` | `StockIntradayChart.tsx:267,273` + `stock-intraday-svg.test.ts:349` | 無 |
| `useChartToggles` | `StockChart.tsx:43`(持 `bb`)+ `StockIntradayChart.tsx:304`(持 `vwap/cdp/ma`) | 無;**每 instance 各一份 state**,`set()` 以重讀 localStorage 為 merge 基底 |
| `bollinger` / `bandSeries` | `CandleChart.tsx:322,325,339,343` | 無 |
| `movingAverage` | `CandleChart.tsx:320,321` + `bollinger.test.ts`(中軌一致性斷言) | 無 |
| `/api/stock/watchlist` GET/PUT | `useStockWatchlist.ts:18,32` ← `WatchlistSidebar` | 無 |

後端側 `copycat/stock_watchlist.py`(v2 groups schema)+ `app.py:416-427`(GET/PUT)為自選唯一持久化路徑;
PUT 成功會 `stock.set_watchlist(union(saved))` 重訂閱池。

## 逐項:現況 vs 目標

### 項 1 — 股票搜尋(代碼 / 名稱 + 提示列)

| | 內容 |
|---|---|
| 現況 | `WatchlistSidebar.tsx:227-242` 單一 `placeholder="輸入股號"` input;Enter / 「新增」→ `input.trim().toUpperCase()` **直接當 code** 寫進群組。零 suggestion、零名稱資料。 |
| 名稱資料現況 | (a) `copycat/stkfut_map.json` code→name,**僅 ~250 檔**(有個股期的標的);(b) `accum.meta.name`(TC4 REALTIME `SecurityName`)— 只有**已訂閱的單檔**才有。**沒有全市場 code↔name 表**。 |
| 目標 | 打代碼或名稱皆可,兩種輸入都出提示列(下拉),選中才加入自選。 |
| 對 caller 影響 | `WatchlistSidebar` 內部 + 新資料源(新 hook / 新 endpoint)。 |
| backward compat | 現有「直接打完整股號 → Enter 新增」必須仍可用(不能強制走選單)。 |
| migration | 無資料遷移;若加 code↔name 表則為新增 JSON cache 檔(git-ignored `data/`)。 |
| **待 user 拍板** | **資料源**(方向性抉擇:對外資料源契約) |

已驗證的候選資料源(本輪實測,2026-07-30):

- `https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL` → **OK,1373 rows**,JSON,含 `Code` / `Name`(上市;不含上櫃)。
- `https://isin.twse.com.tw/isin/C_public.jsp?strMode=2`(上市)/ `strMode=4`(上櫃)→ **兩者皆 OK**(Big5 HTML,7.5 MB / 2.5 MB,31,732 / 10,411 rows,含權證 ETN 需按分類段過濾)。
- `https://www.tpex.org.tw/openapi/...` → **本機 SSL 驗證失敗**(`Missing Subject Key Identifier`),不可用。
- 先例:`copycat/server/mis.py` 已用非契約公開端點(TPEx MIS via `mis.twse.com.tw`),失敗 None 降級。

### 項 2 — 自選群組全列出 + 折疊 + 跨群組拖曳

| | 內容 |
|---|---|
| 現況 | **tab 制**:`activeGroup` state(`null` = 「全部」)+ localStorage key `stock-wl-group`;tab 列 `role="tablist"`(`WatchlistSidebar.tsx:169-226`)。「全部」= `unionCodes` 去重顯示且**停用拖拉**;群組內拖拉 = 同群組 reorder(`onHandleDown`,`lib/list-drag.ts`);換組靠每列 `⊞`(`aria-label="移組 <code>"`)展開 checkbox 面板 → `toggleMembership`(**一檔可同屬多組**)。 |
| 目標 | 所有群組**同時**列在側欄(section 形式,不用 tab),各 section 可折疊 / 展開;可用拖曳把股票從一組移到另一組。 |
| 對 caller 影響 | `StockPage.tsx:31` props 介面預期不變(`active` / `onSelect` / `quotes`);純內部改寫。 |
| backward compat | 後端 schema v2 不動(`{groups:[{name,codes}]}`);多群組成員關係、聯集 30 檔上限、v1 讀時遷移全不動。 |
| migration | localStorage `stock-wl-group`(activeGroup)語意消失 → 需決定忽略或轉為折疊狀態。 |
| **待 user 拍板** | 拖曳語意(移動 vs 複製);「全部」section 去留 |

### 項 3 — 江波圖左緣價位覆蓋走勢線

| | 內容 |
|---|---|
| 現況 | y 軸價位文字畫在 `x={2}`(`StockIntradayChart.tsx:141-153`),而**繪圖區從 x=0 起算**(`stock-intraday-svg.ts:138` `toX` 把 09:00 映到 x=0)→ 文字與走勢線 / 填色重疊。 |
| 目標 | 價位不與線重疊。 |
| 做法 | 左側開 gutter:`toX` 改為映到 `[PAD_LEFT, width]`。牽動 `buildIntradayGeometry`(`toX` / `minuteOf` / `energyBars.x` / `areaPolygon`)+ 元件的模組級 `toX(minute,width)`、`barW`、X_LABELS 垂直線、hover 垂直線(主圖 + 副圖)、水平線 `x1`、疊線 `x1`。 |
| 既有測試影響 | `stock-intraday-svg.test.ts` 多處斷言 x 座標(🔴 該紅);`StockIntradayChart.test.tsx` 有 y-tick / crosshair 斷言。 |

### 項 4 — 左緣價位對應的水平線

| | 內容 |
|---|---|
| 現況 | 只有**整點垂直線**(`X_LABELS` = 09:00/10:00/…/13:00,`stroke-line` `strokeWidth={0.4}`,`StockIntradayChart.tsx:129-139`)+ 平盤虛線(`refY`)。y-tick **沒有**水平格線。 |
| 目標 | 每個左緣價位刻度畫一條同風格淡色水平線。 |
| 做法 | `g.yTicks` 逐條 `<line>`;風格對齊 K 線圖(`CandleChart.tsx:105-113`:`stroke-line` `strokeDasharray="2 3"` `strokeWidth={0.5}`)。 |
| 風險 | 刻度最多 11 條(±10%…0),線密度與紅綠填色的視覺衝突要看畫面確認。 |

### 項 5 — 交易量刻度移到右邊

| | 內容 |
|---|---|
| 現況 | 唯一存在的「量刻度」= 江波圖**內外盤能量副圖**頂端 / 中線兩個數字,畫在 `x={2}` 左緣(`StockIntradayChart.tsx:270-278`,`EnergySub`)。K 線圖的量 bar **沒有**任何刻度文字。 |
| 目標 | 該量刻度移到右緣。 |
| 做法 | `x={w-2}` + `textAnchor="end"`。 |
| **待確認** | 「交易量刻度」是否確指這兩個數字(副圖唯一候選) |

### 項 6 — K 線圖恆顯示布林通道 + 5MA + 20MA

| | 內容 |
|---|---|
| 現況 | MA5 / MA20 **已恆顯示**(`CandleChart.tsx:180-198`,無 toggle);布林通道由 `toggles.bb` 控制,`useChartToggles.ts:15` `DEFAULTS.bb = false`,頂列有「BB」按鈕;`load()` 的 `{...DEFAULTS, ...saved}` 讓**既有 localStorage 存檔覆蓋預設**(刻意不強制升級)。 |
| 目標 | 「都要顯示」= BB 也預設 / 恆顯示。 |
| 對 caller 影響 | `StockChart.tsx:109-110` 傳 `showBb` / `onToggleBb`;移除 toggle 則 props 要改(唯一 caller,無 backward compat 負擔)。 |
| **待 user 拍板** | 移除 BB 按鈕恆顯示 vs 預設開但保留按鈕(後者需處理既有 localStorage `bb:false` 的強制升級) |

## 讀懂現有實作意圖(不可無意識推翻的設計理由)

1. **`toY` / `priceAtY` 共用同一組 `PAD_Y` / `X_LABEL_H`**(`stock-intraday-svg.ts:8-9`)——各自硬編會讓反演只在兩端偏移,目視抓不到。項 3 加 gutter 時 `toX` / `minuteOf` 同理必須共用同一組常數。
2. **`ChartStatic` / `EnergySub` 必 memo,props 必純量**(`w` / `h` 不可傳物件)——hover 每次 mousemove re-render 父層。
3. **`minuteOf` 不 snap 最近分鐘**,無資料 bucket 回 `null`(白名單:hover 空白處不亂指)。
4. **`SUB_TOP_PAD` 是為量刻度文字讓位**——bar 高度分母已扣掉它;項 5 把文字移右緣後這個留邊的理由改變(但仍是頂端刻度的落點)。
5. **`useChartToggles` 每 instance 一份 + 重讀 localStorage 當 merge 基底**——避免兩個持有者互相回滾(實測症狀見 `useChartToggles.ts:30-33`)。
6. **「全部」停用拖拉**是刻意的:union 視圖裡的 index 不對應任何單一群組的 codes 陣列。項 2 拆成 per-group section 後這個限制自然消失。
7. **`removeGroup` 只在 mutation 成功才切走 active tab**(review A2)——失敗時 cache 未動,UI 不該先跳。
