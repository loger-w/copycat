# fix/tc4-logout-and-cancel-reply-warning — verification

branch 開在 worktree `C:\side-project\copycat-wt-logout`(主 tree 同時被另一 session 跑 pr-106 review,
依 ops-discipline「有他人改動就不 switch」)。所有指令在 worktree 內以主 tree venv 跑
(`../copycat/.venv/Scripts/python`;pytest 走 pyproject pythonpath,import 的是 worktree code)。

## 1. Phase 1 feedback loop(紅先行)

一條指令、兩條紅、秒級、可重跑:

```
PYTHONDONTWRITEBYTECODE=1 ../copycat/.venv/Scripts/python -m pytest -q -p no:cacheprovider \
  tests/live/test_tc4.py::TestCloseLogout tests/capital/test_client.py -k "TestCloseLogout or tail_seq"
```

修前(紅先行 commit bf72b054 當下):
```
FAILED tests/live/test_tc4.py::TestCloseLogout::test_close_sends_logout_for_the_live_session_after_unsub
FAILED tests/capital/test_client.py::test_cancel_reply_tail_seq_differs_is_not_flagged_as_preorder
2 failed, 2 passed, 101 deselected in 1.10s
```
- A 紅在 user 症狀:`FakeApi.requests` 全序裡沒有 `{"Request":"LOGOUT",...}`(= TC4 端 62 s 後才 reap 的機制面)。
- B 紅在 user 症狀:刪單回報(C、idx31=A、idx47≠idx0)印出 `Capital reply: KeyNo=… 尾欄序號=… 不同(預約單?)`。

## 2. Phase 2 最小重現

- A:一個 source、一個訂閱、`close()` —— 每個元素都 load-bearing(拿掉訂閱仍應送 LOGOUT,但 UNSUB→LOGOUT 序就驗不到)。
- B:一筆 N 委託 + 一筆同 seq 的 C 刪單(尾欄 = 另一序號);拿掉 N 也紅,但保留才對齊 store 聚合的真實序。

## 3. Phase 3 假說(根因單一,loop 已釘住)

| # | 假說 | 預測 | 結果 |
|---|---|---|---|
| A | `close()` 只呼叫 `Disconnect()`(wrapper 不送 LOGOUT;`Logout()` 零呼叫) | 送 LOGOUT 後 TC4 端 `RemoveLoginInfo` 貼著 Ctrl+C | 成立(§6 真環境 probe:同一毫秒) |
| B | `_handle_reply` 的 KeyNo≠尾欄 條件不看回報類型;刪單尾欄 = 刪單自己的序號 | 排除 `status_raw=="C"` → 08-25 16 筆零 WARNING、預約單 N 回報照舊 | 成立(白名單測試綠) |

## 4. 修法與 commit(rebase 到 origin/master 93f8c303 之後的 SHA)

| commit | 類 | 內容 |
|---|---|---|
| `bf72b054` | 🟢 | 兩條紅 + 白名單一條(FakeApi 新增 `requests` 全序記錄) |
| `1c014c64` | 🔴 | `tc4.py::close()` UNSUB 後、`_dispose` 前呼叫新 `_logout()`:走 `_req` 送 LOGOUT(TC4 回 `Success:OK`);失敗只 log |
| `a4acfb3e` | 🔴 | `client.py::_handle_reply`:`status_raw != "C"` 才印預約單線索 WARNING |
| `6d73bcff` | chore | tc4-market-facts 新事實「Disconnect 不等於登出」;next-time 08-26 節四條 |
| `9511bd50` | 🟢 | review 補鎖:SP1 兩分支 / SP5 序 / SP3 timeout / SP4 無 session / SP2 WS;ST6 反駁還原 |
| `a94d2413` | 🔴 | review 收修:SP3 `_LOGOUT_TIMEOUT_MS=2000`、SP4 仍在線判準維持 `_api`、ST5 兩路 warning、SP6 backfill_tc4 收工 LOGOUT |
| `e3530fad` | chore | ST2 skill bullet 歸位、SP6 app.py 註解 |
| `c6c83ede` | 🔵 | SP4 註解獨立行(ruff format) |

`_logout` 第一版是 send-only(沿官方 `Logout()` 語意);00:56 probe 證實 TC4 有回 reply 後改走 `_req`,
review SP3 再把該次 recv 上界縮到 2 s(五條 session 串行 10 s < run.ps1 15 s)。

## 5. 反向驗證(PASS)

```
git stash push -- copycat/live/tc4.py copycat/capital/client.py   → 2 failed, 2 passed(紅回來)
git stash pop                                                      → 4 passed(綠回去)
```
(`PYTHONDONTWRITEBYTECODE=1` 避 ops-discipline 的同秒 pycache 陷阱。)

## 6. 真實環境

