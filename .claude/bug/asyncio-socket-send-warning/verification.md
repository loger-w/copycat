# Verification — fix/asyncio-socket-send-warning

## Phase 6|自動化 gate(worktree,fix HEAD 9bc5e58;main session 親跑)

| Gate | 指令 | 結果 | Exit |
|---|---|---|---|
| pytest | `.venv\Scripts\python -m pytest -q` | 1500 passed, 1 skipped in 62.08s | 0 |
| ruff | `ruff check copycat tests` | All checks passed | 0 |
| pyright | `python -m pyright` | 0 errors, 0 warnings | 0 |
| validate | `python -m copycat validate`(主 tree;replay 鏈 code 與本分支 byte-identical — diff 只碰 copycat/server/{ws,app,capital_api}.py + tests) | 42/42 PASS | 0 |

(review 補強 commit 後 gate 重跑結果見下方追記。)

## Phase 7|真實環境驗證(重走 Phase 1 重現步驟,修復後 code)

盤中不重啟 prod server(§8 紀律:重啟清櫃買 in-memory 序列;不起第二台連 TC4)→
用 worktree code + fake source 在 8899 重走完全相同的重現步驟:

- RST 突斷後持續推 tick 8 秒:**warning 0 則**(修復前同窗口 613 則)。
- handler 退場證據:relay 單元測試 + 整合測試 0 warning(sans-io impl 無
  "connection closed" INFO 行,該行缺席不具意義 — 只在 TRACE 印 "connection lost")。
- **prod 生效待 user 下次(盤後)重啟 server**;`/api/health` 的 git_sha 可核對。

## Phase 8|反向驗證

紅 commit(1543972)因單元測試 import relay 無法收集(ImportError),改外科手術式:
在 fix HEAD 上 `git checkout a012ee5 -- copycat/server/app.py`(只拔行為修復,relay 保留)→
`pytest tests/server/test_ws_disconnect.py::TestAbruptDisconnect` →
**FAILED + `WARNING asyncio:proactor_events.py:353 socket.send() raised exception.`**(紅回來)→
`git checkout HEAD -- copycat/server/app.py` 還原 → **4 passed in 2.02s**(綠回去)。
測試確實抓得到 bug。

## 收尾 review(C 節,round 1)

`code-review-round-1.json`:async 正確性 lens 0 findings(各路徑實測佐證);
測試品質 lens P1×1 + P2×4 — T1/T2/T3/T5 accepted(測試補強 commit),T4 部分採納
(刪零資訊測試;/ws/futures parametrize 拒 → next-time)。
