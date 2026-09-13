# B03 — WebSocket 廣播與背壓(copycat 架構效能掃描)

> 掃描日期:2026-09-13 · 範圍:`copycat/server/ws.py`(312 LOC)、`copycat/server/audit.py`(39 LOC)、
> `copycat/server/shutdown_budget.py`(59 LOC),以及它們的**全部生產者與消費者**
> (`stock_engine` / `index_engine` / `futures_engine` / `corr_engine` / `breadth_engine` /
> `engine.py` / `capital_api` / `app.py` 八條 WS route、前端 `lib/ws-reconnect.ts` 與 `hooks/useStockStream.ts`)。
>
> **本報告的一句話結論**:`WsBroadcaster` + `relay` 這層的**機制**是全庫設計最乾淨的一塊,
> 實測框架成本 **1.1 µs/則/client**,整層在開盤尖峰只吃 **~3 ms/s(0.3% 單核)**,
> **不是瓶頸、絕大部分不要動**。真正會讓畫面頓的是兩件**在它旁邊**的事:
> (a) 同一條 event loop 上一支 FastAPI `-> dict` 回應要 **45.9 ms**(實測),
> (b) 本層的丟包政策正好會**觸發**那支 46 ms 的請求,形成放大迴圈。
> 其次是三條「該合併而沒合併」的高頻訊息路徑(`book` / `watchlist_quote` / `stkfut`),
> 它們吃掉的不是 CPU,是 **per-client queue 的秒數餘裕**(文件宣稱 100 s,實際約 5 s)。

---

## 1. 架構地圖

### 1.1 拓撲:一個 loop、八條 WS、六顆 broadcaster

```
                    TC4 (ZMQ, 另一條 thread)            群益 COM (另一條 thread)
                              │                                   │
                    call_soon_threadsafe                 call_soon_threadsafe
                              ▼                                   ▼
   ┌──────────────────────── 單一 asyncio event loop(uvicorn,Windows Proactor)───────────────────────┐
   │                                                                                                  │
   │  StockEngine._handle_quote ──┐                                                                   │
   │  SignalHub._emit ────────────┼─► stock_ws  : WsBroadcaster(maxsize=1000) ─► /ws/stock            │
   │                              │                                                                    │
   │  IndexEngine._broadcast_loop ──► index._ws : WsBroadcaster(maxsize=32)  ─► /ws/index             │
   │  BreadthEngine._poll_loop ─────► breadth._ws: WsBroadcaster(maxsize=32) ─► /ws/breadth           │
   │  FuturesEngine._flush ─────────► futures_ws: WsBroadcaster(maxsize=500) ─► /ws/futures           │
   │  CorrelationEngine.tick_once ──► corr_ws   : WsBroadcaster(maxsize=500) ─► /ws/corr              │
   │                            └───► river_ws  : WsBroadcaster(maxsize=500) ─► /ws/river             │
   │  CapitalClient._emit ──────────► capital_ws: WsBroadcaster(maxsize=500) ─► /ws/capital           │
   │  EngineRuntime.snapshots  ─────► (無 broadcaster,per-client generator)  ─► /ws/txo-pnl           │
   │                                                                                                  │
   │  + 所有 REST route(含 46 ms 的 /api/stock/state/{code})跑在同一條 loop 上                        │
   └──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- 六路走 `WsBroadcaster`(`app.py:549-557`),**一條 `/ws/txo-pnl` 是例外**:它用
  `EngineRuntime.snapshots()` 的 per-client async generator(`engine.py:147-175`),
  每個 client 各自 `latest_snapshot()` + 深拷貝 + 深比較 —— 拓撲不一致(見 F-07)。
- 一個瀏覽器分頁 = **8 條 WS 連線**(前端 8 支 hook 各自 `connectWithRetry`,
  `useBreadth` / `useCapital` / `useCorrelation` / `useFuturesStream` / `useIndexStream` /
  `useRiver` / `useStockStream` / `useTxoSnapshot`),每條 relay 起 **3 個 task**
  (`_send` / `_recv` / `_beat`)→ 一個分頁在後端是 **24 個 asyncio task**。

### 1.2 `WsBroadcaster` 的資料結構與政策(`ws.py:45-142`)

| 面向 | 現況 | 評價 |
|---|---|---|
| 容器 | `self._clients: set[asyncio.Queue[dict]]`(`ws.py:55`) | 正確。fanout O(clients),無鎖 |
| maxsize | stock 1000(`stock_engine.py:55`)、index/breadth 32、其餘 500(`ws.py:29`) | 分層合理 |
| 丟包政策 | 滿了 `get_nowait()` 丟最舊 → 再 `put_nowait()`(`ws.py:70-80`) | 對 quote 型正確,**對 `ticks` 型是最壞選擇**(F-08) |
| 可觀測 | `dropped` 累計 + `window_dropped` 節流窗結算 WARNING「ws 佇列滿」(`ws.py:82-119`) | 設計很好;但 `/api/health` 刻意不含,只能 grep log |
| fanout 是否 await | **完全同步**,`publish()` 內無任何 `await`(`ws.py:65-80`) | ✅ 一個慢 client **絕對拖不到**其他 client。這是本層最重要的正確性,不要動 |
| 種子 | `stream(seed=…)` 同步逐則入**該** client 的 queue,不借 `publish`(`ws.py:121-133`) | ✅ 正確且有註解說明理由 |
| 共用物件 | 同一個 `dict` 物件被 `put_nowait` 進所有 client queue | 目前安全(payload 都是新建),但無機械保證(F-10) |

### 1.3 `relay` 的送出路徑(`ws.py:219-312`)

```
queue.get()  ──►  async with send_lock  ──►  websocket.send_json(msg)
                                                  │
                                      starlette/websockets.py:174
                                      json.dumps(data, separators=(",",":"), ensure_ascii=False)
                                                  │
                                      ASGI {"type":"websocket.send","text":…}
                                                  │
                                      uvicorn websockets_sansio_impl
                                                  │
                                      ServerPerMessageDeflateFactory(window=12, memLevel=5)  ← 預設開啟
                                                  │
                                      transport.write()（TCP_NODELAY 已由 asyncio 設好）
