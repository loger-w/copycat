# Round 3 改動規格書:T+1 fade 停損語意重驗(/mod change-spec)

上游(本檔不得與之衝突;衝突以上游為準):
- `docs/superpowers/specs/2026-07-15-fade-round3-prereg-draft.md`(**已凍結**,結構與候選不得動)
- `docs/strategy-decisions.md` §1 Round 2 複驗結果 + 2026-07-15 定案
- `docs/evidence/fade_round3_sec0_sensitivity_2026-07-15.md`(§0 已補跑:誠實區間
  +0.13%~+0.85%;停損保費預算上限 0.68pp/筆;round 2 舊語意花 1.08pp)
- `docs/evidence/gap_anatomy_2026-07-15.md`(貼板線 7.5% 依據)
- Phase 1 現況表:`.claude/mod/fade-round-3/current-state.md`

引用鐵律:noguard +0.85% 必附上界警語(23% 再鎖單零懲罰;誠實區間 +0.13~+0.85%,
§0 表 1 定案值)。

---

## 1. 成功條件(可驗收)

- **SC-1(Q1 池子有肉,複核)**:noguard 三池複驗判定式維持 round 2 語意
  (tiger 淨 EV>0 且日聚類 z 單尾 p<0.05;tiger−對照 ≥0.3pp 且洗牌 p<0.05),
  in-window 已 PASS,forward 樣本到位後同式複核。**單位**:EV = 每筆平均淨報酬率
  (扣 0.196% 成本);**量法**:`fade-diagnose` CLI(noguard config)。
- **SC-2(Q2 吃法可行)**:新停損語意(§3)下 tiger 池底倉臂合併淨 EV>0
  (日聚類 z 單尾 p<0.05),且至少一個劇本格子過 D5(壓測後 ≥1% + n≥80 +
  ≥3/4 段正且合計正)。**量法**:`fade-cells` CLI round 3 config。
  **證據強度註記(R4)**:本輪 in-window 判定 = **候選**,且 b/D/r 與判定同源
  (§5 定值宇宙 = 判定宇宙,有循環擬合成分,Q2 候選的證據強度弱於 Q1);
  報告主結論強制寫「Q2:候選 PASS/FAIL(in-window,參數同源)」,不得裸寫
  PASS/FAIL。**forward 正式判定門檻(事先寫死)**:forward 段累積 ≥20 個交易日
  且底倉 tiger 合併 n≥80 才啟動 forward 判定;門檻未到 = 「forward 未到判定量」。
- **SC-3(判定拆兩題)**:報告輸出 Q1/Q2 各自 PASS/FAIL,不再合併單一布林。
- **SC-4(保險精算表)**:報告強制附 — 每停損機制(結構停損/硬線/災難)觸發率、
  每次觸發平均成本(pnl)、觸發後收盤鎖死比例(砍對)vs 未鎖(砍錯)。
- **SC-5(宇宙紀律)**:貼板線 gap ≥7.5% 排除方向臂與底倉(僅 cell_b 可進,必掛硬線);
  「排除出宇宙」僅限進場當下 entry 已在硬線區內(既有 `excluded_guard_at_entry`,
  = prereg「開盤時 headroom 不足」);結構停損被硬線封頂(結構高×(1+b) ≥ 硬線位)
  之事件**保留**(min() 語意,實際停損 = 硬線)並計數 `b_capped_by_hardline`
  進報告(R1:cell_b 依觸發定義幾乎 100% 被封頂,b 對 cell_b 實際不生效,
  報告必須明示)。
- **SC-6(自由度)**:搜索型變體總數 ≤8(b×2 為停損 2 變體 × cells{a×1, b×1, c×2};
  底倉 6 格與基準線為統計非搜索)。
- **SC-7(考場切分)**:cells 與 diagnose 報告皆分 in-window(<2026-07-11,候選)
  與 forward(≥2026-07-11,正式)兩段輸出;forward 無資料時明確標示
  「forward 樣本 0,僅候選」。**D5 / Q2 / 底倉格開放判定一律以 in-window 段計
  (候選);forward 段僅複核輸出**(R9),直到 SC-2 的 forward 門檻達成。
