# T2-bench-numeric —— 擂台:數值計算(實測報告)

**日期**:2026-09-13
**區塊**:`T2-bench-numeric`
**目標**:把「numpy 能不能幫上 copycat 的數值熱路徑」從推估變成實測。
**紀律遵守**:未改動 repo 任何檔案、未動 `C:/side-project/copycat/.venv`、未啟動 server、未下任何單。
所有 A/B 跑在拋棄式 venv `…/scratchpad/venvs/T2/`。

> **讀法**:§0 是一頁結論;§1 是環境;§2–§6 是五個對決的原始數字;§7 回答「array 建構開銷」那個統一問題;
> §8 是建議;§9 是意外;§10 是我沒量到的東西。**每個數字都標了「實測」或「換算」或「未量」。**

---

## 0. 一句話結論

**numpy 在這套系統的即時熱路徑上,五個對決輸掉四個半。**
唯一真正贏的是相關係數(23x),但同一個對決裡**純 Python 增量版贏得更多(208x)且不需要新相依**。

| 對決 | 現況(實測) | 最佳候選 | 倍數 | numpy 有沒有贏? |
|---|---|---|---|---|
| 1 相關係數 | 9.32 ms / 次 | **純 Python running sums** 0.044 ms | **208x** | ❌ numpy ring 只到 23x |
| 2 個股狀態機 | 1.49–1.70 µs / tick | **不動** | 1.00x | ❌ 系統級反而差 52x |
| 3 訊號窗 sum | 1.4–293 µs / tick(隨窗長) | **純 Python running sum** 0.10 µs | **最高 2,931x** | ❌ numpy ring 慢 6–29x |
| 4 全市場廣度 | 4.44–6.13 ms / 10 s | **純 Python 手工優化** 2.68 ms | 1.71x | ❌ numpy 平手(1.05x 慢 ~ 1.09x 快) |
| 5 K 線 / 疊圖 | 0.2 µs ~ 1.25 ms | **不動** | 1.00x | ❌ 最壞慢 80x |

**這五個對決同時指向同一件事**:這些熱路徑的成本不是「算術太慢」,是
**「本來可以只算一次的東西,每次都從頭重算」**。
把「重算」改成「增量」的收益(208x / 2,931x)遠大於把「重算」改成「向量化重算」的收益(23x / 1.09x)。
numpy 加速的是後者,而後者不是這裡的病。

---

## 1. 環境與可重現性

```
OS        Windows-11-10.0.26200-SP0
Python    3.13.13 (tags/v3.13.13:01104ce, Apr 7 2026, MSC v.1944 64-bit AMD64)
venv      C:/Users/USER/AppData/Local/Temp/claude/C--side-project-copycat/
          2f320e31-68fc-4cfd-859c-b63b666e7f79/scratchpad/venvs/T2/
numpy     2.5.3      (pip install numpy;有 win_amd64 wheel,無編譯)
pyzmq     27.2.0     (只為了 import copycat.server.bars 能過 —— 那條 import 鏈會
                      拉到 live/tc4.py;**沒有連任何 socket**)
```

**專案 `.venv` 全程未被觸碰**(`pytest` / `ruff` / `pyright` / `copycat validate` 的驗證鏈乾淨)。

### 量測方法

- `time.perf_counter()`,每項 warmup 2–3 次後取 15–500 次重複,回報 `min` / `p50` / `p95`。
- **報 p50 為主**;Windows 的 timer 精度(15.6 ms)不影響這裡,因為量的是 CPU-bound 區段而非 sleep。
- 微秒級項目(對決 3 / 5)用高重複次數攤提;µs 欄位的最小解析度約 0.1 µs。

### 輸入資料

| 對決 | 輸入形狀 | 來源 |
|---|---|---|
| 1 | 11 腿(base TXF + 10 條)× 窗 (60,300,1800) × 1800 筆/秒級取樣;SXF/VX 依 `configs/correlation.json` 標 `sparse` → 模擬 25% 有值 | **形狀取自 repo 真實設定檔**;價格序列為合成隨機漫步(共同因子 + 個別噪音,σ=8e-5/秒) |
| 2 | 當日 2,247 / 10,000 / 30,598 筆成交,價格毫元整數,side 三值隨機 | 筆數取自任務給定的 `logs/` 實測(median 2,247、最熱 30,598);tick 內容合成 |
| 3 | 300 秒窗內筆數 42 / 100 / 300 / 567 / 1,000 / 3,000 / 10,000 | 42 與 567 是由上面兩個日筆數**換算**(日筆數 ÷ 16,200 秒 × 300);其餘為叢聚情境 |
| 4 | 1,800 檔(另掃 500 / 5,000 / 20,000),含 2% 漲停 / 1.5% 跌停 / 5% 觸及未鎖 | 檔數取自任務給定的實測;欄位值合成,毫元對齊真實 tick 表 |
| 5 | 1,500 根日 K(含跳過週末的真實日期序列) | 根數取自任務給定 |

**合成資料的侷限見 §10。**

### 腳本與原始輸出

