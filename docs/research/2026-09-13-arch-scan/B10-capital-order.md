# B10 — 群益 Capital 下單鏈 架構/效能掃描報告

> 區塊:`copycat/capital/*`(com / client / models / safety / mapping / reply / store /
> balance / close / factory)+ `copycat/server/capital_api.py` + `copycat/server/audit.py`
> 掃描日期:2026-09-13 · 掃描者:B10 sub-agent · 目標:把「按鈕 → 送出券商」這條
> **延遲最敏感**的鏈逐段拆開,回答「現在多慢、哪裡慢、要換什麼」。
>
> **所有數字都是本機實測**(Python 3.13 / Windows 11 / 16 core)。微基準腳本留在
> `scratchpad/bench_capital.py`、`bench_store.py`、`bench_audit2.py`、`bench_log.py`,
> 可重跑。未量測的段落一律明寫「未量測」或「推測」。

---

## 0. 一句話結論

這條鏈的**程式碼本身不慢**(純 Python 段合計 p50 < 1.5 ms),但它有三個**結構性的
不可預測阻塞源**:(a) 送單前置審計走的是與 TC4 / FinMind 共用的 asyncio 預設
thread pool,無上界排隊;(b) 送單命令與行情回報、部位回查鏈共用**同一條** COM 執行緒
且**沒有優先權**;(c) `return_code_message()` 在 event loop 上跨 apartment 直呼 COM。
再加上一個量化系統的硬缺口:**整條鏈零延遲量測、零冪等鍵、零 runtime kill switch**。

要「改成專注高效能的量化交易系統」,這個區塊該做的**不是**換數值套件(這裡一個
numpy 用得上的地方都沒有),而是:**把寫入路徑從共享資源上隔離出來,並且把它變成
可量測的**。

---

## 1. 架構地圖

```
瀏覽器 (React)
  PriceLadder.tsx / OrderPanel / CapitalPositionsList
    └─ useCapital.ts::useCapitalMutation  →  fetch POST /api/capital/order/stock
                                              (看盤日常經 vite preview 4173 proxy → 8721)
           │
           ▼  ── event loop thread(uvicorn,單一 loop,與全部 TC4 tick fanout 共用)
  server/capital_api.py
    ├─ pydantic BaseModel 驗形(StockOrderBody / FutureOrderBody / …)
    ├─ _capital(request)                  → app.state.capital(None = 503 DISABLED)
    ├─ [future] product_of → _stkfut_gates(lookup_product) → multiplier_of
    │           → futures.resolved_contract → to_exchange_symbol
    ├─ [correct-price fut] _correct_price_tick_gate → client.store.orders() ← 全表建構
    ├─ [close fut] _close_tick_gate
    └─ → dataclass(StockOrderRequest / …)
           │
           ▼
  capital/client.py::submit_stock_order / submit_future_order / cancel / correct / decrease / close
    └─ _execute_write(action, req, gate, com_call)
         1. gate.allowed?              ← safety.py 純算術
         2. status in (ok, degraded)?
         3. await to_thread(_audit(前置))   ← ★ 共享預設 executor + 檔案 IO
         4. fut = loop.create_future(); _cmd_q.put((com_call, fut))
         5. await wait_for(shield(fut), 10s)
         6. self._com.return_code_message(code)  ← ★ 在 loop 上直呼 COM(跨 apartment)
         7. await to_thread(_audit(後置))   ← ★ 再一次共享池 + 檔案 IO
         8. code != 0 → raise BrokerRejectedError(400)
           │
           ▼  ── capital-com thread(daemon,CoInitialize STA,唯一 COM apartment)
  client.py::_run
    while True:
        _pump_once()                     ← com.pump() + 3×collector.poll
                                           + _maybe_query_balance() + _poll_pending()
        cmd = _cmd_q.get(timeout=0.05)   ← ★ 寫入命令只有在這一行才被取走
        result = fn()                    ← SkcomCapitalCom.send_stock_order(...)
        loop.call_soon_threadsafe(_settle, fut, result, exc)
           │
           ▼
  capital/com.py::SkcomCapitalCom
    order = sk.STOCKORDER(); for k,v in fields: setattr(order, k, v)
    message, code = self._order.SendStockOrder(user_id, 0, order)   ← bAsync=0 同步
           │
           ▼
        SKCOM.dll  →  群益主機  →  交易所
```

### 回流(回報 / 部位)是另一條路,但**共用同一條 COM 執行緒**

```
群益回報主機 ─OnNewData→ com.py::_ReplyEvents.OnNewData
                            (由 capital-com thread 的 pythoncom.PumpWaitingMessages() dispatch)
   └─ client._handle_reply(bstr_data)
        ├─ reply.parse_onnewdata()            split(",") + 48 欄取值
        ├─ store.apply_reply(rec)             ★ 取 store._lock(threading.Lock)
        │     └─ D 事件 → _append_fill_locked + _apply_fill_locked
        │           └─ _with_today_qty_locked → _today_net_lots_locked  ← 掃全部委託 O(N)
        ├─ D → _mark_balance_dirty(0.5s)      → 觸發回查鏈
        └─ _emit → loop.call_soon_threadsafe(capital_ws.publish, payload)
                       └─ WS fanout → 前端 useCapitalStream → 200ms debounce invalidate
                                        → GET /api/capital/orders + /positions + /fills

回查鏈(串行三段,每 60 s 定時 + 每筆成交後 0.5 s debounce):
   _maybe_query_balance → com.get_real_balance()      [同步 COM 呼叫,在 pump 圈內]
      → OnRealBalanceReport ×N → BalanceCollector.feed → _on_balance_complete
         → com.get_profit_loss_gw()                    [同步 COM 呼叫]
            → OnProfitLossGWReport ×N → _on_profit_complete(回填均價)
               → com.get_open_interest()               [同步 COM 呼叫]
                  → OnOpenInterest ×N → _on_oi_complete
                     → _finalize_positions → store.set_positions(全量覆蓋 + 水位重套)
                        → _emit capital_position
```

### 檔案清單與職責

| 檔 | LOC | 職責 | 熱路徑? |
|---|---:|---|---|
| `client.py` | 1216 | COM 執行緒生命週期、寫入骨架、回查鏈狀態機、審計接線 | **是**(送單 + 每筆回報) |
| `store.py` | 758 | 委託聚合 / 部位 / 逐筆成交 / 價格別記憶(threading.Lock) | **是**(每筆回報 + 每次 REST) |
| `server/capital_api.py` | 451 | pydantic → dataclass、個股期三道 tick 閘、例外映射、WS route | **是**(每筆送單 + 每次輪詢) |
| `balance.py` | 402 | 三種回報列 parser + BalanceCollector 欠帳/時間窗狀態機 | 中(每 60 s × 每列) |
| `mapping.py` | 296 | TC4 symbol ↔ 期交所契約碼、SKCOM 欄位映射 | 是(每筆期權送單,但 µs 級) |
| `models.py` | 186 | frozen dataclass request + OrderRecord / Position / FillRecord | — |
| `com.py` | 336 | comtypes 封裝 + 事件 sink | 是(COM 呼叫本體) |
| `reply.py` | 131 | OnNewData 逐欄 parser | 是(每筆回報) |
| `safety.py` | 112 | 五個純函式閘 | 是(但 < 5 µs) |
| `close.py` | 86 | 平倉反向單組裝 `_CLOSE_MAP` | 是(每筆平倉) |
| `factory.py` | 121 | env → CapitalClient 單例 | 否(啟動一次) |
| `server/audit.py` | 38 | JSONL append + module lock | **是**(每筆寫入 ×2) |

---

## 2. 熱路徑逐條(含頻率與實測工作量)

