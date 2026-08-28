# mod/index-heal-holiday-gate — 加權分時自癒:休市日窗內補閘 + rollover 作廢在飛 retry

日期:2026-08-28。來源:`docs/superpowers/specs/2026-08-25-do-batch-review.md` §2.5 Spec 1(N105 休市日窗內噪音)/ Spec 2(rollover
前起跑的 retry 把舊日分鐘疊進新日)、§5 A5;08-28 user 拍板題 2「補閘」(原話「休市日就不要抓」;memory `do-batch-batch2-decisions-0828`)。
小活分流(單檔兩處、無對外 API、無 migration)。

## 1. 現況 vs 目標

| 項 | 現況 | 目標 |
|---|---|---|
| 窗內 heal 閘 | `_broadcast_loop`:`in_watch_window()` 為真 → `heal_window = True`,不看日曆;休市日 09:04–13:25 每 60→900 s 空打 TC4 | 有日曆 → AND `_is_trading_day(today)`;無日曆 → 逐字舊行為(窗內照救) |
| rollover 設 pending | 只清 `_pending_minutes` / `_pending_backfill`;在飛的 retry 返回後經 `_merge_backfill` 把舊日分鐘寫進 `_pending_backfill` | 設 pending 時 `_retry_epoch += 1` + cancel `_retry_task` |
| 文件 | CLAUDE.md §4「休市日一發都不打」只講盤外;bars-engine-batch SC-2 寫「窗內照舊有」 | 改「休市日整天一發都不打;無日曆窗內照救」;SC-2 加拍板後口徑 |

## 2. Caller map

- `heal_window` 只在 `_broadcast_loop` 一處計算;讀者 = 同段 `if heal_window:` 的自癒發射。`_has_calendar` / `_is_trading_day` / `_today_fn` 皆既有欄位。
- `_retry_epoch`:寫入點原只有 `_schedule_retry`(+1);讀者 `_subscribe_and_backfill` 早退閘。本案新增第二個寫入點(`_rollover_loop` 設 pending 時)。
- `_retry_task`:`_schedule_retry` 建 / cancel;`close()` cancel;本案 `_rollover_loop` 新增 cancel。
- 無動態用法(grep `heal_window` / `_retry_epoch` / `_retry_task` 全 repo 只 index_engine + tests)。

## 3. 既有行為白名單

1. 盤外段三段語意逐字不變:有日曆且交易日 → `_WATCH_END` 起到午夜;有日曆休市日 → 不打;無日曆 → 13:25–13:40。
2. 無日曆時窗內照救(`test_heal_inside_watch_window_without_a_calendar_still_heals` 新釘)。
3. boot 那一發回補不受 heal 閘管(既有測試斷 `fetch_minutes_calls == 1`)。
4. 自癒退避 / variant 階梯 / `_minutes_lag_exceeded` 判準不變。
5. rollover 兩段式(pending → 重掛 → 回補 → swap)順序不變;`_swap_day` 三層合併不變;rollover 失敗 `_schedule_retry` 不變。
6. stale watchdog(`_in_watch_window` 的另一個讀者)不變。

## 4. 行為改動(🔴 兩筆)

1. 有日曆的休市日,窗內 heal 一發都不打。**事前標該變**:`test_heal_inside_watch_window_ignores_the_calendar` 釘的是相反行為,改名為
   `test_heal_inside_watch_window_skips_a_calendar_holiday` 並反轉斷言。代價(日曆誤標 → 整天不自癒)user 08-28 知情接受。
2. rollover 設 pending 時作廢在飛的 retry:`_retry_epoch += 1`(executor 內未起跑的工作項早退)+ `_retry_task.cancel()`(已 await 的走不到合併點)。
   若該 retry 是 rollover 自己前一拍失敗排的連線 retry,cancel 後本拍 rollover 照樣重掛 / 回補,失敗再排新 retry —— 不失去重試。

## 5. Seams

- `tests/server/test_index_engine.py::test_heal_inside_watch_window_skips_a_calendar_holiday`(紅先行:改前 fetch 2 次)
- `tests/server/test_index_engine.py::test_heal_inside_watch_window_without_a_calendar_still_heals`(白名單 2)
- `tests/server/test_index_engine.py::test_rollover_pending_cancels_the_inflight_retry`(紅先行:改前 epoch 不變、task 不 cancel)

## 6. 留尾

- 日曆誤標交易日的可觀測性只靠畫面(next-time 08-28)。
- cancel 只擋 `_retry_task` 單支;結果面(舊日分鐘不疊進新日)未釘,需可控慢 fetch hook(next-time 08-28)。
