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

## Spec 依據

- 此 PR 未附 spec／plan 文件,按一般 PR 流程 review。來源需求 = `/pr-review #111` 報告的 F-20 ask-user 條(`docs/superpowers/specs/pr-111-review.md`),user 08-26 拍板「改」;`.claude/refactor/f20-corr-leg-keys-from-config/{verification.md,code-review-round-1.json}` 為驗證 / review 紀錄、不當 spec 用。
- SPEC_COMPLIANCE receipt:`gate=SKIPPED`、`dispatch=NOT_APPLICABLE`、`dispatch_count=0`、`reason_code=C4_AUTHORITY_PATH_NOT_ALLOWED`(無 openspec/** 或 normative 文件候選)、`requested_model=opus`、`observed_model=UNAVAILABLE`、`effort=xhigh`、runtime tool calls=0(無)。0 clauses / 0 findings / 0 observations / 0 invalidated。
- reducer 安全投影:本 PR 無 C4 dispatch,故無 `human_projection`;報告內 C4 finding 0、observation 0、invalidated 0,不含任何 invalidated 語意;C4 相關內容只以本 receipt 呈現,未新增獨立 review axis 欄。

## 變更概要

| 檔案 | 類型 | 說明 |
| --- | --- | --- |
| `tests/helpers/corr_legs.py` | 新增(測試 helper) | `CFG = load_config(CONFIG_PATH)`、`LEG_KEYS` / `PAIR_KEYS`(frozenset,pairs = legs − base),import 期讀 `configs/correlation.json` 一次 |
| `tests/server/test_corr_routes.py` | 測試 | 兩份 11 腿字面集合 → `LEG_KEYS` / `PAIR_KEYS`;`len(src.subscribed) == 10` → `len(CFG.tc4_legs())`;docstring 不寫死腿數 |
| `tests/server/test_river_routes.py` | 測試 | 兩份字面集合 → `LEG_KEYS` / `PAIR_KEYS`;docstring 改「腿數隨設定檔」 |
| `.claude/refactor/f20-corr-leg-keys-from-config/verification.md` | docs(驗證紀錄) | gate 數字 + review 收修重跑 |
| `.claude/refactor/f20-corr-leg-keys-from-config/code-review-round-1.json` | docs(review 紀錄) | two-axis round 1:3 S + 1 P,全收修 |
| `docs/next-time.md` | docs | F-20 條勾銷 |

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

#### F-04 verification 自己豁免了全套 gate,理由沒涵蓋新加的 import 期讀檔 helper

**File**: `.claude/refactor/f20-corr-leg-keys-from-config/verification.md`
**Line**: 16

**Comment**:
```
不是 PR 缺陷、不用改 code:reviewer 已在 PR head 代跑全套 `pytest -q` 3096 passed / 3 skipped、
`pyright` 0 errors、`ruff check` clean,新 helper 的 CONFIG_PATH 走 `__file__` 絕對路徑、
檔名不符 test_*.py 不會被誤收集 —— 實害為零。
只是「diff 不碰生產碼所以跳全套」這個理由對『新增一個 import 期做檔案 IO 的共用模組』不成立,
下次 test-only 改動若真有交互作用會漏。要嘛照 CLAUDE.md §1 跑一次全套(189 s),要嘛在 verification 寫明豁免邊界。
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

### Opus 原始 findings (first-pass, context-aware)

- **F-01** [python-reviewer] LOW `tests/server/test_corr_routes.py:14-17`(anchored: exact;baseline: Quality-8 風格)— import 區與 `_client` 之間 3 空行。search-proof:`ruff check --select E303 --preview` 全 repo 僅 3 筆(本 PR 2 + 存量 1);`ruff format --diff` 唯一差異即此行。mechanism:pyproject `[tool.ruff]` 未設 select → 預設 E4/E7/E9/F,不含 E3。
- **F-02** [python-reviewer] LOW `tests/server/test_river_routes.py:14-17`(anchored: exact;baseline: Quality-8 風格)— import 區與 `_client` 之間 3 空行。search-proof:同一次 `ruff check --select E303 --preview --output-format concise copycat tests` 第 2 筆命中 `tests\server	est_river_routes.py:17:1: too-many-blank-lines: Too many blank lines (3)`。mechanism:同 F-01 —— ruff 預設規則集不含 E3、`ruff format` 非 gate,故只有 preview 規則驗得出。
- **F-03** [python-reviewer] LOW `.claude/refactor/f20-corr-leg-keys-from-config/verification.md:4-5`(anchored: exact;baseline: 文件一致性)— 「改動」段停在 61ca1373 形狀。search-proof:`grep -rn "_LEG_KEYS\|_PAIR_KEYS" tests copycat --include=*.py` 零命中;`git diff --stat 314a8f2f..d9afb37d` 6 files 含新檔。mechanism:commit 序列 61ca1373 → f121326f → 7c2dd71e(S3)→ d9afb37d,verification 落檔於最後一筆但正文沿用第一筆措辭。
- **F-04** [python-reviewer] LOW `.claude/refactor/f20-corr-leg-keys-from-config/verification.md:16`(anchored: exact;baseline: none)— 自行豁免全套 gate。reviewer 代跑閉環:`pytest -q -p no:cacheprovider --rootdir <worktree>` → 3096 passed / 3 skipped(188.91 s);`pyright` 全 repo 0 errors;`ruff check` clean。mechanism:`CONFIG_PATH` 由 `__file__` 絕對推導不吃 cwd;`corr_legs.py` 不符 `test_*.py` 收集樣式。
- **F-05** [python-reviewer] LOW `tests/helpers/corr_legs.py:11`(anchored: exact;baseline: Quality-5 命名)— 匯出名 `CFG` 過泛。search-proof:`grep -rn "\bCFG\b" tests copycat` → 3 個模組私有 + corr_legs.py 定義 + 唯一跨檔匯入 test_corr_routes.py:11,60。mechanism:`load_config` 回 frozen dataclass、frozenset 不可變,跨檔共用安全,純命名。
- **F-06** [python-reviewer] LOW `.claude/refactor/f20-corr-leg-keys-from-config/code-review-round-1.json:8-11`(anchored: exact;baseline: 文件一致性)— id `P1` 與 severity 值域撞名。search-proof:121 份 round json 前綴統計 spec 軸 SP* 65 / P* 12,standards 軸 ST* 77 / S* 10;本檔 disposition 全文含「S1 / S2 / P1 → f121326f 收修…無 P1 / P2。」。mechanism:先確認非誤讀 severity 欄 —— 該筆 `"severity": "P3"`,而 disposition「無 P1 / P2」對照的是 severity 值域(P1/P2/P3),兩者確實共用同一組符號,撞名成立、非風格偏好;仍成立理由 = json 為留存 SoT,日後工具照 id/severity 對帳會誤讀。

### Codex 原始 findings (first-pass, diff-only)

N-A —— 本機無 codex CLI,中性 / 對抗兩軸皆未啟動,零 finding。

### Opus 對 Codex 的複查結果

N-A —— 無非 CC finding 可複查。

### Codex 對 Opus 的複查結果(對稱化 4.2)

**Codex 複查 Opus 失敗 —— 本輪 Step 4.2 輸入 findings 無 cross-axis 證據**(本機無 codex,batch 未起跑)。所有 CC finding 視同 INCONCLUSIVE,改由 4.3b 主 agent 判斷式複查:

| Opus # | Opus reviewer | Opus title | Verdict | 原始 → 校正 severity | Codex evidence | 備註 |
| --- | --- | --- | --- | --- | --- | --- |
| F-01 | python-reviewer | E303 三空行 | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | 4.3b:主 agent 讀 HEAD 檔 :14-17 確認;lone,格式 → Nice。 |
| F-02 | python-reviewer | E303 三空行 | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | 4.3b:同上。 |
| F-03 | python-reviewer | verification 改動段停在收修前 | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | 4.3b:主 agent 是該檔作者,確認 S3 收修後未回改「改動」段;lone,文件 → Nice。 |
| F-04 | python-reviewer | 自行豁免全套 gate | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | 4.3b:PARTIAL —— 豁免理由(語意等價)對字面集合成立,對新增 import 期讀檔 helper 確實沒說到;reviewer 已代跑全套綠,實害為零 → Nice / no-op。 |
| F-05 | python-reviewer | `CFG` 名過泛 | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | 4.3b:命名判斷題,repo 內無跨檔匯出的 `CFG` 前例 → Nice。 |
| F-06 | python-reviewer | id `P1` 撞名 | INCONCLUSIVE(4.2 N-A) | LOW→LOW | — | 4.3b:主 agent 讀 json 確認 disposition 字面「無 P1 / P2」與 id `P1` 並存;lone,文件 → Nice。 |

## Action Items

**display_ordinal / action_reason 對應**:canonical record 的 `F-NN` 即 `display_ordinal`(序號連續,與發現總覽及 inline block 標題一致);`action_reason` = 發現總覽「Action 理由」欄,依命令固定格式不重複進 canonical record。

**Severity calibration**:6c 本 PR 無此類 finding → 免;6d-1 hedge:六條皆無假設性措辭;6d-3:六條皆為格式 / 文件,不影響 runtime / 資料 / build·CI → 無 Must / Should;6d-2 由 4.3b 取代。Provenance cap N-A。未驗證前提:無。

**校準套用**: 無作者校準檔(loger-w.md 不存在)、本輪無套用

### Must Fix(合併前必修)

無。

### Should Fix(強烈建議)

無。

### Nice to Have(可選優化)

- F-01 `test_corr_routes.py` import 區與 `_client` 之間刪一個空行
- F-02 `test_river_routes.py` 同上
- F-03 verification「改動」段補 S3 收修後的最終形狀(新檔 `corr_legs.py` / `CFG` / `LEG_KEYS` / `PAIR_KEYS`)
- F-04 verification 豁免全套 gate 的邊界條件未寫明(reviewer 已代跑全套綠,無後續動作)
- F-05 `CFG` 改名 `CORR_CFG`
- F-06 review json spec 軸 id `P1` → `SP1`

### 參考用(任一軸驗證為 REFUTED 或 OUT_OF_SCOPE)

無 —— 本輪無 REFUTED / OUT_OF_SCOPE(4.1 / 4.2 皆 N-A;4.3b 一條 PARTIAL 未推翻)。

## 審查工具比較 (qualitative)

- Opus(CC context-aware)視角:reviewer 在 PR head 做了 mutation 實驗(drop-GC / add-XX 注入 corr 引擎 config → corr.legs / corr.pairs / river.legs / 訂閱數四條斷言全翻紅、baseline 全綠),證明改讀 `configs/correlation.json` 未造成同義反覆也未弱化偵測力;逐字契約仍由 `tests/test_corr_config.py::TestRepoConfigFile` 鎖住;另代跑全套 pytest 3096 passed / pyright 0 / ruff clean。六條 finding 全為 LOW。
- Codex 中性 / 對抗視角:N-A(本機未裝)。重疊率無法計算;4.1 分佈 N-A;4.2 分佈:INCONCLUSIVE 6 / 6(工具缺席,非 Opus over-flag 的訊號)。
- 對抗式第三軸增益:N-A。Gemini 軸增益:N-A。
- 本輪 lone finding = 6 / 6(所有他軸皆未啟動),4.3b 以主 agent 第一手證據判斷,無降級亦無升級。
- 與 in-repo two-axis round 1(`.claude/refactor/f20-corr-leg-keys-from-config/code-review-round-1.json`,3 S + 1 P 全收修)對照:本輪六條全部是 round 1 未抓到的新 finding,其中 F-03 / F-06 是 round 1 的產物本身。

## 沒做的部分(結案對帳)

- Codex 中性軸:FAIL / N-A —— 本機無 `codex` CLI,未起跑,零 finding;報告以 CC 軸為主。
- Codex 對抗軸:FAIL / N-A —— 同上。
- Gemini Flash 軸(永久軸):FAIL / N-A —— 本機無 `agy`,未起跑;Pro 軸未啟用亦無工具。
- Step 4.1:N-A —— 無非 CC finding。
- Step 4.2:FAIL → 全部 INCONCLUSIVE —— codex-companion batch 無法起跑;以 4.3b 主 agent 判斷式複查補位,**不冒充 cross-axis 證據**。
- Step 2.9 blast radius:N-A —— 無 `sem`,空輸出跳過。
- Step 2.65 C4:SKIPPED(C4_AUTHORITY_PATH_NOT_ALLOWED);本機 `pr-review-c4.py` permit 目錄 POSIX-only。
- Step 2.96 / 2.98 提問:未問(工具缺席,無對象可設定),按預設記錄。
- Step 2.97 React-doctor:N-A(非 React PR)。
- 未驗證前提:無。
- 主 agent 利益重疊:本 PR 五個 commit 皆由本 session 的主 agent 產出,4.3b 判斷式複查由同一 agent 執行;reviewer(python-reviewer sub-agent)為獨立 fresh context,finding 本體不受此影響。
- Self-Verify:auditor 輸出格式完整,`VERDICT: VIOLATIONS: R4, R5, R6`。R4 原缺口 = 缺 reducer 安全投影陳述 → 於「Spec 依據」補一條(無 dispatch、無 human_projection、無 invalidated 語意);R5 原缺口 = 無 `display_ordinal` 字面 → canonical record 下補對應說明;R6 原缺口 = F-02「同 F-01」未自帶證據、F-06 缺機制句 → 自 reviewer 原始 JSON 補回 F-02 的 `ruff --select E303 --preview` 第 2 筆命中與 F-06 的「severity 欄 = P3、disposition 的 P1/P2 指 severity 值域」機制。三處皆為補寫既有產物內容,不改 finding 結論。**未經第二次獨立稽查。**
