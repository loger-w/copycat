# X5-memory — 記憶體、配置與長跑穩定性(跨切區塊)

> 掃描範圍:`C:/side-project/copycat/copycat/`(123 個 .py / 37,589 LOC),聚焦
> 「開盤到收盤連續跑 6 小時、處理數百萬 tick 的 process」的記憶體行為。
> 所有數字為 **本機實測**(Python 3.13.13 / Windows 11 / 本 repo 實碼),量測腳本留在
> `scratchpad/bench_*.py`;未實測者一律標「推估」。**未啟動 server、未改動任何 repo 檔案。**

---

## 0. 三個數字先講

| 事實 | 量測值 | 出處 |
|---|---|---|
| 一個交易日 600k 筆個股 tick 進 150 個狀態機,**GC 總開銷 6.9%,單次 full GC 最長 104.6 ms** | gen2 ×3(165 ms 合計)/ gen1 ×26 / gen0 ×292 | `bench_gc4.py` |
| 收盤時 150 檔狀態機常駐 **~170–210 MiB**,加 BarsCache **~100 MiB**,最壞上界 **762 MiB** | 4000 筆/檔 = 1,163 KiB;20,000 筆(deque 上限)= 5.1 MiB | `bench_group.py` / `bench_slots.py` |
| 群組檢視每 60 s 的 `/api/stock/group-state`(150 檔)= **94 ms 同步阻塞 event loop + 17.7 MiB 瞬時配置** | payload 13.7 MiB + JSON 3.4 MiB | `bench_group.py` |

這三件事互相放大:live set 越大 → full GC 越久;full GC 是 **全 process 停頓**(GIL),
同時凍住 event loop、ZMQ listener thread、群益 COM 下單 thread。對一個要下實單的系統,
「在掃單簇 / 鎖板那一刻停 105 ms」正是最不能停的時刻。

---

## 1. 架構地圖(記憶體視角)

### 1.1 一則 TC4 REALTIME 電文的完整生命週期

```
[TC4 桌面 app]
   │ ZMQ PUB tcp://127.0.0.1:<SubPort>
   ▼
tc4.py::_listen_loop            ← 每個 source 一條 daemon thread(共 5 條:txo/stock/index/futures/corr)
   raw = (sock.recv()[:-1]).decode("utf-8")      ① bytes → bytes 切片 → str(全文複製 ×2)
   ▼
tc4.py::_realtime_msg
   msg = json.loads(raw[idx+1:])                  ② 再一次全文切片 + str 版 json.loads
   _note_push(symbol, quote)                      ③ 每則建一個 4 元 str tuple(指紋)
   ▼
stock_source.py::handle_raw
   self._seen.add(symbol)                         ④ 進 threading.Lock
   self._on_message(quote)
   ▼
stock_engine.py::_on_raw_threadsafe
   loop.call_soon_threadsafe(self._handle_quote, quote)   ⑤ Handle 物件 + args tuple + **self-pipe socket send 系統呼叫**
   ═══════════ 跨執行緒邊界,以下全在 event loop ═══════════
   ▼
stock_engine.py::_handle_quote
   parse_stock_realtime(quote)                    ⑥ 3,604 B / 21.66 µs(StockTick + StockBook + StockMeta + 10 個檔位 tuple)
   _observe_trade_status(code, quote)             ⑦ 6.32 µs(datetime.now() + 兩次 strftime,純診斷)
   state.ingest(tick)                             ⑧ 2.26 µs;tick 進 deque(**淨成長 +1 tracked object**)
   _pending_ticks.append({10 鍵 dict})            ⑨ 338 B/筆
   signal_hub.on_tick(code, tick, state)          ⑩ TickContext(每 tick 一個)+ 每條規則一個 list()
   ▼ 0.1 s 後
stock_engine.py::_flush_ticks → ws.py::WsBroadcaster.publish
   同一個 msg dict 放進 N 條 per-client queue        ⑪ **物件共用**,不是 N 份複製
   ▼
ws.py::relay::_send → websocket.send_json(msg)     ⑫ starlette json.dumps → str → bytes
```

**記憶體上重要的結構性事實:**

1. 步驟 ①②:同一則電文在進 parse 前被完整複製 **三次**(bytes 切片 → str decode → str 切片)。
2. 步驟 ⑥:`parse_stock_realtime` 對**每則**訊息(含純簿更新,無成交)都建完整的
   tick/book/meta 三件套 + 10 個 `(價, 量)` tuple —— 3.6 KB。純簿更新佔比在台股高得多
   (五檔一直在動),這些 book/meta 大多**當場丟掉**。
3. 步驟 ⑧:唯一會「淨成長」的一步。`deque.append` 讓 tracked object 數單調上升,
   這才是驅動 GC 的真正力量(見 §3)。
4. 步驟 ⑪:`WsBroadcaster.publish` 把**同一個 dict 物件**放進每條 client queue
   (`ws.py:65-80`),所以 N 個 client 不等於 N 份記憶體 —— 這是既有設計的優點,
   常被誤估成 N 倍。

### 1.2 長駐資料結構清單(全庫掃描結果)

| 結構 | 位置 | 上界機制 | 上界值 | 實測 / 推估佔用 |
|---|---|---|---|---|
| `StockDayState.ticks` | `live/stock_state.py:47` | `deque(maxlen=20_000)` | 20k/檔 | **5.1 MiB/檔**(實測) |
| `StockDayState.minutes` | `live/stock_state.py:46` | 一天的分鐘數 | ~300 格 | ~60 KiB/檔 |
| `StockDayState._vp` | `live/stock_state.py:65` | 當日成交過的檔位數 | ~數十 | <5 KiB/檔 |
| `StockEngine._states` | `server/stock_engine.py:293` | **無**(註解明寫「只增不減」) | 當日曾訂閱 / 曾當主圖的 code 數 | 見 §4 |
| `StockEngine._symbol_to_key` | `server/stock_engine.py:299` | **無**(同上) | symbol 數 | 可忽略 |
| `BarsCache._hist` | `server/bars.py:237` | 只按**日期**剪(today−60d),**code 維度無剪除** | code × 60 日 | **~100 MiB**(實測,150 檔 ×5 日 + 3 期貨 ×30 日) |
| `BarsCache._today` / `_empty` | `server/bars.py:242,251` | TTL + prune | ✅ 有界 | 可忽略 |
| `BarsCache._daily` | `server/bars.py:246` | prune 刪非今日鍵 | ✅ 有界 | ~1 MiB |
| `OverlayCache._store` | `server/overlay.py:52` | **完全無 eviction** | code × 開機天數 | ~1 KiB/格 |
| `CorrState._series` | `live/corr_state.py:55` | 時間戳逐出 + `_cap = 3600` | ✅ 雙重有界 | ~2 MiB(11 腿) |
| `SignalDetector._window/_sweeps/_lookback` | `live/signal_state.py:192,209,210` | 時間窗 popleft + `reset_day()` | ✅ 有界 | 可忽略 |
| `SignalHub._jsonl_queue` / `_discord_queue` | `server/signal_hub.py:406,407` | `maxsize=1000 / 100` + drop-oldest | ✅ 有界 | 可忽略 |
| `SignalHub._discord_sent` | `server/signal_hub.py:415` | 60 s 窗 popleft | ✅ 有界 | 可忽略 |
| `WsBroadcaster` per-client queue | `server/ws.py:127` + `stock_engine.py:55` | `maxsize=1000`,滿丟最舊 | ✅ 有界 | 最壞 **16 MiB 全體共用**(實測) |
| `HandoverBuffer._ticks` | `live/handover.py:26` | `cap=200_000` + 80% 預警 | ✅ 有界 | 可忽略 |
| `OrderStore._orders/_order_seq/_contract_ym` | `capital/store.py:144,145,155` | `clear()`(重連重播時) | 當日單數 | 可忽略 |
| `OrderStore._price_types` | `capital/store.py:149` | **`clear()` 刻意不清** | 開機以來全部送單 | 可忽略(~200 B/筆) |
| `OrderStore._fills` | `capital/store.py:166` | append 時 prune 保留窗 | ✅ 有界 | 可忽略 |
| `BreadthEngine.rows` | `server/breadth_engine.py:197` | 每 10 s **整份取代** | ~4,000 列 | ~2 MiB 常駐 + 2 MiB/10 s 垃圾 |
| `BreadthEngine._series` | `server/breadth_engine.py:221` | 換日清 + 分鐘鍵 | ✅ 有界 | 可忽略 |
| `BreadthEngine._streak_memo` | `server/breadth_engine.py:218` | 武裝時清空 | ✅ 有界(註解已警覺「數百 MB 級」) | — |
| `logs/server-*.log` | `server/__main__.py:143` | **無 rotation、無清理** | 每 session 一檔 | 1.5 MiB/日;24 MiB/79 檔(磁碟) |

