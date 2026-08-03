# Current State: fade-round-2(2026-07-14)

規格上游:`docs/strategy-decisions.md`(§2 D1-D6 定案 + §4 執行要點與判定式;本檔只記現況事實)。
Baseline(分支 mod/fade-round-2 開工時):**pytest 274 passed / ruff 0 / pyright 0**。

## A. 資料現況(D2 標籤回標的前提)

- **neigui 分點資料對 scan 事件覆蓋率 = 0%**(實測交集):
  `neigui/backend/data/research/five-tigers/event_brokers.jsonl`(7.9 MB,3,511 行)是
  事件驅動抓的,恰好 = 舊種子池(tiger_csv 1,029 + control 2,482),與 scan 7,389 筆
  完全不重疊 → strategy-decisions D2 的「覆蓋率 <90% 改重抓」條件已觸發,**直接走
  FinMind 重抓,不接 neigui 檔案**。
- neigui 存檔語意:每事件只留 **T 日 top-30 淨買超分點**(broker_id/name/buy/sell 股數,
  已跨價位聚合);賣方大戶與價位明細**未留存**。tiger 標籤語意 = watchlist 分點 ∈
  T 日 top-30 淨買超。
- FinMind 端點:`GET /api/v4/taiwan_stock_trading_daily_report`,params
  `{data_id, date}`(**per stock-day 一發,不吃日期區間**),Bearer header 必須。
  量級:scan T 日 = 7,389 req(~1.5 hr @ 6,000 req/hr Sponsor 配額);若補 T+1 日
  +7,389;若把舊池重抓成全量(修 top-30 截斷)+3,511。每日更新 ~30-130 req/日(可忽略)。
  區間替代:`taiwan_stock_trading_daily_report_secid_agg` 吃日期區間但必填分點 id
  (5 分點 × 1,377 檔 = 6,885 req,只覆蓋 watchlist 視角)。
- neigui 抓取樣板:`fetch_brokers_all.py`(8 req/s throttle + Semaphore(5) +
  429/502/503 退避 + progress 續傳);copycat 側樣板 = `backfill_daytrade.py`
  (Bearer/`TimeoutError` 重試/manifest 續傳/空回應日不進 manifest/atomic write/可注入 fetch)。
