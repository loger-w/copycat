# B12 — 回測核心 + replay + 評分引擎:架構掃描報告

> 掃描日期 2026-09-13 · 對象 `copycat/backtest/` `copycat/replay/` `copycat/engine/`
> `copycat/strategy_config.py` `copycat/watchlist.py`(連帶 `copycat/data/store.py`
> `copycat/data/daily.py` `copycat/data/models.py` —— 它們是本區塊的 IO 底座)
> 環境:Windows 11 / Python 3.13.13 / `.venv` / 全部量測皆為 **warm OS file cache**
> 紀律:唯讀掃描,repo 零改動;所有 benchmark 產物寫在 scratchpad(`scratchpad/out`、`scratchpad/out2`)

---

## 0. 一句話結論

**這一區塊是「離線批次」,不是熱路徑 —— 但它是量化系統的產能瓶頸,而且目前的實作把
90% 以上的 CPU 花在兩件可以被向量化掉的事上:(a) 把 bitmask 攤成 Python index list,
(b) 把 21,254 個小 JSON 檔逐檔 decode 成 596 萬個 dataclass 物件。**
兩件都有 100 倍等級的收益,而且因為 backtest 是 **offline CLI**,可以把 numpy / msgspec
放進 `[backtest]` extras,**完全不污染 stdlib-only 的 live runtime**。

同時有一個不是效能、但對「要下實單」更致命的架構問題:
**`copycat/engine/` 的狀態機只有 replay 在用,實盤走 `live/signal_state.py` 的另一份鎖板定義,
兩份在數學上不可能等價**(一份吃 Bar1K float close、一份吃整數毫元 + 五檔簿深度)。
你現在回測的東西不是你將來要交易的東西。

---

## 1. 架構地圖

### 1.1 三個子系統,三條獨立管線

```
                    data/ (檔案系統,無 DB)
  ┌──────────────────────────────────────────────────────────────┐
  │ data/1k/<stock_id>/<YYYY-MM-DD>.json   21,254 檔 / 294 MB    │
  │ data/daily/prices.csv                  ~1.04M 列             │
  │ data/events/events.csv                 11,048 列             │
  │ data/events/limitup_all.csv            11,048 列             │
  │ data/events/near_miss.csv              3,341 列              │
  │ data/events/tick_auction.csv           1,995 列              │
  └──────────────────────────────────────────────────────────────┘
        │                    │                        │
        │                    │                        │
  ┌─────▼──────┐    ┌────────▼─────────┐    ┌────────▼─────────────┐
  │ replay/    │    │ backtest/ (tday) │    │ backtest/ (fade_*)   │
  │ runner     │    │ pipeline         │    │ fade_pipeline        │
  │  ↓ engine/ │    │  ↓ universe      │    │  ↓ fade_arms         │
  │  LockTracker    │  ↓ features      │    │  ↓ fade_features     │
  │  T1Tracker │    │  ↓ simulate ×254 │    │  ↓ fade_simulate     │
  │  ↓         │    │  ↓ search (GA)   │    │  ↓ search (共用)     │
  │ events.jsonl    │  ↓ stats 三道驗證 │    │  ↓ walk-forward      │
  │  ↓ report  │    │  ↓ report        │    │  ↓ fade_report       │
  │  ↓ validate│    └──────────────────┘    └──────────────────────┘
  │  (golden gate)         out/tday_ga/            out/fade_*/
  └────────────┘
```

三條管線**共用底座**:`data/store.read_bars`、`data/daily.DailyIndex`、`data/models.Bar1K`、
`backtest/search.py`(謂詞/GA)、`backtest/stats.py`(加權統計)、`market.py`(tick 表)。
所以底座上的任何加速**三條線一起受惠**;反之底座上任何行為改動**三條線的 golden 一起紅**。

### 1.2 replay 管線資料流(`replay/runner.py::run_replay`)

```
load_config(StrategyConfig) ─┐
load_watchlist(frozenset)  ──┤
DailyIndex.load(data_dir) ───┤   ← 4.0 s(prices.csv 1.04M 列 csv.DictReader)
_load_tick_auction(csv)   ───┤
                             ▼
for ev in csv.DictReader(events.csv):       # 11,048 事件
    cohort = _cohort(source, broker_ids, wl.broker_ids)   # frozenset 交集
    t_bars  = read_bars(data_dir, stock, date)            # ← JSON 檔 IO
    LockTracker(cfg, limit); for b in t_bars: feed(b)     # 270 bar/檔
    lock_sig = tracker.finalize()
    t1_bars = read_bars(data_dir, stock, t1_date)         # ← JSON 檔 IO
    T1Tracker(cfg, ctx); for b in t1_bars: feed(b)
    t1_sig = t1.finalize(again)
    out.write(json.dumps({...}) + "\n")                   # events.jsonl 一列一事件
                             ▼
meta.json + write_summary(run_dir)   ← 再把剛寫的 8.45 MB events.jsonl 讀回來
```

**事件數 11,048;read_bars 呼叫 22,067 次(T 日 + T+1 各一);命中 17,449 次、缺 4,618 次。**
產出 `out/<watchlist>/events.jsonl` = 8.45 MB / 11,048 列。

### 1.3 tday 回測管線(`backtest/pipeline.py`)

兩個 CLI 動詞、兩段落檔:

```
tday-features:
  build_universe(events.csv + near_miss.csv) → list[Sample]
  per-sample 前置(θ 無關):read_bars / static_features / avg20_t1 / structural_features / t1_open
  for θ in theta_grid (11 個):
      for 每個 sample: find_trigger(bars, prev_close, θ) → trigger_features(13 欄)
      → features_theta<θ>.csv     (anchor 0.080 → 6,615 列 / 2.47 MB)

tday-search:
  _read_features × 11 θ
  _load_or_simulate × 11 θ:
      anchor θ → 254 個 key(baseline + baseline_stress + 252 combos)
      非 anchor θ → 2 個 key
      → outcomes_theta<θ>.json    (anchor 54 MB / 非 anchor 428 KB)
  for regime in (all, momentum, low_base):      # 3
      for anchor in anchor_thetas:              # 1
          build_predicates(train 3,179 列 × 24 特徵) → 366 謂詞
          exhaustive_scan(1-2 條件,66,795 對)
          ga_search × 5 seeds(pop 500 × 100 代)
          jaccard_dedupe → top 10
          for rank in top10:
              for θ in theta_grid (11):  apply_rule + weighted_stats   ← θ 曲線
              monthly_consistency / plateau_check / stop_duel(252 combo)
  → rules_final.json + docs/evidence/tday_join_ga_backtest_<date>.md
```

### 1.4 評分引擎(`engine/`)

兩個零 IO 狀態機,**皆為「逐 bar 餵入 + finalize 定稿」**:

- `LockTracker`(132 LOC):維護 `_bars` 全量 list、`_first_touch`、`_n_reopens`、`_in_limit`、
  `_run_start`。`feed()` 每 bar O(1);`finalize()` O(n) 三次掃描(day_vol、after_share、
  violent window)。輸出 `LockQualitySignals`(12 欄,frozen slots dataclass)。
- `T1Tracker`(161 LOC):維護 `_bars`、`_high`、`_high_pos`。`feed()` O(1);
  `finalize()` O(n) 兩次掃描 + 路徑分類 7 分支。輸出 `T1OpenSignals`(14 欄)。

兩者的門檻**全部來自 `StrategyConfig`**(48 LOC,18 個欄位,frozen slots + JSON 覆寫),
引擎 code 零 magic number —— 這一點做得很乾淨,**不要動**。

---

## 2. 熱路徑逐條(附實測)

### 2.1 量級定義(本區塊特有)

這一區塊**沒有「每 tick 跑」的東西**。全部是離線批次。所以「熱」的定義改成:
**在一次 CLI 執行內被呼叫的次數**。

| 頻率級別 | 本區塊代表 | 一次執行的呼叫數 |
|---|---|---|
| 極熱(百萬級) | `search.bit_indices` 內層迴圈、`Bar1K.__init__`、`LockTracker.feed` | 5,600 萬 / 596 萬 / 173 萬 |
| 熱(萬級) | `read_bars`、`simulate_sample`、`_entry` | 22,067 / 1,680,210 / 67,161 |
| 溫(千級) | `DailyIndex._find`、`apply_rule` | 10 萬 / 330 |
| 冷(一次) | `DailyIndex.load`、`write_report`、`run_validate` | 1 |

### 2.2 實測數據表(全部我親自跑出來)

