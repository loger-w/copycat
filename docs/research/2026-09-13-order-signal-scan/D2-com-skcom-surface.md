# D2 — 下單:COM 層與 SKCOM API 表面

> 區塊:`copycat/capital/com.py`(337 行,整檔讀完)、`copycat/capital/factory.py`(122 行,整檔讀完)、
> `copycat/capital/client.py`(1217 行,整檔讀完)的 COM 互動段 + `copycat/capital/mapping.py`(297 行)
> + `copycat/server/audit.py` + `copycat/server/shutdown_budget.py` + `copycat/server/app.py` lifespan capital 段。
> 掃描日期 2026-09-13 · 準繩:**這是一個要下實單的系統**。
>
> **證據等級標示**:`[實測-prod]` = 從 `logs/server-*.log`(15 檔)或 `data/audit/capital-*.jsonl`(22 檔 / 1,075 筆)
> 回推的真實數字;`[實測-本機]` = 本輪寫的 micro-benchmark(`scratchpad/order-signal-scan/bench_com.py`,可重跑);
> `[typelib]` = 直讀 `comtypes.gen` 產生的早期繫結 wrapper(`_75AAD71C_…_0_1_0.py`,6,045 行);
> `[推估]` / `[推測]` = 沒量到的,明寫。
>
> 上一輪 `B10-capital-order.md` 已覆蓋的內容不重述;本報告只放**它沒挖到的**,並在三處**推翻/修正**它。

---

## 0. 三句話結論

1. **這條鏈唯一的黑盒已經被量出來了**:`SendStockOrder` 同步 COM 呼叫的期望值 ≈ **84 ms**、
   `P(≥1 s) = 7.6%`、**實測最大 4 秒**(499 筆審計 pre/post 配對)。而那 4 秒期間,
   **唯一的 COM 執行緒不 pump**,所有委託/成交回報全部堆在 COM 訊息佇列裡。
2. **回報斷線偵測是死碼**:65 次 prod session、3,531 則 `OnNewData`,`OnConnect` / `OnDisconnect`
   **一次都沒觸發過**。`_handle_reply_disconnect` → `degraded` 這條「委託面板跟市場脫節」的唯一警報,
   從上線到現在沒有被驗證過能響。這是本輪最重要的零錯誤訊號路徑。
3. **SKCOM 表面用掉不到 5%**:147 個方法只用了 12 個。沒用到的裡面有三類是**這個系統缺什麼就給什麼**的:
   非同步下單(`bAsyncOrder=1` + `OnAsyncOrder`,解 head-of-line blocking)、
   拉式對帳(`GetOrderReport` / `GetFulfillReport`,解 timeout 後「單到底在不在市場上」)、
   券商端風控與緊急撤單(`SetMaxQty` / `SetMaxCount` / `CancelOrderByStockNo` / `CoverAllProduct`)。

---

## 1. 現況地圖:COM 層實際怎麼運作

### 1.1 執行緒模型(Q1)

```
uvicorn MainThread (event loop, ProactorEventLoop)
   │  submit_stock_order → _execute_write
   │    ├ safety gate(純算術)
   │    ├ await to_thread(_audit 前置)  ← 共享預設 executor(20 workers)
   │    ├ fut = loop.create_future();  _cmd_q.put((com_call, fut))   ← queue.Queue() 無上界
   │    ├ await wait_for(shield(fut), 10 s)
   │    ├ self._com.return_code_message(code)   ★ 在 loop 執行緒上直呼 STA COM 物件
   │    └ await to_thread(_audit 後置)
   │
   └─ threading.Thread(name="capital-com", daemon=True) ── client.py:707-710
        _run():
          pythoncom.CoInitialize()          ← client.py:804;COINIT_APARTMENTTHREADED = 2 → **STA**
          _init_com()                        ← setup / SetAuthority / Login / InitOrder /
          │                                     ReadCert / ConnectByID / GetUserAccount
          while True:
              _pump_once()                   ← com.pump() + 3×collector.poll
              │                                + _maybe_query_balance() + _poll_pending()
              cmd = _cmd_q.get(timeout=0.05)  ← 實測 62.3 ms(見 §2)
              result = fn()                   ← SendStockOrder(user, **0**, order) 同步
              loop.call_soon_threadsafe(_settle, fut, result, exc)
          finally:
              _set_status("error"); _drain_pending()
              logger.error("capital-com 執行緒結束(status→error)")   ← 正常關機也走這裡
```

**`CoInitialize` 在哪**:`client.py:804`,`_run()` 的第一件事(在 `_init_com()` 之前)。
`pythoncom.CoInitialize()` 等於 `CoInitializeEx(NULL, COINIT_APARTMENTTHREADED)` →
**STA**(`[實測-本機]` `pythoncom.COINIT_APARTMENTTHREADED == 2`,且 `CoInitialize()` 回 `None` = S_OK)。
沒有對應的 `CoUninitialize()`;daemon thread 隨行程結束回收,COM 的 apartment 也就沒有正常收攤 ——
這在 `close()` join 逾時的路徑上是已知且被接受的(`client.py:712-719` docstring 明寫)。

**為什麼只能一條**:三個 CoClass(`SKCenterLib` / `SKOrderLib` / `SKReplyLib`)是
`comtypes_client.CreateObject(...)` 在這條 STA 執行緒上建的 in-proc 物件(`com.py:122-124`)。
STA 物件的方法只保證在建立它的那條執行緒上被呼叫是安全的;而 SKCOM 是**單一登入、單一 apartment**
的設計(登入狀態綁在 `SKCenterLib` 實例上,`SKOrderLib` / `SKReplyLib` 靠 `bstrLogInID` 對回同一個 session)。
所以「開第二條執行緒做寫入通道」在這個 API 下不成立 —— 上一輪 B10 F-04 講的硬約束我確認是對的。

**但「只能一條執行緒」不等於「只能一筆一筆同步等」** —— 那是 `bAsyncOrder=0` 帶來的,不是 apartment 帶來的。見 §3。

### 1.2 事件怎麼進來

`comtypes_client.GetEvents(self._reply, self._reply_sink)`(`com.py:129, 131`)在 STA 上建 advise 連線。
`[typelib]` `_ISKReplyLibEvents` / `_ISKOrderLibEvents` 都是 **dispinterface**(`_disp_methods_`),
共 12 + 29 = 41 個事件;而 `ISKOrderLib` / `ISKCenterLib` / `ISKReplyLib` 是 **`_methods_` = COMMETHOD 的 vtable 介面**
(`ISKOrderLib._methods_` 有 **147** 條)。

→ **呼叫方向是早期繫結(vtable),事件方向是晚期繫結(IDispatch::Invoke)**。這回答 Q6 的一半(見 §6)。

事件只在 `pythoncom.PumpWaitingMessages()` 被呼叫時 dispatch(`com.py:245-247`),
也就是**只在 `_pump_once()` 那一行**。COM 執行緒在別處(尤其是 `fn()` 裡)待多久,事件就堆多久。

comtypes 對 sink 上**未實作的事件靜默忽略**(`com.py:272` 的註解自承)。我們的 `_ReplyEvents` 實作 4/12、
`_OrderEvents` 實作 5/29 —— 剩下 32 個事件到達時**零痕跡**。

### 1.3 我們實際用到的 SKCOM 方法(12 / 147)

| 方法 | 呼叫點 | 頻率 |
|---|---|---|
| `SKCenterLib_SetAuthority` | `com.py:134` | 啟動 1 次 |
| `SKCenterLib_Login` | `com.py:137` | 啟動 1 次(**永不重登**) |
| `SKOrderLib_Initialize` | `com.py:140` | 啟動 1 次 |
| `ReadCertByID` | `com.py:143` | 啟動 1 次 |
| `SKReplyLib_ConnectByID` | `com.py:147` | 啟動 1 次 |
| `GetUserAccount` | `com.py:222` | 啟動 1 次(固定 3 s) |
| `SendStockOrder` / `SendFutureOrder` / `SendOptionOrder` | `com.py:154/165/167` | 每筆送單 |
| `CancelOrderBySeqNo` / `CorrectPriceBySeqNo` / `DecreaseOrderBySeqNo` | `com.py:172/181/190` | 每筆刪改減 |
| `GetRealBalanceReport` | `com.py:195` | 每 60 s + 每筆成交後 0.5 s |
| `GetProfitLossGWReport` | `com.py:210` | 同上(串行第 2 段) |
| `GetOpenInterestGW` | `com.py:240` | 同上(串行第 3 段) |
| `SKCenterLib_GetReturnCodeMessage` | `com.py:243` | 每筆寫入結果 + 每次查詢 rc≠0 |

### 1.4 `_init_com` 的登入與連線生命週期(Q3)

```
setup()  ── GetModule("SKCOM.dll") + import comtypes.gen.SKCOMLib  [實測-本機 50.9 ms]
         └ CreateObject ×3 + GetEvents ×2
SetAuthority(2 if env=="test" else 0)
   ├ test 且 rc≠0 → raise(絕不默認正式)         ← factory.py:96-99 + client.py:731-740
   └ prod 且 rc≠0 → WARNING 續行(預設即正式)
Login(user, pass) rc≠0 → raise
SKOrderLib_Initialize() rc≠0 → raise
ReadCertByID(user) rc≠0 → raise
SKReplyLib_ConnectByID(user) rc≠0 → degraded(送單仍可用)
GetUserAccount() → pump 迴圈 3.0 s → 取 TF 前綴當期貨帳號
status → ok / degraded
```

