# verification — fix/pr-153-review-followups(2026-08-30)

worktree `C:\side-project\copycat-wt-pr153-followups`,base master 2873e004(PR #153 rebase merge tip)。
Spec = `docs/superpowers/specs/pr-153-review.md`(14 條)+ user 拍板「開 然後全部修」;F-05 走 (b) 擴 catch 到 `ValueError` 並同步兩處 docstring;F-14 亦做。

## 1. 自動化 gate

| Gate | 指令(worktree 根) | 結果 | exit |
|---|---|---|---|
| **pytest** | `.venv/Scripts/python -m pytest -q -p no:cacheprovider` | **3197 passed, 1 skipped, 1 warning in 222.17s**(PR #153 時 3187;+10 = 本分支新測試) | 0 |
| **ruff** | `ruff check copycat tests` | All checks passed! | 0 |
| **ruff format(F-12 判準)** | `ruff format --diff tests/live/test_stock_source.py` hunk 數 | HEAD 8 = pre-PR(25312d79)8 → 本分支零新增偏差 | — |
| **pyright** | `pyright` | 0 errors, 0 warnings, 0 informations | 0 |
| **copycat validate** | 主 tree `python -m copycat validate`(replay / engine 碼本分支零 diff) | 42/42 PASS | 0 |
| frontend | 未動 | N-A | — |

紅先行:`test_member_connection_error_rearms_the_first_tick_trigger`(F-01)、`TestPrepareBackfill::test_bad_payload_is_logged_not_raised`(F-05)在實作前確認紅(2 failed / 23 passed),實作後 25 passed。
F-02 / F-03 / F-04 / F-07 的靈敏度修法在乾淨碼上綠(reviewer 在 /pr-review 時已對 MUTANT-1 / 2 / 5 實測紅)。

## 2. 逐條對帳(F-01…F-14)

| # | 修法 | commit | 證據 |
|---|---|---|---|
| F-01 | 成員 ConnectionError 分支 `self._tick_armed.discard(code)` | 28e7d900 | 新測試 4 筆成交 → 3 次失敗各點火一次、第 4 筆被 `_BACKFILL_MAX_FAILS` 擋、tc4_status 仍 up |
| F-02 | `backfill_gate` 卡第一檔時斷言 `prepares == [codes]` | c1216c15 | `test_worker_prepares_the_whole_queued_batch_before_harvesting` |
| F-03 | `backfills == ["2330","2330"]` + `_tick_armed == set()` | c1216c15 | `test_main_is_left_to_its_own_enqueue_points` |
| F-04 | 兩條鏡射測試(真退訂 / 主圖 release) | c1216c15 | `test_first_tick_trigger_rearms_after_a_real_unsubscribe` / `…_after_a_main_slot_release` |
| F-05 | `except (ConnectionError, ValueError)` + Protocol / impl docstring 同口徑 | 28e7d900 | `test_bad_payload_is_logged_not_raised`(SUBQUOTE 回 `not json\0`) |
| F-06 | `assert sent == [...]` | c1216c15 | `test_transport_failure_is_logged_not_raised` |
| F-07 | 雙碼批次 `prepares == [["2317","2454"]]` + backfills 組成 | c1216c15 | `test_batch_is_deduplicated_before_prepare` |
| F-08 | 試撮 docstring 改「`is_trial` 旗標 + engine guard」 | c1216c15 | `test_trial_window_tick_does_not_enqueue` |
| F-09 | 否定斷言前 `wait_until(meta is not None)` | c1216c15 | 兩條不入列測試 |
| F-10 | `src.on_reconnect()` 真回呼 | c1216c15 | `test_reconnect_rearms_the_first_tick_trigger` |
| F-11 | harness 刪 `watchlist` choice、docstring 補 `ticks` / `--tick-gap-ms` | 93fcab7d | `harness_backfill_timing.py` |
| F-12 | 兩處多餘空白行 | c1216c15 + 93fcab7d | ruff format hunk 8 = pre-PR 8 |
| F-13 | verification.md / round-1 JSON SHA 回填 rebase 後值 + 對照註 | 93fcab7d | 六顆對照全為 db0e6d48 祖先(/pr-review R8 補驗) |
| F-14 | `code not in self._tick_armed` 提到 guard 第一位 | 28e7d900 | 25 條 FirstTick / BatchPrepare / Removal 測試綠 |

## 2a. two-axis review round 1 收修(`code-review-round-1.json`;第 4–6 筆)

| 條 | 修法 | commit | 證據 |
|---|---|---|---|
| F-A / S-1 | F-13 回填改引 master 上的 SHA + 第 n 筆 + subject(先前六顆是 GitHub rebase merge 重寫前的分支 SHA) | 5bb62633 | `git merge-base --is-ancestor <sha> origin/master`:a7156aac / 84dce05f / eab0f33e / 50701501 / 2de68fe3 / 6615f006 / 2873e004 全 yes、cdd847fd no |
| F-B | 兩行超長 CJK 尾註改獨立行 | b5b4effd | `ruff format --diff tests/server/test_stock_engine.py` hunk 14 = pre-PR 14 |
| F-C + F-F | `prepare_backfill` 拆三段:連線失敗整批停 / 逐檔 ConnectionError 停 / ValueError 跳過該檔續行;docstring 同口徑 | f35f545b + b5b4effd | `test_bad_payload_is_logged_not_raised` 改「第一檔壞電文、第二檔照常 Sub」全等斷言,紅先行 |
| F-D / S-3 | `except Exception` 分支同樣 `_tick_armed.discard` | f35f545b | `test_member_unexpected_error_rearms_the_first_tick_trigger`(RuntimeError 後下一筆 tick 再點火),紅先行 |
| S-4 | main-slot 鏡射測試改具體計數 2 → 3 | b5b4effd | — |

**最終 gate(HEAD 5bb62633)**:pytest **3198 passed, 1 skipped, 1 warning in 223.44s**(exit 0);ruff All checks passed;pyright 0 errors;
`ruff format --diff` 兩個測試檔 hunk 數與 pre-PR 相同(8 / 14);`copycat validate` 42/42(replay 碼零 diff)。

## 3. 真實環境
本分支不改任何行為契約(F-01 只在既有失敗路徑還回點火權;F-05 只擴 catch;F-14 純順序)。真環境判準沿 PR #153:08-31 開盤 `grep "stock backfill"` 首筆 ≤ 09:00:05、全部 ≤ 09:00:30(前提 prod 重啟含本 PR)。
