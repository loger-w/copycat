# B06-signals — 訊號引擎(偵測 / 政策 / 推播 / 回填)架構與效能掃描

掃描日期:2026-09-13 · 範圍:`copycat/live/signal_state.py`、`copycat/server/signal_hub.py`、
`copycat/server/signal_policy.py`、`copycat/signal_rules.py`、`copycat/signals_config.py`、
`copycat/server/discord_bot.py`、`copycat/notify.py`(+ 掛點 `copycat/server/stock_engine.py`、
`copycat/server/app.py`、`copycat/server/ws.py`、`copycat/fileio.py`)

本報告所有量測皆以 repo 內 `.venv`(CPython 3.13.13 / Windows 11 / 16 核)實跑,
腳本留在同目錄 `bench_signals.py`(第一版,時鐘漂出盤中窗、數字作廢)與
`bench2.py` / `bench3.py`(正式數字來源)。**未改動 repo 任何檔案、未啟動 server。**

---

## 0. 一句話結論

偵測層的**演算法本身大致正確且便宜**(滑動窗全部用 `deque` 且 amortized O(1)),
但有三件事讓它在熱路徑上付了 **8 倍以上**的不必要代價:

1. `vol_burst` 每 tick 用 `sum()` 重掃整個 300 s 滾動窗 —— 實測 **69.7 µs**(窗長 1501),
   佔「7 顆 detector 一筆 tick 總成本 94.6 µs」的 **74%**,而正確做法是 O(1) 的 running sum。
2. **每條規則各持一顆完整 detector,而一顆 detector 會跑全部六個狀態機** ——
   prod 7 條規則 = 42 個狀態機/tick,其中 35 個**在結構上永遠發不出事件**(`enabled`
   只有自己那一個 kind),純燒 CPU 與記憶體。
3. 整條評估**同步跑在 asyncio event loop 上**(`call_soon_threadsafe` → `_handle_quote` →
   `hub.on_tick`),與 WS 廣播、REST route、TC4 回應共用同一條執行緒。

反過來說:**雙佇列 fanout / 丟最舊背壓 / Discord 節流 / 政策層 / 回填 worker 這幾塊設計
是好的,不要動**(理由見 §6)。訊號量級是 **每日 ~700 列、政策列 ~50 列**,
推播與落檔那一半根本不是瓶頸;瓶頸全部集中在「每 tick / 每簿更新都要跑」的那一段。

---

## 1. 架構地圖

```
TC4 ZMQ listener thread
  └ stock_source → loop.call_soon_threadsafe(_handle_quote, quote)      [stock_engine.py:1150]
                       │  ← 自此全部在 **event loop 單執行緒**上
                       ├ state.ingest(tick)                              [stock_engine.py:1316]
                       │   └ hub.on_tick(code, tick, state)              [stock_engine.py:1352]
                       │        ├ _context(state, tick.cum_vol)          [signal_hub.py:992]
                       │        └ for slot in self._slots.values():      [signal_hub.py:607]  ← N = 規則數
                       │             slot.detector.evaluate(...)         [signal_state.py:292]
                       │                ├ _eval_sweep     (無條件推進)
                       │                ├ window append/trim(無條件)
                       │                ├ _eval_cdp       (basis 為空即早退)
                       │                ├ _eval_surge     (enabled 先檢查 ✔)
                       │                ├ _eval_pullback  (無條件推進)
                       │                ├ _eval_volume    (enabled 先檢查 ✔,但 O(窗長))
                       │                └ _eval_limit_tick(無條件推進)
                       │             _fanout → _emit                     [signal_hub.py:1012]
                       │                ├ self._publish(payload)         → WsBroadcaster.publish(同步)
                       │                ├ _enqueue(row, notify=)         → 兩條有界 asyncio.Queue
                       │                └ (kind==sweep_cluster) _emit_policies
                       │                      ├ resolve_groups           [signal_policy.py:99]
                       │                      ├ peers_fn = engine.policy_quotes(peers)
                       │                      ├ evaluate_policies        [signal_policy.py:126]
                       │                      └ 每命中一條政策 → publish + enqueue
                       └ hub.on_book(code, state)                        [stock_engine.py:1366]
                            ├ _context(state, 0)          ← 同一則 quote 的**第二次**建構
                            └ for slot: evaluate_book(...)               [signal_state.py:334]

背景 worker(皆為 event loop 上的 asyncio.Task):
  _basis_worker        ← _basis_jobs Queue(無界)→ daily_bars(to_thread/TC4)→ compute_cdp → _distribute
  _jsonl_worker        ← _jsonl_queue(maxsize 1000)→ to_thread(_append_jsonl) 每則 open/write/close
  _discord_worker      ← _discord_queue(maxsize 100)→ 相鄰同 (code,time) 合批 → bot / webhook
  _policy_outcome_worker ← 每 30 s 輪詢,每日 13:40 跑 backfill_policy_outcomes
```

### 規則 → detector 的映射(這是效能結構的關鍵)

`signal_rules.rule_config(rule, base)` 把一條規則攤成一份 per-rule `SignalsConfig`,
`SignalHub._make_slot` 為它建**一顆全新的 `SignalDetector`**,`enabled` 恆為
`frozenset({rule["kind"]})`(`signal_hub.py:459-463`)。

prod 現況:`data/signal_rules.json` 是 `_cache_version: 1` 的 4 條規則,
載入時走 `_migrate_v1 → _migrate_v2 → _migrate_v3` 後變成 **7 條**
(cdp_cross / surge_crash / surge_pullback ×2 / vol_burst / limit_lock / sweep_cluster,
實跑 `default_rules()` 驗證過同樣是 7)。`MAX_RULES = 30` 是 REST 可寫的上限。

自選 `data/stock_watchlist.json` = **80 檔**(上限常數 `WATCHLIST_LIMIT = 150`)。

---

## 2. 資料流(三條真相源與它們的節奏)

| 路徑 | 節奏 | 誰在等它 |
|---|---|---|
| WS `publish(payload)` | 訊號產生當下同步送 | 前端 SignalRail / toast;**不受 `notify` 閘影響**(契約) |
| jsonl `data/signals/YYYYMMDD.jsonl` | 有界佇列 → worker → `to_thread` 每則一次 open/write/close | 前端 5 分鐘 baseline 輪詢、離線研究讀者、T+1/T+2 回填 |
| Discord | 有界佇列(100)→ 合批 → 每分鐘 30 則節流 | 人 |

