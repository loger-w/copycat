# B02 — FastAPI server core 與 HTTP 層 架構掃描報告

掃描對象:`copycat/server/app.py`(2133 LOC)、`__main__.py`(197)、`engine.py`(462)、
`build_info.py`(82)、`verify.py`(286)、以及 HTTP/WS 邊界必經的 `ws.py`(312)、
`bars.py`(723)、`capital_api.py`(451)、`oi_levels.py`(292)。

掃描日期 2026-09-13。所有數字都是**本機實測**(Python 3.13.13 / 16 核 / Windows 11),
量測腳本留在 `scratchpad/bench_ser.py`、`bench_build.py`、`bench_route.py`、
`bench_group.py`、`bench_corr.py`、`scan_block.py`。

---

## 0. TL;DR(給趕時間的人)

1. **這一層的「框架成本」不是瓶頸,不要換框架。** 實測固定開銷 ≈ 0.4 ms/req(含 httpx client),
   FastAPI 0.139 + pydantic 2.13 的回應序列化**已經走 pydantic-core 的 Rust `serialize_json` 快路徑**
   (1.6 MB payload 6.8 ms,比 stdlib `json.dumps` 的 14.6 ms 快一倍)。裝 orjson 在 HTTP 回應這一段
   **沒有收益**。
2. **真正的問題是「同一個 event loop + 同一個預設 ThreadPoolExecutor」**:126 個 `asyncio.to_thread`
   呼叫點全部落在 loop 的**預設 executor**(本機 20 workers),裡面同時混著「最壞 20 s 的 TC4 歷史 REQ」、
   「jsonl 整檔讀」、「群益 COM join」,以及 —— 最危險的 —— **下單前的審計落檔**。TC4 半死時,
   送單延遲會被歷史取數的執行緒堆積綁架。這是「不能塞住」這個需求的頭號違反者。
3. **第二個問題是幾個 route 在 event loop 上做百毫秒級的純 Python 建構**:
   `/api/stock/group-state` 150 檔實測 **35 ms 建構 + 23 ms 序列化 = 58 ms**、payload **3.5 MB**;
   `corr.state()` 每秒被 `corr_engine._run` 叫一次,實測 **13 ms**(11 腿 × 3 窗 × 1800 樣本的純 Python 迴圈)。
4. **`app.py` 2133 行不是效能問題**。實測 `import copycat.server.app` 總計 389 ms,其中 `app.py` 自身
   只佔 **3.6 ms**,fastapi 佔 223 ms。切檔對 import/reload 時間**沒有幫助**,要切是為了可維護性。
5. **uvicorn 這邊沒有太多可調的**:Windows 上 uvloop 不存在(已確認未裝也裝不了),uvicorn 自動落到
   `ProactorEventLoop`;httptools 與 websockets 都已裝且自動生效。`workers` **絕對不能開**
   (多 process = 多條 TC4 login,會直接踩 CLAUDE.md §8 的 refcount 地雷)。唯一值得實驗的是 `winloop`。

---

## 1. 架構地圖

### 1.1 進入點與組裝順序

```
python -m copycat.server [--verify]
  └ __main__.main()
      ├ _setup_prod_log()            # sys.stdout/stderr 換成 _Tee(每筆 write 即 flush)
      ├ logging.basicConfig(INFO)
      ├ create_app(...)              # ← 純組裝,零連線;所有 route 都是 create_app 內的 closure
      └ uvicorn.run(app, host="127.0.0.1", port=8721,
                    timeout_graceful_shutdown=WS_DRAIN_SECS)   # 唯一一行 uvicorn 設定
```

`create_app()` 是一個 **~1000 行的巨型工廠函式**(app.py:515–2133),它同時扮演四個角色:

| 角色 | 行數範圍 | 內容 |
|---|---|---|
| per-app 狀態容器 | 538–557 | `overlay_cache` / `overlay_sem=Semaphore(4)` / `bars_cache` / 五顆 `WsBroadcaster` |
| 日期推導層 | 559–635 | `_resolve_trade_date` / `_calendar_crosscheck` |
| lifespan 編排 | 637–1264 | 八段引擎 boot 序列 + 並行 lane 關機 |
| route 宣告 | 1266–2133 | 28 條 APIRoute + 8 條 WebSocket + 5 個 exception handler |

**所有 route 都靠 closure 抓 `create_app` 的區域變數**(`bars_cache`、`overlay_sem`、`trading_calendar`、
`wl_path`、`names_path`),這是「為什麼 app.py 切不開」的結構性原因 —— 不是行數問題,是**依賴注入靠
lexical scope 而不是靠物件**。

### 1.2 Route 清冊(實測 `create_app()` 後列舉)

`APIRoute` 28 條 + `APIWebSocketRoute` 8 條 + capital 子 router(`_IncludedRouter`)+ 4 條 FastAPI 內建
(`/openapi.json`、`/docs`、`/docs/oauth2-redirect`、`/redoc`)。

**全部 28 條 APIRoute 都是 `async def`,沒有任何一條是 `def`**(所以 starlette 的 `run_in_threadpool`
那條路完全沒被用到,anyio 那個 40-token limiter 在這個 app 裡是死的)。

| Route | 方法 | 主要工作 | 在 loop 上的同步工作 |
|---|---|---|---|
| `/api/health` | GET | 回 `app.state.build`(啟動時算一次) | 無 |
| `/api/ready` | GET | 兩個 `getattr` | 無 |
| `/api/calendar` | GET | `sorted(cal.holidays)` + `sorted(extra_trading_days)` | 每次重排(小) |
| `/api/txo/series` `/snapshot` `/contracts` | GET | `runtime.latest_snapshot()` | ChainAggregator 全量快照 |
| `/api/txo/select` | POST | `runtime.activate()` → `to_thread(unsubscribe/subscribe/fetch_backfill)` | — |
| `/api/stock/names` | GET | `load_stock_names()` **每請求讀 60 KB JSON** | **實測 2.53 ms** |
| `/api/stock/watchlist` | GET | `load_watchlist()` 讀 2.8 KB JSON | 0.11 ms |
| `/api/stock/watchlist` | PUT | `WatchlistService.apply()`(asyncio.Lock) | — |
| `/api/stock/overlay/{code}` | GET | `overlay_cache` → `Semaphore(4)` → `wait_for(daily_bars, 15s)` | **見 F-03** |
| `/api/stock/bars/{code}` | GET | `build_daily` / `build_minute` + `BarsCache` | — |
| `/api/stock/signals/today` | GET | `to_thread(hub.today_signals)` ✅ 已丟 worker | — |
| `/api/stock/signals/rules` ×4 | CRUD | `hub.rules()` / `hub.upsert_rule()` | 小 |
| `/api/stock/stkfut/contracts/{code}` | GET | `catalog.get()`(冷 cache 時真打 TC4) | — |
| `/api/stock/state/{code}` | GET | `set_main_contract` + `stock.snapshot()` | **5 ms 建構(20k tick)** |
| `/api/stock/group-state` | GET | `stock.group_snapshot(≤150)` | **35 ms 建構** |
| `/api/index/state` | GET | `index.state()`(twse/otc minutes 全量 dict 複製) | 中 |
| `/api/index/overlay` | GET | `build_period` + `build_overlay` | — |
| `/api/market/bars/{key}` | GET | `build_minute` / `build_period` 分派 index/futures/OTC | — |
| `/api/market/breadth` | GET | `breadth.state()` | 小 |
| `/api/market/breadth/rows` | GET | `breadth.rows_state()` **~2800 列連板算術** | 中 |
| `/api/corr/state` | GET | `corr.state()` → `correlations()` | **13 ms** |
| `/api/river/state` | GET | `corr.river_snapshot()` 全量 | 中大 |
| `/api/futures/oi-levels` | GET | `to_thread(_fetch_rows)` ✅ | — |
| `/api/capital/status|orders|fills|positions` | GET | `store.*()` 取 `threading.Lock` + `dataclasses.asdict` 逐列 | 小~中 |
| `/api/capital/order/*` `/position/close` | POST | `to_thread(audit)` → COM 佇列 → `wait_for(shield(fut), 10s)` | **見 F-01** |

WebSocket 8 條:`/ws/txo-pnl`、`/ws/stock`、`/ws/index`、`/ws/corr`、`/ws/river`、`/ws/breadth`、
`/ws/capital`、`/ws/futures`。全部走 `ws.relay()`(`_send` / `_recv` / `_beat` 三個 task +
`asyncio.wait(FIRST_COMPLETED)`)。

### 1.3 Middleware

**只有條件式的 `CORSMiddleware`**(app.py:1267–1274;`FRONTEND_ORIGIN` 未設就完全不掛)。
實測 `app.user_middleware == []`(本機無 `FRONTEND_ORIGIN`)。

