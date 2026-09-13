# X3-concurrency —— copycat 併發模型 / GIL / 鎖競爭全庫稽核

> 範圍:`copycat/` 全庫 + `run.ps1` + `copycat/server/__main__.py` + `spikes/TCPY/tcoreapi_mq.py`
> (後者是 gitignored 的第三方 wrapper,但它在 process 內開執行緒、持全域鎖,不看它等於拓撲圖缺一角)。
> 量測環境:Windows 11、CPython 3.13.13(**GIL 啟用**,`Py_GIL_DISABLED=0`)、16 邏輯核、本機 venv。
> 所有 µs / ms 數字都是本次實跑 `.venv\Scripts\python.exe` 微基準的結果(腳本留在
> `scratchpad/bench*.py`),不是估算;估算的地方我會明講「推測」。

---

## 0. 一句話結論

**這個 process 的效能天花板是「一條 asyncio event loop 執行緒」,而它的 IO 天花板是
「每條 TC4 session 只有一顆 REQ socket + 一把 `api.lock`」。**

- 所有市場資料的解析、狀態機推進、訊號判定、快照組裝、JSON 序列化**全部擠在 event loop
  那一條執行緒上**,實測單筆成交 tick 要吃掉 **165 µs**、單筆純簿更新 **50 µs**,而
  `vol_burst` 訊號規則是 **O(窗內 tick 數)**,成本**隨 tick 率平方成長**(3 tps → 35 µs;
  10 tps → 106 µs;30 tps → 309 µs,同一檔同一條規則)。
- 91 個 `asyncio.to_thread` 呼叫點共用**同一個** default `ThreadPoolExecutor`(本機 20 worker),
  但其中絕大多數最後都排隊在**同一把 `api.lock`** 上 —— `Semaphore(4)`、20 個 worker
  都是假的平行度。
- 併發**正確性**其實寫得非常紮實(鎖序有文件、cancel 路徑有分支、queue 有背壓政策、
  關機預算三方同源)。這份稽核找到的幾乎都是**吞吐 / 延遲**問題,不是資料競爭問題。

---

## 1. 併發拓撲圖

### 1.1 執行緒清單(prod 全開、150 檔自選)

```
process(python -m copycat.server)
│
├─ MainThread ─ uvicorn ─ asyncio.ProactorEventLoop        ← 一切的瓶頸
│     (uvicorn 0.51 / loops/asyncio.py:asyncio_loop_factory:
│      sys.platform=="win32" and not use_subprocess → asyncio.ProactorEventLoop)
│
├─ TC4 session × 5(txo / stock / index / futures / corr),每條 3 個 Python 執行緒:
│    ├─ tc4.py:1185  threading.Thread(_listen_loop, daemon)
│    │      自建 zmq.Context() + SUB socket,RCVTIMEO=1000ms
│    │      每則:recv → [:-1].decode → find(":") → json.loads → _note_push
│    │             → call_soon_threadsafe(_handle_quote)
│    ├─ tc4.py:638   threading.Thread(_heal_loop, daemon)   零推播自癒 watchdog
│    │      self._stop.wait(heal.poll_secs) 週期喚醒;命中時持 self._lock 走 REQ
│    └─ spikes/TCPY/tcoreapi_mq.py:279  KeepAliveHelper.ThreadProcess(daemon)
│           **另一顆** zmq.Context() + SUB socket,連的是**同一個 SubPort**、
│           SUBSCRIBE "" → 收到與 listener 完全相同的每一則推播,
│           對每則跑 re.search('{"DataType":"PING"}') 只為了找 PING,
│           命中才 objZMQ.Pong() → 取 **api.lock**(= 「毒鎖」的來源)
│
├─ ZMQ IO 執行緒(pyzmq / libzmq 原生,每個 zmq.Context 預設 1 條)
│    QuoteAPI.context × 5 + listener ctx × 5 + KeepAlive ctx × 5 ≈ 15 條
│    (原生執行緒,recv 時釋放 GIL;但 wakeup 仍要搶 GIL 把資料交回 Python)
│
├─ capital-com(client.py:709,threading.Thread daemon,name="capital-com")
│    **COM STA apartment**:pythoncom.CoInitialize() 後所有 SKCOM 呼叫只能在這條上跑。
│    迴圈 = _pump_once() + self._cmd_q.get(timeout=0.05) → 20 Hz 忙輪詢
│
├─ threading.Timer(stock_source.py:642)—— **一個 code 一條執行緒**
│    `_arm_health_check` 每次訂閱 / 每輪退避都 `threading.Timer(...).start()`。
│    150 檔自選開機 = 瞬間建 150 條(各睡 10 s 後死),退避 10→20→40→60 s 再各建一條。
│
└─ asyncio default ThreadPoolExecutor(懶建立,max_workers = min(32, cpu+4) = **20**)
     91 個 to_thread 呼叫點全部共用這一個池:TC4 歷史回補 / 訂閱 / FinMind urllib /
     jsonl 落檔 / 審計落檔 / capital COM join …
```

穩態約 **50 條 OS 執行緒**,其中**會搶 GIL 的 Python 執行緒約 16–36 條**
(1 loop + 5 listener + 5 healer + 5 KeepAlive + 1 COM + 執行中的 executor worker)。

### 1.2 asyncio task 清單(常駐)

| Task | 建立點 | 週期 / 存活 | 職責 |
|---|---|---|---|
| `_boot_all` | `app.py:1143` | 一次性,關機 cancel | 引擎依序啟動 |
| `_calendar_crosscheck` | `app.py:921` | 一次性 | 日曆 vs DK 交叉檢查(只產一行 log) |
| `EngineRuntime._consume` | `engine.py:189` | 常駐 | TXO tick queue 消費 + 自癒輪詢(0.05 s timeout) |
| `StockEngine._backfill_worker` | `stock_engine.py:415` | 常駐 | **單工**回補(一次一檔) |
| `StockEngine._flush_watchlist_loop` | `:416` | 1 s | 側欄 quote 節流合併 |
| `StockEngine._retry_subscribe_loop` | `:417` | 10 s | 訂閱失敗重試 |
| `StockEngine._checkpoint_loop` | `:419` | 60 s | 換日 stage1 武裝 |
| `StockEngine._resubscribe_all` | `:946` | rollover 時 | 全量重掛 |
| `IndexEngine._mis_loop` | `index_engine.py:262` | `poll`(5 s) | 櫃買 MIS poll |
| `IndexEngine._broadcast_loop` | `:263` | `throttle`(1 s) | 指數 WS 廣播 + 分時自癒 watchdog |
| `IndexEngine._rollover_loop` | `:265` | 週期 | 換日 |
| `IndexEngine._retry_loop` | `:350` | 退避 | 1K 回補重試 |
| `FuturesEngine._resub_loop` | `futures_engine.py:225` | `resub_interval` | 訂閱重試 |
| `CorrelationEngine._run` | `corr_engine.py:156` | `tick_secs`(1 s) | 三窗 Pearson + 江波圖 |
| `CorrelationEngine._resub_loop` / `_backfill_river` / `_backfill_retry` | `:155/159/419` | 週期 / 一次性 | |
| `SignalHub._jsonl_worker` | `signal_hub.py:536` | 常駐 | jsonl 落檔(to_thread) |
| `SignalHub._basis_worker` | `:537` | 常駐 | CDP 基準 sweep(逐檔 0.2 s gap) |
| `SignalHub._discord_worker` | `:539` | 常駐 | Discord 批次送出 |
| `SignalHub._policy_outcome_worker` | `:549` | 每日 13:40 | T+1/T+2 回填 |
| `BreadthEngine._poll_loop` | `breadth_engine.py:259` | 10 s | FinMind 全市場家數 |
| `BreadthEngine._compute_streaks_loop` | `:672` | EOD | 連板數 |
| `ScreenEngine._loop` | `screen_engine.py:120` | 每日 08:00 | 盤前篩選 |
| `DiscordBot.client.start` | `discord_bot.py:487` | 常駐 | discord.py gateway(同一條 loop) |
| WS `_send`/`_recv`/`_beat` | `ws.py` | 每條連線 3 個 | fanout / 斷線偵測 / 10 s 心跳 |

**每條瀏覽器 WS 連線 = 3 個 task**。8 條 WS endpoint × 3 分頁 = 最多 72 個常駐 task
只為了收送訊息,其中 1/3 是每 10 秒醒一次的心跳 timer。

### 1.3 `call_later` / `call_soon_threadsafe`(執行緒 → loop 的跨界點)

| 位置 | 種類 | 頻率 |
|---|---|---|
| `stock_engine.py:1150` `_on_raw_threadsafe` | threadsafe | **每則個股推播**(最熱) |
| `engine.py:365` `on_tick` | threadsafe | 每則 TXO tick |
| `futures_engine.py:565` / `index_engine.py:420` / `corr_engine.py:262` | threadsafe | 每則期貨 / 指數 / 相關腿推播 |
| `capital/client.py:826, 856` | threadsafe | 每筆下單結果 / drain |
| `app.py:942` capital 廣播 | threadsafe | 每筆回報 |
| `stock_engine.py:1341` `_tick_flush_timer` | call_later 0.1 s | 逐筆打包 |
| `futures_engine.py:653, 694` `_flush_timer` | call_later 0.1 s | 期貨五檔打包 |
| `stock_engine.py:1509` 回補逾時重排 | call_later | per code |
| `signal_hub.py:875` basis 重試 | call_later 30 s | per (code, date) |

### 1.4 鎖清單

#### threading 家族

