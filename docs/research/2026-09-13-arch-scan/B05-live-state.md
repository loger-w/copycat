# B05-live-state —— 即時狀態機:每 tick 的計算核心

分析日期:2026-09-13 ／ 分析對象:`C:/side-project/copycat` master
量測環境:Windows 11、Python 3.13.13(`.venv`)、本機同一台(與 prod 同機)
量測腳本(scratchpad,未進 repo):
`bench_b05.py` / `bench_signal.py` / `bench_parse.py` / `bench_payload.py` / `bench_corr.py`

---

## 0. 一句話結論(先講反直覺的那個)

**這個區塊的「純計算」不是瓶頸,而且 numpy / numba 幾乎完全用不上。**
實測 `StockDayState.ingest` = **1.96 µs/tick**,300 tick/s 全開也只佔 **0.06% 的一顆核**。
把它換成 numpy 只會**變慢**(per-tick 純量運算,ndarray 的建構成本遠大於幾次 int 加法)。

真正會「塞住」的是三件事,而且它們的共同點是 **全部跑在唯一那條 asyncio event loop thread 上、而且是一次一大坨**:

| 事件 | 實測成本 | 頻率 | 後果 |
|---|---|---|---|
| `group_snapshot(150 檔)` + JSON 序列化 | **33 ms 構建 + 51 ms dumps = 84 ms** | 每 60 s(開著群組檢視時) | loop 整整停 84 ms,期間 ~25 則 tick 排隊 |
| `SignalDetector._eval_volume` 的 `sum(window)` | **58 µs/tick**(窗 1500 筆);base 只有 6 µs | 每成交 tick × 每條 vol_burst 規則 | 活躍股每 tick 多花 10 倍 |
| `CorrState.correlations` | **14.4 ms/次** | 每 1 s | 每秒固定停 14 ms;且 module docstring 寫的「不到 1 ms」是**錯的** |

其次是**每則 REALTIME 訊息**的 `parse_stock_realtime` = **24.9 µs**,跑在 loop thread 上(不是 ZMQ listener thread)。

穩態總帳(300 msg/s、150 檔自選、4 條規則):約 **25–36 ms/s ≈ 2.5–3.6% 一顆核**。
→ **CPU 沒有飽和。問題是尖峰延遲(latency spike),不是吞吐量。**
這對「要下實單」的系統很關鍵:84 ms 的 loop 停頓意味著那段時間**任何下單 route、任何 WS 推播、任何 tick 消化都不會動**。

---

## 1. 架構地圖

### 1.1 模組分工

```
ZMQ listener thread(每個 TC4 session 一條)
  └─ tc4.TC4QuoteSource._listen_loop   sock.recv() → json.loads → _realtime_msg
       └─ _note_push(symbol, quote)            # 自癒記帳:4 鍵指紋 tuple,每則都建
       └─ <subclass>.handle_raw
            └─ StockQuoteSource: _seen.add(symbol) → _on_message(quote)
                 └─ stock_engine._on_raw_threadsafe
                      └─ loop.call_soon_threadsafe(_handle_quote, quote)   ← 跨執行緒
────────────────────────────────────────────────────────────────────
event loop thread(唯一一條;同時服務 HTTP / WS / 下單 route)
  └─ stock_engine._handle_quote(quote)
       ├─ parse_stock_realtime(quote)              24.9 µs   ← 每則都跑
       ├─ _observe_trade_status                     ~1 µs
       ├─ state.update_book / update_meta           ~0 µs(賦值)
       ├─ state.ingest(tick)                        1.96 µs  ← 只有成交才走
       │    └─ _apply → _fold_vp
       ├─ _pending_ticks.append({...})              ~0.5 µs  ← 每 0.1 s flush 成一則
       ├─ signal_hub.on_tick(code, tick, state)
       │    ├─ _context(state, cum_vol)             ~2 µs(TickContext frozen dataclass)
       │    └─ for slot in 4 slots: detector.evaluate(...)
       │         活躍股:3 × 6.3 + 58.3 = 77 µs      ← 本區塊最大的每 tick 成本
       └─ signal_hub.on_book(code, state)
            └─ for slot in 4 slots: evaluate_book(...)  ~4–8 µs
```

### 1.2 純狀態機(零 IO)一覽

| 檔案 | 角色 | 狀態容器 | 每 tick 複雜度 |
|---|---|---|---|
| `live/stock_state.py` | 個股當日狀態機 | `deque(maxlen=20000)` + `minutes: dict[int, MinuteAgg]` + `_vp: dict[int, list[int]]` | **O(1)** ✅ |
| `live/stock_models.py` | REALTIME/TICKS → dataclass | frozen dataclass ×3 | O(5) 五檔 × 2 側 |
| `live/signal_state.py` | 六類訊號偵測 | 13 個 dict + 3 個 deque(每 slot 一份) | **O(窗長)** ❌ 只有 `_eval_volume` |
| `live/corr_state.py` | 滾動 Pearson | `dict[str, deque[(ts, mid)]]` | push O(1) ✅ / read **O(腿×樣本)** ❌ |
| `live/river_state.py` | 江波圖分鐘序列 | `dict[str, dict[int, int]]` | O(1) ✅ |
| `live/aggregate.py` | TXO 逐檔累積 | `dict[str, _PosState]` | O(1) ✅ |
| `live/payoff.py` | 到期損益曲線 | 無狀態純函式 | O(履約價²) 但只在 snapshot |
| `live/handover.py` | 交接 buffer | `list[Tick]` cap 200k | O(1) append ✅ |
| `live/trade_models.py` | 下單欄位對映 | 無狀態 | 下單時才跑,離線級 |

---

## 2. 熱路徑逐條(附實測)

### HP-1 `_handle_quote` → `parse_stock_realtime`(每則 REALTIME 訊息)

頻率:**最高**。含純簿更新(`TradeQuantity=0`),實務上遠多於成交筆數。
CLAUDE.md §4 記「50 檔開盤每秒數百筆」逐筆成交 → 加上簿更新估 500–1500 訊息/s。

實測 **24.9 µs/則**。cProfile 拆解(20000 次):

```
_parse_levels       0.442 s cum (36%)   ← 2 次呼叫 × 5 檔 × (to_milli + _to_int)
_taipei_time        0.379 s cum (31%)   ← 其中 _strptime 0.223 s = 18%
to_milli_units      0.193 s tot (16%)   ← 15 次/則
_to_int             0.047 s (13 次/則)
```

