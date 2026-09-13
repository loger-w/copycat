# X4-numeric —— 跨切:數值計算與資料結構稽核(numpy / polars 落點盤點)

> 掃描範圍:`C:/side-project/copycat/copycat/`(123 個 .py / 37,589 LOC)全庫。
> 所有數字皆為本次在 **本機實測**(Python 3.13.13,Windows 11,16 core),
> 量測腳本落在 `…/scratchpad/bench1.py` ~ `bench8.py`,A/B 用的 numpy / polars /
> orjson / msgspec 裝在 `…/scratchpad/bvenv`(**獨立 venv,未動專案 .venv,未動 repo 任何檔**)。
> 日期:2026-09-13。

---

## 0. 一句話結論

這個 codebase 的數值工作分成三層,而 **現況的最佳化投資完全押錯層**:

| 層 | 現況 | 判定 |
|---|---|---|
| **L1 熱路徑(每 tick / 每秒,跑在 asyncio event loop 上)** | 純 Python,`n` 通常 5–300。**但有三處是 O(n) 或 O(n²) 而且 n 隨行情熱度長大** | ⚠ **真問題;解法是改演算法,不是上 numpy**(唯一例外 = 相關係數) |
| **L2 週期任務(每 10 s / 每 60 s)** | 純 Python + stdlib `json`,n = 2,000 ~ 20,000 | 中度;**換序列化器(orjson/msgspec)是最高 CP 值的一刀** |
| **L3 離線回測 / 資料層(一天一次 ~ 一個月一次)** | 純 Python loop,n = 1,000,000 row / 21,254 個 JSON 檔 / 65,000 次規則評估 | 🔴 **polars + numpy 明確勝出,實測 14x–144x;而且這一層目前 16 核只用 1 核** |

`@dataclass(slots=True)` 的分布正好倒過來:**離線層 20/20 都有 slots,live 熱路徑 0/11 沒有**
(見 §5.1)。這不是效能災難,但它精準反映了「最佳化注意力放錯地方」。

---

## 1. 架構地圖:數值與資料在哪裡流動

### 1.1 三條資料流

```
[L1 即時流 —— 每 tick]
TC4 桌面 app
  └─ ZMQ SUB (localhost) ──► live/tc4.py::_listen_loop        ← 專屬 thread
        sock.recv() → json.loads()  (stdlib, 4.6 us/則)
        └─ call_soon_threadsafe ──────────────────────────────► asyncio event loop
                                                                  │
              server/stock_engine.py::_handle_quote ◄─────────────┘  (全部在 loop 上!)
                ├─ live/stock_models.py::parse_stock_realtime   22.0 us/則
                │     ├─ _parse_levels ×2 → to_milli ×10        (Decimal, 0.30 us ×21)
                │     ├─ _taipei_time → datetime.strptime        8.6 us/則  ← 39% 的解析成本
                │     └─ StockTick / StockBook / StockMeta 三個 frozen dataclass(無 slots)
                ├─ live/stock_state.py::ingest → _apply          O(1)  ✅
                │     └─ _fold_vp → market.snap_down_milli       O(1)  ✅
                ├─ server/signal_hub.py::on_tick
                │     └─ ×4 rule slot → live/signal_state.py::evaluate
                │            ├─ _eval_cdp        O(5 條 CDP 線)   ✅
                │            ├─ _eval_surge      O(1)            ✅
                │            ├─ _eval_pullback   O(1)            ✅
                │            ├─ _eval_volume     **O(窗內筆數)** ❌ ← 見 X4-01
                │            └─ _eval_sweep      O(1) amortised  ✅
                └─ _pending_ticks.append → 0.1 s call_later 打包 → WsBroadcaster.publish
                                                    └─ starlette send_json → json.dumps(stdlib)

[L2 週期任務 —— 每 1 s / 10 s / 60 s,全部在 event loop 上]
server/corr_engine.py::tick_once          每 1 s  → CorrState.correlations()    13.6 ms ❌❌ X4-02
server/engine.py::snapshots()             每 1 s/client → payoff.curve_points()  O(n²)  ❌ X4-03
server/stock_engine.py::_flush_watchlist_loop 每 1 s → ~150 則 watchlist_quote
server/breadth_engine.py::_poll_loop      每 10 s → compute_breadth(2,000 row) + json.dumps 4.0 ms ❌ X4-04
server/stock_engine.py::group_snapshot    每 60 s → 150 × light_snapshot  6.4 ms  ✅(可接受)

[L3 離線 —— CLI / 一天一次]
data/daily/prices.csv (52 MB, 1,013,469 row)
  └─ data/daily.py::DailyIndex.load   csv.DictReader + 1M 個 dataclass   4.33 s  ❌ X4-05
data/1k/<stock>/<date>.json  ×21,254 檔(294 MB)
  └─ data/store.py::read_bars   json.loads + Bar1K 建構  0.83 ms/檔 → 全掃 18 s ❌ X4-06
backtest/
  ├─ fade_*.py  逐 bar 路徑相依模擬(不可向量化)    16M+ bar-iteration  ❌ X4-07(單核)
  └─ search.py  bitmask 謂詞 + 窮舉 + GA            65,000 次 _entry    ❌ X4-08
```

### 1.2 這張圖裡最重要的一件事

**`_handle_quote` 到 `signal_hub.on_tick` 到 `WsBroadcaster.publish` 這整條,全部同步跑在 asyncio event loop 上。**
唯一不在 loop 上的只有 `json.loads`(在 TC4 listener thread)與 `to_thread` 包住的 ZMQ REQ / 回補取數。

這代表:**任何一個在 L1/L2 上的 O(n) 都是「event loop 停擺 n 微秒」**,而不是「多花一點 CPU」。
最極端的是 `CorrState.correlations()`:每一秒,event loop 有 **13.6 ms 完全停住**,
期間 WS fanout 不動、tick 不處理、HTTP route 不回。

---

## 2. 熱路徑逐條(含實測頻率與每次工作量)

### HP-1 `live/stock_models.py::parse_stock_realtime` —— 每則 TC4 推播

- **頻率**:每則 REALTIME。150 檔訂閱,開盤時保守估 500–2,000 則/s(實測未取得,見 §10 Q1)。
- **每次**:22.0 µs。拆解:`_taipei_time` 8.6 µs(39%)、`to_milli` × 21 = 6.4 µs(29%)、
  三個 frozen dataclass 建構 ≈ 2.9 µs、其餘 dict.get / str()。
- 證據(`copycat/live/stock_models.py:89-95`):
  ```python
  def _taipei_time(precise_utc: str, date_utc: str) -> tuple[str, str]:
      s = precise_utc.zfill(12)
      hh, mm, ss, frac = int(s[:2]), int(s[2:4]), int(s[4:6]), s[6:9]
      base = _dt.datetime.strptime(date_utc, "%Y%m%d")   # ← 每 tick 一次 strptime
      local = base + _dt.timedelta(hours=hh, minutes=mm, seconds=ss) + _TAIPEI_OFFSET
      return f"{local:%H:%M:%S}.{frac}", f"{local:%Y-%m-%d}"
  ```
  `date_utc` 一整天只有一到兩個值。

### HP-2 `live/stock_state.py::_apply` + `_fold_vp` —— 每筆成交 tick

- **頻率**:每筆去重後成交。
- **每次**:O(1) —— running max/min、一個 dict setdefault、一個 list 三格累加。
- **判定:✅ 這裡寫得很好,不要動**。`_vp` 刻意做成逐 tick 增量而不是請求時掃 20k deque
  (`stock_state.py:60-64` 的註解已經把理由寫清楚)。這正是本報告要推廣的模式。

### HP-3 `live/signal_state.py::evaluate` —— 每筆成交 tick × 4 個 rule slot

- **頻率**:每筆成交 × `len(signal_hub._slots)`。prod 現況 `data/signal_rules.json` = **4 條規則**
  (cdp_cross / surge_crash / vol_burst / limit_lock,全部 enabled)。
  每個 slot 持有**自己一份** `SignalDetector`,所以 `_window` deque 有 4 份。
- **每次**:除 `_eval_volume` 外全是 O(1) 或 O(5)。`_eval_volume` 是 **O(窗內筆數)**,見 X4-01。

### HP-4 `server/corr_engine.py::tick_once` —— 每 1 s

- **每次實測 13.6 ms**(11 腿 × 3 窗 × 1800 樣本)。見 X4-02。

### HP-5 `server/engine.py::snapshots()` —— 每 1 s **× 每個 WS client**

- `latest_snapshot()` → `ChainAggregator.snapshot()` → `curve_points(rows, grid)` 是 **O(|rows| × |grid|)**,
  而 `|grid| ≈ |strikes| + 2`,`|rows|` = 當日有成交過的 TXO 合約數。實測:
  100 rows → 0.62 ms / 200 rows → 2.53 ms / 400 rows → **11.21 ms**。見 X4-03。

### HP-6 `server/stock_engine.py::_run_backfill_job` 尾端的 `state.apply_backfill(...)` —— 開盤每檔一次

- **在 event loop 上同步跑**(`stock_engine.py:1688` 附近,`await to_thread` 只包住取數,套用在 loop 上)。
- 實測 6,000 筆 = **9.96 ms**;150 檔開盤合計 ≈ **1.5 s 的 event loop 阻塞**(分散在 worker 串行期間,每檔一記 10 ms 卡頓)。

---

## 3. Findings(依嚴重度排序)

### 🔴 X4-01 `_eval_volume` 每 tick 對整個滾動窗做 `sum()` —— 成本隨行情熱度平方成長

- **位置**:`copycat/live/signal_state.py:658`
- **熱路徑**:是。每筆成交 tick × 每個啟用 vol_burst 的 rule slot(prod = 1 條)。
- **證據**:
  ```python
  # signal_state.py:657-659
  window_min = self._cfg.surge_window_secs / 60
  window_vol = sum(qty for _ts, _price, qty in window)   # ← O(len(window)),每 tick
  ratio = window_vol / (avg_per_min * window_min)
  ```
  `window` 是 `evaluate()` 維護的 deque,以**時間**逐出(`signal_state.py:320-322`):
  ```python
  cutoff = mono - self._cfg.surge_window_secs      # 預設 300.0 秒
  while window and window[0][0] < cutoff:
      window.popleft()
  ```
  `surge_window_secs` 預設 **300 秒**(`signals_config.py:29`),prod rule 的 params 也是 300。
  所以 `len(window)` = 該檔過去 5 分鐘的成交筆數。
