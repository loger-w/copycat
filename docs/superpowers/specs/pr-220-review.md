# PR #220 Code Review 比較報告 · SHA c4e43f67
**Report projection schema**: 1

**PR**: [loger-w/copycat#220](https://github.com/loger-w/copycat/pull/220)
**標題**: refactor(backend): BarsCache 日 K 三份同鍵 dict 收成 _DailyEntry 一格(W3 B1,行為不變)
**作者**: loger-w
**分支**: `refactor/bars-cache-daily-entry` → `master`
**變更**: 10 檔案, +354 / -41
**審查日期**: 2026-09-09
**PR 狀態**: MERGED(post-merge 審查,closeout §4.5 自動觸發;findings 以留尾 / 收修 PR 處置,不阻擋任何出貨;merge commit `def15623`)
**Review input basis**: source repo id `R_kgDOTsITBg` + PR headRefOid `c4e43f679f967155300a210747c2c1782db37435`;destination repo id `R_kgDOTsITBg` + baseRefOid `45df8dbd8f8358fa1ca731dc940cb2915969d16e`;`input_binding: verified` —— `git fetch origin refs/pull/220/head` 取回的 commit = headRefOid 逐字相等,review worktree detached 於該 SHA,`git merge-base origin/master HEAD` = baseRefOid
**Review continuity**: `source_continuity=HISTORY_REWRITE`(rebase merge 改寫 SHA;分支已隨 `--delete-branch` 刪除,但 `refs/pull/220/head` 仍指 `c4e43f67`,產報告前重抓 headRefOid 仍為它);`base_changed=true`(origin/master 自 `45df8dbd` 前進至 `def15623`,內容 = 本 PR 自身 4 筆 rebase 後 commit `62cc1cdf` / `be9ec653` / `a6a5662b` / `def15623`,其後零新 commit);`review_context_changed=false`(審的是 PR head,與落地版逐檔等價)
**審查工具**: CC (Fable 5.1)(context-aware reviewer agents;實際 reviewer 模型以下一行與 dispatch receipt 為準)+ Codex 中性 **N-A(user 明示停用,沿 #188 / #190 / #199 / #202 / #211 / #218 前例)** + Codex 對抗式 **N-A(同上)** + Cross-axis verification(4.1 N-A / 4.2 以 **CC 同軸 code-reviewer 內部複查代替,非跨軸證據**)+ Gemini 軸 **N-A(user 明示停用,Flash / Pro 皆不跑)**
**Reviewer model 記錄規則**: 上一行只描述工具組合;固定模型 reviewer 不套用「繼承 main session 模型」,實際身分以下一行與 dispatch receipt 為準。
**Reviewer models**: orchestrator=claude-fable-5-1;primary reviewer=python-reviewer(requested=opus / observed=UNAVAILABLE,harness 不回報 runtime model;主語言 .py 100% 的 source 改動,單派不 chunk);內部複查=code-reviewer(requested=opus / observed=UNAVAILABLE;純讀碼 + grep baseline);spec-compliance-reviewer requested=opus / observed=UNAVAILABLE / effort=xhigh / tools=N-A(未派);Codex=N-A(user 停用);Gemini=N-A(user 停用)
**覆蓋 (ENH-A)**: |F|=10 → covered 4 / no-issues 6 / skipped 0 / **missed 0**(chunked: **否**,2 source 檔 / 137 source diff 行(+97 / −40),低於 15 檔 / 800 行門檻;10/10 per-file accounting 齊)
**定位 (ENH-B)**: anchored exact 5 / ambiguous 0 / **FAILED 0**(五條 anchor 在 worktree 逐字唯一命中:bars.py:219(reviewer 自報 218-219,校正為 219)/ bars.py:604 / test_bars.py:783 / verification.md:58-59 / compare_bars.py:34-35)
**React-doctor (2.97)**: N-A(非 React PR;F 無 .jsx / .tsx)
**Formal spec traceability (2.65)**: SKIPPED (C4_NO_NORMATIVE_CLAUSE)
**Blast radius (2.9)**: 空輸出跳過(`sem-pr-blast-radius.sh` 於 worktree 對 `origin/master` 執行、exit 0、零輸出;`sem` 未安裝)
**Quota (Gemini 軸)**: N-A(Gemini 軸未啟用)
**審查軸狀態**: primary(python-reviewer)PASS(5 findings + 10/10 accounting;另自跑 4000 序列 × 12 步隨機差分驗舊三 dict 版 vs 新版零分歧)/ security-reviewer N-A(無 trigger 面:未動 auth / cookie / 請求體解析 / 秘鑰讀取)/ spec-compliance-reviewer N-A(gate SKIPPED)/ Codex 中性 N-A(user 明示停用)/ Codex 對抗式 N-A(同上)/ Gemini Flash N-A(user 明示停用)/ Gemini Pro N-A(同上)/ cross-axis verification 4.1 N-A(無非 CC finding)、4.2 以同軸 code-reviewer 內部複查代替 PASS(5/5 verdict 齊、ID 集合精確相等、每列六欄齊)
**worktree**: `C:/side-project/copycat/.worktrees/review-pr-220`
**worktree HEAD**: `c4e43f679f967155300a210747c2c1782db37435`

**Report generation**: sha256:41914dcaf83951cf1ede87c001adabeb20090bef851248e0b55546ba004821fb

---
## [完整證據副檔](pr-220-review.audit.md)
### finding_uid 索引
[aacf9021dd35d4406717](pr-220-review.audit.md#發現總覽) · [91b5f8d5bdfd76fd699e](pr-220-review.audit.md#發現總覽) · [ca4b2cf3b7fd0fc79fe3](pr-220-review.audit.md#發現總覽) · [81816979194749fdfd51](pr-220-review.audit.md#發現總覽) · [d1b111c45b3f2d4ba518](pr-220-review.audit.md#發現總覽)
## 發現總覽
| # | 問題 | CC 主軸 | 內部複查(同軸) | 最終建議 | Action | Action 理由 |
|---|---|---|---|---|---|---|
| F-01 | `bars.py:219` `_DailyEntry` docstring 寫「收成一格後『無快照時標記必也不在』變成**結構保證**」,但三欄型別上各自 Optional、寫入半邊仍是 `daily_put` 的單點約定(只有 prune 半邊結構化);round-1 Spec-01 只回校了 design.md,同源的 code docstring 未同動 | LOW | CONFIRMED(LOW→LOW:純措辭精度、零 runtime;緩解 = 同 docstring 下一句已寫「三欄彼此獨立」、`_period_stale_or_empty` 註解只講機制;grep `結構保證` 全 repo 僅此一處超譯) | Nice to Have | `auto-fix` | 一行改「一條單點約定 + prune 的結構保證」,與 design.md 回校後措辭對齊 |
| F-02 | `bars.py:604` `_period_pre_final` docstring 殘留「標記的 **pop**」,收攏後 `daily_put` 是欄位指派無 pop;round-1 S-04 只修了 `PeriodBars` 那一處。內部複查另找出同型殘留 `bars.py:387`「不 pop 界前標記」與 `test_bars.py:169`「也不 pop 界前標記」,共三處 | LOW | CONFIRMED(LOW→LOW:純詞彙陳舊,句子實質主張重構後更成立;損害 = grep `pop` 會誤中 `bars.py:300` 的真 pop;範圍由 1 處擴為 3 處) | Nice to Have | `auto-fix` | 三處「pop」改「清成 None / 不清標記」,同 S-04 口徑 |
| F-03 | `test_bars.py:783` `_make_mutable_clock` docstring 寫「定稿界**兩個** class 共用的唯一一份」,本 PR 新增第三個呼叫端 `TestDailyEntryFields`(:171);同 PR 為同類理由維護了 `build_period` 的「三處 → 兩處」,此處數字沒跟 | LOW | CONFIRMED(LOW→LOW:測試 helper 註解計數失準、零測試行為;grep 呼叫點 3(171 / 800 / 1049)vs base 2(752 / 1001);該 helper 有 pr-171-review F-12 漂移前科) | Nice to Have | `auto-fix` | 改「三個 class 共用」或去掉數字 |
| F-04 | `verification.md:58-59` 真實環境表 10 列,但 `evidence/compare_bars.py::PATHS` 只 8 條、evidence txt 只 8 列;「分 K `tf=1`」與「`/api/calendar`」兩列(419 B / 183 B 位元組計法)不是該腳本的輸出,重跑對不上列數 | LOW | CONFIRMED(LOW→LOW:證據出處標示不精確非造假;失準的兩列是「未改功能抽查」旁證,不承載行為不變主張;房規是手動 curl 另立小節標示,例 `.claude/mod/bars-tristate-status/verification.md:29`) | Nice to Have | `auto-fix` | 兩條路徑補進 `PATHS` 重跑,或表格註明「手動 curl,不在腳本內」 |
| F-05 | `compare_bars.py:34-35` 只比 A == B、無正確性下限(不驗 200 / bars 非空),兩台同壞仍印 `RESULT: ALL SAME`;port 8731 / 8732 寫死而側車吃 argv | LOW | PARTIAL(LOW→LOW:前半 literally 成立但本次產物逐列 `200/200 … bars=5` + meta 可直讀、兩台同版由 `sidecar_bars.py:37` import 錨點 assert 與 `/api/health` git_sha 守住;後半 REFUTED —— 一次性取證腳本寫死 port、只 print 不 assert 是長期房規:`sc1_api_boundary.py:9` / `poll_futures.py:10` / `restart_trials.py:39` 同型) | 參考用 | `no-op` | 不改;要「取證腳本一律帶下限 assert」是新政策不是本 PR 缺陷,user 拍板才動 |

auto-fix 只是處置建議；沒有使用者另行下令，不修改 code、commit、push 或 PR。

F-01 finding_uid: aacf9021dd35d4406717 action=auto-fix
F-02 finding_uid: 91b5f8d5bdfd76fd699e action=auto-fix
F-03 finding_uid: ca4b2cf3b7fd0fc79fe3 action=auto-fix
F-04 finding_uid: 81816979194749fdfd51 action=auto-fix
F-05 finding_uid: d1b111c45b3f2d4ba518 action=no-op
### Inline Comments per Finding（直接複製貼到 PR review）
#### #1 這句「結構保證」講過頭了,寫入那半還是靠 daily_put 一個人守
**File**: `copycat/server/bars.py`
**Line**: 219

**Comment**:
```
三欄都是 Optional,`bars=None` 配一個非 None 的 `pre_final_written_at` 型別上完全合法 —— 「無快照時標記必也不在」
真正靠的是 `daily_put` 空手早退 + 只在非空 bars 後才寫標記這一條單點約定;結構化的只有 prune 那半(同鍵同格一刀清)。
design.md 在 round-1 Spec-01 已經改口成「一條單點約定 + prune 的結構保證」,這句 docstring 沒跟。
順手對齊一下就好:

    收成一格後 prune 的「同鍵同刪」由結構吸收;「無快照時標記必也不在」的寫入半邊仍是
    `daily_put` 的單點約定(空手早退、標記只隨非空 bars 寫入),不是型別級保證。
```
#### #2 「pop」這個字還留了三處,實作已經沒有 pop 了
**File**: `copycat/server/bars.py`
**Line**: 604

**Comment**:
```
`daily_put` 現在是 `entry.pre_final_written_at = now if now < DAILY_FINAL_TIME else None`,沒有 pop 這個動作;
拿 `pop` 去 grep 只會撞到 :300 的 `_empty.pop`。round-1 S-04 修了 `PeriodBars` 那句,這裡漏了,
同型的還有 :387 註解「含不 pop 界前標記」和 test_bars.py:169「也不 pop 界前標記」。
三處一起改成「清成 None」/「不清標記」跟 S-04 同口徑。
```
#### #3 helper 的「兩個 class 共用」現在是三個
**File**: `tests/server/test_bars.py`
**Line**: 783

**Comment**:
```
`_make_mutable_clock` 這輪多了 `TestDailyEntryFields`(:171,`test_daily_put_empty_is_noop_for_all_three` 推到 14:01 跨界)這個呼叫端,
docstring 還寫「定稿界兩個 class 共用的唯一一份」。這支 helper 就是 pr-171-review F-12 抓過會漂的那一支,
數字寫死下次改凍結點語意的人會漏看第三個。改「三個 class 共用」或乾脆不帶數字。
```
#### #4 表裡那兩列「未改功能抽查」用附上的腳本重跑不出來
**File**: `.claude/refactor/bars-cache-daily-entry/verification.md`
**Line**: 58-59

**Comment**:
```
真實環境那張表有 10 列,但 `evidence/compare_bars.py` 的 PATHS 只有 8 條、evidence txt 也只有 8 列;
`tf=1&days=2` 跟 `/api/calendar` 這兩列(還有「419 B / 183 B」這種位元組寫法)是另外手動 curl 的,
表頭卻寫「compare_bars.py 同請求 diff」。後手重跑對不上列數。
兩條補進 PATHS 重跑一次最乾淨;不然就在表格另立一小節「手動 curl(不在腳本內)」,
房規是這樣標的(例:.claude/mod/bars-tristate-status/verification.md:29)。
```