關鍵事實:**`Decimal` 不是兇手**。`to_milli_units` 實測 **0.41 µs**,我手刻的純 `str`/`int` 版是 **0.39 µs** —— 只快 5%,完全不值得為此動一條有「截斷 vs banker's rounding」註記的契約函式(`tc4common.py:16`)。

真兇是 `stock_models.py:93` 的 `strptime`:

```python
def _taipei_time(precise_utc: str, date_utc: str) -> tuple[str, str]:
    s = precise_utc.zfill(12)
    hh, mm, ss, frac = int(s[:2]), int(s[2:4]), int(s[4:6]), s[6:9]
    base = _dt.datetime.strptime(date_utc, "%Y%m%d")     # ← 每 tick 一次,18% 的成本
    local = base + _dt.timedelta(hours=hh, minutes=mm, seconds=ss) + _TAIPEI_OFFSET
    return f"{local:%H:%M:%S}.{frac}", f"{local:%Y-%m-%d}"
```

`date_utc` 一天只有 1–2 個值(跨 UTC 午夜),卻每則重新 parse 一次格式字串。

### HP-2 `StockDayState.ingest`(每成交 tick)

實測 **1.96 µs/tick**(6000 tick 全日 = 11.8 ms 總計)。逐行拆解:

```python
def ingest(self, tick):                       # stock_state.py:87
    if tick.is_trial: return False            # 1 屬性讀
    if tick.cum_vol <= self._last_cum: return False
    self._last_cum = tick.cum_vol
    self._apply(tick)
    self.seq += 1
    return True

def _apply(self, tick):                       # stock_state.py:147
    self.ticks.append(tick)                   # deque append,O(1),滿了自動丟最舊
    # high/low:2 次比較 + 最多 2 次賦值             ← 已是增量,無 O(n) 重算
    self._amount_milli += tick.price_milli * tick.qty
    self._volume += tick.qty
    self.vwap_milli = round(self._amount_milli / self._volume)   ← 已是增量 ✅
    minute_key = int(tick.time[:2]) * 60 + int(tick.time[3:5])   ← 2 次 slice + 2 次 int
    agg = self.minutes.setdefault(minute_key, MinuteAgg())       ← 1 次 dict 查 + (每分鐘一次)建構
    agg.close_milli / high / low / volume / (outer|inner|unch)   ← 6 次屬性寫
    self._fold_vp(tick, minute_key)                              ← 1 次 dict setdefault + 2 次 list 寫
```

**配置次數統計(穩態,非該分鐘首筆、非該檔位首見)**:
- `MinuteAgg()` 建構:每分鐘 1 次(全日 270 次)→ 攤到 tick 上 ≈ 0
- `list [0,0,0]`(VP cell):每個成交過的檔位 1 次(實測全日 117 個)→ 攤到 tick ≈ 0
- 其餘:**零物件配置**,只有 int 加法與 dict 查找。

→ **這段程式碼寫得很好,沒有任何可以撿的東西。** 唯一的 float 運算是 VWAP 的除法,已經是增量式。

**記憶體才是它的成本**:tracemalloc 實測 **365 B/tick 常駐**(含 `StockTick` 物件 200 B + `time` 字串 + deque slot)。
- 150 檔 × 6000 tick = **328 MB**
- 最壞(deque 滿 20k)150 × 20000 = **1.1 GB**

### HP-3 `SignalDetector.evaluate`(每成交 tick × 每條規則)

prod 現況 `data/signal_rules.json` = **4 條規則**(cdp_cross / surge_crash / vol_burst / limit_lock),
`signal_hub.on_tick` 對每條 slot 各呼叫一次 `evaluate`(`signal_hub.py:607`)。

實測(窗 1500 筆 = 5 tick/s 的活躍股,`surge_window_secs=300`):

| enabled 集合 | µs/tick |
|---|---|
| `frozenset()`(全關,只推狀態) | **6.28** |
| `{cdp_cross}` | 6.48 |
| `{limit_lock}` | 5.86 |
| `{vol_burst}` | **58.33** ← |

**窗密度 vs 成本(這是一條漂亮的直線,證明 O(n)):**

| tick 間隔 | 窗內筆數 | µs/tick |
|---|---|---|
| 5.0 s | 61 | 0.59 |
| 1.0 s | 301 | 19.89 |
| 0.5 s | 601 | 29.82 |
| 0.2 s | 1501 | **67.74** |
| 0.1 s | 3000 | **136.76** |

cProfile 指名兇手(`signal_state.py:658`):

```
ncalls   tottime  cumtime  function
  3000    0.317    0.596   {built-in method builtins.sum}          ← 87% of evaluate
4506000   0.279    0.279   signal_state.py:658(<genexpr>)
```

```python
window_vol = sum(qty for _ts, _price, qty in window)   # signal_state.py:658
```

`window` 是 `deque[(mono, price, qty)]`,長度 = 300 秒內的 tick 數。**每 tick 重新加總整個窗。**

prod 每 tick 總成本 = 3 × 6.3 + 58.3 = **77 µs**(活躍股)/ 3 × 2 + 20 = **26 µs**(1 tick/s 的一般股)。

**誠實的補充**:`_eval_volume` 在 `elapsed_min < vol_min_elapsed_min`(15 分)時會**先 return**,所以 09:00–09:15 那段最忙的開盤是免費的。成本從 09:15 才開始。

### HP-4 `signal_hub.on_book`(每則 REALTIME,含純簿更新)

```python
def on_book(self, code, state):               # signal_hub.py:617
    if code not in self._watch: return
    ctx = self._context(state, 0)             # 每則建一個 TickContext frozen dataclass
    for slot in self._slots.values():         # 4 次
        events = list(slot.detector.evaluate_book(code, ctx, slot.enabled))
```

`evaluate_book` 內部只跑兩個方向的 latch 檢查,很便宜(~1 µs),但 `_context` + `list()` + 4 次迴圈 ≈ **4–8 µs/則**,而它對**每則簿更新**都跑。

### HP-5 `group_snapshot`(每 60 s × 開著群組檢視的每個瀏覽器分頁)

`app.py:1707` `stock_group_state` 是 `async def`,**整段跑在 event loop 上**,而且 Starlette 的 `JSONResponse` 也在同一個 task 裡序列化。

實測(150 檔 × 各 270 分鐘 × 117 個 VP 檔位,= CLAUDE.md 記的上限情境):

```
group_snapshot 150 檔 light_snapshot 構建     32.82 ms
json.dumps(150 檔 group payload)             51.07 ms   size = 3218 KB
```

