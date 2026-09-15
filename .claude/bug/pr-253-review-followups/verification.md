# verification — fix/pr-253-review-followups(2026-09-15,pr-review 253 十條收修)

## 0. 處置對照(user 拍板:F-01 + F-03~F-09 修、F-02 (a) 文件、F-10 本批一起做)

| # | 報告 | 處置 | 落點 |
|---|---|---|---|
| F-01 HIGH | 恢復沿用重登清點,截斷在途庫存鏈 | `_set_status(new, *, error, reset_chain=True)`;`_reply_recovered` 傳 False | `client.py`;紅先行 `test_recovery_during_inflight_balance_chain_keeps_the_chain` |
| F-02 MED | 重連窗改價本地閘寬鬆放行 | (a) 文件知情接受 | CLAUDE §4 + diagnosis 已知不救 |
| F-03 MED | 事件路恢復零 client 測試 | `test_connect_event_recovers_and_rearms_balance_query` + `_ReplayingCom` rc=0 先發 `on_reply_connect(0)` | test_reply_reconnect |
| F-04 MED | 重新武裝斷言恆真 | 同上案:`_balance_due=None` 後事件恢復(未出手)→ 斷 not None | test_reply_reconnect |
| F-05 MED | 探針值 2 零測試 | `test_probe_value_two_is_neutral`(`[1,2,2,1]` 全程 ok、零 COM 啟動呼叫、值進 status_view)| test_reply_watch |
| F-06 LOW | `rc` 復用 | `reply_rc` | `_init_com` |
| F-07 LOW | 四行 log 順序可互換 | 文件兩處 | CLAUDE §4 / verification §3 |
| F-08 LOW | import time / 三連空行 | 上提 / 收兩行 | test_reply_reconnect |
| F-09 LOW | 五份 / 六份 | 六份 | next-time F-18 |
| F-10 LOW | 抽狀態機 | `capital/reply_link.py::ReplyLink`(退避 / 去重 / due / begin_attempt / recovered / classify_probe);client 留狀態燈與 IO;`test_reply_link` 五案表驗;既有 12 案改讀 `_reply_link.next` 當 characterization | 🔵 commit 2f4836f1 |

## 1. 自動化 gate(worktree;venv 走主樹絕對路徑)

| gate | 結果 | exit |
|---|---|---|
| 紅先行(commit ef309c4e 單獨) | test_reply_reconnect + test_reply_watch:**1 failed / 13 passed**,紅在 `assert ['2330'] == ['2330', '3357']`(截斷快照)| 1 |
| fix 後(56230fe9)`pytest -q tests/capital/` | 453 passed | 0 |
| refactor 後(2f4836f1)`pytest -q tests/capital/` | 461 passed | 0 |
| 反向驗證(HEAD dc2d46ef 上突變 `reset_chain=False → True`)| test_reply_reconnect **1 failed / 9 passed**(F-01 案)→ `git checkout` 還原 → 10 passed | 1 → 0 |
| ruff `check copycat tests` | All checks passed | 0 |
| pyright 全量 | 0 errors, 0 warnings | 0 |
| validate(主樹 out)| 42/42 PASS | 0 |
| 全量 pytest(HEAD 2ddf439e,含 round-1 收修)| **3447 passed, 3 skipped**(211 s)| 0 |
| frontend | 未動 | — |

## 2. 白名單逐條核

| 白名單 | 證據 |
|---|---|
| 斷線 → degraded → 退避 → clear 先於 ConnectByID → 恢復 ok 主線 | 十二案 characterization 全綠(改讀 `_reply_link.next`,零 assertion 改) |
| 四行 log 字面 | `grep -n "群益回報線" client.py` 四個 format 字串未動 |
| `status_view()` 欄形 | 未動 |
| `test_client` 三條 `_set_status("ok")` 直呼清點(F5 / pr-238 F-05 / N018) | 綠;預設 `reset_chain=True` 保住語意 |
| 探針 10 s / 「群益回報線 IsConnectedByID=n(上一值 m)」 | 未動 |
| `_init_com` 啟動序列 | `test_client` 啟動序列案綠;`reply_rc` 只是改名 |

## 2.5 two-axis review round-1

Standards 8(hard 2 / judgement 6)/ Spec 4;accept 9(1 部分)、note 2、refute 1(Spec-S-01 機制:回查鏈與回報線獨立,
無條件 `reset_chain=False` 才對,重播污染與旗標無關 → 文件層補記)。收修 commit 168b882f(refactor:backoff 注入收掉 /
`next_due` / `classify_probe` module / EOF / 註解)+ d24078be(fix:S-05 rc=0 log 看狀態印)+ docs。收修後 capital 461 passed、
ruff / pyright 綠;全量見 §1 末列。

## 3. 真實環境

本批不另跑 server。真環境判準與 #253 同一份(`.claude/bug/capital-reply-reconnect/verification.md` §3,第 3/4 行順序可互換):
prod 重啟到本 PR merge 後的 master → 盤後斷網 60 s → `grep "回報線\|Solace"` 四行 → 復網 → `/api/capital/status` ok / 1、
委託列數與斷線前相同。**加一條 F-01 專屬判準**:斷網那 60 s 內若正好有庫存查詢在飛(log「balance 鏈: 庫存段收齊」
在「恢復」之後才出現),`部位落地 n 列` 的 n 不得少於斷線前一輪;prod 沒撞到這個時序就以紅先行測試為證。
每日 05:50 固定斷網(22 天 18/18)= 每個交易日一次自然實驗:隔天早上 `grep 05:5 logs/server-<日>.log | grep 回報線` 四行齊 +
`reply_connected=1` 即 PASS;此後早上不需為回報線重啟。

結果:待 prod 重啟。