```

三個關鍵事實:

1. **每則廣播 × 每個 client = 一次 `json.dumps`**。`WsBroadcaster.publish` 傳的是 dict,
   序列化發生在 `relay._send` 的 `send_json`,也就是 **per-client**。1 個分頁時零浪費;
   4 個分頁時同一則 `ticks` 打包被 dumps 四次(實測 47 µs → 188 µs)。
2. **送的是 text frame,不是 bytes**(`starlette/websockets.py:175-176`,`mode="text"`)。
3. **permessage-deflate 預設開著**。`uvicorn/config.py:205` `ws_per_message_deflate: bool = True`,
   而 `copycat/server/__main__.py:193` 的 `uvicorn.run(...)` **沒有傳這個參數** →
   每一則 frame 對每一個 client 各做一次 zlib deflate + `Z_SYNC_FLUSH`。
   實測這是本層最大的一筆 CPU(見 §3)。

`send_lock` 的用法是對的:`ws.py:250-252` 的 docstring 明寫「只序列化單次 `await send_json`,
**不得**包住 `async for` 或 `queue.get()`」—— 這正是心跳在零流量時還出得去的前提。

### 1.4 心跳(`WS_HEARTBEAT_SECS = 10.0`,`ws.py:34`)

- 後端:每連線一個 `_beat` task,`asyncio.sleep(10)` → `send_json(PING)`,**定時不補空窗**
  (有流量時照送)。
- 前端:`lib/ws-reconnect.ts:41` `WS_SILENCE_TIMEOUT_MS = 30_000`,`onopen` 即武裝,
  `WS_WATCHDOG_TICK_MS = 5_000` 單一 `setInterval` 巡檢(`onmessage` 只寫時間戳 —— 這一點
  對個股 tick 洪流很關鍵,零 timer churn)。
- **與協定層 ping 並存**:uvicorn `ws_ping_interval` 預設 20 s(`uvicorn/config.py:203`),
  但那一層的 pong 由瀏覽器自動回、JS 看不到 —— 所以應用層心跳**不能**拿掉。
- 成本:實測 `dumps({"type":"ping"})` = 1.7 µs;8 條 WS / 10 s = **1.33 µs/s**。可忽略。

### 1.5 `audit.py`(39 LOC)

`append_audit`(`audit.py:28-38`)= module-level `threading.Lock` + `json.dumps` + `open("a")` + `write` + `flush`。
**同步阻塞 IO**,但熱路徑已全部包在 `asyncio.to_thread`:

- `capital/client.py:347` `_audit_blocked` → `await asyncio.to_thread(...)`
- `capital/client.py:353` `_audit_after` → `await asyncio.to_thread(...)`
- 唯一在 loop 上同步寫的是 `_on_late_result`(`client.py:357-362`),docstring 已明寫
  「done_callback 在 loop 上跑,同步 append_audit 可接受(罕見路徑)」。

→ **與 WS 廣播無衝突,不是瓶頸**(詳見 §6「不要動」)。

### 1.6 `shutdown_budget.py`(59 LOC)

與效能無關,但是**改 WS 拓撲時的硬約束**:`WS_DRAIN_SECS = 5`(uvicorn `timeout_graceful_shutdown`)
+ `TC4_LANE_DEPTH = 2` → `run_grace_secs()` = 83 s,三個讀者同源(run.ps1 / `__main__.py` / lifespan)。
CLAUDE.md §4「關機預算三方同源」已明文:**改 lane 形狀 = 改契約**。
任何把 fanout 搬出主 loop(獨立 thread / process)的方案都會動到這裡。

---

## 2. 資料流:一則成交從 TC4 到畫面

```
TC4 ZMQ SUB thread
  └─ live/tc4.py 收 frame、parse
      └─ loop.call_soon_threadsafe(StockEngine._handle_quote, quote)     ← 每 tick 一次
          └─ [event loop] _handle_quote (stock_engine.py:1187-1366)
               ├─ parse_stock_realtime
               ├─ state.ingest(tick)
               ├─ 收件人 = _main ∪ _tick_targets → _pending_ticks.append({…10 鍵…})
               │     └─ 首筆排 loop.call_later(0.1, _flush_ticks)
               │           └─ _flush_ticks → publish({"type":"ticks","items":[…]})   ← ≤10 則/s
               ├─ code in _watchlist → _dirty_watchlist.add(code)
               │     └─ _flush_watchlist_loop 每 1 s → 逐檔 publish(watchlist_quote) ← 最多 150 則/s ⚠
               ├─ code == _main → publish({"type":"book",…})            ← 每則 quote 一發,零合併 ⚠
               └─ signal_hub.on_tick → 命中才 publish(signal)
          └─ WsBroadcaster.publish → 逐 client put_nowait(同一個 dict)
              └─ relay._send:queue.get → send_lock → send_json
                   → json.dumps(per client) → deflate(per client) → TCP
                       └─ 瀏覽器 ws-reconnect.ts:201 onmessage
                            → lastMsgAt = now(餵 watchdog)
                            → JSON.parse
                            → isPing? 丟掉 : handlers.onMessage
                                 └─ useStockStream case "ticks"
                                      → 逐 item 檢查 seq === acc.seq + 1
                                      → 跳號 → void refetch()  ← ⚠ 打 /api/stock/state/{code},45.9 ms