→ **一次請求 ≈ 84 ms 的 loop 停頓 + 3.2 MB payload**。
60 檔的盤前篩選群組約 34 ms / 1.3 MB。

成本結構:`light_snapshot()` 實測 **122 µs**,其中絕大部分是 `_minutes_payload()`:

```python
return {
    str(k): {"c":…, "v":…, "i":…, "o":…, "u":…, "h":…, "l":…}
    for k, m in sorted(self.minutes.items())      # stock_state.py:218
}
```
每次呼叫重新 `sorted()` 270 筆 + 建 270 個新 dict + 270 個 `str(k)`。這 270 個分鐘裡,**只有最後一個會再變**。

### HP-6 `snapshot(tape=True)`(開圖 / seq 跳號 refetch / 重連)

```
snapshot(tape=True)  6000 ticks     1.35 ms   + json.dumps  6.19 ms   (467 KB)
snapshot(tape=True)  20000 ticks    7.98 ms   + json.dumps 16.62 ms  (1512 KB)
snapshot(tape=False) 6000 ticks     0.094 ms
```

`tape=False` 的優化(CLAUDE.md §4 `tape=0` 契約)**非常有效**:1.35 ms → 0.094 ms,14 倍。已經做對了。
但 `tape=True` 在下午的熱門股是 **25 ms 的 loop 停頓**。

### HP-7 `CorrState.correlations`(每 1 s)

實測 **14.43 ms/次**(11 腿、1800 樣本窗)。`push` 只要 2.66 µs(正確地做成增量)。

模組 docstring(`corr_state.py:6`)寫:
> 「`statistics.correlation`(stdlib,內部用 fsum)對 1800 樣本實測 0.15 ms,整輪 tick 外推不到 1 ms。」

**這個宣稱與實測差 14 倍**,因為成本根本不在 `statistics.correlation`。cProfile:

```
ncalls   tottime  cumtime  function
   300    0.477    0.912   corr_state.py:82(_paired_returns)     ← 83%
1079400   0.171    0.270   corr_models.py:31(log_return)         ← 每秒 18,000 次 math.log
   900    0.036    0.078   statistics.py:1311(correlation)       ← 只有 7%
```

`_paired_returns(leg, now)` 每次呼叫:
1. `leg_by_ts = dict(leg_series)` —— 重建 1800 筆的 dict
2. 掃過整個 base series 1800 次,對每組配對呼叫 2 次 `log_return`(= `math.log`)
3. 回傳前再 filter 一次
接著 `correlations()` 對 3 個窗各做一次 list comprehension over paired(× 2:xs 和 ys)。

10 腿 × (1800 dict 建 + 1800 掃 + 3600 log + 6 × 1800 filter)= **每秒 ~10 萬次迴圈**,而其中只有**最新那 1 筆**是新的。

### HP-8 `ChainAggregator` / `payoff`(TXO)

```
ChainAggregator.snapshot(8 檔活躍,實務態)      13.66 µs
ChainAggregator.snapshot(120 檔全活,極端)     141.97 µs
```
`snapshots()` 節流 `throttle_secs = 1.0`(`engine.py:70`),每個 WS consumer 每秒最多一次。
`curve_points` 是 O(履約價 × 網格)= O(n²),但 n = 實際有部位的合約數,實務上個位數。

→ **完全不是問題。** 就算 120 檔全活也只有 142 µs/秒。

---

## 3. Findings

### B05-01 `_eval_volume` 每 tick 重算整個 300 秒窗的總量 —— O(n) 可改 O(1)

- **位置**:`copycat/live/signal_state.py:658`
- **熱路徑**:是。每成交 tick × 每條 `vol_burst` 規則(prod 現有 1 條)
- **證據**:
  ```python
  window_min = self._cfg.surge_window_secs / 60
  window_vol = sum(qty for _ts, _price, qty in window)    # ← 658
  ratio = window_vol / (avg_per_min * window_min)
  ```
  cProfile:`sum` + genexpr 佔 `evaluate` 總 tottime 的 **87%**。
  實測 `enabled={vol_burst}` 58.33 µs/tick vs `enabled=frozenset()` 6.28 µs/tick(窗 1501 筆)。
  線性:窗 301 → 19.9 µs、窗 3000 → 136.8 µs。
- **影響**:活躍股每 tick 多 **52 µs**。150 檔 × 2 tick/s = 300 tick/s 的話,單這一行就是 **15.6 ms/s ≈ 1.6% 一顆核**,而且全部集中在 event loop thread。開盤後 09:15 起生效(15 分鐘的 `vol_min_elapsed_min` 之前免費)。
- **修法**:在 `evaluate()` 維護窗的同一處(`signal_state.py:318-323`)順便維護一個 `self._window_qty[code]`:append 時 `+= qty`、popleft 時 `-= qty`;`_eval_volume` 直接讀。
  ```python
  window.append((mono, price, tick.qty))
  self._window_qty[code] = self._window_qty.get(code, 0) + tick.qty
  cutoff = mono - self._cfg.surge_window_secs
  while window and window[0][0] < cutoff:
      self._window_qty[code] -= window.popleft()[2]
  ```
  `reset_day` / `drop_code` 要一起清(那兩支已經有 `_window` 的清除,照抄)。
- **風險**:零 wire 契約影響。唯一風險是增量和整批不等 —— 用突變測試 + 一條 property test(隨機 tick 序列跑完後 `_window_qty == sum(qty for window)`)釘住即可。註:這是 int 累加不是 float,不會有 `corr_state` docstring 擔心的浮點累積誤差。
- **工作量**:S

### B05-02 `group_snapshot` + JSON 序列化 = 84 ms 的 event loop 停頓

- **位置**:`copycat/server/app.py:1735-1736`(route)、`copycat/server/stock_engine.py:838-856`、`copycat/live/stock_state.py:237-264`
- **熱路徑**:每 60 s,但**單次成本是全系統最大的一次停頓**
- **證據**:
  ```python
  # app.py:1707
  @app.get("/api/stock/group-state")
  async def stock_group_state(request: Request, codes: str = "") -> dict:
      ...
      return {"states": stock.group_snapshot(wanted)}     # ← 同步,150 檔全展開
  ```
  實測:構建 32.82 ms + `json.dumps` 51.07 ms = **83.9 ms**,payload **3218 KB**。
- **影響**:那 84 ms 內 event loop **完全不動** —— tick 不消化(`call_soon_threadsafe` 排隊)、WS 不推、**下單 route 不回應**。以 300 tick/s 算,一次請求會積壓 ~25 則 tick。多分頁同時輪詢就是倍數。
  這是整個 B05 區塊裡對「要下實單」傷害最大的一條。
