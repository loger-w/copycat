# Round 4 Change Spec(/mod fade-round-4;2026-07-16)

上游(凍結,不得再動):`docs/superpowers/specs/2026-07-16-fade-round4-prereg-draft.md`。
現況:`.claude/mod/fade-round-4/current-state.md`。規模 = **L**(≥5 檔 + 新 CLI)。

## 1. 成功條件(SC;可驗收)

- **SC-1 新出場機制正確性**:inner_flip 停損 / tp_flush 停利 / tp_hl 停利三機制
  unit tests 全綠,含:觸發、不觸發、min gate、None=off 等價、**零 lookahead**
  (pivot 確認延遲 1 bar;累計內盤比只含已收 bar)、同 bar 衝突取最差
  (停損 > 停利,沿現有 worst 語意)。
- **SC-2 白名單迴歸**:`configs/fade_uc_round3.json` 重跑 `fade-cells` 輸出與
  `docs/evidence/uc_cells_2026-07-15-round3.md` 完全一致(除標題日期);
  round 2 形狀 config 重跑對照 `uc_cells_2026-07-15.md` 一致(沿 round 3
  `out/fade_cells_r2_regression` 慣例);pytest / ruff / pyright /
  `copycat validate`(42/42)全綠;既有 356 測試零紅。
- **SC-3 §0 前置統計可跑**:`python -m copycat fade-anatomy --config <r4 cfg>` 產出
  五項統計(MFE / 出量殺解剖 / 墊高解剖 / 內盤比 UC 分層 gate / 緩漲觀察)
  evidence 報告(md + json),各含凍結值建議欄位與 gate PASS/FAIL 判準輸出。
- **SC-4 round 4 對決可跑**:`fade-cells` 在 round 4 config 下輸出:5 主判定變體
  (cell_a/b/c×2/m7)D5 表 + 底倉 6 格 + Q2′ 判定(tiger 合併日聚類 z)+
  消融對照 5 組(診斷區)+ 敏感度列(φ 次值、b 0.0375)+ 精算表擴充
  (inner_flip 砍對/砍錯;tp_flush/tp_hl 省肉/讓肉)+ 勝率/賺賠比欄
  (avg_win / avg_loss / profit_factor)+ forward 複核區(≥20 交易日門檻沿用)。
- **SC-5 MFE / entry 欄位**:所有非 excluded 出場的 `FadeTradeOutcome.mfe_rate`
  (毛,不扣成本)與 `entry_price` 一律設值,excluded = None。

## 2. 不能破壞的既有行為白名單(比新行為更重要)

1. round 3 config(全部新欄位缺省)下,`_simulate_core` 逐 bar 行為 bit-for-bit
   不變:新機制全部 None/off 短路。
2. `simulate_fade_with_tp(tp=None)` ≡ `simulate_fade_sample`(既有測試鎖)。
3. `TRADEABLE_STATUSES` 集合內容不變(不新增 status;新機制走既有
   guard_exit / target_hit)。
4. `exit_reason` 既有五值(hardline/struct_fixed/struct_ratchet/disaster_x/
   disaster_retrace)語意與優先序(`_REASON_RANK`)不變。
5. `load_fade_config` 對舊 config 檔全部可載;未知 key 仍嚴格拒絕。
6. `fade-diagnose` / `fade-search` / replay / validate 路徑在**舊 config 下**
   行為不變(新欄位預設 off;帶 round 4 欄位的 config 餵這些路徑屬未定義用法,
   不在白名單)。
7. round 3 報告格式既有區塊(變體表 / 底倉 / 精算表 / 基準線)欄位不刪不改名,
   只新增欄與新增區塊。

## 3. Backward compat / migration

- 全部新 config 欄位 default None / 空 tuple = round 3 行為;無資料 migration。
- `FadeTradeOutcome` 新欄位 `mfe_rate` 與 `entry_price` 兩欄皆加在
  **最後、帶 default None**(現有 positional 建構不破)。
- `_SIM_FIELDS` 新增引擎讀取的欄位(hash 變 → pipeline outcome cache 自然失效,
  預期且正確);`_TUPLE_KEYS` 新增 tuple 欄。