| 鎖 | 位置 | 保護什麼 | 最壞持有時間 | 風險 |
|---|---|---|---|---|
| **`api.lock`** | `spikes/TCPY/tcoreapi_mq.py:11` | 那條 session 的**唯一 REQ socket** | 一發 REQ 的 RCVTIMEO = **10 s**(`_REQ_TIMEOUT_MS`) | **全庫最大的序列化點**,見 §4 |
| `TC4QuoteSource._lock` | `tc4.py:399` | `_subscribed` 集合 + 重連重掛臨界區 | `_check_stale` 內**跨 N 次 REQ**(stock session = 150 檔 × 2 發 = 300 發 REQ)→ 分鐘級 | 期間 `_heal_resub` 全擋;不過那條路本來就要等重連 |
| `TC4QuoteSource._api_lock` | `tc4.py:404` | `_api` / `_session` 指標配對 | `_ensure_connected` 持鎖跨 `Connect()` = 最壞 10 s(有註解明說取捨) | 已知、刻意 |
| `_dk_seq_lock` | `tc4.py:395` | DK 取數序號 dict | µs | 無 |
| `StockQuoteSource._seen_lock` / `_timer_lock` | `stock_source.py:547/557` | 已推播集合 / timer 表 | µs | 無 |
| `CapitalStore._lock` | `capital/store.py:143` | 委託 / 成交 / 部位三張表 | 純記憶體運算,µs~ms | **從 event loop 直接 acquire**(見 F-09) |
| `_audit_lock` | `server/audit.py:15` | 審計 JSONL append | open+write+flush,ms 級 | 走 `to_thread`,可接受 |
| `_warn_lock` | `trading_calendar.py:97` | 缺年 WARNING 節流 | µs | 無 |

#### asyncio 家族

| 鎖 | 位置 | 臨界區內有沒有 await / 阻塞 IO |
|---|---|---|
| `StockEngine._pool_lock` | `stock_engine.py:359` | **逐檔取鎖**(N111 已優化),鎖內有 `await to_thread(subscribe)` → 單檔最壞 10 s |
| `SignalHub._rules_lock` | `signal_hub.py:392` | 鎖內 `await to_thread(save_rules)` |
| `WatchlistService._lock` | `watchlist_service.py:70` | **鎖內是同步檔案 IO**(`_commit` → `load_watchlist` / `save_watchlist`,**沒有 to_thread**)→ 直接卡 loop |
| `StkfutCatalog._lock` | `stkfut_catalog.py:41` | 鎖內 `await to_thread(QUERYALLINSTRUMENT)`,實測 1.93 s |
| `oi_levels._lock` | `oi_levels.py:128` | per-loop 單飛;鎖內 FinMind to_thread |
| `ws.relay send_lock` | `ws.py:260` | 只包單次 `await send_json`(註解明確要求不得包迴圈)|
| `app.overlay_sem = Semaphore(4)` | `app.py:547` | 節流 overlay 取數,見 F-02 |

**鎖序**:`tc4.py` 的 docstring 明文規定 `self._lock → _api_lock → api.lock`,且說明全檔無反向路徑
(`_req` 的兩處 `_dispose` 都在 `finally` 釋鎖之後)。我逐條讀過,**沒有找到反轉**。
`_dispose` 刻意不取 `self._lock` 的理由也有文件。**死鎖風險評估:低**。

### 1.5 佇列與背壓

| 佇列 | maxsize | 滿了怎麼辦 | 評價 |
|---|---|---|---|
| `WsBroadcaster` per-client(`ws.py:127`) | stock **1000** / 其餘 **500** / index·breadth **32** | 丟最舊保最新 + 60 s 節流 WARNING + 窗到期結算 | 政策正確,可觀測性完整 |
| `EngineRuntime._queue`(`engine.py:86`) | **10000** | `queue_dropped += 1` + WARNING;清空後 `_maybe_self_heal` 重跑交接補回 | 設計完整 |
| `SignalHub._jsonl_queue` | **1000** | `_put_drop_oldest` + 每 N 筆一則 WARNING | OK |
| `SignalHub._discord_queue` | **100** | 同上 | OK |
| `StockEngine._backfill_jobs`(`:304`) | **無界** | 無 | 見 F-11 |
| `SignalHub._basis_jobs`(`:394`) | **無界** | 無 | 見 F-11 |
| `CapitalClient._cmd_q`(`client.py:211`) | **無界** | 無(但生產者是人手下單,量本來就小) | 可接受 |

---

## 2. 資料流(市場資料 → 瀏覽器)

```
TC4 桌面 app
   │  ZMQ PUB,tcp://127.0.0.1:<SubPort>
   ├──────────────┬──────────────────────────────┐
   │              │                              │
   ▼              ▼                              ▼
KeepAlive thread  _listen_loop thread          (其餘 4 條 session 同構)
(收全部訊息,      recv → decode → find(":")
 regex 找 PING,   → json.loads(4.9 µs)
 命中才 Pong,     → _realtime_msg → _note_push(自癒時鐘)
 Pong 取 api.lock)→ handle_raw → self._on_message(quote)
                       │
                       │ loop.call_soon_threadsafe(8.6 µs,Proactor 自管道 write)
                       ▼
              ╔═══════════════════════════════════════════════════╗
              ║   E V E N T   L O O P  (單一執行緒,全部在這)      ║
              ║                                                   ║
              ║  StockEngine._handle_quote                        ║
              ║   ├ parse_stock_realtime .................  23.3 µs║
              ║   ├ state.update_book / update_meta / ingest 4.0 µs║
              ║   ├ signal_hub.on_tick → 7 個 rule slot          ║
              ║   │    各自一顆 SignalDetector、各自一份 300 s 窗  ║
              ║   │    ..............  69 / 136 / 349 µs(3/10/30 tps)║
              ║   ├ signal_hub.on_book → evaluate_book × 7  26.4 µs║
              ║   ├ _pending_ticks.append + call_later(0.1s)      ║
              ║   └ _publish(book) → WsBroadcaster.publish        ║
              ║                                                   ║
              ║  其他也搶這條執行緒的:                             ║
              ║   · /api/stock/group-state:150 檔 light_snapshot  ║
              ║       = 20.9 ms + starlette json.dumps 43.6 ms    ║
              ║       → 單次請求 ≈ **65 ms 的 loop 停擺**          ║
              ║   · breadth._apply:compute_breadth 2000 列 5.7 ms ║
              ║       + _save() 同步寫檔,**每 10 秒一次**         ║
              ║   · watchlist_service._commit:同步讀寫自選檔       ║
              ║   · corr._run 每 1 s 三窗 Pearson × 11 腿          ║
              ║   · index._broadcast_loop 每 1 s                  ║
              ║   · 每條 WS 的 json.dumps + send                  ║
              ╚═══════════════════════════════════════════════════╝
                       │ WsBroadcaster.publish → per-client asyncio.Queue
                       ▼
                 relay._send → websocket.send_json(starlette json.dumps)
                       ▼
                  瀏覽器
```

反向(REQ 路徑,所有「問 TC4 要資料」的動作):

```
route / worker  ──►  asyncio.to_thread  ──►  default ThreadPoolExecutor(20 worker)
                                                  │
                                                  ▼
                                    TC4QuoteSource._req
                                                  │
                                         api.lock.acquire(timeout=12s)   ◄── 單點序列化
                                                  │
                                     socket.send_string + socket.recv()
                                        (RCVTIMEO = 10 s)
```

同一條 session 上競爭這把鎖的生產者(以 stock session 為例):

- 開機 150 檔 `SUBQUOTE`
- `_backfill_worker` 逐檔當日 TICKS 回補(`_collect_history`:1 發 SubHistory + N 發 GETHISDATA 分頁)
- `SignalHub._basis_worker` 逐檔 DK(150 檔 × 0.2 s gap ≈ 30 s 一輪,每檔內部又是多發 REQ)
- `/api/stock/overlay/{code}`(CDP/MA)—— 每張群組卡片一發
- `/api/stock/bars/{code}`
- `_heal_loop` watchdog 重掛、`threading.Timer` 健檢重掛
- rollover 全量 UNSUB + SUB(300 發)
- `list_stock_futures`(Fut2 目錄,**單發秒級且全程持鎖**,`tc4.py:1136` 有明確警告)
- KeepAlive 的 `Pong`

---

## 3. 熱路徑逐條(附實測)

