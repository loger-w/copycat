# X1 — 阻塞 IO 全庫稽核(「不能塞住」的核心)

> 範圍:`C:/side-project/copycat/copycat/**`(123 檔 / 37,589 LOC)。
> 方法:AST 掃描 + 全檔精讀(app.py / stock_engine.py / signal_hub.py / ws.py / engine.py /
> tc4.py / capital/client.py / capital_api.py / corr_engine.py / corr_state.py 等)
> + **在本機 venv 實跑微基準**(Python 3.13、Windows 11、cpu=16)。
> 所有數字都是實測,非估計;估計值一律標「推測」。
> 唯讀稽核,零 repo 改動、未啟 server、未連 TC4。

---

## 0. 一句話結論

**這套系統沒有「async 函式裡直接 `urlopen` / `time.sleep` / 同步鎖」那種教科書級的阻塞 —— AST 掃描
確認為零。真正會塞住的是三件完全不同的事:**

| # | 塞住的東西 | 實測量級 | 頻率 |
|---|---|---|---|
| **A** | `CorrState.correlations()` 在 event loop 上**每秒**整批重算 1800 樣本 × 10 腿 | **16.0 ms**(每秒!) | 每 1 s + 每個 `/api/corr/state` + 每條 `/ws/corr` |
| **B** | `/api/stock/state/{code}` 全量 tape(2 萬筆)的 snapshot 組裝 + 序列化在 loop 上 | **8.7 ms + ~5 ms** = ~14 ms | 每次切主圖 / 跳號 refetch |
| **C** | **下單的審計寫檔與全庫 TC4 歷史取數共用同一個 20-thread 預設 executor**;TC4 半死時每條佔 10–20 s | 最壞 **秒~數十秒** | 每一筆真單 |

A 是「每秒一定會發生的 16 ms 抖動地板」,B 是「使用者一操作就 14 ms 全站停拍」,
C 是「真錢路徑沒有隔離,被行情查詢排隊」。三者都與「換 numpy / polars」無關 ——
A 是**演算法**(該增量卻整批重算)、B 是**序列化位置**(該離 loop 卻在 loop)、
C 是**資源隔離**(該分池卻共用)。

---

## 1. 量測環境與基準值

```
Windows 11 / Python 3.13 / cpu_count = 16
=> asyncio 預設 ThreadPoolExecutor max_workers = min(32, 16+4) = 20
=> event loop policy = WindowsProactorEventLoopPolicy(uvicorn 未指定 loop;Windows 無 uvloop)
uvicorn 0.51.0 / fastapi 0.139.2 / starlette 1.3.1 / pydantic 2.13.4 / pyzmq 27.1.0
```

實測原始數字(`scratchpad/arch-scan/bench_x1.py` / `bench_x1b.py` / `bench_x1c.py`):

```
json.loads(一則 REALTIME 電文 520 B)                         6.45 us
json.dumps(同上)                                             5.81 us
parse_stock_realtime(一則 quote)                            22.71 us   <- 在 event loop 上
_now_taipei_time()  (datetime.now + %H:%M:%S.%f)             2.52 us
_observe_window_now()                                        2.94 us
datetime.now()                                               0.17 us
load_names()  59 KB json + 2401 鍵 dict                    806.12 us   <- 在 event loop 上
/api/stock/names payload 組裝(2401 dict)                  226.20 us   <- 在 event loop 上
json.dumps(names payload)                                  627.41 us
load_watchlist()  2.8 KB                                   120.65 us   <- 在 event loop 上
read_signals(1 日 jsonl 289 KB / 686 列)                  6188.62 us   <- 有 to_thread,OK
StockDayState.snapshot(tape=True)  20k ticks              8654.59 us   <- 在 event loop 上 ★
StockDayState.snapshot(tape=False)                           18.36 us
StockDayState.light_snapshot()                               19.83 us
json.dumps(full snapshot 20k ticks)                      13045.00 us
json.dumps(light snapshot) × 150 (group-state)            5266.73 us   <- 在 event loop 上
append jsonl 一列(open+write+close)                       199.62 us
_Tee sink write+flush(每行 log)                             4.85 us   <- 比預期便宜,不用動
asyncio.to_thread 往返(pool 空閒)                           89.86 us
loop.call_soon_threadsafe 往返                               11.50 us   <- 每 tick 一次
CorrState.correlations(now)  11 腿 / 窗 (60,300,1800)     16043.00 us  <- 每秒在 loop 上 ★★
CorrState.push(一筆取樣)                                      3.00 us
breadth rows_state 近似(2800 列 {**row,...})              1710.00 us
json.dumps(breadth rows 2800)                              3900.00 us
```

FastAPI 端到端(TestClient,含 HTTP):

```
GET /tiny   (11 B)          1.69 ms
GET /snap   (1,522,690 B)   9.99 ms   <- 全量 tape 的回應序列化
GET /group  (419,251 B)     4.16 ms   <- group-state 150 檔
```

> 註:`jsonable_encoder(full snapshot)` 單獨測是 **137 ms**,但 FastAPI ≥0.100 對 `-> dict`
> 走的是 pydantic-core(Rust)序列化,實測端到端只有 10 ms。**不要據此得出「換 orjson 省 130 ms」
> 的結論** —— 真實可省的是 ~5–8 ms。

---

## 2. 架構地圖:四個執行域

```
┌───────────────────────────────────────────────────────────────────────────┐
│ ① TC4 listener threads(5 條,每條一個 ZMQ SUB socket + 自己的 zmq.Context)│
│    txo / stock / index / futures / corr                                     │
│    tc4.py:1226 _listen_loop:  sock.recv() [RCVTIMEO 1s] → decode           │
│                              → handle_raw → json.loads (6.45 us)           │
│                              → _realtime_msg → on_message 回呼              │
│                              → loop.call_soon_threadsafe(...)   (11.5 us)  │
│    ★ 每一則行情都在這裡跨執行緒交棒一次                                     │
└───────────────────────────────────────────────────────────────────────────┘
                                   │ call_soon_threadsafe
                                   ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ ② asyncio event loop(單執行緒,ProactorEventLoop)                          │
│    ‧ 全部 34 條 HTTP/WS route —— **全部是 async def,零條進 FastAPI 執行緒池**│
│    ‧ 8 條 WS 的 relay(_send / _recv / _beat,每條連線 3 個 task)           │
│    ‧ ~20 條常駐背景 task(見 §3)                                            │
│    ‧ _handle_quote(個股 / 期貨 / corr)per-quote 解析                       │
│    ‧ discord.py client 也跑在這條 loop 上                                   │
│    ★ 任何一個 >5 ms 的同步區段 = 全站(行情推播 + 下單回應)一起停拍         │
└───────────────────────────────────────────────────────────────────────────┘
          │ asyncio.to_thread(60+ 處)                    │ queue.put
          ▼                                              ▼
┌────────────────────────────────┐   ┌────────────────────────────────────┐
│ ③ 預設 ThreadPoolExecutor       │   │ ④ capital-com 單一執行緒            │
│    max_workers = 20             │   │    client.py:709                    │
│    **全庫共用一池**:            │   │    while True:                      │
│      TC4 SUBQUOTE / UNSUBQUOTE  │   │       _pump_once()  ← COM 幫浦 +     │
│      TC4 GETHISDATA(≤20 s)     │   │            balance/profit/OI 輪詢    │
│      TC4 SubHistory 回補         │   │       cmd = _cmd_q.get(timeout=.05) │
│      jsonl 落檔 / 讀檔           │   │       fn()  ← **同步 COM 送單**      │
│      FinMind urlopen(breadth /  │   │    ★ 下單命令與帳務查詢共用這條      │
│         screen / oi-levels)     │   │      執行緒,查詢慢 = 送單慢         │
│      Discord webhook urlopen     │   └────────────────────────────────────┘
│      **下單前後的審計寫檔** ★     │
└────────────────────────────────┘
```

另外還有:
- 5 條 TC4 自癒 watchdog thread(`_heal_loop`,poll 5 s)
- **每檔個股一條 `threading.Timer` 執行緒**(`stock_source.py:642`,見 F-07)
- 每個 `zmq.Context()` 一條 ZMQ IO thread(listener 5 個 + QuoteAPI 各自一個 ≈ 10 條)
- discord.py 的 keep-alive thread

---

## 3. 常駐 task / thread 清冊(問題 5)

### 3.1 `while True` 的 asyncio task(全部用 `await asyncio.sleep`,無一個 busy-loop)