- **修法(三段,依成本效益排序)**:
  1. **換 JSON 編碼器**:`orjson.dumps` 對這種純 int/str 的巢狀 dict 實測業界普遍 **3–8×**;51 ms → 估 7–15 ms。在 `live` extra 加 `orjson`,FastAPI 用 `ORJSONResponse` 或自訂 `default_response_class`。⚠ `orjson` 不接受非 str 的 dict key —— `_minutes_payload` 已經 `str(k)`、`_vp` 也已經 `str(price)`,**現況剛好相容**(這是幸運,不是設計)。
  2. **分鐘增量 wire**:270 個分鐘裡只有最後一個會變。改成 `?since=<minute_key>` 只送新分鐘。這會**動到跨檔契約**(見 §6)。
  3. **構建分批讓路**:`for` 每 20 檔 `await asyncio.sleep(0)`,把 33 ms 切成 8 段。
  **不要做的事**:`asyncio.to_thread(group_snapshot)` —— stdlib `json` 的 C encoder **不釋放 GIL**,orjson 也不釋放,丟到執行緒**完全不會**減少 loop 停頓,只會多一次 context switch。
- **風險**:(1) 只換編碼器 → 風險極低,但 `orjson` 對 `float('nan')` / `Decimal` 行為與 stdlib 不同,要先確認 payload 內沒有(本 payload 全是 int/str/None,安全)。(2) 增量 wire → 動契約,見 §6。
- **工作量**:編碼器 S / 分批 S / 增量 wire L

### B05-03 `CorrState.correlations` 每秒重算 18,000 次 `math.log`,且 docstring 的效能宣稱是錯的

- **位置**:`copycat/live/corr_state.py:82-126`;錯誤宣稱在 `corr_state.py:6`
- **熱路徑**:每 1 s(`corr_engine` 每秒推播)
- **證據**:
  ```python
  def _paired_returns(self, leg: str, now: float):
      ...
      leg_by_ts = dict(leg_series)               # ← 每次重建 1800 筆 dict
      for ts, base_mid in base_series:           # ← 每次掃 1800 筆
          ...
          rb = log_return(prev_base, base_mid)   # ← math.log ×2,每秒 18,000 次
  ```
  cProfile:`_paired_returns` 佔 83%,`statistics.correlation` 只佔 7%。實測 **14.43 ms/次**。
  docstring 寫「整輪 tick 外推不到 1 ms」—— 差 14 倍。
- **影響**:每秒固定 14.4 ms 的 loop 停頓(1.4% 一顆核)。腿數增加或窗拉長是線性惡化;若把 `_DEFAULT_WINDOWS` 的 1800 拉到 3600,直接變 29 ms/s。
- **修法**:把 paired returns 也做成增量 —— 維護 `self._paired: dict[str, deque[(ts, rb, rl)]]`,`push()` 時只計算「最新這一筆與前一筆」的報酬並 append、同時按 `now - max_window` 逐出。`correlations()` 只剩「按窗切片 + `statistics.correlation`」= 估 **< 1 ms**(這才是 docstring 想講的那個數字)。
  docstring 說的「整批重算讓浮點一致性恆真」這個論點**不受影響**:增量的是**報酬序列**(每筆各自獨立由兩個中價算出,不是累加量),`statistics.correlation` 仍然吃整批。要順手把那段 docstring 的數字改對。
- **風險**:中。`_paired_returns` 有「跨洞不接合」的語意(`abs((ts-prev_ts) - sample_secs) <= tol`),增量版要逐條對齊;`push` 的換場清空要同步清 `_paired`。用既有測試 + 一條「增量 == 整批」的 property test 釘住。
- **工作量**:M

### B05-04 每則 REALTIME 的 `strptime` —— 一天只有 1–2 個日期值卻每則重 parse

- **位置**:`copycat/live/stock_models.py:93`
- **熱路徑**:是。每則帶成交的 REALTIME + 每筆回補 tick(`parse_hist_tick` 走同一支)
- **證據**:
  ```python
  base = _dt.datetime.strptime(date_utc, "%Y%m%d")     # stock_models.py:93
  ```
  cProfile(20000 次 `parse_stock_realtime`):`_strptime` cumtime 0.223 s / 總 1.230 s = **18%**;`_taipei_time` 整支 31%。
- **影響**:24.9 µs/則裡約 4.5 µs。1000 訊息/s → 4.5 ms/s。單獨看不大,但它是「一行改動換 18%」的性價比之王。回補路徑更明顯:一次回補 6000 筆 = 27 ms 純 strptime。
- **修法**:`@functools.lru_cache(maxsize=8)` 包一支 `_base_date(date_utc) -> datetime`,或直接手刻 `datetime(int(s[:4]), int(s[4:6]), int(s[6:8]))`(後者更快且無快取狀態)。
  進一步:整支 `_taipei_time` 可以改成純整數算術 —— UTC+8 對 `HHMMSS` 只是「+8 小時、進位則日期 +1」,`_dt.datetime` 與 `timedelta` 的建構(2 個物件/tick)完全可以省掉。但那會動到「跨 UTC 午夜」的邊界語意,要小心。
- **風險**:低(lru_cache 版本);中(全手刻版本 —— 跨日邊界是 `tc4-market-facts` 的實測語意)。
- **工作量**:S(cache)/ M(手刻)

### B05-05 四條規則 = 四份重複的狀態機,每 tick 各推進一次同樣的東西

- **位置**:`copycat/server/signal_hub.py:607`、`signal_state.py:292-332`
- **熱路徑**:是
- **證據**:
  ```python
  for slot in self._slots.values():                      # signal_hub.py:607,prod 4 個 slot
      events = list(slot.detector.evaluate(code, tick, ctx, slot.enabled))
  ```
  每個 `_RuleSlot` 持有**自己的 `SignalDetector`**(`signal_hub.py:455 _make_slot`),因此 `_prev` / `_window` / `_lookback` / `_sweep_group` / `_side` / `_suppressed` 各有 4 份,而且每 tick 都被推進 4 次。
  這是刻意的設計(`signal_state.py` docstring:「狀態推進與事件產出分離」,design R2 —— 停用期間狀態照走)。但代價是 **base 6.28 µs × 4 = 25 µs/tick**,即使 3 個 slot 什麼都不會發。
