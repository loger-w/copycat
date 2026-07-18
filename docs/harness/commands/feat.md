# Feature: $ARGUMENTS

(若 $ARGUMENTS 為空,先問我要做什麼功能再繼續。)

共通鐵則套用 `~/.claude/CLAUDE.md`。自主模式契約見 `~/.claude/commands/auto.md`(下稱 /auto)。

## 核心原則(全程適用)

- **Artifacts 釘檔**:每 phase 產物寫到 `.claude/feat/<slug>/`,跨 session 可 resume(state.json schema 見尾)。**此為 user preference,顯式覆寫** `superpowers:brainstorming` / `superpowers:writing-plans` 的 `docs/superpowers/` 落點與「設計文件先 commit」要求 — artifact 統一釘專案內,Phase 8 才 commit。
- **Receiving 紀律**:所有 RECEIVING feedback(sub-agent JSON / `/code-review` finding / 環境問題)一律過 `superpowers:receiving-code-review` 分類 `accepted` / `rejected_with_reason` / `needs_more_context`,絕不照單全收。
- **Review 輪數上限 3**:**顯式覆寫** `superpowers:subagent-driven-development` 與 `superpowers:requesting-code-review` 的「repeat until approved」無上限迴圈 — 理由:鐵則 G + token 經濟。**Tech pivot(換架構重做)想重置計數 → 必須先向 user 回報並取得批准**,不准自行續跑超限。
- **P1 帶額度退場**:Phase 1/2 退出條件「無 P0 且 P1 ≤ 2(入 Known Risks)」與 Phase 4 的單輪退場條件,**顯式覆寫**鐵則 G 的退出條件「無 P0/P1」— 理由:餘 P1 已具名寫入 Known Risks 落檔追蹤,非默默放掉。
- **失敗類型分流**:Phase 7 失敗不是無腦回 Phase 3,依失敗類型(goal 漏 / design 漏 / impl 漏 / test 漏)回對應 phase。
- **跨 phase meta-cycle**:同 SC 單 phase 回退 ≥ 2 次或跨 phase 累計 ≥ 3 次 → 升級回 Phase 0/1,計數寫 `state.json.sc_cycle_counts`(Phase -1 豁免)。
- **state.json 為唯一資料源**:`brainstorm.md` 對應 SC 旁只標 `cycle-count: [see state.json]`。**每完成一個 phase 立即回寫 `current_phase` / `completed_phases`**(2026-07-06 審計:9 個 feature 有 3 個 state 與 artifact 不同步)。
- **Findings 量大先收斂**:任何 review 收回 > 10 findings → 先 group-by-file dedup + severity rank,合併成單一 `*-review-round-<N>.json` 再處理,不逐條原樣 list。

## Phase -1:工作區隔離 + artifact 釘定

1. 呼叫 `branch-lifecycle` 開工節:status 乾淨 + 主線同步 + 從 $ARGUMENTS 推導 kebab-case `<slug>` + `git switch -c feat/<slug>`(monorepo / 長隔離 → 改呼叫 `superpowers:using-git-worktrees`,worktree 路徑寫 state.json)
2. 建 `.claude/feat/<slug>/` + `echo ".claude/feat/<slug>/" >> .git/info/exclude`(Phase 8 再拿掉)
3. 初始化 state.json(schema 見尾;`sc_cycle_counts` 只建 `_unscoped`,SC-N 條目**稀疏** — 首次回退發生時才建),記錄 `start_sha`

## Phase 0:Brainstorm + 可驗證性 gate + S/M/L 分流