- **實測**(`bench5.py` E 節):

  | 窗長(筆) | `sum()` 成本 | 該檔 10 tick/s 時每秒成本 |
  |---|---|---|
  | 50 | 1.84 µs | 0.02 ms/s |
  | 300 | 10.62 µs | 0.11 ms/s |
  | 1,000 | 37.15 µs | 0.37 ms/s |
  | 3,000 | 117.14 µs | **1.17 ms/s** |

- **影響**:成本 = (tick 速率) × (窗內筆數) = (tick 速率)²×300。
  **這是形狀最糟的一種成本曲線 —— 系統在市場最熱、你最需要它反應快的時候最慢。**
  攻漲停 / 爆量的那一檔正是窗最長的那一檔,也正是訊號要即時發出的那一檔。
  冷門股 50 筆窗無感,2330 開盤 3,000 筆窗就是每 tick 117 µs 卡在 event loop 上。
- **修法(不需要任何套件)**:在 `evaluate()` 維護一個 running 總量,append 時 `+= qty`、
  popleft 時 `-= qty`,`_eval_volume` 改讀該值 → **O(1)**。
  因為窗是**同時** append 與 popleft 的固定總和,不會有浮點漂移問題(qty 是 int)。
  需要同時把 `window` 從裸 deque 換成一個帶總和的小 wrapper(或在 `SignalDetector` 存
  `self._window_qty: dict[str, int]`,與 `self._window` 同生命週期:`reset_day` / `drop_code` 同批清)。
- **風險**:`_eval_surge` / `_eval_pullback` 也讀同一個 `window`(只讀 `window[0]` / `window[-1]`,
  以及 `_eval_pullback:613` 的一次性掃描),它們不受影響。
  **不動任何跨檔契約**;`tests/fixtures/sweep_cluster_golden.json` 與 `signal_param_specs.json`
  都不涵蓋這個內部實作。要補一條「running sum ≡ sum(window)」的不變式測試。
- **effort**:S

---

### 🔴 X4-02 `CorrState.correlations()` 每秒在 event loop 上停 13.6 ms;檔頭註解的成本宣稱錯了 13 倍

- **位置**:`copycat/live/corr_state.py:82-126`,由 `copycat/server/corr_engine.py:543`
  的 `state()` → `tick_once()`(`corr_engine.py:322`)每 `tick_secs`(**預設 1.0 s**)呼叫。
- **熱路徑**:是(每秒,event loop 同步)。
- **證據 1 —— 檔頭的成本宣稱**(`corr_state.py:5-7`):
  ```
  - **整批重算,不維護增量統計量**:`statistics.correlation`(stdlib,內部用 fsum)對
    1800 樣本實測 0.15 ms,整輪 tick 外推不到 1 ms。
  ```
  這句話只量了 `statistics.correlation` **一次**的成本,沒有量整個 `correlations()`。
- **證據 2 —— 實測**(`bench3.py` / `bench4.py`,11 腿 × 窗 (60,300,1800) × 1 s 取樣,
  即 `configs/correlation.json` 的真實形狀):

  | 項目 | 實測 |
  |---|---|
  | `correlations()` 整支 | **13.60 ms**(另一 venv 17.12 ms) |
  | └ 其中 `_paired_returns` 全腿 | 6.81 ms |
  | └ 其中 `statistics.correlation` × 33 次 | 6.36 ms |
  | 檔頭宣稱 | 「不到 1 ms」 |

- **為什麼這麼慢**(`corr_state.py:91-111`、`121-124`):
  ```python
  leg_by_ts = dict(leg_series)                    # 每腿重建 1800-entry dict
  for ts, base_mid in base_series:                # 每腿重掃 1800 筆
      ...
      rb = log_return(prev_base, base_mid)        # math.log ×2 每樣本
      rl = log_return(prev_leg, leg_mid)
  return [row for row in out if row[0] >= now - self._max_window]   # 又掃一次
  ...
  for window in self._windows:                    # 3 窗
      xs = [rb for ts, rb, _ in paired if ts >= cutoff]   # 各掃一次 1800
      ys = [rl for ts, _, rl in paired if ts >= cutoff]   # 再掃一次
  ```
  每秒重算 **同一組 1799 個報酬中的 1798 個**;只有最後一筆是新的。
- **影響**:每秒 13.6 ms event loop 完全停擺(1.4% duty cycle,但是**同步的一整塊**)。
  這 13.6 ms 內 tick 不進、WS 不出、HTTP route 不回。對「要下實單」的系統這是最該先拔掉的一根刺。
  另外 `tick_once()` 的 `self._broadcast(self.state())` 是**無條件每秒呼叫**,
  就算沒人開相關係數面板也照算(`_broadcast` 走 `WsBroadcaster.publish`,沒有 client 時是空迴圈,
  但 `state()` 已經算完了)。
- **修法(三段,由便宜到徹底)**:
  1. **不需要任何套件 —— 增量維護 paired returns**:`push()` 時就把新的一筆 `(ts, rb, rl)`
     算好 append 進 per-leg deque,`_evict` 同步逐出。`correlations()` 只剩「切窗 + 算 r」。
     預期 13.6 → ~7 ms。
  2. **切窗改 bisect**:`paired` 已按 ts 升冪 → `bisect_left` 找 cutoff,切片取代三次全掃。
     預期再省 ~1 ms。
  3. **numpy 全向量化**:base 與 10 腿的報酬各存成 `np.ndarray` ring buffer,
     一次算 `(10 腿 × 3 窗)` 的 Pearson。**實測 0.090 ms** → 相對現況 **151x**。
     (單看相關係數本身:`statistics.correlation` 0.193 ms vs `np.corrcoef` 0.036 ms = 5.4x;
     真正的倍率來自把 `_paired_returns` 的 Python 迴圈整個消掉。)
  4. **無論選哪一段,都應該讓 `state()` 在沒有 corr WS client 時跳過 `correlations()`**
     (`WsBroadcaster` 已有 `self._clients`,加一個 `has_clients()` 即可)。
- **風險**:
  - 檔頭的設計理由是「增量滑動窗的浮點誤差會隨執行時間累積」。
    **修法 1/2 不違反它** —— 逐出的是「報酬」不是「統計量」,相關係數本身仍然每次整批重算。
    真正被禁的是「增量維護 Σx/Σx²/Σxy」,本提案不碰。
  - 修法 3 會把 `statistics.correlation`(fsum,高精度)換成 numpy float64 兩趟累加,
    **數值結果會在 1e-15 量級有差**。`corr` 沒有 golden fixture parity 契約(CLAUDE.md §4 沒有列),
    但前端顯示到小數第 2 位,實務上不可見。仍建議先做 1+2、把 3 列為第二步並附對照測試。
  - **契約**:CLAUDE.md §4「江波圖調色盤色數 ≥ 相關係數腿數」與「稀疏腿 `sparse` 旗標」
    都只約束**腿的集合**,不約束計算方式 → 本 finding 不動契約。
- **effort**:修法 1+2 = M;修法 3 = M(但要拉進 numpy 依賴,見 §6)

---

### 🟠 X4-03 `payoff.curve_points` 是 O(合約數 × 履約價數),每秒 × 每個 WS client 各算一次

- **位置**:`copycat/live/payoff.py:41-51`
- **熱路徑**:是(`server/engine.py:175` 的 `await asyncio.sleep(self._throttle)`,`throttle_secs` 預設 1.0)。
- **證據**:
  ```python
  # payoff.py:41-51
  def _pnl_ntd(rows, k_millipts):
      total_millipts = sum(
          row.net_qty * intrinsic_millipts(row.contract.cp, row.contract.strike_millipts, k_millipts)
          - row.net_cost_millipts
          for row in rows)                                   # O(|rows|)
      return total_millipts * MULTIPLIER / 1000

  def curve_points(rows, grid):
      return [(k, _pnl_ntd(rows, k)) for k in grid]          # O(|grid| × |rows|)
  ```
  `rows` 來自 `aggregate.py:171-179` 的 `self._pos.items()` —— **當日有成交過的每一個 TXO 合約**
  (不是使用者持倉),所以會隨交易日推進單調長大。`grid = build_grid(strikes)` 長度 ≈ 不重複履約價 + 2。
- **實測**(`bench3.py` B 節):

  | rows | grid | curve_points + find_beps |
  |---|---|---|
  | 50 | 27 | 0.16 ms |
  | 100 | 52 | 0.62 ms |
  | 200 | 102 | 2.53 ms |
  | 400 | 202 | **11.21 ms** |

- **影響**:TXO 主序列一天下來成交過的 C/P 合約數上看數百。
  另外 `snapshots()` 是 **per-client async generator**(`engine.py:147-175`),
  每個開著 `/ws/txo-pnl` 的分頁各跑一份 `latest_snapshot()` → **N 個 client = N 倍成本**,
  再加上 `_content(snap)` 的整份 dict 淺複本 + 深比較(`engine.py:49-60`)。
  已知實測 `/ws/txo-pnl` 是 8 條 WS 裡最肥的一條(23.2 KB/s,佔全部 WS 96%,
  `docs/research/2026-08-19-browser-crash-scan.md:31`)。
- **修法(不需套件,改演算法)**:到期損益是**分段線性**,可以 O(n log n) 一次算完:
  把每個 row 拆成「斜率變化點」(Call 在 strike 之上斜率 +net_qty,Put 在 strike 之下斜率 −net_qty),
  對 grid 由左到右做前綴和 → `curve_points` 從 O(n²) 降到 O(n log n)。
  400 rows 時預期 11.2 ms → < 0.3 ms。
  **更便宜的第一刀**:`latest_snapshot()` 在 `EngineRuntime` 層做**每 throttle 週期一次的快取**
  (版本號沒變就回上一份),讓 N 個 client 共用一次計算 —— 現況 `_version` 已經存在,
  `snapshots()` 只是各自呼叫 `latest_snapshot()` 而沒有共用結果。
