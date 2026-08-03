# Bug 3 — 測試依賴未進版控的 spikes/TCPY

## 1. 重現

新 worktree(= 乾淨 checkout,`spikes/TCPY/` 被 `.gitignore:9` 排除)跑:

```
pytest tests/live/test_tc4.py tests/live/test_tc4_trade.py -q
→ 2 failed, 38 passed   ModuleNotFoundError: No module named 'tcoreapi_mq'
```

- `test_tc4.py::TestConnectInterruptible::test_connect_dead_port_raises_connection_error_fast` 紅
- `test_tc4_trade.py::TestFailedConnectGcSafety::test_failed_connect_gc_does_not_block_process` 紅

**外加 handoff 未列的第三條(假綠)**:
`TestConnectInterruptible::test_check_stale_reconnect_loop_stoppable_when_app_dead`
**通過**,但通過的理由是錯的 —— 重連執行緒死於 `ModuleNotFoundError`(pytest 只發
`PytestUnhandledThreadExceptionWarning`),而該測試的斷言是 `assert not worker.is_alive()`。
執行緒「因為爆掉而不活著」也滿足它,等於完全沒驗到「重連迴圈可中斷」。

## 2. Root cause

`_ensure_connected()` 會 `sys.path.insert` 到 `spikes/TCPY` 再 `import tcoreapi_mq`;
該目錄不在版控,任何乾淨環境都沒有。測試沒有「環境未就緒」與「程式壞了」的區分。

## 3. 修法(擇 user 建議的測試層)

`tests/conftest.py` 出 `requires_tcpy` marker(沿用 repo 既有的
`from tests.conftest import ...` 共用慣例),兩個 class 整體 skip。
不把 wrapper 納版控 —— 那是第三方檔案且 22 MB。

## 4. 驗證(雙向,防「守門假綠」)

| 環境 | 結果 |
|---|---|
| 缺 TCPY(worktree 原狀) | 3 skipped / 37 passed / **0 failed** |
| `Copy-Item -Recurse` 複製 TCPY 進 worktree | **40 passed / 0 skipped** |

第二行是關鍵:證明 marker 不會在 wrapper 存在時過度 skip(否則就是把三條測試永久關掉的假綠)。

> 複製而非 junction:CLAUDE.md §8 —— `git worktree remove --force` 會沿 junction
> 把主 tree 的 `spikes/TCPY` 一起刪掉(2026-07-30 真踩過)。已確認 `LinkType` 為空 = 真副本。