1. 呼叫 `superpowers:brainstorming`,**遵循 skill 的對話流程**(一次一問、2-3 方案、分節確認)。以下 2-4 是本流程的**加值 gate**,疊在 skill 之上,不取代其流程。
2. **SC gate**:每條成功條件編號 `SC-1, SC-2…`,強制附「驗證方式」一行(指令 / 測試名 / 截圖步驟)。**量化 SC(size / time / count)必附 measurement unit + 量法指令** — `size ≤ 50 KB` 不合格,要寫 `size ≤ 50 KB(gzip 後;量法 curl --compressed | wc -c)`。寫不出 → 該條不合格(gate 不是建議)。
3. 寫入 `brainstorm.md`(後續修改必標 `[amendment YYYY-MM-DD: <原因>]`)+ ≥ 3 edge cases + out of scope。
4. **S/M/L 分流**(寫 `state.json.scope`):
   - **S**:單檔 / 無新資料流 / 無新依賴 / 不在 hot path、安全邊界、共用 util、對外 API → 跳 Phase 1 文件化,Phase 2 0 輪 review(hot path 判準:有 profile 證據或專案文件 / skill 點名的路徑才算;無證據視為不在)
   - **M**:2-4 檔 → Phase 1/2 各 1 輪 review
   - **L**:≥ 5 檔、跨前後端 / 跨服務、或鑑權 / 加密 / 金流 / 對外 API 任何單檔改動 → 完整流程,Phase 1/2 各 max 3 輪
   - **風險升級**:碰到高風險面無視檔案數一律升 L
5. 等使用者確認再進 Phase 1(自主模式的替代確認條件見 auto.md)

## Phase 1:設計 spec(L: max 3 輪;M: 1 輪;S: 跳過)

1. 呼叫 `superpowers:writing-plans` 寫 `design.md`:架構 / 檔案組織 / 資料流 / 邊界 / 接點;每條 SC-N 對應設計章節;標版本 v1(後續改 → v2…,檔頭保留 changelog)
2. Sub-agent 用 `design-reviewer` agent type dispatch:傳 design.md + brainstorm.md 路徑(round ≥ 2 加上一輪 JSON 路徑 + changelog 摘要),回傳 JSON 寫 `design-review-round-<N>.json`(schema / severity / criteria 固化在 agent 定義,command 不重抄)
3. main agent 對每條 finding 過 `superpowers:receiving-code-review` 分類,附 `resolution` 欄位
4. 處理 accepted 的 P0/P1 後 `state.json.pending_review_rounds.phase_1 += 1`,重跑 review
5. **退出條件**:該輪無 P0 **且 P1 ≤ 2**(餘 P1 逐條寫入 design.md `## Known Risks`)→ reset `phase_1: 0`,進 Phase 2
6. **3 輪上限後仍有 P0** → 結構化回報(剩哪些 P0 + 為何 suggested_fix 被拒 + 試過的方向 + 推測根因),user 三選一:[1] 縮 scope 回 Phase 0 / [2] 換技術方向重寫(**計次歸零需 user 此處批准**)/ [3] 接受 P0 寫入 `## Known Risks`

## Phase 2:Implementation spec(L: max 3 輪;M: 1 輪;S: 簡化版)

1. **模式選擇**(寫 `state.json.phase_2_mode`):**預設 `condensed`** — 單一 `implementation/PLAN.md`,每檔一節 3-5 行(動什麼 / 新增或變更的 signature / 失敗測試清單對應 SC-N)。`per_file`(逐檔 `implementation/<file>.md`:signature / 輸入輸出範例 / 失敗測試清單)**降為 opt-in**:僅 L 級且該檔屬高風險面(安全邊界 / 共用 util / 對外 API / hot path)才逐檔寫(2026-07-06 實證:per-file MD 零回讀、condensed 走完全程,token 成本差一個量級)
   - **Phase 3 對齊規則**(取代舊「ad-hoc 對齊」):落地發現 PLAN.md 該節粒度不足 → 就地補 signature 細節並標 `[phase-3 補註]`,不回頭重跑 review;介面級衝突仍走 Phase 3 失敗回退表