- **gates**:pytest / ruff / pyright / `copycat validate` 全 PASS。

## 2. 不能破壞的既有行為白名單(比新行為更重要)

1. `TRADEABLE_STATUSES` 單一定義不變;`excluded_*` 永不入統計;新增出場 status
   只改 fade_simulate 一處。
2. 舊 config(round 1/2 JSON)**判定數值**完全不變(二輪 P2-6 措辭):新欄位
   一律預設 `None`/停用;`configs/fade_uc_round2.json` 重跑統計/判定結果與
   round 2 一致;報告新增 forward 節屬格式加節不算破壞(hash 檢查:新欄位入
   `_SIM_FIELDS` 會改 hash → outcome cache 正確失效,屬預期)。
3. 鎖死凍結語意(R15):鎖死 bar 內任何停損(含新結構停損/災難回落)不觸發;
   全日鎖 → lock_penalty 語意結算。
4. 衝突取最差(最高回補價)語意不變,新停損機制併入同一 worst-of 集合。
5. `fade-diagnose` 判定式(Q1)數值與 round 2 可重現(§0 表 1 已對帳)。
6. `fade-search` / GA pipeline(fade_pipeline / fade_optimize)行為不動
   (round 3 無搜索項;它們消費 fade_simulate,新參數必須是加法性、預設不啟用)。
7. 悲觀成交慣例:進場扣一檔、強制出場 `max(level, close)`、壓測
   `stress_guard_fill_high` 疊加語意照舊適用於新停損。
8. 既有測試(321)全綠;紅的只允許出現在 spec 標記「該紅」清單(見 §6)。

## 3. 新停損語意(prereg §2 主案,操作化定義)

### 3a. 主停損 = 結構前高 + 緩衝 b ∧ 硬線

- **結構高(per 劇本,進場時已知)**:cell_a = 進場前盤中高點(觸發演算法的
  running high);cell_b = 衝關高點(approach_high);cell_c = 反拉高點;
  底倉 = T+1 開盤後 running high(隨盤 ratchet,見 3c)。
- **cell_a/b/c(靜態)**:沿用既有 `fixed_stop_level` 機制,
  `fixed_stop_level = 結構高 × (1 + b)`。觸發/成交語意與 round 2 cell_b 完全同軌
  (`bar.high ≥ level → max(level, forced_ref)`)。
- **硬線**:`guard_limit_dist = 0.01`(距漲停 1% ≈ 漲 8.9%,prereg 稱「漲 9%」),
  沿用既有 guard 機制(進場已在區內 → `excluded_guard_at_entry`)。
- **兩線相撞(R1 修正;二輪 R1 再修)**:`結構高 × (1 + b) ≥ guard_level` 時
  主停損被硬線封頂 → **事件保留**,cells 層傳 `fixed_stop_level = None`
  (硬線由 guard 單獨實現,成交/歸因不被較高的 fixed_stop 污染 —— 引擎
  worst-of 取 max,若同時傳兩線會以較高的 fixed_stop 成交,違反 min() 語意),
  並計數 `b_capped_by_hardline` 進報告。「排除出宇宙」僅限進場當下 entry
  已在 guard 區(既有 `excluded_guard_at_entry`)。
- b 候選 ≤2 值,由 §5 預載程序定;必須 > 0.005(cell_b round 2 值已證太緊)。

### 3b. 災難停損 = 進場後最高價回落式(取代 entry×(1+4%))

Round 2 根因:固定虧損式災難停損落在例行拉幅(3.8~4.1%)中心 → 系統性買回在頂點。
回落式改為「深度武裝 + 回落確認」:不在衝高當下出場,等高點確認失敗、在回落中出場;
不回落的直衝局由硬線接手。

- **武裝條件**:進場後 running_high ≥ entry × (1 + D)(D = 災難深度,超出例行
  拉幅上緣,由 §5 程序定;round 2 的 4% 落在拉幅中心,新值必須明顯在其上)。
