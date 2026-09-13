# O1-ops-devloop —— Ops:執行環境、啟動、日誌、開發迴圈

分析日期:2026-09-13 · 分析對象:`C:\side-project\copycat` @ master `caca1d30`
執行環境:Windows 11 Home 26200 / Python 3.13.13 (MSC v.1944, **GIL 啟用**) / 16 CPU / Node + Vite 6

> 本報告的所有時間數字都是**本機實測**,指令與量法逐條寫在 §9。推測的地方一律標「【推測】」。

---

## 0. 執行摘要(先講結論)

這個區塊我原本預期會找到一堆「同步 IO 塞住 event loop」的問題,實測下來**大部分不成立**:

- **日誌不是瓶頸**。全庫 `logger.xxx(f"...")` = **0 次**(全部 `%`-style lazy),熱路徑(tick 分派、WS publish)上**零 logger 呼叫**。整條 logging 管線實測 **15.5 µs/行**,加上真實 Windows console 寫入 **23.8 µs/行** ≈ 40 µs;全日 access log 13,964 行 → 每天總成本 **0.56 秒**。→ **不要動**。
- **關機不是瓶頸**。`shutdown_budget.run_grace_secs()` = 83 s 是「TC4 半死」的**上界**,不是實際值;prod log 實測整段收尾 **0.21–0.30 s**。`run.ps1` 的 `WaitForExit(83000)` 在 process 一退就回。→ **不要動**。
- **真正的問題有三個**,而且都是「會直接吃掉下單延遲」的等級:
  1. **Windows 上 `asyncio` 的計時器解析度是 15.6 ms 且無條件向上取整**。實測 `asyncio.sleep(0.05)` → **62.5 ms**、`sleep(0.001)` → **15.5 ms**。這是整條 pipeline 上每一個 coalescing timer 的固定稅。用 `ntdll.NtSetTimerResolution` 可以把它壓到 0.5 ms(實測 `sleep(0.001)` 15.5 → **2.0 ms**,`sleep(0.05)` 62.5 → **50.6 ms**)。**三行程式碼、零相依、量級 12 ms。**
  2. **91 個 `asyncio.to_thread` 呼叫點共用同一個 20 worker 的預設 thread pool**,其中包含所有 TC4 阻塞 REQ(單發最壞 10 s timeout)。零自訂 executor。TC4 一忙,連 `atomic_write_bytes`、`path.read_bytes` 這種毫秒級的檔案 IO 都排在 10 秒級的 TC4 REQ 後面。
  3. **零 runtime metrics 基建**。`/api/health` 只回 `{git_sha, git_dirty, started_at}`,`/api/ready` 只回兩個 bool。沒有任何 latency histogram、tick rate、queue depth、GIL 停等的可視管道。**要做量化交易系統,這是第一個該補的東西** —— 目前唯一的效能量測手段是「盤後 grep log」。
- **開發迴圈實測**:`pytest -q` 全量 **280 s**(其中 `tests/server/` 一個目錄佔 **204 s = 73%**)、`vitest run` **35.4 s**、`tsc -p --noEmit` **5.9 s**、`vite build` **2.6 s**、`pyright` **9.5 s**、`ruff` **0.18 s**、`eslint src` **5.8 s**。後端測試是唯一真正慢的一段,而它慢的原因不是 CPU 而是**真實牆鐘等待**。

---

## 1. 架構地圖:一次啟動到底發生什麼事

```
操作者
  │
  └─ .\run.ps1                                   [run.ps1:1-179]
       ├─ 前置檢查
       │    ├─ .venv\Scripts\python.exe 存在?                     (Test-Path)
       │    ├─ python -c "import fastapi, uvicorn, zmq"            ← 子行程 #1
       │    ├─ python -c "…run_grace_secs()"  → 83                 ← 子行程 #2(實測 0.226 s)
       │    ├─ npm.cmd 找得到?
       │    ├─ port 8721 沒人聽?        (Get-NetTCPConnection)
       │    ├─ port 50774 有人聽?       ← 達錢 4 開著沒
       │    └─ frontend/node_modules 在?否則 npm install
       │
       ├─ $env:TXO_SERVER_PORT = 8721
       ├─ Start-Process python -m copycat.server   -NoNewWindow    ← backend 子行程
       ├─ Start-Process npm run dev                -NoNewWindow    ← ★ 注意:dev,不是 preview
       └─ while(true) { 500 ms 輪詢兩邊 HasExited }
            └─ finally: Stop-Tree(frontend) → Wait-GracefulExit(backend, 83 s) → Stop-Tree(backend)
```

### 1.1 backend 進程內部(`copycat/server/__main__.py`)

```
main()
 ├─ _setup_prod_log()                         [__main__.py:116-132]
 │    ├─ logs/server-YYYYMMDD-HHMM.log 開檔(append)
 │    └─ sys.stdout / sys.stderr 換成 _Tee(console + 檔,**每筆 write 即 flush**)
 │       └─ 必須在 basicConfig 之前 —— StreamHandler 建構當下快取 sys.stderr
 ├─ logging.basicConfig(level=INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
 ├─ create_app(DEFAULT_STOCK, DEFAULT_INDEX, DEFAULT_FUTURES, DEFAULT_CORR, DEFAULT_BREADTH,
 │             trading_calendar=load_trading_calendar())     ← 實測 11 ms(不含引擎)
 └─ uvicorn.run(app, host="127.0.0.1", port=8721,
                timeout_graceful_shutdown=WS_DRAIN_SECS=5)
       ↑ 沒有 workers / log_level / access_log / loop / ws_ping_* 任何一個參數
         → 全部走 uvicorn 預設:workers=1、access_log=True、log_level="info"、
           loop="auto"(Windows 無 uvloop → **ProactorEventLoop**)、
           http="auto"(httptools 0.8.0 已裝 → httptools)、
           ws="auto"(websockets 16.1.1 已裝 → websockets)、
           ws_ping_interval=20 s / ws_ping_timeout=20 s
```

`uvicorn/loops/asyncio.py` 原文(已裝版本 0.51.0):

```python
def asyncio_loop_factory(use_subprocess: bool = False):
    if sys.platform == "win32" and not use_subprocess:
        return asyncio.ProactorEventLoop
    return asyncio.SelectorEventLoop
```

→ **prod 跑的是 ProactorEventLoop**。這件事直接決定了 §3.1 的計時器解析度問題。

### 1.2 lifespan boot 序列(`copycat/server/app.py:637-1265`)

`_boot_all()` 是一個背景 task,**嚴格序列、註解明寫「順序即依賴,不可重排、不可並行」**:

```
build_info.capture()            ← git rev-parse + git status --porcelain 兩個 subprocess
EngineRuntime(txo) .start()     ← TC4 session #1 login + SUBQUOTE 317 檔 + backfill round 制
  ↓ (失敗只降級 txo 面)
_boot_engines():
  stock      ← TC4 session #2   + 自選回填 set_watchlist
  watchlist_service
  signals    ← SignalHub + discord bot login(Gateway 握手 ~1.5 s)
  index      ← TC4 session #3
  capital    ← 群益 COM(獨立執行緒)
  futures    ← TC4 session #4
  corr       ← TC4 session #5(讀 futures.state(),串鏈)
  breadth    ← FinMind
  screen
  crosscheck_task
app.state.boot_done = True
logger.info("boot 序列結束(%.1fs)")
```

**實測 boot 耗時(25 次啟動,`grep "boot 序列結束" logs/*.log`)**:

| 統計 | 秒 |
|---|---|
| 最小 | 8.3 |
| 中位 | ~12.0 |
| 最大 | 38.7 |
| 盤前 09:00 前後啟動(4 次) | 31.0 / 38.0 / 38.1 / 38.7 |

慢的那幾次全在盤前,拆解見 §4。

### 1.3 執行緒與並發拓樸

| 來源 | 檔案 | 數量 | 性質 |
|---|---|---|---|
| uvicorn 主 loop | — | 1 | ProactorEventLoop |
| TC4 `_listen_loop`(ZMQ SUB 阻塞 recv) | `live/tc4.py:1185` | 5(每 session 一條) | `sock.recv()` → `json.loads` → dispatch,**持 GIL 解析** |
| TC4 自癒 watchdog | `live/tc4.py`(`_start_healer`) | 5 | 每 5 s 巡檢 |
| 群益 COM 專屬執行緒 | `capital/client.py` | 1 | COM STA |
| discord.py gateway | 套件內 | 若干 | |
| `asyncio.to_thread` 預設 pool | **無自訂**(`grep ThreadPoolExecutor(` → 0 命中) | **20**(`min(32, 16+4)`) | **91 個呼叫點共用** |

`sys.getswitchinterval()` = **0.005**(預設)→ 任何 CPU-bound 執行緒最長可持 GIL 5 ms 不讓位。

### 1.4 frontend

```
vite.config.ts
 ├─ plugins: react() + tailwindcss() + buildShaPlugin()
 ├─ define: __GIT_SHA__ = gitSha()          ← build 當下凍結;dev 另有 /__build/sha 現算
 └─ server.proxy: /api → 127.0.0.1:8721 , /ws → ws:8721
    (preview 繼承:vite 原始碼 `proxy: preview2?.proxy ?? server.proxy` —— 已在
     node_modules/vite/dist/node/chunks/dep-Dm0c1Wj2.js:48365 驗證)
```

