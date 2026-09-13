# B11 — 回測 fade 家族架構與效能掃描

> 掃描日期 2026-09-13 · 範圍 `copycat/backtest/fade_*.py` + 其共用依賴
> (`search.py` / `stats.py` / `quantiles.py` / `features.py` / `data/store.py`)
> 全部數字皆為本機實測(Windows 11 / Python 3.13 / `.venv`),量測腳本在
> `scratchpad/bench_fade*.py`、`bench_cells.py`、`bench_parse.py`、`bench_scan.py`。
> **本次掃描未改動 repo 任何檔案。**

---

## 0. 一頁摘要

| 項目 | 實測 / 推估 | 說明 |
|---|---|---|
| `fade-cells`(round 4)單次跑 | **~45 s**,其中 **32 s(71%)是 JSON 載入** | 計算本身只有 ~10 s |
| `fade-search`(GA 全流程) | **推估 15–25 小時**(未實跑) | 三塊各自成小時級,詳見 §4 |
| 最貴的單一函式 | `search._evaluate` → `bit_indices`,**617 µs/次**(n_rows=4000、popcount≈980) | 大整數 bitmask 的 `mask & -mask` 是 **O(popcount × n_rows)**,實質 O(n²) |
| 記憶體 | `build_universes` 後 **955 MB**(3.09M 根 Bar1K,**310 B/bar**) | numpy SoA 可降到 ~222 MB |
| 平行化 | **完全沒有**(全庫 0 個 `multiprocessing` / `concurrent.futures`) | 17 臂 × 4,660 combo 是教科書等級的 embarrassingly parallel |
| Outcome cache | **fade 家族沒有**;`fade_pipeline.py:4` 的 docstring 宣稱有,實際只有 tday `pipeline.py` 有 | 重跑一次就是全額重算 |
| 與即時系統耦合 | **零**(`copycat/backtest/` 只被 `cli.py` import) | 可完全獨立改造 —— 但也代表回測與實盤是**兩套獨立實作**(§8) |

**結論方向**:這一區確實是 numpy/polars 最明確的標的,但**標的不是「把 Bar1K 換成 DataFrame」**
—— 真正的錢在三個地方:(a) `search.py` 的 bigint bitmask 換 numpy bool 矩陣(~150–200x);
(b) 1K 載入從 per-file JSON 換成欄狀二進位 + cache(~3–20x);(c) combo 網格用 prefix-scan
把「逐 combo 重跑 270 根 bar」換成「一次掃描 + searchsorted」(~10–50x)。
`fade-cells` 的**評估段本身不要動**(0.1–0.2 s/pass,換工具是過度工程)。

---

## 1. 架構地圖

```
CLI(copycat/cli.py)
├─ fade-search      → fade_pipeline.run_fade_pipeline      ← 最重(小時級)
├─ fade-cells       → fade_cells.run_cells                 ← 中(45 s)
├─ fade-diagnose    → fade_diagnose.run_pool_diagnose      ← 中(permutation 5000 iters)
├─ fade-anatomy     → fade_anatomy.run_anatomy             ← 輕
└─ fade-entry-anatomy → fade_entry_anatomy.run_entry_anatomy ← 輕

                 ┌──────────────────────────────────────────┐
                 │  共用底層(零 IO 純函式)                  │
                 │  fade_simulate._simulate_core  ← 唯一模擬器 │
                 │  fade_tp.check_tp_exit / PivotState        │
                 │  fade_config.FadeBacktestConfig(frozen)    │
                 │  search.{build_predicates,exhaustive_scan,  │
                 │          ga_search,apply_rule,bit_indices}  │
                 │  stats.{weighted_stats,max_drawdown,...}    │
                 └──────────────────────────────────────────┘
                                    ▲
        ┌───────────────────────────┼───────────────────────────┐
   fade_arms(7 臂觸發)      fade_vote(round5 投票)     fade_features(197 欄)
        │                           │                           │
        └──────────── fade_pipeline / fade_cells 兩條 orchestration ─────┘

資料層:data/store.read_bars(per-file JSON)、data/daily.DailyIndex(csv → dict of list)
```

### 1.1 模組職責(讀完全部 13 檔後的實況)

| 檔案 | LOC | 角色 | 熱度 |
|---|---:|---|---|
| `fade_cells.py` | 2007 | **四種 round 的評估 orchestration(round2/3/4/5)+ 三份 markdown 報告 writer** | 中 |
| `fade_pipeline.py` | 735 | universe → 觸發 → 特徵 → combo 網格 → GA → walk-forward | **最高** |
| `fade_anatomy.py` | 594 | round4 §0 描述統計(MFE / flush / 墊高 / 內盤比 / 緩漲)+ 報告 | 低 |
| `fade_entry_anatomy.py` | 576 | round5 §0 進場訊號解剖(流向反轉 / CDP 位階)+ 報告 | 低 |
| `fade_config.py` | 560 | 全參數 dataclass + combo/TP 列舉 + 驗證 + config hash | — |
| `fade_diagnose.py` | 538 | 逼近漲停診斷 + 四池 permutation 檢定 + 報告 | 中 |
| `fade_simulate.py` | 395 | **唯一模擬器 `_simulate_core`**,逐 bar 狀態機 | **最高** |
| `fade_tp.py` | 379 | 11 種 TP + round4 決策樹,`_simulate_core` 內逐 bar 呼叫 | **最高** |
| `fade_optimize.py` | 348 | 規則 × combo / × TP 對決(暴力雙層迴圈) | **最高** |
| `fade_report.py` | 267 | 純字串組裝 | 低 |
| `fade_features.py` | 262 | 197 欄特徵(實測,非 docstring 說的 224) | 中 |
| `fade_arms.py` | 247 | 7 臂觸發器,每個都是單次 O(bars) 掃描 | 低 |
| `fade_vote.py` | 154 | round5 三票計分,generator 形式 | 低 |

**觀察**:`fade_cells.py` 2007 LOC 裡約 900 行是 markdown 報告 writer(`_write_round3/4/5_report`),
三份幾乎同構。這不是效能問題,但是「一檔兩種職責」的架構債,會讓後續把評估段改成
向量化版本時多動一倍的檔(見 F-17)。

---

## 2. 資料流(fade-search 路徑逐步)

```
data/events/events.csv        11,048 列
   ↓ build_fade_universe(cfg)              [8.4 s 實測]
   ↓   per-row: DayTradeIndex 查 + read_bars(存在性 + 首根 open) → gap 過濾
   ↓
samples: list[FadeSample]      5,586 筆(預設 cfg;round4 cfg 下 main=4,129)
   ↓
for arm in ALL_ARMS (7):
  for params in arm.anchor_params (共 17 組):
     run_fade_arm:
       ↓ per sample: read_bars(**再讀一次,無 cache**)  [0.54 ms × 5,586 = 3.0 s]
       ↓ dispatch_trigger                              [1–9 µs]
       ↓ static_features + structural_features(DailyIndex)
       ↓ fade_trigger_features → 197 欄 dict            [231 µs × n_trig]
       ↓ n_triggered ≈ 0.39–1.00 × n_samples(實測觸發率)
       │
       ├─ baseline 128 combo × n_trig × simulate        [~34 s]
       ├─ S1 top-3 排名
       ├─ all_combos = 4,660 combo × n_trig × simulate  [~20 min]  ← ①
       ├─ _collect_tradeable → 平行陣列(feat/pnl/dates/sids)
       ├─ _ga_candidates:
       │    build_predicates  → ~2,300–7,400 predicates
       │    exhaustive_scan   → P²/2 對                 [27 min – 4 hr]  ← ②
       │    ga_search × 10 seeds                        [~8 min]
       │    jaccard_dedupe → top-30
       ├─ 三道驗證(test 期望值 / 月度一致性)
       ├─ optimize_rule_stops: 30 rule × 4,660 combo × train_idx  [~23 min]  ← ③
       └─ optimize_rule_tp:   30 rule × 1,927 TP × train_idx      [~14 min]  ← ④
   ↓
write_fade_report + rules_final.json(含 bigint mask)
```

`fade-cells` 路徑(不同分支,不進 GA):

```
build_universes(cfg)                       [32.1 s 實測]
  ├─ build_fade_universe × 3(main / low / cellb)  ← events.csv 解析 3 次
  └─ _with_bars × 3                                ← read_bars 再讀 3 輪,無 cache
  → 11,426 個 (sample, bars) pair / 3,085,020 根 bar / 955 MB RAM
   ↓ UC 過濾(watchlist broker_ids)→ main_uc 1,634 / low_uc 978 / cellb_uc 1,751
   ↓ round 4:5 主變體 × (base+stress) + 10 敏感度 + 3 量尺 + 5 消融
   ↓   每個 pass = _simulate_r3_trades,實測 0.11–0.23 s
   → 評估總計約 10 s
```

**所以 fade-cells 的 71% 時間是「把 JSON 變成 Python 物件」。**

---

## 3. 資料量級(實測)