### H1 — `client._run` 的幫浦圈(capital-com thread)
**位置** `copycat/capital/client.py:795-838`
**頻率** ≥ 20 圈/秒(`_cmd_q.get(timeout=0.05)`),盤中回報密集時更高。
**每圈工作**
```python
def _pump_once(self) -> None:
    try:
        self._com.pump()          # pythoncom.PumpWaitingMessages() — dispatch 全部待處理 COM 事件
        self._balance.poll()      # 三個 collector 的 timeout flush 保險
        self._profit.poll()
        self._oi.poll()
        self._maybe_query_balance()  # 可能發出同步 COM 查詢 GetRealBalanceReport
        self._poll_pending()
    except Exception:
        logger.exception("COM 幫浦圈例外(本輪略過)")
        time.sleep(1.0)           # ★ 佔住唯一的送單執行緒 1 秒
```
**要點**:`com.pump()` 是把**所有**排隊的 COM 事件 inline 跑完,含 `_handle_reply`
的整條處理(parse + store 鎖 + 樂觀套用 + call_soon_threadsafe)。開盤
`SKReplyLib_ConnectByID` 重播當日 backlog 時,這一次 `pump()` 可能是數百則回報。
寫入命令在 `_pump_once()` 之後才被 `get()` 取走 → **pump 有多久,送單就多等多久**。
`pump()` 本體耗時未量測(需 prod)。

### H2 — `_handle_reply`(每筆委託 / 成交 / 刪改回報)
**位置** `client.py:402-453` → `store.apply_reply` `store.py:188-258`
**頻率** 每張單 2–5 則;開盤 backlog 重播一次數百則;活躍當沖日單日總量推測數百至數千則。
**實測**(`bench_store.py`,合成 OnNewData 48 欄)

| 委託聚合筆數 N | `apply_reply(D)` p50 | p95 |
|---:|---:|---:|
| 50 | 0.026 ms | 0.047 ms |
| 200 | 0.034 ms | 0.061 ms |
| 1000 | 0.069 ms | 0.106 ms |

成長來自 `_today_net_lots_locked`(`store.py:300-321`)每次部位更新掃全部委託:
```python
for a in self._orders.values():
    if a.stock_no != stock_no or a.market not in _SEC_LOT_MARKETS or a.filled_qty <= 0:
        continue
```
**判定:不是問題**。N=1000 時 50 筆/秒也只有 3.5 ms/s。

### H3 — `_execute_write`(送單 / 刪 / 改 / 減 / 平倉)
**位置** `client.py:865-922`
**頻率** 人手驅動。閃電梯鎖定態下峰值推測每秒數筆;正常每分鐘數筆。
**實測分段**(本機,池空)

| 段 | p50 | p95 | max |
|---|---:|---:|---:|
| `to_thread` + `append_audit`(前置) | 0.383 ms | 0.499 ms | **2.751 ms** |
| `_cmd_q.put` → `call_soon_threadsafe` → `await fut` 往返 | 0.212 ms | 0.822 ms | 1.877 ms |
| `to_thread` + `append_audit`(後置) | 同前置 | | |
| safety gate(純算術) | < 0.005 ms | | |
| `mapping` 期權符號解析鏈 | < 0.05 ms(含 1–2 次 `stat()` @ 0.004 ms) | | |
| `SendStockOrder`(SKCOM 同步) | **未量測** — prod-only,推測是整條鏈最大的一段 | | |

**純 Python 段合計 p50 ≈ 1.0 ms、p95 ≈ 1.8 ms。** 但這是**池空、loop 空**的數字;
下面的 F-01 / F-04 說明為什麼實務上這個數字沒有上界。

### H4 — capital REST 三支(前端輪詢 + WS 事件 debounce)
**位置** `capital_api.py:253-291`
**頻率** `positions` 15 s、`fills` 30 s、`orders` 30 s(`useCapital.ts:154/159/190/195`),
**外加**每個 `capital_order` / `capital_position` WS 事件的 200 ms trailing debounce
invalidate(`useCapital.ts:120-143`)—— 也就是說**每一筆成交都會多打一輪**。
**實測**(`store.orders()` + `dataclasses.asdict`,在 event loop 上跑)

| 委託筆數 N | `store.orders()`(持鎖) | `[asdict(o) for o in orders()]` |
|---:|---:|---:|
| 50 | 0.135 ms | 0.288 ms |
| 200 | 0.422 ms | 1.514 ms |
| 1000 | **2.629 ms** | **7.224 ms** |

`positions()` 在所有 N 下都是 0.000 ms(只是 `list(dict.values())`)。

### H5 — 部位回查鏈三段(balance → profit → OI)
**位置** `client.py:478-703`
**頻率** 每 60 s 定時(`stale = now - _balance_last_ts >= 60.0`)+ 每筆成交後 0.5 s debounce。
**每輪工作**:三次同步 COM 查詢 + 每列一次 `collector.feed`(split + 15~26 欄取值)+
`set_positions` 全量替換。
**實測 `set_positions`**

| 委託 N / 部位 M | p50 | p95 |
|---|---:|---:|
| N=200, M=10 | 0.172 ms | 0.243 ms |
| N=200, M=50 | 0.599 ms | 0.710 ms |
| N=1000, M=50 | **2.505 ms** | 4.208 ms |

成長來自 `_with_today_qty_locked` 對每一列部位掃全部委託(O(M×N))。
**判定:60 s 一次的 2.5 ms 不是效能問題**,但它是**持 `store._lock` 在 COM 執行緒上**
跑的 2.5 ms(見 F-07)。

鏈的**端到端延遲是秒級**(0.5 s debounce + 三段 COM 往返 + 每段最長 1 s collector
timeout),這才是使用者「下單後倉位很慢」的結構性來源 —— 已由樂觀套用
(`_apply_fill_locked`)緩解,但**零股 / 無券買向 / 選擇權 / 契約碼不明 / 未滿張一律不套**
(`client.py:438-444` 的 else 分支就是在記這些)。

---

## 3. Findings(依嚴重度)

### F-01 【critical】前置審計走共享預設 executor,可被 TC4 / FinMind 執行緒無上界卡住

**位置** `copycat/capital/client.py:344-347, 884-885`

```python
async def _audit_blocked(self, action, req, reason) -> None:
    await asyncio.to_thread(self._audit, self._record(action, req, blocked=reason))
...
# _execute_write
await asyncio.to_thread(self._audit, self._record(action, req))   # ← 送單前,必過
fut: asyncio.Future[...] = self._loop.create_future()
self._cmd_q.put((com_call, fut))
```

`asyncio.to_thread` 用的是 **loop 的預設 executor**,全庫沒有任何
`set_default_executor` / `ThreadPoolExecutor`(已 grep 確認)。本機 `max_workers =
min(32, 16+4) = 20`。同一個池上跑的還有:

- `stock_engine` 的 `to_thread(self._acquire/_release/_retry_acquire/_resubscribe_all)`
  —— TC4 ZMQ REQ,`_REQ_TIMEOUT_MS = 10_000`、`DEFAULT_LOCK_TIMEOUT_SECS` 12 s
  (`live/tc4.py:120` 及該檔 §X-2a 註解「首個輸家最壞 12+12s」);
- `index_engine` / `corr_engine` / `futures_engine` / `engine` 的訂閱、回補、close;
- `breadth_engine` 的 FinMind 取數(`breadth_fetch.py:63` `timeout=30`,EOD 那支 60 s);
- `app.py:1581` 的 `to_thread(hub.today_signals)`(整份 jsonl 同步讀)。

`app.py:1568-1572` 自己已經寫下這條風險:

> `to_thread` 走 loop 預設 executor,與 daily_bars / capital close 同池且工作執行緒
> **不可中斷** —— TC4 半死的殭屍執行緒堆積時這條會跟著排隊(review C-1)

**同一句話原封不動適用於送單前置審計,而它擋在真錢送出之前。**

**影響**:正常情況 p50 0.38 ms;池被 20 條 TC4 半死執行緒佔滿時,送單要等到有 worker
空出來 —— 每條最壞 10–22 s,**沒有上界、沒有任何錯誤訊號**(HTTP 就是一直轉)。
這是整個 B10 區塊裡唯一一個「延遲可以到秒級甚至分鐘級」的段落。

**修法**(stdlib,零新相依):
```python
# client.__init__
self._audit_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="capital-audit")
# _execute_write
await self._loop.run_in_executor(self._audit_pool, self._audit, record)
```
或更激進(見 F-05 的量測):**直接在 loop 上同步寫**,inline 0.35 ms(含 fsync),
完全繞開 executor。兩者都保住「審計前置失敗 = 錢沒動整筆失敗」這條 design §3 不變量。
`close()` 時記得 `self._audit_pool.shutdown(wait=True)` —— 這會進
`shutdown_budget.run_grace_secs()` 的預算(見 §5 契約)。

---

### F-02 【high】`return_code_message()` 在 event loop 上跨 apartment 直呼 COM

**位置** `client.py:910`(成功路徑)、`client.py:373`(late 路徑)

```python
# _execute_write —— 這是 async 函式,跑在 event loop thread
message, code = await asyncio.wait_for(asyncio.shield(fut), timeout=_WRITE_TIMEOUT_S)
...
ok = code == 0
text = f"{self._com.return_code_message(code)} {message}".strip()   # ← COM 呼叫
```
```python
# com.py:242
def return_code_message(self, code: int) -> str:
    return self._center.SKCenterLib_GetReturnCodeMessage(code)
```

`com.py` 的檔頭明文寫著:

> 真實實作的所有方法都必須在「同一條」CoInitialize 過的執行緒上呼叫
> (COM apartment 親和性)—— 由 CapitalClient 的專屬執行緒保證。

`_center` 是在 `_init_com()` → `setup()` 裡建的,而那是在 **capital-com thread**
(`_run` 先 `pythoncom.CoInitialize()` = STA)。`_execute_write` 的第 910 行是在
**event loop thread** 上呼叫它 —— **這條保證在成功路徑上每筆送單都被打破一次**。

`_on_late_result`(`client.py:357-398`)是 `fut.add_done_callback`,也在 loop 上,
同樣呼叫 `return_code_message`。

**影響**:
1. **正確性**:跨 apartment 直呼 STA in-proc 物件的 vtable 是未定義行為。prod 至今
   沒炸(推測 SKCenterLib 這支是純字串查表、無執行緒親和需求),但這是「靠運氣成立」
   的不變量,而不變量本身在檔頭被宣告為成立。
2. **效能**:成功路徑(`code == 0`)也無條件呼叫一次。若 comtypes 對這個介面建了
   proxy,跨執行緒呼叫會走 COM marshaling —— 需要目標 STA 幫浦,而目標 STA 正是
   capital-com thread,它此刻可能正卡在 `SendStockOrder` 裡 → **死鎖或長阻塞**。
   這是推測(未在 prod 觀察到),但機制是明確的。

**修法**:
- 短期:把 `code == 0` 的訊息 hardcode / 預先快取整張碼表。SKCOM 回傳碼是有限集合,
  啟動時在 COM 執行緒上把常見碼跑一次建 `dict[int, str]`,loop 側只查 dict。
- 或:把 `return_code_message` 的呼叫搬進 `com_call` 閉包裡(在 COM 執行緒上跑完,
  連 message 一起回來)。這是最小改動且語意不變 —— `_ComCall` 的回傳型別從
  `tuple[str, int]` 擴成 `tuple[str, int, str]`。

---

### F-03 【high】幫浦圈的例外分支 `time.sleep(1.0)` 佔住唯一的送單執行緒

**位置** `client.py:791-793`

```python
except Exception:  # noqa: BLE001 — 單輪故障記 log 續命,見 docstring
    logger.exception("COM 幫浦圈例外(本輪略過)")
    time.sleep(1.0)  # 持續性故障時防 log 洪水
```

這條 sleep 跑在 `_run` 的 `_pump_once()` 裡,而 `_cmd_q.get()` 在它**之後**。
持續性故障(TC4/群益端半死、collector flush 鏈打 COM 拋 COMError)時,
**每圈睡 1 秒 = 送單命令最壞等 1 秒才被取走**,而且這個狀態下 `self._status`
仍然是 `ok`(例外被吞掉,狀態沒降)→ 前置檢查放行,使用者只看到按鈕轉圈。

**修法**:退避不要 sleep,改成把退避掛在**佇列等待**上,讓寫入命令能搶先:
```python
except Exception:
    logger.exception(...)
    self._backoff_until = time.monotonic() + 1.0   # 下一圈跳過 pump,但 get() 照跑
```
`get(timeout=0.05)` 本來就是阻塞等待 —— 退避期間照樣每 50 ms 檢查一次命令佇列,
零成本、零 log 洪水。

---

### F-04 【high】寫入命令與回查鏈 / 回報處理共用單一執行緒,且**沒有優先權**

**位置** `client.py:808-816`

```python
while True:
    self._pump_once()                      # ← 含 com.pump() 與同步 COM 查詢
    try:
        cmd = self._cmd_q.get(timeout=0.05)
    except queue.Empty:
        continue
```

`_pump_once` → `_maybe_query_balance`(`client.py:478-528`)在 due / 60 s stale 時
**直接發同步 COM 查詢**:
```python
rc = self._com.get_real_balance(self._user_id, self._full_account)
```
`_on_balance_complete` / `_query_open_interest` 也各有一次同步 COM 查詢,它們是在
`com.pump()` 的事件 dispatch 內被呼叫的 —— 也就是**在 `_pump_once()` 的同一圈裡**。

結果:一筆送單命令若剛好在 `_pump_once()` 開始後入列,要等這一圈的
`pump + 3×poll + 可能的 GetRealBalanceReport/GetProfitLossGWReport/GetOpenInterestGW`
全部跑完。而回查鏈的觸發條件正是「**剛剛有成交**」(`_mark_balance_dirty(0.5)`)
—— 也就是說**連續下單的第二筆,最容易撞上第一筆成交觸發的回查鏈**。

SKCOM 同步查詢耗時未量測(prod-only),但既然 `_BALANCE_CHAIN_TIMEOUT_S = 10.0`
是為「零事件死查詢」設的守門,設計者自己預期它可以是秒級。

**架構限制(硬約束)**:SKCOM 物件是 STA 綁在建立它的執行緒上,**不能**開第二條
執行緒做寫入通道 —— 單一登入、單一 apartment。所以「分離讀寫執行緒」在這個
API 下不可行。

**可行修法(不改 apartment 模型)**:
1. **寫入優先權**:每圈先 `get_nowait()` 看有沒有寫入命令,有就先執行再 pump:
   ```python
   while True:
       cmd = self._drain_one_nowait()          # 寫入優先
       if cmd is not None: self._exec(cmd); continue
       self._pump_once()
       try: cmd = self._cmd_q.get(timeout=0.05)
       ...
   ```
2. **回查鏈讓路**:`_maybe_query_balance` 進門先 `if not self._cmd_q.empty(): return`
   —— 有寫入命令在排隊時,這一圈不發回查。回查晚 50 ms 沒有任何後果(它本來就是
   0.5 s debounce + 60 s 輪詢),而送單早 N 毫秒是真錢。