```

**背壓只有一種形式**:client queue 滿 → 丟最舊。沒有任何上游反壓(不會叫 engine 少發、
不會叫 TC4 少推),也不需要 —— 但丟包的**復原手段**(seq gap → 全量 refetch)成本極高,
這是本層最重要的架構耦合(F-08)。

---

## 3. 熱路徑逐條(含實測)

實測環境:本機 Windows 11 / Python 3.13 / 本 venv;腳本見
`scratchpad/arch-scan/bench_ws.py` `bench_ws2.py` `bench_ws3.py` `bench_ws4.py`。

### 3.1 單則訊息的成本拆解(實測)

| payload | bytes | `json.dumps` | deflate(隨機資料) | deflate 後 bytes |
|---|---:|---:|---:|---:|
| `ticks` 打包 ×40 | 4,986 | **46.9 µs** | **117.1 µs** | ~1,469 |
| `ticks` 打包 ×8 | 1,018 | 11.1 µs | ~7 µs | — |
| `book`(五檔) | 182 | 4.0 µs | ~2 µs | — |
| `watchlist_quote` | 172 | 3.1 µs | ~2 µs | — |
| `index` payload | 228 | 3.3 µs | ~2 µs | — |
| `ping` | 15 | 1.7 µs | ~1.4 µs | — |
| 主圖 snapshot(6.2k ticks,REST) | 477,482 | **3,839 µs** | **4,000 µs** | ~30,844 |

框架本身(`publish` → queue → `relay` → `send_lock` → `send_json`,含 dumps,fake transport):

| 情境 | 每則/每 client |
|---|---:|
| `book` 小訊息,1 client | **5.12 µs**(其中 dumps 4.0 µs → **框架 ≈ 1.1 µs**) |
| `book` 小訊息,2 clients | 9.50 µs |
| `book` 小訊息,4 clients | 23.08 µs |
| `ticks` ×40,1 client | 47.81 µs(幾乎全是 dumps) |

**結論:`WsBroadcaster` + `relay` 的機制成本 ≈ 1 µs/則。完全不是瓶頸。**

### 3.2 熱路徑清單(按「每秒被執行幾次」排序)

| # | 路徑 | 位置 | 頻率 | 每次做什麼 |
|---|---|---|---|---|
| H1 | `relay._send` 迴圈 | `ws.py:262-265` | = 全部廣播則數(尖峰估 **200+/s**) | `queue.get` + lock + dumps + deflate + write |
| H2 | `WsBroadcaster.publish` | `ws.py:65-80` | 同上 | `_settle_drop_window`(兩個比較)+ 逐 client `put_nowait` |
| H3 | `book` 廣播 | `stock_engine.py:1359-1360` | **每則主圖 quote**(活躍股估 10–100/s) | 組 dict(含 `book.bids`/`asks` 兩個 list)+ 一則 frame。**零合併、零去重** |
| H4 | `watchlist_quote` 廣播 | `stock_engine.py:1827-1832` | 1 Hz **爆發**,自選滿載 = **最多 150 則/秒脈衝** | 逐檔 `_quote_payload()`(10 鍵 dict + 一次除法 round)+ 一則 frame |
| H5 | `ticks` 打包 | `stock_engine.py:1782-1797` | **≤10 則/s**(0.1 s 窗) | list 交換 + 一則 frame(尖峰 ~40 items / 5 KB) |
| H6 | `_pending_ticks.append` | `stock_engine.py:1320-1339` | **每 tick**(開盤 50 檔估 300–500/s) | 組 10 鍵 dict + 可能排一支 `call_later` |
| H7 | `stkfut` 廣播 | `stock_engine.py:1473` | 每則 HOT quote(單一合約,估 1–20/s) | 組 5 鍵 dict + 一則 frame。**零合併** |
| H8 | 期貨 `_flush` | `futures_engine.py:655-694` | ≤10 則/s(0.1 s coalesce) | ✅ 已合併 |
| H9 | corr `tick_once` + river delta | `corr_engine.py:300-345` | 各 1/s | 11 腿取樣 + `state()` 全量 + river delta |
| H10 | index `_broadcast_loop` | `index_engine.py:669-746` | 1/s,且 `_dirty` 才發 | ✅ scalar payload 228 B,已是最佳形狀 |
| H11 | `_beat` 心跳 | `ws.py:267-271` | 0.1/s × 8 條 × 分頁數 | dumps 15 B |
| H12 | TXO `snapshots` generator | `engine.py:160-175` | ≤1/s × **每個 client** | `latest_snapshot()` 全量重建 + `_content()` 淺拷貝 + dict 深比較 |
| H13 | seq-gap `refetch` | `app.py:1668-1671` | 事件驅動(丟包 / 重連 / rollover / 切檔) | **`jsonable_encoder` + `json.dumps` 477 KB = 45.9 ms 同步卡 loop** |

### 3.3 圖牆 50 張卡、每秒送多少 bytes(回答 brief 問題 6)

以開盤尖峰 ~400 tick/s、自選 150 檔全活躍估:

| 訊息型別 | 則數/s | bytes/s(raw) | bytes/s(deflate 後) | dumps CPU/s |
|---|---:|---:|---:|---:|
| `ticks` 打包 | 10 | ~50 KB | ~15 KB | 469 µs |
| `watchlist_quote` | ≤150 | ~26 KB | ~8 KB | 465 µs |
| `book`(主圖,30/s 估) | 30 | ~5.5 KB | ~2 KB | 120 µs |
| `stkfut` | ~10 | ~1 KB | — | 30 µs |
| `ping` ×8 | 0.8 | 12 B | — | 1 µs |
| **合計(1 client)** | **~200** | **~83 KB/s** | **~25 KB/s** | **~1.1 ms/s** |
| + deflate CPU | | | | **~1.9 ms/s** |

**整層尖峰 ≈ 3 ms CPU/s = 單核 0.3%。**
對照:**一支 seq-gap refetch = 45.9 ms**,等於整層 **15 秒**的 CPU 塞在一個同步區間裡。

---

## 4. Findings

> 嚴重度判準:對「下實單的看盤系統」而言,**畫面延遲的尖峰值**比平均 CPU 重要得多。
> 一個 46 ms 的同步卡頓 > 一個 3 ms/s 的持續開銷。

---

### F-01 【critical · 跨區(B02 的 code,B03 的下游)】seq-gap refetch 在 event loop 上卡 45.9 ms,而觸發它的正是本層的丟包政策

**位置**:`copycat/server/app.py:1668-1671`

```python
@app.get("/api/stock/state/{code}")
async def stock_state(
    request: Request, code: str, contract: str | None = None, tape: str = "1"
) -> dict:
```

回傳型別是裸 `dict` → FastAPI 走 `serialize_response` → `jsonable_encoder(content)` → `JSONResponse` → `json.dumps`。
`StockDayState.snapshot()`(`copycat/live/stock_state.py:266-310`)的 `ticks` 是一個
**上限 20,000 筆的 deque**(`_TICKS_MAXLEN = 20_000`,`stock_state.py:19`,註解寫「熱門股單日 6.2k 實測」),
每筆再組一個 6 鍵 dict。

**實測**(`bench_ws3.py`,6,200 筆 tick 的 snapshot,477 KB):

```
jsonable_encoder                39.93 ms
json.dumps(直接)                 4.36 ms   (476,911 bytes)
jsonable_encoder + JSONResponse 45.87 ms   ← FastAPI `-> dict` 路徑的實際成本
```

**影響**:這 45.9 ms **完全落在 event loop 上**,期間:

- 8 條 WS 的 `_send` 全停(所有行情凍結 46 ms);
- `call_soon_threadsafe` 進來的 TC4 quote 全部排隊;
- `_flush_ticks` 的 `call_later(0.1)` 到期也跑不了 → 打包窗被拉長成 0.146 s;
- 心跳 `_beat` 也延後。

而 40 ms(87%)是 **`jsonable_encoder` 的純浪費** —— payload 本來就全是 JSON 原生型別
(int / str / bool / None / list / dict),`jsonable_encoder` 是在對 6,200 個 dict 做遞迴
`isinstance` 分派後原樣吐回。

熱門股一天若跑到 15,000 筆,這個數字會變成 **~110 ms**。

**修法**:改用 `orjson`(或 `msgspec.json`)+ 自訂 `Response` class,**繞過 `jsonable_encoder`**:

```python
# copycat/server/json_response.py(新檔)
import orjson
from starlette.responses import Response

class FastJSONResponse(Response):
    media_type = "application/json"
    def render(self, content) -> bytes:
        return orjson.dumps(content)

# app.py create_app(...)
app = FastAPI(..., default_response_class=FastJSONResponse)
```

預期:45.9 ms → **~1 ms**(orjson 對 477 KB 約 0.8–1.5 ms,且不經 `jsonable_encoder`)。**~40×**。

**風險**:
- `orjson.dumps` 不吃非 JSON 原生型別(`date` / `Decimal` / dataclass / 非 str dict key)——
  `jsonable_encoder` 目前會自動轉。**必須先盤點所有 route 的回傳型別**;
  `vp` 已是 `{str(price): …}`(`stock_state.py:257`)、`minutes` 已是 str key,主要路徑安全。
  不安全的會變成 **500 而不是靜默錯**,方向是對的但要一次抓齊。
- `orjson` 對 `NaN` / `Infinity` 會 raise,stdlib `json` 會吐**非法 JSON** `NaN` →
  現在若有這種值,前端的 `JSON.parse` 本來就會炸;換 orjson 只是把炸點提前到後端。
- **不動任何 CLAUDE.md §4 契約**:JSON 的鍵、值、型別逐字不變。
- 與專案「stdlib-only runtime」哲學衝突 —— 但 `dependencies = []` 的前提是「不裝也能跑」,
  而 fastapi/uvicorn 已經在 `[live]` extras 裡;`orjson` 放進同一個 extras 是一致的。

**Effort**:S(新增一個 Response class + 一次 route 回傳型別盤點)

---

### F-02 【high】`book` 每則 quote 一發,零合併、零去重 —— 是 `/ws/stock` 上訊息**則數**最大的生產者

**位置**:`copycat/server/stock_engine.py:1359-1360`

```python
        if code == self._main:
            self._publish({"type": "book", "code": code, "bids": book.bids, "asks": book.asks})