`src/main.tsx` 在 `import.meta.env.DEV` 下安裝 `installUserTimingGuard({maxEntries: 5000})`,
這是 2026-08-19 那次 renderer 10 GB Aw Snap 的修法。它的 docstring 留下了一句**對整個
前端改造最重要的事實證據**:

> 「本 app **每則 WS 訊息都讓整棵樹 re-render** → 實測 **632 筆/秒** ≈ 1.1 MB/s」
> —— `frontend/src/lib/dev-perf-guard.ts` 檔頭

(這條屬於 F 區塊的職責,但它是在 ops 層被發現的,列在這裡當交叉證據。)

---

## 2. 熱路徑盤點(ops 視角)

ops 區塊「每 tick 跑」的東西其實只有一條半:

| # | 路徑 | 位置 | 頻率 | 每次做什麼 |
|---|---|---|---|---|
| H1 | ZMQ SUB → tick 分派 | `live/tc4.py:1226-1253` `_listen_loop` | **每 tick(開盤數百/s × 5 session)** | `sock.recv()` → `[:-1]` → `.decode("utf-8")` → `raw.find(":")` → `json.loads` → `_note_push`(建 5-tuple 指紋、3 次 dict get/set)→ `parse_realtime` → callback。**零 logger 呼叫**(唯一一個 `logger.debug` 在 `_note_push:805`,只在「重掛後 5 s 內同指紋 snapshot」才走到)。 |
| H2 | WS fanout publish | `server/ws.py:65-80` `WsBroadcaster.publish` | 每則廣播(stock 打包 ≤10/s、futures 0.1 s coalesce、state 1 s throttle) | `_settle_drop_window`(兩個比較)+ per-client `put_nowait`。便宜。 |
| H2b | WS 送出 | `server/ws.py:262-265` `_send` | 同上 × client 數 | `starlette.WebSocket.send_json` → `json.dumps` **per client**(同一 dict 序列化 N 次,無共用) |
| H3 | uvicorn access log | uvicorn 內部 → `_Tee.write` | **每個 HTTP request**(全日 13,964 次) | logging format + 檔案 write+flush + console write ≈ **40 µs** |
| H4 | logging 被 level 濾掉 | — | — | 實測 **0.18 µs**(`%`-style,參數不求值)→ 全庫 13 個 `logger.debug` 在 level=INFO 下**幾乎免費** |

**H1 的實際量級**:`logs/server-20260911-0905.log` 全日 17,978 行,其中 13,964 行是 access log
(78%),真正的應用 log 只有 ~3,855 行。tick 本身**完全不落 log**。

---

## 3. Findings

### O1-01 【critical】Windows asyncio 計時器解析度 15.6 ms,且所有 sleep 向上取整 —— 整條 pipeline 的固定延遲稅

**位置**:`copycat/server/__main__.py:193`(`uvicorn.run(...)` 未指定 loop)
+ `uvicorn/loops/asyncio.py::asyncio_loop_factory`(Windows → `ProactorEventLoop`)
+ 所有 `asyncio.sleep` / `loop.call_later` 使用點(`server/stock_engine.py:249` `tick_flush_secs=0.1`、
`server/app.py:529` `throttle_secs=1.0`、`server/signal_hub.py` basis gap、futures 0.1 s coalesce…)

**證據(本機實測,ProactorEventLoop,60 次取樣)**:

```
OFF  0.001: med 15.55 p95 16.04 | 0.01: med 15.53 p95 16.29 | 0.05: med 62.46 p95 63.59
     | 0.1: med 109.05 p95 111.09 | 0.2: med 202.82 p95 205.72
```

對照組,先呼叫 `ntdll.NtSetTimerResolution(5000, True, ...)`(要求 0.5 ms):

```
ON   0.001: med  1.99 p95  2.56 | 0.01: med 11.02 p95 11.55 | 0.05: med 50.56 p95 63.53
     | 0.1: med 109.41 p95 110.78 | 0.2: med 202.76 p95 205.65
```

根因不在 `time.sleep`(那條是準的):

```
time.sleep(0.001): 1.53 ms     ← CPython 3.11+ 在 Windows 用高解析 waitable timer
time.sleep(0.05):  50.22 ms
select([s],[],[],0.001): 15.57 ms   ← 問題在這裡:event loop 的等待原語
select 同一發 + NtSetTimerResolution: 1.0 ms
```

**注意**:`winmm.timeBeginPeriod(1)` **回傳 0(成功)但完全無效**(Selector / Proactor 都沒改善)——
Windows 11 上只有 `NtSetTimerResolution` 真的改到。這一點如果不實測會踩空。

**影響**:
- `tick_flush_secs = 0.1` 的實際 flush 間隔是 **109 ms**,不是 100 ms。
- 任何 < 15 ms 的 coalescing / 退避 / 重試 sleep **全部被拉到 15.5 ms**。想把逐筆節奏從 100 ms 收到 20 ms?收不到 —— 會落在 31 ms。
- 每一層 timer 都吃一次:TC4 tick → stock_engine 打包 timer(109 ms)→ WS → 瀏覽器。單是這一層就是 **9 ms 的無謂延遲**,而且是**下限**(p95 111 ms)。
- 對「要下實單」的系統,這是在做任何 Python 層微優化之前就該先拿掉的 8–16 ms。

**修法**(`copycat/server/__main__.py::main`,uvicorn.run 之前):

```python
# Windows event loop(select / IOCP)的等待解析度預設 = 系統 tick 15.6 ms,
# 所有 asyncio.sleep / call_later 向上取整到 tick 邊界。timeBeginPeriod 在
# Windows 11 無效(回 0 但量不出差別),只有 NtSetTimerResolution 真的改到。
if sys.platform == "win32":
    import ctypes
    _cur = ctypes.c_ulong()
    ctypes.WinDLL("ntdll").NtSetTimerResolution(5_000, True, ctypes.byref(_cur))  # 0.5 ms
```

**取捨**:
- 提高系統計時器解析度是**全機器生效**、增加耗電與中斷率。專用交易機完全可接受;筆電外出用要權衡。
- 實測發現 **0.1 s / 0.2 s 兩檔沒有改善**(109 / 202 ms 兩邊一樣),且 0.05 的 p95 在 ON 模式仍是 63.5 ms(bimodal)——【推測】有別的行程週期性把解析度降回去。所以這不是「打開就穩」,要配合 §9 的持續量測。
- **不必**為此換 event loop:Selector 與 Proactor 實測**完全一樣**(都是 15.5 / 62.3),換 loop 解決不了。
- `winloop`(uvloop 的 Windows port,libuv)是唯一可能繞過的第三方選項,但 **必須先量再決定** —— libuv 在 Windows 同樣走 IOCP,不保證更好;而它會改變整個 loop 的行為(TC4 五條 session、8 條 WS、群益 COM 執行緒都在上面),blast radius 極大。

**風險**:零契約衝突(不碰任何跨檔契約)。行為改動只有「timer 更準」,但這會讓一些**依賴牆鐘寬鬆度的測試變緊**——特別是 `tests/server/test_stock_engine.py:3864` 那條註解明寫的假設:
> 「在 Windows 上 `await asyncio.sleep(0.1)` 對 interval=0.01 實際只跑 ~3 拍」

改了之後就變成 ~9 拍。**這條註解就是這個 finding 的第二份獨立證據,也是改動時第一個會紅的地方。**

**effort**:S(3 行)+ M(測試假設回校)

---

### O1-02 【high】91 個 `to_thread` 呼叫點共用同一個 20 worker 預設 pool —— TC4 一忙,所有檔案 IO 陪葬

**位置**:全庫零自訂 executor(`grep -rn "set_default_executor\|ThreadPoolExecutor(" copycat/` → **0 命中**)

呼叫點分佈:
```
24 copycat/server/stock_engine.py      11 copycat/server/index_engine.py
 8 copycat/server/signal_hub.py         8 copycat/server/futures_engine.py
 8 copycat/server/engine.py             7 copycat/server/app.py
 6 copycat/server/corr_engine.py        5 copycat/capital/client.py
 4 copycat/server/breadth_engine.py     3 copycat/server/screen_engine.py
 3 copycat/server/oi_levels.py          2 copycat/server/stkfut_catalog.py
 1 copycat/trading_calendar.py          1 copycat/server/breadth_fetch.py
```

同一個 pool 裡混著兩種完全不同時間尺度的工作:

```python
# 10 秒級(TC4 ZMQ REQ,_REQ_TIMEOUT_MS = 10_000)
copycat/server/stock_engine.py:878   await asyncio.to_thread(self._source.fetch_daily_bars, code, n)
copycat/server/stock_engine.py:551   await asyncio.to_thread(self._acquire, code, "watchlist")
copycat/server/stock_engine.py:1589  ticks = await asyncio.to_thread(self._source.backfill, code)

# 毫秒級(本機檔案)
copycat/server/signal_hub.py:1190    await asyncio.to_thread(self._append_jsonl, row)
copycat/server/signal_hub.py:1317    raw = await asyncio.to_thread(path.read_bytes)
copycat/server/signal_hub.py:1381    await asyncio.to_thread(atomic_write_bytes, path, b"".join(lines))
copycat/server/signal_hub.py:497     await asyncio.to_thread(save_rules, self._rules_path, ...)
```

**實測環境參數**:`os.cpu_count()` = 16 → 預設 `max_workers = min(32, 16+4) = 20`。