這兩條都是十行內的改動,不動任何跨檔契約。

---

### F-05 【high】`append_audit` 每筆重開檔(0.25 ms)且**沒有 fsync** —— 貴又不耐

**位置** `copycat/server/audit.py:28-38`

```python
def append_audit(base, record, *, when, prefix="orders") -> None:
    path = audit_path(base, when, prefix=prefix)
    line = json.dumps(record, ensure_ascii=False)
    try:
        with _audit_lock:
            base.mkdir(parents=True, exist_ok=True)     # 每筆一次 syscall
            with open(path, "a", encoding="utf-8") as fh:   # 每筆 open + close
                fh.write(line + "\n")
                fh.flush()                               # 只 flush,不 fsync
    except OSError as exc:
        raise AuditWriteError(str(exc)) from exc
```

**實測**(`bench_audit2.py`,同一顆 SSD、同一個目錄):

| 寫法 | p50 | p95 | max |
|---|---:|---:|---:|
| 現況:`mkdir + open + write + flush + close` | **0.2535 ms** | 0.3444 ms | 1.050 ms |
| persistent handle(`ab`, buffering=0)只 write | **0.0041 ms** | 0.0085 ms | 0.106 ms |
| persistent handle + `os.fsync` | **0.3417 ms** | 0.4694 ms | 1.388 ms |
| `json.dumps` 本身 | 0.0024 ms | 0.0042 ms | 0.031 ms |

**兩個結論**:
1. 現況的 0.25 ms 有 **98% 花在 open/close**,不在寫入也不在 JSON 編碼。
2. **保持檔案開著 + 真 fsync 的成本(0.34 ms)跟現在「開開關關但不 fsync」的成本
   幾乎一樣。** 也就是說可以**免費把稽核從「作業系統 page cache 級」升級成
   「真的落盤」** —— 對一個宣稱 append-only 審計、要拿去對帳真錢的系統,這是白撿的。

現況的耐久性缺口很具體:`fh.flush()` 只是把 Python buffer 推到 OS,斷電 / 藍屏
會丟掉最後幾筆 —— 而最後幾筆正是事故當下那幾筆。

**修法**:client 持有 per-day 的 append handle(日界換檔時 close 舊開新),
`_audit()` 直接 `fh.write(line); os.fsync(fh.fileno())`。配合 F-01 的
「inline 在 loop 上寫」,整個前置審計段從「to_thread 0.38 ms + 無上界排隊風險」
變成「inline 0.35 ms + 真 durable + 零排隊風險」。

**風險**:磁碟被防毒掃描 / 雲端同步資料夾(OneDrive)吃住時 fsync 尾巴會爆。
落地前要先量 `CAPITAL_AUDIT_DIR` 實際位置的 fsync p99。

---

### F-06 【medium-high】三條路徑各自呼叫 `store.orders()` 建全表,只為找一筆

**位置**
- `capital_api.py:191` — `_correct_price_tick_gate`
  ```python
  rec = next((o for o in client.store.orders() if o.seq_no == seq_no), None)
  ```
- `client.py:1065` — `_fut_multiplier`
  ```python
  rec = next((o for o in self.store.orders() if o.seq_no == seq_no), None)
  ```
- `client.py:1139` — `_close_dup_reason`
  ```python
  for o in self.store.orders():
      if o.actionable and o.stock_no == scan_key and o.buy_sell == want:
  ```

`store.orders()`(`store.py:594-603`)會:取鎖 → 建 `arrival` 索引 dict → 對全部委託
`sorted()` → 對每一筆跑 `_to_record()`(建 OrderRecord dataclass + `_price_type_of`
查表)。實測 N=1000 時 **2.629 ms**,而三條路徑只要其中一筆。

改價路徑最糟:`_correct_price_tick_gate`(route 層)建一次全表,接著
`client.correct_price` → `_fut_multiplier` **再建一次全表**,同一筆 seq_no 查兩次。
N=1000 的期貨改價 = 5.3 ms 純浪費,全部在 event loop 上、全部持 store 鎖。

**修法**:`CapitalStore` 補一支 `order_of(seq_no) -> OrderRecord | None`,
鎖內 `self._orders.get(seq_no)` 後只 `_to_record` 那一筆 —— O(1),~5 µs。
三個 caller 改用它。零跨檔契約影響(`OrderRecord` 形狀不變)。

---

### F-07 【medium】`store._lock` 是 `threading.Lock`,route handler 在 event loop 上直接 acquire

**位置** `store.py:143` `self._lock = threading.Lock()`,取鎖者橫跨兩條執行緒:

| 呼叫者 | 執行緒 | 鎖內工作 |
|---|---|---|
| `apply_reply` | capital-com | 聚合更新 + 樂觀套用(0.03–0.11 ms) |
| `set_positions` | capital-com | 全量替換 + 水位重套(N=1000/M=50 → **2.5 ms**) |
| `begin_snapshot` | capital-com | 建水位 dict |
| `orders()` / `fills()` | **event loop** | 全表建構(N=1000 → **2.6 ms**) |
| `positions()` / `market_of` / `remaining_shares` / `position_for` | **event loop** | O(1)~O(M) |

`threading.Lock.acquire()` 在 event loop 上是**真阻塞**(不是 `await`)。兩個方向都會:
- REST `/api/capital/orders`(每 30 s + 每筆成交 debounce)持鎖 2.6 ms → 同期到達的
  成交回報在 COM 執行緒上排隊等鎖 → 樂觀套用延後 → 「下單後倉位很慢」再加一點;
- 反過來 `set_positions` 持鎖 2.5 ms → **整條 event loop 凍住 2.5 ms**(不只 capital
  route,連 8 條 WS 的 fanout 一起停)。

現況 N 不大時這是次毫秒等級、可以忍。**但它是一條「隨單日委託筆數線性惡化」的路**,
而且惡化方向是「越忙越慢」—— 正好與量化系統要的相反。

**修法(兩選一)**:
1. 保守:先做 F-06(把 O(N) 全表查詢降成 O(1)),再把 `orders()` 的 `_to_record`
   搬到鎖外(鎖內只 `list(self._orders.values())` 淺複製 `_Agg`)。
2. 徹底:store 改成「COM 執行緒單寫 + loop 側讀不可變快照」—— 每次寫完換一個
   frozen snapshot 物件(copy-on-write),讀端 `self._snapshot`(單一原子屬性讀,
   零鎖)。寫端成本增加、讀端成本歸零,而讀端才是跑在 event loop 上的那一邊。

---

### F-08 【medium】`/api/capital/orders` 每筆都送 `raw` 全文,而前端**沒有任何讀者**

**位置** `models.py:166` `raw: str = ""  # 最新事件原始字串(debug)`,
`capital_api.py:253-261` 走 `dataclasses.asdict(o)` 全欄輸出。

已 grep 確認:`frontend/src/types.ts:100` 宣告了 `raw: string`,但
`frontend/src/components/capital/` 與 `lib/` 下**零處讀取**。

`raw` 是整行 OnNewData(48 個逗號欄)。N=1000 時這是數百 KB 的 payload,
每 30 s + 每筆成交 debounce 打一次,而且 `dataclasses.asdict` 是**遞迴反射深拷貝**
—— 實測 N=1000 時 asdict 佔 7.2 ms(`orders()` 本身只 2.6 ms,也就是 **asdict 比
建構還貴 1.7 倍**)。

**修法**:
1. route 層直接不輸出 `raw`(前端沒讀者,`types.ts` 那行一併刪 → 但這是
   **跨檔契約異動**,要兩邊同動,詳見 §5)。
