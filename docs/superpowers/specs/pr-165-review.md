# PR #165 Code Review 比較報告 · SHA 7887075f
**Report projection schema**: 1

**PR**: [loger-w/copycat#165](https://github.com/loger-w/copycat/pull/165)
**標題**: fix(backend): 期貨日 K daily cache 加定稿界 14:00 —— 夜盤段不再是早上快照
**作者**: loger-w
**分支**: `fix/futures-daily-cache-night` → `master`
**變更**: 7 檔案, +399 / -18
**審查日期**: 2026-08-31
**PR 狀態**: MERGED(post-merge 審查;findings 以留尾 / 收修 PR 處置)
**Review input basis**: source repo id `R_kgDOTsITBg` + source SHA `7887075f877386f47c2007a94ffab9108ab08411`;destination repo id `R_kgDOTsITBg` + destination SHA `7d121a02940d93974919df1f06a63aa5824b305b`;`input_binding: verified`(worktree HEAD == source SHA 精確比中;diff 以 merge-base `68833b6c` 三點語意計)
**Review continuity**: `source_continuity=CURRENT`(head OID 未變;分支已隨 rebase merge 刪除);`base_changed=true`(origin/master 已前進至 `81ab5d05`,含本 PR 之 rebase merge 與後續 #166);`review_context_changed=true`(通知性質;本輪無 PR mutation 計畫)
**審查工具**: CC (Fable 5)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 **N-A** + Codex 對抗式 **N-A** + Cross-axis verification(4.1 N-A / 4.2 以 **CC 內部複查替代、非跨軸**)+ Gemini 軸 **N-A**(本機無 `codex` / `agy` CLI,四軸全數不可用;Step 2.96 / 2.98 詢問因軸不可用而略過,degrade 依 Error Handling「CC 軸必備、其餘軸缺席註明」)
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5;primary reviewer=python-reviewer(requested=opus / observed=UNAVAILABLE,harness 不回報 runtime model);內部複查=code-reviewer(requested=opus / observed=UNAVAILABLE);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=N-A(未派);Codex=N-A;Gemini=N-A
**覆蓋 (ENH-A)**: |F|=7 → covered 4 / no-issues 3 / skipped 0 / **missed 0**(chunked: 否,3 source 檔 / 417 diff 行低於門檻)
**定位 (ENH-B)**: anchored exact 10 / ambiguous 0 / **FAILED 0**(F-01 雙 anchor 各一)
**React-doctor (2.97)**: N-A(非 React PR — F 無 .jsx/.tsx,唯一前端檔 day-bars-rollover.ts 為 .ts 純註解)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_IMPLEMENTATION_BINDING_CLAUSE)
**Blast radius (2.9)**: 空輸出跳過(`sem-pr-blast-radius.sh` 於 worktree 執行、零輸出)
**Quota (Gemini 軸)**: N-A(Gemini 軸未啟用)
**審查軸狀態**: primary(python-reviewer)PASS(9 findings + 7/7 per-file accounting)/ security-reviewer N-A(無 trigger 面)/ spec-compliance-reviewer N-A(gate SKIPPED)/ Codex 中性 FAIL(`codex` CLI 不存在於本機,`which codex` 空)/ Codex 對抗 FAIL(同上)/ Gemini Flash FAIL(`agy` CLI 不存在,`which agy` 空)/ Gemini Pro N-A(未 opt-in 且 CLI 不存在)/ cross-axis verification FAIL(無第二獨立軸)→ 以 CC 內部複查(code-reviewer,9/9 verdict)替代,結果標示為**同軸內部複查、非跨軸證據**
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-165`
**worktree HEAD**: `7887075f877386f47c2007a94ffab9108ab08411`

**Report generation**: sha256:5e149db4261f89b8e1fceb40db36ab1f5a4c908c96b5f9c324a6ce56e330144a

---
## [完整證據副檔](pr-165-review.audit.md)
### finding_uid 索引
[1ab4972b2652f1f3829c](pr-165-review.audit.md#發現總覽) · [d94fbd0a11eb597635cc](pr-165-review.audit.md#發現總覽) · [73c1eac28654d3d11fca](pr-165-review.audit.md#發現總覽) · [351b6ebfde549a1f39a8](pr-165-review.audit.md#發現總覽) · [35896d2b770f096b445d](pr-165-review.audit.md#發現總覽) · [ce362d0b26e3417b955b](pr-165-review.audit.md#發現總覽) · [3629a765bb0288390f12](pr-165-review.audit.md#發現總覽) · [da90790e519259ab1b5e](pr-165-review.audit.md#發現總覽) · [88251b4d6e4f18e69457](pr-165-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | CC 主軸 | 內部複查(同軸) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| F-01 | `DAILY_FINAL_TIME=14:00` 與 app.py `_calendar_crosscheck` 的 14:00 是兩份互不知情的字面值 | MED | PARTIAL(降 LOW:兩 predicate 語意不同、「誤發 WARNING」因果鏈不成立) | Nice to Have | `auto-fix` | 各補一行交叉註記即可、零行為 |
| F-02 | 墊背路徑零 log、build_period 墊背回應與新鮮取數逐字相同 | MED | PARTIAL(降 LOW:上游 engine 失敗時已有固定可 grep WARNING;真正靜默僅「ok+空」一格;D/W/M 無 status 屬既有白名單) | Nice to Have | `auto-fix` | 比照同檔 584 行慣例補一行 INFO |
| F-03 | 「失敗窗沿 EMPTY_TTL_SECS 重試至成功」措辭與請求驅動現實矛盾(前端三個空態自癒因墊背非空全不觸發) | MED | PARTIAL(降 LOW:行為已是 spec 明文知情留尾、殘留純文字口徑) | Nice to Have | `auto-fix` | 三處文字改口徑、不動 code |
| F-04 | `_period_stale_or_empty` 的 W/M 墊背形狀零測試(`return TaggedBars(stale, tag)` 突變體全綠) | LOW | CONFIRMED(墊背窗週/月 K 可回未聚合日 K、零錯誤訊號) | Nice to Have | `auto-fix` | 既有測試尾補 3 行 `period="W"` 斷言 |
| F-05 | `is_partial_last` tf=D 日曆日判準使大盤頁 14:00–24:00 印「最後一根未收盤」但 bar 已定稿 | LOW | PARTIAL(「修前恰好對」不成立 —— 冷啟動晚問同樣誤標;`is_partial_last` 不在 diff 內、非本 PR 引入) | Nice to Have | `no-op` | 非本 PR 引入;docstring 註記 + 是否讓 D 分支吃界走 next-time /mod |
| F-06 | app.py index_overlay docstring「同日兩端點只發一次 DK 取數」被定稿界改成至多兩次、未同步 | LOW | CONFIRMED(本 PR 造成的 docstring 漂移;共用同格主張仍真、只有次數失真) | Nice to Have | `auto-fix` | 句尾補「至多兩次」一行 |
| F-07 | verification.md「六條」「6 條全綠」是收修前快照,實際 8 條 | LOW | CONFIRMED(同檔下節已載 S-1/S-2 補測與 61 綠、可對帳,僅回校漏做) | Nice to Have | `auto-fix` | 兩處數字回校(repo 有 pr-159 F-03 回校前例) |
| F-08 | prune 對 `_daily_pre_final` 的清理零測試 + 無條件重建 set 與鄰居形狀不一致 | LOW | REFUTED(鄰居 `_daily_tag` prune 306-307 同構、同樣零測試、長期未爆;要補就整段一起、非本 PR 債) | 參考用 | `no-op` | baseline 反證;純記憶體上限 ~code 數×交易日數 |
| F-09 | 界值 14:00:00 整無測試,`>=`→`>` / `<`→`<=` 突變體存活 | LOW | REFUTED(`MIDNIGHT_BUFFER_END` 精確界 00:10 平行未釘、同突變體同樣存活未爆;界上一秒失效方向良性且 S-4 已知情) | 參考用 | `no-op` | baseline 反證;一秒窗無實害 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: 1ab4972b2652f1f3829c action=auto-fix
F-02 finding_uid: d94fbd0a11eb597635cc action=auto-fix
F-03 finding_uid: 73c1eac28654d3d11fca action=auto-fix
F-04 finding_uid: 351b6ebfde549a1f39a8 action=auto-fix
F-05 finding_uid: 35896d2b770f096b445d action=no-op
F-06 finding_uid: ce362d0b26e3417b955b action=auto-fix
F-07 finding_uid: 3629a765bb0288390f12 action=auto-fix
F-08 finding_uid: da90790e519259ab1b5e action=no-op
F-09 finding_uid: 88251b4d6e4f18e69457 action=no-op
### Inline Comments per Finding（直接複製貼到 PR review）
#### #1 這個 14:00 在 app.py 還有一份、彼此不知道對方存在
**File**: `copycat/server/bars.py`
**Line**: 73

**Comment**:
```
DAILY_FINAL_TIME = time(14, 0) 跟 app.py:566 _calendar_crosscheck 的 _clock_time(14, 0)
長得一樣但語意不同 —— 這邊問「今日 DK 定稿了沒」(全 code)、那邊問「今日 IX0001 DK
存在了沒」(只 boot 跑一次)。複查過:把這邊往後調不會弄壞那邊的判斷,所以不用 import
同動;但下一個調界值的人會想知道另一份在哪 —— 兩邊註解各補一行「另一個 14:00 讀者在
app.py:566 / bars.py:73,語意不同刻意分家」就好。
```
#### #2 墊背路徑一行 log 都沒有,3am 分不出「定稿到手」還是「一直吃墊背」
**File**: `copycat/server/bars.py`
**Line**: 506-513

**Comment**:
```
_period_stale_or_empty / _daily_stale_or_empty 走到墊背時 payload 跟新鮮取數長一模一樣
(舊 tag 也是 "tc4_dk"),而 D/W/M 又沒有 status 欄。上游 engine 失敗那刻是有固定
WARNING 可 grep 的,真正全靜默的只剩「TC4 回 ok + 空」這一格 —— 但墊背這層自己補一行
比照同檔 build_minute 584 行的慣例最省事:

logger.info("bars %s: 定稿界後 refetch 空手,墊背舊快照(%s)", key, day)

失敗窗最多 15 s 一行,可接受;不想吵就 per (code, day) 印一次。
```
#### #3 「重試至成功」這句話會被當自癒承諾讀,實際是「下一個請求才重試」
**File**: `copycat/server/bars.py`
**Line**: 71-72

**Comment**:
```
「refetch 失敗窗沿 EMPTY_TTL_SECS 節奏重試至成功」—— cache 沒有背景 refresher,重試是
請求驅動;而墊背回的是非空快照,前端三條空態自癒(retryEmpty / barsPollInterval /
useIndexOverlay 輪詢)全都以「bars 空」為觸發條件 → 掛著的分頁到午夜前不會再問,實務上
等於 F5 才重試。行為本身是 next-time 已知情的留尾、不用動 code,但這句(bars.py doc +
diagnosis.md + review JSON S-7 同句)改成「失敗窗的重試由下一個請求驅動,節奏上限
EMPTY_TTL_SECS 一次」比較不會誤導。
```
#### #4 墊背窗的週/月 K 沒測到 —— `_shaped` 那行改壞會拿日 K 冒充週 K
**File**: `copycat/server/bars.py`
**Line**: 513

**Comment**:
```
_period_stale_or_empty 裡的 _shaped(stale, period) 是它四個呼叫點裡唯一沒測試蓋的
(tests 裡 build_period 13 處全是 "D")。把它改成 return TaggedBars(stale, tag) 突變體
全綠 —— 失效樣態是墊背窗內週/月 K 直接回最多 1500 根日 bar,圖照樣畫得出來零訊號。
test_period_expired_refetch_empty_falls_back_to_stale 尾巴補一次 period="W" 請求、
斷言根數 < 日 bar 數,3 行了事。
```
#### #6 index_overlay docstring 的「同日只發一次 DK」已經不成立了
**File**: `copycat/server/app.py`
**Line**: 1620

**Comment**:
```
「同日兩端點只發一次 DK 取數」—— 定稿界落地後這格同日會作廢一次,成本變「至多兩次
(界前一次、界後定稿一次)」。bars.py 自己的 doc 已改口徑、這句沒跟。這是別人日後估
TC4 取數預算會引用的句子,句尾補一句就好。
```
#### #7 verification.md 的測試數停在收修前快照
**File**: `.claude/bug/futures-daily-cache-night/verification.md`
**Line**: 37

**Comment**:
```
「TestDailySnapshotFinality 六條」「反向驗證 …6 條全綠」是 review 收修前的數字,
S-1/S-2 補的兩條寫在下一節、實檔是 8 條。同檔下節有 61 綠可對帳所以不至於誤導,
但唯一列測試清單的那節跟現況對不上 —— 六→八、並把兩條併進清單(pr-159 F-03 有
回校前例)。
```