| 量 | 值 | 來源 |
|---|---|---|
| events.csv | 11,048 列 / 490 KB | `wc -l` |
| daily/prices.csv | **1,013,469 列 / 52 MB** | `wc -l` |
| 1K 檔案數 | **21,254 檔 / 294 MB** | `find` |
| 每檔 bar 數 | 270(09:01–13:30 滿檔) | 抽樣 |
| 1K 總 bar 數 | ~5.7M(全庫)/ 3.09M(round4 universe 實載) | 計算 + 實測 |
| fade universe(預設 cfg) | 5,586 samples(11,048 中剔除 gap 5,315 + 缺 1K 147) | 實測 |
| fade universe(round4 cfg) | main 4,129 / low 2,813 / cellb 4,484 | 實測 |
| UC 池(five_tigers watchlist) | main 1,634 / low 978 / cellb 1,751 | 實測 |
| baseline combos | **128** | 實測 |
| anchor combos(`enumerate_fade_stop_combos`) | **4,660** | 實測 |
| TP combos(`enumerate_tp_combos`) | **1,927** | 實測 |
| anchor arm×param | **17** | 實測 |
| 特徵欄數 | **197**(其中 195 非 None) | 實測 |
| predicates(553 列 universe) | 2,274 | 實測 |
| predicates(推估 4,000 列) | ~5,000–7,400 | 外推(quantile 去重後上限 197×19×2=7,486) |

---

## 4. 熱路徑逐條(全部實測單位成本)

### HP-1 `search._evaluate` → `search.bit_indices` —— **最貴**

`copycat/backtest/search.py:81-111`

```python
def bit_indices(mask: int) -> list[int]:
    out = []
    while mask:
        lsb = mask & -mask          # ← 4000-bit 大整數運算,O(n_rows/30) limbs
        out.append(lsb.bit_length() - 1)
        mask ^= lsb                 # ← 同上
    return out

def _evaluate(mask, pnl, weights, cfg):
    for i in _bit_indices(mask):    # ← 迴圈次數 = popcount
        ...
```

**實測**(n_rows=4,000、popcount=979):`_evaluate` = **617.7 µs**,
對照 `m1 & m2` 大整數 AND 只要 **0.13 µs**。
→ 99.98% 的成本在 `bit_indices` 的 `mask & -mask` / `mask ^= lsb`:
每次都在 4,000-bit(≈134 個 30-bit limb)的大整數上做全長運算,
所以**實際複雜度是 O(popcount × n_rows)**,不是 O(popcount)。

**呼叫頻率**:`exhaustive_scan` 對 P 個 predicate 做 P²/2 對,每對一次 `_entry`→`_evaluate`。

| P | 對數 | 推估耗時 | `seen` set 記憶體 |
|---:|---:|---:|---:|
| 2,274(553 列實測值) | 2.58M | **26.6 min** | 0.28 GB |
| 5,000 | 12.5M | **129 min** | 1.37 GB |
| 7,000 | 24.5M | **252 min** | 2.69 GB |

> 小樣本(553 列)實測 `_entry` 只要 9.7 µs —— 因為 popcount 小、bigint 短。
> **成本隨 universe 大小呈二次爆炸**,這正是「小資料測不出來、正式跑掛掉」的典型形狀。

### HP-2 `fade_simulate._simulate_core` 逐 bar 狀態機

`copycat/backtest/fade_simulate.py:168-353`,每根 bar 做:
locked 判定 → running_low/high 更新 → `outer_win.append` → 5 種強制出場 level 比較
→ 4 種 combo stop → target → TP 樹 → time_1300。

**實測**(300 個真實 sample,270 根 bar):

| combo | µs/call | ns/bar |
|---|---:|---:|
| 無停損抱到收盤 | 111.5 | 413 |
| S4 固定 2% | 64.8 | 240 |
| S1(n=5,φ=.55)+ S5 2% | 20.5 | 76(提早出場) |
| `simulate_with_tp(tp=None 物件)` | **116.8** | 433 |
| `simulate_with_tp(tp1)` | 73.3 | 271 |
| `simulate_with_tp(tp2)` | **174.3** | 646 |

**呼叫頻率**:`fade_pipeline` 的 combo 網格 = 4,660 × n_triggered(≈4,000)= **18.6M 次/臂**,
17 臂 → **317M 次**。以均值 65 µs 計 = **5.7 小時**。

### HP-3 `fade_optimize.optimize_rule_stops` / `optimize_rule_tp`

`fade_optimize.py:101-132` / `147-166`:

```python
for ri, rule in enumerate(rules):            # ≤ 30
    ...
    for combo in all_combos:                 # 4,660
        ev = _eval_combo(train_idx, ...)     # 內層再跑 len(train_idx) 次 simulate
```

三層迴圈。30 × 4,660 × ~150(matched train)× 65 µs ≈ **1,363 s = 23 min/臂**。
TP 版:30 × 1,927 × 150 × ~100 µs ≈ **867 s = 14 min/臂**。

### HP-4 `data.store.read_bars` —— 每次都重新解析 JSON

`copycat/data/store.py:42-60`。**實測拆解(單檔 270 根 / 12.4 KB)**:

| 段 | µs | 佔比 |
|---|---:|---:|
| `path.exists()` | 4 | 1% |
| `path.read_text()` | 53 | 10% |
| `json.loads()` | 180 | 33% |
| **`Bar1K(...)` 建構 × 270** | **271** | **50%** |
| 合計 | **540** | |

**呼叫頻率**:
- `build_fade_universe` 每個 event 一次(11,048)
- `run_fade_arm` 每個 sample 再一次 × **17 臂**(5,586 × 17 = 95,000)
- `build_universes` 呼叫 `build_fade_universe` **三次** + `_with_bars` **三次**
- `run_fade_pipeline` 的 diagnose 分支再讀一次全 universe

實測:`build_fade_universe` 8.4 s、`build_universes` **32.1 s**。
fade-search 光是重複讀檔就是 95,000 × 0.54 ms = **51 s**(佔比不大,但完全是白工)。

### HP-5 `fade_features.fade_trigger_features` —— 197 欄

`fade_features.py:229-262`,實測 **231 µs/call**。內部是 8 個 helper,
每個都對 `w = bars[:trig_idx+1]` 做多重巢狀迴圈:

- `_bid_exhaustion`:8 thresholds × 5 lookbacks = **40 個窗**,每窗反向掃(`fade_features.py:141-151`)
- `_open_eq_high_count`:8 n × 8 tol = **64 欄**,每欄一次 `sum(1 for b in window ...)`
- `_price_vol_divergence`:9 n × 5 d = **45 欄**,每欄一次 O(n) 迴圈

**同一個 window 被重掃 40–64 次**。呼叫頻率 = n_triggered × 17 臂 ≈ 68,000 次 = **16 s**。
量級不大,但這是最典型的「一次 prefix scan 可以算完全部」的形狀。

### HP-6 `fade_diagnose.stratified_permutation_p`

`fade_diagnose.py:149-179`:5,000 iters × 每 iter 對**每個層**(= 每個交易日,~250 層)
做一次 `rng.shuffle(vals)` + 兩次 `sum`。
→ 5,000 × 250 = **1.25M 次 shuffle**,而且 `_comparison_and_verdict` 裡呼叫 **2 次**
(單層 + 雙重分層),`diagnose_pool_fade` 又對全期間 + forward 段各跑一次 → **4 次** ≈ 5M shuffle。

### HP-7 `fade_cells` 的評估 pass —— **這裡其實很快**

實測 `_simulate_r3_trades`:

| kind | universe n | trades | 耗時 |
|---|---:|---:|---:|
| cell_a | 1,634 | 808 | 0.16 s |
| cell_b | 1,751 | 868 | 0.11 s |
| m7_arm | 1,634 | 1,499 | 0.22 s |
| base_arm | 1,634 | 1,634 | 0.23 s |

round 4 完整跑約 50 個 pass → **~10 s**。**這一段不要動**(見 §7)。

---

## 5. Findings

> severity 判準:critical = 讓整個流程不可用 / 小時級浪費;high = 分鐘級以上或有 scaling 崩潰風險;
> medium = 秒級但每次都付;low = 架構/可維護性。

### F-01 `bit_indices` 的大整數 bitmask 是 O(popcount × n_rows),exhaustive_scan 因此是 O(P² · n)
**critical · 熱路徑 · location `copycat/backtest/search.py:81-88,94-111`**

```python
def bit_indices(mask: int) -> list[int]:
    out = []
    while mask:
        lsb = mask & -mask
        out.append(lsb.bit_length() - 1)
        mask ^= lsb
    return out
```

**證據**:實測 n_rows=4,000 / popcount=979 → `_evaluate` **617.7 µs**;同尺寸的 `m1 & m2` 僅 0.13 µs。
**影響**:`exhaustive_scan` 在 P=5,000 時 **129 分鐘**,P=7,000 時 **252 分鐘**;
且這在 `_ga_candidates` 內,walk-forward 模式下**每個 fold 每個臂各跑一次**。

**改法**:把 predicate mask 從 `int` 改成 `numpy.ndarray[bool]`(shape=(n_rows,)),
`_evaluate` 改成:
```python
w_masked = weights * mask          # 或 weights[mask]
raw = int(mask.sum())
wsum = float(w_masked.sum())
acc  = float(pnl @ w_masked)
```
單次成本從 618 µs → **~4 µs**(**~150x**)。