實測量級(`data/signals/`):09-09 = 670 列 / 23 政策列,09-10 = 719 / 38,09-11 = 686 / 49。
檔案大小 265–302 KB。**平均一整個交易日 ~700 列 ≈ 0.04 列/秒。**
`grep -c 佇列滿 logs/server-20260911-0905.log` = **0**(訊號佇列全日零丟)。

→ 推播/落檔這一側**完全沒有壓力**,不需要任何最佳化。所有效能問題都在
「每 tick / 每 quote 都要跑」的偵測層。

---

## 3. 熱路徑逐條(含實測)

### HP-1 `SignalHub.on_tick` — 每筆成交 tick × 規則數

`stock_engine.py:1352`,只對 `code in self._watch`(80 檔)觸發,且掛在 `state.ingest(tick)`
為真的分支內(試撮 / 重複 tick 已短路)。

實測(`bench2.py`,單檔 2330、0.2 s/tick = 5 筆/秒的熱門股節奏、窗長穩態 1501):

```
全 7 顆 detector(prod 形)                   94.64 us/tick  (10,566 tick/s)
   surge window len = 1501  sweep lookback len = 301
  單顆 cdp_cross                          6.27 us/tick
  單顆 surge_crash                        3.87 us/tick
  單顆 surge_pullback                     3.62 us/tick
  單顆 surge_pullback                     3.60 us/tick
  單顆 vol_burst                         66.13 us/tick   ← 74%
  單顆 limit_lock                         4.19 us/tick
  單顆 sweep_cluster                      5.20 us/tick
  單顆 detector / enabled 全開            79.60 us/tick
datetime.now()                             0.349 us
sum(window qty) len=1501                  69.70 us       ← vol_burst 的全部成本
```

窗長會隨該檔 tick 率線性變化(`window_secs 300` × tick 率),所以
`vol_burst` 的每 tick 成本 ≈ **0.046 µs × 窗內筆數**。
`signal_state.py:19` 的實測註解寫「熱門股單日 6.2k tick」→ 全日均 0.38 筆/秒(窗長 ~115,
sum ≈ 5 µs),但開盤五分鐘的爆量段可以輕易到 5–20 筆/秒(窗長 1500–6000,sum 70–280 µs)。
**這是一個隨行情爆量而自我放大的成本**:越忙的時候越慢,正好是最不能慢的時候。

### HP-2 `SignalHub.on_book` — 每筆 quote × 規則數

`stock_engine.py:1366` **無條件**對每一則自選股 quote 呼叫(不判簿是否真的變了)。

```
7 顆 evaluate_book        23.88 us/quote  (41,871 quote/s)
1 顆 evaluate_book         2.94 us
_clock_key(strftime)       2.141 us      ← ×7 = 15.0 us,佔 63%
now.time()                 0.060 us
_mono()                    0.272 us
```

`_clock_key(now)`(`signal_state.py:348`)在 `evaluate_book` 開頭**無條件**計算,
但它只有在真的產生 `limit_open` 事件時才用得到 —— 而 `limit_open` 一天全市場最多幾則。
TC4 REALTIME 的簿更新頻率遠高於成交,所以這一條的總量可能比 HP-1 更大(見 §7 量測計畫)。

### HP-3 `_context()` — 每筆 quote 建 1–2 次

`signal_hub.py:992`。帶成交的 quote 會建**兩次**(`on_tick` 一次、`on_book` 一次),
內容完全相同(除了 `day_volume`)。建一個 10 欄 frozen dataclass + 兩次 `_best_limit_price`。

### HP-4 `_emit` / `_emit_policies` — 每則訊號

~700 次/日。`json.dumps(政策 row)` 實測 **12.56 µs**(28 鍵、含 10 個 peers)。
`_emit_policies` 每命中一條政策建一個 28 鍵 dict + 深拷貝 `peers` / `sweep` / `self`。
**≤50 次/日 → 完全不是問題。**

### HP-5 `_jsonl_worker` — 每則訊號一次 `to_thread` + 一次 open/write/close

`signal_hub.py:1190` + `1412`。~700 次/日。每次 `asyncio.to_thread` 有一次
thread-pool 往返(~50–100 µs),`path.open("a") / write / close` 在 NTFS 上 ~100–300 µs。
總計全日 < 0.3 s。**現況不是問題,但走的是全域共用 executor**(見 F-09)。

### HP-6 `backfill_policy_outcomes` — 每日 13:40 一次

log 實證(`logs/server-20260911-0905.log`):

```
13:40:26,357 T+1/T+2 回填 2026-09-09:回填 23 列(14 檔)
13:40:30,660 T+1/T+2 回填 2026-09-10:回填 38 列(17 檔)
13:40:30,660 T+1/T+2 回填完成:共回填 61 列(掃 5 個日檔,2026-09-04..2026-09-11)
```

全程 ~4.3 s,其中絕大部分是 `_fetch_outcome_bars` 的 `basis_gap_secs = 0.2` sleep
(31 檔 × 0.2 s = 6.2 s 的上界,實際有 cache 命中)。
檔案 265–302 KB / 686 列,`atomic_write_bytes` 整檔覆寫 —— 一天一次,**完全可接受**。
唯一的刺是**逐行 decode + `json.loads` 跑在 event loop 上**(見 F-10)。

### HP-7 `_basis_worker` — 每日開盤前一趟(80 檔 × 0.2 s gap)

序列、每檔之間 `basis_gap_secs 0.2` sleep,80 檔 ≈ 16 s + TC4 日 K 往返。
與 CDP 暖機共用 TC4 `api.lock`(這正是 `_policy_outcome_worker` 刻意不在開盤前起跑的理由,
`signal_hub.py:1254` 的 F-10 拍板)。**設計正確,不要動**。

---

## 4. Findings

### F-01 `vol_burst` 每 tick `sum()` 重掃整個滾動窗(critical,熱路徑)

**位置**:`copycat/live/signal_state.py:658`

```python
window_min = self._cfg.surge_window_secs / 60
window_vol = sum(qty for _ts, _price, qty in window)      # ← 每 tick O(窗長)
ratio = window_vol / (avg_per_min * window_min)
```

