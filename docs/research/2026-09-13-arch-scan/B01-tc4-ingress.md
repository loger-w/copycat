# B01 — TC4 / ZMQ 行情入口(最熱路徑)架構掃描報告

- 掃描日期:2026-09-13
- 範圍:`copycat/live/tc4.py`(1317 LOC)、`copycat/tc4common.py`、`copycat/live/session.py`、
  `copycat/live/stock_source.py`(936 LOC)、`copycat/live/futures_source.py`、`copycat/live/corr_source.py`、
  `copycat/live/models.py`、`copycat/live/stock_models.py`、`spikes/TCPY/tcoreapi_mq.py`(wrapper,**gitignored**),
  以及四條 engine 的 thread→loop 交接點(`server/engine.py`、`stock_engine.py`、`futures_engine.py`、
  `index_engine.py`、`corr_engine.py`)。
- 所有數字皆為**本機實測**(`.venv` Python 3.13.13, Windows 11),腳本在
  `<scratchpad>/bench_ingress.py` / `bench_parse.py` / `bench_handoff.py` / `bench_codec.py` /
  `bench_full.py` / `bench_gil2.py` / `bench_milli.py`。未實測的一律標「推測」。

---

## 0. 一句話結論

**這個區塊真正的效能問題不是「Python 太慢」,是「同一則訊息被解碼 5 次、跨執行緒交接 5 次,
其中 4 次注定被丟掉」。** 換 msgspec/orjson 能把單次解碼從 6.5 µs 降到 1.8 µs(3.6×),但
**先把 5 條 listener 收成 1 條**能一次砍掉 ~68% 的入口 CPU,而且不需要任何新相依。兩件事
應該照這個順序做。

---

## 1. 架構地圖

### 1.1 行程內的 TC4 session 拓樸

`server/app.py` 建**五條互相獨立的 TC4 session**,每條都是 `TC4QuoteSource` 或其子類:

| session | 類別 | 建構點 | 訂閱內容 | REALTIME 窗 |
|---|---|---|---|---|
| TXO | `TC4QuoteSource`(基底) | `app.py:389 _default_source` | 選定序列 277 檔 + `TXF.HOT`(常駐 offset 4 小時) | 台指盤別窗 |
| 個股 | `StockQuoteSource` | `app.py:406 _default_stock_source` | 自選 ≤150 檔 + 個股期 leaf | 個股日盤窗 `YYYYMMDD00`–`06` |
| 指數 | `StockQuoteSource`(第二顆) | `app.py:416 _default_index_source` | `IX0001` | 同上 |
| 期貨 | `FuturesQuoteSource` | `app.py:428 _default_futures_source` | TXF/MXF/TMF `.HOT` + 月份 leaf | 台指盤別窗 |
| 相關係數 | `CorrQuoteSource` | `app.py:442 _default_corr_source` | 10 條 tc4 腿(SGX/CBOT/CME/OSE/CFE + SXF) | 全天窗 / TWS 腿吃個股窗 |

每條 session 在行程內起:

```
copycat/live/tc4.py:1185   self._listener = threading.Thread(target=self._listen_loop, daemon=True)
copycat/live/tc4.py:638    self._healer   = threading.Thread(target=self._heal_loop,  daemon=True)
copycat/live/tc4.py:1229   ctx = zmq.Context()          # listener 自己的 context
spikes/TCPY/tcoreapi_mq.py:8    self.context = zmq.Context()      # REQ socket 用
spikes/TCPY/tcoreapi_mq.py:277  self._ctx    = zmq.Context()      # KeepAlive 用
spikes/TCPY/tcoreapi_mq.py:279  threading.Thread(target=self.ThreadProcess, ..., daemon=True)
```

→ **每條 session = 3 個 Python 執行緒(listener / healer / KeepAlive)+ 3 個 zmq.Context
(= 3 個 C 層 IO thread)**。五條 session = **15 個 Python 執行緒 + 15 個 ZMQ IO thread**,
再加 `StockQuoteSource` 在訂閱瞬間每檔一支 `threading.Timer`(`stock_source.py:642`,
150 檔同時訂閱 = 瞬間 150 支 Timer 執行緒)、capital COM 執行緒、asyncio 預設 executor pool、
uvicorn 自己的執行緒。

### 1.2 資料流(一則 REALTIME 推播的完整旅程)

```
TC4 桌面 app (PUB, tcp://127.0.0.1:<SubPort>)
        │  一則 ~900 byte JSON,前面帶 "REALTIME:" topic 前綴,尾端多 1 byte
        │
        ├────────────┬────────────┬────────────┬────────────┐   ← 同一個 SubPort,五條 SUB 全收
        ▼            ▼            ▼            ▼            ▼
  TXO listener  個股 listener  指數 listener  期貨 listener  corr listener      (5 條 Python thread)
        │            │            │            │            │
   recv()[:-1].decode("utf-8")          tc4.py:1245          × 5
   _realtime_msg(raw):                  tc4.py:1189–1211     × 5
       raw.find(":") → json.loads(raw[idx+1:])               × 5
       _note_push(symbol, quote)  ← 每則、每條 session 都記帳  × 5
        │            │            │            │            │
   handle_raw 覆寫(4 份)                                      × 5
        │            │            │            │            │
   loop.call_soon_threadsafe(_handle_quote, quote)            × 5   ← Windows 自喚醒 socket write
        ▼            ▼            ▼            ▼            ▼
  ══════════════════ 單一 asyncio event loop ══════════════════
   engine._enqueue → asyncio.Queue → _consume → agg.route
   stock_engine._handle_quote → symbol dict lookup → 不是我的 → return
   index_engine._handle_quote → 同上
   futures_engine._handle_quote → product_from_symbol() is None → return
   corr_engine._handle_quote → _by_symbol.get() is None → return
```

**再平行一路**:每條 session 的 KeepAlive 執行緒也開一顆 SUB 接同一個 SubPort、`SUBSCRIBE ""`,
對**每一則**訊息做 `decode("utf-8")` + `re.search("{\"DataType\":\"PING\"}", message)`
(`spikes/TCPY/tcoreapi_mq.py:288–297`)。× 5 條。

### 1.3 REQ 通道(與 REALTIME 完全分離)

`_req`(`tc4.py:547`)是所有同步請求的唯一出口:SUBQUOTE / UNSUBQUOTE / GETHISDATA /
SUBQUOTE(history) / QUERYALLINSTRUMENT / LOGOUT。全部走 wrapper 的 `api.socket`
(一顆 `zmq.REQ`)+ `api.lock`(一把 `threading.Lock`)。**每條 session 一把,行程內五把。**

---

## 2. 熱路徑逐條(含實測成本)

測試訊息:893 byte 的個股 REALTIME(五檔買賣 + 完整 meta),與真實 TC4 電文同形。

### HP-1 `_listen_loop` 的 recv + 解碼 —— 每則、每條 session

```python
# copycat/live/tc4.py:1244-1250
            try:
                raw = (sock.recv()[:-1]).decode("utf-8")
            except zmq.ZMQError:
                self._check_stale()
                continue
            self._last_msg = time.monotonic()
            self.handle_raw(raw)
```

```python
# copycat/live/tc4.py:1195-1211  _realtime_msg
        idx = raw.find(":")
        if idx < 0: return None
        try:
            msg = json.loads(raw[idx + 1 :])
        except json.JSONDecodeError:
            return None
        if msg.get("DataType") != "REALTIME": return None
```