| 腳本(絕對路徑) | 內容 |
|---|---|
| `…/scratchpad/verify-bakeoff/bench_t2_c1_corr.py` | 對決 1 主擂台(A/B/C/D/E 五版 + 成本拆解 + 漂移) |
| `…/scratchpad/verify-bakeoff/bench_t2_c1b_corr_exact.py` | 對決 1「位元等同」版(F/G)+ dense 上界 + 漂移曲線 |
| `…/scratchpad/verify-bakeoff/bench_t2_c1c_error_source.py` | 誤差源隔離:公式 cancellation vs 增量加減 |
| `…/scratchpad/verify-bakeoff/bench_t2_c1d_boundary.py` | 窗邊界 off-by-one 的證明(§9 意外 1) |
| `…/scratchpad/verify-bakeoff/bench_t2_c2_stockstate.py` | 對決 2 主擂台(ingest + snapshot 聚合 + 正確性) |
| `…/scratchpad/verify-bakeoff/bench_t2_c2b_control.py` | 對決 2 對照組:分離「numpy 效應」與「延後效應」 |
| `…/scratchpad/verify-bakeoff/bench_t2_c345.py` | 對決 3 / 4 / 5 |
| `…/scratchpad/verify-bakeoff/bench_t2_c4b_breadth_profile.py` | 對決 4 成本拆解 + cProfile |
| `…/scratchpad/verify-bakeoff/bench_t2_c4c_ticktable.py` | tick 表向量化:全域逐值 parity + 速度 |
| `…/scratchpad/verify-bakeoff/bench_t2_c4d_pyopt.py` | 對決 4 純 Python 手工優化對照組 |

重跑方式(工作目錄必須是 repo root,腳本靠 `sys.path.insert` 讀 repo 的 `copycat/`):

```
cd C:\side-project\copycat
set PYTHONUTF8=1
…\scratchpad\venvs\T2\Scripts\python.exe …\scratchpad\verify-bakeoff\bench_t2_c1_corr.py
```

---

## 2. 對決 1(最重要):相關係數 `CorrState.correlations()`

### 2.1 現況演算法(讀原始碼確認)

`copycat/live/corr_state.py:113-136`。**不是 `statistics.correlation` 一次就結束**,而是:

1. 每腿呼叫 `_paired_returns(leg, now)`(`:82-111`):把整條 1800 筆中價 deque 掃過,
   `dict(leg_series)` 建一張 ts→mid 表,逐筆判相鄰、逐筆 `math.log` 算對數報酬,
   最後再一次 list comp 過濾 `ts >= now - 1800`。**每秒為每一腿從頭重做一次。**
2. 每腿每窗再兩次 list comp 過濾出 `xs` / `ys`(共 10×3×2 = 60 次 list comp)。
3. 最後才是 `statistics.correlation(xs, ys)`(stdlib,內部 `fsum`)共 30 次。

### 2.2 實測:五個候選 + 兩個「位元等同」變體

**單次 `correlations()` 成本(10 腿 × 3 窗 × 1800 樣本)**

| 版本 | min | **p50** | p95 | vs 現況 | max\|Δr\| vs 現況 |
|---|---|---|---|---|---|
| **A 現況**(`statistics.correlation` 整批) | 8.886 | **9.153** | 11.616 | 1.00x | — |
| B numpy 整批(每次從 deque 建陣列) | 1.531 | **1.615** | 2.376 | 5.7x | 5.551e-16 |
| **C numpy ring buffer**(push 寫入預配置陣列,只切片) | 0.390 | **0.402** | 0.528 | **22.8x** | 5.551e-16 |
| **D 純 Python 增量 running sums** | 0.012 | **0.023** | 0.024 | **398x** | 2.331e-15 |
| E numpy 增量(向量閉式) | 0.032 | **0.032** | 0.065 | 286x | 2.331e-15 |
| F 增量 paired-returns + 逐窗過濾 + `statistics.correlation` | 3.626 | **3.881** | 4.475 | 2.4x | **逐位元相同** |
| G 每(腿,窗)獨立 deque + `statistics.correlation` | 2.411 | **2.908** | 3.813 | 3.1x | **逐位元相同** |

(單位 ms;`n` 欄位在所有版本全部相符,`None` 分歧 0 格)

**`push()` 成本(增量版把成本搬到這裡;push 也是每秒 1 次,必須一起算)**

| 版本 | p50 (ms) |
|---|---|
| A push | 0.004 |
| C push(寫 numpy ring) | 0.003 |
| D push(純 Python running sums) | 0.021 |
| E push(numpy running sums) | 0.018 |
| F push | 0.007 |
| G push | 0.010 |

**每秒總成本(push + correlations)**

| 版本 | 每秒 (ms) | vs 現況 | 相依 | 數值風險 |
|---|---|---|---|---|
| A 現況 | **9.157** | 1.00x | 無 | — |
| G(位元等同) | 2.918 | 3.1x | **無** | **零** |
| F(位元等同) | 3.888 | 2.4x | **無** | **零** |
| C numpy ring | 0.405 | 22.6x | numpy | 5.6e-16 |
| E numpy 增量 | 0.050 | 183x | numpy | 3.9e-15 |
| **D 純 Python 增量** | **0.044** | **208x** | **無** | 3.9e-15 |

### 2.3 A 的成本拆解 —— 數學只佔 20%

| 區段 | p50 (ms) | 佔比 |
|---|---|---|
| `_paired_returns` × 10 腿 | 5.594 | **61%** |
| 逐窗 list comp 過濾(60 次) | 1.770 | **19%** |
| `statistics.correlation` × 30(1800 樣本那次 = 0.160 ms) | ≈ 1.8 | 20% |

**檔頭註解量的是最後那 0.160 ms,而每秒真正燒掉的是前面那 7.4 ms。**
`corr_state.py:5-7` 寫「`statistics.correlation` 對 1800 樣本實測 0.15 ms,整輪 tick 外推不到 1 ms」——
0.15 ms 這個數字本身**實測正確**(我量到 0.160 ms),錯的是「外推不到 1 ms」:
外推時漏掉了 `_paired_returns` 與 60 次 list comp。

### 2.4 dense 上界(對照 X4-numeric 報告的 13.60 ms)