**結論:真正無界的只有三個** —— `_states`(日內)、`BarsCache._hist`(code 維度)、
`OverlayCache._store`(完全無界)。其餘全部有界,且守門都寫得相當紮實。
問題不在「洩漏」,在**有界但界太高、而且界上的每個元素都是一個 Python 物件**。

---

## 2. 熱路徑逐條(含量測)

### HP-1 `_handle_quote`(每則 REALTIME,推估 300–1,000 次/秒)

`server/stock_engine.py:1187-1366`。**每則**訊息的固定成本(實測):

| 段 | 時間 | 配置 |
|---|---|---|
| `parse_stock_realtime` | 21.66 µs | 3,604 B |
| `_observe_trade_status`(純診斷) | 6.32 µs | ~300 B |
| `state.ingest` | 2.26 µs | 254 B(**留存**) |
| 打包 item dict | ~1 µs | 338 B(0.1 s 後釋放) |
| `signal_hub.on_tick`(每條規則一次) | 推估 5–15 µs | TickContext + N 個 list |
| **合計** | **~35–50 µs** | **~4.5 KB** |

`bench_gc2.py` 實測純 parse 吞吐 34,545 msg/s(單執行緒、無其他工作)。
加上 ingest / 訊號 / 打包後推估實際上界約 20,000–25,000 msg/s —— 以台股 150 檔的
量級來說**餘裕充足**,CPU 不是瓶頸。**瓶頸是它每秒配置 1.5–4.5 MB,以及其中留存的部分
把 live set 推高到讓 full GC 要跑 100 ms。**

### HP-2 `CorrState.correlations()`(每 1 秒,在 event loop 上)

`server/corr_engine.py:223-230` → `tick_once()` → `state()` → `live/corr_state.py:113-126`。

```python
# live/corr_state.py:91  ← 每腿每秒重建一個 1800 筆的 dict
leg_by_ts = dict(leg_series)
# live/corr_state.py:96-110  ← 每腿每秒走完 1800 個取樣點,產生最多 1800 個 3-tuple
for ts, base_mid in base_series: ...
# live/corr_state.py:111  ← 再整份複製一次
return [row for row in out if row[0] >= now - self._max_window]
# live/corr_state.py:121-122  ← 每窗再各掃一遍,10 腿 × 3 窗 × 2 = 60 次完整掃描
xs = [rb for ts, rb, _ in paired if ts >= cutoff]
ys = [rl for ts, _, rl in paired if ts >= cutoff]
```

**實測(11 腿 / 1800 取樣 / 三窗):`correlations()` = 11.80 ms,單次瞬時配置峰值 436 KB。**
每秒一次 → **event loop 每秒被佔用 11.8 ms(1.2% duty cycle),每秒製造 436 KB 垃圾。**

檔頭註解寫「`statistics.correlation` 對 1800 樣本實測 0.15 ms,整輪 tick 外推不到 1 ms」
—— **那個推算漏掉了 `_paired_returns` 的重建成本**,實測是它宣稱的 12 倍。Pearson 本身確實只
佔一小部分,貴的是每秒把整個 1800×10 的配對序列從頭組一次。

### HP-3 `group_snapshot`(每 60 秒,最多 150 檔,在 event loop 上)

`server/stock_engine.py:838-856` → `live/stock_state.py:237-264`。

實測(150 檔,每檔 4,000 筆 tick / 300 分鐘格):

```
group_snapshot(150) payload in-memory : 13.7 MiB
+ json body                           :  3.4 MiB
peak traced                           : 17.7 MiB
build + encode                        : 94.2 ms   ← 同步阻塞 event loop
```

94 ms 內:沒有任何 tick 被 fanout、沒有 WS ping 被送出、`_flush_ticks` 的 timer 排在後面。
這已經逼近 `WS_HEARTBEAT_SECS = 10 s` 的容錯下緣還遠,但它與 §3 的 105 ms full GC **可以疊加**
—— 兩者恰好撞在一起就是 200 ms 的靜止,而那 200 ms 裡一則成交都不會送到瀏覽器。

`light_snapshot` 本身 0.113 ms / 102 KiB;瓶頸是 ×150 的倍數,以及 `_minutes_payload()`
(`live/stock_state.py:206-219`)每次都把 300 個分鐘格重建成 300 個 7 鍵 dict —— 而
**這 300 格在兩次輪詢之間最多只變動 60 格**。

### HP-4 `_listen_loop` 的字串複製(每則,在 listener thread)

```python
# live/tc4.py:1245
raw = (sock.recv()[:-1]).decode("utf-8")
# live/tc4.py:1195-1199
idx = raw.find(":")
msg = json.loads(raw[idx + 1 :])
```

一則 REALTIME 電文(30+ 欄位,推估 1–2 KB)被複製:`recv()` bytes → `[:-1]` bytes 副本 →
`.decode()` str → `raw[idx+1:]` str 副本 → `json.loads` 再建 dict。推估 4 份 ×1.5 KB ×
450 msg/s ≈ **2.7 MB/s 的純字串搬運**,而 `json.loads` 吃 `str` 比吃 `bytes` 更慢
(內部要再走一次 unicode 路徑)。

### HP-5 `call_soon_threadsafe` 的 self-pipe(每則,跨執行緒)

`server/stock_engine.py:1147-1150`(index / futures / corr 各有一份同型)。
CPython `asyncio/base_events.py:876-884`:`call_soon_threadsafe` 每次都呼叫 `_write_to_self()`,
在 Windows proactor loop 上是一次 socket `send(b'\0')` —— **每則行情一次系統呼叫**。
五條 source 合計推估 1,000–2,500 syscall/s。這不是記憶體問題,但它與記憶體同源:
**沒有批次化,一則一則過橋**。

### HP-6 breadth 每 10 秒的全市場重算(在 event loop 上)

```python
# server/breadth_engine.py:528-529  ← 取數在 to_thread,但這兩行在 loop 上
universe = assemble_universe(rows, self._sector_map, self._disposition)
breadth  = compute_breadth(universe, self._type_map, self._name_map)
...
# server/breadth_engine.py:565
self.rows = breadth["rows"]          ← ~4,000 個新 dict,舊的整份丟掉
...
# server/breadth_engine.py:956  ← _save():同步 write_text + os.replace,在 loop 上
```

09:00–13:40 共 ~1,650 輪。每輪:json.loads 一份 1–2 MB 回應(在 thread)+ 在 loop 上對
4,000 列做四次 list comprehension + 產生 4,000 個新 dict + 一次同步檔案寫入。
推估每輪 loop 佔用 15–40 ms、垃圾 2–4 MB(= 200–400 KB/s)。

---

## 3. GC 壓力 —— 本區塊最重要的發現

### 3.1 全庫零 GC 調參

```
$ grep -rn "import gc|gc.(freeze|disable|collect|set_threshold)" copycat/
(無輸出)
```