→ **沒有任何 request timing / metrics / tracing middleware**。整個系統對「哪條 route 慢」
沒有任何內建答案,只能靠 uvicorn access log 的「有沒有這一行」。這是 quant 系統的重大缺口(F-12)。

### 1.4 EngineRuntime / QuoteSource 抽象邊界

```
QuoteSource(Protocol, engine.py:28)   # 5 個方法:list_series / fetch_backfill / subscribe / unsubscribe / close
        ↑ 實作 = copycat.live.tc4.TC4QuoteSource;測試注入 verify.FakeTxoSource
EngineRuntime(engine.py:63)           # asyncio.Queue(10_000) + ChainAggregator + 交接協定 + 換代 Event 節流流
```

**這個邊界只服務 TXO 一條線。** 另外五個引擎(stock / index / futures / corr / breadth)各自有
**自己的一套** source protocol(`StockSource` / `IndexSource` / `FuturesSource` / `CorrSource` /
`BreadthFetchers` 四元組)與**自己的一套** queue/throttle/broadcast/自癒迴圈。`EngineRuntime`
沒有被任何人重用。

而且這個 Protocol 已經在漏水:`list_stock_futures` **刻意不放進 `StockSource` Protocol**,
改由 app.py:778 用 `getattr(stkfut_source, "list_stock_futures", None)` 取(有註解說明理由 ——
「加進去等於逼所有 fake 實作」)。這是抽象邊界的壓力訊號。

---

## 2. 資料流

### 2.1 行情入 → 出(TXO 這一條,`EngineRuntime`)

```
TC4 ZMQ(source thread)
   └ on_tick(tick)                       engine.py:361
       └ loop.call_soon_threadsafe(_enqueue, tick)      # 跨執行緒唯一入口
           └ _enqueue: 交接中 → HandoverBuffer;否則 queue.put_nowait(maxsize=10_000)
                                                         # 滿 → queue_dropped += 1 + WARNING
   ── event loop ──
   _consume()  engine.py:377
       while True:
         tick = await wait_for(queue.get(), timeout=0.05)     # ← 每 50 ms 一次 timeout 分支做自癒巡檢
         if agg.route(tick): _mark_changed()                  # 版本 +1 + 換代 Event.set()
   snapshots(seed)  engine.py:147
       版本變 → latest_snapshot() → _content() 深比對 → 內容有變才 yield → await sleep(throttle=1.0)
   ws.relay._send → websocket.send_json(dict)   # starlette json.dumps(separators, ensure_ascii=False)
```

值得注意的兩件事:

- **`_consume` 的 `wait_for(..., timeout=0.05)` 是一個每 50 ms 的固定喚醒**,每次建立/取消一個
  `asyncio.wait_for` 的 timeout handle。盤中連續 tick 時 timeout 不觸發,但 `wait_for` 的包裝成本
  (建 future + timer)仍逐 tick 付。這是 TXO 線的每 tick 固定開銷(見 F-19,量級小但是唯一一處逐 tick)。
- **`_content()`(engine.py:49)對整份快照做 dict 複本 + `==` 深比對**,每次版本變動一次。
  TXO 全量快照 CLAUDE.md 記為 ~22 KB。每秒一次的話可接受;但這是「節流靠比對」而不是
  「節流靠 dirty flag」的設計。

### 2.2 HTTP 回應流(FastAPI 0.139 實際路徑)

已逐行確認 `fastapi.routing.get_request_handler`:

```
raw_response = await endpoint(**kwargs)            # 你的 async def 回一個 dict
use_dump_json = response_field is not None and isinstance(response_class, DefaultPlaceholder)
                                                    # ← 本專案全部 route 都成立 = True
content = await serialize_response(field=..., response_content=raw_response, dump_json=True)
          ├ field.validate(dict)                    # pydantic-core(Rust)
          └ field.serialize_json(value)             # pydantic-core 直出 JSON bytes
response = Response(content=bytes, media_type="application/json")
```

**28 條 route 全部有 `response_field`**(實測:`-> dict` 的回傳型別註解被 FastAPI 推成
`response_model=dict`;`POST/PUT /rules` 是 `-> Rule`;`DELETE` 回 `Response` 所以 `response_field=None`)。
所以全部走 Rust 快路徑。**這代表 `orjson`/`msgspec` 在 HTTP 回應層沒有可觀收益**(見 §5 取捨)。

實測(見 §7 腳本):

| payload | fastapi dump_json 快路徑 | fastapi 舊 dict+dumps 路徑 | stdlib json.dumps |
|---|---|---|---|
| 15.5 KB | 0.12 ms | 0.21 ms | 0.25 ms |
| 173.7 KB | 0.81 ms | 1.30 ms | 1.77 ms |
| 648.3 KB | 3.21 ms | 5.45 ms | 6.97 ms |
| 1597.6 KB | 6.80 ms | 10.39 ms | 14.58 ms |

### 2.3 WebSocket 回應流

```
engine._publish(msg: dict)
  └ WsBroadcaster.publish(msg)            ws.py:65   # 同一個 dict 物件塞進 N 個 per-client queue
      └ 滿 → get_nowait() 丟最舊 + put_nowait 保最新 + _note_drop()(60 s 節流 WARNING)
  ── 每個 client ──
  relay._send: async for msg in stream: async with send_lock: await websocket.send_json(msg)
      └ starlette WebSocket.send_json: json.dumps(data, separators=(",",":"), ensure_ascii=False)
                                       ← stdlib,**每個 client 各序列化一次同一份 dict**
  relay._beat: 每 WS_HEARTBEAT_SECS=10 s 直送 {"type":"ping"}(不經 queue)
```

實測 starlette `send_json` 對 15.6 KB payload = **0.324 ms**。8 條 WS × 若干分頁的話這是可累積的
純重複工(F-13)。

### 2.4 啟動流(lifespan)

```
lifespan 進場
 ├ build_info.capture()                 # ← 同步!兩發 subprocess git,實測 38 + 51 = 89 ms
 ├ EngineRuntime(...) 建構
 ├ app.state.<10 個> = None;boot_done=False
 └ boot_task = create_task(_boot_all())   # 背景,不擋 yield → uvicorn 立刻開始收請求
     _boot_all:
       runtime.start()                    # TXO:to_thread(list_series) + activate(交接)
       _boot_engines()  ← **嚴格串行,順序即依賴**
         1 stock      (TC4 login + 自選全量 SUB + load_watchlist)
         2 (WatchlistService 建構)
         3 signals    (SignalHub.start + create_bot + Discord 登入)
         4 index      (TC4 login;背景丟 _calendar_crosscheck task)
         5 capital    (SKCOM DLL 載入 + 群益登入,COM 專屬執行緒)
         6 futures    (TC4 login + SUB)
         7 corr       (TC4 login + 11 腿 SUB)
         8 breadth    (FinMind HTTP)
         9 screen     (FinMind)
        10 stkfut_catalog.prewarm()       # TC4 QUERYALLINSTRUMENT,秒級
       app.state.boot_done = True;log「boot 序列結束(%.1fs)」
```

關機:crosscheck → screen → breadth → signals(串)→ **4 條 TC4 lane 並行**
(corr→futures 串鏈 ‖ index ‖ stock ‖ txo)→ capital 最後。預算同源在
`shutdown_budget.run_grace_secs()` = 83 s(CLAUDE.md §4「關機預算三方同源」契約)。

---

## 3. 熱路徑逐條(按頻率排序)

### HP-1 `EngineRuntime._consume` — 每 tick(TXO 盤中數十~數百/秒)+ 每 50 ms 固定喚醒
`engine.py:377-393`。每個 tick:`wait_for` 包裝 + `agg.route(tick)` + 條件式 `_mark_changed()`
(版本 +1、建一顆新 `asyncio.Event`、set 舊的)。`_mark_changed` 每次**配置一個新 Event 物件** ——
這是有意的設計(避免 `clear()` 漏版本),成本是每個有效 tick 一次小物件配置。

### HP-2 `WsBroadcaster.publish` — 每則推播 × N client
`ws.py:65-80`。每則先跑 `_settle_drop_window(time.monotonic())`(兩個比較,極便宜),
再對每個 client queue `put_nowait`。**同一個 dict 物件共享**,不複製 ✅。

### HP-3 `relay._send` → `websocket.send_json` — 每則推播 × N client
stdlib `json.dumps`。**同一份 dict 被 N 個 client 各序列化一次**。
頻率:futures 每 0.1 s、stock ticks 打包 ≤10/s、index/corr/river/txo 各 1/s、breadth 10 s。
粗估單 client 峰值 ~25 則/s;payload 多為幾 KB。

