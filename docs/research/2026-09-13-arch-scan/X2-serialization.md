# X2-serialization — 跨切稽核:序列化與 wire format 全庫盤點

> 分析日期 2026-09-13 · 對象 `C:/side-project/copycat` · 只讀,未改動任何 repo 檔案
> 所有數字皆為本機 **實測**(Python 3.13 / `.venv`,Node v24.13.0),量測腳本留在
> `…/scratchpad/bench_json.py`、`bench_fastapi.py`、`bench_shape.py`、`bench_asdict.py`、`bench_inbound.py`

---

## 0. 一句話結論(先講最重要的)

**這套系統的 CPU 不在 JSON 上。**全鏈峰值的 JSON 總成本實測約 **6–8 ms / 每牆鐘秒 ≈ 0.7% 單核**。
把整套換 orjson / msgspec 大約省掉其中一半 → **省 0.3% 單核**。以「換序列化器換吞吐量」為理由的改造
在這裡是**過度工程**。

三件真正該做的、而且理由**不是吞吐量而是延遲抖動**:

| # | 事 | 為什麼 | 量級 |
|---|---|---|---|
| A | 大 payload 在 **event loop 上同步序列化** → loop stall | stall 期間**所有 WS 推播都停**,直接加在下單決策鏈的延遲上 | 單發 1.4–19 ms |
| B | **前端主執行緒** `JSON.parse` + 重建 Map | 掉幀;群組檢視 50 卡 = 8.2 ms,150 卡 = 25.5 ms | 每 60 s 一次 |
| C | **payload 形狀**(object-of-object + 字串鍵)比序列化器選型更值錢 | 改列式陣列:體積 1.6x↓、序列化 2.2x↑、兩者疊加 **3.8x** | 見 §6 |

而**已經夠快、不要動**的兩塊:
- **HTTP response 全鏈已經是 Rust**(FastAPI 0.139.2 的 `dump_json` fast path)。加 `ORJSONResponse` ≈ 零收益。
- **TC4 入站 `json.loads` 只佔該路徑 18–20%**,其餘 80% 是 `parse_stock_realtime` 的 Python 欄位展開。
  單換 parser 省 8%,是白工。

---

## 1. 架構地圖:這套系統的六條序列化路徑

```
                      ┌──────────────────── TC4 桌面 app (localhost) ────────────────────┐
                      │  ZMQ REQ/REP :50774        ZMQ PUB  :動態 SubPort                │
                      └───────┬───────────────────────────┬──────────────────────────────┘
                              │                           │
  ① REQ 送出                  │ json.dumps(小 dict)        │ ② 入站推播(熱)
     tc4.py:570               ▼                           ▼   raw bytes → decode → find(":")
  ③ REP 收回 -----------> _req()                    _listen_loop()   → json.loads(str)
     tc4.py:582/583        json.loads(bytes/str)    (×5 個 session 執行緒)  tc4.py:1199
                              │                           │
                              │                    handle_raw → parse_stock_realtime
                              │                           │       (Python 欄位展開,佔 80%)
                              ▼                           ▼
                    ┌─────────────────── uvicorn 單一 event loop ───────────────────┐
                    │                                                              │
                    │  StockEngine / IndexEngine / FuturesEngine / CorrEngine       │
                    │  BreadthEngine / SignalHub / CapitalClient(COM 執行緒)        │
                    │            │                           │                     │
                    │   ④ WS fanout                    ⑤ HTTP response             │
                    │   WsBroadcaster.publish(dict)     route → dict                │
                    │     → per-client asyncio.Queue      → ModelField.validate      │
                    │     → relay._send                   → serialize_json (RUST)    │
                    │       → starlette send_json          → Response(bytes)         │
                    │         → json.dumps ★每 client 各一次                          │
                    │                                                              │
                    │   ⑥ 檔案持久化(全部 stdlib json,大多同步在 loop 上)             │
                    │     data/1k/*.json  signals/*.jsonl  audit/*.jsonl            │
                    │     market/breadth-*.json(每分鐘整檔重寫)watchlist / config   │
                    └──────────────────────────────────────────────────────────────┘
                              │                           │
                              ▼ WS text frame             ▼ HTTP body (無 gzip;localhost 正確選擇)
                    ┌──────────────── 瀏覽器(React 19 / Vite preview :4173)──────────┐
                    │  ws-reconnect.ts:205  JSON.parse(ev.data)    ← 每則              │
                    │  hooks/*.ts           await res.json()       ← 每次 REST         │
                    │  再走一層 JS 重建:minutesFromRecord / vpFromRecord / fromSnapshot │
                    │  (Object.entries → Map,成本與 parse 同級)                       │
                    └──────────────────────────────────────────────────────────────┘
```

### 1.1 全庫呼叫點分佈(74 處)

```
copycat/live       :  5   ← 其中 tc4.py:1199 是唯一的每-tick 熱路徑
copycat/server     : 17   ← 引擎快取落檔 / jsonl / 審計 / HTTP 外呼 resp
copycat/data       : 18   ← 1K store + 四支 backfill(離線)
copycat/backtest   : 18   ← 全離線
copycat/replay     :  3   ← 全離線
copycat/*.py(根)  : 13   ← config / watchlist / names / calendar,啟動期讀一次
copycat/capital    :  0   ← 不自己序列化(走 dataclasses.asdict + route 層)
copycat/engine     :  0   ← 純狀態機,零 IO(設計正確)
```
`import json` 出現在 **36 個檔**;runtime 沒有任何第三方序列化套件(`pyproject.toml` `dependencies = []`)。

---

## 2. 熱路徑逐條 + 實測成本

### HP-1 入站 TC4 推播 —— `copycat/live/tc4.py:1231-1256`(`_listen_loop` / `_realtime_msg`)

```python
# tc4.py:1247  _listen_loop
raw = (sock.recv()[:-1]).decode("utf-8")   # ①bytes→str 全量 decode
...
self.handle_raw(raw)

# tc4.py:1193-1200  _realtime_msg
idx = raw.find(":")                        # ②找 topic 分隔
if idx < 0: return None
try:
    msg = json.loads(raw[idx + 1 :])       # ③slice 再複製一份 str,才 loads
except json.JSONDecodeError:
    return None
if msg.get("DataType") != "REALTIME":      # ④過濾在 loads 之後
    return None
```

**頻率**:5 個 TC4 session 各一條 daemon thread(stock / index / futures / corr / txo)。
`sock.setsockopt_string(zmq.SUBSCRIBE, "")` = 該 session 的所有推播全收。
80 檔自選 + 11 條相關腿 + 期指商品 + 277 檔 TXO 契約,開盤 5 分鐘粗估 **800–2000 則/s**,
盤中穩態 100–400 則/s(推播含五檔簿變動,不只成交)。

**實測(869 B 的個股 REALTIME 電文,三次重跑取範圍)**:

| 段 | 成本 | 佔比 |
|---|---|---|
| ① `bytes.decode('utf-8')` | 0.13 us | 0.5% |
| ② `find(":")` + slice | 0.13 us | 0.5% |
| ③ **`json.loads(str)`** | **5.0 – 10.6 us** | **18–20%** |
| ④ `_note_push` 指紋 tuple(4×`str(get())`) | 0.54 us | 2% |
| ⑤ **`parse_stock_realtime`** | **21.4 – 45.7 us** | **77–80%** |
| └ 其中 `_parse_levels` ×2(五檔歸一) | 16.4 us | |
| └ 其中 `StockMeta` 8 欄 `to_milli`/`_hhmmss` | 5.3 us | |
| **全鏈** | **27.6 – 56 us / 則** | |

換 Rust parser(`pydantic_core.from_json(bytes)`,orjson 同級)實測 **2.65–4.95 us**,省 2.3–5.7 us
= **全鏈的 8–10%**。

> **這就是為什麼「換 orjson 讓入站變快」是錯的判斷**:瓶頸在 ⑤,不在 ③。
> 800 則/s × 27.6 us = **22 ms/s = 2.2% 單核**,其中 JSON 只有 4 ms/s。
> 真正該改的是 `_parse_levels` 的十次 `to_milli` 與 dataclass 建構(那不在本區塊範圍)。

**但有一個真的該改的**:③ 在 ④ 的 `DataType` 過濾**之前**。TC4 的 PING 與非 REALTIME 電文
也被完整 parse 一遍。可以用 `if b'"REALTIME"' not in raw_bytes: return` 先做 bytes 級預篩
(記憶體掃描 ~0.05 us)再 parse。但要先量非 REALTIME 佔比 —— 若只有 1%,不值得。

### HP-2 出站 WS fanout —— `copycat/server/ws.py:281-284` + starlette

```python
# ws.py:281  relay._send
async def _send() -> None:
    async for msg in stream:               # msg 是 **同一個 dict 物件**(publish 不複製,正確)
        async with send_lock:
            await websocket.send_json(msg) # ★ 每個 client 各 json.dumps 一次
```
```python
# .venv/Lib/site-packages/starlette/websockets.py:174
text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
```

**`WsBroadcaster.publish` 把同一個 dict 放進 N 條 queue(零複製,對)**,但序列化發生在
**每個 client 的 `_send`**。N clients = **N 次 `json.dumps`**。

**頻率(stock_ws,峰值)**:
- `watchlist_quote` —— `stock_engine.py:1813-1832` `_flush_watchlist_loop`,`throttle_secs=1.0`,
  **一個 dirty 碼一則**(不是合併成一則!)→ 80 檔全活時 **80 則/s**,各 172 B。