把 SXF / VX 的稀疏拿掉(全 11 腿每秒都有中價):

| 版本 | p50 (ms) |
|---|---|
| A 現況 | **12.240** |
| F | 5.042 |
| G | 3.118 |

**X4-numeric 報告的 13.60 ms 與本次 dense 情境的 12.24 ms 同量級,互相印證。**
我主表用的 9.15 ms 是「SXF/VX 稀疏」的實況形狀(配對報酬總數 14,632 vs dense 的 17,990)。

### 2.5 正確性:浮點加總順序的影響

- **B / C(numpy)**:max|Δr| = **5.551e-16**。原因是 `statistics.correlation` 用 `fsum`(精確加總)
  而 numpy 用成對加總(pairwise),兩者在 1800 筆上的差是 ULP 量級。
- **D / E(閉式公式增量)**:窗對齊後 max|Δr| = **2.3e-15**;連跑 32,400 次 push(9 小時)後
  仍只到 **3.858e-15**(§9 意外 1 的「修正窗邊界」那半)。
- **F / G**:**逐位元相同**(用 `!=` 比浮點,不是 `isclose`)。因為它們把同一份 `xs`/`ys`
  餵給同一個 `statistics.correlation`,只是不再每秒重推那份 list。

**契約影響**:
- 前端 `frontend/src/components/corr/CorrPanel.tsx:25` 是 `r.toFixed(2)` → 顯示解析度 5e-3。
  5.6e-16 / 3.9e-15 都比它小 **12 個數量級**,不可能翻動任何一位顯示。
- `tests/` 內與相關係數相關的只有 `tests/live/test_corr_state.py` 與
  `tests/server/test_corr_routes.py`,**`tests/fixtures/` 沒有任何 corr 的 golden fixture**
  (`ls tests/fixtures | grep -i corr` 空)。
- `CLAUDE.md §4` 的跨檔契約清單裡,corr 只有兩條:「江波圖調色盤色數 ≥ 腿數」與
  「稀疏腿 `sparse` 旗標」—— **都不碰 r 的數值**。
- **結論:數值差異不打到任何既有契約或 golden fixture。** 但 `tests/live/test_corr_state.py`
  若有寫死的 r 期望值,改演算法時要逐條看(未逐條檢,見 §10)。

---

## 3. 對決 2:個股狀態機 `StockState._apply` / `_fold_vp`

### 3.1 實測:每 tick ingest 成本

穩定重跑 3 次(第 1 次冷跑 3.32 µs 為離群值,已排除):

| 版本 | run1 | run2 | run3 | 代表值 | vs 現況 |
|---|---|---|---|---|---|
| **現況 `StockDayState.ingest`**(每 tick 完整增量聚合) | 1.492 | 1.698 | 1.674 | **≈1.6 µs** | 1.00x |
| numpy 延後(寫 int64 陣列) | 0.526 | 0.490 | 0.564 | ≈0.52 µs | 3.1x |
| **純 Python 延後(append 到 4 條 list)** | 0.298 | 0.303 | 0.286 | **≈0.30 µs** | **5.5x** |

(µs/tick;200,000 次攤提。與上一輪報告的 1.96 µs 同量級。)

### 3.2 這個 3x 不是 numpy 的功勞 —— 對照組拆穿它

**純 Python 延後比 numpy 延後快 1.69x。**
numpy 的逐元素 scalar 賦值(`arr[i] = int`)要建一個 numpy scalar 再寫入,比 `list.append` 貴。
所以 §3.1 的加速**完全來自「延後聚合」,一點都不來自 numpy**。

### 3.3 而且「延後」在系統級是淨虧

numpy 版把聚合延到 `snapshot()` 才做。實測 `aggregate()` 成本:

| 當日筆數 | ingest 總計(現況) | ingest 總計(numpy) | numpy 每次 snapshot 聚合 |
|---|---|---|---|
| 2,247(median) | 3.302 ms | 1.087 ms | **0.800 ms** |
| 10,000 | 15.308 ms | 4.539 ms | **2.965 ms** |
| 30,598(最熱) | 46.658 ms | 18.560 ms | **8.960 ms** |

`light_snapshot` 的頻率是**每 60 s × 最多 150 檔**(`CLAUDE.md` 自選上限 150)→ 每檔每日 270 輪。

**全日總成本(最熱 30,598 筆那檔)**

| 版本 | ingest | snapshot 聚合 | 合計 |
|---|---|---|---|
| 現況 | 46.7 ms | **0 ms**(增量已維護好,只是讀屬性) | **46.7 ms** |
| numpy 延後 | 18.6 ms | 270 × 8.96 = 2,419 ms | **2,437 ms** |

**numpy 版全日差 52x。** 更糟的是型態:現況的 1.6 µs/tick 是均勻攤開的;
numpy 版的 8.96 ms 是**每 60 秒一記 event loop 硬停**,正是這次改造要消滅的東西。

### 3.4 正確性

numpy 版的 `aggregate()` 與現況逐欄全等:標量(high / low / vwap)`True`、
VP 全等 `True`、minutes(c / v / i / o / u / h / l 七鍵)全等 `True`,三種筆數都通過。
**所以不是「numpy 做不到」,是「做到了也不划算」。**

### 3.5 判定

**上一輪「換 numpy 只會變慢」的結論成立,但理由要改寫。**
不是「n 太小 numpy 吃虧」(30,598 筆的 n 對 numpy 綽綽有餘),
而是**「這裡已經是增量了,任何批次化都是把 O(1)/tick 換成 O(n)/snapshot」**。
`stock_state.py:60-64` 的註解(刻意逐 tick 折 VP 而不在請求時掃 20k deque)不只是對的,
**它正是本報告在對決 1 和對決 3 要推廣的同一個模式**。

