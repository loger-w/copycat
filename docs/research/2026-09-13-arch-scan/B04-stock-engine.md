# B04 — 個股引擎(訂閱池 / rollover / 回補 worker)架構與效能掃描

> 掃描日期 2026-09-13。範圍:`copycat/server/stock_engine.py`(1832 LOC)、
> `copycat/server/watchlist_service.py`、`copycat/stock_watchlist.py`、
> `copycat/server/stkfut_catalog.py`、`copycat/stkfut_map.py`、`copycat/stock_names.py`,
> 以及熱路徑必經的 `copycat/live/stock_models.py` / `copycat/live/stock_state.py` /
> `copycat/server/ws.py`。
> **所有量測都是本機 Python 3.13.13(專案 `.venv`)實跑**,腳本留在同目錄
> `bench_b04.py` / `bench_b04b.py` / `bench_b04c.py` / `bench_b04d.py` / `bench_b04e.py`,
> 可重跑複驗。沒有量測支撐的敘述一律標「推測」。

---

## 0. 一句話結論

**這個區塊的效能問題不在「每 tick 太慢」,而在三件事:
(a) 每則推播重做一堆不會變的解析(parse 層 28.8 µs 裡有 ~15 µs 是純浪費);
(b) 每 60 s 的群組全量重送把 event loop 一口氣鎖住 20–103 ms 並送出 1–4.5 MB;
(c) 每檔 tick deque 是 Python 物件陣列,150 檔最壞 0.91 GB。**
訂閱池 / rollover / backfill worker 的併發設計本身(ZMQ 全走 `to_thread`、單工 worker、
逐項取鎖)**是正確的,不要為了效能去動它們** —— 那些是拿 bug 換來的不變式。

---

## 1. 架構地圖與資料流

### 1.1 元件與分層

```
TC4 桌面 app
   │ ZMQ SUB (tcp://127.0.0.1:<SubPort>)
   ▼
TC4QuoteSource._listen_loop            [listener thread,tc4.py:1226]
   recv() → decode → handle_raw()
   ├─ _realtime_msg(): json.loads + DataType 過濾 + _note_push(指紋/自癒記帳)
   └─ StockQuoteSource.handle_raw(): _seen.add(symbol) 持 _seen_lock
        → self._on_message(quote)  = StockEngine._on_raw_threadsafe
   │
   │ loop.call_soon_threadsafe(self._handle_quote, quote)      ← 執行緒邊界
   ▼
=========================== event loop(單執行緒) ===========================
StockEngine._handle_quote(quote)       [stock_engine.py:1187-1366]
   1. Symbol → ".HOT" 後綴 → _handle_stkfut()(期現對照腿,直接 publish)
   2. _symbol_to_key[symbol] → instrument key(dict lookup,O(1))
   3. parse_stock_realtime(quote, trial_windows_for(code))     ← 28.8 µs
   4. 期貨鍵 + 非日盤窗 → 整則早退(D14b)
   5. _observe_trade_status()  ← 每則一次 strftime
   6. state.update_book / update_meta                          ← 無條件覆寫
   7. 漲跌停值變 → _enqueue_backfill
   8. 兩段式 rollover 快路徑(stage1)/ stage2 觸發
   9. 首筆當日成交 → _tick_armed → _enqueue_backfill
  10. state.ingest(tick)          ← 4.1 µs(去重 + _apply + _fold_vp)
       ├─ 收件人(main ∪ _tick_targets)→ _pending_ticks.append(9 欄 dict)
       │    首筆到貨排 loop.call_later(0.1s, _flush_ticks)
       ├─ code ∈ _watchlist → _dirty_watchlist.add(code)
       └─ signal_hub.on_tick(code, tick, state)                [B05 區塊]
  11. meta 轉態 / no_data 復原 → _publish(_quote_payload)
  12. code == _main → _publish({"type":"book",...})            ← 零 coalesce
  13. signal_hub.on_book(code, state)                          [B05 區塊]

背景 task(全部在同一條 loop 上)
  _flush_ticks          call_later 0.1 s → 一則 {"type":"ticks","items":[…]}
  _flush_watchlist_loop sleep 1 s → 試撮窗翻轉補推 + dirty 逐檔 watchlist_quote
  _retry_subscribe_loop sleep 10 s → 三段對帳重訂(每項各自 to_thread + 逐項取鎖)
  _checkpoint_loop      sleep 60 s → 08:00 後跨日即 rollover_stage1
  _backfill_worker      queue.get → 整批取件 → to_thread(prepare_backfill)
                        → 逐檔 to_thread(source.backfill) → state.apply_backfill

HTTP(同一條 loop)
  GET /api/stock/state/{code}     → set_main_contract() + snapshot(tape)
  GET /api/stock/group-state      → group_snapshot(codes ≤150)
  PUT /api/stock/watchlist        → WatchlistService.apply → _commit(鎖內落檔)
                                    → _settle(鎖外) → engine.set_watchlist(seq=)
WS  /ws/stock                     → WsBroadcaster.stream(seed=自選全量 quote)
                                    relay() + 入站 {"type":"view","codes":[…]}
```

### 1.2 狀態所在

| 結構 | 型別 | 界 | 說明 |
|---|---|---|---|
| `_refs` | `dict[str, set[str]]` | 訂閱期 | refcount 訂閱池,owner ∈ watchlist/main/stkfut:\<code\> |
| `_states` | `dict[str, StockDayState]` | **只增不減** | per-code 當日狀態機 |
| `_symbol_to_key` | `dict[str, str]` | 只增不減 | TC4 symbol → instrument key,**分派用** |
| `_no_data` | `set[str]` | 訂閱期 | TC4 回「查無此檔」 |
| `_watchlist` | `list[str]` | 整份重新指派 | 自選名單(一致快照) |
| `_main` | `str \| None` | — | 主圖槽位 |
| `_views` | `dict[object, frozenset[str]]` | 連線 | 每條 WS 登記的檢視集合 |
| `_tick_targets` | `frozenset[str]` | 派生 | `_views` 聯集快取 |
| `_pending_ticks` | `list[dict]` | 0.1 s 窗 | 逐筆打包緩衝 |
| `_dirty_watchlist` | `set[str]` | 1 s 窗 | 側欄節流 |
| `_backfill_pending` | `dict[str,int]` | 在途 | 計數(不是集合) |
| `_backfilled` / `_backfill_gave_up` / `_tick_armed` | `set[str]` | 日別+訂閱期 | 回補記帳 |
| `_backfill_failed` / `_backfill_timeouts` | `dict[str,int]` | 日別 | 失敗 / 逾時分帳 |
| `_backfill_timeout_handles` | `dict[str, TimerHandle]` | 在途 | per-code 重排 timer |
| `_trade_status` | `dict[str, tuple[str,bool]]` | 日別+訂閱期 | TradeStatus 轉態觀測 |

→ **13 份 per-code 平行結構**,每一份都有自己的清空時機(日別 / 訂閱期 / 在途)。
這是這個檔最大的結構性負債(見 F-11),也是 columnar 化的前置條件。

### 1.3 邊界檔

- `watchlist_service.py`:三個入口(PUT / Discord `/watch add` / `remove`)共用一把
  `asyncio.Lock`,**鎖只到落檔為止**(`_commit`),訂閱 + 廣播在鎖外(`_settle`),
  並發正確性改由 `seq` 在 engine 端保證(舊名單後到整段跳過)。設計正確,零效能問題。
- `stock_watchlist.py`:`normalize()` 是 O(n²)(`code not in codes` 線性掃),n ≤ 150 →
  最壞 ~22k 次比較 ≈ 數百 µs,**每次 PUT 才跑一次**。不是問題。
- `stkfut_map.py`:`_product_index` 以 `(mtime_ns, size)` 為鍵的 process 級 cache;
  每次 `lookup_product` 付一次 `path.stat()` syscall(見 F-19,量級極小)。
- `stkfut_catalog.py`:當日 in-memory cache + `asyncio.Lock` 單飛 + boot prewarm。
  TC4 `QUERYALLINSTRUMENT` 實測 1.93 s,已移出熱路徑。**這裡不要動**。
- `stock_names.py`:純離線 CLI + 一次性 `load_names()`,零熱路徑。

---

## 2. 熱路徑逐條(含實測)

### HP-1 `_handle_quote` — 每則 TC4 REALTIME 推播一次

| 情境 | 實測 per-call | 單核理論上限 |
|---|---|---|
| 成交型(TradeQuantity > 0) | **49.49 µs** | 20,208 msg/s |
| 純簿更新(TradeQuantity = 0) | **19.25 µs** | 51,961 msg/s |

(`bench_b04c.py`:80 檔訂閱、32 檔在 `_tick_targets`、主圖 = 第一檔、**未掛 signal hub**。
掛上 hub 之後每 tick 還要加上 `on_tick` 全規則評估 + 每則推播的 `on_book`,那是 B05 的帳。)