```

**證據與量級**:
- 這一行在 `_handle_quote` 尾端,**無任何條件**(除了 `code == self._main`)。
  TC4 的 REALTIME 對主圖那一檔**每次簿變動也推**(`TradeQuantity=0` 的純簿更新,
  `stock_engine.py:1216-1218` 的註解明講有這種 quote)—— 所以它的頻率是
  **主圖 quote 全率**,不是成交率。
- **連「簿內容有沒有變」都沒比**:同一組五檔可以連送十則。
- 對照組:同一個檔案裡的 `ticks` 已經打包成 0.1 s 一則(`_flush_ticks`,`stock_engine.py:1782-1797`),
  `futures_engine._flush`(`futures_engine.py:655-694`)也 coalesce 了。
  **`book` 是三條裡唯一沒合併的**。

**影響**:CPU 微不足道(4 µs dumps + 2 µs deflate),真正的代價是**則數**:
每一則吃掉 1/1000 的 per-client queue 額度,而復原成本是 F-01 的 46 ms。
在 client 卡住(分頁被 Chrome 節流、主執行緒長阻塞)時,`book` 是把 queue 燒光最快的那條。

**修法**(兩段,可分開做):
1. **去重**:比 `(bids, asks)` 指紋,沒變不發。這一條零語意改變、零契約衝擊,先做。
   (`corr_engine.py:308-313` 已經有現成的 fingerprint 寫法可抄。)
2. **併進 0.1 s 窗**:把最新的 book 存 `self._pending_book[code]`,在 `_flush_ticks` 同一個
   `call_later` 到期時連同 `ticks` 一起送(仍是獨立的 `{"type":"book",…}` 則,形狀不變)。

**契約衝擊**:
- 訊息**形狀**逐字不變 → 前端 `useStockStream` 的 `case "book"` 零改動。
- **行為改變:閃電梯 / 五檔更新頻率從 tick 率降到 10 Hz**。這需要 **user 拍板** ——
  但有現成先例:CLAUDE.md §4 的 ticks 打包契約已記「主圖最多晚 0.1 s(user 拍板接受)」。
- 注意 `group_snapshot` / `snapshot` 的 `_flush_ticks()` 前置呼叫(CLAUDE.md §4「快照與打包的
  seq 對齊」)—— 若 book 併進同一個 flush,那兩個快照路徑也會順帶 flush book,**這是好事**
  (快照的 book 與已送出的 book 對齊),但要在測試裡釘住。

**Effort**:S(去重)/ M(併窗 + 測試 + 拍板)

---

### F-03 【high】`watchlist_quote` 逐檔一則、1 Hz 脈衝 —— 自選滿載時 150 則/秒,而 §4 的「queue 1000 撐 100 s」是只算 ticks 的算術

**位置**:`copycat/server/stock_engine.py:1813-1832`

```python
    async def _flush_watchlist_loop(self) -> None:
        while True:
            await asyncio.sleep(self._throttle)          # 1.0 s
            ...
            dirty, self._dirty_watchlist = self._dirty_watchlist, set()
            for code in dirty:
                ...
                self._publish(self._quote_payload(code))   # ← 一檔一則
```

加上同一個迴圈裡的試撮翻轉補推(`stock_engine.py:1822-1826`,`_trial_flip_targets()` 最多 151 檔)
與連線種子(`stock_engine.py:1757`,`stream()` 一口氣 seed 150 則)。

**量級**:自選上限 2026-09-01 起 = **150**(CLAUDE.md §4「自選上限常數多邊同值」)。
活躍時段 `_dirty_watchlist` 可以塞滿 150 檔 → **每秒一發 150 則的脈衝**,
是 `ticks` 打包(10 則/s)的 **15 倍則數**。

**與文件的落差**:CLAUDE.md §4 ticks 契約寫「per-client queue 1000 撐 100 s」——
那個算術是 `1000 / 10 則/s`,**只算了 ticks**。把 `watchlist_quote`(≤150/s)、
`book`(F-02,估 10–100/s)、`stkfut`(F-06)算進去,實際總則數 ~200/s →
**queue 的真實餘裕約 5 秒,不是 100 秒**。這不是 bug,是一個**沒有錯誤訊號的認知落差**:
`dropped` 跳起來的門檻比文件說的低 20 倍。

**修法**:
1. 最小改動:文件校正(把 §4 的 100 s 改成把三條路都算進去的數字),**先做,零風險**。
2. 打包:新增 `{"type":"quotes","items":[…]}`(item 逐字沿用現有 `watchlist_quote` 的 10 個鍵,
   去掉 `type`),與 #180 對 ticks 做的手法完全同形。150 則 → 1 則,
   bytes 也降(150 個 `"type":"watchlist_quote"` 前綴消失,約省 25%)。

**契約衝擊**(打包方案):
- **新增訊息型別 = 前後端必須同版部署**。CLAUDE.md §4 已有明文紀律
  (「改規則種類的部署一律前後端同版,畫面『版本落差』膠囊亮起先 `npm run build`」)。
- 前端讀者:`useStockStream`(側欄 quote)+ `useGroupLiveAccums`?—— 需確認
  `watchlist_quote` 目前的所有消費點,舊 `case "watchlist_quote"` 要保留一段過渡期
  (後端同時發舊型別 = 退化;建議直接切、靠部署紀律)。

**Effort**:S(文件校正)/ M(打包)

---

### F-04 【medium】permessage-deflate 預設開著 —— loopback 上是純 CPU 浪費,且佔本層 70% 的 CPU

**位置**:`copycat/server/__main__.py:193`

```python
    uvicorn.run(app, host="127.0.0.1", port=port, timeout_graceful_shutdown=WS_DRAIN_SECS)
```

沒有傳 `ws_per_message_deflate` → 吃 `uvicorn/config.py:205` 的預設 `True` →
`uvicorn/protocols/websockets/websockets_sansio_impl.py:80-88`:

```python
        extensions = []
        if self.config.ws_per_message_deflate:
            extensions = [
                ServerPerMessageDeflateFactory(
                    server_max_window_bits=12,
                    client_max_window_bits=12,
                    compress_settings={"memLevel": 5},
                )
            ]
```

**實測**:`ticks` 打包 ×40(隨機資料,context takeover 生效)= **117.1 µs deflate vs 46.9 µs dumps**。
deflate 是 dumps 的 **2.5 倍**,佔本層總 CPU 約 70%(1.9 ms/s 裡的 1.2 ms/s)。
壓縮率 0.30(4,909 B → 1,469 B)。

**這裡是 `host="127.0.0.1"`** —— 後端與前端跑同一台(CLAUDE.md §1 明載)。
loopback 頻寬實質無限,3.3× 的 bytes(83 KB/s → 25 KB/s 的反向)毫無代價;
換來的是**兩邊**都省:server 省 deflate、瀏覽器主執行緒省 inflate。

**修法**:一行。

```python
    uvicorn.run(app, host="127.0.0.1", port=port,
                timeout_graceful_shutdown=WS_DRAIN_SECS,
                ws_per_message_deflate=False)
