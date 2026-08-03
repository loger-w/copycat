# Round 4 現況盤點(Phase 1;2026-07-16)

Baseline:branch `mod/fade-round-4`(自 master dbc8548)、pytest **356 passed**(6.11s)。

## 現有引擎形狀(round 3 收工狀態)

### 模擬器 `copycat/backtest/fade_simulate.py`

- `_simulate_core`:零 IO、悲觀成交、空方當沖先賣。出場優先序 = 停損 > 停利/TP > 13:00 > 收盤(同 bar 衝突取最差 = 最高回補價)。
- 進場:`trig.close − slippage`(或 `entry_price_override`,cells 用)。
- 強制風控(config 欄位,None = 停用):
  - `guard_limit_dist`(硬線;round 3 = 0.01,即漲 9% 出場;進場已在區內 → `excluded_guard_at_entry`)
  - `disaster_x`(舊固定式)/ `disaster_arm_x` + `disaster_retrace_r`(round 3 回落式,互斥,`validate_disaster_fields` 擋)
  - `fixed_stop_level` / `ratchet_stop_b`(round 3 結構前高 + b;cells 層傳入)
  - `lock_penalty`(全日鎖死回補 = 漲停 ×(1+p))
- `exit_reason` 歸因(hardline / struct_fixed / struct_ratchet / disaster_x / disaster_retrace)→ 精算表。
- `TRADEABLE_STATUSES` 單一定義(§8 教訓:新增出場 status 只改這裡)。
- **TP 掛勾已存在**:`simulate_fade_with_tp(bars, trig_idx, sample, combo, tp, cfg, slippage)`;`tp=None` 與 `simulate_fade_sample` 等價(有測試鎖)。

### 停利機制 `copycat/backtest/fade_tp.py`(Phase B 遺產,11 種)

round 2/3 cells **全部沒用 TP**(抱到收盤)。與 round 4 直接相關:

| 既有 | 語意 | 對應 user 需求 |
|---|---|---|
| tp1 | 創新低 + 量爆(z× 前 N 均量)+ 長下影收回(recovery)→ 收 | **出量殺**(高潮收工)幾乎現成 |
| tp2 | 連續創低後、量增 + 收紅 + 外盤翻轉 → 收 | 反轉確認(部分重疊) |
| tp8 | 近 N bar 外盤比 ≥ 閾值 → 收 | 內外盤失衡反轉 |
| tp9 | 累計 delta 由負轉正 → 收 | 買賣壓翻轉 |
| (無) | 殺不破前低 + 拉回低點/高點遞增(墊高結構) | **竭盡收工 = 新機制** |

TP 網格參數已在 `FadeBacktestConfig`(tp1_*~tp11_*),`enumerate_tp_combos` 只被 `fade_pipeline`(Phase B GA 路徑)/`fade_optimize` 消費。

### 進場 `copycat/backtest/fade_cells.py`

- `find_cell_a_entry`(先拉再出:拉高 ≥1% → 回落 0.8% + headroom ≥4% + **累計內盤比 ≥0.45**)、`find_cell_b_entry`(衝停失敗)、`find_cell_c_entry`(低開反拉)、`_BASELINE_M = 6`(第 7 分鐘基準線)。
- 「造山完成確認」進場 = 新 entry finder(cell_a 已是雛形:它就是「拉高回落確認」,round 4 是重定義/加強確認條件,不是從零)。
- `_evaluate_round3` / `_actuarial_block`(精算表)/ `_cluster_z_block`(日聚類 z)/ forward 切分(`forward_start=2026-07-11`)/ `_write_round3_report` 全在此檔。

### 統計/判定

- `fade_diagnose.run_pool_diagnose`:三池無條件對照(Q1)、洗牌檢定、lock_penalty grid。內盤比 UC 分層重驗 = 此處延伸(新分析)。
- **MFE(最大有利波動)統計:全 codebase 不存在**,新功能。
- D5 門檻:`d5_min_ev=0.01 / d5_min_n=80 / d5_min_positive_segments=3`(config 化)。

### Config / cache 紀律

- `load_fade_config` 嚴格拒未知 key;新欄位要同步 `_TUPLE_KEYS`(tuple 型)與 **`_SIM_FIELDS`**(影響模擬結果的欄位必須入 hash,否則 outcome cache 不失效 → 沿用髒資料)。
- round 3 凍結值(`configs/fade_uc_round3.json`):guard 0.01、D=0.06、r=0.02、b=[0.025,0.0375]、lock_penalty 0.03、貼板線 fade_gap_max 0.075、fee_discount 0.84。

### CLI(`copycat/cli.py`)

`fade-diagnose` / `fade-cells` / `fade-search` 三個子命令,均 `--config` 載 JSON 覆寫。

### 資料現況

- events.csv 至 **2026-07-09**;forward 樣本 0(回補鏈 scan-events → TC4 → daytrade → brokers → label 未跑,TC4 需達錢 4 常駐)。
- Q2 forward 複核機制已凍結(≥20 交易日門檻)。

## Caller map(改動面)

| 目標函式/模組 | Caller |
|---|---|
| `simulate_fade_sample` / `simulate_fade_with_tp` | fade_cells(183/379)、fade_diagnose(205)、fade_optimize(58/60)、fade_pipeline(169/374/511/547)、tests ×5 檔 |
| `check_tp_exit` | 僅 `_simulate_core`(fade_simulate 225) |
| `enumerate_tp_combos` | fade_pipeline(192/627)、tests |
| `NO_STOP_HOLD_COMBO` | fade_cells、fade_diagnose |
| 動態用法 | 無(grep 無 template string / reflection 消費) |

## 現況 vs 目標

| 面向 | 現況 | round 4 目標 | Backward compat |
|---|---|---|---|
| 進場 | cell_a/b/c + 底倉 + 第 7 分鐘基準線 | 「造山完成確認」進場(cell_a 語意重定 or 新 finder) | 新 finder 走新 config 欄位;舊 cells 路徑不動 |
| 停損 | 價格距離(結構高+b ∧ 硬線;災難回落式) | 劇本走樣訊號(內盤比反轉 / 假突破過身高 / 緩漲結束反轉) | 新機制 config-gated(預設 off = round 3 行為) |
| 停利 | 無(抱到收盤);TP 掛勾閒置 | 決策樹:出量殺(tp1 近似)+ 墊高竭盡(新)+ 預設收盤 | cells 路徑首次接 tp 參數;tp=None 不變式已有測試 |
| 統計 | 精算表 / 日聚類 z / D5 | + MFE 統計(讓出多少肉)、內盤比 UC 分層重驗 | 純新增報告區塊 |
| 判定 | Q1/Q2 拆題、forward 唯一考場 | 沿用;新 exit 機制入精算表歸因 | `exit_reason` 詞彙擴充;`TRADEABLE_STATUSES` 單點修改 |

## 風險註記

1. 新 TP/停損若影響模擬 → 對應 config 欄位**必入 `_SIM_FIELDS`**(cache 失效三重機制)。
2. 白名單:round 2/3 config 重跑輸出必須 bit-for-bit 一致(round 3 已建立此迴歸慣例);`copycat validate` 42/42;`tp=None` 等價不變式。
3. 墊高結構確認有「讓肉」代價:訊號確認點 vs 當日最低點差距要入 MFE 報告(否則無法誠實評估)。
4. 自由度預算:round 3 紀律 = 搜索型變體 ≤ 個位數;TP 若走 enumerate 全網格(數千組)= 回到 round 1 過擬合老路,round 4 必須用**凍結參數的少數變體**,不是 GA 搜索。