### HP-4 `corr_engine._run → tick_once → state() → correlations()` — 每 1 秒
`corr_engine.py:223-229` + `corr_state.py:113-126`。實測 **13 ms**(10 腿 × 3 窗 × 1800 樣本)。
`_paired_returns` 每腿重建一個 `dict(leg_series)`(1800 項)+ 全掃;然後每個窗再對 paired 做
兩次 list comprehension 過濾 + `statistics.correlation`。**在 event loop 上**。

### HP-5 `stock_engine._flush_ticks` — 每 0.1 秒(有成交時)
由 `call_later` 排程;也被 `snapshot()` / `group_snapshot()` **同步觸發**(副作用 publish)。

### HP-6 `/api/stock/group-state` — 每 60 秒(群組檢視常開)+ 每次換組 / 重連
實測(合成資料,每檔 270 分鐘 + 300 檔位 VP):

| 檔數 | 建構 | 序列化 | payload |
|---|---|---|---|
| 20 | 3.25 ms | 3.55 ms | 476 KB |
| 50 | 9.48 ms | 8.39 ms | 1.19 MB |
| 150 | **34.89 ms** | **22.92 ms** | **3.57 MB** |

### HP-7 `/api/stock/state/{code}` — 每次換主圖標的 / 重連 / seq 跳號 refetch
實測:20 000 筆 tape 建構 **5.13 ms** + 序列化 **6.80 ms**,payload **1.6 MB**。
`tape=0`(群組點卡片)則是 15.5 KB / 0.12 ms。

### HP-8 `/api/stock/overlay/{code}` — 進群組時一次打 ≤150 條
`app.py:1484-1517`。cache miss 時進 `Semaphore(4)` + `wait_for(15 s)`。

### HP-9 lifespan `build_info.capture()` — 開機一次
實測 `git rev-parse --short HEAD` 38 ms + `git status --porcelain` 51 ms = **89 ms 同步阻塞**,
worst case 2 × `_GIT_TIMEOUT_SECS`(3 s)= 6 s。

### HP-10 `/api/stock/names` — 前端開站一次(TanStack Query 可能重抓)
實測 **2.53 ms**(0.67 ms 讀檔 + 解析,其餘是 2401 個 `{"code","name"}` dict 建構 + 86 KB 序列化)。

---

## 4. Findings

> 嚴重度是「對『下實單 + 不能塞住』這個目標」的嚴重度,不是一般 web 服務的嚴重度。

---

### B02-01 【critical / concurrency】下單路徑與 TC4 歷史取數共用同一個預設 ThreadPoolExecutor

**位置**:`copycat/capital/client.py:885` + 全庫 126 個 `asyncio.to_thread` 呼叫點
(`stock_engine` 15、`index_engine` 8、`signal_hub` 7、`futures_engine` 6、`engine` 5、`corr_engine` 5、
`breadth_engine` 4、`app` 4、`screen_engine` 3、`capital/client` 3、`oi_levels` 2、`stkfut_catalog` 1)。

**證據**

```python
# copycat/capital/client.py:884-891 —— 送單路徑
        # 前置:寫不進去 → AuditWriteError,錢沒動(to_thread 不卡 loop,review B6)
        await asyncio.to_thread(self._audit, self._record(action, req))
        fut: asyncio.Future[tuple[str, int]] = self._loop.create_future()
        self._cmd_q.put((com_call, fut))
        try:
            message, code = await asyncio.wait_for(asyncio.shield(fut), timeout=_WRITE_TIMEOUT_S)
```

```python
# copycat/server/app.py:1568-1572 —— 專案自己已經寫下的警語
        # 讀整份當日 jsonl 是同步 IO,訊號多的日子會卡住 event loop(8 條 WS 一起頓)
        # → 丟 worker thread;_signals 的 503 判定留在 loop 內(handoff R5)。
        # to_thread 走 loop 預設 executor,與 daily_bars / capital close 同池且工作
        # 執行緒不可中斷 —— TC4 半死的殭屍執行緒堆積時這條會跟著排隊(review C-1);
```

```python
# copycat/server/app.py:123-136 —— TC4 歷史單次最壞 20 s(已實測)
#: TC4 對「查無此檔」不是快速失敗 —— `fetch_daily_bars` 內部兩段 deadline 各
#: `BARS_POLL_DEADLINE` = **10s** … → 現在最壞 **20s**。
```

實測:`os.cpu_count()=16` → `asyncio.to_thread` 的預設 executor `max_workers = min(32, 16+4) = 20`。
全庫 **零** `loop.set_default_executor` / `ThreadPoolExecutor` 自建(grep 確認)。

**影響**:TC4 半死時,`daily_bars` / `bars_range` / `fetch_backfill` 的工作執行緒各卡 10–20 s 且
**不可中斷**(`to_thread` 沒有取消語意,`asyncio.wait_for` 只放掉 awaiter,執行緒照跑)。
20 條 worker 被佔滿之後,`await asyncio.to_thread(self._audit, ...)` 會**排在 executor 佇列裡**,
也就是說 **送單指令連進 COM 佇列的資格都還沒拿到**。前端看到的是「按了送單沒反應」,而
`_WRITE_TIMEOUT_S=10 s` 的保護根本還沒開始計時(它保護的是 COM 那一段,不是 executor 排隊那一段)。

**修法**:把 executor 切成具名 lane,依阻塞特性分池:

```python
# 建議 app.py lifespan 進場處
from concurrent.futures import ThreadPoolExecutor
tc4_pool   = ThreadPoolExecutor(max_workers=6,  thread_name_prefix="tc4-hist")
fileio_pool= ThreadPoolExecutor(max_workers=2,  thread_name_prefix="fileio")
order_pool = ThreadPoolExecutor(max_workers=2,  thread_name_prefix="order-audit")
# 之後:await loop.run_in_executor(order_pool, self._audit, rec)
```

比較省事的第一步(**強烈建議先做這一步**):把**送單審計**與**訊號 jsonl 這類檔案 IO**從預設池移走,
讓預設池只剩 TC4。程式碼改動集中在 `capital/client.py` 的三處 `to_thread` 與 `signal_hub` 的 jsonl 路徑。
更徹底的做法是引入一個 `copycat/server/pools.py` 當單一定義點(與 `shutdown_budget.py` 同款)。

**風險**:`run_grace_secs()` 的關機預算契約(CLAUDE.md §4「關機預算三方同源」)沒有把
executor 的排空納入,新增具名池要在關機路徑 `shutdown(wait=False, cancel_futures=True)`,
並確認 `TC4_LANE_DEPTH` 的口頭契約不受影響。`tests/server/test_shutdown_budget.py` 會釘住不等式。

**effort**:M

---

### B02-02 【critical / render+serialization】`/api/stock/group-state` 在 event loop 上花 58 ms、吐 3.5 MB

**位置**:`copycat/server/app.py:1707-1736`;實作在 `copycat/server/stock_engine.py:799-856` →
`copycat/live/stock_state.py:237-264`。

**證據**

```python
# app.py:1724-1736
        stock = _stock(request)
        wanted = list(dict.fromkeys(c for c in codes.split(",") if c))
        if len(wanted) > WATCHLIST_LIMIT:            # 150
            raise HTTPException(status_code=400, detail={"error": "BAD_CODES"})
        for code in wanted:
            _valid_code(code)
        return {"states": stock.group_snapshot(wanted)}      # ← 同步,無 to_thread
```

```python
# live/stock_state.py:206-219 —— 每檔每次都重排一次 minutes
        return {
            str(k): {"c": m.close_milli, "v": m.volume, "i": m.inner, "o": m.outer,
                     "u": m.unch, "h": m.high_milli, "l": m.low_milli}
            for k, m in sorted(self.minutes.items())
        }
# :257 —— 每檔每次都重排一次 VP
            "vp": {str(price): list(cell) for price, cell in sorted(self._vp.items())},
```

**實測**(合成,每檔 270 分鐘 + 300 檔位):150 檔 = 建構 34.89 ms + 序列化 22.92 ms,payload 3.57 MB。
50 檔 = 17.9 ms / 1.19 MB。

**影響**:這 58 ms 期間 event loop 完全停住 —— 八條 WS 一則都送不出去、`_flush_ticks` 的 0.1 s timer
延後、`corr` 的每秒 tick 延後。tick 本身不會遺失(`call_soon_threadsafe` 只是排隊),但**行情在畫面上
會有一次可見的 58 ms 空窗**,而且它每 60 秒準時發生一次。加上 3.5 MB 經 Vite proxy → 瀏覽器
JSON.parse,前端那一側還有第二次停頓(交給 F 區塊)。

**修法(三選一或組合)**:
1. **最小改動**:`return {"states": await asyncio.to_thread(stock.group_snapshot, wanted)}`
   —— **不可行**,`group_snapshot` 的 docstring 明文寫「只能在 event loop 上呼叫」
   (`_flush_ticks` 動 timer handle)。要走這條得先把 `_flush_ticks()` 拆出來在 loop 上先做,
   剩下的純建構才丟 thread。