| 檔案:行 | task | 間隔 | 每輪工作 |
|---|---|---|---|
| `server/engine.py:378` | `EngineRuntime._consume` | `wait_for(queue.get, 0.05)` | TXO tick 路由;**唯一一個每 50 ms 建 timeout 的迴圈** |
| `server/engine.py:160` | `snapshots()` | `throttle` 1 s | per-WS-client,節流快照 |
| `server/stock_engine.py:1553` | `_backfill_worker` | queue 驅動 | 批次 SubHistory + 逐檔收割(to_thread) |
| `server/stock_engine.py:1815` | `_flush_watchlist_loop` | 1 s | ≤150 檔 `_quote_payload`(~8 µs 各) |
| `server/stock_engine.py:994` | `_retry_subscribe_loop` | 10 s | 訂閱對帳三段 |
| `server/stock_engine.py:1130` | `_checkpoint_loop` | 60 s | 換日窗判定 |
| `server/signal_hub.py:822` | `_basis_worker` | queue + `basis_gap_secs` | CDP 基準取數(to_thread) |
| `server/signal_hub.py:1187` | `_jsonl_worker` | queue | `to_thread(_append_jsonl)` |
| `server/signal_hub.py:1209` | `_discord_worker` | queue | 合批送 Discord |
| `server/signal_hub.py:1264` | `_policy_outcome_worker` | 30 s | 牆鐘判定,每日一次真工作 |
| `server/index_engine.py:356` | `_retry_loop` | backoff | 加權回補重試 |
| `server/index_engine.py:509` | `_mis_loop` | `poll`(5 s) | 櫃買 MIS urlopen(to_thread) |
| `server/index_engine.py:590` | `_rollover_loop` | `rollover_check_secs` | 換日 |
| `server/index_engine.py:670` | `_broadcast_loop` | 1 s | watchdog + `state()` 廣播 |
| `server/futures_engine.py:250` | `_resub_loop` | `resub_interval` | 重訂;flush 走 `call_later(0.1)` |
| `server/corr_engine.py:224` | `_run` | **1 s** | `tick_once()` → **`state()` → correlations 16 ms** ★ |
| `server/corr_engine.py:184` | `_resub_loop` | `resub_interval` | 重訂 |
| `server/breadth_engine.py:364` | `_poll_loop` | `effective_interval` | FinMind 取數(to_thread) |
| `server/breadth_engine.py:712` | `_compute_streaks_loop` | 排程 | 連板 EOD |
| `server/screen_engine.py:135` | `_loop` | 到 08:00 | 盤前篩選 |
| `server/ws.py:268` | `_beat`(每條 WS) | 10 s | 送 ping |
| `server/ws.py:274` | `_recv`(每條 WS) | 阻塞 | 收 client frame |
| `server/ws.py:137` | `stream()`(每條 WS) | 阻塞 | queue.get |

**總計:~20 條固定背景 task + 每條 WS 連線 3 條。** 8 種 WS × 2 個分頁 = 48 條 relay task。
數量健康,沒有一個是 busy-loop。

### 3.2 執行緒

| 來源 | 條數 | 備註 |
|---|---|---|
| TC4 `_listen_loop` | 5 | 每條一個 SUB socket |
| TC4 `_heal_loop` watchdog | 5 | poll 5 s |
| **`stock_source` 的 `threading.Timer`** | **最多 ~150** | 見 F-07 —— 每檔一條執行緒 |
| `capital-com` | 1 | 下單 + 帳務,見 F-03 |
| 預設 ThreadPoolExecutor | ≤20 | **全庫共用**,見 F-02 |
| pyzmq Context IO thread | ~10 | 每 `zmq.Context()` 一條 |
| discord.py keep-alive | 1–2 | |
| uvicorn 主執行緒 | 1 | |

---

## 4. 熱路徑逐條(附頻率與每次工作量)

### HP-1:個股 REALTIME 電文 → 瀏覽器(全系統最高頻)

```
TC4 listener thread                              event loop
────────────────────────                        ─────────────────────────
sock.recv()                          6.5us  →
handle_raw → json.loads              6.5us
stock_source.handle_raw:933
  with self._seen_lock: _seen.add()   ~1us   (threading.Lock,持鎖僅一個 set.add)
_on_message(quote)
  → _on_raw_threadsafe
  → loop.call_soon_threadsafe        11.5us ──────► _handle_quote(quote)
                                                     stock_engine.py:1187
                                                     ├ parse_stock_realtime      22.7us
                                                     ├ _observe_trade_status      2.9us
                                                     │   └ _observe_window_now(datetime.now+strftime)
                                                     ├ state.update_book/meta      ~2us
                                                     ├ state.ingest(tick)          ~3us
                                                     ├ _pending_ticks.append       ~1us
                                                     └ signal_hub.on_tick          ~?(每規則一次)
                                                    ────────────────────────────────
                                                     合計 ≈ 40-50 us / 則,**全在 loop 上**
```

頻率:盤中 150 檔自選,**推測** 平均 300–1,000 則/s、開盤瞬間 3,000+ 則/s。
→ loop 佔用 1.5%(300/s)~ 15%(3,000/s)。**這不是瓶頸,但它是 latency 的底噪**。

`_flush_ticks`(0.1 s `call_later`)把整窗打包成一則 `{"type":"ticks","items":[...]}`
→ `WsBroadcaster.publish` → 每個 client queue → `relay._send` → `send_json` → **per-client
`json.dumps`**(8 種 WS × N 分頁各自序列化一次)。

### HP-2:`corr_engine.tick_once()` —— 每 1 s ★★

```
corr_engine.py:300 tick_once()
  ├ 11 腿 mid_from_book                      ~20us
  ├ self._state.push(now, mids, session)       3us
  └ self._broadcast(self.state())
        └ corr_engine.py:543  self._state.correlations(now)
              corr_state.py:113
              for leg in 10 legs:
                  _paired_returns(leg, now)   ← **整批重算 1800 筆 log_return**
                  for window in (60,300,1800):
                      xs = [.. for .. if ts>=cutoff]   ← 每窗再掃一次 paired
                      ys = [.. for .. if ts>=cutoff]
                      statistics.correlation(xs, ys)
        ────────────────────────────────────────
        實測 16.043 ms,每秒一次
```

cProfile 拆解(20 次呼叫 = 811 ms):

```
ncalls  tottime  cumtime  function
   200   0.356    0.674   corr_state.py:82(_paired_returns)   <- 83% 的成本在這裡
720000   0.126    0.198   corr_models.py:31(log_return)
    20   0.077    0.811   corr_state.py:113(correlations)
720000   0.072    0.072   math.log
   600   0.025    0.054   statistics.py:1311(correlation)     <- 只佔 7%
```

**根因**:每秒只新增 1 個取樣點,卻把整條 1800 點的報酬序列從頭重算
(`leg_by_ts = dict(leg_series)` 每腿建一次 3600 項 dict + 逐點 `log_return`)。
`corr_state.py` 的模組 docstring 寫「整輪 tick 外推不到 1 ms」—— 那只量到
`statistics.correlation`(0.15 ms × 30 = 4.5 ms),**漏掉了 83% 的成本,實測差 16 倍**。

### HP-3:`/api/stock/state/{code}` —— 使用者每次切主圖 / 每次 seq 跳號 ★

```
app.py:1668 stock_state(async def,跑在 loop 上)
  ├ _resolve_contract → catalog.contains → to_thread(QUERYALLINSTRUMENT)  冷 cache 秒級
  ├ await stock.set_main_contract(key)
  │     async with self._pool_lock:              ← 與 PUT watchlist / 重試輪競爭
  │       to_thread(_acquire)   ← ZMQ SUBQUOTE,TC4 半死時 10 s
  │       to_thread(_release)
  │       to_thread(_release_stkfut)
  ├ stock.snapshot(key, tape=True)
  │     ├ _flush_ticks()             → publish 一則
  │     └ state.snapshot(tape=True)  **8.65 ms**(2 萬筆各組一個 dict)
  └ FastAPI 回應序列化 1.5 MB          **~5 ms**
  ────────────────────────────────────────────
  loop 上的連續同步區 ≈ 14 ms;整條 route 最壞 30+ s(TC4 半死)
```

### HP-4:`/api/stock/group-state?codes=...`(圖牆每 60 s,最多 150 檔)

```
app.py:1707 → stock.group_snapshot(wanted)
  ├ _flush_ticks()
  └ 150 × (light_snapshot 19.8us + {**light,...} dict 展開)  ≈ 3.5 ms
  回應序列化 419 KB                                          ≈ 4.2 ms
  ──────────────────────────────────────────────────────────
  loop 上 ≈ 8 ms,每 60 s 一次
```

### HP-5:下單 `POST /api/capital/order/stock` ★★★(真錢路徑)

```
capital_api.py:294 (async def, loop)
  └ client.submit_stock_order → _execute_write  (client.py:866)
      ├ gate 檢查                                          ~us
      ├ await asyncio.to_thread(self._audit, ...)   ★★★ 前置審計
      │     └ audit.py:29 append_audit
      │          with _audit_lock:                  ← module-level threading.Lock
      │            open(path,"a") ; write ; flush   ← 實測 200 us
      │     ── pool 空閒時 = 90us(dispatch) + 200us = 0.3 ms
      │     ── **pool 被 20 條 TC4 REQ 佔滿時 = 10–20 s**  ★★★
      ├ self._cmd_q.put((com_call, fut))
      │     └ capital-com 執行緒正在 _pump_once() 裡跑 balance/profit/OI 的
      │       **同步 COM 查詢** → 這一筆命令要等它回來(推測 0.1–3 s)
      ├ await wait_for(shield(fut), timeout=10 s)
      └ await _audit_after → 再一次 to_thread
```

---

## 5. 阻塞點完整清單

### 5.1 AST 掃描結果(`scan_async.py`):async def body 內的同步呼叫

**好消息:全庫 `async def` 內沒有任何 `urlopen` / `time.sleep` / `with threading.Lock` /
`subprocess` / `open()` 寫檔。** 掃描命中的 30 處全部是 `await asyncio.sleep(...)`,
外加以下 4 處真命中:

| 檔案:行 | 命中 | 判定 |
|---|---|---|
| `signal_hub.py:1294` | `signal_dir.exists()` | 一次 stat,每日一次 — 可忽略 |
| `signal_hub.py:1299` | `signal_dir.glob('*.jsonl')` | 目錄列舉,每日一次 — 可忽略 |
| `signal_hub.py:1378` | `json.dumps(row)` 逐列 | 見 F-09 |
| `signal_hub.py:1332` | `_policy_row_needing_outcome(line)` 逐列 `json.loads` | 見 F-09(~30 ms/日) |
| `signal_hub.py:564` | `await self._jsonl_queue.join()` in `close()` | 有 `_CLOSE_FLUSH_TIMEOUT` 5 s 保護 — OK |

