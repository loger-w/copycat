# verification:startup-names-futures-resub

日期:2026-08-04 00:20(夜盤;真實環境驗證全程 fake source + 另一 port,零 TC4 接觸)

## 自動化 gate(主 session 親跑,exit code 皆 0)

| Gate | 指令 | 結果 |
|------|------|------|
| pytest | `.venv\Scripts\python -m pytest -q` | **1497 passed**, 1 warning (62.3s), exit 0 |
| ruff | `.venv\Scripts\python -m ruff check copycat tests` | All checks passed!, exit 0 |
| pyright | `.venv\Scripts\python -m pyright` | 0 errors, 0 warnings, exit 0 |
| validate | `.venv\Scripts\python -m copycat validate` | **42/42 PASS**, exit 0 |
| vitest | `npm test`(frontend/) | **914 passed**(66 files), exit 0 |
| tsc | `npx tsc -b`(frontend/) | exit 0 |
| eslint | `npx eslint src`(frontend/) | exit 0 |

(IDE Pyright 面板曾對 `resub_interval_secs` 報 reportCallIssue — 舊索引誤報,
`copycat.server.ws` 等既有模組同報 unresolved;CLI pyright 0 errors 為準。)

## 真實環境驗證(Phase 7)

**症狀 1/2 機制重現 + 修復後復原**(`scratchpad/startup_window_probe.py`,
`create_app` + FakeTxoSource 的 `list_series` 延遲 12s 模擬 TXO 全鏈回補,port 8899):

```
t=  0.0s  URLError: <urlopen error timed out>
t=  2.5s  URLError: <urlopen error timed out>
t=  5.0s  URLError: <urlopen error timed out>
t=  7.5s  URLError: <urlopen error timed out>
t= 10.0s  URLError: <urlopen error timed out>
t= 12.6s  200 OK  count=2401
```

→ lifespan 阻塞期整段連不上、完成後 0.6s 內 names 可用 — 症狀 1/2 的「一開始沒有、
之後才有」機制成立。前端半邊(error 終態不自動復原 → 修後 3s 輪詢自動拿到)由
整合式測試以真實計時驗證(紅時 10s 逾時仍 undefined;修後 4.07s 拿到 names,
無任何 focus/remount)。

**症狀 3**:真環境無法主動觸發訂閱失敗(第 8 次觀測 2026-08-04 00:06,跑著的 server
三品全健康:TXF p=42708000 / MXF / TMF 皆有值 + 五檔 + resolved=202608)。機制層以
fake source 紅測試穩定重現(前 N 次 ConnectionError);修復後下次真發生時 10s 內自癒,
log 判準:`futures subscribe %s failed`(原字保留)→ `futures %s subscribe retry ok`。

## 反向驗證(Phase 8)

| 修復 | 操作 | 結果 |
|------|------|------|
| backend 30c05d1 | `git revert --no-commit` → pytest test_futures_engine.py | **4 failed**, 25 passed(TestPendingResubscribe 全紅)→ `revert --abort` 還原 |
| frontend 2d14476 | `git revert --no-commit` → vitest useStockNames.test.tsx | **1 failed**, 4 passed(自動復原測試紅)→ `revert --abort` 還原 |

還原後 branch 4 commits 完整(99ef888 / 30c05d1 / 0047531 / 2d14476)。

## 回到動機核對

- 症狀 1「提示列一開始不顯示,用一陣子後才出現」→ 啟動窗內 query error 終態已由
  3s 自動重抓取代 refocus 依賴;server 就緒後 ≤3s 提示列可用。
- 症狀 2「股名很慢才出現」→ 同一 query,同修。
- 症狀 3「期貨與價差有時不出現」→ 已證實的「訂閱失敗零重試」缺陷補上重試佇列;
  真實觸發源(REQ 為何逾時)仍未定位,log 判準保留於 next-time.md。
