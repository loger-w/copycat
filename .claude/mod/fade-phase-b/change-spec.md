# Change Spec: fade-search Phase B

## 成功條件

- SC-1: 每條 Phase A 存活規則都有 best_stop(最佳停損) + best_tp(最佳停利) + test 期望值/勝率/賺賠比/MDD
- SC-2: 每條規則有 stress_passed 布林值(best_stop + best_tp + −2 tick 壓測後期望值是否 > 0)
- SC-3: 報告新增「臂間對決」表:7 臂 top-1 rule 橫向比較(test_exp DESC 排序)
- SC-4: Phase A 既有行為不變(同 config + 同資料 → 同規則產出;186 tests 全綠)
- SC-5: CLI `fade-search` 介面不變(新功能自動啟用,不需新 flag)
- SC-6: 11 種新 TP 機制全部實作在模擬器中,各自有獨立單元測試

量化驗收:
- SC-1: `rules_final.json` 每條 rule 含 `best_stop`, `best_tp`, `best_test_expectancy` 欄位(非 null)
- SC-2: `rules_final.json` 每條 rule 含 `stress_passed`, `stress_expectancy` 欄位
- SC-3: 報告 md 含 `## 臂間對決` 章節
- SC-4: `pytest -q` 全綠;`ruff check` + `pyright` 零錯誤
- SC-6: `test_fade_tp.py` 含 >= 22 個測試(每 TP 至少 2:觸發 + 未觸發)

## 不能破壞的既有行為白名單

1. `simulate_fade_sample()` — 既有 10 個 test 全不動;signature 不變;`tp=None` 時行為與現在完全一致
2. `run_fade_arm()` — 回傳 dict 既有 key 全保留
3. `run_fade_pipeline()` — CLI 介面(args)不變
4. `enumerate_fade_stop_combos()` — signature / 回傳數量不變
5. `FadeBacktestConfig` — 既有欄位語意不變
6. `write_fade_report()` — 現有章節不刪
7. GA 搜索 + 三道驗證邏輯零改動(在 default combo + 無 TP 上搜索)

## Out of scope

- MTX 大盤特徵接入(留 Phase C)
- GA 重搜(規則凍結,只重模擬)
- 並行化 / 效能最佳化
- 新 CLI flag
- TP 之間的疊加(同一時間只有一種 TP 生效)

---

## 架構:兩階段搜索

```
Phase A 存活規則(202 條)
    │
    ▼ Stage 1: 停損對決(train set 最佳化)
    每條規則 × 4640 停損組合(S1-S4 × t1300) → best_stop
    │
    ▼ Stage 2: 停利對決(train set 最佳化)
    每條規則 × best_stop(s5_x 強制 None) × ~1928 TP 配置 → best_tp
    │
    ▼ Stage 3: 驗證 + 滑價壓測(test set)
    best_stop + best_tp → test 期望值 + −2 tick 重跑 → stress_passed
    │
    ▼ 臂間對決
    每臂 top-1 → 橫向排名表
```

### 關鍵設計決策(reviewer R1-R8 修正)

**R1 index 對齊**:`tradeable_samples` 在 `run_fade_arm()` 裡與 `all_feat`/`all_dates`/`all_sids` 同步建構 — 只含 tradeable + non-null pnl 的 subset,index 一對一。`triggered`(未過濾)不傳入 optimize 函式。

**R2 S5 去重**:Stage 1 的 best_stop 可能含 `s5_x`。進入 Stage 2 時,將 best_stop 的 `s5_x` 強制設 `None` — TP 層全權控制停利,避免 S5 雙重生效。

**R5 TP 優先級**:`_simulate_core` 衝突規則:
1. 停損(S1-S4 的 stop_fills list) → 取最差(最高回補價)
2. TP 出場(check_tp_exit 回傳值)
3. 同 bar 停損 + TP 同時觸發 → worst = max(stop_worst, tp_exit)
4. 13:00 出場 / 收盤出場

TP5(缺口回填)為限價單(exit = fill_level);其餘 TP 為 bar close。

**R6 train/test 分離**:Stage 1 + Stage 2 最佳化在 **train set** 上進行。Stage 3 在 **test set** 上驗證 + 壓測。報告欄位 `best_test_expectancy` 是 test set 的 out-of-sample 期望值。

