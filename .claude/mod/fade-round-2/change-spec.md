# Change Spec: fade-round-2 — UC 池特化(標籤回標 + 三池複驗 + 劇本格子)

規格上游:`docs/strategy-decisions.md`(§2 D1-D6 定案 + §4 執行要點與判定式)。
現況盤點:`.claude/mod/fade-round-2/current-state.md`(baseline 274 passed / ruff 0 / pyright 0)。
User 拍板(2026-07-14):架構方案一(新模組並存,舊 GA 管線不動);抓取範圍 B
(scan T 日 + 舊池重抓,存完整原始資料);tick 重驗移出本輪。

## 成功條件(SC)

- **SC-1 分點原始資料回補**:`backfill-brokers` CLI 抓 FinMind
  `taiwan_stock_trading_daily_report`(per stock-day 一發,Bearer),落
  `data/brokers/<stock_id>/<date>.json`(**完整 broker 層聚合**:broker_id/name/buy/sell
  股數,不截 top-30)。範圍 = events.csv 全事件 T 日(~10,900 stock-days),manifest
  續傳冪等,rate sleep 0.65s(≈5,500/hr < 6,000 配額),402 → RuntimeError 停止(續傳可重跑)。
  驗法:unit tests(fetch mock / manifest 續傳 / atomic / 空回應日不進 manifest / 402 停止)
  + 實跑首日先抓 2 個樣本日驗欄位再開全量 + 抽 10 筆對 neigui `event_brokers.jsonl` 舊值核對。
- **SC-2 標籤管道**:`label-events` CLI 讀 brokers store × watchlist → 就地更新 events.csv
  `broker_ids`(**只補空值,不改既有值**;冪等;atomic 寫回)。標籤語意(寫死,與舊池一致):
  watchlist broker ∈ 該股 T 日 **top-5 淨買超**(net = buy − sell,排序 = net desc、
  tie-break broker_id asc)。**[Phase 7 實證修正 2026-07-15:原 spec 寫 top-30,
  一致率 gate 炸出(48.98%)後回溯 —— top-30 是 neigui 儲存層截斷,標籤準則是
  top-5(重算一致率 100.00%、mismatch 全為 old ⊂ new、佐證 event_top5.csv);
  修正 commit 719233f]**。**scan-events 保留條款(R11)**:characterization test 鎖定
  scan-events 重跑不清空既有列的 broker_ids(每日更新順序 = scan-events →
  backfill-brokers 增量 → label-events,為隱性契約,寫入 runbook)。`--verify-existing` 模式:對既有 tiger_csv 1,029 筆
  重算標籤比對,輸出一致率。
  驗法:unit tests(top-30 邊界 / tie-break / 只補空值 / 換 watchlist 重標)+
  實跑 `--verify-existing` 一致率 ≥99%(容忍 FinMind 事後資料修正;<99% → 停下查因)。