2. 用手寫 `to_dict()` 或 `msgspec.Struct` 取代 `dataclasses.asdict`。
   ⚠ **這會碰到 CLAUDE.md §4 的 `unit` 字面值契約**(`_lot_unit` 產生的
   「張/口/股」是前端 `ladder-lots.ts` / `fill-marks.ts` 的過濾鍵,也是後端
   `_fill_code` 的期貨判準代理)—— 任何序列化重寫必須逐欄保住這三個字面值,
   `tests/capital/test_store.py` 有 lock。

---

### F-09 【high / quant-gap】沒有 client order id / 冪等鍵 —— timeout 之後無法對帳

**證據**:grep `request_id|idempot` 在 `copycat/capital/` + `capital_api.py` +
`audit.py` 下 **零命中**。審計記錄結構(`client.py:327-342`):
```python
return {
    "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
    "env": ..., "action": ..., "req": dataclasses.asdict(req),
    "blocked": ..., "result": ...,
}
```
沒有任何本方產生的唯一識別。唯一的識別是**群益回傳的** `seq_no`,而 timeout 路徑
(`client.py:892-898`)的定義就是「拿不到 seq_no」:
```python
result = OrderResult(ok=False, code=-1, message="結果未知,勿重送", seq_no=None)
```

CLAUDE.md §7 要求審計帶 `request_id`,現況沒有。

**影響**:`_WRITE_TIMEOUT_S = 10 s` 逾時後,系統無法回答「我那張單到底在不在市場上」
—— 只能靠人肉去看群益 APP。對一個要下實單的量化系統,這是最致命的缺口:
**重送與不重送都可能是錯的,而系統沒有給出判斷依據**。

**修法**:
1. 產生 `client_order_id`(uuid4 hex 前 16 碼)寫進審計的**前置**行,回應也帶回。
2. 檢查 SKCOM `STOCKORDER` / `FUTUREORDER` 有沒有 user-defined 欄位可以塞
   (`docs/research/2026-07-28-skcom-typelib.md` 有 typelib 全表,需要查證 —— 見
   §7 open question)。有的話 timeout 後可用它反查回報。
3. 沒有的話,退而求其次:timeout 後自動用「同標的 + 同方向 + 同量 + 送出後 ±N 秒」
   掃 store 的新委託,把「疑似就是這張」標出來給人確認 —— 現況連這個都沒有。

---

### F-10 【high / quant-gap】整條鏈零延遲量測;審計時戳只有**秒**解析度

**位置** `client.py:336`
```python
"ts": datetime.now().astimezone().isoformat(timespec="seconds"),
```

前置審計與後置審計各有一個 `ts`,但兩者都是秒級 → **從審計檔最多只能看出
「這筆花了 0 秒或 1 秒」**。沒有 monotonic 時戳,沒有分段(gate / audit / enqueue /
COM in / COM out)的時間點,`/api/health` 也不含 capital 任何指標
(`ws.py` 註解明寫「`/api/health` 刻意不含引擎健康度」)。

現有的唯一觀測是 `_log_chain_stage`(`client.py:674-685`)量「成交回報到達 → 回查鏈
各段」的毫秒數 —— 那是**回流**方向,不是送單方向。

**影響**:「要不要優化」這個問題目前在 prod 無法用證據回答。本報告的所有數字都是
本機合成,`SendStockOrder` 這一段(推測是最大的一段)完全是黑盒。

**修法**(stdlib,零相依):在 `_execute_write` 用 `time.perf_counter_ns()` 打五個點,
把差值(µs)寫進後置審計行:
```python
"lat_us": {"gate": ..., "audit_pre": ..., "queue": ..., "com": ..., "audit_post": ..., "total": ...}
```
盤後 `jq` 就能出 p50/p95/p99。這是一切後續優化的前提 —— **沒有它,後面每一條
改動都是盲改**。

---

### F-11 【high / quant-gap】沒有 runtime kill switch:盤中要停下單只能重啟 server

**位置** `factory.py:101-105` + `safety.py:16-20`
```python
safety = SafetyConfig(
    order_enabled=(_getenv("CAPITAL_ORDER_ENABLED") or "").strip().lower() == "true",
    max_qty=..., max_amount=...,
)
```
```python
@dataclass(frozen=True)
class SafetyConfig:
    order_enabled: bool = False
```

`SafetyConfig` 是 **frozen**、在 `get_capital()`(進程啟動時)建一次,`CapitalClient`
把它存進 `self._safety` 後**沒有任何 runtime 修改路徑**(grep `_safety` 只有讀)。

**影響**:程式跑飛了、策略出錯、市場異常時,唯一的停止手段是 `Ctrl+C` 整台 server
—— 而 server 的 graceful 關機預算是 **83 秒**(`shutdown_budget.run_grace_secs()`)。
對一個下實單的系統,「緊急停止要 83 秒」是不可接受的。

**修法**:`SafetyConfig` 保持 frozen(它是純值),但 client 持有的是
`self._safety: SafetyConfig` 這個**可替換的欄位** + 一支
`POST /api/capital/safety/halt`(以及 `resume`)。halt 只設旗標,不碰 COM —— 之後
每筆 `check_master` 立刻擋下,審計照記 `blocked: "halted"`。
前端在閃電梯上給一顆紅色大鈕。十幾行的改動,是這個區塊 CP 值最高的一條。

---

### F-12 【high / quant-gap】風控只有「單筆張數 / 單筆名目金額」

**位置** `safety.py` 全檔。五個閘的實際內容:
```python
def _check_qty_amount(price, qty, cfg, *, multiplier) -> GateResult:
    if qty <= 0: ...
    if cfg.max_qty is not None and qty > cfg.max_qty: ...
    if cfg.max_amount is not None:
        est = price * qty * multiplier
        if est > cfg.max_amount: ...
```
而且 CLAUDE.md 記載 `CAPITAL_MAX_QTY` / `CAPITAL_MAX_AMOUNT`「未設/0 = 不限
(user 拍板)」—— 也就是**預設是全開的**。

**缺的東西**(量化系統的標準前置風控):
- 速率限制:每秒 / 每分鐘最多幾筆(防程式跑飛、防閃電梯連點);
- 累計曝險:單一標的上限、總部位名目上限(現在每筆單獨過閘,連下 10 筆各過各的);
- 日內停損:當日已實現 + 未實現虧損超過 X 就自動 halt;
- 價格合理性帶:除了個股期的 tick 閘(`_require_legal_tick`),**現股限價沒有任何
  「離現價多遠」的檢查** —— 手滑打成 100 元變 1000 元,只要過得了金額閘就送出去;
- 反向單防護:同標的同時掛多空。

現有的 `_close_dup_reason`(`client.py:1122-1142`)是唯一一個「跨筆」的防護,
但它只管平倉、只有 10 秒窗、只比 in-flight key + 同向活躍委託。

**修法**:新增 `capital/risk.py`(純函式,stdlib,與 safety.py 同款可測性),
輸入 =(request, 當前 store 部位, 最近 N 秒送單紀錄, 現價)。掛在 `_execute_write`
的 gate 之後。這是新功能不是優化,要走 `/feat` + grilling。

---

### F-13 【medium / quant-gap】`degraded`(回報主機斷線)仍放行送單 —— 盲送

**位置** `client.py:880-883`
```python
# degraded(回報斷線)放行:送單通道獨立可用,且刪單/平倉是降風險操作
if self._status not in ("ok", "degraded") or self._loop is None:
```
搭配 `_handle_reply_disconnect`(`client.py:455-462`)—— 斷線後不自動重連、不 clear store。

**影響**:回報斷線期間送出的單**永遠不會進 `store._orders`**(它只由 OnNewData 填),
於是:委託面板看不到、改價 / 刪單的 `_routing` 查不到 `market_of`(寬鬆放行)、
`remaining_shares` 回 None(金額閘跳過)、`_close_dup_reason` 掃不到同向活躍委託
(防重送整層失效)。使用者面對的是「我剛送的單不見了,再送一次?」