- `ticks` 打包 —— `_flush_ticks`,`tick_flush_secs=0.1` → **≤ 10 則/s**,開盤一則可達 50–200 items。
- `book` —— `stock_engine.py:1359`,**完全沒有節流**:

```python
# stock_engine.py:1358-1359
if code == self._main:
    self._publish({"type": "book", "code": code, "bids": book.bids, "asks": book.asks})
```
  主圖那一檔**每一則 TC4 推播**(含純簿更新)各發一則。活躍股開盤可達 50–150 則/s。
  這是 `stock_ws` 上**唯一沒有 coalesce 的訊息型別**(`ticks` 有 0.1 s 打包、`watchlist_quote`
  有 1 s 節流、futures 有 0.1 s dirty flush),形狀不一致。

- futures_ws:`flush_interval_secs=0.1`,per-product dirty → 3–5 商品 × 10/s = 30–50 則/s
- corr_ws / river_ws:各 1 則/s
- index_ws:`index_engine.py:822`,秒級

**實測序列化成本**:

| 訊息 | 大小 | `json.dumps`+encode | Rust `to_json` | 倍率 |
|---|---|---|---|---|
| `watchlist_quote` 單檔 | 172 B | 3.40 us | 1.09 us | 3.13x |
| `ticks` items=10 | 1.3 KB | 10.74 us | 5.62 us | 1.91x |
| `ticks` items=50 | 6.2 KB | 47.4 us | 28.4 us | 1.67x |
| `ticks` items=200 | 24.8 KB | 215.8 us | 132.0 us | 1.64x |

**峰值一秒的出站 JSON 總量(1 client)**:
80×3.4 + 10×47 + 100×4(book) + 40×6(futures) + 2×15 ≈ **1.4 ms/s per client**。

**實際 client 數**:prod log `logs/server-20260911-0905.log` 整場 `/ws/stock` 只握手 10 次
(= 重連 / 重整),同時連線約 **1–2**。所以「N 倍浪費」目前 **N≈1–2,不是問題**。
它是**架構天花板**:雙螢幕 / 多分頁 / 之後接自動化 consumer 時 N 會漲,而修法只有三行。

### HP-3 HTTP response —— **已經是 Rust,不要動**

`copycat/server/app.py` 的 26 支路由全部標註 `-> dict`,`capital_api.py` 13 支同樣。
FastAPI 0.139.2(`.venv/Lib/site-packages/fastapi/routing.py:704-731`)有這條 fast path:

```python
# routing.py:709-731
use_dump_json = response_field is not None and isinstance(response_class, DefaultPlaceholder)
content = await serialize_response(..., dump_json=use_dump_json)
if use_dump_json:
    response = Response(content=content, media_type="application/json", **response_args)
```
```python
# routing.py:322
serializer = field.serialize_json if dump_json else field.serialize
```

`-> dict` + 未指定 `response_class` ⇒ `use_dump_json = True` ⇒ 走 **pydantic-core 的 Rust 序列化器**,
**跳過** `jsonable_encoder` 與 `json.dumps`。實測:

| 端點 payload | 大小 | `field.validate` | `serialize_json`(Rust) | 舊路徑(`serialize`+`json.dumps`) |
|---|---|---|---|---|
| group-state 12 檔 | 260 KB | 1 us | **1,396 us** | 5,164 us |
| group-state 50 檔 | 1,087 KB | 1 us | **5,840 us** | 23,158 us |
| group-state 150 檔 | 3,262 KB | 3 us | **18,852 us** | 74,696 us |
| breadth/rows 2800 | 640 KB | 1 us | **2,701 us** | 6,076 us(純 std dumps) |

`field.validate(dict)` 對裸 `dict` 型別幾乎是 no-op(1–3 us),沒有想像中的「pydantic 驗證稅」。
**加 `ORJSONResponse` 會把這條 fast path 關掉**(`response_class` 不再是 `DefaultPlaceholder`),
退回 `field.serialize`(Python dict 重建)+ orjson.dumps —— **反而變慢**。這是一個很容易踩的陷阱。

**prod 真實請求頻率**(同一份 log,~4.5 小時):

| 端點 | 次數 | 頻率 | 典型 payload | 序列化(Rust) |
|---|---|---|---|---|
| `/api/capital/positions` | 4,329 | 0.27/s | 幾十列 | < 100 us |
| `/api/capital/status` | 2,247 | 0.14/s | 小 | ~10 us |
| `/api/stock/group-state` | 1,247 | 0.077/s | **實測 codes 只有 7–9 個**(非 50/150) | **~1,400 us** |
| `/api/capital/fills` | 1,210 | 0.075/s | 數十至數百列 | 50–600 us |
| `/api/stock/state/{code}` | 911 | 0.056/s | 含 ticks,最壞 1.5 MB | **最壞 7,522 us** |
| `/api/market/breadth/rows` | 16 | — | 640 KB | 2,701 us |

> **重點**:`group-state` 的 `codes=` 實際只有 7–9 檔(log 逐行可證:
> `codes=3008,3406,3630,6209,4976,3362,3504,3441,3019`),不是 CLAUDE.md 上限的 150 檔。
> 所以 §3 的 3.3 MB 情境是**理論最壞**,不是現況。現況每發 ~1.4 ms。

### HP-4 檔案持久化

| 位置 | 頻率 | 執行緒 | payload | 實測 |
|---|---|---|---|---|
| `server/breadth_engine.py:970` `_save` | **每分鐘**(`_poll_loop` 內) | **event loop,同步** | 整份 series,收盤時 ~21 KB | dumps ~200 us + `write_text` + `os.replace` |
| `server/breadth_engine.py:873` `_save_streaks` | 每日一次 | event loop | 實測檔案 524–568 B | 可忽略 |
| `server/signal_hub.py:1417` `_append_jsonl` | 每則訊號(實測 **686 列/日**) | Discord worker | 316 B | 4.2 us |
| `server/signal_hub.py:1378` 回填重寫 | 每日 13:40 一次 | `asyncio.to_thread` ✔ | 只重序列化 dirty 列,其餘保留原 bytes ✔ | 設計正確 |
| `server/audit.py:30` `append_audit` | 每筆下單 ×2 | `asyncio.to_thread` ✔ | 小 | dumps 可忽略;成本在 `open`+`flush` |
| `data/store.py:39/46` 1K bar | **離線**(21,254 檔 / 294 MB) | CLI | 13.5 KB/檔,列式陣列 ✔ | dumps 171 us / loads 145 us |
| `screen_engine.py:445` / `stock_watchlist.py:174` / 各 config | 啟動或使用者操作 | 混 | 小 | 可忽略 |

`breadth_engine._save` 是**唯一一個週期性、同步在 event loop 上、整檔重寫**的落檔。
每分鐘 270 次 × (~200 us dumps + 檔案 IO ~1–3 ms) = 每分鐘一次 1–3 ms 的 loop stall。
不是災難,但屬於「該搬 `to_thread` 且該改成 append」的明確債。

### HP-5 `dataclasses.asdict` —— 全庫 16 處,其中 6 處在 HTTP 熱端點

```python
# server/capital_api.py:253-291
@router.get("/api/capital/orders")
async def capital_orders(request: Request) -> dict:
    return {"orders": [
        {**dataclasses.asdict(o), "code": _fill_code(o.unit, o.stock_no)}
        for o in client.store.orders()]}

@router.get("/api/capital/fills")     # 同款
@router.get("/api/capital/positions") # 同款(polled 4,329 次 = 全站第一名)
```

`dataclasses.asdict` 是**遞迴 + `copy.deepcopy` 非 dataclass 值**的實作。
`OrderRecord` / `FillRecord` / `Position` 都是**扁平**的(欄位全是 `str|int|float|bool|None`),
所以 deepcopy 是純浪費。實測:

| | `asdict` | `dict(obj.__dict__)` | 倍率 |
|---|---|---|---|
| 單列 `OrderRecord`(22 欄) | 4.66 us | **0.51 us** | **9.2x** |
| 單列 `FillRecord`(9 欄) | 2.29 us | **0.24 us** | **9.7x** |
| 整支 route n=100 | 411.8 us | **51.2 us** | 8.0x |
| 整支 route n=400 | 1,872 us | **217.7 us** | 8.6x |
| 整支 route n=1200 | 5,228 us | **748.6 us** | 7.0x |

**對照:n=400 的 Rust 序列化只要 575 us。也就是 `asdict` 比真正的序列化還貴 3.3 倍。**

另外 `capital/client.py:339-341` 的 `_record()` 也用 `asdict`,但那是每筆下單 ×2,量可忽略
(且 `_WriteReq` 是 frozen dataclass,`__dict__` 一樣可用)。

### HP-6 前端解析端

```ts
// frontend/src/lib/ws-reconnect.ts:205
value = JSON.parse(ev.data);        // 每則 WS,8 條連線共用這一支
```
```ts
// frontend/src/hooks/useGroupSnapshots.ts:83-101  fetchGroupState
const body = (await res.json()) as { states?: Record<string, RawState> };
for (const [code, raw] of Object.entries(body.states ?? {})) {
  out[code] = { minutes: minutesFromRecord(raw.minutes), ..., vp: vpFromRecord(raw.vp), ... };
}
```

**Node v24 實測(V8 = 瀏覽器同引擎)**:

| payload | 大小 | `JSON.parse` | JS 重建(Object.entries → Map) | 主執行緒總 block |
|---|---|---|---|---|
| group-state 9 檔(**現況**) | 196 KB | 1,026 us | 518 us | **1.54 ms** |
| group-state 50 檔 | 1,086 KB | 5,884 us | 2,309 us | **8.19 ms**(半幀) |
| group-state 150 檔 | 3,258 KB | 16,293 us | 9,216 us | **25.5 ms**(1.5 幀) |
| `/api/stock/state` 全量 20k ticks | 1,483 KB | 4,939 us | + `foldVp` 20k 迴圈 | **> 5 ms** |
| breadth/rows 2800 | 640 KB | 1,693 us | — | 1.7 ms |
| WS `ticks` items=50 | 6.2 KB | 22.7 us | — | 可忽略 |
| WS `ticks` items=200 | 24.8 KB | 77.2 us | — | 可忽略 |

**JS 重建那一層(`Object.entries` → `Map`)成本是 `JSON.parse` 的 40–57%** —— 幾乎等於再 parse 一次。
這是 §6「payload 形狀」論點的第二個支柱:改成列式陣列,`JSON.parse` 直接吐出可用的
`[[m,c,v,…],…]`,重建那層可以整層刪掉。

---

## 3. 總帳:JSON 在這套系統裡到底花了多少 CPU

**峰值一秒模型**(09:00–09:05,80 檔自選,1 個瀏覽器分頁 = 每個 broadcaster 1 個 client,
群組檢視開著 9 張卡):

| 路徑 | 量 | 單價 | 小計 |
|---|---|---|---|
| 入站 stock session | 800 則/s | 5.0 us(json 部分) | 4.0 ms/s |
| 入站 futures | 100 則/s | 5.0 us | 0.5 ms/s |
| 入站 corr(11 腿) | 50 則/s | 5.0 us | 0.25 ms/s |
| 入站 txo(277 契約,多半靜默) | 50 則/s | 5.0 us | 0.25 ms/s |
| 入站 index | 5 則/s | 5.0 us | 0.03 ms/s |
| 出站 WS × 1 client | 見 HP-2 | — | 1.4 ms/s |
| HTTP(攤平) | group-state 0.077/s + positions 0.27/s + … | — | ~0.2 ms/s |
| 檔案 | breadth `_save` 1/60 s | — | ~0.004 ms/s |
| **合計** | | | **≈ 6.6 ms / 牆鐘秒 = 0.66% 單核** |

**全部換成 Rust 序列化器 → 省約 3 ms/s = 0.3% 單核。**

盤中穩態(200 則/s 入站)這個數字降到 ~2 ms/s = 0.2% 單核。

> 這就是本區塊最重要的一句話:**序列化器選型在這裡是 0.3% 的議題,不是效能改造的主軸。**
> 任何把「換 orjson」寫成第一優先的改造計畫,都應該被這張表擋下來。

**真正該擔心的是分佈的尾巴,不是總和:**
- `/api/stock/state/{code}` 最壞 7.5 ms 的 event-loop stall,期間 8 條 WS 全部停推。
- group-state 若真的用到 50 檔:6 ms 後端 stall + 8 ms 前端 stall。
- 而**最大的 loop stall 來源根本不是 JSON**:5 條 listener thread 跑 Python bytecode
  (`parse_stock_realtime` 21–46 us/則),CPython 預設 `sys.setswitchinterval()` = **5 ms**,
  一條 CPU-bound Python thread 最久可以**霸佔 GIL 5 ms** 才讓出。全庫 `grep setswitchinterval`
  **零命中**。這是本次稽核順手查到的、比 JSON 大一個量級的抖動源。

---

## 4. Findings 全文

### F-01 [critical / on-hot-path] WS fanout 逐 client 重複序列化(N 倍),且 Protocol 只暴露 `send_json` 堵死了修法

**位置**:`copycat/server/ws.py:281-284`(`relay._send`)、`ws.py:158-166`(`WsConnection` Protocol)、
`ws.py:71-89`(`WsBroadcaster.publish`)

```python
# ws.py:158-166
class WsConnection(Protocol):
    async def send_json(self, data: Any) -> None: ...
    async def receive(self) -> Mapping[str, Any]: ...

# ws.py:281-284
async def _send() -> None:
    async for msg in stream:
        async with send_lock:
            await websocket.send_json(msg)     # starlette 內部 json.dumps
```

**影響**:同一則訊息被序列化 N 次(N = 該 broadcaster 的 client 數)。現況 N≈1–2
(prod log `/ws/stock` 整場只 10 次握手),所以**今天不是瓶頸**;但這是架構天花板 ——
雙螢幕 / 多分頁 / 之後掛自動化 consumer 時線性惡化。峰值單 client 出站 JSON ≈ 1.4 ms/s,
N=4 時 5.6 ms/s。

**修法**:在 `WsBroadcaster.publish` 入口序列化**一次**,queue 裡放 `(bytes, dict)` 或直接放
`str`;`relay` 改走 `send_text` / `send_bytes`。`WsConnection` Protocol 要多一個
`send_text(self, data: str)`。心跳 `PING` 可以做成模組級預序列化常數(它是常量 dict!)。

```python
# 建議形狀
PING_TEXT = '{"type":"ping"}'          # 預序列化,零成本心跳
def publish(self, msg: dict) -> None:
    text = _dumps(msg)                  # 一次
    for q in self._clients: q.put_nowait(text)
```

**風險**:
- `stream(seed=...)` 的種子(`stock_engine.py:1765`、`breadth_engine.py:340`、
  `index_engine.py:819`)也要走同一支序列化。
- `send_seed`(`ws.py:170-188`)是 route 層在 `relay` 之前自送的(txo-pnl / corr / river),
  它吃 `Any` 不吃 dict,要分開處理。
- **測試面**:8 條 WS 的 fake `WsConnection` 全部要補 `send_text`。
  `tests/server/test_ws.py` 與各 engine 測試會紅一片。
- 不動任何 CLAUDE.md §4 跨檔契約(wire 上的 JSON 文字**逐字相同**)——
  但 `separators=(",", ":")` / `ensure_ascii=False` **必須逐字沿用 starlette 的參數**,
  否則 wire 上的空白會變(前端不受影響,但 golden 對帳與 log diff 會全紅)。

**effort**:M

---

### F-02 [high / on-hot-path] `book` 訊息零節流 —— `stock_ws` 上唯一沒有 coalesce 的型別

**位置**:`copycat/server/stock_engine.py:1358-1359`

```python
if code == self._main:
    self._publish({"type": "book", "code": code, "bids": book.bids, "asks": book.asks})
```

**影響**:主圖那一檔**每一則 TC4 推播**(含純簿更新、無成交)各發一則 WS。活躍股開盤
50–150 則/s;每則 × N client 各一次 `json.dumps`。同一個 engine 裡:
- `ticks` 有 0.1 s 打包(`_flush_ticks`,`tick_flush_secs=0.1`)
- `watchlist_quote` 有 1 s 節流(`_flush_watchlist_loop`)
- `futures_engine` 有 0.1 s dirty flush(`flush_interval_secs=0.1`)

**只有 `book` 沒有**。而五檔閃電梯畫面的更新頻率上限本來就是 60 fps,>60 則/s 的推播
有一半以上是前端 render 前就被蓋掉的。

**修法**:沿 `_flush_ticks` 的既有樣板(dirty flag + 單一 `call_later` timer),
`book` 用同一個 0.1 s 窗 coalesce(**只送最後一則**,book 是全量快照,合併零資訊損失 ——
與 `futures_engine._flush` 的 docstring 論證逐字同款)。

**風險**:閃電梯五檔最多晚 0.1 s。這與 `app.py:969` 刻意不傳 `flush_interval_secs`
的註解(「五檔盤中要即時,1 s 週期會讓閃電梯五檔慢一秒」)**方向一致**:那裡拒絕的是 1 s,
不是 0.1 s。仍屬行為改動(🔴),需 user 拍板。

**effort**:S

---

### F-03 [high] `dataclasses.asdict` 在三支 HTTP 端點上,成本是真正序列化的 3.3 倍

**位置**:`copycat/server/capital_api.py:258`、`:271`、`:288`(另 `:307/337/344/355/364/381`
的單物件版本,量可忽略);`copycat/capital/client.py:339-341`

```python
{**dataclasses.asdict(p), "code": stock_code_of(p.market, p.stock_no)}
```

**影響**:`asdict` 是遞迴 + `copy.deepcopy`。`Position` / `OrderRecord` / `FillRecord`
全是扁平 dataclass(欄位只有 `str|int|float|bool|None`),deepcopy 純浪費。
實測單列 9.2x(4.66 → 0.51 us);n=400 時 1,872 us → 218 us(省 1.65 ms),
而同一份 payload 的 Rust 序列化只要 575 us。

`/api/capital/positions` 是 prod log 上**請求次數第一名**(4,329 次),`fills` 第四名(1,210)。

**修法**:`{**p.__dict__, "code": ...}`。三支 route 各改一行。
`Position` 若是 `frozen=True` 仍有 `__dict__`(dataclass 用 `object.__setattr__`,不是 `__slots__`);
需先確認沒有 `slots=True`(檢查 `copycat/capital/models.py:169` 的 `@dataclass` 是裸的 ✔)。