- **觸發(R5 修正:與 ratchet 同規,防 intra-bar lookahead)**:武裝判定與
  level 一律用 **prev running_high(不含當前 bar)**;當前 bar 只能更新錨
  (武裝),觸發自下一 bar 起。武裝後,bar.low ≤ level
  (level = prev_running_high × (1 − r))→ 出場。成交 = level(限價語意,
  同 S5 target fill)。
- **鎖死凍結 bar:更新錨(running_high 照舊更新)但不觸發**(明文 + 測試;R5)。
- **凍結 bar 不觸發**(白名單 3);與其他同 bar 出場衝突時併入 worst-of(白名單 4)。
- 引擎欄位:`disaster_arm_x: float | None` + `disaster_retrace_r: float | None`
  (兩者皆設才啟用;與舊 `disaster_x` 互斥,config 同時設非 None → `load_fade_config`
  fail-fast)。舊 `disaster_x` 欄位保留(backward compat,round 3 config 不用)。
- 自由度:災難錨 ×1(單一 (D, r) 組,不做 grid)。

### 3c. 底倉臂(ratchet 結構停損)

- 進場 = T+1 開盤(entry_price_override = bars[0].open,同 diagnose 慣例)。
- 結構高 = 進場後 running high(**用前一 bar 為止的 running high** 判定當前 bar,
  防 intra-bar 自觸發):bar.high ≥ prev_running_high × (1 + b) → 出場
  `max(level, forced_ref)`。第一根 post bar 的 prev_running_high = trig bar high。
- 語意:慢磨上行不觸發(每根新高 < b)→ 由災難(3b)與硬線接手;跳升突破 → 觸發。
- 引擎介面:`ratchet_stop_b` = **per-call kwarg**(同 `fixed_stop_level` 型式;
  不入 cfg、不入 `_SIM_FIELDS`,二輪 P2-1 定案),預設 None = 不啟用。

## 4. 劇本格子與宇宙(prereg §3/§4)

- **主宇宙(方向臂 + 底倉 + 基準線)**:gap 帶上限 0.095 → **0.075**(貼板線)。
- **cell_b 例外**:獵場含 7.5~9.5% 區(獨立宇宙構建,gap 1%~9.5%),必掛硬線。
- 低開宇宙(cell_c):gap −9.5%~1%,不變。
- cell_a:觸發不變(inner 0.45/0.55 兩變體?— **否**,prereg 自由度表 cells 為
  a×1:主變體取 round 2 樣本較穩者 inner_0.45;0.55 不跑)〔備註:round 2 兩變體
  全 FAIL 是風控語意問題,觸發參數不重選;取 0.45 = 較寬鬆、樣本較大者,
  事先在此寫死〕。停損 = 3a + 3b + 硬線。
- cell_b:approach_dist 取 round 2 的 0.02/0.03 之 **0.03**(樣本較大;a×1 同理
  cells 預算 b×1);buffer 改用 b(>0.005);停損 = 衝關高點×(1+b) ∧ 硬線 + 災難。
- cell_c:**升正式入 D5**;rally 0.05 主變體、0.03 對照(prereg 明文 ×2);
  停損 = 反拉高點×(1+b) ∧ 硬線 + 災難。
- 底倉臂:分點數(2+/1)× gap 桶(1~3 / 3~5.5 / 5.5~7.5)6 格 EV 表
  (統計非搜索);開放門檻 = 格 n≥80 且日聚類 z 顯著 >0;Q2 池級判定用
  tiger 合併(全格彙總)。停損 = 3c ratchet + 3b 災難 + 硬線。
- 基準線:第 7 分鐘無條件空,同宇宙同風控(= 底倉停損組,ratchet 錨起算點 =
  進場 bar),不變量尺。
- 變體帳(SC-6):停損 b×2 × cells(a×1 + b×1 + c×2)= 8 個搜索型變體;
  底倉 6 格 × b×2 = 統計表(非搜索,不入帳);災難 (D,r)×1 全局共用。

