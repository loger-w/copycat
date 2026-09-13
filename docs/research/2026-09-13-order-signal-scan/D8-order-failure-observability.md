# D8 — 下單:失效模式與可觀測性(橫向統整)

> 區塊:`copycat/capital/*` + `copycat/server/capital_api.py` + `copycat/server/audit.py`
> + `copycat/server/shutdown_budget.py` + `app.py` lifespan capital 段 + `run.ps1`
> 掃描日期:2026-09-13 · 目標:回答「這條鏈會怎麼壞、壞了看不看得出來、要埋什麼儀器」。
>
> **本輪與 B10 的分工**:B10 量的是「程式碼本身多快」(合成微基準)。D8 量的是
> **prod 真實資料**:22 天 / 1,075 筆審計行 / 79 份 server log / 183 次回查鏈實錄。
> 所有標「實測」的數字都來自 `data/audit/capital-*.jsonl` 或 `logs/server-*.log`,
> 腳本留在 `scratchpad/order-signal-scan/d8-*.py`,可重跑。
>
> **未改動 repo 任何檔案;未啟動 server;未送出任何委託。**

---

## 0. 一句話結論

下單鏈的**故障處理寫得很細**(每一條分支都有 docstring 說明為什麼),但**故障偵測幾乎
不存在**:沒有 metric、沒有告警、`/api/health` 不含 capital 任何一格,而且有一條
**偵測器本身已經死掉、但沒人知道**的路徑(`_ReplyEvents.OnConnect` 在 66 次成功登入中
一次都沒觸發 → 同一個 sink 上的 `OnDisconnect` 極可能同樣不 dispatch → **「券商回報主機
斷線」這個失效模式的唯一偵測器是壞的**)。

真實 prod 資料給出兩個必須先知道的事實:

1. **送單方向沒有出過事**:22 天 536 筆寫入,0 筆逾時、0 筆 late、0 筆審計失敗、
   0 次 COM 幫浦圈例外、0 次執行緒異常終止。B10 列的那些危險路徑(無 TTL、無冪等鍵)
   **機制為真但發生率為零**。
2. **回流方向天天出事**:73 次 `1019` 連發(共 310 行)、8 次部位合併逾時、13 次期貨
   部位查詢未完成、11 次登入失敗導致整個 session 的下單通道永久死亡。**這些全部只有
   一行 WARNING/ERROR 在 log 裡,前端一格都沒有。**

所以這一區該做的順序是:**先把偵測補上(儀器 + 告警),再談優化**。而儀器本身的成本
已經量過了 —— 6 次 `time.perf_counter_ns()` = **0.4 µs**,是審計寫入本身(204 µs)的
**0.2%**。「埋儀器會變慢」在這條鏈上不成立。

---

## 1. 現況地圖 —— 這條鏈實際怎麼運作

### 1.1 兩個方向、三條執行緒

```
                    ┌──────────────── event loop thread(uvicorn,全系統唯一)────────────────┐
瀏覽器 PriceLadder   │                                                                        │
  └→ POST /api/capital/order/stock                                                            │
       capital_api.py:295  pydantic StockOrderBody → StockOrderRequest(frozen dataclass)      │
       client._execute_write(client.py:865)                                                   │
         ① gate.allowed?            safety.py 純函式 5 個閘(<5 µs)                            │
         ② status in (ok,degraded)? ← degraded 也放行(design;見 FM-02)                       │
         ③ await to_thread(_audit(前置))  ★ 共享預設 executor(20 workers,全庫 91 個 caller) │
         ④ fut=loop.create_future(); _cmd_q.put((com_call, fut))   ← 無上界佇列、無 TTL       │
         ⑤ await wait_for(shield(fut), 10 s)                                                  │
         ⑥ self._com.return_code_message(code)  ★ 在 loop 上跨 apartment 直呼 COM             │
         ⑦ await to_thread(_audit(後置))  ★ 同③                                              │
         ⑧ code!=0 → raise BrokerRejectedError(400)                                           │
                    └────────────────────────────────────────────────────────────────────────┘
                                            │ _cmd_q                       ▲ call_soon_threadsafe
                                            ▼                              │
  ┌──────────────────── capital-com thread(daemon,CoInitialize STA,唯一 COM apartment)──────┐
  │  _run(client.py:795)                                                                     │
  │    while True:                                                                           │
  │      _pump_once()   = com.pump()  ← PumpWaitingMessages() inline 跑完全部待處理 COM 事件 │
  │                     + _balance.poll() + _profit.poll() + _oi.poll()                       │
  │                     + _maybe_query_balance()   ← 可能發同步 COM 查詢                      │
  │                     + _poll_pending()                                                     │
  │                     except: log + time.sleep(1.0)   ★ 佔住唯一的送單通道                  │
  │      cmd = _cmd_q.get(timeout=0.05)   ← 寫入命令只有在這一行才被取走                      │
  │      result = fn()                     ← SendStockOrder(user_id, 0, order) bAsync=0 同步  │
  └──────────────────────────────────────────────────────────────────────────────────────────┘
                                            │
                                       SKCOM.dll → 群益主機 → 交易所
```

### 1.2 回流(委託/成交回報 + 部位回查)

回流**與送單共用同一條 COM 執行緒**,而且在 `_pump_once()` 裡跑,也就是**排在寫入命令
之前**。

```
群益回報主機 ─OnNewData→ com.py:281 _ReplyEvents.OnNewData
     try: on_reply(data)
     except: logger.exception("reply 回呼例外,該筆回報丟棄")   ★ 吞掉 = 永久掉一筆
        └→ client._handle_reply(client.py:402)
             reply.parse_onnewdata()  48 欄 split
             store.apply_reply(rec)   取 threading.Lock
               └ D(成交)→ _append_fill_locked + _apply_fill_locked(樂觀套用)
             D → _mark_balance_dirty(0.5)   ← 固定 500 ms debounce
             _emit → call_soon_threadsafe(capital_ws.publish)

回查鏈(串行三段,每次成交後 0.5 s + 每 60 s 定時):
  _maybe_query_balance(client.py:478)
     ├ _pending_sec is not None → return             (鏈進行中不重發)
     ├ _balance_inflight_until 未到 → return          (10 s 守門)
     └ rc = com.get_real_balance(...)
          rc==1019 SK_ERROR_QUERY_IN_PROCESSING → WARNING + _mark_balance_dirty(1.0) 重試
          rc==0 → store.begin_snapshot()(水位)
     OnRealBalanceReport ×N → BalanceCollector → _on_balance_complete
       → _pending_sec = positions; _pending_deadline = now + 8 s
       → com.get_profit_loss_gw(...)
          OnProfitLossGWReport ×N → _on_profit_complete  ← 回填 avg_price / avg_source="broker"
            → _query_open_interest → com.get_open_interest(...)
               OnOpenInterest ×N → _on_oi_complete
                 → _finalize_positions → store.set_positions(全量覆蓋 + 水位重套)
                    → _emit capital_position → WS → 前端 200 ms debounce → 重打三支 REST
     watchdog:_poll_pending 8 s 逾時 → WARNING「部位合併逾時」→ 丟掉損益/OI 兩段
```

### 1.3 關機路徑

`app.py:1252-1254`,**capital 刻意排在 TC4 四條 lane 全部收完之後**(N049):

```python
if booted.capital is not None:
    capital = booted.capital
    await _close_segment("capital", lambda: asyncio.to_thread(capital.close))
```

```python
# client.py:712
def close(self) -> None:
    self._cmd_q.put(None)        # ← FIFO 尾端,前面的寫入命令會先被執行
    t = self._thread
    if t is not None:
        t.join(timeout=COM_JOIN_TIMEOUT_SECS)   # 5.0 s,逾時不 raise
```

預算(實跑 `shutdown_budget` 得到):

| 項 | 值 |
|---|---:|
| `WS_DRAIN_SECS`(uvicorn graceful) | 5 s |
| `TC4_LANE_DEPTH` × `close_worst_secs()` | 2 × 34.0 = 68 s |
| `COM_JOIN_TIMEOUT_SECS` | 5.0 s |
| `LIFESPAN_SLACK_SECS` | 5.0 s |
| `lifespan_close_worst_secs()` | 78.0 s |
| **`run_grace_secs()`(run.ps1 的 taskkill 上限)** | **83 s** |

也就是說:最壞情況下 capital 段在 t=73 s 才進場,只有 10 s 可用,而它自己只肯等 5 s。

---

## 2. 端到端延遲預算(prod 實測為主)

### 2.1 送單方向(每筆委託)

