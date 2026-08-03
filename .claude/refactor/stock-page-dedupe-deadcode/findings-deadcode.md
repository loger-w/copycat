# 死碼 + 邏輯疑點盤點(Explore agent,2026-08-03)

## 死碼候選

| ID | 信心 | 位置 | 說明 |
|---|---|---|---|
| DC-1 | 高 | stock_engine.py:528-530 | `StockEngineLike`/`AnyDict` 型別匯出零引用(app.py 直接 import StockEngine);連帶 `Any` import |
| DC-2 | 高 | stock_engine.py:189-190 | `watchlist_codes()` 零引用(routes 走 load_watchlist) |
| DC-3 | 僅測試 | stock_watchlist.py:60-63 | `ungrouped()` 僅 tests 用;`union()` 有 prod 用勿並砍 |
| DC-4 | 僅測試 | stock_names.py:75-77 | `parse_isin_html`(無 stats 版)僅 tests;prod 走 _with_stats |
| DC-5 | 高 | stock_models.py:51,218 | `StockTick.buy_sell_flag` 解析後零讀取(不進 snapshot/WS) |
| DC-6 | 僅測試 | stock-intraday-svg.ts:112-113,368-369 | `upperY`/`lowerY`:漲跌停虛線已移除(round3 項 4),計算殘留 |
| DC-7 | 僅測試 | stock-intraday-svg.ts:79,284 | `EnergyBar.total` 零 prod 讀取 |
| DC-8 | 僅測試 | stock-intraday-svg.ts:154,183 | `SideSummary.total` 回傳欄位零 prod 讀取(區域變數 :180 有用,勿並砍) |
| DC-9 | 高 | stock-intraday-svg.ts:206,393-395 | `OverlayLine.kind` 寫入後零讀取(元件走 l.level) |
| DC-10 | 高 | candle.ts:99,221 | `Candle.bar: Bar` 全 repo 零讀取 |
| DC-11 | 高 | candle.ts:85-88 | `export interface Pt` 零引用 |
| DC-12 | 僅測試 | list-drag.ts:3-10,16-19 | `reorder`/`insertIndexFromPointer` prod 已全走 dropTargetFromPointer |
| DC-13 | 僅測試 | watchlist-model.ts:124-141 | `setMembership`:Dialog checkbox 矩陣已改群組視圖 |
| DC-14 | 高 | timeframe.ts:10 | `FUT_KEYS` 零引用(含測試) |
| DC-15 | 契約層 | stock-accum.ts:73,106,131 + stock_engine.py:185-186 | `stkfut_prod`/`stkfutProd` 後端送、前端存後零讀取(期現價差走 WS stkfut.prod) |
| DC-16 | 契約層 | stock-accum.ts:50 + stock_state.py:209 | `meta.y_close` 後端送、前端零讀取 |
| DC-17 | 僅測試 | stock-accum.ts:64-65,120-121,166-167 | `cumInner`/`cumOuter` 前端全鏈維護但零 prod 讀取(round6 改走 sideSummary) |
| DC-18 | 契約層 | stock-accum.ts:71-72,104-105,129-130 | `accum.tc4`/`backfilling` 零讀取(畫面走 WS status) |
| DC-19 | 僅測試 | quote/DepthBar.tsx:23,36,48-60,109,150 | `onPriceClick` 整條路徑:唯一 prod 消費者 FuturesPage 不傳 |
| DC-20 | 高 | WatchlistSidebar.tsx:89,197-201,215 | `drag.index` 寫入多處零讀取(落點只讀 drag.to/code;插入 index 是 up 時現算) |
| DC-21 | 僅測試 | useStockBars.ts:35 | `inTradingHours` 相容 re-export 僅測試 import |
| DC-22 | 中 | TickTape.tsx:15 | `priceTone` 的 export 無外部消費者(函式同檔用 3 次,只是多餘 export) |

## 邏輯疑點

[safe] = 可零行為差修:
- L-1 StockIntradayChart:502-505:副圖跑完整 buildIntradayGeometry 只吃 energyBars/maxTotal(同值算兩次)→ 抽 buildEnergyBars
- L-2 CandleChart:398 vs 411-418:bandSeries 每輪算 4 次 → 幾何 memo 一併回傳
- L-3 StockIntradayChart:539,558-559:hoverAgg/shownAgg 取同一格
- L-4 OrderBook:159-165:limitOnly 四趟 filter → 區域變數
- L-5 stock_source:374,385-386:backfill 首頁抓兩次 — **需先驗 QryIndex 游標語意,本輪跳過**
- L-10 stock_source:279-282:docstring 與實作窗不符 → 只改 docstring
- L-11 = 後端 B-D1(fetch_day_minutes 重抄 _taipei_minute_key)
- L-12 stock_engine:395:to_milli 函式內 late import 無必要 → 併檔頭
- L-13 stock_engine:82,236:_resub_task 持有防 GC 但意圖未寫 → 補註解(關機取消是行為變更,另記)
- L-15 WatchlistManagerDialog:129:nameOf O(列數×2401)→ 同側欄 Map memo(輸出逐值同)
- L-16 CandleChart:424-437:滾輪 useEffect deps 與閉包不符 → 補 dimW/dimH(當前值不變)
- L-18 stock_engine:355:stage2 後重讀 self._states 是 no-op → 刪或註解
- L-19 StockIntradayChart:774-784:副圖 hover 線用 mainW 畫進 subW viewBox(今日同值)→ 改 subW
- L-20 stock_models:174-178:price None 早退前白算 vol → 移序

[behavior] = 只記錄,本輪不修(→ docs/next-time.md):
- L-6 ref=0 時 `??` 不退回首筆成交(autofit 畫壞);StockPage/OrderBook 用 truthy 判,不一致
- L-7 前端增量 VWAP 用 cum_vol 當分母,後端分母是去重後 Σqty → 靜默分歧至下次 refetch
- L-8 apply_backfill 兩迴圈去重不對稱且無註解(本輪只補註解,不對齊)
- L-9 /api/stock/bars tf=D 忽略 days 但仍對 days 做 400 驗證
- L-14 DepthBar 仍用 `b[0][0]===upper` 判鎖停(市價佇列 0 價會打穿;期貨面尚未觀測到)
- L-17 TickTape limit state 切股不歸零 + 每 render reverse 200 列
- L-21 契約盈餘(names.count / bars.code/tf)刻意公開,不動

## 契約總結
後端送前端不讀:stkfut_prod、meta.y_close、cum_inner/cum_outer、snapshot.tc4/backfilling、
names.count、bars.code/tf。前端讀後端不送:無。WS 五種訊息欄位雙向對得上。