### 5.2 AST 掃描抓不到的:async route 呼叫「同步方法而該方法很重」

| 位置 | 呼叫 | loop 上耗時 | 頻率 |
|---|---|---|---|
| `app.py:1699` | `stock.snapshot(key, tape=True)` | **8.65 ms** + 5 ms 序列化 | 切主圖 / 跳號 |
| `app.py:1736` | `stock.group_snapshot(wanted)` | 3.5 ms + 4.2 ms | 60 s |
| `app.py:1458` | `load_stock_names(names_path)` 讀 59 KB JSON | 0.81 + 0.23 + 0.63 ms | 開站 / 搜尋 |
| `app.py:1467` | `load_watchlist(wl_path)` 讀檔 | 0.12 ms | 每次 GET |
| `app.py:843` | `groups_fn=lambda: load_watchlist(wl_path)["groups"]` | 0.12 ms | 每次自選變更 |
| `app.py:1986/2010` | `corr.state()` / `corr.river_snapshot()` | **16 ms** / ? | 每個 REST + WS seed |
| `app.py:1961` | `breadth.rows_state()` 2800 列 | 1.7 + 3.9 ms | 展開列表時 |
| `capital_api.py:259/271/289` | `client.store.orders()/fills()/positions()` | `with threading.Lock` + list 複製 | 每次輪詢 |
| `capital_api.py:191` | `_correct_price_tick_gate` → `client.store.orders()` 線性掃 | 同上 | 改價 |
| `watchlist_service.py:89/115/…` | `load_watchlist` + `save_watchlist` 在 `asyncio.Lock` 內 | 0.12 ms + atomic write | 自選操作 |
| `capital/client.py:396` | `self._audit(record)`(`_on_late_result`,done_callback) | 200 µs + 全域鎖 | 罕見 |

### 5.3 `asyncio.to_thread` 全部 60 處 —— 都在同一個 20-thread 池

| 消費者 | 並行度 | 單次最壞 |
|---|---|---|
| `stock_engine._backfill_worker` | 1 | `prepare_backfill` + 逐檔 `backfill`(SubHistory,秒~30 s) |
| `stock_engine` 訂閱池(`_acquire`/`_release`/`_retry_*`) | 1(受 `_pool_lock`) | `_REQ_TIMEOUT_MS` 10 s |
| `stock_engine.daily_bars`(overlay route) | **≤4**(`overlay_sem`) | `BARS_POLL_DEADLINE` 兩段 = 20 s |
| `stock_engine.bars_range`(`/api/stock/bars`) | **無上限** ★ | 20 s |
| `futures_engine.bars_range`(`/api/market/bars`) | **無上限** ★ | 20 s |
| `index_engine`(bars / MIS / 回補) | 1–2 | 20 s / HTTP 60 s |
| `corr_engine`(subscribe / fetch_day_1k / close) | 1 + retry tasks | 20 s |
| `signal_hub`(`_basis_worker` / jsonl / rules 落檔 / 回填) | 1–2 | 20 s |
| `breadth_engine`(FinMind urlopen ×4) | 1 | HTTP timeout |
| `screen_engine`(FinMind urlopen ×3) | 1 | HTTP timeout |
| `oi_levels` / `stkfut_catalog` | 1 | HTTP / QUERYALLINSTRUMENT |
| **`capital._audit`(下單前 + 下單後)** | 2/單 ★★★ | 200 µs(但排隊上界 = 上面全部) |
| `capital.close`(關機 COM join) | 1 | 5 s |

`bars.py:441` 的註解自己承認:**`build_*` 沒有 inflight dedup** ——
同一個 `code` 的並發請求各自打一次 TC4,各佔一條 worker thread。

---

## 6. Findings 全文

---

### F-01 `CorrState.correlations()` 每秒在 event loop 上整批重算 1800 樣本 —— 16 ms/s 的抖動地板(CRITICAL)

**位置**:`copycat/live/corr_state.py:82-126`;呼叫點 `copycat/server/corr_engine.py:300 tick_once()`
→ `:543 state()`,以及 `app.py:1986` `/api/corr/state`、`app.py:1997` `/ws/corr` seed。

**證據**:

```python
# copycat/live/corr_state.py:82
def _paired_returns(self, leg: str, now: float) -> list[tuple[float, float, float]]:
    base_series = self._series[self._base]
    leg_series = self._series.get(leg)
    ...
    leg_by_ts = dict(leg_series)          # ← 每腿每次建一個 3600 項 dict
    out: list[tuple[float, float, float]] = []
    for ts, base_mid in base_series:      # ← 3600 次迴圈
        leg_mid = leg_by_ts.get(ts)
        if (prev_ts is not None and ... and abs((ts - prev_ts) - self._sample_secs) <= self._adjacent_tol):
            rb = log_return(prev_base, base_mid)   # ← math.log ×2,每點
            rl = log_return(prev_leg, leg_mid)
            ...
    return [row for row in out if row[0] >= now - self._max_window]   # ← 再掃一次

# :113
def correlations(self, now: float):
    for leg in self._legs:                       # 10 腿
        paired = self._paired_returns(leg, now)  # ← 整批重算
        for window in self._windows:             # (60, 300, 1800)
            xs = [rb for ts, rb, _ in paired if ts >= cutoff]   # ← 每窗再掃 1800
            ys = [rl for ts, _, rl in paired if ts >= cutoff]
            row[f"w{window}"] = self._corr(xs, ys, ...)
```

```python
# copycat/server/corr_engine.py:300
def tick_once(self) -> None:      # 由 _run 每 self._tick_secs(prod = 1 s)呼叫
    ...
    self._state.push(now, mids, session)
    self._seq += 1
    if self._broadcast is not None:
        self._broadcast(self.state())      # ← state() 內含 correlations() = 16 ms
```

**實測**:11 腿(`configs/correlation.json`:TXF/TWN/YM/ES/NQ/SXF/NK225M/VX/CL/GC/TSMC)、
窗 (60, 300, 1800)、滿窗 1800 樣本 → **16.043 ms**。
cProfile:`_paired_returns` 佔 83%,`statistics.correlation` 只佔 7%。

**量級與影響**:
- 這是 **每秒一次、每次 16 ms 連續佔住 event loop**。期間:所有 WS 推播停、所有 tick 不處理、
  所有 HTTP route 不推進、**下單請求的 HTTP 解析也停**。
- 等於整個系統有一個 **16 ms 的 p99 延遲地板**,而且是週期性的(每秒同一時刻)。
- 開盤後 ~30 分鐘(w1800 的 min_samples=300 滿足後)成本達到最大值並維持整天。
- 再加上 `/api/corr/state` 與 `/ws/corr` 的 seed 也各付一次 16 ms。
- `corr_state.py` 模組 docstring 的「整輪 tick 外推不到 1 ms」**是錯的**(只量了
  `statistics.correlation`)—— 這是本次稽核最值得記的一條認知落差。

**修法(兩階段,建議先做 a)**:

(a) **不加相依、零數值變動**:把「報酬序列」快取起來,`push()` 時只 append 最新一筆配對報酬
(O(腿數)),`correlations()` 直接對快取序列用 `bisect` 切窗再丟給 `statistics.correlation`。
`statistics.correlation` 仍然是整批算,**浮點結果逐位元相同**,module docstring 反對的
「增量統計量誤差累積」完全沒被觸碰(反對的是增量 *相關係數*,不是增量 *報酬序列*)。
預期 16 ms → **< 1 ms**。`bisect` 已在庫內用過一次。

(b) 若要再壓:`numpy` 的 `np.corrcoef` 對預配置的 ring buffer 切片,16 ms → ~0.15 ms,
但會破壞 runtime stdlib-only 的分界 —— **建議先做 (a),量完再決定要不要 (b)**。

**風險**:`CorrState` 是零 IO 純狀態機,有 `tests/live/test_corr_state.py` 覆蓋。
改動 **不碰任何跨檔契約**(`configs/correlation.json` 腿數、`river-colors.ts` 調色盤、
`/api/corr/state` payload 形狀全不變)。要注意的不變式:
「報酬不跨洞接合」(相鄰取樣秒且兩腿皆有中價才產生一筆)與「時間戳逐出」——
增量版必須在 `push()` 當下用**同一組判準**決定要不要追加那一筆,並在 `_evict` 時同步逐出報酬序列。
建議用現有測試當 characterization,再加一條「增量 vs 整批逐位元相等」的 property 測試。

**effort**:M

---

### F-02 下單審計與全庫 TC4 歷史取數共用同一個 20-thread 預設 executor(CRITICAL,真錢路徑)

**位置**:`copycat/capital/client.py:885`(前置審計)、`:353`(後置審計);
共用池的其他 60 處 `asyncio.to_thread` 見 §5.3。

**證據**:

```python
# copycat/capital/client.py:880-893  _execute_write
        # 前置:寫不進去 → AuditWriteError,錢沒動(to_thread 不卡 loop,review B6)
        await asyncio.to_thread(self._audit, self._record(action, req))   # ← 預設 executor
        fut: asyncio.Future[tuple[str, int]] = self._loop.create_future()
        self._cmd_q.put((com_call, fut))
```