2. Review dispatch:`condensed` → 對 PLAN.md dispatch **單一** `impl-spec-reviewer`(逐節視同逐檔套 criteria);`per_file` → 用 `superpowers:dispatching-parallel-agents` fan-out 每檔一個(傳該檔 + design.md 路徑;criteria / JSON schema / {file, section} 雙欄 location 固化在 agent 定義)
3. Receiving 分類同 Phase 1;退出條件:全檔無 P0 且 P1 ≤ 2(進 Known Risks)→ reset 進 Phase 3
4. 3 輪上限後仍有 P0 → [1] 縮 scope 回 Phase 0 / [2] implementation 改寫(finding 暗示問題在 design → escalate 回 Phase 1,計次歸零需 user 批准)/ [3] 接受寫入 Known Risks,Phase 7 表格 regression 欄必涵蓋

## Phase 3:TDD + 文件同步 + commit 三分類

1. 呼叫 `superpowers:test-driven-development`。實作模式依下表為**預設建議**;非自主模式向 user 確認一次(`superpowers:writing-plans` 的 execution handoff 慣例),自主模式直接採用並在 state.json 標 `[auto-default]`:
   | 條件 | 模式 |
   |---|---|
   | ≥ 3 檔且彼此獨立 | `superpowers:subagent-driven-development` |
   | 單檔但長時間 / 跨 session | `superpowers:executing-plans` + checkpoint |
   | ≤ 2 檔且函式清單明確 | main agent 自己 TDD |
2. **TDD 三 commit 各帶 tag**(Phase 8 機械化驗證):
   - 紅測試:`git add <測試檔>`(不要 `-A`)+ `🟢 test(<area>): add failing test for SC-N [red]`
   - 實作到綠:`git add <實作檔>` + `🟢 feat(<area>): implement SC-N [green]`(body 註 `red→green for <red-sha>`)
   - Refactor(再跑測試綠才 commit):`🔵 refactor(<area>): ... [refactor]`
   - **goal_efficiency_mode**(見 auto.md):可改 wave batch,單 `[waveN]` tag,commit body 列該 wave 涵蓋的 SC-N
3. 新發現 case:先回 Phase 2 文件追加(只追加不重跑 review)再寫紅。**test-infra 例外**:selector / matcher / jsdom 行為修正(非新 SC 行為)可同階段直接 patch test 檔,commit body 註 `test-infra-fix: <reason>`,不回 Phase 2
4. **失敗回退**(禁止「就地改 code 不更新上游文件」):(a) 介面 / 資料流無法實作 → 回 Phase 1(快速路徑:只 review 變更段落)/(b) signature 細節錯 → 回 Phase 2 /(c) edge case 沒列 → 回 Phase 0 補 SC
5. **next-time.md 鉤子**:每次 commit 前 cat `docs/next-time.md`,順手改動衝動寫進去或拆獨立 commit。**Subagent 模式下 main agent 在每 task dispatch 前代查**,有相關條目才塞進 dispatch prompt(fresh context 的 subagent 不知道檔案存在)
6. 套鐵則 F:同一輪 red → green 修不過 3 次 → 停下回報三策略 + 推測根因

## Phase 4:自評 — code-review 雙焦點 → receiving → 依層級回對應 phase

1. 跑 `/code-review`(**預設 medium 檔位**;xhigh 全量掃描保留給 user 顯式要求 — 2026-07-06 實證:xhigh 52 候選中真 P1 僅 1 條),**雙焦點**:(a) implementation bug;(b) **missing-from-spec** — 回看 design.md 交叉確認「spec 機制在 impl 有沒有 spec 沒提到的副作用」。寫 `code-review-round-<N>.json`
   - **輸出契約**:round JSON 只逐條展開 P0/P1;P2 慣例 / 風格類彙總為 `p2_summary`(計數 + 主題一行),**不逐條 receiving**。例外:P2 中疑似行為級(資料正確性 / 時序 / 邊界)照常展開
   - **Dispatch / 快篩紀律**(2026-07-11 meta-review,同根因收斂:minimal-model finder 對「機械事實」與「prompt 內排除契約」皆不可靠,把關在 main agent 不在 finder):(a) finder prompt 的排除清單(已文件化慣例 / 刻意 pattern)放 prompt **開頭**並要求輸出前對照自檢 — 此為降噪手段,不可依賴;(b) candidate 進 receiving / verifier dispatch 前 main agent **先機械快篩**:grep/Read 可直接查證的 claim(pragma / import / 行號 / 檔案存在)先反證,誤報直接記 REFUTED 不 dispatch verifier;命中排除清單者彙總計數丟棄,不逐條 receiving