- **風險**:曲線數值必須逐點相同(前端畫 BEP 與 max_profit/max_loss)。
  前綴和重寫要用現有的 `tests/live/test_payoff.py` 當 characterization,
  並加一條「隨機 200 組部位 × 新舊實作逐點相等」的 property test。
  無跨檔契約(payoff 只出現在 `/ws/txo-pnl` payload,前端不重算)。
- **effort**:快取 = S;前綴和重寫 = M

---

### 🟠 X4-04 stdlib `json` 是 WS / REST 的預設序列化器 —— orjson 快 9.3x,而最肥的 payload 是 2,000 列廣度表

- **位置**:全庫 74 處 `json.*`;WS 出口在 starlette `send_json`(`server/ws.py:212` 的
  `await websocket.send_json(data)`),入口在 `live/tc4.py:1199` 的 `json.loads`。
- **熱路徑**:WS 出口每秒數百則;TC4 入口每秒數百~數千則。
- **實測**(`bench4.py` B/C 節):

  | payload | stdlib json | orjson | msgspec |
  |---|---|---|---|
  | `watchlist_quote`(小 dict) | 2.5 µs | 0.2 µs(**9.9x**) | 0.4 µs(6.4x) |
  | `ticks` 打包 300 筆 | 324.4 µs | 36.1 µs(**9.0x**) | 58.7 µs(5.5x) |
  | breadth 2,000 rows | **3,965.9 µs** | 426.8 µs(**9.3x**) | 851.9 µs(4.7x) |
  | TC4 入站 `json.loads`(594 B) | 4.60 µs | 2.14 µs(2.2x) | — |

- **影響**:
  - `compute_breadth` 的結果(2,000 列)每 10 s 廣播一次:光是 `json.dumps` 就 **4 ms event loop 阻塞**,
    而且是 **per client**(starlette 對每個 WS 各 dumps 一次)。
  - 側欄 `watchlist_quote` 每秒 ~150 則 × N client × 2.5 µs。
  - TC4 入站 json.loads 在 listener thread,但 GIL 下仍與 event loop 競爭。
- **修法**:
  1. **`WsBroadcaster` 改為「入列前序列化一次」**:`publish(msg)` 時 `orjson.dumps(msg)` 得到 bytes,
     queue 裡放 bytes,`relay` 改 `send_text(...)` / `send_bytes(...)`。
     **N 個 client 共用一次序列化** —— 這一項本身就能把多分頁情境的成本除以 N。
  2. 入站 `_realtime_msg` 的 `json.loads` → `orjson.loads`。
  3. 離線層 `data/store.py` 的 `read_bars` / `write_bars` 同步換(見 X4-06)。
- **風險 / 取捨**:
  - **orjson / msgspec 是 C 擴充,會打破「runtime stdlib-only」的專案哲學**
    (`pyproject.toml` `dependencies = []`)。但 live 已經需要 `pyzmq` + `uvicorn[standard]`
    (裡面有 httptools / uvloop-family C 擴充),所以 **`[live]` extras 加 orjson 不是新的性質變化**。
  - orjson 對 `float('nan')` / `Decimal` / 非 str key 的行為與 stdlib 不同。
    本 codebase 的 WS payload 都是 str/int/float/None/list/dict,且 `_minutes_payload`
    已經明確把 key 轉成 `str(k)`(`stock_state.py:207`)—— **相容**。要注意 `_vp` 也是 `str(price)`。
  - **契約**:`ticks` 打包、`watchlist_quote`、`signal` 列的 wire 形狀逐鍵不變(只換編碼器)。
    但 **jsonl 真相源不可換**:`signal_hub` 的 `backfill_policy_outcomes` 契約明寫
    「只重寫被補的列、其餘列**原文逐字保留**、`tests/server/test_signal_outcome.py` byte 比對釘住」
    —— orjson 的浮點字面與鍵序與 stdlib 不同,**`data/signals/*.jsonl` 這條路一律維持 stdlib json**。
    這是本項唯一的硬約束,必須在 code 裡留註解標死。
- **effort**:M(WsBroadcaster 改 bytes queue 會動到 6 路 WS 的 relay 契約,但都在 `server/ws.py` 一個檔內)

---

### 🟠 X4-05 `DailyIndex.load` 用 `csv.DictReader` + 100 萬個 dataclass 讀 52 MB CSV,4.33 s;polars 0.03 s(144x)

- **位置**:`copycat/data/daily.py:31-56`
- **頻率**:離線,每次跑 `tday-features` / `tday-search` / `fade` pipeline 各一次。
- **證據**:
  ```python
  # data/daily.py:34-48
  with (data_dir / "daily" / "prices.csv").open("r", encoding="utf-8") as fh:
      for r in csv.DictReader(fh):                 # 1,013,469 列
          rows.setdefault(r["stock_id"], []).append(
              _DayRow(date=r["date"], open=float(r["open"]), ... ))   # 1M 個物件
  for lst in rows.values():
      lst.sort(key=lambda x: x.date)               # 2,044 次 sort
  ```
- **實測**(`bench6.py` G / `bench7.py` K):

  | | 現況 | polars |
  |---|---|---|
  | 讀 prices.csv(52 MB / 1,013,469 列 / 2,044 檔) | **4.33 s** | **0.03 s**(144x) |
  | 依 (stock_id, date) 排序 | 含在上面 | 0.03 s |
  | 寫成 parquet | — | 0.04 s → **14.0 MB**(CSV 52 MB) |
  | 讀 parquet | — | **0.022 s** |
  | 全表 adv20 rolling mean | 現況每次查詢 slice+sum | **0.021 s**(一次算完全部) |
  | 記憶體(僅 `_DayRow` 物件本體) | ≈ 89 MB | numpy column ≈ 8 MB/欄 |

- **影響**:每次跑回測都先付 4.3 s + 89 MB。更重要的是 **`adv20` / `bb_width_pct` / `pos_52w`
  這些方法現在是「每次查詢都重算」**:
  ```python
  # data/daily.py:163-181  bb_width_pct
  for j in range(i - window + 1, i + 1):        # window=60
      w = self.bb_width(stock_id, lst[j].date, n, k)   # 每次又 _find + slice + 2 次 sum(20)
  ```
  → 一次 `bb_width_pct` = 60 × (bisect + 40 次浮點運算) ≈ 2,400 ops。
  polars 只要 `rolling_std(20).over("stock_id")` 一次算完全表(實測 21 ms / 1M 列)。
- **修法**:
  1. 一次性把 `prices.csv` 轉成 `prices.parquet`(14 MB),`DailyIndex.load` 改 `pl.read_parquet`。
  2. **`DailyIndex` 的公開 API 完全不動**(`adv20` / `ma` / `bb_width` / `pos_52w` / `board_streak` …),
     只把內部 `dict[str, list[_DayRow]]` 換成「per-stock 的 numpy 欄 + date→index 對照」。
     `bisect_left(self._dates[sid], date)` 改成 dict 直查 O(1)。
  3. 把 `adv20` / `bb_width` / `pos_52w` 改成 **load 時整表預算一次**(polars rolling over stock_id),
     查詢變成 O(1) 陣列取值。
- **風險**:
  - `bb_width` 用「母體 σ」(`/n` 不是 `/(n-1)`,`daily.py:160`),polars `rolling_std` 預設 ddof=1 —— **必須顯式傳 ddof=0**,否則所有回測數字靜默改變。
  - `quantiles.py` 檔頭明寫「兩種分位數演算法並存,**不可互換**(user 2026-07-20 拍板保留)」
    —— polars 的 `quantile` 是第三種插值法,**不得拿來取代那兩支**。這裡只換資料載入,不換分位數。
  - 需要 characterization:把現況 `DailyIndex` 對一組固定 (stock_id, date) 的全部方法輸出凍成 golden JSON,新實作逐值相等。
- **effort**:L(API 不動但內部全換 + 需要 characterization 保護)

---

### 🟠 X4-06 21,254 個 1K JSON 小檔 = 離線層的結構性瓶頸;全掃 18 s,其中 55% 花在建 `Bar1K` 物件

- **位置**:`copycat/data/store.py:41-60`(`read_bars`),呼叫端 `backtest/fade_pipeline.py:97,444,703`
  與 `backtest/pipeline.py`。
- **頻率**:離線;但 `fade_pipeline` **同一批 sample 會重讀多次**(97 / 444 / 703 三處各一趟,無 cache)。
- **實測**(`bench6.py` H 節,真實 `data/1k/`):

  | | 值 |
  |---|---|
  | 檔數 / 總量 | 21,254 檔 / 294 MB(294 MB 目錄,257 MB 純 JSON) |
  | `read_bars` 單檔(270 bar) | **0.83 ms** |
  | 全量 21,254 檔推估 | **18 s**(每一趟) |
  | 其中 `read_text` + `json.loads` | 45% |
  | 其中 `Bar1K` 物件建構 | **55%** |
  | `orjson.loads` + `read_bytes` | 比 stdlib 快 **2.3x** |

- **影響**:`fade_pipeline.run` 一趟至少讀兩到三遍 → 40–55 s 純 IO/解析,每次調參都重付。
  而且 21k 個小檔在 Windows NTFS 上的 open/close syscall 成本無法用更快的 parser 消掉。
- **修法(由便宜到徹底)**:
  1. **立刻可做,零依賴**:`fade_pipeline` 內把 `read_bars` 結果 memo 起來(`{(sid,date): bars}`),
     消掉 2–3 倍重讀。
  2. `json.loads` → `orjson.loads`(2.3x on the 45% 部分)。
  3. **結構性解**:把 21,254 個 JSON 併成 **按月分割的 parquet**
     (`data/1k/YYYY-MM.parquet`,欄 = stock_id, date, m, o,h,l,c, v, up, down, unch)。
     polars 讀 parquet 實測 1M 列 22 ms;全量 1K ≈ 5.7M 列 → 預期 **< 1 s**(對比現況 18 s)。
     磁碟從 294 MB → 估 30–50 MB。
  4. 模擬層不吃 `list[Bar1K]` 而吃 **per-sample 的 numpy 欄**(見 X4-07)。
