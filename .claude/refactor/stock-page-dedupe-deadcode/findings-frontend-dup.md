# 前端去重盤點(Explore agent,2026-08-03)

## P1 — 明顯值得做

### D-1 | P1 | 毫元價格格式化 `fmt()` 複製 9 份(逐字相同)

StockPage.tsx:16-19 / TickTape.tsx:8-11 / OrderBook.tsx:26-29 / PriceLadder.tsx:28-31 /
CandleChart.tsx:49-52 / StockIntradayChart.tsx:47-50 / quote/DepthBar.tsx:26-29 /
futures/FuturesLadder.tsx:24-27 / futures/FuturesPage.tsx:15-18

```ts
function fmt(milli: number): string {
  const v = milli / 1000;
  return Number.isInteger(v) ? String(v) : v.toFixed(2).replace(/\.?0+$/, "");
}
```

真重複。近親不併:WatchlistSidebar.tsx:37-41 `fmtPrice`(nullable wrapper 可做);
IndexBar/MarketChart/IndexPage 的指數點位版(`Math.round(v*100)/100`)語意分岔不併。
抽取位置:既有 `lib/format.ts`。Blast radius:個股 7 檔 + 期貨 2 檔,測試全靠文字斷言。

### D-2 | P1 | SVG polyline 點串 `pts()` 複製 6 份(逐字相同)

CandleChart.tsx:61-63 / StockIntradayChart.tsx:52-54 / index/MarketChart.tsx:36-38 /
index/IndexPage.tsx:60-62 / corr/RiverCards.tsx:22-24 / corr/RiverOverlay.tsx:22-24
(第 7 處 lib/stock-intraday-svg.ts:340-342 行內展開,精度須一致)

抽取位置:新檔 `lib/svg-points.ts` 或掛 `lib/chart-crosshair.ts`。
測試 stock-intraday-svg.test.ts:219-220 斷言 toFixed(1) 格式。

### D-3 | P1 | X 軸時間刻度 `X_LABELS`/`hhmm` 三份

StockIntradayChart.tsx:43-45(hhmm)+ :56-59(X_LABELS 沒呼叫 hhmm)+
index/MarketChart.tsx:11-14(逐字同)。candle.ts:32-36 stampOf 為近親。
抽取位置:`lib/stock-intraday-svg.ts`(已 export X_START_MIN/X_END_MIN)加 hhmm() + HOUR_TICKS。
注意 lib/index-chart-svg.ts:7-8 另一份 X_START_MIN 屬 D-15 不併。

### D-4 | P1 | HTTP 錯誤碼取值鏈複製 7 份

useStockBars.ts:40-49 ≡ useMarketBars.ts:37-46(逐字);useStockWatchlist.ts:32-39
`parseError` 完成品;useStockNames.ts:11-14(行內版,body 讀兩次的 bug 形態);
useTrade.ts:17-27 / useCapital.ts:91-103 / useSeries.ts:6-11。
抽取位置:新檔 `lib/api-error.ts`(不讓 hook 互 import)。
範圍外佔一半 → 只收 useStockBars + useStockWatchlist + useStockNames(+useMarketBars 同鏈)。
錯誤碼字串是 StockChart.tsx:98-101 畫面文案來源,行為逐字不變。

### D-5 | P1 | 零 PUT 早退守衛複製 3 份

StockPage.tsx:54-59 / WatchlistSidebar.tsx:104-107 / WatchlistManagerDialog.tsx:83-90
(註解自己寫「W-9 三處之一」)。判定式抽 `lib/watchlist-model.ts` 加
`isSameWatchlist(a,b)`;三個 commit wrapper 各留副作用。測試有零 PUT 斷言。

### D-6 | P1 | `markTone` 已存在,StockIntradayChart 又手寫同語意判色

lib/chart-extreme.ts:75-80 markTone(既有)vs StockIntradayChart.tsx:550-557 lastTone
(語意輸出完全相同,同檔 :320 已在呼叫 markTone)→ 直接可換。
同檔 :751-759 time-tag-price 三元式與 tickTone 差一個 null 分支 → 行為判定,不動。

## P2 — 可做

### D-7 | P2 | 漲跌百分比字串 `${x>0?"+":""}${x.toFixed(2)}%` × 11
個股 6 處(StockPage:103 / OrderBook:236 / DepthBar:133 / WatchlistSidebar:352-354 /
CandleChart:352,654 / StockIntradayChart:581)+ 範圍外 5。抽 `lib/format.ts` fmtPct()。

