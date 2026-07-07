# 分點行為指紋辨識 — 評分引擎 + 歷史 replay(回測基建)設計

**日期**:2026-07-07
**狀態**:brainstorm 定稿,待實作計畫(writing-plans)
**上游文件**:CLAUDE.md §0a、`docs/strategy.md`、`docs/evidence/`(5 份報告 + 2 份 CSV)、`docs/research/2026-07-06-tc4-stock-tick-1k-api-report.md`

---

## 1. 定位與階段

- **現在階段 = 策略調整與回測基建期**,尚未落地盤中。終局 = 盤中輔助手動下單,但本設計的交付物是「讓策略能被迭代驗證的基建」,不是落地決策工具。
- 第一個交付物(MVP)= **評分引擎 + 歷史 replay**:把 `strategy.md` Phase 2(鎖板品質)+ Phase 3(T+1 開盤判讀)的訊號實作成可測試的 code,對歷史事件重跑,重現 `docs/evidence/` 的關鍵數字。
- **策略還在迭代** ⇒ 所有策略門檻收在版本化 strategy config,調策略 = 改 config 重跑對照,不動引擎 code。
- 通用框架原則(CLAUDE.md §0a):分點集合(watchlist)是可替換輸入,只影響事件標記與報表分組,**不進評分邏輯** — 引擎訊號全部身分無關。

### MVP 明確不做

- Phase 1 盤前縮池(FinMind 日線篩選)— 後補
- 攻擊手法辨識(burst / 掃單 / 499 拆單偵測)— 後補
- T+1 決策樹輸出(avoid_chase / short_window …)— 策略穩定後再上,MVP 停在「結構化訊號 + 各 regime 歷史統計」
- 加權綜合分數 — 資料只支持分桶條件表,發明權重 = 過擬合
- Portfolio 層(同日多檔取捨、資金分配)
- 盤中 live 餵食器(TC4 增量輪詢 → `feed()`)— 引擎介面已為此設計,實作後補

### 硬限制(提前死心清單)

- **五檔委買賣深度不可得**:TC4 tick 只有成交當下一檔 Bid/Ask,歷史資料無五檔。依賴「掛牆厚度 / 漲停牆委買量」的策略假設**不可回測**。
- TC4 REALTIME push 目前壞(`invalid Date Time Format`),盤中模式將來走增量輪詢(秒級延遲),不影響本 MVP。
- 分點歸屬 T+1 21:00 才揭露:「虎局」標記永遠是事後標記,盤中身分判定天花板 2–2.8x lift(strategy.md §4),本工具不試圖突破它。

---

## 2. 架構

方案 B:**事件驅動串流引擎**。引擎逐 bar / 逐 tick 餵入、隨時可查詢當前評分;replay 與將來的盤中輪詢共用同一套引擎,無 lookahead 是結構保證(引擎在時刻 t 還沒看到 t+1 的資料),不是靠紀律。

```
copycat/                      # Python 3.13 package(repo root,pyproject.toml)
├── data/                     # 資料層
│   ├── models.py             #   Bar1K / Tick / DailyRow 標準模型(台北時間、型別化)
│   ├── store.py              #   本機 JSONL 資料庫(data/ 目錄,git-ignore;無 DB,沿專案慣例)
│   └── import_neigui.py      #   一次性匯入器:neigui 種子資料 → 標準格式
├── engine/                   # 評分引擎(核心,零 IO 依賴、純同步)
│   ├── day_state.py          #   每檔股票的日內狀態機:feed(bar) / feed(tick)
│   ├── lock_quality.py       #   Phase 2 鎖板品質訊號
│   └── t1_open.py            #   Phase 3 T+1 開盤訊號(吃 EventContext + T+1 資料)
├── strategy_config.py        # 版本化策略參數(門檻/分桶切點),JSON 檔載入
├── watchlist.py              # 可替換分點集合(JSON:broker_id + 名稱 + 角色標籤)
├── replay/
│   ├── runner.py             #   事件清單 → 按時序餵引擎 → 收集輸出
│   └── report.py             #   per-event 明細 + 彙總統計表 + 兩份 run 並排對照
└── cli.py                    # python -m copycat <import|replay|validate|compare>
```