`gc.get_threshold()` = `(2000, 10, 10)`(3.13 預設)。沒有 `gc.freeze()`、沒有調 threshold、
沒有在熱路徑停用 GC、沒有任何 GC 可觀測性。

### 3.2 一個關鍵的反直覺事實(先講清楚,免得誤導後續決策)

`bench_gc3.py` 實測:**20 萬次 `parse_stock_realtime`(每次配置 3.6 KB 後立刻釋放)
觸發了 0 次 GC。** 原因是 CPython 的 gen0 計數器是「配置數 **減** 釋放數」,
純粹的短命垃圾靠 refcount 當場回收,根本推不動門檻。

所以 **「每 tick 建 20 個物件」本身不製造 GC 壓力**。製造壓力的是
**存活下來的那一個** —— `state.ticks.append(tick)`(`live/stock_state.py:148`)。

### 3.3 實測:一個交易日的 tick 流

`bench_gc4.py` —— 600,000 筆 tick 進 150 個 `StockDayState`(= 150 檔 × 4,000 筆):

```
ingest 600000 ticks in 4.0s
  gen0:  292 次, 合計  49 ms, max   1.7 ms
  gen1:   26 次, 合計  65 ms, max   4.6 ms
  gen2:    3 次, 合計 165 ms, max 104.6 ms     ← 全 process 停頓
  GC 佔整段 6.9%
```

**gen2 停頓與 live set 大小的關係**(`bench_eod.py` / `bench_gc.py`):

| live set | tracked objects | full GC 停頓 |
|---|---|---|
| 空白 process | 12,935 | 0.8 ms |
| 150 檔 × 4,000 tick | 657,036 | **84.4 ms** |
| 150 檔(10 檔滿 20k)| 821,283 | **103 ms** |
| 上面 + BarsCache 100 MiB | 822,096 | **117 ms** |

注意第三、四列:BarsCache 加了 268,500 個 `Bar` dict,tracked 只 +813 —— 因為
**只含純量的 dict 在一次 collection 後會被 CPython 取消追蹤**。所以 BarsCache 吃記憶體
但**不吃 GC**。吃 GC 的是 `StockTick` —— Python class 的 instance **永遠被追蹤**,
無論有沒有 `__slots__`。

### 3.4 為什麼這對「下實單」是紅線

full GC 持有 GIL。104 ms 停頓期間同時凍住:
- event loop(WS fanout、`_flush_ticks` timer、FastAPI route)
- 5 條 `_listen_loop` thread(ZMQ 收不了新電文,只是塞在 socket buffer)
- 群益 COM 下單執行緒(`capital/com.py`)
- 5 條 `_heal_loop` watchdog

而 gen2 的觸發時機**完全由配置節奏決定,不可預測** —— 開盤那一分鐘的 tick 洪峰
正是最可能觸發它、也是最不能停的時刻。

### 3.5 `gc.freeze()` 的效益(實測,誠實結論)

`bench_gc.py`:對「已建好的 150 檔狀態機」呼叫 `gc.freeze()` 後,gen2 從 84.4 ms → **0.0 ms**。

**但這在 prod 是假的收益**:`gc.freeze()` 只把**呼叫當下**已存在的物件移出掃描,
盤中新 append 的 tick 不受保護。boot 時 freeze 只能凍住 import 出來的 module / class /
常數(~13k 物件,本來就只值 0.8 ms)。

真正可行的組合是 §6 的 **(a) 欄式 tape** 或 **(b) 週期性 freeze**(每小時
`gc.collect(); gc.freeze()` 把當時的 tick 存量整批凍住)—— 後者是 hack,
且會讓「換日 reset 掉的舊 state」永遠不被回收,要配 `gc.unfreeze()` 使用。

---

## 4. 記憶體佔用估算(實測基礎)

### 4.1 單價表(全部實測)

| 物件 | 實測大小 |
|---|---|
| `StockTick`(現況 dataclass,含 unique `time` str) | **254 B** |
| `StockTick` 若加 `slots=True` | 206 B(−19%) |
| `StockTick` 若改 NamedTuple | 222 B(−13%) |
| `Bar`(TypedDict = plain dict,6 鍵) | **400 B** |
| `StockDayState` @4,000 tick(全含) | **1,163 KiB** |
| `StockDayState` @20,000 tick(deque 上限) | ~5.1 MiB(外推) |
| `light_snapshot()` 回值 @300 分鐘格 | **102 KiB** |
| `snapshot(tape=True)` 回值 @6,000 tick | **1,740 KiB** |
| `ticks` 打包訊息(50 item) | **16.9 KiB** |
| `parse_stock_realtime` 一則的瞬時配置 | **3,604 B** |

### 4.2 收盤時的 process 估算

| 項目 | 估算 |
|---|---|
| Python + FastAPI + uvicorn + pyzmq baseline | 60–80 MiB(推估) |
| 150 檔 `StockDayState`(140 檔 ×4k + 10 檔 ×20k = 760k tick) | **~200 MiB** |
| `BarsCache._hist`(150 檔 ×5 日 1K + 3 期貨 ×30 日 allday) | **~100 MiB**(實測) |
| `CorrState` 11 腿 ×1,800 | ~2 MiB |
| breadth `rows` 4,000 列 + 對照表 | ~5 MiB |
| index / futures / river / capital / signal | <10 MiB |
| **合計常駐** | **~380–400 MiB** |
| 瞬時峰值(group_snapshot 撞上 WS 隊列滿) | **+34 MiB** |

### 4.3 最壞上界(結構允許的天花板)

- 150 檔全部撞滿 `_TICKS_MAXLEN = 20_000`:150 × 5.1 MiB = **762 MiB**(僅 tick tape)
- 使用者一天點過 400 檔(主圖切換都會 `_states.setdefault`,`stock_engine.py:461,472`,
  **且永不移除**):400 × 平均 1 MiB = **400 MiB**
- `BarsCache._hist` 對應 400 檔 ×5 日 = **175 MiB**

**結構上沒有任何機制擋得住 1 GB+。** 這對本機看盤或許可忍,但對「要下實單、不能停」
的系統,一次 Windows 分頁換出就是幾百毫秒。

---

## 5. Findings

> 嚴重度以「對下實單系統的延遲/穩定性衝擊」計,不是以工程量計。

### X5-01 [critical] tick tape 用 Python 物件存,一天 76 萬個 instance 把 full GC 推到 105 ms

- **位置**:`copycat/live/stock_state.py:47`、`:148`;`copycat/live/stock_models.py:46-61`
- **熱路徑**:是(每 tick)
- **證據**:
  ```python
  # live/stock_state.py:19,47
  _TICKS_MAXLEN = 20_000
  ticks: deque[StockTick] = field(default_factory=lambda: deque(maxlen=_TICKS_MAXLEN))
  # live/stock_state.py:148
  def _apply(self, tick: StockTick) -> None:
      self.ticks.append(tick)
  # live/stock_models.py:46  ← 注意:沒有 slots
  @dataclass(frozen=True)
  class StockTick:
      code: str; price_milli: int; qty: int; cum_vol: int; time: str; ...
  ```
  對照:`copycat/backtest/`、`copycat/engine/`、`copycat/data/` 裡**離線**用的 dataclass
  全部有 `slots=True`(18 處),**線上熱路徑的三個 model 一個都沒有**。這是反過來的。
- **影響**:600k tick → 657k tracked object → gen2 **104.6 ms 全 process 停頓**,
  GC 佔 CPU 6.9%;常駐 200 MiB,結構上界 762 MiB。