- **風險**:
  - `write_bars` 有一條不變式檢查(`store.py:18-19`:`bars 未按分鐘索引遞增`)—— parquet 版要保留。
  - `Bar1K` 是 `@dataclass(frozen=True, slots=True)`(`data/models.py:8`),全庫大量 `b.close` 屬性存取。
    若改成欄式,`simulate_fade_sample` 等使用點要一起改 → 這是 L 級改動,建議與 X4-07 同批做。
  - `data/` 是 gitignored 的本機產物,**轉檔不動版控、不動任何跨檔契約**。可以保留 JSON 寫入路徑當 fallback。
- **effort**:步驟 1+2 = S;步驟 3+4 = L

---

### 🟠 X4-07 `backtest/fade_*` 的逐 bar 模擬是路徑相依、不可向量化;真正的槓桿是「16 核目前只用 1 核」

- **位置**:`copycat/backtest/fade_simulate.py:163-260`(`simulate_fade_sample` 的 `for b in post:` 主迴圈)、
  `copycat/backtest/fade_cells.py:213-241`(`_simulate_cell_trades`)。
- **頻率**:離線。
- **證據 —— 為什麼 numpy/polars 幫不上**:
  ```python
  # fade_simulate.py:163 起
  for b in post:
      locked = b.low >= t1_limit - eps
      if locked: ...; continue                    # 分支
      if b.low < running_low: running_low = b.low; stall = 0
      else: stall += 1
      running_high = max(running_high, b.high)
      outer_win.append((b.up_volume, b.down_volume))
      cum_delta += b.up_volume - b.down_volume
      ...                                          # 之後是多條停損 / 停利的早退
  ```
  **狀態機 + 早退**:`running_low` 決定 `stall`,`stall` 決定是否出場,出場就 `return`。
  這是嚴格序列相依的,numpy 的 ufunc 與 polars 的 expression 都沒有對應原語。
- **工作量級**:`_simulate_cell_trades` 對 **每個 spec × 整個 universe × 每個 sample 的 ~270 bar**。
  `evaluate_cells_from_universe` 的 spec 數 = `len(cell_a_inner_thresholds) + len(cell_b_approach_dists)
  + len(cell_c_rally_pcts)`,round3/round4 再乘上 `struct_stop_buffers`
  (`fade_cells.py:650-651` 的雙層迴圈)→ 輕易到 **10⁷–10⁸ 次 bar iteration**。
- **修法**:
  1. **🥇 最高 CP 值、零依賴:`concurrent.futures.ProcessPoolExecutor` 切 universe。**
     全庫目前 **零 multiprocessing 使用**(`grep -rn "multiprocessing|ProcessPool|concurrent.futures" copycat` → 0 命中),
     而本機 **16 核**。sample 之間完全獨立(`_simulate_cell_trades` 的 `out.append` 是純累積),
     切塊 → 合併即可。預期 **8–12x**,而且不引入任何第三方套件、不改數值語意。
     Windows 上 spawn 成本高 → 用 chunksize 粗切(每 worker 一整個 spec 或一大塊 universe),
     universe(sample+bars)要能 pickle —— `FadeSample` / `Bar1K` 都是 slots dataclass,可以。
  2. **numba `@njit`**:把 `simulate_fade_sample` 的主迴圈改吃 6 個 float64 array(o/h/l/c/up/dn),
     預期 **20–50x**。代價:LLVM 相依 ~200 MB、首次 JIT 編譯延遲數秒、Windows 上 numba 對 Python 3.13
     的支援時程需先驗(見 §6)。
  3. **Cython / mypyc**:同樣量級但要編譯工具鏈,Windows 上要 MSVC —— 對「一台 Windows 本機」來說維護成本高。
  4. 不要 PyPy:與 pyzmq / comtypes / pywin32 這些 CPython C 擴充不相容,live server 用不了,
     只為回測維護第二個 runtime 不划算。
- **風險**:平行化**不改任何數值**,但要確認 `logger` 與 `dataclasses.replace(cfg, ...)` 在 worker 內行為一致;
  `fade_cells.py:302` 的 `stress_cfg = dataclasses.replace(cfg, stress_guard_fill_high=True)` 要在 worker 內重建或一起 pickle。
  回測報告有 golden/對照機制(`copycat compare out/A out/B`)→ **平行化前後跑一次 compare 應逐字相同**,這就是驗收判準。
- **effort**:multiprocessing = M;numba = L

---

### 🟡 X4-08 `backtest/search.py` 的 bitmask 很聰明,但 numpy 布林遮罩仍快 14–146x

- **位置**:`copycat/backtest/search.py:39-47`(`_pred_mask`)、`94-111`(`_evaluate`)、`143-168`(`exhaustive_scan`)
- **頻率**:離線;`exhaustive_scan` 掃 1+2 條件 = `P + P(P−1)/2` 次 `_entry`。
  `quantile_probs` 9 個 × 2 方向 × 特徵數 → 20 個特徵時 P ≈ 360 → **64,980 次**。
  外圈還有 `theta_grid` 11 個 × regime 數 × `ga_seeds` 5 個。
- **實測**(`bench5.py` D 節):

  | n_rows | `_pred_mask` | numpy | `_evaluate` | numpy | exhaustive_scan 推估 |
  |---|---|---|---|---|---|
  | 1,000 | 92.2 µs | 1.4 µs(**64x**) | 126.0 µs | 9.1 µs(**14x**) | 8 s → 1 s |
  | 5,000 | 595.8 µs | 4.1 µs(**146x**) | 1,351.5 µs | 25.9 µs(**52x**) | **88 s → 2 s** |

- **為什麼**:
  ```python
  # search.py:39-47
  def _pred_mask(rows, feature, threshold, ge):
      mask = 0
      for i, r in enumerate(rows):          # Python 迴圈 × n_rows
          v = r.get(feature)                 # dict 查表 × n_rows
          ...
          mask |= 1 << i                     # 大整數位移(n_rows=5000 時是 5000-bit 整數)
  # search.py:101-107
  for i in _bit_indices(mask):               # 每次重新解碼整個 bitmask
      w = weights[i]; raw += 1; wsum += w; acc += pnl[i] * w
  ```
  `rows: list[dict[str, float|None]]` 是 **row-oriented dict of dict** —— 對 65,000 次全掃來說是最糟的佈局。
  `_bit_indices` 每次 `mask & -mask` + `bit_length()` 對 5,000-bit 大整數做,是 O(n²/64)。
- **修法**:把 `rows` 一次轉成 `np.ndarray[float64]` (n_rows × n_features) + `np.isnan` 遮罩,
  `Predicate.mask` 改存 `np.ndarray[bool]`,`_evaluate` 改 `(pnl*w)[m].sum()`。
  `exhaustive_scan` 的 `mask_i & mask_j` 改 `np.logical_and`。
  **搜索結果與 tie-break 序完全不變**(bitmask 與 bool array 同構;`rule_sort_key` 的
  `json.dumps(conditions, sort_keys=True)` 照舊)。
- **順帶**:`search.py:140` 的 `rule_sort_key` 在 `out.sort()` 裡對 65,000 個候選各做一次
  `json.dumps` —— 約 0.3 s。可以改成預先算好 key 的 decorate-sort-undecorate,或直接把
  conditions 轉成 tuple 比較。低優先。
- **風險**:`_PENALTY = -1e9` 的浮點罰底與 `_evaluate` 的加總順序 —— numpy 的 `.sum()` 是 pairwise 累加,
  與 Python 的順序累加在 1e-15 量級有差,可能翻動兩條 fitness 恰好相等的規則的排序。
  `ga_search` 的 `_fit` cache 與 `rng` 序列不受影響(seed 決定性保留)。
  **驗收判準 = 同 seed 跑完 `copycat compare out/before out/after`**,若有 1e-15 級差異需 user 拍板接受。
- **effort**:M

---

### 🟡 X4-09 `_taipei_time` 每 tick 做一次 `datetime.strptime` —— 佔解析成本 39%,而輸入一天只有兩個值

- **位置**:`copycat/live/stock_models.py:89-95`
- **熱路徑**:是(每則帶成交的 REALTIME + 每筆回補 tick)。
- **實測**:`_taipei_time` **8.60 µs**;把 `strptime(date_utc)` memo 起來後 **4.67 µs**(**1.8x**)。
  整支 `parse_stock_realtime` 22.0 µs → 約 17.9 µs。
- **修法**:module 級 `dict[str, datetime]` cache(`date_utc → base + 台北偏移`),
  一天最多 2 個 entry。**進階**:再把 `s[:6]`(HHMMSS)也當 cache key,
  則兩次 `f"{local:%...}"` 格式化也省掉 → 估 ~1.5 µs,**5.7x**。
  秒級 cache 一天上界 = 86,400 entry × 兩個 str ≈ 10 MB,可以只留 `maxlen` 或每日清。
- **風險**:`parse_hist_tick` 共用同一支,回補路徑同步受益。**`is_trial_window` 與
  `_taipei_time` 的輸出格式字串一個字都不能變**(`stock_state._apply:157` 用
  `int(tick.time[:2])*60 + int(tick.time[3:5])` 硬切位置;`signal_state.tick_secs` 用 `split(":")`)。
  cache 只換來源不換格式 → 安全。需要一條「cache 命中與未命中輸出逐字相等」的測試。
- **effort**:S

---

### 🟡 X4-10 `tc4common.to_milli_units` 每則推播呼叫 21 次;dict memo 快 3.3x(但不要改演算法)

- **位置**:`copycat/tc4common.py:16-29`,呼叫點 `stock_models._parse_levels`(10 次)+ meta 5 次 + price 1 次
  + `live/models.to_millipts` 家族。
- **實測**:`Decimal` 版 **0.305 µs**;手刻字串解析 0.243 µs(1.3x);**dict memo 0.091 µs(3.3x)**。
  每則推播 21 次 → 6.4 µs → memo 後 1.9 µs。
- **修法**:**只加 memo,不改演算法**。價格字串的值域在一天內極小(某檔的五檔報價來回跳同一組價位),
  memo 命中率會非常高。用 `functools.lru_cache(maxsize=8192)` 或裸 dict + 大小上限。
