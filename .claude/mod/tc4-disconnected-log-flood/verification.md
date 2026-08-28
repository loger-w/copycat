# mod/tc4-disconnected-log-flood — verification

## 1. Commits(🟢 測試 → 🔴 行為)

| SHA | 類 | 內容 |
|---|---|---|
| `f7702e49` | 🟢 test | 紅先行:`TestHealWhileDisconnected` 4 條 + `TestReconnectFailureTraceback` 2 條 + change-spec |
| `89ef7f99` | 🔴 fix | `_is_connected()` / `_heal_tick` 未連線整輪跳過 + 一次性等連線行 / `_check_stale` failures 計數;事前標該變 §4 一條 |
| `85d97886` | 🟢 test | review round 1 紅先行:P-1 窗外復位 / P-3 關機靜默 / P-2 換形狀 / S-4 `(#1)` / S-5 巡檢輪數 / S-7 |
| `98b2e22f` | 🔴 fix | review round 1 收修(change-spec §5 處置表) |

## 2. 紅 → 綠

紅態(`f7702e49` 當下,`-k "TestHealWhileDisconnected or TestReconnectFailureTraceback"`):**6 failed / 88 deselected**
- `skips_accounting…`:`AssertionError: 未連線那輪不得記帳`(attempts 被記)
- `prints_once_per_outage`:`assert 0 == 1`(沒有等連線行)
- `prints_again_for_a_new_outage`:`assert 0 == 2`
- `heals_from_a_clean_ladder`:`{…: 3} == {…: 1}`(斷線兩輪已把 attempts 推到 3)
- `first_failure_has_traceback_then_one_liners`:`第 2 發不得再印 traceback`
- `counter_resets…`:`[True, True, True] == [True, True, False]`

綠態(`89ef7f99`):`tests/live/test_tc4.py` **94 passed**。

事前標該變(change-spec §4)`test_heal_thread_survives_failing_requests`:改後測試對**舊實作**(`git stash push copycat/live/tc4.py`)
紅 —— `AssertionError: 第一發 REQ 例外仍要記帳`(舊碼 attempts 已跑過 1);對新實作綠。

## 3. Gate(repo root,89ef7f99)

- `pytest -q`:**3151 passed**(89ef7f99)→ **3154 passed**, 1 warning, 193.96 s(98b2e22f)
- `ruff check copycat tests`:All checks passed
- `pyright`:0 errors, 0 warnings
- `copycat validate`:**42/42 PASS**(兩次)
- frontend 未動,不跑前端 gate。

## 4. Mutation 證據

- 整段實作缺席(紅先行 commit)= 6 條紅(§2)。
- 舊實作 vs 改後既有測試(stash)= 紅(§2 末段)—— 證明「未連線不記帳」的斷言真的綁到行為。

## 5. 真實環境判準(部署後)

- 部署 = prod 8721 重啟(這次重啟同時充當 A7 的 WS 重連驗:分頁開著 → 重啟 → console 一輪「重連」後安靜、uvicorn 一輪 6 條 accepted 後不再增加)。
- 下次達錢 4 斷線(user 刻意關或真事件),`logs/server-<日期>.log` 應呈現:
  - 每條 session 一行 `TC4 REALTIME 自癒:quote 未連線,N 腿待重連後接手(略過巡檢,不記帳)`;斷線期間 `grep 零推播自癒` **0 筆**、
    `grep 自癒重掛失敗.*not connected` **0 筆**。
  - `reconnect attempt failed` 第一發後接 `Traceback`,之後為 `reconnect attempt failed (#n): ConnectionError: …, backoff 60s` 單行,
    `grep -c Traceback` ≈ session 數(5)而非 ×3×發數。
  - 接回後 `TC4 reconnected (total=n)` 照印;第一次真自癒 `attempt 1, window_variant=0`(乾淨帳本)。
- 同長度斷線的預估體積:11.5 分鐘 6764 行 → ≈ 6764 − 4100(traceback)− 2412(自癒)+ 5(等連線)+ 70(單行)≈ **330 行**。

## 6. Review round 1(two-axis,opus / high)

Standards 8 條(S-1 P2、S-2/S-3/S-4 P3、S-5~S-8 nit)、Spec 5 條(P-1 P2、P-2/P-3 P3、P-4/P-5 nit);零 P1。
P-1 = S-1 同一顆:旗標復位綁在「時窗開著且有腿」那條路,index 源 13:2x 斷、窗關後接回 → 整夜卡 True → 次日靜默不印。
紅態(`85d97886` 當下,`-k "TestHealWhileDisconnected or TestReconnectFailureTraceback or test_heal_thread_survives"`):
**5 failed / 5 passed** —— `assert 1 == 2`(窗外不復位)、`[…] == []`(關機仍印)、`'(#1)' in 'reconnect attempt failed, backoff 1s'` ×3、
換形狀 `[True, False, …, True] == […, False]`。綠態(`98b2e22f`):test_tc4 **97 passed**。
處置表見 change-spec §5(S-4 部分做、S-6 不做,其餘全修)。
