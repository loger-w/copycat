# Round 3 現況盤點(/mod Phase 1;2026-07-15)

Baseline:branch `mod/fade-round-3`(3 個開工 commit,status 乾淨),`pytest -q` 321 passed。
上游凍結文件:`docs/superpowers/specs/2026-07-15-fade-round3-prereg-draft.md`(已拍板凍結)、
`docs/strategy-decisions.md` §1「Round 2 複驗結果」+「2026-07-15 定案」。

## 1. 現況:停損/風控語意(round 2 遺留)

### fade_simulate.py(`_simulate_core`)

| 機制 | 現況語意 | 位置 |
|---|---|---|
| guard(防鎖保險) | `guard_level = t1_limit × (1 − cfg.guard_limit_dist)`;進場已在區內 → `excluded_guard_at_entry`(排除非虧損出場);盤中 `bar.high ≥ level` → `guard_exit` | fade_simulate.py:93-96, 157 |
| 災難停損 | `disaster_level = entry × (1 + cfg.disaster_x)`(進場價錨定,固定虧損式) | fade_simulate.py:97, 158-159 |
| fixed_stop_level | 呼叫端傳入的絕對價位強制停損(round 2 cell_b 專用:`approach_high × (1 + cell_b_stop_buffer)`) | fade_simulate.py:160-161 |
| lock_penalty | 全日鎖死回補價 = `t1_limit × (1 + p)`;`None` = 漲停價零懲罰(**noguard +0.85% 上界的根源**) | fade_simulate.py:237-242 |
| stress_guard_fill_high | 壓測:強制出場成交 = `max(level, bar.high)` | fade_simulate.py:154 |
| 鎖死凍結 | 鎖死 bar 內任何停損不觸發(R15) | fade_simulate.py:126-134 |
| 衝突取最差 | forced/stop/target/tp/time 同 bar → 取最高回補價 | fade_simulate.py:214-223 |

`TRADEABLE_STATUSES`(單一定義,fade_simulate.py:51):stopped / target_hit / time_1300 /
closeout / locked_at_limit / guard_exit;`excluded_*` 永不入統計。
**教訓(CLAUDE.md §8)**:新增出場 status 只改這一處。

### fade_config.py(FadeBacktestConfig)

- 風控欄位:`guard_limit_dist` / `disaster_x` / `lock_penalty`(皆 `None` = 停用)——
  三者皆在 `_SIM_FIELDS`(hash 失效鏈),新增模擬語意欄位必須同步加入 `_SIM_FIELDS`。
- round 2 cells 欄位:`cell_a_*`(pullback 0.008 / headroom_min 0.04 / inner 0.45,0.55 /
  window 60 / min_rally 0.01)、`cell_b_*`(approach 0.02,0.03 / fail_confirm 0.01 /
  stop_buffer 0.005)、`cell_c_*`(rally 0.03,0.05 / pullback 0.008)、
  `cells_eval_segments=4`、`d5_*`(0.01 / 80 / 3)。
- 宇宙欄位:`fade_gap_min=0.01` / `fade_gap_max=0.095`(**round 3 貼板線 → 0.075,
  cell_b 例外**)。
- `load_fade_config`:未知欄位 fail-fast;tuple 欄位要登記 `_TUPLE_KEYS`。

### fade_cells.py

- 宇宙:main = gap 帶 [gap_min, gap_max);low = `dataclasses.replace(gap −0.095~0.01)`;
  UC 過濾 = `is_uc_sample`(broker_ids 命中 watchlist)。
- cell_a / cell_c:進場後用 config 的 guard/災難(cfg 原樣傳入);
  cell_b:`guard_limit_dist=None` + fixed_stop(自帶風控)。
- cell_c 目前 `observation=True`(round 3 要升正式入 D5)。
- 基準線 = `_BASELINE_M = 6`(09:07 bar)無條件空,同宇宙同風控。
- D5 判定以壓測組合(stress_slippage_ticks + stress_guard_fill_high)計。
- **無底倉臂**(round 3 新增:分點數 × gap 桶條件格,統計非搜索)。

### fade_diagnose.py

- `diagnose_pool_fade`:四池(tiger_2plus/tiger_1/control/scan)無條件 fade
  (首根 open 進場、NO_STOP_HOLD_COMBO)+ 判定式(i)(ii) + variants
  (stress、`lock_penalty_grid` 逐值)。
- 日聚類 SE(`cluster_se`)、日內分層洗牌(`stratified_permutation_p`)、
  日×成交額雙重分層,全部可重用。
- 判定輸出為單一 `continue_uc` 布林(**round 3 要拆 Q1/Q2 兩題**)。

## 2. Caller map(fade_simulate 消費端)

