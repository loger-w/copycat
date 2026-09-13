# 訊號層三件顯示層小改(`mod/signal-context-trio`)— change spec

來源:`%TEMP%\copycat-handoff-2026-09-14-mod-signal-context.md`(09-14 user 拍板 + 深夜補記三個預設值);
數據 SoT = `Documents\copycat-trading-review\review-2026-09-09.md` §16 / §17 / §19(不重算、不重辯)。
本案疊 `/auto`:grilling / seams / tickets 一律採 handoff 預設推進,決策逐條標 `[auto-default]`(§3)。
影子期(spec #192,2026-09-08 起四週)**不改推播政策、不加硬條件、既有 jsonl 欄位語意不動**。

## 0. 現況 vs 目標

| 件 | 面向 | 現況 | 目標 |
|---|---|---|---|
| 1 CDP 列閘 | `cdp_cross` 事件 | 每檔都發(`notify=false`,rail 淡色列 + jsonl 列) | 只在該檔**前 5 個交易日累計報酬 ≥ +5%**(`close[-1] / close[-6] − 1`,研究 `own5` 同口徑)時產生;不合格的檔當日**零事件**(rail / jsonl 都沒有)。**圖上 CDP 五線照畫**(overlay 端點是另一條路,零改動) |
| 1 | 閘的資料源 | hub `_resolve_basis` 抓 5 根日 K 算 CDP 基準 | 同一趟日 K 多抓幾根(需 ≥ 6 根已完成 bar),閘不過 → 該檔基準餵 None(detector 既有語意「CDP 跳過、其他 kind 照常」),INFO 一行;歷史不足 6 根 = 不合格 |
| 2 放量離開 | 規則種類 | 爆量 `vol_burst` = 5 分窗量 ≥ 3× 當日至今每分鐘均量 | 新增 kind `vol_breakout`(「放量離開」,爆量家族的兄弟卡):價在 ±0.6% 帶內停留 ≥ 10 分,離帶那一分鐘的量 ≥ 4× 迴盪期每分鐘均量 → 發,`direction` = up / down;種子卡 `notify_discord=false`(rail 淡色列 + jsonl,不推播) |
| 2 | 規則檔 | `_cache_version` 4 | 5:v4→v5 append 「放量離開」種子卡(沿 v3→v4 掃單簇同形);回退手順文件化 |
| 3 大單筆數格 | 掃單簇 / 政策列 | 掃單簇列 `detail={n30,levels,qty,up_pct}`;政策列 `sweep` 鏡像 | 掃單簇列 `detail.big_lots_120s`、政策列頂層 `big_lots_120s`(= 發訊時刻往前 120 s 內「大單敲檔」單筆命中數);rail 政策列第三行與 hover 加「大單 n 筆」;Discord 四行卡第二行尾加「・大單 n 筆」 |

## 1. Caller map(grep 2026-09-14,worktree base = master 1a032b9b)

後端:
- `SignalDetector.evaluate` 唯一 caller `SignalHub.on_tick`(per-rule slot);`evaluate_book` ← `on_book`。`_eval_cdp` 讀 `_basis[code]`,唯一寫入點 `set_basis` ← hub `_distribute` / `_seed_slot`(兩處都經 `_filter_levels(cdp, levels)`)。
- 日 K 來源 `hub._daily_bars` = `StockEngine.daily_bars(code, n)` ← `fetch_daily_bars`(DK 段窗逐字 40 日,只有 1K fallback 段隨 n 縮);`_BASIS_BARS = 5` 是唯一的 n 產生點;`done = [b for b in bars if b["date"] < basis_date]` 已剔今日 partial。測試替身 `_FakeBars`(`tests/server/test_signal_hub.py`)記錄 `(code, n)`。
- `SignalEvent.detail` 唯一產生點 `_eval_sweep`;讀者 `hub._emit`(`payload["detail"]`)與 `_emit_policies`(`row["sweep"] = dict(event.detail)`);golden 測試逐鍵取值不比整個 dict。
- `_emit_policies` 列形狀讀者:`tests/server/test_signal_policy.py::_POLICY_KEYS`(集合斷言)、`backfill_policy_outcomes`(只補 t1/t2/d_* 六鍵,其他鍵原文保留)、Discord `format_policy_group_text`(讀 head 的 `sweep` / `groups` / `self` …)、前端 `SignalMsg`(wire 存證欄不讀)。
- `_kind_text`(Discord 單則 / 合併文案)與前端 `kindLabel` 逐字契約;新 kind 兩邊同加。
- 規則:`RULE_KINDS` / `PARAM_SPECS` / `INT_PARAM_KEYS` / `_DEFAULT_NAMES` / `_QUIET_KINDS` / `_seed_params` / `_seed_cooldown` / `rule_config` / `default_rules` 六處 kind 分派;`KIND_SWITCH` / `SWITCH_KEYS`(detector);`_legacy_flags` 以 `SWITCH_KEYS` 起手。
- 規則檔版本:`_CACHE_VERSION` / `_SUPPORTED_VERSIONS` / `load_rules` 遷移鏈;測試 `tests/server/test_signal_hub.py::_write_rules` 寫字面 `4`(→ 改引 `_CACHE_VERSION`,否則每個 hub 測試都會被 v4→v5 遷移多塞一張卡)、`tests/test_signal_rules.py::test_version_zero_and_five_still_raise` / `test_save_after_v1_load_lands_v4`(該變)。
- 前端 parity fixture `tests/fixtures/signal_param_specs.json` ← `tests/test_signal_rules.py::test_param_specs_parity_with_frontend` + `frontend/src/lib/signal-param-parity.test.ts`。

前端:
- `SignalKind` / `kindLabel` / `toneOf`(SignalRail)/ `RULE_KINDS` / `PARAM_FIELDS` / `KIND_LABEL` / `ruleSummary`(SignalRulesDialog)六處 kind 分派。
- 政策列第三行 `policyContextText(anchor)`、hover `policyTitle(policies)`(SignalRail 唯一 caller);`useSignalAlerts` 只讀 `notify` / `isPolicy`,不讀脈絡欄。

離線讀者(repo 外,W1 契約):研究目錄腳本逐列讀 `kind`,以 kind 白名單分桶;**不新增列型、每列 kind 恆在、既有列只加欄**。新 kind 值本身允許。

## 2. 既有行為白名單(不得破壞)

- W-1 圖上 CDP 五線(`/api/stock/overlay`)與閘無關,照畫。
- W-2 `cdp_cross` 合格檔的事件語意逐字不變:側別 / rearm 駐留 / 冷卻 / 多線合併 / 固定序 id。閘只決定「基準餵不餵」。
- W-3 基準取得失敗的既有處置(逾時 WARNING、有限重試、超限落 None、無已完成日 K WARNING)不變;閘不過是**第四種**結果(INFO),不觸發重試、不與失敗混淆。
- W-4 換日兩段式(stage1 暫存 / stage2 promote)、日別 guard、`drop_code` 清理:閘結果隨 cdp 一起走同一份快照,不另開第二份暫存。
- W-5 既有 `vol_burst` 規則與事件(含參數鍵集、種子、v3→v4 翻旗)零改動;新 kind 是兄弟卡不是參數。
- W-6 規則檔 v1..v4 照舊可載入(遷移鏈往前接一段);使用者已有規則一條不動;撞名 / 滿 30 條跳過並 WARNING(沿 `_append_seed`)。
- W-7 掃單簇定義與 golden fixture(`sweep_cluster_golden.json`)零改動:`detail` 既有四鍵值不變、事件時刻 / 價 / n30 / levels / qty / up_pct 逐字;只多一鍵。
- W-8 政策列既有全部欄位(含 `sweep` 四鍵、t1/t2/d_* 回填鍵)逐字不變;`backfill_policy_outcomes` 對含新鍵的列仍只補六鍵、其餘原文保留。
- W-9 Discord 四行卡第 1 / 3 / 4 行逐字不變;第 2 行只在**尾端**接一段。
- W-10 rail 政策列三行結構 / chip 色 / quiet 淡色 / 第三行既有字串前綴不變;舊列(缺 `big_lots_120s`)第三行與 hover **與現在完全相同**(不印「大單 -」)。
- W-11 前端訊號列對舊後端 / 舊 jsonl 不炸:未知 kind 印英文代號(既有);`vol_breakout` 缺 `pct` 時退回只印名,
  缺 `direction` 時退向上(沿 `limit_*` 既有慣例;two-axis spec F-03 後把原句「缺 pct / direction 皆只印名」改成此字面,
  實作與測試兩邊逐字一致)。
- W-12 `notify` 閘契約(缺欄視為 true)不動;新 kind 種子 `notify_discord=false` → 列帶 `notify:false` → 前端 toast / 嗶 / 桌面通知全靜音、rail 淡色仍列。
- W-13 `SignalEvent` 既有建構點零改動(新增狀態全在 detector 私有欄;`detail` 仍是唯一選配欄)。
- W-14 熱路徑:大單中位只在候選 tick(外盤且價升)才算;非掃單簇規則的 detector 不維護大單狀態以外的新東西(狀態是 per-detector,但只有掃單簇規則讀它;開銷 = 每 tick 一次 deque append)。

## 3. Grilling(`/auto` 疊加:frontier 逐題採建議解)

- **Q1 CDP 閘落點**:hub `_resolve_basis`(唯一有日 K 的地方)vs detector。
  `[auto-default: hub | reason: 日 K 只在 hub;detector 零 IO 且只認 set_basis,閘不過餵 None 正是既有「CDP 跳過、其他 kind 照常」語意,零新狀態]`
- **Q2 閘門檻是全域設定還是 per-rule 參數**:`SignalsConfig.cdp_gate_days=5` / `cdp_gate_pct=5.0`(`configs/signals.json` 可覆寫)vs `PARAM_SPECS["cdp_cross"]` 加鍵。
  `[auto-default: 全域設定 | reason: 研究是固定口徑不是使用者旋鈕;per-rule 要動 PARAM_SPECS + fixture + 前端 + 既有 cdp 規則遷移補鍵,影子期沒有調它的需求]`
- **Q3 歷史不足(< days+1 根已完成日 K)**:視為不合格(零事件)vs 放行。
  `[auto-default: 不合格 | reason: user 原話「只有前 5 日 5% 以上才會觸發」,證明不了 ≥5% 就不發;INFO 印「日 K 不足」讓對帳分得出兩種原因]`
- **Q4 日 K 抓幾根**:`_BASIS_BARS` 由 5 提到 `cdp_gate_days + 3`(6 根已完成 + 今日 partial + 1 緩衝 = 8)。
  `[auto-default: 8 | reason: DK 段窗本來就是 40 日逐字、n 只影響 1K fallback 段縮窗,成本不變;新常數以 cfg 推導不再字面]`
- **Q5 放量離開是新 kind 還是 vol_burst 參數化**:新 kind `vol_breakout`。
  `[auto-default: 新 kind | reason: PARAM_SPECS 鍵集是精確集合,給 vol_burst 加鍵 = 既有 vol_burst 規則全部要遷移補鍵;新 kind 讓既有爆量卡零改動(W-5),rail 也分得出兩種事件;「併進爆量規則」= 同家族兄弟卡]`
- **Q6 帶的錨點**:研究以 CDP 五線 / 前收 / 開盤 / 隨機價位當 L,結論「與價位無關」→ 線上不綁價位:錨 = 上一次離帶那筆(或當日首筆)的價,帶 = 錨 ±band_pct;離帶 = |價 − 錨| > 錨 × band_pct。
  `[auto-default: 錨 = 區段首筆價 | reason: §17 敏感度「真價位與隨機價位在 ±2 點內」,價位不是訊號來源;錨在首筆是研究 scan() 進帶邏輯的最小翻譯]`
- **Q7 穿越次數 ≥ 4 要不要**:研究 §17.4 穿越次數與續走無關,handoff 三個預設值也沒有它。
  `[auto-default: 不要 | reason: 沿 handoff 預設(帶寬 / 停留 / 倍數三個數),少一個旋鈕]`
- **Q8 時間軸**:停留時長與分鐘分桶用 tick 時刻(研究同尺,沿掃單簇先例),冷卻用牆鐘。
  `[auto-default: tick 時刻 + 牆鐘冷卻 | reason: 與 _eval_sweep 同一套規則,golden 可對照]`
- **Q9 離帶分鐘量的即時判**:研究看整分鐘(含離帶後同分鐘所有成交),線上自離帶那筆起累積、達 ratio 即發(群內達標即發的同款即時判);該分鐘結束仍未達 → 不發。
  `[auto-default: 即時判 | reason: user 09-07 對掃單簇拍板接受同型差異;等分鐘結束才發會晚最多 60 s]`
- **Q10 迴盪均量的分母**:研究 = 迴盪期**有成交的分鐘數**,且 < 4 分鐘不算(expansion None)。
  `[auto-default: 沿研究,4 分鐘地板留內部常數 | reason: 薄股 10 分鐘只成交 1–2 分鐘時「均量」沒意義,研究就是這樣濾的]`
- **Q11 參數與值域**:`band_pct` [0.1, 5] 預設 0.6、`min_dwell_secs` [60, 3600] 預設 600、`ratio` [1, 100] 預設 4;冷卻種子 600 s。
  `[auto-default: 如上 | reason: 三個預設值沿 handoff;冷卻:每次離帶錨就換新,一檔要再發至少再迴盪 10 分,600 s 只防同一分鐘內 flapping]`
- **Q12 13:00 後不算(研究 LAST_BREAK)**:研究為了 30 分結果窗;顯示層不需要。
  `[auto-default: 不加 | reason: 結果窗是量測用,不是訊號定義]`
- **Q13 大單定義細節**:沿 `bigtick_bt.py::bigtick_hits` 逐字:外盤(價 ≥ 賣一且賣一 > 0)、價 > 前一筆成交價、張數 ≥ K × 當日至今 tick 張數中位(含本筆;≥ 30 筆後才算;中位取最近 300 筆;`max(med, 1)`);n = 時刻 ∈ [s − 120, s] 的命中數(含本筆若命中)。已知差異:(1) 研究的 `hits` 含同毫秒群內**晚於**發訊筆的命中,線上看不到(≤ 群內差);(2) 研究 `bigtick_bt.load` 已濾 0 價 / 0 量列(`load()` 的 list comprehension),`bigtick_hits` 的 30 筆門檻與中位母體不含它們 —— 線上掛在 `_eval_sweep` 的壞 tick 閘之後,同樣不含;two-axis spec F-02 原以為研究不濾,查 `load()` 後確認兩邊一致,記錄在此免下次再查。
  `[auto-default: 逐字 + 已知差異記錄 | reason: 對帳要能回頭算分層,定義必須同源]`
- **Q14 大單參數位置**:`SignalsConfig.big_lot_ratio=10` / `big_lot_window_secs=120`(全域);30 筆 / 300 筆兩個窗留模組常數。
  `[auto-default: 全域設定 | reason: 顯示欄不是規則;欄名 big_lots_120s 是 user 定的字面,窗改了欄名不跟(影子期口徑釘死,doc 註明)]`
- **Q15 欄位落點**:掃單簇列 `detail.big_lots_120s`;政策列頂層 `big_lots_120s`,`sweep` 鏡像**不含**它(保持四鍵)。
  `[auto-default: 如上 | reason: 政策列 sweep 是「掃單簇參數袋」,大單是脈絡;頂層欄是 user 指名的離線讀者鍵;raw 列走 detail 是唯一選配欄]`
- **Q16 顯示**:rail 政策列第三行尾加「・大單 n 筆」、hover 同;Discord 第 2 行尾加「・大單 n 筆」;缺欄(舊列)整段不印。
  `[auto-default: 如上 | reason: handoff 深夜補記 3;缺欄不印是 W-10]`
- **Q17 種子卡預設**:`enabled=true`、`notify_discord=false`、名「放量離開」、進 `_QUIET_KINDS`。
  `[auto-default: 如上 | reason: 影子期只上 rail 列不推播]`

方向性抉擇檢查:SC 集合 / out of scope / 資料源均未動;對外契約只有**加**(新 kind 值、新欄、規則檔版本 +1 with 遷移),無改寫 → 不停。

## 4. Seams(測試只寫在這些)

- S-1 **detector 行為合約**(`tests/live/test_signal_state.py`,既有 seam):放量離開的進帶 / 停留 / 離帶 / 分鐘量即時判 / 方向 / 冷卻 / 狀態無條件推進;大單命中的定義四條件 + 120 s 窗 + `detail.big_lots_120s`。
- S-2 **hub 接線**(`tests/server/test_signal_hub.py` / `test_signal_policy.py`,既有 seam):CDP 閘(合格 / 不合格 / 歷史不足 / 抓幾根 / 換日暫存路徑同閘);政策列頂層 `big_lots_120s` + `sweep` 四鍵不變 + `_POLICY_KEYS`;Discord 第 2 行;規則檔 v4→v5 遷移(`tests/test_signal_rules.py`)。
- S-3 **前端純函式 + rail 元件**(`signal-model.test.ts` / `SignalRail.test.tsx` / `signal-param-parity.test.ts`,既有 seam):`kindLabel` 新 kind、第三行 / hover 帶「大單 n 筆」、缺欄不印、parity fixture 新 kind。

## 5. Tickets(垂直切片)

1. **T1 CDP 列閘**(無 blocker):config 兩鍵 → hub 閘 → 測試(合格 / 不合格 / 不足 / staged 路徑)。
2. **T2 放量離開 kind**(無 blocker):config / rules(kind、PARAM_SPECS、種子、v5 遷移、rule_config)→ detector `_eval_breakout` → hub `_kind_text` → 前端六處 + fixture → 測試。
3. **T3 大單筆數格**(無 blocker):config 兩鍵 → detector 大單狀態 + `detail.big_lots_120s` → hub 政策列頂層欄 + Discord 第 2 行 → 前端第三行 / hover → 測試。

三張互不阻塞;實作序 T1 → T3 → T2(小到大)。

## 6. Out of scope

政策 P 停損 / 現沖計數 / 額度 / 隱藏庫存 / 族群多日漲幅線 / 群益 XScript / 大單獨立訊號 / 慢推偵測器 / 回檔再買 / 週判準併 CSV(全在 handoff「不在本 /mod 範圍」);CDP 閘的可觀測 API(只 log)。
