# mod/shutdown-budget — verification(A1 關機預算同源)

分支 `mod/shutdown-budget`(worktree `C:\side-project\copycat-wt-a1`,自 master `93f8c303` 切)。
**零 TC4 / 零 ZMQ / 零群益**:全程 fake source,未起任何連 TC4 的程序、未碰 prod 8721。

---

## 1. commits(PR 內序號;SHA 在 rebase merge 後會改寫,以 subject 為準)

| # | 類 | subject |
|---|---|---|
| 1 | 🔵 | `refactor(backend): 關機預算的兩個輸入抽成具名常數 + close_worst_secs 純函式(行為不變)` |
| 2 | 🟢 | `test(backend): [red] 關機 lane 並行 / 預算不等式 / close 計時 log / uvicorn WS drain 上限` |
| 3 | 🔴 | `fix(backend): 關機 TC4 session 改並行 lane,graceful 窗三方同源 + 各段計時(review A1)` |
| 4 | 🔴 | `fix(backend): review round-1 收修 —— 單條 session 上界補毒鎖路徑(32→34 s)、段進場先印、彙總固定序、lane 深度釘住` |
| 5 | 🔴 | `fix(tc4): rebase 到 fix/tc4-logout 之後 —— close() 計時延伸到 LOGOUT + Disconnect,LOGOUT 上界改綁 _REQ_TIMEOUT_MS`(rebase 後才可能做;change-spec §1.2) |
| 6 | chore | docs(CLAUDE.md §4 契約 / next-time 留尾)+ artifacts |

rebase 紀錄:review 期間 origin/master 進了 `fix/tc4-logout-and-cancel-reply-warning`(`34484ed4`,同動 `tc4.close()` 尾段);
`git rebase origin/master` 兩處相鄰衝突(`app.py` 一段註解、`test_tc4.py` 檔尾兩個測試類)手動保留兩邊,`tc4.py` 本體自動合併。
rebase 後全套 gate 重跑(§3 數字即 rebase 後)。

commit 邊界偏離(記錄,不重寫歷史):#1 含新函式 `close_worst_secs`(當時零 caller,嚴格屬 🟢);#4 隨同型別註記與
零 caller 參數移除(嚴格屬 🔵)。兩者行為皆不變;下不為例。

## 2. 紅態證據(TDD)

`pytest tests/server/test_boot_window.py tests/live/test_tc4.py -k "ShutdownLanes or CloseTiming"`
(實作前)→ **4 failed, 1 passed**:

| 案 | 紅態 |
|---|---|
| `test_stuck_stock_close_does_not_delay_the_txo_and_index_sessions` | `order` 實得 `['index', 'stock:enter', 'stock:exit', 'txo']`(序列 close,txo 排在卡住的 stock 後面) |
| `test_txo_close_failure_does_not_skip_capital` | `'capital' in ['txo:raise']` 失敗(runtime.close 裸 await 拋 → capital 跳過) |
| `test_shutdown_summary_names_every_segment` | 彙總行 `[]` |
| `test_close_logs_lock_wait_and_unsub_count` | `caplog.text == ''` |
| `test_corr_still_closes_before_futures` | **實作前即綠**(白名單 lock:並行化不得拆掉串鏈) |

`tests/server/test_shutdown_budget.py` / `test_main_wiring.py`:collection 即
`ImportError: cannot import name 'COM_JOIN_TIMEOUT_SECS'` / `'shutdown_budget'`。

review 收修新增 `test_lane_depth_matches_the_real_shutdown_shape`(SP4):反向 mutation `TC4_LANE_DEPTH` 2→3 →
`assert 4 == ((5 - 3) + 1)` **1 failed**;還原 + `sleep 1`(避同秒 pycache)→ 1 passed;`grep -c MUTANT` = 0。

治具自陷兩次(記帳):
- `TestCloseTiming` 首版 `_subscribed = {"TC.F.TWF.TXF.HOT", SPOT_SYMBOL}` —— 同一個字串,set 只有 1 個元素,實作後仍紅
  (`UNSUBQUOTE 1/1`)。換成兩個不同 symbol 才綠。
- lane 深度測試首版的觀察者對 `futures` 也 `wait(_GATE_CAP)`,吃滿 15 s 時 corr 的 gate 同樣到期放行、futures 真的進場 →
  假紅(`futures_before_corr_released` True)。改成只等四條 lane 頭。

## 3. 完成前 gate(worktree,`C:\side-project\copycat\.venv\Scripts\python`)