```

**契約衝擊**:**無**。deflate 是 WS 握手協商的 transport 層擴充,前端 `WebSocket` API 完全無感,
`ws-reconnect.ts` 的 `JSON.parse(ev.data)` 拿到的東西逐字相同。

**反向風險**:未來若真的要跨網段看盤(CLAUDE.md §5 的 open question「跨網段 ZMQ」),
關掉 deflate 會讓頻寬 3.3×。建議寫成 env 開關或在註解裡記明「只對 localhost 成立」。

**Effort**:S(一行 + 一行註解 + 一條 `test_main` 的參數斷言)

---

### F-05 【medium】每則廣播對每個 client 各 `json.dumps` 一次 —— 現況零浪費,多分頁時線性放大

**位置**:`copycat/server/ws.py:262-271` → `starlette/websockets.py:174`

```python
    async def _send() -> None:
        async for msg in stream:
            async with send_lock:
                await websocket.send_json(msg)      # ← dict 進來,在這裡才序列化
```

```python
# starlette/websockets.py:171-176
    async def send_json(self, data: Any, mode: str = "text") -> None:
        ...
        text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
```

**實測**(`bench_ws4.py`,同一則 `book` 廣播):

```
clients=1   5.12 us/則/client
clients=2   9.50 us/則/client   ← 總成本 2×
clients=4  23.08 us/則/client   ← 總成本 4×(還有 scheduler 的超線性)
```

**誠實評估**:看盤時 user 通常只開**一個分頁**(CLAUDE.md §1 明寫日常用 `npm run preview` 的 4173)。
N=1 時這條 finding 的收益是 **0**。它只有在下列情況才回本:
多分頁(preview + dev 同時開)、多螢幕、或未來多台終端看同一顆後端。

**修法**:`WsBroadcaster.publish` 時序列化一次:

```python
# ws.py
def publish(self, msg: dict) -> None:
    text = json.dumps(msg, separators=(",", ":"), ensure_ascii=False)
    ...  # 把 text(或 (msg, text))放進 queue
```
`relay._send` 改走 raw ASGI send:
```python
await websocket.send({"type": "websocket.send", "text": text})
```

**契約衝擊**:
- **wire 完全不變**(同一份 JSON 文字)。
- `WsConnection` Protocol(`ws.py:145-154`)要多一個 `send` 方法 → **21 處測試用到 `send_json`**
  (`tests/server/test_app.py` / `test_stock_routes.py` / `test_ws_disconnect.py`)要改 fake。
- `send_seed`(`ws.py:186-202`)與 route 自送的首則(txo / corr / river)走的是 `websocket.send_json`,
  要一併決定是否同源。
- `PING` 可以在 module level 預先序列化成常數字串(順手省掉每次 1.7 µs)。

**建議**:**先不做**。等 F-01 / F-02 / F-03 / F-04 做完再量一次,若那時多分頁仍是常態再說。
記進「下次處理」清單。

**Effort**:M(改動小但測試面 21 處)

---

### F-06 【medium】`stkfut` 同樣每則 HOT quote 一發、零合併

**位置**:`copycat/server/stock_engine.py:1459-1473`

```python
    def _handle_stkfut(self, quote: dict) -> None:
        ...
        self._publish({"type": "stkfut", "code": code, "prod": prod, "p": price, "basis": basis})
```

F-02 的小號版本:同一個 `_handle_quote` 分派進來、每則 HOT quote 一則 WS frame、無去重無合併。
訂閱中的個股期合約通常只有主圖那一檔 → 頻率估 1–20/s,比 `book` 低一個量級。

**修法**:同 F-02 —— 併進 0.1 s flush 窗,或至少「價沒變不發」。

**契約衝擊**:形狀不變,只變頻率;前端個股期基差顯示更新降到 10 Hz。

**Effort**:S

---

### F-07 【medium】`/ws/txo-pnl` 的 per-client 全量重建 + 深比較,與其他六路拓撲不一致

**位置**:`copycat/server/engine.py:147-175` + `engine.py:49-60`

```python
        while True:
            if self._version == last:
                await self._changed.wait()
                continue
            last = self._version
            snap = self.latest_snapshot()      # ← 每個 client 各建一次全量
            body = _content(snap)              # ← 每個 client 各做一次淺拷貝 + handover 再一層
            if body == prev:                   # ← 每個 client 各做一次 dict 深比較
                continue
            prev = body
            yield snap
            await asyncio.sleep(self._throttle)   # 1.0 s
```

```python
def _content(snap: dict) -> dict:
    body = {k: v for k, v in snap.items() if k != "generated_at"}
```

**問題**:其他六路的模式是「engine 端算一次 → `publish` 一次 → fanout」;這一路是
「每個 client 各算一次 → 各比一次」。`latest_snapshot()` 會呼叫 `self._agg.snapshot(...)`
重建整份 payload(含 `curve`),**即使內容沒變也要先建完才知道沒變**。

**量級**:≤1 Hz × client 數。TXO tab 通常只有 1 個 client → 現況約 1 次/秒的全量重建。
`curve` 的長度未實測(見 §9 open question)。**不是當前瓶頸**,但這是一個「拓撲不一致」的
技術債:未來多分頁或 curve 變長時,它是唯一會隨 client 數線性放大**計算**(不只序列化)的路。

**修法**:把「版本變 → 算一次 → 比一次 → publish」搬進 `EngineRuntime` 的一個週期 task,
下游換成 `WsBroadcaster`(與其他六路同形)。`send_seed` 的首則語意由 `stream(seed=[snap])` 承接。

**契約衝擊**:wire 不變。但 `snapshots(seed=…)` 那套「首則與串流同源」的精巧語意
(`engine.py:150-153` 的 docstring)要重新實現在 broadcaster 的 seed 上 —— 有現成寫法
(`stock_engine.stream()` 的 seed 就是同一個問題的解)。

**Effort**:M

---

### F-08 【medium · 架構】丟包 → seq gap → 全量 refetch 的放大迴圈:「丟最舊保最新」對 `ticks` 型是最壞選擇

**位置**:`ws.py:70-80`(政策)× `frontend/src/hooks/useStockStream.ts:380-381`(復原)

```python
# ws.py:70-80
            except asyncio.QueueFull:
                # 慢連線丟最舊、保最新(行情/回報都是最新有意義)
                try:
                    queue.get_nowait()
                ...
