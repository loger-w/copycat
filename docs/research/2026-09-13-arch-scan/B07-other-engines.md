# B07 — 指數 / 期貨 / 相關係數 / 江波圖引擎:效能與架構檢查

分析日期 2026-09-13。工作樹 `C:\side-project\copycat`(master `caca1d30`)。
全部數字皆為本機實測(`.venv\Scripts\python`,Python 3.13.13,Windows 11),
量測腳本留在
`C:\Users\USER\AppData\Local\Temp\claude\C--side-project-copycat\2f320e31-68fc-4cfd-859c-b63b666e7f79\scratchpad\bench_*.py`,
未寫入 repo。

---

## 0. 一句話結論

這四個引擎裡**只有一個真正的效能問題,但它很大**:
`CorrState.correlations()` 每秒在 event loop 上整批重算 11 腿 × 3 窗的 Pearson,
實測 **14–19 ms/次**,而且**沒有任何 WS client 連著時照算**。
其餘三個引擎(index / futures / river)的每拍成本都在微秒到百微秒量級,
**不該動**——對它們導入 numpy / polars 是純粹的過度工程。

第二層的問題不是「算得慢」而是「**塞住**」:
所有 REALTIME 解析(`parse_stock_realtime`,實測 25.6 µs/則)都跑在 **event loop 執行緒**上,
加上 corr 那 19 ms,event loop 在盤中有可觀的 jitter,而**全庫沒有任何 event loop lag 探針**——
這對「要下實單、不能塞住」的目標是最該先補的觀測性缺口。

---

## 1. 架構地圖

### 1.1 四個引擎與它們的資料來源

```
TC4 (Touchance 4.0 桌面 app, localhost ZMQ)
  │
  ├─ session #3  StockQuoteSource(in_index_heal_window_now 13:25 閘)
  │     └─ IX0001 REALTIME push + 當日 1K 回補
  │           → IndexEngine._handle_quote  (loop thread)
  │
  ├─ session #4  FuturesQuoteSource(in_futures_session_now 日夜盤各寬 5 分)
  │     └─ TC.F.TWF.{TXF,MXF,TMF}.HOT REALTIME
  │           → FuturesEngine._handle_quote (loop thread)
  │           → 五檔 / 成交 / ref-upper-lower / resolved_contract
  │
  └─ session #5  CorrQuoteSource(逐腿 segment_leg_gate,全天 UTC 訂閱窗)
        └─ 10 條 tc4 腿(TWN/YM/ES/NQ/SXF/NK225M/VX/CL/GC/TSMC)REALTIME
              → CorrelationEngine._handle_quote (loop thread)
                   ├─ book → self._books[key]   (相關係數用「中價」)
                   └─ tick.price → RiverState.push (江波圖用「成交價」)

TPEx MIS 公開端點 (https://mis.twse.com.tw)
  └─ 5 s urllib poll(asyncio.to_thread)→ IndexEngine._apply_otc
        → 櫃買現價 + 本機合成分鐘 OHLC

FuturesEngine.state()  ←(每秒 pull,不訂閱)── CorrelationEngine base 腿 TXF
FuturesEngine.fetch_day_1k() ←(江波圖台指腿 1K 回補)── CorrelationEngine
```

**關鍵的結構性約束(CLAUDE.md §8 / tc4-market-facts)**:
base 腿(台指)**必須**讀 `futures_engine.state()` 而不是自己訂 `TXF.HOT`;
台指的 1K 也**必須**由持有該訂閱的 futures session 問。
理由是 TC4 的 refcount key 是 `symbol|DataType|Start|End`、上游 feed 卻以 **symbol** 為單位,
多一把 key 就多一個「歸零時把整個 symbol 的 feed 帶走」的引信,而失效樣態是**永久零推播且無錯誤訊號**。
→ **任何「把 corr 改成自己訂 TXF 省一次 dict 查表」的優化一律禁止。**

### 1.2 corr / river 的資料流(問題 1、2)

```
每秒一拍(CorrelationEngine._run → tick_once,tick_secs = 1.0):

  ① 取樣
     for leg in 11 legs:
       - base(TXF, source=futures_engine):
            self._txf_state_getter()  →  futures.state()  → products[TXF] 的 bids/asks/p
            fingerprint = (tuple(bids), tuple(asks), p)   ← 內容變化才算「有更新」
       - 其餘 10 腿(source=tc4):
            self._books[key]  ← 由 _handle_quote 在推播時寫入
       - fresh 判定:now - last_update <= stale_secs(30 s)
       - st.mid = mid_from_book(bids, asks) = (bids[0][0] + asks[0][0]) // 2

  ② CorrState.push(now, mids, session)
     11 條 deque 各 append 一筆 (ts, mid|None)
     cap = int(2 * max_window / sample_secs) = 3600
     _evict:popleft 掉 ts < now - 1800 的

  ③ broadcast(self.state())        ← ★ 這裡是 14–19 ms 的所在
     state() → self._state.correlations(now)

  ④ _river_tick(session)
     RiverState.set_session + 台指腿 push(minute_end, price)
     river_broadcast(self._river.delta(seq))
```

`correlations(now)` 的實際計算(`copycat/live/corr_state.py:113-126`):

```python
for leg in self._legs:                       # 10 條非 base 腿
    paired = self._paired_returns(leg, now)  # ← 每腿重建一顆 dict + 全掃
    for window in self._windows:             # 60 / 300 / 1800
        cutoff = now - window
        xs = [rb for ts, rb, _ in paired if ts >= cutoff]   # 全掃
        ys = [rl for ts, _, rl in paired if ts >= cutoff]   # 再全掃一次
        row[f"n{window}"] = len(xs)
        row[f"w{window}"] = self._corr(xs, ys, ...)          # statistics.correlation
```

而 `_paired_returns`(`corr_state.py:82-111`)每次呼叫做的事:

```python
leg_by_ts = dict(leg_series)      # ← 把 1800~3600 筆 deque 整份倒成 dict
for ts, base_mid in base_series:  # ← 1800~3600 圈
    leg_mid = leg_by_ts.get(ts)
    ...
    rb = log_return(prev_base, base_mid)   # math.log
    rl = log_return(prev_leg, leg_mid)     # math.log
...
return [row for row in out if row[0] >= now - self._max_window]  # ← 再全掃一次
```

**每秒的總工作量**(滿窗 1800 樣本):
| 項目 | 次數/秒 |
|---|---|
| dict 建構(1800 entry) | 10 |
| deque 全掃 | 10 |
| `math.log` | 36,000 |
| list comprehension 全掃(3 窗 × 2) | 60 |
| `statistics.correlation`(內部用 `fsum`) | 30 |

### 1.3 江波圖 RiverState 的資料結構(問題 2)

`copycat/live/river_state.py:42-101`。

```
_minutes    : dict[leg_key, dict[offset:int, price_milli:int]]   # 日盤 300 格 / 夜盤 840 格 × 11 腿
_last_write : dict[leg_key, (offset, price) | None]
_end_rank   : dict[leg_key, int]     # 收盤 clamp 名次,per-leg 一個數字
```

每拍成本:
- `set_session`:一次 tuple 比較(相同 → 立即 return)。
- 台指腿 `push`:`offset_of`(幾次整數運算)+ `close_clamp_rank` + 一次 dict 寫入 → **O(1)**。
- `delta(seq)`:建一顆 11 key 的 dict,每 key 一顆 `{"m":…, "p":…}` → **~11 個小 dict/秒**。

**後端 river 每拍成本是微秒級,完全不是問題。**
但 `delta()` 有一個語意上的浪費(見 Finding B07-10):
`_last_write` **從不清空**,所以每秒都把 11 腿的「最後寫入」全部重送,
即使某條腿(例如台北上午的 VX)已經幾小時沒動。
前端 `useRiver.applyDelta` 對每個非 null 的腿做 `{...leg.minutes}` 展開複製 —
夜盤滿窗時是 11 × 840 entry 的物件複製,實測 **0.26 ms/秒**(Node 量測,見 §5)。

`snapshot()` 每腿 `dict(minutes)` 整份複製 + `max(minutes)`,只在 REST / WS 首則呼叫,不是熱路徑。

### 1.4 櫃買 MIS poll(問題 3)

`copycat/server/index_engine.py:508-517` + `copycat/server/mis.py:41-63`。

```python
async def _mis_loop(self) -> None:
    while True:
        try:
            snap = await asyncio.to_thread(self._mis_fetch)   # ← 在 worker thread
            if snap is not None:
                self._apply_otc(snap)                          # ← 回到 loop
        except Exception:
            logger.exception("MIS loop 非預期失敗(續行)")
        await asyncio.sleep(self._poll)                        # 5.0 s
```

**答案:是同步 urllib,但跑在 `asyncio.to_thread` 的 worker thread,不卡 event loop。**
這一點做對了。

但它每 5 秒建一條**全新的 TLS 連線**(`urllib.request.urlopen` 不做連線池):

```
實測(本機 → mis.twse.com.tw,674 bytes 回應)
  urlopen  #0  69 ms   #1  34 ms   #2  59 ms      ← 每次都重新握手
  keepalive#0  36 ms   #1   7 ms   #2   7 ms      ← http.client 持久連線
```

→ 每次 poll 多付 ~30–50 ms 的握手 + TLS CPU。盤中 4.5 小時 = 3,240 次 poll,
每天約 **2.5 分鐘的純 TLS 握手**分散在 worker thread 上。
不是 event loop 的問題,但是實打實的浪費,而且讓櫃買現價多 40 ms 的陳舊度。