每則配置的物件:`sock.recv()` 的 bytes → `[:-1]` **bytes 複本** → `.decode()` **str 複本** →
`raw[idx+1:]` **第二個 str 複本** → `json.loads` 建出巢狀 dict(約 40 個 str key + 40 個 str value)。
一則訊息光解碼就配置 **~85 個物件**。

**實測 6.5–7.7 µs / 則 / session。**

### HP-2 `_note_push` —— 每則、每條 session、不分是不是自己的 symbol

```python
# copycat/live/tc4.py:1206-1210
        quote = msg.get("Quote")
        if isinstance(quote, dict):
            symbol = quote.get("Symbol")
            if isinstance(symbol, str) and symbol:
                self._note_push(symbol, quote)
```
```python
# copycat/live/tc4.py:793-797
        now = time.monotonic()
        self._last_push[symbol] = now
        fp = tuple(str(quote.get(k, "")) for k in _PUSH_FP_KEYS)
        prev_fp = self._push_fp.get(symbol)
        self._push_fp[symbol] = fp
```

實測 **0.73 µs / 則 / session**。單筆便宜,但它對**線上出現的每一個 symbol**都寫兩個 dict ——
包含這條 session 根本沒訂的 symbol。`_last_push` / `_push_fp` 因此在五條 session 上各自長成
「全行程所有 symbol」的大小(~450 鍵),而 `_heal_tick` 只讀 `self._subscribed` 那幾十把。

### HP-3 KeepAlive 執行緒的重複解碼 —— 每則、每條 session

```python
# spikes/TCPY/tcoreapi_mq.py:288-297
        while not self.IsTerminal:
            try:
                message = (socket_sub.recv()[:-1]).decode("utf-8")
            except zmq.ZMQError:
                break
            findText = re.search("{\"DataType\":\"PING\"}",message)
            if findText == None:
                continue
            objZMQ.Pong(session, "TC")
```

實測 **1.78 µs / 則 / session**。這條執行緒唯一的職責是回應每 N 秒一次的 PING,卻要對
**每一則行情**做一次完整 UTF-8 decode + 一次全字串 regex 掃描。

### HP-4 thread → loop 交接 `call_soon_threadsafe` —— 每則、每條 session

```python
# copycat/server/stock_engine.py:1147-1150(四條 engine 逐字同形)
    def _on_raw_threadsafe(self, quote: dict) -> None:
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._handle_quote, quote)
```

**實測 8.1 µs / 次(生產端),端到端 8.12 µs/則,上限 ~123,000 msg/s。**
這是本區塊最貴的單一動作。原因是 CPython 的 `BaseEventLoop.call_soon_threadsafe` 每次都
無條件呼叫 `self._write_to_self()`,在 Windows 上 = 對 loopback socket 做一次 send
(ProactorEventLoop,`uvicorn.run` 沒指定 loop,Windows 預設就是它 —— `server/__main__.py:193`)。

### HP-5 真正的 parse —— 每則,但只有「擁有這個 symbol」的那一條 session 做真事

`parse_stock_realtime`(`stock_models.py:188`)實測 **29.8 µs**。拆解:

| 子項 | 實測 | 佔比 | 原因 |
|---|---|---|---|
| `_taipei_time`(`stock_models.py:89`) | **10.21 µs** | 34% | `_dt.datetime.strptime(date_utc, "%Y%m%d")` + 兩次 `%`-format |
| `_parse_levels` × 2(`stock_models.py:171`) | **6.76 µs** | 23% | 每檔 `price_key + suffix` 字串拼接 + 2 次 `dict.get` + `Decimal` |
| 其餘 `to_milli`(ref/upper/lower/yclose/price)+ `_to_int` | ~2.5 µs | 8% | `Decimal` 0.37–0.45 µs × ~6 |
| `_hhmmss` × 2 | 0.48 µs | 2% | |
| `is_trial_window` | 0.47 µs | 2% | |
| 三個 frozen dataclass 建構 + 其它 | ~9 µs | 30% | `StockBook` / `StockMeta` / `StockTick` |

TXO 路徑的 `parse_realtime`(`models.py:91`)只要 **3.16 µs**(不解五檔、不轉時區)。

### HP-6 loop 上的早退

四條 engine 的 `_handle_quote` 第一件事都是 dict lookup,~0.5–1 µs。但這已經是**在
event loop 上**發生的 —— 也就是說 loop 每則訊息被喚醒並執行 5 個 callback,其中 4 個立刻 return。

**例外(最貴的一條)**:TXO 基底的 `handle_raw` 沒有早退,它會**完整 parse 每一則**:

```python
# copycat/live/tc4.py:1219-1224
        msg = self._realtime_msg(raw)
        if msg is None: return
        tick = parse_realtime(msg.get("Quote", {}))
        if tick is not None and self._on_tick is not None:
            self._on_tick(tick)     # → EngineRuntime.on_tick → call_soon_threadsafe → asyncio.Queue
```

個股 tick 一樣解得出 `Tick`(symbol 非空、有價、有 PreciseTime、qty>0)→ 一路穿過
`call_soon_threadsafe` → `_enqueue` → `asyncio.Queue` → `_consume` → `agg.route`,
最後才在這裡被丟掉:

```python
# copycat/live/aggregate.py:85-87
        if tick.symbol not in self._contracts:
            self.totals.dropped_foreign_ticks += 1
            return False
```

### HP-7 `engine._consume` 的 `wait_for` —— 每筆 TXO tick

```python
# copycat/server/engine.py:382-386
            try:
                tick = await asyncio.wait_for(self._queue.get(), timeout=0.05)
            except TimeoutError:
                await self._maybe_self_heal()
                continue
```

實測:`asyncio.Queue` 裸 `get()` = **0.49 µs/筆**;包上 `wait_for(timeout=0.05)` = **2.59 µs/筆**
(+2.1 µs,每筆多建一個 Timeout/TimerHandle)。

---

## 3. Findings

### B01-01 【critical】同一則訊息被五條 session 各自完整解碼並各自跨執行緒交接,四次是純浪費

**證據(這是 repo 自己記下來的事實,不是我的推論)**

```python
# copycat/live/models.py:16-19
#: **不可放寬成 `"TC.F."`**:TXO runtime 的 ZMQ SUB 訂 `""`,會收到同 process 其他引擎訂的
#: 所有期貨推播 —— 個股期(`TC.F.TWF.DHF.HOT`)、海外腿(`TC.F.CME.YM.HOT` 等)、
#: 費半、小台微台。
```
```python
# copycat/live/aggregate.py:46-48
    其餘期貨(個股期 / 海外腿 / 費半 / 小台微台)一律走 foreign 丟棄計數 —— 它們會
    出現在這條流上是因為 TXO runtime 的 ZMQ SUB 訂 `""`,收得到同 process 其他引擎的
    訂閱推播,不是本序列的資料。
```
```python
# copycat/live/tc4.py:1239-1241
                sock = ctx.socket(zmq.SUB)
                sock.connect(f"tcp://127.0.0.1:{self._sub_port}")
                sock.setsockopt_string(zmq.SUBSCRIBE, "")     # ← 五條都訂全部
```

規模的實測值來自 repo 自己的掃描報告:

```
docs/research/2026-08-19-browser-crash-scan.md:41
  實測 dropped_foreign_ticks 309 萬 vs 真 TXO tick 2300
```

**309 萬** = 一天之內,只計「解得出 `Tick`(有成交)」的訊息、只算 TXO 這一條 session 收到的
別人家的推播。純簿更新(`TradeQuantity=0`)被 `parse_realtime` 在更前面丟掉、根本沒進這個計數,
所以線上真實訊息量比 309 萬**更高**。

