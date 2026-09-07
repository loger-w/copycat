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
## [完整證據副檔](pr-177-review.audit.md)
### finding_uid 索引
[74477215207a243b9ff1](pr-177-review.audit.md#發現總覽) · [2e031a143c55425824f6](pr-177-review.audit.md#發現總覽) · [3325cc2414e97bd74c48](pr-177-review.audit.md#發現總覽) · [c94da4efeb14b31d805c](pr-177-review.audit.md#發現總覽) · [4554c6780743ad78cd32](pr-177-review.audit.md#發現總覽) · [9164d9c2766895ea950a](pr-177-review.audit.md#發現總覽) · [2b9002af9d2e3f33bec9](pr-177-review.audit.md#發現總覽) · [c7572570b3f85f5c0735](pr-177-review.audit.md#發現總覽) · [5d0b56de3fecb0c9e9da](pr-177-review.audit.md#發現總覽) · [dd2212e64ddc1f935884](pr-177-review.audit.md#發現總覽) · [5be31ad0ea010480d1da](pr-177-review.audit.md#發現總覽) · [58c674d23c7920348cdf](pr-177-review.audit.md#發現總覽) · [042c65a7c57b5b25aa43](pr-177-review.audit.md#發現總覽) · [5287984c8077226dbc51](pr-177-review.audit.md#發現總覽) · [43e4e753bfdb16715d4e](pr-177-review.audit.md#發現總覽) · [6429121c0d56f108449f](pr-177-review.audit.md#發現總覽)
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