- **影響**:25 µs/tick 的純重複工;加規則是線性惡化(user 可以從 UI 新增規則!10 條規則 = 63 µs/tick 純重複)。記憶體同理:每檔每規則一個 300 秒窗 deque,150 檔 × 4 規則 × 1500 筆 tuple ≈ 90 萬個 tuple。
- **修法**:把「市場狀態推進」(窗、prev、side、lookback、sweep group)抽成 **per-code 共用一份**的 `MarketWindow`,detector 只留「判定 + cooldown + touch 計數」這些**真正 per-rule** 的東西。這正是 `codebase-design` 的 deep module / seam 問題:目前的 seam 切在「規則」,應該切在「狀態 vs 判定」。
- **風險**:高。這是本區塊唯一的架構級改動,會動到 `signal_state.py` 的全部測試與 `tests/fixtures/sweep_cluster_golden.json` 的 golden parity(§6)。**建議排在 B05-01 / B05-02 之後**,而且要有量測證明規則數會長。
- **工作量**:L

### B05-06 `_minutes_payload` 每次重建 270 個 dict + 重排序

- **位置**:`copycat/live/stock_state.py:200-219`
- **熱路徑**:每次 `snapshot()` 或 `light_snapshot()`(群組 batch 150 次/60 s、單檔 refetch)
- **證據**:
  ```python
  return {
      str(k): {"c": m.close_milli, "v": …, "i": …, "o": …, "u": …, "h": …, "l": …}
      for k, m in sorted(self.minutes.items())       # stock_state.py:218
  }
  ```
  `light_snapshot()` 實測 122 µs,其中這一支是主體(`snapshot(tape=False)` 94 µs 也幾乎全是它)。
- **影響**:群組 batch 的 33 ms 構建幾乎全在這裡。
- **修法**:兩條路。(a) 快取 payload 並以 `self.seq` 當失效鍵 —— 但活躍股每 tick 都動,幫助有限;(b) **只快取「已收盤的分鐘」**:過去的分鐘永遠不會再變,把它們的 dict 存下來、只重建最後一個分鐘。實作上是在 `_apply` 偵測到 `minute_key` 前進時,把上一分鐘 freeze 進一個 `list` 裡。
  真正一勞永逸的是 B05-02 的 (2) 增量 wire。
- **風險**:低(純內部);但要注意 `apply_backfill` 的 `reset()` 要清快取,漏了就是「回補後分鐘序列停在舊值」的靜默錯值。
- **工作量**:M

### B05-07 `StockTick` frozen dataclass 無 slots —— 365 B/tick 的常駐記憶體

- **位置**:`copycat/live/stock_models.py:46-61`、`stock_state.py:47`
- **熱路徑**:建構在熱路徑(每 tick 1 個);記憶體是長期累積
- **證據**:
  ```python
  @dataclass(frozen=True)          # ← 沒有 slots=True
  class StockTick:
      code: str; price_milli: int; qty: int; cum_vol: int; time: str
      trade_date: str; side: str; is_trial: bool
      bid_milli: int | None = None; ask_milli: int | None = None
  ```
  實測(同欄位的對照組):
  | 形態 | 建構 | 實例大小 |
  |---|---|---|
  | `frozen=True`(現況) | 1.054 µs | 48 + `__dict__` 152 = **200 B** |
  | `frozen=True, slots=True` | 0.975 µs | **112 B** |
  | 一般 dataclass | 0.256 µs | — |

  tracemalloc 實測整條鏈:**365 B/tick 常駐**(含 `time` 字串)。
  150 檔 × 6000 tick = **328 MB**;deque 滿(20k)的最壞 = **1.1 GB**。
- **影響**:記憶體。`_TICKS_MAXLEN = 20_000` × 150 檔是設計上允許的,實務上長跑一整天的 server 會吃掉數百 MB。另外 frozen 的 `object.__setattr__` 讓建構比一般 dataclass 慢 4 倍(1.05 vs 0.26 µs)—— 但 frozen 是刻意的不可變語意,**不建議為了 0.8 µs 放棄它**。
  對照:`SignalsConfig` 已經用了 `@dataclass(frozen=True, slots=True)`(`signals_config.py:20`),所以 repo 裡已有這個慣例,`StockTick` 只是漏掉。
- **修法**:
  1. `StockTick` / `StockBook` / `StockMeta` / `Tick` / `OptionContract` 加 `slots=True` —— 200 B → 112 B,**零行為改動**。⚠ 唯一要查的是有沒有人對它們 `setattr` 動態欄位或用 `__dict__`(grep 過:`relabel_locked_side` 用 `dataclasses.replace`,那支對 slots dataclass 正常運作)。
  2. `trade_date` / `side` / `code` 三個字串每 tick 都是同一批值 → `sys.intern` 或在 parse 層用查表回傳共用物件,省掉每 tick 的字串物件。
  3. 更激進:`ticks` deque 改 columnar(`array('i')` × 4 + 一個 `array('I')` 存毫秒時刻),tape 的 JSON 也可以直接從 array 組。~30 B/tick。但 `apply_backfill` 的 survivors 過濾與 `last` property 要重寫。
- **風險**:(1) 極低;(2) 低;(3) 中高 —— 動到 `apply_backfill` 的「兩個迴圈去重不對稱」那段刻意保留的語意。
- **工作量**:(1) XS /(2) S /(3) L

### B05-08 `snapshot(tape=True)` 對熱門股是 25 ms 停頓

- **位置**:`copycat/live/stock_state.py:295-307`、`app.py:1699`
- **熱路徑**:開圖 / seq 跳號 refetch / 重連 / rollover
- **證據**:
  ```python
  "ticks": [
      {"t": t.time, "p": t.price_milli, "q": t.qty, "side": t.side, "b": t.bid_milli, "a": t.ask_milli}
      for t in self.ticks                      # ← 6000–20000 筆,每筆一個新 dict
  ] if tape else [],
  ```
  實測:6000 筆 = 1.35 ms 構建 + 6.19 ms dumps(467 KB);20000 筆 = 7.98 ms + 16.62 ms(1512 KB)。
- **影響**:單次 25 ms loop 停頓。頻率低(不是每秒),但 CLAUDE.md §4 記「seq 跳號 → 全量 refetch」,而跳號在丟包 / rollover / 重連時會發生,恰好是系統最忙的時候。
- **修法**:(a) `orjson`(同 B05-02);(b) tape 改送 **array-of-arrays** 而非 array-of-objects(`[t,p,q,side,b,a]`),payload 縮 ~45%、dumps 快 ~2×;(c) `?since_seq=` 增量 tape。(b)(c) 都動契約(§6)。
- **風險**:(a) 低;(b)(c) 動 `frontend/src/lib/stock-accum.ts::fromSnapshot`(那支靠「由尾回推 seq」指派 React key,見 CLAUDE.md §4「個股 `seq` 的兩個口徑」)。
- **工作量**:(a) S /(b) M /(c) L