2. **快取分鐘 payload**:`_minutes_payload` 的 `sorted()` 每次重排。分鐘序列是**只在尾端追加**的,
   可以維護一份已排序的 wire 形 list,新分鐘 append、當前分鐘就地更新 → 建構從 O(n log n) 降到 O(1) 攤銷。
   VP 同理(檔位有序插入)。這一招預估砍掉建構的 60–70%。
3. **改成 delta**:群組卡片已經有 `seq` 逐筆續傳機制(CLAUDE.md §4「個股逐筆 = ticks 打包訊息」),
   60 s 全量重播種本來就是**自癒**手段而不是資料來源。把它降頻到 5 分鐘、或改成只回
   「seq 對不上的那幾檔」,payload 直接降一個數量級。

**風險**:改 payload 形狀會動到 CLAUDE.md §4 的「個股 `seq` 的兩個口徑」契約
(`frontend/src/lib/stock-accum.ts::fromSnapshot` 由 `snap.seq` 由尾回推 React key)與
`useGroupLiveAccums` 的 `seq === acc.seq + 1` 判準 —— **兩邊同動**。純快取化(方案 2)不動契約,
是最安全的第一步。

**effort**:方案 2 = M;方案 3 = L

---

### B02-03 【high / blocking-io】`/api/stock/overlay/{code}` 的 Semaphore(4) + 15 s + 無 inflight dedup = 進群組時的 head-of-line 地雷

**位置**:`app.py:123-136`(常數與註解)、`app.py:547`(semaphore)、`app.py:1484-1517`(route)。

**證據**

```python
# app.py:543-547
    # 群組檢視的 `cdp` 預設是開的 → 一進群組就對整組(上限 150 檔)同時打 `/api/stock/overlay`,而
    # `daily_bars` 走 `to_thread` 沒有上限、整組(上限 150 條)請求共用同一條 TC4 歷史通道。
    overlay_sem = asyncio.Semaphore(4)
```

```python
# app.py:1491-1517
        today = _resolve_trade_date()
        cached = overlay_cache.get(code, today)
        if cached is not None:
            return cached  # cache 命中不進 semaphore
        async with overlay_sem:
            try:
                bars = await asyncio.wait_for(stock.daily_bars(code), timeout=OVERLAY_FETCH_TIMEOUT_S)
            except (TimeoutError, HistoryTimeoutError):
                ...
                return build_overlay([], today)     # **不寫 cache**
```

**影響**:程式碼註解已經自己算過這筆帳(「四檔這種股號就足以把整個端點凍住」)。
更糟的是三件事疊在一起:
1. 逾時**不寫 cache**(正確的資料語意)→ 每次重試都重付 15 s;
2. `wait_for` 逾時只放掉 semaphore 名額,**底層 `to_thread` 執行緒還在跑到 20 s** → 一邊放人進來
   一邊佔著 executor(接回 B02-01);
3. **沒有 inflight dedup** → 前端重整 / 多分頁對同一 code 會各發一次真取數。

最壞路徑:進一個 150 檔的群組、TC4 冷 → 150 / 4 × 15 s ≈ **9.4 分鐘**才畫得完疊線,期間
executor 常駐 4 條殭屍執行緒。

**修法**:
- 加 **per-key inflight dedup**(`dict[str, asyncio.Future]`,首個請求真取、其餘 await 同一顆),
  這同時解掉 F-11 的 `build_daily`/`build_minute`;
- 逾時寫一個**短 TTL 負向快取**(沿 `bars.py` 既有 `empty_mark` 15 s 的做法),不要每次重付;
- semaphore 從 4 提到 8–12 的**前提**是 B02-01 先把 TC4 lane 切出來,否則只是把壓力往 executor 推。

**風險**:負向快取會讓「TC4 剛恢復」的那 15 s 仍回全 null —— 與 `bars.py` 既有政策一致,可接受。
inflight dedup 要注意取消語意:第一個 awaiter 被 client abort 時不可 cancel 共享 future。

**effort**:M

---

### B02-04 【high / algorithmic】`corr.state()` 每秒在 event loop 上燒 13 ms 的純 Python 數值迴圈

**位置**:route `app.py:1981-1986` + `app.py:1997`(WS seed);真正的每秒呼叫在
`corr_engine.py:223-229 _run → tick_once`;算式在 `copycat/live/corr_state.py:82-136`。

**證據**

```python
# live/corr_state.py:113-126
    def correlations(self, now: float) -> dict[str, dict[str, float | int | None]]:
        result = {}
        for leg in self._legs:                       # 11 腿
            paired = self._paired_returns(leg, now)  # 重建 dict(1800 項) + 全掃
            row = {}
            for window in self._windows:             # (60, 300, 1800)
                cutoff = now - window
                xs = [rb for ts, rb, _ in paired if ts >= cutoff]   # 每窗各掃一次
                ys = [rl for ts, _, rl in paired if ts >= cutoff]   # 再掃一次
                row[f"n{window}"] = len(xs)
                row[f"w{window}"] = self._corr(xs, ys, self._min_samples.get(window, 0))
            result[leg] = row
```

實測 config:`windows=(60, 300, 1800)`、`legs=11`、`base=TXF`、`tick_secs=1.0`。
合成 benchmark(10 腿 × 3 窗 × 1800 樣本)= **12.99 ms/call**。

**影響**:盤中每秒固定 13 ms 的 loop 佔用(1.3% duty cycle),而且與 HP-6 的 58 ms 尖峰**會撞在一起**。
`/api/corr/state` REST 與每次 `/ws/corr` 連線的 seed 又各多打一次。這是全庫「手刻 Python 數值迴圈」
最典型的一處,也是 numpy 能給出最大倍率的一處(1800 點的 Pearson,numpy 大約 20–50 µs,
連 `np.corrcoef` 的常數開銷都算進去也 < 0.2 ms → **50–100×**)。

**修法**(實作歸 B04,但 B02 要負責把它**移出 event loop 或移進 numpy**):
- 短期零相依:`_paired_returns` 回一份**已排序 list** 後,三個窗用 `bisect.bisect_left` 找 cutoff 切片,
  不要三次全掃;`statistics.correlation` 換成一次走訪算 Σx/Σy/Σxy/Σx²/Σy²(數值穩定性對 log return
  這種小量級沒問題)。預估可到 2–3 ms。
- 正解:`numpy`。序列用 `np.empty(cap)` ring buffer 維護,相關係數用
  `np.corrcoef` 或直接 `(n·Σxy − Σx·Σy) / sqrt(...)`,全部 vectorized。
- 兩者都不做的話,至少 `tick_once` 丟 `to_thread`(但要先過 B02-01 的 lane 切分)。

**風險**:改算式會動到相關係數的數值輸出 —— `tests/` 內的 corr 測試會釘住。log return 的
`None` 語意(常數序列 → None 而非 0/NaN)必須保留。CLAUDE.md §4 的「江波圖調色盤色數 ≥ 相關係數腿數」
契約不受影響(那是腿數不是算式)。

**effort**:S(bisect 版)/ M(numpy 版)

---

### B02-05 【high / architecture】全域 `Exception` handler 一律回 502 `TC4_DOWN`,把所有後端 bug 偽裝成上游故障

**位置**:`app.py:1284-1287`。

**證據**

```python
    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error on %s", request.url.path, exc_info=exc)
        return JSONResponse(status_code=502, content={"detail": {"error": "TC4_DOWN"}})
```

程式碼本身已經記下三次被這條咬到的案例(`app.py:1589-1596` 註解:「全域 handler 會把它收成
502 TC4_DOWN,而落檔失敗跟達錢 4 一點關係都沒有(排查會被帶到反方向)」;`app.py:1906-1911`:
「直取屬性會是 AttributeError → 全域 handler 轉 502 TC4_DOWN,而那句訊息與真因完全無關」)。

**影響**:對效能工作的直接傷害是 —— **一個 route 因為超時/資源耗盡而拋例外時,監控與前端看到的
是「達錢 4 掛了」**。在一個要下實單的系統上,這會讓「後端塞住」與「行情商掛了」在所有可觀測面
(前端紅色、log grep、使用者回報)上同形。

**修法**:handler 改成回 `{"detail": {"error": "INTERNAL", "path": ..., "type": type(exc).__name__}}`
+ 500,並保留 `TC4_DOWN` 給真正的 `ConnectionError` / `HistoryTimeoutError`
(加一條 `@app.exception_handler(ConnectionError)`)。

**風險**:**這是跨檔契約改動** —— CLAUDE.md §4「API error JSON shape」:前端解 `detail.error`。
前端目前對 `TC4_DOWN` 有專屬文案。要同動 `frontend/src/` 內所有比對 `"TC4_DOWN"` 的地方,
並確認 `tests/server/` 內斷言 502 的測試(數量不少)一起改。建議拆成獨立一筆 🔴 行為改動 commit。