| 量測項 | 數值 | 來源 |
|---|---|---|
| `DailyIndex.load` | **4.02 s**(cProfile 下 7.00 s) | bench1 / bench2 |
| `read_bars` 單次 | **0.97 ms**(平均 270 bar/檔) | bench1(500 次取平均) |
| **完整 replay(11,048 事件)** | **25.3 s wall** | `python -m copycat replay --watchlist five_tigers` |
| └ `read_bars` 累計 | **17.59 s(佔 55%)**,22,067 次 | cProfile cumtime |
| └ `json.decoder.raw_decode` | **4.09 s**,28,496 次 | cProfile tottime |
| └ `read_bars` 自身(建 Bar1K) | **3.56 s tottime** | cProfile |
| └ `DailyIndex.load` | 7.00 s(profiler 加權) | cProfile |
| └ `csv.__next__` | 3.07 s,1,037,564 次 | cProfile |
| └ `LockTracker.feed` | **1.53 s**,1,727,730 次(0.88 µs/bar) | cProfile |
| └ `T1Tracker.feed` | **1.04 s**,2,943,270 次(0.35 µs/bar) | cProfile |
| └ `nt.stat`(`path.exists()`) | 0.91 s,22,068 次 | cProfile |
| `load_events`(8.45 MB jsonl / 11,048 列) | 0.40 s | bench1 |
| **`run_validate`(golden gate 本體)** | **0.64 s / 42 checks / 42 PASS** | bench1 |
| `json.loads` 54 MB outcomes | 0.49 s(+ 0.06 s read) | bench1 |
| `_read_features`(6,615 列 CSV) | 0.09 s | bench3 |
| `enumerate_stop_combos` | **252 combos**(+baseline+stress = 254 key) | bench3 |
| `simulate_sample` × 254 combos / 樣本 | **4.2 ms** | bench3(150 樣本) |
| └ 外推 anchor θ 全量 | **≈ 28 s**(6,615 樣本)+ 6 s IO | bench3 |
| `build_predicates`(3,179 train × 24 特徵) | 0.19 s → **366 謂詞 / 66,795 對** | bench4 |
| **`exhaustive_scan`** | **27.3 s**(cProfile 下 47.5 s) | bench4 / bench6 |
| └ `bit_indices` tottime | **29.77 s(佔 63%)**,67,161 次呼叫 | bench6 |
| └ `int.bit_length` | 5.41 s,**56,173,966 次** | bench6 |
| └ `list.append` | 5.24 s,**56,238,727 次** | bench6 |
| `ga_search` 單 seed | **4.2 s** → ×5 seeds = 21 s | bench4 |
| **每 (regime, anchor) 搜索小計** | **≈ 48 s** → ×3 regime ≈ **145 s** | 推算 |
| `apply_rule`(6,615 列 × 2 條件) | 6 ms | bench4 |
| `_feature_row` 全表重建 | 37.1 ms × **330 次** = **12.2 s 純浪費** | bench5 |
| `pytest tests/backtest tests/engine tests/replay tests/data` | **352 passed / 10.19 s** | pytest |
| 謂詞 mask 平均 popcount | **1,628 / 3,179 列** | bench6 |

### 2.3 熱路徑 #1 — `search.bit_indices`(離線,單次執行 5,600 萬迴圈)

```python
# copycat/backtest/search.py:81-88
def bit_indices(mask: int) -> list[int]:
    out = []
    while mask:
        lsb = mask & -mask
        out.append(lsb.bit_length() - 1)
        mask ^= lsb
    return out
```

被 `_evaluate` 呼叫:

```python
# copycat/backtest/search.py:94-111
def _evaluate(mask, pnl, weights, cfg):
    raw = 0; wsum = 0.0; acc = 0.0
    for i in _bit_indices(mask):          # ← 每次把 ~1,628 bit 攤成 list
        w = weights[i]
        if w <= 0: continue
        raw += 1; wsum += w; acc += pnl[i] * w
```

**為什麼慢**:mask 是 3,179 bit 的 Python 大整數。`mask & -mask` 與 `mask ^= lsb` 各自是
O(n/64) 的 bigint 運算,而且**每次迴圈都配置一個新的大整數物件**。67,161 次規則評估 ×
平均 840 個 set bit = 5,617 萬次迴圈,外加 5,624 萬次 list append。
profiler 顯示 `bit_indices` 自己就吃掉 29.77 s / 47.5 s = **63%**。

這是整個 B12 區塊**最大的單一浪費**,而且修法乾淨(§4.1)。

### 2.4 熱路徑 #2 — `data/store.read_bars`(replay 的 55%)

```python
# copycat/data/store.py:42-60
def read_bars(data_dir, stock_id, date):
    path = bars_path(data_dir, stock_id, date)
    if not path.exists():                       # ← syscall #1(22,067 次 = 0.91 s)
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))   # ← syscall #2 + #3, decode 4.09 s
    return [Bar1K(m=int(r[0]), open=r[1], ..., unch_volume=r[8])
            for r in payload["bars"]]           # ← 596 萬次 dataclass 建構 = 3.56 s
```

三層浪費疊在一起:
1. `exists()` + `open()` = 每檔至少 2 次 syscall;Windows 的 `nt.stat` 特別貴(22,068 次 = 0.91 s)。
2. stdlib `json` 純 C 但仍需建 21,254 × 270 × 9 = 5,165 萬個 Python float/int 中間物件。
3. `Bar1K` 雖是 `frozen=True, slots=True`,596 萬次 `__init__` + 9 個 keyword 綁定 = 3.56 s。

**而且這批 bar 在一次 `tday-search` 裡會被讀第二次**:`run_features` 讀一輪存進
`per_sample`,`_load_or_simulate` 又逐 row 讀一次(pipeline.py:286)。

### 2.5 熱路徑 #3 — `simulate_sample` × 254 combos

```python
# copycat/backtest/pipeline.py:284-295
for row in rows:                       # 6,615
    bars = read_bars(...)              # ← 一次
    for key, combo, ticks in keyed:    # 254
        out = simulate_sample(bars, trig_idx, sample, t1o, combo, cfg, ticks)
```

`simulate_sample` 每次都:
- 重算 `_round_trip_cost(cfg, overnight)`(純 config 常數,254 × 6,615 = 168 萬次重算)
- 重算 `tick_size(trig.close)`(float↔milli 轉換 + zone 掃描)
- 重走一遍 `post = bars[trig_idx+1:]` 的 **list slice 複製**(254 次同樣的複製)
- 每個 combo 各自建一個 `deque(maxlen=10)`

實測 4.2 ms/樣本 → anchor θ 全量 **≈ 28 s**。這個數字比我預期低(Python 標準下算合格),
但 **252 個 combo 共享同一批 bars、同一個 entry 價、同一個 run_high 序列**,大量重複計算。

### 2.6 熱路徑 #4 — θ 曲線三層迴圈的重建浪費

```python
# copycat/backtest/pipeline.py:411-423(regime × rank × θ = 3 × 10 × 11 = 330 次)
for theta in cfg.theta_grid:
    t_rows = rows_by_theta[theta]
    t_test = [i for i, r in enumerate(t_rows)
              if str(r["date"]) >= cfg.split_date and _regime_filter(regime, r, cfg)]
    feat_rows = [_feature_row(t_rows[i]) for i in t_test]    # ← 每次全表重建
    mask = apply_rule(conds, feat_rows)
```

`_feature_row` 本身:

```python
# copycat/backtest/pipeline.py:343-345
def _feature_row(row):
    return {k: (v if isinstance(v, float) else None) for k, v in row.items() if k in FEATURE_NAMES}
```

`FEATURE_NAMES` 是 **list**(24 個),`k in FEATURE_NAMES` 是線性掃描。每列 24 key ×
最多 24 次比較 = 576 次;× 6,615 列 = 381 萬次;× 330 次重建 = **12.6 億次字串比較**。
實測 37.1 ms/次 × 330 = **12.2 s 純浪費**(結果完全相同,rank 與 conds 不影響 feat_rows)。

### 2.7 熱路徑 #5 — `DailyIndex.load`

```python
# copycat/data/daily.py:31-56
for r in csv.DictReader(fh):            # 1,037,564 次 __next__ = 3.07 s
    rows.setdefault(r["stock_id"], []).append(_DayRow(date=..., open=float(...), ...))
for lst in rows.values(): lst.sort(key=lambda x: x.date)
```

**4.0 s,每支 CLI 都要重付一次**(replay / tday-features / tday-search / fade-* 各一次;
`tday-features` + `tday-search` 連跑 = 付兩次)。2,044 支股票 × 平均 507 日 = ~104 萬列。

查詢端 `_find` 用 `bisect_left` 是對的,但 `_dates` 又額外複製一份 date list(記憶體 ×2)。
`adv20` / `ma` / `bb_width` / `pos_52w` 每次都重新 slice + sum —— `bb_width_pct` 更是
**在 120 日窗裡對每一天各算一次 `bb_width`(自己又 slice 20 日 + 兩次 sum)**,
即 120 × 20 = 2,400 次浮點運算 / 呼叫,而 `structural_features` 對每個 sample 都呼叫一次。

---

## 3. Findings(完整版)

### B12-01 `search.bit_indices` 吃掉 exhaustive_scan 的 63% —— 可用矩陣乘法整段消滅

- **位置**:`copycat/backtest/search.py:81-88`(`bit_indices`)、`:94-111`(`_evaluate`)、
  `:143-168`(`exhaustive_scan`)、`:186-190`(`ga_search._fit`)
- **證據**:
  ```
  67161  29.765s  bit_indices           ← tottime 63%
  56173966  5.406s  int.bit_length
  56238727  5.244s  list.append
  ```
  `exhaustive_scan` 實跑 27.3 s(無 profiler),`ga_search` 4.2 s/seed × 5 = 21 s。
  per (regime, anchor) ≈ 48 s;三個 regime ≈ **145 s**。
- **影響**:`tday-search` 的最大單一成本;`fade_pipeline` 的 walk-forward 每個 fold 都跑一次
  `_ga_candidates`(`fade_pipeline.py:190-199`),乘上 fold 數後成本更誇張。
- **修法**(numpy,收益 ~100x):
  1. 謂詞不存 Python bigint mask,改存 `np.ndarray[bool]`(366 × 3,179 = 1.16 MB,
     packbits 後 145 KB)。
  2. 預算 `pw = pnl * weights`(float64 3,179)、`w = weights`、`nz = weights > 0`。
  3. **exhaustive 1-2 條件全掃變成三個 matmul**:
     ```python
     M  = preds_bool.astype(np.float64)        # (P, N)
     ACC  = (M * pw) @ M.T                     # (P, P) 每對的 acc
     WSUM = (M * w ) @ M.T                     # (P, P) 每對的 wsum
     RAW  = (M * nz) @ M.T                     # (P, P) 每對的 raw
     EXP  = np.where((RAW >= raw_min) & (WSUM >= w_min), ACC / WSUM, PENALTY + RAW)
     ```
     366 × 3,179 × 366 = 4.26 億 FLOP × 3 → BLAS 在單核約 0.15 s、多核 < 0.05 s。
     對角線即單條件結果。**27.3 s → < 0.5 s**。
  4. GA 的 `_fit`:`np.logical_and.reduce(M[list(rule_idx)])` 再兩個 `dot` ≈ 5 µs/次,
     45,000 次/seed = 0.2 s。**21 s → 1 s**。