- **A(TC4 對 LOGOUT 的行為,零訂閱 probe,盤中安全 — 不碰任何 refcount key)**:
  scratchpad `logout_probe.py`:LOGIN → `Logout(session)` → recv → `Disconnect()`,2026-08-26 00:56:15。
  - client 端:`LOGOUT reply: {"Reply":"LOGOUT","Success":"OK"}`
  - TC4 端 `QuoteZMQService-20260826-0.log`:
    ```
    00:56:15.321  SaveLoginInfo() Session:c9e6492b…
    00:56:15.324  DoWork:{"Request": "LOGOUT", "SessionKey": "c9e6492b…"}
    00:56:15.324  RemoveLoginInfo(c9e6492b…)
    ```
    對照修前 08-25:UNSUB 17:15:29 → RemoveLoginInfo 17:16:31(62 s reap)。
- **A(prod 收工路徑)**:待 merge + 下次 prod 重啟後的第一次 Ctrl+C —— 判準見 §8。本次不重啟 prod(夜盤跑著)。
- **B**:08-25 log 16 筆誤報樣本(`grep 尾欄序號 logs/server-20260825-0802.log`)全為 `status=刪單` 前一行 →
  修後同型回報以測試治具重放零 WARNING;真環境待下次刪單。

## 7. 自動化 gate(worktree,rebase 後最終 HEAD c6c83ede)

| gate | 指令 | 結果 |
|---|---|---|
| 目標測試 | `pytest tests/live/test_tc4.py tests/capital/test_client.py tests/data` | 255 passed, 2 skipped(exit 0) |
| 全套(review 前 HEAD e7daa79d) | `pytest -q` | 3032 passed, 3 skipped, 2 warnings in 178 s |
| 全套(rebase 後最終 HEAD) | `pytest -q` | 3035 passed, 3 skipped, 2 warnings in 178 s(exit 0)。中途一輪(HEAD 7fe4598e,rebase 前)`tests/server/test_stock_engine.py::TestStreamAndStatus::test_stream_receives_tick_and_book` 紅一次(`tick_msg["seq"]` 1002 ≠ 1),單跑 3/3 綠、前後兩輪全套皆綠、與本 diff 零共同檔 → 記 next-time flake 候選 |
| lint | `ruff check copycat tests` | All checks passed!(exit 0) |
| format(非 gate) | `ruff format --check` 四檔 | 與 master 基線相同(test_tc4 / test_client 存量未格式化;tc4.py 新差異已消) |
| 型別 | `pyright` | 0 errors, 0 warnings(exit 0) |
| golden | `python -m copycat validate`(主 tree,out/ 為 gitignored 產物;本 diff 未動 replay 路徑) | 42/42 PASS(exit 0) |
| 前端 | 未動 frontend/(origin 側 PR #106 收修為 frontend,與本分支零重疊) | n/a |

## 7a. two-axis review round 1

Standards 6 / Spec 6,逐條處置在 `code-review-round-1.json`。接受 8、反駁 3(ST1 既例 / ST3 第二次快照刻意 /
ST4 需同把 api)、先接受後反駁 1(ST6:推導版讓兩條既有測試紅 — 它們把 `rt_requests` 當 clear 後的分段視窗)。
最重要的 finding = SP3(收工時間預算):LOGOUT 專用 2 s recv 上界 + 測試釘 ×5 < 15 s。

## 8. 需 user 過目(prod 重啟後的第一次收工)

1. `.\run.ps1` Ctrl+C 應印 `[run] backend 已自行結束(TC4 session 已 LOGOUT)`(黃字「未結束改強制收掉」= 回報)。
2. `grep RemoveLoginInfo C:\TC4\APPs\TCoreRelease\Logs\QuoteZMQService-YYYYMMDD-0.log | tail -5` 時戳貼著 Ctrl+C(±2 s),
   同段 **不應** 有 `ExecuteCheckPingTime() timeout. Session:<這幾把>`。
3. server log 收工段應有 UNSUB 後緊接 LOGOUT(TC4 log `DoWork:{"Request": "LOGOUT"...}` 五筆,一 session 一筆)。
4. 盤中刪單後 `grep 預約單 logs/server-*.log` 零筆(預約單本身除外)。

## 9. Blast radius

- `close()` caller:`stock_source.py::close()`(覆寫 → `super().close()`)、engine/app lifespan 的 `source.close()`;
  三子類 `StockQuoteSource` / `FuturesQuoteSource` / `CorrQuoteSource` 都無自己的收工路徑 → 五個 prod session 皆生效。
- `_handle_reply` 單一 caller(`client.py:616` COM 事件接線)。
- 未動:`_req` / `_dispose` / UNSUB 迴圈 / `run.ps1`。

## 10. 留尾

- 加權分鐘推播不長、期貨 K 棒落後後端量測 → next-time 08-26 節(本輪不做)。
- `run.ps1` 對「frontend 先退」路徑仍硬殺 backend(既有留尾,不在 scope)。
