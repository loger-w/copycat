# verification(mod/subscribe-retry-recovery,2026-08-05)

## Phase 6 自動化 gate(main session 親跑,HEAD = 382d2a5)

| gate | 指令 | 結果 |
|---|---|---|
| 測試 | `.venv\Scripts\python -m pytest -q` | **1672 passed**, 1 warning, 79.35s(baseline 1651 + 21 新測試)|
| Lint | `.venv\Scripts\python -m ruff check copycat tests` | All checks passed! |
| 型別 | `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings, 0 informations |
| Golden gate | `.venv\Scripts\python -m copycat validate` | 42/42 PASS |

exit code 皆 0(單獨執行,無 pipe 汙染)。

TDD 紅證據(implementer 回報):corr 首輪 17 failed(5 新 + 12 kwarg 連坐)、stock 10 failed
(全為新測試);review 修復輪 corr 1 failed / stock 3 failed 紅先行;W-3 行為已存在,
以 mutation(`_schedule_backfill` → `pass` → FAILED)驗非空轉。

## Phase 7 真實環境驗證

改動為引擎內部背景復原行為,無 HTTP / WS 對外面。依 CLAUDE.md §8 紀律
(盤中/夜盤不重啟跑著的 server、不起第二台連 TC4 的後端),真實環境證據 =
**下次自然重啟後 grep log 判準**:
- corr:`corr subscribe %s(%s)失敗,進重試佇列` / `corr %s subscribe retry ok`
- stock:`watchlist subscribe %s failed` / `rollover resubscribe %s failed`(重試輪同字串)
健康啟動(訂閱全成功)時零新 log、零新 task 行為(SC-4 由測試鎖:
test_all_success_never_resubscribes、test_all_success_leaves_no_retry_task)。

白名單 8 條:兩個 review lens 逐條對照 + 修復輪複核,全數保留(見
code-review-round-1.json whitelist_check)。