- **SC-3 三池複驗(主問題,不依賴 SC-1/2)**:`fade_diagnose.diagnose_pool_fade` 新函式 +
  `fade-diagnose` CLI 子命令:全 universe 無條件 fade(進場 = T+1 首根 1K bar open −
  slippage_ticks,經 `_simulate_core` 新 optional 參數 `entry_price_override` 實現
  (R4;見 fade_simulate diff 節),過 `excluded_guard_at_entry` 前置檢查;
  出場 = guard/disaster/鎖死/收盤)。**分池分派優先序(R5,寫死)**:broker_ids 命中
  watchlist → tiger_1 / tiger_2plus(**不論 source**,control 來源被標記亦歸 tiger);
  未命中 → 按 source 歸 control / scan(unit test 含「control 來源已標記」案例);
  報告註記 control 池在擴池後語意變化(相似配對池被抽走命中成員)。四池輸出:
  淨 EV、日聚類 SE(CR0)、日內分層 permutation p(tiger vs scan、tiger vs control+scan,
  5,000 次、固定 seed)、T 日成交額中位數 × 日雙重分層 p、T+1 鎖回率、
  `excluded_guard_at_entry` 計數、n。**判定式操作化(R2 + round2-R1/R4,寫死)**:
  tiger = tiger_1 ∪ tiger_2plus 合併池;對照池 = **control + scan 合併(無標記全池,
  與 strategy-decisions §4「比全池對照」一致;tiger vs scan 單獨對照僅為報告項)**;
  「UC 方向值得繼續」⟺
  (i) tiger 池淨 EV 點估計 >0 且 **日聚類 SE(CR0)單尾 z 檢定** p < diagnose_p_threshold
  (標籤洗牌檢定的 null 中心是全池平均、不能檢「>0」,故 (i) 不用 permutation);
  且 (ii) tiger − 對照池差 ≥ diagnose_min_edge_pp 且日內分層 permutation
  (H1: 差 >0)單尾 p < diagnose_p_threshold。
  判定一律用 **base config**(stress / lock_penalty_grid 僅敏感度診斷,不餵判定);
  unit test 分別覆蓋 (i) z 檢定與 (ii) permutation 的門檻兩側。
  **共同期間條款(R3,寫死)**:池間比較一律限「標記覆蓋共同期間」
  (t1_date ≤ 標記截止日;SC-2 擴池後標記延伸至 2026-07-09,共同期間隨之延伸;
  期間外樣本不進對照,unit test 鎖定)。**正式判定 = SC-2 擴池後版本**(R8);
  559 池首跑僅 smoke / 方向檢查,不作判定引用;若擴池版方向正但不顯著 →
  預定處置 = 判定記「未確認」、不啟動 D4 上場、等 forward 樣本(不得改判定式)。
  變體:stress(滑價 stress_slippage_ticks + guard fill = bar.high)、lock_penalty grid
  (0.03 / 0.05 / 0.07)。產物 → `out/fade_diagnose/` + `docs/evidence/` 報告(獨立 writer,
  不動 fade_report.py)。
  驗法:unit tests(合成資料:日聚類 SE 手算對照 / permutation 已知標籤差收斂 /
  分池計數 / 判定式門檻兩側)+ 實跑報告(先用既有 559 標記池跑一版,SC-2 完成後擴池重跑)。