## 5. 殘餘自由度預載定值程序(先宣告後跑;跑完填值即凍結)

**程序在此節先寫死,數字未看**。資料 = in-window(t1 ≤ 2026-07-10)主 UC 宇宙
(gap 1~7.5%,可先賣後買、非處置),僅設計輸入(forward 不碰)。
腳本 = scratchpad 一次性(比照 gap anatomy),結果表附錄於本檔 §5a。

- **b(結構停損緩衝,2 值)**:「假突破 overshoot 統計」——對每個 session 取
  cell_a 語意結構高 H(開盤起 rally ≥1% 後首次收盤回落 ≥0.8% 當下的 running high;
  與 find_cell_a_entry 同演算法、不含內盤比/headroom 條件,取覆蓋最大)。
  事後 max_after = 進場 bar 之後全日最高。**假突破事件** = max_after > H 且
  收盤 < H 且未收盤鎖死。overshoot = max_after/H − 1。
  **b1 = 假突破 overshoot 的 p75、b2 = p90**,各四捨五入至 0.25% 步進,
  下限 0.0075(必須 > 0.005)。
- **D(災難武裝深度,1 值)**:同宇宙每 session 開盤後最大不利波幅
  excursion = max_high/open − 1 的分佈(未收盤鎖死子集,= 災難停損的服務對象;
  鎖死局由硬線/lock_penalty 語意處理)。**D = p90**,四捨五入至 0.5% 步進;
  若 ≤ 0.045(拉幅中心上緣)則取 0.05 下限——確保在例行拉幅之上。
- **r(災難回落確認,1 值)**:excursion ≥ D 且**收盤鎖死**的 session
  (真災難局),取「鎖死前自 running high 最大回落幅度」分佈之 **中位數**
  (= 對半數真災難局能在 shakeout 中先出場),四捨五入至 0.25% 步進,
  下限 0.005、上限 0.02(超界取界)。
- 樣本量 gate:任一分佈 n<30 → 該值退回保守預設(b=0.0075/0.0125、D=0.05、
  r=0.01)並在報告註明「統計樣本不足,取預設」。

### 5a. 定值結果(2026-07-15 回填;**已凍結**)

腳本 = scratchpad `preload_stop_values.py`;宇宙 = 主 UC in-window
(included 4,086、main-UC n=1,621)。三分佈樣本量全過 n≥30 gate。

