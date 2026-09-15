# feat/tick-persist — verification(spec #257,tickets #258–#262)

## 1. Seams 與紅先行

| Seam | 測試檔 | 紅先行證據 |
|---|---|---|
| S1 盤中寫入(engine 餵訊息看 jsonl) | `tests/server/test_tick_persist.py` | T1 `ModuleNotFoundError` → 14 綠;T2 3 紅 → 18 綠;T3 4 紅(opener 缺 / disabled 建目錄 / 無 log 行 / 預算常數缺)→ 74 綠(含 shutdown_budget + main_wiring) |
| S2 轉檔 + 讀回(CLI 入口函式) | `tests/test_ticks_compact.py` | `ModuleNotFoundError` → 12 綠 |
| S3 排程(fake clock + fake 呼叫端) | `tests/server/test_ticks_compactor.py` | `ModuleNotFoundError` → 12 綠(含真子程序 1 條) |
| 不另設 seam | `tests/test_ticks_config.py`(breadth 同款 parity)、`test_shutdown_budget` 一條不等式、`test_main_wiring` prod 顯式傳 `ticks_config` | — |

## 2. 突變體閘(spec Testing Decisions)

| 突變 | 結果 |
|---|---|
| 簿列比較只比買一賣一(`key = (bids[:1], asks[:1])`) | 1 紅(`test_book_row_only_when_any_of_twenty_numbers_changes`),還原綠 |
| 去重鍵少 `code`(`key = ("", cum_vol)`) | 4 紅,還原綠 |
| 列數不符仍刪 jsonl(`if False:`) | 1 紅(`test_row_count_mismatch_keeps_jsonl_and_fails`),還原綠 |
| `msg_seq` 不遞增 | 由 `test_msg_seq_counts_every_message…`(`[1, 4]`)與 T2 `("book", 4)` 釘住;未另做突變 |

## 3. 自動化 gate(收修後最終,worktree 內、主樹 venv)

| 指令 | 結果 | exit |
|---|---|---|
| `python -m pytest -q -p no:cacheprovider` | 3532 passed, 3 skipped, 1 warning(252 s) | 0 |
| `python -m ruff check copycat tests` | All checks passed | 0 |
| `python -m pyright` | 0 errors, 0 warnings | 0 |
| `python -m copycat validate --run-five … --run-four …`(主樹 out/) | 42/42 PASS | 0 |
| `ruff format --check` 本案 8 個新檔 | already formatted(存量 66 檔未 format 為既有狀態,不動) | 0 |

真實環境(CLI 形狀:真實 argv + exit code + 讀回 consumer + 兩個未改 subcommand):`evidence/CLI-1_success.txt`(exit 0、兩檔 parquet)、`CLI-2_missing-jsonl.txt`(exit 2)、`CLI-3_non-trading-day.txt`(exit 2)、`CLI-4_load_day-consumer.txt`(parquet 讀回 + to_stock_tick)、`CLI-5_refuse-existing-parquet.txt`(exit 2、三檔都不動)、`REG-1_untouched-cli-subcommands.txt`(screen / chain-stats `--help` exit 0)。server 側(13:45 排程 + 寫入端)的真環境判準在 §6,上線第一個交易日盤後收。

## 4. 與 spec 的已知偏差(two-axis review round-1 後)