**再進一步(建議做)**:exhaustive 2-condition 掃描改成分塊 matmul —— 把 P 個 predicate 疊成
`M`(P × n_rows 的 `bool`/`float32`),對每個 i:
```python
and_i = M & M[i]                  # (P, n) bool
acc   = and_i.astype(np.float32) @ pnl_w      # (P,) 一次算出所有 j 的加權和
raw   = and_i.sum(axis=1)
```
P=7,000 / n=4,000 → 每個 i 是 28M 元素的 BLAS gemv,約 10 ms → 全部 **~70 s**(對照 252 min,**~200x**)。

**風險**:`search.py` 同時被 tday `pipeline.py` 使用(`from copycat.backtest.search import ...`),
改 `Predicate.mask` 型別會同時影響 tday 路徑。`bit_indices` 的 docstring 明寫
「pipeline 共用,勿另行實作」——**這是跨檔契約**,要同步改 `fade_optimize._test_indices` /
`_fold_test_indices`(兩者吃 `bit_indices(mask)`)與 `search.jaccard_dedupe`
(用 `.bit_count()`)。既有 `tests/backtest/test_search.py`(124 行)是安全網,
但建議先加一條 golden:同一份 rows 下新舊實作的 `(fitness, expectancy, raw, wsum)` 逐位元相等。

**effort**:M(單檔 + 兩個 caller,測試已在)

---

### F-02 `exhaustive_scan` 的 `seen` set 在巢狀對迴圈裡是純浪費,且吃 GB 級記憶體
**high · 熱路徑 · location `copycat/backtest/search.py:151-166`**

```python
seen: set[tuple[int, ...]] = set()
...
for i in range(len(predicates)):
    for j in range(i + 1, len(predicates)):
        _try((predicates[i], predicates[j]), (i, j))   # (i,j) 永遠不重複
```

**證據**:`i < j` 的雙層迴圈結構上保證 key 唯一,`seen` 只會單調增長到 P²/2 筆。
**影響**:P=7,000 → 24.5M 個 tuple 進 set ≈ **2.7 GB**(推估,tuple 56 B + set slot ~50 B),
在 16 GB 機器上會和 955 MB 的 bars + predicate masks 一起把行程推向 swap。

**改法**:單條件那圈保留(理論上 predicate 可重複),雙條件那圈直接 `_try` 不查 `seen`,
或整個改成 `if key in seen` 只對單條件圈生效。

**風險**:零行為改變(key 本來就不重複)。`tests/backtest/test_search.py` 應該綠。
**effort**:S

---

### F-03 4,660 combo × 4,000 sample 的「逐 combo 重跑整條 bar」= 5.7 小時純重算
**critical · 熱路徑 · location `copycat/backtest/fade_pipeline.py:547-560`**

```python
for combo in all_combos:                     # 4,660
    ...
    for sample, bars, trig_idx in triggered: # ~4,000
        out_r = simulate_fade_sample(bars, trig_idx, sample, combo, cfg, cfg.slippage_ticks)
```

**證據**:`enumerate_fade_stop_combos` 實測回 **4,660** 組;觸發率實測 39%–100%(均值 ~73%);
`simulate_fade_sample` 實測 20–117 µs。18.6M 次/臂 × 17 臂 = 317M 次。

**影響**:這一段單獨就是 **~5.7 小時**,且每次重跑 config 都從頭來(無 cache,見 F-04)。

**改法(兩層)**:
1. **演算法層(收益最大)**:大多數停損族的出場 bar 是「第一根滿足門檻」的**單調穿越**,
   可以一次 prefix scan 算完整個網格:
   - S4(固定 x):出場 = 第一個 `high ≥ entry×(1+x)` → 對 `cummax(high)` 做 `np.searchsorted`,
     10 個 x 值一次 `searchsorted` 全出,**O(n log n) 取代 O(10 n)**,且省掉 Python 迴圈。
   - S5(目標 x):同理對 `cummin(low)`。
   - S3(跟蹤 x):需要 `running_low`,但 `running_low` 本身就是 `cummin(low)` 的 prefix。
   - S1(stall)/ S2(swing):需要狀態機,留在逐 bar 路徑。
   實測 s4/s5/s3 單族在 4,660 combo 中佔 `bases` 的 20/233,但乘上 `s5 × t1300` 展開後
   **s5 維度(10 值)與 t1300 維度(2 值)是純笛卡兒積** —— 同一次掃描可同時產出全部
   20 種 (s5, t1300) 組合的出場點。光這一步就砍掉 ~20x 的重複掃描。
2. **實作層**:把 `_simulate_core` 的 bars 參數從 `list[Bar1K]` 換成
   `numpy` 的 SoA(9 個 1-D array)+ `numba.njit`。逐 bar 從 240–430 ns → 預期 5–20 ns,**~30x**。

**風險(高)**:`_simulate_core` 是**唯一模擬器**,五個 CLI 全走它,語意極度精細
(同價 tie-break `_REASON_RANK`、`stress_guard_fill_high`、鎖死凍結 bar 仍餵累計量、
`excluded_*` 前綴語意)。`tests/backtest/` 有 5,044 行測試含
`test_fade_simulate_round2/3/4.py`(652 行)+ `test_characterization.py`,
**必須先建 golden fixture:對既有 `out/fade_cells_r4/cells_*.json` 做逐欄 byte 比對**,
新舊實作差一個 float 就紅。numba 的 float 運算順序與 CPython 可能不同 →
建議 numba 版先只跑在「純比較、無累加」的停損判定,累加(`cum_pv` / `cum_delta`)保持原順序。

**effort**:L(prefix-scan 層)/ XL(numba 層)

---

### F-04 fade 家族**沒有** outcome cache,但 docstring 宣稱有
**high · 非熱路徑但影響每次重跑 · location `copycat/backtest/fade_pipeline.py:4`**

```python
"""T+1 Fade pipeline(design.md v2 §8):universe → 觸發 → 特徵 → 模擬 → 搜索 → 驗證 → 報告.
...
Outcome cache 移植 tday pipeline 慣例(三重失效:config hash / rows hash / grid flag)。
"""
```

**證據**:`grep -n "cache|_CACHE|outcomes_path|rows_hash" copycat/backtest/fade_*.py`
**只命中這一行 docstring**;真正的實作只在 `copycat/backtest/pipeline.py:245-308`
(`_load_or_simulate`,三重失效齊備)。

**影響**:每次調 config 重跑 fade-search 都是全額重算(小時級)。
`fade_sim_config_hash(cfg)` 已經存在(`fade_config.py:481`)、`_SIM_FIELDS` 白名單也齊
—— **半套零件已經在了,只差接線**。

**改法**:照抄 `pipeline._load_or_simulate` 的形狀,key = `(fade_sim_config_hash, rows_hash, combo_set_id)`,
落檔 `out/fade_ga/outcomes_<arm>_<param>.json`。注意:4,660 combo × 4,000 sample 的
`pnl`/`status` 表 = 18.6M 個 float + 18.6M 個字串,JSON 會是 GB 級 —— **這份 cache 一定要走
二進位**(`np.savez_compressed` 的 float32 pnl + uint8 status code,約 90 MB)。

**風險**:cache 失效判準漏一欄 = 靜默拿舊結果做決策,對「要下實單的系統」是最危險的一類 bug。
`_SIM_FIELDS` 已經是單一清單,新增 config 欄位時要同步(和 tday 一樣的既有紀律)。

**effort**:M

---

### F-05 `from ... import` 寫在逐 bar 迴圈內
**medium · 熱路徑 · location `copycat/backtest/fade_simulate.py:267,287`**

```python
for b in post:                      # 每根 bar
    ...
    if tp is not None:
        from copycat.backtest.fade_tp import check_tp_exit   # ← 每 bar 執行一次
    ...
    if cfg.tp_flush_z is not None or pivot_state is not None:
        from copycat.backtest.fade_tp import check_flush_exit, check_higher_low_exit  # ← 同上
```

**證據**:實測 `simulate_with_tp(combo=s4_2pct, tp=FadeTakeProfitCombo(None, ()))` = **116.8 µs**,
而完全等價的 `simulate_fade_sample(combo=s4_2pct)` = **64.8 µs**。
差 52 µs / ~270 bar ≈ **0.19 µs/bar**,即 import 查表 + `check_tp_exit` 的 11 段字串比對。

**影響**:在 `optimize_rule_tp`(30 rule × 1,927 TP × 150 sample = 8.7M 次 simulate)上
是 **~7 分鐘/臂的純額外開銷**。

**改法**:兩個 import 提到 module top-level(`fade_tp` 反向 import `fade_simulate.FadeSample`,
會形成循環 —— 用 `TYPE_CHECKING` + 把 `FadeSample` 搬到獨立 `fade_types.py`,或在
`_simulate_core` 函式進入點(迴圈外)做一次 import)。最小改動 = 把兩行移到 `for b in post:` 之前。

**風險**:低(純搬移)。注意 `fade_tp.py:8` 有 `from copycat.backtest.fade_simulate import FadeSample`,
所以不能無腦提到 `fade_simulate.py` 檔頂 —— 函式頂端即可。

**effort**:S

---