---

## 4. 對決 3:訊號偵測器 `_eval_volume` 的窗和

### 4.1 現況

`copycat/live/signal_state.py:658`:

```python
window_vol = sum(qty for _ts, _price, qty in window)   # ← O(len(window)),每 tick
```

`window` 是 `evaluate()`(`:318-322`)以**時間**逐出的 deque,`surge_window_secs` 預設 300 s。

### 4.2 實測

| 窗長(筆) | 現況 `sum(genexp)` | running sum(純 Py) | numpy `arr.sum()`(ring) | numpy 每次建陣列 |
|---|---|---|---|---|
| 42 | 1.40 µs | **0.100 µs** | 0.60 µs | 2.60 µs |
| 100 | 3.30 µs | **0.100 µs** | 0.60 µs | 4.60 µs |
| 300 | 9.40 µs | **0.100 µs** | 0.60 µs | 11.40 µs |
| 567 | 17.10 µs | **0.100 µs** | 0.70 µs | 21.10 µs |
| 1,000 | 29.90 µs | **0.100 µs** | 0.80 µs | 35.50 µs |
| 3,000 | 90.90 µs | **0.100 µs** | 1.10 µs | 97.20 µs |
| 10,000 | 293.10 µs | **0.100 µs** | 2.90 µs | 326.70 µs |

窗長換算:median 2,247 筆/日 ÷ 16,200 s × 300 s ≈ **42 筆**;
最熱 30,598 筆/日 ≈ **567 筆**。但成交是叢聚的(開盤 / 攻板),3,000 筆是爆量情境的合理上界。

### 4.3 判定

- **贏家 = running sum(純 Python),0.100 µs 恆定**,對 3,000 筆窗是 **909x**、10,000 筆是 **2,931x**。
- numpy ring(把 qty 存在預配置 int64 陣列上)0.6–2.9 µs → 比現況快,但**比純 Python running sum 慢 6–29x**。
- numpy 每次建陣列**比現況還慢**(建構就要 O(n) 迭代一遍 Python 容器,然後才輪到 C reduce)。
- **正確性零風險**:`qty` 是 `int`,Python int 加減無溢位無捨入。機械驗:
  100,000 次 append/popleft,`running sum != sum(window)` 的次數 = **0**。

### 4.4 系統級換算

成本 = (tick 速率)×(窗內筆數),而窗內筆數 ≈(tick 速率)×300 → **成本隨 tick 速率平方成長**。
爆量股開盤 20 tick/s 時窗約 6,000 筆,每 tick 約 180 µs(由 3,000 筆的 90.9 µs 線性外推,**換算非實測**)
→ **每秒 3.6 ms 的 event loop 佔用,只為了一檔股票的一條規則。**
改成 running sum 後是每秒 2 µs。

---

## 5. 對決 4:全市場廣度 `compute_breadth`

### 5.1 實測(1,800 檔)

| 版本 | min | **p50** | p95 | vs 現況 |
|---|---|---|---|---|
| **現況 `compute_breadth`** | 4,292.8 | **4,440.5** | 5,532.2 | 1.00x |
| numpy 向量化 + 同樣組 `rows_out` | 4,894.8 | **5,607.6** | 8,005.9 | **0.79x(慢)** |
| numpy 只算家數(不組 `rows_out`,理論上界) | 1,463.4 | **1,632.1** | 1,936.0 | 2.72x |
| **純 Python 手工優化**(tick 表去重 + `type()` 快路徑) | 2,466.5 | **2,675.3** | 3,683.5 | **1.71x** |

(單位 µs。現況在不同輪次量到 4,440 / 4,572 / 6,128 µs,波動約 ±25%;
與任務給定的 5.42 ms 及 X4 報告的 4.0 ms 同量級。)

### 5.2 n 掃描:numpy 沒有一致方向

| n | 現況 | numpy | 結果 |
|---|---|---|---|
| 500 | 1.957 ms | 1.301 ms | numpy 快 1.50x |
| **1,800**(實況) | 4.386 ms | 4.603 ms | **numpy 慢 1.05x** |
| 5,000 | 16.130 ms | 13.379 ms | numpy 快 1.21x |
| 20,000 | 68.173 ms | 81.331 ms | numpy 慢 1.19x |

**在量測噪音之內,numpy 對這支函式基本是平手。** n = 1,800 不是「不夠大」的問題 ——
是這支函式的成本根本不在可向量化的算術上。

### 5.3 成本拆解(cProfile,1,800 檔 × 20 次)

| 區段 | p50 (µs) | 佔比 |
|---|---|---|
| (b) limit / touched 判定(每列 **4 次** tick 表呼叫) | 1,941 | **44%** |
| (c) `_to_number` × 5–7 欄 | 1,014 | **23%** |
| (a) 組 `rows_out` dict(零 limit 判定) | 469 | 10% |

cProfile `tottime` 前三名被呼叫者:
`_to_number` **252,000 次**、`dict.get` 396,000 次、`isinstance` 504,000 次。

**病因是 Python 函式呼叫次數,不是算術。** numpy 動不了函式呼叫。

### 5.4 但 tick 表**可以**向量化,而且是精確的

`market.py::_tick_milli` 是分段常數函式 → `np.searchsorted` 可完整向量化,**全程 int64,零 float**。

**正確性(實測,不是抽樣)**:對 **0 ~ 2,000,000 毫元逐值**(2,000,001 個值)比對:

| 函式 | 不符個數 |
|---|---|
| `limit_up_milli` | **0 / 2,000,001** |
| `limit_down_milli` | **0 / 2,000,001** |
| `snap_down_milli` | **0 / 2,000,001** |

**速度**:1,800 筆 `limit_up_milli`,純 Python list comp **335.60 µs** → numpy 向量 **13.30 µs** = **25.2x**。

**但這條要打一個大星號**:它等於**把 `market.py` 的規則再抄一份**。
`CLAUDE.md` 已經記載 `snap_down_milli` 與前端 `stock-tick.ts::snapDown` 是跨語言 parity 契約
(靠 `tests/fixtures/vp_parity.json` 鎖住),再加一份 numpy 版就是**第三份會漂的規則**。
漂掉的症狀與既有的一樣:兩個數字都看起來對,零錯誤訊號。

### 5.5 判定

**numpy 整體不建議**(平手且多一個相依)。
**純 Python 手工優化 1.71x,逐鍵全等(21,600 格 0 不符),零相依** —— 這才是這裡的答案。
最大單一浪費是**每列呼叫 `limit_up_milli` / `limit_down_milli` 各兩次**
(`_is_limit` 一次、`_is_touched` 又一次,`market_breadth.py:260-267` 與 `:292-303`),
算一次傳下去就好。

---

## 6. 對決 5:K 線聚合與疊圖

### 6.1 `overlay.compute_cdp` —— n = 1,無事可向量化

| 版本 | p50 |
|---|---|
| 現況(4 個整數四則) | **0.30 µs** |
| numpy 等價(3 元素陣列) | 0.30 µs |

**平手。** 這支是 O(1),連 numpy 的 dispatch 開銷都吃掉了全部空間。

### 6.2 `overlay.compute_ma` —— numpy 明確落敗

| 版本 | p50 | vs 現況 |
|---|---|---|
| `compute_ma(closes, 5)` 現況 | **0.20 µs** | 1.00x |
| numpy `nparr[-5:].sum()//5`(陣列已常駐) | 0.70 µs | **0.29x(慢 3.5x)** |
| `compute_ma(closes, 20)` 現況 | **0.30 µs** | 1.00x |
| numpy `nparr[-20:].sum()//20`(陣列已常駐) | 0.70 µs | **0.43x(慢 2.3x)** |
| numpy **含 `np.array(closes)` 建構** + 20MA | 24.00 µs | **0.0125x(慢 80x)** |

最後一列是「array 建構開銷吃掉向量化收益」的教科書案例:
把 1,500 個 Python int 搬進 int64 陣列要 23.7 µs,而要做的 reduce 只有 20 個元素。

### 6.3 `overlay.build_overlay` —— 1,500 根日 K

| 版本 | p50 | vs 現況 |
|---|---|---|
| 現況 | **86.80 µs** | 1.00x |
| numpy 版 | 170.50 µs | **0.51x(慢 1.96x)** |

正確性:`cdp` / `ma5` / `ma20` / `date` 全等 `True`。
但 `build_overlay` 的 O(n) 部分是 `[b for b in bars if b["date"] < today]` ——
**字串比較 + dict 存取**,numpy 只能接手最後那 5 / 20 個元素的 sum,接手的正好是不花錢那段。

### 6.4 `bars.aggregate_period` —— 1,500 根日 K → 週 / 月

| period | 現況 | numpy | 桶數 | 逐欄全等 |
|---|---|---|---|---|
| W | **1,254.80 µs** | 1,403.60 µs(慢 1.12x) | 301 | True |
| M | **636.50 µs** | 714.70 µs(慢 1.12x) | 69 | True |

原因同上:桶鍵是 `date.fromisoformat` + `isocalendar()`(`bars.py:478-496`),**沒有向量版**,
必須逐根算;numpy 只能接手 h/l/v 的 groupby-reduce,而那段本來就便宜。

### 6.5 `bars.build_minute` 沒有可量的數值段

讀 `bars.py:630-723` 確認:這支是 `async`,主體是 cache 查表 + `await fetch` + list `extend` + 狀態合併,
**沒有任何逐元素數值計算**。它的成本在 IO 與 cache,不在數值 —— 不屬本區塊(T2)範圍。

---

## 7. 統一問題:array 建構開銷有沒有吃掉向量化收益?

**每個對決都要回答的那一題,實測答案:**

| 形狀 | n | 每次呼叫要不要建 array? | numpy 結果 |
|---|---|---|---|
| 對決 5b `compute_ma` | 1,500 → reduce 20 | 要 | **慢 80x** |
| 對決 5b(假設陣列常駐) | 1,500 → reduce 20 | 不要 | 慢 2.3–3.5x |
| 對決 5c `build_overlay` | 1,500 | 要 | 慢 1.96x |
| 對決 5d `aggregate_period` | 1,500 → 301 桶 | 要 | 慢 1.12x |
| 對決 3 窗和 | 42–10,000 → reduce 1 次 | 要 | **比現況還慢** |
| 對決 3 窗和 | 42–10,000 → reduce 1 次 | 不要(ring) | 快 2–100x,但輸給 running sum |
| 對決 4 廣度 | 1,800 → 每列 ~12 個判定 | 要 | 平手 |
| 對決 2 個股狀態 | 2,247–30,598 → 5 種聚合 | 逐元素寫入 | 逐 tick 慢 1.7x;全日慢 52x |
| **對決 1 相關係數** | **1,800 × 30 次 reduce** | 要(B) | **快 5.7x** |
| **對決 1 相關係數** | **1,800 × 30 次 reduce** | **不要(C ring)** | **快 22.8x** |

**三條可以直接拿去用的規則(全部由上表實測支撐):**