- **風險 / 契約**:
  - `_evaluate` 的加總順序改變 → 浮點結果**位元層可能不同**。design D11 的 determinism
    要求「同 seed 重跑 byte-identical」;跨版本 byte-identical 沒有承諾,但
    `docs/evidence/` 的既有報告數字會有 1e-15 級漂移,`rule_sort_key` 的 tie-break
    在極端 tie 下可能換序。**必須 user 拍板「允許重拍 evidence」或用
    `math.fsum` 等價路徑做一次 parity 驗證**。
  - `tests/backtest/test_search.py` 是行為鎖,改前先讀。
  - `bit_indices` 有 docstring 註明「pipeline 共用,勿另行實作」,pipeline.py:423/433 兩處
    呼叫端要一起改(改成直接拿 numpy index array)。
- **工作量**:M(search.py 單檔 ~250 LOC 重寫 + pipeline 兩處呼叫端)

### B12-02 `read_bars` = replay 的 55%;21,254 個小 JSON 檔是錯的儲存形狀

- **位置**:`copycat/data/store.py:42-60`;呼叫端 `replay/runner.py:93,109`、
  `backtest/pipeline.py:117,286`、`backtest/fade_pipeline.py:100`
- **證據**:
  ```
  22067  3.563s(tottime)  17.586s(cumtime)  read_bars
  28496  4.085s           json.decoder.raw_decode
  22068  0.462s           nt.stat          ← path.exists()
  17456  0.881s           _io.open
  ```
  完整 replay 25.3 s,其中 17.59 s 在 read_bars。`data/1k` = **294 MB / 21,254 檔**。
- **影響**:replay 55%;`tday-features` 的 per-sample 前置 + `_load_or_simulate` **各讀一次
  同一批 bars**(pipeline.py:117 與 :286);fade universe 更是先 `exists()` 再
  `read_bars()`(裡面再 `exists()` 一次)= 每檔 3 次 syscall(`fade_pipeline.py:96-101`)。
- **修法**(三段,由淺到深):
  1. **零相依即刻收**:`exists()` 換成 `try: open(...) except FileNotFoundError: return None`
     —— 省 22,067 次 stat ≈ 0.9 s(replay 3.5%)。
  2. **msgspec**(建議):`msgspec.json.Decoder(BarsPayload)` 直接解進 `msgspec.Struct`,
     跳過中間 dict/list,實測級距約 stdlib json 的 3–6 倍。`Bar1K` 改成 msgspec.Struct
     或保持 dataclass 但用 `Bar1K(*row)` positional(省 keyword 綁定)。
     預估 read_bars 17.6 s → 5–6 s。
  3. **columnar store**(正解):把 `data/1k` 換成 **per-stock parquet**
     (`data/1k_parquet/<stock_id>.parquet`,欄 = date, m, o,h,l,c, v, up, dn, unch)。
     21,254 檔 → 2,044 檔;294 MB JSON → 估 40–70 MB(zstd + delta)。
     用 `pyarrow.dataset` 或 `polars.scan_parquet` 一次讀進記憶體,replay 的
     `read_bars` 變成 dict 查表 + numpy slice → **17.6 s → < 1 s**。
     整份 1K 全量進記憶體約 5,700 萬 bar × 9 × 4 bytes(float32)= 2.0 GB —— 太大;
     **改 per-stock lazy + LRU,或只載 events 涉及的 stock-day 子集**(17,449 檔 ≈ 470 萬 bar
     = 170 MB float32,一次全載完全可行)。
- **風險 / 契約**:
  - `write_bars` 的遞增檢查(`store.py:17`)與 `atomic_write_text` 語意要在新格式重現。
  - `read_bars` 回傳 `list[Bar1K] | None`,`None` = 檔不存在 —— 這個三態被
    `runner.py:94`(`skip.append("missing_t_1k")`)、`pipeline.py:118`、
    `fade_pipeline.py:100` 當語意用,**不可退化成空 list**。
  - 換 columnar = **雙寫過渡期**(expand–contract):新舊並存 + 一支 parity 腳本逐檔比對
    `read_bars_json(x) == read_bars_parquet(x)`,全綠才切。
  - `copycat validate` golden gate 必須維持 42/42 PASS(數值逐字)。
- **工作量**:S(修法 1)/ M(修法 2)/ L(修法 3,含遷移腳本 + parity)

### B12-03 全庫零平行 —— 這些迴圈是 embarrassingly parallel,卻只用一顆核

- **位置**:全 `copycat/`。`grep -rn "multiprocessing|concurrent.futures|ProcessPool|ThreadPool" copycat/`
  **零命中**。
- **證據**:上面那條 grep 的輸出是空的(bench 已跑,無結果)。
  replay 的 11,048 事件彼此獨立;`_load_or_simulate` 的 6,615 × 254 彼此獨立;
  `run_search` 的 3 個 regime 彼此獨立;fade 的 walk-forward fold 彼此獨立。
- **影響**:一台 8–16 核的 Windows 機器,回測只用 1 核。
  `tday-search` 冷跑估 3.5–4 分鐘 → 8 核可壓到 ~40 s(在做完 B12-01/02 之前;做完之後
  平行化的邊際收益下降,但 simulate 那 28 s 仍值得拆)。
- **修法**:`concurrent.futures.ProcessPoolExecutor`(**stdlib,零新相依**)。
  切分點三個,由易到難:
  1. `run_search` 的 `for regime in ("all","momentum","low_base")` → 3 個 process(最簡單,
     每個 regime 的輸出互不依賴,`final_rules` 最後 concat 再依既有 key 排序)。
  2. `_load_or_simulate` 的 `for row in rows` → chunk 成 N 塊,每塊回 `(pnl, status)` 片段
     依 chunk index 拼回(**順序必須逐字保留 —— determinism D11「樣本序 = features CSV 序」**)。
  3. replay 的事件迴圈 → chunk;但 `out.write` 要改成收集後依序寫。
- **風險 / 契約**:
  - **Windows 是 spawn 不是 fork**:每個 worker 要重新 import + 重建 `DailyIndex`(4 s × N)。
    所以**必須把 DailyIndex 做成可序列化的輕量快照**(見 B12-07)或用 shared memory,
    否則平行化的開銷吃掉收益。
  - determinism:所有 reduce 必須依固定順序拼回,GA 的 `random.Random(seed)` 不可跨 process 共用。
  - `logger.info` 在 worker 裡的輸出順序會亂 —— 目前 `universe:` / `features 完成` 這些行
    沒有被測試斷言,但要確認。
- **工作量**:M(regime 層)/ L(sample 層 + DailyIndex 序列化)

### B12-04 實盤/回測不一致:`engine/` 只有 replay 在用,實盤是另一份鎖板定義

- **位置**:`copycat/engine/lock_quality.py`(全檔)vs `copycat/live/signal_state.py:813-822`
- **證據**:
  - `grep "from copycat.engine"` 的**唯一命中是 `replay/runner.py:14-15`**。
    server / live 全鏈零引用。
  - 回測的鎖板判定:
    ```python
    # engine/lock_quality.py:74-75
    def _at_limit(self, b: Bar1K) -> bool:
        return b.close >= self._limit - self._cfg.limit_eps   # float、1 分 K 收盤價
    ```
  - 實盤的鎖板判定:
    ```python
    # live/signal_state.py:813-818
    def _locked_up(self, price: int, ctx: TickContext) -> bool:
        if ctx.upper_milli is None or price != ctx.upper_milli or ctx.ask_limit_available:
            return False
        return ctx.bids0_is_market or ctx.best_bid_limit_milli == ctx.upper_milli
    ```
    整數毫元 + **五檔委賣是否還有限價量** + **買方是否已形成市價佇列**。
- **影響**:**這是「要下實單」最貴的一條**。回測說的「鎖死」是「這一分鐘收盤價 ≥ 漲停」,
  實盤說的「鎖死」是「成交在漲停價 且 賣方限價掛單已空 且 買方市價佇列成形」。
  兩者在「觸停但賣壓仍在」的 bar 上會給出相反答案 —— 而那正好是最需要分辨的情境
  (CLAUDE.md 0a 節:「鎖板品質 + T+1 開盤微結構」正是核心訊號)。
  於是:**`vol_after_lock_share` / `n_reopens` / `tier` 這些回測出來的分層,在實盤是另一個東西。**
- **這不是 bug,是資料硬限制**:CLAUDE.md §0a 明載「**硬限制:五檔委買賣深度不可回測**
  (TC4 tick 僅成交當下一檔 Bid/Ask)」。所以**兩份實作沒辦法直接合併**。
- **修法**(這是架構決策,不是重構,要 user 拍板):
  - **選項 A(誠實路線)**:在 `engine/lock_quality.py` 的 docstring 與
    `docs/strategy.md` 明確標註「本定義是簿深不可得下的**代理**,與 live `_locked_up`
    不等價」,並把差異量化 —— 用 TC4 tick 逐筆(有成交當下一檔 Bid/Ask)在同一批 stock-day
    上跑一次,測「bar-close 代理」vs「tick 近似簽名」的一致率。這個數字是所有回測結論的
    信心上界,目前**不存在**。
  - **選項 B(共用 seam)**:把兩者收斂成一個 `LockPredicate` Protocol,回測注入
    `BarCloseLockPredicate`、實盤注入 `BookSignatureLockPredicate`,狀態機
    (`_first_touch` / `_n_reopens` / `_run_start` 的轉移邏輯)共用一份。
    這樣至少「打開次數怎麼數」是同一份 code。
  - **選項 C(不建議)**:硬把 live 改成 bar-close 判定 —— 會丟掉 `_locked_up` 第三項
    刻意排除的「首攻吃光賣盤」誤判(該處 docstring 已寫明設計意圖)。