### F-06 `FadeTakeProfitCombo.get()` 是 tuple 線性掃描,逐 bar 呼叫 1–5 次
**medium · 熱路徑 · location `copycat/backtest/fade_config.py:499-503`**

```python
def get(self, key: str) -> float:
    for k, v in self.params:
        if k == key:
            return v
    raise KeyError(key)
```

**證據**:`fade_tp._tp2`(`fade_tp.py:170-196`)一根 bar 內呼叫 `tp.get()` **5 次**
(`min_profit` / `trend_n` / `new_low_count` / `z` / `inner_flip`),每次線性掃 5 個 tuple。
實測 tp2 = **174.3 µs/call**,是 tp=None 的 1.5x、是 s4 純停損的 2.7x。

**影響**:`optimize_tp_for_indices` 跑全部 1,927 個 TP;tp1(900 組)+ tp2(720 組)佔 84%,
兩者都是逐 bar 多次 `get`。

**改法**:`FadeTakeProfitCombo` 保持 frozen tuple(hash 需要),但加一個
`functools.cached_property` 的 `_d: dict[str, float]`,`get` 改查 dict;
或在 `check_tp_exit` 進入時一次解包成 local 變數。後者對 numba 路徑也友善。

**風險**:`tp_id`(`fade_config.py:492-497`)靠 `self.params` 的排序產生報告 key,
不可改 tuple 本身;只加衍生欄位。`slots=True` 下不能用 `cached_property` —— 改成
module-level `@lru_cache` 的 `_params_dict(combo)`。

**effort**:S

---

### F-07 `validate_disaster_fields` / `validate_round4_fields` 在每次 simulate 呼叫
**low · 熱路徑 · location `copycat/backtest/fade_simulate.py:101-102`**

```python
validate_disaster_fields(cfg)  # 擋 dataclasses.replace 繞過 config 驗證(round 3)
validate_round4_fields(cfg)    # 同上(round 4)
```

**證據**:實測兩者合計 **0.71 µs/次**。
**影響**:317M 次 simulate → **~3.8 分鐘**。佔比 ~1%,但完全是重複驗證同一顆 frozen config。

**改法**:`FadeBacktestConfig` 是 `frozen=True, slots=True` → 可 hash。
把 validate 包成 `@lru_cache(maxsize=64)` 的 `_validated(cfg)`,或在
`dataclasses.replace` 的呼叫點(`fade_cells.py:234,301,626,799,1430`、
`fade_diagnose.py:341,351`、`fade_pipeline.py:313`)驗一次。

**風險**:低,但注意這條註解明說目的是「擋 `dataclasses.replace` 繞過驗證」——
改成 lru_cache 仍能擋(replace 出來的是新物件、新 hash)。
**不建議直接刪** —— 它是 round 3/4 互斥欄位的唯一防線。

**effort**:S

---

### F-08 `read_bars` 無 cache,同一檔在一次 run 內被解析 3–17 次
**high · 熱路徑(IO) · location `copycat/data/store.py:42-60`;呼叫點 `fade_pipeline.py:97,444,703`、`fade_cells.py:1936`**

```python
def read_bars(data_dir, stock_id, date):
    path = bars_path(data_dir, stock_id, date)
    if not path.exists(): return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [Bar1K(m=int(r[0]), open=r[1], ...) for r in payload["bars"]]
```

**證據**:
- `build_fade_universe`(`fade_pipeline.py:92-100`)已經讀過一次,只為了拿 `bars[0].open`
- `run_fade_arm`(`fade_pipeline.py:444`)對同一個 sample **再讀一次**,× 17 臂
- `build_universes`(`fade_cells.py:1929-1946`)呼叫 `build_fade_universe` **三次** +
  `_with_bars` **三次** → 同一檔最多讀 6 次
- 實測 `build_universes` = **32.12 s**;`build_fade_universe` 單次 = 8.38 s

**影響**:fade-cells 的 71% / fade-search 的 ~51 s 純浪費。

**改法(三段,由淺到深)**:
1. **立刻可做**:`build_universes` 內加一個 `dict[(stock_id, date), list[Bar1K]]` local cache
   → 32.1 s → 推估 ~12 s(3 次 events.csv 解析仍在)。
2. **中期**:`Bar1K` 建構佔 50%(271 µs/檔)—— 改回傳欄狀
   `BarsArray`(9 個 `array.array('d')` 或 `np.ndarray`),消費端同步改。
   單檔 540 µs → 推估 ~170 µs(**3.2x**)。
3. **長期(建議)**:1K store 從 21,254 個 JSON 改成**單一欄狀二進位**
   —— 一個 `bars.parquet`(polars)或 `bars.npy` + `index.json`。
   294 MB JSON → 約 60 MB(float32 + zstd)。全量載入實測外推:
   JSON 路徑 21,254 × 540 µs = **11.5 s**;parquet 路徑預期 **0.5–1.5 s**(**~10x**)。

**風險**:`write_bars`(`store.py:16-39`)與 `data/import_neigui` 是唯一寫入點,
`replay/` 與 `copycat validate` 的 golden gate 也吃同一份 store
(`CLAUDE.md §1`:`copycat validate` 是完工 gate)。
換格式 = 要同時改 writer + reader + 保留一次性 migration,
且 **`copycat validate` 的 golden 必須先跑過確認 byte-identical**。
建議做法:**保留 JSON 為權威格式,新增一層 derived cache**(`data/1k_cache/*.npz`,
key 含 source mtime),讀不到就 fallback JSON —— 零契約改動。

**effort**:S(cache dict)/ M(欄狀 reader)/ L(格式遷移)

---

### F-09 955 MB / 310 B per bar —— Bar1K 物件的記憶體密度是 numpy 的 4.3 倍
**high · location `copycat/data/models.py:8-18` + `copycat/backtest/fade_cells.py:1941`**

**證據**:`tracemalloc` 實測 `build_universes` 後 **current = 955 MB / peak = 956 MB**,
bars = 3,085,020 根 → **310 B/bar**。
(`@dataclass(frozen=True, slots=True)` 9 欄:物件頭 16 B + 9 個指標 72 B + 8 個獨立
`float` 物件 ×24 B + `int` ≈ 310 B。)

**影響**:
- round 4 只是 UC 池 1,634 檔就吃掉近 1 GB;若要擴到全市場(21,254 檔 × 270 = 5.7M 根)
  就是 **~1.8 GB**,加上 F-02 的 `seen` set 2.7 GB → 16 GB 機器邊緣。
- 也直接限制了 multiprocessing:Windows 是 spawn,每個 worker 都要自己拿到 bars,
  pickle 955 MB × 8 worker = 不可行。

**改法**:SoA numpy(`np.float32` × 9 欄)→ 3.09M × 36 B = **111 MB**(float64 則 222 MB),
**8.6x 縮減**;而且可以 `np.memmap` 讓多個 worker 零拷貝共用(繞過 Windows spawn 的複製問題)。

**風險**:`Bar1K` 是**全庫共用型別**(`copycat/live/`、`copycat/server/bars.py`、
`copycat/replay/` 都吃它)。**不要改 `Bar1K` 本身** —— 在 backtest 層新增一個
`BarsArray`(SoA)並提供 `Bar1K` ↔ `BarsArray` 的雙向轉換,只在 backtest 內部流通。

**effort**:M(backtest 內部)/ 不要碰 live 那半

---

### F-10 `fade_features` 對同一個 window 重掃 40–64 次
**medium · 熱路徑 · location `copycat/backtest/fade_features.py:135-152, 117-132, 94-114`**

```python
def _bid_exhaustion(bars, trig_idx):
    w = bars[: trig_idx + 1]
    for thr in thresholds:        # 8
        for lb in lookbacks:      # 5
            window = w[-lb:] if len(w) >= lb else w
            for b in reversed(window):    # ← 40 個組合各自重掃
                total = b.up_volume + b.down_volume
                ...
```

**證據**:實測 `fade_trigger_features` = **231 µs**,產出 197 欄。
`_open_eq_high_count` 8×8=64 欄、`_price_vol_divergence` 9×5=45 欄、`_bid_exhaustion` 8×5=40 欄
—— 149/197 欄來自這三個三層迴圈。

**影響**:n_triggered(~4,000)× 17 臂 = 68,000 次 → **~16 s**。量級不大,
但 walk-forward 模式下會乘上 fold 數。

**改法**:三者都可以化成 prefix/cummax:
- `_open_eq_high_count`:`ratio = (high - open) / open` 一次算完 → 對 8 個 tol 做
  `np.cumsum(ratio < t)`,8×8 一次取差分。
- `_price_vol_divergence`:`cond_d = (high[1:] > high[:-1]) & (vol[1:] < vol[:-1]*(1-d))`
  → `np.cumsum` 後對 9 個 n 取窗和。
- `_bid_exhaustion`:「連續幾根 up 比 < thr」= 反向 run-length,一次掃出
  `run_len[i]` 後 5 個 lookback 只是 `min(run_len[-1], lb)`。

**風險**:這 149 欄的數值是 GA 的輸入,**改一個浮點就換一組規則**。
必須以 golden fixture(現成的 `out/fade_ga/rules_final.json` 或新錄一份 feature dict)
逐欄比對。`tests/backtest/test_features.py`(222 行)只覆蓋 tday 的 `features.py`,
**fade_features.py 沒有專屬測試檔** —— 先補 characterization 再動。