```python
# copycat/server/app.py:1568-1572  —— 這段註解是 codebase 自己已經辨識出這個問題
        # 讀整份當日 jsonl 是同步 IO ... → 丟 worker thread
        # to_thread 走 loop 預設 executor,與 daily_bars / capital close 同池且工作
        # 執行緒不可中斷 —— TC4 半死的殭屍執行緒堆積時這條會跟著排隊(review C-1);
```

```python
# copycat/server/bars.py:441
#   ... 界前唯一走得到「有 stale 可比」的是同 key 併發首抓(build_* 無 inflight ...
#   ^^^^ 無 inflight dedup:同一支 K 線的 N 個併發請求 = N 條被佔住的 worker thread
```

**量級**:
- 池大小 = `min(32, cpu_count()+4)` = **20**(本機實測 cpu=16)。
- 單條 TC4 歷史取數最壞 `BARS_POLL_DEADLINE` 10 s × 2 段 = **20 s**(`app.py:125-127` 明載)。
- 無上限的消費者:`/api/stock/bars/{code}`、`/api/market/bars/{key}` —— 前端每張圖一個 hook,
  圖牆 / 多分頁同時開時併發數不受控;`overlay` 只擋到 4。
- 因此:**21 個同時在飛的 TC4 歷史請求就能讓下單審計排在第 21 位**,最壞等 20 s。
  `_WRITE_TIMEOUT_S` 是 10 s,但那個計時是在**審計完成之後**才開始 —— 使用者看到的是
  route 整條掛住,而不是「結果未知」。
- 這不是理論:`app.py:1571` 已經記錄「TC4 半死的殭屍執行緒堆積」是觀察過的現象。

**修法**:
1. **給下單/審計一條專屬 executor**(最小改動、最高收益):
   ```python
   # capital/client.py
   self._audit_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="capital-audit")
   ...
   await self._loop.run_in_executor(self._audit_pool, self._audit, record)
   ```
   審計是 200 µs 的 append,2 條執行緒綽綽有餘,且永遠不會被行情查詢排隊。
2. **給 TC4 歷史取數一條有上限的專屬 executor**(例如 `max_workers=6`)+ 全庫其餘 `to_thread` 留在預設池。
   這同時把「TC4 殭屍執行緒」的爆炸半徑框住。
3. **`build_daily` / `build_minute` / `build_period` 加 inflight dedup**(per `(code, tf, window)` 的
   `asyncio.Future` 表):同 key 的併發請求共用一趟取數。這是把併發數從「前端有幾個 hook」
   降到「有幾個不同的 K 線」的唯一結構性解。

**風險**:
- (1) 幾乎零風險,只改一個 executor 參數;測試需要新增「審計池不受預設池飽和影響」的整合測試。
- (2) 要確認關機路徑:`shutdown_budget.py::run_grace_secs()` 是三方同源契約
  (`run.ps1` / `__main__.py` / `app.py` lifespan,CLAUDE.md §4「關機預算三方同源」),
  **新增 executor 不改 lane 形狀就不必動 `TC4_LANE_DEPTH`**,但新 pool 要在 lifespan
  收尾時 `shutdown(wait=False)`,否則多一條不會退的執行緒。
- (3) inflight dedup 會改變 `bars.py:441` 註解描述的「同 key 併發首抓」路徑 ——
  那條註解與 `DAILY_FINAL_TIME` 定稿界契約(CLAUDE.md §4)相關,改前要重讀
  `tests/server/test_bars.py`。

**effort**:S(1)/ M(2)/ L(3)

---

### F-03 下單命令與帳務輪詢共用同一條 COM 執行緒,查詢慢 = 送單慢(HIGH,真錢路徑)

**位置**:`copycat/capital/client.py:808-820`。

**證據**:

```python
# copycat/capital/client.py:786-794  _pump_once
    def _pump_once(self) -> None:
        try:
            self._com.pump()
            self._balance.poll()     # 沒等到結束標記的 flush 保險
            self._profit.poll()
            self._oi.poll()
            self._maybe_query_balance()   # ← 會**同步**發 COM 查詢(GetProfitLossGWReport 等)
            self._poll_pending()
        except Exception:
            logger.exception("COM 幫浦圈例外(本輪略過)")
            time.sleep(1.0)          # ← 持續性故障時,整條送單通道停 1 s

# :806-820  _run
            while True:
                self._pump_once()                        # ← 先跑幫浦與查詢
                try:
                    cmd = self._cmd_q.get(timeout=0.05)  # ← 才輪到下單命令
                except queue.Empty:
                    continue
                ...
                result = fn()        # ← 同步 COM 送單
```

**量級**:
- `queue.get(timeout=0.05)` 本身**不是** 50 ms 的輪詢懲罰(`put` 會 notify 立即喚醒),
  真正的延遲是「命令抵達時 `_pump_once()` 正跑到哪」。
- `_maybe_query_balance()` 在 `_balance_inflight_until` 未設時會發一次帳務查詢;
  `_BALANCE_CHAIN_TIMEOUT_S = 10.0`。同步 COM 呼叫的實際耗時**本機無 COM 環境不可量(推測 0.1–3 s)**。
- 成交後有 debounce 重查 → **剛成交的那一刻正是最可能想再下一單的時刻**,
  也正是 COM 執行緒最忙的時刻。
- `except` 分支的 `time.sleep(1.0)` 讓持續性故障時整條送單通道每輪停 1 s。

**修法**(最小且不動架構):
```python
while True:
    # 先把命令佇列清空(非阻塞)——真錢命令優先於帳務輪詢
    while True:
        try:
            cmd = self._cmd_q.get_nowait()
        except queue.Empty:
            break
        ... 執行 ...
    self._pump_once()
    try:
        cmd = self._cmd_q.get(timeout=0.05)
    except queue.Empty:
        continue
    ... 執行 ...
```
更徹底:把 `_cmd_q` 換成 `queue.PriorityQueue`,寫入命令 priority 0、內部輪詢 priority 1。

**風險**:`_pump_once()` 必須在**每次** COM 呼叫之間跑到(COM STA apartment 需要幫浦訊息),
所以不能把幫浦整段搬走 —— 上面的改法保留了幫浦,只把命令提前。
`_drain_pending` 的不變式(執行緒結束時 future 必須 fail)不受影響。
需要 `tests/capital/test_fill_latency.py` 加一條「帳務查詢在飛時命令仍即時執行」的測試。

**effort**:S

---

### F-04 `/api/stock/state/{code}` 全量 tape 的組裝 + 序列化在 event loop 上(HIGH)

**位置**:`copycat/server/app.py:1699`;`copycat/live/stock_state.py:266 snapshot()`。

**證據**:

```python
# copycat/server/app.py:1698-1705
        omit_tape = tape == "0"
        snap = stock.snapshot(key, tape=not omit_tape)   # ← 同步,在 loop 上
        snap["underlying"] = code
```

```python
# copycat/live/stock_state.py:47
    ticks: deque[StockTick] = field(default_factory=lambda: deque(maxlen=_TICKS_MAXLEN))
    # _TICKS_MAXLEN = 20_000
```

**實測**:`snapshot(tape=True)` 對滿載 20,000 筆 = **8.65 ms**;
FastAPI 回應(1.52 MB)端到端 **9.99 ms**,扣掉 HTTP 開銷,序列化約 5 ms。
合計 loop 上連續同步區 **≈ 14 ms**。
對照:`snapshot(tape=False)` 只要 **18 µs**(480 倍差距)。

**量級**:每次切主圖一次;前端 seq 跳號 refetch 也走這條(`useStockStream`)。
2330 這種大量股當日成交筆數超過 20,000 是常態 → 幾乎恆為最壞值。
14 ms 期間全站停拍(含 WS 心跳、下單 route)。

**修法**:
1. **把 tape 序列化移出 loop**:route 改回 `Response(content=await asyncio.to_thread(json.dumps, snap),
   media_type="application/json")`。注意 `snapshot()` 本身有副作用(`_flush_ticks`),
   **必須在 loop 上先取快照,只把 `json.dumps` 丟 thread**。
2. **`snapshot(tape=True)` 的 8.65 ms 本身**:20,000 次 `{"t":..,"p":..,...}` dict 建構是主成本。
   可改成在 `ingest()` 當下就把 tick 的 wire dict 存進 deque(空間換時間,一次建構、多次讀),
   或直接把 tape 改成欄式(`{"t":[...],"p":[...],...}`)—— 後者會改 wire 形狀,
   **踩到 CLAUDE.md §4「個股 `seq` 的兩個口徑」契約**:前端 `lib/stock-accum.ts::fromSnapshot`
   由尾回推指派 React key `n`,欄式改造要同動兩邊 + `useStockStream.test.ts`。
3. **最便宜的一招**:前端在主圖已有 accum 時只要增量,不要每次拉全量 2 萬筆。
   但這是前端 scope,留給 F1/F2 區塊。

**風險**:
- 修法 1 零契約風險,只要保住「取快照在 loop 上、序列化在 thread 上」的順序(`snapshot()` 非唯讀,
  docstring 已明載「只能在 event loop 上呼叫」)。
- 修法 2 會動 wire 形狀 → 踩 §4 seq 契約 + 前端 `stock-accum.ts` 兩條路徑,**不建議這一輪做**。

**effort**:S(修法 1)/ L(修法 2)

---

### F-05 K 線 route 無併發上限、無 inflight dedup,單條請求最壞佔住 worker 20 秒(HIGH)

**位置**:`copycat/server/app.py:1519`(`/api/stock/bars/{code}`)、`app.py:1782`(`/api/market/bars/{key}`);
`copycat/server/bars.py:441` 自承無 inflight;`copycat/live/tc4.py:51 BARS_POLL_DEADLINE = 10.0`。