2. 呼叫 `superpowers:receiving-code-review` 對每條 finding 分類。**Verify / skeptic 階段前,先摘 design.md changelog 的 accepted findings + rationale 注入 verify prompt**(避免 refute 事後合理的設計收窄)。Lens 經驗值:mature codebase 上 test_coverage lens 命中率最高,correctness / consistency 易產生被 refute 的風格建議 — lens prompt 要角度真差異化
3. accepted 依層級回對應 phase:spec 漏 → Phase 1/2 改文件 / impl 漏 → Phase 3 / test 漏 → Phase 3 紅先行(鐵則 C)。**Test-gap finding 補 lock test**:鎖「已正確行為」天生無紅 → 走 mutation 抽驗(手動改壞 → lock test 紅 → 還原 → 綠),commit 用 `[lock]` tag + body 註 `mutation-verified`。**改壞 / 還原一律用 Edit 工具成對操作,禁止 `git checkout` / `git restore`**(會連同掃掉同檔尚未 commit 的 review fix;2026-07-11 實證損失後補)
4. **退場條件**:round 1 accepted ≤ 5 且無 P0 且 fix 後自動化測試全綠 → 可單輪退場;accepted > 5 或有 P0 → 強制 round 2 verify。loop max 3 輪
5. 完成後跑 **inline 完工自查 checklist**(不呼叫 requesting-code-review — 該 skill 是 dispatch reviewer 流程,不是自查):測試齊全 / commit 分類分明 / 文件同步 / known-risk 已標記
6. 自評收斂後把當下 HEAD sha 寫入 state.json `self_review_head`(收尾節 review 增量判準:`self_review_head..HEAD` 非空才補增量 review)

## Phase 5:自動化驗證

1. 呼叫 `auto-verify` skill — 專案形狀偵測與驗證指令來源**以該 skill 為單一 source of truth**,本檔不重抄表格。偵測不到驗證指令 → 停下問
2. 任一步紅 → 鐵則 F 3 次上限。失敗映射:可歸 SC-N → `sc_cycle_counts.SC-N.phase_5 += 1`;不可歸(global tsc error 等)→ `_unscoped.phase_5 += 1`
3. 每輪輸出 `automated-verification-round-<N>.json`(step / command / exit_code / stderr_tail / hypothesis / strategy_tried);全綠寫 summary 進 `automated-verification.md` 才進 Phase 6

## Phase 6:真實環境驗證

1. 呼叫 `auto-verify` skill 的「真實環境驗證」節(feature shape 分流表以 skill 為準)
2. **Subsumed 判定**:feature shape = web 且該 SC 已有 Playwright e2e 覆蓋(Phase 5 跑過真 backend + 真 browser)→ 該 SC 標 `subsumed by Phase 5`,不重複 DevTools MCP 截圖
3. **Infra_fail 標準 case 與 fallback 路徑以 `auto-verify` skill 真實環境節為準**(token 過期 / browser MCP 斷線 / 外部 503,本檔不重抄)。本流程只補記帳規則:不算 SC 回退,`_unscoped.phase_6 += 1` + state.json 記 `phase_6_blocked_reason`;fallback 的 UI SC 註記(「RTL 涵蓋 logic,視覺 next session 補」)寫進 Phase 7 evidence 欄
4. **失敗回退**(依 cycle-count rule 記數):(a) 情境沒列 SC → 回 Phase 0 補 SC /(b) SC 有列 design 沒兼顧 → 回 Phase 1 /(c) 測試漏 → 回 Phase 3 先寫紅
5. 證據放 `evidence/`,檔名含 SC-N(例:`SC-2_login-empty-input.png`);每輪輸出 `real-env-verification-round-<N>.json`