**effort**:M

---

### B02-06 【high / architecture】`uvicorn.run` 只設了一個參數;沒有 profiling / 沒有 loop 選型實驗

**位置**:`__main__.py:193`。

**證據**

```python
    uvicorn.run(app, host="127.0.0.1", port=port, timeout_graceful_shutdown=WS_DRAIN_SECS)
```

實測環境事實:
- `uvloop` **未裝且 Windows 不支援**;`uvicorn.loops.auto.auto_loop_factory` 落到
  `uvicorn.loops.asyncio.asyncio_loop_factory` → Windows 回 `asyncio.ProactorEventLoop`。
- `httptools 0.8.0` ✅ 已裝(`http="auto"` 會選它);`websockets 16.1.1` ✅ 已裝(`ws="auto"` 選它);
  `wsproto` 未裝。所以 HTTP/WS 協定層**已經是最快的可用組合**,不需要顯式指定。
- `winloop` 未裝 —— 這是 Windows 版的 libuv event loop,是這台機器上**唯一**可能的 loop 升級路徑。
- `access_log` 預設 **開著**,而 stdout 被 `_Tee` 接管(每筆 write 即 flush)。
  實測 write+flush 一行 = **5.4 µs**(vs 純 write 0.3 µs)→ 每請求多 ~11 µs。**不是問題**。

**影響**:目前沒有任何證據說明 Proactor vs winloop 的差距。對一個宣稱「要夠快」的系統,
這是個未被量測的空白。另外 `workers` 未設(= 1)是**正確**的,理由見 §6。

**修法**:
- 明確寫死 `loop="asyncio"`, `http="httptools"`, `ws="websockets"`(不改行為,但讓選型可見、可回溯);
- 做一次 winloop A/B:`pip install winloop`,`uvicorn.run(..., loop="uvloop")` 在 winloop 安裝後
  可用(winloop 有 uvicorn shim),或自己 `winloop.install()` 後傳 `loop="none"`。
  量測指標見 §7 的 M-3。
- `access_log=False` + 自製 timing middleware(見 B02-12)—— 那份資訊比 access log 有用得多。

**風險**:winloop 在 Windows 上**不支援 Proactor 專屬的子行程 API**;`build_info._git` 用
`subprocess.run`(同步、非 asyncio 子行程),不受影響。ZMQ 全部在自己的執行緒裡跑同步 socket,
也不受 loop 換型影響。仍需真實 8 條 WS + 全引擎跑一天才算驗過。

**effort**:S(寫死選型)/ M(winloop 驗證)

---

### B02-07 【medium / serialization】`/api/stock/state/{code}` 全 tape 在 loop 上花 12 ms、吐 1.6 MB

**位置**:`app.py:1668-1705` → `stock_engine.py:713-736` → `live/stock_state.py:266-310`。

**證據**

```python
# live/stock_state.py:295-307
            "ticks": [
                {"t": t.time, "p": t.price_milli, "q": t.qty, "side": t.side,
                 "b": t.bid_milli, "a": t.ask_milli}
                for t in self.ticks          # deque maxlen=20_000
            ] if tape else [],
```

實測:20 000 筆 = 建構 5.13 ms + 序列化 6.80 ms,payload 1.60 MB。8000 筆 = 1.42 + 3.21 ms。

**影響**:換標的、重連、seq 跳號 refetch 各觸發一次。單次 12 ms 不致命,但重連風暴
(前端 WS 30 s 靜默 watchdog 誤觸發時,8 條 WS 同時重連)會疊起來。

**修法**:
- 逐筆明細其實只需要**最近 N 筆**(畫面一次看得到幾十筆,往上捲需求罕見)。
  加一個 `?tape_limit=2000` 走預設,`tape=full` 才給全量 → payload 降 10×。
- 或把 tick 改成**欄式**(`{"t": [...], "p": [...], "q": [...], ...}`)。同樣 20 000 筆,
  欄式 JSON 大約只有 40% 大小,建構也快(不用建 20 000 個 dict)。

**風險**:兩者都動 CLAUDE.md §4 的 seq 契約讀者(`stock-accum.ts::fromSnapshot` 由 `snap.seq`
**由尾回推**指派 React key —— 給的筆數變少時回推仍成立,但前端要知道「這不是全部」)。
欄式改動更大,要同動 `fromSnapshot` 與 `applyTick`。建議先做 `tape_limit`。

**effort**:S(tape_limit)/ L(欄式)

---

### B02-08 【medium / blocking-io】lifespan 第一行就跑兩發同步 subprocess git

**位置**:`app.py:640` + `build_info.py:48-82`。

**證據**

```python
# app.py:639-641
        # 最先做:引擎起不來時 banner 也要印得出來(「這台是哪一版」是排查的第一個問題)
        app.state.build = build_info.capture()
        logger.info("%s", app.state.build.banner())
```

```python
# build_info.py:55-62
        proc = subprocess.run(["git", *args], cwd=_REPO_ROOT, capture_output=True,
                              text=True, timeout=_GIT_TIMEOUT_SECS, check=False)
```

實測:`git rev-parse --short HEAD` 38 ms + `git status --porcelain` 51 ms = **89 ms**。
最壞 2 × 3 s timeout = 6 s(磁碟忙 / git index lock 時真的會發生)。

**影響**:阻塞在 lifespan 進場,也就是 **uvicorn 還沒開始接受連線的那段**。89 ms 不痛,
6 s 就是開盤前重啟時多等 6 秒。低優先。

**修法**:`app.state.build = await asyncio.to_thread(build_info.capture)`,或者更好 ——
在 `create_app()` 之前(`__main__` 裡)同步算好再傳進去,反正那時候還沒有 loop 可以被卡。

**風險**:幾乎零。`/api/health` 的契約(`git_sha` / `git_dirty` / `started_at`)不變。
`started_at` 的取樣時刻會早一點點(語意仍是「這個行程啟動時」)。

**effort**:S

---

### B02-09 【medium / architecture】boot 序列嚴格串行,八段引擎的 TC4 login 逐段排隊

**位置**:`app.py:685-1141`。

**證據**

```python
# app.py:685-693
        async def _boot_all() -> None:
            """引擎啟動序列(背景 task)。**順序即依賴**(current-state §2),不可重排、
            不可並行:watchlist_service 先於 signals、signals **可獨立於 stock**(XR-3;
            但 stock 在場時要在它之後才接得上掛點)、index 綁 runtime.spot、capital 先
            set_broadcast 再 start、corr 後於 futures。
```

實際的依賴圖只有三條邊:`watchlist_service → signals`、`futures → corr`、`index ← runtime.spot`。
`capital`、`breadth`、`screen`、`stkfut prewarm` 與其他段**沒有依賴**,但被排在同一條線上。

**影響**:每段都含一次 TC4 login(ZMQ REQ 往返)或外部登入(群益 SKCOM DLL 載入 + 登入、
Discord bot 登入、FinMind HTTP)。開盤前重啟時,總啟動時間 = 各段之和。程式碼裡已經有
「不擋序列」的例外處理(`_calendar_crosscheck` 背景跑、`stkfut_catalog.prewarm()` 排最後),
說明作者已經在跟這個問題搏鬥。

**注意**:關機路徑**已經**用 `asyncio.gather` 並行 lane(`app.py:1229-1244`),
啟動路徑卻沒有 —— 這是不對稱。

**影響量級未知** —— log 有 `「boot 序列結束(%.1fs)」`,但我沒有 prod log 可查。列入 §8 待確認。

**修法**:把序列改成三條 lane 的 DAG:
```
lane A: runtime(txo) → (無下游)
lane B: stock → watchlist_service → signals ‖ index(需 runtime.spot,但那只是個 getter callable)
lane C: futures → corr
lane D: capital ‖ breadth → screen
```
`asyncio.gather(lane_a, lane_b, lane_c, lane_d)`。

**風險**:**高**。這條序列的註解密度是全庫最高的,每一段都記著一次事故
(`_start_signals` 的「attach 必須是最後一行」、`_make_screen` 需要 `app.state.watchlist_service`
已經指派、`_make_corr` 讀 `futures` 區域變數)。並行化會讓「`_boot` 的傘」語意變複雜
(一條 lane 炸掉不得影響其他 lane —— 現在的 `_boot` 已經保證這件事,但 `booted` record 的
寫入時序會變)。**建議只在有量測證據顯示 boot > 20 s 時才動**,且要一次只並行一條新 lane。

**effort**:L

---

### B02-10 【medium / architecture】`QuoteSource` / `EngineRuntime` 抽象只服務 TXO,五個引擎各造一套輪子