**影響(量化)**

一則 893 byte 訊息的行程總成本:

| 段 | 單次 | × session | 小計 |
|---|---|---|---|
| listener recv + decode + json.loads | 6.5–7.7 µs | ×5 | ~36 µs |
| `_note_push` | 0.73 µs | ×5 | 3.7 µs |
| KeepAlive decode + regex | 1.78 µs | ×5 | 8.9 µs |
| `call_soon_threadsafe` | 8.1 µs | ×5 | **40.5 µs** |
| loop 端 callback 派發 + 早退 | ~1 µs | ×5 | 5 µs |
| 真 parse(只有 1 條做) | 29.8 µs(個股) | ×1 | 29.8 µs |
| **合計** | | | **~124 µs / 則** |

其中 **~86 µs(69%)由四條「這則不關我的事」的 session 付掉**。

- 以日均 200 則/s(由 309 萬/日保守回推)計:~25 ms/s = 2.5% 單核。
- 以開盤瞬間 1500 則/s(**推測**,未實測)計:~186 ms/s = 19% 單核,而且這 19% 全部壓在 GIL 上。

**修法**:一條 reader thread 收一次、解一次、按 symbol 前綴/查表分派給對應 engine,
每 N 則或每 1 ms 做**一次** `call_soon_threadsafe` 送整批。
`_note_push` 改成只餵「有訂這個 symbol」的 session。

**風險 / 契約**
- 前提假設「五條 session 的 `SubPort` 相同」。跨 session 可見性已被上面兩段註解實證,
  但**建議先在 `_ensure_connected` 加一行 `logger.info("session sub_port=%s")` 對五條做一次確認**
  (若 TC4 之後改成 per-session port,單 reader 會靜默只收到一條 session 的流)。
- 每條 session 的 `_last_push` / `_sub_at` / `_heal_*` 記帳必須由 reader 分派後再呼叫 —— 漏掉
  = 自癒 watchdog 誤判「零推播」,整批 UNSUB→SUB churn,零錯誤訊號。
- `handle_raw(raw: str)` 是四個子類的覆寫點,也是 `tests/live/test_tc4.py` 等大量測試的注入點;
  重構要保留 `handle_raw(str)` 當薄轉接層。
- **不動任何 CLAUDE.md §4 的跨檔契約**(這一層完全在 wire 之前)。

**effort**:L

---

### B01-02 【critical】`call_soon_threadsafe` 每則 8.1 µs(Windows 自喚醒 socket write),且是 5 倍放大

**證據**

```python
# copycat/server/engine.py:361-365
    def on_tick(self, tick: Tick) -> None:
        loop = self._loop
        if loop is None: return
        loop.call_soon_threadsafe(self._enqueue, tick)
```
同形的還有 `stock_engine.py:1147`、`futures_engine.py:562`、`index_engine.py:417`、`corr_engine.py:259`。

**實測**:`call_soon_threadsafe` 生產端 8.112 µs/call;端到端 8.124 µs/msg;
吞吐上限 ~123,000 msg/s(單一 producer、loop 空閒)。

**影響**:單則 40.5 µs(×5)。在 1500 則/s 下就是 61 ms/s 純交接開銷;更糟的是每次都是一個
loopback socket 的 send+recv 系統呼叫,把 event loop 從 IOCP 等待中反覆喚醒。

**修法**:批次化。reader thread 用 `collections.deque`(`append` 是 GIL 原子)累積,搭配一個
`_scheduled` 旗標,只在旗標為 False 時發一次 `call_soon_threadsafe(self._drain)`;loop 端
`_drain` 把整個 deque 一次 `popleft` 掃完。批量 20 則時交接成本從 8.1 µs/則降到 ~0.4 µs/則。
延遲代價 ≤ 一次 loop 週轉(實測 p50 1.8 µs)。

**風險**:`stock_engine` 已經在 loop 端做 0.1 s 的 `ticks` 打包(`_flush_ticks`,CLAUDE.md §4
「個股逐筆 = `ticks` 打包訊息」契約),ingress 批次在它**之前**,不改變 wire 形狀、不動 `seq` 口徑。
但 `_handle_quote` 內的 rollover 快路徑對「同一則的先後次序」有依賴 —— 批次必須嚴格保序
(deque FIFO 天然保序,不得改用 set/dict 去重)。

**effort**:M

---

### B01-03 【high】`_taipei_time` 每 tick 一次 `datetime.strptime`,佔個股 parse 的 34%

**證據**

```python
# copycat/live/stock_models.py:89-95
def _taipei_time(precise_utc: str, date_utc: str) -> tuple[str, str]:
    s = precise_utc.zfill(12)
    hh, mm, ss, frac = int(s[:2]), int(s[2:4]), int(s[4:6]), s[6:9]
    base = _dt.datetime.strptime(date_utc, "%Y%m%d")        # ← 10 µs 的來源
    local = base + _dt.timedelta(hours=hh, minutes=mm, seconds=ss) + _TAIPEI_OFFSET
    return f"{local:%H:%M:%S}.{frac}", f"{local:%Y-%m-%d}"
```

**實測**:`_taipei_time` 10.205 µs;手刻整數切片版(已驗證逐位等值,含跨午夜)**1.477 µs**。
一次改動省 **8.7 µs / 個股 tick**,= 個股 parse 從 29.8 → ~21 µs(−29%)。

**修法**:純字串/整數運算。`hh+8 >= 24` 才走 `datetime.date + timedelta(days=1)`
(台股日盤永遠不會走到,個股期夜盤會)。`_taipei_dt_key`(`stock_source.py:288`)同款問題,
但那條在回補路徑(離線),優先度低。

**風險**:`tick.time` / `tick.trade_date` 是整條個股鏈的語意骨幹(試撮窗判定、rollover stage2
的 `tick.trade_date > self._trade_date`、前端分鐘鍵)。必須以現有 `tests/live/test_stock_models.py`
為 characterization + 加一支跨午夜 / 跨月 / 跨年的 property 對照測試(我已本機驗過
`'025751123456','20260913'` 這一組逐字等值,但生產前要全窗對照)。**不動任何跨檔契約**。

**effort**:S

---

### B01-04 【high】`_parse_levels` 每則做 10 次字串拼接 + 20 次 dict.get

**證據**

```python
# copycat/live/stock_models.py:177-185
    levels: list[tuple[int, int]] = []
    for i in range(_DEPTH):
        suffix = "" if i == 0 else str(i)
        price = to_milli(msg.get(price_key + suffix, ""))      # ← 每檔一次 str concat
        if price is None: continue
        vol = _to_int(msg.get(vol_key + suffix, ""))
        levels.append((price, vol or 0))
```

呼叫兩次(bid/ask)= 每則 10 次 `str(i)` + 10 次字串拼接 + 20 次 `dict.get`。
**實測 3.378 µs × 2 = 6.76 µs / 則**(個股 parse 的 23%)。

**修法**:module 層預先算好四組 tuple 常數並 `zip` 走:

```python
_BID_P = ("Bid", "Bid1", "Bid2", "Bid3", "Bid4")
_BID_V = ("BidVolume", "BidVolume1", ...)
```

**注意(反向發現)**:`to_milli_units` 用 `Decimal` 看起來可疑,但實測只有 **0.449 µs**,
手刻整數版 0.369 µs —— **省不到 0.1 µs,而 `tc4common.py:22` 明文寫著「🚨 不與 float
家族合併:Decimal 是截斷、float round 是 banker's rounding,在 tick 邊界會分岔」。
這裡不要動。**(我寫了一版逐位等值的手刻版驗證過語意,結論仍是不值得。)