**R7 cache hash**:新 TP 參數欄位全部加入 `_SIM_FIELDS`,確保 config 變動時 cache 失效。

---

## 11 種 TP 機制定義

### 現有 S5(保留)
固定百分比停利:entry × (1 − x) → 限價出場。
參數:`s5_x`: 0.005, 0.008, 0.010, 0.015, 0.020, 0.025, 0.030, 0.040, 0.050
組合數:9

### TP1: 量能高潮(插針爆量 + 收回)
已獲利 + bar 爆量創新低但收回 = 恐慌賣壓出盡。
觸發:profit >= min_profit AND bar_vol > avg_vol(n) × z AND bar 創 session 新低 AND (close−low)/(high−low) >= recovery_pct。
出場:bar close。
參數:
- `tp1_min_profit`: 0.003, 0.005, 0.008, 0.01, 0.015, 0.02
- `tp1_z`: 1.5, 2.0, 2.5, 3.0, 4.0, 5.0
- `tp1_lookback`: 3, 5, 8, 10, 15
- `tp1_recovery`: 0.3, 0.4, 0.5, 0.6, 0.7
組合數:6 × 6 × 5 × 5 = 900

### TP2: 量能反轉(新低中爆量拉回)
持續下跌中,突然爆量 + 收紅 + 買盤佔比翻轉 = 有人大量接貨。
觸發:近 trend_n 根有 >= new_low_count 根創新低 AND bar_vol > avg_vol(trend_n) × z AND close > open AND up_vol/total > inner_flip_pct。
出場:bar close。
參數:
- `tp2_trend_n`: 3, 5, 8, 10
- `tp2_new_low_count`: 2, 3, 4
- `tp2_z`: 1.5, 2.0, 2.5, 3.0
- `tp2_inner_flip`: 0.50, 0.55, 0.60, 0.65, 0.70
- `tp2_min_profit`: 0.003, 0.005, 0.008
組合數:4 × 3 × 4 × 5 × 3 = 720

### TP3: 下跌減速
還在跌但速度變慢 = 動能衰竭。
觸發:profit >= min_profit AND 近 n 根平均跌幅(各 bar 的 close-to-close %) < 前 n 根平均跌幅 × decel_ratio AND running_low 仍在更新中。
出場:bar close。
參數:
- `tp3_n`: 3, 4, 5, 6, 8
- `tp3_decel`: 0.3, 0.4, 0.5, 0.6, 0.7
- `tp3_min_profit`: 0.003, 0.005, 0.008, 0.01
組合數:5 × 5 × 4 = 100

### TP4: 連續新低計數
連續 N 根創新低 → 過度延伸,反彈在即。
觸發:連續 n 根 bar.low < prev bar.low AND profit >= min_profit。
出場:bar close。
參數:
- `tp4_n`: 3, 4, 5, 6, 7, 8, 10, 12, 15
- `tp4_min_profit`: 0.003, 0.005, 0.008, 0.01, 0.015
組合數:9 × 5 = 45

### TP5: 缺口回填
T+1 跳空高開的缺口被填到一定比例 = 自然支撐。
觸發:bar.low <= fill_level,其中 fill_level = t1_open − fill_pct × (t1_open − limit)。
出場:fill_level(限價單)。分母 guard:t1_open <= limit 時此 TP 不生效。
參數:
- `tp5_fill`: 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0
組合數:8

### TP6: VWAP 偏離
價格跌到 VWAP 以下太遠 → 均值回歸壓力。
VWAP = 累計(bar.close × bar.volume) / 累計(bar.volume),從盤中第一根 bar 持續計算。
觸發:(VWAP − bar.close) / VWAP >= distance_pct。
出場:bar close。
參數:
- `tp6_dist`: 0.005, 0.008, 0.01, 0.012, 0.015, 0.02, 0.025, 0.03
組合數:8

### TP7: 日內區間比例
已吃到當日振幅的夠大比例。
觸發:(entry − bar.close) / (rolling_high − rolling_low) >= capture_pct,且 rolling_high > rolling_low。
出場:bar close。
參數:
- `tp7_capture`: 0.3, 0.4, 0.5, 0.6, 0.7, 0.8
組合數:6