| # | 熱路徑 | 位置 | 頻率 | 每次做什麼 | 實測 |
|---|---|---|---|---|---|
| H1 | 個股 REALTIME → loop | `tc4.py:1225` `_listen_loop` → `stock_source.py:925` `handle_raw` → `stock_engine.py:1147` | 每則推播(開盤 150 檔簿更新 + 成交,**百~千則/s**,未實測) | decode + json.loads + `_note_push` + threadsafe hop | json.loads **4.9 µs**;hop **8.6 µs** |
| H2 | `_handle_quote` 解析 | `stock_engine.py:1187` → `stock_models.py:188` | 同上 | `_parse_levels`×2 + 8 個 `to_milli` + `_taipei_time` | **23.3 µs**(`_taipei_time` 7.6、`_parse_levels` 3.1×2) |
| H3 | 訊號評估(成交) | `signal_hub.py:598` → `signal_state.py:292` ×7 slot | 每筆**成交** | 7 顆 detector 各自 append/trim 300 s 窗 + 六個 `_eval_*` | **69 / 136 / 349 µs**(3 / 10 / 30 tps) |
| H3b | ↳ `vol_burst` 單條 | `signal_state.py:658` `sum(qty for _ts,_price,qty in window)` | 同上 | **O(窗內 tick 數)**;窗 = `surge_window_secs` **300 s** | **35 / 106 / 309 µs** |
| H4 | 訊號評估(簿) | `signal_hub.py:616` `on_book` ×7 slot | 每則推播(含純簿更新,量遠大於成交) | `_eval_limit_tick` 之外全早退 | **26.4 µs** |
| H5 | 逐筆打包 flush | `stock_engine.py:1782` + `ws.py:69` | 0.1 s(有 pending 才醒) | 組一則 `ticks` + per-client put_nowait;每 client `json.dumps` | dumps(30 筆)**38.8 µs** |
| H6 | 群組快照 | `app.py:1736` → `stock_engine.py:799` → `stock_state.py:light_snapshot` | 每分頁 **60 s** 一發,最多 150 檔 | 150 份 minutes(~270 格)+ vp(~400 檔位)dict 重建 + 整份 JSON | **20.9 ms + 43.6 ms = 65 ms loop 停擺** |
| H7 | 家數帶 | `breadth_engine.py:377` `_run_cycle` → `_apply` | **10 s**(09:00–13:40) | `assemble_universe` + `compute_breadth` 2000 列 + 同步 `_save()` 寫檔 | **0.56 + 5.71 ms + 檔案 IO** |
| H8 | TXO tick 消費 | `engine.py:373` `_consume` | 每則 TXO tick | `asyncio.wait_for(queue.get(), 0.05)` 每筆建一顆 Timeout + TimerHandle | wait_for 比裸 get **+2.5 µs/tick** |
| H9 | 相關係數 / 江波圖 | `corr_engine.py:223` `_run` → `tick_once` | **1 s** | 11 腿 × 三窗 Pearson(純 Python) | 未測(推測 < 1 ms) |
| H10 | COM 幫浦 | `capital/client.py:806` | **20 Hz** | `pump()` + 3 個 collector poll + 2 個 watchdog | 未測;COM STA 專屬執行緒,不佔 loop |
| H11 | KeepAlive 重複收訊 | `spikes/TCPY/tcoreapi_mq.py:287` | **每則推播 ×5 session** | 第二次 recv + decode + `re.search` | decode 0.23 + regex **0.59 µs**(小,但是白工 + 一次 GIL 喚醒) |

**離線 / 不在熱路徑**(確認過 server 從不 import):`copycat/backtest/*`(fade_cells 2007 行、
fade_pipeline 735 行)、`copycat/replay/*`、`copycat/data/import_neigui`。這些只從
`python -m copycat <cmd>` 進來,**跑在另一個 process**,不會跟 tick 搶 GIL。

---

## 4. Findings

### X3-01 【critical】`vol_burst` 每 tick 掃整個 300 秒窗,成本隨 tick 率平方成長,而且跑在 event loop 上

**位置**:`copycat/live/signal_state.py:658`

```python
window_min = self._cfg.surge_window_secs / 60
window_vol = sum(qty for _ts, _price, qty in window)   # ← O(len(window)),每 tick 一次
ratio = window_vol / (avg_per_min * window_min)
```

`surge_window_secs` 預設 **300.0**(`signals_config.py`),窗是 `deque[(mono, price, qty)]`。
`window` 長度 = 該檔最近 300 秒的 tick 數,所以 `sum()` 的成本與 tick 率成正比,而它
**每 tick 跑一次** → 總成本 ∝ tick 率²。

實測(同一檔、單一 `vol_burst` 規則、穩態窗):

| tick 率 | 窗長 | `evaluate` 耗時 | 該檔每秒燒掉的 loop 時間 |
|---|---|---|---|
| 3 /s | 901 | 35.0 µs | 0.11 ms |
| 10 /s | 3,001 | 105.9 µs | **1.06 ms** |
| 30 /s | 9,001 | 309.2 µs | **9.3 ms** |

30 tps 只是台積電 / 熱門攻板股在開盤十分鐘的常態。**一檔就吃掉 1% 的 core**,而
event loop 只有一條。十檔同時活躍 = 93 ms/s = **9.3% 的 loop 全被這一行吃掉**,
而這期間所有 WS 推送、所有 REST 回應、所有其他 tick 都在排隊。

**修法**(S,行為完全不變):維護一個**增量總和**。`window` 已經是 deque 且只在
`evaluate` 一處 append / popleft(`signal_state.py:318-321`),把它包成:

```python
window.append((mono, price, tick.qty)); self._wvol[code] += tick.qty
cutoff = mono - self._cfg.surge_window_secs
while window and window[0][0] < cutoff:
    self._wvol[code] -= window.popleft()[2]
```
`_eval_volume` 改讀 `self._wvol[code]` → O(1)。整數加減不會有浮點漂移,結果**逐位元相同**。
`reset_day` / `_drop_code` 一併清。

**風險**:`window` 目前是 `_eval_surge` / `_eval_pullback` / `_eval_volume` 三者共用的
參數物件,新增的總和要與 deque 在**同一處**維護(就是上面那三行),否則會漂。既有測試
(`tests/live/test_signal_state.py` 的 vol_burst 案)是天然的 characterization。
不動任何跨檔契約。

---

### X3-02 【critical】所有 TC4 取數序列化在「一 session 一顆 REQ socket + 一把 `api.lock`」上,`Semaphore(4)` 與 20 個 executor worker 都是假平行

**位置**:`spikes/TCPY/tcoreapi_mq.py:11`(`self.lock = threading.Lock()`)+
`copycat/live/tc4.py:333` `_req`

```python
if not api.lock.acquire(timeout=self._lock_timeout):     # DEFAULT_LOCK_TIMEOUT_SECS = 12.0
    self._dispose(api); raise ConnectionError("TC4 quote api.lock timeout")
try:
    api.socket.send_string(json.dumps(obj))
    message = api.socket.recv()[:-1]                      # RCVTIMEO = _REQ_TIMEOUT_MS = 10_000
finally:
    api.lock.release()
```

同一條 session 上,**同時只能有一發 REQ 在飛**。stock session 的競爭者(§2 列了 8 類)
在開盤前後必然重疊。codebase 自己已經三處記錄過這個病:

- `app.py:127-136`:「配上 route 層 `Semaphore(4)`,四檔這種股號就足以把整個端點凍住
  (head-of-line):進群組時整牆卡(上限 150)的 CDP/MA 全排在後面」
- `tc4.py:1136`:「⚠ **秒級同步呼叫且全程持 session 鎖**(Opt 的同款查詢實測 1.93s)——
  期間這條 session 上的其他 REQ(訂閱 / SubHistory)全部排隊」
- `signal_hub.py:836`:「與主圖回補 / K 線 route 共用同一條 TC4 stock session,連發要讓位」
- `tc4.py:407`(`lock_timeout_secs` 的註解):「三個 REQ 生產者(群組回補 / basis sweep /
  Fut2 目錄)在 boot 必然重疊,**級聯是常態**」

**這不是 asyncio 的問題,是 TCPY wrapper 的協定形狀。** 換 uvloop / winloop / 多執行緒
一點幫助都沒有。

**修法方向**(M~L,要先做 probe):

1. **多開一條「歷史專用」session**。`Connect()` 每次回一把新 `SessionKey` + 新 `SubPort`
   + 新的 REQ socket,所以 N 條 session = N 發並行 REQ。
   歷史(`SUBQUOTE` with `SubDataType=TICKS/1K/DK` + `GETHISDATA`)與 REALTIME 是
   **不同 DataType 的兩把 refcount key**(`tc4.py:_apply_variant` docstring 明說
   「歷史路徑不吃 variant —— 回補窗與 REALTIME 窗是不同 DataType 的兩把鍵」),
   所以歷史 session 與 realtime session 理論上不會互搶 symbol 的上游 feed。
   **但這是假說,不是事實** —— 必須先跑一次受控 probe(見 §8 M4)。
2. 退而求其次:**把 REQ 按優先級排隊**。現在是 `threading.Lock` 的 FIFO/隨機,
   使用者當下在看的那一檔 overlay 會排在 150 檔 basis sweep 後面。
   換成一條 `asyncio.PriorityQueue` + 單一 REQ worker(REQ 本來就只能一發一發送),
   使用者互動優先、背景 sweep 最低。這個改法**不必動 TC4 協定**,只動 `tc4.py` 的
   `_req` 入口與呼叫端的 await 形狀。

**風險**:方案 1 直接踩 CLAUDE.md §8 / `tc4-market-facts` 的兩條硬事實
(「同 symbol 跨 session 只推一邊」、「session reap 會把 refcount key 歸零、帶走
symbol 的上游 feed」)。方案 1 還要同步改 `shutdown_budget.TC4_LANE_DEPTH`
(跨檔契約「關機預算三方同源」,`run.ps1` / `__main__.py` / `app.py` lifespan 三方)。
方案 2 風險小很多,但要重寫 `_req` 的所有 caller(它們現在是同步阻塞形,在 to_thread 裡)。

---

### X3-03 【high】`/api/stock/group-state` 一發 = event loop 停擺 ~65 ms

**位置**:`copycat/server/app.py:1736` → `stock_engine.py:799` `group_snapshot`
→ `live/stock_state.py:light_snapshot`

```python
return {"states": stock.group_snapshot(wanted)}   # app.py:1736,純同步,沒有 to_thread
```
```python
def light_snapshot(self) -> dict:
    return {
        "minutes": self._minutes_payload(),
        ...
        "vp": {str(price): list(cell) for price, cell in sorted(self._vp.items())},
    }
```

