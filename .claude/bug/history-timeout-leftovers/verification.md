# verification — fix/history-timeout-leftovers

| gate | 結果 |
|---|---|
| pytest 全套 | 2904 passed |
| ruff / pyright | All checks passed / 0 |
| copycat validate | 42/42 PASS |
| 反向驗證 | revert round-2 fix(54ca3ff3)→ 2 紅(reconnect_during / timeout_after_release);再 revert round-1 fix(50d26489)→ 4 紅(全部四支 [red]);還原 → 全綠 |

真實環境:TC4 逾時 / reconnect 撞 inflight 無法刻意觸發 → 以 FakeSource gate + 事件序列測試代替;
prod 重啟後 log 觀察 `backfill … timeout 但已退訂,不重排` / `river 回補 single-flight … 併回 pending` 是否如預期(待 user)。
