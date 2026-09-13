# D1 — 下單:端到端延遲鏈逐段拆解

> 掃描日期 2026-09-13 · 區塊 `copycat/capital/client.py` (1216) / `com.py` (336) /
> `factory.py` (121) / `copycat/server/capital_api.py` (451) / `server/audit.py` (38)
> + prod 真實資料 `data/audit/capital-*.jsonl`(22 檔 1,075 列)與 `logs/*.log`(79 檔 24 MB)。
>
> **基準**:這是一個要下實單的系統。
> **前提**:上一輪 `B10-capital-order.md` 已經把結構問題列完,本輪的工作是**把 98.5% 的黑箱拆開**、
> 把每一段標上實測數字、並回答「改非同步要付什麼代價」。
>
> 所有標 `[實測]` 的數字都是本機或 prod 資料回推,腳本留在同目錄
> (`agg_audit.py` / `agg2.py` / `bench_chain.py` / `bench_route.py` / `bench_tail.py`),可重跑。
> 標 `[推估]` 的是有機制證據但沒有量測的;標 `[黑箱]` 的是這台機器上量不到的。
> 環境:Windows 11 26200 / Python 3.13.13 / 16 core / ProactorEventLoop /
> `asyncio.sleep(0.05)` overshoot p50 **12.31 ms**(抖動地板,所有 ms 級數字要先扣它)。

---

## 0. 一句話結論

**送單這條鏈的本地段合計 p50 ≈ 1.14 ms,而 prod 實測端到端 mean ≈ 89.6 ms —— 98.7% 在
`SendStockOrder` 這一次同步 COM 呼叫裡,而那一段是券商往返,不是這個 codebase。**

所以「把下單改快」在這個系統裡**不是優化 Python**,是三件別的事:

1. **把券商往返從單一 COM 執行緒上解耦**(`bAsyncOrder=1`)—— 但這有一個上一輪沒看到的
   前置條件:現在的幫浦圈**在等命令時不幫浦訊息**,換非同步會憑空多出平均 25 ms / 最壞
   50 ms 的完成事件延遲,把 89.6 ms 變成 ~115 ms。要先把「等命令」與「等 COM 訊息」
   合併成一次等待(`MsgWaitForMultipleObjects`),非同步才是淨勝。
2. **把那 1.14 ms 裡唯一有無上界尾巴的一段(前置審計走共用 executor)拔掉** —— 它的
   p50 只有 0.35 ms,但實測 20 條 worker 佔滿時 `to_thread(noop)` **500 ms 內不會完成**。
3. **把秒解析度的審計時戳換成 `perf_counter_ns` 分段** —— 現況任何段內優化都不可驗證。

反向結論同樣重要:**新單路徑(`submit_stock_order`)已經很乾淨** —— 不碰 `store.orders()`、
不碰檔案以外的 IO、閘 0.5 µs、映射 0.5 µs、日曆 2.6 µs。「預先算好什麼」這個問題的誠實答案是
**沒有值得預算的東西**(可預算的部分合計 < 10 µs = 端到端的 0.011%)。

---

## 1. 現況地圖:逐個 await 點與所在執行緒

```
[瀏覽器 · main thread]
  PriceLadder / StkfutLadder / FuturesLadder  onClick
    → lib/flash-send.ts::flashSource(locked)          純函式
    → useCapital.ts::useCapitalMutation → fetchJson()
         fetch(url, {method:POST, headers, body:JSON.stringify})
         ★ 無 AbortController / 無 timeout / 無 keepalive 提示(useCapital.ts:102-114)
           │
           ▼ localhost TCP
[Node · vite preview 4173]  vite.config.ts:20-23  proxy "/api" → 127.0.0.1:8721
           │                ★ 看盤日常一定經過這一跳(CLAUDE.md §1)
           ▼
[uvicorn · MainThread = 唯一 event loop,與 5 條 TC4 session 的 tick fanout 共用]
  h11 解析 → starlette routing → pydantic 驗形(StockOrderBody)
  capital_api.py:294  capital_order_stock()
    ├ _capital(request)                       app.state dict 取值
    ├ StockOrderRequest(...)                  frozen dataclass
    └ await client.submit_stock_order(req)
        client.py:978 → _execute_write(action, req, gate=check_stock_order(...), com_call=_do)
          ①  gate.allowed?                                       safety.py 純算術
          ②  status in (ok, degraded)?                           屬性讀
          ③  await asyncio.to_thread(self._audit, self._record(...))   ← await 點 1
               ‖  executor 提交 → [ThreadPoolExecutor-0_N] append_audit()
               ‖  mkdir + open(a) + write + flush + close  ★ 無 fsync
               ‖  → call_soon_threadsafe 回跳 → loop 重新排程
          ④  fut = loop.create_future();  self._cmd_q.put((com_call, fut))
          ⑤  await asyncio.wait_for(asyncio.shield(fut), 10.0)          ← await 點 2
               ‖
               ▼  [capital-com thread · CoInitialize STA · 唯一 COM apartment]
               ‖  client.py:808  while True:
               ‖      self._pump_once()          ← pythoncom.PumpWaitingMessages()
               ‖                                    + 3×collector.poll
               ‖                                    + _maybe_query_balance()(可能同步發 COM 查詢)
               ‖                                    + _poll_pending()
               ‖      cmd = self._cmd_q.get(timeout=0.05)   ← 命令在這一行才被取走
               ‖      result = fn()   →  com.py:149 send_stock_order()
               ‖                          sk.STOCKORDER(); 10× setattr(BSTR/short/int)
               ‖                          self._order.SendStockOrder(user_id, 0, order)
               ‖                          ★ bAsyncOrder=0 → 阻塞到券商回應
               ‖      loop.call_soon_threadsafe(_settle, fut, result, exc)
               ▼
          ⑥  self._com.return_code_message(code)   ★ 在 event loop 上跨 apartment 直呼 COM
          ⑦  await self._audit_after(...)                               ← await 點 3(同 ③)
          ⑧  code != 0 → raise BrokerRejectedError → 400
        client.py:987  _note_price_type(result, ...)   _today_ymd + _trade_ymd + store 鎖
    └ dataclasses.asdict(result) → FastAPI JSON 回應
  uvicorn access log(★ 無時間戳,對不上 app logger 的 asctime)
```

**送單路徑共 3 個 await 點**,其中 2 個(③ ⑦)是 `to_thread`,各含一次 executor 提交
+ 一次 `call_soon_threadsafe` 回跳 + 一次 loop 重新排程;1 個(⑤)是跨執行緒 future。

**刪 / 改 / 減 / 平倉**多兩段前置(全在 loop 上、全在 ③ 之前):

| 動作 | 額外前置 | 成本(prod N≈63) |
|---|---|---|
| cancel | `_routing` → `store.market_of(seq)` O(1) 持鎖 | < 5 µs |
| correct_price(sec) | `store.remaining_shares(seq)` O(1) | < 5 µs |
| correct_price(fut) | route `_correct_price_tick_gate` → **`store.orders()` 全表** + `client._fut_multiplier` → **再一次全表** | 2 × 89 µs [實測] |
| close(sec) | `position_for` + `_close_dup_reason` → **`store.orders()` 全表** + `build_close_order` | 89 µs [實測] |
| close(fut) | `_close_tick_gate` + `position_for` + `_close_dup_reason` 全表 + `_multiplier_for_contract` | 89 µs [實測] |

---

## 2. 端到端延遲預算表(可加總)

### 2.1 prod 端到端實測(22 天 / 536 組配對)

審計每筆寫**兩行**:送出前(`result: null`)與拿到結果後(`result: {...}`),兩行的 `ts` 差值
就是 ③ 之後到 ⑦ 之間的全部。時戳只有秒解析度,但兩個時刻的相位對延遲獨立,
所以 `E[floor(t+L)−floor(t)] = E[L]` —— **delta 的平均是 L 平均的不偏估計**。