**位置**:`engine.py:28-39`(Protocol)、`engine.py:63-463`(runtime);對照
`stock_engine.py`(1832)、`index_engine.py`(822)、`futures_engine.py`(694)、
`corr_engine.py`(544)、`breadth_engine.py`(1009)。

**證據**

```python
# engine.py:28-39
class QuoteSource(Protocol):
    """行情來源抽象;TC4 實作在 copycat.live.tc4,測試注入 fake。"""
    def list_series(self) -> list[SeriesInfo]: ...
    def fetch_backfill(self, series: SeriesInfo) -> list[Tick]: ...
    def subscribe(self, series: SeriesInfo, on_tick: Callable[[Tick], None]) -> None: ...
    def unsubscribe(self, series: SeriesInfo) -> None: ...
    def close(self) -> None: ...
```

```python
# app.py:776-780 —— Protocol 已經在漏水
            # 合約查詢與個股訂閱共用同一條 session:QUERYALLINSTRUMENT 是 REQ 不是訂閱,
            fetch = getattr(stkfut_source, "list_stock_futures", None)
            if stock is not None and callable(fetch):
                app.state.stkfut_catalog = StkfutCatalog(cast(Callable[[], dict], fetch))
```

五個引擎各自重複實作的東西(以 grep 的 `to_thread` 分布 + 各檔 `_resub_loop` / `_broadcast_loop` /
`throttle_secs` 為證):tick queue、節流廣播、`call_soon_threadsafe` 入口、重訂閱退避迴圈、
rollover 偵測、close 的 cancel 順序。`throttle_secs=1.0` 這個預設值在 `engine.py:69`、
`index_engine.py:176`、`stock_engine.py:248` 各寫一次。

**影響**:對效能的直接影響是 —— **沒有一個地方可以統一加上「loop 佔用預算」或「背壓」**。
要給任何一個引擎加 executor lane、加 metrics、加 latency 時戳,都得改五次。
這也是為什麼 B02-01 的修法會是 M 而不是 S。

**修法**:抽一個 `copycat/server/runtime_base.py`,把「有界 queue + call_soon_threadsafe 入口 +
換代 Event 節流流 + close 協定」做成 mixin/base。**不要**試圖統一 `QuoteSource` Protocol
(五個 source 的 subscribe 語意真的不同)。

**風險**:這是純重構(🔵),行為必須逐字不變。`engine.py` 的 `_run_handover` 有兩層 `finally`
與明文的「呼叫端不變式」(「`_run_handover` 之後不得再 await」),抽 base 時很容易破。
**不建議在效能專案裡做這件事** —— 列為獨立 `/refactor`。

**effort**:XL

---

### B02-11 【medium / data-structure】`build_daily` / `build_minute` / overlay 三條路都沒有 inflight dedup

**位置**:`bars.py:405-428`、`bars.py:630-723`、`app.py:1484-1517`。

**證據**(程式碼自己承認)

```python
# bars.py:440-442
    界前一律不比(pr-171-review F-05):tripwire 語意是「作廢後的
    refetch」,界前唯一走得到「有 stale 可比」的是同 key 併發首抓(build_* 無 inflight
    dedup),後完成者比對先完成者剛寫的快照必同值 —— 不早退就 boot 併發都誤鳴。
```

`BarsCache`(`bars.py:236-403`)**沒有任何鎖**,也沒有 `_inflight` 結構。

**影響**:前端開站時,`useMarketBars` / `useStockBars` / `FuturesChart` / `index overlay` 會在
同一瞬間對重疊的 key 發請求。每個 cache miss 都變成一次獨立的 TC4 REQ(而 TC4 那頭有 `api.lock`
序列化)→ 排隊 + 重複佔 executor。

**修法**:在 `BarsCache` 上加 `_inflight: dict[str, asyncio.Future]`,`build_*` 進場先查。
與 B02-03 的 overlay dedup 用同一份機制(`copycat/server/inflight.py` 單一定義)。

**風險**:低。要注意 `_warn_if_not_advanced` 的「界前一律不比」早退理由會失效
(dedup 之後併發首抓不再各自寫快照)—— 那段註解要更新,測試 `tests/server/test_bars.py`
可能有一條釘住併發行為。

**effort**:M

---

### B02-12 【medium / observability】完全沒有 request timing / event-loop lag 可觀測性

**位置**:`app.py:1266-1274`(只有條件式 CORS,`app.user_middleware == []` 實測)。

**影響**:上面每一條 finding 的量級我都只能用合成 benchmark 推估,因為**線上沒有任何一條
route 的 p50/p95**。對一個要下實單的系統,這是 quant-gap 等級的缺口:你無法回答
「今天開盤那 3 秒鐘,是誰卡住了 loop」。

**修法**(這條應該**最先做**,因為它是其他所有改動的驗收工具):

```python
# copycat/server/timing.py(新檔)
import time, logging
from collections import defaultdict
from starlette.types import ASGIApp, Receive, Scope, Send

class TimingMiddleware:
    """純 ASGI middleware(不用 BaseHTTPMiddleware —— 那個會多包一層 anyio stream)。"""
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.samples: dict[str, list[float]] = defaultdict(list)
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        t0 = time.perf_counter()
        try:
            await self.app(scope, receive, send)
        finally:
            self.samples[scope.get("route_path") or scope["path"]].append(
                (time.perf_counter() - t0) * 1000)
```
加上一個 `/api/metrics` 吐 per-route count/p50/p95/max,以及一條 **event-loop lag 探針**:

```python
async def _lag_probe() -> None:
    while True:
        t0 = time.perf_counter()
        await asyncio.sleep(0.05)
        lag = (time.perf_counter() - t0 - 0.05) * 1000
        if lag > 50:
            logger.warning("event loop 延遲 %.0f ms", lag)
```
這條 lag 探針**單獨就能抓到 B02-02 / B02-04 的每一次發作**,成本 < 0.01% CPU。

**風險**:純新增(🟢)。要注意 `TimingMiddleware` 必須是純 ASGI class 而不是
`BaseHTTPMiddleware`(後者會在 WS 以外的每個請求多開一個 anyio task group,反而變慢)。
`/api/metrics` 不進 CLAUDE.md §4 的任何契約。

**effort**:S

---

### B02-13 【medium / serialization】WS 每則訊息被每個 client 各序列化一次(stdlib json)

**位置**:`ws.py:262-265` + starlette `WebSocket.send_json`。

**證據**

```python
# ws.py:262-265
    async def _send() -> None:
        async for msg in stream:
            async with send_lock:
                await websocket.send_json(msg)     # ← starlette: json.dumps(dict) per client
```
```python
# starlette/websockets.py(實測 getsource)
        text = json.dumps(data, separators=(",",":"), ensure_ascii=False)
```

實測 15.6 KB payload 的 `json.dumps` = **0.324 ms**。

**影響**:單分頁不痛。但「prod build + preview(4173)+ 開發分頁 + 手機」這種多 viewer 場景,
以及 futures 0.1 s flush(10 則/s),會變成 N × 每則。而且這是**純重複工** —— 同一個 dict。

**修法**:在 `WsBroadcaster.publish` 序列化一次成 `str`/`bytes`,queue 裡放序列化後的結果,
`relay._send` 改用 `websocket.send_text(...)`。改完之後再換 `orjson` 才有意義
(`orjson.dumps` 對這種 payload 大約是 stdlib 的 3–5×)。

**風險**:`ws.py` 的 `WsConnection` Protocol(`send_json`)要改成 `send_text`,
所有注入 fake 的測試同動。心跳 `PING` 可以預先序列化成常數。
`stream(seed=[...])` 的 seed 也要一起序列化。**不動任何前端契約**(wire 形狀完全一樣)。

**effort**:M

---

### B02-14 【medium / architecture】`create_app` 是 1000 行的巨型 closure;切檔對效能沒幫助,但對「加 lane / 加 metrics」是阻力

**位置**:`app.py:515-2133`。

**證據 —— 先否定「切檔能加速 import」這個假設**:

```
$ python -X importtime -c "import copycat.server.app"
import time:      3633 |     388887 | copycat.server.app       ← 自身只 3.6 ms
import time:       484 |     222894 |   fastapi                ← 223 ms 在這裡
import time:     51100 |      58471 |           fastapi.openapi.models
import time:       464 |      53205 |   asyncio
import time:       890 |      19030 |           zmq
```

**切成 5 個檔省不到 3.6 ms 裡的任何一毫秒。** 這點必須寫進任何 refactor 提案,免得有人拿效能
當理由去動它。

順帶一個觀察:`app.py:46` 是 `from copycat.live.stock_source import Bar, BarsStatus, DailyBar`
(module-level),而 `_default_stock_source` 等四個工廠函式裡都寫著「延遲 import:測試不觸 pyzmq」
—— 那個意圖**已經被 module-level 的這一行(以及 `breadth_engine → index_engine → stock_source`
這條鏈)破壞了**,實測 `zmq` 確實在 `import copycat.server.app` 時就被載入。19 ms,不痛,
但那幾行註解現在說的是假話。