**風險**:
- 若未來有人給這些 dataclass 加 `slots=True`,`__dict__` 會 AttributeError ——
  屬於「會炸、不會靜默錯」,可接受;可用 `fields()` 推導式當保險(實測 1.10 us,仍比 asdict 快 4x)。
- 若未來欄位裡放進**巢狀 dataclass 或可變預設**,`__dict__` 會回傳參考而非複本 ——
  現況這三個 dataclass 沒有,但要在 docstring 記一行。
- **CLAUDE.md §4 契約**:`OrderRecord.unit` / `FillRecord.unit` 的字面值(張/口/股)與
  `avg_source` / `today_qty` / `PositionKind ⊆ TradeKind` 的 parity 測試
  (`tests/capital/test_models.py::test_avg_source_parity_with_frontend`、
  `test_position_kind_subset_of_trade_kind`)**不受影響** —— 它們比的是型別值域,
  不是轉 dict 的手段。wire 輸出逐字相同。

**effort**:S

---

### F-04 [high] 千萬不要加 `ORJSONResponse` —— 會把 FastAPI 的 Rust fast path 關掉

**位置**:`.venv/Lib/site-packages/fastapi/routing.py:704-731`(證據,非本 repo)

```python
use_dump_json = response_field is not None and isinstance(response_class, DefaultPlaceholder)
```

**影響**:本 repo 39 支路由全部標 `-> dict` 且**沒有**指定 `response_class`,所以
`response_class` 是 `DefaultPlaceholder` ⇒ `use_dump_json=True` ⇒ 走
`field.serialize_json`(pydantic-core Rust)。實測 group-state 50 檔:
- 現況(Rust):`validate` 1 us + `serialize_json` **5,840 us**
- 若改 `ORJSONResponse`:`field.serialize`(Python 重建整棵 dict)10,664 us + orjson.dumps
  ≈ 與實測的 `serialize` + `json.dumps` 23,158 us 同量級(orjson 只省 dumps 那一半)
  → **約 2.5–3x 變慢**

**修法**:**不要動**。這是本次稽核的核心「反向發現」。
唯一該加的,是在 `copycat/server/app.py` 的 app 建構處加一行註解,把這件事釘住,
避免下一個人「順手優化」。

**風險**:0(不做事)。但**必須寫下來** —— 這是一個「看起來明顯正確的優化,實際上是 3x 退步」
的陷阱,且退步完全無訊號(response 內容逐字相同)。

**effort**:S(只是一行註解 + 一條測試)

---

### F-05 [high] 大 payload 在 event loop 上同步序列化 → 8 條 WS 齊停

**位置**:`copycat/server/app.py:1668-1706`(`stock_state`)、`:1707-1736`(`stock_group_state`)、
`:1940-1979`(`market_breadth_rows`);序列化實際發生在 FastAPI 的 `serialize_response`,
**在 route 的 event loop 上同步執行**。

```python
# app.py:1736
return {"states": stock.group_snapshot(wanted)}
```

**影響**:序列化期間 event loop 完全停擺,`relay._send` 的 `await websocket.send_json`
排不到 —— **所有 WS 推播在這段時間全部延遲**。實測 stall 長度:

| 端點 | 現況 payload | stall |
|---|---|---|
| `/api/stock/group-state`(prod 實測 7–9 檔) | 196–260 KB | **1.4 ms** |
| `/api/stock/group-state`(上限 150 檔) | 3.3 MB | **18.9 ms** |
| `/api/stock/state/{code}`(6,000 ticks) | 471 KB | **2.2 ms** |
| `/api/stock/state/{code}`(20,000 ticks 上限) | 1.5 MB | **7.5 ms** |
| `/api/market/breadth/rows` | 640 KB | **2.7 ms** |

對「要下實單」的系統,一發 7.5 ms 的推播空窗是**可量測且可歸因**的延遲。

**修法(依效益排序)**:
1. **縮 payload**(F-06,效益最大,3.8x)。
2. `?tape=0` 的路已經存在(`app.py` 認字面 `"0"`,CLAUDE.md §4 契約),
   **群組檢視點卡片的那條路已經在用**;要確認主圖以外沒有人在拿全量。
3. 把序列化丟 `asyncio.to_thread` —— **不建議**:pydantic-core 的 `to_json` 在 Rust 裡
   對 Python 物件求值時仍持 GIL,搬執行緒省不到;而且會多一次 context switch。
4. `sys.setswitchinterval(0.0005)` —— 這條救的是 listener thread 的 GIL 霸佔,不是這條。

**風險**:縮 payload = 改 wire = 動 CLAUDE.md §4 的
「個股 `seq` 的兩個口徑」/「`tape=0` 字面值 + `tape_omitted`」/「快照與打包的 seq 對齊」三條契約
的**鄰居**(不是那三條本身,但同一批鍵)。詳見 F-06。

**effort**:見 F-06

---

### F-06 [high] payload 形狀比序列化器選型值錢 2 倍 —— `minutes` / `vp` 是 object-of-object + 字串鍵

**位置**:`copycat/live/stock_state.py:199-219`(`_minutes_payload`)、`:255-268`(`light_snapshot` 的 `vp`)

```python
# stock_state.py:206-218
return {
    str(k): {"c": m.close_milli, "v": m.volume, "i": m.inner, "o": m.outer,
             "u": m.unch, "h": m.high_milli, "l": m.low_milli}
    for k, m in sorted(self.minutes.items())
}
# stock_state.py:261
"vp": {str(price): list(cell) for price, cell in sorted(self._vp.items())},
```

**影響**:每一分鐘 bar 都付一個 dict 物件 + 7 個 key 字串 + 一個 **數字轉字串的 key**。
前端還要 `Object.entries` + `Number(k)` 轉回來(`useGroupSnapshots.ts:70-75`、
`stock-accum.ts::minutesFromRecord`)。

**實測(270 分鐘 + 90 個 VP 檔位)**:

| 形狀 | 大小 | std.dumps | Rust to_json | std.loads | Rust from_json |
|---|---|---|---|---|---|
| **A 現況** object-of-object | 22,073 B | 252.9 us | 145.2 us | 250.6 us | 211.3 us |
| **B 列式** `[[m,c,v,i,o,u,h,l],…]` | **13,804 B** (−37%) | 163.1 us | **66.3 us** | 166.2 us | **98.8 us** |
| C 欄式 `{m:[],c:[],…}` | 13,164 B (−40%) | 154.0 us | 75.7 us | 189.4 us | 78.8 us |

**A/std.dumps 252.9 us → B/Rust 66.3 us = 3.8x**。
單換序列化器(A/std → A/Rust)只有 1.74x。**形狀貢獻了 2.2x,序列化器貢獻 1.74x。**

前端同理:列式讓 `minutesFromRecord` / `vpFromRecord` 那層(實測佔 `JSON.parse` 的 40–57%)
可以整層刪掉 —— `JSON.parse` 直接吐出可迭代的 `number[][]`。

**修法**:`minutes` 與 `vp` 改列式陣列,分鐘鍵 / 價位鍵當作陣列第 0 欄(整數,不轉字串)。
`data/store.py:20-35` 的 1K bar 落檔**已經是列式**(`[m,o,h,l,c,v,up,down,unch]`)——
這是同一個 repo 裡的既有正確示範,直接沿用它的慣例。

**風險(這是本區塊 blast radius 最大的一條)**:
- **CLAUDE.md §4 契約直接受影響**:
  - 「個股 `seq` 的兩個口徑」—— `snapshot.seq` / `tick.seq` 語意不變,但 `minutes` 同在
    一份 payload,前端 `fromSnapshot` 要同步改。
  - 「`tape=0` 字面值 + `tape_omitted`」—— `tape_omitted` 不變。
  - 「個股頁即時末根的分鐘鍵 = accum 起點分 +1、上限 13:30」
    (`frontend/src/lib/live-last-bar.ts::mergeLiveMinuteBars`)—— 它吃 `accum.minutes`,
    而 `accum.minutes` 是 `minutesFromRecord` 的產物(`Map<number, …>`)。
    **只要前端在 `minutesFromRecord` 這一層吸收形狀變更、對外仍回 `Map<number,…>`,
    live-last-bar 那條契約與 `lib/live-last-bar.test.ts` 的 9 條測試就零改動。**
    這是唯一該走的接法。
  - 「VP fold 規則逐條對齊前端 `stock-accum.ts::foldVp`,parity 由
    `tests/fixtures/vp_parity.json` 兩側各自斷言」—— **fixture 是規則 parity,不是 wire 形狀**,
    只要 fold 規則不動就不紅;但要確認 fixture 內容不含 wire 形狀。
- `group_snapshot` 的 `{**light, …}` 轉發(`stock_engine.py:851`)不變。
- 需要**前後端同一次部署**(CLAUDE.md 已有此政策:「改規則種類的部署一律前後端同版」)。
- 建議做法:**additive 過渡**——先加 `minutes_v2`(列式)、前端優先讀它、
  兩版並存一週後再拆掉舊鍵。additive 是這個 repo 的既有慣例(`vwap_vol` / `h`/`l` 都是這樣加的)。

**effort**:L

---

### F-07 [medium / on-hot-path] 入站 `json.loads` 在 `DataType` 過濾**之前**;且走 str 而非 bytes

**位置**:`copycat/live/tc4.py:1193-1200`