另外 `mis.py` 的 `_fail_streak` 是 **module-level global**,由 worker thread 讀寫。
GIL 下不會撕裂,但它讓「同一個 process 起兩個 IndexEngine」時計數互相汙染(測試 / 側車情境)。

### 1.5 index watchdog 與 broadcast loop 的排程成本(問題 4)

`index_engine._broadcast_loop`(`index_engine.py:669-746`),每 `throttle_secs`(prod = 1.0 s)一拍:

```
每拍固定做的事:
  1. watchdog:  self._twse.stale? + self._in_watch_window() + monotonic 比較
                 → in_watch_window_now() 內部 datetime.datetime.now().time()
  2. heal 窗判定: self._now_fn()  ← 第二次 datetime.now()
                 self._is_trading_day(self._today_fn())  ← frozenset O(1)
  3. _minutes_lag_exceeded(): max(self._twse.minutes)   ← 最多 270 鍵
  4. txf: self._txf_getter()  ← TXO runtime.spot_millipts()
  5. _check_spot_silence(p)
  6. if self._dirty: _publish(self._payload())
```

三個 `datetime.datetime.now()`/`.today()` 呼叫 + 一次 `max()` over ≤270 鍵。
**總計遠低於 100 µs/拍。** 這裡不要動。

`_payload()`(`index_engine.py:790-801`)只組 scalar 小 dict;
`minutes` 全量只在 `_push_minutes_once` 那一則帶出去(回補成功後一次)。設計正確。

watchdog 判定窗 09:00–13:25(`_WATCH_START` / `_WATCH_END`)本身零成本——
它是**正確性**機制不是效能機制,而且 `_WATCH_END` 與 `stock_source._INDEX_HEAL_END`
是 CLAUDE.md 明文的跨檔契約(`tests/server/test_index_engine.py::test_watch_end_is_the_index_heal_gate_boundary` 鎖住)。

### 1.6 期貨五檔 + resolved_contract 的更新路徑(問題 5)

```
ZMQ listener thread (futures session)
  _listen_loop → sock.recv() → handle_raw
     → _realtime_msg: raw.find(":") + json.loads      ← 實測 5.9 µs / 842 bytes
     → _note_push(symbol, quote): 4-tuple 指紋 + 兩次 dict 寫
     → _on_message(quote)  =  FuturesEngine._on_quote_threadsafe
          → loop.call_soon_threadsafe(self._handle_quote, quote)
                                                       ↓
event loop thread
  FuturesEngine._handle_quote (futures_engine.py:604-653)
     product_from_symbol(symbol)          ← regex,實測 ~0.5 µs
     parse_futures_realtime(quote)        ← = parse_stock_realtime,實測 25.6 µs ★
        ├─ _parse_levels × 2  = 10 × to_milli(Decimal) + 10 × _to_int
        ├─ StockMeta          = 4 × to_milli + _to_int + 2 × _hhmmss
        ├─ _taipei_time       = datetime.strptime + timedelta + 2 × strftime  ← 9.97 µs ★
        └─ derive_side / _best_limit_price / is_trial_window
     st.bids / st.asks / st.p / st.q / st.cum_vol / st.t / st.date  ← 純賦值
     resolve_contract_ym(quote)           ← regex,~0.7 µs
     self._dirty[product] = None
     if self._flush_timer is None: loop.call_later(0.1, self._flush)

  FuturesEngine._flush (futures_engine.py:655-694)  每 0.1 s,只對 dirty 商品
     st.payload(product)  ← 建 dict + list(bids) + list(asks)
     self._broadcast(...)  → WsBroadcaster.publish → per-client queue
```

**這條路的設計是對的**:0.1 s coalesce + per-product dirty set + 「payload 是全量快照,合併無資訊損失」。
唯一的成本集中在 `parse_stock_realtime` 的 25.6 µs,而其中 **39% 花在 `_taipei_time`**(見 Finding B07-04)。

`resolved_contract` 是 `st.resolved_ym` 的純快取讀取,零成本。
`_schedule_leaf_fallback` 只在解析出 ym 時呼叫,而且第一行就 `if self._loop is None or self._leaf_timer is not None: return`——
健康情境下 timer 已存在時直接早退。但注意它在早退之前仍會走 `_handle_quote` 的 `resolve_contract_ym`(regex ×1~3),
每則推播都算一次。可用 `if st.resolved_ym is None or 換月訊號` 短路,收益 ~0.7 µs/則,量級太小,不建議動。

### 1.7 各引擎的 task / thread 清單(問題 6)

**穩態 asyncio task(這四個引擎):**

| 引擎 | task | 間隔 | 備註 |
|---|---|---|---|
| IndexEngine | `_mis_loop` | 5 s(+ fetch 延遲) | 每拍一次 `to_thread` |
| IndexEngine | `_broadcast_loop` | 1.0 s | watchdog + heal 判定 + publish |
| IndexEngine | `_rollover_loop` | 60 s | 交易日 gate 最前面 |
| CorrelationEngine | `_run` | 1.0 s | `tick_once`(★ 19 ms) |
| FuturesEngine | — | — | **零常駐 task**,用 `call_later(0.1)` timer 鏈 |

→ **穩態 4 條常駐 task + 1 條 0.1 s 的 `call_later` timer 鏈。**

條件性 task(只在故障 / 啟動時):
`IndexEngine._retry_task`(single-flight,`_schedule_retry`)、
`CorrelationEngine._backfill_task` / `_resub_task` / `_backfill_retry_tasks`、
`FuturesEngine._resub_task` / `_leaf_tasks` / `_leaf_timer`。

**執行緒**(這四個引擎相關,共 3 條 TC4 session):
每條 `TC4QuoteSource` = 1 × ZMQ SUB listener(`_listen_loop`,`RCVTIMEO=1000`)
+ 1 × healer(`_heal_loop`)+ 1 × wrapper 內部 KeepAlive → **9 條 daemon thread**。
加上全 app 的 5 條 session(txo / stock / index / futures / corr)= **15 條**,
再加 asyncio 預設 `ThreadPoolExecutor`(`min(32, cpu+4)`)。

**這裡有一個重要的正面事實**:每條 session 各自 `Connect()` 拿到**自己的 SubPort**
(`tc4.py:487` `self._sub_port = q["SubPort"]`),所以 5 條 listener **不是**各收一份全市場火線後自己過濾——
每條只收自己訂閱的那批。`json.loads` 沒有被乘 5。這個設計是對的,不要改。

---

## 2. 熱路徑逐條(依頻率排序)

### HP-1 `CorrelationEngine.tick_once` — 每 1 秒,在 event loop 上
`copycat/server/corr_engine.py:300-324`

實測(11 腿、3 窗、1800 樣本):`state()` 內的 `correlations()` = **14.1 ms**;
滿 cap(3600 樣本)時 = **18.8 ms**。
拆解:`_paired_returns` × 10 = 9.2 ms、三窗過濾 + 30 次 `statistics.correlation` = 4.9 ms。

### HP-2 `FuturesEngine._handle_quote` — 每則期貨推播,在 event loop 上
`copycat/server/futures_engine.py:604-653`

25.6 µs/則 × 3 商品。TXF 實測約 516 則/分(檔頭註),三商品合計盤中約 **15–30 則/秒**
→ 0.4–0.8 ms/秒。開盤瞬間可能十倍。

### HP-3 `CorrelationEngine._handle_quote` — 每則 corr 腿推播,在 event loop 上
`copycat/server/corr_engine.py:265-287`

同樣 25.6 µs/則,10 條腿。美盤時段(ES/NQ/YM/CL/GC 同時活躍)是這條路最忙的時候。
**且這裡只用到 `tick.price_milli` 與 `book.bids/asks`** — meta 的 6 次 Decimal 轉換、
`_taipei_time` 的 strptime、`derive_side`、`is_trial_window` 全部丟掉。

### HP-4 `TC4QuoteSource._listen_loop` / `handle_raw` — 每則推播,在 listener thread
`copycat/live/tc4.py:1226-1252` + `1189-1211`

`raw.find(":")` + `json.loads` = **5.9 µs / 842 bytes**,加 `_note_push` 的 4-tuple 指紋。
比 loop 側的 parse 便宜 4 倍。

### HP-5 `IndexEngine._broadcast_loop` — 每 1 秒
< 100 µs。**不是熱點。**

### HP-6 `IndexEngine._mis_loop` — 每 5 秒,在 worker thread
34–69 ms(TLS 握手主導)。不卡 loop。

### HP-7 `FuturesEngine._flush` — 每 0.1 秒(有 dirty 時)
3 × `st.payload()`(建 dict + 2 次 list 複製)≈ 10 µs。**不是熱點。**

### HP-8 `RiverState.push` / `delta` — 每 1 秒
微秒級。**不是熱點(後端)。**

### HP-9 `FuturesEngine._check_1k_health` — 每次 `/api/market/bars/{TXF}?tf=1`,在 executor thread
`copycat/server/futures_engine.py:413-476`

前端 `useMarketBars` 盤中每 **60 秒** poll 一次(`POLL_MS = 60_000`,`days=30`)。
`server/bars.py` 的兩段式 cache 讓穩態只重抓**當日段**,所以穩態的 bars 數 ≤ ~1,380(allday)
→ 1,380 × `datetime.strptime`(4.3 µs)= **~6 ms**。
冷啟動 / 首次載入會走 30 天歷史段:~29,000 根 → **~125 ms**(一次性)。