**影響**:TC4 半死時(這不是假想 —— `docs`/skill 裡有 08-28「斷達錢 4 11.5 分鐘」的實錄),
每一發 TC4 REQ 吃滿 `_REQ_TIMEOUT_MS` 10 s。五條 session × 多個併發 task,湊滿 20 個 worker
並不難。一旦湊滿:
- 訊號列 `_append_jsonl` 寫不進去 → jsonl(**真相源**)延後;
- `atomic_write_bytes` 的自選 / 規則落檔卡住;
- `screen_engine` / `breadth` 的取數排在後面。

失效樣態是**靜默延遲**,不是錯誤 —— 跟這個 repo 裡一再出現的「零錯誤訊號」是同一類。

**修法**:切 lane。三個 executor,各自有界:

```python
# copycat/server/executors.py(新)
from concurrent.futures import ThreadPoolExecutor
TC4_POOL  = ThreadPoolExecutor(max_workers=8,  thread_name_prefix="tc4")   # ZMQ REQ,10 s 級
FILE_POOL = ThreadPoolExecutor(max_workers=4,  thread_name_prefix="fileio")# atomic write / read_bytes
# 預設 pool 留給其餘(discord fallback、群益 COM 邊界…)
```
呼叫端 `await asyncio.to_thread(f, ...)` → `await loop.run_in_executor(TC4_POOL, f, ...)`。
或者更小的改法:包一層 `copycat/server/offload.py::tc4_call(fn, *a)` / `file_call(fn, *a)`,
呼叫端只改 import 名,行為一致。

**取捨**:純 stdlib,零新相依,符合本專案 stdlib-only 哲學。代價是多兩個常駐 pool
(閒置時 0 執行緒,lazily 起)與關機時多兩個 `shutdown(wait=...)` —— 後者**會動到
`shutdown_budget` 的口頭契約**,見風險欄。

**風險**:**會動到 CLAUDE.md §4「關機預算三方同源」契約**。`copycat/server/shutdown_budget.py`
目前的式子是

```python
def lifespan_close_worst_secs() -> float:
    return TC4_LANE_DEPTH * close_worst_secs() + COM_JOIN_TIMEOUT_SECS + LIFESPAN_SLACK_SECS
```

加了自訂 pool 之後,關機時要 `pool.shutdown(wait=True)` 等在飛的 TC4 REQ 收完 —— 那一段
**必須進預算**,否則 `run.ps1` 的 `WaitForExit($graceSecs)` 會在 pool 還沒收乾淨時硬殺,
正好重演 §「下一台開頭 ~60 s 零推播」那個病。同動點:
`shutdown_budget.py`(加一項 `POOL_DRAIN_SECS`)→ `tests/server/test_shutdown_budget.py`
(釘的是**不等式**,會自動紅)→ `run.ps1` 不必改(那正是同源的意義)。

**effort**:M

---

### O1-03 【high】零 runtime metrics 基建 —— 目前唯一的效能量測手段是「盤後 grep log」

**位置**:`copycat/server/app.py:1289-1312`

```python
@app.get("/api/health")
async def health(request: Request) -> dict:
    """執行中 server 的建置身分 —— 「這台是不是舊版」的唯一可視管道。
    刻意不含引擎健康度:那是另一個問題…
    """
    return request.app.state.build.as_dict()   # {git_sha, git_dirty, started_at}

@app.get("/api/ready")
async def ready(request: Request) -> dict:
    return {"ready": bool(...boot_done), "error": getattr(state, "boot_error", None)}
```

`build_info.BuildInfo.as_dict()` 的完整值域(`server/build_info.py:35-40`):
`{"git_sha": str|None, "git_dirty": bool|None, "started_at": str}`。**就這三個欄位。**

現存的唯一量測點是 `WsBroadcaster.dropped` / `window_dropped`,而它的 docstring 明寫:

```python
#: `/api/health` 刻意不含引擎健康度(其 docstring),量走 log,本屬性
#: 給測試 / 診斷直讀,prod 無讀者。          —— server/ws.py:60-61
```

盤後判準因此長成這樣(CLAUDE.md §1 表格):
> `grep '"kind": "policy"' data/signals/<YYYYMMDD>.jsonl` … `grep 佇列滿 logs/server-*.log` 為 0

**影響**:要把系統改造成「專注高效能的量化交易系統」,第一件事是**知道現在多慢**。
目前完全沒有:
- tick 到達 → WS 送出 的端到端延遲分佈(p50/p95/p99/max);
- 每條 TC4 session 的 tick rate 與 gap;
- `to_thread` pool 的排隊深度(§O1-02 的失效樣態沒有任何管道看得到);
- event loop lag(`loop.time()` 漂移 —— 在 §O1-01 的 15.6 ms 稅之上,還有 GIL 造成的抖動);
- GC pause。

沒有這些,任何「改用 numpy / polars / orjson」的決策都是憑感覺,而且改完也**無法證明**變快了。

**修法**(stdlib-only 可行,不必引 prometheus):

1. `copycat/server/metrics.py` —— 一個 `Histogram` 類:固定 bucket 邊界的 `array('Q')` 計數器 +
   `count/sum/max`,`observe()` 是 `bisect.bisect` + 一次 `+=`(**約 0.3 µs,可以掛在每 tick 上**)。
   不要存原始樣本(那才是 O(n) 記憶體)。
2. 三個埋點:
   - `live/tc4.py:1249` `self._last_msg = time.monotonic()` 旁邊已經有時間戳,順手記 `recv→dispatch` 耗時;
   - `server/ws.py:65` `publish()` 入口記 publish→首個 `send_json` 完成的延遲;
   - 一個 `asyncio` 背景 task 每 100 ms 量 `loop.time()` 與期望值的差 = **event loop lag**,
     這是 §O1-01 與 §O1-02 兩個問題的共同觀測指標。
3. `GET /api/metrics` 回 JSON。**注意**:不要塞進 `/api/health` —— 那條 endpoint 的 docstring
   明寫「刻意不含引擎健康度…混進來會讓這條在引擎壞掉時也答不出版本」,那個設計決策是對的。
   `/api/metrics` 是新的一條。
4. 前端加一個 debug 面板讀它(既有 `/api/health` 已經被前端每天打 385 次,通道現成)。

**取捨**:
- 自刻 vs `prometheus_client`:後者多一個相依 + 一個 exposition format 解析器,而這是**單人本機**系統,沒有 scraper。自刻 ~120 行,勝。
- 別用 `time.perf_counter()` 以外的時鐘;Windows 上 `perf_counter` 解析度 1e-7(已驗)。

**風險**:低。新增 endpoint 不碰任何既有契約。唯一要小心的是**埋點本身不能變成熱路徑成本** ——
`observe()` 必須是純 int 運算,不得 format 字串、不得配置物件。

**effort**:M

---

### O1-04 【medium】`_Tee` 每筆 write 即 flush + uvicorn access_log 全開,但**實測不是瓶頸**(含反向結論)

**位置**:`copycat/server/__main__.py:83-90`

```python
def write(self, s: str) -> int:
    if self._sink is not None:
        try:
            self._sink.write(s)
            self._sink.flush()        # ← 每一筆
        except (OSError, ValueError) as e:
            self._degrade(e)
    return self._stream.write(s)      # ← console
```

`uvicorn.run(app, host=..., port=..., timeout_graceful_shutdown=5)` —— **沒有 `access_log=False`**。

**證據(全日 log `logs/server-20260911-0905.log`)**:

```
total lines            17,978
access log lines       13,964  (78%)
  /api/capital/positions  4,328
  /api/capital/status     2,247
  /api/stock/group-state  1,247
  /api/capital/fills      1,210
  /api/capital/orders       816
  /api/txo/contracts        759
  /api/calendar             560
  /api/health               385
```

**成本實測**:

| 量法 | µs/行 |
|---|---|
| `f.write(line); f.flush()`(tempfile) | **4.4** |
| `f.write(line)` 無 flush | 0.3 |
| `logging.info` → StreamHandler → `_Tee`(檔 flush + null console) | **15.5** |
| plain `FileHandler`(對照) | 15.6 |
| 真實 Windows console `CONOUT$` write+flush | **23.8** |
| level 濾掉的 `logger.info`(`%`-style) | **0.18** |

→ 每行 access log 全成本 ≈ **40 µs**。全日 13,964 行 = **0.56 秒/天**。

**結論:這不是瓶頸,不要為了它動手。** 把它寫進 findings 是因為:
(a) 這是「直覺上最像瓶頸、實測卻不是」的典型,省下未來重複踩;
(b) 有一個**真的該做**的小改:`_Tee.flush()` 的註解自己說了它不該依賴 per-write flush。
若未來真的把 tick 級資料寫進 log(例如 §O1-03 的原始樣本落檔),per-write flush 會瞬間變成問題。
屆時正解是 stdlib `logging.handlers.QueueHandler` + `QueueListener`,把 IO 整個搬到專屬執行緒
——**現在不必做**。

**唯一現在值得做的**:`access_log` 的價值 vs 噪音比很差(78% 的 log 是它,而排查問題時真正在
看的是另外那 3,855 行)。可以考慮 `uvicorn.run(..., access_log=False)` 並在 app 內加一個
只記「非 200 / 或耗時 > N ms」的 middleware —— **換來的不是速度,是 log 可讀性**,以及
盤後 grep 不用再過濾。

**風險**:零契約。改 `access_log=False` 會讓既有排查習慣(從 log 看前端打了哪些 API)失效,
要先問過 user。