現況 80 檔自選(`data/stock_watchlist.json` 實查:codes 80、最大群組「盤前篩選」32 檔)。
以每檔開盤時段 2–5 則/s 估,穩態 ≈ 160–400 msg/s → loop 佔用 **0.8–2%**;
開盤瞬間 10× 突波 ≈ 1,600–4,000 msg/s → **8–20%**。上限 150 檔時線性翻倍。
**結論:現況不是瓶頸,但可用餘裕只有 ~5×,而且和 signal hub、group poll 共用同一條 loop。**

### HP-2 `parse_stock_realtime` — 每則推播一次,28.8 µs(佔 HP-1 的 58%)

拆解(`bench_b04e.py`):

| 段 | per-call | 佔比 | 每則推播都跑? |
|---|---|---|---|
| `_taipei_time`(`strptime` + `timedelta` + 2×`strftime`) | **11.06 µs** | 38% | 只有成交型 |
| `_parse_levels` × 2(Bid/Ask 各五檔) | **9.98 µs** | 35% | **是** |
| meta 段(6×`to_milli` + 2×`_hhmmss` + `StockMeta`) | **4.45 µs** | 15% | **是** |
| 其餘(TradeStatus / price / qty / derive_side / is_trial) | ~3.3 µs | 12% | 是 |

三段各自都有便宜的修法,合計可把 28.8 µs 壓到 **~12 µs**(見 F-01/F-02/F-03)。

### HP-3 `StockDayState.ingest` — 每筆收下的成交一次,4.11 µs

`_apply` 做:deque append、high/low running max/min、VWAP 分子分母、
`int(tick.time[:2])*60+int(tick.time[3:5])` 算分鐘鍵、`minutes.setdefault(MinuteAgg())`、
`_fold_vp`(`snap_down_milli` + `setdefault([0,0,0])`)。
**全 O(1),寫得很乾淨,不要動**。

### HP-4 `_flush_ticks` — 每 0.1 s 至多一次

`_pending_ticks` 是 `list[dict]`,每筆 9 個鍵。打包只換掉 list 參照(O(1))+ 一次 publish。
量測:300 筆打包的 `json.dumps` = **263.9 µs / 43,118 bytes**。
**打包機制本身近乎零成本;真正的成本在 WS 送出端每個 client 各做一次 `json.dumps`**(F-15)。

### HP-5 `group_snapshot` — 前端每 60 s 一次(`useGroupSnapshots` `refetchInterval` = 60 s、`staleTime` 55 s)

以「一檔跑了一整天 = 6,000 tick / 270 分鐘 / 200 個 VP 檔位」為基準
(log 實查 `logs/server-20260911-0905.log`,單檔回補最大 3,368 ticks @09:0x,全日推估 6–10k):

| 檔數 | python + `json.dumps`(**event loop 阻塞**) | payload |
|---|---|---|
| 10 | **5.7 ms** | 303 KB |
| 30 | **19.7 ms** | 909 KB |
| 50 | **36.1 ms** | 1,515 KB |
| 150(上限) | **103.2 ms** | 4,545 KB |

單檔 `light_snapshot()` = **168 µs**,其中絕大部分是 `_minutes_payload()` 的
`sorted(self.minutes.items())` + 270 個 dict 重建,加上 `vp` 的 200 次 `str(price)` + `list(cell)`。

**這是本區塊最大的單點 event-loop 阻塞。** 當前最大群組 32 檔 ≈ 21 ms;
上限 150 檔 = 103 ms —— 期間 WS 心跳、逐筆打包、廣播、所有 route 全部排隊。

### HP-6 `snapshot(tape=True)` — 使用者切檔(`GET /api/stock/state/{code}`)

| tick 數 | python | JSON |
|---|---|---|
| 6,000 | 1.77 ms | 535 KB |
| 20,000(deque 上限) | **6.98 ms** | **1,774 KB** |

頻率 = 使用者操作級(切檔 / 重連 / seq 跳號 refetch)。可接受但不優雅。

### HP-7 `_flush_watchlist_loop` — 每 1 s 一次

80 檔全 dirty 時整輪 `_quote_payload` = **0.117 ms**。`_quote_payload` = 1.37 µs/檔。
**完全不是問題,不要動。**

### HP-8 `_backfill_worker` — 開盤一次 + 群組輪詢觸發

prod log 實證(`logs/server-20260911-0905.log`):
```
09:05:10  backfill round 1: 259 pending, 1 ticks
…
09:05:17  backfill round 13: 241 pending, 83 ticks
09:05:17  backfill done: 83 ticks from 260 symbols     ← 整批 7 s
09:05:17  stock backfill 6207: 136 ticks
09:05:17  stock backfill 3481: 2256 ticks              ← 逐檔收割 ~0.01–3 s
09:05:21  stock backfill 6451: 107 ticks
```
`prepare_backfill` 整批先 SubHistory(perf/opening-backfill-parallel 已做過,
40 檔 40.7 s → 0.87 s),之後逐檔收割全走 `to_thread`。**loop 不被阻塞,設計正確。**

### HP-9 `set_watchlist` — 使用者 PUT / Discord `/watch`

逐項 `async with self._pool_lock:` + `await asyncio.to_thread(self._acquire, …)`。
150 檔 = 150 次 executor round-trip + 150 次取鎖。ZMQ REQ 仍在鎖內(已知殘餘,
`watchlist_service.py:238` 與 next-time 08-26 節有記)。**頻率是使用者操作級,不要動。**

---

## 3. Findings

> 排序:先「在熱路徑上 + 修起來便宜」,再「架構債」。
> `location` 全部是實查行號(2026-09-13 master `caca1d30`)。

---

### F-01 `_taipei_time` 每筆成交付一次 `datetime.strptime`(parse 層 38%)

**位置** `copycat/live/stock_models.py:89-95`
**熱路徑** 是(每筆成交 tick 一次;回補也走同一支,一檔 6,000 筆 = 66 ms)
**category** algorithmic / allocation **severity** high

```python
def _taipei_time(precise_utc: str, date_utc: str) -> tuple[str, str]:
    s = precise_utc.zfill(12)
    hh, mm, ss, frac = int(s[:2]), int(s[2:4]), int(s[4:6]), s[6:9]
    base = _dt.datetime.strptime(date_utc, "%Y%m%d")      # ← 8.8 µs
    local = base + _dt.timedelta(hours=hh, minutes=mm, seconds=ss) + _TAIPEI_OFFSET
    return f"{local:%H:%M:%S}.{frac}", f"{local:%Y-%m-%d}"
```

`date_utc` 一整天只有一兩個值,卻每筆 tick 重新 `strptime` 一次,再用兩次 `strftime`
把 `datetime` 印回字串。

**實測**(`bench_b04e.py` + 原型對照):

| 版本 | per-call |
|---|---|
| 現況 | **8.82 µs** |
| 日期字串 → `(當日 ISO, 隔日 ISO)` 的 dict cache + 整數 divmod + f-string | **0.96 µs** |

兩個版本對 `('020304567','20260913')`(不跨日)與 `('180000000','20260913')`(跨日進位)
輸出**逐字相同**(原型已 assert)。

**影響** parse 28.8 → ~21 µs;`_handle_quote` 成交型 49.5 → ~41 µs(−17%)。
回補一檔 6,000 筆省 47 ms、20,000 筆省 157 ms(在 `to_thread` 上,但會佔用 executor)。

**fix**
```python
_DATE_CACHE: dict[str, tuple[str, str]] = {}   # "YYYYMMDD" → (當日 ISO, 隔日 ISO)
# 台北 = UTC+8,秒數 ≥ 86400 即跨到隔日;不必建 datetime 物件
```
cache 無界但鍵值域 = 日期字串(一天一兩個),可用 `functools.lru_cache(maxsize=8)`
省掉手寫失效。

**risk** `_taipei_time` 是 `parse_stock_realtime` 與 `parse_hist_tick` **唯一共用**的時間轉換點
(CLAUDE.md:「回補與 live 必須是同一把尺」)。改這裡等於同時改兩條路,測試要蓋:
(a) 不跨日、(b) UTC 16:00+ 跨日(個股期夜盤)、(c) `precise_utc` 短於 12 位的 `zfill`、
(d) 毫秒 `frac` 原樣保留。`is_trial_window` 做**字串比較**,格式必須逐字不變
(`HH:MM:SS.fff`,秒與毫秒都補零)。
**effort** S

---

### F-02 `StockMeta` 每則推播全量重建,而它一天只變一兩次

**位置** `copycat/live/stock_models.py:201-210`;寫入端 `copycat/server/stock_engine.py:1232`
**熱路徑** 是(**每則推播**,含純簿更新) **category** allocation **severity** high

```python
meta = StockMeta(
    name=str(msg.get("SecurityName", "")),
    ref_milli=to_milli(msg.get("ReferencePrice", "")),
    upper_milli=to_milli(msg.get("UpperLimitPrice", "")),
    lower_milli=to_milli(msg.get("LowerLimitPrice", "")),
    y_close_milli=to_milli(msg.get("YClosedPrice", "")),
    y_volume=_to_int(msg.get("YTradeVolume", "")),
    open_time=_hhmmss(str(msg.get("OpenTime", ""))),
    close_time=_hhmmss(str(msg.get("CloseTime", ""))),
)
```
```python
state.update_meta(meta)        # stock_state.py:144 —— 無條件覆寫
```