- **風險 / 契約**:動 `live/signal_state.py` 會踩 CLAUDE.md §4 的訊號列契約
  (`kind` 值域、`limit_lock`/`limit_open` 前後端同表);動 `engine/` 會讓
  `copycat validate` 的 42 條 golden 全面重拍。**選項 A 零風險,建議先做 A 拿到數字再談 B。**
- **工作量**:S(A 的文件)+ M(A 的量化腳本)/ L(B)

### B12-05 outcome cache:三重失效機制正確,但粒度太粗 + 單檔 54 MB

- **位置**:`copycat/backtest/pipeline.py:245-308`、`config.py:105-137`(`_SIM_FIELDS`)
- **證據**:
  ```python
  # pipeline.py:256-265
  if path.exists():
      payload = json.loads(path.read_text(encoding="utf-8"))
      if (payload.get("_cache_version") == _CACHE_VERSION
          and payload.get("sim_hash") == sim_hash          # 18 個 sim 欄位的 sha256[:12]
          and payload.get("rows_hash") == rows_hash        # (stock,date,trig_idx) 序列的 sha256[:16]
          and payload.get("with_grid") == with_grid):
          return payload
  ```
  `out/tday_ga/outcomes_theta0.080.json` = **54,239,011 bytes**;非 anchor 428 KB(127 倍差,
  正好對應 254 key vs 2 key)。
- **命中成本**:`json.loads` 54 MB = **0.49 s**(read 0.06 s)。× 11 θ ≈ 1 s。**命中很便宜。**
- **未命中成本**:anchor θ 全重算 ≈ 28 s sim + 6 s IO;非 anchor × 10 ≈ 每個 ~0.3 s。
  總重算 ≈ 40 s。
- **問題(不是慢,是粒度)**:`_SIM_FIELDS` 含 `s1_stall_bars` / `s3_trail` / `s4_fixed` 等
  **網格定義**。改網格裡任何一個值(例如 `s3_trail` 加一個 0.025)→ sim_hash 變 →
  **254 個 combo 全部重算**,即使其中 253 個的參數一字沒動。
  正確的粒度是 **per-combo key**:cache 應該是 `{combo_id: (pnl, status)}`,
  失效只作廢 combo_id 不在新網格裡的、或成本欄位(fee/tax/slippage/eps)變動時全作廢。
- **另一個問題**:`_rows_hash`(pipeline.py:235-242)在函式內 `import hashlib`,
  且對 6,615 個 tuple 做 `json.dumps(sort_keys=True)` 再 sha256 —— 每 θ 一次 × 11。
  小(< 0.1 s)但沒必要,`hashlib` 應提到模組層。
- **修法**:
  1. cache payload 改 `{"combos": {combo_id: {"pnl": [...], "status": [...]}}}`,
     失效判準拆成 `cost_hash`(fee/tax/slippage/eps/t1300_min_idx)+ per-combo 存在性。
     `_CACHE_VERSION` bump 到 2。
  2. 54 MB JSON 改 **npz / parquet**:pnl 是 254 × 6,615 float64 = 13.4 MB(numpy 原生),
     status 是 254 × 6,615 的 8 值列舉 → 存 uint8 = 1.7 MB。
     **54 MB → ~15 MB,載入 0.49 s → ~0.02 s。**
- **風險 / 契約**:`_CACHE_VERSION` 是既有慣例(CLAUDE.md §4「Cache version bump」),
  bump 即作廢舊 cache,安全。但 `atomic_write_text` 只有 text 版,npz 要走
  `atomic_write_bytes`(已存在,`fileio.py`)。
- **工作量**:M

### B12-06 θ 曲線迴圈重建 `_feature_row` 330 次 = 12.2 s 純浪費

- **位置**:`copycat/backtest/pipeline.py:411-423`(迴圈)、`:343-345`(`_feature_row`)、
  `:78`(`FEATURE_NAMES` 是 list)
- **證據**:
  ```
  _feature_row over 6615 rows: 37.1ms  -> x330 rebuilds = 12.2s
  _regime_filter scan: 2.2ms x330 = 0.7s
  FEATURE_NAMES is list 24
  ```
  迴圈結構:`for regime (3) → for anchor (1) → for rank (10) → for theta (11)` = 330,
  而 `t_test` 與 `feat_rows` **只依賴 (regime, theta)**,與 rank 完全無關 → 應該只算 33 次。
- **影響**:`tday-search` 裡 12.9 s 的純浪費(佔搜索段 ~8%)。
- **修法**(零風險、零行為改動、零相依):
  1. `FEATURE_NAMES` 旁邊加 `_FEATURE_NAME_SET = frozenset(FEATURE_NAMES)`,
     `_feature_row` 用它 —— 24 次線性掃描 → 1 次 hash。單這一步約省 60%。
  2. 把 `t_test` / `feat_rows` 提到 `for rank` 迴圈**之外**,以 `(regime, theta)` 為 key
     預先算好 memo dict。330 → 33 次。
  - 兩步合計 **12.2 s → ~0.5 s**。
- **風險**:無。輸出逐字相同(同樣的 row、同樣的順序、同樣的 dict 內容)。
  `tests/backtest/test_pipeline.py` 應該直接綠。
- **工作量**:S

### B12-07 `DailyIndex.load` 4 s,每支 CLI 重付一次,且查詢端全是重算

- **位置**:`copycat/data/daily.py:31-56`(load)、`:85-91`(adv20)、`:148-181`(ma/bb_width/bb_width_pct)、`:183-195`(pos_52w)
- **證據**:
  - load = 4.02 s 獨立量測;cProfile 下 7.00 s。`csv.__next__` 1,037,564 次 / 3.07 s。
  - `bb_width_pct(stock, date, n=20, k=2.0, window=120)`:
    ```python
    for j in range(i - window + 1, i + 1):        # 120 次
        w = self.bb_width(stock_id, lst[j].date, n, k)   # 內含 _find(bisect) + 20 日 slice + 兩次 sum
    ```
    = 120 × (1 bisect + 20 日窗兩次掃描) ≈ 2,400 次浮點 + 120 次 bisect,**每個 sample 呼叫一次**
    (`features.py:153`)。
  - `pos_52w` 每次 slice 250 日 list 再 `min`/`max` 兩次全掃。
- **影響**:
  - 固定成本 4 s × 每支 CLI;`tday-features` + `tday-search` 連跑 = 8 s。
  - 平行化(B12-03)時會變成 4 s × N workers(Windows spawn)—— **這是平行化的前置障礙**。
  - `structural_features` 在 `run_features` 裡對每個 universe sample 各算一次(見 pipeline.py:123)。
- **修法**:
  1. **立即可做(零相依)**:`csv.DictReader` 換 `csv.reader` + 固定欄位 index
     —— DictReader 每列建一個 dict,1.04M 個 dict 是主要成本。實測級距約省 50–60%。
  2. **快取**:load 完存一份 `data/daily/prices.index.pickle`(或 npz),mtime 比對決定重建。
     4 s → ~0.3 s,且 worker process 可直接載。
  3. **numpy/polars**:`_DayRow` list-of-struct 換成 per-stock 的 numpy 欄陣列
     (date 用 int32 YYYYMMDD、OHLCV float64)。`adv20` / `ma` 變 `arr[i-19:i+1].mean()`;
     `bb_width_pct` 用 **sliding_window_view + 一次向量化**,2,400 次 → 一次 BLAS。
     `pos_52w` 用 `np.maximum.accumulate` 預算。
     這一塊是 polars 的甜蜜點(groupby stock + rolling)。
- **風險 / 契約**:
  - `ref_prev_close` 的 **row-level `spread is None` fallback 語意**(daily.py:119-136)
    很細:`None` = 舊資料 → 退回前一日 close;`0.0` 是合法平盤值。numpy 化時
    `spread` 欄必須用 **masked / 獨立的 has_spread bool 欄**,不能用 NaN 混淆
    (`float('nan')` 與 `0.0` 的區分要留住)。這一條漂掉 = 除權息日的漲停價算錯,
    `universe.build_universe` 的 `limit_mismatch` 剔除計數會靜默變動。
  - `bb_width` 用 **母體 σ**(`/n` 不是 `/(n-1)`)—— numpy 要 `ddof=0`。
  - 所有結果進 `docs/evidence/` golden 與 `copycat validate`,浮點漂移要過 parity。
- **工作量**:S(修法 1)/ M(修法 2)/ L(修法 3)

### B12-08 `read_bars` 的 `exists()` + `read_text()` 雙 syscall

- **位置**:`copycat/data/store.py:43-46`;同病 `fade_pipeline.py:96-101`(那裡是三次)
- **證據**:`22068 0.462s nt.stat`(cumtime 0.913 s)/ `17456 0.881s _io.open`
- **影響**:replay 0.91 s(3.6%)。fade universe 建構更糟。
- **修法**:
  ```python
  try:
      with path.open("rb") as fh: raw = fh.read()
  except FileNotFoundError:
      return None
  ```
  順便 `json.loads(bytes)` 比 `read_text()` 再 loads 少一次 decode(stdlib json 吃 bytes)。
- **風險**:`None` 的語意要維持(見 B12-02 契約)。`PermissionError` 不可吞
  (CLAUDE.md 鐵則 E:不懂的 error 不要 catch)。
- **工作量**:S

### B12-09 `simulate_sample`:254 combos 重走同一批 bars,常數重算 168 萬次

- **位置**:`copycat/backtest/simulate.py:86-185`;呼叫端 `pipeline.py:292-295`
- **證據**:
  - `_round_trip_cost(cfg, overnight)`(simulate.py:81-83)只依賴 cfg 兩個 bool 分支,
    卻在 `_pnl` 每次呼叫時重算:`fee_rate * (1-discount) * 2 + tax`。
    1,680,210 次 simulate × 每次至少 1 次 = 168 萬次重算。
  - `entry = min(trig.close + slippage_ticks * tick_size(trig.close), limit)`(:107)
    —— `tick_size` 走 `round(price*1000)` + zone 線性掃描,**254 個 combo 對同一個
    trig.close 算 254 次**(只有 2 種 slippage_ticks)。
  - `post = bars[trig_idx + 1:]`(:108)—— **254 次 list slice 複製**,每次平均 ~150 個
    Bar1K 參考。
  - 實測 4.2 ms/樣本(254 combos)→ 16.5 µs/combo,~150 bar → 0.11 µs/bar。