1. **每次都要從 Python 容器建 array → 建構本身就是 O(n) 的 Python 迭代**,和純 Python 迴圈同量級。
   收益只剩「reduce 那一段變 C」,而 reduce 通常只佔一小部分。
   **實測 break-even ≈ n 1,000–3,000,而且要在同一份資料上做多次 reduce。**
   copycat 的即時熱路徑幾乎都在這條線的錯誤那一邊。
2. **numpy 唯一穩贏的形狀 = 陣列常駐**(ring buffer,push 時寫入)。
   對決 1 的 C 版就是這個形狀:22.8x。
3. **但只要「增量」這條路走得通,它永遠贏過「向量化重算」**:
   對決 1 是 208x vs 22.8x、對決 3 是 2,931x vs 100x。
   因為增量把複雜度從 O(n) 降到 O(1),而向量化只是把 O(n) 的常數變小。

---

## 8. 建議

### R1 —— 相關係數改增量 running sums(**純 Python,不裝 numpy**)

- **哪裡**:`copycat/live/corr_state.py::CorrState`。`push()` 多維護
  per (leg, window) 的 `(n, Σx, Σy, Σxx, Σyy, Σxy)`;`correlations()` 改閉式公式。
- **收益**:每秒 9.157 ms → **0.044 ms(208x)**,event loop 每秒少停 9 ms。
- **代價**:零新相依(維持 `pyproject.toml` 的 stdlib-only runtime)。
  演算法複雜度上升 —— 檔頭那段「不維護增量統計量」的設計理由要整段改寫。
- **數值**:max|Δr| = 3.9e-15(32,400 次 push 後),比前端 `toFixed(2)` 的解析度小 12 個數量級。
- **阻擋風險**:**窗邊界語意,不是浮點**(見 §9 意外 1)。
  現況對**中價序列**逐出,配對報酬取較晚那筆 ts → 最長窗實際是 1800 筆不是 1801 筆。
  增量版若直接以 `ts >= now - w` 逐出會多留一筆,`Δr` 就變成 1e-3 ~ 2.8e-3 —— **足以翻動 `toFixed(2)` 的第二位**。
  **必要的守門測試**:對同一串 push 跑 N ≥ 5,000 次,逐輪斷言增量版與現況的 `n{w}` **完全相等**
  (比 r 值更靈敏:n 差 1 一定抓得到,而 r 差 1e-3 可能被 `isclose` 放過)。
  另外**照 `tests/live/test_corr_state.py:120-132`(60 窗邊界)補一條 1800 窗的版本** ——
  現有測試對最長窗**沒有**邊界斷言,而 off-by-one 只發生在最長窗(見 §10.4)。

### R2 —— 若 R1 的增量改寫覺得太大,先做「位元等同」那一刀

- **哪裡**:同上,但只把 `_paired_returns` 改成增量維護(push 時 append 一筆、逐出過期),
  數學仍走 `statistics.correlation`。
- **收益**:每秒 9.157 → **2.918 ms(3.1x,G 版)** 或 **3.888 ms(2.4x,F 版)**。
- **代價**:零相依。
- **數值**:**逐位元相同**(實測用 `!=` 比,不是 `isclose`)。
- **阻擋風險**:**零**。同樣的窗邊界陷阱仍在,但因為結果可以拿來逐位元比對現況,
  守門測試寫起來是「兩版同輸入輸出必須 `==`」,比 R1 好驗。
- **判定**:**如果 user 要的是「先拿走 3x 且不冒任何風險」,這是那一刀。**

### R3 —— 訊號窗和改 running sum(**純 Python**)

- **哪裡**:`copycat/live/signal_state.py:658` 的 `sum(qty for ...)`;
  配套在 `evaluate()`(`:318-322`)的 append / popleft 兩處維護 `self._window_qty: dict[str, int]`,
  與 `self._window` 同生命週期(`reset_day` / `drop_code` 同批清)。
- **收益**:1.4–293 µs → **0.100 µs 恆定**。爆量股開盤的最壞情境由「每秒 3.6 ms event loop」降到「每秒 2 µs」。
- **代價**:零相依。多一份必須與 deque 同步的狀態。
- **數值**:**零風險**(int 加減恆等,100,000 次機械驗 0 次不符)。
- **阻擋風險**:低。`_eval_surge` / `_eval_pullback` 讀同一個 `window` 但只取 `window[0]` / `window[-1]`,不受影響。
  唯一要注意的是 `reset_day` / `drop_code` / `apply_backfill` 三個清空點都要同步清 —— 漏一個就是靜默錯值。
  **必要的守門測試**:不變式 `running_sum == sum(qty for _,_,qty in window)`,在隨機 append/popleft 序列上逐步斷言。
- **判定**:**這是全報告 CP 值最高的一條 —— 成本 S、收益最高 2,931x、數值零風險。**

### R4 —— 廣度改純 Python 手工優化(**不要 numpy**)

- **哪裡**:`copycat/market_breadth.py::compute_breadth`。
  把 `_is_limit` / `_is_touched` 合併成一次計算(現況每列呼叫 tick 表 **4 次**,2 次就夠);
  `_to_number` 的 `isinstance` 鏈加 `type() is float/int` 快路徑。
- **收益**:4,440 → **2,675 µs(1.71x)**,每 10 s 的 event loop 停頓少 1.8 ms。
- **代價**:零相依。
- **數值**:**逐鍵全等**(1,800 列 × 12 鍵 = 21,600 格,0 不符)。
- **阻擋風險**:低。`tests/fixtures/breadth_parity.json` 的 oracle 比的是 counts + 逐檔桶推導,
  這一刀不動任何判定規則,只去掉重複呼叫。
