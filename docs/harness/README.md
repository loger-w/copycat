# AI 開發 Harness — 架構總覽

本專案(trash-mr-warrant)沿用與 neigui 相同的 Claude Code + 自建工程紀律 harness 開發。`commands/`、`hooks/`、`skills/`、`agents/`、`global-rules.md` 是 user-global 檔案(`~/.claude/`)的**鏡像副本**,source of truth 在 user-global,每次 harness 改版時同步至此(本份 2026-07-07 自 `~/.claude/` 原檔同步,逐檔 diff 核對一致;涵蓋 /goal→/auto 改名與 PR 收尾改版)。

harness 的設計理念、演進史與量化成果紀錄在宿主專案 neigui 的 `docs/harness/README.md` 與 `SPEC.md`,不在此重複。

## 分層架構

```
┌─ 全域鐵則(global-rules.md,~/.claude/CLAUDE.md)
│   觀察優先 / Scope 紀律 / 測試紀律 / 證據要求 / 禁止繞過 /
│   3 次失敗上限 / Sub-agent 紀律 / Git 推送紀律
│
├─ 流程指令(commands/,~/.claude/commands/)
│   /feat — 10-phase 新功能流程(brainstorm → 設計 review → TDD →
│           自評 → 自動化驗證 → 真實環境驗證 → 回頭核 goal → 沉澱)
│   /bug  — 重現 → 單一假說驗證 → 紅測試先行 → 反向驗證
│   /mod  — caller map → 行為白名單 → 🔵🔴🟢 三類分離 commit
│   /refactor — why gate → characterization test → 小步保綠
│   /perf — 量化目標 gate → profile → 一策略一 commit → 重量測
│   /auto — 自主模式契約(退出條件 / 自動核准邊界 / 必停清單)
│
├─ 驗證 skill(skills/auto-verify.md,~/.claude/skills/)
│   專案形狀偵測 → 自動化五步驟 + 真實環境驗證分流(單一 source of truth)
│
├─ 版控 skill(skills/branch-lifecycle.md,~/.claude/skills/)
│   開工(主線同步 + prefix 分支)/ 收尾(push → PR → review 補齊 →
│   自動 merge,2026-07-18 起全程無確認;離線 fallback local merge)/ 異常處理
│   五個流程 command 共用(單一 source of truth)
│
├─ Review agent 定義(agents/,~/.claude/agents/)
│   design-reviewer(/feat P1,medium)/ impl-spec-reviewer(/feat P2,low)/
│   change-spec-reviewer(/mod P3,medium)/ refactor-plan-reviewer(/refactor P3,low)
│   criteria + JSON schema + 唯讀 tools 固化在定義檔,dispatch 降級為指名
│
├─ 專案知識層(repo 內,按需載入)
│   CLAUDE.md         — 每 session 必讀的契約(Touchance / FinMind 資料源、
│                       Python / React 風格、§7 下單高 blast radius 閘門)
│   .claude/skills/   — 5 個主題 skill(2026-07-06 自 neigui 複製:
│                       FinMind / cancel 鏈 / e2e / 前端測試 / 前端版面;
│                       market-pipeline 因 scope 劃分不搬 — 市場監控屬 trash-cmoney)
│   .claude/harness.json — 驗證指令插槽(已預置 backend pytest / frontend
│                          test / build,backend/ frontend/ 目錄落地後生效)
│   docs/decisions.md / docs/next-time.md — 尚未建立,首次需要時再開
│   scripts/git-hooks/   — 尚未搬入(repo 還沒 git init;git 側基建
│                          待啟用版控時自 neigui 一併搬 + core.hooksPath 啟用)
│
├─ 強制層(hooks/,~/.claude/hooks/,PreToolUse/PostToolUse/
│          SessionStart/UserPromptSubmit/Stop)
│   block-no-verify.py — 攔截 --no-verify / hooksPath 覆寫 / plumbing
│                        escape / printf 重組 flag 等 20+ 種繞過手法
│   safety-hooks.py    — 攔截危險 rm -rf / bulk git add / 讀寫 secrets /
│                        curl|bash / chmod 777
│   format-on-edit.py  — 編輯後自動 format
│   harness-context.py — SessionStart/UserPromptSubmit 注入進行中 /feat
│                        的 phase 與 gate(soft reminder,弱模型防遺忘)
│   harness-stop-audit.py — Stop 審計 state.json 回寫與收件匣義務
│   (harness-push-gate.py 已於 2026-07-18 除役 — push / merge 全自動)
│   tests/             — hooks 的 pytest(強制層有 bug 比沒有更糟)
│
└─ 自我改進迴路
    .claude/feat/<slug>/       — 每個 feature 的全程證據(brainstorm /
                                 design review rounds / 驗證 JSON / 截圖)
    ~/.claude/feat-improvements.md — 流程瑕疵收件匣(每次 /feat Phase 8.5
                                 自我回報,達門檻觸發 meta-review)
    memory/                    — 帳號 / 偏好 / 名單類跨 session 記憶
```

