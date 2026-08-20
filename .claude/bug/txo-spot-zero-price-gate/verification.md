# verification:bug/txo-spot-zero-price-gate(2026-08-21)

## 自動化(auto-verify,repo root,實跑輸出)
| 指令 | 結果 |
|---|---|
| `.venv\Scripts\python -m pytest -q` | `2804 passed, 1 warning in 157.11s` |
| `.venv\Scripts\python -m ruff check copycat tests` | `All checks passed!` |
| `.venv\Scripts\python -m pyright` | `0 errors, 0 warnings, 0 informations` |
| `.venv\Scripts\python -m copycat validate` | `42/42 PASS` |
| `pytest tests/live/test_aggregate.py -k SpotZeroPriceGate`(修前) | `4 failed`(紅,症狀 = 0 價算 changed) |
| 同上(修後) | `35 passed`(整檔) |

frontend/ 未動,npm gate 不適用。

## 反向驗證
`git revert --no-commit 198ad1f7` + 保留測試 → `4 failed, 31 deselected`;`git revert --abort` → `35 passed`。

## 真實環境
鎖停不可等(handoff 已定:以單元測試為主)。真鎖停日觀測記 next-time 條目尾註。
prod 重啟含本案 master 後以 `/api/health` git_sha 驗(本 session 隨後執行)。

## Code review round 1 後(6 P2 全吸收)
`pytest tests/live/test_aggregate.py tests/live/test_live_models.py tests/server/test_engine.py` → `85 passed`;ruff `All checks passed!`;pyright `0 errors`。