`[實測-prod]` **65 次 session 的「正式環境 banner → Capital login + cert OK」耗時**:
`p50 = 4.83 s`、`min = 4.41 s`、`max = 10.72 s`。
其中 `get_user_accounts(timeout_s=3.0)` 是**無條件的 3.00 s**(`com.py:225-228` 的迴圈**沒有提早結束**),
所以真正的 SKCOM setup + login + cert + connect_reply ≈ **1.83 s p50**、最壞 7.7 s。
→ server 起來後前 ~5 秒,`/api/capital/order/*` 一律 503 `CAPITAL_NOT_READY`。

**`CAPITAL_ENV`**:`factory.py:96-99` 只認 `test` / `prod`,其餘(含拼錯)→ `logger.error` + 回 `None`
= 群益功能**整個不啟用**(route 503 `CAPITAL_DISABLED`)。這是正確的 fail-safe 方向,**不要動**。
`test` 沙盒未開通已多次實證:`[實測-prod]` 全 log 共 **11 次** `Capital init failed: RuntimeError: Login: SK_ERROR_TELNET_LOGINSERVER_FAIL`(=1097)。

**重連 / 重登 / token 有效期**:
- **完全沒有**。`_init_com()` 回 `False` → `_run()` 直接 `return` → `finally` → 執行緒結束、`status=error`,
  **這個 process 的生命週期內不會再試一次**。
- 登入成功後也沒有任何 keep-alive / 重登。`[實測-prod]` `server-20260911-0905.log` 顯示同一個 process
  從 09-11 09:05 一路寫到 09-13 12:34 = **連跑 2 天 3.5 小時**,期間只有一次 login。
  群益 session 的到期行為**未實證**(open question)。
- 回報主機斷線的自動重連刻意不做(`client.py:455-462` docstring:重播 backlog 前必須先 `store.clear()`,另案)。

### 1.5 `GetUserAccount` 的期貨帳號自動發現(Q4)

```
com.py:212-236  get_user_accounts(timeout_s=3.0)
   sink.accounts.clear()
   code = self._order.GetUserAccount()          ← rc≠0 只 WARNING,照樣等滿 3 s
   while time.monotonic() < deadline:            ← 無提早結束
       self.pump(); time.sleep(0.05)
   → [_parse_account_row(raw) for raw in sink.accounts]
```
```
com.py:71-86  _parse_account_row("市場,經紀商,分公司,帳號,身分證,姓名")
   market = parts[0][:2].upper()      # TS=證券 / TF=期貨
   full_account = parts[1] + parts[3] # 經紀商 + 帳號
```
```
client.py:760-765
   self._futures_account = next((acct for mkt, acct in accounts if mkt.startswith("TF")), None)
   None → 期權寫入一律 gate "no_futures_account"
```

三個值得記的事實:
- **`OnAccount` 沒有「收完」訊號** → 只能以 timeout 收束。這是 SKCOM 的固有設計缺口,不是我們的選擇。
  但 3.0 s 是**寫死的**,沒有「收到第一列後再等 300 ms 就收工」的快路徑。
- **證券帳號不走這條**:`CAPITAL_FULL_ACCOUNT` 是 env 手設的(`factory.py:106`),
  `GetUserAccount` 回來的 `TS` 列**完全沒被用到**(`next(...)` 只挑 `TF`)。
  → 證券帳號打錯 = 送單到別人的帳號或被券商拒,而**我們手上明明有一份權威清單卻沒拿來交叉驗證**。
- `parts[0][:2].upper()` 取前 2 碼:`TF` 期貨 / `TO`(期權)若存在會被漏掉 —— 但 `[typelib]` 與
  `docs/research/2026-07-28-skcom-typelib.md` 都只記 `TS` / `TF`,且期權單本來就送期貨帳號,實務無影響。

### 1.6 `_drain_pending` 的收斂邏輯(Q7 的一半)

```python
# client.py:840-861
def _drain_pending(self) -> None:
    while True:
        try: cmd = self._cmd_q.get_nowait()
        except queue.Empty: return          # ← 唯一出口,必然收斂
        if cmd is None: continue
        _fn, fut = cmd
        loop = self._loop
        if loop is None: logger.error(...); continue
        try: loop.call_soon_threadsafe(_settle, fut, None, RuntimeError("COM 執行緒已終止,命令未執行"))
        except RuntimeError: logger.error("寫入命令丟棄(event loop 已關閉)")
```

**收斂性成立**:`get_nowait()` 在空佇列必拋 `Empty` → `return`。不會有生產者把它困住(不是 `get()`)。
**但它只跑一次,而且有競速窗**:`_execute_write` 的順序是
`status 檢查`(`client.py:881`)→ `await to_thread(審計前置)`(0.38 ms,池滿時無上界)→ `_cmd_q.put`。
執行緒在這中間死掉的話,`_set_status("error")` + `_drain_pending()` 已經跑完,
這筆命令**進了一個沒人消化的佇列**,10 秒後 `wait_for` 逾時,使用者拿到
`"結果未知,勿重送"`(`client.py:895`)—— 而真相是**這張單從來沒送出去**。詳見 F-04。

---

## 2. 端到端延遲預算(D2 段)

單位一律毫秒;`[實測-本機]` 的地板是 Windows 15.6 ms timer 精度(任務已給定,不重複扣)。

| # | 區段 | 位置 | 成本 | 依據 | 備註 |
|---|---|---|---|---|---|
| 1 | `_cmd_q.put` → COM 執行緒取走(**執行緒閒置在 `get()`**) | `client.py:887` → `811` | **0.0159 ms p50 / 0.0273 p95 / 0.697 max** | `[實測-本機]` 2,000 次跨執行緒 put→get 喚醒 | 這是**好路徑**,快得不需要動 |
| 2 | 同上(**執行緒正在 `_pump_once()` 空轉**) | `client.py:809` | **+0.0004 ms p50**(pump 本體) | `[實測-本機]` `import+PumpWaitingMessages` 空佇列 200k 次 | 幾乎零成本 |
| 3 | 同上(**pump 正在 dispatch 回報**) | `com.py:245-247` → `client.py:402` | **+~0.1 ms / 則** | `[推估]`(B10 實測 `apply_reply` 0.026–0.069 ms + `_emit`) | 開盤 `ConnectByID` backlog 重播 = **未量測黑盒** |
| 4 | 同上(**幫浦圈例外分支**) | `client.py:791-793` | **+1,000 ms** | `[實測-程式碼常數]` `time.sleep(1.0)` | 佔住唯一送單執行緒;`status` 仍是 `ok` |
| 5 | 同上(**執行緒卡在前一筆 `fn()`**) | `client.py:820` | **最壞 4,000 ms** | `[實測-prod]` 2026-09-07 11:54:52 審計 Δ=4 s | 見 #8 |
| 6 | `STOCKORDER()` + 10 次 `setattr` | `com.py:150-153` | **0.0020 ms p50 / 0.0026 p95** | `[實測-本機]` 50k 次,用真 typelib struct | 完全不是問題 |
| 7 | `SKCenterLib_GetReturnCodeMessage`(loop 執行緒) | `client.py:910`、`373` | **< 0.05 ms** | `[推估]` in-proc vtable 查表 | 成本不是問題,**正確性**是(F-05) |
| 8 | **`SendStockOrder(user, 0, order)` 同步 COM 呼叫** | `com.py:154` | **期望值 84 ms;P(≥1 s)=7.6%;max 4,000 ms** | `[實測-prod]` 499 筆審計 pre/post 秒級配對 | 見下方推導 |
| 9 | `_settle` via `call_soon_threadsafe` 往返 | `client.py:826` | **0.212 ms p50 / 0.822 p95** | `[實測-本機]`(B10 bench_capital.py) | 沿用上一輪 |
| 10 | 幫浦圈週期(閒置) | `client.py:811` | **62.3 ms p50 / 63.7 p95** | `[實測-本機]` `queue.get(timeout=0.05)` 200 次 | **不是 50 ms** → 16 圈/秒不是 20 |
| 11 | `import comtypes.gen.SKCOMLib`(早期繫結 wrapper) | `com.py:120` | **50.9 ms**,一次性 | `[實測-本機]` | 已是 cache;首次 `GetModule` 產生會更貴 |
| 12 | `_init_com` 全段(setup→status=ok) | `client.py:721-778` | **4,830 ms p50 / 4,410 min / 10,720 max** | `[實測-prod]` 65 次 session | 期間送單 503 |
| 13 | ↳ 其中 `get_user_accounts` 固定窗 | `com.py:225-228` | **3,000 ms**(寫死,無提早結束) | `[實測-程式碼常數]` | = #12 的 62% |
| 14 | ↳ 扣掉 #13 的真 SKCOM 登入鏈 | `com.py:133-147` | **~1,830 ms p50** | `[實測-prod]` #12 − #13 | SetAuthority+Login+Init+Cert+ConnectByID |
| 15 | 關機 COM join 上限 | `client.py:83, 719` | **5,000 ms** | `[實測-程式碼常數]` `COM_JOIN_TIMEOUT_SECS` | 進 `run_grace_secs()` 83 s 預算 |

### #8 的推導(本輪核心)

審計時戳是**秒解析度**(`client.py:336` `timespec="seconds"`),但前置行與後置行成對,
所以 `Δ = post_ts − pre_ts` 是一個**秒邊界跨越指示器**:若真實延遲 `L < 1 s`,則 `P(Δ=1) = L`(相位均勻)。
`[實測-prod]` 22 個審計檔、**499 對**成功配對(`action` 與 `req` 逐欄相同的相鄰兩行):

```
Δ=0s : 461 (92.4%)
Δ=1s :  36 ( 7.2%)
Δ=2s :   1
Δ=4s :   1
```
`E[Δ] = 42/499 = 0.0842 s` → **`SendStockOrder` 那一段的期望值 ≈ 84 ms**
(純 Python 段 B10 實測 p50 ≈ 1.0 ms,佔比 1.2% → **98.8% 在 COM + 券商往返**,與上一輪結論一致)。