**effort**:S

---

### O1-05 【medium】`sys.setswitchinterval` 用預設 5 ms —— 10+ 條 GIL-bound 執行緒對 event loop 的抖動上界

**位置**:無(沒有人設定)。實測 `sys.getswitchinterval()` = **0.005**。

**證據**:`live/tc4.py:1226-1253` 的 `_listen_loop` 是純 Python 熱迴圈,每 tick 做
`.decode("utf-8")` + `raw.find(":")` + `json.loads(...)`,**全程持 GIL**:

```python
raw = (sock.recv()[:-1]).decode("utf-8")   # ← recv 釋放 GIL,decode 不釋放
...
msg = json.loads(raw[idx + 1 :])           # ← C 層但持 GIL
```

五條這樣的執行緒 + 五條 healer + 群益 COM 執行緒,全部與 uvicorn 的 event loop 搶同一把 GIL。
預設 switch interval 5 ms 表示:**event loop 最壞要等 5 ms 才拿得到 GIL**。

**影響**:這 5 ms 疊在 §O1-01 的 15.6 ms 上,就是 tick → WS 路徑上「看不見的」20 ms。
對「速度夠快夠順暢」這個目標,這兩條是同一個量級的問題。

**修法**:`copycat/server/__main__.py::main()` 開頭 `sys.setswitchinterval(0.001)`(一行)。
代價是 context switch 次數上升;16 核機器上這個代價可忽略。**必須配 §O1-03 的 event loop lag
histogram 才證明得出有沒有效** —— 這正是為什麼 O1-03 排在前面。

**更根本的修法(L 級,列出但不建議現在做)**:把 `json.loads` 搬出 Python 執行緒。
選項:(a) `msgspec.json.decode` —— C 層、**解析期間釋放 GIL**、比 stdlib json 快 3–6×;
(b) 讓 `_listen_loop` 只做 `recv` + 入 `collections.deque`,解析在 event loop 上批次做。
(a) 是低風險高報酬,但它動的是 B 區塊(tick 解析)的程式碼,這裡只點名。

**風險**:零契約。行為改動 = 排程更細,可能讓某些「靠執行緒慢」而恰好通過的測試變 flaky
(候選:`tests/live/test_tc4.py:539` `time.sleep(0.5)  # 讓迴圈至少失敗一次進 backoff`)。

**effort**:S

---

### O1-06 【medium】後端測試 280 s,其中 `tests/server/` 一個目錄 204 s(73%)—— 慢在真實牆鐘等待,不是 CPU

**實測(逐段獨立跑,`-p no:cacheprovider`)**:

| 目標 | 測試數 | 秒 | 每測試 |
|---|---:|---:|---:|
| 全量 `pytest -q` | 3,569 | **280.0** | 78 ms |
| `--collect-only` | 3,569 | 7.6 | — |
| `tests/server/`(目錄) | 1,540 | **204.5** | **133 ms** |
| `tests/server/test_stock_engine.py` | 207 | **88.8** | **429 ms** |
| `tests/live/` | 689 | 10.7 | 15 ms |
| `tests/capital/` | 425 | 2.2 | 5 ms |
| `tests/test_market.py` | 11 | 1.4 | — |

`--durations=0` 對 `test_stock_engine.py` 的拆解:

```
tests: 164   call sum: 87.0 s   setup: 0.1 s   teardown: 0.0 s
```

→ **100% 在測試本體**,不是 fixture、不是 collection、不是 app 建構
(獨立量:`create_app(FakeTxoSource())` = **11 ms**,`TestClient` 建構 ≈ 0)。

字面 sleep 只解釋了一小部分:

```
tests/server/ 字面 asyncio.sleep(<5s): 149 處,總和 17.66 s
tests/ 字面 time.sleep:                 31 處,總和  5.20 s
```

剩下的 ~180 s 是**等待引擎自己的計時器**(`throttle_secs=0.01`、`tick_flush_secs=0.1`、
退避階梯),而根據 §O1-01,Windows 上這些 sleep 全部被拉到 15.6 ms 的倍數。
`tests/server/test_stock_engine.py:3864` 那條註解就是直接證據。

**影響**:改造期會頻繁改 `server/` 底下的 code,而那正好是最慢的一段。
單跑 `test_stock_engine.py` 就要 **89 秒** —— 一個 red-green 迴圈最少 3 分鐘。

**修法(依 CP 值排序)**:
1. **`pytest-xdist`**(`-n auto`)。這些測試是牆鐘等待型(不吃 CPU),16 核機器上
   理論加速接近 worker 數。**實測前不要承諾數字**,但 204 s → 30–50 s 是合理期待。
   風險:`tests/server/` 有共用檔案落點(`data/`、`logs/`)與 port 使用,需要先掃過
   有沒有共用全域狀態;`--dist loadfile` 可以把同檔測試綁同一個 worker,降低風險。
2. **裝 `pytest-timeout`** 給每測試上限(現在沒有;一個測試卡死 = 整個 gate 掛住)。
3. 把 `throttle_secs=0.01` 這類「小到被 Windows 15.6 ms 吃掉」的參數,換成
   **可注入的假時鐘 + 手動推進**(這個 repo 已經有大量「時鐘可注入」的設計,
   例如 `_heal_tick(now)`、`_now_fn`,方向是對的,只是還沒推到 `asyncio` timer 這一層)。
   這是 L 級工程,但它同時解決 §O1-01 改完之後測試假設全紅的問題。

**風險**:測試基建改動,不碰 prod code。但 xdist 會改變測試的隔離假設 —— 這個 repo
CLAUDE.md 明寫「測試只寫在與 user 議定的 seams」,加平行化前要確認沒有跨檔共享 fixture 落點
(`pythonpath = ["."]` + `tests.data.test_import_neigui` 這個跨檔 helper 是既知的共享點)。

**effort**:S(xdist 試裝)→ L(假時鐘化)

---

### O1-07 【medium】盤前啟動 38 s:TXO 回補 round 制空轉 + TC4 history 10 s timeout 串在 boot 序列上

**證據**(`logs/server-20260904-0900.log`,boot = 38.7 s):

```
09:00:53.889  stdout/stderr 轉存 …
09:00:54.036  copycat server build 0b73e512 +dirty started_at=…
09:00:54.045  TC4 connected, session=ad775627
09:00:55.895  subscribed 317 symbols (series=TX2.202609)
09:00:56.157  backfill round 1: 315 pending, 2 ticks
09:00:56.761  backfill round 2: 315 pending, 2 ticks
09:00:57.377  backfill round 3: 315 pending, 2 ticks
09:00:57.990  backfill round 4: 296 pending, 78 ticks
09:00:58.605  backfill round 5: 265 pending, 289 ticks
09:00:59.212  backfill round 6: 232 pending, 474 ticks
09:00:59.791  backfill round 7: 217 pending, 547 ticks
09:01:00.372  backfill round 8: 216 pending, 548 ticks     ← 1 檔進展
09:01:00.937  backfill round 9: 216 pending, 548 ticks     ← dry 1
09:01:01.511  backfill round 10: 216 pending, 548 ticks    ← dry 2
09:01:02.080  backfill round 11: 216 pending, 548 ticks    ← dry 3 → 早停
09:01:02.080  backfill done: 548 ticks from 316 symbols
...
09:01:14.599  history TC.S.TWS.1303(DK): 10.0s 內首頁未備妥,回空(timeout,非無資料)
09:01:14.599  daily bars 1303: DK 空,fallback 1K 聚合(視窗 2026-08-15..)
09:01:24.603  history TC.S.TWS.1303(1K): 10.0s 內首頁未備妥,回空(timeout,非無資料)
09:01:24.603  CDP 基準日 K 逾時(非 TC4 down):1303(…)
...
09:01:32.104  history TC.S.TWS.6207(TICKS): 30.0s 內首頁未備妥,回空
09:01:32.558  history TC.S.TWS.IX0001(1K): 30.0s 內首頁未備妥,回空
```

兩段各自的帳:
- **回補空轉**:`live/tc4.py:880-897`。round 制已有早停(`_HARVEST_DRY_LIMIT = 3`,
  `_HARVEST_ROUNDS = 16`),設計是對的。但 dry 的那 3 輪仍然**逐檔重打** 216 支的
  `_fetch_symbol_ticks`(阻塞 REQ),約 **1.7 s** 純浪費。
- **10 s timeout 串聯**:`1303` 一檔就吃掉 **20 秒**(DK 10 s + 1K fallback 10 s),而且
  `_REQ_TIMEOUT_MS = 10_000`。CDP 基準 sweep 雖然是背景 worker(`signal_hub.py:821-838`,
  單一 worker + `basis_gap_secs` 間隔),不擋 `boot_done`,但它**與主圖回補共用同一條 TC4
  stock session 的 `api.lock`**(該函式註解自己寫了)。

**影響**:盤中改完 code 要重啟 → 12 s(中位)到 39 s(盤前)的零推播窗。
對「盤中要改要驗」的開發迴圈,這是最直接的痛點。

**修法**:
1. **回補 dry 輪指數退避**:dry 第 1 輪等 0.5×poll_wait、第 2 輪 1×、第 3 輪 2×,
   而不是每輪都全量重打。省 ~1 s,S 級。