| # | 區段 | 位置 | 成本 | 依據 |
|---|---|---|---|---|
| S1 | 瀏覽器 click → route handler 進入(含 vite preview 4173 proxy 一跳 + event loop 排隊) | `useCapital.ts:102` → uvicorn | **未量測** | 無 loop lag probe、無前端 `performance.mark`。這是唯一「規模由市場決定」的一段(開盤時 loop 上有 5 條 TC4 session 的 tick fanout) |
| S2 | pydantic 驗形 → dataclass + safety 五閘 | `capital_api.py:295` / `safety.py` | 閘 **< 0.005 ms**;pydantic 未量 | B10 實測(閘) |
| S3 | 前置審計:`to_thread` 取到 worker | `client.py:885` | 池有空位 **0.10–0.31 ms**;**恰好 20 條佔滿時 ≥ 1004.9 ms 且無上界** | **本輪實測**(`d8-bench-exec.py`:19 條佔用 → 0.297 ms;20 條 → probe 1.0 s 未回,實測 1004.9 ms = 等到佔用者放手) |
| S4 | 前置審計:`append_audit` 本體(mkdir+open+write+flush+close) | `audit.py:28-38` | p50 **0.204 ms** / p95 0.273 / p99 0.382 / max 0.728 | **本輪實測**(`d8-bench-audit.py`,N=400;B10 量到 0.2535 ms,同數量級) |
| S5 | `_cmd_q.put` → COM 執行緒 `get()` 取走 | `client.py:887` → `client.py:811` | **0–50 ms**(`get(timeout=0.05)` 的輪詢粒度)+ 前一圈 `_pump_once()` 的耗時(**未量測**) | 程式碼常數;`pump()` 在開盤 backlog 重播時的耗時是 open question |
| S6 | `SendStockOrder`(SKCOM 同步、bAsync=0) | `com.py:149-155` | **mean ≈ 76 ms**;尾巴實錄 1 筆落在 (1,2] s、1 筆落在 (3,4] s | **prod 推算**:499 對 pre/post 審計行(秒解析度)中 38 對跨秒界。相位均勻假設下 P(跨界)=延遲秒數 → 38/499 = 7.6% → mean ≈ 76 ms。與 B10 的 70 ms 一致 |
| S7 | `return_code_message(code)`(在 loop 上跨 apartment 直呼 STA COM) | `client.py:910` | **未量測** | B10 F-02;成功路徑每筆必過一次 |
| S8 | 後置審計(取 worker + 寫) | `client.py:917` | 同 S3+S4 ≈ **0.31 ms**,池滿時同樣無上界 | 本輪實測 |
| **S9** | **【合計】前置審計 ts → 後置審計 ts** | 審計檔 | **92.4% 落在同一個時鐘秒(<1 s);7.2% 跨 1 秒;1 筆 2 s;1 筆 4 s** | **prod 實測**,n=499 對(order 418 / cancel 80 / close 1)。**注意:2 s 與 4 s 那兩筆都是 code 999 拒單** —— 券商拒單比成交慢 |

**S3+S4+S8 = 純 Python 前後置審計合計 p50 ≈ 0.72 ms,佔 S9 的 ~1%。** 剩下 99% 在
S5+S6(COM 佇列 + SKCOM 同步往返)。**優化這條鏈的收益上限就是 1%**,除非動 S6 本身
(改非同步送單)或 S5(寫入優先權)。

### 2.2 回流方向(每筆成交 → 部位可見)

| # | 區段 | 位置 | 成本 | 依據 |
|---|---|---|---|---|
| R1 | `OnNewData` → parse + `apply_reply` + 樂觀套用 + emit | `client.py:402-437` | p50 **0.20 ms** / p95 0.90 / p99 **5.50** / max **10.20** | **prod 實測**,n=189(log 行 `成交樂觀套用部位: …(%.1f ms)`)。p99 的 5.5 ms 是 `store._lock` 撞上 REST 讀端或 `set_positions` |
| R2 | `_mark_balance_dirty(0.5)` 固定 debounce | `client.py:475` | **500 ms**(常數) | 程式碼 |
| R3 | `GetRealBalanceReport` 發出 → 庫存段收齊 | `client.py:514` → `_on_balance_complete` | p50 **561 ms**(1061 − 500) | **prod 實測**,n=179(`庫存段收齊(自成交回報到達起 N ms)` p50=1061) |
| R4 | `GetProfitLossGWReport` 發出 → 損益段收齊 | `client.py:550` → `_on_profit_complete` | p50 **583 ms**(1644 − 1061) | **prod 實測**,n=181(p50=1644) |
| R5 | `GetOpenInterestGW` 發出 → 期貨段收齊 | `client.py:631` → `_on_oi_complete` | p50 **295 ms**(1939 − 1644) | **prod 實測**,n=182(p50=1939) |
| R6 | `set_positions`(全量覆蓋 + 水位重套)+ emit | `client.py:666-672` | **≈ 0 ms**(p50 落地 1939 = OI 收齊 1939) | prod 實測,n=183 |
| **R7** | **【合計】成交回報到達 → 部位落地** | | **p50 1,939 ms / p90 4,057 / p95 5,412 / p99 6,553 / max 6,639 ms** | **prod 實測**,n=183(跨 22 天全部 log) |
| R8 | WS `capital_position` → 前端 200 ms debounce → 重打 `/positions` + `/orders` + `/fills` | `useCapital.ts:120-143` | +200 ms + 3 支 REST 往返 | 程式碼 |

**R7 就是使用者感受到的「下單後倉位很慢」的真實數字:p50 快 2 秒、p95 超過 5 秒。**

而 **58% 的成交連樂觀套用都吃不到**:log 統計 `成交樂觀套用部位` 189 次 vs
`成交未樂觀套用` **259 次**(其中 257 次 `market=TS` 整股)—— 這 259 筆成交的使用者
必須等完整的 R7。

---

## 3. 完整失效模式表

> 「零訊號」欄的判準:**使用者在畫面上看不出來,而且沒有任何主動通知**。
> 只有一行 log WARNING/ERROR 仍然算零訊號 —— 沒人盤中看 log。