- **修法**:把 `ticks` 從「物件序列」改成**欄式 tape**。實測對照(`bench_columnar.py`,
  **stdlib-only、零新相依**):
  ```
  現況(600k StockTick)  : 145 MiB, gen2  79–105 ms, tracked 613,401
  array.array 欄式 tape   :  12.8 MiB, gen2    0.4 ms, tracked   9,416
                            ↑ 記憶體 11×、GC 停頓 200× 改善
  ```
  形狀:
  ```python
  class ColumnTape:
      __slots__ = ("t","p","q","side","b","a","n")
      # t: array("i") 自午夜毫秒 / p,q,b,a: array("i") 毫元與張數 / side: array("b") −1|0|1
  ```
  進階版用 numpy 預配置固定長度 array + 寫入游標(ring buffer),連 `array.append`
  的攤提成本都省掉,而且 VWAP / VP / minutes 可以直接向量化。
- **風險 / 契約**:
  - `snapshot()` 的 `ticks` **wire 形狀不可變**(CLAUDE.md §4「個股 `seq` 的兩個口徑」:
    前端 `lib/stock-accum.ts::fromSnapshot` 靠 `snap.seq` **由尾回推**指派 React key)。
    欄式只換內部儲存,`snapshot()` 在出口才展開成現有的 dict 列表 → wire 零改動。
  - `apply_backfill`(`stock_state.py:98-139`)的 survivor 篩選 `[t for t in self.ticks
    if t.cum_vol > backfill_max]` 要改成欄式掃描;它那段「兩個迴圈去重不對稱是刻意」
    的語意必須逐字保留(改了會動張數/內外盤累積值)。
  - `signal_hub.on_tick(code, tick, state)` 收的是 `StockTick` 物件 —— 這一個仍然要建
    (每 tick 一個,短命、當場釋放,不進 GC 統計)。只有**存進 tape 的那一份**改欄式。
- **工作量**:L(`stock_state.py` 全改 + `stock_engine`/`signal_hub` 邊界 + vp_parity fixture 重跑)

### X5-02 [critical] `group_snapshot` 每 60 秒同步阻塞 event loop 94 ms、瞬時配置 17.7 MiB

- **位置**:`copycat/server/stock_engine.py:838-856`;`copycat/live/stock_state.py:206-264`
- **熱路徑**:每 60 s × 最多 150 檔
- **證據**:
  ```python
  # server/stock_engine.py:838-855
  self._flush_ticks()
  out: dict[str, dict] = {}
  for code in codes:                                 # ← 最多 150 圈,全同步
      light = state.light_snapshot() if ... else dict(_EMPTY_LIGHT)
      out[code] = {**light, "no_data": ..., "backfilling": ...}
  # live/stock_state.py:206-219  ← 每次把 300 個分鐘格重建成 300 個 7 鍵 dict
  return {str(k): {"c":…, "v":…, "i":…, "o":…, "u":…, "h":…, "l":…}
          for k, m in sorted(self.minutes.items())}
  ```
  實測:payload 13.7 MiB + JSON 3.4 MiB,**build+encode 94.2 ms**。
- **影響**:每分鐘一次 94 ms 的完全靜止(WS 不推、ping 不送、成交不 fanout);
  瞬時 +17.7 MiB 讓 allocator 去跟 OS 要新 arena,釋放後 RSS 多半不還。
  與 §3 的 105 ms full GC 可疊加成 ~200 ms。
- **修法**(三段,由淺到深):
  1. **增量 minutes**:payload 帶 `since` 參數,只回「上次輪詢之後有變動的分鐘格」。
     兩次輪詢之間最多變 60 格,payload 直接掉一個數量級。
  2. **快取 `_minutes_payload()`**:`MinuteAgg` 變動時標 dirty,未變動的格重用上次的 dict
     (dict 是不可變地被送出去的,可安全共用)。
  3. **序列化改 `orjson`/`msgspec`**:3.4 MiB 的 JSON,orjson 比 stdlib 快 3–5×,
     而且直接出 bytes、省掉 str 中繼。
- **風險 / 契約**:`light_snapshot()` 的鍵名是 CLAUDE.md §4 明列的**單一定義**
  (讀者 = 前端 `useGroupSnapshots` + `lib/stock-accum.ts`);`vp` 的折疊規則由
  `tests/fixtures/vp_parity.json` 兩側釘住。加 `since` 是 additive,舊前端不帶就拿全量。
- **工作量**:M(方案 1+2)/ S(方案 3 單獨做)

### X5-03 [high] `CorrState.correlations()` 每秒重建整個配對序列:11.8 ms / 436 KB,而檔頭宣稱「不到 1 ms」

- **位置**:`copycat/live/corr_state.py:82-126`;呼叫點 `copycat/server/corr_engine.py:223-230,543`
- **熱路徑**:每 1 秒
- **證據**:
  ```python
  # live/corr_state.py:91   每腿每秒重建 1800 entry 的 dict
  leg_by_ts = dict(leg_series)
  # live/corr_state.py:111  組完再整份複製過濾一次
  return [row for row in out if row[0] >= now - self._max_window]
  # live/corr_state.py:121-122  10 腿 × 3 窗 × 2 = 60 次 1800 長度的 list comprehension
  xs = [rb for ts, rb, _ in paired if ts >= cutoff]
  ys = [rl for ts, _, rl in paired if ts >= cutoff]
  ```
  檔頭(`corr_state.py:5-7`)寫「`statistics.correlation` 對 1800 樣本實測 0.15 ms,
  整輪 tick 外推不到 1 ms」。**實測 11.80 ms —— 是宣稱的 12 倍**,因為那個推算只算了
  Pearson、沒算 `_paired_returns` 的重建。
- **影響**:event loop 每秒被佔 11.8 ms;每秒 436 KB 垃圾(一天 ~7 GB 的配置流量)。
- **修法**:
  - **最小改動**:`_paired_returns` 改成**增量維護** —— 每秒 push 時只算一筆新的
    `(ts, rb, rl)` 推進一個 per-leg 的 deque(時間戳逐出),`correlations()` 不再重建。
    O(1800×10) → O(10)。檔頭「整批重算避免浮點誤差累積」那條理由**只適用於增量
    Pearson 統計量**(Σx, Σx², Σxy),對「增量維護配對序列、Pearson 仍整批算」不成立
    —— 後者的數值結果與現況逐位元相同。
  - **進階**:numpy。`_series` 改 `np.ndarray` ring buffer,`np.corrcoef` 對 1800×2
    是微秒級,三個窗用 slice 直接切。11.8 ms → 推估 <0.3 ms。
- **風險**:`corr` 的值會進 WS payload 給前端;改法 1 逐位元同值,改法 2 有 float64 vs
  `fsum` 的末位差異(`statistics.correlation` 內部用 fsum)。若要上 numpy,需要一條
  golden fixture 釘住兩者在測試資料上的差 < 1e-12。
- **工作量**:S(改法 1)/ M(改法 2)

### X5-04 [high] `StockEngine._states` 與 `BarsCache._hist` 沒有 code 維度的淘汰

- **位置**:`copycat/server/stock_engine.py:293,461,472`;`copycat/server/bars.py:237,336-359`
- **熱路徑**:否(但決定 live set 大小 → 決定 §X5-01 的 GC 停頓)
- **證據**:
  ```python
  # server/stock_engine.py:297-299(註解自陳)
  # 只增不減(同 `_states`):退訂後殘留的鍵指向仍存在的 state …
  self._symbol_to_key: dict[str, str] = {}
  # server/stock_engine.py:461,472  每次 _acquire / set_main 都 setdefault,無對應的 pop
  self._states.setdefault(code, StockDayState())
  # server/bars.py:339-346  prune 只按日期,code 維度無剪除
  floor = (today - _dt.timedelta(days=DAYS_MAX * 2)).isoformat()
  for key in [k for k in self._hist if k[1] < floor]:
      del self._hist[key]
  ```
  `bars.py:339` 的註解說「`_hist` / `_daily` 的成長來自**日期維度**(股號受 watchlist
  50 檔上限約束)」—— **上限自 2026-09-01 起已是 150**(CLAUDE.md §4),而且
  `_hist` 的鍵根本不是 watchlist 成員,是**任何被畫過圖的 code**(主圖切換、群組檢視、
  盤前篩選那 60 檔)。註解的前提已經不成立。