| 分佈 | n | 關鍵分位 | 定值 |
|---|---:|---|---|
| 假突破 overshoot(context 1,180 → 突破 767 → 假突破 368) | 368 | p50 1.38% / p75 2.51% / p90 3.68% / p95 4.43% | **b1 = 0.0250、b2 = 0.0375** |
| 未鎖死局最大不利波幅 | 1,276 | p50 2.58% / p75 4.52% / p90 6.25% | **D = 0.060**(p90 = 0.0625 落 0.5% 步進中點,banker's → 0.060;取較低值 = 較早武裝,tie-break 事先未指明,在此註記) |
| 真災難局(exc ≥ D 且收盤鎖死)鎖前 max retrace | 121 | p25 3.09% / p50 3.55% / p75 4.55% | **r = 0.020**(上限生效;中位 shakeout 3.55% > 2% → 半數以上真災難局能在 shakeout 完成前出場) |

佐證讀法:round 2 cell_b buffer 0.005 對照假突破 overshoot p50 1.38% —— 遠低於
中位假突破,幾乎每次假突破都會掃到,「太緊」有了量化解釋。b1(p75)/b2(p90)
分別容忍 3/4 與 9/10 的假突破。

**R8(D tie-break 敏感度義務)**:D=0.0625 落 0.5% 步進中點、banker's → 0.060
屬事後 tie-break;正式跑完後必須補一列 D=0.065 敏感度(config 覆寫重跑,
報告限制節收錄,非判定用),證明結論對 tie-break 不敏感。

**校準錨 vs 套用錨(二輪 P2-2,報告限制節必註)**:D 用「開盤錨」分佈
(max_high/open−1)校準,套用時 cells a/b/c 為盤中進場、武裝錨 = entry×(1+D)
——entry 低於開盤時武裝點相對開盤更低、災難更早武裝(保守向);屬已凍結取捨,
不改值,報告限制節註記。

## 6. Backward compat / migration

- 新 config 欄位全部預設停用(`None`);未知欄位 fail-fast 已有。
- `disaster_arm_x`/`disaster_retrace_r` 加入 `_SIM_FIELDS`(hash 失效);
  `ratchet_stop_b` 為 per-call kwarg 不入 cfg(二輪 P2-1);tuple 新欄位入
  `_TUPLE_KEYS`;round 2 config 重跑不受影響(欄位缺席 = None)。
- cells 報告格式新增欄(精算表/Q2/相撞計數):`uc_cells_*.md` 是產物非契約,
  無下游解析器(僅人讀),可加欄。
- 無資料 migration;`copycat validate` golden 不涉 fade(replay 域),不受影響。
- 可逆性:全部改動在 config 開關之後,關閉 = round 2 行為。

## 7. Out of scope(prereg §6 停車場 + 本輪明確不做)

- 時間停損 / T+2 續跌 / 被倒追空臂 / 加速逼近 guard / D2 標籤 ROI 對照。
- fade-search(GA)重跑;TP 網格;次案 B(headroom 比例式)——僅主案全滅時
  才啟用評估(屆時另立 spec 節)。
- tick 級競價 tell(§3 #7 維持不得使用)。
- 盤前預測日誌工具化(上場橋接,round 3 交付後另案)。

## 8. Forward 資料前置(SC-7 依賴;開工事實)

events.csv 目前至 2026-07-09,**forward(t1 ≥2026-07-11)樣本 = 0**。
round 3 判定的 forward 段需要回補鏈:scan-events → backfill-tc4(需 Touchance
app 常駐)→ backfill-daytrade → backfill-brokers → label-events。本輪交付
= 引擎 + in-window 候選判定 + forward 重跑能力;回補鏈執行為收尾步驟
(TC4 不可用時明確回報,不擋 in-window 交付)。

## 9. Diff 級規格(Phase 3;三類標記 🔴行為 / 🟢新功能 / 🔵重構)

規模 = L(≥5 檔)。實作順序 🔴 → 🟢(本 spec 無 🔵 項,二輪 P2-8;
型別簽名改動〔find_cell_a/c〕連同其 gated 消費屬 🔴 先行)。

### 9.1 `copycat/backtest/fade_config.py` 🟢

- 新欄位(全部預設停用;`_SIM_FIELDS` 加入標註 ✱ 者):
  - `disaster_arm_x: float | None = None` ✱(災難武裝深度 D)
  - `disaster_retrace_r: float | None = None` ✱(回落確認 r)
  - `struct_stop_buffers: tuple[float, ...] = ()`(b 候選;cells 層消費,非 sim 欄)
  - `cell_b_gap_max: float | None = None`(None = 沿 `fade_gap_max`;round 3 = 0.095)
  - `base_arm: bool = False`(底倉臂開關)
  - `base_arm_gap_edges: tuple[float, ...] = (0.01, 0.03, 0.055, 0.075)`(3 桶邊界)
  - `forward_start: str = "2026-07-11"`(SC-7 切分日)
- `_TUPLE_KEYS` += `struct_stop_buffers`, `base_arm_gap_edges`。
- `load_fade_config` 追加驗證:`disaster_x` 與 `disaster_arm_x`/`disaster_retrace_r`
  互斥(同時非 None → ValueError);arm/retrace 必須同設或同缺。
- 測試:欄位預設值、round 3 config 載入、互斥驗證、`fade_sim_config_hash` 對
  ✱ 欄位敏感(新增)。既有 config 測試不該紅。

### 9.2 `copycat/backtest/fade_simulate.py` 🟢(加法性引擎擴充;預設關 = 行為不變)

- `FadeTradeOutcome` 加欄位 `exit_reason: str | None = None`(精算表歸因:
  `hardline` / `struct_fixed` / `struct_ratchet` / `disaster_retrace` / 舊災難
  `disaster_x`;非強制出場 = None)。frozen dataclass 加預設欄位,既有建構不動。
- `_simulate_core` / `simulate_fade_sample` 新 kwarg `ratchet_stop_b: float | None = None`:
  每 bar 用 **prev running_high**(不含當前 bar)判 `b.high ≥ prev_high × (1+b)` →
  併入 forced_fills(`max(level, forced_ref)`,吃 `stress_guard_fill_high`)。
- 回落式災難(cfg 兩欄皆設才啟用;R5:全程用 **prev running_high**,不含當前
  bar,當前 bar 只更新錨):prev_high ≥ entry×(1+D) 武裝;武裝後
  `b.low ≤ level`(level = prev_high×(1−r))→ `disaster_fill = level`
  (限價語意,同 S5,不吃 stress);併入 worst-of 衝突集合;單獨觸發時
  status = `guard_exit`、exit_reason = `disaster_retrace`。鎖死凍結 bar
  更新錨但不觸發。
- 鎖死凍結 bar 一律不觸發(沿 R15);**不新增 status**(`TRADEABLE_STATUSES` 不動,
  白名單 1/3/4 全保)。
- 歸因規則(二輪 R1):以 **worst 成交價所屬機制**歸因;多機制同價才用優先序
  hardline > struct > disaster(寫死,測試鎖定)。
- 引擎層 fail-fast(二輪 P2-5):`_simulate_core` 開頭驗證 `disaster_x` 與
  `disaster_arm_x`/`disaster_retrace_r` 不得同時啟用(擋 `dataclasses.replace`
  繞過 config 驗證的路徑)。
- 測試(新):ratchet 慢磨不觸發 / 跳升觸發 / prev-high 語意;災難未武裝不觸發、
  同 bar 衝高不觸發(prev-high 語意,下一 bar 起)、武裝+回落出場於 level、
  凍結 bar 更新錨但不觸發、與 stop 同 bar 取最差;全 None 等價舊行為
  (擴充既有等價測試)。**既有 321 綠測試零紅**(全為預設關閉路徑)。

### 9.3 `copycat/backtest/fade_cells.py` 🔴🟢(round 3 主戰場)

**路徑 gate(R2 裁決,方案 a)**:round 3 行為全部 gate 在
`cfg.struct_stop_buffers` 非空。**空 tuple(所有舊 config / default)= 完整
round 2 形狀**:cell_b `guard_limit_dist=None` + `cell_b_stop_buffer`、cell_c
`observation=True`、變體 key 舊格式、無底倉/精算/段切分。白名單 2 與 §6
可逆性因此成立;既有 evaluate 層測試(key `cell_a:inner_0.45`、
`len(cells)==6`、observation flag、D5、segments)**全數不該紅**。

- 🔴 `find_cell_a_entry` / `find_cell_c_entry` 回傳型別 `int | None` →
  `tuple[int, float] | None`(加回結構高 H;caller 僅 `_simulate_cell_trades`
  一處 + 測試兩處,見 §9.6)。
- 🟢(gated)cell_b round 3 路徑:掛硬線(不再 replace guard=None);
  fixed_stop = approach_high × (1 + b),b ∈ struct_stop_buffers。
- 🟢(gated)cell_c round 3 路徑:`observation=False` 入 D5;rally 0.05 主 /
  0.03 對照。
- 🟢(gated)停損變體迴圈:每 cell × b → fixed_stop = 結構高×(1+b)
  (cell_a = 進場 context high;cell_b = approach_high;cell_c = 反拉高點);
  變體命名 `cell:variant:b{b}`(帳面 8 個搜索型變體 = SC-6)。
- 🟢(gated)`b_capped_by_hardline` 計數(R1;二輪 R1 再修):fixed_stop ≥
  guard_level(t1_limit×(1−guard_limit_dist))的事件**照常模擬但傳
  `fixed_stop_level = None`**(硬線由 guard 單獨實現 = min() 語意),
  per cell×b 計數入報告。
- 🟢(gated)cell_b 獨立宇宙(R7):`run_cells` 以
  `dataclasses.replace(cfg, fade_gap_max=cell_b_gap_max)` 建第三宇宙
  (gap 1%~9.5%);`evaluate_cells_from_universe` 簽名擴充為收
  `cellb_universe`(round 2 路徑傳 main 宇宙 = 行為不變);
  `universe_counts_cellb` 入 JSON;cell_b 基準線 = 同 cell_b 宇宙另跑
  m7 基準線(vs_baseline 對此比較)。
- 🟢(gated)底倉臂(base_arm=True):主宇宙 UC 樣本,trig_idx=0、
  entry_price_override=open、ratchet_stop_b=b;6 格 = 分點數(2+/1)×
  gap 桶(base_arm_gap_edges);每格 n / 淨EV / 日聚類 z(import
  `cluster_se`)/ 開放判定(n≥80 ∧ z 單尾 p<`diagnose_p_threshold`,R9);
  tiger 合併(全格)輸出 Q2 池級判定(EV>0 ∧ z 單尾 p<`diagnose_p_threshold`,
  單一參數源,二輪 P2-4)。**Q2 判定以 b1(0.025,主變體)計**,b2 為敏感度列
  (事先寫死)。**Q2 z 檢定分 in-window / forward 兩段各自計算並入 JSON 判定欄
  (二輪 R2)**:in-window 段 = 本輪候選判定;forward 段機制同式,
  門檻(SC-2)未到時僅列數不判定。分點數 2+/1 操作化 = `assign_pool` 語意
  (tiger_2plus / tiger_1,二輪 P2-3)。
- 🟢(gated)基準線:同宇宙同風控(ratchet b + 災難 + 硬線),per b 變體各一條。
- 🟢(gated)保險精算表(SC-4):per cell×b:各 exit_reason 觸發率、平均 pnl、
  觸發後收盤鎖死(砍對)vs 未鎖(砍錯)比例;鎖死判定 =
  `bars[-1].low ≥ limit_up_price(sample.limit) − cfg.limit_eps`(R10,
  與引擎同源)。
- 🟢(gated)SC-7 切分:統計表分 in-window(< forward_start)/ forward(≥)
  兩段;forward n=0 時印「forward 樣本 0,僅候選」。
- 🟢(gated)報告 `write_cells_report`:新增精算表 / Q2 節(候選字樣,SC-2)/
  b_capped 計數 / 段切分;round 2 路徑輸出格式不變。
- 測試:該紅僅 §9.6 兩條型別斷言;新測試:gate 行為(空 tuple = round 2 形狀)、
  b_capped 計數、底倉格分派(分點數/桶邊界)、精算表歸因與鎖死判定、Q2 判定、
  段切分、cell_b 第三宇宙。

### 9.4 `copycat/backtest/fade_diagnose.py` 🟢

- 報告標題判定節加「Q1(池子有肉)」字樣(SC-3;既有判定式數值路徑零改動)。
- 🟢 SC-7 / R3 / 二輪 R2:`diagnose_pool_fade` 增加 forward 段輸出——樣本依
  `cfg.forward_start` 切兩段,per-pool 統計(base config)各出一表;
  主判定式仍以全共同期間計(round 2 重現性)。**forward 段同時跑完整判定式
  (i)(ii) 含日聚類 z 與分層洗牌**(機制現在就寫死、凍結於看 forward 數字前),
  輸出標「forward;門檻未到時僅列數不判定」(門檻 = SC-2:≥20 交易日)。
  n=0 時明示。實作 = 對日期過濾後的 samples_bars 重跑 `_pool_run` +
  既有判定函式(零新統計邏輯)。
- 測試:forward 切分(混合日期樣本 → 兩段 n 正確;forward 空 → n=0 標示;
  forward 段判定欄存在且標門檻狀態)。
- 白名單 2 對應改寫(二輪 P2-6):舊 config 重跑「判定數值不變」;報告
  新增 forward 節屬格式加節,不算行為破壞。

### 9.5 `configs/fade_uc_round3.json` 🟢(新檔;數值全部來自凍結文件)

```json
{
  "fee_discount": 0.84,
  "universe_daytrade_filter": true,
  "fade_gap_max": 0.075,
  "guard_limit_dist": 0.01,
  "disaster_arm_x": 0.06,
  "disaster_retrace_r": 0.02,
  "lock_penalty": 0.03,
  "struct_stop_buffers": [0.025, 0.0375],
  "cell_a_inner_thresholds": [0.45],
  "cell_b_approach_dists": [0.03],
  "cell_b_gap_max": 0.095,
  "cell_c_rally_pcts": [0.03, 0.05],
  "base_arm": true,
  "lock_penalty_grid": [0.03, 0.05, 0.07],
  "diagnose_perm_iters": 5000,
  "diagnose_perm_seed": 42,
  "diagnose_min_edge_pp": 0.003,
  "diagnose_p_threshold": 0.05,
  "cells_eval_segments": 4,
  "d5_min_ev": 0.01,
  "d5_min_n": 80,
  "d5_min_positive_segments": 3
}
```

(cell_a 觸發參數 pullback/headroom/window/min_rally 沿 default;
`cell_a_inner_thresholds` 單值 0.45、`cell_b_approach_dists` 單值 0.03 =
§4 事先寫死的收斂。)

### 9.6 既有測試紅名單(🔴 該紅;不在此列的紅 = 打到不該動的)

R2 方案 (a)(config gate)後,該紅收斂為**僅兩條回傳型別斷言**:

- `tests/backtest/test_fade_cells.py::test_cell_a_triggers_on_pullback_with_inner_gate`
  (行 68 `find_cell_a_entry(...) == 2` → 改斷言 idx 與 H 兩值)
- `tests/backtest/test_fade_cells.py::test_cell_c_triggers_on_rally_then_pullback`
  (行 139 `find_cell_c_entry(...) == 2` → 同上)

evaluate 層測試(`test_evaluate_filters_to_uc_pool_only` /
`test_evaluate_variant_count_and_observation_flag` /
`test_d5_pass_and_fail_by_config_thresholds` / `test_segments_split_by_calendar`)
走 default config(struct_stop_buffers=())= round 2 路徑,**不該紅**。
其他測試檔(test_fade_simulate / _round2 / test_fade_guard / test_fade_tp /
test_fade_phase_b / test_fade_pool_diagnose / config 測試)**一律不該紅**。

## 10. Prereg 對照節(R11:凍結文件內部矛盾 × 本 spec 單方裁決,供 user 事後可見)

| # | prereg 原文 | 矛盾/歧義 | spec 裁決 | 位置 |
|---|---|---|---|---|
| 1 | §1 Q2「新停損語意下 tiger 池淨 EV>0」 | 「tiger 池」未指明進場方式 | 操作化 = 底倉臂(開盤進場)全格 tiger 合併,b1 計 | §9.3 |
| 2 | §4 cell_a「內盤比門檻沿 0.45/0.55」vs 自由度預算「cells 4(a×1…)」 | 兩變體 vs 預算 1 變體矛盾 | 取 a×1 = inner_0.45(較寬鬆、樣本較大),0.55 不跑 | §4 |
| 3 | §2「排除出宇宙」vs min() 主停損公式 | 相撞事件排除 vs 硬線封頂保留 | 依 min() 語意保留 + `b_capped_by_hardline` 計數;排除僅限 entry 已在硬線區 | §3a(R1) |
| 4 | §2 災難「回落幅度值與 b 同程序定值」 | 「同程序」未指明分佈與統計量 | §5 宣告後跑:D = 未鎖死局 excursion p90、r = 真災難局鎖前 retrace 中位數(capped) | §5 |

裁決原則:凍結結構不動,矛盾取「自由度較小/較保守」一側;本節 = user 的
事後審核清單,任何一條不同意 → 該項重跑,不動其他。

self_review_head: a0f958bb8b097fed1a15e389363eda893f6fbe7c