### HP-10 `_tradable_minutes_between` — 每個缺格一次
`copycat/server/futures_engine.py:72-90`,逐分 `for` 迴圈 + f-string 格式化,上限 2,880 步。
只在 `(cur_at - prev_at) > 1 分` 時走(有快路徑),健康資料幾乎不進。

---

## 3. Findings

### B07-01 [CRITICAL / 熱路徑] corr 相關係數每秒整批重算 19 ms,而且沒人看也算

**位置** `copycat/live/corr_state.py:82-126`;呼叫點 `copycat/server/corr_engine.py:320-323, 543`

**證據**
```python
# corr_state.py:91   ← 每次呼叫把整條 deque 倒成 dict
        leg_by_ts = dict(leg_series)
# corr_state.py:111  ← 再整份掃一次過濾
        return [row for row in out if row[0] >= now - self._max_window]
# corr_state.py:121-122  ← 每窗各掃兩次同一份 paired
                xs = [rb for ts, rb, _ in paired if ts >= cutoff]
                ys = [rl for ts, _, rl in paired if ts >= cutoff]
```

**實測**
```
correlations() full : 14.122 ms / call   (11 legs, 3 windows, 1800 samples)
  └ _paired_returns x10 : 9.212 ms
  └ statistics.correlation(1800) : 0.211 ms  × 30 次
correlations() full : 18.791 ms / call   (滿 cap = 3600 samples)
push()              : 0.0039 ms / call
```

**檔頭註解是錯的。** `corr_state.py:4-7` 寫:

> `statistics.correlation`(stdlib,內部用 fsum)對 1800 樣本實測 0.15 ms,**整輪 tick 外推不到 1 ms**。

那次量測只量了 `statistics.correlation` 本身(我這裡量到 0.211 ms,同量級),
**漏掉了 `_paired_returns` 與六趟 list comprehension**——真值是 14–19 ms,差 **14–19 倍**。
這是一條「rationale 看起來很嚴謹但基準打錯」的典型。

**影響**
- event loop 每秒被同步佔住 14–19 ms(1.4–1.9% duty,但是**單次 19 ms 的 stall**)。
  這 19 ms 內:期貨 0.1 s flush 遲到、WS 心跳遲到、所有 `call_soon_threadsafe`
  排進來的 tick 解析全部排隊。對「下實單、不能塞住」是直接的 latency jitter 來源。
- 每天(夜盤含在內,corr 全天跑)≈ 19 ms × 86,400 = **27 分鐘的純 CPU**。

**修法(不需要 numpy)**:改成**滾動矩累加 + 週期 fsum 精確重播**。
每收到一筆新的配對報酬 `(rb, rl)` 時,對每個窗更新 6 個累加量
`(n, Sx, Sy, Sxx, Syy, Sxy)`;逐出時反向扣除。Pearson 由矩直接算:
`r = (n·Sxy − Sx·Sy) / (√(n·Sxx − Sx²) · √(n·Syy − Sy²))`。

我寫了原型並實測(`scratchpad/bench_incr.py`,純 stdlib):
```
OLD correlations() : 18.791  ms
NEW correlations() :  0.0198 ms      ← 約 950×
OLD push()         :  0.0061 ms
NEW push()         :  0.0419 ms      ← 多 36 µs
淨每秒成本          : 18.80 ms → 0.062 ms   (約 300×)
max |r_old − r_new| : 1.1e-3  (跑 3600 拍之後)
```

那 1.1e-3 的差含兩個來源:(a) 我的原型簡化了相鄰容差判定、(b) 純增量的浮點漂移。
**檔頭那條「不維護增量統計量」的 rationale 值得保留其精神**——收法是**混合**:
每 60 秒用 `math.fsum` 對當前窗精確重播一次矩,把漂移釘死。實測重播成本:
```
exact fsum re-seed, 10 legs × 1800-window : 3.834 ms   (每 60 s 一次 → 攤提 0.064 ms/s)
```
合計 0.062 + 0.064 = **~0.13 ms/秒,對比現在的 18.8 ms/秒,~145×**。
而且「增量 = 整批」這件事從「靠論證」變成「每分鐘機械驗證一次」——比原設計更強。

**風險**:`CorrState` 是零 IO 純狀態機,測試齊全
(`tests/live/test_corr_state.py` + `tests/server/test_corr_engine*.py`)。
改法不碰任何跨檔契約(`pairs` 的 wire 形狀 `{wN, nN}` 逐字不變)。
可以用 characterization test 先釘住現行輸出(同一串 mids 餵進去,比對 `correlations()` 的
完整 dict),再換實作。**Effort: M。**

---

### B07-02 [HIGH / 熱路徑] `tick_once` 無條件廣播 → 零 client 時仍付 19 ms/秒

**位置** `copycat/server/corr_engine.py:320-324`

**證據**
```python
        self._state.push(now, mids, session)
        self._seq += 1
        if self._broadcast is not None:      # ← 只檢查 callback 存不存在
            self._broadcast(self.state())    # ← state() 裡就是那 19 ms
        self._river_tick(session)
```
`self._broadcast` = `corr_ws.publish`(`app.py:1003`),而 `WsBroadcaster.publish`
(`copycat/server/ws.py:65-80`)只是 `for queue in self._clients` —
**client 集合為空時整個 publish 是 no-op,但 `state()` 早就算完了。**

**影響**:實務上瀏覽器多數時間不在相關係數那個面板(它是眾多 tab 之一),
夜盤更是幾乎沒人開著。這 19 ms/秒**絕大多數時候是純浪費**。

**修法**:給 `WsBroadcaster` 加一個 `has_clients` property(`return bool(self._clients)`),
`tick_once` 改成
```python
        if self._broadcast is not None and self._has_listeners():
            self._broadcast(self.state())
```
注意:`self._state.push(...)` **必須照跑**(序列要連續累積,不然重新有人連上時窗是空的),
只有 `correlations()` 這一段可以懶算。
搭配 B07-01 之後這條的收益變小(0.13 ms 省不省無所謂),但**兩條都做**才是對的:
B07-01 降階、B07-02 降頻。

**風險**:`seq` 語意。現在 `_seq` 每拍 +1 不論有沒有人聽;前端
`useCorrelation` 只做 `if (next.seq < seqRef.current) return`(不做跳號 refetch),
所以 seq 跳號無害。但 `state()` 也是 `/api/corr/state` 與 `/ws/corr` seed 的來源,
那兩條路必須照算——不能把 `state()` 整個變成「只有廣播時才有值」。**Effort: S。**

---

### B07-03 [HIGH] `/api/corr/state` 是 `async def` 卻做 19 ms 同步運算 → 直接阻塞 event loop

**位置** `copycat/server/app.py:1981-1986`

**證據**
```python
    @app.get("/api/corr/state")
    async def corr_state(request: Request) -> dict:
        corr: CorrelationEngine | None = request.app.state.corr
        if corr is None:
            raise HTTPException(status_code=503, detail={"error": "CORR_NOT_READY"})
        return corr.state()        # ← 19 ms 純 CPU,跑在 event loop 上
```
`/ws/corr` 的 seed(`app.py:1996`)同理:`await send_seed(websocket, corr.state())`。

**影響**:FastAPI 對 `async def` route **不會**丟 threadpool。
每次開站 / 每次 WS 重連都是一發 19 ms 的 loop stall。
CLAUDE.md §4 記載的 WS 心跳契約失效症狀正是「所有 WS 每 ~35 s 重連一次,
uvicorn access log 每半分鐘一輪 8 條握手」——真踩到那個症狀時,
每半分鐘就有一發 corr seed 的 19 ms 疊上去。

**修法**:B07-01 修完這條自然消失(19 ms → 0.02 ms)。
若要獨立處置:把 route 改成 `def`(FastAPI 自動丟 threadpool),或在引擎內快取
上一拍算好的 `pairs`(反正它每秒才變一次)。**後者更好**:`tick_once` 算完存起來,
`state()` 直接讀快取——REST/WS seed 與 WS 推播拿到的是同一拍的值,語意更一致。
**Effort: S(依附 B07-01)。**

---

### B07-04 [HIGH / 熱路徑 / 跨區塊] `parse_stock_realtime` 的 `_taipei_time` 用 `strptime`,佔全部解析成本的 39%

**位置** `copycat/live/stock_models.py:89-95`(被 futures / corr / stock / index 四條路共用)

**證據**
```python
def _taipei_time(precise_utc: str, date_utc: str) -> tuple[str, str]:
    s = precise_utc.zfill(12)
    hh, mm, ss, frac = int(s[:2]), int(s[2:4]), int(s[4:6]), s[6:9]
    base = _dt.datetime.strptime(date_utc, "%Y%m%d")          # ← 4.3 µs
    local = base + _dt.timedelta(hours=hh, minutes=mm, seconds=ss) + _TAIPEI_OFFSET
    return f"{local:%H:%M:%S}.{frac}", f"{local:%Y-%m-%d}"    # ← 2 次 strftime
```

**實測**
```
parse_stock_realtime      : 25.59 us / call
  _taipei_time            :  9.97 us   → 手刻整數版 1.45 us   (−8.5 µs)
  strptime 單獨            :  4.31 us
to_milli_units(Decimal)   :  0.389 us  × ~16 次 = 6.2 µs
  整數快路徑版             :  0.137 us  (−0.25 µs × 16 = −4 µs)
resolve+product (regex)   :  1.23 us
```
手刻版做整數算術 + 一顆 `{date_utc: date}` 快取(TC4 的 `TradeDate` 一天只有 1–2 個值),
輸出**逐字相同**(我在 bench 裡 assert 過)。