實測(單檔 271 個 minute 格 + 400 個 VP 檔位,這是熱門股盤中的實際量級):

- `light_snapshot()` = **139.4 µs** → 150 檔 = **20.9 ms**
- `json.dumps` 那份 payload = 291 µs → 150 檔 = **43.6 ms**(FastAPI 預設 `JSONResponse`,
  也在 loop 上)

合計 **~65 ms**。前端每 60 秒輪詢一次(`useGroupSnapshots`),開兩個分頁 = 每分鐘
兩次 130 ms 的停擺。這段期間所有 tick 在 `call_soon_threadsafe` 的 ready queue 裡堆著。

**修法**(S→M):
1. `group_snapshot` 本身有副作用(`_flush_ticks()` + `_enqueue_backfill`),**不能整段丟
   to_thread**。拆:副作用留在 loop,`light_snapshot` 的組裝與序列化丟 `to_thread`。
2. 更划算:**改用 `orjson` 直接回 `Response(content=orjson.dumps(...), media_type=...)`**。
   orjson 對這種純 int/str 巢狀結構通常比 stdlib `json` 快 3–8×,43.6 ms → ~7 ms。
3. 更根本:這份 payload 一分鐘只變一點點,應該走 **WS delta** 而不是 REST 全量重送。
   但那是 §X 其他區塊的事,這裡只點出。

**風險**:CLAUDE.md §4 的「API error JSON shape」契約規定 `{"detail": {"error": "<code>"}}`;
換 `Response` 時**錯誤路徑仍要走 `HTTPException`**,不可一起換掉。
改序列化不動任何欄位名,前端零改動。

---

### X3-04 【high】每則 TC4 推播一次 `call_soon_threadsafe`,Windows 上是一次自管道 write syscall

**位置**:`stock_engine.py:1147-1150` / `engine.py:361-365` / `index_engine.py:417-420` /
`futures_engine.py:562-565` / `corr_engine.py:259-262`

```python
def _on_raw_threadsafe(self, quote: dict) -> None:
    loop = self._loop
    if loop is not None:
        loop.call_soon_threadsafe(self._handle_quote, quote)   # 每一則推播一次
```

實測(ProactorEventLoop,本機):**producer 側 8.56 µs / 次**,吞吐上限 ~115k hops/s。
(SelectorEventLoop 更慢:11.27 µs。**Proactor 是對的選擇**,不要換。)

Windows 的 `call_soon_threadsafe` 會 `_write_to_self()` 往 socketpair 寫一個位元組去喚醒
IOCP —— 每則推播一次 syscall + 一次 GIL 交接。1000 則/s = 8.6 ms/s 純開銷 + 1000 次
loop 喚醒。

**諷刺的是,這個 codebase 已經在出口端做了打包**(`_flush_ticks` 0.1 s 一則 `ticks`,
CLAUDE.md §4 有整段契約),**但入口端還是一則一 hop**。

**修法**(M):listener 執行緒側加一個 `collections.deque` + 微批次。
`_on_raw_threadsafe` 改成 append 到 deque,只有在「deque 從空變非空」時才發一次
`call_soon_threadsafe(self._drain_raw)`;`_drain_raw` 在 loop 上把整批 pop 出來逐則處理。
deque 的 append/popleft 在 GIL 下是原子的,不必額外加鎖。
批次大小天然自適應:loop 閒時批次=1(延遲不變),loop 忙時批次自動變大(吞吐提升)。

**風險**:`_handle_quote` 的順序語意必須保住(deque FIFO 天然保序)。
`_flush_ticks` 的 0.1 s 打包契約與 `snapshot()` 前必 flush 的不變式(CLAUDE.md §4
「快照與打包的 seq 對齊 = 同一個 race 的兩道閘」)**不受影響** —— 那是出口側,這裡改入口側。
但要注意:`close()` 時 `self._loop = None` 之後 deque 裡的殘留要丟掉,不能重建 loop 參照。

---

### X3-05 【high】`parse_stock_realtime` 每則 23.3 µs,其中 `_taipei_time` 一支就 7.6 µs,而且純簿更新也照付全額

**位置**:`copycat/live/stock_models.py:188`

```python
def parse_stock_realtime(msg, *, trial_windows=TRIAL_WINDOWS):
    book = StockBook(bids=_parse_levels(msg,"Bid","BidVolume"),
                     asks=_parse_levels(msg,"Ask","AskVolume"))     # 3.1 µs × 2
    meta = StockMeta(name=..., ref_milli=to_milli(...), ... )        # 8 × to_milli 0.36 µs
    ...
    time_tp, date_tp = _taipei_time(str(msg.get("PreciseTime","")), str(msg.get("TradeDate","")))   # 7.6 µs
```

實測拆解:總 **23.3 µs** = `_parse_levels`×2 6.2 + `_taipei_time` 7.6 + 8×`to_milli` 2.9 + 其餘 6.6。

`_taipei_time` 走的是 `datetime.strptime` 家族 —— 這是 Python 裡出了名的慢路徑
(格式固定 `YYYYMMDDHHMMSS.fff`,完全可以手切字串 + 一次 `timedelta(hours=8)` 的整數運算)。

`StockMeta` 每則都重建(8 個 `to_milli`),但參考價 / 漲跌停 / 昨收 **一天只變一次**,
`state.update_meta(meta)` 之後也只是覆蓋同樣的值。

**修法**(S):
1. `_taipei_time` 改手切:`int(raw[8:10])` 等 + 預先算好的「+8 小時」跨日規則。
   期望 7.6 µs → < 1 µs。**必須有 golden 對照測試**(現有 `tests/live/test_stock_models.py`
   應該已經有邊界案例,跨午夜 / 跨月 / 跨年那三條要確認)。
2. `meta` 快取:以 `(ReferencePrice, UpperLimitPrice, LowerLimitPrice, YClosedPrice, SecurityName)`
   五個**原始字串**的 tuple 當鍵,值沒變就回上一顆 `StockMeta`(frozen dataclass,可共享)。
   省 8 次 `to_milli` + 一次 dataclass 建構。

**風險**:`_taipei_time` 的 +8 轉換是 `tc4-market-facts` 記錄過的實測事實
(FilledTime/PreciseTime 為 UTC,OpenTime/CloseTime 是交易所當地時間**不轉**)。
手切版要一模一樣地只轉前者。meta 快取要注意 `StockMeta` 是 frozen dataclass
(可安全共享);若哪天變 mutable,快取就會變成跨檔別名 bug。

---

### X3-06 【high】`SignalHub.on_tick` 對每個 rule slot 各跑一次完整 `evaluate`,7 條預設規則 = 7 份重複的窗維護

**位置**:`copycat/server/signal_hub.py:598-614`、`:455-462`

```python
def _make_slot(self, rule: Rule) -> _RuleSlot:
    return _RuleSlot(
        rule=rule,
        detector=SignalDetector(rule_config(rule, self._cfg), now_fn=self._now_fn),  # ← 一規則一顆
        enabled=frozenset({rule["kind"]}) if rule["enabled"] else frozenset(),
    )

def on_tick(self, code, tick, state) -> None:
    ...
    for slot in self._slots.values():
        events = list(slot.detector.evaluate(code, tick, ctx, slot.enabled))   # ← 每 slot 全跑
```

`default_rules` 產出 **7 條**(6 個 kind,`surge_pullback` 兩張卡)。每顆 detector
都維護自己那份 300 秒 `window` deque、自己的 `_lookback`、自己的 `_sweep_group`
—— 內容**完全相同**,因為輸入 tick 相同。

實測 7 slot 合計:**69 µs(3 tps)/ 136 µs(10 tps)/ 349 µs(30 tps)**。
扣掉 `vol_burst`(X3-01),剩下 6 個 slot 各 ~6 µs = 36 µs,其中大部分是
**六份重複的 deque append + trim + `_eval_sweep` 的 lookback 維護**
(`_eval_sweep` 在 `enabled` gate **之前**跑,所以每個 slot 都無條件付)。

**修法**(M):把「共用狀態」(`_window`、`_lookback`、`_sweep_group`、`_prev`)抽成
每 code 一份的 `SharedTickWindow`,detector 只保留自己的判定狀態(`_cooldown`、
`_suppressed`、`_side`、`_latch`、`_pullback`)。`SignalDetector` 的建構子多吃一個
shared window。

**風險**:這是 `signal_state.py` 的核心不變式改寫 —— docstring 明文寫「狀態推進與
事件產出分離(design R2):過 gate 後 `_prev` / `_window` / `_limit_latch` **無條件推進**」。
共用之後「每 slot 各自推進」變「全域推進一次」,**大部分情況等價,但 `_sweep_group.fired`
與 `_pullback` 這類「一波一則」的狀態是 per-rule 的,不可共用**。
`tests/fixtures/sweep_cluster_golden.json` 的 golden parity 與 `tests/test_signal_rules.py::
test_param_specs_parity_with_frontend` 是護欄。**這條我建議排在 X3-01 之後,而且要先寫
characterization 測試**;X3-01 修完之後剩下 36 µs,收益/風險比已經沒那麼好看了。

---

### X3-07 【medium】`BreadthEngine._apply` 在 event loop 上算 2000 列統計 + 同步寫檔,每 10 秒一次

**位置**:`copycat/server/breadth_engine.py:377-394`、`:513`、`:956`