**effort**:S

---

### B01-05 【high】KeepAlive 執行緒對每一則行情做全字串 regex 掃描,只為了找每 N 秒一次的 PING

**證據**:`spikes/TCPY/tcoreapi_mq.py:288-297`(全文見 §2 HP-3)。

**實測**:1.78 µs/則/session × 5 = 8.9 µs/則。在 1500 則/s 下 = 13 ms/s,
外加 **5 條額外執行緒持續搶 GIL**。

**修法(兩選一)**
- (a) 併進 B01-01 的單 reader:reader 看到 `DataType == "PING"` 就代呼叫每條 session 的
  `api.Pong()` —— KeepAlive 執行緒與它的 zmq.Context 直接不起(省 5 執行緒 + 5 IO thread)。
- (b) 最小改動:把 `re.search(...)` 換成 `message.find('"DataType":"PING"') >= 0`,
  並在 decode **之前**先用 bytes `in` 判(`b'"DataType":"PING"' in raw_bytes`)—— 省掉 decode。

**風險**:`spikes/TCPY/` 是**第三方 vendored + gitignored**(見 B01-06)。改它等於改一個
不在版控裡的檔 —— 必須先把它 fork 進 repo。`Pong` 會取 `api.lock`,代呼叫要維持同一把鎖的語意,
否則 `close_worst_secs()`(`tc4.py:137`)推導出的關機預算(83 s,`server/shutdown_budget.py`
三方同源契約)前提就變了。

**effort**:M(含 fork wrapper)

---

### B01-06 【high】整條行情入口依賴一個 **gitignored 的第三方檔案**,靠 `sys.path.insert` 在 runtime 載入

**證據**

```python
# copycat/live/tc4.py:452-462
        with self._api_lock:
            ...
            sys.path.insert(
                0, str(Path(__file__).resolve().parent.parent.parent / "spikes" / "TCPY")
            )
            from tcoreapi_mq import QuoteAPI  # type: ignore[import-untyped]
            api = QuoteAPI(TC4_APPID, TC4_SKEY)
```
```
$ git check-ignore -v spikes/TCPY/tcoreapi_mq.py
.gitignore:9:spikes/TCPY/     spikes/TCPY/tcoreapi_mq.py
```

而這個檔案裡有**已知的毒鎖**(`Pong` / `SubQuote` / `GetHistory` 全都是
`lock.acquire()` … `lock.release()`,**沒有 try/finally**):任何一發拋例外,
`api.lock` 永久不釋放。`tc4.py` 整套 `lock_timeout_secs=12.0` / `_dispose` / `close_worst_secs`
的複雜度,有一半是在繞這件事。

另外 `ThreadProcess` 只 catch `zmq.ZMQError` —— `decode("utf-8")` 或 `re` 拋任何東西,
KeepAlive 執行緒靜靜死掉,socket 永不關,`Disconnect()` 的 `ctx.term()` **無上界**
(這正是 `close_worst_secs` docstring 裡寫的「不計的段」)。

**影響**:要下實單的系統,其**唯一**行情通道的傳輸層不在版控、不可 code review、不可 diff、
重灌機器就消失。這不是微效能問題,是架構問題,而且它同時**堵死了所有效能改法**
(B01-02 / B01-05 / B01-11 都要碰它)。

**修法**:把 `tcoreapi_mq.py` fork 成 `copycat/live/tc4_transport.py` 進版控,
只保留 `QuoteAPI` 需要的那幾支,全部補 `try/finally`,`ThreadProcess` 改 `except Exception` +
log,並把 PING 判定改 bytes。`sys.path.insert` 整段刪掉。

**風險**:這是行為改動,要走完整 characterization。`_req` 目前**刻意不呼叫 wrapper 方法**
(`tc4.py:548-553` 有明文理由),只用 `api.socket` / `api.lock` / `api.Connect` / `api.Disconnect`
—— 所以 fork 的表面積比看起來小很多。

**effort**:M

---

### B01-07 【high】五條 listener + 五條 KeepAlive 在 GIL 上互相踩,event loop 的 p99 週轉延遲劣化 10×

**實測**(`bench_gil2.py`,背景執行緒各以 5000 則/s 總量做 decode+json.loads):

| 情境 | p50 | p99 | max |
|---|---|---|---|
| 無背景執行緒 | 1.8 µs | **3.5 µs** | 95 µs |
| 5 條 listener | 1.8 µs | **30.1 µs** | 340 µs |
| 10 條(listener + KeepAlive) | 1.8 µs | **37.1 µs** | 235 µs |

`sys.getswitchinterval()` = 0.005 s。

**影響**:p50 完全沒動 —— 這是**純尾延遲**的故事,而尾延遲正是下單系統會痛的地方。
event loop 上跑的是:訊號判定(`signal_hub.on_tick`)、WS 廣播、以及未來的下單決策。
一則觸發訊號的 tick 在 p99 上要多等 30 µs 才輪得到 loop;疊上 HP-4 的 40 µs 交接、
`stock_engine._flush_ticks` 的 0.1 s 打包,端到端已經是**百毫秒級**。

**修法**:B01-01(5→1 reader)直接把這張表拉回第一列附近。若要更進一步,才考慮
「解碼放獨立 process、用 shm ring 傳 struct-packed 二進位」(XL,見 §5)。

**effort**:併入 B01-01

---

### B01-08 【high】ZMQ SUB 的 RCVHWM 沒設,預設 1000 —— listener 被卡住時會**靜默丟行情**

**證據**

```python
# copycat/live/tc4.py:1239-1243
                sock = ctx.socket(zmq.SUB)
                sock.connect(f"tcp://127.0.0.1:{self._sub_port}")
                sock.setsockopt_string(zmq.SUBSCRIBE, "")
                sock.setsockopt(zmq.RCVTIMEO, 1_000)
                bound_port = self._sub_port
```

只設了 `RCVTIMEO`,沒有 `RCVHWM`。pyzmq 預設 `RCVHWM = 1000`。SUB socket 滿了的行為是
**丟棄**(不是阻塞 publisher)。

**listener 執行緒會被卡住的具體路徑**:

```python
# copycat/live/tc4.py:1244-1250
            except zmq.ZMQError:
                self._check_stale()          # ← 這一支可能跑好幾分鐘
```
```python
# copycat/live/tc4.py:1264-1281  _check_stale
        while not self._stop.is_set():
            ...
                with self._lock:
                    ...
                    for sym in resub:
                        self._rt_request("UNSUBQUOTE", sym)   # 個股 150 檔 = 300 發 REQ
                        r = self._rt_request("SUBQUOTE", sym)
            ...
                if self._stop.wait(backoff):   # backoff 最長 60 s
```

另外 `handle_raw` 是同步跑在 listener 上的,任何 `call_soon_threadsafe` 被 loop 端拖慢
(GIL / 慢 callback)都直接回壓到 recv 的節奏。

**影響**:開盤瞬間 / 重連期間,超過 1000 則的積壓會被 ZMQ **無聲丟掉**,沒有任何計數器、
沒有 log。系統看得到的只有「tick 少了幾筆」,而 `_last_cum` 的 stale-drop 設計正好會把
跳號當成正常。**對一個要下實單的系統,這是最危險的一條。**

