# mod/shutdown-budget — change-spec(A1:關機預算同源)

需求原文 = `docs/superpowers/specs/2026-08-25-do-batch-review.md` §2.6 Standards 1 + Spec 2、§3.2、§5 A1。
handoff `%TEMP%\copycat-handoff-2026-08-26-fixes.md` 順位 1;`/auto` 鏈式第一批(A1 → A4 → A8 → A6 → B)。

---

## §0 現況 vs 目標

### 0.1 現況(review 親核屬實)

| 面 | 現況 |
|---|---|
| `run.ps1` graceful 窗 | 寫死 **15 s**,註解只歸因 `_ensure_connected` 持鎖跨 `Connect()` 的 10 s 一發 |
| `app.py` lifespan `finally` | crosscheck → breadth → signals → **corr → futures → index → stock → runtime 序列 `await close()`** → capital(COM join ≤ 5 s) |
| 每條 TC4 session 的 `close()`(`tc4.py:894`) | `_stop.set()` → 取 `_api_lock`(在途 `Connect()` 最壞 **10 s**)→ 逐 symbol `UNSUBQUOTE`(任一 REQ 撞 RCVTIMEO **10 s** 即 break + `_dispose`)→ `_dispose`(等 `api.lock` **12 s** + `Disconnect()`) |
| 最壞情況 | 五條 session **序列** × (10 + 10 + 12) s + 5 s ≫ 15 s → `Stop-Tree` 硬殺在退訂中途,**健康的 session 也跟著變殭屍**(下一台開頭 ~60 s 零推播 —— 正是 #105 要修的病) |
| console | run.ps1 只印「15s 內未結束」,零指向哪一段吃掉時間;server log 無關機各段耗時 |
| uvicorn | `uvicorn.run(app, host, port)` 未帶 `timeout_graceful_shutdown` = 無上限等 WS 收完才進 lifespan(review Spec 2 後半) |

### 0.2 目標

1. **TC4 session 的 close 改為並行 lane**(review A1 候選二「close 改並行 + 總上限」):
   `gather(corr → futures 串鏈, index, stock, runtime)`。健康 session 的 UNSUB + LOGOUT 不再排在
   卡住的那一條後面 —— 硬殺只會落在**真的卡住**的 session 上。
2. **關機預算單一產生點** `copycat/server/shutdown_budget.py`:
   - `tc4.close_worst_secs()` = 2 × `_REQ_TIMEOUT_MS`/1000 + `DEFAULT_LOCK_TIMEOUT_SECS`(單條 session 上界);
   - `lifespan_close_worst_secs()` = `TC4_LANE_DEPTH`(2,corr→futures 串鏈)× 單條上界 + `COM_JOIN_TIMEOUT_SECS` + slack;
   - `run_grace_secs()` = `WS_DRAIN_SECS` + lifespan 上界 → **run.ps1 以 `python -c` 讀這個數字**,不再寫死。
3. **console 印哪段吃掉時間**:lifespan 每段 close 計時,收尾一行 `關機收尾 %.2fs:breadth … / corr … / capital …`;
   單段超過 `SLOW_CLOSE_WARN_SECS` 另印 WARNING 點名;`tc4.close()` 自己印「等鎖 / UNSUB 檔數 / 秒數」;
   run.ps1 超時訊息改指向 server log 那一行。
4. uvicorn `timeout_graceful_shutdown=WS_DRAIN_SECS`:WS 收攤有上限,lifespan 一定輪得到。

### 0.3 `[auto-default]` 紀錄

- `[auto-default: 選「並行 + 總上限」而非「序列 × source 數同源推導」 | reason: 序列版的上界是
  5 × 32 + 5 ≈ 165 s,而且只要一條卡住其餘健康 session 仍等不到 LOGOUT;並行版把上界壓到 lane 深度
  × 單條,且結構上讓健康 session 不受卡住的那條拖累 —— 這才是 review 點名的失效(硬殺還原殭屍)]`
- `[auto-default: corr → futures 保留串鏈(lane 深度 2) | reason: app.py 既有註解明載「corr 讀
  futures.state(),必須排在 futures 之前收」;雖然以 event-loop 語意推演 gather 內先 cancel corr 的
  task 也安全,但那是靠「cancel 與 futures 清 `_source` 之間零 await」的隱含順序,不值得為省 32 s
  (只在**兩條同時卡住**才付)把文件化的不變式改掉]`
- `[auto-default: runtime.close() 納入同一個 try/except 續行傘 | reason: 現況它是唯一裸 await 的一段,
  拋了就跳過 capital close;lifespan :1004 註解宣稱的「各自 try/except 續行」白名單本來就該涵蓋它]`

---

## §1 白名單(每條先 grep 過 caller)

### 1.1 lifespan 關機序(唯一定義點 `app.py` lifespan `finally`)

- 白名單測試:`tests/server/test_boot_window.py` 全檔(`test_capital_com_teardown_runs_after_the_tc4_sources`
  斷言 capital 在 stock / txo 之後 —— 並行 lane 之後仍成立,capital 在 `gather` 之後)、
  `tests/server/test_calendar_wiring.py::TestCrosscheck*`(crosscheck BaseException 仍走完反序 close)、
  `tests/server/test_breadth_routes.py:508`(lifespan 離場必 `await breadth.close()`)、
  `tests/server/test_signal_routes.py:337-401`(CC-1 / CC-2:bot.close 拋不跳過 hub.close;摘掛點在 stock 之前)、
  `tests/server/test_verify.py`。
- 不變式逐字保留:crosscheck / breadth / signals 仍**序列且在 TC4 lane 之前**(signals 摘掛點依賴 stock 活著);
  corr 先於 futures;capital **最後**;每段各自 try/except 續行;例外 log 字面 `"<name> close 失敗(關機續行)"` 不變。
- `_boot` 的 cancel 分支(boot 中斷)不動。

### 1.2 `tc4.close()`(`tc4.py:894-913`)

- caller:四個 engine 的 `close()` 經 `asyncio.to_thread(source.close)`;`stock_source.close()` 走 `super().close()`。
- **另一 session 的分支 `fix/tc4-logout-and-cancel-reply-warning` 改寫 `close()` 尾段(加 `_logout`、
  `_LOGOUT_TIMEOUT_MS` 2 s)**,開工時尚未進 master → 本輪首三個 commit 對 `close()` 的改動只落在 UNSUB 迴圈
  段,尾段一行不動,留 3 行原文隔開。**該分支於本輪 review 期間 merge 進 master(`34484ed4`)**,rebase 時
  `tc4.py` 自動合併乾淨(只有 `app.py` 一段註解與 `tests/live/test_tc4.py` 檔尾兩個測試類相鄰衝突,手動保留兩邊)。
  rebase 後親核合併結果:UNSUB 失敗 → `_req` 內 `_dispose`、`_api` None → `close()` 尾段直接 return,LOGOUT 不送;
  LOGOUT recv 上界 2 s < REQ 10 s → `close_worst_secs` 的「只付一發 REQ」仍成立,不必加項。順手把計時延伸到
  LOGOUT + Disconnect 段(第三行 log),並把該分支註解 / 測試裡「run.ps1 15 s」的舊前提改成
  「`_LOGOUT_TIMEOUT_MS < _REQ_TIMEOUT_MS`」(**該變清單**:`test_close_sends_logout_for_the_live_session_after_unsub`
  的 `_LOGOUT_TIMEOUT_MS * 5 < 15_000` → `< _REQ_TIMEOUT_MS`;舊斷言的前提是 15 s 窗,本輪把窗改掉了)。
- 白名單測試:`tests/live/test_tc4.py::TestReqProtection::test_close_survives_unsub_failure`、
  `TestEnsureConnectedShutdownRace`、`tests/live/test_stock_source.py` 的 close / timer 取消整組。
- 建構子 `lock_timeout_secs: float = 12.0` 改引 `DEFAULT_LOCK_TIMEOUT_SECS`(🔵,值不變;
  `TestLockTimeoutContract` 釘住不等式)。

### 1.3 `CapitalClient.close()`(`client.py:596`)

- `t.join(timeout=5)` → `COM_JOIN_TIMEOUT_SECS`(🔵,值不變)。另一 session 同檔改的是 :390 附近,無重疊。
- 白名單:`tests/capital/test_client.py` 全檔。

### 1.4 `__main__.py`

- `uvicorn.run` 多帶 `timeout_graceful_shutdown`。白名單:`tests/server/test_main_wiring.py` 全檔
  (既有斷言只看 `run_kwargs["port"]`,不鎖整份 dict)。

### 1.5 `run.ps1`

- 無自動化測試(PowerShell)。**必須維持 UTF-8 with BOM**(檔頭註解)。改動:graceful 上限改讀
  Python 產生點;訊息改指向 server log。parity 由 `tests/server/test_shutdown_budget.py` 以字串
  grep 釘住(檔內不得再出現寫死的 `TimeoutSecs = <數字>` 預設)。

---

## §2 backward compat

| 面 | 影響 |
|---|---|
| HTTP / WS 契約 | 零改動 |
| frontend | 零改動 |
| 關機順序 | corr→futures / signals→stock / capital 最後 三條依賴逐字保留;其餘由序列改並行(對外只有「健康 session 更常來得及 LOGOUT」) |
| run.ps1 | 起站多一次 `python -c`(讀預算,毫秒級);Ctrl+C 最壞等待由 15 s 變 `run_grace_secs()`(正常仍 1–3 s);預算讀不到直接 Fail(同 `import fastapi, uvicorn, zmq` 前置檢查慣例) |
| uvicorn | WS 收攤多一個上限(`WS_DRAIN_SECS`);到期後 uvicorn 自己 cancel 剩餘 WS task,relay 的 CancelledError 路徑既有 |

## §3 seams(測試落點)

| seam | 測什麼 |
|---|---|
| `create_app` + fake source 的 `close()` 順序戳(`test_boot_window.py` 既有形狀) | (a) stock close 卡住時 txo / index 仍先收完(lane 並行);(b) corr 仍先於 futures;(c) runtime.close 拋 → capital 仍收;(d) 「關機收尾」彙總 log 含各段 |
| `shutdown_budget` 純函式 | 三個數字的不等式(run ≥ ws + lifespan;lifespan ≥ 2 × 單條 + COM join);單條 ≥ 2 × REQ + lock |
| `run.ps1` 字面 | 引 `run_grace_secs`、無寫死預設 |
| `TC4QuoteSource.close()` + `FakeApi` | 一行「等鎖 / UNSUBQUOTE n/m」log |
| `__main__.main` + `_Capture` | `timeout_graceful_shutdown == WS_DRAIN_SECS`(prod 與 --verify) |
| `CapitalClient.close()` | join timeout 引常數 |

## §4 review round 1 逐條處置

判定欄:**接受** = 照 review 修 / **接受(變形)** = 收同一個問題但手段不同 / **反駁** = 技術上站不住,附理由 /
**申報** = 做不到或只做一半,理由與留尾寫在此。

### Standards

- **ST1 P3 [hard] 常數無型別註記** — **接受**:`DEFAULT_LOCK_TIMEOUT_SECS: float` / `COM_JOIN_TIMEOUT_SECS: float` /
  `shutdown_budget` 四個常數全加。
- **ST2 P2 Speculative Generality `close_worst_secs(lock_timeout_secs=)` 零 caller** — **接受**:改無參數,內部直接引
  `DEFAULT_LOCK_TIMEOUT_SECS`。
- **ST3 P2 「`0392f4f1` merge 後最壞 42 s」** — **反駁**:UNSUB 撞 RCVTIMEO 時 `_req` 內已 `_dispose`,close() 尾段
  `_connection()` 拋 ConnectionError 直接 return,**不會再送 LOGOUT**;反之退訂全過才輪到 LOGOUT 逾時。兩路互斥,
  仍只付一發 REQ。但 docstring 首版沒把互斥寫明,已補;並在 next-time 記「該分支若改成 UNSUB 失敗仍送 LOGOUT,算式 +1 REQ」。
- **ST4 P3 彙總行段序隨完成序漂** — **接受**:`_SHUTDOWN_SEGMENTS` 固定序輸出。
- **ST5 P3 `[int]$graceSecs` 多行時非 Fail 訊息** — **接受**:取 stdout 末行 + `^\d+$` 檢查,不過就 `Fail` 帶原字串。
- **commit 邊界:🔵 `f34ad222` 含新函式 `close_worst_secs`(當時零 caller)** — **接受(記錄偏離,不重寫歷史)**:行為確實不變,
  嚴格屬 🟢;下不為例。

### Spec

- **SP1 P2 `close_worst_secs` 算漏 `_req` 進門的 `api.lock`(12 s)** — **接受(變形)**:reviewer 的 44 s 是重複計(拿到鎖
  就走 REQ 路徑,finally 釋鎖後 `_dispose` 立刻拿到;毒鎖路徑才是 `_req` 等 12 + `_dispose` 等 12,且沒有 send/recv)。
  正確上界 = `req + max(2·req, 2·lock)` = 10 + 24 = **34**(首版 32 少 2 s);lifespan 78、run.ps1 **83**。測試改成兩條
  路徑各一個不等式。
- **SP2 P2 「`Disconnect()` 毫秒級」不成立** — **接受(變形)**:親核 wrapper `ThreadProcess`(:292-303):`Pong` 在 try 外,
  recv 逾時會帶著 `api.lock` 死 → `_dispose` 取不到鎖**跳過** Disconnect(不卡);decode 類例外殺執行緒時鎖已釋放、
  socket 永不關 → `term()` 才無界。改口:上界只宣稱**可計段**,`Disconnect` 標為「無上界不計,那條 lane 正是硬殺要落的
  對象」;wrapper 修法入 next-time(gitignored 本地檔,獨立處理)。
- **SP3 P2 硬殺那一刻零正向訊號** — **接受**:`_close_segment` 進場印「關機 <段> 段開始」;`tc4.close()` 拆成兩行(取到
  鎖即印「等 api 鎖 … 開始 UNSUBQUOTE n 檔」,迴圈後印「n/m 檔 秒數」)。事後由「誰有開始沒結束」指認。
- **SP4 P3 `TC4_LANE_DEPTH` 自證** — **接受**:新增 `test_lane_depth_matches_the_real_shutdown_shape`(五條 session 全卡,
  同時進場條數 = 5 − depth + 1;corr 放行前 futures 不得進場)。
- **`[auto-default]` 三項無方向性抉擇** — 同意;**Ctrl+C 最壞等待 15 s → 83 s 屬使用者手感改變**,升為收尾回報的「需
  user 知情」項(正常仍 1–3 s)。
- **verification §3 gate 未核 / §1 第 4 列尚未 commit** — 收修後全套 gate 重跑一次,數字更新;docs 隨 chore commit 落。