**實測** meta 段 **4.45 µs / 則**。參考價、漲跌停、昨收、開收盤時間在盤中**不會變**
(除權息隔日才變),等於每則推播白燒 4.45 µs 去做一個恆等賦值。

以 300 msg/s 估 = 1.3 ms/s;開盤突波 3,000 msg/s = 13 ms/s。

**fix** 在 parse 層以八個 raw 欄位的 tuple 當指紋,命中就回**上一個 `StockMeta` 物件**
(它是 `frozen=True`,共享安全):
```python
fp = (msg.get("SecurityName"), msg.get("ReferencePrice"), msg.get("UpperLimitPrice"),
      msg.get("LowerLimitPrice"), msg.get("YClosedPrice"), msg.get("YTradeVolume"),
      msg.get("OpenTime"), msg.get("CloseTime"))
```
per-symbol 的 cache 住 parse 層會引進狀態(parse 目前是純函式);
**比較乾淨的落點是 engine**:`_handle_quote` 保留上一則的 fp,相同就跳過 meta 重建與
`update_meta`。此時 `prev_limits`(`stock_engine.py:1228-1230`)與
`was_meta_none`(:1227)兩個判斷天然仍成立。

**risk**
- `parse_stock_realtime` 目前是**純函式**且被四處呼叫(engine / 測試 / golden fixture)。
  把 cache 放進去會破壞純度 → 建議放 engine 層,parse 層改成可選 `prev_meta` 參數
  (keyword-only,沿 `trial_windows` 的既有慣例)。
- `StockMeta.y_close_milli` 是「除權息日判別」的唯一落點(該 dataclass 註解),
  指紋必須含 `YClosedPrice`,漏掉會讓除權息日的 meta 卡在前一天。
- 失效樣態是**靜默的**:漲跌停不更新 → 側欄亮燈與鎖停補判(`relabel_locked_side`)全錯,
  畫面零訊號。必須有「值變了就必定更新」的 golden test。

**effort** M

---

### F-03 `_parse_levels` 每則推播做 20 次字串串接 + 20 次 `dict.get`

**位置** `copycat/live/stock_models.py:171-185`
**熱路徑** 是(**每則推播兩次**,Bid + Ask) **category** algorithmic **severity** high

```python
for i in range(_DEPTH):
    suffix = "" if i == 0 else str(i)
    price = to_milli(msg.get(price_key + suffix, ""))      # ← 字串串接 ×10
    if price is None:
        continue
    vol = _to_int(msg.get(vol_key + suffix, ""))
    levels.append((price, vol or 0))
```

**實測** 單側 **4.99 µs**,雙側 **9.98 µs** = parse 的 35%。

**fix** 模組級預算 key 表(零串接):
```python
_BID_KEYS = (("Bid", "BidVolume"), ("Bid1", "BidVolume1"), … ("Bid4", "BidVolume4"))
_ASK_KEYS = (("Ask", "AskVolume"), …)
```
再把 `to_milli` 的 hot path 內聯(它是 `tc4common.to_milli_units`,每檔位一次 0.50 µs)。
估可降到 ~6 µs 雙側(−4 µs/則)。

**risk** `_parse_levels` 的「`0` 是市價單佇列、要原樣保留」語意不可動
(`_best_limit_price` 依賴它)。`_DEPTH = 5` 改成寫死的 key 表等於把深度硬編 ——
TC4 若哪天推七檔,現在的 `range(_DEPTH)` 改一個常數即可,key 表要改一整張。
接受這個取捨要在表旁邊留 `assert len(_BID_KEYS) == _DEPTH`。
**effort** S

---

### F-04 群組快照每 60 s 全量重送:32 檔阻塞 loop 21 ms、150 檔 103 ms,payload 0.9–4.5 MB

**位置** `copycat/server/stock_engine.py:838-856`、`copycat/live/stock_state.py:237-264`、
`copycat/server/app.py:1707-1736`、前端 `frontend/src/hooks/useGroupSnapshots.ts:119-137`
**熱路徑** 每 60 s(交易時段) **category** serialization / architecture **severity** high

```python
def group_snapshot(self, codes: list[str]) -> dict[str, dict]:
    self._flush_ticks()
    out: dict[str, dict] = {}
    for code in codes:
        state = self._states.get(code)
        subscribed = code in self._refs
        light = state.light_snapshot() if state is not None else dict(_EMPTY_LIGHT)
        …
        out[code] = {**light, "no_data": …, "backfilling": …}
    return out
```

**實測**(`bench_b04b.py`,每檔 6,000 tick / 270 分鐘 / 200 VP 檔位):

| 檔數 | loop 阻塞 | payload |
|---|---|---|
| 10 | 5.7 ms | 303 KB |
| 30 | 19.7 ms | 909 KB |
| 50 | 36.1 ms | 1,515 KB |
| 150 | **103.2 ms** | **4,545 KB** |

`light_snapshot()` 單檔 168 µs。FastAPI 的序列化開銷實測**不是問題**
(`bench_b04d.py`:32 檔端到端 6.6 ms vs 裸 `json.dumps` 10.1 ms —— `-> dict` 推導出的
response model 在 pydantic v2 是淺驗證,沒有深層遞迴成本)。**成本全在 python 組裝 + `json.dumps`。**

**關鍵觀察:這份重送多半是冗餘的。** #180/#182 之後群組卡片已經靠 WS `ticks` 打包 +
`seq == acc.seq + 1` 逐筆前進,60 s 那一發只是**重播種**。前端 `useGroupSnapshots`
每次拿回整份 `minutes`(270 項)、整份 `vp`(200 項),而其中幾乎沒有一格變過。

**fix(依效益排序)**
1. **`?since=` delta**:請求帶 per-code 的 `seq`,後端只回 `seq` 不同的檔;相同者回
   `{"seq": n, "unchanged": true}`。零風險的前置是**先只做「整檔 unchanged」**,
   不做分鐘級 delta —— 活躍檔照舊全量、冷門檔(盤後 / 薄股)直接省掉。
2. `_minutes_payload` 的 wire 形增量維護(見 F-05)。
3. 把 `group_snapshot` 的組裝從 loop 移到 `to_thread`。**目前做不到** —— 它會呼叫
   `_flush_ticks()`(publish 副作用,只能在 loop 上),且 `_states` 由 loop 獨佔寫入。
   要做得先把「flush」與「取值」拆成兩步(見 F-20)。
4. 序列化換 `orjson`(見工具選型;推估 2–4×,未實測)。

**risk(跨檔契約,必須同動)**
- CLAUDE.md §4「**個股 `seq` 的兩個口徑**」:`snapshot.seq` = `ticks` 尾筆序號。
  delta 化等於讓 `seq` 多一個「重播種判準」的角色 —— 前端
  `lib/stock-accum.ts::fromSnapshot`(由尾回推 React key)與
  `hooks/useGroupLiveAccums.ts`(per-code `seq === acc.seq + 1`)兩個讀者都要同動。
- CLAUDE.md §4「**快照與打包的 seq 對齊 = 同一個 race 的兩道閘**」:後端
  `group_snapshot()` 取值前必 `_flush_ticks()` 是其中一道閘。任何「把組裝移出 loop」
  的改法都不可以把這道閘拆掉,只能改成「loop 上先 flush、再交 to_thread 組裝」。
- 「上限 150 檔」的效能預算註解散在 `stock_engine` / `watchlist_service` /
  `stock_state` / `GroupGridView`(CLAUDE.md §4「自選上限常數多邊同值」第二類讀者),
  改了量級要重算。

**effort** L

---

### F-05 `_minutes_payload` 每次呼叫 `sorted()` + 重建 270 個 dict

**位置** `copycat/live/stock_state.py:200-219`
**熱路徑** 每 60 s × 檔數(群組)+ 每次切檔(單檔頁) **category** allocation **severity** high

```python
return {
    str(k): {"c": m.close_milli, "v": m.volume, "i": m.inner, "o": m.outer,
             "u": m.unch, "h": m.high_milli, "l": m.low_milli}
    for k, m in sorted(self.minutes.items())
}
```

一天 270 個分鐘桶,每次 `light_snapshot()` / `snapshot()` 都重排序 + 重建 270 個小 dict
+ 270 次 `str(k)`。這就是 168 µs 的主體。

**fix** 兩層都成立:
1. `self.minutes` 是 `dict[int, MinuteAgg]`,**插入序天然遞增**(分鐘鍵單調),除了
   `apply_backfill` 重放時仍是遞增。→ `sorted()` 在現況是**恆等操作**,可用
   「維護一份已排序 key list」或直接證明單調後拿掉(要先確認回補重放不會逆序)。
2. 對「已收盤的分鐘」做 wire 形 memo:一根分鐘 K 在下一分鐘開始後就不會再變
   (`apply_backfill` 會整份 reset,那時一併作廢)。快取 `dict[int, dict]`,
   只有當下那一分鐘每次重建。270 → 1。

**估計效益** `light_snapshot` 168 µs → ~30 µs;150 檔 group 的 python 段 40 ms → ~8 ms。