關鍵邊界:

1. **engine 零 IO**:唯一入口 `feed()`(時間戳倒流 raise),任何時刻可查詢訊號。不知道資料來自 replay 或盤中。
2. **watchlist 不進評分**:換一組分點 = 換 JSON 重跑,零 code 改動。
3. **T 日 → T+1 用 `EventContext` 顯式傳遞**(前日漲停價、一價到底、連板數、鎖板品質訊號、日線輔助特徵),不靠全域狀態。
4. **strategy config 是策略迭代的介面**:§4 訊號表中所有門檻(早鎖 <10:00、暴力拉 ≥6%、排隊消耗 ≥40%、gap 六桶切點、競價 tell 三桶切點…)都是 config 欄位,附預設值 = strategy.md 當前假設。

## 3. 資料流

```
[一次性] neigui 種子資料(C:\side-project\neigui\backend\data\research\five-tigers\,1.24 GB)
    → python -m copycat import-neigui --src <path>
    → data/tc4/{1k,ticks}/<stock_id>/<date>.jsonl     (標準格式)
    → data/daily/…                                     (日線價格 + 融資券/當沖比等輔助特徵)
    → data/events/five_tigers.csv                      (事件清單,含 cohort 欄:tiger / control)
    → data/manifest.json                               (缺漏 stock-day 清單,已知 12 個停牌)

[每次回測] python -m copycat replay --events … --watchlist … --config strategy-v1.json
    → 每事件:T 日資料餵 DayState → 鎖板品質訊號
    →         T+1 日資料餵(帶 EventContext)→ T+1 開盤訊號
    → out/replay-<ts>/events.jsonl + summary.md(彙總表,cohort 分組對照)

[驗證]   python -m copycat validate      # 對照 evidence golden 數字,列差異
[實驗]   python -m copycat compare A B   # 兩份 replay 輸出並排(調 config 前後)
```

- TC4 陷阱(UTC→台北、`FilledTime` 無前導零、`TradeVolume` 歷史日恆 0、試撮期 Volume=0)**全部在匯入階段清洗**,引擎只看乾淨資料。
- **對照組一級支援**:事件清單帶 `cohort` 欄,彙總表自動分組 — 指紋是對比出來的。
- 日線輔助特徵(融資券、當沖比;FinMind 可補新資料)掛在 `EventContext`,策略迭代加欄不動引擎。

## 4. 訊號定義

原則:每個訊號直接對應 evidence 已驗證的量;輸出「結構化訊號 + 規則分級」,無黑箱總分。門檻值以下皆為 config 預設值。

### 4a. 前置定義(tick 判定,1K 輔助)

- **漲停價** = 前收 ×1.10 依 tick 檔位進位(前收由日線資料帶入)
- **鎖死** = 某 tick 起成交價 = 漲停價,延續到收盤或下一次打開
- **打開** = 鎖死後出現成交價 < 漲停價;段數 = 打開次數
- **首鎖時刻** = 第一段鎖死區間起點

### 4b. Phase 2 — 鎖板品質(T 日)

| 訊號 | 計算式 | 依據(evidence) |
|---|---|---|
| `lock_time_bucket` | 首鎖時刻五桶:<09:05 / –10:00 / –12:00 / –13:00 / 13:00+ | med gap +7.4% → +0.6% 單調遞減 |
| `open_count` | 打開段數 | ≥6 次 → 續鎖 0% |
| `violent_pull` | 首鎖前 10 分鐘推升 ≥6% | gap +6.2% 但續鎖僅 3.3% |
| `queue_consumption` | 鎖死後量 ÷ 全日量;≥40% / 15–40% / <15% | ≥40% → gap +6.0%;<15% → 續鎖 0% |
| `one_price` | 全日 high == low | 續鎖條件表核心項 |
| `board_streak` | 連板數(日線歷史) | 第 1 板 × 漲停開 × 一價到底 → 續鎖 33.3% |
| `tier` | `strong` = 早鎖(<10:00)∧ 非暴力拉 ∧ 排隊消耗 ≥40% ∧ 打開 ≤1;`weak` = 尾盤鎖 ∨ violent_pull ∨ 死鎖無量 ∨ 打開 ≥6;其餘 `neutral` | strategy.md §3c 判讀原則 |

