# feat/surge-pullback-signal — 實作計畫(spec = issue #174)

Handoff:`%TEMP%\copycat-handoff-2026-09-02-surge-pullback.md`。grilling 已於前一 session 完成,
本檔為 to-tickets 級切片(單一垂直切片,不另發 ticket issues —— handoff 指示直接起實作)。

## 拍板摘要(issue #174)

- 新規則 kind `surge_pullback`,三參數:`surge_pct` + `window_secs`(武裝,沿 surge 同式)、
  `pct`(自峰值回檔 %)。
- 武裝後追蹤波峰;回落 ≥ pct 發一則;創該波新高 → 峰值更新重武裝;不限時;只掛個股。
- 種子兩張卡:(5 分鐘 +2%,回檔 1%)、(5 分鐘 +2%,回檔 2%)。與 surge_crash 完全獨立。

## 實作時拍板(寫進 PR)

1. **種子注入 = `_CACHE_VERSION` 2→3 遷移**(沿 v1→v2 pattern):v2 檔載入期在記憶體 append
   兩張種子卡,不回寫檔案(回退窗同 v1);名稱撞名跳過該卡、超 MAX_RULES 跳過並 WARNING。
   遷移參數 = `SignalsConfig()` 預設值(= spec 拍板值;load_rules 簽名不吃 config,v1 同理)。
2. **狀態機語意沿 latch 紀律**:狀態轉移(武裝/峰值/發訊消耗)無條件推進;`enabled` 與
   cooldown 只 gate 事件產出(停用期間波被消耗、重開不補發 —— 與 limit_lock 同)。
3. **重武裝兩條路**(two-axis review S-1 修訂初版「唯一路徑 = 創前高」):(1) 創該波新高
   (嚴格 > 峰值,grilling 拍板);(2) 已發後以「發訊時點之後」的窗重跑 surge 同式 ——
   基線 = 發訊那筆,沿跌不可能連發;深跌後的獨立新波(未過前高)接得回來。
   ※ 此為實作期補拍板,PR 說明列為 user 追認點。
4. **事件 `pct` = 自峰值回落幅度(正數)**;文案「爆拉回檔 {pct:.2f}%」前後端逐字同式。
5. **冷卻桶 `(code, "surge_pullback", "")` per-rule detector 天然獨立**;種子冷卻 60s
   (= COOLDOWN_MIN;一則/波已由重武裝把關,冷卻只防極端 flapping)。
6. `SignalsConfig` 新欄 `pullback_pct=1.0` / `pullback_cooldown_secs=60.0`(rule_config 映射載體;
   configs/signals.json 可覆寫)。武裝參數映既有 `surge_pct` / `surge_window_secs`(per-rule
   config,與 vol_burst 借 surge_window_secs 同一模式)。

## 變更面(檔案)

後端:`copycat/live/signal_state.py`(_eval_pullback + KIND_SWITCH/SWITCH_KEYS)、
`copycat/signal_rules.py`(RULE_KINDS/PARAM_SPECS/種子/遷移 v3/rule_config)、
`copycat/signals_config.py`(兩欄)、`copycat/server/signal_hub.py`(`_kind_text`)。
前端:`useSignalRules.ts`(RULE_KINDS)、`signal-params.ts`(PARAM_FIELDS)、
`signal-model.ts`(SignalKind/kindLabel)、`SignalRulesDialog.tsx`(KIND_LABEL/ruleSummary)、
`SignalRail.tsx`(toneOf)。
契約:`tests/fixtures/signal_param_specs.json` 加 kind(雙邊 parity 測試既有)。

## Seams(user 已核可,測試只寫在這)

1. `signal_state.py` 狀態機(零 IO、時鐘注入)—— 新 TestSurgePullback 類,含鼎元 2426
   2026-09-01 離線對照序列(峰 104.5 → 1% 於 103.4、2% 於 102.4)。
2. 參數契約 parity fixture(既有雙邊測試自動涵蓋)。
   既有字面 lock(RULE_KINDS tuple / PARAM_SPECS literal / default_rules kinds 序 /
   `_kind_text`)屬「事前標為該變」的契約鎖,隨契約同步更新。

## 驗證判準

pytest / ruff / pyright + 前端 npm test / tsc / eslint + `copycat validate`(golden gate,
不碰 replay 面應綠);盤中真環境實發觀察(user 盤中過目,離線對照先行)。