## 4. Out of scope

緩漲反轉入對決(僅 §0(e) 描述統計)、被洗出後再進場、forward 資料回補、
D2 標記管道、tp1~tp11 網格路徑改動(不啟用不刪除)、fade_pipeline/fade_optimize
行為(僅被動相容)。

---

## 5. Diff 級規格(逐檔;🔴 行為改 / 🟢 新功能 / 🔵 純重構)

### 5.1 `copycat/backtest/fade_config.py` 🟢

新欄位(`FadeBacktestConfig`,全部 default off):

```
# --- round 4:劇本結構化出場(prereg §2;None/空 = round 3 行為)---
inner_flip_phi_grid: tuple[float, ...] = ()   # cells 層 φ 變體(主值+敏感度次值)
inner_flip_min_bars: int = 15                 # 累計比最短觀察 bar 數(自開盤)
tp_flush_z: float | None = None               # 出量殺:量 > 前 lookback 均量 z 倍
tp_flush_lookback: int | None = None
tp_flush_recovery: float | None = None        # 長下影收回比例
tp_flush_min_profit: float | None = None      # 毛利 gate(1 − close/entry)
tp_hl_k: int | None = None                    # 墊高:連續 k 對 pivot 確認
tp_hl_min_profit: float | None = None
```

- `validate_round4_fields(cfg)`(新,load + `_simulate_core` 皆呼叫,同
  `validate_disaster_fields` 慣例):tp_flush 四欄全設或全 None;tp_hl 兩欄全設或
  全 None;`inner_flip_min_bars ≥ 1`;違反 raise ValueError。
- `_TUPLE_KEYS` += `inner_flip_phi_grid`。
- `_SIM_FIELDS` += `inner_flip_min_bars, tp_flush_z, tp_flush_lookback,
  tp_flush_recovery, tp_flush_min_profit, tp_hl_k, tp_hl_min_profit`
  (`inner_flip_phi_grid` 不入 — cells 層變體,同 `struct_stop_buffers` 前例)。

### 5.2 `copycat/backtest/fade_tp.py` 🟢

新增兩個 cfg 驅動函式(與既有 combo 驅動 `_tp1` 並存,不改既有):

- `check_flush_exit(cfg, bar, running_low_post, post_bars_so_far, profit) -> float | None`:
  **結構同 `_tp1`,新低錨改為「進場後最低」**(不含 trig bar;凍結 bar 亦更新
  此錨)——量爆 z×前 lookback 均量 + `bar.low ≤ 進場後最低` + 長下影 recovery +
  min_profit gate,參數改讀 cfg.tp_flush_*。成交 = bar.close。anatomy §5.5(b)
  的 flush 事件定義**同此錨**(單一口徑)。
- `check_higher_low_exit(state, bar, profit, cfg) -> float | None` + 
  `PivotState`(dataclass,可變):pivot 偵測 —— bar i−1 為 pivot low ⟺
  `low[i−1] < low[i−2] 且 low[i−1] < low[i]`(在 bar i 確認,**無 lookahead**;
  pivot high 對稱)。維護已確認 pivot low / high 序列。觸發 ⟺ 已有 ≥ k+1 個
  pivot low 且最近 k 對全部 `L[j+1] ≥ L[j]`(殺不破前低),且最近 k 對 pivot high
  全部 `H[j+1] > H[j]`(拉回墊高),且 profit ≥ tp_hl_min_profit。
  成交 = bar.close。相等 low 視為未破(≥)。
- **PivotState 餵入範圍(寫死)**:鎖死凍結 bar 的 low/high **餵入** pivot 偵測
  (資訊真實存在),但凍結 bar 不做出場檢查(現行為;觸發只可能發生在
  非凍結 bar)。**介面拆兩段**(review 二輪 P2):`PivotState.update(bar)` =
  每個 post bar(**含凍結 bar,於 continue 前呼叫**)都餵;
  `check_higher_low_exit(state, bar, profit, cfg)` = 僅非凍結 bar 判定,
  不再內含 update。