**真正的阻力在哪**:所有 route 靠 lexical closure 抓 `bars_cache` / `overlay_sem` /
`trading_calendar` / `wl_path`。要給某一群 route 加 executor lane 或 timing,沒有單一注入點。

**修法**:引入一個 `AppDeps` frozen dataclass(cache / semaphore / pools / calendar / 路徑),
掛 `app.state.deps`,route 從 `request.app.state.deps` 取。然後 route 群可以拆成
`routes/stock.py` / `routes/market.py` / `routes/txo.py` 各自 `register(app)`
(沿用既有的 `register_capital` / `register_oi` 模式 —— 專案已經有這個慣例了)。

**風險**:純重構。要注意測試大量直呼 `create_app(...)` 帶 kwargs(39 個呼叫點,見 app.py:535 註解),
簽名不能動。

**effort**:L

---

### B02-15 【medium / quant-gap】沒有端到端延遲時戳:無法回答「tick 進來到畫面上,花了幾毫秒」

**位置**:全域。`engine.latest_snapshot()` 的 `generated_at=time.strftime("%H:%M:%S")`
(`engine.py:141`)只有**秒**解析度;個股 tick 的 `t` 是 TC4 給的市場時刻字串。

**影響**:對量化交易系統,這是最基礎的缺口。上面每一條 finding 的「影響」欄我都只能寫
「event loop 停 58 ms」,但沒有人知道那 58 ms 在端到端延遲裡佔多少。

**修法**:在 tick 入 `on_tick` 的那一刻蓋一個 `time.perf_counter_ns()`,隨 payload 送到前端
(additive 欄,`ts_ingest_us`),前端收到時再蓋一個。加一條 `/api/metrics` 的延遲直方圖。

**風險**:additive 欄,舊前端忽略。但要小心不要每 tick 多一個 dict key 造成 payload 膨脹 ——
只在打包(`ticks` bundle)層級蓋一個,不逐筆。

**effort**:M

---

### B02-16 【low / blocking-io】`/api/stock/names` 每請求讀 60 KB JSON 並重建 2401 個 dict

**位置**:`app.py:1454-1462` → `stock_names.py:116-126`。

**證據**

```python
# app.py:1458-1462
        names = load_stock_names(names_path)
        return {
            "names": [{"code": code, "name": name} for code, name in names.items()],
            "count": len(names),
        }
```
```python
# stock_names.py:118-123 —— 每次都 exists() + read_text() + json.loads() + 全表重建
    if not path.exists(): return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = payload["names"]
    return {str(k): str(v) for k, v in raw.items()}
```

實測:`load_names()` 0.67 ms;整條 route 端到端 **2.53 ms**(86 KB 回應)。

**修法**:在 `create_app` 裡包一層 mtime cache(名稱表是版控檔,幾乎不變):
```python
_names_cache: tuple[float, dict] | None = None   # (mtime, payload)
```
降到 ~0.1 ms。

**風險**:零。`refresh-stock-names` CLI 改檔後,mtime 會變 → 自動失效。

**effort**:S

---

### B02-17 【low / allocation】capital 三條 GET route 用 `dataclasses.asdict` 逐列深遞迴複製

**位置**:`capital_api.py:253-291`。

**證據**

```python
    return {"orders": [{**dataclasses.asdict(o), "code": _fill_code(o.unit, o.stock_no)}
                       for o in client.store.orders()]}
```

`dataclasses.asdict` 是純 Python 的**遞迴深複製**(會 `copy.deepcopy` 非 dataclass 欄位,
例如 `OrderRecord.raw`)。`store.orders()` 還在 `threading.Lock` 內做一次 `sorted()` + 逐列
`_to_record()`。

**影響**:當日委託通常數十~數百列,估計 < 2 ms。**現階段不是問題**,但 `raw` 欄若含大 dict,
`deepcopy` 成本會不成比例。而且這條路是**下單後立刻輪詢**的路徑,延遲敏感。

**修法**:`dataclasses.asdict` → 手寫 `_to_wire(o)`(或 `{f.name: getattr(o, f.name) for f in fields(o)}`
的淺版)。實測 `asdict` vs 淺版通常差 5–10×。

**風險**:`raw` 欄如果前端真的在讀,淺複製會共享參考 —— 但 route 回傳後立刻序列化,
不會有人改它。要確認 `OrderRecord.raw` 的內容型別都是 JSON-safe。
**注意 CLAUDE.md §4 的 `OrderRecord.unit` / `FillRecord.unit` 字面值契約**:改序列化方式不得
漏掉 `unit` 欄(前端 `ladder-lots.ts` / `fill-marks.ts` + 後端 `_fill_code` 三方讀者)。

**effort**:S

---

### B02-18 【low / observability】`WsBroadcaster` 的丟包統計不進 `/api/health`,只能 grep log

**位置**:`ws.py:56-62`(明文:「`/api/health` 刻意不含引擎健康度,量走 log,本屬性給測試 / 診斷直讀,
prod 無讀者」)。

**影響**:CLAUDE.md §1 的驗收判準是 `grep "佇列滿" logs/server-*.log` 為 0。這是可行的
盤後判準,但**盤中沒有即時訊號**。加進 B02-12 的 `/api/metrics`(不是 `/api/health` ——
那條的職責邊界有明文理由)成本為零。

**effort**:S

---

### B02-19 【low / concurrency】`EngineRuntime._consume` 每 50 ms 建一次 `wait_for` timer;`_content()` 每次版本變動做全量 dict 深比對

**位置**:`engine.py:377-393`、`engine.py:49-60`。

**證據**

```python
# engine.py:382-386
            try:
                tick = await asyncio.wait_for(self._queue.get(), timeout=0.05)
            except TimeoutError:
                await self._maybe_self_heal()
                continue
```
```python
# engine.py:56-60
    body = {k: v for k, v in snap.items() if k != "generated_at"}
    handover = body.get("handover")
    if isinstance(handover, dict):
        body["handover"] = dict(handover)
    return body
```

**影響**:`wait_for` 每 tick 建一個 timer handle + 一顆 future。TXO 盤中數十/秒的話 < 0.1 ms/s,
**不是問題**。`_content()` 的 `==` 深比對是對 ~22 KB 快照做的,每秒至多一次 —— 也不是問題。
**列在這裡只是為了明說「已經看過、確認不需要動」**。

如果哪天 TXO 換成每 tick 數百則,`wait_for` 那圈可以改成
「`queue.get()` + 另一條 `asyncio.sleep(0.05)` 的自癒巡檢 task」,省掉逐 tick 的 timer。

**effort**:S(但現在不該做)

---

## 5. 工具選型建議與取捨

| 工具 | 用在哪 | 解決什麼 | 代價 | 結論 |
|---|---|---|---|---|
| **具名 `ThreadPoolExecutor` lane**(stdlib) | `copycat/server/pools.py`(新)+ `capital/client.py:885` + `signal_hub` jsonl + TC4 取數三處 | B02-01:送單不被 TC4 歷史取數綁架 | 零新相依;要接關機預算契約 | ✅ **最高優先,先做** |
| **event-loop lag 探針 + timing middleware**(stdlib) | `copycat/server/timing.py`(新)+ `app.py` | B02-12:所有後續改動的驗收工具 | 零新相依,< 0.01% CPU | ✅ **與上一條並列第一** |
| **`numpy`** | `copycat/live/corr_state.py::correlations`;之後可延伸到 `market_breadth.py` / `limit_streaks.py` / `backtest/` | B02-04:13 ms → < 0.3 ms(50×) | 破壞 pyproject `dependencies = []` 的 stdlib-only 哲學;+~30 MB wheel;Windows 輪子成熟無虞 | ✅ **建議導入**,但放 `[live]` extras 而不是核心 dependencies,並在 CLAUDE.md 記一筆「為什麼破例」 |
| **`bisect`**(stdlib,已用 1 處) | `corr_state._paired_returns` 三個窗的 cutoff 切片 | B02-04 的零相依版,13 ms → ~3 ms | 零 | ✅ 若不想引 numpy,這是 fallback |
| **`orjson`** | **只**在 B02-13 的 WS 序列化改造之後才有意義 | WS 序列化 3–5× | 二進位相依;**HTTP 回應層零收益**(FastAPI 0.139 已走 pydantic-core Rust) | ⚠️ **有條件導入** —— 先做 B02-13 的「序列化一次 fanout」,量到還不夠快再換 |
| **`msgspec`** | 理論上可取代 pydantic 做 request body 驗證 | 本專案只有 5 個 `BaseModel`,且 `RuleBody` 刻意把每個欄位宣告成 `object` 來繞開 pydantic 的寬鬆轉型 | 要重寫 5 個 model + 錯誤契約;收益 < 0.1 ms/req | ❌ **不建議**(過度工程) |
| **`winloop`** | `__main__.py` uvicorn loop | 未知(可能 10–30% loop throughput) | Windows-only libuv 綁定,相對年輕;要驗 ZMQ 執行緒 + ProactorEventLoop 專屬行為 | ⚠️ **有條件** —— 做 A/B 量測,有證據才換 |
| **`uvloop`** | — | — | **Windows 不支援**(實測 `auto_loop_factory` 落到 ProactorEventLoop) | ❌ 不可用 |
| **`httptools` / `websockets`** | uvicorn 協定層 | — | — | ✅ **已裝且已生效**,只要在 `uvicorn.run` 顯式寫死讓選型可見 |
| **多 `workers`** | — | — | 多 process = 多條 TC4 login = CLAUDE.md §8 refcount 地雷;且全部狀態在記憶體 | ❌ **絕對不可以** |
| **`redis` / 外部 state store** | — | — | 引入網路跳躍與另一個要顧的 process;本機單台單 process 的設計是對的 | ❌ 不建議 |
| **`granian` / `hypercorn`** 換掉 uvicorn | — | — | uvicorn + httptools 在這個量級(每分鐘幾十個請求)完全不是瓶頸 | ❌ 不建議 |