## Phase 7:回頭核 goal — 結構化證據表 + meta-cycle

1. **進入前 state.json 一致性自檢**:`current_phase` / `completed_phases` 與實際 artifact(review JSON / evidence 檔)對得上;不符先補回寫再開始
2. 呼叫 `superpowers:verification-before-completion`,重新讀 brainstorm.md 不憑記憶
3. **強制結構化表格**(每 SC-N 一列):

   | SC-N | 實作檔案:行號 | 自動化測試名 + pass count | real-env 證據路徑 | regression 抽樣對象 |
   |---|---|---|---|---|

   任一欄出現「N/A」「verified ✓」「應該可以」→ 直接視為未完成。**例外**:real-env 欄允許 `infra_fail: <reason>`(須對應 state.json `phase_6_blocked_reason`)或 `subsumed by Phase 5: <e2e spec#>`
4. **失敗類型四分流**:(1) goal 沒被 design 涵蓋 → Phase 1 /(2) design 有實作沒做 → Phase 2/3 /(3) 實作有做測試漏 → Phase 3 先寫紅 /(4) goal 模糊互斥 → Phase 0 改寫 SC(舊 SC 計數移 `docs/next-time.md`,新 SC 從 0 起算)
5. Meta-cycle:每次不通過更新 sc_cycle_counts;同 SC 回退 ≥ 2 次 → 強制升 Phase 0/1。兩輪仍不滿足 → 鐵則 F 找 user:[a] 改寫 SC / [b] 降 known-gap 寫 `docs/next-time.md` / [c] 繼續迭代

## Phase 8:整合與收尾

1. 收尾路徑:**預設走 `branch-lifecycle` 收尾節**(push → PR → review 補齊 → 自動 merge;2026-07-18 拍板全自動無確認)— **顯式覆寫** `superpowers:finishing-a-development-branch` 的三選一互動,理由:solo 無 reviewer,user 拍板自動化。執行順序:步驟 2 tag 驗證 → 步驟 3 artifact commit → 收尾節
2. **Commit tag 機械化驗證(script 化,2026-07-06)**:
   ```bash
   python ~/.claude/hooks/check_feat_tags.py --state .claude/feat/<slug>/state.json
   ```
   四類 tag 掃描 / `[green]`→`[red]` 配對 / 豁免((a) `[lock]`+`mutation-verified`、(b) `Phase 6 real-env finding` design-amend)/ wave 模式判定**固化在 script**(規則本檔不重抄;script 有 pytest 護住)。**wave 模式的「全 SC 有 wave 歸屬」屬半語意判定** — script 只列 wave→SC 對映,由 main agent 對照 brainstorm.md 核。FAIL 且無豁免 → 回 Phase 3 rebase commit message(不增計數)。emoji 三類:🟢 新功能 / 🔵 純重構 / 🔴 行為改動(/feat 純新功能 🔴 可為 0)
3. **Artifact commit**:手動編輯 `.git/info/exclude` 移除 `.claude/feat/<slug>/` 該行(用編輯器 / `grep -v` 重寫,**不用花式 sed delimiter**),然後:
   ```bash
   git add ".claude/feat/<slug>/" && git commit -m "chore(feat-<slug>): artifacts"
   ```
   不允許 `git add -f` 短路(會掩蓋 exclude 是否真清除)。**分支條件**:repo `.gitignore` 排除 `.claude/` → 沿專案政策 skip artifact commit,state.json 記 `artifact_commit: "skipped (.claude/ gitignored)"`(2026-07-11 copycat 實證;有 commit 前例的專案如 neigui 照常 commit)
4. 非預設路徑(user 指定才走):**保留 branch**(state.json 標 `paused: <reason>`,不 push 不 merge)。PR 已是預設收尾;merge 規則在 branch-lifecycle,不重抄
5. Worktree 清理(若有):`git worktree remove <path>` + `git branch -d feat/<slug>`