### TP8: 買盤比翻轉
持倉期間買盤佔比突然回升。
觸發:profit >= min_profit AND 近 n 根 up_vol/(up+dn) >= threshold。
出場:bar close。
參數:
- `tp8_n`: 1, 2, 3, 4, 5
- `tp8_threshold`: 0.50, 0.55, 0.60, 0.65, 0.70, 0.75
- `tp8_min_profit`: 0.003, 0.005, 0.008
組合數:5 × 6 × 3 = 90

### TP9: 累計 delta 翻正
從進場起算的累計 delta(up−dn)從負翻正 = 買盤總量反超。
觸發:prev_cum_delta < 0 AND cur_cum_delta >= 0 AND profit >= min_profit。
出場:bar close。
參數:
- `tp9_min_profit`: 0.003, 0.005, 0.008, 0.01
組合數:4

### TP10: 長下影線(反轉 K 線)
bar 往下插深但收回 = 有人大力接。
觸發:profit >= min_profit AND bar.low <= running_low AND (bar.close − bar.low) / (bar.high − bar.low) >= wick_pct(bar.high > bar.low guard)。
出場:bar close。
參數:
- `tp10_wick`: 0.5, 0.6, 0.7, 0.8
- `tp10_min_profit`: 0.003, 0.005, 0.008, 0.01
組合數:4 × 4 = 16

### TP11: 時間遞減目標
越晚目標越低(hold for bigger move early,take what you can late)。
觸發:profit >= initial_target × decay^elapsed_bars。
出場:bar close。
參數:
- `tp11_initial`: 0.01, 0.015, 0.02, 0.025, 0.03
- `tp11_decay`: 0.95, 0.97, 0.98, 0.99
組合數:5 × 4 = 20

### TP 總計:None(1) + S5(9) + TP1-TP11(900+720+100+45+8+8+6+90+4+16+20) = 1928 組

---

## Diff 級 spec

### 🟢 新功能:`copycat/backtest/fade_config.py` — `FadeTakeProfitCombo` + 枚舉

```python
@dataclass(frozen=True, slots=True)
class FadeTakeProfitCombo:
    tp_type: str | None       # None = 無停利, "s5", "tp1"..."tp11"
    params: tuple[tuple[str, float], ...]  # frozen (sorted key-value pairs)

    @property
    def tp_id(self) -> str: ...
```

注意:`params` 用 `tuple[tuple[str, float], ...]` 而非 `dict` — `frozen=True` 需要 hashable 欄位。

新函式:
```python
def enumerate_tp_combos(cfg: FadeBacktestConfig) -> list[FadeTakeProfitCombo]:
    """全 TP 網格(None + S5 + TP1-TP11),共 1928 組。"""
```

`FadeBacktestConfig` 新增 TP 參數 tuple 欄位(每 TP 的各參數維度)。
既有欄位不動。新 TP 欄位全部加入 `_SIM_FIELDS` 與 `_TUPLE_KEYS`。

新測試:
- `test_enumerate_tp_combos_count`: 驗總數 1928
- `test_tp_combo_id_unique`: 所有 tp_id 唯一

### 🟢 新功能:`copycat/backtest/fade_simulate.py` — TP 出場判定

新函式(模擬器內部呼叫):
```python
def check_tp_exit(
    tp: FadeTakeProfitCombo,
    bar: Bar1K,
    entry: float,
    running_low: float,
    running_high: float,
    post_bars_so_far: list[Bar1K],
    cum_delta: float,
    prev_cum_delta: float,
    sample: FadeSample,
    elapsed_bars: int,
    cum_pv: float,
    cum_vol: float,
) -> float | None:
    """回傳 TP 出場價(bar close 或 limit price);None = 未觸發。"""
```

`_simulate_core` 在模擬迴圈中維護的新 running state:
- `cum_pv: float` — 累計 price × volume(VWAP 計算用)
- `cum_vol: float` — 累計 volume
- `cum_delta: float` — 累計 (up_volume − down_volume)
- `prev_cum_delta: float` — 上一根 bar 結束時的 cum_delta
- `post_bars_so_far: list[Bar1K]` — 進場後所有 bar(TP1/TP2/TP3 lookback 用)
- `elapsed_bars: int` — 進場後經過的 bar 數