**證據**:

```python
# copycat/server/app.py:544-547  —— overlay 有擋,bars 沒有
    # overlay 的 TC4 歷史取數節流 ... `daily_bars` 走 `to_thread` 沒有上限、整組(上限 150 條)
    # 請求共用同一條 TC4 歷史通道。
    overlay_sem = asyncio.Semaphore(4)
```

```python
# copycat/server/app.py:1531  —— 這條沒有 semaphore
            bars, status = await build_daily(stock.bars_range, bars_cache, code, today)
# :1541
            bars, status = await build_minute(stock.bars_range, bars_cache, code, ...)
# :1872  /api/market/bars 同理
            bars, status = await build_minute(plain_with_status, bars_cache, code, ...)
```

```python
# copycat/live/stock_source.py:853-869
            rows, timed_out = self._collect_history(sym, "1K", start, end, BARS_POLL_DEADLINE)
            ...
        dk_rows, dk_timed_out = self._collect_history(sym, "DK", dk_start, end, BARS_POLL_DEADLINE)
        # 兩段各 10 s → 單次最壞 20 s,且工作執行緒不可中斷
```

**量級**:每條佔一個 worker thread 最多 20 s。前端常開的 K 線 hook:個股分 K、個股日 K、
期貨分 K、期貨日 K、加權分 K、加權日 K、櫃買 —— 多分頁 × 多 tab 即可輕鬆超過 10 條併發。
加上 `overlay_sem` 的 4 條、backfill worker、signal basis worker、breadth、screen,
**20 條池滿是可達到的**。池滿之後所有 `to_thread` 排隊 —— 含 F-02 的下單審計。

**修法**:
1. 給 bars route 一個 `asyncio.Semaphore`(建議 6,與 overlay 的 4 分開帳)。
2. inflight dedup:`dict[key, asyncio.Future]`,同 key 併發共用一趟。
3. 搭配 F-02(2) 的專屬 TC4 executor,用 `max_workers` 做第二道硬上限。

**風險**:`bars.py:441` 的註解明講「同 key 併發首抓」是「有 stale 可比」那條路唯一走得到的路徑,
而那與 `DAILY_FINAL_TIME` 定稿界契約(CLAUDE.md §4,前後端同值 14:00)交織。
加 dedup 前要先讀 `tests/server/test_bars.py::test_daily_final_time_parity_with_frontend`
以及 `_daily_stale_or_empty` 的分支。加 semaphore 則無契約風險,但要注意
`/api/stock/overlay` 的 `OVERLAY_FETCH_TIMEOUT_S = 15.0` 與新 semaphore 的 head-of-line 互動。

**effort**:S(semaphore)/ M(dedup)

---

### F-06 34 條 route 全是 `async def` —— FastAPI 執行緒池完全沒被用到(HIGH,是設計選擇也是風險集中點)

**位置**:`copycat/server/app.py` 全部 34 個 route + `capital_api.py` 13 個 + `oi_levels.py` 1 個。

**證據**(掃描結果,`grep -A1 '@app.'`):全部 48 個 handler **無一例外**都是 `async def`。

```
copycat/server/app.py-1290-    async def health(...)
copycat/server/app.py-1315-    async def calendar(...)
...
copycat/server/capital_api.py-233-async def capital_status(...)
```

**量級與影響**:
- 「有幾個同步 route 會排隊在 FastAPI threadpool?」的答案是 **0 個**。
- 但反面是:**沒有任何一條 route 有 event loop 之外的執行位置**。上面 F-01/F-04 的每一毫秒
  都直接變成全站延遲。這在「看盤 + 下實單」的場景下是把所有雞蛋放一個籃子。
- Windows 上沒有 uvloop,`ProactorEventLoop` 的 `call_soon_threadsafe` 每次都對 self-pipe socket
  做一次 `send()`(實測往返 11.5 µs)—— 每 tick 一次。3,000 tick/s 時是 34 ms/s 的純交棒成本。

**建議**(這不是「要改成同步 route」,而是三件事):
1. 把重的同步工作明確標記出來並丟 thread(F-01/F-04 已涵蓋)。
2. 加一條 **event loop lag 監控**:一條 `asyncio.sleep(0.05)` 的 task,量實際醒來時間與 0.05 的差,
   超過門檻印 WARNING(固定 grep 字串)。這是目前**完全缺席**的可觀測性 —— 現在
   「畫面卡了一下」沒有任何後端訊號。
3. Windows 上可考慮 `WindowsSelectorEventLoopPolicy`(Proactor 的 `call_soon_threadsafe`
   走 socket,Selector 走 self-pipe;差異需實測)—— **但 Proactor 是 3.8+ 的 Windows 預設
   且 subprocess 支援較好,不要為了沒量過的收益去換**。

**effort**:S(監控)

---

### F-07 `threading.Timer` 每檔一條執行緒:150 檔自選 = 最多 150 條執行緒(MEDIUM)

**位置**:`copycat/live/stock_source.py:642`。

**證據**:

```python
# copycat/live/stock_source.py:640-651
    def _arm_health_check(self, code: str, delay: float, *, attempt: int) -> None:
        """排下一發健檢,並**換掉**這個 code 上待觸發的那一把(疊鏈是 C-4 的根因)。"""
        timer = threading.Timer(delay, self._health_check, args=(code, attempt))
        timer.daemon = True
        with self._timer_lock:
            old = self._no_data_timers.get(code)
            if old is not None:
                old.cancel()
            ...
            self._no_data_timers[code] = timer
        timer.start()      # ← threading.Timer 是 Thread 子類:一個 timer = 一條執行緒
```

`_arm_health_check` 的呼叫點:`subscribe_symbol` 之後(`:638`)以及 `_health_check` 的退避重排(`:706`)。
自選上限 = 150(`stock_watchlist.py::WATCHLIST_LIMIT`,CLAUDE.md §4 契約)。

**量級**:
- 開盤時 150 檔逐一訂閱 → **150 條 Timer 執行緒**同時 sleep 10 s。
- 退避階梯 10→20→40→60 s 期間對「真的零推播」的檔會持續維持一條執行緒。
- Windows 每條執行緒保留 1 MB stack(lazy commit)。150 條在功能上可行,但這是
  「每個定時器一條 OS 執行緒」這種本不該存在的成本 —— 且每次 `_health_check` 觸發時
  會在**該 Timer 執行緒上**發 ZMQ REQ(`_heal_resub`),與 `api.lock` 競爭。

**修法**:換成單一排程執行緒 + `heapq`(stdlib,零相依):
一條 daemon thread、一個 `(deadline, code, attempt)` 的小根堆、`threading.Condition.wait(timeout)`。
`_arm_health_check` 只是 push/replace,`cancel` 只是標記失效。150 條執行緒 → 1 條。

**風險**:`close()` 的 timer 全取消語意(`:663-666`)與 `_stop` 早退(`:683`)必須保住 ——
兩道防線都是刻意的。`tests/live/test_stock_source.py` 有對應覆蓋,改法要以 characterization 先鎖。

**effort**:M

---

### F-08 `_handle_quote` 每則行情做 2 次 `datetime.now()+strftime`(MEDIUM,純浪費)

**位置**:`copycat/server/stock_engine.py:92-99`(`_now_taipei_time`)、`:151-162`(`_observe_window_now`)、
`:683-703`(`_trial_now`)、`:1402`(`_observe_trade_status` 每則呼叫)。

**證據**:

```python
# copycat/server/stock_engine.py:92
def _now_taipei_time() -> str:
    return f"{_dt.datetime.now():%H:%M:%S.%f}"[:-3]     # 實測 2.52 us

# :151
def _observe_window_now() -> bool:
    return is_trial_window(_now_taipei_time(), _OBSERVE_WINDOWS)   # 實測 2.94 us

# :1398-1403  —— 每一則 REALTIME 都走
        status = str(quote.get("TradeStatus", "0") or "0")
        qty = quote.get("TradeQuantity") or "-"
        in_window = _observe_window_now()      # ← 每則一次,不論會不會用到
        prev = self._trade_status.get(code)
        if prev is None: ...
        prev_status, episode = prev
        if status == prev_status:
            return                              # ← 絕大多數在這裡早退,in_window 白算
```

**量級**:`datetime.now()` 本身只要 0.17 µs,**格式化才是 2.35 µs**(14 倍)。
`in_window` 在同值早退之前就算了 → 每則行情固定付 2.94 µs。
3,000 則/s 時 = 8.8 ms/s;加上 `_quote_payload` 裡的 `_trial_now`(1 s flush × 150 檔 × 2 次)。

**修法**:
1. `in_window = _observe_window_now()` **移到 `if status == prev_status: return` 之後**
   (它只在轉態與首見兩條路上被讀)。零行為改變,省掉 99% 的呼叫。
2. `_now_taipei_time()` 加一個 **per-loop-iteration 的毫秒級快取**:
   同一則 quote 內多次呼叫共用同一個時刻字串(語意上本來就該是同一刻,現在是三個略不同的值)。
   注意:`stock_engine.py:113-119` 的 docstring 明講「窗與日的時鐘是兩顆」且測試會分別 monkeypatch
   **模組屬性** —— 快取必須維持模組級函式的可 patch 性,否則測試會靜默沿用真牆鐘。

**風險**:修法 1 零風險(純移位,`in_window` 在早退分支後沒有任何讀者)。
修法 2 要小心 `_OBSERVE_GRACE_SECS` 2 s 寬限與 `TRIAL_WINDOWS` 邊界 ——
`TestObserveClockContract` 釘死了邊界語意。