**修法**
- 立刻:`sock.setsockopt(zmq.RCVHWM, 100_000)`(一則 900 byte,10 萬則 = 90 MB 上限,
  本機記憶體充裕)+ **每 N 秒對照 `TradeVolume` 累積量與自算量,對不上就 log**。
  ZMQ 本身不提供 SUB 側的丟棄計數,只能靠應用層對帳。
- 根治:B01-01 的單 reader **只做 recv + 入 deque**,不做任何解碼/分派,
  把 recv 迴圈的每則成本壓到 < 1 µs。

**風險**:提高 HWM 把「丟資料」換成「吃記憶體 + 延遲累積」。所以必須配一個「積壓深度」
指標(deque 長度)進 `/api/health`。

**effort**:S(setsockopt)/ M(對帳指標)

---

### B01-09 【medium】TXO 基底的 `handle_raw` 沒有 symbol 早退,每則外來訊息都跑完整 parse + asyncio.Queue

**證據**

```python
# copycat/live/tc4.py:1213-1224
    def handle_raw(self, raw: str) -> None:
        msg = self._realtime_msg(raw)
        if msg is None: return
        tick = parse_realtime(msg.get("Quote", {}))        # 3.16 µs,對外來 symbol 也照跑
        if tick is not None and self._on_tick is not None:
            self._on_tick(tick)                            # → call_soon_threadsafe 8.1 µs
```

丟棄要一路走到:

```python
# copycat/live/aggregate.py:85-87
        if tick.symbol not in self._contracts:
            self.totals.dropped_foreign_ticks += 1
```

中間還經過 `engine._enqueue` → `asyncio.Queue.put_nowait` → `_consume` 的
`asyncio.wait_for(..., 0.05)`(+2.1 µs/筆,見 HP-7)。

**影響**:實測 309 萬則/日 走完這條路。每則 ~14 µs(parse 3.2 + cst 8.1 + queue/wait_for 2.6)
= **43 秒 CPU / 日**,而且全部落在 event loop 上與 GIL 上。

**修法(不等 B01-01 也能立刻做)**:在 `handle_raw` 最前面加 symbol 白名單早退 ——
`self._contracts` 的 key set 已經在 `ChainAggregator`,但 source 層需要自己一份
(`_subscribed` 已經有了,且 `_realtime_msg` 已經解出 symbol)。

```python
# 建議形狀
symbol = quote.get("Symbol")
if symbol not in self._subscribed and not symbol.startswith(SPOT_PREFIX):
    return
```

省下 parse + cst + queue,只留 decode(那個要 B01-01 才省得掉)。

**風險**:`dropped_foreign_ticks` 這個指標會歸零 —— 它目前是 `/api/txo/...` snapshot 的一個欄位
(`aggregate.py:225`),前端可能在顯示。要嘛把計數搬到 source 層,要嘛確認沒有讀者。
另外 `SPOT_SYMBOL` 的常駐 offset(`tc4.py:1089`)讓 TXF.HOT 在 `_subscribed` 裡,白名單成立。

**effort**:S

---

### B01-10 【medium】`engine._consume` 每筆 tick 多付 2.1 µs 的 `wait_for`

**證據**:`server/engine.py:382-386`(全文見 HP-7)。
**實測**:裸 `get()` 0.493 µs;`wait_for(timeout=0.05)` 2.590 µs。

註解自己說明了為什麼有 timeout:「盤中連續 tick 下 timeout 永不觸發(Alt-3)」——
也就是 timeout 分支本來就**不是**盤中的主路徑,它只是 `_maybe_self_heal` 的一個保底觸發器,
而 `_force_heal` 分支(`engine.py:391-393`)已經涵蓋了盤中。

**修法**:`_consume` 改 `tick = await self._queue.get()`,自癒輪詢改成獨立的
`asyncio.sleep(0.05)` 迴圈 task。

**風險**:`_maybe_self_heal` 的觸發條件之一是 `self._queue.empty()`
(`engine.py:418`),拆成獨立 task 後語意不變(它讀的是同一個 queue)。
`self._paused` 的 busy-wait(`engine.py:379-381`,`sleep(0.01)`)一併改成 `asyncio.Event`。

**effort**:S

---

### B01-11 【medium】corr session 的八條海外腿全天候每 5 分鐘 UNSUB→SUB,一天 1926 次 —— 自癒在空轉

**證據**(prod log,2026-09-11)

```
$ grep -c "零推播自癒" logs/server-20260911-0905.log
1926                                     # 全檔 17870 行 → 11% 的 log 是這個

$ grep "零推播自癒" ... | grep -o "TC\.[A-Z]\.[A-Z]*\.[A-Z0-9]*" | sort | uniq -c | sort -rn
    243 TC.F.OSE.NK225M      236 TC.F.CME.NQ       236 TC.F.CME.ES
    235 TC.F.CME.GC          235 TC.F.CME.CL       235 TC.F.CBOT.YM
    234 TC.F.SGX.TWN         232 TC.F.CFE.VX
     15 TC.F.TWF.MXF          12 TC.F.TWF.TXF       12 TC.F.TWF.TMF   1 TC.F.TWF.SXF

# 時間分布:24 小時每小時都是 94–124 發(含 03:00、19:00 等台股與美股都休市的時段)
```

每小時 96 發 = 8 腿 × 12 發 = 剛好 `_HEAL_BACKOFF_CAP`(300 s)封頂的節奏。
`VX` 標了 `sparse: true`(豁免 R2)卻仍有 232 發 → 它們是被 **R1 整批重掛**打到的:

```python
# copycat/live/tc4.py:706-714
        t1 = self._heal_silence
        if t1 is not None:
            quiet_since = max((self._last_push.get(s, 0.0) for s in subs), default=0.0)
            resub_since = max((self._sub_at.get(s, 0.0) for s in subs), default=0.0)
            if quiet_since < now - t1 and resub_since < now - t1:
                for sym in subs:
                    ...
                        self._heal(sym, now, t1)
                return
```

corr session 上「有閘且會開」的腿只有 SXF(`sparse`,本來就常靜默),台指 TXF 走
`futures_engine` 不由 corr 訂。所以 **R1 的「全部 symbol 都靜默」幾乎永遠成立** →
每 300 s 把八條腿全部 UNSUB+SUB 一次。

**影響**:每發 2 個 REQ round-trip(`_heal_resub` → `_resub` → UNSUBQUOTE + SUBQUOTE),
1926 × 2 = **3852 發 REQ / 日**,全部在 corr session 的 `api.lock` 上排隊;
再加上 `_heal_resub` 同時持 `self._lock`(與 `_check_stale` 互斥)。CPU 絕對值不高,
但它是「一個子系統整天在對 TC4 做無效 churn」的訊號,而 `HEAL_VARIANT_AFTER=3` 還會
不斷換訂閱窗字串 —— 在 TC4 端每次都是一把新的 refcount key。

**開放問題**:這八條腿是**真的沒有資料**(user 的 Touchance 訂閱可能不含 CME/CBOT/OSE/CFE/SGX
即時),還是自癒真的救不回來?這決定修法是「關掉它們」還是「修自癒」。

**修法**
- 若真的沒資料:把這些腿標 `sparse: true`(豁免 R2),並讓 R1 的母體扣掉全部 sparse 腿
  —— 目前 `sparse` 只擋 R2(`tc4.py:719-720`),R1 完全不看。這是設計上的洞。
- 若有資料:需要一個「連續 N 次自癒無效就放棄並告警」的收斂機制,而不是無限 300 s 重試。

