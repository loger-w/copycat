# Phase 7 — SC 結構化證據表(2026-07-21)

Fresh gate(本 phase 內重跑):pytest **730 passed** / ruff 0 / pyright 0 / `copycat validate` **42/42** / vitest **102 passed** / tsc 0 / eslint 0 / `npm run build` exit 0。

| SC | 實作檔案 | 自動化測試 + pass | real-env 證據 | regression 抽樣 |
|---|---|---|---|---|
| SC-1 自選(增刪/拖拉/持久化/上限30) | copycat/stock_watchlist.py、server/app.py(routes)、frontend components/stock/WatchlistSidebar.tsx、lib/list-drag.ts | test_stock_watchlist.py 7、test_stock_routes.py::TestWatchlistRoutes 4(含重啟保留)、WatchlistSidebar.test.tsx 4、list-drag.test.ts 5 | 盤中實操新增 2330/5483/2317 + server 重啟與頁面重載後清單保留(SC-2 截圖左欄) | TXO tab 功能不動:test_app.py 全綠 + 首頁截圖 TXO series 選單正常 |
| SC-2 側欄即時報價 | server/stock_engine.py(1s 節流)、hooks/useStockStream.ts | TestStreamAndStatus 3、useStockStream.test.ts 7 | evidence/SC-2-3-4-5-6_2330-main-view-live.png;三次 a11y snapshot 價格跳動(2395→2400→2390) | 5483(上櫃冷門)與 2317 同時跳動 |
| SC-3 江波圖(價/VWAP/昨收/漲跌停/量/回補) | live/stock_state.py、frontend lib/stock-accum.ts、lib/stock-intraday-svg.ts、StockIntradayChart.tsx | test_stock_state.py 10、stock-accum.test.ts 4(後端等值)、stock-intraday-svg.test.ts 6、StockIntradayChart.test.tsx 2 | 同上截圖:中途啟動回補 6,064 ticks 全日曲線 + VWAP 金線 + 量 bar(server log `stock backfill 2330: 6064 ticks`) | 2330/5483 兩檔切換皆全日 |
| SC-4 五檔(位移歸一) | live/stock_models.py(_parse_levels)、components/stock/OrderBook.tsx | test_stock_models.py 11(位移對映真樣本)、OrderBook.test.tsx 3 | 同上截圖:賣1-5/買1-5 價量 + 量能 bar;5483 的 0.5 元檔位正確 | 非整數價位(219.5)格式化正確 |
| SC-5 明細(內外盤色/回補銜接) | live/stock_models.py + stock_state.py(TradeVolume 去重)、TickTape.tsx | dedup/交接 5 案例、TickTape.test.tsx 2 | 同上截圖(逐筆紅綠)+ EDGE-2 截圖(13:24:59 → 13:30:00 收盤撮合 945 張無縫) | 載入更多分頁 |
| SC-6 內外盤能量副圖 | stock_state.MinuteAgg、stock-intraday-svg energyBars | minute_agg 測試、svg energy 測試 | 同上截圖:副圖雙色 bar + 累積外盤比 61.4%/45.3% | 兩檔外盤比皆合理值域 |
| SC-7 期現對照 | copycat/stkfut_map.py(268 檔)、stock_engine stkfut 路徑(F: 鍵) | test_stkfut_map.py 7、TestStkfut 3 | evidence/SC-7_stkfut-basis-header.png:CDF 2403 價差 +8;5483 → NOF 價差 0 | SecurityName 交叉核對 warning(caplog 測試) |
| SC-8 上櫃股 | live/stock_source.stock_symbol(TWS 段,spike 實證) | probe + test_stock_source symbol 測試 | evidence/SC-8_5483-otc-main-view.png:中美晶完整主視圖 | 側欄同列上市/上櫃混排 |

## Edge cases

| Edge | 證據 |
|---|---|
| 1 無效股號健檢 | test_stock_source 健檢 3 案例(盤中 10s 觸發/推播取消/盤外不觸發);修復前 real-env 曾實際觀測到 no_data 灰顯(聽器 bug 期間) |
| 2 試撮 | **EDGE-2 截圖**:真試撮期零筆 + 13:30:00 收盤撮合正確收;probe:試撮期 TC4 不推成交、TradeStatus 值域 {0,1} |
| 3 漲停空側 | test_stock_models 空 Ask 案例 + OrderBook.test.tsx 「—」案例(盤中無漲停股可拍,單元測試覆蓋) |
| 4 斷線/自癒 | TestStreamAndStatus reconnect 測試 + generation listener 繼承 07-20 已實證路徑(不主動拔 user 的 TC4 演練) |
| 5 除權息 ReferencePrice | test_stock_models meta 案例(昨收基準一律取 ReferencePrice) |
| 6 上限/冪等 | test_stock_watchlist 超限/重複案例 + routes 400 契約 |

## Known Risks 殘留(帶入 PR 描述)

- R2 側欄不回補歷史(design 明載,可接受)。
- R4 個股期 HOT 轉倉語意待首次轉倉週實測。
- R6 過期窗跨日推播行為未實測(rollover 已設計為不依賴)。
- rollover 兩段式的真實跨日行為:單元測試覆蓋,首個真實跨日(明晨 08:00)為最終實證。
