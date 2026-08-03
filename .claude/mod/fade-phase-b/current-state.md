# 現況表:fade-search Phase B

## Baseline
- 186 tests / ruff / pyright 全綠
- Phase A 產物:202 條規則通過三道驗證(17/17 臂有存活規則)
- 報告:`docs/evidence/tday_fade_backtest_2026-07-08.md`
- 規則:`out/fade_ga/rules_final.json`

## 核心模組 & caller map

### `fade_pipeline.py` → `run_fade_arm()`
- **唯一 caller**:`run_fade_pipeline()` (同檔 :359)
- 現行行為:
  - `is_anchor=True` 時走 `enumerate_fade_stop_combos(cfg, top3_s1)` 展開全 4640 停損組合
  - `is_anchor=False` 時只跑 baseline combos
  - `slippage_ticks` 固定用 `cfg.slippage_ticks`(預設 1)
  - `mkt_daily_rows` 和 `mkt_intraday` 目前 pipeline 端傳 `None`
  - GA 搜索 + 三道驗證(train/test split + monthly + plateau)在此函式內完成
  - 回傳 dict 含 `rules`, `n_triggered`, `lock_events`, `top3_s1` 等
  
### `fade_pipeline.py` → `run_fade_pipeline()`
- **callers**:
  - `cli.py` :137 (`fade-search` 子命令)
  - `test_cli_fade.py` :32, :66(monkeypatch 測試)
- 現行行為:
  - `mkt_daily_rows = None`(未接 MTX 資料)
  - 只跑 anchor params,不跑 full param grid
  - 報告用 `write_fade_report()`

### `fade_config.py` → `enumerate_fade_stop_combos()`
- **唯一 caller**:`run_fade_arm()` :217
- 現行行為:產生 S1-S5 × t1300 全組合,含 top3 S1×S2 交叉

### `fade_config.py` → `FadeBacktestConfig`
- `stress_slippage_ticks: int = 2` — 已定義但 **未被使用**(Phase A 移除了 dead stress_pnl)
- `slippage_ticks: int = 1` — 所有模擬固定用此值

### `fade_simulate.py` → `simulate_fade_sample()`
- **callers**:
  - `run_fade_arm()` :194, :230(pipeline)
  - `test_fade_simulate.py`(10 處測試)
- 第 6 參數 `slippage_ticks` 是 int,外部傳入

### `market_features.py`
- `compute_mkt_daily_features_full()` — pipeline :152 有呼叫但 `mkt_daily_rows=None` 短路
- `compute_mkt_intraday_features()` — pipeline 完全未呼叫(fade_trigger_features 接 `mkt_intraday=None`)
- 兩者 test 已有(`test_market_features.py`)

### `fade_report.py` → `write_fade_report()`
- **唯一 caller**:`run_fade_pipeline()` :375
- 現行欄位:arm / param / triggered / rules / lock_events

## Phase B 要改什麼

### 1. 停損族對決
- **現況**:Phase A 每臂只在 anchor params 跑一次 GA,停損組合展開(4640)但只用來模擬 default combo 上的 GA
- **目標**:Phase A 存活規則 × 全停損組合,找每條規則的最佳停損配置
- **改動**:`run_fade_arm()` 回傳增加每條規則的 per-combo 最佳化結果

### 2. 滑價壓測
- **現況**:`cfg.stress_slippage_ticks=2` 已定義但沒用
- **目標**:−1 tick vs −2 tick 重跑存活規則,確認不因 1 tick 滑價翻號
- **改動**:新函式或 pipeline 層級

### 3. MTX 1K 大盤特徵
- **現況**:`mkt_daily_rows=None`, `mkt_intraday=None` — 計算函式已寫好但沒接資料
- **目標**:讀 MTX 日 K / 1K → 接入 pipeline
- **改動**:`run_fade_pipeline()` 載入 MTX 資料;data store 需要 MTX 讀取能力

### 4. 臂間對決
- **現況**:報告只有 arm × param 表 + 規則清單,無橫向比較
- **目標**:7 臂 top rule 橫向比較(期望值/勝率/賺賠比/鎖死比例/MDD)
- **改動**:`write_fade_report()` 擴充

## 行為白名單(不能破壞)
1. Phase A 基線結果不變:同 config + 同資料 → 同規則產出
2. `simulate_fade_sample()` 現有 10 個 test 全綠不動
3. `run_fade_arm()` 回傳結構的既有欄位不刪(可加新的)
4. `run_fade_pipeline()` 現有 CLI 介面不變(新功能用新 flag)
5. `write_fade_report()` 現有章節不刪(可加新章節)
6. `FadeBacktestConfig` 現有欄位語意不變(可加新欄)
7. `enumerate_fade_stop_combos()` 回傳數量不變(同 top3_s1)