**風險**:動 R1 的母體定義會改變「整條 session 死掉」的偵測能力 —— `HealPolicy.sparse_symbols`
的 docstring(`tc4.py:196-200`)明文說「母體只剩稀疏腿時 R1 會接手…這是保守選擇不是 bug」。
要改必須連同那段 rationale 一起改,並補一支「session 真的整條死」的測試。

**effort**:M

---

### B01-12 【medium】`handle_raw` 在 `_listen_loop` 的 try 之外 —— 任何例外 = listener 執行緒靜默死亡 = 整條 session 零推播

**證據**

```python
# copycat/live/tc4.py:1244-1250
            try:
                raw = (sock.recv()[:-1]).decode("utf-8")
            except zmq.ZMQError:
                self._check_stale()
                continue
            self._last_msg = time.monotonic()
            self.handle_raw(raw)              # ← try 之外
```

repo 自己記了一次撞上這個的事故:

```python
# copycat/live/tc4.py:798-800
        # 一次取值不裸索引:_unsub(別的執行緒)會在中間 pop 同一鍵,而 handle_raw 在 _listen_loop
        # 的 try 之外 —— KeyError 逃出去 = listener thread 死、整條 session 零推播(pr-145 F-03)
```

而且 `.decode("utf-8")` 本身的 `UnicodeDecodeError` 也在 `except zmq.ZMQError` 抓不到的位置。

**影響**:效能層面是零,但**可用性層面是 critical**:失效樣態是「畫面停住、沒有任何錯誤訊號」。
`_heal_tick` 的 watchdog 救不了它(watchdog 判的是「TC4 沒推」,而這裡是「我們沒在收」),
`_check_stale` 也救不了(它只在 recv 逾時時被呼叫,而執行緒已經死了)。

**修法**:`handle_raw` 包 try/except Exception + `logger.exception` + 計數器;
並在 `_start_listener` 記下 thread 物件,由 healer 每輪檢查 `self._listener.is_alive()`,
死掉就重起 + 告警。

**風險**:無契約影響。但「不懂的 error 不要 catch」的鐵則要求 catch 後有具體處理 ——
這裡的處理是「記帳 + 續行 + 讓 healer 看得到」,不是純 log 吞掉。

**effort**:S

---

### B01-13 【medium】`_seen_lock` 每則訊息取一次鎖,包含不是自己的 symbol

**證據**

```python
# copycat/live/stock_source.py:925-936
    def handle_raw(self, raw: str) -> None:
        msg = self._realtime_msg(raw)
        if msg is None: return
        quote = msg.get("Quote", {})
        symbol = str(quote.get("Symbol", ""))
        if symbol:
            with self._seen_lock:
                self._seen.add(symbol)      # ← 每則、任何 symbol
        if self._on_message is not None:
            self._on_message(quote)
```

`_seen` 因此會長成「行程內所有 session 訂過的全部 symbol」(~450 個),而它的唯一讀者
`_health_check`(`stock_source.py:686-688`)只查自己那幾十檔。

**影響**:單則 ~0.2 µs(uncontended lock)+ set 成長。小,但它是 5× 放大後的其中一份,
且 `_seen_lock` 與 `threading.Timer` 執行緒(可能 150 條)競爭。

**修法**:併進 B01-01 的分派(只有自己的 symbol 才進 `handle_raw`);
或就地加一行 `if symbol not in self._subscribed: return`。

**effort**:S

---

### B01-14 【low】`api.lock` 把一條 session 上所有 REQ 完全序列化,`overlay_sem(4)` 的併發是假的

**`api.lock` 序列化了什麼**(問題 5 的答案):

| 呼叫者 | 路徑 | 頻率 |
|---|---|---|
| `subscribe_symbol` / `unsubscribe_symbol` | `_resub` → `_rt_request` ×2 | 使用者操作 |
| 自癒 watchdog | `_heal_resub` → `_rt_request` ×2 | corr 每 300 s ×8(見 B01-11) |
| 個股零推播健檢 | `_health_check` → `_heal_resub` | 訂閱後 10/20/40/60 s |
| `_check_stale` 重連 | 150 檔 × 2 REQ,**整段持 `self._lock`** | 斷線時 |
| 回補 | `_collect_history` → SubHistory + N 頁 GETHISDATA | 開盤每檔一次 |
| CDP 基準暖機 | `fetch_daily_bars` → 同上 | `signal_hub` 啟動 + 每日 |
| K 線 / overlay | `fetch_bars_range` / `fetch_day_minutes` | 使用者開圖 |
| `QUERYALLINSTRUMENT(Fut2)` | `list_stock_futures`,實測 1.93 s | boot 一次 |
| wrapper `Pong` | KeepAlive 執行緒 | 每 PING |

CLAUDE.md 提到的「回填 DK 與 CDP 基準暖機共用同一把 TC4 `api.lock`」在這裡得到印證,
而且範圍比那句話更大 —— **同一條 session 上的一切都共用**。

`app.py:547` 的 `overlay_sem = asyncio.Semaphore(4)` 想限流,但四條 `to_thread` 出去之後
全部排在同一把 `api.lock` 上,**實際併發度仍是 1**。150 檔群組檢視 = 150 × (1 SubHistory +
1~N GETHISDATA) 完全序列。

**好消息(反向發現)**:**REALTIME 推播完全不吃 `api.lock`** —— 它走 listener 執行緒上的
獨立 SUB socket。所以**回補不會塞住即時流**(問題 7 的答案:不會)。`_collect_history` 的
`time.sleep` 也在鎖外(`tc4.py:1009`),不會把鎖抱著睡。

**影響**:不是 tick 熱路徑,但直接決定「開一個 150 檔群組要等多久」。prod log 實測 TXO 回補
16 輪 × 259 檔 ≈ 4000 發 REQ / 9 秒 ⇒ 單發 REQ round-trip ~2.2 ms。個股 150 檔的 overlay
最壞 = 150 × 2.2 ms × 頁數。

**修法(需先 probe)**:同一個 `SessionKey` 能不能開第二顆 REQ socket?若可以,
做一個 2–4 顆的 REQ socket pool,把「歷史取數」與「訂閱管理」分道 —— 訂閱/退訂就不會
再排在一次 150 檔回補後面。**這是本區塊唯一需要對 TC4 做新實驗才能決定的改法。**

**風險**:TC4 的 refcount key 是 `symbol|DataType|Start|End`,與 socket 無關,所以
pool 不會改變訂閱語意(**推測**,要 probe 驗)。`close_worst_secs()` 的推導
(`tc4.py:137-162`,關機預算三方同源契約,`server/shutdown_budget.py` + `run.ps1` +
`__main__.py`)是以「一把鎖 + 一顆 socket」推的,pool 會讓 `TC4_LANE_DEPTH` 的意義改變
—— 這是 CLAUDE.md §4 明列的契約,改 lane 形狀要同步改。

**effort**:L(含 probe)

---

### B01-15 【low】每則訊息配置 ~85 個物件,全部是短命 str

一則 893 byte / ~40 欄的 quote:`json.loads` 建 40 個 key str + 40 個 value str + 2 個 dict。
再加 `[:-1]` 的 bytes 複本、`decode` 的 str、`raw[idx+1:]` 的第二個 str。
× 5 條 session = **每則 ~425 個物件**。

在 1500 則/s 下 = 64 萬物件/秒的配置與回收壓力,會直接推高 gen0 GC 頻率。

**修法**:B01-01(5→1)直接砍 80%。再往下就是 msgspec `Struct`(B01-16)—— 它只建一個
Struct 物件 + 需要的欄位,不建 dict。