- **風險 —— 這裡有一條白紙黑字的禁令**(`tc4common.py:21-23`):
  ```
  🚨 **不與 float 家族合併**(`stock_source._milli`、`round(float(x) * 1000)`):
     Decimal 是截斷、float round 是 banker's rounding,在 tick 邊界會分岔。
  ```
  → **手刻字串解析版(0.243 µs)雖然我實測與 Decimal 逐值相等,但它是第三種實作,
  違反這條禁令的精神,不建議**。memo 保留 Decimal 本體,零語意風險。
- **effort**:S

---

### 🟡 X4-11 `stock_engine._watchlist` 是 `list` 卻用來做每 tick 的 membership test

- **位置**:`copycat/server/stock_engine.py:301` 宣告 `self._watchlist: list[str] = []`,
  熱路徑讀者在 `1347`(`if code in self._watchlist:`,每筆 ingest 成功的 tick)
  與 `1357`(`if (recovered or was_meta_none) and code in self._watchlist:`,**每則推播**)。
- **實測**(`bench8.py`,n=147):

  | | list | set |
  |---|---|---|
  | 命中(中位) | 0.540 µs | 0.042 µs(**13x**) |
  | 未命中 | 1.084 µs | 0.038 µs(**29x**) |

- **影響**:每則推播 1–2 次 × ~0.5–1.1 µs。1,000 則/s → 0.5–2 ms/s 純浪費。量不大,但**零風險**。
- **注意**:`_watchlist` 的**順序有意義**(`_trial_flip_targets:1807` 的 `codes = list(self._watchlist)`
  再 append main),所以**不能直接換成 set** —— 要並存一個 `self._watchlist_set: frozenset[str]`,
  在 `stock_engine.py:540` 的 `self._watchlist = list(codes)` 同行更新。
  (對照:`_tick_targets` / `_no_data` / `_backfilled` / `_tick_armed` / `signal_hub._watch`
  都已經正確用了 set/frozenset —— 這是唯一一個漏網的。)
- **effort**:S

---

### 🟡 X4-12 `apply_backfill` 在 event loop 上同步跑,6,000 筆 = 9.96 ms;開盤 150 檔 ≈ 1.5 s 阻塞

- **位置**:`copycat/live/stock_state.py:98-139`,呼叫點 `server/stock_engine.py`
  `_run_backfill_job` 尾端(`await asyncio.to_thread(self._source.backfill, code)` **只包住取數**,
  `state.apply_backfill(...)` 在 loop 上)。
- **證據**:
  ```python
  # stock_state.py:113-139
  if self.meta is not None:
      ticks = [relabel_locked_side(t, up, lo) for t in ticks]   # 6000 次 dataclasses.replace 候選
  backfill_max = max((t.cum_vol for t in ticks), default=-1)     # 掃一次
  survivors = [t for t in self.ticks if t.cum_vol > backfill_max]# 掃 deque(最多 20k)
  self.reset()
  for tick in ticks: ...; self._apply(tick)                      # 重放 6000 次
  for tick in survivors: ...
  ```
- **實測**:6,000 筆 = **9.96 ms**(有無 meta 幾乎一樣 —— `relabel_locked_side` 對非 neutral 的 tick 早退)。
  `parse_hist_tick × 6000` = 74.8 ms(這一段在 `to_thread` 內,✅ 沒問題)。
- **修法**:兩選一 ——
  (a) 把 `apply_backfill` 也搬進 `to_thread`(需要確認 `StockDayState` 的執行緒安全:
      `_handle_quote` 同時在 loop 上寫同一個 state → **會有 race,不建議**);
  (b) 把重放切成 chunk,每 1,000 筆 `await asyncio.sleep(0)` 讓出一次 loop。
      代價是 `apply_backfill` 要變 async 且中途狀態半成品可被讀到 —— 會動到
      「`seq` 一次跳增」的既有語意(`stock_state.py:101`)。
  **建議先量真實 tick 數再決定**:熱門股實測 6.2k(`stock_state.py:19` 的註解),
  10 ms 的單次卡頓在 150 檔串行的 worker 上是可接受的(不是每秒發生)。
  → **暫列觀察,不是必修**。
- **effort**:M(且風險高於收益)

---

### 🟡 X4-13 `compute_breadth` 對 2,000 列全市場 rows 每 10 s 重建 2,000 個 dict

- **位置**:`copycat/market_breadth.py:306-397`,由 `server/breadth_engine.py:528-529` 每
  `poll_secs`(**預設 10.0 s**,`breadth_config.py:22`)呼叫。
- **證據**:`rows_out.append({...12 個鍵...})`,per row 還有 4 次 `_to_number`(含 `isinstance` 三連)。
- **量級**:上市+上櫃約 1,900–2,100 檔 → 每 10 s 建 2,000 個 12-鍵 dict。
  純計算估 3–5 ms,**但真正的成本是後面的 `json.dumps` 3.97 ms**(X4-04)。
- **判定**:計算本身**不值得上 numpy**(rows 是異質 dict、要做字串/型別容錯,
  numpy 反而要先付一次轉換)。真正該做的是 X4-04 的序列化,以及
  **`assemble_universe` / `build_type_map` / `dedup_sector_map` 的 `sorted()` 已經只在冷啟動跑一次**
  (`breadth_engine.py:466-468`)→ ✅ 那部分已經對了。
- **一個小的真問題**:`market_breadth.py:111 / 126 / 147-151` 對 TaiwanStockInfo 的**全量 rows 做三次獨立 sort**
  (`build_name_map` / `build_type_map` / `dedup_sector_map` 各一次,後者還是雙層 sort)。
  冷啟動一次,不是熱路徑 → **不要動**。
- **effort**:—(併入 X4-04)

---

### 🟢 X4-14 live 層 11 個 `@dataclass` 全部沒有 `slots=True`,而離線層 20/20 都有

- **位置**:見 §5.1 完整表。最重要的是 `live/stock_models.py:46/63/69`
  (`StockTick` / `StockBook` / `StockMeta`)—— 全系統建構次數最多的三個物件。
- **實測**:

  | | 建構 | 記憶體 |
  |---|---|---|
  | `@dataclass(frozen=True)` | 0.950 µs | 48 B + `__dict__` 152 B = **200 B** |
  | `@dataclass(frozen=True, slots=True)` | 1.066 µs(**反而慢 12%**) | **112 B**(−44%) |

- **誠實的結論**:**slots 不會讓 frozen dataclass 建構變快**(frozen 的 `__init__` 走 `object.__setattr__`,
  slots 版一樣走,還多一層描述子)。**它只省記憶體。**
- **記憶體量級**:`StockDayState.ticks` 是 `deque(maxlen=20_000)`(`stock_state.py:19,47`),
  每個訂閱碼一份。150 檔 × 實測平均 5,000 筆 → 750,000 個 `StockTick`
  → 現況 ≈ **150 MB**,slots 後 ≈ **84 MB**(省 66 MB)。
  最壞(150 檔全滿 20k)→ 600 MB vs 336 MB。
- **判定**:**做,但理由是記憶體與 GC 壓力,不是 CPU**。
  對長跑的看盤 server,少 66 MB 的小物件同時也少一輪 gen2 GC 的掃描量。
- **風險**:`StockTick` 有 default 欄位(`bid_milli` / `ask_milli`),slots + default 在 3.10+ 沒問題。
  `relabel_locked_side` 用 `dataclasses.replace` —— slots 相容。
  `SignalEvent`(`signal_state.py:88`)的 docstring 明寫「**不可雜湊**:frozen dataclass 裝 dict」
  —— slots 不改變這件事。
  **`live/aggregate.py:24/33` 的 `Totals` / `_PosState` 是 mutable dataclass,加 slots 要確認沒有外部 setattr。**
- **effort**:S(一行一個裝飾器 + 跑全量測試)

---

### 🟢 X4-15 `_content(snap)` 每秒每 client 對整份 snapshot 做淺複本 + 深比較

- **位置**:`copycat/server/engine.py:49-60`,由 `snapshots():170-172` 每次版本變動呼叫。
- **證據**:`body = {k: v for k, v in snap.items() if k != "generated_at"}` 然後 `if body == prev: continue`。
  `snap` 含 `curve`(最多 202 個 tuple)、`contracts`(每檔一個 dict)、`beps`。
  深比較整份 = O(payload 大小)。
- **判定**:相對 X4-03 的 O(n²) 是小巫,而且這個比較**有明確的存在理由**(避免推送內容相同的 snapshot)。
  **不要獨立改**;若做了 X4-03 的「per-throttle 快取」,`_content` 自然也只算一次。
- **effort**:—

---

### 🟢 X4-16 全庫零 `.pop(0)`、deque 用得正確、沒有重複排序已排序資料

盤點結果(這些是**確認沒問題**的項目,同樣有價值):

- **`.pop(0)`**:`grep -rn "\.pop(0)" copycat` → **0 命中**。✅
- **`deque` 使用**:11 處,全部用途正確 ——
  `stock_state.ticks`(maxlen 20k)、`signal_state._window/_sweeps/_lookback`(時間逐出)、
  `corr_state._series`(時間戳逐出,`corr_state.py:11-13` 有明確理由)、
  `fade_simulate.outer_win`(maxlen)、`capital/balance._debts`、`signal_hub._discord_sent`。
  沒有一處用 list 當 queue。✅
- **`bisect`**:1 處(`data/daily.py:62`),用在排序好的日期索引上,正確。✅
  (可再進一步 → dict O(1),見 X4-05。)
- **重複排序已排序資料**:未發現。`stock_state._minutes_payload:218` 的 `sorted(self.minutes.items())`
  與 `:257` 的 `sorted(self._vp.items())` 是把 dict 轉成有序 wire 形,n ≤ 270,實測整支
  `light_snapshot` = 0.04 ms → ✅ 不要動。
- **迴圈內 append 後整份複製**:未發現。`fade_simulate.post_bars_so_far.append(b)` 是累積不複製。✅
- **`sum()/max()/min()` 對大 list**:熱路徑只有 X4-01 一處;
  `payoff.extremes:73-74` 的 `max/min(curve)` 是 O(|grid|) ≤ 202,相對 `curve_points` 可忽略。

---

### 🟢 X4-17 `screening.hard_candidates` 是 O(21 日 × 45,000 列),每天 08:00 跑一次 —— 不要動