分佈是**單峰貼近 84 ms**:若 L 恆為 84 ms,理論 `P(Δ=1) = 8.4%`,觀測 7.2% —— 吻合。
但**尾巴是真的**,而且尾巴挑人:

```
(code, Δ)  →  (0,0):414  (0,1):33   ← 成功單 P(Δ≥1) = 7.4%
              (999,0):35 (999,1):3 (999,2):1 (999,4):1  ← 拒單 P(Δ≥1) = 12.5%,唯二 ≥2 s 都在這
```
**券商 gateway 業務拒絕(code 999)比成功單慢**,因為它要跑完額度/簽署/庫存檢查才回。
兩筆尾巴的實錄:
```
2026-09-07T11:54:49  order 6488 buy 969.0 ×1  → 999 「網路單交易額度超過限定額度 249萬!」  Δ=2 s
2026-09-07T11:54:52  order 6488 buy 971.0 ×1  → 999 同上                                  Δ=4 s
```
→ **那 4 秒之內,`com.pump()` 一次都沒跑**。所有 `OnNewData` / `OnRealBalanceReport` /
`OnProfitLossGWReport` / `OnOpenInterest` 全部堆在 COM 訊息佇列裡,
`_maybe_query_balance` 的 60 s stale 計時照走、`_poll_pending` 的 8 s watchdog 照走。
這就是 `bAsyncOrder=0` 的真實代價,而且它是**在使用者最急的時候**(連點重送)發生的。

---

## 3. SKCOM 提供但我們沒用的東西(Q2)

`[typelib]` `ISKOrderLib._methods_` 有 **147** 個方法,我們用 **12** 個(8.2%)。
`_ISKOrderLibEvents` 29 個事件用 5 個,`_ISKReplyLibEvents` 12 個事件用 4 個。
以下只列**對「要下實單的量化系統」有實質價值**的,並給判決。

### 3.1 【最高價值】非同步下單 `bAsyncOrder=1` + `OnAsyncOrder`

`[typelib]`
```
COMMETHOD([dispid(6)], HRESULT, 'SendStockOrder',
    (['in'], BSTR, 'bstrLogInID'),
    (['in'], VARIANT_BOOL, 'bAsyncOrder'),          ← 我們硬寫 0
    (['in'], POINTER(STOCKORDER), 'pAsyncOrder'),
    (['out'], POINTER(BSTR), 'bstrMessage'),
    (['out','retval'], POINTER(c_int), 'retCode'))

DISPMETHOD(..., 'OnAsyncOrder',    (['in'], c_int, 'nThreaID'), (['in'], c_int, 'nCode'), (['in'], BSTR, 'bstrMessage'))
DISPMETHOD(..., 'OnAsyncOrderGW',  同上)
DISPMETHOD(..., 'OnAsyncOrderOLID',同上 + 第 4 參數)
```
現況 `com.py:150-191` **四處**硬寫 `0`(送單 / 期權送單 / 刪 / 改 / 減,共 6 個呼叫點)。