- **影響**:使用者一天點過 400 檔 → `_states` 400 格(推估 400 MiB)+ `_hist` 175 MiB,
  而且每一個死掉的 `StockDayState` 裡的 tick 都還在被 gen2 掃描。
  rollover stage2(`stock_engine.py:1103`)會 reset 全部 state,所以這是**日內**成長,
  換日歸零 —— 但一天就夠把 gen2 從 84 ms 推到 200 ms+。
- **修法**:
  - `_states`:改 LRU。保留 = 自選全員 ∪ 主圖 ∪ 各連線的 `_views` 聯集 ∪ 最近 N 個;
    其餘 evict。淘汰點掛在既有的 `_flush_watchlist_loop`(1 s)或 checkpoint(60 s)。
  - `BarsCache._hist`:加 per-code LRU(記最後存取時刻,超過 N 分鐘未被查就整組刪),
    或至少把 code 數上限做出來。**必須保留** `put_hist_range` 的
    「負向快取只寫到有證據掃過的最後一天」(`bars.py:266`,review P1-2)與
    `MIDNIGHT_BUFFER_END` 午夜緩衝(`bars.py:685-695`,TZ-2)。
- **風險**:evict 掉還在用的 state = 該檔前端的 accum 與後端 seq 斷掉。安全做法是
  **只 evict 不在任何持有者集合裡的 code**,並讓下一次請求走 `_EMPTY_LIGHT` +
  `_backfill_wanted` 自然重建(那條路已經存在且測過)。
- **工作量**:M

### X5-05 [high] 全庫零 GC 調參、零記憶體可觀測性

- **位置**:全庫(`grep -rn "import gc" copycat/` 零命中);`copycat/server/app.py` health endpoint
- **熱路徑**:否
- **證據**:
  ```python
  # server/app.py  health() 的全部內容
  return request.app.state.build.as_dict()   # 只有 git_sha 等建置身分
  ```
  `/api/health` 的 docstring 明寫「刻意不含引擎健康度」。結果是:
  **一個要跑 6 小時的 process,沒有任何管道可以知道自己吃了多少記憶體、GC 停了多久。**
  `WsBroadcaster.dropped` / `window_dropped`(`ws.py:56-62`)是全庫唯一的壓力指標,
  而且刻意不進 `/api/health`。
- **影響**:本報告的所有數字都是**離線 bench 推估**,沒有一個是 prod 實錄 —— 這本身
  就是問題。真正的 tick 速率、真正的 RSS、真正的 GC 停頓分佈都是未知數。
- **修法**(見 §8 完整方案):
  - `gc.callbacks` 記 full GC 停頓(成本近零),max > 50 ms 印固定字串 WARNING
    (沿專案「可 grep 判準」慣例,例如錨「GC 停頓」)。
  - 每 5 分鐘一行 INFO:RSS(`ctypes` 呼 `K32GetProcessMemoryInfo`,零相依)、
    `len(gc.get_objects())`、`len(engine._states)`、Σ`len(state.ticks)`、
    `bars_cache` 三個 dict 的條目數。
  - boot 後 `gc.freeze()`(凍住 import 出來的 ~13k 物件;收益小但零風險零成本)。
- **風險**:極低。`gc.callbacks` 只在 collection 前後各呼叫一次。
- **工作量**:S

### X5-06 [medium] `parse_stock_realtime` 對純簿更新也建完整三件套,3.6 KB/則

- **位置**:`copycat/live/stock_models.py:188-235`;呼叫點 `copycat/server/stock_engine.py:1204`
- **熱路徑**:是(每則,含無成交的簿更新)
- **證據**:
  ```python
  # live/stock_models.py:197-210  book 與 meta 無條件先建
  book = StockBook(bids=_parse_levels(msg,"Bid","BidVolume"),
                   asks=_parse_levels(msg,"Ask","AskVolume"))   # 10 個 tuple
  meta = StockMeta(name=…, ref_milli=…, upper_milli=…, …)        # 8 欄
  …
  # live/stock_models.py:218  才判斷有沒有成交
  if price is None or qty is None or qty <= 0:
      return None, book, meta
  ```
  實測 3,604 B / 21.66 µs 每則。
- **影響**:台股純簿更新佔比高(五檔一直在動);推估 300–1,000 則/s → **1.1–3.6 MB/s
  純垃圾**。不驅動 GC(§3.2),但吃 allocator 與 CPU,而且在 event loop 上。
- **修法**:
  - `StockBook` / `StockMeta` / `StockTick` 三個都加 `slots=True`(零行為改動,
    實測省 19%,而且 attribute 存取更快)。
  - `_parse_levels` 的 10 個 tuple 改成兩條 `array("i")` 或一個扁平 tuple。
  - meta 只在**值變了**才重建(現況 `_handle_quote:1247-1251` 本來就已經在比
    `(upper, lower) != prev_limits`,可以順勢把整個 meta 做成 dirty-check)。
- **風險**:`StockMeta` 有一欄 `y_close_milli` 註解寫「刻意保留:目前無消費者」
  —— 不要順手砍。`slots=True` 對 `dataclasses.replace`(`stock_models.py:143,145`)相容。
- **工作量**:S(slots)/ M(dirty-check meta)

### X5-07 [medium] 每則行情的字串三度複製 + `json.loads(str)`

- **位置**:`copycat/live/tc4.py:1245`、`:1195-1199`
- **熱路徑**:是(每則,listener thread)
- **證據**:
  ```python
  # live/tc4.py:1245
  raw = (sock.recv()[:-1]).decode("utf-8")      # bytes → bytes 副本 → str
  # live/tc4.py:1195-1199
  idx = raw.find(":")
  msg = json.loads(raw[idx + 1 :])              # 再一份 str 副本
  ```
- **影響**:推估 ~1.5 KB × 4 份 × 450/s ≈ 2.7 MB/s 純搬運;`json.loads(str)` 比
  `json.loads(bytes)` 慢。
- **修法**:
  ```python
  buf = sock.recv()                    # bytes,不切
  i = buf.find(b":")
  msg = json.loads(memoryview(buf)[i+1:-1])     # stdlib json 吃 bytes/bytearray
  ```
  或直接上 `orjson.loads`(吃 bytes,推估 2–4× 快)。
- **風險**:`handle_raw(raw: str)` 是**四個子類共用**的介面(`tc4.py:1213-1224` docstring
  明寫「子類覆寫這一支即可共用整個 `_listen_loop`」),簽名改 bytes 要同時改
  `stock_source` / `index` / `futures` / `corr` 四份 + 它們的測試。
- **工作量**:M

### X5-08 [medium] `_observe_trade_status` 是純診斷,卻在每則行情上花 6.3 µs + 兩次 strftime

- **位置**:`copycat/server/stock_engine.py:1222,1368-1430`、`:92-99,151-162`
- **熱路徑**:是(每則非期貨行情)
- **證據**:
  ```python
  # server/stock_engine.py:1222  無條件呼叫
  self._observe_trade_status(code, quote)
  # :1402 → :162 → :99
  def _now_taipei_time() -> str:
      return f"{_dt.datetime.now():%H:%M:%S.%f}"[:-3]     # datetime + strftime + 兩個 str
  ```
  實測 `_now_taipei_time()` 4.36 µs、`_observe_window_now()` 6.32 µs。
  其 docstring 自陳「本輪**不據此判定任何狀態**……只留可 grep 的紀錄」。
