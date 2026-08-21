# verification — mod/calendar-visibility-batch(R6)
## 自動化(2026-08-21 19:2x):pytest 2840 passed(baseline 2833 → +7)| ruff / pyright 0 | copycat validate 42/42 | vitest 136 files / 2510 passed(+21)| tsc / eslint 0 | react-doctor No issues
## SC
- SC-1 膠囊:App.test 正向(calendar_trade_date ≠ today、平日、payload today = 本機日)/ 同日 / 週末 / stale / calendar_loaded=false / 取數失敗(retry 終態)PASS;isWeekendIso TZ 負偏移 lock。
- SC-2 標題:SignalRail 四態 + 空字串;useSignalFeed 兩欄 + refetchInterval 5 分;StockPage 接線「08-20 訊號」PASS;後端 route 三鍵形狀、先取樣後 await lock。
- SC-3 試撮:is_trading_day False + 窗內 → trial False / 播種 False / flush 不翻轉;日曆入參日期檢查;observe 純窗契約;預設 weekday<5 PASS。
- SC-4 UI:膠囊 browser_unavailable(verify 側車無日曆、prod config 不動)→ App.test 為證據 + **user 過目說明**;標題同(verify 側車無 hub)→ StockPage.test 為證據。
## 白名單 W1 useTradingCalendar options 逐字搬 / W2 今日訊號逐字 / W3 交易日 trial 位元不變(fixture 僅顯式注入)/ W4 monthDay 逐字 / W5 header 其餘未動。抽 2 未改:LimitListSection.test 44 綠;test_signal_hub 綠。
## Migration 無。self_review_head = 見 change-spec.md 末尾