```python
idx = raw.find(":")
if idx < 0: return None
try:
    msg = json.loads(raw[idx + 1 :])     # 先 parse
except json.JSONDecodeError:
    return None
if msg.get("DataType") != "REALTIME":    # 才過濾
    return None
```
外加 `tc4.py:1247` 的 `raw = (sock.recv()[:-1]).decode("utf-8")` —— 整則先 decode 成 str,
`_realtime_msg` 再 slice 出第二份 str。

**影響**:非 REALTIME 電文(TC4 PING、SUB/UNSUB 回執廣播)也被完整 parse。
量級未知(需實測佔比)。decode + slice 本身只有 0.26 us,不是問題;
但走 bytes 路徑可以讓 Rust parser 發揮(`from_json(bytes)` 2.65–4.95 us vs
`json.loads(str)` 5.0–10.6 us)。

**修法**:
1. `_listen_loop` 保留 bytes,`_realtime_msg` 改吃 `bytes`,用 `raw.find(b":")`。
2. parse 前先 `if b'"REALTIME"' not in raw: return None`(記憶體掃描,~0.05 us)。
3. parser 換 Rust(見 §5 的選型討論)。

**但先量再改**:這條省的是全鏈的 8–10%(見 HP-1 表),而全鏈本身在峰值也只有 22 ms/s。
**先做 F-09(`setswitchinterval`)與 `parse_stock_realtime` 的優化(不在本區塊),再回頭看這條。**

**風險**:
- `handle_raw(raw: str)` 是**四個子類共用的覆寫點**(`stock_source.py:925`、
  `futures_source.py:222`、`corr_source.py:164`,以及基底 `tc4.py:1207`),簽名改 str→bytes
  要同動四處 + 所有 fake。
- `tests/live/test_stock_source.py:786` 等測試直接餵 `"Q:" + json.dumps(...)` 字串,全部要改。
- **不動任何 CLAUDE.md 契約**(純內部)。

**effort**:M

---

### F-08 [medium] `breadth_engine._save` 每分鐘在 event loop 上整檔重寫

**位置**:`copycat/server/breadth_engine.py:955-973`,呼叫點 `:595`(在 `_poll_loop` 的
`_append` 路徑內,**非** `to_thread`)

```python
self._series[key] = point     # :594
self._save()                  # :595  ← 同步
...
# :970
tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
os.replace(tmp, path)
```

**影響**:每分鐘一次。收盤時 series 檔 ~21 KB(實測 `data/market/breadth-2026-08-19.json` = 20,409 B)。
`json.dumps` ~200 us + `write_text` + `os.replace` ≈ 1–3 ms 的 event-loop stall,270 次/日。
同檔的其他外呼都已經走 `to_thread`(`:399`、`:451`、`:486`、`:750`),**只有落檔沒走**。

**修法**:`await asyncio.to_thread(self._save)`。若要更徹底,改成 append-only
(一分鐘一行 jsonl)—— 但那會動到 `_restore` 與 `_FILE_VERSION`,收益不成比例。
**先只搬 `to_thread`。**

**風險**:`_save` 內讀 `self._series` / `self._trade_date`,搬到別的執行緒後
與 `_append` 的下一輪有 race(讀到半更新的 dict)。要在呼叫前先 snapshot
(`payload = {...self._series_list()}` 在 loop 上做,只把 dumps+寫檔丟 thread)。
`_save_streaks`(`:855`)同理,但每日一次、檔案 524 B,**不值得動**。

**effort**:S

---

### F-09 [medium / on-hot-path] 全庫沒有設 `sys.setswitchinterval` —— 5 條 listener thread 可各霸佔 GIL 5 ms

**位置**:全庫 `grep -rn "setswitchinterval" copycat/` **零命中**。
相關執行緒:`tc4.py:1185`(`_start_listener` × 5 個 session)、`tc4.py:1253`(`_heal_loop`)、
`capital/client.py` 的 COM thread。

**影響**:CPython 預設 `sys.getswitchinterval()` = **0.005 s**。一條跑 Python bytecode 的
執行緒在強制讓出 GIL 前最久可以連跑 5 ms。`_listen_loop` 的 `handle_raw` → `parse_stock_realtime`
是**純 Python bytecode**(21–46 us/則),開盤連續處理時很容易連跑滿 5 ms 才讓出。
5 條這種 thread 同時活躍 ⇒ event loop 最壞可以被餓到 **> 5 ms** 才拿到 GIL。

這比本區塊找到的任何 JSON 成本都大一個量級,而且**完全沒有觀測**。

**修法**:`copycat/server/__main__.py` 啟動時 `sys.setswitchinterval(0.0005)`(0.5 ms)。
一行。代價是 context switch 變頻繁(整體吞吐略降,實測通常 < 2%),換來 loop 延遲上界從 5 ms → 0.5 ms。

**風險**:
- 這是**全 process 的行為改動**,會影響所有執行緒(含 COM 下單執行緒)。
- 吞吐量微降,但這套系統的瓶頸不是吞吐量。
- **必須先量**(見 §8 的探針),不能盲設。
- 不動任何契約。

**effort**:S(改動)/ M(量測證明)

**注意**:這條嚴格說不屬於「序列化」,是稽核 `_listen_loop` 時查到的。
列在這裡是因為**它決定了 F-01/F-05 那些 ms 級 stall 有沒有意義** ——
若 GIL 本來就會卡 5 ms,省 1.4 ms 的序列化沒有可觀測收益。**這條要排在所有 JSON 改動之前。**

---

### F-10 [medium] `watchlist_quote` 一個 dirty 碼一則,沒有合併成批

**位置**:`copycat/server/stock_engine.py:1827-1832`

```python
dirty, self._dirty_watchlist = self._dirty_watchlist, set()
for code in dirty:
    state = self._states.get(code)
    if state is None or state.last is None:
        continue
    self._publish(self._quote_payload(code))    # 一碼一則
```

**影響**:80 檔自選全活時 **80 則/s**,每則 172 B、3.4 us dumps × N client。
同一個 engine 的 `ticks` 在 #182 已經改成打包(「50 檔開盤每秒數百筆 → ≤ 10 則/s」),
`watchlist_quote` 沒跟上。前端 `useStockStream.ts:413` 的 `case "watchlist_quote"`
每則各觸發一次 state 更新 → 80 次/s 的 React 排程。

**成本**:出站 80 × 3.4 = 272 us/s(小)。但**訊息數**才是重點:
80 則/s 佔掉 per-client queue(`_CLIENT_QUEUE_MAX`)的水位,且前端 80 次/s 的
`JSON.parse` + handler dispatch + React setState 比序列化本身貴。

**修法**:沿 `_flush_ticks` 的打包樣板,`{"type":"quotes","items":[…]}` 一秒一則。

**風險**:
- **改 wire = 前後端同動**。前端 `useStockStream.ts` 的 `case "watchlist_quote"` 要加
  `case "quotes"`,舊 dist 收到新型別會走 `default` 靜默丟棄 → **側欄整片凍住,零錯誤訊號**
  (與 CLAUDE.md §4 記載的 `ticks` 打包同一種失效樣態)。
- CLAUDE.md §4 沒有專門條目管 `watchlist_quote` 的形狀,但 `_quote_payload` 的 docstring
  明寫「**判準,不是清單**:凡是要把 `watchlist_quote` 推出去的地方一律呼叫本函式」——
  打包後 items 的欄位必須仍由 `_quote_payload` 單一產生。
- 建議**與 F-01 一起做**(同一次前後端同版部署),不要拆成兩次。

**effort**:M

---

### F-11 [low] `PING` 心跳每 10 s × 每連線各序列化一次一個常量 dict

**位置**:`copycat/server/ws.py:41`(`PING: dict[str, str] = {"type": "ping"}`)、`:286-290`(`_beat`)

```python
PING: dict[str, str] = {"type": "ping"}
...
async def _beat() -> None:
    while True:
        await asyncio.sleep(secs)
        async with send_lock:
            await websocket.send_json(PING)     # 每 10 s、每連線,各 dumps 一次
```

**影響**:8 條 WS × 每 10 s = 0.8 次/s × ~1 us = **0.8 us/s**。完全可忽略。

**列出來的理由**:它是 F-01 修法的**零風險試驗田** —— `PING_TEXT = '{"type":"ping"}'`
配 `send_text` 可以先驗證 Protocol 加 `send_text` 這件事能不能無痛落地,再推廣到 `publish`。
**CLAUDE.md §4「WS 心跳契約」的 wire 文字逐字不變**(前端 `isPing` 比的是 parse 後的
`value.type === "ping"`)。

**effort**:S

---

### F-12 [low] TC4 歷史回補的分頁粒度 → 每頁一次 `json.loads`,開盤 4,000+ 次

**位置**:`copycat/tc4common.py:32-50`(`iter_qry_pages`)、`copycat/live/tc4.py:1012-1013`
(`_collect_history._page`)、`tc4.py:578-583`(`_req(strip_prefix=True)`)

```python
# tc4.py:578-583
if strip_prefix:
    text = message.decode("utf-8")     # 整頁 decode
    idx = text.find(":")
    return json.loads(text[idx + 1 :])  # 整頁 parse
return json.loads(message)
```

**影響**:docs 實測「GetHistory 分頁 max 1.1 ms(3,482 次、10.7 萬 rows)」
⇒ **每頁約 31 rows**。40 檔開盤回補 ≈ 4,000 次 round trip,每次含一發 `json.dumps`(request)
+ 一發 `json.loads`(response)。粗估 JSON 部分 ~0.2 s,約佔回補總時間(memory 記載
`perf/opening-backfill-parallel` 後 40 檔 0.87 s)的 20%。