**effort**:M(含補測試)

---

### F-11 `stratified_permutation_p` 5,000 × 250 層的純 Python shuffle
**medium · 非熱路徑但單次分鐘級 · location `copycat/backtest/fade_diagnose.py:149-179`**

```python
for _ in range(iters):              # 5,000
    for items in by_stratum.values():   # ~250 個交易日
        k = sum(1 for _, is_a in items if is_a)
        vals = [v for v, _ in items]
        rng.shuffle(vals)
        sa += sum(vals[:k]); sb += sum(vals[k:])
```

**證據**:`configs/fade_uc_round4.json` 的 `diagnose_perm_iters: 5000`;
`_comparison_and_verdict` 呼叫 **2 次**(單層 + 日×成交額雙重分層),
`diagnose_pool_fade` 對全期間 + forward 段各一次 → **4 次 × 5,000 × 250 = 5M 次 shuffle**。

**改法**:numpy 向量化 —— 把每個 stratum 的值攤平成 `(n_iters, n_vals)` 的矩陣,
用 `np.argsort(rng.random((iters, n)), axis=1)` 一次產生所有排列,再 `cumsum` 取前 k 個和。
或者用 `np.random.Generator.permuted(arr, axis=1)`。預期 **20–50x**。

**風險(關鍵)**:`rng = random.Random(seed)` 的確定性是報告可重現性的一部分
(`diagnose_perm_seed: 42` 寫在 config、報告數字已落在 `docs/evidence/uc_pool_fade_*.md`)。
**換 RNG = 換數字**,舊報告不可重現。
→ 若要改,必須:(a) 用 `numpy.random.Generator(PCG64(seed))` 並明確宣告「這是新基準」,
(b) 保留舊路徑於 `--legacy-rng` 旗標下,(c) 在報告頭註明 RNG 版本。
**或者乾脆不改** —— 這是離線一次性診斷,分鐘級可接受(見 §7)。

**effort**:M(含重現性處置)

---

### F-12 `rules_final.json` 會在 universe > 14,284 筆時直接 raise
**high(scaling landmine) · location `copycat/backtest/fade_pipeline.py:718-732` + `search.py:129`**

```python
# search._entry 產出的 rule dict 含:
"mask": mask,          # ← 長度 = n_rows bits 的大整數
# fade_pipeline:
atomic_write_text(final_path, json.dumps({"results": all_results, ...}, default=str))
```

**證據**(實測):
```
int_max_str_digits = 4300
RAISES at n_rows= 14300 : ValueError Exceeds the limit (4300 digits) for integer string conversion
threshold bits = 14284
```
目前 universe 5,586 筆(1,682 位數)還安全,但 **已經用掉 39% 的預算**。
擴到全市場事件(11,048 全收 + 放寬 gap)或改用多年資料就會炸。

**影響**:跑滿 20 小時之後在最後一步寫檔時 `ValueError` —— 最惡劣的失敗時機。
而且這個 mask 對報告讀者毫無用處(是 bitmask 不是規則)。

**改法**:`_entry` 回傳的 dict 裡把 `"mask"` 標成內部欄位,序列化前 `pop`;
或存成 `support_raw` + 命中的 index list(本來就更有用)。
若改成 numpy bool array(F-01)則自然消失。

**風險**:`jaccard_dedupe`(`search.py:233-247`)與 `fade_pipeline` 的
`apply_rule` 路徑會讀 `item["mask"]` —— 只要在**寫檔前**移除即可,in-memory 保留。
**effort**:S

---

### F-13 沒有任何平行化 —— 17 臂 / 4,660 combo / P² 對全是完美平行
**critical · 架構 · location 全庫**

**證據**:`grep -rn "multiprocessing|concurrent.futures|ProcessPool|ThreadPool|joblib" copycat/`
**零命中**。

**影響**:`fade_pipeline.run_fade_pipeline:674-688` 的
`for arm in ALL_ARMS: for params in arm.anchor_params:` 是 17 個完全獨立的 job
(共用唯讀的 `samples` / `daily` / `cfg`,結果 append 到 list)。
單執行緒跑 = 把 8–16 核的機器當單核用。

**改法**:`concurrent.futures.ProcessPoolExecutor`。**Windows 專屬約束**:
- Windows 是 `spawn`,子行程要重新 import 模組並 pickle 所有參數。
  `samples`(5,586 個 frozen dataclass)可 pickle(~5 MB,可接受);
  **`bars` 絕對不能 pickle**(955 MB × N worker)。
- 正確做法:worker 只收 `(arm_name, param_id, data_dir, cfg)`,**自己從
  memmap/npz 載入 bars**(配合 F-08 的欄狀 cache,載入從 11.5 s → ~1 s,
  或 `np.memmap` 直接零拷貝)。
- `ALL_ARMS` 的 `ArmSpec.find_fn` 是 module-level 函式 → 可 pickle;
  但 `ArmSpec` 本身含 callable,建議只傳 `arm.name` 由 worker 端查表。
- **`logging` 在 spawn 下不會繼承 handler** —— 現有的 `logger.info("arm=%s param=%s ...")`
  進度輸出會消失,要接 `QueueHandler`。

預期收益:8 核 → **~6x**(17 個 job 不整除 8,尾巴會浪費;建議把 job 切到 combo 層級)。

**風險**:結果順序必須穩定(`all_results` 進報告的排序)。用
`executor.map` 保序,或 worker 回傳帶 index 再 sort。
`atomic_write_text` 在多行程下不要同時寫同一個檔。
**effort**:M

---

### F-14 `_ga_candidates` 在 walk-forward 下 per fold 重建 predicates,且 `apply_rule` 重算 mask
**medium · 熱路徑 · location `fade_pipeline.py:178-192, 241-279`**

```python
def _ga_candidates(feat, pnl, weights, cfg):
    feature_names = sorted({k for row in feat for k in row if row[k] is not None})
    predicates = build_predicates(feat, feature_names, cfg.quantile_probs)   # 每 fold 重建
    ga_all = list(exhaustive_scan(predicates, pnl, weights, cfg))
    for seed in cfg.ga_seeds:      # 10 seeds
        ga_all.extend(ga_search(predicates, pnl, weights, cfg, seed))
...
for rule in candidates:            # 30
    mask = apply_rule(conds, all_feat)     # ← 重掃 all_feat,O(conds × n_rows) dict 查
```

**證據**:實測 `apply_rule(2 conds, 553 rows)` = 0.117 ms;
`build_predicates` 553 列 → 0.16 s(4,000 列外推 ~8 s);
`exhaustive_scan` 是 F-01 的那顆炸彈,**per fold per arm 各跑一次**。
`cfg.wf_test_starts` 非空時(walk-forward)`_run_walk_forward:220` 的外圈是 fold 數。

**影響**:若 wf_test_starts 有 6 個 fold,fade-search 的 ② 段從 4 小時變 **24 小時**。

**改法**:`_ga_candidates` 內 `feature_names` 與 predicate threshold **應只用 core 子集算一次**
(這是刻意的,避免洩漏),但 **mask 的計算可以共用**:所有 fold 的 `all_feat` 是同一份,
只有選取的 index 不同 → 一次在全集上建 predicate bool 矩陣,fold 只是行遮罩。
配合 F-01 的 numpy 化,這是同一次改動的自然副產品。

**風險(重要)**:threshold 必須來自 core 子集(no-lookahead 紀律,`search.py:53` 註解
「per-regime train 子集分位數」)。**只能共用 mask 的計算方式,不能共用 threshold**。
改錯 = 資料洩漏 = 回測數字全部作廢且無錯誤訊號。

**effort**:M

---

### F-15 `fade_cells` 的 `_split_fw` / `_rec_stats` / list comprehension 在每個變體重跑
**low · 非熱路徑 · location `fade_cells.py:584-595, 610-612, 650-683`**

```python
main_uc = [(s, b) for s, b in main_universe if is_uc_sample(s, watchlist_ids)]   # 每個 _evaluate_roundN 重算
...
for b in cfg.struct_stop_buffers:
    for kind, variant, param, uni, base_key in specs:
        base_tr, capped = _simulate_r3_trades(...)
        stress_tr, _ = _simulate_r3_trades(...)
        in_w, fwd = _split_fw(base_tr, cfg.forward_start)    # 字串比較 × n_trades
```

**證據**:`is_uc_sample` 對每個 sample 做 `broker_ids.split("|")`(每次配一個 list);
`_split_fw` 每次對整個 trades list 做兩次字串比較掃描。
實測 `_simulate_r3_trades` 0.11–0.23 s,這些 helper 遠小於它。

**影響**:**可忽略**(round 4 全跑 ~10 s)。列出來只為了說明「這裡不是瓶頸」。

**改法**:不改(見 §7)。若真要做,`is_uc_sample` 可在 `FadeSample` 建構時預算成
`frozenset` 欄位,`_split_fw` 可預排序後 `bisect`。

**effort**:S(但不建議)

---

### F-16 `build_universes` 解析 events.csv 三次
**medium · location `copycat/backtest/fade_cells.py:1928-1947`**

