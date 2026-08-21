# verification — fix/balance-collector-owed-count

| gate | 指令 | 結果 |
|---|---|---|
| pytest 全套 | `.venv\Scripts\python -m pytest -q` | 2898 passed(round-1;round-2 後 capital 352 passed,全套見收尾重跑) |
| ruff | `ruff check copycat tests` | All checks passed |
| pyright | `python -m pyright` | 0 errors |
| validate | `python -m copycat validate` | 42/42 PASS |
| 反向驗證 round-1 | `git revert --no-commit <🔴 欠帳改計數>` | 3 failed(恰為三支 [red])/ 347 passed;還原 350 passed |
| 反向驗證 round-2 | `git revert --no-commit <🔴 清 _last_feed>` | 2 failed(`profit_header_then_swallowed…` / `closed_round_terminator…`)/ 350 passed;還原 352 passed |
| mutation([lock]) | `reset()` 拿掉 `_owed = 0` | `test_collector_reset_after_abandon_clears_stale_debt` + `test_reconnect_ok_clears_abandon_debt` 紅;還原 352 passed |
| ruff format | 存量 5 檔本來就 would-reformat(master 同),本輪不動 | — |

真實環境:死查詢 + 遲到 `##` 無法刻意觸發(COM 事件時序不可控)→ 以 FakeClock + 事件序列測試代替;
prod 重啟後觀察 `collector 忽略放棄輪遲到的終止符(尚欠 n)` log 與部位面板是否再瞬清(待 user 盤中)。