**修法**:分頁粒度是 TC4 端決定的,這裡改不了。可做的只有把 parser 換 Rust(省一半)。
**真正的問題是 3,482 次 round trip 這件事本身**,那屬於 TC4 協定區塊,不在本區塊。

**風險**:`_req` 是全庫 REQ 的唯一出口,改它影響所有 TC4 呼叫。收益 0.1 s / 開盤一次。
**不建議單獨為此動。** 若 F-07 做了(bytes 路徑 + Rust parser),這條順帶收掉。

**effort**:S(搭 F-07 順手)

---

### F-13 [low] 離線 1K store:294 MB / 21,254 檔,全 stdlib `json.loads`

**位置**:`copycat/data/store.py:39`(write)、`:46`(read);
讀者 `backtest/pipeline.py:117/286`、`fade_pipeline.py:97/444/703`、`replay/runner.py:93/109`

```python
# store.py:46
payload = json.loads(path.read_text(encoding="utf-8"))
```

**影響**:單檔 13.5 KB(270 根 × 9 欄列式),`json.loads` 145 us / `from_json` 78 us。
全庫掃一遍 21,254 檔 = **3.1 s → 1.7 s**。
但回測是**每 sample 讀一檔**(不重複讀同一檔),且有 `_load_or_simulate` 的 outcome cache
(`pipeline.py:256-262`,三重失效檢查:`_cache_version` / `sim_hash` / `rows_hash` / `with_grid`),
真正跑 simulate 的次數有限。相對於 `simulate_sample` 的迴圈成本,JSON 不是瓶頸。

**修法**:**不要動**。要動的話,正解不是換 parser 而是換容器
(整個 universe 一份 Parquet / 一份 memory-mapped 二進位),但那要先證明回測時間真的卡在 IO。

**注意 `data/store.py` 的 payload 形狀已經是列式陣列** —— 這是 repo 內既有的正確示範,
F-06 直接引用它當先例。

**effort**:XL(若真要做)/ 建議 0

---

### F-14 [low] `signal_hub` 回填的逐行 bytes 保留是**正確設計**,不要「優化」成整檔 dumps

**位置**:`copycat/server/signal_hub.py:1375-1382`

```python
body = line.rstrip("\r\n")
eol = line[len(body):]
lines[i] = (json.dumps(row, ensure_ascii=False) + eol).encode("utf-8")
...
await asyncio.to_thread(atomic_write_bytes, path, b"".join(lines))
```

**這條是反向 finding**:CLAUDE.md §4 明記「回填改成整檔 dumps → 舊列鍵序 / 浮點字面變動,
對帳 diff 整檔紅;`tests/server/test_signal_outcome.py` byte 比對釘住」。
只重序列化 dirty 列、其餘保留原 bytes、行尾原樣、`atomic_write_bytes` 覆寫 —— **設計完全正確**,
而且已經走 `to_thread`。

**修法**:不動。但若 F-07 / 其他地方換了 parser,**這裡必須留 stdlib `json.dumps`** ——
orjson / Rust serializer 的浮點字面與鍵序輸出與 stdlib **不保證逐字相同**,
換掉會直接打破那條 byte 比對契約與研究目錄的離線對帳。

**effort**:0(但要在改 parser 時當作硬白名單記著)

---

### F-15 [low] 前端 `Object.entries → Map` 重建層成本 = `JSON.parse` 的 40–57%

**位置**:`frontend/src/hooks/useGroupSnapshots.ts:64-75`(`vpFromRecord`)、`:83-101`
(`fetchGroupState`)、`frontend/src/lib/stock-accum.ts:236-273`(`fromSnapshot`)

```ts
// useGroupSnapshots.ts:70-74
const vp = new Map<number, VpCell>();
for (const [price, [t, o, i]] of Object.entries(rec ?? {})) {
  vp.set(Number(price), { t, o, i });
}
```

**實測(Node v24)**:group-state 9 檔 = parse 1,026 us + 重建 518 us;
50 檔 = 5,884 + 2,309;150 檔 = 16,293 + 9,216。

**修法**:這一層是 F-06 的**直接受益者** —— 改列式後 `JSON.parse` 就吐出
`[[m,c,v,…],…]`,`minutesFromRecord` / `vpFromRecord` 可以退化成一次 `for` 迴圈
(無 `Object.entries` 中間陣列、無 `Number(k)` 字串轉數字)。單獨改這層收益有限,
**要跟 F-06 綁在一起**。

**風險**:`minutesFromRecord` 的輸出型別(`Map<number, Minute>`)是
`live-last-bar.ts::mergeLiveMinuteBars` 與 `stock-intraday-svg.ts` 的共同入口,
**對外型別不能變**(見 F-06 風險節)。

**effort**:S(綁 F-06)

---

### F-16 [low] 沒有 gzip —— 這是**正確**的,不要加

**位置**:`copycat/server/app.py:1269-1270` 只有 `CORSMiddleware`,無 `GZipMiddleware`。

**這是反向 finding**:後端與前端**跑在同一台 Windows 11 本機**,HTTP 走 loopback。
loopback 頻寬是 GB/s 級,3.3 MB 的傳輸時間 < 3 ms,而 gzip 一份 3.3 MB 要 20–40 ms CPU
(壓縮端)+ 5–10 ms(解壓端)。**加 gzip 會讓 event loop stall 從 19 ms 變成 40+ ms。**

**修法**:不動。同樣建議留一行註解釘住,避免「順手加壓縮」。

**effort**:0

---

## 5. 工具選型:逐一評估

### 5.1 `orjson` —— **不建議全面導入,只在兩個點有條件導入**

| 面向 | 評估 |
|---|---|
| 收益 | 相對 stdlib 約 2–3x(與實測的 pydantic-core 同級或略快) |
| **但** | HTTP 路徑已經是 Rust(F-04),**加 `ORJSONResponse` 反而慢 2.5–3x** |
| | 入站路徑只佔該鏈 18–20%,換 parser 省全鏈 8%(F-07/HP-1) |
| | 出站 WS 路徑 N≈1–2,總量 1.4 ms/s(F-01) |
| 全套換掉的總收益 | **~3 ms / 牆鐘秒 = 0.3% 單核** |
| 代價 | 打破 `dependencies = []` 的 stdlib-only 哲學;Windows wheel 有(無編譯問題);API 差異:`dumps` 回 `bytes`、無 `separators`/`ensure_ascii` 參數、`sort_keys` 要用 `OPT_SORT_KEYS` |
| **硬白名單** | `signal_hub.py:1378` 的回填重寫、`backtest/config.py:136` 與 `fade_config.py:483` 的 `sort_keys` hash、`pipeline.py:239/307/527` 的 `sort_keys` 產物 —— **這些的輸出字面是契約 / cache key,絕不可換** |
| **裁決** | **有條件導入**:只用在 (a) `WsBroadcaster.publish` 的單點序列化(F-01)、(b) `tc4._realtime_msg` 的入站 parse(F-07)。**其餘全部維持 stdlib。** 而且要排在 F-09 之後 —— 先證明 loop 延遲確實被序列化貢獻,再導入。 |

### 5.2 `msgspec` —— **不建議**

| 面向 | 評估 |
|---|---|
| 收益 | `msgspec.json` 在 `Struct` 定義下可達 5–20x(零複製 + 預編譯 schema) |
| **致命阻礙** | TC4 的 REALTIME quote **schema 不固定**:個股 / 期貨 / 指數 / 海外腿的欄位集不同,且官方文件與現版不符(CLAUDE.md §5 已記載「官方文件 51171/51141 與現版不符」)。程式碼**刻意**全走 `.get(key, "")` + 缺欄降級(`parse_realtime` / `parse_stock_realtime` / `_parse_levels` 逐欄如此)。 |
| | 定義 `Struct` = 把「TC4 隨時可能多送 / 少送欄位」這件事變成**啟動即炸或靜默丟欄**。`stock_models.py:213-217` 的 `TradeStatus` 值域外處置(「僅觀測不丟棄」,`design r2-F5`:「丟棄的失效模式 = 處置股整檔靜默消失」)正是這個哲學的成文化。 |
| | `msgspec.json.decode(raw)` 不帶 type 時退化成通用 decoder,速度與 orjson 同級,失去 Struct 的優勢 —— 那就沒有換它的理由。 |
| **裁決** | **不建議**。理由不是效能,是 schema 穩定性。若未來真要上,只能用在**自家產生的 wire**(WS 出站 / 檔案),不能用在 TC4 入站。 |

### 5.3 `msgpack` / 二進位 WS —— **不建議**

| 面向 | 評估 |
|---|---|
| 收益 | 體積約 −30%(相對本 repo 這種短鍵、整數為主的 payload,壓縮率不高);序列化速度與 JSON 的 Rust 實作同級 |
| 代價 | 前端要加 `@msgpack/msgpack`(~30 KB gzip),**且瀏覽器的 msgpack decode 是 JS,比原生 `JSON.parse`(C++)慢 2–5x** —— 實測 `JSON.parse` 1 MB 只要 5.9 ms,JS msgpack 通常 15–25 ms。**前端會變慢。** |
| | DevTools Network / WS frame 從可讀變成二進位 —— 本 repo 的除錯高度依賴「盤中 grep log + 看 WS frame」(CLAUDE.md §1 的驗證表全是 `curl` / `grep`) |
| | CLAUDE.md §4 的 11 條跨檔契約全部是「wire 欄名 / 字面值」語意,改二進位後 golden fixture 對帳方式要重設計 |
| **裁決** | **不建議**。體積不是瓶頸(localhost),而前端解析會變慢。 |