- **影響**:anchor θ ≈ 28 s。省掉上述重複約可拿 20–30%(→ ~20 s)。
- **修法**:
  1. per-sample 預算一次:`cost_intraday` / `cost_overnight` / `entry_price[ticks]` /
     `post`(共用同一個 list 物件,不複製 —— `post` 只讀)。
  2. **真正的解**:numpy 化 —— 把 `post` 的 `low/high/close/up_volume/down_volume/m`
     取成 6 條 ndarray,S3/S4 的觸發點用 `np.argmax(low < level)`、
     S2 的 swing low 用預算的 `np.minimum.accumulate`。
     但 S1 的 stall 計數與 D9 的「鎖死 bar 凍結」語意是**序列相依**的狀態機,
     不能直接向量化 —— 只能把「非鎖死 bar 的遮罩」先算出來,再在壓縮後的子序列上跑迴圈。
     預期 2–4x,**不是 100x**。
  3. 若做了 B12-03 的 process 平行,28 s / 8 核 ≈ 4 s,**收益比 numpy 化更大且風險更低**。
- **風險 / 契約**:
  - simulate.py 的 docstring 寫死了時序語意(同 bar 優先序:停損 > 時間出場 > 留倉;
    多重停損取最差成交價;13:00 檢查點 one-shot)。任何重寫**必須逐條保留**,
    `tests/backtest/test_simulate.py` 是行為鎖。
  - `LOCKABLE_GROUPS`(`universe.py:18`)與 `closed_at_limit != lockable` 的 D7 雙保險
    (simulate.py:179)是**資料矛盾偵測**,不是效能路徑,不可簡化掉。
- **工作量**:S(修法 1)/ L(修法 2)/ M(修法 3,見 B12-03)

### B12-10 fade walk-forward 的 `mask & (1 << i)` 是 O(n²) bigint

- **位置**:`copycat/backtest/fade_pipeline.py:234-238`
- **證據**:
  ```python
  mask = apply_rule(conds, all_feat)
  val_t = [Trade(date=all_dates[i], stock_id="", pnl=all_pnl[i])
           for i in val_ids if mask & (1 << i)]
  ```
  `1 << i` 對 i ~ 數千是一個 n bit 的大整數配置,`mask & ...` 又是 O(n/64)。
  迴圈跑 `len(val_ids)` 次 → O(n²/64)。外層還有 `for rule in candidates`(30 條)
  × `for test_start in cfg.wf_test_starts`(fold 數)。
- **影響**:fade walk-forward(離線研究批次)。未實測(需要 `data/daytrade` 回補才跑得動),
  但結構上明確是二次式。
- **修法**:`hits = set(bit_indices(mask))` 一次(或做完 B12-01 後直接拿 numpy bool array
  做 `np.intersect1d` / fancy index)。
- **風險**:低,`bit_indices` 已是現成共用 helper。
- **工作量**:S

### B12-11 四份分位數實作並存;每次都 `sorted()` 全複製

- **位置**:`copycat/backtest/quantiles.py:13,33`(round / trunc 兩份)、
  `copycat/backtest/search.py:33-36`(`_quantile`,nearest-rank 第三份)、
  `copycat/replay/report.py:20-22`(`med`,第四份)
- **證據**:
  ```python
  # quantiles.py docstring(user 2026-07-20 拍板)
  # round 版:idx = round(q*(n-1))  — fade_anatomy / fade_cells 系
  # truncate 版:idx = int(p*n)     — fade_diagnose 系
  # 統一演算法會改報告數字 = 行為改動,須另開行為輪,不得在 refactor 內做。
  ```
  ```python
  # replay/report.py:20-22 —— 第四份,而且不是標準中位數
  def med(xs): s = sorted(xs); return s[len(s)//2] if s else None
  ```
  `quantiles_round` 對同一份 values 呼叫 `quantile_round` 四次 → **sorted() 四次**。
- **影響**:效能上小(report 層 n ≤ 幾千)。**但 `med` 的「偶數不取平均」是
  `copycat validate` 的 42 條 golden 的一部分**。
- **修法**:
  - 效能:`quantiles_round` 內部先 sort 一次再取四個 index(3 次多餘 sort 省掉)。零行為改動。
  - **不要統一演算法** —— user 已拍板,且 `med` 換成 `statistics.median` 會讓
    golden 全紅(偶數樣本取平均 vs 取上位)。
- **風險**:`quantiles_round` 的重構要確認 `quantile_round(values,q)` 與
  `quantile_round(sorted_values,q)` 等價(sorted 冪等,是等價的)。
- **工作量**:S

### B12-12 `Bar1K` 596 萬次 dataclass 建構 = 3.56 s

- **位置**:`copycat/data/models.py:8-19`、`copycat/data/store.py:47-59`
- **證據**:`22067 3.563s(tottime) read_bars` —— 扣掉 json(4.09 s 是獨立的 raw_decode)
  與檔案讀取(0.88 s),剩下的 tottime 主要就是 list comprehension + 9 個 keyword 綁定。
- **影響**:replay ~11%;每跑一次 tday-features 再付一次。
- **修法**:
  - **零相依**:`Bar1K(*r)` positional(欄位順序與 store 寫入順序已一致 store.py:23-33),
    省 keyword dict 建構。但 `m=int(r[0])` 的 int 轉換要保留(JSON 讀回來已是 int,
    這個 `int()` 是防禦性的,量測後可考慮移除 —— 但**寫入端保證是 int** 才能移)。
  - **numpy**:整檔 bars 變 `np.ndarray`(shape (n,9), float64)+ 一個 `m` 的 int32 欄。
    `LockTracker.feed` 需要 `.close` `.high` `.volume` `.m` —— 改成索引存取即可,
    但那會讓 `engine/` 的可讀性下降(它現在很乾淨)。**建議只在 backtest 路徑用 numpy 版,
    replay/engine 保持 Bar1K**(反正 engine 只佔 2.6 s / 31.8 s)。
- **風險**:`Bar1K` 是 `frozen=True, slots=True`,被 `engine/` 與四個 backtest 模組共用。
  改成 positional 建構是零行為改動;改成 ndarray 是跨模組介面改動(L)。
- **工作量**:S(positional)/ L(ndarray)

### B12-13 replay 寫完 events.jsonl 又整份讀回來;彙總對同一份 list 反覆全掃

- **位置**:`replay/runner.py:171`(`write_summary(run_dir)`)、
  `replay/report.py:15-17`(`load_events` 整檔 splitlines + 11,048 次 json.loads)、
  `:34-119`(五個 `agg_*`,每個 bucket 一次 list comprehension 全掃)
- **證據**:
  ```
  1  0.526s  write_summary
  1  0.407s  load_events        ← 讀回剛寫的 8.45 MB
  ```
  `agg_lock_buckets` 對 5 個 bucket 各掃一次 `full`;`agg_gap_buckets` 6 次;
  `agg_queue` 3 次;`agg_auction` 3 次 × 2 basis;× 2 cohort = **~40 次全表掃描**。
- **影響**:0.53 s / 25.3 s(2%)。**小,但結構上是「寫檔→讀檔→重算」的反模式**:
  runner 手上本來就有全部資料。
- **修法**:`write_summary(run_dir, events=...)` 加一個可選參數,runner 直接把 list 傳進去
  (`load_events` 保留給 validate / compare 的獨立呼叫)。
  `agg_*` 的多次全掃改成一次 `defaultdict(list)` 分桶。
- **風險**:`validate.run_validate` 與 `compare.write_compare` 都吃 `load_events(Path)`,
  介面不能拿掉,只能加可選參數。
- **工作量**:S

### B12-14 golden gate(`copycat validate`)本體只要 0.64 s —— 慢的是前置的兩次 replay

- **位置**:`copycat/replay/validate.py`(全檔)、CLAUDE.md §1 gate 表
- **證據**:
  ```
  run_validate(incl reload both): 0.64s checks=42 fail=0
  完整 replay(five_tigers): 25.3s
  ```
  CLAUDE.md:「validate 需先跑過 four/five 兩份 replay」→ **完整 gate = 25.3 × 2 + 0.64 ≈ 51 s**。
  `pytest tests/backtest tests/engine tests/replay tests/data` = **352 passed / 10.19 s**(fixture 驅動,不碰 `data/`)。
- **影響**:開發迴圈裡 51 s 的固定成本。做完 B12-02 後 replay → ~5 s,gate → ~11 s。
- **這裡的正確判斷是「不要動 validate 本身」**:
  - 42 條 golden 常數(`_G_LOCK` / `_G_GAP` / `_G_AUCTION`)與容忍值(±5% / ±0.5pp / ±1pp / ±3pp)
    是 characterization 錨點,出處鏈寫在 docstring 裡(intraday_playbook §2d /
    open_gap_definition §2-3 / strategy.md §5),**動它就是動行為合約**。
  - `_seed_only` 的 fail-closed(未知 source 一律排除,validate.py:64-66)是刻意的。
  - 0.64 s 已經夠快,向量化它是過度工程。
- **工作量**:—(不做)

### B12-15 零觀測性:沒有任何分階段計時,`tday-search` 慢了查不出哪一步

- **位置**:`pipeline.py:188`(`logger.info("features 完成 → %s", out_dir)`)、
  `:265`(`logger.info("outcome cache 不符(%s)→ 重算")`)、`runner.py:172`
- **證據**:整個 `run_search`(181 行、跑數分鐘)**只有 cache miss 一行 log**,
  沒有任何 elapsed。我為了寫這份報告必須自己掛 cProfile。