- 兩者皆為純函式 + 顯式 state,fade_anatomy 直接 import 共用(單一實作防 drift)。

### 5.3 `copycat/backtest/fade_simulate.py` 🟢(核心;白名單 #1-#4 約束)

- `_simulate_core` 新參數 `inner_flip_phi: float | None = None`(穿透
  `simulate_fade_sample` / `simulate_fade_with_tp` 簽名,default None =
  caller 零改動)。
- 進場前預累計 `bars[0..trig_idx]` 的 up/down volume(新增 `cum_up`/`cum_dn`
  獨立累計;現有 `cum_delta` 不動);迴圈內鎖死凍結 bar 也累計(真實賣壓資訊),
  但凍結 bar 不做任何出場檢查(現行為)。
- **inner_flip 停損**(forced family):`inner_flip_phi` 非 None 且
  **`b.m ≥ cfg.inner_flip_min_bars`**(分鐘索引口徑,default 15 = 09:16 起可觸發,
  與 §5.5(d)「前 15 分鐘」統計同口徑;**不是**現有 post-entry `elapsed_bars`)
  且 `cum_up+cum_dn > 0` 且 `cum_dn/(cum_up+cum_dn) < φ` →
  `forced_fills.append((b.close, "inner_flip"))`,**append 位置在 struct 檢查之後**
  (同價同級歸因取 append 序前者 = struct 優先,明文寫死)。
  成交 = bar.close(訊號性市價出場,同 S1 慣例,**不吃 stress_guard_fill_high**
  ——非逼近漲停搶買瞬間)。`_REASON_RANK` += `"inner_flip": 2`(與 struct 同級;
  同價 tie-break 在 hardline 之下)。
- **TP 決策樹**(cfg 驅動,獨立於 combo `tp` 參數):每個非凍結 bar,
  `tree_fill = max(check_flush_exit(...), check_higher_low_exit(...))`(None 略);
  併入既有 `tp_fill` 衝突邏輯(`tp_fill = max(combo_tp, tree)`)。純 TP 出場
  status = `target_hit`,`exit_reason` = `"tp_flush"` / `"tp_hl"`(同 bar 兩訊號
  同觸發 → flush 優先,寫死);exit 價由停損 worst 決定時 exit_reason 沿現規則
  (歸因給強制成交價所屬機制,TP 不搶)。combo `tp` 單獨觸發(cells 不用)→
  exit_reason 維持 None(現行為)。
- **MFE**:迴圈內追蹤 `post_low = min(post bars low)`(不含 trig bar;鎖死凍結
  bar 也算),所有 return 點(含 locked_at_limit / closeout / excluded 之外全部)
  帶 `mfe_rate = 1.0 − post_low/entry`(毛)。excluded_* 路徑 = None。
  `FadeTradeOutcome` 末尾新增 `mfe_rate: float | None = None` 與
  **`entry_price: float | None = None`**(非 excluded 出場一律設 = 引擎內部
  entry;包裝層 hold_pnl 用它算,杜絕定價邏輯(slippage/tick 階梯/跌停 cap)
  複製體 drift——review P1)。
- 開頭呼叫 `validate_round4_fields(cfg)`(與 validate_disaster_fields 並列)。

### 5.4 `copycat/backtest/fade_cells.py` 🟢 + 🔵

- 🔵(先行,行為不變):把 `run_cells` 內宇宙構建(main/low/cellb 三宇宙 +
  `_with_bars`)抽成 module 函式 `build_universes(data_dir, cfg, watchlist_ids)
  -> dict[str, list[tuple[FadeSample, list[Bar1K]]]]`,`run_cells` 改呼叫;
  測試不動、round 3 輸出不變。
- 🟢 `_TradeRec` 新欄位:`mfe: float | None`、`hold_pnl: float | None`
  (抱到收盤同筆 pnl = `1 − bars[-1].close/outcome.entry_price − cost`,
  cost 用引擎 `_round_trip_cost(cfg)` 單一定義 import;**entry 取
  `outcome.entry_price`,不在包裝層重算定價**——review P1;
  收盤鎖死日 = None)、沿用其餘。