**risk** wire 形鍵名的「單一定義」不可散掉(`_minutes_payload` docstring 明說兩邊各寫
一份的漂移樣態是 `h`/`l` 留 undefined → 當日高低標記靜默消失)。memo 的作廢點要
涵蓋 `reset()` / `apply_backfill()` / `_apply()` 對當下分鐘的更新,**漏一個就是靜默錯值**。
**effort** M

---

### F-06 tick 儲存是 Python 物件陣列:單檔最壞 6.18 MB,150 檔 0.91 GB

**位置** `copycat/live/stock_state.py:19` `_TICKS_MAXLEN = 20_000`、:47 `deque[StockTick]`
**熱路徑** 記憶體常駐(非 CPU) **category** data-structure **severity** high

**實測**(`bench_b04b.py`,tracemalloc):

| 每檔 tick 數 | 單檔 state | 150 檔 |
|---|---|---|
| 6,000(常見) | 1.90 MB | **0.28 GB** |
| 20,000(deque 上限) | 6.18 MB | **0.91 GB** |

單筆 `StockTick`(10 欄 frozen dataclass,無 slots)= 5.44 MB / 20k = 278 bytes。

**替代方案實測**:

| 方案 | 20k 筆 | 相對 | 每 tick 寫入成本 |
|---|---|---|---|
| 現況 `dataclass(frozen=True)` | 5.44 MB | 1.0× | 0.85 µs |
| `dataclass(frozen=True, slots=True)` | 4.53 MB | 0.83× | 0.92 µs |
| **stdlib `array('q')` 七欄 columnar** | **1.12 MB** | **0.21×** | 0.92 µs |
| `array('i'/'l')` 四位元組(推估) | ~0.56 MB | 0.10× | 同上 |

**為什麼 columnar 能省這麼多**:`code` / `trade_date` 是 per-state 常數(不必逐筆存)、
`time` 可存成當日毫秒整數、`side` 可存成 int8、`is_trial` 的 tick 根本不會被收下
(`ingest` 在 dedup 前就短路)。真正 per-tick 的只有 7 個整數。

**fix** 見 §5「Q8:columnar 化要動哪裡」。
**risk** 見同節 —— 好消息是 `state.ticks` **在 `stock_state.py` 之外零讀者**(全庫 grep 實查)。
**effort** L

---

### F-07 主圖五檔 `book` 訊息零 coalesce(同一條流上唯一沒有節流的路)

**位置** `copycat/server/stock_engine.py:1359-1360`
**熱路徑** 是(每則主圖推播一則 WS 訊息) **category** render / serialization **severity** medium

```python
if code == self._main:
    self._publish({"type": "book", "code": code, "bids": book.bids, "asks": book.asks})
```

同一條 `/ws/stock` 上的另外兩種訊息都節流過:
- `ticks` — `_flush_ticks` 0.1 s 打包(`stock_engine.py:1340-1343`)
- `watchlist_quote` — `_flush_watchlist_loop` 1 s 合併(:1816)

而 `book` 是**逐則直發**。CLAUDE.md 也記著期貨那邊是「期貨 WS 0.1 s coalesce 流」——
個股這一條是漏網的。活躍股的簿更新可達每秒十幾則,每則都要:
per-client `put_nowait` × N 個分頁 → 每 client 一次 `json.dumps` → 前端 `PriceLadder` 重繪。

**fix** 沿 `_flush_ticks` 的 dirty + 單一 `call_later` 樣板做 `_pending_book`
(**只保最新**,簿沒有「不可丟」語意 —— 與逐筆相反)。閒時零喚醒。

**risk**
- 閃電梯 / 五檔最多晚 0.1 s。與逐筆打包當初的 user 拍板(「主圖最多晚 0.1 s,接受」)同量級,
  但**簿是下單決策面**,要 user 明確拍板。
- `signal_hub.on_book(code, state)`(:1365-1366)**不可跟著節流** —— 鎖板打開的無成交
  觸發靠它,漏一則簿就漏一顆訊號。兩者要顯式分離:節流只作用於 WS publish。

**effort** S

---

### F-08 `_observe_trade_status` 每則推播付一次 `strftime`,而 99.99% 的推播沒有轉態

**位置** `copycat/server/stock_engine.py:1402`(`in_window = _observe_window_now()`)
**熱路徑** 是(每則現貨推播) **category** algorithmic **severity** medium

```python
status = str(quote.get("TradeStatus", "0") or "0")
qty = quote.get("TradeQuantity") or "-"
in_window = _observe_window_now()        # ← 2.83 µs,每則都算
prev = self._trade_status.get(code)
…
prev_status, episode = prev
if status == prev_status:
    return                               # ← 幾乎恆走這條
```

**實測** `_now_taipei_time()` = 2.44 µs(`datetime.now()` 只要 0.13 µs,`%H:%M:%S.%f`
格式化吃掉 2.3 µs);`_observe_window_now()` = 2.83 µs。

**fix** 把 `in_window` 的計算搬到 `if status == prev_status: return` **之後**。
順手可把 `_trial_now`(:1405/:1420)與 `_now_taipei_time`(:1408/:1427)重複取的時鐘
收成一次。省 ~2.8 µs/則 = HP-1 純簿路徑的 15%。

**risk** 首見分支(`prev is None`)要保留 `in_window` 的計算 —— 那條路本來就要用它分三種處置
(`stock_engine.py:1404-1415`)。移動之後 `_TRADE_STATUS_FMT` 印出的 `trial_window=` 欄
語意不變(仍是「記錄那一刻的窗」)。既有蒐證 grep 判準(前綴 `trade-status-observe`)不受影響。
**effort** S

---

### F-09 `snapshot(tape=True)` 把兩萬筆 tick 逐筆組成 dict 只為了序列化一次

**位置** `copycat/live/stock_state.py:295-307`
**熱路徑** 使用者切檔 / 重連 / seq 跳號 refetch **category** allocation **severity** medium

```python
"ticks": [
    {"t": t.time, "p": t.price_milli, "q": t.qty, "side": t.side,
     "b": t.bid_milli, "a": t.ask_milli}
    for t in self.ticks
] if tape else [],
```

**實測** 6,000 筆 1.77 ms / 535 KB;20,000 筆 **6.98 ms / 1,774 KB**(event loop 上)。

**fix**
1. columnar 之後這裡改成一次 zip 展開(或直接手刻 JSON 串接,省掉中間 dict)。
2. `tape` 分頁(`?tape_from=<seq>`)—— 前端逐筆明細其實只畫最近幾百筆,
   要確認 `TickTape` 的真實需求(前端區塊的事)。

**risk** `ticks` 的六個鍵名是 wire 契約,`stock-accum.ts::fromSnapshot` 由 `snap.seq`
**由尾回推**指派 React key `n`(CLAUDE.md §4「個股 seq 的兩個口徑」)—— 改變回傳筆數
= 改變回推起點,兩邊必須同動,否則「成交明細 tbody 靜默整片重掛」。
**effort** M(單獨做)/ S(跟 F-06 一起做)

---

### F-10 WS 廣播對每個 client 各做一次 `json.dumps`

**位置** `copycat/server/ws.py:262-265`(`_send` → `websocket.send_json(msg)`)、
`copycat/server/ws.py:65-80`(`publish` 把**同一個 dict** 塞進每個 client 的 queue)
**熱路徑** 是(每則廣播 × client 數) **category** serialization **severity** medium

```python
async def _send() -> None:
    async for msg in stream:
        async with send_lock:
            await websocket.send_json(msg)      # 每 client 各自 dumps 一次
```

**實測** 300 筆的 `ticks` 打包 `json.dumps` = 263.9 µs。使用者實際會開
「dev 4173 + 另一個分頁 + Discord 開的頁」幾個分頁,3 個 client = 792 µs / 打包,
每秒最多 10 個打包 = **7.9 ms/s**,純粹重複勞動。

**fix** `WsBroadcaster.publish` 端序列化一次 → queue 裡放 `str`,`relay._send` 改
`send_text`。心跳 `PING` 可預先序列化成模組常數。

**risk** 六路 WS(capital / futures / corr / river / stock / index)共用 `ws.py`,
改 queue 的元素型別 = 改六條路。`stream(seed=…)` 的種子也要一起轉。
測試裡的 fake `WsConnection` 只有 `send_json` / `receive`(`ws.py:145-154`)—— Protocol 要加 `send_text`。
**這不是 B04 一個區塊的決定**,屬全站序列化策略(見工具選型 `orjson`)。
**effort** M

---

### F-11 13 份 per-code 平行 dict/set —— 每個都有自己的清空時機

**位置** `copycat/server/stock_engine.py:292-346`、:300-301、:319-346、:370、:380
**熱路徑** 否(但擋住 F-06 的 columnar 化) **category** architecture **severity** medium