- **影響**:推估 2.8 ms/s 的 loop 時間 + ~150 KB/s 垃圾,換一個一天只有幾則輸出的 log。
- **修法**:窗判定改成「每秒算一次快取」而不是每則算一次 —— 窗邊界只有 4 個時刻
  (08:30/09:00/13:25/13:30),`_observe_window_now` 的結果在一秒內恆定。
  或把整個觀測掛到 `_flush_watchlist_loop` 的 1 s 拍上(只在 `_trade_status` 有變時記)。
- **風險**:`_TRADE_STATUS_FMT` 的 grep 前綴與格式是蒐證契約(`stock_engine.py:126-131`),
  格式不可改;只改「什麼時候算窗」。`_OBSERVE_GRACE_SECS = 2` 的秒級語意要保住。
- **工作量**:S

### X5-09 [medium] `breadth` 每 10 秒在 event loop 上重算 4,000 列 + 同步落檔

- **位置**:`copycat/server/breadth_engine.py:528-529,565,594,956-975`
- **熱路徑**:每 10 s(09:00–13:40,~1,650 輪/日)
- **證據**:
  ```python
  # :528-529  取數在 to_thread,但這兩個純函式在 loop 上
  universe = assemble_universe(rows, self._sector_map, self._disposition)
  breadth  = compute_breadth(universe, self._type_map, self._name_map)
  # :565
  self.rows = breadth["rows"]        # ~4,000 個新 dict 取代舊的
  # :594 → :956  同步 write_text + os.replace,在 loop 上
  self._save()
  ```
  `market_breadth.py` 裡 `assemble_universe`(:236-257)是三次全表 list comprehension,
  `compute_breadth`(:306+)再一次。
- **影響**:推估每輪 15–40 ms loop 佔用、2–4 MB 垃圾(200–400 KB/s)。
- **修法**:整段(parse + assemble + compute)搬進同一個 `to_thread`,只把結果 dict
  回到 loop;`_save()` 也丟 thread。若引入 numpy/polars,4,000 列的統計是微秒級。
- **風險**:`self.rows` / `self._series` / `self._trade_date` 的寫入目前在 loop 上是天然
  serialized;搬進 thread 後要把「純計算」與「狀態寫入」切開(計算在 thread、
  寫入回 loop)。`_apply` 裡「日期變更三分法」(:546-560,review P1-1)那段是狀態機,
  必須留在 loop。
- **工作量**:M

### X5-10 [medium] WS 慢 client 的隊列最壞 16 MiB;丟包判準有但無記憶體判準

- **位置**:`copycat/server/ws.py:53-119,127`;`copycat/server/stock_engine.py:55`
- **熱路徑**:否(但在瀏覽器分頁被節流時常態發生)
- **證據**:
  ```python
  # server/stock_engine.py:55
  _CLIENT_QUEUE_MAX = 1000
  # server/ws.py:127
  queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=self._maxsize)
  ```
  實測:一則 50-item `ticks` 打包 = 16.9 KiB → 1,000 深 = **16.1 MiB**。
- **影響**:**好消息是這 16 MiB 是全體共用的**(`publish` 把同一個 dict 放進每條
  queue,`ws.py:67`),所以 8 條連線不是 128 MiB。但 16 MiB 的隊列意味著
  「最舊的那則已經在 100 秒前」—— CLAUDE.md §4 說「per-client queue 1000 撐 100 s」,
  這個設計意圖正確,只是沒人量過它的**記憶體**代價。
- **修法**:不動政策(丟最舊保最新是對的),只加觀測:`/api/health` 或 5 分鐘 INFO
  帶各 broadcaster 的 `max(queue.qsize())`。若要降記憶體,把 `maxsize` 從 1000 降到
  300(= 30 s 緩衝)並依賴前端既有的 seq 跳號自癒(`lib/stock-accum.ts`)。
- **風險**:降 maxsize = 改 CLAUDE.md §4 記載的「撐 100 s」前提,要同時更新該條文字
  與 `grep "佇列滿"` 判準的預期頻率。
- **工作量**:S

### X5-11 [low] `OverlayCache._store` 完全沒有 eviction

- **位置**:`copycat/server/overlay.py:52-60`
- **證據**:
  ```python
  class OverlayCache:
      def __init__(self) -> None:
          self._store: dict[tuple[str, str], dict] = {}
      def put(self, code, today, value) -> None:
          if value.get("cdp") is None and …: return
          self._store[(code, today)] = value          # 沒有任何 pop / prune
  ```
- **影響**:key 是 (code, 日期),跨日不清。~1 KiB/格。150 檔 × 250 交易日 = 37 MiB/年。
  本機每天重啟 server 所以實務上看不到,但結構上是真的無界。
- **修法**:仿 `BarsCache.prune`,put 時刪掉非今日的鍵(三行)。
- **工作量**:S

### X5-12 [low] `OrderStore._price_types` 刻意永不清空

- **位置**:`copycat/capital/store.py:149`、`:623-626`
- **證據**:
  ```python
  # :624-626 docstring
  """`_price_types` **不清**:它是送單意圖不是回報事件,重播不會重建它 ——
     清掉等於本 app 送出的市價單在重連後全體失標。"""
  ```
- **影響**:每筆送單 ~200 B,永不釋放。一天 500 單 = 100 KB。**這個取捨是對的**
  (正確性 > 100 KB),只是記帳上要知道它存在。
- **修法**:加一條「日期比當前交易日早兩天以上就刪」的 prune —— 候選日欄位
  (`tuple[str, ...]`)本來就帶日期,判得出來。低優先。
- **工作量**:S

### X5-13 [low] `logs/` 無 rotation 無清理

- **位置**:`copycat/server/__main__.py:143`
- **證據**:`logging.basicConfig(level=logging.INFO, format=…)` —— 無 handler 設定,
  輸出導向由 `run.ps1` 接。實況:`logs/` 79 個檔 24 MiB,單日最大 1.5 MiB。
- **影響**:磁碟,不是 RAM。但長跑診斷靠 `grep logs/server-*.log`(CLAUDE.md 多條判準),
  檔案越多越慢。
- **修法**:`RotatingFileHandler` 或 run.ps1 加保留 30 日的清理。
- **工作量**:S

### X5-14 [low] `SignalDetector.evaluate` 每 tick 建 6 個 list

- **位置**:`copycat/live/signal_state.py:325-332`;`copycat/server/signal_hub.py:607-614`
- **證據**:
  ```python
  # live/signal_state.py:325-331
  events: list[SignalEvent] = []
  events.extend(self._eval_cdp(...))        # 每個 _eval_* 都 return 一個新 list
  events.extend(self._eval_surge(...))      # 絕大多數時候是 []
  events.extend(self._eval_pullback(...))
  events.extend(self._eval_volume(...))
  events.extend(self._eval_limit_tick(...))
  # server/signal_hub.py:609  再包一層
  events = list(slot.detector.evaluate(code, tick, ctx, slot.enabled))
  ```
- **影響**:每 tick 每條規則 7 個 list 物件(絕大多數是空的)。N 條規則 × 450 tick/s。
  推估 ~300 KB/s。CPython 對空 list 沒有 interning。
- **修法**:`_eval_*` 無事件時回模組級的 `_NO_EVENTS: tuple = ()`,`evaluate` 用
  `if evs: events.extend(evs)`;`signal_hub:609` 的 `list()` 拿掉(evaluate 已回 list)。
- **風險**:`_fanout` 對 `events` 只做 `for event in events`,回 tuple 相容。
  型別註記要從 `list[SignalEvent]` 放寬成 `Sequence[SignalEvent]`。
- **工作量**:S

### X5-15 [low] `call_soon_threadsafe` 每則行情一次 self-pipe syscall

- **位置**:`copycat/server/stock_engine.py:1147-1150`(index/futures/corr 各一份同型)
- **證據**:CPython `asyncio/base_events.py:876-884` —— `call_soon_threadsafe` 末尾
  無條件 `self._write_to_self()`,Windows proactor loop 上是一次 socket send。