2. **CDP 基準 sweep 併行化**:`_basis_worker` 是單一 worker 串行。改成 N=3 的
   worker pool(仍受 `api.lock` 序列化,但 timeout 那 10 s 是**等待**不是持鎖,可以疊)。
   要配 §O1-02 的 TC4 lane 一起做,否則只是把壓力搬到預設 pool。
3. **不要**縮 `_REQ_TIMEOUT_MS` —— 它是 `shutdown_budget` 的輸入(`close_worst_secs()`
   = `10 + max(2×10, 2×12)` = 34 s → `run_grace_secs()` = 83)。改它 = 改 CLAUDE.md §4
   「關機預算三方同源」契約的**產生點**,`tests/server/test_shutdown_budget.py` 會紅,
   而且會讓半死的 TC4 更早被判死。

**風險**:(1) 零契約。(2) 動 `basis_gap_secs` 語意與 `api.lock` 競爭 —— 中風險,
需要 `signal_hub` 的 characterization 測試護住。(3) **不要做**。

**effort**:S(1)/ M(2)

---

### O1-08 【medium】`run.ps1` 啟動的是 `npm run dev`,但 CLAUDE.md 明說整天掛著要用 `preview`

**位置**:`run.ps1:142-144`

```powershell
Write-Host '[run] frontend -> vite dev(實際網址看下方 vite 輸出)' -ForegroundColor Green
$frontend = Start-Process -FilePath $npm -ArgumentList 'run', 'dev' `
    -WorkingDirectory $frontendDir -NoNewWindow -PassThru