```
配對 536 組(order 419 / cancel 116 / close 1);orphan 0、未配對 0、late 行 0、timeout 0
delta 直方: {0s: 494, 1s: 39, 2s: 1, 3s: 1, 4s: 1}
Σdelta = 48 s  →  **端到端 mean = 89.6 ms**   [實測]
P(L ≥ 1s) ∈ [0.56%, 7.8%]  ·  單筆最大 ≥ 3 s(觀測到 delta=4s 一筆)
```

| 切面 | n | delta≥1s | mean(不偏) |
|---|---:|---:|---:|
| 全部 | 536 | 7.8% | **89.6 ms** |
| action=order | 419 | 7.2% | 86 ms |
| action=cancel | 116 | 10.3% | 103 ms |
| action=close | 1 | 0% | — |
| market=sec | 533 | 7.9% | 90 ms |
| market=fut | 3 | 0% | —(樣本太少,期貨面零 prod 延遲證據) |
| **result ok=true** | 484 | 7.6% | **81 ms** |
| **result ok=false(拒單)** | 52 | 9.6% | **173 ms** |

> **拒單比成功單慢一倍。** 52 筆拒單裡 40 筆是 `999 網路單交易額度超過限定額度 249萬`。
> 系統對「券商額度」零認知 → 每次都要付一次完整券商往返才知道被拒。

時段切面(這一條**反駁**「loop 忙 → 下單慢」的直覺):

| 時段 | n | delta≥1s | mean |
|---|---:|---:|---:|
| 09:00–09:05 開盤(loop 最忙) | 26 | **0.0%** | 0 ms |
| 09:05–09:30 | 153 | 7.2% | 72 ms |
| 09:30–10:00 | 148 | 5.4% | 54 ms |
| 10:00–11:00 | 134 | 9.0% | 90 ms |
| 11:00–13:30(最清閒) | 70 | **14.3%** | 229 ms |

開盤 26 筆零跨秒(若 p=7.8%,觀察到 0 的機率 ≈ 12%,**不顯著**,只能說「沒有證據顯示開盤更慢」);
但 11:00–13:30 反而最慢,而那一段 loop 最閒。**結論:尾巴在券商端,不在本機 loop。** [實測,樣本小]

### 2.2 逐段預算(加總到 89.6 ms)