- **影響**:量化系統的基本衛生。改了 numpy / 平行化之後,**沒有 before/after 的比較基準**
  就無法證明加速(CLAUDE.md 鐵則 D:完成必附證據 / 量測對照)。
- **修法**:加一個 `_stage(name)` context manager,`logger.info("[%s] %.2fs", name, dt)`,
  掛在:`DailyIndex.load` / `build_universe` / per-theta features / `_load_or_simulate`
  (分 cache-hit / miss)/ `build_predicates` / `exhaustive_scan` / `ga_search` /
  θ 曲線 / `write_report`。輸出同時寫一份 `out/<dir>/timings.json`。
- **風險 / 契約**:**determinism D11 明文「輸出無 timestamp」** —— timings 必須寫**獨立檔**,
  不可進 `rules_final.json` 或報告 md,否則 `docs/evidence/` 的報告每次都 diff。
- **工作量**:S

### B12-16 量化缺口:回測沒有成交/延遲模型,`slippage_ticks` 是常數

- **位置**:`simulate.py:107`(`entry = min(trig.close + slippage_ticks * tick_size(...), limit)`)、
  `config.py:41-42`(`slippage_ticks: int = 1` / `stress_slippage_ticks: int = 2`)
- **證據**:整個模擬器的成交假設 = 「觸發 bar 收盤價 + N tick,cap 在漲停價」。
  `excluded_unfillable`(:105-110)是唯一的成交可行性判定,判準是「bar 的 low ≥ limit」。
  **沒有**:委託延遲、部分成交、排隊位置、taker/maker、下單量對簿的衝擊。
- **影響**:**要下實單的系統,這是最大的模型風險**。CLAUDE.md §0a 已載明五檔深度不可回測,
  所以「排隊位置」在現有資料下無解;但**延遲**與**部分成交**是可以建模的:
  TC4 tick 有時間戳,群益送單的 reply 有回報時間(`capital/reply.py`),
  真實往返可以量出來當 `latency_ms` 分佈。
- **修法**(這是 spec 級決策,不是重構):
  - 短期:把 `slippage_ticks` 常數換成**依 `trig` 當下的量能分桶**的查表
    (例如 `max_minvol_x` 高的樣本吃更多滑價)—— 但這需要先有真實對照資料。
  - 中期:`docs/evidence/` 補一份「實單成交 vs 回測假設」對照 —— 群益 audit jsonl
    (`data/audit/capital-YYYYMMDD.jsonl`)已經在寫,這是現成的真值來源。
- **風險**:動 `slippage_ticks` 語意 = 動 `_SIM_FIELDS` = 全 cache 作廢 + evidence 重拍。
- **工作量**:L(要先有量測資料)

### B12-17 `run_search` 的 rank 迴圈重算 `stop_duel`(252 combo × 10 rank × 3 regime)

- **位置**:`pipeline.py:443-449`
- **證據**:
  ```python
  for key in oc["combo_keys"]:          # 254
      trades_c = _trades_for(rows, hits_a, pnl_map[key], status_map[key])
      s = weighted_stats(trades_c)
      duel[key] = {**s, "mdd": max_drawdown(trades_c)}    # ← max_drawdown 內含 sorted()
  ```
  `max_drawdown`(stats.py:54-63)每次 `sorted(trades, key=lambda t: (t.date, t.stock_id))`。
  252 × 30(rank × regime)= 7,560 次 weighted_stats + 7,560 次 sorted。
  而 `result["stop_duel"]` **最後只用 `final_rules[0]["stop_duel"]`**(pipeline.py:513)—— 其餘 29 份算了丟掉。
- **影響**:未獨立量測,估 5–15 s。但「算了丟掉」是確定的浪費。
- **修法**:只在 `rank == 0` 展開 stop_duel(與 `theta_curves` 的 `if rank == 0` 同一個判斷,:474)。
  **注意**:`record["stop_duel"] = duel` 進了 `rules_final.json`,拿掉會改變 JSON 內容 →
  這是**行為改動**,要 user 拍板(或存成 `null` 保留 key)。
- **風險**:`rules_final.json` 是 evidence 產物,結構改動要確認沒有下游讀者。
- **工作量**:S(但要拍板)

### B12-18 `LockTracker` / `T1Tracker` 的 feed 迴圈:夠快,但 `_bars` 全量保留是設計債

- **位置**:`engine/lock_quality.py:68-93`、`engine/t1_open.py:73-83`
- **證據**:
  ```
  1727730  1.023s(tottime) 1.533s(cumtime)  LockTracker.feed     → 0.88 µs/bar
  2943270  0.716s          1.040s           T1Tracker.feed       → 0.35 µs/bar
  ```
  兩者合計 2.57 s / 31.8 s = **8%**。
- **判斷:效能上不要動。** 0.88 µs/bar 在純 Python 是合格的,向量化它只能省 2 s,
  卻會犧牲「逐 bar 餵入、盤中可查且不回改」這個為**實盤即時**設計的介面
  (`first_touch_idx` / `n_reopens` / `current_lock_start` 三個 property 就是給盤中用的)。
- **但有一個真的設計債**:`self._bars: list[Bar1K]` 保留全日所有 bar。
  - 實盤如果真的用它(目前沒有,見 B12-04),一天 50 檔 × 270 bar = 13,500 個物件,無妨;
  - 但 `finalize()` 的三次 O(n) 掃描(day_vol / after_share / violent window)
    **可以在 feed 時增量維護**,讓 tracker 變成 O(1) 記憶體。
  - 現在的 `feed()` 已經在做增量維護(`_first_touch` / `_n_reopens` / `_run_start`),
    **只差 `day_vol` 與 `suffix_vol`** —— 但 `vol_after_lock_share` 的分子是「從最終鎖點起」的
    累積量,而最終鎖點會因為「打開又鎖」而後移,所以需要「當前 run 起點以來的累積量」
    (可增量)+ 「全日累積量」(可增量)。violent window 需要保留最近
    `violent_pull_window` 根的 open —— 一個 `deque(maxlen=10)` 就夠。
  - 做完之後 tracker 是 **O(1) 記憶體、全增量**,才真的可以掛在實盤 tick 流上。
- **風險 / 契約**:`copycat validate` 的 42 條 golden 直接依賴這兩個 finalize 的輸出。
  增量化必須**數值逐字相同**(`sum` 的加總順序:目前是 `sum(b.volume for b in self._bars)`
  由前往後,增量維護也是由前往後 → 順序一致,float 結果相同)。
  `tests/engine/test_lock_quality.py` / `test_t1_open.py` 是行為鎖。
- **工作量**:M

### B12-19 `_load_or_simulate` 重讀 bars(與 `run_features` 重複)

- **位置**:`pipeline.py:117`(run_features 讀一次)vs `pipeline.py:286`(_load_or_simulate 再讀一次)
- **證據**:兩支是不同 CLI 動詞(`tday-features` / `tday-search`),所以跨 process 不能共用記憶體。
  但 **`_load_or_simulate` 在 11 個 θ 的迴圈裡各讀一次同一批 bars**
  (pipeline.py:355-361 的 dict comprehension → 每個 θ 一次 `_load_or_simulate`)。
  cache 命中時不讀;**cache 全 miss 時 = 11 × 6,615 次 read_bars ≈ 11 × 6 s = 66 s**。
- **影響**:cache 全 miss 的冷跑(例如改了 `fee_rate`)多付 ~60 s。
- **修法**:`_load_or_simulate` 的 bars 讀取提到 `run_search` 層,做一個
  `{(stock_id, date): bars}` 的共用快取(17,449 檔 × 270 bar 的 Bar1K ≈ 記憶體 1–2 GB,
  **太大**)→ 改成「先算出 11 個 θ 的 rows 聯集的 (stock,date) 集合,
  按 (stock,date) 外層迴圈、θ 內層」的迴圈反轉。或做完 B12-02 的 columnar 後這問題自動消失。
- **風險**:迴圈反轉會改變 `pnl` / `status` list 的填入順序 —— **必須依 rows 順序重組**
  (determinism D11「樣本序 = features CSV 序」)。
- **工作量**:M

### B12-20 `fade_*` 家族(11 檔 / 7,300 LOC)未納入本次深掃,但共用同一底座

- **位置**:`backtest/fade_cells.py`(2,007 LOC)、`fade_pipeline.py`(735)、
  `fade_anatomy.py`(594)、`fade_entry_anatomy.py`(576)、`fade_config.py`(560)、
  `fade_diagnose.py`(538)、`fade_simulate.py`(395)、`fade_tp.py`(379)、
  `fade_report.py`(267)、`fade_features.py`(262)、`fade_arms.py`(247)、`fade_vote.py`(154)
- **證據**:`wc -l` 顯示 fade 系 = **6,900 LOC**,佔 `backtest/` 的 82%。
  它們 import 的是**同一份** `search.py` / `stats.py` / `features.py` / `data.store` / `data.daily`。
  `fade_pipeline` docstring:「兩階段 combo:baseline ranking → top3 S1 → 最終 **4,640 組**」
  —— 是 tday 252 組的 18 倍。
- **影響**:B12-01(bit_indices)/ B12-02(read_bars)/ B12-07(DailyIndex)的收益
  **在 fade 上放大 10–20 倍**。反過來說,任何底座上的行為改動也會讓 fade 的 evidence 全紅。
- **建議**:先做底座(search / store / daily),fade 自動受惠,**不要單獨為 fade 動手**。
  `fade_cells.py` 2,007 LOC 單檔是另一個層次的問題(可讀性/可維護性),不在效能範疇。
- **工作量**:—(觀察項)

---

## 4. 工具選型:建議與取捨

### 4.1 numpy —— **建議導入**(放 `[backtest]` extras)