| # | 失效模式 | 觸發條件 | 症狀 | 零訊號 | prod 實錄 | 現在怎麼偵測 | 該加什麼 |
|---|---|---|---|---|---|---|---|
| **FM-01** | **券商回報主機斷線偵測器本身是死的** | 回報主機斷線 | 委託/成交列靜默凍結;`status` 仍是 `ok`;新送的單永遠不進 `store`(`_orders` 只由 OnNewData 填)→ 委託面板看不到、`_close_dup_reason` 掃不到同向活躍委託 → **防重送整層失效** | **是(最嚴重)** | 0 次 `OnDisconnect`;但 **66 次成功登入中 `OnConnect` 也 0 次**(`com.py:264` 的 INFO 從未出現)→ 同一個 sink 的連線生命週期事件根本不 dispatch | 無 | 見 §4.1:改掛 `OnSolaceReplyConnection` / `OnSolaceReplyDisconnect`,並加 `SKReplyLib_IsConnectedByID` 主動輪詢當後備 |
| **FM-02** | `degraded` 狀態在主要下單介面完全不表述 | `status == "degraded"` | 同 FM-01 的後果;而 `_execute_write` 明確放行 degraded 送單 | **是** | 0 次(因為 FM-01 讓它到不了) | `OrderPanel.tsx:77` 有 `degradedNote`(**只有 TXO 面板**);`PriceLadder.tsx` **完全不讀 `useCapitalStatus()`** | 閃電梯加 degraded 橫幅 + Discord 告警 |
| **FM-03** | 單筆回報解析/套用例外 → 該筆回報**永久丟棄** | `parse_onnewdata` 或 `store.apply_reply` 拋例外 | 該筆委託不在委託列、該筆成交不在 `fills` → 圖上成交點少一個、`today_qty` 當沖段算錯 → **打平線的當沖稅減半失效**(CLAUDE.md §4 `today_qty` 契約) | **是** | 0 次(`reply 回呼例外` grep = 0) | `com.py:288` 一行 `logger.exception` | 計數器 + 連續 N 筆就 Discord;`fills` 缺口靠 seq 斷號偵測 |
| **FM-04** | 送單逾時 10 s → 命令留在 `_cmd_q`,**無 TTL、無取消** | `SendStockOrder` 阻塞 > 10 s | HTTP 回 **200 OK** 帶 `ok:false, code:-1, message:"結果未知,勿重送"`;命令仍在佇列,COM 恢復後**照送市場** | 部分(前端有錯誤列,但「這張單在不在市場上」無法回答) | **0/536**(`late` 行 0 筆、`code:-1` 0 筆) | `_on_late_result` 補一行 `late:true` 審計 + WARNING | 命令帶 deadline,`_run` 取出時過期就丟 + 審計 `expired`;審計加 `client_order_id` |
| **FM-05** | **前置審計卡在共享預設 executor** | 20 個 worker 全被 TC4 / FinMind 的不可中斷阻塞佔滿 | 送單 HTTP 一直轉,直到有 worker 空出;每條 TC4 最壞 10–22 s | **是,且無上界** | 未觀測(無探針) | **無** | **本輪實測**:19 條佔用 → 0.297 ms;**20 條 → ≥1004.9 ms**(懸崖)。加專用 1-worker 審計池 + 暴露 `queue depth` |
| **FM-06** | **部位回查 1019 storm**(`SK_ERROR_QUERY_IN_PROCESSING`) | 上一個 SKCOM 查詢還在處理中就發下一個;**每次 server 啟動必發** | 部位 / 均價 / 損益基底停更數秒~9 秒;每次 1 s 退避重試 | **是** | **73 次 storm / 310 行**;長度分佈 1:2 / 2:6 / 3:9 / **4:30** / 5:17 / **7:8** / 8:1;最長 **8 發 9.1 s**(2026-09-09 10:30);啟動型實錄:2026-08-21 17:53:51 登入 → 17:53:53 起連 7 發 8.2 s | `client.py:521` 一行 WARNING | 指數退避取代固定 1 s;啟動時先等 `GetUserAccount` 真的收完;暴露 `balance_chain_1019_count` |
| **FM-07** | **部位合併逾時 → 當輪損益整批丟棄** | `_pending_deadline`(8 s)到期 | `_profit.abandon()` → **`avg_price` / `avg_source` / `pnl_base` 這一輪全部沒回填** → wire 上 `avg_source` 是 `null` → 前端 `positionEcon` 退回「fill 口徑,多加一次買費」→ **打平線跳一格**(CLAUDE.md §4 `avg_source` 契約明寫這是 #118 在 prod 死掉的方式) | **是** | **8 次**,其中 **7 次集中在 2026-08-18 09:46–09:56 這 10 分鐘**(每分鐘一次) | `client.py:693` 一行 WARNING | `avg_source` 為 null 的部位列在前端標「均價待券商確認」;連續 N 次 → Discord |
| **FM-08** | 期貨部位查詢未完成 → 沿用上一輪 | OI 段 rc≠0 或逾時 | 期貨部位顯示的是**舊快照**,看起來完全正常 | **是** | **13 次** | `client.py:642` 一行 WARNING | 部位列帶 `as_of` / `stale` 旗標 |
| **FM-09** | **登入失敗 = 下單通道永久死亡、零重試** | `SKCenterLib_Login` 等任一步失敗 | `_init_com` 回 False → `_run` 直接 return → `finally` 設 `status=error` → **執行緒結束,整個 process 生命週期內不再有下單能力** | 部分(`/api/capital/status` 回 error;`OrderPanel` 會鎖,**`PriceLadder` 不會**) | **11 次**,全部 `Login: SK_ERROR_TELNET_LOGINSERVER_FAIL`(2026-08-04 ~ 08-13 連續 11 個 session) | `client.py:777` 一行 ERROR | 啟動失敗 → **Discord 告警**;加有上限的重試(登入伺服器故障是暫時性的) |
| **FM-10** | **券商拒單 9.7%,其中多數本地可預檢** | 額度 / 庫存 / 可沖銷量 / 融資額度不足 | 使用者按了鈕、等 1–4 秒、拿到紅字。**每一筆都燒掉一次完整 COM 往返**(而 COM 是單一通道) | 否(有錯誤列),但**沒有累計、沒有告警、沒有本地預檢** | **52/536 = 9.7%**。code 999×40(`網路單交易額度超過限定額度 249萬`、`此人融資已滿`、`集保庫存剩 0 股`、`可沖銷股數 0 股`、`尚未簽署創新版風險預告書`)、1068×7、400×3、960×2 | 前端錯誤列 | 本地前置風控(見 F-04);拒單率 metric;同一原因連續 N 次 → Discord + 自動 halt |
| **FM-11** | **關機時 COM 卡在 `SendStockOrder` → 後置審計永遠不寫** | 關機瞬間有在途寫入 | `close()` join 5 s 逾時、不 raise → lifespan 走完 → process 退出 → daemon 執行緒被殺 → **單送出去了,審計檔只有前置那一行,沒有結果行** | **是** | 未觀測 | 無 | 關機時若 `_cmd_q` 非空或有在途命令,先寫一行 `shutdown_pending` 審計 |
| **FM-12** | **關機時佇列殘留寫入命令會被送進市場** | `close()` 把 `None` 放到 FIFO **尾端** | `_run` 依序取,`None` 之前的寫入命令**全部照送**;包含 10 秒前已被 HTTP 端放棄的那些 | **是** | 未觀測 | 無 | `close()` 改先 drain 再 put None;或給命令 deadline |
| **FM-13** | `capital.close()` 走共享 executor,池飽和則關機段不啟動 | 關機時 20 worker 被 TC4 佔滿 | 關機 capital 段一步都跑不到 → 83 s 後 `run.ps1` `taskkill /T /F` → COM 執行緒被硬殺 | **是**(只能事後由「關機 capital 段開始」有印、「關機收尾」沒印來反推) | 未觀測 | `_close_segment` 的「段開始」log(`app.py:1188`,review SP3 就是為這個設計的) | `capital.close` 不走共享池(它本來就只是 `queue.put` + `join`,可直接同步呼叫) |
| **FM-14** | 盤中重啟 → 訊號/部位狀態全失 + 啟動 1019 storm | 任何重啟 | `store` 全空,靠回報 backlog 重播重建;`_positions_seeded` 之前的成交不樂觀套用;啟動後約 **8–10 秒零部位資料** | **是** | FM-06 的啟動型 storm 就是這個 | 無 | `/api/capital/status` 加 `positions_seeded` / `first_snapshot_at` |
| **FM-15** | **審計只 `flush()` 不 `fsync()`** | 藍屏 / 斷電 / 硬殺 | 丟掉 OS page cache 裡最後幾筆 —— **正是事故當下那幾筆**。這是「錢動了、事後必須查得到帳」且**不可重建**的唯一一份 | **是** | 未觀測 | 無 | persistent handle + `os.fsync`,**本輪實測成本 0.313 ms vs 現況 0.204 ms,只貴 0.11 ms**(= S9 的 0.14%) |

---

## 4. 對 logs/ 的完整關鍵字掃描結果

> 上一輪的結論是 `grep -c "COM 幫浦圈例外" logs/*.log` 全部為 0。**確認為真**,並擴大關鍵字。
> 掃描範圍:`logs/` 全 79 份 server log(24 MB,2026-08-04 ~ 2026-09-11)。

### 4.1 零命中(機制存在但從未觸發,或偵測器本身是壞的)

| 關鍵字 | 命中 | 判讀 |
|---|---:|---|
| `COM 幫浦圈例外` | **0** | 確認上一輪結論。幫浦圈從未拋例外 → `time.sleep(1.0)` 那條路徑從未走過 |
| `結果未知` / `寫入結果晚到` | **0** | **送單逾時從未發生**(536 筆寫入) |
| `審計後置寫入失敗` / `晚到結果審計寫入失敗` / `AuditWriteError` | **0** | 審計從未寫失敗 |
| `COM 執行緒已終止` / `寫入命令丟棄` / `event loop 已關閉` | **0** | `_drain_pending` 的兩條路徑從未走過 |
| `回報連線中斷` / `Capital reply disconnected` / `Capital reply connect error` / `回報連線失敗` | **0** | 見下方 ⚠ |
| **`Capital reply connected`** | **0** | ⚠ **這一條是紅旗**。`com.py:267` 的 `OnConnect` INFO 在 `nErrorCode == 0` 時必印,而 `SKReplyLib_ConnectByID` 在 **66 個 session 成功** (`Capital login + cert OK … status=ok` × 66,零 `reply connect failed`)。**66 次成功連線、0 次 OnConnect** ⇒ `_ISKReplyLibEvents.OnConnect` 根本沒有 dispatch 到我們的 sink |
| `reply 回呼例外` / `balance 回呼例外` / `profit 回呼例外` / `open-interest 回呼例外` | **0** | 四個 sink 的吞例外分支從未走過 |
| `capital broadcast 例外` | **0** | |
| `帳號清單查無期貨戶` / `SetAuthority rc=` | **0** | 期貨帳號每次都發現得到 |
| `期貨部位鍵差異` | **0** | 樂觀套用的期貨契約碼從未與券商 OI 對不上(樣本少) |
| `COMError` | **0** | |

#### ⚠ FM-01 的技術根據(本輪新查)

檢查 venv 裡 comtypes 產生的 typelib stub
`.venv/Lib/site-packages/comtypes/gen/_75AAD71C_..._0_1_0.py`,`_ISKReplyLibEvents`
的 `_disp_methods_` 是:

```
['OnConnect', 'OnDisconnect', 'OnComplete', 'OnData', 'OnReplyMessage',
 'OnReplyClear', 'OnNewData', 'OnSolaceReplyConnection', 'OnSolaceReplyDisconnect',
 'OnReplyClearMessage', 'OnStrategyData', 'OnReplyMessageSpecial']
```

`com.py:250-288` 的 `_ReplyEvents` 只實作了 **`OnReplyMessage` / `OnConnect` /
`OnDisconnect` / `OnNewData`** 四支。名稱拼寫與 typelib 完全一致,所以不是打錯字。
`OnNewData` 明確會觸發(330 筆 `KeyNo=…不同` WARNING + 大量 `Capital reply:` INFO),
`OnReplyMessage` 也會(沒有群益彈窗)。**唯獨連線生命週期那兩支零命中。**

最可能的解釋:現版 SKCOM 的回報通道走 **Solace**(typelib 裡有
`SKReplyLib_SolaceCloseByID` 這支方法,以及 `OnSolaceReplyConnection` /
`OnSolaceReplyDisconnect` 這對事件),legacy 的 `OnConnect`/`OnDisconnect` 已不再送。

**後果**:`_handle_reply_disconnect` 是「回報停更」這個失效模式的**唯一**偵測器
(另一條路只有 `_init_com` 裡 `connect_reply` rc≠0),而它極可能永遠不會被呼叫。
於是 `status` 永遠停在 `ok`,委託/成交面板靜默凍結,而 `_execute_write` 照樣放行送單
—— 送出去的單不會進 `store`、`_close_dup_reason` 的第二層防重送整層失效。

**驗證方法(不需要斷券商)**:在 `_ReplyEvents` 上加 `OnSolaceReplyConnection` /
`OnSolaceReplyDisconnect` 兩支只印 log 的方法,下次啟動看哪一支印出來。這是零風險的
一次性實驗。另外 `SKReplyLib_IsConnectedByID` 是**同步查詢**,可以在幫浦圈每 N 秒打
一次當作不依賴事件的後備偵測。

### 4.2 有命中(真實發生過的事故)

| 關鍵字 | 命中 | 事故判讀 |
|---|---:|---|
| **`GetRealBalanceReport rc=1019: SK_ERROR_QUERY_IN_PROCESSING`** | **310** | 73 次連發。詳見 FM-06。**每一個交易日都會發生**,近期(09-09/09-10/09-11)分別 15/14/13 行 |
| **`Capital init failed: RuntimeError: Login: SK_ERROR_TELNET_LOGINSERVER_FAIL`** | **11** | 2026-08-04 ~ 08-13 共 11 個 session,**每次都是整個 session 的下單通道永久死亡**。後續未再出現(推測憑證/環境問題已解) |
| `capital-com 執行緒結束(status→error)` | 44 | 11 次是上一列的 init 失敗;其餘 33 次是正常關機(`_run` 收到 `None` 後走 `finally`)。⚠ **正常關機也印 ERROR「執行緒結束(status→error)」,與真故障同形** —— 事後 grep 分不出來 |
| **`部位合併逾時(損益/期貨查詢未完成)`** | **8** | 7 次集中在 2026-08-18 09:46–09:56。詳見 FM-07 |
| **`期貨部位查詢未完成 — 沿用上一輪 fut 部位(0 列)`** | **13** | 詳見 FM-08 |
| `損益報告遲到(本輪 pending 已發布),丟棄 N 列` | 7 | FM-07 的下一拍:被放棄那一輪的 `##` 遲到了 |
| `期貨部位回報遲到` | 1 | 同上 |
| `GetProfitLossGWReport rc=` / `GetOpenInterestGW rc=` | 5 / 5 | 回查鏈中後兩段的 rc 失敗 |
| `profit row 種類不符略過` | **304** | 高頻。每次都代表**那一列部位這一輪沒回填均價** → `avg_source` 留 null。這是 FM-07 的低烈度版本,而且**它是 WARNING 但完全不影響 UI 表現**(前端只是退回 fill 口徑) |
| `Capital reply: KeyNo=… 尾欄序號=… 不同(預約單?)` | **330** | docstring 說「刪單回報(C)除外」且「2026-08-25 實錄 16 筆全是盤中單」。330 筆遠超過那 16 筆的推論範圍 —— **這條 WARNING 的判準已經與現實脫節,正在洗版** |
| `成交未樂觀套用(…),等回查鏈` | **259** | vs `成交樂觀套用部位` 189 次。**58% 的成交要等完整回查鏈**(p50 1.94 s / p95 5.41 s) |
| `1097` | 69 | ⚠ **全部是誤命中**(委託序號 `…1097…`、HTTP 來源 port `51097`、`stock backfill 6451: 1097 ticks`)。**CLAUDE.md 記載的「test 沙盒未開通 → 1097」在 log 裡一次都沒有真的發生過** —— 因為 22 天審計中 1,072/1,075 筆是 `env=prod`,只有 3 筆 `env=test`(且全是 `capital_not_ready` blocked) |

### 4.3 審計檔(`data/audit/capital-*.jsonl`)全量統計

22 個交易日、**1,075 筆**審計行:

| 項 | 值 |
|---|---|
| action 分佈 | `order` 841 / `cancel` 232 / `close` **2** |
| env | `prod` 1,072 / `test` 3 |
| blocked | **3**,全部 `capital_not_ready`(2026-07-29 那天的 test) |
| 有 result 的行(= 後置) | 536 |
| 成功(code 0) | 484 |
| **拒單** | **52(9.7%)** — 999×40 / 1068×7 / 400×3 / 960×2 |
| `late: true` 行 | **0** |
| `code: -1`(結果未知 / COM 例外) | **0** |
| 每日寫入筆數 | 10 ~ **77**(峰值 2026-08-21),中位數 ~19–24 |
| 審計行大小 | 156 bytes(現況);加 `lat_us` + `cid` 後 289 bytes |

**拒單原因細目(prod 原文)**:

| code | n | 代表訊息 | 本地可否預檢 |
|---:|---:|---|---|
| 999 | 40 | `網路單交易額度超過限定額度 249萬!` | **可**(累計當日委託名目) |
| 999 | | `集保庫存剩 0 股,不得賣出或匯撥交割` | **可**(`store.positions()` 就有) |
| 999 | | `目前此投資人可沖銷股數,資買: 0 股; 集買: 0 股` | **可**(`today_qty` 已經在算了) |
| 999 | | `此人融資已滿!欲借 57萬;額度 90萬` | 需券商額度資料,**不可** |
| 999 | | `此投資人尚未簽署創新版風險預告書,不可委託!` | 一次性,**可快取** |
| 1068 | 7 | `SK_ERROR_SPECIAL_TRADE_TYPE_IS_MARKETPRICE_AND_ORDERPRICE_SHOULD_BE_ZERO` | **已修**,見 §7 |
| 400 | 3 | `DB查詢失敗: tblPriceFuturePM : TMFI6無法轉換商品ID` | **可**(微台 TMF 契約碼對映) |
| 960 | 2 | `此委託不可做刪改!` / `查無委託資料` | **可**(`o.actionable` 已經在 store 裡) |

**至少 45/52(86%)的拒單,系統手上已經有足夠資料在本地擋下來。** 每一筆被擋下的
拒單都省掉一次 COM 單一通道的往返(mean 76 ms,拒單尾巴到 4 s)。

---

## 5. 下單鏈需要什麼儀器

### 5.1 分段時戳 —— 成本已量,是免費的

`d8-bench-audit.py` 實測:

| 項 | p50 |
|---|---:|
| **6 × `time.perf_counter_ns()`** | **0.0004 ms(0.4 µs)** |
| `json.dumps(現況 record)` | 0.0019 ms |
| `json.dumps(record + lat_us + cid)` | 0.0025 ms |
| `append_audit` 本體 | 0.204 ms |

**埋 6 個時戳 + 多序列化 133 bytes 的總成本 ≈ 0.0010 ms,是審計寫入的 0.5%、是
S9 端到端(≈76 ms)的 0.0013%。** 沒有任何理由不埋。

埋法(`client._execute_write`,stdlib、零相依、零跨檔契約):

```python
t = [time.perf_counter_ns()]          # ① 進 _execute_write
...gate...
t.append(time.perf_counter_ns())      # ② gate 過
await self._audit_pre(...)            # (順手帶 cid 進前置行)
t.append(time.perf_counter_ns())      # ③ 前置審計落地
self._cmd_q.put((com_call, fut))
message, code, com_ns = await wait_for(shield(fut), ...)   # _ComCall 回傳擴成三元組
t.append(time.perf_counter_ns())      # ④ COM 結果回到 loop
...
record["lat_us"] = {
    "gate": (t[1]-t[0])//1000, "audit_pre": (t[2]-t[1])//1000,
    "queue_and_com": (t[3]-t[2])//1000, "com": com_ns//1000,   # ← 在 COM 執行緒量
    "total": (time.perf_counter_ns()-t[0])//1000,
}
```

`com` 那一段**必須在 COM 執行緒的 `_run` 裡量**(`fn()` 前後),隨結果回傳 ——
這是唯一能把 S5(佇列等待)與 S6(SKCOM 本體)分開的方法,而這兩段合計佔了 99%。

順手做掉的兩件事:
- `client_order_id`(uuid4 hex 前 16 碼)寫進**前置**行 → FM-04 的對帳能力;
- `ts` 改 `timespec="milliseconds"` → 現有的秒解析度分析(§2.1 S9)不用再靠機率推算。

### 5.2 要暴露的 metric

用 stdlib `collections.deque(maxlen=1024)` 的 ring buffer,零相依:

| metric | 來源 | 為什麼要 |
|---|---|---|
| `write.total_us` p50/p95/p99 + `com_us` p50/p95/p99 | §5.1 的 ring | 唯一能回答「要不要優化」的資料 |
| `write.count` / `reject.count` / `reject.by_code` | `_execute_write` | FM-10:9.7% 拒單率是不是在變壞 |
| `write.timeout_count` / `late_count` | timeout 分支 | FM-04 目前是 0,任何一次非零都要立刻知道 |
| **`audit_pool.queue_depth`** | 專用 executor `_work_queue.qsize()` | **FM-05 的唯一可觀測量**;現在是完全的黑洞 |
| `cmd_q.depth` | `self._cmd_q.qsize()` | FM-12:關機前該是 0 |
| `com_thread.alive` / `com_thread.last_pump_ts` | `_pump_once` 尾端記 monotonic | FM-09 / 幫浦圈卡死;`now - last_pump > 5 s` = 執行緒卡在某個同步 COM 呼叫裡 |
| `reply.last_seen_ts` / `reply.count_today` | `_handle_reply` | **FM-01 的不依賴事件的後備偵測**:盤中 09:00–13:30 超過 N 分鐘零回報而我們有活躍委託 = 回報停更 |
| `balance_chain.1019_count` / `.timeout_count` / `.last_landed_ts` / `.last_duration_ms` | `_maybe_query_balance` / `_finalize_positions` | FM-06 / FM-07 / FM-08 |
| `positions.avg_source_null_count` | `store.positions()` | FM-07 的**畫面級**判準:這個數字 > 0 就是打平線在用錯口徑 |
| `loop_lag` p50/p95/max | 常駐 probe(B10 §6.3) | S1 的下界;也是全系統共用 |

### 5.3 `/api/health` 該加什麼

現況 `app.py:1290-1296` 只回 build 身分,docstring 明寫「刻意不含引擎健康度」。
**這個設計決定是對的,不要破壞它。** 改法:新開一支

```
GET /api/capital/metrics   → 上表全部 + capital status + 最近一筆寫入的 lat_us
```

理由(與 `/api/health` docstring 的理由同構):`/api/health` 要在引擎壞掉時**仍然
答得出版本**;把 capital 指標混進去會讓它在 COM 執行緒死掉時一起答不出來。

`/api/capital/status` 則補三格(它本來就是 capital 專屬,加在這裡不違反上面的分工):
`positions_seeded`(bool)、`reply_last_seen_ts`、`com_thread_alive`。前端閃電梯
就是靠這三格決定要不要擋。

### 5.4 前端半邊

`PriceLadder` 的 onClick `performance.mark("order:click")`、mutation `onSettled`
`performance.mark("order:done")`。與後端 `lat_us.total` 相減 = S1 + S8 之後那一段
(vite proxy + loop 排隊 + HTTP 回程)。這是目前唯一完全沒有數字的一段。

---

## 6. 關機路徑的三個洞

### 6.1 預算分配

`run_grace_secs() = 83 s`。capital 是**最後一段**,而 TC4 四條 lane 的最壞值是
`TC4_LANE_DEPTH(2) × close_worst_secs(34.0) = 68 s`。所以:

- 健康路徑:TC4 全段 1–3 s,capital 在 t≈5 s 進場,`close()` 幾十毫秒回來。**沒問題。**
- TC4 半死:capital 在 t≈73 s 進場,`COM_JOIN_TIMEOUT_SECS = 5 s` + `LIFESPAN_SLACK_SECS = 5 s`
  剛好把 83 s 填滿,**零裕度**。

### 6.2 三個洞

| 洞 | 機制 | 後果 |
|---|---|---|
| **FM-11 後置審計永遠不寫** | `close()` 的 `join(5.0)` 逾時**不 raise**(docstring 明寫是刻意的),lifespan 續行 → process 退出 → daemon 執行緒被殺 | 若當下 COM 卡在 `SendStockOrder`,那筆單**送出去了但審計只有前置行**。這是唯一一份不可重建的紀錄 |
| **FM-12 殘留命令照送市場** | `close()` 做的是 `self._cmd_q.put(None)` —— **放到 FIFO 尾端**。`_run` 依序取,`None` 之前的寫入命令會被 `fn()` 執行 | 10 秒前已被 HTTP 端放棄的單,在關機當下送進市場 |
| **FM-13 關機段可能一步都跑不到** | `await _close_segment("capital", lambda: asyncio.to_thread(capital.close))` —— **走共享預設池**。池被 TC4 殭屍佔滿時,`to_thread` 排隊(§3 FM-05 實測:20 條佔滿 = 無上界) | 83 s 到 → `taskkill /T /F` → COM 執行緒硬殺。事後只能靠「關機 capital 段開始」有印、「關機收尾」沒印來反推 |

**FM-13 的修法是零成本的**:`capital.close()` 本體只是 `queue.put` + `thread.join`
—— 它**本來就不該進 thread pool**。`join(5.0)` 會阻塞 loop 5 秒,但那是關機路徑的
最後一段,loop 上已經沒有別的事了。改成 `await asyncio.to_thread` → 直接同步呼叫,
預算不變(`COM_JOIN_TIMEOUT_SECS` 仍是同一個常數,`shutdown_budget` 的不等式與
`tests/server/test_shutdown_budget.py` 都不用動)。

**FM-12 的修法**:`close()` 先 drain 再 put None:

```python
def close(self) -> None:
    while True:                      # 先把未執行的寫入命令 fail 掉
        try: cmd = self._cmd_q.get_nowait()
        except queue.Empty: break
        if cmd is None: continue
        _fn, fut = cmd
        ...call_soon_threadsafe(_settle, fut, None, RuntimeError("關機中,命令未執行"))
    self._cmd_q.put(None)
    ...
```
(邏輯與既有的 `_drain_pending` 完全相同,只是搬到 `close()` 的開頭再跑一次。)

⚠ 這一段碰 **CLAUDE.md §4「關機預算三方同源」契約**:改 `close()` 的內容**不**改
預算(`COM_JOIN_TIMEOUT_SECS` 沒變);但把 `capital.close` 從 `to_thread` 拿掉算是
**改 lane 形狀**,要確認 `tests/server/test_boot_window.py::TestShutdownLanes` 的
`TC4_LANE_DEPTH` 斷言是否涵蓋 —— 看程式碼,`TC4_LANE_DEPTH` 只描述 TC4 那四條 lane
的串鏈深度,capital 段不在其中,**應該不需要改常數**,但要跑那支測試確認。

---

## 7. 送單頻率上升之後,哪一個先撞牆

現況基線(prod 實測):**每日 10–77 筆寫入、每 session ≤ 58 筆回報**。
以下是把送單頻率往上推時,各資源的撞牆順序。

| 順位 | 資源 | 現況用量 | 容量上界 | 依據 | 撞牆症狀 |
|---:|---|---|---|---|---|
| **1** | **部位回查鏈(串行、不可重入)** | ~20 fills/day | **~0.5 fills/s** | 鏈的 p50 = **1.94 s**、p95 = **5.41 s**(實測 n=183),加 0.5 s debounce。fill 到達率超過 1/(chain+debounce) 就永久飽和 | 1019 storm 變常態(現在已經 73 次);部位 / 均價 / 打平線落後數秒到十數秒;FM-07 的「損益整批丟棄」從每月 8 次變成每分鐘 |
| **2** | **群益網路單額度 249 萬** | 已撞 30 次 | 以 350 元 × 1 張計 ≈ **7 筆**就滿 | code 999 實錄 40 筆 | 額度滿之後**每一筆都是完整 COM 往返的浪費**(mean 76 ms,實錄尾巴 4 s),而 COM 是單一通道 → 自動化策略會把單一通道燒在必敗的請求上 |
| **3** | **COM 執行緒單一通道** | ~0.001 writes/s | **≈ 13 writes/s** 理論上限(1/76 ms);**實務 2–5 writes/s** | S6 的 mean 76 ms;加上每圈 `_pump_once()` 與回查鏈的三次同步查詢(未量測) | 寫入排隊。`_cmd_q` 無上界 → 排 100 筆 = 最後一筆等 7.6 s → 撞 `_WRITE_TIMEOUT_S` 10 s → FM-04 第一次真的發生 |
| 4 | `_close_inflight` 10 s 窗 | 2 筆 close / 22 天 | **同一個 key 每 10 s 1 筆** | `_CLOSE_INFLIGHT_S = 10.0` | 自動化平倉策略會被自己的防重送擋住,而錯誤訊息是「平倉單剛送出(在途)」—— 看起來像重複點擊 |
| 5 | **共享預設 executor 20 workers** | 不隨送單率成長 | **事件驅動,不是速率驅動** | §3 FM-05 實測 | 與送單頻率無關,但送單頻率上升會讓「撞上的機率」上升。**這是唯一一個會把延遲從毫秒推到秒/分鐘的資源** |
| 6 | `store._orders` 無裁剪 | N = 16–63 | 成長軸是 **process uptime**,不是當日筆數(`clear()` 零 prod caller,`store.py:623`) | B10 F-06 / 本輪確認 | N=1000 時 `orders()` 2.6 ms + `asdict` 7.2 ms,**持 `threading.Lock` 在 event loop 上**,每 30 s + 每筆成交 debounce 一次。1000 筆/日 × 1000 次輪詢 = 每日 ~10 s 的 loop 凍結 |
| 7 | 審計檔 IO | 2 行 × 156 bytes / 寫入 | `_audit_lock` 序列化,0.204 ms/行 → **≈ 2,450 行/s** | 本輪實測 | 遠在 COM 之後,不是瓶頸。改 persistent handle 後是 **185,000 行/s** |

**結論:自動化之前必須先解掉 #1 和 #2。**
- #1 的解法不是把鏈跑快,而是**讓樂觀套用涵蓋更多情況**(現在 58% 的成交吃不到)
  + 讓鏈能**合併**連續成交(它已經有 debounce,但飽和時 1019 storm 把它打壞)。
- #2 的解法是把「當日累計委託名目」做成本地閘 —— 資料全部都在 `store` 裡。

---

## 8. 告警:什麼情況該主動通知,現在有嗎

### 8.1 現在有嗎 —— **沒有,一個都沒有**

```
grep -rn "notify|discord|webhook" copycat/capital/ copycat/server/capital_api.py copycat/server/audit.py
  → 只命中 factory.py 的三行「env 讀取慣例」註解,零實際呼叫
grep -rn "from copycat.notify import" copycat/
  → copycat/cli.py:349(CLI notify-test)
  → copycat/server/app.py:59(訊號推播)
```

**`notify_discord` 在整條下單鏈上有 0 個 caller。** 系統有完整的 Discord 通道
(`DISCORD_WEBHOOK_URL` + `DISCORD_BOT_TOKEN` + `SIGNALS_DISCORD_CHANNEL_ID`),而且
訊號那邊已經在用(四行卡、節流、fallback 都寫好了),**下單這邊一格都沒接**。

對比之下,訊號(不動錢)有完整的推播鏈 + 節流 + 佇列 + jsonl 真相源;下單(動錢)
只有 log。這個優先序是反的。

### 8.2 該通知什麼(依「不通知的代價」排序)

| 事件 | 為什麼要主動通知 | 現況 | 頻率(prod 實測) |
|---|---|---|---|
| **啟動時 `_init_com` 失敗** | 整個 session 沒有下單能力,而使用者要等到第一次按鈕才發現 | 一行 ERROR | **11 次 / 22 天** |
| **`status` 轉 `error`(COM 執行緒死)** | 同上,但發生在盤中 | `_emit` 有推 `capital_status` WS,但**前端閃電梯不讀** | 0 次 |
| **`status` 轉 `degraded`(回報停更)** | 委託面板與市場脫節,防重送失效 | 偵測器本身疑似是死的(FM-01) | 0 次(可能是偵測不到) |
| **送單逾時 / `late` 結果** | 「這張單在不在市場上」無法回答,必須人肉去看群益 APP | 一行 WARNING | 0 次 |
| **同一 `code` 連續 N 筆拒單** | 額度滿 / 憑證問題 / 契約碼壞掉 —— 繼續送只是燒 COM 通道 | 前端錯誤列(一次性) | 999 連續出現過 |
| **回查鏈連續 M 次 1019 / 逾時** | 部位資料停更,而畫面看起來完全正常 | 一行 WARNING | **73 次 storm / 8 次逾時** |
| **`avg_source` 為 null 的部位列 > 0 持續 T 秒** | 打平線正在用錯口徑算稅費(CLAUDE.md §4 契約明列這是 #118 的死法) | 無 | FM-07 每發生一次就是一次 |
| **關機時 `_cmd_q` 非空** | 有單要被送進市場或被丟棄 | 無 | 未觀測 |
| **`audit_pool.queue_depth` > 0 持續 T 秒** | 送單正在被共享池卡住 | 無(池本身不存在) | 未觀測 |

實作上可直接沿用 `notify.py`(URL 未設 no-op、never-raise、429 Retry-After 重試一次),
掛在 `client._set_status` 與 `_execute_write` 的錯誤分支,加一個 per-事件的節流表
(訊號那邊的 `signal_hub` 已經有現成的節流模式可以照抄)。

---

## 9. Findings(依嚴重度)

> B10 已列的條目不重述,只標「見 B10 F-xx」。以下是本輪**新增或以 prod 資料改寫嚴重度**的。

### D8-01 【critical】回報主機斷線的唯一偵測器疑似是死的(66:0 證據)
`com.py:250-288` `_ReplyEvents` 只實作 `OnReplyMessage` / `OnConnect` / `OnDisconnect` /
`OnNewData`。typelib `_ISKReplyLibEvents` 另有 `OnSolaceReplyConnection` /
`OnSolaceReplyDisconnect`。**66 次成功 `SKReplyLib_ConnectByID`、0 次 `Capital reply
connected` log** ⇒ legacy 那對事件不 dispatch。
後果:`_handle_reply_disconnect` → `degraded` 這條路走不到 → 委託/成交面板靜默凍結、
`status` 仍 `ok`、送單照放行、`_close_dup_reason` 第二層防重送失效。**零錯誤訊號。**
修法:加掛 Solace 那對事件(先只印 log 驗證)+ `SKReplyLib_IsConnectedByID` 幫浦圈輪詢後備。

### D8-02 【critical】共享預設 executor 飽和 = 送單無上界阻塞(懸崖實測在 20)
`client.py:885`(前置)/ `client.py:353`(後置)/ `app.py:1254`(關機)全走
`asyncio.to_thread`。全庫 **91 個 `to_thread` caller、14 個模組、零自建 executor、
零 `set_default_executor`**(已 grep 確認)。
**本輪實測**:佔用 19 條 → probe 0.297 ms;**佔用 20 條 → probe 1004.9 ms(= 一直等到
佔用者放手,無上界)**。而同池上跑的是 TC4 REQ(`_REQ_TIMEOUT_MS = 10_000`、鎖 12 s,
**不可中斷**)與 FinMind(timeout 30/60 s)。
零探針、零錯誤訊號 —— HTTP 就是一直轉。B10 F-01 的機制,本輪補上懸崖點的實測。

### D8-03 【high】1019 storm 是常態不是異常:73 次 / 310 行 / 啟動必發
`client.py:514-522`。連發長度分佈 1:2 / 2:6 / 3:9 / **4:30** / 5:17 / 7:8 / 8:1,
最長 **8 發 9.1 s**(2026-09-09 10:30)。**啟動型實錄**:2026-08-21 17:53:51 登入成功
→ 17:53:53 起連 7 發、持續 8.2 s → 啟動後約 10 秒完全沒有部位資料。
退避是固定 `_mark_balance_dirty(1.0)`,不是指數;守門旗標 `_balance_inflight_until`
在 rc≠0 時就被清掉(`client.py:516`),所以下一輪照發。
症狀只有 WARNING,前端完全正常。

### D8-04 【high】9.7% 的寫入被券商拒絕,而 86% 的拒單本地擋得下來
prod 實測 52/536。code 999×40 的實際原文包含 `網路單交易額度超過限定額度 249萬`、
`集保庫存剩 0 股`、`可沖銷股數 0 股` —— 這三類的判斷資料**全部已經在 `store` 裡**
(`positions()`、`today_qty`、`orders()`)。另有 960×2 `此委託不可做刪改 / 查無委託資料`
—— `OrderRecord.actionable` 就是為這個存在的。
每一筆拒單燒掉一次 COM 單一通道往返(mean 76 ms,實錄尾巴 2 s / 4 s);**兩筆最慢的
寫入(4 s、2 s)都是 code 999**。
現況:無累計、無 metric、無告警、無本地預檢。

### D8-05 【high】部位合併逾時把當輪損益整批丟棄 → 打平線用錯口徑,零前端訊號
`client.py:687-703`。`_pending_deadline`(8 s)到期 → `_profit.abandon()` →
這一輪 `avg_price` / **`avg_source`** / `pnl_base` 全部沒回填 → wire 上 `avg_source`
是 `null` → 前端 `ladder-position.ts::positionEcon` 退回 fill 口徑、**多加一次買費**。
CLAUDE.md §4 明寫這正是 #118 在 prod 死掉的方式(「打平線在快照落地時跳一格,
零錯誤訊號」)。
prod 實錄 **8 次**,其中 7 次集中在 2026-08-18 09:46–09:56。
另有低烈度版本:`profit row 種類不符略過` **304 次** —— 每一次都是一列部位這一輪沒回填。

### D8-06 【high】登入失敗 = 下單通道永久死亡、零重試、零告警
`client.py:775-778` + `client.py:806-807`:`_init_com()` 回 False → `_run` 直接 return
→ `finally` 設 `status=error`、`_drain_pending()`、執行緒結束。**process 生命週期內
不再有任何下單能力,而且沒有重試路徑。**
prod 實錄 **11 次**(2026-08-04 ~ 08-13),全部 `SK_ERROR_TELNET_LOGINSERVER_FAIL`
—— 這是**券商登入伺服器的暫時性故障**,重試大概率會成功。
偵測:一行 ERROR + `/api/capital/status` 回 `error`。而 `PriceLadder`(主要下單介面)
**完全不讀 `useCapitalStatus()`**。

### D8-07 【high】下單鏈零告警通道
`notify_discord` 在 `copycat/capital/` + `capital_api.py` + `audit.py` 下 **0 個 caller**。
系統有完整的 Discord 基礎設施且訊號那邊已在用。動錢的那一半一格都沒接。

### D8-08 【high】`/api/health` 不含 capital 任何一格;全系統零 metric endpoint
`app.py:1290-1296` 只回 build 身分(docstring 明寫刻意不含引擎健康度 —— **這個決定
是對的,不要破壞**)。`/api/capital/status` 只有
`status / env / account_masked / futures_account_masked / order_enabled` 五格,
沒有 `positions_seeded`、沒有 `reply_last_seen`、沒有佇列深度、沒有任何延遲。

### D8-09 【high】審計時戳只到秒 → 現有 499 對只能給「92.4% < 1 s」
`client.py:336` `timespec="seconds"`。本輪只能靠「跨秒界機率 = 延遲秒數」的相位均勻
假設推出 mean ≈ 76 ms。**p50 / p95 永遠量不出來。**
而埋儀器的成本已量:6 × `perf_counter_ns` = **0.4 µs**,是審計寫入(204 µs)的 0.2%。

### D8-10 【medium-high】關機時 COM 卡在寫入 → 後置審計永遠不寫
`client.py:712-719` 的 `join(timeout=5.0)` 逾時不 raise(刻意),process 隨即退出,
daemon 執行緒被殺。單送出去了,審計檔只有前置那一行。**這是唯一不可重建的紀錄。**

### D8-11 【medium-high】關機時 `_cmd_q` 殘留的寫入命令會被送進市場
`close()` 把 `None` 放到 FIFO **尾端**,`_run` 依序取,`None` 之前的命令照 `fn()` 執行。
包含 10 秒前已被 HTTP 端放棄的那些(FM-04 的無 TTL 問題,以關機為觸發)。
`_drain_pending` 只在 `finally` 跑,已經來不及。

### D8-12 【medium】`capital.close()` 走共享池 → 池飽和時關機段一步都跑不到
`app.py:1254` `asyncio.to_thread(capital.close)`。而 `close()` 本體只是 `queue.put` +
`thread.join` —— 本來就不需要 thread pool。TC4 半死時 capital 段在 t≈73 s 才進場,
再排隊就直接撞 83 s 的 `taskkill /T /F`。

### D8-13 【medium】58% 的成交吃不到樂觀套用 → 使用者等完整回查鏈
log 實測:`成交樂觀套用部位` 189 次 vs `成交未樂觀套用` **259 次**(257 次 `market=TS`)。
未套用的那些要等 R7 = p50 1.94 s / p95 5.41 s。
`store._apply_fill_locked`(`store.py:332-377`)的早退條件裡,`delta <= 0`(部分成交
未滿張)推測是主因 —— 但 log 沒有分流出原因,**現在分不出來**。
修法(觀測面):`成交未樂觀套用` 那行把實際早退原因印出來(現在是一串「/」分隔的可能性)。

### D8-14 【medium】`PriceLadder`(主要下單介面)完全不讀 capital status
grep `useCapitalStatus` 的讀者:`CapitalOrdersList.tsx:32`(只用 `env === "prod"` 判斷
危險色)、`CapitalPositionsList.tsx:26`、`OrderPanel.tsx:43`(有 `STATUS_BLOCKED` 表
+ `degradedNote`)。**`PriceLadder.tsx` 一個都沒有。**
後果:`status=error`(FM-09 / COM 執行緒死)時閃電梯照樣可按,使用者按了才吃 503。

### D8-15 【medium】`OnNewData` 吞例外 = 永久掉一筆委託/成交,`fills` 不可重建
`com.py:281-288`。docstring 自己寫了「這代表一筆委託/成交回報被丟棄,委託面板會跟市場
脫節」。掉一筆成交的連鎖後果:`fills` 少一筆(圖上成交點少一個)、`today_qty` 算錯
→ **當沖稅減半的判準錯** → 打平線錯。而部位可以靠回查鏈自癒,**`fills` 不能**
(它只由回報累積,`store.py:632` 的註解說明重播會重建 —— 但前提是有重播)。
prod 0 次,機制為真。

### D8-16 【medium】幫浦圈例外的 `time.sleep(1.0)` 佔住唯一的送單通道,且 `status` 不降
`client.py:791-793`。持續性故障時每圈睡 1 秒 = 送單命令最壞等 1 秒才被 `get()` 取走,
而 `self._status` 仍是 `ok`(例外被吞)→ 前置檢查放行 → 使用者只看到按鈕轉圈。
prod 0 次(見 B10 F-03 的修法:退避改旗標,`get()` 照跑)。

### D8-17 【low-medium】審計只 `flush()` 不 `fsync()`
`audit.py:36`。本輪實測:persistent handle + `os.fsync` = **0.313 ms**,現況
mkdir+open+write+flush+close = **0.204 ms**。**只貴 0.11 ms 就換到真落盤**
(= S9 端到端 76 ms 的 0.14%)。
⚠ 落地前要量 `CAPITAL_AUDIT_DIR` 實際磁碟的 fsync p99(防毒 / OneDrive)。

### D8-18 【low】正常關機與真故障印同一行 ERROR
`client.py:838` `logger.error("capital-com 執行緒結束(status→error)")` —— 44 次命中
裡 11 次是 init 失敗、33 次是正常關機。事後 grep 分不出來,必須看上一行。
修法:收到 `None` 而結束的路徑印 INFO「capital-com 執行緒正常收尾」。

### D8-19 【reverse / 不要動】送單方向 22 天零事故 —— 先加偵測,不要先加複雜度
536 筆寫入:0 逾時、0 late、0 審計失敗、0 COM 例外、0 執行緒異常終止、
0 `_drain_pending`、0 回呼例外。
B10 列的「無 TTL」「無冪等鍵」「跨 apartment 呼叫」**機制全部為真,但發生率是 0**。
**不要**為了這些先做大改動(改非同步送單、重寫 store 快照化)。順序應該是:
先埋儀器 + 告警(讓第一次發生時能被看見)→ 再按實際發生率決定要不要修機制。
唯一例外是 D8-11 / D8-12(關機那兩條),因為它們的成本是十行、而後果是真錢。

### D8-20 【reverse / 已修】1068 市價單價格欄 bug 已經修好,不要重開
code 1068(`ORDERPRICE_SHOULD_BE_ZERO`)7 筆**全部在 2026-08-24 一天**。
`mapping.py:256` 現在是 `"bstrPrice": "0" if req.price_type == "market" else f"{req.price:.2f}"`,
期權側 `mapping.py:279-285` 是 `"M"`。修好之後再沒出現過。列出來只為完整性。

---

## 10. 這裡不要動(反向結論)

| 位置 | 為什麼不要動 |
|---|---|
| `/api/health` 的「刻意不含引擎健康度」 | `app.py:1291-1295` 的理由是對的:混進來會讓它在引擎壞掉時也答不出版本。capital 指標要另開 endpoint |
| `_execute_write` 的 `shield(fut)` + `_on_late_result` | 這是「單可能已出手」的正確處理。前端**不可以**真的 abort(`useCapital.ts` 現在沒有 AbortController,這是對的) |
| `BalanceCollector` 的欠帳 / abandon / 時間窗 | 它解的是「COM 回呼無查詢識別」這個固有問題,是正確性機器不是效能機器。**1019 storm 不是它的錯**,是 `_maybe_query_balance` 的退避策略 |
| `safety.py` 五個閘 | < 5 µs,是安全邊界。要加的是**新的閘**(本地預檢),不是改快現有的 |
| `_lot_unit` / `_FILL_KIND` / `_CLOSE_MAP` 三張表 | CLAUDE.md §4 的跨檔契約。加儀器時**逐字保留**,不要順手「整理」 |
| `close()` 的 `join` 逾時不 raise | docstring 的理由成立(COM 卡死時不為等它阻塞關機)。要修的是「逾時了要留痕」,不是改成 raise |
| `com.py` 的逐欄 `setattr` | COM struct 是值型別,重用模板的正確性風險遠大於幾十微秒 |
| `_WRITE_TIMEOUT_S` / `_CLOSE_INFLIGHT_S` / `_PENDING_TIMEOUT_S` / `_BALANCE_CHAIN_TIMEOUT_S` | 它們不是效能參數,是**結果未知語意**的參數。要改必須有 prod 實測依據 —— 而現在的 prod 實測說「從沒撞過」 |
| `_audit_lock`(module-level `threading.Lock`) | 序列化是為了防 Windows 並發 append 撕裂行。0.204 ms × 2 行 / 寫入,在 76 ms 的鏈上是雜訊 |

---

## 11. 改造順序

| # | 做什麼 | 為什麼排這裡 | 量測判準 | 回退 |
|---:|---|---|---|---|
| **1** | **驗證 FM-01**:`_ReplyEvents` 加掛 `OnSolaceReplyConnection` / `OnSolaceReplyDisconnect`,**只印 log** | 這是唯一一條「偵測器可能已經死掉」的路徑,而且驗證成本是兩個空方法。在補別的儀器之前必須先知道回報通道的真相 | 下次啟動 `grep -E "SolaceReplyConnection\|Capital reply connected" logs/server-*.log` **恰一行**。若 Solace 那支印出來 = FM-01 確認,接第 2 步;若 `OnConnect` 印出來 = 前提被推翻,本項結案 | 刪掉兩個方法。零行為改動 |
| **2** | **分段時戳 + `client_order_id` + `ts` 改毫秒**(`_execute_write` 五個 `perf_counter_ns`,`_ComCall` 回傳擴成三元組把 `com_ns` 帶回) | 沒有它,後面每一條改動都是盲改。成本已量 = 0.4 µs | 盤後 `jq '.lat_us.total' data/audit/capital-$(date +%Y%m%d).jsonl` 出得了 p50/p95/p99;`lat_us.com` + `lat_us.queue_and_com` 兩格能把 S5 / S6 分開;審計行從 156 → ~289 bytes | 拿掉 `lat_us` 鍵。審計格式是**新增欄不改欄**,離線讀者不受影響 |
| **3** | **`/api/capital/metrics`** + `/api/capital/status` 加 `positions_seeded` / `reply_last_seen_ts` / `com_thread_alive` | 把第 2 步的 ring buffer 暴露出來,順便把 FM-06/07/08 的計數器一起接上 | `curl localhost:8721/api/capital/metrics` 回得出 `write.p50_us` / `reject.by_code` / `balance_chain.1019_count` / `positions.avg_source_null_count`;`/api/health` 的輸出**逐字不變** | 刪 route。零前端依賴(新開的,沒有讀者) |
| **4** | **Discord 告警**:`_set_status` 轉 error/degraded、`_init_com` 失敗、逾時/late、連續 N 筆同碼拒單、回查鏈連續 M 次失敗。沿用 `notify.py`(URL 未設 no-op),加 per-事件節流 | 前三步讓事情看得見,這一步讓它**主動找上人**。下單是動錢的,不該比訊號晚 | 人為讓 `CAPITAL_ORDER_ENABLED=false` 之外的路徑觸發一次(例如關掉網路讓登入失敗)→ Discord 收到一則;同一事件 60 s 內第二次**不**再發 | 拿掉 caller。`notify.py` 本身 never-raise |
| **5** | **關機兩洞**:`close()` 先 drain 再 put None(D8-11);`capital.close` 不走 `to_thread`(D8-12);逾時時寫一行 `shutdown_pending` 審計(D8-10) | 十行內、零新相依,而後果是真錢。放在告警之後是因為前四步不改行為,這一步改 | `pytest tests/server/test_shutdown_budget.py tests/server/test_boot_window.py -q` 全綠(**`TC4_LANE_DEPTH` 不應需要改** —— 若紅了代表 lane 形狀認定與我推斷不同,停下來重看);關機 log 出現「關機 capital 段開始 / 耗時」且 `_cmd_q` 深度印 0 | git revert。`shutdown_budget` 的常數一個都沒動 |
| **6** | **專用審計 executor**(`ThreadPoolExecutor(max_workers=1, thread_name_prefix="capital-audit")`)+ 暴露 `queue_depth` | 解 D8-02。放在儀器之後,是因為第 3 步的 `queue_depth` 正是這一步的驗收指標 | 重跑 `d8-bench-exec.py` 的變體:佔滿預設池 20 條 → 送單前置審計 probe 仍 < 1 ms(現況 ≥ 1004.9 ms);`/api/capital/metrics` 的 `audit_pool.queue_depth` 盤中恆 0 | 改回 `asyncio.to_thread`。⚠ 新 executor 要在 `close()` 裡 `shutdown(wait=True)`,進關機預算 —— 但它是 1 worker × 0.2 ms,可忽略 |
| **7** | **persistent handle + `os.fsync`**(`audit.py`) | 實測只貴 0.11 ms 換到真落盤。與第 6 步同一個檔案區域,一起做省一次 review | 先量 `CAPITAL_AUDIT_DIR` 實際磁碟的 fsync p99(門檻:**< 2 ms**,否則不做);落地後 `d8-bench-audit.py` 重跑,現況 0.204 → 新 0.31 ms 上下;日界換檔正確(跨午夜後新檔有行、舊檔 handle 已 close) | 改回 `append_audit` 原樣。⚠ 關機要 close handle |
| **8** | **本地前置風控**(新 `capital/risk.py` 純函式):當日累計委託名目 vs 249 萬、`positions()` 庫存量 vs 賣出量、`today_qty` vs 可沖銷量、`o.actionable` vs 刪改 | 解 D8-04(9.7% 拒單、86% 本地可擋)。**這是新功能不是優化,要走 `/feat` + grilling**,所以排在純觀測性改動之後 | 上線後 30 個交易日:`reject.by_code` 的 999 佔比從 40/536(7.5%)降到 < 2%;且**零誤擋**(被本地擋下的每一筆都要能對應到一個真實會被券商拒的理由 —— 這條要用歷史審計檔回放驗證,不是上線後才驗) | feature flag(`CAPITAL_LOCAL_RISK=false` 全放行)。閘是純函式,可單獨測 |
| **9** | **runtime kill switch**(`POST /api/capital/safety/halt` + 閃電梯紅色大鈕;`PriceLadder` 補讀 `useCapitalStatus`) | B10 F-11 + D8-14。放在風控之後是因為它們共用同一個「可替換的 `self._safety`」改動面 | halt 後下一筆寫入拿到 `403 ORDER_BLOCKED` 且審計有 `blocked: "halted"` 行;`status=error` 時閃電梯送單鈕 disabled 且文案是 `tradeErrorText("CAPITAL_DOWN")`;resume 後恢復 | halt 只是旗標,resume 即回。⚠ 新錯誤碼碰 CLAUDE.md §4 的 API error shape 契約,`_CAPITAL_ERROR_MAP` 與前端 `parseCapitalError` 要同動 |
| **10** | **回查鏈退避改指數 + 啟動時等 `GetUserAccount` 收完**(D8-03) | 1019 storm 是 73 次實錄的真問題,但它只影響**部位顯示**不影響送單,所以排最後 | 次月 `grep -c "rc=1019" logs/server-*.log` 相對於同樣交易日數下降 > 70%;啟動後 `balance 鏈: 部位落地` 的第一行距 `Capital login + cert OK` **< 3 s**(現況實錄 8–10 s) | 改回固定 1 s。⚠ 不要動 `BalanceCollector` 的欠帳/abandon 邏輯 |

---

## 12. 工具選型

| 工具 | 用在哪 | 為什麼 | 代價 | 結論 |
|---|---|---|---|---|
| `time.perf_counter_ns()` + `collections.deque(maxlen=1024)` | 分段時戳 + metric ring | stdlib。實測 6 次呼叫 0.4 µs = 審計寫入的 0.2% | 零 | **建議導入(最優先)** |
| `concurrent.futures.ThreadPoolExecutor(max_workers=1)` | 專用審計池 | 解 D8-02 的無上界排隊。stdlib | 關機要 shutdown(進預算,但 1 worker × 0.2 ms 可忽略) | **建議導入** |
| persistent file handle + `os.fsync` | `audit.py` | 實測 +0.11 ms 換真落盤 | 管日界換檔 + 關機 close;fsync 尾巴受磁碟/防毒影響 | **有條件導入**:先量目標磁碟 fsync p99 < 2 ms |
| `copycat.notify.notify_discord`(**已在庫內**) | 下單告警 | 零新相依,never-raise、URL 未設 no-op、429 重試已寫好 | 需要一張節流表(訊號那邊有現成模式) | **建議導入** |
| `SKReplyLib_IsConnectedByID`(**已在 typelib**) | 回報連線後備偵測 | 不依賴事件 dispatch,是 FM-01 的保險 | 同步 COM 呼叫,佔幫浦圈;頻率壓到每 10–30 s 一次 | **建議導入(搭配 fix_plan #1 的結果)** |
| `_ISKOrderLibEvents.OnAsyncOrder` / `OnAsyncOrderGW`(**typelib 有**) | 非同步送單(`bAsyncOrder=1`) | 能把 COM 通道從「整個券商往返期間被占住」變成「送出即返回」,直接解 §7 的撞牆順位 #3 | **不是 flag 一翻就好**:要實作新的 sink、要把 `_execute_write` 的 future 改由 `OnAsyncOrder` resolve、要處理「回呼無查詢識別」(與 `BalanceCollector` 同一類問題)。而 prod 22 天零逾時 = 現在不痛 | **不建議現階段**;列為自動化之前的前置條件 |
| `py-spy`(**已裝**) | prod 盤中取樣 `--threads` | 唯一能看到 `capital-com` thread 時間分佈(pump vs 同步查詢 vs 閒置)與預設 executor 佔用數的工具 | 需要權限 | **建議用**(但只是診斷,不進 code) |
| `prometheus_client` | metric 格式 | — | 新相依 + 額外 endpoint;本機單人用 | **不建議**:stdlib ring buffer + 一支 JSON endpoint 就夠 |
| `orjson` / `msgspec` | 審計序列化 | — | 實測 `json.dumps(審計行)` = **0.0019 ms**,佔 S9 的 0.0025%。換掉毫無意義 | **不建議** |
| `aiofiles` | 審計 async 寫入 | — | 內部也是丟 thread pool,**不解 D8-02**,只多一層抽象 | **不建議** |
| `numpy` / `polars` / `pyarrow` | — | — | 這個區塊零數值批次運算,全是 dict / 字串 / dataclass | **明確不建議** |
| `logging.handlers.QueueHandler` | prod log | B10 實測檔案那半 0.0136 ms,不是問題 | 弱化 `_Tee` 的「crash 當下已落盤」設計 | **不建議**(除非先量出真 console 很貴) |

---

## 13. Open questions

1. **`OnSolaceReplyConnection` / `OnSolaceReplyDisconnect` 是不是真的在送?**(fix_plan #1
   的兩個空方法一次啟動就有答案)如果兩對都不送,那回報連線狀態只能靠
   `SKReplyLib_IsConnectedByID` 輪詢。
2. `pythoncom.PumpWaitingMessages()` 在開盤 `ConnectByID` backlog 重播時的耗時?
   決定 S5 的實際大小,也決定「寫入優先權」(B10 F-04)值不值得。
3. `SendStockOrder` 的真實分佈(不是本輪從跨秒率推的 76 mean)?fix_plan #2 落地後
   第一天就有。
4. **58% 成交不樂觀套用的實際原因分流**:是 `delta <= 0`(部分成交未滿張)、
   `_FILL_KIND` miss、還是 `not _positions_seeded`?現在 log 只印一串可能性。
5. `CAPITAL_AUDIT_DIR` 實際落在哪顆磁碟、有沒有防毒即時掃描?決定 fix_plan #7 做不做。
6. 群益「網路單交易額度 249 萬」是**當日累計委託名目**還是**未成交委託名目**還是
   **成交金額**?決定本地閘要累計哪一個量。這個必須問券商或用歷史審計檔回放驗證,
   猜錯會誤擋真單。
7. 使用者對「緊急停止」的期待:全停 / 只停新倉 / 只停某個標的?決定 fix_plan #9 的粒度。
8. 自動化之後的目標送單頻率是多少?(§7 的撞牆順位在 0.5 fills/s 就開始,這個數字
   決定要不要先做非同步送單)
9. `Capital reply: KeyNo=… 尾欄序號=… 不同(預約單?)` 330 筆 —— 這條 WARNING 的判準
   已與現實脫節(docstring 的推論基礎只有 16 筆實錄)。是真的有 330 筆預約單,還是
   判準錯了?這會影響 `store` 以 `seq_no` 為鍵的正確性。