放行的理由(降風險操作要能做)是對的,但**沒有把「這張單你看不到」這件事告訴使用者**。

**修法**:degraded 下送單成功時,把 `OrderResult` 標一個 `visible: false` / 或
client 自己在 store 建一筆 `source="local"` 的**佔位委託列**(回報恢復後由真回報覆蓋)。
這會碰到 store 的「聚合非冪等」註記(`store.py:10-12`),要小心設計。

---

### F-14 【medium】後置審計擋在 HTTP 回應之前,同樣吃共享池

**位置** `client.py:917`
```python
result = OrderResult(ok=ok, code=code, message=..., seq_no=...)
await self._audit_after(action, req, result)     # ← 又一次 to_thread + 檔案 IO
if not ok:
    raise BrokerRejectedError(...)
return result
```

單已經送出去了,結果也拿到了,但使用者還要再等一次 `to_thread` + 開檔關檔
(p50 0.38 ms,池滿時無上界)才看到回應。與 F-01 同根因,但影響性質不同:
前置擋的是「單送不出去」,後置擋的是「使用者不知道送出了沒」—— 而
「不知道送出了沒」正是 `client.py:85-87` 註解裡寫的「最容易誘發重送」。

**修法**:F-01 / F-05 落地後(inline + persistent handle),這一段變成 0.35 ms,問題自解。

---

### F-15 【medium】event loop 與全部 TC4 tick fanout 共用,送單 request 的排隊延遲零量測

**證據**:`copycat/server/` 下 21 個 `call_soon_threadsafe` 呼叫點(stock / index /
futures / corr / engine),全部把 TC4 tick 丟回**同一條** event loop 處理
(`stock_engine.py:1150`、`index_engine.py:420`、`futures_engine.py:565`、
`corr_engine.py:262`、`engine.py:365`)。個股自選上限 150 檔(CLAUDE.md §4),
開盤每秒數百筆 tick。

送單的 HTTP request 要在**同一條 loop 上**排隊:`ws_stock` 的 relay、
`_handle_quote` 的逐筆處理、`_flush_ticks` 的 0.1 s 打包、8 條 WS 的 fanout
(`WsBroadcaster.publish` 對每個 client 做 `put_nowait`)。

**這是整條鏈裡唯一一段「規模由市場決定、不由使用者決定」的延遲**,而且完全沒有量測。

**修法**:先量。一個 loop lag probe(見 §6)幾行就好。量到 p95 > 5 ms 才談分離
(分離的手段:把 capital route 放到獨立進程 / 獨立 loop —— 代價很大,不要先做)。

---

### F-16 【medium】`/api/capital/positions` 每列都跑 `stock_code_of` 反查(含 `stat()`)

**位置** `capital_api.py:286-291`
```python
"positions": [
    {**dataclasses.asdict(p), "code": stock_code_of(p.market, p.stock_no)}
    for p in client.store.positions()
]
```
`stock_code_of`(`mapping.py:109-136`)→ `exchange_product_of`(regex)→
`lookup_product` → `_product_index` → **`path.stat()` 每次**(`stkfut_map.py:148`)。

實測 `stat()` p50 **0.004 ms**、p95 0.006 ms。M=50 列 → 0.2 ms。
每 15 秒 + 每筆成交 debounce 一次。

**判定:目前不是問題,但要知道它在那裡。** `orders` / `fills` 兩支也各自對每列跑
`_fill_code` → 同一條路;N=1000 的 orders 就是 1000 次 stat = 4 ms。
**F-06 的 O(1) 化不解這一條** —— 這是全列輸出的 REST,本來就要每列一次。

**修法(若 F-10 量出來真的重要)**:在 route 內對同一次請求做 memo
(`{stock_no: code}` 本地 dict)—— 同一檔的多種類部位共用一次反查。
**不要動 `stkfut_map` 的 stat 簽章 cache** —— 它是 A4 刻意設計的(CLI 在另一個
process 更新對映檔時,跑著的 server 要能看到新表),拿掉會讓新上市個股期送單被拒。

---

### F-17 【low-medium】前端 mutation 沒有 timeout / AbortController,按鈕可轉 10 秒

**位置** `frontend/src/hooks/useCapital.ts:102-114, 221-230`
```python
const res = await fetch(url, init);      # 無 signal、無 timeout
```
後端 `_WRITE_TIMEOUT_S = 10.0`。使用者按下市價鈕之後,最壞會看到 10 秒的轉圈,
中間沒有任何「已送出,等待券商回應」的階段提示。而 `settleFlashSend` 的斷路器
(連 3 敗)在這 10 秒內是沒有輸入的。

**修法**:mutation 加 AbortController + 一個 ~1.5 s 的「已送出,等待回應」中間態
(不是取消,只是換文案)。零後端改動。
⚠ **不可以真的 abort** —— `_execute_write` 的 `asyncio.CancelledError` 分支
(`client.py:899-902`)明文寫著「單可能已出手」,前端主動取消只會製造更多
「結果未知」。

---

### F-18 【low-medium】看盤日常走 vite preview proxy,送單多一跳 Node 轉送

**證據**:CLAUDE.md §1「看盤日常(prod build)= `npm run preview`(port 4173;
proxy 沿用 dev 的 /api + /ws → 8721)」。

也就是說 prod 使用下單時,`POST /api/capital/order/stock` 走
`瀏覽器 → Node(vite preview)→ uvicorn`。**未量測**,但 localhost 上一跳 Node
HTTP proxy 推測 0.2–1 ms,而且 Node 進程也可能被 GC / 其他事情卡住。

**修法**:給 FastAPI 掛 `StaticFiles` 直接服 `frontend/dist`,單一 origin、零 proxy。
這同時消掉 CORS 設定(`FRONTEND_ORIGIN`)。代價:改部署慣例(CLAUDE.md §1 要改)。
優先序不高,但在「延遲最敏感」的框架下該量一次再決定。

---

### F-19 【low】`_note_price_type` 在回應前跑交易日曆推算

**位置** `client.py:955-976` → `_trade_ymd`(`client.py:141-156`)→
`cal.next_trading_day` / `cal.last_trading_day`。

送單成功後、`return result` 之前,在 event loop 上跑一次日曆推算(最多 60 天迴圈,
有保險絲 RuntimeError)。這是**送出之後**的事,不影響送單延遲,但它影響
「使用者看到回應」的時間。未量測,推測 < 0.05 ms(`TradingCalendar` 是純集合查詢)。
**判定:不要動**,列出來只為完整性。

---

### F-20 【low】`logging` 的 tee 每行同步 flush 到檔案 + console

**位置** `server/__main__.py:83-90`
```python
def write(self, s: str) -> int:
    if self._sink is not None:
        self._sink.write(s); self._sink.flush()     # 每行 flush
    return self._stream.write(s)                     # ← 真 console
```
送單鏈上的 log:`_handle_reply` 每筆一行 INFO、`_log_chain_stage` 每段一行、
`_execute_write` 的 warning、uvicorn 的 access log(每個 HTTP request 一行,
**包含送單 request,在 event loop 上**)。

**實測**(sink = 檔案 + stream = `nul`):`logger.info(...)` p50 **0.0136 ms**、
p95 0.0252 ms。換 `QueueHandler` 只降到 0.0081 ms。
**判定:以檔案那半來說不是問題。** 真 console(PowerShell 視窗、有 scrollback)的
`write` 成本**未量測**,那才是可能的黑洞。