### 5.4 `protobuf` / 自訂 `struct.pack` —— **不建議**

需要固定 schema(同 msgspec 的阻礙)+ codegen 流程 + 前端 runtime,
換來的是體積 −60% 與序列化 5x —— 但這兩者在本系統都不是瓶頸。
唯一可能合理的場景是**未來真的要把 tick 流推給非瀏覽器 consumer(策略引擎)**,
那時應該**繞過 WS 直接走 ZMQ / shared memory**,而不是把 WS 改二進位。

### 5.5 `pydantic-core`(已在 site-packages) —— **已在用,免費**

FastAPI 帶進來的 `pydantic_core.to_json` / `from_json` 就是 Rust serde_json。
如果要導入 Rust 序列化,**它是零新增相依的選項** —— 但 `pydantic_core` 是
FastAPI 的私有相依,直接 import 它等於依賴一個未宣告的傳遞相依。
`pyproject.toml` 的 `live` extras 要顯式加 `pydantic-core` 才算誠實。

### 5.6 `uvloop` —— **Windows 不支援,直接排除**

本專案是 Windows-only(TC4 桌面 app + COM 下單),`uvloop` 只支援 Linux/macOS。
`winloop` 是 Windows 移植版,但與 `pywin32` COM 的 message pump 共存未經驗證 ——
`capital/client.py` 有專屬 COM 執行緒,風險不明。**不建議。**

---

## 6. 具體收益估算(照題目要求)

**現況每秒序列化量(峰值,1 client)**:

| 方向 | 量 | JSON CPU |
|---|---|---|
| 入站 TC4(5 session 共) | ~1,005 則/s × 869 B ≈ **873 KB/s** | **5.0 ms/s** |
| 出站 WS(1 client) | ~232 則/s ≈ **60 KB/s** | **1.4 ms/s** |
| HTTP response(攤平) | ~0.5 發/s ≈ **120 KB/s** | **0.2 ms/s**(已 Rust) |
| 檔案 | 21 KB / 60 s | **0.004 ms/s** |
| **合計** | **~1.05 MB/s** | **6.6 ms/s = 0.66% 單核** |

**換 Rust 序列化器後**:

| 改動 | 省下 | 佔單核 |
|---|---|---|
| 入站 parser → Rust(F-07) | 5.0 → 2.8 ms/s,**省 2.2 ms/s** | 0.22% |
| 出站 WS → Rust + 單點序列化(F-01) | 1.4 → 0.7 ms/s,**省 0.7 ms/s** | 0.07% |
| HTTP(已 Rust) | **0** | 0 |
| **小計** | **省 2.9 ms/s** | **0.29% 單核** |

**再加上 payload 形狀改列式(F-06)**:

| | 現況 | 列式 + Rust | 省 |
|---|---|---|---|
| `/api/stock/group-state` 9 檔 後端 | 1,396 us | **~370 us** | 1.0 ms/發 |
| `/api/stock/group-state` 9 檔 前端(parse+重建) | 1,544 us | **~430 us** | 1.1 ms/發 |
| `light_snapshot` 單檔 序列化 | 252.9 us(std)/ 145.2(Rust) | **66.3 us** | 3.8x / 2.2x |
| WS 傳輸體積 | 22 KB/檔 | **13.8 KB/檔** | −37% |

**換 asdict → `__dict__`(F-03)**:`/api/capital/positions` 0.27 次/s × 幾十列,
省 ~0.03 ms/s(微);但單發最壞(n=400 fills)省 **1.65 ms**,而該端點每 13 s 被打一次。

**總結一句**:
> 全部做完,穩態 CPU 從 0.66% → 0.3% 單核(**省 0.36%,不值得為此改造**);
> 但**單發最壞 event-loop stall 從 18.9 ms → ~5 ms**,
> **前端單發最壞主執行緒 block 從 25.5 ms → ~7 ms**(**這才是值得的部分**)。
> 而在做這些之前,`sys.setswitchinterval`(F-09)的 5 ms GIL 霸佔上界必須先解決,
> 否則上面省下的 ms 在觀測上會被 GIL 抖動蓋掉。

---

## 7. 不要動的地方(反向發現)

| # | 位置 | 為什麼不要動 |
|---|---|---|
| 1 | **所有 HTTP route 的 response class** | FastAPI 0.139.2 的 `dump_json` fast path 已經是 Rust。加 `ORJSONResponse` 會把 fast path 關掉 → **慢 2.5–3x**,且退步零訊號。應加註解 + 一條回歸測試釘住。 |
| 2 | **不要加 `GZipMiddleware`** | 同一台機器走 loopback,gzip 3.3 MB 要 20–40 ms CPU,把 19 ms 的 stall 變成 40+ ms。 |
| 3 | `signal_hub.py:1375-1382` 回填的逐行 bytes 保留 | CLAUDE.md §4 明記 byte 比對契約 + `test_signal_outcome.py` 釘住。**改 parser 時必須把這裡列入硬白名單**(Rust serializer 的浮點字面 / 鍵序與 stdlib 不保證逐字相同)。 |
| 4 | `backtest/config.py:136`、`fade_config.py:483`、`pipeline.py:239/307/527` 的 `sort_keys` | 這些 `json.dumps` 的輸出**是 cache key / hash 輸入**(`sim_hash` / `rows_hash`)。換序列化器 = 所有既有 outcome cache 靜默失效 → 整批回測重跑。 |
| 5 | `data/store.py` 的 1K bar 列式陣列格式 | **已經是正確形狀**(`[m,o,h,l,c,v,up,down,unch]`)。它是 F-06 的先例,不是問題。 |
| 6 | `copycat/engine/` 全部(`lock_quality` / `t1_open`) | 零 IO、零序列化的純狀態機。設計正確。 |
| 7 | `WsBroadcaster.publish` 把同一個 dict 放進 N 條 queue(不複製) | 這部分已經是對的;問題只在序列化發生的**時機**(F-01),不在 publish 本身。 |
| 8 | `msgpack` / `protobuf` / 二進位 WS | 體積不是瓶頸;前端 JS decode 比原生 `JSON.parse` 慢 2–5x;且會摧毀本 repo 高度依賴的「WS frame 可讀 + grep log」除錯路徑。 |
| 9 | `msgspec.Struct` 用在 TC4 入站 | TC4 schema 不固定,程式刻意全走 `.get(k, "")` 降級。定 Struct = 把「多送/少送欄位」變成炸或靜默丟欄。 |
| 10 | `uvloop` | Windows 不支援;`winloop` 與 `pywin32` COM message pump 共存未驗證。 |
| 11 | `breadth_engine._save_streaks`(每日一次,實測檔 524 B) | 量太小,不值得改。只改 `_save`(F-08)。 |
| 12 | 離線 `backtest/` / `replay/` / `data/backfill_*` 的 39 處 json | 全離線,有 outcome cache 保護。JSON 不是回測的瓶頸。 |

---

## 8. 量測方法(要證明快慢該怎麼量)

### 8.1 先量「有沒有問題」,再量「是不是 JSON」

**探針 1:event-loop stall 直接量(最重要)**
```python
# 在 app.py lifespan 起一條 task,不動任何既有 code
async def _loop_lag_probe() -> None:
    import time
    target = 0.010
    while True:
        t0 = time.perf_counter()
        await asyncio.sleep(target)
        lag = (time.perf_counter() - t0 - target) * 1000
        if lag > 5.0:
            logger.warning("event loop lag %.1f ms", lag)
```
盤中跑一天,`grep "event loop lag" logs/server-*.log`。
- 若零命中 → **本區塊的 F-01 / F-05 / F-08 全部不用做**。
- 若命中集中在 `group-state` / `stock/state` 請求的同一秒 → F-05/F-06 成立。
- 若命中散在開盤 5 分鐘且與 HTTP 無關 → **是 F-09 的 GIL,不是 JSON**。

**探針 2:GIL 霸佔(F-09 的判準)**
```
.venv\Scripts\python.exe -m pip install py-spy   # 已裝!site-packages 有 py_spy-0.4.2
py-spy dump --pid <server pid> --locals
py-spy record --pid <server pid> --duration 60 --output open.svg --threads
```
開盤 09:00–09:05 錄一發 flamegraph,看 `_listen_loop` / `parse_stock_realtime` 佔多少、
`json.loads` 佔多少。**這一張圖直接證實或推翻 HP-1 的 18% vs 80% 拆分。**
(py-spy 已在 `.venv`,無需安裝。)

**探針 3:WS 出站序列化量**
```python
# ws.py WsBroadcaster 加兩個計數器(唯讀,同 dropped 慣例)
self.published = 0      # publish 呼叫數
self.fanout = 0         # += len(self._clients)  ← 這才是 json.dumps 次數
```
盤後看 `fanout / published` 的比值 = 實際的 N。若整天 ≈ 1.0,F-01 就是理論問題。