## 設計理念

1. **證據先於宣稱**:任何「完成」必附指令輸出 / 測試數字 / 截圖。自動化全綠 ≠ Done — 還要真實環境驗證 + 回頭核對動機(brainstorm 的 SC 表逐條對證據)。
2. **TDD 紅先行 + 機械化驗證**:紅測試 → 綠實作 → 重構各自帶 tag(`[red]`/`[green]`/`[refactor]`/`[lock]`),流程結束用 `git log --grep` 機械化驗證 TDD 序列真的發生過,不靠自由心證。
3. **Review loop 有上限**:sub-agent review 以 P0/P1/P2 分級,3 輪上限強制收斂;超限必須向 user 回報結構化三件事(剩什麼 / 試了什麼 / 推測根因),禁止「繼續試試看」。
4. **失敗分流不無腦重來**:驗證失敗依類型(goal 漏 / design 漏 / impl 漏 / test 漏)回對應階段,計數進 state.json,同一條件回退 2 次強制升級處理層級。
5. **自我改進迴路閉環**:流程自己回報流程的 bug(收件匣),達門檻觸發 meta-review;知識沉澱有目的地規則 + 強制 GC(寫入前先合併 / 翻新 / 刪同主題舊條目)。
6. **Context 經濟**:每 session 必讀的契約留 CLAUDE.md,情境性慣例拆主題 skill 按需載入,trigger 寫進 description。

## 日常指令 cheat sheet

| 場景 | 指令 |
|---|---|
| 新功能 / 新頁面 / 新指標 | `/feat <目標>`(Phase 0 會自動 S/M/L 分流,小改動走輕量路徑) |
| 東西壞了 / 行為不對 | `/bug <現象>` |
| 改既有功能的行為或介面 | `/mod <改什麼>` |
| 純結構整理(行為不變) | `/refactor <為什麼現在做>` |
| 有量化目標的變快 | `/perf <metric + 目標數字>`(沒數字會被擋,「感覺慢」→ 先 `/bug` 或 `/refactor`) |
| 想全自動跑到某個檢查點 | `/auto <退出條件> /feat <目標>`(收尾自動 push + 開 PR + merge 到底,2026-07-18 起無 merge 確認) |
| 完成前驗證 | 各流程內建呼叫 `auto-verify`,不需手動 |
| 深度審查當前 diff | `/code-review`(想要多 agent 深審在訊息加 `ultracode`) |
| 動 FinMind / cancel 鏈 / e2e / 前端某塊之前 | 對應主題 skill 會自動掛上;手動看:`.claude/skills/` 各 description |

## 檔案同步說明

`commands/`、`hooks/`、`skills/`、`agents/`、`global-rules.md` 為鏡像,**不要直接改這裡** — 改 `~/.claude/` 原檔後執行:

```bash
cp ~/.claude/commands/{feat,bug,mod,perf,refactor,auto}.md docs/harness/commands/
cp ~/.claude/hooks/{block-no-verify,safety-hooks,format-on-edit,harness_lib,harness-context,harness-stop-audit,check_feat_tags}.py docs/harness/hooks/
cp ~/.claude/hooks/tests/test_*.py docs/harness/hooks/tests/
cp ~/.claude/skills/auto-verify/SKILL.md docs/harness/skills/auto-verify.md
cp ~/.claude/skills/branch-lifecycle/SKILL.md docs/harness/skills/branch-lifecycle.md
cp ~/.claude/agents/{design-reviewer,impl-spec-reviewer,change-spec-reviewer,refactor-plan-reviewer}.md docs/harness/agents/
cp ~/.claude/CLAUDE.md docs/harness/global-rules.md
```

neigui 的 `SPEC.md`(履歷素材 handoff)未鏡像至此 — 其規模數據與證據路徑全綁 neigui repo,屬該宿主專案的成果文件。
