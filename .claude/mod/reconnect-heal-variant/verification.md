# mod/reconnect-heal-variant — verification(A6)

分支 `mod/reconnect-heal-variant`(worktree `C:\side-project\copycat-wt-a1`,自 origin/master `44bb3fe8` 切)。
**零 TC4 / 零 ZMQ**:fake source 與 `sys.modules` 注入的 QuoteAPI 替身;未碰 prod 8721。

## 1. commits

| # | 類 | subject |
|---|---|---|
| 1 | 🟢 | `test(backend): [red] TC4 重連重抓沿用自癒 variant;收工分支 Disconnect 必持 api.lock(review A6)` |
| 2 | 🔴 | `fix(backend): TC4 重連後的 index 重抓沿用當前自癒 variant;收工分支 Disconnect 改走持鎖 helper(review A6)` |
| 3 | 🟢 | `test(backend): [red] 重連重抓零新鍵且 variant > 0 → 階梯推前(review A6 round-1 SP1)` |
| 4 | 🔴 | `fix(backend): review round-1 收修 —— 重連無進展 bump variant + 重連 log、WARNING 字面、docstring 回校、測試改 wait_until` |
| 5 | chore | artifacts |

round-1 紅態:`test_reconnect_retry_without_progress_advances_the_variant` → `wait_until` 逾時(variant 停在 2)**1 failed**。

commit 邊界偏離(記錄):#2 含 `_disconnect_locked` helper 抽出(🔵),與 🔴 同 hunk(收工分支改呼 helper)。

## 2. 紅態證據(TDD)

`pytest tests/server/test_index_engine.py::test_reconnect_retry_keeps_the_heal_variant tests/live/test_tc4.py::TestEnsureConnectedShutdownRace`
(實作前)→ **2 failed**:
- reconnect:`window_variants` 實得 `[0, 0]`(boot 0 + 重連 0)→ `assert 0 == 2`。
- 收工分支:`disconnect_locked` 實得 `False`。

## 3. 完成前 gate

| gate | 結果 |
|---|---|
| `pytest -q`(全量,round-1 收修後) | **3055 passed, 1 skipped**(178.01 s;基準 3053 + 2 新案,另一斷言加在既有案內) |
| `pytest tests/server/test_index_engine.py tests/live/test_tc4.py tests/live/test_stock_source.py` | 199 passed |
| `ruff check` / `pyright` | All checks passed / 0 errors |
| `copycat validate` | 未重跑(replay 程式碼零改動;A1 那輪 42/42 為基準) |
| frontend | 未動 |

## 4. 真實環境節

零 TC4 可用(盤後、且紀律:不起第二台連 TC4 的後端)。兩條改動的真環境判準:

- **reconnect 沿用 variant**:prod 重啟後,盤後若 log 出現 `index 分時自癒:minutes 落後 … (window_variant=N)`(N ≥ 1)
  接著 TC4 重連,應看到新 log `index 重連重掛 + 重抓(window_variant=N)`(N 不是 0);若再接一行
  `index 重連重抓無進展(window_variant=N)` = 新 session 的 N 號窗也是 stub,階梯已推前,下一發自癒用 N+1。
  分時線不凍結。
- **收工分支持鎖**:只在「Ctrl+C 落在某條 session 的 Connect() 期間」才走到;可觀察差異 = 該 session 的 close 不再有
  「兩執行緒同碰 socket」的 crash 風險。無正向 log(取不到鎖時印既有 `api.lock busy` WARNING)。

## 5. 白名單逐條核對

| 白名單 | 結果 |
|---|---|
| `tests/server/test_index_engine.py` 全檔(single-flight / 自癒 variant 四案 / `TestRetrySupersededSideEffects` / lag recovery) | 綠 |
| `tests/live/test_tc4.py`(`TestEnsureConnectedAtomic` 四 source / `TestReqProtection` / `TestCloseLogout`) | 綠 |
| `tests/live/test_stock_source.py` | 綠 |
| `_schedule_retry` 其他三個 caller(start 失敗 / rollover 失敗 / 分時自癒)零改動 | `git diff` 核:只加 `_schedule_reconnect_retry` |

## 6. 需 user 過目 / 真環境

無畫面改動。prod 重啟後盤後看 §4 第一條(log 對帳);仍跑 3fabfc7e 的 prod 未含本輪。

## 7. review round 1

(見 `code-review-round-1.json`)