| 項 | 內容 |
|---|---|
| 用在哪 | `search.py` 謂詞矩陣與 fitness(B12-01,**最大收益**)、`data/daily.py` 的 rolling 統計(B12-07)、`pipeline` 的 outcome 陣列(B12-05) |
| 預期收益 | exhaustive_scan **27.3 s → < 0.5 s**;GA 21 s → ~1 s;bb_width_pct 2,400 次浮點 → 一次 BLAS |
| 代價 | ① runtime 相依破功?**不會** —— backtest 是 offline CLI,放 `[backtest]` extras,`live/` `server/` 零 import。pyproject 的 `dependencies = []` 維持不變。② Windows wheel 成熟,零編譯問題。③ **浮點加總順序改變** → determinism D11 與 `docs/evidence/` golden 需要 parity 驗證或重拍 |
| 判定 | **建議導入**,但必須先做一支 parity 腳本:同一份 features + outcomes,新舊兩條路徑各跑一次 `exhaustive_scan`,斷言 top-200 的 conditions 集合與 fitness 在 1e-12 內相等 |

### 4.2 polars —— **有條件導入**

| 項 | 內容 |
|---|---|
| 用在哪 | `data/daily.py`(1.04M 列 CSV → DataFrame,groupby stock + `rolling_mean` / `rolling_std`);`backtest` 的 features CSV 讀寫 |
| 預期收益 | DailyIndex.load **4.0 s → ~0.3 s**;`bb_width_pct` / `pos_52w` / `adv20` 全部變 rolling expression |
| 代價 | ① 相依較重(~30 MB wheel)。② `ref_prev_close` 的 `spread is None` vs `0.0` 三態語意在 DataFrame 裡要用獨立 bool 欄表達,**不能靠 null**(見 B12-07 風險)。③ `DailyIndex` 的 13 個查詢方法要全部重寫,是 L 級工作。④ 若已導入 numpy,polars 的邊際收益只在「load + rolling」 |
| 判定 | **有條件導入** —— 若同時要做 B12-02 的 parquet columnar store,polars(或 pyarrow)本來就要裝,那就一起用;若只做 numpy,`DailyIndex` 用 numpy 手寫 rolling 也夠(收益 8 成) |

### 4.3 pyarrow / parquet —— **建議導入**(若要做 B12-02 修法 3)

| 項 | 內容 |
|---|---|
| 用在哪 | `data/1k` 的 21,254 個 JSON → per-stock parquet;`outcomes_theta*.json` 54 MB → parquet/npz |
| 預期收益 | replay read_bars **17.6 s → < 1 s**;磁碟 294 MB → ~50 MB;outcome cache 54 MB → ~15 MB,載入 0.49 s → 0.02 s |
| 代價 | ① 資料遷移是 L(要寫遷移腳本 + 雙寫過渡 + 逐檔 parity)。② `write_bars` 的 atomic 語意要在 parquet 上重現(寫 tmp + os.replace 仍可用)。③ `data/1k` 是 gitignored 的本機資料,遷移失敗可重跑 `backfill-tc4` 重建 —— **風險比看起來低** |
| 判定 | **建議導入**,但排在 numpy 之後(numpy 的收益/工作量比更好) |

### 4.4 msgspec —— **建議導入**(B12-02 的中間路線)

| 項 | 內容 |
|---|---|
| 用在哪 | `data/store.read_bars`(JSON → Struct,跳過中間 dict);`replay/report.load_events`(11,048 列 jsonl);`pipeline._load_or_simulate` 的 54 MB payload |
| 預期收益 | json decode 4.09 s → ~0.8 s;Bar1K 建構 3.56 s → 併進 decode。replay 25.3 s → ~16 s,**不需要改資料格式** |
| 代價 | ① 新相依(但極輕,純 Rust wheel,Windows 有 wheel)。② `Bar1K` 若改成 `msgspec.Struct`,`engine/` 與四個 backtest 模組的 import 都要跟(但 API 相容,frozen struct 也支援 slots)。③ 與 parquet 路線**部分重疊** —— 做了 parquet 就不太需要 msgspec |
| 判定 | **建議導入(若不做 parquet)**;做 parquet 則降為「有條件」(只用在 events.jsonl / outcomes) |

### 4.5 `concurrent.futures.ProcessPoolExecutor` —— **建議導入(stdlib,零相依)**

| 項 | 內容 |
|---|---|
| 用在哪 | `run_search` 的 regime 迴圈;`_load_or_simulate` 的 sample chunk;replay 的事件 chunk;fade 的 fold |
| 預期收益 | 8 核 → simulate 28 s → ~4 s;replay 25 s → ~5 s(但 read_bars 是 IO,收益看磁碟);search 145 s → ~50 s(3 regime 只能 3 核) |
| 代價 | ① **Windows 是 spawn**:每個 worker 重新 import + 重建 DailyIndex(4 s × N)→ 必須先做 B12-07 的 DailyIndex 快照化,否則得不償失。② determinism:reduce 順序必須固定。③ GA 的 `random.Random(seed)` 不可跨 process 共用狀態(現在也沒有,每次 `ga_search` 自己 new 一個,安全) |
| 判定 | **建議導入**,但**排在 B12-01 / B12-07 之後** —— 先把單核做快,再平行;否則是在平行化一個本來就該消失的迴圈 |

### 4.6 numba —— **不建議**

理由:① 需要 LLVM 工具鏈,Windows 上的安裝/升級是維護負擔;② 本區塊的熱點
(`bit_indices`、`read_bars`)用 numpy/columnar 就解掉了,沒有剩下「非向量化的數值迴圈」
值得 JIT;③ 唯一可能的候選是 `simulate_sample` 的序列相依狀態機,但那裡做 process 平行
(B12-03)的收益相近而風險低得多。**不要為了 2–4x 引入編譯相依。**

### 4.7 duckdb —— **不建議(現階段)**

理由:events.csv 11,048 列、features CSV 6,615 列 —— 這個量級用 Python list 就夠,
`_read_features` 實測 0.09 s。引入 SQL 層是為了解決不存在的問題。
**若將來 events 池長到百萬級**(全市場掃描)再談。

### 4.8 orjson —— **有條件**(msgspec 的次選)

比 stdlib json 快 2–4x,但 msgspec 能直接解成 Struct(省掉 dict 中間層),
在 `read_bars` 這種「decode 完馬上建物件」的場景 msgspec 明顯更好。
`orjson` 的優勢在**寫**(`json.dumps` 的 replay events.jsonl 11,048 次),
但那只佔 replay 不到 1 s。**若已選 msgspec,不要再加 orjson。**

### 4.9 dev 量測工具 —— **建議導入 `[dev]`**

- `py-spy`(取樣 profiler,不需改 code,可 attach 到跑著的 process)
- `line_profiler`(逐行,驗證 B12-01 / B12-06 的修法)
- `pytest-benchmark`(把 B12 的 benchmark 變成可回歸的測試)

---

## 5. 不要動的地方(這同樣有價值)

| 位置 | 為什麼不要動 |
|---|---|
| **`replay/validate.py` 全檔** | 42 條 golden 常數 + 容忍值是 characterization 錨點,出處鏈寫在 docstring;實測 0.64 s 已經夠快。向量化它 = 過度工程 + 風險 |
| **`replay/report.py::med`** | `s[len(s)//2]`(偶數不取平均)是 golden 的一部分;換 `statistics.median` = 42 條全紅 |
| **`backtest/quantiles.py` 的兩份演算法** | user 2026-07-20 明確拍板保留;docstring 寫明「統一演算法會改報告數字 = 行為改動,不得在 refactor 內做」 |
| **`market.py` 的毫元整數運算** | 「全程毫元整數運算,避免二進位殘差」是刻意設計;改 float/numpy 會讓 tick 貼齊出現 off-by-one-tick,而且前端 `stock-tick.ts::snapDown` 有 parity fixture 鎖著(`tests/fixtures/vp_parity.json`) |
| **`engine/lock_quality.feed` / `t1_open.feed` 的逐 bar 迴圈** | 0.88 / 0.35 µs per bar,合計只佔 replay 8%。向量化省 2 s,卻犧牲「盤中可查、不回改」的即時介面 —— 那個介面正是實盤複用的唯一希望(B12-04 選項 B) |
| **`StrategyConfig` / `BacktestConfig` 的 frozen slots + JSON 覆寫樣式** | 乾淨、零 magic number、`configio.load_dataclass_json` 是唯一實作。不要為了效能把它拆成 dict |
| **`simulate.py` 的同 bar 優先序與 D9 凍結語意** | docstring 逐條寫明,`tests/backtest/test_simulate.py` 是行為鎖。任何重寫要逐條重現,**不是效能問題** |
| **`universe.py` 的 D7 雙保險(`closed_at_limit != lockable` → excluded_lock_conflict)** | 這是資料矛盾偵測(no silent caps),不是可以省的分支 |
| **`_seed_only` 的 fail-closed** | 未知 source 一律排除是刻意的;放寬會讓 gate 隨 scan 池成長而漂 |
| **pytest 子集(352 tests / 10.2 s)** | fixture 驅動、不碰 `data/`,已經夠快 |

---

## 6. 量測方法(怎麼證明快了 / 慢了)

### 6.1 立即可重跑的基準(我用的就是這些)

```powershell
# 0) 基準環境
cd C:\side-project\copycat

# 1) replay 全量(最重要的單一數字;寫到 scratchpad 不碰 repo)
Measure-Command { .venv\Scripts\python -m copycat replay `
    --watchlist watchlists\five_tigers.json `
    --out $env:TEMP\copycat-bench\out }
# 基準值 2026-09-13:25.3 s(11,048 事件 / 22,067 次 read_bars)

# 2) replay 逐函式 profile
.venv\Scripts\python -c @'
import cProfile,pstats,io,sys
from pathlib import Path
from copycat.replay.runner import run_replay
pr=cProfile.Profile();pr.enable()
run_replay(Path("data"),Path("watchlists/five_tigers.json"),Path(r"%TEMP%\copycat-bench\out2"),None)
pr.disable();s=io.StringIO();pstats.Stats(pr,stream=s).sort_stats("tottime").print_stats(25);print(s.getvalue())
'@
# 看三個數字:read_bars cumtime / raw_decode tottime / nt.stat ncalls

# 3) golden gate(必須維持 42/42 PASS)
.venv\Scripts\python -m copycat validate
# 基準值:42/42 PASS,0.64 s

# 4) 全量測試
.venv\Scripts\python -m pytest -q tests\backtest tests\engine tests\replay tests\data
# 基準值:352 passed in 10.19s
```

