# verification — fix/pr-251-review-followups(pr-review #251 收修,user 2026-09-15 拍板)

## 0. 拍板(逐字)
1. F-01 選 A:0-1 驗收改相對量(150 → 20–61 ms),真數字等重啟後。
2. F-02 選 A:重啟後立刻、前端先別開再跑 `bench_04_prod_overlay.py 150`;「做完再跟我說,我全部重啟再驗」。
3. 0-5 148 vs 140、0-7 4.40 vs 4.0:接受。
4. 其餘 F-03…F-22 全修一個收修 PR(A);F-23 no-op。

## 1. 自動化 gate(worktree,python = 主樹 venv 絕對路徑)

| gate | 指令 | 結果 |
|---|---|---|
| pytest 全量(第 1 輪,與 Spec reviewer 突變並行) | `python -m pytest -q` | 3426 passed / 3 skipped / **1 failed**:`tests/test_trading_calendar.py::test_warn_if_year_missing_is_atomic_across_threads`(執行緒原子性案;單檔重跑 **3/3 綠**,與本批零交集 —— 判 CPU 競爭 flake) |
| pytest 全量(第 2 輪,round-1 收修後,無並行負載) | 同上 | 3426 passed / 3 skipped / **1 failed**:同一條 `test_warn_if_year_missing_is_atomic_across_threads`。**根因已抓到(不是本批)**:失敗輸出的 caplog 第二筆是 `copycat.live.stock_source:699`「個股零推播自癒:TC.S.TWS.2330 …(attempt 6, window_variant=1)」—— `tests/live/test_stock_source` 洩漏的自癒 timer 執行緒在這條測試的 50 ms 窗內印 WARNING(caplog 掛 root、跨 logger 全收);既有洩漏(ops-discipline 已記「_listen_loop 測後洩漏」),本批新增的 16,200-push 兩案把後段時序推移了幾秒才撞進窗。單檔 3/3 綠、`tests/server + 該檔` 1645 passed。記 next-time 併 test-hygiene 批(該測試改只收 `copycat.trading_calendar` 的記錄、或修洩漏)。 |
| 3 skipped | worktree 缺 gitignored `spikes/TCPY`(2)+ backtest characterization 缺 `data/` 種子(1);與 PR #251 同(主樹 baseline 含它們全綠) | 環境,非本批 |
| ruff | `ruff check copycat tests` | All checks passed |
| ruff format | `win_timer.py`(整檔本批 / 上批新寫)已 format;`corr_config.py` 的 1 處 reformat 是 master 既有(line 50 `min_samples`),不順手重排 | — |
| pyright | `python -m pyright` | 0 errors(中途 2 錯 → 6877dfc7 收) |
| validate | `python -m copycat validate --run-five … --run-four …`(主樹 out/) | 42/42 PASS |

紅先行:F-03 seam 斷言 / F-04 spy 計數 + 佈線 / F-05 重複腿名 / F-06 例外兩案 —— 對應突變體在 review 期間都曾**全綠存活**(pr-251 報告 chunk B 實證),本批加測試後 Spec 軸重做五個突變全 KILLED(見 code-review-round-1.json (c))。

## 2. 逐條處置對照(F-03…F-22;F-01 / F-02 文件;F-23 no-op)

| F | 處置 | 落點 |
|---|---|---|
| F-01 | 相對量口徑 + uniform 存檔 | `verification.md` §2 / §4;`evidence/out_after_01_uniform.json`(60.7 / 60.6) |
| F-02 | 重啟後立刻、前端先別開;熱取對照為額外守門 | `verification.md` §2 0-1 prod 列 / §3-2;#240 留言 |
| F-03 | INFO 印 `sys.getswitchinterval()`;test 釘 `is sys.setswitchinterval` | `__main__.py:168`;`test_main_wiring.py::test_switch_interval_seam_is_bound_to_the_real_api` |
| F-04 | spy `correlations` 計數;佈線案登記 / 除名 client 閘要翻 | `test_corr_engine.py::test_no_clients_skips_the_correlation_math_itself`;`test_corr_routes.py::TestHasClientsWiring` |
| F-05 | `dict.fromkeys` 去重;config 重複 key WARNING(採用後才印) | `corr_state.py:66`;`corr_config.py`;兩測試 |
| F-06 | 例外歸失敗,只印例外本身 | `win_timer.py`;`test_win_timer.py` 參數化兩案(恰一則 WARNING) |
| F-07 | 盤中尺度 + 換日拉回;`entered` = 過 `_in_session` > 90k;窗深 ≥ 300 | `test_signal_state.py` |
| F-08 | bench_07 兩組存檔 | `evidence/out_bench_07_{base,timer1ms}.json`;`diagnosis.md` §1 引用 |
| F-09 | SKILL.md §8 三處改現值 | `.claude/skills/backend-conventions/SKILL.md` |
| F-10 / F-11 / F-12 | `_corr` 具名索引;寫路徑嚴格索引;常數 import tc4 | `corr_state.py` / `signal_state.py` / `river_backfill.py` |
| F-13 | 無 client 16,200 push 後首呼 n 全等 | `test_corr_state.py::test_first_correlations_call_after_a_full_day_of_silence_is_correct` |
| F-14 | 型別字面白名單 | `test_models.py` |
| F-15 | 每 97 筆 ts +2、每 131 筆 base None;docstring 實話 | `test_corr_state.py` 全日對照案(`_adjacent_tol ×1.5` 突變轉紅) |
| F-16 | 等式 `abs(sum − 20) < 1e-9`;#240 補記 | `test_stock_bars.py:468`;issue 留言 |
| F-17 | `def dumps` | `test_river_state.py` |
| F-18 / F-20 / F-21 / F-22 | diagnosis 1-1 目標欄 / §1 首輪未存檔 / 0-3 判準主詞 / 數字統一 | `diagnosis.md` / `verification.md` |
| F-19 | `--all` 取 `KIND_SWITCH` 全集;§2 標母體 | `evidence/bench_02_eval_volume.py`;`verification.md` |
| F-23 | no-op(參考用) | — |

## 3. 行為白名單核對(本批 runtime 語意零改動)
- `corr_state` 去重只影響重複 key 輸入(現行 config 11 腿唯一);`_corr` 具名索引數值逐位同(全日對照案 n / r 仍全等)。
- `win_timer` 例外分支只在 DLL 載不到 / 匯出不存在時走(Windows 11 實務不可達);正常路徑逐字同。
- `signal_state` 寫路徑嚴格索引在正常路徑等價(`_window_vol[code]` 與 `_prev[code]` 同生同滅)。
- `river_backfill` 常數值仍 0.02(改 import);`__main__` 只改 log 印值。

## 4. 真實環境
本批不需重啟;與 PR #251 一起在 user 下一次重啟驗。重啟流程(F-02 拍板 A):**重啟 → 不開前端 → `python .claude/perf/batch-b-tier0/evidence/bench_04_prod_overlay.py 150` → 再開前端**;另看啟動 log 兩行(timer 1 ms 已套用 / switchinterval 0.0010 s,後者現在印的是讀回值)。

## 5. Review
two-axis round-1:Standards 6(H 2 / J 4)、Spec 20 條中 17 完整 / 3 部分、0 漏 0 錯、5 突變 KILLED;收修於 9a1db24b,見 `code-review-round-1.json`。
