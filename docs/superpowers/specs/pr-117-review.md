# PR #117 Code Review 比較報告 · SHA d9afb37d
**Report projection schema**: 1

**PR**: [loger-w/copycat#117](https://github.com/loger-w/copycat/pull/117)
**標題**: refactor(test): corr / river route 測試腿集合改讀 correlation.json(F-20)
**作者**: loger-w(commits 署名 Loger)
**分支**: `refactor/f20-corr-leg-keys-from-config` → `master`(PR 狀態 MERGED,rebase merge 進 master 為 733d772e;回溯 review)
**變更**: 6 檔案, +61 / -56
**審查日期**: 2026-08-27
**Review input basis**: source repo R_kgDOTsITBg + d9afb37d59231f6bc4426fcc0472e1ce7dae75a8;destination repo R_kgDOTsITBg + 314a8f2f66a1404f588166b404ce2f64a19594f1;`input_binding: verified`(worktree HEAD = source SHA,`git fetch refs/pull/117/head` 後 rev-parse 逐字相等;destination SHA 為 master 歷史上的既有 commit)
**Review continuity**: `source_continuity=CURRENT`;`base_changed=false`(產報告前重抓 headRefOid / baseRefOid 與 reviewed 完全相同;PR 已 MERGED);`review_context_changed=false`
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-117`(detached)
**worktree HEAD**: d9afb37d59231f6bc4426fcc0472e1ce7dae75a8
**審查工具**: CC (claude-fable-5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 N-A(本機無 codex CLI)+ Codex 對抗式 N-A(同上)+ Cross-axis verification(4.1 N-A 無非 CC finding;4.2 Codex 驗 CC first-pass N-A → 全部 INCONCLUSIVE,改由 4.3b 判斷式複查)+ Gemini 軸 N-A(本機無 agy;Flash / Pro 皆未啟動)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary reviewer=python-reviewer ×1(源碼變更 3 檔皆 .py,100% 主導;dispatch 顯式 model=opus、effort 依 frontmatter;observed=UNAVAILABLE —— Agent tool 回傳無 runtime model 欄位);domain reviewers=無(security-reviewer 未觸發);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(gate SKIPPED,未派);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=6 → covered 5 / no-issues 1 / skipped 0 / **missed 0**(chunked: 否;FILE_COUNT=3 源檔、DIFF_LINES=117 皆低於門檻;covered = `tests/helpers/corr_legs.py` / `tests/server/test_corr_routes.py` / `tests/server/test_river_routes.py` / `.claude/refactor/f20-corr-leg-keys-from-config/verification.md` / `.claude/refactor/f20-corr-leg-keys-from-config/code-review-round-1.json`;no-issues = `docs/next-time.md`)
**定位 (ENH-B)**: anchored exact 6 / ambiguous 0 / **FAILED 0**(六條 anchor 皆於 worktree HEAD 唯一比中:test_corr_routes.py:17 / test_river_routes.py:17 / verification.md:4 / :16 / corr_legs.py:11 / code-review-round-1.json:8)
**React-doctor (2.97)**: N-A(非 React PR:F 無 .jsx / .tsx)
**Formal spec traceability (2.65)**: SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED)
**Blast radius (2.9)**: 空輸出跳過(本機無 `sem`,`sem-pr-blast-radius.sh` exit 0 零輸出)
**Gemini 軸**: 按預設只跑 Flash —— 但本機無 `agy`,Flash 軸實際未啟動(N-A);因工具缺席 Step 2.96 未向 user 提問
**Codex preset**: 按預設 default —— 但本機無 `codex`,中性 / 對抗兩軸實際未啟動(N-A);因工具缺席 Step 2.98 未向 user 提問
**校準套用**: 無作者校準檔(loger-w.md 不存在;`docs/pr-review-calibration/` 目錄亦不存在)、本輪無套用
**Provenance (2.55)**: N-A(base = master,6 檔全部 authored)
**審查軸狀態**: primary(python-reviewer)PASS(6 findings、6/6 accounting;另代跑全套 pytest 3096 passed / pyright 0 / ruff clean 於 PR head);domain(security-reviewer)N-A 未觸發;spec-compliance-reviewer N-A(gate SKIPPED);Codex 中性 N-A(無 CLI);Codex 對抗 N-A(無 CLI);Gemini Flash N-A(無 agy);Gemini Pro N-A(未啟用且無 agy);cross-axis verification 4.1 N-A(無非 CC finding)/ 4.2 FAIL→INCONCLUSIVE(無 codex,全部 CC finding 無交叉驗證)/ 4.3b PASS(主 agent 逐條判斷式複查,見備註欄);React-doctor N-A(非 React PR)
**Self-Verify**: auditor(skill-verify-auditor,model=opus)回 R1–R3 / R7–R10 PASS、R4 / R5 / R6 FAIL;主 agent 依現有 reviewer 產物補寫(見「沒做的部分」),**未經第二次獨立稽查**

**Report generation**: sha256:0289d5b7183d0438bebde4b21f55b26a346855e8d3c7f88fac49b1b68ecd0f6d

---
## [完整證據副檔](pr-117-review.audit.md)
### finding_uid 索引
[2801e7a464d18f4731b0](pr-117-review.audit.md#發現總覽) · [1b7faf03b6de32049ad2](pr-117-review.audit.md#發現總覽) · [be625f055f0679b2dcb0](pr-117-review.audit.md#發現總覽) · [20bfa710a6716d6b0571](pr-117-review.audit.md#發現總覽) · [e3b72800dd83d8037036](pr-117-review.audit.md#發現總覽) · [8581c5a7538a02370bc5](pr-117-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | Opus | Cdx-N | Cdx-A | Gem-F | Opus 複查(非 Opus 軸) | 最終建議 | Action | Action 理由 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F-01 | import 區與 `_client` 之間多出第三個空行(E303),ruff 預設規則集抓不到(`tests/server/test_corr_routes.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 刪一個空行 |
| F-02 | 同 F-01:三個空行(`tests/server/test_river_routes.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 與 F-01 一併刪 |
| F-03 | verification「改動」段停在 review 收修前的形狀:寫 `_LEG_KEYS` / `_PAIR_KEYS`、未列新檔 `tests/helpers/corr_legs.py`(`.claude/refactor/f20-corr-leg-keys-from-config/verification.md`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 補成最終形狀兩行 |
| F-04 | 自行豁免全套 pytest / validate,豁免理由不涵蓋新增 import 期讀檔 helper 的收集面風險(`.claude/refactor/f20-corr-leg-keys-from-config/verification.md`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `no-op` | reviewer 已於 PR head 代跑全套 3096 passed / pyright 0 閉環;紀律面提醒,無後續動作 |
| F-05 | 共用 helper 匯出名 `CFG` 過泛,use site 讀不出是哪份 config(`tests/helpers/corr_legs.py`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | 改名 `CORR_CFG`,兩個 import 端同步 |
| F-06 | spec 軸 finding id 取名 `P1`,與 severity 值域 P1/P2/P3 撞名,disposition「無 P1 / P2」自相矛盾(`.claude/refactor/f20-corr-leg-keys-from-config/code-review-round-1.json`) | LOW [python-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b 見備註 | Nice to Have | `auto-fix` | id 改 `SP1`(repo 主流前綴) |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 2801e7a464d18f4731b0 action=auto-fix
F-02 finding_uid: 1b7faf03b6de32049ad2 action=auto-fix
F-03 finding_uid: be625f055f0679b2dcb0 action=auto-fix
F-04 finding_uid: 20bfa710a6716d6b0571 action=no-op
F-05 finding_uid: e3b72800dd83d8037036 action=auto-fix
F-06 finding_uid: 8581c5a7538a02370bc5 action=auto-fix
### Inline Comments per Finding（直接複製貼到 PR review）
#### F-01 import 區跟 `_client` 之間多了一個空行
**File**: `tests/server/test_corr_routes.py`
**Line**: 17

**Comment**:
```
新加那行 import 順手多留了一個空行,import 區到 `def _client` 變成 3 行空白(PEP 8 / ruff format 是 2)。
專案 ruff 用預設規則集,E303 不在裡面,所以 gate 恆綠。刪一個空行就好;
`ruff format tests/server/test_corr_routes.py` 也會幫你收。
```
#### F-02 同上,river 那檔也多一個空行
**File**: `tests/server/test_river_routes.py`
**Line**: 17

**Comment**:
```
跟 test_corr_routes.py 同一批複製過來的,import 區到 `def _client` 也是 3 行空白。一併刪掉一行。
```
#### F-03 verification 的「改動」段寫的是收修前的樣子
**File**: `.claude/refactor/f20-corr-leg-keys-from-config/verification.md`
**Line**: 4-5

**Comment**:
```
這兩行講的是 61ca1373 那版(每檔各持 `_LEG_KEYS` / `_PAIR_KEYS`),但出貨的 head 是 S3 收修後 ——
常數搬到新檔 `tests/helpers/corr_legs.py`,名字是 `CFG` / `LEG_KEYS` / `PAIR_KEYS`(沒底線)。
現在 grep `_LEG_KEYS` 全 tests 零命中,檔數也對不上 `git diff --stat` 的 6 檔(含 1 新檔)。

補一句「S3 收修:常數上收 `tests/helpers/corr_legs.py`,匯出 `CFG` / `LEG_KEYS` / `PAIR_KEYS`,兩個 route 測試改 import」即可。
```
#### F-05 共用 helper 匯出 `CFG` 這個名字太泛
**File**: `tests/helpers/corr_legs.py`
**Line**: 11

**Comment**:
```
從共用 helper 匯出後,呼叫端只看得到 `from tests.helpers.corr_legs import CFG` 跟 `len(CFG.tc4_legs())`,
名字本身不帶 corr。repo 內其他 `CFG`(backtest / engine 測試)都是模組私有、沒跨檔匯出。
改成 `CORR_CFG`,跟同檔的 `LEG_KEYS` / `PAIR_KEYS` 一樣自帶領域字;兩個 import 端一起改。
```
#### F-06 review json 裡 spec 軸的 id 叫 `P1`,跟 severity 的 P1 撞名
**File**: `.claude/refactor/f20-corr-leg-keys-from-config/code-review-round-1.json`
**Line**: 8-11

**Comment**:
```
spec 陣列唯一一筆 id 是 "P1"(severity 是 "P3"),而 disposition 寫「S1 / S2 / P1 → 收修 …。無 P1 / P2。」——
前一個 P1 是 finding id、後一個是 severity,同一份 JSON 讀起來像「收修了 P1 又說沒有 P1」。
全 repo 121 份 round json 的 spec 軸主流前綴是 SP*(65 vs 12),改成 "SP1" 就消掉撞名。
```