```python
main_samples, main_counts = build_fade_universe(data_dir, events, cfg)
low_cfg = dataclasses.replace(cfg, fade_gap_min=-0.095, fade_gap_max=0.01)
low_samples, low_counts = build_fade_universe(data_dir, events, low_cfg)     # 再讀一次 csv
...
cellb_samples, cellb_counts = build_fade_universe(data_dir, events, cellb_cfg)  # 第三次
```

**證據**:`build_fade_universe` 實測 8.38 s(含 read_bars);三次 = 25 s,
與 `build_universes` 實測 32.1 s 吻合。三次唯一差別只是 `fade_gap_min/max` 這兩個純量門檻。

**改法**:一次掃 csv + 一次 read_bars → 算出每列的 `gap`,三個 universe 只是三組
`gap` 區間過濾。預期 32.1 s → **~9 s**(**3.5x**),再加 F-08 的 bars cache → ~4 s。

**風險**:`DayTradeIndex` 的 `in_disposition` / `eligible` 與 counts 字典的語意必須逐欄保留
(`excluded_high_gap` / `excluded_low_gap` 等計數會進報告 `universe_counts_*`)。
`tests/backtest/test_fade_universe_filter.py`(115 行)在,先跑過。

**effort**:M

---

### F-17 `fade_cells.py` 2007 LOC 混了「評估引擎」與「三份 markdown writer」
**low(架構) · location `fade_cells.py:1018-1392, 1663-1838, 1841-1910`**

**證據**:`_write_round3_report`(148 行)/ `_write_round4_report`(225 行)/
`_write_round5_report`(176 行)/ `write_cells_report`(70 行)= **619 行純字串組裝**,
另有四個 `_evaluate_roundN`(round2 118 行 / round3 141 / round4 251 / round5 259)。

**影響**:非效能;但要把評估段改成向量化版本時,**每個 round 的 writer 都要重讀一次
result dict 的形狀**,而四個 round 的 result schema 只有部分重疊(`round3` / `round4` /
`round5` 布林旗標分派)。這是「改一個地方要驗四份報告」的結構。

**改法**:把三個 writer 抽到 `fade_cells_report.py`,`fade_cells.py` 只留評估。
`write_cells_report` 的分派邏輯(`fade_cells.py:1841-1852`)保持不變。

**風險**:純搬移,報告 byte 必須完全相同(`docs/evidence/uc_cells_*.md` 是既有證據)。
`tests/backtest/test_fade_cells*.py`(783 行)在。

**effort**:M

---

### F-18 回測與實盤是兩套獨立實作,零共用、零 parity fixture
**critical(量化系統) · location `copycat/backtest/` vs `copycat/live/signal_state.py` + `copycat/engine/`**

**證據**:
```
$ grep -rn "from copycat.backtest" copycat/ --include=*.py | grep -v "^copycat/backtest/"
copycat/cli.py:204,277,278,293,294,308,309,323,324,338,339      ← 只有 CLI

$ grep -rn "backtest" copycat/live/ copycat/server/ --include=*.py
(無命中)
```
- 回測側:`fade_simulate._simulate_core` 吃 `list[Bar1K]`(**float 張數 / 分鐘 bar**),
  出場語意含 `guard_limit_dist` / `disaster_retrace` / `struct_ratchet` / `inner_flip`。
- 實盤側:`copycat/live/signal_state.py`(855 行)吃 tick(**int 毫元**),
  自有 `_eval_cdp` / `_eval_surge` / `_eval_pullback` / `_eval_volume` / `_eval_sweep` /
  `_eval_limit_tick`,再經 `server/signal_policy.py` 的四條政策 P/B-a/B-b/S。
- 兩邊**概念重疊**(內盤比、鎖板、爆量、回落)但**沒有一行共用程式碼**,
  也**沒有任何 parity fixture**(對照 CLAUDE.md §4 裡 CDP/MA、overlay、
  signal param 都有 golden fixture parity —— 唯獨「策略計算本身」沒有)。

**影響(這是量化系統最經典的致命傷)**:
1. 回測出來的 EV 與實盤實際成交的 EV 沒有任何機制保證一致。
2. `docs/evidence/` 裡所有 fade round 2–5 的判定(D5 / Q2 / Q3)都是對
   `_simulate_core` 的判定,而實盤跑的是 `signal_state` + `signal_policy` —— **兩者從未對帳**。
3. memory 索引顯示現況已經是「訊號現階段 = 輔助」「影子期四週」,
   也就是實務上已經在用人工對帳代替 code-level parity。

**改法(建議的量化系統重構主軸)**:
- 抽出一層 **strategy kernel**:輸入 = 一個 bar/tick 序列的欄狀陣列 + 一顆 frozen params,
  輸出 = `(entry_idx, exit_idx, exit_reason, pnl)`。回測端批次餵歷史、
  實盤端逐 tick 餵同一個 kernel 的增量版本。
- 最低限度(不動架構):建立 **replay parity gate** ——
  拿一天的真實 tick 餵 live 路徑產生訊號,同一天的 1K 餵回測路徑產生訊號,
  斷言兩邊事件集合的對稱差 ≤ 已知白名單。專案已有 `copycat/replay/` +
  `copycat validate` 的 golden gate 基礎設施(`CLAUDE.md §1`),可以延伸。

**風險**:這是最大的一項改動,且會同時觸碰 CLAUDE.md §4 的多條契約
(訊號列 `notify` 欄、政策列形狀、掃單簇 parity fixture)。
**不建議在效能重構的同一批做** —— 但如果目標是「要用來下實單」,這是最高優先的架構債。

**effort**:XL

---

### F-19 `fade_pipeline` 的 `mkt_daily_rows` 恆為 None —— 7 欄大盤特徵是死碼
**low · location `fade_pipeline.py:669, 455-457`**

```python
mkt_daily_rows: list[dict[str, Any]] | None = None      # ← 從未賦值
...
mkt_daily_feats = None
if mkt_daily_rows:                                       # ← 永遠 False
    mkt_daily_feats = compute_mkt_daily_features_full(mkt_daily_rows, sample.date)
```

**證據**:`run_fade_pipeline:669` 宣告後就沒有任何寫入點;
`compute_mkt_daily_features_full`(`market_features.py:39`)因此永不被 fade 路徑呼叫。
實測特徵欄數 197 而非 docstring 宣稱的「~224」—— 差的正是大盤 7 欄 + 其他未接線欄位。

**影響**:非效能。但 `compute_mkt_daily_features_full` 內是 O(n) 線性找日期
(`for i, row in enumerate(daily_rows): if row[date_key] == t_date`),
如果將來接線且 daily_rows 是百萬列的 prices.csv,會變成每個 sample 一次全表掃描
→ **5,586 × 1M = 5.6G 次比較**。接線前先換成 dict 索引。

**改法**:現在先在 `_ga_candidates` 的 `feature_names` 註解中說明實際欄數;
若要接線,`daily_rows` 先建 `{date: idx}` 索引。

**effort**:S

---

### F-20 `_simulate_core` 的 `post_bars_so_far` 是 O(n²) 的隱性成長 list
**medium · 熱路徑 · location `fade_simulate.py:145, 178, 199` + `fade_tp.py:53,150,179,214,321`**

```python
post_bars_so_far: list[Bar1K] = []
for b in post:
    ...
    post_bars_so_far.append(b)          # 每 bar append
    ...
    tp_fill = check_tp_exit(tp, b, ..., post_bars_so_far, ...)
```
消費端(`fade_tp.py`)每根 bar 都對它做尾端切片:
```python
window = post_bars_so_far[-(lb + 1) : -1]   # _tp1 / check_flush_exit
window = post_bars[-(trend_n + 1) : -1]     # _tp2
window = post_bars[-n:]                     # _tp8
prior  = post_bars[-(2*n+1) : -(n+1)]       # _tp3
```

**證據**:切片本身是 O(window) 不是 O(n)(window ≤ 15),所以**不是**真的 O(n²);
但每根 bar 配置一個新的 list(270 次 × 每次 3–15 個指標複製)。
實測 tp1 = 73.3 µs vs 無 TP 64.8 µs,tp2 = 174.3 µs —— 約 15–170% 的加成。

**影響**:`optimize_rule_tp` 跑 1,927 個 TP,其中 tp1(900)+ tp2(720)全走這條。

**改法**:改用 `collections.deque(maxlen=16)` 只保留最近 16 根
(所有消費端的 window 上界 = `max(tp1_lookback)=15`、`tp2_trend_n=10`、
`tp3_n=8 → 2n+1=17`、`tp4_n=15 → n+2=17`、`tp8_n=5`)→ **上界 17**。
或直接改成 numpy 的 ring buffer(配合 F-03 的 SoA)。

**風險(關鍵)**:`_tp3` 有 `post_bars[: -(n + 1)]` 的 fallback 分支
(`fade_tp.py:214-221`),在 `len(post_bars) < 2n+1` 時會吃**全部歷史**。
改成 deque(maxlen) 會**靜默改變 `_tp3` 的結果**。
→ 必須先確認 `_tp3` 在 `elapsed_bars < 2*n` 時已經 early-return(`fade_tp.py:210`),
若 `elapsed_bars >= 2n` 則 `len(post_bars) >= 2n+1` 必然成立 → fallback 是死碼。
**這一條要先驗證再改**,`tests/backtest/test_fade_phase_b.py`(352 行)是安全網。