1. ~~parquet 排序鍵 `(code, recv_ns, msg_seq)`~~ **撤銷(round-1 Spec F-03)**:`msg_seq` 改為同日重啟自檔尾接續(`tail_msg_seq` 讀最後 64 KB 的最後一列完整列,當機半行先補換行隔開),排序回 spec 的 `(code, msg_seq)`、`load_day` 只看 `msg_seq`;`recv_ns` 是牆鐘、校時回撥會交錯,不再當排序鍵。
2. **13:45 多一步 `seal_day`**(spec 沒寫):Windows 開著的檔刪不掉,子程序「列數核對後刪 jsonl」會 PermissionError;seal 後該日遲到列丟棄並每個日 WARNING 一次(13:30 收盤後現貨零訊息,丟的只是殘影)。
3. **每日「tick 存檔」行印三處**(13:45、換日 stage2 舊日、關機當日),spec 只寫 13:45;判準「同日取最後」。**計數器是自上次 `open_day` 起的累計**:換日邊界遲到的舊日列會計進新日(round-1 Spec F-04 / Standards F-04 知情接受;判準只看「行存在、寫入失敗 0」不對帳列數)。
4. **retry 語意**:失敗後再試 `retry_max` 次 → 最多 1 + 3 = 4 次呼叫,第 4 次失敗與放棄合成同一行 WARNING(ticket #262 AC 字面「第 4 次不叫」以留言註明)。
5. `to_stock_tick()` 的 `bid_milli / ask_milli` 由存下的五檔重算 `_best_limit`(第一個 > 0 的價),與 engine 當時的值相等(S1 round-trip 釘住)。
6. **補跑範圍比 spec §22 寬**(round-1 Standards F-02 / Spec F-05):排程掃目錄所有 jsonl,過去日的隨時轉(server 13:45 沒開著留下的昨日檔隔天一啟動就補)、今天的 13:45 後轉;非交易日殘檔 / parquet 旁殘餘 jsonl 不轉、WARNING 一次。
7. **已轉檔的日不再開 jsonl**(round-1 Spec F-01):寫入端 `open_day` 見該日 parquet 已在 → 封住;CLI `compact_day` 見 parquet 已在 → `CompactRefused` exit 2「要重轉先刪 parquet」;排程側同閘。修前:盤後重啟預開的空 jsonl 會讓補跑把真 parquet 蓋成空表(reviewer 實跑證實)。

## 7. 回頭核 goal:ticket AC 逐條(`verification-before-completion`,重讀 issue 不憑記憶)

| Ticket | AC | 實作位置 | 測試 / 證據 |
|---|---|---|---|
| #258 T1 | 三則 → 一列、欄位全集逐字 | `tick_persist.observe` / `_common` | `TestTradeRow::test_three_messages_write_exactly_one_trade_row` |
| | msg_seq 被擋也佔號、recv_ns 單調 | `observe`(先 +1 再判)、`_on_raw_threadsafe` 蓋章 | `test_msg_seq_counts_every_message_and_recv_ns_is_monotonic` |
| | 檔名跟 trade_date、同日重啟 append | `_file_for` / `"a"` | `TestFileNaming` 兩案(重啟 msg_seq `[1, 2]`) |
| | flush_secs 一次 flush、不 fsync | `_arm_flush` / `flush` | `TestFlush`;不 fsync 由文件宣告(測試不斷言) |
| | load_day 回 TickRow、to_stock_tick 相等 | `ticks.load_day` / `TickRow.to_stock_tick` | `TestLoadDay::test_load_day_rows_round_trip_to_the_engine_stock_tick` |
| | TicksConfig parity | `ticks_config` | `tests/test_ticks_config.py` 全檔 |
| | pyarrow 零 import | — | `test_pyarrow_never_imported_by_server_or_live` |
| #259 T2 | 四則 → 三列、重複簿計數 1 | `observe` 簿分支 / `_basis` | `TestBookRow::test_book_row_only_when_any_of_twenty_numbers_changes` |
| | 突變:只比買一賣一 → 紅 | — | §2 表(1 紅) |
| | 成交列更新基準 | `observe` `self._basis[code] = key` | `test_trade_row_updates_the_basis…` |
| | 每檔各自基準 | `_basis` per code | `test_basis_is_per_code` |
| | load_day 兩種列按序、成交前一列 = 成交前簿 | `load_day` 排 `msg_seq` | `test_load_day_returns_both_kinds…` |
| | 簿列 to_stock_tick raise | `TickRow.to_stock_tick` | 同上案 `pytest.raises(ValueError)` |
| #260 T3 | OSError 一次 WARNING、停寫、看盤照常 | `_write` / `_fail` / `open_day` try | `TestResilience::test_write_error…`、`TestReviewRound1::test_open_error_at_start…` |
| | 換日重新武裝 | `_failed_days` 日別 | `test_next_day_re_arms_after_a_failed_day` |
| | enabled=false 零目錄零 handle | `_enabled` 全路徑早退;app 不建 | `test_disabled_writes_nothing…`、`TestAppWiring::test_disabled_config_creates_nothing` |
| | 關機 flush;預算段 + 不等式 | `engine.close` gather 後 `persist.close()`;`shutdown_budget.TICK_PERSIST_FLUSH_SECS` | `test_close_flushes_rows…`、`test_lifespan_bound_covers_the_tick_persist_flush` |
| | log 行字面五計數器 | `STATS_FMT` / `log_stats` | `test_close_flushes_rows…`(逐字)、`test_stage2_prints_old_day…` |
| #261 T4 | S2 fixture → 兩檔 parquet、讀回、排序 | `ticks_compact.compact_day` | `TestCompactDay::test_tracer…`、`test_parquet_is_sorted…`、`TestReviewRound1::test_parquet_sorted_by_code_then_msg_seq_only` |
| | 突變:去重鍵少 code / 列數不符仍刪 → 紅 | — | §2 表(4 紅 / 1 紅) |
| | 列數核對失敗 → jsonl 留、exit 非 0 | `CompactFailed` → CLI exit 1 | `test_row_count_mismatch_keeps_jsonl_and_fails` |
| | jsonl 缺 / 非交易日 → exit 2 零檔案 | `CompactRefused` → CLI exit 2 | `test_missing_jsonl…`、`test_non_trading_day…`、`TestCli` 兩案、evidence CLI-2 / CLI-3 |
| | log 行字面、ms = 台北毫秒 | `format_compact_line`;`ms` 由寫入端 `taipei_ms` | `test_log_line_literal`、tracer 案 `rows[0].ms == 39_471_000` |
| | server / live 零 pyarrow | 子程序 | `test_pyarrow_never_imported_by_server_or_live` |
| #262 T5 | 13:44 不叫 / 13:45 一次 / 同日不重叫 | `ticks_compactor.tick` / `_DayState` | `TestSchedule::test_not_before_1345…` |
| | 失敗 15 分鐘 × 3、第 4 次放棄 WARNING | `_tick_day` | `test_failure_retries_every_15_min…`(1+3 語意,見 §4-4) |
| | 啟動補跑(jsonl 在才叫) | `_pending_days` | `test_boot_after_1345…`、`TestReviewRound1::test_stale_jsonl_from_a_previous_day…` |
| | 逾時算失敗一次(不開子程序) | `wait_for` | `test_timeout_counts_as_one_failure` |
| | 保留 120 交易日只刪 -book | `_retain_books` / `_cutoff_trading_day` | `TestRetention` 兩案 |
| | enabled=false 零排程 | `start` / `tick` 早退;app 不建 | `test_disabled_never_calls`、`TestAppWiring` |
| | CLAUDE §1 / §4、預算文件、verification 三處齊 | commit 05441e4e | 本檔 §6 |
| | pytest / ruff / pyright / validate 全綠 | — | §5 |

## 5. 收尾鏈數字

- [x] pytest 全量:收修前 3513 passed / 3 skipped(230 s);收修後 3532 passed / 3 skipped(252 s),exit 0
- [x] validate 42/42(收修前後各一次,exit 0)
- [x] two-axis review round-1:Standards 13 條(0 Must / 2 Should / 11 Nice)、Spec 8 條(2 Must / 3 Should / 1 Nice / 2 info);處置見 `code-review-round-1.json`,收修 commit 8380cc21(test)+ d8cce448(fix)
- [x] graphify:worktree 內 `--update` 會把 worktree 絕對路徑寫進 graph.json 且 cache 整份翻掉(360 檔 D),已還原;merge 後回主樹跑

## 6. 真環境判準(上線第一個交易日盤後;prod 重啟後生效,前端不用 build)

1. `grep "tick 存檔\|tick 轉檔" logs/server-<日>.log`:
   - 「tick 存檔 <日>:成交 n / 簿 m / 重複簿略過 d / flush k / 寫入失敗 e」至少一行(13:45 那行 + 關機那行),**寫入失敗 = 0**
   - 「tick 轉檔 <日>:jsonl n 列 → 成交 a 列 + 簿 b 列(去重 x、壞行 y),耗時 s 秒,MB」一行,**壞行 = 0**;`去重` 應 ≈ 當日重啟次數 × 每檔一筆
   - 零「tick 轉檔 … 失敗」/「放棄」;零「已轉檔封住,之後到達的列丟棄」以外的 tick WARNING
2. `ls data/ticks/`:`<日>.parquet` + `<日>-book.parquet` 在、`<日>.jsonl` 不在
3. `grep 佇列滿 logs/server-<日>.log` 仍為 0(存檔不影響 WS)
4. 開盤 09:00–09:01 從 parquet 算每秒則數與 09-14 手抓樣本(82 檔 49,610 則 / 60 s、峰值 2,932 則/秒)同量級:
   `python -c "import pyarrow.parquet as pq, collections; t=pq.read_table('data/ticks/<日>-book.parquet', columns=['recv_ns']); c=collections.Counter(v//1_000_000_000 for v in t.column('recv_ns').to_pylist()); print(sorted(c.items())[:90])"`
5. 體積覆核(上線第一週):jsonl 峰值大小(13:45 前 `ls -l`)、兩個 parquet 大小、簿列去重後列數 vs spec 估計(jsonl ~700 MB、簿 parquet 60–100 MB)
6. 關機 log「關機 stock 段」不因存檔變慢(健康路徑 1–3 s 內),「關機收尾」彙總行多 `ticks` 段
7. 手動重轉演練(任一天盤後):`python -m copycat ticks-compact --date <YYYYMMDD>` 對已轉過的日 → exit 2「jsonl 不存在」