| gate | 結果 |
|---|---|
| `-m pytest -q`(rebase + 收修後全量,HEAD = commit 5) | **3053 passed, 1 skipped**, 194.78 s(本輪新增 16 案:shutdown_budget 10 / boot_window 5 / tc4 1;其餘 3037 = master `34484ed4` 既有,含另一分支新增) |
| `-m ruff check copycat tests` | **All checks passed!** |
| `-m pyright` | **0 errors, 0 warnings, 0 informations** |
| `-m copycat validate` | **42/42 PASS**(在主 tree 跑:replay 程式碼本輪零改動,worktree 無 `out/` 產物) |
| frontend | 未動 `frontend/` → 不適用 |
| `run.ps1` | `[Parser]::ParseFile` → `parse OK, no errors`;檔頭 bytes `EF BB BF`(UTF-8 BOM 保住) |

skipped 那 1 條 = `tests/backtest/test_characterization.py:47`(需 `data/` 匯入產物,worktree 沒有),既有 skipif,非本輪。

## 4. 真實環境節(happy + edge + 未改功能抽查)

### 4.1 happy:真 uvicorn + 真 lifespan 的 lane 量測(SC-1)

`evidence/shutdown_lanes_probe.py`(fake source、`neutralize_external_env` 先於 `create_app`、
自選檔落 tmp 隔離目錄、port 0)。形狀:stock / index 的 `close()` 各睡 2 s,txo 即時。
輸出 `evidence/shutdown_lanes_probe.out.txt`(收修後重跑):

```
copycat.server.app INFO 關機 signals 段開始
copycat.server.app INFO 關機 index 段開始
copycat.server.app INFO 關機 stock 段開始
copycat.server.app INFO 關機 txo 段開始
[probe] txo close t=0.19s
[probe] index close enter t=0.19s
[probe] stock close enter t=0.19s
[probe] stock close exit  t=2.19s
[probe] index close exit  t=2.19s
copycat.server.app WARNING 關機 stock 段耗時 2.0s(> 2s):在途 Connect 持鎖或 TC4 REQ 逾時,細節看該 source 的「TC4 quote close」行
copycat.server.app WARNING 關機 index 段耗時 2.0s(> 2s):…
copycat.server.app INFO 關機收尾 2.00s:signals 0.00s / index 2.00s / stock 2.00s / txo 0.00s
[probe] shutdown wall = 2.19s (SLOW=2.0s; 序列版 >= 4.0s, 並行版 ≈ 2.0s)
[probe] thread alive after join = False
[probe] RESULT = PASS
```

三條 session **同一瞬間**進場(0.19 s),牆鐘 2.19 s ≈ 一條的耗時而非兩條相加;段進場行、慢段 WARNING、彙總行
(固定段序)都印出 —— run.ps1 超時訊息指的就是這些行。

### 4.2 run.ps1 的那句 `python -c`(SC-2)

worktree 內逐字執行 run.ps1 的取數句:`run_grace_secs()` = **83**(`lifespan_close_worst_secs` 78.0 =
2 × 34.0 + 5 + 5;`close_worst_secs` 34.0 = 10 + max(20, 24);`WS_DRAIN_SECS` 5),末行 `^\d+$` 檢查與
PowerShell `[int]` 解析 OK,exit 0。

### 4.3 edge

- **TXO close 拋例外**:`test_txo_close_failure_does_not_skip_capital` —— capital 仍 join(改動前跳過)。
- **UNSUB 中途失敗**:既有 `test_close_survives_unsub_failure` 仍綠(計時碼落在 try 之外,break 路徑不變)。
- **boot 中斷關機**:`TestShutdownDuringBoot` 兩條仍綠(`_boot` 的 cancel 分支零改動)。
- **五條 session 全卡**:`test_lane_depth_matches_the_real_shutdown_shape` —— 同時進場 4 條、futures 等 corr 放行才進。

### 4.4 未改功能抽查

- `tests/server/test_calendar_wiring.py::TestCrosscheck*`(crosscheck BaseException 仍走完反序 close)綠。
- `tests/server/test_signal_routes.py` CC-1 / CC-2(bot.close 拋不跳過 hub.close;摘掛點在 stock 之前)綠。

## 5. 白名單逐條核對(change-spec §1)

| 白名單 | 結果 |
|---|---|
| `tests/server/test_boot_window.py` 全檔(含 `test_capital_com_teardown_runs_after_the_tc4_sources`) | 綠(capital 仍在 gather 之後) |
| `tests/server/test_calendar_wiring.py` / `test_breadth_routes.py:508` / `test_signal_routes.py:337-401` / `test_verify.py` | 綠 |
| `tests/live/test_tc4.py` 全檔(`test_close_survives_unsub_failure` / `TestEnsureConnectedShutdownRace` / `TestLockTimeoutContract`) | 綠 |
| `tests/live/test_stock_source.py` close / timer 取消整組 | 綠 |
| `tests/capital/test_client.py` 全檔 | 綠 |
| `tests/server/test_main_wiring.py` 全檔 | 綠 |
| `tc4.close()` 首三 commit 只動 UNSUB 迴圈段(另一 session 的 hunk 在尾段) | Standards reviewer 親核:改動止於新增的 `logger.info(...)`,`# 失敗路徑 _req 內已 _dispose` 起逐字未動;rebase 後自動合併,commit 5 才碰尾段(只加計時一行) |
| `tests/live/test_tc4.py::TestCloseLogout`(另一分支剛進 master 的五條) | 綠;其中一條斷言 `_LOGOUT_TIMEOUT_MS * 5 < 15_000` 依「該變清單」改為 `< _REQ_TIMEOUT_MS`(舊前提 15 s 窗已被本輪取代) |

