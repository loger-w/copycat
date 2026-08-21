# change-spec — 日曆輪詢週期 + tape_omitted 前端讀取

分流:已成形(review 指名修法)。S 級兩檔小批 → spec review 0 輪。
[auto-default: calendar 5 min + refetchIntervalInBackground | reason: 看盤日常 = preview 整天掛背景,6h 前景計時器跨午夜膠囊遲到數小時;/api/calendar 靜態 JSON,5 min 成本可忽略]
[auto-default: TickTape 空態文案「載入明細…」只在 tapeOmitted 時 | reason: 與「尚無成交」終態區分,VP 圖層本輪不動(窗短,留 next-time)]

## SC
- SC-1:`calendarQueryOptions.refetchInterval === 5*60_000` 且 `refetchIntervalInBackground === true`(lock 測試)。
- SC-2:`fromSnapshot({tape_omitted:true})` → `tapeOmitted === true`;缺欄 → false;`applyTick` 保留。
- SC-3(畫面可指認):`<TickTape ticks=[] loading />` 印「載入明細…」(ink-muted),非「尚無成交」;`loading=false` 照舊。
- SC-4:StockPage 把 `accum.tapeOmitted` 傳進 TickTape(group→single 首 paint 顯示載入中)。

## 白名單
1. calendar `queryKey` / `staleTime: Infinity` / `retry: 1` 不變;App.test `calendarCalls()==2` 不變。
2. `fromSnapshot` 其餘欄位、`ticks` slice / VP fold 不變。
3. TickTape 有列時的五欄 / 上色 / 載入更多 不變;`loading` 未傳 = 既有行為。
4. useStockStream 的 tape 補打邏輯不動。

## Out of scope:VP 圖層的 tape-less 佔位;`handover.attempt`/`tape=0` 契約登記 CLAUDE.md §4(本輪順手做 docs 🔵)。

## Diff
- 🟢 tests [red]:useTradingCalendar.test(options lock)/ stock-accum.test(tapeOmitted)/ TickTape.test(loading 空態)/ StockPage.test(傳 prop)。
- 🔴 `useTradingCalendar.ts` interval;`stock-accum.ts` 欄位;`TickTape.tsx` prop;`StockPage.tsx` 傳 prop;adapters 補 false;13 fixture 補 false(🟢 test-infra)。
- 🔵 CLAUDE.md §4 補兩條契約。