**effort**:S(1)/ M(2)

---

### F-09 `backfill_policy_outcomes` 逐列 `json.loads` / `json.dumps` 在 event loop 上(MEDIUM,低頻)

**位置**:`copycat/server/signal_hub.py:1294-1383`。

**證據**:

```python
# copycat/server/signal_hub.py:1294-1299   —— async def 內的同步檔案操作
        if not signal_dir.exists():                    # stat
            ...
        for path in signal_dir.glob("*.jsonl"):        # 目錄列舉
# :1317   讀檔有丟 thread(好)
            raw = await asyncio.to_thread(path.read_bytes)
# :1331-1337   但逐列解析在 loop 上
            for i, line_bytes in enumerate(lines):
                line = line_bytes.decode("utf-8")
                row = _policy_row_needing_outcome(line)    # ← 內含 json.loads,每列一次
# :1378
                        lines[i] = (json.dumps(row, ensure_ascii=False) + eol).encode("utf-8")
# :1381   寫檔有丟 thread(好)
                await asyncio.to_thread(atomic_write_bytes, path, b"".join(lines))
```

**量級**:實測一日 jsonl(289 KB / 686 列)的逐列 `json.loads` = **6.19 ms**。
`policy_outcome_days` 個日檔 → 例如 5 天 = **~31 ms 的 loop 停拍**,每日 13:40 一次。
低頻但落在盤後尾盤(13:40),不是無害時段。

**修法**:把整段「逐列 decode + `_policy_row_needing_outcome` + 重組 lines」搬進**同一個**
`asyncio.to_thread`(讀檔、解析、重組、寫檔一趟),只把「取日 K」那段(要 `await`)留在 loop 上 ——
拆成「掃描(thread)→ 取 K(loop/await)→ 套用+寫回(thread)」三段。

**風險**:這段有**逐位元組契約**(CLAUDE.md §4「T+1/T+2 回填原地補欄 + 離線讀者契約」):
「只重寫被補的列,其餘列原文逐字保留、行尾原樣、`atomic_write_bytes` 覆寫」。
`tests/server/test_signal_outcome.py` 做 byte 比對。搬動時**不可改變任何 encode/decode 順序**。

**effort**:M

---

### F-10 `/api/stock/names` 每次請求重讀 59 KB JSON + 重建 2401 個 dict(MEDIUM)

**位置**:`copycat/server/app.py:1454-1462`;`copycat/stock_names.py:116`。

**證據**:

```python
# copycat/server/app.py:1454-1462
    @app.get("/api/stock/names")
    async def stock_names() -> dict:
        names = load_stock_names(names_path)          # ← 每次讀檔 + json.loads
        return {
            "names": [{"code": code, "name": name} for code, name in names.items()],  # 2401 dict
            "count": len(names),
        }
```

**實測**:`load_names()` 0.81 ms + payload 組裝 0.23 ms + 序列化 0.63 ms ≈ **1.7 ms**,全在 loop 上。

**量級**:每次開站一次、搜尋提示列可能重打。單次 1.7 ms 不致命,但這是
**版控檔、內容一天不變**卻每次重算的典型浪費。

**修法**:module-level 或 app-level 快取(帶 mtime 檢查),payload 一次組好存起來。
`_CACHE_VERSION` 慣例已在庫內(CLAUDE.md §4「Cache version bump」)。

**風險**:`load_names` 的降級語意是「任何讀取/格式問題都回 `{}`」且 route 承諾不 500 ——
快取要保住「壞檔 → 空表」這條,且 `refresh-stock-names` CLI 寫檔後要能被下次讀到
(mtime 檢查即可)。

**effort**:S

---

### F-11 `WatchlistService` 在 `asyncio.Lock` 內做同步讀檔 + atomic 寫檔(LOW-MEDIUM)

**位置**:`copycat/server/watchlist_service.py:81-84, 89, 115, 209-227`。

**證據**:

```python
# copycat/server/watchlist_service.py:75-84
    async def apply(self, wl: Watchlist) -> Watchlist:
        async with self._lock:
            pending = self._commit(wl)     # ← 同步:normalize + load(比對) + save(atomic write)
        saved, _ = await self._settle(pending)   # ← 鎖外,正確

# :209-227  _commit(持鎖)
        desired = normalize(wl)
        if desired == self._current_canonical():   # ← load_watchlist 讀檔 120 us
            return desired, False, None
        saved = save_watchlist(self._path, desired)  # ← tmp write + os.replace
```

**量級**:讀 120 µs + 寫(tmp + `os.replace`)推測 0.5–2 ms。每次自選操作一次。
**架構上這一段已經做對了最難的部分**:`_settle`(ZMQ 訂閱迴圈,最壞數十秒)在鎖外
(`:228` docstring 詳述 X-3 / N111 的收斂)。剩下的檔案 IO 是小頭。

**修法**:低優先。若要做,把 `_commit` 整段丟 `to_thread`(它是純同步函式),
但要保住「取號在鎖內」的 X-3 不變式 —— 序號遞增必須與落檔同一個原子區。
建議:**這條只記錄,不動**。

**effort**:S(但收益低)

---

### F-12 `notify.py` 的 429 重試用 `time.sleep`,只靠 caller 記得丟 thread(LOW,潛在陷阱)

**位置**:`copycat/notify.py:105`。

**證據**:

```python
# copycat/notify.py:103-106
            sleep(min(delay, _RETRY_AFTER_CAP))     # ← time.sleep,同步
            try:
                return _post(url, data)
```

呼叫點盤點:
- `signal_hub.py:1563` `await asyncio.to_thread(self._notify_fallback, text)` — **正確**
- `app.py:834` `notify_fallback=notify_discord` — 注入給 hub,走上面那條
- `cli.py:354` — CLI,同步本來就對

**判定**:**目前全部正確**,但這是一顆地雷:`notify_discord` 的簽名看不出「絕不可在 loop 上呼叫」。
`_TIMEOUT` + `_RETRY_AFTER_CAP` 加起來可以是數秒的 loop 停擺。

**修法**:在 `notify_discord` 的 docstring 第一行加上「**同步阻塞,呼叫端必須 `to_thread`**」,
或更硬的:加一道 `asyncio.get_running_loop()` 偵測,在 loop 上被呼叫時 `logger.error` 一次。

**effort**:S

---

### F-13 `audit.append_audit` 的 module-level 鎖橫跨 open+write+flush,且有一條在 loop 上的呼叫者(LOW)

**位置**:`copycat/server/audit.py:15, 29-38`;loop 上的呼叫者 `copycat/capital/client.py:396`。

**證據**:

```python
# copycat/server/audit.py:15
_audit_lock = threading.Lock()
# :31-37
        with _audit_lock:
            base.mkdir(parents=True, exist_ok=True)      # ← 每次都 mkdir(stat)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
```

```python
# copycat/capital/client.py:394-398  —— _on_late_result 是 done_callback,跑在 event loop 上
        try:
            self._audit(record)          # ← 同步 append_audit,在 loop 上
        except Exception:
            logger.exception(...)
```

**量級**:實測 open+write+close = **200 µs**(不含 `flush()` 與 `mkdir`,加上約 300 µs)。
`_on_late_result` 是罕見路徑(逾時 / 取消後晚到),docstring 已標「罕見路徑可接受」。
鎖持有時間 ~300 µs,對 COM 執行緒與 executor 的競爭可忽略。

**判定**:**不必動**,但 `base.mkdir(parents=True, exist_ok=True)` 每次都做是無謂的 stat;
移到第一次寫入時做一次即可省 ~30%。真要改 F-02(1) 時順手。

**effort**:S

---

### F-14 `EngineRuntime._consume` 每 50 ms 建一次 `wait_for` timeout(LOW)

**位置**:`copycat/server/engine.py:377-393`。

**證據**:

```python
# copycat/server/engine.py:377-386
    async def _consume(self) -> None:
        while True:
            if self._paused:
                await asyncio.sleep(0.01)
                continue
            try:
                tick = await asyncio.wait_for(self._queue.get(), timeout=0.05)
            except TimeoutError:
                await self._maybe_self_heal()
                continue
```

**量級**:每則 TXO tick 多付一次 `wait_for` 的 timeout 物件建構(Python 3.12+ 走
`asyncio.timeouts.timeout`,成本已大幅下降)。TXO 鏈盤中 tick 率不高(**推測** < 100/s)。
閒置時每 20 次/s 醒來跑 `_maybe_self_heal()`。

**判定**:**收益太小,不建議動**。若真要:把「自癒巡檢」拆成獨立的 1 s task,
`_consume` 就變成裸 `await queue.get()`。但這會改變「rollover 由 timeout 分支天然補跑」
(`:408-410` 註解明載的不變式),風險 > 收益。

**effort**:M(不建議)

---

### F-15 `WsBroadcaster.publish` 讓每個 client 各自序列化同一則訊息(LOW-MEDIUM)

**位置**:`copycat/server/ws.py:65-80`(publish 放的是同一個 dict 物件)、`:262-265`(`_send`)。

**證據**:

```python
# copycat/server/ws.py:65-69
    def publish(self, msg: dict) -> None:
        self._settle_drop_window(time.monotonic())
        for queue in self._clients:
            queue.put_nowait(msg)          # ← 同一個 dict 物件進每條 queue

# :262-265
    async def _send() -> None:
        async for msg in stream:
            async with send_lock:
                await websocket.send_json(msg)   # ← starlette: json.dumps(msg) 每 client 各一次
```