### B05-09 `_note_push` 每則訊息建一個 4 元素 tuple + 兩次 dict 寫(listener thread)

- **位置**:`copycat/live/tc4.py:780-812`
- **熱路徑**:是,每則 REALTIME(在 listener thread,不佔 loop)
- **證據**:
  ```python
  fp = tuple(str(quote.get(k, "")) for k in _PUSH_FP_KEYS)   # tc4.py:799,4 鍵
  prev_fp = self._push_fp.get(symbol)
  self._push_fp[symbol] = fp
  attempts = self._heal_attempts.get(symbol)
  if attempts is None: return                                # ← 絕大多數走這條
  ```
- **影響**:~1.5 µs/則,但它在 **listener thread**(不阻塞 loop),而且早退很快。**這不是問題**,列出來是為了說明我查過了。
  真正值得注意的是**架構**:`_listen_loop` 對每個 TC4 session 都 `SUBSCRIBE ""`(`tc4.py:1242`),而 `models.py:16` 的註解明說「TXO runtime 的 ZMQ SUB 訂 `""`,會收到同 process 其他引擎的訂閱推播」——
  **也就是 5 條 session 的 listener thread 各自 `json.loads` 了全部 5 條 session 的訊息**。這是 5× 的 JSON decode 浪費,但它散在 5 條 thread 上、不佔 loop,所以在本區塊列為「知情但不動」。歸屬 B04(tc4/source)。
- **修法**:不動。
- **工作量**:—

### B05-10 `stock_source.handle_raw` 把**所有** symbol 都丟過 thread 邊界進 loop

- **位置**:`copycat/live/stock_source.py:925-934` → `stock_engine.py:1147-1150` → `stock_engine.py:1195-1200`
- **熱路徑**:是
- **證據**:
  ```python
  # stock_source.py:925
  def handle_raw(self, raw: str) -> None:
      msg = self._realtime_msg(raw); ...
      if self._on_message is not None:
          self._on_message(quote)           # ← 不管 symbol 是不是這條 session 訂的
  # stock_engine.py:1195
  code = self._symbol_to_key.get(symbol)
  if code is None:
      logger.debug("未對映的推播 symbol=%s(訂閱池外,丟棄)", symbol)
      return                                # ← 到了 loop 才丟掉
  ```
- **影響**:每則「不是我的」訊息都付一次 `call_soon_threadsafe`(要拿 loop 的鎖 + 寫 callback queue + `write` 到 self-pipe 喚醒 loop)+ 一次 loop callback 排程。這在 loop thread 上是純浪費。量級取決於 cross-talk 比例(TC4 廣播全部的話,可能是多數訊息)—— **這個比例我量不到,需要真環境 grep**(見 §8)。
- **修法**:把 `_symbol_to_key` 的查表**下沉到 listener thread**(`handle_raw` 裡先判,不是我的就 return)。`_symbol_to_key` 的寫入在 loop thread、讀在 listener thread —— dict 的單次 `get` 在 GIL 下是原子的,與現有的 `self._seen` + `_seen_lock` 慣例一致(那支已經跨執行緒了)。
- **風險**:中。要確認 `_symbol_to_key` 的更新時序(退訂競態下漏掉幾則是現況就接受的,`logger.debug` 註解已寫明)。
- **工作量**:M

### B05-11 `_context` 每則訊息建一個 frozen dataclass(tick 路 + 簿路各一次)

- **位置**:`copycat/server/signal_hub.py:992-1010`
- **熱路徑**:是,每則
- **證據**:`TickContext` 是 `@dataclass(frozen=True)` 無 slots、10 個欄位 → 建構 ~1.05 µs + `_best_limit_price` ×2(各掃五檔)≈ **2 µs/則**。
- **影響**:小(2 µs × 1000/s = 2 ms/s)。列出是因為修法成本是零:`TickContext` 加 `slots=True`。
- **修法**:`@dataclass(frozen=True, slots=True)`。另外 `_best_limit_price(bids)` 在 `stock_models._parse_levels` 剛跑完後又掃一次同一份 list —— parse 層已經算過 `bid0`/`ask0`(`stock_models.py:221-222`)並存進 `tick.bid_milli`/`ask_milli`,簿路才真的需要重算。tick 路可以直接用 tick 上的值。
- **風險**:低。但「tick 路用 tick 的值」要確認語意等價 —— `parse_stock_realtime` 的 `bid0` 就是同一則的簿算出來的,應該恆等,要寫測試釘住。
- **工作量**:XS(slots)/ S(省重算)

### B05-12 `dropped_foreign_ticks` 路徑:TXO aggregator 對每則非本序列 tick 做 dict 查 + 計數

- **位置**:`copycat/live/aggregate.py:85-87`
- **熱路徑**:是(TXO runtime 的 SUB `""` 會收到全部期貨推播)
- **證據**:
  ```python
  if tick.symbol not in self._contracts:
      self.totals.dropped_foreign_ticks += 1
      return False
  ```
  但**在這之前**已經付了 `parse_realtime()`(`tc4.py:1219`)—— 完整解析了一個不要的 tick。
- **影響**:`parse_realtime` 比個股版便宜(沒有五檔),估 3–5 µs/則 × cross-talk 比例。
- **修法**:`handle_raw` 在 `parse_realtime` 之前先用 symbol 前綴/集合判一次。
- **風險**:低。但 `_SPOT_PREFIX` 的分流語意(`models.py:16-25` 那段長註解)不能動。
- **工作量**:S

---

## 4. 工具選型建議

### 4.1 建議導入

| 工具 | 用在哪 | 解決什麼 | 代價 | 判定 |
|---|---|---|---|---|
| **orjson** | `server/app.py` 的 `default_response_class` + `ws.py` 的 `send_json` | `json.dumps` 51 ms → 估 7–15 ms(group batch);tape snapshot 16.6 → 估 3 ms | 加一個 C extension 相依(有 cp313 win_amd64 wheel);dict key 必須是 str(現況已符合,但成了**隱性契約**要寫進 CLAUDE.md);`NaN` 行為與 stdlib 不同 | **建議導入**(放 `live` extra,與 fastapi/uvicorn 同層) |

### 4.2 有條件導入