```python
self._refs: dict[str, set[str]] = {}
self._states: dict[str, StockDayState] = {}
self._symbol_to_key: dict[str, str] = {}
self._no_data: set[str] = set()
self._backfill_pending: dict[str, int] = {}
self._backfilled: set[str] = set()
self._tick_armed: set[str] = set()
self._backfill_failed: dict[str, int] = {}
self._backfill_timeouts: dict[str, int] = {}
self._backfill_gave_up: set[str] = set()
self._backfill_timeout_handles: dict[str, asyncio.TimerHandle] = {}
self._failed_resubs: set[str] = set()
self._trade_status: dict[str, tuple[str, bool]] = {}
```

清空語意有**四種**且散在六處:日別(rollover stage2)、訂閱期(`set_watchlist` removed
迴圈 / `set_main_contract`)、在途(worker 各離開路徑)、reconnect。
`set_watchlist` 的移除迴圈(:584-592)與 `set_main_contract`(:653-659)是**逐字重複的七行**。

這不是效能問題本身,但它是 F-06 的前置:要把 per-code 狀態改成 columnar / 預配置,
第一步就是讓「一檔的所有狀態」有單一持有者。

**fix** 抽 `_CodeSlot` dataclass(`state` / `owners` / `backfill: _BackfillLedger` /
`trade_status` / `no_data`),把四套清空語意變成
`slot.reset_day()` / `slot.reset_subscription()` 兩個方法。
`_refs` 的 owner set 與 `_states` 合併之後,「只增不減」與「訂閱期為界」的兩種生命週期
要顯式分欄(現在是靠兩個 dict 的存在與否隱式表達,註解寫了 40 行在解釋)。

**risk** 這是**純重構、零行為**,但 blast radius 覆蓋整個檔與
`tests/server/test_stock_engine.py`。`_states` 的「只增不減」與 `_refs` 的「真退訂即移除」
是兩條不同的不變式,合併時必須各自保留 —— 合錯的失效樣態是「退訂後晚到的推播沒有落點」
或「重新訂閱拿回舊 state」,兩者都零錯誤訊號(:296-299 註解已經點名過)。
**effort** XL

---

### F-12 單檔 1832 行 / 57 個方法 / 七個職責

**位置** `copycat/server/stock_engine.py` 全檔
**熱路徑** 否 **category** architecture **severity** medium

實查:`total=1832 / blank=184 / 註解 437 / docstring ~393 / 實碼 ~818`。
**註解 + docstring(830 行)比實碼(818 行)還多。**

職責清點:
1. refcount 訂閱池(`_acquire` / `_release` / `set_watchlist` / `set_main_contract`)
2. 個股期對照腿(`_acquire_stkfut` / `_release_stkfut` / `_handle_stkfut` / `_stkfut_owner_missing`)
3. 兩段式 rollover + checkpoint 時鐘(`rollover_stage1` / `_rollover_stage2` / `_checkpoint_loop`)
4. 訂閱失敗對帳重試(`_retry_subscribe_loop` / `_retry_round` / `_round_robin`)
5. 回補 worker + 六套記帳 + 逾時重排 timer(11 個方法)
6. 推播分派與狀態機編排(`_handle_quote`,**180 行單一方法**)
7. 廣播 / 節流 / 逐筆打包 / 檢視集合(`_publish` / `_flush_ticks` / `set_view` / `_flush_watchlist_loop`)
8. 試撮窗 / 處置股 / TradeStatus 觀測(模組級 5 個函式 + 4 個方法)

**對效能有沒有幫助?** 直接幫助 **很小**(Python 的方法呼叫跨不跨檔沒差)。
間接幫助 **很大**:
- 職責 5(回補記帳)完全不碰熱路徑,把它抽成 `BackfillLedger` 之後
  `_handle_quote` 的可讀性與可量測性(能單獨 profile)才立得起來。
- 職責 7(廣播 / 節流)抽成 `StockFanout` 之後,F-07(book coalesce)與 F-10(預序列化)
  才有一個自然的落點,不必在 1832 行裡見縫插針。
- `_handle_quote` 180 行單一方法是本區塊**唯一**不能用 profile 精確歸因的地方
  (cProfile 只會給你一行)。切成 `_route` / `_apply_state` / `_fanout` 三段之後
  才量得出每段佔比。

**fix** 建議切法(保留 `StockEngine` 為 facade,對外簽名零改動):
```
stock_engine.py        StockEngine facade + _handle_quote 編排(~400 行)
stock_pool.py          refcount 訂閱池 + stkfut 腿 + 重試對帳(~450 行)
stock_backfill.py      BackfillLedger + worker + 逾時重排(~400 行)
stock_fanout.py        _publish / _flush_ticks / _views / _flush_watchlist_loop(~250 行)
stock_clock.py         試撮窗 / 觀測窗 / 處置股 / TradeStatus 觀測(~200 行)
```
**risk** `_handle_quote` 內的**執行順序**是一連串 bug 修出來的不變式
(夜盤早退 → 觀測 → no_data 復原 → book/meta → 漲跌停重排 → rollover 快路徑 →
stage2 → 首筆點火 → ingest → 轉態補推 → book publish → on_book)。
拆檔時任何一步移位都會打破一個註解裡寫明的失效樣態。必須逐步 + characterization test。
**effort** XL

---

### F-13 `_recompute_tick_targets` 對空 `_views` 用 `frozenset().union(*[])`

**位置** `copycat/server/stock_engine.py:1779-1780`
**熱路徑** 否(只在 view 登記 / 除名) **category** allocation **severity** low

```python
self._tick_targets = frozenset().union(*self._views.values())
```
N 條連線 × M 檔的聯集,每條連線的 `view` 訊息各觸發一次。8 個分頁 × 150 檔 = 1,200 次
集合合併,約數十 µs,**頻率 = 開頁 / 換組**。正確且夠快,**列此僅為完整性,不要動**。

---

### F-14 `stream()` 的種子對每個新連線重建整份自選 payload

**位置** `copycat/server/stock_engine.py:1750-1757`
**熱路徑** 否(每次連線 / 重連) **category** allocation **severity** low

```python
return self._ws.stream([self._quote_payload(code) for code in self._watchlist])
```
150 檔 × 1.37 µs = **0.21 ms**。WS 重連風暴(前端靜默 watchdog 誤判時每 35 s 全部重連)
下也只是 8 條 × 0.21 ms。**不要動。**

---

### F-15 `quotes()` / `policy_quotes()` 為了取一個 `chg_pct` 建整份 `_quote_payload` dict

**位置** `copycat/server/stock_engine.py:760`、:792
**熱路徑** 否(Discord 同群摘要 / 每顆掃單簇政策事件) **category** allocation **severity** low

```python
out[code] = (name, self._quote_payload(code)["chg_pct"])
…
chg_pct=self._quote_payload(code)["chg_pct"],
```
1.37 µs × 同伴數(通常 < 20)。**刻意的設計**(docstring 明寫「`chg_pct` 一律走
`_quote_payload` 這個唯一定義,不自己再算一次 —— 除權息日的分母是 `meta.ref_milli`」)。
**不要動** —— 抽一個 `_chg_pct(code)` 純函式是唯一可接受的改法,而收益是零。

---

### F-16 `_backfill_worker` 批次去重只在 `fresh`,逐檔套用仍走完整 `batch`

**位置** `copycat/server/stock_engine.py:1553-1574`
**熱路徑** 開盤一次 **category** algorithmic **severity** low

```python
fresh = list(dict.fromkeys(code for code, generation in batch if generation == self._generation))
if len(fresh) >= 2:
    await asyncio.to_thread(self._source.prepare_backfill, fresh)
for code, generation in batch:            # ← 未去重,同 code 可能跑兩次
    await self._run_backfill_job(code, generation)
```
同一檔被兩個入列點送進同一批時,`prepare_backfill` 只 Sub 一次(正確),
但 `_run_backfill_job` 會跑兩次完整收割。第二次通常被
`_backfill_settled` 的計數擋不住(那只是記帳)—— 它會真的再打一次 TC4。

prod log 實測開盤 260 symbols 整批 7 s、逐檔收割最長 ~3 s,重複一次 = 多 3 s 單工佔用。
**fix** `for code, generation in dict.fromkeys(batch):`(tuple 去重,保序)。
**risk** `_backfill_pending` 的計數語意依賴「每個 put 都有一次 settle」
(:1488-1498 docstring 寫明計數而非集合的理由)。去重之後被跳過的那一筆
**仍必須 `_backfill_settled(code)`**,否則旗標永久為真、卡片永遠「回補中…」。
**effort** S

---

### F-17 `lookup_product` 每次呼叫付一次 `path.stat()` syscall

**位置** `copycat/stkfut_map.py:138-161`
**熱路徑** 送單路徑(頻率 = 使用者按鈕) **category** blocking-io **severity** low

```python
def _product_index(path: Path) -> dict[str, dict]:
    sig = _stat_sig(path)          # ← 每次 os.stat
    cached = _INDEX_CACHE.get(path)
```
Windows `os.stat` ≈ 5–20 µs。頻率是使用者操作級。
**設計是對的**(檔案由另一個 process 的 CLI 重寫,以 `mtime_ns` 偵測是唯一可靠判準,
A4 註解已論證)。**不要動。**

---

### F-18 `normalize()` 是 O(n²),但 n ≤ 150 且頻率 = 每次 PUT