**影響**:`25.6 → ~13 µs`,**每則 REALTIME 推播省一半**。
對 B07 的量級(futures 3 + corr 10 + index 1 腿)約省 0.2–0.5 ms/秒;
但 stock session(150 檔自選,開盤每秒數百則)那邊省的是**數 ms/秒**——
這條是全 repo 跨區塊收益最大的單點。

**風險 / 契約**:
- `tick.time` 的字面格式 `"HH:MM:SS.fff"` 是多處讀者的契約:
  `futures_engine._last_trade_at` 切 `t[:5]` 與 `t[5:].strip(":.0")`、
  `stock_models.is_trial_window` 的字串比較、成交明細顯示。
  `trade_date` 的 `"YYYY-MM-DD"` 同理(`_ProductState.date`、`bars_range` 的 `end >= st.date`)。
  → **改法必須是「輸出逐字相同」的純內部替換**,加一條 property-based 對拍測試
  (隨機 `PreciseTime` × `TradeDate`,新舊兩版逐字比對,含跨午夜 `hh + 8 >= 24`)。
- `to_milli_units` 的整數快路徑(`raw.isdigit()` → `int(raw) * 1000`)**不違反**
  `tc4common.py:21-23` 那條「不與 float 家族合併」的禁令:純整數字串下
  Decimal 與 int 路徑**恆等**,`.5` 之類才走 Decimal。要加測試釘住這個等價。

**Effort: M**(改動小,但要補跨語意的對拍測試,且動到四個區塊共用的檔案)。

---

### B07-05 [MEDIUM-HIGH / 熱路徑] corr `_handle_quote` 用全功能 parser,但只要兩個欄位

**位置** `copycat/server/corr_engine.py:265-287`

**證據**
```python
    def _handle_quote(self, quote: dict) -> None:
        leg = self._by_symbol.get(str(quote.get("Symbol", "")))
        if leg is None or leg.source != SOURCE_TC4:
            return
        tick, book, _meta = parse_stock_realtime(quote)     # ← 25.6 µs,_meta 直接丟掉
        if tick is not None:
            ...
            self._river.push(leg.key, minute, tick.price_milli, self._session_fn())
        if not book.bids and not book.asks:
            return
        self._books[leg.key] = (list(book.bids), list(book.asks))   # ← 再複製一次
```

實際用到的只有 `tick.price_milli`(江波圖)與 `book.bids[0][0]` / `book.asks[0][0]`
(`mid_from_book` 只看最佳檔)。被算了又丟的:
`StockMeta` 的 4 次 `to_milli` + `_to_int` + 2 次 `_hhmmss`、`_taipei_time` 的 strptime
(江波圖用的是 `FilledTime`,**不是** `tick.time` — 見 `corr_engine.py:279`)、
`derive_side`、`_best_limit_price`、`is_trial_window`、`TradeStatus` 檢查、
以及 `_parse_levels` 算出來的 L1–L4 八個檔位。

**修法**:給 corr 一支專用的窄 parser(`corr_models.parse_corr_quote`),只讀
`TradingPrice` / `TradeQuantity` / `Bid` / `Ask` / `FilledTime`。
預估 25.6 µs → **~3 µs**。

同時 `self._books[leg.key] = (list(book.bids), list(book.asks))` 是多餘的複製——
`StockBook` 是 frozen dataclass,那兩顆 list 是 `_parse_levels` 剛建的新物件,
沒有別的持有者。改成窄 parser 直接回 `(bid0, ask0)` 兩個 int 就完全不需要 list。

**風險**:`TradeStatus` 值域外的 WARNING 會在 corr 這條路消失。
那條 warning 的價值在個股(處置股),對海外期貨腿沒有意義——可接受,但要在 docstring 寫明。
另:`is_trial` 在期貨路徑本來就被忽略(`futures_models.py:12` 註明)。
**Effort: M。**

---

### B07-06 [MEDIUM-HIGH] 江波圖 1K 回補 11 腿**序列**執行,最壞 110 秒才補齊

**位置** `copycat/server/corr_engine.py:363-369`

**證據**
```python
            for leg in self._config.legs:
                if legs is not None and leg.key not in legs:
                    continue
                rows = await self._fetch_leg_minutes(leg.key, leg.symbol, leg.source)  # ← 逐腿 await
                if rows:
                    filled = self._river.apply_backfill(leg.key, rows, session)
```
每腿走 `collect_1k_minutes`(`copycat/live/river_backfill.py:34-94`):
```python
    sub_history(symbol, start, end, "1K")
    budget = max(poll_wait * _POLL_BUDGET_FACTOR, 1.0)      # = 1.0 × 10 = 10.0 s
    deadline = time.monotonic() + budget
    while True:
        first = get_history(symbol, start, end, "0", "1K")
        if first.get("HisData"): break
        ...
        time.sleep(min(wait, remaining))                    # ← 阻塞等待,逐腿各等各的
```

11 腿 × 10 s 預算 = **最壞 110 秒**。真實事故已經發生過:
`corr_engine.py:38-43` 的註解記載 2026-08-26 08:52 TSMC 腿開機首輪逾時、
三輪重試全落在 90 秒內就放棄,江波圖整天只從啟動後累積。

**這個 repo 裡已經有正確的解法先例**(memory `opening-backfill-parallel-shipped`:
40 檔 40.7 s → 0.87 s):`tc4.py:864-899` 的 `fetch_backfill` 用的是
**先對全鏈送 SubHistory 讓 TC4 平行備資料,再 round 制輪詢收割**:
```python
        for contract in series.contracts:
            self._sub_history(contract.symbol, start, end)   # ← 先全訂
        ...
        for rnd in range(1, _HARVEST_ROUNDS + 1):
            if rnd > 1 and self._poll_wait:
                time.sleep(self._poll_wait * 0.5)            # ← 全局輪間等待,不是逐檔空等
            for sym in pending: ...
```

**修法**:把 `collect_1k_minutes` 拆成 `sub_all(symbols)` + `harvest_round(symbols)`,
`_backfill_river` 改成「一次全訂 11 腿 → round 制收割」。
預期:最壞 110 s → **~10–15 s**(一個全局預算而不是 11 個)。

**硬約束**:`_req` 是 per-session `api.lock` 序列化(`tc4.py:565`),
所以**不能**靠 `asyncio.gather` 平行化 REQ 本身——REQ 還是會排隊。
真正省下來的是**等待**(`time.sleep` 那段),這正是 batch-sub 模式解決的東西。
另:台指腿走 `futures_minutes_fetch`(**不同 session**),那一腿可以真的與其餘 10 腿並行。

**風險**:`HistoryTimeoutError` 的逐腿分帳(`_backfill_pending_legs`)必須保留——
round 制收割裡「這一腿是真沒資料」與「這一腿還沒備妥」的區分是
`river_backfill.py:76-92` 那段 `not parsed.skipped` 判準的核心,不能在改寫時弄丟。
測試 `tests/server/test_corr_engine_river.py` 鎖著退避階梯字面值。
**Effort: L。**

---

### B07-07 [MEDIUM] 櫃買 MIS poll 每 5 秒重建 TLS 連線,多付 30–50 ms

**位置** `copycat/server/mis.py:41-63`

**證據**
```python
def fetch_otc_snapshot(fetcher: Callable[..., Any] = urlopen) -> OtcSnap | None:
    req = Request(_URL, headers={"User-Agent": "Mozilla/5.0"})
    with_resp = fetcher(req, timeout=_TIMEOUT)      # ← urlopen 不做連線池
```

**實測**(§1.4):urlopen 34–69 ms vs `http.client.HTTPSConnection` 持久連線 7 ms。

**影響**:不卡 event loop(在 `to_thread`),但
(a) 櫃買現價多 ~40 ms 陳舊度;
(b) 每個交易日 3,240 次 TLS 握手 ≈ 2.5 分鐘純 CPU;
(c) 這是唯一一條**外部網路**依賴,握手慢時整條 `_mis_loop` 的實際週期會從 5 s 漂到 5.07 s。

**修法(零新相依,符合 stdlib-only)**:模組內持有一顆 `http.client.HTTPSConnection`,
`ConnectionError` / `http.client.*` 例外時重建。約 20 行。
`fetcher` 注入點要保留(測試用),所以改成注入一個 `Callable[[], bytes]` 型的 fetcher。

**不建議**為了這條裝 `httpx`:它已經在 venv 裡(fastapi TestClient 的傳遞相依),
但它**不在 runtime dependencies**——為了一條 5 秒一次的 poll 把 httpx 推進 runtime
違反 pyproject 的 `dependencies = []`。stdlib 版本足夠。

**風險**:`_fail_streak` 的 module global 已經存在;加一顆 module-level connection
會把同一個問題擴大(兩個 IndexEngine 共用一條連線)。建議一併把兩者收進一個
`MisClient` 類別,由 `IndexEngine` 持有——這順便修掉既有的 global 汙染。
但**這是 scope 擴張**,可以分兩批。
**Effort: S(單純加 keep-alive)/ M(順便收成 class)。**

---

### B07-08 [MEDIUM] `_check_1k_health` 對每根 bar 做 `strptime`,冷路徑 29,000 根 ≈ 125 ms

**位置** `copycat/server/futures_engine.py:48-53, 428-433`