`tp=None` 時不呼叫 `check_tp_exit`(跳過,Phase A 行為)。

**不改** `simulate_fade_sample()` 的 signature。

```python
def simulate_fade_with_tp(
    bars: list[Bar1K],
    trig_idx: int,
    sample: FadeSample,
    combo: FadeStopCombo,
    tp: FadeTakeProfitCombo | None,
    cfg: FadeBacktestConfig,
    slippage_ticks: int,
) -> FadeTradeOutcome:
    """simulate_fade_sample 的 TP 擴充版;tp=None 時行為與原函式一致。"""
```

核心模擬迴圈提取為 `_simulate_core()`。
`simulate_fade_sample()` → `_simulate_core(tp=None)`,行為不變。
`simulate_fade_with_tp()` → `_simulate_core(tp=tp)`。

新測試(放 `tests/test_fade_tp.py`,每 TP 至少 2 個):
- `test_tp1_triggers_on_volume_spike` / `test_tp1_no_trigger_low_volume`
- `test_tp2_triggers_on_reversal` / `test_tp2_no_trigger_no_trend`
- `test_tp3_triggers_on_deceleration` / `test_tp3_no_trigger_still_fast`
- `test_tp4_triggers_on_consecutive_lows` / `test_tp4_no_trigger_not_enough`
- `test_tp5_triggers_on_gap_fill` / `test_tp5_no_trigger_gap_unfilled`
- `test_tp6_triggers_on_vwap_distance` / `test_tp6_no_trigger_near_vwap`
- `test_tp7_triggers_on_range_capture` / `test_tp7_no_trigger_small_capture`
- `test_tp8_triggers_on_inner_flip` / `test_tp8_no_trigger_still_selling`
- `test_tp9_triggers_on_delta_flip` / `test_tp9_no_trigger_delta_negative`
- `test_tp10_triggers_on_long_wick` / `test_tp10_no_trigger_short_wick`
- `test_tp11_triggers_on_decayed_target` / `test_tp11_no_trigger_early`
- `test_simulate_fade_with_tp_none_equals_original` — tp=None 結果與 simulate_fade_sample 一致

### 🟢 新功能:`copycat/backtest/fade_pipeline.py` — `optimize_rule_stops()`

Stage 1 停損對決(**train set** 最佳化):

```python
def optimize_rule_stops(
    tradeable_samples: list[tuple[FadeSample, list[Bar1K], int]],
    rules: list[dict[str, object]],
    all_combos: list[FadeStopCombo],
    all_feat: list[dict[str, float | None]],
    all_dates: list[str],
    cfg: FadeBacktestConfig,
) -> None:
    """就地擴充每條 rule:best_stop(最佳停損)— train set 最佳化。"""
```

索引對應:**`tradeable_samples[i]`** 與 `all_feat[i]` / `all_dates[i]` 一一對應。
都是 tradeable + non-null pnl 的 subset。在 `run_fade_arm()` 裡同步建構。

邏輯:
1. 對每條 rule:
   - `mask = apply_rule(conditions, all_feat)` 篩出命中 sample bit indices
   - 取 **train** set indices:mask 內且 `all_dates[i] < cfg.split_date`
   - 對每個 combo in `all_combos`:
     - 對 train samples 跑 `simulate_fade_sample(bars, trig_idx, sample, combo, cfg, cfg.slippage_ticks)`
     - 算 `weighted_stats()` → train 期望值
   - 取 train 期望值最高的 combo → `best_stop`
2. 就地寫入 rule dict:
   - `best_stop`: combo_id str
   - `best_stop_params`: dict (FadeStopCombo 各欄位)

### 🟢 新功能:`copycat/backtest/fade_pipeline.py` — `optimize_rule_tp()`

Stage 2 停利對決(**train set** 最佳化) + Stage 3 驗證 + 壓測(**test set**):

```python
def optimize_rule_tp(
    tradeable_samples: list[tuple[FadeSample, list[Bar1K], int]],
    rules: list[dict[str, object]],
    tp_combos: list[FadeTakeProfitCombo],
    all_feat: list[dict[str, float | None]],
    all_dates: list[str],
    cfg: FadeBacktestConfig,
) -> None:
    """就地擴充每條 rule:best_tp + test 驗證 + stress test。"""
```

