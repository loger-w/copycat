# PR #130 Code Review 比較報告 · SHA 2774d739
**Report projection schema**: 1

**PR**: [loger-w/copycat#130](https://github.com/loger-w/copycat/pull/130)
**標題**: fix(corr): pr-120 五條收修 —— sparse 非 bool WARNING、_default_corr_source config 必填(keyword-only)、§4 誤標症狀改對、反向驗證 mutation 級
**作者**: loger-w(commits 署名 Loger)
**分支**: `fix/sparse-review-followups` → `master`(PR 狀態 MERGED,rebase merge 進 master 為 a8cacf72;回溯 review)
**變更**: 10 檔案, +185 / -24
**審查日期**: 2026-08-27
**Review input basis**: source repo R_kgDOTsITBg + 2774d739c2012e2ec8156794ac0fa3372f119186;destination repo R_kgDOTsITBg + 4472231080a6cb64cadebe52ca102900068630cb;`input_binding: verified`(`git fetch refs/pull/130/head` 後 FETCH_HEAD 與 headRefOid 逐字相等、worktree HEAD = source SHA;destination SHA 為 master 歷史上的既有 commit,`git merge-base --is-ancestor` 成立)
**Review continuity**: `source_continuity=CURRENT`;`base_changed=false`(產報告前重抓 headRefOid / baseRefOid 與 reviewed 完全相同;PR 已 MERGED);`review_context_changed=false`
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-130`(detached)
**worktree HEAD**: 2774d739c2012e2ec8156794ac0fa3372f119186
**審查工具**: CC (claude-fable-5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 N-A(本機無 codex CLI)+ Codex 對抗式 N-A(同上)+ Cross-axis verification(4.1 N-A 無非 CC finding;4.2 Codex 驗 CC first-pass N-A → 全部 INCONCLUSIVE,改由 4.3b 主 agent 判斷式複查)+ Gemini 軸 N-A(本機無 agy;Flash / Pro 皆未啟動)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary reviewers=python-reviewer(不切塊,單一 dispatch;dispatch 顯式 model=opus、effort 依 frontmatter;observed=UNAVAILABLE —— Agent tool 回傳無 runtime model 欄位);domain reviewers=無(security-reviewer 未觸發:無 auth / request-body / secret 路徑);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(gate SKIPPED,未派);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=10 → covered 7 / no-issues 3 / skipped 0 / **missed 0**(chunked: 否;FILE_COUNT=5 源檔 ≤ 15、DIFF_LINES=209 < 800;reviewer 逐檔 accounting 10/10,union = F)
**定位 (ENH-B)**: anchored exact 8 / ambiguous 0 / **FAILED 0**(全部 anchor 於 worktree HEAD 以 grep 逐字比中,line 以比中結果為準)
**React-doctor (2.97)**: N-A(非 React PR:F 無前端檔)
**Formal spec traceability (2.65)**: SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED)
**Blast radius (2.9)**: 空輸出跳過(本機無 `sem`,`sem-pr-blast-radius.sh` exit 0 零輸出)
**Gemini 軸**: 按預設只跑 Flash —— 但本機無 `agy`,Flash 軸實際未啟動(N-A);因工具缺席 Step 2.96 未向 user 提問
**Codex preset**: 按預設 default —— 但本機無 `codex`,中性 / 對抗兩軸實際未啟動(N-A);因工具缺席 Step 2.98 未向 user 提問
**校準套用**: 無作者校準檔(loger-w.md 不存在;`docs/pr-review-calibration/` 目錄亦不存在)、本輪無套用
**Provenance (2.55)**: N-A(base = master,10 檔全部 authored)
**審查軸狀態**: primary(python-reviewer)PASS(8 findings、10/10 accounting);domain(security-reviewer)N-A 未觸發;spec-compliance-reviewer N-A(gate SKIPPED);Codex 中性 N-A(無 CLI);Codex 對抗 N-A(無 CLI);Gemini Flash N-A(無 agy);Gemini Pro N-A(未啟用且無 agy);cross-axis verification 4.1 N-A(無非 CC finding)/ 4.2 FAIL→INCONCLUSIVE(無 codex,全部 CC finding 無交叉驗證)/ 4.3b PASS(主 agent 逐條實查,見備註欄;F-02 PARTIAL);React-doctor N-A(非 React PR)
**Self-Verify**: auditor(skill-verify-auditor,dispatch model=opus)回 R1–R10 全 PASS、`VERDICT: COMPLIANT`;無需補寫

**Report generation**: sha256:facf80003c92101fcf55aa79566b114598a5c4ee803cc191b2b12595c2bd239c

---
## [完整證據副檔](pr-130-review.audit.md)
### finding_uid 索引
[47c6ec0e03f79d3893b1](pr-130-review.audit.md#發現總覽) · [a307be5489befb1e7891](pr-130-review.audit.md#發現總覽) · [d4dc6b6468088ea07bdf](pr-130-review.audit.md#發現總覽) · [5a691402bc2230165bf8](pr-130-review.audit.md#發現總覽) · [9c76bd72221d6ee2f279](pr-130-review.audit.md#發現總覽) · [31c9d430acd49bdc4202](pr-130-review.audit.md#發現總覽) · [90cfe2db43285078fdc7](pr-130-review.audit.md#發現總覽) · [1be4a01ea44989eb1b80](pr-130-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | Opus | Cdx-N | Cdx-A | Gem-F | Opus 複查(非 Opus 軸) | 最終建議 | Action | Action 理由 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F-01 | sparse WARNING 在 `_parse_legs` 迭代中即時印,但後面任一腿缺必要欄 / base 不在 legs 時整份設定檔被丟棄改用 `DEFAULT_CONFIG`(:121-137 五處 return):log 先出「NQ 的 sparse 非 true/false 旗標無效」再出「改用預設腿」,前者語意是「只掉這面旗」、實際整份沒生效 —— 本 PR 的立意是「不靠事後 grep log 猜」,這裡多了一種誤導組合(`copycat/corr_config.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent grep `return DEFAULT_CONFIG` → :121 / :126 / :129 / :133 / :137,`_parse_legs` 在 :130 之前印;蒐集成 list 延後到 load_config 採用後再印,或註明「可能先於降級印出」 |
| F-02 | 生產碼註解掛本分支 in-flight review 編號 `(review S-1)` / `(review S-3)`,指向的 `code-review-round-1.json` 檔名不在註解裡,讀者拿「S-1」無處可查;WHY 本身已寫完整,尾綴是過程敘事(baseline Quality-8)(`copycat/server/app.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b PARTIAL | Nice to Have | `auto-fix` | 主 agent grep `review S-` copycat/ → 除本 PR 兩處外,`copycat/server/verify.py:204` **早有**同型 `(review S-1)` 尾綴 —— reviewer「只有本 PR 新增兩處」不成立,慣例並非零先例;可讀性點仍在,刪尾綴或改成可解析路徑 |
| F-03 | verification §3「型別守住不變量」過度陳述:突變證的是「漏傳 config → pyright 紅」= 必須傳;「與 engine 同一份」在 `_make_corr` 仍靠同一個區域變數 `corr_cfg` 分別餵兩處,改成 `config=load_corr_config()` 或 `DEFAULT_CONFIG` 型別 / 測試全綠;app.py:410-411 註解措辭準確,只有這格收尾詞說成「守住」(`.claude/bug/sparse-review-followups/verification.md`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent 讀 app.py lifespan:`corr_cfg` 兩處各自傳入無機制綁定;一格改寫成「型別守住『必須傳』;『同一份』仍由單一區域變數保證」 |
| F-04 | 事故記錄引的 `2e31a9bc`(突變體被 commit 的那筆)在 `reset --soft` 後不在任何 ref 祖先鏈上(`merge-base --is-ancestor` 非祖先,物件只存本機 reflog);push 到 GitHub 的分支沒有它,clone 後 `git show` unknown revision —— 最該可覆核的一條事故變成不可驗證的自述(`.claude/bug/sparse-review-followups/verification.md`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent `merge-base --is-ancestor 2e31a9bc HEAD` → not ancestor;註明「已被 reset --soft 丟棄、僅存本機 reflog」或貼當時 `git show HEAD:` 的差異片段 |
| F-05 | 三條與 sparse 無關的 wiring 測試(`always_on_session_gate` / `leg_gate_only_taifex` / `tws_leg_gate_ands_calendar`)只斷言 `heal_symbol_active`,而 `segment_leg_gate` 依 symbol 前綴建、不讀 config,卻各自 `load_config()` 讀真檔 `configs/correlation.json`(user 手改檔)只為滿足簽名:非 hermetic + 四處 inline import 樣板;同檔 :512-515 已有自建 `CorrConfig` 寫法、`tests/helpers/corr_legs.py::CFG` 是既有共用出口(`tests/server/test_main_wiring.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent 確認 `tests/helpers/corr_legs.py:11 CFG = load_config(CONFIG_PATH)` 存在、`segment_leg_gate` 本體零 `config` 引用;三條改傳 `DEFAULT_CONFIG`(:504 已 import)或 helper CFG |
| F-06 | 同一份 verification 內「三條」(§1:23、§5 開頭)與「4 passed」並存:`TestHealSparseSymbol` 現為四條(第四條 `r1_takes_over…` 是 PR #120 review 追加),四條都在建構子帶 `heal_sparse_symbols=` → 今天照原版 stash 手法重跑會是 4 failed,不是三條(`.claude/bug/corr-sparse-leg-heal-exempt/verification.md`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent awk 計 `def test_` → 4;§1:23 仍寫三條;補「當時 3 條、review 追加後 4 條」一句 |
| F-07 | 新訊號(sparse 打成 `"true"` / `1` / `null` 無效並 WARNING)寫進 §4 與 Python 註解,卻沒寫進使用者真正手改的 `configs/correlation.json` `_comment` —— 該 `_comment` 已是 sparse 操作說明書(含 base 腿 WARNING 與漏標症狀),本 PR 未動該檔(`CLAUDE.md`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent grep correlation.json `_comment`:有「選配 `sparse: true`…」與 base 腿 WARNING,無值型別一句;diff --stat 未含該檔;補一子句 |
| F-08 | 白名單第 1 條字面把判準寫死成 `[False, True, False, False, False]` 斷言保留,review S-4 後測試多了 null 腿、斷言變六元素(`test_corr_config.py:139`);行為白名單實質未破(原五腿逐字不變,verification §4.1 已寫六元素),但條文字面不成立、「4/4 PASS」靠讀者心算(`.claude/bug/sparse-review-followups/change-spec.md`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent grep 兩檔 → change-spec:27 五元素、test:139 六元素;條文改不綁長度措辭或 verification 明寫「5 → 6,前五格逐字相同」 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 47c6ec0e03f79d3893b1 action=auto-fix
F-02 finding_uid: a307be5489befb1e7891 action=auto-fix
F-03 finding_uid: d4dc6b6468088ea07bdf action=auto-fix
F-04 finding_uid: 5a691402bc2230165bf8 action=auto-fix
F-05 finding_uid: 9c76bd72221d6ee2f279 action=auto-fix
F-06 finding_uid: 31c9d430acd49bdc4202 action=auto-fix
F-07 finding_uid: 90cfe2db43285078fdc7 action=auto-fix
F-08 finding_uid: 1be4a01ea44989eb1b80 action=auto-fix
### Inline Comments per Finding（直接複製貼到 PR review）
#### F-01 sparse 那行 WARNING 先印、整份設定檔隨後被丟掉,兩行 log 併看會指錯方向
**File**: `copycat/corr_config.py`
**Line**: 101-108

**Comment**:
```
_parse_legs 是逐筆迭代、警告在迴圈裡即時印;但只要後面任一腿缺必要欄就 return None(:98-99),
load_config 接著印「legs 欄格式錯誤,改用預設腿」回 DEFAULT_CONFIG(:130-133);base 不在 legs 同理(:135-137)。
這時 log 先出「NQ 的 sparse 非 true/false…旗標無效」再出「改用預設腿」—— 前者語意是「只掉這面旗」,
實際整份檔案都沒生效、跑的是 DEFAULT_CONFIG(裡面 SXF 的 sparse=True 反而是好的)。
這輪的立意是「不要靠事後 grep log 猜」,這裡多了一種會誤導的組合。

把壞旗標蒐集成 list 回傳(或區域變數),等 load_config 過完 legs / base 兩道降級檢查、確定採用這份 config 之後再 warning;
或退一步在註解註明「本警告可能先於降級印出」。既有的降級測試(:185 / :191)都沒帶壞 sparse 的組合,順手補一條。
```
#### F-02 生產碼註解掛的「review S-1 / S-3」,六個月後沒人查得到
**File**: `copycat/server/app.py`
**Line**: 412

**Comment**:
```
這兩處(app.py:412、corr_config.py:105)的 WHY 已經寫完整了(keyword-only 是為了讓 calendar 預設值跟四個兄弟工廠同形 /
parser 內破例 log 是因為原值不進 Leg),尾綴的 (review S-1) / (review S-3) 指向 .claude/bug/sparse-review-followups/
code-review-round-1.json,檔名不在註解裡,讀者拿著「S-1」無處可查。repo 慣例是掛耐久編號(N051 / pr-120 F-02 / design review P1-1)。
不過 verify.py:204 早就有一個同型的 (review S-1),所以不是零先例 —— 可讀性的點還是成立。

尾綴刪掉,或改寫成可解析路徑(.claude/bug/sparse-review-followups/code-review-round-1.json S-1)。
```
#### F-03 「型別守住不變量」講過頭了,型別守到的是「有傳 config」不是「跟 engine 同一份」
**File**: `.claude/bug/sparse-review-followups/verification.md`
**Line**: 27

**Comment**:
```
突變證的是「prod caller 漏傳 config → pyright 1 error」,只證明必須傳。真正的不變量(source 的稀疏腿集合跟
CorrelationEngine(config=) 吃同一份)在 _make_corr 裡還是靠人眼:把 config=corr_cfg 改成 config=load_corr_config()
(第二次讀檔)或 DEFAULT_CONFIG,型別、pyright、測試全綠。app.py:410-411 的註解措辭是準的(「不留 fallback 讓『各讀各的』
在結構上合法」),只有這一格 verification 的收尾詞說成「守住」。下一輪 handoff 會拿它當「不變量已機械化」的依據。

改成「型別守住『必須傳 config』(漏傳即 pyright 紅);『與 engine 同一份』仍由 _make_corr 單一區域變數保證,無型別守門」。
```
#### F-04 事故記錄引的 2e31a9bc 在 PR 歷史上不可達,別人覆核不了
**File**: `.claude/bug/sparse-review-followups/verification.md`
**Line**: 31

**Comment**:
```
這條事故正是「突變體差點被 commit 進去」—— 最該留可覆核證據的一條。但 reset --soft 之後 2e31a9bc 不在任何 ref 的祖先鏈上
(git merge-base --is-ancestor → 非祖先,物件只因本機 reflog 還在才 cat-file 得到);push 上去的分支沒這顆物件,
clone 後 git show 2e31a9bc 一律 unknown revision,本機 reflog 過期 gc 後作者自己也查不到。

要嘛註明「該 commit 已被 reset --soft 丟棄,SHA 僅存本機 reflog,不可覆核」,
要嘛把當時 git show HEAD:copycat/server/app.py 抓到的那段差異(_default_corr_source(trading_calendar))貼進來當證據。
```
#### F-05 三條跟 sparse 無關的測試被改成讀真檔 load_config(),沒必要
**File**: `tests/server/test_main_wiring.py`
**Line**: 489-494

**Comment**:
```
四個 caller 帶 config= 是 F-04 的正解,但 always_on_session_gate / leg_gate_only_taifex / tws_leg_gate_ands_calendar
這三條只斷言 heal_symbol_active,而 segment_leg_gate 是依 symbol 前綴建的(app.py:414-417)、完全不讀 config 內容 ——
它們拿 load_config() 只是為了滿足簽名,代價是每條都讀一次 configs/correlation.json(CLAUDE.md 明載是 user 手改檔)。
pr-120 F-04 原文也把「測試因此綁真檔」列為副作用,而另一半選項(自建 CorrConfig)同檔 :512-515 已有現成寫法。
非 hermetic + 四處 inline import 樣板 + 四次磁碟 IO;load_config never-raise,壞檔不會讓測試紅、只是白讀。

三條不看 sparse 的改傳 DEFAULT_CONFIG(:504 已 import);真要「repo 真檔那份」用既有共用出口
tests/helpers/corr_legs.py::CFG(module 級只讀一次)。
```
#### F-06 同一份 verification 裡「三條」跟「4 passed」並存,照舊手法重跑今天會是 4 failed
**File**: `.claude/bug/corr-sparse-leg-heal-exempt/verification.md`
**Line**: 48

**Comment**:
```
§5 重寫得很到位(獨立複現 2 failed / 2 passed,紅的正是點名的兩條),但開頭仍寫「原版…三條全炸在 TypeError」,
沒改的 §1(:23)也還列「三條」。TestHealSparseSymbol 現在是四條(is_exempt_from_r2 / still_rides_r1_batch_heal /
r1_takes_over_when_the_population_is_only_sparse_symbols / does_not_trigger_r1_while_another_leg_is_alive),
四條都在建構子帶 heal_sparse_symbols= —— 今天照原版 git stash push tc4.py 重跑會是 4 failed。
第四條是 PR #120 review 追加的,所以「3」只在紅先行當下成立;同段落下方又寫「還原後 4 passed」,前後數字打架。

§5 開頭補一句「當時 3 條;r1_takes_over… 為 review 追加,現為 4 條」,或把 §1 的「三條」改「(當時)三條」。
```
#### F-07 新訊號寫進 §4 了,但沒寫進使用者真正在手改的 correlation.json _comment
**File**: `CLAUDE.md`
**Line**: 268

**Comment**:
```
configs/correlation.json 的 _comment 已經是 sparse 的操作說明書,連姊妹警告都寫了(「只對 source: tc4 的腿有效
(base 腿標了無效,load_config 印 WARNING);漏標的症狀是每 240 s 一發」)。這輪新增的「打成 "true" / 1 / null 一律無效
並印 WARNING」是同一類資訊、同一個讀者(手改 JSON 的人),卻只落在 §4 跟 Python 註解 —— §4 的讀者是排查漂移的 agent,
不是正在編輯 JSON 的人;本 PR 沒動該檔。

_comment 在既有那句後面補一子句:「值只認 JSON 字面 true;打成 "true" / 1 / null 一律無效並印 WARNING 點名該腿」。
```
#### F-08 白名單第 1 條寫死五元素斷言,最終是六元素,對帳靠讀者心算
**File**: `.claude/bug/sparse-review-followups/change-spec.md`
**Line**: 27

**Comment**:
```
白名單訂「load_config 對合法 / 非法 sparse 的回傳值逐字不變」,括號把判準寫死成 [False, True, False, False, False] 斷言保留;
review S-4 之後測試多了一筆 "sparse": None 的腿,斷言變六元素(test_corr_config.py:139)。行為白名單實質沒破
(原五腿逐字未變,verification §4.1 也重述成六元素),但條文字面已經不成立 —— 白名單是自訂的收尾 gate,
判準跟現況對不上時「4/4 PASS」就得靠心算;只讀 change-spec 不讀 verification 的人會誤判被破。

條文改成不綁長度:「原五腿的 sparse 結果逐字不變;新增案只准在尾端追加」,或 verification §4.1 明寫「斷言由 5 擴為 6,前五格逐字相同」。
```
## 沒做的部分（結案對帳）
- Codex 中性 / 對抗軸:FAIL(N-A)—— 無 `codex`。Gemini Flash / Pro:FAIL(N-A)—— 無 `agy`。Step 2.96 / 2.98 提問未執行(工具缺席)。
- Step 4.1 N-A;Step 4.2 FAIL → INCONCLUSIVE,以 4.3b 主 agent 實查代之(grep / awk / merge-base)。
- sem blast radius:跑了,空輸出跳過。React-doctor N-A。C4 SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED,reducer 實跑)。
- 真實環境:本 PR 只多一條 WARNING、簽名收緊,prod 不需為此重啟;`grep 零推播自癒 | grep SXF` 全日 0 筆仍是 #120 本體的 08-28 待驗項。
- 未驗證前提:F-01 的誤導情境(壞 sparse + 後面腿缺欄同時發生)未實跑,由 code 順序推得;F-05 的「四次磁碟 IO」是讀 code 推得,未量測。
- Self-Verify:已執行,COMPLIANT(auditor 以 Read 讀取草稿檔本身,未讀其他產物)。