- **判定**:**numpy 版在這裡是負收益(0.79x),不要做。**

### R5 —— tick 表向量化:**有條件**,而且不是為了廣度

- **哪裡**:新增一支 numpy 版 `vec_limit_up` / `vec_limit_down` / `vec_snap_down`(`np.searchsorted`,全 int64)。
- **收益**:1,800 筆 335.6 → 13.3 µs(**25.2x**)。但套回 `compute_breadth` 整體只從 4.44 → 約 2.6 ms
  (**換算,非實測**:把 §5.3 的 1,941 µs 那段換掉),與 R4 的純 Python 版差不多。
- **代價**:新增 numpy 相依 + **把 `market.py` 的規則抄第三份**。
- **阻擋風險**:**這是本報告唯一一條我判定「不要在即時路徑做」的**。
  `snap_down_milli` 已經有跨語言 parity 契約(後端 `market.py` ↔ 前端 `stock-tick.ts`,
  `tests/fixtures/vp_parity.json` 鎖住);再加一份 numpy 版就是三份規則、三個漂移面。
  而且**任務明定 `market.py` 是禁區** —— 雖然向量版全程 int64 沒違反「不可換浮點」,
  但精神上它就是在複製那段規則。
- **判定**:**即時路徑不建議。** 只有在離線回測(`backtest/`)要對百萬列做停板判定時才值得,
  而且必須配一條「0 ~ 2,000,000 毫元逐值等值」的 parity 測試(本報告已示範,**實測 0 不符**)。

### R6 —— 個股狀態機:**不動**

- 現況 1.6 µs/tick 已經是增量式,是全 codebase 最好的那段。
- numpy 版逐 tick 慢 1.7x(vs 純 Python 延後)、全日慢 52x、並且把均勻成本換成每 60 s 一記 9 ms 硬停。
- **`stock_state.py:60-64` 的註解不要改,它是對的。**

### R7 —— K 線 / 疊圖:**不動**

- `compute_cdp` 平手、`compute_ma` 慢 2.3–80x、`build_overlay` 慢 1.96x、`aggregate_period` 慢 1.12x。
- 這四支全部正確性驗過(numpy 版逐欄全等),**不是做不出來,是做出來比較慢。**
- 真要動 `aggregate_period`,槓桿在 `_period_key` 的 `fromisoformat` + `isocalendar()`(可 memo,
  同一根 bar 的日期一整天不變),不在數值那段 —— **但那不是 numpy 的事,也不在本區塊範圍(未量)**。

---

## 9. 意外(違反直覺的量測結果)

### 意外 1 —— 「增量會浮點漂移」這個設計理由,實測不成立;真正會咬人的是窗邊界

`corr_state.py:5-7` 寫著:

> 增量滑動窗的浮點誤差會隨執行時間累積,整批重算讓「增量 vs 整批一致」這件事恆真,
> 不必寫測試去追誤差上界。

我第一次量增量版時**正好量到了印證這段話的數字**:跑 32,400 次 push,`max|Δr|` 在
2.2e-4 ~ 2.8e-3 之間震盪,而且不隨時間單調 —— 看起來就是典型的累積誤差。

追下去發現**完全不是浮點**:

- 把「增量加減」與「閉式公式」分開量:同一份窗內資料,一次性閉式公式 vs `statistics.correlation`
  的差是 **2.8e-17**;增量加減後的閉式公式差是 **3.7e-16**。**兩者同量級 → 加減本身幾乎不貢獻誤差。**
- 真因是**窗邊界 off-by-one**:`CorrState` 對**中價序列**逐出(`_evict`:`ts < now - 1800`),
  而配對報酬的 ts 取較晚那一筆 → 最長窗實際涵蓋 **1800** 筆,不是 1801 筆。
  我的增量版直接用 `ts >= now - w` 逐出,最長窗多留一筆。
- 證明(`bench_t2_c1d_boundary.py`,同一組資料兩個版本):

  | 逐出條件 | n 不符格數 | max\|Δr\| @ 32,000 push |
  |---|---|---|
  | 原(`< now-w`) | **8 格**(10 腿的 w1800 各差 1,扣掉樣本不足的兩條稀疏腿) | 8.266e-04 |
  | 修正(最長窗改 `<= now-w`) | **0 格** | **3.858e-15** |

**為什麼這條重要**:檔頭那句話會讓下一個人**用錯誤的理由拒絕正確的優化**。
增量版的真實風險不是「誤差隨時間累積」(實測 9 小時後 3.9e-15,比顯示解析度小 12 個數量級),
而是「窗語意要對得剛剛好,差一筆就是 1e-3 的錯,而 1e-3 會翻動 `toFixed(2)` 的第二位」。
**守門測試因此要斷言 `n`,不是斷言 `r` 在容差內** —— 斷言 r 用 `isclose(rel_tol=1e-6)` 會讓 8.3e-4 的錯**靜默通過**。

### 意外 2 —— 對決 2 的「numpy 快 3x」是假的,3x 來自延後聚合

單看「numpy 版 ingest 0.52 µs vs 現況 1.6 µs」會得出「numpy 快 3x」的結論並寫進報告。
加一組**純 Python 延後(append 到 list)**的對照組後:**0.30 µs,比 numpy 還快 1.69x**。
所以 3x 完全來自「不在 tick 時聚合」,而 numpy 的逐元素 scalar 賦值其實**比 `list.append` 貴**。
**沒有這組對照,整個對決 2 的結論會是錯的。**

### 意外 3 —— numpy 在 10×3 的小陣列上輸給純 Python