邏輯:
1. 對每條 rule(已有 best_stop):
   - 重建 best_stop combo,**強制 s5_x=None**(R2 修正:TP 層全權控制停利)
   - mask 內 **train** set samples
   - 對每個 tp in tp_combos:
     - `simulate_fade_with_tp(bars, trig_idx, sample, best_stop_no_s5, tp, cfg, cfg.slippage_ticks)`
     - 算 train 期望值
   - 取最高 → `best_tp`
2. **test set 驗證**:best_stop(s5_x=None) + best_tp,test samples 跑模擬 → test 期望值/勝率/MDD
3. **stress test**:同 test samples,slippage=`cfg.stress_slippage_ticks` → stress_expectancy
4. 就地寫入:
   - `best_tp`: tp_id str
   - `best_tp_params`: dict
   - `best_test_expectancy`: float (test set out-of-sample)
   - `best_test_p_win`, `best_test_payoff`, `best_test_mdd`, `best_test_n`
   - `best_lock_pct`: float
   - `stress_expectancy`: float
   - `stress_passed`: bool (stress_expectancy > 0)
   - `stop_only_expectancy`: float (best_stop 無 TP,test set 期望值,對照基線)

新測試:
- `test_optimize_rule_stops_basic` — best_stop 選正確(train)
- `test_optimize_rule_tp_basic` — best_tp 選正確(train)
- `test_optimize_rule_tp_test_validation` — test set 驗證與 train 分離
- `test_optimize_rule_tp_stress_flip` — 翻號
- `test_optimize_rule_tp_stress_pass` — 通過
- `test_optimize_rule_tp_s5_stripped` — best_stop 有 s5_x 時進 Stage 2 被 strip
- `test_optimize_rule_tp_empty` — 空規則不 crash

### 🟢 新功能:`copycat/backtest/fade_pipeline.py` — `build_cross_arm_table()`

```python
def build_cross_arm_table(
    all_results: list[dict[str, object]],
) -> list[dict[str, object]]:
    """7 臂 top-1 rule 橫向比較表(best_test_expectancy DESC)."""
```

每臂取 best_test_expectancy 最高的一條 rule。
回傳 list of dict:rank, arm, param, test_exp, stress_exp, p_win, payoff, mdd, lock_pct, stress_passed, best_stop, best_tp, n_test。
按 test_exp DESC, mdd ASC 排序。

新測試:
- `test_build_cross_arm_table_ranking` — 3 臂假資料 → 驗排序
- `test_build_cross_arm_table_empty_arm` — 某臂無規則不列入

### 🔴 行為改動:`copycat/backtest/fade_report.py` — 新增章節

signature 擴充(新增 optional 參數):
```python
def write_fade_report(
    results, cfg, report_date, out_dir, evidence_dir=None,
    cross_arm_table: list[dict[str, object]] | None = None,  # NEW
) -> Path:
```

在「存活規則」章節後新增:
```markdown
## 臂間對決(Phase B)

| rank | arm | param | test_exp | stress_exp | p_win | payoff | MDD | lock% | stress | best_stop | best_tp | n_test |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|---|---|---:|
```

既有章節不刪不改。`cross_arm_table=None` 時跳過(backward compat)。

新測試:`test_fade_report_cross_arm_section` — 傳 cross_arm_table → 驗報告含 `## 臂間對決`。

### 🔴 行為改動:`copycat/backtest/fade_pipeline.py` — `run_fade_arm()` 串接

在 return 前:
```python
if is_anchor and rules:
    optimize_rule_stops(tradeable_samples, rules, all_combos, all_feat, all_dates, cfg)
    tp_combos = enumerate_tp_combos(cfg)
    optimize_rule_tp(tradeable_samples, rules, tp_combos, all_feat, all_dates, cfg)
```

`tradeable_samples` 在建構 `all_feat`/`all_dates` 的同一迴圈中同步收集:
```python
tradeable_samples: list[tuple[FadeSample, list[Bar1K], int]] = []
# ... 在既有的 for i, (sample, bars, trig_idx) in enumerate(triggered): 迴圈內
# 與 all_feat.append / all_dates.append 同步:
tradeable_samples.append((sample, bars, trig_idx))
```