`queue_consumption` 分母「全日量」收盤後才知 ⇒ 盤中版用「截至目前量」滾動計算;replay 同時輸出逐時點盤中視角與收盤定稿兩版。

### 4c. Phase 3 — T+1 開盤(吃 EventContext + T+1 頭 15 分鐘)

**無 lookahead 修正**:evidence 研究用「競價量 ÷ 全日量」,全日量在 09:00:06 未知 ⇒ 盤中版一律用 **競價張數 ÷ 20 日均量**。replay 兩版都輸出:研究版對照 golden,盤中版是新產出。

| 訊號 | 計算式 | 依據 |
|---|---|---|
| `gap_bucket` | 開盤 vs 前日漲停收盤;<0 / 0–1 / 1–3 / 3–7 / 7–9.5 / ≥9.5% | 各桶期望值/劇本分佈引用 strategy.md §5b(硬編為參考表資料附在輸出) |
| `auction_tell` | 09:00:06 首筆競價張數 ÷ 20 日均量;<3% / 3–8% / ≥8% | ≥8% = 真需求 |
| `inner_ratio_15m` | 前 15 分鐘貼 Bid 成交量占比(競價/試撮 mid 不計) | >50% = 出貨確認;<20% ∧ 漲停開 = roll 局 |
| `early_high` | 開盤後高點時刻與回落幅度(滾動更新) | 5–8 分鐘高點 = 出貨帶 |

輸出附各 regime 歷史統計(如「E[開→收] −3.47%,n=45」),可被人審視。

## 5. 錯誤處理

- 匯入:缺 stock-day 寫 manifest;replay 跳過並在報表**明列缺漏**(不靜默)。資料異常(盤外時間戳、價格 ≤0)匯入時 fail loud。
- 引擎:`feed()` 時間戳倒流 raise;引擎內不 catch 不懂的錯誤(全域鐵則 E)。
- 試撮期 Volume=0 bars 匯入時標記:量能統計排除、13:30 收盤競價根照算。

## 6. 測試與驗收

TDD(紅先行)。ruff line-length 100 + pyright basic + pytest 從第一天。

- **單元**:每訊號用手工構造 bar/tick 序列測邊界(鎖死→打開→回鎖、暴力拉恰 6%、桶邊界)。
- **無 lookahead 結構測試**:餵至 t 查詢的已定稿訊號,繼續餵資料後不得改變。
- **Characterization gate**(replay 全量歷史事件對照 golden):

| SC | 對照目標 | 容忍度 |
|---|---|---|
| SC-1 | 事件覆蓋率 ≥99%,缺漏明列 | — |
| SC-2 | 鎖板時間五桶 × med gap / 續鎖率(intraday_playbook §2d) | 各桶 n 差 ≤5%、med gap 差 ≤0.5pp |
| SC-3 | 暴力拉板 vs 開盤自然鎖對比(6.2%/3.3% vs 18.3%) | 同上 |
| SC-4 | 排隊消耗三桶 | 同上 |
| SC-5 | T+1 gap 六桶佔比 + E[開→收](open_gap_definition §2–3) | 同上 |
| SC-6 | 競價 tell 研究版重現 evidence;盤中版(÷20日均量)另列新表 | 研究版對 golden |
| SC-7 | 換 watchlist config 重跑,零 code 改動 | — |
| SC-8 | 無 lookahead 結構測試通過 | — |

不達容忍度 = 查根因(鎖死定義、清洗差異),**不是放寬容忍度**。

## 7. 開放問題(實作時驗證)

1. neigui ticks/ 目錄的實際檔案格式與完整度(匯入器實作時盤點)。
2. 「鎖死」定義與 neigui 研究腳本(`analyze_intraday.py`)是否完全一致 — SC-2 不達標時第一個查這裡。
3. 20 日均量的計算窗與除權息調整 — 用日線資料實作時定案。

## 8. 隨附變更

- CLAUDE.md §0a 補「目前階段」段(內容已於 brainstorm 核可,與本文件 §1 一致)。
- repo `git init` + 首次 commit(docs + CLAUDE.md;此前目錄非 git repo)。