**位置** `copycat/stock_watchlist.py:132-165`(`if code not in codes` 線性掃 × 兩層)
**熱路徑** 否 **category** algorithmic **severity** low

150 檔最壞 ~22,000 次字串比較 ≈ 數百 µs,每次存檔一次。
`WatchlistService._commit` 每次還會多跑一次 `_current_canonical()`(讀檔 + normalize)
做零寫比對 —— 那是刻意的(R18,避免同內容 PUT 把整份自選斷訂一次)。
**這裡不要動。** 若真要優化,`dict.fromkeys` 去重可把 O(n²) 降成 O(n),
但「保序去重」的語意必須逐字保留,而收益是 0.3 ms/次。

---

### F-19 `_handle_quote` 對非自選、非主圖、非檢視集合的檔仍走完整解析

**位置** `copycat/server/stock_engine.py:1204`(parse)相對於 :1319(收件人判定)
**熱路徑** 是 **category** algorithmic **severity** medium

現況:只要 symbol 在 `_symbol_to_key` 裡(= 訂閱池曾經有過,**只增不減**),
就完整 parse + ingest + 訊號評估,即使:
- 它不是主圖、不在任何 `view` 裡(逐筆不會送出瀏覽器)
- 它已被退訂(`_symbol_to_key` 刻意不清,:296-299)

「退訂後殘留的鍵仍收推播」是刻意的(晚到推播要有落點),但**沒有時限** ——
一整天內被加進又移出自選的檔,會繼續佔一份 `StockDayState`(最壞 6 MB)並繼續付
每則推播 19–50 µs,直到 TC4 那邊真的停推。

**fix**(要 user 拍板,涉及正確性取捨)
- `_symbol_to_key` 改成「退訂後保留 N 秒」的軟過期(退訂競態窗是秒級,:1197-1199 已寫明);
- 或保留鍵但對「已無 owner」的 code 走 `state.update_book/meta` 早退(不 ingest、不評訊號)。

**risk** :296-299 的註解明說「真正的失效是『訂閱失敗卻留著鍵』」。加過期等於引進一條
新的失效路徑(晚到的權威推播被丟)。**收益(記憶體 + 少量 CPU)可能不值得**,
標為「需要 prod 實測:一天內退訂後仍在推的 symbol 有幾個、推多久」。
**effort** M

---

### F-20 `snapshot()` / `group_snapshot()` 有副作用且**只能在 event loop 上呼叫** —— 擋住把組裝移出 loop

**位置** `copycat/server/stock_engine.py:713-736`(`snapshot`)、:799-856(`group_snapshot`)
**熱路徑** 否(但決定 F-04 / F-09 能做到什麼程度) **category** architecture **severity** medium

```python
def snapshot(self, code: str, *, tape: bool = True) -> dict:
    self._flush_ticks()          # ← publish 副作用 + 動 timer handle
```

docstring 已誠實標註:「副作用 = 可能 publish 一則打包,且**只能在 event loop 上呼叫**」。
這條約束把 F-04 的最大槓桿(把 103 ms 的組裝丟到 `to_thread`)鎖死了。

**fix** 拆成兩步:
```python
def flush_before_snapshot(self) -> None:   # loop only,route 先呼叫
    self._flush_ticks()
def build_group_snapshot(self, codes) -> dict:   # 純讀,可 to_thread
```
route 端:`engine.flush_before_snapshot(); return await asyncio.to_thread(engine.build_group_snapshot, wanted)`。

**risk**
- `_states` 由 loop 獨佔寫入;在 `to_thread` 上讀取會撞到
  「迭代中被 `_acquire` setdefault 新鍵」的 `RuntimeError`(:746-749 與 :1098-1102
  都各自辨識過這條 hazard)。`group_snapshot` 走的是 `for code in codes` 而不是迭代
  `_states`,**這一條剛好安全**;但 `StockDayState` 內部的 `minutes` / `_vp` dict
  會在 to_thread 讀取期間被 loop 上的 `_apply` 改動 → 同款 `RuntimeError`。
  真解是「快照當下先淺拷 dict」或引進 per-state 的寫入世代號。
- CLAUDE.md §4 的「快照與打包的 seq 對齊」兩道閘,loop 上那道(flush)必須保留。
**effort** L

---

## 4. 工具選型與取捨

| 工具 | 用在哪 | 解什麼 / 預期收益 | 代價 | 結論 |
|---|---|---|---|---|
| **`orjson`** | `ws.py::publish` 預序列化、`app.py` group-state / state 的 `ORJSONResponse` | F-04 的 json 段(150 檔 ~60 ms)、F-10 的每 client 重複 dumps。公開 benchmark 2–5×,**本專案未實測** | 第一個 runtime 二進位相依(有 Windows cp313 wheel);`ensure_ascii=False` 是預設、中文名稱行為要驗;`indent` 選項受限 | **建議導入**,但先跑 §6 的量測腳本拿到本專案的真實倍率再決定 |
| **`msgspec`** | 同上 + `parse_stock_realtime` 的 `Struct` 取代 dataclass | 序列化比 orjson 再快一截;`msgspec.Struct` 有 slots 且比 dataclass 省記憶體 | 相依更重;`Struct` 換掉 `StockTick` 會動到 golden fixture 與四處建構點 | **有條件導入**:只當 orjson 實測不夠時才上 |
| **`numpy`** | `StockDayState` 的 tick 欄 | F-06(記憶體 10×)、F-09(zip 展開) | **每次 `.append` 要自己管 ring buffer**;numpy 在 O(1) 逐筆寫入上的 per-call overhead 反而比 stdlib `array` 高;引進整個 BLAS 相依只為存 7 欄整數 | **不建議**(就這個區塊而言)。真正需要 numpy 的是 backtest / 回測聚合,不是即時 tick 存放 |
| **stdlib `array` columnar** | 同上 | F-06 實測 5.44 → 1.12 MB(4.8×),寫入成本持平(0.92 µs vs 0.85 µs) | 要自己寫 ring buffer + 索引;`snapshot` 的展開要重寫 | **建議導入**:零相依、符合 stdlib-only 哲學、收益與 numpy 同量級 |
| **`uvloop`** | event loop | 提升 loop 吞吐 | **Windows 無 wheel、官方不支援** —— 本專案部署綁 Windows(TC4 桌面 app) | **不建議**。替代品 `winloop` 存在但成熟度未驗,且本區塊的瓶頸是**同步 CPU 阻塞**不是 loop 排程,換 loop 救不到 |
| **`cython` / `mypyc`** | `stock_models.parse_stock_realtime` + `stock_state._apply` | 熱路徑 5–20× | 建置鏈上 Windows 編譯器;pyright / 測試路徑要繞;debug 變難 | **不建議**(現階段)。F-01/02/03 的純 Python 修法已能拿到 2.4×,先把便宜的做完 |
| **`polars` / `duckdb` / `pyarrow`** | — | 本區塊零批次分析場景 | — | **不建議**(這裡)。它們的場景在 `backtest/` |
| **`freezegun` 以外的時鐘注入** | `_now_taipei_time` / `_now_taipei_hhmm` | F-01/F-08 的時鐘收斂 | 現況是 monkeypatch 模組屬性(:92-99 docstring 明說「窗與日的時鐘是兩顆」) | **不動**:兩顆時鐘的分離是刻意的,合併的代價已被 `TestObserveClockContract` 釘死 |
| **`cProfile` / `py-spy`** | 量測 | 目前沒有任何 per-tick 延遲儀器 | `py-spy` 需要另一個 process,Windows 可用 | **建議導入 `py-spy`**(唯讀取樣,不改 code,可對 prod server 直接 dump) |

---

## 5. 八個重點問題的直接回答

### Q1 訂閱池怎麼管?150 檔下每 tick 的分派是 dict lookup 還是掃描?

**是 dict lookup,O(1)。** `_handle_quote:1195`:
```python
code = self._symbol_to_key.get(symbol)
```
`_symbol_to_key` 是 TC4 symbol → instrument key 的路由表,在 `_acquire` 中**先寫記帳再訂閱**
(:455-460,因為 TC4 在 SUB 回來後毫秒級就推第一則)。
訂閱池本身 `_refs: dict[str, set[str]]` 是 refcount(owner ∈ `watchlist` / `main` /
`stkfut:<code>`),0→1 真訂、last-out 真退、真訂失敗回滾。
**沒有任何 per-tick 的線性掃描。** 唯一的線性操作是 `code in self._watchlist`(:1347)——
`_watchlist` 是 `list[str]`,150 檔 = 最壞 150 次字串比較 ≈ **1.5 µs / 收下的 tick**。
可改成同步維護的 `frozenset`,但它只在 `ingest` 為真時才跑,收益 < 3%。

### Q2 `_handle_quote` 每次做什麼?`_flush_ticks` 的實作與打包成本?