### 🔴 行為改動:`copycat/backtest/fade_pipeline.py` — `run_fade_pipeline()` 串接

```python
cross_arm = build_cross_arm_table(all_results)
report_path = write_fade_report(all_results, cfg, report_date, out_dir, evidence_dir,
                                cross_arm_table=cross_arm)
```

### 🔵 純重構:`copycat/backtest/fade_simulate.py` — 提取 `_simulate_core()`

將 `simulate_fade_sample()` 的模擬迴圈提取為:
```python
def _simulate_core(
    bars: list[Bar1K],
    trig_idx: int,
    sample: FadeSample,
    combo: FadeStopCombo,
    tp: FadeTakeProfitCombo | None,
    cfg: FadeBacktestConfig,
    slippage_ticks: int,
) -> FadeTradeOutcome:
```

`simulate_fade_sample()` 變成:
```python
def simulate_fade_sample(bars, trig_idx, sample, combo, cfg, slippage_ticks):
    return _simulate_core(bars, trig_idx, sample, combo, None, cfg, slippage_ticks)
```

`_simulate_core` 新增的 running state(僅 tp 非 None 時使用):
- `post_bars_so_far`, `cum_pv`, `cum_vol`, `cum_delta`, `prev_cum_delta`, `elapsed_bars`

既有 10 個 test 不該紅(wrapper 行為不變)。

---

## 測試清單

既有測試逐一標:
- `test_fade_simulate.py` (10 tests) — 不該紅(simulate_fade_sample wrapper 行為不變)
- `test_cli_fade.py` (2 tests) — 不該紅
- `test_fade_features.py` — 不該紅
- `test_fade_trigger.py` — 不該紅
- `test_market_features.py` — 不該紅
- 其他 186 tests — 全不該紅

新測試:
- `tests/test_fade_tp.py` — 11 TP × 2 + tp_none + config 2 = 26 tests
- `tests/backtest/test_fade_phase_b.py` — stops(1)/tp(5+s5_strip)/stress(2)/cross_arm(2)/report(1)/integration(1) = 12 tests

## Commit 計畫(🔵 → 🟢 → 🔴 順序)

1. 🔵 `fade_simulate.py` 提取 `_simulate_core()` + 既有 10 tests 全綠
2. 🟢 `FadeTakeProfitCombo` + `enumerate_tp_combos()` + config 新欄位 + 測試
3. 🟢 `check_tp_exit()` + `simulate_fade_with_tp()` + 26 個 TP 測試
4. 🟢 `optimize_rule_stops()` + `optimize_rule_tp()` + 測試
5. 🟢 `build_cross_arm_table()` + 測試
6. 🔴 `write_fade_report()` 新增章節 + 測試
7. 🔴 `run_fade_arm()` + `run_fade_pipeline()` 串接 + 整合測試

## Review 修正紀錄

- R1(P0): tradeable_samples 與 all_feat index 一對一 → 明確記錄同步建構方式
- R2(P0): S5 去重 → Stage 2 進入前 best_stop.s5_x 強制 None
- R3(P1): TP combo 數 → 修正為 1928(逐 TP 列出)
- R4(P1): CLI flag 矛盾 → 以 spec 為準(不需新 flag)
- R5(P1): TP 優先級 → worst = max(stop_worst, tp_exit)
- R6(P1): train/test 分離 → Stage 1+2 用 train,Stage 3 用 test
- R7(P1): cache hash → 新 TP 欄位加入 _SIM_FIELDS
- R8(P1): commit 順序 → 修正為 🔵→🟢→🔴
- R9(P2): TP5 公式 → 明確 fill_level 計算 + 分母 guard + 限價出場
- R10(P2): _simulate_core running state → 列出全部新 state 變數

self_review_head: 28ee16f
closeout_review_head: e0eb1b7  # 2026-07-10 收尾增量 review(medium):accepted 2(空 t1_date 過濾 P1 / 分頁停滯 guard P2),refuted:UTC 時窗、KeepAlive 洩漏(daemon=True 已保底)、SKEY secret(官方公開範例憑證)
