# repro — BalanceCollector 欠帳一次性時間戳(R7 review P0 + P1×2)

來源:`docs/superpowers/specs/2026-08-22-daytime-chain-review.md` R7 節(PR #84 出貨後 review)。

## 1. 重現(loop)

紅測試 commit `3c2b785d`(先紅後綠):
- `tests/capital/test_balance.py::test_collector_two_abandoned_rounds_swallow_two_late_end_markers`
- `tests/capital/test_balance.py::test_collector_rows_do_not_cancel_remaining_debt`
- `tests/capital/test_client.py::test_two_dead_queries_then_two_late_end_markers_keep_positions`

指令:`.venv\Scripts\python -m pytest tests/capital -q -k "two_abandoned or do_not_cancel or two_dead"`
修前輸出:3 failed —— client 案 `assert client._pending_sec is None` → `[] is None`(第二個遲到 `##`
以空 staging flush 啟動鏈 → `set_positions([])`,與 reviewer 探針 seeded 3357 → [] 同症狀)。

## 2. Root cause

`copycat/capital/balance.py::feed`:`stale_until, self._stale_until = self._stale_until, None` —— 吞第一個
終止符即關窗;`abandon()` 只存 deadline 不存筆數。連續兩輪 abandon 的資訊(欠兩個 `##`)遺失。
附帶:rows 抵達無條件 `self._stale_until = None`,損益段首列固定 `000` 表頭 → profit 段欠帳窗形同虛設。

假說只此一個(code 直接讀出),由紅測試一次驗證。

## 3. 修法(commit 🔴 [green])

欠帳 = `_owed` 計數 + `_stale_until` 時間窗:每個 `##` 消耗一筆;零列且窗內吞掉、帶列照 flush、
窗外欠帳歸零(真空帳戶逃生路保留);rows 不動欠帳。client 端零改動(`keep_abandoned` 語意不變)。

## 4. 反向驗證

`git revert --no-commit <fix>` → `pytest tests/capital` = 3 failed(恰為三支紅測試)/ 347 passed;
還原 → 350 passed。

## 5. 留尾(next-time 已記)

- F7 交錯 / 跨輪混合快照(無 token 不可根治)。
- 窗外遲到 `##` 清空有庫存(20s 未量測)—— 改口記實,prod log 觀察後調窗。
- R7 P2:WARNING 帶 collector 名 / `_set_status("ok")` 專用 clear / `_oi_abandoned` 提前 return。