- **位置**:`copycat/screening.py:109-173`
- **頻率**:**交易日 08:00 一次**(+ 啟動補跑)。
- **證據**:`shrink_rows` 已經先把每日 45,000 列縮成 ~2,000 檔 × 4 欄
  (`screening.py:69-81`,檔頭寫明「全市場單日 ~4.5 萬列 × 21 日全持有是 GB 級」)→ 記憶體紀律已經做對了。
  主迴圈是 `for sid, per_day in series.items()` × `for idx in range(n_days-2, -1, -1)` = 2,000 × 20 = 40,000 次。
- **判定**:**這裡不要動。** 一天一次的 40,000 次迴圈估 < 100 ms。上 polars 是純粹的過度工程,
  而且會把「還原係數鏈自算」這條已經有 review 保護的邏輯(`ratio *= close / prev_ref`)重寫一遍,風險遠大於收益。
  唯一要注意的是它跑在 server process 內 —— 確認 `screen_engine` 有沒有包 `to_thread`(見 §10 Q3)。

---

### 🟢 X4-18 `engine/lock_quality.py` / `engine/t1_open.py` / `replay/` —— 不要動

- 全部 `slots=True`、n ≤ 270 bar、離線 replay。
- `data/daily.py:200-209` 的 `board_streak` 是 while 迴圈往回走,最壞 O(該檔全部交易日)
  —— 但只在連板時往回走,實務上 ≤ 10 步。**不要動。**

---

### 🟢 X4-19 `market.py` 的 tick 表線性掃 5 個 zone —— 不要動

- **位置**:`copycat/market.py:15-19`
- **熱路徑**:是(`_fold_vp` 每筆成交 + `signal_state` 每次 CDP 判定)。
- **判定**:5 個元素的 tuple 線性掃,實測在噪音以下。改 bisect 對 n=5 反而更慢
  (bisect 的函式呼叫開銷 > 5 次整數比較)。
  **而且它與前端 `stock-tick.ts::snapDown` 有 `tests/fixtures/vp_parity.json` 的 parity 契約** ——
  為了 0 收益去動一個有跨語言 golden 的函式是負期望值。**明確:不要動。**

---

### 🟢 X4-20 `backtest/quantiles.py` 的三種分位數演算法並存 —— 不要用 polars/numpy 統一

- **位置**:`copycat/backtest/quantiles.py:1-8`(檔頭 user 拍板紀錄)+ `backtest/search.py:33-36`(第四種)
- **證據**:
  ```
  兩種演算法並存,**不可互換**(user 2026-07-20 拍板保留).
  統一演算法會改報告數字 = 行為改動,須另開行為輪,不得在 refactor 內做。
  ```
- **判定**:numpy `np.quantile` 有 9 種 interpolation,polars 又是另一組。
  **在這裡引入任何一種 = 靜默改變所有已發布的回測報告數字。明確:不要動。**
  上 numpy 時要在這個檔頭補一行「本檔刻意不用 np.quantile」。

---

## 4. 分類判定總表(任務要求的四分類)

### (a) 熱路徑 + 小 n → 純 Python 最快,**明確不要動**

| 位置 | n | 為什麼不要動 |
|---|---|---|
| `market.py::_tick_milli` | 5 | 5 次整數比較 < numpy/bisect 的呼叫開銷;且有 vp_parity 跨語言契約 |
| `stock_state.py::_apply` / `_fold_vp` | O(1) | 已經是增量維護的模範寫法 |
| `signal_state.py::_eval_cdp` / `_advance_sides` / `_advance_rearm` | 5 條 CDP 線 | 建立 numpy array 的開銷 ≈ 1 µs > 整段迴圈成本 |
| `signal_state.py::_eval_surge/_eval_pullback/_eval_sweep` | O(1) | 已經 O(1);`_eval_pullback:613` 的一次性掃描是發訊當下才跑(註解已說明是 O(k) 換每 tick O(1)) |
| `corr_models.py::mid_from_book` / `log_return` | 1 | 單值 `math.log`;numpy 純虧 |
| `overlay.py::compute_cdp` / `compute_ma` | ≤ 20 | 有 `tests/fixtures/overlay_parity.json` 跨語言契約;且有 cache |
| `payoff.py::extremes` / `find_beps` / `interp_pnl` | ≤ 202 | 相對 `curve_points` 可忽略 |
| `limit_streaks.py::compute_prev_streaks` | set 交集 | Python 的 set 交集已是 C 實作 |
| `data/models.py::Bar1K` 屬性存取 | — | slots dataclass,已是最佳 |

**通則:在這個 codebase 裡,任何 n < ~50 的熱路徑計算都不該碰 numpy。**
`np.array([...])` 的建構本身就是 1–3 µs,而這些迴圈整段才 1–5 µs。

### (b) 離線 + 大 n → polars/numpy 明確勝出(附實測倍數)

| 位置 | n | 現況 | 換工具後 | 倍數 |
|---|---|---|---|---|
| `data/daily.py::DailyIndex.load` | 1,013,469 列 | 4.33 s | polars read_csv 0.03 s | **144x** |
| 同上 → parquet | 52 MB | — | 14 MB / 讀 0.022 s | **197x** |
| `data/daily.py::adv20/ma/bb_width` | 全表 rolling | 每次查詢重算 | polars rolling 0.021 s 一次算完 | 依呼叫次數 |
| `data/store.py::read_bars` 全掃 | 21,254 檔 | 18 s | 併 parquet 估 < 1 s | **~18x** |
| `backtest/search.py::_pred_mask` | 5,000 列 | 595.8 µs | numpy 4.1 µs | **146x** |
| `backtest/search.py::_evaluate` | 5,000 列 | 1,351.5 µs | numpy 25.9 µs | **52x** |
| `backtest/search.py::exhaustive_scan` | P=360 | 88 s | numpy 2 s | **~44x** |
| `backtest/fade_*` 逐 bar 模擬 | 10⁷–10⁸ | 單核 | **multiprocessing 16 核** | **~10x**(零依賴) |
| 同上 | | | numba njit | **20–50x**(高代價) |

### (c) 熱路徑 + 中 n → 要實測才知道,但**這次已經實測完了**

| 位置 | 頻率 × n | 實測 | 判定 |
|---|---|---|---|
| `corr_state.correlations()` | 1/s × 11 腿 × 1800 | **13.6 ms/s** | 🔴 必修(X4-02);numpy 版 0.09 ms |
| `payoff.curve_points` | 1/s/client × n² | 200 rows 2.5 ms / 400 rows 11.2 ms | 🟠 必修(X4-03);**改演算法不是 numpy** |
| `signal_state._eval_volume` | 每 tick × 窗長 | 窗 3,000 → 117 µs/tick | 🔴 必修(X4-01);**改演算法不是 numpy** |
| `stock_state.apply_backfill` | 開盤 150 次 × 6,000 | 9.96 ms/次 | 🟡 觀察(X4-12) |
| `compute_breadth` | 1/10s × 2,000 列 | 估 3–5 ms + dumps 4 ms | 🟠 修序列化(X4-04),計算不動 |
| `group_snapshot` | 1/60s × 150 檔 | **6.4 ms**(light_snapshot 0.04 ms/檔) | ✅ 已夠快,不要動 |
| `StockDayState.snapshot(tape=True)` | 每次 REST | 1.74 ms / 6,000 tick | ✅ `tape=0` 契約已把群組路徑降到 0.04 ms |

### (d) 可以預先計算 / 快取掉,根本不用算的

| 位置 | 現況 | 應該 |
|---|---|---|
| `stock_models._taipei_time` 的 `strptime(date_utc)` | 每 tick 一次 | 一天一次(memo),X4-09 |
| `tc4common.to_milli_units` | 每次重解 Decimal | dict memo,命中率極高,X4-10 |
| `corr_state._paired_returns` | 每秒重算 1,798/1,799 筆舊報酬 | push 時增量算一筆,X4-02 |
| `engine.latest_snapshot()` | 每 client 各算一份 | per-version 算一次共用,X4-03 |
| `corr_engine.state()` | 無 client 也算 | `WsBroadcaster` 有 client 才算 |
| `data/daily.py` 的 adv20/bb_width | 每次查詢重算 | load 時整表預算,X4-05 |
| `fade_pipeline` 的 `read_bars` | 同批 sample 讀 2–3 遍 | memo,X4-06 |
| WS `send_json` | N client 各 dumps 一次 | publish 時 dumps 一次共用,X4-04 |

---

## 5. 資料結構稽核

### 5.1 dataclass `slots=True` 全庫統計

**70 個 `@dataclass`,27 個有 `slots=True`(38.6%),56 個 `frozen=True`。**
分布是**反的**:

| 模組群 | 有 slots | 無 slots | 實例數量級 |
|---|---|---|---|
| `backtest/` | **20** | 2(`fade_arms.py:130,141`) | 離線,每次 run 數千–數萬 |
| `data/` | 2(`daily._DayRow`、`models.Bar1K`) | 0 | 1M / 5.7M(離線)|
| `engine/` | 3 | 0 | 離線,每事件一個 |
| config 類(`*_config.py`) | 5 | 2(`corr_config.py:35,47`) | 單例 |
| **`live/`(熱路徑)** | **0** | **11** | **每 tick 3 個以上** |
| `server/` | 0 | 5 | 每 tick 1 個(`TickContext`)|
| `capital/` | 0 | 12 | 每筆委託/成交 |

**無 slots 且在熱路徑上的清單**:

| 位置 | 類別 | 建構頻率 |
|---|---|---|
| `live/stock_models.py:46` | `StockTick` | **每筆成交 + 每筆回補**;最多存 20k × 150 |
| `live/stock_models.py:63` | `StockBook` | **每則 REALTIME** |
| `live/stock_models.py:69` | `StockMeta` | **每則 REALTIME** |
| `live/signal_state.py:121` | `TickContext` | **每筆成交**(`signal_hub._context`) |
| `live/signal_state.py:88` | `SignalEvent` | 每則訊號(低頻) |
| `live/signal_state.py:108` | `_SweepGroup` | 每個同毫秒群 |
| `live/stock_state.py:28` | `MinuteAgg` | 每分鐘 × 每檔(≤ 270×150) |
| `live/stock_state.py:43` | `StockDayState` | 每檔一個 |
| `live/models.py:37/44/56` | `Tick` / `OptionContract` / `SeriesInfo` | TXO 每 tick |
| `live/aggregate.py:24/33` | `Totals` / `_PosState` | 每合約一個 |
| `live/payoff.py:15` | `PositionRow` | **每 snapshot × 每合約**(1/s × 200+) |
| `live/tc4.py:175` | (dataclass) | 低頻 |
| `server/signal_hub.py:288` | `_RuleSlot` | 4 個 |
| `server/signal_policy.py:85` | — | 每則政策 |
| `server/bars.py:214` | `_DailyEntry` | 每 (code, date) |