**effort**:S(驗證完之後)

---

## 6. 工具選型建議與取捨

### 6.1 建議導入

| 工具 | 用在哪 | 解決什麼 / 預期收益 | 代價 |
|---|---|---|---|
| **numpy** | `search.py` 的 predicate mask(F-01/F-02)、`fade_features` prefix scan(F-10)、`stratified_permutation_p`(F-11)、bars SoA(F-09) | `_evaluate` 618 µs → ~4 µs(**150x**);exhaustive_scan 252 min → ~70 s(**200x**);記憶體 955 MB → 111 MB(**8.6x**) | 打破 `dependencies = []` 的 stdlib-only 哲學。**但 backtest 是 dev-only 路徑**,可以放在 `[project.optional-dependencies] backtest`,runtime(server/live)完全不受影響 —— 這是最小代價的切法 |
| **numba** | `fade_simulate._simulate_core`(F-03 第 2 層) | 240–430 ns/bar → 5–20 ns/bar(**~30x**);317M 次 simulate 從 5.7 h → ~12 min | 重(需 LLVM、Windows wheel 有但編譯首跑慢);且 `_simulate_core` 語意極細,float 運算順序可能與 CPython 不同 → **必須先有 byte-level golden**。**建議排在 numpy 化之後、確認 prefix-scan 之後還不夠快才做** |
| **polars** | 1K store 的欄狀格式(F-08 第 3 層)+ `daily/prices.csv`(1,013,469 列 / 52 MB) | `DailyIndex.load` 目前用 `csv.DictReader` 逐列建 dataclass —— 1M 列大約 6–10 s;polars `read_csv` 約 0.2 s(**30x**)。parquet 1K store:294 MB → ~60 MB,全量載入 11.5 s → ~1 s | 多一個大相依(~40 MB wheel)。**只在 backtest extras**。注意 polars 的 lazy API 與現有的「dict of list + bisect」索引語意不同,`DailyIndex` 的 8 個查詢方法要重寫 |
| **`concurrent.futures.ProcessPoolExecutor`**(stdlib) | 17 臂 / combo 網格 / exhaustive scan 分塊(F-13) | 8 核 → ~6x | 零新相依。**Windows spawn 約束**:不能 pickle 955 MB bars → 必須先做 F-08/F-09(memmap) |
| **`orjson`**(可選) | `read_bars` 的 `json.loads`(F-08 第 2 層) | 180 µs → ~40 µs(**4.5x**),佔單檔 33% | 若已走 parquet 路線就不需要。**兩者二選一,不要都做** |

### 6.2 不建議導入

| 工具 | 為什麼不 |
|---|---|
| **pandas** | 這一區的資料形狀是「per-day 的固定 270 根 bar」+「per-sample 的 197 欄特徵」,前者是規則矩形陣列(numpy 就夠)、後者是一次性的寬表(polars 更快)。pandas 的 index 語意會多帶一層概念且比 polars 慢 2–5x |
| **duckdb** | 沒有 SQL 形狀的查詢需求;全部都是逐 bar 狀態機 + 矩陣運算 |
| **dask / ray** | 資料只有 294 MB,單機 8 核 `ProcessPoolExecutor` 完全夠;引入分散式框架是過度工程 |
| **pyarrow 直接用** | 如果導 polars 就已經帶 arrow;不要兩套 |
| **`numpy` 進 runtime(`dependencies`)** | server/live 路徑完全不需要,加進去會讓 `pyproject.toml` 的 stdlib-only 契約失效,也讓 prod 啟動變慢。**堅持放 extras** |

### 6.3 建議的落地順序(收益 / 風險比排序)

```
第 1 批(低風險、立即收益,不動任何數值語意)
  F-02  exhaustive_scan 的 seen set          S  · 0 行為改變 · 省 0.3–2.7 GB
  F-05  逐 bar import 提到函式頂            S  · 0 行為改變 · 省 ~7 min/臂
  F-12  mask 寫檔前 pop                     S  · 0 行為改變 · 拆掉 scaling 地雷
  F-07  validate lru_cache                   S  · 0 行為改變 · 省 ~3.8 min
  F-06  TP params dict                       S  · 0 行為改變 · tp2 快 ~30%
  F-08a build_universes 的 bars dict cache   S  · 0 行為改變 · 32 s → ~12 s
  F-16  events.csv 只解析一次                M  · counts 需逐欄比對 · → ~9 s

第 2 批(numpy 化核心,需 golden fixture)
  F-01  Predicate mask → numpy bool          M  · ~150x · 先建 (fitness,exp,raw,wsum) golden
  F-01b exhaustive_scan 分塊 matmul          M  · ~200x
  F-14  predicate 矩陣跨 fold 共用           M  · ⚠ 不可共用 threshold(洩漏)
  F-09  BarsArray SoA(backtest 內部)       M  · 8.6x 記憶體 · ⚠ 不要改 Bar1K 本身
  F-10  fade_features prefix scan            M  · ⚠ 先補 characterization

第 3 批(架構級)
  F-04  outcome cache(二進位)              M  · 重跑趨近免費
  F-13  ProcessPoolExecutor                  M  · ~6x · 需 F-09 先做
  F-03  combo 網格 prefix-scan               L  · ~20x
  F-03b numba _simulate_core                 XL · ~30x · 需 byte-level golden

第 4 批(量化正確性,獨立於效能)
  F-18  回測 / 實盤 parity gate              XL · 這是「要下實單」的前提
```

---

## 7. 不要動的地方(反向結論)

1. **`fade_cells` 的評估 pass 本身**(`_simulate_r3_trades` 0.11–0.23 s/pass,
   round 4 全跑 ~10 s)。**這裡換 numpy/polars 是純過度工程** ——
   真正的 32 s 在 `build_universes` 的 JSON 載入,修 F-08/F-16 就好。
   把 `_evaluate_round3/4/5` 向量化要重寫 650 行、重驗 4 份報告,換 10 s → 3 s。不值。

2. **`fade_diagnose.stratified_permutation_p` 的 RNG**(F-11)。
   `random.Random(seed=42)` 的確定性已經寫進 `configs/*.json` 和
   `docs/evidence/uc_pool_fade_2026-07-15*.md` 的數字裡。
   換成 numpy RNG = 舊報告不可重現。這是離線一次性診斷,分鐘級可接受。
   **如果一定要快,只把外圈 5,000 iters 改成 multiprocessing 分塊(每塊自帶 seed 偏移),
   不要換 RNG 演算法** —— 但這也會改數字,所以預設是**不動**。

3. **`quantiles.py` 的兩種分位數演算法**(`quantile_round` vs `quantile_trunc`)。
   檔頭 docstring 明寫「user 2026-07-20 拍板保留,統一演算法會改報告數字 = 行為改動」。
   numpy 的 `np.percentile` 兩種都不等價(它是插值版)。**不要碰**。

4. **`Bar1K` 型別本身**(`copycat/data/models.py`)。它是 live / server / replay 的共用型別,
   `copycat/server/bars.py`、`copycat/live/*`、`copycat/replay/*` 全吃它。
   backtest 要 SoA 就在 backtest 內部轉,不要改上游。

5. **`fade_arms` 的 7 個觸發器**(實測 1–9 µs/sample)。
   總計 17 臂 × 4,000 sample × 5 µs = 0.34 s。向量化毫無意義。

6. **`fade_report.py` / 三份 markdown writer 的效能**。純字串組裝,毫秒級。
   (F-17 是架構理由不是效能理由。)

7. **`_simulate_core` 的出場優先序 / tie-break 邏輯**
   (`fade_simulate.py:310-345` 的 `worst = max(...)` 與 `_REASON_RANK`)。
   這是「衝突:停損 > 停利/TP > 13:00 > 收盤(取最差)」的業務語意,
   任何向量化改寫都必須逐條保留。**不要因為「向量化比較好寫」就改成別的優先序**。

8. **`data/daily/prices.csv` 的 `spread` 缺值語意**(`daily.py:46`:
   空字串/缺欄 → None,0.0 是合法平盤值)。換 polars 時 `read_csv` 的
   null 推斷會把空字串變成 null 沒錯,但也可能把 `0` 那欄推成 int —— 要顯式 schema。

---

## 8. 量化系統視角:回測 vs 實盤(問題 8 的正面回答)

**答:是兩份,而且沒有任何對帳機制。**

| 面向 | 回測(`copycat/backtest/`) | 實盤(`copycat/live/` + `copycat/server/`) |
|---|---|---|
| 輸入粒度 | 1 分鐘 Bar1K(float,張) | tick(int,毫元)+ 五檔 book |
| 價格型別 | `float` | `int`(毫元,`copycat/market.py` 的毫元整數運算) |
| 進場判定 | `fade_arms` 7 臂 / `fade_cells` 三格 / `fade_vote` 三票 | `live/signal_state.py` 的 CDP 穿越 / 爆拉跌 / 爆量 / 鎖板 / 掃單簇 |
| 出場判定 | `_simulate_core` 的 guard / disaster / struct / ratchet / inner_flip / TP 樹 | **不存在**(目前只發訊號,不管出場) |
| 政策層 | 無(是 D5 / Q2 / Q3 統計判定) | `server/signal_policy.py` 四條政策 P / B-a / B-b / S |
| 成本模型 | `_round_trip_cost`(fee × 2 + intraday_tax)+ slippage_ticks | `frontend/src/lib/ladder-position.ts::positionEcon`(**前端 TS**,`SELL_TAX_DAYTRADE` 0.15% / 0.3%) |
| 共用程式碼 | **0 行** | |
| parity fixture | **無** | |