```python
async def _run_cycle(self) -> None:
    rows = await self._fetch_snapshot()          # ← 這段有 to_thread,對
    if rows is not None:
        await self._refresh_maps()
        last_minute = self._apply(rows)          # ← 這段沒有,純同步跑在 loop 上
```
`_apply` → `assemble_universe`(0.56 ms)+ `compute_breadth`(**5.71 ms**,2000 列)
→ `_append` → `_save()`(`breadth_engine.py:956`:`tmp.write_text(json.dumps(payload))`
+ `os.replace`,**同步檔案 IO 在 loop 上**)。

盤中(09:00–13:40)每 10 秒一次 → 每小時 360 次 × ~6 ms + 磁碟 IO。
duty cycle 只有 0.06%,但它是**每 10 秒一發的固定延遲毛刺**,而且落在 tick 最密的時段。

**修法**(S):把 `self._apply(rows)` 整個包進 `await asyncio.to_thread(self._apply, rows)`。
`_apply` 會改 `self._series` / `self._counts` / `self.rows` 等 engine 狀態,
所以要確認**沒有其他 loop 上的讀者會在這期間看到半成品**——
`payload()` 是讀者(`_run_cycle` 尾端 + `/api/breadth/*` route)。最安全的切法:
純函式部分(`assemble_universe` + `compute_breadth` + `_save`)丟 to_thread,
狀態賦值那幾行留在 loop。

**風險**:`_apply` 內有 `self._fail()` 的三條路徑(時刻推不出 / 統計全空 / 例外),
拆的時候三條都要跟著走對。`_save()` 丟到執行緒後要注意與下一輪 `_save()` 的重入
(現在靠 loop 天然序列化);加一把 `asyncio.Lock` 或直接沿用 poll loop 的單工性質即可。

---

### X3-08 【medium】`WatchlistService._commit` 在 asyncio 鎖內做同步檔案讀寫

**位置**:`copycat/server/watchlist_service.py:78-95`

```python
def _commit(self, wl: Watchlist) -> _Pending:
    desired = normalize(wl)
    if desired == self._current_canonical():      # ← load_watchlist:同步 read + json.loads
        return desired, False, None
    saved = save_watchlist(self._path, desired)   # ← 同步 atomic write
    ...
```
呼叫端是 `async with self._lock: pending = self._commit(wl)` —— **整段在 event loop 上**。

`_settle` 的設計非常用心(把 ZMQ 訂閱移出鎖外,避免 Discord interaction 15 分鐘 token
過期),但**檔案 IO 還留在鎖內、留在 loop 上**。自選檔 150 檔 + groups 不大(幾十 KB),
單次大概 < 2 ms,而且觸發頻率低(人手改自選 / nightly 篩選寫入)。

**但 `screen_engine` 的 nightly 寫入會一次寫 ~60 檔進「盤前篩選」群組**,那一發落在
08:00,還沒開盤,無害。真正要小心的是**盤中用 Discord `/watch` 改自選**。

**修法**(S):`_commit` 改 async,兩處檔案 IO 各包一次 `to_thread`。
鎖仍然持有整段(語意不變,那是刻意的 —— 註解說「唯一事實點就是這裡的比對」,
不可拆開否則多一個 TOCTOU 窗)。

**風險**:低。`_commit` 的六個呼叫端都已經在 async 函式裡。

---

### X3-09 【medium】`CapitalStore._lock`(threading.Lock)被 REST route 直接在 event loop 上 acquire

**位置**:`copycat/server/capital_api.py:191, 259, 272, 289` → `copycat/capital/store.py:143`

```python
# capital_api.py(async route 內)
rec = next((o for o in client.store.orders() if o.seq_no == seq_no), None)
...
for o in client.store.orders()      # 每個都 with self._lock:
for f in client.store.fills()
for p in client.store.positions()
```

`store` 的寫入者是 **COM 執行緒**(`_apply_fill_locked` / `set_positions` /
`_on_profit_complete`)。REST route 在 loop 上做 blocking `lock.acquire()`。

臨界區都是純記憶體(建 list、dict 複製),微秒~毫秒級,**目前不是問題**。
但這是一個「等待 COM 執行緒」的同步點:如果哪天 `_apply_fill_locked` 的臨界區變長
(例如加了寫檔),下單面板的 REST 就會直接卡住 event loop,而且**零錯誤訊號**。

**修法**:現在**不必改**。記在 next-time:如果 store 的臨界區內出現任何 IO,
那幾個 route 要立刻改成 `await asyncio.to_thread(client.store.orders)`。
或者更乾淨:store 的讀取面改成「寫入時產生 immutable 快照,讀取面無鎖讀 volatile 參照」
(Python 的屬性讀寫在 GIL 下原子,`self._snapshot = new_tuple` 是安全的發布)。

**風險**:改成無鎖快照要確認寫入端每次都是**整份替換**而不是原地修改。

---

### X3-10 【medium】一個 code 一條 `threading.Timer` 執行緒,150 檔開機瞬間建 150 條

**位置**:`copycat/live/stock_source.py:640-651`

```python
def _arm_health_check(self, code: str, delay: float, *, attempt: int) -> None:
    timer = threading.Timer(delay, self._health_check, args=(code, attempt))   # ← Timer 是 Thread 子類
    timer.daemon = True
    with self._timer_lock:
        old = self._no_data_timers.get(code)
        if old is not None: old.cancel()
        if self._stop.is_set(): return
        self._no_data_timers[code] = timer
    timer.start()          # ← 一次 OS 執行緒建立
```

`subscribe_symbol` 每檔呼叫一次(`no_data_secs` 預設 **10 s**),`_health_check` 的
退避路徑(10→20→40→60 s)每輪再建一條。

150 檔自選 = 開機瞬間 **150 次 `Thread.start()`**(Windows 上每條預設保留 1 MB stack
虛擬位址空間,實際 commit 小得多;但建立 + 排程 + 死亡的成本不是零),而且它們
**在最忙的那 10 秒裡全部同時醒來**、各自可能走 `_heal_resub` 去搶 `api.lock`。

**修法**(S):換成**單一 watchdog 執行緒 + 到期時間堆**。這個檔案裡已經有現成樣板 ——
`tc4._heal_loop` 就是「一條執行緒 + `_heal_next` dict 記下次可試時刻」。
健檢完全可以併進同一條 `_heal_loop`(它本來就每 `heal.poll_secs` 醒一次),
只要保住兩套記帳分開的不變式(`_no_data_attempts`/`_no_data_next` vs
`_heal_attempts`/`_heal_next`,`stock_source.py:545` 的註解明說不可共用退避階梯)。

**風險**:健檢的第一發要在訂閱後恰好 10 s ——併進 poll 迴圈後精度變成 `poll_secs`
(預設多少要查)。`_on_no_data` 的「只在 attempt==1 通報一次」語意必須保住。
`close()` 的兩道防線(timer.cancel + `_stop` 早退)要換成 `_stop` 一道。

---

### X3-11 【medium】兩條無界佇列:`_backfill_jobs` 與 `_basis_jobs`

**位置**:`copycat/server/stock_engine.py:304`、`copycat/server/signal_hub.py:394`

```python
self._backfill_jobs: asyncio.Queue[tuple[str, int]] = asyncio.Queue()   # 無 maxsize
self._basis_jobs: asyncio.Queue[tuple[str, str, bool]] = asyncio.Queue()  # 無 maxsize
```

兩者的消費端都是**單工 worker**,而生產端是多路的:
- `_backfill_jobs` 有 **6 個入列點**(set_main / rollover / reconnect / 漲跌停值變 /
  群組 60 s 輪詢 / 首筆成交 tick),消費是 `_backfill_worker` 一次一檔,
  每檔要走 `_collect_history`(最壞 `BARS_POLL_DEADLINE` = 10 s × 兩段)。
  150 檔 × 10 s = **25 分鐘**才能消化一輪。
- `_basis_jobs` 消費端每檔後面還有 `await asyncio.sleep(basis_gap_secs)` = 0.2 s,
  150 檔 = 30 s 一輪;換日 promote 差集補抓 + 重試會再疊。

現有的 dedup guard(`_backfill_wanted` 的四道、`_backfill_pending` 計數)實務上擋住了
無限膨脹,所以**今天不會爆**。但「無界 + 單工 + 每件最壞 10 s」這個組合沒有任何
上界保證,也**沒有任何佇列深度的可觀測性**(`/api/health` 不含,log 也沒有)。

**修法**(S):
1. 加 `maxsize`(例如 `WATCHLIST_LIMIT * 2 = 300`)+ 滿了記 WARNING 並丟棄最舊,
   沿用 `ws.WsBroadcaster` 已經驗證過的「丟最舊保最新 + 60 s 節流結算」樣板。
2. 更重要:**把佇列深度暴露出來**。`_backfill_worker` 每次取件時,若 `qsize() > N`
   就印一則節流 WARNING —— 現在「回補積壓 20 分鐘」在畫面上只表現為「卡片一直寫回補中」。

**風險**:丟棄回補 job 會讓那一檔當日分時圖缺開盤段,而那正是 `_backfill_gave_up`
分帳(pr-164 F-01)辛苦處理的語意。**建議只加可觀測性,先不加丟棄政策**,
等量測到真的積壓再說。

---

### X3-12 【medium】`EngineRuntime._consume` 每筆 tick 付一次 `asyncio.wait_for` 的 Timeout 物件

**位置**:`copycat/server/engine.py:373-380`

```python
async def _consume(self) -> None:
    while True:
        if self._paused: await asyncio.sleep(0.01); continue
        try:
            tick = await asyncio.wait_for(self._queue.get(), timeout=0.05)   # ← 每筆一次
        except TimeoutError:
            await self._maybe_self_heal(); continue
```