```
```ts
// useStockStream.ts:380-381
            if (item.seq !== acc.seq + 1) {
              void refetch(); // 跳號(含 rollover 型回退)→ 全量對齊
```

**問題**:政策註解的理由「行情/回報都是最新有意義」對 `watchlist_quote` / `book` / `index` /
`futures` **完全成立**(它們是自足快照,丟掉舊的正確)。但 **`ticks` 不是自足的** ——
它靠 `seq` 連續性累算,丟一則 = 前端偵測跳號 = 打一支 **45.9 ms 的全量 refetch**(F-01),
而群組檢視那半邊還會 per-code 重拉 `group-state?codes=X`
(CLAUDE.md §4 ticks 契約:「跳號那一檔重拉」)。

**放大迴圈**:queue 滿的時機 = 系統最忙的時機(開盤、client 卡住)→ 丟包 →
最忙的時候再塞一支 46 ms 的同步序列化 → loop 更塞 → 更多 client 跟不上 → 更多丟包。

**現況不是問題**:CLAUDE.md 的盤後判準「`grep 佇列滿 logs/server-*.log` 為 0」長期成立
(記憶檔 09-03 實錄「全日佇列滿 0」)。所以這是**風險**不是**事故**。但一個要下實單的系統,
「從沒發生過」與「發生時會自我惡化」是兩件事。

**修法**(擇一或並用,全部要先過 grilling):
1. **先做 F-01**:把復原成本從 46 ms 壓到 1 ms,迴圈就不放大了 —— **這是最划算的一招,
   而且它同時修掉其他事**。
2. `ticks` 專用的丟包語意:queue 滿時不丟舊 ticks,改在下一則 `ticks` 上掛 `"gap": true`,
   前端據此只補缺口(或直接接受「跳號」但不打 refetch,等下一次 60 s 重播種)。
   **契約衝擊:`ticks` 打包契約新增欄位**(additive,舊前端忽略未知鍵 → 退回現行行為)。
3. `ticks` 與 quote 分成兩顆 broadcaster / 兩條 WS,不互相競爭 queue 額度。
   **契約衝擊大**(多一條 WS = 多一個 route、多一支 hook、多一份心跳),不建議。

**Effort**:S(走 1)/ M(走 2)/ L(走 3)

---

### F-09 【low】連線瞬間 150 則獨立 frame 的種子

**位置**:`copycat/server/stock_engine.py:1757`

```python
        return self._ws.stream([self._quote_payload(code) for code in self._watchlist])
```

自選 150 檔 → 建 150 個 dict,同步入 queue(maxsize 1000,不會滿),接著 relay 逐則
dumps + deflate + frame。總成本估 **~1.5 ms**,發生在每次連線 / 重連。

而重連不罕見:`ws-reconnect.ts` 的 30 s 靜默 watchdog、後端重啟、分頁回前景。
8 條 WS 同時重連時這一條是最重的那個。

**修法**:併入 F-03 的 `quotes` 打包(seed 變成 1 則)。順手解決。

**Effort**:S(跟 F-03 一起)

---

### F-10 【low】`publish` 對所有 client 共用同一個 dict 物件 —— 目前安全但無機械保證

**位置**:`ws.py:65-80`

同一個 `msg` 物件被 `put_nowait` 進 N 個 queue。今天安全,因為所有生產者都是「新建一個 dict 再 publish」
(`_quote_payload` / `_flush_ticks` 的 items 交換 / `index._payload()` 都是新物件)。

但沒有任何東西擋住未來有人寫「快取一份 payload、就地改一個鍵、再 publish」——
那會讓已入列未送出的訊息被追溯性改掉,而且**零錯誤訊號**
(`engine.py:52-54` 的 `_content` docstring 已經在別的地方踩過同款坑並留了註解)。

**修法**:F-05 的預先序列化順便把這個風險變成不可能(入列的是不可變的 str)。
或至少在 `publish` 的 docstring 補一句「傳進來的 dict 在送出前不得再被修改」。

**Effort**:S(文件)

---

### F-11 【info · 不要動】`relay` 的 task / lock 結構已是正解

`ws.py:288-312` 三個 task + `FIRST_COMPLETED` + `finally` 同步 cancel + `_consume_ws_task` 消費例外。
docstring(`ws.py:226-257`)把每一個設計決策的**失效樣態**都寫清楚了
(send-only 迴圈察覺不到斷線、`send_lock` 不得包 `async for`、`close_sent` 後的 RuntimeError 分流)。

實測框架成本 **1.1 µs/則**。不要動。

---

### F-12 【info · 不要動】心跳實作成本可忽略

`_beat` = 每連線一個 `asyncio.sleep(10)` 迴圈。實測 8 條 WS 的心跳 dumps 總成本 **1.33 µs/s**。
「定時而非補空窗」比「補空窗」少一份 lastSent 狀態,換來的節省是 0。不要動。

**注意**:別因為看到 uvicorn 有 `ws_ping_interval=20`(協定層 ping)就想拿掉應用層心跳 ——
協定層的 pong 由瀏覽器自動回,JS 看不到,`ws-reconnect.ts` 的 `WS_SILENCE_TIMEOUT_MS` 餵不到。
CLAUDE.md §4「WS 心跳契約」已明文:拿掉 = 所有 WS 每 ~35 s 重連一次。

---

### F-13 【info · 不要動】`audit.py` 不是熱路徑

`append_audit`(`audit.py:28-38`)的 module-level `threading.Lock` + open/write/flush,
熱路徑已全走 `asyncio.to_thread`(`capital/client.py:347` / `:353`)。
現行下單頻率(人工交易,一天數十筆)下這條完全不在視野裡。
它變成瓶頸的門檻約在 **>100 單/s**(全域鎖序列化 + 每筆 open/flush,估 0.1–1 ms/筆)。
若哪天真要做高頻程式單,屆時的解是「審計改 append 到常開的 file handle + 批次 flush + 單一 writer thread」,
不是現在。

---

### F-14 【info · 硬約束】改 WS 拓撲 = 動關機預算契約

`shutdown_budget.py` 三方同源(run.ps1 / `__main__.py:34,193` / lifespan)。
本區塊任何「把 fanout 搬出主 loop」的方案(獨立 thread、獨立 process、ZMQ PUB 給前端)
都會改變 lifespan 的 lane 形狀 → 必須同步改 `TC4_LANE_DEPTH`(現值 2),
否則 `run.ps1` 會在收尾途中 `taskkill /T /F`,症狀是「下一台開頭 ~60 s 零推播,零錯誤訊號」
(CLAUDE.md §4 已記)。`tests/server/test_shutdown_budget.py` 釘的是不等式。

---

### F-15 【info · 不要查這條】TCP_NODELAY 已經設好,Nagle 不是嫌疑犯

小 frame(`ping` 15 B、`book` 182 B)在 loopback 上如果有 Nagle + delayed ACK 會有 40 ms 級的延遲,
是很自然的懷疑對象。**但不是問題**:CPython 3.13 `asyncio/proactor_events.py:613`
`base_events._set_nodelay(sock)` 對每條 accept 進來的 TCP 連線都設了 `TCP_NODELAY=1`。
(uvicorn / websockets 自己沒設,但 asyncio transport 設了。)
寫在這裡是為了讓下一個人不要重查。

---

### F-16 【low · 跨區 B01】每 tick 一次 `call_soon_threadsafe` 的 loop 喚醒成本(未量測)

`stock_engine.py:1150` / `index_engine.py:420` / `futures_engine.py:565` / `corr_engine.py:262` /
`engine.py:365` —— 五個 source 各自**每則 quote 一次** `loop.call_soon_threadsafe`。
開盤 50 檔 ~400 tick/s → 每秒數百次跨執行緒喚醒,每次在 Windows Proactor 上會寫 self-pipe。

這不是 B03 的 code,但它直接決定 loop 的抖動,而 loop 抖動 = 廣播延遲。
**未量測**,列進 §9 量測計畫。若確認顯著,解是「ZMQ thread 端累積 N ms 或 N 筆再一次 hop」——
但那會動到 `_handle_quote` 的單筆語意(rollover 快路徑、`_tick_armed` 點火),
blast radius 不小,**必須先量再談**。

---

## 5. 工具選型與取捨

| 工具 | 用在哪 | 解決什麼 / 預期收益 | 代價 | 結論 |
|---|---|---|---|---|
| **orjson** | `app.py` 的 `default_response_class`(新 `FastJSONResponse`) | F-01:477 KB 回應 45.9 ms → ~1 ms(**~40×**)。同時吃掉所有其他 REST 的序列化成本 | 一個 C extension 相依(有 Windows wheel,py3.13 OK);繞過 `jsonable_encoder` 後非原生型別改成 raise;與 `dependencies = []` 哲學衝突(放 `[live]` extras 可調和) | **建議導入** |
| **msgspec** | 同上,或更進一步把 payload 改 `msgspec.Struct` | 與 orjson 同級的 encode 速度,外加 Struct 取代 dict(省配置、型別即 schema) | 改 Struct = 大改造(所有 payload builder + 測試);純 encode 用途下相對 orjson 沒有額外優勢 | **有條件導入**(只當 encoder 時選 orjson 更省事;Struct 留到真的要做 zero-copy 再說) |
| `ws_per_message_deflate=False` | `__main__.py:193` | F-04:省本層 ~70% CPU(1.2 ms/s)+ 瀏覽器主執行緒 inflate | 零相依。bytes 3.3×(loopback 無感);跨網段時要改回來 | **建議導入** |
| **py-spy**(已裝於 venv) | 盤中對 prod server 取樣 | 唯一能在不改 code 的前提下看到「loop 上到底誰在跑」的工具 | 無(已在 `.venv`) | **建議導入(用起來)** |
| 自建 **loop-lag 探針** | `app.py` 一個 20 行的 task | 「不能塞住」目前**完全沒有可觀測性**。每 100 ms 量 `sleep(0.1)` 的實際 drift,p99 > 20 ms 就 WARNING | stdlib only、~20 LOC、每秒 10 次 sleep(成本 < 10 µs/s) | **強烈建議自建** |
| **msgpack / CBOR 二進位 WS** | `relay` + `ws-reconnect.ts` | bytes −40%、parse 略快 | 血洗:`ws-reconnect.ts:205` 的 `JSON.parse` 全鏈、8 支 hook、156 個前端測試檔、`ticks` / `view` / `ping` 三個契約的表示層。收益對 25 KB/s 的流量是**零** | **不建議** |
| **SharedArrayBuffer / Web Worker 解碼** | 前端 | 主執行緒解碼卸載 | 需要 COOP/COEP header(Vite proxy + preview 都要改)、worker 通訊層、與 React 狀態同步。而現況 JSON.parse 成本 < 0.5 ms/s | **不建議** |
| **winloop**(Windows 版 uvloop) | `uvicorn.run(loop=…)` | 理論上 socket IO 更快 | 額外 C 相依、Windows + py3.13 成熟度風險。而本層 CPU 只有 3 ms/s,socket IO 不是熱點 | **不建議(現在)**;等 loop-lag 探針說話 |
| **Redis / 獨立 pub-sub process** | fanout 搬出主 loop | 隔離慢 client | 多一個 process、多一跳序列化、動到 F-14 的關機預算契約。而慢 client 現在**已經**拖不到別人(fanout 全同步) | **不建議** |

---

## 6. 不要動的地方(明確)

1. **`WsBroadcaster.publish` 的同步 fanout**(`ws.py:65-80`)—— 沒有 `await` 在裡面是本層最重要的
   正確性保證:一個慢 client 拖不到其他 client。任何「為了效率」把它改成 async 的提案都是退步。
2. **「滿了丟最舊、保最新」對 quote 型訊息**(`watchlist_quote` / `book` / `index` / `futures` / `corr`)
   —— 這些是自足快照,丟舊的完全正確。只有 `ticks` 例外(F-08)。
3. **`relay` 的三 task + `send_lock` 結構**(`ws.py:219-312`)—— 實測 1.1 µs/則,且每個決策的
   失效樣態都有註解。動它只會把已經解過的 bug 放回來。
4. **應用層心跳 10 s**(`ws.py:34`)—— 成本 1.33 µs/s,而拿掉會讓 8 條 WS 每 35 s 全部重連。
   CLAUDE.md §4 明文契約。
5. **`call_soon_threadsafe` 的執行緒紀律** —— 全庫 5 個 source 一致,`publish` 保證在 loop 上。
   這是對的,不要為了省一跳而讓 `publish` 被 TC4 thread 直呼(那會讓 `asyncio.Queue` 的
   非執行緒安全變成真 bug)。
6. **`audit.py`**(F-13)。
7. **TCP_NODELAY / Nagle**(F-15)—— 已經設好,別查。
8. **`index_engine._payload()`**(`index_engine.py:790-801`)—— scalar + `last_minute` 增量,
   已是本庫最好的 payload 形狀(對照 `state()` 才送全量 minutes)。拿它當其他路徑的範本。
9. **`futures_engine._flush` 的 coalesce + 失敗回標 dirty**(`futures_engine.py:655-694`)——
   已經是正解,而且處理了「恆拋的 broadcast 不得原地打轉」這種真實坑。

---

## 7. 契約衝擊對照表(改任何一條都要點名)

| 提案 | 動到的 CLAUDE.md §4 契約 | 兩邊怎麼同動 |
|---|---|---|
| F-01 orjson response | **無**(JSON 逐字不變) | — |
| F-02 `book` 併窗/去重 | 不動契約文字,但**動到**「快照與打包的 seq 對齊」那條的行為面(若 book 併進 `_flush_ticks`) | 後端在 `snapshot()`/`group_snapshot()` 的既有 `_flush_ticks()` 前置點會順帶 flush book;測試加一條斷言 |
| F-03 `watchlist_quote` 打包 | **新增訊息型別** → 前後端同版部署紀律(§4 已載) | 後端 `stock_engine._flush_watchlist_loop` + `stream()` seed;前端 `useStockStream` 加 `case "quotes"`,舊 case 同批移除;`npm run build` + 重啟同時做 |
| F-04 關 deflate | **無** | — |
| F-05 預先序列化 | **無 wire 變更**;動到 `WsConnection` Protocol(`ws.py:145-154`)與 21 處測試 fake | 只在後端;`PING` 順便常數化 |
| F-06 `stkfut` 合併 | 形狀不變,只變頻率 | — |
| F-07 TXO 改 broadcaster | wire 不變;`send_seed` 首則語意要搬到 `stream(seed=)` | 只在後端 |
| F-08(2) `ticks` 加 `gap` 欄 | **ticks 打包契約 additive 加欄**(§4) | 後端 `_flush_ticks` 帶欄;前端 `useStockStream` / `useGroupLiveAccums` 讀;舊前端忽略未知鍵 = 退回現行行為(安全) |
| 任何「fanout 搬出主 loop」 | **關機預算三方同源**(§4)`TC4_LANE_DEPTH` | `shutdown_budget.py` + `run.ps1` + lifespan 同動;`tests/server/test_shutdown_budget.py` 的不等式會擋 |

另外,本區塊**不會**動到的契約(確認過,寫下來免得誤傷):
`WS 心跳契約`(除非改 `WS_HEARTBEAT_SECS` 本身)、`view 訊息契約`(`ws.py:224` 的 `on_message`
只轉文字 frame 原文,route 解 JSON —— 預先序列化只動出站方向)、
`個股 seq 兩口徑`、`ticks 打包`的 item 欄位。

---

## 8. 優先順序建議

| 順位 | 動作 | 收益 | 風險 | Effort |
|---|---|---|---|---|
| 1 | **F-01 orjson response class** | 46 ms → 1 ms 的同步卡頓(整個系統最大的單點 stall) | 需盤點 route 回傳型別 | S |
| 2 | **F-04 關 permessage-deflate** | 本層 CPU −70%,零契約風險 | 幾乎無 | S |
| 3 | **F-02(1) `book` 去重** | 則數大降,零語意改變 | 幾乎無 | S |
| 4 | **F-03(1) §4 queue 餘裕文件校正** | 修掉一個 20 倍的認知落差 | 無 | S |
| 5 | **自建 loop-lag 探針** | 「不能塞住」從無法觀測變成有數字 | 無 | S |
| 6 | F-02(2) `book` 併 0.1 s 窗 + F-06 `stkfut` | 則數再降 | 要 user 拍板頻率 | M |
| 7 | F-03(2) `watchlist_quote` 打包 | 150 則/s → 1 則/s | 新訊息型別,同版部署 | M |
| 8 | F-07 TXO 改 broadcaster | 拓撲一致 | 中 | M |
| 9 | F-05 預先序列化 | 只在多 client 才回本 | 21 處測試 | M |

---

## 9. 量測方法(可重跑)

### 9.1 離線 micro-benchmark(本次用的四支,已放在 scratchpad)

```powershell
$py = "C:\side-project\copycat\.venv\Scripts\python.exe"
$d  = "C:\Users\USER\AppData\Local\Temp\claude\C--side-project-copycat\<sid>\scratchpad\arch-scan"
& $py "$d\bench_ws.py"   # payload 尺寸 / dumps / deflate 對照表
& $py "$d\bench_ws2.py"  # deflate 用隨機資料(context takeover 下的真實成本)
& $py "$d\bench_ws3.py"  # FastAPI `-> dict` 的 jsonable_encoder 成本  ← F-01 的證據
& $py "$d\bench_ws4.py"  # relay + WsBroadcaster 框架成本(fake transport,1/2/4 clients)
```

### 9.2 盤中對 prod server 取樣(py-spy 已裝,不必改 code)

```powershell
# 找 pid
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like "*copycat.server*" } | Select ProcessId, CommandLine