`window` 是 `evaluate()` 每 tick append 一筆、從頭剪掉過期筆的 deque
(`signal_state.py:318-323`),窗長 = `surge_window_secs × 該檔 tick 率`。

**實測**:窗長 1501 時 `sum()` = **69.70 µs**,佔整個 7-detector tick 成本 94.64 µs 的 **74%**。
成本 ≈ 0.046 µs × 窗長,而窗長與行情熱度成正比 → **越爆量越慢**。

**影響**:這一段跑在 event loop 上。開盤五分鐘若 10 檔各 10 筆/秒、窗長 3000,
單這一項就是 10 × 10 × 138 µs = **13.8 ms/秒的 loop 佔用**,而同一條 loop 還要送
WS ticks 打包(`tick_flush_secs 0.1`)、回覆 REST、處理 TC4 回應。

**修法**:窗改成 `(deque, running_sum)` 一組,`append` 時 `+= qty`、`popleft` 時 `-= qty`。
`evaluate()` 裡本來就是唯一的 append/popleft 點(`signal_state.py:318-323`),
改動面積 = 一個小 helper class 或一組平行的 `self._window_qty: dict[str, int]`。
O(窗長) → O(1),把這條熱路徑砍掉 74%。

**風險**:`_eval_volume` 的行為必須逐字不變(整數加減,無浮點誤差累積問題 —— `qty` 是 int)。
既有測試 `tests/live/test_signal_state.py` 的 vol_burst 案是第一道門;
**不動任何跨檔契約**(`PARAM_SPECS["vol_burst"]` 值域不變)。

---

### F-02 每條規則跑全部六個狀態機,其中五個永遠發不出事件(high,熱路徑)

**位置**:`copycat/live/signal_state.py:311, 326-331`;`copycat/server/signal_hub.py:459-463, 607`

`SignalHub._make_slot` 給每條規則配一顆 detector,`enabled = frozenset({rule["kind"]})`。
但 `SignalDetector.evaluate` 是這樣寫的:

```python
sweep_events = self._eval_sweep(code, tick, key, mono, enabled)   # 311 — 無條件(含 deque 維護)
...
window = self._window.setdefault(code, deque())                   # 318 — 無條件
window.append((mono, price, tick.qty))
while window and window[0][0] < cutoff: window.popleft()
...
events.extend(self._eval_cdp(...))        # 326 — basis 空即早退 ✔
events.extend(self._eval_surge(...))      # 327 — enabled 先檢查 ✔
events.extend(self._eval_pullback(...))   # 328 — **無條件推進**,enabled 檢查在 615 行
events.extend(self._eval_volume(...))     # 329 — enabled 先檢查 ✔
events.extend(self._eval_limit_tick(...)) # 330 — **無條件推進**,enabled 檢查在 835 行(_limit_event)
```

`_eval_sweep` 的 `enabled` 檢查在 **754 行**,前面已經做完 `tick_secs` 解析、`lookback`
deque append/trim、同毫秒群比對、`round()` 層數計算。
`_eval_pullback` 的 `enabled` 檢查在 **615 行**,前面已經跑完整個波峰/回檔狀態機。
`_eval_limit_tick` 的 latch 轉移在 802/805 行無條件執行。

這個「狀態推進無條件、`enabled` 只 gate 事件產出」的設計本身是**對的**
(design R2:關掉爆拉不影響共用窗的爆量、停用期間 latch 照轉、重開後不補發)——
但那個 `enabled` 指的是**同一顆 detector 內的某個 kind 被關掉**。
在「一規則一 detector」的架構下,`limit_lock` 那顆 detector 的 sweep / pullback 狀態
**在結構上永遠不可能被讀到**,它是純粹的死工。

**量級**:prod 7 條規則 → 42 個狀態機實例/tick,其中 35 個是死工。
實測「單顆 detector / enabled 全開」= 79.60 µs vs「7 顆各開一個 kind」= 94.64 µs ——
也就是說**把七顆合成一顆、六個 kind 全開,比現在還快 16%**,而且省掉 6 份窗。

**記憶體**:`_window` / `_lookback` / `_sweep_group` / `_sweeps` 都是 per-detector per-code。
7 detector × 80 檔 × 窗長(熱門股峰值 1500)× ~144 B/筆(3-tuple + float + 2 int)
= **最壞約 120 MB**,常態(窗長 ~150)約 12 MB。**7 倍於必要值。**

**修法**(架構級,建議走 `codebase-design` 的 deep module):
把 detector 拆成兩層 ——
(a) **per-code 市場狀態**(窗 + running sum + lookback + sweep group + prev + side),
   每 tick 每檔**算一次**;
(b) **per-rule 門檻判定 + cooldown/touch/latch**,吃 (a) 的結果,只做比較。
這同時解掉 F-01(running sum 只維護一份)、F-05(`datetime.now()` 只叫一次)。

**風險 / 契約**:
- 掃單簇的定義被 golden fixture `tests/fixtures/sweep_cluster_golden.json` 釘住
  (`_eval_sweep` 必須與 `expected_prefix` 集合相等)—— 重構後這支必須仍綠。
- 「規則 = 一顆未改動的 detector + per-rule config」是 signal-rules design 的明文設計
  (`signal_rules.py` docstring:「調參數永遠只是換一份 config」)。拆兩層等於**改這個設計決定**,
  要 user 拍板;好處是規則數 N 從線性成本變成近乎零邊際成本(`MAX_RULES 30` 才有意義)。
- 窗長**不同的兩條同 kind 規則**(例:兩條 vol_burst 一條 60 s 一條 300 s)必須各自有窗。
  解法是 per (code, window_secs) 共享一份窗,而不是 per rule —— 現況 7 條規則其實只有
  **兩種窗長**(surge 300 / sweep lookback 60),去重率 7→2。

---

### F-03 整條訊號評估同步跑在 event loop 上(high,架構)

**位置**:`copycat/server/stock_engine.py:1150`

```python
def _on_raw_threadsafe(self, quote: dict) -> None:
    loop = self._loop
    if loop is not None:
        loop.call_soon_threadsafe(self._handle_quote, quote)
```

ZMQ listener thread 把每一則 quote 丟回 loop,`_handle_quote` 在 loop 上同步做完
ingest → ticks 打包 → **訊號評估(HP-1 + HP-2)** → WS publish。
`SignalHubLike` 的 docstring(`stock_engine.py:226`)明文寫「全部同步方法:engine 熱路徑不 await」。