| 工具 | 用在哪 | 條件 | 判定 |
|---|---|---|---|
| **msgspec** | 取代 `StockTick` / `Tick` 等 frozen dataclass,並接管 JSON 編碼 | `msgspec.Struct` 建構比 frozen dataclass 快 3–5×、記憶體比 slots dataclass 再省一截,`msgspec.json.encode` 可直接吃 Struct(省掉 `snapshot()` 的 dict 中介層,那是 B05-08 的 1.35–8 ms 構建成本)。**但**:會動到 `dataclasses.replace`(`stock_models.py:145`)、`dataclasses.field`、以及全庫 60k LOC 測試裡的 dataclass 慣例 | **有條件** —— 只有在 B05-01/02/03/04 都做完、量測顯示仍不夠快時才值得 |
| **winloop**(Windows 版 uvloop) | uvicorn loop | 收益在 socket IO(HTTP/WS),不在本區塊的純計算。而且本區塊的停頓是**同步 CPU 佔用**,換 loop 實作救不了 | **有條件**,且優先度低於上面全部 |
| **`array` / `struct`**(stdlib) | `StockDayState.ticks` columnar 化 | 365 B/tick → ~30 B/tick,且 tape 序列化可以直接走 array;零新相依,符合 stdlib-only 哲學 | **有條件**(B05-07 的第三條路,L 級) |

### 4.3 不建議

| 工具 | 為什麼不 |
|---|---|
| **numpy** | 本區塊沒有任何「一次處理一個陣列」的運算。每 tick 是**純量** int 加法;唯一像樣的向量運算是 `CorrState` 的 1800 樣本 Pearson,而那裡的成本 93% 在 `_paired_returns` 的**重複計算**(修法是增量,不是向量化),`statistics.correlation` 本身只佔 7%(86 µs)。numpy 的 `corrcoef` 頂多省 60 µs/秒。**而且**引入 numpy 會讓 `dependencies = []` 的 stdlib-only 約束破功,換來的是不到 0.01% CPU。 |
| **numba** | 熱路徑是 dict 查找 / 字串切片 / frozen dataclass —— numba 的 nopython 模式對這些幾乎沒有加速空間,而且 JIT 暖機會讓開盤前幾秒行為不確定。對一個要下實單的系統,「第一筆 tick 的延遲不可預測」是負價值。 |
| **polars / duckdb / pyarrow** | 這裡沒有 dataframe 形狀的資料。(回測區塊 B0x 可能適合,不在本區塊。) |
| **redis** | 沒有跨 process 狀態共享需求(單機單 process)。 |
| **Python 3.13 free-threaded(`--disable-gil`)** | 理論上最對症(能真的把 group_snapshot 丟到別的核),但 `comtypes` / `pywin32`(群益下單)/ `pyzmq` 的 free-threaded wheel 生態在 2026 年中仍不完整。**下實單的系統不該押這個。** |
| **手刻取代 `Decimal`** | 實測 0.41 µs vs 0.39 µs,只快 5%,而 `tc4common.py:16` 的 docstring 明確記了「Decimal 截斷 vs float banker's rounding 在 tick 邊界會分岔」的教訓。**明確不要動。** |

---

## 5. 不要動的地方(這同樣是結論)

1. **`StockDayState.ingest` / `_apply` / `_fold_vp`** —— 1.96 µs/tick,VWAP、high/low、VP 全部已經是增量式,零多餘配置。這段是全 repo 寫得最好的熱路徑之一。唯一該動的是它**持有的記憶體**(B05-07),不是它的演算法。
2. **`to_milli_units`(Decimal)** —— 見 §4.3。實測不是瓶頸,而且有明確的正確性理由。
3. **`ChainAggregator` / `payoff` 全家** —— 實務態 13.7 µs/秒。`curve_points` 的 O(n²) 在 n = 實際部位合約數(個位數)下完全無關。`build_grid` 用 `statistics.median` 也只在 snapshot 跑。**過度工程警告**:這裡是最容易被「O(n²)!」吸引去優化的地方,但它一天跑不到 2 萬次。
4. **`RiverState`** —— push / apply_backfill 都是 O(1) dict 寫;`snapshot` 的 `dict(minutes)` 複製 300–840 筆,每秒一次 delta 只碰 `_last_write`。沒有問題。
5. **`HandoverBuffer`** —— list append,cap 200k。只在交接窗活著。
6. **`trade_models.py`** —— 下單路徑,一天幾十次。`Decimal` 用在這裡是**正確的**(價格字串精確轉換),不要因為「Decimal 慢」就動它。
7. **`_note_push` 的自癒記帳** —— 在 listener thread,早退很快,而且它背後有一整串盤中實測教訓(`tc4-market-facts` skill)。不要為了 1.5 µs 碰它。
8. **`snapshot(tape=False)` 的 `tape=0` 契約** —— 已經是這個區塊裡最成功的優化(14×)。保留並擴大這個思路。

---

## 6. 改動會踩到的跨檔契約(CLAUDE.md §4)

| 契約 | 哪個 finding 會踩到 | 兩邊要怎麼同動 |
|---|---|---|
| **個股 `seq` 的兩個口徑**(`snapshot.seq` = ticks 尾筆;`tick.seq` 每筆 +1) | B05-08(增量 tape) | `stock_state.ingest/snapshot` ↔ `frontend/src/lib/stock-accum.ts::fromSnapshot`(由尾回推 React key)。動 tape 形狀 = 兩邊同動,漂掉的症狀是 tbody 靜默整片重掛 |
| **快照與打包的 seq 對齊(兩道閘)** | B05-02(分批 `await` 讓路!) | ⚠ **高風險**:`group_snapshot` 開頭 `self._flush_ticks()` 後若在迴圈中 `await`,期間新 tick 會進 `_pending_ticks` 並推進 `state.seq` → 後半段的檔拿到的 seq 會領先已送出的打包。**分批讓路必須把 `_flush_ticks()` 搬進每一批之前,或整段禁止 await**。`stock_engine.py:838` 的 docstring 已寫明「只能在 event loop 上呼叫」 |
| **`light_snapshot()` 鍵名的單一定義** | B05-02(增量 wire)、B05-06 | 產生點 `stock_state.py:237`,讀者 `frontend/src/hooks/useGroupSnapshots.ts` + `stock_engine.py:848` 的 `{**light, …}`。加 `?since=` 參數屬 additive,但**前端缺鍵的降級路徑要顯式寫**(不能靠 `?? null`) |
| **VP parity golden**(`tests/fixtures/vp_parity.json`) | B05-02(`vp` 增量)、B05-06 | 後端 `_fold_vp` ↔ 前端 `stock-accum.ts::foldVp`。`snap_down_milli` 的單一定義在 `market.py:31` |
| **訊號規則參數 parity**(`tests/fixtures/signal_param_specs.json`) | B05-05(共用狀態層) | `signal_rules.py::PARAM_SPECS` ↔ `frontend/src/lib/signal-params.ts`。重構若動到參數語意就要同動 |
| **掃單簇 golden**(`tests/fixtures/sweep_cluster_golden.json`) | B05-05 | 線上 `_eval_sweep` 必須與研究 `combo_events.py` 的 `expected_prefix` 集合相等。改 `_eval_sweep` 的狀態推進位置 = 這條 golden 會紅,那是**正確的紅**不是誤報 |
| **`/api/stock/state/{code}?tape=0` + `tape_omitted`** | B05-08 | `app.py` 只認字串 `"0"`;讀者 `useStockStream.ts::stateUrl` + `stock-accum.ts::fromSnapshot` |
| **關機預算三方同源**(`shutdown_budget.py`) | 無(本區塊不動 lane 形狀) | — |
| **orjson 的隱性契約** | B05-02 | orjson 拒絕非 str dict key。`_minutes_payload` 的 `str(k)` 與 `_vp` 的 `str(price)` **從「JSON 物件鍵只能是字串」的說明升級成硬約束**,要寫進 CLAUDE.md §4,否則日後有人「順手」把 key 改回 int 就會在 prod 拋 `TypeError`(而測試若還在用 stdlib json 就是綠的) |

