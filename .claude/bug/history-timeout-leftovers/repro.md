# repro — R8 留尾三條(2026-08-22 review P2 ×3 + round-2 P1)

來源:`docs/superpowers/specs/2026-08-22-daytime-chain-review.md` R8 節(PR #85 出貨後 review)。

## 1. 重現(loop)= 紅測試
round 1(commit `🟢 … R8 留尾三條 [red]`):
- `test_stock_engine.py::TestBackfillTimeoutRetry::test_release_cancels_pending_timeout_retry_and_clears_budget`
  → 修前 `'2330' in _backfill_timeout_handles` 留著。
- `test_corr_engine_river.py::…::test_retry_task_unexpected_error_resets_round_budget` → RuntimeError 逸出。
- (round-1 的 single-flight 案修在到不了的分支,round-2 review P1 抓到 → 重寫)
round 2:
- `test_corr_engine_river.py::…::test_reconnect_during_inflight_round_merges_all_legs_and_tail_refetches`
  (走真入口 `_schedule_backfill` + `_FakeSource.gate`)→ 修前 pending 空。
- `test_stock_engine.py::…::test_timeout_after_release_does_not_rearm_or_bookkeep` → 修前 handles 含 2330。

## 2. Root cause
- stock_engine:release 只清 `_backfilled/_backfill_failed/_no_data/_trade_status`,逾時 timer 與 `_backfill_timeouts` 漏清;
  worker 逾時分支不看 `_refs`,對已退訂 code 照記帳照武裝。
- corr:`_schedule_backfill` inflight 早退(reconnect 整輪真正丟棄點);`_backfill_river` merge 分支對 `legs=None` 不併;
  `_backfill_retry` 無 except → round 卡非零。

## 3. 修法
`_forget_backfill_timeout(code)` 在兩處 release 呼叫;worker 逾時分支 `code not in self._refs → 補推 status + continue`;
corr `_merge_into_inflight_round(legs)` 供 `_schedule_backfill` 與 `_backfill_river` 共用(None=全部腿 + 輪數歸零);
`_backfill_retry` except Exception → `logger.exception` + 輪數歸零。

## 4. 反向驗證
見 verification.md。