**修法:先量再說。** 量法見 §6。若 console 真的貴,`logging.handlers.QueueHandler`
+ `QueueListener` 是 stdlib 的標準解(把 IO 移到背景執行緒),但 `_Tee` 的
「crash 當下已落盤」設計意圖會被弱化 —— 這是取捨,不是純勝。

---

## 4. 工具選型建議與取捨

| 工具 | 用在哪 | 解決什麼 / 預期收益 | 代價 | 結論 |
|---|---|---|---|---|
| `concurrent.futures.ThreadPoolExecutor(max_workers=1)` 專用審計池 | `client._audit*` | 解掉 F-01 的無上界排隊;p50 不變、**尾巴有界** | stdlib,零相依;關機要 shutdown(進關機預算) | **建議導入** |
| persistent file handle + `os.fsync` | `server/audit.py` | 0.25 ms → 0.34 ms **但真 durable**;或不 fsync 則 0.004 ms(62x) | 要管日界換檔 + 關機 close;fsync 尾巴受磁碟/防毒影響 | **建議導入** |
| `time.perf_counter_ns()` 分段時戳寫進審計 | `client._execute_write` | 解掉 F-10;讓後續每一條優化可驗證 | stdlib;審計行變大(~100 bytes) | **建議導入(最優先)** |
| `py-spy`(**已裝**) | prod server 盤中取樣 | 真實 CPU 分佈,含 capital-com thread | 已在 venv;`--threads` 需要權限 | **建議用** |
| `msgspec` 或手寫 `to_dict()` | `capital_api` 三支 REST | 取代 `dataclasses.asdict`(N=1000 佔 7.2 ms) | ⚠ 碰 `unit` / `avg_source` / `today_qty` 三條跨檔契約;msgspec 是新相依,與 stdlib-only 哲學衝突 | **有條件導入**:先做手寫 `to_dict()`(零相依)+ 砍 `raw`,量完再談 msgspec |
| `orjson` | REST response 編碼 | JSON 編碼加速 3–5x | 新相依 | **不建議**:實測瓶頸在 `asdict` 反射(7.2 ms)不在編碼(json.dumps 只 0.0024 ms/筆) |
| `uvloop` | event loop | — | **Windows 不支援** | **不可行** |
| `winloop`(uvloop 的 Windows port) | event loop | 推測降低 call_soon_threadsafe / selector 開銷 | 與 uvicorn Proactor 假定的相容性未知;TC4/COM 混用下風險高;收益未量 | **不建議(現階段)**:先量 loop lag(F-15),量出來才談 |
| `numpy` / `polars` / `numba` / `pyarrow` | — | — | — | **明確不建議**:這個區塊零數值批次運算。全是 dict/字串/dataclass 操作,向量化無從下手 |
| `prometheus_client` | 延遲指標 | 標準指標格式 | 新相依 + HTTP endpoint;本機單人用不需要 | **不建議**:用 stdlib ring buffer(1024 筆)+ `/api/capital/metrics` 回 p50/p95/p99 即可 |
| `aiofiles` | 審計 async 寫入 | — | 內部也是丟 thread pool,不解 F-01;多一層抽象 | **不建議** |
| `logging.handlers.QueueHandler/QueueListener` | prod log | 把 log IO 移出熱路徑 | 弱化 `_Tee` 的「crash 當下已落盤」設計 | **有條件**:先量真 console 成本(F-20) |
| `contextvars` | 跨段傳 client_order_id | 讓分段時戳 / 冪等鍵不用穿參數 | stdlib | **建議(搭配 F-09/F-10)** |

---

## 5. 改動會碰到的跨檔契約(CLAUDE.md §4,必須兩邊同動)

| 契約 | 誰會碰到 | 同動要求 |
|---|---|---|
| **`OrderRecord.unit` / `FillRecord.unit` 字面值(張/口/股)** | F-08(換序列化)、任何 store 重寫 | 產生點 `store.py::_lot_unit` 唯一一份;讀者 = 前端 `ladder-lots.ts`(`unit === "股"` 排零股)+ `fill-marks.ts`(`excludeUnit`)+ **後端 `capital_api.py::_fill_code`**(`unit == "口"` 當期貨判準代理)。改字面值 = 個股期反查靜默死。`tests/capital/test_store.py` 有 lock |
| **`avg_source` + `today_qty`** | F-07(store 快照化)、F-08(序列化) | 產生點 `client._on_profit_complete`(broker)/ `store._apply_fill_locked`(fill)/ `store._with_today_qty_locked`;讀者 = 前端 `PriceLadder.tsx` + `position-summary.ts` → `ladder-position.ts::positionEcon`。少送 `avg_source` → 前端當 fill 多加一次買費;少送 `today_qty` → 當沖稅減半靜默消失。`tests/capital/test_models.py::test_avg_source_parity_with_frontend` 直讀 `types.ts::AVG_SOURCES` |
| **`PositionKind ⊆ TradeKind` / `daytrade_sell`** | F-12(新增風控)、F-13(佔位委託列) | `tests/capital/test_models.py::test_position_kind_subset_of_trade_kind` + `test_close.py::test_close_kind_label_parity_with_frontend` |
| **`_STOCK_FUTURE_UNITS`(std 2000 / mini 100)** | 任何動 `_stkfut_gates` 的改動 | 後端 `capital_api.py:137` ↔ 前端 `lib/stkfut.ts:74` 鏡像 |
| **API error shape `{"detail": {"error": "<code>"}}`** | F-11(新增 halt 錯誤碼)、F-09(新增 timeout 回應欄) | 後端 `capital_api.py::_CAPITAL_ERROR_MAP` + `_gate_blocked` ↔ 前端 `lib/api-error.ts` + `useCapital.ts::parseCapitalError`(ORDER_BLOCKED 的 `:reason` 後綴 + BROKER_REJECTED 的 `:err_code`)+ `lib/trade-text.ts` |
| **關機預算三方同源(`COM_JOIN_TIMEOUT_SECS` 83 s 預算)** | F-01(新增 audit executor,關機要 shutdown) | 產生點 `server/shutdown_budget.py::run_grace_secs()`;讀者 = `run.ps1` / `__main__.py` / `app.py` lifespan。**改 lane 形狀 = 改契約**,要同步改 `TC4_LANE_DEPTH`;`tests/server/test_shutdown_budget.py` 釘住(含 run.ps1 字面 parity) |
| **`_lot_unit` / `_FILL_KIND` / `_CLOSE_MAP` 三張表** | 任何「優化」store 的重寫 | 這三張是安全邊界不是效能路徑,重寫 store 時逐字保留 |

---

## 6. 量測方法(要證明這個區塊快或慢,該怎麼量)

### 6.1 立刻可做(零 prod 風險,離線)
已做,腳本在 scratchpad:
```bash
.venv/Scripts/python scratchpad/bench_capital.py   # audit / stat / queue→loop 往返
.venv/Scripts/python scratchpad/bench_store.py     # orders() / asdict / apply_reply / set_positions
.venv/Scripts/python scratchpad/bench_audit2.py    # open-close vs persistent vs fsync
.venv/Scripts/python scratchpad/bench_log.py       # logging tee(sink=檔案, stream=nul)
```

### 6.2 最優先:把送單鏈變成可量的(F-10)
在 `_execute_write` 打五個 `time.perf_counter_ns()`,把差值寫進**後置**審計行:
```python
"lat_us": {"gate":…, "audit_pre":…, "enqueue_to_com":…, "com":…, "audit_post":…, "total":…}
```
`com` 那一段要在 COM 執行緒的 `_run` 裡量(`fn()` 前後),隨結果一起回傳。
盤後統計:
```bash
grep '"action": "order"' data/audit/capital-20260913.jsonl \
  | python -c "import sys,json;xs=sorted(json.loads(l)['lat_us']['total'] for l in sys.stdin);
               print('n',len(xs),'p50',xs[len(xs)//2],'p95',xs[int(len(xs)*.95)],'max',xs[-1])"
```