實測:`wait_for(queue.get())` 比裸 `queue.get()` **貴 2.52 µs/次**
(3.12+ 的 `wait_for` 內部是 `async with timeouts.timeout(...)`,一次 `Timeout` 物件
+ 一次 `call_at` TimerHandle + heappush/heappop)。

TXO 全鏈訂閱時 tick 率不低(277 檔契約 + TXF),500 tps = 1.25 ms/s 白燒。

**修法**(S):把「每 0.05 s 檢查一次自癒」與「消費 tick」拆成兩件事 ——
自癒改成獨立的 `while True: await asyncio.sleep(0.05); await self._maybe_self_heal()` task,
消費端用裸 `await self._queue.get()`。這也順便解掉現在「盤中連續 tick 下 timeout 永不觸發」
的既有補丁(`self._force_heal` 那個旗標,`engine.py:381` 的註解 Alt-3)。

**風險**:`_maybe_self_heal` 現在依賴「queue 清空」當壓力解除的判準
(`engine.py:_maybe_self_heal` 的 DR-10),拆開後那個判準要改讀 `self._queue.qsize() == 0`。
`_paused` 測試鉤(`pause_consume_for_test`)的語意要一起想。

---

### X3-13 【low】KeepAlive 執行緒重複收下每一則推播,只為了找 PING

**位置**:`spikes/TCPY/tcoreapi_mq.py:287-302`(gitignored 的第三方 wrapper)

```python
socket_sub.setsockopt_string(zmq.SUBSCRIBE, "")      # ← 訂全部
while not self.IsTerminal:
    message = (socket_sub.recv()[:-1]).decode("utf-8")
    findText = re.search("{\"DataType\":\"PING\"}", message)     # ← 每則都跑,未預編譯
    if findText == None: continue
    objZMQ.Pong(session, "TC")                                   # ← 取 api.lock
```

每則市場推播在 process 內被 **recv + decode 兩次**(listener 一次、KeepAlive 一次),
再加一次 regex。實測 decode 0.23 µs + regex 0.59 µs = 0.82 µs/則/session。
1000 則/s × 5 session = 4.1 ms/s —— **量不大,但它是 5 條額外的執行緒喚醒/秒 × 1000**,
每次喚醒都要搶 GIL。

而且 `Pong()` 取的是 `api.lock` —— 這就是 `tc4.py:407` 整段註解在講的「毒鎖」風險來源
(「wrapper KeepAlive Pong **無 try/finally**,timeout 毒鎖」)。

**修法**:`spikes/TCPY/` 是第三方 wrapper 且 gitignored,理論上不該改。
但這個 repo **已經改過它**(`tc4.py:§0a` 記錄 2026-07-06 修過 KeepAlive 執行緒
生命週期 bug、加了 `daemon=True` 與自持 context)。所以「可以改」是既定事實。
最小改動:`re.search(...)` → 預編譯 pattern,或直接 `if '"DataType":"PING"' not in message: continue`
(0.59 → 0.17 µs)。**根本解**是用 ZMQ 的 topic prefix 過濾 —— 但需要先確認 TC4 的
PING 訊息帶什麼 topic 前綴(未知,要 probe)。

**風險**:改第三方 wrapper 沒有測試護欄。`Pong()` 漏了 = TC4 判斷線 = 整條 session 死。
建議**只改 regex 那一行**,不碰訂閱過濾。

---

### X3-14 【low】`_check_stale` 持 `self._lock` 跨越 150 檔 × 2 發 REQ 的重掛迴圈

**位置**:`copycat/live/tc4.py:1279-1298`

```python
with self._lock:
    old = self._api
    if old is not None: self._dispose(old)
    self._ensure_connected()
    resub = list(self._subscribed); self._subscribed = set()
    for sym in resub:
        self._rt_request("UNSUBQUOTE", sym)      # 一發 REQ,最壞 10 s
        r = self._rt_request("SUBQUOTE", sym)    # 又一發
```

stock session 斷線重連 = 150 檔 × 2 發 REQ。健康路徑每發毫秒級(總計約 1 s),
但 TC4 半死時每發最壞 10 s → **持鎖 50 分鐘**。期間所有 `_heal_resub`
(watchdog + 健檢 timer)全部堵在 `self._lock` 上,而它們跑在各自的執行緒上
—— 那些執行緒就這樣一直堵著,`threading.Timer` 那 150 條也一樣。

實務上 `_req` 失敗會 `_dispose` + raise,迴圈會提早中斷(`except` 在外層),
所以不會真的跑滿 50 分鐘。但**沒有任何機制保證**它會早退 —— 只要每發都「慢但成功」
(TC4 忙但沒壞),就會一路慢下去。

**修法**(M):`self._lock` 只保護 `_subscribed` 的讀寫,重掛迴圈移到鎖外,
用一個 `_resubscribing` 旗標擋重入(`_heal_resub` 看到旗標就跳過這輪 —— 反正重連
本來就會重掛全部)。

**風險**:`_lock` 現在同時擋「重連換 session」與「自癒重掛」兩件事(`_heal_resub`
的註解:「與 `_check_stale` 互斥:重連換 session 時不得同時重掛」)。
拆開要重新論證那個互斥性 —— 這是正確性問題,不是效能問題,**優先級低、風險高,
我建議先不動**。

---

### X3-15 【low】`asyncio` default executor 沒有被顯式設定,20 個 worker 全庫共用且不可觀測

**位置**:全庫零個 `set_default_executor` / `ThreadPoolExecutor`(grep 已確認)。
91 個 `to_thread` 呼叫點共用 `loop.run_in_executor(None, ...)` 的預設池,
`max_workers = min(32, os.cpu_count() + 4)` = **20**(本機 16 核)。

混在同一池的工作性質差異巨大:
- TC4 REQ(阻塞在 `api.lock` 上,最壞 12 s)
- FinMind urllib(網路 IO,最壞 timeout)
- jsonl / 審計落檔(毫秒)
- `capital.close()` 的 COM join(最壞 5 s)

`app.py:1570` 的註解自己就點名了:「to_thread 走 loop 預設 executor,與 daily_bars /
capital close 同池」。

20 個 worker 目前夠用(因為真正的瓶頸在 `api.lock`,worker 大多在等鎖),
但**沒有任何佇列深度的可觀測性** —— executor 滿了的症狀是「to_thread 的 await 遲遲不返」,
在畫面上與「TC4 慢」完全同形。

**修法**(S):在 lifespan 開頭顯式建池並命名:
```python
executor = ThreadPoolExecutor(max_workers=24, thread_name_prefix="copycat-io")
loop.set_default_executor(executor)
```
`thread_name_prefix` 讓 py-spy / Process Explorer 的執行緒名字可讀 —— 這是零風險的
可觀測性提升。**不要**為了「隔離」開多個池:多池只會讓 `api.lock` 上的等待者更多。

**風險**:關機時要 `executor.shutdown(wait=False)`,而且必須排在
`shutdown_budget` 的預算之外(不能等它)。

---

### X3-16 【low】WS 每條連線 3 個 task,其中 `_beat` 是每 10 秒醒一次的純 timer

**位置**:`copycat/server/ws.py:288-310`

8 條 WS endpoint(stock / capital / futures / corr / river / index / breadth / txo)
× 每個分頁 = 每分頁 24 個 task,其中 8 個是心跳 timer。三個分頁 = 72 task / 24 個
每 10 秒的喚醒。

`WS_HEARTBEAT_SECS = 10.0` 是**跨檔契約**(CLAUDE.md §4,前端
`ws-reconnect.ts::WS_SILENCE_TIMEOUT_MS = 30s` 必須大於它)。

**這個不要動。** 開銷可以忽略(每 10 秒 24 次喚醒 = 2.4 Hz),而它守的是
「半死 TCP 在瀏覽器端與『沒東西可推』完全同形」這個真實故障模式。列在這裡只是
為了拓撲圖完整。

---

## 5. Python 3.13 free-threading(PEP 703)評估

**結論:現在不可用,而且短期內不值得等。**

理由(逐條可查):

1. **本機跑的就是 GIL 版**:`sysconfig.get_config_var('Py_GIL_DISABLED') == 0`、
   `sys._is_gil_enabled() == True`。要用 free-threading 得換裝 `python3.13t`。
2. **相依鏈擋死**:
   - `comtypes 1.4.16` + `pywin32 312`:COM 是 **STA apartment** 模型,
     free-threading 不改變 apartment 語意 —— 群益 SKCOM 的所有呼叫仍然只能在
     `CoInitialize()` 過的那一條執行緒上。**這裡零收益**。
   - `pyzmq 27.1.0`:有 free-threaded wheel,但 libzmq socket **本來就不是 thread-safe**,
     現在的架構已經用 `api.lock` 把它序列化了 —— 拿掉 GIL 也還是那把鎖。**零收益**。
   - `discord.py 2.7.1` / `aiohttp 3.14.3` / `pydantic-core`:free-threaded wheel 覆蓋
     不完整,而且 asyncio 本身**不會**因為拿掉 GIL 就變成多執行緒 loop。
3. **架構上根本沒有可平行的純 CPU 熱點**。free-threading 的收益場景是「多執行緒跑同一份
   純 Python 計算」。這個 process 的 CPU 熱點全部在**一條 event loop**上,
   而 event loop 本質是單執行緒 —— 拿掉 GIL 不會讓一條 loop 變快。
4. **free-threaded build 的單執行緒效能目前仍有 ~5–10% 的回退**(specializing interpreter
   在 3.13t 上受限)。對一個「單執行緒是瓶頸」的架構,這是**淨負收益**。