- 🟢 `_simulate_r3_trades` 擴參數 `inner_flip_phi: float | None = None`
  (穿透至 simulate;None = round 3 行為)+ 新 kind `"m7_arm"`
  (idx = `_baseline_entry_idx`,ratchet=b,與 baseline_m7 同進場;差異只在
  caller 給不給 round 4 出場)。
- 🟢 round 4 評估路徑 `_evaluate_round4(...)`(新函式;round 3 config →
  走既有 `_evaluate_round3` **零改動**):
  - **分流 gate(寫死)**:`tp_flush_z` / `tp_hl_k` / `inner_flip_phi_grid`
    任一啟用 → round 4 路徑(**優先於** round 3 的 `struct_stop_buffers` gate;
    round 4 config 同時需要 struct_stop_buffers 供 b 值)。
  - **變體參數來源(寫死)**:cell param 取 cfg tuples **首值**
    (round 4 config 一律收斂為單值 tuple,cell_c 例外 = 兩值皆跑,
    沿 round 3 config 慣例);b 主值 = `struct_stop_buffers[0]`、
    敏感度值 = `[1]`(若有)。
  - 主判定 5 變體 = [cell_a, cell_b, cell_c×2, m7_arm] × b 主值 ×
    φ=φ_main(`inner_flip_phi_grid[0]`)× TP 樹全開。
  - **fallback #1 路徑(寫死;prereg §0(d) FAIL)**:`inner_flip_phi_grid`
    為空 → 主判定 5 變體以 **φ=None** 跑(TP 樹 + round 3 停損結構),
    φ 敏感度列跳過,**消融「停損只 inner_flip」組跳過**(與 fallback #2 的
    「只 hl」跳過同慣例),報告印 `inner_flip: DEMOTED`。不得 IndexError、
    不得臨場裁量。
  - **fallback #2 路徑(寫死;prereg §0(c) DEMOTE)**:`tp_hl_k=None`(config
    不填)→ TP 樹只剩 flush,消融「只 hl」組跳過,報告印 `tp_hl: DEMOTED`。
  - 底倉 6 格(分點數 × gap 桶)同語意重跑(新出場)。
  - 量尺 baseline_m7 = round 3 出場(`cfg_legacy = dataclasses.replace(cfg,
    tp_flush_*=None×4, tp_hl_*=None×2)` + φ=None)。
  - 敏感度列(不入 D5,報告獨立節):φ=grid[1](若有)重跑主 5 變體;
    b=struct_stop_buffers[1](若有)重跑(φ_main);**TP 次組**(prereg §4)=
    獨立 sensitivity config 檔(僅 tp 欄位不同)重跑主 5 變體,
    **兩份 fade-cells 報告並排人工對照**(敏感度節引用兩檔路徑;不擴
    `copycat compare`——它只吃 replay 產物)——**不新增 schema 欄位**,
    次組值凍結在該 config 檔。
  - 消融 5 組(診斷,不出 D5):TP 全關 / 只 flush / 只 hl / 停損只 inner_flip
    (fixed_stop 與 ratchet 傳 None,硬線災難保留)/ 停損只結構(φ=None)。
    **聚合集合(寫死)= 主 5 變體同陣容合併重跑的 tiger 合併 EV**。
  - **Q2′ 交易集合(寫死)**:base_arm 臂(main 宇宙、idx=0 開盤進場)套
    round 4 新出場、in-window,沿 round 3 `_cluster_z_block` 日聚類 z 單尾
    p<0.05;主 5 變體**不入** Q2′。forward 複核沿 `_fwd_note`(≥20 交易日)。
- 🟢 `_ACTUARIAL_REASONS` += `"inner_flip"`;新增停利精算表
  `_tp_actuarial_block`:tp_flush / tp_hl 各報 n / rate / avg_pnl /
  **saved = pnl − hold_pnl 的 mean 與 p25/p50/p75 分佈**(正 = 提前收工省到肉;
  兩者同淨口徑、成本相消;hold_pnl None 的鎖死日排除並計數)。