**證據**
```python
def _bar_minute(t: str) -> _dt.datetime | None:
    try:
        return _dt.datetime.strptime(t, "%Y-%m-%d %H:%M")     # ← 4.3 µs × 每根
    except ValueError:
        return None
...
        stamps: list[_dt.datetime] = []
        for bar in bars:
            at = _bar_minute(bar["t"])
            if at is None:
                return
            stamps.append(at)
```
`/api/market/bars/TXF?tf=1&days=30&session=allday` 在冷啟動時走 30 天歷史段
≈ 21 交易日 × (日盤 540 + 夜盤 840) ≈ **29,000 根** → ~125 ms。
穩態(兩段式 cache 只重抓當日段)≈ 1,380 根 → ~6 ms,每 60 秒一次。

跑在 executor thread(`_fetch_and_check`,`futures_engine.py:393-411`),不卡 loop,
但這 125 ms 佔著一條 worker、握著 GIL。

**修法**:`bar["t"]` 的格式是**我們自己產的**(`"YYYY-MM-DD HH:MM"`,固定寬度),
直接切片轉 int 即可:`(int(t[:4]), int(t[5:7]), int(t[8:10]), int(t[11:13]), int(t[14:16]))`,
或乾脆用 `total_minutes = ...` 的整數表示,完全不建 `datetime` 物件
(下游只做減法與 `.date()` 比較,都能用整數表達)。預估 4.3 µs → **0.3 µs**,**~14×**。

**風險 / 契約**:`_tradable_minutes_between` 與前端 `FuturesChart` gate 5 的
「根數」口徑必須維持同一把尺(CLAUDE.md §4 / pr-145 F-08:最後成交先換成所屬 bar
的終點標記再數)。改成整數分鐘表示時,`_last_trade_at` 的 `+1 分` 規則要原樣搬。
`tests/server/test_futures_engine*.py` 有覆蓋。
**Effort: S。**

---

### B07-09 [MEDIUM / 熱路徑 / 跨區塊] `to_milli_units` 走 Decimal,每則推播 16 次

**位置** `copycat/tc4common.py:16-29`

**證據**
```python
def to_milli_units(raw: str) -> int | None:
    if not raw:
        return None
    try:
        return int(Decimal(raw) * 1000)
    except InvalidOperation:
        return None
```
`parse_stock_realtime` 一則呼叫它 **~16 次**(五檔 ×2 = 10、meta 4、TradingPrice 1、…)。

**實測** 0.389 µs → 整數快路徑 0.137 µs;`.5` 之類的小數路徑 0.410 → 0.455 µs(略慢,但佔比低)。
`.isdigit()` 快路徑對純整數輸入(期貨點數、指數點數、大多數股價的整數部分)是恆等變換。

**修法**
```python
def to_milli_units(raw: str) -> int | None:
    if not raw:
        return None
    if raw.isdigit():          # 純整數:Decimal 與 int 路徑恆等,不動捨入語意
        return int(raw) * 1000
    try:
        return int(Decimal(raw) * 1000)
    except InvalidOperation:
        return None
```
省 ~4 µs/則。與 B07-04 合起來 25.6 → ~13 µs。