**唯一可能的用法**:把訊號評估搬到 worker 執行緒池(見 §6 的「替代架構 A」),
那時 free-threading 才會有意義。但即使那樣,`comtypes` 的 STA 限制仍在,
所以**下單面永遠要留在一條專屬執行緒上**。

---

## 6. 替代架構評估(針對這個 codebase)

### A. 維持單 process asyncio + 更聰明的 to_thread(**建議路線**)

**做法**:
1. 修掉 X3-01 / X3-03 / X3-05 / X3-07 —— 這四條把 event loop 上最重的東西砍掉八成,
   而且**每一條都不動任何跨檔契約**。
2. X3-04 的入口批次化 —— 把 hop 成本攤薄。
3. 顯式命名 executor(X3-15)+ 佇列可觀測性(X3-11)。

**收益(推估,需量測驗證)**:熱路徑每 tick 165 µs → 約 40–60 µs;
`group-state` 的 65 ms 毛刺 → 約 10 ms;每 10 秒的 breadth 毛刺消失。

**代價**:幾乎沒有。全部是 in-place 優化,`pytest` 既有 3566 條測試就是護欄。

**這是我的建議。在做完 A 之前,不要考慮 B 或 C。**

---

### B. 多 process(行情 ingest / 計算 / web 分離)

**可能的切法**(以這個 codebase 的既有 seam 為準):

```
process 1:tc4-ingest
   5 條 TC4 session 的 listener + healer
   只做:recv → json.loads → 最小正規化 → 往 IPC 送
process 2:engine
   StockEngine / IndexEngine / FuturesEngine / CorrEngine / SignalHub
process 3:web
   FastAPI + WS fanout
process 4:capital(COM STA)—— 本來就該獨立
```

**為什麼這個 codebase 特別難切**:

1. **`api.lock` 跨不了 process 邊界,而它正是瓶頸**。ingest 分出去之後,
   REQ(訂閱 / 回補 / 歷史)要嘛跟著過去(那 engine 要 RPC 回來,每發多一跳),
   要嘛留下來(那 session 就要開兩條,踩 CLAUDE.md §8 的 refcount key 事實)。
   **切 process 不會解掉 X3-02,只會讓它更難改。**
2. **`SignalHub` 與 `StockEngine` 的耦合是逐 tick 的物件參照**
   (`hub.on_tick(code, tick, state)` 直接吃 `StockDayState` 物件,
   `_context()` 讀 `state.book` / `state.meta`)。跨 process 要序列化整個 state
   —— 那比現在整條熱路徑還貴。
3. **CLAUDE.md §4 的跨檔契約有一半是「前後端同值」**,多 process 會再多出
   「process 間同值」的第三邊。以這個專案已經有 20+ 條契約的密度,這是災難。
4. **Windows 上 `multiprocessing` 是 spawn**:每個子 process 要重新 import 整個
   `copycat` 套件 + 重建 TC4 連線,關機預算(`shutdown_budget`)要整個重算。

**唯一值得的一刀**:`capital`(COM)**已經是專屬執行緒**,把它拆成獨立 process
其實很乾淨(介面已經是 `_cmd_q` + future,天然是 RPC 形狀),而且能把
`COM_JOIN_TIMEOUT_SECS` 從關機預算裡拿掉。但收益是**穩定性**(COM 死掉不拖垮看盤)
而不是效能 —— 現在 COM 執行緒 20 Hz 幾乎不佔 GIL。

**判斷:不建議。** 除非量測證明單 loop 修完 A 之後仍然吃滿一顆核。

---

### C. subinterpreters(3.13 `concurrent.interpreters` / PEP 734)

**不適用。** 三個硬阻擋:

1. **`pyzmq` / `comtypes` / `pywin32` 都是 C 擴充,且都不支援 per-interpreter GIL**
   (需要 `Py_mod_multiple_interpreters` slot)。TC4 與群益兩條命脈直接出局。
2. 3.13 的 subinterpreter **沒有共享可變狀態**,跨 interpreter 只能傳
   「可 pickle / memoryview」—— `StockDayState` / `SignalDetector` 的 deque 狀態機
   沒辦法這樣切。
3. 3.13 的 stdlib API(`interpreters` 模組)在 3.13 是 `_interpreters` 私有 +
   PEP 734 的公開版要到 3.14。這個專案釘 `requires-python = ">=3.13"`。

**判斷:不考慮。**

---

### D. Windows 特有選項

| 選項 | 現況 | 建議 |
|---|---|---|
| **ProactorEventLoop**(現況) | uvicorn 0.51 `loops/asyncio.py` 在 win32 且非 subprocess 時回 `asyncio.ProactorEventLoop` | **保持**。實測 `call_soon_threadsafe` 8.56 µs,比 Selector 的 11.27 µs **快 24%**;IOCP 對 WS 也更好 |
| **winloop**(libuv on Windows,uvloop API 相容) | 未安裝 | **值得試,但期望值放低**。這個 process 的瓶頸是純 Python CPU 不是 socket 層;winloop 主要加速 socket read/write 與 timer。我預估整體收益 < 5%。而且它是 `uvicorn[standard]` 之外的第三方相依,對一個 stdlib-only 哲學的 runtime 是額外負擔。**先做 §6-A,再量測,再決定。** |
| **uvloop** | Linux only | 不適用 |
| **COM STA** | `capital/client.py:_run` 的 `pythoncom.CoInitialize()` + 專屬執行緒 | **保持**,這是唯一正確做法。`com.py` 的 docstring 已經明說「所有方法都必須在同一條 CoInitialize 過的執行緒上」 |
| **執行緒優先權** | 未設定 | **可考慮**:把 event loop 執行緒設成 `ABOVE_NORMAL`(`win32process.SetThreadPriority`),把 executor worker 設成 `BELOW_NORMAL`。pywin32 已經是相依(capital extras)。但這是**最後手段**,先把 CPU 砍下來 |
| **timeBeginPeriod** | 未設定 | Windows 預設 timer 解析度 15.6 ms —— `call_later(0.1)` 的實際抖動可能到 ±16 ms。若要打包窗精度,可用 `winmm.timeBeginPeriod(1)`。**但會增加全系統耗電/排程開銷,而 0.1 s 的打包窗 ±16 ms 完全可接受**。不建議 |

---

## 7. 套件 / 工具選型

| 工具 | 用在哪 | 解決什麼 | 代價 | 判斷 |
|---|---|---|---|---|
| **py-spy**(**已安裝** 0.4.2) | `py-spy dump --pid <uvicorn>` / `py-spy record` | 唯一能在**不改 code、不重啟**的前提下看到「盤中 loop 在忙什麼」的工具。native + Python 混合 stack,能同時看到 15 條 TC4/COM 執行緒 | 零。已在 dev 相依裡 | **立刻用**。見 §8 |
| **orjson** | ① FastAPI `default_response_class`;② `ws.relay` 的 send;③ `tc4._listen_loop` 的 json.loads | X3-03 的 43.6 ms 序列化 → 推估 ~7 ms;json.loads 4.9 → ~1.5 µs | 一個 C 擴充相依,進 `live` extras。Windows wheel 齊全。**打破「runtime stdlib-only」的哲學** —— 但 `live` extras 本來就有 pyzmq/uvicorn 三個 C 擴充,這條線早就跨過了 | **建議導入(live extras)** |
| **msgspec** | 取代 `parse_stock_realtime` 的手寫解析 | 一步到位 bytes → struct,理論上能把 H1+H2 的 28 µs 壓到 < 5 µs | TC4 的欄位是**全字串**(`"1120.0"` / `"12"`),msgspec 的收益要靠 `Struct` + 型別轉換,而型別轉換的語意(空字串 → None、`"-"` → None)是這個 codebase 的既有事實,搬過去要重新驗一遍。**風險 >> 收益** | **不建議**。先做 X3-05 的手切 + meta 快取 |
| **uvloop / winloop** | event loop | socket / timer 層 | 見 §6-D | **量測後再說** |
| **numpy** | `_eval_volume` 的窗總和 / `corr_engine` 的 Pearson | 窗總和用 numpy 是**反模式**(每 tick 建 array 比 Python sum 還慢);Pearson 倒是合適 | 一個大型 C 相依,而相關係數 1 秒才算一次、11 腿 | **不建議**。X3-01 的增量總和是正解 |
| **polars / duckdb / pyarrow** | 回測 `backtest/*` | fade_cells 2007 行的純 Python 迴圈 | 離線、不在熱路徑 | **本區塊不評**(交給 backtest 區塊) |
| **httpx / aiohttp**(**已在 venv**,經 dev/discord 相依進來) | 取代 `urllib` + `to_thread`(21 處 import) | 把 FinMind / MIS 的取數從「佔一個 executor worker」變成「純 async」,executor 就只剩 TC4 REQ | httpx 現在只在 dev extras;要進 runtime 得改 `pyproject.toml`。**收益有限**:FinMind 取數 10 秒才一次、MIS 5 秒一次,佔用 worker 的時間佔比很小 | **低優先**。真要做,順便把 `oi_levels` / `breadth_fetch` / `screen_engine` 的 retry 邏輯統一 |
| **`ThreadPoolExecutor(thread_name_prefix=)`**(stdlib) | X3-15 | py-spy 輸出可讀性 | 零 | **建議做**,五行 |
| **`tracemalloc` / `asyncio` debug mode** | 開發期 | `loop.slow_callback_duration` 會在 callback 超過門檻時印 warning —— 這是**直接量到 X3-01/X3-03 的工具** | debug mode 有 ~10% 額外開銷,只在驗證 session 開 | **建議**:加一個 `--profile` 旗標到 `__main__.py`,開 `loop.set_debug(True)` + `loop.slow_callback_duration = 0.02` |

