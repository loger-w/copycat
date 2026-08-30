# verification — perf/opening-backfill-parallel(2026-08-30)

worktree `C:\side-project\copycat-wt-opening-backfill-parallel`,branch `perf/opening-backfill-parallel`,
分支自 master 09cc3e63 開、收尾 rebase 到 25312d79,PR #153 以 GitHub rebase merge 進 master(七筆,SHA 由 GitHub 重寫);本檔 commit 一律引 **master 上的 SHA + 第 n 筆 + subject**(pr-153 review F-13;review 當下的分支 SHA 已 dangling)。venv = 主 tree `.venv`(Python 3.13)。

## 1. 自動化 gate(auto-verify;專案 CLAUDE.md §1)

| Gate | 指令(worktree 根) | 結果 | exit |
|---|---|---|---|
| baseline pytest(master 09cc3e63) | `.venv/Scripts/python -m pytest -q -p no:cacheprovider` | all passed(尾段截斷,exit 0) | 0 |
| baseline ruff / pyright | `ruff check copycat tests` / `pyright` | All checks passed / 0 errors | 0 / 0 |
| pytest(2de68fe3(第 5 筆 chore(docs,skills)),review 前) | `.venv/Scripts/python -m pytest -q -p no:cacheprovider` | 3181 passed, 1 skipped, 1 warning in 210.34s | 0 |
| **pytest(HEAD 6615f006(第 6 筆 fix(server,live) review 收修),review 收修後)** | 同上 | **3187 passed, 1 skipped, 1 warning in 204.96s** | 0 |
| **ruff** | `.venv/Scripts/python -m ruff check copycat tests` | All checks passed! | 0 |
| **pyright** | `.venv/Scripts/python -m pyright` | 0 errors, 0 warnings, 0 informations | 0 |
| **copycat validate** | 主 tree `.venv/Scripts/python -m copycat validate`(replay / engine 程式碼本分支零 diff;`out/` gitignored 不在 worktree) | 42/42 PASS | 0 |
| frontend | 未動 `frontend/` → 不適用 | — | — |

新測試(紅先行,各自在實作前確認過紅):
- `tests/live/test_stock_source.py::TestBackfill::test_first_page_poll_backs_off_instead_of_sleeping_a_full_poll_wait`(S1-a;修前 elapsed 1.0 s 紅)
- `tests/live/test_stock_source.py::TestPrepareBackfill::*`(2 條;S1-b source 面)
- `tests/server/test_stock_engine.py::TestBackfillBatchPrepare::*`(3 條;S1-b worker 面,主測試修前紅)
- `tests/server/test_stock_engine.py::TestFirstTickEnqueuesBackfill::*`(4 條;S2,首筆入列測試修前紅;試撮 08:35 測試抓到我漏 `is_trial` 一次)
- 既有兩條 rollover 測試斷言依 S2 預告的行為改動調整(見 spec-brief 白名單:「舊帳清空」斷言原樣保留,加 `backfill_gate` 讓新一天 job 在途可觀測)。

## 2. 量測 gate(/perf 步驟 5;與目標 gate 同一把尺)

指令(worktree 根):`.venv/Scripts/python C:/side-project/copycat/.claude/perf/opening-backfill-parallel/evidence/harness_backfill_timing.py --codes 40`
(真 `StockEngine` + 真 `StockQuoteSource` + FakeApi:SubHistory 後 0.2 s 首頁備妥、每 REQ 3 ms;`trigger=group` = 現況群組檢視入列點)

| 版本 | backfill_wall_s(40 檔) | gethis_empty_polls | 備註 |
|---|---|---|---|
| baseline 09cc3e63 | **40.72** | 40 | 1.02 s/檔 = prod 08-28 log 的一秒一檔 |
| S1-a a7156aac(第 1 筆 perf(live) 退避)(退避) | 18.91 | 80 | 0.47 s/檔(0.15+0.3 退避) |
| S1-b 84dce05f(第 2 筆 perf(server,live) prepare_backfill)(整批 SubHistory) | **0.873** | 1 | 只剩第一檔 poll 一次落空;**目標 < 5 s 達標(−97.9%)** |
| HEAD 6615f006(第 6 筆 fix(server,live) review 收修)(review 收修後),`--trigger group` | 0.87 | 1 | 收修無退化 |
| HEAD,`--trigger ticks --tick-gap-ms 10`(S2 路徑:40 檔首筆成交 0.4 s 內到齊) | **1.341** | 3 | 第一筆單跑 ~0.5 s,其餘在它跑的期間累成大批次(review F-4/F-5 的疑慮實測否定) |
| HEAD,`--trigger ticks --tick-gap-ms 50`(首筆散在 2.0 s 內) | 2.70 | 9 | 上界 = 末筆到達 + ~0.5 s;仍 < 5 s |

證據檔:`evidence/harness-head-40codes.json`。

## 1a. review 收修(round 1;`code-review-round-1.json`)
commit 6615f006(第 6 筆 fix(server,live) review 收修):F-1/H1 worker 不死(source `_ensure_connected` 納入 try + worker 端擋 ConnectionError / Exception)、
F-2 tick 入列每訂閱期至多一次(`_tick_armed`)、F-3 主圖排除、J1 訊息、J2 去重。新增紅先行測試 7 條
(`test_prepare_failure_does_not_kill_the_worker` / `test_batch_is_deduplicated_before_prepare` /
`test_fires_at_most_once_per_subscription_period` / `test_reconnect_rearms_the_first_tick_trigger` /
`test_main_is_left_to_its_own_enqueue_points` / `TestPrepareBackfill::test_not_connected_is_logged_not_raised`),
engine + source 256 passed;ruff / pyright 綠;全量 pytest 見 §1 末列。

證據檔:`evidence/harness-baseline-40codes.json`;probe(真 TC4,08-28 盤後,`spikes/stock_backfill_parallel_probe.py`):serial 23.3 s / 批次 3.3 s(同一機制,tick 逐檔相等零逾時)。

不該退化的 metric:
- 單工套用順序 / 三條離開路徑:`TestBackfillBatchPrepare` + 既有 175 條 engine 測試全綠。
- TC4 REQ 數:harness 280 → 281(批次多一輪 40 SUBQUOTE、少 39 次落空 GETHISDATA);TXO 面 280 檔同樣板已跑一年。
- 記憶體 / 其他 endpoint:本分支不碰;pytest 全量綠。

## 3. 真實環境(prod-like)

- 今日(08-30 週日)TC4 未啟動(無 50774 監聽),真 TC4 量測不可得。**留 08-31(一)盤中對帳**(已寫進 `docs/next-time.md` 第 5 條勾銷段):
  `grep "stock backfill" logs/server-20260831-*.log | awk '$2>="09:00:00" && $2<="09:01:00"'` → 首筆 ≤ 09:00:05、自選全部 ≤ 09:00:30;
  09 點整點總筆數對照 08-28 的 313(S2 之後開盤瞬間應只剩一次)。**前提 = prod 8721 重啟到含本 PR**。
- 邊界(單元層已鎖):試撮 08:35 tick 不入列 / 純簿更新不入列 / 在途不重複 / 過期 job 不進批次 / prepare 傳輸失敗只 log。
- 未改功能抽驗:`tests/server/test_app.py`(routes)+ `copycat validate` 42/42 全綠。

## 4. 回到動機
user 原話「一開盤全部都要接收,不是一筆一筆慢慢收」→ S2 讓 09:00 首筆成交即入列(不等群組檢視 / 前端 09:01 閘),S1 讓整批數秒內收完。
08-31 真環境數字回填後才算 Done(本檔 §3)。