**影響**:訊號層的任何一次變慢(F-01 的爆量自我放大、F-07 的使用者可寫窗長)
會直接轉成 **WS 推播延遲 + REST 尾延遲 + TC4 回應處理延遲**,而且沒有任何隔離。
對「要下實單」的系統,這是一條「非關鍵路徑(訊號)可以拖垮關鍵路徑(報價/下單)」的耦合。

**修法(由輕到重)**:
1. 先把 F-01 / F-02 / F-04 的浪費砍掉(不改架構就能拿 8 倍)。
2. 加**預算保護**:`on_tick` 量測自身耗時,超過門檻(例 2 ms)時 WARNING + 該 tick 跳過非必要 kind。
   現況 hub 只有 `dropped_jsonl` / `dropped_discord` 兩個計數,**沒有任何耗時計量**(見 F-18)。
3. 真要隔離就把偵測層搬到獨立執行緒(訊號層本來就零 IO、狀態自持):
   listener thread → 一條 `queue.Queue` → signal thread → 事件再 `call_soon_threadsafe` 回 loop 發 WS。
   代價是 detector 的 `now_fn` 注入時鐘與 `StockDayState` 的跨執行緒讀取要重新定義
   (`stock_engine.py:1768` 明文「`_handle_quote` 同執行緒讀寫,不需鎖」——這條不變式會破)。

**Windows 硬約束**:`uvloop` **不支援 Windows**(本專案後端 host 必須是 Windows + TC4 常駐),
所以「換一個快的 event loop」這條路在本專案不存在;唯一的路是**把 loop 上的工作變少**。

---

### F-04 `_clock_key` 的 strftime 在每筆簿更新 × 每條規則無條件計算(high,熱路徑)

**位置**:`copycat/live/signal_state.py:142-143, 348`

```python
def _clock_key(now: _dt.datetime) -> str:
    return f"{now:%H:%M:%S}.{now.microsecond // 1000:03d}"
...
def evaluate_book(self, code, ctx, enabled):
    now = self._now_fn()
    if not self._in_session(now): return []
    mono = _mono(now)
    key = _clock_key(now)      # ← 348:無條件,但只有真的發 limit_open 時才用得到
```

**實測**:`_clock_key` = **2.141 µs**(datetime 的 `__format__` 走 strftime);
7 顆 detector → **15.0 µs/quote**,佔 `evaluate_book` 總成本 23.88 µs 的 **63%**。
`limit_open` 事件一天全自選最多個位數則。

**修法**:把 `key` 改成 lazy(只在 `_limit_event` 要建事件時才算),
或由 hub 每則 quote 算一次傳進來(與 F-05 合併一起做)。
零契約風險、零行為改變,`evaluate_book` 成本立刻砍 60%。

---

### F-05 `datetime.now()` / `_mono()` 每條規則各叫一次(medium,熱路徑)

**位置**:`signal_state.py:301, 305`(evaluate)、`345, 347`(evaluate_book)

每顆 detector 自己 `self._now_fn()` + `_mono(now)` + `_in_session(now)`。
7 顆 → 7 × (0.349 + 0.272 + 0.060) = **4.8 µs/tick**,簿路再一份。

同一批 detector 在同一則 quote 內被呼叫,拿到的牆鐘必然只差微秒 ——
**語意上本來就該是同一個時刻**。現況還會產生一個微妙的不一致:七顆 detector 的 cooldown
軸各差幾微秒。

**修法**:`SignalHub.on_tick` / `on_book` 算一次 `now` / `mono` / `key`,經參數傳進
`evaluate(..., now=, mono=, key=)`。`now_fn` 注入契約保留(hub 持有那顆時鐘)。
**注意**:`SignalDetector` 的 `now_fn` 參數是測試與盤後重放的注入點
(`signal_hub.py:457` 明文「漏帶 `now_fn` 的那一顆會偷用真實時鐘」),簽名改動要一起改
`_make_slot` 與所有 detector 單元測試。

---

### F-06 `_context()` 對帶成交的 quote 建兩次(medium,熱路徑)

**位置**:`copycat/server/stock_engine.py:1352` 與 `1366`;建構點 `signal_hub.py:992`

```python
if tick is not None and state.ingest(tick):
    ...
    self._signal_hub.on_tick(code, tick, state)      # 內部 _context(state, tick.cum_vol)
...
if self._signal_hub is not None and self._pending_date is None:
    self._signal_hub.on_book(code, state)            # 內部 _context(state, 0)
```

兩次建構除了 `day_volume` 完全相同:讀同一份 `state.book` / `state.meta`,
各跑兩次 `_best_limit_price`。另外 `on_book` **完全不判簿有沒有變**——
只帶成交、簿沒動的 quote 照樣跑 7 顆 `evaluate_book`。

**修法**:
(a) hub 內把 `_context` 結果按 (code, state.seq/book identity) 記一拍;或
(b) engine 側只在 `book` 真的變動時才呼 `on_book`(需要 `StockDayState` 提供
    「這則 quote 有沒有動到簿」的旗標 —— `_apply` 已經有 `recovered` / `was_meta_none`
    這類轉態旗標,加一個同款的成本很低)。
(b) 比較徹底:它同時砍掉 F-04 的 7 × strftime。
**風險**:`limit_open` 的偵測靠的正是「尾盤解鎖無成交也抓得到」(design §3.5b),
所以旗標必須把「賣側限價檔由空變有」算成簿變動 —— 這是行為契約,要紅先行釘住。

---

### F-07 `MAX_RULES 30` × `window_secs ≤ 3600` = REST 可寫的 event-loop 預算炸彈(medium)

**位置**:`copycat/signal_rules.py:54, 73-79`

```python
MAX_RULES = 30
PARAM_SPECS = {
  ...
  "vol_burst": {"ratio": (1,100), "window_secs": (10, 3600), ...},
}
```

`signal_rules.py:53` 的註解自己講對了一半:「REST 可寫入的無界量要有上限(R11)——
熱路徑是 per-tick N × evaluate」。但**只擋了規則數,沒擋單條規則的成本**。