### 6.3 loop lag probe(F-15)
一個常駐 task,零相依:
```python
async def _loop_lag_probe():
    prev = time.perf_counter()
    while True:
        await asyncio.sleep(0.05)
        now = time.perf_counter(); lag_ms = (now - prev - 0.05) * 1000; prev = now
        _LAG_RING.append(lag_ms)
        if lag_ms > 20: logger.warning("loop lag %.1f ms", lag_ms)
```
把 ring 的 p50/p95/max 掛上 `/api/health`。**開盤 09:00–09:05 這一段的 p95 就是
送單 request 的排隊延遲下界。**

### 6.4 prod 取樣(py-spy 已裝)
```powershell
.venv\Scripts\py-spy top  --pid <uvicorn pid> --threads
.venv\Scripts\py-spy record -o cap-open.svg --pid <pid> --duration 180 --threads --idle
```
重點看三件事:`capital-com` thread 的時間去哪裡(pump vs COM 查詢 vs 閒置)、
MainThread 有多少比例在 `store.orders` / `asdict`、預設 executor 的執行緒有幾條在
TC4 呼叫裡卡著。

### 6.5 executor 佔用(F-01)
改用具名 executor 後直接暴露:
```python
"audit_queue_depth": self._audit_pool._work_queue.qsize()
```
在那之前,py-spy 的 `--threads` 輸出裡數 `ThreadPoolExecutor-0_*` 有幾條不在
`_worker` 的 `get()` 上,就是佔用數。

### 6.6 前端半邊
`PriceLadder` 的 onClick 打 `performance.mark("order:click")`,mutation `onSettled`
打 `performance.mark("order:done")` + `performance.measure`。與 6.2 的後端
`lat_us.total` 相減 = 「瀏覽器 + vite proxy + loop 排隊」那一段(F-15 / F-18 的合計)。

### 6.7 SKCOM 那一段(唯一真的黑盒)
無法離線量。6.2 的 `com` 分段就是它。取得第一批 prod 數字之前,**不要對 COM 呼叫
本身做任何優化假設**。

---

## 7. 這裡不要動(反向結論)

| 位置 | 為什麼不要動 |
|---|---|
| `safety.py` 全檔 | 五個純函式閘合計 < 5 µs。它是安全邊界不是熱路徑;任何「優化」都是在動拒單判準。要加的是**新的閘**(F-12),不是改快現有的 |
| `mapping.py` 的契約碼轉換 / regex / `is_option_contract` 的四層收斂 | 實測含 stat 也只有 ~50 µs。而 `is_option_contract` 的判準(第 4 層結構判別)是為了「個股期上線後整條被送進期權面」那個 P0 設計的,動它就是動送單分流 |
| `stkfut_map._product_index` 的 `stat()` 簽章 cache | 0.004 ms。而且 mtime_ns 簽章是 A4 刻意設計:`refresh-stkfut-map` 是另一個 process 跑的 CLI,拿掉簽章 = 新上市個股期被 `unknown product multiplier` 拒單而對映檔明明已更新 |
| `BalanceCollector` 的欠帳 / 逐筆 deadline / 時間窗 | 這是**正確性**機器不是效能機器(N017 / F1-F7 / review P0 一路打磨出來的)。它解的是「COM 回呼無查詢識別」這個無 token 的固有問題。碰它 = 重開那些坑 |
| `_run` 的 `_cmd_q.get(timeout=0.05)` 這個 50 ms | 不要縮成 busy loop。要縮的是 `_pump_once()` 的工作量與優先權(F-04),不是輪詢頻率。縮 timeout 只是燒 CPU |
| `com.py` 的逐欄 `setattr(order, k, v)` | 8–10 個 COM property put。COM struct 是值型別,「重用模板」的正確性風險遠大於幾十微秒的收益 |
| `close.py` 的 `_CLOSE_MAP` | 4 個 entry 的 dict 查表。它是跨語言 parity 測試釘住的安全表 |
| `store` 的樂觀套用 / 水位(`_snapshot_watermark`)邏輯 | 它已經是「讓部位看起來快」的那個優化本身(F5 / next-time L57)。這裡該做的是把**沒被樂觀套用涵蓋的類別**(期貨 / 選擇權 / 零股)補上,不是改快現有的 |
| `logging` tee 的 per-write flush | 實測(檔案半邊)0.0136 ms,不是問題。真 console 那半未量 —— 先量,不要憑感覺改 |
| `_WRITE_TIMEOUT_S` / `_CLOSE_INFLIGHT_S` / `_PENDING_TIMEOUT_S` 等常數 | 它們不是效能參數,是**結果未知語意**的參數。動它們要有 prod 實測依據 |

---

## 8. 建議的落地順序

1. **F-10 分段時戳 + F-11 runtime halt**(各十幾行,零契約風險)— 沒有量測不要改別的;
   沒有 kill switch 不要繼續下實單。
2. **F-05 + F-01**(persistent handle + fsync + 專用單執行緒 audit 池)— 把送單路徑
   從共享池上拔下來,順手換到真 durable。⚠ 關機預算契約要同動。
3. **F-03 + F-04**(退避不 sleep;寫入優先權 + 回查鏈讓路)— 十行內,消掉
   「送單排在行情後面」這個結構性問題。
4. **F-02**(`return_code_message` 搬進 COM 執行緒)— 修掉跨 apartment 呼叫。
5. **F-06**(`store.order_of(seq_no)` O(1))+ **F-08**(砍 `raw` + 手寫 `to_dict`)—
   把 REST 半邊的 O(N) 拆掉。⚠ 砍 `raw` 是跨檔契約。
6. **F-09 冪等鍵** / **F-12 風控層** / **F-13 degraded 盲送** — 這三條是新功能,
   要走 `/feat` + grilling,不是優化。
7. **F-15 / F-18**(loop lag / proxy 那一跳)— 量完再決定要不要動。

---

## 9. Open questions(查不出來 / 需要 prod 或 user 回答)

1. `SendStockOrder` / `SendFutureOrder` 同步呼叫的實際耗時分佈?(整條鏈唯一的黑盒,
   推測是最大的一段。F-10 落地後第一天就有數字)
2. `pythoncom.PumpWaitingMessages()` 在開盤 `ConnectByID` backlog 重播時的耗時?
   (決定 F-04 的優先權改動值不值得)
3. SKCOM 的 `STOCKORDER` / `FUTUREORDER` 有沒有 user-defined / 自訂單號欄位?
   → 決定 F-09 的冪等鍵能不能做到「可向券商反查」還是只能做本地對帳。
   `docs/research/2026-07-28-skcom-typelib.md` 有 typelib 全表,需要查證。
4. prod 的實際單日委託筆數 N 量級?(決定 F-06 / F-08 的優先序:N~50 時全是雜訊,
   N~1000 時是真的)
5. prod 跑 server 的 console 是什麼?(PowerShell 視窗 / Windows Terminal / 背景無視窗)
   → 決定 F-20 要不要做。
6. `CAPITAL_AUDIT_DIR` 實際落在哪顆磁碟?有沒有被防毒即時掃描 / OneDrive 同步?
   → 決定 F-05 的 fsync 尾巴。
7. 使用者對「緊急停止」的期待是什麼?(全停 / 只停新倉 / 只停某個標的)
   → 決定 F-11 halt 的粒度。
8. 閃電梯鎖定態下的實際連點峰值?→ 決定 F-12 速率限制的門檻。