**量級**:8 條 WS 軸 × N 個瀏覽器分頁。`index.state()` 含 ~280 分鐘 × 2 指數,每秒推一次;
`corr.state()` 每秒一次。單則序列化 **推測** 0.3–1 ms,3 個分頁 = 每秒多 2 ms。
`ticks` 打包則很小(0.1 s 一則、幾十筆)。

**修法**:在 broadcaster 層序列化一次(`json.dumps` → str),`relay` 改用
`websocket.send_text(cached)`。訊息是不可變的(codebase 已有「payload 到消費端只被序列化,
不被就地改」的慣例,`stock_engine.py:67`)。

**風險**:`ws.py` 的 `relay` 是 8 條 WS 的**唯一**送出路徑,`send_json` 換 `send_text`
要同時改 `WsConnection` Protocol(`:145-154`)與所有 fake。心跳 `PING` 也走 `send_json`。
`send_seed`(route 層自送的首則)是另一條路徑,要一起想。收益中等、觸面廣 ——
**建議排在 F-01/F-02/F-04 之後**。

**effort**:M

---

### F-16 缺少 event loop lag 的可觀測性(MEDIUM,不是效能問題但是「查不出效能問題」的根因)

**位置**:全庫無。

**證據**:`/api/health` 只回 `build_info`(`app.py:1289-1296`,docstring 明講「刻意不含引擎健康度」);
`WsBroadcaster.dropped` 是唯一與「跟不上」相關的計數,但它量的是 **client 端慢**,
不是 **loop 慢**(`ws.py:56-63`;`/api/health` 刻意不含)。

**影響**:F-01 的 16 ms/s 完全沒有任何後端訊號 —— 它在 log、health、jsonl 裡都不存在。
本次稽核是靠**離線微基準**才量出來的。真要做效能改造,第一步就該是把這個補上。

**修法**:
```python
async def _loop_lag_probe(threshold=0.05):
    while True:
        t0 = time.perf_counter()
        await asyncio.sleep(0.05)
        lag = time.perf_counter() - t0 - 0.05
        if lag > threshold:
            logger.warning("event-loop-lag %.1f ms", lag * 1000)   # 固定 grep 前綴
```
外加把 p50/p95/max 存成屬性,由 `/api/health` 或新的 `/api/perf` 吐出。
命名建議沿 `trade-status-observe` 的「固定 grep 前綴」慣例(`stock_engine.py:126`)。

**effort**:S

---

## 7. 最壞情況排隊分析(問題 6)

**問:一個 request 進來,最壞會被幾個鎖 / threadpool 排隊?**

以 `POST /api/capital/order/stock`(真錢)為例,逐段列出:

| # | 等待點 | 最壞值 | 依據 |
|---|---|---|---|
| 1 | 進入 event loop 的排程延遲(前面有 F-01 的 16 ms 同步區 / F-04 的 14 ms) | **~30 ms** | 實測 16.0 + 14.0 |
| 2 | `await to_thread(self._audit, ...)` 排在預設 executor 佇列後面 | **20 s** | 20 worker 全被 `BARS_POLL_DEADLINE` 2 段 = 20 s 的 TC4 歷史取數佔滿(F-02/F-05) |
| 3 | 審計自身(全域 `_audit_lock` + open/write/flush) | 0.3 ms | 實測 200 µs |
| 4 | `_cmd_q` → capital-com 執行緒正在 `_pump_once()` 的同步 COM 查詢裡 | **推測 0.1–3 s** | `_BALANCE_CHAIN_TIMEOUT_S = 10.0`(F-03) |
| 5 | 同步 COM 送單 | 券商決定 | — |
| 6 | `wait_for(shield(fut), timeout=_WRITE_TIMEOUT_S)` | 10 s 後回「結果未知」 | `client.py:891` |
| 7 | `await _audit_after` 再排一次 #2 | **20 s** | 同 #2 |
| | **合計最壞** | **~50 s**(健康時 ~1–5 ms + 券商往返) | |

**鎖的數量**:1 個(`_audit_lock`,µs 級)。
**threadpool 排隊次數**:**2 次**,兩次都在同一個被行情查詢佔滿的 20-thread 池裡。
**event loop 同步區阻擋**:每秒 16 ms(F-01)必然撞到,加上使用者操作引發的 14 ms(F-04)。

再看一個純讀路徑 `GET /api/stock/state/2330?contract=CDF:202609`:

| # | 等待點 | 最壞值 |
|---|---|---|
| 1 | loop 排程(F-01 / F-04) | ~30 ms |
| 2 | `catalog.contains` → `to_thread(QUERYALLINSTRUMENT)`(冷 cache) | 池排隊 20 s + 查詢秒級 |
| 3 | `async with self._pool_lock`(與 PUT watchlist / `_retry_round` 競爭) | 每項 ≈ `api.lock` 等待 + `_REQ_TIMEOUT_MS` ≈ **20 s**(`stock_engine.py:505-510` 明載) |
| 4 | 鎖內 3 × `to_thread`(acquire / release / release_stkfut) | 各 20 s 池排隊 + 10 s REQ |
| 5 | `stock.snapshot(tape=True)` + 序列化(loop 上) | 14 ms |
| | **合計最壞** | **>60 s** |

> `stock_engine.py:505-510` 自己就寫著:「TC4 故障時單檔 SUBQUOTE 要等 `_REQ_TIMEOUT_MS`(10 s)才失敗,
> 整段持鎖會讓第二個寫入者等整段迴圈 —— 150 檔就是 500 s ... 逐項取鎖之後,等待上界降到
> 『當下這一檔』(≈ `_api_lock` 等待 + `_REQ_TIMEOUT_MS` ≈ 20 s)」。
> **這條已經被改善過一輪,結構是對的;剩下的上界來自 ZMQ IO 仍在鎖內**(該檔明載為 next-time)。

---

## 8. 工具選型建議與取捨

| 工具 | 用在哪 | 解決什麼 | 代價 | 判定 |
|---|---|---|---|---|
| **專屬 `ThreadPoolExecutor`(stdlib)** | `capital/client.py` 審計池;TC4 歷史取數池 | F-02:真錢路徑不再排在行情查詢後面;TC4 殭屍執行緒爆炸半徑封口 | 零相依;關機要多收一個 pool(與 `shutdown_budget` 契約無衝突,不改 lane 形狀) | **強烈建議導入** |
| **`bisect`(stdlib)+ 報酬序列快取** | `live/corr_state.py` | F-01:16 ms → <1 ms,**浮點結果逐位元不變** | 零相依;要新增「增量 vs 整批相等」的 property 測試 | **強烈建議導入** |
| **`heapq` 單執行緒排程器(stdlib)** | `live/stock_source.py` 健檢 timer | F-07:150 執行緒 → 1 | 零相依;要保住 `close()` / `_stop` 兩道防線 | **建議導入** |
| **event loop lag probe(自寫 ~15 行)** | `server/app.py` lifespan | F-16:目前完全看不見 loop 停拍 | 零相依;固定 grep 前綴 | **強烈建議導入(第一步)** |
| `numpy` | `corr_state` / `market_breadth` / 回測 | F-01 再壓一個量級(16 ms → 0.15 ms);回測的手刻迴圈 | **破壞 `dependencies = []` 的 stdlib-only runtime 分界**;Windows wheel 無問題;但 corr 做完快取後已無此需要 | **有條件導入** —— 先做 stdlib 版量測,若 <1 ms 就不必;回測/離線層(`backtest/`)另案評估,那裡是離線不塞 loop |
| `orjson` / `msgspec` | FastAPI `ORJSONResponse`;WS `send_text` | F-04/F-15 的序列化 5–13 ms → ~1–2 ms | 新增 runtime 相依;FastAPI ≥0.100 對 `-> dict` 已走 pydantic-core(Rust),**實測端到端只有 10 ms 不是 137 ms**,實得收益約 5–8 ms | **有條件導入** —— 收益比想像小,排在 F-01/F-02/F-04(修法1)之後再量 |
| `uvloop` | uvicorn loop | 降 loop 開銷 | **Windows 不支援**(本專案 §「部署前置」明確綁 Windows) | **不建議(不可用)** |
| `httpx` / `aiohttp` 取代 `urllib` | breadth / screen / oi-levels / mis / notify | 把 5 處外呼從 to_thread 改成原生 async,釋出 worker | aiohttp 已因 discord.py 在環境裡;但這 5 處**都已經正確 to_thread**,且頻率低(5 s ~ 每日一次) | **不建議** —— 真正的池壓力來自 TC4 歷史取數(ZMQ 同步,換 HTTP 客戶端救不到) |
| `redis` / `duckdb` | 狀態 / 快取 | — | 專案明確「沒有 DB」(CLAUDE.md §5),單機單進程 | **不建議** |
| `numba` | — | — | JIT 暖機 + Windows 相容性 + 與 stdlib-only 哲學衝突;本區塊沒有任何一處是「數值密集到需要 JIT」 | **不建議** |

---

## 9. 不要動的地方(反向結論)

1. **`_Tee` 的 per-write flush**(`server/__main__.py:88-97`)。
   我原本預期這是每行 log 的同步磁碟寫入災難 —— **實測只有 4.85 µs**(OS page cache 吸收)。
   而它換來的是「crash 當下 log 已落盤」這個排查價值。**不要動。**

