# verification — bug/corr-backfill-retry-backoff(2026-08-28)

分支 commit(引「第 n 筆 + subject」):第 1 筆 `test(server): river 回補逾時重試改遞增退避 8 輪…(紅先行)` →
第 2 筆 `fix(server): river 回補逾時重試改遞增退避(30 s 翻倍封頂 10 分)8 輪 ≈ 45 分…` →
第 3 筆 `test(server): review round 1 收修 —— reconnect 整輪起跑作廢沉睡 retry 新案…` →
第 4 筆 `fix(server): reconnect 整輪起跑作廢沉睡的逾時重試 + 輪號睡前定案 + docstring 回校…` → 第 5 筆 artifacts。

## 1. 自動化 gate(worktree `.worktrees/corr-retry`,借主 tree `.venv`)

| gate | 指令 | 結果 | exit |
|---|---|---|---|
| 紅先行(第 1 筆,fix 前) | `pytest tests/server/test_corr_engine_river.py -k "capped or ladder or giving_up"` | **3 failed**(`AttributeError: no attribute '_BACKFILL_RETRY_MAX_SECS'` / `_retry_delay_secs`) | 1 |
| 綠(第 2 筆後) | `pytest tests/server/test_corr_engine_river.py` | 24 passed | 0 |
| 收修後同檔 | 同上 | 25 passed | 0 |
| 全量(第 1 次) | `pytest -q -p no:cacheprovider` | 3141 passed, 3 skipped, **1 failed**:`tests/test_trading_calendar.py::test_warn_if_year_missing_is_atomic_across_threads` | 1 |
| 該案單跑 ×3 | `pytest tests/test_trading_calendar.py` | 39 passed ×3 | 0 |
| 全量(第 2 次,最終樹) | `pytest -q -p no:cacheprovider` | **3142 passed, 3 skipped**(187 s) | 0 |
| lint | `ruff check copycat tests` | All checks passed | 0 |
| 型別 | `pyright` | 0 errors, 0 warnings | 0 |
| golden | `copycat validate` | 未動 replay / engine 路徑 → 不跑(既有 42/42 於 08-28 主 tree) | — |
| frontend | 未動 → 不跑 | — | — |

第 1 次全量的紅是負載 flake:該測試是四執行緒 + 50 ms 睡眠治具的競賽測試,與本案零交集(本案只動 `corr_engine.py`),單跑 3/3 綠、
第 2 次全量綠。**不動它**;記 next-time(候選:治具窗放大或 join timeout 加長)。

## 2. 反向驗證(mutation)

- 第 2 筆:紅先行本身即證(fix 前三案紅)。`test_retry_rounds_are_capped` 4 → 9 與 `test_giving_up…` 4/8 → 9/18 為**事前標該變**的既有斷言(change-spec §4)。
- 第 4 筆 `_cancel_sleeping_retries`:把 `_schedule_backfill` 裡的呼叫換成 `pass` → `test_reconnect_full_round_cancels_sleeping_retry` 紅
  (`整輪起跑沒作廢沉睡的重試`:集合仍有 1 支);還原後 25 passed。

## 3. 白名單逐條(change-spec §3)

| # | 既有行為 | 證據 |
|---|---|---|
| 1 | single-flight / 併回語意不變 | `_merge_into_inflight_round` 零 diff;`test_reconnect_during_inflight_round_merges_all_legs…` / `test_retry_blocked_by_single_flight_keeps_its_legs` 綠 |
| 2 | 放棄歸零 / 非預期例外歸零 不變 | 兩分支零 diff(只改註解字面);對應兩案綠 |
| 3 | `close()` 取消 retry task 不變 | `test_close_cancels_pending_retry_task` 綠(patch 5.0 s 睡眠) |
| 4 | 首輪退避 30 s 逐字同 | `_retry_delay_secs(1) == 30.0`(階梯測試) |
| 5 | `apply_backfill` session 比對不變 | 零 diff;`test_late_backfill_does_not_revert_session` 綠 |

## 4. 行為改動(🔴 兩筆)

1. 退避階梯 30→60→120→240→480→600 封頂、上限 8 輪(第 2 筆)。
2. reconnect 整輪起跑前作廢沉睡中的逾時重試(第 4 筆;review Spec P2-2)。

## 5. 真實環境(盤後 / 次一交易日)

動 `corr_engine.py` → 不起第二台連 TC4(ops-discipline),等 prod 重啟後看:
- 判準(P2-1,已寫進 `corr_engine.py` 檔頭):次一交易日開盤若再出現 `river 回補 TSMC(TC.S.TWS.2330)逾時`,
  之後的 `river 回補重試(第 n 輪)` 必須接上一行 `river 回補 TSMC:N 分鐘`(成功);8 輪打完仍全逾時 = 「拉長」這個選項錯,改事件驅動。
- 健康日(首輪就成功)零差異:`grep "river 回補重試"` 應為 0 筆。
- reconnect 期間若有沉睡 retry:log 不再出現「第 0 輪」。

## 6. 留尾(next-time)

- S-6:只 patch `_BACKFILL_RETRY_SECS` 的新測試跑到上界會 2.55 s > `wait_until` 2.0 s;候選 = fixture 同時 patch 兩常數。
- P2-3:回補被 session 比對整批丟棄時 pending 為空 → 輪數歸零(既有行為;失效在安全側:多給一份有界預算)。
- P3-1:事件驅動變體(開盤後仍缺 seed 就再排)= P2-1 判準失敗時的下一步。
- `test_warn_if_year_missing_is_atomic_across_threads` 負載 flake 一次。
