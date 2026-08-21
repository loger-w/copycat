# current-state — R6 日曆輪詢週期 + R9 前端讀 tape_omitted

| 項 | 現況 | 目標 |
|---|---|---|
| `useTradingCalendar.ts::calendarQueryOptions` | `staleTime: Infinity` + `refetchInterval: 6h`;TanStack 預設 `refetchIntervalInBackground: false` → 背景分頁計時停擺;`refetchOnWindowFocus` 被 staleTime 消解 | `refetchInterval: 5 min` + `refetchIntervalInBackground: true`(與 useSignalFeed `BASELINE_REFETCH_MS` 同口徑);staleTime 不動 |
| 讀者 | `App.tsx`(寫模組級假日集合)、`CalendarHolidayBadge`(同 options 同 cache);App.test 鎖 `calendarCalls()==2`(retry 案)| 不變;只有重取頻率變 |
| `/api/stock/state?tape=0` 回 `tape_omitted: true` | 後端 `app.py:1468` 寫入;前端 `grep tape_omitted src` 0 命中 → `fromSnapshot` 丟掉;群組切單檔首 paint `TickTape` 印「尚無成交」 | `StockAccum.tapeOmitted: boolean`(必填,與 noData/trial 同款);`TickTape` 空態 + `loading` → 「載入明細…」;StockPage 傳 `accum.tapeOmitted` |
| `applyTick` | spread 既有欄 | 自然沿用 tapeOmitted(補打全量後 fromSnapshot 重建為 false)|

Caller:`StockAccum` 建構點 src 3 處(stock-accum 兩處 / futures-accum-adapter / index-accum-adapter)+ 測試 fixture 13 處(機械補 `tapeOmitted: false`)。
`TickTape` 呼叫只有 `StockPage.tsx:463`。