對決 1 的 E 版(numpy 增量,每 push 對 10 腿 × 3 窗一次向量更新)理論上該贏 D 版(純 Python 雙層迴圈),
實測 **E 0.050 ms/s vs D 0.044 ms/s,numpy 慢 14%**。
在 10 個元素的陣列上,`np.ndarray` 的 `__iadd__` dispatch 開銷已經超過 30 次 Python float 加法。

### 意外 4 —— 檔頭那個 0.15 ms 沒說謊,錯的是「外推」

`corr_state.py` 寫「`statistics.correlation` 對 1800 樣本實測 0.15 ms」——
我實測 **0.160 ms**,完全吻合。錯的是下一句「整輪 tick 外推不到 1 ms」:
外推時只乘了腿數,漏掉 `_paired_returns`(5.594 ms,佔 61%)與 60 次 list comp(1.770 ms,佔 19%)。
**單點量測正確 + 外推方式錯誤 = 一個 13 倍的錯誤結論,而且看起來有實測支撐。**

### 意外 5 —— 全市場廣度的 n = 1,800 不是「numpy 不夠大」,是「根本沒有向量化空間」

原本預期 n = 1,800 會是 numpy 的甜蜜點。實測平手,而且 n 掃到 20,000 還是平手。
cProfile 顯示成本結構是 **252,000 次 `_to_number` + 504,000 次 `isinstance` + 144,000 次 `_tick_milli`**
—— 全部是 Python 函式呼叫,不是算術。numpy 對函式呼叫次數無能為力。
**「n 夠不夠大」問錯了問題;該問的是「這個 n 裡面有多少比例是可向量化的算術」**,
這裡的答案是 10%(dict 建構)+ 44%(分段函式,可向量化但有 parity 代價)。

---

## 10. 未量到的東西 / 結論會在什麼情況下反轉

1. **價格序列是合成的,不是 prod tick。**
   形狀(腿數 / 窗長 / 取樣率 / sparse 標記 / 筆數)全部取自 repo 真實設定檔與任務給定的
   `logs/` 實測值,但**價格本身是隨機漫步**。
   - 影響:對決 1 的 `n{w}` 分布會隨真實的缺值樣態變。若真實 SXF / VX 的缺值比 25% 更嚴重,
     A 的成本會比 9.15 ms 更低(配對報酬更少),各版本倍數會縮小。
     **dense 上界 12.24 ms 已經量了,實況一定落在 9.15–12.24 之間。**
   - 影響:對決 4 的漲跌停比例(2% / 1.5%)影響走 `limit_judged` 分支的比例。
     真實鎖板日會更多 → 現況更慢 → R4 的 1.71x 會更高。
2. **對決 3 的窗長是換算,不是實測。**
   我拿「日筆數 ÷ 16,200 秒 × 300 秒」算出 42 / 567,但成交叢聚
   (開盤 5 分鐘與攻板時段佔一天大部分筆數)→ **真實尖峰窗長可能遠大於 567**。
   我量到 10,000 筆為止;**沒有從 prod log 直接量過任何一檔的實際 300 秒窗筆數分布**。
   這只會讓 R3 的收益被低估,不會反轉。
3. **沒有跑 prod 的 event loop 量測。**
   所有數字都是**單執行緒 CPU 時間**。實際 event loop 上的停頓可能更長(GC、其他 task 競爭、
   Windows 排程)。系統級換算(270 輪/日、每秒 3.6 ms 等)是**換算不是實測**。
4. **`tests/live/test_corr_state.py` 已看過,但只掃了斷言形狀,沒逐條跑。**
   確認結果:**沒有任何寫死的 r 字面值**,全部是「與獨立 Pearson 參考實作比,`abs(got-expected) < 1e-9`」
   或 `is None` / `is not None`。所以 R1 / R2 的 3.9e-15 誤差**不會打紅任何一條**。
   **但有一個已經存在的部分守門**:`test_window_evicts_samples_older_than_window_length`
   (`:120-132`)明確斷言 60 秒窗 = 「最後 61 個價格點 → 60 筆報酬」,容差 1e-9 ——
   **這條會抓到 60 窗的 off-by-one**(off-by-one 的誤差量級是 1e-3 ≫ 1e-9)。
   **問題是 §9 意外 1 的 off-by-one 只發生在最長窗(1800)**,因為只有它會撞到中價序列的 `_evict`;
   而**現有測試沒有任何一條對最長窗做同樣的邊界斷言**。
   → R1 / R2 動手時必須**照 `:120-132` 的樣子補一條 1800 窗的版本**,否則那個 1e-3 的錯會靜默通過。
5. **`aggregate_period` 的 `_period_key` memo 化沒量。**
   §8 R7 提到它可能是真槓桿,但那是純 Python 的事,不在本區塊(numpy 擂台)範圍,**未量**。
6. **free-threaded / 多核沒碰。**
   本區塊全部是單執行緒。`.venv` 的 Python 3.13.13 不是 free-threaded build。
   把這些搬到 thread / process 的可行性不在本區塊範圍。
7. **結論會反轉的情況**:
   - 如果腿數從 11 長到 50+、或窗長從 1800 長到 10,000+,對決 1 的 numpy ring(C)與純 Python
     增量(D)的差距會縮小(D 的 push 成本是 O(腿×窗),C 的 push 是 O(腿))。
     **現況 11 腿 × 3 窗下 D 大勝;腿數 ×5 之後要重量。**
   - 如果 `rows_out` 的 wire 形狀改成「只送家數,明細另一支 endpoint」,對決 4 的 numpy
     理論上界 2.72x 就吃得到了 —— 但那是改契約,不是改實作。