| # | 區段 | 位置 | 執行緒 | 成本 | 基準 |
|---|---|---|---|---|---|
| 1 | 瀏覽器 fetch → vite preview proxy → uvicorn | `frontend/vite.config.ts:20-23` | 瀏覽器 + Node | **0.2–1 ms** | [推估] 未量;Node agent keep-alive 未確認 |
| 2 | uvicorn h11 + starlette routing + pydantic 驗形 + 回應編碼 | `capital_api.py:294-307` | event loop | **0.305 ms** p50 / 0.49 p99(框架地板 0.241) | [實測] in-process ASGI,不含 socket |
| 3 | `check_stock_order` 安全閘 | `safety.py:58` | event loop | **0.0005 ms** | [實測] |
| 4 | `_record()`(`datetime.now().astimezone()` 2.5 µs + `asdict(req)` 1.5 µs) | `client.py:327-342` | event loop | **0.0041 ms** | [實測] |
| 5 | **前置審計 `await to_thread(_audit)`** | `client.py:885` → `audit.py:149` | loop→pool→loop | **0.352 ms** p50 / 0.55 p99(池空)<br>**無上界**(池滿) | [實測] hop 0.041 + append_audit 0.225 |
| 6 | `create_future` + `_cmd_q.put`(無界 Queue) | `client.py:886-887` | event loop | < 0.01 ms | [實測估] |
| 7 | COM 執行緒取件(`get(timeout=0.05)`) | `client.py:811` | → capital-com | **0.046 ms** p50 / 0.082 p99<br>命令落在 pump 忙碌段 → 等殘餘(合成 pump=20 ms 時 max 4.5 ms) | [實測] **不是 50 ms 輪詢** |
| 8 | `to_stockorder_fields` + `STOCKORDER()` + 10× setattr(BSTR) | `mapping.py:242` / `com.py:150-153` | capital-com | 0.0005 ms + COM struct 未量 | [實測/黑箱] |
| 9 | **`SendStockOrder(user_id, 0, order)` 同步券商往返** | `com.py:154` | capital-com(全程獨佔) | **≈ 88.5 ms mean(殘差)**<br>7.8% ≥ 1 s;觀測單筆 ≥ 3 s | [黑箱,以殘差法定量] |
| 10 | `call_soon_threadsafe` → `await fut` 恢復 | `client.py:826` → `client.py:891` | capital-com→loop | **0.074 ms** p50 / 0.13 p99(loop 閒)<br>loop 有 13 ms 同步段 → p99 **1.57 ms**;33 ms 段 → max **33 ms** | [實測] |
| 11 | `return_code_message(code)` 跨 apartment 直呼 | `client.py:910` → `com.py:242` | event loop(!) | 未量;有 COM marshaling / 死鎖窗 | [黑箱] |
| 12 | **後置審計 `await _audit_after`** | `client.py:917` | loop→pool→loop | **0.352 ms**(同 #5) | [實測] |
| 13 | `_note_price_type`(`_today_ymd` 0.5 µs + `_trade_ymd` 2.6 µs + store 鎖 prune) | `client.py:955-976` | event loop | **0.0040 ms** | [實測] |
| 14 | `asdict(OrderResult)` + JSON 回應(已含在 #2) | `capital_api.py:307` | event loop | 0.001 ms | [實測] |
| — | **本地段合計(2+3+4+5+6+7+10+12+13)** | | | **≈ 1.14 ms p50** | [實測] |
| — | **殘差 = #9 SendStockOrder** | | | **≈ 88.5 ms = 98.7%** | [實測 − 實測] |
| 15 | (回流方向,同一條 COM 執行緒)成交回報 → 部位落地 | `client.py:478-703` | capital-com | **p50 1,940 ms / p90 4,103 / p99 6,553 / max 6,639**(179 條完整鏈) | [實測 · prod log] |

**對不上的那一格 = #9,而且只有那一格。** #1(proxy)也未量,但它不在審計的兩個時戳之間
—— 它在 pre 行之前,所以**不影響 89.6 ms 的對帳**,只影響「按下去到看到結果」的使用者感知。

### 2.3 回流鏈三段(prod log 實測,179 條完整鏈)

`_log_chain_stage` 每段印「自成交回報到達起 N ms」,`grep "balance 鏈" logs/*.log`:

| 段 | p50 | p90 | p99 | max |
|---|---:|---:|---:|---:|
| 成交回報 → 庫存段收齊(含 0.5 s debounce + `GetRealBalanceReport` 往返) | 1,061 ms | 3,249 | 5,495 | 5,572 |
| 庫存 → 損益段(`GetProfitLossGWReport` 往返) | 576 ms | 743 | 1,007 | 2,122 |
| 損益 → 期貨段(`GetOpenInterestGW` 往返) | 310 ms | 325 | 593 | 628 |
| **成交 → 部位落地(端到端)** | **1,940 ms** | **4,103** | **6,553** | **6,639** |

**回流比送出慢 20 倍**,而且三段串行、全在同一條 COM 執行緒上、每筆成交觸發一次。
使用者感知的「下單後倉位很慢」在這裡,不在送單。

---

## 3. 三個被問到的機制,逐一查證

### 3.1 `_cmd_q.get(timeout=0.05)` 是不是固定成本?**不是。**

`queue.Queue.get(timeout)` 底層是 `threading.Condition.wait(timeout)` —— `put()` 會
`notify()`,阻塞中的 consumer **立刻**被喚醒。50 ms 只是「佇列空時最長睡多久」,不是輪詢週期。

[實測] `bench_chain.py::queue_pickup`,producer 以隨機相位投遞、consumer 照 `_run` 的
`pump(); get(0.05)` 結構跑:

| consumer 每圈 `_pump_once()` 忙碌 | 取件延遲 p50 | p90 | p99 | max |
|---|---:|---:|---:|---:|
| 0 ms(閒置) | 46.2 µs | 55.9 | 81.8 | 87.4 |
| 1 ms | 46.1 µs | 55.8 | 78.6 | 101.8 |
| 5 ms | 47.0 µs | 56.9 | 71.0 | 95.0 |
| 20 ms | 46.6 µs | 56.3 | **1,451 µs** | **4,466 µs** |

**一個命令最壞要等多久才被取走 = 它落進 `_pump_once()` 的那一刻起、該次 pump 的殘餘時間。**
上界 = `_pump_once()` 的最大耗時,不是 50 ms。而 `_pump_once()` 的最大耗時有三個來源:
`com.pump()` 把**所有**排隊 COM 事件 inline 跑完(開盤 `SKReplyLib_ConnectByID` 重播當日
backlog 可能是數百則)、`_maybe_query_balance()` 可能同步發一次 COM 查詢、以及例外分支的
`time.sleep(1.0)`(`client.py:793`)—— **那一條把 46 µs 放大 20,000 倍**。

### 3.2 `bAsyncOrder=0` 的實際代價,以及非同步要動哪些地方

**查證結果(本機 typelib,不是記憶)** —— `.venv/Lib/site-packages/comtypes/gen/_75AAD71C_*.py`:

```
_ISKOrderLibEvents._disp_methods_ 含:
  OnAsyncOrder(nThreaID, nCode, bstrMessage)                       ← 國內證券/期權
  OnAsyncOrderGW(nThreaID, nCode, bstrMessage)                     ← GW 通道
  OnAsyncOrderOLID(nThreaID, nCode, bstrMessage, bstrOrderLinkedID)← 只服務 OLID 家族
```

**兩個關鍵事實**:

1. **非同步回報拿得到** —— `OnAsyncOrder` 存在,關聯 token 是 `nThreadID`(typelib 拼成
   `nThreaID`),依群益慣例 = 非同步 `SendStockOrder` 的回傳值。**回傳語意未在本機證實,
   要 prod 首單驗。**[推估]
2. **`SendStockOrderOLID` / `SendFutureOrderOLID` 不存在**。OLID 家族只有
   `SendOverseaFutureOrderOLID` / `SendForeignStockOrderOLID` / `SGXOverSeaFutureOrderOLID` /
   `OverSeaCancelOrderBySeqNoOLID` 等**海外 / 複委託**方法。
   並且 `STOCKORDER` 只有 14 欄:
   ```
   bstrFullAccount bstrStockNo sPrime sPeriod sFlag sBuySell bstrPrice
   bstrOrderType bstrSeqNo bstrBookNo nQty nTradeType nSpecialTradeType nUnitQty
   ```
   `bstrSeqNo` / `bstrBookNo` 是券商配發(刪改用),**沒有任何 user-defined 欄位**。
   → **B10 open question 3 定案:國內單無法攜帶自訂單號,冪等鍵只能做本地對帳,
   不可能做到「向券商反查」。** 這改變 F-09 的設計空間。

**同步的實際代價(定量)**:`SendStockOrder` 期間 COM 執行緒完全不能做別的事 ——
不能 pump 回報、不能發回查、不能取下一個寫入命令。prod 實測的同時在途深度:

```
in-flight 深度直方(以審計列為樣本):{0:511, 1:524, 2:19, 3:10, 4:5, 5:2, 6:1}
22 天內「同時在途 ≥2」共 25 次(≈1.1 次/交易日),最深 6
```

**head-of-line 的 prod 直接證據**(`capital-20260821.jsonl`):
```
11:07:57 order 2615 PRE      ← A 入列
11:07:59 order 2615 PRE      ← B 入列(A 還沒回)
11:08:00 order 2615 POST     ← A 回(3 s)
11:08:00 order 2615 POST     ← B 回(1 s,實際等 A 做完才開始)
```
以及 `capital-20260825.jsonl` 10:44:52 同一秒 6 筆刪單入列、4 筆同秒回、2 筆跨秒回。

**改非同步要動的地方(以及一個上一輪沒看到的陷阱)**:

| 要動 | 內容 |
|---|---|
| `com.py:149-168` | 四個寫入方法 `bAsyncOrder` 0 → 1;回傳改成 `(thread_id, rc)` |
| `com.py:291` `_OrderEvents` | 新增 `OnAsyncOrder(nThreaID, nCode, bstrMessage)` sink(comtypes 對未實作事件**靜默忽略**,不掛就永遠收不到,而且沒有錯誤訊號) |
| `client.py:159-168` `_Cmd` | 從 `(fn, fut)` 變成 `(fn, fut, thread_id_holder)`;`_run` 取得 thread_id 後**不 settle**,登記進 `_pending_async[thread_id] = fut` |
| `client.py:865-922` `_execute_write` | ⑤ 的 future 由 `OnAsyncOrder` 解;逾時語意不變(shield 照留) |
| **`client.py:808-813` 幫浦圈** | **★ 前置條件,見下** |
| `client.py:373 / 910` | `return_code_message` 一併搬進 COM 執行緒(順手解 F-02) |

**★ 陷阱:換非同步會憑空多出平均 25 ms** —— `_cmd_q.get(timeout=0.05)` 阻塞在 condition
variable 上,**期間不幫浦 STA 訊息佇列**。SKCOM 的事件確定需要幫浦(`com.get_user_accounts`
自己就寫成 `while: pump(); sleep(0.05)` 來收 `OnAccount`)。所以:

- **今天**:`OnNewData` / `OnRealBalanceReport` / `OnProfitLossGWReport` / `OnOpenInterest`
  **每一則**最壞多等 50 ms、平均 ~25 ms 才被 dispatch(佇列空時)。[推估,機制證據明確]
  這一條對回流鏈是 25 ms / 1,940 ms = 1.3%,無感;
- **換非同步後**:`OnAsyncOrder` 走同一條路 → **送單完成事件多等平均 25 ms**,
  89.6 ms 變 ~115 ms。**單筆下單會變慢**,只有連續送單(深度 ≥2,22 天 25 次)才變快。

**正解**:先把兩個等待源合併成一次等待 —— `MsgWaitForMultipleObjects(1, [cmd_event],
FALSE, timeout, QS_ALLINPUT)`,命令到達與 COM 訊息到達都立刻醒。這是 STA 的標準寫法,
pywin32 已在相依裡(`win32event`)。**做完這一步,同步版也會受益**(回報延遲 −25 ms),
而且它是非同步版的**前置條件**,不是選配。

### 3.3 loop 忙的時候,送單協程要排在多少個已就緒 callback 之後?

**答案不是「N 個 callback」,而是「當前正在跑的那一個同步段的殘餘」。**
asyncio 一輪把 `_ready` 整批 drain;`call_soon_threadsafe` 追加到同一個 deque,
所以新來的 callback 通常在**同一輪或下一輪**就跑到。真正的等待是不可中斷的同步段。

[實測] `bench_route.py`,背景 task 週期性佔住 loop:

| loop 上的同步段 | COM 結果回跳延遲 p50 | p90 | p99 | max |
|---|---:|---:|---:|---:|
| 閒 | 73.3 µs | 95.6 | 132.7 | 202.5 |
| 每輪 13 ms(≈ corr engine 每秒) | 72.8 µs | 98.4 | **1,566 µs** | **3,099 µs** |
| 每輪 33 ms(≈ group-state 每 60 s) | 75.3 µs | 118.6 | **23,091 µs** | **33,080 µs** |

**期望貢獻的算術**:corr 13 ms/1,000 ms → 命中率 1.3%、條件期望 6.5 ms → 貢獻 **0.085 ms**;
group-state 33 ms/60,000 ms → 命中率 0.055%、條件期望 16.5 ms → 貢獻 **0.009 ms**。
**合計 ≈ 0.1 ms = 端到端的 0.11%。**

這個數字對「送單 vs 行情爭 loop」這個直覺給出一個明確的量級答案:**現在不值得為它做
進程分離**。它變成問題的門檻是「loop 上出現一個 > 100 ms 的同步段」,而 prod 目前最大
已知同步段是 group-state 的 33 ms。

---

## 4. Findings

> `on_hot_path` = 是否在「按下去 → 送出」那條路徑上。

### D1-01 【critical】非同步化的前置條件缺席:等命令與等 COM 訊息是兩個互斥的等待

**位置** `client.py:808-813`
```python
while True:
    self._pump_once()                     # ← 只有這一行幫浦 STA 訊息
    try:
        cmd = self._cmd_q.get(timeout=0.05)   # ← 這 50 ms 完全不幫浦
    except queue.Empty:
        continue
```
`queue.Queue.get` 阻塞在 `threading.Condition`(Windows 上是核心 semaphore 等待),
**不是 message pump**。SKCOM 事件需要幫浦(`com.get_user_accounts` 的
`while: pump(); sleep(0.05)` 就是證據)。

**影響(今天)**:每一則群益回報平均多等 ~25 ms、最壞 50 ms 才被 dispatch。[推估]
**影響(改非同步後)**:`OnAsyncOrder` 走同一條路 → 送單 mean 從 89.6 ms 變 ~115 ms,
**非同步變成淨負**。
**修法**:`win32event.MsgWaitForMultipleObjects([cmd_event], False, 50, QS_ALLINPUT)`,
命令用 `win32event.SetEvent` 通知。pywin32 已在 `[capital]` extras。

---

### D1-02 【critical】`SendStockOrder` 佔 98.7%,而且它的變異全部不可觀測

**位置** `com.py:154`(`send_stock_order`)、`com.py:165-167`(期權/期貨)
**證據** 本地段實測 1.14 ms p50 vs prod 端到端 mean 89.6 ms(536 組配對)。
**分布**:7.8% ≥ 1 s、觀測到單筆 ≥ 3 s、拒單 mean 173 ms vs 成功 81 ms。
**判定**:這是**券商往返**,不是這個 codebase 的程式碼。任何「優化 Python」的提案在這裡
天花板是 1.14 ms(1.3%)。能動的只有兩件:(a) 不要讓它佔住唯一的 COM 執行緒(D1-01 + 非同步);
(b) 不要在同步呼叫之外再加無上界排隊(D1-04)。
**on_hot_path** 是。

---

### D1-03 【high】國內單無法攜帶自訂單號 —— 冪等鍵設計空間被 typelib 收窄

**證據** `.venv/Lib/site-packages/comtypes/gen/_75AAD71C_*.py`:
`STOCKORDER._fields_` 共 14 欄,無 user-defined;`FUTUREORDER._fields_` 36 欄,
`bstrOrderSign` / `bstrCIDTandem` 是組合單/停損用途,非自由文字。
OLID 家族(`bstrOrderLinkedID`)**只有海外/複委託方法**:`SendOverseaFutureOrderOLID`、
`SendForeignStockOrderOLID`、`SGXOverSeaFutureOrderOLID`、`OverSeaCancelOrderBySeqNoOLID`…
**沒有** `SendStockOrderOLID` / `SendFutureOrderOLID`。

**影響**:B10 F-09 的修法 2(「塞進 user-defined 欄位供 timeout 後反查」)**不可行**。
剩下的只有:本地 `client_order_id` 寫審計 + timeout 後以(標的, 方向, 量, 送出時刻 ±N 秒)
掃 store 做**機率性**對帳。這是設計上的硬天花板,要在 grilling 階段就告訴 user。
**on_hot_path** 否(但決定寫入路徑的合約形狀)。

---

### D1-04 【high】前置審計走共用 executor:實測 20 條 worker 佔滿時 500 ms 內不完成

**位置** `client.py:885`、`audit.py:149`
**實測** `bench_chain.py`:
- `await to_thread(noop)` 池空 p50 **40.6 µs**(executor hop 本身很便宜);
- `await to_thread(append_audit)` 池空 p50 **351.8 µs** / p99 545.9 / max 1,015;
- 用 `loop.run_in_executor(None, event.wait)` 塞滿 20 條 worker 後,
  `asyncio.to_thread(lambda: None)` **500 ms 內未完成**(`default executor max_workers = 20` 已確認)。

同池鄰居包含 TC4 ZMQ REQ(`_REQ_TIMEOUT_MS = 10_000`、`DEFAULT_LOCK_TIMEOUT_SECS = 12`)
與 FinMind EOD(60 s),而且**不可中斷**。

**這是整條送單鏈裡唯一一段延遲沒有上界的**,而且它擋在真錢送出之前,零錯誤訊號
(HTTP 就是一直轉,`_WRITE_TIMEOUT_S` 也管不到它 —— 那個 timeout 在 ⑤,審計在 ③)。
**on_hot_path** 是。

---

### D1-05 【high】`append_audit` 的 225 µs 有 98% 在 open/close,而且沒有 fsync

**位置** `audit.py:149-159`
**實測**(同一顆 SSD,`bench_chain.py`):

| 寫法 | p50 | p90 | p99 | max |
|---|---:|---:|---:|---:|
| 現況 `mkdir + open(a) + write + flush + close` | **224.5 µs** | 286.5 | 353.1 | 622.9 |
| persistent handle(`ab`, buffering=0)只 write | **3.5 µs** | 4.1 | 15.7 | 58.4 |
| persistent handle + `os.fsync` | **295.5 µs** | 340.4 | 491.5 | 591.0 |
| `json.dumps(record)` 本身 | 2.3 µs | 2.4 | 4.0 | 12.2 |
| `_record()`(ts + asdict) | 4.1 µs | 4.2 | 4.3 | 7.7 |

**持久 handle + 真 fsync(295 µs)比現況「開開關關但不 fsync」(225 µs)只貴 70 µs。**
也就是說可以用 0.07 ms 把「作業系統 page cache 級」的稽核換成「真的落盤」——
對一份**錢動了、不可重建、事後要對帳**的檔案,這是白撿的。
**on_hot_path** 是(×2:前置 + 後置)。

---

### D1-06 【high】關機時 `close()` 的終止訊號排在 FIFO 末端 —— 殘留命令會在關機途中送進市場

**位置** `client.py:712-719`
```python
def close(self) -> None:
    self._cmd_q.put(None)          # ← 排在所有既有命令之後
    t.join(timeout=COM_JOIN_TIMEOUT_SECS)   # 5 s
```
`_run` 是 FIFO:`None` 之前的每一個命令都會 `result = fn()` 真的送出去。
`_drain_pending`(`client.py:840-861`)只處理 `None` **之後**殘留的,那時已經來不及。

**情境**:閃電梯連點 → 佇列深 6(prod 實測最深 6)→ 使用者按 Ctrl+C → 前 5 筆照樣進市場,
而 loop 可能已關 → `call_soon_threadsafe` RuntimeError → **結果連審計後置都寫不成**
(只留一行 `logger.error`)。
**修法**:`close()` 先設 `self._draining = True`,`_run` 在取到命令後檢查旗標 →
直接 `_settle(fut, exc=RuntimeError("關機中,命令未執行"))` 不呼叫 `fn()`。
**on_hot_path** 否(關機路徑),但 blast radius = 真錢。

---

### D1-07 【high】逾時命令沒有 TTL —— 而且 22 天 prod 從未觸發,等於這條路徑零驗證

**位置** `client.py:891-898`
逾時後 `fut` 被 `shield` 保護不取消,命令仍在 `_cmd_q`;`_run` 取到就 `fn()`。
**prod 實證**:22 天 536 筆寫入,**timeout 0 筆、`late: true` 審計行 0 筆**。
也就是說 `_on_late_result`(`client.py:357-398`)這整條補償路徑**在 prod 從來沒跑過**,
包含它裡面那次 `return_code_message` 跨 apartment 呼叫。
**判定**:洞真的在,但發生率 < 1/536。**該修的理由是 blast radius 不是機率**,
且修法只要在 `_Cmd` 加一個 `deadline` 欄位、`_run` 取到就比 `time.monotonic()`。
**on_hot_path** 否。

---

### D1-08 【high】拒單比成功單慢一倍,而且 999「額度超過」本地零預檢

**實測** 拒單 n=52 mean **173 ms** vs 成功 n=484 mean **81 ms**。
拒單碼分布:`999` ×40(全是 `網路單交易額度超過限定額度 249萬`)、`1068` ×7
(市價單委託價須為 0)、`400` ×3、`960` ×2。

**2026-09-07 11:54:49–11:55:14 實錄**:連續 5 筆 999,其中兩筆 delta = 2 s 與 **4 s**
(全 22 天最慢的兩筆)。每一筆都付了一次完整券商往返才知道「額度不夠」。
`safety.py` 的 `max_amount` **預設不限**,而且 22 天 prod **零筆 blocked**
(唯三 blocked 行是 2026-07-29 的 `capital_not_ready`)—— 風控層在實務上是 no-op。

**修法**:把「今日已送出名目金額」累加在 client 本地(審計已經有全部素材),
超過 `CAPITAL_DAILY_NOTIONAL` 就在 gate 擋下 → 0.5 µs 取代 173 ms 往返,
而且不佔 COM 執行緒。這是新功能(走 `/feat`),不是優化。
**on_hot_path** 是。

---

### D1-09 【high】整條鏈零分段時戳;審計只有秒解析度,access log 連時戳都沒有

**位置** `client.py:336`(`timespec="seconds"`)、`server/__main__.py:193`(uvicorn 預設 access log)
本報告的 89.6 ms 是用「跨秒機率」反推出來的 —— 這是**能做到的極限**,而且只能給 mean
與「≥1 s 的比例」,**給不出 p50/p90/p99**。

更糟的是 HTTP 層對不上:app logger 有 `%(asctime)s`,但 uvicorn access log 是
`INFO:     127.0.0.1:61918 - "POST /api/capital/order/stock HTTP/1.1" 200 OK` —— **零時戳**。
所以「按下去 → HTTP 到達」與「pre 審計行」之間那一段(含 #1 proxy)永遠對不起來。

**修法(最優先,~20 行)**:`_execute_write` 打 6 個 `time.perf_counter_ns()`
(gate / audit_pre / enqueue / com_in / com_out / audit_post),`com_in`/`com_out` 在
`_run` 的 `fn()` 前後量、隨結果一起回傳,把 µs 差值寫進**後置**審計行的 `lat_us`。
盤後一行 `jq` 就有真 p50/p95/p99。**沒有這個,後面每一條改動都是盲改。**
**on_hot_path** 是(但成本 6 × ~50 ns)。

---

### D1-10 【medium-high】`_pump_once` 例外分支的 `time.sleep(1.0)` 把取件延遲放大 20,000 倍

**位置** `client.py:791-793`
實測正常取件 **46 µs**;例外持續時每圈 sleep 1 s,而 `get()` 在 sleep 之後 → 送單最壞等 1 s。
且此時 `self._status` 仍是 `"ok"`(例外被吞),前置檢查照樣放行。
**修法**(B10 F-03 同):改成 `self._backoff_until = monotonic()+1.0`,下一圈跳過 pump,
`get()` 照跑 —— 退避期間寫入命令仍然 50 ms 內被取走。
**on_hot_path** 是(故障態)。

---

### D1-11 【medium-high】`return_code_message` 在 event loop 上跨 apartment,而且成功路徑也呼叫

**位置** `client.py:910`(成功路徑,**每筆必過**)、`client.py:373`(late 路徑)
`com.py:3-4` 檔頭明文:「所有方法都必須在同一條 CoInitialize 過的執行緒上呼叫」。
`_center` 建在 capital-com thread 的 STA 裡;第 910 行在 event loop 上。
**新增於上一輪的觀察**:如果 comtypes 對這個介面建了 proxy,跨執行緒呼叫需要目標 STA
幫浦 —— 而目標 STA 此刻正**可能卡在下一筆的 `SendStockOrder` 裡**(prod 實測同時在途最深 6)。
機制上這是一個死鎖窗;prod 至今沒炸(推測 `SKCenterLib_GetReturnCodeMessage` 是純查表)。
**修法**:把它包進 `com_call` 閉包,`_ComCall` 回傳型別 `tuple[str,int]` → `tuple[str,int,str]`。
順手在改非同步時一起做(D1-01 的清單裡)。
**on_hot_path** 是。

---

### D1-12 【medium】loop 排隊對送單的期望貢獻只有 0.1 ms —— 不要為它做進程分離

**實測**(§3.3):loop 有 13 ms 同步段時回跳 p99 1.57 ms、33 ms 段時 max 33 ms;
期望貢獻 corr 0.085 ms + group-state 0.009 ms ≈ **0.1 ms = 0.11%**。
prod 時段切面也不支持「開盤更慢」(09:00–09:05 n=26 零跨秒)。
**反向結論:現在不要動 loop 架構。** 這條的價值是給出「什麼時候要動」的門檻 ——
loop 上出現 > 100 ms 的單一同步段時。要監測它,一個 5 行的 loop lag probe 就夠。
**on_hot_path** 是(但判定為非瓶頸)。

---

### D1-13 【medium】回流鏈(成交 → 部位落地)p50 1.94 s / p99 6.55 s,比送單慢 20 倍

**實測** 179 條完整鏈(`grep "balance 鏈" logs/*.log`):見 §2.3。
三段串行 COM 查詢各 p50 ~560 / 576 / 310 ms,外加 0.5 s debounce。
`_apply_fill_locked` 的樂觀套用已經吃掉大部分感知,但 `client.py:438-444` 明列
**零股 / 無券買向 / 選擇權 / 期貨契約碼不明 / 未滿張 / 無價** 六類不套用 —— 那六類就是
完整吃 1.9–6.5 s。
**修法方向**(不是效能是排序):三段串行改成 balance 與 OI **並行**(兩者無依賴,
只有 profit 依賴 balance 的 pending)。省下 310 ms p50 / 593 ms p99。
⚠ 但這會同時發兩個 COM 查詢,可能撞群益 1019「查詢處理中」—— 要先用一天 prod 驗。
**on_hot_path** 否(回流)。

---

### D1-14 【medium】改價 / 平倉路徑重複建全表,但 prod N 讓它不是效能問題

**位置** `capital_api.py:191`、`client.py:1065`、`client.py:1139`
**實測** `store.orders()`:

| N | `orders()` | `+ asdict 全列` |
|---:|---:|---:|
| 20 | 29.7 µs | 92.6 µs |
| **63(prod 上界)** | **89.1 µs** | **288 µs** |
| 200 | 280.7 µs | 890 µs |
| 1000 | 1,447 µs | 4,536 µs |

prod 單日寫入 10–77 筆(22 天直方),server session 最長跨 3 天(`server-20260911-0905.log`
跑到 09-13)→ N 上界 ≈ 200。期貨改價要建兩次全表 = **0.56 ms**,不是 5.3 ms。
**判定**:B10 F-06 該修,但理由是**重複與可讀性**,不是效能。不要用它當優先序理由。
**on_hot_path** 是(改價/平倉),量級可忽略。

---

### D1-15 【medium】送單路徑沒有任何值得預先算的東西(反向結論)

逐項實測:`check_stock_order` 0.5 µs、`to_stockorder_fields` 0.5 µs、
`_today_ymd` 0.5 µs、`_trade_ymd`(交易日曆全鏈)2.6 µs、`_note_price_type` 全段 4.0 µs、
`asdict(OrderResult)` 1.0 µs、pydantic `model_validate_json` 1.4 µs、
body→dataclass 0.8 µs。**合計 < 12 µs = 端到端的 0.013%。**

期貨路徑多的 `product_of`(regex)+ `lookup_product`(含 `path.stat()` 0.004 ms)+
`multiplier_of` + `resolved_contract` + `to_exchange_symbol` 合計 < 50 µs [上一輪實測]。

**「按下去到送出最短」的答案不是快取,是:(a) 把審計的 2 × 0.35 ms 換成 2 × 0.003 ms
(persistent handle,D1-05);(b) 把 to_thread 的排隊風險拔掉(D1-04)。**
`stkfut_map` 的 `stat()` 簽章快取**不要動** —— 那是 CLI 在另一個 process 更新對映檔時,
跑著的 server 要看得到新表的機制,拿掉會讓新上市個股期被拒單。
**on_hot_path** 是。

---

### D1-16 【medium】拒單訊息與回報流互相印證,但系統不做交叉核對

**prod 實錄**(2026-09-07):每一筆 999 拒單,~0.5 s 內都有一則 `OnNewData` 回報
(`Capital reply: seq=2313226448723 stock=6488 status=委託`),seq 是**本方從未見過**的新號。
依 `reply.py:47`(idx3 `order_err`:Y 失敗)與 `store.py:215-218`,這些列會被標成「失敗」
—— 所以委託面板不會出現幽靈活單,這一點是對的。

但:**沒有任何地方把「SendStockOrder 回 999」與「這一則失敗回報」關聯起來**。
`_execute_write` 回傳的 `seq_no=None`,而市場上那張失敗單的 seq 只存在於 store。
對帳時(尤其 timeout 路徑)沒有橋。
**判定**:今天不會出錯(失敗就是失敗),但這是 D1-03 冪等對帳唯一可用的素材,
設計冪等鍵時要把 `order_err` 那一欄接進來。
**on_hot_path** 否。

---

### D1-17 【medium】`_cmd_q` 無上界 + 前端無 timeout/AbortController = 使用者側零反饋 10 秒

**位置** `client.py:212`(`queue.Queue()` 無 maxsize)、`useCapital.ts:102-114`(`fetch` 無 signal)
prod 最深 6,但沒有任何機制擋第 7、第 70 筆。閃電梯鎖定態連點 = 使用者唯一的節流器。
`settleFlashSend` 的連 3 敗斷路器(`lib/flash-send.ts:29-48`)在這 10 秒內**沒有輸入**。
**修法**:`queue.Queue(maxsize=32)` + `put_nowait` 滿了就 `CapitalGateBlockedError("queue_full")`
(有審計、有明確錯誤碼),前端加「已送出,等待券商回應」中間態。
⚠ **前端不可以真的 abort** —— `client.py:899-902` 明文:單可能已出手。
**on_hot_path** 是。

---

### D1-18 【low-medium】uvicorn access log 無時戳,而它是唯一記錄 HTTP 層的地方

**位置** `server/__main__.py:143`(app logger 有 asctime)vs uvicorn 預設 access formatter(無)
prod log 裡 `POST /api/capital/order/stock` 35 筆/日,但一筆都對不上時間軸。
**修法**:`uvicorn.run(..., log_config=...)` 給 access logger 同一個 formatter,或直接關掉
access log 改用 D1-09 的分段時戳(後者更好:access log 在回應**之後**才寫,本來就量不到送單)。
**on_hot_path** 否。

---

### D1-19 【low-medium】看盤日常經 vite preview proxy 多一跳 Node,且完全未量

**位置** `frontend/vite.config.ts:20-23` + CLAUDE.md §1「看盤日常 = `npm run preview`(4173)」
`/api` 走 `瀏覽器 → Node http-proxy → uvicorn`。推估 0.2–1 ms,但 Node 進程也會 GC。
**這一段不在 89.6 ms 之內**(它在 pre 審計行之前),所以它是**純加項**。
**量法**:前端 `performance.mark("order:click")` / `onSettled` 打 mark,減去 D1-09 的
`lat_us.total` = 「瀏覽器 + proxy + loop 排隊」合計。量到 > 2 ms 才談掛 `StaticFiles`。
**on_hot_path** 是(未量)。

---

### D1-20 【low】`_pump_once()` 每圈都在送單命令之前跑 —— 連續送單的每一筆都付一次

**位置** `client.py:808-811`
`while True: _pump_once(); get()` —— burst 中每兩個命令之間插一次完整 `_pump_once()`
(pump + 3×poll + `_maybe_query_balance` + `_poll_pending`)。而 `_maybe_query_balance`
的觸發條件正是「剛剛有成交」(`_mark_balance_dirty(0.5)`)—— **連續下單的第二筆最容易
撞上第一筆成交觸發的回查鏈**。
**實測反證**:22 天裡同時在途 ≥2 只有 25 次,而 08-25 那串 6 筆刪單 1.3 s 內全部收尾
—— 這個成本在 prod 目前是可忽略的。
**修法**(B10 F-04 同,十行內):寫入優先 `get_nowait()`;`_maybe_query_balance` 進門先
`if not self._cmd_q.empty(): return`(回查晚 50 ms 零後果)。
**判定:該做,但不是因為它慢 —— 是因為它讓延遲不可預測。**
**on_hot_path** 是。

---

## 5. 失效模式表(★ = 零錯誤訊號)

| # | 失效模式 | 觸發 | 症狀 | ★ | 現在怎麼發現 |
|---|---|---|---|---|---|
| 1 | 前置審計卡在共用 executor | TC4 半死 → 20 條 worker 全被 10–22 s 的不可中斷呼叫佔住 | 送單按鈕無限轉圈(連 `_WRITE_TIMEOUT_S` 都管不到,那個 timeout 在 ⑤,卡點在 ③) | ★ | **發現不了**。要加具名 pool + `qsize()` 上 `/api/health` |
| 2 | 關機途中殘留命令照送 | 佇列深 ≥2 時 Ctrl+C | 單進了市場,後置審計寫不成(loop 已關)只留一行 `logger.error` | ★ | 只能事後對群益 APP |
| 3 | 逾時命令無 TTL | COM 卡 > 10 s 後恢復 | 10 秒前放棄的單進市場 | 半 | `late: true` 審計行 + WARNING(22 天 0 次,路徑零 prod 驗證) |
| 4 | `_pump_once` 例外持續 → 每圈 sleep 1 s | 群益/TC4 端半死拋 COMError | 送單延遲 1 s,`status` 仍是 `ok` | ★ | `grep "COM 幫浦圈例外"`(有 log,但狀態不降級) |
| 5 | `return_code_message` 跨 apartment marshaling | comtypes 對 `ISKCenterLib` 建 proxy 且 COM 執行緒卡在 `SendStockOrder` | loop 整條凍住 / 死鎖 | ★ | 完全看不到;py-spy `--threads` 才抓得到 |
| 6 | 改非同步後 `OnAsyncOrder` 等幫浦 | 換 `bAsyncOrder=1` 但沒改幫浦圈 | 每筆送單 +25 ms(mean),而且**看起來像是券商變慢** | ★ | 只有 D1-09 的分段時戳分得出來 |
| 7 | `_OrderEvents` 沒掛 `OnAsyncOrder` | 改非同步時漏掛 sink | comtypes 對未實作事件**靜默忽略** → 每筆送單必 timeout 10 s | ★ | 只看到「全部 timeout」,看不出原因 |
| 8 | 券商額度耗盡 | 當日名目累計 > 249 萬 | 每筆都付 173 ms 往返後拒單;閃電梯連點連拒 | 否 | 拒單訊息明確(999)。但**本地零預檢、零累計** |
| 9 | `_cmd_q` 無界堆積 | 前端連點 / 未來程式化下單跑飛 | 佇列愈排愈長,每筆都在 10 s timeout 邊緣,使用者不知道排第幾 | ★ | 無任何佇列深度指標 |
| 10 | 審計未 fsync | 藍屏 / 斷電 | 丟掉最後幾筆 —— 而事故當下那幾筆正是要查的 | ★ | 事後才知道 |
| 11 | 秒解析度時戳 | 一直都是 | 任何延遲改動都不可驗證;p50/p90/p99 拿不到 | ★ | 本報告只能用跨秒機率反推 mean |
| 12 | degraded 下送單 | 回報主機斷線 | 單送得出去,但**永遠不進 store** → 面板看不到、`_close_dup_reason` 防重送整層失效 | ★ | `status=degraded` 有顯示,但「你剛送的單看不到」沒說 |
| 13 | 回流鏈六類不樂觀套用 | 零股 / 無券買向 / 選擇權 / 契約碼不明 / 未滿張 / 無價 | 部位面板慢 1.9–6.5 s | 否 | `client.py:441` 有 INFO 留痕(pr review 加的) |
| 14 | 三段回查串行撞 1019 | 若改成 balance/OI 並行 | 查詢被拒 → 該輪部位整批遺失 | 半 | `logger.warning("GetOpenInterestGW rc=...")` |
| 15 | vite proxy 那一跳 | 一直都是 | 使用者感知延遲多 0.2–1 ms,而所有量測都不含它 | ★ | 完全沒量過 |

---

## 6. 改造順序(每步的量測判準)

> 原則:**先讓它可量 → 再拔無上界的那一段 → 再動 COM 模型**。
> COM 模型是唯一能動那 98.7% 的地方,但它也是唯一會把「已經在跑的下單系統」弄壞的地方。

### 步驟 1 — 分段時戳寫進審計(~20 行,零契約風險)
`_execute_write` 打 6 個 `perf_counter_ns()`;`com_in`/`com_out` 在 `_run` 的 `fn()` 前後量、
隨結果回傳(`_ComCall` 型別 `tuple[str,int]` → `tuple[str,int,int,int]`)。
寫進**後置**審計行的 `lat_us = {gate, audit_pre, enqueue, com, audit_post, total}`。
**判準**:次一交易日盤後
```bash
grep '"action": "order"' data/audit/capital-$(date +%Y%m%d).jsonl | \
  python -c "import sys,json;xs=sorted(json.loads(l)['lat_us']['com'] for l in sys.stdin);\
print('n',len(xs),'p50',xs[len(xs)//2],'p95',xs[int(len(xs)*.95)],'max',xs[-1])"
```
`com` 的 p50 應落在 **60,000–100,000 µs**(與本報告殘差法的 88.5 ms 同量級);
`total − com` 應 < **2,000 µs**。對不上就是本報告的殘差法有誤,**先停下來重看**。
**回滾**:刪掉那 6 行,審計行少一個鍵,零讀者受影響。

### 步驟 2 — runtime halt(kill switch)
`self._safety` 改成可替換欄位 + `POST /api/capital/safety/halt|resume`,halt 只設旗標,
`check_master` 立刻擋、審計記 `blocked: "halted"`。
**判準**:halt 後 `curl -X POST /api/capital/order/stock` 回 403
`{"detail":{"error":"ORDER_BLOCKED","reason":"halted"}}`,且審計有對應 blocked 行;
`resume` 後恢復。**這一步在動 COM 之前必須先有** —— 之後每一步都在動真錢路徑。
**回滾**:route 移除,`_safety` 改回建構時固定。

### 步驟 3 — 審計:persistent handle + fsync + 專用單執行緒 pool
`CapitalClient` 持 per-day append handle(日界換檔 close/open),`_audit()` 走
`fh.write(line); os.fsync(fh.fileno())`;`to_thread` 換成
`run_in_executor(self._audit_pool, ...)`(`max_workers=1`,`thread_name_prefix="capital-audit"`)。
⚠ **`close()` 要 `shutdown(wait=True)` → 進 `shutdown_budget.run_grace_secs()` 契約**
(`tests/server/test_shutdown_budget.py` 釘 run.ps1 字面 parity,要同動)。
**判準**:(a) 步驟 1 的 `audit_pre` p99 從 ~550 µs 降到 **< 400 µs** 且 **max 有界**;
(b) 人為塞爆預設池(把 20 條 worker 用 `curl` 打滿 breadth/daily_bars)後送一筆遠價單,
`audit_pre` 不受影響;(c) `data/audit/capital-*.jsonl` 行數與筆數一致(fsync 不改語意)。
**回滾**:改回 `to_thread(self._audit, ...)`,`audit.py` 不動。
⚠ 落地前先量 `CAPITAL_AUDIT_DIR` 實際磁碟的 fsync p99(防毒 / OneDrive 會爆尾巴)。

### 步驟 4 — 幫浦圈:退避不 sleep + 寫入優先 + 回查讓路
三個十行內改動:例外分支改 `_backoff_until`;每圈先 `get_nowait()`;
`_maybe_query_balance` 進門 `if not self._cmd_q.empty(): return`。
**判準**:(a) `grep "COM 幫浦圈例外" logs/` 出現的那些日子,`lat_us.enqueue` 不再有 ~1,000,000 µs;
(b) 同時在途 ≥2 的那些 burst(prod ≈1.1 次/日),第 2 筆的 `lat_us.enqueue` p95 < 5,000 µs;
(c) 回查鏈 p50 不劣化(仍 ≤ 2,100 ms)。
**回滾**:三處各自獨立,可逐條回退。

### 步驟 5 — 幫浦與命令佇列合併等待(`MsgWaitForMultipleObjects`)
`_cmd_q.put` 旁加 `win32event.SetEvent(self._cmd_evt)`;`_run` 改成
`MsgWaitForMultipleObjects([self._cmd_evt], False, 50, QS_ALLINPUT)` → 醒來先 pump 再 drain 佇列。
**這一步是步驟 6 的前置條件,但它自己就有收益**(回報 dispatch −25 ms mean)。
**判準**:(a) 回流鏈「成交回報 → 庫存段收齊」p50 從 **1,061 ms** 降到 **≤ 1,040 ms**
(0.5 s debounce 不變,省的是 dispatch 相位);(b) `lat_us.enqueue` p50 不劣化(仍 < 100 µs);
(c) 連跑一個完整交易日,`grep "COM 幫浦圈例外"` 為 0、回報筆數與群益 APP 對得上。
**回滾**:回到 `get(timeout=0.05)`,`_cmd_evt` 保留不用。
⚠ 風險最高的一步(動 STA 訊息迴圈)。**必須在非交易時段先跑一整晚**再上盤中。

### 步驟 6 — `bAsyncOrder=1` + `OnAsyncOrder`
`com.py` 四個寫入方法 bAsync 0→1;`_OrderEvents` 掛 `OnAsyncOrder` / `OnAsyncOrderGW`;
`_run` 取得 thread_id 後登記 `_pending_async[tid] = fut` 不 settle;
`return_code_message` 一併搬進 COM 執行緒。
**⚠ 先用 prod 安全首單(遠價 1 張限價 → 群益 APP 核對 → 刪單)確認
「非同步 `SendStockOrder` 的回傳值就是 `nThreadID`」這條慣例** —— 本機 typelib 沒有寫明。
**判準**:(a) `lat_us.com` p50 **不劣化**(步驟 5 做對的話應持平或略降);
(b) burst(同時在途 ≥2)時第 2 筆的 `lat_us.com` 明顯小於第 1 筆 —— 這是非同步唯一的真收益;
(c) 22 天基線的拒單碼分布(999/1068/400/960)在非同步下逐字相同;
(d) `late` 審計行仍為 0。
**回滾**:`bAsyncOrder` 改回 0,sink 留著不會有事(沒有非同步呼叫就不會觸發)。

### 步驟 7 — 當日名目金額累計 + 速率閘(新功能,走 `/feat`)
`capital/risk.py` 純函式:輸入(request, store 部位, 最近 N 秒送單紀錄, 當日已送名目)。
先擋掉 999「額度超過 249 萬」那 40 筆(佔全部拒單 77%)。
**判準**:模擬當日累計逼近上限時,第 N+1 筆在 **< 1 ms** 內被 gate 擋下(審計有 blocked 行),
而不是付 173 ms 往返後吃 999。
**回滾**:閘的上限設 `None` = 不限,退回現行為。

### 步驟 8 — `_cmd_q` 有界 + 前端中間態
`queue.Queue(maxsize=32)` + `put_nowait` 滿了 raise `CapitalGateBlockedError("queue_full")`;
前端 mutation 1.5 s 後換文案「已送出,等待券商回應」(**不 abort**)。
**判準**:壓測 40 連發 → 第 33 筆起回 403 `queue_full` 且有審計行;佇列深度不超過 32。
**回滾**:`maxsize=0`。

### 步驟 9 — 關機終止旗標(D1-06)
`close()` 設 `self._draining = True`;`_run` 取到命令先看旗標 → `_settle(fut, exc=...)` 不 `fn()`。
**判準**:單元測試 — 佇列塞 3 個命令 + `close()`,`FakeCom` 的 `send_stock_order` 呼叫次數 = 0,
三個 future 都以 `RuntimeError` 收尾。**不動 `COM_JOIN_TIMEOUT_SECS`,關機預算契約不變。**
**回滾**:移除旗標。

### 步驟 10 — 回查鏈 balance ‖ OI 並行(選配,先驗 1019)
**判準**:回流鏈 p50 從 **1,940 ms** 降到 **≤ 1,650 ms**(省掉 OI 那 310 ms);
且 `grep "GetOpenInterestGW rc="` 全日為 0(沒撞 1019)。撞到就回滾,不硬幹。
**回滾**:改回串行。

---

## 7. 工具選型

| 工具 | 用在哪 | 為什麼 | 代價 | 結論 |
|---|---|---|---|---|
| `time.perf_counter_ns()` 分段時戳 | `_execute_write` + `_run` | 解掉「一切不可驗證」;本報告的殘差法只能給 mean | stdlib;審計行 +~120 bytes | **建議導入(最優先)** |
| `win32event.MsgWaitForMultipleObjects` | `client._run` | 合併「等命令」與「等 COM 訊息」;非同步化的**前置條件**,自己也省 25 ms | pywin32 已在 `[capital]` extras;動 STA 迴圈,風險最高 | **建議導入(步驟 5,先夜測)** |
| `bAsyncOrder=1` + `OnAsyncOrder` sink | `com.py` + `client.py` | 唯一能動那 98.7% 的槓桿(pipelining) | 沒做步驟 5 就是**淨負**(+25 ms);回傳語意要 prod 首單驗 | **有條件導入(步驟 6,步驟 5 之後)** |
| persistent file handle + `os.fsync` | `server/audit.py` | 225 µs → 295 µs **但真落盤**;或不 fsync 則 3.5 µs(64×) | 日界換檔 + 關機 close 進關機預算契約 | **建議導入** |
| `ThreadPoolExecutor(max_workers=1)` 專用審計池 | `client.__init__` | 解掉唯一無上界的一段(實測 20 worker 佔滿 → 500 ms 不完成) | stdlib;`shutdown(wait=True)` 進關機預算 | **建議導入** |
| `py-spy`(**已裝**) | prod 盤中 `--threads` 取樣 | 唯一能看 `capital-com` thread 時間去向(pump vs COM 查詢 vs 閒置)的工具 | 已在 venv | **建議用** |
| `contextvars` | 跨段傳 `client_order_id` | 分段時戳 + 本地冪等鍵不用穿參數 | stdlib | **建議(搭步驟 1/7)** |
| `orjson` / `msgspec` | 審計 / REST 序列化 | — | 新相依 | **不建議**:`json.dumps(record)` 實測 **2.3 µs** = 端到端的 0.0026%;瓶頸不在編碼 |
| `numpy` / `polars` / `pyarrow` | — | — | — | **明確不建議**:這條鏈零數值批次運算,全是 dict / BSTR / dataclass |
| `uvloop` | event loop | — | Windows 不支援 | **不可行** |
| `winloop` | event loop | 推估降低 `call_soon_threadsafe` 開銷 | 與 Proactor + COM 混用相容性未知 | **不建議**:實測回跳 p50 已是 **74 µs**,總佔比 0.08% |
| `prometheus_client` | 延遲指標 | — | 新相依 + HTTP endpoint | **不建議**:stdlib ring buffer + `/api/capital/metrics` 就夠(本機單人) |
| 顯式 `ORJSONResponse` | capital routes | — | — | **不建議**:FastAPI 0.139 + pydantic 2.13 已走 `dump_json` 的 Rust 快路徑,指定反而退回較慢路徑 |
| `aiofiles` | 審計 async 寫 | — | 內部也是丟 thread pool,不解無上界排隊 | **不建議** |

---

## 8. 這裡不要動(反向結論,附理由)

| 位置 | 為什麼 |
|---|---|
| `safety.py` 五個純函式閘 | 實測 0.5 µs。它是安全邊界不是熱路徑。要加的是**新的閘**(D1-08 的名目累計),不是改快現有的 |
| `mapping.to_stockorder_fields` / `to_futureorder_fields` | 實測 0.5 µs。且 `bstrPrice="0"`(市價)那一行是 prod 實證換來的(2026-08-24 七筆 1068 拒單) |
| `stkfut_map._product_index` 的 `stat()` 簽章快取 | 0.004 ms。拿掉 = CLI 更新對映檔後 server 看不到 → 新上市個股期被 `unknown product multiplier` 拒單 |
| `_cmd_q.get(timeout=0.05)` 的 **50 ms 數值** | 實測取件延遲 46 µs —— 這 50 ms **不是**成本。縮它只是燒 CPU。要改的是**等待的形狀**(步驟 5),不是數值 |
| `_note_price_type` / `store.note_price_type` 的候選日邏輯 | 全段 4.0 µs。它是**誤標防護**不是效能路徑,prune 規則是 review R6/R7/N075 一路打磨出來的 |
| `BalanceCollector` 的欠帳 / deadline / 時間窗 | 正確性機器。它解的是「COM 回呼無查詢識別」這個 API 固有問題。碰它 = 重開那些坑 |
| `com.py` 的逐欄 `setattr` | 10 個 COM property put。COM struct 是值型別,「重用模板」的正確性風險遠大於幾十 µs |
| `store` 的樂觀套用 / 水位 | 它本身就是「讓部位看起來快」的那個優化。該做的是把**沒被涵蓋的六類**補上(D1-13),不是改快現有的 |
| `_WRITE_TIMEOUT_S` / `_CLOSE_INFLIGHT_S` / `_PENDING_TIMEOUT_S` | 不是效能參數,是**結果未知語意**的參數。22 天 prod 零次觸發 → 沒有調整依據 |
| event loop 架構(進程分離 / 獨立 loop) | 實測期望貢獻 **0.1 ms = 0.11%**;prod 時段切面也不支持「開盤更慢」。門檻是「loop 上出現 > 100 ms 同步段」,目前最大 33 ms |
| `dataclasses.asdict` 在 capital 三支 REST | prod N ≤ 63 時 288 µs、N=200 時 890 µs。改寫要碰 `unit` / `avg_source` / `today_qty` 三條跨檔契約,收益不成比例 |

---

## 9. Open questions

1. **非同步 `SendStockOrder` 的回傳值語意** —— 慣例說是 `nThreadID`,本機 typelib 沒寫。
   prod 安全首單(遠價 1 張 → 核對 → 刪)是唯一驗法。**這是步驟 6 的 go/no-go。**
2. `pythoncom.PumpWaitingMessages()` 在開盤 `ConnectByID` backlog 重播時的實際耗時?
   → 決定步驟 4「寫入優先」的收益(現在只有機制推論)。
3. `CAPITAL_AUDIT_DIR` 落在哪顆磁碟、有無防毒即時掃描 / OneDrive 同步?
   → 決定步驟 3 的 fsync 尾巴。
4. 群益「網路單交易額度 249 萬」是**當日累計名目**還是**未平倉名目**?
   → 決定步驟 7 的累計口徑;算錯方向的閘比沒有閘更糟。
5. 使用者對「緊急停止」的期待:全停 / 只停新倉 / 只停某標的?→ 決定步驟 2 的粒度。
6. vite preview proxy 那一跳的實際成本(含 Node agent 是否 keep-alive)?
   → 決定要不要把 `frontend/dist` 掛進 FastAPI(會改 CLAUDE.md §1 部署慣例)。
7. 期貨 / 選擇權寫入的 prod 延遲樣本只有 **3 筆**(全 delta=0)—— 期權面延遲完全沒有證據。
   TXO / 個股期要上量之前,步驟 1 的分段時戳必須先在。
8. 回查鏈 balance 與 OI 並行會不會撞 1019?(步驟 10 的 go/no-go,只能 prod 驗一天)
