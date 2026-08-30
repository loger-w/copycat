# Spec brief(review 用)— perf/opening-backfill-parallel

來源:`diagnosis.md`(同目錄;量化目標 gate + 定位)+ user 08-30 拍板三題。

## User 拍板(HITL,逐字)
1. **S1 吞吐(做)**:worker 出隊前對整批先 `_sub_history`(TXO `fetch_backfill` 樣板)+ backfill 首頁 poll 改 0.15 s 退避;
   零新執行緒、行為不變;各一 commit 可歸因;harness 目標 40 檔 < 5 s(baseline 40.72 s)。
2. **S2 入列時機(本案一起做,🔴 分開 commit)**:原提案「set_watchlist 新增檔即入列 + rollover stage2 對整個訂閱池入列」;
   實作階段依 08-28 log 證據(主圖 6207 08:15 入列 → 30 s 逾時 ×2 → 「放棄」)改為**首筆當日成交 tick 觸發入列**(事件驅動、
   有成交才有東西可補、薄股不卡 worker)。目標:09:00:30 內自選全部有當日線。
3. **S3 set_main 無條件重排去重**:寫進 next-time,本案**不動**。

## 行為保證白名單(本案不得改變)
- 單工 worker:一次一檔套用、收割順序 = 入列順序。
- `_run_backfill_job` 三條離開路徑(generation 早退 / `HistoryTimeoutError` 15 s 重排上限 2 次 / `ConnectionError` 記帳冷卻)逐字沿用。
- 盤前(08:30–09:00 試撮)不入列;`_backfilled` / `_backfill_pending` / `_backfill_failed` 語意不變。
- `group_snapshot` 四道 guard 語意不變(只抽成 `_backfill_wanted`)。
- `backfill()` 的預算 / `poll_wait <= 0` 不等待 / 逾時 raise `HistoryTimeoutError` 不變。
- set_main 無條件入列(S3)不動。

## 量測
- harness `evidence/harness_backfill_timing.py --codes 40`:40.72 s(baseline)→ 18.91 s(S1-a)→ 0.873 s(S1-b)。
- prod-like:08-31 `grep "stock backfill" logs/server-20260831-*.log` 首筆 ≤ 09:00:05、全部 ≤ 09:00:30。