**量測建議**:`gc.get_stats()` 的 gen0 collections 在開盤前後對照;或 `py-spy`(已裝)。

**effort**:併入 B01-01

---

### B01-16 【medium】解碼器可以換掉,實測 3.6×(但這是第二順位,不是第一)

**實測**(893 byte 真實形狀訊息,`bench_codec.py`):

| 方案 | 每則 | 相對 |
|---|---|---|
| 現況 `bytes[:-1].decode() → find → json.loads(str slice)` | **6.48 µs** | 1.0× |
| `orjson.loads(bytes slice)` | **2.18 µs** | **3.0×** |
| `orjson.loads(memoryview slice)` | 2.33 µs | 2.8× |
| `msgspec.json.Decoder(Struct).decode(bytes)` | **1.79 µs** | **3.6×** |
| `msgspec` + memoryview | 1.79 µs | 3.6× |

全鏈(decode + parse)對照(`bench_full.py`):

| | 每則 |
|---|---|
| 現況:`json.loads` + `parse_stock_realtime` | **30.06 µs** |
| msgspec decode + 手刻 parse(預算 key 表 + fast_taipei,保留 `Decimal` 語意) | **13.99 µs** |

(手刻版沒有建三個 frozen dataclass,真正落地的版本**推測**落在 17–20 µs。)

**要動哪裡**
1. `tc4.py:1245` `_listen_loop`:`raw = sock.recv()` 保留 bytes,不 decode。
2. 新增 `handle_frame(buf: bytes)`;`handle_raw(raw: str)` 留成 `handle_frame(raw.encode())`
   的薄轉接 —— **`handle_raw` 是四個子類的覆寫點,也是 `tests/live/test_tc4.py` /
   `test_stock_source.py` 等數十處測試的注入點,簽名不可改**。
3. `_realtime_msg`:`idx = buf.find(b":")` → `decoder.decode(buf[idx+1:-1])`。
4. `_req`(`tc4.py:570-583`)也用 `json.loads`,但那是 REQ 路徑(每秒個位數),**不必動**。
5. `pyproject.toml` 的 `dependencies` 從 `[]` 變成 `["msgspec"]` —— 這會打破「runtime
   stdlib-only」的專案哲學,要 user 拍板。

**取捨**
- msgspec / orjson 都有 Windows x64 的預編譯 wheel,無編譯相依。
- msgspec 的 `Struct` 方案還能順便砍掉 `parse_stock_realtime` 的 `dict.get` 成本
  (屬性存取比 dict 查表快),但代價是 TC4 的欄位集合要寫死成 schema —— 而
  `tc4-market-facts` skill 記了一堆「欄位名未實測 / 值域未實測」的事實
  (`stock_source.py:211 _int_field` 就是「依序試三個欄位名」)。**建議先用
  `msgspec.json.Decoder()`(無 schema,回 dict)拿到 1.8 µs,不要一次上 Struct。**
- 若要維持 stdlib-only:光是把 `decode → slice → loads` 改成 `json.loads(buf[idx+1:-1])`
  實測是 8.73 µs,**比現況還慢**(bytes 切片複本 + C 層 encoding 偵測),
  所以 stdlib 路線在這一段沒有免費午餐,真正的 stdlib 解法是 B01-01(少做 4 次)。

**effort**:M

---

### B01-17 【low】`fetch_backfill` 的 round 制在最壞情況會做 ~4000 發 REQ

**證據**(prod log 2026-09-11,TXO 開盤回補)

```
09:05:10  backfill round 1: 259 pending, 1 ticks
09:05:11  backfill round 2: 259 pending, 1 ticks
...
09:05:15  backfill round 10: 241 pending, 83 ticks
```

```python
# copycat/live/tc4.py:880-897
        for rnd in range(1, _HARVEST_ROUNDS + 1):       # 16 輪
            if rnd > 1 and self._poll_wait:
                time.sleep(self._poll_wait * 0.5)
            for sym in pending:                          # 最壞 259 檔
                symbol_ticks = self._fetch_symbol_ticks(sym, start, end)
```

16 × 259 ≈ 4144 發 `GETHISDATA`,每發 ~2.2 ms(從 log 時間戳回推:每輪 ~0.57 s / 259 檔)。
整段 ~9 s,期間 TXO session 的 `api.lock` 幾乎連續被持有。

**這條不算問題**:它在獨立 session 上(不影響個股/期貨),且已經從「逐檔 Sub→等→收」
(實測 10 分鐘)優化到 9 秒。但如果之後要把回補時間再往下壓,這裡就是 REQ pool(B01-14)
的主要受益者。

**effort**:—(併入 B01-14)

---

## 4. 工具選型建議與取捨

| 工具 | 用在哪 | 解決什麼 | 代價 | 結論 |
|---|---|---|---|---|
| **msgspec** | `tc4.py::_realtime_msg`(先用 no-schema `Decoder()`) | 解碼 6.48 → 1.79 µs(3.6×) | 破壞 runtime stdlib-only;Windows 有 wheel 無編譯相依 | **有條件導入**(user 拍板 stdlib-only 政策後) |
| **orjson** | 同上 | 6.48 → 2.18 µs(3.0×) | 同上;但沒有 Struct 路線的後續上檔 | 若只想換一行,選它;否則選 msgspec |
| **uvloop** | event loop | — | **Windows 不支援,無 wheel** | **不可行,別提** |
| **winloop** | uvloop 的 Windows 移植 | 推測 1.5–2× loop 吞吐 | 小眾、與 uvicorn 整合未驗、ProactorEventLoop 的 subprocess/COM 語意可能改變(capital 走 COM) | **不建議**(風險 >> 收益,且本區塊瓶頸不在 loop 本身) |
| **zmq.asyncio** | 把 recv 搬上 loop | 省掉 `call_soon_threadsafe` 的 8.1 µs | 解碼改在 loop 上跑,與訊號/廣播/下單搶同一條執行緒;且 Windows 的 zmq.asyncio 走 Proactor + 額外 poller 執行緒,實測收益未驗 | **不建議**;B01-01 + B01-02 的收益更大且風險更低 |
| **numpy / polars** | — | — | 這一層是 per-message 的字串解析,不是陣列運算;numpy 對單筆 scalar 是**負優化** | **不要動**(回測 / 廣度那些區塊才是它們的場子) |
| **獨立 process 跑 recv + parse,shm ring 傳 struct-packed** | 整個 ingress | 完全脫離 GIL;可把 tick 壓成 32 byte 定長 record | XL:要自寫 ring buffer、跨 process 生命週期、Windows shm 語意、debug 難度翻倍;而且要先確認 C 層解碼真的是瓶頸 | **現階段不建議**;做完 B01-01/02/03 再量一次才談 |
| **py-spy**(已裝) | 量測 | 無侵入 sampling profiler,可對 prod server 直接 `py-spy top --pid` | 無 | **立刻用** |

### 建議的執行順序(收益/風險比排序)

1. **B01-03 `_taipei_time`**(S,零契約)— 個股 parse −29%,一天就能做完。
2. **B01-09 TXO symbol 早退**(S)— 直接砍掉 309 萬則/日的假工作。
3. **B01-08 RCVHWM + 積壓指標**(S)— 這是資料正確性,不是效能。
4. **B01-12 listener 例外防護**(S)— 可用性。
5. **B01-04 `_parse_levels` key 表**(S)。
6. **B01-10 `wait_for` 拆掉**(S)。
7. **B01-06 fork wrapper 進版控**(M)— 解鎖 8、11、5 的改法。
8. **B01-02 交接批次化**(M)— 8.1 → ~0.4 µs/則。
9. **B01-01 五條 listener 收成一條**(L)— 本區塊最大的單一收益,但要先有 6。
10. **B01-16 換解碼器**(M)— 等 user 拍板 stdlib-only 政策。
11. **B01-14 REQ pool probe**(L)— 需要對 TC4 做新實驗。

