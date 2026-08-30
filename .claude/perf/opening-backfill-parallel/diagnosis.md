# /perf 開盤回補並行 — 量化目標 gate + 定位(2026-08-30)

## 1. 量化目標 gate

| 項 | 值 |
|---|---|
| 現況(prod 08-28 log `logs/server-20260828-0814.log`) | 首筆回補 09:02:09;之後 1.0 s/檔;09:02 38 筆、09 點整點 313 筆 |
| 現況(probe 08-28 盤後,`spikes/stock_backfill_parallel_probe.py` 20 檔) | serial 23.3 s(1.16 s/檔)/ 批次 SubHistory 3.3 s / ThreadPool(4) 3.4 s |
| 現況(確定性 harness,零 TC4) | `evidence/harness_backfill_timing.py --codes 40` → **40.72 s**(1.02 s/檔;`harness-baseline-40codes.json`) |
| 量測方式 | (1) harness:worktree 根目錄 `.venv python evidence/harness_backfill_timing.py --codes 40`,讀 `backfill_wall_s`;(2) prod-like:交易日 09:00–09:05 `grep "stock backfill" logs/server-*.log`,看首筆時戳與最後一檔完成時戳;(3) probe 盤後重跑 |
| 目標(user 原話「一開盤全部都要接收,不是一筆一筆慢慢收」) | **09:00:30 內自選全部有當日線**;harness 40 檔 < **5 s**(留 6× 餘裕給真 TC4 抖動) |
| baseline gate | worktree master 09cc3e63:ruff exit 0、pyright 0 errors;pytest 背景跑(結果見 verification.md) |

## 2. 定位(log 證據,不是猜)

### 2a. 每檔 1 s 的來源 = `poll_wait` 固定睡 1.0 s,不是 TC4 慢
`copycat/live/stock_source.py::backfill`(:695):`_sub_history` 後首頁沒備妥就
`time.sleep(min(self._poll_wait, remaining))`,poll_wait 預設 1.0、無退避。
同檔基底 `tc4.py::_collect_history`(:893)早有 `_POLL_BACKOFF_START=0.15` 加倍退避,backfill 沒用它。
harness 證據:40 檔 `gethis_empty_polls == 40`(每檔恰一次落空 → 睡滿 1 s)、真資料成本 0.2 s。
單工 worker(`stock_engine.py::_backfill_worker`,:1347)把 40 個 1 s 串起來 = 40 s。

### 2b. 09:00 → 09:02 空檔 = 入列點是需求驅動(步驟 ③ 已診斷)
log 09:02:08 第一筆 `GET /api/stock/group-state?codes=3081,…`(user 打開群組檢視)→ 09:02:09 首筆回補。
之前零筆:自選訂閱(`set_watchlist`)**不入列**;五個入列點 = set_main / rollover stage2 / reconnect /
漲跌停值變(限 `_backfilled`)/ `group_snapshot`(群組檢視 60 s 輪詢)。當天 server 08:14 起、無 rollover、
主圖沒切,所以自選成員只能等群組檢視被打開。前端輪詢閘 `inTradingHours` = 09:01–13:35,
`refetchInterval` 回 false 時 TQ 不排 timer → 08:59 就開著的群組檢視要等 query 被別的事件重估才會開始輪詢。

### 2c. 09 點 313 筆回補中大半是重複(旁支,但吃同一條單工通道)
- `GET /api/stock/state/{code}` → `set_main` → `_enqueue_backfill` **無條件**(:611):8358 一天 44 次、6213 41 次、3450 36 次
  (612 次 state 請求)。每次 = SubHistory + 1 s + 全量收割數千 tick + `apply_backfill`。
- 20 檔在 09:02–09:03 內跑了兩次(3042 09:02:20.944 / 09:02:21.976):第二次來自漲跌停值變入列點
  (首則帶 UpperLimitPrice 的 REALTIME 在回補完成後才到 → `prev_limits != meta`)。設計上刻意(補鎖停判定),
  但在開盤瞬間等於每檔付兩次。

### 2d. 未診斷 / 不在本案
- L405 GroupGridView 2.5 萬 SVG 節點:user 不覺得卡;本案以 harness / prod log 量後端,前端 DOM 另量(見 verification)。
