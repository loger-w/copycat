# Phase 7 — goal 核對(重讀 brainstorm.md 後逐 SC 對表)

日期:2026-08-05。HEAD:1b95d89。brainstorm.md 全文重讀(含三處 amendment:SC-3 量法 /
SC-11 口徑 / SC-12 星期測點 / edge case 3 取捨)。

| SC | 實作檔案:行號 | 自動化測試 + pass count | real-env 證據路徑 | regression 抽樣對象 |
|---|---|---|---|---|
| SC-1 近全分時圖 | `frontend/src/components/futures/FuturesChart.tsx:114`(IntradayChart)+ `frontend/src/lib/allday.ts:39,125` | `allday.test.ts` + `FuturesChart.test.tsx` 分時 describe(vitest 全套 1290 passed) | 截圖: `evidence/SC-1_intraday-allday-axis.jpg`、`SC-1_deadzone-continuity-zoom.png`(polyline 745 點,299/300 相鄰無空洞)+ user 過目 | 大盤 tab MarketChart 掛載正常(fixture 巡檢) |
| SC-2 K 線多週期 | `frontend/src/lib/fut-chart-mode.ts` + `FuturesChart.tsx:239` + `lib/candle.ts` aggregateBars | `fut-chart-mode` / `candle.test.ts`(24:00 正規化、跨月年)/ FuturesChart 模式切換持久化(1290 passed) | 截圖: `evidence/SC-2_m5-candle.jpg`、`SC-2_mode-persisted-after-reload.jpg`(localStorage m5 保留)+ user 過目 | 個股頁 ChartMode 值域不變(既有測試) |
| SC-3 夜盤貫通 | `copycat/live/futures_source.py:34,128` + `copycat/live/stock_source.py:201`(_taipei_dt_key)+ `copycat/server/bars.py:422` + `copycat/server/app.py:894` | `test_futures_bars.py`(allday 段界七列 + 窗字串跨月年)+ `test_stock_bars.py` 多段 class + `test_bars.py` session 隔離 + `test_market_routes.py` TestSessionParam(pytest 1795 passed) | `evidence/SC-3_route-validation.txt`(新 sha health / 400 值域);真 TC4 量法 `infra_fail: 夜盤進行中不可起第二台 TC4 後端`(= state.json phase_6_blocked_reason;merge 後 prod 重啟跑量法 curl + user 過目) | 個股 bars 既有測試綠;`copycat validate` 42/42 |
| SC-4 商品同步 | `FuturesChart.tsx:239`(product prop)+ App 既有 state | FuturesPage.test「換小台改抓 MXF bars」(1290 passed) | 截圖: `evidence/SC-4_switch-to-MXF.jpg`(bars_range MXF log + 閃電梯 MXFH6 同步)+ user 過目 | 閃電梯換商品解除武裝(既有測試) |
| SC-5 期現價差 | `FuturesPage.tsx:40` + `frontend/src/lib/spot-session.ts` | FuturesPage.test 價差三態 + 夜間假價差(twse stale:false 夜間 → 「價差 —」)(1290 passed) | 截圖: `evidence/SC-5-6_header-spread-settlement-zoom.png`(夜間顯示「價差 —」= 正確降級)+ user 過目 | IndexBar 顯示不變 |
| SC-6 結算倒數 | `frontend/src/lib/settlement.ts` + FuturesPage badge + `FuturesLadder.tsx` T-0 警示列 | settlement.test(第三週三/跨月/T-0/已過→0)+ ladder T-0 測試(1290 passed) | 截圖: 同上(「結算 T-10」,agent 獨立核算 8/6..8/19 平日數一致)+ user 過目 | — |
| SC-7 持倉均價線 | `FuturesChart.tsx` overlays useMemo(契約完整字串相等) | FuturesChart.test overlays(m1)+ 分時 overlay(review TC-2 補)(1290 passed) | 截圖: `evidence/SC-7_avg-price-line-injected-position.jpg`(fetch override 注入 TXFH6 → 「均 43850 多2口」)+ user 過目 | CapitalPositionsList 既有 9 測試零改動 |
| SC-8 內外盤副圖 | `stock_source.py` uv/dv + `candle.ts` deltaVol + `CandleChart.tsx:117` volumeDelta | test_stock_bars uv/dv 累加 + candle.test deltaVol 對位/null + CandleChart 雙柱/回退 + route uv/dv 直通(review TC-7 補)(雙套件全綠) | 截圖: `evidence/SC-8_volume-delta-zoom.png`(240+240 rect 紅綠並列)+ user 過目 | CandleChart 既有 38 條原文未動;指數無量回退量柱(測試) |
| SC-9 掛單(既有迴歸) | 既有 `splitMyLots` / `cancelLot`(零改動) | FuturesLadder 既有 14 條逐字未動、全綠 | 截圖: `evidence/SC-10_close-cancel-disabled-zoom.png` 同框可見梯 + user 過目 | 同左 |
| SC-10 全撤/平倉 | `FuturesLadder.tsx:190,195` + `frontend/src/lib/close-order.ts` | FuturesLadder.test 21 條(disabled 雙 title / dialog body / 估價 null gate / LF-1 hint 回饋)(1290 passed) | 截圖: 同上(disabled 態 + 注入部位後平倉 enabled 對照)+ user 過目 | 證券平倉流(CapitalPositionsList 既有測試 = 共用 helper 保護) |
| SC-11 OI 撐壓線 | `copycat/server/oi_levels.py:282,317` + `hooks/useOiLevels.ts` + `lib/oi-levels.ts:27` + CandleChart hlines | test_oi_levels(service+route,含 402/負向/單飛並發)+ oi-levels.test(帶界端點 max)+ useOiLevels 降級(雙套件全綠) | `evidence/SC-11_finmind-real.txt`(真打:date 2026-08-05 / 202608 / 238 strikes)+ 截圖 `SC-11_oi-lines-daily.jpg`(壓 47000・OI 1290口・2026-08-05 逐字一致)+ user 過目 | token 缺 → 空 shape(測試);TXO tab 巡檢正常 |
| SC-12 夜盤時窗 | `frontend/src/lib/trading-hours.ts:40` | trading-hours.test 11 個(星期,時刻)對 + 邊界對 13:47/14:56(1290 passed) | 驗證窗口 anytime(brainstorm 標定)— 自動化層即為驗收 | useMarketBars 既有日盤窗不變(既有測試) |

**結論**:12/12 無 FAIL。唯一非綠欄位為 SC-3 real-env 的 `infra_fail`(對應
state.json `phase_6_blocked_reason`,fallback 已載明:fake rows pytest+fixture 雙層覆蓋,
merge 後 prod 自然重啟補量法 curl + user 過目)。無分流敘述(無 FAIL 條目)。

Meta:rollbacks = [](全程零回退)。