## 6. 需 user 過目 / 真環境(**非盤中**,下次收工時)

### 6.0 知情:Ctrl+C 最壞等待由 15 s 變 83 s

正常收尾仍 1–3 s(§4.1 形狀),83 s 只在 TC4 半死時被吃滿 —— 但那 83 s 內 backend 不會被硬殺,使用者手感上是
「Ctrl+C 後最多等一分多鐘」。要縮短只能動 socket RCVTIMEO(next-time),或接受。

### 6.1 run.ps1 Ctrl+C(取代 #105 verification §6.1 的舊判準)

1. `.\run.ps1` 起站(啟動階段多一次 `python -c` 讀預算,毫秒級)→ Ctrl+C。
2. 期望腳本印:
   `[run] 等 backend 自行收尾(TC4 退訂 + LOGOUT + Disconnect;正常 1–3s,上限 83s = 關機預算) ...`
   後接 `[run] backend 已自行結束(TC4 session 已 LOGOUT)`。
   黃字 `83s 內未結束(超過關機預算上界)` → 某條 session 真的卡滿上界,回報時附下一步的兩行。
3. server log(`logs/server-*.log`)尾段應有:
   - 每段一行 `關機 <段> 段開始`(breadth / signals 先,接著 corr / index / stock / txo **四行貼秒**,futures 在 corr 之後,
     capital 最後);
   - 每條 TC4 session 三行 `TC4 quote close:等 api 鎖 0.0Xs,開始 UNSUBQUOTE n 檔` / `UNSUBQUOTE n/n 檔 0.XXs` /
     `LOGOUT + Disconnect 0.XXs`(n = 該 session 訂閱數;stock 那條 n ≈ 自選檔數 + 指數;第三行沒印 = 卡在
     KeepAlive term());
   - 一行 `關機收尾 T s:breadth … / signals … / corr … / futures … / index … / stock … / txo … / capital …`,**T 應在 1–3 s**;
   - **不應**有 `關機 <段> 段耗時 … (> 2s)` WARNING(有 = 那一段值得看,不一定是 bug:在途 Connect 持鎖是合法慢)。
   - 被硬殺時:哪一段「有開始沒結束」就是卡住的那條。
4. TC4 端對帳同 #105 §6.1 判準:`grep "RemoveLoginInfo" QuoteZMQService-YYYYMMDD-0.log | tail` 時戳**貼著**
   Ctrl+C(±2 s);下一台開頭 60 s 不應再有 `零推播自癒` 整批重掛。

### 6.2 uvicorn WS drain 上限(review Spec 2 後半)

Ctrl+C 時若有分頁開著(8 條 WS),uvicorn log 應在 ≤ 5 s 內從 `Shutting down` 走到 `Waiting for application shutdown`;
超過 5 s 才進 lifespan = WS 收攤撞上限,uvicorn 會印 `Cancelling N running task(s)`。看到那行不是錯,但值得回報(代表
某條 WS 對端沒回 close frame)。

## 7. 未做 / 留尾(已回填 `docs/next-time.md` 2026-08-26 節)

- signals 段無上限,只算進 slack 5 s。
- run.ps1 finally 內第二次 Ctrl+C 行為未驗。
- 83 s 是 TC4 半死**可計段**的上界不是承諾;`Disconnect()` 的 KeepAlive `term()` 無上界(wrapper `ThreadProcess` 只 catch
  ZMQError),修法入 next-time。
- (已解)`tc4.close()` 計時不含 LOGOUT / Disconnect 段、「只付一發」merge 後重核 —— 該分支 review 期間已進 master,
  rebase 後兩項都在 commit 5 收掉。
- `ops-discipline/SKILL.md:67`「首則 ping 才武裝」(review §3.1)本輪**未動**:主 tree 該檔有他 session 未提交修改。

## 8. review round 1

`code-review-round-1.json`:Standards 5+1 條(接受 4、反駁 1、偏離記錄 1)/ Spec 4+2 條(接受 2、接受(變形)2、
知情 2)。逐條處置與反駁理由見 change-spec §4。收修後本檔 §3 / §4 數字全部重跑更新。