## Phase 8.5:沉澱(閉環)

### (A) Domain 學習 → 依目的地規則

| 學到的東西 | 去處 |
|---|---|
| Code-anchored 專案慣例(引用檔名 / 函式 / pattern) | 專案 `.claude/skills/` 對應主題 skill(索引見專案 CLAUDE.md §8);沒有合適主題才開新 skill |
| 每 session 必讀的契約 / 風格 | 專案 CLAUDE.md §2-§4 |
| 帳號 / 偏好 / 名單 / 跨專案通用 | `~/.claude/projects/<project>/memory/` + MEMORY.md 索引 |

**GC pass(寫入前強制)**:先搜同主題舊條目 → 合併 / 翻新 / 刪除,**不准只往上疊**。含數字的條目必標日期;date-bound 條目必寫失效條件。

### (B) 流程瑕疵候選 → `~/.claude/feat-improvements.md` 收件匣

判準:不是 domain 學習,而是 phase 漏 / gate 失效 / 文件層斷裂。Schema:
```markdown
## YYYY-MM-DD (feature: <slug>, project: <name>)
- [proposed] Phase <N>: <問題敘述>
  Severity: P0(跑不下去)/ P1(會卡)/ P2(可選)
  Source: <發現情境>
  Proposed_fix: <建議>
```
不直接改 /feat(走獨立 meta-review)。

### (C) Meta-review 觸發檢查(Done 的一部分)

讀 inbox 統計未 resolved 條目:**P0 → 立即提醒 user;同 phase 或同族 ≥ 3 條 → 強烈建議 user 排 meta-review**(2026-07-06 教訓:兩個家族各累積 3 條無人收割)。

## state.json schema(完整)
```json
{ "slug": "...", "start_sha": "...", "branch": "feat/<slug>", "worktree_path": null,
  "current_phase": -1, "completed_phases": [], "scope": null,
  "phase_2_mode": null,
  "pending_review_rounds": { "phase_1": 0, "phase_2": 0, "phase_4": 0 },
  "blockers": [], "phase_6_blocked_reason": null,
  "scope_overrides": { "goal_efficiency_mode": false },
  "last_updated": "<ISO>", "project_shape": null,
  "last_commit_sha": null, "final_merge_sha": null, "self_review_head": null,
  "artifact_commit": null,
  "sc_cycle_counts": {
    "_unscoped": { "phase_1": 0, "phase_2": 0, "phase_3": 0, "phase_4": 0, "phase_5": 0, "phase_6": 0, "phase_7": 0, "total": 0 }
  },
  "paused": null }
```
(`sc_cycle_counts` **稀疏記帳**(2026-07-06,實證多數 feature 全零):初始化只建 `_unscoped`;`SC-N` 條目在該 SC **首次回退時才建**,且只含實際發生過的 phase 欄 + `total` — 零回退的 SC 不出現在 state。`phase_7` 欄是「Phase 7 判定失敗後回退到該 phase」的記錄欄;Phase 7 自身不 increment。meta-cycle 升級規則(同 SC ≥2 / 跨 phase ≥3)讀法不變。)

## 自主模式建議
- 完整契約見 `~/.claude/commands/auto.md`
- **S 級**想全自動:`/auto Phase 8.5 完成 /feat <desc>`
- 中段自動:`/auto Phase 7 結構化表格全綠 /feat <desc>`(2026-07-18 起收尾自動 merge 到底,不再天然停在 merge 確認)
- **L 級不建議全自動**(Phase 0 對齊價值高;merge 確認已移除,想在 merge 前人工試用就不要疊 /auto 跑完收尾)

## Done
**Phase 8 完成 + Phase 8.5 (A)(B)(C) 都處理**才算結束:Phase 7 表格全綠 / Phase 8 tag 驗證過 + artifact commit / 沉澱寫入 + GC pass + meta-review 檢查,缺一不可。
