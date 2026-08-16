# current-state — 群組圖牆分時圖改單檔同款 + 點卡片不跳單檔(R4)

來源 prompt:`docs/superpowers/specs/2026-08-15-user-feedback-batch2-rounds.md` §2 R4。
Baseline(2026-08-16 22:27,master 6a31af57):frontend vitest 113 files / 1872 passed;
backend `pytest tests/live/test_stock_state.py tests/server` 1125 passed。

## 1. 元件 / 資料 現況(以 grep 實查為準)

| 項 | 現況 |
|---|---|
| 圖牆卡片圖 | `frontend/src/components/stock/MiniIntradayChart.tsx`(195 行):`MINI_W=220/MINI_H=76`,只畫平盤虛線 + 紅綠面積 + 價線;`preserveAspectRatio="none"` + `non-scaling-stroke`;`extendMinutes(minutes, liveP)` 用本機時鐘把 `watchlist_quote.p` 延伸成末點。**唯一 caller** = `GroupGridView.tsx:3,143`;測試 `MiniIntradayChart.test.tsx`(extendMinutes + 幾何補償)、`GroupGridView.memo.test.tsx:21`(`vi.mock` 該模組當計次替身)、`GroupGridView.test.tsx:386-411`(查 `[data-testid="mini-price"]` points 數驗延伸接線)。動態用法 grep(`MiniIntradayChart`)只有上列 5 處,無 lazy import / 字串引用。 |
| 單檔分時圖 | `StockIntradayChart.tsx`(1009 行):`Props {accum: StockAccum; mainHeight?; subHeight?; stkfut?}`;內部 `useChartToggles()`(:616)、`useStockOverlay(accum.code, !stkfut && !isInstrumentKey && (cdp||ma))`(:631)、`ChartStatic` memo(VWAP/CDP/MA/VP+POC/高低點/軸/亮燈)、`XAxisLabels`、`EnergySub` 副圖、hover 十字/price-tag/time-tag、`ChartReadout` 六欄、toggle 四鈕(:775-810)、figcaption 說明列(:982-1006)。viewBox 寬固定 `MAIN.width=800`/`SUB.width=800`,高度由 `StockChart.tsx:120-125` 以 `useContainerSize`+`svgBox`(chart-frame `CHART_FRAME` 假設 figure `p-4`+border+頂列+底列)反解後傳入。文字 fontSize 用 rem → 實際字高 = rem × (渲染寬 / 800);單檔頁渲染寬 ≈ 800-1100px 故可讀;若直接掛進 250px 卡片,縮放 0.31× 字高 ≈ 3px 不可讀。 |
| toggle 狀態 | `hooks/useChartToggles.ts`:每 instance 各持一份 state,`load()` 讀 localStorage `CHART_TOGGLES_KEY`,`set()` 先重讀合併再寫(:78-86);單檔頁同時活兩份(`StockChart.tsx:61` 持 bb、`StockIntradayChart.tsx:616` 持 vwap/cdp/ma/vp)。IndexPage 走「上提到頁面、props 下傳」樣板(`IndexPage.tsx:108` → `MarketPane` `toggles` prop)。**16 個 instance 同時掛的競態面**:各 instance 的 `toggles` 只在自己 `set()` 時更新,別的 instance 寫 localStorage 不會通知它 → 圖牆若每卡各持一份,只有被點的那張會變。 |
| 群組資料 | `hooks/useGroupSnapshots.ts`:`GET /api/stock/group-state?codes=`,60s 輪詢(盤外停),payload 每檔 `{minutes, meta, no_data, backfilling}` → `GroupSnapshot`;後端 `stock_engine.py:572 group_snapshot` → `stock_state.py:199 light_snapshot()` **只有 minutes/meta**(設計刻意剔 ticks)。**單檔圖需要而群組沒有的欄位**:`vwap`(後端 `vwap_milli` 現成)、`high/low`(現成)、`last`(現成)、`vp`(後端無;前端 `stock-accum.ts:123 foldVp` 從全量 ticks 折:剔 `p<=0`、分鐘窗 [540,810]、key=`snapDown(p)`,cell `{t,o,i}`)、`code`。 |
| tick 表 | 前端 `lib/stock-tick.ts` `TICK_TABLE`(floor 含)與後端 `market.py::_ZONES`(upper 不含)於邊界等值(1_000_000 → 5_000 兩邊一致);後端無 `snap_down`,只有 `tick_size_milli`。 |
| overlay | `hooks/useStockOverlay.ts`:`["stock-overlay", code, ymd]` staleTime Infinity、retry 1;後端 `/api/stock/overlay/{code}` 有 cache + 已完成 bar 剔除 / don't-cache-empty。同 code 的單檔頁與卡片共用 TQ cache。 |
| 點卡片鏈 | `GroupGridView.tsx:106-147 GroupCard`(memo,button,`aria-label="查看 <code> <name>"`,`onClick={()=>onPick(code)}`);:162-166 `pickRef` 穩定化 → `StockPage.tsx:218-222 onPick = (picked)=>{onSelect(picked); selectView("single")}` → `App.tsx:106 stockCode` → `railCtx.code`(:177-190)→ RightRail ladder;`useStockStream` 打 `/api/stock/state/{code}`(set_main)。GroupGridView **不知道**目前主檔(無 `active` prop);StockPage 手上有 `code`。 |
| 檢視記憶 | `StockPage.selectView` 寫 `STOCK_VIEW_KEY`;pill 在 `code===null`/`accum===null` 分支之外(R6)。 |
| 矩陣佈局 | `GroupGridView.gridShape`(PR #50):≤16 → 2×2~4×4 `minmax(8rem,1fr)` 列軌佔滿中區;>16 → 4 欄 auto 列(內容高)+ `content-start` 捲動。卡片內圖 `h-20 grow`。 |
| 既有測試 | `StockPage.test.tsx:691-701`「點卡片 → onSelect 該股 + 自動切回單檔檢視」(**該紅**);`GroupGridView.test.tsx:418-427`「整張卡片是 button,點了回呼」(**保留**);`GroupGridView.test.tsx:388-416`「盤中且 quote 有現價 → mini 圖比 snapshot 多一個延伸點」(靠 `mini-price` testid,**換元件後 selector 該改**,行為契約保留);`GroupGridView.memo.test.tsx`(mock `MiniIntradayChart` 計次,**mock 目標該換**);`MiniIntradayChart.test.tsx`(元件退役 → extendMinutes 測試需搬家,幾何補償測試隨元件刪);`App.test.tsx:206-268` 有「點列 → 打 /api/stock/state/1101 + localStorage main code」的全鏈樣板可套。 |

## 2. 現況 vs 目標

| 面向 | 現況 | 目標 | caller 影響 | backward compat |
|---|---|---|---|---|
| 卡片圖內容 | 純線 + 面積 | 與單檔同款(VWAP/CDP/MA/VP+POC/高低點/軸/hover 讀值/現價圈/副圖量能) | GroupGridView 換掛元件;MiniIntradayChart 退役 | 無對外契約 |
| 卡片圖尺度 | 220×76 viewBox 非等比拉滿 | viewBox 1:1 像素(量測容器)使 rem 字級可讀 | StockIntradayChart 需接受 `mainWidth`/量測 | 單檔頁維持 800 寬 + StockChart 反解高(不變) |
| toggle | 每 instance 一份 | 圖牆一份(GroupGridView 上提)+ toggle 列在圖牆頂;卡片以 props 接收 | StockIntradayChart 需受控模式(toggles/onToggle props);單檔頁仍自持 | localStorage key / schema 不變 |
| 群組 payload | minutes/meta | + `vwap`/`high`/`low`/`last`/`vp`(後端折)| `light_snapshot` 加鍵;前端 `GroupSnapshot` 加欄 | 加鍵 additive;前端 `?? null` 降級舊後端 |
| 點卡片 | onSelect + 切單檔 | 只 onSelect;檢視停群組;卡片選中態 | StockPage onPick 改;GroupGridView 加 `active` | 無 |
| 進單檔 | 點卡片 / pill | 只靠 pill(D3) | — | — |

## 3. 已知風險 / 邊界

- 16 卡 × overlay = 16 請求(只在 cdp/ma toggle 開時,TQ per-code+日 cache Infinity,後端 cache)→ verification 量測。
- 群組 payload 大小:vp 每檔最多數百檔位(autofit 低價股近千)× 50 檔 / 60s → verification 量測 gzip 前後 bytes。
- 卡片資料節奏 = 60s snapshot + 每秒 `liveP` 末點延伸(現行設計 R10),VWAP/VP/高低 60s 才更新 — 與單檔頁(WS 逐 tick)不同,是資料面差異不是渲染差異;change-spec 明列。
- `useContainerSize` 呼叫端契約:被量元素高度須由外層 flex 指派;>16 檔分支列軌 auto(內容高)→ 卡片需給固定高才不形成量測迴圈。