把 `vol_burst.window_secs` 調到 3600,窗長 = 3600 × tick 率;熱門股 5 筆/秒 → 18,000 筆,
F-01 的 `sum()` = 18000 × 0.046 = **828 µs/tick/規則**。
30 條這樣的規則 → **25 ms/tick**。這是一個從 UI 規則視窗就按得出來的 loop stall。

**修法**:F-01 的 running sum 直接讓這個問題消失(O(1) 與窗長無關)。
若不做 F-01,就得在 `PARAM_SPECS` 收窄 `vol_burst.window_secs` 上界 ——
**那是跨檔契約**:`tests/fixtures/signal_param_specs.json` golden + 前端
`frontend/src/lib/signal-params.ts::PARAM_FIELDS` 的 min/max 必須同動
(CLAUDE.md §4「訊號規則參數契約前後端同表」)。
**建議走 F-01,不要動契約。**

---

### F-08 jsonl 每則一次 `open/write/close` + 一次 `to_thread`(medium)

**位置**:`copycat/server/signal_hub.py:1186-1196, 1412-1419`

```python
async def _jsonl_worker(self):
    while True:
        row = await self._jsonl_queue.get()
        await asyncio.to_thread(self._append_jsonl, row)   # 每則一次 thread 往返
...
def _append_jsonl(self, row):
    path.parent.mkdir(parents=True, exist_ok=True)         # 每則一次 mkdir syscall
    with path.open("a", encoding="utf-8") as fh:           # 每則一次 open/close
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
```

**現況量級 ~700 列/日 → 完全不痛**(全日 < 0.3 s)。列出來是因為它是「要做量化系統」
時第一個會爆的地方:規則數或自選檔數放大 10 倍,或加上 tick 級記帳,
每則一次 open/write/close 在 NTFS 上是 100–300 µs、而且**佔用共用 executor 的一格**。

**修法**(只在真的放大時做):worker 改成「drain 佇列拿 N 則 → 一次 `to_thread` 寫 N 行」,
並把 `mkdir` 移到換日時做一次。
**風險**:`close()` 的 `join()` 零漏語意與 `_flush_pending` 的保底必須一起改;
`_append_jsonl` 寫的是 CRLF(`open("a", encoding=...)` 預設 newline 翻譯),
而回填的 byte 比對測試 `tests/server/test_signal_outcome.py` 依賴這件事 —— **行尾不可變**。

---

### F-09 全域共用 default executor:訊號落檔與 TC4 殭屍執行緒同池(medium,架構)

**位置**:全庫 66 處 `asyncio.to_thread`(`stock_engine` 15 / `index_engine` 8 /
`signal_hub` 7 / `futures_engine` 6 / …),**零處**設定自訂 executor
(`grep set_default_executor|ThreadPoolExecutor` = 無命中)。
本機 16 核 → 預設 `max_workers = min(32, 16+4) = 20`。

`app.py:1570` 自己已經寫下這條教訓:
> `to_thread` 走 loop 預設 executor,與 daily_bars / capital close 同池且工作執行緒不可中斷
> —— TC4 半死的殭屍執行緒堆積時這條會跟著排隊(review C-1);today 若變慢先查同池鄰居。

訊號這邊的具體暴露面:
- `_jsonl_worker` 的每則落檔(F-08)
- `_send_text` → `asyncio.to_thread(self._notify_fallback, text)`(`signal_hub.py:1563`)
  → `notify.py::notify_discord`,內含 `urlopen(timeout=5.0)` **和 429 時的
  `sleep(min(delay, 5.0))`**(`notify.py:105`)→ 單則最壞**佔用一格 pool thread 10 秒**。
- `today_signals`(REST,5 分鐘輪詢 × 每個開著的分頁)

**修法**:給「序列且不可中斷」的工作各自一條專屬 executor
(`concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="signal-jsonl")`,
`loop.run_in_executor(ex, ...)`)。零新相依、零契約。
TC4 那一池另外分,是 B0x 其他區塊的事,但訊號這邊先自保。

---

### F-10 回填的逐行 decode + `json.loads` 跑在 event loop 上(medium)

**位置**:`copycat/server/signal_hub.py:1317-1338`

```python
raw = await asyncio.to_thread(path.read_bytes)      # ← 讀檔 off-loop ✔
lines = raw.splitlines(keepends=True)               # ← 以下全在 loop 上
for i, line_bytes in enumerate(lines):
    line = line_bytes.decode("utf-8")
    row = _policy_row_needing_outcome(line)         # json.loads 每一行
```

讀檔與寫檔都 `to_thread` 了,**中間的解析沒有**。
5 個日檔 × 686 行 = 3,430 次 decode + `json.loads`(~5–10 µs/行)≈ **20–35 ms 的 loop 阻塞**,
外加 `json.dumps` 61 列 + `b"".join(lines)`。

一天一次、13:40(盤後)→ 嚴重度低,但它是「該 off-load 卻沒 off-load」的教科書案例:
同一個函式裡三段 IO 有兩段丟了執行緒、中間那段 CPU 最重的反而留在 loop 上。

**修法**:把「讀 → 解析 → 找出 targets」整段包成一個同步函式丟 `to_thread`,
回來只拿 `targets`(TC4 取數必須留在 loop 上,那是 async)。

---

### F-11 `read_signals` 每次全檔重讀重解(low-medium)

**位置**:`copycat/server/signal_hub.py:1448-1482`,經 `today_signals` 給
`GET /api/stock/signals/today`(`app.py:1581`,已 `to_thread`)。
前端 `useSignalFeed.ts` 帶 `refetchInterval = 5 分鐘`。

每次 = `read_text` 300 KB + `splitlines` + 686 次 `json.loads`(~10 ms 的 pool thread)。
一天 ~54 次 × 開著的分頁數。

**修法**:hub 內保留一份 `(path, mtime, size, rows)` 快取,只讀 **尾端新增的位元組**
(append-only 檔,offset 增量讀)。壞行跳過語意不變。
**注意**:`today_signals` 的「同日走單檔讀、不去重」語意必須逐字保留
(重啟後重發同一事件會有同 id 兩列,是刻意的)。

---

### F-12 `json.dumps` / `send_json` 是全庫唯一序列化路徑(medium,工具選型 + **契約地雷**)

實測 `json.dumps(政策 row)` = **12.56 µs**;`orjson` 典型快 3–6 倍。
WS 側 `ws.py:196/265` 走 Starlette `send_json` = 每個 client 各 `json.dumps` 一次
(8 條 WS → 同一則訊號序列化 8 次)。