做完 1–9(**完全不新增任何相依**),入口每則成本從 ~124 µs 降到**推測 ~25 µs**(−80%);
再加 10,降到**推測 ~18 µs**。

---

## 5. 不要動的地方

| 位置 | 為什麼不要動 |
|---|---|
| `tc4common.py::to_milli_units` 的 `Decimal` | 實測只有 0.449 µs,手刻整數版 0.369 µs —— 省不到 0.1 µs。而檔內明文:「Decimal 是截斷、float round 是 banker's rounding,在 tick 邊界會分岔」。動它的期望收益是零、風險是價格錯一檔。 |
| `session.py` 整檔(80 LOC) | 純字串/time 判定,每次訂閱才呼叫一次,不在熱路徑。 |
| `tc4common.py::iter_qry_pages` | 回補分頁,離線路徑。 |
| `stock_source.py` 的 `parse_1k_bars` / `parse_dk_bars` / `aggregate_1k_to_daily` | 回補 / K 線路徑,每次開圖跑一次。目前是 O(n) + 一次 sort,對 4.8 萬列 1K 也只有幾百 ms。**這裡換 numpy 是過度工程**(輸入是 list[dict] of str,轉換成本比計算高)。 |
| `_apply_variant` / `_next_dk_start` / `_window_offset` 這一整套窗口變體 | 它們是對 TC4 refcount / 凍結快照這兩個實測行為的直接繞法,每一條都有 probe 佐證與 log 判準。看起來複雜,但沒有一行是可以憑「這樣比較乾淨」拿掉的。 |
| `close_worst_secs()` 與關機預算 | CLAUDE.md §4 三方同源契約(`shutdown_budget.py` / `run.ps1` / `__main__.py`),`tests/server/test_shutdown_budget.py` 含 run.ps1 字面 parity。改 timeout 值不必改 run.ps1,但**改 lane 形狀就是改契約**。 |
| `WsBroadcaster`(`server/ws.py`) | per-client 有界 queue、丟最舊保最新、丟包節流結算 —— 設計完整且有 `grep "佇列滿"` 的 prod 判準。不是這區塊的問題。 |
| `zmq.RCVTIMEO = 1000` 的 1 秒輪詢 | 沒有 tick 時每秒一次 `_check_stale()`(一個 `time.monotonic()` 比較就 return),成本可忽略,而它是 stale 偵測的唯一觸發器。 |

---

## 6. 量測方法(怎麼證明快了/慢了)

### 6.1 立刻可做(不動 code)

```powershell
# 1) 抓 prod server 的即時火焰圖(py-spy 已在 .venv)
.venv\Scripts\py-spy top --pid <server pid>
.venv\Scripts\py-spy record --pid <server pid> --duration 60 --output open.svg --subprocesses
# 開盤 08:59 起錄 5 分鐘,看 _listen_loop / json.loads / parse_stock_realtime / strptime 各佔幾 %

# 2) 執行緒盤點(驗證 §1.1 的 15+15)
.venv\Scripts\py-spy dump --pid <server pid>

# 3) 五條 session 的 SubPort 是不是同一個(B01-01 的前提)
#    在 tc4.py:488 那行 logger.info 後面臨時加印 self._sub_port,或直接:
netstat -ano | findstr <TC4 pid>
```

### 6.2 離線 micro-benchmark(已備好,可重跑)

`<scratchpad>/bench_ingress.py`(decode + parse)、`bench_parse.py`(parse 子項)、
`bench_handoff.py`(call_soon_threadsafe / Queue / wait_for)、`bench_codec.py`
(stdlib vs orjson vs msgspec)、`bench_full.py`(全鏈對照)、`bench_gil2.py`(GIL 尾延遲)。
改動前後各跑一次,貼在 verification.md。

### 6.3 線上指標(建議新增到 `/api/health`,這是本區塊目前**完全沒有**的東西)

| 指標 | 怎麼算 | 為什麼要 |
|---|---|---|
| `ingress.msgs_per_sec` | listener 上一個原子計數器 + 每秒取樣差分 | 現在**沒有任何人知道線上到底每秒幾則**,所有容量推算都是推測 |
| `ingress.backlog` | reader deque 長度(B01-01 之後) | B01-08 的丟資料風險唯一的可觀測面 |
| `ingress.decode_us_p99` | 每 1000 則抽樣一次 `perf_counter` | 回歸偵測 |
| `loop.lag_us_p99` | 一支 `while: t0=..; await sleep(0.05); lag = elapsed - 0.05` 的 task | B01-07 的尾延遲,也是未來下單延遲的上游 |
| `tc4.req_wait_us` | `api.lock.acquire` 前後計時 | B01-14 的 head-of-line 證據 |

### 6.4 真環境驗收判準(改動後)

- 開盤 09:00–09:05 `py-spy record`,`json.loads` 的 self time 應從 ~5×N 降到 ~1×N。
- `grep -c "零推播自癒" logs/server-*.log` 在 B01-11 修完後應 < 100/日(現況 1926)。
- `grep "佇列滿" logs/server-*.log` 維持 0(不得因 ingress 批次化而變差)。
- `/api/txo/...` 的 `dropped_foreign_ticks` 在 B01-09 之後應歸零或搬家 —— **先確認前端有沒有讀者**。
- 個股 tick 端到端延遲(TC4 `PreciseTime` → 瀏覽器收到 `ticks` 訊息)在 DevTools 對照:
  現況受 `tick_flush_secs=0.1` 支配,ingress 改動不應讓它變差。

---

## 7. 開放問題(需要 user 回答或需要 probe)

1. **五條 session 的 `SubPort` 是否確實相同?** 跨 session 可見性已由 `models.py:16` /
   `aggregate.py:46` 的註解 + 309 萬 foreign ticks 實證,但沒有一行 log 印過實際 port。
   B01-01 的整個前提壓在這上面 —— 一行 `logger.info` 就能確認。
2. **線上真實訊息速率是多少?** 目前全靠 309 萬 foreign ticks/日 回推。開盤瞬間的峰值
   完全是推測。加一個計數器就有答案。
3. **corr 的八條海外腿到底有沒有資料?**(B01-11)Touchance 訂閱是否涵蓋 CME/CBOT/OSE/CFE/SGX
   即時?這決定是「關掉自癒」還是「修自癒」。
4. **同一個 `SessionKey` 能不能開第二顆 REQ socket?**(B01-14)要對 TC4 做 probe。
   若可以,開盤 150 檔 overlay 的體感會有數量級改善。
5. **`pyproject.toml` 的 runtime stdlib-only 是硬政策還是慣例?** 這決定 B01-16 能不能做。
   我的建議:ingress 是唯一值得破例的地方(3.6×,單點,wheel 無編譯相依);
   其餘區塊繼續 stdlib-only。
6. **`dropped_foreign_ticks` 前端有讀者嗎?**(B01-09 的前置)
7. **要不要把 `spikes/TCPY/` 進版控?**(B01-06)這是「要下實單」這件事的先決條件,
   不只是效能問題。