- **SC-4 劇本格子引擎**:新模組 `fade_cells.py`,三個 pre-registered cells(觸發器 =
  純函式吃 bars + 參數;**全部門檻進 config,本 spec 數字 = pre-registration**)。
  **cells 宇宙 = UC 池**(R1,P0):事件 broker_ids 命中 watchlist 才進 cells(cell_c
  低開宇宙同樣限 UC)——D1 拍板「主戰場 = 優式池」,全池樣本**不得**進 cell 統計
  (unit test 鎖定);**cells 正式評估在 SC-2 擴池之後**(既有 559 標記池對 cells
  細分後樣本過薄)。**每 cell 附同宇宙基準線對照**(R7):同 UC 池、同前置檢查、
  同標準風控下「第 7 分鐘無條件空」(D3 基準線),報告逐 cell 列 vs 基準線差值——
  區分「訊號有價值」vs「池子本身有肉」:
  - **cell_a 先拉再出**:宇宙 = 主池且進場當下 headroom ≥ 0.04;觸發 = 開盤後 60 分鐘內,
    自盤中高點回落 ≥0.008(沿 pullback 存活參數)且**進場當下累計內盤比 ≥ 閾值**
    (變體:0.45 / 0.55)且盤中高點 ≥ 開盤 ×(1 + cell_a_min_rally=0.01)(「先拉」前提,
    R9;開盤即陰跌不觸發);出場 = guard/disaster/收盤(標準風控)。
  - **cell_b 衝停失敗**:觸發 = 盤中曾逼近漲停 ≤d(變體:0.02 / 0.03)後,自逼近高點
    回落 ≥0.01(失敗確認)進場;**自帶風控**:fixed stop = 逼近高點 ×(1+0.005)
    (漲回逼近高點上緣即停,悲觀 max(level, close) 成交)、觸漲停鎖死照 lock_penalty
    結算;**不用距離式 guard**(cfg replace guard_limit_dist=None);災難停損照常。
  - **cell_c 低開反拉(觀察格)**:獨立宇宙 = replace(cfg, fade_gap_min=−0.095,
    fade_gap_max=0.01)(當沖/處置過濾照常);觸發 = 自開盤反拉 ≥r(變體:0.03 / 0.05)
    後回落 ≥0.008 進場;標準風控。**只統計不對決**(D5 不適用,報告標注觀察格)。
  - 評估:全期間按**日曆日期範圍四等分**(R10;等日曆非等事件數,unit test 鎖段界;
    pre-registered 無訓練期,四段 = 方向一致性檢查);per cell × 變體(a×2 + b×2 +
    c×2 = 6,個位數)輸出淨 EV / 勝率 / n / 四段方向 / vs 基準線差值 / stress 變體;
    cell_a/b 出 **D5 判定**(壓測後淨 EV ≥ d5_min_ev=0.01 + ≥3/4 段正且合計正 +
    n ≥ d5_min_n=80,全部 config 讀)。**D5 判定用的壓測組合(R6,寫死)**:
    stress_slippage_ticks + stress_guard_fill_high=True 疊加;lock_penalty 維持 base
    0.03(執行面滑價是必然成本入判定;鎖死 +7% 是尾部情境,僅入敏感度表)。
    報告標注:門檻源自同期診斷(meta 汙染),最終判定 = forward。
  驗法:每 cell 觸發 unit tests(合成 bars:觸發 / 不觸發 / 邊界 / cell_b 觸停)+
  四等分切分 + D5 判定兩側 + 變體枚舉數。
- **SC-5 headroom 死局計數**:`excluded_guard_at_entry` 由 diagnose / cells 聚合計數並
  進報告(現況被靜默吞掉);cells 與無條件 baseline 沿用同一前置檢查(比較公平性)。
  驗法:unit test(計數出現且正確)。
- **SC-6 壓測變體(模擬器)**:`FadeBacktestConfig` 新欄 `stress_guard_fill_high: bool
  = False` —— True 時 guard/disaster 觸發成交價 = max(level, **b.high**)(嘎空瞬間
  全市場搶買的狀態相關滑價);入 `_SIM_FIELDS`。
  驗法:unit test(fill = high 語意)+ **預設 False 時既有模擬輸出 bit-for-bit 不變**
  (既有 guard 測試全綠)。
- **SC-7 🔵 結構債清理(行為零差異,動 wf 前先清)**:
  cross_arm 兩份合併(`_sort_key` 單一 + 排序/appendix 共用 helper)、
  run_fade_arm 雙路徑抽 `_collect_tradeable` 共用、fade_report wf 分叉收斂、
  `_strip_s5`/`_rebuild_combo` 改 `dataclasses.replace`、
  `enumerate_fade_stop_combos` 8 個 `.get` 收斂單一建構點、
  刪 dead code `_param_hash`/`_samples_hash`。
  驗法:既有 274 測試全綠**不改任何 assertion**;validate 42/42。
- **SC-8 全 gate**:pytest / ruff / pyright / `copycat validate` 全 PASS。
- **SC-9 實跑 runbook(證據)**:見 commit 計畫末節;產物 → docs/evidence/ 報告
  (三池複驗 + cells 評估),回寫 `docs/strategy-decisions.md`(判定式結果 + tick 移出註記)。

量化驗收:SC-2 一致率 ≥99%、SC-3 判定式數字(0.3pp / p<0.05)、SC-4 變體 = 6、
D5(0.01 / 80 / 3 of 4)—— 全部從 config 讀,量法 = 報告文字 + 輸出 JSON 欄位。

## 不能破壞的既有行為白名單