**但 jsonl 寫入這一側絕對不能換 orjson**,理由是三條硬契約:
1. CLAUDE.md §1 的影子期判準逐字寫著
   `grep '"kind": "policy"' data/signals/<YYYYMMDD>.jsonl` —— 帶**空白**的 `": "`。
   `orjson.dumps` 不輸出空白(`{"kind":"policy"}`),這條 grep 判準會靜默失效。
2. CLAUDE.md §4「T+1/T+2 回填原地補欄 + 離線讀者契約」:
   「回填改成整檔 dumps → 舊列鍵序 / 浮點字面變動,對帳 diff 整檔紅;
   `tests/server/test_signal_outcome.py` **byte 比對**釘住」。
3. 研究目錄的離線讀者逐列讀 `s["kind"]`(W1 契約)。

**建議**:`orjson` 只用在**讀**(`read_signals` / 回填解析,`orjson.loads` 對空白不敏感)
與 **WS 送出**(改成 hub/ws 層自己序列化一次、多 client 共用同一份 bytes)。
**不碰 jsonl 寫入**。

---

### F-13 `tick_secs(key)` 每 tick 重複解析 7 次(low,熱路徑)

**位置**:`signal_state.py:167-176`,由 `_eval_sweep` 每顆 detector 各呼一次。
實測 0.340 µs × 7 = **2.4 µs/tick**。與 F-05 同一個解法(hub 算一次傳下去);
F-02 的拆層做完後自然消失。

---

### F-14 `set_basis` / `drop_code` 以 dict comprehension 重建整表(low)

**位置**:`signal_state.py:222-223`(`set_basis`)、`280-284`(`drop_code`)

```python
self._side = {k: v for k, v in self._side.items() if k[0] != code}
```

每次 `set_basis` 都 O(全表)。盤前 basis sweep 對 80 檔各呼一次
(`_distribute` → 每條 cdp 規則 `set_basis`),`_side` 最大 80×5 = 400 筆
→ 80 × 400 = 32k 次比較,**一天一次、< 10 ms**。
150 檔上限下是 150 × 750 = 112k,仍 < 50 ms。
**列出來只為記帳:這是 O(N²) 但 N 有上限 150 → 不要動。**
真要改就把 `_side` / `_cooldown` / `_touch` / `_latch` 改成兩層 dict(`code → {level: ...}`),
但那動的是四個資料結構,收益 < 10 ms/日,不值得。

---

### F-15 `policy_quotes` 對每個同伴呼 `_quote_payload` 只為了拿一個 `chg_pct`(low)

**位置**:`copycat/server/stock_engine.py:792`

```python
chg_pct=self._quote_payload(code)["chg_pct"],
```

`_quote_payload` 建一個完整的 `watchlist_quote` dict(8+ 欄)再丟掉 7 欄。
族群最大 32 檔 → 每顆掃單簇事件 32 個多餘 dict。
**只在掃單簇事件時觸發(~50 次/日)→ 不要動**;但它顯示一個模式:
「唯一算式」的收斂是靠「呼叫整個 builder」達成的,而不是抽出算式本身。
若日後把政策層拉到 tick 級,這裡要先抽一個 `_chg_pct(code) -> float | None`。

---

### F-16 hub 零耗時計量(medium,可觀測性 —— 量化系統的前提)

`SignalHub` 對外只有 `dropped_jsonl` / `dropped_discord` / `dropped`
(`signal_hub.py:416-421`),`/api/health` 刻意不含 ws `window_dropped`。
**沒有任何**「這一 tick 的訊號評估花了多久」「每秒評估幾次」「哪條規則最貴」的數字。

要把系統改成「專注高效能、下實單」,第一步不是換套件,是讓「慢」看得見:
- `on_tick` / `on_book` 的耗時 histogram(p50/p95/p99,per-rule 分桶)
- 每秒 evaluate 次數、窗長分佈
- 兩條佇列的 high-water mark(現在只有丟棄計數,丟之前的水位看不到)

**修法**:純 stdlib 就做得到(`time.perf_counter_ns()` + 固定桶陣列 + 每分鐘一行 INFO,
或掛 `/api/health` 的一個 `signals` 區塊)。零相依、零契約。
這是 §7 量測計畫能真的跑起來的前提。

---

### F-17 `_in_session` 硬編 09:00–13:30(low-medium,架構)

**位置**:`signal_state.py:63-64, 366-367`

```python
_SESSION_START = _dt.time(9, 0)
_SESSION_END = _dt.time(13, 30)   # end-exclusive
def _in_session(self, now): return _SESSION_START <= now.time() < _SESSION_END
```

現貨窗寫死在偵測層。要把訊號擴到期貨 / 個股期(日盤 08:45–13:45、夜盤 15:00–05:00)
就得改這裡,而 `_in_session` 是**第一道 gate**(不在窗內連狀態都不推進)。
若量化系統要涵蓋期貨,session 必須變成注入參數(與 `stock_models.TRIAL_WINDOWS`
「窗是參數」的既有慣例一致)。

---

### F-18 Discord bot 與主 server 共用同一個 event loop(low,已正確處理)

**位置**:`discord_bot.py:487`

```python
self._task = asyncio.create_task(self.client.start(self._token))
```

discord.py 的 client 跑在**主 server 的同一條 event loop** 上。
理論上 discord.py 的 gateway 心跳 / HTTP 都是 async,不會阻塞;
`send_signal` 是 `await channel.send(text)`,若 Discord 端慢,
**卡住的是 `_discord_worker` 這條 task,不是 `on_tick`** —— 這正是雙佇列設計要保護的東西,
而它保護到了(佇列滿丟最舊、熱路徑零反壓)。

唯一的實際暴露是 fallback 路徑:`_send_text` 的
`await asyncio.to_thread(self._notify_fallback, text)` 同步 urlopen(見 F-09)。
**Discord 這一側的設計正確,不要動。**

---

### F-19 `_basis_jobs` 是唯一的無界佇列(low)

**位置**:`signal_hub.py:394` `self._basis_jobs: asyncio.Queue[tuple[str,str,bool]] = asyncio.Queue()`