- 🟢 `_stats_block` / `_rec_stats` 新增 `avg_win` / `avg_loss` /
  `profit_factor`(sum(wins)/|sum(losses)|;無虧損 = None)。
- 🟢 `_write_round4_report`(新;沿 round 3 報告骨架,新增:勝率/賺賠比欄、
  消融節、停利精算節、φ/b 敏感度節)。round 3 報告函式不動(白名單 #7)。

### 5.5 `copycat/backtest/fade_anatomy.py` 🟢(新檔;§0 前置統計)

`run_anatomy(data_dir, out_dir, cfg, watchlist, report_date) -> dict`:
共用 `build_universes` + tiger 池過濾(`is_uc_sample`)。
**內部一律以 `cfg_legacy = replace(cfg, tp_flush_*=None, tp_hl_*=None)` +
φ=None 跑模擬**(review P2:凍結值回填 round 4 config 後重跑 anatomy,
§0 統計不得被新出場機制汙染,必須可重現)。五節:

- **(a) MFE**:round 3 陣容各臂(round 3 出場語意)`mfe_rate` 分佈
  (p25/p50/p75/p90)+ closeout 交易的讓回 = `mfe − max(gross_pnl, 0)` 分佈,
  **gross_pnl = pnl + `_round_trip_cost(cfg)`(全毛口徑;review P1:
  毛淨混算會把讓回墊高 ~0.2pp,系統性偏向放行 tp_hl)**。
- **(b) 出量殺解剖**:對 tiger 池每 sample 自 **base_arm 進場窗(idx=0)** 掃
  bars,flush 事件錨 = **進場後最低**(與 §5.2 引擎同口徑),
  z ∈ {2,3,5} × lookback=5(描述掃描,非搜索——輸出分佈供凍結單值);
  報:出現率 / 首次時間分佈 / flush bar close → 收盤的後續走勢分佈
  (反彈中位數)/ recovery(下影)分佈,分 gap 桶。
  **凍結值建議欄**:z / recovery / min_profit 取自然分位。
- **(c) 墊高解剖**:`PivotState` 共用實作,**依 round 3 各臂進場 idx 起算**
  (共用 entry finders,與引擎套用窗口同語意;review P2),k ∈ {2,3}:
  結構出現率 / 確認時間 / **讓肉 = 確認價 vs 進場後(確認前)最低**分佈
  (價格毛口徑)/ 確認後 → 收盤走勢分佈。
  **降級判準輸出(兩邊同毛口徑)**:若讓肉中位數 > (a) 的讓回中位數
  (抱到收盤平均代價)→ 報告印 `tp_hl: DEMOTE`(prereg fallback #2)。
- **(d) 內盤比 UC 分層 gate**:tiger 池,前 15 分鐘累計內盤比桶
  (<0.45 / 0.45–0.55 / >0.55)× gap 桶(沿 `base_arm_gap_edges`):
  後續摸板率(15 分鐘後任一 bar.high ≥ 漲停×(1−0.01),與硬線一致)。
  **PASS 判準(寫死)**:tiger 合併 >0.55 桶摸板率 < <0.45 桶,且 gap 分層
  方向一致 ≥ 2/3 層。PASS → φ 候選 = {0.45, 0.55}(主值 = 分層區辨力較強者,
  報告印建議);FAIL → 報告印 `inner_flip: DEMOTE`(prereg fallback #1)。
- **(e) 緩漲觀察**:緩漲段 = 連續 ≥10 bars close 不減且單 bar 漲幅 ≤0.3%;
  報出現率 + 段結束後 10 bars 方向分佈。純描述。

輸出:`<out>/anatomy.json` + `docs/evidence/fade_round4_anatomy_<date>.md`。

### 5.6 `copycat/cli.py` 🟢

- 新 subcommand `fade-anatomy`(`--data-dir` / `--config` / `--out`
  default `out/fade_anatomy` / `--watchlist` / `--report-date`),dispatch 到
  `run_anatomy`。既有 subcommand 不動。

### 5.7 測試(全 🟢 新增;既有測試預期**零紅**——本 mod 無 🔴)

| 檔 | 內容 |
|---|---|
| `tests/backtest/test_fade_simulate_round4.py` | inner_flip:觸發(φ 下穿)/不觸發(φ=None、min_bars gate、比例在 φ 上)/成交=close 不吃 stress/exit_reason=inner_flip、status=guard_exit/與硬線同 bar worst;TP 樹:flush 觸發/min_profit gate/hl 觸發(手工 pivot 序列)/hl 相等 low 不破/pivot 無 lookahead(確認延遲 1 bar)/**凍結 bar 參與 pivot 偵測(手工案例)**/同 bar flush+hl → flush/停損+TP 同 bar 取 worst/tp 樹 off ≡ round 3 輸出;mfe_rate + entry_price:closeout/stopped/locked 設值、excluded=None;validate_round4_fields 全排列 |
| `tests/backtest/test_fade_cells_round4.py` | m7_arm 進場 idx=6;round 4 分流 gate(round 3 config 走 _evaluate_round3;round 4 gate 優先序);**fallback #1(φ grid 空 → φ=None 跑、不 IndexError、DEMOTED 註記)與 #2(tp_hl_k=None → 樹只剩 flush)**;消融 wiring(各組件 off 傳參正確);_tp_actuarial_block saved mean+分位;_stats_block profit_factor;cfg_legacy baseline 等價 round 3 baseline;hold_pnl 用 outcome.entry_price(鎖死日 None) |
| `tests/backtest/test_fade_anatomy.py` | **(a) MFE 聚合 + 讓回毛口徑(手工案例)**、(b) flush 事件偵測(進場後最低錨)、(c) 讓肉計算 + DEMOTE 判準、(d) 摸板率分桶 + PASS/FAIL 判準、(e) 緩漲段偵測(小型手工 bars) |
| `tests/test_fade_config.py`(擴) | 新欄位 load / 未知 key 拒絕不變 / `_SIM_FIELDS` 含新引擎欄位 / tuple keys |

既有測試逐一標:**全部「不該紅」**(新機制 default off);任何既有測試紅 =
打到無關東西,回本 spec 檢查。

## 6. Commit 切分(🔵 → 🟢;無 🔴)

1. 🔵 refactor(backtest): fade_cells 宇宙構建抽 `build_universes`(行為不變)
2. 🟢 feat(backtest): round 4 config 欄位 + validate + `_SIM_FIELDS`
3. 🟢 feat(backtest): fade_tp cfg 驅動 flush / higher-low + PivotState
4. 🟢 feat(backtest): fade_simulate inner_flip 停損 + TP 決策樹 + mfe_rate
5. 🟢 feat(backtest): fade_cells round 4 評估路徑(m7 臂/消融/精算擴充/報告)
6. 🟢 feat(backtest): fade_anatomy §0 五項統計 + CLI fade-anatomy
7. (跑完 §0 後)🟢 feat(backtest): configs/fade_uc_round4.json 凍結值落 config

## 7. 已知風險 / 註記

- pivot 定義(嚴格 < 兩鄰)對平頂/平底 bar 序列不產生 pivot——墊高結構在
  盤整型走勢偵測率偏低,屬保守向(少收工 ≠ 錯收工);§0(c) 統計會量化出現率。
- inner_flip 用「自開盤累計」而非滾動窗:與 cell_a 進場 gate、全池證據同語意;
  滾動窗版列 round 5 候選(停車場)。
- `hold_pnl` 於收盤鎖死日 = None(當日買不回,無「抱到收盤」對照),
  saved 統計排除並計數——防止停利省肉被鎖死日灌水。
- TP 次組敏感度走獨立 config 檔(不改 schema):次組值凍結於該檔;
  若 §0 分佈只支持單組,次組不設並於報告註記(prereg §4 該句以此落地)。
- inner_flip 的 `b.m` 口徑:m 為分鐘索引,`inner_flip_min_bars=15` 代表
  09:16 起可觸發;§5.5(d) 統計窗同口徑,防凍結值遷移失真。

self_review_head: b9812c7