**風險 / 契約**:`tc4common.py:21-23` 的 🚨 註解明文禁止與 float 家族合併
(Decimal 截斷 vs float banker's rounding 在 tick 邊界分岔)。
**整數快路徑不碰捨入**,但要加一條 parity 測試:對一組真實 TC4 價格字串
(含 `"0"`、`"24580"`、`"1234.5"`、`"0.001"`、負號?)新舊兩版逐字比對。
`raw` 帶正負號時 `.isdigit()` 為 False → 自動走 Decimal,安全。
**Effort: S。**

---

### B07-10 [MEDIUM] `RiverState.delta()` 每秒重送全部 11 腿的 last_write,即使沒變

**位置** `copycat/live/river_state.py:177-193`

**證據**
```python
    def delta(self, seq: int) -> dict:
        return {
            "type": "river_delta", "seq": seq, ...
            "legs": {
                key: ({"m": write[0], "p": write[1]} if write is not None else None)
                for key, write in self._last_write.items()     # ← 從不清空
            },
        }
```
`_last_write[key]` 只在 `push` 時被覆寫、在 `set_session` 換場時被清成 None,
**delta 送出後不清**。對照 `IndexEngine._broadcast_loop:745-746` 的做法:
```python
            self._publish(self._payload())
            self._twse.last_minute = None      # ← index 是清的
            self._otc.last_minute = None
```

**影響(在前端)**:`frontend/src/hooks/useRiver.ts:51-63` 的 `applyDelta`
對每個非 null 的腿做 `{...leg.minutes, [String(point.m)]: point.p}`:
```
實測(Node,11 腿 × 840 分鐘滿窗夜盤):applyDelta = 0.264 ms / 秒
```
加上 `lastOf` 的 `Object.keys(m).map(Number)` + `Math.max(...o)`(840 個參數的 spread)。
每秒 11 次 840-entry 物件配置 → **~9,200 個 key 的複製 + GC 壓力/秒**,
而且 `setState` 每秒觸發江波圖整張 SVG 的 re-render。

**誠實的量級評估**:0.26 ms/秒在主執行緒上**不是災難**。真正的成本是它保證了
江波圖每秒一定 re-render(即使 11 腿一個都沒動)。這條的價值一半在效能、
一半在「訊息語意正確」(delta 應該只帶 delta)。

**修法(後端一行)**:`delta()` 後把 `_last_write` 清成 None,或引入
`_dirty_legs: set[str]`,`delta()` 只帶本拍有寫入的腿。
前端 `applyDelta` 已經對 `point == null` 走 `legs[key] = leg`(原物件複用,零複製)——
**所以後端改完前端零改動就享受到收益**。

**風險 / 契約**:`RiverDelta.legs[key]` 的 `null` 語意在前端註解是
「該腿本場尚無 live 點」(`river_state.py:178`)。改成「本拍沒更新」會讓
前端那句註解變成錯的,但**行為完全相同**(兩種 null 前端都走「沿用舊值」)。
必須同時改兩邊的 docstring/註解,並在 CLAUDE.md §4 補一條契約條目。
`tests/live/test_river_state.py` 有 delta 的斷言要更新。
**Effort: S(code)/ M(含契約文件與測試)。**

---

### B07-11 [MEDIUM] `CorrState` 的資料結構:39,600 個 tuple 常駐 + 每秒 10 顆 3,600-entry dict

**位置** `copycat/live/corr_state.py:54-56, 91`

**證據**
```python
        self._cap = int(2 * self._max_window / sample_secs) if sample_secs > 0 else 4096   # = 3600
        self._series: dict[str, deque[tuple[float, int | None]]] = {
            k: deque() for k in [base, *self._legs]
        }
...
        leg_by_ts = dict(leg_series)     # 每腿每秒重建一顆 3600-entry dict
```

11 腿 × 3600 = **39,600 個 `(float, int)` tuple 常駐**
(每個 tuple ≈ 56 bytes + 兩個 boxed 物件)≈ 5–8 MB,
加上每秒 10 顆 3,600-entry dict 的建立與丟棄(每顆 ~150 KB)≈ **1.5 MB/秒的配置churn**。

**修法**:B07-01 的增量矩實作會讓 `_paired_returns` 整個消失,
`leg_by_ts` 那顆 dict 也就不存在了。
序列本身可以換成 stdlib `array`:
```python
from array import array
self._ts  = array("d")   # float64 ring
self._mid = array("q")   # int64 ring,None 用哨兵值 -1 表示
```
`array` 存的是原生數值不是 boxed 物件,11 × 3600 × 16 bytes ≈ **630 KB**(省 ~90%)。
ring buffer(固定長度 + head/tail 索引)比 deque 的 append/popleft 更適合這個用法。

**注意**:這條的收益幾乎全部含在 B07-01 裡。**單獨做不值得**;
在做 B07-01 時順手把序列換成 `array` ring 即可。
**Effort: 含在 B07-01 的 M 裡。**

---

### B07-12 [MEDIUM / 觀測性] 四個引擎沒有任何 per-tick 耗時記帳,也沒有 event loop lag 探針

**位置** 全區塊。`/api/health` 刻意不含引擎健康度(`ws.py:60` 的註解明說)。

**證據**:grep 全庫沒有 `loop.slow_callback_duration`、沒有 `time.perf_counter()` 圍住任何 tick、
沒有任何 latency histogram。目前唯一的效能訊號是:
- `WsBroadcaster.dropped` / `window_dropped`(丟包,60 s 節流 WARNING)
- `futures_engine._check_1k_health` 的落後 / 缺格 WARNING
- `index_engine` 的「分時自癒」/ 「txo spot 無 TXF 推播」

這三者都是**資料面**的健康度,不是**時間面**的。
「event loop 被佔住 19 ms」這件事目前**完全不可觀測**——
連 B07-01 這個 CRITICAL finding 都是我靠讀 code + 離線 benchmark 才找到的,
跑了幾個月的 prod 沒有留下任何一行 log 可以指向它。

**對「要下實單、不能塞住」的目標,這是最該先補的一件事。**

**修法(三層,都很便宜)**:
1. **最便宜**:`uvicorn`/`asyncio` 的 debug 模式 + `loop.slow_callback_duration = 0.05`
   → 任何超過 50 ms 的 callback 自動 WARNING。零 code、零相依。
   現在就可以跑一次來驗證 corr 那 19 ms(它剛好在門檻下,設 0.015 就抓得到)。
2. **常駐探針**(~30 行):一條 `call_later(0.1)` 的自排程 task,
   量 `實際喚醒時刻 − 預期時刻` 的 drift,維護 p50/p95/max 環形統計,
   掛進 `/api/health` 或每分鐘印一行。這是「有沒有塞住」的唯一直接證據。
3. **per-tick 記帳**:`tick_once` / `_broadcast_loop` / `_flush` 各包一個
   `perf_counter`,超過閾值印一行(節流)。

**Effort: S(1 與 2)。**

---

### B07-13 [LOW-MEDIUM] `_tradable_minutes_between` 逐分走迴圈,上限 2,880 步

**位置** `copycat/server/futures_engine.py:72-90`

**證據**
```python
    n = 0
    cur = a
    step = _dt.timedelta(minutes=1)
    for _ in range(total):
        cur += step
        hhmm = f"{cur:%H%M}"                                  # ← 每步一次 strftime
        if any(start <= hhmm <= end for start, end, _clamp in domain):
            n += 1
```
每步一次 `timedelta` 加法 + 一次 `strftime` 格式化 + 一次 generator 掃 domain。
`_MINUTE_WALK_CAP = 2880`。

**影響**:只在偵測到缺格時走(`cur_at - prev_at > 1 分` 的快路徑已擋掉健康資料),
且只在 executor thread。一個 2,880 步的呼叫約 **3–5 ms**。
盤中資料健康時幾乎不進;TC4 落後 / 缺格的**壞日子**才會多發。

**修法**:把 domain 預先展開成一個 1,440-bit 的 bitmask(或 `bytes(1440)` 查表),
然後用整數分鐘數做算術而不是逐分走。O(1) 而不是 O(n)。
但這只在「壞日子」有收益,而壞日子本來就不是效能瓶頸。

**判定:不急,但如果 B07-08 要把 `_bar_minute` 改成整數表示,這條順手一起改**
(兩者共用同一個「分鐘表示法」的決定)。
**Effort: S(與 B07-08 合併做)。**

---

### B07-14 [LOW] 所有 REALTIME 解析都在 event loop 執行緒上——但 GIL 下搬走不會變快

**位置** `corr_engine.py:259-262`、`futures_engine.py:562-565`、`index_engine.py:417-420`
三處同形:
```python
    def _on_quote_threadsafe(self, quote: dict) -> None:
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._handle_quote, quote)
```
listener thread 只做 `json.loads`(5.9 µs),把 25.6 µs 的 parse 全推到 event loop。

**誠實評估**:直覺會說「把 parse 搬到 listener thread」,但
**Python 3.13.13 是標準(有 GIL)build**——搬過去不會減少總 CPU,
只會把等待從「event loop 上的同步佔用」變成「listener thread 持 GIL 而 loop 等 GIL」。
淨效果接近零,而且會引入跨執行緒的狀態寫入問題
(`_books` / `_states` 目前是「只有 loop thread 寫」的不變式,
`river_state.py:22-24` 明文寫了這條)。

**真正的修法是 B07-04 + B07-05 + B07-09:讓 parse 本身變便宜。**
只有在跳到 free-threaded Python(3.13t / 3.14t)之後,分執行緒才有意義——
但那要先驗 pyzmq / comtypes / pywin32 的相容性(見 open question)。

**判定:不要動。** 記在這裡是為了擋掉「把解析丟去 thread」這個看起來很對的錯誤直覺。

---

### B07-15 [LOW] corr `_futures_leg_book` 每拍呼叫 `futures.state()` 兩次,建整份三商品 payload

**位置** `copycat/server/corr_engine.py:291-298`(被 `tick_once` 與 `_river_tick` 各呼一次)

**證據**
```python
    def _futures_leg_book(self, key: str) -> tuple[list, list, Any]:
        products = (self._txf_state_getter() or {}).get("products", {})   # ← futures.state()
        payload = products.get(key) or {}
        return (list(payload.get("bids") or []), list(payload.get("asks") or []), payload.get("p"))
```
`futures.state()`(`futures_engine.py:334-344`)建三顆 `payload()` dict,
每顆含 `list(self.bids)` / `list(self.asks)`。一拍兩次 = 6 顆 dict + 12 次 list 複製。

**量級**:~20 µs/秒。**與 19 ms 相比是 0.1%,不值得動。**
若真要改,正確做法是給 `FuturesEngine` 加一支 `book_of(product)` 的窄讀取面
(回 `(bids, asks, p)` 不建 payload),但那是新增公開 API 換 20 µs——不划算。

**判定:不要動。**

---

### B07-16 [ARCHITECTURAL] corr engine 同時承載相關係數與江波圖兩個狀態機,綁在同一個 1 s tick

**位置** `copycat/server/corr_engine.py:85-145`(建構子同時建 `CorrState` 與 `RiverState`)

兩者共用同一份報價流是**正確的**(零新增訂閱,`corr_engine.py:125` 的註解說明了理由),
但它們的**自然節奏不同**:
- 相關係數:1 秒取樣是設計核心(Epps 效應,`corr_models.py:3-5`),必須 1 s。
- 江波圖:資料粒度是**分鐘**。每秒 push 同一分鐘的 last-write-wins,
  59/60 的寫入都會被下一秒覆寫掉。

若要進一步降低每秒工作量,江波圖那半可以改成「每秒只記住最新價,每分鐘界才寫桶 + 發 delta」。
但 delta 的**語意**是「這一秒的現價」,前端用它畫即時的線頭——改成每分鐘會讓江波圖線頭一分鐘跳一次。
**這是產品決策不是效能決策。**

**判定:現階段不動**,但如果未來要把 corr 的 tick 拆成獨立 task(例如把相關係數
降到 1 s 而江波圖線頭升到 0.5 s),架構上是乾淨的——兩個狀態機本來就零耦合。

---

### B07-17 [ARCHITECTURAL] 15 條 daemon thread + 1 條 event loop 在單一 GIL 下競爭,是「不塞住」的結構上限

全 app 5 條 TC4 session,每條 = ZMQ listener + healer + wrapper KeepAlive。
加上 asyncio 預設 ThreadPoolExecutor 的 worker(`min(32, cpu+4)`),
以及 capital 的 COM 專屬執行緒。

盤中所有這些執行緒都在做 Python 層的工作(json 解析、指紋比對、時戳格式化),
**全部序列化在同一把 GIL 上**。單核的有效吞吐就是上限。

**現階段的量級**:B07 的三個引擎加起來每秒的 Python 工作量約
19 ms(corr,可降到 0.13)+ 1 ms(parse)+ 0.5 ms(其餘)。
修完 B07-01 之後是 **< 2 ms/秒**,離 GIL 飽和還很遠。
真正吃 GIL 的是 **stock session 的 150 檔**(B-other 區塊)。

**判定:B07 內不需要動**,但它是全系統的架構上限,
要記在總報告裡:任何「加更多 symbol / 加更多引擎」的擴張最終會撞到這裡,
解法只有 (a) free-threaded Python、(b) 把解析搬到 C 擴充(orjson/msgspec)、
(c) 多 process。

---

## 4. 工具選型與取捨

| 工具 | 用在哪 | 解決什麼 | 代價 | 判定 |
|---|---|---|---|---|
| **無(純 stdlib 增量矩)** | `corr_state.py` 全檔 | 18.8 ms → 0.13 ms/秒 | 需要 characterization 測試 + 每 60 s fsum 重播 | ✅ **強烈建議**。這是 B07 唯一的大勝,而且**不需要任何新套件** |
| `array` / ring buffer | `corr_state._series` | 39,600 tuple → 630 KB array | stdlib,零相依 | ✅ 建議(併入上一項) |
| `http.client` 持久連線 | `mis.py` | 50 ms → 7 ms/poll | stdlib,需重建邏輯 ~20 行 | ✅ 建議 |
| **numpy** | corr Pearson / river | — | 20 MB wheel、破 `dependencies = []`、import 成本、Windows wheel 要對 3.13 | ❌ **不建議**。增量矩已經到 0.02 ms,numpy 的 array 邊界處理反而更貴。numpy 該用的地方是 `backtest/` 與 `screening.py`(離線、大批量),**不是這四個引擎** |
| **polars / pandas / duckdb** | — | — | 同上,且這裡根本沒有表格運算 | ❌ **不建議**(B07 內) |
| **numba** | — | — | 需要 numpy、JIT warmup、Windows 編譯鏈 | ❌ 不建議 |
| **orjson / msgspec** | `tc4._realtime_msg` 的 `json.loads`、`_req` 的 dumps/loads | 5.9 µs → ~1.5 µs/則 | 新 runtime 相依(進 `live` extra);msgspec 還能做 struct 反序列化取代 dataclass | ⚠️ **有條件**。對 B07 的量級(~15 則/秒)只省 0.07 ms/秒 —— **不值得為 B07 導入**。但對 stock session(150 檔、開盤數百則/秒)是數 ms/秒,由那個區塊決定;若那邊導入了,B07 白白受益 |
| **uvloop** | event loop | 2–4× loop 吞吐 | ❌ **Windows 無 wheel**(硬約束:CLAUDE.md 明載後端 host 必須 Windows + TC4 常駐) | ❌ 不可用 |
| **winloop** | event loop | uvloop 的 Windows port | 相對小眾、與 uvicorn 的整合要驗、ZMQ + `call_soon_threadsafe` 行為要驗 | ⚠️ 值得做一次 spike,但**排在 B07-01 之後**——現在 loop 的瓶頸是那 19 ms 不是 loop 本身 |
| **py-spy**(已安裝 0.4.2) | 量測 | 對跑著的 prod server 取樣,零侵入 | 已在 venv 裡 | ✅ **立刻可用**,見 §6 |
| `loop.slow_callback_duration` | 量測 | 抓 >N ms 的 callback | stdlib,一行設定 | ✅ **立刻可用** |
| **free-threaded Python 3.13t/3.14t** | 全系統 | 解除 GIL 上限 | pyzmq / comtypes / pywin32 / discord.py 相容性全未驗;群益 SKCOM 是 COM,幾乎確定要留在單執行緒 | ⚠️ **長期選項**,現階段 B07 用不到(修完 B07-01 離飽和很遠) |
| **redis / 任何外部 DB** | — | — | CLAUDE.md §5 明文「沒有 DB」,state = React client + filesystem JSON | ❌ 不建議 |

---

## 5. 不要動的地方(反向結論)

1. **`IndexEngine._broadcast_loop` / `_payload` / `_Series.scalar`** —— 每拍 < 100 µs,
   `_dirty` 閘已經正確,`minutes` 全量只在回補成功後帶一次。這是一個**寫得對**的 1 Hz loop。
2. **`FuturesEngine._flush` 的 0.1 s per-product coalesce** —— 這已經是正確的
   coalescing 設計(payload 是全量快照,合併無資訊損失;失敗那則回標 dirty 重送)。
   不要改成 per-tick 直推(五檔會洗爆 WS),也不要拉長週期(閃電梯五檔會慢)。
3. **`RiverState` 的 `dict[int, int]` 分鐘桶** —— 日盤 300 / 夜盤 840 格 × 11 腿,
   每拍 O(1) 寫入。對它用 numpy array 是純粹的過度工程(稀疏、整數鍵、需要「只填空缺」語意)。
4. **`WsBroadcaster` 的有界 queue「丟最舊保最新」政策 + 60 s 節流結算** —— 設計正確,
   而且 `dropped` / `window_dropped` 是目前唯一可用的背壓訊號。
5. **每條 TC4 session 各自 SubPort + 獨立 ZMQ SUB socket** —— 不是「5 份重複解析」,
   每條只收自己訂閱的那批。改成共用一條 session 會踩 refcount key 的引信。
6. **`_note_push` 的 4 欄指紋** —— 4 次 dict get + tuple 建構,微秒級,而它擋掉的是
   「冷門檔每 60 s 都是 attempt 1」那個真實故障(6949 一天 92 發)。
7. **`corr_state.py` 檔頭「整批重算讓增量=整批恆真」的 rationale** —— 結論(整批)要改,
   但**理由要留**。新設計用「增量 + 每 60 s fsum 精確重播」保留它的精神,
   而且把「恆真」從論證升級成每分鐘機械驗證一次。
8. **`corr_engine._futures_leg_book`** —— 20 µs/秒,佔比 0.1%。不值得為它開新 API。
9. **watchdog / heal 窗的所有時間常數**(`_WATCH_END` 13:25、`_HEAL_TAIL_END` 13:40、
   `_HEAL_BACKOFF_CAP` 900 s、corr 的 `_BACKFILL_RETRY_*` 階梯)—— 這些是**正確性**機制,
   每一個都對應一次真實事故,且多條有跨檔契約鎖住。效能改造**一律不得碰**。
10. **把 REALTIME 解析搬到 listener thread** —— GIL 下淨收益接近零,
    還會破壞「只有 loop thread 寫狀態」的不變式。見 B07-14。

---

## 6. 量測方法

### 6.1 立刻可做(零 code、對跑著的 prod)

**py-spy 已經在 venv 裡**(0.4.2)。盤中對跑著的 server 取樣:
```powershell
# 找 PID
Get-Process python | Where-Object { $_.CommandLine -like "*copycat.server*" }

# 即時 top(看哪個函式吃 CPU)
.venv\Scripts\py-spy top --pid <PID>

# 錄 60 秒火焰圖(--idle 要帶,不然只看到 loop 在 select)
.venv\Scripts\py-spy record --pid <PID> --duration 60 --idle -o corr-flame.svg

# 只看 event loop 那條執行緒
.venv\Scripts\py-spy dump --pid <PID>
```
**預期判準**:修改前,`correlations` / `_paired_returns` 應該在火焰圖上佔
MainThread 的可見比例(約 1.5–2%,而且集中在每秒一個尖峰);修改後應該消失。

### 6.2 event loop lag 探針(建議常駐,~30 行)

```python
# 概念碼,放 copycat/server/loop_probe.py
async def _probe(interval: float = 0.1) -> None:
    expected = time.monotonic() + interval
    worst = 0.0
    while True:
        await asyncio.sleep(interval)
        now = time.monotonic()
        lag = now - expected
        expected = now + interval
        worst = max(worst, lag)
        # 每 60 s 印一行 p_max,超過門檻即 WARNING
```
掛進 lifespan,結果印 log(或掛 `/api/health`——但 `ws.py:60` 記載
`/api/health` 刻意不含引擎健康度,要先跟 user 確認這條政策是否要放寬)。

**預期判準**:修改前 corr tick 那一拍的 lag 應該出現 ~15–20 ms 的規律尖峰;
修改後 p_max 應該落到 < 5 ms。**這是 B07-01 的真環境驗收判準。**

### 6.3 一行設定的粗篩

在 `copycat/server/__main__.py` 或 lifespan 開頭:
```python
loop = asyncio.get_running_loop()
loop.slow_callback_duration = 0.015   # 15 ms,剛好卡在 corr 那一拍下面
```
搭配 `logging.getLogger("asyncio").setLevel(logging.WARNING)`。
**預期判準**:盤中 log 應該每秒出現一行
`Executing <Handle CorrelationEngine.tick_once> took 0.019 seconds`。
這是 B07-01 **最便宜的真環境證據**,不改任何業務 code。

### 6.4 離線基準(重跑我的量測)

```powershell
.venv\Scripts\python <scratchpad>\bench_corr.py      # corr 現況 14/18.8 ms
.venv\Scripts\python <scratchpad>\bench_incr.py      # 增量原型對照 + 精度差
.venv\Scripts\python <scratchpad>\bench_parse.py     # parse_stock_realtime 25.6 µs 拆解
.venv\Scripts\python <scratchpad>\bench_fastparse.py # _taipei_time / to_milli 快路徑
.venv\Scripts\python <scratchpad>\bench_mis.py       # MIS urlopen vs keep-alive(會打真端點)
.venv\Scripts\python <scratchpad>\bench_json.py      # listener 側 json.loads 5.9 µs
```
建議把 `bench_corr.py` / `bench_incr.py` 的精簡版收進 repo 當
**效能 regression 測試**(`tests/perf/` 或 pytest mark),門檻設寬(例如
`correlations() < 1 ms`),只擋「改回整批重算」這種退步。

### 6.5 真環境 tick 率量測(現在查不到,見 open questions)

需要一支臨時探針統計各 session 的每秒推播數:
在 `tc4._realtime_msg` 的 `_note_push` 旁加一個 per-session counter,每 60 s 印一行
`session=corr msgs=1234 symbols=10`。跑一個完整交易日(含美盤時段),
才能把「corr 10 腿的解析成本」從推測變成事實。

---

## 7. 建議的執行順序

| # | Finding | Effort | 預期收益 | 先決條件 |
|---|---|---|---|---|
| 1 | B07-12(量測:slow_callback + py-spy) | S | 0(但讓後面每一步可驗) | 無 |
| 2 | **B07-01**(corr 增量矩 + fsum 重播) | M | **18.8 → 0.13 ms/秒** | 先寫 characterization test |
| 3 | B07-02 + B07-03(懶算 + 快取 pairs) | S | 消掉剩餘的按需 stall | 依附 2 |
| 4 | B07-04 + B07-09(`_taipei_time` + `to_milli` 快路徑) | M | 每則推播 25.6 → 13 µs(**跨全區塊**) | 要 property-based 對拍測試 |
| 5 | B07-10(river delta 只帶變動腿) | S/M | 前端每秒省 11 次物件複製 + re-render | 要補 CLAUDE.md §4 契約 |
| 6 | B07-05(corr 窄 parser) | M | corr 路徑 25.6 → 3 µs | 依附 4 |
| 7 | B07-08 + B07-13(bar 時戳整數化) | S | 冷路徑 125 → 10 ms | 注意 gate 5 同尺契約 |
| 8 | B07-07(MIS keep-alive) | S | 50 → 7 ms/poll | 無 |
| 9 | B07-06(river 回補 batch-sub) | L | 最壞 110 → 15 s | 最複雜,放最後 |

---

## 8. 這個區塊觀察到的硬約束

1. **TC4 refcount 是 `symbol|DataType|Start|End`,上游 feed 卻以 symbol 為單位。**
   任何「省一次 dict 查表」而讓第二條 session 訂同一個 symbol 的優化一律禁止。
   → base 腿必須讀 `futures_engine.state()`;台指 1K 必須由 futures session 問。
   corr 的 TWS 現貨腿(TSMC 2330)訂閱窗還必須與個股引擎**逐字相同**
   (`corr_source.py:119-128`),否則兩把 key 互相歸零。
2. **`_req` 是 per-session `api.lock` 序列化**(`tc4.py:565`)。
   同一條 session 上的回補無法靠 `asyncio.gather` 真平行化 REQ,
   只能靠 batch-SubHistory 把**等待**重疊(B07-06)。
3. **stdlib-only runtime**:`pyproject.toml` 的 `dependencies = []`。
   新套件只能進 extras,而 `live` extra 已經有 pyzmq。
   B07 的所有建議修法**都不需要新套件**(這是好消息)。
4. **Windows 11 本機**:uvloop 不可用。TC4 是桌面 app,Linux Docker 不在規劃內。
5. **跨檔契約(CLAUDE.md §4),B07 內相關的:**
   - 江波圖調色盤色數 ≥ 相關係數腿數(`configs/correlation.json` / `corr_config.DEFAULT_CONFIG`
     ↔ `frontend/src/components/corr/river-colors.ts` + `index.css` token;
     `tests/test_corr_config.py::test_river_palette_covers_every_leg` 鎖住)。
   - `sparse` 旗標只認字面 `true`,且 `DEFAULT_CONFIG` 必須與 repo 真檔逐腿相同
     (`test_sparse_legs_are_sxf_and_vx_and_the_repo_file_agrees`)。
   - `/api/market/bars` 的 `meta.status` 三態鏈:
     `futures_source.fetch_bars_range`(raise `HistoryTimeoutError`)→
     `futures_engine.bars_range`(**裸 tuple** `(bars, status)`,不得回 `BarsResult`)→
     `bars.build_minute`(兩段取最壞)→ `app._market_payload` → 前端 `BarsMeta.status`。
     **且只在期指 `tf=1` 出現**,其餘路徑連鍵都不給。
   - `index_engine._WATCH_END`(13:25)必須與 `stock_source._INDEX_HEAL_END` **同值同語意**
     (`tests/server/test_index_engine.py::test_watch_end_is_the_index_heal_gate_boundary`)。
   - `_check_1k_health` 的「可交易分鐘」口徑必須與前端 `FuturesChart` gate 5 的「根數」同尺
     (最後成交先換成所屬 bar 的終點標記再數;pr-145 F-08)。
   - WS 心跳 `WS_HEARTBEAT_SECS` = 10 s **必須小於**前端 `WS_SILENCE_TIMEOUT_MS` = 30 s。
   - 關機預算三方同源:`shutdown_budget.TC4_LANE_DEPTH = 2` 對應 lifespan 的
     `corr → futures` 串鏈形狀。**改 lane 形狀 = 改契約**,要同步改該常數與 `run.ps1`。
6. **`tick.time` / `trade_date` 的字面格式是多處讀者的契約**
   (`"HH:MM:SS.fff"` / `"YYYY-MM-DD"`):`futures_engine._last_trade_at` 切
   `t[:5]` 與 `t[5:].strip(":.0")`、`is_trial_window` 的字串區間比較、成交明細顯示。
   B07-04 的改法必須輸出**逐字相同**。
7. **`tc4common.to_milli_units` 明文禁止與 float 家族合併**(Decimal 截斷 vs
   float banker's rounding 在 tick 邊界分岔)。整數快路徑不碰捨入,但要加 parity 測試。
8. **`RiverState` 的執行緒不變式**(`river_state.py:22-24`):所有方法只由 event loop thread 呼叫。
   任何把回補 apply 搬進 worker thread 的改動都要先加鎖。
9. **`CorrState` 的「不跨洞接合報酬」與「時間戳逐出而非固定長度」** 是刻意的統計決策
   (Epps 效應 / event loop 漏拍),增量化時必須完整保留這兩條語意。

---

## 9. Open questions(查不出來,需要 user 或 profile 才知道)

1. **corr 10 條 tc4 腿的真實推播率是多少?** 檔頭只給了「台指 516 則/分、費半 146 則/分」,
   美盤時段 ES/NQ/YM/CL/GC 同時活躍時的合計數沒有任何記錄。
   這直接決定 B07-04 / B07-05 在 corr 路徑上的實際收益量級。
   → 需要 §6.5 的 per-session counter 跑一個完整交易日。
2. **相關係數面板實際被打開的時間佔比?** 如果一天只看幾分鐘,
   B07-02(懶算)單獨就能省掉 99% 的成本,優先序應該排在 B07-01 前面。
   → 需要 user 回答使用習慣,或在 `/ws/corr` 的 accept/close 加一行 log 統計連線時長。
3. **1800 秒窗還需要嗎?** `_cap` 是 3600、`_max_window` 是 1800,
   所有成本(記憶體、`_paired_returns` 的掃描長度)都由這個最大窗決定。
   如果量化交易實務上只看 60 / 300 秒窗,砍掉 1800 會讓現行實作的成本直接降到 1/6
   (~3 ms)——這比任何技術優化都直接。**需要 user 拍板。**
4. **`_paired_returns` 的實際 deque 長度分布?** 我用滿窗(1800/3600)量測,
   但如果實務上某些腿常常因為 stale(30 s)而 mid = None,有效樣本數會遠低於 1800,
   實際成本會低於 18.8 ms。→ 需要在 prod 加一行「本拍各窗的 n」統計。
5. **MIS 端點容許 keep-alive 嗎?** `userDelay=5000` 是**節奏**限制不是**連線**限制,
   但這是非契約公開端點(CLAUDE.md §0:「可能無預警壞」)。
   持久連線被伺服器單方面關閉時要能無縫重建——需要跑一天觀察 `_fail_streak`。
6. **free-threaded Python(3.13t / 3.14t)與 pyzmq 27.1 / comtypes 1.4.16 / pywin32 312 的相容性?**
   全未驗。群益 SKCOM 是 COM apartment-threaded,幾乎確定得留在單一專屬執行緒。
7. **`/api/health` 是否可以放寬成含引擎健康度 / loop lag?**
   `ws.py:60` 明文寫「`/api/health` 刻意不含引擎健康度」。
   B07-12 的探針要掛哪裡需要 user 拍板(log 一行 vs 新 endpoint vs 放寬 health)。
8. **江波圖 delta 的「線頭即時性」是否真的需要每秒?**(B07-16)
   改成每分鐘寫桶會讓線頭一分鐘跳一次。這是產品決策。

---

## 附錄 A — 完整實測數據表

```
=== corr(11 腿,base=TXF,windows=60/300/1800,min_samples=30/100/300)===
correlations() full  (1800 samples) : 14.122 ms
correlations() full  (3600 samples) : 18.791 ms
  _paired_returns × 10              :  9.212 ms
  statistics.correlation(1800)      :  0.211 ms   (× 30 次/拍)
push()                              :  0.0039 ms
paired 長度(1800 樣本)             :  1799

=== 增量矩原型(純 stdlib)===
NEW correlations()                  :  0.0198 ms   (≈ 950× vs 18.79)
NEW push()                          :  0.0419 ms   (+36 µs)
淨每秒                              :  0.062 ms    (≈ 300× vs 18.80)
max |r_old − r_new| after 3600 ticks:  1.1e-3
exact fsum re-seed(10 腿 × 1800 窗) :  3.834 ms    (每 60 s 一次 → 攤提 0.064 ms/s)

=== REALTIME 解析 ===
parse_stock_realtime                : 25.59 µs
  _taipei_time                      :  9.97 µs  →  手刻整數版 1.45 µs
    其中 datetime.strptime          :  4.31 µs
  to_milli_units(Decimal, "24580")  :  0.389 µs →  isdigit 快路徑 0.137 µs
  to_milli_units(Decimal, "24580.5"):  0.410 µs →  0.455 µs(略慢,佔比低)
  resolve_contract_ym + product_from_symbol : 1.23 µs
listener 側 find(":") + json.loads  :  5.90 µs   (842 bytes payload)

=== MIS(https://mis.twse.com.tw,674 bytes 回應)===
urlopen        #0 69 ms  #1 34 ms  #2 59 ms
http.client 持久 #0 36 ms  #1  7 ms  #2  7 ms

=== 前端 river(Node)===
useRiver.applyDelta(11 腿 × 840 分鐘滿窗) : 0.264 ms / 秒
```

## 附錄 B — 各檔案 LOC 與角色

| 檔案 | LOC | 角色 | 熱路徑? |
|---|---|---|---|
| `copycat/server/index_engine.py` | 822 | 加權 push + 櫃買 poll + txf 轉供 + watchdog + 兩段式換日 | 1 Hz,< 100 µs |
| `copycat/server/futures_engine.py` | 694 | TXF/MXF/TMF 五檔 + resolved_contract + leaf fallback + 1K 健康 | per-tick 25.6 µs / flush 0.1 s |
| `copycat/server/corr_engine.py` | 544 | 三窗 Pearson + 江波圖(同一報價流) | **1 Hz,19 ms** ★ |
| `copycat/server/mis.py` | 81 | TPEx 非契約端點 urllib 快照 | 0.2 Hz,50 ms(worker thread) |
| `copycat/live/corr_state.py` | 137 | 滾動相關係數狀態機(零 IO) | **★ 瓶頸所在** |
| `copycat/live/corr_models.py` | 36 | 中價 + 對數報酬純函式 | 每腿每拍,< 1 µs |
| `copycat/live/river_state.py` | 194 | 江波圖分鐘桶(零 IO) | 1 Hz,O(1) |
| `copycat/live/river_models.py` | 242 | 分鐘鍵 / 窗 / clamp / 1K 解析純函式 | O(1) |
| `copycat/live/river_backfill.py` | 95 | 1K 收割器(corr / futures 共用) | 啟動 + reconnect |
| `copycat/live/futures_models.py` | 70 | Symbol → 產品碼、HOT → YYYYMM | per-tick,1.2 µs |
| `copycat/corr_config.py` | 169 | 腿設定載入 + 降級 | 啟動一次 |
| `copycat/live/corr_source.py` | 169 | 泛化 symbol 訂閱 + 全天窗覆寫 + 逐腿自癒閘 | listener thread |
| `copycat/live/futures_source.py` | 228 | 期貨訂閱 + 分鐘域 + K 線 | listener thread |
| `copycat/server/ws.py` | 312 | 六路 WS fanout + 心跳 + relay | 每則廣播 |