**探針 4:payload 大小分佈**
```powershell
# 不改 code,從外部量
curl -s -w "%{size_download} %{time_total}\n" -o NUL "localhost:8721/api/stock/group-state?codes=..."
curl -s -w "%{size_download} %{time_total}\n" -o NUL "localhost:8721/api/stock/state/2330"
curl -s -w "%{size_download} %{time_total}\n" -o NUL "localhost:8721/api/market/breadth/rows"
```
盤中每 5 分鐘跑一輪,記 size 與 time 的散佈。這會告訴你 `group-state` 實際的 codes 數
(現有 log 已顯示是 7–9,不是 150)。

**探針 5:前端主執行緒 block**
Chrome DevTools → Performance,錄 60 s 群組檢視。找 `fetchGroupState` 的 Long Task。
或用 `chrome-devtools-mcp` 的 `performance_start_trace` / `performance_analyze_insight`。
判準:`group-state` 落地那一幀有沒有 > 16.7 ms 的 Long Task。

### 8.2 改動後的對照判準

| 改動 | 改前記錄 | 改後判準 |
|---|---|---|
| F-09 `setswitchinterval` | 探針 1 的 lag 直方圖 | p99 lag 從 > 5 ms 降到 < 1 ms;吞吐(探針 3 的 published/s)不得掉 > 3% |
| F-01 單點序列化 | 探針 3 的 `fanout/published` | wire 文字**逐字不變**(用 `websocat` 或 DevTools 存兩份 frame 做 diff) |
| F-03 asdict → `__dict__` | `curl -w "%{time_total}"` on `/api/capital/positions` ×100 取 p95 | p95 下降;`tests/capital/` 全綠;response JSON 逐字 diff = 空 |
| F-06 列式 payload | 探針 4 的 size + 探針 5 的 Long Task | size −37%;Long Task 從 8 ms → ~2.5 ms;`vp_parity.json` / `live-last-bar.test.ts` 全綠 |
| F-08 `_save` 搬 thread | 探針 1 每分鐘那一根 spike | 每分鐘的 lag spike 消失 |

### 8.3 微基準(可重跑)

本次用的五支腳本留在 scratchpad,可直接重跑:
```
.venv\Scripts\python.exe <scratchpad>\bench_json.py      # 16 種 payload × 6 種序列化組合
.venv\Scripts\python.exe <scratchpad>\bench_fastapi.py   # FastAPI validate + serialize_json 真實路徑
.venv\Scripts\python.exe <scratchpad>\bench_shape.py     # A/B/C 三種形狀對照
.venv\Scripts\python.exe <scratchpad>\bench_asdict.py    # asdict vs __dict__
.venv\Scripts\python.exe <scratchpad>\bench_inbound.py   # listener thread 全鏈拆解
node <scratchpad>\fe_bench.mjs                            # 前端 JSON.parse + 重建
```
注意本機有明顯 thermal / turbo 抖動(同一支腳本三次重跑,絕對值差 2x),
**只信比值,不信絕對值**;要信絕對值就跑 5 次取中位數。

---

## 9. 建議的執行順序(給改造計畫用)

```
第 0 步(必做,擋掉錯誤的改造)
  ├─ 探針 1 + 探針 2 跑一個交易日 → 拿到 event-loop lag 直方圖與 flamegraph
  └─ 沒有這兩張圖之前,不要動任何一行序列化程式碼

第 1 步(零風險 / 高槓桿,可並行)
  ├─ F-09  sys.setswitchinterval(0.0005)          [S]  ← 量級最大
  ├─ F-03  capital_api 三處 asdict → __dict__     [S]  ← 9x,零契約影響
  ├─ F-04  在 app.py 加註解 + 回歸測試釘住 fast path [S]  ← 防未來踩雷
  ├─ F-16  在 app.py 加註解:不要加 gzip           [S]
  └─ F-08  breadth._save 搬 to_thread             [S]

第 2 步(行為改動,需 user 拍板)
  ├─ F-02  book 訊息加 0.1 s coalesce             [S]  🔴
  └─ F-11  PING 預序列化(F-01 的試驗田)          [S]

第 3 步(架構,前後端同版部署)
  ├─ F-01  WsBroadcaster 單點序列化 + send_text   [M]
  ├─ F-10  watchlist_quote 打包                   [M]  ← 與 F-01 同一次部署
  └─ F-07  tc4 入站走 bytes + Rust parser         [M]

第 4 步(大工程,只在探針證明值得時做)
  └─ F-06  minutes / vp 改列式(additive 過渡)    [L]  ← 本區塊收益最大的單一改動
     └─ F-15 前端重建層一併簡化                   [S]
```

---

## 10. 硬約束清單(改造時必須同動的跨檔契約)

從 CLAUDE.md §4 逐條比對,本區塊的改動會碰到的:

| 契約 | 誰會碰到 | 怎麼同動 |
|---|---|---|
| **WS 心跳契約**(`ws.py::WS_HEARTBEAT_SECS` ↔ `ws-reconnect.ts::WS_SILENCE_TIMEOUT_MS`) | F-01 / F-11 | wire 文字 `{"type":"ping"}` **逐字不變**;只改產生方式不改內容。前端 `isPing` 比 parse 後的 `.type`,不受影響。 |
| **個股 `seq` 的兩個口徑** | F-06(同一份 payload) | `seq` 語意零改動;`minutes` 形狀改變不碰 seq。 |
| **`tape=0` 字面值 + `tape_omitted`** | F-05 / F-06 | 兩個鍵都保留;`tape_omitted` 是 bool,不受形狀影響。 |
| **快照與打包的 seq 對齊(兩道閘)** | F-01 / F-10 | `_flush_ticks()` 在 `snapshot()` / `group_snapshot()` 前呼叫的順序**不可動**;打包序列化改在 `publish` 不改在 `_flush_ticks`。 |
| **`/ws/stock` 入站 `view` 訊息** | F-01(`relay` 的 `on_message`) | `on_message` 回呼吃**文字原文**,與出站序列化正交。加 `send_text` 不影響它。 |
| **VP fold 規則 parity**(`tests/fixtures/vp_parity.json`) | F-06 | fixture 釘的是 **fold 規則**(剔 0 價 / 分鐘窗 / snap_down),不是 wire 形狀。規則不動 = 不紅。**改前要先確認 fixture 內容。** |
| **個股頁即時末根分鐘鍵 +1 / 上限 13:30**(`live-last-bar.ts`) | F-06 / F-15 | 它吃 `accum.minutes`(`Map<number,…>`)。**前端必須在 `minutesFromRecord` 吸收形狀變更、對外仍回 `Map<number,…>`** → `live-last-bar.test.ts` 9 條零改動。 |
| **CDP/MA 前後端同式**(`overlay_parity.json`) | 無 | overlay 端點不在本區塊改動範圍。 |
| **`OrderRecord.unit` / `FillRecord.unit` 字面值** | F-03 | `__dict__` 輸出與 `asdict` 逐字相同,`unit` 值不變。`_fill_code(o.unit, …)` 的判準不受影響。 |
| **`avg_source` / `today_qty` / `PositionKind ⊆ TradeKind` parity** | F-03 | 同上,只換轉 dict 的手段,值域與欄名不變。`test_avg_source_parity_with_frontend` 不紅。 |
| **訊號規則參數 parity**(`signal_param_specs.json`) | 無 | 不在本區塊。 |
| **T+1/T+2 回填原地補欄 + 離線讀者**(byte 比對) | **F-14 硬白名單** | 換 parser 時 `signal_hub.py:1378` 的 `json.dumps` **必須留 stdlib**。 |
| **`sim_hash` / `rows_hash`**(非 CLAUDE.md 但等價) | 換 parser | `backtest/config.py:136` / `fade_config.py:483` / `pipeline.py:239` 的 `sort_keys` dumps **必須留 stdlib**,否則既有 outcome cache 全失效。 |

**Windows 限制**:
- `uvloop` 不可用(Linux/macOS only)。
- `orjson` / `msgspec` / `pydantic-core` 都有 Windows wheel,無編譯問題。
- 後端與 TC4 同機,loopback IO 便宜 → **不要為體積做取捨,要為 CPU 做取捨**。

---

## 11. 未解問題(需 user 回答或需 profile)

1. **非 REALTIME 電文佔入站的多少比例?** 決定 F-07 的 bytes 級預篩值不值得。
   要在 `_realtime_msg` 加一個計數器盤中量一天。
2. **實際同時 client 數**?prod log 只顯示握手次數(10 次 `/ws/stock`),
   不等於同時連線數。需探針 3(`fanout/published`)才知道 F-01 的 N。
3. **`group-state` 的 codes 數會不會漲?** 現況 log 是 7–9 檔;CLAUDE.md 上限 150。
   若使用者實際上不會開 50 張卡,F-06 的收益要打對折。
4. **`/api/stock/state/{code}` 的 ticks 實際筆數分佈?** 7.5 ms 的最壞是 20,000 筆(deque 上限)。
   活躍股整日成交筆數是多少?需盤後量。
5. **開盤 5 分鐘的 TC4 推播真實速率?** 本報告用的 800–2000 則/s 是**推估**,
   需在 `_listen_loop` 加計數器實測。這個數字直接決定 HP-1 與 F-09 的權重。
6. **user 要不要接受閃電梯五檔延遲 0.1 s?**(F-02)這是行為改動,不是我能決定的。
7. **這套系統未來要不要接非瀏覽器 consumer(策略引擎 / 自動下單)?**
   若要,wire format 的選型結論會完全不同(那時該走 ZMQ 二進位繞過 WS,
   而不是把給人看的 WS 改二進位)。