```

對照 CLAUDE.md §1 的表格:

> **看盤日常(prod build)** | `npm run build` 後 `npm run preview`(port 4173)…
> dev build 的 React Component Performance Track 已由 dev-perf-guard 堵住洩漏,
> **但 props-diff 開銷仍在 —— 整天掛著一律用本列**,`npm run dev` 只做開發(2026-08-20)

**影響**:唯一的「一鍵啟動」腳本走的是**被文件明令禁止**用於看盤的那條路。
dev build 的成本(已有本 repo 自己的實證):React development build 對每次
props identity 改變的 re-render 打一筆 `performance.measure`,實測 **632 筆/秒 ≈ 1.1 MB/s**
(`frontend/src/lib/dev-perf-guard.ts` 檔頭)。guard 只是防止記憶體爆,**產生那些 measure 的
開銷還在**,而且 `<StrictMode>`(`src/main.tsx:20`)在 dev 下還會把每次 render 跑兩遍。

已驗證的次要事實:`vite preview` 的 proxy **會繼承** `server.proxy`
(vite 6 原始碼 `proxy: preview2?.proxy ?? server.proxy`),所以 CLAUDE.md 那句
「proxy 沿用 dev 的 /api + /ws → 8721」是對的,preview 不需要額外設定。

**修法**:`run.ps1` 加一個 `-Dev` switch,**預設走 build + preview**:

```powershell
param([string]$BackfillDate, [switch]$Dev)
...
if ($Dev) {
    $frontend = Start-Process $npm -ArgumentList 'run','dev' ...
} else {
    Push-Location $frontendDir; try { & $npm run build } finally { Pop-Location }
    if ($LASTEXITCODE -ne 0) { Fail 'frontend build 失敗' }
    $frontend = Start-Process $npm -ArgumentList 'run','preview' ...
}
```
`npm run build` 實測 = `tsc -b`(5.9 s)+ `vite build`(2.6 s)≈ **9 秒**,遠小於 boot 的 12–39 s,
完全可以串在啟動流程裡而不拖慢整體(兩者本來就並行)。

**風險**:**會動到 port**:dev 是 5173,preview 是 4173。`run.ps1` 目前只檢查 8721 有沒有被占,
沒檢查前端 port;改了之後「畫面開在哪個網址」也變了。另外 build 失敗會變成啟動失敗
(現在 dev 模式下型別錯只會在畫面上紅字)—— 這是**行為改動**,要先問 user。

**effort**:S

---

### O1-09 【low】海外腿自癒每日 ~1,920 次空 churn —— log 噪音 + TC4 端 session 壓力

**證據**(`logs/server-20260911-0905.log`,非 access log 部分 = 3,855 行的組成):

```
807  copycat.server.stock_engine WARNING trade-status-observe code=N N->N …
251  copycat.live.tc4 WARNING TC4 REALTIME 零推播自癒:TC.F.OSE.NKM.HOT 靜默 Ns
244  …                                              TC.F.CME.NQ.HOT
244  …                                              TC.F.CME.ES.HOT
242  …                                              TC.F.CME.GC.HOT
242  …                                              TC.F.CME.CL.HOT
242  …                                              TC.F.CBOT.YM.HOT
241  …                                              TC.F.SGX.TWN.HOT
240  …                                              TC.F.CFE.VX.HOT
 88  copycat.server.index_engine WARNING index 分時自癒:minutes 落後 >N 分,重…
 71  copycat.server.index_engine WARNING index 分時自癒無進展(window_variant=N…
```

每一發自癒不只是一行 log,而是真的對 TC4 送 REQ(`live/tc4.py:732-756`):

```python
def _heal_resub(self, symbol: str, *, bump_variant: bool) -> bool:
    try:
        with self._lock:                      # ← 與 _check_stale 互斥
            if symbol not in self._subscribed:
                return False
            if bump_variant:
                self._rt_request("UNSUBQUOTE", symbol)   # REQ #1
                self._window_variant[symbol] = self._next_variant(symbol, bump=True)
            self._resub(symbol)                          # REQ #2
```

8 條海外腿 × ~242 = **~1,930 次 / 日**,每次 1–2 個 ZMQ REQ round-trip,且持 session 鎖。

`configs/correlation.json` 的註解說明了閘的形狀:
> symbol 的**前綴決定自癒閘**(`corr_source.py::segment_leg_gate`):`TC.F.TWF.` 吃台期交日夜盤閘、
> `TC.S.TWS.` 吃個股日盤閘、**其餘各段恆開**

→ CME / CBOT / OSE / SGX / CFE 這些腿的自癒閘**整天恆開**,包括它們自己的休市時段。
CLAUDE.md 記的 `sparse` 旗標目前只標了 **SXF 與 VX** 兩腿(`tests/test_corr_config.py::
test_sparse_legs_are_sxf_and_vx_and_the_repo_file_agrees` 鎖住)。

**影響**:
- 不影響 tick 分派(listener thread 獨立讀 SUB socket,不受 `_lock` 影響)→ 所以**不是 critical**;
- 但它佔掉 corr session 的 `api.lock`,與 corr 自己的 REQ 競爭;
- 每日 1,930 行 WARNING 把真正該看的訊號稀釋掉(這是可讀性成本,不是速度成本)。

**修法**:替各海外段補時段閘(`segment_leg_gate` 加 CME / CBOT / OSE / SGX 的 session 窗),
或把這些腿也標 `sparse: true`(只吃 R1 不吃 R2,`tc4.py:719-720`)。

**風險**:**會動到 CLAUDE.md §4「相關係數稀疏腿 `sparse` 旗標」契約**:
產生點 = `configs/correlation.json` 腿的 `"sparse": true`(**只認字面 true**)
+ `copycat/corr_config.py::DEFAULT_CONFIG` 的同一組;兩邊集合一致由
`tests/test_corr_config.py::test_sparse_legs_are_sxf_and_vx_and_the_repo_file_agrees` 釘住
—— 加腿要**同時**改 JSON + `DEFAULT_CONFIG` + 那條測試的名字與斷言。
漏標的症狀是「該腿整場不救」(誤標)或「每 240 s 一發自癒」(漏標),**兩邊都零錯誤訊號**。

**effort**:S(標 sparse)/ M(補時段閘)

---

### O1-10 【low】`WebSocket.send_json` 每個 client 各序列化一次;uvicorn 另有一層 20 s protocol ping 疊在 app 心跳上

**位置**:`copycat/server/ws.py:262-271`

```python
async def _send() -> None:
    async for msg in stream:
        async with send_lock:
            await websocket.send_json(msg)      # ← starlette: json.dumps(data) per call

async def _beat() -> None:
    while True:
        await asyncio.sleep(secs)               # WS_HEARTBEAT_SECS = 10.0
        async with send_lock:
            await websocket.send_json(PING)
```

`WsBroadcaster.publish(msg)` 把**同一個 dict** 送進每個 client 的 queue(`ws.py:65-80`),
然後每個 client 的 `_send` 各自 `json.dumps` 一次。8 條 WS × 每條 1–2 個瀏覽器分頁
= 同一份 payload 最多重複序列化 2–3 次。

同時,uvicorn 的 websockets protocol 預設 `ws_ping_interval=20.0` / `ws_ping_timeout=20.0`,
與 app 層的 `WS_HEARTBEAT_SECS = 10.0` **並存**(前者是 WebSocket protocol frame,後者是
JSON `{"type":"ping"}`)。

**影響**:
- 序列化重複:在目前規模(1–2 個分頁)是 **µs 級**,**不值得動**。真正會痛的是
  「多裝置同時看」或「群組圖牆 50 張卡每 0.1 s 推一則」時,而那時的正解是
  **預序列化一次再用 `websocket.send_text(cached)`**(或 `send_bytes`),而不是換 JSON 庫。
- 雙層 ping:純多餘流量(每條 WS 每 20 s 一個 protocol ping frame),但 `ws_ping_timeout=20`
  有一個副作用 —— 若瀏覽器分頁被 Chrome 背景節流到 20 s 沒回 pong,**uvicorn 會主動關連線**。
  這與前端 `WS_SILENCE_TIMEOUT_MS = 30 s` 的重連策略疊在一起,可能是「分頁切回來要重連」的
  一部分原因。【推測,未實證】

**修法**:
- 序列化:先量(§O1-03)再說。**現在不要動。**
- 若要關 uvicorn protocol ping:`uvicorn.run(..., ws_ping_interval=None)`,一行。
  但這會讓「半死 TCP」只剩 app 層心跳偵測 —— app 層心跳是**單向**的(server → client),
  不驗證回程。**建議維持現狀**,除非 §O1-03 量到分頁背景化造成的重連確實來自這裡。

**風險**:改 `WS_HEARTBEAT_SECS` 會動到 CLAUDE.md §4「WS 心跳契約」(前端
`ws-reconnect.ts::WS_SILENCE_TIMEOUT_MS` 必須 > 心跳間隔)。本 finding 建議的兩個改動
(預序列化、`ws_ping_interval`)**都不碰那個常數**。

**effort**:S

---

### O1-11 【low】log 檔無輪替(79 檔 / 24 MB)+ 交易日曆只載到 2026

**證據**:

```
logs/ 檔數 79,總計 24 MB,單日最大 1.56 MB(server-20260911-0905.log)
```
`_setup_prod_log()`(`__main__.py:125`)每次啟動開一個新檔 `server-%Y%m%d-%H%M.log`,
**永不清理**。以目前速度一年約 400 MB —— 不是效能問題,是磁碟衛生。

`configs/trading_holidays.json` 的 `years` **只有 "2026"**。CLAUDE.md §1 已註記
「`years_loaded` 不含當年 = 日曆過期要更新」,而 `trading_calendar.py` 的行為是
「缺年 WARNING 每年節流一次」→ 2027-01-01 之後**整套自癒閘 / 換日邏輯會退化成
只擋週末**,而那是一則一年只印一次的 WARNING。

**修法**:log 加一支 `python -m copycat prune-logs --keep-days 30`(或 run.ps1 啟動時掃一次);
日曆在 §O1-03 的 `/api/metrics` 順手回 `calendar_years_loaded`,前端亮燈。

**風險**:零。

**effort**:S

---

### O1-12 【low】Windows Defender 即時防護開著,`.venv` / `node_modules` 掃描成本無法量化(需 admin)

**證據**:

```
Get-MpComputerStatus → RealTimeProtectionEnabled: True, AntivirusEnabled: True
Get-MpPreference     → "N/A: Must be an administrator to view exclusions"
node_modules 298 MB,.venv(pyzmq / comtypes / pywin32 / discord.py …)
```

無法確認有沒有排除清單。**間接證據顯示影響有限**:
`pytest --collect-only`(169 個檔 + 全部 import)只要 **7.6 s**;
`import copycat.server.__main__` 全冷 **0.64–0.71 s**(三次)。
若 Defender 在逐檔掃 `.pyc`,這兩個數字會更差。

**修法(要 admin)**:
```powershell
Add-MpPreference -ExclusionPath 'C:\side-project\copycat'
Add-MpPreference -ExclusionProcess 'python.exe','node.exe'
```
**做完要 A/B 量**(§9),不要假設有效。

**風險**:安全性取捨,由 user 決定。零程式改動。

**effort**:S

---

## 4. 啟動 / 關機預算逐條核對

### 4.1 關機:83 s 是上界,實際 0.2–0.3 s —— **不要動**

`shutdown_budget.py` 的推導鏈(逐行核對過):

```
WS_DRAIN_SECS       = 5      (uvicorn timeout_graceful_shutdown)
TC4_LANE_DEPTH      = 2      (corr → futures 串鏈;其餘 lane 各一條)
LIFESPAN_SLACK_SECS = 5.0
COM_JOIN_TIMEOUT_SECS = 5    (capital/client.py)
close_worst_secs()  = _REQ_TIMEOUT_MS/1000 + max(2×10, 2×DEFAULT_LOCK_TIMEOUT_SECS)
                    = 10 + max(20, 24) = 34
lifespan_close_worst_secs() = 2 × 34 + 5 + 5 = 78
run_grace_secs()            = ceil(5 + 78) = 83     ← 實測 python -c 輸出 83 ✓
```

**prod 實測**(`grep "關機收尾" logs/*.log`):

```
2026-09-10 09:05:56  關機收尾 0.30s:screen 0.00 / breadth 0.00 / signals 0.00 / corr 0.02 /
                     futures 0.01 / index 0.01 / stock 0.17 / txo 0.30 / capital 0.00
2026-09-11 09:05:06  關機收尾 0.21s:… stock 0.09 / txo 0.21 …
```

單條 session 的最大一段是 txo 的 `UNSUBQUOTE 255/255 檔 0.15s` + `LOGOUT + Disconnect 0.05s`。

**結論**:83 s 不是「盤中改完要等 83 秒」。`run.ps1:66` 的
`$Proc.WaitForExit($TimeoutSecs * 1000)` 在 process 一退就回,實際等待 = **0.2–0.3 s**。
83 s 只在 TC4 半死時才會被吃到,而那時候硬殺才是錯的(會留殭屍 session → 下一台開頭
~60 s 零推播)。**這套設計是對的,改造時不要碰它。**

> 若 §O1-02 加了自訂 executor,**必須**把 `pool.shutdown(wait=True)` 的上界加進
> `lifespan_close_worst_secs()`,否則契約漂掉。

### 4.2 啟動:12 s 中位 / 39 s 盤前

| 段 | 秒(自 09-04 log 逐行) | 可壓縮性 |
|---|---|---|
| import `copycat.server.__main__`(冷) | 0.64–0.71 | 低(fastapi 0.27 s + zmq 0.04 s + pydantic;`-X importtime` 見 §9) |
| `build_info.capture()`(2 個 git subprocess) | ~0.15【推測】 | 可延後到第一次 `/api/health`,但那會破壞「boot banner 最先印」的設計意圖 —— **不要動** |
| `create_app(...)` | 0.011(實測) | 已經很快 |
| TXO session login + SUBQUOTE 317 檔 | ~1.9 | TC4 端決定 |
| TXO backfill round 制 | **8.2**(其中 dry 3 輪 ~1.7 空轉) | O1-07 |
| stock / index / futures / corr 四條 session | ~1.5 | 可並行(現為序列,註解明寫「不可並行」—— 因為依賴鏈,但 stock ‖ index ‖ futures 三條其實無依賴)【推測,需讀 `_boot_engines` 全文確認】 |
| discord bot Gateway 握手 | ~1.5 | 可背景化 |
| **TC4 history 10 s timeout**(1303 DK + 1K fallback) | **20.0** | O1-07 |
| stkfut catalog QUERYALLINSTRUMENT | ~2.5 | |

---

## 5. 前端 dev vs preview 實測

| 指令 | 秒 | 備註 |
|---|---:|---|
| `npx tsc -p tsconfig.app.json --noEmit`(冷,不寫 tsbuildinfo) | **5.88** | `tsc -b` 有 incremental,熱的會更快 |
| `npx vite build`(輸出到 scratchpad,不動 `frontend/dist`) | **2.59**(rollup 1.34) | 231 modules |
| `npm run build` = 兩者串接 | **≈ 8.5** | |
| `npx vitest run` | **35.38** | 156 files / 3,069 tests,全綠 |
| `npx eslint src` | **5.82** | |

`vitest` 內部拆解(它自己報的,平行執行所以總和 > 牆鐘):

```
transform 28.52s  collect 84.14s  tests 227.37s  environment 85.87s  prepare 28.96s
```

**`environment 85.87s` = jsdom 實例建立**,佔內部總時間的 ~19%。
`vite.config.ts:25-28` 設 `environment: "node"` 為預設,需要 DOM 的檔各自用 docblock 切 jsdom
—— 這個設計是對的(不需要 DOM 的檔不付錢)。要再快一階的話 `happy-dom` 通常比 jsdom
快 2–3×,但**它不是 jsdom 的完全替代**,而這個 repo 有大量 SVG / container query / Radix 相關的
測試(`frontend-testing` skill 明寫「Radix Tabs jsdom 不可靠」),換掉風險高於收益。
**建議:不要換。** 35 秒的前端測試不是改造的瓶頸。

bundle 現況(`frontend/dist/assets/`):

```
index-DZK_0mps.js   386 KB (gzip 123 KB)   ← React + TanStack Query + 共用 lib
StockPage           74 KB
CandleChart         41 KB
IndexPage           26 KB
FuturesPage         14 KB
CorrPage            14 KB
index.css           39 KB (gzip 8 KB)
總計                609 KB
```
已經有 route-level code splitting。**bundle 不是問題。**

---

## 6. 不要動的地方(反向結論)

| # | 東西 | 為什麼不要動 |
|---|---|---|
| D1 | **logging 全鏈** | 全庫 0 個 `logger.xxx(f"...")`;熱路徑零 logger;實測 15.5 µs/行 + 23.8 µs console,全日 0.56 s。`PLE1205/PLE1206` ruff 規則已經機械擋住格式參數錯誤。**已經是最佳實踐,沒有改進空間。** |
| D2 | **關機預算 / lane 設計** | 實測 0.21–0.30 s。83 s 是 TC4 半死的上界,而 `run.ps1` 的 `WaitForExit` 一退就回。三方同源 + 不等式測試釘住,是這個 repo 裡設計最紮實的一塊。 |
| D3 | **`uvicorn --reload` / watchfiles** | `watchfiles` 已裝(uvicorn[standard] 帶的)但**刻意沒用**。開了 reload = 每次存檔重建五條 TC4 session → 每次付 60 s 零推播的 reap 代價。**絕對不要加。** |
| D4 | **`--verify` 模式(port 8722)** | `__main__.py:145-176`。fake TXO source + 外部 IO env 壓制 + 獨立落檔目錄(`data/market-verify/`、`stock_watchlist.json`)。這是盤中驗 HTTP 層改動**唯一不碰 ZMQ**的通道,而且隔離做得很乾淨(註解寫明為什麼不能共用 prod 落點)。**改造期要更常用它,不要改它。** |
| D5 | **`_Tee` 的降級紀律** | 開檔失敗 → console-only + 印一次警告;`__getattr__` 用 `object.__getattribute__` 防遞迴;`isatty()` 回 False 防 ANSI 進檔。每一條都是踩過的坑。 |
| D6 | **`/api/health` 的窄介面** | docstring 明寫「刻意不含引擎健康度…混進來會讓這條在引擎壞掉時也答不出版本」。metrics 要**另開** `/api/metrics`,不要塞進去。 |
| D7 | **前端 bundle / build 工具鏈** | build 8.5 s、bundle 609 KB、已有 route splitting。換 bundler / 加分析工具是純浪費。 |
| D8 | **jsdom → happy-dom** | 35 s 的前端測試不是瓶頸;Radix / SVG / container query 的相容性風險 > 收益。 |
| D9 | **`_HARVEST_DRY_LIMIT = 3` 的早停設計** | 設計正確(空頁無法區分「未備妥」與「無資料」,只能靠進展停滯收斂)。要優化的是 dry 輪的**等待策略**,不是拿掉早停。 |
| D10 | **`_REQ_TIMEOUT_MS` / `DEFAULT_LOCK_TIMEOUT_SECS`** | 它們是關機預算的**產生點**。縮它們 = 讓半死的 TC4 更早被判死 + 三方同源契約全動。**除非有實測證據說 10 s 太長,否則不要碰。** |

---

## 7. 工具選型建議與取捨

| 工具 | 用在哪 | 解決什麼 / 預期收益 | 代價 | 結論 |
|---|---|---|---|---|
| **`ctypes` + `ntdll.NtSetTimerResolution`** | `server/__main__.py::main()` | Windows asyncio timer 15.6 ms → 0.5 ms。實測 `sleep(0.001)` 15.5→2.0 ms、`sleep(0.05)` 62.5→50.6 ms | 全機器生效、耗電↑;不穩定(0.1/0.2 s 檔位沒改善);會讓一批測試的牆鐘假設變緊 | **建議導入**(3 行、零相依、量級 12 ms) |
| **`sys.setswitchinterval(0.001)`** | 同上 | GIL 交接最壞等待 5 ms → 1 ms,降低 event loop 抖動 | context switch↑(16 核可忽略);可能讓靠慢執行緒僥倖通過的測試 flaky | **建議導入**(一行),但**要先有 §O1-03 的 loop lag histogram 才證明得出效果** |
| **自刻 `copycat/server/metrics.py`(stdlib `array` + `bisect`)** | 新檔 + 3 個埋點 + `/api/metrics` | 端到端 latency / loop lag / queue depth / TC4 tick rate。**改造的前提條件** | ~120 行自維護;埋點要嚴守 O(1) 純 int | **建議導入**(第一優先) |
| **`prometheus_client`** | 同上 | 現成 histogram + exposition | 多一個相依 + 沒有 scraper(單人本機);exposition format 對前端不友善 | **不建議**(自刻勝) |
| **專屬 `ThreadPoolExecutor`(TC4 lane / file lane)** | `server/executors.py`(新)+ 91 個呼叫點分流 | 消除「TC4 忙 → 檔案 IO 陪葬」;**stdlib** | 關機預算契約要同動(§O1-02 風險欄) | **建議導入** |
| **`pytest-xdist`** | dev 相依 | `tests/server/` 204 s → **預期** 30–50 s(牆鐘等待型,16 核) | 測試隔離假設要先掃;`--dist loadfile` 降風險;dev-only 相依 | **有條件導入**(先用 `-n 4 --dist loadfile` 試跑 `tests/server/` 驗證綠) |
| **`pytest-timeout`** | dev 相依 | 單測試上限,防一個卡死拖垮整個 gate | dev-only,零 runtime 影響 | **建議導入** |
| **`py-spy`** | **已裝(0.4.2)但幾乎沒在用** | `py-spy record --pid <server> --duration 60 --format speedscope` = **盤中不停機**取真實火焰圖。這是唯一能回答「Python 到底慢在哪」的工具 | 零(已在 .venv);Windows 需要同 session 權限 | **建議導入到日常流程** —— 這是本區塊 CP 值最高的一條 |
| **`msgspec`** | `live/tc4.py:1199` `json.loads` | C 層解析、**解析期間釋放 GIL**、比 stdlib json 快 3–6×。直接減輕 §O1-05 的 GIL 壓力 | 打破 runtime stdlib-only(`pyproject.toml` `dependencies = []`);有 Windows wheel;要決定放 `live` extras 還是核心 | **有條件導入**(屬 B 區塊決策,ops 只提供「GIL 是真問題」的證據) |
| **`orjson`** | `ws.py` 的 `send_json` | 序列化快 2–5× | 同上;但實測規模下**還不是瓶頸** | **不建議現在做**(先量) |
| **`winloop`** | uvicorn `loop=` | uvloop 的 Windows port | libuv 在 Windows 同樣走 IOCP,**不保證解決 timer 解析度**;blast radius = 五條 TC4 session + 8 條 WS + COM 執行緒全在上面 | **不建議**(除非量到明確收益) |
| **切 SelectorEventLoop** | uvicorn `loop=` | — | **實測完全沒差**(Selector 與 Proactor 的 timer 解析度一模一樣:15.53 / 62.32) | **不建議** |
| **`uvicorn --workers N`** | — | — | ZMQ / TC4 session / in-memory state 全部是 process-local,多 worker 會變成 N 份 TC4 登入 | **絕對不要** |
| **`happy-dom`** | vitest | jsdom setup 85.9 s → 可能減半 | Radix / SVG 相容性風險;35 s 不是瓶頸 | **不建議** |
| **Windows Defender 排除** | 系統設定 | 【推測】檔案 IO / import / npm 加速 | 安全性取捨;要 admin | **有條件導入**(要 A/B 量,見 §9) |

---

## 8. 硬約束(這個區塊碰到的跨檔契約)

改造時凡動到下列任一項,**兩邊必須同動**:

1. **關機預算三方同源**(CLAUDE.md §4)——
   產生點 `copycat/server/shutdown_budget.py::run_grace_secs()`(現值 83);
   讀者 = `run.ps1:89`(`python -c` 取值)、`__main__.py:193`(`timeout_graceful_shutdown=WS_DRAIN_SECS`)、
   `app.py` lifespan(`SLOW_CLOSE_WARN_SECS`)。
   **改 lane 形狀 = 改契約**,要同步改 `TC4_LANE_DEPTH`;
   `tests/server/test_shutdown_budget.py` 釘的是**不等式**(含 run.ps1 字面 parity 與 UTF-8 BOM)。
   → §O1-02 加自訂 executor **一定會踩到**。
2. **canonical port 8721**(`run.ps1:28` ↔ `frontend/vite.config.ts:9` `BACKEND` 寫死)。
   → §O1-08 改前端啟動方式**不碰**這條,但會改前端自己的 port(5173 → 4173)。
3. **WS 心跳契約**(CLAUDE.md §4)——
   `ws.py::WS_HEARTBEAT_SECS` (10 s) < 前端 `ws-reconnect.ts::WS_SILENCE_TIMEOUT_MS` (30 s)。
   → §O1-10 的兩個建議都**不碰**這條。
4. **相關係數稀疏腿 `sparse` 旗標**(CLAUDE.md §4)——
   `configs/correlation.json` 腿的 `"sparse": true`(只認字面 true)↔ `corr_config.py::DEFAULT_CONFIG`;
   `tests/test_corr_config.py::test_sparse_legs_are_sxf_and_vx_and_the_repo_file_agrees` 鎖兩邊一致。
   → §O1-09 若走 sparse 路線**一定會踩到**(連測試名字都要改)。
5. **江波圖調色盤色數 ≥ 相關係數腿數**(CLAUDE.md §4)——
   §O1-09 若**增減腿**會踩到;只改閘不改腿則無關。
6. **`run.ps1` 必須存成 UTF-8 with BOM**(`run.ps1:11-12`)——
   PowerShell 5.1 讀無 BOM 會當 CP950,中文變亂碼且可能生出假引號讓整份 parse error(已踩過)。
   `tests/server/test_shutdown_budget.py` 有 BOM 檢查。→ §O1-08 改 run.ps1 **必須守住**。
7. **Windows 限制**:
   - `ProactorEventLoop`(uvicorn 在 Windows 非 subprocess 模式的唯一選擇);
   - 無 uvloop;
   - event loop timer 解析度 = 系統 tick 15.6 ms(§O1-01);
   - `timeBeginPeriod` 在 Windows 11 **回成功但無效**,只有 `NtSetTimerResolution` 有用;
   - `run.ps1:132-134` 記:PowerShell 5.1 **沒有安全的「對別的 process 送 Ctrl+C」**
     (AttachConsole + GenerateConsoleCtrlEvent 會打到本 shell 自己的 handler),
     所以 frontend 先死的那條路只能硬殺 backend。
8. **TC4 是 Windows 桌面 app**,ZMQ 對 localhost;非 headless 友善,Linux Docker 不在規劃內
   (CLAUDE.md「部署前置」)。→ 任何「搬去 Linux 用 uvloop」的方案直接出局。

---

## 9. 量測方法(要證明這個區塊快或慢,怎麼量)

### 9.1 已執行的量測(本報告數字的來源,可原樣重跑)

```bash
# 啟動:import 成本
.venv/Scripts/python.exe -X importtime -c "import copycat.server.app" 2>&1 | sort -t'|' -k2 -rn | head -25
# → copycat.server.app 累計 495 ms;fastapi 267 ms / zmq 45 ms / pydantic 24 ms

# 啟動:冷 import 牆鐘(三次)
.venv/Scripts/python.exe -c "import time,subprocess,sys; t=time.perf_counter(); \
  subprocess.run([sys.executable,'-c','import copycat.server.__main__']); print(time.perf_counter()-t)"
# → 0.71 / 0.639 / 0.644 s

# 啟動 / 關機:從 prod log 取真實值
grep -h "boot 序列結束" logs/*.log | tail -25
grep -h "關機收尾" logs/*.log | tail -5

# 關機預算現值
.venv/Scripts/python.exe -c "from copycat.server.shutdown_budget import run_grace_secs; print(run_grace_secs())"
# → 83

# log 組成
L=logs/server-20260911-0905.log
wc -l $L                                            # 17,978
grep -c '"GET \|"POST \|"PUT \|"DELETE ' $L         # 13,964 (78%)
grep -oE '"(GET|POST|PUT) [^ ]+' $L | sed 's/?.*//' | sort | uniq -c | sort -rn | head -20
grep -v '"GET \|"POST \|WebSocket \|connection ' $L | sed -E 's/^[0-9-]+ [0-9:,]+ //; s/[0-9]+/N/g' \
  | cut -c1-80 | sort | uniq -c | sort -rn | head -12

# lazy logging 稽核(必須恆為 0)
grep -rn 'logger\.\(debug\|info\|warning\|error\|exception\)(f"' copycat/ | wc -l    # → 0
```

### 9.2 Windows timer 解析度 A/B(§O1-01 的判準)

```python
# scratchpad/timer-probe.py —— 不碰 repo
import ctypes, time, statistics, asyncio, sys
if len(sys.argv) > 1 and sys.argv[1] == "on":
    cur = ctypes.c_ulong()
    ctypes.WinDLL("ntdll").NtSetTimerResolution(5_000, True, ctypes.byref(cur))
async def main():
    for d in (0.001, 0.01, 0.05, 0.1, 0.2):
        xs = []
        for _ in range(60):
            t = time.perf_counter(); await asyncio.sleep(d); xs.append((time.perf_counter()-t)*1000)
        xs.sort()
        print(f"{d}: med {statistics.median(xs):.2f} p95 {xs[int(.95*len(xs))]:.2f}")
loop = asyncio.ProactorEventLoop(); loop.run_until_complete(main()); loop.close()
```
判準:`0.001` 的 median 從 15.5 ms 掉到 < 3 ms,`0.05` 從 62.5 掉到 < 52 ms。
**注意 bimodal**:ON 模式下 `0.05` 的 p95 仍可能是 63 ms —— 要連跑 5 次看穩定度。

### 9.3 盤中不停機 profile(最重要的一條,工具已裝)

```powershell
# 找 pid
Get-Process python | Where-Object { $_.CommandLine -like '*copycat.server*' }
# 瞬時堆疊(五條 _listen_loop 是不是都在 sock.recv() 閒置?閒置 = TC4 沒發,不是我們卡住)
.venv\Scripts\py-spy.exe dump --pid <pid>
# 60 秒火焰圖(開盤第一分鐘跑這個)
.venv\Scripts\py-spy.exe record --pid <pid> --duration 60 --format speedscope `
  -o "$env:TEMP\copycat-open-$(Get-Date -f HHmm).speedscope.json"
# 只看 GIL 持有(區分「等 IO」與「真的在算」)
.venv\Scripts\py-spy.exe top --pid <pid> --gil
```
`ops-discipline` skill 第 182 行已經記了 `py-spy dump` 的用法 —— **把 `record --gil` 加進去**。

### 9.4 端到端延遲(要先做 §O1-03)

三個必須存在的指標,缺一不可:
1. `tc4_recv_to_dispatch_us`:`live/tc4.py:1249` 的 `self._last_msg = time.monotonic()` 到
   `handle_raw` 回來。→ 量 §O1-05 的 GIL 影響。
2. `publish_to_wire_ms`:`ws.py:65` `publish()` 到該 client `send_json` 返回。→ 量 §O1-01 的 timer 稅。
3. `loop_lag_ms`:一個 100 ms 週期的背景 task,記 `實際間隔 - 0.1`。
   → **這一條是 §O1-01 + §O1-02 + §O1-05 三個問題的共同體溫計**,先做它。

盤後判準:`curl -s localhost:8721/api/metrics | python -m json.tool`,
`loop_lag_ms` 的 p99 應該 < 20 ms(現況【推測】50–100 ms,因為 15.6 ms quantum + 5 ms GIL + 到期的 to_thread)。

### 9.5 開發迴圈基準線(改造前後對照用)

```bash
# 後端
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --durations=25   # baseline 280 s
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider tests/server/    # baseline 204 s
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --collect-only   # baseline 7.6 s
.venv/Scripts/python.exe -m ruff check copycat tests                       # baseline 0.18 s
.venv/Scripts/python.exe -m pyright                                        # baseline 9.5 s
# 前端(frontend/)
npx vitest run                                 # baseline 35.4 s
npx tsc -p tsconfig.app.json --noEmit          # baseline 5.9 s
npx vite build --outDir <scratchpad>/x         # baseline 2.6 s
npx eslint src                                 # baseline 5.8 s
```

### 9.6 Defender A/B(要 admin)

```powershell
# before
Measure-Command { .venv\Scripts\python.exe -m pytest -q -p no:cacheprovider tests\live\ }
Add-MpPreference -ExclusionPath 'C:\side-project\copycat'
Add-MpPreference -ExclusionProcess 'python.exe','node.exe'
# after — 同一條再跑三次取中位
```
判準:`tests/live/`(10.7 s,大量 import + 檔案存取)改善 > 15% 才算有效。

---

## 10. 本次執行過程中的旁證與注意事項

- **pytest 全量出現 1 條紅**:`tests/server/test_stock_engine.py::TestTickBundle::
  test_close_cancels_flush_and_never_publishes_pending`,錯在 `await asyncio.sleep(0.1)` 之後
  仍收到一筆 pending tick。**這是牆鐘 flake,不是迴歸** —— 我跑全量時同機還在跑別的量測,
  而該測試的假設正是 §O1-01 的 15.6 ms quantum。單獨重跑 `tests/server/test_stock_engine.py`
  時 207 條全綠。這條 flake 本身就是「Windows timer 假設寫進測試」的證據。
- **`configs/signals.json` 不存在** → `SignalsConfig` 全走預設,`policy_exclude_groups = ("ALL IN",)`。
- **`configs/trading_holidays.json` 只有 2026 年** —— 見 §O1-11。
- 沒有啟動任何 server、沒有寫入 repo。`vite build` 輸出到 scratchpad 的 `dist-bench/`,
  `frontend/dist/` 未被覆寫;`pytest` 全程帶 `-p no:cacheprovider`;`tsc` 用 `--noEmit` 不寫
  `tsbuildinfo`。`.env` 只確認存在,未讀內容。

---

## 11. 建議的落地順序

```
第 0 步(前提,沒有它後面全是憑感覺)
  └─ O1-03 metrics.py + /api/metrics + loop_lag_ms 探針        [M]
     └─ 同時把 py-spy record --gil 寫進 ops-discipline skill    [S]

第 1 步(低風險、零契約、量級最大)
  ├─ O1-01 NtSetTimerResolution(3 行)                          [S] → 量 loop_lag_ms 對照
  └─ O1-05 sys.setswitchinterval(0.001)(1 行)                  [S] → 同上

第 2 步(開發迴圈,直接決定後面所有改造的速度)
  ├─ O1-06 pytest-xdist -n 4 --dist loadfile 試跑 tests/server/ [S]
  └─ O1-11 log 輪替                                             [S]

第 3 步(架構,會動契約,要走完整 /refactor 或 /mod 流程)
  ├─ O1-02 TC4 lane / file lane 切 executor
  │        + shutdown_budget 加 POOL_DRAIN_SECS(契約同動)      [M]
  └─ O1-07 CDP basis sweep 併行 + 回補 dry 輪退避               [M]

第 4 步(要先問 user)
  ├─ O1-08 run.ps1 預設改 build + preview(行為改動 + 換 port)  [S]
  ├─ O1-04 access_log=False + 慢請求 middleware                 [S]
  ├─ O1-09 海外腿 sparse / 時段閘(動 corr 契約)               [S/M]
  └─ O1-12 Defender 排除(要 admin)                             [S]
```