---

## 6. 不要動的地方(這些已經夠快 / 動了是倒退)

1. **FastAPI 的回應序列化路徑**。0.139 + pydantic 2.13 已經是 Rust 快路徑,1.6 MB / 6.8 ms。
   `ORJSONResponse` 會**反而變慢**(顯式指定 `response_class` 會讓 `use_dump_json` 變 False,
   退回「pydantic 驗證 → Python dict → orjson.dumps」的兩趟路)。這是個真陷阱。
2. **`app.py` 的行數本身**。實測 import 自身 3.6 ms。切檔的理由只能是可維護性。
3. **`_Tee` 的 per-write flush**。實測 5.4 µs/行 vs 0.3 µs。crash 當下的證據價值遠大於這個成本。
4. **uvicorn 的 `workers`**。見上表。
5. **`WsBroadcaster.publish` 的 dict 共享**。已經是零複製 fanout,寫得很對。
6. **`EngineRuntime` 的換代 Event**(`_mark_changed`)。這是為了修一個真實的漏版本 bug 而設計的
   (`WS-TXO-SHARED-EVENT`),每次多配一顆 Event 是正確的代價。
7. **`relay` 的三 task + `send_lock` 設計**。註解已經解釋了為什麼 lock 不能包住 `async for`
   (會讓心跳在零流量時永遠等鎖)。這是踩過坑才寫成這樣的,不要簡化。
8. **`asyncio.Semaphore(4)` 本身**。問題不是這個數字,是「逾時不進負向快取 + 無 dedup」。
   單獨調高數字只會把壓力推給 executor(B02-01)。
9. **`/api/stock/signals/today` 的 `to_thread`**。這條已經做對了,而且註解還交代了
   「先取樣再 await」的 rollover 時序理由。是全庫 route 層的正面範例。
10. **`build_daily` / `build_minute` 的 cache 鍵設計**(`|M` / `|L` 後綴、`f"{code}:{session}"`)。
    看起來囉嗦,但那是在堵「跨 session 問歷史會多掛一把 TC4 refcount key」這個真地雷。

---

## 7. 量測方法(要證明這個區塊快或慢,該怎麼量)

### M-1 event-loop lag(最重要,先裝)
```python
# 掛在 lifespan 的背景 task
async def _lag_probe():
    while True:
        t0 = time.perf_counter(); await asyncio.sleep(0.05)
        lag = (time.perf_counter() - t0 - 0.05) * 1000
        if lag > 20: logger.warning("loop lag %.0f ms", lag)
```
**判準**:盤中 `grep "loop lag" logs/server-*.log`。
- 每 60 秒準時出現一次 30–60 ms → B02-02(group-state)確認。
- 每秒出現 10–15 ms → B02-04(corr)確認。
- 開盤瞬間出現 > 200 ms → 去看 stock_engine 的回補入列(B03 區塊)。

### M-2 per-route p50/p95(B02-12 的 middleware + `/api/metrics`)
盤後一句 `curl -s localhost:8721/api/metrics | python -m json.tool` 就能排出最慢的 5 條 route。
現在完全沒有這個能力。

### M-3 winloop A/B(B02-06)
盤後用 `--verify` server(fake source,port 8722,不碰 ZMQ)跑固定負載:
```bash
# 8 條 WS + 每秒 20 個 /api/stock/group-state?codes=<50 檔> 打 5 分鐘
.venv/Scripts/python -m copycat.server --verify
# 另一個 shell 跑壓測腳本,比 p95 與 CPU%
```
**判準**:p95 改善 < 10% 就不要換(winloop 的相依風險 > 收益)。

### M-4 executor 佇列深度(B02-01 的直接證據)
```python
# 掛在 lifespan,每 5 s 一次
ex = loop._default_executor          # 或改用具名 pool 後的 pool
logger.info("executor: threads=%d queued=%d", len(ex._threads), ex._work_queue.qsize())
```
**判準**:`queued > 0` 持續超過 2 秒 = executor 已經在排隊,送單延遲已被綁架。
這一條應該在切 lane **之前**先裝,用來證明問題真的存在。

### M-5 已完成的合成 benchmark(可重跑,腳本在 scratchpad)
```
scratchpad/bench_ser.py     FastAPI 序列化三條路徑對照(0/500/2000/8000/20000 ticks)
scratchpad/bench_build.py   snapshot ticks 建構成本 + starlette send_json 成本
scratchpad/bench_route.py   httpx ASGITransport 端到端固定開銷(/api/ready 等)
scratchpad/bench_group.py   group-state 20/50/150 檔的建構 + 序列化 + payload 大小
scratchpad/bench_corr.py    correlations() 11 腿 × 3 窗 × 1800 樣本
scratchpad/scan_block.py    AST 掃「async def 內的同步阻塞呼叫」
```
這些用的都是**合成資料**。要拿到真數字,得在 prod 開一天 M-1 + M-2。

### M-6 payload 大小基準(盤中 curl)
```bash
curl -s -o /dev/null -w "%{size_download} bytes  %{time_total}s\n" \
  "localhost:8721/api/stock/group-state?codes=$(<群組成員 csv>)"
curl -s -o /dev/null -w "%{size_download} bytes  %{time_total}s\n" \
  "localhost:8721/api/stock/state/2330"
curl -s -o /dev/null -w "%{size_download} bytes  %{time_total}s\n" \
  "localhost:8721/api/corr/state"
```
**注意**:`/api/stock/state/{code}` 與 `/api/stock/group-state` **非唯讀**(會 `set_main_contract` /
`_flush_ticks`),CLAUDE.md 明文寫「不要拿這條當健康檢查輪詢」。盤中量測只能各打一發。

---

## 8. Open questions

1. **boot 序列實際耗時多少?** log 有 `「boot 序列結束(%.1fs)」`,但我沒有 prod log。
   B02-09 的 effort 是 L、風險是高,只有在這個數字 > 20 s 時才值得動。
   → 請 user 貼一行 `grep "boot 序列結束" logs/server-*.log`。
2. **盤中真實的 group-state 檔數是多少?** 150 是上限,但使用者實際常開的群組多大?
   20 檔(3 ms)與 150 檔(58 ms)是完全不同的嚴重度。
3. **`/api/stock/state/{code}` 的 tape 真實筆數?** deque maxlen 20 000,但活躍股一天的
   成交筆數是多少?這決定 B02-07 是 12 ms 還是 2 ms。
   → `curl -s localhost:8721/api/stock/state/2330 | python -c "import json,sys; print(len(json.load(sys.stdin)['ticks']))"`
4. **同時有幾個瀏覽器分頁?** 決定 B02-13(WS 重複序列化)的量級。
5. **stdlib-only 這條哲學線,numpy 可以破嗎?** 這是決策不是事實,要 user 拍板。
   我的建議:放 `[live]` extras(runtime 才需要,replay / backtest 那邊本來就可以另外裝),
   核心 `dependencies` 仍維持 `[]`。
6. **executor 是否真的塞過?** M-4 的探針裝上去跑一天就有答案。在有這個證據之前,
   B02-01 的嚴重度是「結構上必然會發生」而不是「已經發生」—— 但對送實單的系統,
   我認為不該等它發生。
7. **改 `Exception` handler 的 502 TC4_DOWN(B02-05),前端有幾個讀者?**
   需要 F 區塊(前端)配合盤點 `"TC4_DOWN"` 的比對點。