1. **fade-search 全管線(GA / wf)行為不變**:預設 config 下模擬輸出 bit-for-bit;
   274 既有測試全綠且**不改任何 assertion**。(`fade_sim_config_hash` 值允許變——
   `_SIM_FIELDS` 加欄位會變 hash,但無 cache 讀取端,純記錄欄位。)
2. events.csv **schema 不變**;既有 broker_ids 值**不被覆寫**;scan-events 冪等規則不變。
3. replay / validate / tday pipeline 不碰:validate 42/42。
4. `diagnose_limit_approach` 簽名與輸出不變;fade_report 既有章節不刪
   (逼近漲停診斷照舊)。
5. backfill-daily / backfill-tc4 / backfill-daytrade / scan-events CLI 介面不變。
6. `TRADEABLE_STATUSES` 單一定義維持;本輪**不新增出場 status**(cell_b 的 fixed stop
   走既有 'stopped' / forced 語意;若實作中發現必須新增 → 停下回 spec)。
7. watchlists/*.json schema 不變(label-events 只讀)。

## Backward compat / migration

- 新 config 欄位全 optional 預設關閉/空 → 舊 config json 照載(`_TUPLE_KEYS` 補新 tuple 欄)。
- `data/brokers/` 全新 store,不影響既有 data/;可由 backfill-brokers 冪等重建。
- events.csv broker_ids 就地補值:整條資料鏈(import-neigui → scan-events →
  backfill-brokers → label-events)冪等可重建,不需備份。
- `_simulate_core` 新參數(fixed_stop_level、stress_guard_fill_high 讀 cfg)預設 None/False
  = 舊行為;既有 caller 零改動。

## Out of scope(本輪不做)

- tick 管道 + 競價量 tell 重驗(user 2026-07-14 拍板移出;獨立輪,完成後回寫
  strategy-decisions §3 #7 終判)
- T+1 日分點資料(範圍 B 不含;未來驗「隔天在哪個分點倒貨」時再抓)
- 鎖板品質三級評等接入(strategy-decisions §4 有列,**排 round 2 第二批**——
  cells 不依賴它;主問題複驗先行。明示於此避免「主問題偷換」疑慮:本輪主問題 =
  三池複驗,已在 SC-3)
- MTX 大盤層(Phase C)
- 效能債:guard grid 全量重模擬 / TP mask 重算 / by_source 重掃(→ /perf 先 profile);
  「診斷重讀 1K」由 SC-3 新設計自然消失(bars 傳遞),不另列
- 每日自動排程(管道 = 冪等 CLI,排程 user 自掛)
- fade-search 對 round 1 config 的重跑對照(白名單 1 靠測試保證,不重跑 6 小時管線)

---

## Diff 級 spec

### 🔵 純重構(先行;既有 274 測試全綠不動)

1. `fade_optimize.py`:
   - `build_cross_arm_table`(:267-316)與 `build_wf_cross_arm_table`(:319-371)的
     `_sort_key` ×2 與排序/rank/appendix 段抽共用 `_rank_and_split(rows, min_n)`;
     兩個 public 函式簽名不變。
   - `_strip_s5`(:135-147)/`_rebuild_combo`(:150-160)→ `dataclasses.replace`
     (FadeStopCombo 是 frozen dataclass)。
2. `fade_config.py`:`enumerate_fade_stop_combos` 的 8 個 `base.get`(:232-243)收斂
   單一建構 helper(維持輸出順序與內容 bit-for-bit)。
3. `fade_pipeline.py`:wf 路徑(:456-465)與單切分路徑(:551-564)的「模擬 → _TRADEABLE
   過濾 → 組平行陣列」抽 `_collect_tradeable(samples, bars_list, feats, combo, cfg)`;
   刪 `_param_hash`(:366-368)、`_samples_hash`(:371-376)。
4. ~~`fade_report.py` wf 分叉收斂~~ **[auto-default: 不動 | reason: Phase 4 實查
   (2026-07-14)——所謂 6 處分叉實為單一變數 `wf_starts`(:31 一次讀取)的 5 個
   必要條件格式點,無重複結構可收斂;強行改寫 = 重構劇場,風險 > 價值(鐵則 B
   不為未來可能加 abstraction)。R12 golden snapshot 因不重構而不需要。
   next-time 該條目由本輪關閉並註記。]**

### 🔴 行為改動:`fade_config.py` 新欄位(全 optional)

```python
stress_guard_fill_high: bool = False        # 壓測:guard/disaster fill = bar.high
lock_penalty_grid: tuple[float, ...] = ()   # diagnose 敏感度(round2 config: 0.03,0.05,0.07)
cell_a_pullback_x: float = 0.008
cell_a_headroom_min: float = 0.04
cell_a_inner_thresholds: tuple[float, ...] = (0.45, 0.55)
cell_a_window_m: int = 60
cell_b_approach_dists: tuple[float, ...] = (0.02, 0.03)
cell_b_fail_confirm: float = 0.01
cell_b_stop_buffer: float = 0.005
cell_a_min_rally: float = 0.01
cell_c_rally_pcts: tuple[float, ...] = (0.03, 0.05)
cell_c_pullback_x: float = 0.008
cells_eval_segments: int = 4
d5_min_ev: float = 0.01
d5_min_n: int = 80
d5_min_positive_segments: int = 3
diagnose_perm_iters: int = 5000
diagnose_perm_seed: int = 42
diagnose_min_edge_pp: float = 0.003   # 判定式 (ii) 差值門檻
diagnose_p_threshold: float = 0.05    # 判定式 (i)/(ii) 顯著門檻
```
- `stress_guard_fill_high` 入 `_SIM_FIELDS`(影響模擬);cell/diagnose/D5 參數**不入**
  `_SIM_FIELDS`(不影響 fade-search 模擬語意);tuple 欄位入 `_TUPLE_KEYS`。
- 新檔 `configs/fade_uc_round2.json`:fee_discount 0.84、guard 0.03、disaster 0.04、
  lock_penalty 0.03、universe_daytrade_filter true、lock_penalty_grid、cells/D5 參數
  (值 = 上列預設,顯式寫出 = pre-registration 快照)。
- 測試:load 舊 config 不炸、round2 config 全欄位載入、hash 隨 stress_guard_fill_high
  變動、cell 參數不動 hash。

### 🔴 行為改動:`fade_simulate.py`

1. `_simulate_core` 增 `fixed_stop_level: float | None = None`(穿透
   `simulate_fade_sample` optional 參數):每根未鎖 bar,`b.high >= fixed_stop_level` →
   併入 forced_fills(成交 max(level, b.close)),status 沿 'guard_exit' 既有 forced 語意
   (**不新增 status**,白名單 6)。鎖死凍結 bar 不觸發(沿 R15 語意)。
2. `_simulate_core` 增 `entry_price_override: float | None = None`(R4;穿透
   `simulate_fade_sample`):None = 舊行為(trig.close 為進場參考價);非 None 時
   進場參考價 = override(SC-3 傳首根 bar open),滑價照扣
   `entry = max(override − slippage_ticks × tick_size(override), t1_down_limit)`,
   guard/disaster 前置檢查與 level 計算一律以此 entry 為準。
3. `stress_guard_fill_high`(讀 cfg):guard/disaster/fixed_stop 觸發成交價
   `max(level, b.high)`(取代 b.close;:149-152 一帶)。
4. 測試:fixed_stop_level 觸發/未觸發/鎖死凍結不觸發、entry_price_override 語意
   (含 override 下 excluded_guard_at_entry)、fill_high 語意、
   **三參數預設下既有 golden 輸出不變**。

### 🟢 新功能:`copycat/data/backfill_brokers.py` + CLI `backfill-brokers`

```python
def run_backfill_brokers(data_dir: Path, events_csv: Path, token: str,
                         fetch: FetchFn | None = None, sleep_s: float = 0.65) -> dict[str, int]:
    """events.csv 全事件 (stock_id, date) → FinMind taiwan_stock_trading_daily_report
    → data/brokers/<stock_id>/<date>.json(broker 層聚合,完整不截斷)。
    manifest 續傳(data/brokers/manifest.json,key=(stock_id,date));空回應不進 manifest;
    402 → RuntimeError。"""
```
- 接入慣例沿 `backfill_daytrade`(Bearer / retry 含 TimeoutError / atomic write /
  可注入 fetch);原始回傳(分點×價位)聚合為 broker 層(sum buy/sell 股數)後落檔,
  檔內含 `_fetched_at`。
- CLI:`backfill-brokers --data-dir --events-csv`(token 走 `_resolve_finmind_token`)。
- 測試 ~6:聚合正確、manifest 續傳、空回應、402、atomic、冪等 skip。

### 🟢 新功能:`copycat/data/label_events.py` + CLI `label-events`

```python
def label_events(data_dir: Path, events_csv: Path, watchlist_path: Path,
                 verify_existing: bool = False) -> dict[str, int]:
    """brokers store × watchlist → events.csv broker_ids 就地補值(只補空、冪等、atomic)。
    語意:watchlist broker ∈ T 日 top-30 淨買超(net=buy−sell desc,tie broker_id asc)。
    verify_existing:不寫檔,對既有非空 broker_ids 重算比對,回報一致率。"""
```
- CLI:`label-events --data-dir --events-csv --watchlist [--verify-existing]`。
- 測試 ~5:top-30 邊界(第 30/31 名)、tie-break、只補空、換 watchlist、verify 模式。

### 🟢 新功能:`fade_diagnose.py` 擴充(既有函式不動)

```python
def diagnose_pool_fade(samples: list[FadeSample], bars_map: dict,
                       turnover_map: dict[tuple[str, str], float],
                       label_cutoff: str, cfg: FadeBacktestConfig) -> dict[str, object]:
    """四池無條件 fade 複驗(round2-R3:turnover_map = T 日成交額 close×volume_lots,
    caller 從 data/daily/prices.csv 預先 join;label_cutoff = 標記截止日,
    共同期間條款 t1_date <= label_cutoff 以此參數注入):
    per-pool 淨 EV / 日聚類 SE / 鎖回率 / excluded 計數;判定式 (i) 日聚類 z +
    (ii) 日內分層 permutation(另出 日×成交額雙重分層 p);判定布林 + 依據;
    stress 與 lock_penalty_grid 變體。"""

def write_pool_fade_report(result: dict, path: Path) -> None: ...
```
- helpers:`_cluster_se`、`_stratified_permutation(groups, iters, seed)`(scratchpad
  分析正式化;成交額 = T 日 close × volume_lots,從 daily 讀)。
- 池定義:tiger_1(broker_ids 恰 1 個 watchlist 成員)/ tiger_2plus / control / scan
  ——**分池依 events.csv 當下標籤**,SC-2 前後各跑一版天然對照。
- CLI:`fade-diagnose --data-dir --out --config --report-date --report-dir
  --label-cutoff --watchlist`(label_cutoff 必填,runbook 兩次實跑分別填
  2026-06-25 / 2026-07-09)。
- 測試 ~8:SE 手算對照、(i) z 檢定兩側、(ii) perm 已知差兩側、雙重分層、分池計數
  (含 control 已標記歸 tiger、共同期間外樣本不進對照)、報告章節。

### 🟢 新功能:`copycat/backtest/fade_cells.py` + CLI `fade-cells`

```python
@dataclass(frozen=True)
class CellTrade: ...  # sample / variant / entry_m / entry / exit / status / pnl

def find_cell_a_entry(bars, limit, inner_threshold, cfg) -> tuple[int, float] | None: ...
def find_cell_b_entry(bars, limit, approach_dist, cfg) -> tuple[int, float, float] | None:
    ...  # (entry_idx, entry_price, approach_high)
def find_cell_c_entry(bars, rally_pct, cfg) -> tuple[int, float] | None: ...

def evaluate_cells(data_dir: Path, cfg: FadeBacktestConfig,
                   watchlist_path: Path) -> dict[str, object]:
    """宇宙(R1):build_fade_universe 後**再過 UC 池過濾**(broker_ids 命中 watchlist
    才留;cell_a/b 用主池 gap band、cell_c 用低開宇宙 replace(cfg,
    fade_gap_min=-0.095, fade_gap_max=0.01)——邊界互斥:主池 = [0.01, 0.095)、
    低開池 = [-0.095, 0.01),gap=0.01 屬主池(R10;沿 :108-113 含下排上語意));
    出場模擬走 simulate_fade_sample(cell_b 傳 fixed_stop_level=approach_high×(1+buffer)
    + replace(cfg, guard_limit_dist=None));**基準線**(R7):同 UC 池同風控之
    「第 7 分鐘 bar close 無條件進場」隨 cells 一起評估,逐 cell 報 vs 基準線差值;
    全期間等日曆四等分方向一致 + D5 判定(壓測組合 = stress_slippage +
    guard_fill_high 疊加)+ stress 變體;cell_c 標 observation=True。"""

def write_cells_report(result: dict, path: Path) -> None: ...
```
- 進場價一律 bar close − slippage_ticks(悲觀,沿現行語意);進場過
  `excluded_guard_at_entry` 前置(cell_b 除外——它 guard=None,但仍過 headroom>0 檢查)。
- 內盤比 = 累計 down_volume /(up+down)(unch 不計),從第 1 根累計到觸發 bar。
- CLI:`fade-cells --data-dir --out --config --report-date --report-dir --watchlist`
  (預設 watchlists/five_tigers.json)。
- 測試 ~11:三 cell 觸發×(觸發/不觸發/邊界)、cell_a 拉幅前提、cell_b 觸停走
  fixed_stop、**UC 池過濾(全池樣本不進統計)**、基準線同宇宙、等日曆四等分段界、
  D5 兩側、變體數=6、觀察格標記。

### 🟢 CLI(`cli.py`):新增 `backfill-brokers` / `label-events` / `fade-diagnose` /
`fade-cells` 四個 subparser + dispatch(字面 if 鏈,沿現行)。測試 ~3(smoke)。

## 既有測試標記

- 該紅:**無**(全部 optional 欄位 + 新模組 + 🔵 不動測試)。
- 不該紅:全部 274(尤其 test_fade_simulate 10 / test_fade_guard 9 / test_fade_tp 27 /
  test_fade_phase_b 11 / test_fade_walk_forward 6)。
- 新測試合計 ≈ 30-32。

## Commit 計畫(🔵 → 🔴 → 🟢)

1. 🔵 fade_optimize cross_arm 合併 + combo replace
2. 🔵 fade_pipeline _collect_tradeable + dead code 刪除;fade_report wf 分叉收斂
3. 🔴 fade_config 新欄位 + configs/fade_uc_round2.json + 測試
4. 🔴 fade_simulate fixed_stop_level + stress_guard_fill_high + 測試
5. 🟢 backfill_brokers + CLI + 測試
6. 🟢 label_events + CLI + 測試
7. 🟢 fade_diagnose 擴充 + CLI + 測試
8. 🟢 fade_cells + CLI + 測試
9. (資料)實跑 runbook(依賴序;SC-3 第一版不等 SC-1/2):
   ```
   python -m copycat fade-diagnose --config configs/fade_uc_round2.json --report-date 2026-07-15 --label-cutoff 2026-06-25   # 559 池 smoke 版
   python -m copycat backfill-brokers                                                                                        # ~2 hr,首日先 2 樣本日驗欄位
   python -m copycat label-events --watchlist watchlists/five_tigers.json --verify-existing                                  # 一致率 gate >=99%
   python -m copycat label-events --watchlist watchlists/five_tigers.json
   python -m copycat fade-diagnose --config configs/fade_uc_round2.json --report-date 2026-07-15 --label-cutoff 2026-07-09   # 正式判定版
   python -m copycat fade-cells --config configs/fade_uc_round2.json --report-date 2026-07-15
   ```
   報告落 docs/evidence/;回寫 docs/strategy-decisions.md(判定式結果、cell_c 樣本數
   是否達標升級、tick 移出註記)。**每日更新順序(隱性契約,R11)**:scan-events →
   backfill-brokers(增量)→ label-events;559 池首跑 = smoke,正式判定 = 擴池版(R8)。

## Review 修正紀錄(round 1)

- R1(P0)accepted:cells 宇宙 = UC 池(watchlist 命中過濾 + 全池不進統計 unit test);
  正式評估在 SC-2 後
- R2(P1)accepted:判定式操作化(tiger = 合併池、單尾 permutation p<0.05 ×2 條件、
  base config 判定)
- R3(P1)accepted:共同期間條款(t1 ≤ 標記截止日,unit test)
- R4(P1)accepted:`entry_price_override` optional 參數入 _simulate_core diff 節
- R5(P1)accepted:分池分派優先序(命中 → tiger 不論 source;含 control 已標記 test)
- R6(P1)accepted:D5 壓測組合寫死(stress_slippage + guard_fill_high 疊加;
  lock_penalty 尾部僅敏感度)
- R7(P1)accepted:cells 附同宇宙第 7 分鐘基準線對照(D3 量尺)
- R8(P2)accepted:正式判定 = 擴池版;不顯著預定處置寫死
- R9(P2)accepted:cell_a_min_rally=0.01 拉幅前提
- R10(P2)accepted:typo 修正、等日曆四等分、cell_c 邊界互斥標明
- R11(P2)accepted:scan-events broker_ids 保留 characterization + 每日順序入 runbook
- R12(P2)accepted:fade_report 重構前 golden snapshot byte 比對

## Review 修正紀錄(round 2)

- R1(P1)accepted:判定式 (i) 改日聚類 SE 單尾 z 檢定(標籤洗牌 null 中心 = 池平均,
  不能檢 >0);permutation 只用於 (ii)
- R2(P1)accepted:`diagnose_min_edge_pp` / `diagnose_p_threshold` 入 config 欄位清單 +
  round2 config 快照 + 載入測試
- R3(P1)accepted:`diagnose_pool_fade` 簽名補 turnover_map + label_cutoff;
  CLI `--label-cutoff` 必填,runbook 兩跑分別 2026-06-25 / 2026-07-09
- R4(P1)accepted:判定 (ii) 對照池 = control+scan 合併(無標記全池,對齊上游
  「比全池對照」;tiger vs scan 降為報告項)

Known Risk(輪數上限,沿 round 1 慣例):round 2 的 4 條 P1 修訂無第三輪確認
(/mod max 2 輪),以「全 finding 有具體 resolution 且已落 spec 本文」+ Phase 4 TDD
單元測試逐條鎖住(判定式兩側 / 共同期間 / 分派優先序 / UC 池過濾均有對應 test)
為替代保證。

## Phase 5 自評紀錄(2026-07-14)

- /code-review medium,8 finder(haiku)× 1-vote verify:**無 P0/P1 bug**
  (removed-behavior 與 cross-file 兩角度回空 = 🔵 重構與 optional 參數安全)。
- Cleanup 接受並修(ebca12e):型別歸位(object+assert → Path)、_fmt/_NO_STOP_COMBO
  重複收斂、load_turnover_map 跳列計數。駁回 3(呼叫端已 guard / 重構前既有語意 /
  兩宇宙互斥無重複 IO);P2 ×5 彙總 docs/next-time.md 2026-07-14 節。
- 完工自查:測試 321(新 47)✓ / 三類 commit 分明(🔵×3 🔴×2 🟢×4 +1 fix)✓ /
  文件同步(fade_report 不動之 [auto-default] 已記)✓。

self_review_head: ebca12e