其他兩條佇列都有界(1000 / 100),這條沒有。
現實上它的生產者是 `request_basis(codes)`(自選變動 / 換日),上界 = 自選檔數 × 2(當日 + staged)
+ 有限重試(`_BASIS_MAX_RETRIES = 2`),所以**不會真的爆**。
記帳用:若日後有人加一條「定時全量重抓基準」的路徑,這裡就沒有保護。

---

### F-20 不要引 numpy / pandas 進 tick 熱路徑(反向 finding)

訊號偵測是**每筆一個標量、分支很重、狀態跨 tick 累積**的工作。
`numpy` 的 per-call overhead(~1–5 µs)比整個 `_eval_surge`(3.87 µs)還高;
`pandas` 的 DataFrame 在這裡完全沒有立足點。
`numba` / `Cython` 也不建議:狀態機是 dict/deque 為主的物件圖,JIT 沒得發揮,
而 Windows 上的編譯鏈是長期維護負擔,且與本專案 `dependencies = []` 的 stdlib-only 哲學衝突。

**真正的加速來源在 §4 F-01/F-02/F-04/F-05:把重複與 O(n) 拿掉,純 Python 就有 8 倍。**
(94.6 µs → 估算 ~12 µs;`bench2.py` 的「單顆 detector / enabled 全開 = 79.6 µs」扣掉
F-01 的 69.7 µs sum 就是 ~10 µs 的實測支撐。)

離線那一側(`backtest/` / 研究 / 回填對帳)是另一回事 —— 那裡 numpy/polars 完全合理,
但不在本區塊範圍。

---

## 5. 工具選型與取捨

| 工具 | 用在哪 | 解什麼 | 代價 / 風險 | 建議 |
|---|---|---|---|---|
| **(無新套件)running sum** | `signal_state.py:658` | F-01,砍掉 74% 的 tick 成本 | 零 | **先做這個** |
| **(無新套件)detector 拆兩層** | `signal_state.py` / `signal_hub._make_slot` | F-02,7× 死工 + 7× 記憶體 | 改 signal-rules design 決定;sweep golden fixture 要仍綠 | 建議(要 user 拍板) |
| **(無新套件)專屬 ThreadPoolExecutor** | `signal_hub` jsonl / notify | F-09,與 TC4 殭屍同池 | 零相依;關機序列要一起收 | 建議導入 |
| **(無新套件)耗時 histogram** | `signal_hub` | F-16,讓「慢」看得見 | 零 | **建議導入(前提)** |
| `orjson` | `read_signals` 解析、回填解析、WS 序列化 | 3–6× 解析 / 序列化 | **不可用於 jsonl 寫入**(空白 / 浮點字面 / byte 比對三條契約,見 F-12);單一 wheel,Windows 有 | 有條件導入(只讀 + WS) |
| `msgspec` | payload struct 化 + 快速編碼 | 型別安全 + 比 orjson 再快一點 | 會動到 `dict` payload 形狀的所有消費點;wire 欄名逐字契約多(政策列形狀 / notify 欄)| 不建議(現階段收益 < 風險) |
| `uvloop` | — | — | **不支援 Windows**,本專案後端必須 Windows | 不可用 |
| `numpy` / `pandas` / `polars` | tick 熱路徑 | — | per-call overhead > 整條判定 | **不建議**(見 F-20) |
| `numba` / `Cython` / Rust(pyo3) | detector | 理論 10–50× | Windows 編譯鏈、與 stdlib-only 哲學衝突;80 檔 × 7 規則遠未到需要它的量級 | 不建議(過度工程) |
| `aiofiles` | jsonl 落檔 | — | 它底層還是 thread pool,等於現況;批次寫才是解 | 不建議 |
| `httpx` | `notify.py` webhook | async、免佔 pool thread | 新 runtime 相依;但 webhook 是 fallback、一天幾十則 | 有條件(若順便統一全庫 21 處 urllib 才划算) |

---

## 6. 不要動的地方(這些已經對了)

1. **雙佇列 fanout + 丟最舊背壓**(`signal_hub.py:1167-1184, 1673-1687`):
   jsonl(1000)與 Discord(100)兩條獨立有界佇列、`_put_drop_oldest` 不 `await put`、
   熱路徑零反壓、丟棄有計數與節流 log。實證全日零丟(`grep -c 佇列滿` = 0)。
   **這是本區塊設計最好的一段,不要碰。**
2. **`_discord_worker` 的單槽 `_discord_pending` 合批**:不回塞佇列(避免順序亂)、
   `task_done()` 恰一次的記帳。一則寫錯就是關機吊死或 worker 猝死,改動風險遠大於收益。
3. **掃單簇的滑動窗實作**(`signal_state.py:718-748`):
   `lookback` / `sweeps` 都是 `deque` + 單向剪裁,amortized O(1),
   而且 `lookback` 刻意保留「窗前最後一筆」當漲幅基準(`while len(lookback) >= 2 and lookback[1][0] <= cutoff`)
   —— 這是正確且省的寫法,**不是**每次重掃 list。實測單顆 5.20 µs/tick。
   另有 golden fixture 釘定義,改動風險高、收益低。
4. **CDP 基準 worker 的 0.2 s 逐檔 gap + 有限重試 + 日別尺**(`signal_hub.py:821-970`):
   它是為了不搶 TC4 `api.lock` 而**刻意慢**的,不是效能缺陷。
5. **回填的「只重寫被補的列、其餘 byte 逐字保留」**(`signal_hub.py:1327-1381`):
   看起來很囉嗦,但那是離線讀者契約 + byte 比對測試釘住的。
   任何「整檔 `json.dumps` 重寫」的簡化都會直接違約。
6. **`signal_policy.py` 全部**:純函式、零 IO、O(同伴數)、一天跑 ~50 次。零最佳化空間也零必要。
7. **`_emit_policies` 的 28 鍵 dict 與深拷貝**:≤50 次/日。
8. **`discord_bot.py` 的 lazy import / 降級三態 / autocomplete 1 s 逾時**:
   與熱路徑無關,設計正確。
9. **`notify.py` 的 never-raise / 429 重試**:語意正確;唯一的刺是它佔用共用 pool thread(F-09),
   解法在 executor 分池而不是改 `notify.py`。

---

## 7. 量測方法(要證明快 / 慢,該怎麼量)

### 7.1 離線微量測(已跑,可重跑)

