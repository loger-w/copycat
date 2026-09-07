# PR #177 Code Review 比較報告 · SHA f4c76faf

**Report projection schema**: 1

**PR**: [loger-w/copycat#177](https://github.com/loger-w/copycat/pull/177)
**標題**: feat(signals): 爆拉回檔訊號 surge_pullback(spec #174,種子 1%/2% 兩卡)
**作者**: XU MIN YU(loger-w)
**分支**: `feat/surge-pullback-signal` → `master`(PR 已 rebase merge、遠端分支已刪;review 環境以 `refs/pull/177/head` 重建)
**變更**: 22 檔案, +912 / −42
**審查日期**: 2026-09-02
**Review input basis**: source repo `R_kgDOTsITBg` + `f4c76faf139bd6457067714b49f7a86045c6f5de`;destination repo `R_kgDOTsITBg` + `6ef6b9131fad0c577edba4327e6a0ee2503cbb43`;input_binding: verified(worktree HEAD 逐字節等於 source SHA;base 以精確 SHA 釘定並可解析)
**Review continuity**: source_continuity=CURRENT(產報告前重抓 headRefOid 仍為 f4c76faf);base_changed=true(master 已因本 PR 自身的 rebase merge 前進至 e93b0afe —— diff 基準 6ef6b913 為 PR API 之 baseRefOid,不受影響);review_context_changed=false
**審查工具**: CC context-aware reviewer agents(primary ×2 chunks)+ 主 session 逐條機制核實(關鍵條 code trace / grep 反證)。Codex 中性、Codex 對抗、Gemini Flash、Gemini Pro 四軸因本機無對應 CLI 全數缺軸(第一手證據:主 session PowerShell 實跑 `Get-Command codex, agy, sem` 三者皆 `NOT FOUND`)—— 本輪為 CC 單軸 + 同軸驗證,非 cross-axis,詳「沒做的部分」
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary=python-reviewer ×2 chunks(requested=opus / observed=opus);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(gate SKIPPED 未派);Codex=UNAVAILABLE(CLI 不存在);Gemini=UNAVAILABLE(agy CLI 不存在)
**覆蓋 (ENH-A)**: |F|=22 → covered 9 / no-issues 12 / skipped 1 / missed 0(chunked: 是 —— DIFF_LINES 954 > 800 門檻;chunk 1 = 排序前 20 檔 785 行、chunk 2 = tests/server/test_signal_routes.py + tests/test_signal_rules.py 169 行;skipped 1 = `.claude/feat/surge-pullback-signal/evidence/rules-dialog-new-pullback.jpg`,理由 = 同內容 close-up PNG 已逐像素審過、全頁版為重複)
**定位 (ENH-B)**: anchored exact 15 / ambiguous 1 / FAILED 0
**React-doctor (2.97)**: 未引入新問題(--scope changed --base 6ef6b913 實跑於 review worktree,newCount 0;既有 1 條不計)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_NORMATIVE_AUTHORITY)
**Blast radius (2.9)**: 空輸出跳過(sem CLI 未安裝,script 無輸出)
**Codex preset (2.98)**: 未詢問(codex CLI 不存在,中性/對抗兩軸缺軸,preset 選擇無意義)
**Gemini 軸 (2.96)**: 未詢問(agy CLI 不存在;Flash 永久軸缺軸、Pro N-A)
**Quota (Gemini 軸)**: 未取 dashboard snapshot(軸未跑)
**審查軸狀態**: primary(python-reviewer ×2 chunks)PASS(逐檔 accounting 齊);domain reviewers N-A(security / spec-compliance 未觸發);Codex 中性 FAIL(CLI 不存在);Codex 對抗 FAIL(CLI 不存在);Gemini Flash FAIL(CLI 不存在);Gemini Pro N-A(opt-in 未啟用且 CLI 不存在);cross-axis verification FAIL → 以同軸替代驗證執行(主 session 對全部 16 條逐條機制核實:F-01/F-03/F-07/F-16 以 code trace 或 grep 實證,其餘對 reviewer 附的 search-proof / 引文逐條對照);C4 N-A(gate SKIPPED)
**校準套用**: 無作者校準檔(xu-min-yu.md 不存在)、本輪無套用
**Provenance (2.55)**: N-A(base = master)
**worktree**: C:\side-project\copycat\.worktrees\review-pr-177
**worktree HEAD**: f4c76faf139bd6457067714b49f7a86045c6f5de

**Report generation**: sha256:8c689d748e1c6e5cc8621ed1fac5cd54a56cb2b0e177890323149177f6e4b32a

---

## Spec 依據

- 依 Step 2.6 偵測規則,本 PR 附 **`.claude/feat/surge-pullback-signal/plan.md`**(實作計畫,含實作期拍板 6 條)。真正的上游 spec 是 **GitHub issue #174**(grilling 拍板全文:kind / 三參數 / 種子兩卡 / 創新高重武裝 / 與 surge_crash 獨立 / 只掛個股 / 不加量能 / parity 契約 / 鼎元 2426 離線判準)。兩份都注入 reviewer 當 scope ground truth。
- **⚠️ spec 作者 = PR 作者**(issue #174 與 plan.md 均由同一流程產出;out-of-scope 判定以其為據時注意利益重疊 —— 本輪 F-01 正是「plan 自寫的安全論證與出貨 code 不符」類,未被 spec 免罪;F-13 是 plan 與 code 直接矛盾)。
- `SPEC_COMPLIANCE` receipt:gate=SKIPPED;dispatch=NOT_APPLICABLE;dispatch_count=0;reason_code=C4_NO_NORMATIVE_AUTHORITY(spec 為 GitHub issue 拍板文字與非正式 plan prose,無可錨定的 NORMATIVE 條文;plan.md 內無 MUST/SHALL 級 implementation-binding 條款);requested_model=opus;observed_model=UNAVAILABLE;effort=xhigh;0 clauses / 0 findings / 0 observations / 0 invalidated。gate=SKIPPED 之下不存在 reducer `human_projection`,本報告零 C4 finding、零 C4 accounting 列 —— 「invalidated 語意不得外洩」要求以空集合恆成立(報告全文對任何 C4 candidate 內容 0 引用)。

## 變更概要

| 檔案 | 類型 | 說明 |
| --- | --- | --- |
| copycat/live/signal_state.py | 新功能 | `_eval_pullback` 狀態機(surge 同式武裝 / 波峰追蹤 / 一波一則 / 兩條重武裝路)+ `_window_change_pct` 抽共用 + KIND_SWITCH/SWITCH_KEYS 五鍵 |
| copycat/signal_rules.py | 新功能 | RULE_KINDS/PARAM_SPECS 加 kind;`_CACHE_VERSION` 2→3;`_migrate_v2` 種子兩卡載入期注入;`_pullback_seed_rule`;rule_config 映射 |
| copycat/signals_config.py | 新功能 | `pullback_pct` / `pullback_cooldown_secs`(映射載體) |
| copycat/server/signal_hub.py | 新功能 | `_kind_text`「爆拉回檔 {pct:.2f}%」 |
| frontend/src/hooks/useSignalRules.ts | 契約 | RULE_KINDS 五值鏡像 |
| frontend/src/lib/signal-params.ts | 契約 | PARAM_FIELDS 加 surge_pullback 三欄 |
| frontend/src/lib/signal-model.ts | 契約 | SignalKind + kindLabel(與後端逐字同式) |
| frontend/src/components/stock/SignalRulesDialog.tsx | 前端 | KIND_LABEL「爆拉回檔」+ ruleSummary |
| frontend/src/components/stock/SignalRail.tsx | 前端 | toneOf 綠(向下) |
| frontend/src/components/stock/SignalRulesDialog.test.tsx | 測試 | 五類中文字面跟進 |
| frontend/src/lib/signal-param-parity.test.ts | 測試 | fixture 健檢五 kind + 預設值 golden |
| tests/fixtures/signal_param_specs.json | 契約 | parity fixture 加 kind |
| tests/live/test_signal_state.py | 測試 | TestSurgePullback 15 條(含鼎元 2426 離線對照、S-1 兩條) |
| tests/test_signal_rules.py | 測試 | 字面鎖跟進 + TestMigrationV2ToV3 七條 + rule_config 映射 |
| tests/server/test_signal_hub.py | 測試 | `_write_rules` 改寫 v3 + 種子序 6 條 |
| tests/server/test_signal_routes.py | 測試 | `_SEEDED_KINDS` 6 條跟進 |
| .claude/feat/surge-pullback-signal/plan.md | 產物 | 實作計畫(拍板紀錄) |
| .claude/feat/surge-pullback-signal/verification.md | 產物 | 驗證證據 |
| .claude/feat/surge-pullback-signal/code-review-round-1.json | 產物 | two-axis review round JSON |
| .claude/feat/surge-pullback-signal/evidence/replay_2426.py | 產物 | 鼎元離線 replay 腳本 |
| .claude/feat/surge-pullback-signal/evidence/rules-dialog-new-pullback.jpg | 產物 | UI 截圖(全頁) |
| .claude/feat/surge-pullback-signal/evidence/rules-dialog-new-pullback-closeup.png | 產物 | UI 截圖(表單 close-up) |

## 發現總覽

| # | 問題 | 嚴重度(原 → 校正) | 複查(同軸替代驗證) | 最終建議 | Action | Action 理由 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | S-1 重武裝基線是「發訊後首筆」不是「該時點起最高」—— V 型反彈(+surge_pct 但未過前高)即重武裝且峰值反向下移,同一波可近重複再發;docstring「不可能連發」論證不成立,追認前提有誤;兩條既有測試恰好繞開此 case | MEDIUM → MEDIUM | CONFIRMED(主 session code trace:104.5 波 fire@102.4 → 反彈 104.45 gain +2.00% → 重武裝 peak=104.45 → 102.36 再發 2.00%;60s 冷卻是唯一 backstop) | Should Fix | `ask-user` | 修法涉 S-1 語意再拍板(波谷基線 / 低於發訊價條件 / 接受現況改文案),正是 PR 留的追認點 |
| 2 | 已發態重武裝檢查每 tick 從窗頭線性掃到 fired_at —— 狀態推進在 enabled gate 前,6 個 slot 全跑 × 訂閱檔數;O(1) 等價修法 = fire price 一起存 | MEDIUM → MEDIUM | CONFIRMED(機制屬實;上界受窗 300s / fire tick 出窗自然消失,量級有界但在每 tick 熱路徑) | Should Fix | `auto-fix` | 等價改寫、局部,不改語意 |
| 3 | tests/server/test_signal_routes.py 的 `_RULE_PARAMS` 漏加 surge_pullback:新 kind 的 REST 鏈(POST → normalize 三參數 → save → 熱重載 → GET)零覆蓋;下次任何測試 `_rule_body("surge_pullback")` 直接 KeyError | MEDIUM → MEDIUM | CONFIRMED(主 session grep:該表四鍵、無 surge_pullback;同 PR 的 test_signal_hub.py 姊妹表有加) | Should Fix | `auto-fix` | 補表項 + 一條 POST/GET round-trip |
| 4 | 遷移 id 撞既有的斷言恆真:`load_rules` 對重複 id 是 raise 不是去重,回傳集 set-size 斷言永不失敗;`_migrate_v2` 的 `while rule_id in ids` 迴圈零覆蓋(砍掉 → 開機 503 而測試全綠) | MEDIUM → MEDIUM | CONFIRMED(signal_rules.py 437-439 對照:重複 id 走 raise 路徑) | Nice to Have | `auto-fix` | 凍 epoch 造撞的測試寫法明確 |
| 5 | v2→v3 遷移的 INFO/WARNING log 未測:MAX_RULES 跳卡 WARNING 是 29 條規則使用者「沒拿到 2% 卡」的唯一訊號;v1 前例(`test_v1_migration_logs_rule_id_and_value`)有測,不對稱 | MEDIUM → LOW | CONFIRMED(grep caplog 僅 v1 類;對帳 log 字串無鎖) | Nice to Have | `auto-fix` | caplog 兩行斷言 |
| 6 | seam 測試類 docstring 仍寫「創該波新高才重武裝(唯一重武裝路徑)」,兩屏之下就是 S-1 第二條路的測試 —— 下一個讀者照 docstring 當 spec 會把第二分支當死碼砍 | MEDIUM → LOW | CONFIRMED(逐字對照 tests/live/test_signal_state.py 789-791 vs 997) | Nice to Have | `auto-fix` | docstring 改兩條路,與 `_eval_pullback` 對齊 |
| 7 | 「surge_pullback 恆走缺鍵那條」註解機制錯:`SWITCH_KEYS` 已含新鍵 → `_legacy_flags` 的 dict 鍵恆在,手改 legacy `signals_enabled.json` 寫 `"surge_pullback": false` 會把兩張種子卡一起關掉 —— 正是註解說不會發生的事;`_legacy_flags` docstring「四條種子規則」同舊 | LOW → LOW | CONFIRMED(主 session 逐行 trace `_legacy_flags`:fromkeys(SWITCH_KEYS) + 檔案值逐鍵覆蓋) | Nice to Have | `auto-fix` | 兩處註解改寫成真機制 |
| 8 | `_seed_params` 沒有 surge_pullback branch → `_seed_params("surge_pullback", cfg)` 回 `{}`(normalize 必 INVALid)——只因 default_rules 顯式繞開才不可達;`_pullback_seed_rule` 又手抄一份 `_clamp` 迴圈 | LOW → LOW | CONFIRMED(唯一 caller 已繞開,現況無症狀;陷阱留給下一個 caller) | Nice to Have | `auto-fix` | 補 branch、種子改 `{**_seed_params(...), "pct": pct}` |
| 9 | 「0 價 tick 整段跳過」宣稱比 code 寬:0 價 tick 在 evaluate 就進共用窗,成為窗頭後 `_window_change_pct` 回 None → surge 與 pullback 武裝一起靜默熄最長 300s、零 log(`_eval_surge` 既有盲點,本 PR 給它第二個消費者並宣稱完整) | LOW → LOW | CONFIRMED(evaluate 窗推進在任何價格 gate 之前;屬既有行為的宣稱過寬,非回歸) | Nice to Have | `auto-fix` | 註解收窄措辭(peak 保護屬實、窗污染另記) |
| 10 | `if version not in (_CACHE_VERSION, 2, 1)` 符號與字面混排:下次 bump 成 4 時要記得手補字面 3,忘了 → 所有 v3 檔開機 raise → hub None → routes 503 | LOW → LOW | CONFIRMED(字面;與 `_migrate_v2` 觸發條件的同步靠人記) | Nice to Have | `auto-fix` | `_SUPPORTED_VERSIONS` 常數或 range 推導 |
| 11 | 模組 docstring 首行仍「四類訊號:CDP 五線穿越 / 爆拉跌 / 爆量 / 鎖漲跌停與打開」—— 維護者第一眼讀的清單漏了爆拉回檔 | LOW → LOW | CONFIRMED | Nice to Have | `auto-fix` | 一行改五類 |
| 12 | 入版控的 evidence 腳本不可重跑:`sys.path` 硬編已刪除的 feature worktree 絕對路徑、輸入 `bars_2426.json` 未入 PR —— verification.md 的「1% 卡 4 則 / 2% 卡 4 則」他人無法重現 | LOW → LOW | CONFIRMED(PR 檔案清單無 bars_2426.json;worktree 已清) | Nice to Have | `ask-user` | 要不要補 commit bars 切片 + 相對路徑化由你裁(evidence 檔案大小取捨) |
| 13 | plan.md 實作拍板 #6 寫 `pullback_pct`「configs/signals.json 可覆寫」,與出貨的 signals_config.py 註解(N-1:覆寫零效果、僅映射載體)直接矛盾 —— plan 是拍板紀錄,下一個讀者會照它以為有旋鈕 | LOW → LOW | CONFIRMED(兩檔逐字對照;code 註解是對的、plan 是錯的) | Nice to Have | `auto-fix` | plan 那半句改掉 |
| 14 | `by_kind = {r["kind"]: ...}` 三處把兩張 surge_pullback 卡塌成最後一張(1% 卡的 cooldown/enabled 斷言被 2% 卡遮蔽) | LOW → LOW | PARTIAL(現行兩卡經 `_seed_cooldown` 同源恆同值,塌卡對現況零遮蔽;防的是未來每卡獨立值時的回歸 —— `test_pullback_seed_cards_pinned_to_names` 已按 name 鎖 params 半邊) | Nice to Have | `auto-fix` | 三處改 name 鍵,與既有 by_name 測試同款 |
| 15 | `_write` helper 在兩個遷移測試類逐字複製;`TestMigrationV1ToV2` 類名已不符內容(擁有 `test_save_after_v1_load_lands_v3`)、`test_one_rule_per_kind_all_valid` 名不符 6 條實斷 | LOW → LOW | CONFIRMED(逐字對照) | Nice to Have | `auto-fix` | module-level helper + 兩個名字改實 |
| 16 | tests/test_signal_rules.py:61 新行 102 字元超宣告 line-length 100,`ruff format` 會重排 | LOW → LOW | REFUTED(baseline 反證:同檔既有 >100 字元行多處(L71/72/74/75,主 session awk 實測)長期存在;repo 慣例明文「不順手重排既存格式」、E501 未啟用 —— 該行與同檔現況一致) | 參考用 | `no-op` | 與 repo 既有格式現況一致,不動 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 74477215207a243b9ff1 action=ask-user
F-02 finding_uid: 2e031a143c55425824f6 action=auto-fix
F-03 finding_uid: 3325cc2414e97bd74c48 action=auto-fix
F-04 finding_uid: c94da4efeb14b31d805c action=auto-fix
F-05 finding_uid: 4554c6780743ad78cd32 action=auto-fix
F-06 finding_uid: 9164d9c2766895ea950a action=auto-fix
F-07 finding_uid: 2b9002af9d2e3f33bec9 action=auto-fix
F-08 finding_uid: c7572570b3f85f5c0735 action=auto-fix
F-09 finding_uid: 5d0b56de3fecb0c9e9da action=auto-fix
F-10 finding_uid: dd2212e64ddc1f935884 action=auto-fix
F-11 finding_uid: 5be31ad0ea010480d1da action=auto-fix
F-12 finding_uid: 58c674d23c7920348cdf action=ask-user
F-13 finding_uid: 042c65a7c57b5b25aa43 action=auto-fix
F-14 finding_uid: 5287984c8077226dbc51 action=auto-fix
F-15 finding_uid: 43e4e753bfdb16715d4e action=auto-fix
F-16 finding_uid: 6429121c0d56f108449f action=no-op

### Inline Comments per Finding（直接複製貼到 PR review）

#### #1 發訊後 V 型反彈沒過前高也會重武裝,而且峰值往下搬 —— 「一波一則」在這個 case 破了

**File**: copycat/live/signal_state.py
**Line**: 509-512

**Comment**:
```
S-1 的安全論證寫「基線是發訊那一筆(該時點起區間內最高的一筆),沿跌永遠不會 +surge_pct」——
前半句對、括號裡那句不對:基線是發訊後「首筆」,之後任何低於 peak 的反彈都比它高。
拿出貨的 2% 卡走一遍:峰 104.5 → 102.4 發訊(−2.01%)→ 反彈 104.45(未過前高,
但距發訊價 +2.00% ≥ surge_pct)→ 重武裝且 peak 變 104.45(峰值向下搬,跟「創波高:峰值前推」
的註解反著走)→ 滑回 102.36 → 再發一則 2.00%,跟第一則差 0.04%。60s 冷卻是唯一擋板,
兩分鐘的來回就穿過去。

兩條測試恰好都繞開:test_downhill_… 只測單邊下跌、test_recovery_below_peak_… 反彈只給 +0.99%(< 2%)。

修法要再拍一次 S-1 語意:重武裝的 surge 基線改成「發訊後波谷」且波谷 < 發訊價(這才是
「深跌後的獨立新波」原意);或接受近重複、把 docstring 的「不可能連發」改掉 + 補 V 反彈測試,
讓追認點寫的是真代價。
```

#### #2 已發態的重武裝檢查每 tick 從窗頭掃一遍,而且 6 個 slot 全都在掃

**File**: copycat/live/signal_state.py
**Line**: 534

**Comment**:
```
_window_change_pct(..., since=fired_at) 是從 deque 頭一路走到 fired_at —— fire tick 還在
300s 窗內的期間,活躍檔一 tick 幾百格;狀態推進又刻意在 enabled gate 之前,所以 6 張卡
的 detector(只有 2 張是 pullback)每 tick 每檔都各掃一遍。

O(1) 等價寫法:fired_at 旁邊把 fire price 一起存 ——
window[0][0] <= fired_at 時基線就是 fire price,否則退回 window[0][1]。
語意完全同(差別只在凍結時鐘下的同時戳 tie)。
```

#### #3 routes 測試的 _RULE_PARAMS 沒加 surge_pullback,新 kind 的 REST 鏈零覆蓋

**File**: tests/server/test_signal_routes.py
**Line**: 57-59

**Comment**:
```
同 PR 裡 test_signal_hub.py 的姊妹表有加 "surge_pullback": {...},這份沒跟 ——
兩個後果:下次誰寫 _rule_body("surge_pullback") 直接 KeyError;
更實際的是使用者真正會從 Dialog 新增的唯一新 kind,POST → normalize(三參數精確集合)
→ save → 熱重載 → GET 這條 wire 路徑目前沒有任何 route 測試走過。

補表項 + 一條 POST-201 / GET round-trip 就好。
```

#### #4 「id 不得撞既有」這條斷言永遠不會紅

**File**: tests/test_signal_rules.py
**Line**: 658

**Comment**:
```
load_rules 對重複 id 的行為是 raise INVALID_RULE(signal_rules.py 437-439),
不是靜默去重 —— 所以對「回傳值」做 set-size 斷言恆真。真正要防的回歸
(_migrate_v2 的 while rule_id in ids 被砍)症狀是開機 raise → hub None → 503,測試照綠。

修法:monkeypatch signal_rules.time.time 凍 epoch,v2 檔預放一條 id = new_rule_id(epoch, 1)
的規則,斷言 load 成功回 3 條 —— 沒有去重迴圈時這裡會 raise。
```

#### #5 遷移的 log/WARNING 沒測 —— MAX_RULES 跳卡那行是使用者唯一的訊號

**File**: tests/test_signal_rules.py
**Line**: 630

**Comment**:
```
_migrate_v2 append 種子卡有 INFO(對帳判準)、29/30 條跳卡有 WARNING ——
後者是滿載使用者「沒拿到 2% 卡」的唯一線索,兩個都沒 caplog 斷言。
v1 那類有 test_v1_migration_logs_rule_id_and_value 前例,補對稱的兩行就好
(test_seed_skipped_when_would_exceed_max_rules 裡 caplog.at_level("WARNING"))。
```

#### #6 seam 測試類的 docstring 還寫「唯一重武裝路徑」,兩屏下面就是第二條路的測試

**File**: tests/live/test_signal_state.py
**Line**: 789-791

**Comment**:
```
類 docstring:「創該波新高才重武裝(唯一重武裝路徑)」——
同類裡 test_fresh_surge_after_fire_rearms_without_new_high 斷言的就是第二條路。
這份 docstring 在 repo 慣例裡是狀態機的人讀契約,照它動手的人會把 S-1 分支當死碼。
改成兩條路、跟 _eval_pullback 的 docstring 對齊。
```

#### #7 「恆走缺鍵那條」是錯的 —— legacy 檔手寫 false 關得掉兩張種子卡

**File**: copycat/signal_rules.py
**Line**: 301

**Comment**:
```
_legacy_flags 是 dict.fromkeys(SWITCH_KEYS, True) 起手,SWITCH_KEYS 這次已含
surge_pullback → 鍵恆在,legacy_flags.get(kind, True) 永遠讀得到值。
今天行為一樣(檔案裡沒這鍵 → True),但手改過 signals_enabled.json 加
"surge_pullback": false 的話,兩張種子卡會一起關 —— 正是這行註解說不會發生的事。
順帶 _legacy_flags docstring 的「四條種子規則」也舊了(現在 5 鍵 6 條)。
兩處註解改寫成真機制就好,行為不用動。
```

#### #8 _seed_params 留了個 `{}` 陷阱,種子卡又手抄了一份 clamp

**File**: copycat/signal_rules.py
**Line**: 274

**Comment**:
```
_seed_params("surge_pullback", cfg) 現在回 {} —— normalize_rule 對它必 INVALID_RULE,
只因 default_rules 顯式 if kind == "surge_pullback" 繞開才碰不到;下一個 caller 就會踩。
_pullback_seed_rule 同時手抄了 _clamp(f"{kind}.{key}") 那段。
補 branch(surge_pct/window_secs 走 cfg)、種子改 {**_seed_params("surge_pullback", cfg), "pct": pct},
陷阱跟重複一起消。
```

#### #9 「0 價 tick 整段跳過」講得比 code 寬 —— 壞 tick 還是進了共用窗

**File**: copycat/live/signal_state.py
**Line**: 515

**Comment**:
```
guard 保護的是 peak 不被 0 價打穿(這半對),但 evaluate 在任何價格 gate 之前就把
0 價 tick 收進共用窗;它變成窗頭後 _window_change_pct 回 None → surge 跟 pullback 的
武裝一起靜默熄最長 300s、零 log。這是 _eval_surge 既有盲點(oldest <= 0 早退同款),
不是本 PR 回歸 —— 但註解寫「整段跳過」會讓人以為窗也是乾淨的。
把措辭收窄成「峰值判定跳過;窗污染是既有另一題」即可。
```

#### #10 版本白名單 (_CACHE_VERSION, 2, 1) 下次 bump 要靠人記得補 3

**File**: copycat/signal_rules.py
**Line**: 421

**Comment**:
```
現值展開是 (3, 2, 1);bump 成 4 時符號自動滑走,字面 3 要手補 ——
忘了的症狀是所有 v3 檔開機 INVALID_RULE → hub None → signals routes 整組 503。
_SUPPORTED_VERSIONS = tuple(range(1, _CACHE_VERSION + 1)) 一行讓白名單跟遷移鏈不可能脫鉤。
```

#### #11 模組 docstring 第一行還是「四類訊號」

**File**: copycat/live/signal_state.py
**Line**: 3

**Comment**:
```
KIND_SWITCH 的註解改五鍵了,模組開頭這行(維護者第一眼)還列四類、沒有爆拉回檔。
一行補上。
```

#### #12 入版控的 evidence 腳本跑不起來 —— 路徑硬編已刪的 worktree、輸入檔沒進 PR

**File**: .claude/feat/surge-pullback-signal/evidence/replay_2426.py
**Line**: 16

**Comment**:
```
sys.path 釘死 C:\...\worktrees\feat-surge-pullback-signal(收尾已刪),
bars_2426.json 又只在 scratchpad —— verification.md 引用的「1% 卡 4 則 / 2% 卡 4 則」
現在只有結論、沒人能重跑。要不要補 commit bars 切片(或 trim 到當日 270 根)+
路徑改 repo-root 相對,由你裁 —— evidence 檔案大小 vs 可重現性的取捨。
```

#### #13 plan.md 說 pullback_pct 可用 configs/signals.json 覆寫 —— code 已經判它是死旋鈕

**File**: .claude/feat/surge-pullback-signal/plan.md
**Line**: 28

**Comment**:
```
實作拍板 #6 那句「configs/signals.json 可覆寫」跟出貨的 signals_config.py 註解
(rule_config 恆以 params["pct"] 覆寫、覆寫本鍵零效果零訊號)直接矛盾 —— code 是對的。
plan 是拍板紀錄,留著錯句下個讀者會以為有旋鈕。半句改掉。
```

#### #14 by_kind 三處把兩張回檔卡塌成一張

**File**: tests/test_signal_rules.py
**Line**: 413

**Comment**:
```
kind 不再是唯一鍵,{r["kind"]: ...} 只留最後那張(2% 卡)——
1% 卡的 cooldown/enabled 斷言其實沒在測。現況兩卡這些值同源恆同、零遮蔽,
但哪天種子改成每卡獨立值就是靜默漏測。三處改 name 鍵,
跟 test_pullback_seed_cards_pinned_to_names 同款。
```

#### #15 _write 抄了兩份、兩個名字跟內容漂了

**File**: tests/test_signal_rules.py
**Line**: 638

**Comment**:
```
_write 在兩個遷移類逐字一樣,搬 module-level 一份就好。
順帶:TestMigrationV1ToV2 現在擁有 test_save_after_v1_load_lands_v3(類名已不符),
test_one_rule_per_kind_all_valid 實際斷 6 條(每 kind 一條的敘述不再成立)。
兩個名字改實。
```

#### #16 102 字元那行 —— 跟同檔既有格式一致,不用動(不是 PR 缺陷)

**File**: tests/test_signal_rules.py
**Line**: 61

**Comment**:
```
reviewer 提的點:RULE_KINDS 字面鎖那行 102 字元超 line-length 100。
複查反證:同檔 L71/72/74/75 既有行(CJK 註解)本來就 >100、E501 沒開、
repo 慣例明文「不順手重排既存格式」—— 這行跟檔案現況一致,動它才是額外 churn。
參考用,不建議改。
```

## Opus 原始 findings(first-pass, context-aware)

### Chunk 1(python-reviewer;20 檔,含後端 4 + 前端 7 + 產物 6 + 狀態機/hub 測試)

逐檔 accounting:findings 於 replay_2426.py / plan.md / signal_state.py / signal_hub.py / signal_rules.py / test_signal_state.py / test_signal_hub.py;REVIEWED_NO_ISSUES ×12(含 signals_config.py 與前端全部 7 檔、fixture、round JSON、closeup 截圖、verification.md);INTENTIONALLY_SKIPPED ×1(全頁截圖,close-up 已審)。另附前端 kind-dispatch 完備性 search-proof:`kind ===` / SignalKind / RuleKind 全域掃描,四個生產讀者(toneOf / kindLabel / KIND_LABEL+ruleSummary / PARAM_FIELDS)全數更新,useSignalAlerts 零 kind 分支。

- c1-F-01 MEDIUM signal_state.py 532-537:post-fire 重武裝 O(k) 窗掃描 × 全 slot(→ 總覽 #2)
- c1-F-02 MEDIUM signal_state.py 509-537:S-1 安全論證不成立,V 反彈重武裝 + 峰值下移 + 近重複再發;既有兩測恰繞開(→ 總覽 #1)
- c1-F-03 MEDIUM test_signal_state.py 789-792:seam 類 docstring「唯一重武裝路徑」與類內測試矛盾(→ 總覽 #6)
- c1-F-04 LOW signal_state.py 3:模組 docstring 四類(→ 總覽 #11)
- c1-F-05 LOW signal_rules.py 301(+hub 1096-1098 + hub 測試 2008):「恆走缺鍵」機制錯(→ 總覽 #7)
- c1-F-06 LOW signal_rules.py 270-292:_seed_params 缺 branch 留 {} 陷阱 + 手抄 clamp(→ 總覽 #8)
- c1-F-07 LOW signal_state.py 515-518:0 價 guard 宣稱過寬(→ 總覽 #9)
- c1-F-08 LOW evidence/replay_2426.py 15-25:不可重跑(→ 總覽 #12)
- c1-F-09 LOW signal_rules.py 421:版本 tuple 符號+字面混排(→ 總覽 #10)
- c1-F-10 LOW plan.md 27-28:plan 與 signals_config 矛盾(→ 總覽 #13)

Chunk 1 verdict:無 CRITICAL/HIGH;遷移鏈 / MAX_RULES 交互 / 撞名跳過 vs normalize 撞名 raise / per-rule config 隔離 / 前端四向 parity 判定全部正確。

### Chunk 2(python-reviewer;契約與遷移測試 2 檔)

逐檔 accounting:test_signal_rules.py → c2-F-01/03/04/05/06;test_signal_routes.py → c2-F-02。並肯定:`test_v2_empty_file_still_gets_seeds` + `test_v3_file_never_reseeded` 釘住「空陣列 ≠ 缺檔改為版本域語意」這個真正新且易錯的點;`test_pullback_seed_cards_pinned_to_names`(cfg pullback_pct=9.9 誘餌)與 MAX_RULES 29/30 對非空洞。

- c2-F-01 MEDIUM test_signal_rules.py 658:id 撞既有斷言恆真、去重迴圈零覆蓋(→ 總覽 #4)
- c2-F-02 MEDIUM test_signal_routes.py 47-59:_RULE_PARAMS 漏 kind、REST 鏈零覆蓋(→ 總覽 #3)
- c2-F-03 MEDIUM test_signal_rules.py 630-715:遷移 log/WARNING 未測、v1 前例不對稱(→ 總覽 #5)
- c2-F-04 LOW test_signal_rules.py 363/381/413:by_kind 塌卡(→ 總覽 #14)
- c2-F-05 LOW test_signal_rules.py 535-539 vs 638-642:_write 複製 + 類/測名漂(→ 總覽 #15)
- c2-F-06 LOW test_signal_rules.py 61:102 字元(→ 總覽 #16)

Chunk 2 verdict:Warning;測試衛生其餘良好(tmp_path 隔離、pytest 原生、無 unittest.mock、字面鎖更新屬刻意契約改動)。

## 同軸替代驗證(主 session 逐條核)

無 Codex / Gemini 軸可跑 cross-axis;主 session 對 16 條逐條做機制核實(等同 4.2 的踢館測試,但同軸):

| # | verdict | 證據 |
| --- | --- | --- |
| 1 | CONFIRMED | 主 session 對 `_eval_pullback` 逐行 trace:基線 = 首筆 `ts >= fired_at`(= fire tick 在窗內時恆為發訊價);反彈 +2.00% 未過前高 → `price > peak` False → surge 分支重武裝、peak 改寫為現價(下移);兩條既有測試參數(單邊跌 / +0.99% 反彈)恰不觸發 |
| 2 | CONFIRMED | `_window_change_pct` 為線性迴圈;`on_tick` 對 `self._slots.values()` 全量 evaluate、狀態推進先於 enabled gate → 6 slot 全跑屬實;上界受 300s 窗自然衰減 |
| 3 | CONFIRMED | 主 session 實跑 `grep -n "surge_pullback" tests/server/test_signal_routes.py`(worktree cwd)→ 僅 47/51/52 三行(_SEEDED_KINDS 字面),`sed -n '/_RULE_PARAMS/,/^}/p'` 印出四鍵表無 surge_pullback;同 PR test_signal_hub.py:55 姊妹表有加 |
| 4 | CONFIRMED | `load_rules` 對重複 id `raise _bad()`(signal_rules.py 437-439)→ 回傳集斷言不可能失敗 |
| 5 | CONFIRMED | grep caplog 全檔僅 TestMigrationV1ToV2 四處 |
| 6 | CONFIRMED | 逐字對照類 docstring 與 test_fresh_surge_after_fire_rearms_without_new_high |
| 7 | CONFIRMED | `_legacy_flags`:`dict.fromkeys(SWITCH_KEYS, True)` + 逐鍵讀檔覆蓋 → 鍵恆在、檔案可關 |
| 8 | CONFIRMED | `_seed_params` 無 branch;唯一 caller `default_rules` 顯式繞開 |
| 9 | CONFIRMED | `evaluate` L253-261:窗 append 在任何價格 gate 前;`base <= 0 → None` 熄武裝;屬既有盲點的宣稱過寬 |
| 10 | CONFIRMED | 字面 `(_CACHE_VERSION, 2, 1)`;遷移觸發條件另寫 `version != _CACHE_VERSION` + `version == 1` |
| 11 | CONFIRMED | 逐字 |
| 12 | CONFIRMED | PR 檔案清單(gh files)無 bars_2426.json;硬編路徑之 worktree 已於收尾刪除 |
| 13 | CONFIRMED | plan.md #6「configs/signals.json 可覆寫」 vs signals_config.py「覆寫本鍵沒有任何效果」;後者與 rule_config 實作一致 |
| 14 | PARTIAL | 塌卡屬實;但兩卡 cooldown/enabled 由 `_seed_cooldown`/同一 legacy flag 同源恆同值 → 現況零遮蔽,價值在防未來每卡獨立值 |
| 15 | CONFIRMED | 逐字複製;類名/測名與內容漂移屬實 |
| 16 | REFUTED | baseline 反證:主 session 實跑 `awk 'length > 100 {print NR" len="length}' tests/test_signal_rules.py` → L61 len=102(新行)與 L71/72/74/75 len=105/103/114/101(既有 CJK 註解行);E501 未啟用、repo 慣例「不順手重排既存格式」→ 與現況一致非缺陷 |

## Action Items

### Must Fix(合併前必修)

無 —— 全場無 CRITICAL/HIGH;無任何一條同時滿足「user-visible 重現路徑 + 不修就壞會出貨的東西」雙半條件(F-01 有具體重現路徑但屬「多發一則近重複訊號」的雜訊面,且 60s 冷卻部分緩解、語意要 user 再拍板,列 Should)。PR 已 merge,本報告為出貨後 review。

### Should Fix(強烈建議)

- **#1** S-1 重武裝基線語意(V 反彈近重複再發 + docstring 安全論證不成立)—— 這條同時改寫「追認點」的內容:PR 說明請你追認的 S-1 敘述其中「不可能連發」半句是錯的,追認前先看這條。
- **#2** 已發態 O(k) 窗掃描 → O(1) 等價改寫(熱路徑紀律)。
- **#3** routes 測試 `_RULE_PARAMS` 補 kind + REST round-trip(唯一使用者會新增的新 kind 的 wire 鏈)。

### Nice to Have(可選優化)

#4 撞 id 測試改實(遷移去重迴圈覆蓋)、#5 遷移 log 斷言、#6 seam docstring 兩條路、#7 恆走缺鍵註解、#8 _seed_params branch、#9 0 價措辭、#10 版本白名單推導、#11 模組 docstring 五類、#12 evidence 可重現(ask-user)、#13 plan 死旋鈕半句、#14 by_kind → by_name、#15 _write 單源 + 改名。

**修法假設核**:各條建議修法屬方向性、除下列外未實跑驗證,落地照常走紅先行 —— #2 的 O(1) 等價性由主 session 推導並標出唯一分歧點(凍結時鐘下同 mono 時戳 tie);#3 沿用同檔既有 `_rule_body` / `BootedClient` 模式(grep 驗證兩者都在該檔);#4 的 monkeypatch `signal_rules.time.time` 寫法沿 repo pytest 慣例(conftest monkeypatch 基建既有);#10 的 `range(1, _CACHE_VERSION + 1)` 為純 stdlib 推導無 API 假設;其餘(#5 caplog / #6-#9、#11、#13-#15 註解與測試重排)均為未確認的建議寫法。

### 參考用

- **#16** 102 字元行:REFUTED —— 同檔既有 >100 行多處、慣例不重排既有格式;非 PR 缺陷,不建議動。

## 審查工具比較(qualitative)

- 本輪為 CC 單軸(chunk ×2)+ 主 session 同軸替代驗證;無 cross-axis 對照,重疊率 / REFUTED 率等跨軸統計不適用。
- Chunk 1(狀態機 + 契約 + 前端)最有價值的一條是 #1:對 shipped docstring 的安全論證做了機制反例(具體價格序列),並指出兩條既有測試恰好繞開該 case —— 這是「測試綠 ≠ 論證成立」的教科書案例,也直接修正了 PR 留給 user 的追認內容。
- Chunk 2(契約測試)抓到 #3/#4 兩條「斷言存在但護不住」型 finding(恆真斷言、姊妹表漏更新),與 repo 突變體驗證傳統同一路數。
- 主 session 複查貢獻:#16 的 baseline 反證(唯一 REFUTED)、#14 降 PARTIAL(同源恆同值)、#1 的完整數值 trace。

## 沒做的部分(結案對帳)

- Codex 中性軸:FAIL —— `codex` CLI 本機不存在,無法跑。
- Codex 對抗軸:FAIL —— 同上;preset 詢問一併略過(無意義)。
- Gemini Flash 軸:FAIL —— `agy` CLI 本機不存在(永久軸缺軸)。
- Gemini Pro 軸:N-A —— opt-in 未啟用且 CLI 不存在;無人值守走預設不加 Pro。
- Cross-axis verification(4.1/4.2):FAIL → 以主 session 同軸逐條機制核實替代(16/16 條各有 verdict + 證據;非獨立軸,信度低於真 cross-axis,已在總覽逐條標注)。
- sem blast radius:空輸出跳過(sem CLI 未安裝)。
- C4 spec-compliance:N-A(gate SKIPPED,C4_NO_NORMATIVE_AUTHORITY)。
- Quota snapshot:未取(Gemini 軸未跑)。
- 未驗證前提:#2 的「一 tick 幾百格」為活躍檔量級估計(未實測本機 tick 密度;機制與上界已核,量級不影響 verdict);#12 的「evidence 大小取捨」未量測 bars_2426.json 實際大小(~數十 KB 級估計)。
- 盤中實發觀察(issue #174 驗證判準之一):未做 —— 需交易時段,屬 user 盤中過目項(verification.md 已列)。
- **Self-Verify 修正紀錄**(auditor VERDICT: VIOLATIONS: R3,R4,R5,R6,R8,R9;修正後未重派 —— **未經第二次獨立稽查**):R3 → header 補 skipped 檔名(全頁截圖)與理由;R4 → Spec 依據補「SKIPPED 下無 reducer projection、invalidated 空集合恆成立、報告零 C4 引用」說明;R6 → 缺軸主張補 `Get-Command` 第一手證據、#3/#16 複查欄補實跑指令字串;R8 → Action Items 補「修法假設核」段(逐條標已驗 / 未確認);R5/R9 → 非缺口:canonical uid 16 行、16 個 inline blocks、22 列變更概要表在本正式 draft 原本就存在,auditor 收到的是嵌入版摘要所致(依 rubric 從嚴照判,此處據實回應)。
- 其餘:無。
