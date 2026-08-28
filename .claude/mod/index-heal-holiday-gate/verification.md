# verification — mod/index-heal-holiday-gate(2026-08-28)

分支 commit(依 08-28 拍板 (b) 引「第 n 筆 + subject」):第 1 筆 `test(server): 紅先行 —— 加權分時自癒窗內段吃日曆… + rollover 設 pending 時作廢在飛的 retry` →
第 2 筆 `fix(server): 加權分時自癒窗內段有日曆時也吃日曆…` → 第 3 筆 `fix(server): rollover 設 pending 時作廢在飛的 retry…` → 第 4 筆 `chore(docs): N105 補窗內閘落文件…` →
第 5 筆 `refactor(server): 抽 _void_inflight_retry()…` → 第 6 筆 `test(server): review round 1 收修…` → 第 7 筆 `test(server): fetch_gate 先定案回傳值再卡閘…` →
第 8 筆 `chore(docs): CLAUDE.md §4 index 閘句…` → 第 9 筆 artifacts。

## 1. 自動化 gate(worktree `.worktrees/mod-index-heal-holiday`,借主 tree `.venv`)

| gate | 指令 | 結果 | exit |
|---|---|---|---|
| 紅先行(第 1 筆,fix 前) | `pytest tests/server/test_index_engine.py -k "skips_a_calendar_holiday or without_a_calendar_still_heals or cancels_the_inflight_retry"` | **2 failed**(`fetch_minutes_calls 2 == 1`、`_retry_epoch 0 > 0`)/ 1 passed(無日曆案 = 白名單) | 1 |
| 綠(第 2 / 3 筆後) | 同上 | 3 passed | 0 |
| 相關三檔(收修後) | `pytest tests/server/test_index_engine.py tests/server/test_main_wiring.py tests/live/test_stock_source.py` | 171 passed | 0 |
| 全量(收修前) | `pytest -q -p no:cacheprovider` | 3139 passed, 3 skipped | 0 |
| 全量(收修後,最終樹) | 同上 | **3140 passed, 3 skipped**(185 s) | 0 |
| lint | `ruff check copycat tests` | All checks passed | 0 |
| 型別 | `pyright` | 0 errors, 0 warnings | 0 |
| golden | `copycat validate`(主 tree) | 42/42 PASS | 0 |
| frontend | 未動 → 不跑 | — | — |

## 2. 反向驗證(mutation)

- 窗內閘:紅先行本身即證(fix 前 `fetch_minutes_calls == 2`);對照組(日曆翻交易日 → `wait_until(calls == 2)`)證明迴圈活著、閘是唯一擋人的東西。
- rollover 作廢:把 `_rollover_loop` 的 `self._void_inflight_retry()` 換成 `pass` →
  `test_rollover_pending_cancels_the_inflight_retry`(機制面)與 `test_rollover_keeps_old_day_backfill_out_of_pending`(結果面)**兩條皆紅**;還原後 63 passed、`grep -c MUTANT` = 0。
- **事故記錄**:結果面測試第一版在 mutation 下**假綠** —— `FakeIndexSource.fetch_day_minutes` 先卡閘、放行後才讀 `day_minutes`,而測試在放行前已把 `day_minutes` 改成 `{}`(給 rollover 自己那趟用),在飛那趟回傳空 dict,merge 空 = 沒 merge。第 7 筆改成「回傳值在卡閘前定案」+ 等 retry task 收場,mutation 才兩條皆紅。教訓:結果面測試一定要跑一次 mutation 看它會不會紅,綠不代表釘到東西。

## 3. 白名單逐條(change-spec §3)

| # | 既有行為 | 證據 |
|---|---|---|
| 1 | 盤外三段語意逐字不變 | `elif self._has_calendar:` / `else:` 兩分支零 diff;既有 `test_heal_after_hours_*` 三條綠 |
| 2 | 無日曆時窗內照救 | `test_heal_inside_watch_window_without_a_calendar_still_heals` 綠 |
| 3 | boot 一發回補不受 heal 閘管 | 翻轉測試斷 `fetch_minutes_calls == 1`(boot)成立 |
| 4 | 退避 / variant 階梯 / lag 判準不變 | `_minutes_lag_exceeded` / `_heal_interval` / `_heal_variant` 零 diff(Spec 軸核) |
| 5 | rollover 兩段式順序 / `_swap_day` 三層不變 | `_rollover_loop` 只在設 pending 後插一行 `_void_inflight_retry()`;`_swap_day` 零 diff;既有 rollover 四條測試綠 |
| 6 | stale watchdog 不變 | `:633` 單獨 `_in_watch_window()` 零 diff |

## 4. 行為改動(🔴 兩筆)

1. 有日曆的休市日,窗內 heal 一發都不打(`heal_window = not _has_calendar or _is_trading_day(today)`)。事前標該變:`test_heal_inside_watch_window_ignores_the_calendar` → `test_heal_inside_watch_window_skips_a_calendar_holiday`(反轉斷言 + 對照組)。代價(日曆誤標 → 整天不自癒)user 08-28 知情接受;可觀測性只靠畫面,記 next-time。
2. rollover 設 pending 時 `_void_inflight_retry()`(cancel + 世代 +1),在下面兩個 `to_thread` 之前。

## 5. 真實環境

- 動 `index_engine.py` → 依 handoff 紀律不起第二台連 TC4 的後端;prod 8721 現在沒在跑(03:xx 無回應),user 重啟含本分支後看:
  - **下一個休市日**(最近:週六 08-30)09:04–13:25 `grep "index 分時自癒" logs/server-*.log` 應 **0 筆**(改動前每 60→900 s 一發);交易日不變。
  - 交易日 08:30 換日後 `grep "index 回補工作項已作廢"`:若換日當下正有 retry 在飛會多一行(新路徑),沒有也正常。
- 紅燈判準:交易日 09:04 後加權分時線落後 > 3 分卻沒有「index 分時自癒」log → 閘誤擋(日曆把當天標成休市);同時畫面會掛休市膠囊。

## 6. 回頭核 goal(08-28 拍板題 2 + review §5 A5 兩部分)

| 要求 | 落點 |
|---|---|
| 休市日不抓(補閘) | 第 2 筆 + 翻轉測試 + 對照組 |
| `_retry_epoch` bump(A5 第二部分) | 第 3 筆(+ 第 5 筆抽 helper)+ 機制面 / 結果面兩條測試 + mutation |
| 文件同步 | CLAUDE.md §4、bars-engine-batch SC-2、review §5 A5「已出貨」、next-time 兩條留尾 |

## 7. 留尾

- 日曆誤標交易日的可觀測性只靠畫面(next-time 08-28)。
- cancel 在 rollover 內的**位置**(兩個 `to_thread` 之前)由 code 註解交代,測試對位置不敏感(review S-P2c knowing)。
