---
name: branch-lifecycle
description: 分支生命週期單一 source of truth:開工(主線同步 + 開分支)與收尾(push → PR → review 補齊 → 單一確認 → auto-merge;離線 fallback local merge)。/feat /bug /mod /refactor /perf 的第一個 phase 與 Done 全過後呼叫。
metadata:
  author: user
  version: "2.0.0"
---

# Branch Lifecycle

分支生命週期的**單一 source of truth** — /feat /bug /mod /refactor /perf 只寫「呼叫本 skill」,不重抄規則(同 auto-verify 慣例,防雙源 drift)。設計依據:開工節與漂移處理 `docs/specs/harness-git-lifecycle/design.md`(2026-07-06);收尾節 `docs/specs/harness-pr-lifecycle/design.md`(2026-07-07 user 拍板,PR 收尾取代 local merge 預設)。(皆在 neigui repo)

## 開工節(各 command 第一個 phase 呼叫)

1. `git status` 確認 working tree 乾淨;不乾淨 → 停下問(commit / stash / 放棄)。
   - **當前不在 main** → 停下問(多半是上一輪流程沒收尾;分支一律從 main 開,不巢狀)。
2. `git fetch origin` 後比對 local main vs origin/main:
   - **落後** → `git pull --ff-only`(漂移來源:GitHub workflow 的 baseline commit、他機開發)
   - **領先**(本地 commit 未推)→ 提醒 user:PR 收尾預設下,收尾節會要求先推平才能開 PR,建議現在就走鐵則 H 的 main push 確認推平;user 不推也可照常繼續(收尾時再處理)
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
2. 在分支上 `git fetch origin` 檢查兩件事:
   - **origin/main 動了沒**(判準:`git merge-base --is-ancestor origin/main HEAD` 成立 = 未動):未動 → 續;**動了(漂移路徑)** → `git switch main` + `git pull --ff-only` → 切回分支 `git rebase main`(衝突 → `git rebase --abort` 停下回報)→ 在 rebase 後的分支上**重跑 auto-verify 自動化節**;紅 → 停下回報,分支保留。
   - **local main 領先 origin/main 沒**(判準:`git rev-list --count origin/main..main` > 0):領先 → 停下要求先推平(走鐵則 H 的 main push 確認)— 否則 PR merge 後 origin/main 與 local main 永久分岔。全 PR 模式下 main 只從 GitHub 拉,「領先未推」應收斂為異常狀態。
3. **Review 補齊**(merge 前對完整 diff 的最終 code review;2026-07-07 拍板「補齊缺口不重跑」):
   - /bug /refactor /perf:跑 `/code-review`(medium)→ `superpowers:receiving-code-review` 逐條分類 → P0/P1 修完才進步驟 4(3 輪上限,超限依鐵則 F 回報)。P2 彙總計數不逐條 receiving,疑似行為級例外展開(同 /mod Phase 5 輸出契約)。
   - /feat /mod:讀自評結束時記錄的 `self_review_head`(/feat 在 state.json;/mod 在 change-spec.md 末尾)→ `git rev-list <self_review_head>..HEAD` 非空才對增量 diff 補一輪 medium `/code-review`;為空 → 沿用自評結果不重跑。**欄位缺失 / null**(2026-07-07 改版前已在途的 feature)→ 保守視同有增量,補跑一輪 medium(無法證明 diff 已被 review 過就 review),並順手回填欄位。
4. `git push -u origin <prefix>/<slug>` — **單獨一條指令下**(push-gate 對此嚴格 fullmatch 格式放行;與其他指令串接、帶額外 flag 都會 fail-closed 跳確認)。
5. `gh pr create`,body 四段:變更摘要 / review 結果摘要(finding 數 + 分類)/ 驗證證據(測試數字、截圖路徑)/ 試用指引。同分支已有 open PR → push 已更新它,跳過 create。
6. **單一確認點**:回報 PR URL + review 摘要 + 試用指引後,**同一 turn 直接發** `gh pr merge --rebase --delete-branch` — push-gate 的 ask 確認框就是「是否 merge」提示,user 可掛著慢慢試用:
   - **allow** → GitHub rebase merge + 遠端 / 本地分支刪除 → `git switch main` + `git pull --ff-only`,收尾完成。
   - **deny** → 流程停下收 feedback;修正後 push 更新同一 PR(**沿用步驟 4 完整形式** `git push -u origin <prefix>/<slug>`,冪等可重複;bare `git push` 會被 push-gate ask,破壞單一確認點),重新進本步驟。
   - merge 方式一律 `--rebase`:保留三類分離 commit 與 TDD tag(squash 會壓掉,`git log --grep` 機械驗證失效);linear history 與舊 local ff 等價。
7. **Fallback(無遠端 / 離線 / gh 未認證)**:`git switch main` → `git merge --ff-only <prefix>/<slug>`(一律 fast-forward,保留分類 commit)→ `git branch -d <prefix>/<slug>`(小寫 `-d` 天然防誤刪),回報註明 fallback 原因 + main 領先 origin N 個 commit 可 push。

## 異常處理(兩節共用)

| 情境 | 處置 |
|---|---|
| rebase 衝突(收尾漂移路徑) | `git rebase --abort` → 停下回報(列衝突檔),不自動解 |
| `--ff-only` 失敗(main 分岔) | 停下回報,不自動 rebase |
| 收尾 gate 沒過 | 留在分支上,回對應 phase(依各 command 失敗 routing) |
| user 中途放棄 | 分支保留;/feat 標 state.json `paused: <reason>`,其他流程口頭確認後才 `git branch -D` |
| 開工 `switch -c` 撞既有同名分支 | 停下問三選一:resume 該分支續作 / user 確認後 `git branch -D` 重開 / 改 slug |
| 開工時不在 main | 停下問;當前分支符合 `<prefix>/` 對照表才可選「resume 走完原流程含收尾」,否則(實驗分支 / detached HEAD)只有「user 確認處置該分支後回 main 重開」 |
| merge 確認 deny | 分支與 PR 保留,停下收 feedback;修正後 push 更新 PR 重發 merge |
| `gh pr create` 撞同分支既有 open PR | 沿用該 PR(push 已更新它),直接進單一確認點 |
| 步驟 4 push 成功但步驟 5 `gh pr create` 失敗(認證過期 / 斷網) | 停下回報(遠端分支已在、尚無 PR),**不走 local fallback**(會刪本地分支留遠端孤兒);恢復後重跑 `gh pr create` 續行 |
| `gh pr merge --rebase` 被 GitHub 拒(不可 rebase) | 停下回報,不自動改 merge 方式 |
| local main 領先 origin/main(收尾) | 停下要求先推平(鐵則 H main push 確認)後再續收尾 |

## 自主模式(/auto)

收尾 gate 全綠即自動走 PR 收尾(push 分支 / 開 PR / review 補齊全自動,不停);**`gh pr merge` 的 hook 確認框 = 必停檢查點**(2026-07-07 拍板,取代 2026-07-06「local merge 自動、push 必停」)。離線 fallback 的 local merge 同樣自動。