| caller | 用法 | round 3 影響 |
|---|---|---|
| `fade_cells._simulate_cell_trades` | cell_a/c 用 cfg 風控;cell_b 用 fixed_stop + guard off | 🔴 主戰場:停損語意全換(結構高 + b ∧ 9% 硬線;災難回落式) |
| `fade_diagnose._pool_run` | NO_STOP_HOLD_COMBO + entry_price_override=open | §0 表 1 直接可用(lock_penalty_grid 已内建);Q1 複核用 |
| `fade_optimize.py`(GA 搜索) | simulate_fade_sample / with_tp | round 3 不動 GA(prereg 無搜索項) |
| `fade_pipeline.py`(fade-search) | 同上 + guard_dist_grid 敏感度 | round 3 不動 |
| tests(test_fade_simulate / _round2 / test_fade_guard / test_fade_tp / test_fade_phase_b) | 行為合約 | 新語意加測試;既有測試不該紅(新欄位走 None=停用預設) |

動態用法 grep:無 template string / reflection 構造 simulate 呼叫;config 欄位僅
`load_fade_config`(JSON key)與 dataclass 直接引用。CLI 子命令:fade-diagnose /
fade-cells / fade-search(cli.py)。

## 3. 現況 vs 目標(prereg 凍結結構)

| 項 | 現況 | 目標(round 3) | backward compat |
|---|---|---|---|
| 主停損 | guard 距漲停 3%(距離式)| min(結構高 × (1+b), 9% 硬線);結構高按劇本(cell_a 進場前盤中高點 / cell_b 衝關高點 / cell_c 反拉高點 / 底倉 running high) | 新欄位預設 None/停用 → 舊 config 行為不變 |
| 硬線 | 同上(guard 3%)| guard_limit_dist=0.01(漲 9%);兩線相撞事件排除出宇宙 + 計數進報告 | guard 機制本身可重用,只換參數 |
| 災難停損 | entry × 1.04 固定虧損式 | 進場後最高價回落式(操作化定義 + 回落幅度值 = change-spec 內預載定值後凍結) | 新欄位;`disaster_x` 保留(None 停用) |
| lock_penalty | base config 0.03 | 沿用;§0 表 1 定誠實區間 | 不變 |
| cell_c | 觀察格 | 升正式入 D5(rally 0.05 主變體、0.03 對照) | observation flag 翻轉 |
| 貼板線 | gap_max 0.095 | 0.075(方向臂+底倉);cell_b 例外可進 7.5~9.5% 必掛硬線 | config 值 + cell_b 宇宙特例 |
| 底倉臂 | 無 | 分點數(2+/1)× gap 桶(1~3/3~5.5/5.5~7.5)開盤無條件空 EV 表;門檻 n≥80 + 日聚類 z 顯著>0 | 純新增 |
| 判定 | 單一 continue_uc | Q1(池子有肉)/ Q2(吃法可行)分開記錄 + 保險精算表(觸發率/均成本/砍對vs砍錯) | 報告層新增 |
| 考場 | 全期間 | 2026-07-11 後 forward 唯一考場;in-window = 設計輸入 | 報告層切分 |

自由度預算(凍結):停損 b×2 + 災難錨×1;cells 4(a×1、b×1、c×2);底倉 6 格(統計);
搜索型變體總數 ≤8。

## 4. §0 收尾補跑的執行路徑(round 3 第一步,先於實作)

- 表 1(noguard × lock_penalty grid):**零 code 改動**——round 2 noguard config
  (`.claude/mod/fade-round-2/evidence/noguard_config.json`)+ `"lock_penalty_grid":
  [0.03, 0.05, 0.07]` → `fade-diagnose` CLI 既有 variants 機制。
- 表 2(noguard 同宇宙):guarded 宇宙 = 排除 `entry ≥ t1_limit × 0.97` 的事件
  (round 2 guarded run 的 `excluded_guard_at_entry`;tiger 196 = 39 + 157)。
  無現成 CLI 路徑 → scratchpad 一次性腳本(import `_pool_run` 等既有引擎,
  比照 gap_anatomy 慣例),結果落 `docs/evidence/`。
- 產出 = 停損保費預算上限(誠實區間下界),為 change-spec 的設計輸入。

## 5. 風險與注意

- 鐵律:引用 noguard +0.85% 必附上界警語(23% 再鎖單零懲罰;誠實區間
  +0.13~+0.85%,§0 表 1 定案,舊粗估 +0.17% 作廢)。
- 凍結後結構不得動;唯 b / 回落幅度依預載程序(假突破 overshoot 統計,僅用
  in-window 設計輸入)定值後凍結。
- 「災難停損回落式」草稿只有一行(候選 (i)),操作化定義(錨定量/觸發條件/與主停損
  優先序)須在 change-spec 明定並經 reviewer 審;不重開結構討論。
- forward 樣本依賴 events.csv 是否已涵蓋 2026-07-11 之後 + 分點標記/當沖資格覆蓋——
  開工時要先盤點 forward 期資料完整度(scan-events / backfill 鏈)。
- 長跑進度 log 紀律(CLAUDE.md §8):cells / diagnose 重跑要有邊界 log。
