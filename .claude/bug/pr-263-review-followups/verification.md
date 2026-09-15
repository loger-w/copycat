# fix/pr-263-review-followups — verification(pr-review 263 收修批)

## 1. 範圍與拍板

- 來源:`docs/superpowers/specs/pr-263-review.md`(32 條;audit 副檔同目錄)。
- user 拍板(2026-09-16):**F-01 先量真實檔案大小不改碼**;**F-04 改成「9 點開盤以前都不用更新簿更新,開盤之後再更新就好」**(簿列只在 09:00 後寫,不動 `STATS_FMT` 字面,`sealed_dropped` > 0 另印一行);**其餘 F-02–F-31 一起修**;F-32 參考用不動。
- 三筆 commit:`159c1fc3` test(紅先行)→ `706063e4` fix(行為)→ `e841d089` chore(docs / pyproject / 報告入 docs)。

## 2. 紅先行證據

收修前跑六個受影響測試檔:**39 failed**(新測試全紅 + `_make` 新簽名連帶),收修後 **146 passed**;逐條對映見 `.claude/feat/tick-persist/verification.md` §4-10。

| Finding | 釘住的測試 |
|---|---|
| F-02 簿檔先寫 | `test_ticks_compact.py::TestReviewRound2::test_book_parquet_is_written_before_trade_parquet`(monkeypatch `_write_parquet` 記順序) |
| F-03 unlink 失敗回滾 + CLI exit 1 | `test_unlink_failure_rolls_back_both_parquet_and_is_a_compact_failed`、`test_cli_maps_unlink_failure_to_exit_1_with_a_message`;真環境 `evidence/CLI-F03_jsonl-held-open.txt` |
| F-04 09:00 簿列閘 | `test_tick_persist.py::TestReviewRound2::test_book_rows_are_not_written_before_0900_but_trades_and_msg_seq_are`、`test_first_trade_before_0900_gate_still_counts_msg_seq_from_one` |
| F-05 補跑過去日不印 stats | `test_ticks_compactor.py::TestReviewRound2::test_catch_up_of_a_past_day_seals_but_does_not_print_current_counters_as_that_day` |
| F-07 load_day 壞行跳過 | `test_load_day_skips_bad_jsonl_lines_like_compact_day`;`test_partial_trailing_line…` 尾巴補 `load_day` 斷言 |
| F-08 cwd + 60 s 上界 | `TestRealSubprocess`(`wait_for(…, 60)`);cwd 由 `run_compact_subprocess` 顯式 `cwd=_REPO_ROOT`(prod 路徑加固) |
| F-09 壞 utf-8 尾列 | `test_bad_utf8_tail_does_not_break_engine_start` |
| F-10 佈線 isinstance | `test_main_wiring.py::test_main_passes_explicit_default_sources` |
| F-11 預算等式 | `test_shutdown_budget.py::test_lifespan_bound_covers_the_tick_persist_flush`(`- LIFESPAN_SLACK_SECS == approx(...)`) |
| F-12 全鏈 parity | `test_full_chain_parity_from_writer_to_parquet`(writer → jsonl → load_day → compact_day → load_day,`TickRow` 逐列相等) |
| F-13 pyarrow 守門 | `test_server_process_never_imports_pyarrow`(乾淨子程序載 `copycat.server.app` 斷 `sys.modules`) |
| F-14 賣側去重 | `test_ask_side_change_alone_writes_a_book_row` |
| F-15 期貨鍵不存 | `test_futures_leg_messages_are_never_persisted`(月契約主圖 `F:CDF:202609`) |
| F-16 app wiring 不起真子程序 | `TestAppWiring` autouse fixture monkeypatch `ticks_compactor.run_compact_subprocess` |
| F-17 退避分支 | `test_after_a_failure_the_loop_sleeps_until_the_retry_not_until_tomorrow` |
| F-18 退避自嘗試結束起算 | `test_backoff_is_measured_from_the_end_of_the_attempt` |
| F-19 observe 尾端 | `test_persist_blowing_up_does_not_block_book_broadcast` |
| F-20 recv_ns 蓋章 | `test_recv_ns_is_stamped_on_the_source_thread_not_on_the_loop` |
| F-21 flush / close OSError | `test_flush_error_warns_once_and_keeps_the_timer_alive_for_the_next_day`、`test_close_error_is_a_write_failure_not_an_exception` |
| F-24 strptime + due_time | `test_ticks_config.py::test_due_time_is_the_parsed_compact_time` + 全形字面 parametrize |
| F-26 handoff try/finally | `TestPersistHandoff`(finally 收尾 + `sealed_dropped` 正面斷言) |
| F-27 kill 分支 | `test_cancelling_the_runner_kills_a_still_running_subprocess`(fake proc,斷 spawn → kill → wait) |
| F-28 config 五字面 | `test_out_of_range_values_are_rejected_at_construction` parametrize |
| F-06 / F-22 / F-23 / F-25 / F-29 / F-30 / F-31 | 文件 / 常數 / 參數 / 依賴 / 測試重複 / docstring / 章節序 —— 由既有測試守住行為不變(146 / 3557 綠) |