→ 見 X4-14。**收益是記憶體(−44%/物件),不是 CPU**;誠實標示。

### 5.2 list vs set membership

| 位置 | 型別 | 熱路徑 | 判定 |
|---|---|---|---|
| `stock_engine.py:301` `_watchlist` | `list[str]`(n≈150) | **每則推播 1–2 次** | 🟡 X4-11,加一份 frozenset |
| `stock_engine.py:276` `_tick_targets` | `frozenset` | 每 tick | ✅ |
| `stock_engine.py:300` `_no_data` | `set` | 每則 | ✅ |
| `stock_engine.py:320` `_backfilled` | `set` | 每則 | ✅ |
| `stock_engine.py:326` `_tick_armed` | `set` | 每則 | ✅ |
| `stock_engine.py:292` `_refs` | `dict[str, set]` | 每則 | ✅ |
| `signal_hub.py:393` `_watch` | `set` | 每 tick | ✅ |
| `signal_state.evaluate(enabled)` | `frozenset[str]` | 每 tick × 6 次查詢 | ✅ |
| `daily._limitup` | `set[tuple]` | 離線每次 `is_limitup` | ✅ |

### 5.3 其他

- **`.pop(0)`**:0 命中 ✅
- **deque**:11 處,用途全部正確 ✅
- **重複排序已排序資料**:未發現 ✅
- **迴圈內 append 後整份複製**:未發現 ✅
- **在 `__init__` 就把可變 default 做成 field(default_factory)**:`stock_state.py:46-47,65` 正確 ✅

---

## 6. 工具選型與取捨

### 6.1 逐項評估

| 工具 | 用在哪 | 預期收益 | 代價 | 判定 |
|---|---|---|---|---|
| **numpy** | `corr_state`(151x)、`backtest/search`(14–146x)、`data/daily` 欄式存放 | 明確且已實測 | ~20 MB wheel;Windows 3.13 有官方 wheel;打破 runtime stdlib-only | **有條件導入**:放 `[live]` 與新的 `[research]` extras,runtime 熱路徑只用在 corr 一處 |
| **polars** | `data/daily.py` 讀 CSV/parquet(144x)、1K 併檔、全表 rolling | 明確且已實測 | ~30 MB;Rust 靜態連結,Windows wheel 齊全;純離線 | **建議導入**,放 `[research]` extras,**不進 live server import 路徑** |
| **pyarrow** | parquet IO | polars 自帶 parquet 引擎,不必額外裝 | ~50 MB | **不建議單獨裝**(polars 已涵蓋) |
| **numba** | `fade_simulate` 主迴圈(20–50x) | 最大的離線倍數 | LLVM ~200 MB;首次 JIT 數秒;**對 Python 3.13 的支援時程需先驗證**;要把 Bar1K 攤平成 6 個 float64 array | **先不導入**:改用 multiprocessing 拿 10x,若還不夠再評估 |
| **Cython / mypyc** | 同上 | 同量級 | Windows 要 MSVC build tools;CI/散佈變複雜;本機單人專案維護成本高 | **不建議** |
| **PyPy** | 整個 runtime | 純 Python loop 可 5–10x | **與 pyzmq / comtypes / pywin32 / uvicorn C 擴充不相容**;live server 根本起不來 | **明確不建議** |
| **orjson** | WS 出口 / TC4 入口 / 1K 讀寫 | **9.3x dumps / 2.2x loads**,已實測 | C 擴充;浮點與 stdlib 字面不同 → **`data/signals/*.jsonl` 不可換**(byte-parity 契約) | **建議導入**([live] extras),並在 jsonl 路徑標死用 stdlib |
| **msgspec** | 同 orjson,另可取代 dataclass 做 zero-copy struct | dumps 4.7–6.4x;`msgspec.Struct` 比 dataclass 省更多記憶體 | 生態較小;會動到全庫的 dataclass 慣例 | **不建議**(orjson 已拿到 9x,msgspec 反而較慢;Struct 遷移是另一個大題) |
| **uvloop** | event loop | Linux 2–4x | **Windows 不支援**,`uvicorn[standard]` 在 Windows 上退回 asyncio | **不適用**(環境是 Windows) |
| **什麼都不裝、只改演算法** | X4-01(O(n)→O(1))、X4-03(O(n²)→O(n log n))、X4-09/10(memo)、X4-11(set)、X4-07(multiprocessing) | **X4-01/03/07 三項加起來是本報告最大的實際收益,而且零依賴** | 只有工程時間 | **🥇 第一優先** |

### 6.2 推薦的導入順序(先零依賴,再逐項加)

```
階段 0(零依賴,先做完)  ← 這一階段就能拿到大部分收益
  X4-01  _eval_volume running sum            S   每 tick O(n)→O(1)
  X4-09  _taipei_time memo                   S   parse 22→17.9 us
  X4-10  to_milli memo                       S   parse 再 −4.5 us
  X4-11  _watchlist 並存 frozenset           S   每則 −1 us
  X4-02(1+2) corr 增量 paired + bisect 切窗   M   13.6→~6 ms/s
  X4-03(快取) latest_snapshot per-version    S   N client → 1 份
  X4-14  live 層 dataclass 加 slots          S   記憶體 −44%/物件
  X4-06(1) fade_pipeline read_bars memo      S   離線 −2/3 IO
  X4-07  ProcessPoolExecutor 切回測          M   離線 ~10x(16 核)

階段 1(加 orjson,[live] extras)
  X4-04  WsBroadcaster 序列化一次 + orjson   M   dumps 9.3x、N client 共用
         ⚠ data/signals/*.jsonl 一律留 stdlib json(byte-parity 契約)

階段 2(加 polars,[research] extras,只在離線)
  X4-05  prices.csv → parquet + DailyIndex 內部欄式   L   144x
  X4-06(3) 1K JSON → 月度 parquet                     L   ~18x

階段 3(加 numpy,先離線後熱路徑)
  X4-08  backtest/search bool array          M   44x(需 compare 對照)
  X4-02(3) corr 全向量化                     M   再 → 0.09 ms(需數值對照)
```

---

## 7. 明確「不要動」的地方(反向結論)

1. **`market.py` 的 5-zone tick 表** —— n=5,改任何東西都更慢,而且有 `vp_parity.json` 跨語言契約。
2. **`stock_state._apply` / `_fold_vp`** —— 已經是增量 O(1),是全庫最該被抄的寫法。
3. **`backtest/quantiles.py` 的三種分位數** —— user 2026-07-20 拍板保留,
   換 `np.quantile` = 靜默改掉所有已發布報告數字。
