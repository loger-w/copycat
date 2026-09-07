# PR #202 Code Review 比較報告 · SHA ca235bac
**Report projection schema**: 1

**PR**: [loger-w/copycat#202](https://github.com/loger-w/copycat/pull/202)
**標題**: mod(next-time-w1): 2026-09-07 盤點批 —— C17 日 K 末根定稿界 / B3 seed send close_sent / B2 新增群組保留輸入 + 置頂 + 守門 / B11 B15 測試 / B14 ruff PLE1205-1206
**作者**: loger-w
**分支**: `mod/next-time-batch-w1` → `master`
**變更**: 14 檔案, +574 / -56
**審查日期**: 2026-09-08
**PR 狀態**: MERGED(post-merge 審查,closeout §4.5 自動觸發;findings 以留尾 / 收修 PR 處置,不阻擋任何出貨)
**Review input basis**: source repo id `R_kgDOTsITBg` + source SHA `ca235bac8b7da203abef18c101e72a5362a01bd5`;destination repo id `R_kgDOTsITBg` + destination SHA `556f497266a735f71688926d58c0ab902cd4f54d`;`input_binding: verified`(`refs/pull/202/head` FETCH_HEAD 逐字等於 headRefOid、worktree HEAD 同值;baseRefOid = `git merge-base` 同值)
**Review continuity**: `source_continuity=CURRENT`(產報告前重抓 headRefOid `ca235bac` 未變;分支已隨 rebase merge 刪除);`base_changed=true`(origin/master 自 `556f4972` 前進至 `e75837da`,內容 = 本 PR 的 rebase merge 9 筆,其後零新 commit);`review_context_changed=false`(head 未動,base 前進即本 PR 自身落地)
**審查工具**: CC (Fable 5.1)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 **N-A(user 明示停用,沿 #188 / #190 / #199 前例)** + Codex 對抗式 **N-A(同上)** + Cross-axis verification(4.1 N-A / 4.2 以 **CC 同軸 code-reviewer 內部複查代替,非跨軸證據**)+ Gemini 軸 **N-A(user 明示停用,Flash / Pro 皆不跑)**
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5-1;primary reviewer=python-reviewer(requested=opus / observed=UNAVAILABLE,harness 不回報 runtime model;.py 改動行 69 vs .ts/.tsx 52 → python 57% 為主語言,tsx 檔納入同一 reviewer 的 per-file accounting);內部複查=code-reviewer(requested=opus / observed=UNAVAILABLE);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=N-A(未派);Codex=N-A(user 停用);Gemini=N-A(user 停用)
**覆蓋 (ENH-A)**: |F|=14 → covered 4 / no-issues 10 / skipped 0 / **missed 0**(chunked: 否,10 source 檔 / 630 diff 行低於 15 檔 or 800 行門檻)
**定位 (ENH-B)**: anchored exact 5 / ambiguous 0 / **FAILED 0**(五條 anchor 皆在 worktree 以 grep 逐字唯一命中:useMarketBars.ts:74 / app.py:1894 / pyproject.toml:22 / WatchlistManagerDialog.tsx:99 / WatchlistManagerDialog.tsx:123)
**React-doctor (2.97)**: 未引入新問題(`--scope changed --base 556f4972 --json`:newCount 1 / fixedCount 1 / baseTotalCount 3,changedFileCount 3 —— new 與 fixed 是**同一條** `no-high-complexity-react-function` `WatchlistManagerDialog.tsx:42`,diagnostic id 含訊息文字,複雜度數字隨新增的 `addInFlight` 分支上調而換 id;master 基準 `--scope all` 同規則同檔同行本就存在,實質零新引入)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_SPEC_DOCUMENT)
**Blast radius (2.9)**: 空輸出跳過(`sem-pr-blast-radius.sh` 於 worktree 對 `origin/master` 執行、exit 0、零輸出)
**Quota (Gemini 軸)**: N-A(Gemini 軸未啟用)
**審查軸狀態**: primary(python-reviewer)PASS(5 findings + 14/14 per-file accounting)/ security-reviewer N-A(無 trigger 面:未動 auth / cookie / 使用者輸入解析;`ws_stock` 的入站 view 解析未在 diff)/ spec-compliance-reviewer N-A(gate SKIPPED)/ Codex 中性 N-A(user 明示停用)/ Codex 對抗式 N-A(同上)/ Gemini Flash N-A(user 明示停用)/ Gemini Pro N-A(同上)/ cross-axis verification 4.1 N-A(無非 CC finding)、4.2 以同軸 code-reviewer 內部複查代替 PASS(5/5 verdict 齊、ID 集合精確相等、每列四欄齊)
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-202`
**worktree HEAD**: `ca235bac8b7da203abef18c101e72a5362a01bd5`

**Report generation**: sha256:b5e885dbdf6c93ae1be2c5b4d7f151b5b009d14fa152b9967364e4819cf71e49

---
## [完整證據副檔](pr-202-review.audit.md)
### finding_uid 索引
[f648446dc88b40d2f5ad](pr-202-review.audit.md#發現總覽) · [a62556dc6e926b6fc042](pr-202-review.audit.md#發現總覽) · [bd1bcb263631c72418f8](pr-202-review.audit.md#發現總覽) · [4387e81e15a891a5138d](pr-202-review.audit.md#發現總覽) · [601bd3e8d936d9f0e341](pr-202-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | CC 主軸 | 內部複查(同軸) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| F-01 | C17 只對「重新載入」的大盤頁生效:`useMarketBars.ts:74-86` D/W/M 的 staleTime / refetchInterval 到午夜才重問,整天掛著的 preview 頁 14:00 後仍印「· 最後一根未收盤」;round-1 S-04 只改寫判準措辭,`docs/next-time.md` 無對應留尾(08-31 第 53 行那條只講期貨 15:00 錨定界) | MED | CONFIRMED(降 LOW:錯的只有 meta 字尾文案,bar 值正確;無緩解層 —— tab hidden 不 unmount、200 降級不進 60 s 重試;spec 未排除、W2 的 C16 也不涵蓋) | Nice to Have | `auto-fix` | 純文件:補一條留尾併 W2 與 C16 同議「大盤日 K 的 14:00 界要不要進 dayBarsRefetchInterval」 |
| F-02 | `pyproject.toml:22` 用 `select` 凍住預設集,註解寫「保留預設」但 ruff 日後調預設不會跟;`extend-select` 才是字面語意 | LOW | CONFIRMED(`ruff 0.15.20 --show-settings` enabled = E4/E7/E9/F 系,當下零差異;全庫無第二處可比照) | Nice to Have | `auto-fix` | 一行設定改 `extend-select = ["PLE1205", "PLE1206"]`,零行為 |
| F-03 | `WatchlistManagerDialog.tsx:99` 關窗再開無條件 `setAddInFlight(false)`,加上 `:124` 的 onSettled 無 key 解除:送出後立刻關窗再開可再送一發、第一發 settle 又放掉第三發 —— S-02 要擋的「第二發假 BAD_GROUP」在此路徑仍可達 | LOW | PARTIAL(可達但窗極窄:要在 PUT 在途中關窗再開並**重打同一組名**;後果 = 群組已建立卻跳 BAD_GROUP 橫幅,`addGroup` 冪等無資料遺失;`renameInFlight` 的開窗重置 `:98` 長期同形未見事故 → 非本 PR 新引入;keyed 解除只補第三發那半) | Nice to Have | `auto-fix` | onSettled 改 keyed 解除(比照 renameInFlight);開窗重置維持與 rename 同形 |
| F-04 | `WatchlistManagerDialog.tsx:116-125` 「只清送出的那個名字」那六行註解講的是 `:122` 的 onDone,中間被 `:119` 守門行隔開,讀起來像在解釋守門 | 參考用 | CONFIRMED(純可讀性;同檔 `submitRename` `:141-143` 是守門在前、註解緊貼 commit,有現成排法可比照) | Nice to Have | `auto-fix` | 守門連同其註解上移到空字串早退之後 |
| F-05 | `app.py:1894-1903` `period_bars_pre_final` 在 `build_period` 之後再讀一次快取,跨 await 兩發併發時 B 的 `daily_put` pop 掉標記可能讓 A 把界前快照標成已定稿 | LOW | REFUTED(兩道各自獨立:① route 內 `await build_period` 與 `period_bars_pre_final` 之間零 await,事件圈內不可插隊;② `daily_put` 是同一段同步碼「先寫 `_daily` 再 pop」,標記已 pop ⇔ `_daily` 已是定稿值,A 的墊背拿到的就是 B 的定稿 bars,`pre_final=False` 屬實) | 參考用 | `no-op` | 非缺陷;兩讀合一的重構(build_period 回墊背旗標)可入 W3 但不必要 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: f648446dc88b40d2f5ad action=auto-fix
F-02 finding_uid: a62556dc6e926b6fc042 action=auto-fix
F-03 finding_uid: bd1bcb263631c72418f8 action=auto-fix
F-04 finding_uid: 4387e81e15a891a5138d action=auto-fix
F-05 finding_uid: 601bd3e8d936d9f0e341 action=no-op
### Inline Comments per Finding（直接複製貼到 PR review）
#### #1 這個修法只救得到「重新載入」的大盤頁,整天掛著的那頁 14:00 後還是印「未收盤」
**File**: `frontend/src/hooks/useMarketBars.ts`
**Line**: 74-86

**Comment**:
```
C17 在後端把 tf=D 的 partial_last 改成 14:00 後回 False,但這支 hook 的日 / 週 / 月 K
staleTime 撐到午夜、refetchInterval 也是 msUntilDayRollover → 早上載入的那份 body
整個下午不會再問後端,MarketChart.tsx:162 那句「· 最後一根未收盤」照印到 00:01。
看盤日常正是 preview 整天掛著,所以主要情境其實沒被蓋到;只有 F5 / 新開分頁才對。

不是要現在改 code —— 只是 next-time 裡沒有這條(08-31 那條只講期貨 15:00 錨定界,
明寫「只有期貨那支該吃 15:00 界」)。建議補一條留尾,併 W2 的 C16 一起議:
大盤日 K 的重抓時點要不要加 14:00 這一界,或前端比照 FuturesChart 自算不信 partial_last。
```
#### #2 這裡用 `select` 其實把 ruff 預設集凍住了,想「保留預設」該用 `extend-select`
**File**: `pyproject.toml`
**Line**: 18-22

**Comment**:
```
select = [...] 是「只跑這幾組」,E4/E7/E9/F 是現在 0.15.20 的預設沒錯(已用
--show-settings 核過,今天零差異),但哪天 ruff 調預設就不會跟著動,而註解寫的是「保留預設」。

extend-select = ["PLE1205", "PLE1206"] 一行就是字面語意,預設集交給 ruff 自己維護。
```
#### #3 送出後立刻關窗再開,守門就被放掉了
**File**: `frontend/src/components/stock/WatchlistManagerDialog.tsx`
**Line**: 99

**Comment**:
```
prevOpen 那段重開時無條件 setAddInFlight(false),而 :124 的 onSettled 也是無條件 false。
PUT 在途中關窗再開 → 旗標歸零 → 重打同一個名字再送會排進佇列 → 第一發成功後第二發撞名
跳「群組名稱不合法」(群組其實已建好);接著第一發的 onSettled 又把旗標放掉,第三發也能排。
窗很窄、群組不會壞(addGroup 冪等),只是橫幅誤導。

renameInFlight 的開窗重置(:98)長期就是這樣、沒出過事,所以重置那半可以不動;
onSettled 那半比照 renameInFlight 改 keyed 解除就好:
  const [addInFlight, setAddInFlight] = useState<string | null>(null);
  ...
  () => setAddInFlight((cur) => (cur === name ? null : cur)),
```
#### #4 這六行註解講的是 onDone 那段,中間被守門那行隔開了
**File**: `frontend/src/components/stock/WatchlistManagerDialog.tsx`
**Line**: 116-125

**Comment**:
```
「群組名輸入框只在成功後清 … 只清這一發送出的那個名字」講的是 :122 的 onDone,
但 :119 的 if (addInFlight) return 夾在中間,第一眼會以為那段在解釋守門。
同檔 submitRename(:141-143)是守門在前、註解緊貼 commit —— 把守門連同它那行註解
上移到 if (name === "") return 之後,註解就直接貼著它要講的 commit 了。
```
## 沒做的部分（結案對帳）
- Codex 中性軸:N-A —— user 明示「不用 Gemini 跟 Codex」(09-05 起 per-PR override,沿 #188 / #190 / #199 前例),未起軸、未 retry。
- Codex 對抗式軸:N-A —— 同上。
- Gemini Flash 軸:N-A —— user 明示停用。Gemini Pro:N-A(同上;Step 2.96 依前例不再問)。
- Step 2.98 Codex preset 詢問:N-A(Codex 停用,依前例不再問)。
- Cross-axis verification 4.1:N-A(無非 CC finding)。4.2:以同軸 code-reviewer 內部複查代替(PASS,5/5),**非跨軸證據** —— 三條 CONFIRMED 全來自同一模型家族,user 讀 Nice to Have 時應據此下調權重。
- Blast radius(2.9):PASS(有跑)但空輸出跳過。
- React-doctor(2.97):PASS,未引入新問題(new 1 / fixed 1 為同一條既有規則換 id,見 header)。
- Formal spec traceability(2.65):SKIPPED (C4_NO_SPEC_DOCUMENT);spec-compliance-reviewer 未派。
- Author calibration(2.2):無檔、本輪無套用。
- Reviewer 未實跑前端測試 / 型別:review worktree 無 `node_modules`,python-reviewer 對 .tsx 純讀 code;前端綠燈證據引自 PR 內 `verification.md`(主 session 出貨前實跑 vitest 3021 / tsc 0 / eslint 0);後端四個觸及測試檔由內部複查於 worktree 實跑 162 passed。
- 未驗前提(集中揭露):F-01 的「常開 preview 頁不 unmount」為 code 讀取(`useMarketBars` D 分支不吃 `active`)+ CLAUDE.md §1 看盤日常敘述,未在真瀏覽器實錄 14:00 後文案;F-03 的窄窗路徑由 code trace 推得、未以測試重現(建議補案列於 Nice)。其餘 finding 的修法假設由內部複查逐條驗過(F-03 修法縮成 keyed 解除)。
- 真環境:本 PR 出貨時即標 prod 未重啟、UI 驗收點與 C17 / B3 判準留 user 下一交易日過目(見 PR body 試用指引與 `verification.md` §5);本 review 亦未驗。
- Self-Verify:已執行(`skill-verify-auditor`,requested=opus / observed=UNAVAILABLE;唯讀、只讀本草稿,零 tool 呼叫)。結果 R1–R10 全 PASS、`VERDICT: COMPLIANT`,輸出格式完整(十行 + 一行 verdict、順序正確、無 FAIL)→ 零修正,直接發布。