## 3. 自動化 gate

| 指令 | 結果 | exit |
|---|---|---|
| `python -m pytest -q -p no:cacheprovider`(全量) | 收修前 3557 passed;round-1 收修後 **3561 passed, 3 skipped, 2 warnings**(239 s) | 0 |
| 六個受影響測試檔 | 146 → round-1 收修後 150 passed | 0 |
| `python -m ruff check copycat tests` | All checks passed | 0 |
| `python -m ruff format --check` 本批 9 檔 | already formatted | 0 |
| `python -m pyright` | 0 errors, 0 warnings | 0 |
| `python -m copycat validate`(主樹 out/) | 42/42 PASS | 0 |

## 4. 真實環境

- `evidence/CLI-F03_jsonl-held-open.txt`:另一個 process 握著 jsonl 時跑 `python -m copycat ticks-compact --date 20260915 --dir <scratch>` → exit 1、stderr「刪 jsonl 失敗([WinError 32] …),parquet 已回滾、jsonl 保留;server 跑著請等 13:45 排程」、目錄只剩 jsonl(修前:traceback + 兩個 parquet 留著 → 之後永遠 exit 2)。
- F-25 事實:PyPI JSON `pyarrow/17.0.0` cp313 wheel 0 個、`18.0.0` 13 個(2026-09-15 查證)。
- 09:00 簿列閘 / F-05 / F-18 屬時序行為,由 fake clock 測試釘住;prod 判準併入 `.claude/feat/tick-persist/verification.md` §7(上線第一個交易日盤後)。

## 4.5 two-axis round-1 收修(`code-review-round-1.json`)

Standards 10 條(2 Should / 8 Nice)+ Spec 4 條(1 Should / 3 Nice)全接受:`except OSError` 收回、盤前略過行、module assert 搬測試、`after` + 逐日 now、`REPO_ROOT` 單一來源、`monkeypatch.setattr`、子程序 env 中和 + 20 s、`jsonl_unlink_denied` fixture、**`ticks.iter_jsonl_rows` + 共用 `well_formed`(load_day / compact_day 同一個讀行器,壞 utf-8 = 壞行、缺欄 = 壞行)**、pip 版本註解、佈線測試 `tick` no-op + `calls == []`、docstring 改述。收修後六檔 150 passed、ruff / pyright 0;全量見 §3 更新。

## 5. 未做 / 留尾

- F-01 記憶體:不改碼,判準 §7-5 + `docs/next-time.md` 09-16 條。
- F-29 `_TickRecorder` 保留(round-trip 案要 StockTick 本體);`_make` 已收 `opener=` / `now_fn=`。
- F-32 分層依賴維持。
- prod 仍跑 8836ca8a,本批與 PR #263 一起等重啟。