- `events.csv`(10,900 筆):`broker_ids` 只有 tiger_csv 有值,pipe 分隔,全檔僅
  5 個 id(= watchlist 成員,非完整分點資料)。watchlists/*.json schema:
  `{name, members: [{broker_id, name, role}]}`。

## B. 程式現況(caller map 摘要,行號為開工時工作樹)

### fade_diagnose.py(103 行)— round 2 主線要正式化的位置
- 唯一 public:`diagnose_limit_approach(samples_bars, cfg)`(:73),輸出 per_dist × 分桶
  統計;唯一 caller `fade_pipeline.py:684-691`(僅 wf 模式,**對全 universe 重讀 1K**,
  效能債);無獨立 CLI subcommand(掛在 fade-search 內);報告渲染 `fade_report.py:218-246`。
- `_quantile`(:22)與 `search.py:33` 演算法不同(int(p*len) vs nearest-rank)。
- 測試:test_fade_diagnose.py × 2。

### fade_simulate.py(257 行)
- `FadeSample`(:28-37):stock_id/date/t1_date/limit/t1_open/gap/broker_ids/source。
- `TRADEABLE_STATUSES`(:51-53)單一定義;消費端 fade_pipeline.py:25-27、
  fade_optimize.py:13-15;同一性測試 test_fade_guard.py:152-155。
  (注意:舊 tday `pipeline.py:79` 另有不相干的 `_TRADEABLE`。)
- guard:進場前置檢查 :89-92(entry >= guard_level → `excluded_guard_at_entry`,
  **下游無計數器,靜默略過**);盤中觸發 :149-150,成交 `max(guard_level, b.close)`。
- disaster :93/:151-152;forced_fills → status `guard_exit` :205-214(出場價取最差)。
- lock_penalty :228-233(全日鎖死 `t1_limit×(1+p)`);鎖死凍結 bar :121-131
  (guard/disaster/停損全不觸發)。
- 滑價唯一套用點 = 進場價 :85(`stress_slippage_ticks` 只墊進場);**出場價無滑價項**
  → round 2「guard 成交 = bar.high」壓測變體要在 :149-150 / :205-214 一帶動。
- guard 敏感度網格樣板(lock_penalty 敏感度可類比):`fade_pipeline.py:302-307`
  (`dataclasses.replace` 逐格重模擬,**每格全量,效能債**)。

### fade_pipeline.py(723 行)
- `build_fade_universe`(:46-130)過濾順序:daytrade(:82-91,fail-fast :69-72)→
  1K 存在性(:93-106)→ gap band(:108-113,`fade_gap_min=0.01 / fade_gap_max=0.095`)。
  source/broker_ids 直通 FadeSample(:124-125);**broker_ids 下游目前零消費**。
- `run_fade_arm`(:379-637)wf 路徑 :446-478 vs 單切分 :480-637;重複段 :456-465 vs
  :551-564(結構債)。`lock_feats` 只有 `{"gap_pct"}`(:412)——**lock_quality 特徵
  完全未接入 backtest**(grep 零命中)。
- `_run_walk_forward`(:179-363):fold GA → val top-1 → t1300 → TP → fold-test +
  stress(:299-301)+ guard 敏感度(:302-307);by_source 分層 :335-339(O(S×T) 重掃)。
- dead code:`_param_hash` :366-368、`_samples_hash` :371-376(零 caller)。
- `run_fade_pipeline`(:640-723):diagnose 僅 wf(:684-691);rules_final.json :704-720。

### fade_config.py(432 行)
- 風控欄位 :130-133(guard/disaster/lock_penalty/guard_dist_grid);wf 欄位 :135-138;
  `_TUPLE_KEYS` :247-287(新 tuple 欄位必加);`_SIM_FIELDS` :289-336(影響模擬的欄位,
  新模擬參數必加,否則 config hash 不變);`fade_sim_config_hash` :353-356
  (只寫進 rules_final.json,**無 cache 讀取端**)。
- combo 手動 8 欄複製:`enumerate_fade_stop_combos` :232-243(結構債)。

### fade_optimize.py(371 行)
- `build_cross_arm_table` :267-316 vs `build_wf_cross_arm_table` :319-371:`_sort_key`
  ×2 逐字同(:303-309 / :358-364)+ 排序/appendix 段逐字同(結構債)。
- `_strip_s5` :135-147 / `_rebuild_combo` :150-160 手動欄位複製(結構債)。
- stress 壓測消費 :240-245;`optimize_rule_tp` 重算 stops 已算過的 mask(:214 vs :104,
  效能債)。

### cli.py(207 行)
- 11 個 subcommand,字面 if 鏈 dispatch(:89-186),無動態拼接;
  `_resolve_finmind_token` :190-203(env → .env → RuntimeError)。
- 新 subcommand 落點:parser 定義區(:25-87)+ dispatch 鏈(:89-186)。

### engine/lock_quality.py(132 行)
- `LockQualitySignals`(:13-27):first_touch_idx/time、lock_idx/time/bucket、n_reopens、
  violent_pull、prelock10_gain、vol_after_lock_share、queue_bucket、day_volume、tier。
  → **三級評等(strategy-decisions §4)需要的原料全齊**,只差接入 backtest 特徵管線
  (現況消費端僅 engine/t1_open.py 與 replay/runner.py)。

### 動態用法
- 無 importlib/字串拼接 dispatch。`getattr` 三處:config hash(固定名單)、
  `fade_report.py:24-32/121`(cfg duck-typed 防禦讀取——**改 FadeBacktestConfig 欄位名
  時的隱性 caller**)。`dispatch_trigger`(fade_arms.py:240-247)有 `arm.name ==
  "fixed_time"` 字串分支——**新增臂要顧到**。
- 函式層延遲 import:cli.py 各分支、fade_pipeline.py :163/:190-191/:611-612/:676-677/:686。

### 測試佈局(相關者)
fade_simulate 10 + fade_guard 9 + fade_universe_filter 4 + fade_walk_forward 6 +
fade_phase_b 11 + fade_round1_config 5 + fade_report_round1 3 + fade_diagnose 2 +
fade_features 16 + fade_tp 27 + fade_trigger 17 + cli_fade 2 + scan_events 5 +
backfill_daytrade 6 + backfill_finmind 6 + store 4 + lock_quality 10;全 suite 274。

## C. 結構債對照(next-time 2026-07-11 節,全部確認存在)

| 條目 | 位置 |
|---|---|
| run_fade_arm 雙路徑重複 | fade_pipeline.py:456-465 vs :551-564 |
| cross_arm 兩份(_sort_key ×2) | fade_optimize.py:303-316 vs :358-371 |
| fade_report 6 處 wf 分叉 | fade_report.py:31/:57/:128/:150/:154/:156 |
| _strip_s5/_rebuild_combo/enumerate 手動欄位複製 | fade_optimize.py:135-160、fade_config.py:232-243 |
| dead code _param_hash/_samples_hash | fade_pipeline.py:366-376 |
| 效能:診斷重讀 1K / TP mask 重算 / guard grid 全量重模擬 / by_source 重掃 | fade_pipeline.py:688-690、fade_optimize.py:214、fade_pipeline.py:302-307、:335-339 |
| _fmt ×2 / _quantile ×2(演算法不同) | report.py:11 vs fade_report.py:9;search.py:33 vs fade_diagnose.py:22 |

## D. 現況 vs 目標

| 面向 | 現況 | 目標(round 2) | caller 影響 | backward compat |
|---|---|---|---|---|
| 分點標籤 | broker_ids 僅舊 tiger 池有值(watchlist 命中);scan 全空 | 新 `backfill-brokers` CLI:FinMind 分點日報 per stock-day 回標 7,389 筆 + 每日增量;events.csv broker_ids 補值 | events.csv 就地更新(schema 不變);scan_events 冪等規則不可破壞 | 只補空值不改既有值;標籤語意沿 neigui(watchlist ∈ T 日 top-30 淨買超)須寫死 |
| 三池複驗 | 無條件分層只存在於 session 暫存腳本(日線粒度) | `fade_diagnose` 增三池複驗(1K+guard+悲觀滑價、日聚類 SE、日內分層 permutation、成交額雙重分層)+ 獨立 CLI 入口 + 判定式輸出 | 新增為主;diagnose 現有函式/報告章節不動 | 新函式並存,舊 `diagnose_limit_approach` 簽名不變 |
| 劇本格子 | 7 臂 GA 搜索(全池) | 3 個 pre-registered cells(先拉再出/衝停失敗/低開反拉觀察格),UC 池,wf 只評估;D5 門檻細則已寫死 | 新模組(fade_cells?);dispatch_trigger 字串分支若加臂要顧 | GA 路徑不刪(退役臂只是不再跑) |
| 參數化軸 | gap band 過濾 + gap 桶報表 | headroom 表達 + guard 死局通則(headroom<guard → 非 squeeze 臂排除,含 baseline) | build_fade_universe / 模擬前置檢查(excluded_guard_at_entry 已有,缺計數器) | headroom 與 gap 在 T+1 對 T 收盤漲停事件是單調變換,語意等價、表達不同 |
| 壓測 | stress 只墊進場滑價;guard 成交 max(level, close) | 加「guard 成交 = bar.high」變體 + lock_penalty 敏感度(到 +7%) | fade_simulate :149-152/:205-214、敏感度網格樣板 :302-307 | 新 config 欄位 optional 預設 None = 舊行為 |
| 鎖板品質 | LockTracker 特徵齊但 backtest 零接入 | 三級評等(門檻寫死 config)接入 UC 池分層驗證 | 特徵組裝 fade_pipeline :412 一帶 | 純新增特徵欄 |
| wf 結構債 | §C 全部存在 | 動 wf 程式前先清(🔵 先行) | 見 §C 行號 | 行為零差異,274 測試全綠不變 |

## E. 風險

- FinMind 分點日報實際欄位/一天量級未實抓過(neigui 聚合後才落檔)——實作首日先抓
  1-2 個樣本日驗欄位,再開全量。
- 7,389 req 全量回標 ≈ 1.5 hr,配額共享(其他 backfill 同時跑會互相擠)。
- 標籤語意選擇(top-30 淨買超 vs 淨買門檻)影響 tiger 池組成——必須與舊池語意一致,
  否則新舊標籤不可比(Phase 2 要定案)。
- excluded_guard_at_entry 目前靜默——headroom 死局通則落地時要補計數器,否則排除量不可見。