---

## 8. 不要動的地方

1. **`ws.py` 整支。** per-client 有界 queue + 丟最舊保最新 + 節流 WARNING + 窗到期結算
   + 心跳 + `FIRST_COMPLETED` 收尾 + `_is_close_sent_error` 的兩句原文辨識 ——
   這是全庫寫得最好的併發 code,每一個分支背後都有一次真實事故。
   `WS_HEARTBEAT_SECS` 更是 CLAUDE.md §4 的跨檔契約。**零改動。**
2. **`shutdown_budget.py` + lifespan 的並行 lane + `run.ps1` 的 `WaitForExit`。**
   三方同源、有不等式測試(`tests/server/test_shutdown_budget.py`)釘住、
   `TC4_LANE_DEPTH` 是口頭契約由 `test_boot_window.py::TestShutdownLanes` 機驗。
   任何 §6-B 的多 process 切法都會炸掉這整套。**不要碰。**
3. **`capital/client.py` 的 COM 執行緒模型。** 20 Hz 幫浦、`_cmd_q` + future、
   `shield` 保護真錢命令、`_drain_pending` 的失敗收斂 —— 這是真錢路徑,
   而且 STA 限制讓它沒有別的寫法。目前完全不是效能瓶頸(未測,但 20 Hz × 幾個
   collector poll 是奈秒級)。**不要為了效能碰它。**
4. **`tc4.py` 的鎖序與 cancel 路徑。** `self._lock → _api_lock → api.lock`、
   `_dispose` 不取 `self._lock`、`_ensure_connected` 持鎖跨 `Connect()` ——
   每一條都有 review 編號與失效樣態的文件。X3-14 雖然是真的問題,但改它的風險
   遠大於收益。**除非量測到它真的發生。**
5. **`backtest/` 與 `replay/` 的純 Python 迴圈。** 它們在另一個 process、離線跑,
   對盤中零影響。`fade_cells.py` 2007 行再慢也不會讓一筆 tick 晚到。
6. **`corr_engine._run` 的 1 秒節拍。** 11 腿三窗 Pearson,1 Hz。
   除非量到它 > 5 ms,否則不動。
7. **WS 心跳 task(X3-16)。** 開銷可忽略,守的是真實故障模式。

---

## 9. 量測方法(要證明快慢,照這個順序做)

### M1 —— 盤中即時採樣(零改動、零重啟,**先做這個**)

`py-spy` 已在 venv。盤中(09:05–09:15,最忙的十分鐘)對跑著的 server:

```powershell
# 找 pid
Get-NetTCPConnection -LocalPort 8721 -State Listen | Select-Object OwningProcess

# 1) 瞬時全執行緒 stack(看誰在 api.lock 上排隊、loop 在哪個函式)
.\.venv\Scripts\py-spy.exe dump --pid <PID> --locals

# 2) 60 秒取樣火焰圖(--idle 一起看,才分得出「在等」與「在算」)
.\.venv\Scripts\py-spy.exe record --pid <PID> --duration 60 --rate 200 --idle `
    --output C:\Users\USER\AppData\Local\Temp\copycat-open.svg

# 3) 只看 event loop 那一條(排除 15 條 TC4/COM 執行緒的噪音)
.\.venv\Scripts\py-spy.exe top --pid <PID> --threads
```

**判準**:
- 火焰圖上 `_eval_volume` / `sum` 的佔比 —— 若 > 5%,X3-01 就從「理論」變「實測」。
- `light_snapshot` / `json.dumps` 的尖峰 —— 對應 X3-03。
- `api.lock.acquire` 的等待者數量(`dump` 會顯示每條執行緒的 stack;
  停在 `acquire` 的執行緒數 = 當下的排隊深度)。

### M2 —— loop 停擺量測(需一行改動 + 重啟)

在 `__main__.py` 的 `main()` 內,`uvicorn.run` 之前(或 lifespan 開頭):

```python
loop = asyncio.get_running_loop()
loop.set_debug(True)
loop.slow_callback_duration = 0.020   # 20 ms
```

asyncio 會對每個超過 20 ms 的 callback 印
`Executing <Handle ...> took X.XXX seconds`。
**盤後 grep**:`grep "took 0\." logs/server-*.log | sort -t' ' -k2 -rn | head -30`
→ 這一張表就是「event loop 被誰卡住」的權威答案,不必猜。

**代價**:debug mode 全域慢 ~10%,而且會對每個 task 存 source traceback(記憶體)。
**只在一次驗證 session 開,不要長跑。**

### M3 —— tick 率真值(目前完全不知道,而所有推估都靠它)

現在 log 裡沒有任何「每秒幾則推播」的數字。加一個 60 秒節流的計數器到
`stock_engine._handle_quote` 入口(或更好:`tc4._realtime_msg`,涵蓋五條 session):

```python
# 每 60 s 印一則:「stock session 推播 n 則/分,其中成交 m 則」
```

**這是最重要的一個數字。** X3-01 的嚴重度完全取決於「熱門股盤中真實 tick 率是 3 / 10 還是 30」,
而那個數字沒有人量過。

### M4 —— TC4 多 session 的 refcount probe(X3-02 的前提,**盤中不可做**)

在**非交易時段**用一支獨立腳本(不經 server):
1. 開 session A,`SUBQUOTE` 2330(REALTIME 窗)。
2. 開 session B,只對 2330 發 `SUBQUOTE` with `SubDataType=TICKS`(歷史窗)+ `GETHISDATA`。
3. 觀察 session A 的 REALTIME 推播**有沒有中斷**。
4. 關掉 session B,再觀察 A。

若 A 全程不中斷 → 「歷史 session 與 realtime session 的 refcount key 不相交」成立,
X3-02 的方案 1 可行。若中斷 → 方案 1 出局,只剩方案 2(優先級佇列)。

**這個 probe 必須在收盤後跑,而且要看 TC4 端的 log**(`ReqSubQuote` / `Remove count`)。
`tc4-market-facts` skill 記錄了怎麼讀那份 log。

### M5 —— 改動前後的 A/B(micro)

本次的 `scratchpad/bench*.py` 可以直接當 baseline harness。改完 X3-01 後重跑
`bench3.py` / `bench4.py`,期望:

| 指標 | 現況 | 目標 |
|---|---|---|
| `evaluate` 7 slot @30 tps | 349 µs | < 60 µs |
| `vol_burst` 單條 @30 tps | 309 µs | < 8 µs(O(1)) |
| `light_snapshot` × 150 | 20.9 ms | < 10 ms |
| `json.dumps` group payload × 150 | 43.6 ms | < 8 ms(orjson) |
| `parse_stock_realtime` | 23.3 µs | < 12 µs |

### M6 —— 執行緒數實測(驗證 §1.1 的 50 條推估)

```powershell
(Get-Process -Id <PID>).Threads.Count
# 或 py-spy dump 會列出所有執行緒名稱
```
配合 X3-15 的 `thread_name_prefix` 之後,這份清單會變得可讀。

---

## 10. 開放問題(查不出來 / 需要 user 或 profile 才知道)

1. **盤中真實推播速率是多少?**(M3)。現有 log 完全沒有這個數字,而 X3-01 / X3-04 的
   嚴重度完全取決於它。我用 3 / 10 / 30 tps 三個量級都測了,但**哪一個是真的,只有量了才知道**。
2. **純簿更新 vs 成交的比例?** TC4 對五檔變動也推 REALTIME。若比例是 10:1,
   那 X3-04(每則一 hop)+ X3-05(每則全額 parse)的權重會超過 X3-01。
3. **TC4 的歷史 session 與 realtime session 會不會互搶 symbol feed?**(M4)。
   這決定 X3-02 有沒有「開第二條 session」這個選項。
4. **`corr_engine.tick_once` 的實際耗時?** 11 腿 × 三窗 Pearson,1 Hz。我沒有造出
   有代表性的輸入來測(需要真的 `RiverState` / 腿資料)。
5. **user 是否接受 runtime 引入 C 擴充(orjson)?** `pyproject.toml` 的
   `dependencies = []` 是刻意的 stdlib-only 哲學,但 `live` extras 已經有
   fastapi / uvicorn[standard] / pyzmq 三個 C 擴充。orjson 進 `live` extras
   在我看來一致,但這是 user 的拍板。
6. **群組檢視同時開幾個分頁是常態?** X3-03 的 65 ms 毛刺乘以分頁數。
   若常態是 1 個分頁,優先級可以降一級。
7. **`vol_burst` 規則實際有沒有開著?** `default_rules` 產出時 `enabled` 來自
   `signals_enabled.json` 的 legacy flag(缺鍵 = True)。若 user 已經把爆量關掉,
   X3-01 的實際影響是零(detector 仍然建了、窗仍然維護,但 `_eval_volume`
   第一行就 `return []`)—— **這一條要 user 直接回答,或看
   `curl -s 127.0.0.1:8721/api/stock/signals/rules`**。
8. **`surge_window_secs = 300` 是否真的需要 300 秒?** 若 user 願意調成 60 秒,
   X3-01 的成本立刻降 5 倍(雖然增量總和才是正解)。但這是**策略參數不是效能參數**,
   不該為了效能改它 —— 列在這裡只是為了說明「窗長直接決定成本」。
