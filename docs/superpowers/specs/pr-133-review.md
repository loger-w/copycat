# PR #133 Code Review 比較報告 · SHA f95441d1
**Report projection schema**: 1

**PR**: [loger-w/copycat#133](https://github.com/loger-w/copycat/pull/133)
**標題**: mod: 期貨 tab 分時圖改 15:00 夜盤起算的一天(錨定日 = 期交所口徑、05:00→08:45 空檔畫水平線)
**作者**: loger-w(commits 署名 Loger)
**分支**: `mod/futures-day-1500` → `master`(PR 狀態 MERGED,rebase merge 進 master 為 a32c5cc4;回溯 review)
**變更**: 21 檔案, +1053 / -342(含 1 張 binary 截圖)
**審查日期**: 2026-08-28
**Review input basis**: source repo R_kgDOTsITBg + f95441d1beb4a82fb2bbdb9fee7dd278931f281d;destination repo R_kgDOTsITBg + c80dbde5113c9743b443bd348b94a6258eece41f;`input_binding: verified`(`git fetch refs/pull/133/head` 後 FETCH_HEAD 與 headRefOid 逐字相等、worktree HEAD = source SHA;destination SHA 以精確 commit 綁定(`git rev-parse --verify c80dbde5…^{commit}` 成立),不用已前進的 `origin/master` 分支 ref)
**Review continuity**: `source_continuity=CURRENT`;`base_changed=false`(產報告前重抓 headRefOid / baseRefOid 與 reviewed 完全相同;PR 已 MERGED、分支已刪);`review_context_changed=false`
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-133`(detached)
**worktree HEAD**: f95441d1beb4a82fb2bbdb9fee7dd278931f281d
**審查工具**: CC (claude-fable-5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 N-A(本機無 codex CLI)+ Codex 對抗式 N-A(同上)+ Cross-axis verification(4.1 N-A 無非 CC finding;4.2 Codex 驗 CC first-pass N-A → 全部 INCONCLUSIVE,改由 4.3b 主 agent 判斷式複查)+ Gemini 軸 N-A(本機無 agy;Flash / Pro 皆未啟動)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary reviewers=typescript-reviewer ×2(chunked 兩塊並行;dispatch 顯式 model=opus、effort 依 frontmatter;observed=UNAVAILABLE —— Agent tool 回傳無 runtime model 欄位);domain reviewers=無(security-reviewer 未觸發:無 auth / request-body / secret 路徑);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=0(gate SKIPPED,未派);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=21 → covered 11 / no-issues 9 / skipped 1 / **missed 0**(chunked: 是;FILE_COUNT=14 源檔 ≤ 15 但 DIFF_LINES=1154 源檔行 > 800 → 依路徑排序切兩塊:chunk 1 = 6 檔 / 821 行(allday ×2、FuturesChart ×2、StockIntradayChart ×2),chunk 2 = 8 源檔 / 333 行 + 7 非源檔(CONTEXT / next-time / 5 個 artifacts);兩塊 accounting 6 + 15 = 21,union = F;skipped 1 = `evidence/SC-13_night_session_2026-08-28_0021.jpg` binary)
**定位 (ENH-B)**: anchored exact 12 / ambiguous 1 / **FAILED 0**(全部 anchor 於 worktree HEAD 以逐字比中;F-12 anchor `const dm = dayMinuteOf(b);` 命中 :76 / :85 兩處,取 reviewer 報的 74–86 區間內最近的 :76;F-14 anchor `<none>`(commit 訊息層),不計)
**React-doctor (2.97)**: 未引入新問題(既有 2 條不計)—— `npx react-doctor@latest --offline --no-score --scope changed --base c80dbde5 --json` 於 worktree `frontend/` 實跑:`newCount 0 / fixedCount 0 / baseTotalCount 2`,changedFileCount 14
**Formal spec traceability (2.65)**: SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED)
**Blast radius (2.9)**: 空輸出跳過(本機無 `sem`,`sem-pr-blast-radius.sh` exit 0 零輸出)
**Gemini 軸**: 按預設只跑 Flash —— 但本機無 `agy`,Flash 軸實際未啟動(N-A);因工具缺席 Step 2.96 未向 user 提問
**Codex preset**: 按預設 default —— 但本機無 `codex`,中性 / 對抗兩軸實際未啟動(N-A);因工具缺席 Step 2.98 未向 user 提問
**校準套用**: 無作者校準檔(loger-w.md 不存在;`docs/pr-review-calibration/` 目錄亦不存在)、本輪無套用
**Provenance (2.55)**: N-A(base = master,21 檔全部 authored)
**審查軸狀態**: primary(typescript-reviewer chunk 1)PASS(4 findings、6/6 accounting、8 條 PR 自我宣稱逐條核對);primary(typescript-reviewer chunk 2)PASS(9 findings、15/15 accounting、round-1 disposition 六條 + commit 慣例核對);domain(security-reviewer)N-A 未觸發;spec-compliance-reviewer N-A(gate SKIPPED);Codex 中性 N-A(無 CLI);Codex 對抗 N-A(無 CLI);Gemini Flash N-A(無 agy);Gemini Pro N-A(未啟用且無 agy);cross-axis verification 4.1 N-A(無非 CC finding)/ 4.2 FAIL→INCONCLUSIVE(無 codex,全部 CC finding 無交叉驗證)/ 4.3b PASS(主 agent 逐條實查,見備註欄;14 條 CONFIRMED 13 / REFUTED 1)/ 4.5 PASS(missed 0)/ 4.6 PASS;React-doctor PASS(新引入 0)
**Self-Verify**: auditor(skill-verify-auditor,dispatch model=opus)回 R1–R10 全 PASS、`VERDICT: COMPLIANT`;無需補寫

**Report generation**: sha256:5bb3aa59b49d212c5d4cf1f6639ca001da5caafca8808a628713515c1408e74e

---
## [完整證據副檔](pr-133-review.audit.md)
### finding_uid 索引
[473b40f7a93bde5a9cac](pr-133-review.audit.md#發現總覽) · [e7afe0c08b17714a9a40](pr-133-review.audit.md#發現總覽) · [bd625799f7df6be04695](pr-133-review.audit.md#發現總覽) · [e762e6769857bfb87a1b](pr-133-review.audit.md#發現總覽) · [953e2668871dbc475854](pr-133-review.audit.md#發現總覽) · [4748d991fa24526620a5](pr-133-review.audit.md#發現總覽) · [d3a4880ee61b6a810da7](pr-133-review.audit.md#發現總覽) · [5a9d8a48d439d3068761](pr-133-review.audit.md#發現總覽) · [fcd99456a3713e99baf0](pr-133-review.audit.md#發現總覽) · [049feda6cb1fc4ccb29c](pr-133-review.audit.md#發現總覽) · [9d43eb3cf97eebff4b47](pr-133-review.audit.md#發現總覽) · [9b0923daeed409128920](pr-133-review.audit.md#發現總覽) · [f001c935cb60c12e45c3](pr-133-review.audit.md#發現總覽) · [183025e6d8390e2d4cb5](pr-133-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | Opus | Cdx-N | Cdx-A | Gem-F | Opus 複查(非 Opus 軸) | 最終建議 | Action | Action 理由 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F-01 | verification §4 以「W12 `alldayFillPoints` 簽名不變、`git diff` 未觸函式體只改註解」結掉白名單,但 HEAD 上 P5 收修就是加第 4 參 `holidays` + 函式體改 `anchorDateOf(stamp, holidays)`(`.claude/mod/futures-day-1500/verification.md:58`) | MEDIUM [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent `git diff c80dbde5...HEAD -- fill-marks.ts` → `+  holidays?: ReadonlySet<string>,` / `-    if (anchorDateOf(stamp) !==` / `+    if (anchorDateOf(stamp, holidays) !==`;一句改成「簽名加選配 holidays、唯一 caller 已同源」 |
| F-02 | change-spec §3 W12「簽名不變(caller 零改)」同根未修訂 —— spec 是回歸依據,日後讀者會以為第 4 參是誤加(`.claude/mod/futures-day-1500/change-spec.md:40`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 同 F-01 證據;補一行「P5 後修訂」 |
| F-03 | `StockIntradayChart.tsx:1384` 註解「夜盤 00:00–05:00 的成交屬前一交易日」與新規則方向相反,且與同檔 1337 這一版剛改的「屬次一交易日」互相矛盾;:1388「近全軸窗 08:45–05:00」、:938「三段軸」同樣過期(SC-12 只改了三行) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent `sed -n 938p;1337p;1384p;1388p` 逐行核:1337 新口徑、其餘三行舊口徑;in-flow review P1 只點名三行、收修只改那三行 |
| F-04 | verification §1 七檔案數四檔錯(allday 寫 37 實 36、adapter 20 實 22、txf 14 實 13、calendar 15 實 16;§1 第 18 行自己寫 36/36 與第 11 行矛盾);總和 233 對、分項是事後補寫(`verification.md:11`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent `grep -cE '^\s*it\('` 七檔 → 36 / 22 / 54 / 13 / 16 / 53 / 39,`it.each` / `test(` 零;36+22+54+13+16+53+39 = 233 與宣稱總數相符 |
| F-05 | current-state 白名單 W1 要求「軸長 1140 + `alldayHhmmOf` 與 `alldayIndexOf` 互逆」,正是 SC-1(1365)/ SC-3(空檔索引也回時刻)要改掉的兩件事;下次被當回歸清單讀會得出相反結論(`current-state.md:40`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent 對照 change-spec SC-1 / SC-3 與 allday.test.ts「可交易索引互逆;空檔索引反查後 alldayIndexOf 回 null」;W1 改寫成真正不變的那部分 |
| F-06 | P5 唯一 regression lock「假日前夜盤:live 點與成交點跟 slice 吃同一份日曆」在正確實作下日曆載入前後畫面相同,`waitFor(length 3)` 可在日曆落地前通過 → 突變只在載入後才紅,判別力靠時序(`FuturesChart.test.tsx:284`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent 逐態推演:載入前兩邊皆讀空模組集合 → 錨定 08-19 一致 → 3 點 + 成交點都畫;突變體亦然;只有載入後(08-20 vs 08-19)才分家。作者 mutation 紅是時序運氣;姊妹條 :289 有「1 → 3」屏障、本條沒有 |
| F-07 | SC-12「死區」口徑更新漏三處測試文字:`fill-marks.test.ts:417` 標題、`FuturesChart.test.tsx:591 / :648` 註解;14:30 現在叫「一天之外」,與「空檔」成因處置都不同(`frontend/src/lib/fill-marks.test.ts:417`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent `grep -rn 死區 frontend/src` → 三處(排除 index-chart-svg.test 無關語境);源檔已清乾淨 |
| F-08 | `MINUTE_SNAP_RADIUS = 3` 的推導註解(「1139 個 key 壓 ~724px → 1px ≈ 1.6 key」)在 1365 軸下算不出來:snap 半徑實質縮 ~15%,且空檔 225 格內只有 08:45 一格橋、hover 中段 ±3 key 必落空(誠實行為但零文件)(`StockIntradayChart.tsx:1060`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent `grep -rn "1139\|1140"` → SIC.tsx:939 / 1060 / 1509 與 stock-intraday-svg.ts:159(不在 F)四處推導文字;`useFuturesBars.ts:21` 的 1140 是可交易分鐘數、仍正確不改。二選一:3 → 4 或改註解數字 + 補「空檔 snap 必落空是刻意」 |
| F-09 | code-review-round-1.json `reviewed_head` 指到 8c09cbaf,不在出貨歷史上(真正是 5316f857;verification §5 寫對了)—— 又一顆 dangling artifact SHA(`code-review-round-1.json:7`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent `git merge-base --is-ancestor` 逐顆:d6f93a12 NO / 8c09cbaf NO / 608b1cfc yes / 1dbb7775 yes / 5316f857 yes(chore commit 後來 `--amend` 帶入 next-time,SHA 變了、JSON 沒回填) |
| F-10 | `liveSlotOf` / `tradeSlotOf` 兩支 file-local helper 的 `holidays` 是選配,而 P5 的復發面正是「有人忘了傳」;各只有一個 caller,收成必填是零成本型別擋(`FuturesChart.tsx:135`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `auto-fix` | 主 agent grep → 定義 :98 / :135、caller :278 / :286 各一;lib 側維持選配(S7 已 rejected 記 next-time),本條只收元件內兩支 |
| F-11 | adapter 的 Σ / high-low 靠「key 恰等於 `ALLDAY_GAP.end`」認出橋 = 位置當哨兵;空檔段哪天變 tradable,落 1064 的真成交會靜默排除在量 / 均價 / 高低之外、零測試紅。現況安全(`alldayIndexOf` 對 0501–0845 一律 null、橋是唯一寫入者)(`futures-accum-adapter.ts:119`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `ask-user` | 改法是把 Σ / high-low 累加移到插橋之前(插橋後只排序),結構取捨;現況零行為問題,是否值得動由 user 決定 |
| F-12 | 解耦後 `txfBarsToSeries` 對 bars 掃兩遍(第一圈找日盤日、第二圈折 minutes),caller memo deps 含每拍 ~1 s 的 `txfP / txfTime` → 每秒 2 × ~5,700 次 `dayMinuteOf`;實測量級 < 1 ms、只在鈕開著時(`txf-overlay-series.ts:76`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | Nice to Have | `ask-user` | 主 agent 核 App.tsx:208 deps;修法 = 第一圈結果存陣列給第二圈(不可改「由尾往前找」,會破亂序防禦);效益 < 1 ms,做不做由 user |
| F-13 | next-time 勾銷行寫「出貨(#132)」,PR 是 #133 —— 但 #132 是本案的 GitHub **issue**(已 closed,標題同 PR),不是不存在的編號;只是 issue / PR 混寫沒標明(`docs/next-time.md:23`) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b **REFUTED**(#132 = issue) | 參考用 | `no-op` | 主 agent `gh issue view 132` → `issue #132 CLOSED mod: 期貨 tab 改 15:00…`;reviewer 只查了 `gh pr view 132`。順手可改「issue #132 / PR #133」,不算缺陷 |
| F-14 | commit `5316f857` subject 寫「StockIntradayChart / fill-marks / adapter 註解口徑改」,但該筆只動 CONTEXT.md / next-time.md / StockIntradayChart.tsx;fill-marks / adapter 的註解實際落在 `1dbb7775`(`reset --soft` 重打時分錯)。另 `1dbb7775` 🔴 行為與 🟢 測試同一筆(紅先行 commit 被併掉)(commit 訊息層,無 file:line) | LOW [typescript-reviewer] | — | — | — | 4.2 INCONCLUSIVE(無 codex);4.3b CONFIRMED | 參考用 | `no-op` | 主 agent `git show --stat 5316f857` → 3 檔、無 fill-marks / adapter;已 rebase merge 進 master,不重寫歷史;下次 `reset --soft` 重打後以 `git show --stat` 回填 subject |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 473b40f7a93bde5a9cac action=auto-fix
F-02 finding_uid: e7afe0c08b17714a9a40 action=auto-fix
F-03 finding_uid: bd625799f7df6be04695 action=auto-fix
F-04 finding_uid: e762e6769857bfb87a1b action=auto-fix
F-05 finding_uid: 953e2668871dbc475854 action=auto-fix
F-06 finding_uid: 4748d991fa24526620a5 action=auto-fix
F-07 finding_uid: d3a4880ee61b6a810da7 action=auto-fix
F-08 finding_uid: 5a9d8a48d439d3068761 action=auto-fix
F-09 finding_uid: fcd99456a3713e99baf0 action=auto-fix
F-10 finding_uid: 049feda6cb1fc4ccb29c action=auto-fix
F-11 finding_uid: 9d43eb3cf97eebff4b47 action=ask-user
F-12 finding_uid: 9b0923daeed409128920 action=ask-user
F-13 finding_uid: f001c935cb60c12e45c3 action=no-op
F-14 finding_uid: 183025e6d8390e2d4cb5 action=no-op inline=none
### Inline Comments per Finding（直接複製貼到 PR review）
#### F-01 W12 這句說「函式體沒動」,但 P5 的修就是動了它
**File**: `.claude/mod/futures-day-1500/verification.md`
**Line**: 58

**Comment**:
```
「W12 alldayFillPoints 簽名不變(git diff 未觸 fill-marks.ts 函式體,只改註解)」—— 一跑 git diff 就被推翻:
P5 收修加了第 4 參 holidays?: ReadonlySet<string>,函式體改成 anchorDateOf(stamp, holidays)。
既有 3 參 caller 不受影響是真的,但理由要換:
「W12:簽名加選配 holidays(既有三參呼叫相容);唯一 prod caller FuturesChart.tsx:254 已同步傳 holidaySet」。
```
#### F-02 spec 的 W12 也還是收修前的話
**File**: `.claude/mod/futures-day-1500/change-spec.md`
**Line**: 40

**Comment**:
```
§3 W12「alldayFillPoints 簽名不變(caller 零改)」在 P5 之後已經不成立(第 4 參 holidays + caller 改傳同一份日曆)。
spec 是日後回歸的依據,補一行:「P5 後修訂:簽名加選配 holidays,caller 必須傳與 anchorDate 同源的那一份」。
```
#### F-03 這行把錨定規則講反了,跟 47 行前剛改的那句打架
**File**: `frontend/src/components/stock/StockIntradayChart.tsx`
**Line**: 1384

**Comment**:
```
1384「夜盤 00:00–05:00 的成交屬前一交易日」—— 新規則正好相反(夜盤 15:01 → 05:00 屬**次一**交易日),
時段也漏了 15:01–23:59;同檔 1337 這一版已經改成「屬次一交易日的錨定日」,兩行互相矛盾。
順手一起改:1388「近全軸窗是 08:45–05:00」→ 15:00–13:45;938「近全三段軸」→ 四段。
```
#### F-04 這一格的七個數字有四個對不上,和自己第 18 行也打架
**File**: `.claude/mod/futures-day-1500/verification.md`
**Line**: 11

**Comment**:
```
第 11 行寫「allday 37、adapter 20、txf 14、trading-calendar 15」,HEAD 上 it( 實數是 36 / 22 / 13 / 16
(第 18 行自己就寫 allday 36/36)。總和 233 是對的,分項是事後補的。
直接貼 vitest 的 per-file 輸出,或改成「allday 36、adapter 22、FuturesChart 54、txf 13、trading-calendar 16、fill-marks 53、SIC.futures 39 = 233」。
```
#### F-05 W1 寫的是本案要改掉的東西,不是要守住的東西
**File**: `.claude/mod/futures-day-1500/current-state.md`
**Line**: 40

**Comment**:
```
白名單 W1「軸長 1140、alldayHhmmOf 與 alldayIndexOf 互逆」正是 SC-1(1365)/ SC-3(空檔索引也回時刻,不再全域互逆)要改的。
下次有人拿這張表當回歸清單會得出相反結論。改寫成真正不變的那部分:
「空檔 / 一天之外 alldayIndexOf 仍回 null;可交易索引與 alldayHhmmOf 仍互逆;三個可交易段的段界字串與後端 FUTURES_ALLDAY_DOMAIN 相同」。
```
#### F-06 這條「同一把尺」測試的紅靠時序,不靠結構
**File**: `frontend/src/components/futures/FuturesChart.test.tsx`
**Line**: 284

**Comment**:
```
正確實作下,日曆載入前(兩邊都讀空模組集合 → 錨定 08-19)和載入後(都讀 query → 08-20)畫面一樣:3 點 + 成交點都在。
所以 waitFor(length 3) 可能在日曆還沒落地時就過,接著同步斷言 last-dot 就跑完 ——
突變(live 改回讀模組集合)只在載入後才分家,現在紅是時序運氣。
補一個只有載入後才成立的屏障再斷言:ordersBody 多塞一筆 { date: "20260820", time: "09:00:30" } 的成交
(載入前 anchorDate 08-19 → 不畫;載入後 08-20 → 畫),先 await waitFor(fill-B-1079) 再驗 last-dot。
姊妹條 :289 的「1 → 3」就是這種屏障。
```
#### F-07 三處測試文字還在說「死區」,14:30 現在叫「一天之外」
**File**: `frontend/src/lib/fill-marks.test.ts`
**Line**: 417

**Comment**:
```
源檔註解已全面改成「空檔(05:01–08:45)/ 一天之外(13:46–15:00)」,只剩這條標題、FuturesChart.test.tsx:591 / :648 的註解還寫「死區」。
兩者成因處置不同(一天之外 = 不在這一天;空檔 = 在軸上要畫水平線),沿用舊詞會混。
這條標題改「一天之外的成交(14:30)→ 不畫」,那兩行註解改「非空檔 / 非一天之外」。
```
#### F-08 snap 半徑的推導註解已經算不出來
**File**: `frontend/src/components/stock/StockIntradayChart.tsx`
**Line**: 1060

**Comment**:
```
「1139 個 key 壓 ~724px → 1px ≈ 1.6 key」是 1140 軸的數字;現在 1365 個 key 壓同寬度 → 1.88 key/px,
MINUTE_SNAP_RADIUS = 3 的 ±1.9px 變 ±1.6px(縮 ~15%)。另外空檔 225 格裡只有 08:45 一格橋,
hover 落在空檔中段 ±3 key 必落空 → 十字與資料點不畫(對的行為,但沒寫)。
二選一:3 → 4 維持 ~±1.9px;或把 939 / 1060 / 1509 的數字改 1365 / ~1.9,並補一句「空檔段 snap 落空是刻意」。
stock-intraday-svg.ts:159 那句 1139 同型但不在本 PR。useFuturesBars.ts:21 的 1140 是可交易分鐘數,還是對的,別動。
```
#### F-09 reviewed_head 指到一顆不在歷史上的 SHA
**File**: `.claude/mod/futures-day-1500/code-review-round-1.json`
**Line**: 7

**Comment**:
```
"history rewritten after fixes → 608b1cfc / 1dbb7775 / 8c09cbaf":8c09cbaf 是 chore commit --amend 前的 SHA,
merge-base --is-ancestor 不成立;真正出貨的是 5316f857(verification §5 寫對了)。
artifacts commit 前用 git log --oneline 回填,不要憑 reset --soft 前的記憶寫。
```
#### F-10 這兩支 helper 的 holidays 可以直接必填
**File**: `frontend/src/components/futures/FuturesChart.tsx`
**Line**: 135

**Comment**:
```
liveSlotOf / tradeSlotOf 是 file-local、各只有一個 caller(:278 / :286),而 P5 那類 bug 就是「有人忘了傳」。
參數改成 holidays: ReadonlySet<string> | undefined(必填、可 undefined)零成本,型別就擋住下次漏傳;
lib 側的 anchorDateOf / sliceCurrentAllday / alldayFillPoints 維持選配(S7 已記 next-time),這裡只收元件內這兩支。
```
#### F-11 橋是靠「key 剛好等於 1064」認出來的
**File**: `frontend/src/lib/futures-accum-adapter.ts`
**Line**: 119

**Comment**:
```
Σ / high-low 迴圈用 k === ALLDAY_GAP.end 跳過橋 —— 橋跟真成交格唯一的差別是索引。現在安全
(alldayIndexOf 對 0501–0845 一律 null、橋是這一格唯一寫入者),但哪天空檔段變 tradable,落在 1064 的真成交會
靜默被排除在量 / 均價 / 高低之外,四個數字都只是數字,沒有測試會紅。
更穩的寫法:amountMilli / volume / high / low 在插橋**之前**對 rows 跑一遍,插橋後只做排序 —— 就不需要哨兵。
零行為問題,做不做你決定。
```
#### F-12 解耦後 bars 每秒被完整掃兩遍
**File**: `frontend/src/lib/txf-overlay-series.ts`
**Line**: 76

**Comment**:
```
第一圈掃日盤日、第二圈折 minutes,兩圈都對每根 bar 跑 dayMinuteOf → splitStamp;caller(App.tsx:208)的 memo deps
含每拍 ~1 s 的 txfP / txfTime,所以是每秒 2 × ~5,700 次。量級 < 1 ms、只在鈕開著時,純可選。
要收就把第一圈的 dayMinuteOf 結果存成陣列給第二圈用;別改成「由尾往前找第一根日盤 bar」,那會破掉檔頭刻意保留的亂序防禦。
```
## 沒做的部分（結案對帳）
- Codex 中性 / 對抗軸:FAIL(N-A)—— 無 `codex`。Gemini Flash / Pro:FAIL(N-A)—— 無 `agy`。Step 2.96 / 2.98 提問未執行(工具缺席)。
- Step 4.1 N-A;Step 4.2 FAIL → INCONCLUSIVE,以 4.3b 主 agent 實查代之(git diff / grep / sed / merge-base / gh issue)。
- sem blast radius:跑了,空輸出跳過。React-doctor:跑了,新引入 0(既有 2 條不計)。C4 SKIPPED (C4_AUTHORITY_PATH_NOT_ALLOWED,reducer 以 `PYTHONUTF8=1 py -3.14` 實跑;前兩次 `C4_CLI_INPUT_INVALID` 為 stdin cp950 解碼,非判定)。
- 自動化綠燈(全量 vitest / tsc / eslint / pytest)與 mutation 紅:本輪未於 worktree 複跑(無 node_modules、依 2.5.4 純讀 review),只引 verification.md 自陳;主 agent 在出貨前實跑過(見 PR body),但那不是本輪的獨立證據。
- 未驗證前提:F-06「作者 mutation 紅是時序運氣」為主 agent 推演,未實跑「日曆未載入 + 突變體」那一態;F-11 / F-12 的「現況安全 / < 1 ms」為 reviewer 追機制與量級估算,未實測。
- 真環境:SC-13 (b)–(e)(15:01 翻頁、次一交易日 08:46 水平橋 + 跳價、CDP 對 APP、個股頁夜盤疊線)待窗口,由 PR verification 自陳、本輪未新增證據;prod 8721 重啟後才看得到本 PR 畫面。
- Self-Verify:已執行,COMPLIANT(auditor 以 Read 讀取草稿檔本身,未讀其他產物;header 與本行為 auditor 回覆後填入,依指示判 N-A)