見 §1.1 的 13 步與 §2 HP-1/HP-4。
`_flush_ticks`(:1782-1797)只做:卸 timer → `items, self._pending_ticks = self._pending_ticks, []`
→ 一次 `_publish`。**打包本體是 O(1) 的 list 換參照,零成本**。
成本在 (a) 每筆成交建一個 9 鍵 dict(:1320-1339,~1 µs)、
(b) 送出端每個 client 各一次 `json.dumps`(300 筆 = 263.9 µs,見 F-10)。
`call_later` 的排程器成本可忽略(閒時零喚醒,首筆到貨才排)。

### Q3 兩段式 rollover 與回補 worker 會不會阻塞 tick 流?

**不會,而且是刻意設計的。** 三個證據:
- `rollover_stage1`(:920-951)同步只做 `_generation += 1` / `_pending_date = new_date` /
  `_trade_status.clear()` / 建 task;**全量重掛與 `set_trade_date` 一起下沉到 `to_thread`**
  (:945-947 + `_resubscribe_all:964-978`)。docstring 明說理由:
  「TC4 半死時 150 檔各等 `_REQ_TIMEOUT_MS`(10 s)= 整條 loop 停擺可達二十餘分鐘」。
- `_rollover_stage2`(:1093-1127)是同步的,但只做 150 次 `state.reset()`(各 O(1),
  ~10 µs 總計)+ 幾個 `clear()`。**快照後迭代**(`list(self._states.values())`)避開
  執行緒競態。
- `_backfill_worker`(:1540-1574)整批取件 → `to_thread(prepare_backfill)` →
  逐檔 `to_thread(source.backfill)` → 回 loop 做 `state.apply_backfill`。
  唯一在 loop 上的同步段是 `apply_backfill` 本身:一檔 6,000 筆重放 ≈ **25 ms**
  (6000 × 4.1 µs;實測 `ingest` 4.11 µs,`apply_backfill` 走同一個 `_apply`)。
  **這是一個被忽略的 loop 阻塞點** —— 開盤 80 檔各補 1–3k 筆,累積 loop 阻塞 0.5–2 s,
  分散在幾十秒內。不緊急,但 columnar 化(F-06)之後會自然改善。

### Q4 `group_snapshot` / `snapshot` 的成本

見 §2 HP-5 / HP-6 與 F-04 / F-05 / F-09。摘要:
- 群組 32 檔(當前最大群組)= **~21 ms loop 阻塞 + 0.97 MB**,每 60 s。
- 群組 150 檔(上限)= **103 ms loop 阻塞 + 4.5 MB**。
- 每檔做的工:`light_snapshot()` 168 µs = 270 個分鐘 dict 重建 + `sorted()` +
  200 個 VP 項的 `str(price)` + `list(cell)`,**其中幾乎沒有一格自上次輪詢以來變過**。
- FastAPI 的序列化層**不是**額外負擔(實測端到端 ≈ 裸 `json.dumps`)。

### Q5 `_pending_ticks` 是什麼結構?

`list[dict]`(:273),每筆 9 個鍵 `{code,t,p,q,side,b,a,h,l,seq}`(:1320-1339)。
0.1 s 窗內以插入序累積(= 到貨序,同檔 `seq` 遞增),flush 時整個 list 換掉。
**逐筆不合併不丟**,打包只降訊息數(開盤每秒數百筆 → ≤10 則/s,per-client queue 1000 撐 100 s)。
收件人 = `_main ∪ _tick_targets`(:1319)。

### Q6 有沒有 per-code 的 state 物件?150 檔各多少記憶體?

有:`_states: dict[str, StockDayState]`(:293),**只增不減**。
實測(tracemalloc,`bench_b04b.py`):

| 每檔 tick 數 | 單檔 | 150 檔 |
|---|---|---|
| 6,000 | 1.90 MB | 0.28 GB |
| 20,000(`_TICKS_MAXLEN`) | 6.18 MB | **0.91 GB** |

組成:`ticks` deque 佔 ~88%(單筆 `StockTick` 278 bytes),`minutes` 270 項、`_vp` 200 項
合計 < 100 KB。另外每檔還散在 13 份平行 dict/set 裡各一個鍵(F-11,量級可忽略)。

### Q7 這個檔 1832 行,職責有幾個?切開對效能有沒有幫助?

**七到八個職責**(見 F-12 清點)。對效能的**直接**幫助 ≈ 0;
**間接**幫助很大 —— `_handle_quote` 是 180 行的單一方法,cProfile 只會給你一行,
切成三段之後才量得出每段佔比;F-07(book coalesce)與 F-10(預序列化)也才有落點。
**但這是 XL effort 的純重構,不該排在 F-01/02/03/08(合計 S effort、2.4× parse 加速)之前。**

### Q8 若要把 per-code state 改成 columnar(預配置 ring buffer),要動哪裡?

**好消息:`StockDayState.ticks` 在 `stock_state.py` 之外零讀者。** 全庫 grep 實查
(`grep -rn "\.ticks\b" copycat/ --include=*.py`)只命中 `live/aggregate.py` 的
另一個同名欄位。`signal_hub` / `signal_policy` 只讀 `state.last` / `state.book` /
`state.meta` / `state.high_milli`(實查 `signal_hub.py:993,996,1022,1058,1104,1105`)。

**要動的點(全部在 `copycat/live/stock_state.py` 內)**:

| 位置 | 現況 | columnar 後 |
|---|---|---|
| :47 `ticks: deque[StockTick]` | 物件陣列 | 7 條 `array('q')` + `head/size` ring 索引 + per-state 常數 `code` / `trade_date` |
| :68 `last` property | `self.ticks[-1]` | 由尾索引重建一個 `StockTick`(對外簽名不變) |
| :74 `reset()` | 換新 deque | ring 索引歸零(**免配置**,rollover 時 150 檔各省一次 20k 配置) |
| :148 `_apply` 首行 `self.ticks.append(tick)` | | 7 次 `array` 寫入 + ring 前進 |
| :123 `survivors = [t for t in self.ticks if t.cum_vol > backfill_max]` | 全掃 | `cum_vol` 欄單調遞增 → **`bisect` O(log n)**(這是隱藏的演算法勝利) |
| :295-307 `snapshot()` 的 tape 展開 | 逐筆 dict | 一次 zip / 手刻 JSON(F-09) |

**時間欄的取捨**:現在 `tick.time` 是 `"HH:MM:SS.fff"` 字串,而它有三個消費者:
`_apply` 的分鐘鍵(`int(t[:2])*60+int(t[3:5])`)、`snapshot` 的 wire `t` 欄、
`_fold_vp` 的窗判定。columnar 後存「當日毫秒整數」,wire 形在 snapshot 時才格式化 ——
**這會把格式化成本從 ingest 搬到 snapshot**,對 20k 筆的全量 tape 反而變慢。
折衷:存毫秒整數 + 對 tape 展開做批次格式化(`divmod` + f-string,~0.5 µs/筆)。

**硬約束(CLAUDE.md §4,必須逐字守住)**
- 「**個股 `seq` 的兩個口徑**」:`snapshot.seq` = `ticks` 尾筆序號;`tick.seq` 每收下一筆 +1。
  ring buffer 的索引**不可**拿來當 `seq`(它會繞回)。`seq` 必須維持獨立的單調計數器。
- 「**快照與打包的 seq 對齊**」:`apply_backfill` 的 `seq = old_seq + max(len(ticks),1) + 1000`
  跳增語意不變。
- `ticks` 的六個 wire 鍵名 `{t,p,q,side,b,a}` 不變(`stock-accum.ts::fromSnapshot` 由
  `snap.seq` 由尾回推 React key)。
- `_TICKS_MAXLEN = 20_000` 的截斷語意不變(前端折的 VP 是不截斷的全量 —— `_vp` 逐 tick
  增量維護,**不受 ring 截斷影響**,這條在 :62-64 已寫明,columnar 後仍成立)。
- `apply_backfill` 的「兩個迴圈去重不對稱」(:125-128)是刻意保留的現況,
  改寫時逐字搬,不要「順手對齊」——那是行為改動。

**前置**:F-11(13 份平行 dict 收成 per-code slot)不是硬前置,但沒有它,
「一檔的記憶體有多少」永遠答不精確。

---

## 6. 量測方法(要證明這個區塊快或慢,怎麼量)

### 6.1 離線微量測(已建立,可直接重跑)

```powershell
cd C:\side-project\copycat
$env:PYTHONUTF8=1
.venv\Scripts\python.exe <scratchpad>\arch-scan\bench_b04.py    # snapshot / group / 記憶體
.venv\Scripts\python.exe <scratchpad>\arch-scan\bench_b04b.py   # 時鐘 / tracemalloc / group 規模曲線
.venv\Scripts\python.exe <scratchpad>\arch-scan\bench_b04c.py   # _handle_quote 全路徑
.venv\Scripts\python.exe <scratchpad>\arch-scan\bench_b04d.py   # FastAPI 序列化開銷
.venv\Scripts\python.exe <scratchpad>\arch-scan\bench_b04e.py   # parse 拆解
```
**任何 F-01/02/03/05 的改動,重跑 `bench_b04e.py` + `bench_b04c.py` 即可拿到前後對照數字。**

### 6.2 event loop 阻塞探針(建議加,現況完全沒有)

