---
name: branch-lifecycle
description: 分支生命週期單一 source of truth:開工(主線同步 + 開分支)與收尾(自動 merge 回 main + 刪分支)。/feat /bug /mod /refactor /perf 的第一個 phase 與 Done 全過後呼叫。
metadata:
  author: user
  version: "1.0.0"
---

# Branch Lifecycle

分支生命週期的**單一 source of truth** — /feat /bug /mod /refactor /perf 只寫「呼叫本 skill」,不重抄規則(同 auto-verify 慣例,防雙源 drift)。設計依據:`docs/specs/harness-git-lifecycle/design.md`(neigui repo,2026-07-06 user 拍板)。

## 開工節(各 command 第一個 phase 呼叫)

1. `git status` 確認 working tree 乾淨;不乾淨 → 停下問(commit / stash / 放棄)。
   - **當前不在 main** → 停下問(多半是上一輪流程沒收尾;分支一律從 main 開,不巢狀)。
2. `git fetch origin` 後比對 local main vs origin/main:
   - **落後** → `git pull --ff-only`(漂移來源:GitHub workflow 的 baseline commit、他機開發)
   - **領先**(本地 commit 未推)→ 照常繼續(solo 常態)
   - **分岔**(`--ff-only` 會失敗)→ 停下回報,不自動 rebase
   - 無遠端 / 離線 → 跳過同步,註記一行繼續(不阻塞)
3. `git switch -c <prefix>/<slug>`;slug 從 $ARGUMENTS 推導 kebab-case。prefix 對照表(零例外):

| Command | prefix |
|---|---|
| /feat | `feat/` |
| /bug | `fix/` |
| /mod | `mod/` |
| /refactor | `refactor/` |
| /perf | `perf/` |

## 收尾節(各 command Done 條件全過後、最終回報前呼叫)

1. **Gate**:該 command 的 Done 條件全過 + auto-verify 全綠。沒過不准進收尾(收尾不是逃生門)。
2. 在分支上 `git fetch origin` 檢查 origin/main(**判準**:`git merge-base --is-ancestor origin/main HEAD` 成立 = 未動,不成立 = 動了 — 「local main 領先未推」的 solo 常態不會誤判為漂移):
   - 未動 → 進步驟 3
   - **動了(漂移路徑)** → `git switch main` + `git pull --ff-only` → 切回分支 `git rebase main`(預設路徑分支從未推遠端,重寫安全;rebase 衝突 → `git rebase --abort` 停下回報)→ **在 rebase 後的分支上重跑 auto-verify 自動化節** — ff 保證分支樹 = merge 後 main 的最終樹,綠燈驗的就是要上 main 的狀態;紅 → 停下回報,分支保留。
3. `git switch main` → `git merge --ff-only <prefix>/<slug>`(**一律 fast-forward**,保留分類 commit;squash 選項取消 — 單 commit 分支 ff 結果等價,多 commit squash 會使步驟 4 的 `-d` 誤判 not-merged)。
4. `git branch -d <prefix>/<slug>`(小寫 `-d`:未 merge 的分支 git 會擋,天然防誤刪)。
5. 回報時提醒 user「main 領先 origin N 個 commit,可 push」— **不自動 push**(鐵則 H + push-gate)。
6. **PR 路徑**(user 事先指定才走;前置依賴:`gh` CLI 已認證,且 **local main == origin/main** — 領先時先走鐵則 H push 流程推平再開 PR,否則 GitHub 端 squash 會與含未推 commit 的 local main 永久分岔):`git push -u origin <branch>`(觸發 push-gate 確認)→ `gh pr create`;user 決定合併時 `gh pr merge --squash|--merge --delete-branch`(一步完成 merge + 清遠端與本地分支)→ 最後 `git switch main && git pull --ff-only`(GitHub 端的 merge commit 拉回本地,補齊與預設路徑的狀態對稱)。預設路徑不推分支上遠端,無遠端殘留分支問題。

## 異常處理(兩節共用)

| 情境 | 處置 |
|---|---|
| rebase 衝突(收尾漂移路徑) | `git rebase --abort` → 停下回報(列衝突檔),不自動解 |
| `--ff-only` 失敗(main 分岔) | 停下回報,不自動 rebase |
| 收尾 gate 沒過 | 留在分支上,回對應 phase(依各 command 失敗 routing) |
| user 中途放棄 | 分支保留;/feat 標 state.json `paused: <reason>`,其他流程口頭確認後才 `git branch -D` |
| 開工 `switch -c` 撞既有同名分支 | 停下問三選一:resume 該分支續作 / user 確認後 `git branch -D` 重開 / 改 slug |
| 開工時不在 main | 停下問;當前分支符合 `<prefix>/` 對照表才可選「resume 走完原流程含收尾」,否則(實驗分支 / detached HEAD)只有「user 確認處置該分支後回 main 重開」 |

## 自主模式(/goal)

merge **不在必停清單**(2026-07-06 拍板):收尾 gate 全綠即自動 local merge(可逆;push / PR 仍必停)。