### 6.2 search 段的獨立探針(不需要跑完整 tday-search)

```python
# scratchpad/bench_search.py —— 直接吃既有的 out/tday_ga 產物,零副作用
import json, time
from pathlib import Path
from copycat.backtest.config import BacktestConfig
from copycat.backtest import pipeline as P
from copycat.backtest.search import build_predicates, exhaustive_scan, ga_search

cfg = BacktestConfig.default()
OD = Path("out/tday_ga")
rows = P._read_features(OD, 0.08)
oc = json.loads((OD / "outcomes_theta0.080.json").read_text(encoding="utf-8"))
bp, bs = oc["pnl"]["baseline"], oc["status"]["baseline"]
TRAD = {"stopped", "time_1300", "closeout", "hold_e1"}
ti = [i for i, r in enumerate(rows) if str(r["date"]) < cfg.split_date]
fp, fw = [], []
for i in ti:
    p, w = bp[i], rows[i]["weight"]
    ok = bs[i] in TRAD and p is not None
    fp.append(p if ok and p is not None else 0.0); fw.append(w if ok else 0.0)
preds = build_predicates([P._feature_row(rows[i]) for i in ti], P.FEATURE_NAMES, cfg.quantile_probs)
t = time.perf_counter(); c = exhaustive_scan(preds, fp, fw, cfg)
print(f"exhaustive_scan {time.perf_counter()-t:.1f}s  preds={len(preds)} out={len(c)}")
t = time.perf_counter(); g = ga_search(preds, fp, fw, cfg, 1)
print(f"ga_search(seed=1) {time.perf_counter()-t:.1f}s out={len(g)}")
```
基準值 2026-09-13:**preds=366 / exhaustive_scan 27.3 s / ga_search 4.2 s**。

### 6.3 改造後的 parity gate(每一條改動都要過)

1. **數值 parity**:改動前後各跑一次 `copycat replay`(four + five)→
   `python -m copycat compare out_old/five_tigers out_new/five_tigers`,
   所有 Δ 必須是 `+0.00%`。
2. **golden gate**:`python -m copycat validate` = 42/42 PASS。
3. **rules parity**:改 search 後,`rules_final.json` 的
   `rules[*].conditions` 集合與 `fitness_train` 在 1e-12 內相等
   (寫一支 `scripts/parity_rules.py`,不進 repo,放 scratchpad)。
4. **before/after 表**:B12-15 的 `timings.json` 兩份並排,附進 PR 描述
   (CLAUDE.md 鐵則 D:完成必附證據 / 量測對照)。

### 6.4 建議建立的長期基準檔

`docs/evidence/2026-XX-XX-backtest-perf-baseline.md`,表格欄 =
`(階段, 呼叫數, wall-clock, 環境 SHA)`,每次效能改動追加一列。
現在**沒有這份檔**,所以 B12-15 的計時要先做。

---

## 7. 硬約束清單(改造時必須點名)

| 約束 | 出處 | 對本區塊的意義 |
|---|---|---|
| **runtime stdlib-only**(`dependencies = []`) | pyproject | numpy / polars / msgspec **只能進 `[backtest]` 或 `[dev]` extras**;`live/` `server/` 零 import。若 backtest 模組被 server 間接 import,就會炸 —— 目前 `server/` 不 import `backtest/`(已確認),要維持 |
| **五檔委買賣深度不可回測** | CLAUDE.md §0a | B12-04 的實盤/回測不一致**在資料層無解**,只能量化差距或做 seam |
| **determinism D11**:輸出無 timestamp、json sort_keys、樣本序 = features CSV 序、隨機性只在 `ga_search(seed)` | `pipeline.py` docstring / `search.py` docstring | 平行化必須固定 reduce 順序;numpy 的浮點加總順序改變要 parity;計時輸出必須寫獨立檔 |
| **`copycat validate` 42 條 golden**(±5% / ±0.5pp / ±1pp / ±3pp) | `replay/validate.py` + CLAUDE.md §1 gate | 任何碰 `engine/` / `DailyIndex` / `read_bars` / `report.med` 的改動都要重跑,**逐字 PASS** |
| **`quantiles.py` 兩份演算法不可互換** | user 2026-07-20 拍板 + docstring | 不得統一 |
| **`_CACHE_VERSION` bump 作廢舊 cache** | CLAUDE.md §4 + `pipeline.py:48` | outcome cache 改格式要 bump 到 2 |
| **`sim_config_hash` 只涵蓋 `_SIM_FIELDS`** | `config.py:105-125` | 改 cache 粒度(B12-05)= 改這個清單的語意,要同步改 docstring |
| **`market.py` 毫元整數 ↔ 前端 `stock-tick.ts::snapDown` parity**(`tests/fixtures/vp_parity.json`) | CLAUDE.md §4 | `tick_size` 不可改成 float 近似 |
| **`Bar1K` 的 `m` 語意:09:01 = 索引 0,bar 以收盤時刻標記** | `data/models.py:10` | 與 CLAUDE.md §4「台指期疊線分鐘鍵 = 1K 終點標記 −1 分」「個股頁即時末根 = accum 起點分 +1」是同一把尺的不同端;columnar 遷移時**不可改標記語意** |
| **`read_bars` 回 `None` = 檔不存在(三態)** | `store.py:44` + 三個呼叫端的 `skip` 分支 | 不可退化成空 list |
| **`ref_prev_close` 的 `spread is None` vs `0.0`** | `daily.py:119-136` | numpy/polars 化時不可用 NaN 混淆 |
| **`write_bars` 的分鐘遞增檢查 + atomic write** | `store.py:17` / `fileio.py` | 新格式要重現 |
| **提交慣例:🔴 行為 / 🟢 新功能 / 🔵 純重構 三類分開 commit** | CLAUDE.md §6 | numpy 化若造成浮點漂移 = 行為改動,**不能混在重構 commit 裡** |

---

## 8. 建議執行順序(收益/風險比排序)

| # | 動作 | 預期收益 | 風險 | 工作量 |
|---|---|---|---|---|
| 1 | **B12-06** `_feature_row` memo + frozenset | 12.2 s → 0.5 s | 零(逐字相同) | S |
| 2 | **B12-08** `exists()` → try/open | 0.9 s | 零 | S |
| 3 | **B12-15** 分階段計時 + `timings.json` | 建立量測基準 | 零(獨立檔) | S |
| 4 | **B12-11** `quantiles_round` 少 3 次 sort | 小 | 零 | S |
| 5 | **B12-13** replay 不重讀 events.jsonl | 0.5 s | 低 | S |
| 6 | **B12-04 選項 A** 量化 live/backtest 鎖板差距 | **模型信心** | 零(只讀 + 文件) | M |
| 7 | **B12-01** numpy 謂詞矩陣 | **27.3 s → 0.5 s / 21 s → 1 s** | 中(浮點 parity) | M |
| 8 | **B12-07** DailyIndex csv.reader + 快照 | 4 s → 0.5 s;解鎖平行化 | 低–中 | M |
| 9 | **B12-05** outcome cache per-combo + npz | 54 MB → 15 MB;粒度正確 | 低 | M |
| 10 | **B12-09/03** simulate 常數外提 + regime 平行 | 28 s → ~15 s → ~5 s | 中(determinism) | M |
| 11 | **B12-02 修法 3** 1K columnar 遷移 | replay 25 s → ~5 s | 中(遷移 + parity) | L |
| 12 | **B12-04 選項 B** LockPredicate seam | 實盤/回測共用狀態機 | 高(踩訊號契約) | L |

做完 1–10,`tday-search` 冷跑估 **3.5–4 分鐘 → ~50 s**;`replay` 25.3 s → ~16 s;
再做 11,`replay` → ~5 s、golden gate 51 s → **~11 s**。

---

## 9. 尚未查清的事(需要 user 回答或需要實跑)

1. **完整 `tday-search` 冷跑的實際 wall-clock 沒有量過** —— 我只有分段外推(sim 28 s +
   search 145 s + 浪費 12 s + IO)。要拿真數字必須刪掉 `out/tday_ga/outcomes_*.json`
   再跑一次,那會覆寫既有 evidence 產物,**超出「不改動 repo」的授權範圍**。
   建議 user 自己跑一次並保留 log。
2. **fade 家族(6,900 LOC / 4,640 combo)的實際跑批時間未知** —— 需要
   `data/daytrade` 已回補才跑得動(`fade_pipeline.py:70` 有 fail-fast)。
3. **numpy 化後是否允許重拍 `docs/evidence/` 的既有報告數字?**
   若不允許,B12-01 必須做到 bit-exact(可行但要用 `math.fsum` 等價路徑,
   收益從 100x 降到 ~30x)。**這是拍板題。**
4. **`engine/` 的狀態機要不要真的上實盤?**(B12-04 選項 B)
   若要,共用的資料形狀是 tick 還是 bar?tick 的話 `LockTracker` 要重寫成
   tick 驅動 + 簿深注入;bar 的話實盤要自己聚合 1K。這是 spec 級決策。
5. **`rules_final.json` 的 `stop_duel` 有沒有下游讀者?**(B12-17 要拍板才能只在 rank 0 展開)
6. **這台機器的實體核心數**?平行化的收益直接依賴它,我沒查(`os.cpu_count()` 沒跑)。
7. **`data/1k` 未來的成長曲線**?若 scan 池會長到全市場 × 數年,
   columnar 就不是「可選」而是「必須」 —— 21,254 檔的 JSON 目錄在 Windows 上
   已經接近檔案系統友善的上界。