現況零儀器:`WsBroadcaster.dropped` 只回答「有沒有丟包」,不回答「loop 卡了多久」。
建議在 `app.py` lifespan 加一支常駐 task(可用 `TXO_LOOP_LAG=1` 開關,prod 預設關):
```python
async def _loop_lag_probe():
    tgt = 0.05
    while True:
        t0 = time.perf_counter()
        await asyncio.sleep(tgt)
        lag = time.perf_counter() - t0 - tgt
        if lag > 0.05:
            logger.warning("loop-lag %.0f ms", lag * 1000)
```
**判準**:交易日 09:00–13:30 盤後 `grep loop-lag logs/server-*.log`
- 每 60 s 出現一次 20–100 ms 的尖峰 = F-04 的群組輪詢(可直接對時間戳比對)
- 開盤 09:00–09:02 連續尖峰 = `apply_backfill` 在 loop 上重放(Q3 尾段)

### 6.3 per-tick 端到端延遲(現況完全沒有)

在 `stock_source.handle_raw` 記 `time.perf_counter()` 進 quote dict,在 `_flush_ticks`
出口算 `now - t0` 的 p50/p95/p99,每分鐘印一行。
**這是唯一能回答「下實單時我看到的價差幾毫秒」的量測**,而現在沒有。

### 6.4 prod 取樣 profile(唯讀,不改 code)

```powershell
pip install py-spy            # 裝在別的 venv 也行
py-spy dump --pid <server pid>                 # 一次性堆疊
py-spy record -o b04.svg --pid <server pid> -d 120 --subprocesses
```
盤中 09:00–09:02 與 10:30(穩態)各錄 120 s,對照 flame graph 中
`parse_stock_realtime` / `light_snapshot` / `json.dumps` 的佔比,
與 §2 的離線推估對帳。

### 6.5 記憶體

```powershell
py-spy dump --pid <pid>        # 不給記憶體
# 改用:
.venv\Scripts\python.exe -c "import psutil,sys; print(psutil.Process(int(sys.argv[1])).memory_info().rss/1024/1024)" <pid>
```
判準:13:30 收盤後 RSS 應接近 §5 Q6 的推估(80 檔 × 6k tick ≈ 150 MB + 其餘引擎)。
**顯著超出 = `_states` 只增不減累積了退訂檔(F-19)**。

### 6.6 現有可用的 prod 判準(不必新增)

- `grep "佇列滿" logs/server-*.log` 為 0 = per-client queue 沒滿(CLAUDE.md 既有判準)
- `grep "stock backfill" logs/server-*.log` 的筆數分布 = 回補入列次數(對帳 F-16 的重複)
- `grep "backfill done" logs/server-*.log` = 開盤整批 prepare 的耗時

---

## 7. 不要動的地方(同樣有價值)

| 位置 | 為什麼夠快 / 為什麼動了會壞 |
|---|---|
| `_acquire` / `_release` refcount 訂閱池(:450-484) | 分派是 O(1) dict lookup;「先寫記帳再訂閱」是 TC4 毫秒級回推的實證修法,順序不可換 |
| ZMQ REQ 全程 `to_thread`(`_resubscribe_all` / `set_watchlist` / `set_main_contract` / `_retry_round`) | 這是 loop 不被 TC4 半死拖垮的**唯一**防線,且逐項取鎖的等待上界(N111)是拿 Discord token 逾時換來的 |
| 單工 `_backfill_worker` + `prepare_backfill` 批次(:1540-1574) | perf/opening-backfill-parallel 已做過(40 檔 40.7 → 0.87 s),prod log 實證開盤 260 symbols 7 s。改成並行收割會打爆 TC4 的 `_api_lock` |
| `_flush_watchlist_loop` 1 s 節流(:1813-1832) | 80 檔整輪 0.117 ms。零優化空間 |
| `StockDayState._apply` / `_fold_vp`(:147-198) | 全 O(1),4.11 µs/tick。VP 逐 tick 增量維護(不在請求時掃 ticks)已經是正確的架構選擇 |
| `_recompute_tick_targets`(:1779) | 只在 view 變更;數十 µs |
| `stream()` 的自選種子(:1750-1757) | 150 檔 0.21 ms |
| `quotes()` / `policy_quotes()` 走 `_quote_payload`(:760/:792) | 刻意的單一定義(除權息日分母 = `meta.ref_milli`),抽出去收益為零 |
| `StkfutCatalog` 的 lock + prewarm(`stkfut_catalog.py`) | `QUERYALLINSTRUMENT` 1.93 s 已 boot 預熱移出熱路徑 |
| `stkfut_map._product_index` 的 `mtime_ns` 簽章(`stkfut_map.py:138-161`) | 跨 process 作廢的唯一可靠判準;省掉 stat 會讓新上市個股期靜默拒單 |
| `WatchlistService` 的 `_commit`(鎖內)/ `_settle`(鎖外)分割 | X-3 的設計,收斂的是鎖凸出不是自己的等待;改 fire-and-forget 會讓 route 回應時訂閱還沒掛上 |
| `stock_watchlist.normalize` 的 O(n²) | n ≤ 150、每次 PUT 一次、保序去重語意不可動 |
| FastAPI 的 `-> dict` response model | 實測不是負擔(端到端 ≈ 裸 `json.dumps`)。改 `response_model=None` 的收益為零 |

---

## 8. 這個區塊發現的硬約束

1. **CLAUDE.md §4「個股 `seq` 的兩個口徑」** — `snapshot.seq` = ticks 尾筆序號;
   `tick.seq` 每收下一筆 +1。columnar / delta 化都會碰到,前端
   `stock-accum.ts::fromSnapshot`(由尾回推 React key)與 `applyTick` 必須同動。
2. **CLAUDE.md §4「快照與打包的 seq 對齊 = 同一個 race 的兩道閘」** — 後端
   `snapshot()`/`group_snapshot()` 取值前必 `_flush_ticks()`;前端
   `isSeededDuplicate` 是另一道。把組裝移出 loop 時只能拆「flush / 取值」兩步,不可拿掉閘。
3. **CLAUDE.md §4「個股逐筆 = `ticks` 打包訊息,單筆 `tick` 型別已退役」** — item 欄位
   `{code,t,p,q,side,b,a,h,l,seq}` 逐字同名、無 `type`。改欄名 → 前端 `default` 分支靜默丟棄。
4. **CLAUDE.md §4「`/ws/stock` 入站 `view` 訊息」** — `_tick_targets` 是各連線聯集,
   前端每次 `onopen` 重送。任何 `_views` 結構改動要維持「以連線為 token」。
5. **CLAUDE.md §4「自選上限常數多邊同值(150)」** — 第二類讀者是「以檔數 × 單價推理的
   效能預算註解」(`stock_engine` / `watchlist_service` / `stock_state` / `GroupGridView`),
   改任何量級判準都要一併改這些註解。
6. **CLAUDE.md §4「`?tape=0` 字面值 + `tape_omitted`」** — 後端只認字串 `"0"`。
7. **回補與 live 必須是同一把試撮窗尺**(`stock_models.parse_hist_tick` docstring)——
   F-01 的 `_taipei_time` 與 `is_trial_window` 的字串比較格式不可動。
8. **`_handle_quote` 13 步的執行順序**本身是不變式(夜盤早退 → 觀測 → no_data 復原 →
   book/meta → 漲跌停重排 → rollover 快路徑 → stage2 → 首筆點火 → ingest → 轉態補推 →
   book publish → on_book)。每一步移位都對應一個註解裡寫明的靜默失效樣態。
9. **Windows 部署**(TC4 是 Windows 桌面 app,ZMQ 對 localhost)—— `uvloop` 出局;
   任何需要編譯的相依要有 cp313 Windows wheel。
10. **stdlib-only runtime**(`pyproject.toml` `dependencies = []`)—— 引進 orjson 是
    對這條哲學的第一次破例,要 user 明確拍板。stdlib `array` columnar 不破例。
11. **`StockDayState.ticks` 零外部讀者** — 這是本區塊最寶貴的重構空間,不要在
    columnar 化之前把它洩漏出去(例如為了「順手」讓 signal_hub 直接掃 ticks)。

---

## 9. 建議排序(如果只能做三件事)

1. **F-01 + F-03 + F-08**(合計 S effort):parse 28.8 → ~17 µs、`_handle_quote` 純簿
   19.3 → ~14 µs。純機械、可用 `bench_b04e.py` 前後對照、不碰任何跨檔契約。
2. **F-05**(M):`light_snapshot` 168 → ~30 µs,群組輪詢的 loop 阻塞 21 ms → ~8 ms。
   不碰 wire 形,只碰 memo 的作廢點。
3. **F-04 的第 1 階段**(整檔 `unchanged` 的 delta,不做分鐘級)+ **F-07**(book coalesce)。
   兩者都要 user 拍板(前者動 wire 契約、後者動下單決策面的延遲)。

F-06 / F-11 / F-12(columnar + per-code slot + 拆檔)是同一條路上的三段,
**要做就一起排成一個 spec**,不要分批 —— 分批會讓 13 份平行 dict 的清空語意在中途
處於半合併狀態,而那正是最容易產生靜默失效的地方。