- **影響**:推估 1,000–2,500 syscall/s(五條 source)。不是記憶體問題,但同源於
  「一則一則過橋」的設計,而且每次多一個 `Handle` 物件 + args tuple。
- **修法**:listener thread 端先在自己的 lock-free ring 裡累積,每 N 則或每 X ms
  才 `call_soon_threadsafe` 一次交一整批。與既有的 `_pending_ticks` 0.1 s 打包
  (`stock_engine.py:1320-1343`)是同一個想法,只是把它往上游再推一層。
- **風險**:跨執行緒批次要小心 `_handle_quote` 裡的 rollover 快路徑
  (`stock_engine.py:1259-1292`)—— 那段假設「一則一則依序處理」,批次化後仍是依序,
  但延遲上界從 0 變成 X ms,要確認 stage2 的 15 分鐘窗不受影響(不受)。
- **工作量**:M

---

## 6. 工具選型建議與取捨

| 工具 | 用在哪 | 解決什麼 / 預期收益 | 代價 | 建議 |
|---|---|---|---|---|
| **`array.array`(stdlib)** | `live/stock_state.py` 的 tick tape | 記憶體 145 MiB → 12.8 MiB;gen2 105 ms → 0.4 ms(實測) | 零新相依、不破 stdlib-only 哲學;code 要自己管游標 | **強烈建議導入**(X5-01 的最小可行解) |
| **numpy** | tick tape(ring buffer)、VP/VWAP/minutes 聚合、`corr_state` 的 Pearson、`market_breadth` 的全表統計 | 比 `array.array` 再快一個量級;`corr` 11.8 ms → 推估 <0.3 ms;VP/minutes 可向量化 | **打破 `dependencies = []`**;Windows wheel 沒問題;+40 MB 安裝體積、+15 MB import 後 RSS | **有條件導入** —— 只給 live 熱路徑(`copycat[live]` extra),不下放到純函式層,讓 replay/backtest 的 stdlib 純度不變 |
| **`orjson`** | `tc4._realtime_msg`(吃 bytes)、`group_snapshot` 的 3.4 MiB response、`signal_hub` jsonl 落檔 | 解析 2–4×、序列化 3–5×;直接出 bytes 省 str 中繼 | 新相依(C extension,Windows wheel 齊);`jsonl` 落檔的**位元組輸出必須與現況逐字相同** | **有條件導入** —— jsonl 那條有 byte 比對測試(`tests/server/test_signal_outcome.py`),先確認 orjson 的浮點字面與 stdlib 一致,不一致就只用在 WS/HTTP 出口 |
| **`msgspec`** | WS payload 的 encode + 取代熱路徑 dataclass(`msgspec.Struct` 自帶 slots、比 dataclass 省 40%) | 同時解決 X5-01 的物件成本與 X5-02 的序列化成本 | 新相依;`Struct` 不是 dataclass,`dataclasses.replace`(`stock_models.py:143`)要改寫 | **有條件導入**,與 numpy 二選一路線;若走欄式 tape 就不太需要它 |
| **`gc.freeze()`** | boot 完成後(`app.py` lifespan 尾) | 凍住 import 出來的 ~13k 物件 | 幾乎零 | **建議導入**(收益小但零風險);**不要**期待它解決 X5-01 |
| **`gc.set_threshold(50_000, 20, 20)`** | boot 時 | 把 full GC 頻率降下來,換單次更久 | 單次停頓變更久、更難預測 | **不建議** —— 對延遲敏感系統,把 GC 從「常來且短」調成「少來且長」是反方向 |
| **`gc.disable()` 在熱路徑** | — | — | 本系統有 asyncio Task / 回呼閉包 / engine 互持,循環參照是真的存在,關掉會真漏 | **不建議** |
| **`tracemalloc`** | 離線 repro 與盤後一次性取證 | 精確定位配置點 | 全程開 2–3× 慢 | **建議導入,但只在 verify server / 盤後** |
| **`gc.callbacks` 探針** | prod 常駐 | 記 full GC 次數與停頓分佈,成本近零 | 幾乎零 | **強烈建議導入**(X5-05) |
| **`polars` / `pyarrow` / `duckdb`** | — | 本系統沒有 DataFrame 形狀的 live 工作負載(唯一接近的是 breadth 的 4,000 列,10 秒一次) | 大相依、大 import 時間 | **不建議**(回測那一側另議,不在本區塊) |
| **`uvloop`** | — | Linux only | — | **不適用**(Windows 綁定,CLAUDE.md §5) |

**跨區塊提醒**:X5-01 的欄式 tape 與 X5-03 的 numpy 化,是唯二能把 GC 停頓
從 105 ms 拉回個位數的手段。其餘所有優化加起來都動不了那個數字。

---

## 7. 不要動的地方(這些已經夠好 / 改了是過度工程)

1. **`futures_engine`(`server/futures_engine.py:115-145,645-694`)** —— 全庫記憶體紀律最好的
   一支:`_ProductState` 有 `__slots__`、`_dirty` dict 合併 + 單一 flush timer(0.1 s)、
   `payload()` 只在送出時複製 bids/asks。10 個商品 × 每 0.1 s = 微不足道。**一行都不用改。**
2. **`RiverState`(`live/river_state.py`)** —— 分鐘桶 dict,上界 = 一天的分鐘數(day 300 / night 840)。
   結構正確,佔用可忽略。
3. **`CorrState` 的儲存層(`live/corr_state.py:55-78`)** —— 時間戳逐出 + `_cap` 雙保險,
   檔頭把「為什麼不用固定長度 deque」講得很清楚。**要改的是 `correlations()` 的演算法
   (X5-03),不是 `_series` 的結構。**
4. **`WsBroadcaster`(`server/ws.py`)** —— per-client 有界 queue、滿丟最舊保最新、
   訊息物件全體共用、丟包有節流 WARNING + 窗結算。政策與實作都對。只缺一個記憶體觀測點。
5. **`HandoverBuffer`(`live/handover.py`)** —— cap 200k + 80% 預警,而且預警文字帶了
   實測依據(「~4.5 分鐘已 buffer ~110k」)。教科書等級。
6. **`SignalHub` 的兩條 queue + `_discord_sent` 時間窗 deque** —— 全部有界,
   關機還有 `join()` 屏障。
7. **`BarsCache.prune` 的日期維度與負向快取規則** —— `put_hist_range` 的
   「只寫到有證據掃過的最後一天」(review P1-2)、`MIDNIGHT_BUFFER_END`(TZ-2)、
   `_today_ttl` 的單一定義,每一條都是踩過坑換來的。**加 code 維度 LRU 時一行都不要碰它們。**
8. **timer handle 的 pop/cancel 紀律**(`stock_engine.py:1506-1538`、
   `signal_hub.py:404,668-669`)—— 排了就有取消點,close 與 rollover 各自清各自的。
   這是全庫最常見的洩漏形狀,而這裡已經處理乾淨。
9. **`backtest/` 與 `engine/` 的 dataclass** —— 已經全帶 `slots=True`,而且是離線路徑,
   不必再動。
10. **`_listen_loop` 測後洩漏**(CLAUDE.md 提及)—— 已於 2026-09-09 `refactor/w3-b2-test-scaffolds`
    以 root conftest autouse `_no_leaked_tc4_threads` 解決(`docs/next-time.md:601-603`)。
    **這是測試環境問題,不是 prod 洩漏**,不要再花時間。

---

## 8. 量測方法(prod 可用、盤中不影響效能)

### 8.1 常駐探針(成本近零,建議直接上)