```
cd C:\side-project\copycat
PYTHONUTF8=1 .venv\Scripts\python.exe <scratchpad>\arch-scan\bench2.py   # tick 路徑
PYTHONUTF8=1 .venv\Scripts\python.exe <scratchpad>\arch-scan\bench3.py   # 簿路 + 元件成本
```

`bench2.py` 的關鍵細節(第一版 `bench_signals.py` 就是踩在這上面):
注入時鐘必須**每筆 tick 一個值、所有 detector 共用**,不能「每次呼叫 now_fn 就前進」——
後者會讓牆鐘漂出 `_in_session` 的 09:00–13:30 窗,`evaluate` 第一行就早退,
量到的全是早退路徑(第一版那組 1 µs/tick 的數字全部作廢)。

### 7.2 線上 profile(盤中,不改行為)

現況**沒有**任何線上計量(F-16),所以要先加最小探針:

```python
# signal_hub.on_tick 開頭 / 結尾(改動 3 行,純記帳)
t0 = time.perf_counter_ns()
...
self._tick_ns_hist[min((time.perf_counter_ns()-t0)//10_000, 63)] += 1   # 10 µs 一桶
```
每分鐘一行 INFO 印 p50/p95/p99 + 評估次數,盤後 `grep` 對照。
判準:**p99 < 200 µs、每秒評估次數 × p50 < 10 ms/s**(loop 佔用 < 1%)。

### 7.3 端到端(不進 prod)

- 起 `python -m copycat.server --verify`(fake source、不碰 ZMQ、port 8722),
  用 `tests/` 既有的 fake tick harness 灌 N 筆/秒,量 `/api/health` 的
  WS 推播延遲與 `dropped`。**不要在 prod server 上做**(CLAUDE.md ops-discipline)。
- 窗長敏感度:同一份 tick 流分別以 `vol_burst.window_secs` = 60 / 300 / 1800 / 3600 跑,
  畫出「每 tick 成本 vs 窗長」的線 —— 修完 F-01 之後這條線應該是**水平的**,
  這就是 F-01 修對了的機驗判準。

### 7.4 記憶體

```python
# 盤中(側車 server)量 detector 的窗總量
sum(len(w) for slot in hub._slots.values() for w in slot.detector._window.values())
```
F-02 修完之後這個數字應該除以 7(或除以「不同窗長的種類數」)。

### 7.5 回填(每日 13:40)

`grep "T+1/T+2 回填" logs/server-*.log` 已有現成的耗時對照
(09-11 實測 13:40:26 → 13:40:30 共 61 列 / 5 個日檔 / 4.3 s)。
修 F-10 之後這一段的**事件 loop 阻塞**要另外量(`loop.slow_callback_duration` 或探針)。

---

## 8. 這個區塊碰到的硬約束(改動時要一起處理)

1. **訊號規則參數契約前後端同表**(CLAUDE.md §4):`signal_rules.PARAM_SPECS` /
   `INT_PARAM_KEYS` / `COOLDOWN_MIN/MAX` ↔ 前端 `frontend/src/lib/signal-params.ts`,
   以 `tests/fixtures/signal_param_specs.json` 雙向釘住。**收窄任何值域 = 改契約要同時改兩邊 + fixture。**
2. **掃單簇定義 golden fixture** `tests/fixtures/sweep_cluster_golden.json`:
   線上 `_eval_sweep` 必須與 `expected_prefix` 集合相等。任何 `_eval_sweep` 的最佳化都要過這支。
3. **政策列形狀契約**:`kind="policy"` + `policy ∈ {P,B-a,B-b,S}` +
   id `<日>-<規則id>-<代號>-policy-<標記>-<時刻鍵>`;前端 `signal-model.ts` 逐字對齊。
4. **`notify` 欄契約**:產生點 `_emit` / `_emit_policies`;缺欄前端視為 true。
5. **T+1/T+2 回填原地補欄 + 離線讀者契約(W1)**:不新增列型、每列 `kind` 恆在、
   只加欄不改欄、被補的列只換 JSON 本體、行尾原樣、整檔 `atomic_write_bytes`;
   `tests/server/test_signal_outcome.py` **byte 比對**。
   → **jsonl 的序列化器與行尾不可換**(直接排除 orjson 寫入、排除 `\n` 統一)。
6. **影子期 grep 判準**(CLAUDE.md §1 表):`grep '"kind": "policy"' data/signals/<日>.jsonl`
   帶空白 —— 依賴 `json.dumps` 的預設 separators。
7. **族群 = 自選群組扣「盤前篩選」與 `policy_exclude_groups`**:
   `resolve_groups` 讀 `screen_engine.SCREEN_GROUP`(前後端同字面)。
8. **Windows**:`uvloop` 不可用;NTFS 的 open/close 成本較高;
   TC4 必須同機常駐(後端 host 不能換 Linux)。
9. **stdlib-only runtime**(`pyproject.toml` `dependencies = []`):
   任何新 runtime 相依都是哲學層決定,要 user 拍板。

---

## 9. 開放問題(查不出來,要 user 或要跑 profile)

1. **TC4 REALTIME 的簿更新頻率是多少?** `on_book` 是無條件每 quote × 7 detector,
   若簿更新是成交的 5–10 倍,F-04 的 15 µs/quote 浪費會比 F-01 還大。
   現有 log 沒有 quote 計數,要加探針才知道。
2. **開盤五分鐘的實際 tick 峰值?** 本報告的「5 筆/秒/檔」是從
   `_TICKS_MAXLEN` 註解的「熱門股單日 6.2k」外推的上界,不是實測峰值。
3. **F-02 的拆層要不要做?** 它會改掉 signal-rules design 的核心決定
   (「一規則一顆未改動的 detector」),收益是 7× → 1×(規則數的邊際成本趨零)。
   這是方向性抉擇,要 user 拍板。
4. **系統要不要擴到期貨 / 夜盤訊號?** 會的話 F-17 的 session 參數化要先做。
5. **要不要引入任何 runtime 相依?** 若答案是「維持 stdlib-only」,
   那 orjson 這條就整條劃掉,而 §4 的前五條(F-01/02/03/04/05)本來就不需要新套件。
6. **`notify.py` 的 webhook 還在用嗎?**(bot 是主路,webhook 是 fallback)
   若已經不靠它,F-09 的 10 秒佔用風險就可以直接降級。