4. **`tc4common.to_milli_units` 的 Decimal 本體** —— 檔頭明禁與 float 家族合併
   (Decimal 截斷 vs float banker's rounding 在 tick 邊界分岔)。只加 memo,不換演算法。
5. **`overlay.compute_cdp/compute_ma`** —— 有 `tests/fixtures/overlay_parity.json` 前後端 golden,
   而且已經有 `OverlayCache`,n ≤ 20。
6. **`screening.hard_candidates`** —— 一天一次,`shrink_rows` 的記憶體紀律已經做對了。
7. **`group_snapshot` / `light_snapshot`** —— 實測 150 檔 6.4 ms/60 s,已經夠快;
   `tape=0` 那條契約(CLAUDE.md §4)已經把成本從 1.74 ms 降到 0.04 ms/檔。
8. **`corr_state` 的「整批重算不維護增量統計量」原則** —— 這條設計理由(浮點誤差累積)是對的。
   X4-02 的修法是「增量維護**報酬**」而不是「增量維護**統計量**」,不要誤讀成推翻它。
9. **`market_breadth` 的三次 sort** —— 冷啟動一次,且有 `breadth_parity.json` oracle。
10. **`data/daily.board_streak` 的 while 迴圈** —— 實務 ≤ 10 步。
11. **`signal_state._eval_pullback:613` 的一次性掃描** —— 註解已說明是「每次發訊 O(k) 換每 tick O(1)」,
    這是刻意的取捨且方向正確。

---

## 8. 量測方法(要證明快或慢,怎麼量)

### 8.1 先做:抓真實的 tick 速率(本報告最大的未知數)

本報告的所有「每秒 N 次」都用推估。真值必須量:

```powershell
# 盤中,不動 prod:在 signal 或 engine 加一個每 60 s 印一行的計數器,或直接用 py-spy(已裝)
.\.venv\Scripts\py-spy.exe top --pid <server pid> --duration 60 --rate 200
.\.venv\Scripts\py-spy.exe record --pid <server pid> --duration 120 --format speedscope -o open.json
```
`py-spy record` 在開盤 09:00–09:02 錄兩分鐘的 speedscope,**這一份會直接回答**:
`parse_stock_realtime` / `_eval_volume` / `correlations` / `json.dumps` 各佔多少 %。
**這是整份報告最該先跑的一件事**,而且 py-spy 是 sampling profiler,對 prod 幾乎零侵入。

### 8.2 event loop 阻塞的直接判準

在 `app.py` lifespan 掛一個 loop lag 探針(零依賴):
```python
async def _loop_lag_probe():
    while True:
        t0 = time.perf_counter()
        await asyncio.sleep(0.1)
        lag = (time.perf_counter() - t0 - 0.1) * 1000
        if lag > 20:
            logger.warning("event loop lag %.1f ms", lag)
```
**判準**:修 X4-02 之前,盤中應該每秒都看得到 ~13 ms 的 lag spike;修完應該消失。
這是 X4-02 最直接的驗收證據,不需要任何 profiler。

### 8.3 逐項 A/B

| Finding | 量法 |
|---|---|
| X4-01 | 造一個 3,000 筆窗的 `SignalDetector`,`timeit` `evaluate()` 前後;盤中用 loop lag 探針看開盤 spike |
| X4-02 | `timeit` `CorrState.correlations()`;loop lag 探針 |
| X4-03 | `timeit` `curve_points(rows, grid)` 在 rows=100/200/400;盤中量 `/ws/txo-pnl` 的 lag |
| X4-04 | `timeit` `json.dumps(payload)` vs `orjson.dumps`;WS bytes/s 用既有的 websockets client 腳本 |
| X4-05/06 | 直接 `time` CLI:`python -m copycat tday-features` 前後 |
| X4-07 | `time` 整支 `fade` pipeline;**驗收 = `python -m copycat compare out/before out/after` 逐字相同** |
| X4-08 | 同上;另加同 seed 的 `ga_search` 輸出 diff |
| X4-09/10/11 | `timeit` 單函式(本報告的 bench1/bench2/bench8 可直接重跑) |
| X4-14 | `sys.getsizeof` + 盤後 `tracemalloc` 或 Windows 工作管理員 RSS 前後對照 |

### 8.4 回歸保護(改任何一項之前先架好)

1. `pytest -q` + `ruff check` + `pyright` + `copycat validate`(CLAUDE.md §1 的既有 gate)。
2. **離線層改動一律過 `copycat compare out/A out/B`** —— 這是本專案既有的 config 實驗對照工具,
   拿來當「重構不改數字」的機驗剛好。
3. 熱路徑改動要補**不變式測試**(不是行為測試):
   - X4-01:`running_sum == sum(window)` 在任意 push/pop 序列後恆成立
   - X4-09/10:memo 命中與未命中輸出**逐字相等**
   - X4-03:新舊 `curve_points` 對隨機 200 組部位逐點相等

---

## 9. 會動到的跨檔契約(CLAUDE.md §4)

| Finding | 契約 | 兩邊要怎麼同動 |
|---|---|---|
| X4-04(orjson) | **「T+1/T+2 回填原地補欄 + 離線讀者契約」** —— `signal_hub.backfill_policy_outcomes` 明定「只重寫被補的列、其餘列原文逐字保留」,由 `tests/server/test_signal_outcome.py` **byte 比對**釘住 | **`data/signals/*.jsonl` 的讀寫一律維持 stdlib `json`**,在 `signal_hub._append_jsonl` 留註解標死。WS/REST 路徑才換 orjson |
| X4-04(WsBroadcaster 改 bytes) | 「WS 心跳契約」`WS_HEARTBEAT_SECS` ↔ 前端 `WS_SILENCE_TIMEOUT_MS`;「`ticks` 打包訊息」;「`/ws/stock` 入站 `view` 訊息」 | wire **內容**不變(只換編碼器),但 `relay` 的 `send_json` → `send_text` 要確保 `PING` 也走同一條;`on_message` 入站解析不受影響 |
| X4-01 | 無(`_eval_volume` 是純內部)。但 `PARAM_SPECS["vol_burst"]` 的值域(`tests/fixtures/signal_param_specs.json`)不變 | 不動 |
| X4-02 | 「江波圖調色盤色數 ≥ 相關係數腿數」「稀疏腿 `sparse` 旗標」只約束腿集合 | 不動 |
| X4-03 | 無(payoff 只出現在 `/ws/txo-pnl`,前端不重算) | 不動 |
| X4-05 | `bb_width` 用母體 σ(ddof=0);`quantiles.py` 三演算法並存 | polars `rolling_std` **必須顯式 ddof=0**;分位數一律不換 |
| X4-09 | `tick.time` 格式 `HH:MM:SS.fff` 被 `stock_state._apply:157` 硬切位置、`signal_state.tick_secs` split;**且「個股 `seq` 的兩個口徑」與「台指期疊線分鐘鍵 −1 分」都建立在這個時刻上** | memo 只換來源不換格式,加一條逐字相等測試 |
| X4-10 | `tc4common.py:21-23` 的「不與 float 家族合併」禁令 | 只加 memo,保留 Decimal |
| X4-11 | 「自選上限常數多邊同值」(`WATCHLIST_LIMIT` = 150) | 不動(只是把 list 旁邊多掛一份 set) |
| X4-14 | 無 | 跑全量測試即可 |
| X4-19 | `market.snap_down_milli` ↔ 前端 `stock-tick.ts::snapDown`,`vp_parity.json` | **不要動** |
| X4-20 | `quantiles.py` user 拍板 | **不要動** |

---

## 10. Open questions(查不出來 / 需要 profile / 需要 user 拍板)

- **Q1(最重要)**:**開盤 09:00–09:05 的真實 TC4 入站訊息速率是多少?**
  本報告所有「每秒 N 則」都是推估。已知 8 條**出站** WS 實測是 futures 17.9 / stock 3.6 msg/s
  (`docs/research/2026-08-19-browser-crash-scan.md:130`),但**入站**沒有數字。
  → 跑一次 `py-spy record --pid <server> --duration 120` 在開盤,或在 `tc4.py:1250` 的
  `handle_raw` 加一個每 60 s 印一行的計數器。**這一個數字會決定 X4-09/X4-10/X4-11 到底值不值得做。**

- **Q2**:一檔熱門股在 5 分鐘窗內的**實際成交筆數上界**?
  `stock_state.py:19` 的註解說「熱門股單日 6.2k 實測、漲停攻防股更高」,
  但那是全日;5 分鐘窗的峰值沒有數字。X4-01 的嚴重度直接取決於它。
  → 盤後對 `data/1k/` 的高量檔算每分鐘成交筆數 × 5 即可(離線,不必盤中)。

- **Q3**:`screen_engine` 的 08:00 task 是不是包在 `to_thread` 裡?
  若不是,`hard_candidates` 的 40,000 次迴圈會在 event loop 上跑(08:00 盤前,影響低但仍值得確認)。

- **Q4**:TXO 主序列在收盤時 `ChainAggregator._pos` 的**實際合約數**是多少?
  X4-03 的成本在 100 rows 是 0.62 ms、400 rows 是 11.2 ms —— 差 18 倍。
  → `curl localhost:8721/ws/txo-pnl` 收一則看 `contracts` 陣列長度,或看 `totals.contracts_active`。

- **Q5(要 user 拍板)**:**要不要打破「runtime stdlib-only」?**
  `pyproject.toml` `dependencies = []` 是明確的專案哲學。本報告的最大收益裡:
  - **零依賴就能拿到**:X4-01 / X4-03 / X4-07 / X4-09 / X4-10 / X4-11 / X4-14 / X4-02 的前兩段
  - **必須加套件**:orjson(9x 序列化)、polars(144x 離線載入)、numpy(corr 151x、search 44x)
  建議的折衷是 **runtime 只加 orjson 到 `[live]` extras;polars/numpy 放新的 `[research]` extras
  且不出現在 `copycat/live/` 與 `copycat/server/` 的 import 路徑**(corr 的 numpy 版列為階段 3、另外拍板)。
  → **這是方向性抉擇,不該由我決定。**

- **Q6(要 user 拍板)**:X4-08 與 X4-02(3) 會讓浮點結果在 1e-15 量級變動。
  對 `backtest` 而言這可能翻動兩條 fitness 相等的規則排序。
  **接受 1e-15 級差異、還是要求 bit-identical?** 後者等於放棄 numpy 在這兩處。

- **Q7**:`data/1k` 的 21,254 個 JSON 是「凍結的研究資料」還是還會持續長大?
  若持續長大(每交易日 +N 檔),parquet 方案要決定是「月度 append」還是「每次全量重寫」。

---

## 附錄 A:量測腳本落點

| 腳本 | 內容 |
|---|---|
| `scratchpad/bench1.py` | `_taipei_time` / `parse_stock_realtime` / `StockTick` slots 建構與記憶體 |
| `scratchpad/bench2.py` | `to_milli_units` 三種實作 A/B |
| `scratchpad/bench3.py` | `CorrState.correlations` 分解 / `payoff.curve_points` 規模曲線 |
| `scratchpad/bench4.py` | numpy 向量化 corr / orjson·msgspec 序列化 / TC4 入站 loads |
| `scratchpad/bench5.py` | `backtest/search` bitmask vs numpy / `_eval_volume` 窗長曲線 / snapshot 三形狀 |
| `scratchpad/bench6.py` | `DailyIndex.load` / `read_bars` 對真實 `data/` |
| `scratchpad/bench7.py` | `apply_backfill` / `parse_hist_tick` / polars vs csv.DictReader vs parquet |
| `scratchpad/bench8.py` | list vs set membership @ n=147 |
| `scratchpad/bvenv/` | 獨立 venv(numpy / polars / pyarrow / orjson / msgspec),**未動專案 .venv** |

## 附錄 B:一頁速查

```
必修(熱路徑,零依賴)
  X4-01  signal_state.py:658   sum(window) 每 tick        → running sum     S
  X4-02  corr_state.py:82-126  13.6 ms/s event loop 停擺  → 增量+bisect     M
  X4-03  payoff.py:50          O(n²) 每秒每 client        → 快取 + 前綴和   S→M

該修(便宜)
  X4-09  stock_models.py:93    strptime 每 tick           → memo            S
  X4-10  tc4common.py:27       Decimal ×21/則             → memo            S
  X4-11  stock_engine.py:301   list membership 每則        → +frozenset     S
  X4-14  live/ 11 個 dataclass 無 slots                    → slots(省記憶體) S

該修(要加套件 / 離線)
  X4-04  server/ws.py          json.dumps ×N client       → orjson + 序列化一次  M
  X4-07  backtest/fade_*       16 核只用 1 核             → ProcessPoolExecutor  M
  X4-05  data/daily.py:34      4.33 s / 1M 列             → polars + parquet 144x L
  X4-06  data/store.py:41      18 s / 21k 檔              → memo + parquet       S→L
  X4-08  backtest/search.py:39 88 s exhaustive_scan       → numpy bool array 44x M

不要動
  market.py 的 5-zone / stock_state._apply / quantiles.py 三演算法 /
  to_milli 的 Decimal 本體 / overlay parity / screening / group_snapshot /
  corr 的「不增量維護統計量」原則 / market_breadth 冷啟動 sort
```