# 60 s 取樣火焰圖(盤中 09:00–09:05 最有代表性)
C:\side-project\copycat\.venv\Scripts\py-spy.exe record -o ws-open.svg -d 60 --pid <PID>
# 即時 top(看 json / zlib / jsonable_encoder 各佔多少)
C:\side-project\copycat\.venv\Scripts\py-spy.exe top --pid <PID>
```

判準:`jsonable_encoder` / `zlib` / `json.encoder` 三者在火焰圖的佔比。
若 `jsonable_encoder` 可見 → F-01 成立於真環境。

### 9.3 loop-lag 探針(建議常駐;目前完全沒有)

```python
# 建議加進 app.py lifespan(stdlib only,~20 LOC)
async def _loop_lag_probe() -> None:
    worst = 0.0
    t_win = time.monotonic()
    while True:
        t0 = time.monotonic()
        await asyncio.sleep(0.1)
        lag = (time.monotonic() - t0 - 0.1) * 1000
        worst = max(worst, lag)
        if time.monotonic() - t_win >= 60:
            if worst > 20:
                logger.warning("event loop 最大延遲 %.1f ms(上一分鐘)", worst)
            worst, t_win = 0.0, time.monotonic()
```
判準:盤中 `grep "event loop 最大延遲" logs/server-*.log`。
做 F-01 之前應該看得到 40–50 ms 的命中(對應 seq-gap refetch);做完之後應該降到 < 10 ms。

### 9.4 WS 則數 / bytes 的真實值(瀏覽器側,零 code 改動)

Chrome DevTools → Network → 篩 `WS` → 點任一條 → **Messages** 分頁。
盤中開盤後錄 60 s,統計:

- `/ws/stock` 每秒訊息則數(預期:`ticks` ~10 + `book` 10–100 + `watchlist_quote` ≤150)
- 各型別的則數佔比 → 直接驗證 F-02 / F-03 的量級推估
- Response Headers 有沒有 `Sec-WebSocket-Extensions: permessage-deflate` → 驗證 F-04

或用 DevTools MCP:`list_network_requests` + `performance_start_trace` 看主執行緒
`JSON.parse` 與 React commit 的佔比。

### 9.5 丟包(既有,不必新建)

```powershell
# 盤後判準(CLAUDE.md 既有)
Select-String -Path C:\side-project\copycat\logs\server-*.log -Pattern "佇列滿"
```
現況應為 0。若做了 F-02 / F-03 的合併,這個 0 的「餘裕」會從 ~5 s 拉回接近文件宣稱的量級。

---

## 10. Open questions(查不出來 / 需要 user 或 profile)

1. **TC4 對主圖那一檔的 REALTIME 實際推播率是多少?**(決定 F-02 的量級是「10/s」還是「100/s」)
   → 只能盤中量。建議在 `_handle_quote` 臨時加一個每 60 s 印一次的計數器,或直接看 DevTools Messages。
2. **`watchlist_quote` 的 `_dirty_watchlist` 在真實盤中每秒平均幾檔?** 150 是上限,實際可能是 30–60。
   → 同上,盤中量。
3. **`/ws/txo-pnl` 的 `curve` 有多長?** 決定 F-07 的量級。TXO 沒在看的日子看不出來。
4. **`/api/stock/group-state?codes=…`(150 檔 light_snapshot,每 60 s)的序列化要多久?**
   `light_snapshot` 每檔含 `minutes`(~270 分鐘 × 5)+ `vp`(當日成交檔位數)→ 粗估
   每檔 15–25 KB × 150 = **2–4 MB**。若成立,這是比 F-01 更大的週期性卡頓(每 60 s 一次)。
   **本次沒有實測**,列為最高優先的下一個量測項。
5. **F-16 的 `call_soon_threadsafe` 每 tick 一跳在 Windows Proactor 上要多少?**
   需要一個能跑到 400 hop/s 的 harness 才量得準。
6. **user 接不接受閃電梯 / 五檔從 tick 率降到 10 Hz?**(F-02 的併窗方案;有 #180 的先例可援引)
7. **未來會不會有多台終端 / 多分頁同時看同一顆後端?** 決定 F-05 值不值得做。
8. **orjson 進 `[live]` extras 是否與「stdlib-only runtime」的哲學拍板衝突?**
   —— 這是 user 的決策,不是技術問題。我的判斷:`fastapi` / `uvicorn` / `pyzmq` 已在 extras,
   `orjson` 同層並不破壞「不裝 extras 也能跑 replay / backtest」這個真正的不變式。