**三個具體風險**:

1. **成本模型有三份**:回測 Python(`fade_simulate._round_trip_cost`)、
   前端 TS(`ladder-position.ts::positionEcon`,含當沖稅減半 / `avg_source` 分支)、
   群益實際扣款。CLAUDE.md §4 已經為 `avg_source` / `today_qty` 建了跨語言 parity 測試
   (`test_avg_source_parity_with_frontend`),但**回測那一份完全在圈外**。
   → 回測的 EV 與實際下單的損益用的是不同的稅率邏輯。

2. **回測驗過的策略(fade 家族)不是實盤在跑的策略(訊號政策層)**。
   memory 顯示 `docs/strategy-decisions.md` 的結論是「政策 P 影子上線」「訊號現階段 = 輔助」,
   也就是**實務上已經知道這兩者沒接起來**。但 code 層沒有任何東西阻止有人把
   fade round 4 的 D5 PASS 當成「可以下單的邊」。

3. **`_simulate_core` 的悲觀假設無法在實盤驗證**:
   `stress_guard_fill_high`(嘎空時成交價取 bar.high)、
   `lock_penalty`(全日鎖死以漲停×1.03 回補)這些都是回測端的假設,
   實盤的 `capital/` 有真實 fills(`OrderRecord` / `FillRecord`),
   但**沒有任何路徑把真實 fills 餵回去校準回測的滑價假設**。

**最小可行的 parity gate 建議**(不動架構):
- 新增 `copycat replay-parity --date YYYY-MM-DD`:
  用同一天的 1K(回測路徑)與 tick jsonl(`data/signals/YYYYMMDD.jsonl`,實盤真相源)
  各跑一次「同一組進場條件」,輸出兩邊事件時刻的對稱差。
- 把真實 `capital/store.py` 的 fills 成交價 vs `_simulate_core` 的
  `entry = trig.close − slippage_ticks × tick_size` 做分佈對照,
  用實際分佈校準 `slippage_ticks`(目前是寫死的 1 / 2)。
- 這兩件事的價值**遠高於**把回測跑快 10 倍。

---

## 9. 量測方法(要證明快慢怎麼量)

### 9.1 已建立的基準(可直接重跑)

四支腳本已寫在 scratchpad,全部唯讀、不碰 repo:

```
scratchpad/bench_fade.py    universe 建構 / read_bars / simulate 單位成本
scratchpad/bench_fade2.py   combo 數量 / 7 臂觸發率 / feature 成本與欄數
scratchpad/bench_fade3.py   predicate 數量 / _entry / apply_rule
scratchpad/bench_fade4.py   simulate × combo/TP 矩陣 / validate 開銷
scratchpad/bench_cells.py   build_universes / UC 過濾 / _simulate_r3_trades
scratchpad/bench_parse.py   read_bars 四段拆解(read_text/json/ctor/exists)
scratchpad/bench_scan.py    _evaluate 隨 popcount×n_rows 的二次爆炸 + seen set 記憶體
```

執行:`.venv\Scripts\python.exe <script>`(cwd 無所謂,腳本自己 `sys.path.insert`)。

### 9.2 端對端的真實量測(尚未做,建議補)

```powershell
# fade-cells 全鏈(--out 指到 scratchpad,不污染 repo out/)
Measure-Command {
  .venv\Scripts\python -m copycat fade-cells `
    --config configs\fade_uc_round4.json `
    --out $env:TEMP\bench\cells_r4 `
    --watchlist watchlists\five_tigers.json `
    --report-date 2026-09-13
}

# fade-search:先用縮小的 config 抓斜率,不要直接跑全量(推估 15–25 h)
#   建一份 configs 副本(放 scratchpad),把:
#     s1_stall_bars / s2_swing_lookback / s3_trail / s4_fixed / s5_target 各砍到 2 值
#     ga_seeds → (1,)  ga_generations → 20
#   → combo 數從 4,660 降到約 100,跑完之後以 O(combo × n_trig) 線性外推
```

### 9.3 逐段 profile 探針

```powershell
# cProfile(全鏈,tottime 排序)—— fade-cells 可直接跑
.venv\Scripts\python -X importtime -m cProfile -s tottime -o $env:TEMP\cells.prof `
  -m copycat fade-cells --config configs\fade_uc_round4.json --out $env:TEMP\bench\c

# 看 top
.venv\Scripts\python -c "import pstats;pstats.Stats(r'$env:TEMP\cells.prof').sort_stats('tottime').print_stats(30)"
```

- **`_evaluate` / `bit_indices` 的二次性驗證**:固定 popcount 比例(50%),
  掃 n_rows ∈ {500, 1000, 2000, 4000, 8000},畫 `µs vs n_rows` ——
  應該看到近乎線性斜率(因為每個 bit 的成本 ∝ n_rows),即總成本 ∝ n²。
  這條曲線是 F-01 的判準:修好之後應該變成平的(numpy bool 的成本 ∝ n,
  單次從 618 µs → ~4 µs 且斜率極小)。
- **記憶體**:`tracemalloc.get_traced_memory()` 已驗過 955 MB;
  改成 SoA 後同一個探針應回報 < 150 MB。
- **平行化驗收**:`ProcessPoolExecutor(max_workers=k)` 對 k ∈ {1,2,4,8}
  量 wall-clock,畫 speedup 曲線;Windows spawn 下若 k=8 的 speedup < 3,
  代表 bars 的重複載入(F-08)還沒解決。
- **正確性 gate(每一批改動都要過)**:
  `pytest -q tests/backtest` + `python -m copycat validate`
  + **新增**:對 `out/fade_cells_r4/cells_2026-07-16.json` 的逐欄 float 比對
    (現成證據檔在 `docs/evidence/uc_cells_2026-07-16-round4.md`)。

---

## 10. Open questions(需要 user 回答 / 需要實跑才知道)

1. **`fade-search` 現在還會跑嗎?** `out/` 底下有 `fade_ga`、`fade_round1`,
   但 `docs/evidence/` 最新的 fade 證據是 2026-07-17 的 round 5,
   而 memory 顯示 09-06 起的主軸已經轉到「訊號研究 + 影子政策層」。
   → 如果 fade-search 已經凍結不跑,那 F-01/F-03/F-13 的 20 小時就不是痛點,
     優先序要重排(F-18 的 parity 才是)。**這一題決定整個 §6.3 的順序。**

2. **walk-forward 模式實際跑過幾個 fold?** `cfg.wf_test_starts` 在所有
   `configs/fade_uc_round*.json` 裡都沒設 → 目前都走單 split 路徑。
   若打算啟用 walk-forward,F-14 的成本會乘上 fold 數。

3. **universe 會不會擴大?** 目前 5,586 筆 / 11,048 events。
   F-12 的 14,284 筆天花板、F-02 的 2.7 GB seen set 都是「擴大後才炸」。
   要不要現在就修,取決於這題。

4. **`diagnose_perm_iters: 5000` 的數字有沒有被引用在已發表結論裡?**
   如果有(看 `docs/evidence/uc_pool_fade_*.md` 的 p 值),F-11 就只能加平行化不能換 RNG。

5. **可以接受在 `pyproject.toml` 加 `[backtest]` extras 嗎?**
   runtime 仍是 stdlib-only,但 `numpy` / `polars` 會進 dev 環境。
   這與 CLAUDE.md 的 stdlib-only 精神有張力 —— 需要 user 拍板。
   (我的建議:接受,因為 backtest 從不上 prod host,且 `copycat/backtest/`
   與 runtime 零 import 耦合,extras 的隔離是乾淨的。)

6. **`_tp3` 的 `post_bars[: -(n + 1)]` fallback 分支是不是死碼?**(F-20)
   需要確認 `elapsed_bars >= 2n` 是否蘊含 `len(post_bars) >= 2n+1`。
   從 `_simulate_core:200` 的 `elapsed_bars += 1` 與 `post_bars_so_far.append(b)`
   同步遞增看來應該是,但鎖死凍結 bar 那條路徑(`fade_simulate.py:177-178`)
   兩者都加,所以應該成立 —— **需要一條測試釘死才敢改成 deque(maxlen)**。

7. **numba 在這台 Windows + Python 3.13 上裝得起來嗎?**
   numba 對新版 CPython 的支援通常落後一兩個版本。若 3.13 沒有 wheel,
   F-03b 就要換成 Cython 或直接放棄(prefix-scan 那層已經有 20x)。

8. **目前 `fade-search` 有沒有人實際量過 wall-clock?**
   §4 的 15–25 小時全是由實測單位成本外推的**推估**,沒有端對端實錄。
   §9.2 的縮小 config 跑法可以在 10 分鐘內把外推換成實測。