### D-8 | P2 | 漲跌色三元式 × 10 — 中性態語意分岔(text-ink/text-ink-dim/""/undefined 刻意不同)
抽帶參數版才安全;26 檔 82 處 blast radius 大 → 只收個股。TickTape.tsx:15 priceTone 已 export。

### D-9 | P2 | 漲跌% 計算 `((p-ref)/ref)*100` × 6
個股 4 + DepthBar + 大盤 2。CandleChart.tsx:343 分母是前一根收盤(語意不同)不併。
抽 `lib/format.ts` chgPct()。

### D-10 | P2 | Toggle 按鈕 className × 5
StockChart.tsx:76-79 ≡ CandleChart.tsx:532-535(逐字)。StockIntradayChart :625-631 少
hover:text-ink 多 opacity-40;IndexPage.tsx:65-92 已抽 <Btn>(最完整藍本)。
統一 hover = 行為改動 → hover 做 prop 或保留現值。

### D-11 | P2 | `useId().replace(/[^a-zA-Z0-9]/g,"")` × 2
WatchlistSidebar.tsx:92 / StockIntradayChart.tsx:487。抽 `lib/utils.ts` safeIdToken()。

### D-12 | P2 | `X_LABEL_H = 14` 三處(candle.ts:135 與 CandleChart.tsx:30 必須恆等)
candle.ts 改 export,CandleChart import。注意 CandleChart 被 index/MarketChart.tsx:3 複用。
stock-intraday-svg.ts:21 那份屬另一座標系可不併。PAD_Y 各圖不同值,不併。

### D-13 | P2 | 群組挑選面板 JSX 重複(StockPage.tsx:136-163 / WatchlistSidebar.tsx:399-420)
aria-label 模板逐字相同。抽 `components/stock/GroupPicker.tsx`(groups/onPick/showUngrouped/disabled)。
測試以 getByLabelText("加入 X 到 Y") 定位 → aria-label 逐字保留。

### D-14 | P2 | 搜尋提示列 JSX 重複(WatchlistSidebar.tsx:454-470 / WatchlistManagerDialog.tsx:335-369)
SUGGEST_LIMIT=8 各硬編一份。抽 `components/stock/StockSuggestList.tsx`;
SUGGEST_LIMIT 移 `lib/stock-search.ts`。data-testid="stock-suggest" 保留同層。

## P3 — 不建議動(碰巧相似 / 收益<風險;原始碼多有「刻意分開」註解)

- D-15 toY/priceAtY 三份:各圖座標系刻意分開(PAD_Y、可用高、退化域皆不同)
- D-16 兩張圖 ChartStatic/XAxisLabels/onMove 三件套:hover state 形狀本質不同,共用部分已抽
- D-17 clamp 一行 helper:收益低於跨檔 import 成本
- D-18 空態卡片 JSX:高度策略各版面刻意(TickTape.tsx:32 註解)
- D-19 code→name 查表兩實作:效能取捨刻意分岔
- D-20 localStorage 樣板 × 5:每處 schema/fallback/版本策略不同,抽 generic 行為風險最高
- D-21 minutesOf vs marketMinutesOf:timeframe.ts 檔頭寫明刻意分開
- D-22 shortStamp vs splitStamp:只有找空白那行同
- D-23(測試)wrap() QueryClientProvider 樣板 × 5:可抽 test-utils.tsx,優先度低
- D-24(測試)ACCUM fixture 重複:共享 fixture 有污染前例(4a9fe24),抽須深拷貝,優先度低

## 建議執行順序
1. D-1/D-2/D-4/D-5/D-6(純 helper 上移)
2. D-3/D-11/D-12(常數與小 helper)
3. D-13/D-14(JSX 抽取,aria-label/testid 逐字保留)
4. D-7/D-8/D-9/D-10 只收個股頁呼叫點
D-15~D-22 整組跳過(合併=推翻既有拍板)。

## 掃過無重複:ChartReadout、candle-viewport、bollinger、chart-frame、list-drag、
watchlist-model、stock-search、stock-accum、stock-tick(marketQty≈OrderBook marketOnly 一行)、
useStockStream(與 futures/index stream backoff 骨架相似但 handler 語意不同)、
useContainerSize、useStockOverlay(localYmd 唯一)、useChartToggles