2. **`_append_jsonl` 的 open+append+close 每列一次**(`signal_hub.py:1412-1418`)。
   200 µs/列,但它在 `to_thread` 裡,而一天只有 ~686 列。保持檔案不長開的好處
   (外部工具可隨時讀、crash 不掉資料)遠大於 200 µs。**不要動。**

3. **`WatchlistService` 的 `_settle` 在鎖外**(`watchlist_service.py:228-253`)。
   這一段已經被 X-3 / N111 兩輪改過,把「鎖凸出」收斂掉了,結構正確。
   剩下的 `_commit` 檔案 IO 是 0.1–2 ms 的小頭。**不要再優化。**

4. **`asyncio.to_thread` 的使用本身**。60 處 `to_thread` 全部用對了地方
   (ZMQ REQ、檔案、urlopen 一律離開 loop)。問題不是「用得不夠」而是「共用一個池」(F-02)。
   **不要把它們改成別的東西。**

5. **`EngineRuntime._consume` 的 50 ms `wait_for`**(F-14)。
   改它會動到「rollover 由 timeout 分支天然補跑」這條寫在註解裡的不變式(`engine.py:408-410`),
   而 TXO tick 率不高。**風險 > 收益,不要動。**

6. **`WsBroadcaster` 的「滿了丟最舊、保最新」**(`ws.py:65-80`)。
   這是對行情/回報語意正確的反壓策略(最新才有意義),而且有 `dropped` /
   `window_dropped` 的可觀測性與 60 s 節流 WARNING。**不要改成阻塞式反壓。**

7. **`_pump_once()` 的 COM 幫浦本身**。COM STA apartment 必須幫浦訊息,
   不能為了「送單優先」把它整段搬走 —— F-03 的修法只是把命令提前,幫浦照跑。

8. **全 route `async def`**。不要為了「丟給 threadpool」把 route 改成 `def` ——
   那只是把 20 條 worker 的競爭再加一組,而且會讓 `_pool_lock` 這類 asyncio 鎖失效。

---

## 10. 量測方法(要證明改動有效,怎麼量)

### 10.1 離線基準(已建立,可重跑)

```
scratchpad/arch-scan/bench_x1.py    # 序列化 / 解析 / 檔案 / threadpool / call_soon_threadsafe
scratchpad/arch-scan/bench_x1b.py   # FastAPI 回應序列化端到端
scratchpad/arch-scan/bench_x1c.py   # corr correlations / breadth rows
scratchpad/arch-scan/scan_async.py  # AST:async def 內的同步呼叫
```
跑法(唯讀、不碰 repo、不連 TC4):
```
cd C:\side-project\copycat
$env:PYTHONUTF8=1; .venv\Scripts\python.exe <script>
```

### 10.2 F-01 的專項驗收

```
# 改動前後同一支 bench_x1c.py,同一組 1801 樣本 × 11 腿
CorrState.correlations(now)   16.043 ms  →  目標 < 1.0 ms
# 數值不變證明(必要):
#   對同一份序列,新舊實作的 correlations() 結果逐 key 逐位元相等(repr 比對,不是 isclose)
```

### 10.3 線上探針(建議先於任何改動落地 —— 見 F-16)

```python
# copycat/server/app.py lifespan 內加一條 task
async def _loop_lag_probe():
    while True:
        t0 = time.perf_counter()
        await asyncio.sleep(0.05)
        lag = (time.perf_counter() - t0 - 0.05) * 1000
        _lag_hist.add(lag)
        if lag > 20.0:
            logger.warning("event-loop-lag %.1f ms", lag)
```
盤中判準(改動前後對照):
```
grep -c "event-loop-lag" logs/server-*.log          # 改動後應大幅下降
grep "event-loop-lag" logs/server-*.log | sort -k5 -rn | head   # 最大 lag
```
預期:F-01 修前每秒一發 16 ms(門檻設 10 ms 時每秒命中),修後歸零。

### 10.4 threadpool 飽和探針(F-02 驗收)

```python
# 一條 1 s task,量 to_thread 的排隊時間
t0 = time.perf_counter()
await asyncio.to_thread(lambda: None)
queue_wait_ms = (time.perf_counter() - t0) * 1000   # 空閒 = 0.09 ms
```
盤中判準:`queue_wait_ms > 500` 即代表預設池已飽和。
改動後(專屬審計池)的判準:**審計池的 queue_wait 恆 < 1 ms,即使預設池的 > 5000 ms**。

### 10.5 下單延遲端到端(F-03 驗收)

`capital/client.py` 已有 `_fill_seen_at` 與「自成交起 N ms」的觀測慣例。
建議在 `_execute_write` 加三段計時,印成一行固定前綴:
```
order-latency action=stock audit=0.3ms com_queue=12.4ms com_call=145.0ms total=157.7ms
```
盤中判準:`com_queue` 的 p95 在修 F-03 前後對照(修前應與帳務查詢節奏相關)。

### 10.6 tick 吞吐上界(推測值需驗證)

目前「盤中 300–3,000 則/s」是推測。實測法:`tc4.py` 的 `handle_raw` 加一個每 10 s 印一次的計數器,
或 `stock_engine._handle_quote` 入口加計數 + `/api/health` 吐出。
沒有這個數字,「parse_stock_realtime 22.7 µs 到底佔 loop 幾 %」就只能是推測。

---

## 11. 硬約束(改動時必須同動的跨檔契約)

引用 CLAUDE.md §4,與本區塊改動相關的條目:

| 契約 | 與哪條 finding 相關 | 注意 |
|---|---|---|
| **個股 `seq` 的兩個口徑** | F-04 修法 2(tape 欄式化) | `stock_state.py::ingest/snapshot` ↔ 前端 `stock-accum.ts::fromSnapshot`(由尾回推 React key)。**不要在這一輪動 wire 形狀** |
| **`/api/stock/state/{code}?tape=0` 字面值 + `tape_omitted`** | F-04 | 後端只認字串 `"0"`;前端 `useStockStream.ts::stateUrl` / `stock-accum.ts::fromSnapshot` |
| **個股逐筆 = `ticks` 打包訊息**(`tick_flush_secs` 0.1 s) | F-15(WS 序列化)/ F-04(`_flush_ticks` 副作用) | `_flush_ticks` 只能在 event loop 上呼叫;`snapshot()` / `group_snapshot()` 取值前必 flush(pr-187 review #1 的兩道閘) |
| **江波圖調色盤色數 ≥ 相關係數腿數** | F-01 | 改 `corr_state` 不動腿數就不觸發;若順手加腿要同動 `configs/correlation.json` + `corr_config.DEFAULT_CONFIG` + `river-colors.ts` + `index.css` token |
| **相關係數稀疏腿 `sparse` 旗標** | F-01 | 只影響 source 層自癒,`CorrState` 不讀 —— 改 correlations 不觸發 |
| **關機預算三方同源**(`shutdown_budget.run_grace_secs()` = 83 s) | F-02(新 executor) | 新 pool 若不改 lane 形狀就不動 `TC4_LANE_DEPTH`;但要在 lifespan 收尾 `shutdown(wait=False)`,由 `tests/server/test_shutdown_budget.py` 的字面 parity 守著 `run.ps1` |
| **自選上限常數多邊同值(150)** | F-07(150 條 Timer 執行緒)、F-04 | 效能預算註解(`stock_engine` / `watchlist_service` / `stock_state` / `GroupGridView`)已改寫成引用上限表述;**改上限值 → 本報告的最壞值要重算** |
| **WS 心跳契約**(`WS_HEARTBEAT_SECS` 10 s ↔ `WS_SILENCE_TIMEOUT_MS` 30 s) | F-15(`send_json` → `send_text`) | 心跳 `PING` 也走 `relay._beat` 的 `send_json`,換序列化路徑要一起換 |
| **日 K 定稿界前後端同值(14:00)** | F-05(bars inflight dedup) | `bars.py::DAILY_FINAL_TIME` ↔ `day-bars-rollover.ts` + `StockChart.tsx`;dedup 會改變「同 key 併發首抓」路徑 |
| **T+1/T+2 回填原地補欄 + 離線讀者契約** | F-09 | 逐位元組保留,`tests/server/test_signal_outcome.py` byte 比對;搬進 thread 時不可改 encode/decode 順序 |
| Windows-only 部署(TC4 桌面 app + ZMQ localhost) | 工具選型 | uvloop 不可用;所有 wheel 需 Windows 支援 |
| runtime `dependencies = []`(stdlib-only) | 工具選型 | 新增任何 runtime 相依都是專案哲學層級的決定,需 user 拍板;本報告的 F-01/F-02/F-07/F-16 **全部可用 stdlib 完成** |

---

## 12. 建議執行順序

```
第 0 步(先量,不改): F-16 event loop lag probe + threadpool queue-wait probe
                      → 讓後面每一步都有改動前後的對照

第 1 步(最高 CP):   F-01 corr 報酬序列快取(stdlib)        16 ms/s → <1 ms
                      F-02(1) 下單審計專屬 executor          真錢路徑脫離行情排隊
                      F-08(1) in_window 移到早退之後          一行,零風險
                      F-03 COM 執行緒命令優先                  送單延遲脫離帳務輪詢

第 2 步:             F-04(1) tape 序列化丟 thread
                      F-05(1) bars route semaphore
                      F-02(2) TC4 歷史取數專屬 executor
                      F-10 names 快取

第 3 步(觸面較廣):  F-07 heapq 單執行緒排程器
                      F-09 回填整段丟 thread
                      F-15 broadcaster 單次序列化
                      F-05(2) bars inflight dedup

不做:               F-11 / F-13 / F-14,以及 §9 列出的七項
```