**價值**:`bAsyncOrder=1` 時 `SendStockOrder` 立即回,`bstrMessage` 帶 **`nThreaID`**(SKCOM 內部工作緒編號),
結果稍後由 `OnAsyncOrder(nThreaID, nCode, bstrMessage)` 推回 —— `nThreaID` 就是**券商端給的關聯 token**。
這一口氣解掉三件事:
1. **head-of-line blocking**(#8 的 4 秒)消失 —— COM 執行緒立刻回去 pump。
2. **B10 F-09「沒有冪等鍵 / timeout 後無法對帳」的最佳解**:
   `[typelib]` 已確認 `STOCKORDER` **14 欄**、`FUTUREORDER` **36 欄**裡
   **沒有任何 user-defined / 自訂單號欄位**(STOCKORDER:`bstrFullAccount / bstrStockNo / sPrime /
   sPeriod / sFlag / sBuySell / bstrPrice / bstrOrderType / bstrSeqNo / bstrBookNo / nQty /
   nTradeType / nSpecialTradeType / nUnitQty`;`bstrSeqNo` / `bstrBookNo` 是**刪改用的既有委託識別**,
   不是自訂欄)。→ B10 §9 open question 3 **答案是「沒有」**,而 `nThreaID` 是唯一的替代。
3. 送單的 HTTP 回應可以**立刻**回「已受理 + nThreaID」,把 `_WRITE_TIMEOUT_S = 10 s` 的轉圈變成毫秒級受理。

**代價 / 風險**(必須寫進 spec):
- **comtypes 對未實作的事件靜默忽略** —— 若翻 `bAsyncOrder=1` 卻沒在 `_OrderEvents` 掛 `OnAsyncOrder`,
  **每一筆單的結果都會靜默消失**,而同步回傳的 `bstrMessage` 只會是 thread id,
  `_execute_write` 的 `seq_no=(message.strip() or None) if ok else None` 會把 thread id 當委託序號存進 store。
  **這是必須綁在同一個 commit 的兩半。**
- `OnAsyncOrder` 三個變體(`OnAsyncOrder` / `GW` / `OLID`)哪一個會來,**未實證**,要 prod 首驗。
- 整個 `_execute_write` 的「審計後置 = 結果已知」語意要改寫。

**判決:建議導入,但要走 `/feat` + grilling,並以 shadow 模式先驗**(仍送同步單,只額外掛
`OnAsyncOrder` sink 看會不會有東西來)。這是本區塊 CP 值最高的一條。

### 3.2 【高價值】拉式對帳:`GetOrderReport` / `GetFulfillReport`

`[typelib]`
```
GetOrderReport(bstrLogInID, bstrAccount, nFormat) -> retCode
GetFulfillReport(bstrLogInID, bstrAccount, nFormat) -> retCode
```
**現況:`store._orders` 的唯一寫入來源是 `OnNewData` 推播**(`client.py:402-453`)。
這表示 B10 F-13 的「degraded 盲送」以及 §4 的 F-01(回報斷線零偵測)之後,
**系統沒有任何辦法知道市場上有什麼單** —— 而 SKCOM 一直提供著拉式查詢。

**價值**:
- 開機時把當日委託 / 成交拉一次 → 盤中重啟不再「委託面板空白」。
- `_WRITE_TIMEOUT_S` 逾時後自動拉一次 → 直接回答「那張單在不在市場上」。
- 回報通道死掉時的降級真相源。

**代價**:`nFormat` 的值域與回傳列格式**未實證**(和 `GetOpenInterestGW` 一樣是「prod 校正欄序」的坑);
`GetRealBalanceReport` 的 1019 `SK_ERROR_QUERY_IN_PROCESSING` 顯示 SKCOM 的查詢通道是**全域單工**,
多加一種查詢會加劇 §4 F-06 的 1019。

**判決:建議導入,但必須先解 1019 的查詢排程**(§5 step 6)。

### 3.3 【高價值】券商端風控與緊急撤單

| `[typelib]` 簽名 | 用途 | 為什麼值得 |
|---|---|---|
| `SetMaxQty(nMarketType, nMaxQty)` | DLL 端單筆最大量 | B10 F-12 說風控只有我方純函式閘;這是**第二道、在 DLL 裡的**閘,程式跑飛也擋得住 |
| `SetMaxCount(nMarketType, nMaxCount)` | DLL 端委託筆數上限 | 直接就是「速率 / 筆數限制」,B10 F-12 列為缺口 |
| `CancelOrderByStockNo(loginID, async, account, stockNo)` | 依股號整批刪單 | **緊急撤單**;現況只有逐筆 `CancelOrderBySeqNo`,而 store 在回報斷線時是空的 |
| `CancelOrderByStockNoAdvance(..., nBuySell, bstrPrice)` | 加方向 / 價格條件的整批刪 | 同上,更細 |
| `CoverAllProduct(loginID, async, pAsyncOrder)` | 全平倉 | B10 F-11 的 kill switch 只到「停止新單」;這是「把倉清掉」 |
| `SendTFOffset` / `SendTXOffset(..., account, ym, buySell, qty)` | 期貨 / 選擇權當沖沖銷 | 現況平倉是「反向限價貼漲跌停 + IOC」的自組單 |

**判決**:`SetMaxQty` / `SetMaxCount` **建議導入**(啟動時各設一次,零熱路徑成本,純加一道閘)。
`CancelOrderByStockNo` **建議導入**(搭配 B10 F-11 的 halt,做成「halt + 全撤」)。
`CoverAllProduct` / `SendTFOffset` **不建議現在做** —— 「自動全平倉」的 blast radius 遠大於收益,
且欄位語意未實證。

### 3.4 【中價值】連線健康探針與診斷

| `[typelib]` 簽名 | 價值 |
|---|---|
| `SKReplyLib_IsConnectedByID(bstrUserID)` | **主動**探測回報連線;直接解 §4 F-01(現況只有被動、且從未觸發的 `OnDisconnect`) |
| `SKReplyLib_CloseByID` / `SKReplyLib_SolaceCloseByID` | 重連的前半(先關再 `ConnectByID`) |
| `OnSolaceReplyConnection` / `OnSolaceReplyDisconnect`(dispid 9/10) | **很可能是這版 SKCOM 真正在用的**回報連線事件(見 F-01) |
| `SKCenterLib_GetLastLogInfo()` | SKCOM 內部最後一筆 log —— rc 之外唯一的細節來源 |
| `SKCenterLib_SetLogPath(bstrPath)` / `SKCenterLib_Debug` | 把 SKCOM 自己的 log 導到我們看得到的地方 |
| `SKOrderLib_TelnetTest` / `SKOrderLib_PingandTracertTest` + `OnTelnetTest` | 連線診斷(1097 那類問題的第一手證據) |
| `SKOrderLib_GetLoginType` / `SKOrderLib_GetSpeedyType` | session 型態(Solace / Telnet / Speedy),決定重連策略 |

**判決**:`SKReplyLib_IsConnectedByID` + `OnSolaceReplyConnection/Disconnect` **建議導入(最優先)**。
`SetLogPath` **建議導入**(零風險,一行)。其餘備查。

### 3.5 【中價值】資料品質與部位

| `[typelib]` 簽名 | 價值 |
|---|---|
| `GetOpenInterestWithFormat(loginID, account, nFormat)` + `OnOpenInterestJson(bstrData)` | **JSON 版期貨部位** —— 現況 `parse_open_interest_line` 的逗號欄序是「prod 校正」出來的,JSON 有欄名 |
| `GetFutureRights(loginID, account, sCoinType)` + `OnFutureRights` / `OnFutureRightsStatus` | 期貨權益數 / 保證金 → 保證金風控(B10 F-12 缺口) |
| `GetBalanceQuery(loginID, account, stockNo)` + `OnBalanceQuery` | 證券可用餘額 → 資金風控 |
| `GetMarginPurchaseAmountLimit` + `OnMarginPurchaseAmountLimit` | 融資額度 —— `[實測-prod]` 已經因此被拒過:`999 [999] 此人融資已滿!欲借 57萬;額度 90萬` |
| `GetAvgCost(loginID, SKAVGCOST)` | 庫存均價(現況靠 `GetProfitLossGWReport` 回填 `avg_source="broker"`) |
| `SendStockOddLotOrder` | 零股專用委託 —— 現況零股完全不在樂觀套用涵蓋內(`client.py:438-444`) |

**判決**:`OnOpenInterestJson` **有條件導入**(欄序坑值得換掉,但要 prod 對照);
`GetMarginPurchaseAmountLimit` / `GetBalanceQuery` **建議導入**(把 30 筆 999 額度拒單變成送出前就擋);
`GetAvgCost` **不建議**(現況 `avg_source` 契約已釘死在 CLAUDE.md §4,換來源 = 動契約,收益只是少一段串行)。

### 3.6 明確不需要的

`SKQuoteLib` / `SKOSQuoteLib` / `SKOOQuoteLib`(行情,我們用 TC4)、
`SendOversea*`(海外期權)、`SendForeignStock*`(複委託)、
`SendStockStrategy*` / `SendFutureMIT/OCO/StopLoss/MovingStopLoss`(券商端條件單 —— **有價值但屬新功能**,
且和本專案「訊號 → 人決策」的定位衝突,現階段不碰)、
`ProxyReconnectByID` / `SendStockProxyOrder`(預約單 proxy)、
`CapitalPayWithDraw` / `WithDraw` / `GetNTDBlock`(出入金 —— **絕對不要碰**)。

---

## 4. 失效模式(特別標零錯誤訊號)

### F-01 【critical / 零錯誤訊號】回報連線的斷線偵測是死碼 —— 65 次 session 從未觸發

**位置** `com.py:264-279` `_ReplyEvents.OnConnect` / `OnDisconnect` → `client.py:455-462` `_handle_reply_disconnect`

`[實測-prod]` 全部 15 個 `logs/server-*.log`:

| log 字串 | 出現次數 |
|---|---:|
| `Capital reply:`(= `OnNewData` 到達) | **3,531** |
| `Capital reply connected`(= `OnConnect(0)`) | **0** |
| `Capital reply connect error`(= `OnConnect(≠0)`) | **0** |
| `Capital reply disconnected`(= `OnDisconnect`) | **0** |
| `Capital reply connect failed`(= `ConnectByID` rc≠0) | **0** |
| `回報連線中斷`(= `_handle_reply_disconnect` 產生的 `degraded`) | **0** |

65 次成功登入、3,531 則主動回報,`OnConnect` **一次都沒響**。`ConnectByID` 的 rc 每次都是 0
(否則會印 `connect failed`),所以連線確實建立了 —— **但成功事件沒有來**。

**根因假說(高信心,未在 prod 驗證)**:`[typelib]` `_ISKReplyLibEvents` 有 12 個事件,
dispid 1/2 是 `OnConnect` / `OnDisconnect`(Telnet 世代),dispid **9/10 是 `OnSolaceReplyConnection` /
`OnSolaceReplyDisconnect`**。SKCOM 2.13.58 的回報通道走 Solace(旁證:`SKReplyLib_SolaceCloseByID`
方法存在;登入失敗碼叫 `SK_ERROR_**TELNET**_LOGINSERVER_FAIL` 顯示 Telnet 是舊路)。
→ 我們掛的是**舊路的事件**,新路的事件因為 sink 沒實作被 comtypes **靜默忽略**(`com.py:272` 自承)。

**後果(這才是重點)**:
- 盤中回報通道掉線 → `status` 永遠是 `ok`,`/api/capital/status` 說一切正常;
- `store._orders` 靜默凍結 → 委託面板停在掉線那一刻;
- `_close_dup_reason`(`client.py:1139-1141`)掃不到同向活躍委託 → **平倉防重送整層失效**;
- `_routing` 的 `market_of` 回 None → 市場別交叉驗證寬鬆放行;
- `remaining_shares` 回 None → **改價的金額閘直接跳過**(`client.py:1082-1090`);
- 使用者看到「我剛送的單不見了」→ 重送。

**這一條同時讓 B10 的 F-13 失效**:F-13 假設 `degraded` 會亮,實際上它從來不會亮。

**偵測**:現在完全沒有。要加的是 `SKReplyLib_IsConnectedByID(user)` 每 N 秒輪詢一次(在 `_pump_once` 裡),
外加把 `OnSolaceReplyConnection` / `OnSolaceReplyDisconnect` 掛上去。

---

### F-02 【critical / 零錯誤訊號】COM 執行緒卡死沒有任何 watchdog

**位置** `client.py:795-838`(`_run`)、`client.py:253-273`(`status` / `status_view`)

grep 全 `copycat/capital/` + `capital_api.py`:**零處 `is_alive()`**、零處「上次 pump 的時刻」、
`/api/health` 刻意不含引擎健康度(`app.py:1290-1296` docstring)。

三種卡法,後果不同但**都零訊號**:

| 卡在哪 | `_status` | `_cmd_q` | 使用者看到 |
|---|---|---|---|
| `fn()`(`SendStockOrder`)內 | **`ok`** | 無上界累積 | 按鈕轉 10 s → 「結果未知,勿重送」 |
| `_pump_once()` 的例外分支 `time.sleep(1.0)` 緊迴圈 | **`ok`**(例外被吞,狀態沒降) | 每圈只取 1 筆 | 每筆送單多等 ≤ 1 s |
| `com.pump()` 在 dispatch backlog | **`ok`** | 累積 | 同上 |

`_cmd_q = queue.Queue()`(`client.py:212`)**沒有 maxsize**。搭配 B10 已記的「逾時的寫入命令沒有 TTL」
(`wait_for(shield(fut))` 逾時後 future 不取消、命令仍留在佇列)→
**COM 恢復的那一刻,10 秒前放棄的單會一次全部送進市場**。

**偵測要加什麼**:`_pump_once()` 結尾記 `self._last_pump = time.monotonic()`,
`status_view()` 多回 `pump_age_ms` 與 `queue_depth`;`pump_age_ms > 3000` → `status = "stalled"`。
十幾行,零契約風險。

---

### F-03 【high / 訊號被污染】正常關機也記 ERROR「capital-com 執行緒結束(status→error)」

**位置** `client.py:832-838`

```python
finally:
    if not self._last_error:
        self._last_error = "COM 執行緒已終止"
    self._set_status("error")
    self._drain_pending()
    logger.error("capital-com 執行緒結束(status→error)")
```

`close()` 投 `None` 哨兵 → `_run` 的 `while` `break` → 直接進 `finally`。
也就是**每一次乾淨的 Ctrl+C 關機都會印一行 ERROR 並把 status 降成 error**。

`[實測-prod]` 全 log:`capital-com 執行緒結束(status→error)` **44 次**,
而 `群益正式環境` banner(= 成功建構 client)**65 次**。
→ 這一行**沒有鑑別力**:真正的執行緒亡故(COM 例外、loop 關閉)和正常收攤長得一模一樣。
盤後要查「今天 COM 執行緒有沒有異常死過」,現在答不出來。

**修法**:`close()` 設 `self._closing = True`;`finally` 依旗標分流
(正常 → `logger.info("capital-com 正常收攤")` 且不改 status;異常 → 維持現狀)。

---

### F-04 【high / 零錯誤訊號】`_drain_pending` 之後入列的命令被謊報成「結果未知」

**位置** `client.py:881`(status 檢查)→ `885`(審計前置 `await`)→ `887`(`put`)vs `836-837`(`finally`)

```
loop 執行緒                                   COM 執行緒
t0  status in ("ok","degraded")  ✔
t1  await to_thread(_audit 前置)  ← 0.38 ms,池滿時無上界
                                              t1.5  finally: _set_status("error"); _drain_pending() 跑完
t2  _cmd_q.put((com_call, fut))   ← 沒人會再取
t3  +10 s → TimeoutError
t4  OrderResult(ok=False, code=-1, message="結果未知,勿重送")
```

**「結果未知,勿重送」的語意是「單可能已在市場上」** —— 這條路徑上它**確定不在**。
使用者因此不敢重送一張根本沒送出去的單;而本文的 F-01 又讓委託面板無法證偽。
兩條合起來 = **該送的單沒送、系統說不確定、面板查不到**。

**修法**:`_execute_write` 在 `put` **之後**再檢查一次 `self._status`(或用一個 `_accepting` 旗標 +
`threading.Lock` 把 `put` 與 `finally` 的 drain 序列化),status 已降則立刻
`fut` 設 `CapitalDownError("COM 執行緒已終止,命令未執行")` —— 語意從「未知」變成「確定沒送」。

---

### F-05 【high / 未定義行為】`return_code_message()` 跨 apartment 直呼(修正 B10 F-02 的機制)

**位置** `client.py:910`(成功路徑,每筆寫入必過)、`client.py:373`(late 路徑)→ `com.py:242-243`

B10 F-02 說「若 comtypes 建了 proxy,跨執行緒呼叫會走 COM marshaling → 死鎖或長阻塞」。
**這個機制我認為是錯的,要修正**:

`[typelib]` `ISKCenterLib._methods_` 是 `COMMETHOD` 的 **vtable 介面**(早期繫結),
而 `comtypes.client.CreateObject(sk.SKCenterLib, interface=sk.ISKCenterLib)`(`com.py:122`)
拿到的是 **in-proc 物件的直接介面指標**,comtypes **不會**自動做跨 apartment marshaling
(那要 `CoMarshalInterThreadInterfaceInStream` / GIT,程式裡沒有)。
→ loop 執行緒上的 `self._center.SKCenterLib_GetReturnCodeMessage(code)` 是一次
**直接 vtable 呼叫,沒有 proxy、沒有 marshaling、不需要目標 STA 幫浦** → **不會死鎖**。

**真正的風險是另一個**:這是在**繞過 apartment 同步**,直接與 COM 執行緒**並行**進入同一個
in-proc COM 物件。若 `SKCenterLib` 內部有共享狀態(回傳碼表的 BSTR buffer、last-error 欄位),
這就是一個 data race,失效樣態是**拿到別人那次呼叫的訊息字串**或記憶體毀損 —— 兩者都零錯誤訊號。
另外 `_on_late_result` 走這條時,COM 執行緒**正卡在 `SendStockOrder` 裡**的機率最高。

**修法(不變)**:把 `return_code_message` 搬進 `com_call` 閉包,`_ComCall` 回傳型別
`tuple[str, int]` → `tuple[str, int, str]`。最小改動、語意不變、一併消掉 `_on_late_result` 那條。

---

### F-06 【high / 有訊號但沒人處理】`GetRealBalanceReport rc=1019` —— 310 次,盤中最密

**位置** `client.py:514-521`

`[實測-prod]` 全 log 共 **310** 次 `GetRealBalanceReport rc=1019: SK_ERROR_QUERY_IN_PROCESSING`,
分佈在 **22 個交易日**(平均 14 次/日),時段集中在盤中:

```
09 時 69 次 · 10 時 46 · 12 時 22 · 15 時 30 · 17 時 23 · 19 時 21 · ...
```
典型形狀是**連發 4–5 次、每次間隔 1 秒**(`_mark_balance_dirty(1.0)` 退避):
```
2026-09-11 09:07:29.096 / 30.112 / 31.169 / 32.179   ← 4 連
2026-09-11 10:33:44.060 / 45.121 / 46.125 / 47.127 / 48.145  ← 5 連
2026-09-11 12:35:45.535 / 46.540 / 47.934 / 48.934   ← 4 連
```
→ **每次事件 = 4–5 秒部位完全停更**,而且發生在「剛成交完、最想看倉位」的時刻。

**根因(高信心推論)**:SKCOM 的查詢通道是**全域單工**(不分查詢種類)。
`client.py` 的守門(`_balance_inflight_until` / `_pending_sec`)只管**我們自己發的 balance 段**,
管不到:(a) `GetProfitLossGWReport` / `GetOpenInterestGW` 還在 DLL 裡跑;
(b) `[實測-prod]` `Capital open-interest 查詢狀態 1: ... HttpSendRequest ... error code is 12007`
顯示 **GW 家族是走 HTTPS 的**(`HttpReuqstJson SSLPost`),DLL 端的 in-flight 比我們以為的久。

**修法**:把三段查詢納入**同一把** in-flight 鎖(現在是三個各自的旗標),
並在 `_maybe_query_balance` 進門先 `if not self._cmd_q.empty(): return`(B10 F-04 已提,順帶解這條)。
1019 本身應該進「可重試」分類表(§4 F-08),退避改指數(1 → 2 → 4 s)。

---

### F-07 【medium / 每日必中】券商 GW 通道每天 05:51–05:52 失敗

`[實測-prod]` `Capital open-interest 查詢狀態 1: Request error Code: HttpReuqstJson SSLPost
HttpSendRequest (else)error and error code is 12007`(12007 = `ERROR_INTERNET_NAME_NOT_RESOLVED`)
**20 次**,時刻高度規律:

```
08-18 05:51/05:52 · 08-21 05:51/05:52 · 08-25 05:51/05:52 · 08-26 · 08-27 · 08-28 · 08-29
09-01 · 09-02 · 09-03 · 09-04 · 09-08 · 09-09 · 09-10 · (09-12 同段)
```
**每一個跨夜的 session 都中,一次不漏**,另外 09-13 05:51/05:52 出現
`balance collector 忽略放棄輪遲到的終止符`(同一件事的下游)。

判定:這是**群益 GW 主機的每日維護窗**(或本機夜間 DNS/網路重置),不是我們的 bug。
夜盤 05:00 已收盤,所以目前**影響是零**(期貨部位沿用上一輪,`_stale_fut_positions`)。

**為什麼還要列**:它證明了兩件對量化系統重要的事 ——
(a) GW 家族(`GetOpenInterestGW` / `GetProfitLossGWReport` / `SKCenterLib_LoginGW`)
**是 HTTP 通道**,受 DNS / TLS / proxy 影響,不在我們任何 timeout 的保護內
(只有 `_PENDING_TIMEOUT_S = 8 s` 這個粗保底);
(b) **送單通道是否也在同一個維護窗**未知 —— 如果是,05:50–05:55 送單會失敗,而我們不知道。
這是要問 user / 群益的 open question。

---

### F-08 【high / 結構缺口】錯誤碼完全沒有「可重試 vs 終局」分類

**位置** `client.py:909-921`(唯一的分類就是 `code == 0`)

```python
ok = code == 0
text = f"{self._com.return_code_message(code)} {message}".strip()
...
if not ok:
    raise BrokerRejectedError(err_code=str(code), err_msg=text)   # → HTTP 400,一視同仁
```

`[實測-prod]` 1,075 筆審計的**真實碼表**(這是本輪從零建出來的):

| code | 出現 | 類別 | 真實訊息樣本 | 該怎麼分 |
|---:|---:|---|---|---|
| `0` | 484 | SK_SUCCESS | `SK_SUCCESS 2313190806783` / `SK_SUCCESS 委託資料傳送成功!` | — |
| `999` | 40 | **券商 gateway 業務拒絕**(HTTP 風格碼) | `網路單交易額度超過限定額度 249萬!`(30)<br>`此投資人尚未簽署創新版風險預告書,不可委託!`(4)<br>`集保庫存剩 0 股,不得賣出或匯撥交割`(4)<br>`此人融資已滿!欲借 57萬;額度 90萬`(1)<br>`目前此投資人可沖銷股數,資買 0 股`(1) | **終局**,且**大半應該在送出前就擋掉**(額度/庫存/融資都可用 §3.5 的查詢先問) |
| `1068` | 7 | **SKCOM 本地參數驗證** | `SK_ERROR_SPECIAL_TRADE_TYPE_IS_MARKETPRICE_AND_ORDERPRICE_SHOULD_BE_ZERO` | 終局(我方 bug);**單沒離開本機** |
| `400` | 3 | 券商 DB 查詢失敗 | `DB查詢失敗: [INFO].[dbo].[tblPriceFuturePM] : TMFI6無法轉換商品ID` | **看起來可重試(DB 失敗),實際是資料面終局** —— 這正是不分類的危險 |
| `960` | 2 | 委託狀態拒絕 | `此委託不可做刪改!` / `查無委託資料` | 終局 |
| `1019` | (查詢路徑 310 次) | 查詢處理中 | `SK_ERROR_QUERY_IN_PROCESSING` | **可重試**(現況已有 1 s 固定退避,但不是分類出來的) |
| `1097` | (登入 11 次) | 登入主機失敗 | `SK_ERROR_TELNET_LOGINSERVER_FAIL` | 環境終局(沙盒未開通) |

**現在怎麼分?答案是:完全不分。** 寫入路徑只有 `code==0` 一個分叉;查詢路徑的
`rc != 0` 一律固定 1 s 退避,不看碼。`SKCenterLib_GetReturnCodeMessage` 只被拿來組**給人看的字串**。

**兩個實務後果**:
1. `999` 額度類拒單佔了全部失敗的 74%(30/40),而它們**每一筆都是本來就可以在送出前知道的**
   (`GetMarginPurchaseAmountLimit` / `GetBalanceQuery`)。使用者現在的體驗是「按了才知道不行」,
   而那一按吃掉 §2 #8 的 84 ms–4 s + 佔住 COM 執行緒。
2. `400` 的「DB查詢失敗」字面是暫時性錯誤,但實際是**微台契約碼 `TMFI6` 群益端不認得**
   —— 若哪天加了「自動重試可重試碼」而把 400 歸進去,會變成對同一張單連打三次。

**修法**:`capital/retcodes.py`(純資料 + 純函式,stdlib):
`TERMINAL = {999, 960, 1068, 400}` / `RETRYABLE = {1019}` / `UNKNOWN → 終局`(fail-safe 方向)。
`_execute_write` 用它決定要不要在 `OrderResult` 帶 `retryable: bool`,route 據此給前端不同文案。
**預設方向必須是終局** —— 真錢路徑上「不確定 → 不重試」。

---

### F-09 【medium / 零錯誤訊號】刪單成功的 `seq_no` 是一句中文,不是委託序號

**位置** `client.py:915`

```python
seq_no=(message.strip() or None) if ok else None
```
這假設 `bstrMessage` 在成功時是委託序號。`[實測-prod]`:

```
(action, code, message 形狀)            筆數
('order' , 0, 'SK_SUCCESS <13 位數字>')   369   ← 假設成立
('close' , 0, 'SK_SUCCESS <13 位數字>')     1   ← 成立
('cancel', 0, 'SK_SUCCESS 委託資料傳送成功!')  114   ← **假設不成立**
```
→ **114 筆刪單的 `OrderResult.seq_no` 字面值是 `"委託資料傳送成功!"`**,而且原樣回給前端。

目前沒有造成災害是因為刪單請求沒有 `price_type`,`_note_price_type`(`client.py:955`)
`if not (price_type and ...)` 早退,所以沒污染 `store` 的價格別記憶。
但這是**靠巧合成立**的:任何未來「用回應的 `seq_no` 做點什麼」的改動(對帳、去重、追單)都會踩到。

**修法**:`_execute_write` 多一個 `expects_seq: bool` 參數(送單 True / 刪改減 False),
False 時 `seq_no=None`。或更嚴:`seq_no = message.strip() if message.strip().isdigit() else None`。

---

### F-10 【medium / 零錯誤訊號】`get_user_accounts` 的 `TS` 列拿到了卻不用

**位置** `com.py:229-236` → `client.py:760-765`

`_parse_account_row` 已經把 `(market_prefix, full_account)` 全部解出來,
但 `client` 只 `next((acct for mkt, acct in accounts if mkt.startswith("TF")), None)`。
**證券帳號 `CAPITAL_FULL_ACCOUNT` 是手設的 env,從來沒跟券商回來的 `TS` 列比對過。**

失效樣態:`.env` 的證券帳號打錯一碼 → SKCOM 送出 → 券商回一個業務拒絕碼(很可能就是 `999` 那一類),
而**錯誤訊息不會說「帳號不對」**。一次啟動時的等值比對就能把它變成啟動即拒。

**修法(三行)**:`_init_com` 裡
```python
sec_accounts = [a for m, a in accounts if m.startswith("TS")]
if sec_accounts and self._full_account not in sec_accounts:
    raise RuntimeError(f"CAPITAL_FULL_ACCOUNT 不在券商帳號清單(****{self._full_account[-4:]})")
```
⚠ 這會讓「帳號設錯」從**靜默送單失敗**變成**啟動即拒**,是安全方向,但要 user 拍板
(萬一 `TS` 欄序在某些帳號型態下不同,會誤擋)。

---

### F-11 【medium】`_init_com` 失敗 = 這個 process 永久沒有下單能力

**位置** `client.py:806-807`

```python
if not self._init_com():
    return          # ← 執行緒結束;沒有任何重試 / 重登路徑
```

`[實測-prod]` 11 次 `Capital init failed`(都是 test 沙盒 1097)。
在 prod,這條會被觸發的情境是:server 在網路就緒前啟動、憑證檔暫時鎖住、群益登入主機維護(參考 F-07 的 05:51 窗)。
後果:**整天不能下單**,而唯一的訊號是啟動時的一行 `logger.error`(已經被 `run.ps1` 的 console 洗掉)
加上 route 回 503。

**修法**:`_run` 外包一層有上界的重試(例如 3 次、指數退避 5/15/45 s),
`_set_status("error", error=...)` 帶上「第 n 次重試中」。⚠ 重試必須有上界(鐵則 F),
且 1097 這類環境終局碼不該重試(和 F-08 的分類表同一份)。

---

### F-12 【medium / 關機】`capital.close()` 走共享預設 executor

**位置** `app.py:1254` `await _close_segment("capital", lambda: asyncio.to_thread(capital.close))`

`shutdown_budget.run_grace_secs()` 把 `COM_JOIN_TIMEOUT_SECS = 5.0` 算進 83 s 預算,
前提是「輪到 capital 段時它立刻開始」。但 `to_thread` 用的是**共享預設 executor(20 workers)**,
而 capital 是**最後一段**(N049)—— 前面五條 TC4 session 若留下卡住的殭屍執行緒佔滿池,
`capital.close()` **連開始都不會開始**,5 s join 形同虛設,`run.ps1` 直接 `taskkill /T /F`。

後果:COM apartment 沒收攤、SKCOM 的登入 session 沒正常登出 → 下一台 server 的
`SKCenterLib_Login` 可能吃到「重複登入」類的碼(**未實證**)。

**修法**:capital 段用專屬執行緒 close(`threading.Thread(target=capital.close).join(timeout)`),
或和 B10 F-01 的專用 audit pool 一起做成 `capital` 自己的小 executor。
⚠ 動到 `shutdown_budget` 的 lane 形狀就是**動 CLAUDE.md §4 契約**,要同步改 `TC4_LANE_DEPTH`
並過 `tests/server/test_shutdown_budget.py`(含 `run.ps1` 字面 parity)。

---

### F-13 【low-medium】`_init_com` 的 3 秒固定窗

**位置** `com.py:225-228`。`[實測-prod]` 佔整段登入 4.83 s 的 **62%**。
`OnAccount` 沒有「收完」訊號是 SKCOM 的固有缺口,所以 timeout 收束是對的;
但可以加一個「距離最後一列到達已超過 400 ms 且已有 ≥1 列」的提早結束,把 3.0 s 降到 ~1.5 s。
**判定:優先序低**(每次啟動一次),列出來是因為它是啟動窗裡唯一可壓縮的整秒。

---

### F-14 【low / 但會變成災難】comtypes 對未實作事件靜默忽略 —— 41 個事件只掛 9 個

**位置** `com.py:250-337`(兩個 sink)、`com.py:272` 的註解自承。

現在無害(沒掛的 32 個事件本來就不期待)。**但它是 §3.1 非同步下單的地雷**:
翻 `bAsyncOrder=1` 而沒掛 `OnAsyncOrder` = **每一筆單的結果靜默消失**,
同步回傳的 `bstrMessage` 變成 thread id 被當成委託序號存進 store。

**要在 spec 裡寫死的不變量**:`bAsyncOrder` 的值與 `OnAsyncOrder` sink 的存在**必須同一個 commit**,
並以測試釘住(FakeCom 送 async 時 sink 沒掛 → 測試紅)。

---

### F-15 【已修正 / 反向證據】市價單 `bstrPrice="0"` 的「未實測」註解已被 prod 推翻

**位置** `mapping.py:248-256` 的註解:
> `**字面 "0"(非 "0.00")是推定未實測**` … `安全首單若仍 1068 → 改試 "0.00"`

`[實測-prod]` 市價單(`price_type == "market"`)的結果分佈:

```
2026-08-24  code 1068 × 7    ← 修正前(帶估價)
2026-08-25  code 0    × 2
2026-08-27  code 0    × 1
2026-09-04  code 0    × 1
2026-09-08  code 0    × 1
2026-09-09  code 0    × 8
```
**修正後 13 筆市價單全數 `code 0`,零筆 1068。** 字面 `"0"` 已實證可用。
→ `mapping.py` 那段註解與 CLAUDE.md 相關描述應更新成「已實證」,
否則下一個人會照註解的指引去改成 `"0.00"`,把一個已驗證的路徑改壞。
**這是 D2 唯一一條「不用改 code、只要改文件」的發現。**

---

## 5. 改造順序 + 量測判準

> 順序原則:**先讓看不見的變看得見**(F-01 / F-02)→ **再修謊報**(F-03 / F-04 / F-09)→
> **再動熱路徑**(F-05 / F-06)→ **最後才是 API 表面的新能力**(非同步 / 拉式對帳)。
> 每一步都要有「怎麼量才算改對了」。

| # | 做什麼 | 為什麼排這裡 | 量測判準 | 回退 |
|---|---|---|---|---|
| 1 | **回報連線健康探針**:`_pump_once` 每 10 s 呼一次 `SKReplyLib_IsConnectedByID(user)`,結果進 `status_view()`;同時把 `OnSolaceReplyConnection` / `OnSolaceReplyDisconnect` 掛上 sink(F-01) | 這是唯一一條「錢在動而系統瞎掉」的路徑,而且現在**從未被驗證過能響** | 盤中 `curl :8721/api/capital/status` 有 `reply_connected: true`;盤後 `grep "回報連線" logs/server-*.log` 每 10 s 一行(或節流後每次變化一行)。**反向驗證**:拔網路線 30 s → `status` 在 ≤ 15 s 內轉 `degraded`,恢復後轉回 `ok`。若掛上 Solace 事件後盤中出現 `OnSolaceReplyConnection`,F-01 的假說即證實 | 純新增讀取 + log,移除該段即回退;不碰任何契約 |
| 2 | **COM 執行緒活性**:`_pump_once` 結尾記 `_last_pump`;`status_view()` 加 `pump_age_ms` / `queue_depth`;`pump_age_ms > 3000` → `status="stalled"`(F-02) | 有了 #1 還是看不出「執行緒本身卡住」;這兩個欄位是後面每一步的驗收儀表 | `curl /api/capital/status` 閒置時 `pump_age_ms < 200`、`queue_depth == 0`。**反向驗證**(測試注入):FakeCom 的 `pump()` 睡 5 s → 3 s 後 status 變 `stalled`,不睡後恢復 | 新欄位,前端不讀就沒影響(wire 只加不減) |
| 3 | **正常關機不記 ERROR**(F-03) | 沒有這一步,#1/#2 加出來的訊號會被同一份 log 裡 44 次假 ERROR 稀釋 | Ctrl+C 一次 → `grep "capital-com 執行緒結束" logs/<新檔>` 為 **0**,改印 `INFO capital-com 正常收攤`;`grep "status→error"` 為 0 | 一個旗標 + 一個 if,直接還原 |
| 4 | **分段時戳 + 毫秒審計 ts**(B10 F-10;`com` 那一段在 COM 執行緒 `fn()` 前後量,隨結果回傳) | 這是後面每一條的驗收基準。#5 之後 `_ComCall` 本來就要改簽名,兩件事一起做只動一次 | 盤後 `python -c` 讀當日 `capital-*.jsonl`,`lat_us.total` 出得了 p50/p95/p99,且 `lat_us.com` 的 p50 落在 **60–110 ms**(對得上本報告 §2 #8 的 84 ms 期望值 —— **這是驗收這一步本身正確性的錨**) | 審計多一個 key,離線讀者(`jq` / 對帳腳本)逐列讀既有 key 不受影響 |
| 5 | **`return_code_message` 搬進 COM 執行緒**:`_ComCall` 回 `tuple[str, int, str]`(F-05) | 修掉跨 apartment 並行呼叫;與 #4 同時改簽名 | `grep -n "_com\." copycat/capital/client.py` 之後,**除了 `_cmd_q` 閉包內**沒有任何 `self._com.*` 出現在 `async def` 裡;`pytest -q` + `pyright` 全綠;prod 送一筆遠價安全單 → 審計 `result.message` 內容與改前逐字相同 | 簽名改動範圍在 `client.py` + `com.py` 內部,不碰 wire |
| 6 | **查詢單工化 + 寫入優先權**:三段查詢共用一把 in-flight 鎖;`_maybe_query_balance` 進門 `if not self._cmd_q.empty(): return`;例外退避改旗標不 `sleep`(F-06 + B10 F-03/F-04) | 前面的儀表到位後才動熱路徑,才量得出有沒有變好 | 盤後 `grep -c "rc=1019" logs/server-*.log` 與改前同期比,從 **~14 次/日降到 ≤ 3 次/日**;#4 的 `lat_us.enqueue_to_com` p95 **< 1 ms** | 三處小改動,各自可獨立還原 |
| 7 | **錯誤碼分類表 `capital/retcodes.py`**(F-08):`RETRYABLE={1019}` / `TERMINAL={999,960,1068,400,1097}` / 未知 → 終局 | 有了 #4 的數字才知道哪些碼真的值得重試;分類表也是 #8 的前置 | 純函式,`pytest` 用本報告 §4 F-08 的真實碼表當 golden fixture(直接抓 `data/audit/` 的實錄碼);prod 一週後 `grep` 不應出現任何「未知碼被當可重試」的 log | 新檔 + 一個 `OrderResult` 欄位,前端不讀即無影響 |
| 8 | **`SetMaxQty` / `SetMaxCount` 在 `_init_com` 顯式設值**(§3.3) | DLL 端第二道閘;十行,零熱路徑成本。排在分類表之後是因為被 DLL 擋下的碼要進得了分類表 | 啟動 log 印 `SetMaxQty(rc=0, market=?, max=N)`;**反向驗證**:把 `CAPITAL_MAX_QTY` 設 1、手動送 2 張的遠價安全單 → 我方閘先擋(審計 `blocked`);再暫時拿掉我方閘重送 → DLL 回非 0 碼,審計有記 | 不設值 = 現況;移除該兩行即回退 |
| 9 | **`GetOrderReport` / `GetFulfillReport` 拉式對帳**(§3.2):開機拉一次 + `_WRITE_TIMEOUT_S` 逾時後拉一次 | 這是 F-01 / F-04 的真正解藥,但必須先有 #6 的查詢單工化,否則加劇 1019 | 盤中重啟 server → 委託面板**不再空白**(改前空白);注入一次 timeout(FakeCom 慢送)→ 10 s 後 log 印「timeout 對帳:市場上有/沒有這張單 seq=…」。`nFormat` 的欄序要先以一天的 prod 資料對照 `OnNewData` 建 golden | 新查詢,失敗只降級成現況;不碰 `store._orders` 的既有寫入路徑 |
| 10 | **非同步下單 shadow → 切換**(§3.1):先只掛 `OnAsyncOrder` sink(仍送同步單)驗證有無事件;確認後才翻 `bAsyncOrder=1` | blast radius 最大的一條,放最後。#4 的 `lat_us.com` 是它唯一的成敗判準 | **shadow 階段**:prod 送一筆遠價安全單 → log 有無 `OnAsyncOrder(nThreaID=…, nCode=…)`。**切換後**:`lat_us.com` 的 p50 從 ~84 ms 降到 **< 5 ms**,p99 從秒級降到 ms 級;`pump_age_ms`(#2)在連續送 3 筆時**不再出現 > 1000 的值**(改前 §2 #5 實測 4 s);審計每筆帶 `async_thread_id` | `bAsyncOrder` 做成一個 env 旗標(預設 0),翻回去即回退 —— **但 sink 必須永遠掛著**(F-14) |

---

## 6. 工具選型:`comtypes` vs `pywin32`,early binding(Q6)

### 現況是對的:已經是 early binding,不要改

`[typelib]` 直讀 `.venv/Lib/site-packages/comtypes/gen/`:

```
SKCOMLib.py                                    41 行(re-export 門面)
_75AAD71C_8F4F_4F1F_9AEE_3D41A8C9BA5E_0_1_0.py 6,045 行(真正的 wrapper)

ISKOrderLib._methods_  = [COMMETHOD(...) ×147]   ← **vtable 早期繫結**
ISKCenterLib._methods_ = [COMMETHOD(...)]        ← 同上
ISKReplyLib._methods_  = [COMMETHOD(...)]        ← 同上
_ISKOrderLibEvents._disp_methods_ = [DISPMETHOD(...) ×29]   ← dispinterface(晚期繫結,無法避免)
_ISKReplyLibEvents._disp_methods_ = [DISPMETHOD(...) ×12]   ← 同上
```

也就是說 `self._order.SendStockOrder(...)` **不走 `IDispatch::Invoke` / `GetIDsOfNames`**,
而是直接查 vtable slot + ctypes FFI。這已經是 COM 呼叫在 Python 上能做到的最快形式。

**typelib cache 已生效**:`comtypes_client.GetModule("SKCOM.dll")`(`com.py:119`)在 gen 目錄
已有對應模組時**不重新產生**,只 import。`[實測-本機]` `import comtypes.gen.SKCOMLib` = **50.9 ms**,
一次性、在啟動的 4.83 s 裡佔 1%。**不要動。**

`[實測-本機]` 送單前的 marshaling 準備 —— `STOCKORDER()` + 10 次 `setattr`
= **2.0 µs p50 / 2.6 µs p95**(用真 typelib struct 量,50k 次)。
相對於 §2 #8 的 84,000 µs,佔 **0.0024%**。B10 §7 的「不要動逐欄 setattr」判斷**成立且被量化**。

### `pywin32` 的角色:只用來 `CoInitialize` + `PumpWaitingMessages`

`com.py:245-247` 每圈 `importlib.import_module("pythoncom")` 再 `PumpWaitingMessages()`。
`[實測-本機]`:

| 動作 | p50 | p95 | max |
|---|---:|---:|---:|
| `importlib.import_module("pythoncom")`(已 cache) | **0.30 µs** | 0.40 | 46.7 |
| `PumpWaitingMessages()`(空佇列) | **0.10 µs** | 0.20 | 11.6 |
| 合計(= `com.pump()` 等價) | **0.40 µs** | 0.80 | 37.7 |

以 16 圈/秒算 = **6.4 µs/秒**。**明確不是問題,不要為了省 `importlib` 去做模組級 import**
(那會打破「CI 無 COM 環境也要能 import `copycat.capital.com`」這個檔頭寫死的約定)。

### 唯一真的值得評估的工具:`win32event.MsgWaitForMultipleObjects`

現況的 `_pump_once()` + `_cmd_q.get(timeout=0.05)` 是**輪詢**,而 `[實測-本機]` 顯示
`queue.get(timeout=0.05)` 實際是 **62.3 ms p50 / 63.7 p95**(Windows 15.6 ms timer 精度),
所以幫浦圈是 **16 Hz 不是 20 Hz**。

pywin32 已裝,`win32event.MsgWaitForMultipleObjects([event], False, timeout, QS_ALLINPUT)`
可以**同時**等「COM 訊息到達」與「命令 event 被設定」,把輪詢換成事件驅動:
命令入列 → 立刻醒;COM 事件到達 → 立刻 pump。

**但**:`[實測-本機]` 現況的 `put → get` 喚醒已經是 **15.9 µs p50**(`queue.Queue` 本來就是
condition variable,不是輪詢醒)—— 也就是說**命令那一半已經是事件驅動的**,
輪詢只影響「沒有命令時多久 pump 一次 COM 事件」。而 COM 事件在 STA 上會排進訊息佇列,
最多晚 62 ms 被 dispatch。

**判決:不建議現在做。** 收益(回報事件最多早 62 ms 被處理)遠小於代價
(重寫 `_run` 的主迴圈 = 動整個下單鏈最核心的 30 行,而它經過 N017/F1-F7/review P0 多輪打磨)。
**先做 §5 #10 的非同步下單** —— 那才是把 `pump` 的空窗從「4 秒」變成「62 ms」的那一刀。

### `timeBeginPeriod(1)`(winmm)

把行程的 timer 精度從 15.6 ms 降到 1 ms,會讓 `queue.get(timeout=0.05)` 真的是 ~50 ms、
`asyncio.sleep(0.05)` 的 12.43 ms overshoot 降到 ~1 ms。
**有條件導入**:它是**全行程**生效的,會同時改變 stock/index/futures/corr 每一條引擎的節奏,
屬於「看盤區塊」的決策不是 D2 的。列出來是因為本報告量到的 62.3 ms 就是它造成的,
別的區塊要動時要知道 capital 的幫浦圈跟著變。

### 明確不建議

| 工具 | 理由 |
|---|---|
| 改用 `win32com.client`(pywin32 的 COM) | `win32com.client.Dispatch` 預設是 **late binding**(IDispatch),比現況慢;`gencache.EnsureDispatch` 才是 early binding,而那等於把 comtypes 換成 pywin32 重做一次同樣的事,零收益、高風險 |
| `numpy` / `polars` / `orjson` / `msgspec` | 這個區塊零數值批次、零大量序列化。COM struct 是 ctypes 值型別,向量化無從下手 |
| 第二條 COM 執行緒 | SKCOM 單一登入 + STA apartment 親和性,架構上不成立(B10 F-04 的硬約束成立) |
| `asyncio` 包裝 COM(`loop.run_in_executor` 直呼 SKCOM) | 會把 COM 呼叫散到預設池的任意執行緒上 = 系統性地違反 apartment 親和性。**比現在 F-05 那一處嚴重得多** |

---

## 7. 這裡不要動(反向結論,附量化理由)

| 位置 | 為什麼不要動 |
|---|---|
| `com.py:150-153` 的逐欄 `setattr` | `[實測-本機]` 2.0 µs,佔送單延遲 0.0024%。COM struct 是值型別,「重用模板」的正確性風險(殘留欄位)遠大於收益 |
| `com.py:245-247` 每圈 `importlib.import_module("pythoncom")` | `[實測-本機]` 0.30 µs × 16/s = 5 µs/s。改成模組級 import 會打破「CI 無 COM 環境可 import」的檔頭約定 |
| `comtypes` 的 early-binding gen module | `[typelib]` 已確認是 `COMMETHOD` vtable,不是 IDispatch。已經是最快形式;`GetModule` 已走 cache(50.9 ms 一次性) |
| `_run` 的 `_cmd_q.get(timeout=0.05)` 這個 50 ms 常數 | `[實測-本機]` `put → get` 喚醒 **15.9 µs** —— 命令那一半本來就是事件驅動的,縮 timeout 只是燒 CPU。要縮的是 `fn()` 的阻塞(§5 #10) |
| `factory.py:96-99` 的 `CAPITAL_ENV` 未知值 → `None` | 唯一正確的方向:「不呼叫 SetAuthority 的預設就是正式環境」,拼錯寧可整個不啟用 |
| `client.py:731-740` 的 test/prod `SetAuthority` 失敗分流 | 同上;test 失敗 raise、prod 失敗續行是刻意的非對稱,不是疏漏 |
| `com.py:261-262` `OnReplyMessage` 回 `-1` | `[typelib]` 該事件簽名有 `[out] sConfirmCode`,comtypes 把回傳值映成該 out 參數 —— 現況寫法正確。漏掛會吃 `SK_WARNING_REGISTER_REPLYLIB_ONREPLYMESSAGE_FIRST` |
| `com.py:199-209` `TSPROFITLOSSGWQUERY` 的字串欄一律帶 `""` | 註解已寫明:comtypes 未設的 BSTR 是 `None`,群益端行為未定義。這是防禦性正確,不是冗餘 |
| `com.py:94, 96, 98` 三個「存著避免 GC」的欄位 | `_dll_cookie` / `_reply_conn` / `_order_conn` —— 丟掉會被 GC → Unadvise → 事件全斷。這是 comtypes 的真實坑 |
| `client.py` 的 `BalanceCollector` 欠帳 / 放棄輪 / 時間窗機器 | 它解的是「COM 回呼無查詢識別」這個 SKCOM 固有問題,是**正確性**機器不是效能機器 |
| `_WRITE_TIMEOUT_S` / `_CLOSE_INFLIGHT_S` / `_PENDING_TIMEOUT_S` / `_BALANCE_CHAIN_TIMEOUT_S` | 它們是**結果未知語意**的參數不是效能參數。§5 #4 的分段時戳落地前不要動任何一個 |
| `mapping.py` 的 `bstrPrice="0"` 市價單映射 | `[實測-prod]` 13 筆全 `code 0`,已驗證。**只要改註解**(F-15),不要改值 |

---

## 8. Open questions(查不出來,需 prod 觀察或 user / 群益回答)

1. **`OnConnect` / `OnDisconnect` 為什麼從沒響?** F-01 的 Solace 假說要證實,最便宜的驗法是
   §5 #1(掛上 `OnSolaceReplyConnection` 看盤中有沒有東西來)。
   若連 Solace 事件也沒有 → 回報連線健康只能靠 `SKReplyLib_IsConnectedByID` 輪詢。
2. **群益登入 session 有沒有有效期?** `[實測-prod]` 同一 process 連跑 2 天 3.5 小時未重登且送單正常
   (09-11 → 09-13),但那期間有沒有跨到「群益端 session 過期」的門檻不知道。
   → 決定 F-11 的重登策略要不要做成定時的。
3. **05:50–05:55 的每日 GW 失敗窗(F-07),送單通道是否同窗?** 夜盤 05:00 已收盤所以目前無影響,
   但這決定「能不能在 05:00 前的夜盤尾聲下單」。要問群益或在該窗送一筆遠價安全單實測。
4. **`bAsyncOrder=1` 時哪一個事件會來**(`OnAsyncOrder` / `OnAsyncOrderGW` / `OnAsyncOrderOLID`)?
   → 決定 §5 #10 的 sink 要掛幾個。shadow 階段一次全掛就有答案。
5. **`GetOrderReport` / `GetFulfillReport` 的 `nFormat` 值域與回傳列格式?**
   → 決定 §5 #9 能不能做。這是和 `GetOpenInterestGW` 一樣的「欄序 prod 校正」坑。
6. **`SetMaxQty` / `SetMaxCount` 的 `nMarketType` 值域,以及 DLL 端有沒有預設上限?**
   `[實測-prod]` 369 筆送單都是 `qty=1`,從沒撞過 —— 所以「沒撞過」不等於「沒有上限」。
   user 要放大單量前必須先問清楚。`UnlockOrder` 同理(369 筆成功證明目前不需要,但不知道在什麼條件下需要)。
7. **`TMFI6無法轉換商品ID`(code 400,3 筆,2026-08-24 夜盤)後來解決了嗎?**
   審計裡之後沒有再出現微台送單 → 不知道是修好了還是 user 不再下微台。
   若沒修,`to_exchange_symbol` 對 TMF 產生的碼群益端就是不認,微台送單永遠失敗。
8. **`CAPITAL_FULL_ACCOUNT` 與 `GetUserAccount` 回來的 `TS` 列一致嗎?**(F-10)
   現在沒有任何比對。要 user 確認 `TS` 列的欄序在他的帳號型態下是不是
   `市場,經紀商,分公司,帳號,…`(`_parse_account_row` 的假設,docstring 自承「prod 實測後校正」而至今無實錄)。

---

## 附:本輪對上一輪報告的修正

| 上一輪 | 本輪的修正 | 依據 |
|---|---|---|
| B10 F-02:跨 apartment 呼叫「會走 COM marshaling → 死鎖或長阻塞」 | **機制錯了**。`ISKCenterLib` 是 vtable 早期繫結、`CreateObject` 拿的是 in-proc 直接指標、comtypes 不自動 marshal → **不會死鎖**。真正的風險是**無同步地並行進入同一個 in-proc COM 物件**(data race)。修法不變,嚴重度從「可能死鎖」降為「未定義行為 + 可能拿到錯字串」 | `[typelib]` `ISKCenterLib._methods_ = [COMMETHOD…]` |
| B10 F-13:`degraded` 放行送單是「盲送但使用者被告知」 | **`degraded` 從來不會亮**(F-01)。所以不是「告知不足」,是**完全沒有告知**。優先序從 medium 升到 critical | `[實測-prod]` OnConnect/OnDisconnect 0 次 / OnNewData 3,531 次 |
| B10 §9 open question 3:「SKCOM 的 `STOCKORDER` / `FUTUREORDER` 有沒有 user-defined 欄位?」 | **答案是沒有**。STOCKORDER 14 欄、FUTUREORDER 36 欄全部列出,`bstrSeqNo` / `bstrBookNo` 是既有委託識別不是自訂欄。替代方案 = `bAsyncOrder=1` 的 `nThreaID` | `[typelib]` `STOCKORDER._fields_` / `FUTUREORDER._fields_` |
| B10 §9 open question 1:「`SendStockOrder` 同步呼叫的實際耗時分佈?整條鏈唯一的黑盒」 | **量出來了**:期望值 84 ms、P(≥1 s)=7.6%、max 4 s;且拒單(code 999)比成功單慢 | `[實測-prod]` 499 筆審計 pre/post 秒級配對 |
| B10「幫浦圈 ≥ 20 圈/秒」 | **實際 16 圈/秒**(`queue.get(timeout=0.05)` 真實耗時 62.3 ms,Windows timer 精度) | `[實測-本機]` |
| `mapping.py:248-256`「市價單字面 `"0"` 推定未實測」 | **已被 prod 實證**:修正後 13 筆市價單全 `code 0` | `[實測-prod]` 審計 |