---

## 7. 量測方法(要證明快或慢,該怎麼量)

### 7.1 離線微量測(已建立,可直接重跑)

scratchpad 下四支腳本,`PYTHONUTF8=1 .venv\Scripts\python.exe <script>`:
- `bench_b05.py` —— ingest / snapshot / light_snapshot / parse / evaluate / TXO snapshot 全表
- `bench_signal.py` —— evaluate 的窗密度掃描 + cProfile
- `bench_parse.py` —— parse 拆解 + Decimal vs 純整數對照
- `bench_payload.py` —— group batch 構建 + json.dumps + payload size
- `bench_corr.py` —— CorrState 每秒成本

**改任何一條 finding 之前先跑一次存 baseline,改完再跑一次對照。** 這幾支腳本的數字就是驗收證據(CLAUDE.md 鐵則 D)。

### 7.2 線上探針(prod,不改行為)

1. **event loop 停頓監測(最重要)**:起一個 `asyncio` task
   ```python
   async def _loop_lag_probe():
       while True:
           t0 = time.perf_counter()
           await asyncio.sleep(0.05)
           lag = (time.perf_counter() - t0 - 0.05) * 1000
           if lag > 20: logger.warning("loop 停頓 %.0f ms", lag)
   ```
   盤中 grep `loop 停頓` —— 應該會看到每 60 s 一次 ~84 ms(B05-02)、每秒一次 ~14 ms(B05-03)。
   **這是把本報告的離線數字轉成真環境證據的唯一方法**,建議先做這個再動任何程式碼。
2. **cross-talk 比例(B05-10 的未知數)**:把 `stock_engine.py:1199` 的 `logger.debug("未對映的推播…")` 暫時改成每 60 s 節流的計數 INFO(`收到 n 則 / 其中 m 則訂閱池外`)。盤中一輪就知道 B05-10 的量級。
3. **窗密度分布(B05-01 的量級)**:在 `_flush_watchlist_loop`(已有的 1 s loop)加一行,每 60 s 記錄 `max(len(w) for w in detector._window.values())` 與中位數。決定 B05-01 的實際收益是 52 µs 還是 5 µs。
4. **記憶體(B05-07)**:盤後 `psutil` / 工作管理員看 python.exe 的 working set;或加一條 13:45 的 `tracemalloc` 快照 log。對照 328 MB 的估算。
5. **payload size**:`curl -s "localhost:8721/api/stock/group-state?codes=..." | wc -c`,對照 3.2 MB 的估算。**這條現在就可以做,不必等盤中。**

### 7.3 驗收 gate

沿 CLAUDE.md §1:`pytest -q` + `ruff check` + `pyright` + `copycat validate` 全 PASS。
本區塊的改動另加:
- B05-01 / B05-03:一條「增量 == 整批」的 property test(隨機序列 1000 輪)
- B05-02 / B05-06 / B05-08:動 wire 的話,前後端 parity 測試(既有 fixture)
- 全部:突變測試(把增量的 `-=` 改成 `+=`,測試必須紅)

---

## 8. Open questions(查不出來,需要真環境或 user 拍板)

1. **真實的 REALTIME 訊息速率是多少?** CLAUDE.md 記「50 檔開盤每秒數百筆」是**成交**筆數,但 `parse_stock_realtime` 對**每則訊息**都跑(含純簿更新)。純簿更新 : 成交的比例我查不到 —— 這個比例直接決定 B05-04(strptime)和 B05-10(cross-talk)的收益量級。→ 需要 §7.2 探針 2。
2. **cross-talk 的實際比例**:5 條 TC4 session 各自 SUB `""`,到底有多少比例的訊息是「不是我的」?`models.py:16` 的註解說 TXO runtime 確實收得到其他引擎的推播,但沒有量。
3. **窗密度的實際分布**:`_window` 在真實的 2330 / 熱門股上到底是 300 筆還是 1500 筆?這決定 B05-01 是 52 µs/tick 還是 5 µs/tick 的收益。
4. **群組檢視實際開幾檔、幾個分頁?** 84 ms 是 150 檔的上限值。實務上 user 常開的是 60 檔的盤前篩選群組(34 ms)還是自訂小群組(< 10 ms)?多分頁同時輪詢會倍增。
5. **規則數會不會長?** B05-05(共用狀態層,L 級重構)只有在規則數會從 4 長到 10+ 時才划算。user 有沒有打算大量新增規則?
6. **`_TICKS_MAXLEN = 20_000` 真的需要嗎?** 前端 tape 實際顯示幾筆?如果只顯示最近幾百筆 + 一個「載入更多」,deque 可以砍到 2000,記憶體直接省 10×,`snapshot(tape=True)` 也從 25 ms 降到 2.5 ms。這是本區塊**投報率最高**的一個決定,但它是產品決定不是技術決定。
7. **下單路徑的延遲預算是多少?** 84 ms 的 loop 停頓對「看盤」是可接受的(畫面頓一下),對「下單」可能不是。user 要不要把下單 route 隔離到獨立的 process / thread pool?這會改變整個優先序 —— 如果下單要嚴格延遲保證,B05-02 就從「medium」升級成「critical」。