```python
# copycat/server/memprobe.py(新檔,零相依)
import ctypes, gc, logging, time
logger = logging.getLogger(__name__)

_GC_PAUSE_WARN_MS = 50.0   # 超過即印固定字串,grep 錨「GC 停頓」

class _PMC(ctypes.Structure):
    _fields_ = [("cb", ctypes.c_uint32), ("PageFaultCount", ctypes.c_uint32),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t)] + \
               [(n, ctypes.c_size_t) for n in
                ("QuotaPeakPagedPool","QuotaPagedPool","QuotaPeakNonPagedPool",
                 "QuotaNonPagedPool","PagefileUsage","PeakPagefileUsage")]

def rss_mib() -> float:
    c = _PMC(); c.cb = ctypes.sizeof(_PMC)
    ctypes.windll.psapi.GetProcessMemoryInfo(
        ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return c.WorkingSetSize / 1048576
```

- **GC 停頓**:`gc.callbacks.append(cb)`,`cb` 在 `phase=="start"` 記時刻、`"stop"` 算差值,
  超過 `_GC_PAUSE_WARN_MS` 印 `logger.warning("GC 停頓 %.0f ms(gen%d,tracked=%d)")`。
  **實測開銷:每次 collection 兩次 Python 函式呼叫,一天 ~300 次 → 完全可忽略。**
  盤後判準:`grep "GC 停頓" logs/server-*.log` —— 現況必然命中(gen2 ~105 ms),
  改完 X5-01 之後應該歸零,這就是修法生效的機驗判準。
- **每 5 分鐘一行 INFO**(掛既有的 `_checkpoint_loop`,`stock_engine.py:1128-1143`,60 s 拍,
  每 5 拍印一次,**不新增 task**):
  ```
  mem rss=412MiB tracked=821283 states=187 ticks=742115 bars_hist=1043 bars_today=42 ws_q_max=31
  ```
  每個數字都是 O(1) 或 O(檔數) 的讀取,總成本 <1 ms。
- **`/api/health` 刻意不含引擎健康度** 是既有拍板(app.py health docstring),
  所以**開一條新的 `/api/health/mem`**,不動那條。

### 8.2 盤後一次性取證(tracemalloc)

```powershell
# 盤後、TC4 關著,起 verify server(側車,見 ops-discipline skill)
$env:PYTHONTRACEMALLOC="1"      # 只在這一台
.venv\Scripts\python -m copycat.server
```
盤後跑一次 `tracemalloc.take_snapshot()` 落檔,與昨日的比對 `compare_to(...,'lineno')`,
前 20 名就是真正的成長點。**絕不在正式看盤那台開** —— tracemalloc 全程開 2–3× 慢。

### 8.3 離線 repro(不需要 TC4)

本報告的五支 bench 已經證明:**不需要真 TC4 就能複現全部記憶體行為**,
因為狀態機與 parse 層都是零 IO 的純函式。建議把它們收成
`tests/perf/` 下的 benchmark(不進預設 `pytest -q`,以 marker 隔開):
- `bench_gc4.py` 型 —— 600k tick 進 150 狀態機,斷言 `max gen2 pause < 20 ms`
- `bench_group.py` 型 —— `group_snapshot(150)`,斷言 `< 20 ms` 且 `peak < 5 MiB`
- `bench_corr.py` 型 —— `correlations()`,斷言 `< 2 ms`

這三條就是 X5-01/02/03 的驗收判準,而且**改壞了會紅**。

### 8.4 真實速率的唯一缺口

本報告所有「每秒幾則」都是推估。**唯一要在 prod 補的是一個計數器**:
`tc4._listen_loop` 每 60 s 印一行 `TC4 <source> 收 %d 則/分(峰值 %d 則/秒)`。
沒有這個數字,上面所有「MB/s」都是推算而不是事實。

---

## 9. 這個區塊發現的硬約束(改造時必須同動)

1. **`snapshot()` / `light_snapshot()` 的 wire 鍵名是單一定義**(CLAUDE.md §4),
   讀者 = 前端 `lib/stock-accum.ts`、`useGroupSnapshots`。內部改欄式儲存可以,
   **出口形狀不可改**。
2. **個股 `seq` 的兩個口徑**(CLAUDE.md §4):`snapshot.seq` = ticks 尾筆序號、
   `tick.seq` 每筆 +1。tape 改結構後 `seq` 的推進點必須逐字保留,否則前端
   「成交明細 tbody 靜默整片重掛」。
3. **`ticks` 打包契約**(CLAUDE.md §4 #180):item 欄位逐字同名、無 `type`、
   `tick_flush_secs = 0.1`、per-client queue 1000 撐 100 s。降 maxsize = 改該條文字。
4. **`vp` parity**:`tests/fixtures/vp_parity.json` 兩側各自斷言,
   `_fold_vp`(`stock_state.py:178-198`)逐條對齊前端 `stock-accum.ts::foldVp`。
   VP 改 numpy 要讓 golden 逐值相同。
5. **WS 心跳 10 s vs 前端靜默 watchdog 30 s**(`ws.py:34` ↔ `ws-reconnect.ts`):
   任何讓 event loop 阻塞逼近 30 s 的改動都會觸發全站重連。現況最壞
   94 ms(group_snapshot)+ 105 ms(GC)= 0.2 s,餘裕大,但這是不可越的界。
6. **`signal_hub` jsonl 的「只加欄不改欄」(W1)** 與 `test_signal_outcome.py` 的
   **byte 比對** —— 換 JSON 函式庫必須先過這關。
7. **`shutdown_budget.run_grace_secs()` = 83 s 與 `run.ps1` 的字面 parity**
   (CLAUDE.md §4 A1):加 lane / 改 timeout 要同動。本區塊的改動不碰它。
8. **`WATCHLIST_LIMIT = 150` 的「效能預算註解」第二類讀者**(CLAUDE.md §4 明列:
   `stock_engine` / `watchlist_service` / `stock_state` / `GroupGridView`):
   本報告的實測數字(1,163 KiB/檔、94 ms/群組輪詢)**正是那些註解該引用的依據** ——
   目前那些註解沒有任何實測支撐,`bars.py:339` 那條甚至還停在「50 檔上限」。

---

## 10. 開放問題(需要 user 回答或需要 prod 探針才知道)

1. **真實 TC4 REALTIME 訊息速率是多少?** 150 檔全訂閱時,開盤第一分鐘 / 平均盤中,
   每秒幾則?本報告全部以 300–1,000 則/s 推估。→ §8.4 的計數器。
2. **單則 REALTIME 電文的實際 bytes 大小?** 推估 1–2 KB(30+ 欄位 + 五檔 20 欄)。
3. **實際 RSS 是多少?** 完全沒有探針,無從得知。推估 380–400 MiB。
4. **一天下來有幾檔會撞到 `_TICKS_MAXLEN = 20_000`?** 註解說「熱門股單日 6.2k 實測、
   漲停攻防股更高」,但沒有「幾檔會滿」的紀錄。這直接決定 §4.3 的上界是 200 MiB 還是 762 MiB。
5. **使用者一天實際會點過幾檔?**(決定 `_states` / `_hist` 的 code 維度成長)
6. **是否接受引入 numpy(打破 `dependencies = []`)?** 這是 X5-01 進階版與 X5-03 進階版的
   前提。stdlib-only 的 `array.array` 版本能拿到 90% 的收益,決策點在剩下的 10% 值不值得。
7. **Windows 上 pymalloc arena 釋放後是否還給 OS?** 未實測。若不還,
   group_snapshot 的 17.7 MiB 峰值會讓 RSS 單調上升(常見現象),
   而那會讓「RSS 只升不降」被誤讀成洩漏。→ 建議 §8.1 的 RSS 探針一起記 `PeakWorkingSetSize`。
8. **是否有 prod 曾觀察到「畫面偶爾頓一下」?** `stock_state.py:63` 的註解提過這個症狀
   形狀(「圖偶爾頓一下」),若 user 實際有感,105 ms GC + 94 ms group_snapshot 就是嫌犯。
